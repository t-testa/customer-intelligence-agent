from types import SimpleNamespace

import pytest

from scripts.init_db import initialize
from src.agents.agent import CustomerAgent
from src.agents.provider import ModelTurn, ToolCall
from src.agents.tools import CustomerArgs, SearchArgs, Tool, ToolRegistry
from src.observability.telemetry import Metrics
from src.services.intelligence import IntelligenceService


def test_model_cannot_change_explicit_customer_scope():
    registry = ToolRegistry(Metrics())
    called = []
    registry.register(
        Tool(
            "get_customer_risk",
            "Risk",
            CustomerArgs,
            lambda customer_id: called.append(customer_id),
        )
    )

    class WrongCustomer:
        mode = "test"

        def turn(self, messages, tools):
            return ModelTurn([ToolCall("get_customer_risk", '{"customer_id":4}', "1")])

    answer = CustomerAgent(WrongCustomer(), registry, Metrics()).ask(
        "What is the risk for customer 3?"
    )
    assert not answer.success and not called


def test_empty_retrieval_abstains_and_injected_tool_is_blocked():
    registry = ToolRegistry(Metrics())
    registry.register(Tool("search_customer_notes", "Notes", SearchArgs, lambda **kwargs: []))

    class EmptyNotes:
        mode = "test"

        def turn(self, messages, tools):
            if len(messages) == 1:
                return ModelTurn(
                    [
                        ToolCall(
                            "search_customer_notes",
                            '{"query":"notes","customer_id":3,"top_k":3}',
                            "1",
                        )
                    ]
                )
            return ModelTurn()

    assert not CustomerAgent(EmptyNotes(), registry, Metrics()).ask("Notes for customer 3").success

    class Injection(EmptyNotes):
        def turn(self, messages, tools):
            if len(messages) > 1:
                return ModelTurn([ToolCall("approve_action", '{"action_id":"stolen"}', "2")])
            return super().turn(messages, tools)

    assert not CustomerAgent(Injection(), registry, Metrics()).ask("Notes for customer 3").success
    assert "approve_action" not in registry.tools


def test_failed_scan_is_recorded():
    recorded = []

    def fail(window):
        raise RuntimeError("input unavailable")

    repository = SimpleNamespace(record_scan=lambda *args: recorded.append(args))
    service = IntelligenceService(SimpleNamespace(deteriorating=fail), repository, Metrics())
    with pytest.raises(RuntimeError):
        service.scan()
    assert recorded == [(0, 0, False)]


@pytest.mark.integration
def test_migration_checksum_rejects_edited_history(clean_db, tmp_path, monkeypatch):
    import scripts.init_db as module
    from src.config import ROOT

    target = tmp_path / "sql"
    target.mkdir()
    for file in (ROOT / "sql").glob("*.sql"):
        (target / file.name).write_text(file.read_text(), encoding="utf-8")
    first = target / "001_schema.sql"
    first.write_text(first.read_text() + "\n-- edited applied migration\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="Applied migration"):
        initialize(clean_db)
