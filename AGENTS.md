# AGENTS.md — Backrooms / splat_walk

## 1. Security (Priority 1)

- **SQL**: Parameterized queries only (`params![]` in Rust). Never interpolate user input.
- **Secrets**: Never hardcode credentials, API keys, or tokens. Never commit `.env` files.
- **Input validation**: Validate at system boundaries. Sanitize before rendering.
- **No stubs**: Never write `TODO`, `FIXME`, `pass`, `...`, `unimplemented!()`. If too complex, use `raise NotImplementedError("Reason")`.

---

## 2. Correctness (Priority 2)

- **Read before write**: Always read a file before editing. Never guess at contents.
- **Complete features**: Implement the full feature as requested. Don't stop partway.
- **Error handling**: Proper error handling everywhere. No panics on bad input.
- **No dead code**: Remove hallucinated functions. Complete unfinished functions.
- **Test after changes**: Run the project's test suite after making code changes.
- **Verify APIs exist**: WebSearch to confirm library APIs before using them. Check current stable versions.

---

## 3. Code Quality

- One concept per file. Split at ~200 lines.
- Functions under 25 lines, max 3 levels of indentation.
- Names reveal intent. No abbreviations.
- Guard clauses and early returns.
- Inject dependencies, don't reach out.
- Extract magic values to named constants.

---

## 4. Rust-Specific Rules

- Use `rustfmt` (`cargo fmt`) and `clippy` (`cargo clippy -- -D warnings`)
- Prefer `?` over `.unwrap()`. Use `anyhow::Result` for app errors.
- Avoid `.clone()` unless necessary.
- Never use `unsafe` without explicit justification.
- Run `cargo test` before committing.

---

## 5. Workflow (Priority 3)

- Write code, don't narrate. Skip "Here is the code" / "Let me..." / "I'll now..."
- Brief explanations only when the code isn't self-explanatory.
- For implementations >500 lines: work incrementally, in logically complete chunks.

---

## 6. Project: Backrooms / splat_walk

Video-sourced walkable Gaussian splat in Bevy 0.18 (Rust). See `PLAN.md` for the current milestone plan and `splat-handoff/` for per-step scaffolding docs.

**Crate:** `splat_walk/` at workspace root (`$HOME/backrooms-workspace/splat_walk/`).
The old `backrooms_infinite/` WFC crate was deleted — do not recreate it.

### Current Milestone

**Milestone #10: Video → Walkable Gaussian Splat** — see `PLAN.md` for issue table and build order.

### Environment Setup (run once before any front-end pipeline work)

The front-end pipeline requires four tools not in the conda env: **GLOMAP**, **Brush**, **VGGT**, **SuGaR**.
COLMAP 3.10 and Python/PyTorch deps are already in the `nerfstudio` conda env.

```bash
# 1. Enter the Nix dev shell (provides cmake, Rust, C++ deps for GLOMAP/Brush)
nix develop

# 2. Install all four missing tools (~10–20 min first time)
./environment/setup-pipeline-tools.sh

# 3. Confirm everything is present before running pipeline scripts
./environment/setup-pipeline-tools.sh status
```

Individual installs if only one tool is missing:
```bash
./environment/setup-pipeline-tools.sh install-glomap   # C++ build from source
./environment/setup-pipeline-tools.sh install-brush    # cargo install brush-app
./environment/setup-pipeline-tools.sh install-vggt     # git clone + conda pip
./environment/setup-pipeline-tools.sh install-sugar    # git clone + conda pip
```

Binaries land in `$HOME/.local/bin/`. The Nix shell and `setup-pipeline-tools.sh`
both prepend this to `PATH` automatically.

**Video resolution requirement:** pipeline scripts require 1080p+ input. All current
captures in `data/videos/` are 720p and will be rejected at Stage A validation.
New captures must be shot at 1080p minimum before INT-4 (#109) can run end-to-end.

### Asset Pipeline

```
data/videos/<capture>.mp4
  → ffmpeg frames → COLMAP/VGGT → Brush (scene.ply) → SuGaR (collision.glb)
  → splat_walk/assets/splats/<scene>/{scene.ply, collision.glb, alignment.toml}
```

### Key Dependencies

| Crate | Version | Purpose |
|-------|---------|---------|
| `bevy` | 0.18 | Game engine |
| `avian3d` | 0.6 | Physics + collision (NOT rapier) |
| `bevy-tnua` | 0.31 | Character controller |
| `bevy-tnua-avian3d` | 0.11 | tnua ↔ avian bridge (PIL ^0.12) |
| `bevy_gaussian_splatting` | 7 | Splat renderer (default-features=false) |
