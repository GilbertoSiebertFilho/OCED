# -*- coding: utf-8 -*-
"""The clean harvest as an ISO 11783-10 TASKDATA set (ISOXML time logs), for Ag Leader SMS to read as monitor data.

    from engine.formats import isoxml_write
    W = isoxml_write.write_clean(source, "out/T_sms3s_clean.shp", "out/isoxml")   # source may be None
    W["zip"]        # TASKDATA/TASKDATA.XML, TASKDATA/LINKLIST.XML, TASKDATA/TLGnnnnn.XML + .BIN (one per combine,
                    # more where its readings cannot follow each other in one log, see below)
    W["verify"]     # the set read back with read_points(): count and the largest difference of every attribute

EXPERIMENTAL, NOT YET TESTED IN SMS: the SMS rules below were measured on an ISOXML set that SMS read (one Case IH
display, one SMS version); whether SMS reads a set written here as it reads a machine's own is not established until a
written set has been read into a scratch SMS project and its Summary and points compared with the clean file.

Works for ANY clean point file of OCED (a decoded card, a .jdl, a GreenStar 3 card, an SMS or Operations Center export,
a KML conversion): it needs only the clean file's own columns (the standard schema of common.py; Time, Duration_s,
Distance_f, Swth_Wdth_, Moisture__, Yld_Mass_W, Machine), never the raw files. It is not the source's own format: for
a raw card OCED offers the card's own writer (engine/formats/native_write.py). One device (DVC) per combine and one
task (TSK) with one binary time log (TLG) per combine, more tasks where needed (below); the device description, the
data dictionary entities (DDIs) and their units follow an ISOXML set
that SMS read (a Case IH harvest TASKDATA, ISO 11783-10 version 4: device 'Harvest Data' with a 'Yield Monitor
Header' and its sections, logged once per second):

    DDI 0x008D (141) Actual Work State, device element (1 = harvesting, 0 = not)
    DDI 0x00A1.. (161..) Actual Condensed Work State, 2 bits per section (01 on, 00 off, 11 not installed)
    DDI 0x0057 (87)  Actual Mass Per Time Yield, mg/s, WET grain flow
    DDI 0x0063 (99)  Actual Grain Moisture, ppm (1e-4 %)
    DDI 0x0042 (66)  Setpoint Working Width, mm      DDI 0x0046 (70) Maximum Working Width, mm (header, first record)
    DDI 0x0086 / 0x0087 / 0x0088 X / Y / Z offsets, mm (navigation element 0, sections' Y; first record)
    DDI 0x00B5 (181) Actual Dry Mass Per Area Yield, mg/m2   DDI 0x0053 (83) Actual Volume Per Area Yield, ml/m2 (dry)
    DDI 0x00B6 (182) Actual Dry Mass Per Time Yield, mg/s    DDI 0x0056 (86) Actual Volume Per Time Yield, ml/s (dry)
    DDI 0x00B8 (184) Reference Moisture For Dry Mass, ppm    DDI 0x0079 (121) Product Density Mass Per Volume, mg/l
    DDI 0x008F (143) Physical Actual Value Time Latency, ms: written 0 (OCED's points already carry their position)
    DDI 0xDFFE PGN 129026 (COG bits 16-31, 1e-4 rad; SOG bits 32-47, 0.01 m/s), navigation element
    task totals (TIM of the TSK): 0x005A (90) Total Yield Mass kg, 0x00B7 (183) Yield Total Dry Mass kg, 0x0059 (89)
    Total Yield Volume l, 0x0074 (116) Total Area m2, 0x0075 (117) Effective Total Distance mm, 0x0077 (119)
    Effective Total Time s.

How SMS turns such a log into points (measured on it, every point compared; not an SMS document; the reader of
engine/formats/isoxml.py follows the same rules and reads the written set back): a record is a point when sections
are on and the flow is above 0; its Duration is the time since the PREVIOUS RECORD and its Distance the step from
that record in a flat-earth metric of 111,120 m per degree, whether or not that record is a point; its width the
sections on times the section width (header width / number of sections); wet mass = flow x duration; the time
latency (DDI 143) and the device offsets move the point (written 0 here); and a record followed by the next one in
less than 0.9 s is put together with that next one (which keeps its own position and sections), so a reading with
another record closer than that behind it is lost.

So the writer writes the clean readings as a monitor log, one record per reading at its own time, wherever a reading
follows the previous one of its combine directly (lead_in="gaps", the default): its time step is its Duration and its
position step, in SMS's metric, gives its area (step x width in whole sections) within AREA_TOL of the clean area. Only
where that does not hold - the first reading, a reading after a gap (removed readings, a pass end), a reading whose
position step is not its distance (Optimize Swath Widths moved it, a narrowed width that whole sections cannot carry) -
a lead-in record (work state 0, sections off, flow 0) is written before the reading, Distance' behind it along Track,
so that the step from it is the reading's distance; it sits the reading's Duration before it. No record is written
closer than MIN_GAP_MS (0.9 s) to a reading, before or after it (SMS would put the two together), so a lead-in needs
1.8 s or more between two readings of a log. A reading that needs one and follows the previous reading sooner (every
reading of a run on a 1-s log) is therefore NOT delayed: it is written, at its own Time, in a further time log of
the same combine (a second task of the same device, named '<field> <combine> (2)', and so on up to TIME_LOGS_MAX),
where the record before it is far enough; SMS reads every time log on its own, so it shows one dataset per time log
and the points of a combine lie in turn in as many of them as are needed (two or more) where its position steps are
not its distances. Every reading then keeps its Time, its Duration, its Distance and its width.
Only where even that leaves no room (readings closer
than 0.9 s to each other in more logs than TIME_LOGS_MAX hold apart) a reading is written with a shorter duration
behind its lead-in (flow raised by the same ratio: the wet mass is kept) or, last, after its Time: both are counted
(verify "n_late", "max_late_s"; a late reading is a warning of the result, never silent). A reading shorter than
0.9 s is written with a duration of 0.9 s and its flow lowered by the same ratio. Before every gap of 0.9 s or more
to the next lead-in and after the last reading of a log a trail-out record (work state 0) closes the reading's own
interval; no two records of a log are closer than 0.9 s. The result reports the lead-ins (verify:
"readings_without_lead_in", "lead_ins_in_runs", "time_logs") and the wet mass and area the set would give if a
reader timed a point to the next record or measured from the previous point. lead_in="always" writes a lead-in
before every reading (every Distance exact; the readings of a run then lie in turn in two or more logs). Two tasks
of one device whose times interleave are not something the set SMS read held: how SMS takes them is part of what the
first written set read into SMS must show (CAVEAT).

Widths are whole sections (N <= 64 equal sections, N chosen so that the full width is whole sections to the mm);
Distance' = clean area / width in sections, so that the AREA is the clean one and Width and Distance differ by at most
half a section in opposite directions. The lead-in's position is a 1e-7 deg grid point near Distance', chosen so that
the combine's running area error (no-lead readings included) returns to 0. Resolutions: position 1e-7 deg (1.1 cm),
time 1 ms, width the section (<= W / 2N), flow 1 mg/s, moisture 1e-4 %, elevation 1 mm. The per-reading area is then
within a fraction of a percent of the clean one; on passes running exactly north-south or east-west the grid gives few
positions near Distance', and a reading shorter than about a centimetre cannot be written: verify reports the
per-reading area error (p99, max) and a warning counts the readings more than 1 % off.

The key from a clean row to the written record: the row number of the clean file (src_row) with its (Dataset,
Obj__Id) and Machine, written to <name>_index.csv next to the set with the TLG and the record index of the reading.
Pure engine code (no Streamlit, no app imports).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import math
import os
import shutil
import struct
import time as _time
import uuid
import zipfile
from xml.sax.saxutils import quoteattr

import numpy as np
import pandas as pd

from engine.formats import common

FORMAT_ID = "isoxml"
LABEL = "ISOXML TASKDATA (not the source's format)"
WRITER = "OCED"
EPOCH = pd.Timestamp("1980-01-01")
SMS_M_PER_DEG = 111_120.0              # SMS's flat-earth metric (60 x 1852 m per degree), measured on the set SMS read
LB_PER_KG = common.LB_PER_KG
M_PER_FT = 0.3048
SQFT_PER_AC = common.SQFT_PER_AC
ML_PER_BU = 35_239.07040               # US bushel
MAX_SECTIONS = 64                      # condensed work state DDIs 0x00A1-0x00A4, the ones SMS read on the set
MIN_SECTIONS = 16
CHAIN_TOL_MS = 150                     # a reading continues the previous one's clock when within this of its Time
MIN_GAP_MS = 900                       # SMS puts a record together with the next one when that follows in less than
                                       # 0.9 s (engine/formats/isoxml.py MERGE_S): no record is written closer than
                                       # this to a reading, before or after it
TIME_LOGS_MAX = 4                      # the most time logs (tasks) the readings of one combine are written in
AREA_TOL = 0.01                        # lead_in="gaps": a reading is written without a lead-in when the area SMS
                                       # measures from the previous reading is within this of the clean area (the
                                       # per-reading precision the 1e-7 deg grid gives a lead-in reading)
DATASET_GAP_MS = 60_000                # date-only times: the next dataset of a combine starts this long after the last
DESIGNATOR_MAX = 32                    # ISO 11783-10 string(32) designators
NULL_I32 = 0x7FFFFFFF
SEARCH_UNITS = 2                       # lead-in position search: +-2 units of 1e-7 deg around the ideal point
RUN_MAX_M2 = 0.5                       # running area error of a combine (m2) above which a farther grid point may help
LEAD_INS = ("gaps", "always")
CAVEAT = ("experimental, not yet tested in SMS: the set follows the rules measured on an ISOXML set SMS read; read "
          "it into a scratch SMS project and compare its Summary and points with the clean file before using it")

DDI = {"work_state": 0x008D, "setpoint_width": 0x0042, "max_width": 0x0046, "mass_flow": 0x0057,
       "moisture": 0x0063, "dry_mass_area": 0x00B5, "vol_area": 0x0053, "dry_mass_time": 0x00B6, "vol_time": 0x0056,
       "ref_moisture": 0x00B8, "density": 0x0079, "latency": 0x008F, "offset_x": 0x0086, "offset_y": 0x0087,
       "offset_z": 0x0088, "condensed": 0x00A1, "pgn": 0xDFFE, "total_mass": 0x005A, "total_dry_mass": 0x00B7,
       "total_volume": 0x0059, "total_area": 0x0074, "eff_distance": 0x0075, "eff_time": 0x0077}
PGN_COG_SOG = 129026


class IsoxmlWriteError(ValueError):
    """The clean file cannot be written as a TASKDATA set (a plain message for the user)."""


def can_write(source: dict | None) -> tuple[bool, str]:
    """ISOXML is written from the clean file's own columns, whatever the source (a decoded card or an export):
    always (True, ""). Whether it is OFFERED for a source is the dispatcher's choice (engine/formats/native_write)."""
    return True, ""


