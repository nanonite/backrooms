# Mutating-Maze Dynamics — Proposal

Status: revised proposal for operator review (2026-11-12). Operator decisions on
the eight questions are recorded in §10; this revision applies them. The second
operator comment on 2026-11-12 supersedes the first on Q3 and confirms Q6-Q8
after the operator read the wording. Design issue #209, child of #169.

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
  it leads to an entirely different maze.
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
| Branch re-growth that fits the vacated envelopes | Unproven; needs the headless slice in §11 |
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
| Layout: cells, envelopes, ports, tree, loops, diagonals | map `cells`, `edges` | `seed + attempt` through `gmap_draft_generation.attempt_rng` | No | Door re-roll only; never a follower edit |
| Light: tier, lamps, flicker seeds, dark wing | cell `light`, map `dark_wing` | `light:gmap-0.8.0`; per-cell `light:gmap-0.13.0` | No setter yet | Lamp state, flicker seed, dim tier, dark-wing growth (#198) |
| Surface: wear and variants | cell `wear`, `surface_variants` | `surface:gmap-0.9.0`; per-cell `surface:gmap-0.13.0` | No | Wear step, one-surface variant change (#199) |
| Palette and floor regions | cell `palette`, map `floor_regions` | `palette` and `floor_regions:gmap-0.12.0`; per-cell keys in 0.13.0 | No | Palette swap, floor-material tell (#208) |
| Elevation | cell `floor_y`; edge `vertical`, `ramp`, `drop` | `elevation:gmap-0.10.0`; per-cell keys in 0.13.0 | No | High-cost edit; geometry rebuild (#201) |
| Reverb | cell `reverb`, map `reverb_layer` | `reverb:gmap-0.11.0`, keyed per cell | Yes: `set_room_reverb` | Wet/dry flip (#204) |
| Doors | cell `doors[]`, edge `door_id` | Base policy only, stream `door-reroll:gmap-0.13.0` reserved | No state machine yet | Lock, unlock, re-roll eligibility (#223) |
| Landmark | map `landmark`, cell `landmark` | `landmark:gmap-0.7.0` | No | Excluded from edits; operator-approved figure |
| Mood / volume / absorption | cell `mood`, `volume`, `absorption` | Derived from module metadata (#219) | No | Cue selection and room character, not a mutation target yet |
| Footsteps, probe, reverb bus | `walk_player.gd`, `room_acoustic_probe.gd`, `room_reverb_bus.gd` | Runtime | Yes, by design | Follower cues, reverb tell (#203, #205) |
| Streaming | full map instanced at load; #156 finite streamer | `seed + catalog snapshot` | Not in the current walkthrough | Branch unload/reload; general streaming is #162 |

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
implements that overlay.

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
     catalog_snapshot_sha256, module metadata pins, candidate_pool_sha256
     when re-rolls are enabled)
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

Every accepted event also stores the resulting per-cell values (or the
replacement branch fragment). Replay applies those values and verifies the
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
    "candidate_pool_sha256": "<64 hex>",
    "generator_version": "gmap-0.13.0",
    "seed": 279,
    "attempt": 0
  },
  "trigger": {
    "kind": "room_entered",            // room_entered | player_opened_door
                                       // | exit_entered | cell_unloaded
                                       // | save_restore | debug
    "player_cell": "c07",
    "from_cell": "c06"
  },
  "target": {
    "cell_id": "c03",
    "port_id": null,
    "threshold_id": null,             // stable runtime door identity
    "branch_root": null                // first cell of the departed component for a re-roll
  },
  "stream": "follower:gmap-0.13.0",
  "draw": {
    "purpose": "lamp-state:1",
    "reroll_serial": null,
    "branch_attempt": null
  },
  "change": {
    "class": "lamp_state",
    "layer_version": "gmap-0.13.0",
    "before": {"tier": "normal", "lamp_index": 1, "state": "on"},
    "after":  {"tier": "normal", "lamp_index": 1, "state": "dead"}
  },
  "validation": {
    "outcome": "accepted",             // accepted | rejected
    "checks": ["target_hidden", "exit_reachable", "escape_safe"]
  },
  "visibility": {
    "player_cell": "c07",
    "target_hidden": true,
    "visible_cells": ["c07", "c08"]
  },
  "prev_state_hash": "<64 hex>",
  "state_hash": "<64 hex>"
}
```

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
(for example `lamp-state:1`). For a graph-wide choice, use a stable sortable
rank:

```text
keyed_rank(seed, attempt, "<stream>:<event_index>", key)
```

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
| `reroll_serial` | one door | Counts accepted re-rolls of that door; seeds the branch selection | Increments on accepted re-roll |
| `branch_attempt` | one re-roll | Candidate index in the precomputed branch pool; the offline generator uses the same index | Selects/retries a candidate only |
| `hunyuan.attempts[]` | one source | Hunyuan inference cap | Unrelated |

For a door re-roll, the offline branch generator seeds candidate
`branch_attempt` as:

```text
sha256("<seed>:<attempt>:<reroll_serial>:<branch_attempt>:door-reroll:<threshold_id>:<departed_root_cell_id>")
```

This follows `gmap_draft_generation.site_layout_rng`, which hashes
`seed:attempt:layout_variant:gmap-layout-0.6.1` for a bounded layout search.
`branch_attempt` selects a precomputed candidate without changing the map's
global `attempt` and without moving any other branch.

The event draw and the candidate geometry are two different draws. At runtime,
`draw(seed, attempt, event_index, "door-reroll", threshold_id, "candidate")`
selects the candidate index to try first; `branch_attempt` records the index
actually used. The offline pool generator created that candidate with the
`reroll_serial`/`branch_attempt` seed above. The runtime event index changes
which precomputed candidate is chosen, not the geometry inside the pool. Both are
deterministic and both are recorded.

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
- each accepted event's stored `after` values match a fresh keyed draw from
  `(seed, attempt, event_index, stream)` under the recorded layer version. This
  is the assertion that proves the event is actually seeded, not merely
  replayed from copied values.

The first implementation slice (§11, M1) is exactly this harness. It is
verifiable before any door, lamp or follower exists.

### 3.5 What the overlay stores

The overlay is keyed by stable IDs and stores only the live divergence from the
base:

```text
overlay = {
  cell_overrides:    cell_id -> {light?, wear?, surface_variants?, palette?,
                                 reverb?, floor_y?, geometry_revision?},
  door_overrides:    port_id -> {state, lock, reroll, follower_visibility},
  branch_overrides:  branch_epoch -> {root_door_id, cells, edges, retired_cell_ids},
  breadcrumbs:       marker_id -> {cell_id, port_id, sequence, kind, state},
  run:               {ended: bool, exit_cell: cell_id | null,
                      ended_at_event: int | null},
  state_hash:        "<64 hex>"
}
```

`run.ended` is set by the `run_end` event; the end card derives its seed,
rooms-visited, edit and re-roll counters from the log. It does not start a new
level or seed.

`geometry_revision` and `branch_epoch` matter for streaming: a retired cell ID
must never be served from a cache as if it still existed. The base map's cell
IDs stay stable for the base; new branch cells get fresh IDs, and the old ones
are tombstoned. Reusing `c07` for a new room would make breadcrumbs, save files
and streaming caches lie about identity.

---

## 4. Door re-roll (A)

### 4.1 In plain language

A door re-roll does **not** change the door. The door keeps its frame, its leaf,
its colour, its material and its position. It is not restyled, copied or
swapped for a different door.

What changes is the part of the maze **behind** the player. Once the player has
passed through the door and it is closed, the rooms on the side they came from
are replaced with a different layout. When the player opens that same door
again, it leads somewhere new. The door is the fixed point; the maze behind it
is the variable.

A short worked example:

1. The player walks out of a room, through door D, into a corridor. D closes
   behind them.
2. They continue into a side room, then decide to retrace their steps.
3. They open D from the corridor side. The room they came from is gone; a
   different set of rooms is there now.
4. The corridor, the door, and everything ahead of the player are exactly as
   they were. Only the route behind has changed.

The rest of this section defines that change precisely. "Behind" means the
connected component containing the player's previous cell after the door is
removed; it is not "the door" and it is not "the room ahead".

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
- `D` is the door port on the `B` side, its frame, and the shared boundary.
  They are pinned. The door is not restyled, copied or replaced.
- `A'` is a newly generated branch of the same walkable-cell count, attached at
  the same port. It is not a re-skin of `A`; it is a new layout drawn from a
  branch-scoped stream. It stays on the map's lattice and inside the same cell
  budget: a re-roll changes map state, it does not let a room enlarge or
  re-route the map.

This is stronger and more useful than re-rolling the room *ahead*: the player
turns around to go back and discovers that the route they came from no longer
exists. It also means the re-roll happens entirely out of sight, behind a
closed door, which is what makes it fair and technically safe. Re-rolling the
side ahead would change geometry the player may be looking at through the open
door, so it is not the v1 reading.

### 4.3 What is pinned

| Pinned item | Why |
|---|---|
| Current cell `B` | The player is standing in it; floor, walls and collision must not move |
| `D`'s port on the `B` side | The new branch attaches at the exact position, normal and compatibility type |
| The door frame and leaf geometry | The closed leaf is the occlusion that makes the swap invisible |
| Every cell on the `B` side | The re-roll is scoped to `A`; the rest of the map keeps its route, exit and identity |
| The exit cell | Fairness; a re-roll must never delete the way out |
| The spawn cell | Reset and save/restore identity; respawning inside a retired branch would be invalid |
| Library module cells and the landmark cell | Operator-approved, hash-pinned art; a re-roll must not orphan or move them |
| Every cell visible from `B` at commit time | Nothing the player can still see may change in view |
| Breadcrumb markers on the `B` side | The player's aid is not silently rewritten with the map |
| The player's position and velocity | No teleport, no fall, no collision pop |

"Visible" here includes open doorways, `closed_visible` void openings, and any
other line of sight the runtime can express. If the helper cannot prove `A` is
hidden, the re-roll waits. A conservative false negative is acceptable; a
visible pop is not.

The runtime threshold identity is `threshold_id`, the pinned `B`-side port, not
the base edge's `door_id` when that ID happens to point into the departed branch.
The base `door_id` is a hint and can become a retired port after a re-roll; the
overlay stores `threshold_id` and rebinds the edge. Do not use a base `door_id`
that points into `A` as a lookup key after `A` is retired.

### 4.4 Eligibility

A door is re-roll eligible only when all of these hold:

1. **It has a closable leaf.** Today a generated doorway is an opening:
   `shape_room_spec.doorway_records` writes `kind: "open"` for a direct edge and
   `closed_visible` otherwise; `shape_room_builder._add_doorway` builds the
   opening or a wall, not a swinging door. A library module's doorway is equally
   an authored opening. A door with no leaf cannot hide the swap, so it is not
   eligible until a leaf exists (§9.5).
2. **It is a bridge in the walkable graph.** Remove `D`; `A` must be a separate
   component from `B`. If a loop, diagonal link or elevation loop connects `A`
   to `B` by another route, cutting only `D` would not isolate `A`; the door is
   not eligible.
3. **The departed component is the right size.** The operator-confirmed v1
   range is `MIN_REROLL_CELLS = 3` to `MAX_REROLL_CELLS = 8` walkable cells. A
   one-cell closet is a room swap, not "an entirely different maze"; a whole-map
   rewrite is too large for the first runtime slice. Both constants are tuning,
   not measured.
4. **It contains no exit, spawn, module, landmark, diagonal link or
   elevation-loop edge.** These are the pinned identities above. A module inside
   `A` would be orphaned; an exit inside `A` would make the run unwinnable; a
   spawn inside `A` would break reset; a diagonal or loop inside `A` would make
   the replacement a different kind of branch than the v1 generator supports.
5. **It contains no visible cell.** `A` must be disjoint from
   `visible_cells(B)` at commit time. The closed leaf is expected to make this
   true; the check is the backstop.
6. **It is level in v1.** If the edge is a `ramp` or `drop`, the new branch would
   have to reproduce the vertical contract at the pinned boundary. That is a
   later extension. A level doorway keeps the attachment exact.
7. **It has re-roll budget.** `doors[].reroll.max_rerolls` (base policy) and a
   run-level cap both allow another re-roll. The operator-confirmed caps are
   `max_rerolls = 1` per door and `MAX_REROLLS_PER_RUN = 3`. One re-roll per
   threshold is the v1 limit because the candidate pool is precomputed against
   the base departed component; repeat re-rolls would need a deeper pool or a
   runtime generator. The caps are pacing guesses, not measured.
8. **The exit is still reachable from `B` without `A`.** The exit is static in
   v1 (§6.4, Q2), so this follows from condition 4; the validator checks it
   anyway, and that check becomes authoritative if a later version ever moves
   the exit.

If any condition fails, the door opens to the old `A` (or stays as it was) and
the attempt is logged as `door_reroll` / `rejected` with the failing code. A
failed re-roll is never a locked door with nowhere to go.

Conditions 1-4, 6 and the structural part of 8 are checked when the offline
candidate pool is built. Condition 5 (visibility), condition 7 (budget) and the
runtime half of 8 are checked at the open request. The pool is therefore a set
of structurally valid candidates; the runtime still decides whether this is the
moment to use one.

### 4.5 How the new branch is drawn

**Where the generator runs.** `gmap_build.py` and the shape-room generator are
offline Python. The walkthrough is GDScript and must not spawn Python in the
frame loop. The operator-confirmed coverage is bridge doors whose departed
component is 3-8 walkable cells, with the caps in §4.4 (Q7). For v1, precompute
a **branch candidate pool** at map build time: for each eligible door and
departure direction, generate `CANDIDATES_PER_DOOR`
(recommend 3) replacement branches with `(seed, attempt, threshold_id,
departed_root_cell_id, candidate_index)` (the event records `candidate_index` as
`branch_attempt`), validate them headlessly, and store the candidates plus their
hashes in a sidecar next to the map. The pool is keyed by
`(threshold_id, departed_root_cell_id)`; either side of a door can be the
departed side, but the tool generates only the directions that pass eligibility
against the base map. Because the pool is keyed to the base map's departed component, an
accepted re-roll spends that threshold (`max_rerolls = 1`); the door remains a
normal door afterwards. Repeat re-rolls are a later extension, not a v1 claim.
Runtime selects a candidate by `reroll_serial` and `branch_attempt`; if the pool
is exhausted or the selected candidate fails a runtime check, it tries the next,
then fails closed. This is a finite pool, not runtime generation. Runtime layer
edits can invalidate a candidate's floor or ceiling assumptions, so the open-time
check revalidates attachment and fairness before selecting one. The pool
manifest is canonical JSON sorted by door, departure direction and candidate
index; its hash is recorded with the map. Determinism is intentional: the same
seed, door and reveal reproduce the same candidate, while different seeds and
directions draw different ones. A true runtime generator would need a GDScript
port of the growth/layer logic or an async Python loading step; that is a later
project, not v1.

1. **Freeze the old branch.** Keep a snapshot of `A`'s cells, edges and room
   specs until the replacement passes validation. Do not despawn it yet.
2. **Select a precomputed candidate.** The pool was generated offline with the
   branch seed from §3.3. `target.branch_root` selects the departure direction;
   the pair (`reroll_serial`, `branch_attempt`) is the "new attempt" for this
   door, and `branch_attempt` is the candidate index. It does not bump the map's
   global `attempt`. If the pool is empty or exhausted, the event fails closed.
3. **Match the budget.** Preserve the walkable-cell count. Preserve the void
   count if `A` contained voids. Do not introduce a library module, a landmark,
   a diagonal site reservation, an elevation loop or an exit. Preserve the role
   mix where it matters: if `A` contained a `threshold` or `figure` cell, the
   replacement must contain one of the same role, subject to the no-adjacent-
   figures rule.
4. **Attach exactly.** The first new cell uses the pinned far-side port. A
   helper analogous to `gmap_grow.connect` is needed that consumes an existing
   port instead of creating both sides; the port on `B` is never rewritten.
5. **Stay level at the door.** The branch root floor equals `B`'s floor. Internal
   levels may vary in a later version, with a return route for every drop, as
   #201 requires. In v1 the attachment edge stays `level`.
6. **Assign layers per cell.** Use branch-scoped per-cell keys for light,
   wear, surface variants, reverb and elevation. Palette assignment is computed
   for new cells against the frozen anchor set; existing cells are never
   recomputed. The new branch should look like it belongs to the same map, but
   it must not inherit `A`'s exact lamp/wear pattern.
7. **Validate before commit.** Run the same tree, port, overlap, void, stage and
   directed-graph checks the generator uses, plus the fairness checks in §6.
   Do not accept a branch that only passes because it is disconnected.
8. **Commit atomically.** Replace `A` with `A'`, retire the old cell IDs,
   increment `reroll_serial`, set `doors[].reroll.draw_index` and
   `last_reroll_id`, write the event, then open the leaf. Rebuild the new
   branch's `doors[]` records and edge `door_id`; the `B`-side door record keeps
   its port, lock and frame, and only its overlay re-roll fields change. Any
   runtime pointer to a retired cell (previous cell, breadcrumb owner, focus)
   is reset to `B` or marked retired.

The new cells get fresh IDs continuing above the base map's highest ID, plus
branch metadata (`root_door_id`, `reroll_serial`, `replaced_cell_ids`). Port IDs
on the new cells are new as well. No retired ID is reused.

### 4.6 When it fires

The sequence is deliberately narrow:

1. **Crossing.** The player moves from `A` into `B` through `D`. The leaf closes
   and latches behind them. Log `door_lock`. The lock is a manual latch, not a
   keyed lock: the player can always open the leaf from the `B` side, so the
   lock cannot be the thing that removes the exit. A keyed lock would remove the
   edge until its condition is met, would need its own F0-F2 check, and is not
   part of the first slice.
2. **Occlusion.** The closed leaf makes `A` invisible. The old branch may remain
   loaded until the player is settled; it is not re-rolled yet.
3. **Open request.** The player interacts with `D` from `B`. Before the leaf
   moves, the controller resolves the re-roll:
   - if `A` is hidden and all eligibility checks pass, swap `A'` in and then
     open;
   - if `A` is somehow visible or a check fails, open to the old `A` and log a
     rejected event.
4. **Never while visible.** There is no timer and no "the player turns around
   and sees the change". The new branch is already in place when the leaf
   opens. If the leaf cannot occlude, the door is not eligible.

The re-roll does not fire on the first crossing, on a timer, or while the player
is inside `A`. It fires only on a later open from the `B` side. That is what
makes "it leads to an entirely different maze" a reveal rather than a pop.

### 4.7 Interaction with seeded room streaming (#162) and unloading

#162 is deferred and blocked on the room-library and workflow gates. The current
walkthrough instances every cell at load; the accepted #156 streamer is a
finite, bounded regression fixture. This proposal does not pretend #162 exists.

For the first runtime slice, branch replacement is a local, bounded form of
unloading:

- The controller removes the old branch's room nodes only after the closed leaf
  hides them, and only after `A'` has passed validation.
- The new branch is built from the base map plus the overlay and the precomputed
  candidate pool, not from a cache keyed only by `cell_id`.
- If #162 later streams cells, its cache key must include the base map hash,
  `branch_epoch` and `content_revision`. A retired cell ID must be a cache miss,
  never a stale room.
- Unload and reload must not change the result: a cell's base layers still come
  from its per-cell draws, and its runtime overrides still come from the event
  log. Loading order is not part of the draw.
- The #156 finite streamed walkthrough remains a regression fixture with
  mutations off, so this work cannot silently change its behaviour.

### 4.8 What the player experiences

The intended beat is: step through, hear the leaf close and latch, walk on,
decide to go back, open the door, and find a corridor that was not there. The
old route is gone; the exit is still ahead somewhere. Because the exit is fixed
(§6.4), if the player was walking toward it, the behind side is the spawn side
and the re-roll is safe. If the player wanders into a dead end, the behind side
contains the exit and the door is not eligible, so the mechanic never strands
them.

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
| `door_reroll` | Replace the departed branch | §4 | High | Structural; §6 | M5/M6 |
| `breadcrumb_tamper` | Move/remove a marker | `breadcrumbs`; §7 | Low | Fairness of the aid, not the exit | Later (not v1) |

Explicitly **not** in the menu: changing a cell envelope or shape (that is a
re-roll), moving a library module or the landmark (operator-approved, frozen),
changing the static exit (v1; §6.4), or changing the exit without the fairness
check. `breadcrumb_tamper` is listed only as later work; v1 breadcrumbs are
honest (§7, Q5). The landmark is a map-level figure, not a prop; if a prop
system arrives, it moves small objects inside a room, never the landmark cell.

`door_lock` in v1 is a manual latch used for occlusion and dread; it does not
remove the edge, because the player can always open it. A future keyed or
impassable lock is the only door edit that can affect F1/F2, and it must pass
the fairness check before it is applied.

Target scope matters. Generated shape rooms can receive every class in the
table. A library module's scene is hash-pinned and its light, wear and palette
are baked into that scene, so the follower may give it a reverb flip or a door
overlay (a runtime prop at the port) but not a lamp, wear or palette rewrite. A
re-roll never contains a module. This is a v1 limitation, not a reason to edit a
library scene.

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
dread. The counter is monotonic: a re-roll may retire cells, but it does not
reduce the escalation already earned. The trigger sequence is logged, so replay
consumes it instead of re-simulating movement.

Proposed curve (all numbers are guesses for the operator walk). `next_edit`
is scheduled as `last_edit + interval(last_edit)`, where `interval` is read from
the row that contains the `last_edit` count:

| Distinct visited cells | Edit cadence | Classes allowed | Notes |
|---|---|---|---|
| 0-4 | None | None | Establish the base maze; first cue may occur on the 5th |
| 5-9 | One edit per 4 newly visited cells | `lamp_state`, `lamp_flicker`, `reverb` | Cheap, reversible, no graph effect |
| 10-14 | One per 3 newly visited cells | Add `wear`, `surface_variant`, `door_lock` | The first "did that change?" beat |
| 15-24 | One per 2 newly visited cells | Add `palette`, `dark_wing` | Visible wear and dark wings |
| 25+ | One per 2 newly visited cells; at most one structural edit per 6 newly visited cells | Add `door_reroll` within the operator-confirmed caps; `elevation` only if later approved | `MAX_REROLLS_PER_RUN = 3`; `max_rerolls = 1` per door |

Additional rules:

- At most one edit per room entry; never two edits in the same entry.
- Never edit the same cell twice in a row.
- Never edit the cell the player is in, the exit cell, the spawn cell, or a
  visible cell.
- After a `door_reroll`, grant a quiet period of at least 3 newly visited cells
  before the next follower edit, so the reveal has room to breathe.
- If no eligible target exists, skip the beat and do not force an edit. Forcing
  one produces the "random" feeling the operator wants to avoid.
- The first edit should be a lamp or a reverb, not a door. The player needs to
  learn that small things change before the maze asks them to distrust a door.

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
| F4 | **Nothing visible changes.** The edited cell or branch is outside `visible_cells(player_cell)` at commit. | Visibility helper |
| F5 | **Base identity unchanged.** The committed map hash, seed, attempt, catalog snapshot and pins are the same before and after. | SHA-256 verification |
| F6 | **Replay agrees.** Re-applying the log produces the same state hash and the same F0-F5 outcomes. | Replay harness |

F1 is the operator's stated rule. F2 is the stronger version that prevents the
"the exit is reachable, but I walked into a one-way wing and cannot get back to
it" soft-lock. F0 is the strictest form: in v1 every door is openable and every
drop has a return route, so the whole graph should stay strongly connected.
The mutation validator therefore requires F0, not just F1. F1 and F2 remain the
operator-facing statement and the checks that stay meaningful if a later keyed
lock or moving exit makes the graph intentionally one-way; they are checked on
every event as well. The v1 exit is static (§6.4), so F1/F2 have a fixed target;
a moving exit is later and out of scope for this proposal.

### 6.3 Reusing the #201 validator

#201 implemented `strongly_connected` over the directed graph and used it to
keep every one-way drop returnable. The same function validates a re-roll
candidate branch:

1. Build the candidate graph from the surviving `B` side plus `A'`.
2. Require `strongly_connected(all_walkable_ids, candidate_edges)` for v1. This
   catches a branch that is reachable only one way and has no return.
3. Apply the current door and elevation states (drops are one-way; a future
   impassable lock removes its edge) and require F1 and F2 from the player's
   current cell. In v1 the door states do not remove edges, so this is a
   redundancy check on the F0 result.
4. If the candidate fails, try the next `branch_attempt`; after the cap, reject
   and restore `A`.

The #201 report's negative case (a ramp changed to a one-way drop without a
return route, rejected with `elevation_graph_not_strongly_connected`) is the
template for the negative tests here. A re-roll that removes the only return
route must fail with a named code, not an exception.

`strongly_connected` lives in Python (`gmap_elevation.py`); the runtime is
GDScript. V1 therefore needs a small GDScript port (`maze_graph.gd`) or a
precomputed pass plus a live BFS. The Python version remains the offline
authority for pool generation; the GDScript version is the runtime F0-F2 check.
They must agree on a shared edge-list fixture, including a drop with and without
a return route. This is a bounded port of one function, not a second generator.

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
- **Placement.** At a leaf/figure cell chosen deterministically from the seed.
  The exit cell is pinned: it is excluded from every re-roll and follower edit,
  never part of a departed component, and never the spawn cell. The threshold
  door is not a re-roll door and is not eligible for lock-behind.
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
  would remove the exit route is rejected before commit (F1/F2); the exit cell
  is never retired. The exit is the stable "out" the player runs toward while
  the path behind them changes.

### 6.5 Repair rules

- An edit that fails F0-F4 is rejected before commit; the log records the
  failing code.
- A re-roll that fails after `A` has been removed from the runtime view restores
  the snapshot of `A`; the old branch is never lost.
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
the maze into a minimap: a gap or an unreachable marker is evidence that the
maze changed. Tampering is not part of v1.

This is later work: it depends on the re-roll (markers in a retired branch must
be retired) and on the follower edit visibility gate. It should not be in the
first implementation slice.

### 7.3 Honesty and tampering (decided for v1)

The operator decided that breadcrumbs are **honest in v1**. An unreliable or
tampering mode is liked in principle but is too confusing for the initial
version, so it stays later work and is not scheduled here.

If a tamper mode is ever built, it must follow these rules and needs explicit
operator approval:

- **Honest (v1).** The trail always reflects the player's true path. It reduces
  dread but makes the re-roll legible: a gap in the trail is evidence that the
  maze changed.
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
in a re-rolled branch is retired with the branch; a marker at the door on the
`B` side stays.

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
| `door_reopen` | A different, wrong-sounding version of the click plus a low tail | When the re-roll opens | The reveal; "that is not the door I came through" |
| `reverb_flip` | No dedicated sound; the room tone changes on the next footstep | On re-entry after a wet/dry edit | The room itself is the tell |
| `lamp_buzz` | Optional low hum from a procedural oscillator, tied to the flicker | While a flickering lamp is visible | Reinforces the light edit; asset work |
| `distant_collapse` | Optional low rumble, no direction | Rare, during escalation | Scale and dread; asset work |

The first four can be built from existing samples. The last three are future
asset work and are not part of this proposal's implementation.

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
- The `door_close` and `lock_click` are mandatory; they are the mechanic's
  contract. The other cues are optional and should not be on every edit, or the
  player learns the pattern and stops being unsettled.
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
make the whole-document pass use those functions. A branch re-roll may recompute
the whole new branch, but never the surviving `B` side.

Static exit selection (§6.4, Q1-Q2) must follow the same discipline: a
seed-keyed draw over eligible cells, not a sequential pass. It must not consume
draws from an existing layer stream or shift any existing cell's value. A map
can carry the selected exit in a new layer version, or derive it from the seed
at load for maps generated before that version.

Branch candidates are the exception to "compute at runtime": they are generated
offline because the branch geometry is Python. The pool is a versioned sidecar
with per-candidate hashes; the runtime selects and applies a candidate, and
never runs the growth/layer generator. If the pool is regenerated, its hashes
change and old overlay logs are checked against the recorded pool hash, not
silently reinterpreted.

### 9.2 Layers mutable at runtime, not baked at generation

The committed map is the base; the runtime overlay is the state. This is the
same rule as #204's reverb and #212 §6.3:

- scalar flags: node metadata, like `reverb_enabled`;
- materials and lamps: runtime setters on the instanced room;
- geometry (elevation, props, branch replacement): rebuild the room node from a
  derived spec; never edit the committed map or shape-room JSON;
- branch replacement: the derived spec comes from the precomputed candidate
  pool, whose file hash is part of the overlay identity;
- library modules: reverb and door overlays only; their light, wear and palette
  are baked into hash-pinned scenes and are not rebuilt or rewritten.

A mutation must leave `sha256(base_map.json)` unchanged. The test is trivial
and should be in every mutation issue.

### 9.3 Stable identity and branch epochs

- Base cell IDs and port IDs never change.
- A re-roll retires the old cell IDs and creates new ones; it never reuses an
  ID.
- A threshold's runtime identity is its pinned current-side port and a stable
  `threshold_id`, not a base `door_id` that may point into the retired side.
  Rebind the edge and tombstone the retired port.
- The overlay carries `branch_epoch`, `content_revision` and the selected
  `candidate_id`; a streamed cache key includes them.
- Breadcrumbs, save files and telemetry reference the IDs; a retired ID is
  reported as retired, not as an empty room.
- A queued follower edit that targets a retired cell is dropped, never retargeted
  silently to a cell that happens to reuse the space.
- Retired IDs are removed from the live visited set; the monotonic escalation
  counter is not reduced (see §5.4).
- The door's `reroll.draw_index` and `last_reroll_id` are the audit trail for
  how many times a threshold has changed.

### 9.4 Runtime ownership

One `MazeMutationController` per walkthrough:

- owns the event log, overlay, cadence counters and state hash;
- receives `room_entered`, `door_opened`, `door_closed`, `exit_entered`,
  `cell_unloaded` and `save_restore` triggers as signals; appends the trigger
  record before deciding what, if anything, to mutate; on `exit_entered` it
  emits `run_end`, stops mutations and leaves the end card to the UI;
- calls the graph/visibility/fairness helpers before committing;
- asks the assembly to apply cell overrides or replace a branch;
- never edits `godot_walk/scripts/player.gd` (frozen) and never writes into the
  committed map document; any runtime document it builds is a copy.

The assembly remains the renderer/physics owner. It exposes narrow methods:
`set_room_reverb`, future `set_cell_light`, `set_cell_surface`,
`replace_branch`, and the visibility query. Mutation logic does not leak into
`walk_player.gd`.

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
polish item, because the leaf is what makes the swap invisible.

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
- The Python validator and the GDScript runtime validator share a fixture: the
  same cell list and directed edge list must produce the same result in both,
  including the #201 negative case. The Python one validates the pool offline;
  the GDScript one validates the live graph.

### 9.7 Streaming, unloading and save/restore

- #162 is deferred; do not make mutation depend on it. The first slice can
  despawn/respawn branch nodes locally while the door is closed.
- When #162 lands, load by `(base_map_id, base_map_sha256, candidate_pool_sha256,
  branch_epoch, content_revision, cell_id)` and rebuild from base + overlay.
  Never cache a room by `cell_id` alone.
- Unload the old branch only after the new branch validates, and only when it is
  hidden. Keep the old snapshot until commit.
- Save/restore stores the base map hash plus the event log, including trigger
  records, not a mutated map. The cadence is reconstructed from the trigger
  sequence. Pending (not yet applied) edits are ephemeral; losing one on save is
  acceptable because it has not happened.
- The #156 finite streamer remains a regression fixture with mutation disabled.

### 9.8 Versioning and frozen files

- The overlay/event schema is a new record; do not overload
  `generative_map.schema.json` or `generative_map_v2.schema.json` in place.
- The base map's `mutation.classes` enum currently lists `door`, `reverb`,
  `palette`, `light`, `breadcrumb`
  (`generative_map_v2.schema.json`, `$defs.mutation`). The follower menu adds
  `surface`, `elevation` and `prop`; those belong in a new overlay schema
  version, not in a silent enum extension.
- A base-generator change is a new `gmap` version. A mutation never changes the
  generator version of an existing map.
- The static exit is a new layer/field version, not a mutation and not an
  overload of an existing schema. Existing maps keep their bytes; the runtime
  derives the same exit from the seed until a map is regenerated with the layer.
- The candidate-pool tool is a sidecar producer, not a change to the base map
  generator. Reusing the generator functions without changing their output keeps
  the base `gmap` version; changing a base draw would require a new version.
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
- No re-roll result in the committed map. The map is the base; the branch
  replacement is overlay state.
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
the v1 issue list. See §6.4.

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

### Q8. Does the player ever see the follower? — decided

Never in v1. Its presence is audio-only and occasional. The operator described
the long-term direction as an almost 4-dimensional entity that creeps in by
distorting space and time; that is a note for later, not a design for this
proposal or its issue list. See §5.6.

### Questions that remain open

These are not decided by the operator and do not block the first issue:

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
  question.

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
| M1 | Mutation overlay core and replay | Event record, trigger and mutation records, keyed draw, fold, state hash, JSONL log, headless replay; run counters derivable from the log | Same base + log => same overlay; trigger-only cadence reconstructs; reorder/tamper/base-mismatch rejected; map hash unchanged; no runtime | Approved #209 |
| M2 | Follower edit: lamp state and flicker | Per-cell light override, visibility gate, cadence counter; first visible edit | Leave cell, edit applies, re-enter sees new lamp; no other cell shifts; map hash unchanged; capture | M1 |
| M3 | Exit threshold and run end card | Static seed-keyed exit selection; bright threshold door and original test-chamber room treatment; crossing ends the run once; end card shows seed, rooms visited, edits and re-rolls; no next-seed or level progression | Same seed => same exit cell; exit excluded from re-roll/edit targets; one `run_end` event and one end card per run; counters match the log; no progression action exists; map bytes unchanged; capture for operator style review | M1 |
| M4 | Door state and lock-behind | Overlay `doors[]`, procedural leaf for generated rooms, close/latch on crossing, manual open; no re-roll; exit threshold is not lock-behind eligible | Headless cross/lock/open; exit reachable; library doorways skipped; save/restore; capture | M1, M3 |
| M5 | Door re-roll: offline branch pool and headless validation | Generate and validate a candidate pool per eligible door at map build time; operator-confirmed bridge doors with a 3-8 cell departed component; `max_rerolls = 1` per door and `MAX_REROLLS_PER_RUN = 3`; sidecar with hashes; no runtime generation | Pool deterministic; every candidate attaches and preserves F0/F1; invalid omitted; no fit fails closed; exit/spawn/module/landmark excluded; `strongly_connected` negative case | M1, M3, M4 |
| M6 | Door re-roll: runtime swap from the pool | Select by `reroll_serial`/`branch_attempt`; enforce 1/door and 3/run; swap while closed/hidden; despawn old branch; build new branch; GDScript F0-F2 check | Headless door-open reveal; no pop in captures; old IDs retired; GDScript and Python graph fixtures agree; map hash and pool hash unchanged; operator walk pending | M5 |
| M7 | Door re-roll: save, restore and cache | Persist base hash + pool hash + event log; restore across reloads; overlay-aware cache key; #156 fixture unchanged | Save/reload at the door produces the same overlay; retired IDs miss the cache; #156 regression; map hash unchanged | M6 |
| M8 | Follower edits: reverb, wear and variant | Reverb flip (existing setter), wear/variant overrides, palette-compatible validation | Per-cell isolation; map hash unchanged; old cells unchanged; capture; operator walk/listen | M1, M2 |
| M9 | Follower presence cues | `Follower` bus, 3D cue pool, distant steps, door/lock sounds, cue events; audio-only, occasional, never visible | Cue timing/distance/volume checks; no visible follower node; no audio assertions; operator listen pending | M1, M2 |
| M10 | Breadcrumb mode (later) | Markers, pause toggle, honest trail, retirement on re-roll; default off; toggle available from the start; no tamper mode in v1 | Drop/retire/replay; map hash unchanged; re-roll truncates trail; toggle works from the start; markers are honest; operator walk | M6, M9 |
| M11 | Dark-wing growth (later) | Add one contiguous visited cell to the dark wing; update its light and surface | Light/surface consistency; no non-wing cell shifts; map hash unchanged; capture | M2, M8 |
| M12 | Elevation edits (later) | Change one visited branch's floor/ramp/drop; rebuild geometry and collision | F0-F3 checks; return route for every drop; no visible pop; capture | M7, M8 |
| M13 | Prop edits (later) | Move or rotate a small prop in a generated room; needs a prop system first | Prop overlay replay; no graph effect; no visible pop; capture | M8 |
| M14 | Escalation tuning and evidence | Tune cadence constants, collect replay logs and captures, operator walk; verify end-card counters and no progression | A full run with A and B; metrics recorded; no new mechanics | M2-M13 |

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
- M5, M6 and M7 split the re-roll into the offline candidate pool, the runtime
  swap, and the save/restore/cache contract. Each is a full loop run; combining
  them would be too large.
- M8 adds the layers that are cheap metadata but have visual/audio tells.
- M9 is audio; agents can verify event wiring, not the mix.
- M10, M11, M12 and M13 are explicitly later; they should not block the first
  A/B slice.
- M14 is a tuning/evidence run, not a feature. It needs the operator's walk and
  listen.

### 11.1 First four issues in detail

1. **M1 — Mutation overlay core and replay.** Add `maze_mutation` with trigger
   and mutation records, `draw_for_event`, `fold_events`, `state_hash`, JSONL
   read/append, cadence reconstruction from triggers, and a replay CLI. Tests
   use a committed gmap-0.13.0 map and synthetic logs. Assertions: deterministic
   state hash; event order matters; trigger-only cadence matches; rejected events
   are inert; base hash mismatch rejected; no file writes to the map. This is the
   only issue that can start immediately after approval.
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
   The end card shows seed, rooms visited, edits and re-rolls from the log; it
   offers no next level or new seed. Check that the same seed selects the same
   exit, the exit is excluded from re-rolls and edits, crossing fires `run_end`
   once, the counters match the log, and no progression action exists. Capture
   the threshold for operator visual review. Original materials only; do not
   copy or reference a third-party asset.
4. **M4 — Door state and lock-behind.** Add the leaf geometry as a new
   shape-room version (or a runtime prop for library ports), the overlay door
   state, close/latch on crossing, and manual open. No re-roll. Check that a
   generated door closes and latches, that the player can open it from the
   current side, that the exit remains reachable, and that a library doorway
   without a leaf is skipped rather than silently locked. Capture the closed and
   open states.

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

---

## 12. Scope guard

- This is a revised proposal, not an approval. The operator decisions in §10 are
  recorded; the operator still reviews this revision before any implementation
  issue is filed.
- No code, schema, generator, map, shape-room or asset change is part of #209.
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
| `godot_walk/scripts/gmap_build.py` | Offline map assembly and versioned layer wiring; where a candidate pool tool belongs |
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

### A.3 Checklist against the eight questions

| #209 question | Where answered |
|---|---|
| 1. Mutation model, seeded event log, `attempt` and streams | §3 |
| 2. Door re-roll: part regenerated, pins, new attempt, firing, streaming | §4 |
| 3. Follower edits: menu, out-of-sight rule, cadence, follower existence | §5 |
| 4. Fairness invariant and directed validator; exit and win decided | §6, §10 |
| 5. Breadcrumb mode: what it is, honesty, toggle, later work | §7, §10 |
| 6. Sound and feel; cues, reverb flips, pacing | §8 |
| 7. Architecture constraints for the backlog | §9 |
| 8. Proposed implementation issues, ordered and sized | §11 |
