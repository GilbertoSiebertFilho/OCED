# -*- coding: utf-8 -*-
"""OCED — Olds College Extract Data: the data of combines, planters and sprayers -> maps of every attribute -> the
3-sigma cleaning (with the clip to the field boundary; for a harvest also the grower's data) -> clean point shapefiles
and reports.

    python -m streamlit run app/oced.py --server.port 8502      (or double-click run_oced.bat)

Four steps on one page:

  1 Machine data: upload the files or type a file or folder on this computer. Combines: a raw monitor dataset (a
    zipped Case IH / New Holland card, a John Deere JD-Data folder, the files of a GreenStar 3 card) lists its units
    (tasks / machines / loads), and the chosen units are extracted as ONE POINT SHAPEFILE PER FIELD, SEASON AND CROP
    (engine.run.decode on each group); a yield point export (or its .kml / .kmz) is used as it is. Planters and
    sprayers: the as-applied point export (a shapefile); any other point shapefile of a machine too. What a point
    file is (harvest, seeding, application, other points) is read from its columns (engine.clean.applied3s.
    detect_operation).
  2 Map and attributes: one button per attribute of the file colours the map (the strips the header swept over the
    satellite image, or the points); the legend, the statistics and the histogram of that attribute sit beside it;
    the attribute table and the first records below. The field boundary of the file, when given, is drawn on it.
  3 Cleaning. A harvest file: the SMS 3-sigma sequence of Ag Leader SMS Advanced (engine.run.clean, method
    sms3sigma, no combine factor): S0 import check, S1 Clip To Field Boundary, S2 Optimize Swath Widths, S3 speed,
    S4 moisture, S5 dry yield (mean +/- k SD on the points still alive, another yield pass while the SD falls by more
    than 25 %); the grower's data (total weight with its unit and basis, the grain moisture, the bushel weight)
    VALIDATE the yields (monitor total against the grower's on the same basis, L = grower / monitor, a verdict) or also
    ADJUST them (Yld_Level = the dry yield x L in the clean file). Any other file (planter, sprayer, other points):
    the same 3-sigma rule on the attributes chosen (engine.clean.applied3s: S0 import check with the minimum of the
    main attribute, S1 clip, one 3-sigma step per attribute, the speed first, the main one repeated while its SD
    falls). Each file keeps its own boundary (.zip / .shp / .geojson / .gpkg / .kml / .kmz; a file of several fields
    asks which one) and its own settings. One file or every file; the steps, the limits and the maps of the result.
  4 Clean shapefiles and reports: the clean shapefile of each file (the kept points with every attribute), all of
    them in one zip, the flagged points (every point with Keep and the step that removed it, Rem_By), the cleaning
    report (PDF) and the cleaning record (JSON).

Work folder: workspace/<YYYYmmdd-HHMMSS>_<name>/ (OCED_WORKSPACE moves it), with uploads/ or input/, decoded/ (the
extracted files), boundary/<name>/ (the boundary files given), clean/<name>/ (the cleaning outputs) and
clean_shapefiles/ (what step 4 hands out). Every value on the maps is a reading's own value: nothing is interpolated
or smoothed.
"""
import base64
import dataclasses
import datetime as dt
import hashlib
import html
import json
import os
import shutil
import sys
import threading
import zipfile

import numpy as np
import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def _drop_stale_engine() -> None:
    """An engine whose source files changed since it was imported (an update while the app runs) is dropped, so that
    the imports below read the new code."""
    eng = sys.modules.get("engine")
    if eng is None:
        return
    stamp, now = getattr(eng, "SOURCE_STAMP", None), getattr(eng, "source_stamp", None)
    try:
        stale = stamp is None or now is None or now() != stamp
    except OSError:                                      # pragma: no cover
        stale = False
    if stale:
        for name in [n for n in sys.modules if n == "engine" or n.startswith("engine.")]:
            sys.modules.pop(name, None)


@st.cache_resource(show_spinner=False)
def _engine_lock():
    return threading.RLock()


with _engine_lock():
    _drop_stale_engine()
    from engine import run as er  # noqa: E402
    from engine.clean import applied3s as a3  # noqa: E402
    from engine.clean import sms3sigma as sms  # noqa: E402
    from engine.clean import yield_clean as yc  # noqa: E402
    from engine.formats import common, detect  # noqa: E402
import brand  # noqa: E402

try:
    import pydeck as pdk
except ImportError:                                      # pragma: no cover
    pdk = None

NAME, VERSION, TAGLINE = brand.NAME, brand.VERSION, brand.TAGLINE
WORKSPACE = os.path.abspath(os.environ.get("OCED_WORKSPACE") or os.path.join(ROOT, "workspace"))
MAP_N = 60000                    # strips or points drawn on a map; above it a random sample of this size
FROM_MONITOR = "from the monitor"
PALETTE_CAT = ["#FFC20E", "#00E5FF", "#FF4FA3", "#76FF03", "#FF8F00", "#B388FF", "#FFFFFF", "#00B373", "#FF5252",
               "#90A4AE", "#1DE9B6", "#F4FF81"]
MAX_CATEGORIES = 40              # a text attribute with more distinct values is listed, not mapped

# the attributes OCED knows by name: (label, unit, colour map); "cat" = categories, "time" = time of the reading
STD_INFO = {c[0]: c for c in common.STANDARD_COLUMNS}
ATTR_INFO = {
    "Yld_Vol_Dr": ("Dry yield", "bu/ac", "RdYlGn"), "Yld_Vol_We": ("Wet yield", "bu/ac", "RdYlGn"),
    "Yld_Mass_D": ("Dry mass", "lb/ac", "RdYlGn"), "Yld_Mass_W": ("Wet mass", "lb/ac", "RdYlGn"),
    "Moisture__": ("Moisture", "%", "YlGnBu"), "Speed_mph_": ("Speed", "mph", "plasma"),
    "Swth_Wdth_": ("Swath width", "ft", "viridis"), "Distance_f": ("Distance", "ft", "viridis"),
    "Track_deg_": ("Heading", "deg", "twilight"), "Elevation_": ("Elevation", "ft", "terrain"),
    "Duration_s": ("Duration", "s", "viridis"), "Time": ("Time", "", "time"), "Obj__Id": ("Record", "", "viridis"),
    "Machine": ("Machine", "", "cat"), "Dataset": ("Dataset", "", "cat"), "Field": ("Field", "", "cat"),
    "Product": ("Product", "", "cat"), "Crop": ("Crop", "", "cat"), "Src_Fmt": ("Format", "", "cat"),
    "Wdth_Raw": ("Width as logged", "ft", "viridis"), "Swath_Scl": ("Swath scale (old / new area)", "", "viridis"),
    "Keep": ("Kept", "", "cat"), "Rem_By": ("Removed by step", "", "cat"),
    "Yld_Level": ("Dry yield adjusted to the grower's weight", "bu/ac", "RdYlGn"),
    "Yld_Lvl_Sy": ("Dry yield adjusted, symmetric shrink", "bu/ac", "RdYlGn"),
    "Yld_Dry_Sy": ("Dry yield, symmetric shrink", "bu/ac", "RdYlGn"), "Harv_Day": ("Harvest day", "", "cat"),
    "Session": ("Harvest session", "", "cat"), "In_AOI": ("Inside the boundary", "", "cat"),
    "Rt_Apd_Ct_": ("Applied rate (count)", "seeds/ac", "RdYlGn"), "Rt_Apd_Ms_": ("Applied rate (mass)", "lb/ac", "RdYlGn"),
    "Rt_Apd_Vol": ("Applied rate (volume)", "gal/ac", "RdYlGn"), "Rt_Tgt_Ct_": ("Target rate (count)", "seeds/ac", "RdYlGn"),
    "Rt_Tgt_Ms_": ("Target rate (mass)", "lb/ac", "RdYlGn"), "Rt_Tgt_Vol": ("Target rate (volume)", "gal/ac", "RdYlGn"),
}
LEVEL_COLUMNS = ("Yld_Level", "Yld_Lvl_Sy")      # what "adjust the yields" adds; "validate only" leaves them out
BOUNDARY_TYPES = ["zip", "shp", "shx", "dbf", "prj", "cpg", "geojson", "json", "gpkg", "kml", "kmz"]
OUTLINE_RGB = [0, 229, 255]                      # the field boundary on the satellite image (cyan)
TICKET_UNIT_LABEL = {"lb": "lb", "kg": "kg", "bu": "bu", "t": "t (1,000 kg)"}
GROWER_USE = {"validate": "Validate only", "adjust": "Validate and adjust the yields"}
# the same for the columns of a vendor export, by the key yield_clean.detect_columns gives them
DET_INFO = {"yield": ("Dry yield", "bu/ac", "RdYlGn"), "yield_wet": ("Wet yield", "bu/ac", "RdYlGn"),
            "moisture": ("Moisture", "%", "YlGnBu"), "speed_mph": ("Speed", "mph", "plasma"),
            "width_ft": ("Swath width", "ft", "viridis"), "distance_ft": ("Distance", "ft", "viridis"),
            "heading": ("Heading", "deg", "twilight"), "duration_s": ("Duration", "s", "viridis"),
            "wet_mass_lbac": ("Wet mass", "lb/ac", "RdYlGn"), "dataset": ("Dataset", "", "cat"),
            "machine": ("Machine", "", "cat"), "time": ("Time", "", "time"), "order": ("Record", "", "viridis")}
FIRST = ["Yld_Vol_Dr", "Yld_Vol_We", "Moisture__", "Speed_mph_", "Swth_Wdth_", "Distance_f", "Track_deg_",
         "Elevation_", "Time", "Duration_s", "Yld_Mass_W", "Yld_Mass_D", "Machine", "Dataset", "Field", "Product"]
DET_FIRST = ["yield", "yield_wet", "moisture", "speed_mph", "width_ft", "distance_ft", "heading", "time", "duration_s",
             "wet_mass_lbac", "machine", "dataset"]          # the same order for the columns of a vendor export
HIDDEN = {"Src_Fmt", "X_log", "Y_log"}          # never offered as a button (still in the attribute table)
STEP_COLORS = {"kept": "#00B373", "S0": "#90A4AE", "S1": "#B0BEC5", "S2": "#B388FF", "S3": "#00B4D8",
               "S4": "#1565C0", "S5": "#FF5252"}

st.set_page_config(page_title=NAME, page_icon=brand.page_icon(), layout="wide")
if os.path.exists(brand.LOGO_H):
    st.logo(brand.LOGO_H, icon_image=brand.LOGO_SHIELD if os.path.exists(brand.LOGO_SHIELD) else None, size="large")
brand.inject()
# the attribute buttons (st.pills in a keyed box): large, navy when chosen
st.html(f"""<style>
.stApp [class*="st-key-attr_box_"] {{ background: #F3F7FC; border: 1px solid #C9D8EC;
  border-left: 5px solid {brand.LIGHT_BLUE}; border-radius: 12px; padding: 0.7rem 1rem 0.8rem !important; }}
.stApp [class*="st-key-attr_box_"] [data-testid="stWidgetLabel"] p {{ font-weight: 700; font-size: 1.02rem;
  color: {brand.NAVY}; }}
.stApp [class*="st-key-attr_box_"] button[role="radio"] {{ min-height: 2.35rem; padding: 0.3rem 0.95rem;
  background: #FFFFFF; border: 1px solid #C9D8EC; }}
.stApp [class*="st-key-attr_box_"] button[role="radio"] p {{ font-weight: 600; color: #0B2A5B; }}
.stApp [class*="st-key-attr_box_"] button[role="radio"]:hover {{ background: #E8F1FB; border-color: {brand.LIGHT_BLUE}; }}
.stApp [class*="st-key-attr_box_"] button[role="radio"][aria-checked="true"] {{
  background: {brand.NAVY}; border-color: {brand.NAVY}; box-shadow: 0 2px 8px rgba(0,53,142,0.28); }}
.stApp [class*="st-key-attr_box_"] button[role="radio"][aria-checked="true"] p {{ color: #FFFFFF; }}
.stApp .st-key-run_go_2 [data-testid="stBaseButton-primary"] {{ min-height: 3.1rem; padding: 0.7rem 2rem;
  border-radius: 12px; font-size: 1.08rem; font-weight: 700; }}
.stApp [class*="st-key-field_box_"] {{ background: #FFFFFF; border: 1px solid #C9D8EC; border-left: 5px solid {brand.NAVY};
  border-radius: 12px; padding: 0.75rem 1.05rem 0.85rem !important; }}
.oced-verdict {{ border-radius: 10px; padding: 0.6rem 0.9rem; font-size: 0.95rem; border: 1px solid #C9D8EC; }}
.oced-legend {{ display: flex; align-items: center; gap: 0.6rem; margin: 0.35rem 0 0.2rem; font-size: 0.86rem;
  color: #1F2937; }}
.oced-bar {{ flex: 1; height: 14px; border-radius: 7px; border: 1px solid #C9D8EC; }}
</style>""")

