"""shape-room-0.5.0: a room's `materials` come from the palette its map cell was assigned (issue 192)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from gmap_palette_registry import (
    load_registry,
    load_registry_v2,
    palette_by_id,
    spec_materials,
    spec_surface_materials,
)
from shape_room_checks import ShapeRoomError


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    return load_registry()


@lru_cache(maxsize=1)
def registry_v2() -> dict[str, Any]:
    return load_registry_v2()


def palette_materials(cell: dict[str, Any]) -> dict[str, Any]:
    """The spec `materials` block for `cell`: v0.5 palette fields or v0.9 selected variants."""
    record = cell.get("palette")
    if record is None:
        raise ShapeRoomError(f"{cell['cell_id']}: gmap-0.5.0 cell has no palette")
    if cell.get("surface_variants") is not None:
        # gmap_validate rejects any non-canonical 0.2.0 reference, so this loader
        # cannot disagree with the registry the map was validated against.
        palette = palette_by_id(registry_v2(), record["palette_id"])
        if palette is None:
            raise ShapeRoomError(
                f"{cell['cell_id']}: palette {record['palette_id']} is not in the 0.2.0 registry"
            )
        return spec_surface_materials(
            palette, dict(cell["surface_variants"]), int(cell.get("wear", 0))
        )
    palette = palette_by_id(registry(), record["palette_id"])
    if palette is None:
        raise ShapeRoomError(
            f"{cell['cell_id']}: palette {record['palette_id']} is not in the registry"
        )
    return spec_materials(palette)
