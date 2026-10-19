"""Hash and verify the immutable inputs for a design round."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "godot_walk"
EVIDENCE = PROJECT / "evidence"

ROUND5_PROTECTED_INPUTS = (
    "godot_walk/assets/corridor_splat/corridor_clean.ply",
    "godot_walk/assets/corridor_splat/corridor_clean.report.json",
    "godot_walk/assets/corridor_splat/collision/corridor_splat.collision.glb",
    "godot_walk/assets/corridor_splat/alignment_manifest.json",
    "godot_walk/scenes/corridor_psx.tscn",
    "godot_walk/scenes/corridor_psx_room_v2.tscn",
    "godot_walk/scripts/psx_patch_room_extension_v2.gd",
    "godot_walk/scripts/verify_bounded_psx.gd",
    "godot_walk/scripts/measure_bounded_fps.gd",
    "godot_walk/scripts/capture_psx_design_review.gd",
    "godot_walk/scripts/psx_design_review_report.py",
    "godot_walk/scripts/psx_design_review_execution.py",
    "godot_walk/scripts/psx_design_variant_driver.gd",
    "godot_walk/scripts/psx_design_variant_catalog.gd",
    "godot_walk/design_variants/source_floor_single_column.json",
    "godot_walk/design_variants/source_floor_ceiling_single_column.json",
    "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_source_video.png",
)
ROUND5_SPECIFIC_INPUTS = frozenset({
    "godot_walk/design_variants/source_floor_single_column.json",
    "godot_walk/design_variants/source_floor_ceiling_single_column.json",
    "godot_walk/assets/psx_extension/textures/ceiling_source_video.png",
    "godot_walk/assets/psx_extension/textures/floor_source_video.png",
    "godot_walk/assets/psx_extension/textures/column_source_video.png",
})
BASE_PROTECTED_INPUTS = tuple(
    path for path in ROUND5_PROTECTED_INPUTS if path not in ROUND5_SPECIFIC_INPUTS
)


def collect_protected_paths(spec: dict[str, Any], out_dir: Path,
                            root: Path = ROOT,
                            base_inputs: tuple[str, ...] = BASE_PROTECTED_INPUTS) -> set[Path]:
    """Collect fixed inputs, referenced variants, round sources, and prior evidence."""
    project = root / "godot_walk"
    paths = {_resolve_existing(root, token) for token in base_inputs}
    manifests = _completed_manifests(project / "evidence")
    variant_ids = set(spec["variants"])
    for manifest_path, manifest in manifests:
        variant_ids.update(manifest.get("variants", []))
        for token in manifest.get("source_sha256", {}):
            paths.add(_resolve_manifest_path(root, token))
        paths.update(_evidence_files(manifest_path.parent))
    for variant_id in variant_ids:
        variant = project / "design_variants" / f"{variant_id}.json"
        if not variant.is_file():
            raise FileNotFoundError(f"completed round references missing variant: {variant}")
        paths.add(variant)
    paths.update(_spec_inputs(spec, root))
    spec_file = project / "design_rounds" / f"round-{spec['round_number']}.json"
    if spec_file.is_file():
        paths.add(spec_file)
    schema_file = project / "design_rounds" / "round.schema.json"
    if schema_file.is_file():
        paths.add(schema_file)
    for evidence_dir in (project / "evidence").glob("*psx-design*"):
        if evidence_dir.resolve() == out_dir.resolve():
            continue
        paths.update(_evidence_files(evidence_dir))
    return paths


def snapshot_protected_inputs(spec: dict[str, Any], out_dir: Path,
                              root: Path = ROOT,
                              base_inputs: tuple[str, ...] = BASE_PROTECTED_INPUTS) -> dict[str, Any]:
    paths = collect_protected_paths(spec, out_dir, root, base_inputs)
    return {
        "sha256": _hash_paths(paths, root),
        "git_diff_sha256": _git_diff_digest(paths, root),
        "file_count": len(paths),
    }


def verify_protected_inputs(spec: dict[str, Any], out_dir: Path,
                            before: dict[str, Any], root: Path = ROOT) -> dict[str, Any]:
    after = snapshot_protected_inputs(spec, out_dir, root)
    before_files = before["sha256"]
    after_files = after["sha256"]
    changed = sorted(path for path, digest in before_files.items()
                     if after_files.get(path) != digest)
    added = sorted(set(after_files) - set(before_files))
    removed = sorted(set(before_files) - set(after_files))
    result = {
        "unchanged": not (changed or added or removed)
        and before["git_diff_sha256"] == after["git_diff_sha256"],
        "changed": changed,
        "added": added,
        "removed": removed,
        "git_diff_unchanged": before["git_diff_sha256"] == after["git_diff_sha256"],
        "start_file_count": before["file_count"],
        "end_file_count": after["file_count"],
    }
    return result


def _completed_manifests(evidence_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    manifests = []
    for evidence_dir in sorted(evidence_root.glob("*psx-design*")):
        for manifest_path in evidence_dir.rglob("review_manifest.json"):
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("variants"):
                manifests.append((manifest_path, manifest))
    return manifests


def _evidence_files(directory: Path) -> set[Path]:
    return {path.resolve() for path in directory.rglob("*") if path.is_file()}


def _resolve_existing(root: Path, token: str) -> Path:
    path = (root / token).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"protected input does not exist: {path}")
    return path


def _resolve_manifest_path(root: Path, token: str) -> Path:
    candidates = [(root / token).resolve(), (root / "godot_walk" / token).resolve()]
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        raise FileNotFoundError(f"previous manifest references missing protected input: {token}")
    return path


def _spec_inputs(spec: dict[str, Any], root: Path) -> set[Path]:
    tokens = list(spec.get("additional_inputs", []))
    tokens.extend(value for value in (spec.get("video"), spec.get("source_frame")) if value)
    return {_resolve_existing(root, token) for token in tokens}


def _hash_paths(paths: set[Path], root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


def _git_diff_digest(paths: set[Path], root: Path) -> str:
    pathspecs = _git_pathspecs(paths, root)
    if not pathspecs:
        return hashlib.sha256(b"").hexdigest()
    parts = []
    for cached in (False, True):
        command = ["git", "diff", "--no-ext-diff", "--binary"]
        if cached:
            command.append("--cached")
        command.extend(["--", *pathspecs])
        result = subprocess.run(command, cwd=root, capture_output=True, check=True)
        parts.append(result.stdout)
    return hashlib.sha256(b"\0".join(parts)).hexdigest()


def _git_pathspecs(paths: set[Path], root: Path) -> list[str]:
    pathspecs = set()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if relative.startswith("godot_walk/evidence/"):
            relative = "/".join(relative.split("/")[:3])
        pathspecs.add(relative)
    return sorted(pathspecs)
