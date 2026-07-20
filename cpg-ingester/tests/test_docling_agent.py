"""Tests for the Docling Agent node."""

import tempfile
from pathlib import Path

import pytest

from cpg_contracts import SourceLocation
from cpg_ingester.nodes.docling_agent import (
    _build_heading_page_map,
    _extract_source_location,
    docling_agent,
)

SYNTHETIC_CPG = Path(__file__).parent.parent / "data" / "synthetic-hypertension-cpg.pdf"


@pytest.mark.skipif(not SYNTHETIC_CPG.exists(), reason="Synthetic CPG PDF not found")
class TestDoclingAgent:

    def test_produces_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"pdf_path": str(SYNTHETIC_CPG), "output_dir": tmpdir}
            result = docling_agent(state)
            assert "markdown" in result
            assert len(result["markdown"]) > 1000

    def test_produces_docling_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"pdf_path": str(SYNTHETIC_CPG), "output_dir": tmpdir}
            result = docling_agent(state)
            assert "docling_json" in result
            assert "texts" in result["docling_json"]

    def test_docling_json_has_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"pdf_path": str(SYNTHETIC_CPG), "output_dir": tmpdir}
            result = docling_agent(state)
            texts = result["docling_json"].get("texts", [])
            with_prov = [t for t in texts if t.get("prov")]
            assert len(with_prov) > 0
            first_prov = with_prov[0]["prov"][0]
            assert "page_no" in first_prov
            assert "bbox" in first_prov

    def test_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"pdf_path": str(SYNTHETIC_CPG), "output_dir": tmpdir}
            docling_agent(state)
            assert (Path(tmpdir) / "parsed.md").exists()
            assert (Path(tmpdir) / "heading-page-map.json").exists()

    def test_markdown_contains_expected_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {"pdf_path": str(SYNTHETIC_CPG), "output_dir": tmpdir}
            result = docling_agent(state)
            md = result["markdown"]
            assert "Hypertension" in md
            assert "Lisinopril" in md
            assert "DASH" in md


class TestSourceLocationHelper:

    def test_source_location_from_docling(self):
        loc = SourceLocation(page_start=3, page_end=None, bbox=[58, 683, 494, 677], source_text="test")
        assert loc.page_start == 3
        assert loc.bbox == [58, 683, 494, 677]

    def test_source_location_minimal(self):
        loc = SourceLocation(page_start=1)
        assert loc.page_end is None
        assert loc.bbox is None
