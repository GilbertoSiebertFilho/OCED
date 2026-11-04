# -*- coding: utf-8 -*-
"""sms_swath - reproduction of Ag Leader SMS Advanced "Optimize Swath Widths" (option 2, scale ON).

SMS option 2: "Create individual swath rectangles for overlapping values, remove swaths that overlap completely and
adjust the width of those that partially overlap", with "Scale Per Area attribute values automatically" ON. Used as
step S2 of the OCCD SMS 3-sigma method (clip -> swath -> speed -> moisture -> yield [-> yield]).

The rules were reverse-engineered from SMS's own output: raw vs 3-sigma clean exports of six 2026 trials (Case IH
AFS: T19, T20, T25; John Deere GS4: T22, T23, T29), every clean point matched to its raw reading, plus the SMS log
counts and limits of a seventh (T30, John Deere GS4, no clean export). Numbers in
brackets are the evidence ("abl." = harness ablation of this module, final value -> rule switched off).
The validation of the whole SMS 3-sigma method on these trials is in docs/METHOD.md, section 10.

INPUT CONVENTIONS (important)
  * x_m, y_m in a plane whose +y axis is TRUE north (local transverse Mercator, or `local_plane()` below), not UTM:
    SMS's sideways move of narrowed points is perpendicular to Track within 0.004-0.10 deg in a true-north plane
    but off by the grid convergence in UTM (-1.94 deg on T19, +1.68 deg on T20).
  * x_m, y_m = the point AFTER SMS's Y_Offset move (`apply_y_offset()`): SMS moves every point Y_Offset_f ft to the
    right of travel and sets Y_Offset to 0 (John Deere offsets reach +/-24.75 ft with sections off). With the
    logged point T29 loses 1,307 readings (SMS 438) at narrowing precision 0.15.
  * order = harvest time order across ALL datasets / combines. John Deere exports list the ~17-min .jdl file
    blocks in file-name order, not time order; rebuild the time order first [T29, this module: narrowing recall
    0.86 with real time, 0.71 with the chained block order, 0.28 when the combines are assumed to start together].

GEOMETRY
  R1  A reading is a rectangle with the point on its FRONT edge, extending back along Track by Distance, Swath Width
      wide, centred on the point [277 of the 280 T19 distance cuts remove the back with the point unchanged; the 3
      front cuts move the point back by exactly the cut].
  R2  Readings are processed in time order against a coverage raster (cell_ft) of all earlier KEPT strips (DLL:
      SortTimes, RasterizeSRCoverage, FindUncovered, AdjustSmartRectAndUpdateCoverage). Removed readings burn
      nothing; narrowed / shortened readings burn only their kept strip.

TWO OVERLAP MECHANISMS, split by WHO covers the reading
  R3  Across-track narrowing comes from OLDER readings only; the reading's own predecessor (previous reading of the
      same machine) is ignored [share of sides SMS cuts when the nearest coverer is the predecessor: T19 0.071,
      T25 0.118; when it is an older reading: 0.957 / 0.957, T20 0.994; abl. narrowing precision T19 0.97 -> 0.95,
      T25 0.95 -> 0.91, T22 0.45 -> 0.27, T23 0.40 -> 0.25, T29 0.61 -> 0.56]. This is why the wedges between
      consecutive readings in turns are never cut. The predecessor is found without machine ids: the most recent of
      the previous pred_k readings in order whose point lies within Distance + pred_tol_ft behind, pred_tol_ft
      ahead and pred_tol_ft sideways.
  R4  Along-track (Distance) trimming comes from the predecessor only: when the reading's centre line overlaps the
      predecessor's kept strip at its back (or front) end by >= along_dead_ft, Distance is shortened by the overlap;
      SMS then recomputes Speed = Distance / Duration [T19 cut share by back overlap: 14 % at 2.0-2.5 ft, 52 % at
      2.5-3.0 ft, 84 % at 3.0-4.0 ft; older readings cause 0-2 %; the cut is continuous, cut - overlap median
      -0.008 ft; SMS cut 280 readings on T19 (277 of them 2-s readings), 1 on T20, 6 on T25, 11 on T23, 13 on T29].

ACROSS-TRACK RULE
  R5  The rectangle is split into col_ft columns across the track; a column is covered when > col_cover of its
      cells are covered. For a sharp parallel edge any share between 0.5 and 0.9 gives the same cut (0.5
      reproduces 210 of 210 such edges on T20); for angled (triangular) overlaps 0.6 cuts less, as SMS does [abl.
      0.6 -> 0.5: removed T20 838 -> 860 (SMS 834), T29 448 -> 499 (438), T30 55 -> 60 (47); T22 / T23 precision
      0.45 / 0.40 -> 0.39 / 0.35].
  R6  Seams: older passes are chains of D-long rectangles with 0.1-0.5 ft seams. Uncovered column gaps up to gap_ft
      between covered columns count as covered [abl. gap_ft 0: removed T19 299 -> 275 (SMS 351), T25 584 -> 511,
      T29 448 -> 363; T19 narrowed-width error 0.92 -> 1.62 ft in the forensic study]. With fill_gap a reading
      also burns the gap back to its predecessor when the step exceeds Distance (Case IH GPS jitter: step / D
      q05-q95 0.72-1.24 on T19, 0.77-1.20 on T25, 0.996-1.005 on T29) [abl.: removed T19 299 -> 292, T25 584 ->
      572]. An uncovered edge strip up to edge_gap_ft next to covered columns also counts as covered [abl.
      edge_gap 0: 3-sigma final T20 65,708 -> 66,163 (SMS 65,786), T25 48,601 -> 48,646 (48,515); it costs T19,
      kept agreement 0.9878 -> 0.9906 without it, see KNOWN LIMITS].
  R7  Dead band: a covered run from an edge shorter than dead_band_ft is not cut [T20 P(cut | run): 0.25 at
      2.0-2.5 ft, 0.94 at 2.5-3.0 ft; aligned cuts are never 1 or 2 ft; smallest SMS cut 2.37-2.80 ft]. Readings
      narrower than the full header (sections off, John Deere) use partial_dead_ft: the monitor has already shut
      the overlapping sections and SMS seldom cuts the remaining angled overlaps [SMS cut share for partial-width
      readings crossed at 30-60 deg: 0.11, vs 0.90-0.98 for Case IH; abl. 5 ft -> dead_band_ft: precision T22
      0.45 -> 0.23, T23 0.40 -> 0.16, T29 0.61 -> 0.51, recall 0.50 -> 0.68, 0.51 -> 0.68, 0.86 -> 0.93; widths
      within 0.5 ft T22 0.9986 -> 0.9972, T23 0.9988 -> 0.9970, T29 0.9887 -> 0.9856].
  R8  The cut is whole feet measured from the rectangle EDGE (not a whole new width): round(run) >= min_cut_ft
      [cuts within 0.25 ft of a whole foot: T23 98.1 %, T20 99.5 %, T29 93.2 %, while new widths are whole for only
      50.9 % on T23 (W = 44.5 ft); headings within 0.5 deg of N/E/S/W: 100 % of cuts are whole feet on T19 (840),
      T25 (306), T20 (2,144), T29 (166)]. SMS works on a north-aligned 1-ft grid, so oblique cuts are grid
      diagonals (sqrt 10, sqrt 17, ...); their sub-foot values need SMS's grid phase, which is not reproducible.
  R9  The point moves sideways to the centre of the kept strip: shift = (L - R) / 2, + = right of travel;
      W' = W - L - R. Per-area attributes are scaled by (W * D) / (W' * D') [max |scale / (W D ratio) - 1|
      2.9e-5 over all fields]; Duration, Track, Moisture and Crop Flow are unchanged.

REMOVAL ("overlaps completely")
  R10 A reading is removed when (a) every column is covered after R6, or (b) >= remove_cov of its rectangle is
      covered by older readings [T20 must-go readings: median covered share 0.98; kept readings never reach 0.95
      on T19, T20, T25; (b) changes 0-4 readings per field once (a) is in place], or (c) the along trim leaves no
      length, or (d) W' < min_w_ft. SMS keeps narrow slivers (T19 pass-1 yield max 3,989 bu/ac, SD 61.7), so
      min_w_ft is small.

KNOWN LIMITS
  * John Deere: SMS narrowed only 28 / 53 / 411 readings on T22 / T23 / T29; narrowing precision here is 0.45 /
    0.40 / 0.61, and T23 removes 174 vs SMS 226 (T22 / T23 orders are reconstructions; the T29 width truth comes
    from a run clipped to an unknown boundary).
  * Slivers: SMS keeps more extreme slivers than this model on T19, T23 and T29 (T19 pass-1 upper yield limit
    260.45 vs 155 here) but fewer on T25 and T20; no single edge-strip rule fits all fields.
  * T19: about 30 SMS removals follow from 1-s display-time ties in SMS's internal order; exports carry only the
    date, so they cannot be reproduced. Distance cuts on the readings in SMS's clean export: 408 vs SMS 280 (628 over all
    active readings; SMS ramps between 2 and 4 ft of overlap).
  * Sub-foot oblique widths need SMS's grid phase (narrowed widths within 1 ft: T20 0.91, T19 0.68, T25 0.70).

Dependencies: numpy only. Performance: 27.8 s for T29 (78,887 readings, 4 combines, real-time order) on the OCCD
PC; candidate peak memory 0.56 GB (tracemalloc 0.61 GB), coverage raster 442 MB at cell_ft 0.25.
"""
import time
import numpy as np

