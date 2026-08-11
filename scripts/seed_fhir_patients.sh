#!/usr/bin/env bash
# Seed demo Patient resources in HAPI FHIR (required before adding observations).
set -euo pipefail

FHIR_BASE_URL="${FHIR_BASE_URL:-http://127.0.0.1:8080/fhir}"

echo "Seeding FHIR patients at ${FHIR_BASE_URL}"

python3 <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

fhir_base_url = os.environ["FHIR_BASE_URL"].rstrip("/")

patients = [
    {
        "id": "P1000",
        "identifier": [{"system": "http://hospital.local/mrn", "value": "1000"}],
        "name": [{"family": "Demo", "given": ["Patient"]}],
        "gender": "unknown",
        "birthDate": "1980-01-01",
    },
    {
        "id": "P1001",
        "identifier": [{"system": "http://hospital.local/mrn", "value": "1001"}],
        "name": [{"family": "Doe", "given": ["Jane"]}],
        "gender": "female",
        "birthDate": "1968-03-22",
    },
    {
        "id": "P1002",
        "identifier": [{"system": "http://hospital.local/mrn", "value": "1002"}],
        "name": [{"family": "Martinez", "given": ["Robert"]}],
        "gender": "male",
        "birthDate": "1965-06-12",
    },
]


def upsert_patient(patient: dict) -> None:
    patient_id = patient["id"]
    payload = {"resourceType": "Patient", **patient}
    url = f"{fhir_base_url}/Patient/{patient_id}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"  Patient/{patient_id} -> HTTP {resp.status}")


for entry in patients:
    try:
        upsert_patient(entry)
    except urllib.error.HTTPError as exc:
        print(f"ERROR seeding Patient/{entry['id']}: HTTP {exc.code} {exc.read().decode()[:300]}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"ERROR: HAPI not reachable at {fhir_base_url}: {exc}", file=sys.stderr)
        print("Start HAPI first: docker compose -f docker-compose.greyflow-app.yaml up -d hapi-fhir", file=sys.stderr)
        raise SystemExit(1) from exc

print("Done. Demo patients: P1000, P1001, P1002")
PY
