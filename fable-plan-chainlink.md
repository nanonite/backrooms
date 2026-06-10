# Fable Plan — Chainlink Decomposition & TL Hand-off

Execution breakdown of [fable-plan.md](fable-plan.md): "Video → Walkable Scene in Godot 4".
Defines Chainlink **milestone #3** with a root→TL fork-wave structure. Root completes the
Phase-0 environment first (DONE — see status); the TL then forks the parallel waves.

> Source of truth for live state is the Chainlink DB
> (`CHAINLINK_DB=/home/user/backrooms-workspace/.chainlink/issues.db`). This doc is the
> human-readable map. Full per-issue scaffolding lives as `--kind plan` comments on each issue.

## Architecture (why this shape)

Every Bevy failure traced to deriving the collider from the splat and never finishing the
alignment ritual. fable-plan.md inverts it: **v1 is mesh-first** — one photogrammetry textured
`scene.glb` is *both* visual and collider, so it cannot be misaligned with itself. The Gaussian
splat is demoted to an optional v2 overlay. Walkability never blocks on splats again.

Locked decisions:
- **Stage-M mesh tool:** COLMAP dense + Poisson primary, **Meshroom fallback** (AppImage, not
  in nixpkgs) if floors hole — `mesh_photogrammetry.sh --fallback meshroom`.
- **v2 splat track:** scaffolded now, **blocked on v1 (G3)**.
- **Godot workflow:** **headless / text-first with a GUI escape hatch**. Agents author
  `.tscn` + `.glb.import` text and run `godot4 --headless --import`. Where a step truly cannot
  be automated, the issue posts a `--kind human` GUI recipe and escalates to the operator.

## Issue graph (milestone #3)

| ID | Issue | Blocked by | Owner / wave |
|----|-------|-----------|--------------|
| **#38** | E1: nix flake — Godot 4.6 + Forward+ headless | — | **root — DONE ✓** |
| **#39** | E2: MVS build env — COLMAP dense + Meshroom fallback | — | **root — DONE ✓** |
| **#40** | E3: scaffold `godot_walk/` Forward+ project | — | **root — DONE ✓** |
| #41 | G1: player controller on a flat plane (+#48/#49/#50) | E1,E3 | TL — Wave 1 engine |
| #42 | G2: import known-good glb → trimesh body → walk | E1,E3 | TL — Wave 1 engine |
| #43 | M1: Stage M — corridor_straight → scene.glb (+#51–#54) | E2 | TL — Wave 1 asset |
| #44 | G3: walk the real corridor (**v1 DONE**) | G1,G2,M1 | TL — Wave 2 |
| #45 | S0: vendor GDGS addon | E1,E3 | TL — Wave 3 (v2) |
| #46 | S1: Brush splat `scene.ply` | E2,G3 | TL — Wave 3 (v2) |
| #47 | G4: layer splat over invisible mesh | S0,S1,G3 | TL — Wave 3 (v2) |

Subissues: G1→ #48 player.tscn, #49 player.gd, #50 mouse-look. M1→ #51 poses+COLMAP dense,
#52 Meshroom fallback, #53 Blender cleanup, #54 glTF export + scene_transform.txt.

**Wave rule:** G1/G2 (engine) ∥ M1 (asset). G3 needs all three. v2 (S0/S1/G4) never forks
until G3 is merged. `chainlink issue ready` surfaces only unblocked work per wave.

## Human GUI checkpoints (headless escape hatch)

Default is headless/text; these steps may need a human eyeball. The leaf attempts headless
first, then posts the pre-written `--kind human` recipe + `notify_parent` with `[NEEDS HUMAN
GUI]` so the TL routes to the operator (not a dev failure).

| Issue | GUI fallback |
|-------|--------------|
| G1c (#50) | run `sandbox.tscn`, confirm WASD + mouse-look feel right |
| G2 (#42)  | open `import_test.tscn`, Mesh → Create Trimesh Static Body if import flag didn't |
| M1c (#53) | open `scene.glb` in Blender, fill floor holes, measure doorway ≈ 2.0 m, re-export |
| G3 (#44)  | walk the full corridor; confirm no fall-through, door-sized doorway |
| G4 (#47)  | toggle mesh visibility mid-walk; confirm splat & collider coincide within cm |

## Phase 0 — completed by root (2026-06-10)

- **#38** `flake.nix`: added `godot_4` (reuses existing Vulkan/xkb/GL `runtimeLibs`) + shell
  probe. nixpkgs `godot_4` = 4.6.3-stable (binary cache). Verified `godot4 --headless
  --version` → 4.6.3; flake still evaluates.
- **#39** COLMAP (flake) confirmed to provide CUDA MVS (`image_undistorter`,
  `patch_match_stereo`, `stereo_fusion`, `poisson_mesher`, `delaunay_mesher`). Meshroom not in
  nixpkgs → [environment/meshroom.md](environment/meshroom.md) (AppImage + `MESHROOM_BIN`).
  Added [scripts/splat_pipeline/mesh_photogrammetry.sh](scripts/splat_pipeline/mesh_photogrammetry.sh)
  CONTRACT/STUB — live dep+input checks, stage bodies exit 7 STUB for M1.
- **#40** [godot_walk/](godot_walk/) skeleton: `project.godot` (forward_plus + input actions),
  `.gitignore`. Verified `godot4 --headless --path godot_walk --import` exits 0.

## TL hand-off

Phase 0 is closed; `chainlink issue ready` now surfaces **#41, #42, #43, #45**. The TL:
1. `fork_wave` Wave 1: G1 (#41) + G2 (#42) [engine] ∥ M1 (#43) [asset].
2. After all three merge → G3 (#44) = v1 gate (human walk-test acceptance per fable-plan §5).
3. After G3 merges → v2 wave: S0 (#45), S1 (#46), G4 (#47).

Every spawned leaf gets `CHAINLINK_DB=/home/user/backrooms-workspace/.chainlink/issues.db` in
its spec and a `chainlink_timer_start <id>` on assignment.

## Verification (end-to-end)

1. **Phase 0 (done):** `nix develop` shows `[x] godot` + `[x] colmap`; empty `godot_walk`
   imports headless (exit 0).
2. **Wave 1 engine:** headless import of sandbox/import_test exits 0; human run confirms
   WASD+mouse and no fall-through on a known-good glb.
3. **Wave 1 asset:** `scene.glb` opens clean in Blender, floor continuous, doorway ≈ 2.0 m,
   ≤500k tris, textures embedded; `scene_transform.txt` written.
4. **Wave 2 (v1 gate):** walk the real corridor — no fall-through/floating/tunneling, ≥60 fps.
5. **Wave 3 (v2):** mesh-visibility toggle shows splat & collider coincide within cm; ≥30 fps.
   If GDGS immature → v1 ships alone.
