from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean
from uuid import uuid4

from app.core.models.reporting import (
    ActionCount,
    ApprovalDenialMetrics,
    AuditExceptionMetrics,
    BalancedScorecardResponse,
    CycleTimeMetrics,
    ModelTrackingMetrics,
    ReportingRequest,
)
from app.services.audit import fetch_audit_logs_since


def _hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return (end - start).total_seconds() / 3600


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _is_audit_exception(log: dict) -> tuple[bool, str | None]:
    action = log.get("action") or ""
    details = log.get("details") or {}

    if action == "case.human_approval" and details.get("approved") is False:
        return True, "case_denied"

    if action == "capability01.eligibility_270_received":
        status = details.get("eligibility_status")
        if status in {"inactive", "unknown"}:
            return True, "eligibility_exception"

    if action == "capability01.eligibility_834_received":
        if details.get("validation_status") == "rejected":
            return True, "enrollment_rejected"

    if action == "capability02.claim_adjudicated":
        status = details.get("adjudication_status")
        if status in {"denied", "partial"} or details.get("duplicate_detected"):
            return True, "claim_adjudication_exception"

    if action == "capability03.adt_received":
        if details.get("processing_status") == "rejected":
            return True, "adt_rejected"

    if action == "capability07.care_gaps_analyzed":
        if details.get("high_priority_gap_count", 0) > 0:
            return True, "care_gap_high_priority"

    if action == "capability10.payment_integrity_detected":
        if details.get("anomaly_count", 0) > 0:
            return True, "payment_integrity_anomaly"

    return False, None


