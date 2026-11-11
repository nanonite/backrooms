# Proposal: one versioned metadata record per module

**Status: proposal only; operator review pending.** This document proposes a
future migration. It changes no schemas, loaders, generators, validators, or
records. The inventory below reflects the repository searched on 2026-11-11.

## Recommendation

Use one authored `module_metadata.json` per module as the canonical, versioned
record. Nest the existing profile, surface/palette, lighting/scale, T6, and
acoustics data in named sections, and keep a hash reference to the frozen
poetics record. Preserve field values, source references, provenance, and
review states exactly during conversion. Add a `space_kind` discriminator
(`enclosed` or `open`) alongside spatial fields. Initially all existing rooms
would be `enclosed`; open-world interpretation is reserved only.

Treat the aggregate as an authored, reviewed snapshot assembled from the
current layer inputs, rather than immediately retiring the layer generators.
The source-of-truth transition and version bump must be coordinated with every
consumer in the inventory. Hashes pin exact contents; section names alone do
not imply approval or measurement.

## Proposed record shape

The record has a top-level format version independent of layer versions, stable
module identity and origin, the space kind, references to immutable inputs,
then the existing semantic sections. Each field carries its own provenance
and review state; missing information stays explicitly unknown or unmeasured.
The sketch below is illustrative and assembled from the committed authored
kit module `godot_early_pocket_pass_through_v1` records. It keeps record-level
review labels separate from the operator approval history recorded for #217
and #219: those are distinct facts with distinct sources.

