import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .cache_service import get_cache
from .redis_client import get_redis
from .routers import ask, cache, connections, records
from .watcher import TableWatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.ensure_ready()  # fails fast with a clear message if SECRET_KEY is missing
    cache_service = get_cache()  # loads the embedding model once at startup
    watcher = None
    if config.WATCHER_ENABLED:
        watcher = TableWatcher(cache_service, config.WATCHER_INTERVAL_SECONDS)
        watcher.start()
    yield
    if watcher:
        watcher.stop()
    db.dispose_all()


app = FastAPI(title="CRM Q&A backend (powered by Glia)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ask.router)
app.include_router(connections.router)
app.include_router(records.router)
app.include_router(cache.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "redis": bool(get_redis().ping())}
