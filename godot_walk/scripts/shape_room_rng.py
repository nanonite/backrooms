"""Seeded, hash-independent random streams for shape rooms (never Python hash())."""

from __future__ import annotations

import hashlib
import random

GENERATOR_VERSION = "shape-room-0.1.0"
GENERATOR_VERSION_V2 = "shape-room-0.2.0"
GENERATOR_VERSION_V3 = "shape-room-0.3.0"
GENERATOR_VERSION_V4 = "shape-room-0.4.0"
GENERATOR_VERSION_V5 = "shape-room-0.5.0"
GENERATOR_VERSION_V6 = "shape-room-0.6.0"
GENERATOR_VERSION_V7 = "shape-room-0.7.0"
GENERATOR_VERSION_V8 = "shape-room-0.8.0"
GENERATOR_VERSION_V9 = "shape-room-0.9.0"
GENERATOR_VERSION_V10 = "shape-room-0.10.0"
VERSIONS = (
    GENERATOR_VERSION,
    GENERATOR_VERSION_V2,
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
)
V4_PLUS = (
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
)  # 45-degree walls, clear-of-library-room ceilings
MAP_VERSION_V2 = "gmap-0.2.0"
MAP_VERSION_V3 = "gmap-0.3.0"
MAP_VERSION_V4 = "gmap-0.4.0"
MAP_VERSION_V5 = "gmap-0.5.0"
MAP_VERSION_V6 = "gmap-0.6.0"
MAP_VERSION_V61 = "gmap-0.6.1"
MAP_VERSION_V7 = "gmap-0.7.0"
MAP_VERSION_V8 = "gmap-0.8.0"
MAP_VERSION_V9 = "gmap-0.9.0"
MAP_VERSION_V10 = "gmap-0.10.0"


def version_for_map(document: dict) -> str:
    """shape-room-0.5.0 for gmap-0.5.0 (palette materials), shape-room-0.4.0 for gmap-0.4.0 (45-degree walls), shape-room-0.3.0 for gmap-0.3.0 (per-port
    doorway sizes), shape-room-0.2.0 for gmap-0.2.0 (strict doorway margins), else shape-room-0.1.0."""
    version = document.get("generator_version")
    if version == MAP_VERSION_V10:
        return GENERATOR_VERSION_V10
    if version == MAP_VERSION_V7:
        return GENERATOR_VERSION_V7
    if version == MAP_VERSION_V9:
        return GENERATOR_VERSION_V9
    if version == MAP_VERSION_V8:
        return GENERATOR_VERSION_V8
    if version == MAP_VERSION_V5:
        return GENERATOR_VERSION_V5
    if version in (MAP_VERSION_V6, MAP_VERSION_V61):
        return GENERATOR_VERSION_V6
    if version == MAP_VERSION_V4:
        return GENERATOR_VERSION_V4
    if version == MAP_VERSION_V3:
        return GENERATOR_VERSION_V3
    return GENERATOR_VERSION_V2 if version == MAP_VERSION_V2 else GENERATOR_VERSION


def cell_rng(
    map_seed: int, cell_id: str, version: str = GENERATOR_VERSION
) -> random.Random:
    """Random(int) from sha256 of "<seed>:<cell_id>:<generator_version>" (shape-room-0.5.0 uses 0.4.0's key)."""
    if (
        version == GENERATOR_VERSION_V5
    ):  # same draws as shape-room-0.4.0: only the materials differ
        version = GENERATOR_VERSION_V4
    if version == GENERATOR_VERSION_V9:
        version = GENERATOR_VERSION_V7
    if version == GENERATOR_VERSION_V10:
        version = GENERATOR_VERSION_V7
    if version == GENERATOR_VERSION_V8:
        version = GENERATOR_VERSION_V7
    if version == GENERATOR_VERSION_V7:
        version = GENERATOR_VERSION_V6  # v0.7 changes geometry only for the map-selected landmark
    text = f"{map_seed}:{cell_id}:{version}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))
