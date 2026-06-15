#!/usr/bin/env python3
"""Produce the final corridor GDGS asset: strip NaN/Inf splats, then cull floaters.

Floaters are a handful of far-flung and/or giant low-opacity Gaussians that
~2x-inflate the cloud AABB, wrecking camera framing. We cull them at the PLY
level so the AABB tightens onto the real corridor automatically.

Pipeline (in order), each step a single boolean mask over the same array:
  0. finite        : drop any vertex with a non-finite float field.
  1. position cull : drop vertices whose x, y, or z is outside [P0.5, P99.5].
  2. scale cull    : 3DGS scale_i are LOG scales; extent_i = exp(scale_i).
                     drop vertices whose max extent exceeds P99 of max-extent.

Opacity is reported (sigmoid(opacity) min/median/max) but NOT culled by default,
to avoid deleting faint real surfaces.

Header is preserved verbatim except the `element vertex N` line.

Usage:
    cull_floaters.py <input.ply> <output.ply>
"""

import sys

import numpy as np

POS_LOW_PCT = 0.5
POS_HIGH_PCT = 99.5
SCALE_HIGH_PCT = 99.0


def parse_header(raw: bytes):
    marker = b"end_header\n"
    idx = raw.find(marker)
    if idx == -1:
        raise SystemExit("ERROR: no end_header found; not an ASCII-header PLY")
    header_len = idx + len(marker)
    lines = raw[:idx].decode("ascii").splitlines()
    if not lines or lines[0].strip() != "ply":
        raise SystemExit("ERROR: missing 'ply' magic")
    fmt = next((l for l in lines if l.startswith("format")), "")
    if "binary_little_endian" not in fmt:
        raise SystemExit("ERROR: only binary_little_endian PLY supported, got: %r" % fmt)
    props = []
    vertex_count = None
    in_vertex = False
    for l in lines:
        parts = l.split()
        if not parts:
            continue
        if parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                vertex_count = int(parts[2])
        elif parts[0] == "property" and in_vertex:
            if parts[1] != "float":
                raise SystemExit("ERROR: expected all-float vertex props, got %r" % parts[1])
            props.append(parts[2])
    if vertex_count is None:
        raise SystemExit("ERROR: no 'element vertex N' found")
    return header_len, props, vertex_count, lines


def rebuild_header(header_lines, kept):
    out = []
    in_vertex = False
    for l in header_lines:
        parts = l.split()
        if parts and parts[0] == "element":
            in_vertex = parts[1] == "vertex"
            if in_vertex:
                out.append("element vertex %d" % kept)
                continue
        out.append(l)
    return ("\n".join(out) + "\nend_header\n").encode("ascii")


def col(props, name):
    return props.index(name)


def aabb(arr, ix, iy, iz):
    mn = arr[:, [ix, iy, iz]].min(axis=0)
    mx = arr[:, [ix, iy, iz]].max(axis=0)
    return mn, mx, mx - mn


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: cull_floaters.py <input.ply> <output.ply>")
    in_path, out_path = sys.argv[1], sys.argv[2]

    with open(in_path, "rb") as f:
        raw = f.read()

    header_len, props, vertex_count, header_lines = parse_header(raw)
    ncols = len(props)
    rec = ncols * 4
    body = raw[header_len:]
    exp = vertex_count * rec
    if len(body) < exp:
        raise SystemExit("ERROR: body too short: %d < %d" % (len(body), exp))
    arr = np.frombuffer(body[:exp], dtype="<f4").reshape(vertex_count, ncols)

    ix, iy, iz = col(props, "x"), col(props, "y"), col(props, "z")
    isc = [col(props, "scale_0"), col(props, "scale_1"), col(props, "scale_2")]
    iop = col(props, "opacity")

    input_count = vertex_count

    # 0. finite
    finite_mask = np.isfinite(arr).all(axis=1)
    after_nan = int(finite_mask.sum())

    # 1. position cull (percentiles computed on finite rows only)
    fin = arr[finite_mask]
    xyz = fin[:, [ix, iy, iz]]
    lo = np.percentile(xyz, POS_LOW_PCT, axis=0)
    hi = np.percentile(xyz, POS_HIGH_PCT, axis=0)
    pos_ok_fin = ((xyz >= lo) & (xyz <= hi)).all(axis=1)
    after_position = int(pos_ok_fin.sum())

    # 2. scale cull (LOG scale -> exp extent); percentile on position-survivors
    surv = fin[pos_ok_fin]
    max_extent = np.exp(surv[:, isc]).max(axis=1)
    scale_thr = np.percentile(max_extent, SCALE_HIGH_PCT)
    scale_ok = max_extent <= scale_thr
    after_scale = int(scale_ok.sum())

    kept_rows = surv[scale_ok]
    final_kept = kept_rows.shape[0]

    # opacity report (sigmoid), not culled
    op_sig = 1.0 / (1.0 + np.exp(-kept_rows[:, iop]))
    op_min, op_med, op_max = float(op_sig.min()), float(np.median(op_sig)), float(op_sig.max())

    mn, mx, size = aabb(kept_rows, ix, iy, iz)

    with open(out_path, "wb") as f:
        f.write(rebuild_header(header_lines, final_kept))
        f.write(np.ascontiguousarray(kept_rows, dtype="<f4").tobytes())

    print("input_count=%d" % input_count)
    print("after_nan=%d (dropped %d)" % (after_nan, input_count - after_nan))
    print("after_position_cull=%d (dropped %d)" % (after_position, after_nan - after_position))
    print("after_scale_cull=%d (dropped %d)" % (after_scale, after_position - after_scale))
    print("final_kept=%d" % final_kept)
    print("scale_extent_P99_threshold=%.4f" % scale_thr)
    print("opacity_sigmoid min/median/max = %.4f / %.4f / %.4f" % (op_min, op_med, op_max))
    print("tight_AABB min = (%.4f, %.4f, %.4f)" % (mn[0], mn[1], mn[2]))
    print("tight_AABB max = (%.4f, %.4f, %.4f)" % (mx[0], mx[1], mx[2]))
    print("tight_AABB size = (%.4f, %.4f, %.4f)" % (size[0], size[1], size[2]))


if __name__ == "__main__":
    main()
