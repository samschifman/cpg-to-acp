"""CLI entry point for care plan generation.

Reads a FHIR Bundle from a file and generates a CarePlan.
"""

import json
import logging

import click

from acp_writer.careplan import build_careplan, extract_patient_data, invoke_decisions


@click.command()
@click.argument("bundle_file", type=click.Path(exists=True))
@click.option("--kogito-url", default="http://localhost:8081", help="Kogito decision service URL.")
@click.option("--output", "-o", type=click.Path(), default=None, help="Write CarePlan JSON to file.")
def main(bundle_file: str, kogito_url: str, output: str):
    """Generate a FHIR CarePlan from a patient data bundle."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    with open(bundle_file) as f:
        bundle = json.load(f)

    patient_data = extract_patient_data(bundle)
    decisions = invoke_decisions(kogito_url, patient_data)
    careplan_bundle = build_careplan(patient_data["patient_id"], decisions)

    careplan_json = json.dumps(careplan_bundle, indent=2)

    if output:
        with open(output, "w") as f:
            f.write(careplan_json)
        click.echo(f"CarePlan written to {output}")
    else:
        click.echo(careplan_json)


if __name__ == "__main__":
    main()
