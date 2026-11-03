# Generative Map Metadata and Library Integration — Proposal

Status: proposal for operator review (2026-11-02). Epic: #169 (under #117); layout lineage #144 / #149 / #162.
Theory sources (converted with the `marker` conda env, see `docs/markdown/`):

- Karth, *Preliminary Poetics of Procedural Generation in Games* (DiGRA 2018) — `docs/markdown/fulltext/fulltext.md`
- Gerner, *Critical Generative AI Aesthetics* (Semeiosis 2023) — `docs/markdown/10.53987-2178-5368-2023-12-05-1702818705/…md`
- Manovich & Arielli, *Artificial Aesthetics* — `docs/markdown/manovich_and_arielli.artificial_aesthetics.all_chapters_final/…md`

Nothing here changes an approval, the catalog, a source event, or `registration_accepted=false` / `scale_calibrated=false`.

---

## 1. Where the library is today (audit, 2026-11-02)

| Source | Video | Library state |
|---|---|---|
| video-ccf9722164a0bdc8 | GoPro FPV abandoned building | Full loop. 2 accepted rooms (#167 frame-1097 hall in catalog; #168 debris-window room + connector). **Event log stops at seq 38; admissions only exist as room-folder files → #170** |
| video-b9161c467ed2d30a | Bill Viola, *The Sleep of Reason* | Full loop through `catalog_admission_accepted` and `operator_requested_module_integration_proposals` (seq 14). Proposals not yet produced |
| video-ef0ec21cd4ae7b26 | room_large | Historical #163 adaptation in catalog; log has registration only → #179 |
| video-51abd379f94b8f84 | corridor_corner | Historical #165 manual adaptation; log has registration only → #180 |
| 8 others | Backrooms FF#55, Antelope Canyon, Max Cooper, Cornell *Angel*, corridor_straight / _t / _x, dead_end | Registered and hash-valid only → #171–#178 |

`register_video_sources.py validate` → `{"valid": true, "registered_count": 12}`.

The catalog has 8 modules, one tested connector pair, and every module is an axis-aligned box. Two of the eight (`godot_gopro_…frame1097_v1` and `video_b9161…bill_viola_single_room_v1`) have `layout_eligible: false` and no sockets, so they cannot enter generation. That is the real bottleneck. The fix is to stop treating each admitted room as an endpoint and to give every module enough **metadata** that a map can ask for it.

---

## 2. Core principle: the map comes first, rooms fit inside it

> Every generated or library room is placed **into a cell of a generative map** and must fit that cell's envelope, ports and role. A room never enlarges, re-routes or re-opens the map.

Karth's argument for this is that "every generator needs to ground-out in designer-created input" (*Cohesion: Data, Metadata, Beeswax*). Generators stay coherent through **metadata that is "visibly related to the shape of the underlying generative system."** Our designer-created input is the operator-approved room library. The metadata is the contract between that library and the map, so the map is the structure that new shapes have to respect.

The pipeline has three layers, each with its own record:

```
L0  generative_map      (structure: lattice, cells, ports, roles, distribution)   ← seed + rules
        │  cell asks for: envelope, required ports, role, rarity tier
        ▼
L1  module_poetics      (per admitted library module: shape, ports, poetics, provenance-by-sign)
        │  fit test: footprint ⊆ envelope, tested sockets ⊇ required ports, role/tier match
        ▼
L2  shape_room          (generated Euclidean room for cells no module fills, bounded by the cell)
        │
        ▼
L3  integration_proposal (append-only; operator chooses; never auto-admitted)
```

---

## 3. What the theory contributes (and which field it becomes)

### 3.1 Karth: four axes, each becomes a generator knob

| Karth axis | Meaning in a Backrooms maze | Field |
|---|---|---|
| **Complexity**: Apollonian order vs Dionysian noise (not opposites; high complexity is high in both) | Lattice regularity, symmetry, repetition of fluorescent bays (order) vs debris, occlusion, off-grid obstacles, unresolved gaps (noise) | `poetics.apollonian` 0–1 and `poetics.dionysian` 0–1, scored separately, never summed |
| **Form**: formal gestalt / repetition / individual | Endless yellow rooms work as gestalt ("orchard" repetition); a source room like the GoPro hall is an *individual* | `poetics.form_role ∈ {ground, figure}`; map `repetition_budget` |
| **Locus**: structure / surface / locus gestalt | Players should be able to *infer* the generator (Karth's "tells", e.g. Spelunky's exit is always lower). Consistent rules about where ports occur | Map `rules[]`: declared, testable invariants |
| **Variation**: multiplicity / style / cohesion | The "10,000 bowls of oatmeal" risk: many layouts that feel identical. Style keeps rooms on-brief (PSX, Backrooms material language) | `poetics.style_tags` (from `room_catalog/MATERIAL_LANGUAGE.md`), map `distinctness_floor` |

*Hierarchy and distribution* (Karth): rare artifacts read as landmarks and frequent ones as background, and non-linear, biased distributions beat uniform ones. So **source-video rooms are rare figures** and **generated Euclidean rooms are the common ground**. The map takes a `rarity_tier` per cell and samples tiers from a biased (e.g. 2d6-like) curve, not a uniform one.

### 3.2 Gerner: gaps, abduction, and three kinds of sign

Gerner's "critique of generativity" targets "excessive richness of details and the missing of gaps, … abductive voids." In a maze this argues for **leaving deliberate unresolved space**: closed thresholds, dark gaps, unreachable glimpses. The existing records already hold these as `observed_openings` with `tested_connector: false`, for example the GoPro frame-1097 "far-right gap". Rather than drop them, the metadata promotes them to **`voids`**: visible, never traversable, and counted by the map as a poetic resource (`void_budget`).

Gerner's use of Peirce's sign types maps exactly onto the provenance discipline this project already enforces. Every geometric or visual feature gets a `sign` field:

| Peirce | Definition (via Nöth, in Gerner) | In this project |
|---|---|---|
| **index** | "real connection" to its object | Seen in a direct-source frame (cites frame ID + hash) |
| **icon** | sign "by resemblance" | Textures, crops, panorama-derived surfaces: they resemble the source but are not observed geometry |
| **symbol** | understood through "factitious habits of interpreters" (convention) | Authored sockets, collision, connectors, generated shape rooms |

Rule: **only `symbol` features may be traversable connectors**, and they always need tests. `index` features may motivate a proposal but never certify one. This puts the existing rule ("do not infer video connectivity") into the schema itself.

Gerner's critique of Birkhoff's M = O/C (one ratio cannot capture aesthetic value) is also why order and complexity stay separate scores in §3.1. They are never collapsed into a single "quality" number the generator could optimise.

### 3.3 Manovich & Arielli

Four ideas from the book apply directly:

- **"Separate and Reassemble"** (ch. 7): CG "takes the world which we see apart, separating objects' shapes, materials, light reflections, textures…"; its representations "are discrete and modular, rather than continuous." This is the case for keeping **shape, surface/material, light, and collision as separate metadata layers** that are recombined at assembly. It is what lets a generated Euclidean shape borrow the surface language of a source room without pretending to be that room. The project already keeps geometry, visual, and collision provenance separate; the metadata makes those layers addressable by the generator.
- **"The Stereotypical and the Unique"** (ch. 5): generative models fall back on a default "house style" and "stereotypical details", while uniqueness comes from details "sufficiently distinct to appear novel." Hunyuan panoramas are a prediction and lean stereotypical; the direct-source frames carry the unique details. So `module_poetics` records **`unique_details[]`** (each citing a source frame), and only modules with source-unique details may take figure/landmark tiers. Generated shape rooms are the stereotypical ground on purpose. That is a deliberate use of the house style, not a failure of it.
- **"From Representation to Prediction" / media translations**: video → panorama → PSX room is a chain of *translations*, not a one-to-one mapping. Each module records its `translation_chain` (direct frame → Hunyuan panorama → authored Godot room) so a reviewer can see where prediction entered.
- **"The Goddess of Chance"** (ch. 8): we attribute autonomy to what we cannot predict, while professionals want control. The kaleidoscope, with regular structure produced from random fragments, is Karth's Apollonian + Dionysian in one image. The design answer is **a deterministic seed with declared rules (control and reproducibility) plus biased sampling (surprise)**, with the operator keeping authorship through proposal choices.

---

## 4. Metadata records

### 4.1 `generative_map` (L0): new schema `room_catalog/generative_map.schema.json`

```jsonc
{
  "schema_version": 1,
  "map_id": "gmap-<seed>-<generator_version>",
  "generator_version": "gmap-0.1.0",
  "seed": 1234,
  "catalog_snapshot": {"path": "…/catalog_snapshots/godot_psx_room_kit-0.5.0.json", "sha256": "…"},
  "lattice": {"kind": "square", "unit_m": 1.0, "port_unit": "level_doorway_2m_v1"},
  "shape_stage_max": 1,                          // §5 gate: which primitives the map may request
  "cells": [{
    "cell_id": "c07",
    "envelope_xz": [[0,0],[12,0],[12,8],[0,8]],  // hard bound for any room in this cell
    "ceiling_range_m": [2.6, 4.8],
    "allowed_primitives": ["box", "rect_poly"],
    "required_ports": [{"port_id": "c07:e", "pos_xz": [12,4], "normal": [1,0], "compatibility_type": "level_doorway_2m_v1"}],
    "role": "ground | figure | threshold | void",
    "rarity_tier": 0
  }],
  "edges": [{"from": "c07:e", "to": "c08:w", "connector": "direct | authored_connector_id"}],
  "distribution": {"tier_curve": "2d6", "repetition_budget": {"max_same_module_adjacent": 0, "max_same_primitive_run": 3}},
  "void_budget": {"min": 1, "max": 4},
  "rules": ["ports only on lattice edges", "figure cells never adjacent", "every void is visible from a walkable cell"],
  "registration_accepted": false, "scale_calibrated": false
}
```

### 4.2 `module_poetics` (L1): sidecar per admitted module, keyed by `(module_id, version, catalog sha256)`

Stored at `source_library/sources/<sid>/rooms/<room_id>/module_poetics_v<N>.json`. The catalog points to it and never rewrites the admitted module.

| Group | Fields | Who fills it |
|---|---|---|
| identity | module_id, version, source_id, room_id, catalog_snapshot sha256 | mechanical |
| shape | `primitive` (best-fit from §5), `footprint_xz` (from catalog), aspect ratio, convexity, `symmetry` (C1/C2/D2/D4…), ceiling height | mechanical (polygon analysis of `placement_footprint_xz`) |
| ports | `tested_sockets[]` (copied from the catalog, the only ones layout may use); `port_slots[]` = boundary edges where an authored adapter *could* be added (proposal-only) | mechanical + operator |
| sign | each obstacle, opening and surface tagged `index` / `icon` / `symbol` with a citation | mechanical from the adaptation `provenance` strings, operator-checked |
| voids | `observed_openings` with `tested_connector:false`, carried forward as non-traversable voids | mechanical |
| poetics | `form_role`, `rarity_tier`, `apollonian`, `dionysian`, `style_tags`, `surface_salience` (what the player notices first), `unique_details[]` (frame-cited) | model-proposed (optional, off by default) → operator-confirmed |
| layers | separate refs for `shape`, `surface`, `light`, `collision` (Manovich's separate-and-reassemble), plus `translation_chain` (frame → panorama → room) | mechanical from adaptation record |
| eligibility | `layout_eligible` is **derived**: true only if ≥1 tested socket exists and the operator accepted the metadata | computed, never asserted |

### 4.3 `shape_room` (L2): generated Euclidean room for a cell

Parametric primitive + parameters + the cell it was generated for + analytic collision + PSX material assignment from `MATERIAL_LANGUAGE.md`. Every feature carries `sign: symbol`. It is a generated *candidate*: it goes through the same mechanical checks and operator review as any other room.

### 4.4 `integration_proposal` (L3)

This extends the #169 spec's proposal record (target module IDs/versions, catalog snapshot hash, placement, sockets or adapter, clearance, rationale, assumptions, evidence, confidence) with `map_id`, `cell_id`, and the fit result. "Keep standalone" and abstain remain valid outcomes. Proposals are append-only in the source's `events.jsonl` (`integration_proposal_recorded`, `integration_proposal_decided`).

---

## 5. Shapes: one Euclidean step at a time

Each stage unlocks only after the previous one passes its gate: analytic collision, port compatibility, bidirectional Godot traversal, no exposed drops, and operator review of one generated walk. The map's `shape_stage_max` is the switch.

| Stage | Primitives | Port rule | Why it comes at this point |
|---|---|---|---|
| **0** (today) | axis-aligned box | 4 cardinal faces | Existing catalog |
| **1** | rectilinear polyominoes: corridor 1×n, L, T, U, + (cross), rectangles with varied aspect | ports on lattice edges, cardinal normals | Matches the corridor_t / _x / dead_end / straight sources (#175–#178); fills the branching gap #144 flagged |
| **2** | 45° chamfered boxes, octagon, right-triangle wedge | ports may sit on 45° faces; `normal` in 8 directions | First non-orthogonal walls while collision stays trivially convex |
| **3** | regular n-gon prisms (hex, oct), cylinder/rotunda discretised to N≤16 facets (PSX-friendly) | ports on facets only | Centralised "figure" rooms: landmarks for Karth's hierarchy |
| **4** | vertical Euclidean variation: ceiling-height bands, steps/ramps between floor elevations, simple vaults | port `floor_elevation_m` must match or go through a ramp connector | Elevation change without curved walls |
| **5** | swept/extruded arcs and curved corridors (polyline-approximated) | ports at sweep ends | Antelope Canyon reference (#172); last Euclidean step before anything non-Euclidean |

Non-Euclidean features (portals, impossible adjacency) are **out of scope** until the operator opens them.

How library modules and shapes interact: an admitted video room (figure) is fitted to a cell by `primitive` + footprint. Generated shape rooms (ground) fill the remaining cells **using the style tags of their neighbouring figure rooms**, so the source rooms set the material language and the generator repeats it. This is Karth's beeswax: hand-authored anchors that a generative ground surrounds.

---

## 6. Making ingestion feed the proposal space automatically

Add two CPU-only stages to `source_ingestion_runner.py`, after the existing `catalog_admission_accepted` event:

1. **`derive-module-metadata <sid> --room-id …`**: computes the mechanical fields of `module_poetics` (shape fit, symmetry, sign tagging from adaptation provenance, voids, port slots). Writes a draft and the event `module_metadata_derived`. Refuses to overwrite and binds to the manifest and catalog hashes.
2. **`propose-integrations <sid> --room-id … --map <generative_map.json>`**: runs the fit test of the module against every cell of the given map(s) and against existing modules' tested sockets. Writes zero or more `integration_proposal` records and the event `integration_proposal_recorded`. Model critique is optional and disabled by default, under the existing cost-ceiling policy.

The operator then records `module_metadata_accepted` and `integration_proposal_decided` (choice + reason). Only after `module_metadata_accepted` **and** a tested socket does the derived `layout_eligible` flip in the next catalog snapshot (new version; the base module is never edited).

A validator check (part of #170) fails whenever a room folder holds an admission or decision file without the matching event. That keeps "properly logged" mechanically enforced.

Each per-video issue (#171–#180) therefore ends at the same point: an admitted module with accepted metadata appears in the proposal space, or a logged reject/abstain is recorded.

---

## 7. Phasing (child issues of #169; blocking order #181 → #182 → #183, #181 → #184)

1. **#170**: reconcile event logs; add the decision-file ↔ event validator.
2. **#181 Metadata schemas**: `generative_map.schema.json`, `module_poetics.schema.json`, and extend the proposal schema. Backfill `module_poetics` drafts for all 8 current modules (mechanical fields only).
3. **#182 Map generator v0 (stage 0–1)**: lattice + cells + roles + biased tier distribution + repetition budget, consuming the current catalog snapshot. Output validates against the existing `layout.schema.json` path, so #149/#164 validators still apply.
4. **#183 Shape stage 1 rooms**: rectilinear polyomino generator constrained to cell envelopes, with analytic collision, Godot candidate scene, and validators. Operator reviews one seeded walk.
5. **#184 Runner stages** `derive-module-metadata` / `propose-integrations`, first demonstrated on Bill Viola (it has a pending proposal request, seq 14).
6. Stages 2→5 of §5, one at a time, each its own issue and gate.

---

## 8. Guardrails carried over unchanged

- No inferred video connectivity; `index` evidence never certifies a connector.
- No automatic admission, promotion, or catalog edits. New versions only; the operator decides.
- No free-model calls. Paid calls only with explicit operator authorisation and a hard USD ceiling.
- Hunyuan per-source cap, GPU lock and resource guard unchanged.
- `registration_accepted=false`, `scale_calibrated=false`.
