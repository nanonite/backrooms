# Backrooms Infinite

PS1-style horror game built in Bevy 0.15 (Rust). Procedurally generated infinite backrooms environment with WFC dungeon layout, Rapier physics, and low-resolution retro rendering effects.

## Tech Stack

| Crate | Purpose |
|-------|---------|
| `bevy` 0.15 | Game engine |
| `ghx_proc_gen` 0.8 | WFC dungeon layout |
| `bevy_rapier3d` 0.27 | Physics + collision |
| `noise` 0.9 | Perlin/simplex variation |
| `fastrand` 2.0 | Seeded deterministic RNG |

## Build and Test

```bash
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
