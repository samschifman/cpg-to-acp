"""File output helpers for writing pipeline artifacts to disk."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_artifact(output_dir: str, filename: str, data: dict | list | str) -> Path:
    """Write an artifact to the run's output directory.

    Args:
        output_dir: Path to the run's output directory.
        filename: Filename within the output directory (e.g., "manifest.json").
        data: Data to write. Dicts/lists are JSON-serialized; strings are written directly.

    Returns:
        Path to the written file.
    """
    out_path = Path(output_dir) / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, str):
        out_path.write_text(data)
    else:
        out_path.write_text(json.dumps(data, indent=2, default=str))

    logger.info("Wrote artifact: %s", out_path)
    return out_path
