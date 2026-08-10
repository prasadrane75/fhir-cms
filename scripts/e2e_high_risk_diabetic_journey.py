#!/usr/bin/env python3
"""End-to-end scenario: High-Risk Diabetic Patient Journey (Capabilities 01–11)."""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "http://localhost:8000"
FHIR_URL = "http://localhost:8080/fhir"
API = f"{BASE_URL}/api/v1"
MEMBER_ID = "M1002"
PATIENT_ID = "P1002"
MRN = "1002"
PAYER_ID = "PAYER01"
PROVIDER_NPI = "1234567890"
SERVICE_DATE = date.today().isoformat()


class StepResult:
    def __init__(self, step: int, name: str, ok: bool, detail: str, payload: Any = None):
        self.step = step
        self.name = name
        self.ok = ok
        self.detail = detail
        self.payload = payload


def request(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    raw_body: str | None = None,
    content_type: str = "application/json",
    timeout: int = 120,
) -> Any:
    url = f"{API}{path}" if path.startswith("/") else f"{API}/{path}"
    data = None
    headers = {}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = content_type
    elif raw_body is not None:
        data = raw_body.encode()
        headers["Content-Type"] = content_type

    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def ensure_patient() -> None:
    patient_url = f"{FHIR_URL}/Patient/{PATIENT_ID}"
    try:
        with urlopen(patient_url, timeout=10) as resp:
            if resp.status == 200:
                return
    except HTTPError as exc:
        if exc.code not in {404, 410}:
            pass

    payload = json.dumps(
        {
            "resourceType": "Patient",
            "id": PATIENT_ID,
            "identifier": [{"system": "http://hospital.local/mrn", "value": MRN}],
            "name": [{"family": "Martinez", "given": ["Robert"]}],
            "gender": "male",
            "birthDate": "1965-06-12",
        }
    ).encode()
    req = Request(
        patient_url,
        data=payload,
        headers={"Content-Type": "application/fhir+json"},
        method="PUT",
    )
    with urlopen(req, timeout=15):
        pass


def step_1_eligibility_834() -> StepResult:
    data = request(
        "POST",
        "/capabilities/01/eligibility/834",
        json_body={
            "member_id": MEMBER_ID,
            "payer_id": PAYER_ID,
            "plan_id": "PLAN-GOLD",
            "coverage_start_date": "2026-01-01",
            "subscriber_first_name": "Robert",
            "subscriber_last_name": "Martinez",
        },
    )
    ok = data["validation_status"] == "accepted"
    return StepResult(1, "Member Eligibility (834)", ok, data["validation_status"], data)


def step_2_adt_er_visit() -> StepResult:
    adt = (
        "MSH|^~\\&|ER_SYSTEM|MEMORIAL|FHIR-CMS|FACILITY|20260807143000||ADT^A01|ER1002|P|2.5\r"
        "EVN|A01|20260807143000\r"
        f"PID|1||{PATIENT_ID}^^^MRN||MARTINEZ^ROBERT^A||19650612|M\r"
        "PV1|1|E|ER^01^01||||1234567890^CHEN^SARAH"
    )
    data = request("POST", "/capabilities/03/adt", raw_body=adt, content_type="text/plain")
    ok = data["processing_status"] == "accepted" and data.get("patient_id") == PATIENT_ID
    return StepResult(2, "HL7 ADT ER Admission", ok, data["processing_status"], data)


def step_3_provider_validation() -> StepResult:
    data = request(
        "POST",
        "/capabilities/04/providers/validate",
        json_body={"npi": PROVIDER_NPI, "tax_id": "12-3456789", "provider_name": "Dr. Sarah Chen"},
    )
    ok = data["network_status"] == "active" and data["credentialing_status"] == "compliant"
    return StepResult(3, "Provider Validation", ok, f"{data['network_status']}/{data['credentialing_status']}", data)


