#!/usr/bin/env python3
"""generate_coverage_clip.py — one coverage-complete source clip for #107.

Produces the single shared source clip consumed by both reconstruction tracks
(the existing Gaussian route #104 and the textured-mesh hypothesis #108). Same
OpenRouter video model and image-to-video flow as ``scripts/generate_videos.py``;
only the prompt and duration differ, to satisfy #107's coverage requirements.

It never overwrites a historical asset: a clip already at the destination is an
error unless ``--force`` is passed, and the default destination is a new,
versioned scene directory.

Usage:
    python3 scripts/generate_coverage_clip.py [--scene-dir DIR] [--force]

Requires OPENROUTER_API_KEY in the environment or in the repo ``.env``.

Output:
    <scene-dir>/video.mp4         the generated 1080p clip
    <scene-dir>/generation.json   prompt, settings, model, seed and hashes

After it lands:
    python3 scripts/splat_pipeline/validate_input.py <scene-dir>/video.mp4
    python3 scripts/splat_pipeline/capture_gate.py <scene-dir>/video.mp4 \
        --staging-dir <scene-dir> --json <scene-dir>/capture_gate.json
    python3 scripts/splat_pipeline/sample_frames.py <scene-dir>/video.mp4 \
        <scene-dir>/capture_gate.json --out <scene-dir>/frames
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent / "splat_pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from coverage_clip import (  # noqa: E402  (path set up above)
    BASE_URL,
    COVERAGE_PROMPT,
    DEFAULT_SCENE_DIR,
    GenerationSettings,
    build_payload,
    report_path,
    video_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
SEED_IMAGE = REPO_ROOT / "Backrooms_model.jpg"

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 5
RETRY_BACKOFF = [5, 10, 20, 40, 60]
POLL_SECONDS = 10


class GenerationError(RuntimeError):
    """The provider rejected or failed the job."""


def load_env() -> None:
    """Load ``.env`` keys without overriding ones already in the environment."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("ERROR: OPENROUTER_API_KEY not set (environment or repo .env)")
    return key


def headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def image_data_uri(path: Path) -> str:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


def _urlopen_with_retry(request: urllib.request.Request, label: str) -> bytes:
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(request) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            preview = exc.read(512).decode(errors="replace")
            print(
                f"  HTTP {exc.code} on {label} (attempt {attempt + 1}/{MAX_RETRIES}): "
                f"{exc.reason} — {preview}",
                flush=True,
            )
            if exc.code not in RETRY_STATUSES or attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BACKOFF[attempt]
            print(f"  retrying in {delay}s...", flush=True)
            time.sleep(delay)
    raise GenerationError("unreachable: retry loop exhausted without returning")


def submit(key: str, payload: dict) -> tuple[str, str]:
    request = urllib.request.Request(
        f"{BASE_URL}/videos",
        data=json.dumps(payload).encode(),
        headers=headers(key),
        method="POST",
    )
    body = json.loads(_urlopen_with_retry(request, "submit"))
    return body["id"], body["polling_url"]


def poll(key: str, polling_url: str, generation_id: str) -> None:
    while True:
        request = urllib.request.Request(polling_url, headers=headers(key))
        body = json.loads(_urlopen_with_retry(request, "poll"))
        status = body.get("status", "unknown")
        print(f"  [{generation_id[:12]}] {status}", flush=True)
        if status == "completed":
            return
        if status in ("failed", "cancelled"):
            raise GenerationError(f"job {generation_id} ended with {status}: {body}")
        time.sleep(POLL_SECONDS)


def download(key: str, generation_id: str, destination: Path) -> None:
    url = f"{BASE_URL}/videos/{generation_id}/content?index=0"
    request = urllib.request.Request(url, headers=headers(key))
    with urllib.request.urlopen(request) as response:
        destination.write_bytes(response.read())


def digest(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "md5": hashlib.md5(data).hexdigest(),
        "bytes": len(data),
    }


def write_report(
    scene_dir: Path,
    generation_id: str,
    settings: GenerationSettings,
    video: Path,
    started: str,
) -> Path:
    report = {
        "issue": 107,
        "purpose": "coverage-complete source clip shared by the Gaussian and textured-mesh tracks",
        "generation_id": generation_id,
        "generated_at_utc": started,
        "settings": settings.to_dict(),
        "seed_image": {"path": str(SEED_IMAGE), **digest(SEED_IMAGE)},
        "video": {"path": str(video), **digest(video)},
    }
    destination = report_path(scene_dir)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    return destination


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="generate_coverage_clip.py",
        description="Generate one coverage-complete Backrooms source clip for #107.",
    )
    parser.add_argument("--scene-dir", default=DEFAULT_SCENE_DIR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing clip at the destination (default: refuse)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    scene_dir = Path(args.scene_dir)
    video = video_path(scene_dir)
    if video.exists() and not args.force:
        sys.exit(
            f"ERROR: {video} already exists; refusing to overwrite. "
            "Pass --force or choose another --scene-dir."
        )

    load_env()
    key = api_key()

    if not SEED_IMAGE.exists():
        sys.exit(f"ERROR: seed image not found at {SEED_IMAGE}")

    scene_dir.mkdir(parents=True, exist_ok=True)
    settings = GenerationSettings()
    payload = build_payload(COVERAGE_PROMPT, settings, image_data_uri(SEED_IMAGE))

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[GEN] {settings.model_id} {settings.duration_seconds}s {settings.resolution}")
    print(f"      {COVERAGE_PROMPT[:96]}...")
    generation_id, polling_url = submit(key, payload)
    print(f"  job submitted -> {generation_id}")
    poll(key, polling_url, generation_id)
    download(key, generation_id, video)

    destination = write_report(scene_dir, generation_id, settings, video, started)
    print(f"  saved {video}")
    print(f"  saved {destination}")
    print("\nNext: validate, gate and sample this clip before either track consumes it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
