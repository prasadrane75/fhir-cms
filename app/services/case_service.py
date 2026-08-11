from datetime import datetime
from uuid import UUID

from app.ai.agent import ClaimReviewContext, ReviewMode, resume_case_review, run_case_review
from app.core.fhir_client import FHIRClient
from app.core.models.case import Case, CaseCreate, CaseStatus
from app.core.models.observation import Observation
from app.services.case_audit import audit_case_ai_review, audit_case_created, audit_case_transition
from app.services.fhir_webhook import observation_label
from app.state_machine.case_state import InvalidTransitionError, get_allowed_transitions, validate_transition


class CaseService:
    def __init__(self) -> None:
        self._cases: dict[UUID, Case] = {}
        self._fhir = FHIRClient()

    def list_cases(self) -> list[Case]:
        return sorted(self._cases.values(), key=lambda c: c.created_at, reverse=True)

    def get_case(self, case_id: UUID) -> Case | None:
        return self._cases.get(case_id)

    def find_workflow_case_for_patient(self, patient_id: str) -> Case | None:
        for case in self.list_cases():
            if case.patient_id != patient_id:
                continue
            if case.status in {CaseStatus.PENDING, CaseStatus.AI_REVIEW}:
                return case
        return None

    async def refresh_case_clinical_data(self, case: Case) -> Case:
        try:
            case.patient = await self._fhir.get_patient(case.patient_id)
            case.observations = await self._fhir.search_observations(case.patient_id)
        except Exception:
            pass
        case.updated_at = datetime.utcnow()
        return case

    async def create_case(self, payload: CaseCreate) -> Case:
        case = Case(
            patient_id=payload.patient_id,
            title=payload.title,
            description=payload.description,
        )
        await self.refresh_case_clinical_data(case)
        self._cases[case.id] = case
        return case

    async def create_case_from_observation(
        self,
        patient_id: str,
        observation: Observation,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> Case:
        label = observation_label(observation)
        value = observation.display_value
        return await self.create_case(
            CaseCreate(
                patient_id=patient_id,
                title=title or f"Auto-review: {label}",
                description=description or f"Triggered by incoming observation {label} = {value}.",
            )
        )

    def transition(self, case_id: UUID, target: CaseStatus) -> Case:
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")
        validate_transition(case.status, target)
        case.status = target
        case.updated_at = datetime.utcnow()
        return case

    async def run_ai_review(
        self,
        case_id: UUID,
        clinical_query: str,
        *,
        review_mode: ReviewMode = ReviewMode.PRIOR_AUTH,
        claim_context: ClaimReviewContext | None = None,
    ) -> Case:
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")
        if case.status == CaseStatus.PENDING_APPROVAL:
            return case
        if case.status != CaseStatus.AI_REVIEW:
            raise InvalidTransitionError(case.status, CaseStatus.AI_REVIEW)

        review = await run_case_review(
            case,
            clinical_query,
            review_mode=review_mode,
            claim_context=claim_context,
        )
        case.ai_summary = review.summary
        if review.awaiting_approval:
            validate_transition(case.status, CaseStatus.PENDING_APPROVAL)
            case.status = CaseStatus.PENDING_APPROVAL
        case.updated_at = datetime.utcnow()
        return case

    async def start_auto_review_for_observation(
        self,
        patient_id: str,
        observation: Observation,
        clinical_query: str,
    ) -> Case:
        case = self.find_workflow_case_for_patient(patient_id)
        if case is None:
            case = await self.create_case_from_observation(patient_id, observation)
            await audit_case_created(case, actor="fhir-webhook")

        await self.refresh_case_clinical_data(case)

        if case.status in {
            CaseStatus.PENDING_APPROVAL,
            CaseStatus.APPROVED,
            CaseStatus.REJECTED,
        }:
            case = await self.create_case_from_observation(patient_id, observation)
            await audit_case_created(case, actor="fhir-webhook")
            await self.refresh_case_clinical_data(case)

        if case.status == CaseStatus.PENDING:
            validate_transition(case.status, CaseStatus.AI_REVIEW)
            case.status = CaseStatus.AI_REVIEW
            case.updated_at = datetime.utcnow()
            await audit_case_transition(case.id, CaseStatus.AI_REVIEW, actor="fhir-webhook")

        if case.status == CaseStatus.AI_REVIEW:
            case = await self.run_ai_review(case.id, clinical_query)
            await audit_case_ai_review(
                case,
                clinical_query=clinical_query,
                review_mode=ReviewMode.PRIOR_AUTH,
                actor="fhir-webhook",
            )

        return case

    async def resume_human_approval(
        self,
        case_id: UUID,
        approved: bool,
        reason: str | None = None,
    ) -> Case:
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")
        if case.status != CaseStatus.PENDING_APPROVAL:
            raise InvalidTransitionError(case.status, CaseStatus.PENDING_APPROVAL)

        review = await resume_case_review(case_id, approved, reason)
        target = CaseStatus.APPROVED if approved else CaseStatus.REJECTED
        case.status = target
        if review.summary:
            case.ai_summary = review.summary
        case.updated_at = datetime.utcnow()
        return case

    def allowed_transitions(self, case_id: UUID) -> list[CaseStatus]:
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")
        return get_allowed_transitions(case.status)


case_service = CaseService()
