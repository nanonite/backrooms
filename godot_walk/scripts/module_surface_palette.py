"""Build and validate additive surface/palette descriptors for admitted modules."""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from deterministic_json import ROOT, canonical_bytes, sha256_file, write_deterministic

DESCRIPTOR_VERSION = "module-surface-palette-0.1.0"
PROFILE_DIRECTORY = Path("godot_walk/room_catalog/module_profiles")
SURFACE_DESCRIPTOR_DIRECTORY = Path("godot_walk/room_catalog/module_surface_palettes")
SOURCE_PROFILE_GLOB = (
    "godot_walk/source_library/sources/*/rooms/*/module_profile_v1.json"
)
REGISTRY_PATH = Path("godot_walk/room_catalog/material_palettes/palettes-0.3.0.json")
ACOUSTICS_PATH = Path("godot_walk/room_catalog/module_acoustics_v0.2.0.json")
SCHEMA_PATH = Path("godot_walk/room_catalog/module_surface_palette.schema.json")
PROFILE_SCHEMA_PATH = Path("godot_walk/room_catalog/module_profile.schema.json")
REPORT_PATH = Path(
    "godot_walk/room_catalog/module_surface_palette_coverage_v0.1.0.json"
)
TABLE_PATH = Path("godot_walk/room_catalog/module_surface_palette_mapping_v0.1.0.md")
SURFACES = ("wall", "floor", "ceiling", "trim")


def profile_paths(root: Path = ROOT) -> list[Path]:
    paths = {
        path
        for path in (root / PROFILE_DIRECTORY).glob("*.json")
        if not path.name.endswith("_surface_palette_v1.json")
        and not path.name.endswith("-t6-v1.json")
        and not path.name.endswith("-lighting-scale-v1.json")
    }
    paths.update(root.glob(SOURCE_PROFILE_GLOB))
    return sorted(paths)


def descriptor_path(profile_path: Path, root: Path = ROOT) -> Path:
    relative = profile_path.resolve().relative_to(root.resolve())
    if relative.parent == PROFILE_DIRECTORY:
        return (
            root
            / SURFACE_DESCRIPTOR_DIRECTORY
            / (profile_path.stem + "_surface_palette_v1.json")
        )
    return profile_path.with_name("module_surface_palette_v1.json")


