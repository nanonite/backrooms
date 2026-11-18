"""Record material-aware footsteps and derived acoustics for the six accepted video rooms (#266).

This module is deliberately read-only over the accepted rooms. It reads each
room's immutable ``module_poetics_v1.json`` (surface textures + shape metadata)
and writes only NEW versioned files:

    godot_walk/room_catalog/footstep_materials_v0.1.0.json
    godot_walk/room_catalog/module_acoustics_v0.3.0.json
    godot_walk/evidence/2026-11-17-issue-266-footsteps-acoustics/gallery_entry_v0.1.0.json

The two catalog records also get detached ``.sha256`` pins computed from their
bytes (never typed by hand).

No audio is synthesised. Snow has no footstep layer and a dedicated rock/sand
layer is only a proxy today; both are listed under ``missing_layers`` for the
operator. Reverb parameters reuse the #205 ``room_acoustic_probe.gd`` mapping,
but the inputs are derived from accepted shape metadata, so the result is marked
``derived_from_shape_metadata`` and is never claimed to be a ray-cast measurement.

Usage:
    python3 godot_walk/scripts/issue266_room_audio.py generate
    python3 godot_walk/scripts/issue266_room_audio.py check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import (
    ROOT,
    canonical_bytes,
    plan_write,
    sha256_file,
    write_new,
)

GENERATOR_VERSION = "issue266-room-audio-0.1.0"
ISSUE = 266

FOOTSTEP_PATH = Path("godot_walk/room_catalog/footstep_materials_v0.1.0.json")
ACOUSTICS_PATH = Path("godot_walk/room_catalog/module_acoustics_v0.3.0.json")
GALLERY_PATH = Path(
    "godot_walk/evidence/2026-11-17-issue-266-footsteps-acoustics/"
    "gallery_entry_v0.1.0.json"
)

# Read-only accepted-room metadata; room_type is the courtyard/corridor class
# recorded by the operator in #172-#177, not a connectivity claim.
ROOMS: tuple[dict[str, str], ...] = (
    {"source_id": "video-22909eb734e4d8e2", "room_id": "slot-canyon-courtyard-v1", "room_type": "courtyard"},
    {"source_id": "video-d857abe7a94da9d1", "room_id": "nested-light-corridor-v1", "room_type": "corridor"},
    {"source_id": "video-d92fc1fa764aa3a2", "room_id": "snow-garden-courtyard-v2", "room_type": "courtyard"},
    {"source_id": "video-102caf53423018b7", "room_id": "chevron-corridor-v1", "room_type": "corridor"},
    {"source_id": "video-2671b32f256a4ee7", "room_id": "chevron-corridor-v1", "room_type": "corridor"},
    {"source_id": "video-61b91dbeb9026dc7", "room_id": "chevron-cross-corridor-v1", "room_type": "corridor"},
)

# Footstep tag vocabulary of the committed footsteps-0.3.0 generator. No snow
# or dedicated rock/sand tag exists, so those are handled explicitly below.
EXISTING_FOOTSTEP_TAGS = ("carpet", "concrete", "tile", "plaster", "metal", "wood", "debris", "default")

# Openness proxies. The #205 probe's openness is the fraction of horizontal
# rays that miss walls, which cannot see an open sky. For courtyards we use a
# deliberately extended open-sky energy-loss proxy (0.9), documented as such;
# for closed corridors we use 1/12, the tightest value measured in
# module_acoustics_v0.2.0.json. Both are estimates, not ray-cast measurements.
OPENNESS_OPEN_SKY = 0.9
OPENNESS_CLOSED = 1.0 / 12.0

# room_acoustic_probe.gd (#205) constants, reproduced verbatim for the mapping.
RAY_LENGTH_M = 20.0
ROOM_SIZE_REFERENCE_M = 10.0
CEILING_LOW_M = 2.2
CEILING_HIGH_M = 6.0
SPEED_OF_SOUND_MPS = 343.0
MIN_PREDELAY_MSEC = 1.0
MAX_PREDELAY_MSEC = 50.0


def _poetics_path(source_id: str, room_id: str) -> Path:
    return Path(
        f"godot_walk/source_library/sources/{source_id}/rooms/{room_id}/"
        "module_poetics_v1.json"
    )


def _load_poetics(source_id: str, room_id: str, root: Path) -> dict[str, Any]:
    path = _poetics_path(source_id, room_id)
    try:
        document = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read {path.as_posix()}: {error}") from error
    if document.get("metadata_status") != "draft_mechanical":
        raise ValueError(f"{path.as_posix()}: unexpected metadata_status")
    return document


def _surface_textures(poetics: dict[str, Any]) -> list[str]:
    names = []
    for feature in poetics["features"]:
        if feature.get("kind") != "surface" or not feature.get("citations"):
            continue
        names.append(Path(feature["citations"][0]).name)
    return sorted(names)


def _floor_evidence(source_id: str, room_id: str, root: Path) -> dict[str, Any]:
    """Read the walkable floor's authored material from the room script (read-only)."""
    path = Path(
        f"godot_walk/source_library/sources/{source_id}/rooms/{room_id}/room.gd"
    )
    try:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read {path.as_posix()}: {error}") from error
    texture = None
    solid_material = None
    png_names: list[str] = []
    for line in lines:
        if "FLOOR_TEXTURE_PATH" in line and ".png" in line:
            texture = Path(line.split('"')[1]).name
        if "WalkableFloor" in line and "materials." in line:
            solid_material = line.split("materials.")[1].split(",")[0].strip()
        png_names.extend(Path(match).name for match in re.findall(r'"([^"]+\.png)"', line))
    if texture is None:
        floor_keywords = ("floor", "sand", "carpet", "tile", "reflect", "snow", "rock")
        candidates = [
            name for name in png_names if any(word in name.lower() for word in floor_keywords)
        ]
        named = [name for name in candidates if "floor" in name.lower()]
        if named or candidates:
            texture = sorted(named or candidates)[0]
    if texture is None and solid_material is None:
        raise ValueError(f"{path.as_posix()}: no authored walkable floor material found")
    return {
        "texture": texture,
        "solid_material": solid_material,
        "source": path.as_posix(),
    }


