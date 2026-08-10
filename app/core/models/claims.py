from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ClaimLineItem(BaseModel):
    procedure_code: str
    billed_amount: float
    units: int = 1
    diagnosis_codes: list[str] = Field(default_factory=list)


class ClaimAdjudicationRequest(BaseModel):
    """Capability 02 — structured claim for adjudication rules check."""

    claim_id: str
    member_id: str
    payer_id: str
    provider_npi: str | None = None
    service_date: date
    line_items: list[ClaimLineItem]
    x12_payload: str | None = None


class ClaimLineAdjudication(BaseModel):
    procedure_code: str
    billed_amount: float
    allowed_amount: float | None = None
    paid_amount: float | None = None
    status: Literal["approved", "denied", "adjusted"]
    reason_codes: list[str] = Field(default_factory=list)


class ClaimAdjudicationResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    claim_id: str
    member_id: str
    payer_id: str
    adjudication_status: Literal["approved", "partial", "denied"]
    line_adjudications: list[ClaimLineAdjudication] = Field(default_factory=list)
    duplicate_detected: bool = False
    duplicate_claim_ids: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
    x12_835_mock: str | None = None
