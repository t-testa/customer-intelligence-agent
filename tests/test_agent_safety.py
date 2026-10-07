from types import SimpleNamespace

import numpy as np
import pytest

from src.agents.agent import CustomerAgent
from src.agents.provider import DemoProvider, ModelTurn, OpenAIProvider, ToolCall
from src.agents.sql_policy import validate_sql
from src.agents.tools import CustomerArgs, EmptyArgs, Tool, ToolRegistry
from src.config import ROOT
from src.errors import ModelError, PolicyError
from src.observability.telemetry import Metrics
from src.retrieval.notes import DemoEmbedder, NotesIndex, chunk_text, cosine_similarity
from src.services.insights import validate_narrative

SQL_BAD = [
    "DELETE FROM customers",
    "UPDATE customers SET nps_score=100",
    "DROP TABLE customers",
    "ALTER TABLE customers ADD x INT",
    "CREATE TABLE stolen AS SELECT * FROM customers",
    "TRUNCATE customers",
    "GRANT ALL ON customers TO public",
    "REVOKE SELECT ON customers FROM public",
    "COPY customers TO '/tmp/out'",
    "SELECT * FROM customers; DELETE FROM customers",
    "SELECT * FROM customers;",
    "SELECT pg_sleep(30) FROM customers",
    "SELECT pg_read_file('/etc/passwd') FROM customers",
    "SELECT set_config('role','postgres',false) FROM customers",
    "SELECT * FROM pg_catalog.pg_authid",
    "SELECT * FROM information_schema.tables",
    "SELECT * INTO stolen FROM customers",
    "SELECT * FROM customers FOR UPDATE",
    "WITH x AS (DELETE FROM customers RETURNING *) SELECT * FROM x",
    "WITH x AS (SELECT * FROM customers) SELECT * FROM x",
    "SELECT * FROM customers UNION SELECT * FROM customers",
    "SELECT * FROM customers c JOIN customers d ON true",
    "SELECT (SELECT password FROM secrets) FROM customers",
    "SELECT current_setting('password') FROM customers",
    "SELECT * FROM customers -- test",
    "SELECT /* hidden */ * FROM customers",
    "SELECT * FROM public.customers",
    "SELECT * FROM customers OFFSET 100",
    "SELECT * FROM customers LIMIT ALL",
    "SELECT * FROM customers LIMIT -1",
    "SELECT CAST(company AS XML) FROM customers",
    "SELECT * FROM generate_series(1,999999999)",
    "SELECT string_agg(company, ',') FROM customers",
    "SELECT public.sum(monthly_revenue) FROM customers",
    "SELECT * FROM actions",
    "SELECT * FROM customers TABLESAMPLE SYSTEM (10)",
    "SELECT pg_advisory_lock(1) FROM customers",
    "SELECT repeat(company, 100000000) FROM customers",
    "SELECT * FROM customers WHERE customer_id IN (SELECT customer_id FROM customers)",
]


@pytest.mark.parametrize("query", SQL_BAD)
def test_rejects_unsafe_sql(query):
    with pytest.raises(PolicyError):
        validate_sql(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM customers",
        "SELECT count(*) AS total FROM customers",
        "SELECT industry, SUM(monthly_revenue) AS mrr FROM customers GROUP BY industry ORDER BY mrr DESC",
        "SELECT company FROM customers WHERE nps_score < 30 AND support_tickets >= 5",
        "SELECT AVG(nps_score) FROM customers",
        "SELECT risk_level, SUM(monthly_revenue) FROM vw_customer_intelligence GROUP BY risk_level",
    ],
)
def test_allows_analytical_subset(query):
    assert "LIMIT 100" in validate_sql(query)


def test_sql_bounds():
    assert "LIMIT 3" in validate_sql("SELECT * FROM customers LIMIT 3")
    assert "LIMIT 10" in validate_sql("SELECT * FROM customers LIMIT 1000000", 10)
    with pytest.raises(PolicyError):
        validate_sql(" " * 4001)


