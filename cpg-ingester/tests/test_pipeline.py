"""Integration tests for the cpg-ingester pipeline."""

import json
import tempfile
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from cpg_ingester.output import write_artifact
from cpg_ingester.pipeline import build_pipeline


def test_pipeline_builds():
    graph = build_pipeline()
    assert graph is not None


def test_pipeline_compiles():
    graph = build_pipeline()
    compiled = graph.compile()
    assert compiled is not None


def test_pipeline_compiles_with_checkpointer():
    graph = build_pipeline()
    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)
    assert compiled is not None


SYNTHETIC_CPG = Path(__file__).parent.parent / "data" / "synthetic-hypertension-cpg.pdf"


@pytest.mark.skipif(not SYNTHETIC_CPG.exists(), reason="Synthetic CPG PDF not found")
def test_pipeline_runs_with_synthetic_cpg():
    graph = build_pipeline()
    checkpointer = MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    with tempfile.TemporaryDirectory() as tmpdir:
        state = {
            "run_id": "test-001",
            "output_dir": tmpdir,
            "pdf_path": str(SYNTHETIC_CPG),
        }
        config = {"configurable": {"thread_id": "test-001"}}
        result = compiled.invoke(state, config=config)
        assert result is not None
        assert result.get("run_id") == "test-001"
        assert len(result.get("markdown", "")) > 1000


def test_write_artifact_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        data = {"key": "value", "count": 42}
        path = write_artifact(tmpdir, "test.json", data)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["key"] == "value"


def test_write_artifact_string():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_artifact(tmpdir, "test.xml", "<root/>")
        assert path.exists()
        assert path.read_text() == "<root/>"


def test_write_artifact_nested_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = write_artifact(tmpdir, "dmn/table-1.dmn", "<definitions/>")
        assert path.exists()
        assert path.parent.name == "dmn"