```json
{
  "metadata_version": "module-metadata-1.0.0",
  "module_id": "godot_early_pocket_pass_through_v1",
  "origin": "authored_kit",
  "space_kind": "enclosed",
  "poetics_ref": {
    "path": "godot_walk/room_catalog/module_poetics/godot_early_pocket_pass_through_v1-v1.accepted.json",
    "sha256": "7e8c4148ab2aaa45af7102719a7f820893b9368480757d6652f1f971774d1b3d",
    "mutable": false
  },
  "approval_history": [
    {
      "issue": 217,
      "scope": "module surface/palette mapping",
      "decision": "operator_approved",
      "known_by_date": "2026-11-11",
      "source": "operator approval recorded for Issue #217"
    },
    {
      "issue": 219,
      "scope": "T6 mood and role drafts",
      "decision": "operator_approved",
      "known_by_date": "2026-11-11",
      "source": "operator approval recorded for Issue #219"
    }
  ],
  "fields": {
    "shape.ceiling_height_m": {
      "value": 2.4,
      "provenance": {"kind": "authored", "source": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json#/shape/ceiling_height_m", "use": "profile ceiling hint for the probe"}
    },
    "ceiling_volume.ceiling_height_m": {
      "value": 2.4,
      "provenance": {
        "kind": "measured",
        "source": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json#/modules/godot_early_pocket_pass_through_v1@1/metrics/ceiling_height_m; Issue 216 headless probe; up-ray result is capped by the profile ceiling hint",
        "status": "measured",
        "basis_status": "measured",
        "tolerance": 0.000001
      }
    },
    "shape.volume_nominal_m3": {
      "value": 198.72,
      "provenance": {"kind": "derived", "status": "derived", "basis_status": "authored", "source": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-t6-v1.json#/ceiling_volume/volume_nominal_m3; godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json#/shape/area_m2; godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json#/shape/ceiling_max_m", "method": "footprint area x authored maximum ceiling; nominal envelope heuristic"}
    },
    "surfaces.floor": {
      "value": {"acoustic": "carpet", "material_id": "backrooms_yellow.floor", "palette_id": "backrooms_yellow", "sign": "icon", "texture_refs": ["res://assets/psx_extension/textures/floor_source_video.png"]},
      "provenance": {"kind": "agent-proposed", "source": "godot_walk/room_catalog/module_surface_palettes/godot_early_pocket_pass_through_v1-v1_surface_palette_v1.json#/surfaces/floor/provenance", "detail": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json; godot_walk/room_catalog/module_acoustics_v0.2.0.json evidence ['carpet_floor']; godot_walk/room_catalog/material_palettes/palettes-0.3.0.json backrooms_yellow.floor via palette registry entry; per-surface assignment is a proposal"},
      "review_state": {"operator_review": "pending", "evidence_status": "proposed"}
    },
    "lighting.illuminance_lux": {
      "value": 120,
      "provenance": {"kind": "agent-proposed", "source": "Agent-proposed estimate for an authored enclosed kit module; basis is the existing 2.4 m ceiling and authored 2.0 m socket width, not a light or scale measurement.", "evidence": [{"path": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json", "sha256": "3dafea55f1db6da5f2d8f956615bc360eccaefd6d85b73d3512ac2403e829c37"}]},
      "review_state": "pending_operator_review"
    },
    "scale.anchor.value_m": {
      "value": 2.0,
      "provenance": {"kind": "agent-proposed", "source": "Agent-proposed estimate copied as a candidate from the base profile socket width; the authored width is not an accepted real-world measurement.", "evidence": [{"path": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-v1.json", "sha256": "3dafea55f1db6da5f2d8f956615bc360eccaefd6d85b73d3512ac2403e829c37"}], "status": "estimated"},
      "review_state": "pending_operator_review"
    },
    "roles.circulation_role": {
      "value": "through",
      "provenance": {"kind": "agent-proposed", "source": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-t6-v1.json#/roles", "evidence": [{"path": "godot_walk/room_catalog/module_poetics/godot_early_pocket_pass_through_v1-v1.accepted.json", "sha256": "7e8c4148ab2aaa45af7102719a7f820893b9368480757d6652f1f971774d1b3d"}]},
      "review_state": "agent_proposed_draft_pending_operator_review"
    },
    "mood.tension": {
      "value": 0.2,
      "provenance": {"kind": "agent-proposed", "source": "godot_walk/room_catalog/module_profiles/godot_early_pocket_pass_through_v1-t6-v1.json#/mood", "evidence": [{"path": "godot_walk/room_catalog/module_poetics/godot_early_pocket_pass_through_v1-v1.accepted.json", "sha256": "7e8c4148ab2aaa45af7102719a7f820893b9368480757d6652f1f971774d1b3d"}]},
      "review_state": "agent_proposed_draft_pending_operator_review"
    },
    "acoustics.probe": {
      "committed_block": {
        "value": {
          "ceiling_height_m": 2.4,
          "damping": 0.616099302191483,
          "max_distance_m": 20.0,
          "mean_distance_m": 7.6380337079366,
          "openness": 0.166666666666667,
          "predelay_msec": 22.2683198482117,
          "room_size": 0.702082418692739,
          "wet": 0.521677720089963
        },
        "provenance": {
          "committed_label": "measured",
          "source": "godot_walk/room_catalog/module_acoustics_v0.2.0.json#/modules/godot_early_pocket_pass_through_v1@1/probe/provenance",
          "meaning_at_issue_216": "from a probe run, not derived from poetics tags"
        }
      },
      "proposed_fields": {
        "mean_distance_m": {"value": 7.6380337079366, "provenance": {"kind": "measured", "source": "godot_walk/room_catalog/module_acoustics_v0.2.0.json#/modules/godot_early_pocket_pass_through_v1@1/probe/mean_distance_m", "evidence": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json; horizontal ray-fan mean"}},
        "max_distance_m": {"value": 20.0, "provenance": {"kind": "measured", "source": "godot_walk/room_catalog/module_acoustics_v0.2.0.json#/modules/godot_early_pocket_pass_through_v1@1/probe/max_distance_m", "evidence": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json; maximum horizontal ray distance, with misses set to the ray-length cap"}},
        "ceiling_height_m": {"value": 2.4, "provenance": {"kind": "measured", "source": "godot_walk/room_catalog/module_acoustics_v0.2.0.json#/modules/godot_early_pocket_pass_through_v1@1/probe/ceiling_height_m", "evidence": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json; up-ray result is capped by the profile ceiling hint", "limitation": "The up-ray ceiling estimate is capped by the 2.4 m profile ceiling hint; it is not an uncapped ceiling measurement."}},
        "openness": {"value": 0.166666666666667, "provenance": {"kind": "measured", "source": "godot_walk/room_catalog/module_acoustics_v0.2.0.json#/modules/godot_early_pocket_pass_through_v1@1/probe/openness", "evidence": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json; fraction of horizontal rays with no hit"}},
        "room_size": {"value": 0.702082418692739, "provenance": {"kind": "derived", "committed_block_label": "measured", "basis": ["mean_distance_m", "ceiling_height_m"], "method": "room_acoustic_probe.gd map_metrics; clamped wall_size and height_size formula"}},
        "damping": {"value": 0.616099302191483, "provenance": {"kind": "derived", "committed_block_label": "measured", "basis": ["mean_distance_m", "ceiling_height_m", "openness"], "method": "room_acoustic_probe.gd map_metrics; clamped wall_size, height_size, and openness formula"}},
        "wet": {"value": 0.521677720089963, "provenance": {"kind": "derived", "committed_block_label": "measured", "basis": ["mean_distance_m", "ceiling_height_m", "openness"], "method": "godot_walk/scripts/room_acoustic_probe.gd map_metrics: clamp((0.18 + 0.48 * wall_size + 0.14 * height_size) * (1.0 - 0.35 * openness), 0.0, 0.75)"}},
        "predelay_msec": {"value": 22.2683198482117, "provenance": {"kind": "derived", "committed_block_label": "measured", "basis": ["mean_distance_m"], "method": "godot_walk/scripts/room_acoustic_probe.gd map_metrics; mean ray distance / speed of sound, clamped to configured pre-delay bounds"}}
      },
      "evidence": [{"path": "godot_walk/evidence/2026-11-11-issue-216/module_acoustics_probe_results.json", "sha256": "3fbdd8ea4ffb7ce69402bc3a5825dbdbef065d26d1ac36586dd629d02b91b6c2"}]
    },
    "acoustics.absorption.status": {
      "value": "unknown",
      "provenance": {"kind": "unknown", "source": "#213"},
      "review_state": "unknown"
    }
  },
  "review": {
    "legacy_surface_operator_review": "pending",
    "legacy_t6_mood_and_role_review": "agent_proposed_draft_pending_operator_review",
    "surface_mapping": "pending",
    "lighting_scale": "pending_operator_review",
    "t6_mood_and_roles": "agent_proposed_draft_pending_operator_review",
    "acoustics_operator_listening": "pending"
  }
}
```

