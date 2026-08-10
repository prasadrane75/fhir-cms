import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from app.core.models.eligibility import (
    Eligibility270Request,
    Eligibility271Response,
    Enrollment834Request,
    Enrollment834Response,
)
from app.core.models.claims import ClaimAdjudicationRequest, ClaimAdjudicationResponse
from app.core.models.appeals import AppealDraftRequest, AppealDraftResponse
from app.core.models.encounter import EncounterNormalizeRequest, EncounterNormalizeResponse
from app.core.models.prior_auth import PriorAuthEvaluateRequest, PriorAuthEvaluateResponse
from app.core.models.provider import ProviderValidationRequest, ProviderValidationResponse
from app.core.models.tpl import TPLCheckRequest, TPLCheckResponse
from app.core.models.care_management import CareGapAnalyticsRequest, CareGapAnalyticsResponse
from app.core.models.payment_integrity import PaymentIntegrityRequest, PaymentIntegrityResponse
from app.core.models.reporting import BalancedScorecardResponse, ReportingRequest
from app.core.models.hl7_adt import ADTIngestionResult
from app.services.audit_logger import schedule_audit_log
from app.services.appeals_service import appeals_service
from app.services.care_management_service import care_management_service
from app.services.claims_adjudication_service import claims_adjudication_service
from app.services.encounter_normalization_service import encounter_normalization_service
from app.services.eligibility_service import eligibility_service
from app.services.hl7_adt_service import hl7_adt_service
from app.services.payment_integrity_service import payment_integrity_service
from app.services.prior_auth_service import prior_auth_service
from app.services.provider_validation_service import provider_validation_service
from app.services.reporting_service import reporting_service
from app.services.tpl_service import tpl_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/capabilities", tags=["capabilities"])


async def _scorecard_response(
    payload: ReportingRequest,
    background_tasks: BackgroundTasks,
) -> BalancedScorecardResponse:
    result = await reporting_service.build_balanced_scorecard(payload)

    logger.info(
        "Capability 11 scorecard generated (lookback_days=%s, events=%s, exceptions=%s)",
        payload.lookback_days,
        result.audit_exceptions.total_events,
        result.audit_exceptions.exception_count,
    )

    schedule_audit_log(
        background_tasks,
        action="capability11.scorecard_generated",
        entity_type="BalancedScorecard",
        entity_id=str(result.transaction_id),
        actor="enterprise-reporting",
        details={
            "lookback_days": payload.lookback_days,
            "total_events": result.audit_exceptions.total_events,
            "exception_count": result.audit_exceptions.exception_count,
            "exception_rate": result.audit_exceptions.exception_rate,
            "approval_ratio": result.approval_denial.approval_ratio,
            "ai_review_count": result.model_tracking.ai_review_count,
            "completed_case_cycles": result.cycle_times.sample_size,
        },
        message=(
            f"Balanced scorecard generated for {payload.lookback_days} day(s): "
            f"{result.audit_exceptions.total_events} audit event(s), "
            f"{result.audit_exceptions.exception_count} exception(s)"
        ),
    )
    return result


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
    "/02/claims/adjudicate",
    response_model=ClaimAdjudicationResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 02 — claims adjudication rules check",
)
async def adjudicate_claim(
    payload: ClaimAdjudicationRequest,
    background_tasks: BackgroundTasks,
) -> ClaimAdjudicationResponse:
    result = claims_adjudication_service.adjudicate(payload)

    logger.info(
        "Capability 02 claim adjudication (claim_id=%s, member_id=%s, status=%s, duplicate=%s)",
        payload.claim_id,
        payload.member_id,
        result.adjudication_status,
        result.duplicate_detected,
    )

    schedule_audit_log(
        background_tasks,
        action="capability02.claim_adjudicated",
        entity_type="Claim",
        entity_id=payload.claim_id,
        actor="claims-adjudication-mock",
        details={
            "member_id": payload.member_id,
            "payer_id": payload.payer_id,
            "service_date": payload.service_date.isoformat(),
            "line_count": len(payload.line_items),
            "adjudication_status": result.adjudication_status,
            "duplicate_detected": result.duplicate_detected,
            "duplicate_claim_ids": result.duplicate_claim_ids,
            "transaction_id": str(result.transaction_id),
            "validation_notes": result.validation_notes,
        },
        message=(
            f"Claim {payload.claim_id} adjudicated for member {payload.member_id}: "
            f"{result.adjudication_status}"
        ),
    )
    return result


