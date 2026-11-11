"""Read-only schema and reference validation for generation-template records.

The template schemas are frozen by version:

* source manifests: v1, v2 and v3 keep their own schema files;
* module profiles: schema v1 in ``module_profile.schema.json``;
* module profile T6 overlays: schema v1 in ``module_profile_t6.schema.json``;
* generative maps: schema v1 and the optional additions in schema v2.

Nothing here derives, writes or rewrites a record. Existing source manifests and
committed maps stay valid under their original schema version.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, sha256_file

SOURCE_MANIFEST_SCHEMAS = {
    1: Path("godot_walk/source_library/source_manifest.schema.json"),
    2: Path("godot_walk/source_library/source_manifest_v2.schema.json"),
    3: Path("godot_walk/source_library/source_manifest_v3.schema.json"),
}
MODULE_PROFILE_SCHEMA = Path(
    "godot_walk/room_catalog/module_profile.schema.json"
)
MODULE_PROFILE_T6_SCHEMA = Path(
    "godot_walk/room_catalog/module_profile_t6.schema.json"
)
GENERATIVE_MAP_SCHEMAS = {
    1: Path("godot_walk/room_catalog/generative_map.schema.json"),
    2: Path("godot_walk/room_catalog/generative_map_v2.schema.json"),
}
MODULE_PROFILE_DIR = Path("godot_walk/room_catalog/module_profiles")
SOURCE_PROFILE_GLOB = (
    "godot_walk/source_library/sources/*/rooms/*/module_profile_v1.json"
)
T6_PROFILE_DIR = Path("godot_walk/room_catalog/module_profiles")
T6_SOURCE_PROFILE_GLOB = (
    "godot_walk/source_library/sources/*/rooms/*/module_profile_t6_v1.json"
)
CATALOG_SNAPSHOT_DIR = Path("godot_walk/room_catalog/catalog_snapshots")


class TemplateValidationError(ValueError):
    """A template schema or record cannot be read or validated."""


@dataclass(frozen=True)
class ValidationReport:
    """Counts and errors from one repository validation pass."""

    source_manifests: int
    module_profiles: int
    generative_maps: int
    errors: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "source_manifests": self.source_manifests,
            "module_profiles": self.module_profiles,
            "generative_maps": self.generative_maps,
            "errors": list(self.errors),
        }


def load_schema(relative_path: Path, root: Path = ROOT) -> dict[str, Any]:
    path = root / relative_path
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TemplateValidationError(
            f"Cannot read schema {relative_path}: {error}"
        ) from error
    if not isinstance(schema, dict):
        raise TemplateValidationError(f"Schema is not a JSON object: {relative_path}")
    Draft202012Validator.check_schema(schema)
    return schema


def schema_errors(record: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(schema)
    ordered = sorted(
        validator.iter_errors(record),
        key=lambda error: [str(part) for part in error.absolute_path],
    )
    return [
        (
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
        )
        for error in ordered
    ]


def _unsupported(version: Any, label: str) -> list[str]:
    return [f"<root>: unsupported {label} schema_version {version!r}"]


def source_manifest_schema_errors(
    record: dict[str, Any], root: Path = ROOT
) -> list[str]:
    version = record.get("schema_version")
    relative_path = (
        SOURCE_MANIFEST_SCHEMAS.get(version) if isinstance(version, int) else None
    )
    if relative_path is None:
        return _unsupported(version, "source manifest")
    return schema_errors(record, load_schema(relative_path, root))


def source_manifest_errors(record: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Schema errors plus the v3 content and evidence references."""
    errors = source_manifest_schema_errors(record, root)
    if errors or record.get("schema_version") != 3:
        return errors
    return errors + _source_content_errors(record, root) + _evidence_errors(
        record.get("scale", {}).get("evidence", []), root, "scale.evidence"
    ) + _evidence_errors(
        record.get("lighting", {}).get("evidence", []), root, "lighting.evidence"
    )