This is a shape sketch, not a schema contract. The approval-history entries
represent the operator approvals recorded for #217 mapping and #219 T6
mood/role drafts as of 2026-11-11. The existing descriptor and T6 files still
contain their original `pending` and
`agent_proposed_draft_pending_operator_review` labels; those labels must be
retained verbatim as source-record state, alongside the later approval event.
During migration, pin the approval source and scope so the aggregate shows
both that the approval occurred and which checked-in labels predate or do not
encode that event. Do not silently rewrite the original records.

Real conversion must carry all
the source record's fields and metadata (including provenance strings, source
hashes, evidence arrays, nulls, fixture details, all surfaces, exits, tags,
and review evidence), not only the representative fields above. The example
uses shortened source labels for readability in the field paths; canonical
records should use repository-relative paths and JSON pointers as evidence.

For acoustics the example deliberately preserves both levels of labeling. The
committed v0.2.0 probe block says `provenance: "measured"` as required by
Issue #216, meaning it came from a probe run rather than poetics tags. The
proposed aggregate keeps that label and all block values under
`committed_block`, then refines the fields under `proposed_fields`: mean/max
wall distance, ceiling height, and openness are measured probe inputs;
`room_size`, `damping`, `wet`, and `predelay_msec` are derived from those
inputs by `godot_walk/scripts/room_acoustic_probe.gd`. The ceiling estimate
retains the T6 overlay's caveat: the up-ray result is capped by the profile
ceiling hint and is not an uncapped ceiling measurement. This per-field split
is a proposed provenance refinement, not a reinterpretation of the committed
block label, and remains an operator question below.

### Review-state and approval evidence

