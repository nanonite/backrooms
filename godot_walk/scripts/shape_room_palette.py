"""shape-room-0.5.0: a room's `materials` come from the palette its map cell was assigned (issue 192)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from gmap_palette_registry import load_registry, palette_by_id, spec_materials
from shape_room_checks import ShapeRoomError


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    return load_registry()


def palette_materials(cell: dict[str, Any]) -> dict[str, Any]:
    """The spec `materials` block (palette_id, wall, floor, ceiling, trim_color, lamp_color) for `cell`."""
    record = cell.get("palette")
    if record is None:
        raise ShapeRoomError(f"{cell['cell_id']}: gmap-0.5.0 cell has no palette")
    palette = palette_by_id(registry(), record["palette_id"])
    if palette is None:
        raise ShapeRoomError(f"{cell['cell_id']}: palette {record['palette_id']} is not in the registry")
    return spec_materials(palette)