@router.post(
    "/04/providers/validate",
    response_model=ProviderValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 04 — provider NPI and credentialing validation",
)
async def validate_provider(
    payload: ProviderValidationRequest,
    background_tasks: BackgroundTasks,
) -> ProviderValidationResponse:
    result = provider_validation_service.validate_provider(payload)
    schedule_audit_log(
        background_tasks,
        action="capability04.provider_validated",
        entity_type="Provider",
        entity_id=payload.npi,
        actor="provider-directory",
        details={
            "tax_id": payload.tax_id,
            "network_status": result.network_status,
            "credentialing_status": result.credentialing_status,
            "transaction_id": str(result.transaction_id),
        },
        message=f"Provider {payload.npi} validation: {result.network_status}/{result.credentialing_status}",
    )
    return result


@router.post(
    "/05/prior-auth/evaluate",
    response_model=PriorAuthEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 05 — utilization management prior authorization evaluation",
)
async def evaluate_prior_auth(
    payload: PriorAuthEvaluateRequest,
    background_tasks: BackgroundTasks,
) -> PriorAuthEvaluateResponse:
    try:
        result = await prior_auth_service.evaluate(payload)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prior auth evaluation failed: {exc}") from exc

    schedule_audit_log(
        background_tasks,
        action="capability05.prior_auth_evaluated",
        entity_type="Case",
        entity_id=str(result.case_id),
        actor="langgraph-prior-auth",
        details={
            "patient_id": payload.patient_id,
            "member_id": payload.member_id,
            "status": result.status,
            "awaiting_human_approval": result.awaiting_human_approval,
            "clinical_query": payload.clinical_query,
        },
        message=f"Prior auth case {result.case_id} evaluated: {result.status}",
    )
    return result


