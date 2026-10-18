"""Planar loop, obstacle, and evidence-footprint calculations."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree


def make_route_geometry(source: dict, spec: dict, grid: dict) -> dict:
    """Build the loop and reject geometry that cannot fit the capsule."""
    geometry = _route_geometry(source, spec, grid)
    if not geometry["capsule_check"]["pass"]:
        raise ValueError("authored loop does not contain the obstacle and capsule")
    return geometry


def _route_geometry(source: dict, spec: dict, grid: dict) -> dict:
    """Measure a chosen route and its candidate-footprint proximity."""
    dimensions = _route_dimensions(spec["route"])
    center = _route_center(source, spec)
    points = loop_points(center, dimensions["radius"], dimensions["samples"])
    metrics = _route_metrics(source, spec, grid, dimensions, points, center)
    return {**dimensions, **metrics, "center": center, "centerline": points}


def _route_dimensions(route: dict) -> dict:
    """Return fixed radial band dimensions and sampling density."""
    radius, width = float(route["radius_m"]), float(route["width_m"])
    return {
        "radius": radius,
        "width": width,
        "inner": radius - width / 2.0,
        "outer": radius + width / 2.0,
        "samples": int(route["segments"]) * 6,
    }


def _route_center(source: dict, spec: dict) -> np.ndarray:
    """Shift the fitted camera orbit center toward the candidate footprint."""
    offset = np.asarray(spec["route"]["center_offset_from_camera_orbit_xz_m"])
    return source["center"] + offset


def _route_metrics(
    source: dict,
    spec: dict,
    grid: dict,
    dimensions: dict,
    points: np.ndarray,
    center: np.ndarray,
) -> dict:
    """Measure evidence proximity and capsule clearance for the route."""
    capsule_radius = float(spec["capsule"]["radius_m"])
    support = support_coverage(points, grid, capsule_radius)
    clearances = distance_to_bounds(points, source["lower"], source["upper"])
    route_source = {**source, "center": center}
    capsule = capsule_route_check(
        route_source,
        dimensions["radius"],
        dimensions["width"],
        dimensions["inner"],
        dimensions["outer"],
        clearances,
        capsule_radius,
    )
    return {
        "support": support,
        "clearances": clearances,
        "capsule_check": capsule,
    }


def loop_points(
    center_xz: np.ndarray, radius_m: float, sample_count: int
) -> np.ndarray:
    """Return a closed-route sampling without duplicating its endpoint."""
    angles = np.linspace(0.0, 2.0 * np.pi, sample_count, endpoint=False)
    return center_xz + radius_m * np.column_stack((np.cos(angles), np.sin(angles)))


def distance_to_bounds(
    points_xz: np.ndarray, lower: np.ndarray, upper: np.ndarray
) -> np.ndarray:
    """Return horizontal Euclidean distance to an axis-aligned rectangle."""
    delta = np.maximum(np.maximum(lower - points_xz, 0.0), points_xz - upper)
    return np.linalg.norm(delta, axis=1)


def capsule_route_check(
    source: dict,
    radius: float,
    width: float,
    inner: float,
    outer: float,
    clearances: np.ndarray,
    capsule_radius: float,
) -> dict:
    """Check capsule corridor width and obstacle enclosure in plan view."""
    obstacle_radius = _max_corner_radius(
        source["center"], source["lower"], source["upper"]
    )
    margins = _capsule_margins(
        width, inner, obstacle_radius, clearances, capsule_radius
    )
    return _capsule_report(
        radius,
        inner,
        outer,
        width,
        capsule_radius,
        obstacle_radius,
        margins,
    )


def _capsule_margins(
    width: float,
    inner: float,
    obstacle_radius: float,
    clearances: np.ndarray,
    capsule_radius: float,
) -> dict:
    """Calculate floor, obstacle, and capsule margins for one route."""
    result = {
        "walls": width / 2.0 - capsule_radius,
        "obstacle": inner - obstacle_radius,
        "capsule": float(clearances.min() - capsule_radius),
    }
    result["pass"] = all(value >= 0.0 for value in result.values())
    return result


def _max_corner_radius(
    center: np.ndarray, lower: np.ndarray, upper: np.ndarray
) -> float:
    """Return the farthest axis-aligned box corner from the loop center."""
    corners = np.array(
        [(x, z) for x in (lower[0], upper[0]) for z in (lower[1], upper[1])]
    )
    return float(np.linalg.norm(corners - center, axis=1).max())


def _capsule_report(
    radius: float,
    inner: float,
    outer: float,
    width: float,
    capsule_radius: float,
    obstacle_radius: float,
    margins: dict,
) -> dict:
    """Name static capsule-clearance quantities and their limits."""
    return {
        "pass": bool(margins["pass"]),
        "capsule_diameter_m": capsule_radius * 2.0,
        "floor_corridor_width_m": width,
        "lateral_margin_each_side_m": margins["walls"],
        "obstacle_max_radius_from_loop_center_m": obstacle_radius,
        "obstacle_clearance_to_floor_inner_edge_m": margins["obstacle"],
        "centerline_obstacle_clearance_after_capsule_m": margins["capsule"],
        "loop_radius_m": radius,
        "loop_band_center_m": (inner + outer) / 2.0,
        "check_kind": "static horizontal geometry only; not a runtime physics traversal",
    }


def support_coverage(points_xz: np.ndarray, grid: dict, radius_m: float) -> dict:
    """Measure candidate-cell proximity without converting it into collider data."""
    rows, columns = np.nonzero(grid["observed"].astype(bool))
    centers = np.column_stack(
        (
            float(grid["origin_x_m"]) + (columns + 0.5) * float(grid["spacing_m"]),
            float(grid["origin_z_m"]) + (rows + 0.5) * float(grid["spacing_m"]),
        )
    )
    distances = cKDTree(centers).query(points_xz)[0]
    return {
        "candidate_cells_within_radius_m": float(radius_m),
        "route_samples": len(points_xz),
        "candidate_supported_samples": int(np.count_nonzero(distances <= radius_m)),
        "candidate_support_fraction": float(np.mean(distances <= radius_m)),
        "nearest_distance_q50_q90_max_m": np.quantile(
            distances, [0.5, 0.9, 1.0]
        ).tolist(),
    }


def corridor_coverage(
    grid: dict, center_xz: np.ndarray, inner_m: float, outer_m: float
) -> dict:
    """Compare the authored loop band with unfilled candidate occupancy."""
    rows, columns = np.indices(grid["observed"].shape)
    x = float(grid["origin_x_m"]) + (columns + 0.5) * float(grid["spacing_m"])
    z = float(grid["origin_z_m"]) + (rows + 0.5) * float(grid["spacing_m"])
    radial = np.hypot(x - center_xz[0], z - center_xz[1])
    corridor = (radial >= inner_m) & (radial <= outer_m)
    occupied = grid["observed"].astype(bool) & corridor
    cell_area = float(grid["spacing_m"]) ** 2
    corridor_cells = int(corridor.sum())
    occupied_cells = int(occupied.sum())
    return {
        "corridor_cells": corridor_cells,
        "candidate_cells_in_corridor": occupied_cells,
        "candidate_area_m2": occupied_cells * cell_area,
        "explicit_authored_fill_area_m2": (corridor_cells - occupied_cells) * cell_area,
        "candidate_occupancy_fraction": occupied_cells / corridor_cells
        if corridor_cells
        else 0.0,
    }
