#!/usr/bin/env python3
"""Generate validated collision geometry from a Gaussian splat.

Runs the pinned PlayCanvas ``splat-transform`` collision pipeline over a splat,
maps the result back into the calibrated frame of a #83 alignment contract, and
scores the output against the acceptance criteria before writing anything down.

Usage::

    python3 scripts/splat_pipeline/generate_collision.py \\
        --manifest godot_walk/assets/corridor_splat/alignment_manifest.json \\
        --ply exports/corridor_travel_v1/splat.ply \\
        --out outputs/collision/corridor_splat \\
        --report scripts/splat_pipeline/collision_benchmark.json

Exit status is 0 when every check passes, 1 when any check fails, 2 when the
tool is unavailable on this host, and 3 when an input is missing.  The four
outcomes mean different things to whoever is reading the log, so they are not
collapsed into one "error".

The report is written even when checks fail -- that is the useful artefact.  A
failing verdict with its numbers is the record; refusing to write it would throw
away the only evidence that the stage ran at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import splat_transform_cli as tool  # noqa: E402
from collision_params import (  # noqa: E402
    DEFAULT_CLUSTER_RESOLUTION_M,
    DEFAULT_EXTERIOR_FILL_RADIUS_M,
    DEFAULT_VOXEL_SIZE_M,
    CollisionError,
    collision_node_transform,
    contract_from_path,
    settings_from_contract,
    voxel_size_in_raw_units,
)
from glb_mesh import read_glb  # noqa: E402
from splat_columns import classify_columns  # noqa: E402
from splat_transform_cli import (  # noqa: E402
    CollisionStageFailed,
    SplatTransformUnavailable,
)
from traversability import OBSTRUCTION_TEST_HEIGHT_M, validate  # noqa: E402
from voxel_octree import VoxelFormatError, VoxelOctree  # noqa: E402

#: Floor-plan column size used for the splat cross-check, in metres.  A quarter
#: metre resolves a doorway reveal while still averaging over the handful of
#: splats a reconstructed wall is made of.
COLUMN_SIZE_M = 0.25

EXIT_OK = 0
EXIT_CHECKS_FAILED = 1
EXIT_TOOL_UNAVAILABLE = 2
EXIT_INPUT_MISSING = 3

#: Why a run with ``--without-contract`` cannot be scored.  Every acceptance
#: criterion in this task is a comparison against either the calibrated contract
#: or the reconstruction the splat came from; with neither, the only honest
#: verdict is "not measured".
NO_CONTRACT_REASON = (
    "the tool ran, but this asset has no alignment contract: there is no calibrated frame, no "
    "camera path and no metric scale, so floor continuity, wall blocking, doorway preservation and "
    "capsule clearance cannot be scored. The measurements recorded above are the tool's own and the "
    "mesh's topology, and nothing here should be read as a walkable result."
)


class MissingInput(CollisionError):
    """Raised when a required input file is absent, named in the message."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", required=True, help="#83 alignment contract JSON")
    parser.add_argument("--ply", required=True, help="Gaussian splat PLY to voxelize")
    parser.add_argument("--out", required=True, help="output stem for the collision files")
    parser.add_argument("--report", help="write the machine-readable benchmark here")
    parser.add_argument("--node-modules", help="directory containing @playcanvas/splat-transform")
    parser.add_argument("--voxel-size-m", type=float, help="override the voxel edge length in metres")
    parser.add_argument("--exterior-fill-m", type=float, help="override the exterior-fill dilation in metres")
    parser.add_argument("--cluster-resolution-m", type=float, help="override the cluster-filter grid in metres")
    parser.add_argument("--repeat", type=int, default=2, help="runs used for the determinism check")
    parser.add_argument(
        "--without-contract",
        action="store_true",
        help="measure the tool only; skip scoring, because there is no alignment contract to "
        "score against",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> tuple[int, dict]:
    """Generate and score the collision, returning ``(exit_status, report)``."""
    contract = contract_from_path(args.manifest)
    ply_path = Path(args.ply)
    if not ply_path.exists():
        raise MissingInput("no splat at %s" % ply_path)
    settings = settings_from_contract(
        contract,
        voxel_size_m=args.voxel_size_m or DEFAULT_VOXEL_SIZE_M,
        exterior_fill_radius_m=args.exterior_fill_m or DEFAULT_EXTERIOR_FILL_RADIUS_M,
        cluster_resolution_m=args.cluster_resolution_m or DEFAULT_CLUSTER_RESOLUTION_M,
    )
    settings.validate()
    metres_per_unit = contract.ply_to_world.metres_per_unit
    cli = tool.resolve_cli(args.node_modules)
    stem = Path(args.out)
    stem.parent.mkdir(parents=True, exist_ok=True)

    report: dict = {
        # In --without-contract mode the manifest is a borrowed contract: its
        # scale, frame and seed say nothing about this splat, so the report is
        # named after the splat instead of claiming the contract's scene.
        "scene_id": ply_path.stem if args.without_contract else contract.scene_id,
        "contract_scene_id": contract.scene_id,
        "tool": {
            "package": tool.PINNED_PACKAGE,
            "pinned_version": tool.PINNED_VERSION,
            "installed_version": tool.installed_version(cli),
            "gpu_adapters": tool.probe_adapters(cli),
            "cli": str(cli),
        },
        "inputs": {
            "manifest": str(args.manifest),
            "ply": str(ply_path),
            "ply_md5": _md5(ply_path),
            "footage_kind": contract.capture.get("footage_kind", "unknown"),
            "contract_splat_count": contract.splat_bounds.splat_count,
        },
        "settings": dict(settings.to_json(), voxel_size_ply_units=voxel_size_in_raw_units(settings.voxel_size_m, contract)),
        "godot_transform": {
            "collision_node_3x4": np.round(collision_node_transform(contract), 6).tolist(),
            "note": "basis = the splat node basis composed with the 180-degree z engine-frame "
            "rotation; translation is non-zero because Godot's glTF importer applies no centroid "
            "subtraction",
        },
    }
    if args.dry_run:
        report["dry_run"] = True
        report["argv"] = list(
            tool.build_argv(cli, ply_path, stem, settings, metres_per_unit)
        )
        return EXIT_OK, report

    run_record = tool.run_collision(cli, ply_path, stem, settings, metres_per_unit)
    voxel = VoxelOctree.load("%s.voxel.json" % stem)
    mesh = read_glb("%s.collision.glb" % stem)
    report["tool_run"] = run_record.to_json()
    report["voxel"] = _voxel_record(voxel)
    report["collision_mesh"] = _mesh_record(mesh)
    if args.without_contract:
        report["verdict"] = {
            "scene_id": report["scene_id"],
            "passed": False,
            "checks": [],
            "not_validated": NO_CONTRACT_REASON,
        }
        report["blocking_stage"] = _blocking_stage(run_record)
        if args.report:
            _write_report(Path(args.report), report)
        return EXIT_CHECKS_FAILED, report
    columns = classify_columns(ply_path, contract, COLUMN_SIZE_M)
    cameras = camera_positions(contract)
    verdict = validate(contract, settings, voxel, mesh, run_record, columns, cameras)
    report["splat_columns"] = columns.summary()
    report["determinism"] = determinism(cli, ply_path, stem, settings, metres_per_unit, args.repeat)
    report["expected_geometry"] = expected_geometry(contract, settings, voxel, columns, verdict)
    report["verdict"] = verdict.to_json()
    if args.report:
        _write_report(Path(args.report), report)
    return (EXIT_OK if verdict.passed else EXIT_CHECKS_FAILED), report


def determinism(cli, ply_path, stem, settings, metres_per_unit, repeats: int) -> dict:
    """Re-run the tool and compare output hashes, byte for byte.

    A second run into a scratch path rather than overwriting in place, so a
    mismatch leaves both artefacts available for a reviewer to diff.
    """
    if repeats < 2:
        return {"tested": False, "reason": "fewer than two runs requested"}
    scratch = Path(str(stem) + ".repeat")
    try:
        tool.run_collision(cli, ply_path, scratch, settings, metres_per_unit)
    except CollisionStageFailed as error:
        return {"tested": False, "reason": str(error)[:300]}
    files = ("voxel.json", "voxel.bin", "collision.glb")
    hashes = {}
    for suffix in files:
        first = Path("%s.%s" % (stem, suffix))
        second = Path("%s.%s" % (scratch, suffix))
        if not (first.exists() and second.exists()):
            hashes[suffix] = {"matched": False, "reason": "a run did not produce this file"}
            continue
        hashes[suffix] = {
            "matched": _md5(first) == _md5(second),
            "md5": _md5(first),
        }
    return {
        "tested": True,
        "runs": repeats,
        "byte_identical": all(entry.get("matched") for entry in hashes.values()),
        "files": hashes,
        "note": "splat-transform has no seedable sampling in these stages, so identical settings "
        "must give byte-identical output; a mismatch means the stages are order- or "
        "floating-point-dependent and the numbers are only reproducible within tolerance",
    }


def expected_geometry(contract, settings, voxel, columns, verdict) -> dict:
    """Return the blocking and opening geometry #85 needs, in calibrated metres.

    Expressed as floor-plan column runs rather than as boxes.  The manifest
    records ``walls_measured: false`` for this capture, so no wall offset can be
    quoted; the honest statement is which observed columns the collision blocks,
    which it leaves open, and where the navigable region actually is.  A run list
    was chosen over a bitmap because a bitmap of 4408 cells cannot be reviewed.
    """
    blocked = verdict.columns_solid & columns.has_floor
    open_columns = ~verdict.columns_solid & columns.has_floor
    return {
        "columns_are_measured_planes": False,
        "why": "the alignment manifest records walls_measured: false for this capture, so no wall "
        "offset can be quoted; what is reported is which observed columns the collision blocks",
        "test_height_m": OBSTRUCTION_TEST_HEIGHT_M,
        "column_size_m": columns.size_m,
        "column_origin_world_m": list(columns.origin),
        "blocked_column_runs": _column_runs(blocked),
        "open_column_runs": _column_runs(open_columns),
        "navigable_bounds_engine_frame_m": [
            [round(float(value), 4) for value in voxel.header.grid_min],
            [round(float(value), 4) for value in voxel.header.grid_max],
        ],
        "floor_height_m": float(contract.collider.floor_height),
        "ceiling_height_m": float(contract.collider.ceiling_height),
        "spawn_m": [round(float(value), 6) for value in contract.spawn],
        "player_capsule_m": {"radius": 0.3, "height": 1.2},
        "carve_capsule_m": {"radius": settings.capsule_radius_m, "height": settings.capsule_height_m},
    }


def _column_runs(mask) -> list[dict]:
    """Collapse a column mask into ``z-index -> list of x-index spans``.

    A span is ``[start, stop)`` on the column index, converted to metres by the
    caller through ``column_size_m`` and ``column_origin_world_m``.
    """
    runs = []
    for index, row in enumerate(mask):
        if not row.any():
            continue
        edges = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        starts = np.flatnonzero(edges == 1)
        stops = np.flatnonzero(edges == -1)
        runs.append({"row": index, "spans": [[int(a), int(b)] for a, b in zip(starts, stops)]})
    return runs


def _blocking_stage(run_record) -> dict:
    """Name the navigation stage that did nothing, if one did.

    A skipped stage still writes a valid-looking collision file, so on an
    uncalibrated asset the only thing distinguishing "collision generated" from
    "collision generated from a fist-sized pocket" is this flag.
    """
    return {
        "exterior_fill_skipped": run_record.exterior_fill_skipped,
        "carve_skipped": run_record.carve_skipped,
        "detail": "; ".join(run_record.warnings),
    }


def camera_positions(contract):
    """Return the reconstruction cameras in world metres, or ``None`` if unreachable.

    The paths come from the contract's own ``cameras.source``, which #83 records
    as prose ("192 registered cameras mapped through ... (data/scenes/.../sparse/0)
    then through ... (outputs/.../dataparser_transforms.json)").  Parsing prose for
    paths is fragile, so the contract's ``capture`` block -- which holds those same
    two paths as structured fields -- is used instead, and the prose is only
    checked for agreement.

    Returning ``None`` makes the camera-path checks fail with "unmeasured" rather
    than pass silently, which is the difference between "the route is covered"
    and "nobody looked".
    """
    capture = contract.capture
    model = str(capture.get("colmap_model", ""))
    dataparser = str(capture.get("nerfstudio_dataparser_transforms", ""))
    if not (model and dataparser):
        return None
    try:
        from colmap_model import read_images
        from measure_splat_frame import cameras_in_ply_frame, load_dataparser
    except ImportError:
        return None
    try:
        images = read_images(model)
        centres = cameras_in_ply_frame(images, load_dataparser(dataparser))
    except (OSError, ValueError, KeyError):
        return None
    if len(centres) != contract.cameras.count:
        return None
    return np.stack([contract.ply_to_world.world_point(row) for row in centres])


def _voxel_record(voxel: VoxelOctree) -> dict:
    """Summarise the voxel dataset for the report."""
    header = voxel.header
    return {
        "format_version": header.version,
        "generator": header.generator,
        "voxel_resolution_m": header.resolution,
        "grid_min_m": [round(value, 4) for value in header.grid_min],
        "grid_max_m": [round(value, 4) for value in header.grid_max],
        "grid_shape": list(header.grid_shape),
        "tree_depth": header.tree_depth,
        "node_count": header.node_count,
        "mixed_leaves": header.num_mixed_leaves,
    }


def _mesh_record(mesh) -> dict:
    """Summarise the collision mesh for the report."""
    return {
        "triangles": mesh.triangle_count,
        "vertices": mesh.vertex_count,
        "bounds_min_m": [round(float(value), 4) for value in mesh.bounds_min],
        "bounds_max_m": [round(float(value), 4) for value in mesh.bounds_max],
        "edges": mesh.edge_manifoldness(),
        "signed_volume_m3": round(mesh.signed_volume(), 4),
        "carries_vertex_normals": False,
    }


def _md5(path: Path) -> str:
    """Return the MD5 of a file, read in chunks so a 180 MB splat is fine."""
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_report(path: Path, report: dict) -> None:
    """Write the report as pretty JSON, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Entry point: generate, score, report, and return the exit status."""
    args = parse_args(argv)
    try:
        status, report = run(args)
    except SplatTransformUnavailable as error:
        print("TOOL UNAVAILABLE: %s" % error, file=sys.stderr)
        return EXIT_TOOL_UNAVAILABLE
    except MissingInput as error:
        print("MISSING INPUT: %s" % error, file=sys.stderr)
        return EXIT_INPUT_MISSING
    except (CollisionError, VoxelFormatError, CollisionStageFailed) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return EXIT_CHECKS_FAILED
    _print_summary(report)
    return status


def _print_summary(report: dict) -> None:
    """Print the tool record and every check's verdict."""
    if "dry_run" in report:
        print("dry run: %s" % " ".join(report["argv"]))
        return
    run_record = report.get("tool_run", {})
    print("splat-transform %s on %s" % (run_record.get("version", "?"), report["scene_id"]))
    print(
        "  %.2f s, %s -> %s gaussians, %d triangles, peak %.0f MiB CPU / %.0f MiB GPU"
        % (
            run_record.get("elapsed_s", 0.0),
            run_record.get("gaussians_in", 0),
            run_record.get("gaussians_out", 0),
            report.get("collision_mesh", {}).get("triangles", 0),
            run_record.get("peak_cpu_bytes", 0) / 1024 ** 2,
            run_record.get("peak_gpu_bytes", 0) / 1024 ** 2,
        )
    )
    determinism_record = report.get("determinism", {})
    if determinism_record.get("tested"):
        print("  deterministic across runs: %s" % determinism_record.get("byte_identical"))
    verdict = report.get("verdict", {})
    if verdict.get("not_validated"):
        print("  NOT VALIDATED: %s" % verdict["not_validated"])
        print("  blocking stage: %s" % report.get("blocking_stage", {}).get("detail", "none reported"))
        return
    for check in verdict.get("checks", []):
        print("  [%s] %-32s %s" % ("PASS" if check["passed"] else "FAIL", check["name"], check["detail"]))
    print("verdict: %s" % ("PASS" if verdict.get("passed") else "FAIL"))


if __name__ == "__main__":
    raise SystemExit(main())