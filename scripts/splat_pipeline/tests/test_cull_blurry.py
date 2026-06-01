"""
Tests for cull_blurry.py — argument parsing, error paths, and idempotency.

Run with: python3 -m pytest scripts/splat_pipeline/tests/ -v
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from cull_blurry import (
    collect_images,
    parse_args,
    parse_extensions,
    resolve_images_dir,
)


class TestParseArgs:
    def test_defaults(self):
        args = parse_args(["some_scene"])
        assert args.scene_dir == "some_scene"
        assert args.percentile == 18
        assert args.dry_run is False
        assert set(args.ext) == {".jpg", ".jpeg", ".png"}

    def test_percentile(self):
        args = parse_args(["scene", "--percentile", "25"])
        assert args.percentile == 25

    def test_dry_run(self):
        args = parse_args(["scene", "--dry-run"])
        assert args.dry_run is True

    def test_ext(self):
        args = parse_args(["scene", "--ext", ".png", "jpg"])
        assert args.ext == [".png", "jpg"]

    def test_no_positional(self):
        with pytest.raises(SystemExit):
            parse_args([])

    def test_help(self):
        with pytest.raises(SystemExit):
            parse_args(["--help"])


class TestParseExtensions:
    def test_bare_extensions(self):
        assert parse_extensions(["jpg", "png"]) == {".jpg", ".png"}

    def test_dotted_extensions(self):
        assert parse_extensions([".jpg", ".PNG"]) == {".jpg", ".png"}

    def test_whitespace_trim(self):
        assert parse_extensions([" jpg "]) == {".jpg"}

    def test_empty_returns_empty_set(self):
        assert parse_extensions([]) == set()


class TestResolveImagesDir:
    def test_scene_dir_with_images_subdir(self, tmp_path):
        (tmp_path / "images").mkdir()
        result = resolve_images_dir(tmp_path)
        assert result == tmp_path / "images"

    def test_direct_images_dir(self, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()
        result = resolve_images_dir(images_dir)
        assert result == images_dir

    def test_missing_images_dir(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            resolve_images_dir(tmp_path)
        assert exc.value.code == 1


class TestCollectImages:
    def test_collects_jpg_png(self, tmp_path):
        (tmp_path / "a.jpg").touch()
        (tmp_path / "b.png").touch()
        (tmp_path / "c.txt").touch()
        frames = collect_images(tmp_path, {".jpg", ".png"})
        assert set(frames) == {tmp_path / "a.jpg", tmp_path / "b.png"}

    def test_empty_dir_exits(self, tmp_path):
        with pytest.raises(SystemExit) as exc:
            collect_images(tmp_path, {".jpg"})
        assert exc.value.code == 3

    def test_sorted_order(self, tmp_path):
        (tmp_path / "frame_002.jpg").touch()
        (tmp_path / "frame_001.jpg").touch()
        (tmp_path / "frame_010.jpg").touch()
        frames = collect_images(tmp_path, {".jpg"})
        assert frames == [
            tmp_path / "frame_001.jpg",
            tmp_path / "frame_002.jpg",
            tmp_path / "frame_010.jpg",
        ]


class TestIdempotency:
    def _make_image(self, path: Path, blur_sigma: float):
        import cv2

        size = 64
        img = np.random.randn(size, size).astype(np.float32) * 30 + 128
        if blur_sigma > 0:
            img = cv2.GaussianBlur(img, (0, 0), blur_sigma)
        img = np.clip(img, 0, 255).astype(np.uint8)
        cv2.imwrite(str(path), img)

    def test_idempotent_rerun_does_not_crash(self, tmp_path):
        import cv2

        images_dir = tmp_path / "images"
        images_dir.mkdir()

        for i in range(10):
            path = images_dir / f"frame_{i:04d}.jpg"
            blur = 1.0 if i < 3 else 0.2
            self._make_image(path, blur)

        from cull_blurry import main

        main([str(tmp_path), "--percentile", "30"])
        remaining1 = sorted(images_dir.glob("*.jpg"))
        assert len(remaining1) < 10

        main([str(tmp_path), "--percentile", "30"])
        remaining2 = sorted(images_dir.glob("*.jpg"))

        assert len(remaining2) <= len(remaining1)
        assert len(remaining1) < 10

    def test_dry_run_preserves_all_files(self, tmp_path):
        images_dir = tmp_path / "images"
        images_dir.mkdir()

        for i in range(5):
            self._make_image(images_dir / f"frame_{i:04d}.jpg", blur_sigma=0.5)

        from cull_blurry import main

        main([str(tmp_path), "--dry-run", "--percentile", "30"])
        remaining = sorted(images_dir.glob("*.jpg"))
        assert len(remaining) == 5

    def test_no_images_dir_exits(self, tmp_path):
        from cull_blurry import main

        with pytest.raises(SystemExit) as exc:
            main([str(tmp_path)])
        assert exc.value.code == 1

    def test_empty_images_dir_exits(self, tmp_path):
        (tmp_path / "images").mkdir()
        from cull_blurry import main

        with pytest.raises(SystemExit) as exc:
            main([str(tmp_path)])
        assert exc.value.code == 3
