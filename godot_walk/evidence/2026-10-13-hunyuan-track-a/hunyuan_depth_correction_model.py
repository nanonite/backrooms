"""Low-order smooth radial scale field for visual-only Hunyuan correction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PARAMETER_COUNT = 6


@dataclass(frozen=True)
class ScaleField:
    coefficients: np.ndarray
    elevation_mean: float
    elevation_scale: float
    log_depth_mean: float
    log_depth_scale: float
    elevation_bounds: tuple[float, float]
    log_depth_bounds: tuple[float, float]

    def predict(self, elevation: np.ndarray, depth: np.ndarray) -> np.ndarray:
        elevation = np.asarray(elevation, dtype=np.float64)
        depth = np.asarray(depth, dtype=np.float64)
        if not np.isfinite(elevation).all():
            raise ValueError("elevation values must be finite")
        if np.any(depth <= 0) or not np.isfinite(depth).all():
            raise ValueError("depth values must be finite and positive")
        elevation_z = (elevation - self.elevation_mean) / self.elevation_scale
        log_depth_z = (np.log(depth) - self.log_depth_mean) / self.log_depth_scale
        elevation_z = np.clip(elevation_z, *self.elevation_bounds)
        log_depth_z = np.clip(log_depth_z, *self.log_depth_bounds)
        log_scale = scale_design(elevation_z, log_depth_z) @ self.coefficients
        with np.errstate(over="ignore", invalid="ignore"):
            return np.exp(log_scale)


def scale_design(elevation_z: np.ndarray, log_depth_z: np.ndarray) -> np.ndarray:
    elevation_z, log_depth_z = np.broadcast_arrays(elevation_z, log_depth_z)
    return np.column_stack(
        (
            np.ones(elevation_z.size),
            elevation_z.ravel(),
            log_depth_z.ravel(),
            elevation_z.ravel() ** 2,
            elevation_z.ravel() * log_depth_z.ravel(),
            log_depth_z.ravel() ** 2,
        )
    )


def fit_scale_field(
    elevation: np.ndarray,
    depth: np.ndarray,
    target_scale: np.ndarray,
) -> ScaleField:
    elevation, depth, target_scale = _validated_samples(elevation, depth, target_scale)
    log_depth = np.log(depth)
    elevation_mean = float(np.mean(elevation))
    log_depth_mean = float(np.mean(log_depth))
    elevation_scale = _nonzero_scale(elevation)
    log_depth_scale = _nonzero_scale(log_depth)
    elevation_z = (elevation - elevation_mean) / elevation_scale
    log_depth_z = (log_depth - log_depth_mean) / log_depth_scale
    design = scale_design(elevation_z, log_depth_z)
    coefficients = _huber_least_squares(design, np.log(target_scale))
    return ScaleField(
        coefficients=coefficients,
        elevation_mean=elevation_mean,
        elevation_scale=elevation_scale,
        log_depth_mean=log_depth_mean,
        log_depth_scale=log_depth_scale,
        elevation_bounds=(float(elevation_z.min()), float(elevation_z.max())),
        log_depth_bounds=(float(log_depth_z.min()), float(log_depth_z.max())),
    )


def _validated_samples(
    elevation: np.ndarray, depth: np.ndarray, target_scale: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    elevation = np.asarray(elevation, dtype=np.float64).reshape(-1)
    depth = np.asarray(depth, dtype=np.float64).reshape(-1)
    target_scale = np.asarray(target_scale, dtype=np.float64).reshape(-1)
    if not (len(elevation) == len(depth) == len(target_scale)):
        raise ValueError("elevation, depth and target scale lengths must match")
    if len(elevation) < PARAMETER_COUNT:
        raise ValueError("at least six samples are required for the quadratic field")
    if not all(np.isfinite(values).all() for values in (elevation, depth, target_scale)):
        raise ValueError("scale-field samples must be finite")
    if np.any(depth <= 0) or np.any(target_scale <= 0):
        raise ValueError("depth and target scale values must be positive")
    return elevation, depth, target_scale


def _nonzero_scale(values: np.ndarray) -> float:
    scale = float(np.std(values))
    if scale <= np.finfo(np.float64).eps:
        raise ValueError("scale-field input has no variation")
    return scale


def _huber_least_squares(design: np.ndarray, targets: np.ndarray) -> np.ndarray:
    coefficients = np.linalg.lstsq(design, targets, rcond=None)[0]
    for _ in range(25):
        residuals = targets - design @ coefficients
        center = float(np.median(residuals))
        robust_sigma = 1.4826 * float(np.median(np.abs(residuals - center)))
        if robust_sigma <= 1e-10:
            break
        cutoff = 1.345 * robust_sigma
        weights = np.minimum(1.0, cutoff / np.maximum(np.abs(residuals), 1e-12))
        root_weights = np.sqrt(weights)
        updated = np.linalg.lstsq(
            design * root_weights[:, None], targets * root_weights, rcond=None
        )[0]
        if np.linalg.norm(updated - coefficients) <= 1e-10:
            coefficients = updated
            break
        coefficients = updated
    return coefficients
