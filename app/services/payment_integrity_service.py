from uuid import uuid4

from app.ai.tools.neo4j_tool import get_neo4j_graph
from app.core.models.payment_integrity import (
    ClinicalGapPaymentFlag,
    DuplicatePaymentAnomaly,
    PaymentIntegrityRequest,
    PaymentIntegrityResponse,
)


class PaymentIntegrityService:
    def detect_anomalies(self, request: PaymentIntegrityRequest) -> PaymentIntegrityResponse:
        notes: list[str] = []
        graph = get_neo4j_graph()

        member_id = request.member_id.strip() if request.member_id else None
        payer_id = request.payer_id.strip() if request.payer_id else None

        duplicate_rows = graph.find_duplicate_payments(
            member_id=member_id,
            payer_id=payer_id,
            lookback_days=request.lookback_days,
        )
        gap_flag_rows = graph.find_clinical_gap_payment_flags(
            member_id=member_id,
            payer_id=payer_id,
            lookback_days=request.lookback_days,
        )

        duplicate_payments = [
            DuplicatePaymentAnomaly(
                anomaly_type=row["anomaly_type"],
                member_id=row["member_id"],
                claim_id=row.get("claim_id"),
                payment_ids=row.get("payment_ids") or [],
                total_amount=float(row.get("total_amount") or 0),
                payment_date=row.get("payment_date"),
                severity=row.get("severity") or "medium",
            )
            for row in duplicate_rows
        ]

        clinical_gap_flags = [
            ClinicalGapPaymentFlag(
                member_id=row["member_id"],
                member_name=row.get("member_name"),
                measure_id=row["measure_id"],
                measure_name=row["measure_name"],
                payment_id=row["payment_id"],
                payment_amount=float(row.get("payment_amount") or 0),
                payment_date=row.get("payment_date"),
                severity=row.get("severity") or "high",
            )
            for row in gap_flag_rows
        ]

        anomaly_count = len(duplicate_payments) + len(clinical_gap_flags)
        if anomaly_count == 0:
            notes.append("No payment integrity anomalies detected in the lookback window.")
        else:
            notes.append(
                f"Detected {len(duplicate_payments)} duplicate payment anomaly(ies) and "
                f"{len(clinical_gap_flags)} high-risk clinical gap flag(s)."
            )

        return PaymentIntegrityResponse(
            transaction_id=uuid4(),
            duplicate_payments=duplicate_payments,
            clinical_gap_flags=clinical_gap_flags,
            anomaly_count=anomaly_count,
            validation_notes=notes,
        )


payment_integrity_service = PaymentIntegrityService()
