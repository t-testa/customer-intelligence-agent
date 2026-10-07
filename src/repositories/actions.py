from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from src.errors import ConflictError, NotFoundError
from src.observability.telemetry import request_id
from src.services.actions import (
    Action,
    ActionState,
    DraftPayload,
    authorize_transition,
    payload_digest,
)


class ActionRepository:
    def __init__(self, db):
        self.db = db

    def create(self, customer_id: int, payload: DraftPayload, actor: str) -> Action:
        digest = payload_digest(payload)
        with self.db.connect() as conn:
            row = conn.execute(
                """INSERT INTO actions(action_id, customer_id, action_type, payload, payload_hash, created_by)
                VALUES (%s,%s,'DRAFT_CUSTOMER_FOLLOWUP',%s,%s,%s) RETURNING *""",
                (uuid4(), customer_id, Jsonb(payload.model_dump()), digest, actor),
            ).fetchone()
            conn.execute(
                """INSERT INTO action_audit(action_id,from_state,to_state,actor,payload_hash,request_id)
                VALUES (%s,NULL,'PENDING',%s,%s,%s)""",
                (row["action_id"], actor, digest, request_id.get()),
            )
        return Action.model_validate(row)

    def get(self, action_id: UUID) -> Action:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM actions WHERE action_id=%s", (action_id,)).fetchone()
        if not row:
            raise NotFoundError("Action not found")
        return Action.model_validate(row)

    def audit(self, action_id: UUID):
        self.get(action_id)
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT * FROM action_audit WHERE action_id=%s ORDER BY audit_id", (action_id,)
            ).fetchall()

    def transition(self, action_id: UUID, target: ActionState, actor: str) -> Action:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM actions WHERE action_id=%s FOR UPDATE", (action_id,)
            ).fetchone()
            if not row:
                raise NotFoundError("Action not found")
            current = Action.model_validate(row)
            authorize_transition(current.status, target)
            if payload_digest(current.payload) != current.payload_hash:
                raise ConflictError("Payload digest mismatch")
            if target == ActionState.EXECUTED:
                row = conn.execute(
                    """UPDATE actions SET status='EXECUTED', executed_at=now(), artifact=payload
                    WHERE action_id=%s RETURNING *""",
                    (action_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    """UPDATE actions SET status=%s, reviewed_by=%s, reviewed_at=now()
                    WHERE action_id=%s RETURNING *""",
                    (target.value, actor, action_id),
                ).fetchone()
            conn.execute(
                """INSERT INTO action_audit(action_id,from_state,to_state,actor,payload_hash,request_id)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    action_id,
                    current.status.value,
                    target.value,
                    actor,
                    current.payload_hash,
                    request_id.get(),
                ),
            )
        return Action.model_validate(row)