The issue review/acceptance record states that the operator approved the #217
mapping and #219 mood/role drafts by 2026-11-11. Preserve those as explicit
approval-history events, with issue and scope references, in the aggregate.
The checked-in layer artifacts independently retain their literal state:
surface descriptors and the mapping report say `pending`; T6 mood and role
blocks say `agent_proposed_draft_pending_operator_review`; the profile README
also says the taste review is pending. The #216 acoustics README and v0.2.0
index say operator listening is pending. These labels are not the approval
event: they are the status strings in the immutable input snapshots. The
migration must keep both dimensions and link the approval event to its issue
source; it must not erase, reinterpret, or fabricate a transition inside an
older sidecar. The example records the approval scope/date supplied by the
issue acceptance context and leaves source-side labels unchanged.

## Versioning, hashes, and migration

1. Define `metadata_version` for the aggregate's structure. Use semantic
   versions: patch for non-semantic corrections, minor for optional fields,
   major for incompatible shape or interpretation changes. Keep each inherited
   layer's source version in `source_layers` during migration so its original
   contract remains identifiable.
2. Store authored-kit records under
   `godot_walk/room_catalog/module_metadata/<module_id>-v<record-version>.json`;
   store source-room records next to the room's source-level records. Pin every
   aggregate by SHA-256 from map references and downstream manifests. Any edit
   creates a new immutable record version; old hashes continue resolving.
3. Keep `module_poetics` frozen and referenced by its exact path and SHA-256.
   Do not inline or rewrite it as part of consolidation. Aggregate generation
   must fail if that hash no longer matches.
4. First land and review the aggregate schema and conversion report. Generate
   candidate aggregates from the existing files and compare field-by-field,
   including unknown/null values, source references, provenance, hashes, and
   review states. Only then add a compatibility loader and teach one consumer
   at a time to prefer the aggregate while verifying equivalence. Finally
   update map references and generators; retain old records and loaders for
   historical artifacts. Retire sidecars only after a repository-wide
   reference scan and a deprecation period show no live readers.
5. Old maps stay valid because they pin their existing profile paths and
   hashes; old profile, overlay, and poetics files remain immutable and
   readable. New maps pin the aggregate path and hash. A version-aware loader
   must support both forms for as long as old maps are supported.

### Generator and validator mapping

| Current tool | Proposed role after migration |
|---|---|
| `backfill_module_profiles.py` / `module_profile.py` | Produce/update the base profile section in a candidate aggregate; never overwrite operator-edited fields. |
| `module_surface_palette.py` | Produce/check only the surface section and retain mapping review semantics; aggregate build embeds its output. |
| `lighting_scale_overlay.py` | Produce/check lighting and scale sections; preserve field-level evidence and review state. |
| `module_profile_t6.py` | Produce/check ceiling-volume, exits, roles, and mood sections; keep the existing limitations around probe-capped ceiling measurements. |
| `module_acoustics.py` / `module_acoustics_v2.py` | Produce/check acoustics sections and measurement references; preserve v0.1.0 compatibility as legacy input. |
| `template_validate.py` | Become the aggregate validator: schema, field provenance, all input/hash references, version support, and cross-layer consistency. |
| Each layer's `check` command | Remain as focused validators over a layer projection of the aggregate, then optionally retire after all callers migrate. |
| `module_poetics.py` / `module_metadata_accept.py` | Continue drafting/accepting frozen poetics; aggregate creation only references accepted output and never edits it. |

## Alternatives

| Option | Benefits | Costs and risks |
|---|---|---|
| One authored aggregate (recommended) | One reviewable, hash-pinned metadata record; field provenance and review live beside values; simple map reference. | Generators must coordinate updates; one record may be large; careful merges are needed to avoid overwriting reviewed fields; migration touches every consumer. |
| Generated aggregate from layer files | Keeps current layer workflows and validators intact; aggregate is reproducible and avoids duplicate manual editing. | Still has several authoritative files; consumers can see stale generated output; provenance references form a dependency graph; adds a required build step and does not fully meet the goal of one versioned authored record. |
| Keep overlays plus a versioned index | Minimal loader changes and lowest initial migration risk; index can pin all layer hashes. | Metadata remains distributed; consumer must resolve several files and handle partial version combinations; operator review remains scattered. |

