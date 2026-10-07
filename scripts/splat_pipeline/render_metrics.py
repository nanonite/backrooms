#!/usr/bin/env python3
"""Quantify matched fixed-view before/after renders of the corridor splat (#103).

Three numbers per heading, all trivially checkable by hand against the PNGs:

* ``black_void_pct`` -- share of pixels with every channel below the background
  threshold. Same definition and same threshold as #101's
  ``heading_black_fraction.json`` so the two tables line up directly and a
  reader can see whether the candidate opened new holes or filled old ones.
* ``changed_pct`` -- share of pixels whose colour moved by more than
  ``--threshold`` between the matched before/after captures. Cleanup only
  deletes splats, so this is the footprint the deleted splats occupied in the
  production eye: the measurable part of "visible floaters". The companion
  ``went_dark_pct`` says how much of that footprint simply became background
  (i.e. the floater covered nothing behind it).
* ``floater_px`` / ``floater_blobs`` -- content that hangs in the void: a
  foreground component that is neither the room's main structure nor touching
  the frame border, and that covers at least ``FLOATER_MIN_PX`` pixels
  (reported as ``before_floater_*`` / ``after_floater_*`` per heading). A
  floater is a *blob* a player would read as a floating object; a one-pixel
  speck is not. Reported for both captures, so a candidate is credited with
  floaters it removed and charged for fragments its new holes created.
* ``noise_pct`` -- the same changed-share computed between two captures of the
  *same* scene (``--repeat``), so a changed-share is never reported against an
  assumed zero. #103 measured it: with ``--settle=200`` two captures of one
  scene differ by 0.000% of pixels, a ``--settle=5`` capture differs from them
  by 0.018%, and a first-frame (``--settle=0``) capture differs by 7.7% --
  the GDGS render still needs a few frames to settle, which is why the
  before/after evidence is taken at ``--settle=200``.

No colour heuristics and no per-image thresholds: a metric that could be tuned
to flatter the candidate would not be evidence. The three constants below are
the only knobs and they are fixed in the module, not on the command line.

Usage:
    render_metrics.py --before <dir> --after <dir> [--repeat <dir>] --out <json>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

#: Background is (8, 9, 10) in the presentation scene and the PSX pass never
#: touches it, so a pixel with all channels below this is a void, not a dark
#: surface. Matches #101's threshold exactly.
BLACK_THRESHOLD = 20
#: Minimum max-channel change counted as real content change rather than
#: renderer noise. The measured run-to-run noise floor at this threshold is
#: reported alongside, not assumed to be zero.
CHANGED_THRESHOLD = 32
#: Sub-directory the capture script writes its heading PNGs into.
HEADINGS_DIR = "spawn_headings"
#: Minimum pixel area of a detached foreground component before it counts as a
#: floater blob. Below this a component is speckle (renderer noise, dither),
#: not something a player would read as a floating object. Fixed here, never a
#: command-line knob, so the metric cannot be tuned to flatter a candidate.
FLOATER_MIN_PX = 100


def read_image(path: Path) -> np.ndarray:
    """Return an ``(H, W, 3)`` uint8 array for one capture."""
    with Image.open(path) as handle:
        return np.asarray(handle.convert("RGB"), dtype=np.uint8)


def black_fraction(image: np.ndarray, threshold: int = BLACK_THRESHOLD) -> float:
    """Return the share of pixels that are background void."""
    return float((image.max(axis=2) < threshold).mean())


def changed_stats(
    before: np.ndarray,
    after: np.ndarray,
    threshold: int = CHANGED_THRESHOLD,
    black_threshold: int = BLACK_THRESHOLD,
) -> dict[str, float]:
    """Return the changed-pixel shares between two matched captures."""
    if before.shape != after.shape:
        raise ValueError("captures differ in shape: %s vs %s" % (before.shape, after.shape))
    delta = np.abs(before.astype(np.int16) - after.astype(np.int16)).max(axis=2)
    changed = delta > threshold
    went_dark = changed & (before.max(axis=2) >= black_threshold) & (after.max(axis=2) < black_threshold)
    went_bright = changed & (before.max(axis=2) < black_threshold) & (after.max(axis=2) >= black_threshold)
    total = before.shape[0] * before.shape[1]
    return {
        "changed_pct": round(100.0 * float(changed.sum()) / total, 3),
        "went_dark_pct": round(100.0 * float(went_dark.sum()) / total, 3),
        "went_bright_pct": round(100.0 * float(went_bright.sum()) / total, 3),
    }


def label_components(mask: np.ndarray) -> np.ndarray:
    """Label 4-connected foreground components of ``mask`` with union-find.

    Pure numpy + Python: row run-length encoding, then union overlapping runs
    in adjacent rows. scipy is unavailable in this environment (its wheel is
    built against numpy 1.x while numpy 2.x is installed), so this lives here
    rather than depending on ``scipy.ndimage.label``. Returns an ``int32``
    array where 0 is background and components are numbered from 1.
    """
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    parent: list[int] = [0]  # index 0 is the background sentinel

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    previous_runs: list[tuple[int, int, int]] = []  # (start, end exclusive, label)
    for y in range(height):
        row = mask[y]
        if not row.any():
            previous_runs = []
            continue
        padded = np.concatenate(([False], row, [False]))
        edges = np.flatnonzero(padded[1:] != padded[:-1])
        runs: list[tuple[int, int, int]] = []
        for start, end in zip(edges[0::2], edges[1::2]):
            label = len(parent)
            parent.append(label)
            for prev_start, prev_end, prev_label in previous_runs:
                if prev_start < end and start < prev_end:
                    union(label, prev_label)
            labels[y, start:end] = label
            runs.append((int(start), int(end), label))
        previous_runs = runs

    # Flatten each label to its final root, then renumber roots 1..k so equal
    # ids mark one component and ids are contiguous.
    flat = labels.ravel()
    roots = np.array([find(i) if i else 0 for i in range(len(parent))], dtype=np.int32)
    flat[:] = roots[flat]
    used = np.unique(flat)
    renumber = np.zeros(int(used.max()) + 1 if used.size else 1, dtype=np.int32)
    renumber[used] = np.arange(used.size, dtype=np.int32)
    flat[:] = renumber[flat]
    return labels


def floater_stats(
    image: np.ndarray,
    black_threshold: int = BLACK_THRESHOLD,
    min_px: int = FLOATER_MIN_PX,
) -> dict[str, float]:
    """Return the detached-blob stats for one capture.

    A *floater* is a foreground component that is neither the frame's main
    structure (the largest component) nor touching the frame border, and that
    covers at least ``min_px`` pixels. Touching the border is excluded because
    the room's walls run off-frame; the largest component is excluded because
    the corridor structure itself is the one legitimate connected mass. What
    remains is content hanging in the void.
    """
    foreground = image.max(axis=2) >= black_threshold
    labels = label_components(foreground)
    component_ids, counts = np.unique(labels, return_counts=True)
    areas = {int(i): int(c) for i, c in zip(component_ids, counts) if i}
    if not areas:
        return {"floater_px": 0, "floater_blobs": 0, "floater_largest_px": 0}
    main = max(areas, key=lambda i: areas[i])
    border_ids = set(np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ])).tolist())
    blobs = 0
    pixels = 0
    largest = 0
    for component, area in areas.items():
        if component == main or component in border_ids or area < min_px:
            continue
        blobs += 1
        pixels += area
        largest = max(largest, area)
    return {"floater_px": pixels, "floater_blobs": blobs, "floater_largest_px": largest}


def headings_dir(run_dir: Path) -> Path:
    """Return the directory holding ``spawn_*.png`` for one capture run."""
    nested = run_dir / HEADINGS_DIR
    return nested if nested.is_dir() else run_dir


def capture_files(run_dir: Path) -> dict[str, Path]:
    """Return ``{heading file name: path}`` for one capture run."""
    found = {path.name: path for path in sorted(headings_dir(run_dir).glob("spawn_*.png"))}
    if not found:
        raise FileNotFoundError("no spawn_*.png captures under %s" % run_dir)
    return found


def compare_runs(
    left_dir: Path,
    right_dir: Path,
    threshold: int = CHANGED_THRESHOLD,
    black_threshold: int = BLACK_THRESHOLD,
) -> dict[str, dict[str, float]]:
    """Return per-heading metrics for two capture runs of matched headings."""
    left = capture_files(left_dir)
    right = capture_files(right_dir)
    if set(left) != set(right):
        raise ValueError(
            "capture sets differ: only in %s: %s; only in %s: %s"
            % (left_dir, sorted(set(left) - set(right)), right_dir, sorted(set(right) - set(left)))
        )
    out: dict[str, dict[str, float]] = {}
    for name in sorted(left):
        before = read_image(left[name])
        after = read_image(right[name])
        out[name] = {
            "black_left_pct": round(100.0 * black_fraction(before, black_threshold), 3),
            "black_right_pct": round(100.0 * black_fraction(after, black_threshold), 3),
            **changed_stats(before, after, threshold, black_threshold),
        }
    return out


def build_report(
    before_dir: Path,
    after_dir: Path,
    repeat_dir: Path | None,
    threshold: int,
    black_threshold: int,
) -> dict:
    """Assemble the full metrics document for the evidence directory."""
    comparison = compare_runs(before_dir, after_dir, threshold, black_threshold)
    before_files = capture_files(before_dir)
    after_files = capture_files(after_dir)
    headings: dict[str, dict] = {}
    for name, values in comparison.items():
        headings[name] = {
            "black_before_pct": values["black_left_pct"],
            "black_after_pct": values["black_right_pct"],
            "black_delta_pct": round(values["black_right_pct"] - values["black_left_pct"], 3),
            "changed_pct": values["changed_pct"],
            "went_dark_pct": values["went_dark_pct"],
            "went_bright_pct": values["went_bright_pct"],
            **{
                "%s_%s" % (side, key): value
                for side, files in (("before", before_files), ("after", after_files))
                for key, value in floater_stats(read_image(files[name])).items()
            },
        }
    report: dict = {
        "schema_version": 1,
        "before": str(before_dir),
        "after": str(after_dir),
        "thresholds": {"black": black_threshold, "changed": threshold},
        "headings": headings,
        "mean": {
            key: round(float(np.mean([values[key] for values in headings.values()])), 3)
            for key in (
                "black_before_pct",
                "black_after_pct",
                "black_delta_pct",
                "changed_pct",
                "before_floater_px",
                "after_floater_px",
                "before_floater_blobs",
                "after_floater_blobs",
            )
        },
    }
    if repeat_dir is not None:
        noise = compare_runs(before_dir, repeat_dir, threshold, black_threshold)
        repeat_files = capture_files(repeat_dir)
        report["noise_floor"] = {
            "repeat": str(repeat_dir),
            "headings": {
                name: {
                    "changed_pct": values["changed_pct"],
                    **floater_stats(read_image(repeat_files[name])),
                }
                for name, values in noise.items()
            },
            "max_changed_pct": max(values["changed_pct"] for values in noise.values()),
            "mean_floater_px": round(
                float(
                    np.mean(
                        [
                            floater_stats(read_image(repeat_files[name]))["floater_px"]
                            for name in noise
                        ]
                    )
                ),
                1,
            ),
        }
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="baseline capture run")
    parser.add_argument("--after", required=True, type=Path, help="candidate capture run")
    parser.add_argument(
        "--repeat",
        type=Path,
        default=None,
        help="second capture of the *before* scene, for the run-to-run noise floor",
    )
    parser.add_argument("--out", required=True, type=Path, help="JSON report to write")
    parser.add_argument("--threshold", type=int, default=CHANGED_THRESHOLD, help="min max-channel delta")
    parser.add_argument(
        "--black-threshold", type=int, default=BLACK_THRESHOLD, help="background-void ceiling"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.before, args.after, args.repeat, args.threshold, args.black_threshold)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, values in report["headings"].items():
        print(
            "%-14s black %5.1f%% -> %5.1f%% (%+.1f)  changed %5.2f%% (dark %4.2f%%)"
            "  floaters %dpx/%d -> %dpx/%d"
            % (
                name,
                values["black_before_pct"],
                values["black_after_pct"],
                values["black_delta_pct"],
                values["changed_pct"],
                values["went_dark_pct"],
                values["before_floater_px"],
                values["before_floater_blobs"],
                values["after_floater_px"],
                values["after_floater_blobs"],
            )
        )
    if "noise_floor" in report:
        print(
            "noise floor (same scene, two captures): %.3f%% changed, %.0f floater px mean"
            % (report["noise_floor"]["max_changed_pct"], report["noise_floor"]["mean_floater_px"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
