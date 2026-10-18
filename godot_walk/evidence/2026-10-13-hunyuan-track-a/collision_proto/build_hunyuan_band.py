"""Build an evidence-only Hunyuan floor-band mesh ablation on CPU."""

from __future__ import annotations

import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import find_objects, label
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "splat_pipeline"))
sys.path.insert(0, str(HERE))

from collision_params import contract_from_path
from colmap_model import read_images
from hunyuan_band import (
    BASE_TRIANGLE_COUNT,
    GRID_HEIGHT,
    GRID_WIDTH,
    MAX_SLOPE_DEGREES,
    MAX_STEP_METRES,
    component_records,
    filter_safe_faces,
    panorama_vertex_selection,
    point_triangle_distance_2d,
    select_original_faces,
    triangle_metrics,
)
from source_inputs import load_camera_centres, sha256_file

PLY_PATH = ROOT / "data/track-a/hunyuan/scene-run-05/mesh_layer1.ply"
MASK_PATH = ROOT / "data/track-a/hunyuan/scene-run-05/fg1_mask.png"
COLMAP_PATH = ROOT / "data/scenes/corridor_travel/sparse/0"
DATAPARSER_PATH = ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
ALIGNMENT_PATH = ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
CALIBRATION_PATH = EVIDENCE / "calibration_manifest_frame_141.json"
OUTPUT_REPORT = HERE / "hunyuan_band_ablation_report.json"
OUTPUT_MESH = HERE / "hunyuan_band_patch_experimental_not_collision.obj"
OUTPUT_GRID = HERE / "hunyuan_band_patch_experimental_not_collision.npz"

VERTEX_DTYPE = np.dtype(
    [
        ("x", "<f8"),
        ("y", "<f8"),
        ("z", "<f8"),
        ("nx", "<f8"),
        ("ny", "<f8"),
        ("nz", "<f8"),
        ("red", "u1"),
        ("green", "u1"),
        ("blue", "u1"),
    ]
)
FACE_DTYPE = np.dtype(
    {
        "names": ["count", "a", "b", "c"],
        "formats": ["u1", "<u4", "<u4", "<u4"],
        "offsets": [0, 1, 5, 9],
        "itemsize": 13,
    }
)


def ply_layout(path: Path) -> tuple[int, int, int]:
    """Read and validate the bounded binary PLY header and offsets."""
    with path.open("rb") as handle:
        header = bytearray()
        while b"end_header\n" not in header:
            line = handle.readline()
            if not line or len(header) > 65536:
                raise ValueError("invalid or oversized PLY header")
            header.extend(line)
        vertex_offset = handle.tell()
    text = header.decode("ascii")
    if "format binary_little_endian 1.0" not in text:
        raise ValueError("run-05 PLY must use binary little-endian format")
    expected_properties = (
        "property double x",
        "property double y",
        "property double z",
        "property double nx",
        "property double ny",
        "property double nz",
        "property uchar red",
        "property uchar green",
        "property uchar blue",
        "property list uchar uint vertex_indices",
    )
    if not all(declaration in text for declaration in expected_properties):
        raise ValueError("run-05 PLY vertex or face property schema changed")
    vertex_count = _element_count(text, "vertex")
    face_count = _element_count(text, "face")
    if vertex_count != GRID_HEIGHT * GRID_WIDTH:
        raise ValueError("unexpected Hunyuan layer-1 panorama vertex count")
    if face_count < BASE_TRIANGLE_COUNT:
        raise ValueError("PLY is missing original panorama-grid triangles")
    return vertex_offset, vertex_count, face_count


def _element_count(header: str, name: str) -> int:
    """Return one declared PLY element count or fail on an ambiguous header."""
    matches = [
        line.split()[-1]
        for line in header.splitlines()
        if line.startswith(f"element {name} ")
    ]
    if len(matches) != 1:
        raise ValueError(f"PLY must declare one {name} element")
    return int(matches[0])