class ReportingService:
    async def build_balanced_scorecard(self, request: ReportingRequest) -> BalancedScorecardResponse:
        logs = await fetch_audit_logs_since(lookback_days=request.lookback_days)
        notes: list[str] = []

        if not logs:
            notes.append(f"No audit ledger entries found in the last {request.lookback_days} day(s).")

        cycle_times = self._aggregate_cycle_times(logs)
        approval_denial = self._aggregate_approval_denial(logs)
        audit_exceptions = self._aggregate_audit_exceptions(logs)
        model_tracking = self._aggregate_model_tracking(logs)

        if cycle_times.sample_size:
            notes.append(f"Computed cycle times from {cycle_times.sample_size} completed case workflow(s).")
        if approval_denial.approved_count + approval_denial.denied_count:
            notes.append(
                f"Human approval ratio: {approval_denial.approval_ratio or 0:.0%} approved "
                f"over {approval_denial.approved_count + approval_denial.denied_count} decision(s)."
            )

        return BalancedScorecardResponse(
            transaction_id=uuid4(),
            generated_at=datetime.utcnow(),
            lookback_days=request.lookback_days,
            cycle_times=cycle_times,
            approval_denial=approval_denial,
            audit_exceptions=audit_exceptions,
            model_tracking=model_tracking,
            validation_notes=notes,
        )

    def _aggregate_cycle_times(self, logs: list[dict]) -> CycleTimeMetrics:
        case_events: dict[str, list[dict]] = defaultdict(list)
        for log in logs:
            if log.get("entity_type") == "Case":
                case_events[log["entity_id"]].append(log)

        pending_to_ai: list[float] = []
        ai_review_durations: list[float] = []
        pending_approval_durations: list[float] = []
        total_cycles: list[float] = []
        completed_cases = 0

        for events in case_events.values():
            events.sort(key=lambda row: row["timestamp"])
            created_at = next(
                (row["timestamp"] for row in events if row["action"] == "case.created"),
                None,
            )
            ai_review_start = next(
                (
                    row["timestamp"]
                    for row in events
                    if row["action"] == "case.transition"
                    and (row.get("details") or {}).get("target_status") == "AI_Review"
                ),
                None,
            )
            if ai_review_start is None and created_at is not None:
                # Cap 05 / webhook paths transition immediately after create.
                ai_review_start = created_at
            ai_review_done = next(
                (row["timestamp"] for row in events if row["action"] == "case.ai_review"),
                None,
            )
            if ai_review_done is None:
                ai_review_done = next(
                    (
                        row["timestamp"]
                        for row in events
                        if row["action"] == "capability05.prior_auth_evaluated"
                    ),
                    None,
                )
            human_decision = next(
                (row["timestamp"] for row in events if row["action"] == "case.human_approval"),
                None,
            )

            if not human_decision:
                continue

            completed_cases += 1
            if created_at and ai_review_start:
                delta = _hours_between(created_at, ai_review_start)
                if delta is not None:
                    pending_to_ai.append(delta)
            if ai_review_start and ai_review_done:
                delta = _hours_between(ai_review_start, ai_review_done)
                if delta is not None:
                    ai_review_durations.append(delta)
            if ai_review_done and human_decision:
                delta = _hours_between(ai_review_done, human_decision)
                if delta is not None:
                    pending_approval_durations.append(delta)
            if created_at and human_decision:
                delta = _hours_between(created_at, human_decision)
                if delta is not None:
                    total_cycles.append(delta)

        return CycleTimeMetrics(
            avg_pending_to_ai_review_hours=_avg(pending_to_ai),
            avg_ai_review_hours=_avg(ai_review_durations),
            avg_pending_approval_hours=_avg(pending_approval_durations),
            avg_total_cycle_hours=_avg(total_cycles),
            sample_size=completed_cases,
        )

    def _aggregate_approval_denial(self, logs: list[dict]) -> ApprovalDenialMetrics:
        approvals = [log for log in logs if log.get("action") == "case.human_approval"]
        approved_count = sum(
            1 for log in approvals if (log.get("details") or {}).get("approved") is True
        )
        denied_count = sum(
            1 for log in approvals if (log.get("details") or {}).get("approved") is False
        )
        total = approved_count + denied_count
        approval_ratio = round(approved_count / total, 4) if total else None
        denial_ratio = round(denied_count / total, 4) if total else None
        return ApprovalDenialMetrics(
            approved_count=approved_count,
            denied_count=denied_count,
            approval_ratio=approval_ratio,
            denial_ratio=denial_ratio,
        )

    def _aggregate_audit_exceptions(self, logs: list[dict]) -> AuditExceptionMetrics:
        by_category: Counter[str] = Counter()
        exception_count = 0
        for log in logs:
            is_exception, category = _is_audit_exception(log)
            if is_exception and category:
                exception_count += 1
                by_category[category] += 1

        total_events = len(logs)
        exception_rate = round(exception_count / total_events, 4) if total_events else None
        return AuditExceptionMetrics(
            total_events=total_events,
            exception_count=exception_count,
            exception_rate=exception_rate,
            by_category=dict(by_category),
        )

    def _aggregate_model_tracking(self, logs: list[dict]) -> ModelTrackingMetrics:
        ai_reviews = [log for log in logs if log.get("action") == "case.ai_review"]
        prior_auth_reviews = [
            log for log in logs if log.get("action") == "capability05.prior_auth_evaluated"
        ]
        reviews_by_mode = Counter(
            (log.get("details") or {}).get("review_mode", "prior_auth") for log in ai_reviews
        )
        reviews_by_mode["prior_auth"] += len(prior_auth_reviews)

        capability_invocations = Counter(
            log["action"] for log in logs if (log.get("action") or "").startswith("capability")
        )

        action_counts = Counter(log.get("action") or "unknown" for log in logs)
        top_actions = [
            ActionCount(action=action, count=count)
            for action, count in action_counts.most_common(8)
        ]

        return ModelTrackingMetrics(
            ai_review_count=len(ai_reviews) + len(prior_auth_reviews),
            reviews_by_mode=dict(reviews_by_mode),
            capability_invocations=dict(capability_invocations),
            top_actions=top_actions,
        )


reporting_service = ReportingService()
