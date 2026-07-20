"""Contract types for the decision model boundary between cpg-ingester and acp-writer.

These types define the API contract. Both components depend on this package;
neither depends on the other.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DecisionCategory(str, Enum):
    TREATMENT = "treatment"
    SCREENING = "screening"
    MONITORING = "monitoring"
    RISK_ASSESSMENT = "risk-assessment"
    DIAGNOSTIC = "diagnostic"


class DecisionVariable(BaseModel):
    name: str
    type: str
    description: str | None = None
    codes: list[str] | None = None


class DecisionModelSummary(BaseModel):
    id: str
    name: str
    inputs: list[DecisionVariable]
    outputs: list[DecisionVariable]
    deployed_at: datetime | None = None
    source_cpg: str | None = None
    category: DecisionCategory | None = None
    modifies: list[str] | None = None


class DecisionEvaluationRequest(BaseModel):
    model_id: str
    inputs: dict


class DecisionEvaluationResponse(BaseModel):
    model_id: str
    outputs: dict
