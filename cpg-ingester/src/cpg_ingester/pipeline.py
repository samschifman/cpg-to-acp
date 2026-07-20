"""LangGraph pipeline definition for cpg-ingester.

Two-phase architecture:
  Phase 1 (Analysis): sequential nodes build a manifest
  Phase 2 (Generation): parallel per-item pipelines with review loops
"""

import logging

from langgraph.graph import END, START, StateGraph

from cpg_ingester.nodes.assembly import assembly
from cpg_ingester.nodes.classification_reviewer import classification_reviewer
from cpg_ingester.nodes.content_filter import content_filter
from cpg_ingester.nodes.delivery import delivery
from cpg_ingester.nodes.docling_agent import docling_agent
from cpg_ingester.nodes.item_identifier import item_identifier
from cpg_ingester.nodes.metadata_extractor import metadata_extractor
from cpg_ingester.nodes.structure_analyzer import structure_analyzer
from cpg_ingester.state import CPGIngesterState

logger = logging.getLogger(__name__)

MAX_CLASSIFICATION_REVIEWS = 2


def _route_after_classification_review(state: CPGIngesterState) -> str:
    if not state.get("classification_review_feedback"):
        return "metadata_extractor"
    if state.get("classification_review_count", 0) >= MAX_CLASSIFICATION_REVIEWS:
        logger.warning("Classification review exhausted after %d iterations, proceeding", MAX_CLASSIFICATION_REVIEWS)
        return "metadata_extractor"
    return "item_identifier"


def build_pipeline() -> StateGraph:
    """Build the Phase 1 analysis graph.

    Phase 2 (generation with fan-out) will be added in Step 2 when
    subgraphs are wired up.
    """
    graph = StateGraph(CPGIngesterState)

    # Phase 1: Analysis (sequential with one review loop)
    graph.add_node("docling_agent", docling_agent)
    graph.add_node("structure_analyzer", structure_analyzer)
    graph.add_node("content_filter", content_filter)
    graph.add_node("item_identifier", item_identifier)
    graph.add_node("classification_reviewer", classification_reviewer)
    graph.add_node("metadata_extractor", metadata_extractor)

    # Phase 2: Assembly + Delivery (stubs for now)
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

    # Phase 2 fan-out will be inserted here (Step 2)
    # For now, wire directly through assembly → delivery
    graph.add_edge("metadata_extractor", "assembly")
    graph.add_edge("assembly", "delivery")
    graph.add_edge("delivery", END)

    return graph
