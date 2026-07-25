# FHIR Case Management System — Functional Manual

**Version:** 0.1.0  
**Audience:** Clinical operations reviewers, QA testers, solution architects  
**Last updated:** July 2026

---

## Table of contents

1. [Purpose](#1-purpose)
2. [Problem statement](#2-problem-statement)
3. [Objectives and how the system meets them](#3-objectives-and-how-the-system-meets-them)
4. [Solution overview](#4-solution-overview)
5. [Architecture](#5-architecture)
6. [Case lifecycle and state machine](#6-case-lifecycle-and-state-machine)
7. [Human-in-the-loop (HITL)](#7-human-in-the-loop-hitl)
8. [Data sources](#8-data-sources)
9. [Environment setup](#9-environment-setup)
10. [Test UI guide](#10-test-ui-guide)
11. [Test data preparation](#11-test-data-preparation)
12. [Functional test scenarios](#12-functional-test-scenarios)
13. [Audit and compliance](#13-audit-and-compliance)
14. [API reference (summary)](#14-api-reference-summary)
15. [Troubleshooting](#15-troubleshooting)
16. [Appendix: scenario results checklist](#16-appendix-scenario-results-checklist)

---

## 1. Purpose

The **FHIR Case Management System (FHIR-CMS)** is a healthcare case review platform that:

- Manages clinical cases through a governed workflow
- Pulls patient and observation data from a **FHIR R4** server
- Uses a **LangGraph AI agent** grounded by a **Neo4j clinical knowledge graph** to produce review recommendations
- Requires **human approval** before a case can be finalized
- Records every significant action in an **audit log**

This manual describes what the system solves, how it meets its design objectives, and how to validate it using seven functional test scenarios.

---

## 2. Problem statement

Healthcare case management often involves:

| Challenge | Impact |
|-----------|--------|
| Fragmented patient data across systems | Reviewers lack a single view of labs and demographics |
| Unstructured clinical review | Decisions are inconsistent and hard to audit |
| AI used without guardrails | Models may hallucinate or bypass human oversight |
| No enforced workflow | Cases skip review steps or close without accountability |

Organizations need a system that combines **structured clinical data**, **governed workflows**, **AI-assisted analysis**, and **mandatory human sign-off** — with a full audit trail.

---

## 3. Objectives and how the system meets them

| Objective | How the system meets it |
|-----------|-------------------------|
| **Standardize case review** | Enforced state machine: `Pending` → `AI_Review` → `Pending_Approval` → `Approved` / `Rejected` |
| **Use interoperable clinical data** | FHIR R4 Patient and Observation resources from HAPI FHIR |
| **Ground AI in clinical knowledge** | LangGraph agent calls Neo4j tools for diseases, reference ranges, comorbidities, and interventions |
| **Keep humans in control** | LangGraph `interrupt()` pauses at `Pending_Approval`; only `/human-approval` can finalize |
| **Support local or cloud LLMs** | OpenAI-compatible endpoint (e.g. Greyflow Ollama at `greyflow-ai:11434`) or OpenAI API |
| **Ensure traceability** | PostgreSQL audit log for case creation, transitions, AI review, and human decisions |
| **Prevent invalid workflow shortcuts** | State machine rejects illegal transitions (e.g. `Pending` → `Approved`) with HTTP 400 |

---

## 4. Solution overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│  HAPI FHIR   │     │   Neo4j     │
│   (API/UI)  │     │  Patients &  │     │  Clinical   │
│             │────▶│ Observations │     │   Graph     │
└──────┬──────┘     └──────────────┘     └──────▲──────┘
       │                                         │
       │         ┌──────────────┐                │
       └────────▶│  LangGraph   │────────────────┘
                 │  AI Agent    │
                 └──────────────┘
       │
       ▼
┌─────────────┐
│ PostgreSQL  │
│ (Audit Log) │
└─────────────┘
```

**End-to-end flow:**

1. Reviewer creates a case linked to a FHIR patient
2. Case moves to `AI_Review`
3. LangGraph agent analyzes case context, queries Neo4j, and produces a recommendation
4. Workflow pauses at `Pending_Approval`
5. Human reviewer approves or rejects
6. Case closes in a terminal state; all steps are audited

---

## 5. Architecture

| Component | Technology | Role |
|-----------|------------|------|
| API & Test UI | FastAPI + static HTML | REST API and manual testing interface |
| Patient data | HAPI FHIR (R4) | Source of truth for patients and observations |
| Clinical knowledge | Neo4j | Diseases, LOINC reference ranges, comorbidities, interventions |
| AI orchestration | LangGraph | Agent loop with tools + human-in-the-loop interrupt |
| Inference | Ollama (local) or OpenAI | LLM for clinical summarization and recommendations |
| Audit | PostgreSQL | Immutable activity log |

**Service URLs (default Docker stack):**

| Service | URL |
|---------|-----|
| Test UI | http://localhost:8000/ |
| API docs | http://localhost:8000/docs |
| HAPI FHIR | http://localhost:8080/fhir |
| Neo4j Browser | http://localhost:7474 |

---

## 6. Case lifecycle and state machine

```
Pending ──▶ AI_Review ──▶ Pending_Approval ──▶ Approved
                                        └──▶ Rejected
```

| Current state | Allowed next step | How |
|---------------|-------------------|-----|
| `Pending` | `AI_Review` | `POST /cases/{id}/transition` |
| `AI_Review` | `Pending_Approval` | `POST /cases/{id}/ai-review` (automatic after AI completes) |
| `Pending_Approval` | `Approved` or `Rejected` | `POST /cases/{id}/human-approval` only |
| `Approved` | *(none — terminal)* | — |
| `Rejected` | *(none — terminal)* | — |

**Important rules:**

- Observations are loaded from FHIR **at case creation** only. Create a new case after adding FHIR observations.
- A case **cannot** return to `AI_Review` after AI review completes. Start a new case to re-run AI.
- Skipping steps (e.g. `Pending` → `Approved`) returns **HTTP 400**.

---

## 7. Human-in-the-loop (HITL)

After AI review, the LangGraph agent hits an **interrupt** node:

1. AI summary is saved to the case
2. Status moves to `Pending_Approval`
3. Graph execution pauses until a human acts
4. Reviewer calls `/human-approval` with `approved: true` or `false`
5. Graph resumes and case moves to `Approved` or `Rejected`

This ensures AI **recommends** but humans **decide** — a core compliance requirement for clinical workflows.

---

## 8. Data sources

### 8.1 FHIR (patient-specific)

Stored in HAPI FHIR. Loaded when a case is created.

| Resource | Example |
|----------|---------|
| Patient | Jane Doe (`Patient/1002`) |
| Observation — Glucose | LOINC `2339-0`, 145 mg/dL |
| Observation — Creatinine | LOINC `2160-0`, 1.4 mg/dL |
| Observation — Systolic BP | LOINC `8480-6`, 142 mmHg |

### 8.2 Neo4j (clinical knowledge)

Seeded once via `init.cypher`. Provides:

| Node | Examples |
|------|----------|
| Disease | Type 2 Diabetes (E11), Hypertension (I10), CKD (N18) |
| Observation | Reference ranges for glucose, BP, creatinine |
| Intervention | Metformin, Lifestyle Modification |
| Relationships | Diabetes ↔ Hypertension comorbidity; diabetes → CKD risk |

### 8.3 How they work together

| Question type | Primary source | Tool |
|---------------|----------------|------|
| "What is this patient's glucose?" | FHIR | Case context |
| "What is the normal range for LOINC 2339-0?" | Neo4j | `get_reference_ranges` |
| "What conditions relate to diabetes?" | Neo4j | `query_clinical_knowledge_graph` |

---

## 9. Environment setup

### 9.1 Start the stack

```bash
cd fhir-cms
cp .env.example .env
# Configure LLM (see below)
docker compose up --build
```

### 9.2 Local LLM (Greyflow / Ollama)

```env
LLM_BASE_URL=http://greyflow-ai:11434/v1
LLM_MODEL=mistral-nemo:latest
LLM_API_KEY=ollama
GREYFLOW_AI_HOST_IP=100.124.13.39
```

### 9.3 Seed Neo4j (required for scenarios 1–5)

```bash
docker compose exec neo4j cypher-shell -u neo4j -p password -f /import/init.cypher
```

Expected output: `Added 8 nodes, Created 7 relationships`

### 9.4 Verify health

```bash
curl http://localhost:8000/health
```

---

## 10. Test UI guide

Open **http://localhost:8000/**

| Panel | Purpose |
|-------|---------|
| **Left** | Create cases, list all cases |
| **Center** | Case detail, workflow actions, AI summary |
| **Right** | Audit log for selected case |

**Standard workflow in UI:**

1. Create case (enter patient ID, title, description)
2. Select case → **Start AI review**
3. Enter clinical query → **Run AI review**
4. Review AI summary → **Approve** or **Reject**

> **Note:** Invalid transitions (Scenario 7) must be tested via Swagger or curl — the UI only exposes valid actions.

---

## 11. Test data preparation

### 11.1 Create patient in FHIR

```bash
curl -X POST http://localhost:8080/fhir/Patient \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Patient",
    "name": [{"family": "Doe", "given": ["Jane"]}],
    "gender": "female",
    "birthDate": "1985-03-15"
  }'
```

Record the returned `id` (e.g. `1002`). Use this as **patient_id** in all scenarios.

### 11.2 Add observations in FHIR

**Glucose (2339-0):**

```bash
curl -X POST http://localhost:8080/fhir/Observation \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Observation",
    "status": "final",
    "code": {
      "coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}],
      "text": "Glucose"
    },
    "subject": {"reference": "Patient/1002"},
    "effectiveDateTime": "2026-07-20",
    "valueQuantity": {"value": 145, "unit": "mg/dL"}
  }'
```

**Creatinine (2160-0):**

```bash
curl -X POST http://localhost:8080/fhir/Observation \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Observation",
    "status": "final",
    "code": {
      "coding": [{"system": "http://loinc.org", "code": "2160-0", "display": "Creatinine"}],
      "text": "Creatinine"
    },
    "subject": {"reference": "Patient/1002"},
    "effectiveDateTime": "2026-07-20",
    "valueQuantity": {"value": 1.4, "unit": "mg/dL"}
  }'
```

**Systolic BP (8480-6):**

```bash
curl -X POST http://localhost:8080/fhir/Observation \
  -H "Content-Type: application/fhir+json" \
  -d '{
    "resourceType": "Observation",
    "status": "final",
    "code": {
      "coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}],
      "text": "Systolic Blood Pressure"
    },
    "subject": {"reference": "Patient/1002"},
    "effectiveDateTime": "2026-07-20",
    "valueQuantity": {"value": 142, "unit": "mmHg"}
  }'
```

### 11.3 Verify observations

```bash
curl http://localhost:8000/api/v1/patients/1002/observations
```

---

## 12. Functional test scenarios

### Scenario coverage matrix

| # | Scenario | Clinical focus | FHIR data needed | Neo4j needed | Human decision | Final status |
|---|----------|----------------|------------------|--------------|----------------|--------------|
| 1 | Diabetes management | Type 2 Diabetes, glucose | Glucose | Yes | Approve | `Approved` |
| 2 | Hypertension follow-up | Hypertension, BP | Systolic BP | Yes | Approve | `Approved` |
| 3 | CKD screening | CKD, creatinine, diabetes risk | Glucose + Creatinine | Yes | Approve | `Approved` |
| 4 | Comorbidity review | Diabetes + Hypertension interaction | All three labs | Yes | Approve | `Approved` |
| 5 | Reference range (LOINC) | Glucose vs normal range | Glucose | Yes (seeded) | Approve | `Approved` |
| 6 | Insufficient evidence | Care management gate | All three labs | Yes | **Reject** | `Rejected` |
| 7 | Invalid transition | State machine guard | None | No | N/A (API test) | Unchanged + 400 |

---

### Scenario 1 — Diabetes management (happy path)

**Objective:** Validate end-to-end workflow with diabetes-focused AI review.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Diabetes management review` |
| Description | `Patient has elevated fasting glucose. Evaluate whether diabetes monitoring and treatment are appropriate.` |
| Clinical query | `Are there concerns about Type 2 Diabetes based on available glucose observations?` |
| Human decision | **Approve** — `Elevated glucose aligns with diabetes monitoring criteria.` |

**Expected AI behavior:** References glucose 145 mg/dL; may cite Neo4j diabetes pathway and Metformin.

**Validates:** Full workflow, FHIR observations, Neo4j disease knowledge, HITL approve path.

---

### Scenario 2 — Hypertension follow-up

**Objective:** Validate hypertension-specific clinical reasoning.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Hypertension follow-up` |
| Description | `Review persistently elevated systolic blood pressure readings.` |
| Clinical query | `Does this patient show signs of hypertension that require intervention?` |
| Human decision | **Approve** — `BP elevation warrants lifestyle modification.` |

**Expected AI behavior:** References systolic BP 142 mmHg; cites hypertension and lifestyle intervention from Neo4j.

**Validates:** BP observation ingestion, hypertension disease node, intervention lookup.

---

### Scenario 3 — Chronic kidney disease screening

**Objective:** Validate CKD risk assessment with renal and metabolic labs.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Chronic kidney disease screening` |
| Description | `Evaluate creatinine levels and kidney disease risk in a patient with metabolic comorbidities.` |
| Clinical query | `Is there evidence of chronic kidney disease risk based on creatinine and related conditions?` |
| Human decision | **Approve** — `CKD risk factors identified; eGFR and nephrology follow-up recommended.` |

**Expected AI behavior:**

- Without creatinine: states insufficient data (reject or new case after adding labs)
- With creatinine 1.4 mg/dL + glucose 145 mg/dL: flags elevated creatinine, diabetes as CKD risk factor, recommends eGFR/ACR monitoring

**Validates:** Multi-lab reasoning, diabetes → CKD risk relationship in Neo4j.

---

### Scenario 4 — Diabetes and hypertension comorbidity

**Objective:** Validate interaction reasoning across multiple conditions.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Diabetes and hypertension comorbidity review` |
| Description | `Patient presents with both metabolic and cardiovascular risk factors.` |
| Clinical query | `How do diabetes and hypertension interact for this patient, and what should be monitored?` |
| Human decision | **Approve** — `Comorbid conditions confirmed; dual monitoring plan appropriate.` |

**Expected AI behavior:**

- With all three labs: explains diabetes–hypertension interaction, kidney impact (creatinine), monitoring plan for glucose, BP, and renal function
- Without BP observation: references hypertension from case text only (weaker demo)

**Validates:** Comorbidity edges in Neo4j, multi-condition monitoring recommendations.

---

### Scenario 5 — Glucose reference range (LOINC 2339-0)

**Objective:** Validate Neo4j reference range tool integration.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Glucose reference range check` |
| Description | `Verify whether glucose observation values fall within normal reference ranges.` |
| Clinical query | `Check reference ranges for LOINC code 2339-0 and interpret any glucose results.` |
| Human decision | **Approve** — `Glucose 145 mg/dL exceeds reference range 70–99 mg/dL.` |

**Expected AI behavior:**

- **Before Neo4j seed:** "Could not find reference ranges" → do not approve; seed graph and retry
- **After Neo4j seed:** "145 mg/dL is above normal range 70–99 mg/dL; suggests prediabetes/diabetes"

**Validates:** `get_reference_ranges` tool, FHIR + Neo4j combined interpretation.

---

### Scenario 6 — Human rejection path (insufficient evidence)

**Objective:** Validate human **reject** workflow and conservative AI reasoning.

| Field | Value |
|-------|-------|
| Patient ID | `1002` |
| Title | `Incomplete clinical workup` |
| Description | `Preliminary review with limited supporting documentation.` |
| Clinical query | `Is there enough evidence to approve ongoing care management for this case?` |
| Human decision | **Reject** — `Insufficient clinical context for care management approval.` |

**Expected AI behavior:** Even with labs present, AI recommends **against** approving ongoing care management without fuller clinical context (history, symptoms, additional workup).

**Validates:** HITL reject path, AI conservative stance, `case.human_approval` audit with `approved: false`.

> **Note:** This returns HTTP **200** (successful rejection). This is correct — Scenario 6 is not an error case.

---

### Scenario 7 — Invalid state transition (error handling)

**Objective:** Validate state machine enforces workflow order.

**Steps:**

1. Create a case (status = `Pending`)
2. **Do not** start AI review
3. Call transition API directly:

```bash
CASE_ID=$(curl -sS -X POST http://localhost:8000/api/v1/cases \
  -H "Content-Type: application/json" \
  -d '{"patient_id":"1002","title":"Scenario 7 test","description":"Invalid transition test"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -X POST "http://localhost:8000/api/v1/cases/$CASE_ID/transition" \
  -H "Content-Type: application/json" \
  -d '{"target_status": "Approved"}'
```

**Expected result:**

```json
HTTP 400
{"detail": "Invalid transition from Pending to Approved"}
```

**Validates:** State machine guardrails; cannot bypass AI review or human approval.

---

## 13. Audit and compliance

Every scenario generates audit events viewable at:

```bash
curl http://localhost:8000/api/v1/audit
curl "http://localhost:8000/api/v1/audit?entity_id={CASE_ID}"
```

| Action | When logged |
|--------|-------------|
| `case.created` | Case created |
| `case.transition` | Status changed (e.g. to `AI_Review`) |
| `case.ai_review` | AI review completed |
| `case.human_approval` | Human approved or rejected |

A complete scenario run should produce all four event types.

---

## 14. API reference (summary)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/health` | Health check |
| `GET` | `/` | Test UI |
| `POST` | `/api/v1/cases` | Create case |
| `GET` | `/api/v1/cases` | List cases |
| `GET` | `/api/v1/cases/{id}` | Get case detail |
| `GET` | `/api/v1/cases/{id}/transitions` | Allowed transitions |
| `POST` | `/api/v1/cases/{id}/transition` | Change status |
| `POST` | `/api/v1/cases/{id}/ai-review` | Run AI review |
| `POST` | `/api/v1/cases/{id}/human-approval` | Approve or reject |
| `GET` | `/api/v1/patients/{id}/observations` | List FHIR observations |
| `GET` | `/api/v1/audit` | Audit log |

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| OpenAI 401 error | `OPENAI_API_KEY` placeholder used | Set `LLM_BASE_URL` for local Ollama |
| "No reference ranges found" | Neo4j not seeded | Run `init.cypher` seed command |
| Observations empty on case | No FHIR observations, or case created before adding them | Add observations in HAPI; create **new** case |
| `Patient/1 not found` | HAPI assigns its own IDs | Use actual patient `id` from FHIR response |
| AI review can't re-run | Case past `AI_Review` | Create a new case |
| Scenario 7 no 400 in UI | UI only allows valid actions | Test via Swagger or curl |
| Port 8000 in use | Another service bound | `docker compose down` or change port |

---

## 16. Appendix: scenario results checklist

Use this checklist when completing the full functional test pass:

| # | Scenario | AI review meaningful | Correct human action | Final status | Audit complete |
|---|----------|---------------------|----------------------|--------------|----------------|
| 1 | Diabetes | ☐ | Approve | `Approved` | ☐ |
| 2 | Hypertension | ☐ | Approve | `Approved` | ☐ |
| 3 | CKD | ☐ | Approve | `Approved` | ☐ |
| 4 | Comorbidity | ☐ | Approve | `Approved` | ☐ |
| 5 | Reference range | ☐ | Approve | `Approved` | ☐ |
| 6 | Insufficient evidence | ☐ | **Reject** | `Rejected` | ☐ |
| 7 | Invalid transition | N/A | N/A | 400 error | ☐ |

**Sign-off:**

| Role | Name | Date | Result |
|------|------|------|--------|
| Tester | | | |
| Reviewer | | | |

---

## Document control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | July 2026 | FHIR-CMS Team | Initial functional manual with 7 test scenarios |
