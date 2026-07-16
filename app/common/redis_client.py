import redis.asyncio as redis

CHANNELS_UPDATE_TOPIC = "channels:updates"


def get_redis(redis_url: str) -> redis.Redis:
    return redis.from_url(redis_url, decode_responses=True)
