from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ReportingRequest(BaseModel):
    """Capability 11 — balanced scorecard reporting request."""

    lookback_days: int = Field(default=30, ge=1, le=365)


class CycleTimeMetrics(BaseModel):
    avg_pending_to_ai_review_hours: float | None = None
    avg_ai_review_hours: float | None = None
    avg_pending_approval_hours: float | None = None
    avg_total_cycle_hours: float | None = None
    sample_size: int = 0


class ApprovalDenialMetrics(BaseModel):
    approved_count: int = 0
    denied_count: int = 0
    approval_ratio: float | None = None
    denial_ratio: float | None = None


class AuditExceptionMetrics(BaseModel):
    total_events: int = 0
    exception_count: int = 0
    exception_rate: float | None = None
    by_category: dict[str, int] = Field(default_factory=dict)


class ActionCount(BaseModel):
    action: str
    count: int


class ModelTrackingMetrics(BaseModel):
    ai_review_count: int = 0
    reviews_by_mode: dict[str, int] = Field(default_factory=dict)
    capability_invocations: dict[str, int] = Field(default_factory=dict)
    top_actions: list[ActionCount] = Field(default_factory=list)


class BalancedScorecardResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    lookback_days: int
    cycle_times: CycleTimeMetrics
    approval_denial: ApprovalDenialMetrics
    audit_exceptions: AuditExceptionMetrics
    model_tracking: ModelTrackingMetrics
    validation_notes: list[str] = Field(default_factory=list)
