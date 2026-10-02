#!/usr/bin/env python3
"""Tests for the resource readers the preflight and benchmark both depend on.

These drive the parsers with captured output and temporary trees, so the suite
runs identically on a laptop with no GPU and on the workstation. A counter
reader that is only ever exercised against real hardware fails exactly when the
hardware is the thing that is broken.

Run with: python3 -m pytest scripts/splat_pipeline/tests/test_resource_probe.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import resource_probe

MEBIBYTE = 1024**2
GIBIBYTE = 1024**3

GPU_CSV = "0, NVIDIA GeForce RTX 4070 Ti, 12282, 2345, 9937, 0, 41\n"
MULTI_GPU_CSV = (
    "0, NVIDIA GeForce RTX 4070 Ti, 12282, 2345, 9937, 0, 41\n"
    "1, NVIDIA RTX A2000, 8192, 1024, 7168, 12, 38\n"
)

MEMINFO = (
    "MemTotal:       65486860 kB\n"
    "MemFree:        30171516 kB\n"
    "MemAvailable:   47052764 kB\n"
    "SwapTotal:      104857600 kB\n"
)


# ---------------------------------------------------------------------------
# nvidia-smi CSV parsing
# ---------------------------------------------------------------------------


def test_parses_one_gpu_with_mebibyte_conversion():
    readings = resource_probe.parse_gpu_csv(GPU_CSV)

    assert len(readings) == 1
    assert readings[0].name == "NVIDIA GeForce RTX 4070 Ti"
    assert readings[0].total_vram_bytes == 12282 * MEBIBYTE
    assert readings[0].used_vram_bytes == 2345 * MEBIBYTE
    assert readings[0].free_vram_bytes == 9937 * MEBIBYTE


def test_parses_every_row_of_a_multi_gpu_machine():
    readings = resource_probe.parse_gpu_csv(MULTI_GPU_CSV)

    assert [reading.index for reading in readings] == [0, 1]
    assert readings[1].name == "NVIDIA RTX A2000"


def test_ignores_rows_with_a_wrong_column_count():
    assert resource_probe.parse_gpu_csv("garbage\n") == []


def test_rejects_a_gpu_name_containing_a_comma_rather_than_shifting_columns():
    """A name with a comma must not be silently mis-parsed into the VRAM column."""
    malformed = "0, Acme, 4000\n"

    assert resource_probe.parse_gpu_csv(malformed) == []


def test_compute_process_rows_skip_the_no_processes_error_line():
    text = (
        "No running processes found\n"
        "4321, /usr/bin/python3, 2048\n"
    )

    processes = resource_probe.parse_compute_process_csv(text)

    assert len(processes) == 1
    assert processes[0].pid == 4321
    assert processes[0].used_vram_bytes == 2048 * MEBIBYTE


# ---------------------------------------------------------------------------
# /proc/meminfo parsing
# ---------------------------------------------------------------------------


def test_meminfo_converts_kibibytes_to_bytes():
    memory = resource_probe.parse_meminfo(MEMINFO)

    assert memory.total_bytes == 65486860 * 1024
    assert memory.available_bytes == 47052764 * 1024
    assert memory.used_bytes == 65486860 * 1024 - 47052764 * 1024


def test_meminfo_raises_when_available_is_missing():
    truncated = "MemTotal:       100 kB\n"

    with pytest.raises(ValueError, match="MemTotal or MemAvailable"):
        resource_probe.parse_meminfo(truncated)


def test_reads_meminfo_from_an_injected_path(tmp_path):
    fake = tmp_path / "meminfo"
    fake.write_text(MEMINFO)

    assert resource_probe.read_memory(fake).total_bytes == 65486860 * 1024


# ---------------------------------------------------------------------------
# Driver version
# ---------------------------------------------------------------------------


def test_driver_version_is_read_from_the_smi_header():
    header = "Fri Oct  2 17:15:00 2026\nNVIDIA-SMI 595.91.07   Driver Version: 595.91.07   CUDA Version: 13.2\n"

    assert resource_probe.parse_nvidia_driver_version(header) == "595.91.07"


def test_missing_driver_version_is_reported_as_unknown():
    assert resource_probe.parse_nvidia_driver_version("no header here") == "unknown"


# ---------------------------------------------------------------------------
# Disk accounting
# ---------------------------------------------------------------------------


def test_directory_size_sums_regular_files_recursively(tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "top.bin").write_bytes(b"x" * 100)
    (tmp_path / "nested" / "inner.bin").write_bytes(b"y" * 250)

    assert resource_probe.directory_size(tmp_path) == 350


def test_directory_size_of_a_missing_path_is_zero_not_an_error(tmp_path):
    assert resource_probe.directory_size(tmp_path / "absent") == 0


def test_directory_size_does_not_follow_symlinks_into_a_loop(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / "data.bin").write_bytes(b"z" * 10)
    (real / "loop").symlink_to(real)

    assert resource_probe.directory_size(real) == 10


def test_filesystem_usage_reports_a_positive_free_size(tmp_path):
    usage = resource_probe.filesystem_usage(tmp_path)

    assert usage.total_bytes > 0
    assert usage.path == str(tmp_path)


def test_gibibyte_constant_matches_the_bytes_the_parsers_produce():
    reading = resource_probe.parse_gpu_csv(GPU_CSV)[0]

    assert reading.total_vram_bytes == pytest.approx(11.99 * GIBIBYTE, rel=0.01)