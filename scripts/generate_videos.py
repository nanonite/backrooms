#!/usr/bin/env python3
"""
generate_videos.py — Backrooms video clip generator
Uses OpenRouter Seedance 2.0 image-to-video to produce one clip per module type.
Seed image: Backrooms_model.jpg (repo root)

API flow (OpenRouter video generation):
  1. POST  /api/v1/videos          → returns generation_id + polling_url
  2. GET   /api/v1/videos/{id}     → poll until status == "completed"
  3. GET   /api/v1/videos/{id}/content?index=0  → download mp4

Usage:
    python3 scripts/generate_videos.py

Requires OPENROUTER_API_KEY in environment (already set in this session).

Output:
    data/videos/corridor_straight.mp4
    data/videos/corridor_corner.mp4
    data/videos/corridor_t.mp4
    data/videos/corridor_x.mp4
    data/videos/room_large.mp4
    data/videos/dead_end.mp4
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
# Config
# ---------------------------------------------------------------------------

API_KEY    = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    sys.exit("ERROR: OPENROUTER_API_KEY environment variable not set")

SEED_IMAGE = Path(__file__).parent.parent / "Backrooms_model.jpg"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "videos"
MODEL_ID   = "google/veo-3.1-lite"
BASE_URL   = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Module definitions — one clip per room module type.
# Prompt drives camera motion; seed image locks the visual style.
# ---------------------------------------------------------------------------

MODULES = [
    {
        "name": "corridor_straight",
        "prompt": (
            "Camera slowly dollies forward through an endless yellow backrooms corridor, "
            "moist carpet tiles underfoot, buzzing fluorescent strip lights above, "
            "drop ceiling, no windows, no people, liminal space, eerie."
        ),
    },
    {
        "name": "corridor_corner",
        "prompt": (
            "Camera pans 90 degrees left in a yellow backrooms hallway, revealing another "
            "identical corridor turning away into the distance, fluorescent lights flickering, "
            "moist carpet, drop ceiling, no people."
        ),
    },
    {
        "name": "corridor_t",
        "prompt": (
            "Camera slowly pulls back in a yellow backrooms T-junction, revealing three "
            "branching hallways each receding into darkness, fluorescent lights, moist carpet, "
            "drop ceiling, no people, liminal dread."
        ),
    },
    {
        "name": "corridor_x",
        "prompt": (
            "Camera rotates 360 degrees in place at a 4-way backrooms intersection, "
            "four identical yellow corridors radiating outward, fluorescent hum, moist carpet, "
            "drop ceiling, no people."
        ),
    },
    {
        "name": "room_large",
        "prompt": (
            "Camera slowly pans across a large open backrooms room, yellow carpet tiles, "
            "fluorescent strip lights in a grid pattern overhead, drop ceiling, empty walls, "
            "no furniture, no windows, no people, oppressive emptiness."
        ),
    },
    {
        "name": "dead_end",
        "prompt": (
            "Camera dollies slowly toward a blank wall at the end of a yellow backrooms "
            "corridor, fluorescent lights above, moist carpet, drop ceiling. "
            "The wall fills the frame — nowhere left to go."
        ),
    },
]

# ---------------------------------------------------------------------------
# OpenRouter helpers
# ---------------------------------------------------------------------------

def headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

def image_data_uri(path: Path) -> str:
    """Encode image as a data URI for inline submission."""
    data = path.read_bytes()
    b64  = base64.b64encode(data).decode()
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return f"data:{mime};base64,{b64}"

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES    = 5
RETRY_BACKOFF  = [5, 10, 20, 40, 60]  # seconds between attempts


def _urlopen_with_retry(req: urllib.request.Request, label: str) -> bytes:
    """urlopen with retry on transient HTTP errors. Returns response bytes."""
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
    """
    POST /api/v1/videos
    Returns (generation_id, polling_url).
    """
    payload = json.dumps({
        "model": MODEL_ID,
        "prompt": prompt,
        "duration": 4,
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "generate_audio": False,  # audio out of scope
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

    generation_id = body["id"]
    polling_url   = body["polling_url"]
    return generation_id, polling_url

def poll(polling_url: str, generation_id: str) -> None:
    """Poll until status == 'completed'. Raises on failure."""
    while True:
        req = urllib.request.Request(polling_url, headers=headers())
        body = json.loads(_urlopen_with_retry(req, "poll"))

        status = body.get("status", "unknown")
        print(f"  [{generation_id[:12]}] {status}", flush=True)

        if status == "completed":
            return
        elif status in ("failed", "cancelled"):
            raise RuntimeError(f"Job {generation_id} ended with: {status}\n{body}")

        time.sleep(10)  # video generation takes 30–120 s

def download(generation_id: str, dest: Path) -> None:
    """GET /api/v1/videos/{id}/content?index=0 → save mp4."""
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

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Encoding seed image: {SEED_IMAGE.name}")
    image_uri = image_data_uri(SEED_IMAGE)

    for module in MODULES:
        name   = module["name"]
        prompt = module["prompt"]
        dest   = OUTPUT_DIR / f"{name}.mp4"

        if dest.exists():
            print(f"[SKIP] {name}.mp4 already exists")
            continue

        print(f"\n[GEN]  {name}")
        print(f"       {prompt[:80]}...")

        generation_id, polling_url = submit(image_uri, prompt)
        print(f"  job submitted → {generation_id[:12]}...")

        poll(polling_url, generation_id)

        print(f"  downloading → {dest.name}")
        download(generation_id, dest)
        print(f"  saved {dest}")

    print("\nDone. Run task #3 (extract textures) next.")
    print(f"Videos at: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
