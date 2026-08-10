from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ProviderValidationRequest(BaseModel):
    npi: str
    tax_id: str | None = None
    provider_name: str | None = None


class ProviderValidationResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    npi: str
    network_status: Literal["active", "inactive", "not_found"]
    credentialing_status: Literal["compliant", "expired", "pending"]
    validation_notes: list[str] = Field(default_factory=list)
