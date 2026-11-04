# Backrooms Infinite

Video-sourced walkable Gaussian splat in Bevy 0.18 (Rust). Pipeline: video → COLMAP/VGGT → Brush (splat) → SuGaR (collision mesh) → Bevy first-person controller.

## Crate

`splat_walk/` — lives at the workspace root.

## Tech Stack

| Crate | Purpose |
|-------|---------|
| `bevy` 0.18 | Game engine |
| `avian3d` 0.6 | Physics + collision (NOT rapier) |
| `bevy-tnua` 0.31 | Character controller |
| `bevy-tnua-avian3d` 0.11 | tnua ↔ avian bridge (PIL ^0.12) |
| `bevy_gaussian_splatting` 7 | Gaussian splat renderer (default-features=false) |

## Build and Test

```bash
# run from splat_walk/
cargo check              # Fast syntax + type check (preferred for iteration)
cargo clippy             # Lint
cargo test               # Unit tests
cargo build              # Full build
```

## Testing Constraints — All Agents

**Agents cannot run the game or observe visual output.** There is no display or GPU available in the agent environment. This applies to TL agents, workers, and reviewers equally.

Acceptable verification:
- `cargo check` — catches type errors and misuse of APIs
- `cargo clippy` — catches logic issues linters can find
- `cargo test` — unit tests only
- Code review of logic, data flow, and Bevy system ordering

Not acceptable:
- Running `cargo run` and observing behavior
- Expecting visual correctness to be verified
- Requesting a worker "test the game"

If a change can only be verified visually (e.g., shader effects, rendering pipeline), note it as "requires human visual verification" in the PR description. Do not block the PR on it.

## Godot (`godot_walk/`) verification

The constraint above applies to the Bevy crate. On this workstation (RTX 4070 Ti, `DISPLAY=:1`), agents working on `godot_walk/` *can* run Godot and inspect its output:

- **Headless checks:** `godot4 --headless --path godot_walk --script res://scripts/test_issue183_shape_rooms.gd -- --map=... --rooms=...`, plus `python3 -m pytest -q godot_walk/scripts`.
- **Render captures:** `godot4 --path godot_walk --rendering-driver vulkan --resolution 960x540 --script res://scripts/capture_diagonal_passage.gd -- --map=... --rooms=... --out=<dir>`. Then view the PNGs. Render before asking the operator to walk a map.
- **godot-mcp (#197):** an MCP server named `godot`, installed system-wide for Claude Code, Codex and OpenCode. The install is pinned at `~/.local/share/godot-mcp` (commit 1209744).
  - Use `run_project` → `get_debug_output` → `stop_project` to catch runtime script errors.
  - `run_project` cannot pass user args. Write `godot_walk/.walk_target.json` (gitignored) as `{"map": "res://...json", "rooms": "res://.../index.json"}`, then run scene `res://scenes/generative_map_walkthrough.tscn`. An explicit `-- --map= --rooms=` still takes precedence.
  - It takes no screenshots; use the capture scripts above for visuals.
  - Never use its scene-editing tools (`create_scene`, `add_node`, `save_scene`, `load_sprite`, `export_mesh_library`, `update_project_uids`) on library rooms, `catalog.json`, `scripts/player.gd`, `project.godot` or `room_catalog/MATERIAL_LANGUAGE.md`. Frozen evidence hashes pin those files.

The operator still walks and approves each map; a capture or a clean debug log is not approval.

## Source Control

The only remote is `github` (`git@github.com:nanonite/backrooms.git`); push with `git push github main`. Use plain `git` commands only. Do NOT use the `gh` CLI. Issue tracking stays in chainlink.
