#!/usr/bin/env python3
"""Training-view support per splat: how many registered capture cameras see it (#103).

The multi-view half of standard 3DGS cleanup: a Gaussian that no training
camera ever looked at carries no evidence from the footage, and on this asset
those are exactly the masses north and west of spawn that #101 measured as
27.4% / 19.3% black plus splatter. The stage is therefore a *support* count,
not a visibility proof, and the report says so.

Coordinate chain (the exact inverse of ``measure_splat_frame.cameras_in_ply_frame``)::

    Godot world -> exported PLY -> nerfstudio dataparser -> COLMAP world -> image

Each hop is a similarity or a rotation, and the caller must validate the
resulting camera centres against the manifest's recorded camera bound before
anything is filtered (``verify_camera_bound``). That check is what makes a bug
in the chain impossible to ship: a wrong rotation moves the cameras by metres
and the bound check fails loudly instead of deleting half the room.

Honest limits, repeated in the report: the test is a frustum test with a near
plane and no z-buffer, so a splat hidden *behind* a wall still counts as seen.
It therefore over-estimates observation support, never under-estimates it --
which is the safe direction for a filter that deletes.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Near plane for the frustum test, in COLMAP metres. Below this the projection
#: divides by a near-zero depth and means nothing.
MIN_DEPTH_M = 0.05

#: Camera models this module can project through. ``SIMPLE_RADIAL`` is what
#: this capture's ``cameras.bin`` holds; ``PINHOLE`` is the plain case. Any
#: other model must fail loudly rather than be silently mis-projected.
SUPPORTED_MODELS = ("SIMPLE_RADIAL", "PINHOLE")


def world_to_colmap(points_world: np.ndarray, mapping: Any, dataparser: dict) -> np.ndarray:
    """Map Godot world metres to COLMAP world units, per the contract chain."""
    points_world = np.asarray(points_world, dtype=np.float64)
    if points_world.ndim != 2 or points_world.shape[1] != 3:
        raise ValueError("points_world must have shape (N, 3)")
    ply = (points_world / mapping.metres_per_unit) @ mapping.rotation()
    ply = ply + np.asarray(mapping.origin_ply_units, dtype=np.float64)
    return (ply / dataparser["scale"] - dataparser["origin"]) @ dataparser["rotation"]


def camera_centres_world(images: list, dataparser: dict, mapping: Any) -> np.ndarray:
    """Return the registered camera centres in Godot world metres."""
    centres_colmap = np.stack([image.camera_center for image in images])
    ply = (centres_colmap @ dataparser["rotation"].T + dataparser["origin"]) * dataparser["scale"]
    return np.stack([mapping.world_point(point) for point in ply])


def verify_camera_bound(centres_world: np.ndarray, cameras_contract: Any, tolerance_m: float) -> None:
    """Raise :class:`ValueError` unless the centres reproduce the manifest bound.

    The manifest's ``cameras.world_min`` / ``world_max`` were recorded when the
    contract was built (``measure_splat_frame.camera_path``), independently of
    this module. Reproducing them here to within ``tolerance_m`` proves the
    world -> COLMAP chain runs backwards correctly before any splat is dropped.
    """
    low = np.asarray(centres_world, dtype=np.float64).min(axis=0)
    high = np.asarray(centres_world, dtype=np.float64).max(axis=0)
    expected_low = np.asarray(cameras_contract.world_min, dtype=np.float64)
    expected_high = np.asarray(cameras_contract.world_max, dtype=np.float64)
    error = max(np.abs(low - expected_low).max(), np.abs(high - expected_high).max())
    if error > tolerance_m:
        raise ValueError(
            "mapped camera bound misses the manifest by %.4f m (> %.4f m): the "
            "world->COLMAP chain does not invert the recorded one"
            % (error, tolerance_m)
        )


def _project(camera_points: np.ndarray, camera: Any) -> tuple[np.ndarray, np.ndarray]:
    """Return image ``(u, v)`` for points already in the camera frame."""
    x = camera_points[:, 0] / camera_points[:, 2]
    y = camera_points[:, 1] / camera_points[:, 2]
    if camera.model == "PINHOLE":
        focal_x, focal_y, centre_x, centre_y = camera.params
        return focal_x * x + centre_x, focal_y * y + centre_y
    if camera.model == "SIMPLE_RADIAL":
        focal, centre_x, centre_y, k1 = camera.params
        radius_squared = x * x + y * y
        spread = 1.0 + k1 * radius_squared
        return focal * x * spread + centre_x, focal * y * spread + centre_y
    raise ValueError(
        "camera model %r is not supported (supported: %s)"
        % (camera.model, ", ".join(SUPPORTED_MODELS))
    )


def count_views(
    points_colmap: np.ndarray,
    images: list,
    cameras: dict,
    *,
    min_depth_m: float = MIN_DEPTH_M,
    max_depth_m: float = 0.0,
) -> np.ndarray:
    """Return, per point, how many cameras place it inside their image.

    ``max_depth_m`` of ``0`` disables the far plane (this capture's room is far
    smaller than any sensible limit, and a far plane would silently drop the
    far wall's support). Points behind a camera, behind ``min_depth_m`` or
    outside the image bounds never count.
    """
    points_colmap = np.asarray(points_colmap, dtype=np.float64)
    if points_colmap.ndim != 2 or points_colmap.shape[1] != 3:
        raise ValueError("points_colmap must have shape (N, 3)")
    if min_depth_m <= 0.0:
        raise ValueError("min_depth_m must be positive")
    counts = np.zeros(points_colmap.shape[0], dtype=np.int32)
    for image in images:
        camera = cameras[image.camera_id]
        camera_points = (image.rotation_w2c @ points_colmap.T).T + image.translation_w2c
        depth = camera_points[:, 2]
        inside_depth = depth > min_depth_m
        if max_depth_m > 0.0:
            inside_depth = inside_depth & (depth < max_depth_m)
        with np.errstate(divide="ignore", invalid="ignore"):
            u, v = _project(np.where(inside_depth[:, None], camera_points, 0.0), camera)
        inside_image = (
            inside_depth
            & np.isfinite(u)
            & np.isfinite(v)
            & (u >= 0.0)
            & (u < camera.width)
            & (v >= 0.0)
            & (v < camera.height)
        )
        counts += inside_image.astype(np.int32)
    return counts
