"""Reserved-site realization for gmap-0.6.1; gmap-0.6.0 remains frozen."""

from __future__ import annotations

from typing import Any

from gmap_diagonal import _add_one, rng_for, sampled_budget
from gmap_diagonal_candidates import candidate_pairs, select_pairs
from gmap_diagonal_nudge import nudge_to_budget

SELECTION_RULE = (
    "seeded weighted draw 0:3, 1:5, 2:2; growth reservations first; "
    "remaining eligible pairs sorted then seeded shuffle"
)


def _matches(pair: dict[str, Any], reservation: dict[str, Any]) -> bool:
    return (
        pair["a"]["cell_id"] == reservation["endpoint_ids"][0]
        and pair["b"]["cell_id"] == reservation["endpoint_ids"][1]
        and pair["corner_a_xz"] == reservation["corner_xz"][0]
        and pair["corner_b_xz"] == reservation["corner_xz"][1]
    )


def _reserved_pairs(
    candidates: list[dict[str, Any]], reservations: list[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chosen, records, used_cells = [], [], set()
    for source in reservations:
        record = {key: value for key, value in source.items()}
        match = next((pair for pair in candidates if _matches(pair, source)), None)
        if (
            len(chosen) < budget
            and match is not None
            and not used_cells.intersection(source["endpoint_ids"])
        ):
            chosen.append(match)
            used_cells.update(source["endpoint_ids"])
            record["status"] = "realized"
            record["link_id"] = f"dl{len(chosen) - 1:02d}"
        else:
            record["status"] = "released"
            record["release_reason"] = "not_eligible_after_final_stages"
        records.append(record)
    return chosen, records


def _remaining_pairs(
    candidates: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    reservations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    used = {
        cell
        for pair in selected
        for cell in (pair["a"]["cell_id"], pair["b"]["cell_id"])
    }
    reserved = {cell for record in reservations for cell in record["endpoint_ids"]}
    blocked = used | reserved
    return [
        pair
        for pair in candidates
        if pair["a"]["cell_id"] not in blocked and pair["b"]["cell_id"] not in blocked
    ]


def apply_links_v61(
    document: dict[str, Any], reservations: list[dict[str, Any]], budget: int
) -> None:
    """Nudge only unreserved leaves, realize sites first, then incidental eligible pairs."""
    rng = rng_for(document["seed"], document["attempt"])
    expected_budget = sampled_budget(rng)
    if budget != expected_budget:
        raise ValueError(
            f"growth budget {budget} differs from seeded budget {expected_budget}"
        )
    endpoints = {cell for zone in reservations for cell in zone["endpoint_ids"]}
    polygons = [zone["clearance_polygon_xz"] for zone in reservations]
    nudged = nudge_to_budget(document, budget, endpoints, polygons)
    candidates = candidate_pairs(document)
    reserved, records = _reserved_pairs(candidates, reservations, budget)
    incidental = select_pairs(
        _remaining_pairs(candidates, reserved, records), budget - len(reserved), rng
    )
    chosen = reserved + incidental
    for index, pair in enumerate(chosen):
        _add_one(document, pair, index)
    document["edges"].sort(key=lambda edge: (edge["from"], edge["to"]))
    document["diagonal_links"] = {
        "budget": budget,
        "used": len(chosen),
        "selection_rule": SELECTION_RULE,
        "nudged_cells": nudged,
        "reserved_diagonal_zones": records,
    }
