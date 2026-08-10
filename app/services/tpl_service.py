from uuid import uuid4

from app.core.models.tpl import TPLCheckRequest, TPLCheckResponse


class TPLService:
    def check_tpl(self, request: TPLCheckRequest) -> TPLCheckResponse:
        notes: list[str] = []
        targets: list[str] = []

        if request.accident_related:
            targets.append("automobile_liability_carrier")
            notes.append("Accident-related indicator requires subrogation review.")

        if request.other_coverage_indicator:
            targets.append("secondary_commercial_plan")
            notes.append("Other coverage indicator found; verify coordination of benefits.")

        if request.member_id.upper().endswith("SUB"):
            targets.append("legacy_workers_comp")
            primary_status = "subrogation_review"
            notes.append("Member flagged for legacy workers compensation subrogation.")
        elif targets:
            primary_status = "other_coverage_found"
            notes.append("Additional coverage targets identified before disbursement.")
        else:
            primary_status = "confirmed"
            notes.append("No conflicting third-party liability targets detected.")

        return TPLCheckResponse(
            transaction_id=uuid4(),
            member_id=request.member_id,
            primary_payer_status=primary_status,
            tpl_targets=targets,
            validation_notes=notes,
        )


tpl_service = TPLService()
