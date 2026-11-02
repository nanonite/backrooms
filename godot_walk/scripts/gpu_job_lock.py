"""Exclusive repository-wide lock for guarded local GPU jobs."""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = Path("godot_walk/source_library/.gpu-job.lock")


class GpuJobLockError(RuntimeError):
    """A competing local GPU job holds the shared lock past the wait limit."""


@contextmanager
def exclusive_gpu_job(
    root: Path = ROOT, *, timeout_seconds: float = 0
) -> Iterator[None]:
    lock_path = root / LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_symlink():
        raise GpuJobLockError("GPU lock path may not be a symlink")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o644)
    try:
        _acquire(descriptor, timeout_seconds)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _acquire(descriptor: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + max(0, timeout_seconds)
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError as error:
            if time.monotonic() >= deadline:
                raise GpuJobLockError(
                    "Another guarded GPU job holds the shared lock"
                ) from error
            time.sleep(min(0.25, max(0, deadline - time.monotonic())))
