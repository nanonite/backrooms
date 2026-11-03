"""Write evidence/2026-11-03-issue-183/{report.json,REPORT.md} from the headless runtime reports."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, canonical_bytes, write_deterministic  # noqa: E402

EVIDENCE = ROOT / "godot_walk/evidence/2026-11-03-issue-183"
SPECS = ROOT / "godot_walk/room_catalog/shape_rooms"
SEEDS = (1, 2, 3)
LAUNCH = (
    "godot4 --path godot_walk --rendering-driver vulkan --resolution 1280x720 "
    "res://scenes/generative_map_walkthrough.tscn -- "
    "--map=res://room_catalog/generative_maps/gmap-1-gmap-0.1.0.json "
    "--rooms=res://room_catalog/shape_rooms/gmap-1-gmap-0.1.0/index.json"
)
TEST = (
    "godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- "
    "--map=res://room_catalog/generative_maps/<map_id>.json "
    "--rooms=res://room_catalog/shape_rooms/<map_id>/index.json"
)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def spec_counts(index_path: Path) -> dict[str, Any]:
    rooms = load(index_path)["rooms"]
    return {
        "rooms": len(rooms),
        "by_primitive": dict(sorted(Counter(r["primitive"] for r in rooms).items())),
        "by_primitive_class": dict(sorted(Counter(r["primitive_class"] for r in rooms).items())),
        "by_construction": dict(sorted(Counter(r["construction"] for r in rooms).items())),
    }


def runtime_summary(runtime: dict[str, Any]) -> dict[str, Any]:
    positive = runtime["positive"]
    edges, flood = positive["edges"], positive["flood"]
    return {
        "rooms_checked": runtime["rooms_checked"],
        "direct_edges": edges["direct_edges"],
        "direct_edges_checked": edges["direct_edges_checked"],
        "edges_passed_forward": edges["passed_forward"],
        "edges_passed_reverse": edges["passed_reverse"],
        "closed_edges": edges["closed_edges"],
        "closed_edges_blocked": edges["closed_blocked"],
        "flood_expected_cells": flood["expected_cells"],
        "flood_reached_cells": flood["reached_cells"],
        "flood_void_cells_reached": flood["void_cells_reached"],
        "flood_clear_samples": flood["clear_samples"],
        "flood_reached_samples": flood["reached_samples"],
        "negative_controls": {
            name: {"applicable": c["applicable"], "failed_as_expected": c["failed_as_expected"], "first_failure": c.get("first_failure", "")}
            for name, c in sorted(runtime["negative_controls"].items())
        },
        "scene": runtime["scene"],
        "failures": runtime["failures"],
    }


def collect() -> dict[str, Any]:
    maps: dict[str, Any] = {}
    for seed in SEEDS:
        map_id = f"gmap-{seed}-gmap-0.1.0"
        entry = {
            "all_walkable": {
                "shapes": spec_counts(SPECS / map_id / "index.json"),
                "runtime": runtime_summary(load(EVIDENCE / f"runtime_{map_id}.json")),
            }
        }
        if seed == 1:
            entry["pending"] = {
                "shapes": spec_counts(SPECS / map_id / "pending/index.json"),
                "runtime": runtime_summary(load(EVIDENCE / f"runtime_{map_id}_pending.json")),
            }
        maps[map_id] = entry
    return {
        "issue": 183,
        "walkthrough_launch_seed_1": LAUNCH,
        "headless_test": TEST,
        "requires_human_visual_verification": True,
        "registration_accepted": False,
        "scale_calibrated": False,
        "maps": maps,
    }


def table(report: dict[str, Any]) -> list[str]:
    lines = [
        "| map | mode | rooms | edges both ways | closed blocked | flood cells | void reached | controls failed as expected |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for map_id, modes in report["maps"].items():
        for mode, entry in modes.items():
            r = entry["runtime"]
            controls = ", ".join(n for n, c in r["negative_controls"].items() if c["applicable"] and c["failed_as_expected"]) or "none"
            lines.append(
                f"| {map_id} | {mode} | {r['rooms_checked']} | "
                f"{r['edges_passed_forward'] + r['edges_passed_reverse']}/{2 * r['direct_edges_checked']} | "
                f"{r['closed_edges_blocked']}/{r['closed_edges']} | {r['flood_reached_cells']}/{r['flood_expected_cells']} | "
                f"{r['flood_void_cells_reached']} | {controls} |"
            )
    return lines


def shape_lines(report: dict[str, Any]) -> list[str]:
    lines = []
    for map_id, modes in report["maps"].items():
        shapes = modes["all_walkable"]["shapes"]
        lines.append(
            f"- {map_id}: primitives {shapes['by_primitive']}; classes {shapes['by_primitive_class']}; "
            f"construction {shapes['by_construction']}"
        )
    return lines


def markdown(report: dict[str, Any]) -> str:
    parts = [
        "# Issue 183: shape stage 1 rooms and walkable assembly",
        "",
        "Generated rooms are the stereotyped ground: every feature is a symbol, each room is bounded by its map",
        "cell, and rooms never change the map. `registration_accepted=false`, `scale_calibrated=false`.",
        "",
        "## What was checked (headless, physics only, no rendering)",
        "",
        "- Python: primitive per port pattern, doorway wall margins, polygon inside envelope, connectivity,",
        "  determinism (byte-identical), schema, stage_max 0 gives boxes, all features symbols, negative controls.",
        "- Godot per room: floor ray support at 0.5 m samples inside the polygon and none outside; the player",
        "  capsule (r 0.3, h 1.2) blocked at wall samples away from doorways; clear through open doorways;",
        "  closed_visible doorways blocked.",
        "- Godot assembled map: every direct edge passable in both directions (capsule sweep from 1 m inside one",
        "  cell to 1 m inside the other with floor support throughout); every closed edge blocked; flood fill from",
        "  the spawn reaches every walkable cell and no void cell.",
        "- Negative controls: one doorway removed fails traversal; one floor rectangle removed fails support.",
        "",
        "## Results",
        "",
        *table(report),
        "",
        "## Shapes (all_walkable)",
        "",
        *shape_lines(report),
        "",
        "## Operator walkthrough (seed 1)",
        "",
        "```",
        report["walkthrough_launch_seed_1"],
        "```",
        "",
        "Press R to reset to the spawn in cell c00.",
        "",
        "## Headless test",
        "",
        "```",
        report["headless_test"],
        "```",
        "",
        "## Requires human visual verification",
        "",
        "Texture density and UV scale, olive trim, the recessed dark panel at closed doorways, lamp placement,",
        "the PSX look and overall room feel cannot be judged without rendering. No captures were taken.",
        "",
    ]
    return "\n".join(parts)


def main() -> int:
    report = collect()
    results = [
        write_deterministic(EVIDENCE / "report.json", canonical_bytes(report)),
        write_deterministic(EVIDENCE / "REPORT.md", markdown(report).encode("utf-8")),
    ]
    print(json.dumps({"report": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
