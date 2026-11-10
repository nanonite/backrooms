# Module profiles (schema v1)

One `module_profile_v1.json` sidecar per admitted library module, from
`docs/GENERATIVE_MAP_TEMPLATE_PROPOSAL.md` sections 4.2, 4.5 and 6.5.

The sidecars are **derived records**. Each one references its frozen
`module_poetics` record by path and sha256 and never edits it, a module scene,
the catalog or a catalog snapshot.

## Locations

| Module kind | Profile |
|---|---|
| Authored kit | `room_catalog/module_profiles/<module_id>-v<version>.json` |
| Source room | `source_library/sources/<source_id>/rooms/<room_id>/module_profile_v1.json` |

## Derived now (issue #215)

* `shape`: footprint, bbox, area, aspect, convexity, primitive, stage and
  symmetry from the accepted poetics. `volume_nominal_m3` is the
  `envelope_area_x_max_ceiling` heuristic and says so; `volume_measured_m3` is
  null; `ceiling_kind` is `"unknown"`.
* `exits`: socket identity, tested/untested status, compatibility type, width,
  elevation and tested pair ids from the accepted poetics and the library index.
* `surfaces.*.acoustic` and `acoustics.tag`: the `module_acoustics` tag derived
  from the accepted `style_tags`.
* `eligibility`: `layout_eligible_derived` from tested sockets and
  `catalog_layout_eligible` copied from the library index.

## Not reviewed yet (operator step pending)

These fields are explicit placeholders, not invented values. Do not read them as
accepted art direction:

* `roles.semantic_tags`, `roles.sightline_tags`, `roles.circulation_role`
  (schedule: #219);
* `mood` values and tags (schedule: #219);
* `surfaces.*.material_id`, `surfaces.*.palette_id` (schedule: #217);
* `acoustics.probe` and `acoustics.absorption` (schedule: #216 and #213);
* `lighting`, `scale` (schedule: #218);
* `runtime` door/mutation policy (schedule: #223).

`profile_version` stays `module-profile-0.1.0` and no accepted/approved flag is
set. The operator accepts or edits the semantic fields. `check` enforces the
schema, the frozen references and the mechanical projection, so reviewed
semantic edits are preserved.

## Commands

```bash
python3 godot_walk/scripts/backfill_module_profiles.py check
python3 godot_walk/scripts/backfill_module_profiles.py build
python3 godot_walk/scripts/template_validate.py
```

`build` refuses to overwrite an existing profile whose content differs, so an
operator-edited profile is never silently regenerated.
