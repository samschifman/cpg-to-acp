"""Compile/execution check against the Drools decision-service (`/jit/dmn`).

This is the harness's engine-truth signal. Because the current decision-service
surfaces a compile failure as HTTP 500 whose body contains the marker string
``Failed to build DMN runtime`` (and evaluation errors as 422), we classify by
status + marker until the error-fidelity work gives compile failures their own
422. Any other 500 or a connection error is reported as ``INFRA`` / ``SKIPPED``
and never counted as a compile failure — a flaky engine must not look like a bad
model.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import mlflow
import requests

COMPILE_FAILURE_MARKER = "Failed to build DMN runtime"


@dataclass
class CompileResult:
    status: str          # "COMPILE_OK" | "COMPILE_FAIL" | "INFRA" | "SKIPPED"
    http_status: int | None = None
    messages: list = None
    detail: str = ""

    @property
    def compiled(self) -> bool:
        return self.status == "COMPILE_OK"


def kogito_url() -> str:
    """Base URL for the decision-service, read the way the pipeline does."""
    return os.environ.get("KOGITO_URL", "http://localhost:8081").rstrip("/")


@mlflow.trace(name="dmn_compile_check")
def compile_check(dmn_xml: str, inputs: dict | None = None,
                  base_url: str | None = None, timeout: float = 30) -> CompileResult:
    """POST a DMN to ``/jit/dmn`` and classify whether it compiled.

    A 200 or 422 both mean the model *compiled* (422 = evaluation errors on the
    given inputs, which is not a compile failure). A 500 carrying the compile
    marker is a compile failure; anything else is infrastructure.
    """
    url = f"{base_url or kogito_url()}/jit/dmn"
    payload = {
        "dmn_xml_base64": base64.b64encode(dmn_xml.encode("utf-8")).decode("ascii"),
        "inputs": inputs or {},
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.RequestException as e:
        return CompileResult(status="SKIPPED", detail=f"decision-service unreachable: {e}")

    if resp.status_code in (200, 422):
        return CompileResult(status="COMPILE_OK", http_status=resp.status_code)

    body = resp.text or ""
    if resp.status_code == 500 and COMPILE_FAILURE_MARKER in body:
        return CompileResult(status="COMPILE_FAIL", http_status=500,
                             messages=[body], detail="compile failure")
    if resp.status_code == 400:
        # Malformed request or no models — treat as compile failure of the model.
        return CompileResult(status="COMPILE_FAIL", http_status=400,
                             messages=[body], detail="bad model")
    return CompileResult(status="INFRA", http_status=resp.status_code,
                         messages=[body], detail=f"unexpected {resp.status_code}")


def service_available(base_url: str | None = None, timeout: float = 5) -> bool:
    """Cheap reachability probe so the harness can mark compile metrics SKIPPED."""
    url = f"{base_url or kogito_url()}/jit/dmn"
    try:
        # An empty POST returns 400 fast if the service is up.
        requests.post(url, json={}, timeout=timeout)
        return True
    except requests.RequestException:
        return False
