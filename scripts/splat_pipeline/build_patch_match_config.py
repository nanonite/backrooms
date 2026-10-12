#!/usr/bin/env python3
"""Write COLMAP PatchMatch neighbors for images registered in the dense model."""

from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

MAX_IMAGE_ID = 2_147_483_647
MAX_NEIGHBORS = 10


def registered_database_images(database_path: Path, dense_dir: Path) -> dict[int, str]:
    image_dir = dense_dir / "images"
    registered_names = {
        path.relative_to(image_dir).as_posix()
        for path in image_dir.rglob("*")
        if path.is_file()
    }
    with closing(sqlite3.connect(database_path)) as database:
        return {
            int(image_id): name
            for image_id, name in database.execute(
                "SELECT image_id, name FROM images ORDER BY image_id"
            )
            if name in registered_names
        }


def image_neighbors(database_path: Path, registered: dict[int, str]) -> dict[str, list[tuple[str, int]]]:
    neighbors = {name: [] for name in registered.values()}
    with closing(sqlite3.connect(database_path)) as database:
        pairs = database.execute("SELECT pair_id, rows FROM two_view_geometries")
        for pair_id, match_count in pairs:
            image_id_1, image_id_2 = divmod(pair_id, MAX_IMAGE_ID)
            if image_id_1 not in registered or image_id_2 not in registered:
                continue
            name_1, name_2 = registered[image_id_1], registered[image_id_2]
            neighbors[name_1].append((name_2, match_count))
            neighbors[name_2].append((name_1, match_count))
    return neighbors


def write_patch_match_config(dense_dir: Path, database_path: Path) -> tuple[int, int]:
    registered = registered_database_images(database_path, dense_dir)
    if not registered:
        raise ValueError(f"no registered images found in {dense_dir / 'images'}")

    neighbors = image_neighbors(database_path, registered)
    lines = []
    for image_name in sorted(neighbors):
        image_pairs = sorted(neighbors[image_name], key=lambda pair: -pair[1])
        selected = image_pairs[:MAX_NEIGHBORS]
        if selected:
            lines.extend((image_name, ", ".join(name for name, _ in selected)))
    if not lines:
        raise ValueError("registered images have no two-view neighbors")

    config_path = dense_dir / "stereo" / "patch-match.cfg"
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(registered), len(lines) // 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dense-dir", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        registered_count, configured_count = write_patch_match_config(
            args.dense_dir, args.database
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    print(
        "  patch-match.cfg written for "
        f"{configured_count} registered images ({registered_count} total)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
