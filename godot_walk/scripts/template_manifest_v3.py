"""Build source-manifest v2/v3 successors without rewriting frozen records.

The v3 manifest is the template-level source snapshot from
``docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md`` section 4.1. A v1 source needs a
v2 bridge so the existing append-only manifest chain can reach v3 one version
at a time; the old v1 record stays byte-identical.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import template_validate as tv
from deterministic_json import canonical_bytes, plan_write, write_new
from video_source_library import manifest_video_content, utc_now

MANIFEST_SCHEMA_VERSION = 3
CAPTURE_BLOCK = {
    "camera_model": None,
    "lens": None,
    "intrinsics": {"fx": None, "fy": None, "cx": None, "cy": None},
    "distortion": None,
    "capture_height_m": None,
    "orientation": None,
}
SCALE_BLOCK = {
    "status": "uncalibrated",
    "method": None,
    "anchor": None,
    "confidence": 0.0,
    "evidence": [],
}
LIGHTING_BLOCK = {
    "status": "unknown",
    "color_temp_k": None,
    "illuminance_lux": None,
    "fixtures": [],
    "confidence": 0.0,
    "evidence": [],
}
AUDIO_BLOCK = {"present": False, "path": None, "sha256": None}
VERSIONED_MANIFEST_PATTERN = re.compile(r"^source_manifest-v([2-9]|[1-9][0-9]+)\.json$")


class ManifestUpgradeError(ValueError):
    """A source manifest cannot become a template v3 snapshot."""


def manifest_version(relative_path: str) -> int:
    """Return the manifest chain version encoded in a source-manifest path."""
    name = Path(relative_path).name
    if name == "source_manifest.json":
        return 1
    match = VERSIONED_MANIFEST_PATTERN.fullmatch(name)
    if match is None:
        raise ManifestUpgradeError(f"Unsupported source manifest path: {relative_path}")
    return int(match.group(1))


def build_v2(
    manifest: dict[str, Any], parent_path: str, parent_hash: str
) -> dict[str, Any]:
    """Return a no-op v2 successor that keeps the v1 record untouched."""
    if manifest.get("schema_version") != 1:
        raise ManifestUpgradeError("A v2 bridge requires a schema-v1 predecessor")
    successor = dict(manifest)
    successor.update(
        {
            "schema_version": 2,
            "manifest_version": 2,
            "supersedes": {"path": parent_path, "sha256": parent_hash},
            "recorded_at_utc": utc_now(),
        }
    )
    return successor


def build_v3(
    manifest: dict[str, Any],
    parent_path: str,
    parent_hash: str,
    version: int,
) -> dict[str, Any]:
    """Return a schema-v3 snapshot with the template blocks added."""
    if manifest.get("schema_version") not in (1, 2):
        raise ManifestUpgradeError("A v3 snapshot requires a v1 or v2 predecessor")
    video = _video_identity(manifest)
    successor = {
        key: value for key, value in manifest.items() if key != "canonical_video"
    }
    successor.update(
        {
            "schema_version": 3,
            "manifest_version": version,
            "source_kind": "video",
            "content": {
                "video": video,
                "picture_set": None,
                "audio": copy.deepcopy(AUDIO_BLOCK),
            },
            "capture": copy.deepcopy(CAPTURE_BLOCK),
            "scale": copy.deepcopy(SCALE_BLOCK),
            "lighting": copy.deepcopy(LIGHTING_BLOCK),
            "supersedes": {"path": parent_path, "sha256": parent_hash},
            "recorded_at_utc": utc_now(),
        }
    )
    successor.setdefault("registration_accepted", False)
    successor.setdefault("scale_calibrated", False)
    return successor


def _video_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    video = manifest_video_content(manifest)
    path, digest, metadata = (
        video.get("path"),
        video.get("sha256"),
        video.get("metadata"),
    )
    if (
        not isinstance(path, str)
        or not isinstance(digest, str)
        or not isinstance(metadata, dict)
    ):
        raise ManifestUpgradeError("Source manifest has an incomplete video identity")
    return {
        "path": path,
        "sha256": digest,
        "metadata": {
            key: metadata.get(key)
            for key in ("width", "height", "fps", "frame_count", "duration_seconds")
        },
    }


def write_successor(path: Path, record: dict[str, Any]) -> str:
    """Create a successor file, or accept an identical existing file."""
    data = canonical_bytes(record)
    status = plan_write(path, data)
    if status == "create":
        write_new(path, data)
    return status


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ManifestUpgradeError(
            f"Cannot read source manifest {path}: {error}"
        ) from error
    if not isinstance(record, dict):
        raise ManifestUpgradeError(f"Source manifest is not an object: {path}")
    return record


def verify_v3(
    manifest: dict[str, Any],
    video: dict[str, Any],
    source_id: str,
    parent_path: str,
    parent_hash: str,
    root: Path,
) -> None:
    """Check a v3 successor against its parent and the registered video."""
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or manifest.get("source_kind") != "video"
        or manifest.get("source_id") != source_id
    ):
        raise ManifestUpgradeError("Template v3 manifest identity is invalid")
    content = manifest.get("content")
    if not isinstance(content, dict) or content.get("picture_set") is not None:
        raise ManifestUpgradeError("Template v3 manifest has no video content")
    current = content.get("video")
    if not isinstance(current, dict):
        raise ManifestUpgradeError("Template v3 manifest has no video block")
    for key in ("path", "sha256", "metadata"):
        if current.get(key) != video.get(key):
            raise ManifestUpgradeError(
                f"Template v3 video {key} differs from the registered source"
            )
    if manifest.get("supersedes") != {"path": parent_path, "sha256": parent_hash}:
        raise ManifestUpgradeError("Template v3 manifest has the wrong predecessor")
    errors = tv.source_manifest_errors(manifest, root)
    if errors:
        raise ManifestUpgradeError("; ".join(errors))