# ================================================================================================= reading the clean file
def _columns(cols) -> dict:
    from engine.clean import yield_clean
    cc = yield_clean.detect_columns(cols)
    low = {str(c).lower(): c for c in cols}
    for k, names in {"field": ("Field",), "product": ("Product",), "elevation": ("Elevation_", "Elevation"),
                     "dry_mass_lbac": ("Yld_Mass_D",), "dry_sym": ("Yld_Dry_Sy",), "width_raw": ("Wdth_Raw",),
                     "swath_scale": ("Swath_Scl",), "crop": ("Crop",)}.items():
        cc[k] = next((low[n.lower()] for n in names if n.lower() in low), None)
    return cc


def _load(path: str):
    import pyogrio
    g = pyogrio.read_dataframe(path)
    if g.crs is not None:
        try:
            if g.crs.to_epsg() != 4326:
                g = g.to_crs(4326)
        except Exception:                                  # noqa: BLE001 - an unknown CRS is read as degrees
            pass
    geom = g.geometry
    df = pd.DataFrame(g.drop(columns=g.geometry.name))
    df["lon"], df["lat"] = geom.x.to_numpy(float), geom.y.to_numpy(float)
    return df, _columns(list(df.columns))


def _num(df, col, default=np.nan):
    if not col:
        return np.full(len(df), default, float)
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float)


def _crop_constants(df, cc, source, warns) -> tuple[float, float, list]:
    """(test weight lb/bu, standard moisture %, how): from the file's own columns first (wet mass / wet volume; the
    dry / wet ratio where the shrink acts, else the symmetric dry yield), then the decoder's options, then the crop."""
    how = []
    tw = None
    w, v = _num(df, cc.get("wet_mass_lbac")), _num(df, cc.get("yield_wet"))
    with np.errstate(divide="ignore", invalid="ignore"):
        r = w / v
    r = r[np.isfinite(r) & (r > 0)]
    if len(r):
        tw = float(np.median(r))
        how.append(f"test weight {tw:.3f} lb/bu = median Yld_Mass_W / Yld_Vol_We of the file")
    opts = (source or {}).get("options") or {}
    crop = None
    if cc.get("crop") and len(df):
        crop = str(df[cc["crop"]].astype(str).mode().iat[0]).strip().lower() or None
        crop = None if crop in ("nan", "none") else crop
    crop = crop or (str(opts.get("crop")).lower() if opts.get("crop") else None)
    if tw is None:
        tw = opts.get("test_weight_lb_bu") or (common.CROPS.get(crop, (None, None))[0] if crop else None)
        if tw:
            how.append(f"test weight {float(tw):g} lb/bu from the decoder options / crop table ({crop})")
        else:
            tw = 60.0
            warns.append("no test weight in the file, the decoder options or the crop table: 60 lb/bu written")
    ms = None
    m = _num(df, cc.get("moisture"))
    dry = _num(df, cc.get("dry_mass_lbac"))
    k = np.isfinite(dry) & np.isfinite(w) & (w > 0) & (dry < w * (1 - 1e-6)) & np.isfinite(m)
    if k.sum() >= 3:
        ms = float(np.median(100.0 - (100.0 - m[k]) * w[k] / dry[k]))
        how.append(f"standard moisture {ms:.2f} % from the dry / wet ratio of {int(k.sum()):,} wetter readings")
    if ms is None and cc.get("dry_sym") and cc.get("yield_wet"):
        sy = _num(df, cc["dry_sym"])
        k = np.isfinite(sy) & (sy > 0) & np.isfinite(v) & (v > 0) & np.isfinite(m)
        if k.sum() >= 3:
            ms = float(np.median(100.0 - (100.0 - m[k]) * v[k] / sy[k]))
            how.append(f"standard moisture {ms:.2f} % from the symmetric dry yield (Yld_Dry_Sy)")
    if ms is None:
        ms = opts.get("std_moisture_pct")
        if ms is None and crop in common.CROPS:
            ms = common.CROPS[crop][1]
        if ms is None:
            ms = 13.5
            warns.append("no standard moisture in the file or the decoder options: 13.5 % written")
        how.append(f"standard moisture {float(ms):g} % from the decoder options / crop table ({crop})")
    return float(tw), float(ms), how


def _times(df, cc, dur_s, warns, machine=None) -> np.ndarray:
    """Reading times as int64 ms since 1980-01-01 on the file's own clock. A Time without a time of day (an SMS
    export's date) becomes noon of that date plus the running durations of each dataset, the datasets of one combine
    one after the other (DATASET_GAP_MS apart, in date and file order), with a warning. A time-zone-aware Time is
    written in UTC."""
    n = len(df)
    if cc.get("time"):
        s = df[cc["time"]]
        if pd.api.types.is_datetime64_any_dtype(s):
            t = pd.to_datetime(s)
        else:
            t = pd.to_datetime(s.astype(str).str.strip(), errors="coerce", format="mixed")
        if getattr(t.dt, "tz", None) is not None:
            t = t.dt.tz_convert("UTC").dt.tz_localize(None)
        ok = t.notna().to_numpy()
        tod = (t - t.dt.normalize()).dt.total_seconds().to_numpy()
        if ok.mean() >= 0.99 and np.nanmean(tod[ok] != 0) >= 0.5:
            ms = ((t - EPOCH) / pd.Timedelta(milliseconds=1)).to_numpy(float)
            if (~ok).any():
                warns.append(f"{int((~ok).sum()):,} readings without a readable time: placed after the previous one")
                ms = pd.Series(ms).ffill().bfill().to_numpy()
            return np.rint(ms).astype(np.int64)
        warns.append("the clean file's Time has no time of day: the times written are noon of the date plus the "
                     "running durations of each dataset, the datasets of a combine one after the other (SMS shows "
                     "these times)")
        day = t.dt.normalize().fillna(pd.Timestamp("2000-01-01"))
    else:
        warns.append("the clean file has no Time column: the times written start at 2000-01-01 12:00 and add the "
                     "durations of each dataset, the datasets of a combine one after the other")
        day = pd.Series(pd.Timestamp("2000-01-01"), index=df.index)
    base = ((day - EPOCH) / pd.Timedelta(milliseconds=1)).to_numpy(float) + 12 * 3600_000
    key = df[cc["dataset"]].astype(str).to_numpy() if cc.get("dataset") else np.zeros(n, object)
    mach = np.asarray(machine, object) if machine is not None else np.zeros(n, object)
    order = _num(df, cc.get("order"), 0.0)
    out = np.zeros(n, np.int64)
    groups = []
    for g in pd.unique(key):
        idx = np.where(key == g)[0]
        if len(np.unique(order[idx])) == len(idx):     # an order column that repeats (merged datasets): file order
            idx = idx[np.argsort(order[idx], kind="stable")]
        groups.append((str(mach[idx[0]]), float(base[idx[0]]), int(idx[0]), idx))
    end = {}                                            # combine -> end of its last dataset written (ms)
    for m, b0, _, idx in sorted(groups, key=lambda x: (x[0], x[1], x[2])):
        start = max(b0, end.get(m, -np.inf) + DATASET_GAP_MS)
        out[idx] = np.rint(start + np.cumsum(dur_s[idx] * 1000.0)).astype(np.int64)
        end[m] = float(out[idx[-1]])
    return out


