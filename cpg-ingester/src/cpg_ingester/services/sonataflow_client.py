"""SonataFlow REST client and workflow state mapping for the BFF."""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)

WORKFLOW_NAME = "cpgingester"

PIPELINE_STEPS = [
    "Parse", "Analyze", "ReviewManifest",
    "Generate", "ReviewArtifacts",
    "Assemble", "Deliver", "Done",
]

_STATE_TO_RUN_STATUS = {
    "Parse": "parsing",
    "Analyze": "analyzing",
    "ReviewManifest": "awaiting_manifest_review",
    "Generate": "generating",
    "ReviewArtifacts": "awaiting_artifact_review",
    "Assemble": "assembling",
    "Deliver": "delivering",
    "Done": "completed",
}

_REVIEW_GATE_MAP = {
    "ReviewManifest": "manifest",
    "ReviewArtifacts": "pre-delivery",
}

_REVIEW_EVENT_TYPE = {
    "manifest": "manifest-reviewed",
    "pre-delivery": "artifacts-reviewed",
}


def infer_current_state(data: dict, instance_status: str) -> str:
    """Determine the active pipeline step from workflow data."""
    if instance_status == "COMPLETED" or data.get("status") == "completed":
        return "Done"
    if instance_status in ("ERROR", "ABORTED"):
        return "Failed"

    if "deliveryResult" in data:
        return "Done"
    if "assemblyResult" in data:
        return "Deliver"
    if data.get("artifactsReview", {}).get("action") == "approve":
        return "Assemble"
    if "generateResult" in data:
        return "ReviewArtifacts"
    if data.get("manifestReview", {}).get("action") == "approve":
        return "Generate"
    if "analysisResult" in data:
        return "ReviewManifest"
    if "parseResult" in data:
        return "Analyze"
    return "Parse"


def _step_timestamps(data: dict, created_at: str) -> dict[str, dict[str, str]]:
    """Build a map of step name -> {startedAt, completedAt} from result timestamps.

    Each step starts when the previous step completed. The chain:
    created_at -> Parse -> Analyze -> ReviewManifest -> Generate ->
    ReviewArtifacts -> Assemble -> Deliver -> Done
    """
    timestamps: dict[str, dict[str, str]] = {}
    prev = created_at

    step_result_keys = [
        ("Parse", "parseResult"),
        ("Analyze", "analysisResult"),
        ("ReviewManifest", "manifestReview"),
        ("Generate", "generateResult"),
        ("ReviewArtifacts", "artifactsReview"),
        ("Assemble", "assemblyResult"),
        ("Deliver", "deliveryResult"),
    ]

    for step_name, result_key in step_result_keys:
        result = data.get(result_key)
        if not result or not isinstance(result, dict):
            if prev:
                timestamps[step_name] = {"startedAt": prev}
            break
        completed = result.get("completed_at", "")
        entry: dict[str, str] = {}
        if prev:
            entry["startedAt"] = prev
        if completed:
            entry["completedAt"] = completed
        timestamps[step_name] = entry
        prev = completed or prev

    if data.get("status") == "completed" or "deliveryResult" in data:
        delivery = data.get("deliveryResult", {})
        done_at = delivery.get("completed_at", "")
        if done_at:
            timestamps["Done"] = {"startedAt": done_at, "completedAt": done_at}

    return timestamps


def build_steps(current_state: str, data: dict | None = None, created_at: str = "") -> list[dict]:
    """Build the steps array the UI expects from the current state."""
    ts = _step_timestamps(data or {}, created_at) if data else {}
    steps = []
    reached = False
    for name in PIPELINE_STEPS:
        if name == current_state:
            reached = True
            step: dict = {"name": name, "status": "active"}
        elif not reached:
            step = {"name": name, "status": "completed"}
        else:
            step = {"name": name, "status": "pending"}
        if name in ts:
            step.update(ts[name])
        steps.append(step)
    if current_state == "Done":
        for s in steps:
            s["status"] = "completed"
    if current_state == "Failed":
        for s in steps:
            if s["status"] == "active":
                s["status"] = "failed"
                break
    return steps


