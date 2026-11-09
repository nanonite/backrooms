"""Material palette registries (issues 192, 199 and 208): load, validate and select palettes.

The 0.1.0 registry is frozen. The 0.2.0 registry adds surface variants and acoustic tags
for gmap-0.9.0. The 0.3.0 registry adds the tile, metal and wood regional floor palettes
for gmap-0.12.0 while keeping the three 0.2.0 palettes unchanged. Every value names where
it was read or generated from; `registry_errors` re-reads those sources so a stale
citation is caught. Nothing here edits the registries, library rooms or their textures.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, repo_relative, sha256_file
from library_index import load_json

REGISTRY_PATH = Path("godot_walk/room_catalog/material_palettes/palettes-0.1.0.json")
SCHEMA_PATH = Path(
    "godot_walk/room_catalog/material_palettes/material_palette.schema.json"
)
REGISTRY_PATH_V2 = Path("godot_walk/room_catalog/material_palettes/palettes-0.2.0.json")
SCHEMA_PATH_V2 = Path(
    "godot_walk/room_catalog/material_palettes/material_palette_v2.schema.json"
)
REGISTRY_PATH_V3 = Path("godot_walk/room_catalog/material_palettes/palettes-0.3.0.json")
SCHEMA_PATH_V3 = Path(
    "godot_walk/room_catalog/material_palettes/material_palette_v3.schema.json"
)
GENERATED_TEXTURE_PREFIX = "res://assets/psx_extension/textures/surfaces/"
GENERATED_MANIFEST = Path(
    "godot_walk/assets/psx_extension/textures/surfaces/surface_variants.json"
)
GENERATED_MANIFEST_V3 = Path(
    "godot_walk/assets/psx_extension/textures/surfaces/palette_0_3_0_textures.json"
)
SURFACES = ("wall", "floor", "ceiling")
SURFACES_V2 = ("wall", "floor", "ceiling", "trim")
VARIANTS = ("clean", "worn", "damaged")
ACOUSTIC_TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris")
FIELDS = (*SURFACES, "trim_color", "lamp_color")
COLOUR = re.compile(r"Color\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)")
SHA256 = re.compile(r"^[a-f0-9]{64}$")


def registry_ref(root: Path = ROOT) -> dict[str, str]:
    path = root / REGISTRY_PATH
    return {"path": repo_relative(path, root), "sha256": sha256_file(path)}


def registry_ref_v2(root: Path = ROOT) -> dict[str, str]:
    path = root / REGISTRY_PATH_V2
    return {"path": repo_relative(path, root), "sha256": sha256_file(path)}


def registry_ref_v3(root: Path = ROOT) -> dict[str, str]:
    path = root / REGISTRY_PATH_V3
    return {"path": repo_relative(path, root), "sha256": sha256_file(path)}


def load_registry(root: Path = ROOT) -> dict[str, Any]:
    return load_json(root / REGISTRY_PATH)


def load_registry_v2(root: Path = ROOT) -> dict[str, Any]:
    return load_json(root / REGISTRY_PATH_V2)


def load_registry_v3(root: Path = ROOT) -> dict[str, Any]:
    return load_json(root / REGISTRY_PATH_V3)


def load_registry_file(path: Path) -> dict[str, Any]:
    """Load the registry named by a document ref (0.1.0, 0.2.0 or 0.3.0)."""
    return load_json(path)


def palette_by_id(registry: dict[str, Any], palette_id: str) -> dict[str, Any] | None:
    return next(
        (p for p in registry["palettes"] if p["palette_id"] == palette_id), None
    )


def default_palette(registry: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in registry["palettes"] if p["is_default"])


def select_palette(
    registry: dict[str, Any], style_tags: Iterable[str]
) -> dict[str, Any] | None:
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


def spec_surface_materials(
    palette: dict[str, Any],
    variants: dict[str, str],
    wear: int,
    registry_version: str = "0.2.0",
) -> dict[str, Any]:
    """The selected wall/floor/ceiling/trim values and acoustic tags for a v0.9 cell."""
    materials: dict[str, Any] = {
        "palette_id": palette["palette_id"],
        "registry_version": registry_version,
        "wear": wear,
        "acoustic": {},
        "variants": {},
        "lamp_color": list(palette["lamp_color"]["color"]),
    }
    for surface in SURFACES_V2:
        field = palette["surfaces"][surface]
        chosen = variants.get(surface, "clean")
        if chosen not in field["variants"]:
            chosen = "clean"
        variant = field["variants"][chosen]
        materials["acoustic"][surface] = field["acoustic"]
        materials["variants"][surface] = chosen
        if surface == "trim":
            materials["trim_color"] = list(variant["color"])
            continue
        materials[surface] = {
            key: value for key, value in variant.items() if key != "provenance"
        }
        materials[surface]["acoustic"] = field["acoustic"]
        materials[surface]["variant"] = chosen
    return materials


def resolve(res_path: str, root: Path) -> Path:
    """res:// is the godot_walk project folder."""
    return root / "godot_walk" / res_path.removeprefix("res://")


