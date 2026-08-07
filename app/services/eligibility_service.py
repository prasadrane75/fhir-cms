from datetime import date
from uuid import uuid4

from app.core.models.eligibility import (
    Eligibility270Request,
    Eligibility271Response,
    Enrollment834Request,
    Enrollment834Response,
)


def _format_x12_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _build_mock_271(request: Eligibility270Request, response: Eligibility271Response) -> str:
    status_code = {"active": "1", "inactive": "6", "unknown": "V"}.get(response.eligibility_status, "V")
    service_date = _format_x12_date(request.service_date or date.today())
    return (
        f"ISA*00*          *00*          *ZZ*{request.payer_id:<15}*ZZ*RECEIVER       "
        f"*260807*1200*^*00501*000000001*0*P*:~"
        f"GS*HB*{request.payer_id}*RECEIVER*260807*1200*1*X*005010X279A1~"
        f"ST*271*0001*005010X279A1~"
        f"BHT*0022*11*{response.transaction_id.hex[:12]}*260807*1200~"
        f"HL*1**20*1~"
        f"NM1*PR*2*{request.payer_id}*****PI*{request.payer_id}~"
        f"HL*2*1*22*0~"
        f"NM1*1P*2*PROVIDER*****XX*{request.provider_npi or '0000000000'}~"
        f"HL*3*2*23*0~"
        f"NM1*IL*1*{request.subscriber_last_name or 'MEMBER'}*{request.subscriber_first_name or 'UNKNOWN'}~"
        f"REF*0F*{request.member_id}~"
        f"EB*{status_code}**30**{response.plan_name or 'UNKNOWN PLAN'}~"
        f"DTP*291*D8*{service_date}~"
        f"SE*10*0001~"
        f"GE*1*1~"
        f"IEA*1*000000001~"
    )


def _build_mock_999(request: Enrollment834Request, response: Enrollment834Response) -> str:
    ack_code = "A" if response.validation_status == "accepted" else "R"
    return (
        f"ISA*00*          *00*          *ZZ*{request.payer_id:<15}*ZZ*RECEIVER       "
        f"*260807*1200*^*00501*000000002*0*P*:~"
        f"GS*FA*{request.payer_id}*RECEIVER*260807*1200*2*X*005010X231A1~"
        f"ST*999*0001*005010X231A1~"
        f"AK1*BE*{response.transaction_id.hex[:12]}~"
        f"AK2*834*0001~"
        f"IK5*{ack_code}~"
        f"SE*4*0001~"
        f"GE*1*2~"
        f"IEA*1*000000002~"
    )


class EligibilityService:
    def validate_270(self, request: Eligibility270Request) -> Eligibility271Response:
        notes: list[str] = []
        if not request.member_id.strip():
            notes.append("member_id is required")
        if not request.payer_id.strip():
            notes.append("payer_id is required")

        member_id = request.member_id.strip()
        payer_id = request.payer_id.strip()

        if notes:
            response = Eligibility271Response(
                member_id=member_id or "unknown",
                payer_id=payer_id or "unknown",
                eligibility_status="unknown",
                validation_notes=notes,
            )
            response.x12_271_mock = _build_mock_271(request, response)
            return response

        if member_id.endswith("9"):
            response = Eligibility271Response(
                member_id=member_id,
                payer_id=payer_id,
                eligibility_status="inactive",
                plan_name="Mock PPO Gold",
                group_number="GRP-1000",
                effective_date=date(2024, 1, 1),
                termination_date=date(2025, 12, 31),
                validation_notes=["Member coverage is inactive in mock rules (member_id ends with 9)."],
            )
        else:
            response = Eligibility271Response(
                member_id=member_id,
                payer_id=payer_id,
                eligibility_status="active",
                coverage_level="individual",
                plan_name="Mock PPO Gold",
                group_number="GRP-1000",
                effective_date=date(2024, 1, 1),
                validation_notes=["Eligibility confirmed by mock 270/271 validator."],
            )

        response.x12_271_mock = _build_mock_271(request, response)
        return response

    def validate_834(self, request: Enrollment834Request) -> Enrollment834Response:
        rejection_reasons: list[str] = []

        if not request.member_id.strip():
            rejection_reasons.append("member_id is required")
        if not request.payer_id.strip():
            rejection_reasons.append("payer_id is required")
        if not request.plan_id.strip():
            rejection_reasons.append("plan_id is required")
        if not request.subscriber_first_name.strip():
            rejection_reasons.append("subscriber_first_name is required")
        if not request.subscriber_last_name.strip():
            rejection_reasons.append("subscriber_last_name is required")
        if request.coverage_end_date and request.coverage_end_date < request.coverage_start_date:
            rejection_reasons.append("coverage_end_date must be on or after coverage_start_date")
        if request.member_id.strip().upper().startswith("INVALID"):
            rejection_reasons.append("member_id marked invalid for mock enrollment rejection")

        validation_status = "rejected" if rejection_reasons else "accepted"
        response = Enrollment834Response(
            transaction_id=uuid4(),
            member_id=request.member_id.strip() or "unknown",
            payer_id=request.payer_id.strip() or "unknown",
            validation_status=validation_status,
            rejection_reasons=rejection_reasons,
        )
        response.x12_999_mock = _build_mock_999(request, response)
        return response


eligibility_service = EligibilityService()
