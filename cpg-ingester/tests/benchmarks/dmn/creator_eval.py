"""Creator evaluation: drive the real DMN loop with instrumentation.

Rather than re-implement the subgraph, this reuses the actual nodes
(``dmn_creator``, ``dmn_syntax_validator``, ``dmn_semantic_reviewer``) and the
actual router functions from ``generation.py`` so the measured behavior matches
production exactly — it just records what happens at each step (first-attempt
validity, attempts-to-valid, escalation reason, final DMN) that the compiled
subgraph does not surface.

Each accepted/escalated model is then scored against its golden (structural F1,
threshold exactness) and compile-checked against the decision-service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from cpg_ingester.generation import (
    _extract_section_text,
    _route_after_dmn_semantic,
    _route_after_dmn_syntax,
)
from cpg_ingester.nodes.dmn_creator import dmn_creator
from cpg_ingester.nodes.dmn_semantic_reviewer import dmn_semantic_reviewer
from cpg_ingester.nodes.dmn_syntax_validator import dmn_syntax_validator
from cpg_ingester.validators.dmn_syntax import validate_dmn_xml

from compile_check import compile_check
from dmn_diff import diff_models

logger = logging.getLogger(__name__)

_MAX_LOOP_ITERATIONS = 12  # safety cap; the real routers stop well before this


@dataclass
class CreatorResult:
    decision: str
    first_attempt_l0_pass: bool = False
    creator_calls: int = 0
    attempts_to_valid: int | None = None
    final_l0_valid: bool = False
    escalated: bool = False
    escalation_reason: str = ""
    section_text_present: bool = False
    final_dmn: str = ""
    golden_diff: dict = field(default_factory=dict)
    compile_status: str = "SKIPPED"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d.pop("final_dmn", None)  # keep the report readable; DMN saved separately
        return d


def _drive_loop(item: dict, source_text: str, llm_config: dict, output_dir: str) -> CreatorResult:
    """Run creator→validate→(retry|review)→(retry|accept|escalate), instrumented."""
    res = CreatorResult(decision=item.get("name", "unknown"),
                        section_text_present=bool(source_text))
    state: dict = {
        "item": item,
        "source_pages": source_text or item.get("source_pages", ""),
        "output_dir": output_dir,
        "syntax_retry_count": 0,
        "semantic_retry_count": 0,
        **llm_config,
    }

    for _ in range(_MAX_LOOP_ITERATIONS):
        state.update(dmn_creator(state))
        res.creator_calls += 1
        state.update(dmn_syntax_validator(state))

        if res.creator_calls == 1:
            res.first_attempt_l0_pass = not state.get("syntax_errors")

        route = _route_after_dmn_syntax(state)
        if route == "dmn_creator":
            continue  # syntax retry
        if route == "dmn_escalate":
            res.escalated = True
            res.escalation_reason = "syntax-budget-exhausted"
            break

        # Syntax clean at this point.
        if res.attempts_to_valid is None:
            res.attempts_to_valid = res.creator_calls

        state.update(dmn_semantic_reviewer(state))
        route = _route_after_dmn_semantic(state)
        if route == "dmn_accept":
            break
        if route == "dmn_escalate":
            res.escalated = True
            res.escalation_reason = state.get("escalation_reason") or "semantic-budget-exhausted"
            break
        # else route == dmn_creator -> semantic retry, loop again

    res.final_dmn = state.get("dmn_xml", "")
    res.final_l0_valid = res.final_dmn and not validate_dmn_xml(res.final_dmn)
    return res


def run_creator_suite(corpus: dict, markdown: str, llm_config: dict, output_dir: str,
                      repo_root, run_compile: bool = True) -> dict:
    """Generate DMN for each decision, score vs golden, compile-check."""
    results: list[CreatorResult] = []
    for dec in corpus.get("decisions", []):
        heading = dec.get("source_section", {}).get("heading", "")
        source_text = _extract_section_text(markdown, [{"heading": heading}], heading)
        item = {
            "name": dec["name"],
            "type": "decision",
            "category": dec.get("category", "treatment"),
            "hit_policy": dec.get("hit_policy", "FIRST"),
            "inputs": dec.get("inputs", []),
            "outputs": [o["name"] for o in dec.get("outputs", [])],
            "section": heading,
        }
        res = _drive_loop(item, source_text, llm_config, output_dir)

        golden_xml = (repo_root / dec["golden"]).read_text()
        if res.final_dmn:
            try:
                res.golden_diff = diff_models(golden_xml, res.final_dmn)
            except Exception as e:  # malformed final DMN
                res.golden_diff = {"error": str(e)}
            if run_compile:
                rep_inputs = (dec.get("representative_inputs") or [{}])[0].get("inputs", {})
                res.compile_status = compile_check(res.final_dmn, rep_inputs).status
        results.append(res)

    return _aggregate(results)


def _aggregate(results: list[CreatorResult]) -> dict:
    n = len(results)
    if not n:
        return {"decisions": 0}
    first_pass = sum(int(r.first_attempt_l0_pass) for r in results)
    escalated = sum(int(r.escalated) for r in results)
    section_hits = sum(int(r.section_text_present) for r in results)
    valid_attempts = [r.attempts_to_valid for r in results if r.attempts_to_valid]
    compiled = sum(1 for r in results if r.compile_status == "COMPILE_OK")
    compile_fail = sum(1 for r in results if r.compile_status == "COMPILE_FAIL")
    compile_measured = sum(1 for r in results if r.compile_status in ("COMPILE_OK", "COMPILE_FAIL"))
    l0_pass_compile_fail = sum(1 for r in results
                               if r.final_l0_valid and r.compile_status == "COMPILE_FAIL")
    f1s = [r.golden_diff.get("structural_f1") for r in results
           if isinstance(r.golden_diff, dict) and "structural_f1" in r.golden_diff]

    return {
        "decisions": n,
        "first_attempt_validity_rate": round(first_pass / n, 4),
        "mean_attempts_to_valid": round(sum(valid_attempts) / len(valid_attempts), 3) if valid_attempts else None,
        "escalation_rate": round(escalated / n, 4),
        "section_extraction_hit_rate": round(section_hits / n, 4),
        "compile_pass_rate": round(compiled / compile_measured, 4) if compile_measured else None,
        "compile_measured": compile_measured,
        "compile_fail": compile_fail,
        "l0_pass_but_compile_fail": l0_pass_compile_fail,
        "mean_structural_f1": round(sum(f1s) / len(f1s), 4) if f1s else None,
        "per_decision": [r.to_dict() for r in results],
    }


def score_generated_corpus(dmn_paths: list, run_compile: bool = True) -> dict:
    """L0 + compile validity for a directory of generated DMN (no goldens)."""
    rows = []
    for path in dmn_paths:
        xml = path.read_text()
        l0_errors = validate_dmn_xml(xml)
        compile_status = compile_check(xml).status if run_compile else "SKIPPED"
        rows.append({
            "file": path.name,
            "l0_valid": not l0_errors,
            "l0_error_count": len(l0_errors),
            "compile_status": compile_status,
        })
    n = len(rows) or 1
    l0_valid = sum(int(r["l0_valid"]) for r in rows)
    compiled = sum(1 for r in rows if r["compile_status"] == "COMPILE_OK")
    measured = sum(1 for r in rows if r["compile_status"] in ("COMPILE_OK", "COMPILE_FAIL"))
    l0_pass_compile_fail = sum(1 for r in rows
                               if r["l0_valid"] and r["compile_status"] == "COMPILE_FAIL")
    return {
        "files": len(rows),
        "l0_validity_rate": round(l0_valid / n, 4),
        "compile_pass_rate": round(compiled / measured, 4) if measured else None,
        "l0_pass_but_compile_fail": l0_pass_compile_fail,
        "per_file": rows,
    }
