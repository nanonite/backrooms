#!/usr/bin/env python3
"""
generate_corridor_walk.py — Parallax-rich corridor clip for the splat pipeline.

Derived from generate_videos.py. SAME video model and OpenRouter parameters
(google/veo-3.1-lite, 1080p, 16:9, no audio, first-frame seed image) — only the
prompt changes, to drive parallax-creating camera motion per VIDEO_CAPTURE_SPEC.md.

Why: the original corridor_straight clip was a near-straight forward dolly. COLMAP
needs parallax (same wall point seen from different directions) to triangulate depth;
a straight dolly gives almost none, so splatfacto fit spiky needles instead of walls.
The fix is camera MOTION (weave + look at the walls), not clip length or frame count.

DURATION stays at 4 s to match the proven pipeline parameters. Parallax comes from
motion, not length, so a 4 s weaving clip is the right next test. Bump DURATION below
only if your model/plan supports longer single clips.

API flow (OpenRouter video generation):
  1. POST  /api/v1/videos          -> generation_id + polling_url
  2. GET   /api/v1/videos/{id}     -> poll until status == "completed"
  3. GET   /api/v1/videos/{id}/content?index=0  -> download mp4

Usage:
    python3 scripts/generate_corridor_walk.py

Requires OPENROUTER_API_KEY in environment.

Output:
    data/scenes/corridor_straight/video.mp4   (the splat-pipeline hand-off path)
After it lands, gate it before training:
    python3 scripts/splat_pipeline/preflight_parallax.py <colmap sparse/0>
"""

import os
import sys
import time
import base64
import urllib.request
import urllib.error
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env if present
# ---------------------------------------------------------------------------

ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)

# ---------------------------------------------------------------------------
# Config — IDENTICAL model + params to generate_videos.py
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    sys.exit("ERROR: OPENROUTER_API_KEY environment variable not set")

SEED_IMAGE  = Path(__file__).parent.parent / "Backrooms_model.jpg"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "scenes" / "corridor_straight" / "video.mp4"
MODEL_ID    = "google/veo-3.1-lite"
BASE_URL    = "https://openrouter.ai/api/v1"
DURATION    = 4            # seconds — same as proven pipeline params; bump only if supported
RESOLUTION  = "1080p"
ASPECT      = "16:9"

# ---------------------------------------------------------------------------
# The new prompt — parallax-creating camera motion (VIDEO_CAPTURE_SPEC.md).
# Seed image locks the visual style; prompt drives the motion that COLMAP needs.
# ---------------------------------------------------------------------------

PROMPT = (
    "First-person walkthrough of an endless yellow backrooms corridor, moving slowly "
    "forward while gently weaving side to side and turning the camera to look at the "
    "left and right walls from changing angles, tilting up toward the drop ceiling and "
    "down to the moist carpet tiles, buzzing fluorescent strip lights above. "
    "Consistent rigid geometry, stable lighting, sharp focus, no motion blur, no flicker, "
    "no people, photorealistic, fixed camera lens, liminal and eerie."
)

# ---------------------------------------------------------------------------
# OpenRouter helpers (verbatim from generate_videos.py)
# ---------------------------------------------------------------------------

def headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

def image_data_uri(path: Path) -> str:
    data = path.read_bytes()
    b64  = base64.b64encode(data).decode()
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES    = 5
RETRY_BACKOFF  = [5, 10, 20, 40, 60]


def _urlopen_with_retry(req: urllib.request.Request, label: str) -> bytes:
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body_preview = exc.read(512).decode(errors="replace")
            print(
                f"  HTTP {exc.code} on {label} (attempt {attempt + 1}/{MAX_RETRIES}): "
                f"{exc.reason} — {body_preview}",
                flush=True,
            )
            if exc.code not in RETRY_STATUSES or attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BACKOFF[attempt]
            print(f"  retrying in {delay}s...", flush=True)
            time.sleep(delay)
    raise RuntimeError("unreachable")


def submit(image_uri: str, prompt: str) -> tuple[str, str]:
    payload = json.dumps({
        "model": MODEL_ID,
        "prompt": prompt,
        "duration": DURATION,
        "resolution": RESOLUTION,
        "aspect_ratio": ASPECT,
        "generate_audio": False,
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": image_uri},
                "frame_type": "first_frame",
            }
        ],
    }).encode()

    req = urllib.request.Request(
        f"{BASE_URL}/videos",
        data=payload,
        headers=headers(),
        method="POST",
    )
    body = json.loads(_urlopen_with_retry(req, "submit"))
    return body["id"], body["polling_url"]


def poll(polling_url: str, generation_id: str) -> None:
    while True:
        req = urllib.request.Request(polling_url, headers=headers())
        body = json.loads(_urlopen_with_retry(req, "poll"))
        status = body.get("status", "unknown")
        print(f"  [{generation_id[:12]}] {status}", flush=True)
        if status == "completed":
            return
        elif status in ("failed", "cancelled"):
            raise RuntimeError(f"Job {generation_id} ended with: {status}\n{body}")
        time.sleep(10)


def download(generation_id: str, dest: Path) -> None:
    url = f"{BASE_URL}/videos/{generation_id}/content?index=0"
    req = urllib.request.Request(url, headers=headers())
    with urllib.request.urlopen(req) as resp:
        dest.write_bytes(resp.read())

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not SEED_IMAGE.exists():
        sys.exit(f"ERROR: seed image not found at {SEED_IMAGE}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if OUTPUT_PATH.exists():
        print(f"[SKIP] {OUTPUT_PATH} already exists — move/delete it to regenerate.")
        return

    print(f"Encoding seed image: {SEED_IMAGE.name}")
    image_uri = image_data_uri(SEED_IMAGE)

    print(f"\n[GEN]  corridor_walk  ({MODEL_ID}, {DURATION}s, {RESOLUTION})")
    print(f"       {PROMPT[:80]}...")

    generation_id, polling_url = submit(image_uri, PROMPT)
    print(f"  job submitted → {generation_id[:12]}...")

    poll(polling_url, generation_id)

    print(f"  downloading → {OUTPUT_PATH}")
    download(generation_id, OUTPUT_PATH)
    print(f"  saved {OUTPUT_PATH}")

    print("\nNext: run COLMAP, then gate before training:")
    print("  python3 scripts/splat_pipeline/preflight_parallax.py <colmap sparse/0>")

if __name__ == "__main__":
    main()
