#!/usr/bin/env python3
"""A pinned, timestamped snapshot of the machine the pipeline runs on.

Everything the budget depends on is read here once and carried in one object,
so a reviewer can check "was the box the same box" without re-running
anything. Project notes guessed at an RTX 4070 Ti and 64 GB of RAM; this module
records what is actually installed, because those guesses are exactly the kind
of claim that silently stops being true.

Version strings are pinned in :data:`TOOL_SPECS` rather than discovered, so the
report names the exact command that produced each string.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from resource_probe import (
    FilesystemReading,
    GpuProcess,
    GpuReading,
    MemoryReading,
    filesystem_usage,
    nvidia_driver_version,
    query_gpu_processes,
    query_gpus,
    read_memory,
)

#: The interpreter that owns nerfstudio. Pinned because the system python3 has
#: no torch: measuring with the wrong interpreter reports a machine that does
#: not exist.
NERFSTUDIO_PYTHON = "/home/user/anaconda3/envs/nerfstudio/bin/python"

#: Directories searched before PATH. The setup script installs into ~/.local/bin
#: and the engine binary was downloaded by hand, so neither is on PATH.
EXTRA_BIN_DIRS: tuple[str, ...] = (str(Path.home() / ".local/bin"), str(Path.home() / "Downloads"))

#: Godot has no system package here; this is the pinned build.
GODOT_BINARY = str(Path.home() / "Downloads/Godot_v4.6.3-stable_linux.x86_64")

VERSION_QUERY_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class ToolSpec:
    """How to ask one tool for its version, and how to read the answer."""

    name: str
    argv: list[str]
    pattern: str = ""
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolInfo:
    """One tool's presence and version, or why it is missing."""

    name: str
    version: str
    command: list[str]
    available: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "command": list(self.command),
            "available": self.available,
        }


#: Reports the distribution version, which is what a "nerfstudio 1.1.5" claim
#: has to be checked against -- the module itself exposes no __version__.
_NERFSTUDIO_VERSION_SCRIPT = (
    "import importlib.metadata as m;print(m.version('nerfstudio'))"
)

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("nvidia-smi", ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]),
    ToolSpec("ffmpeg", ["ffmpeg", "-version"], r"ffmpeg version (\S+)"),
    ToolSpec("colmap", ["colmap", "-h"], r"COLMAP (\S+)"),
    ToolSpec("glomap", ["glomap", "-h"], r"glomap (\S+)"),
    ToolSpec("brush", ["brush", "--version"]),
    ToolSpec("blender", ["blender", "--version"], r"Blender (\S+)"),
    ToolSpec("godot", [GODOT_BINARY, "--version"]),
    ToolSpec("nerfstudio", [NERFSTUDIO_PYTHON, "-c", _NERFSTUDIO_VERSION_SCRIPT]),
    ToolSpec("python3", ["python3", "--version"]),
)


def resolve_binary(name: str, candidates: tuple[str, ...] = ()) -> str:
    """Return the first usable path for ``name``.

    Search order: explicit candidates, :data:`EXTRA_BIN_DIRS`, then ``PATH``.
    Returns the bare name when nothing is found, so the version query fails with
    a recognisable "not found" rather than silently reporting an unknown version.
    """
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for directory in EXTRA_BIN_DIRS:
        candidate = Path(directory) / name
        if candidate.exists():
            return str(candidate)
    return shutil.which(name) or name


def probe_tool(spec: ToolSpec) -> ToolInfo:
    """Run one version query and return what it said, or why it could not run."""
    command = [resolve_binary(spec.argv[0], spec.candidates), *spec.argv[1:]]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=VERSION_QUERY_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return ToolInfo(spec.name, f"unavailable: {error.__class__.__name__}", command, False)
    output = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(spec.pattern, output) if spec.pattern else None
    version = match.group(1) if match else _first_meaningful_line(output)
    return ToolInfo(spec.name, version, command, available=version != "")


