from typing import Any

from app.core.models.observation import Observation


def extract_patient_id(reference: str | None) -> str | None:
    if not reference:
        return None
    if reference.startswith("Patient/"):
        return reference.split("/", 1)[1]
    return reference


def parse_observation_from_payload(payload: dict[str, Any]) -> Observation | None:
    resource_type = payload.get("resourceType")
    if resource_type == "Observation":
        return Observation.model_validate(payload)

    if resource_type != "Bundle":
        return None

    for entry in payload.get("entry", []):
        resource = entry.get("resource")
        if isinstance(resource, dict) and resource.get("resourceType") == "Observation":
            return Observation.model_validate(resource)
    return None


def observation_label(observation: Observation) -> str:
    if observation.code.text:
        return observation.code.text
    if observation.code.coding:
        return observation.code.coding[0].get("display", "Observation")
    return "Observation"
