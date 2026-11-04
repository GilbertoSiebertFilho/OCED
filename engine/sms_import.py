# -*- coding: utf-8 -*-
"""Import as SMS: the Processing Settings Ag Leader SMS Advanced applies when it imports a harvest (Grain Harvest
operation), so that the data OCED maps and cleans is the data SMS would hold after its import.

    from engine import sms_import as si
    S = si.settings({"product": "barley"})          # every key, validated (missing keys = SMS's defaults)
    R = si.resolve(S, crop="barley")                # the values of one file: product defaults filled in
    rep = si.apply(shp, out_shp, R)                 # writes the imported file (records byte for byte, cells patched)

SMS's settings (Processing Settings of a Grain Harvest operation), with its defaults per physical product:
    Weight To Volume (lb/bu) and Dry Moisture (%)  wheat 60.00 / 13.50, barley 48.00 / 14.50 (SMS, Wheat - Spring and
                                                   Barley - Fall); another crop: engine.formats.common.CROPS
    Expand Dry Moisture       off: grain drier than the dry moisture is not raised (one-sided shrink); on: symmetric
    Use Manual Swath          off; Manual Swath Width 15.00 ft (the per-area values are scaled by logged / manual)
    Use Manual Moisture       off; Manual Moisture = the dry moisture
    Min. Yield Volume         5.000 bu/ac (a reading with no dry yield or one below it is left out)
    Max. Yield Volume         wheat 300.00, barley 200.00 bu/ac (above it left out); another crop 300.00
    Start Delay / Stop Delay  0.00 s: the first / last seconds of every pass left out (grain filling / draining)
    Flow Shift                0.00 s: the grain mass of a reading moved to the position logged that many seconds
                              earlier (positive) or later (negative), within each logged sequence

Checked on an SMS export (Barley - Fall): wet mass / wet volume = 48.000 lb/bu, dry / wet volume = (100 - M) /
(100 - 14.5) above 14.5 % and exactly 1 below it, no reading below 5.01 bu/ac. Pure Python (no Streamlit).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from engine.formats import common

PRODUCT_DEFAULTS = {          # SMS's Processing Settings per physical product: (lb/bu, dry moisture %, max bu/ac)
    "wheat": (60.0, 13.5, 300.0),
    "barley": (48.0, 14.5, 200.0),
}
MAX_YIELD_OTHER = 300.0
DEFAULTS = {
    "on": True,
    "product": None,                  # a key of common.CROPS; None = the crop of the data
    "test_weight_lb_bu": None,        # Weight To Volume; None = the product's
    "dry_moisture_pct": None,         # Dry Moisture; None = the product's
    "expand_dry_moisture": False,
    "use_manual_swath": False,
    "manual_swath_ft": 15.0,
    "use_manual_moisture": False,
    "manual_moisture_pct": None,      # None = the dry moisture
    "min_yield": 5.0,                 # Min. Yield Volume (bu/ac); None = no minimum
    "max_yield": None,                # Max. Yield Volume (bu/ac); None = the product's
    "start_delay_s": 0.0,
    "stop_delay_s": 0.0,
    "flow_shift_s": 0.0,
}
PASS_BREAK_M = 15.0                   # a pass ends where the next reading is farther than this (as the engine)
PASS_BREAK_DEG = 60.0                 # or turns by more than this
PER_AREA = ("Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr")


def crop_key(text) -> str | None:
    """The common.CROPS key a crop name points at ('Barley - Fall' -> barley, 'crop 48 (wheat?)' -> wheat), else None."""
    s = str(text or "").strip().lower()
    if not s:
        return None
    if s in common.CROPS:
        return s
    for k in sorted(common.CROPS, key=len, reverse=True):     # 'durum' before a shorter name inside it
        if k in s:
            return k
    return None


def product_defaults(crop) -> tuple[float | None, float | None, float]:
    """(weight to volume, dry moisture, max yield volume) of a product: SMS's for wheat and barley, the crop table and
    300 bu/ac for another crop, (None, None, 300) when the crop is unknown."""
    k = crop_key(crop)
    if k in PRODUCT_DEFAULTS:
        return PRODUCT_DEFAULTS[k]
    tw, ms = common.CROPS.get(k, (None, None)) if k else (None, None)
    return tw, ms, MAX_YIELD_OTHER


def settings(S: dict | None = None) -> dict:
    """Every key of DEFAULTS, the given ones validated."""
    out = dict(DEFAULTS)
    for k, v in (S or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"unknown SMS import setting {k!r}")
        out[k] = v
    for k in ("expand_dry_moisture", "use_manual_swath", "use_manual_moisture", "on"):
        out[k] = bool(out[k])
    for k, lo, hi in (("test_weight_lb_bu", 1, 200), ("dry_moisture_pct", 0, 60), ("manual_swath_ft", 0.1, 300),
                      ("manual_moisture_pct", 0, 80), ("min_yield", 0, 1e4), ("max_yield", 0, 1e5),
                      ("start_delay_s", 0, 600), ("stop_delay_s", 0, 600), ("flow_shift_s", -600, 600)):
        v = out[k]
        if v is None:
            continue
        v = float(v)
        if not np.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"SMS import setting {k} = {v!r} is outside {lo:g}-{hi:g}")
        out[k] = v
    if out["product"] is not None:
        k = crop_key(out["product"])
        if k is None:
            raise ValueError(f"unknown product {out['product']!r}: use one of {sorted(common.CROPS)}")
        out["product"] = k
    return out


def resolve(S: dict, crop=None) -> dict:
    """The settings of one file: the product (the setting, else the crop of the data), its weight to volume, dry
    moisture and maximum where the settings leave them empty, the manual moisture = the dry moisture when empty."""
    S = settings(S)
    prod = S["product"] or crop_key(crop)
    tw0, ms0, mx0 = product_defaults(prod)
    out = dict(S)
    out["product"] = prod
    out["test_weight_lb_bu"] = S["test_weight_lb_bu"] or tw0
    out["dry_moisture_pct"] = S["dry_moisture_pct"] if S["dry_moisture_pct"] is not None else ms0
    out["max_yield"] = S["max_yield"] if S["max_yield"] is not None else mx0
    out["manual_moisture_pct"] = (S["manual_moisture_pct"] if S["manual_moisture_pct"] is not None
                                  else out["dry_moisture_pct"])
    return out


def describe(R: dict) -> str:
    """One line of the settings, as SMS's dialog lists them."""
    def f(v, d=2):
        return "-" if v is None else f"{float(v):,.{d}f}"
    s = (f"product {R.get('product') or 'unknown'}; weight to volume {f(R['test_weight_lb_bu'])} lb/bu; dry moisture "
         f"{f(R['dry_moisture_pct'])} %; expand dry moisture {'on' if R['expand_dry_moisture'] else 'off'}")
    if R["use_manual_swath"]:
        s += f"; manual swath {f(R['manual_swath_ft'])} ft"
    if R["use_manual_moisture"]:
        s += f"; manual moisture {f(R['manual_moisture_pct'])} %"
    s += f"; yield volume {f(R['min_yield'], 3)}-{f(R['max_yield'])} bu/ac"
    s += (f"; start delay {f(R['start_delay_s'])} s, stop delay {f(R['stop_delay_s'])} s, flow shift "
          f"{f(R['flow_shift_s'])} s")
    return s


