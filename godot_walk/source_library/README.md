# Per-source room library

`data/videos/` remains the local drop folder. Registration hashes and probes
each direct child in place; it never moves, rewrites, stages, or commits source
media. The central index contains one entry per content hash. IDs use the first
16 SHA-256 hex digits, while the full digest remains authoritative and is
checked for collisions.

Each `sources/<source_id>/source_manifest.json` is an immutable intake
snapshot. After catalog admission, create a versioned successor such as
`source_manifest-v2.json`; update the central index to that snapshot and keep
the earlier manifests and their hashes intact. A successor records the exact
adaptation and decision artifacts. Its `supersedes` link preserves the prior
manifest chain. Existing events remain bound to the hash of the manifest
version active when they were written; workers accept those verified ancestor
hashes, while new events use the current index hash. `events.jsonl` remains
append-only and records stage receipts, operator checkpoints, and Hunyuan
attempts. Room outputs belong under `sources/<source_id>/rooms/<room_id>/`;
directly decoded frames and Hunyuan attempt outputs use their corresponding
source-local folders. A source can have zero or more rooms. These records make
no claim about room count, hidden geometry, or connectivity.

The initial registration command is CPU-only:

```bash
python3 godot_walk/scripts/register_video_sources.py inventory
python3 godot_walk/scripts/register_video_sources.py validate
python3 godot_walk/scripts/build_source_intake_contact_sheet.py \
  --output godot_walk/evidence/<fresh-intake-evidence-folder>
```

The contact sheet uses scaled preview frames only. A panorama seed must be a
separate full-resolution frame decoded directly from the selected source video
after the operator approves source suitability and the exact frame.

New sources start with pending suitability and seed decisions. Every Hunyuan
attempt is recorded against that source and consumes one of its three allowed
invocations. The operator reviews each result; workers cannot select a winner,
choose a manual fallback, accept a room, or admit a catalog module. CPU work can
be split across distinct source IDs; GPU inference and capture require the
existing GPU/RAM guard and the source library's exclusive GPU-job lock.
If source review changes, append a superseding decision; earlier review events
remain intact and the latest decision controls which stages may proceed.

Accepting a room normally completes that source's current panorama loop. For a
separately reviewed second room from the same video, select a new direct-source
seed after the accepted-room event. If exactly one source invocation remains
and no feedback or stop condition is pending, the operator may authorize one
`hunyuan_room_attempt_authorized` event bound to a room ID, the next attempt ID,
and the full seed record. This does not reset or extend the source cap. It
enables only that panorama; the result waits for operator review before room
authoring or catalog admission.

The historical `room_large.mp4` record links the accepted #163 adaptation and
review without changing them. It records all four old stopped-before-panorama
attempts as historical and over the new three-attempt limit, so registration
does not authorize another run. The historical `corridor_corner.mp4` record
links #165's accepted manual adaptation and records zero Hunyuan invocations in
that workflow. Neither historical approval is reopened.

After the operator chooses a source, the staged CPU path is:

```bash
python3 godot_walk/scripts/source_ingestion_runner.py status <source_id>
python3 godot_walk/scripts/source_ingestion_runner.py review-source <source_id> \
  --decision proceed_with_limitations --reason "<operator rationale>"
python3 godot_walk/scripts/source_ingestion_runner.py extract-frames <source_id> \
  --run-id seed-candidates-001 --indices <zero-based-frame-indices>
python3 godot_walk/scripts/source_ingestion_runner.py select-seed <source_id> \
  --frame-id <frame_id> --path <source-local-frame-path>
```

`status` is the worker handoff packet: it returns the exact source and manifest
hashes, the source-scoped output root, current gate state, and the next allowed
stage names. Give a worker one source ID and its `status` output; stages reject
unsafe IDs, stale hashes, cross-source frames, conflicting source claims, and
existing output paths. Each worker chooses a fresh run ID for extraction, and
the Hunyuan runner generates its own unique attempt run ID.

Only a selected full-resolution direct source frame unlocks one panorama call:

```bash
python3 godot_walk/scripts/run_source_hunyuan.py <source_id> \
  --prompt "<reviewed source-specific prompt>" --timeout-seconds 300
```

The panorama runner obtains the shared lock, runs the existing GPU/RAM guard,
records guard/config/resource/output receipts, applies a timeout, and records
exactly one invocation. The `feedback` subcommand records an operator judgment
before another call. Two consecutive no-improvement judgments, repeated
failures without a plausible next step, a guard block, or the three-call cap
stop further inference. A separate `manual-fallback` subcommand requires the
operator to choose manual adaptation or reject the source. No step chooses a
winner or admits a room.

After operator approval and catalog admission, link the immutable candidate
and decision into a new source-manifest version:

```bash
python3 godot_walk/scripts/register_source_room.py <source_id> \
  --adaptation godot_walk/source_library/sources/<source_id>/rooms/<room_id>/adaptation.json \
  --decision godot_walk/source_library/sources/<source_id>/rooms/<room_id>/catalog_admission_decision.json
```

The command validates the candidate-bound decision, source-video identity,
catalog module, and frozen catalog snapshot. It refuses to overwrite a
manifest version and leaves the intake manifest and earlier decisions intact.