def step_4_claims_and_labs() -> StepResult:
    lab_notes: list[str] = []
    for obs in (
        {"loinc_code": "2339-0", "display": "Glucose", "value": 280, "unit": "mg/dL"},
        {"loinc_code": "2160-0", "display": "Creatinine", "value": 1.8, "unit": "mg/dL"},
    ):
        try:
            request(
                "POST",
                f"/patients/{PATIENT_ID}/observations",
                json_body={**obs, "effective_date": SERVICE_DATE},
            )
            lab_notes.append(obs["display"])
        except HTTPError as exc:
            lab_notes.append(f"{obs['display']}: HTTP {exc.code}")

    data = request(
        "POST",
        "/capabilities/02/claims/adjudicate",
        json_body={
            "claim_id": "CLM-ER-1002",
            "member_id": MEMBER_ID,
            "payer_id": PAYER_ID,
            "provider_npi": PROVIDER_NPI,
            "service_date": SERVICE_DATE,
            "line_items": [
                {"procedure_code": "99285", "billed_amount": 450.0, "units": 1},
                {"procedure_code": "80053", "billed_amount": 45.0, "units": 1},
            ],
        },
    )
    ok = data["adjudication_status"] in {"approved", "partial", "denied"}
    return StepResult(
        4,
        "Claims Intake & Adjudication",
        ok,
        f"{data['adjudication_status']} | labs: {', '.join(lab_notes)}",
        data,
    )


def step_5_prior_auth() -> StepResult:
    data = request(
        "POST",
        "/capabilities/05/prior-auth/evaluate",
        json_body={
            "patient_id": PATIENT_ID,
            "member_id": MEMBER_ID,
            "clinical_query": "Is there risk of chronic disease progression?",
            "title": "High-risk diabetic ER follow-up prior auth",
            "description": "Glucose 280 mg/dL with elevated creatinine after ER visit.",
        },
        timeout=300,
    )
    ok = data["awaiting_human_approval"] and data["status"] == "Pending_Approval"
    return StepResult(5, "Prior Auth (LangGraph + Neo4j)", ok, data["status"], data)


def step_6_appeals(case_id: str) -> StepResult:
    data = request("POST", "/capabilities/06/appeals/draft", json_body={"case_id": case_id})
    ok = data["audit_trace_ready"] and bool(data["draft_summary"])
    return StepResult(
        6,
        "Appeals & Grievances Draft",
        ok,
        f"multi_system_risk={data['multi_system_risk_detected']}",
        data,
    )


def step_7_care_gaps() -> StepResult:
    data = request(
        "POST",
        "/capabilities/07/care-gaps/analyze",
        json_body={"member_id": MEMBER_ID},
    )
    risk = data["comorbidity_risks"][0] if data["comorbidity_risks"] else {}
    score = risk.get("comorbidity_risk_score", 0)
    ok = bool(data["comorbidity_risks"]) and (score >= 4 or len(data["care_gaps"]) > 0)
    detail = f"risk_score={score}, gaps={len(data['care_gaps'])}"
    if not ok:
        detail += " | seed Neo4j: docker compose exec neo4j cypher-shell -u neo4j -p password -f /import/init.cypher"
    return StepResult(
        7,
        "Care Management & Care Gaps",
        ok,
        detail,
        data,
    )


def step_8_encounter_normalize() -> StepResult:
    data = request(
        "POST",
        "/capabilities/08/encounters/normalize",
        json_body={
            "member_id": MEMBER_ID,
            "patient_id": PATIENT_ID,
            "diagnosis_codes": ["E11", "I10"],
            "procedure_codes": ["99285", "80053"],
            "service_date": SERVICE_DATE,
        },
    )
    ok = data["cms_ready"]
    return StepResult(8, "Encounter CMS Normalization", ok, f"cms_ready={data['cms_ready']}", data)


def step_9_tpl() -> StepResult:
    data = request(
        "POST",
        "/capabilities/09/tpl/check",
        json_body={"member_id": MEMBER_ID, "payer_id": PAYER_ID, "accident_related": False},
    )
    ok = data["primary_payer_status"] == "confirmed"
    return StepResult(9, "Third-Party Liability Check", ok, data["primary_payer_status"], data)


def step_10_payment_integrity() -> StepResult:
    data = request(
        "POST",
        "/capabilities/10/payment-integrity/detect",
        json_body={"member_id": MEMBER_ID, "payer_id": PAYER_ID, "lookback_days": 90},
    )
    ok = "anomaly_count" in data
    return StepResult(
        10,
        "Payment Integrity",
        ok,
        f"anomalies={data['anomaly_count']}, clearance={'high' if data['anomaly_count'] == 0 else 'review'}",
        data,
    )


