"""Evaluate contracts offline; --live adds real model routing, embeddings and synthesis."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.provider import DemoProvider, OpenAIProvider
from src.agents.sql_policy import validate_sql
from src.agents.tools import EmptyArgs, Tool, TrendArgs, customer_tools
from src.config import ROOT, Settings
from src.errors import ConflictError, ModelError, PolicyError
from src.observability.telemetry import Metrics
from src.retrieval.notes import DemoEmbedder, NotesIndex, OpenAIEmbedder
from src.services.actions import ActionState, authorize_transition
from src.services.data import load_customers, summarize
from src.services.insights import InsightNarrative, validate_narrative

THRESHOLDS = {
    "tool_selection_accuracy": 0.95,
    "sql_safety_pass_rate": 1.0,
    "rag_hit_at_3": 0.9,
    "structured_output_compliance": 1.0,
    "action_policy_compliance": 1.0,
}


class EvalCustomers:
    """Read-only fixture adapter; never an application persistence substitute."""

    def __init__(self):
        self.customers = load_customers(ROOT / "data/customers.csv")

    def get_all_customers(self):
        return self.customers

    def get_customer_by_id(self, customer_id):
        return next(c for c in self.customers if c.customer_id == customer_id)

    def get_summary(self):
        return summarize(self.customers)

    def get_revenue_by_industry(self):
        return []

    def get_low_nps_customers(self):
        return [c for c in self.customers if c.nps_score < 30]


class NoSqlExecution:
    def execute(self, query):
        raise PolicyError("Routing evaluation never executes model SQL")


def load_dataset(name):
    return json.loads((ROOT / f"evals/datasets/{name}.json").read_text(encoding="utf-8"))


def evaluate(live=False):
    metrics = Metrics()
    if live:
        settings = Settings(model_mode="openai")
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(), timeout=30, max_retries=1
        )
        provider = OpenAIProvider(client, settings.openai_model)
        embedder = OpenAIEmbedder(client, settings.embedding_model)
    else:
        settings = Settings(_env_file=None, app_env="test", model_mode="demo")
        provider, embedder = DemoProvider(), DemoEmbedder()
    notes = NotesIndex(ROOT / "data/customer_notes", embedder, metrics)
    registry = customer_tools(EvalCustomers(), notes, NoSqlExecution(), metrics, settings.today)
    registry.register(
        Tool(
            "get_deteriorating_customers",
            "Authoritative deteriorating customers",
            TrendArgs,
            lambda window_days: [],
        )
    )
    registry.register(
        Tool(
            "get_open_intelligence_events",
            "Persisted open intelligence events",
            EmptyArgs,
            lambda: [],
        )
    )
    cases = {key: [] for key in THRESHOLDS}
    for item in load_dataset("tool_selection"):
        turn = provider.turn([{"role": "user", "content": item["question"]}], registry.schemas())
        actual = [call.name for call in turn.calls]
        valid_args = True
        for call in turn.calls:
            try:
                registry.tools[call.name].args.model_validate_json(call.arguments, strict=True)
            except (KeyError, ValueError):
                valid_args = False
        # First-turn tool selection is reported separately from end-to-end pytest coverage.
        expected = item["tools"]
        correct = set(actual) == set(expected)
        # Live serial tool calling can request risk before notes; require first tool to be right.
        if live and len(expected) > 1:
            correct = actual == expected[:1] or set(actual) == set(expected)
        cases["tool_selection_accuracy"].append(
            {"question": item["question"], "passed": correct and valid_args}
        )
    for item in load_dataset("sql_safety"):
        try:
            validate_sql(item["sql"])
            allowed = True
        except PolicyError:
            allowed = False
        cases["sql_safety_pass_rate"].append(
            {"sql": item["sql"], "passed": allowed == item["allowed"]}
        )
    for item in load_dataset("rag"):
        hits = notes.search(item["query"], item["customer_id"], 3)
        cases["rag_hit_at_3"].append(
            {
                "expected": item["source"],
                "passed": item["source"] in {h.source_id for h in hits}
                and all(h.customer_id == item["customer_id"] for h in hits),
            }
        )
    evidence = notes.search("unresolved data import defects", 3, 3)
    base = {
        "executive_summary": "Review the documented implementation concerns",
        "source_ids": [evidence[0].source_id],
        "recommended_actions": ["Discuss adoption blockers with the account owner"],
        "confidence": 0.7,
    }
    for item in load_dataset("structured_output"):
        try:
            validate_narrative(base | item["patch"], evidence)
            allowed = True
        except ModelError:
            allowed = False
        cases["structured_output_compliance"].append(
            {"patch": item["patch"], "passed": allowed == item["allowed"]}
        )
    if live:
        for cid in (3, 8, 12, 23, 40):
            evidence = notes.search("renewal support concerns", cid, 3)
            try:
                raw = provider.narrative(
                    InsightNarrative, {"evidence": [e.model_dump() for e in evidence]}
                )
                validate_narrative(raw, evidence)
                passed = True
            except ModelError:
                passed = False
            cases["structured_output_compliance"].append(
                {"live_customer_id": cid, "passed": passed}
            )
    for item in load_dataset("action_policy"):
        try:
            authorize_transition(ActionState(item["from"]), ActionState(item["to"]))
            allowed = True
        except ConflictError:
            allowed = False
        cases["action_policy_compliance"].append(
            {"from": item["from"], "to": item["to"], "passed": allowed == item["allowed"]}
        )
    scores = {name: sum(c["passed"] for c in rows) / len(rows) for name, rows in cases.items()}
    digest = hashlib.sha256()
    for path in sorted((ROOT / "evals/datasets").glob("*.json")):
        digest.update(path.read_bytes())
    return {
        "mode": "live" if live else "deterministic",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_sha256": digest.hexdigest(),
        "scores": scores,
        "thresholds": THRESHOLDS,
        "passed": all(scores[k] >= threshold for k, threshold in THRESHOLDS.items()),
        "cases": cases,
        "limitations": "Offline routing and lexical retrieval scores measure demo contracts, not live model quality. Live routing measures first-turn selection; multi-step behavior is tested with mocks in pytest.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Uses paid external API calls; opt-in only"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "evals/results/latest.json")
    args = parser.parse_args()
    try:
        result = evaluate(args.live)
    except Exception as exc:
        result = {
            "passed": False,
            "mode": "live" if args.live else "deterministic",
            "error_type": type(exc).__name__,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
