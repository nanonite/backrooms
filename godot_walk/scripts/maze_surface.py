"""Palette-compatible surface layers for the M8 follower edits (#238).

M8 adds the cheap metadata layers that still have a visual or audible tell:
the room's wet/dry ``reverb`` flag, its ``wear`` level and its per-surface
``surface_variants`` record.  The committed map is only ever read; an edit
lives in the M1 overlay as a per-cell override.

This module owns the palette check.  A cell's palette must exist in the
registry the map names, the registry hash must match, and every selected
variant must exist for that surface in that palette.  A variant can only move
forward along ``clean -> worn -> damaged``; nothing is ever downgraded.

The runtime equivalent is ``maze_surface_controller.gd``.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, sha256_file
from library_index import load_json

RULE = "maze_surface"
SURFACE_LAYER_VERSION = "maze-surface-0.1.0"
SURFACES = ("floor", "wall", "ceiling", "trim")
VARIANT_ORDER = ("clean", "worn", "damaged")
MIN_WEAR = 0
MAX_WEAR = 2
REGISTRY_VERSIONS = ("0.2.0", "0.3.0")
REGISTRY_DIRECTORY = "godot_walk/room_catalog/material_palettes"


class SurfaceError(ValueError):
    """A palette or surface-layer record is missing or incompatible."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@lru_cache(maxsize=8)
def _registry_at(path_text: str, expected_sha256: str, root_text: str) -> dict[str, Any]:
    root = Path(root_text)
    path = root / path_text
    if not path.is_file():
        raise SurfaceError("palette_missing", f"palette registry {path_text} is missing")
    if sha256_file(path) != expected_sha256:
        raise SurfaceError(
            "palette_stale", f"palette registry {path_text} does not match its recorded hash"
        )
    registry = load_json(path)
    if not isinstance(registry, dict) or not isinstance(registry.get("palettes"), list):
        raise SurfaceError("palette_invalid", f"{path_text} is not a palette registry")
    return registry


