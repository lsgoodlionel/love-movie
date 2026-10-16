from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.runner import run_generation


class WorkerSettings:
    functions = [run_generation]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = 60 * 60
    keep_result = 60 * 60
