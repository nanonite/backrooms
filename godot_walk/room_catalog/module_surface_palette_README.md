# Module surface and palette descriptors

Issue #217 adds one `module_surface_palette_v1.json` descriptor per admitted
module profile. Source-room descriptors sit beside their profile; authored-kit
descriptors live in `room_catalog/module_surface_palettes/` so the existing
profile loaders continue to see only profile records. Each descriptor links to
the unchanged profile by path and SHA-256. Its `surfaces` block follows the
exact surface schema from `module_profile.schema.json`, so it can be copied into
a module profile without transforming its records. Provenance carries the
evidence basis; a sibling `review.surfaces` block stores resolution status,
evidence status, and any bespoke reason without adding fields rejected by the
profile schema.

The descriptors extend the existing module profile records without changing
their hashes, any accepted poetics, library scene, catalog, or palette registry.
Mappings to a palette entry identify a registry match as `observed` or an
evidence-limited suggestion as `proposed`. Unsupported materials carry a null
palette ID and an explicit null/bespoke reason. No 0.4.0 registry was needed.

The operator mapping table is
`module_surface_palette_mapping_v0.1.0.md`; operator review is **pending**.
The re-runnable coverage report is
`module_surface_palette_coverage_v0.1.0.json`.

```bash
python3 godot_walk/scripts/module_surface_palette.py build
python3 godot_walk/scripts/module_surface_palette.py check
```

`check` validates the descriptor schema, profile references and hashes, palette
surface resolution, required evidence basis, and complete coverage. It fails
when a surface is missing or unresolved.
