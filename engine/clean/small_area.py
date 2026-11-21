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

It only reads the cleaning's flagged file; it writes <tag>_small_area.csv and <tag>_small_area.zip (a point shapefile:
the kept readings that count under the rule, with the polygon's name, the area counted and the yield used) and never
touches the clean, flagged or DIFM files.
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
               "min_bu_ac", "max_bu_ac", "sd_bu_ac", "moisture_mean_pct", "removed_by_cleaning", "removed_by_step"]
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


def prepare(flagged: gpd.GeoDataFrame) -> dict:
    """The arrays of both sets from the flagged file: the position of each set with its CRS (kept: the file's point,
    which S2 moved to the middle of the strip it kept when it narrowed the reading; raw: the logged point X_log /
    Y_log, which OCED writes in WGS 84 whatever the file's CRS, taken in the file's CRS only when its values cannot
    be longitudes / latitudes), heading, yield, length / width (ft), moisture, Keep, Rem_By."""
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
    ycol = _col(flagged, "Yld_Vol_Dr")
    if ycol is None:
        raise ValueError("small area: the flagged file has no Yld_Vol_Dr (dry yield) column")
    yraw = _num(flagged, ycol)
    scl = _num(flagged, _col(flagged, "Swath_Scl"), 1.0)
    scl = np.where(np.isfinite(scl), scl, 1.0)
    d_raw, w_raw = _num(flagged, _col(flagged, "Distance_f")), _num(flagged, _col(flagged, "Swth_Wdth_"))
    d_opt = _num(flagged, _col(flagged, "Dist_Opt")) if _col(flagged, "Dist_Opt") else d_raw.copy()
    w_opt = _num(flagged, _col(flagged, "Wdth_Opt")) if _col(flagged, "Wdth_Opt") else w_raw.copy()
    rem = (flagged["Rem_By"].astype(object).where(flagged["Rem_By"].notna(), "").astype(str).str.strip().to_numpy()
           if "Rem_By" in flagged.columns else np.full(len(flagged), "", object))
    return {"x": x, "y": y, "heading": _num(flagged, _col(flagged, "Track_deg_"), 0.0),
            "keep": np.where(np.isfinite(keep), keep, 0) == 1, "rem": rem,
            "moist": _num(flagged, _col(flagged, "Moisture__", "Moisture")),
            "kept": {"yield": yraw * scl, "len_ft": d_opt, "wid_ft": w_opt, "x": xk, "y": yk, "crs": fcrs},
            "raw": {"yield": yraw, "len_ft": d_raw, "wid_ft": w_raw, "x": x, "y": y, "crs": rcrs},
            "position": pos, "yield_column": ycol}


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


def measure(flagged: gpd.GeoDataFrame, polygons: gpd.GeoDataFrame, rule: str = DEFAULT_RULE) -> dict:
    """{'rule', 'crs', 'polygons': [{name, area_ac, kept: figures, raw: figures}], 'rows': {name: (index of the
    kept readings that count, area counted ac, yield used)}}."""
    rule = rule_key(rule)
    if flagged.crs is None:
        flagged = flagged.set_crs(4326)
    P = prepare(flagged)
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
    fps = {s: footprints(XY[s][0], XY[s][1], P["heading"], P[s]["len_ft"] * FT_M, P[s]["wid_ft"] * FT_M)
           for s in ("kept", "raw")}
    res, rows = [], {}
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
        res.append(rec)
    return {"rule": rule, "rule_text": EDGE_RULES[rule], "crs": crs.to_string(), "position": P["position"],
            "yield_column": P["yield_column"], "polygons": res, "rows": rows}


def table(M: dict) -> pd.DataFrame:
    """One row per polygon and set (kept / raw), the CSV columns."""
    out = []
    for p in M["polygons"]:
        for s in ("kept", "raw"):
            f = p[s]
            out.append({"polygon": p["name"], "set": s, "rule": M["rule"], **{k: f.get(k) for k in CSV_COLUMNS[3:12]},
                        "removed_by_cleaning": (p["raw"].get("removed_by_cleaning") if s == "raw" else None),
                        "removed_by_step": ("; ".join(f"{k} {v}" for k, v in
                                                      (p["raw"].get("removed_by_step") or {}).items())
                                            if s == "raw" else None)})
    return pd.DataFrame(out, columns=CSV_COLUMNS)


