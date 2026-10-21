"""Build separate early-pocket and authored-connector review assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ISSUE_DIR = Path(__file__).resolve().parent
ROOT = ISSUE_DIR.parents[3]
REFERENCE = ROOT / "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column"
sys.path.insert(0, str(REFERENCE))
sys.path.insert(0, str(ISSUE_DIR))

from early_pocket_assets import (  # noqa: E402
    ASSEMBLED_LOWER,
    ASSEMBLED_UPPER,
    DOOR_Z_BOUNDS,
    FLOOR_Y_M,
    LATER_BAY_LOWER,
    LATER_BAY_UPPER,
    POCKET_LOWER,
    POCKET_UPPER,
    WALL_HEIGHT_M,
    WALL_THICKNESS_M,
    assembled_collision_meshes,
    assembled_visual_boxes,
    interior_wall_boxes,
    interior_wall_meshes,
    standalone_collision_meshes,
    standalone_visual_boxes,
)
from early_pocket_geometry import merge_meshes, rectangle_floor, room_walk_loop  # noqa: E402
from collision_meshes import box_mesh  # noqa: E402
from glb_writer import build_glb  # noqa: E402

SOURCE_VIDEO = ROOT / "data/scenes/corridor_travel/video.mp4"
SOURCE_IMAGES = ROOT / "data/scenes/corridor_travel/images"
INVENTORY = ROOT / "godot_walk/evidence/2026-10-18-issue-145/ROOM_CATALOG.md"
CAMERA_PATH = ROOT / "godot_walk/evidence/2026-10-18-issue-145/camera_path.csv"
SOURCE_FRAME_IDS = (13, 17, 25, 27)
VISUAL_PATHS = ("mesh_layer0", "mesh_layer1")
ROOM_BOUNDARY_NAMES = (
    "authored_room_boundary_west",
    "authored_room_boundary_east",
    "authored_room_boundary_south",
    "authored_room_boundary_north",
)
ASSEMBLY_PATH = (
    (2.0, 4.0), (4.0, 4.0), (5.0, 4.0), (7.5, 4.0), (9.0, 4.0),
    (12.0, 4.0), (12.0, 6.5), (9.0, 6.5), (9.0, 4.0), (7.5, 4.0),
    (5.0, 4.0), (4.0, 4.0),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def write_json(path: Path, value: dict, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing #148 output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def source_frames() -> list[dict]:
    return [
        {
            "frame_id": frame_id,
            "zero_based_index": frame_id - 1,
            "timestamp_seconds": (frame_id - 1) / 24,
            "image": {
                "path": f"data/scenes/corridor_travel/images/frame_{frame_id:04}.jpg",
                "sha256": file_digest(SOURCE_IMAGES / f"frame_{frame_id:04}.jpg"),
            },
            "usage": "Direct #100 frame; visual context for the observed opening and nearby partition. It does not establish a separate room, route, scale or connection.",
        }
        for frame_id in SOURCE_FRAME_IDS
    ]


def visual_glb(bounds: tuple[tuple[float, float], tuple[float, float]], extras: dict) -> bytes:
    lower, upper = bounds
    floor = rectangle_floor(lower, upper, FLOOR_Y_M - 0.04)
    ceiling = rectangle_floor(lower, upper, FLOOR_Y_M + WALL_HEIGHT_M + 0.04)
    return build_glb(
        [
            {"name": VISUAL_PATHS[0], "vertices": floor[0], "faces": floor[1]},
            {"name": VISUAL_PATHS[1], "vertices": ceiling[0], "faces": ceiling[1]},
        ],
        extras,
    )


def named_collision_meshes(values: dict[str, tuple[np.ndarray, np.ndarray]]) -> list[dict]:
    names = {
        "floor": "AuthoredPlanarRouteFloor",
        "column": "ColumnObstacleProxy",
        "interior": "AuthoredRoomInteriorBoundaries",
    }
    names.update({name: name for name in ROOM_BOUNDARY_NAMES})
    return [{"name": names[key], "vertices": mesh[0], "faces": mesh[1]} for key, mesh in values.items()]


def path_samples(points: tuple[tuple[float, float], ...]) -> list[list[float]]:
    samples: list[list[float]] = []
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        count = max(2, math.ceil(math.dist(start, end) / 0.2))
        samples.extend(
            [
                [start[0] + (end[0] - start[0]) * step / count,
                 start[1] + (end[1] - start[1]) * step / count]
                for step in range(count)
            ]
        )
    return samples


def closed_path_length(points: list[list[float]]) -> float:
    return sum(math.dist(points[index], points[(index + 1) % len(points)]) for index in range(len(points)))


def route_report(
    file_name: str,
    glb: bytes,
    values: dict[str, tuple[np.ndarray, np.ndarray]],
    bounds: tuple[tuple[float, float], tuple[float, float]],
    points: list[list[float]],
    visual_boxes: list[dict],
    status: str,
) -> dict:
    lower, upper = bounds
    center = [(lower[0] + upper[0]) / 2, (lower[1] + upper[1]) / 2]
    boundary_triangles = [len(values[name][1]) for name in ROOM_BOUNDARY_NAMES]
    interior_triangles = len(values.get("interior", (np.empty((0, 3)), np.empty((0, 3))))[1])
    export = {
        "path": file_name,
        "sha256": digest(glb),
        "bytes": len(glb),
        "floor_triangles": len(values["floor"][1]),
        "column_triangles": len(values.get("column", (np.empty((0, 3)), np.empty((0, 3))))[1]),
        "inner_edge_boundary_triangles": 0,
        "outer_edge_boundary_triangles": sum(boundary_triangles) + interior_triangles,
        "room_boundary_triangles": boundary_triangles,
        "mesh_names": [mesh["name"] for mesh in named_collision_meshes(values)],
        "node_transform": "identity; authored geometry uses an uncalibrated design convention",
    }
    report = {
        "schema_version": 1,
        "issue": 148,
        "status": status,
        "gpu_used": False,
        "metric_scale_accepted": False,
        "hunyuan_registration_accepted": False,
        "plane": {"height_m": FLOOR_Y_M, "basis": "reused #100 convention; not surveyed"},
        "route": {
            "kind": "authored_module_or_connector_loop",
            "center_xz_m": center,
            "radius_m": 0.0,
            "width_m": 0.0,
            "closed_path_length_m": closed_path_length(points),
            "centerline_samples": len(points),
            "geometry_origin": "authored design; not recovered from video",
        },
        "column_obstacle": {
            "footprint_lower_xz_m": [-1.2568561533613571, -0.7415601043662503] if "column" in values else [0.0, 0.0],
            "footprint_upper_xz_m": [0.36192645011758046, 1.3885216998149807] if "column" in values else [0.0, 0.0],
            "height_m": WALL_HEIGHT_M if "column" in values else 0.0,
            "basis": "#150 authored column proxy retained only in the assembled candidate" if "column" in values else "No column is added to the standalone early-pocket module.",
            "metric_scale_accepted": False,
        },
        "edge_boundaries": {
            "height_m": WALL_HEIGHT_M,
            "thickness_m": WALL_THICKNESS_M,
            "origin": "authored visible shell and collision; not reconstructed",
        },
        "room_layout": {
            "bounds_lower_xz_m": list(lower),
            "bounds_upper_xz_m": list(upper),
            "boundary_height_m": WALL_HEIGHT_M,
            "boundary_thickness_m": WALL_THICKNESS_M,
            "walk_loop_centerline_xz_m": points,
            "boundary_triangles": boundary_triangles,
            "interior_boundary_triangles": interior_triangles,
            "geometry_origin": "authored design proposal; footprint and registration remain unaccepted",
            "visual_boxes": visual_boxes,
        },
        "export": export,
    }
    return report


def camera_pose(name: str, position: tuple[float, float, float], forward: tuple[float, float, float]) -> dict:
    return {
        "name": name,
        "position_world_m": list(position),
        "forward_world": list(forward),
        "up_world": [0.0, 1.0, 0.0],
    }


def capture_poses(standalone: bool) -> dict:
    camera_y = 0.0
    if standalone:
        poses = [
            camera_pose("pocket_entry", (1.0, camera_y, 6.9), (1.0, 0.0, 0.0)),
            camera_pose("pocket_center", (3.0, camera_y, 6.9), (0.0, 0.0, 1.0)),
            camera_pose("pocket_far_end", (3.0, camera_y, 12.3), (0.0, 0.0, -1.0)),
            camera_pose("pocket_west_wall", (0.8, camera_y, 3.0), (1.0, 0.0, 0.0)),
            camera_pose("pocket_east_wall", (5.2, camera_y, 3.0), (-1.0, 0.0, 0.0)),
            camera_pose("pocket_north_wall", (3.0, camera_y, 12.0), (0.0, 0.0, -1.0)),
        ]
    else:
        poses = [
            camera_pose("later_bay_approach", (2.0, camera_y, 4.0), (1.0, 0.0, 0.0)),
            camera_pose("doorway_from_later_bay", (3.4, camera_y, 4.0), (1.0, 0.0, 0.0)),
            camera_pose("connector_midpoint", (6.2, camera_y, 4.0), (1.0, 0.0, 0.0)),
            camera_pose("pocket_entry", (8.7, camera_y, 4.0), (1.0, 0.0, 0.0)),
            camera_pose("pocket_far_end", (13.0, camera_y, 4.0), (-1.0, 0.0, 0.0)),
            camera_pose("pocket_return", (10.0, camera_y, 1.0), (0.0, 0.0, 1.0)),
            camera_pose("column_to_connector", (0.0, camera_y, 1.9), (1.0, 0.0, 0.0)),
            camera_pose("connector_return", (6.2, camera_y, 4.0), (-1.0, 0.0, 0.0)),
        ]
    return {
        "issue": 148,
        "label": "uncalibrated",
        "registration_accepted": False,
        "scale_calibrated": False,
        "resolution": [960, 540],
        "vertical_fov_degrees": 47.3988056,
        "settle_frames_before_each_capture": 8,
        "pose_set": "authored review views, not registered to source video",
        "poses": poses,
    }


def scene_manifest(scene_name: str, visual: Path, collision: Path, report: Path, poses: Path, camera: Path) -> dict:
    def record(path: Path) -> dict:
        return {"path": str(path.relative_to(ROOT)), "sha256": file_digest(path)}

    evidence = [record(SOURCE_VIDEO), *(record(SOURCE_IMAGES / f"frame_{frame:04}.jpg") for frame in SOURCE_FRAME_IDS), record(INVENTORY), record(CAMERA_PATH)]
    floor_y = FLOOR_Y_M
    return {
        "schema_version": 1,
        "issue": 148,
        "label": "uncalibrated",
        "status": scene_name,
        "registration_accepted": False,
        "scale_calibrated": False,
        "transform": {
            "transform_status": "uncalibrated_convention",
            "scale_m_per_hunyuan_unit": 1.0,
            "scale_basis": "authored convention-unit geometry; not surveyed or calibrated",
            "scale_sensitivity_range_m_per_hunyuan_unit": [0.999, 1.001],
            "local_axis_mapping": "authored Bevy world axes; no Hunyuan registration",
            "camera_anchor_world_m": [0.0, 0.0, 0.0],
            "plane_aligned_translation_world_m": [0.0, 0.0, 0.0],
            "camera_anchor_shift_y_m": 0.0,
            "declared_collision_floor_y_m": floor_y,
            "note": "Review transform is identity for authored geometry. No source registration or metric calibration is claimed.",
        },
        "assets": {
            "visual": {**record(visual), "role": "authored visual-only mesh layers; never collision"},
            "collision": {**record(collision), "role": "separate authored collision geometry"},
            "camera_metadata": record(camera),
        },
        "source_evidence": evidence,
        "route_report_path": str(report.relative_to(ROOT)),
        "route_report_sha256": file_digest(report),
        "output_report_path": str((report.parent / f"{scene_name}_scene_report.json").relative_to(ROOT)),
        "capture_poses_path": str(poses.relative_to(ROOT)),
        "capture_poses_sha256": file_digest(poses),
        "capture_output_path": str((report.parent / f"captures/{scene_name}").relative_to(ROOT)),
        "locked_traversal_gate": {
            "source": "#148 authored standalone or connector route gate",
            "outbound_progress_fraction_min": 1.0,
            "inbound_progress_fraction_min": 0.992,
            "moving_support_fraction_min": 0.993,
            "safety_net_contacts_max": 0,
            "max_vertical_step_m": 0.2,
            "comparison_rule": "walk the authored route both ways with floor support and no SafetyNet contacts; geometry is a design proposal, not recovered connectivity",
        },
    }


def glb_for(values: dict[str, tuple[np.ndarray, np.ndarray]], details: dict) -> bytes:
    return build_glb(
        named_collision_meshes(values),
        {
            "issue": 148,
            "geometry_origin": "authored_not_reconstructed",
            "metric_scale_accepted": False,
            "hunyuan_registration_accepted": False,
            **details,
        },
    )


def write_asset(path: Path, content: bytes, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing #148 output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def build_layout_svg(path: Path, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"refusing to overwrite existing #148 output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LAYOUT_SVG, encoding="utf-8")


LAYOUT_SVG = """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1080\" height=\"650\" viewBox=\"0 0 1080 650\">
<rect width=\"1080\" height=\"650\" fill=\"#f4f2ea\"/><text x=\"32\" y=\"42\" font-family=\"sans-serif\" font-size=\"24\" font-weight=\"700\">#148 authored assembly proposal</text>
<text x=\"32\" y=\"70\" font-family=\"sans-serif\" font-size=\"14\">Plan view only. Positions and connector are game-design choices, not recovered video layout.</text>
<rect x=\"100\" y=\"155\" width=\"490\" height=\"350\" fill=\"#d1c17f\" stroke=\"#35352e\" stroke-width=\"5\"/><text x=\"140\" y=\"205\" font-family=\"sans-serif\" font-size=\"20\">#150 later-bay baseline</text>
<rect x=\"590\" y=\"255\" width=\"175\" height=\"90\" fill=\"#c7c39b\" stroke=\"#9b482f\" stroke-width=\"4\" stroke-dasharray=\"9 7\"/><text x=\"610\" y=\"305\" font-family=\"sans-serif\" font-size=\"16\">authored hall</text>
<rect x=\"765\" y=\"155\" width=\"295\" height=\"350\" fill=\"#c5ce8c\" stroke=\"#35352e\" stroke-width=\"5\"/><text x=\"795\" y=\"205\" font-family=\"sans-serif\" font-size=\"20\">early-pocket module</text>
<line x1=\"590\" y1=\"300\" x2=\"765\" y2=\"300\" stroke=\"#9b482f\" stroke-width=\"9\"/><text x=\"610\" y=\"370\" font-family=\"sans-serif\" font-size=\"13\">2.4 m authored clearance</text>
<rect x=\"275\" y=\"295\" width=\"65\" height=\"75\" fill=\"#b9ac78\" stroke=\"#554e39\" stroke-width=\"3\"/><text x=\"249\" y=\"395\" font-family=\"sans-serif\" font-size=\"13\">existing #150 column</text>
<text x=\"100\" y=\"545\" font-family=\"sans-serif\" font-size=\"15\">Source evidence: #145 opening candidate C, frames 0013-0027. The camera does not establish threshold traversal.</text>
<text x=\"100\" y=\"575\" font-family=\"sans-serif\" font-size=\"15\">The pocket is a new authored room proposal; its location, size, hallway, and connector are not source facts.</text></svg>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args()
    generated = ISSUE_DIR / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    build_standalone(generated, args.replace_generated)
    build_assembly(generated, args.replace_generated)
    build_negative_controls(generated / "negative_controls", args.replace_generated)
    build_layout_svg(ISSUE_DIR / "authored_assembly_layout.svg", args.replace_generated)