FT = 0.3048                      # metres per foot

DEFAULTS = {
    "cell_ft": 0.25,             # coverage raster cell size (ft)
    "col_ft": 0.25,              # across-track column width used for the coverage test (ft)
    "col_cover": 0.6,            # a column is covered when more than this share of its cells is covered
    "dead_band_ft": 2.75,        # covered edge runs shorter than this are ignored (no cut)
    "partial_dead_ft": 5.0,      # dead band for readings narrower than the full header; None = dead_band_ft
    "min_cut_ft": 3.0,           # smallest across cut (ft)
    "round_ft": 1.0,             # across cut quantum (whole feet from the edge); 0 = continuous
    "gap_ft": 2.75,              # uncovered column gaps up to this width between covered columns are closed
    "edge_gap_ft": 2.0,          # an uncovered edge strip up to this width next to covered columns is closed
    "remove_cov": 0.95,          # removed when this share of the rectangle is covered by older readings
    "min_w_ft": 0.5,             # removed when the kept width is below this (ft)
    "along_dead_ft": 2.5,        # predecessor overlaps along track shorter than this are ignored (ft)
    "fill_gap": True,            # burn the gap back to the predecessor when the step is longer than Distance
    "fill_max": 2.0,             # ... at most up to fill_max x Distance behind the point
    "fill_lat_ft": 2.0,          # ... only when the predecessor is within this lateral offset (ft)
    "fill_dh_deg": 20.0,         # ... and within this heading change (deg)
    "exclude_pred": True,        # ignore the predecessor's coverage in the across test (R3)
    "pred_k": 8,                 # predecessor searched among the previous pred_k readings in order
    "pred_tol_ft": 6.0,          # predecessor search window (ft), see R3
    "chunk": 512,                # readings rasterised per vectorised batch (memory / speed trade-off)
}

