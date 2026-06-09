# Plan: Fix the Splat→Mesh→Collider Handoff in `splat_walk`

**Chainlink milestone #2 — "Splat-Collider Handoff Fix (v1 walkable)"**
`CHAINLINK_DB=/home/user/backrooms-workspace/.chainlink/issues.db`

## Context

The `plan_redirection.md` review concluded **Vista4D does not fix our physics problem** — it is a novel-view *video* tool and never produces collision geometry. The bug that breaks `cargo run --release` ("player floats off the land") lives in the **splat → mesh → collider → alignment** handoff *after* reconstruction, and is a documented, solved problem. We drop Vista4D for v1 and apply the review's Section B fixes directly to the existing Bevy crate `splat_walk`.

`splat_walk` already implements much of Section B: `alignment.rs` (per-scene `alignment.toml` transform), `collision_floor.rs` (RANSAC floor), `collision_spawn.rs` (spawn above floor), `collision_diagnostics.rs` (`SPLAT_COLLISION_DEBUG=1` overlay). Two defects match the symptom:

1. **Collider topology** — the collider is a single monolithic `ColliderConstructor::TrimeshFromMesh` (`splat.rs`). Concave triangle soup tunnels/panics (the recent `corridor_straight trimesh collider panic` fix is a symptom).
2. **Scale never recovered** — `assets/splats/corridor_straight/alignment.toml` is identity rotation, `scale = 1.0`, translation `0`. The alignment ritual (handoff_contract.md §5) was never tuned, so the world may not be metric and the character controller misbehaves even with a good mesh.

**Outcome:** `cargo run --release` on `corridor_straight` spawns the player on the floor and lets them walk without falling through or floating — and emits a clear verdict when something is still off. Staged: a guaranteed floor safety-net first, then full-geometry robustness. Photogrammetry "baked-in physics" is documented as a fallback, not built.

Active scene: `corridor_straight`. Assets present: `scene.ply` (Brush, Y-up), `collision.mesh.glb` (5.5 MB full), `collision_proxy.mesh.glb` (124 KB; preferred by `scene.rs`), `alignment.toml`.

## Parallelism map (for the TL spawning waves)

Conflict analysis is by **owned file** — two issues are parallel-safe only if they edit disjoint files.

| Wave | Issue | Owns (edits) | Parallel with | Blocked by |
|------|-------|--------------|---------------|------------|
| **1** | **#18 Wave A — diagnostics + verdict** | `collision_diagnostics.rs` (+`collision_report.rs`) | #19 | — |
| **1** | **#19 Wave B — safety-net floor** | `splat.rs` (+ optional `scene.rs` flag) | #18 | — |
| **2** | **#20 Wave C — convex segments** | `splat.rs`, `collision_geometry.rs`, new `scripts/splat_pipeline/decompose_collision.*` | #21 | #19 (shared `splat.rs`), #18 (verdict) |
| **2** | **#21 Wave D — alignment ritual** | `corridor_straight/alignment.toml` only (data) | #20 | #18 (needs scale check) |

- **Wave 1 = spawn #18 and #19 together** — disjoint files (`collision_diagnostics.rs` vs `splat.rs`), neither touches `main.rs`. True parallel.
- **Wave 2 = spawn #20 and #21 together** after Wave 1 merges — `splat.rs`/code vs `alignment.toml`/data, disjoint. True parallel.
- #20 must wait for #19 (both edit `splat.rs`) — Chainlink block recorded.
- B's implementation is independent of A; only B's *final verdict=OK check* is a post-merge integration step.

## Chainlink issue tree

```
Milestone #2  Splat-Collider Handoff Fix (v1 walkable)
├─ #18 Wave A: Collision diagnostics + floor verdict   [high]   (Wave 1, ∥ #19)
│   ├─ #22 A1: Downward shapecast floor self-test from spawn
│   ├─ #23 A2: Scale sanity check vs expected real span (SPLAT_EXPECTED_SPAN_M)
│   ├─ #24 A3: Emit verdict line → handoff §6 symptom table
│   └─ #25 A4: Document one-command repro + marker legend
├─ #19 Wave B: RANSAC safety-net floor collider        [high]   (Wave 1, ∥ #18)
│   ├─ #26 B1: Spawn flat static floor collider from FloorEstimate
│   ├─ #27 B2: Gate safety-net behind per-scene flag (SPLAT_SAFETY_FLOOR)
│   └─ #28 B3: Ensure spawn clearance consistent with safety-net Y
├─ #20 Wave C: Convex-decomposition collider segments  [med]    (Wave 2, blocked by #19,#18)
│   ├─ #29 C1: Offline CoACD/V-HACD decomposition script → collision_segments/
│   ├─ #30 C2: Runtime convex-hull colliders per segment
│   ├─ #31 C3: Spatial-chunking fallback
│   └─ #32 C4: Re-verify no wall tunneling via Wave A verdict
└─ #21 Wave D: Alignment/scale ritual                  [med]    (Wave 2, blocked by #18)
    ├─ #33 D1: Measure known real distance against Bevy units
    ├─ #34 D2: Bake measured scale into corridor_straight/alignment.toml
    └─ #35 D3: Re-run verdict, confirm OK
```

