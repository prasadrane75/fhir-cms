#!/usr/bin/env bash
set -euo pipefail

FHIR_BASE_URL="${FHIR_BASE_URL:-http://localhost:8080/fhir}"
WEBHOOK_URL="${WEBHOOK_URL:-http://api:8000/api/v1/webhooks/fhir/observation}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-change-me-in-production}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

echo "Registering HAPI FHIR Subscription"
echo "  FHIR:     $FHIR_BASE_URL"
echo "  Webhook:  $WEBHOOK_URL"

wait_for_hapi() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  local attempt=0

  echo "Waiting for HAPI FHIR to accept requests (up to ${WAIT_SECONDS}s)..."
  while (( SECONDS < deadline )); do
    attempt=$((attempt + 1))
    if curl -sf "${FHIR_BASE_URL}/metadata" >/dev/null 2>&1; then
      echo "HAPI FHIR is ready (attempt ${attempt})."
      return 0
    fi
    sleep 3
  done

  echo "ERROR: HAPI FHIR is not reachable at ${FHIR_BASE_URL}." >&2
  echo "Start the stack and wait for startup to finish:" >&2
  echo "  docker compose up -d hapi-fhir" >&2
  echo "  docker compose logs -f hapi-fhir" >&2
  echo "Look for: REST-hook subscriptions enabled" >&2
  return 1
}

wait_for_hapi

RESPONSE=$(
  FHIR_BASE_URL="$FHIR_BASE_URL" \
  WEBHOOK_URL="$WEBHOOK_URL" \
  WEBHOOK_SECRET="$WEBHOOK_SECRET" \
  MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}" \
  python3 <<'PY'
import json
import os
import sys
import time
import urllib.error
import urllib.request

fhir_base_url = os.environ["FHIR_BASE_URL"].rstrip("/")
webhook_url = os.environ["WEBHOOK_URL"]
webhook_secret = os.environ["WEBHOOK_SECRET"]
max_attempts = int(os.environ.get("MAX_ATTEMPTS", "5"))

payload = {
    "resourceType": "Subscription",
    "status": "active",
    "reason": "Auto-trigger case review when final Observations arrive",
    "criteria": "Observation?status=final",
    "channel": {
        "type": "rest-hook",
        "endpoint": webhook_url,
        "payload": "application/fhir+json",
        "header": [f"X-Webhook-Secret: {webhook_secret}"],
    },
}


def request(method: str, url: str, body: dict | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def request_with_retry(method: str, url: str, body: dict | None = None) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return request(method, url, body)
        except (urllib.error.URLError, TimeoutError, ConnectionResetError) as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(3)
                continue
            raise
    raise RuntimeError("request failed") from last_error


try:
    search = request_with_retry("GET", f"{fhir_base_url}/Subscription")
    existing_id = None
    for entry in search.get("entry", []):
        sub = entry.get("resource", {})
        endpoint = (sub.get("channel") or {}).get("endpoint", "")
        if endpoint == webhook_url:
            existing_id = sub.get("id")
            break

    if existing_id:
        payload["id"] = existing_id
        result = request_with_retry("PUT", f"{fhir_base_url}/Subscription/{existing_id}", payload)
    else:
        result = request_with_retry("POST", f"{fhir_base_url}/Subscription", payload)
except Exception as exc:
    print(f"ERROR: Failed to register subscription: {exc}", file=sys.stderr)
    print(
        "HAPI may still be starting. Retry in ~30s or check: docker compose logs hapi-fhir",
        file=sys.stderr,
    )
    raise SystemExit(1) from exc

print(json.dumps(result))
PY
)

echo "$RESPONSE" | python3 -m json.tool

SUBSCRIPTION_ID=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))")
SUBSCRIPTION_STATUS=$(echo "$RESPONSE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))")

echo ""
if [[ "$SUBSCRIPTION_STATUS" == "active" ]]; then
  echo "Subscription $SUBSCRIPTION_ID is active."
else
  echo "WARNING: Subscription $SUBSCRIPTION_ID status is '$SUBSCRIPTION_STATUS' (expected 'active')."
fi

echo "Create a final Observation in HAPI to trigger the webhook."
echo "Watch API logs: docker compose logs -f api"
