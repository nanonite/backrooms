"""GPU-attempt tests use fake preflight, sampler, and child process."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_source_hunyuan
import source_ingestion_gpu
import source_ingestion_runner
from gpu_job_lock import exclusive_gpu_job
from register_video_sources import register_video
from source_ingestion_resource_guard import ResourceGuardError, ResourceLimits
from video_source_library import SourceLibraryError, sha256_file


def fake_probe(_path: Path) -> dict[str, object]:
    return {
        "width": 1920,
        "height": 1080,
        "fps": 24.0,
        "frame_count": 96,
        "duration_seconds": 4.0,
    }


class FakeSampler:
    def start(self) -> None:
        return None

    def stop(self) -> dict[str, int]:
        return {"peak_child_rss_bytes": 100, "peak_gpu_memory_delta_bytes": 0}


class SourceIngestionGpuTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        video_dir = self.root / "data/videos"
        video_dir.mkdir(parents=True)
        self.video = video_dir / "sample.mp4"
        self.video.write_bytes(b"video bytes")
        self.source_id = register_video(self.video, self.root, fake_probe)
        source_ingestion_runner.record_source_review(
            self.source_id,
            "proceed",
            "The source shows a useful indoor space.",
            self.root,
        )
        self._extract_direct_seed()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _extract_direct_seed(self) -> None:
        def fake_extract(source_path: str, _indices: list[int], output: str) -> Path:
            output_dir = self.root / output
            output_dir.mkdir(parents=True)
            frame_path = output_dir / "frame_0001.png"
            Image.new("RGB", (1920, 1080), (10, 20, 30)).save(frame_path)
            relative = frame_path.relative_to(self.root).as_posix()
            extraction = {
                "schema_version": 1,
                "source_video": source_path,
                "source_video_sha256": sha256_file(self.video),
                "decoder": "ffmpeg select by decoded zero-based frame index",
                "frames": [
                    {
                        "frame_id": "frame_0001",
                        "index_zero_based": 0,
                        "timestamp_seconds": 0,
                        "path": relative,
                        "sha256": sha256_file(frame_path),
                        "decode_operation": "direct_source_video_decode_no_resize_or_edit",
                    }
                ],
            }
            manifest = output_dir / "extraction_manifest.json"
            manifest.write_text(json.dumps(extraction), encoding="utf-8")
            return manifest

        with patch.object(
            source_ingestion_runner,
            "extract_source_frames",
            side_effect=fake_extract,
        ):
            manifest_path = source_ingestion_runner.extract_frames(
                self.source_id, "seed-candidates-1", [0], self.root
            )
        extraction = json.loads(manifest_path.read_text(encoding="utf-8"))
        frame = extraction["frames"][0]
        with patch.object(
            source_ingestion_runner,
            "_presentation_timestamp_seconds",
            return_value=0.0,
        ):
            source_ingestion_runner.select_seed(
                self.source_id, frame["frame_id"], frame["path"], self.root
            )

    def _fake_runner(
        self, command: list[str], **_arguments
    ) -> subprocess.CompletedProcess[str]:
        output_index = command.index("--output-dir") + 1
        output = Path(command[output_index])
        output.mkdir(parents=True)
        (output / "panorama.png").write_bytes(b"fake panorama")
        return subprocess.CompletedProcess(command, 0, "complete", "")

    def test_next_attempt_id_uses_retry_path_once_then_advances_ordinal(self) -> None:
        authorization = {
            "event_type": "hunyuan_preflight_retry_approved",
            "payload": {"retry_attempt_id": "attempt-004-retry-001"},
        }
        self.assertEqual(
            "attempt-004-retry-001",
            source_ingestion_gpu._next_attempt_id(3, [authorization]),
        )
        started = {
            "event_type": "hunyuan_attempt_started",
            "payload": {"attempt_id": "attempt-004-retry-001"},
        }
        self.assertEqual(
            "attempt-005",
            source_ingestion_gpu._next_attempt_id(4, [authorization, started]),
        )

    def test_success_records_one_attempt_and_hashes_output(self) -> None:
        guard_calls = []

        def guard() -> dict[str, str]:
            guard_calls.append("checked")
            return {"guard_policy_version": "test", "free_vram_bytes": 1234}

        result = source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=guard,
            runner=self._fake_runner,
            sampler_factory=FakeSampler,
        )
        self.assertEqual("produced", result["status"])
        self.assertEqual(1, len(guard_calls))
        self.assertEqual(1, len(result["outputs"]))
        attempt_dir = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "hunyuan/attempt-001"
        )
        settings = json.loads(
            (attempt_dir / "attempt_config.json").read_text(encoding="utf-8")
        )
        self.assertEqual("sequential_cpu", settings["offload_mode"])
        self.assertEqual((512, 256), (settings["width"], settings["height"]))
        self.assertFalse(settings["cache_enabled"])
        self.assertTrue(settings["vae_tiling_enabled"])
        self.assertEqual(2700, settings["timeout_seconds"])
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(1, status["attempts_used"])
        self.assertTrue(status["awaiting_feedback"])
        self.assertFalse(status["can_start_attempt"])

    def test_guard_block_records_stop_without_counting_inference(self) -> None:
        def guard() -> dict[str, str]:
            raise RuntimeError("insufficient free VRAM")

        result = source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=guard,
            runner=self._fake_runner,
            sampler_factory=FakeSampler,
        )
        self.assertEqual("blocked", result["status"])
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(0, status["attempts_used"])
        self.assertIn("preflight blocked", status["stopped_reason"])
        self.assertTrue(status["manual_fallback_allowed"])

    def test_resource_guard_block_receipt_records_snapshot_and_policy(self) -> None:
        snapshot = {
            "ram_available_bytes": 20 * 1024**3,
            "swap_free_bytes": 80 * 1024**3,
            "gpu_free_bytes": 10 * 1024**3,
        }
        limits = ResourceLimits()

        def guard() -> dict[str, object]:
            raise ResourceGuardError(
                "available host RAM is below the diagnostic threshold",
                snapshot=snapshot,
                limits=limits,
            )

        result = source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=guard,
            runner=self._fake_runner,
            sampler_factory=FakeSampler,
        )
        attempt_dir = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "hunyuan/attempt-001"
        )
        receipt = json.loads((attempt_dir / "gpu_guard.json").read_text())
        status = source_ingestion_runner.source_status(self.source_id, self.root)

        self.assertEqual("blocked", result["status"])
        self.assertEqual(snapshot, receipt["preflight_details"]["snapshot"])
        self.assertEqual(
            limits.as_dict(), receipt["preflight_details"]["resource_policy"]
        )
        self.assertEqual(0, status["attempts_used"])
        self.assertFalse(status["can_start_attempt"])

    def test_feedback_unlocks_next_manual_attempt_only_after_operator_review(
        self,
    ) -> None:
        result = source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=lambda: {"guard_policy_version": "test"},
            runner=self._fake_runner,
            sampler_factory=FakeSampler,
        )
        source_ingestion_runner.record_operator_feedback(
            self.source_id,
            "attempt-001",
            "improved",
            "The panorama contains more useful wall context.",
            root=self.root,
        )
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(1, status["attempts_used"])
        self.assertFalse(status["awaiting_feedback"])
        self.assertTrue(status["can_start_attempt"])
        self.assertEqual("produced", result["status"])

    def test_manual_fallback_requires_explicit_stop_and_then_closes_inference(
        self,
    ) -> None:
        source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=lambda: (_ for _ in ()).throw(RuntimeError("guard blocked")),
            runner=self._fake_runner,
            sampler_factory=FakeSampler,
        )
        source_ingestion_runner.record_manual_fallback(
            self.source_id,
            "proceed_manual",
            "The local guard blocked this source's panorama run.",
            self.root,
        )
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertFalse(status["manual_fallback_allowed"])
        self.assertFalse(status["can_start_attempt"])

    def test_lock_contention_blocks_before_inference(self) -> None:
        with exclusive_gpu_job(self.root):
            result = source_ingestion_gpu.run_panorama_attempt(
                self.source_id,
                "A test interior panorama prompt.",
                root=self.root,
                runner=self._fake_runner,
                sampler_factory=FakeSampler,
                gpu_lock_timeout_seconds=0,
            )
        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "shared lock",
            source_ingestion_runner.source_status(self.source_id, self.root)[
                "stopped_reason"
            ],
        )

    def test_attempt_timeout_is_recorded_and_waits_for_feedback(self) -> None:
        def timeout(
            _command: list[str], **_arguments
        ) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired("panogen", 2)

        result = source_ingestion_gpu.run_panorama_attempt(
            self.source_id,
            "A test interior panorama prompt.",
            root=self.root,
            guard=lambda: {"guard_policy_version": "test"},
            runner=timeout,
            sampler_factory=FakeSampler,
            timeout_seconds=2,
        )
        self.assertEqual("timed_out", result["status"])
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        self.assertEqual(1, status["attempts_used"])
        self.assertTrue(status["awaiting_feedback"])

    def test_attempt_directory_overwrite_is_refused(self) -> None:
        attempt = (
            self.root
            / "godot_walk/source_library/sources"
            / self.source_id
            / "hunyuan/attempt-001"
        )
        attempt.mkdir(parents=True)
        with self.assertRaises(FileExistsError):
            source_ingestion_gpu.run_panorama_attempt(
                self.source_id,
                "A test interior panorama prompt.",
                root=self.root,
                runner=self._fake_runner,
            )

    def test_attempt_directory_symlink_escape_is_refused(self) -> None:
        source_dir = self.root / "godot_walk/source_library/sources" / self.source_id
        outside = self.root / "outside"
        outside.mkdir()
        (source_dir / "hunyuan").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(SourceLibraryError, "symlink"):
            source_ingestion_gpu.run_panorama_attempt(
                self.source_id,
                "A test interior panorama prompt.",
                root=self.root,
                runner=self._fake_runner,
            )

    def test_panogen_uses_pinned_python_and_offline_model_cache(self) -> None:
        environment = source_ingestion_gpu._panogen_environment()
        self.assertEqual("1", environment["HF_HUB_OFFLINE"])
        self.assertEqual("1", environment["TRANSFORMERS_OFFLINE"])
        self.assertEqual(
            "expandable_segments:True", environment["PYTORCH_CUDA_ALLOC_CONF"]
        )
        self.assertEqual(
            str(source_ingestion_gpu.HUNYUAN_CACHE), environment["HF_HOME"]
        )
        command = source_ingestion_gpu._panogen_command(
            self.video,
            self.root / "attempt-001",
            {
                "source_id": self.source_id,
                "seed_frame": {"sha256": "a" * 64},
                "source_video_sha256": "b" * 64,
                "source_manifest_sha256": "c" * 64,
                "prompt": "test",
                "width": 768,
                "height": 384,
                "diffusion_seed": 42,
                "offload_mode": "sequential_cpu",
                "true_cfg_scale": 1.0,
            },
            {"path": "guard.json", "sha256": "d" * 64},
            self.root,
        )
        self.assertEqual(str(source_ingestion_gpu.HUNYUAN_PYTHON), command[0])
        self.assertIn("--offload-mode", command)
        self.assertIn("sequential_cpu", command)
        self.assertIn("--no-cache", command)
        self.assertIn("--vae-tiling", command)

    def test_diagnostic_profile_is_recorded_and_propagated(self) -> None:
        _manifest, _events, entry = source_ingestion_runner.load_source(
            self.source_id, self.root
        )
        status = source_ingestion_runner.source_status(self.source_id, self.root)
        settings = source_ingestion_gpu._attempt_settings(
            self.source_id,
            entry,
            status["selected_seed"],
            "attempt-001",
            "A test interior panorama prompt.",
            512,
            256,
            42,
            "sequential_cpu",
            2700,
        )
        self.assertEqual("memory-diagnostic-512x256-v1", settings["diagnostic_profile"])
        self.assertEqual("sequential_cpu", settings["offload_mode"])
        self.assertFalse(settings["pipeline_cuda_move"])
        self.assertFalse(settings["cache_enabled"])
        self.assertTrue(settings["vae_tiling_enabled"])
        self.assertEqual(2700, settings["timeout_seconds"])
        self.assertEqual(512, settings["width"])
        self.assertEqual(256, settings["height"])

    def test_public_launcher_passes_sequential_profile_and_timeout(self) -> None:
        with (
            patch(
                "sys.argv",
                [
                    "run_source_hunyuan.py",
                    self.source_id,
                    "--prompt",
                    "A bounded diagnostic room.",
                    "--offload-mode",
                    "sequential_cpu",
                    "--timeout-seconds",
                    "2700",
                ],
            ),
            patch.object(
                run_source_hunyuan,
                "run_panorama_attempt",
                return_value={"status": "blocked"},
            ) as launch,
            redirect_stdout(io.StringIO()),
        ):
            exit_code = run_source_hunyuan.main()

        self.assertEqual(0, exit_code)
        launch.assert_called_once_with(
            self.source_id,
            "A bounded diagnostic room.",
            width=512,
            height=256,
            seed=42,
            offload_mode="sequential_cpu",
            timeout_seconds=2700,
        )

    def test_profile_rejects_resolution_or_timeout_outside_bounded_policy(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires 512x256"):
            source_ingestion_gpu._validate_settings(
                "A test interior panorama prompt.", 768, 384, 2700, "sequential_cpu"
            )
        with self.assertRaisesRegex(ValueError, "between 1 and 2700"):
            source_ingestion_gpu._validate_settings(
                "A test interior panorama prompt.", 512, 256, 2701, "sequential_cpu"
            )
        with self.assertRaisesRegex(ValueError, "only supports sequential_cpu"):
            source_ingestion_gpu._validate_settings(
                "A test interior panorama prompt.", 512, 256, 2700, "model_cpu"
            )

    def test_execution_guard_receipt_binds_effective_policy_and_start_sample(self):
        from source_ingestion_resource_guard import DEFAULT_LIMITS

        attempt_dir = self.root / "attempt"
        attempt_dir.mkdir()
        snapshot = {"ram_available_bytes": 40 * 1024**3, "gpu_free_bytes": 10 * 1024**3}
        receipt = source_ingestion_gpu._write_execution_guard(
            attempt_dir, "passed", snapshot, None, self.root
        )
        contents = json.loads((attempt_dir / "execution_guard.json").read_text())

        self.assertEqual("passed", contents["status"])
        self.assertEqual(DEFAULT_LIMITS.as_dict(), contents["resource_policy"])
        self.assertEqual(snapshot, contents["start_snapshot"])
        self.assertEqual(
            sha256_file(attempt_dir / "execution_guard.json"), receipt["sha256"]
        )


if __name__ == "__main__":
    unittest.main()
