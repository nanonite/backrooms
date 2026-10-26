"""Validate catalog modules and fingerprint the full supported resource graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path, resolve_scene_reference
from video_adaptation_resource_graph import discover_resource_graph


def validate_required_scene_dependencies(
    record: dict[str, Any],
    catalog: dict[str, Any],
    root: Path = ROOT,
    dynamic_declarations: list[dict[str, Any]] | None = None,
    supplemental_dependencies: list[dict[str, str]] | None = None,
) -> None:
    resolved = record["resolved_adaptation"]
    declared = {item["path"] for item in resolved["dependencies"]}
    required_scenes = _required_scene_paths(record, catalog, root)
    discovered = discover_resource_graph(
        required_scenes, dynamic_declarations or [], root
    )
    supplemental = {item["path"] for item in (supplemental_dependencies or [])}
    missing = discovered - declared - supplemental
    if missing:
        raise AdaptationValidationError(
            f"Required runtime dependency is not fingerprinted: {min(missing)}"
        )
    stale = supplemental - (discovered - declared)
    if stale:
        raise AdaptationValidationError(
            f"Supplemental migration dependency is not referenced: {min(stale)}"
        )


def _required_scene_paths(
    record: dict[str, Any], catalog: dict[str, Any], root: Path
) -> list[str]:
    resolved = record["resolved_adaptation"]
    scenes = [_repo_scene_path(resolved["scene_path"], root)]
    controller = record["reusable_requirements"]["player"]["controller_scene"]
    scenes.append(_repo_scene_path(controller, root))
    modules = {item["id"]: item for item in catalog["modules"]}
    for reference in resolved["catalog_module_refs"]:
        module = modules.get(reference["catalog_id"])
        if module is None or module["version"] != reference["version"]:
            raise AdaptationValidationError(
                f"Catalog snapshot module reference is missing or changed: {reference['catalog_id']}"
            )
        scenes.append(_repo_scene_path(module["scene"], root))
        scenes.extend(
            _repo_dependency_path(path, root) for path in module.get("dependencies", [])
        )
    return scenes


def _repo_scene_path(value: str, root: Path) -> str:
    path, relative = resolve_scene_reference(value, root)
    if path.suffix != ".tscn":
        raise AdaptationValidationError(
            f"Scene reference must point to a .tscn file: {value}"
        )
    return relative


def _repo_dependency_path(value: str, root: Path) -> str:
    relative = value.removeprefix("res://") if value.startswith("res://") else value
    if value.startswith("res://"):
        relative = f"godot_walk/{relative}"
    path = resolve_repo_path(relative, root, require_file=True)
    return path.relative_to(root.resolve()).as_posix()
