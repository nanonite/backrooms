"""Peirce sign tagging, voids and translation chain for module_poetics.

Rule: only `symbol` features (authored sockets, collision, obstacles) may ever
be traversable connectors. `index` features may motivate a proposal but never
certify one. `icon` features resemble the source but are not observed geometry.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

PATH_PATTERN = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.\w{1,6}")
FRAME_PATTERN = re.compile(r"(^|/)frames/.+\.(png|jpe?g)$")
PANORAMA_PATTERN = re.compile(r"(^|/)hunyuan/.+/panorama[^/]*$")
FRAMES_SEGMENT = "/frames/"


def citations_in(text: str | None) -> list[str]:
    """Repo-style file paths mentioned in free provenance text."""
    return sorted(set(PATH_PATTERN.findall(text or "")))


def motivated_by_index(citations: list[str]) -> bool:
    return any(FRAMES_SEGMENT in f"/{path}" for path in citations)


def obstacle_id(obstacle: Any) -> str:
    if isinstance(obstacle, str):
        return obstacle.rsplit("/", 1)[-1]
    identifier = obstacle.get("id") or str(obstacle.get("collision_node") or "")
    if not identifier:
        raise ValueError(f"Obstacle has no id: {obstacle}")
    return identifier.rsplit("/", 1)[-1]


def obstacle_feature(obstacle: Any) -> dict[str, Any]:
    text = None if isinstance(obstacle, str) else obstacle.get("provenance")
    citations = citations_in(text)
    return {
        "feature_id": f"obstacle:{obstacle_id(obstacle)}",
        "kind": "obstacle",
        "sign": "symbol",
        "citations": citations,
        "motivated_by_index": motivated_by_index(citations),
        "provenance_text": text,
    }


def socket_feature(socket: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": f"socket:{socket['id']}",
        "kind": "socket",
        "sign": "symbol",
        "citations": [],
    }


def collision_feature(module: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": "collision",
        "kind": "collision",
        "sign": "symbol",
        "citations": citations_in(module.get("collision_provenance")),
    }


def is_surface_asset(path: str) -> bool:
    return (
        "/textures/" in f"/{path}"
        or "/hunyuan/" in f"/{path}"
        or PurePosixPath(path).name.startswith("panorama")
    )


def surface_features(visual_assets: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "feature_id": f"surface:{path}",
            "kind": "surface",
            "sign": "icon",
            "citations": [path],
        }
        for path in visual_assets
        if is_surface_asset(path)
    ]


def opening_feature(opening: dict[str, Any]) -> dict[str, Any]:
    frame = opening.get("source_frame")
    return {
        "feature_id": f"observed_opening:{opening['id']}",
        "kind": "observed_opening",
        "sign": "index",
        "citations": [frame] if frame else [],
    }


def build_features(module: dict[str, Any]) -> list[dict[str, Any]]:
    features = [obstacle_feature(item) for item in module.get("obstacles") or []]
    features += [socket_feature(item) for item in module.get("sockets") or []]
    features.append(collision_feature(module))
    features += surface_features(module.get("visual_assets") or [])
    features += [opening_feature(item) for item in module.get("observed_openings") or []]
    identifiers = [feature["feature_id"] for feature in features]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"Duplicate feature ids in module {module.get('id')}")
    return sorted(features, key=lambda feature: feature["feature_id"])


def build_voids(module: dict[str, Any]) -> list[dict[str, Any]]:
    """Observed openings never tested as connectors, kept as non-traversable."""
    voids = [
        {
            "void_id": opening["id"],
            "source_frame": opening.get("source_frame"),
            "description": opening.get("description"),
            "traversable": False,
        }
        for opening in module.get("observed_openings") or []
        if opening.get("tested_connector") is not True
    ]
    return sorted(voids, key=lambda void: void["void_id"])


def translation_chain(
    source_id: str | None, scene: str | None, paths: list[str]
) -> list[dict[str, Any]]:
    """Ordered media translations: direct frame, Hunyuan panorama, Godot room."""
    if source_id is None:
        return []
    stages = [
        ("direct_frame", sorted(p for p in paths if FRAME_PATTERN.search(p))),
        ("hunyuan_panorama", sorted(p for p in paths if PANORAMA_PATTERN.search(p))),
        ("godot_room", [scene] if scene else []),
    ]
    return [{"stage": name, "evidence": found} for name, found in stages if found]
