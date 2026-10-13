#!/usr/bin/env python3
"""Capture spatial #100 views and compare a separate bounded candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw
from render_metrics import build_report

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-13-bounded-psx"
HEADINGS = ["e", "ne", "n", "nw", "w", "sw", "s", "se"]


def inventory(source):
    paths = [source / "godot_walk/assets/corridor_splat",
             source / "data/scenes/backrooms_coverage_v1_gaussian_splatfacto"]
    paths.extend(source / "godot_walk/scenes" / name for name in
                 ["corridor.tscn", "corridor_splat.tscn", "corridor_psx.tscn"])
    files = sorted({file for path in paths for file in
                    (path.rglob("*") if path.is_dir() else [path])
                    if file.is_file()})
    result = {}
    for file in files:
        with file.open("rb") as handle:
            result[str(file.relative_to(source))] = hashlib.file_digest(handle, "sha256").hexdigest()
    return result


def capture(point, scene, group):
    destination = EVIDENCE / group / point["id"]
    destination.mkdir(parents=True, exist_ok=True)
    command = ["godot4", "--path", str(ROOT / "godot_walk"),
               "--rendering-driver", "vulkan", "--resolution", "1280x720",
               "--disable-vsync", "--script", "res://scripts/capture_walk_envelope.gd",
               "--", f"--scene=res://scenes/{scene}.tscn", "--settle=200",
               "--camera-position=" + ",".join(str(value) for value in point["eye"]),
               f"--out={destination}"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180,
                            env={**os.environ, "DISPLAY": ":1"})
    (destination / "capture.log").write_text(result.stdout + result.stderr)
    if result.returncode or "SCRIPT ERROR" in result.stderr:
        raise RuntimeError(f"Capture failed: {destination}")
    return destination


def contact_sheet(points, group):
    sheet = Image.new("RGB", (8 * 240, len(points) * 155), "#202020")
    draw = ImageDraw.Draw(sheet)
    for row, point in enumerate(points):
        for column, heading in enumerate(HEADINGS):
            path = EVIDENCE / group / point["id"] / "spawn_headings" / f"spawn_{heading}.png"
            with Image.open(path) as image:
                sheet.paste(image.resize((240, 135)), (column * 240, row * 155 + 20))
            draw.text((column * 240 + 3, row * 155 + 3), f'{point["id"]} {heading}', fill="white")
    sheet.save(EVIDENCE / f"{group}_contact.jpg", quality=92)


def boundary_captures(candidate_only):
    points = json.loads((EVIDENCE / "boundary_positions.json").read_text())
    for group, scene in [("boundary_baseline", "corridor_psx"),
                         ("boundary_candidate", "corridor_bounded_psx")]:
        if candidate_only and group == "boundary_baseline":
            continue
        for point in points:
            capture(point, scene, group)
            print(f'Captured {group}: {point["id"]}', flush=True)
        contact_sheet(points, group)
    reports = {point["id"]: build_report(EVIDENCE / "boundary_baseline" / point["id"],
              EVIDENCE / "boundary_candidate" / point["id"], None, 32, 20) for point in points}
    (EVIDENCE / "boundary_metrics.json").write_text(json.dumps(reports, indent=2) + "\n")


def capture_cases(mode):
    point_file = "search_positions.json" if mode == "search" else "route_positions.json"
    points = json.loads((EVIDENCE / point_file).read_text())
    points = [point for point in points if point.get("floor", True) and point.get("displacement", 0) < 0.1]
    if mode in ("search", "candidate"):
        scene = "corridor_psx" if mode == "search" else "corridor_bounded_psx"
        for point in points:
            capture(point, scene, mode)
            print(f'Captured {mode}: {point["id"]}', flush=True)
        contact_sheet(points, mode)
        return
    reports = {point["id"]: build_report(EVIDENCE / "search" / point["id"],
               EVIDENCE / "candidate" / point["id"], None, 32, 20) for point in points}
    (EVIDENCE / "matched_metrics.json").write_text(json.dumps(reports, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["inventory", "search", "candidate", "compare", "boundary"])
    parser.add_argument("--source", type=Path, default=Path("/mnt/sharedOs/backrooms-workspace"))
    parser.add_argument("--output", default="protected_before.json")
    parser.add_argument("--candidate-only", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if args.mode == "inventory":
        (EVIDENCE / args.output).write_text(json.dumps(inventory(args.source), indent=2) + "\n")
        return
    if args.mode == "boundary":
        boundary_captures(args.candidate_only)
        return
    capture_cases(args.mode)


if __name__ == "__main__":
    main()
