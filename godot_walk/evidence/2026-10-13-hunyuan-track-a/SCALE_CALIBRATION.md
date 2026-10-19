# Hunyuan Frame-141 Scale and Anchor Check

## Result

The frame-141 camera anchor and orientation can be reproduced. A CPU-only fit
of the run-05 background depth sheet also identifies local floor and ceiling
patches. Matching their separation to the existing #100 **chosen** 2.4 m clear
height gives a candidate scale of `1.558285848 declared metres per Hunyuan
unit`. This is a convention-derived scale, not a physical measurement.

The candidate is not an accepted registration. With the camera center fixed,
both fitted planes sit about 12 cm above the corresponding #100 floor and
ceiling at the reference x/z. Moving the transform down to align those planes
moves the Hunyuan camera origin down by the same 12 cm. There are no confirmed
Hunyuan-to-#100 point correspondences, so mesh reprojection error is unknown.
Keep `registration_accepted=false`; do not use this candidate for collision,
walkability, or a claim of surveyed metric geometry.

The first assessment left scale null because no plane comparison had been
made. The follow-up below supersedes that limited assessment only for a
convention-based candidate; it does not change the older mesh evaluator's
`calibrated_unit_scale=false` finding or collision decision.

## Evidence

The source-frame helper in `scripts/splat_pipeline/hunyuan_source.py` converts
the registered COLMAP camera through the existing `corridor_splat` alignment
contract and dataparser transform. It gives frame 141's declared world camera
center `[2.250342, -0.100280, 4.398888]`, forward
`[-0.528622, 0.001250, -0.848856]`, and up
`[0.003274, 0.999994, -0.000566]`. The source camera has horizontal FOV
75.934660 degrees and vertical FOV 47.398806 degrees.

The Hunyuan source code defines panorama rays with the image center pointing
along local `-X`, increasing panorama longitude toward local `+Y`, and the top
pole at local `+Z`. Thus the orientation matrix in
`calibration_manifest_frame_141.json` maps `-X` to registered forward, `+Y` to
registered right, and `+Z` to registered up. Its determinant is 1.000000000000,
maximum orthogonality error is 1.18e-12, and the registered camera up vector is
0.190367 degrees from Godot world `+Y`.

The existing camera-contract projection of its separate target
`[0.5, -0.07, 1.7]` is `(937.366, 530.026)` at depth 3.206077 in frame 141.
That target is not a matched point on the Hunyuan mesh, so it is not a mesh
reprojection residual. No confirmed Hunyuan 2D/3D landmarks are available;
reprojection residual is therefore unmeasured.

The existing #133 Bevy capture at `bevy_fixture/frame_141.png` verifies that
the forward composition and vertex colors render with this camera orientation.
It used provisional display scale 1.0 and is not a scale or landmark-residual
measurement.

Frame 141 alone does not provide an independent metric scale: perspective
projection of a local point `p` is unchanged when `p` is multiplied by a
positive uniform scale because that scale cancels between image coordinates
and camera depth. The mesh export metadata states `unknown; no scale was
applied`. Upstream Hunyuan builds vertices as predicted panorama distance times
a unit ray and applies depth compression to some layers. It provides no metric
bridge to COLMAP coordinates. A scale can only be proposed here by adding the
#100 declared floor-to-ceiling convention as a shared semantic dimension.

The #100 `corridor_splat` manifest sets 5.128383849 m per Nerfstudio unit by
declaring a synthetic corridor ceiling height of 2.4 m for 0.46798369 units.
Its own text explicitly calls this a choice, not a measurement. That factor
applies only to the Nerfstudio export frame and is not copied to Hunyuan. The
candidate below independently fits the Hunyuan planes and solves a new scale
that makes their separation equal to the same declared 2.4 m convention.

## CPU Plane-Fit Follow-Up

The analysis uses `data/track-a/hunyuan/scene-run-05/mesh_layer1.ply`, SHA256
`4955ffcd5d05d9dd0bdece02624495fbd39eeb80383c3c5bd119a0a2473e8698`. This is
the 3840 by 1920 full-panorama background grid, with 7,372,800 points. A
1000-point sample confirmed that vertex colors match the bicubic-resized
`remove_fg1_image_sr.png` at their row/column positions exactly (maximum
channel error 0), which supports using the PLY's grid position as its panorama
pixel correspondence.

