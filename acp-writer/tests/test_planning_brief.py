"""Tests for PlanningBrief Pydantic schema."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from acp_writer.planning_brief import (
    ActivityType,
    ActivityWorkflow,
    ConflictCategory,
    ConflictEntry,
    ConflictSeverity,
    ConflictSource,
    ConflictStatus,
    DMNAuditEntry,
    FHIRCode,
    PlanActivity,
    PlanGoal,
    PlanningBrief,
    ReviewStatus,
    TargetValue,
    coerce_conflicts,
    conflict_id,
    render_conflicts_feedback,
)


def _sample_brief() -> PlanningBrief:
    return PlanningBrief(
        patient_reference="Patient/123",
        applicable_cpgs=["SYN-HTN-2026-001"],
        dmn_audit_trail=[
            DMNAuditEntry(
                model_id="treatment-recommendation",
                model_name="Treatment Recommendation",
                inputs={"Systolic BP": 145, "Has Diabetes": True, "Has Kidney Disease": False},
                outputs={
                    "Action": "Start medication",
                    "Medication": "Lisinopril",
                    "Dose": "10 mg daily",
                    "Follow Up Weeks": 4,
                },
                fhir_references=["Observation/bp-001", "Condition/diabetes-001"],
                timestamp=datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc),
            ),
        ],
        goals=[
            PlanGoal(
                description="Lower blood pressure to target range",
                target_measure_code=FHIRCode(
                    system="http://loinc.org",
                    code="8480-6",
                    display="Systolic blood pressure",
                ),
                target_value=TargetValue(high=140, unit="mmHg"),
                source_recommendation_id="rec-guid-123",
                source_cpg="SYN-HTN-2026-001",
            ),
        ],
        activities=[
            PlanActivity(
                type=ActivityType.MEDICATION,
                description="Start Lisinopril 10mg daily",
                code=FHIRCode(
                    system="http://www.nlm.nih.gov/research/umls/rxnorm",
                    code="29046",
                    display="Lisinopril",
                ),
                dose="10 mg",
                route="oral",
                frequency="daily",
                source_recommendation_id="rec-guid-456",
                source_cpg="SYN-HTN-2026-001",
                source_dmn_call=0,
                clinical_rationale="ACE inhibitor selected due to renal protective effects",
                workflow=ActivityWorkflow(
                    actor="prescribing_physician",
                    escalation="If BP not at target after 4 weeks, consider dose increase",
                    monitoring_trigger="BMP in 4 weeks to check renal function",
                ),
            ),
            PlanActivity(
                type=ActivityType.MONITORING,
                description="Basic Metabolic Panel",
                code=FHIRCode(
                    system="http://loinc.org",
                    code="51990-0",
                    display="Basic metabolic panel",
                ),
                frequency="4 weeks",
                source_recommendation_id="rec-guid-789",
                source_cpg="SYN-HTN-2026-001",
                source_dmn_call=0,
            ),
            PlanActivity(
                type=ActivityType.LIFESTYLE,
                description="DASH diet - reduce sodium intake to less than 2300mg/day",
                source_recommendation_id="rec-guid-abc",
                source_cpg="SYN-HTN-2026-001",
                clinical_rationale="Dietary modification is first-line for all hypertension stages",
            ),
        ],
        review_status=ReviewStatus.APPROVED,
    )


class TestFHIRCode:
    def test_with_display(self):
        code = FHIRCode(system="http://loinc.org", code="8480-6", display="Systolic BP")
        assert code.system == "http://loinc.org"
        assert code.display == "Systolic BP"

    def test_without_display(self):
        code = FHIRCode(system="http://loinc.org", code="8480-6")
        assert code.display is None

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            FHIRCode(system="http://loinc.org")


class TestTargetValue:
    def test_high_only(self):
        tv = TargetValue(high=140, unit="mmHg")
        assert tv.low is None

    def test_range(self):
        tv = TargetValue(low=90, high=140, unit="mmHg")
        assert tv.low == 90
        assert tv.high == 140

    def test_missing_unit(self):
        with pytest.raises(ValidationError):
            TargetValue(high=140)


class TestDMNAuditEntry:
    def test_roundtrip(self):
        entry = DMNAuditEntry(
            model_id="treatment-recommendation",
            model_name="Treatment Recommendation",
            inputs={"Systolic BP": 145},
            outputs={"Action": "Start medication"},
            timestamp=datetime(2026, 7, 21, 10, 0, 0, tzinfo=timezone.utc),
        )
        data = entry.model_dump(mode="json")
        restored = DMNAuditEntry.model_validate(data)
        assert restored.model_id == entry.model_id
        assert restored.inputs == entry.inputs

    def test_fhir_references_default_empty(self):
        entry = DMNAuditEntry(
            model_id="test",
            model_name="Test",
            inputs={},
            outputs={},
            timestamp=datetime.now(timezone.utc),
        )
        assert entry.fhir_references == []


class TestActivityWorkflow:
    def test_all_fields(self):
        wf = ActivityWorkflow(
            actor="prescribing_physician",
            sequence_after="Initial assessment",
            escalation="Refer to specialist if uncontrolled after 3 months",
            monitoring_trigger="BMP in 4 weeks",
        )
        assert wf.actor == "prescribing_physician"
        assert wf.sequence_after == "Initial assessment"

    def test_all_optional(self):
        wf = ActivityWorkflow()
        assert wf.actor is None
        assert wf.sequence_after is None


class TestPlanActivity:
    def test_medication_activity(self):
        act = PlanActivity(
            type=ActivityType.MEDICATION,
            description="Start Lisinopril",
            code=FHIRCode(system="http://www.nlm.nih.gov/research/umls/rxnorm", code="29046"),
            dose="10 mg",
            route="oral",
            frequency="daily",
            source_cpg="SYN-HTN-2026-001",
        )
        assert act.type == ActivityType.MEDICATION
        assert act.dose == "10 mg"

    def test_lifestyle_activity_minimal(self):
        act = PlanActivity(
            type=ActivityType.LIFESTYLE,
            description="Reduce sodium intake",
            source_cpg="SYN-HTN-2026-001",
        )
        assert act.code is None
        assert act.dose is None

    def test_missing_required(self):
        with pytest.raises(ValidationError):
            PlanActivity(type=ActivityType.MEDICATION, description="test")

    def test_activity_type_enum(self):
        for t in ["medication", "monitoring", "lifestyle", "referral", "educational", "process"]:
            act = PlanActivity(type=t, description="test", source_cpg="test")
            assert act.type == ActivityType(t)


class TestConflictEntry:
    def test_new_model(self):
        c = ConflictEntry(
            id="conf-abc123",
            category=ConflictCategory.DIVERGENT_TARGET,
            severity=ConflictSeverity.WARNING,
            description="Conflicting BP targets from two guidelines",
            goal_indices=[0, 1],
            sources=[
                ConflictSource(cpg_id="SYN-HTN-2026-001", recommendation_id="rec-1"),
                ConflictSource(cpg_id="SYN-DM2-2026-001", recommendation_id="rec-2"),
            ],
        )
        assert c.status == ConflictStatus.DETECTED
        assert c.detected_by == "llm"
        assert len(c.sources) == 2
        assert c.resolution is None

    def test_defaults(self):
        c = ConflictEntry(id="conf-1", description="x")
        assert c.category == ConflictCategory.OTHER
        assert c.severity == ConflictSeverity.WARNING
        assert c.goal_indices == []
        assert c.activity_indices == []
        assert c.sources == []

    def test_json_roundtrip(self):
        c = ConflictEntry(
            id="conf-1",
            category=ConflictCategory.CONTRADICTION,
            description="titrate up vs. reduce lisinopril",
            activity_indices=[0, 3],
            sources=[ConflictSource(cpg_id="A", recommendation_id="r1", excerpt="q")],
            confidence="high",
        )
        restored = ConflictEntry.model_validate(c.model_dump(mode="json"))
        assert restored == c


class TestConflictId:
    def test_deterministic(self):
        sources = [ConflictSource(cpg_id="A", recommendation_id="r1")]
        a = conflict_id(ConflictCategory.OVERLAP, sources)
        b = conflict_id(ConflictCategory.OVERLAP, sources)
        assert a == b
        assert a.startswith("conf-")

    def test_order_insensitive(self):
        s1 = [ConflictSource(cpg_id="A", recommendation_id="r1"),
              ConflictSource(cpg_id="B", recommendation_id="r2")]
        s2 = list(reversed(s1))
        assert conflict_id(ConflictCategory.OVERLAP, s1) == conflict_id(ConflictCategory.OVERLAP, s2)

    def test_category_and_content_key_change_id(self):
        sources = [ConflictSource(cpg_id="A", recommendation_id="r1")]
        base = conflict_id(ConflictCategory.OVERLAP, sources)
        assert conflict_id(ConflictCategory.CONTRADICTION, sources) != base
        assert conflict_id(ConflictCategory.OVERLAP, sources, content_key="bp") != base

    def test_falls_back_to_cpg_ids(self):
        # No recommendation ids → cpg ids drive the hash (still stable).
        s = [ConflictSource(cpg_id="A"), ConflictSource(cpg_id="B")]
        assert conflict_id(ConflictCategory.OVERLAP, s) == conflict_id(
            ConflictCategory.OVERLAP, list(reversed(s))
        )


class TestCoerceConflicts:
    def test_empty(self):
        assert coerce_conflicts(None) == []
        assert coerce_conflicts([]) == []

    def test_bare_string(self):
        [c] = coerce_conflicts(["Two guidelines disagree on BP target"])
        assert c["description"] == "Two guidelines disagree on BP target"
        assert c["detected_by"] == "composer"
        assert c["id"].startswith("conf-")
        ConflictEntry.model_validate(c)  # must validate

    def test_legacy_sources_list_of_str(self):
        [c] = coerce_conflicts([
            {"description": "dup monitoring", "activity_indices": [2, 3], "sources": ["CPG-A", "CPG-B"]}
        ])
        assert c["sources"] == [{"cpg_id": "CPG-A"}, {"cpg_id": "CPG-B"}]
        ConflictEntry.model_validate(c)

    def test_legacy_recommendation_ids_key(self):
        [c] = coerce_conflicts([{"description": "x", "recommendation_ids": ["r1"]}])
        assert c["sources"] == [{"cpg_id": "r1"}]
        assert "recommendation_ids" not in c
        ConflictEntry.model_validate(c)

    def test_preserves_existing_id_and_detected_by(self):
        [c] = coerce_conflicts([
            {"id": "conf-keep", "description": "x", "detected_by": "llm", "sources": []}
        ])
        assert c["id"] == "conf-keep"
        assert c["detected_by"] == "llm"

    # --- F7: coerce_conflicts must be total (never raise on loose input) ---

    def test_camelcase_source_keys(self):
        [c] = coerce_conflicts([
            {"description": "x", "sources": [
                {"cpgId": "CPG-A", "recommendationId": "r1", "excerpt": "quote"}
            ]}
        ])
        assert c["sources"] == [
            {"cpg_id": "CPG-A", "recommendation_id": "r1", "excerpt": "quote"}
        ]
        ConflictEntry.model_validate(c)

    def test_source_missing_cpg_id_is_dropped_not_fatal(self):
        # A source with no recoverable cpg_id must be dropped without sinking
        # the whole conflict (previously raised inside ConflictSource(**s)).
        [c] = coerce_conflicts([
            {"description": "x", "sources": [{"recommendation_id": "r1"}, {"cpg_id": "CPG-A"}]}
        ])
        assert c["sources"] == [{"cpg_id": "CPG-A"}]
        ConflictEntry.model_validate(c)

    def test_non_string_source_fields_coerced(self):
        [c] = coerce_conflicts([{"description": "x", "sources": [{"cpg_id": 123}]}])
        assert c["sources"] == [{"cpg_id": "123"}]
        ConflictEntry.model_validate(c)

    def test_severity_synonyms_coerced(self):
        [c] = coerce_conflicts([{"description": "x", "severity": "high", "sources": []}])
        assert c["severity"] == "critical"
        [c2] = coerce_conflicts([{"description": "x", "severity": "low", "sources": []}])
        assert c2["severity"] == "info"
        ConflictEntry.model_validate(c)
        ConflictEntry.model_validate(c2)

    def test_unknown_category_and_status_defaulted(self):
        [c] = coerce_conflicts([
            {"description": "x", "category": "banana", "status": "whatever", "sources": []}
        ])
        assert c["category"] == "other"
        assert c["status"] == "detected"
        ConflictEntry.model_validate(c)

    def test_conflict_entry_instances_accepted(self):
        entry = ConflictEntry(id="conf-1", description="x", detected_by="llm")
        [c] = coerce_conflicts([entry])
        assert c["id"] == "conf-1"
        assert c["detected_by"] == "llm"
        ConflictEntry.model_validate(c)

    def test_non_string_description_coerced(self):
        [c] = coerce_conflicts([{"description": 42, "sources": []}])
        assert c["description"] == "42"
        ConflictEntry.model_validate(c)


class TestRenderConflictsFeedback:
    """F16a: prior conflicts render into a compact composer-feedback block."""

    def _conflict(self) -> dict:
        return {
            "id": "conf-abc12345",
            "category": "divergent_target",
            "severity": "warning",
            "description": "Two guidelines set different BP targets",
            "rationale": "HTN <140/90 vs DM2 <130/80",
            "suggested_resolution": "Prefer the diabetes guideline's <130/80 target",
            "sources": [
                {"cpg_id": "SYN-HTN-2026-001", "recommendation_id": "htn-rec-002"},
                {"cpg_id": "SYN-DM2-2026-001"},
            ],
        }

    def test_empty_is_blank(self):
        assert render_conflicts_feedback(None) == ""
        assert render_conflicts_feedback([]) == ""

    def test_renders_all_fields_compactly(self):
        block = render_conflicts_feedback([self._conflict()])
        assert "## Previously identified conflicts" in block
        assert "[conf-abc12345]" in block
        assert "divergent_target" in block
        assert "warning" in block
        assert "Two guidelines set different BP targets" in block
        assert "Rationale: HTN <140/90 vs DM2 <130/80" in block
        assert "Suggested: Prefer the diabetes guideline's <130/80 target" in block
        assert "SYN-HTN-2026-001/htn-rec-002" in block
        assert "SYN-DM2-2026-001" in block
        # Compact — no raw JSON dump of the conflict object.
        assert "{" not in block

    def test_coerces_loose_shapes(self):
        # Bare-string / legacy conflicts must not raise (coerced first).
        block = render_conflicts_feedback(["two guidelines disagree on BP"])
        assert "two guidelines disagree on BP" in block


class TestPlanningBriefCoercesConflicts:
    """F4: a single malformed conflict must never sink the whole brief."""

    def _base(self, conflicts):
        return {
            "patient_reference": "Patient/1",
            "applicable_cpgs": ["CPG-A"],
            "goals": [{"description": "g", "source_cpg": "CPG-A"}],
            "activities": [
                {"type": "lifestyle", "description": "a", "source_cpg": "CPG-A"}
            ],
            "conflicts": conflicts,
        }

    def test_loose_conflict_does_not_drop_goals_and_activities(self):
        # Before the before-validator, this brief raised on validate — and every
        # caller that swallowed the error dropped the goals/activities too.
        brief = PlanningBrief.model_validate(self._base([
            {"description": "loose", "severity": "high", "sources": ["CPG-A"]}
        ]))
        assert len(brief.goals) == 1
        assert len(brief.activities) == 1
        assert len(brief.conflicts) == 1
        assert brief.conflicts[0].severity == ConflictSeverity.CRITICAL

    def test_bare_string_conflict_validates(self):
        brief = PlanningBrief.model_validate(self._base(["two guidelines disagree"]))
        assert brief.conflicts[0].description == "two guidelines disagree"
        assert len(brief.goals) == 1

    def test_source_without_cpg_id_does_not_raise(self):
        brief = PlanningBrief.model_validate(self._base([
            {"description": "x", "sources": [{"recommendation_id": "r1"}]}
        ]))
        assert brief.conflicts[0].sources == []
        assert len(brief.activities) == 1

    def test_clean_brief_is_idempotent(self):
        clean = self._base([
            {"id": "conf-x", "description": "x", "detected_by": "llm",
             "category": "overlap", "severity": "info", "sources": [{"cpg_id": "CPG-A"}]}
        ])
        once = PlanningBrief.model_validate(clean)
        twice = PlanningBrief.model_validate(once.model_dump(mode="json"))
        assert once == twice


class TestPlanningBrief:
    def test_roundtrip(self):
        brief = _sample_brief()
        data = brief.model_dump(mode="json")
        restored = PlanningBrief.model_validate(data)
        assert restored.patient_reference == "Patient/123"
        assert len(restored.goals) == 1
        assert len(restored.activities) == 3
        assert len(restored.dmn_audit_trail) == 1
        assert restored.review_status == ReviewStatus.APPROVED

    def test_json_roundtrip(self):
        brief = _sample_brief()
        json_str = brief.model_dump_json()
        restored = PlanningBrief.model_validate_json(json_str)
        assert restored == brief

    def test_missing_goals(self):
        with pytest.raises(ValidationError):
            PlanningBrief(
                patient_reference="Patient/123",
                applicable_cpgs=["SYN-HTN-2026-001"],
                activities=[],
            )

    def test_missing_activities(self):
        with pytest.raises(ValidationError):
            PlanningBrief(
                patient_reference="Patient/123",
                applicable_cpgs=["SYN-HTN-2026-001"],
                goals=[],
            )

    def test_empty_goals_allowed(self):
        brief = PlanningBrief(
            patient_reference="Patient/123",
            applicable_cpgs=["SYN-HTN-2026-001"],
            goals=[],
            activities=[],
        )
        assert brief.goals == []

    def test_defaults(self):
        brief = PlanningBrief(
            patient_reference="Patient/123",
            applicable_cpgs=[],
            goals=[],
            activities=[],
        )
        assert brief.dmn_audit_trail == []
        assert brief.conflicts == []
        assert brief.review_status == ReviewStatus.PENDING
        assert brief.review_feedback is None

    def test_review_status_values(self):
        for status in ["pending", "approved", "revised", "flagged"]:
            brief = PlanningBrief(
                patient_reference="Patient/123",
                applicable_cpgs=[],
                goals=[],
                activities=[],
                review_status=status,
            )
            assert brief.review_status == ReviewStatus(status)

    def test_workflow_context_serializes(self):
        brief = _sample_brief()
        data = brief.model_dump(mode="json")
        med_activity = data["activities"][0]
        assert med_activity["workflow"]["actor"] == "prescribing_physician"
        assert med_activity["workflow"]["escalation"] is not None
        assert med_activity["clinical_rationale"] is not None

    def test_provenance_chain(self):
        brief = _sample_brief()
        for activity in brief.activities:
            assert activity.source_cpg is not None
            assert activity.source_recommendation_id is not None

        assert brief.dmn_audit_trail[0].fhir_references == [
            "Observation/bp-001",
            "Condition/diabetes-001",
        ]