# reason codes in the returned "reason" array
KEPT, REM_ALONG, REM_COLUMNS, REM_SLIVER, REM_COVER = 0, 1, 2, 3, 5
REASONS = {KEPT: "kept", REM_ALONG: "along trim leaves no length", REM_COLUMNS: "every column covered",
           REM_SLIVER: "kept width < min_w_ft", REM_COVER: "covered share >= remove_cov"}


# ----------------------------------------------------------------------------------------------------------------
# Helpers for callers (OCCD)
# ----------------------------------------------------------------------------------------------------------------
def local_plane(lon, lat, lon0=None, lat0=None):
    """Project WGS84 lon/lat (deg) to a local true-north plane in metres (equirectangular at lat0 with the WGS84
    meridian and prime-vertical radii). Against the local transverse Mercator used for validation it differs by
    at most 0.16 m in position, 1.8e-4 in distance and 0.015 deg in bearing on 1.6-km fields (T23, T29), far below
    what the swath step can see. Returns x_m, y_m, (lon0, lat0); lon0/lat0 default to the data median."""
    lon = np.asarray(lon, float); lat = np.asarray(lat, float)
    lon0 = float(np.nanmedian(lon)) if lon0 is None else float(lon0)
    lat0 = float(np.nanmedian(lat)) if lat0 is None else float(lat0)
    a, e2 = 6378137.0, 6.69437999014e-3
    p = np.radians(lat0)
    s2 = 1.0 - e2 * np.sin(p) ** 2
    m_rad = a * (1 - e2) / s2 ** 1.5          # meridian radius
    n_rad = a / np.sqrt(s2)                   # prime-vertical radius
    x = np.radians(lon - lon0) * n_rad * np.cos(p)
    y = np.radians(lat - lat0) * m_rad
    return x, y, (lon0, lat0)


