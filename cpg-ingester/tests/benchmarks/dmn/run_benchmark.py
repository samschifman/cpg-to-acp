"""CLI entrypoint for the DMN generation-quality benchmark.

    ./run-benchmark.sh --suite creator|reviewer|all --corpus hypertension

(or run this file directly with the cpg-ingester venv python). One MLflow run per
invocation: params record the prompt version (git describe + a manual --prompt-rev
tag), metrics record per-suite scores. Results are also written as JSON to the
report directory for eyeballing. LLM configuration is read from the environment
exactly as the pipeline reads it (LITELLM_URL / LLM_MODEL / LITELLM_API_KEY).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import mlflow
import yaml

# Non-package benchmark: make sibling modules (creator_eval, reviewer_eval, ...)
# importable whether invoked via the wrapper, `python run_benchmark.py`, or pytest.
BENCH_DIR = Path(__file__).resolve().parent
if str(BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR))

logger = logging.getLogger(__name__)

# tests/benchmarks/dmn/run_benchmark.py -> parents[3]=cpg-ingester, parents[4]=repo root.
INGESTER_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[4]


def _git_describe() -> str:
    try:
        return subprocess.check_output(
            ["git", "describe", "--always", "--dirty"], cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _llm_config() -> dict:
    return {
        "litellm_url": os.environ.get("LITELLM_URL", "http://localhost:4000"),
        "llm_model": os.environ.get("LLM_MODEL", "default"),
        "llm_api_key": os.environ.get("LITELLM_API_KEY", "sk-change-me"),
    }


def _load_config() -> dict:
    return yaml.safe_load((BENCH_DIR / "config.yaml").read_text())


def _flatten_metrics(prefix: str, d: dict) -> dict:
    """Pull scalar metrics out of a nested report for MLflow logging."""
    out = {}
    for k, v in d.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[f"{prefix}.{k}"] = v
        elif isinstance(v, dict):
            out.update(_flatten_metrics(f"{prefix}.{k}", v))
    return out


@click.command()
@click.option("--suite", type=click.Choice(["creator", "reviewer", "all"]), default="all")
@click.option("--corpus", default="hypertension")
@click.option("--prompt-rev", default="baseline", help="Manual prompt-version tag.")
@click.option("--no-compile", is_flag=True, help="Skip decision-service compile checks.")
@click.option("--skip-real-corpora", is_flag=True, help="Skip the no-golden real corpora.")
def main(suite: str, corpus: str, prompt_rev: str, no_compile: bool, skip_real_corpora: bool):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    config = _load_config()
    # corpus_manifest is resolved relative to this benchmark folder (self-contained);
    # the manifest's source_cpg/golden paths are cpg-ingester-relative (INGESTER_ROOT),
    # while config's real_corpora paths are repo-relative (REPO_ROOT) — see below.
    manifest = yaml.safe_load((BENCH_DIR / config["corpus_manifest"]).read_text())
    corpus_entry = manifest["corpora"][corpus]
    markdown = (INGESTER_ROOT / corpus_entry["source_cpg"]).read_text()
    llm_config = _llm_config()
    holdout = set(config.get("reviewer_holdout_classes", []))

    report_dir = (INGESTER_ROOT / config["report_dir"]).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(config["mlflow_experiment"])

    report: dict = {"suite": suite, "corpus": corpus, "prompt_rev": prompt_rev,
                    "git": _git_describe()}

    with tempfile.TemporaryDirectory() as tmp:
        with mlflow.start_run(run_name=f"{suite}-{corpus}-{prompt_rev}"):
            mlflow.log_params({"suite": suite, "corpus": corpus,
                               "prompt_rev": prompt_rev, "git": report["git"],
                               "llm_model": llm_config["llm_model"]})

            if suite in ("creator", "all"):
                from creator_eval import run_creator_suite, score_generated_corpus
                logger.info("Running creator suite on %s ...", corpus)
                report["creator"] = run_creator_suite(
                    corpus_entry, markdown, llm_config, tmp, INGESTER_ROOT,
                    run_compile=not no_compile,
                )
                mlflow.log_metrics(_flatten_metrics("creator", report["creator"]))

                if not skip_real_corpora:
                    report["real_corpora"] = {}
                    for rel in config.get("real_corpora", []):
                        d = REPO_ROOT / rel
                        if not d.exists():
                            logger.warning("Real corpus missing: %s", rel)
                            continue
                        paths = sorted(d.glob("*.dmn"))
                        if paths:
                            report["real_corpora"][rel] = score_generated_corpus(
                                paths, run_compile=not no_compile)
                    mlflow.log_metrics(_flatten_metrics("real", report["real_corpora"]))

            if suite in ("reviewer", "all"):
                from reviewer_eval import run_reviewer_suite
                logger.info("Running reviewer suite on %s ...", corpus)
                report["reviewer"] = run_reviewer_suite(
                    corpus_entry, markdown, llm_config, tmp, holdout, INGESTER_ROOT)
                mlflow.log_metrics(_flatten_metrics("reviewer", report["reviewer"]))

            out_path = report_dir / f"eval-{suite}-{corpus}-{prompt_rev}.json"
            out_path.write_text(json.dumps(report, indent=2, default=str))
            mlflow.log_artifact(str(out_path))
            logger.info("Report written to %s", out_path)

    _print_summary(report)


def _print_summary(report: dict):
    click.echo("\n=== Eval summary ===")
    if "creator" in report:
        c = report["creator"]
        click.echo(f"Creator: first-attempt L0 {c.get('first_attempt_validity_rate')}, "
                   f"escalation {c.get('escalation_rate')}, "
                   f"mean F1 {c.get('mean_structural_f1')}, "
                   f"compile-pass {c.get('compile_pass_rate')}, "
                   f"L0-pass-but-compile-fail {c.get('l0_pass_but_compile_fail')}")
    if "reviewer" in report:
        r = report["reviewer"]
        click.echo(f"Reviewer: recall {r.get('overall_recall')}, "
                   f"precision {r.get('overall_precision')}, "
                   f"false-escalation {r.get('false_escalation_rate')}")


if __name__ == "__main__":
    main()
