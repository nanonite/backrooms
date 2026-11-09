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
GENERATOR_VERSION_V7 = "gmap-0.7.0"
GENERATOR_VERSION_V8 = "gmap-0.8.0"
GENERATOR_VERSION_V9 = "gmap-0.9.0"
GENERATOR_VERSION_V10 = "gmap-0.10.0"
VERSIONS = (
    GENERATOR_VERSION,
    GENERATOR_VERSION_V2,
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
)
MARGIN_VERSIONS = (
    GENERATOR_VERSION_V2,
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
)  # standard margins + degenerate cells
MODULE_VERSIONS = (
    GENERATOR_VERSION_V3,
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
)  # library modules as leaf cells
STAGE2_VERSIONS = (
    GENERATOR_VERSION_V4,
    GENERATOR_VERSION_V5,
    GENERATOR_VERSION_V6,
    GENERATOR_VERSION_V61,
    GENERATOR_VERSION_V7,
    GENERATOR_VERSION_V8,
    GENERATOR_VERSION_V9,
    GENERATOR_VERSION_V10,
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
RULE_IDS_V7 = sorted([*RULE_IDS_V61, "landmark_contract"])
RULE_IDS_V8 = sorted([*RULE_IDS_V7, "light_layer"])
RULE_IDS_V9 = sorted([*RULE_IDS_V8, "surface_layer"])
RULE_IDS_V10 = sorted([*RULE_IDS_V9, "elevation_layer"])
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
    if version in (
        GENERATOR_VERSION_V5,
        GENERATOR_VERSION_V6,
        GENERATOR_VERSION_V61,
        GENERATOR_VERSION_V7,
    ):
        return GENERATOR_VERSION_V4
    return version


def rule_ids(version: str) -> list[str]:
    if version == GENERATOR_VERSION_V10:
        return RULE_IDS_V10
    if version == GENERATOR_VERSION_V9:
        return RULE_IDS_V9
    if version == GENERATOR_VERSION_V8:
        return RULE_IDS_V8
    if version == GENERATOR_VERSION_V5:
        return RULE_IDS_V5
    if version == GENERATOR_VERSION_V6:
        return RULE_IDS_V6
    if version == GENERATOR_VERSION_V61:
        return RULE_IDS_V61
    if version == GENERATOR_VERSION_V7:
        return RULE_IDS_V7
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
        "ceiling_range_m": list(CEILING[cell.role])
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
    if version == GENERATOR_VERSION_V10:
        if stage_max not in (None, 3):
            raise GenerationError("gmap-0.10.0 requires --stage-max=3")
        document = build_map(
            seed, library, cells, 3, GENERATOR_VERSION_V9, degenerate_max
        )
        document["generator_version"] = GENERATOR_VERSION_V10
        document["map_id"] = map_id_for(seed, GENERATOR_VERSION_V10)
        document["rules"] = list(rule_ids(GENERATOR_VERSION_V10))
        from gmap_elevation import assign_elevation
        from gmap_light import assign_light
        from gmap_palette_registry import load_registry_v2
        from gmap_surface import assign_surface

        assign_elevation(document)
        assign_light(document, library)
        assign_surface(document, load_registry_v2())
        return document
    if version == GENERATOR_VERSION_V9:
        if stage_max not in (None, 3):
            raise GenerationError("gmap-0.9.0 requires --stage-max=3")
        document = build_map(
            seed, library, cells, 3, GENERATOR_VERSION_V8, degenerate_max
        )
        document["generator_version"] = GENERATOR_VERSION_V9
        document["map_id"] = map_id_for(seed, GENERATOR_VERSION_V9)
        document["rules"] = list(rule_ids(GENERATOR_VERSION_V9))
        from gmap_palette_registry import load_registry_v2, registry_ref_v2
        from gmap_surface import assign_surface

        document["palette_registry"] = registry_ref_v2()
        assign_surface(document, load_registry_v2())
        return document
    if version == GENERATOR_VERSION_V8:
        if stage_max not in (None, 3):
            raise GenerationError("gmap-0.8.0 requires --stage-max=3")
        document = build_map(
            seed, library, cells, 3, GENERATOR_VERSION_V7, degenerate_max
        )
        document["generator_version"] = GENERATOR_VERSION_V8
        document["map_id"] = map_id_for(seed, GENERATOR_VERSION_V8)
        document["rules"] = list(rule_ids(GENERATOR_VERSION_V8))
        from gmap_light import assign_light

        assign_light(document, library)
        return document
    v4 = version in STAGE2_VERSIONS
    stage_limit = 3 if version == GENERATOR_VERSION_V7 else 2 if v4 else 1
    stage_max = (
        (stage_limit if version == GENERATOR_VERSION_V7 else 2 if v4 else 1)
        if stage_max is None
        else stage_max
    )
    if stage_max not in range(stage_limit + 1) or (stage_max >= 2 and not v4):
        raise GenerationError(
            f"--stage-max must be 0..{stage_limit} in generator {version}"
        )
    if version == GENERATOR_VERSION_V7 and stage_max != 3:
        raise GenerationError("gmap-0.7.0 requires --stage-max=3")
    if degenerate_max < 0:
        raise GenerationError("--degenerate-max must be >= 0")
    growth_cell_target = cells
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
        extras = assign_stage2(
            seed, attempt, layout_version(version), cells, min(stage_max, 2)
        )
        for record in cells:
            record.update(extras[record["cell_id"]])
        if version == GENERATOR_VERSION_V7:
            _assign_landmark_target(draft, cells, stage_max)
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
    if version in (GENERATOR_VERSION_V61, GENERATOR_VERSION_V7):
        document["layout_variant"] = draft.layout_variant
    if version == GENERATOR_VERSION_V7 and draft.landmark_plan is not None:
        from gmap_landmark import map_landmark

        document["landmark"] = map_landmark(
            draft.landmark_plan,
            "placed" if draft.landmark_cell_id else "unplaced",
            draft.landmark_cell_id,
            None if draft.landmark_cell_id else "no_legal_attachment_after_target_step",
        )
    if version == GENERATOR_VERSION_V7:
        document["growth_cell_target"] = growth_cell_target
    if v2:
        document["degenerate_budget"] = {"max": degenerate_max, "used": used}
    if v3:
        placed = sum(1 for c in draft.cells.values() if c.module)
        document["module_budget"] = {**MODULE_BUDGET, "used": placed}
    if version == GENERATOR_VERSION_V6:
        from gmap_diagonal import apply_links

        apply_links(document)
    if version in (GENERATOR_VERSION_V61, GENERATOR_VERSION_V7):
        from gmap_diagonal_v61 import apply_links_v61

        apply_links_v61(document, draft.reserved_diagonal_zones, draft.diagonal_budget)
    if version in (
        GENERATOR_VERSION_V5,
        GENERATOR_VERSION_V6,
        GENERATOR_VERSION_V61,
        GENERATOR_VERSION_V7,
    ):
        document["palette_registry"] = registry_ref()
        palettes = assign_palettes(document, library, load_registry())
        for record in document["cells"]:
            if record["cell_id"] in palettes:
                record["palette"] = palettes[record["cell_id"]]
        if version in (
            GENERATOR_VERSION_V6,
            GENERATOR_VERSION_V61,
            GENERATOR_VERSION_V7,
        ):
            by_id = {c["cell_id"]: c for c in document["cells"]}
            for record in document["cells"]:
                passage = record.get("diagonal_passage")
                if passage and passage["from_cell_id"] in by_id:
                    source_palette = by_id[passage["from_cell_id"]].get("palette")
                    if source_palette:
                        record["palette"] = dict(source_palette)
    return document


def _assign_landmark_target(
    draft: Any, records: list[dict[str, Any]], stage_max: int
) -> None:
    if stage_max < 3 or draft.landmark_plan is None:
        return
    by_id = {record["cell_id"]: record for record in records}
    cell_id = draft.landmark_cell_id
    if cell_id is None:
        return
    from gmap_landmark import cell_landmark

    record = by_id[cell_id]
    record["shape_stage_target"] = 3
    record.pop("shape_class_target", None)
    record["allowed_primitives"] = [
        *record["allowed_primitives"],
        draft.landmark_plan["class"],
    ]
    record["landmark"] = cell_landmark(draft.landmark_plan)
