"""Terminology Lookup — multi-system clinical code find/verify.

Supports SNOMED CT (tx.fhir.org), RxNorm (rxnav.nlm.nih.gov),
LOINC and ICD-10-CM (clinicaltables.nlm.nih.gov). Results cached
with 30-day TTL. Graceful degradation on network errors.
"""
