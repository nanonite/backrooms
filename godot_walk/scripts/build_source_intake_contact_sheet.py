"""Build CPU-only scaled previews for operator source selection."""

from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from video_source_library import (
    INDEX_PATH,
    ROOT,
    VIDEO_SOURCE_KIND,
    SourceLibraryError,
    manifest_video_content,
    sha256_file,
)

THUMBNAIL_SIZE = (480, 270)
ROW_HEADER = 44
BACKGROUND = (20, 22, 28)
TEXT = (244, 244, 244)
ACCENT = (132, 183, 237)


def _read_sources(root: Path) -> list[dict[str, Any]]:
    index_path = root / INDEX_PATH
    index = json.loads(index_path.read_text(encoding="utf-8"))
    result = []
    for entry in index["sources"]:
        manifest_path = root / entry["manifest_path"]
        if sha256_file(manifest_path) != entry["manifest_sha256"]:
            raise SourceLibraryError(f"Source manifest changed: {entry['source_id']}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("source_kind", VIDEO_SOURCE_KIND) != VIDEO_SOURCE_KIND:
            continue
        video = manifest_video_content(manifest)
        video_path = root / video["path"]
        if sha256_file(video_path) != video["sha256"]:
            raise SourceLibraryError(f"Source video changed: {entry['source_id']}")
        result.append({**entry, "metadata": video["metadata"]})
    return sorted(result, key=lambda item: item["source_path"].casefold())


def _previously_sampled_videos(root: Path) -> set[str]:
    manifest = root / "godot_walk/evidence/2026-10-24-issue-163/source_manifest.json"
    document = json.loads(manifest.read_text(encoding="utf-8"))
    return set(document["contact_sheet"]["videos"])


def _sample_times(source: dict[str, Any]) -> list[float]:
    duration = source["metadata"]["duration_seconds"]
    return [round(duration * fraction, 3) for fraction in (0.15, 0.5, 0.85)]


def _decode_preview(video: Path, seconds: float, destination: Path) -> None:
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        str(seconds),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2",
        "-y",
        str(destination),
    ]
    subprocess.run(command, check=True, timeout=90, capture_output=True)
    with Image.open(destination) as image:
        if image.size != THUMBNAIL_SIZE:
            raise SourceLibraryError(f"Unexpected preview dimensions: {image.size}")


