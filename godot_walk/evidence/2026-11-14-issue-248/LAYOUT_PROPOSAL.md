# Issue 248 — Single-image picture input layout proposal

Status: **PROPOSAL ONLY — PENDING operator decision (2026-11-14).**

No file under `data/pictures/` or `godot_walk/source_library/` was moved,
copied, registered, or edited for this proposal. The 57 photos and
`picture-set-d160eaa3cc847d5c` are untouched. No source was registered and no
picture-source event was appended by this task; no Hunyuan, Panogen, or model
call ran. The existing picture-set record remains
`source_review.status: pending_operator_review` with
`registration_accepted: false` and `scale_calibrated: false`.

This document is the layout decision the operator has to make. It is paired
with [`REPORT.md`](REPORT.md), which records what the existing evidence says
about single-image limits and usefulness.

## 1. What exists today

| Item | Current state |
|---|---|
| Picture intake root | `data/pictures/` (gitignored; images stay local) |
| Picture-set layout | `data/pictures/<set>/<image files>` |
| Picture-set registration | `.venv`-free `register_picture_sources.py`; one directory = one `picture_set` source |
| Picture source IDs | `picture-set-<first 16 hex of the ordered image-set hash>` |
| Picture manifest | schema v3, `content.picture_set[]`, one to many images |
| Picture review | frozen `picture_seed_review_v1`; ranks up to three images per set |
| Single-image source kind | **none** |
| Single-image review | **none** |
| Source-library index | schema 2; 13 sources = 12 `video` + 1 `picture_set` |
| Registered photo collection | `picture-set-d160eaa3cc847d5c`, 57 unrelated webp photos |
| True multi-view reference | Mip-NeRF 360 `room`, 311 photos, COLMAP poses in `sparse/0`, outside git, **not registered** |

Two current behaviours matter for the layout:

1. `register_picture_sources.py inventory` treats every direct child
   **directory** under `data/pictures/` as another picture set. A new
   `data/pictures/singles/` folder would be swept into that path unless it is
   reserved and excluded.
2. `source_kind` is the discriminator in the manifest, but the source ID and
   index patterns only know `video` and `picture-set`. A one-image directory
   today can only be registered as a one-image `picture_set`, which is exactly
   the ambiguous label that caused the #246 correction.

## 2. Definitions used in this proposal

| Term | Meaning | Cardinality | Relationship between images |
|---|---|---:|---|
| **Multi-view picture set** | Several photographs of one physical place, with overlapping viewpoints; optionally COLMAP poses. One `picture_set` source. | 2 or more | Same scene; view relationships exist |
| **Single-image source** | One photograph as its own source. | Exactly 1 | None; no peers, no sequence, no pose |
| **Single-image collection / batch** | A folder of unrelated photos gathered for convenience. It is not one scene and must not become one source. | Many | None assumed |

The distinction is semantic, not just a count. A 57-photo folder of unrelated
photos is a single-image collection; a 311-photo Mip-NeRF room capture is a
multi-view picture set. The source record has to say which one it is.

## 3. Options

### Option A — one directory per image, registered as a one-image `picture_set`

```
data/pictures/single-<slug>/<one image>
```

No code change; `register_picture_sources.py` already accepts a directory with
one image, and `picture_seed_review_v1` would produce one candidate.

- Good: works today; hashing, dimension probing, exact-bytes review, and guard
  binding already exist.
- Bad: records an unrelated single image as a `picture_set`; the name implies a
  set/scene; consensus and future multi-view code will see a set of one; the
  index and manifest still cannot distinguish a true multi-view set from a
  single photo. It does not meet goal (3) of #248.

### Option B — reserved `data/pictures/singles/` folder plus a `single_image` source kind (recommended)

```
data/pictures/
├── <multi-view-set>/           # picture_set, 2+ views of one place
└── singles/                    # reserved; flat
    ├── <image-a>.webp          # one file = one single_image source
    └── <image-b>.jpg
```

Each direct supported file in `singles/` is one source. Directories in
`singles/` are rejected. `register_picture_sources.py inventory` explicitly
skips `singles/`; a new `register_single_image_sources.py` (name to be fixed in
the implementation issue) scans it.

- Good: matches the operator's request for a single-images folder; keeps
  single images and multi-view sets separate at the source-kind, source-ID,
  index, manifest, review, and guard levels; one image can be added or removed
  without changing any other source; content-addressed identity catches
  duplicates.
- Cost: new schema v4, index schema v3, registration/review/runner branches,
  tests, and a reserved-name rule in the existing picture-set inventory. This
  is a versioned addition, not an edit to frozen `WORKFLOW_V1` or
  `SEED_REVIEW_PICTURE_SET_V1`.

