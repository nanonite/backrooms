"""Explicit, overwrite-safe extraction stages for direct source-video evidence."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from video_adaptation_validation import ROOT, AdaptationValidationError, repo_file, sha256_file


def _safe_output_dir(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    if not path.is_relative_to(ROOT):
        raise AdaptationValidationError("Output path must stay inside the repository")
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing extraction output: {relative_path}")
    return path


def _video_metadata(video: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    stream = next(item for item in payload["streams"] if item.get("codec_type") == "video")
    numerator, denominator = map(int, stream["r_frame_rate"].split("/"))
    return {
        "width": int(stream["width"]), "height": int(stream["height"]),
        "fps": numerator / denominator, "frame_count": int(stream["nb_frames"]),
        "duration_seconds": float(payload["format"]["duration"]),
    }


def extract_source_frames(video_relative: str, indices: list[int], output_relative: str) -> Path:
    video = repo_file(video_relative)
    metadata = _video_metadata(video)
    selected = sorted(set(indices))
    if not selected or selected[0] < 0 or selected[-1] >= metadata["frame_count"]:
        raise ValueError("Frame indices must be unique valid zero-based source indices")
    output = _safe_output_dir(output_relative)
    output.mkdir(parents=True)
    frames = []
    for index in selected:
        frame_number = index + 1
        destination = output / f"frame_{frame_number:04d}.png"
        filter_expression = f"select=eq(n\\,{index})"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video), "-vf",
             filter_expression, "-frames:v", "1", "-vsync", "0", str(destination)],
            check=True,
            timeout=90,
        )
        with Image.open(destination) as image:
            if image.size != (metadata["width"], metadata["height"]):
                raise ValueError(f"Decoded frame dimensions changed at source index {index}")
        relative = destination.relative_to(ROOT).as_posix()
        frames.append({
            "frame_id": f"frame_{frame_number:04d}", "index_zero_based": index,
            "timestamp_seconds": index / metadata["fps"], "path": relative,
            "sha256": sha256_file(destination),
            "decode_operation": "direct_source_video_decode_no_resize_or_edit",
        })
    manifest = {
        "schema_version": 1, "source_video": video_relative,
        "source_video_sha256": sha256_file(video), "metadata": metadata,
        "decoder": "ffmpeg select by decoded zero-based frame index",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "frames": frames,
    }
    manifest_path = output / "extraction_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def extract_source_crops(manifest_relative: str, plan_relative: str, output_relative: str) -> Path:
    manifest_path = repo_file(manifest_relative)
    plan_path = repo_file(plan_relative)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    frames = {frame["frame_id"]: frame for frame in manifest["frames"]}
    output = _safe_output_dir(output_relative)
    output.mkdir(parents=True)
    crops = []
    for crop in plan["crops"]:
        _extract_one_crop(crop, frames, output, crops)
    result = {
        "schema_version": 1, "frame_manifest": manifest_relative,
        "frame_manifest_sha256": sha256_file(manifest_path),
        "operation": "direct_rectangular_crop_no_resize_or_color_edit", "crops": crops,
    }
    destination = output / "crop_manifest.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return destination


def _extract_one_crop(crop: dict[str, Any], frames: dict[str, dict[str, Any]], output: Path,
                      results: list[dict[str, Any]]) -> None:
    frame = frames.get(crop["frame_id"])
    if frame is None or sha256_file(repo_file(frame["path"])) != frame["sha256"]:
        raise AdaptationValidationError(f"Missing or changed source frame: {crop['frame_id']}")
    name = crop["name"]
    if re.fullmatch(r"[a-z0-9_]+", name) is None:
        raise ValueError(f"Unsafe crop name: {name}")
    bounds = crop["source_pixel_bounds_xyxy"]
    with Image.open(repo_file(frame["path"])) as source:
        left, top, right, bottom = bounds
        if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
            raise ValueError(f"Crop bounds exceed frame dimensions: {name}")
        destination = output / f"{name}.png"
        source.crop(tuple(bounds)).save(destination)
    results.append({
        "name": name, "frame_id": crop["frame_id"],
        "source_pixel_bounds_xyxy": bounds,
        "path": destination.relative_to(ROOT).as_posix(),
        "dimensions": _image_dimensions(destination), "sha256": sha256_file(destination),
    })


def _image_dimensions(path: Path) -> list[int]:
    with Image.open(path) as image:
        return [image.width, image.height]
