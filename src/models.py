from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Customer(StrictModel):
    customer_id: int = Field(gt=0)
    company: str = Field(min_length=1, max_length=120)
    industry: str = Field(min_length=1, max_length=80)
    monthly_revenue: Decimal = Field(ge=0, le=100_000_000, decimal_places=2)
    contract_end: date
    support_tickets: int = Field(ge=0, le=10000)
    nps_score: int = Field(ge=-100, le=100)
    last_contact: date

    @field_validator("company", "industry")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Must not be blank")
        return value.strip()


class Summary(StrictModel):
    customer_count: int
    total_mrr: Decimal
    average_nps: float | None
    average_support_tickets: float | None
    highest_revenue_customer: Customer | None


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Risk(StrictModel):
    customer_id: int
    as_of: date
    risk_score: int = Field(ge=0, le=8)
    risk_level: RiskLevel
    reasons: list[str]


class Health(StrictModel):
    status: str
    database: str
