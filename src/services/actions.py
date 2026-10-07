import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from src.errors import ConflictError
from src.models import StrictModel
from src.observability.telemetry import event
from src.services.risk import calculate_risk


class ActionState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"


TRANSITIONS = {
    ActionState.PENDING: {ActionState.APPROVED, ActionState.REJECTED},
    ActionState.APPROVED: {ActionState.EXECUTED},
    ActionState.REJECTED: set(),
    ActionState.EXECUTED: set(),
}


def authorize_transition(current: ActionState, target: ActionState):
    if target not in TRANSITIONS[current]:
        raise ConflictError("Invalid action transition")


class DraftPayload(StrictModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=6000)

    @field_validator("subject")
    @classmethod
    def subject_safe(cls, text):
        if "\n" in text or "\r" in text:
            raise ValueError("Subject must be a single line")
        return text


def payload_digest(payload: DraftPayload) -> str:
    canonical = json.dumps(
        payload.model_dump(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class Action(StrictModel):
    action_id: UUID
    customer_id: int
    action_type: str
    status: ActionState
    payload: DraftPayload
    payload_hash: str
    created_by: str
    created_at: datetime
    reviewed_by: str | None
    reviewed_at: datetime | None
    executed_at: datetime | None
    artifact: DraftPayload | None


class ActionService:
    def __init__(self, repository, customers, metrics, today):
        self.repository, self.customers, self.metrics, self.today = (
            repository,
            customers,
            metrics,
            today,
        )

    def propose_followup(self, customer_id: int, actor: str) -> Action:
        customer = self.customers.get_customer_by_id(customer_id)
        risk = calculate_risk(customer, self.today())
        # Internal draft is intentionally neutral; risk metrics are not sent externally.
        body = (
            f"Hello {customer.company} team,\n\n"
            "Could we schedule a conversation to review your priorities, open support needs, "
            "and upcoming success milestones? We would like to agree on a practical follow-up plan.\n\n"
            f"Internal preparation notes (remove before external use): {'; '.join(risk.reasons) or 'Routine relationship check-in'}.\n\n"
            "This is an internal draft. No email has been sent."
        )
        payload = DraftPayload(subject=f"Success planning follow-up: {customer.company}", body=body)
        action = self.repository.create(customer_id, payload, actor)
        event(
            "action_proposed",
            action_id=str(action.action_id),
            customer_id=customer_id,
            state=action.status,
        )
        return action

    def transition(self, action_id: UUID, target: ActionState, actor: str) -> Action:
        action = self.repository.transition(action_id, target, actor)
        if target in {ActionState.APPROVED, ActionState.REJECTED}:
            self.metrics.increment(f"actions_{target.lower()}_total")
        event("action_transition", action_id=str(action_id), state=target)
        return action
