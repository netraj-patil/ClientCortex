import logging
import time

from fastapi import APIRouter, HTTPException

from .. import db, pipeline
from ..cache_service import get_cache
from ..schemas import AskRequest, AskResponse

log = logging.getLogger("crm.ask")
router = APIRouter(prefix="/api", tags=["ask"])


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    started = time.perf_counter()
    question = req.question.strip()
    try:
        db.get_record(req.connection_id)
    except db.ConnectionNotFound:
        raise HTTPException(404, "Connection not found")

    cache = get_cache()

    # Fast path: semantic cache check
    try:
        hit = cache.lookup(req.connection_id, question)
    except Exception:
        log.exception("cache lookup failed, falling back to the database")
        hit = None
    if hit:
        return AskResponse(answer=hit["answer"], source="cache", sql=hit["sql"], latency_ms=_ms(started))

    # Miss path: generate SQL, run it, explain the result
    try:
        result = pipeline.answer_question(req.connection_id, question)
    except pipeline.PipelineError as exc:
        raise HTTPException(422, str(exc))
    except Exception:
        log.exception("ask failed")
        raise HTTPException(502, "The LLM or database request failed. Check the server logs.")

    try:
        cache.save(req.connection_id, question, result.answer, result.sql, result.tables, result.fingerprints)
    except Exception:
        log.exception("could not save to cache (answer is still returned)")

    return AskResponse(answer=result.answer, source="database", sql=result.sql, latency_ms=_ms(started))
