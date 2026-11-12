# Issue 222 — Template T9: ingest the #195 video batch

Date: 2026-11-12
Batch: `issue-195` (`godot_walk/source_library/batches/issue-195.json`)
Template: `generation-template-0.1.0`, proposal sections 5.1–5.4 and 8
Sources: #174–#180 (seven videos). The operator direction for this run names
#174–#180 only; #171–#173 remain outside this batch even though the #195
umbrella lists #171–#180.

## What changed

- Each batch source now has a versioned schema-v3 source manifest:
  `source_manifest-v3.json`. Sources that only had the original v1 record
  received a `source_manifest-v2.json` bridge first, so the append-only chain
  reaches v3 one version at a time. Original v1 records are byte-identical.
- The source-library index points at the v3 manifests (`index_version` 23).
- Each source received one `source_manifest_v3_recorded` event. The event
  records the manifest hash, the predecessor, the template version and that
  `registration_accepted` and `scale_calibrated` remain false. No operator
  decision, model call or catalog admission is created.
- New verifier: `godot_walk/scripts/template_batch_ingest.py` (`status`,
  `upgrade`, `check`) with `template_manifest_v3.py` and
  `template_module_contract.py`.
- Existing consumers now read both manifest shapes through
  `video_source_library.manifest_video_content`: source status and frame
  selection, seed review, the intake contact sheet and room admission. The
  contact sheet also skips picture-set sources instead of assuming a video.
- Existing 11 library modules were not re-ingested. No module scene, poetics,
  profile, acoustics, surface, metadata, map, shape room or frozen catalog file
  changed.

## Batch contract state

| Issue | Source ID | Latest manifest | Source review | Seed | Admitted module |
|---:|---|---|---|---|---|
| 174 | `video-d92fc1fa764aa3a2` | v3 | pending operator | none | none |
| 175 | `video-102caf53423018b7` | v3 | pending operator | none | none |
| 176 | `video-2671b32f256a4ee7` | v3 | pending operator | none | none |
| 177 | `video-61b91dbeb9026dc7` | v3 | pending operator | none | none |
| 178 | `video-f657e9bc27813df8` | v3 | pending operator | none | none |
| 179 | `video-ef0ec21cd4ae7b26` | v3 | pending operator | none | none |
| 180 | `video-51abd379f94b8f84` | v3 | pending operator | none | none |

The batch currently admits zero new modules. That is the operator gate, not a
worker failure: each source still needs a suitability decision, a selected
direct-source seed, an authorized Hunyuan run, a reviewed room candidate and
catalog admission. #174 is 636x480, below the 1080p capture requirement, so a
logged reject or `proceed_with_limitations` is a valid operator outcome. When a
module is admitted, `template_batch_ingest.py check`
requires its source manifest v3, module profile, `module_acoustics` v0.2.0
record and surface/palette descriptor; it also checks the consolidated module
metadata record.

The historical #163 (`room_large.mp4`) and #165 (`corridor_corner.mp4`)
adaptations are preserved in the v3 manifests unchanged. Their approvals were
not reopened, and their existing library modules are part of the existing 11
modules, not new batch modules.

## Checks run

```bash
python3 godot_walk/scripts/template_batch_ingest.py status
python3 godot_walk/scripts/template_batch_ingest.py upgrade
python3 godot_walk/scripts/template_batch_ingest.py check
python3 godot_walk/scripts/register_video_sources.py validate
python3 godot_walk/scripts/template_validate.py
python3 -m pytest -q godot_walk/scripts
for seed in 1 2 3 32 279; do
  godot4 --headless --path godot_walk \
    --script res://scripts/test_issue183_shape_rooms.gd -- \
    --map=res://room_catalog/generative_maps/gmap-${seed}-gmap-0.13.0.json \
    --rooms=res://room_catalog/shape_rooms/gmap-${seed}-gmap-0.13.0/index.json
done
godot4 --headless --path godot_walk --script res://scripts/test_library_rooms.gd
```

- `python3 godot_walk/scripts/template_batch_ingest.py check` — valid; 7 batch
  sources, 0 new modules, 0 errors:

  ```json
  {
    "valid": true,
    "batch_id": "issue-195",
    "errors": []
  }
  ```
- `python3 godot_walk/scripts/register_video_sources.py validate` — valid,
  13 registered sources.
- `python3 godot_walk/scripts/template_validate.py` — valid; 30 source
  manifests, 22 module profiles, 68 generative maps, 0 errors.
- Full Python suite: `python3 -m pytest -q godot_walk/scripts` — 1,291 passed,
  5 skipped, 58 subtests passed in 965.20 seconds (exit 0).
- Godot headless walkthrough for `gmap-0.13.0` seeds 1, 2, 3, 32 and 279 on
  Godot 4.6.3.stable.official: exit 0, `ISSUE183_SHAPE_ROOMS: PASS` for every
  seed.
- Godot headless library-room contract: exit 0,
  `LIBRARY_ROOM_CONTRACT: PASS`.
- `template_batch_ingest.py status` committed as
  `godot_walk/evidence/2026-11-12-issue-222/batch_status.json`.

## Operator steps pending

1. Source suitability decision for each of #174–#180 (`review-source`).
2. Frame extraction and seed selection after that decision; seed approval is
   the operator's.
3. Hunyuan authorization with an explicit per-source budget and the existing
   three-attempt cap.
4. Room candidate review and catalog admission. Catalog admission stays the
   operator's; this run did not create a module or a catalog snapshot.
5. Module poetics acceptance, then module profile, acoustics and surface
   descriptor generation for any newly admitted module.
6. The operator walk remains pending for every generated map.

## Text-only and evidence rules

All batch records are UTF-8 JSON text. No image or binary payload was added to
a module metadata or layer file. No render capture applies: this run changes
source manifests and validation only, not map geometry, materials, lighting or
camera-visible content. Visual evidence for the later room candidates must be
written as a separate text log under `docs/evidence/`.

`content.audio.present` is `false` because no audio evidence stream was
registered for these sources. It is not an ffprobe claim that the containers
have no audio track.

## Approval state

`registration_accepted` and `scale_calibrated` are **false** in every batch
manifest. No source review, seed, room, catalog admission, poetics record or
module was approved by this run.
