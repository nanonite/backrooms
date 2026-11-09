# Generative Map Template Proposal — Complete Metadata for the Generation Scope

Status: proposal for operator review (2026-11-09). Issue #212, child of #169. This file is the only deliverable of #212: no code, schema, map, room, catalog, palette or frozen-file change is proposed here. Field names are proposals for the operator to accept, rename or reject before any implementation issue is filed.

The question is narrow: if the next batch of videos (#195) and the per-source ingest issues (#174–#180) are processed against the current metadata, will every generated layer be able to use them without re-ingesting or patching the modules later? The answer today is **no**. The map layers grew one at a time and the module records still describe the 2026-11-02 design. This proposal puts the whole template side by side, names the gaps, and recommends a versioned way to close them without editing a single frozen library file.

The earlier design is `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` (2026-11-02); this proposal does not replace it, it completes the template that design left open. Evidence is taken from the committed code and records listed in Appendix A. Where a fact is measured, it is marked measured. Where it is authored, inferred or still a guess, it is marked as such. In particular, picture-only ingestion was checked in the code rather than assumed: it does not exist today (section 3.9).

---

## 1. Audit: what the generation scope carries today

### 1.1 Record chain

```
source_manifest (v1/v2)              video hash, ffprobe metadata, review state, frame/room references
        │
        ▼
catalog snapshot + library index      admitted modules, footprints, sockets, tested pairs
        │
        ▼
module_poetics (schema v1)            shape, ports, sign features, voids, layers, poetics, eligibility
        │
        ├── module_acoustics.json     categorical floor acoustic tag derived from style_tags
        ▼
generative_map (schema v1, gmap-0.12.0)
        │  cells: envelope, ceiling, ports, role, tier, module, palette, wear,
        │         surface_variants, light, floor_y, reverb, landmark, diagonal_passage
        │  edges: connector, connection_status, vertical/ramp/drop, diagonal link
        ▼
shape_room specs + generative_map_assembly.gd
        │  generated rooms, library module instances, lights, materials, risers, player
        ▼
runtime: walk_player.gd + room_reverb_bus.gd
```

The records are not one template. They are five independently versioned records, and only some of them know about the newer layers.

### 1.2 Layer audit

One row per layer. “Baked” means the value is committed into a map, shape-room spec or accepted module record and is not changed by the running game. “Runtime” means a running node or overlay can change it without rewriting the committed record.

| Layer | Owner | Origin | Stream and version | Baked or runtime | Consumers |
|---|---|---|---|---|---|
| Lattice, cells, ports, roles, rarity, distribution | map | generated from seed/attempt/layout variant | layout `gmap-layout-0.6.1`; degenerate `degenerate:{version}`; shape-stage `shape_stage:{version}`; generator `gmap-0.1.0`–`gmap-0.12.0` | baked | `gmap_build.py`, `gmap_validate.py`, `shape_room_spec.py`, `generative_map_assembly.gd` |
| Library module placement and socket joint | map placement; module shape | module is video-derived or authored kit; placement is generated | module placement since `gmap-0.3.0`; poetics `module-poetics-0.1.0` | baked | `gmap_modules.py`, `gmap_library.py`, `gmap_module_rules.py`, `generative_map_assembly.gd::_place_module` |
| Generated shape room | map | generated | `shape-room-0.10.0` for `gmap-0.10.0`–`gmap-0.12.0`; per-cell `cell_rng` key | baked into shape-room specs | `shape_room_spec.py`, `shape_room_builder.gd`, `generative_map_assembly.gd` |
| Diagonal links and reserved sites | map | generated | `diagonal-links:gmap-0.6.0`; `diagonal-sites:gmap-0.6.1` | baked | `gmap_diagonal*.py`, `shape_room_diagonal*.gd`, `gmap_validate.py` |
| Landmark room | map | generated | `landmark:gmap-0.7.0` | baked | `gmap_landmark*.py`, `shape_room_landmark.py`, `gmap_validate.py` |
| Material palette anchor | map | generated from nearby library figure room style tags | `palette:gmap-0.7.0` (the anchor stream used by `gmap-0.8.0`–`gmap-0.12.0`); registry `0.1.0`/`0.2.0`/`0.3.0` | baked | `gmap_palette.py`, `shape_room_palette.py`, `shape_room_materials.gd`, `generative_map_assembly.gd` |
| Regional floor palette | map | generated | `floor_regions:gmap-0.12.0`, per-cell keyed draw | baked | `gmap_floor_regions.py`, `gmap_palette.py`, `shape_room_palette.py` |
| Wear and surface variants | map | generated | `surface:gmap-0.9.0`, sequential RNG | baked | `gmap_surface.py`, `shape_room_spec.py`, `shape_room_materials.gd`, `shape_room_builder.gd`, `gmap_validate.py` |
| Light tier, colour temperature, lamps, dark wing | map | generated | `light:gmap-0.8.0`, sequential RNG | baked into map and shape-room specs | `gmap_light.py`, `shape_room_spec.py::_attach_light`, `shape_room_builder.gd`, `shape_room_lighting.gd`, `gmap_validate.py` |
| Elevation, ramps, drops, loops | map | generated | `elevation:gmap-0.10.0`, sequential RNG | baked | `gmap_elevation.py`, `shape_room_spec.py`, `generative_map_assembly.gd::_add_risers`, `gmap_validate.py` |
| Reverb wet/dry flag | map | generated | `reverb:gmap-0.11.0:<cell_id>`, per-cell keyed draw | baked base; runtime-mutable | `gmap_reverb.py`, `generative_map_assembly.gd::_tag_reverb` / `set_room_reverb` / `room_reverb_at`, `walk_player.gd`, `room_reverb_bus.gd` |
| Module floor acoustic tag | module sidecar | derived from accepted poetics `style_tags` | `module-acoustics-0.1.0` | baked sidecar; applied at assembly | `module_acoustics.py`, `generative_map_assembly.gd::_tag_module_floor`, `walk_player.gd` footstep surface tag |
| Runtime room acoustics | runtime | measured by ray probe | `room_acoustic_probe.gd` metrics; no stored version | runtime only | `room_acoustic_probe.gd`, `walk_player.gd`, `room_reverb_bus.gd` |
| Ceiling and nominal volume | map + module | ceiling authored in module/cell; volume is a heuristic | map `ceiling_range_m`; module `shape.ceiling_height_m`; `gmap-0.10.0` can raise ceilings | baked | `gmap_build.py::cell_json`, `shape_room_spec.py`, `generative_map_assembly.gd::nominal_room_volume_m3`, `room_acoustic_probe.gd` fallback |
| Poetics and provenance | module | derived mechanical fields + operator-confirmed poetics | `module-poetics-0.1.0`, schema v1 | frozen accepted record | `module_poetics.py`, `gmap_library.py`, `gmap_palette.py` (style tags), `gmap_light.py` (form role), `module_acoustics.py`, `gmap_validate.py` |
| Door / junction state | map edge | generated joint, currently only `proposed_untested` | map `connection_status`; no door stream | baked | `generative_map_assembly.gd::_module_joints` / `_forced_closed`, `gmap_validate.py` |
| Wall-material absorption | — | absent | — | — | reserved for research issue #213 |
| Source lighting and scale calibration | — | absent | — | — | parked in #187 |

Two facts in this table matter for the rest of the proposal:

1. **Only two of the map post-pass layers are per-cell keyed today.** Reverb (`gmap_reverb.py`) and regional floor palettes (`gmap_floor_regions.py`) use `sha256(seed:attempt:stream:cell_id)`, so one cell can be re-drawn without shifting another. Shape-room geometry is also per-cell keyed (`shape_room_rng.cell_rng`), but the map post-passes for light, surface/wear, elevation and the palette anchor use sequential `random.Random` streams. Re-drawing one of those cells would shift every later draw. A “re-draw one room” feature therefore needs either a new keyed stream version or a runtime overlay; it cannot be done safely against the current maps.
2. **Module cells are deliberately excluded from several map layers.** `gmap_light._eligible_cells`, `gmap_surface.assign_surface`, `gmap_palette` and the schema description for `cell.palette` all skip module cells. A module keeps its own scene, materials, light and ceiling. Only `reverb` is assigned to every walkable cell, including modules (`gmap_reverb.assign_reverb`). This is why a module cannot currently describe its own floor material in the map’s palette vocabulary.

### 1.3 Current records and versions

| Record | Version today | What it actually contains | Frozen? |
|---|---|---|---|
| `godot_walk/source_library/source_manifest.schema.json` / `source_manifest_v2.schema.json` | schema v1 / v2 | canonical video path/hash, ffprobe metadata, review state, frame references, Hunyuan attempts, room adaptations | append-only; versioned manifests supersede |
| `godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json` | index `library-index-0.1.0`, catalog `0.5.0` | 11 modules, 2 tested connector pairs, sockets, snapshot hash | catalog snapshot pinned |
| `godot_walk/room_catalog/module_poetics.schema.json` | schema v1 | shape, ports, sign features, voids, layers, poetics, eligibility | accepted records immutable |
| `godot_walk/room_catalog/module_acoustics.json` | `module-acoustics-0.1.0` | module@version → categorical acoustic tag, evidence tags, poetics path/hash | generated sidecar; regenerating is a new version |
| `godot_walk/room_catalog/generative_map.schema.json` | schema v1 | map cells/edges for `gmap-0.1.0`–`gmap-0.12.0` | old maps stay valid |
| `godot_walk/room_catalog/material_palettes/palettes-0.3.0.json` | registry `0.3.0`, schema v3 | 6 palettes: yellow, concrete, debris, tile, metal, wood; four surfaces, three variants, acoustic tags | registry versioned; old maps keep old registries |
| `godot_walk/scripts/shape_room_spec.py` output | `shape-room-0.10.0` for current maps | geometry, ceiling, doorways, lamps, materials, light, floor_y | shape-room specs are committed evidence |

There are 12 registered sources and 11 modules in the current index. Five `gmap-0.12.0` maps are committed. The current #208 report measures 768 generated cells across seeds 1–60.

---

## 2. Measured versus guessed

This distinction is the point of the proposal. The template must not present an authored guess as a measurement.

| Claim | Status | Evidence |
|---|---|---|
| Video dimensions, frame rate, frame count, duration | **measured** | `video_source_library.probe_video` runs `ffprobe`; values are stored in `canonical_video.metadata` |
| Source and frame hashes | **measured** | `sha256_file`, extraction manifests, event payloads |
| Map layout, palette assignment, wear, light, elevation, reverb are deterministic for a seed | **measured** | committed maps/fills and `gmap_validate.py`; `test_generative_map.py` etc. |
| Regional floor palette mix | **measured** | #208 report: 768 generated cells; carpet share min 55.7% whole-map, 78.4% non-anchor; `godot_walk/evidence/2026-11-09-issue-208/palette_mix.json` |
| Runtime room probe metrics on four shape rooms | **measured** | #205 report table: `c00`, `c02`, `c04`, `c09` on `gmap-279-gmap-0.11.0`; `mean_distance_m`, `ceiling_height_m`, `openness`, mapped `room_size`/`damping`/`wet`/pre-delay |
| Module floor acoustic tag | **derived, not measured** | `module_acoustics.derive_acoustic` maps style tags through a fixed precedence; no probe is run on the module |
| Module geometry, footprint, ceiling | **derived from authored scene/index data** | `module_poetics.build_shape` reads `placement_footprint_xz` and `floor/ceiling_elevation_m`; dimensions are authored assumptions, not video measurements |
| Nominal room volume | **heuristic, not measured** | `gmap_reverb.room_volume_m3` and `generative_map_assembly.nominal_room_volume_m3` use envelope area × authored maximum ceiling |
| Source lighting (colour temperature, illuminance, fixture layout) | **absent / guessed** | `module_poetics.build_layers` writes `layers.light = {value: null, note: "not derived"}`; map light is generated independently (`gmap_light.py`) |
| Real-world scale | **uncalibrated** | `scale_calibrated` is `false` in every manifest and map; no camera intrinsics or known-dimension anchor is stored |
| Poetics (`apollonian`, `dionysian`, role, rarity, salience, unique details) | **operator judgement** | accepted `module_poetics_v2.json` / `*.accepted.json`; `poetics_status` records operator confirmation |
| Tension / mood | **absent** | `module_poetics.schema.json` has no such field; `poetics` stops at the Karth axes and surface salience |
| Picture-only ingestion | **not supported** | `video_source_library.VIDEO_SUFFIXES` is `{.mp4,.mov,.mkv,.webm}`; `canonical_video_path` rejects other suffixes; `probe_video` requires an ffprobe video stream; `extract_source_frames` decodes video with ffmpeg |
| Wall-material absorption | **not implemented** | #205 report: “Wall-material absorption from ray hits is not implemented”; #213 is the research issue |

The four #205 probe rooms are generated shape rooms. The report does not include a library module cell, so there is currently no measured acoustic descriptor for any of the 11 modules.

---

## 3. Gaps

### 3.1 Per-module measured acoustics

Current state: `module_acoustics.json` is a projection of accepted poetics. Each module gets one of `carpet`, `concrete`, `debris`, `plaster`, `metal`, `wood` (or `default`) from `style_tags` through the precedence list in `module_acoustics.py`. The #205 probe measures `mean_distance_m`, `max_distance_m`, `ceiling_height_m`, `openness`, then maps them to `room_size`, `damping`, `wet` and `predelay_msec` (`room_acoustic_probe.gd::map_metrics`). Those measured values are used live but are never stored per module.

Gap: a module descriptor cannot say “this room measured 6.55 m mean wall, 4.6 m ceiling, openness 0.0, wet 0.58”. It can only say “carpet”. Two carpet modules of very different size therefore look identical to the acoustic layer until the player is inside them.

Proposed field: `module_profile.acoustics` with `tag`, `probe` (the five measured metrics plus the four mapped values), `probe_version`, `sample_points`, `evidence`, and later `absorption` from #213. The tag remains the fast fallback; the probe block is the measured descriptor.

### 3.2 Floor material per module versus generated floor palettes

Current state: generated cells get a `palette` record and, from `gmap-0.9.0`, `wear` + `surface_variants`. `shape_room_palette.palette_materials` resolves the palette to wall/floor/ceiling/trim textures and acoustic tags. Module cells carry **no** `palette` (`generative_map.schema.json` cell description: “Module and void cells carry none”). Their floor is whatever the library scene contains; `module_acoustics.json` only assigns a categorical tag to the floor bodies found by `generative_map_assembly._tag_module_floor`.

Gap: #208 added tile, metal and wood floor palettes, but a module cannot declare “my floor is tile / metal / wood / carpet” in the same vocabulary. The anchor rule in `gmap_palette.py` reads a figure module’s `style_tags` to choose a palette for neighbouring generated cells, but the module’s own floor material is not represented as a palette id or a per-surface material record. A future module with a metal grating floor and a carpeted room next door can therefore produce an acoustic tag that is correct but a palette anchor that is only approximate.

Proposed field: `module_profile.surfaces.{wall,floor,ceiling,trim}` with `material_id`, `palette_id` (nullable), `acoustic`, `texture_refs`, `provenance`, `sign`. The palette registry already has the vocabulary (`palettes-0.3.0.json`: `backrooms_yellow`, `industrial_concrete`, `plaster_debris`, `tiled_institutional`, `metal_service`, `wood_parquet`); the template needs to let a module point at it without editing the module scene.

### 3.3 Source lighting and scale calibration (#187)

Current state: `module_poetics.build_layers` hard-codes `layers.light = {value: null, note: "not derived"}`. The map’s light layer is generated from the map seed (`light:gmap-0.8.0`), not from the source video. `source_manifest` stores only `width`, `height`, `fps`, `frame_count`, `duration_seconds`; it stores no camera intrinsics, capture height, known dimension, colour temperature or illuminance. `scale_calibrated` is `false` everywhere.

Gap: the template cannot distinguish a dim concrete hall from a bright tiled corridor at the source level, and it cannot state that a room is 4.2 m wide because a door is 2.0 m. #187 is the parked issue for this; the template should reserve the fields now so new videos can carry the data when #187 lands.

Proposed fields: `source_manifest.scale` (`status`, `method`, `anchor`, `confidence`, `evidence`) and `source_manifest.lighting` (`status`, `color_temp_k`, `illuminance_lux`, `fixtures`, `confidence`, `evidence`); `module_profile.scale` and `module_profile.lighting` for the per-room projection. Until #187 provides a method, both default to `unknown` / `uncalibrated`, never a fabricated number.

### 3.4 Ceiling and volume

Current state: map cells have `ceiling_range_m`; module cells get the module’s `shape.ceiling_height_m` copied into both ends of the range by `gmap_build.cell_json`. `gmap_elevation` can raise a lower cell’s ceiling for clearance. `gmap_reverb` and the assembly compute a **nominal** volume as envelope area × maximum authored ceiling. The runtime probe measures ceiling height with an up ray, capped by the authored ceiling because generated ceilings have no collider (`room_acoustic_probe.gd`; #205 report).

Gap: no stored `volume_m3`, no `ceiling_kind` (flat, beam grid, open-to-above, coffered, skylight), no measured ceiling from a module probe, and no distinction between the authored range and the built room height. Reverb currently biases on the heuristic; the template should carry both the nominal and measured values so a later layer can choose.

Proposed fields: `module_profile.shape.ceiling_min_m`, `ceiling_max_m`, `ceiling_height_m`, `ceiling_kind`, `volume_nominal_m3`, `volume_measured_m3`, `volume_source`; map cell `volume` with the same nominal/measured distinction.

### 3.5 Exits and role tags

Current state: a module has `ports.tested_sockets` and `ports.untested_sockets`, plus `poetics.form_role` (`ground`/`figure`). `gmap_modules.usable_modules` requires `form_role` in `("figure","ground")` and `tested_socket()` returns the **first** tested socket; the module enters as a leaf attached to one parent. The map cell has `role` (`ground`, `figure`, `threshold`, `void`) and `rarity_tier`.

Gap: there is no semantic exit description (entrance, exit, connector, service, dead end), no through-room / multi-exit placement, no `circulation_role` (through, terminal, branch, hub), and no sightline or threshold tag. A module with two tested sockets cannot be used as a through-room because the placer only spends one socket.

Proposed fields: `module_profile.exits[]` (`socket_id`, `kind`, `compatibility_type`, `width_m`, `elevation_m`, `circulation_role`, `tested_pair_ids`, `provenance`) and `module_profile.roles` (`map_role`, `form_role`, `semantic_tags`, `circulation_role`, `sightline_tags`). The exact placement policy for multi-exit modules is a separate implementation issue; the template only has to carry the facts.

### 3.6 Tension or mood descriptors

Current state: `poetics` carries `apollonian`, `dionysian`, `form_role`, `rarity_tier`, `style_tags`, `surface_salience` and `unique_details`. These are Karth’s complexity/form axes and Manovich-style salience, not a tension or mood description.

Gap: the maze feel cannot be queried. There is no way to ask for “a low-tension carpet run”, “a high-dread concrete wing” or “a safe room after a drop”. The map has `dark_wing` and light tier, but those are lighting mechanics, not a mood descriptor.

Proposed field: `module_profile.mood` and map cell `mood`, both optional and operator-confirmed: `tension`, `dread`, `curiosity`, `safety`, `anomaly` in 0–1, plus `tags` and `evidence`. These are design scales, not measurements; the template should say so and keep them out of any automatic “quality” score. This also preserves the existing rule that order and complexity are never collapsed into one number.

### 3.7 Fields the open design issue #209 will need

#209 is the open design issue for door re-roll and follower mutation. This proposal does not design that behaviour and does not duplicate it. It only reserves the fields the template must be able to carry:

| #209 need | Template fields | Where |
|---|---|---|
| Door lock | `doors[].lock_state` (`open`, `closed`, `locked`), `lock_id`, `unlock_condition`, `locked_by` | map cell port or edge; runtime overlay |
| Re-roll eligibility | `doors[].reroll_eligible`, `reroll_stream`, `reroll_draw_index`, `max_rerolls`, `last_reroll_id` | map edge / runtime overlay |
| Mutation eligibility | `mutation.eligible`, `mutation.classes` (`door`, `reverb`, `palette`, `light`, `breadcrumb`), `mutation.policy`, `mutation.last_change_id` | cell |
| Follower-visible vs untouched cells | `mutation.follower_visibility` (`visible`, `untouched`), `observer_scope` | cell and door |
| Breadcrumb markers | `breadcrumb.marker_id`, `kind`, `owner_scope`, `persistent`, `sequence` | cell or edge |

The important structural point is that these are **runtime state**, not baked map data. The current `set_room_reverb` pattern is the precedent: the committed map keeps the base flag, and the running assembly writes node metadata. #209 should get the same separation, with a runtime overlay keyed by `cell_id`/`port_id`. Exact names and semantics belong to #209.

### 3.8 Fields the research issue #213 will need

#213 is the research issue for wall-material acoustics. This proposal does not choose absorption coefficients or a measurement method. It reserves:

- `module_profile.surfaces.{wall,floor,ceiling,trim}.acoustic` (existing categorical tag);
- `module_profile.acoustics.absorption.{wall,floor,ceiling,trim}` with `material_id`, `bands_hz` → coefficient, `scattering`, `measurement_source`, `confidence`;
- probe ray hit metadata: `surface_material` / `surface_acoustic` per hit, so a later probe can say which wall material produced the reflection;
- map cell `surface_composition` if a cell mixes materials (for example a concrete wall with a carpet floor).

#213 decides whether these are octave-band coefficients, a small material class table or a measured impulse response. The template only has to leave room for the answer.

### 3.9 Picture-only inputs: verified, not assumed

Picture-only ingestion is **not supported today**. The code is explicit:

- `video_source_library.VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}`; `canonical_video_path` rejects any other suffix.
- `register_video_sources.inventory` iterates `data/videos` and registers only files whose suffix is in that set.
- `video_source_library.probe_video` runs `ffprobe` with `-select_streams v:0` and raises “ffprobe did not report a video stream” when there is none.
- `video_adaptation_sources.extract_source_frames` decodes by frame index with ffmpeg and verifies decoded dimensions against the video metadata.
- `source_ingestion_runner.extract_frames` binds the extraction to `canonical_video.path` / `source_video_sha256`; `select_seed` verifies a direct video decode, not an imported still.
- `run_source_panogen.py` accepts an image seed in principle, but its guard requires `--source-video-sha256`, `--seed-frame-sha256` and a video-derived seed frame; the pipeline has no image-set registration or image-set hash to bind to.

So a picture set cannot be registered, validated, reviewed or turned into a module through the current source library. The template should define the picture-set shape now, but the implementation issue must add a new intake path rather than pretending the video path already covers it.

Proposed picture-set extension (not implemented here):

- `source_kind: "video" | "picture_set"` at the manifest root;
- `content.picture_set[]` with `image_id`, `path`, `sha256`, `width`, `height`, `capture_index`, optional `captured_at_utc`, optional `camera_pose`;
- `content.video` and `content.picture_set` are mutually exclusive, one required;
- `probe_picture_set` reads image dimensions with Pillow and hashes each file;
- `import-images` (or an equivalent stage) records an image-set extraction receipt and the same `direct_*` provenance discipline;
- Hunyuan/panogen guard binds the image-set hash instead of `source_video_sha256`;
- downstream `module_profile`, palette, acoustics and map layers are identical to the video path. A picture set has no frame timestamps; it must not invent them.

### 3.10 Re-draw and runtime mutability

The task requires layers to stay re-drawable per cell and mutable at runtime. Today:

- reverb and regional floor choices are per-cell keyed;
- light, surface/wear, elevation and palette anchors are sequential, so a single-cell re-draw would shift later cells;
- only reverb has a runtime mutator (`set_room_reverb`); palette, wear, light, elevation and door state are baked;
- the map JSON is treated as immutable by the assembly; runtime changes live in node metadata.

Recommendation: the template should distinguish `base` (the committed map/spec value) from `runtime` (an overlay keyed by cell/edge). New layers should use per-cell keyed draws from the start. Moving the old sequential layers to keyed draws is a new `gmap` version, not an in-place edit.

---

## 4. Proposed template

The recommended shape is **one source-level block, one module-level sidecar, and a map version that references both**. The existing records are not rewritten.

### 4.1 Source-level block (`source_manifest` v3)

Every newly registered video or picture set must emit at least:

```jsonc
{
  "schema_version": 3,
  "manifest_version": 3,
  "source_id": "video-<16 hex>",
  "source_kind": "video" | "picture_set",

  "content": {
    "video": {
      "path": "data/videos/<file>",
      "sha256": "<64 hex>",
      "metadata": {"width": 1920, "height": 1080, "fps": 30.0,
                   "frame_count": 7292, "duration_seconds": 243.136}
    },
    "picture_set": [
      {"image_id": "img_0001", "path": "data/pictures/<set>/<file>",
       "sha256": "<64 hex>", "width": 4000, "height": 3000,
       "capture_index": 1, "captured_at_utc": null, "camera_pose": null}
    ],
    "audio": {"present": false, "path": null, "sha256": null}
  },

  "capture": {
    "camera_model": null,
    "lens": null,
    "intrinsics": {"fx": null, "fy": null, "cx": null, "cy": null},
    "distortion": null,
    "capture_height_m": null,
    "orientation": null
  },

  "scale": {
    "status": "uncalibrated" | "calibrated",
    "method": null,                  // "known_dimension", "camera_intrinsics", ...
    "anchor": null,                  // {"kind":"door_height","value_m":2.0,"frame_id":...}
    "confidence": 0.0,
    "evidence": []
  },

  "lighting": {
    "status": "unknown" | "estimated" | "measured",
    "color_temp_k": null,
    "illuminance_lux": null,
    "fixtures": [],                  // {"kind":"fluorescent_bay","count":6,...}
    "confidence": 0.0,
    "evidence": []
  },

  "source_review": {"status": "pending_operator_review", "decision": null},
  "frame_references": [],
  "hunyuan": {"status": "not_attempted", "attempts": []},
  "room_adaptations": [],
  "registration_accepted": false,
  "scale_calibrated": false
}
```

Rules:

- `content.video` and `content.picture_set` are mutually exclusive; exactly one is required.
- Every file reference carries a SHA-256. The manifest itself is hash-pinned by the index.
- `scale.status = "calibrated"` requires a non-null `method`, `anchor` and evidence; `scale_calibrated` stays `false` until the operator accepts it.
- `lighting.status = "measured"` requires evidence and a confidence; `estimated` is explicitly a guess and must not be read as measured.
- `audio` is optional; if a source has usable audio, it is a separate evidence stream and does not by itself set room acoustics.

### 4.2 Module-level sidecar (`module_profile_v1.json`)

Recommended: a new sidecar beside `module_poetics_v2.json` (source rooms) or in `room_catalog/module_profiles/` (authored kit). It references the accepted poetics record by path/hash and never edits it.

```jsonc
{
  "schema_version": 1,
  "profile_version": "module-profile-0.1.0",
  "module_id": "<id>",
  "version": 1,
  "source_id": "video-<16 hex>" | null,
  "origin": "source_video" | "authored_kit",

  "poetics_ref": {"path": "...module_poetics_v2.json", "sha256": "<64 hex>"},
  "catalog_snapshot_sha256": "<64 hex>",
  "template_ref": {"version": "generation-template-0.1.0", "path": "...", "sha256": "..."},

  "shape": {
    "footprint_xz": [[0,0],[6,0],[6,13.8],[0,13.8]],
    "bbox_xz": {"min": [0,0], "max": [6,13.8]},
    "area_m2": 82.8,
    "ceiling_min_m": 2.4,
    "ceiling_max_m": 2.4,
    "ceiling_height_m": 2.4,
    "ceiling_kind": "flat" | "beam_grid" | "coffered" | "open_to_above" | "unknown",
    "volume_nominal_m3": 198.72,
    "volume_measured_m3": null,
    "volume_source": "envelope_area_x_max_ceiling" | "probe" | "authored"
  },

  "exits": [
    {"socket_id": "south", "kind": "tested" | "untested" | "adapter" | "void",
     "compatibility_type": "level_doorway_2m_v1",
     "width_m": 2.0, "elevation_m": 0.0,
     "circulation_role": "entrance" | "exit" | "connector" | "service" | "terminal",
     "tested_pair_ids": ["issue168_industrial_hall_south__debris_rock_north_v1"],
     "provenance": "..."}
  ],

  "roles": {
    "map_role": "ground" | "figure" | "threshold" | "void",
    "form_role": "ground" | "figure",
    "semantic_tags": ["hub", "dead_end", "landmark", "safe", "anomaly"],
    "circulation_role": "through" | "terminal" | "branch" | "hub",
    "sightline_tags": ["long_view", "occluded", "threshold_glimpse"]
  },

  "surfaces": {
    "wall":    {"material_id": "plaster_walls", "palette_id": "plaster_debris",
                "acoustic": "plaster", "texture_refs": [], "provenance": "...", "sign": "icon"},
    "floor":   {"material_id": "carpet_floor", "palette_id": "backrooms_yellow",
                "acoustic": "carpet", "texture_refs": [], "provenance": "...", "sign": "icon"},
    "ceiling": {"material_id": "ceiling_tile", "palette_id": "backrooms_yellow",
                "acoustic": "tile", "texture_refs": [], "provenance": "...", "sign": "symbol"},
    "trim":    {"material_id": "metal_trim", "palette_id": null,
                "acoustic": "metal", "texture_refs": [], "provenance": "...", "sign": "symbol"}
  },

  "acoustics": {
    "status": "tag_only" | "probed" | "measured",
    "tag": "carpet",
    "probe": {
      "probe_version": "room-acoustic-probe-0.1.0",
      "mean_distance_m": null, "max_distance_m": null,
      "ceiling_height_m": null, "openness": null,
      "room_size": null, "damping": null, "wet": null, "predelay_msec": null,
      "sample_points": [], "evidence": []
    },
    "absorption": {
      "status": "unknown" | "estimated" | "measured",
      "wall": null, "floor": null, "ceiling": null, "trim": null,
      "source": "#213", "confidence": 0.0
    }
  },

  "lighting": {
    "status": "unknown" | "source_estimated" | "operator_confirmed",
    "tier": null, "color_temp_k": null, "illuminance_lux": null,
    "fixtures": [], "evidence": []
  },

  "scale": {"status": "uncalibrated" | "calibrated", "anchor": null,
            "confidence": 0.0, "evidence": []},

  "mood": {
    "tension": null, "dread": null, "curiosity": null,
    "safety": null, "anomaly": null,
    "tags": [], "evidence": []
  },

  "runtime": {
    "mutation_eligible": false,
    "mutation_classes": [],
    "follower_visibility": "visible" | "untouched",
    "breadcrumb_policy": "none" | "marker" | "trail"
  },

  "translation_chain": [],
  "eligibility": {"layout_eligible_derived": false, "catalog_layout_eligible": null}
}
```

Notes:

- `volume_nominal_m3` is a derived heuristic and must be labelled as such. `volume_measured_m3` is null until a probe or operator measurement exists.
- `surfaces` is the bridge to `palettes-0.3.0.json`. A module may have `palette_id: null` when its material is bespoke; the `material_id` and `acoustic` tag still make it usable.
- `acoustics.tag` preserves the existing `module_acoustics.json` behaviour; `acoustics.probe` is the new measured descriptor.
- `mood` and `roles.semantic_tags` are operator/vision judgements, not measurements.
- `runtime` is a policy declaration; actual runtime state lives in the overlay described in 4.4.

### 4.3 Map-level additions (`gmap-0.13.0`, schema v2)

Existing map fields stay as they are. A new map version adds references and the fields that #209/#213 need:

```jsonc
{
  "schema_version": 2,
  "generator_version": "gmap-0.13.0",
  "template": {"version": "generation-template-0.1.0", "path": "...", "sha256": "..."},

  "cells": [{
    "cell_id": "c07",
    // ... existing envelope, ceiling_range_m, ports, role, rarity_tier, floor_y,
    //     palette, wear, surface_variants, light, reverb, landmark, diagonal_passage ...

    "module_profile": {"path": "...module_profile_v1.json", "sha256": "<64 hex>"},
    "volume": {"nominal_m3": 198.72, "measured_m3": null,
               "source": "module_profile" | "cell_envelope"},
    "mood": {"tension": null, "tags": []},

    "doors": [{
      "port_id": "c07:e",
      "state": "open" | "closed" | "locked",
      "lock": {"lock_id": null, "unlock_condition": null, "locked_by": null},
      "reroll": {"eligible": false, "stream": "door-reroll:gmap-0.13.0",
                 "draw_index": null, "max_rerolls": 0, "last_reroll_id": null},
      "follower_visibility": "visible" | "untouched",
      "breadcrumb": {"marker_id": null, "kind": null, "persistent": false}
    }],

    "mutation": {
      "eligible": false,
      "classes": [],
      "follower_visibility": "visible" | "untouched",
      "policy": "none",
      "last_change_id": null
    }
  }],

  "edges": [{
    "from": "c07:e", "to": "c08:w", "connector": "direct",
    "connection_status": "proposed_untested",
    "door_id": "c07:e"
    // ... existing vertical/ramp/drop/diagonal fields ...
  }]
}
```

The map should not store live door locks or follower state. It stores the **base policy and eligibility**; a runtime overlay stores the current state. This mirrors `reverb` today.

### 4.4 Assembly-side acoustic projection (`module_acoustics` v0.2.0)

Keep the existing sidecar pattern. A new version is a projection of accepted `module_profile` records; library scenes and poetics files are never edited:

```jsonc
{
  "generator": "godot_walk/scripts/module_acoustics.py",
  "generator_version": "module-acoustics-0.2.0",
  "schema_version": 2,
  "source_index": {"path": "...", "sha256": "..."},
  "modules": {
    "<module_id>@1": {
      "acoustic": "carpet",
      "evidence": ["carpet_floor"],
      "poetics": {"path": "...", "sha256": "..."},
      "profile": {"path": "...", "sha256": "..."},
      "probe": {"mean_distance_m": 6.55, "max_distance_m": 9.1,
                "ceiling_height_m": 4.6, "openness": 0.0,
                "room_size": 0.687, "damping": 0.648,
                "wet": 0.583, "predelay_msec": 19.1},
      "absorption": {"status": "unknown", "source": "#213"}
    }
  }
}
```

`generative_map_assembly._tag_module_floor` keeps reading the categorical tag; a later issue can also expose the probe values as room metadata. No module scene changes. The probe values shown are #205's `c04` shape-room example, included only to show the shape of the record; they are not a measurement of a library module.

### 4.5 Which fields are automatic and which need review

| Field group | Automatic | Operator / vision review | Notes |
|---|---|---|---|
| Source/file hashes, dimensions, fps, frame count, frame IDs | yes | no | `sha256_file`, `probe_video`, extraction manifest |
| Frame timestamps and decode provenance | yes | no | ffmpeg decode; direct-source rule |
| Footprint, bbox, area, aspect, convexity, symmetry, ceiling from scene | yes | ceiling value may be authored | `module_poetics.py`, `poetics_geometry.py` |
| Ports, tested/untested sockets, port slots | yes from index | tested-pair status is operator-approved | `module_poetics.build_ports` |
| Palette tag / palette id | yes from registry `match_style_tags` | material exceptions need review | `gmap_palette_registry.select_palette` |
| Acoustic tag | yes from style tags | measured probe needs a built room | `module_acoustics.derive_acoustic` |
| Per-surface material id / texture refs | partly | yes when the scene does not expose a material | proposed `surfaces` block |
| Measured probe values | yes when a probe run exists | operator listens / accepts the result | #205 probe; no stored module values yet |
| Source lighting, scale | no | yes (vision/operator) | parked #187 |
| Poetics, semantic roles, mood | no | yes; model may propose, off by default | no free-model calls |
| Door lock/re-roll, mutation, follower visibility, breadcrumbs | policy only | yes; #209 design | runtime overlay |
| Wall absorption | no | research #213 | coefficients not chosen here |
| Picture-set import | no | operator review | new intake path required |

---

## 5. Ingestion contract

Every newly ingested video or picture set must produce the following. “Required” means the stage refuses to complete without it; “nullable” means the key exists with `null` until a later review.

### 5.1 Source registration

Required:

1. `source_kind` (`video` or `picture_set`).
2. Content identity: `path`, `sha256`, and either video metadata (`width`, `height`, `fps`, `frame_count`, `duration_seconds`) or a picture-set list with per-image `image_id`, `path`, `sha256`, `width`, `height`, `capture_index`.
3. `capture` block: camera model/lens/intrinsics/distortion/capture height/orientation, nullable.
4. `scale` block: status, method, anchor, confidence, evidence.
5. `lighting` block: status, colour temperature, illuminance, fixtures, confidence, evidence.
6. `source_review`: pending until the operator records `proceed`, `proceed_with_limitations` or `reject`.
7. `registration_accepted: false` and `scale_calibrated: false` at registration.

Derived automatically: hashes, media metadata, image dimensions, frame/image IDs, manifest hash. Review: source suitability, scale, lighting, any claim about the source.

### 5.2 Frame or image extraction

For video: direct-source frames only, no resize/edit, frame index + PTS + SHA-256 + extraction manifest, as `video_adaptation_sources.extract_source_frames` does today.

For a picture set: direct image import only, no resize/edit, `image_id` + capture index + SHA-256 + image dimensions + import manifest. Do not invent a frame timestamp. The import receipt must bind the image-set hash, not a video hash.

### 5.3 Room admission and mechanical module metadata

Required per admitted room/module:

1. `module_id`, `version`, `source_id`, `room_dir`, catalog snapshot hash, library index path/hash.
2. `shape`: footprint, bbox, area, aspect, convexity, rectilinear, primitive, shape stage, symmetry, `ceiling_min_m`, `ceiling_max_m`, `ceiling_height_m`, `ceiling_kind`.
3. `ports`: tested sockets, untested sockets, port slots, and the new `exits[]` with circulation role.
4. `features` and `voids` as today, with `index`/`icon`/`symbol` signs.
5. `surfaces`: wall/floor/ceiling/trim material id, palette id (nullable), acoustic tag, texture refs, provenance.
6. `layers`: shape, surface, collision, light (light may be `unknown` until #187).
7. `translation_chain`: direct frame → panorama (if any) → Godot room.
8. `poetics`: Karth axes, form role, rarity, style tags, surface salience, unique details, status.
9. `acoustics`: tag now; probe block once a probe run exists.
10. `lighting`, `scale`, `mood`, `roles`, `runtime` policy.
11. `eligibility`: derived, never asserted.

Automatic: shape geometry, ports, features/voids, hashes, palette/acoustic tags where the inputs exist. Operator/vision: poetics, semantic roles, mood, source lighting, scale, any material the scene does not expose.

### 5.4 Map generation

The map generator consumes the module profile, not the raw scene:

- module placement and `connection_status` as today;
- `module_profile` ref on the cell;
- `volume` nominal/measured;
- `mood` from the module profile;
- `doors` and `mutation` base policy;
- existing palette/wear/light/elevation/reverb layers unchanged for generated cells;
- no map JSON mutation at runtime.

### 5.5 Picture-only fit

A picture set follows the same contract with three substitutions:

1. `source_kind = "picture_set"`, `content.picture_set[]` replaces `content.video`.
2. `import-images` replaces `extract-frames`; the receipt binds the image-set hash and per-image hashes.
3. The Hunyuan/panogen guard binds the image-set hash and a selected `image_id` instead of `source_video_sha256` and a video frame ID.

Everything downstream — module profile, palette, acoustics, map, assembly — is identical. This is the cleanest way to let new videos and new picture sets feed every layer without a second metadata vocabulary.

---

## 6. Versioning plan

The rule is: **never edit a frozen record; add a new version and reference the old hash.**

### 6.1 New template version

- Template name: `generation-template-0.1.0` (proposal).
- `source_manifest` schema v3: adds `source_kind`, `content`, `capture`, `scale`, `lighting`, `audio`. New manifests are `source_manifest-vN.json` with `schema_version: 3`; v1/v2 manifests and their chains remain valid.
- `module_profile` schema v1: new sidecar `module_profile_v1.json`, keyed by `(module_id, version, poetics sha256)`. Existing `module_poetics` schema v1 records are untouched. If the operator prefers to extend `module_poetics` instead, the same fields can be added as schema v2 and new records named `module_poetics_v3.json`; the hash-pinning rule is the same. The sidecar is recommended because it keeps the accepted poetics record exactly as reviewed.
- `generative_map` schema v2: new file `generative_map_v2.schema.json` (or a versioned `$id` in the same path) with `schema_version: 2`; `gmap-0.13.0` is the first generator version that emits it. Existing `gmap-0.1.0`–`gmap-0.12.0` maps keep validating against schema v1.
- `module_acoustics` v0.2.0: new file or new `generator_version` in a versioned sidecar; it is a projection, not an edit of any module.
- Palette registry: `0.3.0` stays canonical for existing maps. A new `0.4.0` is only needed if module surface records require materials that do not exist in `0.3.0`; new maps reference the new registry by path/hash.

### 6.2 Hash-pinned files

The following are never edited by this programme:

- `scripts/player.gd`, `project.godot`;
- library room scenes and their textures;
- `catalog.json` and committed catalog snapshots;
- `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md`, `PALETTES_0_2_0.md`, `PALETTES_0_3_0.md`;
- accepted `module_poetics_v2.json` / `*.accepted.json` records.

New information goes into a new sidecar that references the frozen hash. If a module’s geometry genuinely changes, that is a new module version and a new catalog snapshot, not an edit.

### 6.3 Runtime overlay

- The committed map is the base.
- The running assembly reads base values and writes node metadata, as `set_room_reverb` does today.
- New runtime state (door lock, re-roll result, follower visibility, breadcrumb) lives in an overlay keyed by `cell_id`/`port_id`; it is not written back into the map JSON.
- A later save/restore format, if needed, serialises the overlay separately and records the base map hash.

### 6.4 Draw-stream migration

- Reverb and regional floor palettes already use per-cell keyed draws; keep that pattern.
- Light, surface/wear, elevation and palette anchors are sequential today. Moving them to per-cell keys changes the generated result, so it belongs in `gmap-0.13.0` (or later), with new committed maps and new evidence. Do not silently change the old stream and expect old maps to match.
- New layers (`mood`, `doors`, `mutation`, `absorption`) must use per-cell keyed draws from day one if they are generated at all.

### 6.5 Backfill and migration

- 12 registered sources and 11 modules exist today. Backfill should create `module_profile_v1.json` sidecars for the 11 modules, referencing their existing accepted poetics hashes. No source re-ingest is required for those 11.
- The 5 committed `gmap-0.12.0` maps stay as they are. New `gmap-0.13.0` maps are generated for the same seeds if the operator wants a comparison; old maps remain valid.
- #195 and #174–#180 should ingest against the new contract, not the old one. That is the point of doing #212 before #195.

---

## 7. Related issues, not duplicated here

### #209 — door re-roll and follower mutation

#209 owns the design of door locks, re-roll rules, mutation eligibility, follower-visible vs untouched cells and breadcrumb markers. This proposal only reserves the fields listed in 3.7 and recommends the runtime-overlay pattern. Do not implement #209 from this document.

### #213 — wall-material acoustics

#213 owns the research and measurement method for wall absorption. This proposal only reserves the per-surface `acoustic`/`absorption` fields and the probe’s surface-hit metadata listed in 3.8. Do not choose coefficients or a probe algorithm here.

### #187 — source lighting and scale calibration

#187 owns the method for deriving source lighting and real-world scale. This proposal reserves `source_manifest.scale` / `lighting` and `module_profile.scale` / `lighting`, and defaults them to `uncalibrated` / `unknown`. No fabricated values.

---

## 8. Recommended order and implementation issues

### Recommended order

1. **Operator review of this proposal.** Freeze or rename the template fields. Decide sidecar vs `module_poetics` schema v2.
2. **Template/schema issue.** Add `module_profile` schema v1, source-manifest v3, `generative_map` schema v2 and validators. No behaviour change; old records stay valid.
3. **Mechanical profile derivation.** Extend `derive-module-metadata` (or add a profile stage) to emit `module_profile_v1.json` from the catalog/scene; operator accepts it. Backfill the 11 existing modules.
4. **Per-module acoustic probe.** Run the #205 probe on each module in a probe assembly; write the measured block into `module_acoustics` v0.2.0. This is the first measured module descriptor.
5. **Module surfaces and palette mapping.** Fill `surfaces` from scene materials, map to `palettes-0.3.0.json` where possible; add a `0.4.0` registry only if a material is missing.
6. **Lighting and scale (#187).** Add the source/module fields and the operator review; keep `uncalibrated` until measured.
7. **Ceiling/volume/exits/roles/mood.** Fill the remaining module profile fields; operator reviews the semantic tags and mood.
8. **`gmap-0.13.0` consumption.** Emit `module_profile` refs, `volume`, `mood`, `doors`, `mutation`; keep old maps valid; add validator checks.
9. **Picture-set intake.** Add `source_kind: picture_set`, image-set hashing, `import-images`, guard binding; run one operator-reviewed picture set end to end.
10. **#195 and #174–#180 ingestion.** Ingest the new batch against the completed contract. Do not re-ingest the existing 11 modules.
11. **#209 runtime overlay.** Implement door locks/re-roll/follower/breadcrumb state after #209’s design is accepted.
12. **#213 wall absorption.** Add coefficients and probe surface hits after #213’s research is accepted.

### Concrete implementation issues to file after review

| # | Proposed title | Scope | Depends on | Acceptance |
|---|---|---|---|---|
| T1 | Add `module_profile` schema and source-manifest v3 | New schema files, validators, no behaviour change; keep v1/v2 records valid | operator accepts field names | schema tests pass; old records still validate |
| T2 | Derive and accept module profiles for the 11 existing modules | Mechanical shape/ports/surfaces/acoustics tag; operator accepts; write sidecars only | T1 | 11 profiles, each references its frozen poetics hash |
| T3 | Add per-module acoustic probe and `module_acoustics` v0.2.0 | Probe each module in a headless assembly; store measured metrics; no module edits | T1, T2, #205 | probe values reproducible; sidecar hash-pinned |
| T4 | Add module surface/palette descriptor | Fill wall/floor/ceiling/trim material + palette id; map to `palettes-0.3.0.json`; new 0.4.0 only if needed | T1, T2 | every module surface resolves or is explicitly `null`/bespoke |
| T5 | Add source lighting and scale fields (#187) | Manifest + module profile fields; operator/vision review; default uncalibrated | T1, #187 method | one source and one module carry reviewed values; false stays false until accepted |
| T6 | Add ceiling/volume/exits/roles/mood descriptors | Module profile fields and operator review; no map change yet | T1, T2 | fields validate; measured vs authored is explicit |
| T7 | Emit `gmap-0.13.0` with template references and #209/#213 placeholders | New generator version, schema v2, maps/fills/SVGs/shape rooms; old maps unchanged | T1–T6, T7 | committed maps validate; old maps still validate |
| T8 | Add picture-set intake | `source_kind`, image-set hashing, `import-images`, guard binding; no video regression | T1 | one picture set registers, reviews, imports and produces a module profile |
| T9 | Backfill and regression run for #195 | Ingest the new batch; no re-ingest of existing 11; full Python/Godot checks | T1–T8 | #195 batch completes against the new contract |
| T10 | Implement #209 runtime overlay | Door locks/re-roll/follower/breadcrumb state; map base immutable | #209 design, T7 | overlay survives save/restore; map hash unchanged |
| T11 | Implement #213 wall absorption | Per-surface coefficients and probe surface hits | #213 research, T3, T7 | measured absorption used by the reverb bus; no fabricated coefficients |

T7 depends on T1–T6; the numbering above is the filing order, not a strict dependency chain. T10 and T11 are explicitly downstream of their design/research issues and should not be filed as implementation until those issues close.

---

## 9. Scope guard

This proposal intentionally does **not**:

- edit `scripts/player.gd`, `project.godot`, any library room scene, `catalog.json`, `room_catalog/MATERIAL_LANGUAGE.md`, `PALETTES.md` or `PALETTES_0_3_0.md`;
- change a schema, map, shape-room spec, palette or event log;
- re-ingest an existing source or rewrite a frozen module;
- infer source-video connectivity or promote an `index` observation to a traversable connector;
- set `registration_accepted` or `scale_calibrated` to true;
- call a free model; model proposals remain optional and off by default.

The operator reviews this document first. Only then should T1 be filed, and #195 should wait until the template is accepted.

---

## Appendix A — code and evidence citations

### Map generation and validation

- `godot_walk/scripts/gmap_build.py` — generator versions `gmap-0.1.0`–`gmap-0.12.0`; `build_map` composition order; `cell_json`; `rule_ids`.
- `godot_walk/scripts/gmap_validate.py` — schema/hash/rule validation; calls `light_errors`, `surface_errors`, `elevation_errors`, `reverb_errors`, `palette_errors`, `module_errors`, `landmark_errors`, `diagonal_errors`.
- `godot_walk/scripts/gmap_draft_generation.py` — layout stream `gmap-layout-0.6.1`; attempt/variant.
- `godot_walk/scripts/gmap_degenerate.py` — `degenerate:{version}`.
- `godot_walk/scripts/gmap_stage2.py` — `shape_stage:{version}`.
- `godot_walk/scripts/gmap_diagonal.py`, `gmap_diagonal_sites.py`, `gmap_diagonal_v61.py` — `diagonal-links:gmap-0.6.0`, `diagonal-sites:gmap-0.6.1`.
- `godot_walk/scripts/gmap_landmark.py`, `gmap_landmark_growth.py` — `landmark:gmap-0.7.0`.
- `godot_walk/scripts/gmap_light.py` — `light:gmap-0.8.0`; dark wing; module/landmark exclusion.
- `godot_walk/scripts/gmap_surface.py` — `surface:gmap-0.9.0`; wear/variants; module exclusion.
- `godot_walk/scripts/gmap_elevation.py` — `elevation:gmap-0.10.0`; levels/ramps/drops/loops; ceiling clearance.
- `godot_walk/scripts/gmap_reverb.py` — `reverb:gmap-0.11.0:<cell_id>`; nominal volume heuristic; runtime-mutable flag.
- `godot_walk/scripts/gmap_floor_regions.py` — `floor_regions:gmap-0.12.0`; per-cell keyed draw; region budget.
- `godot_walk/scripts/gmap_palette.py`, `gmap_palette_registry.py` — palette anchor stream `palette:gmap-0.7.0`; registry versions; `ACOUSTIC_TAGS`.
- `godot_walk/scripts/gmap_modules.py`, `gmap_library.py`, `gmap_module_rules.py` — module placement, tested socket, leaf rule, role/tier.

### Module metadata

- `godot_walk/room_catalog/module_poetics.schema.json` — schema v1 fields; `layers.light` null/not derived; `poetics`; eligibility.
- `godot_walk/scripts/module_poetics.py` — `DERIVER_VERSION = module-poetics-0.1.0`; `build_shape`, `build_layers`, `derive_record`.
- `godot_walk/scripts/poetics_geometry.py`, `poetics_signs.py` — mechanical geometry/sign derivation.
- `godot_walk/scripts/module_integration_stages.py` — `plan_derive`, `plan_accept`, `plan_propose`, `plan_decide`.
- `godot_walk/scripts/module_acoustics.py` — `module-acoustics-0.1.0`; precedence; sidecar projection.
- `godot_walk/room_catalog/module_acoustics.json` — 11 module entries, tags and poetics hashes.
- `godot_walk/room_catalog/module_poetics/*.accepted.json`, `godot_walk/source_library/sources/*/rooms/*/module_poetics_v2.json` — accepted poetics records.
- `godot_walk/room_catalog/library_index/godot_psx_room_kit-0.5.0.json` — 11 modules, 2 tested pairs, snapshot hash.

### Map schema and runtime

- `godot_walk/room_catalog/generative_map.schema.json` — schema v1; cell/edge fields; version-conditional requirements; module cells carry no palette.
- `godot_walk/scripts/shape_room_spec.py` — `build_spec`, `_attach_light`, palette materials, ceiling, floor_y, ramps.
- `godot_walk/scripts/shape_room_palette.py` — palette resolution for v0.5/v0.9/v0.12.
- `godot_walk/scripts/shape_room_builder.gd`, `shape_room_materials.gd`, `shape_room_lighting.gd` — runtime construction, materials, lights.
- `godot_walk/scripts/generative_map_assembly.gd` — module placement, `_tag_reverb`, `set_room_reverb`, `room_reverb_at`, `nominal_room_volume_m3`, `_tag_module_floor`, `room_ceiling_height_at`.
- `godot_walk/scripts/room_acoustic_probe.gd` — probe metrics and `map_metrics`.
- `godot_walk/scripts/room_reverb_bus.gd`, `walk_player.gd` — reverb bus, 4 Hz probe sampling, footstep `surface_acoustic`.

### Source ingestion

- `godot_walk/source_library/source_manifest.schema.json`, `source_manifest_v2.schema.json` — current manifest fields.
- `godot_walk/scripts/video_source_library.py` — `VIDEO_SUFFIXES`, `canonical_video_path`, `probe_video`, index/manifest validation.
- `godot_walk/scripts/register_video_sources.py` — inventory/register/append_event.
- `godot_walk/scripts/source_ingestion_runner.py` — source review, extract-frames, select-seed, derive/accept/propose/decide stages.
- `godot_walk/scripts/video_adaptation_sources.py` — `extract_source_frames`, ffmpeg decode, dimension verification.
- `godot_walk/scripts/run_source_panogen.py`, `source_ingestion_gpu.py` — image-seed panorama guard bound to `source_video_sha256`.

### Evidence

- `godot_walk/evidence/2026-11-09-issue-205/REPORT.md` — probe metrics, four measured rooms, wall absorption out of scope.
- `godot_walk/evidence/2026-11-09-issue-208/REPORT.md`, `palette_mix.json` — 768 cells, palette mix, floor acoustic tags, module cells no palette.
- `godot_walk/evidence/2026-11-09-issue-204/REPORT.md` — reverb flag and runtime mutability.
- `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` — original 2026-11-02 metadata design and theory mapping.
- `PLAN.md` — #169 context and the current workflow constraints.
