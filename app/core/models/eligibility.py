from datetime import date
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Eligibility270Request(BaseModel):
    """X12 270 eligibility inquiry (structured mock payload)."""

    member_id: str
    payer_id: str
    provider_npi: str | None = None
    subscriber_first_name: str | None = None
    subscriber_last_name: str | None = None
    date_of_birth: date | None = None
    service_date: date | None = None
    x12_payload: str | None = None


class Eligibility271Response(BaseModel):
    """X12 271 eligibility response (mock)."""

    transaction_id: UUID = Field(default_factory=uuid4)
    member_id: str
    payer_id: str
    eligibility_status: Literal["active", "inactive", "unknown"]
    coverage_level: str | None = None
    plan_name: str | None = None
    group_number: str | None = None
    effective_date: date | None = None
    termination_date: date | None = None
    validation_notes: list[str] = Field(default_factory=list)
    x12_271_mock: str | None = None


class Enrollment834Request(BaseModel):
    """X12 834 benefit enrollment and maintenance (structured mock payload)."""

    member_id: str
    payer_id: str
    plan_id: str
    coverage_start_date: date
    subscriber_first_name: str
    subscriber_last_name: str
    coverage_end_date: date | None = None
    relationship_code: str = "18"
    x12_payload: str | None = None


class Enrollment834Response(BaseModel):
    """X12 834 validation result with optional 999 acknowledgment mock."""

    transaction_id: UUID = Field(default_factory=uuid4)
    member_id: str
    payer_id: str
    validation_status: Literal["accepted", "rejected"]
    rejection_reasons: list[str] = Field(default_factory=list)
    x12_999_mock: str | None = None