The recommendation's main cost is coordinated schema/consumer migration. It is
worth taking only with the hash and compatibility checks below, since a single
file that drops a layer's review semantics would be less reliable than today's
overlays.

## Consumer inventory

Searches used to build and reproduce this inventory (run from repository root):

```sh
rg -l -i 'module_profile|module_surface_palette|lighting_scale_overlay|module_profile_t6|module_acoustics|module_poetics' --glob '*.py' --glob '*.gd' --glob '*.md' --glob '*.jsonl' --glob '*.schema.json' . | sort
rg -n -i 'module_profile|module_surface_palette|lighting_scale_overlay|module_profile_t6|module_acoustics|module_poetics' --glob '*.py' --glob '*.gd' --glob '*.md' --glob '*.jsonl' --glob '*.schema.json' .
rg -l -i 'lighting_scale_state|uncalibrated_not_reviewed' --glob '*.py' --glob '*.gd' --glob '*.md' --glob '*.jsonl' --glob '*.schema.json' . | sort
rg -n -i 'lighting_scale_state|uncalibrated_not_reviewed' --glob '*.py' --glob '*.gd' --glob '*.md' --glob '*.jsonl' --glob '*.schema.json' .
```

The searches cover the full repository, including evidence and docs, without
excluding generated maps, per-module records, or fixtures. The first pair
searches layer names; the supplemental pair searches the lighting/scale API
and its conservative missing-overlay status. The primary search returns 51
paths; the supplemental search returns the lighting/scale review contract,
loader, tests, schema, README, and this proposal. Results overlap and are
collapsed into one inventory below. `rg -l` gives the path inventory and
`rg -n` gives the matching lines for inspection. File paths are
repository-relative.

