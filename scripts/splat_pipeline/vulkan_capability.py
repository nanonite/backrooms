#!/usr/bin/env python3
"""Prove a Vulkan device can actually be created, using the project's renderer.

The runtime splat renderer is Godot, so the question that matters is not "is
there a Vulkan ICD file" but "does the renderer we ship initialise a device".
A present ICD and a dead loader look identical from the filesystem, so this
probe boots the renderer against a throwaway empty project and reads the device
banner it prints.

Measuring the shipped renderer rather than a synthetic loader enumeration also
keeps the answer honest when the two disagree -- which they can, because a
loader-level enumeration exercises the loader and not the renderer's device
selection, shader pipeline or swapchain setup.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from hardware_report import GODOT_BINARY, resolve_binary

PROBE_TIMEOUT_SECONDS = 180

#: Banner Godot prints on a successful Vulkan start, e.g.
#: "Vulkan 1.4.329 - Forward+ - Using Device #0: NVIDIA - NVIDIA GeForce RTX 4070 Ti"
_DEVICE_BANNER = re.compile(
    r"Vulkan\s+(?P<api>[\d.]+)\s+-\s+(?P<method>[\w+]+)(?:\s+-\s+Using Device #\d+:\s*(?P<vendor>[\w ]+?)\s+-\s+(?P<device>.+))?$"
)

#: A minimal project plus a one-node scene: the probe must not import or
#: modify the real game assets, but Godot still refuses to run a project with no
#: main scene, so the throwaway project needs one.
_EMPTY_PROJECT = (
    '[application]\n'
    'config/name="vulkan-probe"\n'
    'run/main_scene="res://probe.tscn"\n'
    '\n'
    '[rendering]\n'
    'renderer/rendering_method="forward_plus"\n'
)
_EMPTY_SCENE = '[gd_scene format=3]\n\n[node name="Probe" type="Node3D"]\n'

#: Substrings that mean the *probe* is misconfigured, not the machine. Saying
#: "install the Vulkan loader" for a missing scene file would send an operator
#: after a problem they do not have.
_PROBE_FAULT_MARKERS = ("no main scene", "Can't run project", "Parse Error")


@dataclass(frozen=True)
class VulkanCapability:
    """Whether a Vulkan device was created, and which one."""

    available: bool
    api_version: str
    device_name: str
    vendor: str
    rendering_method: str
    source: str
    error: str

    def remediation(self) -> str:
        """Return the specific next action for the failure that occurred."""
        if self.available:
            return ""
        if any(marker in self.error for marker in _PROBE_FAULT_MARKERS):
            return (
                f"The Vulkan probe itself failed to start the renderer ({self.error}). This is "
                "a defect in vulkan_capability.py, not a machine problem; do not act on it."
            )
        if "not found" in self.error or "not a file" in self.error:
            return (
                f"Godot binary is missing at {GODOT_BINARY}. Install the pinned Godot build, "
                "or point GODOT_BINARY at it, then re-run the preflight."
            )
        return (
            "Godot could not create a Vulkan device. Install the Vulkan loader and an ICD "
            "(`apt install libvulkan1 vulkan-tools mesa-vulkan-drivers`), then confirm with "
            "`vulkaninfo --summary`. A headless or session-less shell cannot reach the GPU."
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "api_version": self.api_version,
            "device_name": self.device_name,
            "vendor": self.vendor,
            "rendering_method": self.rendering_method,
            "source": self.source,
            "error": self.error,
        }


def _probe_with_vulkaninfo(binary: str) -> VulkanCapability:
    """Fall back to ``vulkaninfo`` when the renderer cannot be used as the probe."""
    try:
        completed = subprocess.run(
            [binary, "--summary"], capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return VulkanCapability(False, "", "", "", "", "vulkaninfo", str(error))
    if completed.returncode != 0:
        return VulkanCapability(False, "", "", "", "", "vulkaninfo", "vulkaninfo reported no device")
    device = re.search(r"deviceName\s*=\s*(.+)", completed.stdout)
    api = re.search(r"Vulkan Instance Version:\s*([\d.]+)", completed.stdout)
    return VulkanCapability(
        available=True,
        api_version=api.group(1) if api else "",
        device_name=device.group(1).strip() if device else "",
        vendor="",
        rendering_method="",
        source="vulkaninfo",
        error="",
    )


def _parse_banner(output: str) -> VulkanCapability | None:
    """Return a capability when the output carries a Vulkan device banner."""
    for line in output.splitlines():
        match = _DEVICE_BANNER.search(line.strip())
        if match:
            return VulkanCapability(
                available=True,
                api_version=match.group("api"),
                device_name=(match.group("device") or "").strip(),
                vendor=(match.group("vendor") or "").strip(),
                rendering_method=match.group("method"),
                source="godot",
                error="",
            )
    return None


def probe_vulkan(godot_binary: str = GODOT_BINARY) -> VulkanCapability:
    """Boot the renderer with Vulkan in a throwaway project and report the device."""
    binary = resolve_binary(Path(godot_binary).name, (godot_binary,))
    if not Path(binary).exists():
        fallback = _probe_with_vulkaninfo(resolve_binary("vulkaninfo"))
        if not fallback.available:
            return VulkanCapability(
                False, "", "", "", "", "", f"Godot binary not found at {godot_binary}"
            )
        return fallback
    with tempfile.TemporaryDirectory(prefix="vulkan-probe-") as workspace:
        project = Path(workspace) / "project.godot"
        project.write_text(_EMPTY_PROJECT)
        (Path(workspace) / "probe.tscn").write_text(_EMPTY_SCENE)
        command = [binary, "--path", workspace, "--rendering-driver", "vulkan", "--quit"]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return VulkanCapability(False, "", "", "", "", "godot", str(error))
    output = (completed.stdout or "") + (completed.stderr or "")
    parsed = _parse_banner(output)
    if parsed is not None:
        return parsed
    return VulkanCapability(False, "", "", "", "", "godot", _first_error_line(output))


def _first_error_line(output: str) -> str:
    """Return the most informative line of a failed renderer start."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in lines:
        if "rror" in line or "ailed" in line or "Vulkan" in line:
            return line
    return lines[-1] if lines else "renderer produced no output"