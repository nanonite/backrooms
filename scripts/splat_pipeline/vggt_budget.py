#!/usr/bin/env python3
"""VGGT resource policy: what VGGT may attempt, and what it refuses to attempt.

VGGT's demo_colmap.py globs every file in ``<scene>/images/`` and calls
``PIL.Image.open`` on each, then runs global attention over all frames at
once. Two consequences, both handled here:

* **Metadata is not input.** Pipeline manifests (``frames.json``) and any
  other non-image file in ``images/`` crash the loader with
  ``PIL.UnidentifiedImageError``. Only files with an image extension are
  presented to VGGT.
* **VRAM grows with the frame count.** The aggregator's global attention is
  quadratic in the total token count, so an over-large selection OOMs
  mid-run. The policy is deterministic: a frame cap selects an evenly-spaced
  subset (the same input always produces the same attempt), an OOM is
  classified from the run's output and answered with a smaller attempt down
  to a floor, and below the floor the run is refused with the budget and the
  setting that would change it.

The module is importable (the policy functions are pure) and has a small CLI
so ``pose_vggt.sh`` can drive it without re-implementing the rules.

CLI:
    vggt_budget.py plan <images_dir> <max_frames> <min_frames>
        Print the total image count, then one line per attempt with the
        frame count to try, largest first, ending at <min_frames>.
    vggt_budget.py select <images_dir> <frame_count>
        Print the image paths for one attempt, one per line, evenly spaced.
    vggt_budget.py classify <log_file>
        Print "oom" when the log shows a CUDA out-of-memory failure, else
        "other". An OOM is the one failure a smaller attempt can fix.
    vggt_budget.py refuse <scene_dir> <reason> <budget> <suggested>
        Write POSE_REFUSED into <scene_dir> and print the refusal text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Extensions VGGT's PIL loader can actually open. Everything else in
#: ``images/`` (the ``frames.json`` manifest, logs, thumbnails) is metadata.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

#: Default frame cap for one VGGT attempt on the target GPU (RTX 4070 Ti,
#: 12 GiB). The aggregator's global attention is quadratic in the frame
#: count. Measured on this host: 24 frames at 1080p OOMs; 12 frames succeeds
#: at a 11643 MiB sampled peak. Frame counts 13–23 were not attempted.
DEFAULT_MAX_FRAMES = 12

#: Floor for the OOM backoff. Below this a refusal is issued instead of
#: another attempt: a reconstruction from fewer frames is not a pose stage.
MIN_FRAMES = 4

#: Markers that distinguish an OOM from any other failure. Matched
#: case-insensitively against the captured output of one VGGT run.
OOM_MARKERS = (
    "outofmemoryerror",
    "cuda out of memory",
    "out of memory",
    "cudnn_status_alloc_failed",
    "cublas_status_alloc_failed",
)

#: Markers for interpreter/import/driver failures — the Python environment is
#: broken, not the capture. These must never be reported as a capture problem.
ENV_MARKERS = (
    "modulenotfounderror",
    "importerror",
    "libgmpxx.so",
    "libstdc++.so",
    "cannot open shared object file",
    "error while loading shared libraries",
)

#: Marker file written beside the scene when VGGT refuses to attempt the
#: reconstruction. run_pipeline.sh surfaces its contents verbatim.
REFUSED_FILE = "POSE_REFUSED"


def is_image_file(path: Path) -> bool:
    """Whether ``path`` has an extension VGGT's PIL loader can open."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def select_image_files(files) -> list[Path]:
    """The image files among ``files``, sorted by name.

    Sorting is what makes every later selection deterministic: the same
    ``images/`` directory always yields the same ordered list, so an
    evenly-spaced subset is reproducible across runs.
    """
    return sorted((p for p in files if is_image_file(p)), key=lambda p: p.name)


def evenly_spaced_indices(count: int, cap: int) -> list[int]:
    """Indices of the ``cap`` frames to keep out of ``count``, including both ends.

    Even spacing (rather than the first ``cap`` frames) keeps coverage of the
    whole clip: a walk-through reconstruction needs poses from the start and
    the end of the capture, not just its opening.
    """
    if count < 0:
        raise ValueError(f"count must be non-negative, got {count}")
    if cap < 1:
        raise ValueError(f"cap must be at least 1, got {cap}")
    if count <= cap:
        return list(range(count))
    if cap == 1:
        return [0]
    step = (count - 1) / (cap - 1)
    return [round(i * step) for i in range(cap)]