def apply_y_offset(x_m, y_m, heading_deg, y_offset_ft):
    """Move each logged point Y_Offset_f feet to the right of travel, as SMS does before (and in) the swath step.
    Returns the moved x_m, y_m; pass these to optimize_swath and use them as the output positions."""
    h = np.radians(np.asarray(heading_deg, float))
    off = np.nan_to_num(np.asarray(y_offset_ft, float)) * FT
    return np.asarray(x_m, float) + off * np.cos(h), np.asarray(y_m, float) - off * np.sin(h)


# ----------------------------------------------------------------------------------------------------------------
# Raster and vectorised rectangle rasterisation
# ----------------------------------------------------------------------------------------------------------------
class _Grid:
    """Boolean coverage raster (flat, row-major), cells aligned to x east / y north."""

    def __init__(self, x_m, y_m, pad_m, cell_m):
        self.cs = float(cell_m)
        self.x0 = float(np.min(x_m) - pad_m)
        self.y0 = float(np.min(y_m) - pad_m)
        self.nx = int(np.ceil((np.max(x_m) + pad_m - self.x0) / self.cs)) + 1
        self.ny = int(np.ceil((np.max(y_m) + pad_m - self.y0) / self.cs)) + 1
        self.cov = np.zeros(self.nx * self.ny, dtype=bool)


