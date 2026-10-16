from arq import create_pool
from arq.connections import RedisSettings


async def create_queue_pool(redis_url: str):
    return await create_pool(RedisSettings.from_dsn(redis_url))