def map_to_run_summary(instance: dict) -> dict[str, Any]:
    """Map a SonataFlow workflow instance to a RunSummary for the dashboard."""
    data = instance.get("workflowdata", {})
    status = instance.get("status", "ACTIVE")
    current_state = infer_current_state(data, status)
    return {
        "id": instance["id"],
        "status": _STATE_TO_RUN_STATUS.get(current_state, "parsing"),
        "cpgName": data.get("cpg_name", "Unknown CPG"),
        "createdAt": instance.get("startDate") or data.get("created_at", ""),
        "currentStep": current_state,
    }


def map_to_run_detail(instance: dict) -> dict[str, Any]:
    """Map a SonataFlow workflow instance to a RunDetail for the detail view.

    Returns workflow data as-is — artifact refs are NOT resolved here.
    Use ``artifact_resolver.enrich_run_detail`` to hydrate refs from MinIO.
    """
    data = instance.get("workflowdata", {})
    status = instance.get("status", "ACTIVE")
    current_state = infer_current_state(data, status)

    created_at = instance.get("startDate") or data.get("created_at", "")
    detail: dict[str, Any] = {
        "id": instance["id"],
        "status": _STATE_TO_RUN_STATUS.get(current_state, "parsing"),
        "cpgName": data.get("cpg_name", "Unknown CPG"),
        "createdAt": created_at,
        "steps": build_steps(current_state, data, created_at),
        "workflowData": {
            "analysisResult": data.get("analysisResult"),
            "generateResult": data.get("generateResult"),
            "assemblyResult": data.get("assemblyResult"),
            "deliveryResult": data.get("deliveryResult"),
        },
    }

    review_type = _REVIEW_GATE_MAP.get(current_state)
    if review_type:
        detail["awaitingReview"] = review_type

    if current_state == "ReviewManifest":
        detail["reviewIteration"] = data.get("manifestReviewCount", 0)
        prev = data.get("manifestReview")
        if prev and prev.get("action") == "request_changes":
            detail["previousFeedback"] = prev
    elif current_state == "ReviewArtifacts":
        detail["reviewIteration"] = data.get("artifactReviewCount", 0)
        prev = data.get("artifactsReview")
        if prev and prev.get("action") == "request_changes":
            detail["previousFeedback"] = prev

    return detail


class SonataFlowClient:
    """REST client for the SonataFlow cpgingester workflow."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def start_workflow(self, pdf_ref: str, cpg_name: str) -> dict:
        resp = requests.post(
            f"{self.base_url}/{WORKFLOW_NAME}",
            json={
                "pdf_ref": pdf_ref,
                "cpg_name": cpg_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def list_instances(self) -> list[dict]:
        resp = requests.get(
            f"{self.base_url}/{WORKFLOW_NAME}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_instance(self, instance_id: str) -> dict:
        resp = requests.get(
            f"{self.base_url}/{WORKFLOW_NAME}/{instance_id}",
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def abort_instance(self, instance_id: str) -> None:
        resp = requests.delete(
            f"{self.base_url}/{WORKFLOW_NAME}/{instance_id}",
            timeout=10,
        )
        resp.raise_for_status()

    def send_review(self, instance_id: str, gate: str, review_data: dict) -> None:
        event_type = _REVIEW_EVENT_TYPE[gate]
        resp = requests.post(
            self.base_url,
            json=review_data,
            headers={
                "Content-Type": "application/json",
                "ce-specversion": "1.0",
                "ce-id": str(uuid4()),
                "ce-source": "bff",
                "ce-type": event_type,
                "ce-kogitoprocrefid": instance_id,
            },
            timeout=10,
        )
        resp.raise_for_status()
