# Issue #255 — snow-garden-courtyard-v2 (detail revision of #174 v1)

Source: `video-d92fc1fa764aa3a2` ("Angel (Joseph Cornell, 1957).mp4"; 636×480,
29.97003 fps, 6,782 frames, 226.348 s).

This task revises the accepted stage-6 v1 candidate with **more detail**, as a NEW
version `snow-garden-courtyard-v2` under
`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/`.
The v1 folder is byte-for-byte untouched.

Before authoring I viewed all of the required references:

- the issue and its operator comment (2026-11-17: "snow garden is lacking but fine
  as a first pass; wants more detail"; resolution/contract ideas are tracked in #256,
  **not** this issue — no new Hunyuan attempt here);
- `godot_walk/evidence/2026-11-17-issue-174-room-candidate/REPORT.md`;
- the v1 folder (`room.gd`, `adaptation_candidate.json`, `crop_plan.json`,
  `test_room.gd`, `capture_room.gd`, `run_capture_guarded.py`, all four captures);
- the accepted panorama
  `…/hunyuan/attempt-001-retry-001/panorama/panorama.png` (512×256, sha256
  `f9c95477644ed77038775ec23a99c3573db78c0d06e991ace76796b5a57b283b`);
- the selected direct-source seed frame `…/frames/issue174-5s-c/frame_4347.png`
  (636×480, sha256 `ae59a84fb9aa07612b5b100c2ee5b5ab5645836dd5bccc665b862acd51ab500f`,
  PTS 145.011533 s — confirmed by `source_ingestion_runner.py status`,
  `selected_seed.frame_id = frame_4347`).

## 1. Concretely what the panorama/seed show that v1 lacked

Viewing the panorama, the seed and every v1 capture, these were missing or weak in v1:

1. **Tree variety and density** — the panorama has many leafless trees of varied
   height and thickness plus a brownish/leafy cluster; v1 had eight identical box
   trunks with two flat dark billboard panels each (the largest mismatch per the
   v1 report).
2. **Ground undulation / snow drifts** — the panorama snow field is not a perfectly
   flat plane; v1 had one flat box.
3. **Boundary / hedge detail** — v1's four plain dark-green walls had no caps,
   posts or base; the panorama shows a tree line rather than a wall.
4. **Sky and horizon** — v1 reused the panorama sky but with flat ambient/key
   light and no horizon treatment.
5. **Bench and low-wall detail** — the panorama bench is a low articulated stone
   bench with small markers nearby; v1's bench was three boxes with a blurry
   statue crop and no bollards or legs.
6. **Lighting and dusk colour** — panorama/seed are blue dusk; v1 used unshaded
   flat materials with one cool light.
7. **Foreground clutter** — the panorama field has many small dark posts/stumps;
   v1 had none.

## 2. What was built in v2

A new standalone playable Godot room under
`…/rooms/snow-garden-courtyard-v2/`: the **same closed 20×16 design-unit rectangle
in XZ, +Y up, uncalibrated** as v1, with the same snow floor at Y=0, same spawn
`[0, 0.6, 6]`, and the accepted panorama as a camera-centred `PanoramaSkyMaterial`
visible above the walls. All four edges are closed and collidable; `sockets` is
`[]`. No doors, entities, animated/moving props, particle snowfall or hidden rooms.
The panorama is **visual only** — no panorama pixel is used as a surface.

Added static detail, all from what the panorama/seed show:

- **18 static leafless trees** (up from 8) in three rows with varied heights
  (5.2–7.6) and trunk radii, each a low-poly cylinder trunk plus four angled
  branch cylinders; canopy variety via direct crop panels (`branch_canopy`,
  `branch_fine`) and `evergreen_foliage` crop clusters.
- **10 snow drifts** — flattened low-poly spheres in two snow shades, decorative
  (no collider), placed away from the spawn lane.
- **12 marker posts / stumps** — short low-poly cylinders, decorative.
- **Richer boundary** — snow-dusted wall caps, vertical posts with caps on all
  four walls, and darker inner hedge-base strips; the collidable footprint is
  unchanged.
- **Detailed stone bench** — plinth, four legs, seat, three back posts, three
  back slats and four bollards.
- **Static stone angel statue** — plinth, figure slab, angled wing and head,
  placed off the spawn-to-bench lane, made from the seed-frame angel crop; a
  non-animated prop, not an entity.
- **Lighting / sky** — a warm low "WinterSunlight" key light, a cool
  "WinterSkyFill", tuned blue ambient and `background_energy_multiplier`, with the
  unchanged PSX compositor/preset.

New files only under the v2 folder: `adaptation_candidate.json`, `crop_plan.json`,
`room.gd`, `room.tscn`, `test_room.gd`, `capture_room.gd`,
`run_capture_guarded.py`, `standalone_test_receipt.json`,
`capture_resource_run.json`, `textures/{stone_figure,stone_robe,branch_canopy,
branch_fine,evergreen_foliage}.png`, `textures/crop_manifest.json`, and six
`captures/*.png` plus `captures/capture_manifest.json`. No shared material or
hash-pinned file was edited.

