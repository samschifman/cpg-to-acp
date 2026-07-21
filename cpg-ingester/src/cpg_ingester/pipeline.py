"""LangGraph pipeline definition for cpg-ingester.

Two-phase architecture:
  Phase 1 (Analysis): sequential nodes build a manifest
  Phase 2 (Generation): per-item pipelines with review loops, then assembly + delivery
"""

import logging

from langgraph.graph import END, START, StateGraph

from cpg_ingester.nodes.assembly import assembly
from cpg_ingester.nodes.classification_reviewer import classification_reviewer
from cpg_ingester.nodes.content_filter import content_filter
from cpg_ingester.nodes.delivery import delivery
from cpg_ingester.nodes.dmn_creator import dmn_creator
from cpg_ingester.nodes.dmn_semantic_reviewer import dmn_semantic_reviewer
from cpg_ingester.nodes.dmn_syntax_validator import dmn_syntax_validator
from cpg_ingester.nodes.docling_agent import docling_agent
from cpg_ingester.nodes.item_identifier import item_identifier
from cpg_ingester.nodes.metadata_extractor import metadata_extractor
from cpg_ingester.nodes.rec_extractor import rec_extractor
from cpg_ingester.nodes.rec_schema_validator import rec_schema_validator
from cpg_ingester.nodes.rec_semantic_reviewer import rec_semantic_reviewer
from cpg_ingester.nodes.structure_analyzer import structure_analyzer
from cpg_ingester.state import CPGIngesterState, DMNPipelineState, RecPipelineState

logger = logging.getLogger(__name__)

MAX_CLASSIFICATION_REVIEWS = 2
MAX_DMN_REVIEWS = 2
MAX_REC_REVIEWS = 2


# --- Phase 1 routing ---

def _route_after_classification_review(state: CPGIngesterState) -> str:
    if not state.get("classification_review_feedback"):
        return "metadata_extractor"
    if state.get("classification_review_count", 0) >= MAX_CLASSIFICATION_REVIEWS:
        logger.warning("Classification review exhausted after %d iterations", MAX_CLASSIFICATION_REVIEWS)
        return "metadata_extractor"
    return "item_identifier"


# --- DMN subgraph routing ---

def _route_after_dmn_syntax(state: DMNPipelineState) -> str:
    if state.get("syntax_errors"):
        if state.get("review_count", 0) >= MAX_DMN_REVIEWS:
            return "dmn_escalate"
        return "dmn_creator"
    return "dmn_semantic_reviewer"


def _route_after_dmn_semantic(state: DMNPipelineState) -> str:
    if state.get("semantic_discrepancies"):
        if state.get("review_count", 0) >= MAX_DMN_REVIEWS:
            return "dmn_escalate"
        return "dmn_creator"
    return "dmn_accept"


def _dmn_accept(state: DMNPipelineState) -> dict:
    logger.info("DMN accepted: %s", state.get("item", {}).get("name", "unknown"))
    return {"escalated": False}


def _dmn_escalate(state: DMNPipelineState) -> dict:
    logger.warning("DMN escalated for human review: %s", state.get("item", {}).get("name", "unknown"))
    return {"escalated": True}


# --- Rec subgraph routing ---

def _route_after_rec_schema(state: RecPipelineState) -> str:
    if state.get("schema_errors"):
        if state.get("review_count", 0) >= MAX_REC_REVIEWS:
            return "rec_escalate"
        return "rec_extractor"
    return "rec_semantic_reviewer"


def _route_after_rec_semantic(state: RecPipelineState) -> str:
    if state.get("semantic_discrepancies"):
        if state.get("review_count", 0) >= MAX_REC_REVIEWS:
            return "rec_escalate"
        return "rec_extractor"
    return "rec_accept"


def _rec_accept(state: RecPipelineState) -> dict:
    logger.info("Recommendations accepted for section")
    return {"escalated": False}


def _rec_escalate(state: RecPipelineState) -> dict:
    logger.warning("Recommendations escalated for human review")
    return {"escalated": True}


# --- Subgraph builders ---

def _build_dmn_subgraph() -> StateGraph:
    graph = StateGraph(DMNPipelineState)

    graph.add_node("dmn_creator", dmn_creator)
    graph.add_node("dmn_syntax_validator", dmn_syntax_validator)
    graph.add_node("dmn_semantic_reviewer", dmn_semantic_reviewer)
    graph.add_node("dmn_accept", _dmn_accept)
    graph.add_node("dmn_escalate", _dmn_escalate)

    graph.add_edge(START, "dmn_creator")
    graph.add_edge("dmn_creator", "dmn_syntax_validator")
    graph.add_conditional_edges("dmn_syntax_validator", _route_after_dmn_syntax, {
        "dmn_semantic_reviewer": "dmn_semantic_reviewer",
        "dmn_creator": "dmn_creator",
        "dmn_escalate": "dmn_escalate",
    })
    graph.add_conditional_edges("dmn_semantic_reviewer", _route_after_dmn_semantic, {
        "dmn_accept": "dmn_accept",
        "dmn_creator": "dmn_creator",
        "dmn_escalate": "dmn_escalate",
    })
    graph.add_edge("dmn_accept", END)
    graph.add_edge("dmn_escalate", END)

    return graph


