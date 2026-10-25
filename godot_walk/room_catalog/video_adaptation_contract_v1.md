# Godot video-to-PSX room adaptation contract v1.0.0

This contract describes a repeatable operator-directed adaptation. A video is
evidence for visible surfaces and context; it is not a recovered floor plan.
Every candidate resolves its own shape and may be rejected when the source does
not support a useful bounded room.

## Three records

1. **Source observations** cite direct decoded source frames and crops. They
   separate visible, partly visible, occluded and unknown facts. A source-visible
   opening does not establish where it leads.
2. **Reusable requirements** define the game module's allowed spatial shapes,
   controller clearance, floor and ceiling rules, collision obligations,
   visual containment, typed sockets and closure behavior. They permit different
   footprints and zero or more authored sockets.
3. **Resolved adaptation** records one actual scene, assets, walkable region,
   boundaries, obstacles, render placement envelope, sockets, PSX settings and
   readiness evidence. Only reviewed unchanged artifacts inherit an approval.

## Spatial contract

- Coordinates are local Godot X/Y/Z with +Y up. Current coordinates are design
  units; registration and scale remain unaccepted.
- Version 1 footprints use a finite, simple orthogonal polygon in XZ. Multi-part
  floors are represented as explicit unions of supported polygons/prisms. Other
  shape types are rejected until a contract version describes their checks.
- Record the spawn-connected capsule-clear floor region and its measurement
  method separately from boundary and obstacle collision.
- Record the rendered placement envelope independently. It includes all visible
  room geometry, overhangs and background meshes. A conservative AABB may bound a
  non-rectangular shape; it does not claim the whole AABB is walkable.
- Record every socket opening, approach-clearance volume, compatibility type and
  closure behavior. Keep observed video openings separate from authored sockets
  and mechanically tested connectors. No socket means no stitchability claim.
- Geometry, appearance, placement basis and collision each have their own origin
  and evidence references. A source crop can texture explicitly authored geometry.

## Reusable requirements

- Reuse the active Godot 4.6.3 controller and the accepted `MATERIAL_LANGUAGE.md`
  PSX profile. Keep `registration_accepted=false` and `scale_calibrated=false`.
- The player capsule and a safe spawn/reset must be clear. Floors support the full
  tested route. Every reachable exposed boundary and approachable upright gets a
  visual and collision check.
- Close unused perimeter edges with visible geometry and matching collision.
  Keep visual containment separate from collision traversal tests.
- Use source frames decoded from the original video. Record the zero-based frame
  index, timestamp, decoded-frame hash, pixel crop bounds and crop hash. Never use
  Gaussian renders, PSX captures or generated-room screenshots as source seeds.
- Validators are read-only. Extraction, mechanical checks, GPU capture and
  performance measurement are explicit stages with fresh output paths. A changed
  candidate or runtime dependency makes affected evidence stale; never rewrite a
  historical operator decision.

The JSON schema is `video_adaptation.schema.json`. The versioned freeze manifest
pins that schema, this contract, the existing catalog and material profile before
the first transfer adaptation.
