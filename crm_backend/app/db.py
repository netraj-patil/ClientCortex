"""Saved database connections: storage, SQLAlchemy engines and schema helpers."""
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import URL, Engine

from . import config
from .redis_client import get_redis

CONNECTIONS_KEY = "crm:connections"
DRIVERS = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql", "sqlite": "sqlite"}

# conn_id -> (engine for CRM reads/writes, read-only engine used for LLM-generated SQL)
_engines: Dict[str, Tuple[Engine, Engine]] = {}
_lock = threading.Lock()


class ConnectionNotFound(Exception):
    pass


class ConnectionFailed(Exception):
    pass


def _fernet() -> Fernet:
    if not config.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    return Fernet(config.SECRET_KEY.encode())


def ensure_ready() -> None:
    _fernet()


def _build_url(rec: dict, password: Optional[str]) -> URL:
    if rec["db_type"] == "sqlite":
        return URL.create("sqlite", database=rec["database"])
    return URL.create(
        DRIVERS[rec["db_type"]],
        username=rec.get("username"),
        password=password,
        host=rec.get("host"),
        port=rec.get("port"),
        database=rec["database"],
    )


def _make_engines(rec: dict, password: Optional[str]) -> Tuple[Engine, Engine]:
    url = _build_url(rec, password)
    engine = create_engine(url, pool_pre_ping=True)
    ro_engine = create_engine(url, pool_pre_ping=True)
    dialect = ro_engine.dialect.name
    timeout_ms = config.QUERY_TIMEOUT_SECONDS * 1000

    # Every connection on the read-only engine is put in read-only mode with a timeout.
    # This is the safety net behind the SQL validation in pipeline.py.
    @event.listens_for(ro_engine, "connect")
    def _read_only(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        if dialect == "postgresql":
            cur.execute("SET default_transaction_read_only = on")
            cur.execute(f"SET statement_timeout = {timeout_ms}")
        elif dialect == "mysql":
            cur.execute("SET SESSION TRANSACTION READ ONLY")
            cur.execute(f"SET SESSION max_execution_time = {timeout_ms}")
        elif dialect == "sqlite":
            cur.execute("PRAGMA query_only = ON")
        cur.close()
        dbapi_conn.commit()

    return engine, ro_engine


def _check(engine: Engine) -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise ConnectionFailed(str(getattr(exc, "orig", None) or exc)) from exc


def public(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if k != "password_enc"}


def create_connection(data: dict) -> dict:
    password = data.get("password") if data["db_type"] != "sqlite" else None
    rec = {
        "id": uuid.uuid4().hex[:12],
        "name": data["name"],
        "db_type": data["db_type"],
        "host": data.get("host"),
        "port": data.get("port"),
        "database": data["database"],
        "username": data.get("username"),
        "password_enc": _fernet().encrypt(password.encode()).decode() if password else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    engine, ro_engine = _make_engines(rec, password)
    try:
        _check(engine)
        _check(ro_engine)
    except ConnectionFailed:
        engine.dispose()
        ro_engine.dispose()
        raise
    with _lock:
        _engines[rec["id"]] = (engine, ro_engine)
    get_redis().hset(CONNECTIONS_KEY, rec["id"], json.dumps(rec))
    return {**public(rec), "tables": sorted(inspect(engine).get_table_names())}


def get_record(conn_id: str) -> dict:
    raw = get_redis().hget(CONNECTIONS_KEY, conn_id)
    if raw is None:
        raise ConnectionNotFound(conn_id)
    return json.loads(raw)


def list_records() -> List[dict]:
    recs = [json.loads(v) for v in get_redis().hvals(CONNECTIONS_KEY)]
    return sorted(recs, key=lambda r: r["created_at"])


def engines(conn_id: str) -> Tuple[Engine, Engine]:
    with _lock:
        if conn_id in _engines:
            return _engines[conn_id]
    rec = get_record(conn_id)  # after a restart, rebuild from the saved record
    password = _fernet().decrypt(rec["password_enc"].encode()).decode() if rec.get("password_enc") else None
    pair = _make_engines(rec, password)
    with _lock:
        return _engines.setdefault(conn_id, pair)


def delete_connection(conn_id: str) -> None:
    get_redis().hdel(CONNECTIONS_KEY, conn_id)
    with _lock:
        pair = _engines.pop(conn_id, None)
    if pair:
        for eng in pair:
            eng.dispose()


def dispose_all() -> None:
    with _lock:
        pairs = list(_engines.values())
        _engines.clear()
    for pair in pairs:
        for eng in pair:
            eng.dispose()


def describe_schema(conn_id: str) -> dict:
    engine, _ = engines(conn_id)
    insp = inspect(engine)
    out = {}
    for table in sorted(insp.get_table_names()):
        pks = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
        out[table] = [
            {"name": c["name"], "type": str(c["type"]), "primary_key": c["name"] in pks}
            for c in insp.get_columns(table)
        ]
    return out


def table_fingerprint(engine: Engine, table: str) -> str:
    """A cheap value that changes when the table's data changes. Used by the watcher."""
    quoted = engine.dialect.identifier_preparer.quote(table)
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            row = conn.execute(
                text(
                    "SELECT n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_user_tables "
                    "WHERE relname = :t AND schemaname = current_schema()"
                ),
                {"t": table},
            ).first()
            if row:
                return "pg:" + ":".join(str(v) for v in row)
        count = conn.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar()
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        latest = None
        if "updated_at" in columns:
            latest = conn.execute(text(f"SELECT MAX(updated_at) FROM {quoted}")).scalar()
        return f"{count}:{latest}"
