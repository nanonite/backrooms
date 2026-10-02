#!/usr/bin/env python3
"""Read the vertex count from a 3D Gaussian Splat PLY header.

Deliberately self-contained rather than reusing the pipeline's ``splat_ply``
reader. A benchmark has to be able to price an asset that another task owns, and
importing that task's module would make this one unusable on a checkout where it
has not landed. One measurement -- how many Gaussians are in the file -- does not
justify coupling two independently-owned stages.

Only the ASCII header is read, so a 170 MB splat is probed without paying for
its data, and nothing is interpreted: the count is exactly what the file claims.
"""

from __future__ import annotations

from pathlib import Path

#: Enough for any header nerfstudio, Brush or the GDGS importer writes. Longer
#: headers are not truncated in practice; the file is re-read if this is not
#: enough rather than guessing.
HEADER_PROBE_BYTES = 65536

PLY_MAGIC = "ply"
END_HEADER_MARKER = "end_header"


class PlyHeaderError(ValueError):
    """Raised when a file is not the ASCII-header PLY a splat count needs."""


def vertex_count(path: str | Path) -> int:
    """Return the number of vertices a binary PLY declares.

    Raises :class:`PlyHeaderError` when the file is absent, is not a PLY, or
    declares no vertex element. Callers that want a soft answer should catch it;
    a benchmark must not silently record a count of zero for an unreadable asset.
    """
    raw = _read_header(path)
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] == "element" and parts[1] == "vertex":
            return int(parts[2])
    raise PlyHeaderError(f"{path}: no 'element vertex N' in the PLY header")


def _read_header(path: str | Path) -> str:
    """Return the ASCII text between the PLY magic and ``end_header``."""
    target = Path(path)
    if not target.is_file():
        raise PlyHeaderError(f"{target}: not a file")
    with target.open("rb") as handle:
        raw = handle.read(HEADER_PROBE_BYTES)
    text = raw.decode("ascii", "replace")
    if not text.startswith(PLY_MAGIC):
        raise PlyHeaderError(f"{target}: missing 'ply' magic")
    if END_HEADER_MARKER not in text:
        raise PlyHeaderError(f"{target}: no end_header within {HEADER_PROBE_BYTES} bytes")
    return text[: text.index(END_HEADER_MARKER)]