def _classify_floor(floor: dict[str, Any], room_id: str) -> dict[str, Any]:
    """Return floor class, footstep tag and rationale from the authored floor."""
    texture = (floor["texture"] or "").lower()
    material = (floor["solid_material"] or "").lower()
    joined = f"{texture} {material} {room_id.lower()}"
    if "snow" in joined:
        return {
            "floor_class": "snow",
            "footstep_tag": None,
            "status": "missing_layer",
            "rationale": (
                f"Walkable floor uses {floor['solid_material']} (an authored solid "
                "snow material; no snow texture). No snow footstep layer exists, "
                "so no material tag is asserted."
            ),
        }
    if "carpet" in joined:
        return {
            "floor_class": "carpet",
            "footstep_tag": "carpet",
            "status": "existing_tag",
            "rationale": (
                f"Walkable floor uses {floor['texture']}; the existing heavily "
                "damped 'carpet' layer matches a soft floor."
            ),
        }
    if any(word in joined for word in ("reflective", "gloss", "tile")):
        return {
            "floor_class": "concrete_tile",
            "footstep_tag": "tile",
            "status": "existing_tag",
            "rationale": (
                f"Walkable floor uses {floor['texture']}, a hard reflective surface "
                "read as polished tile; the existing bright, short 'tile' layer matches."
            ),
        }
    if any(word in joined for word in ("rock", "sand", "rubble")):
        return {
            "floor_class": "rock_sand",
            "footstep_tag": "debris",
            "status": "proxy_existing_tag",
            "rationale": (
                f"Walkable floor uses {floor['texture']}, a granular rock/sand surface; "
                "the existing 'debris' crunch layer is the closest available proxy, "
                "not a dedicated rock or sand layer."
            ),
        }
    return {
        "floor_class": "unknown",
        "footstep_tag": "default",
        "status": "unknown_surface",
        "rationale": "No recognised floor surface; the 'default' layer is a fallback only.",
    }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _map_metrics(mean_distance_m: float, ceiling_height_m: float, openness: float) -> dict[str, float]:
    """#205 room_acoustic_probe.gd map_metrics, evaluated on derived inputs."""
    mean_distance = _clamp(mean_distance_m, 0.0, RAY_LENGTH_M)
    ceiling = _clamp(ceiling_height_m, CEILING_LOW_M, RAY_LENGTH_M)
    openness_value = _clamp(openness, 0.0, 1.0)
    wall_size = _clamp(mean_distance / ROOM_SIZE_REFERENCE_M, 0.0, 1.0)
    height_size = _clamp(
        (ceiling - CEILING_LOW_M) / (CEILING_HIGH_M - CEILING_LOW_M), 0.0, 1.0
    )
    room_size = _clamp(0.10 + 0.78 * wall_size + 0.12 * height_size, 0.0, 1.0)
    damping = _clamp(
        0.22 + 0.48 * wall_size + 0.18 * height_size + 0.12 * openness_value, 0.0, 1.0
    )
    wet = _clamp(
        (0.18 + 0.48 * wall_size + 0.14 * height_size) * (1.0 - 0.35 * openness_value),
        0.0,
        1.0,
    )
    predelay = _clamp(
        mean_distance / SPEED_OF_SOUND_MPS * 1000.0, MIN_PREDELAY_MSEC, MAX_PREDELAY_MSEC
    )
    return {
        "room_size": round(room_size, 6),
        "damping": round(damping, 6),
        "wet": round(wet, 6),
        "predelay_msec": round(predelay, 6),
    }


