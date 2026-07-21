"""Tests for PlanningBrief Pydantic schema."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from acp_writer.planning_brief import (
    ActivityType,
    ActivityWorkflow,
    ConflictEntry,
    DMNAuditEntry,
    FHIRCode,
    PlanActivity,
    PlanGoal,
    PlanningBrief,
    ReviewStatus,
    TargetValue,
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
    def test_conflict(self):
        c = ConflictEntry(
            description="Conflicting BP targets from two guidelines",
            activity_indices=[0, 1],
            sources=["CPG-A", "CPG-B"],
        )
        assert len(c.sources) == 2
        assert c.resolution is None

    def test_with_resolution(self):
        c = ConflictEntry(
            description="Duplicate monitoring",
            activity_indices=[2, 3],
            sources=["rec-1", "rec-2"],
            resolution="Merged into single monitoring activity",
        )
        assert c.resolution is not None


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
