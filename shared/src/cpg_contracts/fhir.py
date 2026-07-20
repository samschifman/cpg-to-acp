"""FHIR query contract types for MCP tool interfaces."""

from pydantic import BaseModel


class PatientSummary(BaseModel):
    patient_id: str
    name: str
    birth_date: str | None = None
    gender: str | None = None
    conditions: list[dict]
    observations: list[dict]
    medications: list[dict]
