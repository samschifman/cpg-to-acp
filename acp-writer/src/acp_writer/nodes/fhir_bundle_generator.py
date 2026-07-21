"""FHIR Bundle Generator — produce valid FHIR R4 Bundle from Planning Brief.

Deterministic code, no LLM. Delegates to fhir_bundle_builder
for resource construction. Adds AI Transparency IG compliance
(AIAST tags, AI-Device, AI-Provenance).
"""
