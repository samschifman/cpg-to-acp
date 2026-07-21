"""Tests for the terminology lookup tool.

Tests marked with @pytest.mark.network require internet access to
public terminology servers. They are included by default but can
be skipped with: pytest -m "not network"
"""

import pytest

from acp_writer.tools.terminology_lookup import (
    ICD10_SYSTEM,
    LOINC_SYSTEM,
    RXNORM_SYSTEM,
    SNOMED_SYSTEM,
    LookupResult,
    TerminologyCache,
    _extract_coded_fields,
    find,
    verify,
    verify_bundle_codes,
)


class TestLookupResult:
    def test_found(self):
        r = LookupResult(found=True, system=SNOMED_SYSTEM, code="38341003", display="Hypertension")
        d = r.to_dict()
        assert d["found"] is True
        assert d["code"] == "38341003"

    def test_not_found(self):
        r = LookupResult(found=False, system=SNOMED_SYSTEM)
        d = r.to_dict()
        assert d["found"] is False
        assert "code" not in d

    def test_error(self):
        r = LookupResult(found=False, error="network_error")
        d = r.to_dict()
        assert d["error"] == "network_error"


class TestCache:
    def test_set_and_get(self):
        cache = TerminologyCache()
        result = LookupResult(found=True, code="123")
        cache.set("sys", "verify", "123", result)
        cached = cache.get("sys", "verify", "123")
        assert cached is not None
        assert cached.code == "123"

    def test_miss(self):
        cache = TerminologyCache()
        assert cache.get("sys", "verify", "999") is None


class TestExtractCodedFields:
    def test_simple_coding(self):
        resource = {
            "resourceType": "Condition",
            "code": {
                "coding": [
                    {"system": "http://snomed.info/sct", "code": "38341003", "display": "Hypertension"},
                ],
            },
        }
        fields = _extract_coded_fields(resource)
        assert len(fields) == 1
        assert fields[0][1]["code"] == "38341003"

    def test_nested_codings(self):
        resource = {
            "resourceType": "Observation",
            "code": {
                "coding": [{"system": "http://loinc.org", "code": "85354-9"}],
            },
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6"}]},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4"}]},
                },
            ],
        }
        fields = _extract_coded_fields(resource)
        codes = {f[1]["code"] for f in fields}
        assert codes == {"85354-9", "8480-6", "8462-4"}

    def test_empty_resource(self):
        assert _extract_coded_fields({}) == []


class TestUnsupportedSystem:
    def test_find_unsupported(self):
        r = find("http://unknown.system", "test")
        assert not r.found
        assert "Unsupported" in r.error

    def test_verify_unsupported(self):
        r = verify("http://unknown.system", "123")
        assert not r.found
        assert "Unsupported" in r.error


@pytest.mark.network
class TestSNOMED:
    def test_verify_hypertension(self):
        r = verify(SNOMED_SYSTEM, "38341003")
        assert r.found
        assert r.code == "38341003"
        assert r.display is not None

    def test_verify_essential_hypertension(self):
        r = verify(SNOMED_SYSTEM, "59621000")
        assert r.found

    def test_verify_invalid(self):
        r = verify(SNOMED_SYSTEM, "0000000")
        assert not r.found or r.error

    def test_find_hypertension(self):
        r = find(SNOMED_SYSTEM, "essential hypertension")
        assert r.found
        assert r.code is not None


@pytest.mark.network
class TestLOINC:
    def test_verify_systolic_bp(self):
        r = verify(LOINC_SYSTEM, "8480-6")
        assert r.found
        assert r.code == "8480-6"

    def test_find_systolic(self):
        r = find(LOINC_SYSTEM, "systolic blood pressure")
        assert r.found
        assert r.code is not None

    def test_verify_invalid(self):
        r = verify(LOINC_SYSTEM, "XXXXX-X")
        assert not r.found


@pytest.mark.network
class TestRxNorm:
    def test_find_lisinopril(self):
        r = find(RXNORM_SYSTEM, "lisinopril")
        assert r.found
        assert r.code is not None

    def test_verify_metformin(self):
        r = verify(RXNORM_SYSTEM, "860975")
        assert r.found
        assert r.display is not None

    def test_verify_invalid(self):
        r = verify(RXNORM_SYSTEM, "9999999999")
        assert not r.found


@pytest.mark.network
class TestICD10:
    def test_find_hypertension(self):
        r = find(ICD10_SYSTEM, "essential hypertension")
        assert r.found
        assert r.code is not None

    def test_verify_i10(self):
        r = verify(ICD10_SYSTEM, "I10")
        assert r.found
        assert r.code == "I10"

    def test_verify_invalid(self):
        r = verify(ICD10_SYSTEM, "ZZZ99")
        assert not r.found


@pytest.mark.network
class TestVerifyBundle:
    def test_valid_bundle(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c1",
                        "code": {
                            "coding": [
                                {"system": SNOMED_SYSTEM, "code": "38341003", "display": "Hypertension"},
                            ],
                        },
                    },
                },
            ],
        }
        issues = verify_bundle_codes(bundle)
        invalid = [i for i in issues if i["status"] == "invalid"]
        assert len(invalid) == 0

    def test_invalid_code_in_bundle(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "c1",
                        "code": {
                            "coding": [
                                {"system": LOINC_SYSTEM, "code": "INVALID-CODE"},
                            ],
                        },
                    },
                },
            ],
        }
        issues = verify_bundle_codes(bundle)
        assert len(issues) >= 1
        assert issues[0]["code"] == "INVALID-CODE"
