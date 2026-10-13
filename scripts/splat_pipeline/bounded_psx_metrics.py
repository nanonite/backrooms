#!/usr/bin/env python3
"""Summarize the bounded experiment without interpreting enclosure as recovery."""
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw
from render_metrics import black_fraction, changed_stats, floater_stats, read_image

EVIDENCE = Path(__file__).resolve().parents[2] / "godot_walk/evidence/2026-10-13-bounded-psx"


def sweep_report():
    frames = json.loads((EVIDENCE / "sweep_candidate/frames.json").read_text())
    reports = []
    for frame in frames:
        before = read_image(EVIDENCE / "sweep_baseline" / frame["filename"])
        after = read_image(EVIDENCE / "sweep_candidate" / frame["filename"])
        reports.append({**frame, "black_before_pct": black_fraction(before) * 100,
                        "black_after_pct": black_fraction(after) * 100,
                        **changed_stats(before, after),
                        "before_floaters": floater_stats(before),
                        "after_floaters": floater_stats(after)})
    (EVIDENCE / "sweep_metrics.json").write_text(json.dumps(reports, indent=2) + "\n")
    return reports


def authored_report():
    frames = json.loads((EVIDENCE / "diagnostic/frames.json").read_text())
    headings = ["e", "ne", "n", "nw", "w", "sw", "s", "se"]
    reports = []
    for frame in frames:
        image = read_image(EVIDENCE / "diagnostic" / frame["filename"])
        mask = (image[:, :, 0] > 200) & (image[:, :, 1] < 40)
        reports.append({"point": frame["point"], "heading": headings[frame["yaw"]],
                        "authored_depth_reject_pct": round(float(mask.mean()) * 100, 3)})
    (EVIDENCE / "authored_coverage.json").write_text(json.dumps(reports, indent=2) + "\n")
    return reports


def summary(reports):
    return {"captures": len(reports), "mean_black_before_pct": float(np.mean([
            row["black_before_pct"] for row in reports])),
            "mean_black_after_pct": float(np.mean([row["black_after_pct"] for row in reports])),
            "max_black_after_pct": max(row["black_after_pct"] for row in reports),
            "max_after_floater_px": max(row["after_floaters"]["floater_px"] for row in reports)}


def sweep_contact(group, frames):
    sheet = Image.new("RGB", (3840, 12 * 110), "#202020")
    draw = ImageDraw.Draw(sheet)
    selected = EVIDENCE / "sweep_selected" / group
    selected.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        left, top = index % 24 * 160, index // 24 * 110
        path = EVIDENCE / group / frame["filename"]
        with Image.open(path) as image:
            sheet.paste(image.resize((160, 90)), (left, top + 20))
        draw.text((left + 2, top + 2), f'{frame["point"]} {frame["yaw"]}/{frame["pitch"]}', fill="white")
        if frame["yaw"] in (14, 179):
            shutil.copyfile(path, selected / path.name)
    sheet.save(EVIDENCE / f"{group}_contact.jpg", quality=92)


def main():
    reports = sweep_report()
    authored = authored_report()
    frames = json.loads((EVIDENCE / "sweep_candidate/frames.json").read_text())
    for group in ("sweep_baseline", "sweep_candidate"):
        sweep_contact(group, frames)
    result = {"sweep": summary(reports), "authored_depth_reject_mean_pct": float(np.mean([
              row["authored_depth_reject_pct"] for row in authored]))}
    (EVIDENCE / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
