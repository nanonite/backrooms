"""Project registered route-floor samples into the #100 source video frames."""

from __future__ import annotations

import json

import numpy as np
from camera_path_diagnostic_inputs import (
    HERE,
    floor_masks,
    input_hashes,
    load_camera_path,
    percentile_summary,
    project_world_points,
)

OUTPUT = HERE / "route_floor_visibility_diagnostics.json"
IMAGE_REGIONS = {
    "bottom_band_v_ge_930": 930,
    "lower_half_v_ge_540": 540,
    "full_image": 0,
}


def route_floor_points(context) -> np.ndarray:
    """Place camera-path XZ samples on the declared #100 floor plane."""
    floor_height = context.contract.collider.floor_height
    return np.column_stack(
        (
            context.centres_world_m[:, 0],
            np.full(len(context.images), floor_height),
            context.centres_world_m[:, 2],
        )
    )


def update_frame_visibility(
    context,
    image_index: int,
    route_points: np.ndarray,
    visible: dict,
    nearest_distance: np.ndarray,
    nearest_row: np.ndarray,
    apply_radial_distortion: bool,
) -> None:
    """Accumulate in-frame route samples and their nearest lower-half view."""
    image = context.images[image_index]
    camera = context.cameras[image.camera_id]
    pixels, in_front = project_world_points(
        context, image_index, route_points, apply_radial_distortion
    )
    in_frame = in_image_rectangle(pixels, in_front, camera.width, camera.height)
    for name, top_row in IMAGE_REGIONS.items():
        visible[name] |= in_frame & (pixels[:, 1] >= top_row)
    capture_nearest_view(
        context,
        image_index,
        route_points,
        pixels,
        in_frame,
        nearest_distance,
        nearest_row,
    )


def in_image_rectangle(
    pixels: np.ndarray, in_front: np.ndarray, width: int, height: int
) -> np.ndarray:
    """Return projected points inside a camera's image bounds."""
    return (
        in_front
        & (pixels[:, 0] >= 0.0)
        & (pixels[:, 0] < width)
        & (pixels[:, 1] >= 0.0)
        & (pixels[:, 1] < height)
    )


def capture_nearest_view(
    context,
    image_index: int,
    route_points: np.ndarray,
    pixels: np.ndarray,
    in_frame: np.ndarray,
    nearest_distance: np.ndarray,
    nearest_row: np.ndarray,
) -> None:
    """Record the closest lower-half image view of each route sample."""
    nearest = in_frame & (pixels[:, 1] >= IMAGE_REGIONS["lower_half_v_ge_540"])
    distance = np.linalg.norm(
        route_points - context.centres_world_m[image_index], axis=1
    )
    nearer = nearest & (distance < nearest_distance)
    nearest_distance[nearer] = distance[nearer]
    nearest_row[nearer] = pixels[nearer, 1]


def summarize_visibility(
    context, visible: dict, nearest_distance: np.ndarray, nearest_row: np.ndarray
) -> dict:
    """Summarize sample visibility and closest lower-half projections."""
    frame_numbers = np.asarray(
        [floor_masks.image_number(image.name) for image in context.images]
    )
    results = {
        name: {
            "route_samples_visible_in_at_least_one_frame": int(samples.sum()),
            "route_sample_count": len(samples),
            "never_visible_frame_numbers_1_based": frame_numbers[~samples].tolist(),
        }
        for name, samples in visible.items()
    }
    observed = np.isfinite(nearest_distance)
    results["lower_half_nearest_view_distance_m"] = percentile_summary(
        nearest_distance[observed]
    )
    results["lower_half_nearest_view_row_px"] = percentile_summary(
        nearest_row[observed]
    )
    results["lower_half_nearest_view_sample_count"] = int(observed.sum())
    return results


def evaluate_visibility(context, apply_radial_distortion: bool) -> dict:
    """Count in-image route projections, without claiming they are unoccluded."""
    route_points = route_floor_points(context)
    visible = {name: np.zeros(len(route_points), dtype=bool) for name in IMAGE_REGIONS}
    nearest_distance = np.full(len(route_points), np.inf)
    nearest_row = np.full(len(route_points), np.nan)
    for image_index in range(len(context.images)):
        update_frame_visibility(
            context,
            image_index,
            route_points,
            visible,
            nearest_distance,
            nearest_row,
            apply_radial_distortion,
        )
    return summarize_visibility(context, visible, nearest_distance, nearest_row)


def main() -> None:
    """Write a machine-readable, distortion-aware route visibility diagnostic."""
    context = load_camera_path()
    report = {
        "schema_version": 1,
        "issue": 135,
        "status": "in_image_visibility_upper_bound",
        "inputs": input_hashes(),
        "registered_frames": len(context.images),
        "camera_model": context.cameras[context.images[0].camera_id].model,
        "floor_height_m": context.contract.collider.floor_height,
        "projection_comparison": [
            "Pinhole reproduction of the supplied scratch calculation.",
            "COLMAP SIMPLE_RADIAL forward distortion on the monotonic radial branch.",
        ],
        "occlusion_tested": False,
        "route_samples": "192 registered camera XZ centres with Y set to the declared #100 floor height",
        "results": {
            "pinhole_scratch_reproduction": evaluate_visibility(
                context, apply_radial_distortion=False
            ),
            "simple_radial_corrected": evaluate_visibility(
                context, apply_radial_distortion=True
            ),
        },
        "limits": [
            "In-frame projection ignores walls, columns, and other occluders.",
            "The route sample heights are imposed by the #100 plane; this is not measured floor geometry.",
            "The #100 scale is a synthetic coordinate convention, not surveyed scale.",
        ],
    }
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
