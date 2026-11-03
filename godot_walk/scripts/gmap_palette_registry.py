"""Material palette registry (issue 192): load, validate and pick palettes by style tag.

The registry is hand-curated data (room_catalog/material_palettes/palettes-0.1.0.json). Every value
names where it was read from; `registry_errors` re-reads those files so a stale citation is caught.
Nothing here edits the registry, the library rooms or their textures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, repo_relative, sha256_file  # noqa: E402
from library_index import load_json  # noqa: E402

REGISTRY_PATH = Path("godot_walk/room_catalog/material_palettes/palettes-0.1.0.json")
SCHEMA_PATH = Path("godot_walk/room_catalog/material_palettes/material_palette.schema.json")
SURFACES = ("wall", "floor", "ceiling")
FIELDS = (*SURFACES, "trim_color", "lamp_color")
COLOUR = re.compile(r"Color\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")


def registry_ref(root: Path = ROOT) -> dict[str, str]:
    path = root / REGISTRY_PATH
    return {"path": repo_relative(path, root), "sha256": sha256_file(path)}


def load_registry(root: Path = ROOT) -> dict[str, Any]:
    return load_json(root / REGISTRY_PATH)


def palette_by_id(registry: dict[str, Any], palette_id: str) -> dict[str, Any] | None:
    return next((p for p in registry["palettes"] if p["palette_id"] == palette_id), None)


def default_palette(registry: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in registry["palettes"] if p["is_default"])


def select_palette(registry: dict[str, Any], style_tags: Iterable[str]) -> dict[str, Any] | None:
    """First non-default palette (sorted by palette_id) whose match_style_tags overlap `style_tags`."""
    tags = set(style_tags)
    for palette in sorted(registry["palettes"], key=lambda p: p["palette_id"]):
        if not palette["is_default"] and tags & set(palette["match_style_tags"]):
            return palette
    return None


def spec_materials(palette: dict[str, Any]) -> dict[str, Any]:
    """The `materials` block of a shape-room-0.5.0 spec: the palette without provenance."""
    materials: dict[str, Any] = {"palette_id": palette["palette_id"]}
    for key in SURFACES:
        materials[key] = {k: v for k, v in palette[key].items() if k != "provenance"}
    for key in ("trim_color", "lamp_color"):
        materials[key] = list(palette[key]["color"])
    return materials


def resolve(res_path: str, root: Path) -> Path:
    """res:// is the godot_walk project folder."""
    return root / "godot_walk" / res_path.removeprefix("res://")


def provenance_errors(palette_id: str, key: str, field: dict[str, Any], root: Path) -> list[str]:
    label = f"{palette_id}.{key}"
    path_text, _, name = field["provenance"]["from"].partition("::")
    source = resolve(path_text, root)
    if not source.is_file():
        return [f"{label}: provenance file {path_text} is missing"]
    lines = [line for line in source.read_text(encoding="utf-8").splitlines() if name in line]
    if not lines:
        return [f"{label}: {path_text} does not contain {name!r}"]
    if field["provenance"]["sign"] != "icon":
        return []  # authored values have no source literal to compare
    if "texture" in field:
        wanted = field["texture"].rsplit("/", 1)[-1]
        return [] if any(wanted in line for line in lines) else [f"{label}: no {name} line names {wanted}"]
    if "color" in field:
        found = [tuple(float(v) for v in m.groups()) for line in lines for m in COLOUR.finditer(line)]
        if not any(all(abs(a - b) < 1e-6 for a, b in zip(triple, field["color"])) for triple in found):
            return [f"{label}: no {name} line holds Color{tuple(field['color'])}"]
    return []


def registry_errors(registry: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Schema, unique ids, exactly one default, existing textures and cited constants."""
    validator = Draft202012Validator(load_json(root / SCHEMA_PATH))
    errors = [f"schema: {e.message}" for e in validator.iter_errors(registry)]
    if errors:
        return errors
    palettes = registry["palettes"]
    ids = [p["palette_id"] for p in palettes]
    if len(set(ids)) != len(ids):
        errors.append("palette ids are not unique")
    if sum(1 for p in palettes if p["is_default"]) != 1:
        errors.append("the registry needs exactly one default palette")
    for palette in palettes:
        for key in FIELDS:
            field = palette[key]
            if "texture" in field and not resolve(field["texture"], root).is_file():
                errors.append(f"{palette['palette_id']}.{key}: texture {field['texture']} is missing")
            errors += provenance_errors(palette["palette_id"], key, field, root)
    return errors
