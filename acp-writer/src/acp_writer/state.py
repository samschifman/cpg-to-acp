"""LangGraph state definition for the care plan composition pipeline."""

from typing import Any, TypedDict


class CarePlanComposerState(TypedDict, total=False):
    """Top-level state for the acp-writer care plan pipeline.

    Phase 1 (Clinical Reasoning) populates conditions, guidelines, DMN results,
    recommendations, and the planning brief.
    Phase 2 (FHIR Generation) produces and validates the FHIR bundle.
    """

    # Run metadata
    run_id: str
    output_dir: str
    litellm_url: str
    llm_model: str
    llm_api_key: str

    # Input
    ips_bundle: dict[str, Any]

    # Phase 1: Condition Scanner outputs
    patient_reference: str
    patient_demographics: dict[str, Any]
    condition_codes: list[dict[str, str]]
    medication_codes: list[dict[str, str]]
    allergy_codes: list[dict[str, str]]

    # Phase 1: Guideline Resolver outputs
    applicable_cpgs: list[dict[str, Any]]
    applicable_dmn_models: list[dict[str, Any]]
    dmn_dependency_graph: list[list[str]]

    # Phase 1: DMN Executor outputs
    dmn_results: list[dict[str, Any]]

    # Phase 1: Recommendation Retriever outputs
    recommendations: list[dict[str, Any]]

    # Phase 1: Plan Composer outputs
    planning_brief: dict[str, Any]

    # Phase 1: Brief Reviewer
    brief_review_count: int
    brief_review_feedback: str

    # Phase 2: FHIR Bundle Generator outputs
    fhir_bundle: dict[str, Any]

    # Phase 2: Terminology Validator outputs
    terminology_issues: list[dict[str, str]]

    # Phase 2: FHIR Syntax Validator outputs
    syntax_errors: list[str]

    # Phase 2: FHIR Semantic Reviewer
    fhir_review_count: int
    fhir_review_feedback: str

    # Phase 2: FHIR Server Writer outputs
    fhir_server_response: dict[str, Any]
    careplan_id: str
    delivery_status: str
