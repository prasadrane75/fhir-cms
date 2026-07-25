from fastapi import APIRouter, Query

from app.services.audit import list_audit_logs

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def get_audit_logs(
    entity_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
) -> list[dict]:
    return await list_audit_logs(entity_id=entity_id, limit=limit)
