"""Measure camera motion, view direction, and bottom-band floor projection."""

from __future__ import annotations

import json

import build_registered_floor_masks_all_frames as floor_masks
import numpy as np
from camera_path_diagnostic_inputs import (
    HERE,
    input_hashes,
    load_camera_path,
    percentile_summary,
)
from registered_floor_masks import (
    FrameContext,
    candidate_band_pixels,
    floor_intersections,
)

OUTPUT = HERE / "camera_path_geometry_diagnostics.json"
PIXEL_STRIDE = 16


def optical_axis_world(context, image) -> np.ndarray:
    """Map COLMAP camera +Z into the declared #100 world frame."""
    axis = np.array([0.0, 0.0, 1.0]) @ image.rotation_w2c
    axis = axis @ context.dataparser["rotation"].T
    axis = axis @ context.contract.ply_to_world.rotation().T
    norm = float(np.linalg.norm(axis))
    if norm < 1e-12:
        raise ValueError("camera optical axis has zero length")
    return axis / norm


def mapped_intersection_origin(context, image) -> np.ndarray:
    """Recompute the ray origin independently from the contract camera list."""
    centre_ply = (
        image.camera_center @ context.dataparser["rotation"].T
        + context.dataparser["origin"]
    ) * context.dataparser["scale"]
    return context.contract.ply_to_world.world_point(centre_ply)


def motion_components(context) -> tuple[np.ndarray, float]:
    """Measure frame-to-frame movement expressed in each source camera frame."""
    components = []
    for first, second in zip(context.images[:-1], context.images[1:], strict=True):
        movement = second.camera_center - first.camera_center
        local = first.rotation_w2c @ movement
        norm = float(np.linalg.norm(local))
        if norm > 1e-12:
            components.append(np.abs(local / norm))
    values = np.stack(components)
    return np.median(values, axis=0), float(np.mean(values[:, 0] > values[:, 2]))


def orientation_samples(context) -> tuple[np.ndarray, np.ndarray]:
    """Return camera pitch and heading-relative-to-motion samples."""
    pitch, heading_delta = [], []
    for index, image in enumerate(context.images):
        axis = optical_axis_world(context, image)
        horizontal_axis = axis[[0, 2]]
        horizontal_axis /= np.linalg.norm(horizontal_axis)
        before, after = max(index - 3, 0), min(index + 3, len(context.images) - 1)
        motion = (
            context.centres_world_m[after, [0, 2]]
            - context.centres_world_m[before, [0, 2]]
        )
        if np.linalg.norm(motion) > 1e-12:
            motion /= np.linalg.norm(motion)
            cross = horizontal_axis[0] * motion[1] - horizontal_axis[1] * motion[0]
            heading_delta.append(
                np.degrees(np.arctan2(cross, horizontal_axis @ motion))
            )
        pitch.append(np.degrees(np.arcsin(np.clip(axis[1], -1.0, 1.0))))
    return np.asarray(pitch), np.asarray(heading_delta)


def bottom_band_offsets(context) -> tuple[np.ndarray, np.ndarray]:
    """Measure bottom-band plane hits relative to each camera heading."""
    forward_distance, lateral_distance = [], []
    floor_height = context.contract.collider.floor_height
    for index, image in enumerate(context.images):
        centre = context.centres_world_m[index]
        axis = optical_axis_world(context, image)[[0, 2]]
        axis /= np.linalg.norm(axis)
        camera = context.cameras[image.camera_id]
        pixels = candidate_band_pixels(
            camera.width, camera.height, floor_masks.MASK_TOP_ROW, PIXEL_STRIDE
        )
        hits, _ = floor_intersections(
            pixels,
            FrameContext(image=image, camera=camera),
            context.dataparser,
            context.contract.ply_to_world,
            floor_height,
        )
        direction = hits[:, [0, 2]].mean(axis=0) - centre[[0, 2]]
        forward_distance.append(float(direction @ axis))
        lateral_distance.append(float(axis[0] * direction[1] - axis[1] * direction[0]))
    return np.asarray(forward_distance), np.asarray(lateral_distance)


def ray_origin_residuals(context) -> np.ndarray:
    """Compare independently mapped image origins with contract centres."""
    return np.asarray(
        [
            np.linalg.norm(mapped_intersection_origin(context, image) - centre)
            for image, centre in zip(
                context.images, context.centres_world_m, strict=True
            )
        ]
    )


def describe_path(context) -> dict:
    """Build path-relative camera and floor-band statistics."""
    floor_height = context.contract.collider.floor_height
    pitch, heading_delta = orientation_samples(context)
    forward, lateral = bottom_band_offsets(context)
    motion_median, x_dominant_fraction = motion_components(context)
    return {
        "camera_motion_local_abs_component_median_xyz": np.round(
            motion_median, 6
        ).tolist(),
        "fraction_frames_x_motion_exceeds_z": round(x_dominant_fraction, 6),
        "camera_pitch_deg": percentile_summary(pitch),
        "view_heading_minus_motion_deg": percentile_summary(heading_delta),
        "camera_height_above_declared_floor_m": percentile_summary(
            context.centres_world_m[:, 1] - floor_height
        ),
        "ray_origin_vs_registered_camera_residual_m": percentile_summary(
            ray_origin_residuals(context)
        ),
        "bottom_band_floor_hit_centroid_forward_m": percentile_summary(forward),
        "bottom_band_floor_hit_centroid_lateral_m": percentile_summary(lateral),
    }


def main() -> None:
    """Write a machine-readable, read-only geometry diagnostic."""
    context = load_camera_path()
    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "read_only_camera_coverage_diagnostic",
        "inputs": input_hashes(),
        "registered_frames": len(context.images),
        "camera_model": context.cameras[context.images[0].camera_id].model,
        "floor_height_m": context.contract.collider.floor_height,
        "pixel_stride": PIXEL_STRIDE,
        "results": describe_path(context),
        "limits": [
            "Bottom-band floor intersections use the declared #100 horizontal plane.",
            "This measures image/frustum geometry, not actual floor elevation or occlusion.",
            "The #100 scale is a synthetic coordinate convention, not surveyed scale.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
