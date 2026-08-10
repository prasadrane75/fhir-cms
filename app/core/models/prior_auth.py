from uuid import UUID

from pydantic import BaseModel, Field


class PriorAuthEvaluateRequest(BaseModel):
    patient_id: str
    member_id: str
    clinical_query: str = "Is there risk of chronic disease progression?"
    title: str | None = None
    description: str | None = None


class PriorAuthEvaluateResponse(BaseModel):
    case_id: UUID
    status: str
    ai_summary: str | None = None
    awaiting_human_approval: bool = False
    validation_notes: list[str] = Field(default_factory=list)