def build_standalone(output: Path, replace: bool) -> None:
    values = standalone_collision_meshes()
    glb = glb_for(values, {"asset_status": "authored_early_pocket_standalone"})
    collision = output / "early_pocket_collision.glb"
    visual = output / "early_pocket_visual.glb"
    write_asset(collision, glb, replace)
    write_asset(visual, visual_glb((POCKET_LOWER, POCKET_UPPER), {"asset_status": "authored_early_pocket_visual"}), replace)
    points = room_walk_loop(POCKET_LOWER, POCKET_UPPER)
    report = route_report(collision.name, glb, values, (POCKET_LOWER, POCKET_UPPER), points, standalone_visual_boxes(), "authored_early_pocket_standalone")
    write_json(output / "early_pocket_route_report.json", report, replace)
    write_capture_metadata(output, "early_pocket", visual, collision, output / "early_pocket_route_report.json", True, replace)


def build_assembly(output: Path, replace: bool) -> None:
    later_report_path = ROOT / "godot_walk/evidence/2026-10-20-issue-150/route_report.json"
    later_report = json.loads(later_report_path.read_text(encoding="utf-8"))
    column = later_report["column_obstacle"]
    column_bounds = (tuple(column["footprint_lower_xz_m"]), tuple(column["footprint_upper_xz_m"]))
    values = assembled_collision_meshes(column_bounds)
    glb = glb_for(values, {"asset_status": "authored_early_pocket_connector_adaptation"})
    collision = output / "assembled_connector_collision.glb"
    visual = output / "assembled_review_visual.glb"
    write_asset(collision, glb, replace)
    write_asset(visual, visual_glb((ASSEMBLED_LOWER, ASSEMBLED_UPPER), {"asset_status": "authored_connector_review_visual"}), replace)
    points = path_samples(ASSEMBLY_PATH)
    visuals = assembled_visual_boxes(column_bounds)
    report = route_report(collision.name, glb, values, (ASSEMBLED_LOWER, ASSEMBLED_UPPER), points, visuals, "authored_connector_candidate")
    write_json(output / "assembled_route_report.json", report, replace)
    write_capture_metadata(output, "assembled_connector", visual, collision, output / "assembled_route_report.json", False, replace)


