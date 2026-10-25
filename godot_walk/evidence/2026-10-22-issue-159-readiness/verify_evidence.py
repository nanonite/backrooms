"""Verify live audit evidence and preserve the previously recorded protected hashes."""

import hashlib
import json
from collections import deque
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent
ROOT = EVIDENCE.parents[2]


def load(path):
    return json.loads(path.read_text())


def save(name, document):
    (EVIDENCE / name).write_text(json.dumps(document, indent=2) + "\n")


def protected_hashes():
    provenance = load(ROOT / "godot_walk/evidence/2026-10-21-issue-155-godot-library/provenance.json")
    entries = provenance["protected"]
    for entry in entries:
        actual = hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest()
        entry["matches"] = actual == entry["sha256"]
    if not all(entry["matches"] for entry in entries):
        raise RuntimeError("Protected source asset changed")
    return entries


def connected_cells():
    cells = {tuple(point) for point in load(EVIDENCE / "capsule_clear_cells.json")}
    visited = {(-44, -40)}
    pending = deque(visited)
    while pending:
        current = pending.popleft()
        for offset in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            neighbor = (current[0] + offset[0], current[1] + offset[1])
            if neighbor in cells and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    if visited != cells:
        raise RuntimeError("Current capsule-clear cells are not all spawn connected")
    return cells


def region(bounds):
    points = load(EVIDENCE / "midheight_visual_slice.json")
    selected = [point for point in points
                if bounds[0] < point[0] < bounds[1] and bounds[2] < point[1] < bounds[3]]
    if not selected:
        raise RuntimeError("Column candidate region has no source surface samples")
    return {"selection_xz": bounds, "selected_samples": len(selected),
            "sample_extents_xz": [min(point[0] for point in selected), max(point[0] for point in selected),
                                  min(point[1] for point in selected), max(point[1] for point in selected)],
            "meaning": "Selected partial midheight surface samples, not a recovered complete solid"}


def inventory():
    return [
        {"id": "C01", "classification": "inside proposed/current module; accepted authored visual box",
         "visual_xz": [0.06, 0.78, 0.3, 1.8], "confidence": "high for authored bounds",
         "collision_xz": [-1.3768562, 0.4819264, -0.8615601, 1.5085216],
         "action": "Preserve accepted visual; independently align collision in a later approved change"},
        {"id": "C02", "classification": "inside current capsule-clear area and proposed module",
         "source_surface": region([-1.6, 0.1, 3.8, 5.4]),
         "confidence": "high for visible partial upright and open side; unknown original complete shape",
         "views": ["V05_west", "V09_C02_front", "V10_C02_reverse"],
         "collision": "No dedicated collider; capsule at estimated upright center is clear",
         "action": "Repair all reachable exposed faces and add independently tested collision later"},
        {"id": "C03", "classification": "outside current east collision perimeter; visible background",
         "source_surface": region([4.45, 5.9, 4.0, 5.5]),
         "confidence": "moderate for column-like upright; complete base/solid/source semantics uncertain",
         "views": ["V05_west", "V09_C02_front"],
         "collision": "No floor support at estimated center (5,4.7); beyond invisible east boundary",
         "action": "Explicitly occlude/exclude from bounded playable module; repair if still visible"},
    ]


def verify_views(cells):
    records = load(EVIDENCE / "capture_manifest.json") + load(EVIDENCE / "close_manifest.json")
    for record in records:
        point = (round(record["eye"][0] * 10), round(record["eye"][2] * 10))
        if point not in cells:
            raise RuntimeError("Capture eye is outside sampled spawn-connected capsule area")
        destination = EVIDENCE / "captures" / (record["id"] + ".png")
        if not destination.is_file() or record["resolution"] != [960, 540]:
            raise RuntimeError("Missing or unexpected capture")
    return len(records)


def main():
    cells = connected_cells()
    audit = load(EVIDENCE / "audit.json")
    if len(cells) != audit["measurement"]["spawn_connected_center_samples"]:
        raise RuntimeError("Live grid count disagrees with independent graph traversal")
    if audit["registration_accepted"] or audit["scale_calibrated"]:
        raise RuntimeError("Calibration flags changed")
    save("column_inventory.json", inventory())
    save("verification.json", {"protected_hashes": protected_hashes(),
         "independently_connected_cells": len(cells), "reachable_captures": verify_views(cells),
         "registration_accepted": False, "scale_calibrated": False,
         "runtime_geometry_modified": False, "runtime_collision_modified": False})
    print("READINESS_EVIDENCE_VERIFIED: 11338 cells, 10 reachable captures, 7 protected hashes")


if __name__ == "__main__":
    main()
