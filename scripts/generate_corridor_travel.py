#!/usr/bin/env python3
"""
generate_corridor_travel.py — NEAR-FIELD-parallax corridor clip for the splat pipeline.

Third iteration of the corridor capture. Same video model and OpenRouter params as
generate_videos.py (google/veo-3.1-lite, 1080p, 16:9, no audio, first-frame seed) —
only the prompt and DURATION change.

WHY THIS EXISTS (proven from two prior clips, see VIDEO_CAPTURE_SPEC.md):
  - Clip 1 (straight dolly, 4s):  lateral/fwd 2.2%,  near-field 41%,  tri-angle 5.7deg
  - Clip 2 (weave + look, 4s):    lateral/fwd 86%,   near-field 8.2%, tri-angle 4.0deg
  Both FAILED the parallax gate. The lesson is NOT "rotate more" — clip 2 rotated very
  little and TRANSLATED plenty (baseline 12.8) yet still failed. The real culprit is
  FAR-FIELD content: a straight backrooms hallway is mostly distant wall near the
  vanishing point, and distant points subtend <5deg no matter how far the camera moves
  (reprojection error was clean at 1.29px, so it's geometry, not AI warping).

  The lever is NEAR-FIELD parallax: keep textured surfaces CLOSE to the lens and move
  LATERALLY past them (hug one wall, cross to the other, round a corner). Do NOT center
  the open vanishing point. That is why the previous "always faces straight forward"
  prompt was wrong and has been replaced.

DURATION is 8s (the model's typical max) to give the camera room to traverse the width
and round a corner. If the API rejects 8, that tells us the cap — drop it back down.

Usage:
    python3 scripts/generate_corridor_travel.py

Output:
    data/scenes/corridor_travel/video.mp4
Then verify (note the matching scene dir):
    conda activate nerfstudio
    scripts/splat_pipeline/colmap_and_gate.sh \
        data/scenes/corridor_travel/video.mp4 data/scenes/corridor_travel
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
# Config — same model + params as generate_videos.py; DURATION bumped to 8.
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    sys.exit("ERROR: OPENROUTER_API_KEY environment variable not set")

SEED_IMAGE  = Path(__file__).parent.parent / "Backrooms_model.jpg"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "scenes" / "corridor_travel" / "video.mp4"
MODEL_ID    = "google/veo-3.1-lite"
BASE_URL    = "https://openrouter.ai/api/v1"
DURATION    = 8            # seconds — room to traverse the width and round a corner
RESOLUTION  = "1080p"
ASPECT      = "16:9"

# ---------------------------------------------------------------------------
# The new prompt — NEAR-FIELD parallax. Camera stays close to textured surfaces
# and moves laterally past them, rounding a corner. It does NOT center the open
# vanishing point (that far-field shot is exactly what failed in clip 2).
# ---------------------------------------------------------------------------

PROMPT = (
    "First-person camera travels forward through a yellow backrooms corridor while "
    "drifting from one wall to the other, passing within arm's reach of the walls, a "
    "door frame, and wall fixtures so nearby textured surfaces fill much of the frame, "
    "then rounding a corner into a connecting hallway. The camera stays close to the "
    "walls and never lingers on a distant empty vanishing point. Smooth steady gimbal "
    "motion, moist carpet tiles underfoot, buzzing fluorescent strip lights overhead, "
    "drop ceiling, no windows, no people. Consistent rigid geometry, stable lighting, "
    "sharp focus, no motion blur, no flicker, photorealistic, fixed camera lens, "
    "liminal and eerie."
)

# ---------------------------------------------------------------------------
# OpenRouter helpers (verbatim from generate_videos.py)
# ---------------------------------------------------------------------------

def headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

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
        f"{BASE_URL}/videos", data=payload, headers=headers(), method="POST",
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

    print(f"\n[GEN]  corridor_travel  ({MODEL_ID}, {DURATION}s, {RESOLUTION})")
    print(f"       {PROMPT[:80]}...")

    generation_id, polling_url = submit(image_uri, PROMPT)
    print(f"  job submitted → {generation_id[:12]}...")
    poll(polling_url, generation_id)
    print(f"  downloading → {OUTPUT_PATH}")
    download(generation_id, OUTPUT_PATH)
    print(f"  saved {OUTPUT_PATH}")

    print("\nNext: verify parallax before training:")
    print(f"  scripts/splat_pipeline/colmap_and_gate.sh {OUTPUT_PATH} {OUTPUT_PATH.parent}")

if __name__ == "__main__":
    main()
