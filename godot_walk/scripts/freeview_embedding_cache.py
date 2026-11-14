"""Hash-keyed JSON cache for view embeddings.

The cache key is the frame SHA-256, never the file path or batch name, so a
frame decoded into two batches is embedded once. The model identity is part of
the cache header: a different model or weight hash cannot reuse the file.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deterministic_json import canonical_bytes

CACHE_SCHEMA_VERSION = 1
PREPROCESSING_VERSION = "dinov2-cls-resize256-centercrop224-imagenet-v1"
EMBEDDING_DIGITS = 7
UNIT_NORM_TOLERANCE = 1e-3
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CACHE_KEYS = {"schema_version", "model", "entries"}
MODEL_KEYS = {
    "model_id",
    "weights_sha256",
    "embedding_dim",
    "preprocessing_version",
}


class EmbeddingCacheError(ValueError):
    """A cache file is stale, malformed, or bound to another model."""


@dataclass(frozen=True)
class EmbeddingModelIdentity:
    """The exact model and preprocessing contract an embedding belongs to."""

    model_id: str
    weights_sha256: str
    embedding_dim: int
    preprocessing_version: str = PREPROCESSING_VERSION

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise EmbeddingCacheError("Model ID must not be empty")
        if SHA256_PATTERN.fullmatch(self.weights_sha256) is None:
            raise EmbeddingCacheError("Weights SHA-256 must be 64 lowercase hex")
        if self.embedding_dim < 1:
            raise EmbeddingCacheError("Embedding dimension must be positive")
        if not self.preprocessing_version.strip():
            raise EmbeddingCacheError("Preprocessing version must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "weights_sha256": self.weights_sha256,
            "embedding_dim": self.embedding_dim,
            "preprocessing_version": self.preprocessing_version,
        }


class EmbeddingCache:
    """A deterministic, append-only embedding map keyed by frame SHA-256."""

    def __init__(
        self,
        path: Path,
        identity: EmbeddingModelIdentity,
        entries: dict[str, list[float]] | None = None,
    ) -> None:
        self.path = path
        self.identity = identity
        self._entries: dict[str, list[float]] = {}
        for frame_sha256, embedding in (entries or {}).items():
            self._put_checked(frame_sha256, embedding)

    @classmethod
    def load(cls, path: Path, identity: EmbeddingModelIdentity) -> EmbeddingCache:
        if not path.exists():
            return cls(path, identity)
        if path.is_symlink():
            raise EmbeddingCacheError(f"Refusing to read a symlinked cache: {path}")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EmbeddingCacheError(
                f"Embedding cache is unreadable: {path}"
            ) from error
        return cls(path, identity, _validated_entries(document, identity))

    def __len__(self) -> int:
        return len(self._entries)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._entries))

    def get(self, frame_sha256: str) -> list[float] | None:
        values = self._entries.get(frame_sha256)
        return list(values) if values is not None else None

    def put(self, frame_sha256: str, embedding: Sequence[float]) -> None:
        """Add one embedding; refuse to replace a different value."""
        self._put_checked(frame_sha256, embedding)

    def save(self) -> str:
        """Merge with any file already on disk and replace it atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_lock(self.path.with_name(self.path.name + ".lock")):
            self._merge_existing()
            data = canonical_bytes(self.to_dict())
            if self.path.exists():
                if self.path.is_symlink():
                    raise EmbeddingCacheError(
                        f"Refusing to write a symlinked cache: {self.path}"
                    )
                if self.path.read_bytes() == data:
                    return "unchanged"
                status = "updated"
            else:
                status = "created"
            _atomic_replace(self.path, data)
            return status

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "model": self.identity.to_dict(),
            "entries": {
                frame_sha256: self._entries[frame_sha256]
                for frame_sha256 in sorted(self._entries)
            },
        }

    def _merge_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EmbeddingCacheError(
                f"Embedding cache is unreadable: {self.path}"
            ) from error
        existing = _validated_entries(document, self.identity)
        for frame_sha256, embedding in existing.items():
            self._put_checked(frame_sha256, embedding)

    def _put_checked(self, frame_sha256: str, embedding: Sequence[float]) -> None:
        values = _validated_embedding(frame_sha256, embedding, self.identity)
        prior = self._entries.get(frame_sha256)
        if prior is not None and prior != values:
            raise EmbeddingCacheError(
                f"Refusing to replace a cached embedding for {frame_sha256}"
            )
        self._entries[frame_sha256] = values


def _validated_entries(
    document: Any, identity: EmbeddingModelIdentity
) -> dict[str, list[float]]:
    if not isinstance(document, dict) or set(document) != CACHE_KEYS:
        raise EmbeddingCacheError("Embedding cache has unexpected top-level fields")
    if document["schema_version"] != CACHE_SCHEMA_VERSION:
        raise EmbeddingCacheError("Embedding cache schema version is not supported")
    model = document["model"]
    if not isinstance(model, dict) or set(model) != MODEL_KEYS:
        raise EmbeddingCacheError("Embedding cache model block is malformed")
    if model != identity.to_dict():
        raise EmbeddingCacheError(
            "Embedding cache belongs to a different model or preprocessing contract"
        )
    entries = document["entries"]
    if not isinstance(entries, dict):
        raise EmbeddingCacheError("Embedding cache entries must be an object")
    for frame_sha256, embedding in entries.items():
        if not isinstance(embedding, list):
            raise EmbeddingCacheError(f"Embedding for {frame_sha256} is not a list")
    return entries


def _validated_embedding(
    frame_sha256: str, embedding: Sequence[float], identity: EmbeddingModelIdentity
) -> list[float]:
    if SHA256_PATTERN.fullmatch(frame_sha256) is None:
        raise EmbeddingCacheError("Cache keys must be frame SHA-256 hex digests")
    try:
        values = [float(value) for value in embedding]
    except (TypeError, ValueError) as error:
        raise EmbeddingCacheError(
            f"Embedding for {frame_sha256} contains non-numeric values"
        ) from error
    if len(values) != identity.embedding_dim:
        raise EmbeddingCacheError(
            f"Embedding for {frame_sha256} has {len(values)} values; "
            f"expected {identity.embedding_dim}"
        )
    if not all(math.isfinite(value) for value in values):
        raise EmbeddingCacheError(f"Embedding for {frame_sha256} is not finite")
    norm = math.sqrt(sum(value * value for value in values))
    if abs(norm - 1.0) > UNIT_NORM_TOLERANCE:
        raise EmbeddingCacheError(
            f"Embedding for {frame_sha256} is not L2-normalized (norm {norm:.6f})"
        )
    return [round(value, EMBEDDING_DIGITS) for value in values]


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _atomic_replace(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