def _collect(root: Path) -> list[dict[str, Any]]:
    records = []
    for spec in ROOMS:
        poetics = _load_poetics(spec["source_id"], spec["room_id"], root)
        textures = _surface_textures(poetics)
        floor_evidence = _floor_evidence(spec["source_id"], spec["room_id"], root)
        floor_evidence["sha256"] = sha256_file(root / floor_evidence["source"])
        floor = _classify_floor(floor_evidence, spec["room_id"])
        shape = poetics["shape"]
        bbox = shape["bbox_xz"]
        width = float(bbox["max"][0]) - float(bbox["min"][0])
        depth = float(bbox["max"][1]) - float(bbox["min"][1])
        mean_distance = round((width + depth) / 4.0, 6)
        openness = OPENNESS_OPEN_SKY if spec["room_type"] == "courtyard" else OPENNESS_CLOSED
        reverb = _map_metrics(mean_distance, float(shape["ceiling_height_m"]), openness)
        key = f"{poetics['module_id']}@{poetics['version']}"
        poetics_rel = _poetics_path(spec["source_id"], spec["room_id"])
        records.append(
            {
                "key": key,
                "module_id": poetics["module_id"],
                "version": int(poetics["version"]),
                "source_id": spec["source_id"],
                "room_id": spec["room_id"],
                "room_type": spec["room_type"],
                "poetics": {
                    "path": poetics_rel.as_posix(),
                    "sha256": sha256_file(root / poetics_rel),
                },
                "surfaces": textures,
                "floor_evidence": floor_evidence,
                "area_m2": float(shape["area_m2"]),
                "ceiling_height_m": float(shape["ceiling_height_m"]),
                "mean_distance_proxy_m": mean_distance,
                "openness_proxy": openness,
                "floor": floor,
                "reverb": reverb,
            }
        )
    return records


def _missing_layers() -> list[dict[str, Any]]:
    return [
        {
            "material": "snow",
            "needed_for": ["video_d92fc1fa764aa3a2_snow_garden_courtyard_v2@1"],
            "reason": "Snow-garden floor has a snow class but no synthesised layer.",
            "required_before_audio": [
                "Add a 'snow' tag with transient_soft, transient_hard, body and texture "
                "profiles to generate_footstep_audio.PROFILES (footsteps-0.4.0, new version).",
                "Bake four deterministic variants and extend audio/footsteps/provenance.json "
                "through the generator, never by hand.",
                "Add 'snow' to footstep_audit.AUDITION_TAGS/DISTANCE_TAGS and re-run the "
                "loudness and separability audit so all pairs pass.",
                "Operator listens to an audition sheet and approves before use.",
            ],
            "target_character": "soft, low-frequency crunch with a short damped body",
        },
        {
            "material": "rock_sand",
            "needed_for": ["video_22909eb734e4d8e2_slot_canyon_courtyard_v1@1"],
            "reason": "The existing 'debris' layer is a granular proxy for a sandy/rocky floor.",
            "required_before_audio": [
                "Decide whether a dedicated 'rock' or 'sand' tag is needed after operator "
                "listening; if so, add a new versioned generator profile and stems as for snow.",
                "Re-run the #202 audit before adopting any new tag.",
            ],
            "target_character": "dry granular crunch, mid-low modal body, bright short transient",
        },
    ]


