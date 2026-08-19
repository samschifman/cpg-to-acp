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


def test_enum_values_match_contract():
    spec = _spec()

    def _spec_enum(name):
        return set(spec["components"]["schemas"][name]["enum"])

    assert {e.value for e in m.RunStatus} == _spec_enum("RunStatus")
    assert {e.value for e in m.StepStatus} == _spec_enum("StepStatus")
    assert {e.value for e in m.ReviewGate} == _spec_enum("ReviewGate")
    assert {e.value for e in m.ReviewDecision} == _spec_enum("ReviewDecision")
    assert {e.value for e in m.StepKey} == _spec_enum("StepKey")
    # Severity is defined inline on PlanConflict.severity in the contract
    assert {e.value for e in m.Severity} == set(
        spec["components"]["schemas"]["PlanConflict"]["properties"]["severity"]["enum"]
    )


def test_careplan_detail_is_summary_plus_patient_and_view():
    spec = _spec()
    summary = _schema_props(spec, "CarePlanSummary")
    # CarePlanDetail is allOf(CarePlanSummary, {patient, view})
    expected = summary | {"patient", "view"}
    assert _model_aliases(m.CarePlanDetail) == expected


def _walk_routes(routes):
    # FastAPI >=0.141 wraps included routers in a lazy _IncludedRouter instead of
    # flattening them onto app.routes; descend into it to see the real routes.
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _walk_routes(inner.routes)
        else:
            yield route


def test_app_routes_match_contract_paths():
    from acp_writer.services.bff import create_app
    spec = _spec()
    contract_paths = set(spec["paths"].keys())  # e.g. "/runs", "/runs/{runId}"
    app = create_app()
    app_paths = set()
    for route in _walk_routes(app.routes):
        path = getattr(route, "path", "")
        if path.startswith("/api/v1"):
            # normalize {run_id} -> {runId}, strip prefix to match contract keys
            rel = path[len("/api/v1"):]
            rel = rel.replace("{run_id}", "{runId}").replace("{careplan_id}", "{careplanId}")
            app_paths.add(rel)
    assert app_paths == contract_paths, {
        "missing_in_app": sorted(contract_paths - app_paths),
        "extra_in_app": sorted(app_paths - contract_paths),
    }
