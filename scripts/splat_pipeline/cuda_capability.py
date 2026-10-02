#!/usr/bin/env python3
"""Prove the CUDA *training* path works, separately from the collision path.

``nvidia-smi`` proving a GPU exists says nothing about whether a training step
runs: the pinned interpreter may lack torch, torch may have been built against
a CUDA runtime the driver cannot load, or the card may be busy enough that an
allocation fails. Those three failures need three different fixes, so this probe
actually runs one forward/backward pass and reports which of them happened.

The probe runs in the pinned nerfstudio interpreter as a subprocess because the
system python has no torch, and importing torch into the preflight's own
process would make it unrunnable on machines that lack it.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from hardware_report import NERFSTUDIO_PYTHON

PROBE_TIMEOUT_SECONDS = 300

#: One tiny training step. Small enough to be free, real enough that a broken
#: driver, a missing CUDA runtime or an exhausted card all fail here.
_TRAINING_STEP_SCRIPT = """
import json, sys
result = {}
try:
    import torch
    result["torch"] = torch.__version__
    result["torch_cuda"] = torch.version.cuda
    if not torch.cuda.is_available():
        result.update(available=False, error="torch.cuda.is_available() returned False")
    else:
        props = torch.cuda.get_device_properties(0)
        major, minor = torch.cuda.get_device_capability(0)
        result.update(
            available=True,
            device_name=props.name,
            compute_capability=f"{major}.{minor}",
            total_vram_bytes=props.total_memory,
            free_vram_bytes=torch.cuda.mem_get_info(0)[0],
        )
        layer = torch.nn.Linear(64, 64).cuda()
        optimiser = torch.optim.SGD(layer.parameters(), lr=1e-3)
        loss = layer(torch.ones(8, 64, device="cuda")).pow(2).mean()
        loss.backward()
        optimiser.step()
        torch.cuda.synchronize()
        result.update(trained=True, probe_peak_bytes=torch.cuda.max_memory_allocated(0))
except Exception as error:
    result.update(trained=False, error=f"{type(error).__name__}: {error}")
print("CAPABILITY_JSON " + json.dumps(result))
"""


@dataclass(frozen=True)
class CudaCapability:
    """What a real training step proved, and what to do when it proved nothing."""

    available: bool
    trained: bool
    device_name: str
    compute_capability: str
    total_vram_bytes: int
    free_vram_bytes: int
    probe_peak_bytes: int
    torch_version: str
    torch_cuda_version: str
    error: str

    @property
    def usable(self) -> bool:
        return self.available and self.trained

    def remediation(self) -> str:
        """Return the specific next action for the failure that occurred."""
        if self.usable:
            return ""
        if not self.available and "No module named" in self.error:
            return (
                f"torch is not installed for {NERFSTUDIO_PYTHON}. Activate the nerfstudio "
                "conda env before running the preflight."
            )
        if not self.available:
            return (
                f"torch cannot reach a CUDA device ({self.error}). Check that the NVIDIA "
                "driver is loaded (`nvidia-smi` must work) and that the container or host "
                "exposes the device."
            )
        return (
            f"A CUDA device is present but a training step failed ({self.error}). This is "
            "usually exhausted VRAM held by another process; close GPU jobs and re-check "
            "with `nvidia-smi`."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "trained": self.trained,
            "usable": self.usable,
            "device_name": self.device_name,
            "compute_capability": self.compute_capability,
            "total_vram_bytes": self.total_vram_bytes,
            "free_vram_bytes": self.free_vram_bytes,
            "probe_peak_bytes": self.probe_peak_bytes,
            "torch_version": self.torch_version,
            "torch_cuda_version": self.torch_cuda_version,
            "error": self.error,
        }


def _empty(error: str) -> CudaCapability:
    """Return a failed capability with no device details."""
    return CudaCapability(False, False, "", "", 0, 0, 0, "", "", error)


def probe_cuda(python: str = NERFSTUDIO_PYTHON) -> CudaCapability:
    """Run one training step in ``python`` and report whether CUDA training works."""
    try:
        completed = subprocess.run(
            [python, "-c", _TRAINING_STEP_SCRIPT],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return _empty(f"interpreter not found: {python}")
    except subprocess.TimeoutExpired:
        return _empty(f"training probe timed out after {PROBE_TIMEOUT_SECONDS}s")
    for line in completed.stdout.splitlines():
        if line.startswith("CAPABILITY_JSON "):
            return _capability_from_json(json.loads(line.removeprefix("CAPABILITY_JSON ")))
    detail = (completed.stderr or completed.stdout or "").strip().splitlines()
    return _empty(f"probe exited {completed.returncode}: {detail[-1] if detail else 'no output'}")


def _capability_from_json(data: dict[str, object]) -> CudaCapability:
    """Build a :class:`CudaCapability` from the probe script's JSON line."""
    return CudaCapability(
        available=bool(data.get("available", False)),
        trained=bool(data.get("trained", False)),
        device_name=str(data.get("device_name", "")),
        compute_capability=str(data.get("compute_capability", "")),
        total_vram_bytes=int(data.get("total_vram_bytes", 0)),
        free_vram_bytes=int(data.get("free_vram_bytes", 0)),
        probe_peak_bytes=int(data.get("probe_peak_bytes", 0)),
        torch_version=str(data.get("torch", "")),
        torch_cuda_version=str(data.get("torch_cuda", "")),
        error=str(data.get("error", "")),
    )