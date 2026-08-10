from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EncounterNormalizeRequest(BaseModel):
    member_id: str
    patient_id: str
    diagnosis_codes: list[str] = Field(default_factory=list)
    procedure_codes: list[str] = Field(default_factory=list)
    service_date: str | None = None


class NormalizedCode(BaseModel):
    source_code: str
    normalized_code: str
    code_system: Literal["ICD-10", "CPT", "HCPCS"]
    display: str | None = None


class EncounterNormalizeResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    member_id: str
    patient_id: str
    cms_ready: bool
    normalized_diagnoses: list[NormalizedCode] = Field(default_factory=list)
    normalized_procedures: list[NormalizedCode] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