ss = st.session_state
for k, v in {"workdir": None, "cands": None, "open_error": None, "open_exc": None, "open_request": None,
             "open_log": [], "units": {}, "datasets": {}, "cleaned": {}, "active": None, "boundary": {},
             "grower": {}, "a3set": {}, "smsset": None}.items():
    ss.setdefault(k, v)


# ------------------------------------------------------------------------------------------------ helpers
def key_of(s: str) -> str:
    return hashlib.md5(str(s).encode("utf-8")).hexdigest()[:8]


def mtime(p: str) -> float:
    return os.path.getmtime(p) if p and os.path.exists(p) else 0.0


def start_over():
    for k in ("cands", "open_error", "open_exc", "open_request", "active"):
        ss[k] = None
    ss.open_log, ss.units, ss.datasets, ss.cleaned, ss.boundary, ss.grower, ss.a3set = [], {}, {}, {}, {}, {}, {}
    ss.workdir = None
    for k in [k for k in ss if str(k).startswith(("cand_idx", "units_", "attr_", "path_in", "bnd_", "gw_", "a3_"))]:
        ss.pop(k, None)


def request_open(source):
    ss.open_request = source


def do_open(source):
    """source: ('upload', [UploadedFile]) or ('path', str). A new work folder; the content detected (engine.run)."""
    for k in ("cands", "open_error", "open_exc", "active"):
        ss[k] = None
    ss.open_log, ss.datasets, ss.cleaned, ss.boundary, ss.grower, ss.a3set = [], {}, {}, {}, {}, {}
    ss.pop("cand_idx", None)
    kind, val = source
    try:
        if kind == "upload":
            ss.workdir = er.new_workdir(WORKSPACE, os.path.splitext(val[0].name)[0])
            up = os.path.join(ss.workdir, "uploads")
            os.makedirs(up, exist_ok=True)
            for f in val:
                with open(os.path.join(up, os.path.basename(f.name)), "wb") as fh:
                    fh.write(f.getbuffer())
            paths = [up]
        else:
            p = val.strip().strip('"')
            if not p or not os.path.exists(p):
                raise ValueError(f"not found on this computer: {p or '(empty)'}")
            ss.workdir = er.new_workdir(WORKSPACE, os.path.splitext(os.path.basename(p.rstrip('\\/')))[0])
            paths = [p]
        ss.cands = er.open_input(paths, ss.workdir, log=ss.open_log.append)
    except ValueError as e:
        ss.open_error = str(e)
    except Exception as e:                               # shown with its traceback, never swallowed
        ss.open_error = f"Opening failed ({type(e).__name__}): {e}"
        ss.open_exc = e


@st.cache_data(max_entries=12, show_spinner="Reading the points ...")
def read_points(path: str, mt: float) -> pd.DataFrame:
    """Every point of a point shapefile with every attribute, plus lon / lat (WGS 84)."""
    import pyogrio
    g = pyogrio.read_dataframe(path)
    if g.crs is not None and not g.crs.equals("EPSG:4326"):
        g = g.to_crs("EPSG:4326")
    df = pd.DataFrame(g.drop(columns="geometry"))
    df["lon"], df["lat"] = g.geometry.x.to_numpy(float), g.geometry.y.to_numpy(float)
    return df


@st.cache_data(max_entries=12, show_spinner="Building the strips the header swept ...")
def strips_of(path: str, mt: float) -> pd.DataFrame:
    """The readings as the strips they swept (engine.run.preview_swaths, MAP_N at most), each with its file row."""
    try:
        return er.preview_swaths(path, None, n_max=MAP_N)
    except Exception:                                    # a preview problem never takes the page down: the points
        return pd.DataFrame()


def attributes(df: pd.DataFrame) -> list:
    """[(column, label, unit, kind)] of the attributes worth a button: the known ones first (FIRST), then the other
    numeric columns, then the text columns with few distinct values. kind: 'num' (with its colour map), 'cat' or
    'time'."""
    cols = [c for c in df.columns if c not in ("lon", "lat")]
    det = yc.detect_columns(cols)
    by_det = {v: k for k, v in det.items() if v}
    out = {}
    for c in cols:
        if c in HIDDEN:
            continue
        if c in ATTR_INFO:
            lab, unit, cmap = ATTR_INFO[c]
        elif c in by_det and by_det[c] in DET_INFO:
            lab, unit, cmap = DET_INFO[by_det[c]]
        else:
            num = pd.api.types.is_numeric_dtype(df[c])
            if num:
                lab, unit, cmap = c, "", "viridis"
            else:
                n = df[c].astype(str).nunique()
                if n > MAX_CATEGORIES or n < 1:
                    continue
                lab, unit, cmap = c, "", "cat"
        if cmap not in ("cat", "time") and not pd.api.types.is_numeric_dtype(df[c]):
            if pd.to_numeric(df[c], errors="coerce").notna().mean() < 0.5:
                continue                                 # a text column that is not numbers
        if cmap == "cat" and df[c].astype(str).nunique() > MAX_CATEGORIES:
            continue
        v = df[c]
        if cmap not in ("cat", "time") and not np.isfinite(pd.to_numeric(v, errors="coerce").to_numpy(float)).any():
            continue                                     # all empty
        out[c] = (c, lab, unit, cmap)
    known = [c for c in FIRST if c in out] + [det[k] for k in DET_FIRST if det.get(k) in out]
    known = list(dict.fromkeys(known))
    order = known + [c for c in out if c not in known]
    return [out[c] for c in order]


def values_of(df: pd.DataFrame, col: str, kind: str):
    """(numeric values, categories or None, time origin or None) of one attribute: numbers as they are; a time as
    minutes since the first reading; categories as their codes."""
    if kind == "cat":
        s = df[col].astype(str).replace({"": "(empty)", "nan": "(empty)", "None": "(empty)"})
        cats = s.value_counts().index.tolist()
        return s.map({c: i for i, c in enumerate(cats)}).to_numpy(float), cats, None
    if kind == "time":
        t = pd.to_datetime(df[col], errors="coerce")
        if t.notna().any():
            t0 = t.min()
            return ((t - t0).dt.total_seconds() / 60.0).to_numpy(float), None, t0
        return pd.to_numeric(df[col], errors="coerce").to_numpy(float), None, None
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float), None, None


def rgba_of(v, kind, cmap, lo, hi, cats) -> np.ndarray:
    """(n, 4) uint8 colours: categories from PALETTE_CAT; numbers through the colour map between lo and hi; no value
    grey."""
    import matplotlib
    n = len(v)
    out = np.zeros((n, 4), np.uint8)
    fin = np.isfinite(v)
    if kind == "cat":
        pal = np.array([[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)] for h in PALETTE_CAT], np.uint8)
        idx = np.where(fin, v, 0).astype(int) % len(pal)
        out[:, :3] = pal[idx]
    else:
        cm = matplotlib.colormaps["viridis" if cmap == "time" else cmap]
        t = np.clip((np.where(fin, v, lo) - lo) / (hi - lo if hi > lo else 1.0), 0, 1)
        out[:, :3] = (cm(t)[:, :3] * 255).astype(np.uint8)
    out[:, 3] = 220
    out[~fin] = [158, 158, 158, 150]
    return out


def fmt_value(x, unit="", kind="num", t0=None, cats=None) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    if kind == "cat" and cats is not None:
        return str(cats[int(x)])
    if kind == "time" and t0 is not None:
        return (t0 + pd.Timedelta(minutes=float(x))).strftime("%Y-%m-%d %H:%M")
    a = abs(x)
    s = f"{x:,.2f}" if a >= 0.1 or a == 0 else f"{x:.3g}"   # two decimals (64.35, not 64.3)
    return f"{s} {unit}".strip()


# satellite basemap: Esri World Imagery as a one-source MapLibre style sent as a data URL
SATELLITE_STYLE = {
    "version": 8,
    "sources": {"satellite": {
        "type": "raster", "tileSize": 256, "maxzoom": 19,
        "tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
        "attribution": "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community"}},
    "layers": [{"id": "satellite", "type": "raster", "source": "satellite"}]}
SATELLITE_STYLE_URL = "data:application/json;base64," + base64.b64encode(json.dumps(SATELLITE_STYLE).encode()).decode()

if pdk is not None:
    class _CompactDeck(pdk.Deck):
        """Compact JSON: 60,000 strips in about a third of pydeck's indented payload."""

        def to_json(self):
            from pydeck.bindings.json_tools import default_serialize
            return json.dumps(self, sort_keys=True, default=default_serialize, separators=(",", ":"))


def outline_layer(outline):
    """The field boundary as a cyan line over the strips (outline: [[[lon, lat], ...], ...], one ring per path)."""
    if pdk is None or not outline:
        return None
    # the width in metres, held between 2 and 4 pixels (a string such as width_units="pixels" would reach deck.gl
    # as a pydeck expression, not as the word)
    return pdk.Layer("PathLayer", data=pd.DataFrame({"path": outline}), get_path="path", get_color=OUTLINE_RGB,
                     get_width=1, width_min_pixels=2, width_max_pixels=4, pickable=False)


def deck(layers, lon, lat, height, tooltip=None, width=900):
    lo0, lo1 = float(np.nanmin(lon)), float(np.nanmax(lon))
    la0, la1 = float(np.nanmin(lat)), float(np.nanmax(lat))
    coslat = np.cos(np.radians((la0 + la1) / 2))
    z_w = np.log2(0.9 * width * 360.0 / (512.0 * max(lo1 - lo0, 1e-6)))
    z_h = np.log2(0.9 * height * 360.0 * coslat / (512.0 * max(la1 - la0, 1e-6)))
    view = pdk.ViewState(latitude=(la0 + la1) / 2, longitude=(lo0 + lo1) / 2,
                         zoom=float(np.clip(min(z_w, z_h), 9, 17)))
    st.pydeck_chart(_CompactDeck(layers=layers, initial_view_state=view, map_style=SATELLITE_STYLE_URL,
                                 tooltip=tooltip), height=height)


def legend(kind, cmap, lo, hi, unit, t0=None, cats=None, counts=None):
    """Under the map: the colour bar from lo to hi, or one chip per category with its points."""
    if kind == "cat":
        items = []
        for i, c in enumerate(cats[:MAX_CATEGORIES]):
            col = PALETTE_CAT[i % len(PALETTE_CAT)]
            n = int(counts.get(i, 0)) if counts is not None else None
            items.append(f'<span style="display:inline-flex;align-items:center;gap:6px;margin:2px 14px 2px 0;'
                         f'font-size:0.86rem"><span style="width:12px;height:12px;border-radius:50%;background:{col};'
                         f'border:1px solid #1F2937"></span><b>{html.escape(str(c))}</b>'
                         + (f" {n:,} points" if n is not None else "") + "</span>")
        st.html('<div style="display:flex;flex-wrap:wrap">' + "".join(items) + "</div>")
        return
    import matplotlib
    cm = matplotlib.colormaps["viridis" if cmap == "time" else cmap]
    stops = ", ".join(matplotlib.colors.to_hex(cm(x)) for x in np.linspace(0, 1, 11))
    st.html(f'<div class="oced-legend"><span>{html.escape(fmt_value(lo, unit, kind, t0))}</span>'
            f'<div class="oced-bar" style="background:linear-gradient(90deg,{stops})"></div>'
            f'<span>{html.escape(fmt_value(hi, unit, kind, t0))}</span></div>')


