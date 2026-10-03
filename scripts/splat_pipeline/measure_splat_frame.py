#!/usr/bin/env python3
"""Measure a splat scene's frame and emit its alignment manifest.

Reads the three records that actually define the frame, and never guesses:

* the **PLY** -- where the Gaussian centres, scales and rotations are
* the **COLMAP sparse model** -- the poses splatfacto trained against, the only
  record of which reconstruction axis points at the floor
* the **nerfstudio dataparser transform** -- the similarity that connects the
  COLMAP frame to the exported PLY frame

Output is one ``FrameContract`` JSON, read at runtime by
``godot_walk/scripts/splat_alignment.gd``.  Re-running after a re-train must
reproduce the same frame; a changed up axis or scale is then a reviewable diff
rather than silent drift.

Usage::

    python3 scripts/splat_pipeline/measure_splat_frame.py \\
        --ply godot_walk/assets/corridor_splat/corridor.ply \\
        --colmap-model data/scenes/corridor_travel/sparse/0 \\
        --dataparser-transforms outputs/corridor_travel_v1/splatfacto/<run>/dataparser_transforms.json \\
        --scene-id corridor_splat --target-clear-height 2.40 \\
        --out godot_walk/assets/corridor_splat/alignment_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import colmap_model  # noqa: E402
import frame_axes  # noqa: E402
import splat_geometry  # noqa: E402
import splat_ply  # noqa: E402
from manifest_rules import automatic_transforms, rejected_scales  # noqa: E402
from splat_frame import (  # noqa: E402
    SCHEMA_VERSION,
    CameraPath,
    ColliderBox,
    FrameContract,
    PlyToWorld,
    ScaleReference,
    SplatBounds,
)

# Half-extent of the analysis window around the training camera path, in
# reconstruction units.  Splatfacto only reconstructs what it saw, so a window
# that reaches past the camera path admits far-field floaters into the planes.
CORE_MARGIN = np.array([0.9, 0.9, 0.6])

SPAWN_CLEARANCE_M = 0.5
MIN_CORE_SPLATS = 5000


@dataclass(frozen=True)
class Measurement:
    """Raw measurements taken from the PLY and COLMAP model, before any metric decision."""

    splat_count: int
    md5: str
    builder_centroid: tuple[float, float, float]
    core_count: int
    core_min: np.ndarray
    core_max: np.ndarray
    full_min: np.ndarray
    full_max: np.ndarray
    floor_frame: float
    ceiling_frame: float
    width_low_frame: float
    width_high_frame: float
    height_units: float
    height_spread: float
    height_stations: int
    up_axis: int
    up_sign: int
    width_axis: int
    up_evidence: dict
    camera_ply: np.ndarray


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ply", required=True, help="the exported 3DGS PLY")
    parser.add_argument("--colmap-model", required=True, help="COLMAP sparse model directory")
    parser.add_argument("--dataparser-transforms", required=True, help="nerfstudio dataparser_transforms.json")
    parser.add_argument("--scene-id", required=True, help="scene name recorded in the manifest")
    parser.add_argument("--asset-path", default="", help="res:// path recorded for the PLY")
    parser.add_argument("--source-path", default="", help="provenance path for the PLY")
    parser.add_argument("--video", default="", help="source footage, when known")
    parser.add_argument("--footage-kind", default="synthetic", choices=("synthetic", "real"))
    parser.add_argument(
        "--target-clear-height",
        type=float,
        required=True,
        help="chosen (synthetic) floor-to-ceiling height in metres",
    )
    parser.add_argument(
        "--measured-reference",
        type=float,
        default=None,
        help="real-world floor-to-ceiling distance observed in real footage, in metres",
    )
    parser.add_argument("--out", required=True, help="manifest path to write")
    return parser.parse_args(argv)


def load_dataparser(path: str) -> dict:
    """Return the COLMAP->training similarity nerfstudio recorded for the run."""
    with Path(path).open(encoding="utf-8") as handle:
        raw = json.load(handle)
    transform = np.asarray(raw["transform"], dtype=np.float64)
    if transform.shape != (3, 4):
        raise SystemExit("ERROR: %s is not a 3x4 transform" % path)
    return {"rotation": transform[:, :3], "origin": transform[:, 3], "scale": float(raw["scale"])}


def cameras_in_ply_frame(images, dataparser: dict) -> np.ndarray:
    """Return registered camera centres expressed in exported-PLY units."""
    centres = colmap_model.camera_centers(images)
    return (centres @ dataparser["rotation"].T + dataparser["origin"]) * dataparser["scale"]


def measure_up_axis(images, dataparser: dict) -> tuple[int, int, dict]:
    """Return ``(axis_index, sign, evidence)`` for the exported frame's up axis."""
    up_colmap = colmap_model.dominant_up_direction(images)
    up_ply = (dataparser["rotation"] @ up_colmap) * dataparser["scale"]
    norm = float(np.linalg.norm(up_ply))
    if norm < 1e-9:
        raise SystemExit("ERROR: measured up direction collapsed to zero")
    up_ply = up_ply / norm
    index = int(np.argmax(np.abs(up_ply)))
    share = abs(float(up_ply[index]))
    if share < 0.9:
        raise SystemExit(
            "ERROR: measured up direction %s is not dominated by one axis (share %.3f); "
            "refusing to invent a frame for a tilted reconstruction"
            % (np.round(up_ply, 6).tolist(), share)
        )
    return index, (1 if up_ply[index] >= 0.0 else -1), {
        "colmap_up": up_colmap.tolist(),
        "ply_frame_up": up_ply.tolist(),
        "principal_axis": frame_axes.AXIS_NAMES[index],
        "principal_share": share,
        "registered_images": len(images),
        "method": "mean registered-camera up axis mapped through the nerfstudio "
        "dataparser transform (COLMAP y-down world -> exported frame)",
    }