def provenance_errors(
    palette_id: str, key: str, field: dict[str, Any], root: Path
) -> list[str]:
    label = f"{palette_id}.{key}"
    path_text, _, name = field["provenance"]["from"].partition("::")
    source = resolve(path_text, root)
    if not source.is_file():
        return [f"{label}: provenance file {path_text} is missing"]
    lines = [
        line for line in source.read_text(encoding="utf-8").splitlines() if name in line
    ]
    if not lines:
        return [f"{label}: {path_text} does not contain {name!r}"]
    if field["provenance"]["sign"] != "icon":
        return []  # authored values have no source literal to compare
    if "texture" in field:
        wanted = field["texture"].rsplit("/", 1)[-1]
        return (
            []
            if any(wanted in line for line in lines)
            else [f"{label}: no {name} line names {wanted}"]
        )
    if "color" in field:
        found = [
            tuple(float(v) for v in m.groups())
            for line in lines
            for m in COLOUR.finditer(line)
        ]
        if not any(
            all(abs(a - b) < 1e-6 for a, b in zip(triple, field["color"]))
            for triple in found
        ):
            return [f"{label}: no {name} line holds Color{tuple(field['color'])}"]
    return []


def _variant_provenance_errors(
    label: str, field: dict[str, Any], root: Path
) -> list[str]:
    path_text, _, name = field["provenance"]["from"].partition("::")
    source = resolve(path_text, root)
    if not source.is_file():
        return [f"{label}: provenance file {path_text} is missing"]
    lines = [
        line for line in source.read_text(encoding="utf-8").splitlines() if name in line
    ]
    if not lines:
        return [f"{label}: {path_text} does not contain {name!r}"]
    if "texture" in field:
        wanted = field["texture"].rsplit("/", 1)[-1]
        stem = wanted.removesuffix(".png")
        if any(wanted in line or stem in line for line in lines):
            return []
        return [f"{label}: no {name} line names {wanted}"]
    if "color" in field:
        found = [
            tuple(float(value) for value in match.groups())
            for line in lines
            for match in COLOUR.finditer(line)
        ]
        if any(
            all(abs(a - b) < 1e-6 for a, b in zip(triple, field["color"]))
            for triple in found
        ):
            return []
        return [f"{label}: no {name} line holds Color{tuple(field['color'])}"]
    return []


def _generated_manifest(root: Path) -> dict[str, dict[str, Any]] | None:
    records: dict[str, dict[str, Any]] = {}
    found = False
    for relative in (GENERATED_MANIFEST, GENERATED_MANIFEST_V3):
        path = root / relative
        if not path.is_file():
            continue
        found = True
        try:
            document = load_json(path)
            for record in document["records"]:
                records[record["output"]] = record
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return records if found else None


