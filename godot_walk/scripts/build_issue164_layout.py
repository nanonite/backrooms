"""Build the immutable three-room #164 layout and its catalog snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from issue149_layout_core import ROOT, canonical_json, load_catalog_snapshot
from issue164_layout import build_layout
from jsonschema import Draft202012Validator

EVIDENCE = ROOT / "godot_walk/evidence/2026-10-24-issue-164"
LAYOUT_PATH = EVIDENCE / "layout_three_room.json"
SNAPSHOT_PATH = EVIDENCE / "catalog_snapshot.json"
LAYOUT_RESOURCE = "res://evidence/2026-10-24-issue-164/catalog_snapshot.json"
LAYOUT_SCHEMA = ROOT / "godot_walk/design_rounds/issue164_layout.schema.json"
PHYSICS_REPORTS = (
    EVIDENCE / "mechanics/standalone_column/physics_candidate.json",
    EVIDENCE / "mechanics/standalone_pocket/physics_candidate.json",
    EVIDENCE / "mechanics/standalone_large_baseline/physics_candidate.json",
    EVIDENCE / "mechanics/assembled/physics_candidate.json",
)
CONTROL_REPORT = EVIDENCE / "mechanics/physics_controls.json"


def build_bundle() -> tuple[dict, bytes, bytes]:
    snapshot, catalog_hash, snapshot_bytes = load_catalog_snapshot()
    layout = build_layout(snapshot, catalog_hash, LAYOUT_RESOURCE)
    schema = json.loads(LAYOUT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(layout)
    return layout, snapshot_bytes, canonical_json(layout)


def write_bundle(
    layout: dict,
    snapshot_bytes: bytes,
    layout_bytes: bytes,
    refresh_provisional: bool = False,
) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    _write_or_check(SNAPSHOT_PATH, snapshot_bytes, refresh_provisional)
    _write_or_check(LAYOUT_PATH, layout_bytes, refresh_provisional)
    sidecar = f"{_sha256_bytes(layout_bytes)}  {LAYOUT_PATH.name}\n".encode()
    _write_or_check(
        LAYOUT_PATH.with_suffix(".json.sha256"), sidecar, refresh_provisional
    )


def _write_or_check(path: Path, expected: bytes, refresh_provisional: bool) -> None:
    if path.exists():
        if path.read_bytes() != expected:
            if refresh_provisional and _is_unreviewed_candidate():
                path.write_bytes(expected)
                return
            raise FileExistsError(
                f"Refusing to replace immutable #164 evidence: {path}"
            )
        return
    path.write_bytes(expected)


def _is_unreviewed_candidate() -> bool:
    if not LAYOUT_PATH.is_file() or (EVIDENCE / "operator_review.json").exists():
        return False
    try:
        current = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        current.get("layout_id") == "issue164_three_room_chain_seed_164"
        and current.get("operator_status") == "review_pending"
    )


def _sha256_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _validate_mechanical_evidence() -> None:
    for path in PHYSICS_REPORTS:
        report = json.loads(path.read_text(encoding="utf-8"))
        route = report.get("out_and_back", {})
        segments = report.get("route_segments", [])
        if report.get("failures") or route.get("floor_fraction") != 1.0:
            raise ValueError(f"Physics verification did not pass: {path}")
        if route.get("safety_contacts") != 0 or not segments or not all(
            segment.get("reached") for segment in segments
        ):
            raise ValueError(f"Route or boundary verification did not pass: {path}")
    controls = json.loads(CONTROL_REPORT.read_text(encoding="utf-8"))
    expected = {
        "blocked_connector": ("unblocked_crossing_clear", "blocked_crossing_collides"),
        "missing_floor": ("floor_blocks_fall_before_removal", "fall_path_clear_after_removal"),
        "open_boundary": ("closed_boundary_blocks_escape", "removed_boundary_allows_escape"),
        "source_room_column_obstacle": ("collision_node_present", "approach_collides"),
    }
    if controls.get("failures"):
        raise ValueError("Physics control report contains failures")
    for control_id, checks in expected.items():
        measured = controls.get("controls", {}).get(control_id, {})
        if any(measured.get(check) is not True for check in checks):
            raise ValueError(f"Physics control did not pass: {control_id}")


def _mark_mechanically_validated(layout: dict) -> bytes:
    layout["mechanical_status"] = "mechanically_validated"
    for connection in layout["connections"]:
        connection["mechanical_status"] = "mechanically_validated_review_pending"
    layout.pop("layout_sha256", None)
    layout["layout_sha256"] = _sha256_bytes(canonical_json(layout))
    return canonical_json(layout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--refresh-provisional",
        action="store_true",
        help="Replace only the unreviewed #164 candidate bundle before operator review.",
    )
    parser.add_argument(
        "--mark-mechanically-validated",
        action="store_true",
        help="Record completed standalone, assembled, and negative-control evidence.",
    )
    args = parser.parse_args()
    layout, snapshot_bytes, layout_bytes = build_bundle()
    if args.mark_mechanically_validated:
        _validate_mechanical_evidence()
        layout_bytes = _mark_mechanically_validated(layout)
        schema = json.loads(LAYOUT_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(layout)
    if not args.validate_only:
        if args.refresh_provisional and not _is_unreviewed_candidate():
            raise SystemExit("Refusing refresh: no unreviewed #164 candidate exists")
        write_bundle(layout, snapshot_bytes, layout_bytes, args.refresh_provisional)
    print(
        f"ISSUE164_LAYOUT_VALID seed={layout['seed']} rooms={len(layout['placements'])} "
        f"connections={len(layout['connections'])} mechanical={layout['mechanical_status']} "
        f"catalog={layout['catalog_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
