import logging
from typing import Any

from app.core.config import settings
from app.core.models.observation import Observation
from app.services.audit import write_audit_log
from app.services.case_service import case_service
from app.services.fhir_webhook import extract_patient_id, parse_observation_from_payload

logger = logging.getLogger(__name__)


class WebhookValidationError(ValueError):
    pass


def validate_webhook_secret(provided_secret: str | None) -> None:
    if settings.webhook_secret and provided_secret != settings.webhook_secret:
        raise WebhookValidationError("Invalid webhook secret")


def parse_observation_event(payload: dict[str, Any]) -> tuple[Observation, str]:
    observation = parse_observation_from_payload(payload)
    if observation is None:
        raise WebhookValidationError("Payload does not contain an Observation resource")

    patient_id = extract_patient_id(
        observation.subject.reference if observation.subject else None
    )
    if not patient_id:
        raise WebhookValidationError("Observation is missing subject.reference to a Patient")

    return observation, patient_id


async def process_observation_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    observation, patient_id = parse_observation_event(payload)
    case = await case_service.start_auto_review_for_observation(
        patient_id,
        observation,
        settings.webhook_clinical_query,
    )

    await write_audit_log(
        "webhook.observation_processed",
        "Case",
        str(case.id),
        actor="fhir-webhook",
        details={
            "patient_id": patient_id,
            "observation_id": observation.id,
            "case_status": case.status.value,
            "clinical_query": settings.webhook_clinical_query,
        },
        message="Observation webhook triggered automated AI review",
    )

    return {
        "case_id": str(case.id),
        "patient_id": patient_id,
        "status": case.status.value,
        "observation_id": observation.id,
    }


async def run_observation_webhook_background(payload: dict[str, Any]) -> None:
    try:
        result = await process_observation_webhook(payload)
        logger.info("Observation webhook processed: %s", result)
    except Exception:
        logger.exception("Observation webhook background processing failed")
        await write_audit_log(
            "webhook.observation_failed",
            "Webhook",
            "observation",
            actor="fhir-webhook",
            details={"error": "background processing failed"},
            message="Observation webhook processing failed",
        )
