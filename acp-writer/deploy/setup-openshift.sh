#!/usr/bin/env bash
# One-time setup for deploying acp-writer to OpenShift.
#
# Creates ImageStreams and BuildConfigs for acp-writer images.
# Run this ONCE before the first `helm install` of the acp-writer chart.
#
# Usage:
#   bash acp-writer/deploy/setup-openshift.sh [--namespace NS] [--repo URL] [--branch BRANCH] [--tag TAG] [--mode pods|monolith]

set -euo pipefail

NAMESPACE="${NAMESPACE:-sschifma-cpg-to-acp}"
GIT_REPO="${GIT_REPO:-https://github.com/samschifman/cpg-to-acp.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
MODE="${MODE:-pods}"

log() { echo "[setup-openshift] $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2;;
    --branch) GIT_BRANCH="$2"; shift 2;;
    --tag) IMAGE_TAG="$2"; shift 2;;
    --repo) GIT_REPO="$2"; shift 2;;
    --mode) MODE="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ "$MODE" != "pods" && "$MODE" != "monolith" ]]; then
  echo "ERROR: --mode must be 'pods' or 'monolith' (got '$MODE')"
  exit 1
fi

log "Component:  acp-writer"
log "Namespace:  $NAMESPACE"
log "Git branch: $GIT_BRANCH"
log "Image tag:  $IMAGE_TAG"
log "Mode:       $MODE"
log ""

oc project "$NAMESPACE" 2>/dev/null || oc new-project "$NAMESPACE"

create_is() {
  local name="$1"
  oc create imagestream "$name" -n "$NAMESPACE" 2>/dev/null \
    && log "  Created $name" || log "  $name already exists"
}

create_bc() {
  local name="$1" context="$2" containerfile="$3"
  oc apply -f - <<EOF
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: $name
  namespace: $NAMESPACE
spec:
  source:
    type: Git
    git:
      uri: $GIT_REPO
      ref: $GIT_BRANCH
    contextDir: $context
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: $containerfile
  output:
    to:
      kind: ImageStreamTag
      name: $name:$IMAGE_TAG
  resources:
    limits:
      cpu: "1"
      memory: 2Gi
  failedBuildsHistoryLimit: 3
  successfulBuildsHistoryLimit: 3
EOF
  log "  $name: contextDir=$context containerfile=$containerfile -> $name:$IMAGE_TAG"
}

# --- ImageStreams ---

log "=== Creating ImageStreams ==="

# Decision service is always needed
create_is "acp-writer-decision-service"

if [[ "$MODE" == "pods" ]]; then
  for is in acp-writer-patient-data acp-writer-llm acp-writer-decision acp-writer-fhir-gen acp-writer-fhir-srv acp-writer-ui acp-writer-mcp; do
    create_is "$is"
  done
else
  create_is "acp-writer"
fi

# --- BuildConfigs ---

log ""
log "=== Creating BuildConfigs ==="

# Decision service is always needed (separate build context)
create_bc "acp-writer-decision-service" "acp-writer/decision-service" "deploy/Containerfile"

if [[ "$MODE" == "pods" ]]; then
  create_bc "acp-writer-patient-data" "" "acp-writer/deploy/pods/Containerfile.patient-data"
  create_bc "acp-writer-llm"          "" "acp-writer/deploy/pods/Containerfile.llm-reasoning"
  create_bc "acp-writer-decision"     "" "acp-writer/deploy/pods/Containerfile.decision-engine"
  create_bc "acp-writer-fhir-gen"     "" "acp-writer/deploy/pods/Containerfile.fhir-generation"
  create_bc "acp-writer-fhir-srv"     "" "acp-writer/deploy/pods/Containerfile.fhir-server"
  create_bc "acp-writer-ui"           "" "acp-writer/deploy/pods/Containerfile.ui"
  create_bc "acp-writer-mcp"          "" "acp-writer/deploy/pods/Containerfile.mcp"
else
  create_bc "acp-writer" "" "acp-writer/deploy/Containerfile"
fi

# --- Trigger builds ---

log ""
log "=== Starting builds ==="

BUILD_CONFIGS=("acp-writer-decision-service")
if [[ "$MODE" == "pods" ]]; then
  BUILD_CONFIGS+=(acp-writer-patient-data acp-writer-llm acp-writer-decision acp-writer-fhir-gen acp-writer-fhir-srv acp-writer-ui acp-writer-mcp)
else
  BUILD_CONFIGS+=(acp-writer)
fi

for bc in "${BUILD_CONFIGS[@]}"; do
  oc start-build "$bc" -n "$NAMESPACE" 2>&1 | head -1
done

log "Waiting for builds..."
for bc in "${BUILD_CONFIGS[@]}"; do
  for i in $(seq 1 60); do
    phase=$(oc get builds -n "$NAMESPACE" -l "openshift.io/build-config.name=$bc" -o jsonpath='{.items[-1].status.phase}' 2>/dev/null)
    if [ "$phase" = "Complete" ]; then log "  $bc: Complete"; break; fi
    if [ "$phase" = "Failed" ]; then log "  $bc: FAILED"; break; fi
    sleep 10
  done
done

log ""
log "=== Setup complete ==="
