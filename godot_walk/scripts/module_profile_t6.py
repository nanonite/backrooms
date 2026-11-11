"""Build and check additive T6 descriptors for the 11 admitted modules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import template_validate as tv
from backfill_module_profiles import expected_profiles
from deterministic_json import (
    ROOT,
    canonical_bytes,
    repo_relative,
    sha256_file,
    write_deterministic,
)

PROFILE_VERSION = "module-profile-t6-0.1.0"
SCHEMA = Path("godot_walk/room_catalog/module_profile_t6.schema.json")
PROBE_RESULTS = Path("godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json")
REVIEW_STATUS = "agent_proposed_draft_pending_operator_review"
PROBE_CEILING_NOTE = "#216 headless probe; up-ray result is capped by the profile ceiling hint"

# These are taste drafts grounded in accepted poetics and source descriptions.
# They do not claim operator or vision-model review.
DRAFTS: dict[str, dict[str, Any]] = {
    "godot_early_pocket_pass_through_v1": {"role": "through", "semantic": ["carpeted", "repetitive"], "sightline": ["occluded"], "mood": [0.20, 0.10, 0.25, 0.75, 0.10], "tags": ["quiet", "familiar"]},
    "godot_early_pocket_single_west_v1": {"role": "terminal", "semantic": ["carpeted", "single_socket"], "sightline": ["occluded"], "mood": [0.25, 0.15, 0.20, 0.70, 0.10], "tags": ["quiet", "enclosed"]},
    "godot_early_pocket_three_way_v1": {"role": "branch", "semantic": ["carpeted", "multi_socket"], "sightline": ["occluded"], "mood": [0.30, 0.15, 0.30, 0.65, 0.10], "tags": ["quiet", "choice"]},
    "godot_later_bay_column_bounded_v1": {"role": "terminal", "semantic": ["columns", "bounded"], "sightline": ["occluded"], "mood": [0.35, 0.20, 0.35, 0.60, 0.20], "tags": ["ordered", "interrupted_view"]},
    "godot_source_textured_large_room_hall_end_v1": {"role": "terminal", "semantic": ["large_room", "hall_opening", "columns"], "sightline": ["threshold_glimpse"], "mood": [0.40, 0.25, 0.55, 0.45, 0.25], "tags": ["spacious", "anticipatory"]},
    "godot_source_textured_large_room_v1": {"role": "terminal", "semantic": ["large_room", "hall_opening", "columns"], "sightline": ["threshold_glimpse"], "mood": [0.40, 0.25, 0.55, 0.45, 0.25], "tags": ["spacious", "anticipatory"]},
    "video_b9161c467ed2d30a_bill_viola_single_room_v1": {"role": "terminal", "semantic": ["domestic", "lit_vignette", "standalone"], "sightline": ["focused_view"], "mood": [0.45, 0.60, 0.65, 0.35, 0.75], "tags": ["intimate", "uncanny"]},
    "video_ccf9722164a0bdc8_debris_window_rock_room_v1": {"role": "terminal", "semantic": ["debris", "window_strip", "standalone"], "sightline": ["threshold_glimpse"], "mood": [0.75, 0.65, 0.60, 0.15, 0.80], "tags": ["unstable", "exposed"]},
    "video_ccf9722164a0bdc8_debris_window_rock_north_socket_v1": {"role": "terminal", "semantic": ["debris", "window_strip"], "sightline": ["threshold_glimpse"], "mood": [0.75, 0.65, 0.60, 0.15, 0.80], "tags": ["unstable", "exposed"]},
    "godot_gopro_industrial_hall_frame1097_v1": {"role": "terminal", "semantic": ["industrial_hall", "columns", "clerestory"], "sightline": ["long_view"], "mood": [0.55, 0.40, 0.55, 0.35, 0.45], "tags": ["monumental", "distant_light"]},
    "godot_gopro_industrial_hall_south_socket_v1": {"role": "terminal", "semantic": ["industrial_hall", "columns", "clerestory"], "sightline": ["long_view"], "mood": [0.55, 0.40, 0.55, 0.35, 0.45], "tags": ["monumental", "distant_light"]},
}


def t6_path(base_path: Path) -> Path:
    if base_path.name == "module_profile_v1.json":
        return base_path.with_name("module_profile_t6_v1.json")
    module_id = base_path.stem.rsplit("-v", 1)[0]
    return base_path.with_name(f"{module_id}-t6-v1.json")


def build_records(root: Path = ROOT) -> list[tuple[Path, dict[str, Any]]]:
    """Derive T6 files from frozen v1 profiles, the #216 measurements and drafts."""
    raw_probe = json.loads((root / PROBE_RESULTS).read_text(encoding="utf-8"))
    measurements = raw_probe["modules"]
    output = []
    for item in expected_profiles(root):
        base = json.loads(item.path.read_text(encoding="utf-8"))
        draft = DRAFTS[item.module_id]
        source = base["poetics_ref"]["path"]
        poetics = base["shape"]
        probe = measurements[f"{item.module_id}@{item.version}"]
        authored = lambda key: {
            "value": poetics[key],
            "status": "authored",
            "basis_status": "authored",
            "source": f"{source}#/shape/{key}",
        }
        measured_height = probe["metrics"]["ceiling_height_m"]
        exits = []
        for exit_record in base["exits"]:
            copied = dict(exit_record)
            copied["provenance"] = f"{source}; accepted ports and library index socket data"
            exits.append(copied)
        record = {
            "schema_version": 1,
            "profile_version": PROFILE_VERSION,
            "module_id": item.module_id,
            "base_profile": {"path": repo_relative(item.path, root), "sha256": sha256_file(item.path)},
            "template_ref": {"version": "generation-template-0.1.0", "path": "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md", "sha256": sha256_file(root / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md")},
            "ceiling_volume": {
                "ceiling_min_m": authored("ceiling_min_m"),
                "ceiling_max_m": authored("ceiling_max_m"),
                "ceiling_height_m": {
                    "value": measured_height,
                    "status": "measured",
                    "basis_status": "measured",
                    "source": f"{PROBE_RESULTS.as_posix()}#/modules/{item.module_id}@{item.version}/metrics/ceiling_height_m; {PROBE_CEILING_NOTE}",
                },
                "ceiling_kind": {
                    "value": "beam_grid" if "beam" in " ".join(json.loads((root / source).read_text())["poetics"]["style_tags"]) or "grid_and_lamps" in json.loads((root / source).read_text())["poetics"]["style_tags"] else "unknown",
                    "status": "authored",
                    "basis_status": "authored",
                    "source": f"{source}#/poetics/style_tags; ceiling-kind interpretation is a draft",
                },
                "volume_nominal_m3": {
                    "value": base["shape"]["volume_nominal_m3"],
                    "status": "derived",
                    "basis_status": "authored",
                    "derivation": "footprint area x authored maximum ceiling; nominal envelope heuristic",
                    "source": f"{source}#/shape; derived from authored footprint area and authored maximum ceiling",
                },
                "volume_measured_m3": {
                    "value": None,
                    "status": "unmeasured",
                    "basis_status": "unmeasured",
                    "source": "No committed per-module volume measurement exists",
                },
            },
            "exits": exits,
            "roles": {"review_status": REVIEW_STATUS, "map_role": base["roles"]["map_role"], "form_role": base["roles"]["form_role"], "semantic_tags": draft["semantic"], "circulation_role": draft["role"], "sightline_tags": draft["sightline"]},
            "mood": {"review_status": REVIEW_STATUS, "tension": draft["mood"][0], "dread": draft["mood"][1], "curiosity": draft["mood"][2], "safety": draft["mood"][3], "anomaly": draft["mood"][4], "tags": draft["tags"], "evidence": [{"path": source, "sha256": sha256_file(root / source)}]},
        }
        output.append((t6_path(item.path), record))
    return output


def validate_record(record: dict[str, Any], root: Path = ROOT) -> list[str]:
    errors = tv.schema_errors(record, tv.load_schema(SCHEMA, root))
    if errors:
        return errors
    errors += tv._reference_errors(record["base_profile"], root, "base_profile")
    errors += tv._reference_errors(record["template_ref"], root, "template_ref")
    for index, evidence in enumerate(record["mood"]["evidence"]):
        errors += tv._reference_errors(evidence, root, f"mood.evidence[{index}]")
    if errors:
        return errors
    base_path = root / record["base_profile"]["path"]
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"base_profile: cannot read referenced profile: {error}"]
    if not isinstance(base, dict):
        return ["base_profile: referenced profile must be a JSON object"]
    if record["module_id"] != base["module_id"]:
        errors.append("module_id does not match base profile")
    if record["exits"] != _expected_exit_projection(base):
        errors.append("exits differ from the authored/recorded base profile sockets")
    for key, metric in record["ceiling_volume"].items():
        if not metric["source"].strip():
            errors.append(f"ceiling_volume.{key}: source is empty")
    return errors


def _expected_exit_projection(base: dict[str, Any]) -> list[dict[str, Any]]:
    source = base["poetics_ref"]["path"]
    return [{**exit_record, "provenance": f"{source}; accepted ports and library index socket data"} for exit_record in base["exits"]]


def check(root: Path = ROOT) -> list[str]:
    errors = []
    expected = build_records(root)
    expected_paths = {path for path, _ in expected}
    existing = set((root / "godot_walk/room_catalog/module_profiles").glob("*-t6-v1.json"))
    existing.update(root.glob("godot_walk/source_library/sources/*/rooms/*/module_profile_t6_v1.json"))
    for path in sorted(expected_paths - existing):
        errors.append(f"{repo_relative(path, root)}: missing T6 sidecar")
    for path in sorted(existing - expected_paths):
        errors.append(f"{repo_relative(path, root)}: unexpected T6 sidecar")
    for path, draft in expected:
        if not path.is_file():
            continue
        try:
            actual = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{repo_relative(path, root)}: cannot read: {error}")
            continue
        errors.extend(f"{repo_relative(path, root)}: {error}" for error in validate_record(actual, root))
        if actual.get("base_profile") != draft["base_profile"] or actual.get("module_id") != draft["module_id"]:
            errors.append(f"{repo_relative(path, root)}: frozen base profile identity changed")
    return errors


def build(root: Path = ROOT) -> list[dict[str, str]]:
    results = []
    for path, record in build_records(root):
        status = write_deterministic(path, canonical_bytes(record))
        results.append({"path": repo_relative(path, root), "status": status})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    args = parser.parse_args(argv)
    if args.command == "build":
        print(json.dumps(build(), indent=2))
        return 0
    errors = check()
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
