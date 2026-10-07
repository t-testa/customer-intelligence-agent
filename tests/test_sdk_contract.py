import json

import httpx

from src.agents.provider import OpenAIProvider
from src.agents.tools import CustomerArgs, Tool, ToolRegistry
from src.observability.telemetry import Metrics
from src.services.insights import InsightNarrative


def response(output):
    return {
        "id": "resp_synthetic",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": "configured-model",
        "output": output,
        "parallel_tool_calls": False,
        "tools": [],
        "tool_choice": "auto",
        "metadata": {},
        "error": None,
        "incomplete_details": None,
    }


def test_sdk_serializes_strict_tools_and_parses_calls(sdk_client_factory):
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=response(
                [
                    {
                        "type": "function_call",
                        "id": "fc_synthetic",
                        "call_id": "call_synthetic",
                        "name": "get_customer_risk",
                        "arguments": '{"customer_id":3}',
                        "status": "completed",
                    }
                ]
            ),
        )

    registry = ToolRegistry(Metrics())
    registry.register(Tool("get_customer_risk", "Risk", CustomerArgs, lambda customer_id: {}))
    provider = OpenAIProvider(sdk_client_factory(handle), "configured-model")
    turn = provider.turn([{"role": "user", "content": "Customer 3 risk"}], registry.schemas())
    assert turn.calls[0].name == "get_customer_risk"
    schema = captured[0]["tools"][0]
    assert schema["strict"] and schema["parameters"]["required"] == ["customer_id"]
    assert schema["parameters"]["additionalProperties"] is False and captured[0]["store"] is False


def test_sdk_parses_structured_insight(sdk_client_factory):
    data = {
        "executive_summary": "Review the support concerns",
        "source_ids": ["C003-support#0"],
        "recommended_actions": ["Discuss adoption needs"],
        "confidence": 0.7,
    }

    def handle(request):
        sent = json.loads(request.content)
        assert sent["text"]["format"]["strict"] is True
        assert sent["text"]["format"]["schema"]["additionalProperties"] is False
        return httpx.Response(
            200,
            json=response(
                [
                    {
                        "type": "message",
                        "id": "msg_synthetic",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": json.dumps(data), "annotations": []}
                        ],
                    }
                ]
            ),
        )

    parsed = OpenAIProvider(sdk_client_factory(handle), "configured-model").narrative(
        InsightNarrative, {"evidence": []}
    )
    assert parsed.confidence == 0.7 and parsed.source_ids == ["C003-support#0"]
