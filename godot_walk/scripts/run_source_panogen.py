"""Run one pre-authorized, direct-source Hunyuan image-to-panorama attempt."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
HUNYUAN = Path("/mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0")
EXPECTED_COMMIT = "57fa9f3a79eae1079c279968cdb9d82c75fa7c86"
EXPECTED_PACKAGES = {
    "diffusers": "0.34.0",
    "accelerate": "1.6.0",
    "torch": "2.5.0",
    "transformers": "4.51.0",
}


def main() -> int:
    arguments = _arguments()
    _validate_guard_and_seed(arguments)
    output = Path(arguments.output_dir).resolve()
    if output.exists():
        raise FileExistsError(f"Panorama output already exists: {output}")
    _validate_runtime()
    sys.path.insert(0, str(HUNYUAN))
    _validate_offload_compatibility()
    demo = _build_demo(arguments)
    demo.width, demo.height, demo.FOV = arguments.width, arguments.height, 80.0
    demo.true_cfg_scale = arguments.true_cfg_scale
    output.mkdir(parents=True, exist_ok=False)
    demo.run(
        arguments.prompt,
        "",
        arguments.seed_frame,
        seed=arguments.seed,
        output_path=str(output),
    )
    if not (output / "panorama.png").is_file():
        raise RuntimeError("Panogen completed without panorama.png")
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--source-kind", choices=("video", "picture_set"), default="video"
    )
    parser.add_argument("--seed-frame", required=True, type=Path)
    parser.add_argument("--seed-frame-sha256", required=True)
    parser.add_argument("--source-video-sha256")
    parser.add_argument("--source-image-set-sha256")
    parser.add_argument("--image-id")
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--guard-receipt-sha256", required=True)
    parser.add_argument("--guard-receipt", required=True, type=Path)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=256)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--offload-mode", choices=("sequential_cpu",), default="sequential_cpu"
    )
    parser.add_argument("--cache", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--vae-tiling", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--fp8-attention", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument(
        "--fp8-gemm", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--true-cfg-scale", type=float, default=1.0)
    arguments = parser.parse_args()
    if (arguments.width, arguments.height) != (512, 256):
        parser.error("The bounded memory diagnostic profile requires 512 by 256")
    if arguments.width % 64 or arguments.height % 64:
        parser.error("Panogen dimensions must be multiples of 64")
    if not arguments.vae_tiling:
        parser.error("The diagnostic profile requires VAE tiling")
    if arguments.cache:
        parser.error("The diagnostic profile requires caching to be disabled")
    if not arguments.fp8_attention or not arguments.fp8_gemm:
        parser.error("The diagnostic profile requires both existing FP8 processors")
    if arguments.source_kind == "video":
        if not arguments.source_video_sha256:
            parser.error("Video sources require --source-video-sha256")
        if arguments.source_image_set_sha256 or arguments.image_id:
            parser.error("Video sources cannot carry picture-set arguments")
    else:
        if not arguments.source_image_set_sha256 or not arguments.image_id:
            parser.error(
                "Picture-set sources require --source-image-set-sha256 and --image-id"
            )
        if arguments.source_video_sha256:
            parser.error("Picture-set sources cannot carry --source-video-sha256")
    return arguments


def _build_demo(arguments: argparse.Namespace):
    import torch

    sys.path.insert(0, str(HUNYUAN))
    from demo_panogen import Image2PanoramaDemo
    from hy3dworld import Image2PanoramaPipelines
    from hy3dworld.AngelSlim.attention_quantization_processor import (
        FluxFp8AttnProcessor2_0,
    )
    from hy3dworld.AngelSlim.gemm_quantization_processor import FluxFp8GeMMProcessor

    from source_panogen_offload import configure_demo_state, configure_pipeline

    if arguments.offload_mode != "sequential_cpu":
        raise ValueError(
            "The bounded source launcher only supports sequential CPU offload"
        )
    demo = Image2PanoramaDemo.__new__(Image2PanoramaDemo)
    demo.args = SimpleNamespace(cache=arguments.cache)
    demo.height, demo.width, demo.FOV = arguments.height, arguments.width, 80.0
    demo.THETA, demo.PHI = 0, 0
    demo.true_cfg_scale = arguments.true_cfg_scale
    demo.model_path = "black-forest-labs/FLUX.1-Fill-dev"
    demo.lora_path = "tencent/HunyuanWorld-1"
    pipeline = Image2PanoramaPipelines.from_pretrained(
        demo.model_path, torch_dtype=torch.bfloat16
    )
    pipeline.load_lora_weights(
        demo.lora_path,
        subfolder="HunyuanWorld-PanoDiT-Image",
        weight_name="lora.safetensors",
        torch_dtype=torch.bfloat16,
    )
    pipeline.fuse_lora()
    pipeline.unload_lora_weights()
    configure_pipeline(
        pipeline,
        fp8_attention=arguments.fp8_attention,
        fp8_gemm=arguments.fp8_gemm,
        attention_processor_factory=FluxFp8AttnProcessor2_0,
        gemm_processor=FluxFp8GeMMProcessor,
    )
    return configure_demo_state(demo, pipeline, arguments.cache)


def _validate_offload_compatibility() -> None:
    from diffusers import DiffusionPipeline
    from hy3dworld import Image2PanoramaPipelines
    from hy3dworld.AngelSlim.attention_quantization_processor import (
        FluxFp8AttnProcessor2_0,
    )
    from hy3dworld.AngelSlim.gemm_quantization_processor import FluxFp8GeMMProcessor

    if not issubclass(Image2PanoramaPipelines, DiffusionPipeline):
        raise TypeError("Pinned image-to-panorama pipeline is not a DiffusionPipeline")
    if not callable(FluxFp8AttnProcessor2_0) or not callable(FluxFp8GeMMProcessor):
        raise TypeError("Pinned FP8 processor API is unavailable")
    source = inspect.getsource(DiffusionPipeline.enable_sequential_cpu_offload)
    if "self.remove_all_hooks()" not in source or "cpu_offload(model" not in source:
        raise RuntimeError(
            "Pinned Diffusers sequential offload no longer replaces hooks as expected"
        )
    if not callable(getattr(Image2PanoramaPipelines, "enable_vae_tiling", None)):
        raise TypeError("Pinned custom pipeline does not expose VAE tiling")


def _validate_guard_and_seed(arguments: argparse.Namespace) -> None:
    receipt = json.loads(arguments.guard_receipt.read_text(encoding="utf-8"))
    _validate_guard_source(receipt, arguments)
    if receipt.get("seed_frame_sha256") != arguments.seed_frame_sha256:
        raise RuntimeError("GPU guard receipt does not bind this seed frame")
    if _sha256(arguments.guard_receipt) != arguments.guard_receipt_sha256:
        raise RuntimeError("GPU guard receipt hash changed")
    if _sha256(arguments.seed_frame) != arguments.seed_frame_sha256:
        raise RuntimeError("Direct-source seed hash changed")


def _validate_guard_source(
    receipt: dict[str, object], arguments: argparse.Namespace
) -> None:
    if (
        receipt.get("status") != "passed"
        or receipt.get("source_id") != arguments.source_id
        or receipt.get("source_manifest_sha256") != arguments.source_manifest_sha256
    ):
        raise RuntimeError("Panogen requires a passing source-bound GPU guard receipt")
    if getattr(arguments, "source_kind", "video") == "picture_set":
        if (
            receipt.get("source_kind") != "picture_set"
            or receipt.get("source_image_set_sha256")
            != getattr(arguments, "source_image_set_sha256", None)
            or receipt.get("seed_image_id") != getattr(arguments, "image_id", None)
        ):
            raise RuntimeError(
                "Panogen requires a passing image-set-bound GPU guard receipt"
            )
        return
    if (
        receipt.get("source_kind", "video") != "video"
        or receipt.get("source_video_sha256")
        != getattr(arguments, "source_video_sha256", None)
    ):
        raise RuntimeError("Panogen requires a passing video-bound GPU guard receipt")


def _validate_runtime() -> None:
    if not HUNYUAN.is_dir():
        raise FileNotFoundError(HUNYUAN)
    result = subprocess.run(
        ["git", "-C", str(HUNYUAN), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.stdout.strip() != EXPECTED_COMMIT:
        raise RuntimeError(
            "HunyuanWorld runtime revision differs from the pinned build"
        )
    package_check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.metadata as m; import json; expected=json.loads("
            + repr(json.dumps(EXPECTED_PACKAGES))
            + "); actual={k:m.version(k) for k in expected}; print(actual); raise SystemExit(actual != expected)",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(f"Validated Hunyuan offload dependencies: {package_check.stdout.strip()}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
