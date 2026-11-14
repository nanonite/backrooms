"""DINOv2 CLS embedding extraction with an offline, local-weights guard.

No download path exists in this module. A caller must point at a local
Hugging Face snapshot directory; if it is absent the error names the exact
model, size and source the operator would need to provide.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from deterministic_json import sha256_file
from freeview_embedding_cache import (
    PREPROCESSING_VERSION,
    EmbeddingCache,
    EmbeddingModelIdentity,
)
from PIL import Image, UnidentifiedImageError

IMAGE_SIZE = 224
RESIZE_SHORT_EDGE = 256
PATCH_SIZE = 14
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
DEFAULT_MODEL_ID = "facebook/dinov2-base"
WEIGHTS_FILENAMES = ("model.safetensors", "pytorch_model.bin")
MODEL_CATALOG = {
    "facebook/dinov2-small": {
        "embedding_dim": 384,
        "weights_megabytes": 88,
        "source": "https://huggingface.co/facebook/dinov2-small",
    },
    "facebook/dinov2-base": {
        "embedding_dim": 768,
        "weights_megabytes": 346,
        "source": "https://huggingface.co/facebook/dinov2-base",
    },
    "facebook/dinov2-large": {
        "embedding_dim": 1024,
        "weights_megabytes": 1210,
        "source": "https://huggingface.co/facebook/dinov2-large",
    },
}
HF_CACHE_ROOT = Path.home() / ".cache" / "huggingface" / "hub"
TORCH_CHECKPOINT_ROOT = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"


class EmbeddingUnavailableError(RuntimeError):
    """No usable local DINOv2 snapshot or runtime is present."""


@dataclass(frozen=True)
class LocalModel:
    model_id: str
    model_dir: Path
    weights_path: Path
    weights_sha256: str
    embedding_dim: int

    def identity(self) -> EmbeddingModelIdentity:
        return EmbeddingModelIdentity(
            model_id=self.model_id,
            weights_sha256=self.weights_sha256,
            embedding_dim=self.embedding_dim,
            preprocessing_version=PREPROCESSING_VERSION,
        )


def preprocess_frame(path: Path) -> np.ndarray:
    """Deterministic resize-short-side-256, center-crop-224 ImageNet tensor."""
    try:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            if width < 1 or height < 1:
                raise EmbeddingUnavailableError(f"Frame has no pixels: {path}")
            scale = RESIZE_SHORT_EDGE / min(width, height)
            resized_size = (
                max(RESIZE_SHORT_EDGE, round(width * scale)),
                max(RESIZE_SHORT_EDGE, round(height * scale)),
            )
            resized = rgb.resize(resized_size, resample=Image.Resampling.BICUBIC)
            left = (resized_size[0] - IMAGE_SIZE) // 2
            top = (resized_size[1] - IMAGE_SIZE) // 2
            cropped = resized.crop((left, top, left + IMAGE_SIZE, top + IMAGE_SIZE))
            array = np.asarray(cropped, dtype=np.float32) / 255.0
    except (OSError, UnidentifiedImageError) as error:
        raise EmbeddingUnavailableError(f"Cannot read frame: {path}") from error
    normalized = (array - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(normalized, (2, 0, 1)).astype(np.float32)


def resolve_local_model(model_dir: Path, model_id: str) -> LocalModel:
    """Validate one local Hugging Face snapshot and hash its weight file."""
    if not model_dir.is_dir():
        raise EmbeddingUnavailableError(_missing_weights_message(model_dir, model_id))
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        raise EmbeddingUnavailableError(
            f"{model_dir} has no config.json; {_missing_weights_message(model_dir, model_id)}"
        )
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EmbeddingUnavailableError(f"Cannot read {config_path}") from error
    _validate_backbone_config(config, model_dir)
    weights_path = _weights_path(model_dir)
    embedding_dim = int(config["hidden_size"])
    return LocalModel(
        model_id=model_id,
        model_dir=model_dir,
        weights_path=weights_path,
        weights_sha256=sha256_file(weights_path),
        embedding_dim=embedding_dim,
    )


def discover_local_weights(
    hf_cache_root: Path = HF_CACHE_ROOT,
    torch_checkpoint_root: Path = TORCH_CHECKPOINT_ROOT,
) -> list[dict[str, Any]]:
    """Report DINOv2 weights already present in the usual local caches."""
    found: list[dict[str, Any]] = []
    for model_id in sorted(MODEL_CATALOG):
        repository = hf_cache_root / f"models--{model_id.replace('/', '--')}"
        for snapshot in sorted(repository.glob("snapshots/*")):
            weights = _weights_path(snapshot, required=False)
            if weights is None:
                continue
            found.append(
                {
                    "model_id": model_id,
                    "kind": "huggingface_snapshot",
                    "model_dir": snapshot.as_posix(),
                    "weights_path": weights.as_posix(),
                    "weights_bytes": weights.stat().st_size,
                }
            )
    for checkpoint in sorted(torch_checkpoint_root.glob("dinov2_vit*.pth")):
        found.append(
            {
                "model_id": "facebookresearch/dinov2 torch hub checkpoint",
                "kind": "torch_hub_checkpoint",
                "model_dir": None,
                "weights_path": checkpoint.as_posix(),
                "weights_bytes": checkpoint.stat().st_size,
                "note": "needs the DINOv2 repository; the Hugging Face snapshot path is preferred",
            }
        )
    return found


def runtime_status() -> dict[str, Any]:
    """Report whether the optional torch/transformers runtime is importable."""
    status: dict[str, Any] = {"torch": None, "transformers": None}
    try:
        import torch

        status["torch"] = torch.__version__
    except ImportError:
        return status
    try:
        import transformers

        status["transformers"] = transformers.__version__
    except ImportError:
        return status
    return status


class DinoV2Encoder:
    """A CPU-only DINOv2 reader over a local snapshot; never downloads."""

    def __init__(self, model: LocalModel, batch_size: int = 8) -> None:
        if batch_size < 1:
            raise ValueError("Batch size must be positive")
        self.model = model
        self.batch_size = batch_size
        self._network = None

    def encode(self, paths: Sequence[Path]) -> np.ndarray:
        if not paths:
            return np.empty((0, self.model.embedding_dim), dtype=np.float32)
        network = self._load_network()
        embeddings = []
        for start in range(0, len(paths), self.batch_size):
            chunk_paths = paths[start : start + self.batch_size]
            chunk = np.stack([preprocess_frame(path) for path in chunk_paths])
            embeddings.append(self._forward(network, chunk))
        return np.concatenate(embeddings, axis=0)

    def _load_network(self) -> Any:
        if self._network is not None:
            return self._network
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            from transformers import Dinov2Model
        except ImportError as error:
            raise EmbeddingUnavailableError(
                "DINOv2 extraction needs torch and transformers in the active "
                "interpreter; neither the system python3 nor the nerfstudio env "
                "currently provides transformers."
            ) from error
        network = Dinov2Model.from_pretrained(
            self.model.model_dir.as_posix(), local_files_only=True
        )
        network.eval()
        network.to("cpu")
        hidden_size = int(network.config.hidden_size)
        if hidden_size != self.model.embedding_dim:
            raise EmbeddingUnavailableError(
                f"Model hidden size {hidden_size} does not match the resolved "
                f"embedding dimension {self.model.embedding_dim}"
            )
        self._network = network
        return network

    def _forward(self, network: Any, batch: np.ndarray) -> np.ndarray:
        import torch

        tensor = torch.from_numpy(batch).to("cpu")
        with torch.inference_mode():
            output = network(pixel_values=tensor)
        cls = output.last_hidden_state[:, 0, :].detach().float().cpu().numpy()
        return _normalized_rows(cls)


def embed_into_cache(
    frames: Sequence[tuple[str, Path]],
    encoder: DinoV2Encoder,
    cache: EmbeddingCache,
) -> dict[str, int]:
    """Encode only cache misses, in SHA order, and return reuse counts."""
    unique = {frame_sha256: path for frame_sha256, path in frames}
    missing = [
        (frame_sha256, unique[frame_sha256])
        for frame_sha256 in sorted(unique)
        if cache.get(frame_sha256) is None
    ]
    vectors = encoder.encode([path for _, path in missing])
    for (frame_sha256, _), vector in zip(missing, vectors, strict=True):
        cache.put(frame_sha256, vector.tolist())
    return {
        "encoded": len(missing),
        "reused": len(unique) - len(missing),
        "cached_total": len(unique),
    }


def _weights_path(model_dir: Path, required: bool = True) -> Path | None:
    for filename in WEIGHTS_FILENAMES:
        candidate = model_dir / filename
        if candidate.is_file():
            return candidate
    index = model_dir / "model.safetensors.index.json"
    if index.is_file():
        raise EmbeddingUnavailableError(
            f"{model_dir} is a sharded checkpoint; supply the single-file snapshot"
        )
    if required:
        raise EmbeddingUnavailableError(_missing_weights_message(model_dir, None))
    return None


def _validate_backbone_config(config: dict[str, Any], model_dir: Path) -> None:
    if int(config.get("image_size", IMAGE_SIZE)) != IMAGE_SIZE:
        raise EmbeddingUnavailableError(
            f"{model_dir} expects image size {config['image_size']}; this "
            f"preprocessing contract uses {IMAGE_SIZE}"
        )
    if int(config.get("patch_size", PATCH_SIZE)) != PATCH_SIZE:
        raise EmbeddingUnavailableError(
            f"{model_dir} expects patch size {config['patch_size']}; this "
            f"preprocessing contract uses {PATCH_SIZE}"
        )
    if "hidden_size" not in config:
        raise EmbeddingUnavailableError(f"{model_dir} config has no hidden_size")


def _normalized_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms <= 0.0):
        raise EmbeddingUnavailableError("DINOv2 produced a zero CLS embedding")
    return (matrix / norms).astype(np.float32)


def _missing_weights_message(model_dir: Path, model_id: str | None) -> str:
    requested = model_id or DEFAULT_MODEL_ID
    lines = [
        f"No usable local DINOv2 snapshot at {model_dir}.",
        (
            "Needed: one local Hugging Face DINOv2 snapshot with config.json and "
            "model.safetensors (or pytorch_model.bin). No download is attempted."
        ),
        "Candidates:",
    ]
    for name in sorted(MODEL_CATALOG):
        entry = MODEL_CATALOG[name]
        lines.append(
            f"- {name}: ~{entry['weights_megabytes']} MB, "
            f"{entry['embedding_dim']}-d CLS, {entry['source']}"
        )
    lines.append(
        f"Pass the snapshot directory with --model-dir; requested {requested}."
    )
    return "\n".join(lines)
