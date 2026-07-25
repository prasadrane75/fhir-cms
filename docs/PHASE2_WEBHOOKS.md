# Phase 2 — FHIR Observation Webhooks

Phase 2 adds an event-driven path: when HAPI FHIR receives a new **final** Observation, it notifies the CMS via a **rest-hook** webhook. The CMS queues background processing that:

1. Parses the Observation and patient ID
2. Creates or reuses an in-progress case
3. Refreshes FHIR clinical data
4. Moves the case to `AI_Review`
5. Runs the LangGraph agent
6. Pauses at `Pending_Approval` for human sign-off

## Architecture

```
HAPI FHIR (Observation created)
        │
        │  rest-hook POST
        ▼
POST /api/v1/webhooks/fhir/observation   (202 Accepted)
        │
        │  FastAPI BackgroundTasks
        ▼
CaseService.start_auto_review_for_observation()
        │
        ├── refresh FHIR patient + observations
        ├── Pending → AI_Review
        └── run LangGraph review → Pending_Approval
```

## Configuration

Add to `.env`:

```env
WEBHOOK_SECRET=change-me-in-production
WEBHOOK_CLINICAL_QUERY=Review the latest observation in context and recommend whether care management should proceed.
WEBHOOK_ENABLED=true
WEBHOOK_PUBLIC_BASE_URL=http://api:8000
```

| Variable | Purpose |
|----------|---------|
| `WEBHOOK_SECRET` | Optional shared secret sent as `X-Webhook-Secret` |
| `WEBHOOK_CLINICAL_QUERY` | Default query passed to the LangGraph agent |
| `WEBHOOK_ENABLED` | Kill switch for the endpoint |
| `WEBHOOK_PUBLIC_BASE_URL` | Base URL HAPI uses inside Docker (`http://api:8000`) |

Restart after changes:

```bash
docker compose up -d --build api hapi-fhir
```

Re-register the subscription after HAPI restarts (subscriptions are stored in HAPI's in-memory DB and are lost on container recreate):

```bash
FHIR_BASE_URL=http://localhost:8080/fhir \
WEBHOOK_URL=http://api:8000/api/v1/webhooks/fhir/observation \
WEBHOOK_SECRET=change-me-in-production \
./scripts/register_hapi_subscription.sh
```

## 1. Webhook endpoint

**URL (inside Docker network):**

```
http://api:8000/api/v1/webhooks/fhir/observation
```

**URL (from host / manual testing):**

```
http://localhost:8000/api/v1/webhooks/fhir/observation
```

**Method:** `POST`  
**Content-Type:** `application/fhir+json`  
**Optional header:** `X-Webhook-Secret: <WEBHOOK_SECRET>`

### Accepted payloads

- A single `Observation` resource
- A FHIR `Bundle` containing an `Observation` (typical HAPI subscription notification)

**Response:** `202 Accepted`

```json
{
  "status": "accepted",
  "message": "Observation event queued for automated AI review"
}
```

Processing happens in the background. Check the test UI or audit log for results.

## 2. Enable HAPI subscriptions

`docker-compose.yaml` mounts `config/hapi/application.yaml` and enables REST-hook subscriptions:

```yaml
SPRING_CONFIG_ADDITIONAL_LOCATION: "optional:file:/opt/hapi-extra/"
HAPI_FHIR_SUBSCRIPTION_RESTHOOK_ENABLED: "true"
hapi.fhir.subscription.resthook_enabled: "true"
hapi.fhir.subscription.immediately_queued: "true"
```

After changing HAPI config, recreate the container:

```bash
docker compose up -d --force-recreate hapi-fhir
```

Confirm subscriptions are enabled (should **not** say "Subscriptions are disabled"):

```bash
docker compose logs hapi-fhir | rg -i "subscription"
```

## 3. Register the subscription in HAPI

From the project root (with the stack running). The script waits up to 2 minutes for HAPI to finish starting:

```bash
chmod +x scripts/register_hapi_subscription.sh

# From host (FHIR on localhost)
FHIR_BASE_URL=http://localhost:8080/fhir \
WEBHOOK_URL=http://api:8000/api/v1/webhooks/fhir/observation \
WEBHOOK_SECRET=change-me-in-production \
./scripts/register_hapi_subscription.sh
```

If you see `Connection reset by peer`, HAPI is still booting. Wait for `REST-hook subscriptions enabled` in `docker compose logs hapi-fhir`, then rerun the script.

Or from inside the API container:

```bash
docker compose exec api sh -c '
  FHIR_BASE_URL=http://hapi-fhir:8080/fhir \
  WEBHOOK_URL=http://api:8000/api/v1/webhooks/fhir/observation \
  WEBHOOK_SECRET=change-me-in-production \
  /app/scripts/register_hapi_subscription.sh
'
```

> **Note:** HAPI must be able to reach `http://api:8000` on the Docker network. Do not use `localhost` in the subscription endpoint when registering from inside HAPI.

## 4. Manual webhook test (without HAPI subscription)

Simulate an incoming observation event:

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/fhir/observation \
  -H "Content-Type: application/fhir+json" \
  -H "X-Webhook-Secret: change-me-in-production" \
  -d '{
    "resourceType": "Observation",
    "id": "webhook-test-1",
    "status": "final",
    "code": {
      "coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}],
      "text": "Glucose"
    },
    "subject": {"reference": "Patient/1000"},
    "effectiveDateTime": "2026-07-24",
    "valueQuantity": {"value": 145, "unit": "mg/dL"}
  }'