### Contract freeze and provenance

Contract freeze: `godot_walk/room_catalog/contract_freeze_v3.json` sha256
`91c0cb1b47f980193a47d8e221b366f2d452256fa7b383adc818a177c9813ba1` — the same
v3 freeze v1 used. Catalog snapshot: `godot_psx_room_kit-0.2.0.json`
(`8feb31a…80d`). PSX profile `library-psx-ursc-1.5-native-compositor` reused
unchanged.

Five surface textures are **direct rectangular crops of the 636×480 seed frame**,
extracted with `video_adaptation_runner.py extract-source-crops` (no resize, no
colour edit): `stone_figure [190,200,430,480]`, `stone_robe [200,280,380,470]`,
`branch_canopy [60,20,380,200]`, `branch_fine [380,0,636,150]`,
`evergreen_foliage [0,0,130,200]`. Snow, drifts, hedges, caps, trunks, branches
and marker posts use local solid-color PSX `StandardMaterial3D` values authored
in `room.gd` because the seed frame shows no such surfaces. No panorama pixel was
used for any surface.

## 3. v1 versus v2 comparison table

| Feature | v1 | v2 | Added detail | Still differs from panorama / seed | Invented / authored |
|---|---|---|---|---|---|
| Trees | 8 identical boxes + 2 flat billboards each | 18 low-poly trees, 3 rows, varied height/radius, 4 angled branches each, canopy variants | Count, variety, branching geometry, fine-branch and foliage crops | Panorama trees are photoreal, continuous, with real bark/leaf silhouettes; v2 trunks are solid dark cylinders and crop panels still read as flat patches from some angles | Tree count, positions, heights, radii, variants are authored, not measured |
| Ground | One flat pale snow box | Same walkable floor + 10 decorative flattened snow mounds in two shades | Snow drifts / undulation, visual only | Panorama snow has real drift shading and long tree shadows; v2 drifts are simple flat ellipsoids with no dynamic shadow | Drift count, positions and sizes are authored |
| Boundary | 4 plain dark wall boxes | 4 walls + snow caps, vertical posts with caps, darker inner base strip | Low-wall / hedge detail, snow dusting | The panorama has no wall at all — it is an open park; v2's wall ring is a traversal bound, not an observed structure | The entire wall idea and its cap/post spacing are authored bounds |
| Bench | 3 boxes, blurry statue crop | Plinth, 4 legs, seat, 3 back posts, 3 back slats, 4 bollards, direct `stone_robe` crop | Articulated legs/back/bollards | Panorama bench position/shape is only glimpsed; the crop is the seed angel's robe, not bench pixels | Bench articulation and placement are authored |
| Stone statue | none | Static plinth + figure/wing/head using `stone_figure` crop | Static angel prop from the seed frame | The seed shows the angel in close-up only; the panorama does not show a statue in the field | Statue placement and simplified proxy geometry are authored; it is a non-animated prop |
| Marker posts | none | 12 low cylinder stumps, decorative | Foreground clutter matching panorama markers | Panorama markers are irregular; v2 uses a loose authored cylinder pattern | Post count, positions, heights are authored |
| Sky / horizon | panorama sky, flat key + ambient | panorama sky, warm key + cool fill, tuned ambient and background energy | Dusk key/fill, horizon treatment via panorama | Sky is still a static 512×256 equirectangular image with no parallax; no real horizon geometry | Light colours/energies are authored interpretation; PSX shaders are unshaded/fog-disabled so light energy does not shade authored geometry |
| Provenance flags | candidate_pending_review, both flags false | unchanged | — | — | `registration_accepted=false`, `scale_calibrated=false`, no sockets |

Observed versus authored versus unknown is recorded explicitly in
`v2/adaptation_candidate.json` under `source_observations.observations`,
`.unknowns`, `reusable_requirements`, `surfaces` and `authoring_log`.

## 4. Mechanical checks (exact output lines)

`python3 godot_walk/scripts/source_ingestion_runner.py status video-d92fc1fa764aa3a2`:
`selected_seed.frame_id = frame_4347`, PTS 145.011533 s; no Hunyuan was run.

Crop extraction `python3 godot_walk/scripts/video_adaptation_runner.py extract-source-crops …`:
```
godot_walk/source_library/sources/video-d92fc1fa764aa3a2/rooms/snow-garden-courtyard-v2/textures/crop_manifest.json
```

