from app.core.models.appeals import AppealDraftRequest, AppealDraftResponse
from app.core.models.case import CaseStatus
from app.services.case_service import case_service

RISK_KEYWORDS = (
    "hypertension",
    "kidney",
    "comorbid",
    "multi-system",
    "progression",
    "creatinine",
    "glucose",
    "diabetes",
)


class AppealsService:
    def draft_recommendation(self, request: AppealDraftRequest) -> AppealDraftResponse:
        notes: list[str] = []
        case = case_service.get_case(request.case_id)
        if not case:
            raise KeyError(f"Case {request.case_id} not found")

        summary = case.ai_summary or "No AI recommendation available."
        summary_lower = summary.lower()
        multi_system_risk = sum(1 for keyword in RISK_KEYWORDS if keyword in summary_lower) >= 2

        if case.status == CaseStatus.PENDING_APPROVAL:
            notes.append("Case is at Pending_Approval after LangGraph interrupt(); audit trail is active.")
        elif case.status == CaseStatus.AI_REVIEW:
            notes.append("Case still in AI_Review; formal recommendation draft uses latest AI summary.")
        else:
            notes.append(f"Case status is {case.status.value}; draft generated from last AI summary.")

        draft = (
            "APPEALS & GRIEVANCES — STRUCTURED CLINICAL RECOMMENDATION\n"
            f"Case: {case.id}\n"
            f"Patient: {case.patient_id}\n"
            f"Status: {case.status.value}\n\n"
            f"Clinical summary:\n{summary}\n\n"
            f"Multi-system risk flagged: {'YES' if multi_system_risk else 'NO'}\n"
            "Next step: human reviewer approve or reject via /human-approval."
        )

        return AppealDraftResponse(
            case_id=case.id,
            status=case.status.value,
            clinical_recommendation=summary,
            multi_system_risk_detected=multi_system_risk,
            audit_trace_ready=True,
            draft_summary=draft,
            validation_notes=notes,
        )


appeals_service = AppealsService()
