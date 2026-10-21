"""Build the CPU-only authored #150 room shell and its review manifests."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ISSUE_DIR = Path(__file__).resolve().parent
ROOT = ISSUE_DIR.parents[2]
REFERENCE = ROOT / "godot_walk/evidence/2026-10-13-hunyuan-track-a/collision_proto/authored_route_around_column"
SOURCE_MANIFEST = ROOT / "godot_walk/evidence/2026-10-20-issue-147/module_manifest.json"
sys.path.insert(0, str(REFERENCE))

from collision_meshes import box_mesh  # noqa: E402
from glb_writer import build_glb  # noqa: E402

OUTPUT_GLB = ISSUE_DIR / "authored_room_collision.glb"
OUTPUT_REPORT = ISSUE_DIR / "route_report.json"
OUTPUT_MANIFEST = ISSUE_DIR / "module_manifest.json"
OUTPUT_POSES = ISSUE_DIR / "capture_poses.json"
FLOOR_Y_M = -1.2709904909133911
ROOM_LOWER_XZ_M = (-5.4, -5.0)
ROOM_UPPER_XZ_M = (4.5, 8.8)
ROOM_WALL_HEIGHT_M = 2.4
ROOM_WALL_THICKNESS_M = 0.12
COLUMN_LOWER_XZ_M = (-1.2568561533613571, -0.7415601043662503)
COLUMN_UPPER_XZ_M = (0.36192645011758046, 1.3885216998149807)
COLUMN_HEIGHT_M = 2.4
WALK_MARGIN_M = 0.85
BOUNDARY_NAMES = (
    "authored_room_boundary_west",
    "authored_room_boundary_east",
    "authored_room_boundary_south",
    "authored_room_boundary_north",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def floor_mesh() -> tuple[np.ndarray, np.ndarray]:
    x0, z0 = ROOM_LOWER_XZ_M
    x1, z1 = ROOM_UPPER_XZ_M
    vertices = np.asarray([(x0, FLOOR_Y_M, z0), (x0, FLOOR_Y_M, z1), (x1, FLOOR_Y_M, z1), (x1, FLOOR_Y_M, z0)], dtype=np.float32)
    faces = np.asarray([(0, 1, 2), (0, 2, 3)], dtype=np.uint32)
    return vertices, faces


def wall_meshes() -> list[tuple[str, tuple[np.ndarray, np.ndarray]]]:
    lower = np.asarray(ROOM_LOWER_XZ_M, dtype=np.float32)
    upper = np.asarray(ROOM_UPPER_XZ_M, dtype=np.float32)
    x0, z0 = lower
    x1, z1 = upper
    t = ROOM_WALL_THICKNESS_M
    boxes = (
        (BOUNDARY_NAMES[0], [x0 - t, z0 - t], [x0, z1 + t]),
        (BOUNDARY_NAMES[1], [x1, z0 - t], [x1 + t, z1 + t]),
        (BOUNDARY_NAMES[2], [x0, z0 - t], [x1, z0]),
        (BOUNDARY_NAMES[3], [x0, z1], [x1, z1 + t]),
    )
    return [(name, box_mesh(np.asarray(box_lower), np.asarray(box_upper), FLOOR_Y_M, ROOM_WALL_HEIGHT_M)) for name, box_lower, box_upper in boxes]


def meshes() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    result = {"floor": floor_mesh()}
    result["column"] = box_mesh(np.asarray(COLUMN_LOWER_XZ_M), np.asarray(COLUMN_UPPER_XZ_M), FLOOR_Y_M, COLUMN_HEIGHT_M)
    result.update({name: mesh for name, mesh in wall_meshes()})
    return result


def walk_loop() -> list[list[float]]:
    x0, z0 = ROOM_LOWER_XZ_M
    x1, z1 = ROOM_UPPER_XZ_M
    margin = WALK_MARGIN_M
    corners = [(x0 + margin, z0 + margin), (x1 - margin, z0 + margin), (x1 - margin, z1 - margin), (x0 + margin, z1 - margin)]
    points: list[list[float]] = []
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        segments = max(2, math.ceil(math.dist(start, end) / 0.2))
        points.extend([[start[0] + (end[0] - start[0]) * step / segments, start[1] + (end[1] - start[1]) * step / segments] for step in range(segments)])
    return points


def named_meshes(values: dict[str, tuple[np.ndarray, np.ndarray]]) -> list[dict]:
    names = {"floor": "AuthoredPlanarRouteFloor", "column": "ColumnObstacleProxy"}
    names.update({key: key for key in BOUNDARY_NAMES})
    return [{"name": names[key], "vertices": value[0], "faces": value[1]} for key, value in values.items()]


def route_report(values: dict[str, tuple[np.ndarray, np.ndarray]], glb: bytes) -> dict:
    lower = np.asarray(ROOM_LOWER_XZ_M)
    upper = np.asarray(ROOM_UPPER_XZ_M)
    center = ((lower + upper) * 0.5).tolist()
    loop = walk_loop()
    length = sum(math.dist(loop[index], loop[(index + 1) % len(loop)]) for index in range(len(loop)))
    triangles = {name: len(mesh[1]) for name, mesh in values.items()}
    return {
        "schema_version": 1,
        "issue": 150,
        "status": "operator_accepted_standalone_design_baseline",
        "gpu_used": False,
        "metric_scale_accepted": False,
        "hunyuan_registration_accepted": False,
        "plane": {"height_m": FLOOR_Y_M, "basis": "reused #100 convention; not surveyed"},
        "route": {"kind": "authored_rectangular_room_perimeter_loop", "center_xz_m": center, "radius_m": 0.0, "width_m": 0.0, "closed_path_length_m": length, "centerline_samples": len(loop), "geometry_origin": "authored proposal; not recovered from video"},
        "room_layout": {"bounds_lower_xz_m": list(ROOM_LOWER_XZ_M), "bounds_upper_xz_m": list(ROOM_UPPER_XZ_M), "boundary_height_m": ROOM_WALL_HEIGHT_M, "boundary_thickness_m": ROOM_WALL_THICKNESS_M, "walk_loop_centerline_xz_m": loop, "boundary_triangles": [triangles.get(name, 0) for name in BOUNDARY_NAMES], "geometry_origin": "authored proposal; registration and scale remain unaccepted"},
        "column_obstacle": {"footprint_lower_xz_m": list(COLUMN_LOWER_XZ_M), "footprint_upper_xz_m": list(COLUMN_UPPER_XZ_M), "height_m": COLUMN_HEIGHT_M, "basis": "reused conservative authored proxy from #135 frames 0137 and 0141", "metric_scale_accepted": False},
        "edge_boundaries": {"height_m": ROOM_WALL_HEIGHT_M, "thickness_m": ROOM_WALL_THICKNESS_M, "origin": "authored visible room shell and collision; not reconstructed"},
        "export": {"path": OUTPUT_GLB.name, "sha256": sha256(glb), "bytes": len(glb), "floor_triangles": triangles.get("floor", 0), "column_triangles": triangles.get("column", 0), "inner_edge_boundary_triangles": 0, "outer_edge_boundary_triangles": sum(triangles.get(name, 0) for name in BOUNDARY_NAMES), "room_boundary_triangles": [triangles.get(name, 0) for name in BOUNDARY_NAMES], "mesh_names": [mesh["name"] for mesh in named_meshes(values)], "node_transform": "identity; authored vertices use the uncalibrated #100 convention"},
    }


def camera_pose(name: str, position: tuple[float, float, float], forward: tuple[float, float, float]) -> dict:
    return {"name": name, "position_world_m": list(position), "forward_world": list(forward), "up_world": [0.0, 1.0, 0.0]}


def capture_poses() -> dict:
    x0, z0 = ROOM_LOWER_XZ_M
    x1, z1 = ROOM_UPPER_XZ_M
    cx, cz = (x0 + x1) * 0.5, (z0 + z1) * 0.5
    camera_y = -0.100279711
    col_x = (COLUMN_LOWER_XZ_M[0] + COLUMN_UPPER_XZ_M[0]) * 0.5
    col_z = (COLUMN_LOWER_XZ_M[1] + COLUMN_UPPER_XZ_M[1]) * 0.5
    return {"issue": 150, "label": "uncalibrated", "registration_accepted": False, "scale_calibrated": False, "resolution": [960, 540], "vertical_fov_degrees": 47.3988056, "settle_frames_before_each_capture": 8, "pose_set": "four authored room-end views, four authored column-face views, and the frame-0152 camera anchor", "poses": [
        camera_pose("south_room_end", (cx, camera_y, z0 + 1.0), (0.0, 0.0, 1.0)),
        camera_pose("north_room_end", (cx, camera_y, z1 - 1.0), (0.0, 0.0, -1.0)),
        camera_pose("west_room_end", (x0 + 1.0, camera_y, cz), (1.0, 0.0, 0.0)),
        camera_pose("east_room_end", (x1 - 1.0, camera_y, cz), (-1.0, 0.0, 0.0)),
        camera_pose("column_south_face", (col_x, camera_y, COLUMN_LOWER_XZ_M[1] - 2.0), (0.0, 0.0, 1.0)),
        camera_pose("column_north_face", (col_x, camera_y, COLUMN_UPPER_XZ_M[1] + 2.0), (0.0, 0.0, -1.0)),
        camera_pose("column_west_face", (COLUMN_LOWER_XZ_M[0] - 2.0, camera_y, col_z), (1.0, 0.0, 0.0)),
        camera_pose("column_east_face", (COLUMN_UPPER_XZ_M[0] + 2.0, camera_y, col_z), (-1.0, 0.0, 0.0)),
        camera_pose("registered_frame_0152_anchor", (2.920978333, -0.084976566, 3.703507945), (-0.690928499, 0.00022245, -0.722923066)),
    ]}


def module_manifest(report: dict, poses: dict) -> dict:
    base = json.loads(SOURCE_MANIFEST.read_text())
    manifest = copy.deepcopy(base)
    manifest.update({"issue": 150, "status": "operator_accepted_standalone_design_baseline"})
    manifest["assets"]["collision"] = {"path": f"{ISSUE_DIR.relative_to(ROOT)}/{OUTPUT_GLB.name}", "sha256": report["export"]["sha256"], "nodes": report["export"]["mesh_names"], "role": "explicit authored room floor, column obstacle, and four visible end boundaries; physics only"}
    manifest.update({"route_report_path": f"{ISSUE_DIR.relative_to(ROOT)}/{OUTPUT_REPORT.name}", "route_report_sha256": sha256(json.dumps(report, indent=2).encode() + b"\n"), "output_report_path": f"{ISSUE_DIR.relative_to(ROOT)}/hunyuan_route_scene_report.json", "capture_poses_path": f"{ISSUE_DIR.relative_to(ROOT)}/{OUTPUT_POSES.name}", "capture_poses_sha256": sha256(json.dumps(poses, indent=2).encode() + b"\n"), "capture_output_path": f"{ISSUE_DIR.relative_to(ROOT)}/captures/bevy"})
    manifest["locked_traversal_gate"]["source"] = "#150 authored room-end perimeter traversal gate"
    manifest["locked_traversal_gate"]["comparison_rule"] = "standalone authored room perimeter must pass with continuous support and four explicit boundaries; no connector or registration claim"
    return manifest


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-control", choices=("missing_floor", "missing_column", "missing_boundaries"))
    parser.add_argument("--replace-generated", action="store_true")
    args = parser.parse_args()
    control = args.negative_control or ""
    output_dir = ISSUE_DIR / "negative_controls" if control else ISSUE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    meshes_to_export = meshes()
    omitted = {"missing_floor": ("floor",), "missing_column": ("column",), "missing_boundaries": BOUNDARY_NAMES}.get(control, ())
    for name in omitted:
        meshes_to_export.pop(name)
    glb = build_glb(named_meshes(meshes_to_export), {"issue": 150, "asset_status": "negative_control" if control else "authored_room_candidate", "metric_scale_accepted": False, "hunyuan_registration_accepted": False, "geometry_origin": "authored_not_reconstructed", "negative_control": control or None})
    if control:
        glb_path = output_dir / f"{control}.glb"
        report_path = output_dir / f"{control}_route_report.json"
        if (glb_path.exists() or report_path.exists()) and not args.replace_generated:
            raise FileExistsError("refusing to overwrite an existing #150 negative control")
        report = route_report(meshes_to_export, glb)
        report["status"] = "negative_control"
        report["negative_control"] = control
        report["export"]["path"] = glb_path.name
        glb_path.write_bytes(glb)
        write_json(report_path, report)
        print(f"wrote negative control {control}: {glb_path}")
        return
    for path in (OUTPUT_GLB, OUTPUT_REPORT, OUTPUT_MANIFEST, OUTPUT_POSES):
        if path.exists() and not args.replace_generated:
            raise FileExistsError(f"refusing to overwrite existing #150 output: {path}")
    report = route_report(meshes_to_export, glb)
    poses = capture_poses()
    OUTPUT_GLB.write_bytes(glb)
    write_json(OUTPUT_REPORT, report)
    write_json(OUTPUT_POSES, poses)
    write_json(OUTPUT_MANIFEST, module_manifest(report, poses))
    print(json.dumps(report["export"], indent=2))


if __name__ == "__main__":
    main()
