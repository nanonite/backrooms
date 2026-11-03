"""Read-only view of the library index plus module_poetics drafts for map stages."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT, repo_relative, sha256_file  # noqa: E402
from library_index import load_json, load_verified_index  # noqa: E402
from module_poetics import SOURCE_ROOM_PREFIX, draft_path  # noqa: E402

ACCEPTED_SOURCE_NAME = "module_poetics_v2.json"
ACCEPTED_STATUS = "operator_accepted"

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
    # Operator-accepted poetics (issue 188); None / empty for a module that only has a draft.
    form_role: str | None = None
    rarity_tier: int | None = None
    apollonian: float | None = None
    dionysian: float | None = None
    style_tags: tuple[str, ...] = ()
    metadata_record: dict[str, str] | None = None  # {path, sha256} of the record that was read
    draft_layout_usable: bool | None = None  # the v1 draft's flag (gmap-0.1.0/0.2.0 fill files)
    ceiling_height_m: float | None = None

    @property
    def tested_socket_count(self) -> int:
        return sum(1 for socket in self.sockets if socket.tested)

    @property
    def legacy_layout_usable(self) -> bool:
        """`layout_usable` as gmap-0.1.0 / 0.2.0 fill files report it (draft-based)."""
        return self.layout_usable if self.draft_layout_usable is None else self.draft_layout_usable


@dataclass(frozen=True)
class Library:
    index_ref: dict[str, str]
    snapshot_ref: dict[str, str]
    modules: tuple[LibraryModule, ...]


def bbox(points: tuple[Point, ...]) -> tuple[float, float, float, float]:
    xs, zs = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(zs), max(xs), max(zs)


def accepted_path(entry: dict, root: Path) -> Path:
    """Where the operator-accepted record of this index entry lives (it may not exist)."""
    room_dir = entry.get("room_dir")
    if room_dir and room_dir.startswith(SOURCE_ROOM_PREFIX):
        return root / room_dir / ACCEPTED_SOURCE_NAME
    return draft_path(entry, root).with_name(f"{entry['module_id']}-v{entry['version']}.accepted.json")


def resolve_record(entry: dict, root: Path) -> tuple[Path, dict, bool]:
    """(path, record, accepted): the accepted record when it exists and says so, else the v1 draft."""
    path = accepted_path(entry, root)
    if path.is_file():
        record = load_json(path)
        if record.get("metadata_status") == ACCEPTED_STATUS:
            return path, record, True
    return draft_path(entry, root), load_json(draft_path(entry, root)), False


def load_module(entry: dict, root: Path) -> LibraryModule:
    path, draft, accepted = resolve_record(entry, root)
    legacy = load_json(draft_path(entry, root)) if accepted else draft
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
    poetics = draft.get("poetics") or {}
    eligible = bool(draft["eligibility"]["layout_eligible_derived"])
    return LibraryModule(
        entry["module_id"],
        entry["version"],
        entry["source_id"],
        footprint,
        sockets,
        accepted and eligible,
        poetics.get("form_role") if accepted else None,
        poetics.get("rarity_tier") if accepted else None,
        poetics.get("apollonian") if accepted else None,
        poetics.get("dionysian") if accepted else None,
        tuple(poetics.get("style_tags") or ()) if accepted else (),
        {"path": repo_relative(path, root), "sha256": sha256_file(path)},
        bool(legacy["eligibility"]["layout_eligible_derived"]),
        draft["shape"].get("ceiling_height_m"),
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


def metadata_records(library: Library) -> list[dict[str, str]]:
    """[{module_id, path, sha256}] of the record read for each module, sorted by module_id."""
    return sorted(
        ({"module_id": m.module_id, **m.metadata_record} for m in library.modules if m.metadata_record),
        key=lambda record: record["module_id"],
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