def _draw_contact_sheet(
    sources: list[dict[str, Any]], root: Path, image_path: Path
) -> dict[str, Any]:
    card_width = THUMBNAIL_SIZE[0]
    sheet = Image.new(
        "RGB",
        (card_width * 3, (ROW_HEADER + THUMBNAIL_SIZE[1]) * len(sources)),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    entries = []
    with tempfile.TemporaryDirectory(prefix="source-preview-") as temporary:
        temporary_dir = Path(temporary)
        for row, source in enumerate(sources):
            video = root / source["source_path"]
            times = _sample_times(source)
            header_y = row * (ROW_HEADER + THUMBNAIL_SIZE[1])
            draw.text((8, header_y + 3), source["source_id"], fill=ACCENT, font=font)
            draw.text((8, header_y + 20), source["source_path"], fill=TEXT, font=font)
            previews = []
            for column, seconds in enumerate(times):
                preview = temporary_dir / f"{row:02d}_{column}.png"
                _decode_preview(video, seconds, preview)
                x = column * card_width
                y = header_y + ROW_HEADER
                with Image.open(preview) as image:
                    sheet.paste(image.convert("RGB"), (x, y))
                draw.rectangle((x, y, x + 150, y + 22), fill=BACKGROUND)
                draw.text(
                    (x + 6, y + 5), f"{seconds:.2f} s preview", fill=TEXT, font=font
                )
                previews.append({"time_seconds": seconds, "preview_only": True})
            entries.append(
                {
                    "source_id": source["source_id"],
                    "source_path": source["source_path"],
                    "source_sha256": source["source_sha256"],
                    "metadata": source["metadata"],
                    "samples": previews,
                }
            )
    sheet.save(image_path, quality=92, optimize=True)
    return {
        "sources": entries,
        "contact_sheet": image_path.relative_to(root).as_posix(),
    }


def build(output_relative: str, root: Path = ROOT) -> Path:
    output = root / output_relative
    if output.exists():
        raise FileExistsError(
            f"Refusing to overwrite evidence directory: {output_relative}"
        )
    sources = _read_sources(root)
    if not sources:
        raise SourceLibraryError("No registered source videos to preview")
    output.mkdir(parents=True, exist_ok=False)
    summary = _draw_contact_sheet(sources, root, output / "source_contact_sheet.jpg")
    previous = _previously_sampled_videos(root)
    candidates = [
        source for source in sources if Path(source["source_path"]).name not in previous
    ]
    summary["candidate_source_ids"] = [source["source_id"] for source in candidates]
    if candidates:
        candidate_sheet = output / "new_source_candidates.jpg"
        _draw_contact_sheet(candidates, root, candidate_sheet)
        summary["candidate_contact_sheet"] = candidate_sheet.relative_to(
            root
        ).as_posix()
    summary.update(
        {
            "schema_version": 1,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "sampling": "CPU ffmpeg seeks; resized/padded previews for source selection only",
            "seed_rule": "A Hunyuan seed must later be decoded directly from the chosen source at original resolution.",
        }
    )
    (output / "inventory.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    _write_report(output, summary)
    _write_review_page(output, summary)
    return output / "source_contact_sheet.jpg"


def _write_report(output: Path, summary: dict[str, Any]) -> None:
    rows = [
        "# Issue #167 — local source intake previews",
        "",
        "The contact sheet contains scaled CPU-decoded previews at 15%, 50%, and 85% of each clip. It is for source suitability review only; no preview is a Hunyuan seed.",
        "A selected seed must be decoded directly from its source video at original dimensions and recorded with the source and frame hashes.",
        "The separate `new_source_candidates.jpg` contains clips absent from the earlier #163 contact sheet; these remain unreviewed candidates.",
        "",
        "| Source ID | Video | Dimensions | Duration | SHA-256 |",
        "|---|---|---:|---:|---|",
    ]
    for source in summary["sources"]:
        metadata = source["metadata"]
        rows.append(
            f"| `{source['source_id']}` | `{source['source_path']}` | "
            f"{metadata['width']}×{metadata['height']} | {metadata['duration_seconds']:.3f}s | "
            f"`{source['source_sha256']}` |"
        )
    rows.extend(
        [
            "",
            "## Review boundary",
            "",
            "No room count, video connectivity, metric scale, or Hunyuan suitability is inferred from this index. Existing #163/#165 room decisions are linked as historical records. The operator selects a source and seed before any inference.",
            "",
        ]
    )
    (output / "REPORT.md").write_text("\n".join(rows), encoding="utf-8")


def _write_review_page(output: Path, summary: dict[str, Any]) -> None:
    candidate_ids = set(summary["candidate_source_ids"])
    rows = []
    for source in summary["sources"]:
        group = (
            "unreviewed intake candidate"
            if source["source_id"] in candidate_ids
            else "previously sampled local clip"
        )
        metadata = source["metadata"]
        rows.append(
            "<tr><td>"
            + group
            + "</td><td><code>"
            + escape(source["source_id"])
            + "</code></td>"
            + "<td>"
            + escape(source["source_path"])
            + "</td><td>"
            + f"{metadata['width']}×{metadata['height']}, {metadata['duration_seconds']:.1f}s"
            + "</td></tr>"
        )
    html = (
        """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Issue 167 source intake</title>
<style>body{font:16px system-ui;max-width:1500px;margin:2rem auto;padding:0 1rem;background:#15171c;color:#eee}img{width:100%;height:auto;margin:1rem 0}table{border-collapse:collapse;width:100%}td,th{padding:.55rem;border-bottom:1px solid #555;text-align:left}code{color:#9cd}</style>
<h1>Issue #167 · source intake review</h1>
<p>Preview frames are CPU-decoded, scaled samples. Choose a source first; a seed must then be decoded directly at original resolution. No model inference has run.</p>
<h2>Unreviewed local candidates</h2><img src="new_source_candidates.jpg" alt="Unreviewed source previews">
<h2>Full local registry</h2><img src="source_contact_sheet.jpg" alt="All registered sources">
<h2>Inventory</h2><table><thead><tr><th>Group</th><th>Source ID</th><th>Source path</th><th>Metadata</th></tr></thead><tbody>"""
        + "".join(rows)
        + """</tbody></table>
<p><a href="REPORT.md">Inventory report</a> · <a href="inventory.json">Manifest and hashes</a></p></html>
"""
    )
    (output / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(build(args.output).as_posix())
