"""Run CPU-only held-out checks for the locked Route A correction."""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

import cv2
import numpy as np

from hunyuan_depth_correction_data import (
    CEILING_Y,
    FLOOR_Y,
    RaySamples,
    collect_frame_samples,
    make_camera_context,
)
from hunyuan_depth_correction_mesh import (
    classify_plane_regions,
    plane_snapped_world_positions,
    radial_world_positions,
    read_mesh_grid,
    seam_integrity,
    write_corrected_ply,
)
from hunyuan_depth_correction_model import ScaleField, fit_scale_field
from hunyuan_depth_correction_visibility import collect_cross_frame_floor_samples

EVIDENCE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVIDENCE_DIR.parents[2]
DEFAULT_OUTPUT = EVIDENCE_DIR / "hunyuan_depth_correction_frame_141.json"
DEFAULT_SOURCE = REPO_ROOT / "data/scenes/corridor_travel/images/frame_0141.jpg"
DEFAULT_MESH = REPO_ROOT / "data/track-a/hunyuan/scene-run-05/mesh_layer1.ply"
DEFAULT_MASK = REPO_ROOT / "data/track-a/hunyuan/scene-run-05/fg1_mask.png"
DEFAULT_COLMAP = REPO_ROOT / "data/scenes/corridor_travel/sparse/0"
DEFAULT_DATAPARSER = REPO_ROOT / "data/track-a/hunyuan/dataparser_transforms.json"
DEFAULT_ALIGNMENT = REPO_ROOT / "godot_walk/assets/corridor_splat/alignment_manifest.json"
DEFAULT_CALIBRATION = EVIDENCE_DIR / "calibration_manifest_frame_141.json"
DEFAULT_MESH_OUTPUT = REPO_ROOT / "data/track-a/hunyuan/route-a-visual-correction-frame-141"
EXPECTED_ACCEPTANCE_HASH = "8495b08fbfeff739beacfc8fe2961ce81eb3ba485425ada890788b7edb56b4af"
PARAMETER_COUNT = 6
K_FOLDS = 5
RANDOM_SEED = 142
MAX_PLANE_Q90_M = 0.05
FLOOR_GOAL_Q90_M = 0.03
BANDS = {"top": (0.0, 0.45), "middle": (0.45, 0.55), "bottom_floor_side": (0.55, 1.0)}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_locked_acceptance(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    acceptance = manifest["visual_depth_correction_acceptance"]
    digest = hashlib.sha256(
        json.dumps(acceptance, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != EXPECTED_ACCEPTANCE_HASH or digest != manifest.get(
        "visual_depth_correction_acceptance_sha256"
    ):
        raise ValueError("locked acceptance block hash does not match")
    if manifest.get("registration_accepted") or manifest.get("scale_calibrated"):
        raise ValueError("calibration flags must remain false during visual correction")
    if acceptance["smooth_scale_field"]["parameter_count"] != PARAMETER_COUNT:
        raise ValueError("locked parameter count differs from this evaluator")
    return manifest


def _plane_metrics(residual: np.ndarray) -> dict:
    if not len(residual):
        return {"count": 0, "signed_median_m": None, "absolute_q90_m": None}
    absolute = np.abs(residual)
    return {
        "count": int(len(residual)),
        "signed_median_m": float(np.median(residual)),
        "absolute_q50_q90_q95_max_m": [
            float(value) for value in np.percentile(absolute, [50, 90, 95, 100])
        ],
        "absolute_q90_m": float(np.percentile(absolute, 90)),
    }


def _ray_metrics(residual: np.ndarray) -> dict:
    if not len(residual):
        return {"count": 0, "signed_median_m": None, "absolute_q90_m": None}
    absolute = np.abs(residual)
    return {
        "count": int(len(residual)),
        "signed_median_m": float(np.median(residual)),
        "absolute_q50_q90_q95_q99_max_m": [
            float(value) for value in np.percentile(absolute, [50, 90, 95, 99, 100])
        ],
        "absolute_q90_m": float(np.percentile(absolute, 90)),
    }


def _predictions(
    samples: RaySamples,
    field: ScaleField,
    camera_center: np.ndarray,
    snap_labels: np.ndarray | None,
) -> dict:
    factors = field.predict(samples.elevation, samples.depth)
    corrected_depth = samples.depth * factors
    snapped = np.zeros(len(samples.point_ids), dtype=bool)
    if snap_labels is not None:
        labels = snap_labels[samples.row, samples.column]
        snapped = labels != 0
        plane_y = np.where(labels < 0, FLOOR_Y, CEILING_Y)
        snapped_depth = (plane_y - camera_center[1]) / samples.direction_world_y
        if np.any(snapped & (~np.isfinite(snapped_depth) | (snapped_depth <= 0))):
            raise ValueError("a snapped sample ray does not intersect its declared plane")
        corrected_depth[snapped] = snapped_depth[snapped]
    predicted_world_y = camera_center[1] + corrected_depth * samples.direction_world_y
    floor_residual = predicted_world_y[samples.plane_kind == -1] - FLOOR_Y
    ceiling_residual = predicted_world_y[samples.plane_kind == 1] - CEILING_Y
    ray_residual = corrected_depth - samples.target_depth
    return {
        "floor_residuals": floor_residual,
        "ceiling_residuals": ceiling_residual,
        "ray_residuals": ray_residual,
        "snapped": snapped,
        "plane_kind": samples.plane_kind,
    }


def _summarize_predictions(prediction: dict, anchor_residual: float) -> dict:
    kinds = prediction["plane_kind"]
    snapped = prediction["snapped"]
    return {
        "floor": _plane_metrics(prediction["floor_residuals"]),
        "ceiling": _plane_metrics(prediction["ceiling_residuals"]),
        "ray_depth_residual_m": _ray_metrics(prediction["ray_residuals"]),
        "camera_anchor_residual_m": anchor_residual,
        "plane_snapping_coverage": {
            "floor_samples_snapped": int(np.count_nonzero(snapped & (kinds == -1))),
            "floor_samples_total": int(np.count_nonzero(kinds == -1)),
            "ceiling_samples_snapped": int(np.count_nonzero(snapped & (kinds == 1))),
            "ceiling_samples_total": int(np.count_nonzero(kinds == 1)),
        },
    }


def _scale_targets(samples: RaySamples) -> np.ndarray:
    if np.any(samples.depth <= 0):
        raise ValueError("Hunyuan ray depths must be positive")
    return samples.target_depth / samples.depth


def _fit(samples: RaySamples) -> ScaleField:
    return fit_scale_field(samples.elevation, samples.depth, _scale_targets(samples))


def _fold_indices(samples: RaySamples) -> list[np.ndarray]:
    cells = np.unique(samples.spatial_cell)
    shuffled = np.random.default_rng(RANDOM_SEED).permutation(cells)
    return [np.isin(samples.spatial_cell, fold_cells) for fold_cells in np.array_split(shuffled, K_FOLDS)]


def _band_indices(samples: RaySamples) -> dict[str, np.ndarray]:
    return {
        name: (samples.row_fraction >= lower) & (samples.row_fraction < upper)
        for name, (lower, upper) in BANDS.items()
    }


def _combine_predictions(predictions: list[dict]) -> dict:
    keys = ("floor_residuals", "ceiling_residuals", "ray_residuals", "snapped", "plane_kind")
    return {key: np.concatenate([item[key] for item in predictions]) for key in keys}


def _gate(metrics: dict) -> dict:
    floor = metrics["floor"]["absolute_q90_m"]
    ceiling = metrics["ceiling"]["absolute_q90_m"]
    floor_pass = None if floor is None else floor <= MAX_PLANE_Q90_M
    ceiling_pass = None if ceiling is None else ceiling <= MAX_PLANE_Q90_M
    present_planes = [value for value in (floor_pass, ceiling_pass) if value is not None]
    return {
        "floor_q90_pass_5cm": floor_pass,
        "floor_goal_pass_3cm": floor is not None and floor <= FLOOR_GOAL_Q90_M,
        "ceiling_q90_pass_5cm": ceiling_pass,
        "pass": bool(present_planes) and all(present_planes),
    }


def _evaluate_method(
    name: str,
    training: RaySamples,
    extra_floor: RaySamples,
    mesh,
    positions: np.ndarray,
    context,
    acceptance: dict,
    mesh_output: Path,
) -> dict:
    full_field = _fit(training)
    anchor = float(
        np.linalg.norm(
            context.camera_center
            - np.asarray(acceptance["camera_anchor_world_declared"], dtype=np.float64)
        )
    )
    snap_labels = (
        classify_plane_regions(mesh, context.rotation, context.camera_center)
        if name == "plane_snap"
        else None
    )
    in_sample = _summarize_predictions(
        _predictions(training, full_field, context.camera_center, snap_labels), anchor
    )

    kfold_results = []
    kfold_predictions = []
    for fold_number, heldout_mask in enumerate(_fold_indices(training), start=1):
        fit_samples = training.subset(~heldout_mask)
        heldout = training.subset(heldout_mask)
        field = _fit(fit_samples)
        prediction = _predictions(heldout, field, context.camera_center, snap_labels)
        metrics = _summarize_predictions(prediction, anchor)
        kfold_results.append(
            {
                "fold": fold_number,
                "held_out_spatial_cells": sorted(map(int, np.unique(heldout.spatial_cell))),
                "training_count": len(fit_samples.point_ids),
                "held_out": metrics,
                "gate": _gate(metrics),
            }
        )
        kfold_predictions.append(prediction)
    pooled_kfold = _summarize_predictions(_combine_predictions(kfold_predictions), anchor)

    lobo_results = []
    lobo_predictions = []
    for band_name, heldout_mask in _band_indices(training).items():
        fit_samples = training.subset(~heldout_mask)
        heldout = training.subset(heldout_mask)
        if len(fit_samples.point_ids) < PARAMETER_COUNT or not len(heldout.point_ids):
            lobo_results.append(
                {"band": band_name, "training_count": len(fit_samples.point_ids),
                 "held_out_count": len(heldout.point_ids), "gate": {"pass": False},
                 "error": "insufficient fit or held-out samples"}
            )
            continue
        field = _fit(fit_samples)
        prediction = _predictions(heldout, field, context.camera_center, snap_labels)
        metrics = _summarize_predictions(prediction, anchor)
        lobo_results.append(
            {
                "band": band_name,
                "training_count": len(fit_samples.point_ids),
                "held_out_count": len(heldout.point_ids),
                "held_out": metrics,
                "gate": _gate(metrics),
            }
        )
        lobo_predictions.append(prediction)
    pooled_lobo = (
        _summarize_predictions(_combine_predictions(lobo_predictions), anchor)
        if lobo_predictions
        else None
    )

    external_prediction = _predictions(extra_floor, full_field, context.camera_center, snap_labels)
    external_metrics = _summarize_predictions(external_prediction, anchor)

    if name == "smooth_field":
        corrected, factors = radial_world_positions(
            positions, context.camera_center, context.rotation, full_field
        )
        median_scale = float(np.median(factors))
        baseline = context.camera_center + (positions * median_scale) @ context.rotation.T
        seam = seam_integrity(mesh, baseline, corrected, None, 1.0)
        correction_report = {"median_factor": median_scale}
        output_path = mesh_output / "frame_141_layer1_smooth_corrected.ply"
    else:
        corrected, correction_report = plane_snapped_world_positions(
            mesh,
            positions,
            context.camera_center,
            context.rotation,
            full_field,
            FLOOR_Y,
            CEILING_Y,
        )
        seam = seam_integrity(
            mesh, radial_world_positions(positions, context.camera_center, context.rotation, full_field)[0],
            corrected, snap_labels != 0, 1.0
        )
        output_path = mesh_output / "frame_141_layer1_plane_snapped_corrected.ply"
    write_corrected_ply(mesh, output_path, corrected)
    del corrected

    kfold_pass = bool(kfold_results) and all(result["gate"]["pass"] for result in kfold_results)
    lobo_pass = bool(lobo_results) and all(result["gate"]["pass"] for result in lobo_results)
    external_pass = (
        external_metrics["floor"]["absolute_q90_m"] is not None
        and external_metrics["floor"]["absolute_q90_m"] <= MAX_PLANE_Q90_M
    )
    return {
        "method": name,
        "parameter_count": PARAMETER_COUNT,
        "in_sample": in_sample,
        "k_fold": {
            "folds": kfold_results,
            "pooled_out_of_fold": pooled_kfold,
            "all_fold_gates_pass": kfold_pass,
        },
        "leave_one_panorama_band_out": {
            "folds": lobo_results,
            "pooled_out_of_band": pooled_lobo,
            "all_band_gates_pass": lobo_pass,
            "floor_band_left_out": next(
                (result for result in lobo_results if result["band"] == "bottom_floor_side"), None
            ),
        },
        "other_frame_floor_holdout": external_metrics,
        "other_frame_floor_gate_pass": external_pass,
        "held_out_acceptance_pass": kfold_pass and lobo_pass and external_pass,
        "seam_integrity": seam,
        "correction": correction_report,
        "experimental_mesh": str(output_path.relative_to(REPO_ROOT)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mesh-output", type=Path, default=DEFAULT_MESH_OUTPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--mask", type=Path, default=DEFAULT_MASK)
    parser.add_argument("--colmap", type=Path, default=DEFAULT_COLMAP)
    parser.add_argument("--dataparser", type=Path, default=DEFAULT_DATAPARSER)
    parser.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    return parser


def main() -> int:
    started = time.monotonic()
    args = _parser().parse_args()
    cv2.setNumThreads(1)
    manifest = verify_locked_acceptance(args.calibration)
    acceptance = manifest["visual_depth_correction_acceptance"]
    if args.mesh_output.exists():
        raise FileExistsError("refusing to reuse correction output directory: %s" % args.mesh_output)
    mesh = read_mesh_grid(args.mesh)
    positions = mesh.positions
    context = make_camera_context(
        args.source, args.colmap, args.dataparser, args.alignment, manifest
    )
    training, training_counts = collect_frame_samples(context, mesh, args.mask)
    extra_floor, visibility = collect_cross_frame_floor_samples(context, mesh, args.mask)
    if len(training.point_ids) <= PARAMETER_COUNT:
        raise ValueError("too few frame-141 training observations")
    output_dir = args.mesh_output
    output_dir.mkdir(parents=True, exist_ok=False)
    methods = [
        _evaluate_method(
            name, training, extra_floor, mesh, positions, context, acceptance, output_dir
        )
        for name in ("smooth_field", "plane_snap")
    ]
    result = {
        "schema_version": 1,
        "issue": 142,
        "status": "experimental_visual_correction_not_calibrated",
        "method_label": "corrected_not_calibrated",
        "registration_accepted": False,
        "scale_calibrated": False,
        "acceptance_block_sha256": EXPECTED_ACCEPTANCE_HASH,
        "inputs": {
            "source_frame": str(args.source.relative_to(REPO_ROOT)),
            "hunyuan_mesh": str(args.mesh.relative_to(REPO_ROOT)),
            "hunyuan_mesh_sha256": sha256(args.mesh),
            "foreground_mask": str(args.mask.relative_to(REPO_ROOT)),
            "colmap_model": str(args.colmap.relative_to(REPO_ROOT)),
            "dataparser": str(args.dataparser.relative_to(REPO_ROOT)),
            "alignment_manifest": str(args.alignment.relative_to(REPO_ROOT)),
            "camera_anchor_world_declared": context.camera_center.tolist(),
            "camera_anchor_residual_m": 0.0,
        },
        "model": {
            "target": "log(scale)",
            "scale_function": "exp(six-term quadratic in standardized elevation and log-depth)",
            "basis": ["1", "elevation", "log_depth", "elevation^2", "elevation*log_depth", "log_depth^2"],
            "parameter_count": PARAMETER_COUNT,
            "term_count_justification": acceptance["smooth_scale_field"]["term_count_justification"],
            "training_observations": training_counts,
        },
        "cross_frame_visibility": visibility,
        "methods": methods,
        "resource_use": {
            "runtime_seconds": round(time.monotonic() - started, 3),
            "peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "gpu_used": False,
        },
        "decision": {
            "route_a_held_out_acceptance_pass": all(
                method["held_out_acceptance_pass"] for method in methods
            ),
            "second_frame_mesh_check_complete": False,
            "second_frame_gpu_run_started": False,
            "may_be_used_by_issue_137": False,
            "reason": "The required second source-frame mesh check is pending explicit operator GPU approval.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["decision"], indent=2))
    print("report: %s" % args.output)
    print("experimental meshes: %s" % output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
