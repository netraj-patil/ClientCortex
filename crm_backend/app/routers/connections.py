from typing import List

from fastapi import APIRouter, HTTPException

from .. import db
from ..cache_service import get_cache
from ..schemas import ConnectionCreate, ConnectionOut

router = APIRouter(prefix="/api/connections", tags=["connections"])


def _require(conn_id: str) -> dict:
    try:
        return db.get_record(conn_id)
    except db.ConnectionNotFound:
        raise HTTPException(404, "Connection not found")


@router.post("", response_model=ConnectionOut, status_code=201)
def add_connection(body: ConnectionCreate):
    try:
        return db.create_connection(body.model_dump())
    except db.ConnectionFailed as exc:
        raise HTTPException(400, f"Could not connect: {exc}")


@router.get("", response_model=List[ConnectionOut])
def list_connections():
    return [db.public(r) for r in db.list_records()]


@router.get("/{conn_id}/schema")
def get_schema(conn_id: str):
    _require(conn_id)
    try:
        return db.describe_schema(conn_id)
    except Exception as exc:
        raise HTTPException(400, f"Could not read the schema: {getattr(exc, 'orig', None) or exc}")


@router.delete("/{conn_id}")
def remove_connection(conn_id: str):
    _require(conn_id)
    removed = get_cache().clear(conn_id)
    db.delete_connection(conn_id)
    return {"deleted": conn_id, "cache_entries_removed": removed}
