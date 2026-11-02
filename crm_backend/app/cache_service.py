"""Glia-backed semantic cache plus the small registry that links cached answers to tables.

Glia stores one answer per source_id tag. A SQL answer can depend on several tables, so the
source_id used here is the sorted table list ("customers__deals"), and a Redis registry maps
each table to the source_ids that depend on it. When a table changes, every source_id that
depends on it is deleted through Glia's delete_by_tag().

Each database connection gets its own Glia index, so answers never leak across connections.
"""
import json
import logging
import re
import threading
from datetime import datetime, timezone
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple

from glia import CacheInvalidator, GliaManager

from . import config
from .embeddings import LocalVectorizer
from .redis_client import get_redis

log = logging.getLogger("crm.cache")


def _key(conn_id: str, *parts: str) -> str:
    return ":".join(("crm", conn_id) + parts)


def _source_id(tables: Iterable[str]) -> str:
    # Tag-safe: letters, digits and underscores only. A collision only makes invalidation broader.
    return re.sub(r"\W", "_", "__".join(sorted(tables)))


class CacheService:
    def __init__(self):
        self.vectorizer = LocalVectorizer(config.EMBEDDING_MODEL, config.VECTOR_DIMS)
        self.r = get_redis()
        self._glia_by_conn: Dict[str, Tuple[GliaManager, CacheInvalidator]] = {}
        self._lock = threading.Lock()

    def _glia(self, conn_id: str) -> Tuple[GliaManager, CacheInvalidator]:
        with self._lock:
            if conn_id not in self._glia_by_conn:
                manager = GliaManager(
                    vectorizer=self.vectorizer,
                    redis_url=config.REDIS_URL,
                    index_name=f"crm_{conn_id}",
                    distance_threshold=config.DISTANCE_THRESHOLD,
                    vector_dims=config.VECTOR_DIMS,
                    ttl_seconds=config.CACHE_TTL_SECONDS,
                )
                self._glia_by_conn[conn_id] = (manager, CacheInvalidator(manager))
            return self._glia_by_conn[conn_id]

    # ---- lookup / save -------------------------------------------------

    def lookup(self, conn_id: str, question: str) -> Optional[dict]:
        manager, _ = self._glia(conn_id)
        raw = manager.check(question)
        stats_key = _key(conn_id, "stats")
        if raw is None:
            self.r.hincrby(stats_key, "misses", 1)
            return None
        self.r.hincrby(stats_key, "hits", 1)
        try:
            data = json.loads(raw)
            return {"answer": data["answer"], "sql": data.get("sql")}
        except (ValueError, KeyError, TypeError):
            return {"answer": raw, "sql": None}

    def save(self, conn_id: str, question: str, answer: str, sql: str,
             tables: List[str], fingerprints: Dict[str, str]) -> None:
        manager, _ = self._glia(conn_id)
        source_id = _source_id(tables)
        entry = json.dumps({
            "question": question,
            "answer": answer,
            "sql": sql,
            "tables": sorted(tables),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Register dependencies first so an invalidation can never miss a stored entry.
        pipe = self.r.pipeline()
        src_key = _key(conn_id, "src", source_id)
        pipe.rpush(src_key, entry)
        pipe.expire(src_key, config.CACHE_TTL_SECONDS)
        pipe.sadd(_key(conn_id, "sources"), source_id)
        for table in tables:
            pipe.sadd(_key(conn_id, "deps", table), source_id)
            if table in fingerprints:
                # Baseline taken before the query ran; only set if the table has none yet.
                pipe.set(_key(conn_id, "fp", table), fingerprints[table], nx=True)
        pipe.execute()

        manager.store(question, json.dumps({"answer": answer, "sql": sql}), source_id=source_id)

    # ---- invalidation --------------------------------------------------

    def invalidate_table(self, conn_id: str, table: str) -> int:
        """Remove every cached answer that depends on this table. Returns entries deleted."""
        _, invalidator = self._glia(conn_id)
        deleted = 0
        for source_id in self.r.smembers(_key(conn_id, "deps", table)):
            deleted += invalidator.delete_by_tag(source_id)
            self._forget_source(conn_id, source_id)
        self.r.delete(_key(conn_id, "deps", table), _key(conn_id, "fp", table))
        if deleted:
            self.r.hincrby(_key(conn_id, "stats"), "invalidations", deleted)
        return deleted

    def _forget_source(self, conn_id: str, source_id: str) -> None:
        src_key = _key(conn_id, "src", source_id)
        first = self.r.lindex(src_key, 0)
        if first:
            for table in json.loads(first).get("tables", []):
                deps_key = _key(conn_id, "deps", table)
                self.r.srem(deps_key, source_id)
                if self.r.scard(deps_key) == 0:
                    self.r.delete(_key(conn_id, "fp", table))
        self.r.delete(src_key)
        self.r.srem(_key(conn_id, "sources"), source_id)

    def clear(self, conn_id: str) -> int:
        """Delete every cached answer (and the stats) for a connection."""
        _, invalidator = self._glia(conn_id)
        deleted = 0
        for source_id in self.r.smembers(_key(conn_id, "sources")):
            deleted += invalidator.delete_by_tag(source_id)
            self._forget_source(conn_id, source_id)
        self.r.delete(_key(conn_id, "stats"))
        return deleted

    # ---- visibility ----------------------------------------------------

    def entries(self, conn_id: str) -> List[dict]:
        out = []
        for source_id in sorted(self.r.smembers(_key(conn_id, "sources"))):
            items = self.r.lrange(_key(conn_id, "src", source_id), 0, -1)
            if not items:  # registry entry expired along with the cache entry
                self.r.srem(_key(conn_id, "sources"), source_id)
                continue
            for raw in items:
                out.append({**json.loads(raw), "connection_id": conn_id})
        return out

    def stats(self, conn_id: str) -> dict:
        h = self.r.hgetall(_key(conn_id, "stats"))
        return {
            "hits": int(h.get("hits", 0)),
            "misses": int(h.get("misses", 0)),
            "invalidations": int(h.get("invalidations", 0)),
            "entries": len(self.entries(conn_id)),
        }

    # ---- helpers for the watcher --------------------------------------

    def tracked_tables(self) -> List[Tuple[str, str]]:
        out = []
        for key in self.r.scan_iter(match="crm:*:deps:*"):
            _, conn_id, _, table = key.split(":", 3)
            out.append((conn_id, table))
        return out

    def get_fingerprint(self, conn_id: str, table: str) -> Optional[str]:
        return self.r.get(_key(conn_id, "fp", table))

    def set_fingerprint(self, conn_id: str, table: str, value: str) -> None:
        self.r.set(_key(conn_id, "fp", table), value)


@lru_cache(maxsize=None)
def get_cache() -> CacheService:
    return CacheService()