def _footstep_document(records: list[dict[str, Any]]) -> dict[str, Any]:
    rooms = {}
    for record in records:
        rooms[record["key"]] = {
            "floor_class": record["floor"]["floor_class"],
            "footstep_tag": record["floor"]["footstep_tag"],
            "runtime_fallback": "default" if record["floor"]["footstep_tag"] is None else None,
            "status": record["floor"]["status"],
            "source_id": record["source_id"],
            "room_id": record["room_id"],
            "surfaces": record["surfaces"],
            "floor_evidence": record["floor_evidence"],
            "poetics": record["poetics"],
            "rationale": record["floor"]["rationale"],
        }
    return {
        "schema_version": 1,
        "generator": "godot_walk/scripts/issue266_room_audio.py",
        "generator_version": GENERATOR_VERSION,
        "issue": ISSUE,
        "scope": "the six operator-accepted standalone video rooms of #266",
        "footstep_generator": "footsteps-0.3.0",
        "footstep_tags_in_use": list(EXISTING_FOOTSTEP_TAGS),
        "provenance": "derived_from_accepted_surface_textures",
        "operator_listening": "pending",
        "audio_authoring_status": "none: no new footstep audio was synthesised or claimed correct",
        "missing_layers": _missing_layers(),
        "rooms": rooms,
    }


def _acoustics_document(records: list[dict[str, Any]], footstep_path: Path, root: Path) -> dict[str, Any]:
    modules = {}
    for record in records:
        area = record["area_m2"]
        size_class = "large" if area >= 300.0 else "medium" if area >= 150.0 else "small"
        reverb_character = "open_courtyard" if record["room_type"] == "courtyard" else "enclosed_corridor"
        modules[record["key"]] = {
            "acoustic": record["floor"]["footstep_tag"] or "default",
            "floor_class": record["floor"]["floor_class"],
            "footstep_status": record["floor"]["status"],
            "reverb_character": reverb_character,
            "size_class": size_class,
            "surfaces": record["surfaces"],
            "floor_evidence": record["floor_evidence"],
            "shape": {
                "area_m2": area,
                "ceiling_height_m": record["ceiling_height_m"],
            },
            "derived_enclosure": {
                "mean_distance_proxy_m": record["mean_distance_proxy_m"],
                "openness_proxy": record["openness_proxy"],
                "mean_distance_rule": "(bbox width + bbox depth) / 4 of accepted footprint",
                "openness_rule": (
                    "0.9 open-sky energy-loss proxy for courtyards (an extension of "
                    "the #205 horizontal-ray openness), 1/12 for closed corridors"
                ),
            },
            "reverb": record["reverb"],
            "provenance": "derived_from_shape_metadata",
            "poetics": record["poetics"],
            "rationale": (
                f"{record['floor']['rationale']} Reverb character '{reverb_character}' "
                f"from a {size_class} ({area:g} m2) {record['room_type']} with a "
                f"{record['ceiling_height_m']:g} m ceiling; parameters use the #205 "
                "mapping on derived enclosure inputs, not a ray-cast measurement."
            ),
            "absorption": {"status": "unknown", "source": "#213"},
        }
    return {
        "schema_version": 3,
        "generator": "godot_walk/scripts/issue266_room_audio.py",
        "generator_version": GENERATOR_VERSION,
        "issue": ISSUE,
        "supersedes": None,
        "relationship_to_v0.2.0": (
            "additive overlay for six video rooms; module_acoustics_v0.2.0.json "
            "remains authoritative for its 11 measured modules"
        ),
        "reverb_mapping": {
            "source": "godot_walk/scripts/room_acoustic_probe.gd",
            "probe_version": "room-acoustic-probe-#205",
            "inputs": "derived_from_shape_metadata",
            "operator_listening": "pending",
        },
        "footstep_materials": {
            "path": FOOTSTEP_PATH.as_posix(),
            "sha256": sha256_file(root / footstep_path),
        },
        "modelling_limitations": [
            "Values are computed from accepted shape metadata, not measured by a ray-cast probe.",
            "No accepted module_profile_v1 exists for these rooms, so the #216 probe cannot run.",
            "The #205 openness metric is horizontal and does not model open sky; "
            "the courtyard proxy is a deliberate extension pending operator review.",
            "Agents cannot listen; reverb character and footstep match are pending operator review.",
        ],
        "modules": modules,
    }


