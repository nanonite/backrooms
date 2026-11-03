"""Seeded, hash-independent random streams for shape rooms (never Python hash())."""

from __future__ import annotations

import hashlib
import random

GENERATOR_VERSION = "shape-room-0.1.0"


def cell_rng(map_seed: int, cell_id: str) -> random.Random:
    """Random(int) from sha256 of "<seed>:<cell_id>:<generator_version>"."""
    text = f"{map_seed}:{cell_id}:{GENERATOR_VERSION}"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, "big"))
