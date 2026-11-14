"""Tests for deterministic preprocessing, local model discovery and cache reuse."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import sha256_file
from freeview_embedding_cache import EmbeddingCache, EmbeddingModelIdentity
from freeview_embeddings import (
    IMAGE_SIZE,
    EmbeddingUnavailableError,
    discover_local_weights,
    embed_into_cache,
    preprocess_frame,
    resolve_local_model,
    runtime_status,
)
from run_freeview_consensus import main as run_freeview_main

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _gradient(path: Path, width: int, height: int) -> Path:
    array = np.zeros((height, width, 3), dtype=np.uint8)
    array[..., 0] = np.linspace(0, 255, width, dtype=np.uint8)[None, :]
    array[..., 1] = np.linspace(0, 255, height, dtype=np.uint8)[:, None]
    Image.fromarray(array, mode="RGB").save(path)
    return path


def _snapshot(directory: Path, hidden_size: int = 768) -> Path:
    snapshot = directory / "models--facebook--dinov2-base" / "snapshots" / "abc"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text(
        json.dumps({"image_size": 224, "patch_size": 14, "hidden_size": hidden_size}),
        encoding="utf-8",
    )
    (snapshot / "model.safetensors").write_bytes(b"local-weights")
    return snapshot


class PreprocessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_landscape_frame_is_a_deterministic_224_tensor(self) -> None:
        image = _gradient(self.directory / "frame.png", 320, 180)
        first = preprocess_frame(image)
        second = preprocess_frame(image)
        self.assertEqual((3, IMAGE_SIZE, IMAGE_SIZE), first.shape)
        self.assertEqual("float32", first.dtype)
        self.assertTrue(np.array_equal(first, second))

    def test_portrait_and_small_frames_are_supported(self) -> None:
        portrait = _gradient(self.directory / "portrait.png", 180, 320)
        small = _gradient(self.directory / "small.png", 100, 50)
        self.assertEqual((3, IMAGE_SIZE, IMAGE_SIZE), preprocess_frame(portrait).shape)
        self.assertEqual((3, IMAGE_SIZE, IMAGE_SIZE), preprocess_frame(small).shape)

    def test_unreadable_frame_is_rejected(self) -> None:
        broken = self.directory / "broken.png"
        broken.write_bytes(b"not an image")
        with self.assertRaises(EmbeddingUnavailableError):
            preprocess_frame(broken)


class LocalModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_snapshot_identity_is_the_weight_hash(self) -> None:
        snapshot = _snapshot(self.directory)
        model = resolve_local_model(snapshot, "facebook/dinov2-base")
        self.assertEqual("facebook/dinov2-base", model.model_id)
        self.assertEqual(768, model.embedding_dim)
        self.assertEqual(
            sha256_file(snapshot / "model.safetensors"), model.weights_sha256
        )
        self.assertEqual(
            "dinov2-cls-resize256-centercrop224-imagenet-v1",
            model.identity().preprocessing_version,
        )

    def test_missing_snapshot_names_model_size_and_source(self) -> None:
        with self.assertRaises(EmbeddingUnavailableError) as context:
            resolve_local_model(self.directory / "missing", "facebook/dinov2-base")
        message = str(context.exception)
        self.assertIn("facebook/dinov2-base", message)
        self.assertIn("346 MB", message)
        self.assertIn("https://huggingface.co/facebook/dinov2-base", message)
        self.assertIn("--model-dir", message)

    def test_pretraining_image_size_may_differ_from_preprocessing(self) -> None:
        snapshot = _snapshot(self.directory)
        (snapshot / "config.json").write_text(
            json.dumps({"image_size": 518, "patch_size": 14, "hidden_size": 768}),
            encoding="utf-8",
        )
        model = resolve_local_model(snapshot, "facebook/dinov2-base")
        self.assertEqual(768, model.embedding_dim)

    def test_wrong_backbone_geometry_is_rejected(self) -> None:
        snapshot = _snapshot(self.directory)
        (snapshot / "config.json").write_text(
            json.dumps({"image_size": 224, "patch_size": 16, "hidden_size": 768}),
            encoding="utf-8",
        )
        with self.assertRaises(EmbeddingUnavailableError):
            resolve_local_model(snapshot, "facebook/dinov2-base")

    def test_config_without_hidden_size_is_rejected(self) -> None:
        snapshot = _snapshot(self.directory)
        (snapshot / "config.json").write_text(
            json.dumps({"image_size": 224, "patch_size": 14}), encoding="utf-8"
        )
        with self.assertRaises(EmbeddingUnavailableError):
            resolve_local_model(snapshot, "facebook/dinov2-base")

    def test_sharded_checkpoint_is_rejected(self) -> None:
        snapshot = _snapshot(self.directory)
        (snapshot / "model.safetensors").unlink()
        (snapshot / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(EmbeddingUnavailableError):
            resolve_local_model(snapshot, "facebook/dinov2-base")

    def test_discovery_finds_a_local_hf_snapshot(self) -> None:
        snapshot = _snapshot(self.directory)
        checkpoints = self.directory / "torch-checkpoints"
        checkpoints.mkdir()
        found = discover_local_weights(self.directory, checkpoints)
        self.assertEqual(1, len(found))
        self.assertEqual("facebook/dinov2-base", found[0]["model_id"])
        self.assertEqual(snapshot.as_posix(), found[0]["model_dir"])
        self.assertIn("model.safetensors", found[0]["weights_path"])

    def test_discovery_finds_a_torch_hub_checkpoint(self) -> None:
        checkpoints = self.directory / "torch-checkpoints"
        checkpoints.mkdir()
        checkpoint = checkpoints / "dinov2_vitb14_pretrain.pth"
        checkpoint.write_bytes(b"checkpoint")
        found = discover_local_weights(self.directory, checkpoints)
        self.assertEqual("torch_hub_checkpoint", found[0]["kind"])
        self.assertEqual(checkpoint.as_posix(), found[0]["weights_path"])

    def test_discovery_is_empty_for_an_empty_cache(self) -> None:
        checkpoints = self.directory / "torch-checkpoints"
        checkpoints.mkdir()
        self.assertEqual([], discover_local_weights(self.directory, checkpoints))

    def test_runtime_status_reports_both_optional_imports(self) -> None:
        status = runtime_status()
        self.assertEqual({"torch", "transformers"}, set(status))
        self.assertTrue(
            all(found is None or isinstance(found, str) for found in status.values())
        )


class _FakeEncoder:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.paths: list[Path] = []

    def encode(self, paths: list[Path]) -> np.ndarray:
        self.paths.extend(paths)
        return np.asarray(
            [[1.0] + [0.0] * (self.dimension - 1) for _ in paths], dtype=np.float32
        )


class CacheReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.identity = EmbeddingModelIdentity(
            model_id="facebook/dinov2-base",
            weights_sha256="1" * 64,
            embedding_dim=3,
        )
        self.cache = EmbeddingCache(self.directory / "cache.json", self.identity)
        self.encoder = _FakeEncoder()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_second_run_reuses_every_cached_embedding(self) -> None:
        frames = [
            (SHA_A, self.directory / "a.png"),
            (SHA_B, self.directory / "b.png"),
        ]
        first = embed_into_cache(frames, self.encoder, self.cache)  # type: ignore[arg-type]
        self.assertEqual({"encoded": 2, "reused": 0, "cached_total": 2}, first)
        self.assertEqual(2, len(self.encoder.paths))
        second = embed_into_cache(frames, self.encoder, self.cache)  # type: ignore[arg-type]
        self.assertEqual({"encoded": 0, "reused": 2, "cached_total": 2}, second)
        self.assertEqual(2, len(self.encoder.paths))

    def test_only_the_missing_frame_is_encoded(self) -> None:
        embed_into_cache([(SHA_A, self.directory / "a.png")], self.encoder, self.cache)  # type: ignore[arg-type]
        self.encoder.paths.clear()
        counts = embed_into_cache(
            [
                (SHA_A, self.directory / "a.png"),
                (SHA_C, self.directory / "c.png"),
            ],
            self.encoder,  # type: ignore[arg-type]
            self.cache,
        )
        self.assertEqual({"encoded": 1, "reused": 1, "cached_total": 2}, counts)
        self.assertEqual([self.directory / "c.png"], self.encoder.paths)

    def test_repeated_sha_is_encoded_once(self) -> None:
        counts = embed_into_cache(
            [
                (SHA_A, self.directory / "a.png"),
                (SHA_A, self.directory / "copy-of-a.png"),
            ],
            self.encoder,  # type: ignore[arg-type]
            self.cache,
        )
        self.assertEqual({"encoded": 1, "reused": 0, "cached_total": 1}, counts)

    def test_saved_cache_survives_reload(self) -> None:
        embed_into_cache(
            [(SHA_B, self.directory / "b.png")], self.encoder, self.cache  # type: ignore[arg-type]
        )
        self.cache.save()
        reloaded = EmbeddingCache.load(self.cache.path, self.identity)
        self.assertEqual([1.0, 0.0, 0.0], reloaded.get(SHA_B))


class WeightsCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_model_dir_outside_the_hub_cache_reports_available(self) -> None:
        snapshot = _snapshot(self.directory)
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_freeview_main(
                [
                    "weights",
                    "--hf-cache",
                    (self.directory / "empty-hub").as_posix(),
                    "--torch-checkpoints",
                    (self.directory / "empty-checkpoints").as_posix(),
                    "--model-dir",
                    snapshot.as_posix(),
                ]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertEqual("available", report["status"])
        self.assertEqual("available", report["requested_model"]["status"])
        self.assertEqual("facebook/dinov2-base", report["requested_model"]["model_id"])

    def test_missing_model_dir_reports_missing_without_a_model_call(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = run_freeview_main(
                [
                    "weights",
                    "--hf-cache",
                    (self.directory / "empty-hub").as_posix(),
                    "--torch-checkpoints",
                    (self.directory / "empty-checkpoints").as_posix(),
                    "--model-dir",
                    (self.directory / "missing").as_posix(),
                ]
            )
        report = json.loads(output.getvalue())
        self.assertEqual(3, code)
        self.assertEqual("missing", report["status"])
        self.assertEqual("missing", report["requested_model"]["status"])


if __name__ == "__main__":
    unittest.main()
