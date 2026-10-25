"""Build a contact sheet and source hashes for the #157 connector review."""

from __future__ import annotations

import hashlib
import html
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "godot_walk/evidence/2026-10-23-issue-157"
sys.path.insert(0, str(ROOT / "godot_walk/scripts"))
from psx_design_review_execution import odiff_command
from psx_design_review_report import compare

SOURCES = (
    "godot_walk/project.godot",
    "godot_walk/scripts/capture_issue157_transition.gd",
    "godot_walk/scripts/capture_issue157_floor_candidate.gd",
    "godot_walk/scripts/capture_issue157_ceiling_candidate.gd",
    "godot_walk/scripts/issue157_transition_review.gd",
    "godot_walk/scripts/test_issue157_transition_review.gd",
    "godot_walk/scenes/issue157_transition_review.tscn",
    "godot_walk/scripts/build_issue157_transition_review.py",
    "godot_walk/scripts/library_psx_preset.gd",
    "godot_walk/scripts/issue160_bounded_column_room.gd",
    "godot_walk/scripts/issue160_pocket_room.gd",
    "godot_walk/scripts/issue160_room_geometry.gd",
    "godot_walk/scripts/issue149_pocket_topology.gd",
    "godot_walk/scripts/hunyuan_psx_round1.gd",
    "godot_walk/shaders/library_psx_textured.gdshader",
    "godot_walk/vendor/ursc/common.gdshaderinc",
    "godot_walk/evidence/2026-10-22-issue-160/bounded_hunyuan_visual.glb",
    "godot_walk/evidence/2026-10-21-issue-148/early-pocket/generated/early_pocket_visual.glb",
    "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "godot_walk/assets/psx_extension/textures/wallpaper_source_video.png",
    "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_source_video.png",
    "godot_walk/evidence/2026-10-23-issue-156/layout_seed_149.json",
    "godot_walk/evidence/2026-10-23-issue-157/operator_feedback.json",
)
TILE_SIZE = (640, 360)


def main() -> int:
    records = json.loads((EVIDENCE / "capture_manifest.json").read_text())
    if len(records) != 6:
        raise ValueError(f"Expected six connector review captures, got {len(records)}")
    for record in records:
        if record.get("affine_texture_mapping") is not False:
            raise ValueError(f"Unexpected render profile in {record.get('view_id')}")
        if not (EVIDENCE / record["path"]).is_file():
            raise FileNotFoundError(EVIDENCE / record["path"])
    candidate_metrics = _compare_floor_candidate(records)
    ceiling_metrics = _compare_ceiling_candidate()
    _write_contact_sheet(records)
    _write_floor_candidate_sheet(records, candidate_metrics)
    _write_ceiling_candidate_sheet(ceiling_metrics)
    _write_hashes()
    _write_candidate_metrics(candidate_metrics)
    _write_ceiling_candidate_metrics(ceiling_metrics)
    _write_index(records, candidate_metrics, ceiling_metrics)
    print(f"built #157 transition review: {len(records)} matched approach/threshold views")
    return 0


def _write_contact_sheet(records: list[dict]) -> None:
    columns, rows, gutter, caption_height = 2, 3, 12, 32
    width = columns * TILE_SIZE[0] + (columns + 1) * gutter
    height = rows * (TILE_SIZE[1] + caption_height) + (rows + 1) * gutter
    sheet = Image.new("RGB", (width, height), "#1b2022")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, record in enumerate(records):
        column, row = index % columns, index // columns
        x = gutter + column * (TILE_SIZE[0] + gutter)
        y = gutter + row * (TILE_SIZE[1] + caption_height + gutter)
        with Image.open(EVIDENCE / record["path"]) as source:
            tile = source.convert("RGB").resize(TILE_SIZE, Image.Resampling.LANCZOS)
        sheet.paste(tile, (x, y + caption_height))
        label = f"{record['view_id']} | from {record['room_instance']}"
        draw.text((x + 4, y + 8), label, fill="#f0eee5", font=font)
    sheet.save(EVIDENCE / "contact_sheet.jpg", quality=92)


