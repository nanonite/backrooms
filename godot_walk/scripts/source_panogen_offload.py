"""Apply the pinned diagnostic profile to Hunyuan's custom Diffusers pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

DIAGNOSTIC_PROFILE = "memory-diagnostic-512x256-v1"
OFFLOAD_MODE = "sequential_cpu"


def configure_pipeline(
    pipeline: Any,
    *,
    fp8_attention: bool,
    fp8_gemm: bool,
    attention_processor_factory: Callable[[], Any],
    gemm_processor: Callable[[Any], None],
) -> None:
    """Configure tiling and FP8 before installing one sequential offload hook set."""
    if not callable(getattr(pipeline, "enable_sequential_cpu_offload", None)):
        raise TypeError("Installed Diffusers pipeline lacks sequential CPU offload")
    if not callable(getattr(pipeline, "remove_all_hooks", None)):
        raise TypeError("Installed Diffusers pipeline cannot replace offload hooks")
    if not callable(getattr(pipeline, "enable_vae_tiling", None)):
        raise TypeError("Hunyuan custom pipeline lacks VAE tiling")
    if not hasattr(pipeline, "transformer"):
        raise RuntimeError("Hunyuan custom pipeline lacks its transformer")

    pipeline.enable_vae_tiling()
    if fp8_attention:
        pipeline.transformer.set_attn_processor(attention_processor_factory())
    if fp8_gemm:
        gemm_processor(pipeline.transformer)

    # Diffusers 0.34.0 removes existing model/sequential hooks inside this method.
    # Do not call enable_model_cpu_offload or move the pipeline to CUDA here.
    pipeline.enable_sequential_cpu_offload(gpu_id=0)


def configure_demo_state(demo: Any, pipeline: Any, cache_enabled: bool) -> Any:
    """Set the upstream demo fields consumed by its unchanged image-to-panorama run."""
    demo.args.cache = cache_enabled
    demo.pipe = pipeline
    demo.THETA = 0
    demo.PHI = 0
    demo.guidance_scale = 30
    demo.num_inference_steps = 50
    demo.shifting_extend = 0
    demo.blend_extend = 6
    demo.general_negative_prompt = (
        "human, person, people, messy,low-quality, blur, noise, low-resolution"
    )
    demo.general_positive_prompt = "high-quality,  high-resolution, sharp, clear, 8k"
    return demo
