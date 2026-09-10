"""Contract types for the decision model boundary between cpg-ingester and acp-writer.

These types define the API contract. Both components depend on this package;
neither depends on the other.
"""

from datetime import datetime
from enum import Enum
import re

from pydantic import BaseModel, Field

from cpg_contracts.recommendations import SourceLocation


def decision_model_id(name: str) -> str:
    """Return the stable wire identifier shared by ingester and writer."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "unknown").lower()).strip("-")
    return slug or "unknown"


class DecisionCategory(str, Enum):
    TREATMENT = "treatment"
    SCREENING = "screening"
    MONITORING = "monitoring"
    RISK_ASSESSMENT = "risk-assessment"
    DIAGNOSTIC = "diagnostic"


class Extraction(BaseModel):
    function: str
    params: dict = Field(default_factory=dict)


class DecisionVariable(BaseModel):
    name: str
    type: str
    description: str | None = None
    codes: list[str] | None = None
    extraction: Extraction | None = None
    """Clinical terminology codes for this variable.

    Format: ``["<system-url>|<code>", ...]`` using the FHIR token search
    format, e.g. ``["http://loinc.org|8480-6"]`` for systolic BP.

    Populated by cpg-ingester during DMN generation (see GitHub #85).
    acp-writer uses these to map DMN inputs to FHIR patient data,
    falling back to KNOWN_VARIABLE_MAP when codes are absent.
    """


class DecisionModelSummary(BaseModel):
    id: str
    name: str
    inputs: list[DecisionVariable]
    outputs: list[DecisionVariable]
    deployed_at: datetime | None = None
    source_cpg: str | None = None
    category: DecisionCategory | None = None
    modifies: list[str] | None = None
    source_location: SourceLocation | None = None


class DecisionEvaluationRequest(BaseModel):
    model_id: str
    inputs: dict


class DecisionEvaluationResponse(BaseModel):
    model_id: str
    outputs: dict
