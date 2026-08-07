"""Tests for Capability 01 (834/270) and Capability 03 (HL7 ADT)."""

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.eligibility_service import eligibility_service
from app.services.hl7_adt_service import hl7_adt_service
from app.core.models.eligibility import Eligibility270Request, Enrollment834Request


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