def _manifest_record_errors(record: Any, expected_output: str) -> list[str]:
    if not isinstance(record, dict):
        return ["record is not a JSON object"]
    problems = []
    if record.get("output") != expected_output:
        problems.append("output does not match the texture path")
    for key in ("source", "variant"):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"{key} is missing or not a string")
    if isinstance(record.get("variant"), str) and record["variant"] not in VARIANTS:
        problems.append(f"variant {record['variant']} is not clean/worn/damaged")
    for key in ("source_sha256", "output_sha256"):
        value = record.get(key)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            problems.append(f"{key} is missing or not a sha256")
    source = record.get("source")
    if isinstance(source, str):
        source_path = Path(source)
        if source_path.is_absolute() or ".." in source_path.parts:
            problems.append("source is not a repository-relative path")
    return problems


def _generated_texture_errors(
    label: str,
    field: dict[str, Any],
    root: Path,
    manifest: dict[str, dict[str, Any]] | None,
) -> list[str]:
    if not field["texture"].startswith(GENERATED_TEXTURE_PREFIX):
        return []
    texture = resolve(field["texture"], root)
    if not texture.is_file():
        return [f"{label}: generated texture {field['texture']} is missing"]
    if manifest is None:
        return [f"{label}: generated texture manifest is missing or invalid"]
    expected_output = repo_relative(texture, root)
    record = manifest.get(expected_output)
    if record is None:
        return [f"{label}: {field['texture']} is not recorded in surface_variants.json"]
    problems = _manifest_record_errors(record, expected_output)
    if problems:
        return [
            f"{label}: malformed surface_variants.json record for "
            f"{field['texture']}: " + "; ".join(problems)
        ]
    source = root / record["source"]
    if not source.is_file():
        return [f"{label}: generated source {record['source']} is missing"]
    if sha256_file(source) != record["source_sha256"]:
        return [f"{label}: generated source {record['source']} hash changed"]
    if sha256_file(texture) != record["output_sha256"]:
        return [f"{label}: generated texture {field['texture']} hash changed"]
    return []


def _surface_registry_errors(registry: dict[str, Any], root: Path = ROOT) -> list[str]:
    schema_path = SCHEMA_PATH_V3 if registry.get("schema_version") == 3 else SCHEMA_PATH_V2
    validator = Draft202012Validator(load_json(root / schema_path))
    errors = [f"schema: {e.message}" for e in validator.iter_errors(registry)]
    if errors:
        return errors
    manifest = _generated_manifest(root)
    palettes = registry["palettes"]
    ids = [palette["palette_id"] for palette in palettes]
    if len(set(ids)) != len(ids):
        errors.append("palette ids are not unique")
    if sum(1 for palette in palettes if palette["is_default"]) != 1:
        errors.append("the registry needs exactly one default palette")
    for palette in palettes:
        for surface in SURFACES_V2:
            field = palette["surfaces"][surface]
            label = f"{palette['palette_id']}.{surface}"
            if field["acoustic"] not in ACOUSTIC_TAGS:
                errors.append(f"{label}: unknown acoustic tag {field['acoustic']}")
            for variant_id, variant in sorted(field["variants"].items()):
                if variant_id not in VARIANTS:
                    errors.append(f"{label}: unknown variant {variant_id}")
                    continue
                if (
                    "texture" in variant
                    and not resolve(variant["texture"], root).is_file()
                ):
                    if variant["texture"].startswith(GENERATED_TEXTURE_PREFIX):
                        errors += _generated_texture_errors(
                            f"{label}.{variant_id}", variant, root, manifest
                        )
                    else:
                        errors.append(
                            f"{label}.{variant_id}: texture {variant['texture']} is missing"
                        )
                    continue
                errors += _variant_provenance_errors(
                    f"{label}.{variant_id}", variant, root
                )
                if "texture" in variant:
                    errors += _generated_texture_errors(
                        f"{label}.{variant_id}", variant, root, manifest
                    )
        errors += provenance_errors(
            palette["palette_id"], "lamp_color", palette["lamp_color"], root
        )
    return errors


def registry_errors(registry: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Schema, unique ids, exactly one default, existing textures and cited constants."""
    if registry.get("schema_version") in (2, 3):
        return _surface_registry_errors(registry, root)
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
                errors.append(
                    f"{palette['palette_id']}.{key}: texture {field['texture']} is missing"
                )
            errors += provenance_errors(palette["palette_id"], key, field, root)
    return errors
