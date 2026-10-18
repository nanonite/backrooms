"""Build an evidence-only support grid from #100 floor-oriented splats."""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))

from collision_params import contract_from_path
from source_inputs import (
    camera_sample_coverage,
    grid_parameters,
    load_camera_centres,
    select_floor_samples,
    sha256_file,
    world_gaussian_geometry,
)
from source_support import (
    filter_support,
    grid_from_points,
    triangulate_support,
    validate_alignment_manifest,
)

ALIGNMENT_PATH = ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
PLY_PATH = ROOT / "godot_walk/assets/corridor_splat/corridor.ply"
COLMAP_PATH = ROOT / "data/scenes/corridor_travel/sparse/0"
DATAPARSER_PATH = ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
HUNYUAN_CALIBRATION_PATH = HERE.parent / "calibration_manifest_frame_141.json"
OUTPUT_GRID = HERE / "source_floor_support_evidence.npz"
OUTPUT_MESH = HERE / "source_floor_patch_experimental_not_collision.obj"
OUTPUT_REPORT = HERE / "source_floor_support_report.json"

GRID_SPACING_M = 0.05
MAX_SLOPE_DEGREES = 15.0
MAX_STEP_M = 0.20


def write_obj(path: Path, mesh) -> None:
    """Write an evidence mesh; it is not a runtime collider asset."""
    with path.open("w", encoding="ascii") as handle:
        handle.write("# Evidence-only support patch. Not a collision asset.\n")
        handle.write("o observed_source_floor_samples_not_collision\n")
        for x, y, z in mesh.vertices:
            handle.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for first, second, third in mesh.triangles + 1:
            handle.write(f"f {first} {second} {third}\n")


def write_grid(grid, filtered) -> None:
    """Save source evidence with unknown and rejected states kept separate."""
    np.savez_compressed(
        OUTPUT_GRID,
        heights_m=grid.heights_m.astype(np.float32),
        observed=grid.observed.astype(np.uint8),
        supported=filtered.supported.astype(np.uint8),
        rejection_reason=filtered.rejection_reason,
        origin_x_m=np.float64(grid.origin_x_m),
        origin_z_m=np.float64(grid.origin_z_m),
        spacing_m=np.float64(grid.spacing_m),
    )


def frame_record(frame: dict, contract, hunyuan: dict) -> dict:
    """Keep the #100 chosen scale and unaccepted Hunyuan candidate distinct."""
    return {
        **frame,
        "scene_id": contract.scene_id,
        "metric_scale_accepted": False,
        "scale_note": "The #100 scale is a chosen synthetic convention, not surveyed metric scale.",
        "hunyuan_transform_used": False,
        "hunyuan_registration_accepted": hunyuan["registration_accepted"],
        "hunyuan_convention_scale": hunyuan["scale"],
        "hunyuan_scale_note": "Recorded for provenance only; no Hunyuan geometry or scale entered this grid.",
    }


def input_record(cameras_world: np.ndarray) -> dict:
    """Record source hashes needed to reproduce the sample selection."""
    return {
        "alignment_manifest": str(ALIGNMENT_PATH.relative_to(ROOT)),
        "alignment_manifest_sha256": sha256_file(ALIGNMENT_PATH),
        "source_ply": str(PLY_PATH.relative_to(ROOT)),
        "source_ply_sha256": sha256_file(PLY_PATH),
        "colmap_images": str((COLMAP_PATH / "images.bin").relative_to(ROOT)),
        "colmap_images_sha256": sha256_file(COLMAP_PATH / "images.bin"),
        "dataparser_transform": str(DATAPARSER_PATH.relative_to(ROOT)),
        "dataparser_transform_sha256": sha256_file(DATAPARSER_PATH),
        "mapped_camera_bounds_match_contract": True,
        "registered_camera_count": len(cameras_world),
    }


