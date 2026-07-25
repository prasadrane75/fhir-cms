from fastapi import BackgroundTasks

from app.services.audit import write_audit_log


def schedule_audit_log(
    background_tasks: BackgroundTasks,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    actor: str | None = None,
    details: dict | None = None,
    message: str | None = None,
) -> None:
    background_tasks.add_task(
        write_audit_log,
        action,
        entity_type,
        entity_id,
        actor=actor,
        details=details,
        message=message,
    )
