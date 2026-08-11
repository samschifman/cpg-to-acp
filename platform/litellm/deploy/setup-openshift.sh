#!/usr/bin/env bash
# One-time setup for deploying LiteLLM to OpenShift.
#
# Creates an ImageStream and BuildConfig for the LiteLLM image.
# Run this ONCE before the first `helm install` of the LiteLLM chart.
#
# Usage:
#   bash platform/litellm/deploy/setup-openshift.sh [--namespace NS] [--branch BRANCH] [--tag TAG]

set -euo pipefail

NAMESPACE="${NAMESPACE:-sschifma-cpg-to-acp}"
GIT_REPO="https://github.com/samschifman/cpg-to-acp.git"
GIT_BRANCH="${GIT_BRANCH:-main}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

log() { echo "[setup-openshift] $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace) NAMESPACE="$2"; shift 2;;
    --branch) GIT_BRANCH="$2"; shift 2;;
    --tag) IMAGE_TAG="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

log "Component:  litellm"
log "Namespace:  $NAMESPACE"
log "Git branch: $GIT_BRANCH"
log "Image tag:  $IMAGE_TAG"
log ""

oc project "$NAMESPACE" 2>/dev/null || oc new-project "$NAMESPACE"

# --- ImageStream ---

log "=== Creating ImageStream ==="
oc create imagestream "litellm" -n "$NAMESPACE" 2>/dev/null \
  && log "  Created litellm" || log "  litellm already exists"

# --- BuildConfig ---

log ""
log "=== Creating BuildConfig ==="
oc apply -f - <<EOF
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: litellm
  namespace: $NAMESPACE
spec:
  source:
    type: Git
    git:
      uri: $GIT_REPO
      ref: $GIT_BRANCH
    contextDir: platform/litellm
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: deploy/Containerfile
  output:
    to:
      kind: ImageStreamTag
      name: litellm:$IMAGE_TAG
  resources:
    limits:
      cpu: "1"
      memory: 2Gi
  failedBuildsHistoryLimit: 3
  successfulBuildsHistoryLimit: 3
EOF
log "  litellm: contextDir=platform/litellm containerfile=deploy/Containerfile -> litellm:$IMAGE_TAG"

# --- Trigger build ---

log ""
log "=== Starting build ==="
oc start-build "litellm" -n "$NAMESPACE" 2>&1 | head -1

log "Waiting for build..."
for i in $(seq 1 60); do
  phase=$(oc get builds -n "$NAMESPACE" -l "openshift.io/build-config.name=litellm" -o jsonpath='{.items[-1].status.phase}' 2>/dev/null)
  if [ "$phase" = "Complete" ]; then log "  litellm: Complete"; break; fi
  if [ "$phase" = "Failed" ]; then log "  litellm: FAILED"; break; fi
  sleep 10
done

log ""
log "=== Setup complete ==="
