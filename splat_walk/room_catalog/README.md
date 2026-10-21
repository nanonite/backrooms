# Bevy Room Catalog

`catalog.json` is the versioned registry for independently described playable
zones. `catalog.schema.json` defines its JSON shape; the Rust validator adds
cross-field, connector, calibration, path-containment, and SHA-256 checks.

Run the CPU-only validator from any directory:

```sh
cargo run --release --manifest-path splat_walk/Cargo.toml --bin validate_room_catalog
```

An optional first argument selects a workspace root. The validator checks every
source, asset, transform, runtime, boundary, and validation-evidence file listed
in the catalog. Paths must be repository-relative and resolve inside that root.

## Opening And Connector Semantics

- `observed_openings` records visible source-video evidence. Entries have a
  catalog/frame reference and cannot carry a socket transform or destination.
  They do not imply traversal or registration with a Bevy module.
- `connector_sockets` are authored module-local interfaces with rigid transforms.
  A socket alone is not a traversed connection.
- `tested_connectors` links two registered sockets only after traversal evidence
  exists. The validator checks both endpoints and the evidence hash.

The current reference entry has one unregistered opening observation, no sockets,
and no tested connectors. This is deliberate: #145 found candidate openings but
did not prove a threshold traversal or the relation of those zones to the Bevy
walkthrough.

## Reference Zone

`milestone-video-to-walkable-working` points to the tagged Bevy walkthrough's
run-05 Hunyuan visual GLB and the exact #135 authored collision GLB. It is an
uncalibrated bounded playable reference, not a surveyed or complete room.
`registration_accepted` and `scale_calibrated` are both false. The floor loop,
column proxy, and edge boundaries are explicitly authored; the Hunyuan visual
asset is never collision. The catalog preserves the selected source-video frame,
hashes, transform convention, shared controller parameters, validation evidence,
and measured CPU runtime/resource figures.

The operator accepted #150 as an approximate, standalone playable candidate for
the later column bay, using the #147 Hunyuan visual and a separately authored
room shell and collision asset. Its core perspective is useful; exact
video-to-Bevy geometry is not claimed. The far side of the column remains
room-specific art polish. #148 owns catalog admission and any connector test.
The #145 inventory does not establish that this candidate connects to the
tagged reference zone, so any such connection must be labeled as authored and
tested rather than inferred from the video.
