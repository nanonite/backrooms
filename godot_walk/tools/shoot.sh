#!/usr/bin/env bash
# Render a Godot scene through screenshot_scene.gd.
# Uses a real rendering driver, not plain --headless. When DISPLAY is missing,
# xvfb-run provides an X server; Vulkan is tried first, then opengl3 if Vulkan
# fails or reports device/context creation errors.

set -euo pipefail

SCENE_PATH="${1:-res://scenes/corridor.tscn}"
GODOT_BIN="${GODOT_BIN:-godot4}"
RESOLUTION="${SHOT_RESOLUTION:-1280x720}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCREENSHOT_DIR="$PROJECT_DIR/screenshots"
mkdir -p "$SCREENSHOT_DIR"

usage() {
    cat <<'EOF'
Usage: shoot.sh [scene_path]

  scene_path defaults to res://scenes/corridor.tscn.

Environment:
  GODOT_BIN          Godot executable to run (default: godot4)
  SHOT_RESOLUTION    Render resolution, WIDTHxHEIGHT (default: 1280x720)
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

command -v "$GODOT_BIN" >/dev/null 2>&1     || { echo "ERROR: $GODOT_BIN not found in PATH" >&2; exit 2; }

run_with_display() {
    local driver="$1"
    local log_path="$SCREENSHOT_DIR/shoot-${driver}.log"
    local -a cmd=(
        "$GODOT_BIN"
        --path "$PROJECT_DIR"
        --rendering-driver "$driver"
        --resolution "$RESOLUTION"
        --script res://scripts/screenshot_scene.gd
        -- "$SCENE_PATH"
    )

    if [[ -z "${DISPLAY:-}" ]]; then
        command -v xvfb-run >/dev/null 2>&1             || { echo "ERROR: DISPLAY is unset and xvfb-run is not installed" >&2; return 127; }
        cmd=(xvfb-run -a -s "-screen 0 ${RESOLUTION}x24" "${cmd[@]}")
    fi

    echo "Running ${driver} capture for ${SCENE_PATH}"
    set +e
    "${cmd[@]}" > >(tee "$log_path") 2> >(tee -a "$log_path" >&2)
    local rc=$?
    return "$rc"
}

should_retry_opengl3() {
    local rc="$1"
    local log_path="$SCREENSHOT_DIR/shoot-vulkan.log"
    if [[ "$rc" -ne 0 ]]; then
        return 0
    fi
    grep -Eq "ERR_CANT_CREATE|rendering_context_driver_vulkan|Vulkan" "$log_path"
}

set +e
run_with_display vulkan
vulkan_rc=$?
set -e

if should_retry_opengl3 "$vulkan_rc"; then
    echo "Vulkan capture failed or reported context creation trouble; retrying opengl3." >&2
    set +e
    run_with_display opengl3
    opengl_rc=$?
    set -e
    exit "$opengl_rc"
fi

exit "$vulkan_rc"
