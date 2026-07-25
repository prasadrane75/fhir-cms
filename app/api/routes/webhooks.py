import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from app.core.config import settings
from app.services.audit_logger import schedule_audit_log
from app.services.webhook_service import (
    WebhookValidationError,
    run_observation_webhook_background,
    validate_webhook_secret,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _receive_observation_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str | None,
    *,
    delivery_path: str | None = None,
) -> dict[str, Any]:
    if not settings.webhook_enabled:
        raise HTTPException(status_code=503, detail="Webhook processing is disabled")

    try:
        validate_webhook_secret(x_webhook_secret)
        payload = await request.json()
    except WebhookValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    resource_type = payload.get("resourceType")
    observation_id = payload.get("id")
    if resource_type == "Bundle":
        for entry in payload.get("entry", []):
            resource = entry.get("resource") or {}
            if resource.get("resourceType") == "Observation":
                observation_id = resource.get("id")
                break

    logger.info(
        "FHIR observation webhook received (method=%s, path=%s, resourceType=%s, observationId=%s)",
        request.method,
        delivery_path or request.url.path,
        resource_type,
        observation_id,
    )

    schedule_audit_log(
        background_tasks,
        action="webhook.observation_received",
        entity_type="Webhook",
        entity_id="observation",
        actor="fhir-webhook",
        details={
            "resource_type": resource_type,
            "observation_id": observation_id,
            "delivery_path": delivery_path,
            "http_method": request.method,
        },
        message="Incoming FHIR observation webhook accepted for background processing",
    )
    background_tasks.add_task(run_observation_webhook_background, payload)

    return {
        "status": "accepted",
        "message": "Observation event queued for automated AI review",
    }


@router.post(
    "/fhir/observation",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive HAPI FHIR Observation subscription notifications",
)
async def receive_observation_webhook_post(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    return await _receive_observation_webhook(
        request,
        background_tasks,
        x_webhook_secret,
        delivery_path="/fhir/observation",
    )


@router.api_route(
    "/fhir/observation/{resource_type}/{resource_id}",
    methods=["PUT", "PATCH"],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive HAPI FHIR Observation subscription notifications (idempotent delivery)",
)
async def receive_observation_webhook_put(
    request: Request,
    background_tasks: BackgroundTasks,
    resource_type: str,
    resource_id: str,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    return await _receive_observation_webhook(
        request,
        background_tasks,
        x_webhook_secret,
        delivery_path=f"/fhir/observation/{resource_type}/{resource_id}",
    )
