"""Build a hash-bound deterministic #149 layout JSON for Godot playback."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from issue149_layout_core import ROOT, canonical_json, generate_layout, load_catalog_snapshot

EVIDENCE = ROOT / "godot_walk/evidence/2026-10-22-issue-149"
DEFAULT_OUTPUT = EVIDENCE / "layout_seed_149.json"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=149)
    parser.add_argument("--placements", type=int, default=10)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--snapshot-out", type=Path)
    parser.add_argument("--bounded-streaming", action="store_true")
    parser.add_argument("--loops", action="store_true", help="Request unsupported loop topology (will be rejected)")
    arguments = parser.parse_args()
    if arguments.loops:
        parser.error("loop topology is not supported by the current open-socket tree kit")
    return arguments


def _resource_path(path: Path) -> str:
    project = ROOT / "godot_walk"
    try:
        relative = path.resolve().relative_to(project.resolve())
    except ValueError as error:
        raise ValueError("Layout output must be inside godot_walk so Godot can load it") from error
    return "res://" + relative.as_posix()


def _seal_layout(layout: dict, snapshot_path: Path) -> None:
    layout["catalog_snapshot_path"] = _resource_path(snapshot_path)
    layout.pop("layout_sha256", None)
    layout["layout_sha256"] = hashlib.sha256(canonical_json(layout)).hexdigest()


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main() -> int:
    arguments = _arguments()
    snapshot_output = arguments.snapshot_out or arguments.out.parent / "catalog_snapshot.json"
    snapshot, catalog_hash, snapshot_bytes = load_catalog_snapshot()
    layout = generate_layout(arguments.seed, arguments.placements, snapshot, catalog_hash,
                             arguments.bounded_streaming)
    _seal_layout(layout, snapshot_output)
    _write(snapshot_output, snapshot_bytes)
    serialized_layout = (json.dumps(layout, indent=2, ensure_ascii=True) + "\n").encode()
    _write(arguments.out, serialized_layout)
    _write(arguments.out.with_suffix(arguments.out.suffix + ".sha256"),
           (hashlib.sha256(serialized_layout).hexdigest() + "  " + arguments.out.name + "\n").encode())
    print(
        f"generated {layout['layout_id']}: {len(layout['placements'])} placements, "
        f"{len(layout['connections'])} connections, branch={layout['topology']['branch_side']}, "
        f"catalog_sha256={catalog_hash}, layout={arguments.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
