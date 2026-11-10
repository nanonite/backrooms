"""Backfilled module profiles for the 11 admitted modules (issue 215)."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backfill_module_profiles as backfill
import template_validate as tv
from deterministic_json import ROOT, sha256_file
from module_profile import PLACEHOLDER_CIRCULATION_ROLE, PROFILE_VERSION, SURFACES

MODULE_ACOUSTICS = ROOT / "godot_walk/room_catalog/module_acoustics.json"
TEMPLATE = ROOT / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md"
SNAPSHOT_DIR = ROOT / "godot_walk/room_catalog/catalog_snapshots"
SOURCE_ID = re.compile(r"^(video|picture-set)-[0-9a-f]{16}$")

EXPECTED = backfill.expected_profiles()
PROFILE_PATHS = [item.path for item in EXPECTED]
PROFILES = {item.module_id: json.loads(item.path.read_text(encoding="utf-8")) for item in EXPECTED}
ACOUSTICS = json.loads(MODULE_ACOUSTICS.read_text(encoding="utf-8"))["modules"]


def profile(module_id: str) -> dict[str, Any]:
    return PROFILES[module_id]


def accepted_flags(value: Any, path: tuple[str, ...] = ()) -> list[tuple[str, Any]]:
    """Every key that looks like an acceptance flag, wherever it appears."""
    flags: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = path + (key,)
            if "accept" in key.lower() or "approv" in key.lower():
                flags.append((".".join(child_path), child))
            flags.extend(accepted_flags(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flags.extend(accepted_flags(child, path + (str(index),)))
    return flags


# --- inventory ------------------------------------------------------------


def test_exactly_eleven_admitted_modules_have_profiles() -> None:
    assert len(EXPECTED) == backfill.ADMITTED_MODULE_COUNT == 11
    assert len({item.module_id for item in EXPECTED}) == 11


def test_committed_profile_paths_are_exactly_the_expected_sidecars() -> None:
    assert set(tv.module_profile_paths()) == set(PROFILE_PATHS)
    assert len(tv.module_profile_paths()) == 11


def test_profile_locations_never_overwrite_frozen_records() -> None:
    for path in PROFILE_PATHS:
        relative = path.relative_to(ROOT).as_posix()
        assert relative.startswith(backfill.PROFILE_DIR.as_posix() + "/") or (
            relative.endswith("/" + backfill.SOURCE_PROFILE_NAME)
            and relative.startswith(backfill.SOURCE_ROOM_PREFIX)
        ), relative


# --- schema and frozen references ----------------------------------------


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_profile_validates_with_every_frozen_reference(module_id: str) -> None:
    assert tv.module_profile_errors(profile(module_id)) == []


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_profile_keeps_its_poetics_identity_and_hash(module_id: str) -> None:
    record = profile(module_id)
    reference = record["poetics_ref"]
    poetics_path = ROOT / reference["path"]
    assert poetics_path.is_file()
    assert sha256_file(poetics_path) == reference["sha256"]
    poetics = json.loads(poetics_path.read_text(encoding="utf-8"))
    assert poetics["metadata_status"] == "operator_accepted"
    assert (record["module_id"], record["version"]) == (
        poetics["module_id"],
        poetics["version"],
    )
    assert record["catalog_snapshot_sha256"] == poetics["catalog_snapshot_sha256"]


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_profile_references_a_committed_catalog_snapshot(module_id: str) -> None:
    digest = profile(module_id)["catalog_snapshot_sha256"]
    snapshots = {
        sha256_file(path) for path in sorted(SNAPSHOT_DIR.glob("*.json"))
    }
    assert digest in snapshots


def test_every_profile_references_the_approved_template() -> None:
    expected = {
        "version": "generation-template-0.1.0",
        "path": "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md",
        "sha256": sha256_file(TEMPLATE),
    }
    for module_id in PROFILES:
        assert profile(module_id)["template_ref"] == expected


# --- mechanical derivation ------------------------------------------------


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_mechanical_fields_still_match_the_frozen_inputs(module_id: str) -> None:
    actual = profile(module_id)
    expected = next(item.record for item in EXPECTED if item.module_id == module_id)
    assert backfill.mechanical_projection(actual) == backfill.mechanical_projection(
        expected
    )


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_surface_and_acoustic_tags_match_module_acoustics(module_id: str) -> None:
    tag = ACOUSTICS[f"{module_id}@1"]["acoustic"]
    record = profile(module_id)
    assert record["acoustics"]["tag"] == tag
    assert record["acoustics"]["status"] == "tag_only"
    for surface in SURFACES:
        assert record["surfaces"][surface]["acoustic"] == tag


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_origins_and_translation_chains_match_the_poetics(module_id: str) -> None:
    record = profile(module_id)
    poetics = json.loads(
        (ROOT / record["poetics_ref"]["path"]).read_text(encoding="utf-8")
    )
    if record["origin"] == "authored_kit":
        assert record["source_id"] is None
        assert record["translation_chain"] == []
        return
    assert SOURCE_ID.fullmatch(record["source_id"])
    assert record["translation_chain"]
    assert record["translation_chain"][0]["stage"] == "direct_frame"
    assert record["translation_chain"] == poetics["translation_chain"]


# --- unreviewed placeholders ---------------------------------------------


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_semantic_fields_are_unreviewed_placeholders(module_id: str) -> None:
    record = profile(module_id)
    assert record["profile_version"] == PROFILE_VERSION == "module-profile-0.1.0"
    assert record["roles"]["map_role"] == record["roles"]["form_role"]
    assert record["roles"]["semantic_tags"] == []
    assert record["roles"]["sightline_tags"] == []
    assert record["roles"]["circulation_role"] == PLACEHOLDER_CIRCULATION_ROLE
    for field in ("tension", "dread", "curiosity", "safety", "anomaly"):
        assert record["mood"][field] is None
    assert record["mood"]["tags"] == []
    assert record["mood"]["evidence"] == []
    assert record["lighting"]["status"] == "unknown"
    assert record["lighting"]["tier"] is None
    assert record["lighting"]["evidence"] == []
    assert record["scale"]["status"] == "uncalibrated"
    assert record["scale"]["anchor"] is None
    assert record["scale"]["evidence"] == []
    assert record["acoustics"]["absorption"]["status"] == "unknown"
    assert record["acoustics"]["absorption"]["confidence"] == 0.0
    assert record["acoustics"]["probe"] == {
        "probe_version": None,
        "mean_distance_m": None,
        "max_distance_m": None,
        "ceiling_height_m": None,
        "openness": None,
        "room_size": None,
        "damping": None,
        "wet": None,
        "predelay_msec": None,
        "sample_points": [],
        "evidence": [],
    }
    for surface in SURFACES:
        assert record["surfaces"][surface]["palette_id"] is None
    assert record["runtime"]["mutation_eligible"] is False
    assert record["runtime"]["mutation_classes"] == []
    assert record["eligibility"]["catalog_layout_eligible"] in (None, False)


@pytest.mark.parametrize("module_id", sorted(PROFILES), ids=sorted(PROFILES))
def test_no_accepted_or_approved_flag_is_set(module_id: str) -> None:
    assert accepted_flags(profile(module_id)) == []


# --- backfill script ------------------------------------------------------


def test_backfill_check_is_clean() -> None:
    assert backfill.check() == []


def test_backfill_build_is_idempotent() -> None:
    results = backfill.build()
    assert len(results) == 11
    assert {result["status"] for result in results} == {"unchanged"}


def test_backfill_check_detects_changed_mechanical_content() -> None:
    record = copy.deepcopy(profile(min(PROFILES)))
    changed = copy.deepcopy(record)
    changed["shape"]["area_m2"] += 1.0
    assert backfill._projection_errors(
        backfill.mechanical_projection(changed),
        backfill.mechanical_projection(record),
    )