@router.post(
    "/06/appeals/draft",
    response_model=AppealDraftResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 06 — appeals and grievances structured recommendation draft",
)
async def draft_appeal_recommendation(
    payload: AppealDraftRequest,
    background_tasks: BackgroundTasks,
) -> AppealDraftResponse:
    try:
        result = appeals_service.draft_recommendation(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    schedule_audit_log(
        background_tasks,
        action="capability06.appeal_draft_generated",
        entity_type="Case",
        entity_id=str(result.case_id),
        actor="appeals-grievances",
        details={
            "status": result.status,
            "multi_system_risk_detected": result.multi_system_risk_detected,
            "audit_trace_ready": result.audit_trace_ready,
        },
        message=f"Appeal draft generated for case {result.case_id}",
    )
    return result


@router.post(
    "/08/encounters/normalize",
    response_model=EncounterNormalizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 08 — encounter normalization for CMS reporting",
)
async def normalize_encounter(
    payload: EncounterNormalizeRequest,
    background_tasks: BackgroundTasks,
) -> EncounterNormalizeResponse:
    result = encounter_normalization_service.normalize(payload)
    schedule_audit_log(
        background_tasks,
        action="capability08.encounter_normalized",
        entity_type="Encounter",
        entity_id=payload.member_id,
        actor="cms-encounter-normalizer",
        details={
            "patient_id": payload.patient_id,
            "cms_ready": result.cms_ready,
            "diagnosis_count": len(result.normalized_diagnoses),
            "procedure_count": len(result.normalized_procedures),
            "transaction_id": str(result.transaction_id),
        },
        message=f"Encounter normalized for member {payload.member_id}: cms_ready={result.cms_ready}",
    )
    return result


@router.post(
    "/09/tpl/check",
    response_model=TPLCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 09 — third-party liability primary payer check",
)
async def check_tpl(
    payload: TPLCheckRequest,
    background_tasks: BackgroundTasks,
) -> TPLCheckResponse:
    result = tpl_service.check_tpl(payload)
    schedule_audit_log(
        background_tasks,
        action="capability09.tpl_checked",
        entity_type="TPL",
        entity_id=payload.member_id,
        actor="tpl-analyzer",
        details={
            "payer_id": payload.payer_id,
            "primary_payer_status": result.primary_payer_status,
            "tpl_targets": result.tpl_targets,
            "transaction_id": str(result.transaction_id),
        },
        message=f"TPL check for member {payload.member_id}: {result.primary_payer_status}",
    )
    return result


@router.post(
    "/07/care-gaps/analyze",
    response_model=CareGapAnalyticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 07 — care management and care gap analytics",
)
async def analyze_care_gaps(
    payload: CareGapAnalyticsRequest,
    background_tasks: BackgroundTasks,
) -> CareGapAnalyticsResponse:
    result = care_management_service.analyze_care_gaps(payload)

    logger.info(
        "Capability 07 care gap analytics (member_count=%s, gaps=%s, high_priority=%s)",
        result.member_count,
        len(result.care_gaps),
        result.high_priority_gap_count,
    )

    schedule_audit_log(
        background_tasks,
        action="capability07.care_gaps_analyzed",
        entity_type="CareGapAnalytics",
        entity_id=payload.member_id or "all-members",
        actor="care-management-analytics",
        details={
            "member_id": payload.member_id,
            "include_all_members": payload.include_all_members,
            "member_count": result.member_count,
            "care_gap_count": len(result.care_gaps),
            "high_priority_gap_count": result.high_priority_gap_count,
            "transaction_id": str(result.transaction_id),
            "validation_notes": result.validation_notes,
        },
        message=(
            f"Care gap analytics for {payload.member_id or 'all members'}: "
            f"{len(result.care_gaps)} gap(s), "
            f"{result.high_priority_gap_count} high-priority"
        ),
    )
    return result


@router.post(
    "/10/payment-integrity/detect",
    response_model=PaymentIntegrityResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 10 — payment integrity anomaly detection",
)
async def detect_payment_anomalies(
    payload: PaymentIntegrityRequest,
    background_tasks: BackgroundTasks,
) -> PaymentIntegrityResponse:
    result = payment_integrity_service.detect_anomalies(payload)

    logger.info(
        "Capability 10 payment integrity (member_id=%s, anomalies=%s)",
        payload.member_id,
        result.anomaly_count,
    )

    schedule_audit_log(
        background_tasks,
        action="capability10.payment_integrity_detected",
        entity_type="PaymentIntegrity",
        entity_id=payload.member_id or payload.payer_id or "all-scope",
        actor="payment-integrity-analytics",
        details={
            "member_id": payload.member_id,
            "payer_id": payload.payer_id,
            "lookback_days": payload.lookback_days,
            "duplicate_payment_count": len(result.duplicate_payments),
            "clinical_gap_flag_count": len(result.clinical_gap_flags),
            "anomaly_count": result.anomaly_count,
            "transaction_id": str(result.transaction_id),
            "validation_notes": result.validation_notes,
        },
        message=(
            f"Payment integrity scan detected {result.anomaly_count} anomaly(ies) "
            f"({len(result.duplicate_payments)} duplicate payments, "
            f"{len(result.clinical_gap_flags)} clinical gap flags)"
        ),
    )
    return result


@router.get(
    "/11/reporting/scorecard",
    response_model=BalancedScorecardResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 11 — enterprise data warehouse balanced scorecard",
)
async def get_balanced_scorecard(
    background_tasks: BackgroundTasks,
    lookback_days: int = Query(default=30, ge=1, le=365),
) -> BalancedScorecardResponse:
    return await _scorecard_response(ReportingRequest(lookback_days=lookback_days), background_tasks)


@router.post(
    "/11/reporting/scorecard",
    response_model=BalancedScorecardResponse,
    status_code=status.HTTP_200_OK,
    summary="Capability 11 — enterprise data warehouse balanced scorecard (POST)",
)
async def post_balanced_scorecard(
    payload: ReportingRequest,
    background_tasks: BackgroundTasks,
) -> BalancedScorecardResponse:
    return await _scorecard_response(payload, background_tasks)


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