def calibration_transform() -> tuple[np.ndarray, np.ndarray, float, dict]:
    """Load only the explicitly unaccepted frame-141 candidate transform."""
    document = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    if document.get("registration_accepted") is not False:
        raise ValueError("refusing to use an accepted or changed Hunyuan registration")
    if document.get("scale_status") != "convention_derived_not_surveyed":
        raise ValueError("Hunyuan candidate scale basis changed")
    rotation = np.asarray(
        document["rotation_local_to_world_row_major"], dtype=np.float64
    )
    translation = np.asarray(document["translation_world_declared"], dtype=np.float64)
    scale = float(document["scale"])
    if rotation.shape != (3, 3) or translation.shape != (3,) or scale <= 0.0:
        raise ValueError("Hunyuan similarity transform is malformed")
    return rotation, translation, scale, document


def resized_foreground_mask() -> tuple[np.ndarray, dict]:
    """Apply the upstream PIL nearest resize from run-05 mask resolution."""
    source = Image.open(MASK_PATH).convert("L")
    source_size = source.size
    if source_size != (2560, 1280):
        raise ValueError("run-05 foreground mask resolution changed")
    resized = source.resize((GRID_WIDTH, GRID_HEIGHT), Image.Resampling.NEAREST)
    mask = np.asarray(resized) > 0
    return mask, {
        "source_size_width_height": list(source_size),
        "resized_size_width_height": [GRID_WIDTH, GRID_HEIGHT],
        "resampling": "PIL Image.Resampling.NEAREST (upstream WorldComposer load)",
        "foreground_pixels_after_resize": int(mask.sum()),
        "foreground_fraction_after_resize": float(mask.mean()),
        "selected_band_foreground_vertices": None,
    }


def crop_quad_mask_cuts(in_crop: np.ndarray, foreground: np.ndarray) -> dict:
    """Count mask-cut source quads and identify open notches vs enclosed holes."""
    crop = in_crop.reshape(GRID_HEIGHT, GRID_WIDTH)
    mask = foreground.reshape(GRID_HEIGHT, GRID_WIDTH)
    rows = np.flatnonzero(crop.any(axis=1))
    if len(rows) < 2:
        return {
            "eligible_crop_quads": 0,
            "mask_cut_quads": 0,
            "mask_cut_components": 0,
            "enclosed_mask_hole_components": 0,
        }
    first, last = max(int(rows[0]) - 1, 0), min(int(rows[-1]) + 1, GRID_HEIGHT - 1)
    crop_rows = crop[first : last + 1]
    mask_rows = mask[first : last + 1]
    eligible = (
        crop_rows[:-1, :-1]
        & crop_rows[:-1, 1:]
        & crop_rows[1:, :-1]
        & crop_rows[1:, 1:]
    )
    cut = eligible & (
        mask_rows[:-1, :-1]
        | mask_rows[:-1, 1:]
        | mask_rows[1:, :-1]
        | mask_rows[1:, 1:]
    )
    labelled, components = label(cut, structure=np.ones((3, 3), dtype=np.uint8))
    bounds = find_objects(labelled)
    eligible_rows, eligible_columns = np.nonzero(eligible)
    eligible_bounds = (
        [
            first + int(eligible_rows.min()),
            first + int(eligible_rows.max()),
            int(eligible_columns.min()),
            int(eligible_columns.max()),
        ]
        if len(eligible_rows)
        else None
    )
    component_records = []
    enclosed_components = 0
    for component, region in enumerate(bounds, start=1):
        if region is None:
            continue
        row_slice, column_slice = region
        component_mask = labelled == component
        touches_crop_boundary = _touches_crop_boundary(component_mask, eligible)
        enclosed_components += int(not touches_crop_boundary)
        component_records.append(
            {
                "quad_count": int((labelled[region] == component).sum()),
                "row_bounds_grid": [
                    first + row_slice.start,
                    first + row_slice.stop - 1,
                ],
                "column_bounds": [column_slice.start, column_slice.stop - 1],
                "touches_crop_boundary": touches_crop_boundary,
            }
        )
    return {
        "eligible_crop_quads": int(eligible.sum()),
        "mask_cut_quads": int(cut.sum()),
        "mask_cut_components_8_connected": int(components),
        "enclosed_mask_hole_components": enclosed_components,
        "eligible_crop_quad_bounds_grid": eligible_bounds,
        "mask_cut_component_bounds": component_records,
        "filled_or_bridged_mask_quads": 0,
    }


