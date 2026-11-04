"""Assemble a generative map document from the staged draft."""

from __future__ import annotations

from typing import Any

from gmap_assign import VOID_BUDGET
from gmap_geometry import PORT_STEP_M, rect_polygon
from gmap_grow import PORT_TYPE, Draft, GenerationError
from gmap_library import Library, figure_classes, metadata_records
from gmap_modules import MODULE_BUDGET
from gmap_palette import assign_palettes
from gmap_palette_registry import load_registry, registry_ref
from gmap_stage2 import PRIMITIVES_BY_STAGE, assign_stage2

GENERATOR_VERSION = "gmap-0.1.0"
GENERATOR_VERSION_V2 = "gmap-0.2.0"
GENERATOR_VERSION_V3 = "gmap-0.3.0"
GENERATOR_VERSION_V4 = "gmap-0.4.0"
GENERATOR_VERSION_V5 = "gmap-0.5.0"
GENERATOR_VERSION_V6 = "gmap-0.6.0"
GENERATOR_VERSION_V61 = "gmap-0.6.1"
VERSIONS = (
    GENERATOR_VERSION,
    GENERATOR_VERSION_V2,
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
)
MARGIN_VERSIONS = (
    GENERATOR_VERSION_V2,
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
)  # standard margins + degenerate cells
MODULE_VERSIONS = (
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
)  # library modules as leaf cells
STAGE2_VERSIONS = (
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
)  # 45-degree classes, library-room overhang margin
DEFAULT_DEGENERATE_MAX = 1
MAX_ATTEMPTS = 50
CELL_RANGE = (6, 20)
RULE_IDS = [
    "branch_required",
    "figure_not_adjacent",
    "no_envelope_overlap",
    "ports_on_lattice",
    "ports_on_shared_edge",
    "tree_no_loops",
    "void_visible_from_walkable",
    "voids_never_traversable",
]
RULE_IDS_V2 = sorted(
    [*RULE_IDS, "degenerate_only_in_degenerate_cells", "standard_doorway_margin"]
)
RULE_IDS_V3 = sorted(
    [
        *RULE_IDS_V2,
        "module_budget",
        "module_leaf_proposed_untested",
        "module_socket_landing",
        "module_usable_once",
    ]
)
RULE_IDS_V4 = sorted([*RULE_IDS_V3, "shape_stage2_eligibility"])
RULE_IDS_V5 = sorted([*RULE_IDS_V4, "palette_assignment"])
RULE_IDS_V6 = sorted([*RULE_IDS_V5, "diagonal_links"])
RULE_IDS_V61 = sorted([*RULE_IDS_V6, "diagonal_site_reservations"])
CEILING = {
    "figure": [3.0, 6.0],
    "ground": [2.6, 4.8],
    "threshold": [2.6, 4.8],
    "void": [2.6, 4.8],
}
STREAM_STRIDE = 1 << 32
MAX_SITE_LAYOUT_VARIANTS = 48


def map_id_for(seed: int, version: str = GENERATOR_VERSION) -> str:
    return f"gmap-{seed}-{version}"


def layout_version(version: str) -> str:
    """gmap-0.5.0 draws its layout, degenerate and shape-stage streams exactly as gmap-0.4.0 does, so a
    0.5.0 map differs from the 0.4.0 map of the same seed only by its palettes."""
    if version in (GENERATOR_VERSION_V5, GENERATOR_VERSION_V6, GENERATOR_VERSION_V61):
        return GENERATOR_VERSION_V4
    return version


def rule_ids(version: str) -> list[str]:
    if version == GENERATOR_VERSION_V5:
        return RULE_IDS_V5
    if version == GENERATOR_VERSION_V6:
        return RULE_IDS_V6
    if version == GENERATOR_VERSION_V61:
        return RULE_IDS_V61
    if version == GENERATOR_VERSION_V4:
        return RULE_IDS_V4
    if version == GENERATOR_VERSION_V3:
        return RULE_IDS_V3
    return RULE_IDS_V2 if version == GENERATOR_VERSION_V2 else RULE_IDS


def port_json(port: Any, v2: bool) -> dict[str, Any]:
    record = {
        "port_id": port.port_id,
        "pos_xz": list(port.pos),
        "normal": list(port.normal),
        "compatibility_type": port.compatibility_type,
    }
    if v2:
        record["placement"] = port.placement
    return record


def cell_json(
    cell: Any, primitives: list[str], v2: bool = False, ceiling_m: float | None = None
) -> dict[str, Any]:
    record = {
        "cell_id": cell.cell_id,
        "envelope_xz": rect_polygon(cell.rect),
        "ceiling_range_m": CEILING[cell.role]
        if ceiling_m is None
        else [ceiling_m, ceiling_m],
        "allowed_primitives": primitives,
        "required_ports": [port_json(port, v2) for port in cell.ports],
        "role": cell.role,
        "rarity_tier": cell.tier if cell.role != "void" else 0,
    }
    if v2:
        record["mode"] = cell.mode
    if cell.module:
        record["module"] = {key: value for key, value in cell.module.items()}
    return record


