import redis

from . import config

_client = None


def get_redis() -> redis.Redis:
    """Shared Redis client for the app's own bookkeeping (connections, cache registry, stats)."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _client
