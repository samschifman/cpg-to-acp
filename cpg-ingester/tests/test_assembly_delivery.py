"""Tests for Assembly Agent and Delivery Agent nodes."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cpg_ingester.nodes.assembly import (
    _check_integrity,
    _resolve_cross_references,
    assembly,
)
from cpg_ingester.nodes.delivery import delivery


# --- Assembly tests ---

class TestCrossReferenceResolution:

    def test_resolves_valid_string_refs(self):
        recs = [
            {"id": "aaa", "cross_references": ["bbb"]},
            {"id": "bbb", "cross_references": ["aaa"]},
        ]
        result = _resolve_cross_references(recs, [])
        assert result[0]["cross_references"][0]["target_id"] == "bbb"
        assert result[1]["cross_references"][0]["target_id"] == "aaa"

    def test_resolves_valid_dict_refs(self):
        recs = [
            {"id": "aaa", "cross_references": [{"target_id": "bbb", "relationship": "related"}]},
            {"id": "bbb", "cross_references": []},
        ]
        result = _resolve_cross_references(recs, [])
        assert result[0]["cross_references"][0]["target_id"] == "bbb"

    def test_removes_missing_refs(self):
        recs = [
            {"id": "aaa", "cross_references": ["nonexistent"]},
        ]
        result = _resolve_cross_references(recs, [])
        assert result[0]["cross_references"] is None

    def test_resolves_refs_to_dmn(self):
        recs = [
            {"id": "aaa", "cross_references": ["dmn-1"]},
        ]
        dmn_results = [{"decision_model_summary": {"id": "dmn-1"}}]
        result = _resolve_cross_references(recs, dmn_results)
        assert result[0]["cross_references"][0]["target_id"] == "dmn-1"

    def test_handles_empty_refs(self):
        recs = [{"id": "aaa", "cross_references": []}]
        result = _resolve_cross_references(recs, [])
        assert result[0]["cross_references"] is None

    def test_handles_null_refs(self):
        recs = [{"id": "aaa", "cross_references": None}]
        result = _resolve_cross_references(recs, [])
        assert result[0]["cross_references"] is None


class TestIntegrityChecks:

    def test_passes_valid_data(self):
        recs = [{"id": "aaa", "source_cpg": "CPG-001"}]
        dmn = [{"decision_model_summary": {"id": "dmn-1"}}]
        errors = _check_integrity(recs, dmn, {"cpg_id": "CPG-001"})
        assert errors == []

    def test_catches_duplicate_rec_ids(self):
        recs = [{"id": "aaa"}, {"id": "aaa"}]
        errors = _check_integrity(recs, [], {"cpg_id": "CPG-001"})
        assert any("Duplicate recommendation" in e for e in errors)

    def test_catches_mismatched_source_cpg(self):
        recs = [{"id": "aaa", "source_cpg": "WRONG"}]
        errors = _check_integrity(recs, [], {"cpg_id": "CPG-001"})
        assert any("source_cpg" in e for e in errors)

    def test_tbd_source_cpg_is_ok(self):
        recs = [{"id": "aaa", "source_cpg": "TBD"}]
        errors = _check_integrity(recs, [], {"cpg_id": "CPG-001"})
        assert errors == []

    def test_catches_empty_output(self):
        errors = _check_integrity([], [], {"cpg_id": "CPG-001"})
        assert any("No recommendations" in e for e in errors)


class TestAssemblyNode:

    def _write_rec_file(self, tmpdir, filename, recs):
        Path(tmpdir, filename).write_text(json.dumps(recs))

    def _write_dmn_file(self, tmpdir, name, xml="<definitions/>"):
        dmn_dir = Path(tmpdir) / "dmn"
        dmn_dir.mkdir(exist_ok=True)
        (dmn_dir / f"{name}.dmn").write_text(xml)

    def test_assembles_recommendations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_rec_file(tmpdir, "recommendations-3.1.json", [
                {"id": "r1", "source_cpg": "TBD", "title": "A", "cross_references": []},
                {"id": "r2", "source_cpg": "TBD", "title": "B", "cross_references": []},
            ])
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001", "contract_version": "1.0"},
                "item_manifest": [],
                "output_dir": tmpdir,
            }
            result = assembly(state)
            assert len(result["recommendation_results"]) == 2
            assert all(r["source_cpg"] == "CPG-001" for r in result["recommendation_results"])

    def test_fills_tbd_source_cpg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_rec_file(tmpdir, "recommendations-3.1.json", [
                {"id": "r1", "source_cpg": "TBD", "cross_references": []},
            ])
            state = {
                "cpg_metadata": {"cpg_id": "MY-CPG"},
                "item_manifest": [],
                "output_dir": tmpdir,
            }
            result = assembly(state)
            assert result["recommendation_results"][0]["source_cpg"] == "MY-CPG"

    def test_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._write_rec_file(tmpdir, "recommendations-3.1.json", [
                {"id": "r1", "source_cpg": "TBD", "cross_references": []},
            ])
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001"},
                "item_manifest": [],
                "output_dir": tmpdir,
            }
            assembly(state)
            assert (Path(tmpdir) / "recommendation-bundle.json").exists()
            assert (Path(tmpdir) / "assembly-report.json").exists()

    def test_collects_escalated_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001"},
                "item_manifest": [{"id": "x", "escalated": True}],
                "output_dir": tmpdir,
            }
            result = assembly(state)
            assert len(result["escalated_items"]) >= 1
            assert (Path(tmpdir) / "escalated-items.json").exists()


# --- Delivery tests ---

class TestDeliveryNode:

    def test_skips_when_no_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001"},
                "dmn_results": [],
                "recommendation_results": [],
                "escalated_items": [],
                "assembly_report": {},
                "acp_writer_url": "",
                "output_dir": tmpdir,
            }
            result = delivery(state)
            assert result["delivery_status"]["delivered"] is False
            assert (Path(tmpdir) / "delivery-status.json").exists()

    def test_delivers_all_artifacts(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("cpg_ingester.nodes.delivery.requests.post", return_value=mock_response) as mock_post:
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001", "title": "Test", "contract_version": "1.0"},
                "dmn_results": [{"dmn_xml": "<definitions/>", "item": {"name": "D1"}}],
                "recommendation_results": [{"id": "r1", "title": "R1"}],
                "escalated_items": [],
                "assembly_report": {},
                "acp_writer_url": "http://localhost:8082",
                "output_dir": tmpdir,
            }
            result = delivery(state)

            assert result["delivery_status"]["delivered"] is True
            assert mock_post.call_count == 3
            urls = [call.args[0] for call in mock_post.call_args_list]
            assert any("guidelines" in u for u in urls)
            assert any("decisions" in u for u in urls)
            assert any("recommendations" in u for u in urls)

    def test_handles_connection_error(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("cpg_ingester.nodes.delivery.requests.post", side_effect=Exception("Connection refused")), \
             patch("cpg_ingester.nodes.delivery.time.sleep"):
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001"},
                "dmn_results": [],
                "recommendation_results": [],
                "escalated_items": [],
                "assembly_report": {},
                "acp_writer_url": "http://localhost:8082",
                "output_dir": tmpdir,
            }
            result = delivery(state)

            assert len(result["delivery_status"]["results"]["errors"]) > 0

    def test_writes_delivery_status(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("cpg_ingester.nodes.delivery.requests.post", return_value=mock_response):
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001", "contract_version": "1.0"},
                "dmn_results": [],
                "recommendation_results": [{"id": "r1"}],
                "escalated_items": [],
                "assembly_report": {},
                "acp_writer_url": "http://localhost:8082",
                "output_dir": tmpdir,
            }
            delivery(state)

            status_file = Path(tmpdir) / "delivery-status.json"
            assert status_file.exists()
            status = json.loads(status_file.read_text())
            assert status["delivered"] is True

    def test_reports_escalated_count(self):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.raise_for_status = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir, \
             patch("cpg_ingester.nodes.delivery.requests.post", return_value=mock_response):
            state = {
                "cpg_metadata": {"cpg_id": "CPG-001", "contract_version": "1.0"},
                "dmn_results": [],
                "recommendation_results": [],
                "escalated_items": [{"name": "Bad item"}, {"name": "Another"}],
                "assembly_report": {},
                "acp_writer_url": "http://localhost:8082",
                "output_dir": tmpdir,
            }
            result = delivery(state)
            assert result["delivery_status"]["escalated_items_count"] == 2