def edge_json(draft: Draft, a: str, b: str, connector: str) -> dict[str, str]:
    edge = {"from": a, "to": b, "connector": connector}
    if (a, b) in draft.untested:
        edge["connection_status"] = "proposed_untested"
    return edge


def lattice_json(v2: bool) -> dict[str, Any]:
    lattice: dict[str, Any] = {"kind": "square", "unit_m": 1.0, "port_unit": PORT_TYPE}
    if v2:
        lattice["port_step_m"] = PORT_STEP_M
    return lattice


def build_map(
    seed: int,
    library: Library,
    cells: int = 12,
    stage_max: int | None = None,
    version: str = GENERATOR_VERSION,
    degenerate_max: int = DEFAULT_DEGENERATE_MAX,
) -> dict[str, Any]:
    if version not in VERSIONS:
        raise GenerationError(f"generator version must be one of {', '.join(VERSIONS)}")
    v4 = version in STAGE2_VERSIONS
    stage_max = (2 if v4 else 1) if stage_max is None else stage_max
    if stage_max not in (0, 1, 2) or (stage_max == 2 and not v4):
        raise GenerationError(
            f"--stage-max must be 0..{2 if v4 else 1} in generator {version}"
        )
    if degenerate_max < 0:
        raise GenerationError("--degenerate-max must be >= 0")
    base_version = GENERATOR_VERSION_V5 if version == GENERATOR_VERSION_V6 else version
    from gmap_draft_generation import generate_draft

    draft, attempt, used = generate_draft(
        seed, cells, figure_classes(library), base_version, degenerate_max, library
    )
    primitives = PRIMITIVES_BY_STAGE[min(stage_max, 1)]
    v2 = version in MARGIN_VERSIONS
    v3 = version in MODULE_VERSIONS
    heights = {m.module_id: m.ceiling_height_m for m in library.modules}
    cells = [
        cell_json(
            c, primitives, v2, heights.get(c.module["module_id"]) if c.module else None
        )
        for c in draft.cells.values()
    ]
    if v4:
        extras = assign_stage2(seed, attempt, layout_version(version), cells, stage_max)
        for record in cells:
            record.update(extras[record["cell_id"]])
    document = {
        "schema_version": 1,
        "map_id": map_id_for(seed, version),
        "generator_version": version,
        "seed": seed,
        "attempt": attempt,
        "catalog_snapshot": dict(library.snapshot_ref),
        "library_index": {
            **library.index_ref,
            "metadata_records": metadata_records(library),
        }
        if v3
        else dict(library.index_ref),
        "lattice": lattice_json(v2),
        "shape_stage_max": stage_max,
        "cells": cells,
        "edges": sorted(
            (edge_json(draft, a, b, k) for a, b, k in draft.edges),
            key=lambda e: (e["from"], e["to"]),
        ),
        "distribution": {
            "tier_curve": "2d6",
            "repetition_budget": {
                "max_same_module_adjacent": 0,
                "max_same_primitive_run": 3,
            },
        },
        "void_budget": dict(VOID_BUDGET),
        "rules": list(rule_ids(version)),
        "registration_accepted": False,
        "scale_calibrated": False,
    }
    if version == GENERATOR_VERSION_V61:
        document["layout_variant"] = draft.layout_variant
    if v2:
        document["degenerate_budget"] = {"max": degenerate_max, "used": used}
    if v3:
        placed = sum(1 for c in draft.cells.values() if c.module)
        document["module_budget"] = {**MODULE_BUDGET, "used": placed}
    if version == GENERATOR_VERSION_V6:
        from gmap_diagonal import apply_links

        apply_links(document)
    if version == GENERATOR_VERSION_V61:
        from gmap_diagonal_v61 import apply_links_v61

        apply_links_v61(document, draft.reserved_diagonal_zones, draft.diagonal_budget)
    if version in (GENERATOR_VERSION_V5, GENERATOR_VERSION_V6, GENERATOR_VERSION_V61):
        document["palette_registry"] = registry_ref()
        palettes = assign_palettes(document, library, load_registry())
        for record in document["cells"]:
            if record["cell_id"] in palettes:
                record["palette"] = palettes[record["cell_id"]]
        if version in (GENERATOR_VERSION_V6, GENERATOR_VERSION_V61):
            by_id = {c["cell_id"]: c for c in document["cells"]}
            for record in document["cells"]:
                passage = record.get("diagonal_passage")
                if passage and passage["from_cell_id"] in by_id:
                    source_palette = by_id[passage["from_cell_id"]].get("palette")
                    if source_palette:
                        record["palette"] = dict(source_palette)
    return document