def _readings(df, cc, widths, factors, tw, ms, notes, warns) -> pd.DataFrame:
    n = len(df)
    dur = _num(df, cc.get("duration_s"))
    bad = ~(np.isfinite(dur) & (dur > 0))
    if bad.any():
        med = float(np.nanmedian(dur[~bad])) if (~bad).any() else 1.0
        dur[bad] = med
        warns.append(f"{int(bad.sum()):,} readings without a duration: {med:g} s written")
    dist = _num(df, cc.get("distance_ft"))
    if not cc.get("distance_ft"):
        dist = _num(df, cc.get("speed_mph")) * 5280.0 / 3600.0 * dur
        notes.append("Distance = Speed x Duration (the clean file has no distance)")
    w_clean = _num(df, cc.get("width_ft"))
    area_clean = dist * w_clean / SQFT_PER_AC                      # ac, after Optimize Swath Widths
    wet_lbac = _num(df, cc.get("wet_mass_lbac"))
    if not cc.get("wet_mass_lbac"):
        if cc.get("yield_wet"):
            wet_lbac = _num(df, cc["yield_wet"]) * tw
            notes.append("wet mass = Yld_Vol_We x test weight (the clean file has no Yld_Mass_W)")
        else:
            shr = common.shrink_factor(_num(df, cc.get("moisture"), 0.0), ms, "one_sided")
            wet_lbac = _num(df, cc.get("yield")) * tw / shr
            warns.append("wet mass rebuilt from the DRY yield, the moisture and a one-sided shrink: no wet column")
    wet_lb = wet_lbac * area_clean                                 # the reading's grain: unchanged by the swath step
    dry_lbac = _num(df, cc.get("dry_mass_lbac"))
    if not cc.get("dry_mass_lbac"):
        dry_lbac = _num(df, cc.get("yield")) * tw if cc.get("yield") else \
            wet_lbac * common.shrink_factor(_num(df, cc.get("moisture"), 0.0), ms, "one_sided")
    dry_lb = dry_lbac * area_clean
    if widths:
        width, area = w_clean, area_clean
    else:
        if cc.get("width_raw") and cc.get("swath_scale"):
            width = _num(df, cc["width_raw"])
            area = area_clean * _num(df, cc["swath_scale"], 1.0)
            notes.append("widths = Wdth_Raw (the widths before Optimize Swath Widths), area = clean area x Swath_Scl")
        else:
            width, area = w_clean, area_clean
            warns.append("widths=False but the clean file has no Wdth_Raw / Swath_Scl: the clean widths are written")
    mach = df[cc["machine"]].astype(str).to_numpy() if cc.get("machine") else \
        (df[cc["dataset"]].astype(str).to_numpy() if cc.get("dataset") else np.full(n, "combine", object))
    fac = np.ones(n)
    if factors:
        known = set(pd.unique(mach))
        for k, f in factors.items():
            if str(k) not in known:
                warns.append(f"factor for {k!r}: no such machine in the clean file (machines {sorted(known)[:6]})")
                continue
            if not (np.isfinite(float(f)) and float(f) > 0):
                warns.append(f"factor {f!r} for {k!r} ignored (not a positive number)")
                continue
            fac[mach == str(k)] = float(f)
            notes.append(f"combine factor {float(f):.4f} applied to the grain of {k}")
    head = _num(df, cc.get("heading"))
    elev = _num(df, cc.get("elevation"))
    R = pd.DataFrame({
        "machine": mach,
        "dataset": df[cc["dataset"]].astype(str).to_numpy() if cc.get("dataset") else np.full(n, "", object),
        "order": _num(df, cc.get("order"), 0.0),
        "field": df[cc["field"]].astype(str).to_numpy() if cc.get("field") else np.full(n, "", object),
        "product": df[cc["product"]].astype(str).to_numpy() if cc.get("product") else np.full(n, "", object),
        "crop": df[cc["crop"]].astype(str).to_numpy() if cc.get("crop") else np.full(n, "", object),
        "lon": df.lon.to_numpy(float), "lat": df.lat.to_numpy(float),
        "dur_s": dur, "width_ft": width, "area_ac": area,
        "wet_lb": wet_lb * fac, "dry_lb": dry_lb * fac, "moist": _num(df, cc.get("moisture"), 0.0),
        "heading": head, "elev_ft": elev, "src_row": np.arange(n)})
    R["t_ms"] = _times(df, cc, dur, warns, machine=mach)
    bad = ~(np.isfinite(R.area_ac) & (R.area_ac > 0) & np.isfinite(R.width_ft) & (R.width_ft > 0))
    if bad.any():
        warns.append(f"{int(bad.sum()):,} readings without an area (distance or width 0): written with the smallest "
                     "area SMS can hold; SMS will show yields that are not the clean file's for them")
    nog = _no_grain(R)
    if nog.any():
        warns.append(f"{int(nog.sum()):,} readings with no grain ({float(R.area_ac[nog].sum()):,.2f} ac): SMS does not "
                     "count a record with flow 0 as a point, so the set reads back that many points and that area "
                     "fewer than were written")
    return R


def _no_grain(R: pd.DataFrame) -> np.ndarray:
    """The readings written with no grain (flow 0): written, but not points when the set is read (read_points)."""
    return (~(np.isfinite(R.wet_lb) & (R.wet_lb > 0))).to_numpy()


# ================================================================================================= planning the records
def _sections(width_mm_full: float, max_sections: int) -> tuple[int, int]:
    """(N, section width mm): N equal sections whose sum is closest to the full width (whole mm), larger N first."""
    W = max(float(width_mm_full), 1.0)
    best = None
    for N in range(max_sections, MIN_SECTIONS - 1, -1):
        ws = max(1, int(round(W / N)))
        err = abs(N * ws - W)
        if best is None or err < best[0] - 1e-9:
            best = (err, N, ws)
    return best[1], best[2]


def _sms_step_m(lat1, lon1, lat2, lon2):
    """SMS's distance between two positions (deg): flat earth, 111,120 m per degree, cos of the mean latitude."""
    x = (lon2 - lon1) * SMS_M_PER_DEG * np.cos(np.radians((lat1 + lat2) / 2.0))
    y = (lat2 - lat1) * SMS_M_PER_DEG
    return np.hypot(x, y)


def _place(tau_prev: int, clock: int, gap: int, monitor_ok: bool) -> tuple:
    """Where a reading goes in a time log whose last reading was written at tau_prev: (time of its lead-in record or
    None for a monitor record, the time it is written at, quality). quality 0: at its Time (a monitor record one
    duration after the previous reading, or behind a lead-in its own duration before it, the lead-in MIN_GAP_MS or
    more after the previous reading); 1: at its Time behind a lead-in that had less room than its duration; 2:
    after its Time (no room for a lead-in MIN_GAP_MS from both)."""
    if monitor_ok and abs(tau_prev + gap - clock) <= CHAIN_TOL_MS:
        return None, tau_prev + gap, 0
    if clock - gap >= tau_prev + MIN_GAP_MS:
        return clock - gap, clock, 0
    if clock - MIN_GAP_MS >= tau_prev + MIN_GAP_MS:
        return tau_prev + MIN_GAP_MS, clock, 1
    return tau_prev + MIN_GAP_MS, tau_prev + 2 * MIN_GAP_MS, 2


def _lanes(R: pd.DataFrame, sections: tuple, lead_in: str = "gaps", max_logs: int = TIME_LOGS_MAX) -> np.ndarray:
    """The time log (0, 1, ...) every reading of one combine is written in (R in time order): the first log in which
    it keeps its Time, Duration and Distance (_place quality 0); a new log when none does and fewer than max_logs are
    open; else the log in which it loses least (a shorter duration before a later time)."""
    n = len(R)
    N, ws = sections
    d_ms = np.maximum(1, np.rint(R.dur_s.to_numpy() * 1000.0)).astype(np.int64)
    gap = np.maximum(d_ms, MIN_GAP_MS).tolist()
    clock = R.t_ms.to_numpy(np.int64).tolist()
    wmm = R.width_ft.to_numpy() * 304.8
    w = (np.clip(np.rint(np.nan_to_num(wmm, nan=0.0) / ws), 1, N) * ws / 1000.0).tolist()
    area = np.maximum(np.nan_to_num(R.area_ac.to_numpy() * SQFT_PER_AC * M_PER_FT ** 2, nan=0.0), 1e-4).tolist()
    lat = (np.rint(R.lat.to_numpy() * 1e7) / 1e7).tolist()
    lon = (np.rint(R.lon.to_numpy() * 1e7) / 1e7).tolist()
    lane = np.zeros(n, int)
    last = []                                            # per log: (time its last reading is written at, its index)
    for i in range(n):
        best = None
        for L, (tp, j) in enumerate(last):
            mon = False
            if lead_in == "gaps":
                step = math.hypot((lon[i] - lon[j]) * SMS_M_PER_DEG * math.cos(math.radians((lat[i] + lat[j]) / 2.0)),
                                  (lat[i] - lat[j]) * SMS_M_PER_DEG)
                mon = step > 0 and abs(step * w[i] / area[i] - 1) <= AREA_TOL
            _, tau, q = _place(tp, clock[i], gap[i], mon)
            key = (q, tau - clock[i] if q == 2 else 0, L)
            if best is None or key < best[0]:
                best = (key, L, tau)
            if q == 0:
                break
        if best is None or (best[0][0] > 0 and len(last) < max_logs):
            last.append((clock[i], i))
            lane[i] = len(last) - 1
        else:
            lane[i] = best[1]
            last[best[1]] = (best[2], i)
    return lane