| Path(s) | Reads or writes |
|---|---|
| `godot_walk/scripts/backfill_module_profiles.py`; `godot_walk/scripts/module_profile.py` | Read library index and accepted poetics plus acoustics v0.1 mapping; build/check authored and source-room profile v1 records. |
| `godot_walk/scripts/module_surface_palette.py` | Read profile, acoustics v0.2 evidence, and palette registry; build/check descriptors, mapping report, and coverage JSON. |
| `godot_walk/scripts/lighting_scale_overlay.py` | Read base profiles; build/check authored and source overlays; expose `lighting_scale_state` with the conservative default for missing/invalid overlays. |
| `godot_walk/scripts/module_profile_t6.py` | Read base profiles and issue #216 probe output; build/check authored and source T6 overlays. |
| `godot_walk/scripts/module_acoustics.py`; `godot_walk/scripts/module_acoustics_v2.py` | Read profiles, accepted poetics, probe results, and legacy acoustics table; build/check v0.1.0 and v0.2.0 acoustics maps. |
| `godot_walk/scripts/probe_module_acoustics.gd` | Resolve module profiles for the Godot acoustic probe runner and emit per-module measurement evidence. |
| `godot_walk/scripts/template_validate.py` | Read schemas, profiles, T6/lighting overlays, and acoustic evidence; validate template records and hash references. |
| `godot_walk/scripts/generative_map_assembly.gd`; `godot_walk/scripts/gmap_library.py` | Consume map module data, catalog records, and profile fields during map assembly. |
| `godot_walk/scripts/integration_artifact_citations.py`; `godot_walk/scripts/module_integration_stages.py`; `godot_walk/scripts/module_metadata_accept.py` | Check metadata event citations, derive staged integration metadata, and record accepted module poetics. |
| `godot_walk/scripts/module_poetics.py`; `godot_walk/scripts/poetics_geometry.py`; `godot_walk/scripts/poetics_signs.py` | Derive, analyze, and validate poetics inputs; aggregate references accepted poetics without modifying it. |
| `godot_walk/scripts/source_ingestion_runner.py` | Create source-room metadata through staged ingestion; profile and poetics outputs must be migrated with source-level consumers. |
| `godot_walk/scripts/test_module_profiles.py`; `godot_walk/scripts/test_template_schema.py` | Validate profile v1 shape, projections, hashes, map references, and unsupported versions. |
| `godot_walk/scripts/test_module_surface_palette.py`; `godot_walk/scripts/test_lighting_scale_overlay.py`; `godot_walk/scripts/test_module_profile_t6.py` | Validate layer schemas, evidence, review state, generator behavior, profile links, and the uncalibrated/not-reviewed missing-overlay fallback. |
| `godot_walk/scripts/test_module_acoustics.py`; `godot_walk/scripts/test_module_acoustics_v2.py` | Validate acoustics generations, probe links, reproducibility, profile references, and legacy mapping. |
| `godot_walk/scripts/test_module_poetics.py`; `godot_walk/scripts/test_module_integration_stages.py`; `godot_walk/scripts/test_picture_set_intake.py` | Exercise accepted poetics, metadata staging/citations, and source ingestion/profile output. |
| `godot_walk/scripts/test_gmap_modules.py`; `godot_walk/scripts/test_issue200_footsteps.gd` | Check module/map behavior and acoustic material behavior used by module records. |
| `godot_walk/room_catalog/module_profile.schema.json`; `godot_walk/room_catalog/module_profile_t6.schema.json`; `godot_walk/room_catalog/module_surface_palette.schema.json`; `godot_walk/room_catalog/lighting_scale_overlay.schema.json`; `godot_walk/room_catalog/module_poetics.schema.json`; `godot_walk/room_catalog/generative_map_v2.schema.json` | Define current layer and map-reference contracts; retain for legacy validation after any aggregate schema is approved. |
| `CHANGELOG.md`; `docs/GENERATIVE_MAP_METADATA_PROPOSAL.md`; `docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md` | Summarize layer additions, describe `module_poetics` storage/generation and metadata boundaries, and define map template/profile references. |
| `godot_walk/evidence/2026-11-03-issue-185/REVIEW.md`; `godot_walk/evidence/2026-11-06-issue-200/REPORT.md` | Review/report documents cite module metadata or its consumers. |
| `godot_walk/evidence/2026-11-11-issue-216/README.md` | Document probe inputs, ceiling-hint cap, acoustics projection, commands, and pending listening review. |
| `godot_walk/room_catalog/module_profiles/README.md`; `godot_walk/room_catalog/module_surface_palette_README.md`; `godot_walk/room_catalog/lighting_scale_overlay_README.md`; `godot_walk/room_catalog/module_surface_palette_mapping_v0.1.0.md`; `godot_walk/source_library/README.md` | Document file locations, generation/validation commands, review states, and source-library authoring. The lighting/scale README names the state API and its fallback. |
| `godot_walk/room_catalog/LIGHTING_SCALE_OVERLAY_REVIEW.md` | Define T5 overlay validation and fallback contracts; distinguish provenance from review evidence; require evidence for reviewed/calibrated claims; specify contributor-status agreement, measured-anchor checks, source-manifest calibration state, and review-record fields. |
| `godot_walk/room_catalog/module_profiles/*.json`; `godot_walk/room_catalog/module_surface_palettes/*.json` | Authored-kit base, lighting-scale, T6, and surface/palette records read by tools/tests above; source of the illustrative example. |
| `godot_walk/room_catalog/module_acoustics.json`; `godot_walk/room_catalog/module_acoustics_v0.2.0.json`; `godot_walk/room_catalog/module_acoustics_v0.2.0.json.sha256`; `godot_walk/room_catalog/module_surface_palette_coverage_v0.1.0.json` | Shared generated mapping and coverage records read by profile, surface, acoustics, and validation paths. |
| `godot_walk/room_catalog/module_poetics/*.json`; `godot_walk/room_catalog/module_poetics/decisions.jsonl`; `godot_walk/room_catalog/schema_fixtures/module_profile.fixture.json` | Accepted/draft kit poetics, acceptance ledger, and profile validation fixture. |
| `godot_walk/source_library/sources/*/rooms/*/module_profile_v1.json`; `godot_walk/source_library/sources/*/rooms/*/module_profile_t6_v1.json`; `godot_walk/source_library/sources/*/rooms/*/module_surface_palette_v1.json`; `godot_walk/source_library/sources/*/rooms/*/module_poetics_v1.json`; `godot_walk/source_library/sources/*/rooms/*/module_poetics_v2.json` | Source-room layer records read by shared validators/generators; poetics records are immutable versioned references. |
| `godot_walk/source_library/sources/*/source_lighting_scale_v1.json` | Source-level lighting/scale overlay; source manifest remains the source metadata record. |
| `godot_walk/source_library/sources/video-b9161c467ed2d30a/events.jsonl`; `godot_walk/source_library/sources/video-ccf9722164a0bdc8/events.jsonl` | Source event ledgers cite accepted module metadata and its immutable poetics path/hash. |
| `godot_walk/room_catalog/generative_maps/*.json`; `godot_walk/room_catalog/generative_maps/*.fill.json` | Historical/current map snapshots may pin profile paths and hashes; retain compatibility readers for them. |
| `docs/MODULE_METADATA_CONSOLIDATION_PROPOSAL.md` | This proposal appears in the search because it documents the metadata names and sources; it is not a runtime consumer. |

