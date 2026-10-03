#!/usr/bin/env python3
"""Read a COLMAP sparse reconstruction (cameras.bin / images.bin).

This is the authoritative *training* transform record for every capture: it
holds the poses splatfacto was optimised against.  Nothing here guesses -- the
up axis, the orbit axis and the camera heights are all measured from the
registered images, so the metric-scale decision in ``splat_frame`` can cite a
real reference instead of an assumption carried over from a retired mesh.

COLMAP camera convention (scripts/python/database.py): the camera looks down
its own +Z, +X is right, +Y is *down* in the image.  Therefore the world-space
"up" for a camera is ``-R[:, 1]`` and the view direction is ``R[:, 2]``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# struct layouts from COLMAP's src/colmap/scene/reconstruction.cc
_CAMERA_MODEL_NAMES = {
    0: "SIMPLE_PINHOLE",
    1: "PINHOLE",
    2: "SIMPLE_RADIAL",
    3: "RADIAL",
    4: "OPENCV",
    5: "OPENCV_FISHEYE",
    6: "FULL_OPENCV",
    7: "FOV",
    8: "SIMPLE_RADIAL_FISHEYE",
    9: "RADIAL_FISHEYE",
    10: "THIN_PRISM_FISHEYE",
}

_CAMERA_MODEL_NUM_PARAMS = {
    0: 3, 1: 4, 2: 4, 3: 5, 4: 8, 5: 8, 6: 12, 7: 5, 8: 4, 9: 5, 10: 12,
}


@dataclass(frozen=True)
class Camera:
    """One COLMAP camera record (intrinsics only)."""

    camera_id: int
    model: str
    width: int
    height: int
    params: tuple[float, ...]


@dataclass(frozen=True)
class RegisteredImage:
    """One registered image: its world-to-camera rotation and camera centre."""

    image_id: int
    name: str
    camera_id: int
    rotation_w2c: np.ndarray  # 3x3, world -> camera
    translation_w2c: np.ndarray  # 3, world -> camera
    xys: np.ndarray  # (N, 2) keypoints
    point3d_ids: np.ndarray  # (N,)

    @property
    def camera_center(self) -> np.ndarray:
        """Camera centre in COLMAP world coordinates (``-R^T t``)."""
        return -self.rotation_w2c.T @ self.translation_w2c

    @property
    def view_direction(self) -> np.ndarray:
        """Unit look direction in world space (camera +Z axis)."""
        return _unit(self.rotation_w2c[2])

    @property
    def up_direction(self) -> np.ndarray:
        """Unit world-space "up" (negative of the image-down +Y axis)."""
        return _unit(-self.rotation_w2c[1])

    @property
    def right_direction(self) -> np.ndarray:
        """Unit world-space "right" (camera +X axis)."""
        return _unit(self.rotation_w2c[0])


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm < 1e-12:
        raise ValueError("cannot normalise a zero-length direction")
    return np.asarray(vector, dtype=np.float64) / norm


def find_sparse_model(scene_dir: str | Path, prefer: str | None = None) -> Path:
    """Locate a COLMAP sparse model directory inside ``scene_dir``.

    ``prefer`` names a subdirectory to try first (``sparse/0``, ``sparse/1``...).
    Otherwise the model with the most registered cameras wins, which is the rule
    LESSONS_LEARNED 2.4 established for disjoint COLMAP sub-models.
    """
    root = Path(scene_dir)
    candidates = [root] if _is_model_dir(root) else []
    if root.is_dir():
        for child in sorted(p for p in root.rglob("*") if p.is_dir()):
            if _is_model_dir(child):
                candidates.append(child)

    if not candidates:
        raise FileNotFoundError("no COLMAP sparse model (cameras.bin/images.bin) under %s" % root)

    if prefer:
        wanted = root / prefer
        for candidate in candidates:
            if candidate == wanted:
                return candidate

    scored = []
    for candidate in candidates:
        try:
            scored.append((len(read_images(candidate)), str(candidate)))
        except (struct.error, OSError):
            continue
    if not scored:
        raise ValueError("no readable COLMAP model under %s" % root)
    scored.sort(reverse=True)
    return Path(scored[0][1])


def _is_model_dir(path: Path) -> bool:
    return (path / "cameras.bin").is_file() and (path / "images.bin").is_file()


def read_cameras(model_dir: str | Path) -> dict[int, Camera]:
    """Parse ``cameras.bin`` into ``{camera_id: Camera}``."""
    path = Path(model_dir) / "cameras.bin"
    with path.open("rb") as handle:
        count = struct.unpack("<Q", handle.read(8))[0]
        cameras: dict[int, Camera] = {}
        for _ in range(count):
            camera_id, model_id, width, height = struct.unpack("<iiQQ", handle.read(24))
            model = _CAMERA_MODEL_NAMES.get(model_id, "UNKNOWN_%d" % model_id)
            num_params = _CAMERA_MODEL_NUM_PARAMS.get(model_id)
            if num_params is None:
                raise ValueError("unsupported COLMAP camera model id %d" % model_id)
            params = struct.unpack("<%dd" % num_params, handle.read(8 * num_params))
            cameras[camera_id] = Camera(camera_id, model, int(width), int(height), params)
    return cameras


def read_images(model_dir: str | Path) -> list[RegisteredImage]:
    """Parse ``images.bin`` into ``RegisteredImage`` records."""
    path = Path(model_dir) / "images.bin"
    images: list[RegisteredImage] = []
    with path.open("rb") as handle:
        count = struct.unpack("<Q", handle.read(8))[0]
        for _ in range(count):
            image_id = struct.unpack("<i", handle.read(4))[0]
            quaternion = struct.unpack("<4d", handle.read(32))
            translation = struct.unpack("<3d", handle.read(24))
            camera_id = struct.unpack("<i", handle.read(4))[0]
            name = _read_string(handle)
            num_points2d = struct.unpack("<Q", handle.read(8))[0]
            # Each 2D point is double x, double y, int64 point3D_id = 24 bytes.
            raw = np.frombuffer(handle.read(24 * num_points2d), dtype="<f8")
            triples = raw.reshape(num_points2d, 3)
            images.append(
                RegisteredImage(
                    image_id=image_id,
                    name=name,
                    camera_id=camera_id,
                    rotation_w2c=_quaternion_to_rotation(*quaternion),
                    translation_w2c=np.asarray(translation, dtype=np.float64),
                    xys=triples[:, :2].copy(),
                    point3d_ids=np.nan_to_num(triples[:, 2], nan=-1.0).astype(np.int64),
                )
            )
    return images


def _read_string(handle) -> str:
    chars = []
    while True:
        char = handle.read(1)
        if char == b"\x00" or char == b"":
            return "".join(chars)
        chars.append(char.decode("utf-8", "replace"))


def _quaternion_to_rotation(qw, qx, qy, qz) -> np.ndarray:
    """COLMAP stores world-to-camera quaternions as (w, x, y, z)."""
    quaternion = np.asarray([qw, qx, qy, qz], dtype=np.float64)
    norm = float(np.linalg.norm(quaternion))
    if norm < 1e-12:
        raise ValueError("degenerate quaternion in images.bin")
    w, x, y, z = quaternion / norm
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def camera_centers(images: list[RegisteredImage]) -> np.ndarray:
    """Stack registered camera centres into an ``(N, 3)`` array."""
    if not images:
        raise ValueError("no registered images")
    return np.stack([image.camera_center for image in images])


def dominant_up_direction(images: list[RegisteredImage]) -> np.ndarray:
    """Measure the world-space up axis from the registered cameras.

    Combines the average scene up (COLMAP's own convention: the mean camera
    +Y axis) with each camera's own up, which is the signal COLMAP's
    ``database.py`` and nerfstudio's ``orientation_method: up`` both use.  The
    sign is fixed by the *majority* of cameras, so a couple of flipped poses
    cannot invert the result.
    """
    if not images:
        raise ValueError("no registered images")
    stacked = np.stack([image.up_direction for image in images])
    # Cameras weighted equally: scene-level mean first, then per-camera votes.
    scene_up = _unit(stacked.mean(axis=0))
    votes = stacked @ scene_up
    if float(np.sum(votes < 0)) > float(np.sum(votes >= 0)):
        scene_up = -scene_up
    return scene_up


def dominant_up_axis_index(up_direction: np.ndarray) -> tuple[int, float]:
    """Return ``(axis_index, signed_magnitude)`` of the strongest up component.

    ``signed_magnitude`` is positive when up is +axis, negative when it is
    -axis.  ``abs()`` is the share of up that lies on that principal axis.
    """
    index = int(np.argmax(np.abs(up_direction)))
    return index, float(up_direction[index])