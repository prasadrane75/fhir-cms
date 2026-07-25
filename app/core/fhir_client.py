import httpx

from app.core.config import settings
from app.core.models.observation import Observation
from app.core.models.patient import Patient


class FHIRClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.fhir_base_url).rstrip("/")

    async def get_patient(self, patient_id: str) -> Patient:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}/Patient/{patient_id}")
            response.raise_for_status()
            return Patient.model_validate(response.json())

    async def search_observations(self, patient_id: str, limit: int = 20) -> list[Observation]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/Observation",
                params={"patient": patient_id, "_count": limit, "_sort": "-date"},
            )
            response.raise_for_status()
            bundle = response.json()
            entries = bundle.get("entry", [])
            return [Observation.model_validate(e["resource"]) for e in entries if "resource" in e]

    async def create_patient(self, patient: Patient) -> Patient:
        payload = patient.model_dump(by_alias=True, exclude_none=True, mode="json")
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/Patient", json=payload)
            response.raise_for_status()
            return Patient.model_validate(response.json())

    async def create_observation(self, patient_id: str, payload: dict) -> Observation:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{self.base_url}/Observation", json=payload)
            response.raise_for_status()
            return Observation.model_validate(response.json())
