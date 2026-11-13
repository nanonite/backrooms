# Mutating-Maze Dynamics — Proposal

Status: second revision for operator review (2026-11-12/13). Operator decisions on
the original eight questions are recorded in §10; this revision keeps them and
rewrites the door re-roll around a concrete footprint-preserving bounded-rewire
algorithm with a five-seed feasibility measurement (§4.5.9). The measurement is
sparse: two v1 door directions with pools under the operator's pin list, five if the spawn
cell is allowed as a content-pinned island. Q9-Q13 are the resulting open
questions (target size, content-pinned spawn/exit, reserved void, first-tier edit
character and latch policy) with recommendations. Design issue #209, child of
#169.

This document is design only: no code, schema, generator, map, shape-room or asset change.
It builds on `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` (the agreed map-first
direction) and `docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md` (#212), and on the
completed layer work in #198, #199, #201, #204, #205, #208, #219 and #220.
The runtime-overlay implementation is #223, which is blocked by #209 and starts
only after the operator closes this issue.

Nothing here changes an approval, the catalog, a source event, the committed
maps, `registration_accepted=false`, or `scale_calibrated=false`. The operator
reviews this document before any implementation issue is filed.

---

## 1. The feeling, and what is being designed

The operator's direction (2026-11-08) is that the end goal is a **maze generator**.
The Backrooms look is the starting palette; the feeling is *trying to escape or
find an exit, with the impending sense that the maze is not stable*. Two dread
mechanics were named:

- **A. Door re-roll:** a door locks behind the player; when it is opened again
  the part of the maze behind them is the same rooms with a different passage
  graph, so the route they used is gone but the place is recognisable.
- **B. Follower edits:** something or someone changes rooms the player has
  already passed, so retracing steps is very hard.

**Breadcrumb mode** is later work: a player aid for tracing steps. The operator
decided it is honest in v1, defaults off, and has a pause-menu toggle from the
start (§10).

The operator answered the eight questions in §10 on 2026-11-12. Those answers
are decisions, not options, and the rest of this revision reflects them.

The map-first rule from the metadata proposal still governs:

> Every generated or library room is placed into a cell of a generative map and
> must fit that cell's envelope, ports and role. A room never enlarges, re-routes
> or re-opens the map.

So mutation is not a room-authoring feature. It is a **runtime change to the map
state around the player**, expressed through the layers the map already owns.
The committed map and the operator-approved library are the base; a mutation
never edits either one.

### 1.1 Scope guard

In scope for this proposal: the mutation model, door re-roll, follower edits,
the fairness invariant, the exit and run end card, breadcrumb design, sound/feel,
architecture constraints, and the ordered implementation issues to file after
approval.

Out of scope: implementation, new assets, enemy/combat systems, scoring, new
source ingestion, catalog admission, and any change to the generator's committed
output for existing seeds.

### 1.2 What is measured, and what is a guess

| Item | Status |
|---|---|
| Deterministic map generation and per-layer streams | Measured and tested; see #201, #204, #208, #220 |
| Per-cell keyed reverb and floor-region draws | Measured; `gmap_reverb.py`, `gmap_floor_regions.py` |
| Directed strong connectivity and one-way drops | Measured and tested; #201 report |
| Runtime reverb setter on an instanced room | Implemented; `generative_map_assembly.gd:199-209` |
| Layered footsteps, acoustic probe, footstep reverb bus | Implemented; #203, #205 |
| Per-cell re-draw of light/surface/elevation/palette for one cell | Partly implemented in gmap-0.13.0, but the layer functions still walk the whole document; a local redraw API is new work |
| Footprint-preserving passage rewire | Design in §4.5; feasibility measured on the five committed seeds in §4.5.9 (sparse); implementation unproven |
| Runtime passage-graph enumeration and doorway rebuild | New work; headless slice M5 and runtime M6 |
| Branch re-growth that fits vacated envelopes | Superseded by the footprint-preserving rewire; no growth is needed |
| Door leaf, lock click and follower cue mix | Not implemented; assets and mix are future work |
| Static exit, bright threshold style and end card | Operator decision recorded in §10; not implemented; the visual style needs original assets and operator acceptance |
| Cadence numbers, escalation curve, "unsettling but not random" | Design guess; requires operator walks and listening |
| Visibility predicate cost and conservatism | Design guess; needs a headless test |

The distinction matters: a green test proves replay, isolation and reachability,
not that the maze feels right. Only the operator can approve the feel.

---

## 2. What the maze can already mutate

The generator is at `gmap-0.13.0` (schema v2). Its layers are deliberately
separate and versioned. This audit is the menu the mutation design draws from.

| Layer | Current record | Stream / key | Runtime-mutable today | Mutation use |
|---|---|---|---|---|
| Layout: cells, envelopes, tree, diagonals | map `cells`, `edges` (tree) | `seed + attempt` through `gmap_draft_generation.attempt_rng` | No | Pinned by a re-roll; never a follower edit |
| Passages: which shared walls are open, doorway placement | map `edges`, cell `required_ports`, `doors[]` | Base `seed + attempt`; runtime stream `door-reroll:gmap-0.13.0` | No; rebuilt from the overlay | Door re-roll only; cells and keyed layers are pinned |
| Light: tier, lamps, flicker seeds, dark wing | cell `light`, map `dark_wing` | `light:gmap-0.8.0`; per-cell `light:gmap-0.13.0` | No setter yet | Lamp state, flicker seed, dim tier, dark-wing growth (#198) |
| Surface: wear and variants | cell `wear`, `surface_variants` | `surface:gmap-0.9.0`; per-cell `surface:gmap-0.13.0` | No | Wear step, one-surface variant change (#199) |
| Palette and floor regions | cell `palette`, map `floor_regions` | `palette` and `floor_regions:gmap-0.12.0`; per-cell keys in 0.13.0 | No | Palette swap, floor-material tell (#208) |
| Elevation | cell `floor_y`; edge `vertical`, `ramp`, `drop` | `elevation:gmap-0.10.0`; per-cell keys in 0.13.0 | No | High-cost edit; geometry rebuild (#201) |
| Reverb | cell `reverb`, map `reverb_layer` | `reverb:gmap-0.11.0`, keyed per cell | Yes: `set_room_reverb` | Wet/dry flip (#204) |
| Doors | cell `doors[]`, edge `door_id` | Base policy only, stream `door-reroll:gmap-0.13.0` reserved | No state machine yet | Lock, unlock, re-roll eligibility (#223) |
| Landmark | map `landmark`, cell `landmark` | `landmark:gmap-0.7.0` | No | Excluded from edits; operator-approved figure |
| Mood / volume / absorption | cell `mood`, `volume`, `absorption` | Derived from module metadata (#219) | No | Cue selection and room character, not a mutation target yet |
| Footsteps, probe, reverb bus | `walk_player.gd`, `room_acoustic_probe.gd`, `room_reverb_bus.gd` | Runtime | Yes, by design | Follower cues, reverb tell (#203, #205) |
| Streaming | full map instanced at load; #156 finite streamer | `seed + catalog snapshot` | Not in the current walkthrough | Local door re-roll rebuild/unload; general streaming is #162 |

The row that matters for door re-roll is **Passages**, not **Layout**. A re-roll
keeps every cell, envelope, floor level, role, per-cell keyed layer and module
scene; it changes which shared walls are open and where the doorway sits. This is
why the re-roll can be consistent with the previous generation and why it needs
no new cell IDs. The base `edges` array records the generated passages; the
overlay records the replacement passage set and the new doorway geometry. The
committed `edges` and `doors[]` arrays are never rewritten.

The generated map has **no exit layer today**: #219 leaves the map-level exit
open. The operator's static-exit decision (§10, Q1-Q2) needs one. §6.4 and M3
propose a seed-keyed selection in a new layer version; maps generated before it
can derive the same exit from the seed at load, so no existing map file is
rewritten. Until that lands, fairness tests may use a synthetic exit cell.

The important structural fact is that **the base map already carries the
placeholders** for the runtime overlay. `gmap_template.py:67-93` writes each
door and `gmap_template.py:138-147` writes each cell's mutation block. A door is
`state: "open"`, `lock: {lock_id: null, unlock_condition: null, locked_by: null}`,
`reroll: {eligible: false,
stream: "door-reroll:gmap-0.13.0", draw_index: null, max_rerolls: 0,
last_reroll_id: null}`, and each cell as `mutation: {eligible: false, classes: [],
follower_visibility: "untouched", policy: "none", last_change_id: null}`. The
template proposal (#212 §3.7) reserves these fields and explicitly says the live
state belongs in a runtime overlay, not the map. #223 is the issue that
implements that overlay. A re-roll's new doorways are overlay records keyed by
the cell pair; they do not add entries to the committed `doors[]` array. The base
placeholders cover the generated ports only.

### 2.1 The `attempt` field is a generation stream, not a mutation counter

`generative_map.schema.json:17-20` defines `attempt` as the seed stream used by
the generator: stream 0 is the seed itself, and stream *n* is used after a rule
such as `branch_required` fails. `gmap_draft_generation.attempt_rng(seed,
attempt)` implements it as `Random(seed + attempt * STREAM_STRIDE)`, where
`STREAM_STRIDE = 1 << 32`; every layer's `rng_for(seed, attempt)` repeats the
same pattern. The successful attempt is written into the map document and is
part of the map identity.

This proposal **does not bump `attempt`** for mutations. Doing so would shift
every layer of the whole map and change already-committed results. The mutation
model adds its own subordinate counters (§3.3) and leaves `attempt` as the base
map's generation identity.

The source library's `hunyuan.attempts[]` (per-source Hunyuan attempt cap) is a
different concept and is not used by the maze runtime either.

---

## 3. Mutation model

### 3.1 State = f(base map, ordered event log)

Define the base:

```
B = (map document, base_map_sha256, generator_version, seed, attempt,
     catalog_snapshot_sha256, module metadata pins)
```

Define the runtime state:

```
O_0 = empty overlay
O_n = f(seed, B, E[1..n]) = fold(B, E[1..n])
E   = append-only ordered mutation-event log
```

Equivalently, state is a function of the seed and the ordered mutation-event
log, with the base map as the fixed starting point.

The committed map JSON is never rewritten. The overlay is a separate derived
record; the running assembly applies it to instanced nodes. This is the same
separation as #204's reverb flag: the map keeps the base value, and
`set_room_reverb` changes the live room without touching the file.

Every accepted event also stores the resulting per-cell values (or the passage
set and doorway records for a re-roll). Replay applies those values and verifies the
recorded draw; it does not re-run a global layer pass. That keeps old logs
readable if a layer implementation is improved later.

### 3.2 Event record

The exact schema belongs to #223. The proposal asks for these fields, because
they are what make replay and testing possible:

```jsonc
{
  "schema_version": 1,
  "event_index": 7,                    // 1-based; the only ordering that seeds mutation draws
  "event_id": "mut-gmap-279-gmap-0.13.0-000007",
  "record_kind": "mutation",           // mutation | trigger
  "event_type": "follower_edit",       // follower_edit | door_lock | door_unlock
                                       // | door_reroll | breadcrumb | follower_cue
                                       // | run_end | repair
                                       // exit_move is reserved for a later version;
                                       // v1 never emits it
  "occurred_at_utc": "2026-11-12T00:00:00Z", // bookkeeping only, never a draw input
  "base": {
    "map_id": "gmap-279-gmap-0.13.0",
    "base_map_sha256": "<64 hex>",
    "generator_version": "gmap-0.13.0",
    "seed": 279,
    "attempt": 0
  },
  "trigger": {
    "kind": "player_opened_door",      // room_entered | player_opened_door
                                       // | exit_entered | cell_unloaded
                                       // | save_restore | debug
    "player_cell": "c11",
    "from_cell": "c11"
  },
  "target": {
    "cell_id": "c02",                  // root cell of the departed component
    "port_id": "c11:p0",               // pinned B-side port
    "threshold_id": "c11:p0",          // stable runtime door identity
    "branch_root": "c02"               // first cell of the departed component
  },
  "stream": "door-reroll:gmap-0.13.0",
  "draw": {
    "purpose": "candidate",
    "reroll_serial": 1,
    "branch_attempt": 1                // chosen rank in the shortlist
  },
  "rewire": {
    "algorithm_version": "rewire-1",
    "target_cells": ["c02", "c03", "c07", "c08", "c09", "c10", "c12", "dp00"],
    "passages_before": [
      ["c02", "c03"], ["c02", "dp00"], ["c03", "c07"], ["c03", "c08"],
      ["c07", "c08"], ["c07", "c09"], ["c07", "c12"], ["c08", "c10"],
      ["c10", "dp00"]
    ],
    "passages_after": [
      ["c02", "c03"], ["c02", "dp00"], ["c03", "c07"], ["c03", "c08"],
      ["c07", "c09"], ["c07", "c12"], ["c08", "c10"], ["c10", "dp00"]
    ],
    "pinned_passages": [
      ["c02", "dp00"], ["c07", "c09"], ["c07", "c12"], ["c10", "dp00"]
    ],
    "edit_distance": 1,
    "retained_fraction": 0.889,
    "shape_before": {"leaves": 2, "loops": 2, "max_depth": 3,
                     "mean_depth": 1.75, "door_count": 10},
    "shape_after":  {"leaves": 2, "loops": 1, "max_depth": 3,
                     "mean_depth": 1.75, "door_count": 9},
    "candidate_count": 13,
    "shortlist_size": 3,
    "chosen_rank": 1,
    "consistency_relaxed": false,
    "candidate_set_hash": "<64 hex>",
    "doorways": [
      {"cell_a": "c07", "cell_b": "c08", "action": "closed"}
    ]
  },
  "validation": {
    "outcome": "accepted",             // accepted | rejected
    "checks": ["target_hidden", "same_footprint", "pinned_passages",
               "connected", "strong_connectivity", "exit_reachable",
               "no_visible_change", "edit_bounds", "shape_tolerance"]
  },
  "visibility": {
    "player_cell": "c11",
    "target_hidden": true,
    "visible_cells": ["c11"]
  },
  "prev_state_hash": "<64 hex>",
  "state_hash": "<64 hex>"
}
```

The example shows a re-roll. A follower edit uses the same envelope with a
`change` block (`class`, `layer_version`, `before`, `after`) and no `rewire`
block; a trigger record has neither. The re-roll block is the part that makes a
footprint-preserving rewire replayable: `passages_before` and `passages_after`
are canonical sorted cell pairs, `pinned_passages` is the part of the previous
generation that must not move, and `doorways` records every changed doorway with
its exact position. The event does not carry a candidate-pool hash because there
is no offline pool in this revision (§4.5.8); `candidate_set_hash` is an audit
hash of the enumerated set, not a loaded artifact.

`event_index` is the authoritative order. `occurred_at_utc` is useful for the
operator's review but must never feed a draw, or a replay after a clock change
would produce a different maze. Rejected events are logged with the same index
and a reason; they do not change the overlay, but they do occupy their place in
the history, so a later event's draw differs from a run where the rejected
attempt never happened. Cue and rejected events are logged for telemetry; a cue
never changes state, while a rejected mutation changes nothing except its own
place in the order. A rejected event is evidence that the fairness check ran,
not an error to hide.

The log is JSONL, one record per line, append-only. It has two record kinds:
**trigger** records (`room_entered`, `door_opened`, `door_closed`,
`exit_entered`, `cell_unloaded`, `save_restore`) and **mutation** records (the
event types in the example). A trigger record carries no `change` and does not
alter the overlay; it is the input history that made a later mutation possible.
It uses the same envelope but omits `target`, `stream`, `draw` and `change`; its
`visibility` and `validation` fields are optional. Both kinds consume
`event_index`, so the order is explicit and the cadence counter can be
reconstructed by replaying the trigger sequence. This is what lets save/restore
keep only the log. The overlay
is a function of the mutation subset; the scheduler is a function of the trigger
subset. One ordered file keeps both replayable without a second sidecar.

The log can live in the run save directory or be printed by a headless harness;
it is not committed to the map folder. The source library's `events.jsonl`
(`register_video_sources.append_event`) is the precedent for an append-only,
sequenced record; the mutation log uses the same discipline with `event_index`
instead of `sequence`. A queued but not yet applied edit is runtime state, not a
log record; it enters the log only when it applies or is rejected. #223's
save/restore serialises the base hash plus this log, never a mutated copy of the
map JSON.

### 3.3 Seeded draws

Every event draw is seeded from `(seed, attempt, event_index, stream)`, in the
same idiom as `gmap_keyed.rng_for_cell(seed, attempt, stream, cell_id, draw)`:

```text
draw(seed, attempt, event_index, stream, target, purpose) =
    sha256("<seed>:<attempt>:<event_index>:<stream>:<target>:<purpose>")
```

For a one-cell edit, `target` is the `cell_id` and `purpose` names the field
(for example `lamp-state:1`). For a graph-wide choice, use a stable hash; the
re-roll's shortlist draw is defined in §4.5.6. The result depends only on the
key, not on iteration order or on a language RNG.

This is deliberately the same construction as the existing per-cell layers, so
a mutation can re-draw one cell without touching any other cell's result. It is
also deliberately not a Python `random.Random()` walked across a list, because
that would make the result depend on iteration order and on how many earlier
cells were edited.

The existing `gmap_reverb.keyed_draw` and `gmap_floor_regions.keyed_draw` are
the precedents: both hash `(seed, attempt, stream, cell_id)` and both were
introduced so a later runtime pass could re-draw one room. The mutation stream
adds `event_index` as the extra namespace, because the same cell can be edited
twice in one run.

#### Attempts, serials and retries

| Name | Scope | Purpose | Changed by mutation? |
|---|---|---|---|
| `seed` | map | Base identity | No |
| `attempt` | map | Generation retry stream (`gmap_draft_generation.attempt_rng`) | No |
| `event_index` | mutation log | Distinguishes repeated events on the same target | Increments once per event |
| `reroll_serial` | one door | Counts accepted re-rolls of that door; audit field | Increments on accepted re-roll |
| `branch_attempt` | one re-roll | Chosen rank in the enumerated shortlist | Selects a candidate only |
| `hunyuan.attempts[]` | one source | Hunyuan inference cap | Unrelated |

For a door re-roll, the candidate shortlist is enumerated from the map's own
cells (§4.5) and the choice is made by a stable hash:

```text
rank = int(sha256(
    "<seed>:<attempt>:<event_index>:<stream>:<threshold_id>:<algorithm_version>:choose"
).hexdigest(), 16)
choice = shortlist[rank % len(shortlist)]
```

`stream` is the base map's reserved `door-reroll:gmap-0.13.0` stream. There is no
offline branch generator and no precomputed pool in this revision: the
enumeration is a pure function of the base map, the target and the event tier,
and the only geometry it creates is a doorway cut in an existing wall. The
`branch_attempt` field records the chosen rank for audit; it does not select a
precomputed artifact. `candidate_set_hash` in the event is a hash of the
enumerated hard-valid set, so a later audit can detect drift without making the
pool an authority.

This follows `gmap_draft_generation.site_layout_rng`, which hashes
`seed:attempt:layout_variant:gmap-layout-0.6.1` for a bounded layout search, but
the re-roll does not bump `attempt` and does not run the growth generator. It
selects among passage graphs on the existing footprint.

A deterministic event, such as the automatic lock on crossing, still gets an
`event_index` and a stream even when its outcome is forced. The index preserves
order and lets the log explain every state change; a forced event simply has no
branching draw to record.

### 3.4 Replay and the determinism boundary

The claim is precise:

> Given the same base map and the same ordered event log, the overlay and its
> state hash are identical.

The claim is not that two players walk the same route. Player input, timing and
which room they enter are not deterministic; they decide *which events exist*.
Once an event exists, its target selection, draw and outcome are deterministic.
This is the same boundary the source library uses: the video is fixed, the
inspection events are logged, and the record replays.

A headless replay test can therefore use synthetic logs and assert:

- identical base + log produces the identical overlay and `state_hash`;
- changing `event_index`, moving an event, or changing its target changes the
  result or is rejected;
- a log whose `base_map_sha256` does not match the map is rejected;
- a trigger-only prefix replays to the same state hash and reconstructs the
  same cadence counters as the live controller;
- a rejected event leaves the state hash unchanged;
- replay never writes the base map;
- For a one-cell follower edit, each accepted event's stored `after` values match
  a fresh keyed draw from `(seed, attempt, event_index, stream)` under the
  recorded layer version. This proves the event is actually seeded, not merely
  replayed from copied values.
- For a re-roll, the stored `passages_after` and doorway records match a fresh
  enumeration and seeded shortlist draw under the recorded `algorithm_version`,
  and `candidate_set_hash` matches the enumerated set. If the algorithm version
  is older than the runtime, replay applies the stored `P` and the audit reports
  the drift instead of reinterpreting it.

The first implementation slice (§11, M1) is exactly this harness. It is
verifiable before any door, lamp or follower exists.

### 3.5 What the overlay stores

The overlay is keyed by stable IDs and stores only the live divergence from the
base:

```text
overlay = {
  cell_overrides:    cell_id -> {light?, wear?, surface_variants?, palette?,
                                 reverb?, floor_y?, geometry_revision?},
  door_overrides:    threshold_id -> {state, lock, reroll, follower_visibility},
  passage_overrides: branch_epoch -> {
                       threshold_id, root_cell_id, target_cells,
                       passages_before, passages_after, pinned_passages,
                       doorways, passage_revision, algorithm_version,
                       edit_distance, retained_fraction, candidate_set_hash
                     },
  breadcrumbs:       marker_id -> {cell_id, port_id, sequence, kind, state},
  run:               {ended: bool, exit_cell: cell_id | null,
                      ended_at_event: int | null},
  state_hash:        "<64 hex>"
}
```

`run.ended` is set by the `run_end` event; the end card derives its seed,
rooms-visited, edit and re-roll counters from the log. It does not start a new
level or seed.

`passage_overrides` are folded in **event order**, not by `branch_epoch`; the
epoch is an identity for caches and breadcrumbs, while the log order is the
authority. A later event's `passages_before` must match the folded state or the
event is rejected as tampered. This is what lets two re-rolls in one run stay
consistent with each other.

`passage_revision` and `branch_epoch` matter for streaming: a cell whose doorway
set changed must never be served from a cache as if it still had the old
passages. The base map's cell IDs stay stable because a re-roll does not retire
or create cells; the overlay changes the cell's `passage_revision` and rebuilds
its room node from a derived spec. A retired-cell tombstone is not needed for a
re-roll. If a future mutation ever does retire a cell, it must add its own
tombstone rule rather than borrowing this one.

---

## 4. Door re-roll (A)

### 4.1 In plain language

A door re-roll does **not** change the door. The door keeps its frame, its leaf,
its colour, its material and its position. It is not restyled, copied or swapped
for a different door.

What changes is the part of the maze **behind** the player, and it changes in a
specific way: **the rooms stay and the walls between them move.** The cells the
player came through keep their identity, their size, their floor height, their
lamps, their wear, their palette, their reverb, their props, their module rooms
and the landmark. What changes is which shared walls are open and where the
doorways sit. A corridor the player walked down can become a dead end; a wall
they passed can become an opening; a loop can close or open. The branch is the
same part of the maze rearranged, not an off-the-wall replacement.

That distinction is what makes the effect both fair and legible. The player
recognises the rooms, the light and the way the place looks, but the route they
just used is not there. The door is the fixed point; the passage graph behind it
is the variable. Nothing is teleported, no cell is added or removed, and no
library scene is rebuilt.

A short worked example:

1. The player walks out of a room, through door D, into a corridor. D closes
   behind them.
2. They continue into a side room, then decide to retrace their steps.
3. They open D from the corridor side. The room they came from is still the same
   room, with the same lamps and floor, but the wall that used to lead on is now
   closed and a different wall is open. The route they walked is gone; the place
   is recognisable.
4. The corridor, the door and everything ahead of the player are exactly as they
   were.

The rest of this section defines that change precisely. "Behind" means the
connected component containing the player's previous cell after the door is
removed; it is not "the door" and it is not "the room ahead". The target is
called `A`, and the replacement uses the same cells as `A` with a different set
of open passages.

### 4.2 The shape of the event

The operator's wording is "a door locks behind the player; when it is opened
again it leads to an entirely different maze". The important word is **behind**.
The part that changes is the side the player came from, not the side ahead.

```text
before crossing:      A  ---[ D ]--->  B        player is in A
crossing:             A  ---[ D ]--->  B        player enters B; D closes and latches
later, from B:        A' ---[ D ]--->  B        player opens D; A has become A'
```

- `A` is the **departed component**: the connected component containing the
  player's previous cell after the traversed door `D` is removed. "Unseen" here
  means out of sight at the moment of replacement, not never visited; the rooms
  the player has already walked through are exactly what changes.
- `B` is the current cell. It is pinned.
- `D` is the door port on the `B` side, its frame, its leaf, its threshold
  identity and the shared boundary. They are pinned. The door is not restyled,
  copied or replaced.
- `A'` is **the same cells as `A` with a different passage set `P`**. It is not a
  new branch of rooms and it is not a re-skin. Cell IDs, envelopes, floor
  levels, roles, per-cell keyed layers, module scenes, the landmark and the
  spawn/exit markers stay exactly where they were. Only the set of open level
  passages among those cells and the doorway geometry on the affected shared
  walls change. Vertical passages (ramps and drops) are pinned.

This is stronger and more useful than re-rolling the room *ahead*: the player
turns around to go back and discovers that the route they came from no longer
exists, while the place still looks like the place they remember. It also means
the re-roll happens entirely out of sight, behind a closed leaf, which is what
makes it fair and technically safe. Re-rolling the side ahead would change
geometry the player may be looking at through the open door, so it is not the v1
reading.

The rest of this section calls the target `A` when it is the whole departed
component, and `T` when a later revision allows the target to be a bounded
prefix of a larger `A`. In v1, `T = A` whenever `A` is eligible; the prefix is an
open question in §10, not a silent behaviour.

### 4.3 What is pinned

The re-roll is a change to passages, never to cell content. That gives three
groups of pinned things.

| Pinned item | Why |
|---|---|
| Current cell `B` | The player is standing in it; floor, walls and collision must not move |
| Every cell on the `B` side | The re-roll is scoped to `A`; the rest of the map keeps its route, exit and identity |
| `D`'s port on the `B` side, frame and leaf | `A'` attaches at the exact position, normal and compatibility type; the closed leaf is the occlusion that makes the swap invisible |
| `D`'s vertical contract | A level or ramp door keeps its level/ramp; a drop is not re-roll eligible because it cannot be reopened from the lower side |
| The exit cell and threshold | Fairness, and the operator's Q2 decision; v1 excludes it from `A` (see Q10 for the content-pinned exception) |
| Every cell visible from `B` at commit time | Nothing the player can still see may change in view |
| The player's position and velocity | No teleport, no fall, no collision pop |
| Every cell ID, envelope and role in `A` | The footprint is the identity: a re-roll changes passages, not cells |
| Every per-cell keyed layer in `A` | Light tier, lamps and flicker seeds (#198), wear and surface variants (#199), palette (#208), reverb (#204), `floor_y` and vertical geometry (#201), mood, volume and absorption (#219) |
| Module cells, their scenes and every passage incident to them | Library scenes are hash-pinned; a re-roll must not rebuild or re-door a module |
| Landmark cells and the landmark figure | Operator-approved art; the cell and its content stay |
| Diagonal-threshold cells and their passages | The diagonal passage is fixed geometry; the cell stays and its two openings stay |
| The spawn cell and its marker | Reset identity; the cell, room, floor and marker stay. v1 keeps the operator's pin: a target containing the spawn cell is not eligible. Q10 asks whether to allow it as a content-pinned island; the cell and marker would still stay, and only its passages would change |
| Breadcrumb markers | The cells stay, so the markers stay; the route between them may change, which is honest evidence of the re-roll |
| The base map bytes, seed, attempt and catalog snapshot | The committed map is never rewritten |

The only things a re-roll may change are:

- which **level passages** between generated cells in `A` are open;
- the **doorway records and wall geometry** on those shared walls;
- the overlay's `branch_epoch`, `passage_revision` and re-roll audit fields.

A cell with a module, landmark or diagonal is a **content-pinned island** inside
`A`: the cell stays, its scene or geometry stays, and every base passage
incident to it is pinned. The spawn and exit cells are content-pinned in the same
sense for the cell, room, floor and marker, but Q10 decides whether their
incident passages are pinned or variable. The rest of the branch rewires around
the island. This is a deliberate refinement of the earlier proposal, which
excluded those cells entirely because the old design retired the branch.
Footprint-preserving rewire does not retire cells, so the old exclusion is no
longer necessary. It is the main reason the measured feasibility in §4.5.9 is
better than the strict reading.

"Pinned" is precise per kind of island:

- **Library module:** the scene, its light/wear/palette and its doorway are
  baked into a hash-pinned file. The scene and every incident passage are
  pinned; the module cannot be re-doored without editing the scene.
- **Landmark and diagonal threshold:** the content and the diagonal geometry are
  pinned; their incident passages are pinned for conservatism, so the figure or
  the diagonal link cannot be orphaned.
- **Spawn and exit (v1 pin; Q10 asks to relax it):** v1 follows the operator's
  pinned list: a target containing the spawn or exit cell is not eligible. Q10
  asks whether to allow either as a content-pinned island. If approved, the
  cell, room, floor, marker or threshold stays exactly as it is; only the
  passages incident to it may change, and F1/F2 keep the exit reachable. If not,
  the cell and its passages are both excluded. The measured difference is
  substantial: the v1 pin list gives two door directions with pools, the Q10
  spawn relaxation gives five (§4.5.9).

The runtime threshold identity is `threshold_id`, the pinned `B`-side port, not
the base edge's `door_id` when that ID happens to point into the departed branch.
A base `door_id` is an alias for a base passage; after a re-roll, the passage
identity is the sorted cell pair, and the overlay stores the new doorway. Do not
use a base `door_id` that points into `A` as a lookup key after `A` has been
rewired.

### 4.4 Eligibility

A door is re-roll eligible only when all of these hold. The evaluation happens
once when the door is about to latch behind the player, and is revalidated when
the player opens it. A door that is not eligible does not auto-latch; it behaves
like any other door. That keeps the latch itself meaningful: a door that closes
behind the player is a door that has a re-roll ready.

1. **It has a closable leaf.** Today a generated doorway is an opening:
   `shape_room_spec.doorway_records` writes `kind: "open"` for a direct edge and
   `closed_visible` otherwise; `shape_room_builder._add_doorway` builds the
   opening or a wall, not a swinging door. A library module's doorway is equally
   an authored opening. A door with no leaf cannot hide the swap, so it is not
   eligible until a leaf exists (§9.5). A ramp door is eligible if a leaf can be
   placed at its port without rebuilding the ramp; a drop door is not eligible.
2. **It is a bridge in the walkable graph.** Remove `D`; `A` must be a separate
   component from `B`. If a loop, diagonal link or elevation loop connects `A`
   to `B` by another route, cutting only `D` would not isolate `A`; the door is
   not eligible.
3. **The target is the right size.** In v1 the target is the whole departed
   component `A`, and `MIN_REROLL_CELLS = 3` to `MAX_REROLL_CELLS = 8` walkable
   cells (operator Q7). A one-cell closet is a room swap, not "an entirely
   different maze"; a whole-map rewrite is too large for the first runtime
   slice. A target with fewer than two valid candidates is not eligible either
   (condition 8). If Q9 option (b) is approved, a larger `A` may use a connected 3-8 cell
   prefix as `T`; until then, a larger `A` is not eligible.
4. **Pinned content is respected.** The exit and spawn cells are excluded from
   the target in v1 (the operator's pinned list). Q10 asks whether to allow
   either as a content-pinned island; if approved, the cell, room, floor, marker
   or threshold stays exactly as it is and only its incident passages may change.
   A module, landmark or diagonal cell may be inside the target only when every
   base passage incident to it is pinned, so its scene and doorways stay exactly
   as they were. If a module, landmark or diagonal cell cannot keep all of its
   base passages and remain reachable, the door is not eligible.
5. **It contains no visible cell.** With the leaf closed, `A` must be disjoint
   from `visible_cells(B)` at commit time. The closed leaf is expected to make
   this true; the check is the backstop. A conservative false negative is
   acceptable; a visible pop is not.
6. **The vertical contract is pinned.** `D` may be level or a ramp, and its
   vertical geometry stays. Every ramp or drop inside `A` is pinned; the re-roll
   only changes level passages between cells on the same floor. A drop inside
   `A` stays, and the candidate must keep its return route; that is covered by
   the directed strong-connectivity check. A drop `D` is not eligible.
7. **It has re-roll budget.** `doors[].reroll.max_rerolls` (base policy) and a
   run-level cap both allow another re-roll. The operator-confirmed caps are
   `max_rerolls = 1` per door and `MAX_REROLLS_PER_RUN = 3`. The per-door cap is
   one accepted re-roll; a rejected attempt does not spend it, but a door that
   fails with `no_candidate` at latch time is marked ineligible for the run so
   the player is not asked to retry a door that cannot change. The caps are
   pacing guesses, not measured.
8. **It has re-roll potential.** After the hard filters in §4.5.4, at least
   `MIN_REROLL_ALTERNATIVES = 2` candidates must exist; `POOL_TARGET = 3` is the
   comfortable target. A door with zero or one candidate fails closed and opens
   normally. This is the condition the feasibility measurement in §4.5.9 is
   about: a shortlist that is empty is a door that cannot deliver the
   mechanic, and pretending otherwise would create a locked door with nowhere
   to go.
9. **The exit is still reachable from `B`.** In v1 the exit is outside `A`, so
   this follows from condition 4. If Q10 allows the exit inside `A`, the
   candidate must keep it reachable from `B` through the new passage graph. The
   validator checks F1/F2 either way, and that check becomes authoritative if a
   later version ever moves the exit.
10. **Geometry is valid.** Every new doorway fits its shared wall with the
    configured width and margins, does not overlap an existing opening or a
    corner, does not cut a pinned wall or a module scene, and does not open into
    a void or a cell at a different floor level. The room spec rebuild must not
    change the cell's envelope, floor, ceiling or materials.
11. **The algorithm version is supported.** The event records
    `algorithm_version` (v1: `rewire-1`); a runtime that does not know the
    version refuses to re-roll rather than guessing.

If the door is structurally a candidate but fails one of the runtime conditions,
the attempt is logged as `door_reroll` / `rejected` with a stable code, the door
opens to the old `A`, and the door is marked blocked for the run. A failed
re-roll is never a locked door with nowhere to go. The rejection codes are:

| Code | Meaning |
|---|---|
| `no_leaf` | No closable leaf at `D` |
| `not_bridge` | Another route connects `A` to `B` |
| `drop_door` | `D` is a one-way drop |
| `target_too_small` | `A` has fewer than 3 cells |
| `target_too_large` | `A` has more than 8 cells and Q9 option (b) is not enabled |
| `exit_inside` | The exit cell is in the target |
| `spawn_inside` | The spawn cell is in the target and the Q10 spawn relaxation is not enabled |
| `visible_target` | A target cell is visible from `B` |
| `pinned_cell_conflict` | A content-pinned cell cannot keep its passages |
| `no_candidate` | The enumeration produced no hard-valid candidate |
| `below_min_alternatives` | Fewer than `MIN_REROLL_ALTERNATIVES` candidates |
| `no_candidate_in_tier` | No candidate fits the current escalation tier |
| `geometry_conflict` | A doorway cannot be placed without overlap or a pinned wall |
| `unsupported_algorithm` | The runtime does not know the recorded algorithm version |
| `candidate_failed_runtime` | The chosen candidate failed the open-time revalidation |

Conditions 1-3 and the structural part of 4 are checked when the door is about to
latch. Conditions 5-11 and the runtime half of 4 are checked again at open time.
The candidate shortlist is cached between the two checks; if a target cell's
`content_revision` changed (a follower edit, a later elevation edit, or a
save/restore), the pool is rebuilt before the draw.

### 4.5 The re-roll algorithm: footprint-preserving bounded rewire

This section is the concrete algorithm. It follows the operator's recommended
starting design, with four deliberate refinements justified below:

1. **Content-pinned islands replace blanket exclusion.** A module, landmark or
   diagonal cell can stay in `A` if every passage incident to it is pinned; the
   spawn and exit cells stay excluded in v1, with Q10 asking whether to allow
   them as content-pinned islands. The old exclusion existed because the old
   design retired the branch; footprint-preserving rewire keeps the cells, so a
   module/landmark/diagonal island can stay and the rest of the branch can rewire
   around it without changing its content. This is the largest feasibility gain
   that does not relax the operator's pinned list; the spawn/exit relaxation is
   Q10 and is measured separately.
2. **Runtime enumeration replaces the offline precomputed pool.** The geometry
   is the map's existing cells; no growth is needed. The candidate universe is
   at most a few thousand subsets, and the only new geometry is a doorway cut in
   an existing wall, which the shape builder can derive. A sidecar pool, a pool
   hash and a Python step in the runtime are no longer needed. The event stores
   the chosen passage set, so replay does not depend on the enumerator version.
3. **The first tier's minimum edit is one passage, not two.** A single passage
   change is real, provided the shortlist enforces the shape tolerance. The
   measured seed 279 pool makes this concrete: the consistent candidates remove
   one of two loops (edit 1, 8 of 9 passages retained); requiring two edits
   deletes both loops and changes the branch's character, which is exactly what
   the consistency rule is meant to prevent. The shape tolerance, not a larger
   edit floor, is the guard.
4. **The seeded draw is from a shortlist of the most consistent candidates, not
   the whole hard-valid set.** The shortlist is the consistency filter; the draw
   supplies variety within it. The event records both the full hard-valid count
   and the shortlist size, so a thin pool is visible in the log.

#### Parameters and constants (tuning)

All values are tuning unless marked as measured or an operator decision. The
table is the single place to change them; the rest of the algorithm refers to
the names.

| Parameter | Value | Status | Role |
|---|---:|---|---|
| `MIN_REROLL_CELLS` | 3 | Operator Q7 | Smallest target; smaller is a room swap |
| `MAX_REROLL_CELLS` | 8 | Operator Q7 | Largest target; larger is a whole-map rewrite |
| `MAX_REROLLS_PER_RUN` | 3 | Operator Q7 | Run-wide accepted re-rolls |
| `max_rerolls` per door | 1 | Operator Q7 | One accepted re-roll per threshold |
| `MAX_DEGREE` | 4 | Tuning | Physical maximum openings per cell; `D` counts at `R` |
| `MIN_SHARED_WALL_M` | 1.8 m | Tuning / geometry | 1.4 m doorway plus 0.2 m margins |
| `DOOR_WIDTH_M` | 1.4 m | Tuning / geometry | Doorway clear width |
| `DOOR_HEIGHT_M` | 2.2 m | Tuning / geometry | Doorway clear height |
| `DOORWAY_MARGIN_M` | 0.2 m | Tuning / geometry | Corner and existing-opening clearance |
| `MIN_RETAINED` | 0.5 | Tuning | Hard floor on the fraction of `E_T` kept |
| `MIN_EDIT` | 1 / 2 / 3 | Tuning | Tier 1 / 2 / 3 minimum passage changes |
| `MAX_EDIT` | 2 / 4 / 6 | Tuning | Tier 1 / 2 / 3 maximum passage changes |
| `CANDIDATE_SHORTLIST` | 8 | Tuning | Maximum candidates the draw ranges over |
| `MIN_REROLL_ALTERNATIVES` | 2 | Tuning, measured | A door with fewer fails closed; 2 v1 doors meet it |
| `POOL_TARGET` | 3 | Tuning, measured | Comfortable first-tier pool; only seed 279 A8 meets it |
| Shape tolerances | see §4.5.5 | Tuning | Dead ends, loops, depth, degree mix, door count |

The only empirical inputs are the five-seed counts in §4.5.9. Parameters marked
"tuning, measured" are chosen against those counts, not measured themselves; they
still need an operator walk before they are treated as settled.

#### 4.5.1 Vocabulary and the model

Let:

- `A` be the departed component, or `T` the target when Q9 option (b) allows a prefix. In
  v1, `T = A`.
- `R` be the **root** cell of `T`: the cell adjacent to `D` on the departed side.
  The player was in `R` immediately before crossing.
- `E_T` be the **current passage set** of `T` before this event: every
  traversable passage between two cells of `T`, including level, ramp and drop
  passages. For the first re-roll in a region this is the base map's `edges`;
  after an earlier re-roll it is that event's `passages_after`.
- `H_T` be the **candidate passage universe**: every unordered pair of cells in
  `T` that is either a current passage or a shared axis-aligned wall with enough
  length and the same `floor_y`. `H_T` is geometric: it does not shrink when an
  earlier re-roll closed a passage. A wall that used to be a doorway can be
  reopened.
- `M_T` be the **mandatory passage set**: `D`, every vertical passage in `E_T`,
  every base passage incident to a module, landmark or diagonal cell, and (in
  prefix mode) every passage between `T` and `A \ T`. The spawn and exit cells
  are excluded from `T` in v1; if Q10 allows them, their incident passages are
  variable under the content-pinned reading and mandatory under the strict
  reading.
- `P` be a **candidate passage set**: `M_T ⊆ P ⊆ H_T ∪ M_T`.
- A **passage** is identified by the sorted pair `(cell_a, cell_b)`, not by a
  base `door_id`. A new passage gets an overlay ID
  `rewire:<branch_epoch>:<cell_a>:<cell_b>`. The base `door_id` stays as an
  alias only for the passages that were in `E_T`.
- `edit_distance(P) = |P Δ E_T|` (passages added plus passages removed).
- `retained(P) = |P ∩ E_T| / |E_T|` (if `E_T` is empty, there is no candidate).
- The **shape** of a passage graph is the tuple
  `(leaves, loops, degree_histogram, max_depth, mean_depth, door_count)`,
  where `loops = |P| - (|T| - 1)`, depths are shortest-path distances from `R`,
  `degree_histogram` counts cells by passage degree (the door `D` counts as one
  degree at `R`), and `door_count = |P| + 1` includes `D`. The "corridor/room
  mix" is the degree histogram: degree 1 is a dead end, degree 2 a corridor,
  degree 3 or more a junction. The cells' `role` values are unchanged; the mix
  is about how the passages connect them.

`T` is fixed for the whole operation. The algorithm never adds, removes, moves
or renames a cell. It only chooses `P`.

`E_T` is the **previous generation**, not necessarily the original map. If an
earlier re-roll already changed a passage in the same region, this event is
consistent with that result. The overlay folds `passage_overrides` in event
order; each re-roll's `passages_before` must match the folded current state, or
the event is rejected as tampered. The base map's `edges` remain the starting
point and are never rewritten. This is what "keep generations consistent with
each other" means mechanically: every re-roll compares against the layout the
player last saw, not against a fresh map.

#### 4.5.2 Step 0: freeze the target

Before the leaf closes, or immediately after it closes while `A` is still
hidden:

1. Confirm `3 <= |T| <= 8`; if not, fail with `target_too_small` or
   `target_too_large` and do not auto-latch.
2. Record `E_T`, the cell list, the room spec references, the old passage-to-node
   map, the current `passage_revision` of every cell in `T`, and the pinned set
   `M_T`.
3. Do not despawn the old rooms. The old passage graph and nodes are the
   snapshot that is kept until the new branch has passed validation.
4. Confirm the leaf can close and that, with the leaf closed, `A` is outside
   `visible_cells(B)`. The check is run against the closed-leaf state, not the
   current open doorway; the leaf is the occluder. If the helper cannot prove
   `A` is hidden with the leaf closed, the door does not latch and is not
   eligible.

The snapshot is runtime state, not a second map file. It is the old `P` plus the
old node references; because the cells do not change, no cell data needs to be
copied.

#### 4.5.3 Step 1: build the passage universe `H_T`

For every unordered pair `(u, v)` of cells in `T`:

- If a current passage exists between them (a base `direct` edge or a passage
  added by an earlier overlay event), include the pair. Its vertical kind is
  level, ramp or drop.
- Otherwise, include the pair if all of the following hold:
  - `u` and `v` share an axis-aligned wall segment of at least
    `MIN_SHARED_WALL_M = 1.8` m (a 1.4 m doorway plus 0.2 m margins);
  - `floor_y(u) == floor_y(v)`;
  - the wall is not pinned: it is not between `T` and a non-`T` cell, not a
    library-module scene wall, not a void boundary, not a wall whose opening
    would cut a content-pinned cell's only access, and not an outer envelope
    wall;
  - the wall is not already occupied by a fixed diagonal passage or a fixed
    prop that the room spec marks as immovable.
- A `closed_visible` edge between two walkable cells is a wall with a visible
  doorway shape; it is a potential passage if the wall passes the checks above.
  It is not traversable in `E_T`, so opening it is a real change. If the edge
  already has a doorway frame, the frame's center is reused and no new doorway
  draw is made; this avoids overlapping the existing shape.

`H_T` is small: at most 12 for a compact 3x3-minus-one footprint, and observed at
most 9 for the 3-8 cell branches in the five committed seeds. The implementation
asserts `|H_T| <= 16`; a larger universe means the target or the wall filter is
wrong, not that the enumerator needs to be cleverer.

`M_T` is built at the same time:

- `D` is always mandatory and is not part of `H_T` (it is the external edge).
- Every ramp or drop in `E_T` is mandatory.
- Every base passage incident to a module, landmark or diagonal cell is
  mandatory.
- The exit and spawn cells are excluded from `T` in v1. If Q10 later allows
  them, their incident passages follow the approved reading (variable under the
  content-pinned reading, mandatory under the strict reading).
- In prefix mode, every base passage between `T` and `A \ T` is mandatory.

The mandatory set is the part of the previous generation that must survive
exactly. Everything else is a candidate for change.

#### 4.5.4 Step 2: enumerate every passage graph

Enumerate every subset `X` of `H_T` and let `P = M_T ∪ X`; `D` is the external
edge and is always present. The bound is `2^(|H_T| - |M_T ∩ H_T|)`; for a 3-8
cell target this is at most a few thousand and in the committed maps it is at
most `2^9 = 512`. This is a complete enumeration, not a sample. There is no retry
loop and no random growth.

For each subset, apply the **hard invariants** in order. A candidate that fails
any invariant is dropped; the reason is recorded for diagnostics but the
candidate is not considered further.

| ID | Hard invariant | Check |
|---|---|---|
| R0 | **Same footprint.** `P` uses only cells of `T`; no cell is added, removed, moved or renamed. | Set equality of target cells |
| R1 | **Connected.** Every cell of `T` is reachable from `R` through `P`. | BFS/DFS on the undirected passage graph |
| R2 | **Strongly connected.** Every cell of `T` reaches every other through the directed graph: level and ramp passages both ways, drops upper-to-lower only. | `strongly_connected(cells(T), directed(P))` |
| R3 | **Degree limit.** `deg_P(c) + (1 if c == R else 0) <= MAX_DEGREE = 4`. The door counts at the root. | Degree count |
| R4 | **Pins.** `M_T ⊆ P`; no passage through a pinned wall; every module, landmark or diagonal cell keeps its exact incident passage set. The spawn/exit cells follow the Q10 reading. | Set check |
| R5 | **Retained fraction.** `retained(P) >= MIN_RETAINED = 0.5`. | Set arithmetic |
| R6 | **Edit bounds.** `MIN_EDIT[tier] <= edit_distance(P) <= MAX_EDIT[tier]`. | Set arithmetic |
| R7 | **No content change.** No module scene, landmark, exit threshold, spawn marker, floor level, lamp, wear, palette or reverb value changes. | Layer hashes unchanged |
| R8 | **Geometry.** Every new doorway fits its wall; no overlap with an existing opening or corner; no void, no different floor, no pinned wall, no module scene cut. | Doorway geometry check |
| R9 | **Visibility.** With the leaf closed, `T` is disjoint from `visible_cells(B)` at commit. | Visibility helper |
| R10 | **Exit reachable.** In v1 the exit is outside `T` and reachable from `B`; if Q10 allows it inside `T`, the candidate must keep it reachable from `R` and the global F1/F2 check must pass. | Graph helper |
| R11 | **Change is real.** `P != E_T`; implied by R6 because `MIN_EDIT[tier] >= 1`. | Set arithmetic |

The hard invariants are the F0-F5 fairness set and the F7-F9 re-roll contract
from §6, plus the footprint and pin rules that are specific to a rewire. R2 is
the local form of F0: if `T` is strongly connected and attached at `D` (and its
prefix boundary is pinned), the whole graph stays strongly connected when the
rest of the map was already strongly connected. §6.3 states the local theorem;
the global check still runs as a backstop.

If the enumeration yields no candidate, fail with `no_candidate` and do not
latch. If it yields exactly one, fail with `below_min_alternatives`; a pool of
one is a change with no choice, and the measured coverage in §4.5.9 is thin
enough without pretending otherwise.

#### 4.5.5 Step 3: rank for consistency

The hard-valid candidates are the survivors. They are ranked so that the seeded
draw chooses among changes that keep the character of the branch, not among
arbitrary rewires.

For every candidate, compute the shape metrics against `E_T`:

| Metric | Symbol | Tolerance (tier 1) | Tolerance (tier 2) | Tolerance (tier 3) |
|---|---|---|---|---|
| Dead ends | `leaves` | ±1 | ±1 | ±2 |
| Loops | `loops` | ±1 | ±1 | ±2 |
| Maximum depth from `R` | `max_depth` | ±1 | ±2 | ±3 |
| Mean depth from `R` | `mean_depth` | ±0.75 | ±1.0 | ±1.5 |
| Degree histogram | `degree_hist` | L1 ≤ 2 | L1 ≤ 3 | L1 ≤ 4 |
| Door count | `door_count` | ±2 | ±3 | ±4 |
| Retained fraction | `retained` | Hard floor 0.5; score term only | Hard floor 0.5; score term only | Hard floor 0.5; score term only |

All tolerances are tuning, not measured. `shape_violations(P)` is the number of
metrics outside the tier's tolerance. The shape score is a weighted sum used as
a tie-breaker:

```text
shape_score(P) =
    2 * |leaves(P) - leaves(E_T)|
  + 3 * |loops(P) - loops(E_T)|
  + 1 * |max_depth(P) - max_depth(E_T)|
  + 2 * |mean_depth(P) - mean_depth(E_T)|
  + 2 * L1(degree_hist(P), degree_hist(E_T))
  + 1 * |door_count(P) - door_count(E_T)|
  + 2 * (1 - retained(P))
```

The weights say loops and the overall degree mix matter most, then dead ends and
mean depth, then the maximum depth and door count. They are a design judgement,
not a measurement.

Sort the survivors by:

```text
(shape_violations, edit_distance, shape_score, keyed_rank(P))
```

The first key is the consistency gate: every in-tolerance candidate comes before
every out-of-tolerance one. The second key prefers the smallest real change
within the tolerance band. The third breaks ties by shape, and the fourth is a
stable hash so equal candidates do not depend on iteration order.

The **shortlist** is built from the sorted list:

- Let `IN_TOLERANCE` be the candidates with `shape_violations == 0`.
- If `|IN_TOLERANCE| >= MIN_REROLL_ALTERNATIVES`, the shortlist is the first
  `CANDIDATE_SHORTLIST = 8` of `IN_TOLERANCE`.
- Otherwise, the shortlist is the first
  `max(MIN_REROLL_ALTERNATIVES, min(CANDIDATE_SHORTLIST, |hard|))` candidates by
  the sort, and the event records `consistency_relaxed = true`. This is a
  bounded, explicit relaxation, not a retry loop: it is used only when the
  shape tolerance is too strict for the map, and the log says so.
- If `|hard| < MIN_REROLL_ALTERNATIVES`, the door fails with
  `below_min_alternatives`.

The shortlist is the ranked list per door that replaces the old precomputed
candidate pool. It is produced at latch time, cached in memory, and discarded
after the commit or the run.

#### 4.5.6 Step 4: seeded draw and escalation

Let `reroll_index` be one plus the number of accepted re-rolls in the run. The
operator caps it at `MAX_REROLLS_PER_RUN = 3` and at `max_rerolls = 1` per door.
The tier table is:

| `reroll_index` | `MIN_EDIT` | `MAX_EDIT` | Shortlist rule | Intent |
|---|---|---|---|---|
| 1 | 1 | 2 | tier-1 tolerance; in-tolerance first | One or two passages; the place is recognisably the same |
| 2 | 2 | 4 | tier-2 tolerance; in-tolerance first | A clear change; the route is visibly different |
| 3 | 3 | 6 | tier-3 tolerance; best effort | A large change; the branch is rearranged |

All values are tuning. If a door has no candidate in the current tier, it fails
with `no_candidate_in_tier`; the algorithm does not lower the minimum edit to
force a change. A later re-roll at another door can use a larger tier. This
keeps the first re-roll small and the escalation honest.

The draw is a stable hash, not a language `random` walk:

```text
rank = int(sha256(
    "<seed>:<attempt>:<event_index>:<stream>:<threshold_id>:<algorithm_version>:choose"
).hexdigest(), 16)
choice = shortlist[rank % len(shortlist)]
```

`stream` is the base map's reserved `door-reroll:gmap-0.13.0` stream; the
algorithm version is in the key so a future `rewire-2` does not silently
reinterpret an old log. The chosen candidate's `chosen_rank` and
`branch_attempt` are stored in the event. The full hard-valid set is hashed into
`candidate_set_hash` for audit, but the draw only ranges over the shortlist.

The draw is uniform over the shortlist. If the shortlist is `[C1, C2]`, an
`event_index` whose hash is even picks `C1` and one whose hash is odd picks
`C2`; both are in tolerance, so either is a valid expression of the same
consistency rule. The operator can replay the log to see which was chosen.

#### 4.5.7 Step 5: rebuild and commit

For each cell in `T` whose doorway set changed:

1. Copy the base room spec and reapply the overlay's current per-cell overrides
   (light, wear, surface variants, palette, reverb) for every changed cell. The
   copy keeps the envelope, shape, floor, ceiling, materials, props, lamps and
   every per-cell keyed value. It is not a regeneration, and a follower edit that
   happened after generation is not lost.
2. Replace the `doorway_records` for the changed shared walls:
   - keep the current doorway for every passage in `P ∩ E_T`;
   - remove the doorway for every passage in `E_T \ P`;
   - add an overlay doorway for every passage in `P \ E_T`.
3. Place each new doorway with a keyed draw:
   ```text
   doorway_center = clamp(
       keyed_uniform(seed, attempt, event_index,
                     "doorway:rewire-1", threshold_id, cell_a, cell_b),
       wall_start + margin + width/2,
       wall_end - margin - width/2)
   ```
   The doorway is `DOOR_WIDTH_M = 1.4` m wide, `DOOR_HEIGHT_M = 2.2` m high,
   with `DOORWAY_MARGIN_M = 0.2` m to corners and existing openings. The exact
   center, width and height are stored in the event, so replay does not depend
   on a later change to the placement function. `keyed_uniform` is the §3.3
   SHA-256 construction mapped to `[0, 1)`; it is not a language RNG.
4. Increment the cell's `passage_revision` and set the branch's
   `branch_epoch`. The base cell's keyed layers are not re-drawn.
5. Rebuild only the changed room nodes. Cells whose doorway set did not change
   keep their nodes; the B-side nodes are never touched.
6. Validate the assembled `A'` against R0-R11 again, with the real room specs and
   the real doorway geometry. This is the check that a candidate which passes
   the abstract graph can still fail because a wall is too short or a module
   scene is in the way.
7. Commit atomically:
   - swap the changed nodes while the leaf is closed;
   - update the overlay's `passage_overrides`;
   - append the `door_reroll` event with `P`, the doorway records and the
     validation results;
   - increment `reroll_serial`;
   - open the leaf.

If the validation fails, keep the old nodes, open the leaf to the old `A`, append
a rejected event with `candidate_failed_runtime` or `geometry_conflict`, and mark
the door blocked for the run. The old branch is never lost: it was never
despawned before the new one validated.

The base map is never written. No cell ID is retired. No breadcrumb is deleted:
the markers are in the same cells, even if the route between them now crosses a
wall. That is honest evidence of the change, not a lie.

#### 4.5.8 Step 6: replay, storage and the end of the precomputed pool

The event record for a re-roll carries:

| Field | Meaning |
|---|---|
| `algorithm_version` | `rewire-1` |
| `target_cells` | `T` (the same cells as `A` in v1) |
| `root_cell_id` | `R` |
| `threshold_id` | The pinned `B`-side door identity |
| `passages_before` | `E_T`, canonical sorted cell pairs |
| `passages_after` | `P`, canonical sorted cell pairs |
| `pinned_passages` | `M_T` |
| `doorways` | `{cell_a, cell_b, center_xz, width_m, height_m}` for every changed doorway |
| `edit_distance` | `\|P Δ E_T\|` |
| `retained_fraction` | `\|P ∩ E_T\| / \|E_T\|` |
| `shape_before`, `shape_after` | The shape tuples |
| `shape_score` | The ranking score |
| `candidate_count` | Number of hard-valid candidates |
| `shortlist_size` | Number of candidates the draw ranged over |
| `chosen_rank` | 1-based index in the shortlist |
| `consistency_relaxed` | True when the tolerance had to be relaxed |
| `candidate_set_hash` | SHA-256 of the canonical hard-valid set |

Replay applies `passages_after` and `doorways` directly. It does **not**
re-enumerate; the event is the authority. Cell overrides are orthogonal: a
follower lamp/wear/palette/reverb edit in a target cell stays through the
re-roll. Replay applies `cell_overrides` and `passage_overrides` independently;
they touch different fields, so their order does not matter. A future edit that
changes a cell's `floor_y` or a module scene is not orthogonal and must be
rejected or handled by its own mutation class, not by a re-roll. An audit mode may re-enumerate under
the same `algorithm_version` and compare `candidate_set_hash`; if it differs, the
audit reports a warning but does not change the state. A future `rewire-2` can
re-enumerate under its own rules, but an old event still applies its stored `P`.
This is the same separation as §3.4: the log records the result, and the seed
only proves the result was not arbitrary.

This removes the precomputed candidate pool from the design:

- No `candidate_pool_sha256` is part of the base identity.
- No sidecar pool is generated at map build time.
- No Python growth/layer step runs at runtime.
- The ranked list is produced from the map's own cells, the same base hash and
  the same event stream; it is a cache, not a committed artifact.
- If profiling later shows the enumerator is too slow at open time, the ranked
  list can be precomputed at map load for every eligible door. That is an
  optimization of the same pure function, not an authority; the event still
  stores `P`, and replay still works without the cache.

The candidate selection draw and the doorway placement are the only new draws.
Both are keyed by the event; the chosen passage set and doorway records are
stored, so replay is reproducible and auditable without re-enumerating.

#### 4.5.9 Feasibility on the five committed seeds (measured)

The operator asked for a measurement, not an assurance. The analysis below was
run as a throwaway script outside the repository; it is described here so it can
be reproduced, and it is not committed. It reads the five committed
`gmap-{1,2,3,32,279}-gmap-0.13.0.json` maps, builds the walkable graph from
`direct` non-drop edges, removes each traversable door in turn, and takes the
far component as `A`. It then builds `H_T` with a minimum shared wall of 1.8 m
and equal `floor_y`, pins every vertical passage and every passage incident to a
module, landmark or diagonal cell, and enumerates every connected passage set
with degree at most 4 (the door counts at the root), retained fraction at least
0.5, and at least one passage change. The in-tolerance count uses the tier-1
shape table in §4.5.5. It counts two pools:

- **hard-valid**: passes the hard invariants R0-R11 as far as the analysis can
  check them (no room specs and no visibility; those can only reduce the count);
- **in-tolerance**: also passes the tier-1 shape tolerances above. This is the
  shortlist the first re-roll would actually draw from.

The enumeration does not pin the spawn cell; the table's spawn column lets the
v1 pin list and the Q10 spawn relaxation be read from the same data. The exit is not
in the committed maps yet, so the exit exclusion is applied by the later
selection order (§6.4), not by this analysis.

The counts are per **direction**: a bridge door has two possible departed sides,
and the player can arrive from either. The five maps contain 74 undirected
level/ramp traversable door pairs. Eleven directions have a departed component of
3-8 cells. The table lists all eleven. A door that appears twice is the same
physical threshold; its `max_rerolls = 1` cap is shared between the two
directions. Under the v1 pin list, a `yes` in the spawn column makes the
direction ineligible; the two `no` rows with a pool are the v1 doors. The other
pooled rows are measured Q10 spawn options.

| Seed | Door (cell pair) | `\|A\|` | Spawn in `A`? | Hard-valid | In-tolerance | Edit range | Read |
|---|---:|---:|---:|---:|---:|---|---|
| 1 | `c03`-`c05` | 5 | no | 0 | 0 | — | Tree footprint; no spare shared wall |
| 2 | `c03`-`c07` | 4 | no | 0 | 0 | — | Ramp door; tree footprint; no spare wall |
| 279 | `c02`-`c11` | 8 | no | 13 | 3 | 1-2 | The only v1 eligible rich pool |
| 279 | `c02`-`c11` (other side) | 6 | yes | 3 | 2 | 1-2 | Q10 spawn only |
| 279 | `c04`-`c06` | 4 | yes | 0 | 0 | — | Q10 spawn only; tree footprint |
| 279 | `c06`-`c11` | 5 | yes | 3 | 2 | 1-2 | Q10 spawn only; ramp door |
| 32 | `c00`-`c01` | 8 | yes | 4 | 2 | 1-2 | Q10 spawn only; module c13 |
| 32 | `c00`-`c01` (other side) | 6 | no | 3 | 2 | 1-2 | The clean v1 worked example in §4.5.10 |
| 32 | `c00`-`c03` | 5 | no | 0 | 0 | — | Tree footprint |
| 32 | `c01`-`c05` | 4 | no | 0 | 0 | — | Tree footprint |
| 32 | `c03`-`c08` | 3 | no | 0 | 0 | — | Ramp door; tree footprint |
| 3 | none | — | — | — | — | — | No 3-8 cell bridge in either direction |

The headline is:

- **Under the strict reading of the recommended design** (level door, all target
  cells on one floor, no module, landmark, diagonal or spawn inside `A`), only
  **one door** is eligible: seed 1, `c03`-`c05`, with a 5-cell tree footprint.
  It has **zero** candidates, because its four internal passages are the only
  shared walls of the right width. The recommended design as written cannot
  re-roll any door in these five maps.
- **Under the v1 pin list** (module, landmark and diagonal cells allowed as
  content-pinned islands with their incident passages pinned; ramp doors
  allowed; internal ramps/drops pinned; spawn and exit excluded), **two
  directions** have at least two in-tolerance candidates: seed 279's 8-cell
  direction (3 candidates) and seed 32's 6-cell direction (2). Both are
  spawn-free, so both are eligible under the operator's pinned list. Seed 3 has
  no 3-8 cell bridge at all, and seeds 1 and 2 have a bridge but no spare wall,
  so no eligibility rule can give them a pool.
- **Under the Q10 spawn relaxation** (the spawn cell allowed as a content-pinned
  island, so its room and marker stay but its passages may change), **five
  directions** have at least two in-tolerance candidates: the two above plus
  seed 279's 6-cell and 5-cell directions and seed 32's 8-cell direction. All
  three additions contain the spawn cell. This is the difference between a
  sparse v1 and a mechanic that fires on more seeds; it is a relaxation of the
  operator's pinned list and needs an explicit answer (Q10).
- **The 3-8 window is too small for these maps.** The generator grows mostly
  tree-shaped branches, and the cells are large rectangles that often share only
  one wall. A 5-cell tree has exactly one connected passage graph on its own
  footprint, so it cannot be re-rolled. The measured 0 for seed 1 and seed 2 is
  not a tuning failure; it is the geometry of the committed maps.
- **The rich pool is small.** Seed 279's 8-cell direction has 13 hard-valid
  candidates, but only three pass the tier-1 shape tolerance. All three are
  edit 1: they remove one of the branch's two loops, keeping 8 of 9 passages.
  That is a recognisable first re-roll, but it is a pool of three, not a deep
  pool. A tier-1 minimum edit of 2 would delete both loops and fail the
  consistency target, which is why §4.5 uses a minimum of 1 and relies on the
  shape tolerance as the guard.
- **The exit interaction is a real risk.** The exit is not in the committed maps
  yet. In seed 279 the only figure cell is `c12`, which is inside the only
  8-cell pool; if the exit is chosen there and the v1 rule excludes the exit
  cell, the best pool is lost. Seed 32's 6-cell pool contains the figure cell
  `c10`; if the exit is there, that pool is lost, and the 8-cell direction is
  spawn-ineligible under the v1 pin list, so seed 32 would have no re-roll door
  unless Q10 allows the spawn or the exit selection chooses a cell outside both
  targets. This is why the exit selection order in §6.4 is mandatory, not a
  detail.
- **The spawn pin is the coverage cliff.** The spawn cell is `c00` in every
  committed map. v1 keeps the operator's pin, so a target containing spawn is
  not eligible and the measured coverage is two directions, not five. The Q10
  spawn relaxation would keep the spawn room and marker and let only its passages
  change, which is the reading that makes the reset point stable while the route
  out changes. The operator has to decide whether that counts as "the spawn stays
  exactly as it was"; the proposal does not assume it.

**The smallest change that preserves every pin** is the module/landmark/diagonal
content-pin island: those cells and their scenes stay exactly, and only their
incident passages are pinned; the rest of the branch rewires around them. It
requires no new geometry, no new map version and no generator change, and it
raises the measured coverage from one strict door with zero alternatives to
**two v1 doors with two or three in-tolerance alternatives each**. That is still
sparse, but it is real and it respects the operator's list. The Q10 spawn
relaxation is a separate decision that raises the count to five.

**The smallest change that makes every seed playable** is not an eligibility
tweak; it is a target-selection change. If Q9 option (b) is approved, a departed component
larger than 8 cells may be re-rolled as a connected 3-8 cell prefix `T` grown
from the root, with every passage from `T` to `A \ T` pinned. A preliminary
existence check (not a full candidate count) found that 35 of the 51 door
directions with `|A| >= 3` have a 3-8 cell prefix containing at least one spare
shared wall, including seed 3. That is a necessary condition for a candidate,
not a guarantee; the full `H_T` enumeration and shape filter still decide. The
prefix is a design change because the player may have come from deeper in `A`;
the near part of the route changes, the deep part stays. It is the recommended
way to get coverage on the committed seeds if that coverage is required.

**The robust long-term fix** is a generator-side rewire reserve: for new seeds,
designate one or more 3-8 cell bridge branches as "rewire-friendly" and grow
them as compact clusters (for example a 2x3 block, where every internal shared
wall is valid), so the footprint has spare passages by construction. That is a
new `gmap` version and it does not change the committed maps. It should be a
separate issue after v1; it is not part of this proposal's implementation list
unless the operator wants to replace the prefix fallback with it.

The analysis did not use an exit layer, did not build room specs, and did not
test line of sight. Those steps can only remove candidates, so the two v1 and
five Q10 spawn counts are upper bounds. The operator should read them as "at most
two v1 door directions, or five if the spawn is allowed, in these five maps",
not as a promise.

#### 4.5.10 Worked example

The cleanest eligible door in the committed maps is seed 32, door
`c00:p0 <-> c01:p0`. The player crosses from `c01` into `c00`; `B = c00` (the
spawn cell), `A = {c01, c02, c05, c10, c11, c12}`, and the root `R = c01`.
All six cells are on `floor_y = 0`.

- `E_A = {c01-c02, c01-c05, c05-c10, c05-c11, c10-c12}` (5 passages).
- `H_A = E_A ∪ {c01-c10}`; `c01` and `c10` share a 3 m wall at `x = -7`,
  `z = 6..9`, so one new doorway fits.
- `M_A = {c10-c12}` (internal pins), because `c12` is the library module
  `godot_early_pocket_single_west_v1`; its scene and its `c10-c12` doorway stay
  exactly as they are. `D` is the external mandatory attachment and is not part
  of `H_A`.
- The hard filter yields three candidates:

| # | Added | Removed | Edit | Retained | Shape `(leaves, loops, max depth, sum depth)` | Tier-1 tolerance | Why |
|---|---|---|---:|---:|---|---|---|
| C1 | `c01-c10` | — | 1 | 1.0 | `(3, 1, 2, 7)` | in | Opens a shortcut; c05 keeps its c10 link, so the degree profile changes by only L1 = 2 |
| C2 | `c01-c10` | `c01-c05` | 2 | 0.8 | `(3, 0, 3, 9)` | in | Swaps one junction; c05 is reached via c10; same degree profile as the base |
| C3 | `c01-c10` | `c05-c10` | 2 | 0.8 | `(3, 0, 2, 7)` | out | Closing c05-c10 drops c05 to a corridor and concentrates the root; degree profile L1 = 4 |

The shortlist is `[C1, C2]` (C3 is hard-valid but outside the tier-1 degree
tolerance). For an illustrative `event_index = 1`, the draw hash is
`eb0f20...`, which is odd, so the second shortlist entry is chosen: **C2**. The
chosen `A'` is:

```text
P = {c01-c02, c01-c10, c05-c10, c05-c11, c10-c12}
```

The changed geometry is exactly two shared walls:

- `c01-c05` (the 3 m wall at `z = 6`, `x = -7..-4`) becomes a wall;
- `c01-c10` (the 3 m wall at `x = -7`, `z = 6..9`) gets a 1.4 m doorway.

Everything else is unchanged. The cells stay `c01, c02, c05, c10, c11, c12`.
The cell IDs, envelopes, `floor_y`, roles and all per-cell keyed layers stay
identical: light tiers, lamp states and flicker seeds (#198); wear and surface
variants (#199); palette and floor material (#208); reverb (#204); mood, volume
and absorption (#219); the module scene and its doorway in `c12`; the B-side
cell `c00`; and the base map bytes. The only changed values are the doorway
records of `c01`, `c05` and `c10`, their `passage_revision`, and the overlay's
`branch_epoch`/`P`.

The player's experience: they walked from `c01` through `c05` to `c10` and the
module at `c12`. When they reopen the door, `c01` is still the same room with the
same lamps and floor, but the opening to `c05` is gone; a new opening leads
straight to `c10`. The module is still at the end of `c10`; the way to `c10` is
now direct instead of through `c05`. The route they used is not there; the place
is recognisable. If the shortlist draw had picked C1 instead, the old route
would still exist and a new shortcut would open; both are valid first-tier
changes, and the log records which one happened.

This example assumes the static exit is not `c10` or `c12`. If the exit selection
puts the bright threshold in `c10` (the figure cell) or `c12` (the module), the
v1 exit exclusion makes this door ineligible. That is the Q10 interaction, and it
is why the exit selection order is an implementation constraint (§9.1, M3).

#### 4.5.11 Replay and the tests the implementation issue must contain

The implementation issue that adds the enumerator (M5) must contain these
headless tests. The runtime issue (M6) must contain the geometry and reveal
tests. The save/cache issue (M7) must contain the persistence tests.

| # | Test | Owner | Assertion |
|---|---|---|---|
| T1 | Determinism | M5 | Same base map + same event log => same `P`, same `state_hash`, same `candidate_set_hash` |
| T2 | Five-seed golden fixture | M5 | The eleven 3-8 cell directions, the spawn column and the v1/Q10 pool split in §4.5.9 are reproduced exactly (2 v1 directions with >=2 in-tolerance, 5 if the spawn is allowed); seed 3 has none; seed 1 and seed 2 have zero |
| T3 | Hard invariants | M5 | For every hard-valid candidate: same cells, connected, strongly connected, degree ≤4, pins preserved, retained ≥0.5, edit in bounds, no content change |
| T4 | Shape shortlist | M5 | Tier-1 shortlist is the in-tolerance set; a relaxed shortlist records `consistency_relaxed`; C3 in §4.5.10 is hard-valid but not in the tier-1 shortlist |
| T5 | Seeded draw | M5 | The same `(seed, attempt, event_index, stream, threshold_id, algorithm_version)` picks the same shortlist entry; a changed `event_index` can pick a different one; the draw never picks outside the shortlist |
| T6 | Replay from stored `P` | M1/M7 | An event with `rewire-1` applies its stored `P` even if the current enumerator has changed; the state hash matches; no map writes |
| T7 | No visible change | M4/M6 | With the leaf closed, every cell of `T` is outside `visible_cells(B)`; a fixture with a visible target is rejected with `visible_target` |
| T8 | F0/F1/F2 | M6 | The global directed graph stays strongly connected; the exit is reachable from `B`; every reachable cell can still reach the exit |
| T9 | Geometry | M6 | Every new doorway fits its wall, does not overlap an existing opening or corner, does not cut a pinned/module wall; the room envelope, floor, ceiling and materials are unchanged |
| T10 | Cell and layer identity | M6 | Cell IDs, envelopes, `floor_y`, light, wear, surface variants, palette, reverb, mood and module scenes are byte-identical for every target cell; only doorway records and `passage_revision` change |
| T11 | Save/restore and cache | M7 | Base hash + log restores the same `P` and `state_hash`; a changed `passage_revision` is a cache miss; the #156 finite streamer fixture is unchanged |
| T12 | Python/GDScript parity | M5/M6 | The Python reference enumerator and the GDScript runtime enumerator agree on `H_T`, the hard-valid count, the shortlist and the chosen `P` for the seed 32 and seed 279 fixtures |
| T13 | Negative cases | M5/M6 | A straight 5-cell corridor has zero candidates; a 4-cell tree has zero; a 2-cell target is ineligible; a drop `D` is ineligible; a visible target is ineligible; a content-pinned cell with a removable pin is rejected; a no-candidate door does not latch |
| T14 | Stacked re-rolls | M5/M7 | A second re-roll whose target overlaps an earlier one uses the current `E_T` from the folded log, not the base map; its `passages_before` matches the current state; the two events replay to the same final state hash; the base map is unchanged |

The five-seed golden fixture is intentionally a golden test: if the generator or
the wall filter changes, the expected counts in §4.5.9 must be updated
deliberately, not drift silently. The fixture can use the committed map files
directly; it does not need a sidecar pool.

#### 4.5.12 Open questions from the algorithm

The full operator questions are in §10. The algorithm creates five:

- **Q9, coverage and target size.** Keep the full-`A` 3-8 rule and accept that
  only seeds 279 and 32 can re-roll (and seed 3 cannot); or allow a 3-8 prefix of
  a larger `A` (Q9 option (b), recommended if coverage on the committed seeds is
  required); or raise the cap to the whole departed component (Q9 option (c), simplest
  constants change but a near-whole-map re-roll). See §10 Q9.
- **Q10, content-pinned cells inside the target.** v1 follows the operator's pin
  list and excludes spawn and exit, which gives two doors with pools. The
  question is whether to allow either as a content-pinned island: the cell, room
  and marker/threshold stay, and only the incident passages may change. The
  recommendation is to allow both, because the content stays and fairness keeps
  the exit reachable; allowing spawn alone gives five directions but leaves the seed
  279 exit risk. If the operator keeps the exclusion, the exit selection must
  prefer cells outside every candidate target. See §10 Q10.
- **Q11, reserved void envelope.** Allow one adjacent safe void cell to be
  opened during a re-roll (adding one cell and one or two passages). The
  preliminary hard-valid counts rise (for example the seed 279 8-cell pool from
  8 to 35 at edit ≥2 without the shape filter, and the seed 32 6-cell pool from
  2 to 10), but it breaks the same-cell-count rule. It is a later extension, not
  v1. See §10 Q11.
- **Q12, first-tier edit character.** Allow a pure addition, require a removal,
  or require a swap. The recommendation is to allow any edit ≥1 and judge the
  feel on a walk. See §10 Q12.
- **Q13, latch policy.** Latch only a re-roll-ready door (recommended) or latch
  every door behind the player. See §10 Q13.

### 4.6 When it fires

The sequence is deliberately narrow:

1. **Crossing.** The player moves from `A` into `B` through `D`. Before the leaf
   closes, the controller evaluates eligibility (§4.4). If the door is eligible,
   the leaf closes and latches behind the player, and a `door_lock` event is
   logged with `threshold_id`, the target cells, the branch epoch and the
   eligibility result. If the door is not eligible, it behaves like any other
   door: no automatic latch and no re-roll. A door that is structurally a
   candidate but fails a runtime condition is logged as `door_reroll` /
   `rejected` with the failing code and does not latch. This keeps the latch
   itself meaningful: a door that closes behind the player is a door that has a
   re-roll ready.
2. **Occlusion.** The closed leaf makes `A` invisible. The old rooms may remain
   loaded; they are not rebuilt yet. The ranked candidate list is cached in
   memory. The player can walk on; the branch is frozen behind the leaf.
3. **Open request.** The player interacts with `D` from `B`. Before the leaf
   moves, the controller resolves the re-roll:
   - if a target cell's `content_revision` changed since the latch (a follower
     edit, a later elevation edit, a save/restore), rebuild the ranked list from
     the current map state;
   - choose the candidate from the cached shortlist using the commit
     `event_index` and the tier from `reroll_index`;
   - revalidate visibility, geometry, R0-R11 and F0-F2 with the real room specs;
   - on success, rebuild `A'` behind the closed leaf, swap, append the accepted
     `door_reroll` event, increment `reroll_serial`, and then open the leaf;
   - on failure, open to the old `A`, append a rejected event with
     `candidate_failed_runtime` or `geometry_conflict`, and mark the door
     blocked for the run.
4. **Never while visible.** There is no timer and no "the player turns around
   and sees the change". The new passage graph is already in place when the leaf
   opens. If the leaf cannot occlude, the door is not eligible.
5. **One accepted re-roll per threshold.** After it, the door is a normal door.
   The overlay stores `last_reroll_id` and `draw_index`; the base `doors[]` array
   is never edited. A rejected attempt does not spend the per-door cap, but the
   door is blocked for the rest of the run so the player is not asked to retry a
   door that cannot change. The no-retry rule is deliberate: the enumeration is
   deterministic, and reopening the same door a second later would produce the
   same conditions.

The re-roll does not fire on the first crossing, on a timer, or while the player
is inside `A`. It fires only on a later open from the `B` side. That is what
makes "it leads to an entirely different maze" a reveal rather than a pop.

### 4.7 Interaction with seeded room streaming (#162) and unloading

#162 is deferred and blocked on the room-library and workflow gates. The current
walkthrough instances every cell at load; the accepted #156 streamer is a
finite, bounded regression fixture. This proposal does not pretend #162 exists.

For the first runtime slice, the re-roll is a local, bounded form of unloading:

- The controller rebuilds only the room nodes whose doorway set changed, and
  only after the closed leaf hides them and only after `A'` has passed
  validation. Cells in `T` whose passages did not change keep their nodes; the
  `B` side is never touched. This is a smaller and safer operation than
  despawning the whole branch.
- The new passage graph is built from the base map plus the overlay passage set
  and the doorway records, not from a cache keyed only by `cell_id`.
- If #162 later streams cells, its cache key must include
  `(base_map_id, base_map_sha256, branch_epoch, passage_revision,
  content_revision, cell_id)`. A cell whose `passage_revision` changed is a cache
  miss. Since cell IDs never change on a re-roll, the stale-room failure mode is
  an old doorway set, and the revision is the guard.
- Unload and reload must not change the result: a cell's base layers still come
  from its per-cell draws, and its runtime doorway set still comes from the
  event log. Loading order is not part of the draw.
- A save/restore while a re-roll is pending (the door is latched, the leaf is
  closed, no `door_reroll` event has been appended yet) restores the
  `door_lock` trigger and re-enumerates from the current map state. The pending
  ranked list is ephemeral; losing it is acceptable because no mutation has
  happened. Once the `door_reroll` event exists, replay applies its stored `P`
  and does not need the pending list.
- The #156 finite streamed walkthrough remains a regression fixture with
  mutations off, so this work cannot silently change its behaviour.

### 4.8 What the player experiences

The intended beat is: step through, hear the leaf close and latch, walk on,
decide to go back, open the door, and find the same rooms with a different way
through them. The old route is gone; the exit is still ahead somewhere. Because
the exit is fixed (§6.4), if the player was walking toward it, the behind side is
the spawn side and the re-roll is safe. If the player wanders into a dead end,
the behind side contains the exit and the door is not eligible, so the mechanic
never strands them.

The same rooms, lamps, wear, palette and module anchors are what make the change
feel like the same place rearranged. The player does not see a new branch; they
see their branch with one junction, one wall or one loop changed. That is the
consistency target, and it is why the footprint and layer pins are hard rules
rather than preferences.

That asymmetry is the design: **you can only lose the path you have already
used, not the path you still need.**

---

## 5. Follower edits (B)

### 5.1 The follower is a process, not an enemy

For this proposal the follower is an off-screen process that edits the rooms the
player has already visited. It does not chase, block, damage or appear. It has
no combat stats, no pathfinding agent and no simulated body. In v1 the player
never sees it; it is present only as occasional audio (§5.6, §8). Its "body" is
the cue track and its "hand" is the edit event.

This keeps the work inside the existing map/runtime architecture and avoids the
out-of-scope enemy/combat system. It also preserves the operator's ambiguity:
"something or someone" is scarier when it is never confirmed.

### 5.2 Edit menu

Each edit reuses an existing layer. Costs are implementation cost, not runtime
cost; fairness risk is the chance the edit affects traversal.

| Class | What changes | Layer / field | Cost | Fairness risk | Phase |
|---|---|---|---|---|---|
| `lamp_state` | One lamp `on`/`flicker`/`dead`, or a tier change | `light.lamps[i].state`, `light.tier` (#198) | Low | None | M2 |
| `lamp_flicker` | Flicker seed or pattern only | `light.lamps[i].flicker_seed` (#198) | Low | None | M2 |
| `reverb` | Wet/dry flag | `cell.reverb`; `set_room_reverb` (#204) | Low | None | M8 |
| `wear` | Wear +1, capped at 2 | `cell.wear` (#199) | Low | None | M8 |
| `surface_variant` | One surface clean/worn/damaged within the palette | `cell.surface_variants` (#199) | Low | None | M8 |
| `palette` | Swap the cell's palette, including floor material | `cell.palette`; floor regions (#208) | Medium | None on graph; changes acoustic tag | M8 |
| `door_lock` | Latch an open/closed door in a visited room | `doors[].state`, `lock` (#223) | Medium | Must not remove the exit route | M4 |
| `dark_wing` | Add one contiguous cell to the dark wing | `dark_wing.cell_ids`; light/surface (#198) | Medium | None on graph | M11 |
| `prop_moved` | Move or rotate a small prop inside a generated room | New prop overlay; no prop system today | Medium | None on graph | M13 |
| `elevation` | Change a floor level, ramp or drop | `floor_y`, `vertical`, geometry/collision (#201) | High | Can break directed reachability; rebuild | M12 |
| `door_reroll` | Replace the passage graph on the departed footprint | `edges`, doorway records; §4 | High | Structural; §6 | M5/M6 |
| `breadcrumb_tamper` | Move/remove a marker | `breadcrumbs`; §7 | Low | Fairness of the aid, not the exit | Later (not v1) |

Explicitly **not** in the menu: changing a cell envelope or shape (a re-roll
keeps the envelope too; changing it is not a mutation at all), moving a library
module or the landmark (operator-approved, frozen), changing the static exit
(v1; §6.4), or changing the exit without the fairness check. `breadcrumb_tamper`
is listed only as later work; v1 breadcrumbs are honest (§7, Q5). The landmark is
a map-level figure, not a prop; if a prop system arrives, it moves small objects
inside a room, never the landmark cell.

`door_lock` in v1 is a manual latch used for occlusion and dread; it does not
remove the edge, because the player can always open it. A future keyed or
impassable lock is the only door edit that can affect F1/F2, and it must pass
the fairness check before it is applied.

Target scope matters. Generated shape rooms can receive every class in the
table. A library module's scene is hash-pinned and its light, wear and palette
are baked into that scene, so the follower may give it a reverb flip or a door
overlay (a runtime prop at the port) but not a lamp, wear or palette rewrite. A
re-roll may contain a module cell only as a **content-pinned island**: the module
scene and every passage incident to it stay exactly as they are, and the rest of
the branch rewires around it. The re-roll never rebuilds or re-doors a library
scene. This is a v1 limitation, not a reason to edit a library scene.

A palette swap is medium cost because the floor material is also the acoustic
tag read by `walk_player._floor_acoustic` and the footstep bus. It is allowed
only when the new palette is present in the registry and its variants are
compatible; it is a visible and audible change, so it belongs after the cheap
lamps and wear.

An elevation edit is the only follower class that touches geometry. It must
rebuild the affected cell's floor, ramp/drop and collider, may change the
neighbor's ceiling clearance, and must satisfy F0-F3. If a neighboring cell that
would change is still visible, defer the edit; otherwise the player could watch
a wall or floor move.

### 5.3 The out-of-sight rule

An edit is queued when its cadence trigger fires, but it is applied only when
the target satisfies all of:

- the target cell is not the player's current cell;
- the target cell is not in `visible_cells(player_cell)`, a conservative graph
  walk through open and `closed_visible` openings up to a bounded depth;
- the target room node is not being rendered in the current view (the graph
  check is the cheap proxy; the render check is a backstop);
- the target is not in the middle of a door transition or a re-roll.

The current cell is the last cell whose interior the player entered. A door
transition is atomic for mutation purposes: no edit or re-roll fires while the
capsule is between cells.

If the target never becomes hidden, the edit is dropped rather than applied in
view. A dropped edit is not an event; it did not happen. This is the one place
where player behaviour legitimately changes the mutation history, and the log
makes that history reviewable.

Applying at re-entry is preferred to applying while the room is still loaded
but merely off-camera: the player sees the room already changed when it comes
back, not a flicker at the edge of vision. For the first lamp slice, the
implementation may apply when the player leaves the cell, provided the change is
not visible from the doorway.

### 5.4 Cadence and escalation

The cadence is counted in **distinct visited cells**, not seconds. A player who
stands still should not be punished, and a speedrunner should not outrun the
dread. The counter is monotonic: a re-roll changes passages, not the visited-cell
count, and it does not reduce the escalation already earned. The trigger sequence
is logged, so replay consumes it instead of re-simulating movement.

Proposed curve (all numbers are guesses for the operator walk). `next_edit`
is scheduled as `last_edit + interval(last_edit)`, where `interval` is read from
the row that contains the `last_edit` count:

| Distinct visited cells | Edit cadence | Classes allowed | Notes |
|---|---|---|---|
| 0-4 | None | None | Establish the base maze; first cue may occur on the 5th |
| 5-9 | One edit per 4 newly visited cells | `lamp_state`, `lamp_flicker`, `reverb` | Cheap, reversible, no graph effect |
| 10-14 | One per 3 newly visited cells | Add `wear`, `surface_variant`, `door_lock` | The first "did that change?" beat |
| 15-24 | One per 2 newly visited cells | Add `palette`, `dark_wing` | Visible wear and dark wings |
| 25+ | One per 2 newly visited cells; at most one structural edit per 6 newly visited cells | Add `elevation` only if later approved | Door re-roll is a separate door-triggered mechanic (§4.5), not a follower cadence edit; `MAX_REROLLS_PER_RUN = 3` still caps it |

Additional rules:

- At most one edit per room entry; never two edits in the same entry.
- Never edit the same cell twice in a row.
- Never edit the cell the player is in, the exit cell, the spawn cell, or a
  visible cell.
- After a `door_reroll`, grant a quiet period of at least 3 newly visited cells
  before the next follower edit, so the reveal has room to breathe.
- If no eligible target exists, skip the beat and do not force an edit. Forcing
  one produces the "random" feeling the operator wants to avoid.
- The first edit should be a lamp or a reverb, not a door lock. The player needs
  to learn that small things change before the maze asks them to distrust a door.

The curve is deliberately monotonic: the maze gets less stable as the run gets
longer, rather than rolling a fresh probability every room. That is what makes
it feel like escalation instead of noise.

### 5.5 Target selection

Given the eligible set, choose with a keyed rank, not a sequential walk. The
edit class is a keyed weighted draw from the allowed set; the target is the
keyed rank below.

- Prefer cells the player passed 1-3 rooms ago, so a backtrack can reveal the
  change.
- Prefer cells with degree 2 or more, so the player is likely to pass again.
- Weight recent cells higher than the spawn end, but never the last edited cell.
- Avoid a cell whose only doorway is the player's current view.
- Skip a module cell for a class that would rewrite its baked light, wear or
  palette; the module target set is limited to reverb and door overlays.
- If the class is `dark_wing`, require the chosen cell to be graph-adjacent to
  the existing dark wing and eligible under #198's rules (not spawn, not
  landmark, not module, not void).
- If the class is `door_lock`, require the door to be on a visited edge and
  require the exit to remain reachable from the player's current cell with the
  lock applied.

### 5.6 How the follower exists

| Option | What the player perceives | Strength | Cost / risk |
|---|---|---|---|
| Unseen agent | Footsteps, doors and edits with a moving cause; may be avoided | Strongest causal dread | Needs a graph walker, distance rules and a "never catch" contract; can drift into enemy design |
| **Audible cues only (chosen for v1)** | Distant steps, a door, a lock; no body | Cheap, ambiguous, works with current audio | The player may not connect cue to edit; needs careful mixing |
| Implied only | Rooms simply change | Strongest "the maze is unstable" | Can feel random or unfair; no presence to fear |
| Visible entity | A body at the end of a corridor | Immediate | Out of scope: enemy/combat, animation, AI, new assets |

**Decision (Q4, Q8).** For v1 the follower is **audio-only and occasional**:
distant steps, a door, a latch; no body. It is never seen. It never chases,
blocks, damages or catches the player, and it has no visible model, animation,
pathfinding agent or combat behaviour. This keeps the work inside the existing
audio and map architecture and preserves the operator's "something or someone"
ambiguity. The cue rules are in §8.

The operator's long-term direction, recorded here as a note and **not designed
in this proposal**, is an almost 4-dimensional entity that creeps in by
distorting space and time. If that direction is ever pursued it needs its own
design issue; it is not a v1 feature and must not drift into enemy/combat design.

---

## 6. Fairness invariant

### 6.1 Graph

Let `G` be the current directed traversal graph:

- nodes: walkable cells (`role != "void"`);
- edges: `directed_edges(document)` after the overlay is applied: level and
  ramp edges both ways, drop edges upper-to-lower only, and diagonal and
  elevation-loop edges exactly as the generator's traversal graph includes them.
  A door in `open`, `closed` or manually latched state stays bidirectional,
  because the player can open it from either side. A future keyed or impassable
  lock removes its edge while locked; that is the only door state that changes
  reachability.

The existing helpers are the authority:

- `gmap_elevation.strongly_connected(cell_ids, edges)` — Kosaraju over the
  directed edge list; reusable by any caller, per the #201 report.
- `gmap_elevation.directed_edges(document)` — drops are one-way; everything
  else is bidirectional.
- `gmap_elevation.directed_reachable(document, start)` and
  `drop_has_return_route` — the reachability primitives.

No mutation implementation may re-implement these on a different graph shape.
If the graph changes, the helper changes once and every mutation is re-tested.

### 6.2 Invariants

Every accepted event must satisfy:

| ID | Invariant | Check |
|---|---|---|
| F0 | **Strong connectivity (v1).** Every walkable cell reaches every other through the directed graph. | `strongly_connected(walkable_ids, directed_edges)` |
| F1 | **Exit reachable.** The exit is reachable from the player's current cell. | `exit in directed_reachable(G, player_cell)` |
| F2 | **No trap.** Every cell reachable from the player can still reach the exit. | For each `c` in `directed_reachable(player_cell)`, `exit in directed_reachable(c)` |
| F3 | **Geometry valid.** Ports match, envelopes do not overlap, walkable surfaces exist, drops have a return route. | Existing generator checks plus `drop_has_return_route` |
| F4 | **Nothing visible changes.** The edited cell or re-roll target is outside `visible_cells(player_cell)` at commit. | Visibility helper |
| F5 | **Base identity unchanged.** The committed map hash, seed, attempt, catalog snapshot and pins are the same before and after. | SHA-256 verification |
| F6 | **Replay agrees.** Re-applying the log produces the same state hash and the same F0-F5 outcomes. | Replay harness |
| F7 | **Same footprint.** A re-roll keeps the exact cell set, IDs, envelopes, roles, `floor_y` and per-cell keyed layers; no cell is added, removed, moved or retired. | Set and layer hash comparison |
| F8 | **Pins preserved.** `D`, every vertical passage, every passage incident to a module, landmark or diagonal cell, and every prefix boundary passage are unchanged. The spawn/exit cells follow the Q10 reading. | Passage-set comparison |
| F9 | **Change is real and consistent.** A re-roll changes at least one passage, retains at least half of the base passages, and its shortlisted candidates satisfy the tier's shape tolerance (or record an explicit relaxation). | Edit distance, retained fraction, shape metrics |

F1 is the operator's stated rule. F2 is the stronger version that prevents the
"the exit is reachable, but I walked into a one-way wing and cannot get back to
it" soft-lock. F0 is the strictest form: in v1 every door is openable and every
drop has a return route, so the whole graph should stay strongly connected.
The mutation validator therefore requires F0, not just F1. F1 and F2 remain the
operator-facing statement and the checks that stay meaningful if a later keyed
lock or moving exit makes the graph intentionally one-way; they are checked on
every event as well. The v1 exit is static (§6.4), so F1/F2 have a fixed target;
a moving exit is later and out of scope for this proposal.

F7-F9 are the extra invariants a door re-roll adds. They are not new fairness
rules; they are the footprint and consistency contract from §4.3-4.5 expressed
as validator checks. F7 and F8 are hard. F9 has a hard floor (one passage
changed, at least half retained, no pinned passage moved) and a soft shortlist
(the shape tolerance, which may be relaxed with `consistency_relaxed=true` when a
map has no in-tolerance candidate). A candidate that fails the hard floor is
rejected; a candidate outside the soft shortlist is only considered after every
in-tolerance candidate.

### 6.3 Reusing the #201 validator

#201 implemented `strongly_connected` over the directed graph and used it to
keep every one-way drop returnable. The same function validates a re-roll
candidate:

1. Build the candidate graph from the unchanged `B` side plus the chosen passage
   set `P` on `T`. Do not build a separate graph type: the candidate is just the
   base graph with the target's level passages replaced.
2. Require `strongly_connected(all_walkable_ids, candidate_edges)` for v1. This
   catches a branch that is reachable only one way and has no return.
3. Apply the current door and elevation states (drops are one-way; a future
   impassable lock removes its edge) and require F1 and F2 from the player's
   current cell. In v1 the door states do not remove edges, so this is a
   redundancy check on the F0 result.
4. Require the local form as well: `T` is strongly connected under `P` plus its
   pinned vertical passages, and `D` is the only attachment to the `B` side (or,
   in prefix mode, every boundary passage is pinned). The local form is the
   theorem that makes the enumeration bounded; the global check is the backstop.
5. A candidate that fails is dropped during enumeration. The chosen candidate is
   revalidated with the real room specs at open time. If it fails there, the
   controller opens the old `A` and logs `candidate_failed_runtime`; it does not
   try the next candidate in the same open. There is no retry loop.

The local theorem is: if the base graph `G` is strongly connected, `T` is
strongly connected under `P` and its pinned vertical edges, and every passage
between `T` and the rest of the graph is pinned, then replacing `T`'s internal
level passages with `P` leaves `G` strongly connected. Every path that used a
removed passage can be rerouted through `T`'s strong connectivity; the rest of
the graph is unchanged. In full-`A` mode the only boundary is `D`; in prefix
mode the boundary is the pinned set. This is why the algorithm does not need to
search the whole graph for every candidate, but it still runs the global check
because the theorem depends on the pins being correct.

The #201 report's negative case (a ramp changed to a one-way drop without a
return route, rejected with `elevation_graph_not_strongly_connected`) is the
template for the negative tests here. A re-roll that removes the only return
route must fail with a named code, not an exception.

`strongly_connected` lives in Python (`gmap_elevation.py`); the runtime is
GDScript. V1 therefore needs a small GDScript port (`maze_graph.gd`) or a
precomputed graph pass plus a live BFS. The Python version remains the reference
implementation for the headless enumeration and the golden fixture; the
GDScript version is the runtime F0-F2 check. They must agree on a shared
edge-list fixture, including a drop with and without a return route, and on the
seed 32/seed 279 re-wire fixtures (§4.5.11). This is a bounded port of one
function and one enumerator, not a second generator.

### 6.4 The exit, its style, and the win condition (decided)

The operator decided Q1-Q3 on 2026-11-12 (§10). These are design inputs now,
not options:

- **One static exit.** Exactly one exit threshold is chosen at seed generation.
  It does not move during a run. Q2 records this as an initial-version choice,
  not a permanent rule, but v1 must not implement a moving exit.
- **A distinct bright door.** The exit is a threshold door, always a door that
  reads as bright, inside a room that carries the clean, bright industrial
  test-chamber style the operator described as the Portal 2 direction. The same
  visual language must read consistently from seed to seed; room layout may
  vary, but the threshold must stay unmistakable.
- **Style, not asset copying.** This is a style and consistency target. The
  game reference is a style comparison only; no third-party texture, model,
  logo or other asset is copied, referenced or required. The implementation
  builds original materials and geometry in the existing palette language; a
  later asset issue may refine it, and the operator's visual acceptance is the
  gate.
- **Placement.** At a leaf cell (preferred) or a figure cell chosen
  deterministically from the seed. The selection runs before the re-roll
  eligibility map and prefers a cell outside every candidate target, so the exit
  does not silently remove the only re-roll door. The exit cell is pinned in v1:
  it is excluded from every re-roll and follower edit, never part of a departed
  component, and never the spawn cell. The threshold door is not a re-roll door
  and is not eligible for lock-behind. Q10 asks whether the exit may instead be a
  content-pinned cell inside a target; if the operator allows it, the room,
  threshold and marker stay exactly as they are and only the route to them may
  change. Until that is decided, the conservative exclusion is the v1 rule and
  the placement order is a hard implementation constraint (§9.1, M3).
- **Win condition.** Crossing the exit threshold ends the run. A short end card
  follows, showing the seed, rooms visited, edit count and re-roll count (and
  any other counters already in the log). The end card is the whole escape
  loop; it is not a score.
- **No progression.** The end card does not offer or start a next level or a new
  seed. Level/seed chaining is outside this repository's scope for now: this
  repo constructs levels, and something else would tie them together. Do not
  design or implement next-seed progression in #209 or its implementation
  issues.
- **No moving exit in v1.** A moving exit stays out of scope. If a later version
  reopens it, every move must be a logged mutation event with its own draw, a
  cue, and F0/F1/F2 checks, and it must never move into a visible cell or a
  branch about to be re-rolled.
- **Fairness.** With a static exit, F0/F1/F2 still apply. A re-roll or edit that
  would remove the exit route is rejected before commit (F1/F2); the exit
  threshold is never retired, rebuilt or replaced. Under v1 the exit cell is
  excluded, so its room is not re-doored either. If Q10 allows the exit cell
  inside the target, the threshold and room content stay exactly as they are, but
  the passages around the cell may change; F1/F2 keep the exit reachable. The
  exit is the stable "out" the player runs toward while the path behind them
  changes.

### 6.5 Repair rules

- An edit or re-roll that fails an applicable F-check is rejected before commit;
  the log records the failing code.
- A re-roll that fails validation keeps the old passage graph and the old room
  nodes; the new nodes are not swapped in until every check passes. The old
  branch is never lost because it is never despawned before the new one
  validates. A failure opens the door to the old `A` and marks the door blocked
  for the run.
- A door lock that would remove the exit route is not applied; the door may
  close but stays openable.
- If a committed state is later found to violate F0-F2 (a bug, not a design),
  the controller unlocks the last door and logs a `repaired` event; it never
  teleports the player. This is an error path, not a gameplay mechanic.
- There is no death, no fall damage (#201), and no "you are trapped, restart"
  screen in the mutation design. F0-F2 are absolute.

---

## 7. Breadcrumb mode (later work)

### 7.1 Options

| Option | What it is | Player aid | Diegetic fit | Risk |
|---|---|---|---|---|
| Dropped markers | Player places a finite number of objects | Precise route marks | Strong; a physical object in the world | Inventory/placement UI; asset work |
| Auto trail | Crumbs or a line appear as the player moves | Strong; low effort | Medium; why is it there? | Clutter; can trivialize backtracking |
| Map memory | A 2D visited map or minimap | Strongest | Weak; a UI layer | Turns the maze into a map-reading game |
| Chalk/thread | Player draws a line or unspools thread | Strong, physical | Strong | Continuous geometry; can be cut or blocked |
| Honest vs tampered | Any of the above, with the follower able or unable to change it | Varies | Strong if the rule is learnable | Tampering can feel unfair if silent |

### 7.2 v1 design (honesty and toggle decided)

The v1 aid is the proposed limited, diegetic auto trail with one small marker
per distinct visited cell, a proposed cap of 32 (not measured), visible only at
short range, and **honest**: it always reflects the player's true path. The
operator decided the honesty on 2026-11-12 (Q5), together with the toggle:
default off, pause-menu toggle available from the start (Q6).

Honest markers still help the player notice that a room changed without turning
the maze into a minimap: a marker that is now behind a closed wall, or a trail
that no longer connects the same way, is evidence that the maze changed.
Tampering is not part of v1.

This is later work: it depends on the re-roll (markers stay in their cells and
the route between them may change) and on the follower edit visibility gate. It
should not be in the first implementation slice.

### 7.3 Honesty and tampering (decided for v1)

The operator decided that breadcrumbs are **honest in v1**. An unreliable or
tampering mode is liked in principle but is too confusing for the initial
version, so it stays later work and is not scheduled here.

If a tamper mode is ever built, it must follow these rules and needs explicit
operator approval:

- **Honest (v1).** The trail always reflects the player's true path. It reduces
  dread but makes the re-roll legible: a marker whose former opening is now a
  wall is evidence that the maze changed, without the marker itself moving.
- **Follower tampering (later).** The follower may move or remove a marker, at
  most one per edit, never the marker in the player's current cell, never
  create a marker in an unvisited cell, and never lead the player into a
  non-walkable cell. A moved marker visibly changes (tilt, colour, a missing
  cap) so the player can learn the rule. Silent tampering is unfair.
- **Unreliable by design (later).** Markers sometimes lie; the player can never
  trust them. This is the strongest dread but the weakest fairness; it needs an
  explicit tell and the operator's approval.

F0-F2 never depend on breadcrumbs, so even a future lying trail cannot
soft-lock the run.

### 7.4 Data model

The base map already reserves `breadcrumb.marker_id`, `kind`, `persistent`, and
#212 §3.7 adds `owner_scope` and `sequence`. The overlay should store the live
version:

```text
marker_id, cell_id, port_id, sequence, kind, owner_scope,
persistent, state ("placed" | "moved" | "removed" | "retired")
```

Events: `breadcrumb_drop`, `breadcrumb_move`, `breadcrumb_remove`,
`breadcrumb_tamper`, `breadcrumb_retire`. The base map is not edited. A marker
in a re-rolled target stays in its cell and keeps its state; the re-roll does not
delete markers. The route between markers may change, which is honest evidence
of the re-roll. A future mutation that actually retires cells (none in v1) would
need its own marker-retirement rule; the re-roll does not.

### 7.5 Toggle (decided)

Default off, pause-menu toggle available from the start, with no penalty for
turning it on and no first-escape unlock. The operator confirmed this after
reading the wording (Q6). It is a comfort/difficulty aid, not an accessibility
requirement.

---

## 8. Sound and feel

### 8.1 What already exists

- `walk_player.gd` plays layered footstep stems (transient, body, texture) with
  material tags from the floor collider; #203 built the stems and the runtime
  layering.
- `room_acoustic_probe.gd` samples the room at about 4 Hz and on each step;
  `room_reverb_bus.gd` maps the probe to a stock `AudioEffectReverb` on a
  dedicated `Footsteps` bus, created in code because `godot_walk/project.godot`
  is frozen.
- `generative_map_assembly.gd:199-209` exposes `set_room_reverb`; the flag is
  node metadata, so a runtime flip is already possible (#204).
- `shape_room_lamp_flicker.gd` is a seeded 8 Hz visual pattern on an
  `OmniLight3D`; it has no audio.

There is no follower audio, no door-lock sample, no ambient track and no score.
Agents cannot hear; every audio claim is a design guess until the operator
listens.

### 8.2 Cue menu

| Cue | Source / method | When | Purpose |
|---|---|---|---|
| `follower_step` | Existing footstep stems, 3D player at a cell 1-2 graph steps away, lowpass, volume by distance, 1-3 steps | When the player is still or between their own steps | The presence; can precede an edit |
| `door_close` | Low thud, built from an existing `land` or `wood`/`metal` transient, pitched down | As the leaf closes behind the player | Confirms the lock and the boundary |
| `lock_click` | Short metal transient, dry | Immediately after `door_close` | The latch; the tell that the door is now a threshold |
| `door_reopen` | The same latch click as `lock_click`, optionally followed by a low room-tone tail from beyond the leaf | When the re-roll opens | The door is the same; the room beyond is not. The reveal is visual; the tail is room tone, not a different door |
| `reverb_flip` | No dedicated sound; the room tone changes on the next footstep | On re-entry after a wet/dry edit | The room itself is the tell |
| `lamp_buzz` | Optional low hum from a procedural oscillator, tied to the flicker | While a flickering lamp is visible | Reinforces the light edit; asset work |
| `distant_collapse` | Optional low rumble, no direction | Rare, during escalation | Scale and dread; asset work |

The first four can be built from existing samples. The last three are future
asset work and are not part of this proposal's implementation.

`door_reopen` must **not** sound like a different door. The operator clarified
that the door stays the same; the cue is the same latch the player already heard,
optionally followed by a low room-tone tail from the new passage graph. The
reveal is visual, not a door-swap sound. If the tail sounds like a second door,
it is wrong and should be cut.

### 8.3 Bus and mix

Use a separate `Follower` bus, created in code like `room_reverb_bus.gd`, with a
lowpass and a 3D `AudioStreamPlayer` pool. The player's own footsteps stay on
the `Footsteps` bus. This prevents the follower's steps from being mistaken for
the player's and lets the operator mix the cue independently.

For v1, do not try to probe the follower's source room; use a fixed lowpass and
distance attenuation. A later version can read the source cell's `reverb` flag
and send the cue through a second reverb, but that is extra complexity for a
sound the player should barely identify.

### 8.4 Pacing rules

The follower is heard, never seen, and its cues are occasional. A run may go
several rooms without one; silence is part of the effect. The rules below keep
the cue rate low.

- No cues in the first 4 rooms. The base maze must establish its own sound
  before the follower has a voice.
- One cue per edit at most, and no more than one cue per 8-15 seconds. Silence
  between cues is part of the effect.
- Prefer cues when the player has just stopped or is between their own steps;
  a follower step buried under the player's sprint is wasted.
- The `door_close` and `lock_click` are mandatory **on an eligible door**; they
  are the mechanic's contract. The other cues are optional and should not be on
  every edit, or the player learns the pattern and stops being unsettled.
- No non-diegetic music or stingers. The score is the room tone and the
  player's own steps. This is a design preference, not an operator decision,
  but it follows from the "diegetic, ambiguous" direction.
- Reverb flips are never applied while the player is in the room. The change is
  heard on re-entry as a different tail, not as a live crossfade.

The 8-15 second and 4-room numbers are guesses. They need an operator listen on
a real walk, not a headless assertion.

### 8.5 What the audio must not do

- It must not promise a visible enemy or a reveal the design will not deliver;
  the follower is heard, not seen.
- It must not mask the player's own footsteps so thoroughly that movement feels
  unresponsive.
- It must not play a cue for every edit, or the follower becomes a metronome.
- It must not change a room's reverb while the player is inside it.

---

## 9. Architecture constraints for the backlog

These are constraints on work already planned, so mutation is not blocked later.

### 9.1 Per-cell keyed draws, not sequential draws

New layers must use per-cell keys from day one:

```text
sha256("<seed>:<attempt>:<stream>:<cell_id>:<purpose>")
```

`gmap_keyed.rng_for_cell`, `gmap_reverb.keyed_draw` and
`gmap_floor_regions.keyed_draw` are the pattern. `gmap-0.13.0` already uses
per-cell keys for light, surface, elevation, palette anchors, floor regions and
reverb. Mutation events add `event_index` to the same key, as in §3.3. The
remaining problem is that the layer functions still walk the whole document and,
in `_build_v13_layers`, alternate light and surface passes. A runtime edit must
not call `assign_light(document)` or `assign_surface(document)` to change one
cell; that risks recomputing the dark wing, the near-library brightening or the
palette graph and shifting cells the player has seen.

Implementation constraint: add **per-cell pure functions** (or an override
layer) that compute one cell's value from frozen neighbours and a draw key, and
make the whole-document pass use those functions. A re-roll must **not**
recompute any layer: every cell in the target keeps its light, wear, surface
variants, palette, reverb, elevation, mood and module content. The only new
geometry is a doorway cut, and the only new draws are the candidate shortlist
selection and the doorway placement; neither consumes a layer stream. This is
stricter than the earlier proposal, which allowed a new branch to recompute its
own layers; the footprint-preserving design does not need that and should not do
it.

Static exit selection (§6.4, Q1-Q2) must follow the same discipline: a
seed-keyed draw over eligible cells, not a sequential pass. It must not consume
draws from an existing layer stream or shift any existing cell's value. A map
can carry the selected exit in a new layer version, or derive it from the seed
at load for maps generated before that version. The selection must run before the
re-roll eligibility map and prefer a cell outside every candidate target; if the
exit lands inside the only 3-8 cell pool, the v1 exit exclusion silently removes
the re-roll door. This is a real interaction in seed 279 (§4.5.9).

The re-roll enumerator is a runtime pure function, not an offline branch
generator. It reads the base map's cells, walls and pins and enumerates passage
graphs on the existing footprint. It consumes no layer stream and produces no
new cell geometry. The only artifact it produces is the chosen passage set and
the doorway records; both are stored in the event. If the enumerator is cached at
map load, the cache is an optimization of the same function and is keyed by the
base map hash and `rewire-1`; it is not an authority and it is not committed.

### 9.2 Layers mutable at runtime, not baked at generation

The committed map is the base; the runtime overlay is the state. This is the
same rule as #204's reverb and #212 §6.3:

- scalar flags: node metadata, like `reverb_enabled`;
- materials and lamps: runtime setters on the instanced room;
- geometry (elevation, props, re-roll): rebuild the room node from a derived
  spec; never edit the committed map or shape-room JSON;
- re-roll: the derived spec is the base room spec with the doorway records for
  the chosen passage set. Each cell's ID, envelope, floor, materials, lamps and
  per-cell keyed values are copied unchanged; only the doorway list and
  `passage_revision` differ;
- library modules: reverb and door overlays only; their light, wear and palette
  are baked into hash-pinned scenes and are not rebuilt or rewritten. A re-roll
  may not change a module cell's doorway set; the module is a content-pinned
  island (§4.3).

A mutation must leave `sha256(base_map.json)` unchanged. The test is trivial
and should be in every mutation issue.

### 9.3 Stable identity and branch epochs

- Base cell IDs and port IDs never change.
- A re-roll **does not create or retire cells**. It changes the level passage set
  inside the target and the doorway records on the affected shared walls. Cell
  IDs, envelopes and per-cell keyed layers stay valid across the re-roll.
- A cell whose doorway set changed gets a new `passage_revision`; a cell whose
  passages did not change keeps its revision and its node.
- A threshold's runtime identity is its pinned current-side port and a stable
  `threshold_id`, not a base `door_id` that may stop being the passage identity
  after a rewire. The passage identity is the sorted cell pair; the old doorway
  record is tombstoned, never the cell.
- The overlay carries `branch_epoch`, `passage_revision`, `content_revision` and
  `algorithm_version`; a streamed cache key includes them.
- Breadcrumbs, save files and telemetry reference cell IDs; the IDs stay valid,
  so a marker in a rewired cell is still a marker in that cell. The route between
  markers may change; no marker is retired by a re-roll.
- A queued follower edit that targets a cell whose `content_revision` changed is
  revalidated against the new state, not retargeted to a different cell. There is
  no retired-cell fallback to invent.
- The run-wide escalation counter is monotonic and is not reduced by a rejected
  re-roll.
- The door's `reroll.draw_index` and `last_reroll_id` are overlay audit fields for
  how many times a threshold has changed. The base `doors[]` array is never
  edited.

### 9.4 Runtime ownership

One `MazeMutationController` per walkthrough:

- owns the event log, overlay, cadence counters and state hash;
- receives `room_entered`, `door_opened`, `door_closed`, `exit_entered`,
  `cell_unloaded` and `save_restore` triggers as signals; appends the trigger
  record before deciding what, if anything, to mutate; on `exit_entered` it
  emits `run_end`, stops mutations and leaves the end card to the UI;
- calls the graph/visibility/fairness helpers before committing;
- asks the assembly to apply cell overrides or a rewire on the target cells;
- never edits `godot_walk/scripts/player.gd` (frozen) and never writes into the
  committed map document; any runtime document it builds is a copy.

The assembly remains the renderer/physics owner. It exposes narrow methods:
`set_room_reverb`, future `set_cell_light`, `set_cell_surface`,
`apply_rewire(target_cells, passage_set, doorways)`, and the visibility query.
Mutation logic does not leak into `walk_player.gd`.

### 9.5 Doors and rebuild boundaries

The current generated doorway is an opening, not a leaf:
`shape_room_spec.doorway_records` writes `kind: "open"` or `closed_visible`;
`shape_room_builder._add_doorway` builds the opening or a wall. A library
module's doorway is also an authored opening, and the library scenes are
hash-pinned.

To support a lock/occlusion, add a **door leaf** as new geometry:

- generated shape rooms: a new shape-room version adds a leaf mesh and collider
  for eligible doors; the existing version and its committed rooms stay valid;
- library modules: a runtime door prop at the port, never an edit to the
  library scene;
- no new texture asset in this proposal: reuse the palette materials. If the
  operator wants a distinct door material, that is a later asset decision.

A door without a leaf is not re-roll eligible. This is a hard constraint, not a
polish item, because the leaf is what makes the swap invisible. The leaf is only
at `D`; the internal passages of the re-roll are open doorways, not leaves. A
ramp `D` is eligible only if the leaf can be placed at its port without
rebuilding the ramp; if the ramp has no flat landing, the door is not eligible.

The internal doorway cuts for `A'` are **not** a new shape-room version. They are
derived records on a copy of the base cell spec: the cell's shape, materials,
floor, ceiling, lamps and props are unchanged, and only the `doorway_records`
list differs. The shape-room builder's doorway path is reused; no new texture,
mesh or material is introduced. A module cell is content-pinned, so its doorway
list is never regenerated.

The static exit threshold (§6.4) is a different door: it may use a distinct
original bright material and room treatment in M3, but it still must not copy a
third-party asset.

### 9.6 One fairness helper, one visibility helper

- `maze_graph.py` (or equivalent) wraps `directed_edges`, `directed_reachable`,
  `drop_has_return_route` and `strongly_connected`. Every mutation calls it.
- `maze_visibility.gd` (or equivalent) answers `visible_cells(player_cell)` with
  a conservative graph walk through open and `closed_visible` openings. It is
  deterministic and allocation-light; it does not depend on camera FOV.
- The two helpers are tested independently, including negative cases: a future
  keyed lock that removes the only route, a one-way drop with no return, a branch
  that is visible through a void.
- The Python reference enumerator/validator and the GDScript runtime validator
  share fixtures: the same cell list, directed edge list, passage universe and
  pins must produce the same `H_T`, hard-valid count, shortlist and chosen `P`,
  including the #201 negative case and the seed 32/seed 279 re-wire fixtures. The
  Python one is the headless reference; the GDScript one validates the live graph.

### 9.7 Streaming, unloading and save/restore

- #162 is deferred; do not make mutation depend on it. The first slice rebuilds
  the changed room nodes locally while the door is closed; it does not need a
  general streamer.
- When #162 lands, load by `(base_map_id, base_map_sha256, branch_epoch,
  passage_revision, content_revision, cell_id)` and rebuild from base + overlay.
  Never cache a room by `cell_id` alone; a cell with an old `passage_revision` has
  the wrong doorways even though its ID and layers are correct.
- Rebuild only the cells whose doorway set changed, and only after the new
  passage graph validates and the leaf hides them. Keep the old nodes until the
  atomic swap; there is no retired cell to unload.
- Save/restore stores the base map hash plus the event log, including trigger
  records, not a mutated map. The cadence is reconstructed from the trigger
  sequence. A pending (not yet applied) re-roll is ephemeral: if the save has a
  `door_lock` trigger but no `door_reroll` event, the controller re-enumerates on
  restore; losing the pending list is acceptable because no mutation has
  happened. Once the `door_reroll` event exists, its stored `P` is the state.
- The #156 finite streamer remains a regression fixture with mutation disabled.

### 9.8 Versioning and frozen files

- The overlay/event schema is a new record; do not overload
  `generative_map.schema.json` or `generative_map_v2.schema.json` in place.
- The base map's `mutation.classes` enum currently lists `door`, `reverb`,
  `palette`, `light`, `breadcrumb`
  (`generative_map_v2.schema.json`, `$defs.mutation`). The follower menu adds
  `surface`, `elevation` and `prop`, and the door re-roll adds `door_reroll` plus
  the `rewire` block; those belong in the new overlay schema, not in a silent
  enum extension.
- A base-generator change is a new `gmap` version. A mutation never changes the
  generator version of an existing map.
- The static exit is a new layer/field version, not a mutation and not an
  overload of an existing schema. Existing maps keep their bytes; the runtime
  derives the same exit from the seed until a map is regenerated with the layer.
- The re-roll algorithm version (`rewire-1`) is a runtime contract, not a `gmap`
  version. A change to the enumeration, wall filter, ranking or draw bumps it to
  `rewire-2`; an old event still applies its stored `P`, and only an audit
  compares the old `candidate_set_hash`. The base generator version of an
  existing map never changes.
- A future generator-side rewire reserve (compact re-roll footprints for new
  seeds) is a new `gmap` version. It must not change the committed maps; existing
  seeds keep their bytes and their measured eligibility (§4.5.9).
- Dark-wing growth, palette swaps and elevation edits must not change the
  committed map or any existing seed's generated values. They are overlay state.
- Never edit the frozen set: `godot_walk/scripts/player.gd`,
  `godot_walk/project.godot`, library room scenes,
  `godot_walk/room_catalog/catalog.json`,
  `godot_walk/room_catalog/MATERIAL_LANGUAGE.md`,
  `godot_walk/room_catalog/material_palettes/PALETTES.md`. Extend through new
  files and new versions.

### 9.9 What must not be built into the generator

- No door-lock state in the committed map. The map stores eligibility/policy;
  the overlay stores live state.
- No follower cadence in the generator. Cadence is runtime, seeded per event.
- No re-roll result in the committed map. The map is the base; the passage
  rewire is overlay state.
- No new cell IDs, no retired cells and no candidate-pool sidecar for a re-roll.
  The footprint is fixed and the chosen passage set is stored in the event.
- No mutation-driven change to a library module scene.
- No exit movement or next-seed progression. V1's exit is static, and the run
  ends at the end card; level/seed chaining belongs outside this repository.
- No "random" runtime call without a `(seed, attempt, event_index, stream)`
  key.

---

## 10. Operator decisions (2026-11-12)

The operator answered the eight questions in two comments on issue #209
(comments 509 and 510) on 2026-11-12. The second comment supersedes the first on
Q3 and confirms Q6-Q8 after the operator read the wording. These are decisions,
not recommendations; the rest of this revision reflects them.

### Q1. What is the exit? — decided

A distinct threshold door: always a bright door inside a room styled in the
clean, bright industrial test-chamber direction the operator described as the
Portal 2 look. The threshold and its room should read consistently from seed to
seed. This is a style and consistency target, not a request to copy any
third-party asset; the implementation must use original materials and geometry.
See §6.4.

### Q2. Does the exit move? — decided

No, not in v1. The exit is static from seed generation. The operator noted that
they had earlier said the exit could move; this is an initial-version choice,
not a permanent rule. A moving exit is out of scope for this proposal and for
the v1 issue list. Q10 is a different question: whether the static exit cell may
be content-pinned inside a re-roll target. The exit itself would still not move;
only the route to it could change. See §6.4 and §10 Q10.

### Q3. What is the win condition? — decided

Finding the exit and crossing its threshold ends the run with a short end card:
seed, rooms visited, edits, re-rolls. This confirms the end-card part of the
proposal's recommendation, but not the earlier next-seed sentence. Chaining
levels or seeds is outside this repository's scope for now; do not design
next-seed progression. The first operator comment's "continues to the next
level / new seed" reading is superseded. See §6.4 and §11.

### Q4. How does the follower exist? — decided

The follower is not a core dynamic now. It is an audible cue plus an implied
presence, as recommended. It does not chase, block, damage or appear. See §5.6
and §8.

### Q5. Is breadcrumb mode honest? — decided

Honest in v1. An unreliable or tampering breadcrumb mode is liked in principle
but is too confusing for the initial version; it stays later work and is not
scheduled. See §7.3.

### Q6. Breadcrumb default and toggle — decided

Default off, with a pause-menu toggle available from the start. Confirmed after
the operator read the wording. See §7.2 and §7.5.

### Q7. Door re-roll coverage and caps — decided

Eligible bridge doors whose departed component is 3-8 walkable cells. At most
one re-roll per door (`max_rerolls = 1`) and at most three per run
(`MAX_REROLLS_PER_RUN = 3`). The operator also clarified the term: a re-roll is
not copying or restyling a door. The door stays the same; the part of the maze
behind the player is regenerated into a different layout once the door is
closed. See §4.1 and §4.4.

This decision was confirmed before the feasibility measurement in §4.5.9. The
measurement keeps the 3-8 window as the v1 rule but records that it is sparse:
11 bridge directions across the five committed seeds, 1 strict eligible door with
zero alternatives, **2 v1 door directions with pools** (seed 279's 8-cell direction with 3
candidates and seed 32's 6-cell direction with 2), and **5 directions** if the spawn
cell is allowed as a content-pinned island (the Q10 spawn option). The coverage question is Q9
below; it does not change the cap without the operator's answer.

### Q8. Does the player ever see the follower? — decided

Never in v1. Its presence is audio-only and occasional. The operator described
the long-term direction as an almost 4-dimensional entity that creeps in by
distorting space and time; that is a note for later, not a design for this
proposal or its issue list. See §5.6.

### Q9. Coverage and target size — open, needs an answer before M5

The full-`A` 3-8 rule cannot re-roll seed 3 (no 3-8 bridge in either direction)
and gives seeds 1 and 2 zero alternatives. The options are:

- **(a) Keep full-`A` 3-8.** Accept that only seeds 279 and 32 can re-roll, and
  file a generator-side rewire reserve for new seeds (compact 2x3-ish branches
  with spare shared walls). This preserves "the whole departed component is
  regenerated" exactly and is the smallest semantic change.
- **(b) Full `A` when 3-8, otherwise a 3-8 prefix.** If `A` is larger than 8,
  re-roll a connected 3-8 cell prefix `T` grown from the root, pin every passage
  from `T` to `A \ T`, and leave the rest of `A` unchanged. This keeps the 3-8
  work bound and the same consistency algorithm, and it gives the committed seeds
  a target. The player loses the near part of the route they used, not the whole
  departed component. A preliminary existence check found 35 of 51 door
  directions with `|A| >= 3` have a 3-8 prefix containing at least one spare
  shared wall, including seed 3; that is a necessary condition, not a full pool
  count, and some of those prefixes contain the spawn cell, so under the v1 pin
  list they would still be ineligible.
- **(c) Raise the cap to the whole departed component.** With the whole `A`
  (up to 13 cells) and the spawn allowed, every seed has a pool before the exit
  exclusion (seed 3's 12-cell component has 225 hard candidates at edit >=2
  without the shape filter; the in-tolerance count is lower and is not measured
  here). This is the simplest constants change but the largest re-roll: almost
  the whole map behind the player is rearranged. The exit selection order still
  applies, so a seed whose only big A contains the exit can still lose the
  mechanic.

**Recommendation:** (b) if the committed seeds must demonstrate the mechanic,
because it preserves the 3-8 work bound and the consistency algorithm while
fixing the coverage; otherwise (a) plus the generator reserve. Do not choose (c)
for v1 unless the operator wants a near-whole-map re-roll. If (b) is approved,
the prefix rule is: grow a connected set from the root, prefer frontier cells
that add spare shared walls, cap at 8 cells, exclude the exit and (under the v1
pin list) the spawn, pin the boundary, and enumerate the prefix's passage graphs
with the same §4.5 algorithm. The exact prefix search is an implementation
detail in M5, not a second design.

### Q10. May the spawn and exit cells be content-pinned inside the target? — open, needs an answer before M5

The old exclusion of spawn, exit, module and landmark cells was justified by the
old design retiring the branch. Footprint-preserving rewire keeps every cell, so
the rationale no longer applies. The module/landmark/diagonal refinement is
already part of the v1 pin list: those cells and their scenes stay exactly, and
only their incident passages are pinned. The remaining question is the spawn and
exit cells:

- **Allow both as content-pinned islands (recommended if coverage matters).**
  The spawn point, exit room, threshold and marker stay exactly as they are; the
  passages incident to them may change; the rest of the branch rewires. A reset
  puts the player back in the same room with a different route. F1/F2 still
  require the exit to be reachable; if it is inside the target, the candidate
  must keep it reachable from the root. Measured: 5 directions, and the seed 279 exit
  risk is removed because the exit can be inside the target as long as it stays
  reachable. This is a revision of the Q2 "exit is excluded from every re-roll"
  decision and needs explicit approval.
- **Allow spawn only.** The exit stays hard-excluded. Measured: 5 directions, but seed
  279's only rich pool can be lost if the exit is chosen at `c12`. The exit
  selection must then prefer a cell outside every candidate target.
- **Keep both excluded (v1 default).** Measured: 2 directions (seed 279's 8-cell
  direction and seed 32's 6-cell direction); seed 279 still risks losing its rich
  pool to the exit selection. This is the reading that treats "spawn" and "exit"
  as pinned including their incident passages.

**Recommendation:** allow both, because the cells and their content stay exactly
as they were and fairness is checked; the only change is the route to them. If
the operator reads "spawn" or "exit" as including the passages around the cell,
keep both excluded and accept the two-door v1 coverage. Either way, the exit
selection order in §6.4 is mandatory when the exit is excluded.

### Q11. Is a reserved void envelope worth the extra cell? — open, later

A re-roll could open one adjacent void cell whose walkable neighbours are all
inside `A`, adding one room and one or two passages. The preliminary hard-valid
counts rise (seed 279's 8-cell pool from 8 to 35 at edit >=2 without the shape
filter; seed 32's 6-cell pool from 2 to 10), but it breaks the same-cell-count
rule and needs the void's floor, layers and content to be generated on the fly.
**Recommendation:** defer to a later extension; do not use it in v1. The
generator-side rewire reserve is a cleaner way to get spare adjacency without
adding a cell at runtime.

### Q12. Should the first re-roll be allowed to add a shortcut, or must it remove a passage? — open, taste

A tier-1 candidate may be a pure addition (a new loop or shortcut), a pure
removal (a loop closes), or a swap (one passage removed, one added). The shape
shortlist allows all three. The measured maps contain both characters: seed 32's
C1 is a pure addition, and seed 279's three consistent candidates are pure
removals.

- **Allow any edit ≥1 (recommended).** The seeded draw gives variety, and a first
  re-roll that opens a new shortcut is unsettling in a different way from one
  that closes a route. The shape shortlist keeps either from changing the room
  character.
- **Require at least one removal in tier 1.** The player's route is always
  broken, which is closer to the headline "the route you came from is gone". It
  removes the pure-addition candidates and thins the already thin pool.
- **Require a swap.** Every re-roll both closes and opens a passage. This is the
  most legible "the walls moved" reading, but it rejects the pure-removal seed
  279 candidates and may leave that door with no tier-1 candidate.

**Recommendation:** allow any edit ≥1, and let the operator judge the feel on a
walk. If the first re-roll must always feel like a loss, choose the removal
requirement and accept a smaller pool.

### Q13. Does every door latch, or only a door with a re-roll ready? — open, taste/pacing

The design latches only a door that has passed eligibility (§4.4, §4.6). That
makes the latch a meaningful tell and guarantees the player is never locked out
of a door that cannot change. The alternative is that every door latches behind
the player, and only the eligible ones re-roll; the latch becomes ambient dread
but loses its meaning, and the player may repeatedly open doors expecting a
change that never comes.

**Recommendation:** eligible-only. It is the cleaner contract and it keeps the
"locked door with nowhere to go" failure out of the design. This is a
taste/pacing decision, not a technical one; if the operator wants every door to
latch, the re-roll eligibility check moves to the open request and the lock state
stays harmless.

### Questions that remain open

These are not decided by the operator. Q9, Q10 and Q12 must be answered before
M5; Q13 before M4. Q11 is later, and the rest do not block M1:

- Q9, Q10, Q11, Q12 and Q13 above.
- The exact end-card wording and which counters it shows.
- The exact original materials, geometry and lighting for the bright exit room.
  The style direction is set; the asset work and the operator's visual
  acceptance are later.
- The pacing constants: edit cadence, cue interval and escalation curve need an
  operator walk and listen.
- Whether a dishonest breadcrumb mode is ever wanted. It is later work only and
  is not scheduled.
- Whether the long-term 4D follower direction is ever pursued. It is a note, not
  a design.
- The storage mechanism for the static exit: a new map layer or a seed-derived
  value for existing maps. This is an implementation choice, not an operator
  question. The selection order (before re-roll eligibility) is an implementation
  constraint, not a choice.

---

## 11. Proposed implementation issues (after approval)

These are proposals, not filed issues. Each is sized to one loop run. They are
slices of #223, which is the umbrella runtime-overlay issue and must not start
until #209 is closed. The first slice is deliberately headless: it proves the
event log and replay before anything is visible. The operator decisions in §10
are fixed inputs: the exit is static, crossing it ends the run with an end card,
and there is no next-seed or next-level progression. M1 and M2 can use a
synthetic exit fixture; M3 adds the real static exit and end card, and every
later issue uses it.

| Order | Working title | Scope | Verification | Depends on |
|---|---|---|---|---|
| M1 | Mutation overlay core and replay | Event record, trigger and mutation records, keyed draw, fold, state hash, JSONL log, headless replay; the event envelope reserves the `rewire` block from §3.2/§4.5.8; run counters derivable from the log | Same base + log => same overlay; trigger-only cadence reconstructs; reorder/tamper/base-mismatch rejected; rewire block round-trips; map hash unchanged; no runtime | Approved #209 |
| M2 | Follower edit: lamp state and flicker | Per-cell light override, visibility gate, cadence counter; first visible edit | Leave cell, edit applies, re-enter sees new lamp; no other cell shifts; map hash unchanged; capture | M1 |
| M3 | Exit threshold and run end card | Static seed-keyed exit selection, evaluated before the re-roll eligibility map and preferring a cell outside every 3-8 target; bright threshold door and original test-chamber room treatment; crossing ends the run once; end card shows seed, rooms visited, edits and re-rolls; no next-seed or level progression | Same seed => same exit cell; exit excluded from re-roll/edit targets; the selection runs before eligibility; one `run_end` event and one end card per run; counters match the log; no progression action exists; map bytes unchanged; capture for operator style review | M1 |
| M4 | Door state and lock-behind | Overlay `doors[]`, procedural leaf for generated rooms, close/latch on crossing, manual open; ramp doors only when the leaf fits the port; no re-roll; exit threshold is not lock-behind eligible | Headless cross/lock/open; the closed leaf occludes the target; exit reachable; library doorways skipped; save/restore; capture | M1, M3 |
| M5 | Door re-roll: passage-graph enumerator and headless validation | `rewire-1` enumerator: `H_T`, mandatory pins, hard invariants R0-R11, shape ranking, shortlist, seeded draw, event payload; full-A 3-8 in v1 (prefix fallback only if Q9 option (b) is approved); spawn/exit exclusion per Q10; no runtime geometry | T1-T5, T12-T14; the §4.5.9 golden fixture (11 directions, 2 v1 doors with >=2 in-tolerance, 5 if Q10 allows spawn, seed 3 none); seed 32 C1/C2/C3; seed 279 13/3; no-candidate fail closed; Python/GDScript parity | M1, M3, M4 |
| M6 | Door re-roll: runtime rebuild and reveal | Apply `P` on the same cells; place doorways; rebuild only changed room nodes from derived specs; atomic swap behind the closed leaf; GDScript F0-F2 check; no cell retirement | T6-T10, T13; headless door-open reveal; no pop in captures; cell IDs and per-cell layers unchanged; only doorway records and `passage_revision` change; map hash unchanged; operator walk pending | M5 |
| M7 | Door re-roll: save, restore and cache | Persist base hash + event log (no pool hash); restore across reloads; cache key includes `branch_epoch`/`passage_revision`; pending re-roll re-enumerates from the `door_lock` trigger; #156 fixture unchanged | T6, T11, T14; save/reload at the door produces the same `P` and state hash; a changed `passage_revision` is a cache miss; #156 regression; map hash unchanged | M6 |
| M8 | Follower edits: reverb, wear and variant | Reverb flip (existing setter), wear/variant overrides, palette-compatible validation | Per-cell isolation; map hash unchanged; old cells unchanged; capture; operator walk/listen | M1, M2 |
| M9 | Follower presence cues | `Follower` bus, 3D cue pool, distant steps, door/lock sounds, cue events; audio-only, occasional, never visible; `door_reopen` is the same latch plus a room-tone tail, never a different door | Cue timing/distance/volume checks; no visible follower node; no audio assertions; operator listen pending | M1, M2 |
| M10 | Breadcrumb mode (later) | Markers, pause toggle, honest trail; default off; toggle available from the start; no tamper mode in v1; a re-roll keeps markers and changes only the route | Drop/replay; map hash unchanged; re-roll keeps every marker in its cell; no marker is deleted; toggle works from the start; markers are honest; operator walk | M6, M9 |
| M11 | Dark-wing growth (later) | Add one contiguous visited cell to the dark wing; update its light and surface | Light/surface consistency; no non-wing cell shifts; map hash unchanged; capture | M2, M8 |
| M12 | Elevation edits (later) | Change one visited branch's floor/ramp/drop; rebuild geometry and collision | F0-F3 checks; return route for every drop; no visible pop; capture | M7, M8 |
| M13 | Prop edits (later) | Move or rotate a small prop in a generated room; needs a prop system first | Prop overlay replay; no graph effect; no visible pop; capture | M8 |
| M14 | Escalation tuning and evidence | Tune cadence constants, collect replay logs and captures, operator walk; verify end-card counters and no progression; record the five-seed eligibility/re-roll counts from §4.5.9 | A full run with A and B; metrics recorded; no new mechanics | M2-M13 |

Notes on sizing:

- M1 is the **first verifiable slice**: it can pass without a door, a lamp or a
  player. If M1 is not deterministic, nothing after it can be trusted.
- M2 proves the out-of-sight rule and the per-cell override on the cheapest
  layer. It should not also add a door.
- M3 adds the static exit and the end card before any door mutation. It gives
  every later fairness check a real exit and closes the escape loop. It must not
  add seed or level chaining. If the style pass is too large for one loop run,
  split the material work into a follow-up without changing the functional
  contract.
- M4 adds the leaf and the lock but not the re-roll; this isolates the geometry
  and occlusion risk.
- M5, M6 and M7 split the re-roll into the pure enumerator, the runtime
  rebuild/reveal, and the save/restore/cache contract. Each is a full loop run;
  combining them would be too large. M5 is where the §4.5.9 golden fixture lives,
  so a thin pool or a generator drift is caught before any geometry moves.
- Q9 (target size/prefix), Q10 (content-pinned spawn/exit) and Q12 (first-tier
  edit character) must be answered before M5; Q13 (latch policy) before M4. Q11
  is later. The rest of the issues do not depend on them.
- M8 adds the layers that are cheap metadata but have visual/audio tells.
- M9 is audio; agents can verify event wiring, not the mix.
- M10, M11, M12 and M13 are explicitly later; they should not block the first
  A/B slice.
- M14 is a tuning/evidence run, not a feature. It needs the operator's walk and
  listen.

### 11.1 First four issues in detail

1. **M1 — Mutation overlay core and replay.** Add `maze_mutation` with trigger
   and mutation records, `draw_for_event`, `fold_events`, `state_hash`, JSONL
   read/append, cadence reconstruction from triggers, and a replay CLI. The event
   envelope reserves the `rewire` block from §3.2/§4.5.8 even though no re-roll
   exists yet; a follower edit uses `change` and no `rewire`. Tests use a
   committed gmap-0.13.0 map and synthetic logs. Assertions: deterministic state
   hash; event order matters; trigger-only cadence matches; rejected events are
   inert; base hash mismatch rejected; a `rewire` record round-trips without
   being interpreted; no file writes to the map. This is the only issue that can
   start immediately after approval.
2. **M2 — Lamp state/flicker edit.** Add `set_cell_light` to the assembly (or a
   small runtime light controller), an override record, the visibility gate and
   the cadence counter. The first event is a lamp flip in a room the player has
   left. Check that the committed map hash is unchanged, the target cell's
   override is the only change, and re-entry shows the new state. Capture before
   and after; operator visual review is the human step.
3. **M3 — Exit threshold and run end card.** Add deterministic static exit
   selection from the seed (a new layer version, or a seed-derived value for
   existing maps), a bright threshold door and an original clean test-chamber
   room treatment in the operator's style direction, and the run-end trigger.
   Run the exit selection **before** the re-roll eligibility map and prefer a
   cell outside every 3-8 target, so the exit does not silently remove the only
   re-roll door. The end card shows seed, rooms visited, edits and re-rolls from
   the log; it offers no next level or new seed. Check that the same seed selects
   the same exit, the exit is excluded from re-rolls and edits, crossing fires
   `run_end` once, the counters match the log, and no progression action exists.
   Capture the threshold for operator visual review. Original materials only; do
   not copy or reference a third-party asset.
4. **M4 — Door state and lock-behind.** Add the leaf geometry as a new
   shape-room version (or a runtime prop for library ports), the overlay door
   state, close/latch on crossing, and manual open. No re-roll. A ramp door is
   eligible only if the leaf fits the port without rebuilding the ramp. Check
   that a generated door closes and latches, that the closed leaf occludes the
   target, that the player can open it from the current side, that the exit
   remains reachable, and that a library doorway without a leaf is skipped rather
   than silently locked. Capture the closed and open states.

### 11.2 What is deliberately not in the first pass

- No follower entity, pathfinding or chase.
- No visible follower; presence is audio-only in v1.
- No breadcrumb tamper mode; v1 breadcrumbs are honest, default off, with a
  pause-menu toggle from the start.
- No elevation/prop edits.
- No moving exit; the exit is static by decision.
- No next-seed progression, level chaining or score.
- No third-party assets; the exit style target is original work.
- No new audio assets; cues reuse existing stems or wait for an asset issue.
- No change to committed maps or library scenes. The static exit is additive:
  an existing seed keeps its existing layer values, and its exit is either
  recorded in a new layer version or derived from the seed at load.
- No prefix fallback or reserved void envelope unless Q9 option (b) or Q11 is approved.
- No offline candidate pool, sidecar hash, new cell IDs or cell retirement.
  A re-roll is a passage-only change on the existing footprint.

---

## 12. Scope guard

- This is a revised proposal, not an approval. The operator decisions in §10 are
  recorded; the operator still reviews this revision before any implementation
  issue is filed.
- No code, schema, generator, map, shape-room or asset change is part of #209.
- The five-seed feasibility analysis in §4.5.9 is a throwaway script run outside
  the repository. Its method, constants and results are recorded in the
  document; the script itself is not committed, and no map or generator output
  changes because of it.
- No hash-pinned file is edited: `godot_walk/scripts/player.gd`,
  `godot_walk/project.godot`, library room scenes,
  `godot_walk/room_catalog/catalog.json`,
  `godot_walk/room_catalog/MATERIAL_LANGUAGE.md`,
  `godot_walk/room_catalog/material_palettes/PALETTES.md`.
- No catalog admission, source event, `registration_accepted` or
  `scale_calibrated` change.
- No enemy/combat, scoring, new source ingestion or SkillOpt run.
- No next-seed progression or level chaining; the run ends at the exit card.
- No third-party asset files, textures, models, logos or other assets. The
  bright exit style is an original-work target.
- No push and no issue closure by the worker; the operator does both.

---

## Appendix A — References

### A.1 Issues cited

| Issue | Title | Why it matters here |
|---|---|---|
| #169 | Automate video seed selection, PSX room review, and module integration proposals | Parent direction; map-first and operator-approval rules |
| #149 | Generate the first seeded multi-room Backrooms walkthrough | First seeded layout baseline |
| #156 | Stream connected Backrooms modules for effectively endless walking | Finite bounded streamer; regression fixture |
| #162 | Scale seeded room streaming after the approved room library and workflow mature | Deferred streaming; cache-key and unloading constraint |
| #198 | Light layer: map-driven lamps, flicker and dark wings with lit PSX materials (gmap-0.8.0) | Lamp states, flicker seeds, dark wing |
| #199 | Surface layer: palette variants, wear and acoustic material tags (palettes 0.2.0, gmap-0.9.0) | Wear and surface variants |
| #201 | Elevation: floor levels, ramps and one-way ledge drops, no fall damage (gmap-0.10.0) | Directed graph, `strongly_connected`, drops and ramps |
| #203 | Layered procedural footsteps (footsteps-0.3.0) | Follower cue source; player footsteps |
| #204 | Per-room reverb flag in the generative map (wet/dry rooms) | Runtime reverb flip precedent |
| #205 | Ray-cast room-acoustics probe and footstep reverb bus | Probe and `Footsteps` bus; cue mix |
| #208 | Floor-material palettes: tile, metal and wood floors in generated rooms | Palette/floor-material edits and acoustic tags |
| #212 | Proposal: complete metadata template for the generation scope | Template fields, §3.7, §3.10, §6.3 |
| #219 | Template T6: ceiling/volume, exits/roles and mood descriptors | Module exits/roles and mood fields; the map-level exit decision is recorded in §10 |
| #220 | Template T7: gmap-0.13.0 consuming the template | Per-cell keyed layer work |
| #223 | Template T10: implement the #209 runtime overlay (door re-roll, follower, breadcrumb state) | The implementation umbrella; blocked by #209 |

### A.2 Files cited

| Path | What it establishes |
|---|---|
| `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md` | Map-first rule; rooms fit cells; no inferred connectivity |
| `docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md` | Reserved door/mutation/breadcrumb fields; runtime overlay; per-cell keyed recommendation |
| `godot_walk/room_catalog/generative_map.schema.json` | `attempt` definition; base map contract |
| `godot_walk/room_catalog/generative_map_v2.schema.json` | `doors`, `mutation`, `mood`, `volume`; base placeholders |
| `godot_walk/scripts/gmap_draft_generation.py` | `attempt_rng`, `site_layout_rng`, generation retry |
| `godot_walk/scripts/gmap_build.py` | Offline map assembly and versioned layer wiring; the base map the rewire enumerator reads. No candidate-pool tool is added |
| `godot_walk/room_catalog/generative_maps/gmap-{1,2,3,32,279}-gmap-0.13.0.json` | The five committed maps used for the §4.5.9 feasibility measurement; they are read only and never modified |
| `godot_walk/scripts/gmap_grow.py` | Tree growth, `connect`, port placement and bridge-shaped branches |
| `godot_walk/scripts/gmap_keyed.py` | Per-cell keyed draw and stable rank |
| `godot_walk/scripts/gmap_light.py` | Light tiers, lamp states, flicker seeds, dark wing |
| `godot_walk/scripts/gmap_surface.py` | Wear and variant draws |
| `godot_walk/scripts/gmap_palette.py` | Palette anchors and regional floor assignment |
| `godot_walk/scripts/gmap_floor_regions.py` | Per-cell keyed regional floors |
| `godot_walk/scripts/gmap_elevation.py` | `strongly_connected`, `directed_edges`, `directed_reachable`, drops/ramps |
| `godot_walk/scripts/gmap_reverb.py` | Per-cell keyed wet/dry flag |
| `godot_walk/scripts/gmap_template.py` | Base `doors[]` and `mutation` placeholders |
| `godot_walk/scripts/shape_room_spec.py` | Doorways are `open`/`closed_visible`, not leaves |
| `godot_walk/scripts/shape_room_builder.gd` | Doorway geometry; no door leaf today |
| `godot_walk/scripts/generative_map_assembly.gd` | Runtime room instancing; `set_room_reverb` |
| `godot_walk/scripts/walk_player.gd` | Layered footsteps, probe, reverb bus hookup |
| `godot_walk/scripts/room_acoustic_probe.gd` | Room metrics for the reverb mix |
| `godot_walk/scripts/room_reverb_bus.gd` | Bus created in code; frozen project file avoided |
| `godot_walk/scripts/register_video_sources.py` | Append-only, sequenced source event log precedent |
| `godot_walk/scripts/shape_room_lamp_flicker.gd` | Seeded 8 Hz visual flicker |
| `godot_walk/evidence/2026-11-08-issue-201/REPORT.md` | Strong-connectivity validator and negative case |
| `godot_walk/evidence/2026-11-09-issue-205/REPORT.md` | Probe/bus implementation and pending listen |
| `docs/evidence/gmap-0.13.0-visual-evidence.md` | Per-cell stream changes and keyed layer identity |

The feasibility script from §4.5.9 is deliberately not in this table: it is a
throwaway analysis run outside the repository, and the document records its
inputs, constants and results so it can be reproduced without committing it.

### A.3 Checklist against the eight questions

| #209 question | Where answered |
|---|---|
| 1. Mutation model, seeded event log, `attempt` and streams | §3 |
| 2. Door re-roll: same-footprint passage rewire, pins, seeded draw, firing, streaming | §4; measurement in §4.5.9; Q9-Q13 in §10 |
| 3. Follower edits: menu, out-of-sight rule, cadence, follower existence | §5 |
| 4. Fairness invariant and directed validator; exit and win decided | §6, §10 |
| 5. Breadcrumb mode: what it is, honesty, toggle, later work | §7, §10 |
| 6. Sound and feel; cues, reverb flips, pacing | §8 |
| 7. Architecture constraints for the backlog | §9 |
| 8. Proposed implementation issues, ordered and sized | §11 |

The feasibility measurement is an addition to question 2, not a new question:
it tests whether the door re-roll can actually fire on the committed maps. The
answer is "not often enough yet", and Q9-Q13 are the resulting operator
decisions. The rest of the eight-question structure is unchanged.
