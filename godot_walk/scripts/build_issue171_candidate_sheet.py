"""Build labelled contact sheets from a mechanical frame ranking report.

CPU-only: reads direct-source frame PNGs and the deterministic
``run_freeview_consensus.py inventory`` report. It never decodes, resizes,
edits, scores or selects a seed; previews are scaled copies for operator
review only.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from deterministic_json import sha256_file
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = "#161b1e"
TEXT = "#eef3f0"
MUTED = "#9db1ad"
ACCENT = "#84b7ed"
THUMBNAIL_SIZE = (480, 270)
SMALL_THUMBNAIL_SIZE = (320, 180)
CAPTION_HEIGHT = 44
COLUMNS = 3
SMALL_COLUMNS = 4


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args(argv)
    ranking_path = ROOT / args.ranking
    report = json.loads(ranking_path.read_text(encoding="utf-8"))
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    views = _verified_views(report)
    ranked = sorted(views, key=lambda view: view["mechanical"]["mechanical_rank"])
    top = ranked[: args.top]
    _write_sheet(top, output_dir / "top-candidates.jpg", THUMBNAIL_SIZE, COLUMNS, True)
    ordered = sorted(views, key=lambda view: view["index_zero_based"])
    _write_sheet(
        ordered, output_dir / "coverage.jpg", SMALL_THUMBNAIL_SIZE, SMALL_COLUMNS, False
    )
    print(
        json.dumps(
            {
                "top_candidates": len(top),
                "coverage_frames": len(ordered),
                "output_dir": output_dir.relative_to(ROOT).as_posix(),
            }
        )
    )
    return 0


def _verified_views(report: dict[str, Any]) -> list[dict[str, Any]]:
    views = report.get("views")
    if not isinstance(views, list) or not views:
        raise ValueError("Ranking report has no views")
    for view in views:
        path = ROOT / view["path"]
        if sha256_file(path) != view["sha256"]:
            raise ValueError(f"Frame bytes changed: {view['path']}")
    return views


def _write_sheet(
    views: list[dict[str, Any]],
    destination: Path,
    size: tuple[int, int],
    columns: int,
    show_rank: bool,
) -> None:
    rows = (len(views) + columns - 1) // columns
    sheet = Image.new(
        "RGB", (columns * size[0], rows * (size[1] + CAPTION_HEIGHT)), BACKGROUND
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for position, view in enumerate(views):
        x = (position % columns) * size[0]
        y = (position // columns) * (size[1] + CAPTION_HEIGHT)
        source = ROOT / view["path"]
        with Image.open(source) as image:
            tile = ImageOps.fit(
                image.convert("RGB"), size, method=Image.Resampling.LANCZOS
            )
        sheet.paste(tile, (x, y))
        _draw_caption(draw, font, view, x, y + size[1], show_rank)
    sheet.save(destination, quality=92, optimize=True)


def _draw_caption(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    view: dict[str, Any],
    x: int,
    y: int,
    show_rank: bool,
) -> None:
    metrics = view["mechanical"]
    lead = (
        f"rank {metrics['mechanical_rank']} | {view['frame_id']}"
        if show_rank
        else f"{view['pts_seconds']:.2f} s | {view['frame_id']}"
    )
    draw.text(
        (x + 10, y + 6),
        f"{lead} | {view['pts_seconds']:.2f} s | score {metrics['mechanical_score']:.6f}",
        fill=TEXT,
        font=font,
    )
    draw.text(
        (x + 10, y + 24),
        (
            f"native {view['index_zero_based']} | focus {metrics['focus_score']:.3f}"
            f" | exposure {metrics['exposure_score']:.3f}"
            f" | dup {metrics['duplicate_similarity']:.3f}"
        ),
        fill=MUTED,
        font=font,
    )


if __name__ == "__main__":
    raise SystemExit(main())
