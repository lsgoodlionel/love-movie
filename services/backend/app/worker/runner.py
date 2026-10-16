from typing import Any


async def run_generation(ctx: dict[str, Any], task_id: str) -> None:
    runner = ctx.get("generation_runner")
    if runner is None:
        raise RuntimeError("generation_runner 未配置")
    await runner.run(task_id)
