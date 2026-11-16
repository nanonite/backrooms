"""Unit tests for the Hunyuan preflight's GPU process filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from source_ingestion_preflight import (
    INGESTION_GUARD_POLICY_VERSION,
    _gpu_process_scan,
    check_ingestion_headroom,
)

GIB = 1024**3


def pmon(*rows: str) -> str:
    header = "# gpu pid type sm mem enc dec jpg ofa command"
    return "\n".join((header, *rows))


class GpuProcessScanTests(unittest.TestCase):
    def _scan(
        self,
        output: str,
        names: dict[str, str] | None = None,
        same_group: tuple[str, ...] = (),
    ) -> dict[str, list[dict[str, str]]]:
        names = names or {}
        result = CompletedProcess([], 0, output, "")
        with (
            patch(
                "source_ingestion_preflight.subprocess.run", return_value=result
            ),
            patch(
                "source_ingestion_preflight._gpu_process_name",
                side_effect=lambda pid, fallback: names.get(
                    pid, fallback.split(maxsplit=1)[0].rsplit("/", maxsplit=1)[-1]
                ),
            ),
            patch(
                "source_ingestion_preflight._same_process_group",
                side_effect=lambda pid: pid in same_group,
            ),
        ):
            return _gpu_process_scan()

    def test_graphics_only_desktop_rows_are_ignored_and_recorded(self) -> None:
        scan = self._scan(
            pmon(
                "0 28826 G - - - - - - gnome-text-editor",
                "0 6718 G - - - - - - gnome-shell",
                "0 191847 G - - - - - - discord --gpu-p",
            ),
            names={
                "28826": "gnome-text-editor",
                "6718": "gnome-shell",
                "191847": "discord",
            },
        )

        self.assertEqual([], scan["blocked"])
        self.assertEqual(
            [
                {"pid": "28826", "type": "G", "command": "gnome-text-editor"},
                {"pid": "6718", "type": "G", "command": "gnome-shell"},
                {"pid": "191847", "type": "G", "command": "discord"},
            ],
            scan["ignored_graphics"],
        )

    def test_compute_row_is_blocked(self) -> None:
        scan = self._scan(
            pmon("0 450 C - - - - - - python"),
            names={"450": "python"},
        )

        self.assertEqual(
            [{"pid": "450", "type": "C", "command": "python"}], scan["blocked"]
        )
        self.assertEqual([], scan["ignored_graphics"])

    def test_compute_plus_graphics_row_is_blocked(self) -> None:
        scan = self._scan(
            pmon("0 700 C+G - - - - - - blender"),
            names={"700": "blender"},
        )

        self.assertEqual(
            [{"pid": "700", "type": "C+G", "command": "blender"}], scan["blocked"]
        )
        self.assertEqual([], scan["ignored_graphics"])

    def test_mixed_rows_block_only_the_compute_row(self) -> None:
        scan = self._scan(
            pmon(
                "0 28826 G - - - - - - gnome-text-editor",
                "0 450 C - - - - - - python",
                "0 700 C+G - - - - - - blender",
            ),
            names={
                "28826": "gnome-text-editor",
                "450": "python",
                "700": "blender",
            },
        )

        self.assertEqual(
            [
                {"pid": "450", "type": "C", "command": "python"},
                {"pid": "700", "type": "C+G", "command": "blender"},
            ],
            scan["blocked"],
        )
        self.assertEqual(
            [{"pid": "28826", "type": "G", "command": "gnome-text-editor"}],
            scan["ignored_graphics"],
        )

    def test_own_process_group_compute_row_does_not_block(self) -> None:
        scan = self._scan(
            pmon("0 450 C - - - - - - python"),
            names={"450": "python"},
            same_group=("450",),
        )

        self.assertEqual([], scan["blocked"])
        self.assertEqual([], scan["ignored_graphics"])


class IngestionHeadroomTests(unittest.TestCase):
    def _headroom(self, scan: dict[str, list[dict[str, str]]]) -> dict:
        with (
            patch(
                "source_ingestion_preflight._active_named_jobs", return_value=[]
            ),
            patch(
                "source_ingestion_preflight._gpu_process_scan", return_value=scan
            ),
            patch(
                "source_ingestion_preflight._gpu_snapshot",
                return_value={
                    "free_vram_bytes": 8 * GIB,
                    "total_vram_bytes": 12 * GIB,
                    "utilization_pct": 12,
                },
            ),
            patch(
                "source_ingestion_preflight._compute_apps", return_value=[]
            ),
            patch(
                "source_ingestion_preflight._available_ram_bytes",
                return_value=8 * GIB,
            ),
        ):
            return check_ingestion_headroom()

    def test_graphics_only_rows_pass_and_are_recorded_with_their_type(self) -> None:
        ignored = [{"pid": "28826", "type": "G", "command": "gnome-text-editor"}]

        result = self._headroom({"blocked": [], "ignored_graphics": ignored})

        self.assertEqual(INGESTION_GUARD_POLICY_VERSION, result["guard_policy_version"])
        self.assertEqual("2.3.0", result["guard_policy_version"])
        self.assertEqual(ignored, result["ignored_graphics_processes"])
        self.assertEqual([], result["compute_apps"])

    def test_compute_row_blocks_even_when_graphics_rows_are_present(self) -> None:
        scan = {
            "blocked": [{"pid": "700", "type": "C+G", "command": "blender"}],
            "ignored_graphics": [
                {"pid": "28826", "type": "G", "command": "gnome-text-editor"}
            ],
        }

        with self.assertRaisesRegex(
            RuntimeError, "pid=700 type=C\\+G command=blender"
        ):
            self._headroom(scan)

    def test_memory_headroom_thresholds_match_the_psx_preflight(self) -> None:
        import psx_design_round_resources as psx

        gpu = {
            "free_vram_bytes": 8 * GIB,
            "total_vram_bytes": 12 * GIB,
            "utilization_pct": 12,
        }
        with (
            patch(
                "source_ingestion_preflight._active_named_jobs", return_value=[]
            ),
            patch(
                "source_ingestion_preflight._gpu_process_scan",
                return_value={"blocked": [], "ignored_graphics": []},
            ),
            patch(
                "source_ingestion_preflight._gpu_snapshot", return_value=gpu
            ),
            patch("source_ingestion_preflight._compute_apps", return_value=[]),
            patch(
                "source_ingestion_preflight._available_ram_bytes",
                return_value=8 * GIB,
            ),
            patch.object(psx, "_active_named_jobs", return_value=[]),
            patch.object(psx, "_active_gpu_jobs", return_value=[]),
            patch.object(psx, "_gpu_snapshot", return_value=gpu),
            patch.object(psx, "_compute_apps", return_value=[]),
            patch.object(psx, "_available_ram_bytes", return_value=8 * GIB),
        ):
            ingestion = check_ingestion_headroom()
            psx_headroom = psx.check_capture_headroom()

        for key in (
            "free_vram_bytes",
            "total_vram_bytes",
            "ram_available_bytes",
            "vram_after_headroom_bytes",
            "ram_after_headroom_bytes",
            "vram_headroom_fraction",
            "ram_headroom_fraction",
        ):
            self.assertEqual(psx_headroom[key], ingestion[key], key)

    def test_memory_headroom_thresholds_still_block(self) -> None:
        with (
            patch(
                "source_ingestion_preflight._active_named_jobs", return_value=[]
            ),
            patch(
                "source_ingestion_preflight._gpu_process_scan",
                return_value={"blocked": [], "ignored_graphics": []},
            ),
            patch(
                "source_ingestion_preflight._gpu_snapshot",
                return_value={
                    "free_vram_bytes": 2 * GIB,
                    "total_vram_bytes": 12 * GIB,
                    "utilization_pct": 0,
                },
            ),
            patch("source_ingestion_preflight._compute_apps", return_value=[]),
            patch(
                "source_ingestion_preflight._available_ram_bytes",
                return_value=8 * GIB,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "free VRAM"):
                check_ingestion_headroom()


class NamedJobScanTests(unittest.TestCase):
    PS = (
        "100 1 bun /bin/bun chainlink-loop --prompt run_source_hunyuan.py\n"
        "101 100 opencode opencode run worker run_source_hunyuan.py\n"
        "102 1 bash /bin/bash -c python3 run_source_hunyuan.py\n"
        "103 1 tee tee /tmp/hunyuan-run.log\n"
        "104 1 python3 python3 demo_panogen.py hunyuanworld\n"
        "105 1 qemu-aarch64 qemu-system-aarch64 -m 4G\n"
        "106 1 python3 python3 hunyuan_review_server.py\n"
        "107 1 python3 python3 something_else.py\n"
    )

    def _scan(self) -> list[str]:
        from unittest.mock import MagicMock, patch

        import source_ingestion_preflight as preflight

        completed = MagicMock(stdout=self.PS)
        with (
            patch("source_ingestion_preflight.subprocess.run", return_value=completed),
            patch("source_ingestion_preflight.os.getpid", return_value=999),
        ):
            return preflight._active_named_jobs()

    def test_only_real_job_executables_match(self) -> None:
        jobs = self._scan()
        self.assertEqual(len(jobs), 2)
        self.assertTrue(any(line.startswith("104 ") for line in jobs))
        self.assertTrue(any(line.startswith("105 ") for line in jobs))

    def test_orchestrators_and_review_server_never_match(self) -> None:
        for line in self._scan():
            self.assertFalse(
                line.startswith(("100 ", "101 ", "102 ", "103 ", "106 ", "107 "))
            )


if __name__ == "__main__":
    unittest.main()
