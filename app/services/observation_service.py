from datetime import date

from app.core.fhir_client import FHIRClient
from app.core.models.observation import Observation, ObservationCreate


def build_observation_payload(patient_id: str, data: ObservationCreate) -> dict:
    effective_date = data.effective_date or date.today().isoformat()
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": data.loinc_code,
                    "display": data.display,
                }
            ],
            "text": data.display,
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": effective_date,
        "valueQuantity": {
            "value": data.value,
            "unit": data.unit,
            "system": "http://unitsofmeasure.org",
            "code": data.unit,
        },
    }


async def create_patient_observation(
    patient_id: str,
    data: ObservationCreate,
    fhir_client: FHIRClient | None = None,
) -> Observation:
    client = fhir_client or FHIRClient()
    payload = build_observation_payload(patient_id, data)
    return await client.create_observation(patient_id, payload)
