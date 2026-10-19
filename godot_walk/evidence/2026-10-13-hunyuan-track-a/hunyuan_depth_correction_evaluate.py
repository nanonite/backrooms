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
    mesh_quality,
    plane_snap_blend_weights,
    plane_snapped_world_positions,
    radial_world_positions,
    read_mesh_grid,
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
DEFAULT_MESH_OUTPUT = REPO_ROOT / "data/track-a/hunyuan/route-a-visual-correction-v2-frame-141"
EXPECTED_ACCEPTANCE_HASH = "ef8a166af45750f36cb73d44a2c5f8b653b0128f34a686210ad979610fd58b69"
PARAMETER_COUNT = 6
K_FOLDS = 5
RANDOM_SEED = 142
MAX_PRIMARY_Q90_M = 0.05
FLOOR_GOAL_Q90_M = 0.03
MAX_DEGENERATE_TRIANGLES = 44829
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
    if acceptance["primary_held_out_gate"]["floor_member_q90_max_m"] != MAX_PRIMARY_Q90_M:
        raise ValueError("locked primary floor gate differs from this evaluator")
    if acceptance["mesh_quality_gate"]["degenerate_triangle_max_count"] != MAX_DEGENERATE_TRIANGLES:
        raise ValueError("locked mesh-quality gate differs from this evaluator")
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
    snap_weights: dict[str, np.ndarray] | None,
) -> dict:
    factors = field.predict(samples.elevation, samples.depth)
    corrected_depth = samples.depth * factors
    floor_weights, ceiling_weights = _sample_snap_weights(samples, snap_weights)
    snapped_weight = np.maximum(floor_weights, ceiling_weights)
    snap_plane_y = np.where(floor_weights >= ceiling_weights, FLOOR_Y, CEILING_Y)
    snapped = snapped_weight > 0
    snapped_depth = corrected_depth.copy()
    snapped_depth[snapped] = (
        snap_plane_y[snapped] - camera_center[1]
    ) / samples.direction_world_y[snapped]
    if np.any(snapped & (~np.isfinite(snapped_depth) | (snapped_depth <= 0))):
        raise ValueError("a blended sample ray does not intersect its declared plane")
    corrected_depth += snapped_weight * (snapped_depth - corrected_depth)
    predicted_world_y = camera_center[1] + corrected_depth * samples.direction_world_y
    target_world_y = camera_center[1] + samples.target_depth * samples.direction_world_y
    floor_residual = predicted_world_y[samples.plane_kind == -1] - FLOOR_Y
    ceiling_residual = predicted_world_y[samples.plane_kind == 1] - CEILING_Y
    floor_oracle_residual = target_world_y[samples.plane_kind == -1] - FLOOR_Y
    ceiling_oracle_residual = target_world_y[samples.plane_kind == 1] - CEILING_Y
    ray_residual = corrected_depth - samples.target_depth
    vertical_residual = (corrected_depth - samples.target_depth) * samples.direction_world_y
    return {
        "primary_vertical_residuals": vertical_residual,
        "floor_plane_residuals": floor_residual,
        "ceiling_plane_residuals": ceiling_residual,
        "floor_oracle_plane_residuals": floor_oracle_residual,
        "ceiling_oracle_plane_residuals": ceiling_oracle_residual,
        "ray_residuals": ray_residual,
        "floor_snap_weights": floor_weights,
        "ceiling_snap_weights": ceiling_weights,
        "plane_kind": samples.plane_kind,
    }


def _sample_snap_weights(
    samples: RaySamples, snap_weights: dict[str, np.ndarray] | None
) -> tuple[np.ndarray, np.ndarray]:
    if snap_weights is None:
        zeros = np.zeros(len(samples.point_ids), dtype=np.float64)
        return zeros, zeros
    return (
        snap_weights["floor"][samples.row, samples.column],
        snap_weights["ceiling"][samples.row, samples.column],
    )


