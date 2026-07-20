"""Delivery Agent — sends assembled artifacts to acp-writer API."""

import logging
import time

import mlflow
import requests

from cpg_ingester.output import write_artifact

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF = 2


def _post_with_retry(url: str, data=None, json_data=None, headers=None) -> requests.Response:
    """POST with exponential backoff retry."""
    for attempt in range(MAX_RETRIES):
        try:
            if json_data is not None:
                r = requests.post(url, json=json_data, headers=headers, timeout=30)
            else:
                r = requests.post(url, data=data, headers=headers, timeout=30)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF ** (attempt + 1)
                logger.warning("Delivery attempt %d failed (%s), retrying in %ds", attempt + 1, e, wait)
                time.sleep(wait)
            else:
                raise
        except requests.HTTPError:
            raise


@mlflow.trace(name="delivery")
def delivery(state: dict) -> dict:
    """Send assembled artifacts to acp-writer API."""
    cpg_metadata = state.get("cpg_metadata", {})
    dmn_results = state.get("dmn_results", []) or []
    recommendation_results = state.get("recommendation_results", [])
    escalated_items = state.get("escalated_items", [])
    assembly_report = state.get("assembly_report", {})
    acp_writer_url = state.get("acp_writer_url", "")
    output_dir = state.get("output_dir", "output")

    if not acp_writer_url:
        logger.info("No acp_writer_url configured — skipping delivery")
        status = {"delivered": False, "reason": "no acp_writer_url configured"}
        write_artifact(output_dir, "delivery-status.json", status)
        return {"delivery_status": status}

    results = {"metadata": None, "dmn_models": [], "recommendations": None, "errors": []}

    # 1. POST CPGMetadata
    if cpg_metadata:
        try:
            r = _post_with_retry(
                f"{acp_writer_url}/api/v1/guidelines",
                json_data=cpg_metadata,
            )
            results["metadata"] = {"status": r.status_code, "cpg_id": cpg_metadata.get("cpg_id")}
            logger.info("Delivered CPGMetadata: %s", cpg_metadata.get("cpg_id"))
        except Exception as e:
            results["errors"].append(f"CPGMetadata delivery failed: {e}")
            logger.error("CPGMetadata delivery failed: %s", e)

    # 2. POST DMN models
    for dmn in dmn_results:
        dmn_xml = dmn.get("dmn_xml", "") if isinstance(dmn, dict) else ""
        if not dmn_xml:
            continue
        try:
            r = _post_with_retry(
                f"{acp_writer_url}/api/v1/decisions/models",
                data=dmn_xml,
                headers={"Content-Type": "application/xml"},
            )
            name = dmn.get("item", {}).get("name", "unknown") if isinstance(dmn, dict) else "unknown"
            results["dmn_models"].append({"status": r.status_code, "name": name})
            logger.info("Delivered DMN model: %s", name)
        except Exception as e:
            results["errors"].append(f"DMN delivery failed: {e}")
            logger.error("DMN delivery failed: %s", e)

    # 3. POST RecommendationBundle
    if recommendation_results:
        bundle = {
            "contract_version": cpg_metadata.get("contract_version", "1.0"),
            "source_cpg": cpg_metadata.get("cpg_id", "UNKNOWN"),
            "recommendations": recommendation_results if isinstance(recommendation_results, list) else [],
        }
        try:
            r = _post_with_retry(
                f"{acp_writer_url}/api/v1/knowledge/recommendations/batch",
                json_data=bundle,
            )
            results["recommendations"] = {
                "status": r.status_code,
                "count": len(bundle["recommendations"]),
            }
            logger.info("Delivered %d recommendations", len(bundle["recommendations"]))
        except Exception as e:
            results["errors"].append(f"Recommendation delivery failed: {e}")
            logger.error("Recommendation delivery failed: %s", e)

    status = {
        "delivered": True,
        "acp_writer_url": acp_writer_url,
        "results": results,
        "escalated_items_count": len(escalated_items),
    }
    write_artifact(output_dir, "delivery-status.json", status)

    if escalated_items:
        logger.warning("%d items were escalated for human review", len(escalated_items))

    if results["errors"]:
        logger.error("Delivery completed with %d errors", len(results["errors"]))
    else:
        logger.info("Delivery complete — all artifacts sent successfully")

    return {"delivery_status": status}
