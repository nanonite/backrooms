#!/usr/bin/env python3
"""Pre-flight parallax/triangulation gate for the splat pipeline.

Reads a COLMAP sparse model (images.bin + points3D.bin) and refuses to train if
the camera motion + scene geometry has too little parallax to reconstruct
surfaces. A near-straight forward dolly, a pure pan, OR an endless receding
corridor all produce spiky-needle splats instead of walls — this catches that
BEFORE a ~12-minute splatfacto run is wasted.

Usage:
    python3 scripts/splat_pipeline/preflight_parallax.py <sparse/0 dir> [--strict]

Exit codes: 0 = PASS, 1 = FAIL (low parallax), 2 = error reading model.

Three things must hold for a corridor to reconstruct:
    median triangulation angle  >= 8 deg   (target >=12)   <- the arbiter
    lateral/forward motion ratio >= 10%    (target >=20%)  <- camera weaved
    near-field coverage          >= 25%    (target >=40%)  <- scene is bounded
With --strict, the *target* values are required instead of the minimums.

The two motion/scene metrics do not gate on their own; they exist to NAME the
failure when the triangulation angle is too low, so you know which lever to pull:
  - low lateral ratio + tiny baseline  -> rotation-dominant (camera pivoted, didn't travel)
  - decent baseline + low near-field   -> far-field dominant (endless-corridor / vanishing point)
"""
import sys, os, struct, argparse
import numpy as np

