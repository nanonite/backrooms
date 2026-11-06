"""Deterministic surface/wear assignment for gmap-0.9.0 (#199).

The surface post-pass runs after the light layer. It draws one wear level per
generated non-module cell and one clean/worn/damaged variant per palette
surface. Geometry, light and palette records are not touched.
"""

from __future__ import annotations

import hashlib
import random
from copy import deepcopy
from typing import Any

RULE = "surface_layer"
STREAM = "surface:gmap-0.9.0"
SURFACES = ("floor", "wall", "ceiling", "trim")
WEAR_BUCKETS = {
    "bright": ((80, 0), (98, 1), (100, 2)),
    "normal": ((62, 0), (92, 1), (100, 2)),
    "dim": ((45, 1), (100, 2)),
}
VARIANT_BUCKETS = {
    0: ((100, "clean"),),
    1: ((35, "clean"), (90, "worn"), (100, "damaged")),
    2: ((5, "clean"), (40, "worn"), (100, "damaged")),
}
ACOUSTIC_TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris")


def rng_for(seed: int, attempt: int) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{attempt}:{STREAM}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


def _draw_weighted(
    rng: random.Random, buckets: tuple[tuple[int, int | str], ...]
) -> Any:
    draw = rng.randrange(100)
    return next(label for limit, label in buckets if draw < limit)


def _palette(
    registry: dict[str, Any], cell: dict[str, Any], default_id: str
) -> dict[str, Any]:
    palette_id = (cell.get("palette") or {}).get("palette_id", default_id)
    return next(
        (
            palette
            for palette in registry["palettes"]
            if palette["palette_id"] == palette_id
        ),
        next(palette for palette in registry["palettes"] if palette["is_default"]),
    )


def _wear(
    cell: dict[str, Any], spawn_id: str, wing: set[str], rng: random.Random
) -> int:
    if cell["cell_id"] in wing:
        return int(_draw_weighted(rng, WEAR_BUCKETS["dim"]))
    if cell["cell_id"] == spawn_id or cell.get("landmark"):
        return 0
    tier = str((cell.get("light") or {}).get("tier", "normal"))
    return int(_draw_weighted(rng, WEAR_BUCKETS.get(tier, WEAR_BUCKETS["normal"])))


def _variants(palette: dict[str, Any], wear: int, rng: random.Random) -> dict[str, str]:
    selected = {}
    for surface in SURFACES:
        variant = str(_draw_weighted(rng, VARIANT_BUCKETS[wear]))
        available = palette["surfaces"][surface]["variants"]
        if variant not in available:
            variant = "clean" if "clean" in available else min(available)
        selected[surface] = variant
    return selected


def assign_surface(document: dict[str, Any], registry: dict[str, Any]) -> None:
    """Attach wear and surface variants without consuming any geometry/light/palette stream."""
    rng = rng_for(document["seed"], document.get("attempt", 0))
    default_id = next(
        palette["palette_id"]
        for palette in registry["palettes"]
        if palette["is_default"]
    )
    spawn_id = document["cells"][0]["cell_id"]
    wing = set(document.get("dark_wing", {}).get("cell_ids", []))
    for cell in sorted(document["cells"], key=lambda item: item["cell_id"]):
        if cell["role"] == "void" or cell.get("module"):
            continue
        palette = _palette(registry, cell, default_id)
        wear = _wear(cell, spawn_id, wing, rng)
        cell["wear"] = wear
        cell["surface_variants"] = _variants(palette, wear, rng)


def _variant_in_palette(palette: dict[str, Any], surface: str, variant: str) -> bool:
    return variant in palette["surfaces"][surface]["variants"]


def surface_errors(
    document: dict[str, Any], registry: dict[str, Any]
) -> list[dict[str, str]]:
    """Check wear/variant determinism, ranges and the light-correlated constraints."""
    palettes = registry.get("palettes")
    if not isinstance(palettes, list) or not any(
        palette.get("is_default") for palette in palettes
    ):
        return [_error("surface_registry_invalid", "registry has no default palette")]
    expected = deepcopy(document)
    for cell in expected["cells"]:
        cell.pop("wear", None)
        cell.pop("surface_variants", None)
    assign_surface(expected, registry)
    expected_by_id = {cell["cell_id"]: cell for cell in expected["cells"]}
    default_id = next(
        palette["palette_id"]
        for palette in registry["palettes"]
        if palette["is_default"]
    )
    spawn_id = document["cells"][0]["cell_id"]
    wing = set(document.get("dark_wing", {}).get("cell_ids", []))
    errors: list[dict[str, str]] = []
    for cell in document["cells"]:
        generated = cell["role"] != "void" and not cell.get("module")
        has_any = "wear" in cell or "surface_variants" in cell
        has_both = "wear" in cell and "surface_variants" in cell
        if not generated:
            if has_any:
                errors.append(_error("surface_on_non_generated_cell", cell["cell_id"]))
            continue
        if not has_both:
            errors.append(_error("surface_layer_missing", cell["cell_id"]))
            continue
        wear = cell.get("wear")
        if not isinstance(wear, int) or not 0 <= wear <= 2:
            errors.append(_error("surface_wear_invalid", cell["cell_id"]))
        variants = cell.get("surface_variants")
        palette = _palette(registry, cell, default_id)
        if not isinstance(variants, dict) or set(variants) != set(SURFACES):
            errors.append(_error("surface_variants_invalid", cell["cell_id"]))
        else:
            for surface, variant in variants.items():
                if not _variant_in_palette(palette, surface, variant):
                    errors.append(
                        _error(
                            "surface_variant_unknown",
                            f"{cell['cell_id']}: {surface}={variant}",
                        )
                    )
        wanted = expected_by_id[cell["cell_id"]]
        if cell.get("wear") != wanted.get("wear") or cell.get(
            "surface_variants"
        ) != wanted.get("surface_variants"):
            errors.append(_error("surface_layer_mismatch", cell["cell_id"]))
        if cell["cell_id"] in wing and cell.get("wear") == 0:
            errors.append(_error("surface_dark_wing_clean", cell["cell_id"]))
        if cell.get("landmark") and cell.get("wear") != 0:
            errors.append(_error("surface_landmark_worn", cell["cell_id"]))
        if cell["cell_id"] == spawn_id and cell.get("wear") != 0:
            errors.append(_error("surface_spawn_worn", cell["cell_id"]))
    return errors


def _error(code: str, message: str) -> dict[str, str]:
    return {"rule": RULE, "code": code, "message": message}
