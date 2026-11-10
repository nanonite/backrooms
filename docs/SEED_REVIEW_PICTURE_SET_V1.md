# Picture-set seed review v1

Picture collections use the new `picture_seed_review_v1` path in
`godot_walk/scripts/picture_seed_review_v1.py`. The frozen video `WORKFLOW_V1`
and its schemas stay unchanged; this version does not interpret a picture set
as a video or invent timestamps.

## Review package

`prepare-picture-seed-review` verifies the registered picture-set manifest,
rechecks the image-set hash and every original image hash, then scores every
image with the existing focus, exposure, and duplicate-similarity metrics.
Temporal coverage is omitted. The three metric weights retain the video
workflow's relative proportions and are normalized by their 0.90 total. The
package sends no more than the three highest ranked originals for model review;
the remaining images stay in the output with their rank and exclusion reason.

Each reviewed candidate contains the original repository path, `image_id`,
SHA-256, dimensions, capture index, and scoring measurements. The image path is
the full-resolution original file. `build_picture_model_invocation` verifies
those exact bytes and dimensions and passes only those original paths to the
existing vision adapter. It does not create a resize or contact sheet. The
review prompt says that `capture_index` is file order only for an unrelated
collection; it is not time and has no temporal-coverage meaning.

Images with a long side below 1024 pixels remain in the score and candidate
output and carry `resolution_warning: true`. The Hunyuan guard rejects an
approved seed below that threshold. The resolution warning does not affect
mechanical ranking.

## Operator approval and guard binding

After inspecting the bounded review, the operator records an explicit decision
with `approve-picture-seed --image-id ... --reason ...`, then selects the
matching imported image with `select-image`. The append-only decision binds
`source_image_set_sha256`, `image_id`, the original image SHA-256 and path,
dimensions, capture index, and review-request hash. Selection copies that
decision into the selected-seed event only when its image identity matches.

The picture-set GPU guard requires and embeds the decision. The Panogen guard
rechecks the decision hash and its image-set hash, image ID, image SHA-256,
original path, and dimensions against the seed and guard receipt. A mismatch or
low-resolution image fails closed. Video selection and video guard validation
remain on their existing path.

No decision is recorded for the real `picture-set-d160eaa3cc847d5c` collection
by this implementation. Its exact-image operator approval remains open. This
version does not run Hunyuan, invoke a model, or admit a catalog entry.
