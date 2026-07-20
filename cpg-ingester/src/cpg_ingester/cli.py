"""CLI entrypoint for the cpg-ingester pipeline."""

import logging
import uuid
from pathlib import Path

import click
import mlflow

from cpg_ingester.pipeline import build_pipeline

try:
    mlflow.langchain.autolog()
except Exception:
    pass


@click.command()
@click.argument("input_pdf", type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--acp-writer-url", default="http://localhost:8082")
@click.option("--litellm-url", envvar="LITELLM_URL", default="http://localhost:4000")
@click.option("--model", envvar="LLM_MODEL", default="default")
@click.option("--api-key", envvar="LITELLM_API_KEY", default="sk-change-me")
def main(
    input_pdf: Path,
    output_dir: Path | None,
    acp_writer_url: str,
    litellm_url: str,
    model: str,
    api_key: str,
):
    """Run the cpg-ingester pipeline on a CPG PDF."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    run_id = str(uuid.uuid4())[:8]
    if output_dir is None:
        output_dir = Path("output") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    graph = build_pipeline()
    compiled = graph.compile()

    initial_state = {
        "run_id": run_id,
        "output_dir": str(output_dir),
        "pdf_path": str(input_pdf),
    }

    click.echo(f"Starting cpg-ingester pipeline (run: {run_id})")
    click.echo(f"  PDF: {input_pdf}")
    click.echo(f"  Output: {output_dir}")

    result = compiled.invoke(initial_state)

    click.echo(f"\nPipeline complete (run: {run_id})")


if __name__ == "__main__":
    main()
