from redis.asyncio import Redis

from config import get_config

_redis = None
def get_redis() -> Redis:
    global _redis
    config = get_config()

    if _redis is None:
        _redis = Redis(host=config.redis.host, port=config.redis.port, decode_responses=True)
    
    return _redis