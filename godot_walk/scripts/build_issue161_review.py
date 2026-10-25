"""Build matched profile metrics and a local review page for Chainlink #161."""

from __future__ import annotations

import hashlib
import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-23-issue-161"
sys.path.insert(0, str(ROOT / "godot_walk/scripts"))
from psx_design_review_execution import odiff_command
from psx_design_review_report import compare

PROFILES = ("affine_on", "affine_off")
NOISE_REPEATS = (2, 3)
THRESHOLD = 0.1
TILE_SIZE = (640, 360)
SOURCE_PATHS = (
    "godot_walk/project.godot",
    "godot_walk/scripts/library_psx_preset.gd",
    "godot_walk/shaders/library_psx_textured.gdshader",
    "godot_walk/vendor/ursc/common.gdshaderinc",
    "godot_walk/scenes/issue156_streamed_walkthrough.tscn",
    "godot_walk/scripts/issue156_streamed_walkthrough.gd",
    "godot_walk/scenes/issue161_render_profile_review.tscn",
    "godot_walk/scripts/issue161_render_profile_review.gd",
    "godot_walk/scripts/capture_issue161.gd",
    "godot_walk/scripts/capture_issue161_default.gd",
    "godot_walk/scripts/measure_issue161_profiles.gd",
    "godot_walk/scripts/build_issue161_review.py",
    "godot_walk/evidence/2026-10-23-issue-156/layout_seed_149.json",
    "godot_walk/evidence/2026-10-23-issue-156/catalog_snapshot.json",
    "godot_walk/evidence/2026-10-22-issue-160/bounded_hunyuan_visual.glb",
    "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_visual.glb",
    "godot_walk/assets/psx_extension/textures/wallpaper_source_video.png",
    "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_source_video.png",
    "godot_walk/assets/psx_extension/textures/hunyuan_round3_column_front.png",
)


def main() -> int:
    records = _load_manifest()
    by_profile = _group_records(records)
    if set(by_profile) != set(PROFILES):
        raise ValueError(f"Expected both profiles {PROFILES}, got {tuple(by_profile)}")
    odiff = odiff_command()
    metrics = _compare_profiles(odiff, by_profile)
    metrics["project_default_render_check"] = _compare_project_default(
        odiff, metrics["noise_ceiling_pct"]
    )
    _write_hashes()
    _write_comparison_sheet(by_profile)
    _write_metrics(metrics)
    _write_index(metrics, by_profile)
    print(
        f"built #161 comparison: {len(metrics['matched_views'])} matched views, "
        f"noise ceiling={metrics['noise_ceiling_pct']:.4f}%"
    )
    return 0


def _load_manifest() -> list[dict]:
    records = json.loads((EVIDENCE / "capture_manifest.json").read_text())
    if not records:
        raise ValueError("Capture manifest is empty")
    for record in records:
        path = EVIDENCE / record["path"]
        if not path.is_file():
            raise FileNotFoundError(path)
    return records


def _group_records(records: list[dict]) -> dict[str, dict[str, dict]]:
    grouped = {profile: {} for profile in PROFILES}
    for record in records:
        profile = record["profile_id"]
        capture_id = record["capture_id"]
        if profile not in grouped or capture_id in grouped[profile]:
            raise ValueError(f"Invalid/duplicate capture {profile}/{capture_id}")
        grouped[profile][capture_id] = record
    return grouped


def _compare_profiles(odiff: list[str], grouped: dict[str, dict[str, dict]]) -> dict:
    noise = _measure_noise(odiff, grouped)
    view_ids = sorted(
        record["view_id"] for record in grouped["affine_on"].values()
        if record["capture_id"] == record["view_id"]
    )
    matched = [
        _compare_view(odiff, grouped, view_id)
        for view_id in view_ids
    ]
    noise_values = [sample["diff_pct"] for profile in noise for sample in profile["samples"]]
    ceiling = max(noise_values, default=0.0)
    for row in matched:
        row["above_repeat_noise"] = row["diff_pct"] > ceiling
    return {
        "odiff_version": "odiff-bin@4.5.0",
        "odiff_threshold": THRESHOLD,
        "profiles": {
            "affine_on": {"affine_texture_mapping": True, "texture_filtering": False,
                          "vertex_snap_intensity": 1},
            "affine_off": {"affine_texture_mapping": False, "texture_filtering": False,
                           "vertex_snap_intensity": 1},
        },
        "repeat_noise": noise,
        "noise_ceiling_pct": ceiling,
        "matched_views": matched,
        "operator_choice": "affine_off",
        "operator_review_status": "accepted after live walkthrough on 2026-10-23",
        "interpretation": "ODiff is a pixel-change diagnostic, not an art-direction score.",
        "inconclusive_rule": "A matched view at or below the maximum control-repeat noise is inconclusive.",
    }


def _measure_noise(odiff: list[str], grouped: dict[str, dict[str, dict]]) -> list[dict]:
    rows = []
    for profile in PROFILES:
        first = EVIDENCE / grouped[profile]["repeat_noise_1"]["path"]
        samples = []
        for repeat in NOISE_REPEATS:
            second = EVIDENCE / grouped[profile][f"repeat_noise_{repeat}"]["path"]
            output = EVIDENCE / "diffs" / "noise" / f"{profile}_repeat_1_vs_{repeat}.png"
            samples.append(compare(odiff, first, second, output))
        rows.append({"profile": profile, "samples": samples})
    return rows


def _compare_view(odiff: list[str], grouped: dict[str, dict[str, dict]], view_id: str) -> dict:
    left = EVIDENCE / grouped["affine_on"][view_id]["path"]
    right = EVIDENCE / grouped["affine_off"][view_id]["path"]
    output = EVIDENCE / "diffs" / "profiles" / f"{view_id}.png"
    metadata = grouped["affine_on"][view_id]
    return {"view_id": view_id, "room_instance": metadata["room_instance"],
            "surfaces": metadata["surfaces"], **compare(odiff, left, right, output)}


