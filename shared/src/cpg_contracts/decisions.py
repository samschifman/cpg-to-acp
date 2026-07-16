"""Contract types for the decision model boundary between cpg-ingester and acp-writer.

These types define the API contract. Both components depend on this package;
neither depends on the other.
"""

from datetime import datetime

from pydantic import BaseModel


class DecisionVariable(BaseModel):
    name: str
    type: str


class DecisionModelSummary(BaseModel):
    id: str
    name: str
    inputs: list[DecisionVariable]
    outputs: list[DecisionVariable]
    deployed_at: datetime | None = None
    source_cpg: str | None = None


class DecisionEvaluationRequest(BaseModel):
    model_id: str
    inputs: dict


class DecisionEvaluationResponse(BaseModel):
    model_id: str
    outputs: dict
