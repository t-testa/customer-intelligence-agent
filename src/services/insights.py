import re

from pydantic import Field, ValidationError

from src.errors import ModelError
from src.models import Risk, RiskLevel, StrictModel
from src.retrieval.notes import Evidence
from src.services.risk import calculate_risk


class InsightNarrative(StrictModel):
    executive_summary: str = Field(min_length=1, max_length=1800)
    source_ids: list[str] = Field(max_length=10)
    recommended_actions: list[str] = Field(min_length=1, max_length=5)
    confidence: float = Field(ge=0, le=1)


class CustomerInsight(StrictModel):
    customer_id: int
    risk_level: RiskLevel
    risk: Risk
    executive_summary: str
    evidence: list[Evidence]
    recommended_actions: list[str]
    confidence: float = Field(ge=0, le=1)
    sources: list[str]
    mode: str


def validate_narrative(raw, evidence: list[Evidence]) -> InsightNarrative:
    try:
        narrative = InsightNarrative.model_validate(raw)
    except ValidationError as exc:
        raise ModelError("Narrative schema invalid") from exc
    known = {e.source_id for e in evidence}
    if not set(narrative.source_ids) <= known or (known and not narrative.source_ids):
        raise ModelError("Narrative cites unsupported evidence")
    for text in [narrative.executive_summary, *narrative.recommended_actions]:
        if (
            not text.strip()
            or len(text) > 1800
            or re.search(
                r"\d|[$€£]|\b(?:high|medium|low)[ -]risk\b|\b(?:dollars?|percent|million|billion)\b",
                text,
                re.I,
            )
        ):
            raise ModelError("Narrative must not restate authoritative quantitative facts")
    return narrative


class InsightService:
    def __init__(self, customers, notes, provider, today):
        self.customers, self.notes, self.provider, self.today = customers, notes, provider, today

    def get(self, customer_id: int) -> CustomerInsight:
        customer = self.customers.get_customer_by_id(customer_id)
        risk = calculate_risk(customer, self.today())
        evidence = self.notes.search(
            "renewal support implementation executive concerns expansion", customer_id, 3
        )
        context = {
            "risk": risk.model_dump(mode="json"),
            "evidence": [e.model_dump() for e in evidence],
        }
        raw = self.provider.narrative(InsightNarrative, context)
        narrative = validate_narrative(raw, evidence)
        sources = set(narrative.source_ids)
        return CustomerInsight(
            customer_id=customer.customer_id,
            risk_level=risk.risk_level,
            risk=risk,
            executive_summary=narrative.executive_summary,
            evidence=[e for e in evidence if e.source_id in sources],
            recommended_actions=narrative.recommended_actions,
            confidence=min(narrative.confidence, 0.85) if sources else 0,
            sources=sorted(sources),
            mode=self.provider.mode,
        )
