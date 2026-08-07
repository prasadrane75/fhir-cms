from typing import Literal

from pydantic import BaseModel, Field


class ADTIngestionResult(BaseModel):
    """Parsed HL7 v2.x ADT message ingestion outcome."""

    message_control_id: str
    message_type: str
    event_code: str
    sending_application: str | None = None
    patient_id: str | None = None
    patient_name: str | None = None
    processing_status: Literal["accepted", "rejected"]
    rejection_reason: str | None = None
    segment_count: int = 0
    raw_message_preview: str = Field(max_length=500)
