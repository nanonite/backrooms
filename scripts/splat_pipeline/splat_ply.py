#!/usr/bin/env python3
"""Read a 3D Gaussian Splat PLY (binary_little_endian, float32 vertex props).

Pure passthrough reader: it returns exactly the numbers stored in the file and
never applies a correction.  Deciding what those numbers *mean* (which axis is
up, what one unit is worth in metres) belongs to ``splat_frame``; keeping the
read dumb is what makes the contract auditable.

Only the columns a caller asks for are materialised, so a 180 MB splat can be
probed for ``x/y/z`` without paying for the 45 spherical-harmonic floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

REQUIRED_PROPERTIES = ("x", "y", "z")
POSITION_PROPERTIES = ("x", "y", "z")


class PlyFormatError(ValueError):
    """Raised when a PLY is not the ASCII-header binary-little-endian 3DGS form."""


@dataclass(frozen=True)
class PlyHeader:
    """Parsed ASCII PLY header."""

    byte_length: int
    vertex_count: int
    properties: tuple[str, ...]
    comments: tuple[str, ...]

    @property
    def stride_bytes(self) -> int:
        return len(self.properties) * 4


def parse_header(path: str | Path) -> PlyHeader:
    """Parse the ASCII header of a binary-little-endian PLY."""
    with Path(path).open("rb") as handle:
        raw = handle.read(65536)
    marker = b"end_header\n"
    end = raw.find(marker)
    if end == -1:
        raise PlyFormatError("%s: no end_header; expected an ASCII-header PLY" % path)
    header_length = end + len(marker)
    lines = raw[:end].decode("ascii", "replace").splitlines()
    if not lines or lines[0].strip() != "ply":
        raise PlyFormatError("%s: missing 'ply' magic" % path)

    vertex_count = None
    properties: list[str] = []
    comments: list[str] = []
    in_vertex = False
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertex:
            if parts[1] != "float":
                raise PlyFormatError("%s: vertex property %r is not float" % (path, parts[2]))
            properties.append(parts[2])
        elif parts[0] == "comment":
            comments.append(line[len("comment") :].strip())

    if vertex_count is None:
        raise PlyFormatError("%s: no 'element vertex N'" % path)
    if vertex_count <= 0:
        raise PlyFormatError("%s: vertex count is %d" % (path, vertex_count))
    missing = [name for name in REQUIRED_PROPERTIES if name not in properties]
    if missing:
        raise PlyFormatError("%s: missing vertex properties %s" % (path, ", ".join(missing)))
    return PlyHeader(header_length, vertex_count, tuple(properties), tuple(comments))


def read_columns(path: str | Path, names: tuple[str, ...]) -> np.ndarray:
    """Return an ``(N, len(names))`` float64 array of the requested columns."""
    header = parse_header(path)
    missing = [name for name in names if name not in header.properties]
    if missing:
        raise PlyFormatError("%s: missing vertex properties %s" % (path, ", ".join(missing)))
    dtype = np.dtype([(name, "<f4") for name in header.properties])
    table = np.memmap(
        Path(path), dtype=dtype, mode="r", offset=header.byte_length, shape=(header.vertex_count,)
    )
    return np.stack([table[name].astype(np.float64) for name in names], axis=1)


def read_positions(path: str | Path) -> np.ndarray:
    """Return the ``(N, 3)`` float64 ``(x, y, z)`` columns exactly as stored."""
    return read_columns(path, POSITION_PROPERTIES)


def read_alphas(path: str | Path) -> np.ndarray:
    """Return sigmoid(opacity) as stored in the PLY."""
    opacity = read_columns(path, ("opacity",))[:, 0]
    return 1.0 / (1.0 + np.exp(-opacity))


def header_comments(path: str | Path) -> dict[str, str]:
    """Return header comments as ``{key: value}``, lower-cased keys.

    GDGS' decoders ignore these entirely; the alignment contract records them as
    provenance so a future reader can see what the exporter *claimed* about the
    frame and check it against measurement rather than trusting it.
    """
    parsed: dict[str, str] = {}
    for comment in parse_header(path).comments:
        key, _, value = comment.partition(" ")
        parsed[key.strip().lower()] = value.strip()
    return parsed