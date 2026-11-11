"""Schema and validator tests for the generation template (issue 214)."""

from __future__ import annotations

import copy
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

import template_validate as tv
from deterministic_json import ROOT, repo_relative, sha256_file
from gmap_validate import validate_document

CATALOG = ROOT / "godot_walk/room_catalog"
SOURCE_LIBRARY = ROOT / "godot_walk/source_library"
MAP_DIR = CATALOG / "generative_maps"
MODULE_PROFILE_FIXTURE = CATALOG / "schema_fixtures/module_profile.fixture.json"
VIDEO_FIXTURE = (
    SOURCE_LIBRARY / "schema_fixtures/source_manifest_v3_video.fixture.json"
)
PICTURE_SET_FIXTURE = (
    SOURCE_LIBRARY / "schema_fixtures/source_manifest_v3_picture_set.fixture.json"
)
PROPOSAL_PATH = ROOT / "docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def path_id(path: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in path) or "<root>"


def resolve_ref(root_schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    reference = node.get("$ref")
    if not isinstance(reference, str):
        return node
    if not reference.startswith("#/"):
        raise AssertionError(f"Unexpected non-local schema reference: {reference}")
    target: Any = root_schema
    for part in reference[2:].split("/"):
        target = target[part.replace("~1", "/").replace("~0", "~")]
    return target


def _required_field_paths(
    root_schema: dict[str, Any],
    schema: dict[str, Any],
    value: Any,
    prefix: tuple[Any, ...] = (),
) -> Iterator[tuple[Any, ...]]:
    schema = resolve_ref(root_schema, schema)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key in value:
                yield prefix + (key,)
        for key, child in schema.get("properties", {}).items():
            if key in value:
                yield from _required_field_paths(
                    root_schema, child, value[key], prefix + (key,)
                )
    for child in schema.get("oneOf", []) + schema.get("anyOf", []):
        yield from _required_field_paths(root_schema, child, value, prefix)
    items = schema.get("items")
    if isinstance(items, dict) and isinstance(value, list):
        for index, item in enumerate(value):
            yield from _required_field_paths(
                root_schema, items, item, prefix + (index,)
            )


def required_field_paths(
    root_schema: dict[str, Any], record: dict[str, Any]
) -> list[tuple[Any, ...]]:
    paths: list[tuple[Any, ...]] = []
    seen: set[tuple[Any, ...]] = set()
    for path in _required_field_paths(root_schema, root_schema, record):
        if path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def remove_path(record: dict[str, Any], path: tuple[Any, ...]) -> dict[str, Any]:
    removed = copy.deepcopy(record)
    parent: Any = removed
    for part in path[:-1]:
        parent = parent[part]
    del parent[path[-1]]
    return removed


def source_schema(name: str) -> dict[str, Any]:
    return load_json(SOURCE_LIBRARY / f"{name}.schema.json")


def module_profile_schema() -> dict[str, Any]:
    return load_json(CATALOG / "module_profile.schema.json")


def template_ref() -> dict[str, str]:
    return {
        "version": "generation-template-0.1.0",
        "path": repo_relative(PROPOSAL_PATH),
        "sha256": sha256_file(PROPOSAL_PATH),
    }


def module_profile_ref() -> dict[str, str]:
    return {
        "path": repo_relative(MODULE_PROFILE_FIXTURE),
        "sha256": sha256_file(MODULE_PROFILE_FIXTURE),
    }


SOURCE_V3_SCHEMA = source_schema("source_manifest_v3")
VIDEO_RECORD = load_json(VIDEO_FIXTURE)
PICTURE_SET_RECORD = load_json(PICTURE_SET_FIXTURE)
MODULE_PROFILE_RECORD = load_json(MODULE_PROFILE_FIXTURE)
VIDEO_REQUIRED_PATHS = required_field_paths(SOURCE_V3_SCHEMA, VIDEO_RECORD)
PICTURE_SET_REQUIRED_PATHS = required_field_paths(
    SOURCE_V3_SCHEMA, PICTURE_SET_RECORD
)
MODULE_PROFILE_REQUIRED_PATHS = required_field_paths(
    module_profile_schema(), MODULE_PROFILE_RECORD
)


# --- schema files ---------------------------------------------------------


@pytest.mark.parametrize(
    "relative_path",
    [
        Path("godot_walk/source_library/source_manifest_v3.schema.json"),
        Path("godot_walk/room_catalog/module_profile.schema.json"),
        Path("godot_walk/room_catalog/module_profile_t6.schema.json"),
        Path("godot_walk/room_catalog/lighting_scale_overlay.schema.json"),
        Path("godot_walk/room_catalog/generative_map_v2.schema.json"),
    ],
)
def test_new_schemas_are_valid_draft_2020_12(relative_path: Path) -> None:
    Draft202012Validator.check_schema(tv.load_schema(relative_path))


def test_source_manifest_v3_keeps_v1_and_v2_schema_files() -> None:
    assert tv.SOURCE_MANIFEST_SCHEMAS[1] != tv.SOURCE_MANIFEST_SCHEMAS[3]
    assert tv.SOURCE_MANIFEST_SCHEMAS[2] != tv.SOURCE_MANIFEST_SCHEMAS[3]


# --- source manifest v3 ---------------------------------------------------


@pytest.mark.parametrize("fixture_path", [VIDEO_FIXTURE, PICTURE_SET_FIXTURE])
def test_source_manifest_v3_fixtures_are_schema_valid(fixture_path: Path) -> None:
    record = load_json(fixture_path)
    assert tv.source_manifest_schema_errors(record) == []


def test_source_manifest_v3_video_fixture_references_exist() -> None:
    record = load_json(VIDEO_FIXTURE)
    assert tv.source_manifest_errors(record) == []


@pytest.mark.parametrize("path", VIDEO_REQUIRED_PATHS, ids=path_id)
def test_source_manifest_v3_video_requires_each_required_field(
    path: tuple[Any, ...]
) -> None:
    broken = remove_path(VIDEO_RECORD, path)
    assert tv.source_manifest_schema_errors(broken), path_id(path)


@pytest.mark.parametrize("path", PICTURE_SET_REQUIRED_PATHS, ids=path_id)
def test_source_manifest_v3_picture_set_requires_each_required_field(
    path: tuple[Any, ...]
) -> None:
    broken = remove_path(PICTURE_SET_RECORD, path)
    assert tv.source_manifest_schema_errors(broken), path_id(path)


def test_source_manifest_v3_content_kinds_are_mutually_exclusive() -> None:
    record = load_json(VIDEO_FIXTURE)
    both = copy.deepcopy(record)
    both["content"]["picture_set"] = load_json(PICTURE_SET_FIXTURE)["content"][
        "picture_set"
    ]
    assert tv.source_manifest_schema_errors(both)
    neither = copy.deepcopy(record)
    neither["content"]["video"] = None
    assert tv.source_manifest_schema_errors(neither)


def test_source_manifest_v3_calibrated_scale_requires_evidence() -> None:
    record = load_json(VIDEO_FIXTURE)
    calibrated = copy.deepcopy(record)
    calibrated["scale"] = {
        "status": "calibrated",
        "method": "known_dimension",
        "anchor": {"kind": "door_height", "value_m": 2.0, "frame_id": "frame_0001"},
        "confidence": 0.8,
        "evidence": [],
    }
    assert tv.source_manifest_schema_errors(calibrated)
    calibrated["scale"]["evidence"] = [
        {
            "path": repo_relative(PROPOSAL_PATH),
            "sha256": sha256_file(PROPOSAL_PATH),
        }
    ]
    assert tv.source_manifest_schema_errors(calibrated) == []


def test_source_manifest_v3_measured_lighting_requires_evidence() -> None:
    record = load_json(VIDEO_FIXTURE)
    measured = copy.deepcopy(record)
    measured["lighting"]["status"] = "measured"
    assert tv.source_manifest_schema_errors(measured)
    measured["lighting"]["evidence"] = [
        {
            "path": repo_relative(PROPOSAL_PATH),
            "sha256": sha256_file(PROPOSAL_PATH),
        }
    ]
    assert tv.source_manifest_schema_errors(measured) == []


def test_source_manifest_v3_audio_is_optional() -> None:
    record = copy.deepcopy(VIDEO_RECORD)
    del record["content"]["audio"]
    assert tv.source_manifest_schema_errors(record) == []


def test_source_manifest_v3_audio_presence_requires_a_reference() -> None:
    record = load_json(VIDEO_FIXTURE)
    present_without_path = copy.deepcopy(record)
    present_without_path["content"]["audio"]["present"] = True
    assert tv.source_manifest_schema_errors(present_without_path)
    absent_with_path = copy.deepcopy(record)
    absent_with_path["content"]["audio"]["path"] = "data/audio/example.wav"
    assert tv.source_manifest_schema_errors(absent_with_path)


def test_source_manifest_v3_pending_review_has_no_decision() -> None:
    record = load_json(VIDEO_FIXTURE)
    decided = copy.deepcopy(record)
    decided["source_review"]["decision"] = "proceed"
    assert tv.source_manifest_schema_errors(decided)


def test_source_manifest_v3_registration_flags_stay_false() -> None:
    record = load_json(VIDEO_FIXTURE)
    accepted = copy.deepcopy(record)
    accepted["registration_accepted"] = True
    assert tv.source_manifest_schema_errors(accepted)
    scaled = copy.deepcopy(record)
    scaled["scale_calibrated"] = True
    assert tv.source_manifest_schema_errors(scaled)


def test_source_manifest_unsupported_version_is_reported() -> None:
    record = load_json(VIDEO_FIXTURE)
    record["schema_version"] = 99
    assert tv.source_manifest_errors(record) == [
        "<root>: unsupported source manifest schema_version 99"
    ]


# --- module profile v1 ----------------------------------------------------


def test_module_profile_fixture_is_valid() -> None:
    record = load_json(MODULE_PROFILE_FIXTURE)
    assert tv.module_profile_errors(record) == []


@pytest.mark.parametrize("path", MODULE_PROFILE_REQUIRED_PATHS, ids=path_id)
def test_module_profile_requires_each_required_field(
    path: tuple[Any, ...]
) -> None:
    broken = remove_path(MODULE_PROFILE_RECORD, path)
    assert tv.module_profile_schema_errors(broken), path_id(path)


def test_module_profile_origin_matches_source_id() -> None:
    record = load_json(MODULE_PROFILE_FIXTURE)
    authored = copy.deepcopy(record)
    authored["origin"] = "authored_kit"
    assert tv.module_profile_schema_errors(authored)
    authored["source_id"] = None
    authored["translation_chain"] = []
    assert tv.module_profile_schema_errors(authored) == []


def test_module_profile_calibrated_scale_requires_anchor_and_evidence() -> None:
    record = load_json(MODULE_PROFILE_FIXTURE)
    calibrated = copy.deepcopy(record)
    calibrated["scale"] = {
        "status": "calibrated",
        "anchor": None,
        "confidence": 0.8,
        "evidence": [],
    }
    assert tv.module_profile_schema_errors(calibrated)
    calibrated["scale"]["anchor"] = {
        "kind": "door_height",
        "value_m": 2.0,
        "frame_id": "frame_0001",
    }
    calibrated["scale"]["evidence"] = [
        {
            "path": repo_relative(PROPOSAL_PATH),
            "sha256": sha256_file(PROPOSAL_PATH),
        }
    ]
    assert tv.module_profile_schema_errors(calibrated) == []


def test_module_profile_rejects_changed_poetics_reference() -> None:
    record = load_json(MODULE_PROFILE_FIXTURE)
    changed = copy.deepcopy(record)
    changed["poetics_ref"]["sha256"] = "0" * 64
    assert tv.module_profile_errors(changed) == [
        (
            "poetics_ref: "
            f"{record['poetics_ref']['path']} no longer matches its sha256"
        )
    ]


def test_module_profile_unsupported_version_is_reported() -> None:
    record = load_json(MODULE_PROFILE_FIXTURE)
    record["schema_version"] = 2
    assert tv.module_profile_errors(record) == [
        "<root>: unsupported module profile schema_version 2"
    ]


# --- generative map schema v2 --------------------------------------------


def committed_map(seed: int = 1) -> dict[str, Any]:
    return load_json(MAP_DIR / f"gmap-{seed}-gmap-0.12.0.json")


def map_v2_base() -> dict[str, Any]:
    document = copy.deepcopy(committed_map())
    document["schema_version"] = 2
    document["template"] = template_ref()
    return document


def test_committed_maps_still_validate_unchanged() -> None:
    paths = tv.generative_map_paths()
    assert paths
    for path in paths:
        record = load_json(path)
        assert validate_document(record) == [], path
        assert tv.generative_map_errors(record) == [], path


def test_committed_source_manifests_still_validate_unchanged() -> None:
    paths = tv.source_manifest_paths()
    assert paths
    for path in paths:
        record = load_json(path)
        assert tv.source_manifest_errors(record) == [], path


def test_repository_report_is_clean() -> None:
    report = tv.validate_repository()
    assert report.valid, report.errors
    assert report.source_manifests == len(tv.source_manifest_paths())
    assert report.generative_maps == len(tv.generative_map_paths())


def test_generative_map_v2_new_fields_are_optional() -> None:
    document = map_v2_base()
    assert tv.generative_map_errors(document) == []


def test_generative_map_v2_accepts_policy_and_profile_additions() -> None:
    document = map_v2_base()
    cell = document["cells"][0]
    cell["module_profile"] = module_profile_ref()
    cell["volume"] = {
        "nominal_m3": 994.24,
        "measured_m3": None,
        "source": "module_profile",
    }
    cell["mood"] = {"tension": 0.4, "tags": ["low_tension"]}
    cell["doors"] = [
        {
            "port_id": "c00:e",
            "state": "closed",
            "lock": {
                "lock_id": None,
                "unlock_condition": None,
                "locked_by": None,
            },
            "reroll": {
                "eligible": False,
                "stream": "door-reroll:gmap-0.13.0",
                "draw_index": None,
                "max_rerolls": 0,
                "last_reroll_id": None,
            },
            "follower_visibility": "visible",
            "breadcrumb": {
                "marker_id": None,
                "kind": None,
                "persistent": False,
            },
        }
    ]
    cell["mutation"] = {
        "eligible": False,
        "classes": [],
        "follower_visibility": "untouched",
        "policy": "none",
        "last_change_id": None,
    }
    document["edges"][0]["door_id"] = "c00:e"
    assert tv.generative_map_errors(document) == []


def test_generative_map_v2_rejects_unknown_door_state() -> None:
    document = map_v2_base()
    cell = document["cells"][0]
    cell["doors"] = [
        {
            "port_id": "c00:e",
            "state": "ajar",
            "lock": {
                "lock_id": None,
                "unlock_condition": None,
                "locked_by": None,
            },
            "reroll": {
                "eligible": False,
                "stream": "door-reroll:gmap-0.13.0",
                "draw_index": None,
                "max_rerolls": 0,
                "last_reroll_id": None,
            },
            "follower_visibility": "visible",
            "breadcrumb": {
                "marker_id": None,
                "kind": None,
                "persistent": False,
            },
        }
    ]
    assert tv.generative_map_schema_errors(document)


def test_generative_map_v2_rejects_changed_module_profile_reference() -> None:
    document = map_v2_base()
    document["cells"][0]["module_profile"] = {
        "path": repo_relative(MODULE_PROFILE_FIXTURE),
        "sha256": "0" * 64,
    }
    assert tv.generative_map_errors(document) == [
        (
            "cells[c00].module_profile: "
            f"{repo_relative(MODULE_PROFILE_FIXTURE)} no longer matches its sha256"
        )
    ]


def test_generative_map_v2_still_requires_v1_fields() -> None:
    document = map_v2_base()
    del document["cells"]
    assert tv.generative_map_schema_errors(document)


def test_generative_map_unsupported_version_is_reported() -> None:
    document = map_v2_base()
    document["schema_version"] = 3
    assert tv.generative_map_errors(document) == [
        "<root>: unsupported generative map schema_version 3"
    ]