### Option C — one batch folder registered as one `picture_set` with a marker

```
data/pictures/singles/<batch>/<many unrelated images>
```

- Good: fewer sources, one review package, existing code mostly reused.
- Bad: repeats the #246 error. The batch hash changes when a photo is added or
  removed; one source implies one scene; the operator's "unrelated photos"
  collection would again look like a multi-view set. Rejected.

### Option D — no registration

Keep single images as loose local files and do not put them in the source
library.

- Good: zero code and zero risk.
- Bad: no content hash in the ledger, no exact-bytes review, no operator
  decision binding, no Hunyuan guard. It cannot support the limit/usefulness
  question beyond ad hoc inspection. Rejected.

**Recommendation: Option B.** Option A is the zero-code fallback only if the
operator wants to defer all implementation; it does not provide the separation
the issue asks for.

## 4. Recommended contract (Option B)

### 4.1 Folder and registration rules

- `data/pictures/singles/` is reserved and flat. Supported suffixes are the
  existing picture suffixes (`.jpg`, `.jpeg`, `.png`, `.webp`, `.tif`,
  `.tiff`).
- Every direct file is one source. Symlinks, subdirectories, and unsupported
  files are refused with a clear error.
- `source_path` is the file path, `data/pictures/singles/<file>`. No file is
  copied, resized, renamed, or edited during registration.
- `source_id` is `single-image-<first 16 hex of the image file SHA-256>`.
  Duplicate bytes are one source; the second path is refused rather than
  creating a second identity.
- A file whose bytes change must be registered as a new source. The old record
  and its events are never rewritten. The operator should rename or replace the
  file rather than edit it in place, because the old record's path would no
  longer match its recorded hash.
- Registration writes a new manifest version and one append-only
  `source_registered` event. It does not approve the source.

### 4.2 Manifest schema v4 (new file; v3 untouched)

Minimal shape:

```jsonc
{
  "schema_version": 4,
  "manifest_version": 4,
  "source_id": "single-image-<16 hex>",
  "source_kind": "single_image",
  "content": {
    "video": null,
    "picture_set": null,
    "single_image": {
      "image_id": "img_0001",
      "path": "data/pictures/singles/<file>",
      "sha256": "<64 hex>",
      "width": 3000,
      "height": 4000,
      "capture_index": 1,
      "captured_at_utc": null,
      "camera_pose": null
    },
    "audio": {"present": false, "path": null, "sha256": null}
  },
  "view_support": {"view_count": 1, "multi_view": false},
  "capture": {
    "camera_model": null,
    "lens": null,
    "intrinsics": {"fx": null, "fy": null, "cx": null, "cy": null},
    "distortion": null,
    "capture_height_m": null,
    "orientation": null
  },
  "scale": {"status": "uncalibrated", "method": null, "anchor": null,
            "confidence": 0.0, "evidence": []},
  "lighting": {"status": "unknown", "color_temp_k": null,
               "illuminance_lux": null, "fixtures": [], "confidence": 0.0,
               "evidence": []},
  "source_review": {"status": "pending_operator_review", "decision": null},
  "frame_references": [],
  "hunyuan": {"status": "not_attempted", "attempts": [],
              "policy_invocation_limit": 3,
              "policy_note": "Single-image registration does not authorize a model run."},
  "room_adaptations": [],
  "registration_accepted": false,
  "scale_calibrated": false
}
```

`capture_index` is always `1`; no timestamp or pose is invented. The source
has no multi-view support and the manifest says so.

### 4.3 Index schema v3 (new file; v2 untouched)

- `source_id`: `^(video|picture-set|single-image)-[0-9a-f]{16}$`
- `source_path`: existing video and picture-set patterns, plus
  `^data/pictures/singles/[^/]+$`
- `manifest_path`: existing patterns, plus
  `.../sources/single-image-[0-9a-f]{16}/source_manifest(-v[0-9]+)?\.json`

### 4.4 Review path

New versioned `single_image_seed_review_v1` (new files; frozen
`picture_seed_review_v1` is not edited):

- Exactly one candidate; no batch ranking is required or implied.
- Report **absolute** focus and exposure measurements and the existing
  `resolution_warning` rule (long side below 1024 px).
- Do **not** report the one-image `picture_seed_review_v1` score as a quality
  score. With one image, `focus_score` is `1.0` by construction,
  `duplicate_similarity` is `0.0` by construction, and the score collapses to
  `0.722222 + 0.277778 * exposure_score` (see `REPORT.md` §4.2).
- An optional model review may describe visible content, but it stays
  advisory and disabled by default, exactly as picture review is today.
- The operator approves or rejects the exact image; the decision binds the
  source ID, image SHA-256, path, dimensions, and review-request hash.
