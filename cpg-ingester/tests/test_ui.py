"""Tests for the cpg-ingester web UI."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from cpg_ingester.ui.app import OUTPUT_BASE, app


@pytest.fixture
def client(tmp_path):
    with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
        yield TestClient(app)


@pytest.fixture
def populated_run(tmp_path):
    run_dir = tmp_path / "test-run"
    run_dir.mkdir()
    (run_dir / "run-summary.json").write_text(json.dumps({
        "run_id": "test-run",
        "pdf_path": "/tmp/test.pdf",
        "manifest_items": 6,
        "dmn_results": 2,
        "recommendations": 4,
        "escalated_items": 0,
    }))
    (run_dir / "metadata.json").write_text(json.dumps({
        "cpg_id": "TEST-001",
        "title": "Test Guideline",
        "grading_system": "GRADE",
    }))
    (run_dir / "section-map.json").write_text(json.dumps([
        {"heading": "1. Intro", "page_start": 1, "page_end": 2, "classification": "skip"},
        {"heading": "3. Recommendations", "page_start": 3, "page_end": 5, "classification": "both"},
    ]))
    (run_dir / "manifest.json").write_text(json.dumps([
        {"type": "decision", "name": "Treatment", "id": "d1", "category": "treatment", "tier": 1, "section": "3.2"},
        {"type": "recommendation", "title": "DASH Diet", "id": "r1", "recommendation_type": "lifestyle", "section": "3.4"},
    ]))
    (run_dir / "assembly-report.json").write_text(json.dumps({
        "recommendations_count": 4,
        "dmn_models_count": 2,
        "escalated_count": 0,
        "integrity_errors": [],
    }))
    return "test-run"


class TestUploadPage:

    def test_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Upload" in r.text
        assert "CPG Ingester" in r.text

    def test_has_file_input(self, client):
        r = client.get("/")
        assert 'type="file"' in r.text
        assert 'name="pdf"' in r.text


class TestRunsPage:

    def test_empty_runs(self, client):
        r = client.get("/runs")
        assert r.status_code == 200
        assert "No runs yet" in r.text

    def test_lists_runs(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs")
        assert r.status_code == 200
        assert "test-run" in r.text


class TestRunDetailPage:

    def test_shows_metadata(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run")
        assert r.status_code == 200
        assert "TEST-001" in r.text
        assert "Test Guideline" in r.text
        assert "GRADE" in r.text

    def test_shows_section_map(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run")
        assert "Recommendations" in r.text
        assert "skip" in r.text
        assert "both" in r.text

    def test_shows_manifest(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run")
        assert "Treatment" in r.text
        assert "DASH Diet" in r.text

    def test_shows_assembly_report(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run")
        assert "Assembly Report" in r.text

    def test_lists_artifacts(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run")
        assert "run-summary.json" in r.text
        assert "manifest.json" in r.text

    def test_nonexistent_run(self, client, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/nonexistent")
        assert r.status_code == 200


class TestArtifactServing:

    def test_serves_json_artifact(self, client, populated_run, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run/artifact/metadata.json")
        assert r.status_code == 200
        data = r.json()
        assert data["cpg_id"] == "TEST-001"

    def test_404_for_missing_artifact(self, client, tmp_path):
        with patch("cpg_ingester.ui.app.OUTPUT_BASE", tmp_path):
            r = client.get("/runs/test-run/artifact/nonexistent.json")
        assert r.status_code == 404
