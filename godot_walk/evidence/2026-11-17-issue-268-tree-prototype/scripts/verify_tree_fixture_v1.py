"""Read-only integrity checks for the issue-268 isolated one-tree fixture.

Verifies that source/crop hashes and references resolve, that the canopy card
record has distinct orientations and depth offsets, that the matched-view record
is complete, and that every recorded flag stays false. It performs no rendering,
makes no model calls, edits nothing and admits nothing to the catalog.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
EVIDENCE_DIR = SCRIPT_DIR.parent
FIXTURE_DIR = EVIDENCE_DIR / "fixture"
ROOT = EVIDENCE_DIR.parents[2]

REQUIRED_VIEWS = ("front", "side", "oblique", "close", "elevated")
REQUIRED_CROPS = ("branch_canopy", "branch_fine", "evergreen_foliage")
FALSE_FLAGS = ("registration_accepted", "scale_calibrated", "operator_approved")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _repo_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path escapes repository: {relative}")
    return path


def collect_errors(fixture_dir: Path = FIXTURE_DIR, root: Path = ROOT) -> list[str]:
    """Return all integrity errors; an empty list means the fixture is consistent."""
    errors: list[str] = []
    try:
        provenance = _load(fixture_dir / "crop_provenance_v1.json")
        cards = _load(fixture_dir / "card_specs_v1.json")
        views = _load(fixture_dir / "views_v1.json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return [f"Cannot read fixture record: {error}"]

    errors.extend(_check_source(provenance, root))
    errors.extend(_check_crops(provenance, root))
    errors.extend(_check_cards(cards, provenance))
    errors.extend(_check_views(views))
    errors.extend(_check_flags(provenance, views))
    errors.extend(_check_notes(fixture_dir))
    return errors


def _check_source(provenance: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    source = provenance.get("source", {})
    for key in ("source_video", "frame_manifest", "source_frame_id"):
        if not source.get(key):
            errors.append(f"source.{key} is missing")
    if errors:
        return errors
    try:
        video = _repo_file(source["source_video"])
        manifest = _repo_file(source["frame_manifest"])
    except ValueError as error:
        return [str(error)]
    if not video.is_file():
        return [f"Source video does not resolve: {source['source_video']}"]
    actual_video = sha256_file(video)
    if actual_video != source.get("source_video_sha256"):
        errors.append(f"Source video hash mismatch: {actual_video}")
    if not manifest.is_file():
        return errors + [f"Frame manifest does not resolve: {source['frame_manifest']}"]
    actual_manifest = sha256_file(manifest)
    if actual_manifest != source.get("frame_manifest_sha256"):
        errors.append(f"Frame manifest hash mismatch: {actual_manifest}")
    frames = _load(manifest).get("frames", [])
    frame = next(
        (item for item in frames if item["frame_id"] == source["source_frame_id"]), None
    )
    if frame is None:
        errors.append(
            f"Source frame {source['source_frame_id']} is not in the frame manifest"
        )
        return errors
    frame_path = _repo_file(frame["path"])
    if not frame_path.is_file():
        errors.append(f"Source frame does not resolve: {frame['path']}")
    elif sha256_file(frame_path) != source.get("source_frame_sha256"):
        errors.append(f"Source frame hash mismatch: {frame['path']}")
    return errors


def _check_crops(provenance: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    crops = provenance.get("crops", [])
    names = [crop.get("name") for crop in crops]
    for expected in REQUIRED_CROPS:
        if expected not in names:
            errors.append(f"Crop {expected} is missing from the provenance record")
    origin_manifest = provenance.get("origin_crop_manifest", {}).get("path", "")
    try:
        origin = _load(_repo_file(origin_manifest))
    except (OSError, ValueError, json.JSONDecodeError):
        return errors + [f"Origin crop manifest does not resolve: {origin_manifest}"]
    origin_by_name = {crop["name"]: crop for crop in origin.get("crops", [])}
    for crop in crops:
        name = crop.get("name", "<unnamed>")
        previous = origin_by_name.get(name)
        if previous is None:
            errors.append(f"Crop {name} has no record in the origin crop manifest")
            continue
        if crop.get("source_pixel_bounds_xyxy") != previous.get(
            "source_pixel_bounds_xyxy"
        ):
            errors.append(f"Crop {name} bounds differ from the origin crop manifest")
        if crop.get("sha256") != previous.get("sha256"):
            errors.append(f"Crop {name} hash differs from the origin crop manifest")
        if crop.get("dimensions") != previous.get("dimensions"):
            errors.append(
                f"Crop {name} dimensions differ from the origin crop manifest"
            )
        for hash_key, path_key in (
            ("sha256", "origin_path"),
            ("fixture_sha256", "fixture_path"),
        ):
            try:
                path = _repo_file(crop[path_key])
            except (KeyError, ValueError) as error:
                errors.append(f"Crop {name} {path_key} is invalid: {error}")
                continue
            if not path.is_file():
                errors.append(f"Crop {name} {path_key} does not resolve: {path}")
            elif sha256_file(path) != crop.get(hash_key):
                errors.append(f"Crop {name} {hash_key} does not match its file")
    assessment = provenance.get("bark_crop_assessment", {})
    if assessment.get("result") != "no_appropriate_bark_crop_found":
        errors.append(
            "Bark crop assessment must record that no appropriate bark crop was found"
        )
    if not assessment.get("frames_inspected"):
        errors.append("Bark crop assessment must list the inspected frames")
    return errors


def _check_cards(cards: dict[str, Any], provenance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = cards.get("cards", [])
    if len(entries) < 6:
        errors.append(f"Canopy needs at least six layered cards; found {len(entries)}")
    crop_names = {crop["name"] for crop in provenance.get("crops", [])}
    azimuths: list[float] = []
    radials: list[float] = []
    heights: list[float] = []
    used: set[str] = set()
    for card in entries:
        crop = card.get("crop")
        if crop not in crop_names:
            errors.append(f"Canopy card {card.get('id')} uses unresolved crop {crop}")
        used.add(crop)
        for key in ("azimuth_deg", "radial_offset", "center_y", "size_x", "size_y"):
            if not isinstance(card.get(key), (int, float)):
                errors.append(f"Canopy card {card.get('id')} has invalid {key}")
        azimuths.append(float(card.get("azimuth_deg", 0)))
        radials.append(float(card.get("radial_offset", 0)))
        heights.append(float(card.get("center_y", 0)))
    for label, values in (
        ("azimuth", azimuths),
        ("radial_offset", radials),
        ("center_y", heights),
    ):
        if len(set(values)) != len(values):
            errors.append(f"Canopy card {label} values are not distinct")
    for expected in REQUIRED_CROPS:
        if expected not in used:
            errors.append(f"Crop {expected} is not used by any canopy card")
    return errors


def _check_views(views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    entries = views.get("views", [])
    ids = [view.get("id") for view in entries]
    for required in REQUIRED_VIEWS:
        if required not in ids:
            errors.append(f"Required matched view is missing: {required}")
    for view in entries:
        for key in ("position", "target"):
            value = view.get(key)
            if (
                not isinstance(value, list)
                or len(value) != 3
                or not all(isinstance(number, (int, float)) for number in value)
            ):
                errors.append(f"View {view.get('id')} has an invalid {key}")
    return errors


def _check_flags(provenance: dict[str, Any], views: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    records = (
        (
            "provenance.authored_vs_source.flags",
            provenance.get("authored_vs_source", {}).get("flags", {}),
        ),
        ("views.flags", views.get("flags", {})),
    )
    for label, flags in records:
        for flag in FALSE_FLAGS:
            if flags.get(flag) is not False:
                errors.append(f"{label}.{flag} must be false")
    if (
        provenance.get("authored_vs_source", {}).get("status")
        != "candidate_pending_review"
    ):
        errors.append("Fixture status must be candidate_pending_review")
    return errors


def _check_notes(fixture_dir: Path) -> list[str]:
    errors: list[str] = []
    authored = fixture_dir / "authored_vs_source_v1.md"
    limits = fixture_dir / "limitations_v1.md"
    if (
        not authored.is_file()
        or "authored" not in authored.read_text(encoding="utf-8").lower()
    ):
        errors.append("Authored-versus-source notes are missing or incomplete")
    if not limits.is_file():
        errors.append("Limitations notes are missing")
    else:
        text = limits.read_text(encoding="utf-8").lower()
        for keyword in ("silhouette", "crop edges", "repetition", "collision"):
            if keyword not in text:
                errors.append(f"Limitations notes do not record {keyword}")
    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("FAIL issue-268 tree fixture")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASS issue-268 tree fixture: source/crop hashes, card transforms, views and flags verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