def run(flagged_path: str, polygons_path: str, out_dir: str, tag: str, rule: str = DEFAULT_RULE, log=print) -> dict:
    """Measure the polygons of polygons_path on the cleaning's flagged file and write <tag>_small_area.csv and
    <tag>_small_area.zip into out_dir. Returns the record (JSON-safe) kept as R['small_area']."""
    rule = rule_key(rule)
    src = flagged_path
    if src.lower().endswith(".zip"):
        src = "zip://" + os.path.abspath(src).replace("\\", "/")
    fl = gpd.read_file(src)
    polys, notes = read_polygons(polygons_path)
    log(f"small area: {len(polys)} polygon(s) of {os.path.basename(polygons_path)}, rule {EDGE_RULES[rule]}")
    M = measure(fl, polys, rule)
    os.makedirs(out_dir, exist_ok=True)
    csv = os.path.join(out_dir, f"{tag}_small_area.csv")
    table(M).to_csv(csv, index=False, float_format="%.6f")
    # the point shapefile: the kept readings that count, as the flagged file holds them, + the polygon and the counts
    parts = []
    for name, (ii, area, yv) in M["rows"].items():
        if len(ii):
            sub = fl.iloc[ii].copy()
            sub["SA_Poly"] = str(name)[:80]
            sub["SA_Area_ac"] = area
            sub["SA_Yld_Dr"] = yv
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
    rec = {"file": os.path.basename(polygons_path), "rule": rule, "rule_text": EDGE_RULES[rule],
           "position": M["position"], "crs": M["crs"], "notes": notes,
           "yield_rule": ("kept: Yld_Vol_Dr x Swath_Scl over Dist_Opt x Wdth_Opt (as the clean file); without the "
                          "cleaning: Yld_Vol_Dr over Distance_f x Swth_Wdth_ of every reading of the flagged file"),
           "polygons": M["polygons"], "files": {"csv": csv, "zip": shp_zip}}
    for p in M["polygons"]:
        log("  " + polygon_text(p))
    return rec


def _f(v, d=2):
    return "-" if v is None else f"{float(v):,.{d}f}"


def polygon_text(p: dict) -> str:
    k, r = p["kept"], p["raw"]
    return (f"{p['name']} ({p['area_ac']:,.3f} ac): {k['readings']:,} readings, {_f(k['area_ac'], 3)} ac, "
            f"{_f(k['total_dry_bu'])} bu, {_f(k['dry_yield_bu_ac'])} bu/ac after the cleaning; without it "
            f"{r['readings']:,} readings, {_f(r['area_ac'], 3)} ac, {_f(r['total_dry_bu'])} bu, "
            f"{_f(r['dry_yield_bu_ac'])} bu/ac; the cleaning removed {r.get('removed_by_cleaning', 0):,}"
            + (" (" + ", ".join(f"{s} {n}" for s, n in (r.get("removed_by_step") or {}).items()) + ")"
               if r.get("removed_by_step") else ""))


def summary_text(rec: dict) -> str:
    """The line of the cleaning record / report."""
    return (f"small area cut after the cleaning: {len(rec['polygons'])} polygon(s) of {rec['file']}, rule "
            f"{rec['rule_text']}: " + "; ".join(polygon_text(p) for p in rec["polygons"]))


def report_section(story, R, num) -> int:
    """The section 'Small area' of the cleaning report (engine/report/clean_report.make_report); returns num + 1."""
    from reportlab.platypus import Paragraph
    from engine.report import clean_report as cr
    X = R["small_area"]
    e_ = cr._e
    story.append(Paragraph(f"{num}. Small area (cut after the cleaning)", cr.H2))
    story.append(Paragraph(e_(f"Polygon file {X['file']}; edge rule: {X['rule_text']}. The readings the whole-field "
                              f"cleaning kept, counted in each polygon ({X['yield_rule']}; positions from "
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