def read_images_bin(path):
    imgs = {}
    with open(path, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            image_id = struct.unpack('<I', f.read(4))[0]
            q = struct.unpack('<4d', f.read(32))
            t = struct.unpack('<3d', f.read(24))
            struct.unpack('<I', f.read(4))            # camera_id
            name = b''
            while True:
                c = f.read(1)
                if c == b'\x00':
                    break
                name += c
            npts = struct.unpack('<Q', f.read(8))[0]
            f.read(npts * 24)                          # skip 2D points
            imgs[image_id] = (np.array(q), np.array(t))
    return imgs

def qvec2rotmat(q):
    w, x, y, z = q
    return np.array([
        [1-2*y*y-2*z*z, 2*x*y-2*z*w,   2*x*z+2*y*w],
        [2*x*y+2*z*w,   1-2*x*x-2*z*z, 2*y*z-2*x*w],
        [2*x*z-2*y*w,   2*y*z+2*x*w,   1-2*x*x-2*y*y]])

def read_points3d_bin(path):
    pts = []
    with open(path, 'rb') as f:
        n = struct.unpack('<Q', f.read(8))[0]
        for _ in range(n):
            struct.unpack('<Q', f.read(8))[0]          # point id
            xyz = struct.unpack('<3d', f.read(24))
            f.read(3)                                  # rgb
            struct.unpack('<d', f.read(8))[0]          # error
            tl = struct.unpack('<Q', f.read(8))[0]
            track = []
            for _ in range(tl):
                img_id = struct.unpack('<I', f.read(4))[0]
                f.read(4)                              # point2D idx
                track.append(img_id)
            pts.append((np.array(xyz), track))
    return pts

def max_pair_angle(P, cam_ids, centers):
    cc = [centers[i] for i in cam_ids if i in centers]
    if len(cc) < 2:
        return None
    dirs = [(P - c) / (np.linalg.norm(P - c) + 1e-12) for c in cc]
    best = 0.0
    for a in range(len(dirs)):
        for b in range(a + 1, len(dirs)):
            ang = np.degrees(np.arccos(np.clip(dirs[a] @ dirs[b], -1, 1)))
            if ang > best:
                best = ang
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sparse_dir", help="path to COLMAP sparse/0 (with images.bin, points3D.bin)")
    ap.add_argument("--strict", action="store_true", help="require target values, not minimums")
    args = ap.parse_args()

    imb = os.path.join(args.sparse_dir, "images.bin")
    pmb = os.path.join(args.sparse_dir, "points3D.bin")
    if not (os.path.isfile(imb) and os.path.isfile(pmb)):
        print(f"ERROR: images.bin / points3D.bin not found in {args.sparse_dir}")
        return 2

    imgs = read_images_bin(imb)
    pts = read_points3d_bin(pmb)
    centers = {iid: -qvec2rotmat(q).T @ t for iid, (q, t) in imgs.items()}
    Cs = np.array(list(centers.values()))
    if len(Cs) < 2:
        print("ERROR: fewer than 2 registered cameras")
        return 2

    # --- camera motion: principal axes of the camera path ---
    mean_C = Cs.mean(0)
    X = Cs - mean_C
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    std = S / np.sqrt(len(Cs))
    lat_ratio = 100 * std[1] / std[0] if std[0] > 0 else 0.0
    travel_axis = Vt[0]                                  # principal direction of travel
    cam_proj = X @ travel_axis
    baseline = float(cam_proj.max() - cam_proj.min())    # absolute distance traveled

    # --- scene geometry: where do the points live vs the camera path ---
    P = np.array([p for p, _ in pts]) if pts else np.zeros((0, 3))
    near_field = 100.0
    median_depth_ratio = 0.0
    if len(P):
        pt_proj = (P - mean_C) @ travel_axis
        within = (pt_proj >= cam_proj.min()) & (pt_proj <= cam_proj.max())
        near_field = 100 * within.mean()                 # % of points inside the travel envelope
        # median point distance to the NEAREST camera, in units of the baseline
        d = np.linalg.norm(P[:, None, :] - Cs[None, :, :], axis=2).min(1) if len(P) < 20000 \
            else np.array([np.linalg.norm(Cs - p, axis=1).min() for p in P])
        median_depth_ratio = float(np.median(d) / baseline) if baseline > 0 else 0.0

    angs = np.array([a for a in (max_pair_angle(p, tr, centers) for p, tr in pts) if a is not None])
    median_ang = float(np.median(angs)) if len(angs) else 0.0
    pct_under5 = 100 * (angs < 5).mean() if len(angs) else 100.0
    pct_over10 = 100 * (angs > 10).mean() if len(angs) else 0.0

    MIN_ANG, TGT_ANG = 8.0, 12.0
    MIN_LAT, TGT_LAT = 10.0, 20.0
    MIN_NF,  TGT_NF  = 25.0, 40.0
    ang_thr = TGT_ANG if args.strict else MIN_ANG
    lat_thr = TGT_LAT if args.strict else MIN_LAT
    nf_thr  = TGT_NF  if args.strict else MIN_NF

    print("=== PRE-FLIGHT PARALLAX GATE ===")
    print(f"  cameras registered:        {len(Cs)}")
    print(f"  3D points:                 {len(angs)}")
    print(f"  camera baseline (travel):  {baseline:.2f} units")
    print(f"  lateral/forward ratio:     {lat_ratio:.1f}%   (need >= {lat_thr:.0f}%, target {TGT_LAT:.0f}%)")
    print(f"  near-field coverage:       {near_field:.1f}%   (need >= {nf_thr:.0f}%, target {TGT_NF:.0f}%)")
    print(f"  median pt depth / baseline:{median_depth_ratio:6.2f}x (lower is better; >3x = far-field)")
    print(f"  median triangulation angle:{median_ang:6.2f} deg (need >= {ang_thr:.0f}, target {TGT_ANG:.0f})")
    print(f"  points under 5 deg (poor): {pct_under5:.1f}%")
    print(f"  points over 10 deg (good): {pct_over10:.1f}%")

    ok = (median_ang >= ang_thr) and (lat_ratio >= lat_thr) and (near_field >= nf_thr)
    if ok:
        print("RESULT: PASS — enough parallax to reconstruct surfaces.")
        return 0

    # --- name the dominant failure mode so the recapture targets the right lever ---
    print("RESULT: FAIL — insufficient parallax to reconstruct surfaces.")
    scene_scale = float(np.linalg.norm(P.std(0))) if len(P) else 0.0
    rotation_dominant = (lat_ratio < lat_thr) and (baseline < 0.25 * (scene_scale + 1e-9))
    far_field_dominant = (near_field < nf_thr) and (baseline >= 0.25 * (scene_scale + 1e-9))
    if rotation_dominant:
        print("  CAUSE: ROTATION-DOMINANT — the camera pivoted/looked around but barely")
        print("         travelled (small baseline). Pure rotation is a panorama: zero")
        print("         triangulation baseline. FIX: physically move the camera body through")
        print("         space; turning the view does nothing for depth.")
    elif far_field_dominant:
        print("  CAUSE: FAR-FIELD DOMINANT — the camera travelled fine, but the scene recedes")
        print(f"        past the camera path ({near_field:.0f}% of points lie within the travel")
        print("         envelope; the rest are distant corridor near the vanishing point).")
        print("         Distant points subtend tiny angles no matter how far the camera moves.")
        print("         FIX: bound the scene. Pass CLOSE to and LATERALLY PAST near surfaces")
        print("         (hug one wall, cross to the other), shoot corners/doorways/alcoves —")
        print("         NOT an open straight shaft to infinity. See VIDEO_CAPTURE_SPEC.md.")
    else:
        print("  CAUSE: mixed/low parallax. Increase lateral travel AND keep textured surfaces")
        print("         close to the camera. See VIDEO_CAPTURE_SPEC.md.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