def _interval(p, f, c, lo, hi):
    """x-interval where lo <= (x - p) * f + c <= hi, vectorised; f may be 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        a = p + (lo - c) / f
        b = p + (hi - c) / f
    xa = np.where(f > 0, a, b)
    xb = np.where(f > 0, b, a)
    z = np.abs(f) < 1e-12
    inside = (c >= lo) & (c <= hi)
    xa = np.where(z, np.where(inside, -np.inf, np.inf), xa)
    xb = np.where(z, np.where(inside, np.inf, -np.inf), xb)
    return xa, xb


def _rect_cells(g, px, py, fx, fy, back_m, half_m):
    """Cells whose centres lie inside many rectangles at once (scanline per raster row). Rectangle k: reference point
    (px, py) on its front edge, unit forward vector (fx, fy), extending back_m behind and half_m to each side.
    Returns offs (n + 1), flat cell indices, v = across (m, + right) and u = along (m, + forward) of each cell
    centre relative to the reference point."""
    n = px.size
    ry = -fx
    cu = np.stack([-back_m, -back_m, np.zeros(n), np.zeros(n)], 1)
    cv = np.stack([-half_m, half_m, half_m, -half_m], 1)
    Y = py[:, None] + cu * fy[:, None] + cv * ry[:, None]
    cs = g.cs
    j0 = np.maximum(np.ceil((Y.min(1) - g.y0) / cs - 0.5), 0).astype(np.int64)
    j1 = np.minimum(np.floor((Y.max(1) - g.y0) / cs - 0.5), g.ny - 1).astype(np.int64)
    nr = np.maximum(j1 - j0 + 1, 0)
    R = int(nr.sum())
    idt = np.int32 if g.nx * g.ny < 2 ** 31 - 1 else np.int64
    if R == 0:
        return np.zeros(n + 1, np.int64), np.zeros(0, idt), np.zeros(0, np.float32), np.zeros(0, np.float32)
    rk = np.repeat(np.arange(n), nr)
    jj = j0[rk] + (np.arange(R) - np.repeat(np.cumsum(nr) - nr, nr))
    dy = g.y0 + (jj + 0.5) * cs - py[rk]
    a1, b1 = _interval(px[rk], fx[rk], dy * fy[rk], -back_m[rk], np.zeros(R))
    a2, b2 = _interval(px[rk], fy[rk], -dy * fx[rk], -half_m[rk], half_m[rk])
    xa = np.maximum(a1, a2); xb = np.minimum(b1, b2)
    ok = xa <= xb
    i0 = np.where(ok, np.maximum(np.ceil((np.where(ok, xa, 0) - g.x0) / cs - 0.5), 0), 0).astype(np.int64)
    i1 = np.where(ok, np.minimum(np.floor((np.where(ok, xb, 0) - g.x0) / cs - 0.5), g.nx - 1), -1).astype(np.int64)
    cnt = np.maximum(i1 - i0 + 1, 0)
    C = int(cnt.sum())
    per = np.bincount(rk, weights=cnt, minlength=n).astype(np.int64)
    offs = np.r_[0, np.cumsum(per)]
    if C == 0:
        return offs, np.zeros(0, idt), np.zeros(0, np.float32), np.zeros(0, np.float32)
    cstart = np.cumsum(cnt) - cnt
    ar = np.arange(C, dtype=idt)
    flat = ar + np.repeat((jj * g.nx + i0 - cstart).astype(idt), cnt)
    dx0 = g.x0 + (i0 + 0.5) * cs - px[rk]
    arf = ar.astype(np.float64)
    v0 = dx0 * fy[rk] - dy * fx[rk]; dv = cs * fy[rk]
    v = (np.repeat(v0 - cstart * dv, cnt) + arf * np.repeat(dv, cnt)).astype(np.float32)
    u0 = dx0 * fx[rk] + dy * fy[rk]; du = cs * fx[rk]
    u = (np.repeat(u0 - cstart * du, cnt) + arf * np.repeat(du, cnt)).astype(np.float32)
    return offs, flat, v, u


# ----------------------------------------------------------------------------------------------------------------
# Small helpers of the across test
# ----------------------------------------------------------------------------------------------------------------
def _run(flags):
    """Length of the leading run of True."""
    if flags.size == 0 or not flags[0]:
        return 0
    k = int(np.argmin(flags))
    return flags.size if flags[k] else k


def _close_gaps(flags, k):
    """Set False runs of length <= k that have True on both sides."""
    if k <= 0 or flags.all() or not flags.any():
        return flags
    f = flags.copy()
    idx = np.flatnonzero(flags)
    for a, g_ in zip(idx[:-1], np.diff(idx) - 1):
        if 0 < g_ <= k:
            f[a + 1:a + 1 + g_] = True
    return f


def _predecessors(x_m, y_m, fx, fy, D, seq, k, tol_ft):
    """pred[i] = the most recent of the previous k readings in seq whose point lies within D_i + tol behind, tol
    ahead and tol sideways of reading i (same machine, consecutive in time); -1 when none."""
    n = x_m.size
    pred = np.full(n, -1, np.int64)
    m = seq.size
    if m < 2:
        return pred
    arg = np.full(m, -1, np.int64)
    xs, ys, fxs, fys, Ds = x_m[seq], y_m[seq], fx[seq], fy[seq], D[seq]
    for lag in range(1, min(k, m - 1) + 1):
        j = seq[:-lag]
        dx = (x_m[j] - xs[lag:]) / FT; dy = (y_m[j] - ys[lag:]) / FT
        al = dx * fxs[lag:] + dy * fys[lag:]
        la = dx * fys[lag:] - dy * fxs[lag:]
        ok = (arg[lag:] < 0) & (al >= -Ds[lag:] - tol_ft) & (al <= tol_ft) & (np.abs(la) <= tol_ft)
        arg[lag:] = np.where(ok, j, arg[lag:])
    pred[seq] = arg
    return pred


def _centre_line_in_strip(dx, dy, fxi, fyi, d, fxq, fyq, strip):
    """Interval [lo, hi] of u in [-d, 0] where the centre-line point (point_i + u * fwd_i) lies inside the kept strip
    of the predecessor q. dx, dy: point_i - point_q (ft); strip = (back, front, left, right) in q's frame (ft)."""
    rxq, ryq = fyq, -fxq
    a0 = dx * fxq + dy * fyq; a1 = fxi * fxq + fyi * fyq          # along_q(u) = a0 + a1 u
    b0 = dx * rxq + dy * ryq; b1 = fxi * rxq + fyi * ryq          # across_q(u) = b0 + b1 u
    lo, hi = -d, 0.0
    kb, kf, kl, kr = strip
    for c0, c1, l1, l2 in ((a0, a1, kb, kf), (b0, b1, kl, kr)):
        if abs(c1) < 1e-9:
            if not (l1 <= c0 <= l2):
                return 1.0, 0.0
        else:
            ta = (l1 - c0) / c1; tb = (l2 - c0) / c1
            if ta > tb:
                ta, tb = tb, ta
            lo = max(lo, ta); hi = min(hi, tb)
    return lo, hi