def plan_attempts(frame_count: int, max_frames: int, min_frames: int) -> list[int]:
    """Frame counts to try, largest first, ending at ``min_frames``.

    The first attempt is the capped selection; each OOM halves it. The
    schedule always ends at ``min_frames`` so the caller can issue a refusal
    after the last attempt fails instead of looping forever.
    """
    if not (1 <= min_frames <= max_frames):
        raise ValueError(f"need 1 <= min_frames ({min_frames}) <= max_frames ({max_frames})")
    if frame_count <= 0:
        return []
    first = min(frame_count, max_frames)
    schedule = [first]
    while schedule[-1] > min_frames:
        schedule.append(max(min_frames, schedule[-1] // 2))
    return schedule


def classify_failure(output: str) -> str:
    """``"oom"``, ``"env"``, or ``"other"``.

    An OOM is answered with a smaller attempt. An environment failure
    (missing module, broken interpreter, missing shared library) is an
    operator problem, not a capture problem — it must never be reported as
    a capture issue. Any other failure would fail identically at every
    frame count, so retrying would waste the operator's time.
    """
    lowered = output.lower()
    if any(marker in lowered for marker in OOM_MARKERS):
        return "oom"
    if any(marker in lowered for marker in ENV_MARKERS):
        return "env"
    return "other"


def format_refusal(reason: str, budget: str, suggested: str) -> str:
    """The bounded-refusal text: what was attempted, the budget, and the fix."""
    return (
        f"POSE_REFUSED: {reason}\n"
        f"  budget: {budget}\n"
        f"  suggested: {suggested}\n"
    )


def write_refusal(scene_dir: Path, reason: str, budget: str, suggested: str) -> Path:
    """Write POSE_REFUSED into ``scene_dir`` and return its path."""
    path = scene_dir / REFUSED_FILE
    path.write_text(format_refusal(reason, budget, suggested), encoding="utf-8")
    return path


def _cmd_plan(args: argparse.Namespace) -> int:
    images = select_image_files(Path(args.images_dir).iterdir())
    schedule = plan_attempts(len(images), args.max_frames, args.min_frames)
    print(len(images))
    for count in schedule:
        print(count)
    return 0


def _cmd_select(args: argparse.Namespace) -> int:
    images = select_image_files(Path(args.images_dir).iterdir())
    indices = evenly_spaced_indices(len(images), args.frame_count)
    for index in indices:
        print(images[index])
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    output = Path(args.log_file).read_text(encoding="utf-8", errors="replace")
    print(classify_failure(output))
    return 0


def _cmd_refuse(args: argparse.Namespace) -> int:
    path = write_refusal(Path(args.scene_dir), args.reason, args.budget, args.suggested)
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vggt_budget.py",
        description="Deterministic VGGT resource policy: frame cap, OOM backoff, bounded refusal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="print the attempt schedule for an images directory")
    plan.add_argument("images_dir")
    plan.add_argument("max_frames", type=int, default=DEFAULT_MAX_FRAMES)
    plan.add_argument("min_frames", type=int, default=MIN_FRAMES)
    plan.set_defaults(func=_cmd_plan)

    select = sub.add_parser("select", help="print the image paths for one attempt")
    select.add_argument("images_dir")
    select.add_argument("frame_count", type=int)
    select.set_defaults(func=_cmd_select)

    classify = sub.add_parser("classify", help="classify a failed run's output as oom, env, or other")
    classify.add_argument("log_file")
    classify.set_defaults(func=_cmd_classify)

    refuse = sub.add_parser("refuse", help="write POSE_REFUSED and print the refusal text")
    refuse.add_argument("scene_dir")
    refuse.add_argument("reason")
    refuse.add_argument("budget")
    refuse.add_argument("suggested")
    refuse.set_defaults(func=_cmd_refuse)

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
