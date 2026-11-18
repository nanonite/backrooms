"""Compute a mechanical light-response record from the guarded paired captures.

This script never judges appearance and never approves anything. It compares
decoded pixels of matched light-off / light-on captures (and matched baseline /
lit captures) using identical camera transforms, records whether pixels changed,
and writes the observation under captures/ so bulky outputs stay local. Hashes
and guard receipts are produced by the existing tooling, not written here.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
CAPTURE_DIR = EVIDENCE_DIR / "captures" / "paired_v1"
VARIANTS = (
    "baseline_solid",
    "lit_solid",
    "baseline_textured",
    "lit_textured",
)
VIEWS = ("surface_survey", "sphere_close")
TARGET = CAPTURE_DIR / "light_response_v1.json"


def _image(variant: str, light_state: str, view: str) -> Image.Image:
    path = CAPTURE_DIR / variant / light_state / f"{view}.png"
    if not path.is_file():
        raise SystemExit(f"Missing capture: {path}")
    return Image.open(path).convert("RGBA")


def _difference(first: Image.Image, second: Image.Image) -> dict[str, object]:
    if first.size != second.size:
        raise SystemExit("Matched captures have different dimensions")
    delta = ImageChops.difference(first, second)
    changed = 0
    max_channel = 0
    for pixel in delta.getdata():
        if pixel[0] or pixel[1] or pixel[2] or pixel[3]:
            changed += 1
            max_channel = max(max_channel, pixel[0], pixel[1], pixel[2], pixel[3])
    total = first.width * first.height
    return {
        "changed_pixels": changed,
        "total_pixels": total,
        "changed_fraction": round(changed / total, 6),
        "max_channel_delta": max_channel,
        "pixels_changed": changed > 0,
    }


def main() -> int:
    if TARGET.exists():
        raise SystemExit(f"Refusing to overwrite light response record: {TARGET}")
    if not CAPTURE_DIR.is_dir():
        raise SystemExit(f"Capture directory is missing: {CAPTURE_DIR}")

    off_on: dict[str, object] = {}
    for variant in VARIANTS:
        off_on[variant] = {}
        for view in VIEWS:
            off_on[variant][view] = _difference(
                _image(variant, "light_off", view),
                _image(variant, "light_on", view),
            )

    baseline_vs_lit: dict[str, object] = {}
    for path_name, baseline, lit in (
        ("solid", "baseline_solid", "lit_solid"),
        ("textured", "baseline_textured", "lit_textured"),
    ):
        baseline_vs_lit[path_name] = {}
        for view in VIEWS:
            baseline_vs_lit[path_name][view] = _difference(
                _image(baseline, "light_on", view),
                _image(lit, "light_on", view),
            )

    record = {
        "schema_version": 1,
        "record_id": "issue-272-light-response-v1",
        "note": "Mechanical decoded-pixel differences between matched guarded captures with identical camera, light and material settings. This is an observation, not an appearance judgment or approval. The operator reviews the PNGs on suitable hardware.",
        "comparison": "light_off vs light_on within each variant, and baseline vs lit at light_on for each material path",
        "light_off_vs_on": off_on,
        "baseline_vs_lit": baseline_vs_lit,
        "registration_accepted": False,
        "scale_calibrated": False,
        "operator_review": "pending; agent does not approve appearance or lighting suitability",
    }
    TARGET.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    summary = {
        variant: {view: off_on[variant][view]["pixels_changed"] for view in VIEWS}
        for variant in VARIANTS
    }
    print(f"Wrote {TARGET}")
    print(
        f"Light on/off pixel-change observation: {json.dumps(summary, sort_keys=True)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
