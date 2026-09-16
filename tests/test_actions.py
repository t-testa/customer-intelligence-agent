from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.api import create_app
from src.config import Settings
from src.errors import ConflictError
from src.observability.telemetry import Metrics
from src.repositories.actions import ActionRepository
from src.repositories.customers import CustomerRepository
from src.services.actions import ActionService, ActionState, authorize_transition


@pytest.mark.parametrize("current", list(ActionState))
@pytest.mark.parametrize("target", list(ActionState))
def test_complete_action_transition_matrix(current, target):
    allowed = {("PENDING", "APPROVED"), ("PENDING", "REJECTED"), ("APPROVED", "EXECUTED")}
    if (current, target) in allowed:
        authorize_transition(current, target)
    else:
        with pytest.raises(ConflictError):
            authorize_transition(current, target)


@pytest.mark.integration
def test_payload_audit_and_exactly_once(clean_db, as_of):
    repo = ActionRepository(clean_db)
    service = ActionService(repo, CustomerRepository(clean_db), Metrics(), lambda: as_of)
    action = service.propose_followup(3, "analyst")
    with pytest.raises(ConflictError):
        repo.transition(action.action_id, ActionState.EXECUTED, "human")
    with pytest.raises(psycopg.Error):
        with clean_db.connect() as conn:
            conn.execute(
                "UPDATE actions SET payload='{}'::jsonb WHERE action_id=%s", (action.action_id,)
            )
    approved = repo.transition(action.action_id, ActionState.APPROVED, "human")

    def attempt():
        try:
            return repo.transition(action.action_id, ActionState.EXECUTED, "human").status
        except ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["EXECUTED", "conflict"]
    result = repo.get(action.action_id)
    assert result.artifact == approved.payload == action.payload
    assert len(repo.audit(action.action_id)) == 3
    assert [r["to_state"] for r in repo.audit(action.action_id)] == [
        "PENDING",
        "APPROVED",
        "EXECUTED",
    ]


@pytest.mark.integration
def test_action_api_authorization(clean_db, as_of):
    settings = Settings(
        _env_file=None,
        app_env="test",
        business_date=as_of,
        reader_api_key="reader-test-only",
        reviewer_api_key="reviewer-test-only",
    )
    app = create_app(settings)
    app.state.db = clean_db
    app.state.customers = CustomerRepository(clean_db)
    with TestClient(app) as client:
        assert client.get("/customers/summary").status_code == 401
        reader = {"Authorization": "Bearer reader-test-only"}
        reviewer = {"Authorization": "Bearer reviewer-test-only"}
        proposal = client.post("/customers/3/actions/followup", headers=reader)
        assert proposal.status_code == 201
        aid = proposal.json()["action_id"]
        assert client.post(f"/actions/{aid}/approve", headers=reader).status_code == 403
        assert client.post(f"/actions/{aid}/execute", headers=reviewer).status_code == 409
        assert client.post(f"/actions/{aid}/reject", headers=reviewer).status_code == 200
        assert client.post(f"/actions/{aid}/execute", headers=reviewer).status_code == 409
        assert client.get(f"/actions/{aid}/audit", headers=reader).status_code == 200
        assert client.get("/metrics", headers=reader).json()["actions_rejected_total"] == 1