def _first_meaningful_line(text: str) -> str:
    """Return the first non-blank line, stripped; empty string when there is none."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def detect_tool_versions(specs: tuple[ToolSpec, ...] = TOOL_SPECS) -> dict[str, str]:
    """Return ``{tool: version}`` for every spec, using ``"missing"`` when absent."""
    return {spec.name: probe_tool(spec).version for spec in specs}


def cuda_toolchain_versions() -> dict[str, str]:
    """Return torch/CUDA versions from the pinned nerfstudio interpreter.

    Raises nothing: an unavailable toolchain is reported as an empty mapping so
    the preflight can turn it into an actionable message instead of a traceback.
    """
    script = (
        "import importlib.metadata as m;"
        "print(m.version('torch'));"
        "import torch;print(torch.version.cuda or 'none');"
        "print('yes' if torch.cuda.is_available() else 'no')"
    )
    try:
        completed = subprocess.run(
            [NERFSTUDIO_PYTHON, "-c", script],
            capture_output=True,
            text=True,
            timeout=VERSION_QUERY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 3:
        return {}
    return {"torch": lines[0], "torch_cuda": lines[1], "cuda_available": lines[2]}


@dataclass(frozen=True)
class HardwareSnapshot:
    """The machine as measured, plus what it needs to be reproducible."""

    hostname: str
    kernel: str
    os_release: str
    cpu_model: str
    cpu_threads: int
    gpus: tuple[GpuReading, ...]
    vram_holders: tuple[GpuProcess, ...]
    memory: MemoryReading
    filesystems: tuple[FilesystemReading, ...]
    driver_version: str
    tools: dict[str, str]
    cuda: dict[str, str]
    interpreter: str = sys.executable

    @property
    def primary_gpu(self) -> GpuReading | None:
        return self.gpus[0] if self.gpus else None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready view for the machine-readable report."""
        gpu = self.primary_gpu
        return {
            "hostname": self.hostname,
            "kernel": self.kernel,
            "os_release": self.os_release,
            "cpu_model": self.cpu_model,
            "cpu_threads": self.cpu_threads,
            "driver_version": self.driver_version,
            "interpreter": self.interpreter,
            "gpu": {
                "name": gpu.name,
                "total_vram_bytes": gpu.total_vram_bytes,
                "free_vram_bytes": gpu.free_vram_bytes,
                "used_vram_bytes": gpu.used_vram_bytes,
                "utilization_percent": gpu.utilization_percent,
                "count": len(self.gpus),
            }
            if gpu
            else None,
            "vram_holders": [
                {"pid": p.pid, "name": p.process_name, "used_bytes": p.used_vram_bytes}
                for p in self.vram_holders
            ],
            "memory": {
                "total_bytes": self.memory.total_bytes,
                "available_bytes": self.memory.available_bytes,
            },
            "filesystems": [
                {"path": fs.path, "free_bytes": fs.free_bytes, "total_bytes": fs.total_bytes}
                for fs in self.filesystems
            ],
            "tools": dict(self.tools),
            "cuda": dict(self.cuda),
        }


def _read_cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def _read_os_release() -> str:
    try:
        content = Path("/etc/os-release").read_text()
    except OSError:
        return platform.platform()
    for line in content.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return platform.platform()


def capture_snapshot(filesystem_paths: tuple[str, ...] = ("/",)) -> HardwareSnapshot:
    """Measure the machine now. Raises OSError only if ``/proc`` is unreadable."""
    try:
        memory = read_memory()
        gpus = query_gpus()
    except (RuntimeError, OSError, ValueError):
        memory, gpus = MemoryReading(0, 0), ()
    filesystems = tuple(filesystem_usage(path) for path in filesystem_paths if Path(path).is_dir())
    return HardwareSnapshot(
        hostname=socket.gethostname(),
        kernel=platform.release(),
        os_release=_read_os_release(),
        cpu_model=_read_cpu_model(),
        cpu_threads=len(os.sched_getaffinity(0)),
        gpus=gpus,
        vram_holders=query_gpu_processes(),
        memory=memory,
        filesystems=filesystems,
        driver_version=nvidia_driver_version(),
        tools=detect_tool_versions(),
        cuda=cuda_toolchain_versions(),
    )