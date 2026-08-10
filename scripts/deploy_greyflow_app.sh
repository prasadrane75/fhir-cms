#!/usr/bin/env bash
# Deploy fhir-cms on greyflow-app.
#
# Option A — build on app server (no registry):
#   ssh greyflow-app
#   git clone <repo> && cd fhir-cms
#   cp .env.greyflow-app.example .env   # edit secrets/IPs
#   ./scripts/deploy_greyflow_app.sh up
#
# Option B — build locally, transfer image, load on app server:
#   ./scripts/deploy_greyflow_app.sh build
#   ./scripts/deploy_greyflow_app.sh save
#   scp /tmp/fhir-cms-api.tar.gz greyflow-app:/tmp/
#   ssh greyflow-app 'docker load -i /tmp/fhir-cms-api.tar.gz && cd ~/fhir-cms && ./scripts/deploy_greyflow_app.sh up'
#
# Option C — push to registry, pull on app server:
#   export FHIR_CMS_IMAGE=ghcr.io/your-org/fhir-cms-api:latest
#   ./scripts/deploy_greyflow_app.sh push
#   ssh greyflow-app 'cd ~/fhir-cms && export FHIR_CMS_IMAGE=... && ./scripts/deploy_greyflow_app.sh pull && ./scripts/deploy_greyflow_app.sh up'

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT}/docker-compose.greyflow-app.yaml"
IMAGE="${FHIR_CMS_IMAGE:-fhir-cms-api:latest}"
ARCHIVE="${FHIR_CMS_ARCHIVE:-/tmp/fhir-cms-api.tar.gz}"

cd "${ROOT}"

build() {
  echo "Building ${IMAGE}…"
  docker build -f docker/Dockerfile.prod -t "${IMAGE}" .
}

save() {
  build
  echo "Saving ${IMAGE} to ${ARCHIVE}…"
  docker save "${IMAGE}" | gzip > "${ARCHIVE}"
  echo "Transfer: scp ${ARCHIVE} greyflow-app:/tmp/"
}

push() {
  build
  docker push "${IMAGE}"
}

pull() {
  docker pull "${IMAGE}"
}

seed_neo4j() {
  echo "Seeding Neo4j knowledge graph…"
  docker compose -f "${COMPOSE_FILE}" exec -T neo4j \
    cypher-shell -u neo4j -p "${NEO4J_PASSWORD:-password}" -f /import/init.cypher
}

sync_repo() {
  if [[ ! -d "${ROOT}/.git" ]]; then
    return 0
  fi
  echo "Syncing repo to origin/main (keeps local .env)…"
  git fetch origin main
  git reset --hard origin/main
}

up() {
  sync_repo
  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "Missing .env — copy .env.greyflow-app.example to .env and edit." >&2
    exit 1
  fi
  export FHIR_CMS_IMAGE="${IMAGE}"
  docker compose -f "${COMPOSE_FILE}" pull --ignore-buildable 2>/dev/null || true
  docker compose -f "${COMPOSE_FILE}" up -d --build
  echo "Waiting for API health…"
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:${FHIR_CMS_PORT:-8001}/health" >/dev/null 2>&1; then
      echo "API healthy at http://127.0.0.1:${FHIR_CMS_PORT:-8001}/health"
      break
    fi
    sleep 2
  done
  seed_neo4j || echo "Neo4j seed skipped (run seed manually if needed)."
  echo ""
  echo "URLs (on greyflow-app):"
  echo "  API/docs:  http://127.0.0.1:${FHIR_CMS_PORT:-8001}/docs"
  echo "  Demo:      http://127.0.0.1:${FHIR_CMS_PORT:-8001}/demo/explorer"
  echo "  Dashboard: http://127.0.0.1:${FHIR_CMS_PORT:-8001}/dashboard"
}

down() {
  docker compose -f "${COMPOSE_FILE}" down
}

logs() {
  docker compose -f "${COMPOSE_FILE}" logs -f "${1:-api}"
}

case "${1:-up}" in
  build) build ;;
  save) save ;;
  push) push ;;
  pull) pull ;;
  up) up ;;
  down) down ;;
  logs) logs "${2:-}" ;;
  seed) seed_neo4j ;;
  *)
    echo "Usage: $0 {build|save|push|pull|up|down|logs|seed}" >&2
    exit 1
    ;;
esac
