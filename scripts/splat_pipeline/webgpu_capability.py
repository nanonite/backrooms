#!/usr/bin/env python3
"""Prove a WebGPU adapter is reachable, or say exactly how to get one.

Collision generation is the one stage that is not CUDA: the reference
implementation is PlayCanvas' splat-transform, which runs its compute work on
WebGPU and is documented to be driven from its published container. So the
collision stage's feasibility turns on a WebGPU adapter existing *on this
machine*, which is a different question from whether a CUDA GPU exists.

Every host is probed in turn and the first that answers wins. When none do,
the remediation names the container rather than a vague "install WebGPU",
because a desktop WebGPU build and a headless compute adapter are not the same
thing and installing the wrong one wastes an afternoon.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

PROBE_TIMEOUT_SECONDS = 120

#: The documented upstream container for the collision toolchain. Quoted in the
#: remediation so the operator gets the exact reference, not a paraphrase.
SPLAT_TRANSFORM_CONTAINER = "https://developer.playcanvas.com/user-manual/splat-transform/docker/"

_WGPU_PYTHON_SCRIPT = """
import json
result = {}
try:
    import wgpu
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    result["available"] = adapter is not None
    if adapter is not None:
        info = adapter.info
        result["adapter"] = getattr(info, "adapter_name", "") or getattr(info, "device", "")
        result["backend"] = getattr(info, "backend_type", "")
        result["library"] = wgpu.__version__
except Exception as error:
    result.update(available=False, error=f"{type(error).__name__}: {error}")
print("WEBGPU_JSON " + json.dumps(result))
"""

_NODE_SCRIPT = """
const out = { available: false };
(async () => {
  try {
    if (!globalThis.navigator || !globalThis.navigator.gpu) {
      out.error = "navigator.gpu is undefined";
    } else {
      const adapter = await navigator.gpu.requestAdapter();
      out.available = adapter !== null;
      if (adapter) out.adapter = adapter.info ? adapter.info.vendor : "unknown";
      else out.error = "requestAdapter() returned null";
    }
  } catch (error) {
    out.error = String(error);
  }
  process.stdout.write("WEBGPU_JSON " + JSON.stringify(out) + "\\n");
})();
"""

_DENO_SCRIPT = """
const out = { available: false };
try {
  const adapter = await navigator.gpu.requestAdapter();
  out.available = adapter !== null;
  if (adapter) out.adapter = adapter.info ? adapter.info.vendor : "unknown";
  else out.error = "requestAdapter() returned null";
} catch (error) {
  out.error = String(error);
}
console.log("WEBGPU_JSON " + JSON.stringify(out));
"""


@dataclass(frozen=True)
class WebGpuCapability:
    """Whether a WebGPU adapter was obtained, and which host provided it."""

    available: bool
    adapter_name: str
    backend: str
    host: str
    error: str

    def remediation(self) -> str:
        """Return the specific next action for the failure that occurred."""
        if self.available:
            return ""
        return (
            "No WebGPU adapter was found on this host. The collision stage needs one: run "
            "the pinned PlayCanvas splat-transform container on a machine with a working "
            f"Vulkan/GL stack ({SPLAT_TRANSFORM_CONTAINER}), or run it here under "
            "`VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json` with a Node build "
            "that exposes navigator.gpu. Until then the collision stage has no measured "
            "local support and must not be reported as verified."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "adapter_name": self.adapter_name,
            "backend": self.backend,
            "host": self.host,
            "error": self.error,
        }


def _from_json_line(text: str, host: str) -> WebGpuCapability | None:
    """Parse a ``WEBGPU_JSON`` line into a capability, or None if there is none."""
    for line in text.splitlines():
        if line.startswith("WEBGPU_JSON "):
            data = json.loads(line.removeprefix("WEBGPU_JSON "))
            return WebGpuCapability(
                available=bool(data.get("available", False)),
                adapter_name=str(data.get("adapter", "")),
                backend=str(data.get("backend", "") or str(data.get("library", ""))),
                host=host,
                error=str(data.get("error", "")),
            )
    return None


def _run_node() -> WebGpuCapability | None:
    """Probe Node, which is how the upstream splat-transform container runs."""
    if not shutil.which("node"):
        return None
    return _execute(["node", "-e", _NODE_SCRIPT], "node")


def _run_deno() -> WebGpuCapability | None:
    """Probe Deno, whose default permission set already exposes ``navigator.gpu``."""
    if not shutil.which("deno"):
        return None
    return _execute(["deno", "run", "--allow-all", "-"], "deno", stdin=_DENO_SCRIPT)


def _execute(command: list[str], host: str, stdin: str | None = None) -> WebGpuCapability | None:
    """Run one host probe and parse its answer; None when it cannot be reached."""
    try:
        completed = subprocess.run(
            command,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _from_json_line((completed.stdout or "") + (completed.stderr or ""), host)


def _probe_wgpu_python() -> WebGpuCapability | None:
    """Probe the ``wgpu`` PyPI binding, which is what a Python collision tool uses."""
    from hardware_report import NERFSTUDIO_PYTHON

    try:
        completed = subprocess.run(
            [NERFSTUDIO_PYTHON, "-c", _WGPU_PYTHON_SCRIPT],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return _from_json_line((completed.stdout or "") + (completed.stderr or ""), "wgpu-py")


def probe_webgpu() -> WebGpuCapability:
    """Try each known WebGPU host in turn and return the first working answer."""
    attempts = [_probe_wgpu_python(), _run_node(), _run_deno()]
    for attempt in attempts:
        if attempt is not None and attempt.available:
            return attempt
    reasons = [a.error for a in attempts if a is not None and a.error]
    detail = "; ".join(reasons) or "no WebGPU host answered"
    return WebGpuCapability(False, "", "", "none", detail)