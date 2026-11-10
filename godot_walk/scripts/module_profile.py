"""Build a module_profile_v1 sidecar from an accepted module_poetics record.

The profile is a derived projection. It never edits the accepted poetics, the
module scene, the catalog or a catalog snapshot. Source videos and picture sets
use the same builder; only the direct-source translation stage differs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deterministic_json import canonical_bytes, sha256_bytes, write_new
from module_acoustics import derive_acoustic
from video_source_library import (
    PICTURE_SET_SOURCE_KIND,
    ROOT,
    SourceLibraryError,
    sha256_file,
    source_kind_for_id,
)

PROFILE_VERSION = "module-profile-0.1.0"
TEMPLATE_VERSION = "generation-template-0.1.0"
TEMPLATE_PATH = Path("docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md")
SURFACES = ("wall", "floor", "ceiling", "trim")
PLACEHOLDER_CIRCULATION_ROLE = "branch"
SURFACE_SIGN = {"wall": "icon", "floor": "icon", "ceiling": "symbol", "trim": "symbol"}


def template_ref(root: Path = ROOT) -> dict[str, str]:
    path = root / TEMPLATE_PATH
    if not path.is_file():
        raise SourceLibraryError(f"Template document is missing: {TEMPLATE_PATH}")
    return {
        "version": TEMPLATE_VERSION,
        "path": TEMPLATE_PATH.as_posix(),
        "sha256": sha256_file(path),
    }


def build_profile(
    poetics: dict[str, Any],
    poetics_path: str,
    entry: dict[str, Any],
    catalog_snapshot_sha256: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Return a schema-v1 module profile for one operator-accepted poetics record."""
    if poetics.get("metadata_status") != "operator_accepted":
        raise SourceLibraryError("A module profile needs an accepted poetics record")
    if poetics.get("catalog_snapshot_sha256") != catalog_snapshot_sha256:
        raise SourceLibraryError("Profile catalog snapshot differs from poetics")
    source_id = poetics.get("source_id")
    origin = _origin(source_id)
    poetics_block = poetics.get("poetics") or {}
    ports = poetics.get("ports") or {}
    exits = _exits(ports, entry, poetics_path)
    tag, _evidence = derive_acoustic(poetics_block.get("style_tags", []))
    return {
        "schema_version": 1,
        "profile_version": PROFILE_VERSION,
        "module_id": poetics["module_id"],
        "version": poetics["version"],
        "source_id": source_id,
        "origin": origin,
        "poetics_ref": {"path": poetics_path, "sha256": sha256_file(root / poetics_path)},
        "catalog_snapshot_sha256": catalog_snapshot_sha256,
        "template_ref": template_ref(root),
        "shape": _shape(poetics["shape"]),
        "exits": exits,
        "roles": _roles(poetics_block),
        "surfaces": _surfaces(tag, poetics_path),
        "acoustics": _acoustics(tag),
        "lighting": _lighting(poetics.get("layers") or {}),
        "scale": {
            "status": "uncalibrated",
            "anchor": None,
            "confidence": 0.0,
            "evidence": [],
        },
        "mood": {
            "tension": None,
            "dread": None,
            "curiosity": None,
            "safety": None,
            "anomaly": None,
            "tags": [],
            "evidence": [],
        },
        "runtime": {
            "mutation_eligible": False,
            "mutation_classes": [],
            "follower_visibility": "visible",
            "breadcrumb_policy": "none",
        },
        "translation_chain": _translation_chain(
            poetics.get("translation_chain", []), origin
        ),
        "eligibility": {
            "layout_eligible_derived": bool(ports.get("tested_sockets")),
            "catalog_layout_eligible": entry.get("catalog_layout_eligible"),
        },
    }


def _origin(source_id: Any) -> str:
    if source_id is None:
        return "authored_kit"
    if not isinstance(source_id, str):
        raise SourceLibraryError("Poetics source ID is not safe")
    if source_kind_for_id(source_id) == PICTURE_SET_SOURCE_KIND:
        return "source_picture_set"
    return "source_video"


def _shape(source: dict[str, Any]) -> dict[str, Any]:
    ceiling = source.get("ceiling_height_m")
    area = source["area_m2"]
    shape = {
        "footprint_xz": source["footprint_xz"],
        "bbox_xz": source["bbox_xz"],
        "area_m2": area,
        "ceiling_min_m": ceiling,
        "ceiling_max_m": ceiling,
        "ceiling_height_m": ceiling,
        "ceiling_kind": "unknown",
        "volume_nominal_m3": (
            round(area * ceiling, 6) if isinstance(ceiling, (int, float)) else None
        ),
        "volume_measured_m3": None,
        "volume_source": "envelope_area_x_max_ceiling",
    }
    for key in (
        "vertex_count",
        "aspect",
        "convexity",
        "rectilinear",
        "primitive",
        "shape_stage",
        "symmetry",
    ):
        if key in source:
            shape[key] = source[key]
    return shape


