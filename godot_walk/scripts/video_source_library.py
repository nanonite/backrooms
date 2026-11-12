"""Safe registration and validation for the local source library.

The library holds direct video sources and picture sets. Video manifests keep
their v1/v2 shape; new picture-set manifests use source-manifest schema v3 and
never rewrite an older record.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = Path("godot_walk/source_library")
INDEX_PATH = LIBRARY / "index.json"
VIDEO_DIR = Path("data/videos")
PICTURE_DIR = Path("data/pictures")
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}
PICTURE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
VIDEO_SOURCE_KIND = "video"
PICTURE_SET_SOURCE_KIND = "picture_set"
SOURCE_KINDS = (VIDEO_SOURCE_KIND, PICTURE_SET_SOURCE_KIND)
SOURCE_ID_PATTERN = re.compile(r"^(video|picture-set)-[0-9a-f]{16}$")
VERSIONED_MANIFEST_PATTERN = re.compile(r"^source_manifest-v([2-9]|[1-9][0-9]+)\.json$")
PICTURE_SET_IDENTITY_FIELDS = (
    "image_id",
    "path",
    "sha256",
    "width",
    "height",
    "capture_index",
)


class SourceLibraryError(ValueError):
    """An intake source or library record violates the source contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_kind_for_id(source_id: str) -> str:
    if not isinstance(source_id, str):
        raise SourceLibraryError("Source ID is not safe")
    if source_id.startswith("picture-set-"):
        return PICTURE_SET_SOURCE_KIND
    if source_id.startswith("video-"):
        return VIDEO_SOURCE_KIND
    raise SourceLibraryError("Source ID is not safe")


def safe_source_id(digest: str, source_kind: str = VIDEO_SOURCE_KIND) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise SourceLibraryError("Source SHA-256 must contain 64 lowercase hex digits")
    if source_kind == PICTURE_SET_SOURCE_KIND:
        return f"picture-set-{digest[:16]}"
    if source_kind != VIDEO_SOURCE_KIND:
        raise SourceLibraryError(f"Unsupported source kind: {source_kind}")
    return f"video-{digest[:16]}"


