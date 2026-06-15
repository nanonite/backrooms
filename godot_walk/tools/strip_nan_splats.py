#!/usr/bin/env python3
"""Strip NaN/Inf splats from a binary_little_endian 3DGS PLY before GDGS import.

A single splat with a non-finite position (or any non-finite field) poisons the
merged AABB (NaN), which sends Godot's camera-framing math to NaN and yields
blank frames; the GDGS StandardPlyDecoder may also choke on the bad vertex.

This reads the PLY, drops every vertex that has any non-finite float field, and
writes a new PLY with the *identical* header (same format, property order, SH
degree) except the vertex count, which is reduced to the number kept.

Usage:
    strip_nan_splats.py <input.ply> <output.ply>
"""

import sys

import numpy as np


def parse_header(raw: bytes):
    """Return (header_len, property_names, vertex_count, header_lines)."""
    marker = b"end_header\n"
    idx = raw.find(marker)
    if idx == -1:
        raise SystemExit("ERROR: no end_header found; not an ASCII-header PLY")
    header_len = idx + len(marker)
    header_text = raw[:idx].decode("ascii")
    lines = header_text.splitlines()

    if not lines or lines[0].strip() != "ply":
        raise SystemExit("ERROR: missing 'ply' magic")
    fmt = next((l for l in lines if l.startswith("format")), "")
    if "binary_little_endian" not in fmt:
        raise SystemExit("ERROR: only binary_little_endian PLY is supported, got: %r" % fmt)

    props = []
    vertex_count = None
    in_vertex_element = False
    for l in lines:
        parts = l.split()
        if not parts:
            continue
        if parts[0] == "element":
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertex_element:
            if parts[1] == "list":
                raise SystemExit("ERROR: list properties not supported in vertex element")
            if parts[1] != "float":
                raise SystemExit("ERROR: expected all-float vertex properties, got %r" % parts[1])
            props.append(parts[2])

    if vertex_count is None:
        raise SystemExit("ERROR: no 'element vertex N' found")
    return header_len, props, vertex_count, lines


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: strip_nan_splats.py <input.ply> <output.ply>")
    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, "rb") as f:
        raw = f.read()

    header_len, props, vertex_count, header_lines = parse_header(raw)
    ncols = len(props)
    record_size = ncols * 4  # all <f4

    body = raw[header_len:]
    expected = vertex_count * record_size
    if len(body) < expected:
        raise SystemExit(
            "ERROR: body too short: have %d bytes, need %d (%d verts x %d)"
            % (len(body), expected, vertex_count, record_size)
        )
    # Trim any trailing bytes (newline/EOF padding) beyond the declared vertices.
    body = body[:expected]

    arr = np.frombuffer(body, dtype="<f4").reshape(vertex_count, ncols)
    mask = np.isfinite(arr).all(axis=1)
    kept = int(mask.sum())
    dropped = vertex_count - kept

    # Rebuild header with the new vertex count; preserve every other line verbatim.
    new_lines = []
    in_vertex_element = False
    for l in header_lines:
        parts = l.split()
        if parts and parts[0] == "element":
            in_vertex_element = parts[1] == "vertex"
            if in_vertex_element:
                new_lines.append("element vertex %d" % kept)
                continue
        new_lines.append(l)
    new_header = ("\n".join(new_lines) + "\nend_header\n").encode("ascii")

    kept_rows = arr[mask].tobytes()  # contiguous, same <f4 layout

    with open(out_path, "wb") as f:
        f.write(new_header)
        f.write(kept_rows)

    print("input=%d kept=%d dropped=%d" % (vertex_count, kept, dropped))


if __name__ == "__main__":
    main()
