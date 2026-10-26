"""Explicit, overwrite-safe extraction stages for direct source-video evidence."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from video_adaptation_paths import resolve_repo_path
from video_adaptation_validation import (
    ROOT,
    AdaptationValidationError,
    repo_file,
    sha256_file,
)


def _safe_output_dir(relative_path: str) -> Path:
    path = resolve_repo_path(relative_path, ROOT)
    if path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing extraction output: {relative_path}"
        )
    return path


def _video_metadata(video: Path) -> dict[str, Any]:
    payload = json.loads(_probe_video(video))
    stream = next(
        item for item in payload["streams"] if item.get("codec_type") == "video"
    )
    numerator, denominator = map(int, stream["r_frame_rate"].split("/"))
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": numerator / denominator,
        "frame_count": int(stream["nb_frames"]),
        "duration_seconds": float(payload["format"]["duration"]),
    }


def _probe_video(video: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def extract_source_frames(
    video_relative: str, indices: list[int], output_relative: str
) -> Path:
    video = repo_file(video_relative)
    metadata = _video_metadata(video)
    selected = sorted(set(indices))
    if not selected or selected[0] < 0 or selected[-1] >= metadata["frame_count"]:
        raise ValueError("Frame indices must be unique valid zero-based source indices")
    output = _safe_output_dir(output_relative)
    output.mkdir(parents=True)
    frames = [
        _decode_source_frame(video, index, output, metadata) for index in selected
    ]
    manifest = {
        "schema_version": 1,
        "source_video": video_relative,
        "source_video_sha256": sha256_file(video),
        "metadata": metadata,
        "decoder": "ffmpeg select by decoded zero-based frame index",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "frames": frames,
    }
    manifest_path = output / "extraction_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _decode_source_frame(
    video: Path, index: int, output: Path, metadata: dict[str, Any]
) -> dict[str, Any]:
    frame_number = index + 1
    destination = output / f"frame_{frame_number:04d}.png"
    subprocess.run(
        _ffmpeg_frame_command(video, destination, index), check=True, timeout=90
    )
    _verify_frame_dimensions(destination, index, metadata)
    return {
        "frame_id": f"frame_{frame_number:04d}",
        "index_zero_based": index,
        "timestamp_seconds": index / metadata["fps"],
        "path": destination.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(destination),
        "decode_operation": "direct_source_video_decode_no_resize_or_edit",
    }


def _ffmpeg_frame_command(video: Path, destination: Path, index: int) -> list[str]:
    return [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(video),
        "-vf",
        f"select=eq(n\\,{index})",
        "-frames:v",
        "1",
        "-vsync",
        "0",
        str(destination),
    ]


def _verify_frame_dimensions(
    destination: Path, index: int, metadata: dict[str, Any]
) -> None:
    with Image.open(destination) as image:
        if image.size != (metadata["width"], metadata["height"]):
            raise ValueError(
                f"Decoded frame dimensions changed at source index {index}"
            )


def extract_source_crops(
    manifest_relative: str, plan_relative: str, output_relative: str
) -> Path:
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
        "schema_version": 1,
        "frame_manifest": manifest_relative,
        "frame_manifest_sha256": sha256_file(manifest_path),
        "operation": "direct_rectangular_crop_no_resize_or_color_edit",
        "crops": crops,
    }
    destination = output / "crop_manifest.json"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return destination


def _extract_one_crop(
    crop: dict[str, Any],
    frames: dict[str, dict[str, Any]],
    output: Path,
    results: list[dict[str, Any]],
) -> None:
    frame = frames.get(crop["frame_id"])
    if frame is None:
        raise AdaptationValidationError(f"Missing source frame: {crop['frame_id']}")
    name = crop["name"]
    if re.fullmatch(r"[a-z0-9_]+", name) is None:
        raise ValueError(f"Unsafe crop name: {name}")
    bounds = crop["source_pixel_bounds_xyxy"]
    destination = _crop_frame(frame, name, bounds, output)
    results.append(
        {
            "name": name,
            "frame_id": crop["frame_id"],
            "source_pixel_bounds_xyxy": bounds,
            "path": destination.relative_to(ROOT).as_posix(),
            "dimensions": _image_dimensions(destination),
            "sha256": sha256_file(destination),
        }
    )


def _crop_frame(
    frame: dict[str, Any], name: str, bounds: list[int], output: Path
) -> Path:
    source_path = repo_file(frame["path"])
    if sha256_file(source_path) != frame["sha256"]:
        raise AdaptationValidationError(
            f"Missing or changed source frame: {frame['frame_id']}"
        )
    with Image.open(source_path) as source:
        left, top, right, bottom = bounds
        if not (
            0 <= left < right <= source.width and 0 <= top < bottom <= source.height
        ):
            raise ValueError(f"Crop bounds exceed frame dimensions: {name}")
        destination = output / f"{name}.png"
        source.crop(tuple(bounds)).save(destination)
    return destination


def _image_dimensions(path: Path) -> list[int]:
    with Image.open(path) as image:
        return [image.width, image.height]
