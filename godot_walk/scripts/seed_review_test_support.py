"""Shared fixtures for seed-review tests; no model or GPU access."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from seed_review_paths import ROOT


def build_fake_repo(root: Path) -> tuple[dict[str, Any], Path]:
    source_workflow = ROOT / "godot_walk/seed_review"
    target_workflow = root / "godot_walk/seed_review"
    target_workflow.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_workflow, target_workflow)
    video_dir = root / "data/videos"
    video_dir.mkdir(parents=True)
    video = video_dir / "sample.mp4"
    video.write_bytes(b"seed-review-source-video-bytes")
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    source_id = f"video-{digest[:16]}"
    frame_dir = (
        root
        / "godot_walk/source_library/sources"
        / source_id
        / "frames"
        / "seed-review"
    )
    frame_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "source_id": source_id,
        "created_at_utc": "2026-11-02T00:00:00+00:00",
        "canonical_video": {
            "path": "data/videos/sample.mp4",
            "sha256": digest,
            "metadata": {
                "width": 64,
                "height": 64,
                "fps": 10.0,
                "frame_count": 40,
                "duration_seconds": 4.0,
            },
        },
        "registration_accepted": False,
        "scale_calibrated": False,
        "source_review": {"status": "pending_operator_review", "decision": None},
        "frame_references": [],
        "hunyuan": {"status": "not_attempted", "attempts": []},
        "room_adaptations": [],
        "historical_artifacts": [],
    }
    manifest_path = (
        root / "godot_walk/source_library/sources" / source_id / "source_manifest.json"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    index = {
        "schema_version": 1,
        "index_version": 1,
        "sources": [
            {
                "source_id": source_id,
                "source_path": "data/videos/sample.mp4",
                "source_sha256": digest,
                "manifest_path": (
                    "godot_walk/source_library/sources/"
                    f"{source_id}/source_manifest.json"
                ),
                "manifest_sha256": manifest_sha,
            }
        ],
    }
    (root / "godot_walk/source_library/index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return manifest, frame_dir


def make_candidate(
    root: Path,
    frame_dir: Path,
    index: int,
    *,
    seed: int | None = None,
    image: np.ndarray | None = None,
) -> dict[str, Any]:
    if image is None:
        generator = np.random.default_rng(index if seed is None else seed)
        image = generator.integers(0, 256, (64, 64, 3), dtype=np.uint8)
    path = frame_dir / f"frame_{index:04d}.png"
    Image.fromarray(image, mode="RGB").save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "frame_id": f"frame_{index:04d}",
        "index_zero_based": index,
        "pts_seconds": index / 10.0,
        "path": path.relative_to(root).as_posix(),
        "sha256": digest,
        "width": 64,
        "height": 64,
        "origin": "direct_source_frame",
        "decode_operation": "direct_source_video_decode_no_resize_or_edit",
    }


def request_document(
    source_id: str, source_sha256: str, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "workflow_spec_version": "1.0.0",
        "source_id": source_id,
        "source_video_sha256": source_sha256,
        "candidates": candidates,
    }


def response_document(
    selected: str | None,
    alternatives: list[str],
    confidence: int = 4,
) -> dict[str, Any]:
    return {
        "selected_frame_id": selected,
        "ranked_alternatives": alternatives,
        "evidence": "Synthetic test evidence.",
        "uncertainty": "Synthetic test uncertainty.",
        "confidence_1_to_5": confidence,
        "use_original_frame_not_a_composite": True,
    }


def write_json(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path
