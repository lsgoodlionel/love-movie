from typing import Any
from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.ai_resources.models import ModelRoute


class AIResourceRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def enabled_model_routes(self) -> list[ModelRoute]:
        with self._sessions() as db:
            return list(db.scalars(select(ModelRoute).where(ModelRoute.enabled.is_(True)).order_by(ModelRoute.priority)))

    def list_model_routes(self) -> list[ModelRoute]:
        with self._sessions() as db:
            return list(db.scalars(select(ModelRoute).order_by(ModelRoute.priority, ModelRoute.capability)))

    def create_model_route(self, values: dict[str, Any]) -> ModelRoute:
        with self._sessions.begin() as db:
            route = ModelRoute(**values)
            db.add(route)
            db.flush()
            return route

    def update_model_route(self, route_id: UUID, values: dict[str, Any]) -> ModelRoute | None:
        with self._sessions.begin() as db:
            route = db.get(ModelRoute, route_id)
            if route is None:
                return None
            for key, value in values.items():
                setattr(route, key, value)
            return route
