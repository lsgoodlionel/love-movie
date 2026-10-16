from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from app.domain.ai_resources.models import ModelRoute


class AIResourceRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def enabled_model_routes(self) -> list[ModelRoute]:
        with self._sessions() as db:
            return list(db.scalars(select(ModelRoute).where(ModelRoute.enabled.is_(True)).order_by(ModelRoute.priority)))
