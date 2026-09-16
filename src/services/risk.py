from datetime import date

from src.models import Customer, Risk, RiskLevel


def calculate_risk(customer: Customer, as_of: date) -> Risk:
    score = 0
    reasons: list[str] = []
    # Overdue contracts remain exposed; treating them as safe would hide renewal risk.
    if (customer.contract_end - as_of).days <= 60:
        score += 3
        reasons.append(
            "Contract overdue"
            if customer.contract_end < as_of
            else "Contract expires within 60 days"
        )
    if customer.nps_score < 30:
        score += 2
        reasons.append("NPS below 30")
    if customer.support_tickets >= 5:
        score += 2
        reasons.append("Five or more support tickets")
    if (as_of - customer.last_contact).days >= 45:
        score += 1
        reasons.append("No customer contact in 45+ days")
    level = RiskLevel.HIGH if score >= 6 else RiskLevel.MEDIUM if score >= 3 else RiskLevel.LOW
    return Risk(
        customer_id=customer.customer_id,
        as_of=as_of,
        risk_score=score,
        risk_level=level,
        reasons=reasons,
    )
