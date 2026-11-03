"""Seeded, hash-independent random streams for shape rooms (never Python hash())."""

from __future__ import annotations

import hashlib
import random

GENERATOR_VERSION = "shape-room-0.1.0"
GENERATOR_VERSION_V2 = "shape-room-0.2.0"
GENERATOR_VERSION_V3 = "shape-room-0.3.0"
GENERATOR_VERSION_V4 = "shape-room-0.4.0"
VERSIONS = (GENERATOR_VERSION, GENERATOR_VERSION_V2, GENERATOR_VERSION_V3, GENERATOR_VERSION_V4)
MAP_VERSION_V2 = "gmap-0.2.0"
MAP_VERSION_V3 = "gmap-0.3.0"
MAP_VERSION_V4 = "gmap-0.4.0"


def version_for_map(document: dict) -> str:
    """shape-room-0.4.0 for gmap-0.4.0 (45-degree walls), shape-room-0.3.0 for gmap-0.3.0 (per-port
    doorway sizes), shape-room-0.2.0 for gmap-0.2.0 (strict doorway margins), else shape-room-0.1.0."""
    version = document.get("generator_version")
    if version == MAP_VERSION_V4:
        return GENERATOR_VERSION_V4
    if version == MAP_VERSION_V3:
        return GENERATOR_VERSION_V3
    return GENERATOR_VERSION_V2 if version == MAP_VERSION_V2 else GENERATOR_VERSION


def cell_rng(map_seed: int, cell_id: str, version: str = GENERATOR_VERSION) -> random.Random:
    """Random(int) from sha256 of "<seed>:<cell_id>:<generator_version>"."""
    text = f"{map_seed}:{cell_id}:{version}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))
