import json
from time import perf_counter

from pydantic import Field

from src.errors import ModelError, NotFoundError, PolicyError
from src.models import StrictModel
from src.observability.telemetry import event


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=2000)


class ToolResult(StrictModel):
    tool: str
    data: object


class AgentAnswer(StrictModel):
    answer: str
    tools_used: list[str]
    success: bool
    mode: str
    facts: list[ToolResult]
    sources: list[str]


def render_results(results: list[ToolResult]) -> str:
    parts = []
    for result in results:
        data = result.data
        if result.tool == "get_customer_risk":
            parts.append(
                f"Customer {data['customer_id']}: {data['risk_level']} risk ({data['risk_score']}/8). "
                + "; ".join(data["reasons"])
            )
        elif result.tool == "get_customer_summary":
            parts.append(
                f"{data['customer_count']} customers; total MRR CAD {data['total_mrr']}; average NPS {data['average_nps']}."
            )
        elif result.tool == "search_customer_notes":
            parts.extend(f"[{row['source_id']}] {row['text']}" for row in data)
        else:
            parts.append(result.tool + ": " + json.dumps(data, ensure_ascii=False))
    return "\n".join(parts)


class CustomerAgent:
    def __init__(self, provider, registry, metrics, max_calls=6):
        self.provider = provider
        self.registry = registry
        self.metrics = metrics
        self.max_calls = max_calls

    def ask(self, question: str) -> AgentAnswer:
        self.metrics.increment("agent_calls_total")
        start = perf_counter()
        messages = [{"role": "user", "content": question}]
        results: list[ToolResult] = []
        seen = set()
        try:
            for _ in range(self.max_calls + 1):
                turn = self.provider.turn(messages, self.registry.schemas())
                messages.extend(turn.output)
                if not turn.calls:
                    break
                if len(results) + len(turn.calls) > self.max_calls:
                    raise PolicyError("Tool budget exceeded")
                for call in turn.calls:
                    signature = (call.name, call.arguments)
                    if signature in seen:
                        raise PolicyError("Repeated tool call")
                    seen.add(signature)
                    data = self.registry.dispatch(call.name, call.arguments)
                    results.append(ToolResult(tool=call.name, data=data))
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(data),
                        }
                    )
            sources = [
                e["source_id"] for r in results if r.tool == "search_customer_notes" for e in r.data
            ]
            # Free-form model prose is deliberately never authoritative. Render typed tool facts.
            return AgentAnswer(
                answer=render_results(results)
                if results
                else "I cannot answer that from the approved customer tools.",
                tools_used=[r.tool for r in results],
                success=bool(results),
                mode=self.provider.mode,
                facts=results,
                sources=list(dict.fromkeys(sources)),
            )
        except (PolicyError, NotFoundError):
            return AgentAnswer(
                answer="I could not safely answer that question from the available customer evidence.",
                tools_used=[r.tool for r in results],
                success=False,
                mode=self.provider.mode,
                facts=[],
                sources=[],
            )
        except ModelError:
            self.metrics.increment("errors_total")
            raise
        finally:
            elapsed = (perf_counter() - start) * 1000
            self.metrics.increment("agent_latency_ms_sum", elapsed)
            event(
                "agent_call",
                mode=self.provider.mode,
                latency_ms=round(elapsed, 2),
                count=len(results),
            )