def stats_of(v: np.ndarray) -> dict:
    f = v[np.isfinite(v)]
    if not len(f):
        return {"n": int(len(v)), "valid": 0}
    m, sd = float(f.mean()), float(f.std(ddof=1)) if len(f) > 1 else 0.0
    return {"n": int(len(v)), "valid": int(len(f)), "min": float(f.min()), "p2": float(np.percentile(f, 2)),
            "mean": m, "median": float(np.median(f)), "p98": float(np.percentile(f, 98)), "max": float(f.max()),
            "sd": sd, "cv": (100 * sd / m if m else None)}


def attribute_table(df: pd.DataFrame) -> pd.DataFrame:
    """Every column of the file: what it is, its unit, how many points have a value, and its range or values."""
    rows = []
    det = yc.detect_columns([c for c in df.columns if c not in ("lon", "lat")])
    by_det = {v: k for k, v in det.items() if v}
    for c in df.columns:
        if c in ("lon", "lat"):
            continue
        meaning = (STD_INFO[c][3] if c in STD_INFO else
                   f"{DET_INFO[by_det[c]][0]} (recognised by the cleaning)" if c in by_det and by_det[c] in DET_INFO
                   else ATTR_INFO[c][0] if c in ATTR_INFO else "")
        unit = STD_INFO[c][2] if c in STD_INFO else (ATTR_INFO.get(c) or DET_INFO.get(by_det.get(c), ("", "")))[1]
        s = df[c]
        num = pd.to_numeric(s, errors="coerce") if not pd.api.types.is_numeric_dtype(s) else s
        if pd.api.types.is_numeric_dtype(s) or num.notna().mean() > 0.9:
            f = num[np.isfinite(num.astype(float))]
            ints = bool(len(f)) and bool((f.astype(float) % 1 == 0).all())   # ids, counts: no decimals
            n2 = (lambda x: f"{x:,.0f}") if ints else (lambda x: f"{x:,.2f}" if abs(x) >= 0.1 or x == 0 else f"{x:.3g}")
            rng = (f"{n2(f.min())} … {n2(f.max())}" if len(f) else "—")
            mean = f"{f.mean():,.2f}" if len(f) else "—"
            valid = int(len(f))
        else:
            vals = s.astype(str)
            vals = vals[~vals.isin(["", "nan", "None"])]
            u = vals.unique()
            rng = ", ".join(map(str, u[:4])) + (f" … ({len(u):,} values)" if len(u) > 4 else "")
            mean, valid = "", int(len(vals))
        rows.append({"attribute": c, "meaning": meaning, "unit": unit, "points with a value": valid,
                     "range / values": rng, "mean": mean})
    return pd.DataFrame(rows)


def explorer(shp: str, key: str, title: str = "", height: int = 520, default: str | None = None, outline=None):
    """The map of a point file coloured by the attribute chosen on the buttons, with its legend, statistics and
    histogram beside it, and the attribute table and the first records below. outline: the field boundary (rings of
    [lon, lat]) drawn over the strips."""
    if not shp or not os.path.exists(shp):
        st.error("The file is no longer on disk.", icon=":material/error:")
        return
    df = read_points(shp, mtime(shp))
    attrs = attributes(df)
    if not attrs:
        st.warning("This file holds no attribute to map.", icon=":material/warning:")
        return
    names = [a[0] for a in attrs]
    info = {a[0]: a for a in attrs}
    akey = f"attr_{key}"
    if ss.get(akey) not in names:
        ss[akey] = default if default in names else names[0]
    with st.container(key=f"attr_box_{key}"):
        pick = st.pills("Attribute on the map", names, selection_mode="single", key=akey,
                        format_func=lambda c: info[c][1] + (f" ({info[c][2]})" if info[c][2] else ""))
    col = pick or names[0]
    _, label, unit, cmap = info[col]
    kind = "cat" if cmap == "cat" else "time" if cmap == "time" else "num"
    v, cats, t0 = values_of(df, col, kind)
    S = stats_of(v) if kind != "cat" else None
    lo, hi = ((S["p2"], S["p98"]) if (S and S.get("valid")) else (0.0, max(len(cats or []) - 1, 1)))
    if kind == "num" and S and S.get("valid") and hi <= lo:
        lo, hi = S["min"], S["max"]
    c_map, c_side = st.columns([2.6, 1], gap="medium")
    with c_map:
        draw = st.segmented_control("Draw the readings as", ["strips", "points"], default="strips", required=True,
                                    key=f"draw_{key}", format_func={"strips": "Strips the header swept",
                                                                    "points": "Points"}.get)
        pv = strips_of(shp, mtime(shp)) if draw == "strips" else pd.DataFrame()
        if draw == "strips" and ("polygon" not in pv or "row" not in pv):
            st.caption("The strips cannot be built for this file (no heading, width or distance): points instead.")
            pv = pd.DataFrame()
        if pv.empty:
            rows = np.flatnonzero(np.isfinite(df["lon"].to_numpy()) & np.isfinite(df["lat"].to_numpy()))
            if len(rows) > MAP_N:
                rows = np.sort(np.random.default_rng(0).choice(rows, MAP_N, replace=False))
            pv = pd.DataFrame({"lon": df["lon"].to_numpy()[rows], "lat": df["lat"].to_numpy()[rows], "row": rows})
        rows = pv["row"].to_numpy(int)
        vr = v[rows]
        rgba = rgba_of(vr, kind, cmap, lo, hi, cats)
        txt = [fmt_value(x, unit, kind, t0, cats) for x in vr]
        if pdk is None:
            st.map(pd.DataFrame({"lat": pv["lat"], "lon": pv["lon"]}), height=height)
        else:
            layers = []
            has = pv["polygon"].notna().to_numpy() if "polygon" in pv else np.zeros(len(pv), bool)
            if has.any():
                layers.append(pdk.Layer("PolygonLayer", data=pd.DataFrame(
                    {"polygon": pv["polygon"][has].tolist(), "rgb": rgba[has].tolist(),
                     "v": [t for t, h in zip(txt, has) if h]}), get_polygon="polygon", get_fill_color="rgb",
                    filled=True, stroked=False, pickable=True))
            if (~has).any():
                layers.append(pdk.Layer("ScatterplotLayer", data=pd.DataFrame(
                    {"lon": pv["lon"].to_numpy()[~has], "lat": pv["lat"].to_numpy()[~has],
                     "rgb": rgba[~has].tolist(), "v": [t for t, h in zip(txt, has) if not h]}),
                    get_position=["lon", "lat"], get_fill_color="rgb", get_radius=2, radius_min_pixels=1.5,
                    radius_max_pixels=6, pickable=True))
            ol = outline_layer(outline)
            if ol is not None:
                layers.append(ol)
            deck(layers, pv["lon"].to_numpy(), pv["lat"].to_numpy(), height,
                 tooltip={"html": f"<b>{html.escape(label)}</b>: {{v}}",
                          "style": {"backgroundColor": "#00358E", "color": "white", "fontSize": "12px"}})
        counts = pd.Series(v[np.isfinite(v)].astype(int)).value_counts().to_dict() if kind == "cat" else None
        legend(kind, cmap, lo, hi, unit, t0, cats, counts)
        st.caption((f"All {len(df):,} readings" if len(pv) >= len(df) else
                    f"A random {len(pv):,} of the {len(df):,} readings")
                   + (" as the strips their header swept" if "polygon" in pv else " as points")
                   + f", coloured by {label}" + (" (2nd to 98th percentile; beyond it the end colours)"
                                                 if kind != "cat" else "")
                   + ". Point at a strip to read its value. Nothing is interpolated or smoothed."
                   + (" The cyan line is the field boundary." if outline else ""))
    with c_side:
        st.markdown(f"**{label}**" + (f" · {unit}" if unit else "") + f"  \n`{col}`")
        if kind == "cat":
            vc = pd.Series(df[col].astype(str).replace({"": "(empty)", "nan": "(empty)"})).value_counts()
            st.dataframe(pd.DataFrame({"value": vc.index, "points": vc.values,
                                       "share (%)": 100 * vc.values / max(len(df), 1)}), hide_index=True,
                         height=min(36 * (len(vc) + 1) + 3, 420),
                         column_config={"share (%)": st.column_config.NumberColumn(format="%.2f")})
        elif S and S.get("valid"):
            rows_ = [("points with a value", f"{S['valid']:,} of {S['n']:,}"),
                     ("minimum", fmt_value(S["min"], unit, kind, t0)), ("2nd percentile", fmt_value(S["p2"], unit, kind, t0)),
                     ("mean", fmt_value(S["mean"], unit, kind, t0)), ("median", fmt_value(S["median"], unit, kind, t0)),
                     ("98th percentile", fmt_value(S["p98"], unit, kind, t0)), ("maximum", fmt_value(S["max"], unit, kind, t0))]
            if kind == "num":
                rows_ += [("SD", fmt_value(S["sd"], unit)), ("CV", f"{S['cv']:.2f} %" if S.get("cv") else "—")]
            st.dataframe(pd.DataFrame(rows_, columns=["statistic", "value"]), hide_index=True,
                         height=36 * (len(rows_) + 1) + 3)
            f = v[np.isfinite(v)]
            if len(f) > 1 and kind == "num" and S["p98"] > S["p2"]:
                import altair as alt
                pad = 0.25 * (S["p98"] - S["p2"])
                h, e = np.histogram(np.clip(f, S["p2"] - pad, S["p98"] + pad), bins=30)
                hist = pd.DataFrame({"from": e[:-1], "to": e[1:], "points": h})
                ch = (alt.Chart(hist, height=210).mark_bar(color=brand.NAVY)
                      .encode(x=alt.X("from:Q", bin="binned", title=label + (f" ({unit})" if unit else ""),
                                      axis=alt.Axis(format=",.4~r", tickCount=6)),
                              x2="to:Q", y=alt.Y("points:Q", title="points"),
                              tooltip=[alt.Tooltip("from:Q", format=".3~g"), alt.Tooltip("to:Q", format=".3~g"),
                                       "points:Q"]))
                st.altair_chart(ch, width="stretch")
                st.caption("Values beyond the scale are counted in the end bars.")
        else:
            st.caption("No point has a value.")
    with st.expander(f"The attributes of this file ({len(df.columns) - 2} columns)", icon=":material/table_view:"):
        st.dataframe(attribute_table(df), hide_index=True,
                     column_config={"points with a value": st.column_config.NumberColumn(format="%d")})
    with st.expander("The first 1,000 records", icon=":material/list:"):
        st.dataframe(df.drop(columns=["lon", "lat"]).head(1000), hide_index=True)


def zip_shapefile(shp: str, zpath: str, stem: str | None = None) -> str:
    """The .shp / .shx / .dbf / .prj / .cpg of shp in one zip, renamed to `stem` when given."""
    base = os.path.splitext(shp)[0]
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for e in er.SHP_EXTS:
            if os.path.exists(base + e):
                z.write(base + e, (stem or os.path.basename(base)) + e)
    return zpath


def download(label, path, mime, key, primary=False, icon=":material/download:"):
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            st.download_button(label, fh.read(), file_name=os.path.basename(path), mime=mime, key=key,
                               type="primary" if primary else "secondary", icon=icon)


# ------------------------------------------------------------------------------------------------ field boundary
def _outline_of(geom) -> list:
    """The rings of a (Multi)Polygon in WGS 84 as [[[lon, lat], ...], ...] (exteriors and holes)."""
    polys = list(getattr(geom, "geoms", [geom]))
    out = []
    for p in polys:
        if getattr(p, "geom_type", "") != "Polygon":
            continue
        for ring in [p.exterior, *p.interiors]:
            out.append([[round(float(x), 7), round(float(y), 7)] for x, y in ring.coords])
    return out


