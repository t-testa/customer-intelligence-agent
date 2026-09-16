import json
from collections.abc import Callable
from dataclasses import dataclass

from fastapi.encoders import jsonable_encoder
from pydantic import Field, ValidationError

from src.errors import PolicyError
from src.models import StrictModel
from src.observability.telemetry import event
from src.services.risk import calculate_risk


class EmptyArgs(StrictModel):
    pass


class CustomerArgs(StrictModel):
    customer_id: int = Field(gt=0)


class SearchArgs(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    customer_id: int | None
    top_k: int = Field(ge=1, le=10)


class SqlArgs(StrictModel):
    query: str = Field(min_length=1, max_length=4000)


class TrendArgs(StrictModel):
    window_days: int = Field(ge=1, le=90)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[StrictModel]
    execute: Callable


class ToolRegistry:
    def __init__(self, metrics):
        self.tools: dict[str, Tool] = {}
        self.metrics = metrics

    def register(self, tool: Tool):
        if tool.name in self.tools:
            raise ValueError("Duplicate tool")
        self.tools[tool.name] = tool

    def schemas(self):
        return [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.args.model_json_schema(),
                "strict": True,
            }
            for t in self.tools.values()
        ]

    def dispatch(self, name: str, arguments: str):
        tool = self.tools.get(name)
        if tool is None or len(arguments) > 6000:
            raise PolicyError("Unknown tool or excessive arguments")
        try:
            args = tool.args.model_validate_json(arguments, strict=True)
        except ValidationError as exc:
            raise PolicyError("Invalid tool arguments") from exc
        self.metrics.increment("tool_calls_total")
        try:
            result = jsonable_encoder(tool.execute(**args.model_dump()))
            if len(json.dumps(result).encode()) > 128_000:
                raise PolicyError("Tool output budget exceeded")
            event("tool_call", tool=name, success=True)
            return result
        except Exception:
            event("tool_call", tool=name, success=False)
            raise


def customer_tools(repo, notes, sql_executor, metrics, today):
    registry = ToolRegistry(metrics)

    def high_risk():
        return [
            r
            for c in repo.get_all_customers()
            if (r := calculate_risk(c, today())).risk_level == "HIGH"
        ]

    for tool in [
        Tool(
            "get_customer_risk",
            "Authoritative risk score and reasons for one customer",
            CustomerArgs,
            lambda customer_id: calculate_risk(repo.get_customer_by_id(customer_id), today()),
        ),
        Tool(
            "get_high_risk_customers",
            "List current high risk customer scores",
            EmptyArgs,
            high_risk,
        ),
        Tool(
            "get_customer_summary",
            "Customer count, total MRR, average NPS and top revenue customer",
            EmptyArgs,
            repo.get_summary,
        ),
        Tool(
            "get_revenue_by_industry",
            "Total MRR grouped by industry",
            EmptyArgs,
            repo.get_revenue_by_industry,
        ),
        Tool(
            "get_low_nps_customers",
            "Customers with NPS below thirty",
            EmptyArgs,
            repo.get_low_nps_customers,
        ),
        Tool(
            "get_customer_by_id",
            "Authoritative CRM record by customer ID",
            CustomerArgs,
            repo.get_customer_by_id,
        ),
        Tool(
            "search_customer_notes",
            "Retrieve evidence from untrusted notes; filter to the requested customer",
            SearchArgs,
            notes.search,
        ),
        Tool(
            "analytical_sql",
            "Fallback analytics only when another tool cannot answer. Single SELECT on customers or vw_customer_intelligence, vw_customer_history, vw_portfolio_trend. No joins, subqueries, CTEs, comments, semicolons or qualified names. customers columns: customer_id, company, industry, monthly_revenue, contract_end, support_tickets, nps_score, last_contact. Never calculate risk or risk delta here.",
            SqlArgs,
            sql_executor.execute,
        ),
    ]:
        registry.register(tool)
    return registry
