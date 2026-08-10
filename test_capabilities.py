"""Tests for Capability 01 (834/270), Capability 02 (claims adjudication),
Capability 03 (HL7 ADT), Capability 07 (care gaps), and Capability 10 (payment integrity)."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.care_management_service import care_management_service
from app.services.claims_adjudication_service import claims_adjudication_service
from app.services.eligibility_service import eligibility_service
from app.services.hl7_adt_service import hl7_adt_service
from app.services.payment_integrity_service import payment_integrity_service
from app.core.models.care_management import CareGapAnalyticsRequest
from app.core.models.claims import ClaimAdjudicationRequest, ClaimLineItem
from app.core.models.eligibility import Eligibility270Request, Enrollment834Request
from app.core.models.payment_integrity import PaymentIntegrityRequest


SAMPLE_ADT_A01 = (
    "MSH|^~\\&|SENDING_APP|FACILITY|RECEIVING|FACILITY|20260807120000||ADT^A01|MSG001|P|2.5\r"
    "EVN|A01|20260807120000\r"
    "PID|1||12345^^^MRN||DOE^JANE^M||19850315|F\r"
    "PV1|1|I|ICU^101^01||||1234567890^SMITH^JOHN"
)


def test_validate_270_active_member():
    request = Eligibility270Request(
        member_id="M1001",
        payer_id="PAYER01",
        provider_npi="1234567890",
        service_date=date(2026, 8, 7),
    )
    result = eligibility_service.validate_270(request)

    assert result.eligibility_status == "active"
    assert result.plan_name == "Mock PPO Gold"
    assert result.x12_271_mock is not None
    assert "ST*271" in result.x12_271_mock


def test_validate_270_inactive_member():
    request = Eligibility270Request(member_id="M1009", payer_id="PAYER01")
    result = eligibility_service.validate_270(request)

    assert result.eligibility_status == "inactive"
    assert result.termination_date is not None


def test_validate_834_accepted():
    request = Enrollment834Request(
        member_id="M1001",
        payer_id="PAYER01",
        plan_id="PLAN-GOLD",
        coverage_start_date=date(2026, 1, 1),
        subscriber_first_name="Jane",
        subscriber_last_name="Doe",
    )
    result = eligibility_service.validate_834(request)

    assert result.validation_status == "accepted"
    assert result.rejection_reasons == []
    assert result.x12_999_mock is not None
    assert "ST*999" in result.x12_999_mock


def test_validate_834_rejected():
    request = Enrollment834Request(
        member_id="INVALID-M1001",
        payer_id="PAYER01",
        plan_id="PLAN-GOLD",
        coverage_start_date=date(2026, 1, 1),
        subscriber_first_name="Jane",
        subscriber_last_name="Doe",
    )
    result = eligibility_service.validate_834(request)

    assert result.validation_status == "rejected"
    assert result.rejection_reasons


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_adjudicate_claim_approved(mock_get_graph):
    graph = MagicMock()
    mock_get_graph.return_value = graph
    graph.check_claim_pricing_rules.return_value = [
        {
            "procedure_code": "99213",
            "description": "Office visit",
            "allowed_amount": 125.0,
            "max_units": 1,
            "billed_amount": 120.0,
            "units": 1,
            "pricing_status": "within_limits",
        }
    ]
    graph.check_duplicate_claims.return_value = []

    request = ClaimAdjudicationRequest(
        claim_id="CLM-2001",
        member_id="M1001",
        payer_id="PAYER01",
        service_date=date(2026, 8, 7),
        line_items=[ClaimLineItem(procedure_code="99213", billed_amount=120.0)],
    )
    result = claims_adjudication_service.adjudicate(request)

    assert result.adjudication_status == "approved"
    assert result.duplicate_detected is False
    assert result.line_adjudications[0].paid_amount == 120.0
    assert result.x12_835_mock is not None
    assert "ST*835" in result.x12_835_mock


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_adjudicate_claim_duplicate_denied(mock_get_graph):
    graph = MagicMock()
    mock_get_graph.return_value = graph
    graph.check_claim_pricing_rules.return_value = [
        {
            "procedure_code": "99213",
            "description": "Office visit",
            "allowed_amount": 125.0,
            "max_units": 1,
            "billed_amount": 125.0,
            "units": 1,
            "pricing_status": "within_limits",
        }
    ]
    graph.check_duplicate_claims.return_value = [
        {
            "duplicate_claim_id": "CLM-1001",
            "service_date": "2026-08-01",
            "status": "paid",
            "procedure_code": "99213",
            "units": 1,
            "amount": 125.0,
        }
    ]

    request = ClaimAdjudicationRequest(
        claim_id="CLM-2002",
        member_id="M1001",
        payer_id="PAYER01",
        service_date=date(2026, 8, 1),
        line_items=[ClaimLineItem(procedure_code="99213", billed_amount=125.0)],
    )
    result = claims_adjudication_service.adjudicate(request)

    assert result.adjudication_status == "denied"
    assert result.duplicate_detected is True
    assert "CLM-1001" in result.duplicate_claim_ids
    assert result.line_adjudications[0].status == "denied"
    assert "DUPLICATE_CLAIM" in result.line_adjudications[0].reason_codes


@patch("app.services.claims_adjudication_service.get_neo4j_graph")
def test_adjudicate_claim_pricing_adjusted(mock_get_graph):
    graph = MagicMock()
    mock_get_graph.return_value = graph
    graph.check_claim_pricing_rules.return_value = [
        {
            "procedure_code": "99213",
            "description": "Office visit",
            "allowed_amount": 125.0,
            "max_units": 1,
            "billed_amount": 150.0,
            "units": 1,
            "pricing_status": "billed_exceeds_contract",
        }
    ]
    graph.check_duplicate_claims.return_value = []

    request = ClaimAdjudicationRequest(
        claim_id="CLM-2003",
        member_id="M1001",
        payer_id="PAYER01",
        service_date=date(2026, 8, 7),
        line_items=[ClaimLineItem(procedure_code="99213", billed_amount=150.0)],
    )
    result = claims_adjudication_service.adjudicate(request)

    assert result.adjudication_status == "partial"
    assert result.line_adjudications[0].status == "adjusted"
    assert result.line_adjudications[0].paid_amount == 125.0


@patch("app.services.care_management_service.get_neo4j_graph")
def test_analyze_care_gaps_member(mock_get_graph):
    graph = MagicMock()
    mock_get_graph.return_value = graph
    graph.calculate_comorbidity_risk_scores.return_value = [
        {
            "member_id": "M1001",
            "member_name": "Jane Doe",
            "conditions": ["Type 2 Diabetes Mellitus", "Hypertension"],
            "comorbidity_risk_score": 8,
        }
    ]
    graph.find_care_gaps.return_value = [
        {
            "member_id": "M1001",
            "measure_id": "HEDIS_BP",
            "measure_name": "Blood Pressure Control",
            "related_condition": "Hypertension",
            "priority": "medium",
            "gap_status": "open",
            "days_overdue": 180,
        }
    ]

    result = care_management_service.analyze_care_gaps(
        CareGapAnalyticsRequest(member_id="M1001")
    )

    assert result.member_count == 1
    assert result.comorbidity_risks[0].risk_level == "high"
    assert len(result.care_gaps) == 1
    assert result.care_gaps[0].measure_id == "HEDIS_BP"


@patch("app.services.payment_integrity_service.get_neo4j_graph")
def test_detect_payment_anomalies(mock_get_graph):
    graph = MagicMock()
    mock_get_graph.return_value = graph
    graph.find_duplicate_payments.return_value = [
        {
            "anomaly_type": "duplicate_claim_payment",
            "member_id": "M1001",
            "claim_id": "CLM-1001",
            "payment_ids": ["PAY-1001", "PAY-1002"],
            "total_amount": 250.0,
            "payment_date": "2026-08-06",
            "severity": "high",
        }
    ]
    graph.find_clinical_gap_payment_flags.return_value = [
        {
            "member_id": "M1001",
            "member_name": "Jane Doe",
            "measure_id": "HEDIS_BP",
            "measure_name": "Blood Pressure Control",
            "payment_id": "PAY-1003",
            "payment_amount": 45.0,
            "payment_date": "2026-08-07",
            "flag_type": "high_risk_gap_with_payment",
            "severity": "high",
        }
    ]

    result = payment_integrity_service.detect_anomalies(
        PaymentIntegrityRequest(member_id="M1001", payer_id="PAYER01")
    )

    assert result.anomaly_count == 2
    assert result.duplicate_payments[0].anomaly_type == "duplicate_claim_payment"
    assert result.clinical_gap_flags[0].measure_id == "HEDIS_BP"


def test_ingest_adt_a01():
    result = hl7_adt_service.ingest_adt(SAMPLE_ADT_A01)

    assert result.processing_status == "accepted"
    assert result.message_control_id == "MSG001"
    assert result.event_code == "A01"
    assert result.patient_id == "12345"
    assert result.patient_name == "JANE M DOE"


def test_ingest_adt_rejects_non_adt():
    result = hl7_adt_service.ingest_adt(
        "MSH|^~\\&|APP|FAC|REC|FAC|20260807120000||ORM^O01|MSG002|P|2.5\r"
        "PID|1||99999^^^MRN||SMITH^BOB"
    )

    assert result.processing_status == "rejected"
    assert "Unsupported message type" in (result.rejection_reason or "")


@pytest.mark.asyncio
async def test_capability_routes_return_expected_status_codes():
    with (
        patch("app.api.routes.capabilities.schedule_audit_log"),
        patch("app.services.claims_adjudication_service.get_neo4j_graph") as mock_claims_graph,
        patch("app.services.care_management_service.get_neo4j_graph") as mock_care_graph,
        patch("app.services.payment_integrity_service.get_neo4j_graph") as mock_payment_graph,
    ):
        graph = MagicMock()
        mock_claims_graph.return_value = graph
        mock_care_graph.return_value = graph
        mock_payment_graph.return_value = graph
        graph.check_claim_pricing_rules.return_value = [
            {
                "procedure_code": "99213",
                "description": "Office visit",
                "allowed_amount": 125.0,
                "max_units": 1,
                "billed_amount": 120.0,
                "units": 1,
                "pricing_status": "within_limits",
            }
        ]
        graph.check_duplicate_claims.return_value = []
        graph.calculate_comorbidity_risk_scores.return_value = [
            {
                "member_id": "M1001",
                "member_name": "Jane Doe",
                "conditions": ["Type 2 Diabetes Mellitus"],
                "comorbidity_risk_score": 5,
            }
        ]
        graph.find_care_gaps.return_value = []
        graph.find_duplicate_payments.return_value = []
        graph.find_clinical_gap_payment_flags.return_value = []

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response_270 = await client.post(
                "/api/v1/capabilities/01/eligibility/270",
                json={
                    "member_id": "M1001",
                    "payer_id": "PAYER01",
                    "provider_npi": "1234567890",
                    "service_date": "2026-08-07",
                },
            )
            assert response_270.status_code == 200
            assert response_270.json()["eligibility_status"] == "active"

            response_834 = await client.post(
                "/api/v1/capabilities/01/eligibility/834",
                json={
                    "member_id": "M1001",
                    "payer_id": "PAYER01",
                    "plan_id": "PLAN-GOLD",
                    "coverage_start_date": "2026-01-01",
                    "subscriber_first_name": "Jane",
                    "subscriber_last_name": "Doe",
                },
            )
            assert response_834.status_code == 200
            assert response_834.json()["validation_status"] == "accepted"

            response_claim = await client.post(
                "/api/v1/capabilities/02/claims/adjudicate",
                json={
                    "claim_id": "CLM-2001",
                    "member_id": "M1001",
                    "payer_id": "PAYER01",
                    "service_date": "2026-08-07",
                    "line_items": [
                        {"procedure_code": "99213", "billed_amount": 120.0, "units": 1}
                    ],
                },
            )
            assert response_claim.status_code == 200
            assert response_claim.json()["adjudication_status"] == "approved"

            response_care_gaps = await client.post(
                "/api/v1/capabilities/07/care-gaps/analyze",
                json={"member_id": "M1001"},
            )
            assert response_care_gaps.status_code == 200
            assert response_care_gaps.json()["member_count"] == 1

            response_payment = await client.post(
                "/api/v1/capabilities/10/payment-integrity/detect",
                json={"member_id": "M1001", "payer_id": "PAYER01", "lookback_days": 90},
            )
            assert response_payment.status_code == 200
            assert response_payment.json()["anomaly_count"] == 0

            response_adt = await client.post(
                "/api/v1/capabilities/03/adt",
                content=SAMPLE_ADT_A01,
                headers={"Content-Type": "text/plain"},
            )
            assert response_adt.status_code == 202
            assert response_adt.json()["event_code"] == "A01"
            assert response_adt.json()["processing_status"] == "accepted"

            response_bad_adt = await client.post(
                "/api/v1/capabilities/03/adt",
                content="MSH|^~\\&|APP|FAC|REC|FAC|20260807120000||ORM^O01|MSG002|P|2.5",
                headers={"Content-Type": "text/plain"},
            )
            assert response_bad_adt.status_code == 202
            assert response_bad_adt.json()["processing_status"] == "rejected"
