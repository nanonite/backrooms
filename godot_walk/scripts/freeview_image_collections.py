"""Deterministic labelled image collections for consensus validation.

A collection is an exact, hashed list of image files with a ground-truth role:
`scene` images belong to the one place under test, `distractor` images do not.
Selection is a SHA-256 ordering with a fixed integer seed, so a collection is
reproducible without depending on a random-number implementation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, canonical_bytes, sha256_bytes, sha256_file
from PIL import Image, UnidentifiedImageError

COLLECTION_SCHEMA_VERSION = 1
TOOL_VERSION = "1.0.0"
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
SCENE_ROLE = "scene"
DISTRACTOR_ROLE = "distractor"
ROLES = (SCENE_ROLE, DISTRACTOR_ROLE)
DEFAULT_SEEDS = (2461, 2462, 2463)
DEFAULT_MIX_LEVELS = (0.10, 0.25, 0.50)
DEFAULT_ROOM_SAMPLE = 57
SCORE_DIGITS = 6


class CollectionError(ValueError):
    """A directory, manifest or mix level violates the collection contract."""


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    path: str
    sha256: str
    width: int
    height: int
    role: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "path": self.path,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "role": self.role,
        }


def scan_image_directory(
    directory: Path, role: str, root: Path = ROOT
) -> list[ImageRecord]:
    """Hash every supported image directly inside one directory."""
    if role not in ROLES:
        raise CollectionError(f"Unknown role: {role}")
    if not directory.is_dir():
        raise FileNotFoundError(f"Image directory does not exist: {directory}")
    paths = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not paths:
        raise CollectionError(f"No supported images in {directory}")
    records = []
    seen: dict[str, Path] = {}
    for path in paths:
        digest = sha256_file(path)
        if digest in seen:
            raise CollectionError(f"Duplicate image bytes: {path} and {seen[digest]}")
        seen[digest] = path
        width, height = _image_size(path)
        records.append(
            ImageRecord(
                image_id=f"{role}/{path.name}",
                path=_display_path(path, root),
                sha256=digest,
                width=width,
                height=height,
                role=role,
            )
        )
    return records


def verify_scene_manifest(
    manifest_path: Path, records: Sequence[ImageRecord], resolution: str
) -> dict[str, Any]:
    """Check one Mip-NeRF-style flat manifest entry list against the scan."""
    entries = _read_json(manifest_path, "scene manifest")
    if not isinstance(entries, list):
        raise CollectionError(f"Scene manifest must be a JSON list: {manifest_path}")
    expected = {}
    marker = f"/{resolution}/"
    for entry in entries:
        if not isinstance(entry, dict) or marker not in str(entry.get("path", "")):
            continue
        expected[Path(entry["path"]).name] = entry
    return _compare_manifest(manifest_path, records, expected, "path", "sha256")


def verify_picture_set_manifest(
    manifest_path: Path, records: Sequence[ImageRecord]
) -> dict[str, Any]:
    """Check the registered picture-set manifest against a distractor scan."""
    document = _read_json(manifest_path, "picture-set manifest")
    images = (document.get("content") or {}).get("picture_set")
    if not isinstance(images, list) or not images:
        raise CollectionError(f"Picture-set manifest has no images: {manifest_path}")
    expected = {Path(image["path"]).name: image for image in images}
    if len(expected) != len(images):
        raise CollectionError(
            f"Picture-set manifest has duplicate basenames: {manifest_path}"
        )
    return _compare_manifest(manifest_path, records, expected, "path", "sha256")


def build_collection_spec(
    scene_records: Sequence[ImageRecord],
    distractor_records: Sequence[ImageRecord],
    seeds: Sequence[int] = DEFAULT_SEEDS,
    mix_levels: Sequence[float] = DEFAULT_MIX_LEVELS,
    room_sample: int = DEFAULT_ROOM_SAMPLE,
    k_values: Sequence[int] = (3, 5, 8, 15, 30),
) -> dict[str, Any]:
    """Build clean, mixed, combined and distractor-only collections."""
    _validate_records(scene_records, SCENE_ROLE)
    _validate_records(distractor_records, DISTRACTOR_ROLE)
    _validate_parameters(seeds, mix_levels, room_sample)
    overlap = {record.sha256 for record in scene_records} & {
        record.sha256 for record in distractor_records
    }
    if overlap:
        raise CollectionError(
            f"{len(overlap)} image(s) appear in both roles; labels would conflict"
        )
    if len(scene_records) < room_sample:
        raise CollectionError(
            f"Room sample {room_sample} exceeds the {len(scene_records)} scene images"
        )
    _validate_distractor_capacity(distractor_records, room_sample, mix_levels)
    collections = [_all_scene_collection(scene_records)]
    for seed in seeds:
        collections.extend(
            _seeded_collections(
                scene_records, distractor_records, seed, mix_levels, room_sample
            )
        )
    collections.append(
        _collection("mixed-all", "mixed", None, None, scene_records, distractor_records)
    )
    collections.append(
        _collection(
            "distractor-only", "distractor_only", None, None, [], distractor_records
        )
    )
    return {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "tool": "freeview_image_collections",
        "tool_version": TOOL_VERSION,
        "issue": 246,
        "scene_role": SCENE_ROLE,
        "distractor_role": DISTRACTOR_ROLE,
        "seeds": [int(seed) for seed in seeds],
        "mix_levels": [float(level) for level in mix_levels],
        "room_sample_size": int(room_sample),
        "k_values": [int(k) for k in k_values],
        "scene_source": _source_summary(scene_records),
        "distractor_source": _source_summary(distractor_records),
        "collections": collections,
    }


def collection_images(collection: dict[str, Any]) -> list[dict[str, Any]]:
    """The validated image list of one collection, in canonical order."""
    images = collection.get("images")
    if not isinstance(images, list) or not images:
        raise CollectionError(f"Collection {collection.get('name')} has no images")
    return images


def roles_by_image(collection: dict[str, Any]) -> dict[str, str]:
    return {image["image_id"]: image["role"] for image in collection_images(collection)}


def resolve_collection_path(path_text: str, root: Path = ROOT) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def _seeded_collections(
    scene_records: Sequence[ImageRecord],
    distractor_records: Sequence[ImageRecord],
    seed: int,
    mix_levels: Sequence[float],
    room_sample: int,
) -> list[dict[str, Any]]:
    rooms = take_sample(scene_records, room_sample, seed)
    collections = [_collection(f"clean-seed-{seed}", "clean", seed, None, rooms, [])]
    ordered_distractors = take_sample(distractor_records, len(distractor_records), seed)
    for level in mix_levels:
        count = distractor_count(level, room_sample)
        collections.append(
            _collection(
                f"mixed-{_percent(level)}-seed-{seed}",
                "mixed",
                seed,
                level,
                rooms,
                ordered_distractors[:count],
            )
        )
    return collections


def distractor_count(fraction: float, scene_count: int) -> int:
    """Distractor images needed for ``fraction`` of the combined collection."""
    if not 0.0 < fraction < 1.0:
        raise CollectionError(
            f"Distractor fraction must be between 0 and 1: {fraction}"
        )
    return round(fraction * scene_count / (1.0 - fraction))


def take_sample(
    records: Sequence[ImageRecord], count: int, seed: int
) -> list[ImageRecord]:
    """Take the first ``count`` records under a seeded SHA-256 ordering."""
    if count < 1 or count > len(records):
        raise CollectionError(f"Cannot sample {count} of {len(records)} images")
    ordered = sorted(
        records, key=lambda record: (_selection_key(seed, record), record.image_id)
    )
    return ordered[:count]


def _selection_key(seed: int, record: ImageRecord) -> str:
    payload = f"{seed}|{record.role}|{record.image_id}".encode()
    return hashlib.sha256(payload).hexdigest()


def _collection(
    name: str,
    kind: str,
    seed: int | None,
    requested_fraction: float | None,
    scene_records: Sequence[ImageRecord],
    distractor_records: Sequence[ImageRecord],
) -> dict[str, Any]:
    images = sorted(
        [record.to_dict() for record in scene_records]
        + [record.to_dict() for record in distractor_records],
        key=lambda image: image["image_id"],
    )
    total = len(images)
    distractor_total = len(distractor_records)
    realized = round(distractor_total / total, SCORE_DIGITS) if total else 0.0
    return {
        "name": name,
        "kind": kind,
        "seed": seed,
        "requested_distractor_fraction": requested_fraction,
        "realized_distractor_fraction": realized,
        "scene_count": len(scene_records),
        "distractor_count": distractor_total,
        "collection_sha256": sha256_bytes(canonical_bytes(images)),
        "images": images,
    }


def _all_scene_collection(records: Sequence[ImageRecord]) -> dict[str, Any]:
    return _collection("clean-full", "clean", None, None, records, [])


def _validate_records(records: Sequence[ImageRecord], expected_role: str) -> None:
    if not records:
        raise CollectionError(f"No {expected_role} images supplied")
    ids = [record.image_id for record in records]
    if len(set(ids)) != len(ids):
        raise CollectionError(f"Duplicate {expected_role} image IDs")
    digests = [record.sha256 for record in records]
    if len(set(digests)) != len(digests):
        raise CollectionError(f"Duplicate {expected_role} image bytes")
    if any(record.role != expected_role for record in records):
        raise CollectionError(f"Every record must have role {expected_role}")


def _validate_distractor_capacity(
    distractor_records: Sequence[ImageRecord],
    room_sample: int,
    mix_levels: Sequence[float],
) -> None:
    for level in mix_levels:
        needed = distractor_count(level, room_sample)
        if needed > len(distractor_records):
            raise CollectionError(
                f"A {level:.0%} mix needs {needed} distractor images, "
                f"but only {len(distractor_records)} are available"
            )


def _validate_parameters(
    seeds: Sequence[int], mix_levels: Sequence[float], room_sample: int
) -> None:
    if not seeds:
        raise CollectionError("At least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise CollectionError("Seeds must be unique")
    if not mix_levels:
        raise CollectionError("At least one mix level is required")
    if len(set(mix_levels)) != len(mix_levels):
        raise CollectionError("Mix levels must be unique")
    if room_sample < 1:
        raise CollectionError("Room sample size must be positive")
    for level in mix_levels:
        distractor_count(level, room_sample)


def _compare_manifest(
    manifest_path: Path,
    records: Sequence[ImageRecord],
    expected: dict[str, dict[str, Any]],
    path_key: str,
    hash_key: str,
) -> dict[str, Any]:
    scanned = {Path(record.path).name: record for record in records}
    missing = sorted(set(expected) - set(scanned))
    extra = sorted(set(scanned) - set(expected))
    mismatched = sorted(
        name
        for name in set(expected) & set(scanned)
        if expected[name][hash_key] != scanned[name].sha256
    )
    if missing or extra or mismatched:
        raise CollectionError(
            f"{manifest_path} disagrees with the scan: "
            f"missing={missing[:5]} extra={extra[:5]} mismatched={mismatched[:5]}"
        )
    return {
        "path": manifest_path.as_posix(),
        "sha256": sha256_file(manifest_path),
        "matched_images": len(scanned),
        "hash_field": hash_key,
        "path_field": path_key,
    }


def _source_summary(records: Sequence[ImageRecord]) -> dict[str, Any]:
    return {
        "image_count": len(records),
        "directories": sorted({str(Path(record.path).parent) for record in records}),
    }


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _image_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as error:
        raise CollectionError(f"Cannot read image: {path}") from error
    if width < 1 or height < 1:
        raise CollectionError(f"Image has no pixels: {path}")
    return int(width), int(height)


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CollectionError(f"Cannot read {label}: {path}") from error


def _percent(fraction: float) -> str:
    return f"{round(fraction * 100)}"