def _plan(R: pd.DataFrame, max_sections: int, notes: list, tw: float, lead_in: str = "gaps",
          sections: tuple | None = None) -> dict:
    """The record list of one time log of one combine (module docstring): per reading an optional lead-in (work state
    0), the reading (work state 1) and an optional trail-out (work state 0), in time order. sections = (N, section
    mm) of the combine's header (default: from the widths of R)."""
    R = R.sort_values(["t_ms", "src_row"], kind="stable").reset_index(drop=True)
    n = len(R)
    d_ms = np.maximum(1, np.rint(R.dur_s.to_numpy() * 1000.0)).astype(np.int64)
    clock = R.t_ms.to_numpy(np.int64)
    # widths in sections
    wmm = R.width_ft.to_numpy() * 304.8
    full = float(np.nanmax(wmm)) if np.isfinite(wmm).any() else 9144.0
    N, ws = sections or _sections(full, max_sections)
    k = np.clip(np.rint(np.nan_to_num(wmm, nan=0.0) / ws), 1, N).astype(int)
    w_sms_m = k * ws / 1000.0
    area_m2 = np.nan_to_num(R.area_ac.to_numpy() * SQFT_PER_AC * M_PER_FT ** 2, nan=0.0)
    area_m2 = np.maximum(area_m2, 1e-4)
    dist_m = area_m2 / w_sms_m                          # SMS distance that makes the area exact
    # positions
    lat_u = np.rint(R.lat.to_numpy() * 1e7).astype(np.int64)
    lon_u = np.rint(R.lon.to_numpy() * 1e7).astype(np.int64)
    lat_r, lon_r = lat_u / 1e7, lon_u / 1e7
    h = R.heading.to_numpy(float)
    if not np.isfinite(h).all():
        hh = common.heading_deg(R.lon.to_numpy(), R.lat.to_numpy())
        h = np.where(np.isfinite(h), h, hh)
        h = np.where(np.isfinite(h), h, 0.0)
    hr = np.radians(h)
    coslat = np.cos(np.radians(lat_r))
    lat_i = lat_r - dist_m * np.cos(hr) / SMS_M_PER_DEG
    lon_i = lon_r - dist_m * np.sin(hr) / (SMS_M_PER_DEG * coslat)
    # the lead-in grid point candidates: per reading those within 2 mm of the best distance, or - once the combine's
    # running area error (no-lead readings included) is above RUN_MAX_M2 - any within AREA_TOL of the reading's
    # distance, so that the lead-in readings bring the total back (passes exactly north-south or east-west have one
    # candidate per grid step only)
    base_lat = np.rint(lat_i * 1e7).astype(np.int64)
    base_lon = np.rint(lon_i * 1e7).astype(np.int64)
    offs = [(a, b) for a in range(-SEARCH_UNITS, SEARCH_UNITS + 1) for b in range(-SEARCH_UNITS, SEARCH_UNITS + 1)]
    E = np.empty((n, len(offs)))
    for j, (a, b) in enumerate(offs):
        st = _sms_step_m((base_lat + a) / 1e7, (base_lon + b) / 1e7, lat_r, lon_r)
        E[:, j] = np.where(st > 0, st - dist_m, np.inf)
    best = np.min(np.abs(E), axis=1)
    EA_near = np.where(np.abs(E) <= (best + 0.002)[:, None], E * w_sms_m[:, None], np.nan)
    far = np.maximum(best + 0.002, AREA_TOL * dist_m)                # the reading's own area within AREA_TOL
    EA_far = np.where(np.abs(E) <= far[:, None], E * w_sms_m[:, None], np.nan)
    step_prev = np.r_[np.nan, _sms_step_m(lat_r[:-1], lon_r[:-1], lat_r[1:], lon_r[1:])] if n else np.zeros(0)
    # ---- times, lead-ins, trail-outs (one pass in time order)
    tau = np.zeros(n, np.int64)
    lead_t = np.zeros(n, np.int64)
    has_lead = np.ones(n, bool)
    trail = np.zeros(n, bool)
    in_run = np.zeros(n, bool)                          # a lead-in behind a reading that follows the previous one
    pick = np.zeros(n, int)
    dist_written = np.zeros(n)
    run = 0.0
    moved = max_move = 0
    # what a reading needs after the record before it: its own duration, and SMS's 0.9 s (a record closer than that
    # to the next one is put together with it)
    gap_ms = np.maximum(d_ms, MIN_GAP_MS)
    for i in range(n):
        if i > 0:
            mon = lead_in == "gaps" and step_prev[i] > 0 and \
                abs(step_prev[i] * w_sms_m[i] / area_m2[i] - 1) <= AREA_TOL
            lt, tau[i], _ = _place(int(tau[i - 1]), int(clock[i]), int(gap_ms[i]), bool(mon))
            if tau[i] - clock[i] > CHAIN_TOL_MS:        # no room at its Time in this log (_lanes found none better)
                moved += 1
                max_move = max(max_move, int(tau[i] - clock[i]))
            if lt is None:                               # a monitor record: the step from the reading before it
                has_lead[i] = False
                dist_written[i] = step_prev[i]
                run += (step_prev[i] - dist_m[i]) * w_sms_m[i]
                continue
            lead_t[i] = lt
            in_run[i] = abs((clock[i] - clock[i - 1]) - d_ms[i]) <= CHAIN_TOL_MS
            if lead_in == "gaps" and tau[i - 1] + gap_ms[i - 1] + MIN_GAP_MS <= lead_t[i]:
                trail[i - 1] = True                      # the previous reading's own interval is closed
        else:
            tau[i], lead_t[i] = clock[i], clock[i] - gap_ms[i]
        row = EA_far[i] if abs(run) > RUN_MAX_M2 else EA_near[i]
        j = int(np.nanargmin(np.abs(run + row)))
        pick[i] = j
        run += row[j]
    if n and lead_in == "gaps":
        trail[n - 1] = True
    oa = np.array([o[0] for o in offs])[pick]
    ob = np.array([o[1] for o in offs])[pick]
    blat, blon = base_lat + oa, base_lon + ob
    dl = _sms_step_m(blat / 1e7, blon / 1e7, lat_r, lon_r)
    dist_written = np.where(has_lead, dl, dist_written)
    prev_t = np.r_[0, tau[:-1]] if n else np.zeros(0, np.int64)
    d_eff = np.where(has_lead, tau - lead_t, tau - prev_t)
    short = d_eff != d_ms
    # trail-out positions: the reading's distance ahead along Track
    tlat = np.rint((lat_r + dist_m * np.cos(hr) / SMS_M_PER_DEG) * 1e7).astype(np.int64)
    tlon = np.rint((lon_r + dist_m * np.sin(hr) / (SMS_M_PER_DEG * coslat)) * 1e7).astype(np.int64)
    # the record list
    cnt = has_lead.astype(int) + 1 + trail.astype(int)
    m = int(cnt.sum())
    first = np.r_[0, np.cumsum(cnt)[:-1]] if n else np.zeros(0, int)
    rec_of_reading = first + has_lead.astype(int)
    kind = np.ones(m, np.int8)
    rd = np.repeat(np.arange(n), cnt)
    rt = np.zeros(m, np.int64)
    rlat = np.zeros(m, np.int64)
    rlon = np.zeros(m, np.int64)
    rt[rec_of_reading], rlat[rec_of_reading], rlon[rec_of_reading] = tau, lat_u, lon_u
    li = first[has_lead]
    kind[li] = 0
    rt[li], rlat[li], rlon[li] = lead_t[has_lead], blat[has_lead], blon[has_lead]
    ti = rec_of_reading[trail] + 1
    kind[ti] = 2
    rt[ti], rlat[ti], rlon[ti] = tau[trail] + gap_ms[trail], tlat[trail], tlon[trail]
    if m > 1 and not (np.diff(rt) >= MIN_GAP_MS).all():
        raise IsoxmlWriteError(f"internal: two records of a time log are closer than {MIN_GAP_MS} ms")
    # values
    wet_kg = R.wet_lb.to_numpy() / LB_PER_KG
    dry_kg = R.dry_lb.to_numpy() / LB_PER_KG
    with np.errstate(divide="ignore", invalid="ignore"):
        flow = np.rint(wet_kg * 1e6 / (d_eff / 1000.0))
        dflow = np.rint(dry_kg * 1e6 / (d_eff / 1000.0))
        dry_ml = R.dry_lb.to_numpy() / tw * ML_PER_BU
        dvolt = np.rint(dry_ml / (d_eff / 1000.0))
        darea_mg = np.rint(dry_kg * 1e6 / area_m2)
        dvola = np.rint(dry_ml / area_m2)
    sog = np.clip(np.rint(dist_written / (d_eff / 1000.0) / 0.01), 0, 65532).astype(np.int64)
    cog = np.clip(np.rint((hr % (2 * math.pi)) / 1e-4), 0, 62831).astype(np.int64)
    elev = pd.Series(R.elev_ft.to_numpy(float))
    no_el = int(elev.isna().sum())
    if no_el and elev.notna().any():
        elev = elev.ffill().bfill()                      # the nearest earlier (else later) elevation of the combine
    elev_mm = np.where(np.isfinite(elev.to_numpy()), np.rint(elev.to_numpy() * 304.8), 0).astype(np.int64)
    return {"R": R, "n": n, "tau": tau, "lead": lead_t, "has_lead": has_lead, "trail": trail, "in_run": in_run,
            "d_ms": d_ms, "d_eff": d_eff, "short": short, "n_late": int(moved), "max_late_ms": int(max_move),
            "N": N, "ws": ws, "k": k, "w_sms_m": w_sms_m, "area_m2": area_m2, "dist_m": dist_m,
            "dist_written": dist_written, "lat_u": lat_u, "lon_u": lon_u, "lead_lat_u": blat, "lead_lon_u": blon,
            "rec_kind": kind, "rec_reading": rd, "rec_t": rt, "rec_lat": rlat, "rec_lon": rlon,
            "rec_of_reading": rec_of_reading,
            "flow": np.nan_to_num(flow).astype(np.int64), "dflow": np.nan_to_num(dflow).astype(np.int64),
            "dvolt": np.nan_to_num(dvolt).astype(np.int64), "darea": np.nan_to_num(darea_mg).astype(np.int64),
            "dvola": np.nan_to_num(dvola).astype(np.int64), "moist": np.rint(R.moist.to_numpy() * 1e4).astype(np.int64),
            "width_mm": np.rint(np.nan_to_num(wmm, nan=0.0)).astype(np.int64), "sog": sog, "cog": cog,
            "elev_mm": elev_mm, "no_elev": no_el, "no_elev_filled": no_el if elev.notna().any() else 0}


def _condensed(k_on: np.ndarray, N: int) -> np.ndarray:
    """(n, ceil(N/16)) uint32 condensed work states: k sections on, centred; sections > N 'not installed' (11)."""
    G = (N + 15) // 16
    out = np.zeros((len(k_on), G), np.uint64)
    s0 = (N - k_on) // 2
    for sec in range(G * 16):
        g, b = divmod(sec, 16)
        if sec >= N:
            v = np.full(len(k_on), 3, np.uint64)
        else:
            v = ((sec >= s0) & (sec < s0 + k_on)).astype(np.uint64)
        out[:, g] |= v << np.uint64(2 * b)
    return out.astype(np.uint32)


# ================================================================================================= writing
def _q(s) -> str:
    return quoteattr(str(s)[:DESIGNATOR_MAX])


def _iso_time(ms: int, utc: bool) -> str:
    t = EPOCH + pd.Timedelta(milliseconds=int(ms))
    s = t.strftime("%Y-%m-%dT%H:%M:%S") + f".{t.microsecond // 1000:03d}"
    return s + ("Z" if utc else "")


