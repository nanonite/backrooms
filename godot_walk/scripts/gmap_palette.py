"""Generated rooms take a material palette from nearby library figure rooms (issue 192).

For every walkable non-module cell, graph distance d over open (direct) edges to each placed FIGURE
module. A module's palette is the first non-default registry palette whose style tags overlap its
accepted style_tags; ground (kit) modules and unmatched figures exert no influence.
d = 1 takes the palette, d = 2 takes it with probability 0.5 (one seeded coin per cell, drawn in
cell_id order for every such cell whether or not it is needed), d >= 3 stays default. Competing
anchors: smaller d, then higher rarity_tier, then module_id. Module and void cells carry no palette.

gmap-0.12.0 then runs the regional floor layer (`gmap_floor_regions`): up to three non-anchored
seed cells spread a tile, metal or wood palette over graph distance 1 on its own keyed stream.
Library anchors always win, and the spawn cell plus its direct neighbours are excluded.
"""

from __future__ import annotations

import hashlib
import random
from collections import deque
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, sha256_file
from gmap_library import Library, LibraryModule, load_library
from gmap_palette_registry import (
    default_palette,
    load_registry_file,
    palette_by_id,
    registry_errors,
    registry_ref_v2,
    registry_ref_v3,
    select_palette,
)
from gmap_rules import Errors, edge_cells, err
from gmap_keyed import rng_for_cell

RULE = "palette_assignment"
FLOOR_REGION_RULE = "floor_region_layer"
FULL_DISTANCE = 1
COIN_DISTANCE = 2
COIN_PROBABILITY = 0.5
REGION_VERSIONS = ("gmap-0.12.0", "gmap-0.13.0")
REGISTRY_VERSION_V3 = "0.3.0"


