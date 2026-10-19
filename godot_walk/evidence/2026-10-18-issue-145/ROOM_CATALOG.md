# Room And Connector Catalog

**Status labels:** Direct = the feature itself is visible. Partial = a feature or continuation is occluded or only partly visible. Authored proposal = a design suggestion, not source evidence. Frame IDs refer to the 24 fps source; time is `(id - 1) / 24` seconds.

| ID | Kind / status | Source frames | Directly observed | Limits / continuity |
|---|---|---:|---|---|
| A | Interior finish / Direct | 0001-0192 | Patterned green/yellow wall covering, carpeted floor, tiled ceiling, and fluorescent ceiling panels recur throughout the clip. | Strong visual continuity; this does not prove a closed room boundary or a single architectural room. |
| B | Partition run / Direct | 0001-0048 | Long patterned wall or partition occupies the near view; a pale square column with a cap/base is close to the camera. | Back side and full endpoints are not visible. Treat as partition/wall surface, not a room boundary with known extent. |
| C | Open passage / Direct + Partial | 0013-0027 (0.500-1.083 s) | A rectangular gap between visible partition ends gives a view into more patterned interior. | Opening is visible; no door leaf or definitive door frame is visible. The space past it is only partially observed. Do not label it a separate room. |
| D | Wall return / Partial | 0049-0096 (2.000-3.958 s) | The camera sees a perpendicular return/corner in the patterned wall/partition and its relationship to nearby columns. | Occlusion hides what lies around the return. It may connect continuously to the earlier partition; the footage does not prove a distinct corridor or room. |
| E | Column bay / Direct | about 0085-0192 (3.500-7.958 s) | A wider sightline reveals multiple pale square columns and further patterned wall/partition fragments. | Repeated columns are visible, but identical appearance and occlusion do not prove which column is the earlier foreground column. Bay extent and perimeter remain unknown. |
| F | Background connectors / Partial | throughout; clearest around 0085-0192 | Additional gaps between columns and wall fragments expose deeper views into the same visual environment. | Their endpoints and destinations are out of frame or occluded; do not model them as confirmed doorways or named adjoining rooms. |

## Camera And Continuity Notes

- All 192 frame IDs 0001-0192 have registered poses in the same sparse reconstruction. The camera moves continuously rather than cutting between rooms.
- Useful close references reviewed at full resolution: 0017, 0024, 0048, 0065, 0087, 0093, 0105, 0135, 0157, 0192. The four contact sheets provide the full sequence context.
- Approximate camera-center samples (COLMAP X, Z; reconstruction units): 0001 (-2.7637, -4.3565), 0025 (-1.5506, -4.1083), 0049 (-0.0811, -3.3761), 0073 (1.1862, -1.9814), 0097 (1.8146, -0.1259), 0121 (1.5858, 1.8472), 0145 (0.4823, 3.5866), 0169 (-1.2964, 4.7879), 0192 (-3.3575, 5.2190). Full positions and view directions are in `camera_path.csv`.

## Unknown Or Unobserved

- The full floor-plan perimeter, room dimensions, ceiling height, and metric scale.
- The space behind the visible opening and beyond the far/background gaps.
- Whether any gap is a formal doorway, and whether any door leaf exists outside the camera view.
- The unseen sides/endpoints of the partition runs and the full extents of the column bay.
- Any rooms, corridors, or connectors not directly visible in the source images.

No additional room is inferred from these unknowns.
