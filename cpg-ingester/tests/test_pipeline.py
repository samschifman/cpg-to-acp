"""Integration tests for the cpg-ingester pipeline."""

from cpg_ingester.pipeline import build_pipeline


def test_pipeline_builds():
    graph = build_pipeline()
    assert graph is not None


def test_pipeline_compiles():
    graph = build_pipeline()
    compiled = graph.compile()
    assert compiled is not None
