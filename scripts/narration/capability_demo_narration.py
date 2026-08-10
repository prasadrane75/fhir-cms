"""Narration segments for the capability demonstration video.

Each segment includes target screen time in seconds so commentary stays
aligned with the auto-playing demo timeline.
"""

NARRATION_SEGMENTS = [
    {
        "id": "intro",
        "duration_sec": 28,
        "text": (
            "Welcome to the FHIR Case Management System capability demonstration. "
            "This is the high-risk diabetic patient journey for Robert Martinez, "
            "member M1002, following eleven integrated capabilities from enrollment "
            "through executive reporting."
        ),
    },
    {
        "id": "cap01",
        "duration_sec": 38,
        "text": (
            "Phase one begins with Capability Zero One, member eligibility. "
            "An eight thirty-four enrollment payload arrives from the employer group. "
            "FastAPI validates the schema, resolves member identity, and registers "
            "active coverage on the common product spine."
        ),
    },
    {
        "id": "cap03",
        "duration_sec": 38,
        "text": (
            "Capability Zero Three ingests a real-time HL seven A D T feed. "
            "Robert Martinez, patient P1002, is admitted through the emergency room. "
            "The listener matches the member identifier and records the admission "
            "event with no perceptible latency."
        ),
    },
    {
        "id": "cap04",
        "duration_sec": 38,
        "text": (
            "Capability Zero Four validates the attending physician. "
            "National Provider Identifier and tax identifier are cross-referenced "
            "against the master provider directory, confirming active network "
            "participation and credentialing compliance before downstream processing."
        ),
    },
    {
        "id": "cap02",
        "duration_sec": 45,
        "text": (
            "Phase two automates claims and clinical review. "
            "Capability Zero Two receives an institutional claim with blood glucose "
            "at two hundred eighty milligrams per deciliter and elevated creatinine. "
            "The intake engine checks Neo4j pricing rules and flags the claim for review."
        ),
    },
    {
        "id": "cap05",
        "duration_sec": 48,
        "text": (
            "Capability Zero Five spawns a prior authorization case automatically. "
            "The LangGraph agent analyzes chronic disease progression risk, "
            "querying the Neo4j knowledge graph for comorbidities like hypertension "
            "and evidence-based reference ranges for glucose and kidney function."
        ),
    },
    {
        "id": "cap06",
        "duration_sec": 40,
        "text": (
            "Capability Zero Six drafts a structured appeals and grievances recommendation. "
            "Because multi-system risk is detected, the agent reaches the human-in-the-loop "
            "interrupt checkpoint. Every reasoning step is written to the PostgreSQL audit ledger."
        ),
    },
    {
        "id": "hitl",
        "duration_sec": 36,
        "text": (
            "A human reviewer approves the recommendation. "
            "The case transitions from pending approval to approved, "
            "preserving immutable audit evidence for compliance and traceability."
        ),
    },
    {
        "id": "cap07",
        "duration_sec": 42,
        "text": (
            "Capability Zero Seven runs care management analytics. "
            "Neo4j calculates a comorbidity risk score from the clinical graph "
            "and surfaces open care gaps, prioritizing outreach for high-risk measures "
            "such as annual A one C monitoring."
        ),
    },
    {
        "id": "cap08",
        "duration_sec": 38,
        "text": (
            "Capability Zero Eight normalizes encounter data for C M S reporting. "
            "Diagnosis codes map to I C D ten, procedures align to C P T, "
            "and clean encounter records are prepared for regulatory submission."
        ),
    },
    {
        "id": "cap09",
        "duration_sec": 36,
        "text": (
            "Capability Zero Nine performs third-party liability screening. "
            "The engine verifies primary payer status and scans for subrogation targets "
            "before any disbursement is authorized."
        ),
    },
    {
        "id": "cap10",
        "duration_sec": 40,
        "text": (
            "Capability Ten applies payment integrity controls. "
            "Duplicate payments, coding discrepancies, and overpayment anomalies "
            "are screened across the adjudication path, producing a clearance score."
        ),
    },
    {
        "id": "cap11",
        "duration_sec": 44,
        "text": (
            "Capability Eleven closes the loop in the enterprise data warehouse. "
            "All transactional handoffs feed a real-time balanced scorecard: "
            "operational cycle times, approval ratios, audit exception rates, "
            "and LangGraph model tracking from the PostgreSQL audit ledger."
        ),
    },
    {
        "id": "finale",
        "duration_sec": 30,
        "text": (
            "This completes the end-to-end capability demonstration. "
            "Every step you saw is backed by live FastAPI services, "
            "Neo4j clinical and claims intelligence, LangGraph human-in-the-loop review, "
            "and executive reporting on the dashboard."
        ),
    },
]
