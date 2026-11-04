"""Deterministic growth and draft-level version rules for generative maps."""

from __future__ import annotations

import hashlib
import random

from gmap_assign import add_voids, assign_roles, assign_tiers
from gmap_build import (
    CELL_RANGE,
    DEFAULT_DEGENERATE_MAX,
    GENERATOR_VERSION_V61,
    MARGIN_VERSIONS,
    MAX_ATTEMPTS,
    MAX_SITE_LAYOUT_VARIANTS,
    MODULE_VERSIONS,
    STAGE2_VERSIONS,
    STREAM_STRIDE,
    layout_version,
)
from gmap_degenerate import assign_degenerate, degenerate_rng
from gmap_geometry import DOORWAY_HALF_M, STANDARD_MARGIN_M
from gmap_grow import Draft, GenerationError, RetryAttempt, grow
from gmap_library import Library
from gmap_modules import OVERHANG_MARGIN_M, attach_modules


def attempt_rng(seed: int, attempt: int) -> random.Random:
    """Seed stream `attempt` of this seed; stream 0 is the seed itself."""
    return random.Random(seed + attempt * STREAM_STRIDE)


def site_layout_rng(seed: int, attempt: int, layout_variant: int) -> random.Random:
    digest = hashlib.sha256(
        f"{seed}:{attempt}:{layout_variant}:gmap-layout-0.6.1".encode()
    ).digest()
    return random.Random(int.from_bytes(digest, "big"))


def attempt_once(
    rng: random.Random,
    cells: int,
    classes: list[tuple[int, int]],
    version: str,
    library: Library | None,
    site_rng: random.Random | None = None,
    diagonal_budget: int = 0,
) -> Draft:
    v2 = version in MARGIN_VERSIONS
    draft = grow(
        rng,
        cells,
        centred=v2,
        margin=STANDARD_MARGIN_M if v2 else DOORWAY_HALF_M,
        site_rng=site_rng if version == GENERATOR_VERSION_V61 else None,
        site_budget=diagonal_budget,
    )
    draft.diagonal_budget = diagonal_budget
    assign_tiers(rng, draft, classes)
    assign_roles(draft)
    if not any(draft.degree(cell.cell_id) >= 3 for cell in draft.walkable()):
        raise RetryAttempt("branch_required: no cell of degree >= 3")
    if version in MODULE_VERSIONS and library is not None:
        attach_modules(
            rng,
            draft,
            library,
            OVERHANG_MARGIN_M if version in STAGE2_VERSIONS else 0.0,
        )
    add_voids(rng, draft)
    return draft


def generate_draft(
    seed: int,
    cells: int,
    classes: list[tuple[int, int]],
    version: str,
    degenerate_max: int = DEFAULT_DEGENERATE_MAX,
    library: Library | None = None,
) -> tuple[Draft, int, int]:
    """Return a valid draft, the successful attempt number, and degenerate count."""
    if not CELL_RANGE[0] <= cells <= CELL_RANGE[1]:
        raise GenerationError(
            f"--cells must be within {CELL_RANGE[0]}..{CELL_RANGE[1]}"
        )
    for attempt in range(MAX_ATTEMPTS):
        if version == GENERATOR_VERSION_V61:
            draft_result = _generate_v61(
                seed, attempt, cells, classes, version, degenerate_max, library
            )
            if draft_result is not None:
                return draft_result
            continue
        try:
            draft = attempt_once(
                attempt_rng(seed, attempt), cells, classes, version, library
            )
            used = _degenerate_count(seed, attempt, draft, degenerate_max, version)
            return draft, attempt, used
        except RetryAttempt:
            continue
    raise GenerationError(
        f"no valid map for seed {seed} within {MAX_ATTEMPTS} attempts"
    )


def _generate_v61(
    seed: int,
    attempt: int,
    cells: int,
    classes: list[tuple[int, int]],
    version: str,
    degenerate_max: int,
    library: Library | None,
) -> tuple[Draft, int, int] | None:
    from gmap_diagonal import rng_for, sampled_budget
    from gmap_diagonal_sites import rng_for as site_rng_for

    budget = sampled_budget(rng_for(seed, attempt))
    best: tuple[Draft, int, int, int] | None = None
    variants = 1 if budget == 0 else MAX_SITE_LAYOUT_VARIANTS
    for variant in range(variants):
        try:
            layout_rng = (
                attempt_rng(seed, attempt)
                if variant == 0
                else site_layout_rng(seed, attempt, variant)
            )
            draft = attempt_once(
                layout_rng,
                cells,
                classes,
                version,
                library,
                site_rng_for(seed, attempt, variant),
                budget,
            )
            draft.layout_variant = variant
            used = _degenerate_count(
                seed if variant == 0 else seed + variant * STREAM_STRIDE,
                attempt,
                draft,
                degenerate_max,
                version,
            )
        except RetryAttempt:
            continue
        result = (draft, attempt, used, variant)
        if best is None or _site_score(result) > _site_score(best):
            best = result
        if len(draft.reserved_diagonal_zones) >= budget:
            return draft, attempt, used
    if best is None:
        return None
    best[0].layout_variant = best[3]
    return best[0], best[1], best[2]


def _site_score(result: tuple[Draft, int, int, int]) -> tuple[int, int]:
    return len(result[0].reserved_diagonal_zones), -result[3]


def _degenerate_count(
    seed: int, attempt: int, draft: Draft, maximum: int, version: str
) -> int:
    if version not in MARGIN_VERSIONS:
        return 0
    return assign_degenerate(
        degenerate_rng(seed, attempt, layout_version(version)), draft, maximum
    )
