"""WS6 read-back: conflicts survive the round-trip into the BFF view-model.

Two paths reconstruct a ``PlanConflict`` for the UI:
  1. from the FHIR bundle's conflict Provenances (persisted care plans) —
     ``bff._extract_view_from_bundle``;
  2. from the planning brief's ``ConflictEntry`` (live run detail) —
     ``artifact_resolver.plan_conflict_from_entry``.
Both must yield the same camelCase contract shape.
"""

from acp_writer.planning_brief import (
    ActivityType,
    ConflictCategory,
    ConflictEntry,
    ConflictSeverity,
    ConflictSource,
    ConflictStatus,
    FHIRCode,
    PlanActivity,
    PlanGoal,
    PlanningBrief,
    TargetValue,
)
from acp_writer.services.artifact_resolver import plan_conflict_from_entry
from acp_writer.services.bff import _extract_view_from_bundle
from acp_writer.validators.fhir_bundle_builder import build_fhir_bundle


def _brief_with_conflict() -> PlanningBrief:
    return PlanningBrief(
        patient_reference="Patient/p1",
        applicable_cpgs=["SYN-HTN-2026-001", "SYN-DM2-2026-001"],
        goals=[
            PlanGoal(
                description="Lower BP <140/90",
                target_measure_code=FHIRCode(system="http://loinc.org", code="8480-6", display="Systolic BP"),
                target_value=TargetValue(high=140, unit="mmHg"),
                source_cpg="SYN-HTN-2026-001",
            ),
            PlanGoal(
                description="Lower BP <130/80",
                target_measure_code=FHIRCode(system="http://loinc.org", code="8480-6", display="Systolic BP"),
                target_value=TargetValue(high=130, unit="mmHg"),
                source_cpg="SYN-DM2-2026-001",
            ),
        ],
        activities=[
            PlanActivity(
                type=ActivityType.MEDICATION,
                description="Lisinopril",
                dose="10 mg",
                source_recommendation_id="rec-123",
                source_cpg="SYN-HTN-2026-001",
            ),
        ],
        conflicts=[
            ConflictEntry(
                id="conf-abc12345",
                category=ConflictCategory.DIVERGENT_TARGET,
                severity=ConflictSeverity.WARNING,
                status=ConflictStatus.DETECTED,
                description="Two guidelines set different BP targets",
                rationale="HTN targets <140/90; DM2 targets <130/80",
                confidence="high",
                goal_indices=[0, 1],
                activity_indices=[0],
                sources=[
                    ConflictSource(cpg_id="SYN-HTN-2026-001", recommendation_id="rec-123", excerpt="<140/90"),
                    ConflictSource(cpg_id="SYN-DM2-2026-001", recommendation_id="dm2-rec-002", excerpt="<130/80"),
                ],
            )
        ],
    )


class TestBundleReadBack:
    def test_conflict_reconstructed_from_provenance(self):
        bundle = build_fhir_bundle(_brief_with_conflict())
        _goals, _acts, conflicts = _extract_view_from_bundle(bundle)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c["id"] == "conf-abc12345"
        assert c["severity"] == "warning"
        assert c["category"] == "divergent_target"
        assert c["status"] == "detected"
        assert c["confidence"] == "high"
        assert "different BP targets" in c["description"]

    def test_sources_reconstructed(self):
        bundle = build_fhir_bundle(_brief_with_conflict())
        _g, _a, conflicts = _extract_view_from_bundle(bundle)
        srcs = {s["cpgId"]: s for s in conflicts[0]["sources"]}
        assert set(srcs) == {"SYN-HTN-2026-001", "SYN-DM2-2026-001"}
        assert srcs["SYN-HTN-2026-001"]["recommendationId"] == "rec-123"
        assert srcs["SYN-HTN-2026-001"]["excerpt"] == "<140/90"

    def test_no_conflicts_yields_empty(self):
        brief = _brief_with_conflict()
        brief.conflicts = []
        bundle = build_fhir_bundle(brief)
        _g, _a, conflicts = _extract_view_from_bundle(bundle)
        assert conflicts == []


class TestEntryMapping:
    def test_maps_snake_to_camel(self):
        entry = _brief_with_conflict().conflicts[0].model_dump(mode="json")
        pc = plan_conflict_from_entry(entry)
        assert pc["id"] == "conf-abc12345"
        assert pc["severity"] == "warning"
        assert pc["category"] == "divergent_target"
        assert pc["status"] == "detected"
        assert pc["confidence"] == "high"
        assert pc["sources"][0]["cpgId"] == "SYN-HTN-2026-001"
        assert pc["sources"][0]["recommendationId"] == "rec-123"
        assert pc["sources"][0]["excerpt"] == "<140/90"

    def test_minimal_entry(self):
        pc = plan_conflict_from_entry({"id": "c1", "description": "d"})
        assert pc == {"id": "c1", "description": "d"}

    def test_source_without_rec_or_excerpt(self):
        entry = {"id": "c1", "description": "d", "sources": [{"cpg_id": "X"}]}
        pc = plan_conflict_from_entry(entry)
        assert pc["sources"] == [{"cpgId": "X"}]
