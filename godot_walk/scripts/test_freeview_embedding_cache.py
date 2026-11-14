"""Tests for the hash-keyed, model-bound embedding cache."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freeview_embedding_cache import (
    EmbeddingCache,
    EmbeddingCacheError,
    EmbeddingModelIdentity,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _identity(**overrides: object) -> EmbeddingModelIdentity:
    values = {
        "model_id": "facebook/dinov2-base",
        "weights_sha256": "1" * 64,
        "embedding_dim": 3,
    }
    values.update(overrides)
    return EmbeddingModelIdentity(**values)  # type: ignore[arg-type]


class EmbeddingCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "embeddings.json"
        self.identity = _identity()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_round_trip_is_keyed_by_frame_sha256(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        cache.put(SHA_A, [1.0, 0.0, 0.0])
        self.assertEqual("created", cache.save())
        loaded = EmbeddingCache.load(self.path, self.identity)
        self.assertEqual([1.0, 0.0, 0.0], loaded.get(SHA_A))
        self.assertIsNone(loaded.get(SHA_B))
        self.assertEqual((SHA_A,), loaded.keys())

    def test_second_save_is_unchanged(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        cache.put(SHA_A, [1.0, 0.0, 0.0])
        cache.save()
        before = self.path.read_bytes()
        self.assertEqual("unchanged", cache.save())
        self.assertEqual(before, self.path.read_bytes())

    def test_other_model_identity_is_rejected(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        cache.put(SHA_A, [1.0, 0.0, 0.0])
        cache.save()
        other = _identity(weights_sha256="2" * 64)
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, other)
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, _identity(embedding_dim=4))

    def test_different_embedding_for_same_hash_is_refused(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        cache.put(SHA_A, [1.0, 0.0, 0.0])
        with self.assertRaises(EmbeddingCacheError):
            cache.put(SHA_A, [0.0, 1.0, 0.0])

    def test_save_merges_entries_written_by_another_instance(self) -> None:
        first = EmbeddingCache.load(self.path, self.identity)
        second = EmbeddingCache.load(self.path, self.identity)
        first.put(SHA_A, [1.0, 0.0, 0.0])
        first.save()
        second.put(SHA_B, [0.0, 1.0, 0.0])
        second.save()
        merged = EmbeddingCache.load(self.path, self.identity)
        self.assertEqual([1.0, 0.0, 0.0], merged.get(SHA_A))
        self.assertEqual([0.0, 1.0, 0.0], merged.get(SHA_B))

    def test_save_is_byte_deterministic_regardless_of_insertion_order(self) -> None:
        one = EmbeddingCache(self.directory / "one.json", self.identity)
        two = EmbeddingCache(self.directory / "two.json", self.identity)
        one.put(SHA_A, [1.0, 0.0, 0.0])
        one.put(SHA_B, [0.0, 1.0, 0.0])
        two.put(SHA_B, [0.0, 1.0, 0.0])
        two.put(SHA_A, [1.0, 0.0, 0.0])
        one.save()
        two.save()
        self.assertEqual(
            (self.directory / "one.json").read_bytes(),
            (self.directory / "two.json").read_bytes(),
        )

    def test_non_unit_embedding_is_rejected(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        with self.assertRaises(EmbeddingCacheError):
            cache.put(SHA_A, [2.0, 0.0, 0.0])

    def test_wrong_dimension_is_rejected(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        with self.assertRaises(EmbeddingCacheError):
            cache.put(SHA_A, [1.0, 0.0])

    def test_non_finite_embedding_is_rejected(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        with self.assertRaises(EmbeddingCacheError):
            cache.put(SHA_A, [float("nan"), 0.0, 0.0])

    def test_unsafe_cache_key_is_rejected(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        with self.assertRaises(EmbeddingCacheError):
            cache.put("../frame.png", [1.0, 0.0, 0.0])

    def test_malformed_documents_are_rejected(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, self.identity)

        self.path.write_text(
            json.dumps({"schema_version": 1, "model": {}, "entries": {}}),
            encoding="utf-8",
        )
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, self.identity)

        self.path.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, self.identity)

    def test_symlinked_cache_is_refused(self) -> None:
        target = self.directory / "real.json"
        target.write_text("{}", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises(EmbeddingCacheError):
            EmbeddingCache.load(self.path, self.identity)

    def test_cache_document_has_text_only_values(self) -> None:
        cache = EmbeddingCache(self.path, self.identity)
        cache.put(SHA_A, [1.0, 0.0, 0.0])
        cache.put(SHA_B, [0.0, 1.0, 0.0])
        cache.save()
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(1, document["schema_version"])
        self.assertEqual(self.identity.to_dict(), document["model"])
        self.assertEqual([SHA_A, SHA_B], list(document["entries"]))
        self.assertTrue(
            all(isinstance(value, float) for value in document["entries"][SHA_A])
        )


class ModelIdentityTests(unittest.TestCase):
    def test_identity_fields_are_validated(self) -> None:
        with self.assertRaises(EmbeddingCacheError):
            _identity(model_id=" ")
        with self.assertRaises(EmbeddingCacheError):
            _identity(weights_sha256="abc")
        with self.assertRaises(EmbeddingCacheError):
            _identity(embedding_dim=0)
        with self.assertRaises(EmbeddingCacheError):
            _identity(preprocessing_version="")


if __name__ == "__main__":
    unittest.main()