def core_window(cameras: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the ``(low, high)`` analysis window hugging the camera path."""
    return cameras.min(axis=0) - CORE_MARGIN, cameras.max(axis=0) + CORE_MARGIN


def camera_path(
    cameras_ply: np.ndarray, mapping: PlyToWorld, source: str
) -> CameraPath:
    """Map reconstruction cameras through the contract and summarise where they land.

    Only the bound and the height band are kept, not the poses: a manifest
    carrying 192 positions would drift out of step with the PLY on every retrain
    for no reviewer benefit, while the bound and the band are exactly what proves
    the chain COLMAP -> exported PLY -> Godot metres is closed.
    """
    if cameras_ply.size == 0:
        raise SystemExit("ERROR: no registered cameras to map into world metres")
    world = np.stack([mapping.world_point(tuple(point)) for point in cameras_ply])
    heights = world[:, 1]
    return CameraPath(
        count=int(world.shape[0]),
        world_min=tuple(float(v) for v in world.min(axis=0)),
        world_max=tuple(float(v) for v in world.max(axis=0)),
        height_min_m=float(heights.min()),
        height_mean_m=float(heights.mean()),
        height_max_m=float(heights.max()),
        source=source,
    )


def camera_source(args: "argparse.Namespace", count: int) -> str:
    """Return the provenance string recorded alongside the camera path."""
    return (
        "%d registered cameras mapped through the nerfstudio dataparser transform "
        "(%s) then through ply_to_world" % (count, args.colmap_model)
    )


def camera_path_report(cameras: CameraPath, collider: ColliderBox) -> str:
    """Return a one-line summary of where the reconstruction cameras landed."""
    return (
        "%d cameras, %s .. %s, heights %.3f .. %.3f m (mean %.3f m = %.2f m above the "
        "floor)"
        % (
            cameras.count,
            tuple(round(v, 3) for v in cameras.world_min),
            tuple(round(v, 3) for v in cameras.world_max),
            cameras.height_min_m,
            cameras.height_max_m,
            cameras.height_mean_m,
            cameras.height_mean_m - collider.floor_height,
        )
    )


def measure(ply_path: Path, model_dir: str, dataparser_path: str) -> Measurement:
    """Take every raw measurement the contract needs."""
    images = colmap_model.read_images(model_dir)
    if not images:
        raise SystemExit("ERROR: %s has no registered images" % model_dir)
    dataparser = load_dataparser(dataparser_path)

    points = splat_ply.read_positions(ply_path)
    alphas = splat_ply.read_alphas(ply_path)
    columns = splat_ply.read_columns(
        ply_path, ("scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")
    )
    finite = np.isfinite(points).all(axis=1)
    # The camera path is mapped into exported-PLY units here, not world metres:
    # world metres depend on metres_per_unit, which is not decided until the floor
    # and ceiling have been measured. Keeping it in frame units lets the contract
    # map it through the same ply_to_world as every other record, which is what
    # makes "the cameras agree with the room" a check rather than an assertion.
    camera_centres = cameras_in_ply_frame(images, dataparser)
    low, high = core_window(camera_centres)
    inside = ((points >= low) & (points <= high)).all(axis=1)
    keep = finite & inside & (alphas > 0.5)
    if int(keep.sum()) < MIN_CORE_SPLATS:
        raise SystemExit(
            "ERROR: only %d opaque splats inside the camera-path window (need %d)"
            % (int(keep.sum()), MIN_CORE_SPLATS)
        )
    core = points[keep]
    normals = splat_geometry.gaussian_normal_axes(np.exp(columns[keep, :3]), columns[keep, 3:7])

    up_axis, up_sign, evidence = measure_up_axis(images, dataparser)
    try:
        lower, upper, spread, stations = splat_geometry.measure_room_bounds(core, normals, up_axis)
    except splat_geometry.MeasurementError as error:
        raise SystemExit(
            "ERROR: could not measure floor and ceiling on the measured up axis %s: %s"
            % (frame_axes.AXIS_NAMES[up_axis], error)
        ) from error
    height = float(upper.offset - lower.offset)
    # Offsets are low/high by position, not by facing: a covariance encodes an
    # axis, never a facing, so only the measured up sign says which one is the floor.
    floor_frame = lower.offset if up_sign > 0 else upper.offset
    ceiling_frame = upper.offset if up_sign > 0 else lower.offset

    # The width axis is only *tried*; a capture whose walls are not resolvable
    # reports width_axis = -1 and the room box falls back to the measured splat
    # extent on both horizontal axes.  That is the honest outcome, not a failure:
    # pretending to measure walls we cannot see is how colliders drift by eye.
    width_axis = _width_axis(core, normals, up_axis)
    if width_axis < 0:
        width_low = width_high = float("nan")
    else:
        width_low, width_high = _wall_offsets(core, normals, width_axis)
    return Measurement(
        splat_count=len(points),
        md5=md5(ply_path),
        builder_centroid=tuple(float(v) for v in points[finite].mean(axis=0)),
        core_count=int(keep.sum()),
        core_min=core.min(axis=0),
        core_max=core.max(axis=0),
        # The full extent includes floaters; the renderer will load all of them, so
        # the manifest predicts it too and the runtime verifier compares it numerically.
        full_min=points[finite].min(axis=0),
        full_max=points[finite].max(axis=0),
        floor_frame=floor_frame,
        ceiling_frame=ceiling_frame,
        width_low_frame=width_low,
        width_high_frame=width_high,
        height_units=height,
        height_spread=spread,
        height_stations=stations,
        up_axis=up_axis,
        up_sign=up_sign,
        width_axis=width_axis,
        up_evidence=evidence,
        camera_ply=camera_centres,
    )


def _width_axis(core, normals, up_axis: int) -> int:
    """Return the horizontal axis whose surfaces are clear enough to measure, or -1.

    Picking the axis with the strongest bimodality beats picking by bounding-box
    width, which a long corridor wins on the axis you do not want.  When no axis
    clears the contrast bar the function returns -1 and the caller reports that
    the room's width was not measured, instead of inventing it.
    """
    strengths = {
        candidate: splat_geometry.measure_plane_strength(core, normals, candidate)
        for candidate in sorted({0, 1, 2} - {up_axis})
    }
    best = max(strengths, key=lambda index: strengths[index])
    if strengths[best] < splat_geometry.MIN_MODE_CONTRAST:
        return -1
    return best


def _mapping_width_axis(measurement: Measurement) -> int:
    """Return the frame axis the contract treats as horizontal width.

    Falls back to the wider of the two horizontal extents when no wall pair was
    measurable, so the mapping still has a well-defined width/depth assignment
    even on a capture whose walls are only a blob.
    """
    if measurement.width_axis >= 0:
        return measurement.width_axis
    up_axis = measurement.up_axis
    extents = measurement.core_max - measurement.core_min
    extents[up_axis] = -1.0
    return int(np.argmax(extents))


def _wall_offsets(core, normals, width_axis: int) -> tuple[float, float]:
    """Return the two measured wall-plane offsets, low first."""
    try:
        lower, upper = splat_geometry.measure_plane_pair(core, normals, width_axis, 0.02, 0.05)
    except splat_geometry.MeasurementError as error:
        raise SystemExit(
            "ERROR: could not resolve both wall planes on %s: %s"
            % (frame_axes.AXIS_NAMES[width_axis], error)
        ) from error
    return lower.offset, upper.offset


def target_metres(args: argparse.Namespace) -> float:
    """Return the metric target, refusing an unmeasured scale on real footage."""
    if args.footage_kind == "real":
        if args.measured_reference is None:
            raise SystemExit("ERROR: --footage-kind real requires --measured-reference")
        return float(args.measured_reference)
    return float(args.target_clear_height)


def build_contract(measurement: Measurement, args: argparse.Namespace) -> FrameContract:
    """Assemble the manifest from raw measurements plus the recorded decisions."""
    target = target_metres(args)
    basis = frame_axes.world_basis_for(
        measurement.up_axis, _mapping_width_axis(measurement), measurement.up_sign
    )
    mapping = PlyToWorld(
        basis_columns=tuple(tuple(float(v) for v in column) for column in basis.T),
        metres_per_unit=target / measurement.height_units,
        origin_ply_units=measurement.builder_centroid,
        frame_name="nerfstudio_export",
        up_axis=frame_axes.AXIS_NAMES[measurement.up_axis],
        up_sign=measurement.up_sign,
        handedness="right",
    )
    reference = ScaleReference(
        kind="measured_reference" if args.footage_kind == "real" else "chosen",
        quantity="floor_to_ceiling_clear_height",
        raw_units=measurement.height_units,
        raw_units_spread=measurement.height_spread,
        raw_units_spread_samples=measurement.height_stations,
        target_metres=target,
        reason=_scale_reason(args, measurement),
    )
    collider, landmarks, spawn = room_from_measurement(mapping, measurement)
    contract = FrameContract(
        schema_version=SCHEMA_VERSION,
        scene_id=args.scene_id,
        ply_to_world=mapping,
        scale_reference=reference,
        automatic_transforms=automatic_transforms(),
        landmarks=landmarks,
        collider=collider,
        splat_bounds=splat_bounds(mapping, measurement, collider),
        cameras=build_camera_path(measurement, mapping, args),
        spawn=spawn,
        spawn_clearance_m=SPAWN_CLEARANCE_M,
        asset=_asset_record(args, measurement),
        capture=_capture_record(args, measurement),
        rejected_scales=rejected_scales(),
        notes=(
            "ply_to_world.matrix() maps raw PLY coordinates to world metres and "
            "includes the centroid subtraction. node_transform_matrix() is what a "
            "Godot node carries: identical except the translation is ZERO, because "
            "the GDGS resource builder has already subtracted the mean Gaussian centre "
            "at import. Reapplying the centroid on the node would double-subtract it "
            "and shift the room while still importing and rendering. The mapping is a "
            "pure rotation times one uniform scale, so Gaussian orientations, "
            "covariances and extents all stay correct under the renderer's "
            "M3 * covariance * M3^T; nothing is baked into the PLY. The exported "
            "frame's up axis and Godot's differ by a -90 degree rotation about x, and "
            "both scenes must apply this basis explicitly: equal serialised transforms "
            "are not evidence of equal effective world mapping."
        ),
    )
    contract.validate()
    return contract


def build_camera_path(
    measurement: Measurement, mapping: PlyToWorld, args: argparse.Namespace
) -> CameraPath:
    """Return the reconstruction camera path, mapped into Godot world metres.

    Mapped through the same ``ply_to_world`` as the splat, the collider and the
    spawn, so the runtime verifier can require that all four agree. The cameras
    come from the COLMAP model rather than from the PLY, which makes this the one
    check in the contract that is not the room validating itself.

    The poses are not stored, only where they land and how high they sit: enough
    to prove the frame is closed, small enough that the manifest stays reviewable
    and does not become a second camera database to keep in sync.
    """
    return camera_path(
        measurement.camera_ply,
        mapping,
        camera_source(args, len(measurement.camera_ply)),
    )


def room_from_measurement(mapping: PlyToWorld, measurement: Measurement):
    """Return ``(collider, landmarks, spawn)`` derived from the measured planes.

    Floor and ceiling heights come from the measured sheet offsets; the horizontal
    extents come from the opaque splats inside the camera-path window.  Nothing
    here is a per-face guess, which is what makes the result reviewable.
    """
    def to_world(axes: dict[int, float]) -> np.ndarray:
        """Map a frame point, centring any axis the caller did not pin down.

        A landmark has to name one specific point, so an axis left unspecified
        resolves to the midpoint of the measured extent rather than to zero --
        otherwise "floor" would be a point on the floor somewhere off to one side
        and its distance to anything else would look arbitrary.
        """
        frame = 0.5 * (measurement.core_min + measurement.core_max)
        for index, value in axes.items():
            frame[index] = value
        return mapping.world_point(tuple(frame))

    up_axis = frame_axes.axis_index(mapping.up_axis)
    width_axis = _mapping_width_axis(measurement)
    length_axis = frame_axes.remaining_axis(up_axis, width_axis)
    width_centre = (
        0.5 * (measurement.width_low_frame + measurement.width_high_frame)
        if measurement.width_axis >= 0
        else float(0.5 * (measurement.core_min[width_axis] + measurement.core_max[width_axis]))
    )
    floor = to_world({up_axis: measurement.floor_frame, width_axis: width_centre})
    ceiling = to_world({up_axis: measurement.ceiling_frame, width_axis: width_centre})
    low = to_world({
        up_axis: measurement.floor_frame,
        width_axis: measurement.core_min[width_axis],
        length_axis: measurement.core_min[length_axis],
    })
    high = to_world({
        up_axis: measurement.ceiling_frame,
        width_axis: measurement.core_max[width_axis],
        length_axis: measurement.core_max[length_axis],
    })
    corner_low, corner_high = np.minimum(low, high), np.maximum(low, high)
    collider = ColliderBox(
        min_corner=tuple(float(v) for v in corner_low),
        max_corner=tuple(float(v) for v in corner_high),
        floor_height=float(floor[1]),
        ceiling_height=float(ceiling[1]),
        derivation="Floor/ceiling from the measured sheet offsets; horizontal extents from "
        "the opaque splats inside the camera-path window; all mapped through ply_to_world.",
    )
    landmarks = {
        "floor": tuple(float(v) for v in floor),
        "ceiling": tuple(float(v) for v in ceiling),
        "room_centre": tuple(float(v) for v in 0.5 * (corner_low + corner_high)),
    }
    spawn = (
        float(0.5 * (corner_low[0] + corner_high[0])),
        collider.floor_height + SPAWN_CLEARANCE_M,
        float(0.5 * (corner_low[2] + corner_high[2])),
    )
    return collider, landmarks, spawn


def splat_bounds(
    mapping: PlyToWorld, measurement: Measurement, collider: ColliderBox
) -> SplatBounds:
    """Return predicted world bounds for the observed room, core and whole cloud.

    The full extent is what the renderer actually loads, so predicting it lets the
    runtime verifier catch a stale imported ``.res`` cache or a scene still
    pointing at a different PLY -- both of which pass an import check and a
    screenshot while showing the wrong geometry.
    """
    observed_low = np.asarray(collider.min_corner)
    observed_high = np.asarray(collider.max_corner)
    core_low, core_high = _mapped_corners(mapping, measurement.core_min, measurement.core_max)
    full_low, full_high = _mapped_corners(mapping, measurement.full_min, measurement.full_max)
    return SplatBounds(
        observed_min=tuple(float(v) for v in observed_low),
        observed_max=tuple(float(v) for v in observed_high),
        core_min=core_low,
        core_max=core_high,
        full_min=full_low,
        full_max=full_high,
        splat_count=measurement.splat_count,
    )


def _mapped_corners(mapping: PlyToWorld, low, high) -> tuple:
    """Return the world-space ``(min, max)`` of a reconstruction-frame box.

    All eight corners are mapped, not just two opposite ones: the world bounds of
    a rotated box are strictly larger than the mapped box, and using only the low
    and high corners understates the extent by up to a factor of two on an axis.
    """
    corners = [
        mapping.world_point((
            low[0] if (index & 1) else high[0],
            low[1] if (index & 2) else high[1],
            low[2] if (index & 4) else high[2],
        ))
        for index in range(8)
    ]
    stacked = np.stack(corners)
    return tuple(float(v) for v in stacked.min(axis=0)), tuple(float(v) for v in stacked.max(axis=0))


def _asset_record(args: argparse.Namespace, measurement: Measurement) -> dict:
    return {
        "resource_path": args.asset_path,
        "source_path": args.source_path,
        "md5": measurement.md5,
        "splat_count": measurement.splat_count,
        "ply_header": dict(splat_ply.header_comments(args.ply)),
        "builder_centroid_ply": list(measurement.builder_centroid),
        "up_axis_evidence": measurement.up_evidence,
    }


def _capture_record(args: argparse.Namespace, measurement: Measurement) -> dict:
    return {
        "footage_kind": args.footage_kind,
        "video": args.video,
        "colmap_model": args.colmap_model,
        "nerfstudio_dataparser_transforms": args.dataparser_transforms,
        "core_window_splats": measurement.core_count,
        "core_bounds_ply_units": [measurement.core_min.tolist(), measurement.core_max.tolist()],
        "walls_measured": measurement.width_axis >= 0,
        "width_note": (
            "Wall planes measured on frame axis %s (separation %.5f units = %.3f m)"
            % (
                frame_axes.AXIS_NAMES[measurement.width_axis],
                measurement.width_high_frame - measurement.width_low_frame,
                (measurement.width_high_frame - measurement.width_low_frame)
                * (target_metres(args) / measurement.height_units),
            )
            if measurement.width_axis >= 0
            else "Wall planes were NOT resolved: no horizontal axis showed two surfaces "
            "above the %.1fx density-contrast threshold (see splat_geometry.MIN_MODE_"
            "CONTRAST). The room's horizontal extents therefore come from the measured "
            "splat extent inside the camera-path window, not from measured wall offsets. "
            "Treat them as observation bounds, not as a measured room."
            % splat_geometry.MIN_MODE_CONTRAST
        ),
    }


def _scale_reason(args: argparse.Namespace, measurement: Measurement) -> str:
    if args.footage_kind == "real":
        return (
            "Real footage: metres_per_unit divides a measured real-world floor-to-ceiling "
            "distance (%.3f m) by the reconstructed height (%.5f reconstruction units). "
            "Tolerance is two standard deviations of that height across %d independent "
            "corridor stations." % (target_metres(args), measurement.height_units, measurement.height_stations)
        )
    return (
        "Synthetic footage (%s): generated frames contain no real-world reference, so this "
        "is an explicit choice, not a measurement. The reconstructed floor-to-ceiling "
        "height is %.5f reconstruction units (spread %.5f over %d corridor stations) and "
        "the corridor is declared to have a %.2f m clear height. Re-decide it when real "
        "footage lands; never inherit a factor from a retired mesh."
        % (
            args.video or "unspecified video",
            measurement.height_units,
            measurement.height_spread,
            measurement.height_stations,
            args.target_clear_height,
        )
    )


def md5(path: Path) -> str:
    """Return the MD5 of a file, used as a provenance fingerprint only."""
    digest = hashlib.md5()  # noqa: S324 - provenance, not a security control
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Measure the scene and write its alignment manifest."""
    args = parse_args(argv)
    measurement = measure(Path(args.ply), args.colmap_model, args.dataparser_transforms)
    contract = build_contract(measurement, args)
    written = contract.save(args.out)
    reference = contract.scale_reference
    print("wrote %s" % written)
    print("  up axis         : %+s%s (exported frame), width axis %s%s"
          % (measurement.up_sign, contract.ply_to_world.up_axis,
             frame_axes.AXIS_NAMES[_mapping_width_axis(measurement)],
             "" if measurement.width_axis >= 0 else " (fallback: walls unmeasured)"))
    print("  metres per unit : %.6f  [%s]  clear height %.5f +/- %.5f units -> %.2f m"
          % (contract.ply_to_world.metres_per_unit, reference.kind, reference.raw_units,
             reference.raw_units_spread, reference.target_metres))
    print("  tolerance       : %.4f m on %s" % (reference.tolerance_metres, reference.quantity))
    print("  floor / ceiling : %.4f m / %.4f m" % (contract.collider.floor_height, contract.collider.ceiling_height))
    print("  room bounds     : %s .. %s"
          % (tuple(round(v, 4) for v in contract.collider.min_corner),
             tuple(round(v, 4) for v in contract.collider.max_corner)))
    print("  walls measured  : %s" % ("yes" if measurement.width_axis >= 0 else "NO (see capture.width_note)"))
    print("  camera path     : %s" % camera_path_report(contract.cameras, contract.collider))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())