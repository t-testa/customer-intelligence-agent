from uuid import uuid4

from src.errors import NotFoundError
from src.observability.telemetry import event, request_id
from src.services.intelligence import EventStatus, IntelligenceEvent, authorize_event_transition


class EventRepository:
    def __init__(self, db):
        self.db = db

    def create(self, trend, severity: str, key: str):
        with self.db.connect() as conn:
            row = conn.execute(
                """INSERT INTO intelligence_events(event_id,event_type,customer_id,severity,
                previous_risk_score,current_risk_score,risk_delta,window_days,baseline_date,as_of,dedupe_key)
                VALUES (%s,'CUSTOMER_RISK_DETERIORATION',%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (dedupe_key) DO NOTHING RETURNING *""",
                (
                    uuid4(),
                    trend.customer_id,
                    severity,
                    trend.previous_risk_score,
                    trend.current_risk_score,
                    trend.risk_delta,
                    trend.window_days,
                    trend.baseline_date,
                    trend.as_of,
                    key,
                ),
            ).fetchone()
            created = row is not None
            if created:
                conn.execute(
                    """INSERT INTO intelligence_event_audit(event_id,from_state,to_state,actor,request_id)
                    VALUES (%s,NULL,'OPEN','intelligence-scan',%s)""",
                    (row["event_id"], request_id.get()),
                )
            else:
                row = conn.execute(
                    "SELECT * FROM intelligence_events WHERE dedupe_key=%s", (key,)
                ).fetchone()
        return IntelligenceEvent.model_validate(row), created

    def list(self, status: EventStatus | None = None, limit: int = 100, offset: int = 0):
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM intelligence_events WHERE (%s::text IS NULL OR status=%s)
                ORDER BY detected_at DESC, event_id LIMIT %s OFFSET %s""",
                (status, status, limit, offset),
            ).fetchall()
        return [IntelligenceEvent.model_validate(row) for row in rows]

    def open_count(self):
        with self.db.connect() as conn:
            return conn.execute(
                "SELECT count(*) AS count FROM intelligence_events WHERE status='OPEN'"
            ).fetchone()["count"]

    def record_scan(self, created: int, duplicates: int, success: bool):
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO intelligence_scan_runs(created_events,deduplicated_events,success) VALUES (%s,%s,%s)",
                (created, duplicates, success),
            )

    def scan_metrics(self):
        with self.db.connect() as conn:
            row = conn.execute("""SELECT count(*) AS intelligence_scans_total,
                coalesce(sum(created_events),0) AS intelligence_events_created_total,
                coalesce(sum(deduplicated_events),0) AS intelligence_events_deduplicated_total
                FROM intelligence_scan_runs""").fetchone()
        return {**row, "intelligence_open_events": self.open_count()}

    def transition(self, event_id, target: EventStatus, actor: str):
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM intelligence_events WHERE event_id=%s FOR UPDATE", (event_id,)
            ).fetchone()
            if not row:
                raise NotFoundError("Event not found")
            authorize_event_transition(EventStatus(row["status"]), target)
            old_status = row["status"]
            row = conn.execute(
                "UPDATE intelligence_events SET status=%s,updated_at=now() WHERE event_id=%s RETURNING *",
                (target, event_id),
            ).fetchone()
            conn.execute(
                """INSERT INTO intelligence_event_audit(event_id,from_state,to_state,actor,request_id)
                VALUES (%s,%s,%s,%s,%s)""",
                (event_id, old_status, target, actor, request_id.get()),
            )
        event("intelligence_event_transition", event_id=str(event_id), state=target)
        return IntelligenceEvent.model_validate(row)
