from datetime import date
from uuid import uuid4

from app.ai.tools.neo4j_tool import get_neo4j_graph
from app.core.models.claims import (
    ClaimAdjudicationRequest,
    ClaimAdjudicationResponse,
    ClaimLineAdjudication,
)


def _format_x12_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def _build_mock_835(request: ClaimAdjudicationRequest, response: ClaimAdjudicationResponse) -> str:
    status_code = {"approved": "1", "partial": "2", "denied": "4"}.get(response.adjudication_status, "4")
    paid_total = sum(line.paid_amount or 0 for line in response.line_adjudications)
    return (
        f"ISA*00*          *00*          *ZZ*{request.payer_id:<15}*ZZ*RECEIVER       "
        f"*260807*1200*^*00501*000000003*0*P*:~"
        f"GS*HP*{request.payer_id}*RECEIVER*260807*1200*3*X*005010X221A1~"
        f"ST*835*0001*005010X221A1~"
        f"BPR*I*{paid_total:.2f}*C*ACH*CTX*01*999999999*DA*1234567890**01*999999999*DA*0987654321*"
        f"{_format_x12_date(request.service_date)}~"
        f"TRN*1*{response.transaction_id.hex[:12]}*{request.payer_id}~"
        f"CLP*{request.claim_id}*{status_code}*"
        f"{sum(item.billed_amount for item in request.line_items):.2f}*"
        f"{paid_total:.2f}*"
        f"{request.member_id}~"
        f"SE*5*0001~"
        f"GE*1*3~"
        f"IEA*1*000000003~"
    )


class ClaimsAdjudicationService:
    def adjudicate(self, request: ClaimAdjudicationRequest) -> ClaimAdjudicationResponse:
        notes: list[str] = []
        if not request.claim_id.strip():
            notes.append("claim_id is required")
        if not request.member_id.strip():
            notes.append("member_id is required")
        if not request.payer_id.strip():
            notes.append("payer_id is required")
        if not request.line_items:
            notes.append("at least one line item is required")

        graph = get_neo4j_graph()
        line_payload = [
            {
                "procedure_code": item.procedure_code.strip(),
                "billed_amount": item.billed_amount,
                "units": item.units,
            }
            for item in request.line_items
        ]
        pricing_results = graph.check_claim_pricing_rules(request.payer_id.strip(), line_payload)
        procedure_codes = [item.procedure_code.strip() for item in request.line_items]
        duplicate_results = graph.check_duplicate_claims(
            request.member_id.strip(),
            request.claim_id.strip(),
            request.service_date.isoformat(),
            procedure_codes,
        )

        duplicate_claim_ids = sorted(
            {row["duplicate_claim_id"] for row in duplicate_results if row.get("duplicate_claim_id")}
        )
        duplicate_detected = bool(duplicate_claim_ids)

        line_adjudications: list[ClaimLineAdjudication] = []
        denied_lines = 0

        for item, pricing in zip(request.line_items, pricing_results, strict=False):
            reason_codes: list[str] = []
            status = "approved"
            allowed_amount = pricing.get("allowed_amount")
            paid_amount = item.billed_amount

            pricing_status = pricing.get("pricing_status")
            if pricing_status == "procedure_not_covered":
                status = "denied"
                reason_codes.append("PROC_NOT_COVERED")
                paid_amount = 0.0
            elif pricing_status == "units_exceed_max":
                status = "denied"
                reason_codes.append("UNITS_EXCEED_MAX")
                paid_amount = 0.0
            elif pricing_status == "billed_exceeds_contract":
                status = "adjusted"
                reason_codes.append("CONTRACT_RATE_APPLIED")
                paid_amount = float(allowed_amount or 0)
            elif allowed_amount is not None and item.billed_amount > allowed_amount:
                status = "adjusted"
                reason_codes.append("ALLOWED_AMOUNT_CAP")
                paid_amount = float(allowed_amount)

            if duplicate_detected:
                status = "denied"
                reason_codes.append("DUPLICATE_CLAIM")
                paid_amount = 0.0

            if status == "denied":
                denied_lines += 1

            line_adjudications.append(
                ClaimLineAdjudication(
                    procedure_code=item.procedure_code,
                    billed_amount=item.billed_amount,
                    allowed_amount=float(allowed_amount) if allowed_amount is not None else None,
                    paid_amount=paid_amount,
                    status=status,
                    reason_codes=reason_codes,
                )
            )

        if notes:
            adjudication_status = "denied"
        elif duplicate_detected:
            adjudication_status = "denied"
            notes.append(
                "Duplicate claim detected for member/date/procedure combination "
                f"({', '.join(duplicate_claim_ids)})."
            )
        elif denied_lines == len(line_adjudications):
            adjudication_status = "denied"
        elif denied_lines > 0 or any(line.status == "adjusted" for line in line_adjudications):
            adjudication_status = "partial"
        else:
            adjudication_status = "approved"
            notes.append("All line items passed pricing and duplicate checks.")

        response = ClaimAdjudicationResponse(
            transaction_id=uuid4(),
            claim_id=request.claim_id.strip(),
            member_id=request.member_id.strip(),
            payer_id=request.payer_id.strip(),
            adjudication_status=adjudication_status,
            line_adjudications=line_adjudications,
            duplicate_detected=duplicate_detected,
            duplicate_claim_ids=duplicate_claim_ids,
            validation_notes=notes,
        )
        response.x12_835_mock = _build_mock_835(request, response)
        return response


claims_adjudication_service = ClaimsAdjudicationService()
