import json
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from evals.run_evals import evaluate
from src.api import create_app
from src.config import Settings
from src.errors import ModelError
from src.observability.telemetry import JsonFormatter, event, logger
from src.repositories.customers import CustomerRepository
from src.retrieval.notes import OpenAIEmbedder
from src.services.insights import InsightNarrative


@pytest.mark.integration
def test_whole_customer_workflow(clean_db, as_of):
    app = create_app(Settings(_env_file=None, app_env="test", business_date=as_of))
    app.state.db = clean_db
    app.state.customers = CustomerRepository(clean_db)
    with TestClient(app) as client:
        response = client.post("/agent/ask", json={"question": "Why is customer 3 high risk?"})
        assert response.status_code == 200, response.text
        answer = response.json()
        assert answer["success"] and "8/8" in answer["answer"]
        assert all(source.startswith("C003-") for source in answer["sources"])
        insight = client.get("/customers/3/insight")
        assert insight.status_code == 200, insight.text
        assert insight.json()["risk_level"] == "HIGH" and insight.json()["risk"]["risk_score"] == 8
        assert insight.json()["mode"] == "demo"
        assert client.get("/customers/999/insight").status_code == 404
        assert not client.post("/agent/ask", json={"question": "Show customer 999"}).json()[
            "success"
        ]
        assert client.post("/agent/ask", json={"question": "x" * 2001}).status_code == 422
        assert (
            client.post("/agent/ask", json={"question": "summary", "tool": "execute"}).status_code
            == 422
        )
        action = client.post("/customers/3/actions/followup").json()
        aid = action["action_id"]
        assert client.get(f"/actions/{aid}").json()["payload"] == action["payload"]
        assert client.post(f"/actions/{aid}/approve").status_code == 200
        executed = client.post(f"/actions/{aid}/execute").json()
        assert executed["artifact"] == action["payload"]
        assert client.post(f"/actions/{aid}/execute").status_code == 409
        assert client.get("/intelligence/trends").status_code == 200
        assert client.get("/intelligence/events").json() == []
        assert client.get("/intelligence/trends?window_days=0").status_code == 422
        assert (
            client.post(
                "/agent/ask", json={"question": "Which customers deteriorated?"}
            ).status_code
            == 200
        )
        assert client.post("/agent/ask", json={"question": "Show open events"}).status_code == 200


@pytest.mark.integration
def test_event_api_lifecycle(clean_db, as_of):
    from src.repositories.intelligence import EventRepository
    from src.services.intelligence import dedupe_key
    from src.services.trends import compare_risk

    trend = compare_risk(3, 8, 2, as_of, 7)
    record, _ = EventRepository(clean_db).create(trend, "CRITICAL", dedupe_key(trend))
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.state.db = clean_db
    with TestClient(app) as client:
        assert len(client.get("/intelligence/events?status=OPEN").json()) == 1
        path = f"/intelligence/events/{record.event_id}"
        assert client.post(path + "/acknowledge").json()["status"] == "ACKNOWLEDGED"
        assert client.post(path + "/resolve").json()["status"] == "RESOLVED"
        assert client.post(path + "/resolve").status_code == 409
        assert client.get("/metrics").json()["intelligence_open_events"] == 0


def test_health_and_error_redaction():
    app = create_app(Settings(_env_file=None, app_env="test"))
    app.state.db = SimpleNamespace(healthy=lambda: False)

    @app.get("/test-error")
    def fail():
        raise RuntimeError("secret-password-do-not-log")

    with TestClient(app) as client:
        assert client.get("/health").status_code == 503
        response = client.get("/test-error", headers={"X-Request-ID": "contains invalid spaces"})
        assert response.status_code == 500
        assert "secret-password" not in response.text
        assert response.headers["X-Request-ID"] != "contains invalid spaces"
        assert app.state.metrics.snapshot()["errors_total"] == 1


def test_logs_only_allow_operational_fields():
    import io
    import logging

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        event(
            "test",
            count=1,
            password="sensitive",
            note="full private note",
            authorization="Bearer hidden",
        )
    finally:
        logger.removeHandler(handler)
    output = json.loads(stream.getvalue())
    assert output["count"] == 1 and "sensitive" not in stream.getvalue()
    assert "note" not in output and "authorization" not in output


def test_staging_configuration():
    base = {
        "_env_file": None,
        "app_env": "staging",
        "business_date": None,
        "database_url": "postgresql://host/db?sslmode=verify-full",
        "sql_database_url": "postgresql://host/db?sslmode=verify-full",
        "reader_api_key": "r" * 32,
        "reviewer_api_key": "w" * 32,
    }
    assert Settings(**base).app_env == "staging"
    for update in [
        {"reviewer_api_key": ""},
        {"reviewer_api_key": "r" * 32},
        {"database_url": "postgresql://user:sslmode=verify-full@host/db?sslmode=disable"},
        {"business_date": date(2026, 9, 16)},
        {"model_mode": "openai", "openai_api_key": None},
    ]:
        with pytest.raises(ValidationError):
            Settings(**(base | update))
    assert Settings(_env_file=None, reader_api_key="", reviewer_api_key="").reader_api_key is None


def test_openai_embeddings_mock_and_failure():
    client = SimpleNamespace(
        embeddings=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[1.0, 0.0])]
            )
        )
    )
    assert np.array_equal(OpenAIEmbedder(client, "model").embed(["text"]), [[1.0, 0.0]])
    bad = SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kw: SimpleNamespace(data=[])))
    with pytest.raises(ModelError):
        OpenAIEmbedder(bad, "model").embed(["text"])


def test_openai_structured_adapter():
    from src.agents.provider import OpenAIProvider

    narrative = InsightNarrative(
        executive_summary="Review concerns",
        source_ids=["source"],
        recommended_actions=["Discuss priorities"],
        confidence=0.5,
    )
    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(status="completed", output_parsed=narrative)

    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    assert (
        OpenAIProvider(client, "configured").narrative(InsightNarrative, {"evidence": []})
        == narrative
    )
    assert captured["store"] is False and captured["text_format"] == InsightNarrative
    client.responses.parse = lambda **kw: SimpleNamespace(status="completed", output_parsed=None)
    with pytest.raises(ModelError):
        OpenAIProvider(client, "configured").narrative(InsightNarrative, {})


def test_deterministic_eval_thresholds():
    result = evaluate()
    assert result["passed"] and result["mode"] == "deterministic"
    assert (
        result["scores"]["sql_safety_pass_rate"]
        == result["scores"]["action_policy_compliance"]
        == 1.0
    )
    assert all(len(cases) >= 10 for cases in result["cases"].values())
