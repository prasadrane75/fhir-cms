from uuid import UUID

from app.ai.agent import ReviewMode
from app.core.models.case import Case, CaseStatus
from app.services.audit import write_audit_log


async def audit_case_created(case: Case, *, actor: str | None = None) -> None:
    await write_audit_log(
        "case.created",
        "Case",
        str(case.id),
        actor=actor,
        details={"patient_id": case.patient_id, "title": case.title},
        message=f"Case '{case.title}' created for patient {case.patient_id}",
    )


async def audit_case_transition(
    case_id: UUID,
    target: CaseStatus,
    *,
    reason: str | None = None,
    actor: str | None = None,
) -> None:
    await write_audit_log(
        "case.transition",
        "Case",
        str(case_id),
        actor=actor,
        details={"target_status": target.value, "reason": reason},
        message=f"Case transitioned to {target.value}",
    )


async def audit_case_ai_review(
    case: Case,
    *,
    clinical_query: str,
    review_mode: ReviewMode = ReviewMode.PRIOR_AUTH,
    actor: str | None = None,
) -> None:
    await write_audit_log(
        "case.ai_review",
        "Case",
        str(case.id),
        actor=actor,
        details={
            "clinical_query": clinical_query,
            "review_mode": review_mode.value,
            "status": case.status.value,
        },
        message=(
            "AI clinical review completed; awaiting human approval"
            if case.status == CaseStatus.PENDING_APPROVAL
            else "AI clinical review completed"
        ),
    )
