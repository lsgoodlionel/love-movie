from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.domain.generation.models import GenerationTask
from app.domain.generation.schemas import CreateGenerationCommand, GenerationStatus


class GenerationRepository:
    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create_or_get_task(
        self,
        command: CreateGenerationCommand,
        idempotency_key: str,
    ) -> tuple[GenerationTask, bool]:
        db = self._sessions()
        try:
            task = GenerationTask(
                tenant_id=command.tenant_id,
                project_id=command.project_id,
                created_by=command.created_by,
                kind=command.kind.value,
                status=GenerationStatus.DRAFT.value,
                parameters=command.parameters,
                workflow_version=command.workflow_version,
                idempotency_key=idempotency_key,
            )
            db.add(task)
            db.commit()
            return task, True
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(GenerationTask).where(
                    GenerationTask.tenant_id == command.tenant_id,
                    GenerationTask.idempotency_key == idempotency_key,
                )
            )
            if existing is None:
                raise
            return existing, False
        finally:
            db.close()