def canonical_video_path(path: Path, root: Path = ROOT) -> tuple[Path, str]:
    repo = root.resolve()
    intake = repo / VIDEO_DIR
    if intake.is_symlink():
        raise SourceLibraryError(
            "The data/videos intake directory may not be a symlink"
        )
    if path.is_symlink():
        raise SourceLibraryError(f"Source video may not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    video_root = intake.resolve(strict=True)
    if not video_root.is_relative_to(repo):
        raise SourceLibraryError(
            "The data/videos intake directory escapes the repository"
        )
    if not resolved.is_relative_to(video_root) or resolved.parent != video_root:
        raise SourceLibraryError("Source videos must be direct files under data/videos")
    if not resolved.is_file() or resolved.suffix.lower() not in VIDEO_SUFFIXES:
        raise SourceLibraryError(f"Unsupported or non-file source: {path}")
    if not resolved.relative_to(repo).as_posix().startswith("data/videos/"):
        raise SourceLibraryError("Canonical source path is outside data/videos")
    return resolved, resolved.relative_to(repo).as_posix()


def canonical_picture_set_path(path: Path, root: Path = ROOT) -> tuple[Path, str]:
    repo = root.resolve()
    intake = repo / PICTURE_DIR
    if intake.is_symlink():
        raise SourceLibraryError(
            "The data/pictures intake directory may not be a symlink"
        )
    if not intake.is_dir():
        raise SourceLibraryError("Local intake directory data/pictures does not exist")
    if path.is_symlink():
        raise SourceLibraryError(f"Picture set may not be a symlink: {path}")
    resolved = path.resolve(strict=True)
    picture_root = intake.resolve(strict=True)
    if not picture_root.is_relative_to(repo):
        raise SourceLibraryError(
            "The data/pictures intake directory escapes the repository"
        )
    if not resolved.is_relative_to(picture_root) or resolved.parent != picture_root:
        raise SourceLibraryError(
            "Picture sets must be direct directories under data/pictures"
        )
    if not resolved.is_dir():
        raise SourceLibraryError(f"Unsupported or non-directory picture set: {path}")
    relative = resolved.relative_to(repo).as_posix()
    if not relative.startswith("data/pictures/"):
        raise SourceLibraryError("Canonical source path is outside data/pictures")
    return resolved, relative


def picture_set_images(directory: Path) -> list[Path]:
    """Return the direct, supported image files of one picture set in stable order."""
    images = [
        path
        for path in directory.iterdir()
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in PICTURE_SUFFIXES
    ]
    return sorted(images, key=lambda item: (item.name.casefold(), item.name))


def probe_picture(path: Path) -> dict[str, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            image.verify()
    except (OSError, ValueError) as error:
        raise SourceLibraryError(f"Cannot read picture: {path}") from error
    if width <= 0 or height <= 0:
        raise SourceLibraryError("Picture dimensions must be positive")
    return {"width": width, "height": height}


def probe_picture_set(picture_dir: Path, root: Path = ROOT) -> list[dict[str, Any]]:
    """Hash every image and read its dimensions; no image is copied or edited."""
    directory, relative = canonical_picture_set_path(picture_dir, root)
    files = picture_set_images(directory)
    if not files:
        raise SourceLibraryError(f"Picture set contains no supported images: {relative}")
    images = []
    for capture_index, path in enumerate(files, start=1):
        dimensions = probe_picture(path)
        images.append(
            {
                "image_id": f"img_{capture_index:04d}",
                "path": (Path(relative) / path.name).as_posix(),
                "sha256": sha256_file(path),
                "width": dimensions["width"],
                "height": dimensions["height"],
                "capture_index": capture_index,
                "captured_at_utc": None,
                "camera_pose": None,
            }
        )
    return images


def picture_set_sha256(images: list[dict[str, Any]]) -> str:
    """Hash the ordered, direct-source image identity of one picture set."""
    identity = [
        {field: image.get(field) for field in PICTURE_SET_IDENTITY_FIELDS}
        for image in images
    ]
    payload = json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def probe_video(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=45
    )
    return _metadata_from_probe(json.loads(result.stdout))


def _metadata_from_probe(probe: dict[str, Any]) -> dict[str, Any]:
    streams = probe.get("streams", [])
    if not streams:
        raise SourceLibraryError("ffprobe did not report a video stream")
    stream = streams[0]
    frame_rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    try:
        fps = float(Fraction(frame_rate))
        width, height = int(stream["width"]), int(stream["height"])
        duration = float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise SourceLibraryError(
            "ffprobe returned incomplete video metadata"
        ) from error
    if width <= 0 or height <= 0 or fps <= 0 or duration <= 0:
        raise SourceLibraryError(
            "Video dimensions, frame rate, and duration must be positive"
        )
    frame_count = stream.get("nb_frames")
    return {
        "width": width,
        "height": height,
        "fps": round(fps, 6),
        "frame_count": int(frame_count) if frame_count not in (None, "N/A") else None,
        "duration_seconds": round(duration, 6),
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceLibraryError(f"Cannot read JSON record: {path}") from error
    if not isinstance(value, dict):
        raise SourceLibraryError(f"Expected a JSON object: {path}")
    return value


def validate_index(root: Path = ROOT) -> list[dict[str, Any]]:
    index_path = root / INDEX_PATH
    _reject_symlink_path(index_path, root)
    index = _read_json(index_path)
    version = index.get("schema_version")
    if version not in (1, 2) or not isinstance(index.get("sources"), list):
        raise SourceLibraryError("Unsupported source-library index")
    for entry in index["sources"]:
        if version == 1 and isinstance(entry, dict) and str(
            entry.get("source_id", "")
        ).startswith("picture-set-"):
            raise SourceLibraryError("Picture-set sources require index schema 2")
    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()
    for entry in index["sources"]:
        _validate_index_entry(entry, seen_paths, seen_hashes, root)
    return index["sources"]


def _validate_index_entry(
    entry: dict[str, Any], seen_paths: set[str], seen_hashes: set[str], root: Path
) -> None:
    if not isinstance(entry, dict):
        raise SourceLibraryError("Index source entries must be JSON objects")
    source_id = entry.get("source_id")
    if not isinstance(source_id, str) or SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise SourceLibraryError("Index contains an unsafe source ID")
    source_kind = source_kind_for_id(source_id)
    if entry.get("source_kind", source_kind) != source_kind:
        raise SourceLibraryError(f"Malformed source index entry: {source_id}")
    source_path = entry.get("source_path")
    source_digest = entry.get("source_sha256")
    manifest_path_text = entry.get("manifest_path")
    manifest_path = _source_manifest_path(manifest_path_text, source_id, root)
    if (
        not _valid_source_path(source_path, source_kind)
        or not isinstance(source_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None
        or source_id != safe_source_id(source_digest, source_kind)
        or manifest_path is None
        or not isinstance(entry.get("manifest_sha256"), str)
        or re.fullmatch(r"[0-9a-f]{64}", entry["manifest_sha256"]) is None
    ):
        raise SourceLibraryError(f"Malformed source index entry: {source_id}")
    if source_path in seen_paths or source_digest in seen_hashes:
        raise SourceLibraryError("Duplicate source path or content hash in index")
    seen_paths.add(source_path)
    seen_hashes.add(source_digest)
    if sha256_file(manifest_path) != entry["manifest_sha256"]:
        raise SourceLibraryError(f"Source manifest changed: {source_id}")
    chain = _read_manifest_chain(manifest_path, source_id, root)
    if chain[0][1] != entry["manifest_sha256"]:
        raise SourceLibraryError(f"Source manifest changed: {source_id}")
    if chain[0][0].get("source_kind", VIDEO_SOURCE_KIND) != source_kind:
        raise SourceLibraryError(f"Manifest source kind mismatch: {source_id}")
    for ancestor, _digest, _path in chain:
        if ancestor.get("source_id") != source_id:
            raise SourceLibraryError(f"Source ID mismatch in manifest: {source_id}")
        _validate_manifest_source(
            ancestor, source_id, source_kind, source_path, source_digest, root
        )
        _validate_manifest_references(ancestor, root)


def _valid_source_path(source_path: Any, source_kind: str) -> bool:
    if not isinstance(source_path, str):
        return False
    if source_kind == VIDEO_SOURCE_KIND:
        return (
            source_path.startswith("data/videos/")
            and Path(source_path).name == source_path.removeprefix("data/videos/")
        )
    relative = PurePosixPath(source_path)
    return (
        source_path.startswith("data/pictures/")
        and len(relative.parts) == 3
        and relative.parts[0] == "data"
        and relative.parts[1] == "pictures"
        and relative.parts[2] not in {"", ".", ".."}
    )


def _validate_manifest_source(
    manifest: dict[str, Any],
    source_id: str,
    source_kind: str,
    source_path: str,
    source_digest: str,
    root: Path,
) -> None:
    manifest_kind, content_path, content_digest, pictures = _manifest_identity(manifest)
    if manifest_kind != source_kind:
        raise SourceLibraryError(f"Manifest source kind mismatch: {source_id}")
    if manifest_kind == VIDEO_SOURCE_KIND:
        video, canonical = canonical_video_path(root / source_path, root)
        if canonical != source_path or sha256_file(video) != source_digest:
            raise SourceLibraryError(
                f"Source video changed since registration: {source_id}"
            )
        if content_path != source_path or content_digest != source_digest:
            raise SourceLibraryError(f"Manifest source hash mismatch: {source_id}")
        return
    if content_digest != source_digest:
        raise SourceLibraryError(f"Manifest source hash mismatch: {source_id}")
    _validate_picture_set_content(pictures or [], source_path, source_digest, source_id, root)


def manifest_video_content(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical video block from a v1/v2 or v3 manifest.

    v1/v2 records store it as ``canonical_video``; schema v3 stores it as
    ``content.video``. Both shapes stay valid, so every consumer reads the
    identity through this one accessor.
    """
    if manifest.get("schema_version") == 3:
        content = manifest.get("content")
        video = content.get("video") if isinstance(content, dict) else None
    else:
        video = manifest.get("canonical_video")
    if not isinstance(video, dict):
        raise SourceLibraryError("Source manifest has no canonical video")
    return video


def _manifest_identity(
    manifest: dict[str, Any],
) -> tuple[str, str | None, str | None, list[dict[str, Any]] | None]:
    if manifest.get("schema_version") == 3:
        source_kind = manifest.get("source_kind")
        content = manifest.get("content")
        if not isinstance(content, dict):
            raise SourceLibraryError("Source manifest has no content block")
        if source_kind == PICTURE_SET_SOURCE_KIND:
            pictures = content.get("picture_set")
            if not isinstance(pictures, list) or not pictures:
                raise SourceLibraryError("Picture-set manifest has no images")
            if content.get("video") is not None:
                raise SourceLibraryError("Picture-set manifest also declares a video")
            return source_kind, None, picture_set_sha256(pictures), pictures
        if source_kind == VIDEO_SOURCE_KIND:
            video = content.get("video")
            if not isinstance(video, dict):
                raise SourceLibraryError("Video manifest has no video block")
            if content.get("picture_set") is not None:
                raise SourceLibraryError("Video manifest also declares a picture set")
            return source_kind, video.get("path"), video.get("sha256"), None
        raise SourceLibraryError("Unsupported source kind in manifest")
    canonical_video = manifest.get("canonical_video")
    if not isinstance(canonical_video, dict):
        raise SourceLibraryError("Source manifest has no canonical video")
    return (
        VIDEO_SOURCE_KIND,
        canonical_video.get("path"),
        canonical_video.get("sha256"),
        None,
    )


def _validate_picture_set_content(
    pictures: list[dict[str, Any]],
    source_path: str,
    source_digest: str,
    source_id: str,
    root: Path,
) -> None:
    if picture_set_sha256(pictures) != source_digest:
        raise SourceLibraryError(f"Picture-set hash mismatch: {source_id}")
    directory = root / source_path
    _reject_symlink_path(directory, root)
    if not directory.is_dir():
        raise SourceLibraryError(f"Picture set is missing: {source_path}")
    expected_paths = set()
    seen_indexes = set()
    for picture in pictures:
        path_text = picture.get("path")
        if not isinstance(path_text, str):
            raise SourceLibraryError(f"Picture entry has no path: {source_id}")
        relative = PurePosixPath(path_text)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in path_text.split("/"))
            or relative.parent.as_posix() != source_path
            or relative.name in {"", ".", ".."}
        ):
            raise SourceLibraryError(f"Picture path escapes its set: {path_text}")
        capture_index = picture.get("capture_index")
        if (
            not isinstance(capture_index, int)
            or isinstance(capture_index, bool)
            or capture_index < 1
            or capture_index in seen_indexes
        ):
            raise SourceLibraryError(f"Picture capture indexes are invalid: {source_id}")
        seen_indexes.add(capture_index)
        path = root.joinpath(*relative.parts)
        _reject_symlink_path(path, root)
        if not path.is_file() or sha256_file(path) != picture.get("sha256"):
            raise SourceLibraryError(f"Picture changed since registration: {path_text}")
        dimensions = probe_picture(path)
        if (dimensions["width"], dimensions["height"]) != (
            picture.get("width"),
            picture.get("height"),
        ):
            raise SourceLibraryError(f"Picture dimensions changed: {path_text}")
        expected_paths.add(path_text)
    actual_paths = {
        (Path(source_path) / path.name).as_posix()
        for path in picture_set_images(directory)
    }
    if actual_paths != expected_paths:
        raise SourceLibraryError(f"Picture set contents changed: {source_id}")


def _source_manifest_path(path_text: Any, source_id: str, root: Path) -> Path | None:
    if not isinstance(path_text, str):
        return None
    expected_dir = (LIBRARY / "sources" / source_id).as_posix()
    relative = PurePosixPath(path_text)
    if (
        relative.is_absolute()
        or any(part in {"", ".", ".."} for part in path_text.split("/"))
        or relative.parent.as_posix() != expected_dir
        or relative.name != "source_manifest.json"
        and VERSIONED_MANIFEST_PATTERN.fullmatch(relative.name) is None
    ):
        return None
    path = root.joinpath(*relative.parts)
    _reject_symlink_path(path, root)
    return path


def _read_manifest_chain(
    current_path: Path, source_id: str, root: Path
) -> list[tuple[dict[str, Any], str, Path]]:
    chain = []
    path = current_path
    expected_version = _manifest_version(path.name)
    while True:
        _reject_symlink_path(path, root)
        manifest = _read_json(path)
        digest = sha256_file(path)
        chain.append((manifest, digest, path))
        _validate_manifest_version(manifest, path.name, expected_version)
        if manifest.get("schema_version") == 3 and "supersedes" not in manifest:
            break
        if expected_version == 1:
            break
        path = _manifest_parent(manifest, source_id, expected_version, root)
        expected_version -= 1
    return chain


def _manifest_version(filename: str) -> int:
    if filename == "source_manifest.json":
        return 1
    match = VERSIONED_MANIFEST_PATTERN.fullmatch(filename)
    if match is None:
        raise SourceLibraryError(f"Unsupported source manifest filename: {filename}")
    return int(match.group(1))


def _validate_manifest_version(
    manifest: dict[str, Any], filename: str, expected_version: int
) -> None:
    if expected_version == 1:
        if filename != "source_manifest.json" or manifest.get("schema_version") != 1:
            raise SourceLibraryError("The original source manifest must remain v1")
        return
    schema_version = manifest.get("schema_version")
    if (
        filename != f"source_manifest-v{expected_version}.json"
        or schema_version not in (2, 3)
        or manifest.get("manifest_version") != expected_version
        or (schema_version == 3 and expected_version < 3)
    ):
        raise SourceLibraryError("Versioned source manifest identity is invalid")


def _manifest_parent(
    manifest: dict[str, Any], source_id: str, version: int, root: Path
) -> Path:
    previous_name = (
        "source_manifest.json"
        if version == 2
        else f"source_manifest-v{version - 1}.json"
    )
    expected_relative = (LIBRARY / "sources" / source_id / previous_name).as_posix()
    parent = manifest.get("supersedes")
    if not isinstance(parent, dict) or parent.get("path") != expected_relative:
        raise SourceLibraryError("Versioned source manifest has an invalid predecessor")
    parent_path = _source_manifest_path(expected_relative, source_id, root)
    if parent_path is None or not parent_path.is_file():
        raise SourceLibraryError("Versioned source manifest predecessor is missing")
    if sha256_file(parent_path) != parent.get("sha256"):
        raise SourceLibraryError("Versioned source manifest predecessor changed")
    return parent_path


def manifest_lineage_hashes(entry: dict[str, Any], root: Path = ROOT) -> set[str]:
    """Return hashes of the current manifest and its validated predecessors."""
    path = _source_manifest_path(entry.get("manifest_path"), entry["source_id"], root)
    if path is None:
        raise SourceLibraryError("Source index contains an unsafe manifest path")
    return {
        digest
        for _manifest, digest, _path in _read_manifest_chain(
            path, entry["source_id"], root
        )
    }


def _validate_manifest_references(manifest: dict[str, Any], root: Path) -> None:
    references = list(manifest.get("historical_artifacts", []))
    references.extend(manifest.get("frame_references", []))
    for room in manifest.get("room_adaptations", []):
        references.extend(_room_artifacts(room))
    for attempt in manifest.get("hunyuan", {}).get("historical_attempts", []):
        references.extend(attempt.get("evidence", []))
    for reference in references:
        _verify_artifact_reference(reference, root)


def _room_artifacts(room: dict[str, Any]) -> list[dict[str, Any]]:
    references = [
        {"path": room.get(path_key), "sha256": room.get(hash_key)}
        for path_key, hash_key in (
            ("adaptation_path", "adaptation_sha256"),
            ("decision_path", "decision_sha256"),
        )
    ]
    for path_key, hash_key in (
        ("scene_path", "scene_sha256"),
        ("catalog_snapshot_path", "catalog_snapshot_sha256"),
    ):
        if path_key in room or hash_key in room:
            references.append(
                {"path": room.get(path_key), "sha256": room.get(hash_key)}
            )
    return references


def _verify_artifact_reference(reference: dict[str, Any], root: Path) -> None:
    path_text, digest = reference.get("path"), reference.get("sha256")
    if not isinstance(path_text, str) or not isinstance(digest, str):
        raise SourceLibraryError("Artifact reference lacks a path or SHA-256")
    relative = PurePosixPath(path_text)
    if (
        relative.is_absolute()
        or PureWindowsPath(path_text).is_absolute()
        or any(part in {"", ".", ".."} for part in path_text.split("/"))
        or "\\" in path_text
    ):
        raise SourceLibraryError(f"Unsafe artifact reference: {path_text}")
    artifact = root.joinpath(*relative.parts)
    _reject_symlink_path(artifact, root)
    if not artifact.is_file() or sha256_file(artifact) != digest:
        raise SourceLibraryError(f"Missing or changed referenced artifact: {path_text}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def lock_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    stream = os.fdopen(descriptor, "a+b")
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    return stream


def _reject_symlink_path(path: Path, root: Path) -> None:
    repo = root.resolve()
    candidate = path.absolute()
    if not candidate.is_relative_to(repo):
        raise SourceLibraryError("Source-library path escapes the repository")
    current = repo
    for component in candidate.relative_to(repo).parts:
        current /= component
        if current.is_symlink():
            raise SourceLibraryError(f"Source-library path uses a symlink: {current}")


def write_new_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def write_new_jsonl_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        stream.write("\n")


Probe = Callable[[Path], dict[str, Any]]
