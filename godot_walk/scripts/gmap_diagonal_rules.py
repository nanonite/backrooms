"""Static metadata checks for gmap-0.6.0 diagonal chamfer passages."""

from __future__ import annotations

import math
from typing import Any

from gmap_diagonal import (
    CHAMFER_M,
    CLEAR_WIDTH_M,
    DIAG,
    RULE,
    WALL_M,
    _passage_polygon,
    rng_for,
    sampled_budget,
)
from gmap_diagonal_rule_geometry import (
    edge_groups,
    point_matches,
    polygon_errors,
    ports_by_id,
)
from gmap_diagonal_v61 import SELECTION_RULE as SELECTION_RULE_V61
from gmap_rules import Errors, err

EPS = 1e-6


def diagonal_errors(document: dict[str, Any]) -> Errors:
    budget = document.get("diagonal_links", {})
    rng = rng_for(document["seed"], document.get("attempt", 0))
    expected_budget = sampled_budget(rng)
    passages = [c for c in document["cells"] if c.get("diagonal_passage")]
    groups = edge_groups(document)
    errors: Errors = []
    if budget.get("budget") != expected_budget:
        errors.append(
            err(
                RULE,
                "link_budget_draw_mismatch",
                f"expected {expected_budget}, got {budget.get('budget')}",
            )
        )
    if budget.get("used") != len(passages) or len(passages) > budget.get("budget", -1):
        errors.append(
            err(
                RULE,
                "link_budget_used_mismatch",
                f"passages={len(passages)}, record={budget}",
            )
        )
    expected_selection = (
        SELECTION_RULE_V61
        if document["generator_version"]
        in ("gmap-0.6.1", "gmap-0.7.0", "gmap-0.8.0", "gmap-0.9.0", "gmap-0.10.0", "gmap-0.11.0", "gmap-0.12.0")
        else "seeded weighted draw 0:3, 1:5, 2:2; eligible pairs sorted then seeded shuffle"
    )
    if budget.get("selection_rule") != expected_selection:
        errors.append(
            err(RULE, "link_selection_rule", "selection rule declaration changed")
        )
    cells = {c["cell_id"]: c for c in document["cells"]}
    ports = ports_by_id(document["cells"])
    for passage in passages:
        meta = passage["diagonal_passage"]
        link = meta["link_id"]
        a_id, b_id = meta["from_cell_id"], meta["to_cell_id"]
        a, b = cells.get(a_id), cells.get(b_id)
        if (
            not a
            or not b
            or a["role"] not in ("ground", "figure")
            or b["role"] not in ("ground", "figure")
            or a.get("module")
            or b.get("module")
            or a.get("landmark")
            or b.get("landmark")
        ):
            errors.append(err(RULE, "link_source_ineligible", link))
            continue
        if meta["clear_width_m"] != CLEAR_WIDTH_M or meta["wall_thickness_m"] != WALL_M:
            errors.append(err(RULE, "passage_dimensions", link))
        if len(groups.get(link, [])) != 2:
            errors.append(
                err(RULE, "link_edges_missing", f"{link}: expected two diagonal edges")
            )
        expected_edges = {
            (meta["from_port_id"], f"{passage['cell_id']}:a"),
            (f"{passage['cell_id']}:b", meta["to_port_id"]),
        }
        actual_edges = {(edge["from"], edge["to"]) for edge in groups.get(link, [])}
        if actual_edges != expected_edges:
            errors.append(err(RULE, "link_edges_miswired", link))
        for port_id, paired_cell in (
            (meta["from_port_id"], a),
            (meta["to_port_id"], b),
        ):
            record = ports.get(port_id)
            if (
                not record
                or record[0] is not paired_cell
                or not paired_cell.get("diagonal_link_chamfer")
            ):
                errors.append(err(RULE, "source_chamfer_missing", f"{link}: {port_id}"))
        p_a = ports.get(meta["from_port_id"])
        p_b = ports.get(meta["to_port_id"])
        p_pass = {p["port_id"]: p for p in passage["required_ports"]}
        if p_a and p_b and len(p_pass) == 2:
            pa, pb = p_a[1], p_b[1]
            ca = a.get("diagonal_link_chamfer", {}).get("corner_xz", [])
            cb = b.get("diagonal_link_chamfer", {}).get("corner_xz", [])
            da = p_pass.get(f"{passage['cell_id']}:a")
            db = p_pass.get(f"{passage['cell_id']}:b")
            if (
                da is None
                or db is None
                or not point_matches(pa["pos_xz"], da["pos_xz"])
                or not point_matches(pb["pos_xz"], db["pos_xz"])
            ):
                errors.append(err(RULE, "passage_port_misaligned", link))
            if da and db:
                n = pa["normal"]
                if (
                    len(ca) != 2
                    or len(cb) != 2
                    or abs(abs(cb[0] - ca[0]) - 1.0) > EPS
                    or abs(abs(cb[1] - ca[1]) - 1.0) > EPS
                ):
                    errors.append(err(RULE, "source_corners_not_one_metre_apart", link))
                if ca and not point_matches(
                    pa["pos_xz"],
                    [
                        ca[0] - n[0] * CHAMFER_M / math.sqrt(2),
                        ca[1] - n[1] * CHAMFER_M / math.sqrt(2),
                    ],
                ):
                    errors.append(err(RULE, "from_chamfer_port_mismatch", link))
                if cb and not point_matches(
                    pb["pos_xz"],
                    [
                        cb[0] - pb["normal"][0] * CHAMFER_M / math.sqrt(2),
                        cb[1] - pb["normal"][1] * CHAMFER_M / math.sqrt(2),
                    ],
                ):
                    errors.append(err(RULE, "to_chamfer_port_mismatch", link))
                if (
                    math.dist(
                        n,
                        [
                            DIAG * (1 if n[0] > 0 else -1),
                            DIAG * (1 if n[1] > 0 else -1),
                        ],
                    )
                    > EPS
                ):
                    errors.append(err(RULE, "port_normal_not_45", link))
                if (
                    math.dist(da["normal"], [-n[0], -n[1]]) > EPS
                    or math.dist(db["normal"], n) > EPS
                    or math.dist(pb["normal"], [-n[0], -n[1]]) > EPS
                ):
                    errors.append(err(RULE, "port_normals_not_outward", link))
                expected_length = math.dist(pa["pos_xz"], pb["pos_xz"])
                if abs(meta["length_m"] - expected_length) > EPS:
                    errors.append(err(RULE, "passage_length_mismatch", link))
                expected_poly = _passage_polygon(
                    pa["pos_xz"], pb["pos_xz"], CLEAR_WIDTH_M / 2 + WALL_M
                )
                if any(
                    not point_matches(p, q)
                    for p, q in zip(meta["outline_xz"], expected_poly)
                ):
                    errors.append(err(RULE, "passage_outline_mismatch", link))
        start = (
            ports[meta["from_port_id"]][1]["pos_xz"]
            if meta["from_port_id"] in ports
            else [0.0, 0.0]
        )
        finish = (
            ports[meta["to_port_id"]][1]["pos_xz"]
            if meta["to_port_id"] in ports
            else [0.0, 0.0]
        )
        errors.extend(
            polygon_errors(passage, document["cells"], (a_id, b_id), start, finish)
        )
    return errors
