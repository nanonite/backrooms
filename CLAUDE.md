# Backrooms Infinite

Video-sourced walkable Gaussian splat in Bevy 0.18 (Rust). Pipeline: video → COLMAP/VGGT → Brush (splat) → SuGaR (collision mesh) → Bevy first-person controller.

## Crate

`splat_walk/` — lives at the workspace root (`/home/user/backrooms-workspace/splat_walk/`).

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

## Issue Tracking

Chainlink is the issue tracker. Before doing anything, read all files in `.chainlink/rules/`:

```bash
.chainlink/rules/global.md
.chainlink/rules/tracking-normal.md
.chainlink/rules/quality.md
.chainlink/rules/rust.md
```

## PR Workflow

There is no GitHub remote. Do NOT use `gh` commands — they will fail.

- PRs are tracked locally in `.exo/prs.json`
- Workers file PRs via the `file_pr` MCP tool
- Review feedback is written to `.exo/reviews/pr_{N}.json` via `request_changes` / `approve_pr`
- The worktree event watcher delivers feedback to workers and notifies the TL automatically