def _summarize_predictions(prediction: dict, anchor_residual: float) -> dict:
    kinds = prediction["plane_kind"]
    vertical = prediction["primary_vertical_residuals"]
    floor_samples = kinds == -1
    ceiling_samples = kinds == 1
    floor_weight = prediction["floor_snap_weights"]
    ceiling_weight = prediction["ceiling_snap_weights"]
    return {
        "primary_point_vertical_error_m": {
            "floor": _ray_metrics(vertical[floor_samples]),
            "ceiling": _ray_metrics(vertical[ceiling_samples]),
        },
        "legacy_plane_metric_context_only": {
            "floor": _plane_metrics(prediction["floor_plane_residuals"]),
            "ceiling": _plane_metrics(prediction["ceiling_plane_residuals"]),
        },
        "oracle_legacy_plane_metric_context_only": {
            "floor": _plane_metrics(prediction["floor_oracle_plane_residuals"]),
            "ceiling": _plane_metrics(prediction["ceiling_oracle_plane_residuals"]),
        },
        "ray_depth_residual_m": _ray_metrics(prediction["ray_residuals"]),
        "camera_anchor_residual_m": anchor_residual,
        "plane_snapping_blend_coverage": {
            "floor_samples_blended": int(np.count_nonzero(floor_weight > 0)),
            "floor_samples_fully_snapped": int(np.count_nonzero(floor_weight >= 1.0)),
            "floor_samples_total": int(np.count_nonzero(floor_samples)),
            "ceiling_samples_blended": int(np.count_nonzero(ceiling_weight > 0)),
            "ceiling_samples_fully_snapped": int(np.count_nonzero(ceiling_weight >= 1.0)),
            "ceiling_samples_total": int(np.count_nonzero(ceiling_samples)),
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
    keys = (
        "primary_vertical_residuals",
        "floor_plane_residuals",
        "ceiling_plane_residuals",
        "floor_oracle_plane_residuals",
        "ceiling_oracle_plane_residuals",
        "ray_residuals",
        "floor_snap_weights",
        "ceiling_snap_weights",
        "plane_kind",
    )
    return {key: np.concatenate([item[key] for item in predictions]) for key in keys}


def _gate(metrics: dict, require_ceiling: bool = True) -> dict:
    primary = metrics["primary_point_vertical_error_m"]
    floor = primary["floor"]["absolute_q90_m"]
    ceiling = primary["ceiling"]["absolute_q90_m"]
    floor_pass = None if floor is None else floor <= MAX_PRIMARY_Q90_M
    ceiling_pass = None if ceiling is None else ceiling <= MAX_PRIMARY_Q90_M
    floor_pass = bool(floor_pass)
    ceiling_pass = bool(ceiling_pass) if require_ceiling else True
    anchor_pass = metrics["camera_anchor_residual_m"] <= 1e-12
    return {
        "floor_point_vertical_q90_pass_5cm": floor_pass,
        "floor_goal_pass_3cm": floor is not None and floor <= FLOOR_GOAL_Q90_M,
        "ceiling_point_vertical_q90_pass_5cm": ceiling_pass,
        "camera_anchor_pass": anchor_pass,
        "pass": floor_pass and ceiling_pass and anchor_pass,
    }


def _field_record(field: ScaleField) -> dict:
    return {
        "coefficients": field.coefficients.tolist(),
        "elevation_mean": field.elevation_mean,
        "elevation_scale": field.elevation_scale,
        "log_depth_mean": field.log_depth_mean,
        "log_depth_scale": field.log_depth_scale,
        "elevation_z_bounds": list(field.elevation_bounds),
        "log_depth_z_bounds": list(field.log_depth_bounds),
    }


def _field_from_record(record: dict) -> ScaleField:
    field = ScaleField(
        coefficients=np.asarray(record["coefficients"], dtype=np.float64),
        elevation_mean=float(record["elevation_mean"]),
        elevation_scale=float(record["elevation_scale"]),
        log_depth_mean=float(record["log_depth_mean"]),
        log_depth_scale=float(record["log_depth_scale"]),
        elevation_bounds=tuple(map(float, record["elevation_z_bounds"])),
        log_depth_bounds=tuple(map(float, record["log_depth_z_bounds"])),
    )
    if len(field.coefficients) != PARAMETER_COUNT:
        raise ValueError("transferred field must use exactly six coefficients")
    return field


def _transferred_field(path: Path) -> ScaleField:
    report = json.loads(path.read_text())
    candidate = next(
        method for method in report["methods"]
        if method["method"] == "smooth_field"
    )
    return _field_from_record(candidate["fitted_field"])


def _oracle_report(samples: RaySamples, camera_center: np.ndarray) -> dict:
    zero_field = np.zeros(len(samples.point_ids), dtype=np.float64)
    floor = samples.plane_kind == -1
    ceiling = samples.plane_kind == 1
    world_y = camera_center[1] + samples.target_depth * samples.direction_world_y
    return {
        "sample_count": len(samples.point_ids),
        "primary_point_vertical_error_m": {
            "all": _ray_metrics(zero_field),
            "floor_members": _ray_metrics(zero_field[floor]),
            "ceiling_members": _ray_metrics(zero_field[ceiling]),
        },
        "legacy_plane_metric_context_only": {
            "floor": _plane_metrics(world_y[floor] - FLOOR_Y),
            "ceiling": _plane_metrics(world_y[ceiling] - CEILING_Y),
        },
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
    field_override: ScaleField | None = None,
    transfer_source: str | None = None,
) -> dict:
    full_field = field_override or _fit(training)
    anchor = 0.0
    snap_weights = plane_snap_blend_weights(mesh, context.rotation) if "plane_snap" in name else None
    in_sample = _summarize_predictions(
        _predictions(training, full_field, context.camera_center, snap_weights), anchor
    )

    kfold_results = []
    kfold_predictions = []
    for fold_number, heldout_mask in enumerate(_fold_indices(training), start=1):
        fit_samples = training.subset(~heldout_mask)
        heldout = training.subset(heldout_mask)
        field = full_field if field_override is not None else _fit(fit_samples)
        prediction = _predictions(heldout, field, context.camera_center, snap_weights)
        metrics = _summarize_predictions(prediction, anchor)
        kfold_results.append(
            {
                "fold": fold_number,
                "held_out_spatial_cells": sorted(map(int, np.unique(heldout.spatial_cell))),
                "training_count": 0 if field_override is not None else len(fit_samples.point_ids),
                "coefficient_transfer_used": field_override is not None,
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
        if not len(heldout.point_ids) or (
            field_override is None and len(fit_samples.point_ids) < PARAMETER_COUNT
        ):
            lobo_results.append(
                {"band": band_name, "training_count": len(fit_samples.point_ids),
                 "held_out_count": len(heldout.point_ids), "gate": {"pass": False},
                 "error": "insufficient fit or held-out samples"}
            )
            continue
        field = full_field if field_override is not None else _fit(fit_samples)
        prediction = _predictions(heldout, field, context.camera_center, snap_weights)
        metrics = _summarize_predictions(prediction, anchor)
        lobo_results.append(
            {
                "band": band_name,
                "training_count": 0 if field_override is not None else len(fit_samples.point_ids),
                "held_out_count": len(heldout.point_ids),
                "coefficient_transfer_used": field_override is not None,
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

    external_prediction = _predictions(extra_floor, full_field, context.camera_center, snap_weights)
    external_metrics = _summarize_predictions(external_prediction, anchor)
    external_gate = _gate(external_metrics, require_ceiling=False)

    smooth_world, factors = radial_world_positions(
        positions, context.camera_center, context.rotation, full_field
    )
    median_scale = float(np.median(factors))
    source_baseline = context.camera_center + (positions * median_scale) @ context.rotation.T
    if snap_weights is None:
        corrected = smooth_world
        quality_weights = None
    else:
        corrected, correction_report, quality_weights = plane_snapped_world_positions(
            mesh,
            positions,
            context.camera_center,
            context.rotation,
            full_field,
            FLOOR_Y,
            CEILING_Y,
        )
    if snap_weights is None:
        correction_report = {"median_factor": median_scale}
    else:
        correction_report["median_factor"] = median_scale
    quality = mesh_quality(
        mesh, source_baseline, corrected, quality_weights,
        int(acceptance["mesh_quality_gate"]["degenerate_triangle_max_count"]),
    )
    output_path = _corrected_mesh_path(mesh_output, Path(context.image.name).stem, name)
    write_corrected_ply(mesh, output_path, corrected)
    del corrected, smooth_world, source_baseline

    kfold_pass = bool(kfold_results) and all(result["gate"]["pass"] for result in kfold_results)
    lobo_pass = bool(lobo_results) and all(result["gate"]["pass"] for result in lobo_results)
    external_pass = external_gate["pass"]
    primary_pass = kfold_pass and lobo_pass and external_pass
    return {
        "method": name,
        "parameter_count": PARAMETER_COUNT,
        "fit_policy": "coefficient_transfer" if field_override is not None else "frame_specific_refit",
        "transfer_source": transfer_source,
        "fitted_field": _field_record(full_field),
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
        "other_frame_floor_gate": external_gate,
        "primary_held_out_acceptance_pass": primary_pass,
        "mesh_quality": quality,
        "candidate_for_route_a_decision": field_override is None,
        "route_a_method_pass": primary_pass and quality["mesh_quality_pass"],
        "correction": correction_report,
        "experimental_mesh": str(output_path.relative_to(REPO_ROOT)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mesh-output", type=Path, default=DEFAULT_MESH_OUTPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--mesh", type=Path, default=DEFAULT_MESH)
    parser.add_argument("--mask", "--fg-mask", dest="mask", type=Path, default=DEFAULT_MASK)
    parser.add_argument("--colmap", type=Path, default=DEFAULT_COLMAP)
    parser.add_argument("--dataparser", type=Path, default=DEFAULT_DATAPARSER)
    parser.add_argument("--alignment", type=Path, default=DEFAULT_ALIGNMENT)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--frame-camera", type=Path)
    parser.add_argument("--coefficients-from", type=Path)
    return parser


def _resolve_repo_path(path: Path | None) -> Path | None:
    if path is None or path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def _corrected_mesh_path(mesh_output: Path, frame_id: str, method: str) -> Path:
    return mesh_output / ("%s_%s_corrected.ply" % (frame_id, method))


def main() -> int:
    started = time.monotonic()
    args = _parser().parse_args()
    for name in (
        "output", "mesh_output", "source", "mesh", "mask", "colmap", "dataparser",
        "alignment", "calibration", "frame_camera", "coefficients_from",
    ):
        setattr(args, name, _resolve_repo_path(getattr(args, name)))
    cv2.setNumThreads(1)
    manifest = verify_locked_acceptance(args.calibration)
    acceptance = manifest["visual_depth_correction_acceptance"]
    if args.source.name != "frame_0141.jpg" and args.frame_camera is None:
        raise ValueError("non-frame-141 evaluations require per-frame camera metadata")
    if args.mesh_output.exists():
        raise FileExistsError("refusing to reuse correction output directory: %s" % args.mesh_output)
    mesh = read_mesh_grid(args.mesh)
    positions = mesh.positions
    context = make_camera_context(
        args.source, args.colmap, args.dataparser, args.alignment, manifest,
        args.frame_camera,
    )
    training, training_counts = collect_frame_samples(context, mesh, args.mask)
    extra_floor, visibility = collect_cross_frame_floor_samples(context, mesh, args.mask)
    if len(training.point_ids) <= PARAMETER_COUNT:
        raise ValueError("too few registered source-frame observations")
    output_dir = args.mesh_output
    output_dir.mkdir(parents=True, exist_ok=False)
    frame_id = Path(context.image.name).stem
    refit_names = (
        ("smooth_field", "plane_snap")
        if frame_id == "frame_0141"
        else ("smooth_field_refit", "plane_snap_refit")
    )
    methods = [
        _evaluate_method(
            name, training, extra_floor, mesh, positions, context, acceptance, output_dir
        )
        for name in refit_names
    ]
    if args.coefficients_from is not None:
        transferred = _transferred_field(args.coefficients_from)
        for name in ("smooth_field_coefficient_transfer", "plane_snap_coefficient_transfer"):
            methods.append(
                _evaluate_method(
                    name, training, extra_floor, mesh, positions, context, acceptance,
                    output_dir, field_override=transferred,
                    transfer_source=str(args.coefficients_from),
                )
            )
    oracle = {
        "registered_source_frame_samples": _oracle_report(training, context.camera_center),
        "other_frame_floor_holdout": _oracle_report(extra_floor, context.camera_center),
        "legacy_plane_gate_status": acceptance["legacy_plane_gate"]["status"],
    }
    result = {
        "schema_version": 2,
        "issue": 142,
        "source_frame": frame_id,
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
            "frame_camera_metadata": (
                str(args.frame_camera.relative_to(REPO_ROOT))
                if args.frame_camera is not None else None
            ),
            "frame_camera_source": context.camera_frame_source,
            "frame_camera_metadata_sha256": (
                sha256(args.frame_camera) if args.frame_camera is not None else None
            ),
            "coefficient_transfer_source": (
                str(args.coefficients_from.relative_to(REPO_ROOT))
                if args.coefficients_from is not None else None
            ),
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
        "oracle_noise_floor": oracle,
        "methods": methods,
        "resource_use": {
            "runtime_seconds": round(time.monotonic() - started, 3),
            "peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "gpu_used": False,
        },
        "decision": {
            "route_a_candidate_methods_pass": {
                method["method"]: method["route_a_method_pass"]
                for method in methods if method["candidate_for_route_a_decision"]
            },
            "second_frame_mesh_check_complete": frame_id == "frame_0152",
            "gpu_used": False,
            "may_be_used_by_issue_137": False,
            "reason": "This report is experimental. Final Route A decision requires qualifying primary held-out and mesh-quality results on both frames 141 and 152.",
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
