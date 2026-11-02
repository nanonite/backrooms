"""Launch one child while sampling and enforcing the Hunyuan resource budget."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable
from typing import Any

from source_ingestion_resource_guard import (
    DEFAULT_LIMITS,
    ResourceGuardError,
    ResourceLimits,
    capture_resources,
    check_start_limits,
    external_compute_pids,
    runtime_stop_reason,
)


def run_guarded_process(
    command: list[str],
    *,
    cwd: str,
    environment: dict[str, str],
    timeout_seconds: int,
    on_start: Callable[[dict[str, Any]], None],
    limits: ResourceLimits = DEFAULT_LIMITS,
    snapshotter: Callable[[int | None], dict[str, Any]] = capture_resources,
    external_processes: Callable[[int], list[str]] = external_compute_pids,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    sample_period_seconds: float | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("Inference timeout must be positive")
    if timeout_seconds > limits.max_execution_seconds:
        raise ValueError("Requested timeout exceeds the inference policy limit")
    initial = snapshotter(None)
    try:
        check_start_limits(initial, limits)
    except ResourceGuardError as error:
        return _blocked_result(initial, limits, str(error))

    samples = [initial]
    return _execute_child(
        command,
        cwd,
        environment,
        timeout_seconds,
        on_start,
        initial,
        samples,
        limits,
        snapshotter,
        external_processes,
        popen,
        sleep,
        clock,
        sample_period_seconds or limits.sample_period_seconds,
    )


def _execute_child(
    command: list[str],
    cwd: str,
    environment: dict[str, str],
    timeout_seconds: int,
    on_start: Callable[[dict[str, Any]], None],
    initial: dict[str, Any],
    samples: list[dict[str, Any]],
    limits: ResourceLimits,
    snapshotter: Callable[[int | None], dict[str, Any]],
    external_processes: Callable[[int], list[str]],
    popen: Callable[..., subprocess.Popen[bytes]],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    sample_period: float,
) -> dict[str, Any]:
    start = clock()
    process = None
    stop_reason = None
    with (
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
        try:
            on_start(initial)
            process = popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            stop_reason = _monitor(
                process,
                initial,
                samples,
                limits,
                timeout_seconds,
                snapshotter,
                external_processes,
                sleep,
                clock,
                start,
                sample_period,
            )
            if stop_reason:
                _stop_process_group(process)
            return_code = process.wait()
        except OSError as error:
            return _failed_result(initial, samples, limits, str(error), start, clock)
        finally:
            if process is not None and process.poll() is None:
                _stop_process_group(process)
        stdout = _read_text(stdout_file)
        stderr = _read_text(stderr_file)
    status = "stopped_by_guard" if stop_reason else "complete"
    code = 124 if stop_reason else return_code
    return _result(
        status,
        code,
        stdout,
        stderr,
        initial,
        samples,
        limits,
        stop_reason,
        start,
        clock,
    )


def _monitor(
    process: subprocess.Popen[bytes],
    initial: dict[str, Any],
    samples: list[dict[str, Any]],
    limits: ResourceLimits,
    timeout_seconds: int,
    snapshotter: Callable[[int | None], dict[str, Any]],
    external_processes: Callable[[int], list[str]],
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    start: float,
    sample_period: float,
) -> str | None:
    while process.poll() is None:
        sleep(sample_period)
        if process.poll() is not None:
            break
        try:
            sample = snapshotter(process.pid)
            samples.append(sample)
            reason = runtime_stop_reason(
                sample, initial, limits, external_processes(process.pid)
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            return f"resource monitoring failed: {error}"
        if reason:
            return reason
        if clock() - start >= timeout_seconds:
            return "hard inference timeout reached"
    return None


def _blocked_result(
    sample: dict[str, Any], limits: ResourceLimits, reason: str
) -> dict[str, Any]:
    return {
        "status": "blocked",
        "return_code": 125,
        "stdout": "",
        "stderr": "",
        "stop_reason": reason,
        "resources": {
            **_resource_summary([sample], sample, limits),
            "start_snapshot": sample,
        },
    }


def _failed_result(
    initial: dict[str, Any],
    samples: list[dict[str, Any]],
    limits: ResourceLimits,
    reason: str,
    start: float,
    clock: Callable[[], float],
) -> dict[str, Any]:
    return _result(
        "failed", 127, "", reason, initial, samples, limits, reason, start, clock
    )


def _result(
    status: str,
    return_code: int,
    stdout: str,
    stderr: str,
    initial: dict[str, Any],
    samples: list[dict[str, Any]],
    limits: ResourceLimits,
    stop_reason: str | None,
    start: float,
    clock: Callable[[], float],
) -> dict[str, Any]:
    return {
        "status": status,
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "stop_reason": stop_reason,
        "elapsed_seconds": round(clock() - start, 3),
        "samples": samples,
        "resources": _resource_summary(samples, initial, limits),
    }


def _resource_summary(
    samples: list[dict[str, Any]], initial: dict[str, Any], limits: ResourceLimits
) -> dict[str, Any]:
    return {
        "policy": limits.as_dict(),
        "sample_count": len(samples),
        "peak_process_group_rss_bytes": max(
            sample["process_group_rss_bytes"] for sample in samples
        ),
        "peak_gpu_memory_used_bytes": max(
            sample["gpu_used_bytes"] for sample in samples
        ),
        "minimum_gpu_free_bytes": min(sample["gpu_free_bytes"] for sample in samples),
        "minimum_ram_available_bytes": min(
            sample["ram_available_bytes"] for sample in samples
        ),
        "minimum_swap_free_bytes": min(sample["swap_free_bytes"] for sample in samples),
        "swap_free_at_start_bytes": initial["swap_free_bytes"],
        "gpu_free_at_start_bytes": initial["gpu_free_bytes"],
    }


def _read_text(stream: Any) -> str:
    stream.seek(0)
    return stream.read().decode("utf-8", errors="replace")


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    for process_signal, grace_seconds in (
        (signal.SIGINT, 5),
        (signal.SIGTERM, 5),
        (signal.SIGKILL, 0),
    ):
        try:
            os.killpg(process.pid, process_signal)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            continue
