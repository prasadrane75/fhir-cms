from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.core.models.observation import Observation
from app.core.models.patient import Patient


class CaseStatus(str, Enum):
    PENDING = "Pending"
    AI_REVIEW = "AI_Review"
    PENDING_APPROVAL = "Pending_Approval"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class Case(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    patient_id: str
    status: CaseStatus = CaseStatus.PENDING
    title: str
    description: str | None = None
    patient: Patient | None = None
    observations: list[Observation] = Field(default_factory=list)
    ai_summary: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CaseCreate(BaseModel):
    patient_id: str
    title: str
    description: str | None = None


class CaseTransitionRequest(BaseModel):
    target_status: CaseStatus
    reason: str | None = None


class CaseReviewRequest(BaseModel):
    clinical_query: str = "Summarize relevant clinical context for this case."


class HumanApprovalRequest(BaseModel):
    approved: bool
    reason: str | None = None