```

Then open http://localhost:8000/ — a new case should appear and move to `Pending_Approval` after background processing.

## 5. End-to-end test with HAPI

1. Ensure patient `1000` exists in HAPI FHIR
2. Register the subscription (step 3) — status must be **`active`**
3. Post a new Observation to HAPI:

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
    "subject": {"reference": "Patient/1000"},
    "effectiveDateTime": "2026-07-24",
    "valueQuantity": {"value": 152, "unit": "mg/dL"}
  }'
```

4. Watch API logs:

```bash
docker compose logs -f api
```

5. Verify in UI or audit log:

```bash
curl http://localhost:8000/api/v1/audit
```

Look for `webhook.observation_received` and `webhook.observation_processed`.

## Case selection rules

| Existing case for patient | Webhook behavior |
|---------------------------|------------------|
| `Pending` or `AI_Review` | Reuse case, refresh observations, run review |
| `Pending_Approval`, `Approved`, `Rejected` | Create a **new** case |

Human approval is still required — the webhook automates everything **up to** `Pending_Approval`.

## Audit events

| Action | When |
|--------|------|
| `webhook.observation_received` | Webhook accepted (HTTP 202) |
| `webhook.observation_processed` | Background review completed |
| `webhook.observation_failed` | Background processing error |
| `case.ai_review` | AI review completed (existing) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 401 Invalid webhook secret | Match `X-Webhook-Secret` to `WEBHOOK_SECRET` in `.env` |
| 503 Webhook disabled | Set `WEBHOOK_ENABLED=true` |
| HAPI returns 404 on webhook | HAPI may `PUT` to `/webhooks/fhir/observation/Observation/{id}`; the API accepts both `POST` and `PUT` |
| HAPI never calls webhook | Recreate `hapi-fhir`, re-run `register_hapi_subscription.sh`, confirm status is `active`; check `docker compose logs hapi-fhir` |
| Only one auto-review for many observations | Each observation only triggers review if HAPI delivers a webhook; UI form writes to HAPI but does not call CMS directly |
| Case not created | Ensure `subject.reference` points to an existing Patient |
| AI review not running | Check API logs; verify LLM and Neo4j are configured |

## Security notes

- Always set a non-empty `WEBHOOK_SECRET` in production
- Expose the webhook only on the internal Docker network if possible
- The endpoint returns `202` immediately; failures are logged and audited asynchronously
