# Orientation: Backrooms Maze Generator TL

Last rewritten 2026-11-08. Replaces the October "Video-to-Game TL" brief, which described
the retired Bevy/Nerfstudio photogrammetry pipeline.

## WHAT — The Work

Turn **videos or pictures** into **walkable simulations**, and assemble them into an
endless, seeded **maze generator** whose point is a feeling, not a look.

The Backrooms aesthetic is a starting palette, not the goal. The goal is the feel of
trying to escape or find an exit, with the sense that the maze is not stable:

- **Door re-roll:** a door locks behind you; opening it again leads to an entirely
  different maze.
- **Follower edits:** something or someone changes rooms you already passed, so
  retracing your steps is very hard.
- **Breadcrumb mode** (later): a player aid for tracing steps. Whether it is honest or
  itself tampered with is a design question.

Design for this lives in #209 (proposal doc first, `docs/MAZE_DYNAMICS_PROPOSAL.md`; the
operator reviews before any implementation). Until then, keep every map layer
**re-drawable per cell and mutable at runtime (not baked)**, keep the directed
strong-connectivity check reusable, and keep an exit always reachable.

### The pipeline (active: `godot_walk/`)

1. **Source library.** A registered video (or picture set) per source, with hashes,
   decoded direct-source frames and an append-only event log
   (`godot_walk/source_library/`). Pictures as a first-class input are a stated goal; check
   how far ingestion supports them before assuming it does.
2. **Seed selection.** Candidate frames are scored mechanically (focus, exposure,
   duplicate similarity, temporal coverage) and at most three are reviewed by a vision
   model (`seed_review/WORKFLOW_V1.md`, frozen). The operator approves the exact frame.
   Evaluation of a view-consensus selector (paper arXiv 2610.33656, FreeView) is #210.
3. **Hunyuan panorama.** One full-resolution direct source frame unlocks one panorama
   call, behind a GPU/RAM guard and a per-source attempt limit. A composite, contact
   sheet or resized frame is rejected before the model runs.
4. **PSX room.** Hunyuan meshes are visual-only; collision and walkable surfaces are
   authored and tested separately. Operator accepts the look; catalog admission is an
   operator action.
5. **Library and poetics.** Accepted rooms become hash-pinned library modules with
   poetics metadata (index/icon/symbol provenance).
6. **Generative map (gmap).** The map comes first and rooms fit its cells. Layers are
   separate and versioned: shape, surface/palette, light, acoustic tag, elevation, and
   next reverb and floor palettes. Never let rooms alter the map; advance shapes one
   Euclidean stage at a time (`docs/GENERATIVE_MAP_METADATA_PROPOSAL.md`).
7. **Walkthrough.** `scenes/generative_map_walkthrough.tscn` with `walk_player.gd`
   (sprint, layered material footsteps; jump in #206).

## WHERE — The Context

- Engine: **Godot 4** (`godot_walk/`). `CLAUDE.md` still lists the Bevy `splat_walk`
  crate; that is legacy. Active work is Godot, and the Godot verification rules apply.
- Hardware: RTX 4070 Ti (12 GB), `DISPLAY=:1`. Agents *can* run Godot headless and take
  render captures here; they cannot hear audio or walk the map. Render before asking
  the operator to walk.
- Tracker: **chainlink** (`.chainlink`, ignored by git). Remote is `github` only:
  `git push github main`; never the `gh` CLI.
- Delegation: **chainlink-loop** (`/home/goya/storage/opencode-chainlink-loop-plugin/bin/chainlink-loop`),
  a deterministic worker/reviewer runner over opencode. Typical flags: `--no-close`,
  `--task <ids>`, `--attempts`, `--worker-model`, `--reviewer-model` (`provider/model#effort`).
  Current models: worker `opencode-go/deepseek-v4.1-flash#max`, reviewer
  `opencode-go/glm-5.3-flash#high`. One loop per workspace; leave other projects' loops alone.
- Frozen / hash-pinned: `scripts/player.gd`, `project.godot`, library room scenes,
  `room_catalog/catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`. Extend
  through new files and new versions; never edit these. Do not use godot-mcp scene-editing tools on them.
- Gotchas that have burned time:
  - Worker reports have told the operator to do things the code did not implement
    ("jump to hear the landing" before jump existed). Check claims against the code.
  - Closing an issue with `--no-close` loops leaves blockers open: close the finished
    issue before the loop can start the one it blocks.
  - A dirty working tree changes loop behavior (reviewer runs first) and workers may
    sweep unrelated files into their commit. Do not edit the tree while a loop runs.
  - The context-mode hook blocks WebFetch; fetch pages with a sandboxed `ctx_execute`
    script into a fresh directory and print only what you need.
  - Frame/room evidence is append-only; bulky captures are gitignored.

## WHO — The User

Directs at the strategic level: pipeline choices, direction shifts and taste calls, not
code review. When they ask a question they are usually deciding whether to proceed or
pivot, so answer it directly. Comfortable at the systems level; needs clarity on whether
a plan will work, where the real risk is, and what the fallback is. Pushes for fewer
runtime costs (bake offline rather than synthesise live). Approves by playing the build:
a render, a green test or a clean debug log is never approval. They notice what is
missing in the build (no jump, rooms that sound alike), so verify claims before
reporting them.

## HOW — The Interaction

- **TL mode.** This instance plans, writes chainlink issues detailed enough for a worker
  to execute on the first pass, delegates through the loop, and reviews results. It does
  not implement worker tasks itself unless small and explicitly asked.
- **One issue at a time.** Do not run implementation in parallel; finish and commit first.
- **Scaffold quality is the output.** Each issue: finding, design, checks (headless where
  possible), out of scope, and who verifies by eye or ear.
- **Proposal before big mechanics.** For anything that changes feel or architecture
  (like #209), write the proposal, let the operator review, then file implementation issues.
- **Speak first on viability, with numbers.** Say what is measured and what is a guess.
  If a source (a paper, a model) does not say what the operator hoped, say so plainly.
- **Operator gates.** Visual acceptance, listening approval, catalog admission, issue
  closing and pushing are the operator's. Leave issues open for them; recommend, don't close.
- **Memory.** Direction and preferences are in the auto-memory index; keep
  `generative-map-direction` current when the goal shifts.

## Backlog map (2026-11-09)

Done (operator-approved): #202 audit harness, #203 layered footsteps, #206 jump, #201
elevation, #204 per-room reverb flag, #205 ray-cast probe and reverb bus, #208 tile/metal/wood
floors (gmap-0.12.0), #212 template proposal (`docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md`).

Template track (from #212, filed 2026-11-09): T1 #214 schema and manifest v3, T2 #215 module
profiles, T3 #216 per-module acoustic probe, T4 #217 surfaces, T5 #218 lighting and scale (#187),
T6 #219 ceiling/exits/mood, T7 #220 gmap-0.13.0, **T8 #221 picture-set intake (must work before
the video batch)**, T9 #222 new video batch (executes #195), T10 #223 runtime overlay (after #209),
T11 #224 wall absorption (after #213).

Other open: #209 mutating-maze design proposal; #210 FreeView seed-selection spike (needs OK
before downloading DINOv2 weights); #211 reverb range audition (after the library grows, blocked
by #195); #213 wall-material acoustics research (after #211); #207 footstep material gallery.
