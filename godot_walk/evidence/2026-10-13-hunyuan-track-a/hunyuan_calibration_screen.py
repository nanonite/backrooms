"""Screen frame-141 Hunyuan/source image matches against registered COLMAP points."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pycolmap

EVIDENCE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE_DIR.parents[2]
DEFAULT_SOURCE = REPO_ROOT / "data/scenes/corridor_travel/images/frame_0141.jpg"
DEFAULT_PANORAMA = (
    REPO_ROOT / "data/track-a/hunyuan/scene-run-05/remove_fg1_image_sr.png"
)
DEFAULT_COLMAP = REPO_ROOT / "data/scenes/corridor_travel/sparse/0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reproject_panorama(
    panorama: np.ndarray, camera: pycolmap.Camera
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, width = camera.height, camera.width
    y_grid, x_grid = np.mgrid[:height, :width].astype(np.float32)
    pixels = np.stack((x_grid, y_grid), axis=-1).reshape(-1, 1, 2)
    focal, center_x, center_y, radial = camera.params
    intrinsics = np.array(
        [[focal, 0.0, center_x], [0.0, focal, center_y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    undistorted = cv2.undistortPoints(
        pixels, intrinsics, np.array([radial, 0.0, 0.0, 0.0])
    ).reshape(height, width, 2)
    x_ray, y_ray = undistorted[..., 0], undistorted[..., 1]
    ray_norm = np.sqrt(x_ray * x_ray + y_ray * y_ray + 1.0)
    longitude = np.arctan2(x_ray, 1.0)
    latitude = np.arcsin(-y_ray / ray_norm)
    pano_height, pano_width = panorama.shape[:2]
    map_x = ((longitude / (2 * np.pi)) + 0.5) * pano_width
    map_y = (0.5 - latitude / np.pi) * pano_height
    projected = cv2.remap(
        panorama,
        map_x.astype(np.float32),
        map_y.astype(np.float32),
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return projected, map_x, map_y


def nearest_registered_points(
    image, matched_keypoints, maximum_distance: float
) -> set[int]:
    image_points = np.array([point.xy for point in image.points2D], dtype=np.float32)
    point_ids = [int(point.point3D_id) for point in image.points2D]
    associated: set[int] = set()
    for keypoint in matched_keypoints:
        distances = np.linalg.norm(image_points - np.asarray(keypoint), axis=1)
        nearest = int(np.argmin(distances))
        if distances[nearest] <= maximum_distance:
            point_id = point_ids[nearest]
            if point_id != 2**64 - 1:
                associated.add(point_id)
    return associated


def analyze(source_path: Path, panorama_path: Path, colmap_path: Path) -> dict:
    source = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
    panorama = cv2.imread(str(panorama_path), cv2.IMREAD_GRAYSCALE)
    if source is None or panorama is None:
        raise FileNotFoundError("could not decode source frame or Hunyuan panorama")

    reconstruction = pycolmap.Reconstruction(str(colmap_path))
    source_record = next(
        (
            item
            for item in reconstruction.images.values()
            if item.name == source_path.name
        ),
        None,
    )
    if source_record is None:
        raise ValueError("source frame is not registered in the COLMAP reconstruction")
    camera = reconstruction.cameras[source_record.camera_id]
    projected, map_x, map_y = reproject_panorama(panorama, camera)

    detector = cv2.SIFT_create(nfeatures=4000)
    source_keypoints, source_descriptors = detector.detectAndCompute(source, None)
    pano_keypoints, pano_descriptors = detector.detectAndCompute(projected, None)
    if source_descriptors is None or pano_descriptors is None:
        raise ValueError("SIFT found no descriptors in one of the images")
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(
        source_descriptors, pano_descriptors, k=2
    )
    good_matches = [
        best
        for pair in matches
        if len(pair) == 2
        for best, second in [pair]
        if best.distance < 0.75 * second.distance
    ]
    inlier_mask = np.zeros(len(good_matches), dtype=bool)
    if len(good_matches) >= 4:
        source_xy = np.float32(
            [source_keypoints[match.queryIdx].pt for match in good_matches]
        )
        pano_xy = np.float32(
            [pano_keypoints[match.trainIdx].pt for match in good_matches]
        )
        _, mask = cv2.findHomography(source_xy, pano_xy, cv2.RANSAC, 3.0)
        if mask is not None:
            inlier_mask = mask.reshape(-1).astype(bool)
    inlier_matches = [match for match, keep in zip(good_matches, inlier_mask) if keep]
    source_xy = [source_keypoints[match.queryIdx].pt for match in inlier_matches]
    pano_xy = [pano_keypoints[match.trainIdx].pt for match in inlier_matches]
    sparse_points = nearest_registered_points(source_record, source_xy, 10.0)
    image_cells = {
        (min(3, int(x * 4 / camera.width)), min(3, int(y * 4 / camera.height)))
        for x, y in source_xy
    }
    pano_samples = []
    for x, y in pano_xy:
        pixel_x = min(camera.width - 1, max(0, round(x)))
        pixel_y = min(camera.height - 1, max(0, round(y)))
        pano_samples.append(
            [
                float(map_x[pixel_y, pixel_x]),
                float(map_y[pixel_y, pixel_x]),
            ]
        )
    return {
        "method": "SIFT ratio matches after Hunyuan equirectangular-to-camera reprojection",
        "source_frame": source_record.name,
        "camera_model": str(camera.model),
        "camera_parameters": [float(value) for value in camera.params],
        "source_image": {"path": str(source_path), "sha256": sha256(source_path)},
        "hunyuan_panorama": {
            "path": str(panorama_path),
            "sha256": sha256(panorama_path),
            "size": [int(panorama.shape[1]), int(panorama.shape[0])],
        },
        "colmap_model": str(colmap_path),
        "sift_keypoints": {
            "source": len(source_keypoints),
            "hunyuan_projected_view": len(pano_keypoints),
        },
        "lowe_ratio_threshold": 0.75,
        "ratio_matches": len(good_matches),
        "homography_ransac_threshold_pixels": 3.0,
        "homography_inliers": len(inlier_matches),
        "inlier_source_image_grid_cells_occupied_4x4": len(image_cells),
        "unique_registered_3d_points_within_10px_of_inliers": len(sparse_points),
        "inlier_hunyuan_equirectangular_pixels": pano_samples,
        "automated_correspondence_screen_passed": (
            len(inlier_matches) >= 20
            and len(sparse_points) >= 12
            and len(image_cells) >= 6
        ),
        "limitation": (
            "Feature screening does not prove semantic identity. A passing count still "
            "requires spatially distributed, manually confirmed landmarks and a robust fit."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--panorama", type=Path, default=DEFAULT_PANORAMA)
    parser.add_argument("--colmap", type=Path, default=DEFAULT_COLMAP)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = analyze(args.source, args.panorama, args.colmap)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
