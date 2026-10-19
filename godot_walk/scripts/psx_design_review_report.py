#!/usr/bin/env python3
"""Build local ODiff comparisons and reviewer contact sheets for #120."""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ODIFF_THRESHOLD = "0.1"
VARIANTS = ("v2_control", "door_flush", "door_removed")
REPEATS = ("repeat_2", "repeat_3")
THUMBNAIL = (480, 270)


def load_frames(directory: Path) -> dict:
    """Load and validate the capture metadata for one run."""
    metadata = json.loads((directory / "frames.json").read_text())
    names = [view["filename"] for view in metadata.get("views", [])]
    if not names or len(set(names)) != len(names):
        raise ValueError(f"invalid or duplicate views in {directory}")
    for name in names:
        if not (directory / "spawn_headings" / name).is_file():
            raise FileNotFoundError(directory / "spawn_headings" / name)
    return metadata


def compare(odiff: list[str], left: Path, right: Path, output: Path) -> dict:
    """Run ODiff once and retain its default-style pixel count and percentage."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [*odiff, str(left), str(right), str(output), "--threshold", ODIFF_THRESHOLD,
               "--parsable-stdout"]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 22):
        raise RuntimeError(f"ODiff failed ({result.returncode}): {result.stderr.strip()}")
    match = re.search(r"(\d+);([0-9]+(?:\.[0-9]+)?)", result.stdout)
    if match is None:
        if result.returncode != 0:
            raise RuntimeError(f"ODiff returned no parsable result: {result.stdout}")
        count, percent = 0, 0.0
    else:
        count, percent = int(match.group(1)), float(match.group(2))
    if count and not output.is_file():
        raise RuntimeError(f"ODiff reported a difference but did not write {output}")
    return {"diff_pixels": count, "diff_pct": percent,
            "diff_image": str(output) if count else None,
            "odiff_threshold": float(ODIFF_THRESHOLD)}


def _view_map(metadata: dict) -> dict[str, dict]:
    return {view["filename"]: view for view in metadata["views"]}


def _compare_runs(odiff: list[str], left_dir: Path, right_dir: Path,
                  output_dir: Path, label: str) -> list[dict]:
    left = load_frames(left_dir)
    right = load_frames(right_dir)
    left_views, right_views = _view_map(left), _view_map(right)
    if set(left_views) != set(right_views):
        raise ValueError(f"matched view names differ: {left_dir} vs {right_dir}")
    comparisons = []
    for filename, view in left_views.items():
        stats = compare(odiff, left_dir / "spawn_headings" / filename,
                        right_dir / "spawn_headings" / filename,
                        output_dir / f"{label}_{Path(filename).stem}.png")
        comparisons.append({"view": filename, "station": view["station"],
                            "heading": view["heading"], **stats})
    return comparisons


def _draw_contact_rows(sheet: Image.Image, out_dir: Path, variant_ids: tuple[str, ...],
                       variants: dict, names: list[str], label_height: int,
                       gutter: int) -> None:
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for row, filename in enumerate(names):
        for column, variant in enumerate(variant_ids):
            x = gutter + column * (THUMBNAIL[0] + gutter)
            y = gutter + row * (THUMBNAIL[1] + label_height + gutter)
            heading = variants[variant][filename]["heading"]
            draw.text((x + 4, y + 4), f"{variant} | {heading}",
                      fill=(240, 240, 240), font=font)
            path = out_dir / "captures" / variant / "repeat_1" / "spawn_headings" / filename
            with Image.open(path) as image:
                thumb = image.convert("RGB").resize(THUMBNAIL, Image.Resampling.LANCZOS)
            sheet.paste(thumb, (x, y + label_height))


def _contact_sheet(out_dir: Path, station: str, frames: dict[str, dict],
                   variant_ids: tuple[str, ...], baseline_id: str) -> Path:
    variants = {variant: _view_map(frames[variant]) for variant in variant_ids}
    names = [name for name, view in variants[baseline_id].items()
             if view["station"] == station]
    names.sort(key=lambda name: variants[baseline_id][name]["heading"])
    label_height, gutter = 24, 8
    width = len(variant_ids) * THUMBNAIL[0] + (len(variant_ids) + 1) * gutter
    height = len(names) * (THUMBNAIL[1] + label_height + gutter) + gutter
    sheet = Image.new("RGB", (width, height), (28, 31, 34))
    _draw_contact_rows(sheet, out_dir, variant_ids, variants, names, label_height, gutter)
    target = out_dir / "contact_sheets" / f"{station}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, quality=92)
    return target


def _metric_rows(out_dir: Path, metrics: dict) -> list[str]:
    rows = []
    for comparison in metrics["candidate_comparisons"]:
        for view in comparison["views"]:
            diff_path = view["diff_image"]
            diff = ("<a href=\"%s\">open</a>" % html.escape(
                Path(diff_path).relative_to(out_dir).as_posix())
                if diff_path else "identical at configured ODiff threshold")
            rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%.3f%%</td><td>%s</td></tr>"
                         % (html.escape(comparison["variant"]), html.escape(view["view"]),
                            view["diff_pixels"], view["diff_pct"], diff))
    return rows


def _gallery_sections(out_dir: Path, sheets: list[Path]) -> list[str]:
    return ["<section><h2>%s</h2><img src=\"%s\" alt=\"%s matched views\"></section>"
            % (html.escape(sheet.stem), html.escape(str(sheet.relative_to(out_dir))),
               html.escape(sheet.stem)) for sheet in sheets]


def _write_index(out_dir: Path, sheets: list[Path], metrics: dict, title: str,
                 scope: str, review_prompt: str) -> None:
    rows = _metric_rows(out_dir, metrics)
    sections = _gallery_sections(out_dir, sheets)
    links = ["<a href=\"review_metrics.json\">Full visual metrics</a>",
             "<a href=\"review_manifest.json\">Capture manifest</a>"]
    if (out_dir / "route_drift.json").is_file():
        links.append("<a href=\"route_drift.json\">Route repeat drift</a>")
    if (out_dir / "operator_feedback.md").is_file():
        links.append("<a href=\"operator_feedback.md\">Operator feedback sheet</a>")
    noise_max = max(item["max_diff_pct"] for item in metrics["repeat_noise"])
    page = """<!doctype html><meta charset="utf-8"><title>__TITLE__</title>
