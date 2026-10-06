#!/usr/bin/env python3
"""Apply :mod:`splat_cleanup` to a 3DGS PLY and write a filtered derivative.

The source PLY is never modified. The derivative keeps every vertex property of
the source (positions, scales, rotations, opacity, spherical harmonics) and only
changes the vertex count, so the renderer imports it exactly as it imported the
source. A JSON report records the source hash, the deterministic parameters, the
per-stage removed counts and the node translation needed to keep the world
fixed after GDGS re-centres the filtered cloud at import.

That last field is load-bearing. ``gaussian_resource_builder.gd`` subtracts the
*mean of the loaded PLY* and the scene node carries the contract's zero
translation. Filtering changes the mean, so the presentation node must add
``M * (filtered_centroid - source_centroid)`` or the room shifts by ~1.6 m on
this asset -- still importing, still rendering, and wrong.

Usage:
    clean_splat.py --ply <source.ply> --manifest <alignment_manifest.json> \
        --out <derivative.ply> --report <report.json> \
        --margin-m 0.5 --max-extent-m 0.30 [--min-opacity 0.0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import splat_cleanup
import splat_frame
import splat_ply

END_HEADER_MARKER = b"end_header\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ply", required=True, type=Path, help="source 3DGS PLY")
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="alignment manifest holding the PLY->world contract",
    )
    parser.add_argument("--out", required=True, type=Path, help="filtered PLY to write")
    parser.add_argument("--report", required=True, type=Path, help="JSON report to write")
    parser.add_argument(
        "--margin-m",
        type=float,
        default=0.5,
        help="crop margin around the measured room, in metres (default 0.5)",
    )
    parser.add_argument(
        "--max-extent-m",
        type=float,
        default=0.30,
        help="drop splats whose largest extent exceeds this, in metres (0 disables)",
    )
    parser.add_argument(
        "--min-opacity",
        type=float,
        default=0.0,
        help="drop splats below this sigmoid(opacity) (0 disables)",
    )
    return parser.parse_args(argv)


def file_digests(path: Path) -> dict[str, str]:
    """Return md5 and sha256 digests of a file, read once."""
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    return {"md5": md5.hexdigest(), "sha256": sha256.hexdigest()}


def read_raw_ply(path: Path) -> tuple[list[str], np.ndarray, bytes]:
    """Return ``(property_names, table, header_prefix)`` for a binary PLY.

    ``table`` is the full ``(N, C)`` float32 vertex array. ``header_prefix`` is
    the source header up to and including ``end_header``; the writer rewrites
    only the ``element vertex`` line so every other byte of provenance survives.
    """
    header = splat_ply.parse_header(path)
    properties = list(header.properties)
    table = splat_ply.read_columns(path, tuple(properties)).astype(np.float32)
    raw = path.read_bytes()
    end = raw.find(END_HEADER_MARKER)
    if end == -1:
        raise splat_ply.PlyFormatError("%s: no end_header" % path)
    return properties, table, raw[: end + len(END_HEADER_MARKER)]


def rebuild_header(header_prefix: bytes, kept: int) -> bytes:
    """Return the source header with only the vertex count changed."""
    text = header_prefix.decode("ascii")
    lines = text.splitlines()
    out: list[str] = []
    in_vertex = False
    for line in lines:
        parts = line.split()
        if parts and parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                out.append("element vertex %d" % kept)
                continue
        out.append(line)
    return ("\n".join(out) + "\n").encode("ascii")


def write_subset_ply(path: Path, header_prefix: bytes, table: np.ndarray, keep: np.ndarray) -> None:
    """Write the kept rows with the source header (vertex count adjusted)."""
    kept_rows = np.ascontiguousarray(table[keep], dtype="<f4")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rebuild_header(header_prefix, kept_rows.shape[0]) + kept_rows.tobytes())


def world_positions(table: np.ndarray, properties: list[str], mapping) -> np.ndarray:
    """Map the raw x/y/z columns to Godot world metres."""
    index = {name: position for position, name in enumerate(properties)}
    raw = np.column_stack(
        [table[:, index["x"]], table[:, index["y"]], table[:, index["z"]]]
    ).astype(np.float64)
    rotation = mapping.rotation()
    origin = np.asarray(mapping.origin_ply_units, dtype=np.float64)
    return (rotation @ (raw - origin).T).T * mapping.metres_per_unit


def node_translation_world(
    filtered_centroid: np.ndarray, source_centroid: np.ndarray, mapping
) -> np.ndarray:
    """Return the node translation that keeps world positions fixed.

    The renderer computes ``world = M * (raw - centroid_loaded) + t_node``. The
    contract's world mapping is ``world = M * (raw - centroid_source)``. With
    ``centroid_loaded`` equal to the filtered mean, ``t_node`` must be
    ``M * (centroid_filtered - centroid_source)``.
    """
    return mapping.linear_matrix() @ (filtered_centroid - source_centroid)


def run(args: argparse.Namespace) -> dict:
    """Perform the cleanup and return the report dictionary."""
    contract = splat_frame.FrameContract.load(args.manifest)
    mapping = contract.ply_to_world

    properties, table, header_prefix = read_raw_ply(args.ply)
    index = {name: position for position, name in enumerate(properties)}
    for required in ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2"):
        if required not in index:
            raise splat_ply.PlyFormatError("%s: missing property %r" % (args.ply, required))

    positions_world = world_positions(table, properties, mapping)
    opacity = splat_cleanup.sigmoid_opacity(table[:, index["opacity"]].astype(np.float64))
    scale_log = np.column_stack(
        [table[:, index["scale_0"]], table[:, index["scale_1"]], table[:, index["scale_2"]]]
    ).astype(np.float64)
    extent_m = splat_cleanup.max_extent_metres(scale_log, mapping.metres_per_unit)

    params = splat_cleanup.CleanupParams.from_room(
        contract.splat_bounds.observed_min,
        contract.splat_bounds.observed_max,
        margin_m=args.margin_m,
        max_extent_m=args.max_extent_m,
        min_opacity=args.min_opacity,
    )
    keep, removed = splat_cleanup.compute_keep_mask(positions_world, opacity, extent_m, params)

    raw_positions = np.column_stack(
        [table[:, index["x"]], table[:, index["y"]], table[:, index["z"]]]
    ).astype(np.float64)
    source_centroid = np.asarray(mapping.origin_ply_units, dtype=np.float64)
    filtered_centroid = raw_positions[keep].mean(axis=0)
    translation = node_translation_world(filtered_centroid, source_centroid, mapping)

    write_subset_ply(args.out, header_prefix, table, keep)
    kept_world = positions_world[keep]
    report = {
        "schema_version": 1,
        "source": {
            "path": str(args.ply),
            "splat_count": int(table.shape[0]),
            "digests": file_digests(args.ply),
        },
        "output": {
            "path": str(args.out),
            "splat_count": int(keep.sum()),
            "digests": file_digests(args.out),
        },
        "contract": {
            "manifest": str(args.manifest),
            "scene_id": contract.scene_id,
            "metres_per_unit": mapping.metres_per_unit,
            "origin_ply_units": list(source_centroid),
        },
        "params": params.to_json(),
        "removed": {
            "per_stage": removed,
            "total": int(table.shape[0] - keep.sum()),
        },
        "kept_bounds_world": {
            "min": kept_world.min(axis=0).tolist(),
            "max": kept_world.max(axis=0).tolist(),
        },
        "filtered_centroid_ply": filtered_centroid.tolist(),
        "node_translation_world": translation.tolist(),
        "note": (
            "GDGS subtracts the mean of the loaded PLY at import, so the "
            "presentation node must carry node_translation_world on top of the "
            "contract's zero-translation basis to keep the world fixed."
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("source=%d kept=%d removed=%d" % (table.shape[0], keep.sum(), report["removed"]["total"]))
    print("removed per stage: %s" % json.dumps(removed))
    print("node_translation_world=(%.4f, %.4f, %.4f)" % tuple(translation))
    return report


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
