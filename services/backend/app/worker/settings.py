from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.runner import run_generation
from app.worker.runtime import shutdown_worker, startup_worker


class WorkerSettings:
    functions = [run_generation]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 1
    job_timeout = 60 * 60
    keep_result = 0
    on_startup = startup_worker
    on_shutdown = shutdown_worker
