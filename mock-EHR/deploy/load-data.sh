#!/bin/bash
set -e

FHIR_URL="${FHIR_BASE_URL:-http://hapi-fhir:8080/fhir}"
DATA_DIR="/data"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "Waiting for HAPI FHIR server at $FHIR_URL..."
for i in $(seq 1 $MAX_RETRIES); do
  if curl -sf "$FHIR_URL/metadata" > /dev/null 2>&1; then
    echo "HAPI FHIR is ready."
    break
  fi
  if [ "$i" -eq "$MAX_RETRIES" ]; then
    echo "ERROR: HAPI FHIR did not become ready within $((MAX_RETRIES * RETRY_INTERVAL)) seconds."
    exit 1
  fi
  sleep $RETRY_INTERVAL
done

for bundle in "$DATA_DIR"/*.json; do
  echo "Loading $(basename "$bundle")..."
  response=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X POST "$FHIR_URL" \
    -H "Content-Type: application/fhir+json" \
    -d @"$bundle")
  if [ "$response" -ge 200 ] && [ "$response" -lt 300 ]; then
    echo "  OK ($response)"
  else
    echo "  FAILED ($response)"
    exit 1
  fi
done

echo "All bundles loaded successfully."