def _touches_crop_boundary(component: np.ndarray, eligible: np.ndarray) -> bool:
    """Check whether a cutout has an edge adjacent to unknown cropped cells."""
    padded = np.pad(eligible, 1, constant_values=False)
    neighbours = (
        padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    )
    return bool(np.any(component & ~neighbours))


def transform_points(
    local: np.ndarray, rotation: np.ndarray, translation: np.ndarray, scale: float
) -> np.ndarray:
    """Apply row-major local-to-world rotation and provisional uniform scale."""
    return translation + scale * (local @ rotation.T)


def path_distances(
    query_xz: np.ndarray, world_triangles: np.ndarray, candidate_limit: int = 64
) -> np.ndarray:
    """Measure nearest projected support triangle using local centroid candidates."""
    if len(world_triangles) == 0:
        return np.full(len(query_xz), np.inf, dtype=np.float64)
    triangles = world_triangles[:, :, [0, 2]]
    centroids = triangles.mean(axis=1)
    tree = cKDTree(centroids)
    candidate_count = min(candidate_limit, len(triangles))
    _, candidates = tree.query(query_xz, k=candidate_count)
    candidates = np.asarray(candidates).reshape(len(query_xz), candidate_count)
    distances = np.empty(len(query_xz), dtype=np.float64)
    for index, point in enumerate(query_xz):
        nearest = point_triangle_distance_2d(
            point[None, :], triangles[candidates[index]]
        )
        distances[index] = float(nearest.min())
    return distances