def _name_hex(machine: str) -> str:
    """An ISO NAME for the device (8 bytes, hex): self-configurable, industry group 2 (agriculture), device class 7
    (harvesters), function 255, manufacturer code 0 (none claimed), identity number from the machine id."""
    ident = int(hashlib.sha1(machine.encode("utf-8")).hexdigest(), 16) & 0x1FFFFF
    v = (1 << 63) | (2 << 60) | (7 << 49) | (0xFF << 40) | (0 << 21) | ident
    return f"{v:016X}"


FIRST_ONLY = ("max_width", "nav_x", "nav_y", "nav_z")   # + sec<j>_x / sec<j>_y


def _tlg_header(dets: dict, N: int) -> tuple[str, list]:
    """The TLG XML header and the DLV order [(key, DDI, DET id)]: the per-record values, then the values logged in
    the first record only (the header's maximum width and every offset), as a machine's own set logs them."""
    hd = dets["header"]
    order = [("work_state", DDI["work_state"], dets["device"]),
             ("setpoint_width", DDI["setpoint_width"], hd),
             ("mass_flow", DDI["mass_flow"], hd),
             ("moisture", DDI["moisture"], hd),
             ("dry_mass_area", DDI["dry_mass_area"], hd),
             ("vol_area", DDI["vol_area"], hd),
             ("dry_mass_time", DDI["dry_mass_time"], hd),
             ("vol_time", DDI["vol_time"], hd),
             ("ref_moisture", DDI["ref_moisture"], hd),
             ("density", DDI["density"], hd),
             ("latency", DDI["latency"], hd)]
    for g in range((N + 15) // 16):
        order.append((f"condensed{g}", DDI["condensed"] + g, hd))
    order.append(("cog", DDI["pgn"], dets["nav"]))
    order.append(("sog", DDI["pgn"], dets["nav"]))
    order += [("max_width", DDI["max_width"], hd),
              ("nav_x", DDI["offset_x"], dets["nav"]), ("nav_y", DDI["offset_y"], dets["nav"]),
              ("nav_z", DDI["offset_z"], dets["nav"])]
    for j, sd in enumerate(dets["sections"]):
        order += [(f"sec{j}_x", DDI["offset_x"], sd), (f"sec{j}_y", DDI["offset_y"], sd)]
    if len(order) > 255:
        raise IsoxmlWriteError(f"{len(order)} logged values: a time log holds at most 255")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<TIM A="" D="4">', '    <PTN A="" B="" C="" D="1"/>']
    for key, ddi, det in order:
        if key == "cog":
            lines.append(f'    <DLV A="{ddi:04X}" B="" C="{det}" D="{PGN_COG_SOG}" E="16" F="31"/>')
        elif key == "sog":
            lines.append(f'    <DLV A="{ddi:04X}" B="" C="{det}" D="{PGN_COG_SOG}" E="32" F="47"/>')
        else:
            lines.append(f'    <DLV A="{ddi:04X}" B="" C="{det}"/>')
    lines.append("</TIM>")
    return "\r\n".join(lines) + "\r\n", order


def _section_y_mm(N: int, ws: int, k_max: int | None = None) -> list:
    """Y offset (mm, + = right of travel) of each section's centre, section 1 on the left, measured from the centre
    of the widest state the log holds (k_max sections on, as _condensed lays them: the middle of the header when
    N - k_max is even, half a section left of it when odd). SMS refers every point of a time log to the centre of
    its widest state (engine/formats/isoxml.py rule 5): measured from there, the points of a log that holds no
    full-width reading (a further time log of a combine) stay where the clean file has them."""
    k = N if k_max is None else int(k_max)
    c0 = ((N - k) // 2 + k / 2.0 - N / 2.0) * ws
    return [int(round((j + 0.5) * ws - N * ws / 2.0 - c0)) for j in range(N)]


def _tlg_binary(P: dict, order: list, static: dict) -> bytes:
    """The records of P (lead-ins and trail-outs with work state 0, readings with work state 1). The per-record
    values in every record; the maximum width and the offsets in the first record only."""
    N = P["N"]
    G = (N + 15) // 16
    rd = P["rec_reading"]
    m = len(rd)
    off = P["rec_kind"] != 1
    cond_on = _condensed(P["k"], N).astype(np.int64)
    cond_off = _condensed(np.zeros(P["n"], int), N).astype(np.int64)
    idx = {key: i for i, (key, _, _) in enumerate(order)}
    keys = [k for (k, _, _) in order if k not in FIRST_ONLY and not k.startswith("sec")]
    first_vals = [("max_width", static["max_width"]), ("nav_x", 0), ("nav_y", 0), ("nav_z", 0)]
    for j, y in enumerate(_section_y_mm(N, P["ws"], int(P["k"].max()) if P["n"] else None)):
        first_vals += [(f"sec{j}_x", 0), (f"sec{j}_y", y)]
    V = {"work_state": np.where(off, 0, 1),
         "setpoint_width": P["width_mm"][rd],
         "mass_flow": np.where(off, 0, P["flow"][rd]),
         "moisture": P["moist"][rd],
         "dry_mass_area": np.where(off, 0, P["darea"][rd]),
         "vol_area": np.where(off, 0, P["dvola"][rd]),
         "dry_mass_time": np.where(off, 0, P["dflow"][rd]),
         "vol_time": np.where(off, 0, P["dvolt"][rd]),
         "ref_moisture": np.full(m, static["ref_moisture"]),
         "density": np.full(m, static["density"]),
         "latency": np.zeros(m, np.int64),
         "cog": P["cog"][rd], "sog": P["sog"][rd]}
    for g in range(G):
        V[f"condensed{g}"] = np.where(off, cond_off[rd, g], cond_on[rd, g])
    K = len(keys)
    fields = [("ms", "<u4"), ("day", "<u2"), ("lat", "<i4"), ("lon", "<i4"), ("up", "<i4"), ("n", "u1")]
    for j in range(K):
        fields += [(f"i{j}", "u1"), (f"v{j}", "<u4")]
    A = np.zeros(m, np.dtype(fields))
    t = P["rec_t"].astype(np.int64)
    A["day"], A["ms"] = np.divmod(t, 86_400_000)
    A["lat"] = P["rec_lat"]
    A["lon"] = P["rec_lon"]
    A["up"] = P["elev_mm"][rd]
    A["n"] = K
    for j, key in enumerate(keys):
        A[f"i{j}"] = idx[key]
        A[f"v{j}"] = (np.asarray(V[key], np.int64) & 0xFFFFFFFF).astype(np.uint32)
    first = bytearray(A[:1].tobytes())
    first[18] = K + len(first_vals)
    for key, v in first_vals:
        first += struct.pack("<BI", idx[key], int(v) & 0xFFFFFFFF)
    return bytes(first) + A[1:].tobytes()


def _dvc_xml(m: int, machine: str, P: dict, version: str) -> tuple[str, dict]:
    """The DVC of one combine and the DET ids {device, nav, header, sections[]}: device element (type 1, work state
    and task totals), navigation element (type 7, the position's offsets 0), 'Yield Monitor Header' (type 2) and its
    N sections (type 4), as in a machine's own set; no device properties (DPT): widths and offsets are logged values."""
    base = (m + 1) * 1000
    dets = {"device": f"DET-{base + 1}", "nav": f"DET-{base + 2}", "header": f"DET-{base + 3}",
            "sections": [f"DET-{base + 10 + j}" for j in range(P["N"])]}
    N = P["N"]
    L = [f'\t<DVC A="DVC-{m + 1}" B={_q("Harvest Data " + machine)} C={_q(WRITER + " " + version)} '
         f'D="{_name_hex(machine)}" E={_q(machine)} F="4F4345440{(m + 1) % 16:X}0101" G="FF000000006E65">']
    groups = [(dets["device"], 1, 1, "Yield Monitor Totals", 0, 0, [1000, 1020, 1021, 1022, 1023, 1024, 1025]),
              (dets["nav"], 2, 7, "Vehicle Nav Element", 1, 1, [1012, 1013, 1014]),
              (dets["header"], 3, 2, "Yield Monitor Header", 2, 1,
               [1001, 1002, 1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1012, 1013]
               + [1030 + g for g in range((N + 15) // 16)])]
    groups += [(dets["sections"][j], 10 + j, 4, f"Header Section {j}", 3 + j, 3, [1002, 1012, 1013, 1000])
               for j in range(N)]
    for det, oid, typ, des, num, parent, dors in groups:
        L.append(f'\t\t<DET A="{det}" B="{oid}" C="{typ}" D={_q(des)} E="{num}" F="{parent}">')
        L += [f'\t\t\t<DOR A="{a}"/>' for a in dors]
        L.append("\t\t</DET>")
    dpd = [(1000, "work_state", 1, 8, "Actual Work State", None),
           (1001, "setpoint_width", 1, 9, "Target Cut Width", 2013),
           (1002, "max_width", 1, 8, "Maximum Working Width", 2013),
           (1003, "mass_flow", 1, 9, "Wet Yield-Mass/Time", 2001),
           (1004, "moisture", 1, 9, "Crop Moisture", 2007),
           (1005, "dry_mass_area", 1, 9, "Dry Yield-Mass/Area", 2000),
           (1006, "vol_area", 1, 9, "Dry Yield-Volume/Area", 2002),
           (1007, "dry_mass_time", 1, 9, "Dry Yield-Mass/Time", 2001),
           (1008, "vol_time", 1, 9, "Dry Yield-Volume/Time", 2003),
           (1009, "ref_moisture", 1, 9, "Reference Moisture", 2007),
           (1010, "density", 1, 9, "Crop Density", 2012),
           (1011, "latency", 1, 9, "Crop Delay", 2009),
           (1012, "offset_x", 1, 8, "X-Offset", 2013),
           (1013, "offset_y", 1, 8, "Y-Offset", 2013),
           (1014, "offset_z", 1, 8, "Z-Offset", 2013),
           (1020, "total_mass", 1, 16, "Total Wet Yield-Mass", 2004),
           (1021, "total_dry_mass", 1, 16, "Total Dry Yield-Mass", 2004),
           (1022, "total_volume", 1, 16, "Total Wet Yield-Volume", 2005),
           (1023, "total_area", 1, 16, "Total Area", 2014),
           (1024, "eff_distance", 1, 16, "Effective Total Distance", 2015),
           (1025, "eff_time", 1, 16, "Effective Total Time", 2016)]
    for g in range((N + 15) // 16):
        lo, hi = 16 * g + 1, 16 * g + 16
        dpd.append((1030 + g, None, 1, 9, f"Actual Condensed Work State{lo}-{hi}", None))
    for oid, key, prop, trig, des, dvp in dpd:
        ddi = DDI[key] if key else DDI["condensed"] + (oid - 1030)
        f = f' F="{dvp}"' if dvp else ""
        L.append(f'\t\t<DPD A="{oid}" B="{ddi:04X}" C="{prop}" D="{trig}" E={_q(des)}{f}/>')
    dvp = [(2000, 0, "0.0000100000", 1, "ton/ha"), (2001, 0, "0.0000036000", 1, "ton/h"),
           (2002, 0, "10.0000000000", 3, "L/ha"), (2003, 0, "3.6000000000", 1, "L/h"),
           (2004, 0, "0.0010000000", 3, "ton"), (2005, 0, "1.0000000000", 3, "L"),
           (2007, 0, "0.0001000000", 1, "%"), (2009, 0, "0.0010000000", 1, "seconds"),
           (2012, 0, "0.0010000000", 1, "g/L"), (2013, 0, "0.1000000000", 1, "cm"),
           (2014, 0, "0.0001000000", 2, "ha"), (2015, 0, "0.0010000000", 1, "m"),
           (2016, 0, "1.0000000000", 0, "s")]
    L += [f'\t\t<DVP A="{a}" B="{b}" C="{c}" D="{d}" E="{e}"/>' for a, b, c, d, e in dvp]
    L.append("\t</DVC>")
    return "\r\n".join(L), dets


def _inside(path: str, folder: str) -> bool:
    p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    f = os.path.normcase(os.path.realpath(os.path.abspath(folder)))
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def _input_root(source) -> str | None:
    """The raw input folder of a decoded source (from its decode report), or None."""
    if not isinstance(source, dict):
        return None
    if source.get("input_root"):
        return source["input_root"]
    rep = source.get("report")
    if rep is None and source.get("decode_report") and os.path.isfile(source["decode_report"]):
        try:
            import json
            with open(source["decode_report"], encoding="utf-8") as f:
                rep = json.load(f)
        except (OSError, ValueError):
            rep = None
    return (rep or {}).get("input_root")


def write_clean(source: dict | None, clean_shp: str, out_dir: str, *, widths: bool = True,
                factors: dict | None = None, new_ids: bool = True, log=print,
                max_sections: int = MAX_SECTIONS, lead_in: str = "gaps", out_name: str | None = None) -> dict:
    """Write the clean harvest of `clean_shp` as a TASKDATA set in out_dir. Returns {path, zip, n_kept, n_removed,
    files_changed, notes, warnings, verify, totals, index_csv, machines, sms_tested}. Advanced options: max_sections
    (the most sections a header is split in, 16-64), lead_in "gaps" (default: a lead-in record only where a reading
    does not follow the previous one directly) or "always" (before every reading); out_name: the name the set's
    folder starts with (default <clean file name>_isoxml; _<time stamp> follows with new_ids). See the module
    docstring. Raises IsoxmlWriteError (a ValueError) with a plain message when it cannot write."""
    from engine import run as _run                          # the version only; engine.run imports no writer
    if lead_in not in LEAD_INS:
        raise IsoxmlWriteError(f"lead_in must be one of {LEAD_INS}")
    if not (MIN_SECTIONS <= int(max_sections) <= MAX_SECTIONS):
        raise IsoxmlWriteError(f"max_sections must be {MIN_SECTIONS}-{MAX_SECTIONS} (the condensed work states SMS read)")
    if not clean_shp or not os.path.isfile(clean_shp):
        raise IsoxmlWriteError(f"the clean file {clean_shp!r} is not there")
    out_dir = os.path.abspath(out_dir)
    root = _input_root(source)
    if root and os.path.isdir(root) and _inside(out_dir, root):
        raise IsoxmlWriteError("the output folder is inside the raw input's folder: choose a folder outside it")
    notes, warns = [], []
    df, cc = _load(clean_shp)
    if not len(df):
        raise IsoxmlWriteError("the clean file has no readings: there is nothing to write")
    tw, ms, how = _crop_constants(df, cc, source, warns)
    notes += how
    R = _readings(df, cc, widths, factors, tw, ms, notes, warns)
    utc = str((source or {}).get("time_basis") or "").upper() == "UTC"
    if out_name is not None and (not str(out_name).strip() or any(c in str(out_name) for c in '/\\:')):
        raise IsoxmlWriteError(f"the output folder name {out_name!r} is not a plain folder name")
    stem = os.path.splitext(os.path.basename(clean_shp))[0]
    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    name = (str(out_name) if out_name else f"{stem}_isoxml") + (f"_{stamp}" if new_ids else "")
    folder = os.path.join(out_dir, name)
    tdir = os.path.join(folder, "TASKDATA")
    if _inside(clean_shp, folder) or (root and os.path.isdir(root) and _inside(root, folder)):
        raise IsoxmlWriteError(f"{folder} holds the clean file or the raw input: choose another output folder")
    if os.path.isdir(tdir):
        shutil.rmtree(tdir)
    os.makedirs(tdir, exist_ok=True)
    tlg0 = (int(_time.time()) % 89_000 + 10_000) if new_ids else 1
    static = {"ref_moisture": int(round(ms * 1e4)),
              "density": int(round(tw / LB_PER_KG * 1e6 / (ML_PER_BU / 1000.0)))}   # mg/l
    machines = list(pd.unique(R.machine))
    dvc_xml, tsk_xml, lnk, index, mrep = [], [], [], [], []
    files = []
    fields = [f for f in pd.unique(R.field) if f] or ["OCED field"]
    products = [p for p in pd.unique(R["product"]) if p] or ["Harvest"]
    crops = [c for c in pd.unique(R.crop) if c and c.lower() not in ("nan", "none")]
    version = getattr(_run, "__version__", "")
    n_log = 0
    for m, mach in enumerate(machines):
        Rm = R[R.machine == mach].sort_values(["t_ms", "src_row"], kind="stable").reset_index(drop=True)
        wmm = Rm.width_ft.to_numpy() * 304.8
        sec = _sections(float(np.nanmax(wmm)) if np.isfinite(wmm).any() else 9144.0, int(max_sections))
        lane = _lanes(Rm, sec, lead_in)                  # the time log of every reading (0 for all where one will do)
        plans = [_plan(Rm[lane == j], int(max_sections), notes, tw, lead_in, sections=sec)
                 for j in range(int(lane.max()) + 1 if len(lane) else 1)]
        dxml, dets = _dvc_xml(m, str(mach), plans[0], version)
        dvc_xml.append(dxml)
        hdr, order = _tlg_header(dets, sec[0])
        dev_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"oced:device:{mach}")
        lnk.append((f"DVC-{m + 1}", str(dev_uuid), f"Harvest Data {mach}"[:DESIGNATOR_MAX]))
        rep_m = {"machine": str(mach), "tlg": None, "tlgs": [], "time_logs": len(plans), "n_readings": 0,
                 "n_records": 0, "lead_ins": 0, "lead_ins_in_runs": 0, "trail_outs": 0, "sections": int(sec[0]),
                 "section_mm": int(sec[1]), "header_mm": int(sec[0] * sec[1]), "durations_shortened": 0,
                 "max_duration_short_ms": 0, "n_late": 0, "max_late_ms": 0, "readings_in_further_logs": 0,
                 "no_elevation": 0, "no_elevation_filled": 0, "wet_lb": 0.0, "area_ac": 0.0, "bytes_bin": 0}
        for j, P in enumerate(plans):
            static_m = dict(static, max_width=int(P["N"] * P["ws"]))
            tlg = f"TLG{tlg0 + n_log:05d}"
            n_log += 1
            with open(os.path.join(tdir, tlg + ".XML"), "w", encoding="utf-8", newline="") as fh:
                fh.write(hdr)
            binb = _tlg_binary(P, order, static_m)
            with open(os.path.join(tdir, tlg + ".BIN"), "wb") as fh:
                fh.write(binb)
            files += [f"TASKDATA/{tlg}.XML", f"TASKDATA/{tlg}.BIN"]
            Rp = P["R"]
            fld = Rp.field.mode().iat[0] if len(Rp) and Rp.field.iat[0] else fields[0]
            prd = Rp["product"].mode().iat[0] if len(Rp) and Rp["product"].iat[0] else products[0]
            pdt = f"PDT-{products.index(prd) + 1}" if prd in products else "PDT-1"
            pfd = f"PFD-{fields.index(fld) + 1}" if fld in fields else "PFD-1"
            t0, t1 = int(P["rec_t"][0]), int(P["rec_t"][-1])
            tot = {"wet_kg": float((P["flow"] * P["d_eff"]).sum() / 1e9),
                   "dry_kg": float((P["dflow"] * P["d_eff"]).sum() / 1e9),
                   "area_m2": float((P["dist_written"] * P["w_sms_m"]).sum()),
                   "dist_mm": float(P["dist_written"].sum() * 1000.0), "time_s": float(P["d_eff"].sum() / 1000.0)}
            wet_l = tot["wet_kg"] * LB_PER_KG / tw * ML_PER_BU / 1000.0
            task_id = f"TSK-{n_log}"
            des = f"{fld} {mach}"[:DESIGNATOR_MAX - 4] + (f" ({j + 1})" if j else "")
            T = [f'\t<TSK A="{task_id}" B={_q(des)} C="CTR-1" D="FRM-1" E="{pfd}" G="4">',
                 f'\t\t<DAN A="{_name_hex(str(mach))}" B="FFFFFFFFFFFFFFFF" C="DVC-{m + 1}">',
                 f'\t\t\t<ASP A="{_iso_time(t0, utc)}" B="{_iso_time(t1, utc)}" D="4"/>', "\t\t</DAN>",
                 '\t\t<OTP A="CPC-1"/>',
                 f'\t\t<PAN A="{pdt}" E="{dets["header"]}">',
                 f'\t\t\t<ASP A="{_iso_time(t0, utc)}" B="{_iso_time(t1, utc)}" D="4"/>', "\t\t</PAN>",
                 f'\t\t<TIM A="{_iso_time(t0, utc)}" B="{_iso_time(t1, utc)}" D="4">',
                 f'\t\t\t<DLV A="{DDI["total_mass"]:04X}" B="{int(round(tot["wet_kg"]))}" C="{dets["device"]}"/>',
                 f'\t\t\t<DLV A="{DDI["total_dry_mass"]:04X}" B="{int(round(tot["dry_kg"]))}" C="{dets["device"]}"/>',
                 f'\t\t\t<DLV A="{DDI["total_volume"]:04X}" B="{int(round(wet_l))}" C="{dets["device"]}"/>',
                 f'\t\t\t<DLV A="{DDI["total_area"]:04X}" B="{int(round(tot["area_m2"]))}" C="{dets["device"]}"/>',
                 f'\t\t\t<DLV A="{DDI["eff_distance"]:04X}" B="{int(round(tot["dist_mm"]))}" C="{dets["device"]}"/>',
                 f'\t\t\t<DLV A="{DDI["eff_time"]:04X}" B="{int(round(tot["time_s"]))}" C="{dets["device"]}"/>',
                 "\t\t</TIM>", f'\t\t<TLG A="{tlg}" C="1"/>', "\t</TSK>"]
            tsk_xml.append("\r\n".join(T))
            tsk_uuid = uuid.uuid4() if new_ids else uuid.uuid5(
                uuid.NAMESPACE_URL, f"oced:task:{stem}:{mach}:{t0}" + (f":{j}" if j else ""))
            lnk.append((task_id, str(tsk_uuid), des[:DESIGNATOR_MAX]))
            index.append(pd.DataFrame({"Dataset": Rp.dataset, "Obj__Id": Rp.order, "Machine": Rp.machine,
                                       "src_row": Rp.src_row, "TLG": tlg, "record": P["rec_of_reading"],
                                       "t_written_ms": P["tau"], "t_clean_ms": Rp.t_ms}))
            rep_m["tlg"] = rep_m["tlg"] or tlg
            rep_m["tlgs"].append(tlg)
            for key, v in (("n_readings", int(P["n"])), ("n_records", int(len(P["rec_t"]))),
                           ("lead_ins", int(P["has_lead"].sum())), ("lead_ins_in_runs", int(P["in_run"].sum())),
                           ("trail_outs", int(P["trail"].sum())),
                           ("durations_shortened", int(P["short"].sum())),   # written with another duration
                           ("n_late", P["n_late"]), ("readings_in_further_logs", int(P["n"]) if j else 0),
                           ("no_elevation", P["no_elev"]), ("no_elevation_filled", P["no_elev_filled"]),
                           ("wet_lb", tot["wet_kg"] * LB_PER_KG),
                           ("area_ac", tot["area_m2"] / (SQFT_PER_AC * M_PER_FT ** 2)), ("bytes_bin", len(binb))):
                rep_m[key] += v
            rep_m["max_duration_short_ms"] = max(rep_m["max_duration_short_ms"],
                                                 int(np.abs(P["d_ms"] - P["d_eff"]).max()) if P["n"] else 0)
            rep_m["max_late_ms"] = max(rep_m["max_late_ms"], P["max_late_ms"])
            log(f"ISOXML: {mach}: {P['n']:,} readings -> {tlg} ({len(P['rec_t']):,} records, {P['N']} sections of "
                f"{P['ws']} mm)")
            if j == len(plans) - 1:
                mrep.append(rep_m)
    # TASKDATA.XML (root children in the schema's order: AFE, CPC, CTP, CTR, DVC, FRM, PDT, PFD, TSK)
    X = ['<?xml version="1.0" encoding="UTF-8"?>',
         f'<ISO11783_TaskData VersionMajor="4" VersionMinor="2" ManagementSoftwareManufacturer="{WRITER}" '
         f'ManagementSoftwareVersion={_q(version)} TaskControllerManufacturer="{WRITER}" '
         f'TaskControllerVersion={_q(version)} DataTransferOrigin="2">',
         '\t<AFE A="LINKLIST.XML" B="1" C="OCED" D="1"/>',
         '\t<CPC A="CPC-1" B="HARVESTING"/>']
    for j, c in enumerate(crops[:1]):
        X.append(f'\t<CTP A="CTP-{j + 1}" B={_q(c)}/>')
    X.append('\t<CTR A="CTR-1" B="OCED clean data"/>')
    X += dvc_xml
    X.append('\t<FRM A="FRM-1" B="OCED clean data" I="CTR-1"/>')
    for j, p in enumerate(products):
        X.append(f'\t<PDT A="PDT-{j + 1}" B={_q(p)} F="1"/>')
    ctp = ' G="CTP-1"' if crops else ""
    for j, f in enumerate(fields):
        X.append(f'\t<PFD A="PFD-{j + 1}" C={_q(f)} D="0" E="CTR-1" F="FRM-1"{ctp}/>')
    X += tsk_xml
    X.append("</ISO11783_TaskData>")
    with open(os.path.join(tdir, "TASKDATA.XML"), "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(X) + "\r\n")
    LX = ['<?xml version="1.0" encoding="UTF-8"?>',
          f'<ISO11783LinkList VersionMajor="4" VersionMinor="2" ManagementSoftwareManufacturer="{WRITER}" '
          f'ManagementSoftwareVersion={_q(version)} TaskControllerManufacturer="{WRITER}" '
          f'TaskControllerVersion={_q(version)} DataTransferOrigin="2">']
    for j, (ident, uid, des) in enumerate(lnk):         # a combine's device, then its task(s)
        kind = "Device UUIDs" if ident.startswith("DVC") else "Task UUIDs"
        LX += [f'\t<LGP A="LGP-{j + 1}" B="1" E="{kind}">', f'\t\t<LNK A="{ident}" B="{uid}" C={_q(des)}/>',
               "\t</LGP>"]
    LX.append("</ISO11783LinkList>")
    with open(os.path.join(tdir, "LINKLIST.XML"), "w", encoding="utf-8", newline="") as fh:
        fh.write("\r\n".join(LX) + "\r\n")
    files = ["TASKDATA/TASKDATA.XML", "TASKDATA/LINKLIST.XML"] + files
    I = pd.concat(index, ignore_index=True)
    index_csv = os.path.join(out_dir, f"{name}_index.csv")
    I.to_csv(index_csv, index=False)
    zpath = os.path.join(out_dir, f"{name}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(os.path.join(folder, f), f)
    # read back and compare with what was meant
    V = verify(tdir, R, I)
    V["readings_without_lead_in"] = int(sum(r["n_readings"] - r["lead_ins"] for r in mrep))
    V["lead_ins_in_runs"] = int(sum(r["lead_ins_in_runs"] for r in mrep))
    V["time_logs"] = int(sum(r["time_logs"] for r in mrep))
    # how far after its Time a reading is written (0 unless no time log had room for it at its Time)
    late = (I.t_written_ms - I.t_clean_ms).to_numpy(np.int64)
    V["n_late"] = int((late > CHAIN_TOL_MS).sum())
    V["max_late_s"] = float(max(int(late.max()), 0)) / 1000.0 if len(late) else 0.0
    # the readings with no grain are written but are not points when the set is read: the totals of the points read
    # back are compared with those of the readings with grain
    nog = _no_grain(R)
    V["n_no_grain"] = int(nog.sum())
    V["area_no_grain_ac"] = float(R.area_ac[nog].sum())
    meant_pts = V["totals_meant"]["area_ac"] - V["area_no_grain_ac"]
    V["total_area_rel_points"] = V["totals_read"]["area_ac"] / meant_pts - 1 if meant_pts else float("nan")
    if V["n_points"] != len(R):
        warns.append(f"read back {V['n_points']:,} points, wrote {len(R):,} readings"
                     + (f" ({V['n_no_grain']:,} of them with no grain)" if V["n_no_grain"] else ""))
    n_src = (source or {}).get("n_readings")
    short = sum(r["durations_shortened"] for r in mrep)
    lead_n = sum(r["lead_ins"] for r in mrep)
    notes.append(f"lead_in={lead_in!r}: {V['readings_without_lead_in']:,} of {len(R):,} readings written as monitor "
                 f"records (the step from the previous reading), {lead_n:,} after a lead-in record, "
                 f"{sum(r['trail_outs'] for r in mrep):,} trail-out records; every reading at its own Time"
                 + ("" if not V["n_late"] else f" but {V['n_late']:,} (below)"))
    for r in mrep:
        if r["time_logs"] > 1:
            notes.append(f"{r['machine']}: written in {r['time_logs']} time logs ({', '.join(r['tlgs'])}; tasks "
                         f"'... (2)' and so on), {r['readings_in_further_logs']:,} of its {r['n_readings']:,} readings "
                         "in the further ones: a reading whose position step from the previous one is not its "
                         f"distance needs a lead-in record, SMS puts records closer than {MIN_GAP_MS / 1000:g} s "
                         "together, so it is written at its own Time in another time log of the same combine "
                         "instead of later in the same one. SMS shows one dataset per time log")
        if r["n_late"]:
            warns.append(f"{r['n_late']:,} readings of {r['machine']} are written up to {r['max_late_ms'] / 1000:.1f} "
                         f"s after their Time: they follow each other closer than {MIN_GAP_MS / 1000:g} s, the least "
                         f"SMS keeps apart, in more places than {TIME_LOGS_MAX} time logs can take (their grain, "
                         "area and position are kept)")
    if short:
        notes.append(f"{short:,} readings are written with another duration than the clean file's (largest "
                     f"difference {max(r['max_duration_short_ms'] for r in mrep)} ms; their flow is changed by the "
                     f"same ratio, so the wet mass is kept): readings shorter than {MIN_GAP_MS / 1000:g} s, written "
                     f"with {MIN_GAP_MS / 1000:g} s (SMS puts a record together with the next one when that follows "
                     "sooner), and readings whose lead-in had less room than their duration")
    notes.append(f"per-reading area of the written set vs the clean file: p99 {100 * V['p99_area_rel']:.2f} %, max "
                 f"{100 * V['max_area_rel']:.2f} %; total {100 * V['total_area_rel']:+.5f} %")
    rel = V["total_area_rel_points"]
    grain = " of its readings with grain" if V["n_no_grain"] else ""
    if np.isfinite(rel) and abs(rel) > 0.001 and lead_in != "always":
        warns.append(f"the total area of the points read back differs from the clean file's{grain} by {100 * rel:+.2f} "
                     "%: the readings written as monitor records take SMS's step between positions as their distance "
                     "(lead-in records before every reading keep the total exact, but every Duration then rests on "
                     "the previous-record rule: the writer's option lead_in='always', in the app 'ISOXML: lead-in "
                     "records' of the writers' advanced options)")
    elif np.isfinite(rel) and abs(rel) > 0.001:
        warns.append(f"the total area of the points read back differs from the clean file's{grain} by {100 * rel:+.2f} "
                     "%, with a lead-in record before every reading")
    if V.get("n_area_off_1pct"):
        warns.append(f"{V['n_area_off_1pct']:,} of {len(R):,} readings have a written area more than 1 % off the "
                     f"clean one (p99 {100 * V['p99_area_rel']:.2f} %, largest {100 * V['max_area_rel']:.1f} %): the "
                     "1e-7 deg position grid (about 1.1 cm) leaves few lead-in positions near the wanted distance on "
                     "passes running exactly north-south or east-west, and readings shorter than about a centimetre "
                     "cannot be written")
    no_el = sum(r["no_elevation"] for r in mrep)
    if no_el:
        filled = sum(r["no_elevation_filled"] for r in mrep)
        warns.append(f"{no_el:,} readings without an elevation: {filled:,} written with the nearest elevation of their "
                     f"combine, {no_el - filled:,} as 0 (SMS shows a null 0x7FFFFFFF as 7,045,550 ft)")
    notes.append("time latency (DDI 143) and every offset written 0: SMS places each point where the clean file has it")
    notes.append(CAVEAT)
    return {"path": folder, "zip": zpath, "n_kept": int(len(R)),
            "n_removed": (int(n_src) - int(len(R))) if n_src else None,
            "files_changed": files, "notes": notes, "warnings": warns, "verify": V, "machines": mrep,
            "index_csv": index_csv, "test_weight_lb_bu": tw, "std_moisture_pct": ms, "lead_in": lead_in,
            "sms_tested": False,
            "totals": {"n": int(len(R)), "wet_lb": float(R.wet_lb.sum()), "area_ac": float(R.area_ac.sum()),
                       "dry_bu": float(R.dry_lb.sum() / tw)}}


# ================================================================================================= reading back
def read_points(taskdata_dir: str) -> pd.DataFrame:
    """The points SMS makes of a TASKDATA set, by the rules measured on a set SMS read: the reader of
    engine/formats/isoxml.py (sms_points: sections on and flow > 0, Duration and Distance from the previous record,
    records closer than 0.9 s put together, the latency and the offsets applied). One row per point: Machine, TLG,
    record (its index in the log), t_ms, lon, lat, elev_ft, dur_s, dist_ft, width_ft, flow_lbs, moist, wet_lb,
    area_ac; the monitor's own values at the record: wset_ft (setpoint width) and dry_lbac (dry mass per area); and
    what a reader with another convention would get: dur_next_s (the time to the next record) and dist_prev_on_ft
    (the step from the previous point)."""
    from engine.formats import isoxml
    ts = isoxml.read_taskdata(taskdata_dir)
    logs, _, _ = isoxml._scan_set(taskdata_dir)
    rows = []
    for L in logs:
        log = isoxml._load(L)
        for element in L.yield_elements:
            S = isoxml._series(L, ts, log, element)
            if S is None:                                  # no grain on this header: no point
                continue
            pts, _ = isoxml.sms_points(S)
            if not len(pts):
                continue
            rec = pts.rec.to_numpy(int)
            dtn = np.r_[np.diff(S.t), np.nan] / 1000.0
            la, lo = pts.lat_gps.to_numpy(float), pts.lon_gps.to_numpy(float)
            own = {k: log.column(log.index(DDI[k], element))[rec] for k in ("setpoint_width", "dry_mass_area")}
            sp = np.r_[np.nan, _sms_step_m(la[:-1], lo[:-1], la[1:], lo[1:])] if len(pts) else np.zeros(0)
            rows.append(pd.DataFrame({
                "Machine": L.machine, "TLG": L.names[0], "record": rec, "t_ms": pts.t_ms.to_numpy(np.int64),
                "lon": pts.lon.to_numpy(float), "lat": pts.lat.to_numpy(float),
                "elev_ft": pts.alt_m.to_numpy(float) / M_PER_FT, "dur_s": pts.dur_s.to_numpy(float),
                "dist_ft": pts.dist_m.to_numpy(float) / M_PER_FT, "width_ft": pts.width_m.to_numpy(float) / M_PER_FT,
                "dur_next_s": dtn[rec], "dist_prev_on_ft": sp / M_PER_FT,
                "flow_lbs": pts.grain.to_numpy(float) / 1e6 * LB_PER_KG, "moist": pts.moist.to_numpy(float),
                "wset_ft": own["setpoint_width"] / 304.8,
                "dry_lbac": own["dry_mass_area"] / 1e6 * LB_PER_KG * 4046.8564224}))
    cols = ["Machine", "TLG", "record", "t_ms", "lon", "lat", "elev_ft", "dur_s", "dist_ft", "width_ft", "dur_next_s",
            "dist_prev_on_ft", "flow_lbs", "moist", "wset_ft", "dry_lbac"]
    P = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=cols)
    P["wet_lb"] = P.flow_lbs * P.dur_s
    P["area_ac"] = P.dist_ft * P.width_ft / SQFT_PER_AC
    return P


def verify(taskdata_dir: str, R: pd.DataFrame, index: pd.DataFrame) -> dict:
    """Read the written set back (read_points) and compare every point with the reading it was written from; also
    the totals the set would give under the conventions not established (Duration to the next record, Distance from
    the previous point)."""
    P = read_points(taskdata_dir)
    J = index.merge(P, on=["TLG", "record"], how="left", suffixes=("", "_r"))
    Rr = R.set_index("src_row").loc[J.src_row.to_numpy()]
    out = {"n_points": int(len(P)), "n_matched": int(J.flow_lbs.notna().sum())}

    def mx(a, b):
        d = np.abs(np.asarray(a, float) - np.asarray(b, float))
        d = d[np.isfinite(d)]
        return float(d.max()) if len(d) else float("nan")
    pos_m = np.hypot((J.lon.to_numpy() - Rr.lon.to_numpy()) * 111_320 * np.cos(np.radians(Rr.lat.to_numpy())),
                     (J.lat.to_numpy() - Rr.lat.to_numpy()) * 111_320)
    out["max_position_cm"] = float(np.nanmax(pos_m) * 100) if len(pos_m) else float("nan")
    out["max_duration_s"] = mx(J.dur_s, Rr.dur_s)
    out["max_width_ft"] = mx(J.width_ft, Rr.width_ft)
    out["max_moisture_pct"] = mx(J.moist, Rr.moist)
    out["max_wet_lb"] = mx(J.wet_lb, Rr.wet_lb)
    with np.errstate(divide="ignore", invalid="ignore"):
        ar = np.abs(J.area_ac.to_numpy() / Rr.area_ac.to_numpy() - 1.0)
    out["max_area_rel"] = float(np.nanmax(ar)) if len(ar) else float("nan")
    out["p99_area_rel"] = float(np.nanquantile(ar, 0.99)) if len(ar) else float("nan")
    out["n_area_off_1pct"] = int((ar > 0.01).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        yr = np.abs((J.wet_lb / J.area_ac).to_numpy() / (Rr.wet_lb / Rr.area_ac).to_numpy() - 1.0)
    out["max_wet_yield_rel"] = float(np.nanmax(yr)) if len(yr) else float("nan")
    out["p99_wet_yield_rel"] = float(np.nanquantile(yr, 0.99)) if len(yr) else float("nan")
    out["totals_read"] = {"n": int(len(P)), "wet_lb": float(P.wet_lb.sum()), "area_ac": float(P.area_ac.sum())}
    out["totals_meant"] = {"n": int(len(R)), "wet_lb": float(R.wet_lb.sum()), "area_ac": float(R.area_ac.sum())}
    out["total_area_rel"] = out["totals_read"]["area_ac"] / out["totals_meant"]["area_ac"] - 1 \
        if out["totals_meant"]["area_ac"] else float("nan")
    out["total_wet_rel"] = out["totals_read"]["wet_lb"] / out["totals_meant"]["wet_lb"] - 1 \
        if out["totals_meant"]["wet_lb"] else float("nan")
    # the conventions not established: what SMS would show if it used them
    wet_next = float(np.nansum(P.flow_lbs * P.dur_next_s))
    area_on = float(np.nansum(P.dist_prev_on_ft * P.width_ft) / SQFT_PER_AC)
    m = out["totals_meant"]
    out["if_duration_to_next_record_wet_rel"] = wet_next / m["wet_lb"] - 1 if m["wet_lb"] else float("nan")
    out["if_distance_from_previous_point_area_rel"] = area_on / m["area_ac"] - 1 if m["area_ac"] else float("nan")
    return out
