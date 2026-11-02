"""Local tests for cross-worker GPU lock exclusion."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu_job_lock import GpuJobLockError, exclusive_gpu_job


class GpuJobLockTests(unittest.TestCase):
    def test_lock_excludes_a_second_job_and_releases_after_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                exclusive_gpu_job(root),
                self.assertRaises(GpuJobLockError),
                exclusive_gpu_job(root),
            ):
                self.fail("second GPU job unexpectedly acquired the lock")
            with exclusive_gpu_job(root):
                self.assertTrue(True)

    def test_lock_refuses_symlink_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock_parent = root / "godot_walk/source_library"
            lock_parent.mkdir(parents=True)
            target = root / "other"
            target.write_text("", encoding="utf-8")
            (lock_parent / ".gpu-job.lock").symlink_to(target)
            with (
                self.assertRaisesRegex(GpuJobLockError, "symlink"),
                exclusive_gpu_job(root),
            ):
                self.fail("symlink GPU lock unexpectedly acquired")


if __name__ == "__main__":
    unittest.main()
