import pytest

from app.domain.generation.schemas import GenerationStatus
from app.domain.generation.state_machine import InvalidTransition, transition


def test_invalid_transition_raises() -> None:
    with pytest.raises(InvalidTransition):
        transition(GenerationStatus.DRAFT, GenerationStatus.COMPLETED)


def test_remote_submission_can_advance_to_running() -> None:
    assert transition(GenerationStatus.REMOTE_SUBMITTED, GenerationStatus.RUNNING) is GenerationStatus.RUNNING