def write_obj(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    """Write a diagnostic mesh that cannot be mistaken for runtime collision."""
    with path.open("w", encoding="ascii") as handle:
        handle.write("# Experimental evidence only; not a collision asset.\n")
        handle.write("o hunyuan_forward_floor_band_not_collision\n")
        for x, y, z in vertices:
            handle.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for first, second, third in faces + 1:
            handle.write(f"f {first} {second} {third}\n")


def build() -> dict:
    """Filter run-05 base topology, report gaps, and measure camera proximity."""
    started = time.monotonic()
    vertex_offset, vertex_count, face_count = ply_layout(PLY_PATH)
    face_offset = vertex_offset + vertex_count * VERTEX_DTYPE.itemsize
    vertices_raw = np.memmap(
        PLY_PATH,
        mode="r",
        dtype=VERTEX_DTYPE,
        offset=vertex_offset,
        shape=(vertex_count,),
    )
    faces_raw = np.memmap(
        PLY_PATH, mode="r", dtype=FACE_DTYPE, offset=face_offset, shape=(face_count,)
    )
    if np.any(faces_raw["count"][:BASE_TRIANGLE_COUNT] != 3):
        raise ValueError("original Hunyuan sheet face range contains non-triangles")
    in_crop = panorama_vertex_selection(vertices_raw["x"], vertices_raw["y"])
    mask_grid, mask_record = resized_foreground_mask()
    foreground = mask_grid.reshape(-1)
    faces, face_selection = select_original_faces(
        faces_raw, in_crop, foreground, BASE_TRIANGLE_COUNT
    )
    mask_record["selected_band_foreground_vertices"] = int((in_crop & foreground).sum())
    mask_record["selected_band_vertices"] = int(in_crop.sum())
    mask_record["unmasked_band_vertices"] = int((in_crop & ~foreground).sum())
    mask_cuts = crop_quad_mask_cuts(in_crop, foreground)

    used, inverse = np.unique(faces.reshape(-1), return_inverse=True)
    selected_faces = inverse.reshape(-1, 3)
    local = np.column_stack(
        (vertices_raw["x"][used], vertices_raw["y"][used], vertices_raw["z"][used])
    )
    rotation, translation, scale, calibration = calibration_transform()
    world = transform_points(local, rotation, translation, scale)
    metrics = triangle_metrics(world, selected_faces)
    safe = filter_safe_faces(metrics)
    rejected = ~safe
    supported_faces = selected_faces[safe]
    supported_metrics = {key: value[safe] for key, value in metrics.items()}
    components = component_records(supported_faces, supported_metrics["area_m2"])
    supported_world_triangles = world[supported_faces]

    alignment = contract_from_path(ALIGNMENT_PATH)
    cameras_world = load_camera_centres(alignment, COLMAP_PATH, DATAPARSER_PATH)
    images = read_images(COLMAP_PATH)
    frame_index = next(
        index for index, image in enumerate(images) if image.name == "frame_0141.jpg"
    )
    anchor = np.asarray(
        calibration["registered_camera"]["camera_center_world_declared"]
    )
    if not np.allclose(cameras_world[frame_index], anchor, atol=1e-6):
        raise ValueError("frame-141 source camera does not match provisional anchor")
    distance_camera = path_distances(
        cameras_world[:, [0, 2]], supported_world_triangles
    )
    distance_camera_wide = path_distances(
        cameras_world[:, [0, 2]], supported_world_triangles, candidate_limit=256
    )
    distance_search_delta = float(
        np.max(np.abs(distance_camera - distance_camera_wide))
    )
    if distance_search_delta > 1e-8:
        raise ValueError(
            "nearest-support distances changed when search widened to 256 triangles"
        )
    distance_anchor = float(
        path_distances(anchor[None, [0, 2]], supported_world_triangles)[0]
    )
    frame_coverage = int((distance_camera <= 0.30).sum())

    bounds_min, bounds_max = world.min(axis=0), world.max(axis=0)
    slope = metrics["slope_degrees"]
    step = metrics["max_edge_vertical_step_m"]
    accepted_vertices, compact_inverse = np.unique(
        supported_faces.reshape(-1), return_inverse=True
    )
    output_vertices = world[accepted_vertices]
    output_faces = compact_inverse.reshape(-1, 3)
    write_obj(OUTPUT_MESH, output_vertices, output_faces)
    np.savez_compressed(
        OUTPUT_GRID,
        vertices_world_m=output_vertices.astype(np.float64),
        triangles=output_faces.astype(np.int32),
        status=np.asarray("evidence_only_not_collision"),
    )

    report = {
        "schema_version": 1,
        "issue": 135,
        "method": "run-05 layer-1 original panorama-grid forward floor-band triangles",
        "status": "experimental_hunyuan_patch_route_start_failed",
        "asset_status": "evidence_only_not_collision_not_runtime_imported",
        "gpu_used": False,
        "hunyuan_inference_run": False,
        "transform": {
            "kind": calibration["transform_kind"],
            "scale": scale,
            "scale_status": calibration["scale_status"],
            "scale_calibrated": False,
            "registration_accepted": False,
            "rotation_local_to_world_row_major": rotation.tolist(),
            "translation_world_declared": translation.tolist(),
            "frame_141_anchor_world_declared": anchor.tolist(),
            "camera_anchor_y_offset_from_declared_source_floor_m": float(
                anchor[1] - alignment.collider.floor_height
            ),
            "warning": "Convention-derived #134 scale only; not surveyed or approved for collision.",
        },
        "inputs": {
            "ply": str(PLY_PATH.relative_to(ROOT)),
            "ply_sha256": sha256_file(PLY_PATH),
            "mask": str(MASK_PATH.relative_to(ROOT)),
            "mask_sha256": sha256_file(MASK_PATH),
            "source_alignment_manifest_sha256": sha256_file(ALIGNMENT_PATH),
            "registered_source_camera_count": len(cameras_world),
            "frame_141_source_camera_index_in_colmap_order": frame_index,
            "source_frame_141_anchor_match": True,
        },
        "grid_and_selection": {
            "panorama_size_width_height": [GRID_WIDTH, GRID_HEIGHT],
            "original_layer_vertices": vertex_count,
            "original_layer_triangles": face_count,
            "original_regular_grid_triangles_including_panorama_seam": BASE_TRIANGLE_COUNT,
            "original_panorama_seam_triangles": 2 * (GRID_HEIGHT - 1),
            "nonseam_regular_grid_triangles": 2 * (GRID_HEIGHT - 1) * (GRID_WIDTH - 1),
            "appended_upstream_boundary_fill_faces_excluded": face_count
            - BASE_TRIANGLE_COUNT,
            "panorama_v_fraction_from_top_inclusive": [0.56, 0.62],
            "yaw_absolute_degrees_limit_from_local_minus_x": 35.0,
            "foreground_mask": mask_record,
            "foreground_mask_cuts": mask_cuts,
            "triangle_selection": face_selection,
            "seam_triangles_excluded_by_crop": True,
            "unknown_or_masked_faces_filled": 0,
        },
        "geometry_gate": {
            "max_slope_degrees": MAX_SLOPE_DEGREES,
            "max_vertical_edge_step_m": MAX_STEP_METRES,
            "triangle_count_before_gate": len(faces),
            "triangle_count_after_gate": len(supported_faces),
            "triangle_count_rejected": int(rejected.sum()),
            "degenerate_triangles_rejected": int((metrics["area_m2"] <= 1e-12).sum()),
            "slope_rejected_triangles": int((slope > MAX_SLOPE_DEGREES).sum()),
            "step_rejected_triangles": int((step > MAX_STEP_METRES).sum()),
            "slope_degrees_min_q50_q90_q95_q99_max": np.quantile(
                slope, [0, 0.50, 0.90, 0.95, 0.99, 1]
            ).tolist(),
            "max_edge_vertical_step_m_min_q50_q90_q95_q99_max": np.quantile(
                step, [0, 0.50, 0.90, 0.95, 0.99, 1]
            ).tolist(),
            "accepted_area_m2": float(supported_metrics["area_m2"].sum()),
            "accepted_triangle_winding": {
                "normal_world_y_positive": int(
                    (supported_metrics["normal_y"] > 1e-12).sum()
                ),
                "normal_world_y_negative": int(
                    (supported_metrics["normal_y"] < -1e-12).sum()
                ),
                "near_vertical_or_degenerate": int(
                    (np.abs(supported_metrics["normal_y"]) <= 1e-12).sum()
                ),
            },
        },
        "patch": {
            "connected_component_count": len(components),
            "largest_components_by_area": components[:10],
            "accepted_vertex_count": len(output_vertices),
            "accepted_triangle_count": len(output_faces),
            "candidate_world_bounds_min_xyz_m": bounds_min.tolist(),
            "candidate_world_bounds_max_xyz_m": bounds_max.tolist(),
            "file_obj": str(OUTPUT_MESH.relative_to(ROOT)),
            "file_npz": str(OUTPUT_GRID.relative_to(ROOT)),
        },
        "camera_path_proximity_not_traversal": {
            "metric": "nearest horizontal XZ distance from camera centre to projected accepted triangle",
            "capsule_radius_m": 0.30,
            "frame_141_anchor_nearest_support_xz_m": distance_anchor,
            "camera_samples_within_0_30m": frame_coverage,
            "camera_sample_count": len(cameras_world),
            "camera_nearest_support_xz_distance_q50_q90_q95_max_m": np.quantile(
                distance_camera, [0.50, 0.90, 0.95, 1.0]
            ).tolist(),
            "nearest_triangle_centroid_search": {
                "primary_candidates": 64,
                "comparison_candidates": 256,
                "max_abs_distance_difference_m": distance_search_delta,
            },
            "local_capsule_support_can_start_at_registered_camera": distance_anchor
            <= 0.30,
            "walkability_tested": False,
            "bevy_avian_physics_tested": False,
            "collision_glb_created": False,
        },
        "execution": {
            "elapsed_seconds": time.monotonic() - started,
            "peak_process_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
            "obj_bytes": OUTPUT_MESH.stat().st_size,
            "npz_bytes": OUTPUT_GRID.stat().st_size,
        },
        "failure_reason": (
            "No accepted support triangle lies within a 0.30 m horizontal capsule radius "
            "of the registered frame-141 camera anchor; calibration is also unaccepted. "
            "No route or walkability claim is supported."
        ),
    }
    OUTPUT_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
