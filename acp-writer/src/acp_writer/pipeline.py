"""LangGraph pipeline for care plan composition.

Two-phase architecture:
  Phase 1 (Clinical Reasoning): condition_scanner → guideline_resolver →
    dmn_executor → recommendation_retriever → plan_composer → brief_reviewer
  Phase 2 (FHIR Generation): fhir_bundle_generator → terminology_validator →
    fhir_syntax_validator → fhir_semantic_reviewer → fhir_server_writer
"""
