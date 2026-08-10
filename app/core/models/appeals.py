from uuid import UUID

from pydantic import BaseModel, Field


class AppealDraftRequest(BaseModel):
    case_id: UUID


class AppealDraftResponse(BaseModel):
    case_id: UUID
    status: str
    clinical_recommendation: str
    multi_system_risk_detected: bool
    audit_trace_ready: bool
    draft_summary: str
    validation_notes: list[str] = Field(default_factory=list)
