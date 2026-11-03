"""Build deterministic integration_proposal records from mechanical fits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from deterministic_json import canonical_bytes, sha256_bytes
from integration_fit import Fit, ModuleGeometry, SlotGeom, SocketGeom
from poetics_geometry import open_ring

SCHEMA_PATH = "godot_walk/room_catalog/integration_proposal.schema.json"
FIT_NOTE = "mechanical fit score, not a visual judgement"
NO_CONNECTIVITY = "No video connectivity inferred"
ADAPTER_ASSUMPTION = (
    "Adapter work requires a new module version, separate collision, "
    "bidirectional traversal tests and operator review"
)
UNACCEPTED_ASSUMPTION = "poetics not operator-accepted"
UNREGISTERED_ASSUMPTION = (
    "Map coordinates are unregistered and unscaled (registration_accepted=false, "
    "scale_calibrated=false)"
)
PROPOSAL_ID_LENGTH = 16


class ProposalError(ValueError):
    """A proposal record cannot be built or fails its schema."""


@dataclass(frozen=True)
class ProposalContext:
    source_id: str
    module_id: str
    version: int
    draft: dict[str, Any]
    draft_path: str
    draft_accepted: bool
    index: dict[str, Any]
    index_sha256: str
    map_id: str
    map_path: str


def module_geometry(draft: dict[str, Any], entry: dict[str, Any]) -> ModuleGeometry:
    tested = {item["socket_id"] for item in draft["ports"]["tested_sockets"]}
    sockets = [
        SocketGeom(
            socket["id"],
            (socket["local_floor_center"][0], socket["local_floor_center"][2]),
            (socket["outward_normal"][0], socket["outward_normal"][2]),
            socket["compatibility_type"],
        )
        for socket in entry["sockets"]
        if socket["id"] in tested
    ]
    slots = [
        SlotGeom(
            slot["slot_id"], tuple(slot["from_xz"]), tuple(slot["to_xz"]),
            tuple(slot["outward_normal_xz"]),
        )
        for slot in draft["ports"]["port_slots"]
    ]
    return ModuleGeometry(open_ring(draft["shape"]["footprint_xz"]), sockets, slots)


def _clean(value: float) -> float:
    return round(float(value), 6) + 0.0


def _partners(ctx: ProposalContext, socket_id: str) -> list[tuple[dict[str, str], str, str]]:
    """Tested pair partners of our socket as (socket_ref, pair_id, placement_scope)."""
    pair_ids = {
        pair["pair_id"]: pair["placement_scope"]
        for item in ctx.draft["ports"]["tested_sockets"]
        if item["socket_id"] == socket_id
        for pair in item["pairs"]
    }
    versions = {m["module_id"]: m["version"] for m in ctx.index["modules"]}
    found = []
    for pair in ctx.index["connector_pairs"]:
        if pair["id"] not in pair_ids:
            continue
        ends = [pair["from"], pair["to"]]
        mine = [end for end in ends if end == [ctx.module_id, socket_id]]
        other = [end for end in ends if end != [ctx.module_id, socket_id]]
        if mine and other:
            ref = {"module_id": other[0][0], "version": versions[other[0][0]], "socket_id": other[0][1]}
            found.append((ref, pair["id"], pair_ids[pair["id"]]))
    return sorted(found, key=lambda item: (item[0]["module_id"], item[0]["socket_id"], item[1]))


def _text_lists(ctx: ProposalContext, fit: Fit, partners: dict[str, list]) -> dict[str, Any]:
    sockets = [c for c in fit.covers if c.kind == "socket"]
    adapters = [c for c in fit.covers if c.kind == "adapter"]
    approach = {s["id"]: s.get("approach_clearance_m") for e in ctx.index["modules"]
                if e["module_id"] == ctx.module_id for s in e["sockets"]}
    clearance = [
        f"Verify the {approach[c.ref]} m approach clearance at socket {c.ref} for port {c.port_id}."
        for c in sockets
    ] + [f"Verify clearance around the new opening at port slot {c.ref} for port {c.port_id}." for c in adapters]
    collision = [f"Author matching collision for the adapter opening at port slot {c.ref}." for c in adapters]
    junction = [f"Retest the join at port {c.port_id} in this placement; tested only in pair {pair_id} "
                f"({scope})." for c in sockets for _ref, pair_id, scope in partners[c.ref]]
    junction += [f"Test bidirectional traversal across the adapter at port {c.port_id}." for c in adapters]
    return {
        "clearance": clearance,
        "collision": collision or ["No new collision proposed; tested socket collision is reused unchanged."],
        "junction": junction,
    }


def _assumptions(ctx: ProposalContext, adapter: bool) -> list[str]:
    items = [NO_CONNECTIVITY, UNREGISTERED_ASSUMPTION]
    if adapter:
        items.append(ADAPTER_ASSUMPTION)
    if not ctx.draft_accepted:
        items.append(UNACCEPTED_ASSUMPTION)
    return items


def _evidence(ctx: ProposalContext) -> list[str]:
    return [ctx.draft_path, ctx.map_path, ctx.index["snapshot_path"]]


def _finish(ctx: ProposalContext, record: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in record.items() if key != "proposal_id"}
    record["proposal_id"] = sha256_bytes(canonical_bytes(body))[:PROPOSAL_ID_LENGTH]
    return record


def _base(ctx: ProposalContext) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_id": ctx.source_id,
        "module": {"module_id": ctx.module_id, "version": ctx.version},
        "catalog_snapshot_sha256": ctx.draft["catalog_snapshot_sha256"],
        "library_index_sha256": ctx.index_sha256,
        "map_id": ctx.map_id,
        "evidence": _evidence(ctx),
    }


def propose_record(ctx: ProposalContext, fit: Fit, envelope_area: float) -> dict[str, Any]:
    adapters = [c for c in fit.covers if c.kind == "adapter"]
    sockets = [c for c in fit.covers if c.kind == "socket"]
    partners = {c.ref: _partners(ctx, c.ref) for c in sockets}
    used = [
        {"from": {"module_id": ctx.module_id, "version": ctx.version, "socket_id": c.ref}, "to": ref}
        for c in sockets for ref, _pair, _scope in partners[c.ref]
    ] if not adapters else []
    targets = sorted({(ref["module_id"], ref["version"]) for c in sockets for ref, _p, _s in partners[c.ref]})
    unknowns = ["Light, scale and the connecting geometry beyond this module are not derived."]
    unknowns += [f"Pair {pair_id} is exact_pair_only; this placement is not covered by it."
                 for c in sockets for _r, pair_id, scope in partners[c.ref] if scope == "exact_pair_only"]
    rationale = (
        f"At yaw {fit.yaw_deg} and translation ({_clean(fit.translation[0])}, {_clean(fit.translation[1])}) "
        f"the placed footprint lies inside the envelope of cell {fit.cell_id}; {len(sockets)} of "
        f"{len(fit.covers)} required ports match tested sockets and {len(adapters)} need adapter work. "
        f"Mechanical score {fit.score:.3f} (envelope slack {fit.slack_m2} m2 of {_clean(envelope_area)} m2)."
    )
    if adapters and sockets:
        rationale += (" Tested sockets also align at " + ", ".join(c.ref for c in sockets)
                      + "; they are not listed in sockets_used because a record carries either tested sockets or an adapter.")
    record = _base(ctx) | {
        "targets": [{"module_id": m, "version": v} for m, v in targets],
        "cell_id": fit.cell_id,
        "placement": {"position_xz": [_clean(fit.translation[0]), _clean(fit.translation[1])],
                      "yaw_deg": fit.yaw_deg},
        "sockets_used": used,
        "adapter_required": None if not adapters else {
            "description": "Authored adapter geometry at " + ", ".join(sorted(c.ref for c in adapters))
            + " for ports " + ", ".join(c.port_id for c in adapters) + "; no source opening is implied.",
            "port_slot_ids": sorted(c.ref for c in adapters),
        },
        "work_required": _text_lists(ctx, fit, partners),
        "rationale": rationale,
        "assumptions": _assumptions(ctx, bool(adapters)),
        "unknowns": unknowns,
        "confidence": _clean(min(1.0, max(0.0, fit.score))),
        "outcome": "propose",
        "fit_result": {"footprint_fits": True, "ports_covered": not adapters, "notes": FIT_NOTE},
    }
    return _finish(ctx, record)


def keep_standalone_record(ctx: ProposalContext, footprint_fitted: bool, cell_count: int) -> dict[str, Any]:
    reason = ("a rotated footprint fits some cell envelope, but no placement covers every required port"
              if footprint_fitted else "the footprint fits no cell envelope at any tested rotation or translation")
    record = _base(ctx) | {
        "targets": [], "cell_id": None, "placement": None, "sockets_used": [], "adapter_required": None,
        "work_required": {"clearance": ["None proposed."], "collision": ["None proposed."], "junction": ["None proposed."]},
        "rationale": f"Of {cell_count} walkable cells, none admits this module: {reason}.",
        "assumptions": _assumptions(ctx, False),
        "unknowns": ["Whether a different map, a new module version or an adapter would fit is not assessed."],
        "confidence": 0.0,
        "outcome": "keep_standalone",
        "fit_result": {"footprint_fits": footprint_fitted, "ports_covered": False if footprint_fitted else None,
                       "notes": FIT_NOTE},
    }
    return _finish(ctx, record)


def validate_record(record: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(record)
    ]
    if errors:
        raise ProposalError("Proposal fails integration_proposal.schema.json: " + "; ".join(errors))
