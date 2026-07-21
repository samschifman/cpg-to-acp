"""Recommendation Schema Validator — deterministic Pydantic/cross-ref validation."""

import logging

import mlflow

from cpg_ingester.validators.rec_schema import validate_recommendations

logger = logging.getLogger(__name__)


@mlflow.trace(name="rec_schema_validator")
def rec_schema_validator(state: dict) -> dict:
    """Validate extracted recommendations against the contract schema."""
    logger.info("── Rec Schema Validator ──")
    recommendations = state.get("recommendations", [])
    items = state.get("items", [])

    if not recommendations:
        return {"schema_errors": ["No recommendations produced"]}

    manifest_ids = {item.get("id", "") for item in items if item.get("id")}

    errors = validate_recommendations(
        recs=recommendations,
        manifest_ids=manifest_ids,
    )

    if errors:
        logger.warning("Recommendation schema validation: %d errors", len(errors))
        for err in errors:
            logger.warning("  %s", err)
    else:
        logger.info("Recommendation schema validation passed (%d recs)", len(recommendations))

    return {"schema_errors": errors}
