"""Small area cut AFTER the whole-field cleaning (OCED 0.3.6).

The field of interest (engine/clean/aoi.py) cuts BEFORE the cleaning, so a small polygon given there gets its 3-sigma
limits from its own few readings. This step instead takes the readings the whole-field cleaning kept and counts, for
each polygon of a polygon file, the readings that fall in it under an edge rule (default: clip, the polygon's line
cuts the footprints, as the user chose for small plots; the whole-field cleaning's own clip, S1, is not this):

  clip   the footprint clipped to the polygon: every reading whose footprint overlaps the polygon counts with the
         area of the overlap only (area-weighted).
  full   the whole footprint inside (as SMS's query of a polygon): a reading counts when the polygon covers its whole
         footprint (1 mm tolerance).
  point  the reading's point inside; the reading counts with its whole area.

The footprint is the rectangle of the reading's width and distance along its heading (Track_deg_) that ENDS at the
reading's point. For the kept readings that is the clean file's own reading: Wdth_Opt x Dist_Opt at the point of the
flagged / clean file, which Optimize Swath Widths (S2) moved sideways to the middle of the strip it kept when it
narrowed the reading; for every reading without the cleaning it is the reading as logged: Swth_Wdth_ x Distance_f at
the logged point (X_log / Y_log, WGS 84).

Figures per polygon, for the kept readings (Keep = 1, yield Yld_Vol_Dr x Swath_Scl, area Dist_Opt x Wdth_Opt, as
the clean file) and for every reading of the flagged file without the cleaning (the readings as imported, after the
field clip: yield Yld_Vol_Dr, area Distance_f x Swth_Wdth_): readings, area (ac), total dry bu (sum of yield x
area), area-weighted dry yield (bu/ac), plain mean, min, max, population SD (as SMS), moisture mean, and the readings
of the polygon the cleaning removed, per step (Rem_By).

It only reads the cleaning's flagged file; it writes <tag>_small_area.csv, <tag>_small_area.zip (a point shapefile:
the kept readings that count under the rule, with the polygon's name, the share of the strip counted, the area
counted, the yield used and the bushels) and <tag>_small_area_parts.zip (a polygon shapefile of the counted parts of
the strips: the clipped part under 'clip', the whole strip under 'full' and 'point', with SA_Share, SA_Area_ac, SA_Bu,
SA_Rule, SA_Why) and never touches the clean, flagged or DIFM files.

Per reading (0.3.7): measure() also gives, for every reading whose strip (at the clean file's position) touches a
polygon (or lies within a margin of it), what the rule did with it (M['readings']): counted or not and why, the share
of its strip inside, the area counted, the yield used, the bushels (yield x area), its strip and the counted part.
The app's map of the small area, its hover text (reading_text), the two shapefiles and the replay's small-area
columns (replay_part) all read these rows, so the figures of the table are the sums of the rows shown, and a change of
the estimator here changes all of them together.

The names above are OCED's (raw monitor data, an SMS export, a KML export). The flagged file keeps the columns of the
file that was cleaned under their own names, so (0.4.0) the small area reads the columns the cleaning read, from its
record (columns_of): an Operations Center export's dry yield is its VRYIELDVOL (as the import wrote it), its distance
DISTANCE, its width SWATHWIDTH, its heading Heading, its moisture Moisture; the texts name the columns read.
"""
from __future__ import annotations

import math
import os
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

from engine.clean import aoi as aoi_mod

EDGE_RULES = {"clip": "footprint clipped by the polygon's line (area-weighted)",
              "full": "whole footprint inside (as SMS's query)",
              "point": "the reading's point inside"}
DEFAULT_RULE = "clip"                     # the first of EDGE_RULES: the app's list starts with it
FT_M = 0.3048
FT2_PER_AC = 43560.0
M2_PER_AC = 4046.8564224
COVER_TOL_M = 0.001                       # 'full': the polygon grown by 1 mm covers the footprint (rounding only)
CSV_COLUMNS = ["polygon", "set", "rule", "readings", "area_ac", "total_dry_bu", "dry_yield_bu_ac", "mean_bu_ac",
               "min_bu_ac", "max_bu_ac", "sd_bu_ac", "moisture_mean_pct", "removed_by_cleaning", "removed_by_step",
               # 0.3.7 (section J): the figure of the method chosen, grain / ground, the SMS query, the ranges
               "method", "figure_bu_ac", "ground_dry_yield_bu_ac", "ground_grain_bu", "ground_ac", "ground_pct",
               "ground_readings", "ground_moisture_pct", "ground_removed_grain_bu", "ground_below_min_pct",
               "ground_transient_pct", "sms_readings", "sms_area_ac", "sms_total_dry_bu", "sms_dry_yield_bu_ac",
               "spread_lo_bu_ac", "spread_hi_bu_ac", "spread_pct", "calibration_cv_pct", "calibration_lo_bu_ac",
               "calibration_hi_bu_ac", "interior_m"]
OLD_COLUMNS = CSV_COLUMNS[:14]
# the small area's figure (0.3.7, decided 2026-11 after the weigh-wagon checks: grain / ground)
METHODS = {"ground": "grain / ground",
           "cleaned": "cleaned map average",
           "sms": "as SMS's query"}
METHOD_HELP = {
    "ground": "every reading inside the polygon, whatever the cleaning did with it, and those the import left out "
              "(read from the decoded file); each logged strip clipped by the line; grain = dry yield x logged area "
              "x share inside; ground = the area the clipped strips cover (overlaps once); yield = grain / ground",
    "cleaned": "the readings the cleaning kept, at the clean file's strip (Wdth_Opt x Dist_Opt), under the edge "
               "rule, area-weighted (the 0.3.6 figure)",
    "sms": "the readings the cleaning kept whose whole strip is inside, their grain / their own area (as SMS's "
           "query of a polygon)"}
DEFAULT_METHOD = "ground"
LEGACY_METHOD_TEXT = "cleaned map average (0.3.6)"
N_BOOT = 4000                             # the spread inside the polygon: moving-block bootstrap draws
BLOCK_M = 30.0                            # its blocks: about 30 m of consecutive readings of one pass
SEED = 20261120                           # fixed: same file, same polygons, same options -> same numbers
TRANSIENT_M = 10.0                        # the first / last 10 m of a pass (the elevator filling, emptying)
TRANSIENT_WARN = 0.15                     # a warning when they are more than 15 % of the ground
PASS_TURN_DEG = 60.0                      # a new pass: a heading change of more than 60 deg,
PASS_STEP = (1.5, 0.3)                    # or a step longer than 1.5 x the distance + 0.3 m (the replay's rule)
SAME_SPOT_DEG = 1e-7                      # one logged position: within 1e-7 deg (about 1 cm) in lon and in lat
CV_HELP = ("The load-to-load coefficient of variation of this combine's calibration (monitor / scale), in %. Measure it "
           "on this combine: monitor against the scale, load by load. Empty or 0: no range.")
SETS = {"kept": "after the cleaning (the readings it kept)", "raw": "without the cleaning (the readings as imported)"}


def rule_key(rule) -> str:
    r = str(rule or DEFAULT_RULE).strip().lower()
    alias = {"footprint": "full", "whole": "full", "sms": "full", "logged": "point", "points": "point",
             "area": "clip", "clipped": "clip", "weighted": "clip"}
    r = alias.get(r, r)
    if r not in EDGE_RULES:
        raise ValueError(f"edge rule {rule!r}: use one of {', '.join(EDGE_RULES)}")
    return r


def read_polygons(path: str) -> tuple[gpd.GeoDataFrame, list]:
    """(polygons with a 'name' column, notes): every polygon of the file (zip / shp / geojson / gpkg / kml / kmz),
    named by its name column (name, field, label ...; else Bnd_Name / Plot_Id / id) or by its number (1, 2, ...)."""
    if not path or not os.path.exists(path):
        raise ValueError(f"small area: polygon file not found: {path}")
    gdf, notes = aoi_mod._read_vector(path)
    if gdf.crs is None:
        notes.append(f"{os.path.basename(path)} has no coordinate system: taken as WGS 84")
        gdf = gdf.set_crs(4326)
    gdf = gdf[gdf.geometry.notna() & gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf[~gdf.geometry.is_empty]
    if not len(gdf):
        raise ValueError(f"small area: {os.path.basename(path)} holds no polygon")
    gdf["geometry"] = gdf.geometry.make_valid()
    col = aoi_mod._name_col(gdf.columns)
    if col is None:
        for c in ("Bnd_Name", "Plot_Id", "PLOT_ID", "plot", "Plot", "id", "ID", "Id"):
            if c in gdf.columns:
                col = c
                break
    names = []
    for i, v in enumerate(gdf[col].tolist() if col else [None] * len(gdf), start=1):
        s = "" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v).strip()
        names.append(s or str(i))
    seen: dict = {}
    for i, n in enumerate(names):                   # two polygons of one name: 'A', 'A (2)'
        seen[n] = seen.get(n, 0) + 1
        if seen[n] > 1:
            names[i] = f"{n} ({seen[n]})"
    gdf = gdf.reset_index(drop=True)
    gdf["name"] = names
    return gdf[["name", "geometry"]], notes


