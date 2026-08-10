#!/usr/bin/env python3
"""Detailed narration for the Capability Explorer demo (Jane Doe / M1001)."""

NARRATION_SEGMENTS = [
    {
        "id": "intro",
        "duration_sec": 35,
        "text": (
            "Welcome to the Capability Explorer — a detailed walkthrough of all eleven "
            "healthcare payer capabilities. Our new scenario follows Jane Doe, member M1001, "
            "through a cardiac care coordination episode: chest pain evaluation, prior authorization, "
            "payment integrity, and executive reporting. Each step explains what the capability does, "
            "how it works, and shows a live API result."
        ),
    },
    {
        "id": "cap01",
        "duration_sec": 55,
        "text": (
            "Capability One is Member Eligibility on the common product spine. "
            "It supports two X twelve flows. The two seventy inquiry confirms active coverage "
            "before a cardiology visit. The eight thirty-four enrollment transaction registers "
            "or updates member demographics and plan assignment. "
            "FastAPI validates payloads, returns mock two seventy-one and nine ninety-nine responses, "
            "and writes every transaction to the PostgreSQL audit ledger."
        ),
    },
    {
        "id": "cap02",
        "duration_sec": 50,
        "text": (
            "Capability Two is Claims Intake and Adjudication. "
            "When Jane's professional claim arrives with an office visit and electrocardiogram, "
            "the engine queries Neo4j for payer contract rates and duplicate claim detection. "
            "Each line item receives an allowed amount, adjustment reason codes, "
            "and an overall adjudication status of approved, partial, or denied."
        ),
    },
    {
        "id": "cap03",
        "duration_sec": 45,
        "text": (
            "Capability Three is Real-Time Clinical Data Exchange via HL seven A D T. "
            "When Memorial Hospital admits Jane for chest pain observation, "
            "the A zero one admission message is parsed for patient identifier, event type, "
            "and attending context. Accepted messages become immediate triggers for downstream "
            "utilization management without batch delay."
        ),
    },
    {
        "id": "cap04",
        "duration_sec": 42,
        "text": (
            "Capability Four is Provider Validation. "
            "Before authorizing cardiac procedures, the platform cross-references "
            "the cardiologist's National Provider Identifier and tax identifier "
            "against the master provider directory. Network status and credentialing compliance "
            "must be confirmed before claims or prior authorization proceed."
        ),
    },
    {
        "id": "cap05",
        "duration_sec": 55,
        "text": (
            "Capability Five is Prior Authorization with LangGraph and Neo4j grounding. "
            "A utilization management case is auto-spawned when clinical criteria require review. "
            "The LangGraph agent queries the knowledge graph for comorbidities, "
            "reference ranges, and evidence-based interventions, then pauses at a human-in-the-loop "
            "interrupt checkpoint for reviewer approval."
        ),
    },
    {
        "id": "cap06",
        "duration_sec": 48,
        "text": (
            "Capability Six is Appeals and Grievances. "
            "When a member or provider challenges a determination, "
            "the system drafts a structured clinical recommendation from the AI summary. "
            "Multi-system risk keywords — diabetes, hypertension, kidney function — "
            "flag complex cases. Every reasoning step remains traceable in the audit ledger."
        ),
    },
    {
        "id": "cap07",
        "duration_sec": 48,
        "text": (
            "Capability Seven is Care Management and Care Gap Analytics. "
            "Neo4j calculates comorbidity risk scores from chronic conditions on the member graph "
            "and surfaces open HEDIS-style care measures. "
            "Care coordinators receive prioritized outreach lists — for example, "
            "blood pressure control gaps for members with hypertension."
        ),
    },
    {
        "id": "cap08",
        "duration_sec": 42,
        "text": (
            "Capability Eight is Encounter Normalization for C M S reporting. "
            "Diagnosis codes map to I C D ten, procedures align to C P T, "
            "and the encounter is validated for regulatory completeness before submission. "
            "Incomplete encounters are flagged so data quality teams can remediate upstream."
        ),
    },
    {
        "id": "cap09",
        "duration_sec": 40,
        "text": (
            "Capability Nine is Third-Party Liability screening. "
            "Before disbursement, the engine confirms primary payer status "
            "and scans for subrogation targets such as workers compensation "
            "or automobile liability when accident indicators are present."
        ),
    },
    {
        "id": "cap10",
        "duration_sec": 48,
        "text": (
            "Capability Ten is Payment Integrity. "
            "For Jane Doe, Neo4j detects a duplicate payment anomaly — "
            "two posted payments against the same claim identifier. "
            "The screening engine also flags clinical-to-payment mismatches, "
            "protecting the payer from overpayment and fraud leakage."
        ),
    },
    {
        "id": "cap11",
        "duration_sec": 50,
        "text": (
            "Capability Eleven is the Enterprise Data Warehouse balanced scorecard. "
            "All capability handoffs aggregate from the PostgreSQL audit ledger: "
            "case cycle times, human approval ratios, audit exception rates, "
            "and LangGraph model tracking. Executives monitor live metrics on the dashboard."
        ),
    },
    {
        "id": "finale",
        "duration_sec": 30,
        "text": (
            "This completes the Capability Explorer demonstration. "
            "You saw each capability explained in business and technical terms, "
            "with live FastAPI calls, Neo4j intelligence, LangGraph review, "
            "and executive reporting. Open the dashboard to explore scorecard metrics interactively."
        ),
    },
]