def step_11_scorecard() -> StepResult:
    data = request("GET", "/capabilities/11/reporting/scorecard?lookback_days=7", timeout=30)
    ok = data["audit_exceptions"]["total_events"] > 0
    return StepResult(
        11,
        "EDW Executive Dashboard",
        ok,
        (
            f"events={data['audit_exceptions']['total_events']}, "
            f"exceptions={data['audit_exceptions']['exception_count']}, "
            f"ai_reviews={data['model_tracking']['ai_review_count']}"
        ),
        data,
    )


def human_approval(case_id: str) -> StepResult:
    data = request(
        "POST",
        f"/cases/{case_id}/human-approval",
        json_body={"approved": True, "reason": "High-risk diabetic criteria met; care management authorized."},
    )
    ok = data["status"] == "Approved"
    return StepResult(12, "Human Approval (HITL closure)", ok, data["status"], data)


def print_header() -> None:
    print("=" * 72)
    print(" High-Risk Diabetic Patient Journey — End-to-End Scenario")
    print(f" API: {BASE_URL}  |  Member: {MEMBER_ID}  |  Patient: {PATIENT_ID} (MRN {MRN})")
    print("=" * 72)


def print_result(result: StepResult) -> None:
    mark = "PASS" if result.ok else "FAIL"
    print(f"[{mark}] Step {result.step:02d} — {result.name}")
    print(f"       {result.detail}")


def main() -> int:
    print_header()
    results: list[StepResult] = []

    try:
        with urlopen(f"{BASE_URL}/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"ERROR: Cannot reach API at {BASE_URL}: {exc}")
        print("Run: docker compose up --build")
        return 1

    if health.get("status") != "ok":
        print("ERROR: API health check failed")
        return 1

    print("API health: ok\n")
    try:
        ensure_patient()
        print(f"FHIR Patient/{PATIENT_ID} ready\n")
    except Exception as exc:
        print(f"WARNING: Could not ensure FHIR patient {PATIENT_ID}: {exc}\n")

    results.append(step_1_eligibility_834())
    print_result(results[-1])

    results.append(step_2_adt_er_visit())
    print_result(results[-1])

    results.append(step_3_provider_validation())
    print_result(results[-1])

    try:
        results.append(step_4_claims_and_labs())
    except Exception as exc:
        results.append(StepResult(4, "Claims Intake & Adjudication", False, str(exc)))
    print_result(results[-1])

    print("\nRunning LangGraph prior auth (Step 5) — this may take 1–3 minutes...\n")
    try:
        results.append(step_5_prior_auth())
    except Exception as exc:
        results.append(StepResult(5, "Prior Auth (LangGraph + Neo4j)", False, str(exc)))
    print_result(results[-1])

    case_id = None
    if results[-1].payload:
        case_id = results[-1].payload.get("case_id")

    if case_id:
        try:
            results.append(step_6_appeals(case_id))
        except Exception as exc:
            results.append(StepResult(6, "Appeals & Grievances Draft", False, str(exc)))
        print_result(results[-1])
        time.sleep(0.5)
        try:
            results.append(human_approval(case_id))
        except Exception as exc:
            results.append(StepResult(12, "Human Approval (HITL closure)", False, str(exc)))
        print_result(results[-1])
    else:
        results.append(StepResult(6, "Appeals & Grievances Draft", False, "Skipped — no case_id"))
        print_result(results[-1])

    for fn, step_num, name in [
        (step_7_care_gaps, 7, "Care Management & Care Gaps"),
        (step_8_encounter_normalize, 8, "Encounter CMS Normalization"),
        (step_9_tpl, 9, "Third-Party Liability Check"),
        (step_10_payment_integrity, 10, "Payment Integrity"),
        (step_11_scorecard, 11, "EDW Executive Dashboard"),
    ]:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(StepResult(step_num, name, False, str(exc)))
        print_result(results[-1])

    passed = sum(1 for r in results if r.ok)
    total = len(results)
    print("\n" + "=" * 72)
    print(f" Summary: {passed}/{total} steps passed")
    print(f" Dashboard: {BASE_URL}/dashboard")
    print("=" * 72)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
