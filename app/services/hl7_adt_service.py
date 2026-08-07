from app.core.models.hl7_adt import ADTIngestionResult


def _normalize_hl7(raw: str) -> str:
    return raw.strip().replace("\n", "\r").replace("\r\r", "\r")


def _split_segments(raw: str) -> list[str]:
    normalized = _normalize_hl7(raw)
    if not normalized:
        return []
    return [segment for segment in normalized.split("\r") if segment]


def _field(segment: str, index: int) -> str:
    parts = segment.split("|")
    if index >= len(parts):
        return ""
    return parts[index]


def _component(value: str, index: int) -> str:
    parts = value.split("^")
    if index >= len(parts):
        return ""
    return parts[index]


def _format_patient_name(pid5: str) -> str | None:
    if not pid5:
        return None
    family = _component(pid5, 0)
    given = _component(pid5, 1)
    middle = _component(pid5, 2)
    name_parts = [part for part in [given, middle, family] if part]
    return " ".join(name_parts) if name_parts else pid5


class HL7ADTService:
    def ingest_adt(self, raw_message: str) -> ADTIngestionResult:
        segments = _split_segments(raw_message)
        preview = _normalize_hl7(raw_message)[:500]

        if not segments:
            return ADTIngestionResult(
                message_control_id="unknown",
                message_type="unknown",
                event_code="unknown",
                processing_status="rejected",
                rejection_reason="Empty HL7 payload",
                raw_message_preview=preview,
            )

        msh_segment = next((segment for segment in segments if segment.startswith("MSH")), None)
        if not msh_segment:
            return ADTIngestionResult(
                message_control_id="unknown",
                message_type="unknown",
                event_code="unknown",
                processing_status="rejected",
                rejection_reason="Missing MSH segment",
                segment_count=len(segments),
                raw_message_preview=preview,
            )

        message_type_field = _field(msh_segment, 8)
        message_type = message_type_field or "unknown"
        event_code = _component(message_type_field, 1) or "unknown"
        message_control_id = _field(msh_segment, 9) or "unknown"
        sending_application = _field(msh_segment, 2) or None

        if not message_type.startswith("ADT"):
            return ADTIngestionResult(
                message_control_id=message_control_id,
                message_type=message_type,
                event_code=event_code,
                sending_application=sending_application,
                processing_status="rejected",
                rejection_reason=f"Unsupported message type: {message_type}",
                segment_count=len(segments),
                raw_message_preview=preview,
            )

        pid_segment = next((segment for segment in segments if segment.startswith("PID")), None)
        patient_id = None
        patient_name = None
        if pid_segment:
            patient_id = _component(_field(pid_segment, 3), 0) or None
            patient_name = _format_patient_name(_field(pid_segment, 5))

        if not patient_id:
            return ADTIngestionResult(
                message_control_id=message_control_id,
                message_type=message_type,
                event_code=event_code,
                sending_application=sending_application,
                patient_name=patient_name,
                processing_status="rejected",
                rejection_reason="Missing PID-3 patient identifier",
                segment_count=len(segments),
                raw_message_preview=preview,
            )

        return ADTIngestionResult(
            message_control_id=message_control_id,
            message_type=message_type,
            event_code=event_code,
            sending_application=sending_application,
            patient_id=patient_id,
            patient_name=patient_name,
            processing_status="accepted",
            segment_count=len(segments),
            raw_message_preview=preview,
        )


hl7_adt_service = HL7ADTService()