def footprints(x, y, heading_deg, length_m, width_m) -> np.ndarray:
    """Rectangles (shapely polygons, projected metres) of width width_m and length length_m along the heading
    (degrees clockwise from north) that END at (x, y); a reading of no length or no width is its point."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    th = np.radians(np.nan_to_num(np.asarray(heading_deg, float)))
    L, W = np.nan_to_num(np.asarray(length_m, float)), np.nan_to_num(np.asarray(width_m, float))
    ux, uy = np.sin(th), np.cos(th)                  # along the travel
    vx, vy = np.cos(th), -np.sin(th)                 # across (to the right)
    h = W / 2.0
    bx, by = x - L * ux, y - L * uy                  # where the reading started
    ring = np.stack([np.stack([x - h * vx, y - h * vy], -1), np.stack([x + h * vx, y + h * vy], -1),
                     np.stack([bx + h * vx, by + h * vy], -1), np.stack([bx - h * vx, by - h * vy], -1),
                     np.stack([x - h * vx, y - h * vy], -1)], axis=1)
    geoms = shapely.polygons(ring)
    flat = ~((L > 0) & (W > 0))
    if flat.any():
        geoms[flat] = shapely.points(x[flat], y[flat])
    return geoms


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def _num(df, c, default=np.nan):
    if c is None:
        return np.full(len(df), default, float)
    return pd.to_numeric(df[c], errors="coerce").to_numpy(float)


# The columns of the flagged file the small area reads are the cleaning's own (0.4.0): the flagged file keeps the
# columns of the file that was cleaned under their own names (an Operations Center export: VRYIELDVOL, DISTANCE,
# SWATHWIDTH, Heading, Moisture ...; raw monitor data, an SMS export or a KML: OCED's / SMS's Yld_Vol_Dr, Distance_f,
# Swth_Wdth_, Track_deg_, Moisture__), and the cleaning resolved which column holds what (its record's 'columns':
# yield_clean.resolve_columns, detected or given in the settings' 'cols'). Units as the cleaning takes them: the dry
# yield in bu/ac, distance and width in ft, heading in degrees, moisture in %, speed in mph, duration in s; no
# distance column: speed x duration (as the cleaning); no width column: the settings' harvester width.
SA_KEYS = ("yield", "distance_ft", "width_ft", "heading", "moisture", "speed_mph", "duration_s", "dataset", "order",
           "time", "machine")
OCED_COLUMNS = {"yield": "Yld_Vol_Dr", "distance_ft": "Distance_f", "width_ft": "Swth_Wdth_",
                "heading": "Track_deg_", "moisture": "Moisture__"}
COLUMN_WORDS = {"yield": "dry yield (bu/ac)", "distance_ft": "distance (ft)", "width_ft": "swath width (ft)",
                "heading": "heading (deg)", "moisture": "moisture (%)"}


def cleaning_record(flagged_path) -> dict | None:
    """The cleaning record (<tag>_cleaning.json) next to a flagged file (<tag>_flagged.zip / .shp), or None."""
    if not flagged_path:
        return None
    base = os.path.abspath(str(flagged_path))
    for suf in ("_flagged.zip", "_flagged.shp"):
        if base.endswith(suf):
            js = base[:-len(suf)] + "_cleaning.json"
            if os.path.exists(js):
                try:
                    import json
                    with open(js, encoding="utf-8") as f:
                        R = json.load(f)
                    return R if isinstance(R, dict) else None
                except (OSError, ValueError):
                    return None
            return None
    return None


def columns_of(flagged: gpd.GeoDataFrame, R: dict | None = None) -> dict:
    """{key: column of the flagged file or None} for SA_KEYS, plus 'harvester_width_ft' (the settings' constant width
    of a file without a width column, else None) and 'source': the columns the cleaning resolved (R['columns'], the
    cleaning record) when R gives them, each one checked against the flagged file; else the cleaning's own detection
    (yield_clean.detect_columns) over the flagged file's columns, which finds the same names (the columns the cleaning
    adds to the flagged file are none of the names it looks for)."""
    from engine.clean.yield_clean import detect_columns
    names = [c for c in flagged.columns if c != "geometry"]
    det = detect_columns(names)
    rc = R.get("columns") if isinstance(R, dict) and isinstance(R.get("columns"), dict) else None
    out = {}
    for k in SA_KEYS:
        if rc is not None and k in rc and (rc[k] is None or rc[k] in names):
            out[k] = rc[k]
        else:
            out[k] = det.get(k)
    hw = ((R.get("settings") or {}).get("harvester_width_ft") if isinstance(R, dict) else None)
    try:
        hw = float(hw) if hw is not None and float(hw) > 0 else None
    except (TypeError, ValueError):
        hw = None
    out["harvester_width_ft"] = hw
    out["source"] = "the cleaning record" if rc is not None else "found in the flagged file"
    return out


def legacy_columns(cols: dict | None) -> bool:
    """True when the columns read are OCED's own names (raw monitor data, an SMS export, a KML): the small area's
    record then stays as it was before 0.4.0 (no 'columns' key). The settings' harvester width counts only for a file
    without a width column (the one it is used for): with Swth_Wdth_ there, the width read is that column."""
    if not cols:
        return True
    return (all(cols.get(k) == v for k, v in OCED_COLUMNS.items() if k != "moisture")
            and cols.get("moisture") in (None, "Moisture__", "Moisture")
            and not (cols.get("harvester_width_ft") and not cols.get("width_ft")))


def _dist_text(cols: dict) -> str:
    if cols.get("distance_ft") or not (cols.get("speed_mph") and cols.get("duration_s")):
        return cols.get("distance_ft") or OCED_COLUMNS["distance_ft"]
    return f"({cols['speed_mph']} x {cols['duration_s']}, speed x duration)"


def _width_text(cols: dict) -> str:
    if cols.get("width_ft") or not cols.get("harvester_width_ft"):
        return cols.get("width_ft") or OCED_COLUMNS["width_ft"]
    return f"the harvester width {float(cols['harvester_width_ft']):g} ft"


def kept_text(cols: dict | None) -> str:
    """'Yld_Vol_Dr x Swath_Scl over Dist_Opt x Wdth_Opt': the yield and area of the kept readings, by the columns
    read (cols: columns_of, or a small-area record's 'columns'; None: OCED's names)."""
    y = (cols or {}).get("yield") or OCED_COLUMNS["yield"]
    return f"{y} x Swath_Scl over Dist_Opt x Wdth_Opt"


def raw_text(cols: dict | None) -> str:
    """'Yld_Vol_Dr over Distance_f x Swth_Wdth_': the yield and area of a reading as imported, by the columns read."""
    if not cols:
        return f"{OCED_COLUMNS['yield']} over {OCED_COLUMNS['distance_ft']} x {OCED_COLUMNS['width_ft']}"
    return f"{cols.get('yield') or OCED_COLUMNS['yield']} over {_dist_text(cols)} x {_width_text(cols)}"


def _missing(key: str, cols: dict, flagged) -> str:
    """The plain message of a column the small area needs and the flagged file does not have."""
    from engine.clean.yield_clean import COLUMN_ALIASES
    names = ", ".join(COLUMN_ALIASES.get(key, [])[:4])
    rc = cols.get("source") == "the cleaning record"
    return (f"small area: the cleaned file has no {COLUMN_WORDS[key]} column, so the plots cannot be measured "
            + ("(the cleaning's record names none that is still in the flagged file)" if rc else
               f"(none of {names} or the like is in the flagged file)")
            + ". Clean this file again in step 3 and press Measure again; if the cleaning cannot find it either, the "
              "file itself has no such column: export it again with its " + COLUMN_WORDS[key].split(" (")[0]
            + " (columns in the flagged file: " + ", ".join(c for c in flagged.columns if c != "geometry")[:400]
            + ")")


def prepare(flagged: gpd.GeoDataFrame, cols: dict | None = None) -> dict:
    """The arrays of both sets from the flagged file: the position of each set with its CRS (kept: the file's point,
    which S2 moved to the middle of the strip it kept when it narrowed the reading; raw: the logged point X_log /
    Y_log, which OCED writes in WGS 84 whatever the file's CRS, taken in the file's CRS only when its values cannot
    be longitudes / latitudes), heading, yield, length / width (ft), moisture, Keep, Rem_By. cols: the columns read
    (columns_of; None: found in the flagged file as the cleaning finds them)."""
    cols = cols if cols is not None else columns_of(flagged)
    fcrs = flagged.crs or "EPSG:4326"
    xk, yk = flagged.geometry.x.to_numpy(float), flagged.geometry.y.to_numpy(float)
    xl, yl = _col(flagged, "X_log"), _col(flagged, "Y_log")
    if xl and yl:
        x, y = _num(flagged, xl), _num(flagged, yl)
        ok = np.isfinite(x) & np.isfinite(y)
        lonlat = bool(ok.any()) and bool((np.abs(x[ok]) <= 180).all() and (np.abs(y[ok]) <= 90).all())
        rcrs = "EPSG:4326" if lonlat else fcrs
        if (~ok).any():                              # no logged position: the file's point, in the logged CRS
            gx = gpd.GeoSeries(shapely.points(xk[~ok], yk[~ok]), crs=fcrs).to_crs(rcrs)
            x[~ok], y[~ok] = gx.x.to_numpy(float), gx.y.to_numpy(float)
        pos = ("kept: the clean file's point (moved by Optimize Swath Widths when it narrowed the reading); "
               "raw: X_log / Y_log")
    else:
        x, y, rcrs = xk.copy(), yk.copy(), fcrs
        pos = "the point geometry (no X_log / Y_log)"
    keep = _num(flagged, _col(flagged, "Keep"), 1.0)
    have = set(flagged.columns)
    ycol = cols.get("yield") if cols.get("yield") in have else None
    if ycol is None:
        raise ValueError(_missing("yield", cols, flagged))
    yraw = _num(flagged, ycol)
    scl = _num(flagged, _col(flagged, "Swath_Scl"), 1.0)
    scl = np.where(np.isfinite(scl), scl, 1.0)
    dcol = cols.get("distance_ft") if cols.get("distance_ft") in have else None
    if dcol:
        d_raw = _num(flagged, dcol)
    elif cols.get("speed_mph") in have and cols.get("duration_s") in have:
        # as the cleaning: distance = speed x duration (mph -> m/s, then ft)
        d_raw = _num(flagged, cols["speed_mph"]) * 0.44704 * _num(flagged, cols["duration_s"]) / FT_M
    else:
        raise ValueError(_missing("distance_ft", cols, flagged))
    wcol = cols.get("width_ft") if cols.get("width_ft") in have else None
    if wcol:
        w_raw = _num(flagged, wcol)
    elif cols.get("harvester_width_ft"):
        w_raw = np.full(len(flagged), float(cols["harvester_width_ft"]))       # as the cleaning: the constant width
    else:
        raise ValueError(_missing("width_ft", cols, flagged))
    d_opt = _num(flagged, _col(flagged, "Dist_Opt")) if _col(flagged, "Dist_Opt") else d_raw.copy()
    w_opt = _num(flagged, _col(flagged, "Wdth_Opt")) if _col(flagged, "Wdth_Opt") else w_raw.copy()
    rem = (flagged["Rem_By"].astype(object).where(flagged["Rem_By"].notna(), "").astype(str).str.strip().to_numpy()
           if "Rem_By" in flagged.columns else np.full(len(flagged), "", object))
    hcol = cols.get("heading") if cols.get("heading") in have else None
    mcol = cols.get("moisture") if cols.get("moisture") in have else None
    used = {k: cols.get(k) for k in SA_KEYS}           # the columns read, as read (the texts and the record name them)
    used.update({"yield": ycol, "distance_ft": dcol, "width_ft": wcol, "heading": hcol, "moisture": mcol,
                 "harvester_width_ft": (None if wcol else cols.get("harvester_width_ft")),
                 "source": cols.get("source")})
    return {"x": x, "y": y, "heading": _num(flagged, hcol, 0.0),
            "keep": np.where(np.isfinite(keep), keep, 0) == 1, "rem": rem,
            "moist": _num(flagged, mcol),
            "kept": {"yield": yraw * scl, "len_ft": d_opt, "wid_ft": w_opt, "x": xk, "y": yk, "crs": fcrs},
            "raw": {"yield": yraw, "len_ft": d_raw, "wid_ft": w_raw, "x": x, "y": y, "crs": rcrs},
            "position": pos, "yield_column": ycol, "columns": used}


def _figures(yv, area_ac, moist, rem, removed_mask) -> dict:
    ok = np.isfinite(yv) & np.isfinite(area_ac)
    yv, area_ac, moist = yv[ok], area_ac[ok], moist[ok]
    a = float(area_ac.sum())
    bu = float((yv * area_ac).sum())
    mm = moist[np.isfinite(moist)]
    out = {"readings": int(len(yv)), "area_ac": a, "total_dry_bu": bu,
           "dry_yield_bu_ac": (bu / a if a > 0 else None),
           "mean_bu_ac": (float(yv.mean()) if len(yv) else None),
           "min_bu_ac": (float(yv.min()) if len(yv) else None),
           "max_bu_ac": (float(yv.max()) if len(yv) else None),
           "sd_bu_ac": (float(yv.std(ddof=0)) if len(yv) else None),
           "moisture_mean_pct": (float(mm.mean()) if len(mm) else None)}
    if removed_mask is not None:
        r = rem[removed_mask]
        steps = {}
        for s in r:
            steps[s or "?"] = steps.get(s or "?", 0) + 1
        out["removed_by_cleaning"] = int(removed_mask.sum())
        out["removed_by_step"] = dict(sorted(steps.items()))
    return out


def _labels(flagged, cols: dict | None = None) -> dict:
    """The combine, the time and the record id of every reading of the flagged file (text), for the hover text; the
    columns the cleaning used (cols: columns_of; None: found in the flagged file as the cleaning finds them)."""
    d = cols if cols is not None else columns_of(flagged)
    out = {}
    for k in ("machine", "time", "order"):
        c = d.get(k)
        if c and c in flagged.columns:
            v = flagged[c]
            out[k] = np.array(["" if (x is None or (isinstance(x, float) and math.isnan(x))) else
                               (str(int(x)) if isinstance(x, (int, np.integer)) or (isinstance(x, float) and
                                                                                    float(x).is_integer()) else str(x))
                               for x in v.tolist()], dtype=object)
        else:
            out[k] = np.full(len(flagged), "", object)
    return out


WHY = {"clip": "footprint clipped by the line: the part inside counted",
       "full_in": "whole footprint inside: counted whole",
       "full_cross": "crosses the line: not counted (whole footprint inside only)",
       "point_in": "point inside: counted whole",
       "point_out": "point outside: not counted",
       "no_area": "no width or no distance: no area to count",
       "outside": "outside the polygon: not counted",
       "removed": "removed by the cleaning: not counted"}


def measure(flagged: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, rule: str = DEFAULT_RULE,
            detail_margin_m: float = 0.0, cols: dict | None = None) -> dict:
    """{'rule', 'crs', 'polygons': [{name, area_ac, kept: figures, raw: figures}], 'rows': {name: (index of the
    kept readings that count, area counted ac, yield used)}, 'readings': {name: per-reading rows}}. The per-reading
    rows (every reading of the flagged file whose strip at the clean file's position touches the polygon grown by
    detail_margin_m): idx (row of the flagged file), counted, why (a WHY key), share (of the strip inside the
    polygon), full_ac (the strip's area, distance x width), area_ac (counted), yield (used, bu/ac), bu (yield x area
    counted; 0 not counted), removed_by (Rem_By of a reading the cleaning removed), machine, time, record, fp (the
    strip) and part (the part counted: the strip clipped to the polygon under 'clip', the whole strip otherwise; None
    not counted), both shapely geometries in M['crs']. The counted rows are exactly those of the figures 'kept'.
    cols: the columns the cleaning used (columns_of(flagged, R)); None: found in the flagged file as the cleaning
    finds them. M['columns'] says which were read."""
    rule = rule_key(rule)
    if flagged.crs is None:
        flagged = flagged.set_crs(4326)
    P = prepare(flagged, cols)
    crs = flagged.crs if (flagged.crs is not None and not flagged.crs.is_geographic) else None
    XY = {}
    for s in ("kept", "raw"):
        pts = gpd.GeoSeries(shapely.points(P[s]["x"], P[s]["y"]), crs=P[s]["crs"])
        if crs is None:
            crs = pts.estimate_utm_crs()
        pm = pts.to_crs(crs)
        XY[s] = (pm.x.to_numpy(float), pm.y.to_numpy(float))
    polys = polygons.to_crs(crs)
    keep = P["keep"]
    geoms = list(polys.geometry)
    fps = {s: footprints(XY[s][0], XY[s][1], P["heading"], P[s]["len_ft"] * FT_M, P[s]["wid_ft"] * FT_M)
           for s in ("kept", "raw")}
    res, rows, detail = [], {}, {}
    lab = _labels(flagged, P["columns"])
    for name, g in zip(polys["name"], polys.geometry):
        shapely.prepare(g)
        rec = {"name": name, "area_ac": float(g.area / M2_PER_AC)}
        for s in ("kept", "raw"):
            base = keep if s == "kept" else np.ones(len(keep), bool)
            L, W = P[s]["len_ft"], P[s]["wid_ft"]
            full_ac = np.nan_to_num(L) * np.nan_to_num(W) / FT2_PER_AC
            if rule == "point":
                hit = base & shapely.contains_xy(g, XY[s][0], XY[s][1])
                area = full_ac
            elif rule == "full":
                gb = g.buffer(COVER_TOL_M)
                shapely.prepare(gb)
                cand = base & shapely.intersects(g, fps[s])
                hit = np.zeros(len(keep), bool)
                idx = np.flatnonzero(cand)
                hit[idx] = shapely.covers(gb, fps[s][idx])
                area = full_ac
            else:                                    # clip: the overlap of the footprint with the polygon
                cand = base & shapely.intersects(g, fps[s])
                idx = np.flatnonzero(cand)
                area = np.zeros(len(keep), float)
                inter = shapely.area(shapely.intersection(fps[s][idx], g)) / M2_PER_AC
                # the share of the footprint inside, applied to the area the file holds (distance x width)
                fa = shapely.area(fps[s][idx]) / M2_PER_AC
                share = np.where(fa > 0, inter / np.where(fa > 0, fa, 1.0), 1.0)
                area[idx] = share * full_ac[idx]
                hit = np.zeros(len(keep), bool)
                hit[idx] = (inter > 0) | (fa <= 0)    # a reading of no area counts when its point touches it
            removed = (hit & ~keep) if s == "raw" else None
            rec[s] = _figures(P[s]["yield"][hit], area[hit], P["moist"][hit], P["rem"], removed)
            if s == "kept":
                ii = np.flatnonzero(hit)
                rows[name] = (ii, area[ii], P["kept"]["yield"][ii])
                detail[name] = _detail(g, fps["kept"], XY["kept"], hit, area, full_ac, P, rule, lab, detail_margin_m)
        res.append(rec)
    return {"rule": rule, "rule_text": EDGE_RULES[rule], "crs": crs.to_string(), "position": P["position"],
            "yield_column": P["yield_column"], "columns": P["columns"], "polygons": res, "rows": rows,
            "readings": detail, "geoms": geoms, "n": int(len(flagged))}


def _detail(g, fps, xy, hit, area, full_ac, P, rule, lab, margin_m) -> dict:
    """The per-reading rows of one polygon (measure): the counted readings of the kept set with their share, area and
    bushels as the figures count them, and the other readings whose strip touches the polygon (or its margin), with
    why they are not counted."""
    gm = g.buffer(float(margin_m)) if margin_m and margin_m > 0 else g
    near = shapely.intersects(gm, fps) | hit
    idx = np.flatnonzero(near)
    fp = fps[idx]
    inter_g = shapely.intersection(fp, g)
    fa = shapely.area(fp) / M2_PER_AC
    inter = shapely.area(inter_g) / M2_PER_AC
    pin = shapely.contains_xy(g, xy[0][idx], xy[1][idx])
    share = np.where(fa > 0, inter / np.where(fa > 0, fa, 1.0), np.where(pin, 1.0, 0.0))
    counted = hit[idx]
    keep = P["keep"][idx]
    yv = P["kept"]["yield"][idx]
    a_c = np.where(counted, area[idx], 0.0)
    ok = counted & np.isfinite(yv) & np.isfinite(a_c)
    bu = np.where(ok, np.nan_to_num(yv) * a_c, 0.0)
    why = []
    for j in range(len(idx)):
        if not keep[j]:
            why.append("removed")
        elif counted[j]:
            why.append("no_area" if fa[j] <= 0 else ("clip" if rule == "clip" else
                                                     "full_in" if rule == "full" else "point_in"))
        elif rule == "full" and share[j] > 0:
            why.append("full_cross")
        elif rule == "point" and share[j] > 0:
            why.append("point_out")
        else:
            why.append("outside")
    part = np.array([None] * len(idx), dtype=object)
    for j in np.flatnonzero(counted):
        part[j] = inter_g[j] if rule == "clip" else fp[j]
    return {"idx": idx, "counted": counted, "why": why, "share": share, "full_ac": full_ac[idx], "area_ac": a_c,
            "yield": yv, "bu": bu, "removed_by": P["rem"][idx], "machine": lab["machine"][idx],
            "time": lab["time"][idx], "record": lab["order"][idx], "fp": fp, "part": part,
            "yield_column": P["yield_column"]}


def _n(v, d):
    return "-" if v is None or not np.isfinite(v) else f"{float(v):,.{d}f}"


def removed_by_hand(D: dict, j: int) -> bool:
    """A reading of a per-reading row (measure()['readings'][polygon], row j) removed by hand: its Rem_By is the step
    of the edits by hand (manual_edits.STEP, 'SM', Edit points), not an automatic step of the cleaning."""
    from engine.clean.manual_edits import STEP
    return D["why"][j] == "removed" and str(D["removed_by"][j] or "") == STEP


def reading_text(D: dict, j: int, polygon: str, rule: str) -> list:
    """The hover text of one per-reading row (measure()['readings'][polygon], row j) as plain lines: the reading
    (combine, time, record id), the yield used or why it is not used, its strip, what the rule did with it, the
    calculation and the polygon it counts in."""
    rule = rule_key(rule)
    head = " · ".join(x for x in (str(D["machine"][j]), str(D["time"][j]),
                                  (f"record {D['record'][j]}" if str(D["record"][j]) else "")) if x)
    out = [head or "reading"]
    full, sh, a, y, b = (float(D["full_ac"][j]), float(D["share"][j]), float(D["area_ac"][j]), float(D["yield"][j]),
                         float(D["bu"][j]))
    w = D["why"][j]
    if w == "removed":
        out.append("Removed by hand (Edit points): its yield is not used" if removed_by_hand(D, j) else
                   f"Removed by the cleaning ({D['removed_by'][j] or '?'}): its yield is not used")
    else:
        out.append(f"Yield used {_n(y, 2)} bu/ac (the clean file's: {D.get('yield_column') or OCED_COLUMNS['yield']}"
                   " x Swath_Scl)")
    out.append(f"Strip {full:.5f} ac (its distance x its width)")
    if w == "clip":
        out.append(f"Clip: {100 * sh:.0f} % inside: {a:.5f} of {full:.5f} ac counted"
                   + (f"; {100 * (1 - sh):.0f} % cut off: {max(full - a, 0.0):.5f} ac" if sh < 0.9995 else ""))
    elif w in ("full_in", "point_in"):
        out.append(("Whole footprint inside" if w == "full_in" else "Point inside") + f": counted whole, {a:.5f} ac")
    elif w == "full_cross":
        out.append(f"Crosses the line ({100 * sh:.0f} % inside): not counted (whole footprint inside only)")
    elif w == "point_out":
        out.append(f"Point outside ({100 * sh:.0f} % of the strip inside): not counted")
    elif w == "no_area":
        out.append("No width or no distance: counted with no area")
    elif w == "removed":
        out.append(f"{100 * sh:.0f} % of its strip inside: not counted")
    else:
        out.append("Outside the polygon: not counted")
    if D["counted"][j]:
        out.append(f"{_n(y, 2)} bu/ac x {a:.5f} ac = {b:.4f} bu, counted in {polygon}")
    return out


def polygon_sum_text(p: dict) -> str:
    """The sum of one polygon: total bu / acres counted = dry yield (the kept readings, the table's figures)."""
    k = p["kept"]
    return (f"{p['name']}: {k['readings']:,} readings, {_f(k['total_dry_bu'], 4)} bu / {_f(k['area_ac'], 5)} ac "
            f"= {_f(k['dry_yield_bu_ac'])} bu/ac")


def replay_part(M: dict, n_rows: int) -> dict:
    """The small area on the replay of the cleaning (engine/replay.py replay_payload(small_area=...)): the polygons
    (rings and a label point in WGS 84, the table's figures), the box to zoom to, and by_row: per row of the flagged
    file the polygon (1-based; 0 none) and the share of its strip counted (0.1 %), of the polygon where it counts most.
    From measure_all (0.3.8: M has ground_rows) the figures and shares are grain / ground's, the figure the small area
    leads with: every reading of the flagged file whose strip as logged has a part inside (kept, removed by the
    cleaning or by hand) with its share inside, and per polygon readings, grain_bu, ground_ac, ground_pct and
    dry_yield_bu_ac (grain / ground), the cleaned map average beside it as cleaned_bu_ac. From measure() (a small area
    of 0.3.6) the cleaned map average's counted readings and figures, as before."""
    from shapely.ops import polylabel
    crs = M["crs"]
    names = [p["name"] for p in M["polygons"]]
    poly_of = np.zeros(int(n_rows), np.int64)
    share_of = np.zeros(int(n_rows), np.int64)
    best = np.zeros(int(n_rows), float)
    ground = M.get("ground_rows") is not None
    for k, name in enumerate(names, start=1):
        if ground:
            D = M["ground_rows"].get(name)
            if not D:
                continue
            sh_all = np.asarray(D["share"], float)
            c = (np.asarray(D["touch"], bool) & (sh_all > 0)
                 & np.array([str(s_) == "flagged" for s_ in D["src"]], bool))
            ii, sh = np.asarray(D["row"], np.int64)[c], sh_all[c]
        else:
            D = (M.get("readings") or {}).get(name)
            if not D:
                continue
            c = np.asarray(D["counted"], bool)
            ii, sh = np.asarray(D["idx"])[c], np.asarray(D["share"], float)[c]
        better = sh > best[ii]
        poly_of[ii[better]], share_of[ii[better]] = k, np.round(1000 * sh[better]).astype(np.int64)
        best[ii[better]] = sh[better]
    out_p, x0, y0, x1, y1 = [], [], [], [], []
    G = gpd.GeoSeries(M["geoms"], crs=crs).to_crs(4326) if M.get("geoms") is not None else None
    for k, p in enumerate(M["polygons"]):
        rings, lab = [], None
        if G is not None:
            g = G.iloc[k]
            for part in getattr(g, "geoms", [g]):
                if part.geom_type != "Polygon":
                    continue
                for ring in [part.exterior, *part.interiors]:
                    rings.append([[round(float(a), 7), round(float(b), 7)] for a, b in ring.coords])
            try:
                big = max(getattr(g, "geoms", [g]), key=lambda q: q.area)
                pt = polylabel(big, tolerance=1e-7)
            except Exception:                         # noqa: BLE001 - a degenerate polygon: its surface point
                pt = g.representative_point()
            lab = [round(float(pt.x), 7), round(float(pt.y), 7)]
            b = g.bounds
            x0.append(b[0]), y0.append(b[1]), x1.append(b[2]), y1.append(b[3])
        if ground:
            Gp = p.get("ground") or {}
            figs = {f: Gp.get(f) for f in ("readings", "grain_bu", "ground_ac", "ground_pct", "dry_yield_bu_ac")}
            figs["cleaned_bu_ac"] = p["kept"].get("dry_yield_bu_ac")
        else:
            figs = {f: p["kept"].get(f) for f in ("readings", "area_ac", "total_dry_bu", "dry_yield_bu_ac")}
        out_p.append({"name": str(p["name"]), "rings": rings, "label": lab, **figs})
    bbox = [min(x0), min(y0), max(x1), max(y1)] if x0 else None
    return {"polygons": out_p, "bbox": bbox, "rule": M["rule"], "rule_text": M["rule_text"],
            "method": "ground" if ground else None, "by_row": {"poly": poly_of, "share": share_of}}


def table(M: dict) -> pd.DataFrame:
    """One row per polygon and set (kept: the cleaned map average under the edge rule; raw: the readings as
    imported), the CSV columns: the 0.3.6 columns, then (0.3.7) the method and its figure, grain / ground (ground_),
    SMS's query (sms_), the spread inside the polygon and the calibration range, on the 'kept' row of each polygon."""
    out = []
    for p in M["polygons"]:
        for s in ("kept", "raw"):
            f = p[s]
            row = {"polygon": p["name"], "set": s, "rule": M["rule"], **{k: f.get(k) for k in CSV_COLUMNS[3:12]},
                   "removed_by_cleaning": (p["raw"].get("removed_by_cleaning") if s == "raw" else None),
                   "removed_by_step": ("; ".join(f"{k} {v}" for k, v in
                                                 (p["raw"].get("removed_by_step") or {}).items())
                                       if s == "raw" else None)}
            G, Q = p.get("ground") or {}, p.get("sms") or {}
            if s == "kept" and G:
                sp, ca = G.get("spread") or {}, p.get("calibration") or {}
                row.update({"method": M.get("method"), "figure_bu_ac": p.get("figure"),
                            "ground_dry_yield_bu_ac": G.get("dry_yield_bu_ac"), "ground_grain_bu": G.get("grain_bu"),
                            "ground_ac": G.get("ground_ac"), "ground_pct": G.get("ground_pct"),
                            "ground_readings": G.get("readings"), "ground_moisture_pct": G.get("moisture_pct"),
                            "ground_removed_grain_bu": G.get("removed_grain_bu"),
                            "ground_below_min_pct": G.get("below_min_ground_pct"),
                            "ground_transient_pct": G.get("transient_ground_pct"),
                            "sms_readings": Q.get("readings"), "sms_area_ac": Q.get("area_ac"),
                            "sms_total_dry_bu": Q.get("total_dry_bu"), "sms_dry_yield_bu_ac": Q.get("dry_yield_bu_ac"),
                            "spread_lo_bu_ac": sp.get("lo"), "spread_hi_bu_ac": sp.get("hi"),
                            "spread_pct": sp.get("pct"), "calibration_cv_pct": ca.get("cv_pct"),
                            "calibration_lo_bu_ac": ca.get("lo"), "calibration_hi_bu_ac": ca.get("hi"),
                            "interior_m": M.get("interior_m")})
            out.append(row)
    return pd.DataFrame(out, columns=CSV_COLUMNS)


def _read_flagged(flagged_path: str) -> gpd.GeoDataFrame:
    src = flagged_path
    if src.lower().endswith(".zip"):
        src = "zip://" + os.path.abspath(src).replace("\\", "/")
    return gpd.read_file(src)


def _decoded_for(flagged_path, decoded, import_rec, R=None):
    """(decoded GeoDataFrame or None, the decoded file's path or None, the import record, a note or None): the
    decoded file given, else the one of the cleaning (find_decoded)."""
    path, IM = (decoded, import_rec) if decoded else (None, import_rec)
    if not path:
        p2, IM2 = find_decoded(flagged_path, R)
        path, IM = p2, (IM if IM is not None else IM2)
    elif IM is None:
        IM = find_decoded(flagged_path, R)[1]
    if not path:
        left = sum((IM or {}).get("left_out", {}).values()) if isinstance((IM or {}).get("left_out"), dict) else 0
        return None, None, IM, ("no decoded file of this harvest file was found: grain / ground is computed from the "
                                "flagged file only" + (f" (the {left:,} readings the import left out are not counted)"
                                                       if left else ""))
    D, err = decoded_values(path, IM)
    if D is None:
        return None, path, IM, (err or "the decoded file could not be read") + \
            ": grain / ground is computed from the flagged file only"
    return D, path, IM, None


def run(flagged_path: str, polygons_path: str, out_dir: str, tag: str, rule: str = DEFAULT_RULE, log=print,
        method: str = DEFAULT_METHOD, cv_pct=None, interior_m: float = 0.0, decoded: str | None = None,
        import_rec: dict | None = None, R: dict | None = None) -> dict:
    """Measure the polygons of polygons_path on the cleaning's flagged file and write <tag>_small_area.csv,
    <tag>_small_area.zip (the kept readings counted in the cleaned map average), <tag>_small_area_parts.zip (their
    counted parts) and <tag>_small_area_ground.zip (every reading's strip clipped by the line, as grain / ground counts
    it) into out_dir. method: the figure the record leads with (grain / ground by default; all three are always
    measured); cv_pct: the calibration CV (%) for the calibration range and the pair table; interior_m: metres off
    each end of the polygons along their long axis; decoded / import_rec: the decoded file of the harvest file and the
    import record (else found from the cleaning: R, or the cleaning JSON next to the flagged file). Returns the record
    (JSON-safe) kept as R['small_area']."""
    rule = rule_key(rule)
    method = method_key(method)
    fl = _read_flagged(flagged_path)
    polys, notes = read_polygons(polygons_path)
    log(f"small area: {len(polys)} polygon(s) of {os.path.basename(polygons_path)}, figure {METHODS[method]}, edge "
        f"rule of the cleaned map average {EDGE_RULES[rule]}")
    D, dpath, IM, dnote = _decoded_for(flagged_path, decoded, import_rec, R)
    # the columns the cleaning read (its record: R, else the cleaning JSON next to the flagged file)
    cols = columns_of(fl, R if isinstance(R, dict) else cleaning_record(flagged_path))
    M = measure_all(fl, polys, rule, method, decoded=D, cv_pct=cv_pct, interior_m=interior_m, cols=cols)
    CU = M["columns"]
    os.makedirs(out_dir, exist_ok=True)
    csv = os.path.join(out_dir, f"{tag}_small_area.csv")
    table(M).to_csv(csv, index=False, float_format="%.6f")
    # the point shapefile: the kept readings that count, as the flagged file holds them, + the polygon and the counts
    parts = []
    for name, (ii, area, yv) in M["rows"].items():
        if len(ii):
            Dd = M["readings"][name]
            c = np.asarray(Dd["counted"], bool)
            by_idx = dict(zip(np.asarray(Dd["idx"])[c].tolist(), zip(np.asarray(Dd["share"], float)[c].tolist(),
                                                                     np.asarray(Dd["bu"], float)[c].tolist())))
            sub = fl.iloc[ii].copy()
            sub["SA_Poly"] = str(name)[:80]
            sub["SA_Area_ac"] = area
            sub["SA_Yld_Dr"] = yv
            sub["SA_Share"] = [by_idx[int(i)][0] for i in ii]
            sub["SA_Bu"] = [by_idx[int(i)][1] for i in ii]
            parts.append(sub)
    shp_zip = None
    if parts:
        G = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=fl.crs)
        base = os.path.join(out_dir, f"{tag}_small_area")
        exts = (".shp", ".shx", ".dbf", ".prj", ".cpg")
        for e in exts:
            if os.path.exists(base + e):
                os.remove(base + e)
        G.to_file(base + ".shp", driver="ESRI Shapefile", encoding="utf-8")
        shp_zip = base + ".zip"
        with zipfile.ZipFile(shp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for e in exts:
                if os.path.exists(base + e):
                    z.write(base + e, os.path.basename(base + e))
                    os.remove(base + e)
    parts_zip = write_parts(M, out_dir, tag)
    ground_zip = write_ground(M, out_dir, tag)
    used = D is not None
    rec = {"file": os.path.basename(polygons_path), "rule": rule, "rule_text": EDGE_RULES[rule],
           "position": M["position"], "crs": M["crs"], "notes": notes + M["ground_notes"],
           "yield_rule": (f"kept: {kept_text(CU)} (as the clean file); without the "
                          f"cleaning: {raw_text(CU)} of every reading of the flagged file"),
           "method": method, "method_text": METHODS[method], "method_help": METHOD_HELP[method],
           "ground_rule": (f"grain = {CU['yield']} (as imported) x {_dist_text(CU)} x {_width_text(CU)} x the share "
                           "of the logged strip inside the line, over every reading touching the polygon (kept, "
                           "removed by the cleaning or by hand" + (", left out by the import" if used else "")
                           + "); ground = the area of the union of the clipped strips; the strips as logged "
                           "(X_log / Y_log), their heading turned from true north to grid north"),
           "decoded": {"used": used, "file": (os.path.basename(dpath) if dpath else None),
                       "added": int(M["decoded_added"]) if used else 0,
                       "note": dnote or (None if used else "grain / ground from the flagged file only")},
           "grid_heading": {"on": True, "convergence_deg": float(M["convergence_deg"])},
           "duplicates": int(M["duplicates"]), "interior_m": float(M["interior_m"]), "cv_pct": M["cv_pct"],
           "pairs": M["pairs"], "polygons": _json_polys(M["polygons"]),
           "files": {"csv": csv, "zip": shp_zip, "parts_zip": parts_zip, "ground_zip": ground_zip}}
    if not legacy_columns(CU):
        # a file cleaned under its own column names (an Operations Center export ...): the columns read, said in the
        # record (a file with OCED's names keeps the record of before, byte for byte)
        rec["columns"] = {k: CU.get(k) for k in ("yield", "distance_ft", "width_ft", "heading", "moisture",
                                                 "speed_mph", "duration_s", "harvester_width_ft")}
    # 0.4.0: the report's figures of the plots (small_area_figures), drawn from M once everything above is written;
    # a figure that cannot be drawn never stops the measure (the report then has the tables only)
    from engine.clean import small_area_figures as saf
    try:
        figs, finfo = saf.write_figures(fl, M, out_dir, tag, cols)
    except Exception as e:                           # noqa: BLE001 - the record stands without its figures
        saf.remove_figures(out_dir, tag)
        figs, finfo = {}, {}
        log(f"  WARNING: the small area's figures could not be drawn: {type(e).__name__}: {e}")
    if figs:                                         # flat keys: every value of rec['files'] stays a path
        rec["files"].update({f"fig_{k}": v for k, v in figs.items()})
        rec["figures"] = finfo
    if dnote:
        log("  " + dnote)
    for p in rec["polygons"]:
        log("  " + polygon_text(p))
    return rec


def _json_polys(polys: list) -> list:
    """The polygons of measure_all as JSON-safe dicts (numpy numbers to floats)."""
    def fix(v):
        if isinstance(v, dict):
            return {k: fix(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [fix(x) for x in v]
        if isinstance(v, (np.bool_,)):
            return bool(v)
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        return v
    return [fix(p) for p in polys]


def ground_frame(M: dict) -> gpd.GeoDataFrame | None:
    """Every reading touching a polygon as grain / ground counts it, one row per reading and polygon (WGS 84): the
    logged strip clipped by the line, with SA_Poly, SA_Src (flagged / decoded), SA_Row (its row in that file),
    SA_Status (kept / removed / hand / left_out), SA_Yld (dry bu/ac as imported), SA_Share, SA_ClipAc, SA_GrndAc (its
    part of the ground), SA_Grain (bu), SA_SMSin (1: counted by SMS's query). SA_Grain sums to the grain and SA_GrndAc
    to the ground of each polygon. None when no reading has an area inside."""
    out = []
    for name, D in (M.get("ground_rows") or {}).items():
        for j in range(len(D["idx"])):
            if not D["touch"][j] or D["part"][j] is None:
                continue
            out.append({"SA_Poly": str(name)[:80], "SA_Src": str(D["src"][j]), "SA_Row": int(D["row"][j]),
                        "SA_Status": str(D["status"][j]), "SA_Yld": float(D["yield"][j]),
                        "SA_Share": float(D["share"][j]), "SA_ClipAc": float(D["clip_ac"][j]),
                        "SA_GrndAc": float(D["ground_ac"][j]), "SA_Grain": float(D["grain"][j]),
                        "SA_SMSin": int(bool(D["sms_in"][j])), "geometry": D["part"][j]})
    if not out:
        return None
    return gpd.GeoDataFrame(out, geometry="geometry", crs=M["crs"]).to_crs(4326)


def write_ground(M: dict, out_dir: str, tag: str) -> str | None:
    """<tag>_small_area_ground.zip (ground_frame as a polygon shapefile), or None."""
    G = ground_frame(M)
    base = os.path.join(out_dir, f"{tag}_small_area_ground")
    exts = (".shp", ".shx", ".dbf", ".prj", ".cpg")
    for e in exts + (".zip",):
        if os.path.exists(base + e):
            os.remove(base + e)
    if G is None:
        return None
    G["geometry"] = G.geometry.apply(lambda q: q if q.geom_type in ("Polygon", "MultiPolygon") else q.buffer(0.0))
    G = G[~G.geometry.is_empty]
    if not len(G):
        return None
    G.to_file(base + ".shp", driver="ESRI Shapefile", encoding="utf-8")
    with zipfile.ZipFile(base + ".zip", "w", zipfile.ZIP_DEFLATED) as z:
        for e in exts:
            if os.path.exists(base + e):
                z.write(base + e, os.path.basename(base + e))
                os.remove(base + e)
    return base + ".zip"


def parts_frame(M: dict) -> gpd.GeoDataFrame | None:
    """The counted parts of the strips, one row per reading and polygon it counts in (WGS 84): SA_Poly, SA_Row (the
    row of the flagged file), SA_Share, SA_Area_ac, SA_Yld_Dr, SA_Bu, SA_Rule, SA_Why. SA_Bu sums to the table's total
    dry bu of each polygon. None when no reading counts."""
    out = []
    for name, D in (M.get("readings") or {}).items():
        c = np.flatnonzero(np.asarray(D["counted"], bool))
        for j in c:
            out.append({"SA_Poly": str(name)[:80], "SA_Row": int(D["idx"][j]), "SA_Share": float(D["share"][j]),
                        "SA_Area_ac": float(D["area_ac"][j]), "SA_Yld_Dr": float(D["yield"][j]),
                        "SA_Bu": float(D["bu"][j]), "SA_Rule": M["rule"], "SA_Why": WHY[D["why"][j]][:250],
                        "geometry": D["part"][j]})
    if not out:
        return None
    return gpd.GeoDataFrame(out, geometry="geometry", crs=M["crs"]).to_crs(4326)


def write_parts(M: dict, out_dir: str, tag: str) -> str | None:
    """<tag>_small_area_parts.zip (parts_frame as a polygon shapefile), or None when no reading counts."""
    G = parts_frame(M)
    base = os.path.join(out_dir, f"{tag}_small_area_parts")
    exts = (".shp", ".shx", ".dbf", ".prj", ".cpg")
    for e in exts + (".zip",):
        if os.path.exists(base + e):
            os.remove(base + e)
    if G is None:
        return None
    G = G[[c for c in G.columns if c != "geometry"] + ["geometry"]]
    G["geometry"] = G.geometry.apply(lambda q: q if q.geom_type in ("Polygon", "MultiPolygon") else q.buffer(0.0))
    G.to_file(base + ".shp", driver="ESRI Shapefile", encoding="utf-8")
    with zipfile.ZipFile(base + ".zip", "w", zipfile.ZIP_DEFLATED) as z:
        for e in exts:
            if os.path.exists(base + e):
                z.write(base + e, os.path.basename(base + e))
                os.remove(base + e)
    return base + ".zip"


def detail_of(flagged_path: str, polygons_path: str, rule: str = DEFAULT_RULE, margin_m: float = 10.0,
              method: str | None = None, decoded: str | None = None, interior_m: float = 0.0,
              cv_pct=None) -> dict:
    """measure() of a cleaning's flagged file (a .zip or a .shp) and a polygon file, with the per-reading rows of the
    readings within margin_m of the polygons: what the app's map of the small area draws. With method (0.3.7):
    measure_all, so the rows of grain / ground (ground_rows) are there too, the decoded file given or found."""
    fl = _read_flagged(flagged_path)
    polys, _ = read_polygons(polygons_path)
    R = cleaning_record(flagged_path)               # the columns the cleaning read, from its record
    cols = columns_of(fl, R)
    if method is None:
        return measure(fl, polys, rule, detail_margin_m=margin_m, cols=cols)
    D, _p, _im, _note = _decoded_for(flagged_path, decoded, None, R)
    return measure_all(fl, polys, rule, method, decoded=D, cv_pct=cv_pct, interior_m=interior_m,
                       detail_margin_m=margin_m, cols=cols)


def _f(v, d=2):
    return "-" if v is None else f"{float(v):,.{d}f}"


def polygon_text(p: dict) -> str:
    k, r = p["kept"], p["raw"]
    G, Q = p.get("ground"), p.get("sms")
    lead = ""
    if G:
        lead = (f"grain / ground {_f(G.get('grain_bu'))} bu / {_f(G.get('ground_ac'), 3)} ac = "
                f"{_f(G.get('dry_yield_bu_ac'))} bu/ac ({G.get('readings', 0):,} readings, ground "
                f"{_f(G.get('ground_pct'), 0)} % of the polygon)"
                + (f"; as SMS's query {Q.get('readings', 0):,} readings, {_f(Q.get('area_ac'), 3)} ac, "
                   f"{_f(Q.get('dry_yield_bu_ac'))} bu/ac" if Q else "") + "; cleaned map average: ")
    return (f"{p['name']} ({p['area_ac']:,.3f} ac): {lead}{k['readings']:,} readings, {_f(k['area_ac'], 3)} ac, "
            f"{_f(k['total_dry_bu'])} bu, {_f(k['dry_yield_bu_ac'])} bu/ac after the cleaning; without it "
            f"{r['readings']:,} readings, {_f(r['area_ac'], 3)} ac, {_f(r['total_dry_bu'])} bu, "
            f"{_f(r['dry_yield_bu_ac'])} bu/ac; the cleaning removed {r.get('removed_by_cleaning', 0):,}"
            + (" (" + ", ".join(f"{s} {n}" for s, n in (r.get("removed_by_step") or {}).items()) + ")"
               if r.get("removed_by_step") else ""))


def summary_text(rec: dict) -> str:
    """The line of the cleaning record / report."""
    return (f"small area cut after the cleaning: {len(rec['polygons'])} polygon(s) of {rec['file']}, figure "
            f"{method_text(rec)}, rule {rec['rule_text']}: " + "; ".join(polygon_text(p) for p in rec["polygons"]))


def plot_names_said(m, n) -> str:
    """The sentence of a plots figure's caption on the plot names it writes: m of the n plots' names fit inside their
    plot (None: not counted, as every name written)."""
    if m is None or m >= n:
        return "Each plot's name is written inside it."
    if m <= 0:
        return "No plot name fits its plot at this scale; the table and the bar chart name every plot."
    return (f"The names of {m:,} of the {n:,} plots are written inside them; the others are left out where they "
            "would overlap another name or not fit their plot at this scale (the table and the bar chart name "
            "every plot).")


def report_section(story, R, num) -> int:
    """The section 'Small area' of the cleaning report (engine/report/clean_report.make_report); returns num + 1."""
    from reportlab.platypus import Paragraph
    from engine.report import clean_report as cr
    X = R["small_area"]
    e_ = cr._e
    story.append(Paragraph(f"{num}. Small area (cut after the cleaning)", cr.H2))
    if X.get("method"):
        story.append(Paragraph(e_(
            f"Polygon file {X['file']}. The figure: {X.get('method_text')} ({X.get('method_help')}). Grain / ground: "
            f"{X.get('ground_rule')}. Beside it the cleaned map average (the 0.3.6 figure: the kept readings under the "
            f"edge rule {X['rule_text']}) and as SMS's query (the kept readings whose whole strip is inside, their "
            "grain / their own area)."
            + (f" The polygons lose {X['interior_m']:g} m off each end along their long axis (the ends of a pass read "
               "low, so the interior reads higher than the whole pass)." if X.get("interior_m") else "")
            + (f" {X['decoded']['note']}." if (X.get("decoded") or {}).get("note") else
               f" The readings the import left out read from {X['decoded'].get('file')}.")), cr.BODY))
        rows = [["Polygon", "Grain / ground", "Grain bu", "Ground ac", "Ground %", "Cleaned map", "SMS query",
                 "Spread", "Calibration"]]
        for p in X["polygons"]:
            G, Q = p.get("ground") or {}, p.get("sms") or {}
            sp, ca = G.get("spread") or {}, p.get("calibration") or {}
            rows.append([e_(str(p["name"])), _f(G.get("dry_yield_bu_ac")), _f(G.get("grain_bu")),
                         _f(G.get("ground_ac"), 3), _f(G.get("ground_pct")), _f(p["kept"].get("dry_yield_bu_ac")),
                         _f(Q.get("dry_yield_bu_ac")),
                         (f"+- {sp['pct']:.2f} %" if sp.get("pct") is not None else "-"),
                         (f"+- {ca['half']:.2f}" if ca.get("half") is not None else "-")])
        w = cr.TEXT_W / 9.0
        story.append(cr._table(rows, [w] * 9, small=True))
        story.append(Paragraph(e_(
            "bu/ac dry. Spread: half the 95 % bootstrap range of the polygon's figure under the yield's variation "
            f"along the passes, in % of the figure (moving-block bootstrap along each pass, blocks of {BLOCK_M:g} m, "
            f"{N_BOOT:,} draws, fixed seed); it leaves out the monitor's calibration error. "
            + (f"Calibration (95 %): +- 1.96 x CV {X['cv_pct']:g} % x the figure; it covers comparisons between "
               "polygons of the same combine and day; the absolute level also needs a scale level (grower's weight)."
               if X.get("cv_pct") else "No calibration CV given: no calibration range.")), cr.BODY))
        warn = [f"{p['name']}: {(p.get('ground') or {}).get('transient_ground_pct'):.0f} % of the ground is the "
                f"first or last {TRANSIENT_M:g} m of a pass (filling / emptying)"
                for p in X["polygons"] if (p.get("ground") or {}).get("transient_warning")]
        for line in warn + list(X.get("notes") or []):
            story.append(Paragraph(e_(line), cr.BODY))
        if X.get("pairs"):
            prow = [["Polygon", "minus", "Difference bu/ac", "+- (95 %)", "Beyond the range"]]
            for q in X["pairs"]:
                prow.append([e_(str(q["a"])), e_(str(q["b"])), _f(q["diff"]), _f(q["half"]),
                             "yes" if q["beyond"] else "no"])
            w5 = cr.TEXT_W / 5.0
            story.append(cr._table(prow, [w5] * 5, small=True))
        report_figures(story, X)
        story.append(Paragraph(e_("The cleaned map average in detail (the readings the cleaning kept, and the "
                                  "readings as imported):"), cr.BODY))
    else:
        story.append(Paragraph(e_(f"Polygon file {X['file']}; edge rule: {X['rule_text']}. Measured by OCED 0.3.6: "
                                  f"its figure is the {LEGACY_METHOD_TEXT}. The readings the whole-field cleaning "
                                  f"kept, counted in each polygon ({X['yield_rule']}; positions from "
                                  f"{X['position']}).") , cr.BODY))
    rows = [["Polygon", "Set", "Readings", "Acres", "Dry bu", "bu/ac", "Mean", "SD", "Removed"]]
    for p in X["polygons"]:
        for s, lab in (("kept", "cleaned"), ("raw", "as imported")):
            f = p[s]
            rows.append([e_(str(p["name"])), lab, f"{f['readings']:,}", _f(f["area_ac"], 3), _f(f["total_dry_bu"]),
                         _f(f["dry_yield_bu_ac"]), _f(f["mean_bu_ac"]), _f(f["sd_bu_ac"]),
                         (e_(", ".join(f"{k} {v}" for k, v in (f.get("removed_by_step") or {}).items()) or "0")
                          if s == "raw" else "")])
    w = cr.TEXT_W / 9.0
    story.append(cr._table(rows, [w] * 9, small=True))
    return num + 1


def report_figures(story, X: dict):
    """0.4.0: the small area's figures in its report section (small_area_figures: X['files']['fig_map'], 'fig_inside',
    'fig_bars_1' ... with X['figures']): the clean map with the plots, the readings inside the plots and the yield of
    every plot with its spread, each with its bold title and caption, kept together on a page. Nothing when the record
    has none (a small area measured before 0.4.0, or a figure that could not be drawn)."""
    from reportlab.platypus import KeepTogether, Paragraph
    from engine.report import clean_report as cr
    F = {k[len("fig_"):]: v for k, v in (X.get("files") or {}).items() if str(k).startswith("fig_")}
    I = X.get("figures") or {}
    if not F:
        return
    e_ = cr._e
    n = int(I.get("n_plots") or len(X.get("polygons") or []))
    scale = (f"Colours: the dry yield (bu/ac) on the report's scale, red below the clean map's mean "
             f"({_f(I.get('mean'))} bu/ac, yellow) and green above it, from {_f(I.get('lo'))} to {_f(I.get('hi'))} "
             "bu/ac (the 2nd to the 98th percentile of the clean map; beyond it the end colours).")

    def names_said(k):
        return plot_names_said(I.get(k), n)

    def block(path, title, caption, max_h):
        if path and os.path.exists(path):
            story.append(KeepTogether([Paragraph(title, cr.BODY), cr._image(path, cr.TEXT_W, max_h),
                                       Paragraph(e_(caption), cr.CAP)]))
    block(F.get("map"), "<b>The plots on the clean map</b>",
          f"The {I.get('n_kept', 0):,} readings the cleaning kept, each drawn as the strip it swept (distance x "
          "width, as the clean file holds them), with the outlines of the "
          f"{n:,} plots of {X.get('file', '')} in navy. {names_said('names_map')} {scale}", 4.6 * cr.inch)
    rem = [f"{I[k]:,} reading(s) {w}" for k, w in (("n_removed", "removed by the cleaning (orange edge)"),
                                                   ("n_hand", "removed by hand (purple edge)"),
                                                   ("n_left_out", "left out by the import (blue edge)")) if I.get(k)]
    block(F.get("inside"), "<b>The readings inside the plots</b>",
          f"The part of each reading's strip inside its plot, as grain / ground counts it ({I.get('n_parts', 0):,} "
          "parts; the strips as logged, clipped by the plot's line), coloured by the reading's dry yield as "
          "imported, the plots' outlines in navy"
          + (f"; among them the parts of {', '.join(rem)}" if rem else "") + f". {names_said('names_inside')} "
          f"{scale} The same colours as the map above: the same colour is the same yield.", 4.6 * cr.inch)
    bars = [F[k] for k in sorted((k for k in F if str(k).startswith("bars_")), key=lambda k: int(k.split("_")[1]))]
    for i, p in enumerate(bars):
        more = (f" Part {i + 1} of {len(bars)}: up to {I.get('per_row', 20)} plots a row." if len(bars) > 1 else
                f" Up to {I.get('per_row', 20)} plots a row." if n > int(I.get("per_row") or 20) else "")
        block(p, "<b>Yield of the plots</b>" + (f" ({i + 1} of {len(bars)})" if len(bars) > 1 else ""),
              "Each plot's yield, grain / ground (bu/ac dry; the value written over its bar, two decimals), in the "
              "table's order. The light blue error bar is the spread inside the plot: the 95 % bootstrap range of "
              f"the plot's figure under the yield's variation along the passes (moving-block bootstrap along each "
              f"pass, blocks of {BLOCK_M:g} m, {N_BOOT:,} draws); it leaves out the monitor's calibration error."
              + (f" {I['n_no_figure']:,} plot(s) without a reading inside: no bar." if I.get("n_no_figure") else "")
              + more, 7.0 * cr.inch)


# ================================================================================================================
# 0.3.7, section J: the small area's yield is grain / ground
# ================================================================================================================

def method_key(method) -> str:
    m = str(method or DEFAULT_METHOD).strip().lower()
    alias = {"grain": "ground", "grain/ground": "ground", "grain_ground": "ground", "clean": "cleaned",
             "map": "cleaned", "average": "cleaned", "query": "sms", "full": "sms"}
    m = alias.get(m, m)
    if m not in METHODS:
        raise ValueError(f"small area method {method!r}: use one of {', '.join(METHODS)}")
    return m


def method_text(rec: dict) -> str:
    """The name of the figure a small-area record leads with; a record of 0.3.6 (no method) is its cleaned map
    average."""
    m = rec.get("method") if isinstance(rec, dict) else None
    return METHODS.get(m, LEGACY_METHOD_TEXT) if m else LEGACY_METHOD_TEXT


def interior_polygons(polys: gpd.GeoDataFrame, metres: float, crs) -> tuple:
    """The polygons with `metres` taken off each end along their long axis (the long side of the minimum rotated
    rectangle), in `crs` (projected). Returns (polygons, notes); a polygon shorter than 2 x metres is left whole with a
    note."""
    P = polys.to_crs(crs).copy()
    notes, out = [], []
    for name, g in zip(P["name"], P.geometry):
        c = np.asarray(g.minimum_rotated_rectangle.exterior.coords)[:4]
        e = np.diff(np.vstack([c, c[:1]]), axis=0)
        k = int(np.argmax(np.hypot(e[:, 0], e[:, 1])))
        u = e[k] / max(float(np.hypot(*e[k])), 1e-12)
        v = np.array([-u[1], u[0]])
        o = np.asarray(g.centroid.coords[0])
        pts = np.vstack([np.asarray(q.exterior.coords) for q in getattr(g, "geoms", [g]) if q.geom_type == "Polygon"])
        s_ = (pts - o) @ u
        t_ = (pts - o) @ v
        s0, s1 = float(s_.min()) + metres, float(s_.max()) - metres
        if s1 <= s0:
            notes.append(f"{name}: shorter than 2 x {metres:g} m along its long axis: measured whole")
            out.append(g)
            continue
        t0, t1 = float(t_.min()) - 1.0, float(t_.max()) + 1.0
        band = shapely.Polygon([o + u * s0 + v * t0, o + u * s1 + v * t0, o + u * s1 + v * t1, o + u * s0 + v * t1])
        out.append(shapely.intersection(g, band))
    P["geometry"] = out
    return P, notes


def grid_convergence_deg(lon, lat, crs) -> np.ndarray:
    """The grid azimuth (deg, clockwise from grid north) of true north at each point, in the projected crs: a
    heading measured from true north is heading + this on the grid (the meridian convergence; about 2 deg on a
    field 2 to 3 deg of longitude from its UTM zone's central meridian)."""
    from pyproj import Transformer
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    out = np.zeros(len(lon))
    ok = np.isfinite(lon) & np.isfinite(lat)
    if not ok.any():
        return out
    T = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x0, y0 = T.transform(lon[ok], lat[ok])
    x1, y1 = T.transform(lon[ok], lat[ok] + 1e-4)
    out[ok] = np.degrees(np.arctan2(np.asarray(x1) - np.asarray(x0), np.asarray(y1) - np.asarray(y0)))
    return out


def _key_text(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, (int, np.integer)) or (isinstance(v, float) and float(v).is_integer()):
        return str(int(v))
    return str(v).strip()


def find_decoded(flagged_path, R: dict | None = None):
    """(decoded file, import record) of a cleaning: the import's file of every reading (its record's all_readings,
    found again by its name in the work's decoded/ folder when the record names it by its name only or the work was
    moved) and the import record (R['sms_import'] or R['settings']['sms_import']); R None: the cleaning JSON next to
    the flagged file (<tag>_flagged.zip -> <tag>_cleaning.json). (None, record) when no decoded file is reachable."""
    if R is None and flagged_path:
        R = cleaning_record(flagged_path)
    if not isinstance(R, dict):
        return None, None
    IM = R.get("sms_import") if isinstance(R.get("sms_import"), dict) else None
    if IM is None and isinstance(R.get("settings"), dict) and isinstance(R["settings"].get("sms_import"), dict):
        IM = R["settings"]["sms_import"]
    if not isinstance(IM, dict) or not IM.get("all_readings"):
        return None, IM
    p = str(IM["all_readings"])
    if os.path.isabs(p) and os.path.exists(p):
        return p, IM
    name = os.path.basename(p)
    d = (R.get("files") or {}).get("dir") or (os.path.dirname(os.path.abspath(str(flagged_path)))
                                              if flagged_path else None)
    if d:
        for up in (os.path.dirname(d), os.path.dirname(os.path.dirname(d))):
            q = os.path.join(up, "decoded", name)
            if os.path.exists(q):
                return q, IM
    return None, IM


def _passes(machine, dataset, order, x, y, heading, length_m) -> tuple:
    """(pass id, distance from the pass start to the reading's start, distance from the reading's end to the pass
    end), in metres: the readings of one combine in time order; a new pass at a change of machine or dataset, a
    heading change of more than PASS_TURN_DEG or a step longer than PASS_STEP[0] x the distance + PASS_STEP[1] m."""
    n = len(x)
    pid = np.zeros(n, np.int64)
    if n == 0:
        return pid, np.zeros(0), np.zeros(0)
    o = np.lexsort((order, machine))
    m, ds, xs, ys = machine[o], dataset[o], x[o], y[o]
    hd, L = np.nan_to_num(heading[o]), np.nan_to_num(length_m[o])
    new = np.ones(n, bool)
    if n > 1:
        dh = np.abs((hd[1:] - hd[:-1] + 180.0) % 360.0 - 180.0)
        step = np.hypot(xs[1:] - xs[:-1], ys[1:] - ys[:-1])
        new[1:] = ((m[1:] != m[:-1]) | (ds[1:] != ds[:-1]) | (dh > PASS_TURN_DEG)
                   | ~np.isfinite(step) | (step > PASS_STEP[0] * L[1:] + PASS_STEP[1]))
    ps = np.cumsum(new) - 1
    pid[o] = ps
    cum = pd.Series(L).groupby(ps).cumsum().to_numpy()
    tot = pd.Series(L).groupby(ps).transform("sum").to_numpy()
    start = np.zeros(n)
    rest = np.zeros(n)
    start[o] = cum - L
    rest[o] = tot - cum
    return pid, start, rest


def _time_order(times, records) -> np.ndarray:
    """A number per reading that orders them in time (the Time text parsed; else the record id; else the file
    order)."""
    n = len(times)
    tt = pd.to_datetime(pd.Series(list(times), dtype=object).replace({"": None}), errors="coerce", format="mixed")
    if tt.notna().any():
        v = tt.to_numpy(dtype="datetime64[ns]").astype(np.int64).astype(float)
        v[~tt.notna().to_numpy()] = np.inf
        return v
    rec = pd.to_numeric(pd.Series(list(records), dtype=object), errors="coerce").to_numpy(float)
    return np.where(np.isfinite(rec), rec, np.arange(n, dtype=float))


def _same_spot(lon_a, lat_a, lon_b, lat_b) -> bool:
    """True when two logged positions (WGS 84) are one: within SAME_SPOT_DEG in longitude and in latitude; a position
    missing on either side does not tell two readings apart (True), as the machine + time alone did before 0.4.0."""
    if not (math.isfinite(lon_a) and math.isfinite(lat_a) and math.isfinite(lon_b) and math.isfinite(lat_b)):
        return True
    return abs(lon_a - lon_b) <= SAME_SPOT_DEG and abs(lat_a - lat_b) <= SAME_SPOT_DEG


class _Spots:
    """The positions of a set of readings, found again by position: a reading at the same spot (_same_spot) as one of
    them is among the cells next to its own (cells of SAME_SPOT_DEG), so a machine + time holding many readings (a
    time column that holds the date only) is still read in one pass."""

    def __init__(self, lon, lat):
        self.lon, self.lat = lon, lat
        self.cells: dict = {}
        self.missing: list = []                       # readings without a position: at the same spot as any
        self.order: list = []
        self.rank: dict = {}

    @staticmethod
    def _cell(x, y):
        return math.floor(x / SAME_SPOT_DEG), math.floor(y / SAME_SPOT_DEG)

    def add(self, i):
        self.rank[i] = len(self.order)
        self.order.append(i)
        x, y = self.lon[i], self.lat[i]
        if math.isfinite(x) and math.isfinite(y):
            self.cells.setdefault(self._cell(x, y), []).append(i)
        else:
            self.missing.append(i)

    def first_at(self, x, y):
        """The first reading added (in the order added) at the same spot as (x, y), or None."""
        if not self.order:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return self.order[0]
        found = list(self.missing[:1])
        cx, cy = self._cell(x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for k in self.cells.get((cx + dx, cy + dy), ()):
                    if _same_spot(self.lon[k], self.lat[k], x, y):
                        found.append(k)
                        break
        return min(found, key=self.rank.get) if found else None


def _nearest_free(flon, flat, cand, dlon, dlat):
    """For each flagged reading (flon, flat; in order) the nearest decoded reading of cand not taken before (distances
    in degrees, the longitude scaled by the cosine of the latitude): a dict {flagged position in the list: decoded
    reading}; a flagged reading has none once every one is taken. Every distance for a few readings, else a k-d tree
    (a machine + time holding many readings)."""
    out = {}
    if not cand or not flon:
        return out
    c = math.cos(math.radians(next((v for v in flat if math.isfinite(v)), 0.0)))
    pts = np.array([[dlon[j] * c, dlat[j]] if math.isfinite(dlon[j]) and math.isfinite(dlat[j]) else [np.inf, np.inf]
                    for j in cand], float)
    free = np.ones(len(cand), bool)
    if len(cand) * len(flon) <= 250_000:                 # a few readings: every distance
        for q, (x, y) in enumerate(zip(flon, flat)):
            if not free.any():
                break
            if math.isfinite(x) and math.isfinite(y):
                d = np.hypot(pts[:, 0] - x * c, pts[:, 1] - y)
            else:
                d = np.full(len(cand), np.inf)
            d = np.where(free & np.isfinite(d), d, np.inf)
            k = int(np.argmin(d)) if np.isfinite(d).any() else int(np.flatnonzero(free)[0])
            free[k] = False
            out[q] = cand[k]
        return out
    from scipy.spatial import cKDTree
    ok = np.isfinite(pts).all(axis=1)
    tree = cKDTree(pts[ok]) if ok.any() else None
    back = np.flatnonzero(ok)
    for q, (x, y) in enumerate(zip(flon, flat)):
        if not free.any():
            break
        k = None
        if tree is not None and math.isfinite(x) and math.isfinite(y):
            n_ask = 8
            while k is None:
                n_ask = min(n_ask, len(back))
                _, ii = tree.query([x * c, y], k=n_ask)
                for t in np.atleast_1d(ii):
                    if t < len(back) and free[back[t]]:
                        k = int(back[t])
                        break
                if k is None and n_ask >= len(back):
                    break
                n_ask *= 4
        if k is None:
            k = int(np.flatnonzero(free)[0])
        free[k] = False
        out[q] = cand[k]
    return out


def _match_decoded(A: dict, decoded: gpd.GeoDataFrame, dm, dt) -> np.ndarray:
    """Per reading of the decoded file: True when it is not in the flagged file (A: its readings; dm / dt: the decoded
    readings' machine and time). A machine + time the flagged file does not hold: not in it. A machine + time held by
    one reading on each side: the same reading (as before 0.4.0). A machine + time held by several readings on either
    side (a point export whose times are whole seconds: two readings of one combine in one second): the readings told
    apart by their logged position (the flagged file's X_log / Y_log against the decoded file's point): a decoded
    reading at the position of a flagged one is in the flagged file; a flagged reading at no decoded position (its
    point moved, a flagged file without X_log / Y_log) takes the nearest decoded reading of its machine + time still
    unmatched; the decoded readings left are not in the flagged file."""
    have: dict = {}
    for i, k in enumerate(zip(A["machine"].tolist(), A["time"].tolist())):
        have.setdefault(k, []).append(i)
    keys = list(zip(dm.tolist(), dt.tolist()))
    new = np.array([k not in have for k in keys], bool)
    cnt: dict = {}
    for k in keys:
        cnt[k] = cnt.get(k, 0) + 1
    many = {k for k, c in cnt.items() if k in have and k[1] != "" and (c > 1 or len(have[k]) > 1)}
    if not many:
        return new
    dj = [j for j, k in enumerate(keys) if k in many]
    gl = gpd.GeoSeries(decoded.geometry.values[dj], crs=decoded.crs or "EPSG:4326").to_crs(4326)
    dlon = dict(zip(dj, gl.x.to_numpy(float).tolist()))
    dlat = dict(zip(dj, gl.y.to_numpy(float).tolist()))
    by: dict = {}
    for j in dj:
        by.setdefault(keys[j], []).append(j)
    lon, lat = A["lon"], A["lat"]
    for k, Dk in by.items():
        Fk = have[k]
        F = _Spots(lon, lat)
        for f in Fk:
            F.add(f)
        present, hit = set(), set()
        for j in Dk:
            f = F.first_at(dlon[j], dlat[j])
            if f is not None:
                present.add(j)
                hit.add(f)
        # a flagged reading at no decoded position (its point moved, no X_log / Y_log): the nearest one still free,
        # unless it is a copy of a flagged reading matched (the same spot)
        H = _Spots(lon, lat)
        for f in Fk:
            if f in hit:
                H.add(f)
        alone = []
        for f in Fk:
            if f not in hit and H.first_at(lon[f], lat[f]) is None:
                alone.append(f)
                H.add(f)
        if alone:
            rest = [j for j in Dk if j not in present]
            took = _nearest_free([lon[f] for f in alone], [lat[f] for f in alone], rest, dlon, dlat)
            present.update(took.values())
        for j in Dk:
            new[j] = j not in present
    return new


def _logged_twice(A: dict) -> tuple:
    """(dup, apart): dup True for a reading that repeats an earlier one of the same machine, time and logged position
    (_same_spot; the first kept); apart = the readings that share their machine and time with an earlier reading but
    not its position, each a reading of its own. Readings without a time are never one."""
    tm = pd.Series(list(A["time"])).astype(str)
    kk = pd.Series([f"{a}\x00{b}" for a, b in zip(A["machine"], A["time"])])
    cand = (kk.duplicated(keep="first") & (tm != "")).to_numpy()
    dup = cand.copy()
    if not cand.any():
        return dup, 0
    lon, lat = A["lon"], A["lat"]
    groups: dict = {}
    for i in np.flatnonzero((kk.duplicated(keep=False) & (tm != "")).to_numpy()).tolist():
        g = groups.get(kk.iat[i])
        if g is None:
            g = groups[kk.iat[i]] = _Spots(lon, lat)
        if g.first_at(lon[i], lat[i]) is None:
            dup[i] = False
            g.add(i)
        else:
            dup[i] = True
    return dup, int(cand.sum() - dup.sum())


def ground_readings(flagged: gpd.GeoDataFrame, crs, decoded: gpd.GeoDataFrame | None = None,
                    grid_heading: bool = True, cols: dict | None = None) -> dict:
    """Every reading of the harvest file for grain / ground, as logged: the flagged file's readings (kept, removed by
    the cleaning or by hand) and, with `decoded` (sms_import.all_import_values of the decoded file), the readings the
    import left out (not in the flagged file, matched by machine + time, and by the logged position too where one
    machine + time holds several readings: _match_decoded); one reading logged twice (the same machine, time and
    logged position: _logged_twice) counted once. Arrays
    in `crs`: x, y (the logged point), heading (deg on the grid: true north corrected by the meridian convergence when
    grid_heading), len_m, wid_m, full_ac (distance x width), yield (dry bu/ac as imported), moisture, src ('flagged' /
    'decoded'), row (in its file), keep, rem (Rem_By), step (the import's left-out step), machine, time, record,
    pass, from_start_m, to_end_m, fp (the strips); and notes, duplicates, decoded_added, convergence_deg (mean),
    yield_column (the flagged file's yield read). cols: the columns the cleaning used (columns_of; None: found in the
    flagged file as the cleaning finds them)."""
    P = prepare(flagged, cols)
    lab = _labels(flagged, P["columns"])
    n0 = len(flagged)
    pts = gpd.GeoSeries(shapely.points(P["raw"]["x"], P["raw"]["y"]), crs=P["raw"]["crs"])
    ll = pts.to_crs(4326)
    pm = pts.to_crs(crs)
    dc = P["columns"]
    dset = (np.array([_key_text(v) for v in flagged[dc["dataset"]].tolist()], dtype=object)
            if dc.get("dataset") in flagged.columns else np.full(n0, "", object))
    A = {"x": pm.x.to_numpy(float), "y": pm.y.to_numpy(float), "lon": ll.x.to_numpy(float),
         "lat": ll.y.to_numpy(float), "heading": np.asarray(P["heading"], float),
         "len_ft": np.asarray(P["raw"]["len_ft"], float), "wid_ft": np.asarray(P["raw"]["wid_ft"], float),
         "yield": np.asarray(P["raw"]["yield"], float), "moisture": np.asarray(P["moist"], float),
         "src": np.full(n0, "flagged", object), "row": np.arange(n0), "keep": np.asarray(P["keep"], bool),
         "rem": np.asarray(P["rem"], object), "step": np.full(n0, "", object),
         "machine": np.asarray(lab["machine"], object), "time": np.asarray(lab["time"], object),
         "record": np.asarray(lab["order"], object), "dataset": dset}
    notes = []
    added = 0
    if decoded is not None and len(decoded):
        if not any(str(t) for t in A["time"]):
            notes.append("the flagged file has no time column: the readings of the decoded file cannot be matched; "
                         "grain / ground from the flagged file only")
        else:
            dm, dt = decoded["machine"].astype(str).to_numpy(), decoded["time"].astype(str).to_numpy()
            new = _match_decoded(A, decoded, dm, dt)
            if new.any():
                D = decoded[new]
                gp = gpd.GeoSeries(D.geometry.values, crs=decoded.crs or "EPSG:4326")
                gx, gl = gp.to_crs(crs), gp.to_crs(4326)
                k = int(new.sum())
                ext = {"x": gx.x.to_numpy(float), "y": gx.y.to_numpy(float), "lon": gl.x.to_numpy(float),
                       "lat": gl.y.to_numpy(float), "heading": D["heading"].to_numpy(float),
                       "len_ft": D["distance_ft"].to_numpy(float), "wid_ft": D["width_ft"].to_numpy(float),
                       "yield": D["dry_bu_ac"].to_numpy(float), "moisture": D["moisture"].to_numpy(float),
                       "src": np.full(k, "decoded", object), "row": np.flatnonzero(new),
                       "keep": np.zeros(k, bool), "rem": np.full(k, "", object),
                       "step": np.array([s_ or "not in the flagged file" for s_ in D["step"].astype(str)], object),
                       "machine": dm[new].astype(object), "time": dt[new].astype(object),
                       "record": D["order"].astype(str).to_numpy().astype(object),
                       "dataset": D["dataset"].astype(str).to_numpy().astype(object)}
                for key in A:
                    A[key] = np.concatenate([A[key], ext[key]])
                added = k
    # one reading logged twice (or the same reading in two files): the same machine, time and logged position,
    # counted once; two readings of one machine and time at two positions (a point export whose times are whole
    # seconds) are two readings
    n = len(A["x"])
    dup, apart = np.zeros(n, bool), 0
    if any(str(t) for t in A["time"]):
        dup, apart = _logged_twice(A)
        if apart:
            notes.append(f"{apart:,} reading(s) share the machine and the time of another reading but not its logged "
                         "position (times in whole seconds): each counted as a reading of its own")
    if dup.any():
        # the words of before 0.4.0 where no two readings shared a machine and time at two positions (the record
        # of such a file stays byte for byte)
        notes.append(f"{int(dup.sum()):,} reading(s) logged twice (same machine"
                     + (", time and position" if apart else " and time") + "): counted once")
        for key in A:
            A[key] = A[key][~dup]
        n = len(A["x"])
    conv = grid_convergence_deg(A["lon"], A["lat"], crs) if grid_heading else np.zeros(n)
    A["heading_true"] = A["heading"].copy()
    A["heading"] = np.nan_to_num(A["heading"]) + conv
    A["len_m"], A["wid_m"] = A["len_ft"] * FT_M, A["wid_ft"] * FT_M
    A["full_ac"] = np.nan_to_num(A["len_ft"]) * np.nan_to_num(A["wid_ft"]) / FT2_PER_AC
    A["order"] = _time_order(A["time"], A["record"])
    A["pass"], A["from_start_m"], A["to_end_m"] = _passes(A["machine"].astype(str), A["dataset"].astype(str),
                                                          A["order"], A["x"], A["y"], A["heading"], A["len_m"])
    A["fp"] = footprints(A["x"], A["y"], A["heading"], A["len_m"], A["wid_m"])
    A.update(notes=notes, duplicates=int(dup.sum()), decoded_added=int(added),
             convergence_deg=(float(np.nanmean(conv)) if n else 0.0), n=n, yield_column=P["yield_column"])
    return A


def _ground_parts(clipped, order) -> np.ndarray:
    """The part of the ground each clipped strip adds (ac): in time order, the area of the strip not already covered
    by an earlier one (the parts sum to the area of their union: the overlaps counted once)."""
    n = len(clipped)
    parts = np.zeros(n)
    if not n:
        return parts
    o = np.argsort(order, kind="stable")
    rank = np.empty(n, np.int64)
    rank[o] = np.arange(n)
    tree = shapely.STRtree(clipped)
    for i in range(n):
        g = clipped[i]
        if g is None or g.is_empty or g.area <= 0:
            continue
        nb = [int(j) for j in tree.query(g, predicate="intersects") if rank[int(j)] < rank[i]]
        if nb:
            prev = shapely.union_all([clipped[j] for j in nb])
            parts[i] = shapely.area(shapely.difference(g, prev))
        else:
            parts[i] = g.area
    return parts / M2_PER_AC


def _spread(yv, a, pid, seg_m, ground, name):
    """'Spread inside the polygon': a moving-block bootstrap along each pass (blocks of about BLOCK_M m of
    consecutive readings, N_BOOT draws, a seed fixed by SEED and the polygon's name), statistic grain / ground in the
    ratio form: sum(y a) / sum(a) of the readings drawn x sum(a) / ground of the readings measured. Returns {lo, hi,
    pct (half the 95 % range, % of the figure), point, passes, draws, block_m, seed} or None (nothing with an area).
    It is the sampling range of the polygon's figure under the yield's variation along the passes; the monitor's
    calibration error is not in it (the calibration range is)."""
    import zlib
    yv, a, pid, seg_m = (np.asarray(v) for v in (yv, a, pid, seg_m))
    ok = (a > 0) & np.isfinite(yv)
    if not ok.any() or ground <= 0:
        return None
    yv, a, pid, seg_m = yv[ok].astype(float), a[ok].astype(float), pid[ok], seg_m[ok].astype(float)
    fac = float(a.sum()) / ground
    point = float((yv * a).sum() / a.sum()) * fac
    rng = np.random.default_rng(SEED ^ zlib.crc32(str(name).encode("utf-8")))
    num = np.zeros(N_BOOT)
    den = np.zeros(N_BOOT)
    ups = pd.unique(pid)
    for p_ in ups:
        ix = np.flatnonzero(pid == p_)
        nn = len(ix)
        med = float(np.median(seg_m[ix]))
        k = int(max(1, min(nn, round(BLOCK_M / max(med, 1e-6)))))
        nb = int(np.ceil(nn / k))
        st_ = rng.integers(0, nn - k + 1, (N_BOOT, nb))
        take = (st_[:, :, None] + np.arange(k)[None, None, :]).reshape(N_BOOT, -1)[:, :nn]
        num += (yv[ix] * a[ix])[take].sum(axis=1)
        den += a[ix][take].sum(axis=1)
    est = num / den * fac
    lo, hi = (float(v) for v in np.percentile(est, [2.5, 97.5]))
    return {"lo": lo, "hi": hi, "pct": (100.0 * (hi - lo) / 2.0 / point if point else None), "point": point,
            "passes": int(len(ups)), "draws": N_BOOT, "block_m": BLOCK_M, "seed": SEED}


def measure_ground(A: dict, g, name: str, sms_in=None, margin_m: float = 0.0) -> tuple:
    """Grain / ground of one polygon g (in the readings' crs) from ground_readings A: (figures, per-reading rows).
    Figures: readings (touching the polygon), readings_area (with an area inside), grain_bu, ground_ac,
    dry_yield_bu_ac (grain / ground), ground_pct (of the polygon), moisture_pct (grain-weighted), kept /
    removed_by_cleaning / removed_by_hand / import_left_out (readings), removed_grain_bu, left_out_grain_bu,
    below_min_ground_pct (the ground logged below the import's minimum), transient (readings in the first or last
    TRANSIENT_M m of a pass) and transient_ground_pct, transient_warning, no_yield, spread (_spread). Rows (the
    readings touching, and with margin_m those near): idx (in A), touch, share, full_ac, clip_ac, ground_ac (its part
    of the ground), yield, grain, status (kept / removed / hand / left_out), removed_by, step, machine, time, record,
    sms_in (counted by SMS's query), src, row, fp, part (the clipped strip), transient, len_ft, wid_ft."""
    from engine.clean.manual_edits import STEP as HAND
    from engine.clean.yield_clean import IMPORT_MIN_STEP
    fps = A["fp"]
    tree = shapely.STRtree(fps)
    gm = g.buffer(float(margin_m)) if margin_m and margin_m > 0 else g
    near = np.sort(np.asarray(tree.query(gm, predicate="intersects"), np.int64))
    m = len(near)
    touch = shapely.intersects(g, fps[near]) if m else np.zeros(0, bool)
    clipped = shapely.intersection(fps[near], g) if m else np.array([], object)
    fa = shapely.area(fps[near]) if m else np.zeros(0)
    share = np.where(touch & (fa > 0), shapely.area(clipped) / np.where(fa > 0, fa, 1.0), 0.0) if m else np.zeros(0)
    full_ac = A["full_ac"][near]
    clip_ac = share * full_ac
    yv = A["yield"][near]
    grain = np.where(np.isfinite(yv), yv, 0.0) * clip_ac
    areal = touch & (fa > 0) & (share > 0)
    cl = np.array([clipped[j] if areal[j] else None for j in range(m)], dtype=object)
    parts = np.zeros(m)
    ground = 0.0
    if areal.any():
        jj = np.flatnonzero(areal)
        parts[jj] = _ground_parts(np.asarray([cl[j] for j in jj], dtype=object), A["order"][near][jj])
        ground = float(shapely.area(shapely.union_all([cl[j] for j in jj])) / M2_PER_AC)
    T = touch
    keep, rem, src, step = A["keep"][near], A["rem"][near], A["src"][near], A["step"][near]
    hand = (src == "flagged") & ~keep & np.array([str(r) == HAND for r in rem], bool)
    auto = (src == "flagged") & ~keep & ~hand
    left = src == "decoded"
    trans = (A["from_start_m"][near] < TRANSIENT_M) | (A["to_end_m"][near] < TRANSIENT_M)
    gsum = float(grain[T].sum())
    mo = A["moisture"][near]
    mw = T & np.isfinite(mo) & (grain > 0)
    below = left & np.array([str(s_) == IMPORT_MIN_STEP for s_ in step], bool)
    poly_ac = float(g.area / M2_PER_AC)
    fig = {"readings": int(T.sum()), "readings_area": int(areal.sum()), "grain_bu": gsum, "ground_ac": ground,
           "dry_yield_bu_ac": (gsum / ground if ground > 0 else None),
           "ground_pct": (100.0 * ground / poly_ac if poly_ac > 0 else None),
           "moisture_pct": (float((mo[mw] * grain[mw]).sum() / grain[mw].sum()) if mw.any() else None),
           "kept": int((T & keep).sum()), "removed_by_cleaning": int((T & auto).sum()),
           "removed_by_hand": int((T & hand).sum()), "import_left_out": int((T & left).sum()),
           "removed_grain_bu": float(grain[T & (auto | hand)].sum()),
           "left_out_grain_bu": float(grain[T & left].sum()),
           "below_min_ground_pct": (100.0 * float(parts[T & below].sum()) / ground if ground > 0 else None),
           "transient": int((T & trans).sum()),
           "transient_ground_pct": (100.0 * float(parts[T & trans].sum()) / ground if ground > 0 else None),
           "no_yield": int((T & ~np.isfinite(yv)).sum())}
    fig["transient_warning"] = bool(fig["transient_ground_pct"] is not None
                                    and fig["transient_ground_pct"] > 100 * TRANSIENT_WARN)
    fig["spread"] = _spread(yv[T], clip_ac[T], A["pass"][near][T], A["len_m"][near][T], ground, name)
    status = np.where(left, "left_out", np.where(hand, "hand", np.where(auto, "removed", "kept"))).astype(object)
    sms_in = set(sms_in or ())
    sin = np.array([(src[j] == "flagged" and int(A["row"][near][j]) in sms_in) for j in range(m)], bool)
    rows = {"idx": near, "touch": T, "share": share, "full_ac": full_ac, "clip_ac": clip_ac, "ground_ac": parts,
            "yield": yv, "grain": grain, "status": status, "removed_by": rem, "step": step,
            "machine": A["machine"][near], "time": A["time"][near], "record": A["record"][near], "sms_in": sin,
            "src": src, "row": A["row"][near], "fp": fps[near], "part": cl, "transient": trans,
            "len_ft": A["len_ft"][near], "wid_ft": A["wid_ft"][near],
            "yield_column": A.get("yield_column") or OCED_COLUMNS["yield"]}
    return fig, rows


STATUS_TEXT = {"kept": "Kept by the cleaning",
               "removed": "Removed by the cleaning ({by}): its yield is not used in the cleaned map average; it is "
                          "counted in grain / ground",
               "hand": "Removed by hand (Edit points): its yield is not used in the cleaned map average; it is "
                       "counted in grain / ground",
               "left_out": "Left out by the import ({by}; read from the decoded file): counted in grain / ground"}


def ground_text(D: dict, j: int, polygon: str, cleaned: dict | None = None) -> list:
    """The hover text of one reading of the grain / ground rows (measure_ground's rows, row j): the reading, what the
    cleaning or the import did with it, its yield and strip as logged, the clip by the line, the grain counted, its
    part of the ground (after the overlaps), whether SMS's query counts it (its whole cleaned strip inside) and, from
    `cleaned` ({flagged row: (area counted, bu)} of the cleaned map average), what the cleaned map counted."""
    head = " · ".join(x for x in (str(D["machine"][j]), str(D["time"][j]),
                                  (f"record {D['record'][j]}" if str(D["record"][j]) else "")) if x)
    out = [head or "reading"]
    stt = str(D["status"][j])
    by = str(D["removed_by"][j] or "?") if stt == "removed" else str(D["step"][j] or "?")
    out.append(STATUS_TEXT[stt].format(by=by))
    y, full, sh, ca = float(D["yield"][j]), float(D["full_ac"][j]), float(D["share"][j]), float(D["clip_ac"][j])
    out.append(f"Yield {_n(y, 2)} bu/ac dry, as imported ({D.get('yield_column') or OCED_COLUMNS['yield']})")
    out.append(f"Strip as logged {_n(float(D['wid_ft'][j]), 1)} ft x {_n(float(D['len_ft'][j]), 1)} ft = "
               f"{full:.5f} ac")
    if not D["touch"][j]:
        out.append("Outside the polygon: not counted")
    elif full <= 0:
        out.append("No width or no distance: no area, no grain")
    elif sh >= 0.9995:
        out.append(f"Whole strip inside the line: {ca:.5f} ac")
    else:
        out.append(f"Clipped by the line: {100 * sh:.0f} % inside: {ca:.5f} of {full:.5f} ac")
    if D["touch"][j]:
        out.append(f"Grain counted {_n(y, 2)} bu/ac x {full:.5f} ac x {100 * sh:.1f} % = "
                   f"{float(D['grain'][j]):.4f} bu")
        ga = float(D["ground_ac"][j])
        out.append(f"Its part of the ground {ga:.5f} ac"
                   + (f" ({max(ca - ga, 0.0):.5f} ac already covered by earlier readings)" if ca - ga > 5e-7 else ""))
    if D["src"][j] == "flagged" and stt == "kept":
        out.append("SMS's query: whole strip inside: counted" if D["sms_in"][j] else
                   "SMS's query: its strip is not whole inside: not counted")
    else:
        out.append("SMS's query: not in the cleaned map: not counted")
    if cleaned is not None and D["src"][j] == "flagged" and stt == "kept":
        c = cleaned.get(int(D["row"][j]))
        out.append(f"Cleaned map average: {c[0]:.5f} ac, {c[1]:.4f} bu" if c else "Cleaned map average: not counted")
    if D["transient"][j] and D["touch"][j]:
        out.append(f"In the first or last {TRANSIENT_M:g} m of its pass (the elevator filling or emptying)")
    if D["touch"][j]:
        out.append(f"Polygon {polygon}")
    return out


def ground_sum_text(p: dict) -> str:
    G = p.get("ground") or {}
    return (f"{p['name']}: grain {_f(G.get('grain_bu'), 3)} bu / ground {_f(G.get('ground_ac'), 4)} ac = "
            f"{_f(G.get('dry_yield_bu_ac'))} bu/ac ({G.get('readings', 0):,} readings)")


HOVER_STATUS = {"kept": "kept by the cleaning", "removed": "removed by the cleaning ({by})",
                "hand": "removed by hand (Edit points)", "left_out": "left out by the import"}
HOVER_CLICK = "Click (tap) for the calculation"
HOVER_CLICK_SUMS = "Click (tap) for its sums"


def _hv(v) -> str:
    """A number of the hover as the maps' hover writes it (the app's fmt_value): two decimals, a value under 0.1
    with three significant digits (a reading's bushels), '-' for none."""
    if v is None or not np.isfinite(float(v)):
        return "-"
    a = abs(float(v))
    return f"{float(v):,.2f}" if a >= 0.1 or a == 0 else f"{float(v):.3g}"


def ground_hover_fields(D: dict, j: int, polygon: str) -> dict:
    """The SHORT hover of one reading of the grain / ground rows (measure_ground's rows, row j) as the fields of the
    maps' hover (0.4.0: the general map's box, '<b>label</b>: value', the yield above them as 'Dry yield: v'): st
    (what happened to the reading: 'Reading: st'), shl / sh (the share of its strip inside the polygon and the grain
    it adds: 'Inside P: 50.00 % of its strip · 0.0123 bu', or why it adds none), ck (the click). The whole
    calculation (ground_text) is the card a click on the reading shows."""
    stt = str(D["status"][j])
    full, sh = float(D["full_ac"][j]), float(D["share"][j])
    if not D["touch"][j]:
        shl, shv = f"Outside {polygon}", "not counted"
    elif full <= 0:
        shl, shv = f"In {polygon}", "no width or no distance, no area"
    else:
        shl, shv = f"Inside {polygon}", f"{100 * sh:.2f} % of its strip · {_hv(float(D['grain'][j]))} bu"
    return {"st": HOVER_STATUS[stt].format(by=str(D["removed_by"][j] or "?")), "shl": shl, "sh": shv,
            "ck": HOVER_CLICK}


def ground_hover_text(D: dict, j: int, polygon: str) -> list:
    """ground_hover_fields as the lines of plain text the hover shows (the yield first, as the maps' hover)."""
    F = ground_hover_fields(D, j, polygon)
    return [f"Dry yield: {_hv(float(D['yield'][j]))} bu/ac", f"Reading: {F['st']}", f"{F['shl']}: {F['sh']}",
            F["ck"]]


def ground_sum_fields(p: dict) -> dict:
    """The SHORT hover of a polygon's line as the fields of the maps' hover (under 'Plot <name>'): gg (grain /
    ground, bu/ac), nr (the readings it counts), ck (the click)."""
    G = p.get("ground") or {}
    return {"gg": f"{_f(G.get('dry_yield_bu_ac'))} bu/ac", "nr": f"{G.get('readings', 0):,}", "ck": HOVER_CLICK_SUMS}


def ground_sum_hover(p: dict) -> str:
    """ground_sum_fields as the lines of plain text the hover of a polygon's line shows."""
    F = ground_sum_fields(p)
    return "\n".join([f"Plot {p['name']}", f"Grain / ground: {F['gg']}", f"Readings: {F['nr']}", F["ck"]])


def figure_of(p: dict, method: str):
    """The figure (bu/ac) of one polygon under the method: grain / ground, the cleaned map average or SMS's query."""
    if method == "ground":
        return (p.get("ground") or {}).get("dry_yield_bu_ac")
    if method == "sms":
        return (p.get("sms") or {}).get("dry_yield_bu_ac")
    return p["kept"].get("dry_yield_bu_ac")


def pair_table(polys: list, method: str, cv_pct) -> list:
    """The differences between every pair of polygons (first minus second, bu/ac) with +- 1.96 x sqrt((CV y1)^2 +
    (CV y2)^2) when a CV is given: [{a, b, diff, half, beyond}]. Empty without a CV or with one polygon."""
    if not cv_pct or len(polys) < 2:
        return []
    cv = float(cv_pct) / 100.0
    out = []
    for i in range(len(polys)):
        for k in range(i + 1, len(polys)):
            y1, y2 = figure_of(polys[i], method), figure_of(polys[k], method)
            if y1 is None or y2 is None:
                continue
            half = 1.96 * math.hypot(cv * y1, cv * y2)
            out.append({"a": polys[i]["name"], "b": polys[k]["name"], "diff": y1 - y2, "half": half,
                        "beyond": bool(abs(y1 - y2) > half)})
    return out


def cv_value(cv_pct):
    """The calibration CV (%) given, or None (empty, 0 or not a number)."""
    try:
        v = float(cv_pct)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) and v > 0 else None


def measure_all(flagged: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, rule: str = DEFAULT_RULE,
                method: str = DEFAULT_METHOD, decoded: gpd.GeoDataFrame | None = None, cv_pct=None,
                interior_m: float = 0.0, grid_heading: bool = True, detail_margin_m: float = 0.0,
                cols: dict | None = None) -> dict:
    """The three figures of every polygon (section J): measure() under the edge rule (the cleaned map average, and the
    readings as imported), measure() under 'full' (SMS's query: the kept readings whose whole strip is inside) and
    grain / ground (measure_ground over ground_readings; with `decoded` also the readings the import left out). The
    polygons first lose interior_m off each end along their long axis when interior_m > 0. Adds to measure()'s dict:
    method, method_text, ground_rows {name: rows}, cleaned_rows {name: {flagged row: (ac, bu)}}, pairs, cv_pct,
    interior_m, ground_notes, duplicates, decoded_added, convergence_deg; per polygon 'ground', 'sms', 'figure' and
    'calibration'. cols: the columns the cleaning used (columns_of(flagged, R)); None: found in the flagged file as
    the cleaning finds them."""
    method = method_key(method)
    rule = rule_key(rule)
    if flagged.crs is None:
        flagged = flagged.set_crs(4326)
    cols = cols if cols is not None else columns_of(flagged)
    notes = []
    im = float(interior_m or 0.0)
    if im > 0:
        crs0 = (flagged.crs if not flagged.crs.is_geographic else
                gpd.GeoSeries(flagged.geometry.values, crs=flagged.crs).estimate_utm_crs())
        polygons, notes = interior_polygons(polygons, im, crs0)
    M = measure(flagged, polygons, rule, detail_margin_m=detail_margin_m, cols=cols)
    MS = M if rule == "full" else measure(flagged, polygons, "full", cols=cols)
    A = ground_readings(flagged, M["crs"], decoded=decoded, grid_heading=grid_heading, cols=cols)
    G_rows, C_rows = {}, {}
    cv = cv_value(cv_pct)
    for k, (p, g) in enumerate(zip(M["polygons"], M["geoms"])):
        ps = MS["polygons"][k]
        p["sms"] = {f: ps["kept"].get(f) for f in ("readings", "area_ac", "total_dry_bu", "dry_yield_bu_ac")}
        fig, rows = measure_ground(A, g, p["name"], sms_in=MS["rows"][p["name"]][0].tolist(),
                                   margin_m=detail_margin_m)
        p["ground"] = fig
        D = M["readings"][p["name"]]
        c = np.asarray(D["counted"], bool)
        C_rows[p["name"]] = dict(zip(np.asarray(D["idx"])[c].tolist(),
                                     zip(np.asarray(D["area_ac"], float)[c].tolist(),
                                         np.asarray(D["bu"], float)[c].tolist())))
        G_rows[p["name"]] = rows
        y = figure_of(p, method)
        p["figure"] = y
        p["calibration"] = ({"cv_pct": cv, "lo": y * (1 - 1.96 * cv / 100), "hi": y * (1 + 1.96 * cv / 100),
                             "half": 1.96 * cv / 100 * y} if (cv and y is not None) else None)
    M.update(method=method, method_text=METHODS[method], ground_rows=G_rows, cleaned_rows=C_rows,
             pairs=pair_table(M["polygons"], method, cv), cv_pct=cv, interior_m=im,
             ground_notes=notes + A["notes"], duplicates=A["duplicates"], decoded_added=A["decoded_added"],
             convergence_deg=A["convergence_deg"], grid_heading=bool(grid_heading))
    return M


def decoded_values(path, import_rec):
    """The decoded file's readings with what the import computed for them (sms_import.all_import_values), with the
    import's own settings (import_rec: the cleaning's sms_import record; None: the yields as the file gives them).
    (GeoDataFrame or None, note)."""
    if not path or not os.path.exists(str(path)):
        return None, "no decoded file"
    from engine import sms_import as si
    RS = (dict(import_rec.get("resolved") or {}, family=import_rec.get("family"),
               sources=import_rec.get("sources") or {}) if isinstance(import_rec, dict) and
          import_rec.get("resolved") else None)
    try:
        return si.all_import_values(str(path), RS), None
    except Exception as e:                               # noqa: BLE001 - grain / ground then from the flagged file
        return None, f"the decoded file {os.path.basename(str(path))} could not be read ({type(e).__name__}: {e})"