For reproducibility, `v` is the panorama row fraction from top (horizon at
`v=0.5`); yaw is measured from local `-X` forward toward local `+Y`. Include
points within a symmetric yaw window and the stated inclusive `v` bounds. The
base fit uses floor `v=[0.56,0.62]`, ceiling `v=[0.37,0.42]`, and yaw `+/-35`
degrees. The latter is inside frame 141's measured horizontal half-FOV of
37.967 degrees.
Fit `z = a*x + b*y + c` by least squares independently to each point set. The
floor fit has 85,790 points and coefficients
`[0.0119497094, -0.0088902111, -0.6674828591]`; absolute residual quantiles
q50/q90/q95/q99 are `[0.001963, 0.005819, 0.007180, 0.009439]` Hunyuan units.
The ceiling fit has 71,616 points and coefficients
`[-0.0013708361, -0.0320067653, 0.8238017148]`; residual quantiles are
`[0.002881, 0.007286, 0.009728, 0.015633]` Hunyuan units. These are locally
coherent depth-sheet patches, not watertight or collision surfaces. Their
transformed normal tilts from world horizontal are 0.920 degrees and 2.015
degrees for floor and ceiling.

The #100 reference floor and ceiling have shared declared x/z
`[-0.6513254731, 2.8875470744]`, with y values `-1.2709904916` and
`1.1290095084`. For a local plane normal `n_local=[-a,-b,1]`, the world normal
is `n=R*n_local`; its world height at the reference x/z under scale `s` and
camera center `C` is
`y=C_y + (s*c - n_x*(X-C_x) - n_z*(Z-C_z))/n_y`.
Solving the difference of ceiling and floor heights to equal 2.4 gives the
Hunyuan clear height `1.5401538834` units and candidate scale `s=1.5582858479`
declared metres per Hunyuan unit. No #100 Nerfstudio scale factor is reused.

The candidate is stable to the tested masks, but this is sensitivity within the
same generated depth sheet, not independent validation. Changing yaw half-width
from 31 to 35 to 37.967 degrees gives scales 1.557443, 1.558286, and 1.559205.
Small floor/ceiling band variants produce a combined range 1.555256 to
1.559205, about 0.254% of the candidate. Broadening the ceiling mask toward
`v=0.45` includes a wall transition and lowers the fitted result; that is why
the stricter base ceiling band is used.

Two transforms expose the remaining registration ambiguity:

| Transform | Translation | Outcome |
|---|---|---|
| Camera anchored (recorded candidate) | `[2.25034218896, -0.10027971444, 4.39888812352]` | Camera origin residual is zero by construction. At the #100 reference x/z, both fitted planes are about `+0.120342 m` above their #100 counterparts. Floor surface residual RMS is `0.093333 m`; ceiling RMS is `0.080582 m`. |
| Plane-aligned diagnostic | `[2.25034218896, -0.22062215756, 4.39888812352]` | Fits floor and ceiling to the #100 heights at the reference x/z, but puts the Hunyuan camera origin `-0.120342 m` below the registered camera. Not adopted. |

The fitted surfaces are mildly tilted; residual q05/median/q95/q99 against the
respective #100 horizontal planes are floor `[0.052546, 0.090980, 0.122383,
0.126719] m` and ceiling `[-0.008751, 0.065026, 0.138093, 0.142813] m` under
the camera-anchored candidate. Those residuals describe fitted sheet points
against the declared horizontal reference planes. They are not point-landmark
reprojection residuals. The source camera uses SIMPLE_RADIAL distortion while
the Hunyuan panorama warp does not model that distortion, which is another
reason not to infer correspondence from similar pixels alone.

The completed scene runs 04 and 05 use the same input panorama hash
`523bf7a6...1ea5427`, but export different mesh hashes. They are output
variants of one zone, not independently anchored zones. Cross-zone overlap is
not available to measure. Mesh evaluator results are unchanged: no
walkability, collision, or physical metric scale approval.

## To Finish Calibration

To accept registration, provide a surveyed dimension or confirmed matched
Hunyuan-to-#100 landmarks with 2D/3D correspondences and camera IDs. Resolve
the 12 cm conflict between preserving the camera center and aligning the two
fitted planes with independent image/landmark evidence. Cross-zone overlap
requires a Hunyuan mesh generated from another registered source frame. Only
after these checks should a separate walkability/collision assessment begin.

No inference, GPU rendering, or collision work was run for this follow-up. See
`calibration_manifest_frame_141.json` for input hashes and the complete numeric
anchor and plane-fit record. The initial scale-null assessment is retained in
its `assessment_history`; the current numeric scale is not surveyed or accepted.
