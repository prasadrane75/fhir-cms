from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TPLCheckRequest(BaseModel):
    member_id: str
    payer_id: str
    accident_related: bool = False
    other_coverage_indicator: bool = False


class TPLCheckResponse(BaseModel):
    transaction_id: UUID = Field(default_factory=uuid4)
    member_id: str
    primary_payer_status: Literal["confirmed", "subrogation_review", "other_coverage_found"]
    tpl_targets: list[str] = Field(default_factory=list)
    validation_notes: list[str] = Field(default_factory=list)
