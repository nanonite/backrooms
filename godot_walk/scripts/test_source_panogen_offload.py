"""CPU-only compatibility tests for the source Panogen offload adapter."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_source_panogen
from source_panogen_offload import configure_demo_state, configure_pipeline


class FakePipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.transformer = self
        self.hooks = ["old_model_offload_hook"]

    def enable_vae_tiling(self) -> None:
        self.calls.append(("vae_tiling", True))

    def set_attn_processor(self, processor: object) -> None:
        self.calls.append(("fp8_attention", processor))

    def enable_sequential_cpu_offload(self, gpu_id: int) -> None:
        self.calls.append(("sequential_cpu_offload", gpu_id))
        self.hooks.clear()

    def remove_all_hooks(self) -> None:
        self.hooks.clear()

    def to(self, device: str) -> None:
        self.calls.append(("pipeline_to", device))


class PanogenOffloadTests(unittest.TestCase):
    def test_fp8_and_tiling_are_configured_before_one_hook_replacing_offload(self):
        pipeline = FakePipeline()

        def fp8_gemm(_transformer: object) -> None:
            pipeline.calls.append(("fp8_gemm", True))

        configure_pipeline(
            pipeline,
            fp8_attention=True,
            fp8_gemm=True,
            attention_processor_factory=lambda: "fp8-processor",
            gemm_processor=fp8_gemm,
        )

        self.assertEqual(
            ["vae_tiling", "fp8_attention", "fp8_gemm", "sequential_cpu_offload"],
            [name for name, _value in pipeline.calls],
        )
        self.assertEqual(("sequential_cpu_offload", 0), pipeline.calls[-1])
        self.assertEqual([], pipeline.hooks)
        self.assertFalse(any(name == "pipeline_to" for name, _ in pipeline.calls))

    def test_missing_sequential_api_fails_closed(self):
        with self.assertRaisesRegex(TypeError, "sequential CPU offload"):
            configure_pipeline(
                object(),
                fp8_attention=False,
                fp8_gemm=False,
                attention_processor_factory=lambda: object(),
                gemm_processor=lambda _transformer: None,
            )

    def test_demo_uses_original_run_state_without_deep_cache(self):
        demo = SimpleNamespace(args=SimpleNamespace())
        pipeline = object()

        result = configure_demo_state(demo, pipeline, cache_enabled=False)

        self.assertIs(result, demo)
        self.assertIs(demo.pipe, pipeline)
        self.assertFalse(demo.args.cache)
        self.assertEqual(50, demo.num_inference_steps)
        self.assertEqual(6, demo.blend_extend)
        self.assertEqual(0, demo.shifting_extend)

    def test_launcher_parses_explicit_diagnostic_configuration(self):
        arguments = [
            "run_source_panogen.py",
            "--source-id",
            "video-0123456789abcdef",
            "--seed-frame",
            "/tmp/frame.png",
            "--seed-frame-sha256",
            "a" * 64,
            "--source-video-sha256",
            "b" * 64,
            "--source-manifest-sha256",
            "c" * 64,
            "--guard-receipt-sha256",
            "d" * 64,
            "--guard-receipt",
            "/tmp/guard.json",
            "--output-dir",
            "/tmp/panorama",
            "--prompt",
            "test room",
            "--width",
            "512",
            "--height",
            "256",
            "--seed",
            "42",
            "--offload-mode",
            "sequential_cpu",
            "--no-cache",
            "--vae-tiling",
            "--fp8-attention",
            "--fp8-gemm",
        ]
        with patch("sys.argv", arguments):
            config = run_source_panogen._arguments()

        self.assertEqual("sequential_cpu", config.offload_mode)
        self.assertFalse(config.cache)
        self.assertTrue(config.vae_tiling)
        self.assertEqual((512, 256, 42), (config.width, config.height, config.seed))


if __name__ == "__main__":
    unittest.main()