def load_boundary(tag: str, source, feature=None) -> dict:
    """A boundary file for the extracted file `tag`: source ('upload', [UploadedFile]) or ('path', str), or the
    path of a boundary already loaded (a new choice of field). The uploads go to boundary/<tag>/ in the work folder.
    Returns {path, name, n_polygons, area_ac, needs_choice, fields, feature, is_plan, warnings, outline}; raises
    ValueError when the file is not a polygon file OCED can read."""
    kind, val = source
    if kind == "upload":
        d = os.path.join(ss.workdir, "boundary", tag)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        for f in val:
            with open(os.path.join(d, os.path.basename(f.name)), "wb") as fh:
                fh.write(f.getbuffer())
        names = [os.path.basename(f.name) for f in val]
        main = ([n for n in names if n.lower().endswith(".shp")] or
                [n for n in names if os.path.splitext(n)[1].lower() in er.AOI_EXTS])
        if not main:
            raise ValueError("no polygon file among the files given: a boundary is a .zip, a .shp (with its .shx, "
                             ".dbf and .prj), a .geojson, a .gpkg, a .kml or a .kmz")
        path = os.path.join(d, main[0])
    else:
        path = str(val).strip().strip('"')
        if not path or not os.path.exists(path):
            raise ValueError(f"not found on this computer: {path or '(empty)'}")
    P = er.read_plan(path, feature=er.feature_setting(feature))
    out = {"path": os.path.abspath(path), "name": os.path.basename(path), "n_polygons": int(P["n_polygons"]),
           "area_ac": float(P["area_ac"]), "needs_choice": bool(P.get("needs_choice")),
           "fields": list(P.get("fields") or []), "feature": er.feature_list(feature),
           "is_plan": bool(P.get("is_plan")), "warnings": list(P.get("warnings") or []), "outline": []}
    if not out["needs_choice"]:
        out["outline"] = _outline_of(er.plan_union_wgs84(P))
    return out


def chosen_fields(B: dict) -> str:
    """'field Synthetic 1' / 'fields 1 and 2' of a boundary file of several fields, for the messages."""
    names = {int(f["index"]): (f.get("name") or f"polygon {f['index']}") for f in B.get("fields") or []}
    ch = [names.get(int(v), str(v)) for v in B.get("feature") or []]
    return ("field " if len(ch) == 1 else "fields ") + " + ".join(ch)


def boundary_of(tag: str) -> dict | None:
    """The boundary of an extracted file, when one is given and usable (a file of several fields needs its choice)."""
    B = ss.boundary.get(tag)
    return B if (B and not B.get("needs_choice") and os.path.exists(B["path"])) else None


# ------------------------------------------------------------------------------------------------ grower's data
def grower_ticket(G: dict | None) -> dict | None:
    """The grower's total weight of a file as the engine's scale_ticket {value, unit, basis, moisture_pct, note}."""
    if not G or not G.get("weight"):
        return None
    wet = G.get("basis") == "wet"
    return {"value": float(G["weight"]), "unit": G.get("unit") or "lb", "basis": "wet" if wet else "dry",
            "moisture_pct": (float(G["moisture"]) if (wet and G.get("moisture") is not None) else None), "note": None}


def file_config(tag: str, sset: dict) -> dict:
    """Everything one cleaning of `tag` depends on: the SMS 3-sigma settings, the boundary and the grower's data."""
    B = boundary_of(tag)
    G = ss.grower.get(tag) or {}
    return {"sms3sigma": dict(sset), "boundary": (B["path"], tuple(B.get("feature") or ())) if B else None,
            "grower": {k: G.get(k) for k in ("weight", "unit", "basis", "moisture", "test_weight", "crop", "std_moisture",
                                             "use")} if grower_ticket(G) or G.get("test_weight") else None}


def settings_of(tag: str, sset: dict) -> dict:
    """The engine settings of one cleaning: the SMS 3-sigma sequence without a combine factor; the field boundary as
    the field of interest (records more than the S1 edge tolerance outside it set aside before the cleaning, the clean
    file clipped to it, so the monitor total that the grower's weight is compared with is the field's); the grower's
    total weight, the bushel weight (test weight), the crop and the standard moisture."""
    clip = bool(sset.get("clip", True))
    S3 = {k: v for k, v in sset.items()}
    S = {"method": "sms3sigma", "tag": tag, "machines": {"harmonise": False}, "sms3sigma": S3}
    B = boundary_of(tag)
    if B is not None and clip:
        S["aoi"] = {"file": B["path"], "buffer_m": float(sms.DEFAULTS["clip_tolerance_m"]), "clip_output": True,
                    "feature": er.feature_setting(B.get("feature"))}
    G = ss.grower.get(tag) or {}
    T = grower_ticket(G)
    if T is not None:
        S["scale_ticket"] = T
    if G.get("test_weight"):
        S["test_weight_lb_bu"] = float(G["test_weight"])
    if G.get("crop"):
        S["crop"] = G["crop"]
    if G.get("std_moisture") is not None and T is not None:
        S["moisture"] = {"standard_pct": float(G["std_moisture"])}
    return S


def dbf_drop_fields(dbf: str, names) -> list:
    """Remove the fields `names` from a dBase file in place, every other byte kept (the header, the other fields'
    descriptors and values, the deletion flags). Returns the names removed."""
    with open(dbf, "rb") as fh:
        b = fh.read()
    n_rec = int.from_bytes(b[4:8], "little")
    h_len = int.from_bytes(b[8:10], "little")
    r_len = int.from_bytes(b[10:12], "little")
    fields, off, pos = [], 1, 32
    while pos < h_len and b[pos] != 0x0D:
        d = b[pos:pos + 32]
        name = d[:11].split(b"\x00")[0].decode("latin-1")
        fields.append((name, d, off, d[16]))
        off += d[16]
        pos += 32
    drop = {str(n).upper() for n in names}
    keep = [f for f in fields if f[0].upper() not in drop]
    gone = [f[0] for f in fields if f[0].upper() in drop]
    if not gone:
        return []
    tail = b[pos:h_len]                                  # the 0x0D terminator and whatever followed it in the header
    new_h = 32 + 32 * len(keep) + len(tail)
    new_r = 1 + sum(f[3] for f in keep)
    head = bytearray(b[:32])
    head[8:10] = new_h.to_bytes(2, "little")
    head[10:12] = new_r.to_bytes(2, "little")
    out = bytearray(head) + b"".join(f[1] for f in keep) + tail
    for i in range(n_rec):
        r = b[h_len + i * r_len: h_len + (i + 1) * r_len]
        out += r[:1] + b"".join(r[f[2]:f[2] + f[3]] for f in keep)
    out += b[h_len + n_rec * r_len:]                     # the end-of-file marker, when present
    with open(dbf, "wb") as fh:
        fh.write(bytes(out))
    return gone


def extract(cand, chosen_units, opts, kw, log):
    """The chosen units as one shapefile per field, season and crop (engine.run.decode on each group)."""
    groups = {}
    for u in chosen_units:
        groups.setdefault((u.field or "", u.year, str(u.crop or "").strip().lower()), []).append(u)
    made = {}
    for (field, year, crop), us in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0, kv[0][2])):
        tag = er.candidate_tag(cand, us)
        if tag in made:                                  # the same field and season in two crops
            tag = yc.sanitise_tag(f"{tag}_{crop or 'crop'}")[:60]
        ss.cleaned.pop(tag, None)                        # extracted again: its old cleaning no longer applies
        log(f"extracting {field or '(no field)'} {year or ''} ({len(us)} unit(s)) ...")
        d = er.decode(cand, [u.id for u in us], opts, ss.workdir, log=log, tag=tag, **kw)
        d.pop("df", None)
        t = d["report"].get("totals") or {}
        made[d["tag"]] = {"tag": d["tag"], "shp": d["shp"], "zip": d["zip"], "n": d["n"], "kind": "raw",
                          "op": "harvest", "yield": True,
                          "label": f"{field or '(no field)'} · {year or 'no season'} · {crop or 'crop?'}",
                          "source": d["source"], "report": d["report"], "area_ac": t.get("area_ac"),
                          "units": [u.label for u in us]}
    return made


def clean_one(tag: str, sset: dict, log=lambda m: None) -> dict:
    """The SMS 3-sigma sequence on one extracted file (yield_clean through engine.run.clean, method sms3sigma, no
    combine factor; the file's boundary and grower's data from settings_of), then <tag>_sms3s_clean.shp / .zip in
    clean_shapefiles/. 'Validate only' leaves the adjusted yields (Yld_Level, Yld_Lvl_Sy) out of the clean file."""
    D = ss.datasets[tag]
    if not D.get("yield", True):
        return clean_applied(tag, sset, log=log)
    out = os.path.join(ss.workdir, "clean", tag)
    settings = settings_of(tag, sset)
    R = er.clean(D["shp"], out, settings, log=log, source=D.get("source"))
    F = R["files"]
    cdir = os.path.join(ss.workdir, "clean_shapefiles")
    os.makedirs(cdir, exist_ok=True)
    src = os.path.splitext(F["difm_ready_shp"])[0]
    stem = os.path.join(cdir, os.path.basename(src))     # <tag>_sms3s_clean, the name the report gives
    for e in er.SHP_EXTS:
        if os.path.exists(stem + e):
            os.remove(stem + e)
        if os.path.exists(src + e):
            shutil.copyfile(src + e, stem + e)
    G = ss.grower.get(tag) or {}
    adjusted = bool(settings.get("scale_ticket")) and G.get("use", "validate") == "adjust"
    dropped = [] if adjusted else dbf_drop_fields(stem + ".dbf", LEVEL_COLUMNS)
    if dropped:
        R = record_without_level(R, dropped)
    clean_zip = zip_shapefile(stem + ".shp", stem + ".zip")
    return {"R": R, "shp": stem + ".shp", "zip": clean_zip, "flagged_shp": F.get("flagged_shp"),
            "flagged_zip": F.get("flagged_zip"), "report_pdf": F.get("report_pdf"), "json": F.get("json"),
            "settings": dict(sset), "config": file_config(tag, sset), "adjusted": adjusted, "dropped": dropped,
            "boundary": boundary_of(tag) if settings.get("aoi") else None, "kind": "sms",
            "at": dt.datetime.now().strftime("%H:%M:%S")}


# ------------------------------------------------------------------------------------------------ as-applied 3-sigma
A3_KEYS = ("attributes", "repeat", "min_value", "k_sd", "max_passes", "group_by", "clip")


def a3_defaults(op: dict) -> dict:
    """The 3-sigma settings a planter / sprayer file starts with: the applied rate (the first one found) and the
    speed, the rate as the main attribute, readings with no product (rate <= 0) removed at import."""
    attrs = op["rates"][:1] + ([op["speed"]] if op.get("speed") else [])
    return {"attributes": attrs, "repeat": op["rates"][0] if op["rates"] else (attrs[0] if attrs else None),
            "min_value": 0.0, "k_sd": float(a3.DEFAULTS["k_sd"]), "max_passes": int(a3.DEFAULTS["max_passes"]),
            "group_by": "auto", "clip": True}


def sset_for(tag: str) -> dict:
    """The cleaning settings of one file: the SMS sequence of the harvest panel for a yield file, the file's own
    3-sigma settings for any other (its panel's, else the defaults of its columns)."""
    D = ss.datasets[tag]
    if D.get("yield", True):
        keys = ("k_sd", "group_by", "max_yield_passes", "min_yield", "clip", "swath", "speed", "moisture", "yield")
        return dict(ss.get("smsset") or {k: sms.DEFAULTS[k] for k in keys})
    if tag in ss.a3set:
        return dict(ss.a3set[tag])
    df = read_points(D["shp"], mtime(D["shp"]))
    return a3_defaults(a3.detect_operation([c for c in df.columns if c not in ("lon", "lat")], df))


