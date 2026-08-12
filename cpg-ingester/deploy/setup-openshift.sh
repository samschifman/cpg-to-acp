#!/usr/bin/env bash
# One-time setup for deploying cpg-ingester to OpenShift.
#
# Creates ImageStreams and BuildConfigs for cpg-ingester images.
# Run this ONCE before the first `helm install` of the cpg-ingester chart.
#
# Usage:
#   bash cpg-ingester/deploy/setup-openshift.sh [--namespace NS] [--repo URL] [--branch BRANCH] [--tag TAG] [--mode pods|monolith]

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
    -h|--help)
      echo "Usage: bash cpg-ingester/deploy/setup-openshift.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --namespace NS    OpenShift namespace (default: sschifma-cpg-to-acp)"
      echo "  --repo URL        Git repository URL (default: upstream)"
      echo "  --branch BRANCH   Git branch to build from (default: main)"
      echo "  --tag TAG         Image tag (default: latest)"
      echo "  --mode pods|monolith  Deployment mode (default: pods)"
      echo "  -h, --help        Show this help message"
      exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ "$MODE" != "pods" && "$MODE" != "monolith" ]]; then
  echo "ERROR: --mode must be 'pods' or 'monolith' (got '$MODE')"
  exit 1
fi

log "Component:  cpg-ingester"
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

if [[ "$MODE" == "pods" ]]; then
  for is in cpg-ingester-ingestion cpg-ingester-llm cpg-ingester-assembly cpg-ingester-delivery cpg-ingester-ui; do
    create_is "$is"
  done
else
  create_is "cpg-ingester"
fi

# --- BuildConfigs ---

log ""
log "=== Creating BuildConfigs ==="

if [[ "$MODE" == "pods" ]]; then
  create_bc "cpg-ingester-ingestion" "" "cpg-ingester/deploy/pods/Containerfile.ingestion"
  create_bc "cpg-ingester-llm"       "" "cpg-ingester/deploy/pods/Containerfile.llm-analysis"
  create_bc "cpg-ingester-assembly"  "" "cpg-ingester/deploy/pods/Containerfile.assembly"
  create_bc "cpg-ingester-delivery"  "" "cpg-ingester/deploy/pods/Containerfile.delivery"
  create_bc "cpg-ingester-ui"        "" "cpg-ingester/deploy/pods/Containerfile.ui"
else
  create_bc "cpg-ingester" "" "cpg-ingester/deploy/Containerfile"
fi

# --- Trigger builds ---

log ""
log "=== Starting builds ==="

if [[ "$MODE" == "pods" ]]; then
  BUILD_CONFIGS=(cpg-ingester-ingestion cpg-ingester-llm cpg-ingester-assembly cpg-ingester-delivery cpg-ingester-ui)
else
  BUILD_CONFIGS=(cpg-ingester)
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