def grid_record(grid, filtered) -> dict:
    """Summarize known, rejected, and unsupported grid cells."""
    observed = grid.observed
    return {
        "resolution_m": GRID_SPACING_M,
        "origin_xz_m": [grid.origin_x_m, grid.origin_z_m],
        "shape_rows_z_columns_x": list(grid.heights_m.shape),
        "grid_cell_count": int(grid.heights_m.size),
        "observed_cells_before_filter": int(observed.sum()),
        "unsupported_unknown_cells_before_filter": int((~observed).sum()),
        "cells_rejected_for_local_geometry": int(
            (observed & ~filtered.supported).sum()
        ),
        "supported_cells_after_filter": int(filtered.supported.sum()),
        "accepted_slope_degrees": MAX_SLOPE_DEGREES,
        "maximum_step_m": MAX_STEP_M,
        "filtered_reason_counts": {
            "slope_or_step": int((filtered.rejection_reason != 0).sum()),
            "step_bit_set": int(((filtered.rejection_reason & 1) != 0).sum()),
            "slope_bit_set": int(((filtered.rejection_reason & 2) != 0).sum()),
        },
        "unknown_cells_filled": 0,
    }


def make_report(
    frame, contract, hunyuan, cameras_world, selection, grid, filtered, mesh, started
) -> dict:
    """Assemble the evidence report without implying metric or physics approval."""
    return {
        "schema_version": 1,
        "issue": 135,
        "status": "evidence_only_route_support_failed",
        "asset_status": "not_collision_not_runtime_imported",
        "gpu_used": False,
        "method": "#100 Gaussian centres near its declared floor plane and with a floor-like short covariance axis",
        "source_masks": {
            "reviewed_floor_masks_available": False,
            "note": "No reviewed floor masks or dense registered floor mesh were found in this worktree.",
        },
        "frame": frame_record(frame, contract, hunyuan),
        "inputs": input_record(cameras_world),
        "selection": selection,
        "grid": grid_record(grid, filtered),
        "patch": {
            "vertex_count": len(mesh.vertices),
            "triangle_count": len(mesh.triangles),
            "file": str(OUTPUT_MESH.relative_to(ROOT)),
            "grid_file": str(OUTPUT_GRID.relative_to(ROOT)),
            "note": "Only fully observed adjacent quads are emitted. This OBJ is evidence only, not a valid collision asset.",
        },
        "camera_path_sample_coverage": camera_sample_coverage(
            grid, filtered.supported, cameras_world
        ),
        "measurements": {
            "registered_camera_samples_within_0_30m": "proximity only; not a walkability test",
            "tested_walkability": False,
            "bevy_avian_tnua_runtime_tested": False,
            "collision_glb_created": False,
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "grid_npz_bytes": OUTPUT_GRID.stat().st_size,
            "obj_bytes": OUTPUT_MESH.stat().st_size,
        },
        "failure_reason": "The 5 cm observation grid yields only one contiguous quad and 69/192 camera samples are within 0.30 m of support samples. This proximity probe is not traversal evidence; no connected player route is established.",
    }


def build() -> dict:
    """Run the bounded source-only experiment and write evidence artefacts."""
    started = time.monotonic()
    alignment = json.loads(ALIGNMENT_PATH.read_text(encoding="utf-8"))
    frame = validate_alignment_manifest(alignment, "corridor_splat")
    contract = contract_from_path(ALIGNMENT_PATH)
    cameras_world = load_camera_centres(contract, COLMAP_PATH, DATAPARSER_PATH)
    positions, normals = world_gaussian_geometry(PLY_PATH, contract)
    samples, selection = select_floor_samples(
        positions, normals, contract.collider.floor_height, cameras_world
    )
    selection["ply_gaussian_count"] = len(positions)
    origin_x, origin_z, shape = grid_parameters(cameras_world, GRID_SPACING_M)
    grid = grid_from_points(samples, origin_x, origin_z, GRID_SPACING_M, shape)
    filtered = filter_support(grid, MAX_SLOPE_DEGREES, MAX_STEP_M)
    mesh = triangulate_support(grid, filtered)
    write_grid(grid, filtered)
    write_obj(OUTPUT_MESH, mesh)
    hunyuan = json.loads(HUNYUAN_CALIBRATION_PATH.read_text(encoding="utf-8"))
    if hunyuan.get("registration_accepted") is not False:
        raise ValueError("expected Hunyuan registration to remain unaccepted")
    report = make_report(
        frame,
        contract,
        hunyuan,
        cameras_world,
        selection,
        grid,
        filtered,
        mesh,
        started,
    )
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
