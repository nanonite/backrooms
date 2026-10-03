#!/usr/bin/env python3
"""Write COLMAP-format ``cameras.bin`` / ``images.bin`` for tests.

The registration report is only meaningful if it has been run against real
model files, and no COLMAP binary is required to produce one -- the format is
three small structs per record. This writes them directly, so
``test_model_coverage.py`` can assert on a model with a known number of
registered and unregistered frames without running a reconstruction.

Layout, from COLMAP's ``src/colmap/scene/reconstruction.cc``:

* ``cameras.bin``  -- uint64 count, then per camera: int32 id, int32 model_id,
  uint64 width, uint64 height, ``double params[model_params]``.
* ``images.bin``   -- uint64 count, then per image: int32 id, ``double quat[4]``
  as (w, x, y, z), ``double translation[3]``, int32 camera_id, NUL-terminated
  name, uint64 num_points2D, then per point ``(double x, double y, int64 point3D_id)``.

Camera model 0 is ``SIMPLE_PINHOLE`` with 3 params ``(f, cx, cy)``.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

#: ``SIMPLE_PINHOLE`` from colmap_model's model-name table.
SIMPLE_PINHOLE = 0
SIMPLE_PINHOLE_PARAMS = 3

#: Points per registered image in these fixtures. The registration report does
#: not read keypoints, but the record length has to be self-consistent or the
#: next image's struct is read at the wrong offset.
POINTS_PER_IMAGE = 8


def _quaternion(rotation: np.ndarray) -> tuple[float, float, float, float]:
    """Rotation matrix to COLMAP's (w, x, y, z) quaternion."""
    trace = float(np.trace(rotation))
    if trace > 0:
        scale = np.sqrt(trace + 1.0) * 2
        w = 0.25 * scale
        x = (rotation[2, 1] - rotation[1, 2]) / scale
        y = (rotation[0, 2] - rotation[2, 0]) / scale
        z = (rotation[1, 0] - rotation[0, 1]) / scale
    else:
        diagonal = int(np.argmax(np.diag(rotation)))
        if diagonal == 0:
            scale = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2
            w = (rotation[2, 1] - rotation[1, 2]) / scale
            x = 0.25 * scale
            y = (rotation[0, 1] + rotation[1, 0]) / scale
            z = (rotation[0, 2] + rotation[2, 0]) / scale
        elif diagonal == 1:
            scale = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2
            w = (rotation[0, 2] - rotation[2, 0]) / scale
            x = (rotation[0, 1] + rotation[1, 0]) / scale
            y = 0.25 * scale
            z = (rotation[1, 2] + rotation[2, 1]) / scale
        else:
            scale = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2
            w = (rotation[1, 0] - rotation[0, 1]) / scale
            x = (rotation[0, 2] + rotation[2, 0]) / scale
            y = (rotation[1, 2] + rotation[2, 1]) / scale
            z = 0.25 * scale
    norm = float(np.sqrt(w * w + x * x + y * y + z * z))
    return w / norm, x / norm, y / norm, z / norm


def _camera_centres(poses: list[tuple[float, float, float]]):
    """Yield ``(quaternion, translation)`` whose camera centres are ``poses``.

    The camera looks down its own +Z, so a camera centred at ``C`` with identity
    rotation satisfies ``C = -R^T t`` -> ``t = -R C``. Poses therefore come out of
    this writer as the positions a reader measures back, which is what lets the
    test assert on a known pose extent.
    """
    for centre in poses:
        point = np.asarray(centre, dtype=np.float64)
        yield _quaternion(np.eye(3)), tuple(-point)


def write_cameras(model_dir: Path, width: int, height: int, focal: float, count: int = 1) -> None:
    """Write ``cameras.bin`` holding ``count`` identical ``SIMPLE_PINHOLE`` cameras."""
    principal = (width / 2.0, height / 2.0)
    payload = [struct.pack("<Q", count)]
    for camera_id in range(1, count + 1):
        payload.append(struct.pack("<iiQQ", camera_id, SIMPLE_PINHOLE, width, height))
        payload.append(struct.pack("<3d", focal, *principal))
    (model_dir / "cameras.bin").write_bytes(b"".join(payload))


def write_images(
    model_dir: Path,
    names: list[str],
    poses: list[tuple[float, float, float]] | None = None,
    camera_id: int = 1,
) -> None:
    """Write ``images.bin`` for ``names``, at poses on the x axis by default."""
    model_dir.mkdir(parents=True, exist_ok=True)
    centres = list(poses) if poses is not None else [(float(index), 0.0, 0.0) for index in range(len(names))]
    payload = [struct.pack("<Q", len(names))]
    for image_id, (name, record) in enumerate(zip(names, _camera_centres(centres)), start=1):
        quaternion, translation = record
        payload.append(struct.pack("<i", image_id))
        payload.append(struct.pack("<4d", *quaternion))
        payload.append(struct.pack("<3d", *translation))
        payload.append(struct.pack("<i", camera_id))
        payload.append(name.encode("utf-8") + b"\x00")
        payload.append(struct.pack("<Q", POINTS_PER_IMAGE))
        for point in range(POINTS_PER_IMAGE):
            payload.append(struct.pack("<ddq", 10.0 * point, 20.0 * point, point))
    (model_dir / "images.bin").write_bytes(b"".join(payload))


def write_model(
    model_dir: Path,
    names: list[str],
    width: int = 640,
    height: int = 360,
    focal: float = 500.0,
    poses: list[tuple[float, float, float]] | None = None,
) -> Path:
    """Write a complete ``cameras.bin`` + ``images.bin`` model at ``model_dir``."""
    model_dir.mkdir(parents=True, exist_ok=True)
    write_cameras(model_dir, width, height, focal)
    write_images(model_dir, names, poses)
    return model_dir


if __name__ == "__main__":
    import sys

    target = Path(sys.argv[1] if len(sys.argv) > 1 else "sparse/0")
    write_model(target, [f"frame_{index:04d}.jpg" for index in range(1, 11)])
    print(f"wrote a 10-image model to {target}")
