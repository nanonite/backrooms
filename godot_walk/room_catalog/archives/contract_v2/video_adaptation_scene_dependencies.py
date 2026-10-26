"""Resolve and verify scene resources against an adaptation artifact manifest."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from video_adaptation_errors import AdaptationValidationError
from video_adaptation_paths import ROOT, resolve_repo_path, resolve_scene_reference

EXTERNAL_RESOURCE = re.compile(r"\[ext_resource[^\]]*\]")
RESOURCE_PATH = re.compile(r'path="([^"]+)"')
RESOURCE_TYPE = re.compile(r'type="([^"]+)"')


def validate_required_scene_dependencies(
    record: dict[str, Any], catalog: dict[str, Any], root: Path = ROOT
) -> None:
    resolved = record["resolved_adaptation"]
    dependencies = {item["path"] for item in resolved["dependencies"]}
    scenes = _required_scene_paths(record, catalog, root)
    missing = _transitive_scene_dependencies(scenes, root) - dependencies
    if missing:
        raise AdaptationValidationError(
            f"Required scene dependency is not fingerprinted: {min(missing)}"
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
            _repo_scene_path(path, root)
            for path in module.get("dependencies", [])
            if path.endswith(".tscn")
        )
    return scenes


def _transitive_scene_dependencies(scenes: list[str], root: Path) -> set[str]:
    pending = list(scenes)
    visited: set[str] = set()
    dependencies: set[str] = set()
    while pending:
        scene = pending.pop()
        if scene in visited:
            continue
        path = resolve_repo_path(scene, root, require_file=True)
        if path.suffix != ".tscn":
            raise AdaptationValidationError(
                f"Scene dependency must reference a .tscn file: {scene}"
            )
        visited.add(scene)
        dependencies.add(scene)
        for resource in EXTERNAL_RESOURCE.findall(path.read_text(encoding="utf-8")):
            match = RESOURCE_PATH.search(resource)
            resource_type = RESOURCE_TYPE.search(resource)
            if not match:
                continue
            resource_path = _repo_resource_path(match.group(1), root)
            dependencies.add(resource_path)
            if resource_type and resource_type.group(1) == "PackedScene":
                pending.append(resource_path)
    return dependencies


def _repo_scene_path(value: str, root: Path) -> str:
    path, relative = resolve_scene_reference(value, root)
    if path.suffix != ".tscn":
        raise AdaptationValidationError(
            f"Scene reference must point to a .tscn file: {value}"
        )
    return relative


def _repo_resource_path(value: str, root: Path) -> str:
    relative = value.removeprefix("res://") if value.startswith("res://") else value
    if value.startswith("res://"):
        relative = f"godot_walk/{relative}"
    path = resolve_repo_path(relative, root, require_file=True)
    return path.relative_to(root.resolve()).as_posix()