The table follows direct textual matches from the repeatable repository-wide
search. A later implementation must also search dynamically assembled paths
and indirect loader calls before deleting sidecars; this inventory does not
claim that a string search can prove the absence of those consumers.

## Source-level metadata

Keep source identity in `source_manifest.json` and retain one source-level
overlay for source-wide lighting/scale (currently
`source_lighting_scale_v1.json`). Do not fold source manifests into every
module: a source can contain several rooms, frames, provenance events, and
ingestion decisions that are not module properties. Each source room should
receive the same `module_metadata.json` aggregate as an authored kit module,
beside its room files, while retaining the manifest and its separate hash.
This draws the boundary at module identity and avoids duplicating source-wide
facts into every room.

## Space-kind forward compatibility

Set `space_kind` to `enclosed` for current modules. For an eventual `open`
record, keep height fields explicitly scoped: `ceiling_height_m` means a
physical ceiling for enclosed spaces; an open-space counterpart would describe
`world_ceiling` (including the skybox boundary) and must not be treated as a
room ceiling. Likewise, enclosed `volume_nominal_m3` is a room-envelope
estimate; open-space volume must state its world-boundary/skybox basis or be
null when no finite world ceiling exists. Preserve the raw measured geometry
and its coordinate/boundary provenance either way. **Open-world support is not
being built now.**

## Risks and operator questions

* **Missed consumers/version bumps:** issue #218 showed that version bumps can
  miss consumers. Before each migration bump, rerun the searches above, search
  for indirect/dynamic path construction, update a consumer checklist, and
  require a compatibility test that loads both an old pinned map and the new
  aggregate. Do not infer safety from a clean primary loader test.
* **Dropped review semantics:** current files use distinct labels (`pending`,
  `proposed`, `unreviewed`, and `agent_proposed_draft_pending_operator_review`).
  A conversion must carry them verbatim, not collapse them to one boolean.
* **Hash churn and merge conflicts:** a combined file creates larger diffs and
  more frequent new hashes. Version immutable records rather than editing a
  referenced record in place.
* **Stale derived data:** the aggregate generator must record input hashes and
  fail on stale sidecars until they are retired. Do not silently prefer a
  stale aggregate.
* **Open-world semantics:** `space_kind` reserves the distinction but does not
  define complete world-boundary geometry or rendering behavior.
* **Approval history versus snapshots:** the #217 and #219 operator approvals
  must be linked as approval-history events, while the checked-in sidecars'
  pending labels remain preserved as literal historical state. Which durable
  issue-record URI or exported approval receipt should the aggregate use when
  Chainlink issue links are not available to offline validators?
* Should the authored aggregate be manually editable, generated with a locked
  section merge, or fully generated after operator acceptance of each layer?
* Should the proposed acoustics per-field provenance refinement be adopted
  while retaining the committed v0.2.0 probe-block label `measured` verbatim?
* Which old map versions and save files must remain loadable, and for how long?
* Should source-wide `source_lighting_scale_v1.json` remain separate as
  proposed, or should source-level metadata have its own aggregate record?
* Should aggregate hash pins be embedded in map records, source event ledgers,
  or both?

**Operator review: pending.** No schema, loader, generator, module record, map,
or hash-pinned file is changed by this proposal.
