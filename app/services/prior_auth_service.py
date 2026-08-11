from app.ai.agent import ReviewMode
from app.core.models.case import CaseCreate, CaseStatus
from app.core.models.prior_auth import PriorAuthEvaluateRequest, PriorAuthEvaluateResponse
from app.services.case_audit import audit_case_ai_review, audit_case_created, audit_case_transition
from app.services.case_service import case_service


class PriorAuthService:
    async def evaluate(self, request: PriorAuthEvaluateRequest) -> PriorAuthEvaluateResponse:
        notes: list[str] = []
        title = request.title or "Prior authorization: chronic disease progression review"
        description = (
            request.description
            or f"Auto-spawned UM case for member {request.member_id}, patient {request.patient_id}."
        )

        case = await case_service.create_case(
            CaseCreate(
                patient_id=request.patient_id,
                title=title,
                description=description,
            )
        )
        await audit_case_created(case, actor="langgraph-prior-auth")
        notes.append(f"Prior authorization case {case.id} created.")

        case_service.transition(case.id, CaseStatus.AI_REVIEW)
        await audit_case_transition(case.id, CaseStatus.AI_REVIEW, actor="langgraph-prior-auth")
        notes.append("Case transitioned to AI_Review for LangGraph clinical evaluation.")

        case = await case_service.run_ai_review(case.id, request.clinical_query, review_mode=ReviewMode.PRIOR_AUTH)
        await audit_case_ai_review(
            case,
            clinical_query=request.clinical_query,
            review_mode=ReviewMode.PRIOR_AUTH,
            actor="langgraph-prior-auth",
        )
        awaiting = case.status == CaseStatus.PENDING_APPROVAL
        if awaiting:
            notes.append("LangGraph agent completed review and paused at human_approval interrupt().")
        else:
            notes.append(f"Review completed with status {case.status.value}.")

        return PriorAuthEvaluateResponse(
            case_id=case.id,
            status=case.status.value,
            ai_summary=case.ai_summary,
            awaiting_human_approval=awaiting,
            validation_notes=notes,
        )


prior_auth_service = PriorAuthService()
