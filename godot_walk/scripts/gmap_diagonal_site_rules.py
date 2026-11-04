"""Static reservation checks for growth-created gmap-0.6.1 diagonal sites."""

from __future__ import annotations

from typing import Any

from gmap_diagonal import (
    CHAMFER_M,
    CLEAR_WIDTH_M,
    CLEARANCE_M,
    WALL_M,
    _passage_polygon,
    _rect_intersects_polygon,
)
from gmap_geometry import polygon_rect
from gmap_modules import OVERHANG_MARGIN_M
from gmap_rules import Errors, err

RULE = "diagonal_site_reservations"
EPS = 1e-6


def _same_point(left: list[float], right: list[float]) -> bool:
    return (
        len(left) == len(right) == 2
        and abs(left[0] - right[0]) <= EPS
        and abs(left[1] - right[1]) <= EPS
    )


def _cells(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {cell["cell_id"]: cell for cell in document["cells"]}


def _zone_matches_record(record: dict[str, Any]) -> bool:
    expected = _passage_polygon(
        record["start_xz"],
        record["finish_xz"],
        CLEAR_WIDTH_M / 2 + WALL_M + CLEARANCE_M,
    )
    return all(
        _same_point(actual, wanted)
        for actual, wanted in zip(record["clearance_polygon_xz"], expected)
    )


def _corners_match_sources(
    record: dict[str, Any], sources: list[dict[str, Any]]
) -> bool:
    if len(record["corner_indices"]) != 2 or len(record["corner_xz"]) != 2:
        return False
    for source, corner_index, recorded in zip(
        sources, record["corner_indices"], record["corner_xz"]
    ):
        if source is None or corner_index not in range(4):
            return False
        if not _same_point(source["envelope_xz"][corner_index], recorded):
            return False
    a, b = record["corner_xz"]
    sx, sz = (1 if b[0] > a[0] else -1), (1 if b[1] > a[1] else -1)
    expected_start = [a[0] - sx * CHAMFER_M / 2, a[1] - sz * CHAMFER_M / 2]
    expected_finish = [b[0] + sx * CHAMFER_M / 2, b[1] + sz * CHAMFER_M / 2]
    return _same_point(record["start_xz"], expected_start) and _same_point(
        record["finish_xz"], expected_finish
    )


def _linked_passage(document: dict[str, Any], record: dict[str, Any]) -> bool:
    return any(
        (passage := cell.get("diagonal_passage"))
        and passage["link_id"] == record.get("link_id")
        and [passage["from_cell_id"], passage["to_cell_id"]] == record["endpoint_ids"]
        for cell in document["cells"]
    )


def _occupancy_errors(
    document: dict[str, Any], record: dict[str, Any], cells: dict[str, dict[str, Any]]
) -> Errors:
    errors: Errors = []
    allowed = set(record["endpoint_ids"])
    if record["status"] == "realized":
        if not _linked_passage(document, record):
            errors.append(err(RULE, "reservation_link_missing", record["site_id"]))
        else:
            allowed.update(
                cell["cell_id"]
                for cell in document["cells"]
                if cell.get("diagonal_passage", {}).get("link_id")
                == record.get("link_id")
            )
    for cell in document["cells"]:
        if cell["cell_id"] in allowed:
            continue
        rect = polygon_rect(cell["envelope_xz"])
        if rect is None:
            continue
        pad = OVERHANG_MARGIN_M if cell.get("module") else 0.0
        expanded = (rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)
        if _rect_intersects_polygon(expanded, record["clearance_polygon_xz"]):
            errors.append(
                err(
                    RULE,
                    "reserved_zone_occupied",
                    f"{record['site_id']} intersects {cell['cell_id']}",
                )
            )
    return errors


def reservation_errors(document: dict[str, Any]) -> Errors:
    links = document.get("diagonal_links", {})
    records = links.get("reserved_diagonal_zones", [])
    errors: Errors = []
    if len(records) > links.get("budget", -1):
        errors.append(err(RULE, "reservation_count_exceeds_budget", str(len(records))))
    cells = _cells(document)
    seen_sites, seen_cells = set(), set()
    for record in records:
        site_id = record["site_id"]
        endpoints = record["endpoint_ids"]
        if site_id in seen_sites:
            errors.append(err(RULE, "reservation_id_duplicate", site_id))
        seen_sites.add(site_id)
        if (
            len(endpoints) != 2
            or len(set(endpoints)) != 2
            or not set(endpoints).isdisjoint(seen_cells)
        ):
            errors.append(err(RULE, "reservation_endpoints_reused", site_id))
        seen_cells.update(endpoints)
        sources = [cells.get(cell_id) for cell_id in endpoints]
        if any(
            source is None
            or source["role"] not in ("ground", "figure")
            or source.get("module")
            for source in sources
        ):
            errors.append(err(RULE, "reservation_endpoint_ineligible", site_id))
            continue
        corners = record["corner_xz"]
        if (
            len(corners) != 2
            or abs(abs(corners[1][0] - corners[0][0]) - 1.0) > EPS
            or abs(abs(corners[1][1] - corners[0][1]) - 1.0) > EPS
        ):
            errors.append(err(RULE, "reservation_corners_invalid", site_id))
        if not _corners_match_sources(record, sources):
            errors.append(err(RULE, "reservation_endpoint_geometry_mismatch", site_id))
        if not _zone_matches_record(record):
            errors.append(err(RULE, "reservation_clearance_shape_mismatch", site_id))
        if record["status"] == "released" and record.get("link_id"):
            errors.append(err(RULE, "released_reservation_has_link", site_id))
        if record["status"] == "realized" and not record.get("link_id"):
            errors.append(err(RULE, "realized_reservation_missing_link", site_id))
        errors.extend(_occupancy_errors(document, record, cells))
    return errors
