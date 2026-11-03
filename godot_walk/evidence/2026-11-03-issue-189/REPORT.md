# Issue #189: door-frame flicker at library-room joints

Implemented by a Sonnet 5.5 agent. The lead wrote this report from the agent's hand-back and re-ran the tests and the seed-3 headless check.

**Cause.** The coplanar faces at the joint were not trim. The parent's `Wall_*` end faces and the `Header_*` underside and sides lay in the same planes as the library room's own opening faces, because both openings have the same width and height.

**Fix (GDScript only).** At a doorway into a library room, the parent's cut is `MODULE_JOINT_RECESS` = 0.04 m wider on each side and 0.04 m higher than the library opening. The trim follows that cut. Collision, the floor seam, other doorways, library scenes and the catalog are all unchanged. No data changed, so no gmap-0.3.1 was made.

**Check changes.**
- `reveal_coplanar_faces` now fails the check, with 0 expected.
- New negative control `module_joint_recess_removed` rebuilds the old geometry. It fires on 8, 5 and 10 faces for seeds 1, 2 and 3.

**Results**

| Seed (0.3.0) | Edges both ways | trim_coplanar | wall_coplanar | reveal_faces |
|---|---|---|---|---|
| 1 | 26/26 | 0 | 0 | 0 |
| 2 | 24/24 | 0 | 0 | 0 |
| 3 | 26/26 | 0 | 0 | 0 |

- **pytest:** 488 passed.
- **0.1.0 and 0.2.0:** results are unchanged.
- **Lead re-run of seed 3:** PASS, reveal_faces=0, with all 4 controls firing.

**Known gap: seed 9 at 0.3.0, not kept.** A library box (`c12/EastBoundaryVisual`) shares plane x=15 with the outer east face of a non-parent cell's walls. The module overhangs that cell's corner by a sliver. Fixing it needs a generator placement rule, so the fix is folded into #190's gmap-0.4.0.

**Needs human visual verification**
- Whether the flicker is gone at the hall door frame (seed 2).
- How the 0.04 m step where the library opening stands proud of the parent cut looks.
