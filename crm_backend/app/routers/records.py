"""Generic CRM CRUD over any table of a saved connection.

Every write invalidates the cached answers that depend on that table, right after the commit.
"""
import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import MetaData, Table, delete, func, inspect, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from .. import db
from ..cache_service import get_cache

log = logging.getLogger("crm.records")
router = APIRouter(prefix="/api/connections/{conn_id}/tables/{table}/records", tags=["records"])


@contextmanager
def _db_errors():
    try:
        yield
    except SQLAlchemyError as exc:
        raise HTTPException(400, str(getattr(exc, "orig", None) or exc))


def _load(conn_id: str, table: str):
    try:
        engine, _ = db.engines(conn_id)
    except db.ConnectionNotFound:
        raise HTTPException(404, "Connection not found")
    with _db_errors():
        names = inspect(engine).get_table_names()
        real = next((n for n in names if n.lower() == table.lower()), None)
        if real is None:
            raise HTTPException(404, f"Table '{table}' not found")
        tbl = Table(real, MetaData(), autoload_with=engine)
    pk_cols = list(tbl.primary_key.columns)
    if len(pk_cols) != 1:
        raise HTTPException(400, "Only tables with a single-column primary key are supported")
    return engine, real, tbl, pk_cols[0]


def _coerce(column, value: str):
    try:
        py_type = column.type.python_type
    except NotImplementedError:
        return value
    try:
        return py_type(value) if py_type in (int, float) else value
    except ValueError:
        raise HTTPException(400, f"Invalid id '{value}'")


def _check_columns(tbl, body: Dict[str, Any]) -> Dict[str, Any]:
    unknown = [k for k in body if k not in tbl.c]
    if unknown:
        raise HTTPException(400, f"Unknown column(s): {', '.join(unknown)}")
    return body


def _invalidate(conn_id: str, table: str) -> Optional[int]:
    try:
        return get_cache().invalidate_table(conn_id, table)
    except Exception:
        log.exception("cache invalidation failed (entries will expire via TTL)")
        return None


@router.get("")
def list_records(conn_id: str, table: str, limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    engine, _, tbl, pk = _load(conn_id, table)
    with _db_errors(), engine.connect() as conn:
        rows = conn.execute(select(tbl).order_by(pk).limit(limit).offset(offset)).mappings().all()
        total = conn.execute(select(func.count()).select_from(tbl)).scalar()
    return {"total": total, "limit": limit, "offset": offset, "items": jsonable_encoder([dict(r) for r in rows])}


@router.get("/{record_id}")
def read_record(conn_id: str, table: str, record_id: str):
    engine, _, tbl, pk = _load(conn_id, table)
    with _db_errors(), engine.connect() as conn:
        row = conn.execute(select(tbl).where(pk == _coerce(pk, record_id))).mappings().first()
    if row is None:
        raise HTTPException(404, "Record not found")
    return jsonable_encoder(dict(row))


@router.post("", status_code=201)
def create_record(conn_id: str, table: str, body: Dict[str, Any] = Body(...)):
    engine, real, tbl, pk = _load(conn_id, table)
    values = _check_columns(tbl, body)
    with _db_errors(), engine.begin() as conn:
        result = conn.execute(insert(tbl).values(**values))
        row = conn.execute(select(tbl).where(pk == result.inserted_primary_key[0])).mappings().first()
    invalidated = _invalidate(conn_id, real)
    return {"record": jsonable_encoder(dict(row)), "cache_entries_invalidated": invalidated}


@router.put("/{record_id}")
def update_record(conn_id: str, table: str, record_id: str, body: Dict[str, Any] = Body(...)):
    engine, real, tbl, pk = _load(conn_id, table)
    values = _check_columns(tbl, body)
    if not values:
        raise HTTPException(400, "Send at least one column to update")
    pk_value = _coerce(pk, record_id)
    with _db_errors(), engine.begin() as conn:
        conn.execute(update(tbl).where(pk == pk_value).values(**values))
        row = conn.execute(select(tbl).where(pk == pk_value)).mappings().first()
    if row is None:
        raise HTTPException(404, "Record not found")
    invalidated = _invalidate(conn_id, real)
    return {"record": jsonable_encoder(dict(row)), "cache_entries_invalidated": invalidated}


@router.delete("/{record_id}")
def delete_record(conn_id: str, table: str, record_id: str):
    engine, real, tbl, pk = _load(conn_id, table)
    with _db_errors(), engine.begin() as conn:
        result = conn.execute(delete(tbl).where(pk == _coerce(pk, record_id)))
        deleted = result.rowcount
    if deleted == 0:
        raise HTTPException(404, "Record not found")
    invalidated = _invalidate(conn_id, real)
    return {"deleted": record_id, "cache_entries_invalidated": invalidated}