## Reconciling decision files with the ledger

Every `operator_review.json`, `catalog_admission_decision.json` and
`adaptation_*accepted*.json` in a source's `rooms/*/` folder (and every
`decision_path` in its latest manifest) must be cited by at least one event, or
`register_video_sources.py validate` fails. If a decision file was written
without an event, backfill it:

```bash
python3 godot_walk/scripts/source_ingestion_runner.py reconcile-historical <source_id>
```

This appends `historical_decision_reconciled` events whose `occurred_at_utc` is
the reconciliation time (never backdated) and whose `payload.reconciles` cites
the artifact path, its SHA-256, the original decision timestamp found in the
file, and the issue number. A file with no decision timestamp of its own (and no
hash-verified operator record to inherit one from), or that is not an
acceptance, gets a `historical_decision_reconciliation_deferred` event instead:
it is linked in the ledger but not claimed as an operator decision. Reruns skip
files that are already cited, and a reconciled file whose bytes later change
fails validation. Reconciliation creates or reopens no approval.

## Module metadata and integration proposals (after catalog admission)

Four runner stages feed an admitted room into the proposal space. All are
CPU-only, make no model calls, and never edit a module, the catalog, a snapshot
or a map. Each appends one event under the normal source lock.

```bash
R=godot_walk/scripts/source_ingestion_runner.py
python3 $R derive-module-metadata <source_id> --room-id <room_id>
python3 $R accept-module-metadata <source_id> --room-id <room_id> --form-role ground|figure \
  --rarity-tier 0-3 --apollonian 0-1 --dionysian 0-1 --style-tag T \
  --unique-detail "<frame_path>::<text>" --surface-salience "<text>" --reason "<text>"   # operator
python3 $R propose-integrations <source_id> --room-id <room_id> --map <generative_map.json>
python3 $R decide-integration <source_id> --proposal <path> --choice accept|reject|keep_standalone --reason "<text>"  # operator
python3 godot_walk/scripts/module_poetics.py accept-kit --module-id <id> ...same flags...  # kit modules, operator
```

- `derive-module-metadata` needs the room in the newest library index for the
  current catalog version and an admission event; it links the mechanical
  `module_poetics_v1.json` (`module_metadata_derived`). Reruns add nothing.
- `accept-module-metadata` writes `module_poetics_v2.json` (v1 plus filled
  poetics, `supersedes` v1) and logs `module_metadata_accepted`. A `figure`
  needs at least one `--unique-detail`; frame paths must exist under the
  source's `frames/`. v1 is never modified.
- `propose-integrations` fits the module (yaw 0/90/180/270, 1 m lattice
  translations) into each non-void map cell and writes up to five
  `integration_proposals/<map_id>/<proposal_id>.json` records (or one
  `keep_standalone`), then logs `integration_proposal_recorded`. Scores are
  mechanical, not visual judgements.
- `decide-integration` logs `integration_proposal_decided` for a recorded
  proposal only.

`register_video_sources.py validate` fails when a `module_poetics_v2.json` or
an `integration_proposals/**/*.json` file has no citing event with its exact
hash. `status` lists these stages in `next_worker_actions` once their
preconditions hold.

## Picture-set sources

`data/pictures/<set>/` is the local drop folder for a direct picture set. Each
image is hashed and probed in place; registration never copies, resizes or
edits it. New picture-set manifests use `source-manifest` schema v3 and carry
`source_kind: picture_set`, `content.picture_set[]`, `capture`, `scale`,
`lighting` and the pending source review. The index moves to schema v2 when a
picture set is present; old video entries stay valid.

```bash
P=godot_walk/scripts/register_picture_sources.py
python3 $P inventory
python3 $P register data/pictures/<set>
python3 $P validate

R=godot_walk/scripts/source_ingestion_runner.py
python3 $R status picture-set-<16 hex>
python3 $R review-source picture-set-<16 hex> \
  --decision proceed_with_limitations --reason "<operator rationale>"
python3 $R import-images picture-set-<16 hex> --run-id seed-candidates-001
python3 $R select-image picture-set-<16 hex> \
  --image-id img_0001 \
  --path godot_walk/source_library/sources/picture-set-<16 hex>/images/seed-candidates-001/<imported image file>
```

`import-images` copies each source image byte-for-byte into the source folder
and writes `import_manifest.json` with the image-set hash, every per-image
hash and the image dimensions. `select-image` accepts only an imported image
from that receipt. A picture seed has an `image_id` and capture index and no
frame timestamp; none is invented. Hunyuan and Panogen guard receipts bind
`source_image_set_sha256` plus `seed_image_id` instead of
`source_video_sha256` and a video frame ID. Everything downstream — accepted
poetics, module profile, palette, acoustics, map and assembly — is the same
pipeline.

For a CPU-only end-to-end check, generate a deterministic synthetic set first:

```bash
python3 godot_walk/scripts/generate_picture_set_fixture.py \
  --output data/pictures/synthetic-picture-set-221
python3 godot_walk/scripts/register_picture_sources.py register \
  data/pictures/synthetic-picture-set-221
```

A real operator-supplied picture set and its seed review remain the human step;
the synthetic set only proves the intake wiring.
