"""DMN Syntax Validator — deterministic XML/namespace/structure/FEEL validation."""

import logging

import mlflow

from cpg_ingester.validators.dmn_syntax import validate_dmn_xml

logger = logging.getLogger(__name__)


@mlflow.trace(name="dmn_syntax_validator")
def dmn_syntax_validator(state: dict) -> dict:
    """Validate DMN XML syntax. Returns errors in state for retry routing."""
    logger.info("── DMN Syntax Validator ──")
    dmn_xml = state.get("dmn_xml", "")
    item = state.get("item", {})
    name = item.get("name", "unknown")

    if not dmn_xml:
        return {"syntax_errors": ["No DMN XML produced"]}

    errors = validate_dmn_xml(dmn_xml)

    if errors:
        logger.warning("DMN syntax validation failed for '%s': %d errors", name, len(errors))
        for err in errors:
            logger.warning("  %s", err)
    else:
        logger.info("DMN syntax validation passed for '%s'", name)

    return {"syntax_errors": errors}
