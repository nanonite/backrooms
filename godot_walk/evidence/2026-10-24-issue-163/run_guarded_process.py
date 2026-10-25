"""Run local Hunyuan inference with GPU, memory, and time limits."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
GIB = 1024**3
MIN_START_RAM = 18 * GIB
MIN_START_VRAM_MIB = 8192
MIN_RAM = 4 * GIB
MIN_SWAP_FREE = 16 * GIB
MIN_VRAM_MIB = 2048
SAMPLE_SECONDS = 1


def main() -> int:
    args = _arguments()
    command = _command_after_separator(args.command)
    initial = _snapshot()
    _check_start_headroom(initial)
    run = _run(command, args, initial)
    _write_json(args.status, run)
    print(f"{run['status']}: {run['exit_code']} ({run['stop_reason'] or 'command ended'})")
    return int(run["exit_code"])


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=int, required=True)
    parser.add_argument("--cwd", type=Path, default=ROOT)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def _command_after_separator(command: list[str]) -> list[str]:
    values = command[1:] if command and command[0] == "--" else command
    if not values:
        raise ValueError("A command is required after --")
    return values


def _check_start_headroom(initial: dict[str, Any]) -> None:
    sys.path.insert(0, str(ROOT / "godot_walk/scripts"))
    from psx_design_round_resources import check_capture_headroom

    check_capture_headroom()
    if initial["ram_available_bytes"] < MIN_START_RAM:
        raise RuntimeError("Inference preflight blocked: less than 18 GiB RAM available")
    if initial["gpu_free_mib"] < MIN_START_VRAM_MIB:
        raise RuntimeError("Inference preflight blocked: less than 8 GiB VRAM free")
    if initial["swap_free_bytes"] < MIN_SWAP_FREE:
        raise RuntimeError("Inference preflight blocked: less than 16 GiB swap free")


def _run(
    command: list[str], args: argparse.Namespace, initial: dict[str, Any]
) -> dict[str, Any]:
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.samples.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    deadline = start + args.timeout_seconds
    stop_reason = None
    samples: list[dict[str, Any]] = [initial]
    with args.log.open("wb") as output:
        process = subprocess.Popen(
            command,
            cwd=args.cwd,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        _append_jsonl(args.samples, initial)
        while process.poll() is None:
            time.sleep(SAMPLE_SECONDS)
            if process.poll() is not None:
                break
            sample = _snapshot(process.pid)
            samples.append(sample)
            _append_jsonl(args.samples, sample)
            stop_reason = _runtime_stop_reason(sample, process.pid)
            if stop_reason is None and time.monotonic() >= deadline:
                stop_reason = "hard timeout reached"
            if stop_reason:
                _stop_process_group(process)
                break
        exit_code = process.wait()
    if stop_reason:
        exit_code = 124
    return _run_record(command, start, exit_code, stop_reason, samples)


def _runtime_stop_reason(sample: dict[str, Any], process_group: int) -> str | None:
    if sample["ram_available_bytes"] < MIN_RAM:
        return "host available RAM fell below 4 GiB"
    if sample["swap_free_bytes"] < MIN_SWAP_FREE:
        return "free swap fell below 16 GiB"
    if sample["gpu_free_mib"] < MIN_VRAM_MIB:
        return f"free VRAM fell below {MIN_VRAM_MIB} MiB"
    external = _external_compute_pids(process_group)
    if external:
        return "external GPU compute process appeared: " + ",".join(external)
    return None


def _snapshot(process_group: int | None = None) -> dict[str, Any]:
    memory = _memory_values()
    gpu = _gpu_values()
    rss = _group_rss_kib(process_group) if process_group is not None else 0
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **memory,
        **gpu,
        "process_group_rss_kib": rss,
    }


def _memory_values() -> dict[str, int]:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key in {"MemAvailable", "SwapFree"}:
            values[key] = int(value.split()[0]) * 1024
    if set(values) != {"MemAvailable", "SwapFree"}:
        raise RuntimeError("Could not read MemAvailable and SwapFree")
    return {
        "ram_available_bytes": values["MemAvailable"],
        "swap_free_bytes": values["SwapFree"],
    }


def _gpu_values() -> dict[str, int]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=memory.free,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    free, used, utilization = (int(item.strip()) for item in result.stdout.split(","))
    return {"gpu_free_mib": free, "gpu_used_mib": used, "gpu_utilization_pct": utilization}


def _group_rss_kib(process_group: int | None) -> int:
    if process_group is None:
        return 0
    result = subprocess.run(
        ["ps", "-eo", "pgid=,rss="], capture_output=True, text=True, check=True
    )
    return sum(
        int(rss)
        for row in result.stdout.splitlines()
        if len(fields := row.split()) == 2
        and int(fields[0]) == process_group
        for rss in (fields[1],)
    )


def _external_compute_pids(process_group: int) -> list[str]:
    result = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=True,
    )
    external = []
    for value in result.stdout.splitlines():
        pid_text = value.strip()
        if not pid_text:
            continue
        try:
            same_group = os.getpgid(int(pid_text)) == process_group
        except (ProcessLookupError, ValueError):
            same_group = False
        if not same_group:
            external.append(pid_text)
    return external


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    for sig, grace in ((signal.SIGINT, 15), (signal.SIGTERM, 10), (signal.SIGKILL, 0)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def _run_record(
    command: list[str],
    start: float,
    exit_code: int,
    stop_reason: str | None,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    keys = ("process_group_rss_kib", "gpu_used_mib", "ram_available_bytes")
    peaks = {key: max((sample[key] for sample in samples), default=0) for key in keys[:2]}
    minima = {
        key: min((sample[key] for sample in samples), default=0)
        for key in ("gpu_free_mib", "ram_available_bytes", "swap_free_bytes")
    }
    return {
        "command": command,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "exit_code": exit_code,
        "status": "stopped_by_guard" if stop_reason else "complete" if exit_code == 0 else "failed",
        "stop_reason": stop_reason,
        "peak_process_group_rss_kib": peaks["process_group_rss_kib"],
        "peak_gpu_used_mib": peaks["gpu_used_mib"],
        "minimum_gpu_free_mib": minima["gpu_free_mib"],
        "minimum_ram_available_bytes": minima["ram_available_bytes"],
        "minimum_swap_free_bytes": minima["swap_free_bytes"],
        "sample_count": len(samples),
    }


def _append_jsonl(path: Path, sample: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(sample, sort_keys=True) + "\n")


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f"INFERENCE_GUARD_REFUSED: {error}", file=sys.stderr)
        raise SystemExit(1)
