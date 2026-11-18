# Authored data — issue 272 lit PSX material fixture

Everything in this fixture is **authored** in uncalibrated design units. No metric
scale, registration, source connectivity or catalog admission is established.
`registration_accepted=false` and `scale_calibrated=false` everywhere.

## What is new (this slice)

- Four **new** shader variant files under `fixture/`. Each is derived from the
  accepted library shader but is a separate, opt-in file; neither
  `library_psx_vertex.gdshader` nor `library_psx_textured.gdshader` was edited.
- One **new** fixture scene script (`psx_lighting_fixture_v1.gd`) and four **new**
  scene files, one per independently selectable combination.
- One **new** machine-readable record (`shader_decision_v1.json`) documenting the
  shader choices, material/light/camera settings and preserved artifacts.

## Baseline versus lit

The **baseline** variants set both `UNSHADED` and `FOG_DISABLED`, exactly mirroring
the accepted library shaders. Scene lights must not change their output.

The **lit** variants remove `UNSHADED` only. The shared URSC include then selects
`diffuse_lambert_wrap` + `vertex_lighting`; `FOG_DISABLED`, `CULL_MODE` and the
rest of the PSX path stay byte-identical to the baseline. This isolates lighting
as the single changed variable.

## Solid and textured paths tested separately

- **Solid**: `TEXTURE_DISABLED`, neutral authored albedo (0.62, 0.66, 0.71). No
  texture is involved, so geometry/normal response is isolated from texels.
- **Textured**: `TEXTURE_REPEAT`, with a deterministic 64 px / 8-cell checker
  generated in code. It is authored, **not** source-derived and not an attempted
  reconstruction of any accepted crop; it exists only to exercise the textured
  shader path with unit UVs repeated across every mesh.

Both paths can be selected independently of the lighting mode, so the four scenes
are baseline-solid, lit-solid, baseline-textured and lit-textured.

## Light and camera settings

A single `DirectionalLight3D` key (energy 1.7, warm tint, rotation -38/28/0) plus
a colour ambient source (energy 0.4 when on, 0.0 when off) form the lighting.
`set_light_on(bool)` toggles both together and is repeatable. Fog is held at the
disabled setting in every variant and both light states; it is deliberately not
part of this comparison. Camera transforms are recorded byte-for-byte in
`views_v1.json` and reused by every capture.

## Geometry

All four scenes share one script. The same five meshes (floor, cuboid, sphere,
cylinder, back wall), transforms, camera and light are built in every variant;
only the assigned shader and the light state differ. The sphere and cylinder
provide curved normals so any light response is visible across a gradient rather
than a single flat face.
