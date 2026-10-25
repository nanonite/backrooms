# Issue 163 source-video preflight

The selected next source is data/videos/room_large.mp4, separate from the
#100 data/scenes/corridor_travel/video.mp4 source. It is a 1920x1080,
24 fps, four-second clip. This task uses a decoded source-video frame as the
Hunyuan image-to-panorama seed; the clip is not being treated as complete
multi-view reconstruction coverage. Frame 0013 is selected because it gives a
broad view of wallpapered space, a column, ceiling grid, and an open passage.
This selects an experiment input only; it does not approve generated output,
room dimensions, or authored layout.

source_candidates_contact.jpg compares three CPU-decoded samples from each
of six local candidate videos. The room-large 0.5-second sample presents a
broad room view with a visible column and wallpaper. It is the selected seed
(frame index 12 zero-based / frame 0013 one-based), not a design approval.
Other candidate frames at 2.0 and 3.5 seconds are preserved for comparison.
Exact frame hashes and source-video provenance are in source_manifest.json.

No Gaussian render was used. No model inference or room production is claimed
by this preflight. Both registration and scale calibration remain false.
