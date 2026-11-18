"""Build the issue-273 baseline/variant provenance record from real artifacts.

All hashes, view records and receipt summaries are read from the working tree;
nothing is authored by hand. The record is new and refuses to overwrite.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
ROOT = EVIDENCE_DIR.parents[2]
SOURCE = "godot_walk/source_library/sources/video-22909eb734e4d8e2/rooms"
BASELINE = f"{SOURCE}/slot-canyon-courtyard-v1"
VARIANT = f"{SOURCE}/slot-canyon-courtyard-v2"
BASELINE_CAPTURES = (
    "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues/captures/baseline_v1"
)
BASELINE_RECEIPT = (
    "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues/resource/"
    "capture_baseline_v1_resource.json"
)


def sha256_file(relative: str) -> str:
    digest = hashlib.sha256()
    with (ROOT / relative).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def receipt_summary(relative: str) -> dict:
    receipt = load_json(relative)
    return {
        "path": relative,
        "sha256": sha256_file(relative),
        "return_code": receipt["return_code"],
        "timed_out": receipt["timed_out"],
        "error": receipt["error"],
        "finished_at_utc": receipt["finished_at_utc"],
    }


def main() -> int:
    target = EVIDENCE_DIR / "provenance" / "baseline_vs_variant_v1.json"
    if target.exists():
        raise SystemExit(f"Refusing to overwrite provenance record: {target}")
    baseline_harness_manifest = f"{BASELINE_CAPTURES}/capture_manifest.json"
    baseline_manifest = load_json(baseline_harness_manifest)
    variant_manifest = load_json(f"{VARIANT}/captures/capture_manifest.json")
    baseline_receipt = receipt_summary(BASELINE_RECEIPT)
    variant_receipt = receipt_summary(f"{VARIANT}/capture_resource_run.json")
    record = {
        "schema_version": 1,
        "record_id": "issue-273-baseline-vs-variant-v1",
        "operator_review": "pending",
        "registration_accepted": False,
        "scale_calibrated": False,
        "source_video": (
            "godot_walk/source_library/sources/video-22909eb734e4d8e2/source_manifest-v3.json"
        ),
        "seed_frame": "frame_1363",
        "panorama_attempt": "attempt-001 (accepted previously, not rerun)",
        "baseline": {
            "room_id": "slot-canyon-courtyard-v1",
            "status": "operator-accepted standalone candidate; unchanged by this slice",
            "scene": f"{BASELINE}/room.tscn",
            "scene_sha256": sha256_file(f"{BASELINE}/room.tscn"),
            "script_sha256": sha256_file(f"{BASELINE}/room.gd"),
            "candidate_sha256": sha256_file(f"{BASELINE}/adaptation_candidate.json"),
            "capture_manifest": f"{BASELINE}/captures/capture_manifest.json",
            "capture_manifest_sha256": sha256_file(
                f"{BASELINE}/captures/capture_manifest.json"
            ),
            "captures_in_new_harness": f"{BASELINE_CAPTURES}",
            "new_harness_manifest_sha256": sha256_file(baseline_harness_manifest),
            "guard_receipt": baseline_receipt,
        },
        "variant": {
            "room_id": "slot-canyon-courtyard-v2",
            "status": "experimental visual-only depth variant; candidate_pending_review",
            "scene": f"{VARIANT}/room.tscn",
            "scene_sha256": sha256_file(f"{VARIANT}/room.tscn"),
            "script_sha256": sha256_file(f"{VARIANT}/room.gd"),
            "capture_manifest": f"{VARIANT}/captures/capture_manifest.json",
            "capture_manifest_sha256": sha256_file(
                f"{VARIANT}/captures/capture_manifest.json"
            ),
            "guard_receipt": variant_receipt,
        },
        "matched_capture": {
            "harness": (
                "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues/fixture/"
                "paired_capture.gd"
            ),
            "harness_sha256": sha256_file(
                "godot_walk/evidence/2026-11-17-issue-273-canyon-depth-cues/fixture/"
                "paired_capture.gd"
            ),
            "same_harness_for_both_scenes": True,
            "camera_baseline": baseline_manifest["camera"],
            "camera_variant": variant_manifest["camera"],
            "views_baseline": baseline_manifest["views"],
            "views_variant": variant_manifest["views"],
            "walk_path_baseline": baseline_manifest["walk_path"],
            "walk_path_variant": variant_manifest["walk_path"],
            "walk_path_is_deterministic_teleport_sequence": True,
        },
        "negative_control": {
            "kind": "boundary_check_reversal",
            "description": (
                "The v2 headless test disables the NorthWall collider and asserts the "
                "boundary ray misses, then disables all six walls and asserts the ray "
                "misses again, restoring colliders between checks. This demonstrates "
                "the boundary check can detect an escape or a missing boundary."
            ),
        },
        "no_new_collidable_obstacles": True,
        "invented_details": (
            "All relief fins, overhead ledges and boulder caps are authored visual-only "
            "boxes. Their count, positions, sizes, tilts and materials are invented, not "
            "measured or inferred from the source. They have no collider and may visually "
            "overlap collidable walls and boulders."
        ),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