def _gallery_document(records: list[dict[str, Any]]) -> dict[str, Any]:
    order = []
    for record in records:
        order.append(
            {
                "room_id": record["room_id"],
                "source_id": record["source_id"],
                "module": record["key"],
                "floor_class": record["floor"]["floor_class"],
                "footstep_tag": record["floor"]["footstep_tag"] or "default (fallback, not a match)",
                "reverb_character": "open_courtyard" if record["room_type"] == "courtyard" else "enclosed_corridor",
                "audition_status": "pending_operator_listening",
            }
        )
    return {
        "schema_version": 1,
        "generator": "godot_walk/scripts/issue266_room_audio.py",
        "generator_version": GENERATOR_VERSION,
        "issue": ISSUE,
        "style": "issue-207 strip list: each row is a walkable material entry",
        "note": (
            "This is a gallery entry listing material assignments, not a built scene. "
            "No new audio was authored; operator listening and any walkable audition "
            "scene remain pending."
        ),
        "operator_listening": "pending",
        "entries": order,
    }


def _write_versioned(path: Path, document: dict[str, Any], root: Path, pin: bool) -> str:
    data = canonical_bytes(document)
    status = plan_write(root / path, data)
    if status == "create":
        write_new(root / path, data)
    statuses = [f"{path.as_posix()}: {status}"]
    if pin:
        checksum = root / f"{path.as_posix()}.sha256"
        pin_data = f"{sha256_file(root / path)}  {path.name}\n".encode("utf-8")
        pin_status = plan_write(checksum, pin_data)
        if pin_status == "create":
            write_new(checksum, pin_data)
        statuses.append(f"{checksum.relative_to(root).as_posix()}: {pin_status}")
    return "; ".join(statuses)


def generate(root: Path = ROOT) -> dict[str, Any]:
    records = _collect(root)
    footstep = _footstep_document(records)
    footstep_status = _write_versioned(FOOTSTEP_PATH, footstep, root, pin=True)
    acoustics = _acoustics_document(records, FOOTSTEP_PATH, root)
    acoustics_status = _write_versioned(ACOUSTICS_PATH, acoustics, root, pin=True)
    gallery = _gallery_document(records)
    gallery_status = _write_versioned(GALLERY_PATH, gallery, root, pin=False)
    return {
        "rooms": len(records),
        "footstep_materials": footstep_status,
        "module_acoustics": acoustics_status,
        "gallery_entry": gallery_status,
        "audio_authored": False,
    }


def check(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        records = _collect(root)
        expected = {
            FOOTSTEP_PATH: _footstep_document(records),
            ACOUSTICS_PATH: _acoustics_document(records, FOOTSTEP_PATH, root),
            GALLERY_PATH: _gallery_document(records),
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [str(error)]
    for path, document in expected.items():
        target = root / path
        if not target.is_file():
            errors.append(f"{path.as_posix()}: missing")
            continue
        if target.read_bytes() != canonical_bytes(document):
            errors.append(f"{path.as_posix()}: differs from deterministic projection")
        if path in (FOOTSTEP_PATH, ACOUSTICS_PATH):
            pin = root / f"{path.as_posix()}.sha256"
            expected_pin = f"{sha256_file(target)}  {path.name}\n".encode("utf-8")
            if not pin.is_file() or pin.read_bytes() != expected_pin:
                errors.append(f"{path.as_posix()}.sha256: missing or stale")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check"))
    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        print(json.dumps(generate(), sort_keys=True))
        return 0
    errors = check()
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