def _source_content_errors(record: dict[str, Any], root: Path) -> list[str]:
    content = record["content"]
    errors: list[str] = []
    video = content.get("video")
    if isinstance(video, dict):
        errors += _reference_errors(
            {"path": video["path"], "sha256": video["sha256"]},
            root,
            "content.video",
        )
    for index, picture in enumerate(content.get("picture_set") or []):
        errors += _reference_errors(picture, root, f"content.picture_set[{index}]")
    audio = content.get("audio")
    if isinstance(audio, dict) and audio.get("present"):
        errors += _reference_errors(
            {"path": audio["path"], "sha256": audio["sha256"]},
            root,
            "content.audio",
        )
    for index, frame in enumerate(record.get("frame_references", [])):
        errors += _reference_errors(frame, root, f"frame_references[{index}]")
    for index, artifact in enumerate(record.get("historical_artifacts", [])):
        errors += _reference_errors(artifact, root, f"historical_artifacts[{index}]")
    for index, room in enumerate(record.get("room_adaptations", [])):
        errors += _room_reference_errors(room, root, f"room_adaptations[{index}]")
    for index, attempt in enumerate(
        record.get("hunyuan", {}).get("historical_attempts", [])
    ):
        errors += _evidence_errors(
            attempt.get("evidence", []),
            root,
            f"hunyuan.historical_attempts[{index}].evidence",
        )
    return errors


def _room_reference_errors(
    room: dict[str, Any], root: Path, label: str
) -> list[str]:
    errors = _reference_errors(
        {"path": room["adaptation_path"], "sha256": room["adaptation_sha256"]},
        root,
        f"{label}.adaptation",
    )
    errors += _reference_errors(
        {"path": room["decision_path"], "sha256": room["decision_sha256"]},
        root,
        f"{label}.decision",
    )
    for path_key, hash_key in (
        ("scene_path", "scene_sha256"),
        ("catalog_snapshot_path", "catalog_snapshot_sha256"),
    ):
        if path_key in room and hash_key in room:
            errors += _reference_errors(
                {"path": room[path_key], "sha256": room[hash_key]},
                root,
                f"{label}.{path_key.removesuffix('_path')}",
            )
    return errors


def module_profile_schema_errors(
    record: dict[str, Any], root: Path = ROOT
) -> list[str]:
    if record.get("schema_version") != 1:
        return _unsupported(record.get("schema_version"), "module profile")
    return schema_errors(record, load_schema(MODULE_PROFILE_SCHEMA, root))