def _build_rec_subgraph() -> StateGraph:
    graph = StateGraph(RecPipelineState)

    graph.add_node("rec_extractor", rec_extractor)
    graph.add_node("rec_schema_validator", rec_schema_validator)
    graph.add_node("rec_semantic_reviewer", rec_semantic_reviewer)
    graph.add_node("rec_accept", _rec_accept)
    graph.add_node("rec_escalate", _rec_escalate)

    graph.add_edge(START, "rec_extractor")
    graph.add_edge("rec_extractor", "rec_schema_validator")
    graph.add_conditional_edges("rec_schema_validator", _route_after_rec_schema, {
        "rec_semantic_reviewer": "rec_semantic_reviewer",
        "rec_extractor": "rec_extractor",
        "rec_escalate": "rec_escalate",
    })
    graph.add_conditional_edges("rec_semantic_reviewer", _route_after_rec_semantic, {
        "rec_accept": "rec_accept",
        "rec_extractor": "rec_extractor",
        "rec_escalate": "rec_escalate",
    })
    graph.add_edge("rec_accept", END)
    graph.add_edge("rec_escalate", END)

    return graph


# --- Phase 2 generation node ---

def _generate_all(state: CPGIngesterState) -> dict:
    """Run DMN and Rec subgraphs for each manifest item.

    Results are written to the output directory by each subgraph node
    AND returned in state for distributed mode (assembly can use either).
    """
    manifest = state.get("item_manifest", [])
    if not manifest:
        logger.warning("Empty manifest — skipping generation")
        return {}

    shared = {
        "abbreviations": state.get("abbreviations", {}),
        "litellm_url": state.get("litellm_url", ""),
        "llm_model": state.get("llm_model", ""),
        "llm_api_key": state.get("llm_api_key", ""),
        "output_dir": state.get("output_dir", ""),
    }

    dmn_graph = _build_dmn_subgraph().compile()
    rec_graph = _build_rec_subgraph().compile()

    dmn_results = []
    decisions = [i for i in manifest if i.get("type") == "decision"]
    for item in decisions:
        logger.info("Generating DMN for: %s", item.get("name", "?"))
        try:
            result = dmn_graph.invoke({
                "item": item,
                "source_pages": item.get("source_pages", ""),
                **shared,
            })
            if result.get("dmn_xml") and not result.get("escalated"):
                dmn_results.append({
                    "dmn_xml": result["dmn_xml"],
                    "item": item,
                    "decision_model_summary": result.get("decision_model_summary", {}),
                })
        except Exception as e:
            logger.error("DMN generation failed for '%s': %s", item.get("name"), e)

    all_recs = []
    seen_sections = set()
    recommendations = [i for i in manifest if i.get("type") == "recommendation"]
    for item in recommendations:
        section = item.get("section", "default")
        if section in seen_sections:
            continue
        seen_sections.add(section)
        section_items = [i for i in recommendations if i.get("section") == section]
        logger.info("Extracting recommendations for section: %s (%d items)", section, len(section_items))
        try:
            result = rec_graph.invoke({
                "items": section_items,
                "source_pages": item.get("source_pages", ""),
                "grading_definitions": state.get("grading_definitions", ""),
                **shared,
            })
            recs = result.get("recommendations", [])
            if recs and not result.get("escalated"):
                all_recs.extend(recs)
        except Exception as e:
            logger.error("Rec extraction failed for section '%s': %s", section, e)

    return {
        "dmn_results": dmn_results,
        "recommendation_results": all_recs,
    }


# --- Main pipeline ---

def build_pipeline() -> StateGraph:
    """Build the full cpg-ingester pipeline graph."""
    graph = StateGraph(CPGIngesterState)

    # Phase 1: Analysis (sequential with classification review loop)
    graph.add_node("docling_agent", docling_agent)
    graph.add_node("structure_analyzer", structure_analyzer)
    graph.add_node("content_filter", content_filter)
    graph.add_node("item_identifier", item_identifier)
    graph.add_node("classification_reviewer", classification_reviewer)
    graph.add_node("metadata_extractor", metadata_extractor)

    # Phase 2: Generation + Assembly + Delivery
    graph.add_node("generate", _generate_all)
    graph.add_node("assembly", assembly)
    graph.add_node("delivery", delivery)

    # Phase 1 edges
    graph.add_edge(START, "docling_agent")
    graph.add_edge("docling_agent", "structure_analyzer")
    graph.add_edge("structure_analyzer", "content_filter")
    graph.add_edge("content_filter", "item_identifier")
    graph.add_edge("item_identifier", "classification_reviewer")
    graph.add_conditional_edges(
        "classification_reviewer",
        _route_after_classification_review,
        {
            "metadata_extractor": "metadata_extractor",
            "item_identifier": "item_identifier",
        },
    )

    # Phase 2 edges
    graph.add_edge("metadata_extractor", "generate")
    graph.add_edge("generate", "assembly")
    graph.add_edge("assembly", "delivery")
    graph.add_edge("delivery", END)

    return graph