Bundle validation `python3 godot_walk/scripts/video_adaptation_runner.py validate --bundle …/adaptation_candidate.json`:
```
  "status": "valid",
  "adaptation_id": "snow-garden-courtyard-v2",
  "candidate_fingerprint": "3ab070183f63c27b538af23a99196106338ec818252b8d3f6766a247af676cb9",
  "candidate_identity": "3ab070183f63c27b538af23a99196106338ec818252b8d3f6766a247af676cb9",
  "static_consistency": "passed",
  "runtime_evidence": { "status": "historical fingerprinted records verified; runtime not rerun" },
  "validation_is_read_only": true
```
50 hash-bound dependencies; record sha256
`fef59f775dbc72eb18ffb95bca21d58c02eea9db105a5d1d928ca68b6d4bcdb0`,
candidate_identity bound through `candidate_identity`.

Godot headless room test
`godot4 --headless --path godot_walk --script res://…/v2/test_room.gd`:
```
Snow garden courtyard v2 reset to safe spawn
SNOW_GARDEN_V2_TESTS_PASSED
```
Checks: snow-floor support, floor ray, north boundary ray, tree-obstacle ray,
stone-statue obstacle ray, walk-and-backtrack, no boundary escape, ≥20 authored
obstacles, ≥120 authored visual nodes, missing-floor negative control,
open-boundary negative control, and R reset to `[0, 0.6, 6]`.

Full script suite `python3 -m pytest -q godot_walk/scripts`:
```
1530 passed, 5 skipped, 67 subtests passed in 268.28s (0:04:28)
```

Source registry `python3 godot_walk/scripts/register_video_sources.py validate`:
```
{ "valid": true, "registered_count": 13 }
```

Ruff on the new guard wrapper `python3 -m ruff check …/run_capture_guarded.py`:
```
All checks passed!
```

## 5. Captures

Rendered with the guarded script
`python3 …/v2/run_capture_guarded.py --output-dir …/v2/captures --report …/v2/capture_resource_run.json -- godot4 --path godot_walk --script …/v2/capture_room.gd -- --out=res://…/v2/captures`.
Receipt: `return_code=0`, `timed_out=false`, `error=null`, `elapsed_seconds=10.712`,
`compute_apps=[]`; preflight and peak-resource samples are in
`capture_resource_run.json`. Frame profile in `captures/capture_manifest.json`:
mean 16.67 ms, p95 17.66 ms, p99 20.91 ms over 300 samples (includes display sync,
not a measured gameplay FPS); 6 views (the four v1 viewpoints plus two new ones).

All six 1152×648 PNGs were viewed:

- `captures/spawn_toward_bench.png` (same v1 viewpoint)
- `captures/tree_line.png` (same v1 viewpoint)
- `captures/stone_bench.png` (same v1 viewpoint)
- `captures/open_winter_sky.png` (same v1 viewpoint)
- `captures/snow_drift_and_posts.png` (new)
- `captures/statue_detail.png` (new)

Note: the first capture pass produced an occluded `spawn_toward_bench.png`; I
added a second `look_at` after a short frame settle in `capture_room.gd` and
re-ran the guarded capture cleanly, after which all six views were correct. The
v1 viewpoints/positions/targets are unchanged.

## 6. Honest comparison and limitations

**Matches / improved.** Tree density and height variety, branch structure, the
articulated bench, caps/posts on the boundary, snow mounds, marker posts and the
static angel prop all read clearly in the six views. The panorama sky still
dominates the upper frame with blue dusk tone, matching the source.

**Still different from the panorama.** The panorama is a photoreal, unbounded
park; this is a deliberately bounded low-walled PSX courtyard stand-in. Tree
trunks are solid-color cylinders, canopy crops remain visibly flat from some
angles, snow drifts are simple ellipsoids with no real shadows, and the sky is a
static image with no parallax. The dusk lighting is baked into albedo colours
because the project PSX shaders are unshaded and fog-disabled — dynamic light
settings do not shade authored geometry. The bench crop is the seed angel's robe,
not a faithful stone-bench texture.

**Invented / approximated.** All counts, positions, heights, colours, the wall
ring and its details, the marker/stump layout, the drift layout, the bench
articulation and the statue's placement are authored, not measured. No video
metric scale is claimed. The tree line and sky are scenery; no connectivity is
established.

A passing validator, clean test suite and clean captures are **not approval**.
This candidate remains `candidate_pending_review` for operator review; it has not
been accepted or admitted to any catalog.

## 7. Ledger and scope compliance

No existing `source_ingestion_runner.py` stage records room-candidate authoring,
so none was used and no event or receipt was written by hand:
`godot_walk/source_library/sources/video-d92fc1fa764aa3a2/events.jsonl` is
unchanged (last event `hunyuan_operator_feedback`). No Hunyuan or new panorama
attempt, no operator feedback recording, no seed change, no winner/decision, no
catalog admission, no `catalog.json`/snapshot edit, no `register_source_room.py`,
no module metadata and no hash-pinned file (`scripts/player.gd`, `project.godot`,
library room scenes, `catalog.json`, `MATERIAL_LANGUAGE.md`, `PALETTES.md`) was
touched. Both calibration flags remain false. Only new files under the source's
`rooms/snow-garden-courtyard-v2/` folder and this evidence report were created.