- If a shortlist over a batch of unrelated singles is wanted for convenience,
  make it a separate advisory report (`single_image_batch_shortlist_v1`) that
  says it is not scene membership and does not write approval. It is not
  required for a single-image source.

### 4.5 Hunyuan/Panogen guard

- New `source_kind: single_image` branch binds `source_image_sha256`,
  `seed_image_id`, path, width, height, and the operator decision.
- The existing long-side rule applies: an approved image below 1024 px on the
  long side is rejected. The current collection has 7 such images.
- The existing `picture_set` branch is unchanged.
- No automatic run. The operator authorizes each attempt exactly as today.

### 4.6 Multi-view picture sets stay separate

- `picture_set` remains the kind for two or more images of one physical place.
  It may use scene-level review and the advisory FreeView consensus.
- For new registrations, a one-image directory should be routed to
  `single_image` (or refused with a message) so the `picture_set` label cannot
  drift back to meaning "any folder of pictures". If Option A is chosen
  instead, that routing is not available; the one-image `picture_set` must then
  be documented as a compatibility fallback, not a multi-view set. Existing
  one-image records are not rewritten.
- The 57 unrelated photos are **not** a multi-view set. They stay the existing
  legacy `picture_set` record until the operator decides their migration; this
  proposal does not relabel them.
- The Mip-NeRF 360 `room` scene is an external multi-view reference. It is
  outside git, not registered, and must never be placed in `singles/`.

### 4.7 Migration of the existing 57-photo collection

No migration is proposed in this issue, and nothing may move before the
operator agrees the layout. Once the layout is approved, the operator has two
safe choices:

1. **Leave it as a legacy single-image collection.** Keep
   `picture-set-d160eaa3cc847d5c` as the recorded history, use `singles/` only
   for new single-image sources, and add a versioned successor with a
   `collection_kind: single_image_collection` marker (no source-kind rewrite,
   no path move).
2. **Reclassify it in a later, separately reviewed migration.** Register each
   photo as its own `single_image` source, preserving the old manifest and
   event chain. This needs its own index/manifest compatibility decision
   because the photos live in the shared `single_backrooms_esq` folder.

Either choice preserves the old record. Neither is part of this proposal.

## 5. Implementation checklist after operator approval

| Area | Change | Guardrail |
|---|---|---|
| Schema | New `source_manifest_v4.schema.json`, `index_v3.schema.json` | v3/v2 untouched; versioned additions |
| Registration | New single-image probe/register module; reserve `singles/` in picture-set inventory | Hash/probe in place; no copy/edit |
| Manifest | `source_kind: single_image`, one image, `view_count: 1`, `multi_view: false` | No timestamp/pose/scale invented |
| Index | Add `single-image-` IDs and `data/pictures/singles/<file>` paths | Existing entries unchanged |
| Seed review | New `single_image_seed_review_v1`; absolute metrics; one candidate | Frozen `SEED_REVIEW_PICTURE_SET_V1` untouched |
| Guard | New `single_image` branch; exact image binding; <1024 rejection | No automatic Hunyuan run |
| Tests | One-image source, duplicate hash, low-res rejection, `singles/` not swept into picture inventory, multi-view set unaffected, append-only events, schema validation | CPU only; no model/GPU |
| Docs | `source_library/README.md` plus a dedicated layout note | No hash-pinned file edited |

## 6. Why not a one-image `picture_set`?

It works mechanically today, but it makes the two input types indistinguishable
in exactly the place that matters: the source record. The #246 correction
happened because a folder of unrelated photos was recorded as one picture set.
A one-image `picture_set` repeats that mistake at a smaller scale. The layout
should make the distinction explicit rather than infer it from the number of
files.

## 7. PENDING operator decisions

1. **Layout:** approve Option B (`data/pictures/singles/` flat folder plus a
   `single_image` source kind), or choose Option A/C/D.
2. **Folder name:** confirm `data/pictures/singles/`; `single_images/` is the
   alternative.
3. **Identity:** confirm `single-image-<sha256[:16]>` and
   `source_path: data/pictures/singles/<file>`.
4. **Review semantics:** confirm that a one-image source has no batch
   mechanical rank, only absolute measurements plus operator review.
5. **One-image `picture_set` rule (Option B):** confirm that a new one-image
   directory is routed to `single_image` or refused, so `picture_set` keeps its
   multi-view meaning.
6. **Legacy 57-photo collection:** decide later whether to leave it as a
   legacy single-image collection or migrate it; do not move it now.
7. **Downstream test:** a single-image seed review and any Hunyuan attempt
   remain separately operator-gated; this proposal does not authorize either.

Until decision 1 is recorded, the layout is **PENDING** and no implementation
or file move is allowed.
