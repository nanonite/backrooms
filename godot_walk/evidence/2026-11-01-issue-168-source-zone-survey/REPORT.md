# Same-source room survey (CPU preview)

## Input and method

- Source: `data/videos/GoPro Awards_ Haunting FPV Drone Flight Through Abandoned Building.mp4`
- Source SHA-256: `ccf9722164a0bdc8aa0497e8f4ca16b30fcdc6b752192859fd8fef537ba5a0bb`
- Preview: 49 frames sampled approximately every 5 seconds with FFmpeg, resized to 320×180 for this contact sheet.
- Contact-sheet SHA-256: `e315596b27a0b0303ec3d257a91c9e904920e0035ba2dc2788febc06610aa668`
- These are timeline previews only. They are not seed frames; exact frame index, PTS and native-resolution hash must be recorded after a region is selected.

## Directly visible candidate zones

- Around 15–45 seconds: large industrial hall with repeated supports, roof trusses and a far window wall. The accepted room uses a direct seed at 36.533333 seconds.
- Around 145–165 seconds: a smaller debris-filled interior with a low roof, windows and visible supports. This is the strongest candidate for a visually distinct second room in this sample.
- Around 175–210 seconds: several painted interior views with windows, door frames and colored wall bands. This may offer another module candidate, but the 5-second sampling does not establish where one room ends and another begins.

The sampled views show more than one visual zone in the source. They do not establish a floor plan, exact room count, scale, or a walkable connection between those zones. Any connector would be authored game geometry and would need separate traversal tests.

## Gate

A follow-up decoded eleven adjacent native-resolution frames around 152 seconds. The recommended frame is frame_4560 (zero-based index 4559, PTS 151.966667 seconds); its hash and adjacent blur checks are in `seed-review-152s/index.html`. Exact seed approval is still pending. No room was authored, and no Hunyuan inference or GPU work ran. Attempt 005 remains the accepted broad-layout panorama for the first hall; the source budget is 5/6. Do not start attempt 006 without explicit authorization. The first accepted room and its catalog/source-manifest records remain unchanged.