# ================================================================================================ apply
def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float) if (col and col in df) else None


def _sequences(df, C) -> np.ndarray:
    """A sequence number per record: a new sequence where the dataset or the machine changes (file order)."""
    brk = np.zeros(len(df), bool)
    if len(df):
        brk[0] = True
    for key in ("dataset", "machine"):
        col = C.get(key)
        if col and col in df:
            v = df[col].astype(str).to_numpy()
            brk[1:] |= v[1:] != v[:-1]
    return np.cumsum(brk)


def _clock(df, C, seq) -> np.ndarray | None:
    """Seconds since the start of each record's sequence: the durations added up (the time column without one)."""
    dur = _num(df, C.get("duration_s"))
    if dur is not None and np.isfinite(dur).any():
        d = np.where(np.isfinite(dur) & (dur > 0), dur, 0.0)
        c = np.cumsum(d)
        start = pd.Series(c - d).groupby(seq).transform("min").to_numpy()
        return c - start
    tcol = C.get("time")
    if tcol and tcol in df:
        t = pd.to_datetime(df[tcol], errors="coerce")
        if t.notna().any():
            s = (t - t.min()).dt.total_seconds().to_numpy(float)
            return s - pd.Series(s).groupby(seq).transform("min").to_numpy()
    return None


def _passes(df, C, seq, xy) -> np.ndarray:
    """A pass number per record: a new pass with a new sequence, a step longer than PASS_BREAK_M or a turn sharper than
    PASS_BREAK_DEG (the engine's pass break)."""
    brk = np.r_[True, seq[1:] != seq[:-1]]
    if xy is not None:
        step = np.r_[0.0, np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1]))]
        brk |= step > PASS_BREAK_M
    hd = _num(df, C.get("heading"))
    if hd is not None:
        dh = np.r_[0.0, ((np.diff(hd) + 180) % 360) - 180]
        brk |= np.abs(np.nan_to_num(dh)) > PASS_BREAK_DEG
    return np.cumsum(brk)


