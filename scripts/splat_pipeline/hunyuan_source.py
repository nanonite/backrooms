"""Source-frame metadata and extraction for the HunyuanWorld experiment."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np

import colmap_model
import measure_splat_frame
import view_support
from splat_frame import FrameContract

EXPECTED_VIDEO_SHA256 = "ac5cd0d1aa11aadd39cc45ff460af5e00372f8417d2514fce1bfa7c7837895c4"
HUNYUAN_COMMIT = "57fa9f3a79eae1079c279968cdb9d82c75fa7c86"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
            "-show_entries", "format=duration", "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    return {**data["streams"][0], "duration_seconds": float(data["format"]["duration"])}


def fov_degrees(sensor_pixels: int, focal_pixels: float) -> float:
    if sensor_pixels <= 0 or not math.isfinite(focal_pixels) or focal_pixels <= 0:
        raise ValueError("sensor size and focal length must be positive and finite")
    return math.degrees(2.0 * math.atan(sensor_pixels / (2.0 * focal_pixels)))


def focal_lengths(camera: colmap_model.Camera) -> tuple[float, float]:
    if camera.model == "SIMPLE_RADIAL":
        return camera.params[0], camera.params[0]
    if camera.model == "PINHOLE":
        return camera.params[0], camera.params[1]
    raise ValueError("unsupported COLMAP camera model: %s" % camera.model)


def selected_image(images: list, frame_number: int) -> colmap_model.RegisteredImage:
    expected_name = "frame_%04d.jpg" % frame_number
    matches = [image for image in images if Path(image.name).name == expected_name]
    if len(matches) != 1:
        raise ValueError("frame is not uniquely registered in COLMAP: %s" % expected_name)
    return matches[0]


def target_projection(image, camera, target_world, contract, dataparser) -> dict:
    target_colmap = view_support.world_to_colmap(
        np.asarray(target_world, dtype=np.float64).reshape(1, 3),
        contract.ply_to_world,
        dataparser,
    )[0]
    target_camera = image.rotation_w2c @ target_colmap + image.translation_w2c
    pixels_x, pixels_y = view_support._project(target_camera.reshape(1, 3), camera)
    x, y = float(pixels_x[0]), float(pixels_y[0])
    return {
        "camera_depth_m": float(target_camera[2]),
        "pixel": [x, y],
        "normalized_center_offset": math.hypot(
            (x - camera.width / 2) / (camera.width / 2),
            (y - camera.height / 2) / (camera.height / 2),
        ),
        "inside_image": 0 <= x < camera.width and 0 <= y < camera.height,
    }


def camera_orientation_world(image, contract, dataparser) -> tuple[np.ndarray, np.ndarray]:
    rotation_w2c = image.rotation_w2c
    forward_colmap = rotation_w2c.T @ np.array([0.0, 0.0, 1.0])
    up_colmap = rotation_w2c.T @ np.array([0.0, -1.0, 0.0])
    rotation_colmap_to_ply = dataparser["rotation"]
    scale = dataparser["scale"]
    forward_ply = rotation_colmap_to_ply @ forward_colmap * scale
    up_ply = rotation_colmap_to_ply @ up_colmap * scale
    forward_world = contract.ply_to_world.world_vector(forward_ply)
    up_world = contract.ply_to_world.world_vector(up_ply)
    return forward_world / np.linalg.norm(forward_world), up_world / np.linalg.norm(up_world)


def inspect_registered_camera(args, registered_count: int) -> tuple:
    images = colmap_model.read_images(args.colmap_model)
    if len(images) != registered_count:
        raise ValueError("registered image count does not match the expected #100 model")
    image = selected_image(images, args.frame_number)
    camera = colmap_model.read_cameras(args.colmap_model)[image.camera_id]
    registered_path = args.registered_images / image.name
    registered_image = cv2.imread(str(registered_path), cv2.IMREAD_UNCHANGED)
    if registered_image is None or registered_image.shape[:2] != (camera.height, camera.width):
        raise ValueError("registered frame is missing or has unexpected dimensions")
    return image, camera, registered_path


def source_video_record(video: Path) -> tuple[dict, float, int]:
    video_hash = sha256_file(video)
    if video_hash != EXPECTED_VIDEO_SHA256:
        raise ValueError("video SHA-256 does not match the accepted #100 source")
    info = probe_video(video)
    fps = float(Fraction(info["r_frame_rate"]))
    frame_count = int(info["nb_frames"])
    return {
        "path": str(video),
        "sha256": video_hash,
        "width": int(info["width"]),
        "height": int(info["height"]),
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": info["duration_seconds"],
    }, fps, frame_count


def camera_record(image, camera, centre_world, focal_x: float, focal_y: float) -> dict:
    return {
        "camera_id": image.camera_id,
        "colmap_model": camera.model,
        "parameters": list(camera.params),
        "focal_x_pixels": focal_x,
        "focal_y_pixels": focal_y,
        "approx_horizontal_fov_degrees": fov_degrees(camera.width, focal_x),
        "approx_vertical_fov_degrees": fov_degrees(camera.height, focal_y),
        "radial_distortion_is_not_modeled_by_upstream_panorama_warp": camera.model == "SIMPLE_RADIAL",
        "world_to_camera_rotation": image.rotation_w2c.tolist(),
        "world_to_camera_translation": image.translation_w2c.tolist(),
        "camera_center_colmap": image.camera_center.tolist(),
        "camera_center_godot_world_m": centre_world.tolist(),
    }


def frame_record(args, image, camera, registered_path, fps: float) -> dict:
    return {
        "video_frame_number_1_based": args.frame_number,
        "video_frame_index_0_based": args.frame_number - 1,
        "timestamp_seconds": (args.frame_number - 1) / fps,
        "registered_image": image.name,
        "registered_image_sha256": sha256_file(registered_path),
        "seed_png": str(args.frame_out.resolve()),
        "seed_png_sha256": None,
        "dimensions": [camera.width, camera.height],
        "crop_or_resize": False,
    }


def aligned_anchor_data(args, image, camera) -> tuple:
    contract = FrameContract.load(args.alignment_manifest)
    dataparser = measure_splat_frame.load_dataparser(str(args.dataparser_transforms))
    centre_ply = measure_splat_frame.cameras_in_ply_frame([image], dataparser)[0]
    centre_world = contract.ply_to_world.world_point(centre_ply)
    projection = target_projection(image, camera, args.target_world, contract, dataparser)
    forward_world, up_world = camera_orientation_world(image, contract, dataparser)
    return centre_world, projection, forward_world, up_world


def build_metadata(args) -> dict:
    video_record, fps, frame_count = source_video_record(args.video.resolve())
    if not 1 <= args.frame_number <= frame_count:
        raise ValueError("frame number is outside the source video")
    image, camera, registered_path = inspect_registered_camera(args, frame_count)
    focal_x, focal_y = focal_lengths(camera)
    centre_world, projection, forward_world, up_world = aligned_anchor_data(args, image, camera)
    camera_data = camera_record(image, camera, centre_world, focal_x, focal_y)
    camera_data.update({
        "forward_godot_world": forward_world.tolist(),
        "up_godot_world": up_world.tolist(),
        "yaw_degrees": math.degrees(math.atan2(-forward_world[0], -forward_world[2])),
        "pitch_degrees": math.degrees(math.asin(max(-1.0, min(1.0, forward_world[1])))),
    })
    return {
        "source_video": video_record,
        "registered_images": frame_count,
        "selected_frame": frame_record(args, image, camera, registered_path, fps),
        "camera": camera_data,
        "patch_anchor_check": {"target_godot_world_m": list(args.target_world), **projection},
        "hunyuan": {
            "repository": "https://github.com/Tencent-Hunyuan/HunyuanWorld-1.0",
            "commit": HUNYUAN_COMMIT,
            "default_panorama_fov_degrees": 80.0,
            "measured_panorama_fov_degrees": fov_degrees(camera.width, focal_x),
            "theta_degrees": 0.0,
            "phi_degrees": 0.0,
        },
    }


def extract_frame(video: Path, frame_number: int, output: Path, expected_size: tuple[int, int]) -> tuple[str, str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame_index = frame_number - 1
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", "select=eq(n\\,%d)" % frame_index, "-frames:v", "1",
        "-fps_mode", "vfr", "-c:v", "png", str(output),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    frame = cv2.imread(str(output), cv2.IMREAD_UNCHANGED)
    if frame is None or frame.shape[:2] != expected_size:
        raise ValueError("extracted seed frame does not match source dimensions")
    return " ".join(command), sha256_file(output)