# ----------------------------------------------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------------------------------------------
def optimize_swath(x_m, y_m, heading_deg, dist_ft, width_ft, order, active=None, params=None):
    """SMS "Optimize Swath Widths" (option 2, scale ON) for one instance / task.

    x_m, y_m      projected coordinates (m) of each reading in a TRUE-NORTH plane, after the Y_Offset move (see the
                  module docstring, `local_plane`, `apply_y_offset`).
    heading_deg   Track, degrees clockwise from north.  dist_ft, width_ft: logged Distance and Swath Width (ft).
    order         int array of reading indices in processing (harvest time) order across all datasets / combines.
    active        bool mask; only active readings take part (inactive: neither tested nor burnt). None = all.
                  A reading without a finite position, heading or width (> 0) is inactive as well.
    params        overrides of DEFAULTS.

    Returns a dict of arrays of length n:
      removed       active and removed as fully overlapped
      width_ft_new  new width (= width_ft when unchanged; NaN for inactive or removed)
      dist_ft_new   new Distance (= dist_ft when unchanged; NaN for inactive or removed). SMS shortens Distance on
                    some readings and recomputes Speed = Distance / Duration.
      scale         multiplier of per-area attributes (Yld_Vol_Dr, Yld_Mass_*, Fuel per area ...):
                    (W * D) / (W' * D') for kept active readings (= W / W' when D is unchanged), else 1.0.
                    Prod_ac_h (area rate) and area per fuel are divided by it, i.e. multiplied by (W' * D') / (W * D).
      shift_ft      signed lateral move of the point to the centre of the kept strip, + = right of travel
      dx_m, dy_m    the total point move in x / y metres (lateral move, plus the move back by a front trim)
      covered_frac  share of the reading's rectangle already covered by older readings when processed (the
                    predecessor excluded); NaN for inactive readings
      reason        int8 removal reason (REASONS), 0 for kept / inactive
      stats         n_active, n_removed, n_narrowed, n_dist_cut, seconds, raster cells / MB, ...
    """
    t_start = time.perf_counter()
    p = dict(DEFAULTS); p.update(params or {})
    unknown = set(p) - set(DEFAULTS)
    if unknown:
        raise KeyError(f"unknown parameter(s): {sorted(unknown)}")
    x_m = np.asarray(x_m, float); y_m = np.asarray(y_m, float)
    n = x_m.size
    W = np.asarray(width_ft, float); D = np.asarray(dist_ft, float)
    act = np.ones(n, bool) if active is None else np.asarray(active, bool).copy()
    act &= (np.isfinite(x_m) & np.isfinite(y_m) & np.isfinite(W) & (W > 0)
            & np.isfinite(np.asarray(heading_deg, float)))
    h = np.radians(np.asarray(heading_deg, float))
    FX, FY = np.sin(h), np.cos(h)                 # forward unit vector (x east, y north)
    RX, RY = FY, -FX                              # right unit vector
    out = dict(removed=np.zeros(n, bool), width_ft_new=np.where(act, W, np.nan),
               dist_ft_new=np.where(act, D, np.nan), scale=np.ones(n), shift_ft=np.zeros(n), dx_m=np.zeros(n),
               dy_m=np.zeros(n), covered_frac=np.full(n, np.nan), reason=np.zeros(n, np.int8))
    order = np.asarray(order, np.int64)
    seq = order[act[order]]
    if seq.size == 0:
        out["stats"] = dict(n_active=0, n_removed=0, n_narrowed=0, n_dist_cut=0,
                            seconds=round(time.perf_counter() - t_start, 3))
        return out

    cs = float(p["cell_ft"]); colw = float(p["col_ft"])
    dead = float(p["dead_band_ft"]); adead = float(p["along_dead_ft"])
    pdead = dead if p["partial_dead_ft"] is None else float(p["partial_dead_ft"])
    ccv = float(p["col_cover"]); mincut = float(p["min_cut_ft"]); rnd = float(p["round_ft"])
    minw = float(p["min_w_ft"]); rmc = float(p["remove_cov"]); expred = bool(p["exclude_pred"])
    gapk = int(round(p["gap_ft"] / colw)); egk = int(round(p["edge_gap_ft"] / colw))

    D0 = np.nan_to_num(D, nan=0.0)
    Dm = np.maximum(D0, cs)                       # zero-length readings still get one cell row
    pred = _predecessors(x_m, y_m, FX, FY, D0, seq, int(p["pred_k"]), float(p["pred_tol_ft"]))
    ext = np.zeros(n)                             # burnt-only extension behind the rectangle (fill_gap)
    if p["fill_gap"]:
        cu = seq[pred[seq] >= 0]; pv = pred[cu]
        dxp = (x_m[cu] - x_m[pv]) / FT; dyp = (y_m[cu] - y_m[pv]) / FT
        al = dxp * FX[cu] + dyp * FY[cu]; la = dxp * FY[cu] - dyp * FX[cu]
        dh = np.abs(((np.degrees(h[cu] - h[pv]) + 180.0) % 360.0) - 180.0)
        ok = (np.abs(la) < p["fill_lat_ft"]) & (dh < p["fill_dh_deg"]) & (al > Dm[cu])
        ext[cu[ok]] = np.minimum(al[ok] - Dm[cu[ok]], (p["fill_max"] - 1.0) * Dm[cu[ok]])
    g = _Grid(x_m[seq], y_m[seq], (np.max(W[seq]) + np.max(Dm[seq] + ext[seq])) * FT + 1.0, cs * FT)
    cov = g.cov
    wfull = float(np.nanmax(W[seq]))              # full header width (partial widths = sections off)

    # kept strip of every processed reading, in its own frame (ft): u in [kb, kf] along, v in [kl, kr] across
    kb = np.zeros(n); kf = np.zeros(n); kl = np.zeros(n); kr = np.zeros(n)
    kept_flag = np.zeros(n, bool)
    new_cells = {}                                # recent kept readings -> raster cells they newly covered
    recent = []
    n_nar = n_rem = n_dcut = 0

    def remove(i, why):
        nonlocal n_rem
        out["removed"][i] = True; out["width_ft_new"][i] = np.nan; out["dist_ft_new"][i] = np.nan
        out["reason"][i] = why
        n_rem += 1

    for c0 in range(0, seq.size, int(p["chunk"])):
        ids = seq[c0:c0 + int(p["chunk"])]
        offs, flat, vv, uu = _rect_cells(g, x_m[ids], y_m[ids], FX[ids], FY[ids], (Dm[ids] + ext[ids]) * FT,
                                         W[ids] / 2 * FT)
        vft = vv / np.float32(FT); uft = uu / FT
        for j, i in enumerate(ids):
            s, e = offs[j], offs[j + 1]
            w = W[i]; d = Dm[i]
            fi_all = flat[s:e]; v_all = vft[s:e]; u_all = uft[s:e]
            if ext[i] > 0:                        # test only the rectangle itself; the extension is burnt only
                core = u_all >= -d - 1e-6
                fi = fi_all[core]; vj = v_all[core]; uj = u_all[core]
            else:
                fi = fi_all; vj = v_all; uj = u_all
            if fi.size == 0:                      # rectangle smaller than a cell: kept unchanged
                out["covered_frac"][i] = 0.0
                kept_flag[i] = True; kl[i] = -w / 2; kr[i] = w / 2; kb[i] = -d; kf[i] = 0.0
                continue
            ntot = fi.size
            q = pred[i] if (pred[i] >= 0 and kept_flag[pred[i]]) else -1

            # coverage by OLDER readings: the predecessor's own cells are hidden during the test (R3)
            pc = new_cells.get(q) if (q >= 0 and expred) else None
            if pc is not None and pc.size:
                cov[pc] = False
            c = cov[fi]
            if pc is not None and pc.size:
                cov[pc] = True
            nc = int(np.count_nonzero(c))
            out["covered_frac"][i] = nc / ntot

            # R4: along-track trim from the predecessor's kept strip, measured on the centre line
            B = Fr = 0.0
            if q >= 0:
                lo, hi = _centre_line_in_strip((x_m[i] - x_m[q]) / FT, (y_m[i] - y_m[q]) / FT, FX[i], FY[i], d,
                                               FX[q], FY[q], (kb[q], kf[q], kl[q], kr[q]))
                if hi > lo:
                    if lo <= -d + 1e-6:
                        B = d if hi >= -1e-6 else hi + d
                    elif hi >= -1e-6:
                        Fr = -lo
                    if B < d:
                        B = B if B >= adead else 0.0
                        Fr = Fr if Fr >= adead else 0.0
            dn = d - B - Fr
            if dn <= 1e-9:
                remove(i, REM_ALONG)
                continue
            # R10b: (almost) completely covered
            if nc >= rmc * ntot:
                remove(i, REM_COVER)
                continue

            # R5-R8: across-track cut on the along-kept part of the rectangle
            L = R = 0.0
            sub = None
            if B > 0 or Fr > 0:
                sub = (uj >= -d + B - 1e-6) & (uj <= -Fr + 1e-6)
            if nc:
                vs = vj if sub is None else vj[sub]
                cc = c if sub is None else c[sub]
                # quick skip: no covered cell close enough to an edge for a cut beyond the dead band
                if cc.any() and float(np.max(np.abs(vs[cc]))) >= w / 2 - min(dead, pdead) + colw:
                    ncol = max(int(round(w / colw)), 1)
                    cj = np.clip(((vs + w / 2) / colw).astype(np.int64), 0, ncol - 1)
                    tot = np.bincount(cj, minlength=ncol); hit = np.bincount(cj[cc], minlength=ncol)
                    colcov = (hit > ccv * tot) & (tot > 0)
                    if np.any(tot == 0):          # columns without a cell centre take the previous column's value
                        k_ = np.where(tot > 0, np.arange(ncol), 0); np.maximum.accumulate(k_, out=k_)
                        colcov = colcov[k_]
                    if gapk:
                        colcov = _close_gaps(colcov, gapk)
                    if egk and colcov.any() and not colcov.all():
                        k0 = _run(~colcov)
                        if 0 < k0 <= egk:
                            colcov[:k0] = True
                        k1 = _run(~colcov[::-1])
                        if 0 < k1 <= egk:
                            colcov[ncol - k1:] = True
                    nl = _run(colcov); nr = _run(colcov[::-1])
                    if nl >= ncol:
                        remove(i, REM_COLUMNS)
                        continue
                    dd = dead if w >= wfull - 0.5 else pdead
                    L = nl * colw if nl * colw >= dd else 0.0
                    R = nr * colw if nr * colw >= dd else 0.0
                    if rnd:
                        if L > 0:
                            L = max(np.round(L / rnd) * rnd, mincut)
                        if R > 0:
                            R = max(np.round(R / rnd) * rnd, mincut)
            wn = w - L - R
            if wn < minw:
                remove(i, REM_SLIVER)
                continue

            # R9: outputs
            sh = (L - R) / 2.0
            mx = sh * FT * RX[i]; my = sh * FT * RY[i]
            if Fr > 0:                            # a front trim moves the point back by the trim
                mx -= Fr * FT * FX[i]; my -= Fr * FT * FY[i]
            if L > 0 or R > 0:
                n_nar += 1
                out["width_ft_new"][i] = wn
            if B > 0 or Fr > 0:
                n_dcut += 1
                out["dist_ft_new"][i] = D0[i] - B - Fr if D0[i] > B + Fr else dn
            out["shift_ft"][i] = sh
            out["dx_m"][i] = mx; out["dy_m"][i] = my
            dnew = out["dist_ft_new"][i]
            wnew = out["width_ft_new"][i]
            out["scale"][i] = (w * D0[i]) / (wnew * dnew) if (D0[i] > 0 and dnew > 0) else w / wnew

            # burn the kept strip and remember the cells it newly covered (for the predecessor rule)
            if L > 0 or R > 0 or B > 0 or Fr > 0:
                keep = (vj >= -w / 2 + L) & (vj <= w / 2 - R)
                if sub is not None:
                    keep &= sub
                kc = fi[keep]
            else:
                kc = fi
            if ext[i] > 0 and B == 0:             # fill_gap: also burn the gap back to the predecessor
                kc = np.concatenate([kc, fi_all[~core & (v_all >= -w / 2 + L) & (v_all <= w / 2 - R)]])
            nw = kc[~cov[kc]]
            cov[nw] = True
            new_cells[i] = nw
            recent.append(i)
            if len(recent) > 64:
                new_cells.pop(recent.pop(0), None)
            kept_flag[i] = True
            kl[i] = -w / 2 + L; kr[i] = w / 2 - R; kb[i] = -d + B; kf[i] = -Fr

    out["stats"] = dict(n_active=int(act.sum()), n_removed=n_rem, n_narrowed=n_nar, n_dist_cut=n_dcut,
                        n_with_predecessor=int(np.sum(pred[seq] >= 0)),
                        removed_by_reason={REASONS[k]: int(np.sum(out["reason"] == k)) for k in REASONS if k},
                        seconds=round(time.perf_counter() - t_start, 2), raster_cells=int(g.nx * g.ny),
                        raster_mb=round(cov.nbytes / 2 ** 20, 1), cell_ft=cs)
    return out
