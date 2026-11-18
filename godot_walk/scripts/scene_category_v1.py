"""Versioned intake scene category: validation and safe routing (CPU-only).

New sources carry a separate ``scene_category_v1`` record. Sources with no such
record are legacy: they are read unchanged and route to the enclosed workflow.
An ``open_world`` category only routes to the outdoor path when an operator has
reviewed it and the record carries provenance; otherwise it is held, never
silently admitted. This module writes no ledger events, receipts or hashes and
does not modify any source manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "godot_walk/room_catalog/scene_category_v1.schema.json"

CONTRACT_ID = "godot_intake_scene_category"
CONTRACT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

ENCLOSED = "enclosed"
OPEN_WORLD = "open_world"
UNKNOWN = "unknown"
CATEGORIES = (ENCLOSED, OPEN_WORLD, UNKNOWN)

PENDING = "pending"
OPERATOR_REVIEWED = "operator_reviewed"
REJECTED = "rejected"
REVIEW_STATES = (PENDING, OPERATOR_REVIEWED, REJECTED)

ROUTE_ENCLOSED = "enclosed"
ROUTE_OPEN_WORLD = "open_world"
ROUTE_OPEN_WORLD_HOLD = "open_world_hold"

LEGACY_ROUTE = {
    "category": ENCLOSED,
    "category_source": "legacy_default",
    "review_state": "not_applicable",
    "route": ROUTE_ENCLOSED,
    "can_enter_open_world": False,
}


class SceneCategoryError(ValueError):
    """A scene-category record or routing request is invalid."""


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(record: Any) -> list[str]:
    """Return all validation errors for a category record (empty when valid)."""
    if not isinstance(record, dict):
        return ["Scene-category record must be a JSON object"]
    errors: list[str] = []
    validator = jsonschema.Draft202012Validator(load_schema())
    errors.extend(
        f"schema: {list(error.absolute_path)}: {error.message}"
        for error in sorted(
            validator.iter_errors(record), key=lambda item: list(item.absolute_path)
        )
    )
    errors.extend(_semantic_errors(record))
    return errors


def _semantic_errors(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    category = record.get("category")
    if category not in CATEGORIES:
        errors.append(
            f"Unknown scene category {category!r}; expected one of {list(CATEGORIES)}"
        )
    review = record.get("review")
    if not isinstance(review, dict):
        return errors
    state = review.get("state")
    if state not in REVIEW_STATES:
        errors.append(
            f"Unknown review state {state!r}; expected one of {list(REVIEW_STATES)}"
        )
    if category == OPEN_WORLD and state == OPERATOR_REVIEWED:
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or provenance.get("basis") == "unknown":
            errors.append(
                "An operator-reviewed open_world category requires provenance with a non-unknown basis"
            )
    return errors


def route_source(
    manifest: dict[str, Any], category_record: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Route a source manifest to enclosed or the held/released open path.

    A manifest without a ``scene_category`` field is legacy and is never
    rewritten. A manifest that claims a category without a versioned record is
    rejected so no source silently enters the outdoor path.
    """
    if not isinstance(manifest, dict):
        raise SceneCategoryError("Source manifest must be a JSON object")
    if category_record is None:
        if "scene_category" in manifest:
            raise SceneCategoryError(
                "A categorised manifest requires a versioned scene_category_v1 record"
            )
        result = dict(LEGACY_ROUTE)
        result["source_id"] = manifest.get("source_id")
        return result

    errors = validate(category_record)
    if errors:
        raise SceneCategoryError("; ".join(errors))

    manifest_source = manifest.get("source_id")
    record_source = category_record.get("source_id")
    if manifest_source is not None and manifest_source != record_source:
        raise SceneCategoryError(
            "Scene-category source_id does not match the source manifest"
        )

    category = category_record["category"]
    state = category_record["review"]["state"]
    route = ROUTE_ENCLOSED
    can_enter = False
    if category == OPEN_WORLD and state == OPERATOR_REVIEWED:
        route = ROUTE_OPEN_WORLD
        can_enter = True
    elif category == OPEN_WORLD:
        route = ROUTE_OPEN_WORLD_HOLD

    return {
        "category": category,
        "category_source": "versioned_v1_record",
        "review_state": state,
        "route": route,
        "can_enter_open_world": can_enter,
        "source_id": record_source,
        "synthetic_fixture": category_record.get("synthetic_fixture", False),
    }


def validate_file(path: Path) -> dict[str, Any]:
    """Load and validate a category record file, returning the routing result."""
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SceneCategoryError(
            f"Cannot read category record {path}: {error}"
        ) from error
    errors = validate(record)
    if errors:
        raise SceneCategoryError(f"{path}: " + "; ".join(errors))
    return route_source({}, record)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("validate", help="Validate a category record file")
    check.add_argument("path", type=Path)
    route = subparsers.add_parser(
        "route", help="Route a manifest with an optional category record"
    )
    route.add_argument("manifest", type=Path)
    route.add_argument("--category", type=Path, default=None)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate":
            result = validate_file(arguments.path)
            print(json.dumps(result, sort_keys=True))
            return 0
        manifest = json.loads(arguments.manifest.read_text(encoding="utf-8"))
        record = None
        if arguments.category is not None:
            record = json.loads(arguments.category.read_text(encoding="utf-8"))
        result = route_source(manifest, record)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        SceneCategoryError,
    ) as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