def palette_rng(seed: int, attempt: int, version: str) -> random.Random:
    """Separate sha256-derived stream; never Python hash()."""
    if version in (
        "gmap-0.8.0",
        "gmap-0.9.0",
        "gmap-0.10.0",
        "gmap-0.11.0",
        "gmap-0.12.0",
    ):
        version = "gmap-0.7.0"  # v0.8 lighting, v0.9 surfaces, v0.10 elevation, v0.11 reverb, v0.12 floor regions; anchor draws unchanged.
    digest = hashlib.sha256(f"{seed}:{attempt}:palette:{version}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def open_neighbours(document: dict[str, Any]) -> dict[str, set[str]]:
    """Walkable cells joined by a direct (traversable) edge."""
    walkable = {c["cell_id"] for c in document["cells"] if c["role"] != "void"}
    graph: dict[str, set[str]] = {cell: set() for cell in walkable}
    for edge in document["edges"]:
        a, b = edge_cells(edge)
        if edge["connector"] == "direct" and a in walkable and b in walkable:
            graph[a].add(b)
            graph[b].add(a)
    return graph


def distances(graph: dict[str, set[str]], source: str) -> dict[str, int]:
    found = {source: 0}
    queue = deque([source])
    while queue:
        cell = queue.popleft()
        for other in sorted(graph[cell]):
            if other not in found:
                found[other] = found[cell] + 1
                queue.append(other)
    return found


def module_of(library: Library, placement: dict[str, Any]) -> LibraryModule | None:
    return next(
        (
            m
            for m in library.modules
            if (m.module_id, m.version)
            == (placement["module_id"], placement["version"])
        ),
        None,
    )


def anchors(
    document: dict[str, Any], library: Library, registry: dict[str, Any]
) -> list[dict[str, Any]]:
    """Placed figure modules whose style tags select a palette: cell, module, tier and palette."""
    found = []
    for cell in document["cells"]:
        module = module_of(library, cell["module"]) if cell.get("module") else None
        palette = (
            select_palette(registry, module.style_tags)
            if module and module.form_role == "figure"
            else None
        )
        if module and palette:
            found.append(
                {
                    "cell_id": cell["cell_id"],
                    "module_id": module.module_id,
                    "tier": int(module.rarity_tier or 0),
                    "palette_id": palette["palette_id"],
                }
            )
    return found


def record(
    palette_id: str,
    anchor: str | None = None,
    distance: int | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "palette_id": palette_id,
        "anchor_module_id": anchor,
        "distance": distance,
    }
    if version in REGION_VERSIONS:
        result["registry_version"] = REGISTRY_VERSION_V3
    return result


def palette_assignment(
    document: dict[str, Any], library: Library, registry: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    """cell_id -> palette record, plus the floor-region metadata on gmap-0.12.0."""
    version = document["generator_version"]
    base = default_palette(registry)["palette_id"]
    graph = open_neighbours(document)
    reach = [
        (a, distances(graph, a["cell_id"]))
        for a in anchors(document, library, registry)
    ]
    rng = palette_rng(
        document["seed"], document["attempt"], document["generator_version"]
    )
    records: dict[str, dict[str, Any]] = {}
    for cell in sorted(document["cells"], key=lambda c: c["cell_id"]):
        if cell["role"] == "void" or cell.get("module"):
            continue
        passage = cell.get("diagonal_passage")
        if passage and passage.get("palette_source_cell_id") in records:
            records[cell["cell_id"]] = dict(records[passage["palette_source_cell_id"]])
            continue
        coin = (
            rng_for_cell(
                document["seed"],
                document["attempt"],
                "palette-anchor:gmap-0.13.0",
                cell["cell_id"],
                "anchor-choice",
            ).random()
            if version == "gmap-0.13.0"
            else rng.random()
        )
        near = [
            (d[cell["cell_id"]], -a["tier"], a["module_id"], a)
            for a, d in reach
            if d.get(cell["cell_id"], 99) <= COIN_DISTANCE
        ]
        if not near:
            records[cell["cell_id"]] = record(base, version=version)
            continue
        distance, _, _, anchor = min(near, key=lambda item: item[:3])
        takes = distance == FULL_DISTANCE or coin < COIN_PROBABILITY
        records[cell["cell_id"]] = (
            record(anchor["palette_id"], anchor["module_id"], distance, version)
            if takes
            else record(base, version=version)
        )
    regions = None
    if version in REGION_VERSIONS:
        from gmap_floor_regions import apply_floor_regions

        records, regions = apply_floor_regions(document, records)
        by_id = {cell["cell_id"]: cell for cell in document["cells"]}
        for cell in sorted(document["cells"], key=lambda c: c["cell_id"]):
            passage = cell.get("diagonal_passage")
            if not passage:
                continue
            source_id = passage.get("palette_source_cell_id") or passage.get(
                "from_cell_id"
            )
            if source_id in records and cell["cell_id"] in by_id:
                records[cell["cell_id"]] = dict(records[source_id])
    return records, regions


def assign_palettes(
    document: dict[str, Any], library: Library, registry: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """cell_id -> palette record for every walkable non-module cell."""
    return palette_assignment(document, library, registry)[0]


def palette_errors(
    document: dict[str, Any],
    root: Path = ROOT,
    library: Library | None = None,
) -> Errors:
    """gmap-0.5.0: the registry is current and every cell's palette is the one the rules give."""
    ref = document.get("palette_registry")
    if ref is None:
        return [
            err(
                RULE,
                "palette_registry_missing",
                "palette_registry is required in gmap-0.5.0",
            )
        ]
    path = root / ref["path"]
    if not path.is_file():
        return [err(RULE, "stale_palette_registry", f"{ref['path']} is missing")]
    if sha256_file(path) != ref["sha256"]:
        return [
            err(
                RULE,
                "stale_palette_registry",
                f"{ref['path']} no longer matches its recorded hash",
            )
        ]
    errors: Errors = []
    version = document["generator_version"]
    if version in REGION_VERSIONS:
        if ref != registry_ref_v3(root):
            errors.append(
                err(
                    RULE,
                    "palette_registry_not_canonical",
                    f"{ref['path']} is not the canonical 0.3.0 registry",
                )
            )
    elif version in (
        "gmap-0.9.0",
        "gmap-0.10.0",
        "gmap-0.11.0",
    ) and ref != registry_ref_v2(root):
        errors.append(
            err(
                RULE,
                "palette_registry_not_canonical",
                f"{ref['path']} is not the canonical 0.2.0 registry",
            )
        )
    try:
        registry = load_registry_file(path)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [
            err(
                RULE,
                "palette_registry_invalid",
                f"{ref['path']} could not be loaded: {error}",
            )
        ]
    errors += [
        err(RULE, "palette_registry_invalid", problem)
        for problem in registry_errors(registry, root)
    ]
    if errors:
        return errors
    if library is None:
        library = load_library(root / document["library_index"]["path"], root)
    expected, regions = palette_assignment(document, library, registry)
    for cell in document["cells"]:
        got, want = cell.get("palette"), expected.get(cell["cell_id"])
        if got is not None and palette_by_id(registry, got["palette_id"]) is None:
            errors.append(
                err(RULE, "palette_unknown", f"{cell['cell_id']}: {got['palette_id']}")
            )
        elif got != want:
            errors.append(
                err(
                    RULE,
                    "palette_mismatch",
                    f"{cell['cell_id']}: has {got}, rules give {want}",
                )
            )
    if version in REGION_VERSIONS and document.get("floor_regions") != regions:
        errors.append(
            err(
                FLOOR_REGION_RULE,
                "floor_region_metadata_mismatch",
                "floor_regions does not match the keyed re-derivation",
            )
        )
    return errors
