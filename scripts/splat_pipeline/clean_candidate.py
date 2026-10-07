#!/usr/bin/env python3
"""Apply :mod:`splat_filter` to the #100 cleanup result and write a candidate derivative.

The #100 output (``corridor_clean.ply``) is the *input* here and is never
modified: source, #100 result and this candidate all exist side by side, so a
reviewer can re-render any of the three. The candidate keeps every vertex
property of its input and only changes the vertex count, so the renderer
imports it exactly as it imported the #100 file.

Provenance is checked, not claimed: by default the input PLY's sha256 must
equal the digest recorded in the #100 baseline report, so "candidate built from
the shipped #100 result" is a verified statement rather than an assumption. The
report then records input/output digests, the exact parameters, per-stage
removed counts, the component/view diagnostics and the node translation that
keeps the world fixed after GDGS re-centres the smaller cloud (the trap
``clean_splat.py`` documents and ``test_candidate_scene.py`` checks).

Usage:
    clean_candidate.py --ply <#100 output.ply> --manifest <alignment_manifest.json> \
        --out <candidate.ply> --report <candidate.report.json> \
        [--baseline-report <#100 report.json>] \
        [--min-views 1 --colmap <sparse/0> --dataparser <dataparser_transforms.json>] \
        [--voxel-m 0.08 --min-component-splats N] \
        [--min-opacity 0.0 --min-extent-m 0.0 --max-extent-m 0.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clean_splat
import colmap_model
import measure_splat_frame
import splat_components
import splat_cleanup
import splat_filter
import splat_frame
import splat_ply
import view_support


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ply", required=True, type=Path, help="#100 cleanup output PLY")
    parser.add_argument("--manifest", required=True, type=Path, help="alignment manifest")
    parser.add_argument("--out", required=True, type=Path, help="candidate PLY to write")
    parser.add_argument("--report", required=True, type=Path, help="JSON report to write")
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=None,
        help="#100 report whose recorded output digest must match --ply (provenance check)",
    )
    parser.add_argument("--min-views", type=int, default=0, help="multi-view support floor (0 disables)")
    parser.add_argument("--colmap", type=Path, default=None, help="COLMAP sparse model dir (views stage)")
    parser.add_argument("--dataparser", type=Path, default=None, help="nerfstudio dataparser json (views stage)")
    parser.add_argument("--voxel-m", type=float, default=0.08, help="connectivity grid pitch in metres")
    parser.add_argument(
        "--min-component-splats",
        type=int,
        default=0,
        help="keep components at least this large (0 disables)",
    )
    parser.add_argument("--min-opacity", type=float, default=0.0, help="sigmoid(opacity) floor (0 disables)")
    parser.add_argument("--min-extent-m", type=float, default=0.0, help="smallest Gaussian extent (0 disables)")
    parser.add_argument("--max-extent-m", type=float, default=0.0, help="largest Gaussian extent (0 disables)")
    return parser.parse_args(argv)


def check_baseline(path: Path, baseline_report: Path | None) -> dict:
    """Return the baseline report, having verified the input is its recorded output."""
    digest = clean_splat.file_digests(path)["sha256"]
    if baseline_report is None:
        return {"checked": False, "input_sha256": digest}
    recorded = json.loads(baseline_report.read_text(encoding="utf-8"))
    expected = recorded.get("output", {}).get("digests", {}).get("sha256")
    if expected != digest:
        raise SystemExit(
            "ERROR: %s sha256 %s does not match the baseline report output digest %s; "
            "the input is not the shipped #100 result" % (path, digest, expected)
        )
    return {
        "checked": True,
        "baseline_report": str(baseline_report),
        "baseline_report_sha256": clean_splat.file_digests(baseline_report)["sha256"],
        "baseline_output_sha256": expected,
        "input_sha256": digest,
    }


def view_diagnostics(view_counts: np.ndarray | None) -> dict | None:
    """Summarise the per-splat view counts for the report."""
    if view_counts is None:
        return None
    return {
        "min": int(view_counts.min()),
        "median": float(np.median(view_counts)),
        "max": int(view_counts.max()),
        "zero_view_share": round(float((view_counts == 0).mean()), 6),
    }


def component_diagnostics(labels: np.ndarray | None) -> dict | None:
    """Summarise the connectivity labelling for the report."""
    if labels is None:
        return None
    sizes = splat_components.component_sizes(labels)
    ordered = np.sort(sizes)[::-1]
    return {
        "component_count": int(len(ordered)),
        "largest_splats": int(ordered[0]),
        "top_sizes": [int(value) for value in ordered[:10]],
        "single_splat_components": int((ordered == 1).sum()),
    }


def compute_view_counts(args: argparse.Namespace, positions_world: np.ndarray, contract) -> np.ndarray:
    """Project every splat into every registered training camera and count hits."""
    if args.colmap is None or args.dataparser is None:
        raise SystemExit("ERROR: --min-views > 0 requires --colmap and --dataparser")
    images = colmap_model.read_images(args.colmap)
    cameras = colmap_model.read_cameras(args.colmap)
    dataparser = measure_splat_frame.load_dataparser(str(args.dataparser))
    centres = view_support.camera_centres_world(images, dataparser, contract.ply_to_world)
    view_support.verify_camera_bound(centres, contract.cameras, tolerance_m=0.01)
    points_colmap = view_support.world_to_colmap(positions_world, contract.ply_to_world, dataparser)
    return view_support.count_views(points_colmap, images, cameras)


def run(args: argparse.Namespace) -> dict:
    """Build the candidate and return the report dictionary."""
    contract = splat_frame.FrameContract.load(args.manifest)
    mapping = contract.ply_to_world
    baseline = check_baseline(args.ply, args.baseline_report)

    properties, table, header_prefix = clean_splat.read_raw_ply(args.ply)
    index = {name: position for position, name in enumerate(properties)}
    for required in ("x", "y", "z", "opacity", "scale_0", "scale_1", "scale_2"):
        if required not in index:
            raise splat_ply.PlyFormatError("%s: missing property %r" % (args.ply, required))

    positions_world = clean_splat.world_positions(table, properties, mapping)
    opacity = splat_cleanup.sigmoid_opacity(table[:, index["opacity"]].astype(np.float64))
    scale_log = np.column_stack(
        [table[:, index["scale_%d" % axis]] for axis in range(3)]
    ).astype(np.float64)
    extent_m = splat_cleanup.max_extent_metres(scale_log, mapping.metres_per_unit)

    params = splat_filter.CandidateParams(
        min_views=args.min_views,
        voxel_m=args.voxel_m,
        min_component_splats=args.min_component_splats,
        min_opacity=args.min_opacity,
        min_extent_m=args.min_extent_m,
        max_extent_m=args.max_extent_m,
    )
    view_counts = compute_view_counts(args, positions_world, contract) if params.uses_views else None
    keep, removed = splat_filter.compute_keep_mask(
        positions_world, opacity, extent_m, params, view_counts
    )
    if not keep.any():
        raise SystemExit("ERROR: every splat was removed; refusing to write an empty candidate")

    labels = (
        splat_components.label_components(positions_world, params.voxel_m)
        if params.uses_components
        else None
    )

    raw_positions = np.column_stack(
        [table[:, index["x"]], table[:, index["y"]], table[:, index["z"]]]
    ).astype(np.float64)
    source_centroid = np.asarray(mapping.origin_ply_units, dtype=np.float64)
    filtered_centroid = raw_positions[keep].mean(axis=0)
    translation = clean_splat.node_translation_world(filtered_centroid, source_centroid, mapping)

    clean_splat.write_subset_ply(args.out, header_prefix, table, keep)
    kept_world = positions_world[keep]
    report = {
        "schema_version": 1,
        "input": {
            "path": str(args.ply),
            "splat_count": int(table.shape[0]),
            "digests": clean_splat.file_digests(args.ply),
            "provenance": baseline,
        },
        "output": {
            "path": str(args.out),
            "splat_count": int(keep.sum()),
            "digests": clean_splat.file_digests(args.out),
        },
        "contract": {
            "manifest": str(args.manifest),
            "scene_id": contract.scene_id,
            "metres_per_unit": mapping.metres_per_unit,
            "origin_ply_units": list(source_centroid),
        },
        "params": params.to_json(),
        "sources": _source_paths(args, params),
        "removed": {"per_stage": removed, "total": int(table.shape[0] - keep.sum())},
        "view_counts": view_diagnostics(view_counts),
        "components": component_diagnostics(labels),
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

    print("input=%d kept=%d removed=%d" % (table.shape[0], keep.sum(), report["removed"]["total"]))
    print("removed per stage: %s" % json.dumps(removed))
    print("node_translation_world=(%.4f, %.4f, %.4f)" % tuple(translation))
    return report


def _source_paths(args: argparse.Namespace, params: splat_filter.CandidateParams) -> dict[str, str]:
    """Record the auxiliary data the stages were computed from."""
    if not params.uses_views:
        return {}
    return {"colmap_model": str(args.colmap), "dataparser": str(args.dataparser)}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
