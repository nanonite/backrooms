"""Doorway clear size per connector compatibility type (issue 188).

One lookup table; scripts/doorway_sizes.gd carries the same table for the Godot builder and a
unit test keeps the two in step. A doorway's solid-wall margin on each side is 0.5 m, so the
port margin from an envelope side end is half the width plus that 0.5 m.
"""

from __future__ import annotations

DEFAULT_TYPE = "level_doorway_2m_v1"
WIDE_TYPE = "authored_direct_doorway_2.4x2.2_v1"
# compatibility_type -> (clear width m, clear height m)
DOORWAY_SIZES: dict[str, tuple[float, float]] = {
    DEFAULT_TYPE: (2.0, 2.1),
    WIDE_TYPE: (2.4, 2.2),
    "maze_rewire_1_4m_v1": (1.4, 2.2),
}
WALL_MARGIN_M = 0.5


def doorway_size(compatibility_type: str) -> tuple[float, float]:
    """(width, height); a type outside the table is a fail-closed error."""
    try:
        return DOORWAY_SIZES[compatibility_type]
    except KeyError as error:
        raise ValueError(f"no doorway size for compatibility type {compatibility_type!r}") from error


def port_margin_m(compatibility_type: str) -> float:
    """Least distance from an envelope side end to the doorway centre (1.5 m for 2 m doorways)."""
    return doorway_size(compatibility_type)[0] / 2.0 + WALL_MARGIN_M
