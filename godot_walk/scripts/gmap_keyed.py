"""Independent deterministic random streams for gmap-0.13.0 layers."""

from __future__ import annotations

import hashlib
import random


def rng_for_cell(
    seed: int, attempt: int, stream: str, cell_id: str, draw: str
) -> random.Random:
    """Return a draw stream addressed by layer, cell and draw purpose."""
    key = f"{seed}:{attempt}:{stream}:{cell_id}:{draw}".encode("utf-8")
    return random.Random(int.from_bytes(hashlib.sha256(key).digest(), "big"))


def keyed_rank(seed: int, attempt: int, stream: str, key: str) -> bytes:
    """Stable sortable rank for graph-wide candidates."""
    return hashlib.sha256(f"{seed}:{attempt}:{stream}:{key}".encode("utf-8")).digest()