def write_capture_metadata(output: Path, name: str, visual: Path, collision: Path, report: Path, standalone: bool, replace: bool) -> None:
    poses_path = output / f"{name}_capture_poses.json"
    camera_path = output / f"{name}_camera_metadata.json"
    write_json(poses_path, capture_poses(standalone), replace)
    camera = {
        "camera": {
            "camera_center_godot_world_m": [0.0, 0.0, 0.0],
            "forward_godot_world": [-1.0, 0.0, 0.0],
            "up_godot_world": [0.0, 0.0, 1.0],
            "origin": "authored review camera; not a registered source camera",
        }
    }
    write_json(camera_path, camera, replace)
    manifest_path = ISSUE_DIR / "standalone_scene_manifest.json" if standalone else ISSUE_DIR / "module_manifest.json"
    write_json(manifest_path, scene_manifest(name, visual, collision, report, poses_path, camera_path), replace)


def build_negative_controls(output: Path, replace: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    later_report = json.loads((ROOT / "godot_walk/evidence/2026-10-20-issue-150/route_report.json").read_text(encoding="utf-8"))
    column = later_report["column_obstacle"]
    column_bounds = (tuple(column["footprint_lower_xz_m"]), tuple(column["footprint_upper_xz_m"]))
    controls = {
        "blocked_entry": assembled_collision_meshes(column_bounds),
        "missing_connector_floor": assembled_collision_meshes(column_bounds),
    }
    blocked_mesh = box_mesh(np.asarray((4.5 - WALL_THICKNESS_M / 2, DOOR_Z_BOUNDS[0])), np.asarray((4.5 + WALL_THICKNESS_M / 2, DOOR_Z_BOUNDS[1])), FLOOR_Y_M, WALL_HEIGHT_M)
    controls["blocked_entry"]["interior"] = merge_meshes([*interior_wall_meshes(), blocked_mesh])
    floor_patches = [
        rectangle_floor(LATER_BAY_LOWER, LATER_BAY_UPPER, FLOOR_Y_M),
        rectangle_floor((8.0, -5.0), ASSEMBLED_UPPER, FLOOR_Y_M),
    ]
    controls["missing_connector_floor"]["floor"] = merge_meshes(floor_patches)
    for control, meshes in controls.items():
        relative = f"{control}.glb"
        glb = glb_for(meshes, {"negative_control": control})
        write_asset(output / f"{control}.glb", glb, replace)
        points = path_samples(ASSEMBLY_PATH)
        report = route_report(relative, glb, meshes, (ASSEMBLED_LOWER, ASSEMBLED_UPPER), points, assembled_visual_boxes(column_bounds), f"negative_control_{control}")
        report_path = output / f"{control}_route_report.json"
        write_json(report_path, report, replace)


if __name__ == "__main__":
    main()