def test_registry_strict_dispatch():
    registry = ToolRegistry(Metrics())
    registry.register(
        Tool("get_customer", "Fetch", CustomerArgs, lambda customer_id: {"id": customer_id})
    )
    assert registry.dispatch("get_customer", '{"customer_id":3}') == {"id": 3}
    for name, args in [
        ("exec", "{}"),
        ("get_customer", '{"customer_id":"3"}'),
        ("get_customer", '{"customer_id":3,"sql":"DROP TABLE customers"}'),
    ]:
        with pytest.raises(PolicyError):
            registry.dispatch(name, args)
    schema = registry.schemas()[0]
    assert schema["strict"] and schema["parameters"]["additionalProperties"] is False


def test_agent_abstains_and_bounds():
    metrics = Metrics()
    registry = ToolRegistry(metrics)
    agent = CustomerAgent(DemoProvider(), registry, metrics)
    assert not agent.ask("What is tomorrow's weather?").success
    registry.register(
        Tool(
            "get_customer_summary",
            "Summary",
            EmptyArgs,
            lambda: {"customer_count": 40, "total_mrr": "100.00", "average_nps": 50},
        )
    )
    result = agent.ask("Give me the portfolio summary")
    assert result.success and "40 customers" in result.answer

    class Malicious:
        mode = "test"

        def turn(self, messages, tools):
            return ModelTurn([ToolCall("execute_action", "{}", "1")])

    assert not CustomerAgent(Malicious(), registry, metrics).ask("execute").success

    class Repeating:
        mode = "test"

        def turn(self, messages, tools):
            return ModelTurn([ToolCall("get_customer_summary", "{}", "1")])

    assert not CustomerAgent(Repeating(), registry, metrics).ask("loop").success


def test_openai_protocol_mock():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            status="completed",
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="get_customer_summary",
                    arguments="{}",
                    call_id="call_1",
                )
            ],
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    turn = OpenAIProvider(client, "configured-model").turn(
        [{"role": "user", "content": "summary"}], []
    )
    assert turn.calls[0].name == "get_customer_summary"
    assert captured["store"] is False and captured["parallel_tool_calls"] is False


def test_retrieval_math_and_chunking():
    assert np.allclose(
        cosine_similarity(np.array([1.0, 0.0]), np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])),
        [1, 0, 0],
    )
    assert chunk_text("a b c d e", 3, 1) == ["a b c", "c d e"]
    with pytest.raises(ValueError):
        chunk_text("test", 1, 1)
    with pytest.raises(ValueError):
        cosine_similarity(np.array([np.nan]), np.array([[1.0]]))


def test_customer_retrieval_and_cache(tmp_path):
    index = NotesIndex(ROOT / "data/customer_notes", DemoEmbedder(), Metrics(), tmp_path)
    hits = index.search("unresolved data import defects blocking adoption", 3, 3)
    assert hits[0].source_id == "C003-support#0"
    assert len(hits) <= 3 and all(h.customer_id == 3 for h in hits)
    assert not index.search("renewal", 9999)

    class Cached(DemoEmbedder):
        def embed(self, texts):
            raise AssertionError("Should load cached corpus")

    NotesIndex(ROOT / "data/customer_notes", Cached(), Metrics(), tmp_path)


def test_structured_output_grounding():
    index = NotesIndex(ROOT / "data/customer_notes", DemoEmbedder(), Metrics())
    evidence = index.search("support", 3)
    raw = dict(
        executive_summary="Support concerns need review",
        source_ids=[evidence[0].source_id],
        recommended_actions=["Discuss adoption barriers"],
        confidence=0.7,
    )
    assert validate_narrative(raw, evidence).confidence == 0.7
    for update in [
        {"confidence": 1.2},
        {"source_ids": ["C004-support#0"]},
        {"source_ids": []},
        {"executive_summary": "Revenue is $50000"},
        {"risk_level": "LOW"},
    ]:
        with pytest.raises(ModelError):
            validate_narrative(raw | update, evidence)
