from datetime import datetime, timedelta

from app.services.reporting_service import ReportingService, _is_audit_exception


def _log(
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    timestamp: datetime,
    details: dict | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details or {},
        "message": action,
    }


def test_aggregate_cycle_times_with_capability05_fallback():
    base = datetime.utcnow() - timedelta(hours=10)
    logs = [
        _log(
            action="capability05.prior_auth_evaluated",
            entity_type="Case",
            entity_id="case-cap05",
            timestamp=base + timedelta(hours=2),
        ),
        _log(
            action="case.human_approval",
            entity_type="Case",
            entity_id="case-cap05",
            timestamp=base + timedelta(hours=4),
            details={"approved": True},
        ),
    ]

    metrics = ReportingService()._aggregate_cycle_times(logs)

    assert metrics.sample_size == 1
    assert metrics.avg_pending_approval_hours == 2.0
    assert metrics.avg_pending_to_ai_review_hours is None
    assert metrics.avg_ai_review_hours is None


def test_aggregate_cycle_times():
    base = datetime.utcnow() - timedelta(hours=10)
    logs = [
        _log(action="case.created", entity_type="Case", entity_id="case-1", timestamp=base),
        _log(
            action="case.transition",
            entity_type="Case",
            entity_id="case-1",
            timestamp=base + timedelta(hours=1),
            details={"target_status": "AI_Review"},
        ),
        _log(
            action="case.ai_review",
            entity_type="Case",
            entity_id="case-1",
            timestamp=base + timedelta(hours=2),
            details={"review_mode": "prior_auth"},
        ),
        _log(
            action="case.human_approval",
            entity_type="Case",
            entity_id="case-1",
            timestamp=base + timedelta(hours=4),
            details={"approved": True},
        ),
    ]

    service = ReportingService()
    metrics = service._aggregate_cycle_times(logs)

    assert metrics.sample_size == 1
    assert metrics.avg_pending_to_ai_review_hours == 1.0
    assert metrics.avg_ai_review_hours == 1.0
    assert metrics.avg_pending_approval_hours == 2.0
    assert metrics.avg_total_cycle_hours == 4.0


def test_aggregate_approval_denial():
    logs = [
        _log(
            action="case.human_approval",
            entity_type="Case",
            entity_id="case-1",
            timestamp=datetime.utcnow(),
            details={"approved": True},
        ),
        _log(
            action="case.human_approval",
            entity_type="Case",
            entity_id="case-2",
            timestamp=datetime.utcnow(),
            details={"approved": False},
        ),
    ]

    metrics = ReportingService()._aggregate_approval_denial(logs)

    assert metrics.approved_count == 1
    assert metrics.denied_count == 1
    assert metrics.approval_ratio == 0.5
    assert metrics.denial_ratio == 0.5


def test_audit_exception_detection():
    log = _log(
        action="capability02.claim_adjudicated",
        entity_type="Claim",
        entity_id="CLM-1",
        timestamp=datetime.utcnow(),
        details={"adjudication_status": "denied", "duplicate_detected": True},
    )

    is_exception, category = _is_audit_exception(log)

    assert is_exception is True
    assert category == "claim_adjudication_exception"


def test_aggregate_model_tracking():
    logs = [
        _log(
            action="case.ai_review",
            entity_type="Case",
            entity_id="case-1",
            timestamp=datetime.utcnow(),
            details={"review_mode": "claims_adjudication"},
        ),
        _log(
            action="capability11.scorecard_generated",
            entity_type="BalancedScorecard",
            entity_id="txn-1",
            timestamp=datetime.utcnow(),
        ),
    ]

    metrics = ReportingService()._aggregate_model_tracking(logs)

    assert metrics.ai_review_count == 1
    assert metrics.reviews_by_mode["claims_adjudication"] == 1
    assert metrics.capability_invocations["capability11.scorecard_generated"] == 1