<style>body{font:14px system-ui,sans-serif;margin:24px;background:#f3f4f5;color:#202326}
main{max-width:1500px;margin:auto}img{max-width:100%;height:auto}table{border-collapse:collapse;width:100%}
th,td{text-align:left;border-bottom:1px solid #c9cccf;padding:6px}section{margin:28px 0}</style>
<main><h1>__TITLE__</h1>
<p>__SCOPE__ ODiff locates pixel changes; it does not score art direction.
ODiff threshold: 0.1. Control repeats differ by up to __NOISE__% of pixels. Candidate deltas
at or below that measured noise are inconclusive; no threshold was tuned.</p>
__SECTIONS__<h2>Operator Review</h2><p>__PROMPT__</p><h2>Candidate Pixel Deltas</h2><table><thead><tr><th>Variant</th><th>View</th>
<th>Changed pixels</th><th>Changed share</th><th>Diff image</th></tr></thead><tbody>__ROWS__</tbody></table>
<p>__LINKS__</p>
</main>""".replace("__SECTIONS__", "\n".join(sections)).replace(
        "__ROWS__", "\n".join(rows)).replace("__NOISE__", f"{noise_max:.3f}").replace(
        "__TITLE__", html.escape(title)).replace("__SCOPE__", html.escape(scope)).replace(
        "__PROMPT__", html.escape(review_prompt)).replace("__LINKS__", " | ".join(links))
    (out_dir / "index.html").write_text(page)


def _repeat_noise(odiff: list[str], out_dir: Path, baseline_dir: Path) -> list[list[dict]]:
    return [_compare_runs(odiff, baseline_dir / "repeat_1", baseline_dir / repeat,
                          out_dir / "diffs" / "baseline_noise", repeat)
            for repeat in REPEATS]


def _candidate_deltas(odiff: list[str], out_dir: Path, baseline_dir: Path,
                      variant_ids: tuple[str, ...], baseline_id: str) -> list[dict]:
    candidates = []
    for variant in variant_ids:
        if variant == baseline_id:
            continue
        views = _compare_runs(odiff, baseline_dir / "repeat_1",
                              out_dir / "captures" / variant / "repeat_1",
                              out_dir / "diffs" / variant, variant)
        candidates.append({"variant": variant, "views": views,
                           "mean_diff_pct": round(sum(v["diff_pct"] for v in views) / len(views), 3),
                           "max_diff_pct": max(v["diff_pct"] for v in views)})
    return candidates


def _metrics_document(noise: list[list[dict]], candidates: list[dict], scope: str) -> dict:
    repeats = [{"repeat": repeat, "views": results,
                "max_diff_pct": max(v["diff_pct"] for v in results)}
               for repeat, results in zip(REPEATS, noise)]
    return {"scope": scope,
            "repeat_noise": repeats, "candidate_comparisons": candidates,
            "odiff_threshold": float(ODIFF_THRESHOLD),
            "repeatability_note": "Candidate deltas at or below maximum control-repeat noise are inconclusive.",
            "interpretation": "ODiff is a pixel-change diagnostic, not an art-direction score."}


def build_report(out_dir: Path, odiff: list[str], variant_ids: tuple[str, ...] = VARIANTS,
                 title: str = "PSX Design Review: Hatch Variants",
                 scope: str = "Only the service hatch policy changes.",
                 review_prompt: str = "Choose, reject, or rank the candidates and add a reason.",
                 baseline_id: str = "v2_control") -> dict:
    """Compare repeated control renders and build local review artifacts."""
    frames = {variant: load_frames(out_dir / "captures" / variant / "repeat_1")
              for variant in variant_ids}
    if baseline_id not in frames:
        raise ValueError(f"baseline variant is missing from review set: {baseline_id}")
    baseline = out_dir / "captures" / baseline_id
    noise = _repeat_noise(odiff, out_dir, baseline)
    candidates = _candidate_deltas(odiff, out_dir, baseline, variant_ids, baseline_id)
    metrics = _metrics_document(noise, candidates, scope)
    sheets = [_contact_sheet(out_dir, station, frames, variant_ids, baseline_id)
              for station in ("patch_anchor", "transition", "column", "far_room")]
    (out_dir / "review_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    _write_index(out_dir, sheets, metrics, title, scope, review_prompt)
    return metrics
