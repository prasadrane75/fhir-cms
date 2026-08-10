from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.ai.agent import ClaimReviewContext, ReviewMode
from app.core.models.case import (
    Case,
    CaseCreate,
    CaseReviewRequest,
    CaseStatus,
    CaseTransitionRequest,
    HumanApprovalRequest,
)
from app.services.audit_logger import schedule_audit_log
from app.services.case_service import case_service
from app.state_machine.case_state import InvalidTransitionError

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[Case])
async def list_cases() -> list[Case]:
    return case_service.list_cases()


@router.post("", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    background_tasks: BackgroundTasks,
) -> Case:
    case = await case_service.create_case(payload)
    schedule_audit_log(
        background_tasks,
        action="case.created",
        entity_type="Case",
        entity_id=str(case.id),
        details={"patient_id": case.patient_id, "title": case.title},
        message=f"Case '{case.title}' created for patient {case.patient_id}",
    )
    return case


@router.get("/{case_id}", response_model=Case)
async def get_case(case_id: UUID) -> Case:
    case = case_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/{case_id}/transitions", response_model=list[CaseStatus])
async def get_allowed_transitions(case_id: UUID) -> list[CaseStatus]:
    try:
        return case_service.allowed_transitions(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found") from None


@router.post("/{case_id}/transition", response_model=Case)
async def transition_case(
    case_id: UUID,
    payload: CaseTransitionRequest,
    background_tasks: BackgroundTasks,
) -> Case:
    try:
        case = case_service.transition(case_id, payload.target_status)
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found") from None
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition from {exc.current.value} to {exc.target.value}",
        ) from exc

    schedule_audit_log(
        background_tasks,
        action="case.transition",
        entity_type="Case",
        entity_id=str(case_id),
        details={
            "target_status": payload.target_status.value,
            "reason": payload.reason,
        },
        message=f"Case transitioned to {payload.target_status.value}",
    )
    return case


@router.post("/{case_id}/ai-review", response_model=Case)
async def ai_review_case(
    case_id: UUID,
    payload: CaseReviewRequest,
    background_tasks: BackgroundTasks,
) -> Case:
    try:
        review_mode = ReviewMode(payload.review_mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid review_mode '{payload.review_mode}'. Use prior_auth or claims_adjudication.",
        ) from exc

    claim_context = None
    if review_mode == ReviewMode.CLAIMS_ADJUDICATION:
        missing = [
            field
            for field, value in {
                "claim_id": payload.claim_id,
                "member_id": payload.member_id,
                "payer_id": payload.payer_id,
                "service_date": payload.service_date,
            }.items()
            if not value
        ]
        if missing or not payload.line_items:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Claims adjudication review requires claim_id, member_id, payer_id, "
                    "service_date, and at least one line item."
                ),
            )
        claim_context = ClaimReviewContext(
            claim_id=payload.claim_id,
            member_id=payload.member_id,
            payer_id=payload.payer_id,
            service_date=payload.service_date.isoformat(),
            provider_npi=payload.provider_npi,
            line_items=payload.line_items,
        )

    try:
        case = await case_service.run_ai_review(
            case_id,
            payload.clinical_query,
            review_mode=review_mode,
            claim_context=claim_context,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found") from None
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"AI review requires case to be in {CaseStatus.AI_REVIEW.value}, currently {exc.current.value}",
        ) from exc

    schedule_audit_log(
        background_tasks,
        action="case.ai_review",
        entity_type="Case",
        entity_id=str(case_id),
        details={
            "clinical_query": payload.clinical_query,
            "review_mode": review_mode.value,
            "status": case.status.value,
        },
        message=(
            "AI claims adjudication completed; awaiting human approval"
            if review_mode == ReviewMode.CLAIMS_ADJUDICATION
            and case.status == CaseStatus.PENDING_APPROVAL
            else (
                "AI clinical review completed; awaiting human approval"
                if case.status == CaseStatus.PENDING_APPROVAL
                else (
                    "AI claims adjudication completed"
                    if review_mode == ReviewMode.CLAIMS_ADJUDICATION
                    else "AI clinical review completed"
                )
            )
        ),
    )
    return case


@router.post("/{case_id}/human-approval", response_model=Case)
async def human_approval_case(
    case_id: UUID,
    payload: HumanApprovalRequest,
    background_tasks: BackgroundTasks,
) -> Case:
    try:
        case = await case_service.resume_human_approval(case_id, payload.approved, payload.reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="Case not found") from None
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Human approval requires case to be in {CaseStatus.PENDING_APPROVAL.value}, "
                f"currently {exc.current.value}"
            ),
        ) from exc

    schedule_audit_log(
        background_tasks,
        action="case.human_approval",
        entity_type="Case",
        entity_id=str(case_id),
        details={
            "approved": payload.approved,
            "reason": payload.reason,
            "target_status": case.status.value,
        },
        message=f"Human reviewer {'approved' if payload.approved else 'rejected'} the case",
    )
    return case