def a3_panel(tag: str, op: dict, df: pd.DataFrame) -> dict:
    """The 3-sigma settings of a planter / sprayer / other point file (each file keeps its own)."""
    TKa = key_of(tag)
    P = ss.a3set.get(tag) or a3_defaults(op)
    nums = [c for c in df.columns if c not in ("lon", "lat") and c not in HIDDEN
            and pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=True) > 1]
    unit = lambda c: op["units"].get(c) or (ATTR_INFO.get(c) or ("", "", ""))[1]          # noqa: E731
    lab = lambda c: c + (f" ({unit(c)})" if unit(c) else "")                                # noqa: E731
    with st.container(key="method_panel"):
        attrs = st.multiselect("Attributes to clean with 3-sigma", nums, default=[a for a in P["attributes"] if a in nums],
                               key=f"a3_attrs_{TKa}", format_func=lab, placeholder="choose the attributes ...",
                               help="The applied rate and the speed are the usual pair (SMS filters the speed and the "
                                    "rate). Each one is a 3-sigma step, the speed first.")
        with st.container(horizontal=True, vertical_alignment="bottom"):
            opts = attrs or nums
            cur = P.get("repeat") if P.get("repeat") in opts else (opts[0] if opts else None)
            main = st.selectbox("Main attribute", opts, index=opts.index(cur) if cur in opts else 0,
                                key=f"a3_main_{TKa}", format_func=lab,
                                help="Its 3-sigma runs again while the SD falls by more than 25 % (as SMS does with the "
                                     "yield), and the import minimum applies to it.") if opts else None
            k_sd = st.number_input("k (SD)", 1.0, 6.0, float(P["k_sd"]), 0.5, key=f"a3_k_{TKa}")
            mp = st.number_input("Passes (max)", 1, 10, int(P["max_passes"]), 1, key=f"a3_mp_{TKa}")
            gm = list(a3.GROUP_MODES)
            gb = st.selectbox("Mean and SD per", gm, index=gm.index(P.get("group_by", "auto")), key=f"a3_gb_{TKa}",
                              format_func={"auto": "auto", "dataset": "dataset", "machine": "machine",
                                           "none": "the field"}.get,
                              help="auto: per machine when the file holds several machines, else the field.")
        with st.container(horizontal=True, vertical_alignment="bottom"):
            use_min = st.toggle("S0 import minimum", value=P.get("min_value") is not None, key=f"a3_um_{TKa}",
                                help="Remove the readings whose main attribute is at or below the minimum (0 = no "
                                     "product or no seed applied: sections off, the planter raised).")
            mv = st.number_input("Minimum of the main attribute", value=float(P.get("min_value") or 0.0), step=1.0,
                                 key=f"a3_mv_{TKa}", disabled=not use_min)
            clip = st.toggle("S1 Clip To Field Boundary", value=bool(P.get("clip", True)), key=f"a3_clip_{TKa}",
                             help="Needs the boundary of the file (below); a file without one is not clipped.")
    if main and main not in attrs:
        attrs = list(attrs) + [main]
    out = {"attributes": list(attrs), "repeat": main, "min_value": float(mv) if use_min else None,
           "k_sd": float(k_sd), "max_passes": int(mp), "group_by": gb, "clip": bool(clip)}
    ss.a3set[tag] = out
    return out


def clean_applied(tag: str, aset: dict, log=lambda m: None) -> dict:
    """The 3-sigma cleaning of a planter / sprayer / other point file (engine/clean/applied3s.py), then its clean
    shapefile in clean_shapefiles/."""
    D = ss.datasets[tag]
    if not aset.get("attributes"):
        raise ValueError("choose the attributes to clean (step 3)")
    out = os.path.join(ss.workdir, "clean", tag)
    B = boundary_of(tag)
    use_b = B is not None and aset.get("clip", True)
    R = a3.run(D["shp"], out, {k: aset[k] for k in A3_KEYS}, boundary=B["path"] if use_b else None,
               feature=er.feature_setting(B.get("feature")) if use_b else None, tag=tag, log=log)
    F = R["files"]
    cdir = os.path.join(ss.workdir, "clean_shapefiles")
    os.makedirs(cdir, exist_ok=True)
    src = os.path.splitext(F["clean_shp"])[0]
    stem = os.path.join(cdir, os.path.basename(src))
    for e in er.SHP_EXTS + (".zip",):
        if os.path.exists(src + e):
            shutil.copyfile(src + e, stem + e)
    return {"R": R, "shp": stem + ".shp", "zip": stem + ".zip", "flagged_shp": F.get("flagged_shp"),
            "flagged_zip": F.get("flagged_zip"), "report_pdf": F.get("report_pdf"), "json": F.get("json"),
            "settings": dict(aset), "config": file_config(tag, aset), "adjusted": False, "dropped": [],
            "boundary": B if use_b else None, "kind": "a3", "at": dt.datetime.now().strftime("%H:%M:%S")}


def clipped_of(C: dict) -> int:
    """The readings S1 clipped in a cleaning result (SMS: the pre-step + S1; 3-sigma: the S1 row)."""
    R = C["R"]
    if C.get("kind") == "a3":
        return int(next((r["removed"] for r in R["cascade"] if r["filter"] == "S1"), 0))
    return int(((R.get("sms3sigma") or {}).get("clip") or {}).get("sms_clip_equivalent") or 0)


def record_without_level(R: dict, dropped: list) -> dict:
    """'Validate only': the report (PDF) and the cleaning record (JSON) written again for the clean file without the
    leveled yields. The validation (the Level to scale ticket section) stays; the column to map is the monitor's dry
    yield and the final map (a figure of the leveled yield) is left out. Returns the result as written."""
    import copy
    from engine.report.clean_report import make_report
    R2 = copy.deepcopy(R)
    R2["difm_ready_added_columns"] = [c for c in R2.get("difm_ready_added_columns") or [] if c not in dropped]
    R2["yield_column_for_difm"] = (R2.get("columns") or {}).get("yield") or "Yld_Vol_Dr"
    for k in ("level_column_for_difm", "level_symmetric_column_for_difm", "final_map"):
        R2.pop(k, None)
    figs = (R2.get("files") or {}).get("figures") or {}
    figs.pop("final", None)
    R2.setdefault("notes", []).append(
        "OCED, validate only: the grower's weight validates the monitor's total; the clean shapefile keeps the "
        "monitor's yields and leaves out the leveled columns (" + ", ".join(dropped) + ")")
    R2["oced"] = {"grower_use": "validate", "columns_left_out": list(dropped)}
    F = R2.get("files") or {}
    if F.get("report_pdf"):
        make_report(R2, F["report_pdf"])
    if F.get("json"):
        with open(F["json"], "w", encoding="utf-8") as fh:
            json.dump(R2, fh, indent=1, default=yc._json_default)
    return R2