def _write_hashes() -> None:
    items = []
    for relative in SOURCES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        items.append({"path": relative, "sha256": _sha256(path)})
    (EVIDENCE / "source_hashes.json").write_text(json.dumps(items, indent=2) + "\n")


def _compare_floor_candidate(records: list[dict]) -> dict:
    experiment = json.loads((EVIDENCE / "floor_candidate_manifest.json").read_text())
    repeats = {row["view_id"]: row for row in experiment["records"]
               if row["variant_id"] == "repeat"}
    candidates = {row["view_id"]: row for row in experiment["records"]
                  if row["variant_id"] == "floor_uv_16"}
    odiff = odiff_command()
    rows = []
    for baseline in records:
        view_id = baseline["view_id"]
        repeat = repeats.get(view_id)
        candidate = candidates.get(view_id)
        if repeat is None or candidate is None:
            raise ValueError(f"Missing repeat or candidate capture for {view_id}")
        noise = compare(odiff, EVIDENCE / baseline["path"],
                        EVIDENCE / repeat["path"],
                        EVIDENCE / "diffs/noise" / f"{view_id}.png")
        delta = compare(odiff, EVIDENCE / repeat["path"],
                        EVIDENCE / candidate["path"],
                        EVIDENCE / "diffs/floor_uv_16" / f"{view_id}.png")
        rows.append({"view_id": view_id, "repeat_noise_pct": noise["diff_pct"],
                     "candidate_changed_pct": delta["diff_pct"],
                     "candidate_diff_image": delta["diff_image"],
                     "surfaces": baseline["surfaces"]})
    ceiling = max((row["repeat_noise_pct"] for row in rows), default=0.0)
    for row in rows:
        row["above_repeat_noise"] = row["candidate_changed_pct"] > ceiling
    return {"odiff_version": "odiff-bin@4.5.0", "odiff_threshold": 0.1,
            "candidate": experiment["candidate"],
            "baseline_uv_scale": experiment["baseline_uv_scale"],
            "candidate_uv_scale": experiment["candidate_uv_scale"],
            "repeat_noise_ceiling_pct": ceiling,
            "interpretation": "ODiff reports changed pixels; it is not a visual quality score.",
            "views": rows}


def _write_floor_candidate_sheet(records: list[dict], metrics: dict) -> None:
    gutter, caption_height = 12, 28
    width = 3 * 480 + 4 * gutter
    height = len(records) * (270 + caption_height + gutter) + gutter
    sheet = Image.new("RGB", (width, height), "#1b2022")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    rows = {row["view_id"]: row for row in metrics["views"]}
    for index, baseline in enumerate(records):
        y = gutter + index * (270 + caption_height + gutter)
        view_id = baseline["view_id"]
        candidate = EVIDENCE / "captures/floor_uv_16" / f"{view_id}.png"
        diff_path = rows[view_id]["candidate_diff_image"]
        diff_image = Image.open(diff_path).convert("RGB") if diff_path else Image.new("RGB", (1280, 720), "#1b2022")
        paths = [EVIDENCE / baseline["path"], candidate]
        labels = ["current", "pocket floor UV 4→16", f"ODiff {rows[view_id]['candidate_changed_pct']:.2f}%"]
        for offset, path in enumerate(paths + [diff_image]):
            x = gutter + offset * (480 + gutter)
            if isinstance(path, Image.Image):
                source = path
            else:
                source = Image.open(path)
            with source:
                tile = source.convert("RGB").resize((480, 270), Image.Resampling.LANCZOS)
            sheet.paste(tile, (x, y + caption_height))
            draw.text((x + 4, y + 6), f"{view_id} | {labels[offset]}",
                      fill="#f0eee5", font=font)
    sheet.save(EVIDENCE / "floor_uv_16_comparison.jpg", quality=92)