def registry_surfaces(root: Path = ROOT) -> dict[str, dict[str, Any]]:
    path = root / REGISTRY_PATH
    stat = path.stat()
    return dict(
        _registry_surfaces_cached(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    )


@lru_cache(maxsize=8)
def _registry_surfaces_cached(
    path_text: str, mtime_ns: int, size: int
) -> tuple[tuple[str, dict[str, Any]], ...]:
    del mtime_ns, size
    registry = json.loads(Path(path_text).read_text(encoding="utf-8"))
    return tuple((record["palette_id"], record) for record in registry["palettes"])


def palette_for(
    module_id: str,
    acoustic: str,
    evidence: list[str],
    registry: dict[str, dict[str, Any]],
) -> str | None:
    for palette_id, record in registry.items():
        if module_id in record["source_module_ids"]:
            return palette_id
    if "dark_carpet" in evidence:
        return None
    if acoustic == "carpet" and "backrooms_yellow" in registry:
        return "backrooms_yellow"
    return None


def surface_entry(
    module_id: str,
    surface: str,
    palette_id: str | None,
    evidence: list[str],
    registry: dict[str, dict[str, Any]],
    profile_path: Path,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_reference = profile_path.resolve().relative_to(root.resolve()).as_posix()
    if palette_id is None:
        acoustic = (
            "carpet" if surface == "floor" and "dark_carpet" in evidence else "unknown"
        )
        label = (
            "dark_carpet" if surface == "floor" and acoustic == "carpet" else "unknown"
        )
        status = "bespoke" if label == "dark_carpet" else "null"
        basis = (
            f"{profile_reference}; {ACOUSTICS_PATH.as_posix()} evidence {evidence}; "
            f"no palettes-0.3.0 surface is evidenced for {surface}"
        )
        return (
            {
                "material_id": f"{module_id}.{label}_{surface}",
                "palette_id": None,
                "acoustic": acoustic,
                "texture_refs": [],
                "provenance": basis,
                "sign": "symbol",
            },
            {
                "basis": basis,
                "status": status,
                "evidence_status": "observed" if label == "dark_carpet" else "proposed",
                "bespoke_reason": f"No supported palettes-0.3.0 mapping for this module's {surface}; retain an explicit {label} slot pending operator review.",
            },
        )
    material = registry[palette_id]["surfaces"][surface]
    clean = material["variants"]["clean"]
    source_modules = registry[palette_id]["source_module_ids"]
    provenance = clean.get("provenance", {})
    provenance_source = provenance.get("from", "")
    provenance_field = provenance_source.rsplit("::", 1)[-1].lower()
    observed = (
        module_id in source_modules
        and provenance.get("sign") == "icon"
        and provenance_source.startswith("res://source_library/")
        and provenance_field.startswith(f"{surface}_")
    )
    relation = (
        f"registry module match and direct {surface} provenance ({provenance_source})"
        if observed
        else "palette registry entry; per-surface assignment is a proposal"
    )
    basis = (
        f"{profile_reference}; {ACOUSTICS_PATH.as_posix()} evidence {evidence}; "
        f"{REGISTRY_PATH.as_posix()} {palette_id}.{surface} via {relation}"
    )
    return (
        {
            "material_id": f"{palette_id}.{surface}",
            "palette_id": palette_id,
            "acoustic": material["acoustic"],
            "texture_refs": [clean["texture"]] if "texture" in clean else [],
            "provenance": basis,
            "sign": clean["provenance"]["sign"],
        },
        {
            "basis": basis,
            "status": "resolved",
            "evidence_status": "observed" if observed else "proposed",
            "bespoke_reason": None,
        },
    )


def build_descriptor(profile_path: Path, root: Path = ROOT) -> dict[str, Any]:
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    acoustics = json.loads((root / ACOUSTICS_PATH).read_text(encoding="utf-8"))[
        "modules"
    ]
    acoustic_record = acoustics.get(f"{profile['module_id']}@{profile['version']}")
    if acoustic_record is None:
        raise ValueError(
            f"no module acoustics record for {profile['module_id']}@{profile['version']}"
        )
    registry = registry_surfaces(root)
    palette_id = palette_for(
        profile["module_id"],
        acoustic_record["acoustic"],
        acoustic_record["evidence"],
        registry,
    )
    relative_profile = profile_path.resolve().relative_to(root.resolve()).as_posix()
    descriptor = {
        "schema_version": 1,
        "descriptor_version": DESCRIPTOR_VERSION,
        "module_id": profile["module_id"],
        "profile_ref": {"path": relative_profile, "sha256": sha256_file(profile_path)},
        "surfaces": {},
        "review": {"operator_review": "pending", "surfaces": {}},
    }
    evidence = acoustic_record["evidence"]
    for surface in SURFACES:
        profile_surface, review_surface = surface_entry(
            profile["module_id"],
            surface,
            palette_id,
            evidence,
            registry,
            profile_path,
            root,
        )
        descriptor["surfaces"][surface] = profile_surface
        descriptor["review"]["surfaces"][surface] = review_surface
    return descriptor


def _descriptor_schemas(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_path = root / SCHEMA_PATH
    profile_path = root / PROFILE_SCHEMA_PATH
    schema_stat = schema_path.stat()
    profile_stat = profile_path.stat()
    return _descriptor_schemas_cached(
        str(schema_path.resolve()),
        schema_stat.st_mtime_ns,
        schema_stat.st_size,
        str(profile_path.resolve()),
        profile_stat.st_mtime_ns,
        profile_stat.st_size,
    )


@lru_cache(maxsize=8)
def _descriptor_schemas_cached(
    schema_path: str,
    schema_mtime: int,
    schema_size: int,
    profile_path: str,
    profile_mtime: int,
    profile_size: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    del schema_mtime, schema_size, profile_mtime, profile_size
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    profile_schema = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    profile_surface_schema = {
        "$schema": profile_schema["$schema"],
        "$defs": profile_schema["$defs"],
        "type": "object",
        "required": ["surfaces"],
        "properties": {"surfaces": {"$ref": "#/$defs/surfaces"}},
        "additionalProperties": False,
    }
    return schema, profile_surface_schema


def validate_descriptor(
    descriptor: dict[str, Any], profile_path: Path, root: Path = ROOT
) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema

        schema, profile_surface_schema = _descriptor_schemas(root)
        jsonschema.validate(descriptor, schema)
        jsonschema.validate(
            {"surfaces": descriptor.get("surfaces")}, profile_surface_schema
        )
    except ImportError:
        errors.append("jsonschema is required to validate surface/palette descriptors")
    except (
        Exception
    ) as exc:  # jsonschema reports several concrete validation exception types
        errors.append(f"schema: {exc.message if hasattr(exc, 'message') else exc}")
    if descriptor.get("module_id") != json.loads(
        profile_path.read_text(encoding="utf-8")
    ).get("module_id"):
        errors.append("module_id does not match the referenced profile")
    reference = descriptor.get("profile_ref", {})
    if (
        reference.get("path")
        != profile_path.resolve().relative_to(root.resolve()).as_posix()
    ):
        errors.append("profile_ref.path does not match its profile")
    if reference.get("sha256") != sha256_file(profile_path):
        errors.append("profile_ref.sha256 does not match its profile")
    registry = registry_surfaces(root)
    surfaces = descriptor.get("surfaces", {})
    review_surfaces = descriptor.get("review", {}).get("surfaces", {})
    for name in SURFACES:
        entry = surfaces.get(name)
        review = review_surfaces.get(name)
        if not isinstance(entry, dict) or not isinstance(review, dict):
            errors.append(f"{name}: unresolved surface")
            continue
        palette_id = entry.get("palette_id")
        status = review.get("status")
        if status in ("null", "bespoke"):
            if palette_id is not None or not review.get("bespoke_reason"):
                errors.append(
                    f"{name}: bespoke surface requires null palette_id and a reason"
                )
        elif status != "resolved":
            errors.append(f"{name}: unsupported resolution status {status!r}")
        elif palette_id not in registry:
            errors.append(f"{name}: unresolved palette_id {palette_id!r}")
        elif name not in registry[palette_id]["surfaces"]:
            errors.append(f"{name}: {palette_id} has no registry surface")
        elif (
            entry.get("acoustic") != registry[palette_id]["surfaces"][name]["acoustic"]
        ):
            errors.append(f"{name}: acoustic does not match {palette_id} registry data")
        if not review.get("basis"):
            errors.append(f"{name}: missing evidence basis")
        if entry.get("provenance") != review.get("basis"):
            errors.append(f"{name}: provenance does not match review basis")
    return errors


def coverage_report(descriptors: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in ("resolved", "null", "bespoke", "unresolved")}
    rows = []
    for descriptor in descriptors:
        surfaces = {}
        for name in SURFACES:
            entry = descriptor.get("surfaces", {}).get(name)
            review = descriptor.get("review", {}).get("surfaces", {}).get(name)
            status = (
                review.get("status", "unresolved")
                if isinstance(review, dict)
                else "unresolved"
            )
            counts[status if status in counts else "unresolved"] += 1
            surfaces[name] = {
                "status": status,
                "palette_id": entry.get("palette_id")
                if isinstance(entry, dict)
                else None,
            }
        rows.append({"module_id": descriptor["module_id"], "surfaces": surfaces})
    return {
        "report_version": "module-surface-palette-coverage-0.1.0",
        "module_count": len(rows),
        "surface_count": len(rows) * len(SURFACES),
        "counts": counts,
        "operator_review": "pending",
        "modules": rows,
    }


def mapping_table(descriptors: list[dict[str, Any]]) -> str:
    lines = [
        "# Module surface and palette mapping (0.1.0)",
        "",
        "Operator mapping review: **pending**. `observed` rows have matching module and direct surface provenance; assignments based on acoustic evidence or palette registry entries without direct surface evidence are `proposed`. `null` rows have no supported palette assignment; `bespoke` rows retain an identified material without a palette match.",
        "",
        "| Module | Surface | Material ID | Palette ID | State | Basis |",
        "|---|---|---|---|---|---|",
    ]
    for descriptor in descriptors:
        for name in SURFACES:
            entry = descriptor["surfaces"][name]
            review = descriptor["review"]["surfaces"][name]
            basis = review["basis"].replace("|", "\\|")
            lines.append(
                f"| `{descriptor['module_id']}` | {name} | `{entry['material_id']}` | "
                f"{entry['palette_id'] or 'null'} | {review['status']} ({review['evidence_status']}) | {basis} |"
            )
    return "\n".join(lines) + "\n"


def run(root: Path, build: bool) -> list[str]:
    errors: list[str] = []
    profiles = profile_paths(root)
    descriptors = []
    for profile_path in profiles:
        descriptor_path_value = descriptor_path(profile_path, root)
        expected = build_descriptor(profile_path, root)
        if build:
            write_deterministic(descriptor_path_value, canonical_bytes(expected))
            descriptor = expected
        elif not descriptor_path_value.is_file():
            errors.append(f"{descriptor_path_value}: descriptor missing")
            continue
        else:
            descriptor = json.loads(descriptor_path_value.read_text(encoding="utf-8"))
            if descriptor != expected:
                errors.append(
                    f"{descriptor_path_value}: differs from derived descriptor; run build"
                )
        errors.extend(
            f"{descriptor_path_value}: {error}"
            for error in validate_descriptor(descriptor, profile_path, root)
        )
        descriptors.append(descriptor)
    if build:
        write_deterministic(
            root / REPORT_PATH, canonical_bytes(coverage_report(descriptors))
        )
        write_deterministic(
            root / TABLE_PATH, mapping_table(descriptors).encode("utf-8")
        )
    elif (root / REPORT_PATH).is_file():
        actual_report = json.loads((root / REPORT_PATH).read_text(encoding="utf-8"))
        if actual_report != coverage_report(descriptors):
            errors.append(f"{REPORT_PATH}: differs from descriptor coverage")
    else:
        errors.append(f"{REPORT_PATH}: coverage report missing")
    table_path = root / TABLE_PATH
    if not build:
        if not table_path.is_file():
            errors.append(f"{TABLE_PATH}: mapping table missing")
        elif table_path.read_text(encoding="utf-8") != mapping_table(descriptors):
            errors.append(f"{TABLE_PATH}: differs from descriptor mappings; run build")
    if len(profiles) != 11:
        errors.append(f"expected 11 admitted module profiles, found {len(profiles)}")
    if any(
        count
        for key, count in coverage_report(descriptors)["counts"].items()
        if key == "unresolved"
    ):
        errors.append("coverage contains unresolved surfaces")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = run(args.root.resolve(), args.command == "build")
    if errors:
        print("\n".join(errors))
        return 1
    print(
        f"validated surface/palette descriptors for {len(profile_paths(args.root.resolve()))} modules"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