def apply(shp: str, out_shp: str, R: dict, log=lambda m: None) -> dict:
    """Import a standard harvest point file as SMS would: manual swath / moisture, flow shift, the weight to volume
    and dry moisture (wet volume, dry mass and dry volume computed again from the wet mass), the start / stop delays
    and the yield volume limits. Writes out_shp with the kept records byte for byte and the changed cells patched
    (engine.clean.yield_clean.write_points); when nothing changes and nothing is left out the file is not copied.
    Returns {path, n_in, n_out, left_out: {step: n}, changed: [columns], settings, notes}."""
    import pyogrio
    from engine.clean import yield_clean as yc
    base = os.path.splitext(shp)[0]
    g = pyogrio.read_dataframe(shp)
    C = yc.detect_columns([c for c in g.columns if c != "geometry"])
    n = len(g)
    rep = {"path": shp, "n_in": n, "n_out": n, "left_out": {}, "changed": [], "settings": R, "notes": []}
    if n == 0:
        return rep
    vals = {c: _num(g, c) for c in PER_AREA if c in g}
    wcol, mcol = C.get("width_ft"), C.get("moisture")
    width = _num(g, wcol)
    moist = _num(g, mcol)
    new = {}
    # Use Manual Swath: the logged width replaced, the per-area values scaled by logged / manual (the mass is kept)
    if R["use_manual_swath"] and width is not None:
        mw = float(R["manual_swath_ft"])
        sc = np.where(np.isfinite(width) & (width > 0), width / mw, np.nan)
        for c, v in vals.items():
            vals[c] = v * sc
            new[c] = vals[c]
        width = np.full(n, mw)
        new[wcol] = width
    elif R["use_manual_swath"]:
        rep["notes"].append("manual swath: the file has no width column")
    # Use Manual Moisture
    if R["use_manual_moisture"] and mcol:
        moist = np.full(n, float(R["manual_moisture_pct"]))
        new[mcol] = moist
    tw, ms = R["test_weight_lb_bu"], R["dry_moisture_pct"]
    wet = vals.get("Yld_Mass_W")
    if wet is None and vals.get("Yld_Vol_We") is not None and tw:
        wet = vals["Yld_Vol_We"] * float(tw)
    seq = _sequences(g, C)
    clock = _clock(g, C, seq)
    xy = None
    try:
        if g.crs is not None:
            utm = g.estimate_utm_crs()
            pts = g.geometry.to_crs(utm)
            xy = np.c_[pts.x.to_numpy(float), pts.y.to_numpy(float)]
    except Exception:                                # no usable geometry: passes from the heading only
        xy = None
    # Flow Shift: the grain mass logged s seconds later belongs to this position (positive s)
    s = float(R["flow_shift_s"] or 0)
    if s and wet is not None:
        dist = _num(g, C.get("distance_ft"))
        if clock is None or dist is None or width is None:
            rep["notes"].append("flow shift: the file needs duration (or time), distance and width columns: not applied")
        else:
            area = dist * width / 43560.0
            mass = wet * area
            shifted = np.full(n, np.nan)
            for q in np.unique(seq):
                idx = np.flatnonzero(seq == q)
                t = clock[idx]
                j = np.searchsorted(t, t + s - 1e-9)
                ok = (j < len(idx)) & (t + s >= t[0] - 1e-9)     # no grain from beyond the ends of the sequence
                shifted[idx[ok]] = mass[idx[j[ok]]]
            with np.errstate(divide="ignore", invalid="ignore"):
                wet = np.where(area > 0, shifted / area, np.nan)
            rep["notes"].append(f"flow shift {s:+g} s: the grain mass moved within each logged sequence")
    # Weight To Volume, Dry Moisture, Expand Dry Moisture: the yields again from the wet mass
    if wet is not None and tw and ms is not None:
        f = common.shrink_factor(moist if moist is not None else np.full(n, float(ms)), float(ms),
                                 "symmetric" if R["expand_dry_moisture"] else "one_sided")
        f = np.where(np.isfinite(f), f, 1.0)
        calc = {"Yld_Mass_W": wet, "Yld_Vol_We": wet / float(tw), "Yld_Mass_D": wet * f,
                "Yld_Vol_Dr": wet * f / float(tw)}
        for c, v in calc.items():
            if c in g:
                vals[c] = v
                new[c] = v
    elif wet is None:
        rep["notes"].append("no wet mass or wet volume column: the yields are used as the file gives them")
    else:
        rep["notes"].append("weight to volume or dry moisture unknown (product not recognised): the yields are used "
                            "as the file gives them")
    # which records stay
    keep = np.ones(n, bool)
    dv = vals.get("Yld_Vol_Dr") if vals.get("Yld_Vol_Dr") is not None else _num(g, C.get("yield"))

    def drop(name, bad):
        nonlocal keep
        bad = np.asarray(bad, bool) & keep
        if bad.any():
            rep["left_out"][name] = int(bad.sum())
        keep &= ~bad
    if (R["start_delay_s"] or R["stop_delay_s"]) and clock is not None:
        ps = _passes(g, C, seq, xy)
        dur = _num(g, C.get("duration_s"))
        d = np.where(np.isfinite(dur) & (dur > 0), dur, 0.0) if dur is not None else np.zeros(n)
        t0 = pd.Series(clock - d).groupby(ps).transform("min").to_numpy()
        t1 = pd.Series(clock).groupby(ps).transform("max").to_numpy()
        if R["start_delay_s"]:
            drop("start delay", (clock - d) - t0 < float(R["start_delay_s"]))
        if R["stop_delay_s"]:
            drop("stop delay", t1 - (clock - d) <= float(R["stop_delay_s"]))
    elif R["start_delay_s"] or R["stop_delay_s"]:
        rep["notes"].append("start / stop delay: the file has no duration or time column: not applied")
    if dv is not None:
        drop("no yield", ~np.isfinite(dv))
        if R["min_yield"] is not None:
            drop("below the min. yield volume", dv < float(R["min_yield"]))
        if R["max_yield"] is not None:
            drop("above the max. yield volume", dv > float(R["max_yield"]))
    # the cells that really change at the field's own decimals
    dbf = yc._read_dbf(base + ".dbf")
    dec = {d[:11].split(b"\0")[0].decode("latin-1"): d[17] for d in dbf["fdesc"]}
    rows = np.flatnonzero(keep)
    patch = {}
    for c, v in new.items():
        old = _num(g, c)
        q = int(dec.get(c, 6))
        a, b = np.round(np.asarray(v, float), q), np.round(old, q)
        # a cell changes when it moves by more than one unit of its last decimal: SMS computes the volumes from the
        # unrounded mass, so recomputing them from the rounded one differs by that unit (noise, not a change)
        with np.errstate(invalid="ignore"):
            diff = ~((np.abs(a - b) <= 1.5 * 10.0 ** -q) | (~np.isfinite(a) & ~np.isfinite(b)))
        if diff[rows].any():
            patch[c] = (np.asarray(v, float)[rows], diff[rows])
            rep["changed"].append(c)
    rep["n_out"] = int(keep.sum())
    if not patch and keep.all():
        return rep
    yc.write_points(out_shp, shp, g, rows, [], byte_copy=(yc._read_shp(shp), dbf), patch=patch or None)
    rep["path"] = out_shp
    log(f"import as SMS: {n - rep['n_out']:,} of {n:,} readings left out"
        + (" (" + ", ".join(f"{k} {v:,}" for k, v in rep["left_out"].items()) + ")" if rep["left_out"] else "")
        + (f"; changed {', '.join(rep['changed'])}" if rep["changed"] else ""))
    return rep
