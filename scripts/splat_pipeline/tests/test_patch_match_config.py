"""Tests for registered-image filtering in the COLMAP PatchMatch config."""

import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from build_patch_match_config import write_patch_match_config

MAX_IMAGE_ID = 2_147_483_647


def _pair_id(image_id_1: int, image_id_2: int) -> int:
    first, second = sorted((image_id_1, image_id_2))
    return first * MAX_IMAGE_ID + second


def _make_database(path: Path, names: list[str], pairs: list[tuple[int, int]]) -> None:
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE images (image_id INTEGER, name TEXT)")
        database.execute("CREATE TABLE two_view_geometries (pair_id INTEGER, rows INTEGER)")
        database.executemany(
            "INSERT INTO images VALUES (?, ?)",
            [(index, name) for index, name in enumerate(names, start=1)],
        )
        database.executemany(
            "INSERT INTO two_view_geometries VALUES (?, ?)",
            [(_pair_id(first, second), 100 - first) for first, second in pairs],
        )


def test_config_excludes_unregistered_database_frames(tmp_path):
    dense_dir = tmp_path / "dense"
    image_dir = dense_dir / "images"
    stereo_dir = dense_dir / "stereo"
    image_dir.mkdir(parents=True)
    stereo_dir.mkdir(parents=True)
    for name in ("frame_0001.jpg", "frame_0002.jpg"):
        (image_dir / name).write_bytes(b"registered")
    database_path = tmp_path / "database.db"
    _make_database(
        database_path,
        ["frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg"],
        [(1, 2), (1, 3), (2, 3)],
    )

    registered_count, configured_count = write_patch_match_config(dense_dir, database_path)

    config = (stereo_dir / "patch-match.cfg").read_text(encoding="utf-8")
    assert registered_count == 2
    assert configured_count == 2
    assert "frame_0001.jpg\nframe_0002.jpg" in config
    assert "frame_0003.jpg" not in config


def test_config_fails_when_registered_images_have_no_neighbors(tmp_path):
    dense_dir = tmp_path / "dense"
    (dense_dir / "images").mkdir(parents=True)
    (dense_dir / "images/frame_0001.jpg").write_bytes(b"registered")
    (dense_dir / "stereo").mkdir()
    database_path = tmp_path / "database.db"
    _make_database(database_path, ["frame_0001.jpg"], [])

    try:
        write_patch_match_config(dense_dir, database_path)
    except ValueError as error:
        assert "no two-view neighbors" in str(error)
    else:
        raise AssertionError("expected an error for an isolated registered image")
