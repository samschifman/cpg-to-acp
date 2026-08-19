"""Contract conformance: our models/routes match acp-writer/api/bff-openapi.yaml."""

from pathlib import Path

import yaml

from acp_writer.services import bff_models as m

SPEC_PATH = Path(__file__).parents[2] / "acp-writer" / "api" / "bff-openapi.yaml"
# When run from the acp-writer/ dir the repo layout differs; resolve robustly:
if not SPEC_PATH.exists():
    SPEC_PATH = Path(__file__).parents[1] / "api" / "bff-openapi.yaml"


def _spec():
    return yaml.safe_load(SPEC_PATH.read_text())


def _schema_props(spec, name):
    return set(spec["components"]["schemas"][name]["properties"].keys())


def _model_aliases(model):
    return {f.alias or n for n, f in model.model_fields.items()}


def test_model_fields_match_contract_schemas():
    spec = _spec()
    pairs = {
        "CodedItem": m.CodedItem,
        "PatientSummary": m.PatientSummary,
        "PlanGoal": m.PlanGoal,
        "PlanActivity": m.PlanActivity,
        "PlanConflict": m.PlanConflict,
        "CarePlanView": m.CarePlanView,
        "FeedbackItem": m.FeedbackItem,
        "ReviewAction": m.ReviewAction,
        "RunCreated": m.RunCreated,
        "PipelineStep": m.PipelineStep,
        "RunError": m.RunError,
        "RunSummary": m.RunSummary,
        "RunDetail": m.RunDetail,
        "CarePlanSummary": m.CarePlanSummary,
        "SystemStatus": m.SystemStatus,
        "Error": m.Error,
    }
    mismatches = {}
    for name, model in pairs.items():
        want = _schema_props(spec, name)
        got = _model_aliases(model)
        if want != got:
            mismatches[name] = {"missing": sorted(want - got), "extra": sorted(got - want)}
    assert not mismatches, mismatches


def test_careplan_detail_is_summary_plus_patient_and_view():
    spec = _spec()
    summary = _schema_props(spec, "CarePlanSummary")
    # CarePlanDetail is allOf(CarePlanSummary, {patient, view})
    expected = summary | {"patient", "view"}
    assert _model_aliases(m.CarePlanDetail) == expected
