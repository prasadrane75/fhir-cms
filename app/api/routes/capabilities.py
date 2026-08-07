import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.core.models.eligibility import (
    Eligibility270Request,
    Eligibility271Response,
    Enrollment834Request,
    Enrollment834Response,
)
from app.core.models.hl7_adt import ADTIngestionResult
from app.services.audit_logger import schedule_audit_log
from app.services.eligibility_service import eligibility_service
from app.services.hl7_adt_service import hl7_adt_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.post(
    "/01/eligibility/270",
    response_model=Eligibility271Response,
    status_code=status.HTTP_200_OK,
    summary="Capability 01 — mock X12 270 eligibility validation",
)
async def validate_eligibility_270(
    payload: Eligibility270Request,
    background_tasks: BackgroundTasks,
) -> Eligibility271Response:
    result = eligibility_service.validate_270(payload)

    logger.info(
        "Capability 01 270 eligibility request (member_id=%s, payer_id=%s, status=%s)",
        payload.member_id,
        payload.payer_id,
        result.eligibility_status,
    )

    schedule_audit_log(
        background_tasks,
        action="capability01.eligibility_270_received",
        entity_type="Eligibility270",
        entity_id=payload.member_id,
        actor="x12-eligibility-mock",
        details={
            "payer_id": payload.payer_id,
            "provider_npi": payload.provider_npi,
            "service_date": payload.service_date.isoformat() if payload.service_date else None,
            "has_x12_payload": bool(payload.x12_payload),
            "eligibility_status": result.eligibility_status,
            "transaction_id": str(result.transaction_id),
            "validation_notes": result.validation_notes,
        },
        message=(
            f"270 eligibility inquiry for member {payload.member_id}: "
            f"{result.eligibility_status}"
        ),
    )
    return result


@router.post(
    "/01/eligibility/834",
    response_model=Enrollment834Response,
    status_code=status.HTTP_200_OK,
    summary="Capability 01 — mock X12 834 enrollment validation",
)
async def validate_enrollment_834(
    payload: Enrollment834Request,
    background_tasks: BackgroundTasks,
) -> Enrollment834Response:
    result = eligibility_service.validate_834(payload)

    logger.info(
        "Capability 01 834 enrollment request (member_id=%s, payer_id=%s, status=%s)",
        payload.member_id,
        payload.payer_id,
        result.validation_status,
    )

    schedule_audit_log(
        background_tasks,
        action="capability01.eligibility_834_received",
        entity_type="Eligibility834",
        entity_id=payload.member_id,
        actor="x12-eligibility-mock",
        details={
            "payer_id": payload.payer_id,
            "plan_id": payload.plan_id,
            "coverage_start_date": payload.coverage_start_date.isoformat(),
            "coverage_end_date": (
                payload.coverage_end_date.isoformat() if payload.coverage_end_date else None
            ),
            "has_x12_payload": bool(payload.x12_payload),
            "validation_status": result.validation_status,
            "transaction_id": str(result.transaction_id),
            "rejection_reasons": result.rejection_reasons,
        },
        message=(
            f"834 enrollment validation for member {payload.member_id}: "
            f"{result.validation_status}"
        ),
    )
    return result


@router.post(
    "/03/adt",
    response_model=ADTIngestionResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Capability 03 — HL7 v2.x ADT ingestion listener",
)
async def ingest_hl7_adt(
    request: Request,
    background_tasks: BackgroundTasks,
) -> ADTIngestionResult:
    raw_body = (await request.body()).decode("utf-8", errors="replace").strip()
    if not raw_body:
        raise HTTPException(status_code=400, detail="HL7 ADT payload is required")

    result = hl7_adt_service.ingest_adt(raw_body)

    logger.info(
        "Capability 03 ADT ingestion (control_id=%s, type=%s, event=%s, status=%s)",
        result.message_control_id,
        result.message_type,
        result.event_code,
        result.processing_status,
    )

    schedule_audit_log(
        background_tasks,
        action="capability03.adt_received",
        entity_type="HL7ADT",
        entity_id=result.message_control_id,
        actor=result.sending_application or "hl7-adt-listener",
        details={
            "message_type": result.message_type,
            "event_code": result.event_code,
            "patient_id": result.patient_id,
            "patient_name": result.patient_name,
            "processing_status": result.processing_status,
            "rejection_reason": result.rejection_reason,
            "segment_count": result.segment_count,
            "content_type": request.headers.get("content-type"),
        },
        message=(
            f"ADT {result.event_code} message {result.message_control_id} "
            f"for patient {result.patient_id or 'unknown'}: {result.processing_status}"
        ),
    )

    return result
