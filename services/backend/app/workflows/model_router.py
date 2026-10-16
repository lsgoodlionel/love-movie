from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    model: str
    capability: str
    quality: str


class ModelRouter:
    def __init__(self, routes: dict[tuple[str, ...], str]) -> None:
        self._routes = routes

    @classmethod
    def defaults(cls) -> "ModelRouter":
        return cls(
            {
                ("cleanup", "interactive"): "qwen3.5:4b",
                ("json_repair", "interactive"): "qwen3.5:4b",
                ("story_planning", "interactive"): "qwen3.5:latest",
                ("dialogue_enhancement", "interactive"): "gemma4:12b",
                ("longform_planning", "high_quality_async"): "qwen3.8:27b",
                ("final_review", "manual"): "gemma4:31b",
            }
        )

    def select(self, capability: str, quality: str, tenant_id: str | None = None) -> ModelSelection:
        if capability in {"longform_planning", "final_review"} and quality == "interactive":
            raise ValueError("大模型不能用于同步交互")
        try:
            model = (
                self._routes.get((tenant_id, capability, quality)) if tenant_id else None
            ) or self._routes[(capability, quality)]
        except KeyError as exc:
            raise ValueError("没有可用的模型路由") from exc
        return ModelSelection(model=model, capability=capability, quality=quality)
