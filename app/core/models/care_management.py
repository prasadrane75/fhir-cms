from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CareGapAnalyticsRequest(BaseModel):
    """Capability 07 — care management and care gap analytics request."""

    member_id: str | None = None
    include_all_members: bool = False


class ComorbidityRisk(BaseModel):
    member_id: str
    member_name: str | None = None
    conditions: list[str] = Field(default_factory=list)
    comorbidity_risk_score: float
    risk_level: Literal["low", "moderate", "high", "critical"]


class CareGap(BaseModel):
    member_id: str
    measure_id: str
    measure_name: str
    related_condition: str
    priority: Literal["low", "medium", "high"]
    gap_status: Literal["open", "overdue"]
    days_overdue: int | None = None


class CareGapAnalyticsResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    member_count: int
    comorbidity_risks: list[ComorbidityRisk] = Field(default_factory=list)
    care_gaps: list[CareGap] = Field(default_factory=list)
    high_priority_gap_count: int = 0
    validation_notes: list[str] = Field(default_factory=list)
