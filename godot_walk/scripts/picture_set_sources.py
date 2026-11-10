"""Direct, overwrite-safe image import for picture-set source evidence."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from video_source_library import (
    PICTURE_SET_SOURCE_KIND,
    SourceLibraryError,
    picture_set_sha256,
    sha256_file,
)

IMPORT_OPERATION = "direct_source_picture_import_no_resize_or_edit"
IMPORT_MANIFEST_NAME = "import_manifest.json"
IMPORTER = "direct_file_copy_no_resize_or_edit"


def import_source_images(
    images: list[dict[str, Any]],
    source_path: str,
    output: Path,
    root: Path,
) -> Path:
    """Copy each direct source image byte-for-byte and write an import receipt."""
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Refusing to overwrite image import: {output}")
    output.mkdir(parents=True)
    imported = [_import_one(image, source_path, output, root) for image in images]
    manifest = {
        "schema_version": 1,
        "source_kind": PICTURE_SET_SOURCE_KIND,
        "source_path": source_path,
        "source_image_set_sha256": picture_set_sha256(images),
        "importer": IMPORTER,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "images": imported,
    }
    path = output / IMPORT_MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _import_one(
    image: dict[str, Any], source_path: str, output: Path, root: Path
) -> dict[str, Any]:
    source = root / image["path"]
    if not source.is_file() or source.is_symlink():
        raise SourceLibraryError(f"Picture is missing or unsafe: {image['path']}")
    if not image["path"].startswith(f"{source_path}/"):
        raise SourceLibraryError("Picture entry is outside its registered set")
    if sha256_file(source) != image["sha256"]:
        raise SourceLibraryError(f"Picture changed before import: {image['path']}")
    _verify_dimensions(source, image)
    destination = output / f"{image['image_id']}{source.suffix.lower()}"
    shutil.copyfile(source, destination)
    if sha256_file(destination) != image["sha256"]:
        raise SourceLibraryError(f"Imported picture changed: {image['path']}")
    return {
        "image_id": image["image_id"],
        "capture_index": image["capture_index"],
        "source_path": image["path"],
        "source_sha256": image["sha256"],
        "width": image["width"],
        "height": image["height"],
        "path": destination.relative_to(root).as_posix(),
        "sha256": sha256_file(destination),
        "import_operation": IMPORT_OPERATION,
    }


def _verify_dimensions(path: Path, image: dict[str, Any]) -> None:
    with Image.open(path) as handle:
        if handle.size != (image["width"], image["height"]):
            raise SourceLibraryError(f"Picture dimensions changed: {image['path']}")


def verify_imported_image(
    image: dict[str, Any], source: dict[str, Any], root: Path
) -> None:
    """Check one import record against the exact source image it claims."""
    path = root / image["path"]
    if (
        not path.is_file()
        or path.is_symlink()
        or sha256_file(path) != image["sha256"]
    ):
        raise SourceLibraryError("Imported picture is missing or changed")
    if image["sha256"] != source["sha256"]:
        raise SourceLibraryError("Imported picture does not match its source image")
    if (image["width"], image["height"]) != (source["width"], source["height"]):
        raise SourceLibraryError("Imported picture dimensions changed")
    _verify_dimensions(path, source)