def all_clean_zip() -> str | None:
    C = {t: c for t, c in ss.cleaned.items() if os.path.exists(c["shp"])}
    if not C:
        return None
    zp = os.path.join(ss.workdir, "clean_shapefiles", "OCED_clean_shapefiles.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for t, c in C.items():
            base = os.path.splitext(c["shp"])[0]
            for e in er.SHP_EXTS:
                if os.path.exists(base + e):
                    z.write(base + e, f"{t}/{os.path.basename(base)}{e}")
    return zp


# ------------------------------------------------------------------------------------------------ header
with st.container(key="app_header"):
    h1, h2, h3 = st.columns([1.4, 3.8, 1.5], vertical_alignment="center")
    with h1:
        logo = brand.LOGO_H_REV if os.path.exists(brand.LOGO_H_REV) else brand.LOGO_H
        if os.path.exists(logo):
            st.image(logo, width=200)
    with h2:
        brand.brand_block(NAME, VERSION, TAGLINE)
    with h3:
        if st.button("Start over", icon=":material/restart_alt:", key="start_over",
                     help="Clears the screen. The files already written stay in the work folder."):
            start_over()
            st.rerun()

with st.sidebar:
    st.markdown(f"**{NAME} {VERSION}** · Olds College Extract Data")
    st.caption("The data of combines, planters and sprayers: the map of every attribute, the 3-sigma cleaning with "
               "the clip to the field boundary, the grower's data to validate or adjust the yields, and the clean "
               "shapefiles and reports.")
    st.caption("Combines, raw: Case IH / New Holland .cn1 cards, John Deere Gen4 / G5 logs (JD-Data .jdl), John Deere "
               "GreenStar 3 cards (.fdd / .fdl). Point exports of combines, planters and sprayers: SMS and Operations "
               "Center shapefiles (yield also as .kml / .kmz), or any point shapefile of a machine.")
    if ss.workdir:
        st.caption("Work folder")
        st.code(ss.workdir, language=None, wrap_lines=True)

# ------------------------------------------------------------------------------------------------ 1 raw data
with st.container(border=True, key="oced_step_1"):
    brand.step_header(1, "Machine data", "The files of a combine, planter or sprayer: upload them, or open a file or "
                                         "folder on this computer")
    ups = st.file_uploader("Upload files", accept_multiple_files=True, key="uploads",
                           help="Combines: a zipped card or JD-Data folder, the files of a GreenStar card, a yield "
                                "point export or its .kml / .kmz. Planters and sprayers: the as-applied point export "
                                "(.shp + .shx + .dbf + .prj, or a zip). Any other point shapefile of a machine too.")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.text_input("or a file or folder on this computer", key="path_in",
                      placeholder=r"C:\...\JD-Data   or   C:\...\CARD19.cn1   (nothing is copied)")
        if st.button("Open", type="primary", icon=":material/folder_open:", key="open_btn"):
            if ups:
                request_open(("upload", ups))
            elif (ss.get("path_in") or "").strip():
                request_open(("path", ss.path_in))
            else:
                st.toast("Upload files or type a path first", icon=":material/info:")
    if ss.open_request:
        req, ss.open_request = ss.open_request, None
        with st.spinner("Unpacking and recognising the input ..."):
            do_open(req)
    if ss.open_error:
        st.error(ss.open_error, icon=":material/error:")
        if ss.open_exc is not None:
            st.exception(ss.open_exc)
    cands, cand = ss.cands, None
    if cands is not None:
        if not cands:
            st.error(cands.message or "Nothing that OCED can read was found.", icon=":material/help:")
        else:
            idx = (st.selectbox("Several datasets were found: which one?", range(len(cands)),
                                format_func=lambda i: cands[i]["label"], key="cand_idx", index=None,
                                placeholder="choose a dataset ...") if len(cands) > 1 else 0)
            cand = cands[idx] if idx is not None else None
        with st.expander("Details of the unpacking"):
            st.text("\n".join(ss.open_log + [f"note: {n}" for n in getattr(cands, "notes", [])]) or "nothing")
    if cand is not None:
        icon = ":material/memory:" if cand["kind"] == "raw" else ":material/scatter_plot:"
        st.success(cand["label"], icon=icon)
        CK = key_of(cand.get("path") or cand["probe"].root)
        if cand["kind"] == "raw":
            root = cand["probe"].root
            if root not in ss.units:
                with st.spinner("Listing the tasks / machines / loads ..."):
                    ss.units[root] = er.list_units(cand)
            units = ss.units[root]
            if not units:
                st.error("No harvest data with grain flow was found in this dataset. Planter and sprayer data are "
                         "read from their point exports for now (a shapefile from SMS, Operations Center or the "
                         "display's export): the raw planter and sprayer formats of the cards are not decoded yet.",
                         icon=":material/error:")
            else:
                U = pd.DataFrame([dataclasses.asdict(u) for u in units])
                U["field"] = U["field"].replace("", "(no field)")
                U = U.sort_values(["field", "year", "start"], na_position="last").reset_index(drop=True)
                n_fields = U["field"].nunique()
                st.markdown(f"**{len(U):,} unit(s) in {n_fields:,} field(s).** Choose the units to extract: each "
                            "field, season and crop becomes its own shapefile. The most recent season is pre-selected.")
                ev = st.dataframe(U[["field", "year", "crop", "machine", "n_records", "start", "end", "label"]],
                                  hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"units_{CK}",
                                  selection_default={"selection": {"rows": [int(i) for i in U.index[U["default"]]]}},
                                  column_config={"n_records": st.column_config.NumberColumn("records", format="%d"),
                                                 "label": st.column_config.TextColumn("unit", width="large")})
                chosen_ids = U.iloc[list(ev.selection.rows)]["id"].tolist()
                chosen = [u for u in units if u.id in set(chosen_ids)]
                groups = sorted({(u.field or "(no field)", u.year) for u in chosen}, key=lambda g: (g[0], g[1] or 0))
                fid = cand["decoder"]
                dflt = detect.default_options(fid)
                with st.expander("Decoding options (crop, test weight, standard moisture, dry yield)",
                                 icon=":material/tune:"):
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        crop = st.selectbox("Crop", [FROM_MONITOR] + list(common.CROPS), key=f"crop_{CK}")
                        tw = st.number_input("Test weight (lb/bu)", min_value=1.0, max_value=100.0, value=None,
                                             step=0.5, key=f"tw_{CK}", placeholder="monitor / crop table")
                        sm = st.number_input("Standard moisture (%)", min_value=0.0, max_value=40.0, value=None,
                                             step=0.5, key=f"sm_{CK}", placeholder="monitor / crop table")
                        shrink = st.segmented_control("Dry yield", ["one_sided", "symmetric"], default=dflt.shrink,
                                                      required=True, key=f"shrink_{CK}",
                                                      format_func={"one_sided": "One-sided",
                                                                   "symmetric": "Symmetric"}.get)
                    kw = {}
                    if fid == "cnh_cn1":
                        kw["calibration"] = st.segmented_control(
                            "Calibration curve", ["task", "latest"], default="task", required=True, key=f"cal_{CK}",
                            format_func={"task": "Each task's own (as SMS)", "latest": "Crop's latest"}.get)
                    elif fid == "jd_gs3_rcd":
                        from engine.formats import jd_gs3_rcd as gs3
                        with st.container(horizontal=True):
                            kw["flow_delay_s"] = st.number_input("Grain flow delay (s)", 0.0, 60.0, gs3.FLOW_DELAY_S,
                                                                 1.0, key=f"fd_{CK}")
                            kw["moisture_delay_s"] = st.number_input("Moisture delay (s)", 0.0, 60.0,
                                                                     gs3.MOISTURE_DELAY_S, 1.0, key=f"md_{CK}")
                    st.caption("Empty = the monitor's own values (else the crop table). The vendor's convention for "
                               f"the dry yield of this format: {dflt.shrink.replace('_', '-')}.")
                with st.container(key="run_go"):
                    go = st.button(f"Extract {len(groups)} file" + ("s" if len(groups) != 1 else "") if groups
                                   else "Extract", type="primary",
                                   icon=":material/file_export:", disabled=not chosen, key=f"extract_{CK}")
                if go:
                    opts = dataclasses.replace(dflt, crop=None if crop == FROM_MONITOR else crop,
                                               test_weight_lb_bu=tw, std_moisture_pct=sm, shrink=shrink)
                    with st.status("Extracting ...", expanded=True) as status:
                        try:
                            made = extract(cand, chosen, opts, kw, status.text)
                            ss.datasets.update(made)
                            ss.active = next(iter(made), ss.active)
                            status.update(label=f"Extracted {len(made)} file(s): "
                                                + ", ".join(f"{m['tag']} ({m['n']:,} readings)" for m in made.values()),
                                          state="complete", expanded=False)
                        except ValueError as e:
                            status.update(label="Extraction stopped", state="error")
                            st.error(str(e), icon=":material/error:")
                        except Exception as e:                       # shown, never swallowed
                            status.update(label="Extraction failed", state="error")
                            st.exception(e)
        else:
            if cand.get("sections") and not cand.get("source_path"):
                with st.spinner("One point per header section: collapsing to one reading per combine and second ..."):
                    er.use_candidate(cand, ss.workdir, log=ss.open_log.append)
            tag = er.candidate_tag(cand)
            if tag not in ss.datasets:
                ss.datasets[tag] = {"tag": tag, "shp": cand["path"], "zip": None, "n": int(cand.get("n") or 0),
                                    "kind": "export", "label": os.path.basename(cand.get("source_path") or cand["path"]),
                                    "op": cand.get("operation") or "harvest", "yield": bool(cand.get("yield", True)),
                                    "source": None, "report": None, "area_ac": None, "units": []}
                ss.active = tag
            st.caption("A point export is used as it is: its attributes are the vendor's columns."
                       + ("" if cand.get("yield", True) else " Not a yield file: it is cleaned with the 3-sigma of the "
                          "attributes you choose (the applied rate, the speed ...)."))

DS = ss.datasets
if not DS:
    st.info("Open the data of a field (step 1): the map, the attributes and the cleaning follow.",
            icon=":material/arrow_upward:")
    st.stop()

# ------------------------------------------------------------------------------------------------ 2 map and attributes
with st.container(border=True, key="oced_step_2"):
    brand.step_header(2, "Map and attributes", "One button per attribute: the map, its legend, its statistics")
    tags = list(DS)
    if ss.active not in tags:
        ss.active = tags[0]
    if len(tags) > 1:
        ss.active = st.selectbox("File", tags, index=tags.index(ss.active), key="active_pick",
                                 format_func=lambda t: f"{t} · {DS[t]['label']} · {DS[t]['n']:,} readings")
    D = DS[ss.active]
    df0 = read_points(D["shp"], mtime(D["shp"]))
    det = yc.detect_columns([c for c in df0.columns if c not in ("lon", "lat")])
    OPX = a3.detect_operation([c for c in df0.columns if c not in ("lon", "lat")], df0)
    yv = pd.to_numeric(df0[det["yield"]], errors="coerce") if det.get("yield") else None
    tcol = det.get("time")
    tt = pd.to_datetime(df0[tcol], errors="coerce") if tcol else None
    mcol = det.get("machine")
    with st.container(horizontal=True):
        st.metric("Operation", a3.OPERATION_LABEL.get(D.get("op") or "harvest", "Point data").split(" (")[0],
                  border=True, help=a3.OPERATION_LABEL.get(D.get("op") or "harvest"))
        st.metric("Readings", f"{len(df0):,}", border=True)
        if not D.get("yield", True) and OPX["rates"]:
            r0 = OPX["rates"][0]
            rv = pd.to_numeric(df0[r0], errors="coerce")
            if rv.notna().any():
                st.metric("Mean applied rate", f"{rv.mean():,.2f} {OPX['units'].get(r0, '')}".strip(), border=True,
                          help=f"{r0}, every reading")
        if D.get("area_ac"):
            st.metric("Area harvested", f"{float(D['area_ac']):,.2f} ac", border=True,
                      help="The strips the readings swept (distance x width), added up.")
        if D.get("yield", True) and yv is not None and yv.notna().any():
            st.metric("Mean dry yield", f"{yv.mean():,.2f} bu/ac", border=True)
        if tt is not None and tt.notna().any():
            st.metric("Date", f"{tt.min():%d %b %Y}" + (f" – {tt.max():%d %b}" if tt.max().date() != tt.min().date()
                                                            else ""), border=True)
        if mcol:
            st.metric("Machines", f"{df0[mcol].astype(str).replace('', np.nan).nunique():,}", border=True)
    B_ = boundary_of(ss.active)
    dflt_attr = (("Yld_Vol_Dr" if "Yld_Vol_Dr" in df0 else det.get("yield")) if D.get("yield", True) else
                 (OPX["rates"][0] if OPX["rates"] else None))
    explorer(D["shp"], key=f"raw_{key_of(D['shp'])}", default=dflt_attr, outline=B_["outline"] if B_ else None)
    if D.get("report"):
        with st.expander("What the decoder reported", icon=":material/memory:"):
            rep = D["report"]
            st.caption("Units: " + "; ".join(D.get("units") or []))
            if rep.get("machines"):
                st.dataframe(pd.DataFrame(rep["machines"]), hide_index=True)
            if rep.get("pre_step"):
                st.dataframe(pd.Series(rep["pre_step"], name="records").rename_axis("not exported as readings")
                             .reset_index(), hide_index=True)
            for w in rep.get("warnings") or []:
                st.warning(w, icon=":material/warning:")
    if D.get("zip"):
        download("Extracted points, all readings (.zip)", D["zip"], "application/zip", key=f"dl_ext_{ss.active}")

# ------------------------------------------------------------------------------------------------ 3 SMS 3-sigma
with st.container(border=True, key="oced_step_3"):
    IS_Y = bool(D.get("yield", True))
    D0 = sms.DEFAULTS
    if IS_Y:
        brand.step_header(3, "Cleaning: SMS 3-sigma", "The sequence of Ag Leader SMS Advanced, with the field boundary "
                                                      "and the grower's data")
        st.caption("S0 import check (no position, no yield, dry yield below the SMS import minimum) · S1 Clip To Field "
                   "Boundary (the readings outside the boundary of the file; a point on the edge is inside) · S2 "
                   "Optimize Swath Widths (overlapping strips removed or narrowed, per-area values scaled) · S3 speed, "
                   "S4 moisture and S5 dry yield: keep the mean ± k SD of the points still alive, another yield pass "
                   "while the SD falls by more than 25 %. No combine factor between harvesters.")
        P0 = ss.get("smsset") or {}
        with st.container(key="method_panel"):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                k_sd = st.number_input("k (SD)", 1.0, 6.0, float(P0.get("k_sd", D0["k_sd"])), 0.5, key="k_sd",
                                       help="Keep mean ± k standard deviations (3 = the 3-sigma of SMS).")
                gm = list(sms.GROUP_MODES)
                group_by = st.selectbox("Mean and SD per", gm, index=gm.index(P0.get("group_by", "auto")),
                                        key="group_by", format_func={"auto": "auto", "task": "task (dataset)",
                                                                     "machine": "machine", "field": "field"}.get,
                                        help="auto: one mean and SD for the field when one combine cut it, one per task "
                                             "(dataset) when several did, as the OFPE team runs SMS.")
                max_passes = st.number_input("Yield passes (max)", 1, 10,
                                             int(P0.get("max_yield_passes", D0["max_yield_passes"])), 1,
                                             key="max_passes")
                min_yield = st.number_input("Import minimum (bu/ac)", 0.0, 50.0,
                                            float(P0.get("min_yield", D0["min_yield"])), 1.0, key="min_yield",
                                            help="S0: SMS drops the readings below 5 bu/ac at import.")
            with st.container(horizontal=True):
                clip = st.toggle("S1 Clip To Field Boundary", value=bool(P0.get("clip", D0["clip"])), key="t_clip",
                                 help="Needs the boundary of the file (below); a file without one is not clipped.")
                swath = st.toggle("S2 Optimize Swath Widths", value=bool(P0.get("swath", D0["swath"])), key="t_swath")
                speed = st.toggle("S3 speed", value=bool(P0.get("speed", D0["speed"])), key="t_speed")
                moist = st.toggle("S4 moisture", value=bool(P0.get("moisture", D0["moisture"])), key="t_moist")
                yld = st.toggle("S5 dry yield", value=bool(P0.get("yield", D0["yield"])), key="t_yield")
        sset = {"k_sd": float(k_sd), "group_by": group_by, "max_yield_passes": int(max_passes),
                "min_yield": float(min_yield), "clip": bool(clip), "swath": bool(swath), "speed": bool(speed),
                "moisture": bool(moist), "yield": bool(yld)}
        ss.smsset = dict(sset)
    else:
        brand.step_header(3, "Cleaning: 3-sigma", "The SMS 3-sigma rule on the attributes you choose, with the field "
                                                  "boundary")
        st.caption("S0 import check (no position; the main attribute missing or at or below the minimum: no product "
                   "applied) · S1 Clip To Field Boundary · then one 3-sigma step per attribute, the speed first: keep "
                   "the mean ± k SD of the points still alive (limits rounded to 2 decimals, as typed in SMS); the "
                   "main attribute again while its SD falls by more than 25 %.")
        sset = a3_panel(ss.active, OPX, df0)
    clip = bool(sset.get("clip", True))
    # ---- the field boundary and the grower's data of the file on screen (each file keeps its own)
    TK = key_of(ss.active)
    c_b, c_g = st.columns(2, gap="medium")
    with c_b:
        with st.container(key=f"field_box_b_{TK}"):
            st.markdown(f"**Field boundary (S1)** · `{ss.active}`")
            B = ss.boundary.get(ss.active)
            if B:
                if B["needs_choice"]:
                    st.info(f"{B['name']} · {len(B.get('fields') or [])} fields in one file", icon=":material/crop_free:")
                else:
                    st.success(f"{B['name']} · " + (f"{chosen_fields(B)} · " if B.get("feature")
                                                     else f"{B['n_polygons']} polygon(s) · ")
                               + f"{B['area_ac']:,.2f} ac" + ("" if clip else " · S1 is off: not clipped"),
                               icon=":material/crop_free:")
                if B.get("fields") and (B["needs_choice"] or B.get("feature")):
                    opts = [int(f["index"]) for f in B["fields"]]
                    lab = {int(f["index"]): f"{f['index']} · {f.get('name') or 'polygon ' + str(f['index'])} "
                                            f"({float(f.get('area_ac') or 0):,.2f} ac)" for f in B["fields"]}
                    sel = st.multiselect("This file holds several fields: which one is this field?", opts,
                                         default=[v for v in (B.get("feature") or []) if v in opts], key=f"bnd_feat_{TK}",
                                         format_func=lab.get, placeholder="choose the field ...",
                                         help="Several polygons together = one field drawn in parts (their union).")
                    if sorted(sel) != sorted(B.get("feature") or []):
                        try:
                            if sel:
                                nb = load_boundary(ss.active, ("path", B["path"]), feature=sel)
                                nb["fields"] = nb["fields"] or B["fields"]
                            else:
                                nb = dict(B, feature=None, needs_choice=True, outline=[])
                            ss.boundary[ss.active] = nb
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e), icon=":material/error:")
                    if B["needs_choice"]:
                        st.warning("Choose the field: until then the file is cleaned without the clip.",
                                   icon=":material/warning:")
                if B.get("is_plan"):
                    st.caption("This file looks like a trial plan (plots): S1 clips to the plots, not to a field "
                               "boundary. Give the field boundary to keep the alleys and the border.")
                for w in B.get("warnings") or []:
                    st.caption(w)
                if st.button("Remove the boundary", icon=":material/delete:", key=f"bnd_rm_{TK}"):
                    ss.boundary.pop(ss.active, None)
                    st.rerun()
            else:
                bup = st.file_uploader("Boundary file", accept_multiple_files=True, key=f"bnd_up_{TK}",
                                       type=BOUNDARY_TYPES,
                                       help="A .zip (a shapefile or an SMS 'Boundaries' export), the .shp + .shx + "
                                            ".dbf + .prj of a shapefile, a .geojson, .gpkg, .kml or .kmz.")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    bpath = st.text_input("or a file on this computer", key=f"bnd_path_{TK}",
                                          placeholder=r"C:\...\Field 19 boundary.zip")
                    use_b = st.button("Use", type="primary", icon=":material/crop_free:", key=f"bnd_use_{TK}")
                if use_b:
                    if not bup and not (bpath or "").strip():
                        st.toast("Upload a boundary file or type its path first", icon=":material/info:")
                    else:
                        try:
                            ss.boundary[ss.active] = load_boundary(ss.active, ("upload", bup) if bup
                                                                   else ("path", bpath))
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e), icon=":material/error:")
                        except Exception as e:                       # shown, never swallowed
                            st.exception(e)
                st.caption("Without a boundary S1 is skipped and every reading of the file goes into the cleaning.")
    with c_g:
        if not IS_Y:
            with st.container(key=f"field_box_g_{TK}"):
                st.markdown(f"**What the file is** · `{ss.active}`")
                rows_i = [("Operation", OPX["label"]),
                          ("Applied rate", ", ".join(OPX["rates"]) or "none found (choose the attributes at the left)"),
                          ("Target rate", ", ".join(OPX["targets"]) or "-"), ("Speed", OPX["speed"] or "-"),
                          ("Machine", OPX["machine"] or "-"), ("Dataset", OPX["dataset"] or "-")]
                if OPX["product"]:
                    pv = df0[OPX["product"]].astype(str).replace({"": np.nan, "nan": np.nan}).dropna().unique()
                    rows_i.append(("Product", ", ".join(map(str, pv[:5])) + (f" … ({len(pv)})" if len(pv) > 5 else "")))
                st.dataframe(pd.DataFrame(rows_i, columns=["", "in this file"]), hide_index=True)
                st.caption("Recognised from the column names. The grower's data (total weight, moisture, bushel "
                           "weight) apply to harvest files.")
        else:
            with st.container(key=f"field_box_g_{TK}"):
                st.markdown(f"**Grower's data** · `{ss.active}`")
                G0 = ss.grower.get(ss.active) or {}
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    g_unit_prev = ss.get(f"gw_u_{TK}", G0.get("unit") or "lb")
                    g_w = st.number_input("Total weight of the field", 0.0, 1e12, value=G0.get("weight"), step=100.0,
                                          key=f"gw_w_{TK}", format="%.3f" if g_unit_prev == "t" else "%.0f",
                                          placeholder="optional, e.g. 1500000",
                                          help="What the grower got for this field (scale tickets or the grain cart), as "
                                               "written, in the unit at the right.")
                    g_unit = st.segmented_control("Unit", list(er.TICKET_UNITS), default=G0.get("unit") or "lb",
                                                  required=True, key=f"gw_u_{TK}", format_func=TICKET_UNIT_LABEL.get)
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    g_basis = st.segmented_control("Weighed", ["wet", "dry"], default=G0.get("basis") or "wet",
                                                   required=True, key=f"gw_b_{TK}",
                                                   format_func={"wet": "As delivered (wet)",
                                                                "dry": "At the standard moisture"}.get,
                                                   help="As delivered: compared with the monitor's wet total (or, with "
                                                        "the grain moisture, brought to the standard moisture). At the "
                                                        "standard moisture: compared with the dry total.")
                    g_m = st.number_input("Grain moisture (%)", 0.0, 60.0, value=G0.get("moisture"), step=0.1,
                                          key=f"gw_m_{TK}", placeholder="optional", disabled=g_basis != "wet",
                                          help="The moisture of the grain the grower weighed: the weight is brought to the "
                                               "standard moisture and compared with the monitor's dry total.")
                    g_tw = st.number_input("Bushel weight (lb/bu)", 1.0, 100.0, value=G0.get("test_weight"), step=0.1,
                                           key=f"gw_tw_{TK}", placeholder="file / crop table",
                                           help="The grower's test weight: converts the weight to bushels. Empty = the "
                                                "file's own (wet mass / wet volume), else the crop table.")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    crops = [None] + sorted(common.CROPS)
                    g_crop = st.selectbox("Crop", crops, index=crops.index(G0.get("crop")) if G0.get("crop") in crops else 0,
                                          key=f"gw_c_{TK}", format_func=lambda c: "from the file" if c is None else c,
                                          help="For the standard moisture and the crop's bushel weight when the file does "
                                               "not give them.")
                    g_sm = st.number_input("Standard moisture (%)", 0.0, 40.0, value=G0.get("std_moisture"), step=0.5,
                                           key=f"gw_sm_{TK}", placeholder="decoder / crop table")
                g_use = st.segmented_control("Use the grower's weight to", list(GROWER_USE),
                                             default=G0.get("use") or "validate", required=True, key=f"gw_use_{TK}",
                                             format_func=GROWER_USE.get, disabled=not g_w,
                                             help="Validate: the monitor's total against the grower's, L = grower / "
                                                  "monitor and a verdict; the clean file keeps the monitor's yields. "
                                                  "Adjust: also Yld_Level = the dry yield x L in the clean file (the bu/ac "
                                                  "then sum to the grower's weight); the monitor's columns stay as logged.")
                ss.grower[ss.active] = {"weight": float(g_w) if g_w else None, "unit": g_unit or "lb",
                                        "basis": g_basis or "wet", "moisture": g_m if g_basis == "wet" else None,
                                        "test_weight": g_tw, "crop": g_crop, "std_moisture": g_sm,
                                        "use": g_use or "validate"}
                T_ = grower_ticket(ss.grower[ss.active])
                if T_ is not None:
                    try:
                        conv = er.ticket_conversion(T_, test_weight=g_tw, shp=D["shp"], crop=g_crop)
                    except ValueError as e:
                        conv = {"error": str(e), "text": str(e)}
                    if conv.get("error"):
                        st.warning(f"{er.ticket_label(T_)}: {conv['error']}", icon=":material/warning:")
                    else:
                        st.caption(f"{er.ticket_label(T_)} {conv['text']}"
                                   + (f"; {T_['moisture_pct']:g} % grain moisture" if T_["moisture_pct"] is not None else "")
                                   + ("; weighed as delivered." if T_["basis"] == "wet" else
                                      "; at the standard moisture."))
                else:
                    st.caption("Optional. The total weight, the grain moisture and the bushel weight the grower measured "
                               "validate the monitor's yields or adjust them.")

    many = False
    with st.container(horizontal=True, key="run_go_box"):
        with st.container(key="run_go_2"):
            one = st.button(f"Clean {ss.active}", type="primary", icon=":material/cleaning_services:", key="clean_one")
        if len(DS) > 1:
            many = st.button(f"Clean all {len(DS)} files", icon=":material/done_all:", key="clean_all",
                             help="Each file with its own boundary and grower's data.")
    todo = [ss.active] if one else (list(DS) if many else [])
    for t in todo:
        with st.status(f"SMS 3-sigma on {t} ...", expanded=True) as status:
            try:
                ss.cleaned[t] = clean_one(t, sset if t == ss.active else sset_for(t), log=status.text)
                R = ss.cleaned[t]["R"]
                status.update(label=f"{t}: {R['n_in']:,} in → {R['n_kept']:,} kept ({R['removed_pct']:.2f} % "
                                    "removed)", state="complete", expanded=False)
            except Exception as e:                                   # shown, never swallowed
                status.update(label=f"{t}: the cleaning failed", state="error")
                st.exception(e)
    C = ss.cleaned.get(ss.active)
    if C and os.path.exists(C["shp"]):
        R = C["R"]
        A3 = C.get("kind") == "a3"
        if C.get("config") != file_config(ss.active, sset):
            st.warning("The settings, the boundary or the grower's data changed since this file was cleaned: clean it "
                       "again to apply them.", icon=":material/sync_problem:")
        M3 = R.get("sms3sigma") or {}
        L = R.get("level") or {}
        CL = L.get("closure") or {}
        with st.container(horizontal=True):
            st.metric("Readings in", f"{R['n_read'] if R.get('n_read') else R['n_in']:,}", border=True)
            st.metric("Kept", f"{R['n_kept']:,}", border=True)
            st.metric("Removed", f"{R['removed_pct']:.2f} %", border=True,
                      help="Of the readings inside the boundary" if C.get("boundary") else None)
            if C.get("boundary"):
                st.metric("Clipped (S1)", f"{clipped_of(C):,}",
                          border=True, help="Readings outside the field boundary (a point on the edge is inside).")
            if not A3:
                sw = M3.get("swath") or {}
                st.metric("Narrowed by S2", f"{int(sw.get('n_narrowed') or 0):,}", border=True,
                          help="Readings whose strip overlapped ground already cut: narrowed to the new strip, their "
                               "per-area values scaled (mass kept).")
            else:
                st.metric("Passes of " + str(R["main"]), f"{R.get('passes', 1)}", border=True)
            if CL:
                st.metric("Monitor vs grower", f"{CL['diff_pct']:+.2f} %", border=True,
                          help="The monitor's total against the grower's weight on the same basis: + = the monitor "
                               f"read more than the grower weighed (L = grower / monitor = {L['factor']:.4f}).")
        tab_names = ["Steps", "Limits", "Clean map", "Removed points"] + (["Grower's data"] if L else [])
        tabs_ = st.tabs(tab_names)
        t_steps, t_lim, t_clean, t_rem = tabs_[:4]
        with t_steps:
            steps_df = pd.DataFrame(R["cascade"])[["filter", "name", "on", "criterion", "removed", "remaining"]]
            pre = R.get("pre_steps") or []
            if pre:
                # the clip runs first (the readings outside the boundary are set aside before S0); the engine's own
                # S1 then finds nothing left outside, so its empty row goes
                steps_df = steps_df[~((steps_df["filter"] == "S1") & (steps_df["removed"] == 0))]
                steps_df = pd.concat([pd.DataFrame([{"filter": "S1", "name": "Clip To Field Boundary", "on": True,
                                                     "criterion": "outside the field boundary (a point within 1 cm "
                                                                  "of the edge is inside)",
                                                     "removed": p["removed"], "remaining": p["remaining"]}
                                                    for p in pre]), steps_df], ignore_index=True)
            st.dataframe(steps_df, hide_index=True)
            if C.get("boundary") and not A3:
                st.caption("S1 runs first here: the readings outside the boundary are set aside before S0, so the "
                           "monitor total that the grower's weight is compared with is the field's. SMS clips after "
                           "its import check; the points kept are the same.")
        with t_lim:
            steps = R.get("steps") if A3 else ((R.get("sms3sigma") or {}).get("steps") or [])
            if steps:
                cols = [c for c in ["group", "step", "attribute", "n_before", "mean", "sd", "lo", "hi", "unit",
                                    "removed", "n_after", "sd_drop_pct"] if c in pd.DataFrame(steps)]
                st.dataframe(pd.DataFrame(steps)[cols], hide_index=True,
                             column_config={"mean": st.column_config.NumberColumn(format="%.3f"),
                                            "sd": st.column_config.NumberColumn(format="%.3f"),
                                            "lo": st.column_config.NumberColumn("low", format="%.2f"),
                                            "hi": st.column_config.NumberColumn("high", format="%.2f"),
                                            "sd_drop_pct": st.column_config.NumberColumn("SD drop %", format="%.2f")})
                st.caption("Mean and SD of the points still alive before each step, and the limits typed into "
                           "Filter Data (mean ± k SD, rounded to 2 decimals). Grouping: "
                           + str(((R if A3 else (R.get("sms3sigma") or {})).get("grouping") or {}).get("rule", ""))
                           + ".")
        with t_clean:
            cols_clean = read_points(C["shp"], mtime(C["shp"])).columns
            explorer(C["shp"], key=f"clean_{key_of(C['shp'])}", height=480,
                     default=(R["main"] if A3 else "Yld_Level" if C.get("adjusted") and "Yld_Level" in cols_clean else
                              "Yld_Vol_Dr" if "Yld_Vol_Dr" in cols_clean else None),
                     outline=C["boundary"]["outline"] if C.get("boundary") else None)
        with t_rem:
            fl = C.get("flagged_shp")
            if fl and os.path.exists(fl):
                F_ = read_points(fl, mtime(fl))
                rb = F_["Rem_By"].astype(str).str[:2]
                grp = np.where(pd.to_numeric(F_["Keep"], errors="coerce").to_numpy(float) == 1, "kept", rb)
                rows = np.flatnonzero(np.isfinite(F_["lon"].to_numpy()) & np.isfinite(F_["lat"].to_numpy()))
                if len(rows) > MAP_N:
                    rows = np.sort(np.random.default_rng(0).choice(rows, MAP_N, replace=False))
                g = grp[rows]
                cols_ = [STEP_COLORS.get(x, "#FF8F00") for x in g]
                rgb = [[int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 90 if x == "kept" else 230]
                       for h, x in zip(cols_, g)]
                pts = pd.DataFrame({"lon": F_["lon"].to_numpy()[rows], "lat": F_["lat"].to_numpy()[rows], "rgb": rgb,
                                    "v": g})
                if pdk is not None:
                    lay = [pdk.Layer("ScatterplotLayer", data=pts, get_position=["lon", "lat"], get_fill_color="rgb",
                                     get_radius=2, radius_min_pixels=1.5, radius_max_pixels=6, pickable=True)]
                    ol = outline_layer(C["boundary"]["outline"] if C.get("boundary") else None)
                    if ol is not None:
                        lay.append(ol)
                    deck(lay, pts["lon"].to_numpy(), pts["lat"].to_numpy(), 460, tooltip={"text": "{v}"})
                vc = pd.Series(grp).value_counts()
                names = {str(r["filter"])[:2]: (r["name"] if A3 else
                                                sms.STEP_INFO.get(str(r["filter"])[:2], {}).get("name", r["name"]))
                         for r in R["cascade"]}
                st.html('<div style="display:flex;flex-wrap:wrap">' + "".join(
                    f'<span style="display:inline-flex;align-items:center;gap:6px;margin:2px 14px 2px 0;'
                    f'font-size:0.86rem"><span style="width:12px;height:12px;border-radius:50%;'
                    f'background:{STEP_COLORS.get(k, "#FF8F00")};border:1px solid #1F2937"></span><b>'
                    f'{html.escape("kept" if k == "kept" else k + " " + names.get(k, ""))}</b> {int(n):,} points</span>'
                    for k, n in vc.items()) + "</div>")
                st.caption("Every reading of the file: kept in green (faint), the removed ones in the colour of the "
                           "step that removed them." + (" The readings outside the boundary (S1) are not drawn; the "
                                                        "cyan line is the boundary." if C.get("boundary") else ""))
        if L:
            with tabs_[4]:
                area = float(L.get("export_area_ac") or 0)
                mon, gro = float(L["export_total_bu"]), float(L["scale_ticket_bu"])
                pct = (lambda m, g: f"{100 * (m / g - 1):+.2f} %" if g else "—")
                basis_txt = ("at the standard moisture" if L.get("ticket_bu_at_standard") is not None or
                             str(L.get("comparison_basis") or "").startswith("dry") else "as delivered")
                rows_v = [{"": f"Total (bu, {basis_txt})", "monitor": f"{mon:,.0f}", "grower": f"{gro:,.0f}",
                           "monitor vs grower": pct(mon, gro)}]
                if area > 0:
                    rows_v.append({"": f"Mean yield (bu/ac, {basis_txt})", "monitor": f"{mon / area:,.2f}",
                                   "grower": f"{gro / area:,.2f}", "monitor vs grower": pct(mon, gro)})
                if L.get("ticket_lb") and L.get("export_total_lb") and L.get("ticket_basis") == "wet":
                    rows_v.append({"": "Total weight as delivered (lb)", "monitor": f"{L['export_total_lb']:,.0f}",
                                   "grower": f"{L['ticket_lb']:,.0f}",
                                   "monitor vs grower": pct(L["export_total_lb"], L["ticket_lb"])})
                st.dataframe(pd.DataFrame(rows_v), hide_index=True)
                if len(rows_v) > 2 and L.get("ticket_bu_at_standard") is not None:
                    st.caption("The weights as delivered also differ by the moisture of the grain: the verdict "
                               "compares both at the standard moisture.")
                band = CL.get("band", "")
                tone = ("#E8F7F0", "#00784D") if band in ("<= 1 %", "1-3 %") else (
                    ("#FFF5E5", "#9A5B00") if band == "3-10 %" else ("#FDECEC", "#B42318"))
                st.html(f'<div class="oced-verdict" style="background:{tone[0]};border-color:{tone[1]};color:#1F2937">'
                        f'<b style="color:{tone[1]}">L = {L["factor"]:.4f} · band {html.escape(band)}</b><br>'
                        f'{html.escape(CL.get("verdict", ""))}</div>')
                facts = [f"Compared on the {L.get('comparison_basis') or L.get('basis')} basis, over the "
                         f"{area:,.2f} ac the readings swept"
                         + (" inside the boundary" if C.get("boundary") else "") + "."]
                if L.get("ticket_caption"):
                    facts.append("Grower's weight: " + L["ticket_caption"].replace(
                        "test weight from settings (test_weight_lb_bu)", "the grower's bushel weight") + ".")
                if L.get("ticket_bu_at_standard") is not None:
                    facts.append(f"At {L['ticket_moisture_pct']:g} % grain moisture: {L['ticket_bu']:,.0f} bu as "
                                 f"delivered = {L['ticket_bu_at_standard']:,.0f} bu at the standard moisture.")
                if L.get("test_weight_used") and not L.get("ticket_caption"):
                    facts.append(f"Bushel weight {L['test_weight_used']:.2f} lb/bu ({L.get('test_weight_source')}).")
                facts.append("Adjusted: Yld_Level = the dry yield x L is in the clean file (map it to use the "
                             "grower's level); the monitor's columns stay as logged." if C.get("adjusted") else
                             "Validation only: the clean file keeps the monitor's yields (no Yld_Level). Choose "
                             "'Validate and adjust the yields' and clean again to add the adjusted column.")
                st.caption(" ".join(facts))
                for w in [w for w in R.get("warnings") or [] if "ticket" in w.lower() or "level" in w.lower()]:
                    st.warning(w, icon=":material/warning:")

