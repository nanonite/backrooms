"""Backfill module_profile_v1 sidecars for the admitted library modules (#215).

The profile is a derived projection of an operator-accepted module_poetics record.
This script never edits a poetics record, a module scene, the catalog or a
catalog snapshot. Kit modules get a flat sidecar in ``room_catalog/module_profiles``;
source-room modules get ``module_profile_v1.json`` beside their ``module_poetics_v2.json``.

Only mechanical fields are derived here. Semantic fields (roles, mood, lighting,
scale, absorption) are written as explicit unreviewed placeholders and are the
operator's to accept or edit later; see docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md
sections 4.2, 4.5 and 6.5.

Usage:
    python3 godot_walk/scripts/backfill_module_profiles.py build
    python3 godot_walk/scripts/backfill_module_profiles.py check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import template_validate as tv
from deterministic_json import (
    ROOT,
    canonical_bytes,
    plan_write,
    repo_relative,
    sha256_bytes,
    write_new,
)
from gmap_library import accepted_path
from library_index import load_json, load_verified_index
from module_profile import SURFACES, build_profile

INDEX = Path("godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json")
PROFILE_DIR = Path("godot_walk/room_catalog/module_profiles")
SOURCE_ROOM_PREFIX = "godot_walk/source_library/sources/"
SOURCE_PROFILE_NAME = "module_profile_v1.json"
ADMITTED_MODULE_COUNT = 11
SHAPE_MECHANICAL_FIELDS = (
    "footprint_xz",
    "bbox_xz",
    "area_m2",
    "vertex_count",
    "aspect",
    "convexity",
    "rectilinear",
    "primitive",
    "shape_stage",
    "symmetry",
)
EXIT_MECHANICAL_FIELDS = (
    "socket_id",
    "kind",
    "compatibility_type",
    "width_m",
    "elevation_m",
    "tested_pair_ids",
    "provenance",
)


class BackfillError(ValueError):
    """An admitted module cannot be projected into a profile."""


@dataclass(frozen=True)
class ExpectedProfile:
    """One admitted module and the record derived from its frozen inputs."""

    module_id: str
    version: int
    path: Path
    record: dict[str, Any]


def profile_path(entry: dict[str, Any], root: Path = ROOT) -> Path:
    """Where a module profile lives; mirrors the two locations in section 4.2."""
    room_dir = entry.get("room_dir")
    if room_dir and room_dir.startswith(SOURCE_ROOM_PREFIX):
        return root / room_dir / SOURCE_PROFILE_NAME
    return root / PROFILE_DIR / f"{entry['module_id']}-v{entry['version']}.json"


def _accepted_poetics(
    entry: dict[str, Any], root: Path
) -> tuple[dict[str, Any], str]:
    source = accepted_path(entry, root)
    if not source.is_file():
        raise BackfillError(
            f"{entry['module_id']} has no operator-accepted poetics record"
        )
    record = load_json(source)
    if record.get("metadata_status") != "operator_accepted":
        raise BackfillError(f"{entry['module_id']} poetics is not operator-accepted")
    if (
        record.get("module_id") != entry["module_id"]
        or record.get("version") != entry["version"]
    ):
        raise BackfillError(f"{entry['module_id']} poetics identity does not match the index")
    return record, repo_relative(source, root)


def expected_profiles(root: Path = ROOT) -> list[ExpectedProfile]:
    """Derive every admitted module profile from the frozen index and poetics."""
    index = load_verified_index(root / INDEX, root)
    entries = index["modules"]
    if len(entries) != ADMITTED_MODULE_COUNT:
        raise BackfillError(
            f"expected {ADMITTED_MODULE_COUNT} admitted modules, found {len(entries)}"
        )
    expected = []
    for entry in entries:
        poetics, poetics_path = _accepted_poetics(entry, root)
        record = build_profile(poetics, poetics_path, entry, index["snapshot_sha256"], root)
        expected.append(
            ExpectedProfile(
                entry["module_id"],
                entry["version"],
                profile_path(entry, root),
                record,
            )
        )
    return expected


def build(root: Path = ROOT) -> list[dict[str, str]]:
    """Write missing profiles; refuse to overwrite different content."""
    results = []
    for expected in expected_profiles(root):
        data = canonical_bytes(expected.record)
        status = plan_write(expected.path, data)
        if status == "create":
            write_new(expected.path, data)
        results.append(
            {
                "module_id": expected.module_id,
                "path": repo_relative(expected.path, root),
                "sha256": sha256_bytes(data),
                "status": status,
            }
        )
    return results


def mechanical_projection(record: dict[str, Any]) -> dict[str, Any]:
    """The fields #215 owns; later template issues may edit the rest."""
    return {
        "module_id": record["module_id"],
        "version": record["version"],
        "source_id": record["source_id"],
        "origin": record["origin"],
        "poetics_ref": record["poetics_ref"],
        "catalog_snapshot_sha256": record["catalog_snapshot_sha256"],
        "template_ref": record["template_ref"],
        "shape": {
            field: record["shape"].get(field) for field in SHAPE_MECHANICAL_FIELDS
        },
        "exits": [
            {field: exit_record.get(field) for field in EXIT_MECHANICAL_FIELDS}
            for exit_record in record["exits"]
        ],
        "surface_acoustics": {
            surface: record["surfaces"][surface]["acoustic"] for surface in SURFACES
        },
        "acoustics_tag": record["acoustics"]["tag"],
        "eligibility": record["eligibility"],
        "translation_chain": record["translation_chain"],
    }


def _projection_errors(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    if actual == expected:
        return []
    errors = []
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            errors.append(
                f"{key}: derived value changed "
                f"(expected {expected_value!r}, found {actual.get(key)!r})"
            )
    return errors


def check(root: Path = ROOT) -> list[str]:
    """Validate the committed profiles against the frozen inputs and the schema."""
    errors: list[str] = []
    try:
        expected = expected_profiles(root)
    except (BackfillError, OSError, ValueError, KeyError) as error:
        return [f"cannot derive expected profiles: {error}"]
    expected_paths = {item.path for item in expected}
    committed_paths = set(tv.module_profile_paths(root))
    for missing in sorted(expected_paths - committed_paths):
        errors.append(f"{repo_relative(missing, root)}: missing")
    for extra in sorted(committed_paths - expected_paths):
        errors.append(f"{repo_relative(extra, root)}: unexpected module profile")
    for item in expected:
        label = repo_relative(item.path, root)
        if not item.path.is_file():
            continue
        try:
            actual = json.loads(item.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{label}: cannot read module profile: {error}")
            continue
        problems = tv.module_profile_errors(actual, root)
        errors.extend(f"{label}: {problem}" for problem in problems)
        if problems:
            continue
        projected = mechanical_projection(actual)
        errors.extend(
            f"{label}: {problem}"
            for problem in _projection_errors(projected, mechanical_projection(item.record))
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    arguments = parser.parse_args(argv)
    if arguments.command == "build":
        print(json.dumps(build(), indent=2, sort_keys=True))
        return 0
    problems = check()
    print(json.dumps({"valid": not problems, "errors": problems}, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
