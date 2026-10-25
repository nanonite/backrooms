"""Validate matched captures and produce pixel-change diagnostics."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from hunyuan_round1_contract import ROUND_ID, VARIANTS, VIEW_IDS
from PIL import Image, ImageDraw, ImageFont

THUMBNAIL = (480, 270)
ODIFF_THRESHOLD = "0.1"


def validate_captures(
    out_dir: Path,
    variants: tuple[str, ...] = VARIANTS,
    view_ids: tuple[str, ...] = VIEW_IDS,
    repeats_by_variant: dict[str, tuple[int, ...]] | None = None,
) -> dict[str, dict[str, Any]]:
    if repeats_by_variant is None:
        repeats_by_variant = {
            variant: (1, 2, 3) if variant == "preserve_hunyuan" else (1,)
            for variant in variants
        }
    frames = {}
    for variant in variants:
        repeats = repeats_by_variant.get(variant, (1,))
        for repeat in repeats:
            frames[f"{variant}:{repeat}"] = _validate_capture_run(
                out_dir, variant, repeat, view_ids
            )
    return frames


def _validate_capture_run(
    out_dir: Path, variant: str, repeat: int, view_ids: tuple[str, ...]
) -> dict[str, Any]:
    run_dir = out_dir / "captures" / variant / f"repeat_{repeat}"
    metadata = json.loads((run_dir / "frames.json").read_text(encoding="utf-8"))
    actual_ids = [Path(view["filename"]).stem for view in metadata["views"]]
    if actual_ids != list(view_ids):
        raise ValueError(f"Matched view IDs changed for {variant} repeat {repeat}")
    for view in metadata["views"]:
        image = run_dir / "spawn_headings" / view["filename"]
        if not image.is_file():
            raise FileNotFoundError(image)
    return metadata


def build_metrics(
    out_dir: Path,
    round_id: str = ROUND_ID,
    variants: tuple[str, ...] = VARIANTS,
    view_ids: tuple[str, ...] = VIEW_IDS,
    baseline_variant: str = "preserve_hunyuan",
    candidate_variant: str = "source_surface_cleanup",
    scope: str = "Authored surface coverage changes; room bounds, collision and camera poses match.",
) -> dict[str, Any]:
    from psx_design_review_execution import odiff_command

    odiff = odiff_command()
    noise = [
        _repeat_noise(out_dir, odiff, baseline_variant, repeat, view_ids)
        for repeat in (2, 3)
    ]
    noise_ceiling = _noise_ceiling(noise, view_ids)
    deltas = [
        _compare(
            out_dir,
            odiff,
            baseline_variant,
            1,
            candidate_variant,
            1,
            view_id,
            f"diffs/variant_delta/{view_id}.png",
            noise_ceiling[view_id],
        )
        for view_id in view_ids
    ]
    metrics = {
        "round_id": round_id,
        "odiff_tool": "odiff-bin@4.5.0",
        "scope": scope,
        "odiff_threshold": float(ODIFF_THRESHOLD),
        "control_repeat_noise": noise,
        "per_view_noise_ceiling_pct": noise_ceiling,
        "variant_pixel_deltas": deltas,
        "interpretation": "ODiff is a visual-difference diagnostic, not an art-direction score.",
        "rule": "A variant delta at or below its matched control-repeat noise ceiling is inconclusive.",
    }
    _write_json(out_dir / "review_metrics.json", metrics)
    return metrics


def _repeat_noise(
    out_dir: Path,
    odiff: list[str],
    baseline_variant: str,
    repeat: int,
    view_ids: tuple[str, ...],
) -> dict[str, Any]:
    views = [
        _compare(
            out_dir,
            odiff,
            baseline_variant,
            1,
            baseline_variant,
            repeat,
            view_id,
            f"diffs/control_noise/repeat_{repeat}/{view_id}.png",
        )
        for view_id in view_ids
    ]
    return {
        "repeat": repeat,
        "views": views,
        "max_diff_pct": max(item["diff_pct"] for item in views),
    }


def _noise_ceiling(
    noise: list[dict[str, Any]], view_ids: tuple[str, ...]
) -> dict[str, float]:
    return {
        view_id: max(
            view["diff_pct"]
            for repeat in noise
            for view in repeat["views"]
            if view["view_id"] == view_id
        )
        for view_id in view_ids
    }


def _compare(
    out_dir: Path,
    command: list[str],
    left_variant: str,
    left_repeat: int,
    right_variant: str,
    right_repeat: int,
    view_id: str,
    output_path: str,
    noise_ceiling: float | None = None,
) -> dict[str, Any]:
    left = _capture_path(out_dir, left_variant, left_repeat, view_id)
    right = _capture_path(out_dir, right_variant, right_repeat, view_id)
    output = out_dir / output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    result = _run_odiff(command, left, right, output, view_id, out_dir)
    comparison = {"view_id": view_id, **result}
    if noise_ceiling is not None:
        comparison["control_repeat_noise_ceiling_pct"] = noise_ceiling
        comparison["interpretation"] = (
            "inconclusive"
            if result["diff_pct"] <= noise_ceiling
            else "measurable_pixel_change"
        )
    return comparison


def _run_odiff(
    command: list[str],
    left: Path,
    right: Path,
    output: Path,
    view_id: str,
    out_dir: Path,
) -> dict[str, Any]:
    arguments = [
        *command,
        str(left),
        str(right),
        str(output),
        "--threshold",
        ODIFF_THRESHOLD,
        "--parsable-stdout",
    ]
    result = subprocess.run(
        arguments, capture_output=True, text=True, timeout=90, check=False
    )
    if result.returncode not in (0, 22):
        raise RuntimeError(f"ODiff failed for {view_id}: {result.stderr.strip()}")
    return _parse_odiff(result, output, view_id, out_dir)


def _parse_odiff(
    result: subprocess.CompletedProcess[str], output: Path, view_id: str, out_dir: Path
) -> dict[str, Any]:
    match = re.search(r"(\d+);([0-9]+(?:\.[0-9]+)?)", result.stdout)
    if match is None:
        if result.returncode != 0:
            raise RuntimeError(f"ODiff returned no metric for {view_id}")
        count, percent = 0, 0.0
    else:
        count, percent = int(match.group(1)), float(match.group(2))
    diff_image = output.relative_to(out_dir).as_posix() if count else None
    return {"diff_pixels": count, "diff_pct": percent, "diff_image": diff_image}


def _capture_path(out_dir: Path, variant: str, repeat: int, view_id: str) -> Path:
    return (
        out_dir
        / "captures"
        / variant
        / f"repeat_{repeat}"
        / "spawn_headings"
        / f"{view_id}.png"
    )


def draw_contact_sheet(out_dir: Path) -> None:
    draw_variant_contact_sheet(out_dir, VARIANTS, VIEW_IDS)


def draw_variant_contact_sheet(
    out_dir: Path, variants: tuple[str, ...], view_ids: tuple[str, ...]
) -> None:
    caption_height, gap = 26, 10
    width = len(variants) * THUMBNAIL[0] + (len(variants) + 1) * gap
    height = len(view_ids) * (THUMBNAIL[1] + caption_height + gap) + gap
    sheet = Image.new("RGB", (width, height), (31, 34, 33))
    _draw_view_pairs(sheet, out_dir, variants, view_ids, caption_height, gap)
    sheet.save(out_dir / "candidate_contact_sheet.jpg", quality=94)


def _draw_view_pairs(
    sheet: Image.Image,
    out_dir: Path,
    variants: tuple[str, ...],
    view_ids: tuple[str, ...],
    caption_height: int,
    gap: int,
) -> None:
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for row, view_id in enumerate(view_ids):
        y = gap + row * (THUMBNAIL[1] + caption_height + gap)
        for column, variant in enumerate(variants):
            x = gap + column * (THUMBNAIL[0] + gap)
            _paste_capture(sheet, draw, font, out_dir, view_id, variant, x, y)


def _paste_capture(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    out_dir: Path,
    view_id: str,
    variant: str,
    x: int,
    y: int,
) -> None:
    path = _capture_path(out_dir, variant, 1, view_id)
    with Image.open(path) as image:
        tile = image.convert("RGB").resize(THUMBNAIL, Image.Resampling.LANCZOS)
    sheet.paste(tile, (x, y))
    draw.text(
        (x + 5, y + THUMBNAIL[1] + 6),
        f"{view_id} | {variant}",
        font=font,
        fill=(245, 244, 236),
    )


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