def _compare_project_default(odiff: list[str], noise_ceiling_pct: float) -> dict:
    manifest_path = EVIDENCE / "captures/project_default/project_default.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("affine_texture_mapping") is not False:
        raise ValueError("Project-default capture must record affine mapping off")
    default_capture = EVIDENCE / manifest["path"].removeprefix(
        "res://evidence/2026-10-23-issue-161/"
    )
    affine_off = EVIDENCE / "captures/affine_off/branch_center.png"
    output = EVIDENCE / "diffs/project_default_vs_affine_off_branch_center.png"
    result = compare(odiff, default_capture, affine_off, output)
    return {
        "affine_texture_mapping": False,
        "capture": str(default_capture.relative_to(EVIDENCE)),
        "reference": "captures/affine_off/branch_center.png",
        "noise_ceiling_pct": noise_ceiling_pct,
        "matches_affine_off_within_noise": result["diff_pct"] <= noise_ceiling_pct,
        **result,
    }


def _write_hashes() -> None:
    records = []
    for relative in SOURCE_PATHS:
        path = ROOT / relative
        records.append({"path": relative, "exists": path.is_file(),
                        "sha256": _sha256(path) if path.is_file() else None})
    output = EVIDENCE / "source_hashes.json"
    output.write_text(json.dumps(records, indent=2) + "\n")


def _write_comparison_sheet(grouped: dict[str, dict[str, dict]]) -> None:
    view_ids = sorted(
        record["view_id"] for record in grouped["affine_on"].values()
        if record["capture_id"] == record["view_id"]
    )
    label_height, gutter = 28, 10
    width = TILE_SIZE[0] * 2 + gutter * 3
    height = gutter + len(view_ids) * (TILE_SIZE[1] + label_height + gutter)
    sheet = Image.new("RGB", (width, height), "#1b2022")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for row, view_id in enumerate(view_ids):
        y = gutter + row * (TILE_SIZE[1] + label_height + gutter)
        for column, profile in enumerate(PROFILES):
            x = gutter + column * (TILE_SIZE[0] + gutter)
            capture = EVIDENCE / grouped[profile][view_id]["path"]
            with Image.open(capture) as source:
                image = source.convert("RGB").resize(TILE_SIZE, Image.Resampling.LANCZOS)
            sheet.paste(image, (x, y + label_height))
            label = "A | affine mapping on" if profile == "affine_on" else "B | affine mapping off"
            draw.text((x + 4, y + 6), f"{view_id} — {label}", fill="#f0eee5", font=font)
    sheet.save(EVIDENCE / "comparison.jpg", quality=92)


def _write_metrics(metrics: dict) -> None:
    (EVIDENCE / "review_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (EVIDENCE / "project_default_comparison.json").write_text(
        json.dumps(metrics["project_default_render_check"], indent=2) + "\n"
    )


def _write_index(metrics: dict, grouped: dict[str, dict[str, dict]]) -> None:
    rows = []
    for row in metrics["matched_views"]:
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%.4f%%</td><td>%s</td></tr>" % (
                html.escape(row["view_id"]), html.escape(row["surfaces"]),
                row["diff_pct"], "above noise" if row["above_repeat_noise"] else "inconclusive")
        )
    noise_rows = []
    for profile in metrics["repeat_noise"]:
        values = ", ".join(f"{sample['diff_pct']:.4f}%" for sample in profile["samples"])
        noise_rows.append(f"<li>{html.escape(profile['profile'])}: {values}</li>")
    content = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Issue 161 PSX affine UV comparison</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1500px;margin:24px auto;padding:0 18px;background:#171b1d;color:#e8e6dc}}
p{{line-height:1.5;max-width:980px}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}
td,th{{padding:8px;text-align:left;border-bottom:1px solid #50585b}}a{{color:#9dd6de}}</style>
<h1>Issue 161: PSX affine UV comparison</h1>
<p>A preserves the pinned URSC affine texture mapping. B disables only affine mapping. Both keep nearest sampling and vertex snap intensity 1. The room, UVs, camera poses, and streamed layout are matched. ODiff records changed pixels; it does not score image quality.</p>
<p>Operator review selected B after a live walkthrough. Affine mapping off is now the project default.</p>
<p>Rendered default check: {metrics['project_default_render_check']['diff_pct']:.4f}% changed pixels from the captured affine-off reference; repeat-noise ceiling {metrics['project_default_render_check']['noise_ceiling_pct']:.4f}%. Matches within noise: {metrics['project_default_render_check']['matches_affine_off_within_noise']}.</p>
<p>Maximum repeated-control noise: {metrics['noise_ceiling_pct']:.4f}%. Differences at or below this ceiling are inconclusive.</p>
<p><a href="REPORT.md">Evidence report</a> · <a href="COMMANDS.md">Commands</a> · <a href="review_metrics.json">Metrics JSON</a> · <a href="project_default_comparison.json">Default render check</a> · <a href="source_hashes.json">Source hashes</a></p>
<h2>Matched views</h2><img src="comparison.jpg" alt="A/B contact sheet">
<table><thead><tr><th>View</th><th>Surfaces</th><th>ODiff changed pixels</th><th>Compared with repeat noise</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<h2>Control-repeat noise</h2><ul>{''.join(noise_rows)}</ul>
<h2>Operator review</h2><p>The operator selected B after a live walkthrough. The F7 comparison scene remains available to revisit profile A on surfaces where it may be useful. Treat the measurements as evidence, not an art-direction score.</p>
</html>"""
    (EVIDENCE / "index.html").write_text(content)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
