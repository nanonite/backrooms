#!/usr/bin/env bash

# Verify the GDGS demo on a real desktop Vulkan session.
set -euo pipefail

GODOT_BIN="${GODOT_BIN:-godot4}"
RESOLUTION="${SHOT_RESOLUTION:-1280x720}"
TIMEOUT_SECONDS="${GDGS_VERIFY_TIMEOUT_SECONDS:-90}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENE_PATH="res://scenes/gdgs_demo.tscn"
DEMO_PLY="$PROJECT_DIR/assets/gdgs_demo/demo.compressed.ply"
SCREENSHOT_DIR="$PROJECT_DIR/screenshots"
LOG_PATH="$SCREENSHOT_DIR/gdgs-demo-vulkan.log"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_desktop_display() {
    [[ -n "${DISPLAY:-}" ]] || fail "DISPLAY is unset. Run this from the real desktop GPU session, not headless/xvfb."
    [[ "${DISPLAY}" != :99* ]] || fail "DISPLAY looks like xvfb (${DISPLAY}). GDGS proof requires the real desktop GPU session."
}

require_demo_asset() {
    [[ -s "$DEMO_PLY" ]] || fail "Missing local demo splat: $DEMO_PLY"
}

run_capture() {
    mkdir -p "$SCREENSHOT_DIR"
    rm -f \
        "$SCREENSHOT_DIR/overhead_orbit.png" \
        "$SCREENSHOT_DIR/player_pov.png" \
        "$SCREENSHOT_DIR/top_down.png" \
        "$LOG_PATH"

    command -v "$GODOT_BIN" >/dev/null 2>&1 || fail "$GODOT_BIN not found in PATH"
    command -v timeout >/dev/null 2>&1 || fail "timeout command not found"

    echo "Running GDGS Vulkan capture for $SCENE_PATH"
    timeout "${TIMEOUT_SECONDS}s" \
        "$GODOT_BIN" \
        --path "$PROJECT_DIR" \
        --rendering-driver vulkan \
        --resolution "$RESOLUTION" \
        --script res://scripts/screenshot_scene.gd \
        -- "$SCENE_PATH" \
        > >(tee "$LOG_PATH") \
        2> >(tee -a "$LOG_PATH" >&2)
}

reject_fallback_renderer() {
    if grep -Eiq "switching to OpenGL 3|OpenGL API|Compatibility|llvmpipe|ERR_CANT_CREATE|rendering_context_driver_vulkan" "$LOG_PATH"; then
        fail "Godot did not stay on the real Vulkan/Forward+ path. See $LOG_PATH"
    fi
}

check_nonblank_images() {
    python3 - "$SCREENSHOT_DIR" <<'PY'
import struct
import sys
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
EXPECTED = ["overhead_orbit.png", "player_pov.png", "top_down.png"]
MIN_CHANGED_PIXELS = 64


def read_png_pixels(path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"{path.name}: not a PNG")
    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        chunk_type = data[offset + 4:offset + 8]
        chunk_data = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if bit_depth != 8 or color_type not in (0, 2, 6):
        raise ValueError(f"{path.name}: unsupported PNG format bit_depth={bit_depth} color_type={color_type}")
    channels = {0: 1, 2: 3, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows = []
    previous = [0] * stride
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = list(raw[cursor:cursor + stride])
        cursor += stride
        for index, value in enumerate(row):
            left = row[index - channels] if index >= channels else 0
            up = previous[index]
            up_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                row[index] = (value + left) & 0xFF
            elif filter_type == 2:
                row[index] = (value + up) & 0xFF
            elif filter_type == 3:
                row[index] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[index] = (value + paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise ValueError(f"{path.name}: unsupported PNG filter {filter_type}")
        rows.append(row)
        previous = row
    pixels = []
    for row in rows:
        for index in range(0, stride, channels):
            if color_type == 0:
                value = row[index]
                pixels.append((value, value, value))
            else:
                pixels.append(tuple(row[index:index + 3]))
    return width, height, pixels


def paeth(left, up, up_left):
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def changed_pixel_count(pixels):
    background = pixels[0]
    return sum(1 for pixel in pixels if pixel != background)


root = Path(sys.argv[1])
ok = True
for name in EXPECTED:
    path = root / name
    if not path.exists():
        print(f"FAIL: missing screenshot {path}", file=sys.stderr)
        ok = False
        continue
    width, height, pixels = read_png_pixels(path)
    changed = changed_pixel_count(pixels)
    unique = len(set(pixels))
    print(f"{name}: {width}x{height} unique={unique} changed_from_background={changed}")
    if changed < MIN_CHANGED_PIXELS:
        print(f"FAIL: {name} is blank or background-only", file=sys.stderr)
        ok = False
if not ok:
    raise SystemExit(1)
PY
}

require_desktop_display
require_demo_asset
run_capture
reject_fallback_renderer
check_nonblank_images

echo "OK: GDGS demo rendered nonblank screenshots on Vulkan"