def _registry_reference(document: dict[str, Any]) -> tuple[str, str]:
    reference = document.get("palette_registry")
    if not isinstance(reference, dict):
        raise SurfaceError("palette_missing", "map has no palette_registry reference")
    path_text = reference.get("path")
    expected = reference.get("sha256")
    if not isinstance(path_text, str) or not path_text:
        raise SurfaceError("palette_missing", "palette_registry.path is missing")
    if not isinstance(expected, str) or len(expected) != 64:
        raise SurfaceError("palette_missing", "palette_registry.sha256 is missing")
    relative = Path(path_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise SurfaceError("palette_invalid", "palette_registry.path is not repository-relative")
    return path_text, expected


def palette_registry(
    document: dict[str, Any], *, root: Path = ROOT
) -> dict[str, Any]:
    """Load and hash-check the registry the map names."""
    path_text, expected = _registry_reference(document)
    return _registry_at(path_text, expected, str(root))


def registry_version_for(document: dict[str, Any]) -> str:
    """The palette registry version named by the map reference."""
    path_text, _ = _registry_reference(document)
    folder = Path(REGISTRY_DIRECTORY) / "palettes-"
    relative = Path(path_text).as_posix()
    prefix = folder.as_posix()
    if not relative.startswith(prefix) or not relative.endswith(".json"):
        raise SurfaceError("palette_invalid", f"{path_text} is not a palette registry path")
    version = relative[len(prefix) : -len(".json")]
    if version not in REGISTRY_VERSIONS:
        raise SurfaceError("palette_invalid", f"unsupported palette registry {version}")
    return version


def palette_for_cell(
    document: dict[str, Any],
    cell: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    root: Path = ROOT,
) -> dict[str, Any]:
    """The registry entry for one cell, or a ``palette_*`` error."""
    record = cell.get("palette")
    if not isinstance(record, dict):
        raise SurfaceError("palette_missing", f"{cell.get('cell_id')}: no palette record")
    palette_id = record.get("palette_id")
    if not isinstance(palette_id, str) or not palette_id:
        raise SurfaceError("palette_missing", f"{cell.get('cell_id')}: no palette_id")
    version = record.get("registry_version")
    if version is not None and version not in REGISTRY_VERSIONS:
        raise SurfaceError(
            "palette_incompatible", f"{cell.get('cell_id')}: registry {version} is not supported"
        )
    loaded = registry if registry is not None else palette_registry(document, root=root)
    palette = next(
        (entry for entry in loaded["palettes"] if entry.get("palette_id") == palette_id),
        None,
    )
    if not isinstance(palette, dict):
        raise SurfaceError(
            "palette_unknown", f"{cell.get('cell_id')}: palette {palette_id} is not registered"
        )
    return palette


def surface_record(cell: dict[str, Any]) -> dict[str, str]:
    """The cell's per-surface variant record, copied and shape-checked."""
    record = cell.get("surface_variants")
    if not isinstance(record, dict):
        raise SurfaceError(
            "surface_missing", f"{cell.get('cell_id')}: no surface_variants record"
        )
    result: dict[str, str] = {}
    for surface in SURFACES:
        value = record.get(surface)
        if not isinstance(value, str) or value not in VARIANT_ORDER:
            raise SurfaceError(
                "surface_invalid", f"{cell.get('cell_id')}: {surface} variant {value!r}"
            )
        result[surface] = value
    return result


def wear_record(cell: dict[str, Any]) -> int:
    """The cell's wear level, copied and range-checked."""
    value = cell.get("wear")
    if type(value) is not int or not MIN_WEAR <= value <= MAX_WEAR:
        raise SurfaceError("wear_invalid", f"{cell.get('cell_id')}: wear {value!r}")
    return value


def validate_variants(
    cell: dict[str, Any], variants: dict[str, str], palette: dict[str, Any]
) -> None:
    """Every surface must name a variant that exists in the cell's palette."""
    surfaces = palette.get("surfaces")
    if not isinstance(surfaces, dict):
        raise SurfaceError("palette_invalid", f"{palette.get('palette_id')}: no surfaces block")
    for surface in SURFACES:
        variant = variants.get(surface)
        if not isinstance(variant, str) or variant not in VARIANT_ORDER:
            raise SurfaceError(
                "variant_invalid", f"{cell.get('cell_id')}: {surface} variant {variant!r}"
            )
        field = surfaces.get(surface)
        available = field.get("variants") if isinstance(field, dict) else None
        if not isinstance(available, dict):
            raise SurfaceError(
                "palette_incompatible",
                f"{palette.get('palette_id')}: no variants for {surface}",
            )
        if variant not in available:
            raise SurfaceError(
                "variant_incompatible",
                f"{cell.get('cell_id')}: {surface} {variant} is not in "
                f"palette {palette.get('palette_id')}",
            )


def validate_cell(
    document: dict[str, Any], cell: dict[str, Any], *, root: Path = ROOT
) -> tuple[dict[str, str], int]:
    """The cell's variants and wear after the palette check."""
    palette = palette_for_cell(document, cell, root=root)
    variants = surface_record(cell)
    validate_variants(cell, variants, palette)
    return variants, wear_record(cell)


def next_variant(surface: str, current: str, palette: dict[str, Any]) -> str | None:
    """The next variant along clean -> worn -> damaged that the palette offers."""
    if current not in VARIANT_ORDER:
        raise SurfaceError("variant_invalid", f"{surface} variant {current!r}")
    surfaces = palette.get("surfaces")
    field = surfaces.get(surface) if isinstance(surfaces, dict) else None
    available = field.get("variants") if isinstance(field, dict) else None
    if not isinstance(available, dict):
        raise SurfaceError(
            "palette_incompatible", f"{palette.get('palette_id')}: no variants for {surface}"
        )
    for candidate in VARIANT_ORDER[VARIANT_ORDER.index(current) + 1 :]:
        if candidate in available:
            return candidate
    return None


def escalatable_from_variants(
    variants: dict[str, str], palette: dict[str, Any]
) -> list[str]:
    """Surfaces whose given variant can move at least one step forward."""
    result: list[str] = []
    for surface in SURFACES:
        current = variants.get(surface)
        if not isinstance(current, str) or current not in VARIANT_ORDER:
            raise SurfaceError("variant_invalid", f"{surface} variant {current!r}")
        if next_variant(surface, current, palette) is not None:
            result.append(surface)
    return result


def escalatable_surfaces(cell: dict[str, Any], palette: dict[str, Any]) -> list[str]:
    """Surfaces whose current variant can move at least one step forward."""
    variants = surface_record(cell)
    validate_variants(cell, variants, palette)
    return escalatable_from_variants(variants, palette)


def effective_variants(
    document: dict[str, Any],
    cell: dict[str, Any],
    override: dict[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, str]:
    """Base variants with one folded ``surface_variant`` change applied.

    The overlay key is the change class (singular), not the cell layer name
    (``surface_variants``), because M1 stores an edit under ``change.class``.
    """
    palette = palette_for_cell(document, cell, root=root)
    variants = surface_record(cell)
    value = override.get("surface_variant")
    if value is not None:
        if not isinstance(value, dict):
            raise SurfaceError(
                "override_invalid", f"{cell.get('cell_id')}: surface_variants is not an object"
            )
        for surface, variant in value.items():
            if surface not in SURFACES:
                raise SurfaceError("override_invalid", f"unknown surface {surface!r}")
            if not isinstance(variant, str):
                raise SurfaceError("override_invalid", f"{surface} variant is not a string")
            variants[surface] = variant
    validate_variants(cell, variants, palette)
    return variants


def effective_wear(cell: dict[str, Any], override: dict[str, Any]) -> int:
    """Base wear with one folded ``wear`` override applied."""
    wear = wear_record(cell)
    value = override.get("wear")
    if value is not None:
        if type(value) is not int or not MIN_WEAR <= value <= MAX_WEAR:
            raise SurfaceError(
                "override_invalid", f"{cell.get('cell_id')}: wear override {value!r}"
            )
        wear = value
    return wear


def surface_change(
    cell: dict[str, Any],
    surface: str,
    before: dict[str, str],
    palette: dict[str, Any],
) -> dict[str, str] | None:
    """The full variants record after one surface moves forward, or ``None``."""
    after = copy.deepcopy(before)
    variant = next_variant(surface, before[surface], palette)
    if variant is None:
        return None
    after[surface] = variant
    validate_variants(cell, after, palette)
    return after