Verdict vocabulary (Wave A output, mapped to handoff_contract.md §6):
`FALL_THROUGH | SCALE_WRONG | UP_AXIS_WRONG | SPLAT_COLLIDER_OFFSET | MESH_HOLES | OK`

## Per-wave specs (summary; full detail in each Chainlink issue `-d`)

**#18 Wave A — diagnostics (gating).** Extend `collision_diagnostics.rs`: downward shapecast (Avian `SpatialQuery`) from resolved spawn → hit / distance / collider name; scale sanity vs `SPLAT_EXPECTED_SPAN_M`; print one verdict line; document `SPLAT_COLLISION_DEBUG=1 SPLAT_SCENE=corridor_straight cargo run --release`. **DO NOT** touch `splat.rs`/`main.rs`.

**#19 Wave B — safety-net floor (ship first).** In `splat.rs`, for `Real` scenes, additionally spawn a thin `Collider::cuboid` sized to aligned XZ-bounds at `floor.point.y`, `Static`, `Visibility::Hidden` (reuse `collision_spawn::estimate_scene_floor`). Gate via `SPLAT_SAFETY_FLOOR` (default on). Keep trimesh for walls. **DO NOT** touch `collision_diagnostics.rs`. PR: `feat: add RANSAC-derived safety-net floor collider`.

**#20 Wave C — convex segments (after B+A).** Offline CoACD (fallback V-HACD) → convex GLBs into `collision_segments/` (loader in `scene.rs` already enumerates them). Runtime: load each segment as a convex `Collider` instead of one `TrimeshFromMesh`. Chunking fallback if CoACD unavailable. PR: `feat: convex-decomposition collider segments`.

**#21 Wave D — alignment ritual (after A).** Data-only: measure a known real distance with `SPLAT_COLLISION_DEBUG=1` + Wave A scale check; bake the measured `scale` (and rotation/translation if floor ≠ y=0) into `corridor_straight/alignment.toml`. **DO NOT** edit any `.rs`.

## Backup plan (documented, not built): Photogrammetry "baked-in physics"

Per redirection plan Section D Path 2/3. If the splat collision handoff stays unreliable after Waves A–D, switch the *collider source* to a photogrammetry textured mesh, where **the mesh is the collider for free**:
- **Pipeline:** same source video → Meshroom / RealityScan → textured triangle mesh → `decimate_to_glb.py` (exists) → `collision.mesh.glb`. Continuous surface, no splat-extraction gaps.
- **Engine:** no `splat_walk` code change — drop the mesh in as the scene's `collision.mesh.glb`; existing loader/collider path consumes it. Optionally keep the Gaussian splat on top for visuals (Section D Path 3 hybrid: visible splat + invisible collider).
- **Trigger:** Wave A keeps reporting `MESH_HOLES`/`SPLAT_COLLIDER_OFFSET` that Waves B/C cannot close.
- **Cost:** loses splat fidelity on the collider mesh, but output quality is explicitly not a priority and physics is guaranteed.

## Critical files

- `splat_walk/src/collision_diagnostics.rs` — Wave A (extend).
- `splat_walk/src/splat.rs` — Wave B safety-net floor; Wave C segment/convex colliders.
- `splat_walk/src/collision_floor.rs`, `collision_spawn.rs`, `collision_report.rs` — reuse `FloorEstimate` (no rewrite).
- `splat_walk/src/scene.rs` — `collision_segments/` loading already present (reuse for Wave C).
- `splat_walk/assets/splats/corridor_straight/alignment.toml` — Wave D values.
- `scripts/splat_pipeline/decimate_to_glb.py`, `extract_mesh.sh`, new `decompose_collision.*` — Wave C/D offline steps.
- `splat-handoff/handoff_contract.md` §5–§6 — alignment ritual + symptom table (authoritative reference).

## End-to-end verification

1. `cd splat_walk && cargo build --release && cargo test`.
2. `SPLAT_COLLISION_DEBUG=1 SPLAT_SCENE=corridor_straight cargo run --release` — read the verdict line; confirm floor/spawn/collider markers align with the splat.
3. Walk (WASD) across the corridor and into walls: **no fall-through, no floating, no tunneling**.
4. Verdict reads `OK`; spawn-to-floor gap logged near zero.
