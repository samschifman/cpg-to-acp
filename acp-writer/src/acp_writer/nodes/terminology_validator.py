"""Terminology Validator — verify all coded fields in the FHIR Bundle.

Walks coded fields and verifies each via the terminology lookup tool.
Fixes invalid codes when possible, flags unresolvable in CarePlan.note.
"""
