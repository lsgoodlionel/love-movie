from app.domain.generation.schemas import GenerationStatus


class InvalidTransition(ValueError):
    pass


_ALLOWED: dict[GenerationStatus, set[GenerationStatus]] = {
    GenerationStatus.DRAFT: {GenerationStatus.VALIDATING, GenerationStatus.CANCELLED},
    GenerationStatus.VALIDATING: {GenerationStatus.QUEUED, GenerationStatus.FAILED, GenerationStatus.CANCELLED},
    GenerationStatus.QUEUED: {GenerationStatus.PLANNING, GenerationStatus.REMOTE_SUBMITTED, GenerationStatus.CANCELLED},
    GenerationStatus.PLANNING: {GenerationStatus.REMOTE_SUBMITTED, GenerationStatus.FAILED, GenerationStatus.NEEDS_ATTENTION},
    GenerationStatus.REMOTE_SUBMITTED: {
        GenerationStatus.RUNNING,
        GenerationStatus.DOWNLOADING,
        GenerationStatus.CANCELLING,
        GenerationStatus.FAILED,
        GenerationStatus.NEEDS_ATTENTION,
    },
    GenerationStatus.RUNNING: {
        GenerationStatus.DOWNLOADING,
        GenerationStatus.CANCELLING,
        GenerationStatus.FAILED,
        GenerationStatus.NEEDS_ATTENTION,
    },
    GenerationStatus.DOWNLOADING: {GenerationStatus.QUALITY_CHECK, GenerationStatus.FAILED, GenerationStatus.NEEDS_ATTENTION},
    GenerationStatus.QUALITY_CHECK: {GenerationStatus.PERSISTED, GenerationStatus.FAILED, GenerationStatus.NEEDS_ATTENTION},
    GenerationStatus.PERSISTED: {GenerationStatus.COMPLETED, GenerationStatus.FAILED},
    GenerationStatus.CANCELLING: {GenerationStatus.CANCELLED, GenerationStatus.COMPLETED, GenerationStatus.NEEDS_ATTENTION},
    GenerationStatus.NEEDS_ATTENTION: {GenerationStatus.QUEUED, GenerationStatus.CANCELLED, GenerationStatus.FAILED},
    GenerationStatus.COMPLETED: set(),
    GenerationStatus.CANCELLED: set(),
    GenerationStatus.FAILED: set(),
}


def transition(current: GenerationStatus, target: GenerationStatus) -> GenerationStatus:
    if target not in _ALLOWED[current]:
        raise InvalidTransition(f"不能从 {current.value} 变更为 {target.value}")
    return target
