from typing import List, Optional

from fastapi import APIRouter, HTTPException

from .. import db
from ..cache_service import get_cache

router = APIRouter(prefix="/api/cache", tags=["cache"])


def _conn_ids(connection_id: Optional[str]) -> List[str]:
    if connection_id:
        try:
            db.get_record(connection_id)
        except db.ConnectionNotFound:
            raise HTTPException(404, "Connection not found")
        return [connection_id]
    return [r["id"] for r in db.list_records()]


@router.get("/entries")
def list_entries(connection_id: Optional[str] = None):
    cache = get_cache()
    entries = []
    for cid in _conn_ids(connection_id):
        entries.extend(cache.entries(cid))
    return {"count": len(entries), "entries": entries}


@router.get("/stats")
def cache_stats(connection_id: Optional[str] = None):
    cache = get_cache()
    total = {"hits": 0, "misses": 0, "invalidations": 0, "entries": 0}
    for cid in _conn_ids(connection_id):
        for key, value in cache.stats(cid).items():
            total[key] += value
    lookups = total["hits"] + total["misses"]
    total["hit_rate"] = round(total["hits"] / lookups, 3) if lookups else 0.0
    return total


@router.delete("")
def clear_cache(connection_id: Optional[str] = None):
    cache = get_cache()
    removed = sum(cache.clear(cid) for cid in _conn_ids(connection_id))
    return {"cache_entries_removed": removed}
