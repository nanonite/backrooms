"""Read-only view of the library index plus module_poetics drafts for map stages."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, repo_relative, sha256_file  # noqa: E402
from library_index import load_json, load_verified_index  # noqa: E402
from module_poetics import draft_path  # noqa: E402

Point = tuple[float, float]


@dataclass(frozen=True)
class Socket:
    socket_id: str
    pos: Point
    normal: Point
    compatibility_type: str
    tested: bool


@dataclass(frozen=True)
class LibraryModule:
    module_id: str
    version: int
    source_id: str | None
    footprint: tuple[Point, ...]
    sockets: tuple[Socket, ...]
    layout_usable: bool

    @property
    def tested_socket_count(self) -> int:
        return sum(1 for socket in self.sockets if socket.tested)


@dataclass(frozen=True)
class Library:
    index_ref: dict[str, str]
    snapshot_ref: dict[str, str]
    modules: tuple[LibraryModule, ...]


def bbox(points: tuple[Point, ...]) -> tuple[float, float, float, float]:
    xs, zs = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(zs), max(xs), max(zs)


def load_module(entry: dict, root: Path) -> LibraryModule:
    draft = load_json(draft_path(entry, root))
    tested = {item["socket_id"] for item in draft["ports"]["tested_sockets"]}
    sockets = tuple(
        Socket(
            s["id"],
            (s["local_floor_center"][0], s["local_floor_center"][2]),
            (s["outward_normal"][0], s["outward_normal"][2]),
            s["compatibility_type"],
            s["id"] in tested,
        )
        for s in entry["sockets"]
    )
    footprint = tuple((float(x), float(z)) for x, z in draft["shape"]["footprint_xz"])
    return LibraryModule(
        entry["module_id"],
        entry["version"],
        entry["source_id"],
        footprint,
        sockets,
        bool(draft["eligibility"]["layout_eligible_derived"]),
    )


def load_library(index_path: Path, root: Path = ROOT) -> Library:
    index = load_verified_index(index_path, root)
    modules = tuple(
        sorted(
            (load_module(entry, root) for entry in index["modules"]),
            key=lambda module: (module.module_id, module.version),
        )
    )
    return Library(
        {"path": repo_relative(index_path, root), "sha256": sha256_file(index_path)},
        {"path": index["snapshot_path"], "sha256": index["snapshot_sha256"]},
        modules,
    )


def figure_classes(library: Library) -> list[tuple[int, int]]:
    """Integer-ceiled bbox sizes of source-video modules, deduped and sorted."""
    sizes = set()
    for module in library.modules:
        if module.source_id is None:
            continue
        x0, z0, x1, z1 = bbox(module.footprint)
        sizes.add((math.ceil(round(x1 - x0, 6)), math.ceil(round(z1 - z0, 6))))
    return sorted(sizes)
