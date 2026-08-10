from uuid import uuid4

from app.ai.tools.neo4j_tool import get_neo4j_graph
from app.core.models.care_management import (
    CareGap,
    CareGapAnalyticsRequest,
    CareGapAnalyticsResponse,
    ComorbidityRisk,
)


def _risk_level(score: float) -> str:
    if score >= 10:
        return "critical"
    if score >= 7:
        return "high"
    if score >= 4:
        return "moderate"
    return "low"


class CareManagementService:
    def analyze_care_gaps(self, request: CareGapAnalyticsRequest) -> CareGapAnalyticsResponse:
        notes: list[str] = []
        if not request.member_id and not request.include_all_members:
            notes.append("Provide member_id or set include_all_members=true.")

        member_filter = None if request.include_all_members and not request.member_id else request.member_id
        graph = get_neo4j_graph()

        risk_rows = graph.calculate_comorbidity_risk_scores(member_filter)
        gap_rows = graph.find_care_gaps(member_filter)

        comorbidity_risks = [
            ComorbidityRisk(
                member_id=row["member_id"],
                member_name=row.get("member_name"),
                conditions=[c for c in (row.get("conditions") or []) if c],
                comorbidity_risk_score=float(row.get("comorbidity_risk_score") or 0),
                risk_level=_risk_level(float(row.get("comorbidity_risk_score") or 0)),
            )
            for row in risk_rows
            if row.get("member_id")
        ]

        care_gaps = [
            CareGap(
                member_id=row["member_id"],
                measure_id=row["measure_id"],
                measure_name=row["measure_name"],
                related_condition=row["related_condition"],
                priority=row.get("priority") or "medium",
                gap_status=row.get("gap_status") or "open",
                days_overdue=int(row["days_overdue"]) if row.get("days_overdue") is not None else None,
            )
            for row in gap_rows
        ]

        if not comorbidity_risks and member_filter:
            notes.append(f"No member record found for member_id={member_filter}.")
        elif comorbidity_risks:
            notes.append(f"Analyzed {len(comorbidity_risks)} member(s) for comorbidity risk.")

        high_priority_gap_count = sum(1 for gap in care_gaps if gap.priority == "high")

        return CareGapAnalyticsResponse(
            transaction_id=uuid4(),
            member_count=len(comorbidity_risks),
            comorbidity_risks=comorbidity_risks,
            care_gaps=care_gaps,
            high_priority_gap_count=high_priority_gap_count,
            validation_notes=notes,
        )


care_management_service = CareManagementService()
