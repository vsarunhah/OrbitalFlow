"""Deterministic stage reducer.

Maps (current_stage, event_type, confidence) -> new_stage | None.

Rules (from SPEC.md):
  - APPLICATION_RECEIVED     => APPLIED
  - INTERVIEW_*              => INTERVIEW
  - TAKEHOME_REQUEST         => TAKEHOME
  - OFFER                    => OFFER
  - REJECTION                => REJECTED
  - Never auto-change out of REJECTED / WITHDRAWN
  - Never auto-downgrade (ordinal must increase, except terminal transitions)
  - Only auto-change if confidence >= CONFIDENCE_THRESHOLD (0.80)
"""

from __future__ import annotations

from app.schemas.extraction import EventType
from app.schemas.job import (
    CONFIDENCE_THRESHOLD,
    STAGE_ORDINAL,
    TERMINAL_STAGES,
    JobStage,
)

EVENT_TO_STAGE: dict[str, JobStage] = {
    EventType.APPLICATION_RECEIVED.value: JobStage.APPLIED,
    EventType.INTERVIEW_REQUEST.value: JobStage.INTERVIEW,
    EventType.INTERVIEW_SCHEDULED.value: JobStage.INTERVIEW,
    EventType.INTERVIEW_RESCHEDULE.value: JobStage.INTERVIEW,
    EventType.TAKEHOME_REQUEST.value: JobStage.TAKEHOME,
    EventType.OFFER.value: JobStage.OFFER,
    EventType.REJECTION.value: JobStage.REJECTED,
}


def compute_new_stage(
    current_stage: JobStage,
    event_type: str,
    confidence: float,
) -> JobStage | None:
    """Return the new stage if a transition should happen, else None.

    This function is pure / deterministic — no DB, no LLM.
    """
    if current_stage in TERMINAL_STAGES:
        return None

    proposed = EVENT_TO_STAGE.get(event_type)
    if proposed is None:
        return None

    if confidence < CONFIDENCE_THRESHOLD:
        return None

    if proposed in TERMINAL_STAGES:
        return proposed

    current_ord = STAGE_ORDINAL.get(current_stage, -1)
    proposed_ord = STAGE_ORDINAL.get(proposed, -1)

    if proposed_ord <= current_ord:
        return None

    return proposed
