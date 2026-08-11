"""
25 end-to-end test scenarios covering the healthcare payer platform codebase.

Scenario map:
  SC01-SC03  Capability 01 — Eligibility (270/834)
  SC04-SC06  Capability 02 — Claims adjudication
  SC07-SC08  Capability 03 — HL7 ADT
  SC09-SC10  Capability 04 — Provider validation
  SC11       Capability 05 — Prior authorization (LangGraph path)
  SC12-SC13  Capability 06 — Appeals & grievances
  SC14-SC15  Capability 07 — Care gap analytics
  SC16-SC17  Capability 08 — Encounter CMS normalization
  SC18-SC19  Capability 09 — Third-party liability
  SC20       Capability 10 — Payment integrity
  SC21-SC22  Capability 11 — EDW scorecard
  SC23       Case state machine
  SC24       Case workflow API
  SC25       Webhooks, observations, agent, and UI routes
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.agent import (
    ClaimReviewContext,
    ReviewMode,
    build_case_context,
    build_claim_context,
)
from app.core.models.appeals import AppealDraftRequest
from app.core.models.care_management import CareGapAnalyticsRequest
from app.core.models.case import Case, CaseCreate, CaseStatus
from app.core.models.claims import ClaimAdjudicationRequest, ClaimLineItem, ClaimLineItem as LineItem
from app.core.models.encounter import EncounterNormalizeRequest
from app.core.models.observation import ObservationCreate
from app.core.models.prior_auth import PriorAuthEvaluateRequest
from app.core.models.provider import ProviderValidationRequest
from app.core.models.reporting import ReportingRequest
from app.core.models.tpl import TPLCheckRequest
from app.core.models.payment_integrity import PaymentIntegrityRequest
from app.core.models.eligibility import Eligibility270Request, Enrollment834Request
from app.main import app
from app.services.appeals_service import appeals_service
from app.services.care_management_service import care_management_service
from app.services.case_service import CaseService
from app.services.claims_adjudication_service import claims_adjudication_service
from app.services.encounter_normalization_service import encounter_normalization_service
from app.services.eligibility_service import eligibility_service
from app.services.hl7_adt_service import hl7_adt_service
from app.services.observation_service import build_observation_payload
from app.services.payment_integrity_service import payment_integrity_service
from app.services.provider_validation_service import provider_validation_service
from app.services.reporting_service import ReportingService, _is_audit_exception
from app.services.tpl_service import tpl_service
from app.services.webhook_service import (
    WebhookValidationError,
    parse_observation_event,
    validate_webhook_secret,
)
from app.state_machine.case_state import InvalidTransitionError, validate_transition
from app.ai.agent import CaseReviewResult


SAMPLE_ADT = (
    "MSH|^~\\&|ER|HOSP|CMS|FAC|20260808120000||ADT^A01|MSG100|P|2.5\r"
    "PID|1||P1002^^^MRN||MARTINEZ^ROBERT||19650612|M\r"
)


# --- Capability 01 -----------------------------------------------------------------


def test_sc01_cap01_270_active_eligibility():
    result = eligibility_service.validate_270(
        Eligibility270Request(member_id="M1001", payer_id="PAYER01")
    )
    assert result.eligibility_status == "active"
    assert "ST*271" in (result.x12_271_mock or "")


def test_sc02_cap01_834_rejected_enrollment():
    result = eligibility_service.validate_834(
        Enrollment834Request(
            member_id="INVALID-M1001",
            payer_id="PAYER01",
            plan_id="PLAN-GOLD",
            coverage_start_date=date(2026, 1, 1),
            subscriber_first_name="Jane",
            subscriber_last_name="Doe",
        )
    )
    assert result.validation_status == "rejected"
    assert result.rejection_reasons


def test_sc03_cap01_270_unknown_missing_fields():
    result = eligibility_service.validate_270(
        Eligibility270Request(member_id="", payer_id="")
    )
    assert result.eligibility_status == "unknown"
    assert result.validation_notes


# --- Capability 02 -----------------------------------------------------------------


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_sc04_cap02_claim_approved(mock_graph):
    mock_graph.return_value = _claims_graph(within_limits=True, duplicates=False)
    result = claims_adjudication_service.adjudicate(_sample_claim(billed=120.0))
    assert result.adjudication_status == "approved"


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_sc05_cap02_duplicate_claim_denied(mock_graph):
    mock_graph.return_value = _claims_graph(
        within_limits=True,
        duplicates=True,
        duplicate_id="CLM-1001",
    )
    result = claims_adjudication_service.adjudicate(_sample_claim(claim_id="CLM-NEW"))
    assert result.adjudication_status == "denied"
    assert result.duplicate_detected


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_sc06_cap02_pricing_partial_adjustment(mock_graph):
    mock_graph.return_value = _claims_graph(pricing_status="billed_exceeds_contract", duplicates=False)
    result = claims_adjudication_service.adjudicate(_sample_claim(billed=150.0))
    assert result.adjudication_status == "partial"
    assert result.line_adjudications[0].status == "adjusted"


# --- Capability 03 -----------------------------------------------------------------


def test_sc07_cap03_adt_er_admission_accepted():
    result = hl7_adt_service.ingest_adt(SAMPLE_ADT)
    assert result.processing_status == "accepted"
    assert result.patient_id == "P1002"


def test_sc08_cap03_adt_rejects_non_adt_message():
    result = hl7_adt_service.ingest_adt(
        "MSH|^~\\&|APP|FAC|REC|FAC|20260808120000||ORM^O01|X|P|2.5"
    )
    assert result.processing_status == "rejected"


# --- Capability 04 -----------------------------------------------------------------


def test_sc09_cap04_provider_active_and_compliant():
    result = provider_validation_service.validate_provider(
        ProviderValidationRequest(npi="1234567890", tax_id="12-3456789")
    )
    assert result.network_status == "active"
    assert result.credentialing_status == "compliant"


def test_sc10_cap04_provider_not_in_directory():
    result = provider_validation_service.validate_provider(
        ProviderValidationRequest(npi="0000000000")
    )
    assert result.network_status == "not_found"


# --- Capability 05 -----------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.prior_auth_service.audit_case_ai_review", new_callable=AsyncMock)
@patch("app.services.prior_auth_service.audit_case_transition", new_callable=AsyncMock)
@patch("app.services.prior_auth_service.audit_case_created", new_callable=AsyncMock)
@patch("app.services.prior_auth_service.case_service.run_ai_review", new_callable=AsyncMock)
@patch("app.services.prior_auth_service.case_service.transition")
@patch("app.services.prior_auth_service.case_service.create_case", new_callable=AsyncMock)
async def test_sc11_cap05_prior_auth_spawns_ai_review_case(
    mock_create, mock_transition, mock_review, mock_audit_created, mock_audit_transition, mock_audit_review
):
    from app.services.prior_auth_service import prior_auth_service

    case = Case(patient_id="P1002", title="PA", description="test")
    case.status = CaseStatus.PENDING_APPROVAL
    case.ai_summary = "Recommend approve with care management."
    mock_create.return_value = case
    mock_review.return_value = case

    result = await prior_auth_service.evaluate(
        PriorAuthEvaluateRequest(
            patient_id="P1002",
            member_id="M1002",
            clinical_query="Is there risk of chronic disease progression?",
        )
    )

    assert result.awaiting_human_approval is True
    assert result.status == "Pending_Approval"
    mock_transition.assert_called_once()
    mock_audit_created.assert_awaited_once()
    mock_audit_transition.assert_awaited_once()
    mock_audit_review.assert_awaited_once()


# --- Capability 06 -----------------------------------------------------------------


def test_sc12_cap06_appeals_draft_detects_multi_system_risk():
    case = Case(
        patient_id="P1002",
        title="Appeal case",
        description="test",
        status=CaseStatus.PENDING_APPROVAL,
        ai_summary="Diabetes progression with hypertension and creatinine elevation suggest multi-system risk.",
    )
    case_service = CaseService()
    case_service._cases[case.id] = case

    with patch("app.services.appeals_service.case_service", case_service):
        result = appeals_service.draft_recommendation(AppealDraftRequest(case_id=case.id))

    assert result.multi_system_risk_detected is True
    assert result.audit_trace_ready is True
    assert "APPEALS" in result.draft_summary


def test_sc13_cap06_appeals_missing_case_raises():
    with pytest.raises(KeyError):
        appeals_service.draft_recommendation(AppealDraftRequest(case_id=uuid4()))


# --- Capability 07 -----------------------------------------------------------------


@patch("app.services.care_management_service.get_neo4j_graph")
def test_sc14_cap07_care_gap_analytics_high_risk_member(mock_graph):
    mock_graph.return_value = MagicMock(
        calculate_comorbidity_risk_scores=MagicMock(
            return_value=[
                {
                    "member_id": "M1002",
                    "member_name": "Robert Martinez",
                    "conditions": ["Type 2 Diabetes Mellitus", "Hypertension"],
                    "comorbidity_risk_score": 10,
                }
            ]
        ),
        find_care_gaps=MagicMock(
            return_value=[
                {
                    "member_id": "M1002",
                    "measure_id": "HEDIS_A1C",
                    "measure_name": "Annual A1C",
                    "related_condition": "Type 2 Diabetes Mellitus",
                    "priority": "high",
                    "gap_status": "open",
                    "days_overdue": 365,
                }
            ]
        ),
    )
    result = care_management_service.analyze_care_gaps(
        CareGapAnalyticsRequest(member_id="M1002")
    )
    assert result.comorbidity_risks[0].risk_level == "critical"
    assert result.high_priority_gap_count == 1


@patch("app.services.care_management_service.get_neo4j_graph")
def test_sc15_cap07_care_gaps_all_members(mock_graph):
    mock_graph.return_value = MagicMock(
        calculate_comorbidity_risk_scores=MagicMock(return_value=[]),
        find_care_gaps=MagicMock(return_value=[]),
    )
    result = care_management_service.analyze_care_gaps(
        CareGapAnalyticsRequest(include_all_members=True)
    )
    assert result.member_count == 0


# --- Capability 08 -----------------------------------------------------------------


def test_sc16_cap08_encounter_cms_ready():
    result = encounter_normalization_service.normalize(
        EncounterNormalizeRequest(
            member_id="M1002",
            patient_id="P1002",
            diagnosis_codes=["E11", "I10"],
            procedure_codes=["99285", "80053"],
        )
    )
    assert result.cms_ready is True
    assert len(result.normalized_diagnoses) == 2


def test_sc17_cap08_encounter_incomplete_without_procedures():
    result = encounter_normalization_service.normalize(
        EncounterNormalizeRequest(
            member_id="M1002",
            patient_id="P1002",
            diagnosis_codes=["E11"],
            procedure_codes=[],
        )
    )
    assert result.cms_ready is False


# --- Capability 09 -----------------------------------------------------------------


def test_sc18_cap09_tpl_primary_payer_confirmed():
    result = tpl_service.check_tpl(
        TPLCheckRequest(member_id="M1002", payer_id="PAYER01")
    )
    assert result.primary_payer_status == "confirmed"


def test_sc19_cap09_tpl_subrogation_review():
    result = tpl_service.check_tpl(
        TPLCheckRequest(member_id="M1002SUB", payer_id="PAYER01", accident_related=True)
    )
    assert result.primary_payer_status == "subrogation_review"
    assert result.tpl_targets


# --- Capability 10 -----------------------------------------------------------------


@patch("app.services.payment_integrity_service.get_neo4j_graph")
def test_sc20_cap10_payment_integrity_anomalies(mock_graph):
    mock_graph.return_value = MagicMock(
        find_duplicate_payments=MagicMock(return_value=[{"anomaly_type": "duplicate_claim_payment", "member_id": "M1001", "claim_id": "CLM-1", "payment_ids": ["P1", "P2"], "total_amount": 250.0, "payment_date": "2026-08-07", "severity": "high"}]),
        find_clinical_gap_payment_flags=MagicMock(return_value=[]),
    )
    result = payment_integrity_service.detect_anomalies(
        PaymentIntegrityRequest(member_id="M1001")
    )
    assert result.anomaly_count == 1


# --- Capability 11 -----------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.services.reporting_service.fetch_audit_logs_since", new_callable=AsyncMock)
async def test_sc21_cap11_scorecard_service(mock_fetch):
    base = datetime.utcnow()
    mock_fetch.return_value = [
        _audit("case.created", "Case", "c1", base),
        _audit("case.human_approval", "Case", "c1", base + timedelta(hours=2), {"approved": True}),
        _audit("capability05.prior_auth_evaluated", "Case", "c2", base, {}),
    ]
    result = await ReportingService().build_balanced_scorecard(ReportingRequest(lookback_days=7))
    assert result.audit_exceptions.total_events == 3
    assert result.model_tracking.ai_review_count >= 1


@pytest.mark.asyncio
@patch("app.api.routes.capabilities.schedule_audit_log")
@patch("app.services.reporting_service.fetch_audit_logs_since", new_callable=AsyncMock)
async def test_sc22_cap11_scorecard_route_get(mock_fetch, _mock_audit):
    mock_fetch.return_value = []
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities/11/reporting/scorecard?lookback_days=7")
    assert response.status_code == 200
    assert "cycle_times" in response.json()


# --- Case workflow -----------------------------------------------------------------


def test_sc23_case_state_machine_enforces_valid_transitions():
    validate_transition(CaseStatus.PENDING, CaseStatus.AI_REVIEW)
    validate_transition(CaseStatus.AI_REVIEW, CaseStatus.PENDING_APPROVAL)
    with pytest.raises(InvalidTransitionError):
        validate_transition(CaseStatus.PENDING, CaseStatus.APPROVED)


@pytest.mark.asyncio
@patch("app.services.case_service.run_case_review", new_callable=AsyncMock)
async def test_sc24_case_api_create_transition_and_review(mock_run_review):
    case = Case(patient_id="P1002", title="Workflow test", description="desc")
    case.status = CaseStatus.PENDING_APPROVAL
    case.ai_summary = "Summary"
    mock_run_review.return_value = CaseReviewResult(
        summary="Summary",
        awaiting_approval=True,
    )

    service = CaseService()
    with patch.object(service, "_fhir") as mock_fhir:
        mock_fhir.get_patient = AsyncMock(return_value=None)
        mock_fhir.search_observations = AsyncMock(return_value=[])
        created = await service.create_case(CaseCreate(patient_id="P1002", title="Workflow test"))
        service.transition(created.id, CaseStatus.AI_REVIEW)
        reviewed = await service.run_ai_review(created.id, "Clinical query")

    assert reviewed.status == CaseStatus.PENDING_APPROVAL
    assert reviewed.ai_summary == "Summary"


# --- Cross-cutting: webhooks, agent, UI ------------------------------------------------


def test_sc25_webhooks_observations_agent_and_ui_routes():
    with patch("app.services.webhook_service.settings") as mock_settings:
        mock_settings.webhook_secret = "secret"
        validate_webhook_secret("secret")
        with pytest.raises(WebhookValidationError):
            validate_webhook_secret("wrong")

    payload = build_observation_payload(
        "P1002",
        ObservationCreate(
            loinc_code="2339-0",
            display="Glucose",
            value=280,
            unit="mg/dL",
        ),
    )
    assert payload["subject"]["reference"] == "Patient/P1002"
    obs, patient_id = parse_observation_event(
        {
            "resourceType": "Observation",
            "status": "final",
            "code": {"text": "Glucose"},
            "subject": {"reference": "Patient/P1002"},
        }
    )
    assert patient_id == "P1002"

    case = Case(patient_id="P1002", title="Ctx", description="High glucose")
    context = build_case_context(case)
    assert "P1002" in context
    claim_ctx = build_claim_context(
        ClaimReviewContext(
            claim_id="CLM-1",
            member_id="M1002",
            payer_id="PAYER01",
            service_date="2026-08-08",
            line_items=[LineItem(procedure_code="80053", billed_amount=45.0)],
        )
    )
    assert "80053" in claim_ctx
    assert ReviewMode.CLAIMS_ADJUDICATION.value == "claims_adjudication"

    is_exc, cat = _is_audit_exception(
        _audit("capability07.care_gaps_analyzed", "CareGap", "M1002", datetime.utcnow(), {"high_priority_gap_count": 2})
    )
    assert is_exc and cat == "care_gap_high_priority"


@pytest.mark.asyncio
async def test_sc25_ui_routes_available():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for path in ["/health", "/dashboard", "/demo", "/demo/explorer", "/"]:
            response = await client.get(path)
            assert response.status_code == 200


# --- helpers ---------------------------------------------------------------------


def _sample_claim(*, claim_id: str = "CLM-TEST", billed: float = 125.0) -> ClaimAdjudicationRequest:
    return ClaimAdjudicationRequest(
        claim_id=claim_id,
        member_id="M1001",
        payer_id="PAYER01",
        service_date=date(2026, 8, 8),
        line_items=[ClaimLineItem(procedure_code="99213", billed_amount=billed)],
    )


def _claims_graph(
    *,
    within_limits: bool = True,
    pricing_status: str = "within_limits",
    duplicates: bool = False,
    duplicate_id: str = "CLM-1001",
) -> MagicMock:
    graph = MagicMock()
    graph.check_claim_pricing_rules.return_value = [
        {
            "procedure_code": "99213",
            "allowed_amount": 125.0,
            "pricing_status": pricing_status if not within_limits else "within_limits",
            "billed_amount": 125.0,
            "units": 1,
        }
    ]
    graph.check_duplicate_claims.return_value = (
        [
            {
                "duplicate_claim_id": duplicate_id,
                "service_date": "2026-08-08",
                "procedure_code": "99213",
                "units": 1,
                "amount": 125.0,
            }
        ]
        if duplicates
        else []
    )
    return graph


def _audit(action, entity_type, entity_id, timestamp, details=None):
    return {
        "timestamp": timestamp,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
    }
