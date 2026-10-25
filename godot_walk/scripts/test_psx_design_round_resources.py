"""Unit tests for GPU preflight process filtering."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "godot_walk" / "scripts"))

from psx_design_round_resources import _active_gpu_jobs, _active_named_jobs


class ActiveJobScanTests(unittest.TestCase):
    def test_scan_ignores_runner_and_wrapper_but_detects_other_gpu_jobs(self) -> None:
        process_table = """50 1 bash bash -lc timeout 1800s python3 run_hunyuan_psx_round1.py
100 50 timeout timeout 1800s python3 godot_walk/scripts/run_hunyuan_psx_round1.py
101 100 python3 python3 godot_walk/scripts/run_hunyuan_psx_round1.py
201 1 python3 python3 godot_walk/scripts/hunyuan_review_server.py --port 8765
200 1 python3 python3 /opt/hunyuan/infer.py
300 1 qemu-system-x86_64 qemu-system-x86_64 -name test-vm"""
        result = CompletedProcess([], 0, process_table, "")
        with (
            patch("psx_design_round_resources.subprocess.run", return_value=result),
            patch("psx_design_round_resources.os.getpid", return_value=101),
        ):
            active = _active_named_jobs()
        self.assertEqual(len(active), 2)
        self.assertIn("/opt/hunyuan/infer.py", " ".join(active))
        self.assertIn("qemu-system-x86_64", " ".join(active))

    def test_gpu_scan_resolves_allowlisted_desktop_executables(self) -> None:
        pmon = """# gpu pid type sm mem enc dec jpg ofa command
0 6718 G - - - - - - snapd-desktop-i
0 191847 G - - - - - - discord --gpu-p
0 450 C - - - - - - python"""
        result = CompletedProcess([], 0, pmon, "")
        with (
            patch("psx_design_round_resources.subprocess.run", return_value=result),
            patch(
                "psx_design_round_resources._gpu_process_name",
                side_effect={
                    "6718": "snapd-desktop-integration",
                    "191847": "discord",
                    "450": "python",
                }.get,
            ),
        ):
            active = _active_gpu_jobs()
        self.assertEqual(active, ["pid=450 type=C command=python"])


if __name__ == "__main__":
    unittest.main()
