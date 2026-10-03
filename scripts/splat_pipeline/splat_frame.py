#!/usr/bin/env python3
"""The one explicit coordinate + metric-scale contract for splat scenes.

Everything a Gaussian splat scene needs to agree on, in one serialisable record:

* which PLY/reconstruction axis is **up**, and with which sign
* the **handedness** of that frame and of the Godot world
* how many **reconstruction units** there are in a **metre**, and *why*
* every transform the toolchain applies **automatically**, so none is
  accidentally applied twice and none is silently missed
* the resulting PLY -> Godot-world mapping, as an explicit basis (not an Euler
  triple, because axis-order conventions differ between languages)
* landmarks and the collision box derived from those landmarks

The point of putting this in a file rather than in prose is that
``godot_walk/scripts/verify_alignment.gd`` reads the *same* file at runtime and
fails loudly when a scene's effective mapping drifts from it.  Equal serialised
transforms are not evidence; equal *effective world mapping* is.

See ``godot_walk/assets/corridor_splat/README.md`` for the narrative version.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_VERSION = 2

AXIS_VECTORS = {
    "x": np.array([1.0, 0.0, 0.0]),
    "y": np.array([0.0, 1.0, 0.0]),
    "z": np.array([0.0, 0.0, 1.0]),
}

#: Slack allowed when requiring the reconstruction camera path to lie inside the
#: room, in metres. Generous on purpose: the room's horizontal extents are
#: observation bounds derived from the camera window, so demanding exact
#: containment would be demanding the two measurements agree by construction.
CAMERA_ROOM_SLACK_M = 2.0

#: Plausible range for the mean camera height above the floor, in metres. A
#: person walking a corridor records an eye height inside this band; a mean
#: outside it means the mapping or the up axis is wrong, not that someone filmed
#: a crawlspace. Deliberately wide -- this is a sanity band, not a measurement.
EYE_HEIGHT_RANGE_M = (0.4, 2.2)


class ContractError(ValueError):
    """Raised when a manifest is internally inconsistent or unusable."""


def _camera_from_json(data: dict[str, Any]) -> "CameraPath":
    """Rebuild a :class:`CameraPath`, normalising the bounds back to tuples.

    JSON has no tuple type, so a save/load round trip turns the bounds into lists.
    Every other tuple field is normalised back the same way (``landmarks``,
    ``spawn``); doing it here too keeps the camera path from being the one place
    a round trip silently changes type.
    """
    return CameraPath(
        count=int(data["count"]),
        world_min=tuple(float(v) for v in data["world_min"]),
        world_max=tuple(float(v) for v in data["world_max"]),
        height_min_m=float(data["height_min_m"]),
        height_mean_m=float(data["height_mean_m"]),
        height_max_m=float(data["height_max_m"]),
        source=str(data["source"]),
    )


@dataclass(frozen=True)
class AutomaticTransform:
    """A transform the toolchain applies without being asked.

    ``basis``/``origin`` are the row-major 3x3 / 3 part of the correction.
    ``neutralised`` records that the scene deliberately avoids it.
    """

    stage: str
    source: str
    summary: str
    basis: tuple[tuple[float, ...], ...]
    origin: tuple[float, float, float]
    neutralised: bool
    neutralised_by: str

    def matrix(self) -> np.ndarray:
        """Return the 4x4 homogeneous matrix for this correction."""
        out = np.eye(4)
        out[:3, :3] = np.asarray(self.basis, dtype=np.float64)
        out[:3, 3] = self.origin
        return out


@dataclass(frozen=True)
class ScaleReference:
    """How ``metres_per_unit`` was decided, and how well it is pinned down.

    ``basis`` is ``"measured_reference"`` when a real-world distance was observed
    in the footage (e.g. a taped floor mark), and ``"chosen"`` when the footage
    is synthetic and no real reference can exist.  The two are never conflated:
    a chosen value is a decision, and is reported as one.
    """

    kind: str
    quantity: str
    raw_units: float
    raw_units_spread: float
    raw_units_spread_samples: int
    target_metres: float
    reason: str

    @property
    def tolerance_metres(self) -> float:
        """Allowed world error on the reference quantity, from the raw spread.

        Two standard deviations of the raw measurement, floored at 10% of the
        target so a suspiciously tight reconstruction cannot force a tolerance
        no real scene will ever meet.
        """
        if self.raw_units <= 0.0:
            raise ContractError("reference raw_units must be positive")
        relative = 2.0 * self.raw_units_spread / self.raw_units
        return max(self.target_metres * relative, 0.10 * self.target_metres)


@dataclass(frozen=True)
class PlyToWorld:
    """Explicit PLY/reconstruction-frame -> Godot-world mapping.

    ``basis_columns`` are the images of the frame's x/y/z axes expressed in Godot
    world axes, as three columns.  ``metres_per_unit`` scales them, and
    ``origin_ply_units`` is subtracted first.

    ``origin_ply_units`` is the centroid the GDGS resource builder subtracts from
    every Gaussian on import.  It is recorded rather than assumed, because it is
    the one automatic transform with no visual effect: forget it and the splat
    lands at the right orientation and the wrong place, which is exactly the
    class of bug this contract exists to make impossible.
    """

    basis_columns: tuple[tuple[float, float, float], ...]
    metres_per_unit: float
    origin_ply_units: tuple[float, float, float]
    frame_name: str
    up_axis: str
    up_sign: int
    handedness: str

    def rotation(self) -> np.ndarray:
        """Return the 3x3 rotation matrix, columns = ``basis_columns``."""
        matrix = np.column_stack([np.asarray(c, dtype=np.float64) for c in self.basis_columns])
        determinant = float(np.linalg.det(matrix))
        if abs(determinant - 1.0) > 1e-6:
            raise ContractError(
                "ply_to_world basis is not a proper rotation (det=%.9f); the frame "
                "mapping would mirror geometry and flip Gaussian handedness" % determinant
            )
        return matrix

    def matrix(self) -> np.ndarray:
        """Return the 3x4 mapping from **raw PLY** coordinates to Godot metres.

        Applies the builder's centroid subtraction, so this maps points as they
        are stored in the PLY file. Use it for landmarks and offline checks.
        """
        linear = self.linear_matrix()
        out = np.zeros((3, 4))
        out[:, :3] = linear
        out[:, 3] = -linear @ np.asarray(self.origin_ply_units, dtype=np.float64)
        return out

    def node_transform_matrix(self) -> np.ndarray:
        """Return the 3x4 transform to serialise onto a Godot node.

        Identical to :meth:`matrix` **except the translation is zero**, because
        the GDGS resource builder has already subtracted the centroid at import
        time. A node transform that reapplies it double-subtracts and shifts the
        room: it still imports, still renders, and is easy to miss by eye.
        """
        out = np.zeros((3, 4))
        out[:, :3] = self.linear_matrix()
        return out

    def linear_matrix(self) -> np.ndarray:
        """Return the 3x3 rotation-times-scale part of the mapping."""
        return self.rotation() * self.metres_per_unit

    def world_point(self, frame_point) -> np.ndarray:
        """Map a point in reconstruction units to Godot world metres."""
        point = self._as_vector(frame_point, "frame_point")
        return self.rotation() @ (point - np.asarray(self.origin_ply_units, dtype=np.float64)) * (
            self.metres_per_unit
        )

    def world_vector(self, frame_vector) -> np.ndarray:
        """Map a direction in reconstruction units to Godot world metres."""
        return self.rotation() @ self._as_vector(frame_vector, "frame_vector") * self.metres_per_unit

    def frame_up_in_world(self) -> np.ndarray:
        """Return the frame's up axis expressed in Godot world axes (unit length).

        Callers wanting only the *direction* should use this, not a basis column:
        the frame's up axis is not generally its y axis, so reading the wrong
        column can return a plausible-looking direction unrelated to gravity.
        """
        return self.rotation() @ (self.up_sign * AXIS_VECTORS[self.up_axis])

    def frame_axis_in_world(self, axis: str, sign: int = 1) -> np.ndarray:
        """Return a frame axis expressed in Godot world axes (unit length)."""
        return self.rotation() @ (sign * AXIS_VECTORS[axis])

    def is_proper_rotation(self) -> bool:
        """Whether the mapping is a rotation (det +1) rather than a mirror.

        Does not call :meth:`rotation`, so it reports ``False`` on a mirrored basis
        instead of raising -- callers use this to *ask* the question, and the
        mirror is the answer, not an error.
        """
        matrix = np.column_stack(
            [np.asarray(column, dtype=np.float64) for column in self.basis_columns]
        )
        return abs(float(np.linalg.det(matrix)) - 1.0) <= 1e-6

    def godot_transform(self) -> np.ndarray:
        """Return the equivalent 4x4 homogeneous matrix, for tests and docs."""
        out = np.eye(4)
        out[:3, :] = self.matrix()
        return out

    @staticmethod
    def _as_vector(value, label: str) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float64)
        if vector.shape != (3,):
            raise ContractError("%s must have 3 components" % label)
        return vector


@dataclass(frozen=True)
class ColliderBox:
    """Axis-aligned room bounds in Godot world metres, derived from the mapping."""

    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]
    floor_height: float
    ceiling_height: float
    derivation: str


@dataclass(frozen=True)
class SplatBounds:
    """Predicted world bounds of the Gaussian cloud, in Godot world metres.

    Recorded so the runtime verifier can compare *numbers* against what the
    renderer actually loaded, instead of accepting "the scene opened". Three
    bounds are kept because they answer different questions:

    * ``observed`` is the measured room interior: vertical extent from the
      floor/ceiling sheet offsets, horizontal from the opaque splats inside the
      training camera path. This is the region the floor and ceiling landmarks
      must sit on the extremes of -- the numeric form of "the right way up".
    * ``core`` is the whole camera-path window, which is *taller* than the room
      because the window is padded around the camera path. Landmarks belong
      inside it but must not touch its edges.
    * ``full`` includes far-field floaters and is far larger than either. The
      rendered AABB must match it numerically, which catches a stale imported
      ``.res`` cache or a scene still pointing at a different PLY.
    """

    observed_min: tuple[float, float, float]
    observed_max: tuple[float, float, float]
    core_min: tuple[float, float, float]
    core_max: tuple[float, float, float]
    full_min: tuple[float, float, float]
    full_max: tuple[float, float, float]
    splat_count: int


@dataclass(frozen=True)
class CameraPath:
    """Where the reconstruction cameras land in Godot world metres.

    The cameras are the one part of the frame that *no scene file contains*:
    the splat node, the collider and the spawn are all authored by hand, so
    without this the contract only ever checks the authored things against each
    other and the reconstruction the splat came from is never actually pinned
    down. Mapping them through the same ``ply_to_world`` makes the chain
    splatfacto trained against -> exported PLY -> Godot metres explicit, and
    gives the runtime verifier something to compare the room against that was
    not itself derived from the room.

    Heights are kept separately because they are the strongest available check on
    the up axis: a camera walking a corridor sits between the floor and the
    ceiling, and that is true in the reconstruction frame only if the measured up
    axis was the right one.
    """

    count: int
    world_min: tuple[float, float, float]
    world_max: tuple[float, float, float]
    height_min_m: float
    height_mean_m: float
    height_max_m: float
    source: str

    def validate(self, room: "ColliderBox") -> None:
        """Raise :class:`ContractError` if the path is malformed or contradicts the room.

        Well-formedness is checked first, and deliberately before containment: an
        inverted bound would otherwise be reported as "outside the room", which
        sends a reviewer hunting for a coordinate bug instead of a corrupt record.
        """
        if self.count <= 0:
            raise ContractError("the camera path must contain at least one camera")
        low = np.asarray(self.world_min, dtype=np.float64)
        high = np.asarray(self.world_max, dtype=np.float64)
        if np.any(low > high):
            raise ContractError(
                "camera path bounds are inverted: min %s is above max %s"
                % (low.round(4).tolist(), high.round(4).tolist())
            )
        if not room.floor_height <= self.height_min_m <= self.height_max_m <= room.ceiling_height:
            raise ContractError(
                "camera heights %.4f..%.4f m do not sit between the floor (%.4f m) "
                "and the ceiling (%.4f m); the mapped up axis cannot be right"
                % (self.height_min_m, self.height_max_m,
                   room.floor_height, room.ceiling_height)
            )
        if not self.inside_room(room, CAMERA_ROOM_SLACK_M):
            raise ContractError(
                "the reconstruction cameras (%d, %s .. %s, heights %.4f..%.4f m) do not "
                "lie inside the room %s .. %s; the camera path and the measured room "
                "were derived from different frames"
                % (self.count, low.round(4).tolist(), high.round(4).tolist(),
                   self.height_min_m, self.height_max_m,
                   np.round(room.min_corner, 4).tolist(),
                   np.round(room.max_corner, 4).tolist())
            )
        eye = self.height_mean_m - room.floor_height
        if not EYE_HEIGHT_RANGE_M[0] <= eye <= EYE_HEIGHT_RANGE_M[1]:
            raise ContractError(
                "the mean camera height is %.4f m above the floor, outside the "
                "plausible walking eye-height range %s; either the scale or the up "
                "axis is wrong" % (eye, EYE_HEIGHT_RANGE_M)
            )

    def inside_room(self, room: "ColliderBox", tolerance: float) -> bool:
        """Whether the whole camera path lies within the room's bounds.

        ``tolerance`` widens the room on every axis, so a capture whose cameras
        grazed a wall during the walk does not invalidate the contract.
        """
        low = np.asarray(room.min_corner, dtype=np.float64)
        high = np.asarray(room.max_corner, dtype=np.float64)
        here = np.asarray(self.world_min, dtype=np.float64)
        there = np.asarray(self.world_max, dtype=np.float64)
        if np.any(here < low - tolerance) or np.any(there > high + tolerance):
            return False
        return (
            self.height_min_m >= room.floor_height - tolerance
            and self.height_max_m <= room.ceiling_height + tolerance
        )


@dataclass(frozen=True)
class FrameContract:
    """The whole contract for one scene."""

    schema_version: int
    scene_id: str
    ply_to_world: PlyToWorld
    scale_reference: ScaleReference
    automatic_transforms: tuple[AutomaticTransform, ...]
    landmarks: dict[str, tuple[float, float, float]]
    collider: ColliderBox
    splat_bounds: SplatBounds
    cameras: CameraPath
    spawn: tuple[float, float, float]
    spawn_clearance_m: float
    asset: dict[str, Any] = field(default_factory=dict)
    capture: dict[str, Any] = field(default_factory=dict)
    rejected_scales: tuple[dict[str, str], ...] = ()
    notes: str = ""

    def validate(self) -> None:
        """Raise :class:`ContractError` if any part of the contract disagrees."""
        if self.schema_version != SCHEMA_VERSION:
            raise ContractError(
                "manifest schema_version %d is not supported (expected %d)"
                % (self.schema_version, SCHEMA_VERSION)
            )
        if self.ply_to_world.metres_per_unit <= 0.0:
            raise ContractError("metres_per_unit must be positive")
        if self.ply_to_world.up_sign not in (1, -1):
            raise ContractError("up_sign must be +1 or -1")
        if self.ply_to_world.handedness != "right":
            raise ContractError("only right-handed source frames are supported")
        expected = self.scale_reference.target_metres / self.scale_reference.raw_units
        if abs(expected - self.ply_to_world.metres_per_unit) > 1e-4 * max(expected, 1.0):
            raise ContractError(
                "metres_per_unit %.6f disagrees with its reference: %.6f raw units "
                "should be %.3f m, giving %.6f m/unit"
                % (
                    self.ply_to_world.metres_per_unit,
                    self.scale_reference.raw_units,
                    self.scale_reference.target_metres,
                    expected,
                )
            )
        up_world = self.ply_to_world.frame_up_in_world()
        if float(np.linalg.norm(up_world - AXIS_VECTORS["y"])) > 1e-6:
            raise ContractError(
                "frame up %+s%s does not map onto Godot +Y (got %s)"
                % (self.ply_to_world.up_sign, self.ply_to_world.up_axis, np.round(up_world, 6).tolist())
            )
        floor = self.collider.floor_height
        ceiling = self.collider.ceiling_height
        if not ceiling > floor:
            raise ContractError("collider ceiling %.4f is not above floor %.4f" % (ceiling, floor))
        floor_y = float(self.landmark("floor")[1])
        ceiling_y = float(self.landmark("ceiling")[1])
        if not np.isclose(floor_y, floor, atol=1e-6):
            raise ContractError(
                "floor landmark is at y=%.6f but the collider floor is at %.6f" % (floor_y, floor)
            )
        if not np.isclose(ceiling_y, ceiling, atol=1e-6):
            raise ContractError(
                "ceiling landmark is at y=%.6f but the collider ceiling is at %.6f"
                % (ceiling_y, ceiling)
            )
        for name in ("floor", "ceiling", "room_centre"):
            if name not in self.landmarks:
                raise ContractError("manifest is missing the %r landmark" % name)
        self._check_landmarks_inside_room()
        self._check_camera_path()

    def _check_camera_path(self) -> None:
        """Require the reconstruction cameras to agree with the room they imply.

        The camera path is measured from the COLMAP model and the room from the
        splat, so the two are independent records. If the cameras do not land
        inside the room, then the mapping, the room box, or the measured up axis
        is wrong -- and none of those is visible from inside a single scene.
        """
        self.cameras.validate(self.collider)

    def _check_landmarks_inside_room(self) -> None:
        """Require every landmark and the spawn to lie within the collider bounds.

        A landmark outside the room bounds means the mapping and the collider were
        derived from different things, which is the whole class of bug this
        contract exists to rule out.
        """
        low = np.asarray(self.collider.min_corner, dtype=np.float64)
        high = np.asarray(self.collider.max_corner, dtype=np.float64)
        for name in sorted(self.landmarks):
            point = self.landmark(name)
            if np.any(point < low - 1e-6) or np.any(point > high + 1e-6):
                raise ContractError(
                    "landmark %r at %s lies outside the collider room %s .. %s"
                    % (name, np.round(point, 4).tolist(), low.round(4).tolist(), high.round(4).tolist())
                )
        spawn = np.asarray(self.spawn, dtype=np.float64)
        if np.any(spawn < low - 1e-6) or np.any(spawn > high + 1e-6):
            raise ContractError(
                "spawn %s lies outside the collider room %s .. %s"
                % (spawn.round(4).tolist(), low.round(4).tolist(), high.round(4).tolist())
            )
        expected = self.collider.floor_height + self.spawn_clearance_m
        if not np.isclose(spawn[1], expected, atol=1e-6):
            raise ContractError(
                "spawn y=%.6f is not %.6f m above the floor at %.6f"
                % (spawn[1], self.spawn_clearance_m, self.collider.floor_height)
            )

    def landmark(self, name: str) -> np.ndarray:
        """Return a named landmark in Godot world metres."""
        if name not in self.landmarks:
            raise ContractError("no landmark named %r (have %s)" % (name, ", ".join(sorted(self.landmarks))))
        return np.asarray(self.landmarks[name], dtype=np.float64)

    def landmark_distance(self, first: str, second: str) -> float:
        """Return the world-space distance between two landmarks, in metres."""
        return float(np.linalg.norm(self.landmark(first) - self.landmark(second)))

    def collider_height(self, fraction: float) -> float:
        """Interpolate between the floor and ceiling heights."""
        return self.collider.floor_height + fraction * (
            self.collider.ceiling_height - self.collider.floor_height
        )

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of the whole contract."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FrameContract":
        """Rebuild a contract from :meth:`to_json` output."""
        contract = cls(
            schema_version=int(data["schema_version"]),
            scene_id=str(data["scene_id"]),
            ply_to_world=PlyToWorld(**data["ply_to_world"]),
            scale_reference=ScaleReference(**data["scale_reference"]),
            automatic_transforms=tuple(
                AutomaticTransform(**entry) for entry in data.get("automatic_transforms", ())
            ),
            landmarks={k: tuple(v) for k, v in data.get("landmarks", {}).items()},
            collider=ColliderBox(**data["collider"]),
            splat_bounds=SplatBounds(**data["splat_bounds"]),
            cameras=_camera_from_json(data["cameras"]),
            spawn=tuple(data["spawn"]),
            spawn_clearance_m=float(data["spawn_clearance_m"]),
            asset=data.get("asset", {}),
            capture=data.get("capture", {}),
            rejected_scales=tuple(data.get("rejected_scales", ())),
            notes=data.get("notes", ""),
        )
        contract.validate()
        return contract

    @classmethod
    def load(cls, path: str | Path) -> "FrameContract":
        """Load and validate a manifest from disk."""
        resolved = Path(path)
        with resolved.open(encoding="utf-8") as handle:
            return cls.from_json(json.load(handle))

    def save(self, path: str | Path) -> Path:
        """Write the manifest as pretty-printed JSON and return the path."""
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with resolved.open("w", encoding="utf-8") as handle:
            json.dump(self.to_json(), handle, indent=2, sort_keys=False)
            handle.write("\n")
        return resolved