def _exits(
    ports: dict[str, Any], entry: dict[str, Any], poetics_path: str
) -> list[dict[str, Any]]:
    sockets = {socket["id"]: socket for socket in entry.get("sockets", [])}
    exits = []
    for tested in ports.get("tested_sockets", []):
        socket = sockets.get(tested["socket_id"], {})
        exits.append(
            _exit_record(
                tested["socket_id"],
                "tested",
                socket,
                [pair["pair_id"] for pair in tested["pairs"]],
                poetics_path,
            )
        )
    for socket_id in ports.get("untested_sockets", []):
        exits.append(
            _exit_record(
                socket_id,
                "untested",
                sockets.get(socket_id, {}),
                [],
                poetics_path,
            )
        )
    return exits


def _exit_record(
    socket_id: str,
    kind: str,
    socket: dict[str, Any],
    tested_pair_ids: list[str],
    poetics_path: str,
) -> dict[str, Any]:
    clear_size = socket.get("clear_size_m") or [None, None]
    return {
        "socket_id": socket_id,
        "kind": kind,
        "compatibility_type": socket.get("compatibility_type"),
        "width_m": clear_size[0],
        "elevation_m": socket.get("floor_elevation_m"),
        "circulation_role": "connector",
        "tested_pair_ids": tested_pair_ids,
        "provenance": (
            f"{poetics_path}; socket data from the library index; "
            "circulation_role is an unreviewed placeholder (#219)"
        ),
    }


def _roles(poetics: dict[str, Any]) -> dict[str, Any]:
    """Ground/figure comes from the accepted poetics; the rest waits for #219."""
    form_role = poetics.get("form_role")
    if form_role not in {"ground", "figure"}:
        raise SourceLibraryError("Accepted poetics must carry a ground/figure role")
    return {
        "map_role": form_role,
        "form_role": form_role,
        "semantic_tags": [],
        "circulation_role": PLACEHOLDER_CIRCULATION_ROLE,
        "sightline_tags": [],
    }


def _surfaces(tag: str, poetics_path: str) -> dict[str, Any]:
    """Tag-only surfaces: #217 owns the reviewed material and palette identifiers."""
    provenance = (
        f"{poetics_path}; acoustic tag derived from accepted style_tags; "
        "material_id and palette_id are unreviewed placeholders (#217)"
    )
    return {
        surface: {
            "material_id": f"{tag}_{surface}_material",
            "palette_id": None,
            "acoustic": tag,
            "texture_refs": [],
            "provenance": provenance,
            "sign": SURFACE_SIGN[surface],
        }
        for surface in SURFACES
    }


def _acoustics(tag: str) -> dict[str, Any]:
    return {
        "status": "tag_only",
        "tag": tag,
        "probe": {
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
        },
        "absorption": {
            "status": "unknown",
            "wall": None,
            "floor": None,
            "ceiling": None,
            "trim": None,
            "source": "#213",
            "confidence": 0.0,
        },
    }


def _lighting(layers: dict[str, Any]) -> dict[str, Any]:
    light = layers.get("light") or {}
    value = light.get("value")
    return {
        "status": "source_estimated" if value is not None else "unknown",
        "tier": None,
        "color_temp_k": None,
        "illuminance_lux": None,
        "fixtures": [],
        "evidence": [],
    }


def _translation_chain(
    chain: list[dict[str, Any]], origin: str
) -> list[dict[str, Any]]:
    result = []
    for stage in chain:
        name = stage.get("stage")
        evidence = stage.get("evidence") or []
        if not evidence:
            continue
        if name == "direct_frame" and origin == "source_picture_set":
            name = "direct_image"
        result.append({"stage": name, "evidence": list(evidence)})
    return result


def write_profile(
    profile: dict[str, Any], target: Path, root: Path = ROOT
) -> dict[str, str]:
    """Write one new profile sidecar; existing targets are never overwritten."""
    data = canonical_bytes(profile)
    write_new(target, data)
    return {
        "path": target.relative_to(root).as_posix(),
        "sha256": sha256_bytes(data),
    }
