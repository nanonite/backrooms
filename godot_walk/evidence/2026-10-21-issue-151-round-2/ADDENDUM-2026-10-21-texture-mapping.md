# Addendum: Round 2 Texture Mapping

This addendum corrects the implementation description without changing the reviewed Round 2 bundle or its operator feedback.

The `column_box_source_face` candidate uses one `StandardMaterial3D` as the `BoxMesh.material_override`. Godot therefore applies the same frame-0152 crop to all six box faces. It does **not** map the crop only to the camera-visible/front face, and it does not use separately oriented face materials or camera projection.

Round 2 consequently tests a complete authored box with a repeated source crop, not the face-specific texture treatment described in the variant hypothesis. The operator reports that the column issue remains unresolved. Do not treat these captures as evidence that a correctly aligned, face-specific source texture cannot work.

For the next #151 iteration, isolate the visible face mapping and inspect box-to-column alignment from the matched views. Keep the accepted floor and ceiling fixed. Registration and scale remain unaccepted.
