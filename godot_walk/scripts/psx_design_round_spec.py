"""Load a PSX design round from its checked-in JSON specification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DESIGN_ROUNDS = ROOT / "godot_walk" / "design_rounds"
SCHEMA_PATH = DESIGN_ROUNDS / "round.schema.json"


def load_spec(path: Path) -> dict[str, Any]:
    """Read, schema-check, and semantically validate a design round."""
    try:
        import jsonschema
    except ImportError as error:
        raise RuntimeError("Install jsonschema to validate design round specs") from error

    schema = json.loads(SCHEMA_PATH.read_text())
    spec = json.loads(path.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(spec),
                    key=lambda item: list(item.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise ValueError(f"invalid design round spec {path}: {details}")
    _validate_round_relations(spec, path)
    return spec


def _validate_round_relations(spec: dict[str, Any], path: Path) -> None:
    if spec["round_id"] != f"round-{spec['round_number']}":
        raise ValueError(f"round_id and round_number disagree in {path}")
    if spec["baseline"] not in spec["variants"]:
        raise ValueError(f"baseline must be included in variants in {path}")
    if ("video" in spec) != ("source_frame" in spec):
        raise ValueError(f"video and source_frame must be supplied together in {path}")
