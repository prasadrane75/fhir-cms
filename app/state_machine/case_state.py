from app.core.models.case import CaseStatus

VALID_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.PENDING: {CaseStatus.AI_REVIEW},
    CaseStatus.AI_REVIEW: {CaseStatus.PENDING_APPROVAL},
    CaseStatus.PENDING_APPROVAL: set(),
    CaseStatus.APPROVED: set(),
    CaseStatus.REJECTED: set(),
}


class InvalidTransitionError(Exception):
    def __init__(self, current: CaseStatus, target: CaseStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current.value} to {target.value}")


def can_transition(current: CaseStatus, target: CaseStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


def validate_transition(current: CaseStatus, target: CaseStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def get_allowed_transitions(current: CaseStatus) -> list[CaseStatus]:
    return sorted(VALID_TRANSITIONS.get(current, set()), key=lambda s: s.value)