# ------------------------------------------------------------------------------------------------ 4 clean shapefiles
with st.container(border=True, key="oced_step_4"):
    brand.step_header(4, "Clean shapefiles and reports", "The kept readings of each file, with every attribute")
    if not ss.cleaned:
        st.info("Clean a file in step 3: its clean shapefile appears here.", icon=":material/info:")
    else:
        rows = []
        for t, c in ss.cleaned.items():
            R = c["R"]
            Lc = R.get("level") or {}
            rows.append({"file": t, "readings in": R.get("n_read") or R["n_in"],
                         "clipped (S1)": clipped_of(c) if c.get("boundary") else None,
                         "kept": R["n_kept"], "removed (%)": R["removed_pct"],
                         "cleaned on": (", ".join(R["attributes"]) if c.get("kind") == "a3" else "SMS S0-S5"),
                         "monitor vs grower (%)": (Lc.get("closure") or {}).get("diff_pct"),
                         "yields": ("—" if c.get("kind") == "a3" else "adjusted (Yld_Level)" if c.get("adjusted") else
                                    "validated" if Lc else "as logged"),
                         "cleaned at": c["at"], "clean shapefile": os.path.basename(c["zip"])})
        T4 = pd.DataFrame(rows)
        if not any(c.get("kind") != "a3" for c in ss.cleaned.values()):
            T4 = T4.drop(columns=["monitor vs grower (%)", "yields"])
        elif T4["monitor vs grower (%)"].isna().all():
            T4 = T4.drop(columns=["monitor vs grower (%)"])
        if T4["clipped (S1)"].isna().all():
            T4 = T4.drop(columns=["clipped (S1)"])
        st.dataframe(T4, hide_index=True,
                     column_config={"removed (%)": st.column_config.NumberColumn(format="%.2f"),
                                    "monitor vs grower (%)": st.column_config.NumberColumn(format="%+.2f"),
                                    "clipped (S1)": st.column_config.NumberColumn(format="%d")})
        zp = all_clean_zip()
        if zp and len(ss.cleaned) > 1:
            download(f"All {len(ss.cleaned)} clean shapefiles (.zip)", zp, "application/zip", key="dl_all",
                     primary=True, icon=":material/folder_zip:")
        for t, c in ss.cleaned.items():
            st.markdown(f"**{t}**")
            with st.container(horizontal=True):
                download("Clean shapefile (.zip)", c["zip"], "application/zip", key=f"dl_clean_{t}", primary=True,
                         icon=":material/cloud_download:")
                download("Flagged points (.zip)", c.get("flagged_zip"), "application/zip", key=f"dl_flag_{t}")
                download("Report (PDF)", c.get("report_pdf"), "application/pdf", key=f"dl_pdf_{t}",
                         icon=":material/picture_as_pdf:")
                download("Cleaning record (JSON)", c.get("json"), "application/json", key=f"dl_json_{t}",
                         icon=":material/data_object:")
        st.caption("Clean shapefile = the kept readings with every attribute of the file, inside the field boundary "
                   "when one was given. A harvest file is written as SMS exports it after Optimize Swath Widths (the "
                   "narrowed readings carry their new width and scaled per-area values; Wdth_Raw and Swath_Scl added; "
                   "with the yields adjusted, also Yld_Level, the dry yield leveled to the grower's weight). Removed % "
                   "= of the readings inside the boundary. Flagged = every reading with Keep and the step that removed "
                   "it (Rem_By). Report = the steps, the limits, the statistics and the maps (PDF). The files are also "
                   "in the work folder: " + os.path.join(ss.workdir or "", "clean_shapefiles") + ".")