def _write_candidate_metrics(metrics: dict) -> None:
    (EVIDENCE / "floor_candidate_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )


def _compare_ceiling_candidate() -> dict:
    experiment = json.loads((EVIDENCE / "ceiling_candidate_manifest.json").read_text())
    first_repeats = {row["view_id"]: row for row in experiment["records"]
                     if row["variant_id"] == "ceiling_repeat_a"}
    second_repeats = {row["view_id"]: row for row in experiment["records"]
                      if row["variant_id"] == "ceiling_repeat_b"}
    candidates = {row["view_id"]: row for row in experiment["records"]
                  if row["variant_id"] == "ceiling_source_bridge"}
    odiff = odiff_command()
    rows = []
    for view_id, repeat in second_repeats.items():
        first_repeat = first_repeats.get(view_id)
        candidate = candidates.get(view_id)
        if first_repeat is None or candidate is None:
            raise ValueError(f"Missing repeat or candidate capture for {view_id}")
        noise = compare(odiff, EVIDENCE / first_repeat["path"],
                        EVIDENCE / repeat["path"],
                        EVIDENCE / "diffs/ceiling_noise" / f"{view_id}.png")
        delta = compare(odiff, EVIDENCE / repeat["path"],
                        EVIDENCE / candidate["path"],
                        EVIDENCE / "diffs/ceiling_source_bridge" / f"{view_id}.png")
        rows.append({"view_id": view_id, "repeat_noise_pct": noise["diff_pct"],
                     "candidate_changed_pct": delta["diff_pct"],
                     "candidate_diff_image": delta["diff_image"]})
    if len(rows) != 4:
        raise ValueError(f"Expected four ceiling candidate views, got {len(rows)}")
    ceiling = max((row["repeat_noise_pct"] for row in rows), default=0.0)
    for row in rows:
        row["above_repeat_noise"] = row["candidate_changed_pct"] > ceiling
    return {"odiff_version": "odiff-bin@4.5.0", "odiff_threshold": 0.1,
            "candidate": experiment["candidate"],
            "source_texture": experiment["source_texture"],
            "geometry": experiment["geometry"],
            "visual_only": experiment["visual_only"],
            "collision_added": experiment["collision_added"],
            "repeat_noise_ceiling_pct": ceiling,
            "interpretation": "ODiff reports changed pixels; it is not a visual quality score.",
            "views": rows}


def _write_ceiling_candidate_sheet(metrics: dict) -> None:
    gutter, caption_height = 12, 28
    width = 3 * 480 + 4 * gutter
    height = len(metrics["views"]) * (270 + caption_height + gutter) + gutter
    sheet = Image.new("RGB", (width, height), "#1b2022")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, row in enumerate(metrics["views"]):
        y = gutter + index * (270 + caption_height + gutter)
        view_id = row["view_id"]
        paths = [EVIDENCE / "captures/ceiling_repeat_b" / f"{view_id}.png",
                 EVIDENCE / "captures/ceiling_source_bridge" / f"{view_id}.png"]
        diff_path = row["candidate_diff_image"]
        diff_image = Image.open(diff_path).convert("RGB") if diff_path else Image.new("RGB", (1280, 720), "#1b2022")
        labels = ["unchanged repeat", "source-textured bridge",
                  f"ODiff {row['candidate_changed_pct']:.2f}%"]
        for offset, source in enumerate(paths + [diff_image]):
            x = gutter + offset * (480 + gutter)
            if isinstance(source, Image.Image):
                image = source
            else:
                image = Image.open(source)
            with image:
                tile = image.convert("RGB").resize((480, 270), Image.Resampling.LANCZOS)
            sheet.paste(tile, (x, y + caption_height))
            draw.text((x + 4, y + 6), f"{view_id} | {labels[offset]}",
                      fill="#f0eee5", font=font)
    sheet.save(EVIDENCE / "ceiling_source_bridge_comparison.jpg", quality=92)


def _write_ceiling_candidate_metrics(metrics: dict) -> None:
    (EVIDENCE / "ceiling_candidate_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n"
    )


def _write_index(records: list[dict], metrics: dict, ceiling_metrics: dict) -> None:
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
        % (html.escape(row["view_id"]), html.escape(row["room_instance"]),
           html.escape(row["surfaces"]))
        for row in records
    )
    (EVIDENCE / "index.html").write_text(f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Issue 157 connector material review</title>
<style>body{{font:16px system-ui,sans-serif;max-width:1400px;margin:24px auto;padding:0 18px;background:#171b1d;color:#e8e6dc}}p{{line-height:1.5;max-width:1000px}}img{{width:100%;height:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #50585b}}a{{color:#9dd6de}}</style>
<h1>Issue 157: accepted connector material review</h1>
<p>Six views of the operator-accepted column-to-pocket connection, using the affine-off project default. The operator kept the current 4× pocket floor and rejected the source-textured doorway ceiling bridge, which remains disabled. ODiff reports pixel changes, not preference.</p>
<p><a href="REPORT.md">Report</a> · <a href="COMMANDS.md">Commands</a> · <a href="operator_feedback.json">Operator decision</a> · <a href="floor_candidate_metrics.json">Floor candidate metrics</a> · <a href="ceiling_candidate_metrics.json">Ceiling candidate metrics</a> · <a href="ceiling_candidate_manifest.json">Ceiling candidate manifest</a> · <a href="capture_manifest.json">Baseline poses</a> · <a href="source_hashes.json">Source hashes</a></p>
<img src="contact_sheet.jpg" alt="Six views of the room connector and material transition">
<table><thead><tr><th>View</th><th>Approach module</th><th>Surfaces</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Floor UV candidate</h2><p>Repeat-noise ceiling: {metrics['repeat_noise_ceiling_pct']:.4f}%. Candidate changes above this are measurable but are not scored for quality.</p>
<img src="floor_uv_16_comparison.jpg" alt="Baseline, shared floor-density candidate, and ODiff images">
<table><thead><tr><th>View</th><th>Repeat noise</th><th>Candidate changed pixels</th><th>Above noise</th></tr></thead><tbody>{''.join(f"<tr><td>{html.escape(row['view_id'])}</td><td>{row['repeat_noise_pct']:.4f}%</td><td>{row['candidate_changed_pct']:.4f}%</td><td>{row['above_repeat_noise']}</td></tr>" for row in metrics['views'])}</tbody></table>
<h2>Rejected ceiling bridge candidate</h2><p>The operator chose to keep the bridge off after review. These archived captures show the runtime-only 2.6 × 2.0 m ceiling plane across both sides of the doorway, using the existing source-video texture at UV scale 1.3 × 1.18. It had no collider and changed no saved room or source asset. Repeat-noise ceiling: {ceiling_metrics['repeat_noise_ceiling_pct']:.4f}%. ODiff differences measure changed pixels, not visual quality.</p>
<img src="ceiling_source_bridge_comparison.jpg" alt="Repeated control, source-textured ceiling bridge, and ODiff difference images">
<table><thead><tr><th>View</th><th>Repeat noise</th><th>Candidate changed pixels</th><th>Above noise</th></tr></thead><tbody>{''.join(f"<tr><td>{html.escape(row['view_id'])}</td><td>{row['repeat_noise_pct']:.4f}%</td><td>{row['candidate_changed_pct']:.4f}%</td><td>{row['above_repeat_noise']}</td></tr>" for row in ceiling_metrics['views'])}</tbody></table>
<p>Wall source audit: both room families use wallpaper_source_video.png, nearest filtering, and UV scale 4×4 through the same PSX preset. This points to surface geometry and visible Hunyuan coverage as the remaining causes; a global wall-scale change is not supported by the source audit.</p>
</html>""")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