def module_profile_errors(record: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Schema errors plus every frozen record the profile references."""
    errors = module_profile_schema_errors(record, root)
    if errors:
        return errors
    errors += _reference_errors(record["poetics_ref"], root, "poetics_ref")
    errors += _reference_errors(record["template_ref"], root, "template_ref")
    errors += _catalog_snapshot_errors(record["catalog_snapshot_sha256"], root)
    errors += _evidence_errors(
        record["acoustics"]["probe"]["evidence"], root, "acoustics.probe.evidence"
    )
    for key in ("lighting", "scale", "mood"):
        errors += _evidence_errors(record[key]["evidence"], root, f"{key}.evidence")
    return errors


def module_profile_t6_errors(
    record: dict[str, Any], root: Path = ROOT
) -> list[str]:
    """Validate an editable T6 overlay and its frozen base/evidence references."""
    errors = schema_errors(record, load_schema(MODULE_PROFILE_T6_SCHEMA, root))
    if errors:
        return errors
    errors += _reference_errors(record["base_profile"], root, "base_profile")
    errors += _reference_errors(record["template_ref"], root, "template_ref")
    for index, evidence in enumerate(record["mood"]["evidence"]):
        errors += _reference_errors(evidence, root, f"mood.evidence[{index}]")
    if errors:
        return errors
    base_path = (root / record["base_profile"]["path"]).resolve()
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"base_profile: cannot read referenced profile: {error}"]
    if record["module_id"] != base.get("module_id"):
        errors.append("module_id does not match base profile")
    if len(record["exits"]) != len(base.get("exits", [])):
        errors.append("exits must describe exactly the recorded base profile sockets")
    for index, (exit_record, base_exit) in enumerate(
        zip(record["exits"], base.get("exits", []))
    ):
        for field in (
            "socket_id",
            "kind",
            "compatibility_type",
            "width_m",
            "elevation_m",
            "tested_pair_ids",
        ):
            if exit_record[field] != base_exit[field]:
                errors.append(f"exits[{index}].{field} differs from recorded socket")
    return errors


def generative_map_schema_errors(
    record: dict[str, Any], root: Path = ROOT
) -> list[str]:
    version = record.get("schema_version")
    relative_path = (
        GENERATIVE_MAP_SCHEMAS.get(version) if isinstance(version, int) else None
    )
    if relative_path is None:
        return _unsupported(version, "generative map")
    return schema_errors(record, load_schema(relative_path, root))


def generative_map_errors(record: dict[str, Any], root: Path = ROOT) -> list[str]:
    """Schema errors plus the schema-v2 template and module-profile references."""
    errors = generative_map_schema_errors(record, root)
    if errors or record.get("schema_version") != 2:
        return errors
    if "template" in record:
        errors += _reference_errors(record["template"], root, "template")
    for cell in record["cells"]:
        reference = cell.get("module_profile")
        if isinstance(reference, dict):
            errors += _reference_errors(
                reference, root, f"cells[{cell['cell_id']}].module_profile"
            )
    return errors


def _reference_errors(
    reference: dict[str, Any], root: Path, label: str
) -> list[str]:
    path_text, digest = reference.get("path"), reference.get("sha256")
    if not isinstance(path_text, str) or not isinstance(digest, str):
        return [f"{label}: reference lacks a path or sha256"]
    candidate = (root / path_text).resolve()
    if not candidate.is_relative_to(root.resolve()):
        return [f"{label}: {path_text} escapes the repository"]
    if not candidate.is_file():
        return [f"{label}: {path_text} is missing"]
    if sha256_file(candidate) != digest:
        return [f"{label}: {path_text} no longer matches its sha256"]
    return []


def _evidence_errors(
    evidence: Any, root: Path, label: str
) -> list[str]:
    if not isinstance(evidence, list):
        return [f"{label}: evidence must be an array"]
    errors: list[str] = []
    for index, reference in enumerate(evidence):
        if not isinstance(reference, dict):
            errors.append(f"{label}[{index}]: evidence entry must be an object")
            continue
        errors += _reference_errors(reference, root, f"{label}[{index}]")
    return errors


def _catalog_snapshot_errors(digest: str, root: Path) -> list[str]:
    directory = root / CATALOG_SNAPSHOT_DIR
    if not directory.is_dir():
        return [f"catalog_snapshot_sha256: {CATALOG_SNAPSHOT_DIR} is missing"]
    for candidate in sorted(directory.glob("*.json")):
        if sha256_file(candidate) == digest:
            return []
    return [f"catalog_snapshot_sha256: no catalog snapshot matches {digest}"]


def source_manifest_paths(root: Path = ROOT) -> list[Path]:
    sources = root / "godot_walk/source_library/sources"
    return sorted(sources.glob("*/source_manifest*.json"))


def module_profile_paths(root: Path = ROOT) -> list[Path]:
    paths = {
        path
        for path in (root / MODULE_PROFILE_DIR).glob("*.json")
        if not path.name.endswith("-t6-v1.json")
    }
    paths.update(root.glob(SOURCE_PROFILE_GLOB))
    return sorted(paths)


def module_profile_t6_paths(root: Path = ROOT) -> list[Path]:
    paths = set((root / T6_PROFILE_DIR).glob("*-t6-v1.json"))
    paths.update(root.glob(T6_SOURCE_PROFILE_GLOB))
    return sorted(paths)


def generative_map_paths(root: Path = ROOT) -> list[Path]:
    maps = root / "godot_walk/room_catalog/generative_maps"
    return sorted(
        path for path in maps.glob("*.json") if ".fill." not in path.name
    )


def validate_repository(root: Path = ROOT) -> ValidationReport:
    """Schema-check every committed source manifest, profile and map."""
    manifest_paths = [
        path for path in source_manifest_paths(root) if path.is_file()
    ]
    profile_paths = [path for path in module_profile_paths(root) if path.is_file()]
    t6_profile_paths = [
        path for path in module_profile_t6_paths(root) if path.is_file()
    ]
    map_paths = [path for path in generative_map_paths(root) if path.is_file()]
    errors: list[str] = []
    errors += _validate_files(
        manifest_paths, source_manifest_errors, root, "source manifest"
    )
    errors += _validate_files(
        profile_paths, module_profile_errors, root, "module profile"
    )
    errors += _validate_files(
        t6_profile_paths, module_profile_t6_errors, root, "module profile T6"
    )
    errors += _validate_files(map_paths, generative_map_errors, root, "generative map")
    return ValidationReport(
        source_manifests=len(manifest_paths),
        module_profiles=len(profile_paths) + len(t6_profile_paths),
        generative_maps=len(map_paths),
        errors=tuple(errors),
    )


def _validate_files(
    paths: list[Path],
    validator: Callable[[dict[str, Any], Path], list[str]],
    root: Path,
    label: str,
) -> list[str]:
    errors: list[str] = []
    for path in paths:
        relative = _relative(path, root)
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{relative}: cannot read {label}: {error}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{relative}: {label} must be a JSON object")
            continue
        try:
            problems = validator(record, root)
        except TemplateValidationError as error:
            errors.append(f"{relative}: {error}")
            continue
        errors.extend(f"{relative}: {problem}" for problem in problems)
    return errors


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root (default: this checkout)",
    )
    arguments = parser.parse_args(argv)
    report = validate_repository(arguments.root.resolve())
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
