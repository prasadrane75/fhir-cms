import httpx
from fastapi import APIRouter, HTTPException, status

from app.core.fhir_client import FHIRClient
from app.core.models.observation import Observation, ObservationCreate
from app.core.models.patient import Patient
from app.services.observation_service import create_patient_observation

router = APIRouter(prefix="/patients", tags=["patients"])
fhir_client = FHIRClient()


def _raise_fhir_error(exc: Exception, *, patient_id: str | None = None) -> None:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        body = (response.text or "").strip()[:500]
        if response.status_code == 404 and patient_id and f"/Patient/{patient_id}" in str(exc.request.url):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Patient '{patient_id}' not found in HAPI FHIR. "
                    "Use IDs like P1000 (not purely numeric). Seed with: ./scripts/seed_fhir_patients.sh"
                ),
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"FHIR server error ({response.status_code}): {body or exc}",
        ) from exc
    raise HTTPException(status_code=502, detail=f"FHIR server error: {exc}") from exc


@router.get("/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str) -> Patient:
    try:
        return await fhir_client.get_patient(patient_id)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_fhir_error(exc, patient_id=patient_id)


@router.get("/{patient_id}/observations", response_model=list[Observation])
async def get_patient_observations(patient_id: str) -> list[Observation]:
    try:
        return await fhir_client.search_observations(patient_id)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_fhir_error(exc, patient_id=patient_id)


@router.post(
    "/{patient_id}/observations",
    response_model=Observation,
    status_code=status.HTTP_201_CREATED,
)
async def add_patient_observation(patient_id: str, payload: ObservationCreate) -> Observation:
    try:
        await fhir_client.get_patient(patient_id)
        return await create_patient_observation(patient_id, payload, fhir_client)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_fhir_error(exc, patient_id=patient_id)


@router.post("", response_model=Patient, status_code=201)
async def create_patient(patient: Patient) -> Patient:
    try:
        return await fhir_client.create_patient(patient)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_fhir_error(exc)
