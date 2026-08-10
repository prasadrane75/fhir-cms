from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PaymentIntegrityRequest(BaseModel):
    """Capability 10 — payment integrity anomaly detection request."""

    member_id: str | None = None
    payer_id: str | None = None
    lookback_days: int = Field(default=90, ge=1, le=365)


class DuplicatePaymentAnomaly(BaseModel):
    anomaly_type: Literal["duplicate_claim_payment", "duplicate_member_payment"]
    member_id: str
    claim_id: str | None = None
    payment_ids: list[str] = Field(default_factory=list)
    total_amount: float
    payment_date: str | None = None
    severity: Literal["medium", "high"]


class ClinicalGapPaymentFlag(BaseModel):
    member_id: str
    member_name: str | None = None
    measure_id: str
    measure_name: str
    payment_id: str
    payment_amount: float
    payment_date: str | None = None
    flag_type: Literal["high_risk_gap_with_payment"] = "high_risk_gap_with_payment"
    severity: Literal["high", "critical"]


class PaymentIntegrityResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    duplicate_payments: list[DuplicatePaymentAnomaly] = Field(default_factory=list)
    clinical_gap_flags: list[ClinicalGapPaymentFlag] = Field(default_factory=list)
    anomaly_count: int = 0
    validation_notes: list[str] = Field(default_factory=list)
