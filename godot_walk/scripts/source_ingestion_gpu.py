"""Run exactly one guarded Hunyuan attempt for a reviewed source and seed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gpu_job_lock import GpuJobLockError, exclusive_gpu_job
from register_video_sources import append_event
from source_ingestion_policy import (
    WorkflowGateError,
    evaluate_workflow,
    require_attempt_start,
)
from source_ingestion_runner import (
    _reject_symlink_components,
    _source_lock,
    load_source,
)
from video_source_library import (
    LIBRARY,
    ROOT,
    SourceLibraryError,
    sha256_file,
    write_new_json,
)

SCRIPTS = ROOT / "godot_walk/scripts"
HUNYUAN_RUNTIME = Path("/mnt/sharedOs/backrooms-track-a-runtime/HunyuanWorld-1.0")
HUNYUAN_PYTHON = Path("/mnt/sharedOs/backrooms-track-a-runtime/hunyuan-env/bin/python")
HUNYUAN_CACHE = Path("/mnt/sharedOs/backrooms-track-a-runtime/hf-cache")
HUNYUAN_COMMIT = "57fa9f3a79eae1079c279968cdb9d82c75fa7c86"
DEFAULT_TIMEOUT_SECONDS = 2700
DIAGNOSTIC_WIDTH = 512
DIAGNOSTIC_HEIGHT = 256
DIAGNOSTIC_PROFILE = "memory-diagnostic-512x256-v1"
OFFLOAD_MODE = "sequential_cpu"


def run_panorama_attempt(
    source_id: str,
    prompt: str,
    *,
    width: int = DIAGNOSTIC_WIDTH,
    height: int = DIAGNOSTIC_HEIGHT,
    seed: int = 42,
    offload_mode: str = OFFLOAD_MODE,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    gpu_lock_timeout_seconds: int = 600,
    root: Path = ROOT,
    guard: Callable[[], dict[str, Any]] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sampler_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    _validate_settings(prompt, width, height, timeout_seconds, offload_mode)
    with _source_lock(source_id, root):
        return _run_locked_source_attempt(
            source_id,
            prompt,
            width,
            height,
            seed,
            offload_mode,
            timeout_seconds,
            gpu_lock_timeout_seconds,
            root,
            guard,
            runner,
            sampler_factory,
        )


def _run_locked_source_attempt(
    source_id: str,
    prompt: str,
    width: int,
    height: int,
    seed: int,
    offload_mode: str,
    timeout_seconds: int,
    gpu_lock_timeout_seconds: int,
    root: Path,
    guard: Callable[[], dict[str, Any]] | None,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    sampler_factory: Callable[[], Any] | None,
) -> dict[str, Any]:
    manifest, events, entry = load_source(source_id, root)
    state = evaluate_workflow(manifest, events)
    require_attempt_start(state)
    if runner is subprocess.run:
        _validate_local_runtime()
    attempt_id = _next_attempt_id(state.attempts_used, events)
    seed_frame = _validated_seed(state.selected_seed, entry, root)
    attempt_dir = _create_attempt_dir(root, source_id, attempt_id)
    settings = _attempt_settings(
        source_id,
        entry,
        state.selected_seed,
        attempt_id,
        prompt,
        width,
        height,
        seed,
        offload_mode,
        timeout_seconds,
    )
    settings["run_id"] = f"run-{uuid.uuid4().hex}"
    write_new_json(attempt_dir / "attempt_config.json", settings)
    return _run_guarded_attempt(
        source_id,
        entry,
        attempt_id,
        attempt_dir,
        seed_frame,
        settings,
        timeout_seconds,
        root,
        guard,
        runner,
        sampler_factory,
        gpu_lock_timeout_seconds,
    )


def _create_attempt_dir(root: Path, source_id: str, attempt_id: str) -> Path:
    parent = root / LIBRARY / "sources" / source_id / "hunyuan"
    attempt_dir = parent / attempt_id
    _reject_symlink_components(attempt_dir, root)
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(attempt_dir, root)
    attempt_dir.mkdir()
    return attempt_dir


def _next_attempt_id(attempts_used: int, events: list[dict[str, Any]]) -> str:
    retry_authorization = next(
        (
            event["payload"]
            for event in reversed(events)
            if event["event_type"] == "hunyuan_preflight_retry_approved"
        ),
        None,
    )
    if retry_authorization is not None:
        retry_attempt_id = retry_authorization["retry_attempt_id"]
        retry_started = any(
            event["event_type"] == "hunyuan_attempt_started"
            and event["payload"].get("attempt_id") == retry_attempt_id
            for event in events
        )
        if not retry_started:
            return retry_attempt_id
    return f"attempt-{attempts_used + 1:03d}"


def _validate_settings(
    prompt: str, width: int, height: int, timeout: int, offload_mode: str
) -> None:
    if not prompt.strip():
        raise ValueError("A source-specific panorama prompt is required")
    if width < 512 or height < 256 or width % 64 or height % 64:
        raise ValueError("Panogen dimensions must meet minimums and be multiples of 64")
    if (width, height) != (DIAGNOSTIC_WIDTH, DIAGNOSTIC_HEIGHT):
        raise ValueError(
            f"The bounded memory diagnostic profile requires {DIAGNOSTIC_WIDTH}x{DIAGNOSTIC_HEIGHT}"
        )
    if offload_mode != OFFLOAD_MODE:
        raise ValueError("The bounded launcher only supports sequential_cpu offload")
    from source_ingestion_resource_guard import DEFAULT_LIMITS

    if timeout < 1 or timeout > DEFAULT_LIMITS.max_execution_seconds:
        raise ValueError(
            f"Panogen timeout must be between 1 and {DEFAULT_LIMITS.max_execution_seconds} seconds"
        )


def _validated_seed(
    seed: dict[str, Any] | None, entry: dict[str, Any], root: Path
) -> Path:
    if seed is None or seed.get("source_video_sha256") != entry["source_sha256"]:
        raise WorkflowGateError("Select a current direct-source frame before Hunyuan")
    path = root / seed["path"]
    if not path.is_file() or path.is_symlink() or sha256_file(path) != seed["sha256"]:
        raise SourceLibraryError("Selected seed frame is missing or changed")
    return path


def _attempt_settings(
    source_id: str,
    entry: dict[str, Any],
    seed: dict[str, Any],
    attempt_id: str,
    prompt: str,
    width: int,
    height: int,
    seed_number: int,
    offload_mode: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    from source_ingestion_resource_guard import DEFAULT_LIMITS

    return {
        "schema_version": 2,
        "diagnostic_profile": DIAGNOSTIC_PROFILE,
        "source_id": source_id,
        "source_video_sha256": entry["source_sha256"],
        "source_manifest_sha256": entry["manifest_sha256"],
        "attempt_id": attempt_id,
        "seed_frame": seed,
        "model": "HunyuanWorld-1.0 Panogen local runtime",
        "model_commit": HUNYUAN_COMMIT,
        "runtime_python": HUNYUAN_PYTHON.as_posix(),
        "model_cache": HUNYUAN_CACHE.as_posix(),
        "model_cache_offline": True,
        "pytorch_cuda_alloc_conf": "expandable_segments:True",
        "offload_mode": offload_mode,
        "offload_api": "Diffusers DiffusionPipeline.enable_sequential_cpu_offload",
        "offload_hook_replacement": "Diffusers remove_all_hooks within offload method",
        "pipeline_cuda_move": False,
        "vae_tiling_enabled": True,
        "cache_enabled": False,
        "timeout_seconds": timeout_seconds,
        "resource_policy": DEFAULT_LIMITS.as_dict(),
        "runtime_packages": {
            "torch": "2.5.0",
            "diffusers": "0.34.0",
            "accelerate": "1.6.0",
            "transformers": "4.51.0",
        },
        "prompt": prompt,
        "width": width,
        "height": height,
        "fov_degrees": 80.0,
        "fov_source": "Pinned upstream Panogen default; source camera FOV unmeasured",
        "diffusion_seed": seed_number,
        "fp8_attention": True,
        "fp8_gemm": True,
        "true_cfg_scale": 1.0,
    }


def _run_guarded_attempt(
    source_id: str,
    entry: dict[str, Any],
    attempt_id: str,
    attempt_dir: Path,
    seed_frame: Path,
    settings: dict[str, Any],
    timeout: int,
    root: Path,
    guard: Callable[[], dict[str, Any]] | None,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    sampler_factory: Callable[[], Any] | None,
    gpu_lock_timeout_seconds: int,
) -> dict[str, Any]:
    try:
        with exclusive_gpu_job(root, timeout_seconds=gpu_lock_timeout_seconds):
            try:
                preflight = guard() if guard else _capture_preflight()
            except (RuntimeError, OSError, subprocess.SubprocessError) as error:
                details = {
                    "snapshot": getattr(error, "snapshot", None),
                    "resource_policy": (
                        error.limits.as_dict()
                        if getattr(error, "limits", None) is not None
                        else None
                    ),
                }
                return _record_guard_block(
                    source_id,
                    attempt_id,
                    attempt_dir,
                    str(error),
                    root,
                    preflight_details=details,
                )
            guard_record = _write_guard_receipt(
                attempt_dir, source_id, entry, seed_frame, preflight, root
            )
            append_event(source_id, "hunyuan_guard_passed", guard_record, root)
            return _invoke_panogen(
                source_id,
                attempt_id,
                attempt_dir,
                seed_frame,
                settings,
                guard_record,
                timeout,
                root,
                runner,
                sampler_factory,
            )
    except GpuJobLockError as error:
        return _record_guard_block(source_id, attempt_id, attempt_dir, str(error), root)


def _capture_preflight() -> dict[str, Any]:
    sys.path.insert(0, str(SCRIPTS))
    from psx_design_round_resources import check_capture_headroom
    from source_ingestion_resource_guard import (
        DEFAULT_LIMITS,
        capture_resources,
        check_start_limits,
    )

    baseline = check_capture_headroom()
    snapshot = capture_resources()
    check_start_limits(snapshot)
    return {
        **baseline,
        "hunyuan_resource_policy": DEFAULT_LIMITS.as_dict(),
        "hunyuan_start_snapshot": snapshot,
    }


def _validate_local_runtime() -> None:
    if not HUNYUAN_PYTHON.is_file() or not HUNYUAN_CACHE.is_dir():
        raise FileNotFoundError("Pinned Hunyuan Python environment or cache is missing")
    revision = subprocess.run(
        ["git", "-C", str(HUNYUAN_RUNTIME), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()
    if revision != HUNYUAN_COMMIT:
        raise SourceLibraryError("HunyuanWorld runtime differs from its pinned commit")
    subprocess.run(
        [
            str(HUNYUAN_PYTHON),
            "-c",
            "import importlib.metadata as m; expected={'torch':'2.5.0','diffusers':'0.34.0','accelerate':'1.6.0','transformers':'4.51.0'}; actual={name:m.version(name) for name in expected}; print(actual); raise SystemExit(actual != expected)",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write_guard_receipt(
    attempt_dir: Path,
    source_id: str,
    entry: dict[str, Any],
    seed_frame: Path,
    preflight: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    data = {
        "status": "passed",
        "source_id": source_id,
        "source_video_sha256": entry["source_sha256"],
        "source_manifest_sha256": entry["manifest_sha256"],
        "seed_frame_sha256": sha256_file(seed_frame),
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "preflight": preflight,
    }
    path = attempt_dir / "gpu_guard.json"
    write_new_json(path, data)
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def _record_guard_block(
    source_id: str,
    attempt_id: str,
    attempt_dir: Path,
    reason: str,
    root: Path,
    execution_receipt: dict[str, str] | None = None,
    preflight_details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        "status": "blocked",
        "source_id": source_id,
        "attempt_id": attempt_id,
        "reason": reason,
        "execution_guard_receipt": execution_receipt,
        "preflight_details": preflight_details,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = attempt_dir / "gpu_guard.json"
    if not path.exists():
        write_new_json(path, data)
    receipt = {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
    append_event(
        source_id,
        "hunyuan_preflight_blocked",
        {
            "reason": reason,
            "guard_receipt": receipt,
            "execution_guard_receipt": execution_receipt,
            "preflight_details": preflight_details,
        },
        root,
    )
    return {**data, "status": "blocked"}


def _invoke_panogen(
    source_id: str,
    attempt_id: str,
    attempt_dir: Path,
    seed_frame: Path,
    settings: dict[str, Any],
    guard_receipt: dict[str, str],
    timeout: int,
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    sampler_factory: Callable[[], Any] | None,
) -> dict[str, Any]:
    command = _panogen_command(seed_frame, attempt_dir, settings, guard_receipt, root)
    _verify_candidate_identity(source_id, settings, root)
    return _run_process(
        source_id,
        attempt_id,
        attempt_dir,
        command,
        timeout,
        root,
        runner,
        sampler_factory,
        settings,
        guard_receipt,
    )


def _verify_candidate_identity(
    source_id: str, settings: dict[str, Any], root: Path
) -> None:
    _, _, entry = load_source(source_id, root)
    if (
        entry["source_sha256"] != settings["source_video_sha256"]
        or entry["manifest_sha256"] != settings["source_manifest_sha256"]
    ):
        raise SourceLibraryError("Source identity changed before Hunyuan invocation")


def _panogen_command(
    seed_frame: Path,
    attempt_dir: Path,
    settings: dict[str, Any],
    guard_receipt: dict[str, str],
    root: Path,
) -> list[str]:
    return [
        str(HUNYUAN_PYTHON),
        str(SCRIPTS / "run_source_panogen.py"),
        "--source-id",
        settings["source_id"],
        "--seed-frame",
        str(seed_frame),
        "--seed-frame-sha256",
        settings["seed_frame"]["sha256"],
        "--source-video-sha256",
        settings["source_video_sha256"],
        "--source-manifest-sha256",
        settings["source_manifest_sha256"],
        "--guard-receipt",
        str(root / guard_receipt["path"]),
        "--guard-receipt-sha256",
        guard_receipt["sha256"],
        "--output-dir",
        str(attempt_dir / "panorama"),
        "--prompt",
        settings["prompt"],
        "--width",
        str(settings["width"]),
        "--height",
        str(settings["height"]),
        "--seed",
        str(settings["diffusion_seed"]),
        "--offload-mode",
        settings["offload_mode"],
        "--no-cache",
        "--vae-tiling",
        "--fp8-attention",
        "--fp8-gemm",
        "--true-cfg-scale",
        str(settings["true_cfg_scale"]),
    ]


def _run_process(
    source_id: str,
    attempt_id: str,
    attempt_dir: Path,
    command: list[str],
    timeout: int,
    root: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    sampler_factory: Callable[[], Any] | None,
    settings: dict[str, Any],
    guard_receipt: dict[str, str],
) -> dict[str, Any]:
    started = time.monotonic()
    if runner is subprocess.run:
        return _run_monitored_process(
            source_id,
            attempt_id,
            attempt_dir,
            command,
            timeout,
            root,
            settings,
            guard_receipt,
            started,
        )

    sampler = sampler_factory() if sampler_factory else _resource_sampler()
    sampler.start()
    try:
        _record_attempt_started(
            source_id, attempt_id, settings, guard_receipt, attempt_dir, root
        )
        completed = runner(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_panogen_environment(),
        )
        status, return_code = _process_status(completed.returncode, attempt_dir)
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as error:
        status, return_code = "timed_out", 124
        stdout, stderr = _timeout_text(error.stdout), _timeout_text(error.stderr)
    except OSError as error:
        status, return_code = "failed", 127
        stdout, stderr = "", str(error)
    finally:
        resources = sampler.stop()
    result = _write_attempt_result(
        attempt_dir,
        status,
        return_code,
        stdout,
        stderr,
        resources,
        time.monotonic() - started,
        root,
    )
    attempt_config = json.loads(
        (attempt_dir / "attempt_config.json").read_text(encoding="utf-8")
    )
    append_event(
        source_id,
        "hunyuan_attempt_result",
        {"attempt_id": attempt_id, "run_id": attempt_config["run_id"], **result},
        root,
    )
    return result


def _run_monitored_process(
    source_id: str,
    attempt_id: str,
    attempt_dir: Path,
    command: list[str],
    timeout: int,
    root: Path,
    settings: dict[str, Any],
    guard_receipt: dict[str, str],
    started: float,
) -> dict[str, Any]:
    from source_ingestion_process import run_guarded_process
    from source_ingestion_resource_guard import DEFAULT_LIMITS

    def record_start(snapshot: dict[str, Any]) -> None:
        receipt = _write_execution_guard(attempt_dir, "passed", snapshot, None, root)
        _record_attempt_started(
            source_id, attempt_id, settings, guard_receipt, attempt_dir, root, receipt
        )

    try:
        execution = run_guarded_process(
            command,
            cwd=str(root),
            environment=_panogen_environment(),
            timeout_seconds=timeout,
            on_start=record_start,
            limits=DEFAULT_LIMITS,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        receipt = _write_execution_guard(attempt_dir, "blocked", None, str(error), root)
        return _record_guard_block(
            source_id, attempt_id, attempt_dir, str(error), root, receipt
        )

    if execution["status"] == "blocked":
        receipt = _write_execution_guard(
            attempt_dir,
            "blocked",
            execution["resources"].get("start_snapshot"),
            execution["stop_reason"],
            root,
        )
        return _record_guard_block(
            source_id, attempt_id, attempt_dir, execution["stop_reason"], root, receipt
        )

    samples = execution.pop("samples")
    sample_path = attempt_dir / "resource_samples.jsonl"
    sample_text = "".join(json.dumps(item, sort_keys=True) + "\n" for item in samples)
    _write_new_text(sample_path, sample_text)
    resources = {
        **execution["resources"],
        "sample_file": {
            "path": sample_path.relative_to(root).as_posix(),
            "sha256": sha256_file(sample_path),
        },
        "stop_reason": execution["stop_reason"],
    }
    return_code = execution["return_code"]
    if execution["status"] == "stopped_by_guard":
        status = (
            "timed_out"
            if execution["stop_reason"] == "hard inference timeout reached"
            else "resource_stopped"
        )
    else:
        status, return_code = _process_status(return_code, attempt_dir)
    return _finalize_attempt_result(
        source_id,
        attempt_id,
        attempt_dir,
        settings,
        status,
        return_code,
        execution["stdout"],
        execution["stderr"],
        resources,
        execution["elapsed_seconds"],
        root,
    )


def _record_attempt_started(
    source_id: str,
    attempt_id: str,
    settings: dict[str, Any],
    guard_receipt: dict[str, str],
    attempt_dir: Path,
    root: Path,
    execution_receipt: dict[str, str] | None = None,
) -> None:
    append_event(
        source_id,
        "hunyuan_attempt_started",
        {
            "attempt_id": attempt_id,
            "run_id": settings["run_id"],
            "source_video_sha256": settings["source_video_sha256"],
            "source_manifest_sha256": settings["source_manifest_sha256"],
            "seed_frame_sha256": settings["seed_frame"]["sha256"],
            "config_sha256": sha256_file(attempt_dir / "attempt_config.json"),
            "guard_receipt": guard_receipt,
            "execution_guard_receipt": execution_receipt,
        },
        root,
    )


def _write_execution_guard(
    attempt_dir: Path,
    status: str,
    snapshot: dict[str, Any] | None,
    reason: str | None,
    root: Path,
) -> dict[str, str]:
    from source_ingestion_resource_guard import DEFAULT_LIMITS

    path = attempt_dir / "execution_guard.json"
    write_new_json(
        path,
        {
            "status": status,
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            "resource_policy": DEFAULT_LIMITS.as_dict(),
            "start_snapshot": snapshot,
            "reason": reason,
        },
    )
    return {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}


def _finalize_attempt_result(
    source_id: str,
    attempt_id: str,
    attempt_dir: Path,
    settings: dict[str, Any],
    status: str,
    return_code: int,
    stdout: str,
    stderr: str,
    resources: dict[str, Any],
    elapsed: float,
    root: Path,
) -> dict[str, Any]:
    result = _write_attempt_result(
        attempt_dir, status, return_code, stdout, stderr, resources, elapsed, root
    )
    append_event(
        source_id,
        "hunyuan_attempt_result",
        {"attempt_id": attempt_id, "run_id": settings["run_id"], **result},
        root,
    )
    return result


def _resource_sampler():
    sys.path.insert(0, str(SCRIPTS))
    from psx_design_round_resources import PeakResourceSampler

    return PeakResourceSampler()


def _panogen_environment() -> dict[str, str]:
    environment = os.environ.copy()
    hub_cache = HUNYUAN_CACHE / "hub"
    environment.update(
        {
            "HF_HOME": str(HUNYUAN_CACHE),
            "HF_HUB_CACHE": str(hub_cache),
            "TRANSFORMERS_CACHE": str(hub_cache),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
    return environment


def _process_status(return_code: int, attempt_dir: Path) -> tuple[str, int]:
    if return_code != 0:
        return "failed", return_code
    if not (attempt_dir / "panorama/panorama.png").is_file():
        return "failed", return_code
    return "produced", return_code


def _write_attempt_result(
    attempt_dir: Path,
    status: str,
    return_code: int,
    stdout: str,
    stderr: str,
    resources: dict[str, Any],
    elapsed: float,
    root: Path,
) -> dict[str, Any]:
    _write_new_text(attempt_dir / "stdout.log", stdout)
    _write_new_text(attempt_dir / "stderr.log", stderr)
    outputs = _hash_panorama_outputs(attempt_dir / "panorama", root)
    data = {
        "status": status,
        "return_code": return_code,
        "elapsed_seconds": round(elapsed, 3),
        "resources": resources,
        "outputs": outputs,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_new_json(attempt_dir / "attempt_result.json", data)
    return data


def _hash_panorama_outputs(directory: Path, root: Path) -> list[dict[str, str]]:
    if not directory.is_dir():
        return []
    outputs = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise SourceLibraryError("Panogen output may not contain symlinks")
        if path.is_file():
            outputs.append(
                {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
            )
    return outputs


def _timeout_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


def _write_new_text(path: Path, content: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
