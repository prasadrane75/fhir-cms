# FHIR Case Management System

A healthcare Case Management System built with **FastAPI**, **FHIR R4** resources, a **case state machine**, a **LangGraph** AI agent grounded by **Neo4j**, and **PostgreSQL** audit logging.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│  HAPI FHIR   │     │   Neo4j     │
│   (API)     │     │  (Patients,  │     │  (Clinical  │
│             │────▶│ Observations)│     │   Graph)    │
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

### Case State Machine

```
Pending ──▶ AI_Review ──▶ Pending_Approval ──▶ Approved
                                        └──▶ Rejected
```

| Current State      | Allowed Transitions              |
|--------------------|----------------------------------|
| `Pending`          | `AI_Review`                      |
| `AI_Review`        | `Pending_Approval`               |
| `Pending_Approval` | *(via `/human-approval` only)* |
| `Approved`         | *(terminal)*                     |
| `Rejected`         | *(terminal)*                     |

After AI review, the LangGraph agent pauses at a **human-in-the-loop** checkpoint until a reviewer approves or rejects via the API.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- An [OpenAI API key](https://platform.openai.com/) **or** a local OpenAI-compatible inference endpoint (e.g. Greyflow's Ollama instance)

## Quick Start

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY or LLM_BASE_URL for local inference
```

### 2. Start the stack

```bash
docker compose up --build
```

This starts:

| Service    | URL / Port              | Purpose                        |
|------------|-------------------------|--------------------------------|
| FastAPI    | http://localhost:8000   | Case Management API            |
| HAPI FHIR  | http://localhost:8080   | FHIR R4 server                 |
| Neo4j      | http://localhost:7474   | Clinical knowledge graph (UI)  |
| PostgreSQL | localhost:5432          | Audit log storage              |

Test UI: http://localhost:8000/  
Chat UI: http://localhost:8000/chat  
Quick capability journey: http://localhost:8000/demo  
**Capability Explorer** (detailed per-capability tour): http://localhost:8000/demo/explorer  
Executive dashboard: http://localhost:8000/dashboard  
API docs: http://localhost:8000/docs  
Functional manual: [docs/FUNCTIONAL_MANUAL.md](docs/FUNCTIONAL_MANUAL.md)  
Phase 1 chat: [docs/PHASE1_CHAT.md](docs/PHASE1_CHAT.md)  
Phase 2 webhooks: [docs/PHASE2_WEBHOOKS.md](docs/PHASE2_WEBHOOKS.md)

#### Demo modes

| URL | Use case | Best for |
|-----|----------|----------|
| `/demo` | High-risk diabetic patient journey (Robert Martinez / M1002) | Fast executive narrative |
| `/demo/explorer` | Cardiac care coordination (Jane Doe / M1001) — **each capability explained separately** | Deep-dive briefings, training, narrated video |
| `/dashboard` | Capability 11 balanced scorecard | Live KPI monitoring |

Record the detailed explorer demo:

```bash
python3 scripts/record_capability_explorer_demo.py --fast --pace slow
python3 scripts/add_voice_commentary.py --narration explorer
```

### 3. Seed the Neo4j knowledge graph

After Neo4j is healthy, load the sample clinical data:

```bash
docker compose exec neo4j cypher-shell -u neo4j -p password -f /import/init.cypher
```

### 4. (Optional) Create a test patient in HAPI FHIR

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

Note the returned `id` for use when creating cases.

## API Usage

### Create a case

```bash
curl -X POST http://localhost:8000/api/v1/cases \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "1",
    "title": "Diabetes management review",
    "description": "Review elevated glucose observations"
  }'
```

### Transition: Pending → AI_Review

```bash
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/transition \
  -H "Content-Type: application/json" \
  -d '{"target_status": "AI_Review"}'
```

### Run AI clinical review (uses LangGraph + Neo4j)

```bash
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/ai-review \
  -H "Content-Type: application/json" \
  -d '{"clinical_query": "Are there concerns about diabetes based on available observations?"}'
```

### Human approval (required after AI review)

After `/ai-review`, the case moves to `Pending_Approval` and waits for a human decision:

```bash
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/human-approval \
  -H "Content-Type: application/json" \
  -d '{"approved": true, "reason": "Clinical criteria met"}'
```

To reject:

```bash
curl -X POST http://localhost:8000/api/v1/cases/{case_id}/human-approval \
  -H "Content-Type: application/json" \
  -d '{"approved": false, "reason": "Insufficient evidence"}'
```

### View audit logs

```bash
curl http://localhost:8000/api/v1/audit
curl "http://localhost:8000/api/v1/audit?entity_id={case_id}"
```

## Project Structure

```
fhir-cms/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── core/
│   │   ├── config.py            # Settings (env-based)
│   │   ├── fhir_client.py       # HAPI FHIR HTTP client
│   │   └── models/
│   │       ├── patient.py       # FHIR Patient Pydantic model
│   │       ├── observation.py   # FHIR Observation Pydantic model
│   │       └── case.py          # Case domain model
│   ├── state_machine/
│   │   └── case_state.py        # Case transition rules
│   ├── ai/
│   │   ├── agent.py             # LangGraph clinical review agent
│   │   └── tools/
│   │       └── neo4j_tool.py    # Neo4j grounding tools
│   ├── api/routes/
│   │   ├── cases.py             # Case CRUD + transitions
│   │   ├── patients.py          # FHIR patient proxy
│   │   └── audit.py             # Audit log queries
│   └── services/
│       ├── case_service.py      # Case business logic
│       ├── audit.py             # PostgreSQL audit persistence
│       └── audit_logger.py      # Background task scheduler
├── docker/
│   └── Dockerfile
├── init-scripts/neo4j/
│   └── init.cypher              # Sample clinical graph
├── docker-compose.yaml
├── requirements.txt
└── .env.example
```

## Local Development (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Start Postgres, Neo4j, and HAPI FHIR separately, then:
uvicorn app.main:app --reload
```

## Environment Variables

| Variable          | Default                                      | Description              |
|-------------------|----------------------------------------------|--------------------------|
| `DATABASE_URL`    | `postgresql+asyncpg://cms:cms@postgres:5432/cms_audit` | Audit DB connection |
| `NEO4J_URI`       | `bolt://neo4j:7687`                          | Neo4j bolt URI           |
| `NEO4J_USER`      | `neo4j`                                      | Neo4j username           |
| `NEO4J_PASSWORD`  | `password`                                   | Neo4j password           |
| `FHIR_BASE_URL`   | `http://hapi-fhir:8080/fhir`                 | HAPI FHIR base URL       |
| `OPENAI_API_KEY`  | *(required unless `LLM_BASE_URL` is set)*    | OpenAI API key           |
| `LLM_BASE_URL`    | *(optional)*                                 | OpenAI-compatible LLM URL (e.g. Greyflow Ollama at `http://greyflow-ai:11434/v1`) |
| `LLM_MODEL`       | `gpt-4o-mini`                                | Model name for the configured LLM provider |
| `LLM_API_KEY`     | `ollama`                                     | API key for compatible local endpoints (Ollama accepts any value) |
| `GREYFLOW_AI_HOST_IP` | `host.docker.internal`                   | Host/IP used to resolve `greyflow-ai` from the API container |

## License

MIT
