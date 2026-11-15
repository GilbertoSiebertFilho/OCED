# -*- coding: utf-8 -*-
"""OCED — Olds College Extract Data: the data of combines, planters and sprayers -> maps of every attribute -> the
3-sigma cleaning (with the clip to the field boundary; for a harvest also the grower's data) -> clean point shapefiles
and reports.

    python -m streamlit run app/oced.py --server.port 8502      (or double-click run_oced.bat)

Four steps on one page:

  1 Raw data: upload the files or type a file or folder on this computer. Combines: a raw monitor dataset (a
    zipped Case IH / New Holland card, a John Deere JD-Data folder, the files of a GreenStar 3 card, the TASKDATA
    sets of ISOXML harvest task data) lists its units
    (tasks / machines / loads), and the chosen units are extracted as ONE POINT SHAPEFILE PER FIELD, SEASON AND CROP
    (engine.run.decode on each group); a yield point export (or its .kml / .kmz) is imported as SMS's generic import
    of a point file holds it (Import as SMS below: every reading kept, its dry yield computed again from its wet
    mass when its crop names a product; else the file's own yields: said in its import note and in step 2 when it
    carries its own dry yield and dry mass, as SMS's exports do, with a warning when it does not). Planters and
    sprayers: the as-applied point export (a shapefile); any other point shapefile of a machine too. What a point
    file is (harvest, seeding, application, other points) is read from its columns (engine.clean.applied3s.
    detect_operation). Step 1 shows the file's default import only (SMS's, no import setting here): its import line
    with a badge, its strip of cards and its map (one button per attribute colours the strips the header swept over
    the satellite image, or the points; the legend, the statistics and the histogram beside it; the field boundary,
    when given, drawn on it), then the details in compact expanders (the header width as logged, the import record,
    the decoder's report, the attributes, the first records, the extracted points).
  2 Import settings: the switch 'Use SMS's default settings' (on: the data is step 1's). Off: the import settings of
    the file, editable, with Apply (this file, or every harvest file on its own SMS default), or no import as SMS
    ('None': an export as written, raw data decoded again as the monitor logged it); applied, step 2 shows its own
    strip of cards (against step 1) and map (on step 1's colour scale). Back on: back to the default, asked first in a
    dialog when the file has a cleaning (it is set aside). Planter and sprayer files have no import settings.
  3 Cleaning. A harvest file: the SMS 3-sigma sequence of Ag Leader SMS Advanced (engine.run.clean, method
    sms3sigma): S0 import check, S1 Clip To Field Boundary, S2 Optimize Swath Widths (once; 2 or 3 passes repeat
    an SMS chain where Clip + Optimize Swath Widths was added that many times), S3 moisture, S4 speed (the
    order of the filters is a setting: speed then moisture, the earlier order of the SMS sequence), S5 dry yield
    (mean +/- k SD on the points still alive, one mean and SD per combine by default, another yield pass while the SD
    falls by more than 25 %); with several combines, the combine factor when the user switches it on (Yld_Harm); the
    grower's data (total weight with its unit and basis, the grain moisture, the bushel weight) VALIDATE the yields
    (monitor total against the grower's on the same basis, compared as a mass in the file's bushels, L = grower /
    monitor, a verdict; nothing in the clean file changes) or also ADJUST them (Yld_Level = the dry yield x the combine
    factor x L in the clean file). Any other file (planter, sprayer, other points):
    the same 3-sigma rule on the attributes chosen (engine.clean.applied3s: S0 import check with the minimum of the
    main attribute, S1 clip, one 3-sigma step per attribute, the speed first, the main one repeated while its SD
    falls). Each file keeps its own boundary (.zip / .shp / .geojson / .gpkg / .kml / .kmz; a file of several fields
    asks which one) and its own settings. One file or every file. On screen: the import the cleaning starts from
    (with S0's minimum) and the sequence in one line each, the settings (folded into one line once the file is
    cleaned; the grower's weight folded while empty), then the strip of the result, the clean map under it (six
    attributes on pills and the others under 'More', the statistics and the histogram at its side; a corrected yield
    one pill away, compared with the clean map) and the details in tabs (yield path, steps, limits, removed points,
    grower's data, combines). The maps of steps 1 and 2 fold once the file is cleaned (a click opens them again).
  4 Clean files and reports: the clean shapefile of each file (the kept points with every attribute), all of
    them in one zip, the flagged points (every point with Keep and the step that removed it, Rem_By), the cleaning
    report (PDF) and the cleaning record (JSON). A clean file also comes as a shapefile for DIFM (engine/difm.py: a
    harvest's readings in the layout of an SMS shapefile export, <tag>_sms3s_clean_DIFM.zip, a planter / sprayer
    file's with its own columns and its dates as dBASE dates, <tag>_3s_clean_DIFM.zip, in clean_shapefiles/; written
    with the cleaning or, for a work cleaned before, when step 4 shows it; none for a cleaning to clean again). Its
    numbers have 6 decimals; a field the clean file does not hold (an Operations Center export: Yld_Mass_D,
    Yld_Vol_We, Duration_s, Field, Dataset, Product) is filled only with what follows exactly from the clean file and
    the file's import (difm_basis), else left empty: readings without Yld_Mass_D or Yld_Vol_Dr, and a zip over
    10 MB, are warnings of step 4. When
    the cleaning adjusted the yield (a combine factor applied, the grower's weight used to adjust), step 4 asks which
    yield the harvest's file carries: 3-sigma only (the monitor's, <tag>_sms3s_clean_DIFM.zip) or the adjusted one
    (the default, <tag>_sms3s_clean_adjusted_DIFM.zip); the cleaning record says which was generated. A
    clean harvest can also be saved in the same raw format it was imported from (the monitor's own card or logs, a
    new TASKDATA set for ISOXML task data: engine/formats/native_write.py options / write), with ISOXML TASKDATA as
    the fallback (the only format besides the
    shapefile for a point export); every such output is marked not yet tested in SMS. They are written to native/<tag>/
    in the work folder (never inside the input), each with a small record (native/<tag>/<format>.json) that brings its
    result back when the work is opened again. On screen: 'What each file is' folded at the top, the table of the
    cleaned files (with the import each cleaning started from), then per file its downloads, one line on the file for
    DIFM (the rest under 'About the file for DIFM') and the box to save the clean file in the monitor's format.

Import as SMS: every harvest file opens with SMS's default import (its Processing Settings untouched), kept as the
file's default import beside the active one (import_default / import_mode); the import settings of each file (step 2)
apply own values to that file (or to every harvest file), go back to the default, or use the file with no import as
SMS (an export as written, a raw file as the monitor logged it). The values SMS gives the source when a setting is
left empty (engine/sms_import.py resolve): John Deere files (GreenStar 3 cards, Gen4 .jdl logs) the crop
definition of the file, min 5 / max 10,000 bu/ac; ISOXML task data what SMS gives the task's crop, min 5 / max 10,000;
Case IH / New Holland cards SMS's product table by the crop name; point exports (shapefiles, .kml / .kmz, Operations
Center and SMS exports) as SMS's generic import of a point file: every reading kept (min 0, no max), the weight to
volume and dry moisture of SMS's product table; expand dry moisture off. A value typed by the user wins; the panels
say where each value came from ('from the file', 'SMS product table', 'SMS's generic import of a point file', 'you'
...). A work saved by an older version that imported a point export with other values says so when it is opened.

Work folder: workspace/<YYYYmmdd-HHMMSS>_<name>/ (OCED_WORKSPACE moves it), with uploads/ (the files uploaded; an
uploaded zip is removed once unpacked) or input/ (what was unpacked), decoded/ (the extracted files: <tag>_decoded.shp,
<tag>_decode_report.json and <tag>_imported.shp, the file as SMS imports it), imported/ (point exports as SMS imports
them), <tag>_imported_custom.* (an import with the user's settings), <tag>_imported_default.* (SMS's default import
built again for a work of an earlier version), as_logged/decoded/ (a raw file decoded again as the monitor logged it),
sections/ (Operations Center section exports collapsed to one reading per second), boundary/<tag>/ (the boundary
files uploaded), clean/<tag>/ (the cleaning outputs), clean_shapefiles/ (what step 4 hands out), superseded/ (the
outputs of a cleaning that an import or an extraction made obsolete), native/<tag>/ (the clean harvest in the
monitor's format) and oced_work.json (the saved work). An input left out when the data was opened (a damaged zip
among the zips of a zip or of a folder given; engine.run.open_input) is warned about in step 1 and named, with the
reason, in every decode report, cleaning record and report of the work and in the saved work, which says it again
when it is opened. Every value
on the maps is a reading's own value: nothing is interpolated or smoothed.
"""
import base64
import copy
import dataclasses
import datetime as dt
import functools
import hashlib
import html
import json
import ntpath
import os
import re
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


@st.cache_resource(show_spinner=False)
def server_token() -> str:
    """What this start of the app's server writes into its cleaning locks: the process id and when it started, so
    that a lock left by a server that was closed (a process id used again later included) is known as stale."""
    return f"{os.getpid()} {dt.datetime.now().strftime('%Y%m%d%H%M%S%f')}"


with _engine_lock():
    _drop_stale_engine()
    from engine import run as er  # noqa: E402
    from engine import works as ew  # noqa: E402
    from engine import sms_import as si  # noqa: E402
    from engine.clean import applied3s as a3  # noqa: E402
    from engine.clean import sms3sigma as sms  # noqa: E402
    from engine.clean import yield_clean as yc  # noqa: E402
    from engine.formats import common, detect  # noqa: E402
    from engine.formats import native_write as nw  # noqa: E402
    from engine import difm as ed  # noqa: E402
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
    "Yld_Harm": ("Dry yield x the combine factor", "bu/ac", "RdYlGn"),
    "Session": ("Harvest session", "", "cat"), "In_AOI": ("Inside the boundary", "", "cat"),
    "Rt_Apd_Ct_": ("Applied rate (count)", "seeds/ac", "RdYlGn"), "Rt_Apd_Ms_": ("Applied rate (mass)", "lb/ac", "RdYlGn"),
    "Rt_Apd_Vol": ("Applied rate (volume)", "gal/ac", "RdYlGn"), "Rt_Tgt_Ct_": ("Target rate (count)", "seeds/ac", "RdYlGn"),
    "Rt_Tgt_Ms_": ("Target rate (mass)", "lb/ac", "RdYlGn"), "Rt_Tgt_Vol": ("Target rate (volume)", "gal/ac", "RdYlGn"),
}
LEVEL_COLUMNS = ("Yld_Level", "Yld_Lvl_Sy")      # what "adjust the yields" adds; "validate only" leaves them out
BOUNDARY_TYPES = ["zip", "shp", "shx", "dbf", "prj", "cpg", "geojson", "json", "gpkg", "kml", "kmz"]
OUTLINE_RGB = [0, 229, 255]                      # the field boundary on the satellite image (cyan)
TICKET_UNIT_LABEL = {"lb": "lb", "kg": "kg", "bu": "bu", "t": "t (1,000 kg)", "bu/ac": "bu/ac"}
GROWER_USE = {"validate": "Validate only", "adjust": "Validate and adjust the yields"}
GROWER_BUSHELS = {"given": "As given (trade bushels)", "grower": "Bushels of the bushel weight above"}
BUSHEL_FROM_LABEL = {"file": "The file's (wet mass / wet volume)", "declared": "The declared one (import / crop)"}
# the SMS 3-sigma panel: the mean and SD groups, the scope of Optimize Swath Widths, the lateral offset check
GROUP_LABEL = {"auto": "auto: one mean and SD per combine (one for the field with one combine)",
               "task": "task: each dataset / combine-day",
               "machine": "combine", "field": "field (all readings)"}
SWATH_SCOPE_LABEL = {"operation": "all combines (one SMS instance)",
                     "machine": "each combine alone (one SMS instance per combine)"}
SWATH_BIAS_LABEL = {"warn": "warn", "auto": "auto (move back before the swath step)", "off": "off"}
# the combine factor (OCCD's, engine/clean/machines.py combine_factors): how it is computed
CF_METHODS = ["auto", "cells", "track", "point", "machine"]
CF_LABEL = {"auto": "Auto (recommended)", "cells": "Paired cells", "track": "Track × track", "point": "Point × point",
            "machine": "Machine × machine"}
CF_HELP = {
    "auto": "Auto: the paired cells where the combines met on interleaved or mixed passes (the most conservative "
            "method); no factor where each combine cut its own block or they never met - then only the grower's weight "
            "levels the field.",
    "cells": "Paired cells: 30 m and 50 m squares where both combines cut neighbouring passes, proven at both sizes "
             "and in both halves of the field. Green on interleaved and mixed passes, yellow in blocks.",
    "track": "Track × track: every pair of adjacent passes (one of each combine) compares its yield along the common "
             "edge, all pairs together. Green on interleaved and mixed passes, yellow in blocks.",
    "point": "Point × point: every point against the nearest point of the other combine. Finds a real difference "
             "more often on interleaved passes but is noisier: green interleaved, yellow mixed, red in blocks.",
    "machine": "Machine × machine: the whole-field mean of each combine (Maldaner et al. 2016; the LSU AgCenter "
               "normalisation). Right only when the combines alternated passes: green interleaved, yellow mixed, red "
               "in blocks, where it mixes the machine with the ground each combine cut."}
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
STEP_COLORS = {"kept": "#00B373", "S0": "#90A4AE", "S1": "#B0BEC5", "S2": "#B388FF", "S3": "#1565C0",
               "S4": "#00B4D8", "S5": "#FF5252"}
# the moisture and speed filters keep their colour whatever their place (S3 / S4 follow the order of the filters)
ATTR_COLORS = {"moisture": "#1565C0", "speed": "#00B4D8", "dry yield": "#FF5252"}

st.set_page_config(page_title=NAME, page_icon=brand.page_icon(), layout="wide")
if os.path.exists(brand.LOGO_H):
    st.logo(brand.LOGO_H, icon_image=brand.LOGO_SHIELD if os.path.exists(brand.LOGO_SHIELD) else None, size="large")
brand.inject()                       # the page's CSS, all of it in brand.py (light / dark pairs)

ss = st.session_state
for k, v in {"workdir": None, "cands": None, "open_error": None, "open_exc": None, "open_request": None,
             "open_log": [], "units": {}, "datasets": {}, "cleaned": {}, "active": None, "boundary": {},
             "grower": {}, "a3set": {}, "smsset": None, "input_label": None, "work_saved": None, "cfset": {},
             "work_saved_at": None, "work_msg": None, "work_nonce": 0, "last_cand": None, "open_fail_log": [],
             "last_open_path": None, "left_out": [], "away": {}, "away_order": []}.items():
    ss.setdefault(k, v)


# ------------------------------------------------------------------------------------------------ helpers
def key_of(s: str) -> str:
    return hashlib.md5(str(s).encode("utf-8")).hexdigest()[:8]


def file_key(tag: str) -> str:
    """The key of the widgets of one file of the work on screen. Every new work (Open, Start over, a saved work
    opened) gets new keys, so a file of another work with the same name never starts with the values typed for this
    one, neither on the server nor in the browser."""
    return key_of(f"{int(ss.get('work_nonce') or 0)}|{tag}")


def mtime(p: str) -> float:
    return os.path.getmtime(p) if p and os.path.exists(p) else 0.0


def content_sig(shp: str | None) -> str | None:
    """The md5 of a shapefile's .shp and .dbf (None when it is not there): the same file whatever its time on disk (a
    work copied or unzipped without its files' times) and whatever day it was written (the date of the last update
    in the .dbf header, bytes 1-3, is left out: the same import written again on another day is the same import)."""
    if not shp or not os.path.exists(str(shp)):
        return None
    h = hashlib.md5()
    for e in (".shp", ".dbf"):
        p = os.path.splitext(str(shp))[0] + e
        try:
            with open(p, "rb") as fh:
                if e == ".dbf":
                    h.update(fh.read(1))                 # the version byte; the date after it is left out
                    fh.read(3)
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
        except OSError:
            return None
    return h.hexdigest()


def stamp(shp: str | None) -> dict:
    """{mtime, sig} of the file of an import (a default import's block keeps them: default_needs_build)."""
    return {"mtime": mtime(shp), "sig": content_sig(shp)}


# the import settings of a value: where the value came from (engine/sms_import.py resolve, R["sources"])
SOURCE_LABEL = {"you": "you", "file": "from the file", "SMS product table": "SMS product table",
                "SMS for this John Deere crop": "SMS's value for this John Deere crop, not the file's own",
                "SMS for John Deere files": "SMS for John Deere files", "crop table": "crop table",
                "SMS for this crop in ISOXML task data": "SMS's value for this crop in ISOXML task data, not the "
                                                         "log's own",
                "SMS for ISOXML task data": "SMS for ISOXML task data",
                "SMS for ISOXML task data without a product": "SMS's value for an ISOXML dataset without a product",
                "SMS generic import of point files": "SMS's generic import of a point file, which keeps every reading",
                "OCED default": "OCED default"}
WORK_PER_FILE_KEYS = ("cand_idx", "units_", "attr_", "draw_", "bnd_", "gw_", "a3_", "cf_", "fi_", "cnh_tot_", "cal_",
                      "tb_", "fd_", "md_", "al_", "pts_", "isl_", "extract_", "src_collapse_", "set_box_", "gw_box_",
                      "src_box_", "map_box_")
PATH_LIMIT = 250                 # the longest path written in a work folder (Windows opens a file up to 259)
LONGEST_OUTPUT = "_sms3s_cleaning_report.pdf"     # the longest name the cleaning writes after the tag
TAG_FLOOR = 12                   # the fewest characters tag_budget gives a tag, however deep the work folder
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
RAW_FILE_EXTS = (".jdl", ".fdd", ".fdl", ".fdr", ".tso", ".tlo", ".tlh", ".vy1")


def tag_budget(workdir: str | None = None) -> int:
    """The most characters a file's tag may have in this work folder: the cleaning writes
    clean/<tag>/<tag>_sms3s_cleaning_report.pdf, which must stay within PATH_LIMIT (12 to 60 characters), and the
    ISOXML set of step 4, native/<tag>/isoxml_<stamp>/TASKDATA/LINKLIST.XML (a card written in the monitor's format
    also holds the card's own tree: write_native checks its depth before writing)."""
    return tag_budget_for(len(os.path.abspath(workdir or ss.get("workdir") or WORKSPACE)))


def tag_budget_for(n: int) -> int:
    """tag_budget of a work folder of n characters. n + tag_budget_for(n) never falls as n grows."""
    room = PATH_LIMIT - n - len(os.sep + "clean" + os.sep + os.sep + LONGEST_OUTPUT)
    room_iso = PATH_LIMIT - n - len(os.sep + "native" + os.sep + os.sep + "isoxml") - 37
    return int(max(TAG_FLOOR, min(60, room // 2, room_iso)))


def fit_tag(tag: str, budget: int | None = None) -> str:
    """A tag shortened to the path budget of the work folder (tag_budget)."""
    b = budget or tag_budget()
    t = yc.sanitise_tag(str(tag or ""))
    return (t[:b].rstrip("_-") or t[:b]) or "file"


def free_tag(base: str, src: str | None = None, also=()) -> str:
    """A tag no other file of the work (nor any of `also`) has, ignoring case (tags become file and folder names, and
    Windows does not tell 'Harvest' from 'harvest'): the base tag; else the base with the folder of src (the folder
    itself for a raw dataset's folder, the parent folder of a file); else base_2, base_3 ..."""
    taken = {str(t).casefold() for t in list(ss.datasets) + list(ss.get("away") or {}) + list(also)}
    b = tag_budget()
    t = fit_tag(base, b)
    if t.casefold() not in taken:
        return t
    par = ""
    if src:
        par = yc.sanitise_tag(os.path.basename(os.path.normpath(src)) if os.path.isdir(src)
                              else os.path.basename(os.path.dirname(src)))
    if par:
        t2 = fit_tag(f"{fit_tag(base, max(6, b - len(par[:20]) - 1))}_{par[:20]}", b)
        if t2.casefold() not in taken:
            return t2
    i = 2
    while f"{fit_tag(t, b - 3)}_{i}".casefold() in taken:
        i += 1
    return f"{fit_tag(t, b - 3)}_{i}"


def src_of(cand: dict) -> str:
    """The file a point-export candidate comes from (the export itself, before a section export is collapsed)."""
    return os.path.normcase(os.path.abspath(cand.get("source_path") or cand["path"]))


def cand_labels(cands) -> list:
    """The labels of the candidates of an input. Exports whose file names (or tags) are the same name their folder
    too, so that the list tells them apart."""
    keys = []
    for c in cands:
        if c.get("kind") == "export":
            p = c.get("source_path") or c["path"]
            keys.append(yc.sanitise_tag(os.path.splitext(os.path.basename(p))[0]).casefold())
        else:
            keys.append(("raw", str(c.get("label") or "")))
    out = []
    for c, k in zip(cands, keys):
        lab = str(c.get("label") or "")
        group = [x for x, kx in zip(cands, keys) if k and kx == k]
        if len(group) > 1 and c.get("kind") != "export":         # two raw datasets that read alike: their folders
            roots = [os.path.dirname(os.path.normpath(x["probe"].root)) for x in group]
            try:
                common_ = os.path.commonpath(roots)
            except ValueError:
                common_ = ""
            rel = os.path.relpath(os.path.dirname(os.path.normpath(c["probe"].root)), common_) if common_ else ""
            out.append(lab + (f" · in {rel}" if rel not in ("", ".") else f" · {c['probe'].root}"))
            continue
        if len(group) > 1:
            p = c.get("source_path") or c["path"]
            dirs = [os.path.dirname(x.get("source_path") or x["path"]) for x in group]
            try:
                common_ = os.path.commonpath(dirs)
            except ValueError:
                common_ = ""
            rel = os.path.relpath(os.path.dirname(p), common_) if common_ else os.path.dirname(p)
            if rel not in (".", ""):
                name = os.path.basename(p)
                lab = (lab.replace(name, os.path.join(rel, name), 1) if name in lab else f"{lab} · in {rel}")
        out.append(lab)
    return out


CAND_LINE_MAX = 150


def cand_line(label: str) -> str:
    """Step 1's line of the dataset opened: its label, or, when longer than CAND_LINE_MAX, its format and first clause
    ('<format> · 53 log file(s), 1 machine(s) (...)'); the rest (field, crop, farm) is in the units table and the
    Unpacking log."""
    lab = str(label or "")
    if len(lab) <= CAND_LINE_MAX:
        return lab
    head, sep, rest = lab.partition(" · ")
    s = head + sep + rest.split("; ")[0]
    return s if len(s) <= CAND_LINE_MAX else s[:CAND_LINE_MAX - 2].rsplit(" ", 1)[0] + " …"


def totals_only_of(cand: dict, chosen) -> list:
    """The Case IH / New Holland tasks of the chosen units' fields and seasons whose totals are on the card without
    their log (engine/formats/cnh_cn1.totals_only_tasks), read once per card and choice of units."""
    ids = tuple(sorted(str(u.id) for u in chosen or []))
    if not ids:
        return []
    k = ("totals_only", os.path.normcase(cand["probe"].root), ids)
    cache = ss.setdefault("_totals_only", {})
    if k not in cache:
        try:
            from engine.formats import cnh_cn1
            cache[k] = list(cnh_cn1.totals_only_tasks(cand["probe"].root, list(ids)) or [])
        except Exception:                                # an older decoder, or a card it cannot list: no option
            cache[k] = []
    return cache[k]


def same_harvest_warning(cands):
    """Under the list of datasets: two raw datasets of one format whose units name the same field, season and crop
    (one combine's logs zipped and the other's loose, say) are two parts of one harvest."""
    by = {}
    for c in cands:
        if c.get("kind") == "raw":
            by.setdefault(c["decoder"], []).append(c)
    for fid, cs in by.items():
        if len(cs) < 2:
            continue
        seen = {}
        for c in cs:
            root = c["probe"].root
            if root not in ss.units:
                try:
                    ss.units[root] = er.list_units(c)
                except Exception:                        # a listing problem is shown when the dataset is chosen
                    ss.units[root] = []
            for u in ss.units[root]:
                seen.setdefault((u.field or "(no field)", u.year, str(u.crop or "").strip().lower()), set()).add(root)
        dup = sorted((k for k, v in seen.items() if len(v) > 1), key=lambda k: (k[0], k[1] or 0, k[2]))
        if dup:
            st.warning(f"{len(cs)} datasets of this input ({cs[0]['probe'].label}) hold units of the same field, "
                       "season and crop: " + "; ".join(f"{f} {y or ''} {c or ''}".strip() for f, y, c in dup[:4])
                       + (" ..." if len(dup) > 4 else "") + ". They may be two parts of one harvest. Each one "
                       "extracts to its own file (the second one with a suffix); to clean them as one field, give "
                       "their files together in one folder.", icon=":material/warning:")


def _forget_work(clear_inputs: bool = False):
    """The session forgets the work on screen: its files, cleanings, boundaries, grower's data and settings, and the
    widgets of its files; the next work gets new widget keys (work_nonce)."""
    for k in ("cands", "open_error", "open_exc", "open_request", "active", "last_cand"):
        ss[k] = None
    ss.open_log, ss.units, ss.datasets, ss.cleaned, ss.boundary, ss.grower, ss.a3set = [], {}, {}, {}, {}, {}, {}
    ss.cfset, ss.open_fail_log = {}, []
    ss.away, ss.away_order = {}, []   # files of the work set aside while their points are away (restore_work)
    ss.left_out = []                 # the inputs left out when this work's data was opened (a damaged zip)
    ss.workdir = None
    ss.input_label = ss.work_saved = ss.work_saved_at = ss.work_msg = None
    for k in ("work_name", "work_name_for", "active_pick", "save_request", "default_failed"):
        ss.pop(k, None)
    prefixes = WORK_PER_FILE_KEYS + (("path_in", "uploads") if clear_inputs else ())
    for k in [k for k in ss if str(k).startswith(prefixes)]:
        ss.pop(k, None)
    ss.work_nonce = int(ss.get("work_nonce") or 0) + 1


def drop_unused_workdir(wd: str | None, keep_recent_s: float = 0.0) -> bool:
    """Removes a work folder of the workspace that nothing can open again (no saved work, nothing extracted, imported
    or cleaned: ew.load_work is None and imported/, decoded/, clean/ and sections/ are empty), e.g. an input opened and
    left before anything was made of it. keep_recent_s: a folder made less than that many seconds ago stays (another
    tab may be opening it). Returns True when it was removed."""
    try:
        if not wd or not os.path.isdir(wd):
            return False
        if os.path.normcase(os.path.dirname(os.path.abspath(wd))) != os.path.normcase(os.path.abspath(WORKSPACE)):
            return False
        if keep_recent_s and (dt.datetime.now().timestamp() - os.path.getmtime(wd)) < keep_recent_s:
            return False
        if ew.load_work(wd) is not None:
            return False
        for sub in ("imported", "decoded", "clean", "clean_shapefiles", "sections"):
            p = os.path.join(wd, sub)
            if os.path.isdir(p) and os.listdir(p):
                return False
        shutil.rmtree(wd, ignore_errors=True)
        return not os.path.exists(wd)
    except OSError:
        return False


def start_over():
    drop_unused_workdir(ss.get("workdir"))
    _forget_work(clear_inputs=True)
    # a file uploader keeps its files until it is created again: a new key empties the upload fields
    ss.up_nonce = int(ss.get("up_nonce") or 0) + 1


def request_open(source):
    ss.open_request = source


def upload_names(names: list, folder: str) -> list:
    """The names the uploaded files are written under in `folder`: their own, or, where folder + name would pass
    PATH_LIMIT, the stem cut to fit (the same cut for every part of a shapefile, so its .shp, .shx, .dbf and .prj stay
    together)."""
    out, cut = [], {}
    for n in names:
        stem, ext = os.path.splitext(n)
        room = PATH_LIMIT - len(os.path.join(folder, "")) - len(ext)
        if len(stem) > room and stem.lower() not in cut:
            s = stem[:max(8, room - 3)].rstrip(" ._-") or stem[:8]
            taken = {v.lower() for v in cut.values()} | {os.path.splitext(x)[0].lower() for x in names}
            i, s0 = 2, s
            while s.lower() in taken:
                s, i = f"{s0}_{i}", i + 1
            cut[stem.lower()] = s
        out.append(cut.get(stem.lower(), stem) + ext)
    return out


def _work_folder_name(kind: str, val) -> str:
    """The name part of a new work folder: the first zip, shapefile or KML of an upload (a loose log is called by a
    GUID or a serial number, which says nothing), the file or folder of a path; else a neutral 'upload' / 'data'."""
    if kind == "upload":
        for f in val:
            b, e = os.path.splitext(os.path.basename(f.name))
            if e.lower() in (".zip", ".shp", ".kml", ".kmz") and not _GUID.match(b):
                return b[:WORK_FOLDER_CHARS]
        return "upload"
    p = str(val).strip().strip('"').rstrip("\\/")
    b, e = os.path.splitext(os.path.basename(p))
    if (e.lower() in RAW_FILE_EXTS and os.path.isfile(p)) or _GUID.match(b) or not b:
        return "data"
    return b[:WORK_FOLDER_CHARS]


WORK_FOLDER_CHARS = 20           # of the input's name in a new work folder's name (the rest of the path is for the
                                 # files written below it; the work's name on screen comes from its files)


def do_open(source) -> bool:
    """source: ('upload', [UploadedFile]) or ('path', str). Opens the input into a new work folder and detects what
    it holds (engine.run.open_input). The work on screen is replaced only when something usable was found: a path
    that does not exist, an input that cannot be unpacked or in which nothing is recognised leaves it as it is (the
    error is shown) and removes the new folder. The outgoing work is saved first (its files on screen), an outgoing
    folder with nothing in it is removed. Returns True when the input was opened."""
    kind, val = source
    log, wd, cands, err, exc = [], None, None, None, None
    ss.open_error = ss.open_exc = None
    try:
        if kind == "upload":
            names = [os.path.basename(f.name) for f in val]
            low = [n.lower() for n in names]
            dup = sorted({n for n in names if low.count(n.lower()) > 1})
            if dup:
                raise ValueError(f"two uploaded files are named {dup[0]}: OCED cannot tell which set each part "
                                 "belongs to. Zip each set (one zip per folder), or open the folder by its path.")
            wd = er.new_workdir(WORKSPACE, _work_folder_name(kind, val))
            up = os.path.join(wd, "uploads")
            os.makedirs(up, exist_ok=True)
            short = upload_names(names, up)
            for f, n in zip(val, short):
                with open(os.path.join(up, n), "wb") as fh:
                    fh.write(f.getbuffer())
            if short != names:
                log.append("the names of the uploaded files were shortened to fit Windows' path limit under the work "
                           "folder: " + ", ".join(f"{a} -> {b}" for a, b in zip(names, short) if a != b))
            paths, label = [up], ", ".join(names)
        else:
            p = str(val).strip().strip('"')
            if not p or not os.path.exists(p):
                raise ValueError(f"not found on this computer: {p or '(empty)'}")
            wd = er.new_workdir(WORKSPACE, _work_folder_name(kind, p))
            paths, label = [p], p
        cands = er.open_input(paths, wd, log=log.append)
    except ValueError as e:
        err = str(e)
    except Exception as e:                               # shown with its traceback, never swallowed
        err, exc = f"Opening failed ({_error_reason(e)})", e
    if err is None and not cands:
        notes = list(getattr(cands, "notes", None) or [])
        msg = str(getattr(cands, "message", "") or "Nothing that OCED can read was found.")
        head, _, rest = msg.partition("\n")
        names = [os.path.basename(f.name) for f in val] if kind == "upload" else [str(val)]
        arch = [n for n in names if n.lower().endswith((".7z", ".rar", ".tar", ".tar.gz", ".tgz", ".gz", ".bz2",
                                                        ".xz"))]
        why = [f"{n}: this archive type is not unpacked; make a .zip of it or give the unpacked folder" for n in arch]
        why += notes[:max(0, 5 - len(why))]
        said = head.startswith("ISOXML task data was found")    # the message names what was found and why already
        if not why and not said:
            why = ["the input holds no file OCED reads (an empty zip or folder?)"]
        more = len(notes) + len(arch) - len(why)
        err = (head + (" Why: " + "; ".join(why) if why else "")
               + (f"; ... and {more} more (Details below)" if more > 0 else "") + ("\n" + rest if rest else ""))
    if err is not None:
        if wd:
            shutil.rmtree(wd, ignore_errors=True)        # the folder this call made: nothing in it to keep
        ss.open_error, ss.open_exc, ss.open_fail_log = err, exc, log
        return False
    if ss.get("workdir") and ss.datasets:
        save_current(quiet=True)                         # the outgoing work, as it is on screen
    elif ss.get("workdir"):
        drop_unused_workdir(ss.workdir)
    _forget_work(clear_inputs=False)
    ss.workdir, ss.cands, ss.open_log, ss.input_label = wd, cands, log, label
    ss.left_out = [str(w) for w in (getattr(cands, "left_out", None) or [])]   # kept with the work (work_record)
    if kind == "upload":
        for n in os.listdir(os.path.join(wd, "uploads")):    # an uploaded zip is unpacked into input/: its copy goes
            if n.lower().endswith(".zip"):
                try:
                    os.remove(os.path.join(wd, "uploads", n))
                except OSError:
                    pass
    else:
        ss.last_open_path = label
    return True


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
    s = f"{x:,.2f}" if a >= 0.1 or a == 0 else f"{x:.3g}"   # two decimals, never one
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
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    ok = np.isfinite(lon) & np.isfinite(lat)
    if not ok.any():                                 # nothing with a position: no map (never a crash)
        st.caption("No reading with a position to map.")
        return
    lon, lat = lon[ok], lat[ok]
    lo0, lo1 = float(np.nanmin(lon)), float(np.nanmax(lon))
    la0, la1 = float(np.nanmin(lat)), float(np.nanmax(lat))
    coslat = np.cos(np.radians((la0 + la1) / 2))
    z_w = np.log2(0.9 * width * 360.0 / (512.0 * max(lo1 - lo0, 1e-6)))
    z_h = np.log2(0.9 * height * 360.0 * coslat / (512.0 * max(la1 - la0, 1e-6)))
    view = pdk.ViewState(latitude=(la0 + la1) / 2, longitude=(lo0 + lo1) / 2,
                         zoom=float(np.clip(min(z_w, z_h), 9, 17)))
    st.pydeck_chart(_CompactDeck(layers=layers, initial_view_state=view, map_style=SATELLITE_STYLE_URL,
                                 tooltip=tooltip), height=height)


def legend(kind, cmap, lo, hi, unit, t0=None, cats=None, counts=None, note: str = ""):
    """Under the map: the colour bar from lo to hi (note: what the scale is, e.g. step 1's), or one chip per
    category with its points."""
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
            f'<span>{html.escape(fmt_value(hi, unit, kind, t0))}</span>'
            + (f'<span>· {html.escape(note)}</span>' if note else "") + '</div>')


def stats_of(v: np.ndarray) -> dict:
    f = v[np.isfinite(v)]
    if not len(f):
        return {"n": int(len(v)), "valid": 0}
    m, sd = float(f.mean()), float(f.std(ddof=1)) if len(f) > 1 else 0.0
    return {"n": int(len(v)), "valid": int(len(f)), "min": float(f.min()), "p2": float(np.percentile(f, 2)),
            "mean": m, "median": float(np.median(f)), "p98": float(np.percentile(f, 98)), "max": float(f.max()),
            "sd": sd, "cv": (100 * sd / m if m else None)}


@st.cache_data(max_entries=12, show_spinner=False)
def attribute_table_of(path: str, mt: float) -> pd.DataFrame:
    """attribute_table of a point file, computed once per file and modification time (not on every click)."""
    return attribute_table(read_points(path, mt))


@st.cache_data(max_entries=12, show_spinner=False)
def operation_of(path: str, mt: float) -> dict:
    """What a point file is (engine.clean.applied3s.detect_operation over every record), once per file and
    modification time."""
    df = read_points(path, mt)
    return a3.detect_operation([c for c in df.columns if c not in ("lon", "lat")], df)


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


def corrected_column(C: dict, cols, ycol) -> tuple[str, str] | None:
    """The column of the clean file that carries the correction factors, and how it was made: Yld_Level (or the
    symmetric Yld_Lvl_Sy) = the clean dry yield x the combine factor x L when the yields were adjusted to the grower's
    weight; Yld_Harm = the clean dry yield x the combine factor when only that was applied. None without a factor."""
    R = C["R"]
    L = R.get("level") or {}
    MF = {str(k): float(v) for k, v in ((R.get("machines") or {}).get("factor_applied") or {}).items()}
    harm_on = "Yld_Harm" in cols and any(abs(v - 1) > 1e-9 for v in MF.values())
    fac = ", ".join((f"{m} x {v:.4f}" if abs(v - 1) > 1e-9 else f"{m} x 1 (reference)") for m, v in MF.items())
    fcol = R.get("yield_column_for_difm")
    Lf = L.get("factor_final", L.get("factor"))
    if C.get("adjusted") and fcol in cols and fcol not in (ycol, "Yld_Harm") and Lf is not None:
        base = "the clean symmetric dry yield (Yld_Dry_Sy)" if fcol == "Yld_Lvl_Sy" else "the clean dry yield"
        given = er.ticket_label({"value": L.get("ticket_value"), "unit": L.get("ticket_unit")}) if L.get("ticket_value") else ""
        return fcol, (f"{fcol} = {base}" + (f" x the combine factor ({fac})" if harm_on else "")
                      + f" x L {float(Lf):.4f} (the grower's {given}" + (f" over {float(L['ticket_area_ac']):,.2f} ac"
                                                                        if L.get("ticket_area_ac") else "")
                      + "). Its own colour scale; the column at the right of the statistics is the change against the "
                        "clean map.")
    if harm_on:
        return "Yld_Harm", (f"Yld_Harm = the clean dry yield x the combine factor ({fac}). Its own colour scale; the "
                            "column at the right of the statistics is the change against the clean map.")
    return None


TOP_N = 6                        # the attributes on the pills of a map; the others are under 'More'
_STD_COL = {"yield": "Yld_Vol_Dr", "moisture": "Moisture__", "speed_mph": "Speed_mph_", "width_ft": "Swth_Wdth_",
            "yield_wet": "Yld_Vol_We", "machine": "Machine", "dataset": "Dataset"}
DRAW_HELP = ("Strips: the ground the header swept by each reading. Points: one dot per reading (used when the strips "
             "cannot be built).")


def top_attrs(names: list, op: dict | None = None, first=(), n: int = TOP_N) -> list:
    """The attributes on the pills of a map (the others are under 'More'): for a yield file the first n present of
    the dry yield, the columns in `first` (a corrected yield), Yld_Level, Yld_Harm, the moisture, speed, width, wet
    yield and machine / dataset; for a planter or sprayer file its rates, speed, width and machine; then the other
    attributes in their order until there are n."""
    det = yc.detect_columns(list(names))

    def c(k):
        return det.get(k) or _STD_COL.get(k)
    rates = [r for r in (op or {}).get("rates") or []]
    if c("yield") in names or not rates:
        pref = [c("yield"), *first, "Yld_Level", "Yld_Harm", c("moisture"), c("speed_mph"), c("width_ft"),
                c("yield_wet"), c("machine"), c("dataset")]
    else:
        pref = [*first, *rates, (op or {}).get("speed") or c("speed_mph"), c("width_ft"),
                (op or {}).get("machine") or c("machine")]
    top = [x for x in dict.fromkeys(pref) if x and x in names][:n]
    return top + [x for x in names if x not in top][:max(n - len(top), 0)]


def _more_pick(key: str):
    """The 'More' select of a map: its choice goes onto the pills (as the attribute shown), the select empties."""
    v = ss.get(f"attr_more_{key}")
    if v:
        ss[f"attr_{key}"] = v
    ss[f"attr_more_{key}"] = None


def explorer(shp: str, key: str, height: int = 520, default: str | None = None, outline=None, extras: bool = True,
             scale_of: str | None = None, base_for: dict | None = None, labels: dict | None = None,
             col_help: dict | None = None, data: str | None = None):
    """The map of a point file coloured by the attribute chosen on the pills (six of them, the others under 'More',
    the way the readings are drawn at the right), with its legend under it and its statistics and histogram beside
    it. outline: the field boundary (rings of [lon, lat]) drawn over the strips; extras False: no attribute table and
    first records (the caller draws explorer_extras where it wants them); scale_of: another point file whose values
    of the same column give the colour scale (step 2's map on step 1's scale: the same colour is the same value);
    base_for: {column: base column}: while that column is shown, every statistic is also given as the change against
    the base column (the column "change vs the clean map"); labels: {column: pill label} (a corrected yield is
    'Final yield (Yld_Level)'); col_help: {column: the "?" of the side heading while it is shown}; data: which data
    the map shows, after the column in the side heading ('SMS default (step 1)', 'your settings (step 2)', 'clean
    (step 3)')."""
    if not shp or not os.path.exists(shp):
        st.error("The file is no longer on disk.", icon=":material/error:")
        return
    df = read_points(shp, mtime(shp))
    attrs = attributes(df)
    if not attrs:
        st.warning("This file holds no attribute to map.", icon=":material/warning:")
        return
    labels, col_help = dict(labels or {}), dict(col_help or {})
    names = [a[0] for a in attrs]
    info = {a[0]: a for a in attrs}
    akey = f"attr_{key}"
    if ss.get(akey) not in names:
        ss[akey] = default if default in names else names[0]
    top = top_attrs(names, operation_of(shp, mtime(shp)), first=[c for c in labels if c in names])
    shown = top + ([ss[akey]] if ss[akey] not in top else [])          # a pick from 'More' joins the pills
    rest = [c for c in names if c not in shown]

    def pill_text(c):
        return labels.get(c) or (info[c][1] + (f" ({info[c][2]})" if info[c][2] else ""))
    with st.container(key=f"attr_box_{key}"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            pick = st.pills("Attribute on the map", shown, selection_mode="single", required=True, key=akey,
                            format_func=pill_text, label_visibility="collapsed")
            if rest:
                st.selectbox("More attributes", rest, index=None, placeholder=f"More ({len(rest)})",
                             key=f"attr_more_{key}", format_func=pill_text, label_visibility="collapsed",
                             on_change=_more_pick, args=(key,), width=190)
            st.space("stretch")
            draw = st.segmented_control("Draw the readings as", ["strips", "points"], default="strips", required=True,
                                        key=f"draw_{key}", format_func={"strips": "Strips",
                                                                        "points": "Points"}.get,
                                        label_visibility="collapsed", help=DRAW_HELP)
    col = pick if pick in names else ss.get(akey) if ss.get(akey) in names else names[0]
    _, label, unit, cmap = info[col]
    label = labels.get(col) or label
    base_col = (base_for or {}).get(col)
    kind = "cat" if cmap == "cat" else "time" if cmap == "time" else "num"
    v, cats, t0 = values_of(df, col, kind)
    S = stats_of(v) if kind != "cat" else None
    lo, hi = ((S["p2"], S["p98"]) if (S and S.get("valid")) else (0.0, max(len(cats or []) - 1, 1)))
    if kind == "num" and S and S.get("valid") and hi <= lo:
        lo, hi = S["min"], S["max"]
    scale_note = ""
    if scale_of and kind == "num" and os.path.exists(scale_of):
        df_s = read_points(scale_of, mtime(scale_of))
        if col in df_s:
            S_s = stats_of(values_of(df_s, col, "num")[0])
            if S_s.get("valid"):
                lo, hi = (S_s["p2"], S_s["p98"]) if S_s["p98"] > S_s["p2"] else (S_s["min"], S_s["max"])
                scale_note = "scale of step 1"
    c_map, c_side = st.columns([1.8, 1], gap="medium")      # the side wide enough for its table's labels
    with c_map:
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
        legend(kind, cmap, lo, hi, unit, t0, cats, counts, note=scale_note)
    # what the map shows, behind the "?" of the side heading (the column's own text first when the caller gives one)
    how = ((f"All {len(df):,} readings" if len(pv) >= len(df) else f"A random {len(pv):,} of the {len(df):,} readings")
           + (" as the strips their header swept" if "polygon" in pv else " as points")
           + (", coloured from the 2nd to the 98th percentile" + (" of step 1's file" if scale_note else "")
              if kind != "cat" else "")
           + ". Point at a strip to read its value; nothing is interpolated."
           + (" The cyan line is the field boundary." if outline else "")
           + (" Values beyond the scale are counted in the end bars of the histogram." if kind == "num" else ""))
    with c_side:
        st.markdown(f"**{label}**" + (f" · {unit}" if unit else "") + f"  \n`{col}`"
                    + (f" · {html.escape(data)}" if data else ""),
                    help=(col_help[col] + (" Values beyond the scale are counted in the end bars of the histogram."
                                           if kind == "num" else "")) if col_help.get(col) else how)
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
                av = avg_of(df, col) if per_area(unit) else None
                if av is not None:
                    rows_.insert(4, ("average (SMS, area-weighted)", fmt_value(av, unit)))
            if base_col and kind == "num" and base_col in df:
                vb, _, _ = values_of(df, base_col, "num")
                Sb = stats_of(vb)
                ref = {"minimum": Sb.get("min"), "2nd percentile": Sb.get("p2"), "mean": Sb.get("mean"),
                       "median": Sb.get("median"), "98th percentile": Sb.get("p98"), "maximum": Sb.get("max"),
                       "SD": Sb.get("sd"), "average (SMS, area-weighted)": avg_of(df, base_col)}
                cur = {"minimum": S.get("min"), "2nd percentile": S.get("p2"), "mean": S.get("mean"),
                       "median": S.get("median"), "98th percentile": S.get("p98"), "maximum": S.get("max"),
                       "SD": S.get("sd"), "average (SMS, area-weighted)": avg_of(df, col)}

                def chg(k):
                    if k == "CV" and S.get("cv") and Sb.get("cv"):
                        return f"{S['cv'] - Sb['cv']:+.2f} points"
                    a, b = cur.get(k), ref.get(k)
                    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b):
                        return ""
                    return f"{a - b:+.2f} {unit}".strip() + (f" ({100 * (a - b) / b:+.2f} %)" if b else "")
                tbl = pd.DataFrame([(k, v_, chg(k)) for k, v_ in rows_],
                                   columns=["statistic", "value", "change vs the clean map"])
            else:
                tbl = pd.DataFrame(rows_, columns=["statistic", "value"])
            # the statistic's name in full and the value beside it within the side column (no side scroll)
            st.dataframe(tbl, hide_index=True, height=36 * (len(rows_) + 1) + 3,
                         column_config={"statistic": st.column_config.TextColumn(width=200),
                                        "value": st.column_config.TextColumn(width=104)})
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
        else:
            st.caption("No point has a value.")
    if not extras:
        return
    explorer_extras(shp)


def map_folded(tag: str) -> bool:
    """True once the file has a cleaning with its clean shapefile on disk: the maps of steps 1 and 2 are folded then
    (a rerun of step 3 draws its own maps only, as quick as with one map per step)."""
    C = ss.cleaned.get(tag)
    return bool(C) and os.path.exists(str(C.get("shp") or ""))


def map_box(key: str, folded: bool):
    """The expander of the map of step 1 or 2: open until the file is cleaned, folded after (a click opens it again).
    It runs its content only while open: the caller draws the map when .open is True."""
    return st.expander("Map", expanded=not folded, key=f"map_box_{key}", icon=":material/map:", on_change="rerun")


def explorer_extras(shp: str):
    """Under a map: the table of the file's attributes and its first 1,000 records (compact expanders)."""
    if not shp or not os.path.exists(shp):
        return
    df = read_points(shp, mtime(shp))
    with st.expander(f"Attributes ({len(df.columns) - 2})", type="compact"):
        st.dataframe(attribute_table_of(shp, mtime(shp)), hide_index=True,
                     column_config={"points with a value": st.column_config.NumberColumn(format="%d")})
    with st.expander("First 1,000 records", type="compact"):
        st.dataframe(df.drop(columns=["lon", "lat"]).head(1000), hide_index=True)


def zip_shapefile(shp: str, zpath: str, stem: str | None = None) -> str:
    """The .shp / .shx / .dbf / .prj / .cpg of shp in one zip, renamed to `stem` when given."""
    base = os.path.splitext(shp)[0]
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for e in er.SHP_EXTS:
            if os.path.exists(base + e):
                z.write(base + e, (stem or os.path.basename(base)) + e)
    return zpath


def download(label, path, mime, key, primary=False, icon=":material/download:", help: str | None = None):
    if path and os.path.exists(path):
        with open(path, "rb") as fh:
            st.download_button(label, fh.read(), file_name=os.path.basename(path), mime=mime, key=key,
                               type="primary" if primary else "secondary", icon=icon, help=help)


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
        low = [os.path.basename(f.name).lower() for f in val]
        dup = sorted({n for n in low if low.count(n) > 1})
        if dup:
            raise ValueError(f"two boundary files are named {dup[0]}: give one boundary (one shapefile set, or a zip)")
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
           "is_plan": bool(P.get("is_plan")), "warnings": list(P.get("warnings") or []), "outline": [],
           "fingerprint": boundary_fingerprint(path)}
    if not out["needs_choice"]:
        out["outline"] = _outline_of(er.plan_union_wgs84(P))
    return out


def boundary_fingerprint(path: str) -> str:
    """What a boundary file holds, as a short hash of its bytes (a shapefile: its .shp, .shx and .dbf): another file
    with the same name, or the same file edited on disk, is another boundary for the 'settings changed' check; the
    same file uploaded again is the same."""
    h = hashlib.sha1()
    base, ext = os.path.splitext(path)
    parts = [base + e for e in (".shp", ".shx", ".dbf")] if ext.lower() == ".shp" else [path]
    for p in parts:
        try:
            with open(p, "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:16]


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
    """The grower's total weight of a file as the engine's scale_ticket {value, unit, basis, moisture_pct, note,
    area_ac, use, test_weight_lb_bu, bushel_from}. use: 'validate' (the weight is compared and changes nothing in the
    clean file, not even a combine factor) or 'adjust'. test_weight_lb_bu: the grower's bushel weight. A weight in lb,
    kg or t is always compared as a mass, in the file's bushels, so the bushel weight changes no number there (it is
    reported); grower's bushels (bu, bu/ac) are converted through it only when the user says they are bushels of that
    weight (G['bushels'] == 'grower'), else they are compared as given (trade bushels). bushel_from: the bushel of the
    monitor's total, 'file' (its own wet mass / wet volume, the default) or 'declared'."""
    if not G or not G.get("weight"):
        return None
    wet = G.get("basis") == "wet"
    unit = G.get("unit") or "lb"
    tw = float(G["test_weight"]) if G.get("test_weight") else None
    if unit in ("bu", "bu/ac") and G.get("bushels") != "grower":
        tw = None                                        # trade bushels: compared as given
    return {"value": float(G["weight"]), "unit": unit, "basis": "wet" if wet else "dry",
            "moisture_pct": (float(G["moisture"]) if (wet and G.get("moisture") is not None) else None), "note": None,
            "area_ac": (float(G["area_ac"]) if (unit == "bu/ac" and G.get("area_ac")) else None),
            "use": "adjust" if G.get("use") == "adjust" else "validate", "test_weight_lb_bu": tw,
            "bushel_from": "declared" if G.get("bushel_from") == "declared" else "file"}


def import_record_of(tag: str) -> dict | None:
    """The record of the file's import as SMS (resolved settings, readings left out ...), or None."""
    IM = (ss.datasets.get(tag) or {}).get("sms_import")
    return IM if isinstance(IM, dict) and IM else None


def import_min_yield(tag: str):
    """(minimum, True) when the file was imported as SMS: the S0 minimum of its cleaning is the import's own (None =
    no minimum); (None, False) without an import record (S0 then takes the minimum of step 3)."""
    RS = (import_record_of(tag) or {}).get("resolved")
    if isinstance(RS, dict) and "min_yield" in RS and RS["min_yield"] != si.AUTO:
        v = RS["min_yield"]
        return (None if v is None or float(v) <= 0 else float(v)), True
    return None, False


def file_config(tag: str, sset: dict) -> dict:
    """Everything one cleaning of `tag` depends on: the SMS 3-sigma settings (with the S0 minimum the cleaning really
    uses: the import's for a file imported as SMS), the boundary (path, chosen fields and what the file holds), the
    grower's data and the combine factor. Lists and plain values only, so that a config saved with the work compares
    equal after it is read back."""
    B = boundary_of(tag)
    G = ss.grower.get(tag) or {}
    S3 = dict(sset)
    is_y = ss.datasets.get(tag, {}).get("yield", True)
    mn, has_imp = import_min_yield(tag)
    if is_y and has_imp:
        S3["min_yield"] = mn
    if grower_ticket(G) or G.get("test_weight"):
        gr = {k: G.get(k) for k in ("weight", "unit", "basis", "moisture", "test_weight", "crop", "std_moisture", "use",
                                    "area_ac", "bushels", "bushel_from")}
    else:
        gr = {"crop": G.get("crop")} if G.get("crop") else None     # the crop alone reaches the engine too
    return {"sms3sigma": S3,
            "boundary": [B["path"], [int(x) for x in (B.get("feature") or ())], B.get("fingerprint")] if B else None,
            "grower": gr, "combines": combine_settings(tag) if is_y else None}


NOT_CONFIRMED = "not confirmed by the cleaning record"


def config_of_cleaning(t: str, C: dict, R: dict) -> dict:
    """The config a restored cleaning ran with, for the 'settings changed: clean again' check: the one saved with the
    work when it has one; else (works saved before it was kept) the config of the restored state, part by part, where
    the cleaning record (its JSON) confirms it, and a value that never equals the current state where it does not."""
    def with_passes(s3):
        """Harvest settings kept before the passes of Optimize Swath Widths had a control: the passes the cleaning's
        own record says it ran with (1 when it says none), so that such a work is not told to clean again."""
        if C.get("kind") == "a3" or not isinstance(s3, dict) or not s3 or "swath_passes" in s3:
            return s3
        return {**s3, "swath_passes": swath_passes_of(((R or {}).get("settings") or {}).get("sms3sigma"))}

    cfg = C.get("config")
    if isinstance(cfg, dict) and "sms3sigma" in cfg:
        b = cfg.get("boundary")
        if isinstance(b, (list, tuple)) and b:
            b = [b[0], [int(x) for x in (b[1] if len(b) > 1 and b[1] else [])], b[2] if len(b) > 2 else None]
        return {**cfg, "boundary": b, "sms3sigma": with_passes(cfg.get("sms3sigma"))}
    cur = file_config(t, with_passes(C.get("settings")) or sset_for(t))
    S = (R or {}).get("settings") or {}
    out = dict(cur)
    if C.get("kind") == "a3":
        rb = (R or {}).get("boundary") or {}
        b_file, b_feat = rb.get("file"), rb.get("feature")
        clip_on = bool((C.get("settings") or {}).get("clip", True))
    else:
        A = S.get("aoi") or {}
        b_file, b_feat = A.get("file"), A.get("feature")
        clip_on = bool((C.get("settings") or {}).get("clip", True))
    if clip_on:
        cb = cur.get("boundary")
        feats = sorted(int(x) for x in (b_feat if isinstance(b_feat, (list, tuple)) else
                                        ([b_feat] if b_feat not in (None, "") else [])))
        if bool(cb) != bool(b_file) or (cb and (os.path.basename(str(b_file)).lower() != os.path.basename(cb[0]).lower()
                                                or feats != sorted(cb[1]))):
            out["boundary"] = NOT_CONFIRMED
    if C.get("kind") != "a3":
        mn, has_imp = import_min_yield(t)
        imp = S.get("sms_import")
        used = ((imp.get("resolved") or {}).get("min_yield") if isinstance(imp, dict)
                else (S.get("sms3sigma") or {}).get("min_yield"))

        def nz(v):
            return 0.0 if v in (None, si.AUTO) else float(v)
        if has_imp and S and abs(nz(used) - nz(mn)) > 1e-9:
            out["sms3sigma"] = NOT_CONFIRMED            # an older cleaning: S0 ran with step 3's minimum, not the import's
        G = ss.grower.get(t) or {}
        T, Ts = grower_ticket(G), S.get("scale_ticket") or {}
        ok = (T is None) == (not Ts.get("value"))
        if ok and T is not None:
            ok = (all(abs(float(T[k] or 0) - float(Ts.get(k) or 0)) < 1e-6 for k in ("value", "moisture_pct", "area_ac"))
                  and str(T["unit"]) == str(Ts.get("unit") or "lb") and str(T["basis"]) == str(Ts.get("basis") or "wet")
                  and (G.get("use") == "adjust") == bool(C.get("adjusted")))
        if ok and T is not None:
            # this version passes the use and the grower's bushel weight in the ticket; an older record carried the
            # bushel weight as the settings' test weight and decided validate / adjust in the app: never the same
            ok = (str(Ts.get("use") or "") == T["use"]
                  and abs(float(T.get("test_weight_lb_bu") or 0) - float(Ts.get("test_weight_lb_bu") or 0)) < 1e-6
                  and str(Ts.get("bushel_from") or "file") == T["bushel_from"])
        if ok and G.get("crop"):
            ok = str(G["crop"]) == str(S.get("crop") or "")
        if not ok:
            out["grower"] = NOT_CONFIRMED
        M, CF = S.get("machines") or {}, combine_settings(t)
        okm = bool(M.get("harmonise")) == bool(CF["on"])
        if okm and CF["on"]:
            okm = (str(M.get("method") or "auto") == CF["method"] and str(M.get("reference") or "auto") == CF["reference"]
                   and abs(100 * float(M.get("max_factor") or 0.1) - CF["max_pct"]) < 1e-6
                   and bool(M.get("ticket_confirms", True)) == CF["ticket_confirms"])
        if not okm:
            out["combines"] = NOT_CONFIRMED
    return out


def settings_of(tag: str, sset: dict) -> dict:
    """The engine settings of one cleaning: the SMS 3-sigma sequence (sset); the field boundary as
    the field of interest (records more than the S1 edge tolerance outside it set aside before the cleaning, the clean
    file clipped to it, so the monitor total that the grower's weight is compared with is the field's); the grower's
    total weight with its use (validate / adjust) and the grower's bushel weight (grower_ticket), the crop and the
    standard moisture; the combine factor only when it is switched on."""
    clip = bool(sset.get("clip", True))
    S3 = {k: v for k, v in sset.items()}
    CF = combine_settings(tag)
    # the combine factor switched off: nothing else of its panel reaches the engine (a stale max factor cannot stop
    # the cleaning)
    S = {"method": "sms3sigma", "tag": tag, "sms3sigma": S3,
         "machines": ({"harmonise": True, "method": CF["method"], "reference": CF["reference"],
                       "max_factor": CF["max_pct"] / 100.0, "ticket_confirms": CF["ticket_confirms"]}
                      if CF["on"] else {"harmonise": False})}
    B = boundary_of(tag)
    if B is not None and clip:
        S["aoi"] = {"file": B["path"], "buffer_m": float(sms.DEFAULTS["clip_tolerance_m"]), "clip_output": True,
                    "feature": er.feature_setting(B.get("feature"))}
    G = ss.grower.get(tag) or {}
    T = grower_ticket(G)
    if T is not None:
        S["scale_ticket"] = T
    IM = import_record_of(tag)
    RS = (IM or {}).get("resolved") or {}
    mn, has_imp = import_min_yield(tag)
    if has_imp:
        # S0 takes the file's own import minimum (None = no minimum: the import kept every reading above 0), and the
        # cleaning record carries the import (the readings in the data, those left out and why, the settings)
        S3["min_yield"] = 0.0 if mn is None else mn
        S["sms_import"] = {k: v for k, v in IM.items() if k != "all_readings"}
        S["sms_import"]["all_readings"] = os.path.basename(str(IM.get("all_readings") or ""))
        S["sms_import"].setdefault("text", IM.get("settings"))       # the settings line the report prints
        # the report names the import as steps 3 and 4 do: the user's settings (also those a work of an earlier
        # version kept), an older OCED rule's import kept as saved
        D_ = ss.datasets.get(tag) or {}
        if import_mode(D_) == "custom":
            S["sms_import"]["mode"] = "custom"
        elif import_mode(D_) == "default" and default_of(D_).get("older"):
            S["sms_import"]["mode"] = "older"
            S["sms_import"]["older"] = list(default_of(D_)["older"])
            if default_of(D_).get("older_decode"):     # an older version's decode, not an older rule
                S["sms_import"]["older_decode"] = str(default_of(D_)["older_decode"])
                if yields_converted(IM):
                    # the import converted those readings' yields with its own product: the report names that
                    # product, its weight and moisture (the import's own line)
                    S["sms_import"]["older_decode_converted"] = True
                else:
                    # the weight and moisture its yields carry (the report names them, not 'product unknown')
                    S["sms_import"]["older_decode_values"] = older_decode_values(default_view(D_).get("report"))
    wm = yields_converted(IM)
    if wm and RS.get("test_weight_lb_bu"):
        S["test_weight_lb_bu"] = float(RS["test_weight_lb_bu"])     # the import's weight to volume
    if wm and RS.get("dry_moisture_pct") is not None:
        # the import's dry moisture and its shrink: the dry yield of the file was computed with them
        S["moisture"] = {"standard_pct": float(RS["dry_moisture_pct"]),
                         "shrink": "symmetric" if RS.get("expand_dry_moisture") else "one_sided"}
    # the grower's bushel weight travels in the ticket (grower_ticket): test_weight_lb_bu stays the import's weight
    # to volume, the bushel of the monitor's total
    if G.get("crop"):
        S["crop"] = G["crop"]
    if G.get("std_moisture") is not None and T is not None:
        S["moisture"] = {**(S.get("moisture") or {}), "standard_pct": float(G["std_moisture"])}
    # the engine's defaults for an SMS cleaning of an imported file, where nothing above set them (setdefault only)
    # (the import's weight and moisture only when the import computed the file's dry yield with them)
    return er.sms_clean_defaults(S, S.get("sms_import") if wm else None) if hasattr(er, "sms_clean_defaults") else S


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


def data_crops(shp: str, strict: bool = False) -> tuple[str | None, str | None]:
    """(crop, note) of a point file: the crop its Crop column names, else its Product column (which may hold a
    variety, e.g. 'Variety X'), read over EVERY record. One known crop (sms_import.crop_key): its most frequent name.
    Several known crops: None and a note (one crop's weight, moisture and limits would convert the other's readings
    too). No known crop: the most frequent name, else None. strict: a file that cannot be read raises (OSError),
    never (None, None), which would say the file names no crop."""
    try:
        import pyogrio
        fields = list(pyogrio.read_info(shp)["fields"])
        cols = sorted([c for c in fields if c.lower() in ("crop", "product")], key=lambda c: c.lower() != "crop")
        first = None
        for c in cols:
            v = pyogrio.read_dataframe(shp, columns=[c], read_geometry=False)[c]
            v = v.astype(str).str.strip().replace({"": np.nan, "nan": np.nan, "None": np.nan}).dropna()
            if not len(v):
                continue
            vc = v.value_counts()
            first = first or str(vc.index[0])
            by = {}
            for name, n in vc.items():
                k = si.crop_key(name)
                if k:
                    by.setdefault(k, [0, str(name)])[0] += int(n)
            if len(by) == 1:
                return next(iter(by.values()))[1], None
            if len(by) > 1:
                parts = ", ".join(f"{k} ({n:,} readings)" for k, (n, _) in sorted(by.items(), key=lambda kv: -kv[1][0]))
                return None, (f"the {c} column of the file names more than one crop: {parts}. Nothing was converted "
                              "with one crop's weight to volume, dry moisture and limits: choose the product in the "
                              "import settings of the file (step 2), or open each crop as its own file")
        return first, None
    except Exception as e:
        if strict:
            raise OSError(f"{os.path.basename(str(shp))} could not be read ({_error_reason(e)})") from e
        return None, None


def data_crop(shp: str) -> str | None:
    """The crop a point file names (data_crops without the note)."""
    return data_crops(shp)[0]


def iso_crops() -> dict:
    """{crop: (lb/bu, dry moisture %)}: what SMS gives the crop of ISOXML task data (engine/formats/isoxml.py)."""
    try:
        from engine.formats import isoxml
        return dict(isoxml.ISO_SMS_CROPS)
    except Exception:                                    # the reader not loadable: the caption names no crop
        return {}


def import_fmt(source: dict | None = None, cand: dict | None = None) -> str | None:
    """The source format sms_import.resolve takes (engine.run.import_format): a decoded raw dataset's decoder
    (cnh_cn1, jd_jdl, jd_gs3_rcd, isoxml); 'jd_ops_center' for an Operations Center export (the Deere metadata's crop
    or monitor product, or collapsed from section elements); 'point_export' for any other point export (both are
    imported as SMS's generic import of a point file); None when neither says what the source is."""
    return er.import_format(source, cand)


def export_import_basis_of(path: str, cand: dict | None = None, strict: bool = False) -> dict:
    """What any import of a point export starts from (the 'basis' of its default import): {all_readings: the export
    (sections/<stem>_per_second.shp for one collapsed from section elements), crop, monitor (the crop definition an
    Operations Center export carries), fmt}. From the candidate when it is given (an export being opened), else read
    again from the export (its Deere metadata); the crop the file's Crop / Product column names when neither gives
    one, as import_as_sms does. strict: an export that cannot be read raises OSError (its crop not read is not a crop
    not known: export_basis_now)."""
    if cand is not None:
        crop, mon, fmt = cand.get("crop"), cand.get("monitor_product"), import_fmt(None, cand)
    else:
        crop, mon, fmt = _export_meta(path or "")
    if crop is None and mon is None and path and os.path.exists(path):
        try:
            crop = data_crops(path, strict=strict)[0]
        except Exception:                                # the crop stays unknown
            if strict:
                raise
            crop = None
    return {"all_readings": path, "crop": crop, "monitor": mon, "fmt": fmt}


def _export_meta(src: str) -> tuple:
    """(crop, monitor product, format) of the point export at src: an Operations Center export's crop from the
    '-Deere-Metadata.json' beside it (for a file collapsed from section elements, beside the export in the work's
    input/ folder) and format 'jd_ops_center'; (None, None, 'point_export') for any other export."""
    stem = os.path.splitext(os.path.basename(src))[0]
    sections = os.path.basename(os.path.dirname(src)).lower() == "sections" and stem.endswith("_per_second")
    orig = src
    if sections:                                         # engine.run.use_candidate: sections/<stem>_per_second.shp
        want = stem[:-len("_per_second")].lower() + ".shp"
        orig = next((os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(ss.workdir, "input")) for f in fs
                     if f.lower() == want), "")
    meta = (detect._deere_metadata(orig) if orig and os.path.isfile(orig) else None) or {}
    mon = (common.jd_monitor_product(meta.get("crop"), "CropName / CropId of the export's Deere-Metadata.json "
                                     "(Operations Center)", crop_id=meta.get("crop_id"))
           if (meta.get("crop") or meta.get("crop_id") is not None) else None)
    fmt = import_fmt(None, {"kind": "export", "monitor_product": mon, "crop": meta.get("crop"), "sections": sections})
    return meta.get("crop"), mon, fmt


IMPORT_KEYS_SHOWN = ("product", "test_weight_lb_bu", "dry_moisture_pct", "min_yield", "max_yield")
UNKNOWN_POINT_PRODUCT = ("The crop of this point export is not recognised: its yields are taken as the file gives them "
                         "(no dry yield computed again from the wet mass). SMS's generic import of a point file needs "
                         "a product, so this import cannot be SMS's: choose the product in step 2 (switch off SMS's "
                         "default) and Apply.")


OWN_YIELDS_TEXT = ("The product of this point export is not known (its crop or product column names none, e.g. a "
                   "variety), so the file's own dry yields are used as it gives them. Choosing the product in the "
                   "import settings of this file converts them with its weight to volume and dry moisture (the dry "
                   "yield computed again from the wet mass).")


def unknown_point_product(IM) -> bool:
    """True for the import record of a point export whose crop OCED could not map to a product (no weight to volume
    or no dry moisture) and which does not carry its own dry yield and dry mass (own_point_yields): its yields stay
    as the file gives them, which SMS's generic import (it needs a product) never does: step 1 warns."""
    if not isinstance(IM, dict) or IM.get("family") != "point" or IM.get("own_yields"):
        return False
    RS = IM.get("resolved") or {}
    return RS.get("test_weight_lb_bu") is None or RS.get("dry_moisture_pct") is None


def own_point_yields(IM) -> bool:
    """True for the import record of a point export whose product is not known and which carries its own dry yield
    (bu/ac) and dry mass (SMS's exports do; one of John Deere data names the variety as its product): the file's own
    yields are used, said plainly in the import note and in step 2 (OWN_YIELDS_TEXT), not warned in step 1."""
    if not isinstance(IM, dict) or IM.get("family") != "point" or not IM.get("own_yields"):
        return False
    RS = IM.get("resolved") or {}
    return RS.get("test_weight_lb_bu") is None or RS.get("dry_moisture_pct") is None


def older_import_rules(IM) -> bool:
    """True for an import record made by a version of OCED whose import rules were not this version's: recorded
    without 'sources' (the first published version) or with a revision below sms_import.IMPORT_REVISION (a point
    export cut at the product's yield volume limits, before point exports followed SMS's generic import)."""
    if not isinstance(IM, dict):
        return False
    try:
        rev = int(IM.get("revision") or 0)
    except (TypeError, ValueError):
        rev = 0
    return "sources" not in IM or rev < si.IMPORT_REVISION


def fresh_export_import(D: dict) -> dict | None:
    """For a point export whose import as SMS was recorded by an older version of OCED (older_import_rules), what
    opening it again gives: {"crop", "monitor", "fmt", "R": engine/sms_import.resolve, "own": the record keeps
    settings of the user's (a product chosen, a value labelled 'you', a flag, a delay or flow shift)}. The basis is
    always read from the export itself (export_basis_unrecorded: its Deere metadata, then its Crop / Product column;
    never the crop the record names: amendment A1.3), with a monitor product the record keeps. A record without
    'sources': today's default settings on that basis. A record with them: its settings under this version's rules
    (format 'point_export' for an export recorded with none), keeping what the user set (the values labelled 'you', a
    product chosen that is not the data's crop). None for any other file, or while the export cannot be read (its
    basis pending)."""
    IM = D.get("sms_import") if isinstance(D, dict) else None
    if not isinstance(IM, dict) or D.get("kind") != "export" or not older_import_rules(IM):
        return None
    try:
        # the data's crop read from the export (never the crop the record names: amendment A1.3); not known yet
        # while the export cannot be read: nothing to compare with
        B_ = export_basis_unrecorded(D, IM)
        if B_.get("pending"):
            return None
        crop, mon, fmt = B_["crop"], B_["monitor"], B_["fmt"] or si.POINT_EXPORT
        if "sources" not in IM:                          # a record of the first version: today's default settings
            return {"crop": crop, "monitor": mon, "fmt": fmt, "R": si.resolve(si.settings({}), crop, mon, fmt),
                    "own": False}
        RS, SRC = dict(IM.get("resolved") or {}), IM.get("sources") or {}
        S = {k: RS[k] for k in si.DEFAULTS if k in RS and k not in si.RESOLVED_KEYS and k != "product"}
        S.update({k: RS.get(k) for k in si.RESOLVED_KEYS if SRC.get(k) == si.SRC_YOU})
        S["on"] = True
        if S.get("manual_moisture_pct") is not None and not S.get("use_manual_moisture"):
            S["manual_moisture_pct"] = None              # the dry moisture, as the import resolves it again
        data_prod = si.crop_key(crop) or si.crop_key((mon or {}).get("crop") if isinstance(mon, dict) else None)
        if RS.get("product") and RS["product"] != data_prod:
            S["product"] = RS["product"]
        own = bool(S.get("product")) or any(SRC.get(k) == si.SRC_YOU for k in si.RESOLVED_KEYS) or any(
            RS.get(k) for k in FLAG_KEYS) or any(abs(float(RS.get(k) or 0.0)) > 1e-9 for k in DELAY_KEYS)
        return {"crop": crop, "monitor": mon, "fmt": fmt, "R": si.resolve(si.settings(S), crop, mon, fmt),
                "own": own}
    except Exception:                                    # nothing to compare with
        return None


def export_basis_now(D: dict, IM: dict | None) -> dict:
    """The basis of a point export saved without one (a work of an earlier version), read from the export itself as a
    fresh open reads it (its Deere metadata, then its Crop / Product column), never from the crop its record names:
    0.3.0 recorded no crop when step 1 had a product, and the product chosen as the crop when its file panel imported
    again a file whose record had none (amendment A1.3). Where 0.3.0 recorded the data's crop this gives the same
    value. A monitor product the record keeps is the data's (0.3.0 took it only from the export's Deere metadata):
    it stays when the metadata is no longer beside the export, with the recorded crop only when it is that crop. When
    the export cannot be read now (its folder away, or its files there but not readable), nothing is taken for the
    data's crop: the basis is marked 'pending' and read again once the readings are back (settle_basis).
    {all_readings (as recorded), crop, monitor, fmt[, pending]}."""
    IM = IM if isinstance(IM, dict) else {}
    allr = IM.get("all_readings") or D.get("shp")
    path = ew.resolve_moved(allr, ss.workdir) if allr else None
    mon_r = IM.get("monitor") if isinstance(IM.get("monitor"), dict) and IM.get("monitor") else None
    crop_r = (IM.get("crop") if (mon_r and IM.get("crop") and _crop(IM["crop"]) == _crop(mon_r.get("crop")))
              else None)                                 # the metadata's crop name, beside its crop definition
    def not_read(why=None):
        if mon_r:
            return {"all_readings": allr, "crop": crop_r, "monitor": mon_r, "fmt": IM.get("fmt") or si.POINT_EXPORT}
        # why: the reason a file that is there could not be read (none: its folder away)
        return {"all_readings": allr, "crop": None, "monitor": None, "fmt": IM.get("fmt") or si.POINT_EXPORT,
                "pending": True, **({"why": why} if why else {})}
    if not path or not os.path.exists(path):
        return not_read()
    part = path
    try:
        # a file there that cannot be read (held open by another program, a cloud folder offline, a network read
        # that fails) is not read: its crop is not taken as 'none' (amendment A1.3 R2)
        # (GDAL opens a shapefile whose .dbf it cannot open as one with no columns: each part is opened first)
        stem_ = os.path.splitext(path)[0]
        for part in (path, stem_ + ".dbf", stem_ + ".shx", stem_ + "-Deere-Metadata.json"):
            if os.path.isfile(part):
                with open(part, "rb") as fh_:
                    fh_.read(1)
        # a .dbf there whose header is not valid (shorter than its 33 bytes, or a header length beyond the file):
        # not read, never a file with no crop column (amendment A1.3 R2)
        dbf_ = stem_ + ".dbf"
        if os.path.isfile(dbf_):
            size_ = os.path.getsize(dbf_)
            with open(dbf_, "rb") as fh_:
                head_ = fh_.read(32)
            if size_ < 33 or int.from_bytes(head_[8:10], "little") > size_:
                return not_read(f"{os.path.basename(dbf_)} could not be read: its header is not valid (the file is "
                                "cut or damaged)")
        part = path
        B = export_import_basis_of(path, strict=True)
    except OSError as e:
        # (a reader that names the file in its error: the reason under it)
        return not_read(f"{os.path.basename(part)} could not be read: "
                        f"{_first_sentence(_error_reason(e.__cause__ or e))}")
    if B.get("monitor") is None and mon_r:               # the Deere metadata no longer beside the export
        B.update({"crop": crop_r, "monitor": mon_r, "fmt": IM.get("fmt") or B.get("fmt")})
    return {"all_readings": allr, "crop": B.get("crop"), "monitor": B.get("monitor"),
            "fmt": B.get("fmt") or si.POINT_EXPORT}


def _first_sentence(text: str) -> str:
    """The first sentence of a reader's message, with no full stop at its end ('DataSourceError: Unable to open x.shx
    or x.SHX. Set SHAPE_RESTORE_SHX ...': up to 'x.SHX'); a full stop inside a file name does not end it."""
    m = re.search(r"\.[;:]?\s+\S", str(text))
    return (str(text)[:m.start()] if m else str(text)).rstrip(" .")


def export_basis_unrecorded(D: dict, IM: dict) -> dict:
    """The basis of a point export whose import was recorded by an earlier version: the file's basis once it has one
    that was read, else read from the export now (export_basis_now; 'pending' when it cannot be read)."""
    B = import_basis(D)
    if B is None or B.get("pending"):
        return export_basis_now(D, IM)
    return {"all_readings": IM.get("all_readings") or D.get("shp"), "crop": B.get("crop"),
            "monitor": B.get("monitor"), "fmt": B.get("fmt")}


def import_values_line(R: dict) -> str:
    """'product unknown, - lb/bu, - %, 5-300 bu/ac' ('from 0 bu/ac, no maximum' ...): the values of a resolved import
    the old-import line compares."""
    def f(v, d):
        return "-" if v in (None, si.AUTO) else f"{float(v):,.{d}f}"
    mn, mx = R.get("min_yield"), R.get("max_yield")
    mn = None if mn == si.AUTO else mn
    lim = (f"{f(mn, 0)}-{f(mx, 0)} bu/ac" if mn is not None and mx is not None else
           f"from {f(mn, 0)} bu/ac, no maximum" if mn is not None else
           f"no minimum, up to {f(mx, 0)} bu/ac" if mx is not None else "no yield volume limits")
    return (f"product {R.get('product') or 'unknown'}, {f(R.get('test_weight_lb_bu'), 2)} lb/bu, "
            f"{f(R.get('dry_moisture_pct'), 1)} %, {lim}")


def import_differences(R: dict, F: dict, S_f: dict | None = None) -> list:
    """The product, weight to volume, dry moisture and yield volume limits in which the import R differs from F
    (what opening the export again gives), leaving out what the user set (S_f): a value labelled 'you', and the
    values another product chosen brings."""
    if (R.get("product") or None) != (F.get("product") or None) and (S_f or {}).get("product"):
        return []
    src = (R.get("sources") or {}) if S_f is not None else {}       # an old record's labels are not compared
    return [k for k in IMPORT_KEYS_SHOWN
            if not ((R.get(k) or None) == (F.get(k) or None) if k == "product" else
                    (_same_value(R.get(k), F.get(k)) or src.get(k) == si.SRC_YOU))]


def old_export_import(D: dict, FR: dict | None = None) -> str:
    """For a point export whose import as SMS was recorded by an older version of OCED (older_import_rules): '' when
    opening it again gives the same product, weight to volume, dry moisture and yield volume limits; else what the
    old import used and what this version uses ('product unknown, -, 5-300 bu/ac' ...) and how to import it again.
    FR: fresh_export_import(D) when known."""
    IM = D.get("sms_import") if isinstance(D, dict) else None
    if (not isinstance(IM, dict) or D.get("kind") != "export" or not D.get("yield", True)
            or not older_import_rules(IM) or not isinstance(IM.get("resolved"), dict)):
        return ""
    FR = FR or fresh_export_import(D)
    if FR is None or not import_differences(IM["resolved"], FR["R"]):
        return ""
    why = (" (this version imports a point export as SMS's generic import of a point file does: every reading kept, "
           "the product's weight to volume and dry moisture)" if "sources" in IM else "")
    # with settings of the user's (a product chosen, values typed) the line says what importing it again with them
    # gives, not what a fresh open does (a fresh open imports the data's crop: step 1 has no product)
    how = ("imported again with your settings under today's rule it is imported as SMS with" if FR.get("own") else
           "opened again it is imported as SMS with")
    return (f"imported by an older version of OCED ({import_values_line(IM['resolved'])}); {how} "
            f"{import_values_line(FR['R'])}{why}: import it again in step 2 (switch off "
            "SMS's default and Apply; its cleaning is set aside) or open the export again (step 1) for the current "
            "import (a new cleaning keeps the old one)")


def _import_record(R: dict, rep: dict, src: str, monitor=None, fmt=None, crop=None) -> dict:
    """The record of one import as SMS the app keeps per file (and the cleaning receives): the resolved settings and
    where each value came from, the readings in the data and those left out (per reason and per combine), what was
    recomputed, the notes, whether a point export of an unknown product keeps its own dry yields (own_yields); plus
    what is needed to import it again (the file of all readings, the monitor's crop definition, the format, the crop)
    and the revision of the import rules (sms_import.IMPORT_REVISION)."""
    return {"resolved": {k: R.get(k) for k in si.DEFAULTS}, "settings": si.describe(R),
            "sources": dict(R.get("sources") or {}), "defaults": dict(R.get("defaults") or {}),
            "sms_product": R.get("sms_product"), "family": R.get("family"), "sources_text": si.describe_sources(R),
            "monitor": dict(monitor) if isinstance(monitor, dict) else None, "fmt": fmt,
            "crop": None if crop is None else str(crop),
            "left_out": dict(rep["left_out"]),
            "left_out_by_group": {k: dict(v) for k, v in (rep.get("left_out_by_group") or {}).items()},
            "applied": dict(rep.get("applied") or {}), "n_all": int(rep["n_in"]), "n_in": int(rep["n_out"]),
            "all_readings": src, "changed": list(rep["changed"]), "notes": list(rep["notes"]),
            "own_yields": bool(rep.get("own_yields")), "revision": si.IMPORT_REVISION}


def sources_line(IM: dict) -> str:
    """'weight to volume <x> lb/bu (from the file); dry moisture <y> % (from the file); min. yield volume 5.000
    bu/ac (SMS for John Deere files); ...': the values of an import and where each came from."""
    S, RS = IM.get("sources") or {}, IM.get("resolved") or {}
    out = []
    for k, lab, unit, d in (("test_weight_lb_bu", "weight to volume", "lb/bu", 2), ("dry_moisture_pct", "dry moisture",
                                                                                 "%", 2),
                            ("min_yield", "min. yield volume", "bu/ac", 3), ("max_yield", "max. yield volume", "bu/ac", 2)):
        v = RS.get(k)
        val = "none" if v in (None, si.AUTO) else f"{float(v):,.{d}f} {unit}"
        out.append(f"{lab} {val}" + (f" ({SOURCE_LABEL.get(S[k], S[k])})" if S.get(k) else ""))
    prod = IM.get("sms_product") if si.SRC_TABLE in S.values() else None
    return ("SMS product " + prod + ": " if prod else "") + "; ".join(out)


PRE_STEP_LABEL = {"header_up": "header up", "no_position": "no position", "stationary": "standing still",
                  "no_distance": "no distance moved (SMS points)", "position_outlier": "position outlier",
                  "no_moisture": "no moisture", "no_flow": "no grain flow", "no_grain": "no grain"}


def sms_summary_view(rep: dict | None, IM: dict | None):
    """(total, datasets table or None, how) of a card's SMS Summary (report['sms_summary']: the display's own area,
    wet weight and moisture per dataset). The dry volume and yield follow the file's import settings: wet weight /
    weight to volume x the shrink at the dataset's moisture (one-sided unless expand dry moisture), as the decoder
    computes them, so another weight or dry moisture applied in step 2 changes them too. Without an import
    (or without its weight and moisture) the volume is the decoder's and `how` says so."""
    SM = (rep or {}).get("sms_summary") or {}
    T0, rows = dict(SM.get("total") or {}), [dict(r) for r in (SM.get("datasets") or [])]
    RS = (IM or {}).get("resolved") or {}
    tw, dm = RS.get("test_weight_lb_bu"), RS.get("dry_moisture_pct")
    if IM and tw and dm is not None:
        mode = "symmetric" if RS.get("expand_dry_moisture") else "one_sided"

        def vol(r):
            if r.get("wet_lb") is None:
                return r.get("dry_bu")
            m = r.get("moisture_pct")
            return float(r["wet_lb"]) / float(tw) * float(common.shrink_factor(dm if m is None else m, dm, mode))
        how = (f"dry at {float(tw):.2f} lb/bu and {float(dm):.2f} % ({mode.replace('_', '-')} shrink), the import "
               "settings of this file")
        for r in rows:
            r["dry_bu"] = vol(r)
            r["bu_ac"] = r["dry_bu"] / r["area_ac"] if (r.get("dry_bu") is not None and r.get("area_ac")) else None
        if rows and all(r.get("dry_bu") is not None for r in rows):
            T0["dry_bu"] = float(sum(r["dry_bu"] for r in rows))
        elif T0.get("wet_lb") is not None:
            T0["dry_bu"] = vol(T0)
        T0["bu_ac"] = T0["dry_bu"] / T0["area_ac"] if (T0.get("dry_bu") is not None and T0.get("area_ac")) else None
    elif IM is None:
        how = "not imported as SMS: area, wet weight and moisture only"
        T0.pop("dry_bu", None)
        T0.pop("bu_ac", None)
        for r in rows:
            r.pop("dry_bu", None)
            r.pop("bu_ac", None)
    else:
        how = "dry with the decoder's weight to volume and dry moisture (the import kept the file's yields)"
    df = pd.DataFrame(rows).drop(columns=["unit"], errors="ignore") if rows else None
    return T0, df, how


def _fi_product_changed(TKi: str, monitor=None, fmt=None, crop=None):
    """A new product in the import settings of a file: the weight to volume and dry moisture SMS gives that product
    from this source (the file's crop definition for a John Deere file of that crop), and each yield volume limit
    only where the product changes it on this file's basis (crop: its data's crop; the product the field showed
    before against the new one, as Apply to all decides it for every file it reaches: amendment A1.3); a limit the
    product does not change keeps the value shown, typed or not. Every value written is the one the new product gives
    on this file's basis, the value the comparison uses: for 'unknown' (the product taken back) the values of the
    data's own product, so that Apply puts the file back on its SMS default, as it does every file Apply to all takes
    the product back from."""
    p = ss.get(f"fi_prod_{TKi}")
    was = ss.get(f"fi_prodwas_{TKi}")
    try:
        R = si.resolve(si.settings({"product": p}), None, monitor, fmt)
    except ValueError:
        return
    Bp = {"crop": crop, "monitor": monitor, "fmt": fmt}

    def value(k):
        v = _product_value(Bp, p, k)
        if v is not None and v != si.AUTO and not isinstance(v, (int, float)):
            v = R.get(k)                                 # (not resolved on this basis: the product's own value)
        return None if v in (None, si.AUTO) else float(v)
    ss[f"fi_tw_{TKi}"] = value("test_weight_lb_bu")
    ss[f"fi_dm_{TKi}"] = value("dry_moisture_pct")
    ss[f"fi_mm_{TKi}"] = ss[f"fi_dm_{TKi}"]
    for k, key in (("min_yield", f"fi_min_{TKi}"), ("max_yield", f"fi_max_{TKi}")):
        if key in ss and _same_value(_product_value(Bp, was, k), _product_value(Bp, p, k)):
            continue                                     # not changed by this product here: the value shown stays
        ss[key] = value(k)
    ss[f"fi_prodwas_{TKi}"] = p


def superseded_dir(tag: str) -> str:
    """superseded/<time>/: the files of a cleaning made obsolete, side by side (the names carry the tag), so that
    their paths are no longer than in clean/<tag>/ (the Windows path limit)."""
    return os.path.join(ss.workdir, "superseded", dt.datetime.now().strftime("%Y%m%d-%H%M%S"))


def _move_free(p: str, folder: str):
    """Moves p into folder, under a free name (name_2 ...) when one is there already."""
    os.makedirs(folder, exist_ok=True)
    shutil.move(p, detect._free_name(os.path.join(folder, os.path.basename(p))))


def drop_cleaning(tag: str) -> list:
    """A cleaning of `tag` that no longer applies (the file was imported or extracted again): out of the session, and
    its files out of the folders step 4 hands out: the files of clean/<tag>/ move to superseded/<time>/ and the clean
    shapefile set handed out (exactly its own names: <tag>_sms3s_clean.* / <tag>_3s_clean.* and the zip, the shapefiles
    for DIFM <tag>_sms3s_clean_DIFM.zip, <tag>_sms3s_clean_adjusted_DIFM.zip / <tag>_3s_clean_DIFM.zip, never another
    file whose tag starts with this one)
    to superseded/<time>/p/. Also when the session holds no cleaning (a folder left in that state). A file another
    program holds open stays, with a warning. Returns the warnings."""
    c = ss.cleaned.pop(tag, None)
    if not ss.get("workdir"):
        return []
    warn, moves = [], []
    cdir = os.path.join(ss.workdir, "clean_shapefiles")
    stems = {os.path.splitext(c["shp"])[0]} if (c and c.get("shp")) else set()
    stems |= {os.path.join(cdir, f"{tag}_sms3s_clean"), os.path.join(cdir, f"{tag}_3s_clean")}
    for st_ in stems:
        for e in tuple(er.SHP_EXTS) + (".zip", ed.ZIP_SUFFIX, ed.ADJUSTED_ZIP_SUFFIX):
            if os.path.exists(st_ + e):
                moves.append(st_ + e)
    if c and c.get("zip") and os.path.exists(c["zip"]) and c["zip"] not in moves:
        moves.append(c["zip"])
    cl = os.path.join(ss.workdir, "clean", tag)
    nat = os.path.join(ss.workdir, NATIVE_DIR, tag)
    if not moves and not os.path.isdir(cl) and not os.path.isdir(nat):
        return []
    dest = superseded_dir(tag)
    if os.path.isdir(nat):
        try:
            _move_free(nat, os.path.join(dest, NATIVE_DIR))
        except OSError as e:
            warn.append(f"{NATIVE_DIR}/{tag} could not be moved ({_error_reason(e)}): it holds the monitor-format "
                        "files of the previous import")
    for p in moves:
        try:
            _move_free(p, os.path.join(dest, "p"))
        except OSError as e:
            warn.append(f"{os.path.basename(p)} could not be moved out of clean_shapefiles ({_error_reason(e)}): "
                        "close it in the other program; it is the clean file of the previous import")
    if os.path.isdir(cl):
        for n in sorted(os.listdir(cl)):
            if n == LOCK_NAME:
                continue
            try:
                _move_free(os.path.join(cl, n), dest)
            except OSError as e:
                warn.append(f"clean/{tag}/{n} could not be moved ({_error_reason(e)}): it is of the previous import")
        try:
            if not os.listdir(cl):
                os.rmdir(cl)
        except OSError:
            pass
    if not ss.cleaned:
        all_clean_zip()                                   # no cleaning left: the zip of all of them goes too
    return warn


# ------------------------------------------------------------------------------------------------ the two imports
# Each harvest file keeps two imports: the DEFAULT import (step 1: what SMS's import gives the source with its
# Processing Settings untouched, written when the file is opened or extracted and never overwritten by step 2) and
# the ACTIVE import (D["shp"], D["n"], D["sms_import"], D["source"]: what the cleaning and every output read; the
# default until the user applies own settings in step 2). D["import_default"] = {shp, n, mtime, sms_import, source
# (raw files), basis {all_readings, crop, monitor, fmt}: what any import of the file starts from, error: SMS's
# default import failed (shp = the readings as they are), older: a saved import made under an older OCED rule (what
# differs)}; D["import_mode"] = "default" | "custom" (the user's settings) | "as_is" (no import as SMS: an export as
# written, a raw file as the monitor logged it, the readings as they are when SMS's import failed).
IMPORT_MODES = ("default", "custom", "as_is")
AS_LOGGED_DIR = "as_logged"      # <work>/as_logged/decoded/<tag>_decoded.*: a raw file decoded again as logged
DEFAULT_DECODE_DIR = "sms_default"   # <work>/sms_default/decoded/<tag>_decoded.*: a raw file an earlier version
#                                      decoded with a product, decoded again for SMS's default (decode_default)
CUSTOM_SUFFIX = "_imported_custom"               # the user's import of a file (step 2)
NEXT_SUFFIX = "_imported_next"                   # an import being written: swapped in once it is complete
DEFAULT_SUFFIX = "_imported_default"             # SMS's default import built again (a work of an earlier version)
NO_PRODUCT_TAIL = "; choose the product in step 2"
NO_PRODUCT_DECODE = ("crop not known on the card: decoded with SMS's values for data without a product ({:g} lb/bu, "
                     "{:g} %)" + NO_PRODUCT_TAIL)
DEFAULT_GONE_NOTE = "step 1 shows the import in use: its readings are no longer on disk"
FLAG_KEYS = ("expand_dry_moisture", "use_manual_swath", "use_manual_moisture")
DELAY_KEYS = ("start_delay_s", "stop_delay_s", "flow_shift_s")
CROP_SETTING_KEYS = ("product", "test_weight_lb_bu", "dry_moisture_pct")    # they belong to a crop


def import_mode(D: dict) -> str:
    """The mode of a file's active import: 'default', 'custom' or 'as_is' ('default' when not recorded)."""
    m = D.get("import_mode") if isinstance(D, dict) else None
    return m if m in IMPORT_MODES else "default"


def default_of(D: dict) -> dict:
    """The default-import block of a file ({} when it has none)."""
    DF = D.get("import_default") if isinstance(D, dict) else None
    return DF if isinstance(DF, dict) else {}


def import_basis(D: dict) -> dict | None:
    """What any import of a harvest file starts from ({all_readings, crop, monitor, fmt}), or None (a planter or
    sprayer file, a folder of an older version rebuilt from its files, an import that kept no record)."""
    B = default_of(D).get("basis")
    return B if isinstance(B, dict) and B.get("all_readings") else None


def default_view(D: dict) -> dict:
    """What step 1 shows of a file: its default import ({shp, n, sms_import, report, op, yield, area_ac, zip, source,
    error, older, is_default}); a file without a default block (or one not built yet) shows its active import
    (is_default False)."""
    DF = default_of(D)
    has = bool(DF.get("shp"))
    out = {k: D.get(k) for k in ("report", "op", "yield", "area_ac", "zip", "kind", "label", "import_min")}
    out.update({"shp": DF["shp"] if has else D.get("shp"),
                "n": DF.get("n") if has else D.get("n"),
                "sms_import": DF.get("sms_import") if has else D.get("sms_import"),
                "source": DF["source"] if (has and "source" in DF) else D.get("source"),
                "error": DF.get("error"), "older": DF.get("older"), "older_decode": DF.get("older_decode"),
                "raw_gone": DF.get("raw_gone"), "is_default": has})
    if has and isinstance(DF.get("report"), dict):      # decoded again for SMS's default (decode_default)
        out["report"] = DF["report"]
        out["area_ac"] = (DF["report"].get("totals") or {}).get("area_ac")
        out["zip"] = DF.get("zip") or out.get("zip")
    return out


def has_cleaning(tag: str) -> bool:
    """The file has a cleaning in this work."""
    return tag in ss.cleaned


def failed_in_use(D: dict) -> bool:
    """The file is on the readings its failed SMS import left (as they are), not on an import chosen in step 2 ('None:
    as the monitor logged it' gives a raw file another file; own settings are mode custom)."""
    DF = default_of(D)
    if not DF.get("error") or import_mode(D) != "as_is" or D.get("as_is_chosen"):
        return False
    a, b = D.get("shp"), DF.get("shp")
    return not a or not b or os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def default_resolved(B: dict) -> dict:
    """The settings of SMS's default import of a file (engine/sms_import.resolve with the settings untouched)."""
    return si.resolve(si.settings({}), (B or {}).get("crop"), (B or {}).get("monitor"), (B or {}).get("fmt"))


def _fmt_setting(v, d) -> str:
    if d == "flag":
        return "on" if v else "off"
    if d == "product":
        return str(v) if v else "unknown"
    if v is None or v == si.AUTO:
        return "none"
    return f"{float(v):,.{d}f}"


def import_changes(R_from: dict | None, R_to: dict | None, keys=None) -> list:
    """['Max. yield volume 300.00 → 150.00', 'Manual swath off → on (30.00 ft)', ...]: the import settings in which
    R_to differs from R_from, in the order of step 2's fields ('none' for no value, flags 'on' / 'off'). keys: only
    these settings (e.g. IMPORT_KEYS_SHOWN)."""
    a, b = R_from or {}, R_to or {}
    out = []

    def want(k):
        return keys is None or k in keys
    for k, lab, d in (("product", "Product", "product"), ("test_weight_lb_bu", "Weight to volume", 2),
                      ("dry_moisture_pct", "Dry moisture", 2), ("expand_dry_moisture", "Expand dry moisture", "flag")):
        if want(k) and not (((a.get(k) or None) == (b.get(k) or None)) if d == "product" else
                            (bool(a.get(k)) == bool(b.get(k))) if d == "flag" else _same_value(a.get(k), b.get(k))):
            out.append(f"{lab} {_fmt_setting(a.get(k), d)} → {_fmt_setting(b.get(k), d)}")
    for flag, k, lab, unit in (("use_manual_swath", "manual_swath_ft", "Manual swath", "ft"),
                               ("use_manual_moisture", "manual_moisture_pct", "Manual moisture", "%")):
        if not want(flag):
            continue
        fa, fb = bool(a.get(flag)), bool(b.get(flag))
        if fa != fb:
            out.append(f"{lab} {'on' if fa else 'off'} → {'on' if fb else 'off'}"
                       + (f" ({_fmt_setting(b.get(k), 2)} {unit})" if fb and b.get(k) is not None else ""))
        elif fa and not _same_value(a.get(k), b.get(k)):
            out.append(f"{lab} {_fmt_setting(a.get(k), 2)} → {_fmt_setting(b.get(k), 2)} {unit}")
    for k, lab, d in (("min_yield", "Min. yield volume", 3), ("max_yield", "Max. yield volume", 2),
                      ("start_delay_s", "Start delay", 2), ("stop_delay_s", "Stop delay", 2),
                      ("flow_shift_s", "Flow shift", 2)):
        if want(k) and not _same_value(a.get(k), b.get(k)):
            out.append(f"{lab} {_fmt_setting(a.get(k), d)} → {_fmt_setting(b.get(k), d)}")
    return out


def same_import(A: dict, B: dict) -> bool:
    """Two resolved imports are the same on every setting of sms_import.DEFAULTS (a manual swath or moisture value
    counts only while its box is ticked)."""
    for k in si.DEFAULTS:
        if k == "manual_swath_ft" and not (A.get("use_manual_swath") or B.get("use_manual_swath")):
            continue
        if k == "manual_moisture_pct" and not (A.get("use_manual_moisture") or B.get("use_manual_moisture")):
            continue
        if k == "product":
            if (A.get(k) or None) != (B.get(k) or None):
                return False
        elif not _same_value(A.get(k), B.get(k)):
            return False
    return True


def changed_settings(R: dict, R0: dict, S_typed: dict | None = None) -> dict:
    """The settings in which the import R differs from the file's default R0, as sms_import settings: a product
    chosen, the values the user typed (labelled 'you'; for a record without labels, every value that differs), the
    flags with their values, the delays and the flow shift. S_typed: the values as typed (an empty manual moisture
    stays empty: the dry moisture of each file)."""
    out = {}
    if (R.get("product") or None) != (R0.get("product") or None) and R.get("product"):
        out["product"] = R["product"]
    SRC = R.get("sources")
    for k in si.RESOLVED_KEYS:
        you = (SRC.get(k) == si.SRC_YOU) if isinstance(SRC, dict) else not _same_value(R.get(k), R0.get(k))
        if you:
            out[k] = R.get(k)
    for k in FLAG_KEYS + DELAY_KEYS:
        if not _same_value(R.get(k), R0.get(k)):
            out[k] = R.get(k)
    if R.get("use_manual_swath"):
        out["use_manual_swath"], out["manual_swath_ft"] = True, R.get("manual_swath_ft")
    if R.get("use_manual_moisture"):
        out["use_manual_moisture"] = True
        out["manual_moisture_pct"] = (S_typed or {}).get("manual_moisture_pct") if S_typed is not None else \
            R.get("manual_moisture_pct")
    return out


def _decoded_totals(shp: str | None, tw: float, dm: float, shrink: str) -> dict | None:
    """The totals of every decoded reading (engine/formats/common.summarize: the wet mass over the readings' areas)
    with another weight to volume, dry moisture and shrink: {wet_lb, area_ac, bu_wet, bu_dry}; None when the file or
    a column is missing."""
    try:
        import pyogrio
        df = pyogrio.read_dataframe(shp, read_geometry=False,
                                    columns=["Distance_f", "Swth_Wdth_", "Yld_Mass_W", "Moisture__"])
        num = {c: pd.to_numeric(df[c], errors="coerce").to_numpy(float) for c in df.columns}
        area = num["Distance_f"] * num["Swth_Wdth_"] / common.SQFT_PER_AC
        wet = num["Yld_Mass_W"] * area
        dry = wet * common.shrink_factor(num["Moisture__"], dm, shrink)
    except Exception:
        return None
    return {"wet_lb": float(np.nansum(wet)), "area_ac": float(np.nansum(area)),
            "bu_wet": float(np.nansum(wet)) / float(tw), "bu_dry": float(np.nansum(dry)) / float(tw)}


def source_with_import(source: dict | None, R: dict, applied: dict | None, src_shp: str | None = None,
                       report: dict | None = None) -> dict | None:
    """The decode source of a raw file (engine.run.decode_source) for the import R: the shrink, weight to volume and
    dry moisture its dry yield now has, when the import computed it with them (the report's source paragraph and the
    cleaning read them; a writer of the monitor's format decodes the card again with these options, so that its
    totals are on the clean file's basis), the dry totals of every decoded reading (src_shp) and of the card's SMS
    Summary (report) on that basis, and the crop of a product chosen that is not the data's (the re-decode uses it as
    a product of the decode did; the decoder's 'choose the product in step 2' then names the product chosen). A copy;
    the source unchanged when it has no options."""
    if not isinstance(source, dict) or not isinstance(source.get("options"), dict):
        return copy.deepcopy(source)
    s = copy.deepcopy(source)
    o = s["options"]
    tw, dm = R.get("test_weight_lb_bu"), R.get("dry_moisture_pct")
    if (applied or {}).get("weight_and_moisture"):
        sh = "symmetric" if R.get("expand_dry_moisture") else "one_sided"
        if tw and dm is not None:
            T = _decoded_totals(src_shp, tw, dm, sh) if src_shp else None
            if T and isinstance(s.get("totals"), dict):
                s["totals"] = {**s["totals"], "bu_wet": T["bu_wet"], "bu_dry": T["bu_dry"]}
            if report and isinstance(s.get("sms_summary"), dict):
                SS_T = sms_summary_view(report, {"resolved": {"test_weight_lb_bu": tw, "dry_moisture_pct": dm,
                                                              "expand_dry_moisture": R.get("expand_dry_moisture")}})[0]
                s["sms_summary"] = {**s["sms_summary"], **{k: SS_T[k] for k in ("dry_bu", "bu_ac") if k in SS_T}}
        o_new = {"shrink": sh}
        if R.get("test_weight_lb_bu"):
            o_new["test_weight_lb_bu"] = float(R["test_weight_lb_bu"])
        if R.get("dry_moisture_pct") is not None:
            o_new["std_moisture_pct"] = float(R["dry_moisture_pct"])
        o.update(o_new)
        cs = str(s.get("calibration_summary") or "")
        cs = re.sub(r"shrink [a-z-]+", f"shrink {sh.replace('_', '-')}", cs)
        # the test weight with 2 decimals, as the Import as SMS row and the report give it (one rule)
        for k, pat, txt in (("test_weight_lb_bu", r"test weight [^;]*? lb/bu", "test weight {:.2f} lb/bu"),
                            ("std_moisture_pct", r"standard moisture [^;]*? %", "standard moisture {:g} %")):
            if k in o_new:
                m = re.search(pat, cs)
                was = re.search(r"-?\d[\d,]*(?:\.\d+)?", m.group(0)) if m else None
                if was and _same_value(float(was.group(0).replace(",", "")), o_new[k]):
                    continue                             # the decoder's own words for the same value stay
                new = txt.format(round(o_new[k], 4))
                cs = re.sub(pat, new, cs) if m else (cs + "; " if cs else "") + new
        s["calibration_summary"] = cs
    pk = si.crop_key(R.get("product")) if R.get("product") else None
    ck = si.crop_key(source.get("crop_name")) if source.get("crop_name") else None
    if pk and o.get("crop") != pk and (pk != ck or o.get("crop")):
        o["crop"] = pk
    if pk and isinstance(s.get("warnings"), list):
        chosen = (f"; product {R['product']} chosen in step 2"
                  + (f" ({float(tw):g} lb/bu, {float(dm):g} %)" if tw and dm is not None else ""))
        s["warnings"] = [str(w).replace(NO_PRODUCT_TAIL, chosen) for w in s["warnings"]]
    return s


def crop_labels(D: dict, B: dict | None, R: dict, rep: dict | None = None, src: str | None = None) -> dict | None:
    """The Product and Crop a file's import writes in its readings when its yields are converted with another crop
    than the one its readings are labelled with (a product chosen in step 2; for a raw file also what 0.3.0's decoder
    wrote for a product chosen before extracting, and SMS's default of a file an earlier version decoded with another
    product): {"Product": the SMS product name of the crop used (common.product_name; the data's own name of that crop
    when it names it so), "Crop": crop key} ({"Crop": crop key} only when the data names no crop OCED knows). A point
    export: its own Product / Crop columns (sms_import.export_labels on src, else the readings of B; the data's crop
    is its columns', else its metadata's), written with
    keep_crop (label_keep): a reading that already names the crop used keeps its text. None when the labels already
    name that crop (the file keeps its text byte for byte). rep: the decode report of the readings of B (default: the
    default import's own decode, else the file's)."""
    P = si.crop_key(R.get("product")) if R.get("product") else None
    if not P:
        return None
    if D.get("kind") != "raw":
        path = src or (ew.resolve_moved(B["all_readings"], ss.workdir) if (B or {}).get("all_readings") else None)
        if not D.get("yield", True) or not path or not os.path.exists(path):
            return None
        mon = (B or {}).get("monitor") if isinstance((B or {}).get("monitor"), dict) else {}
        # the data's crop: its columns', else its metadata's (an Operations Center export of varieties)
        return si.export_labels(path, R, (B or {}).get("crop") or mon.get("crop"))
    if not isinstance(rep, dict):
        rep = default_of(D).get("report")
        rep = rep if isinstance(rep, dict) else (D.get("report") if isinstance(D.get("report"), dict) else {})
    o_crop = (rep.get("options") or {}).get("crop") if isinstance(rep.get("options"), dict) else None
    data_crop = (B or {}).get("crop")
    labelled = si.crop_key(o_crop) if o_crop else (si.crop_key(data_crop) if data_crop else None)
    if P == labelled:
        return None
    if labelled is None:                                 # a crop the card does not name: its Product stays (0.3.0)
        return {"Crop": P}
    name = (str(data_crop) if (data_crop and "," not in str(data_crop) and si.crop_key(data_crop) == P)
            else common.product_name(P))
    return {"Product": name, "Crop": P}


def label_keep(D: dict, R: dict) -> str | None:
    """The keep_crop of a file's import (engine/sms_import.py apply): a point export's readings that already name the
    crop the import used keep their own text; None for a raw file (its readings are labelled alike)."""
    return si.crop_key(R.get("product")) if (D.get("kind") != "raw" and R.get("product")) else None


def _summary_crop(source: dict | None, labels: dict | None) -> dict | None:
    """The source of a raw file with the crop of its summary ('crop <name>; test weight ...') set to the label the
    import wrote (the report's source paragraph reads it)."""
    if not labels or not isinstance(source, dict) or not source.get("calibration_summary"):
        return source
    s = dict(source)
    name = labels.get("Product") or labels.get("Crop")
    s["calibration_summary"] = re.sub(r"(^|; )crop [^;]*", lambda m: f"{m.group(1)}crop {name}",
                                      str(s["calibration_summary"]), count=1)
    return s


def _parts(stem: str) -> list:
    """The files of one shapefile stem (<stem>.shp, .shx, .dbf ... and <stem>.<anything>), never another stem's."""
    folder, base = os.path.split(stem)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names if n.lower().startswith(base.lower() + ".")]


def _norm_p(p) -> str:
    return os.path.normcase(os.path.abspath(str(p))) if p else ""


def _where(p) -> str:
    """'x_decoded.shp in the folder decoded': a file named by its name and its folder's (never its full path)."""
    q = os.path.normpath(str(p)) if p else ""
    name, folder = os.path.basename(q), os.path.basename(os.path.dirname(q))
    return f"{name} in the folder {folder}" if (name and folder) else (name or "its folder")


def _folder_name(root) -> str:
    """'the folder <name>' of a folder (its name, not its full path), 'its folder' when not recorded."""
    name = os.path.basename(os.path.normpath(str(root))) if root else ""
    return f"the folder {name}" if name else "its folder"


def _own_import(tag: str, shp: str) -> bool:
    """The shapefile is one of the imports the app writes for this file (<tag>_imported*), never its readings or
    another file's."""
    return os.path.basename(os.path.splitext(str(shp))[0]).lower().startswith((tag + "_imported").lower())


def _in_folder(p, folder) -> bool:
    """The path lies inside the folder (compared as Windows compares them)."""
    if not p or not folder:
        return False
    a, b = os.path.normcase(os.path.abspath(str(p))), os.path.normcase(os.path.abspath(str(folder)))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                                   # (another drive)
        return False


def derived_import(tag: str, shp) -> bool:
    """The file in use is one the app derived for this file inside its work folder: its import with the user's
    settings (<tag>_imported*) or its readings decoded again as the monitor logged them (as_logged/). When such a file
    is gone, the file goes back to its default import. Any other file in use (the input read in place: 'None' on an
    export, an import that left nothing out; the readings a raw file decoded) holds the file's points: when it is
    missing, its points are away, not its import gone (amendment A1.3)."""
    if not shp or not ss.get("workdir") or not _in_folder(shp, ss.workdir):
        return False
    return _own_import(tag, shp) or _in_folder(shp, os.path.join(ss.workdir, AS_LOGGED_DIR))


def away_line(t: str, D: dict, cleaned: bool) -> str:
    """The line of the work message for a file set aside when its work is opened (its points not at hand): where
    they were and the way back, in the words of where they were (inside the work folder they cannot come back by
    themselves: its data opened again, or the file removed from the work in step 1)."""
    shp = str(D.get("shp") or "")
    with_ = " with its cleaning" if cleaned else ""
    if ss.get("workdir") and _in_folder(shp, ss.workdir):
        return (f"{t}: its points are no longer in the work folder ({_folder_name(os.path.dirname(shp))}): it stays "
                f"in this work, set aside{with_}; open its data again (step 1) to import it again, or remove it "
                "from this work (step 1)")
    return (f"{t}: its points are no longer in {_folder_name(os.path.dirname(shp))}: it stays in this work, set "
            f"aside{with_}, until they are back (reconnect the drive and open the work again), or remove it from "
            "this work (step 1)")


def _remove_files(paths) -> list:
    """Deletes the files; one warning per shapefile (stem) another program holds open, naming its parts held (the
    reason without the full path)."""
    held = {}
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        except OSError as e:
            st_, ext = os.path.splitext(os.path.basename(p))
            held.setdefault(st_, {"ext": [], "why": e.strerror or type(e).__name__})["ext"].append(ext)
    return [f"{st_}{'/'.join(h['ext'])} could not be deleted ({h['why']}): close it in the other program; it is no "
            "longer used" for st_, h in held.items()]


def delete_custom_import(tag: str, keep=(), as_logged: bool = True, keep_next: bool = False) -> list:
    """Deletes the user's import of a file: <tag>_imported_custom.* and <tag>_imported_next.* in decoded/, imported/
    and the default's folder, and (as_logged) <work>/as_logged/decoded/<tag>_decoded.* and <tag>_decode_report.json;
    never a file of another stem, never one of the stems of `keep` (shapefiles in use). Custom imports are derived
    data (the record and the file of all readings build them again): they are not kept. Returns the warnings (a
    file held open)."""
    if not ss.get("workdir"):
        return []
    DF = default_of(ss.datasets.get(tag) or {})
    folders = {os.path.join(ss.workdir, "decoded"), os.path.join(ss.workdir, "imported")}
    if DF.get("shp"):
        folders.add(os.path.dirname(os.path.abspath(DF["shp"])))
    kept = {os.path.normcase(os.path.splitext(os.path.abspath(p))[0]) for p in keep if p}
    stems = [os.path.join(f, tag + CUSTOM_SUFFIX) for f in folders]
    if not keep_next:
        stems += [os.path.join(f, s) for f in folders for s in _next_stems(f, tag)]
    if as_logged:
        al = os.path.join(ss.workdir, AS_LOGGED_DIR, "decoded")
        stems += [os.path.join(al, f"{tag}_decoded"), os.path.join(al, f"{tag}_decode_report")]
    files = [p for st_ in stems if os.path.normcase(os.path.abspath(st_)) not in kept for p in _parts(st_)]
    return _remove_files(files)


def _referenced_paths(*recs, exts=None) -> set:
    """The paths (normalised) of every file with one of these extensions (default: a shapefile's) a record names
    (nested dicts and lists; a relative path is of the work folder)."""
    exts = tuple(exts or er.SHP_EXTS)
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for w in v.values():
                walk(w)
        elif isinstance(v, (list, tuple)):
            for w in v:
                walk(w)
        elif isinstance(v, str) and os.path.splitext(v)[1].lower() in exts:
            out.add(_norm_p(v if os.path.isabs(v) else os.path.join(str(ss.get("workdir") or ""), v)))
    for r in recs:
        walk(r)
    return out


def _referenced_stems(*recs) -> set:
    """The stems (normalised, no extension) of every shapefile path a record names (nested dicts and lists; a
    relative path is of the work folder)."""
    return {os.path.splitext(p)[0] for p in _referenced_paths(*recs)}


def drop_unreferenced(tag: str, cands=(), dec_too: bool = False) -> list:
    """After an import of a file was replaced: the shapefiles of the import it had (one of the file's own
    <tag>_imported stems, as 0.3.0's <tag>_imported, or one a swap blocked earlier left under a temporary name) and
    of the readings an older version decoded it into (decoded/<tag>_decoded, with the zip of its extracted points and
    its decode report) that nothing of the file references any more go (never another stem, never a file outside the
    work folder; the user's own import is delete_custom_import's). dec_too: decoded/<tag>_decoded is looked at too,
    named or not in cands (an action of the user's replaced the import). Returns the warnings (a file held open)."""
    wd = ss.get("workdir")
    if not wd:
        return []
    recs = (ss.datasets.get(tag) or {}, ss.cleaned.get(tag) or {})
    refs = _referenced_stems(*recs)
    dec = _norm_p(os.path.join(wd, "decoded", f"{tag}_decoded"))
    files = []
    mine = re.compile(re.escape((tag + CUSTOM_SUFFIX).lower()) + r"$")        # delete_custom_import's: said there
    for stem in sorted({_norm_p(os.path.splitext(str(c))[0]) for c in list(cands) + ([dec + ".shp"] if dec_too else [])
                        if c}):
        if (stem in refs or not stem.startswith(_norm_p(wd) + os.sep) or mine.match(os.path.basename(stem))
                or not (_own_import(tag, stem) or stem == dec)):
            continue
        files += [q for q in _parts(stem) if os.path.splitext(q)[1].lower() in er.SHP_EXTS]
        if stem == dec:                                  # its zip and decode report, when nothing names them either
            named = _referenced_paths(*recs, exts=(".zip", ".json"))
            files += [q for q in (os.path.join(wd, "decoded", f"{tag}_decoded.zip"),
                                  os.path.join(wd, "decoded", f"{tag}_decode_report.json"))
                      if os.path.exists(q) and _norm_p(q) not in named]
    return _remove_files(files)


def _next_stems(folder: str, tag: str) -> list:
    """The names (no extension) of the imports being written for a file in a folder: <tag>_imported_next,
    <tag>_imported_next2 ..."""
    pat = re.compile(r"(" + re.escape(tag + NEXT_SUFFIX) + r"\d*)\.", re.IGNORECASE)
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    return sorted({m.group(1) for m in (pat.match(n) for n in names) if m})


def _next_path(folder: str, tag: str, in_use=()) -> str:
    """<folder>/<tag>_imported_next.shp, or _imported_next2, 3 ... when that name is an import in use (a swap that a
    file held open blocked keeps the complete import under its temporary name): a new import is never written over
    the one the file uses."""
    used = {os.path.normcase(os.path.splitext(os.path.abspath(str(p)))[0]) for p in in_use if p}
    k = 1
    while True:
        p = os.path.join(folder, f"{tag}{NEXT_SUFFIX}{'' if k == 1 else k}.shp")
        if os.path.normcase(os.path.splitext(os.path.abspath(p))[0]) not in used:
            return p
        k += 1


def _swap_in(nxt_shp: str, target_shp: str) -> tuple:
    """The parts of a complete import written under <tag>_imported_next renamed to the target stem (its old parts
    removed first). (path in use, warnings): a part that cannot be removed or renamed (held open) leaves the complete
    _next file in use, with a warning."""
    t_stem, n_stem = os.path.splitext(target_shp)[0], os.path.splitext(nxt_shp)[0]
    held = _remove_files(_parts(t_stem))
    if held:
        return nxt_shp, [f"The previous import {os.path.basename(target_shp)} could not be removed (it is open in "
                         f"another program): the new one is {os.path.basename(nxt_shp)}"]
    done = []
    for p in sorted(_parts(n_stem)):
        q = t_stem + p[len(n_stem):]
        try:
            os.replace(p, q)
            done.append((p, q))
        except OSError as e:
            for a, b in reversed(done):
                try:
                    os.replace(b, a)
                except OSError:
                    pass
            return nxt_shp, [f"{os.path.basename(p)} could not be renamed ({_error_reason(e)}): the new import is "
                             f"{os.path.basename(nxt_shp)}"]
    return target_shp, []


def _forget_old_import_line(tag: str):
    """The 'imported by an older version of OCED' line of the work message goes (the file is imported by this
    version now)."""
    msg = ss.get("work_msg")
    if msg and msg[0] in ("warning", "ok"):
        lines = str(msg[1]).split("\n")
        keep = [x for x in lines[1:] if not x.startswith(f"- {tag}: imported by an older version of OCED")]
        if len(keep) != len(lines) - 1:
            ss.work_msg = ("warning" if keep else "ok", "\n".join(lines[:1] + keep))


def _set_aside(had: bool, warn: list) -> str:
    """' Its cleaning was set aside ...' and the warnings, each a sentence of its own (a warning starts with a
    capital or with a file name)."""
    return ((" Its cleaning was set aside: clean it again in step 3." if had else "")
            + "".join(f" {w}." for w in warn if w))


def _done_line(line: str, had: bool, warn: list, warns: list | None) -> str:
    """The line of what was done, with ' Its cleaning was set aside ...'; the warnings (a file held open ...) joined
    to it, or, with the list warns, passed there once each (step 2 shows them as warnings, apart from that line)."""
    warn = list(dict.fromkeys(w for w in warn if w))     # a file held open is said once
    if warns is None:
        return line + _set_aside(had, warn)
    warns.extend(w for w in warn if w and w not in warns)
    return line + _set_aside(had, [])


def apply_custom(tag: str, S_f: dict, warns: list | None = None, product_from: dict | None = None) -> str:
    """Step 2's Apply with 'As SMS': the file imported again from all its readings (its default's basis) with the
    settings S_f. Values equal to SMS's default go back to the default import (or, when the default failed or was
    made under an older rule, the new import becomes the default). The import is written under a temporary stem and
    swapped in once complete: when it fails, the file, its import and the files on disk are unchanged (ValueError).
    The cleaning of the file no longer applies and is set aside (superseded/), unless the new import is the one in use
    reading for reading (the same settings, the same file content): then it stays. Returns a line for the user; warns:
    receives the warnings (a file held open) instead of that line. product_from: where a product chosen came from
    (Apply to all), kept in the record while the file has that product of its own (product_group); without it the
    record keeps what it had for the same product."""
    D = ss.datasets[tag]
    if import_basis(D) is None:
        raise ValueError(f"{tag} keeps no record of its import: open the data again (step 1) to change it")
    tried = default_needs_build(tag, retry=True)
    if tried:
        ensure_default(tag, retry=True)
    DF = default_of(D)
    B = DF["basis"]
    src = ew.resolve_moved(B["all_readings"], ss.workdir)
    if not src or not os.path.exists(src):
        raise ValueError(f"the readings this file was imported from ({_where(src or B['all_readings'])}) are no longer "
                         "on disk: reconnect the drive, or open the data again (step 1) to import it with other "
                         "settings")
    S_f = si.settings(S_f)
    R = si.resolve(S_f, S_f.get("product") or B.get("crop"), B.get("monitor"), B.get("fmt"))
    R0 = default_resolved(B)
    becomes_default = same_import(R, R0)
    if becomes_default and DF.get("older_decode"):
        # the default is made from the readings an older version decoded with a product (its raw data not at hand):
        # importing them again gives the same import, so nothing is imported again; SMS's default needs the raw data
        way = older_decode_way(D)
        if import_mode(D) == "default":
            return (f"{tag} is on the import of the older version's readings (Older rule): these values change "
                    f"nothing in it. To get SMS's default (today's rule), {way}.")
        return back_to_default(tag, warns=warns, tried=tried)
    if becomes_default and not (DF.get("error") or DF.get("older")):
        return back_to_default(tag, msg=f"{tag}: these are SMS's default settings: back to the default import.",
                               warns=warns, tried=tried)
    n_older = DF.get("n") if (becomes_default and DF.get("older")) else None
    def_shp = DF.get("shp")
    folder = (os.path.dirname(os.path.abspath(def_shp)) if def_shp and os.path.normcase(os.path.abspath(def_shp))
              != os.path.normcase(os.path.abspath(src)) else os.path.join(ss.workdir, "imported"))
    os.makedirs(folder, exist_ok=True)
    # a temporary name no import in use has (a swap blocked earlier leaves the import in use under a _next name)
    nxt = _next_path(folder, tag, in_use=(D.get("shp"), def_shp))
    _remove_files(_parts(os.path.splitext(nxt)[0]))          # one an earlier failure left
    labels = crop_labels(D, B, R, src=src)
    try:
        rep = si.apply(src, nxt, R, labels=labels, keep_crop=label_keep(D, R))
    except Exception as e:
        _remove_files(_parts(os.path.splitext(nxt)[0]))
        raise ValueError(f"{tag} could not be imported with these settings ({_error_reason(e)}): the file and its "
                         "import are unchanged") from e
    # the import in use made again reading for reading (the same settings, the same content: own settings made from
    # the readings an older version decoded, imported again from step 1's): its cleaning stays
    RS_use = (D.get("sms_import") or {}).get("resolved")
    same_data = (has_cleaning(tag) and import_mode(D) != "as_is" and isinstance(RS_use, dict)
                 and same_import(R, RS_use) and content_sig(rep["path"]) is not None
                 and content_sig(rep["path"]) == content_sig(D.get("shp")))
    had = has_cleaning(tag) and not same_data
    warn = [] if same_data else drop_cleaning(tag)
    prev = (D.get("shp"), (D.get("sms_import") or {}).get("all_readings"))     # the import replaced, its readings
    held = ""                                            # the stem a blocked swap already named
    if os.path.normcase(os.path.abspath(rep["path"])) == os.path.normcase(os.path.abspath(src)):
        path = src                                       # nothing left out, nothing recomputed: the readings file
    else:
        target = os.path.join(folder, f"{tag}{DEFAULT_SUFFIX if becomes_default else CUSTOM_SUFFIX}.shp")
        path, w = _swap_in(nxt, target)
        warn += w
        held = os.path.splitext(os.path.basename(target))[0] if w else ""
    rec = _import_record(R, rep, src, B.get("monitor"), B.get("fmt"), B.get("crop"))
    note = (DF.get("sms_import") or {}).get("crops_note")
    if note and not S_f.get("product"):
        rec["notes"].append(note)
        rec["crops_note"] = note
    if not becomes_default:
        rec["mode"] = "custom"
        pf = product_from
        IMo = D.get("sms_import") or {}
        if pf is None and _crop((IMo.get("resolved") or {}).get("product")) == _crop(R.get("product")):
            pf = IMo.get("product_from")                 # the same product: where it came from stays
        if isinstance(pf, dict) and R.get("product") and _crop(R.get("product")) != _crop(R0.get("product")):
            rec["product_from"] = dict(pf)
    D["shp"], D["n"], D["sms_import"] = path, int(rep["n_out"]), rec
    D.pop("as_is_chosen", None)
    _follow_default_decode(D, DF)                        # the decode the import is made from
    if D.get("kind") == "raw" and isinstance(DF.get("source"), dict):
        D["source"] = _summary_crop(source_with_import(DF["source"], R, rep.get("applied"), src_shp=src,
                                                       report=D.get("report")),
                                    labels if rep.get("relabelled") else None)
    if becomes_default:
        D["import_default"] = {**DF, "shp": path, "n": int(rep["n_out"]), **stamp(path),
                               "sms_import": copy.deepcopy(rec), "error": None, "older": None}
        if D.get("kind") == "raw" and "source" in D:
            D["import_default"]["source"] = copy.deepcopy(D["source"])
        D["import_mode"] = "default"
    else:
        D["import_mode"] = "custom"
    # the parts of the stem the blocked swap named are said once
    warn += [w for w in delete_custom_import(tag, keep=(path, default_of(D).get("shp")))
             if not (held and w.startswith(held + "."))]
    old = DF.get("shp")
    if (becomes_default and DF.get("older") and old and _own_import(tag, old)
            and _norm_p(old) not in (_norm_p(path), _norm_p(src))):
        # the older rule's import is no longer referenced: its files go (only a stem of this file's own imports)
        warn += _remove_files(_parts(os.path.splitext(os.path.abspath(old))[0]))
    # (0.3.0's import of the file, the readings it decoded with their zip and report, once nothing names them)
    warn += drop_unreferenced(tag, prev, dec_too=True)
    _forget_old_import_line(tag)
    save_current(quiet=True)
    n_all, n_out = int(rep["n_in"]), int(rep["n_out"])
    head = (f"{tag} imported again with SMS's default settings (today's rule)" if becomes_default
            else f"{tag} imported again with your settings")
    line = f"{head}: {n_out:,} of {n_all:,} readings ({n_all - n_out:,} left out)."
    if n_older is not None:
        line += f" Steps 1 and 2 now show it; the older rule's import had {int(n_older):,} readings."
    if same_data:
        line += " Its cleaning stays: the import is the one it was made from, reading for reading."
    return _done_line(line, had, warn, warns)


def _raw_root(D: dict, S0: dict | None = None) -> str | None:
    """The input folder a raw file was decoded from (found again under a moved work folder), None when not recorded."""
    S0 = S0 if isinstance(S0, dict) else (default_of(D).get("source") if isinstance(default_of(D).get("source"), dict)
                                          else D.get("source"))
    return ew.input_root({"source": S0 or {}, "report": D.get("report")}, ss.workdir)


def _tree_sig(root: str):
    """A cheap signature of everything under a folder: (number of files, their total size, the newest modification
    time), from one walk; a file deleted, added or changed anywhere below it changes it."""
    n = size = newest = 0
    for d, _, fs in os.walk(root):
        for f in fs:
            try:
                st_ = os.stat(os.path.join(d, f))
            except OSError:
                continue
            n, size, newest = n + 1, size + st_.st_size, max(newest, st_.st_mtime_ns)
    return n, size, newest


def raw_at_hand(tag: str, D: dict, root: str | None) -> bool:
    """The input folder of a raw file is there and still holds the raw data of its units, as decoding it again needs
    (_raw_candidate: a raw candidate of its format whose units include the ones the file was decoded from). Checked
    once per file, folder and content in the session (the file: its tag, format and the recorded unit ids of its
    import's source, so that two files of one folder each get their own answer; the folder's path and a signature of
    every file below it: a file deleted in a sub-folder changes it)."""
    if not root or not os.path.isdir(root):
        return False
    S0 = default_of(D).get("source") if isinstance(default_of(D).get("source"), dict) else D.get("source")
    S0 = S0 if isinstance(S0, dict) else {}
    try:
        key = (str(tag), str(S0.get("format") or ""), tuple(sorted(str(u) for u in (S0.get("unit_ids") or []))),
               os.path.normcase(os.path.abspath(root)), _tree_sig(root))
    except OSError:
        return False
    memo = ss.setdefault("raw_at_hand", {})
    if key not in memo:
        try:
            _raw_candidate(tag, D)
            memo[key] = True
        except Exception:                                # not at hand, or a folder that cannot be read
            memo[key] = False
    return memo[key]


def _raw_candidate(tag: str, D: dict) -> tuple:
    """(how the file was decoded: its source, the raw candidate of its input folder to decode it again). ValueError
    when that is not recorded or the raw data is gone."""
    S0 = default_of(D).get("source") if isinstance(default_of(D).get("source"), dict) else D.get("source")
    if not isinstance(S0, dict) or S0.get("kind") != "decoded" or not S0.get("unit_ids"):
        raise ValueError(f"{tag}: how this file was decoded is not recorded: open the raw data again (step 1)")
    fid = S0.get("format")
    root = _raw_root(D, S0)
    if not root or not os.path.isdir(root):
        raise ValueError(f"The raw data is no longer in {_folder_name(root)}: reconnect the drive or open it again "
                         "(step 1).")
    cands = detect.detect([root])
    raw = [c for c in cands if c.get("kind") == "raw" and c.get("decoder") == fid]
    cand = next((c for c in raw if os.path.normcase(os.path.abspath(c["probe"].root))
                 == os.path.normcase(os.path.abspath(root))), raw[0] if raw else None)
    try:
        ids = {u.id for u in er.list_units(cand)} if cand is not None else set()
    except Exception:                                    # the folder's remains cannot be listed
        ids = set()
    if cand is None or not set(S0["unit_ids"]) <= ids:
        # the folder there, but not the raw data of this file's units (files deleted below its folders)
        raise ValueError(f"The raw data of {tag} is not at hand ({_folder_name(root)}): reconnect the drive or open it "
                         "again (step 1).")
    cand["inputs_left_out"] = list(S0.get("inputs_left_out") or [])
    return S0, cand


def decoded_with_choice(D: dict) -> str | None:
    """What an earlier version gave the decoder of a raw file beyond SMS's default (0.3.0's step 1: a product chosen,
    or a weight to volume or dry moisture typed, before extracting): 'product barley', 'its own weight to volume and
    dry moisture'; None for readings decoded as a fresh extraction decodes them (every file this version extracts).
    The decode report read is the one of the readings the file's imports start from."""
    if not isinstance(D, dict) or D.get("kind") != "raw":
        return None
    rep = default_of(D).get("report")
    rep = rep if isinstance(rep, dict) else D.get("report")
    o = (rep or {}).get("options") if isinstance(rep, dict) else None
    if not isinstance(o, dict):
        return None
    B = import_basis(D) or {}
    pk = si.crop_key(o["crop"]) if o.get("crop") else None
    # against the data's crop: the label's (it always names the data's), else the basis's (never the report's crop,
    # which 0.3.0's ISOXML reader set to the product it was given)
    data_k = _crop(_label_crop(D.get("label"))) or _crop(B.get("crop"))
    if pk and pk != data_k:
        return f"product {o['crop']}"
    fid = rep.get("format") or (D.get("source") or {}).get("format")
    try:
        d0 = detect.default_options(fid)
        if si.format_family(fid) in si.FILE_CROP_FAMILIES:
            tw0, dm0 = d0.test_weight_lb_bu, d0.std_moisture_pct
        else:
            R_pre = si.resolve(si.settings({}), _label_crop(D.get("label")), None, fid)
            tw0, dm0 = ((R_pre["test_weight_lb_bu"], R_pre["dry_moisture_pct"]) if R_pre["product"]
                        else (d0.test_weight_lb_bu, d0.std_moisture_pct))
    except Exception:                                    # a decoder or crop not known here: nothing to compare
        return None
    tw, dm = o.get("test_weight_lb_bu"), o.get("std_moisture_pct")
    # values given to the decoder (None: the monitor's own, as logged; an import converts them from the wet mass)
    if (tw is None or _same_value(tw, tw0)) and (dm is None or _same_value(dm, dm0)):
        return None
    if tw0 is None and dm0 is None and _same_value(tw, no_product_values()[0]) \
            and _same_value(dm, no_product_values()[1]):
        return None                                      # SMS's values for data without a product (extract's retry)
    return "its own weight to volume and dry moisture"


OLDER_DECODE_WORD = "made from an older decode"


def older_decode_word(D: dict) -> str | None:
    """What an older OCED decoded the readings of a raw file's import in use with, when they are not SMS's default
    decode ('product wheat', 'its own weight to volume and dry moisture'): its default still labelled as an older
    decode (its raw data not at hand), its readings or its own decode report decoded with a product of 0.3.0's step 1
    (decoded_with_choice); None for any other file. A file on its own settings with no value of the user's is then
    named by its readings ('made from an older decode'), never 'your values' with nothing named."""
    if not isinstance(D, dict) or D.get("kind") != "raw":
        return None
    DF = default_of(D)
    if DF.get("older_decode"):
        return str(DF["older_decode"])
    w = decoded_with_choice(D)
    if w:
        return w
    o = (D.get("report") or {}).get("options") if isinstance(D.get("report"), dict) else None
    pk = _crop(o.get("crop")) if isinstance(o, dict) and o.get("crop") else None
    if pk and pk != (_crop(_label_crop(D.get("label"))) or _crop((import_basis(D) or {}).get("crop"))):
        return f"product {o['crop']}"
    return None


def older_decode_way(D: dict) -> str:
    """What gives SMS's default import of a raw file whose default is still made from the readings an older version
    decoded with a product (import_default older_decode): its raw data back in its folder (named, not its full path)
    and the work opened again, or the raw data extracted again."""
    DF = default_of(D)
    if DF.get("raw_gone"):
        return (f"put its raw data back in {_folder_name(_raw_root(D))} (reconnect the drive) and open the work again "
                "for SMS's default")
    return "extract its raw data again (step 1) for SMS's default"


def older_decode_values(rep: dict | None) -> str:
    """'48.00 lb/bu, 14.50 %': the weight to volume and dry moisture an older version decoded a raw file's readings
    with (their yields are on that basis), from the decode report of those readings; '' when it does not say."""
    o = rep.get("options") if isinstance(rep, dict) else None
    o = o if isinstance(o, dict) else {}
    return _tw_dm_text(o.get("test_weight_lb_bu"), o.get("std_moisture_pct"))


def _tw_dm_text(tw, dm) -> str:
    """'48.00 lb/bu, 14.50 %' ('' for what is not known)."""
    return ", ".join(([f"{float(tw):,.2f} lb/bu"] if tw else []) + ([f"{float(dm):.2f} %"] if dm is not None else []))


def yields_converted(IM: dict | None) -> bool:
    """The import recomputed the dry yields with its weight to volume and dry moisture (sms_import.apply's
    applied.weight_and_moisture; a record that does not say: both values known)."""
    IM = IM if isinstance(IM, dict) else {}
    a, RS = IM.get("applied"), IM.get("resolved") or {}
    if isinstance(a, dict):
        return bool(a.get("weight_and_moisture"))
    return bool(RS.get("test_weight_lb_bu")) and RS.get("dry_moisture_pct") is not None


def older_decode_text(V: dict, RS: dict) -> str:
    """The import line of a default made from the readings an older version decoded with a product, with the
    import's yield volume limits: 'decoded by an older OCED with product barley (48.00 lb/bu, 14.50 %) · 5.000-300.00
    bu/ac' when the import keeps the yields those readings carry (no product to convert them with), 'decoded by an
    older OCED with product barley, the yields converted with wheat (60.00 lb/bu, 13.50 %) · ...' when it converts
    them with its own product's weight to volume and dry moisture (the card names its crop)."""
    lims = import_values_text(RS).split(" · ")[-1]
    if yields_converted(V.get("sms_import")):
        vals = _tw_dm_text(RS.get("test_weight_lb_bu"), RS.get("dry_moisture_pct"))
        return (f"decoded by an older OCED with {V['older_decode']}, the yields converted with "
                f"{RS.get('product') or 'the product not known'}" + (f" ({vals})" if vals else "") + f" · {lims}")
    vals = older_decode_values(V.get("report"))
    return f"decoded by an older OCED with {V['older_decode']}" + (f" ({vals})" if vals else "") + f" · {lims}"


def older_decode_help(D: dict, V: dict | None = None) -> str:
    """The help of a default made from the readings an older version decoded with a product (import_default
    older_decode; V: the file's default view). When the import converts their yields with its own product's weight
    to volume and dry moisture (the card names its crop), it converts them as SMS's default does (the mass is the
    decoder's either way): only decoding options that are not SMS's leave SMS's default to confirm from the raw data.
    Else the yields are those the decode gave them: not SMS's default import, with the way to it."""
    V = V if isinstance(V, dict) else default_view(D)
    od = V.get("older_decode")
    why = "; ".join(str(x) for x in (V.get("older") or []))
    way = older_decode_way(D)
    IM = V.get("sms_import") or {}
    if yields_converted(IM):
        prod = (IM.get("resolved") or {}).get("product")
        txt = (f"Decoded by an older OCED with {od}" + (f" ({why})" if why else "") + "; the import converts its "
               f"yields with {prod or 'its weight to volume and dry moisture'} as SMS's default does")
        if decoding_not_sms(V.get("source"), V.get("report")):
            txt += f"; its decoding options are not SMS's: to confirm SMS's default, {way}"
        return txt + "."
    return (f"Decoded by an older OCED with {od}, not as SMS's default decodes it, so this is not SMS's default "
            "import" + (f" ({why})" if why else "") + f". To get SMS's default, {way}.")


def decode_default(tag: str, D: dict) -> dict:
    """A raw file an earlier version decoded with values of its own (decoded_with_choice) decoded again from its raw
    data as a fresh extraction decodes it for SMS's default import (decode_for_default), into
    <work>/sms_default/decoded/; the decoder's choices of the file (calibration, points ...) kept. ValueError when the
    raw data is gone or the decoder refuses it."""
    S0, cand = _raw_candidate(tag, D)
    # the field and season the warnings name, as an extraction names them (the label '<field> · <season> · <crop>')
    lab = str(D.get("label") or "").split(" · ")
    where = (f"{lab[0]} {'' if lab[1] == 'no season' else lab[1]}" if len(lab) >= 3 else tag)
    d, no_product, err = decode_for_default(
        cand, list(S0["unit_ids"]), detect.default_options(S0.get("format")), _label_crop(D.get("label")),
        dict(S0.get("decoder_kwargs") or {}), os.path.join(ss.workdir, DEFAULT_DECODE_DIR), tag, lambda m: None,
        where)
    if d is None:
        raise ValueError(f"{tag}: the raw data could not be decoded again ({err})")
    d.pop("df", None)
    if no_product:
        d["report"].setdefault("warnings", []).append(no_product)
        if isinstance(d.get("source"), dict):
            d["source"]["warnings"] = list(d["source"].get("warnings") or []) + [no_product]
    return d


def _follow_default_decode(D: dict, DF: dict):
    """A file whose import is now made from its default's readings, when those were decoded again for SMS's default
    (decode_default): the file's decode report, extracted points and area are that decode's."""
    if isinstance(DF.get("report"), dict):
        D["report"] = copy.deepcopy(DF["report"])
        D["area_ac"] = (DF["report"].get("totals") or {}).get("area_ac", D.get("area_ac"))
        if DF.get("zip"):
            D["zip"] = DF["zip"]


def decode_as_logged(tag: str, D: dict) -> dict:
    """A raw file decoded again as the monitor logged it (the monitor's own weight and moisture, its dry-yield
    convention: 0.3.0's extraction with the import off) into <work>/as_logged/decoded/. ValueError when the raw data
    is gone or the decoder refuses it."""
    S0, cand = _raw_candidate(tag, D)
    fid = S0.get("format")
    names = {f.name for f in dataclasses.fields(common.DecodeOptions)}
    o = {**(S0.get("options") or {}), "crop": None, "test_weight_lb_bu": None, "std_moisture_pct": None,
         "shrink": detect.default_options(fid).shrink}
    opts = common.DecodeOptions(**{k: v for k, v in o.items() if k in names})
    d = er.decode(cand, list(S0["unit_ids"]), opts, os.path.join(ss.workdir, AS_LOGGED_DIR), log=lambda m: None,
                  tag=tag, **dict(S0.get("decoder_kwargs") or {}))
    d.pop("df", None)
    return d


def apply_as_is(tag: str, warns: list | None = None) -> str:
    """Step 2's Apply with 'None': no import as SMS. A point export: the export as written (nothing left out or
    recomputed). A raw file: decoded again as the monitor logged it. The cleaning of the file is set aside. Returns a
    line for the user (warns: as apply_custom); ValueError when the readings or the raw data are gone (the file
    unchanged)."""
    D = ss.datasets[tag]
    B = import_basis(D)
    if B is None:
        raise ValueError(f"{tag} keeps no record of its import: open the data again (step 1) to change it")
    DF = default_of(D)
    had = has_cleaning(tag)
    if D.get("kind") == "raw":
        d = decode_as_logged(tag, D)
        warn = drop_cleaning(tag)
        D["shp"], D["n"], D["source"], D["sms_import"] = d["shp"], int(d["n"]), d["source"], None
        D["import_mode"] = "as_is"
        warn += delete_custom_import(tag, keep=(d["shp"], DF.get("shp")), as_logged=False)
        line = f"{tag} decoded again as the monitor logged it: {int(d['n']):,} readings, no import as SMS."
    else:
        src = ew.resolve_moved(B["all_readings"], ss.workdir)
        if not src or not os.path.exists(src):
            raise ValueError(f"the readings of this file ({_where(src or B['all_readings'])}) are no longer on disk: "
                             "reconnect the drive, or open the data again (step 1)")
        n_shp, n_dbf = shapefile_counts(src)
        # the file in use already the export as written (its SMS import failed): the same data, its cleaning stays
        same = import_mode(D) == "as_is" and not D.get("sms_import") and _norm_p(D.get("shp")) == _norm_p(src)
        warn = [] if same else drop_cleaning(tag)
        had = had and not same
        D["shp"], D["n"], D["sms_import"] = src, (n_shp if n_shp >= 0 else max(n_dbf, 0)), None
        D["import_mode"] = "as_is"
        D["as_is_chosen"] = True                         # 'None' chosen: not the failed import's readings
        warn += delete_custom_import(tag, keep=(src, DF.get("shp")))
        line = f"{tag} used as it is: {int(D['n']):,} readings, no import as SMS."
    _forget_old_import_line(tag)
    save_current(quiet=True)
    return _done_line(line, had, warn, warns)


def back_to_default(tag: str, msg: str | None = None, warns: list | None = None, tried: bool = False) -> str:
    """The file back to its default import (SMS's default, step 1): a pointer swap, the user's import deleted, the
    cleaning set aside. Safe in a callback. Returns a line for the user (warns: as apply_custom); ValueError when the
    default cannot be made (the reason when its write failed: a file held open, a full disk). tried: the caller has
    just tried to build the default (apply_custom): it is not imported a second time."""
    D = ss.datasets[tag]
    if not tried and default_needs_build(tag, retry=True):
        ensure_default(tag, retry=True)
    DF = default_of(D)
    if not DF.get("shp") or not os.path.exists(DF["shp"]):
        why = default_failed_reason(tag)
        if why:
            raise ValueError(f"{tag}: SMS's default import of this file could not be made ({why}): the file and its "
                             f"import are unchanged; {retry_advice(why)}")
        raise ValueError(f"{tag}: SMS's default import of this file cannot be made (its readings are no longer on "
                         "disk): open the data again (step 1)")
    had = has_cleaning(tag)
    prev = (D.get("shp"), (D.get("sms_import") or {}).get("all_readings"))     # the import replaced, its readings
    D["shp"], D["n"] = DF["shp"], DF.get("n")
    D["sms_import"] = copy.deepcopy(DF.get("sms_import"))
    if D.get("kind") == "raw" and "source" in DF:
        D["source"] = copy.deepcopy(DF["source"])
    _follow_default_decode(D, DF)
    D["import_mode"] = "as_is" if DF.get("error") else "default"
    D.pop("as_is_chosen", None)
    warn = delete_custom_import(tag, keep=(DF["shp"],))
    warn += drop_cleaning(tag)
    # (0.3.0's import of the file, the readings it decoded with their zip and report, once nothing names them)
    warn += drop_unreferenced(tag, prev, dec_too=True)
    if not DF.get("older"):
        _forget_old_import_line(tag)
    save_current(quiet=True)
    if not msg and DF.get("older_decode"):              # not SMS's default: the older version's readings
        msg = (f"{tag}: back to the import of the older version's readings (Older rule), not SMS's default. To get "
               f"SMS's default (today's rule), {older_decode_way(D)}.")
    return _done_line(msg or f"{tag}: back to SMS's default import.", had, warn, warns)


def _in_use_product(Dt: dict, Bt: dict) -> str | None:
    """The product of a file's import in use (a product the user chose in step 2 counts), else its default's."""
    RSt = (Dt.get("sms_import") or {}).get("resolved")
    if import_mode(Dt) != "as_is" and isinstance(RSt, dict):
        return RSt.get("product") or None
    return default_resolved(Bt).get("product") or None


def step2_start(D: dict) -> dict:
    """What step 2's fields of a harvest file start from: {"R0": its SMS default, "RS": the values of its import in use
    (with no import as SMS, the default's; SMS's default when it failed), "RP": the values the fields show (an import
    of an older rule or a failed one: today's product, weight to volume, dry moisture and yield volume limits, so that
    one Apply updates it), "SRCP": where those came from, "monitor" and "fmt": what a product chosen is resolved with,
    "IMv": the record the values are read from, "crop": the data's crop a product chosen is compared on, "old_imp": a
    point export imported under an older version's rules (old_export_import)}."""
    B = import_basis(D) or {}
    DF, mode = default_of(D), import_mode(D)
    try:
        R0 = default_resolved(B)
    except ValueError:
        R0 = si.resolve(si.settings({}))
    IM = D.get("sms_import") or {}
    IMv = IM if (IM and IM.get("resolved")) else (DF.get("sms_import") or {})
    RS = dict(IMv.get("resolved") or {k: R0.get(k) for k in si.DEFAULTS})
    SRC = IMv.get("sources") or R0.get("sources") or {}
    FR = fresh_export_import(D)
    old_imp = old_export_import(D, FR) if FR is not None else ""
    mon, fmt, RP, SRCP, crop = B.get("monitor"), B.get("fmt"), RS, SRC, B.get("crop")
    if old_imp:
        mon, fmt, crop = FR["monitor"], FR["fmt"], FR["crop"]
        RP = {**RS, **{k: FR["R"].get(k) for k in IMPORT_KEYS_SHOWN}}
        SRCP = FR["R"].get("sources") or {}
    elif DF.get("error") or (DF.get("older") and mode == "default"):
        RP = {**RS, **{k: R0.get(k) for k in IMPORT_KEYS_SHOWN}}
        SRCP = R0.get("sources") or {}
    return {"R0": R0, "RS": RS, "RP": RP, "SRCP": SRCP, "monitor": mon, "fmt": fmt, "crop": crop, "IMv": IMv,
            "old_imp": old_imp}


def typed_fields(S_f: dict, RP: dict, RS: dict) -> list:
    """The fields of step 2 whose value in S_f differs from the one they started from (RP): what the user typed,
    including a field set back to SMS's default (a manual swath or moisture value counts only while its box is ticked,
    now or in the import in use)."""
    return [k for k, v in S_f.items() if k in RP and not _same_value(RP.get(k), v)
            and not (k == "manual_swath_ft" and not (S_f.get("use_manual_swath") or RS.get("use_manual_swath")))
            and not (k == "manual_moisture_pct" and not (S_f.get("use_manual_moisture")
                                                           or RS.get("use_manual_moisture")))]


# the fields 'Apply to all' carries, in the order of step 2 (a box and its value go together)
CHANGE_GROUPS = (("test_weight_lb_bu",), ("dry_moisture_pct",), ("expand_dry_moisture",),
                 ("use_manual_swath", "manual_swath_ft"), ("use_manual_moisture", "manual_moisture_pct"),
                 ("min_yield",), ("max_yield",), ("start_delay_s",), ("stop_delay_s",), ("flow_shift_s",))


def _crop(p) -> str | None:
    """The crop key of a product (None: not known)."""
    return si.crop_key(p) if p else None


# where a product a file chose came from, kept in its import record ('product_from'): 0.3.0's step 1 gave one product
# to the files opened together; Apply to all gives the group of the file it was chosen on (amendment A1.2)
PRODUCT_FROM_030 = {"by": "0.3.0", "group": "0.3.0"}


def product_group(D: dict, B: dict | None) -> str:
    """Who gave a file the product it chose, as Apply to all compares it: the group its record keeps (given by Apply
    to all, or by 0.3.0's step 1), else the file itself ('data:<the product of its data>': chosen on that file)."""
    pf = (D.get("sms_import") or {}).get("product_from") if isinstance(D, dict) else None
    if isinstance(pf, dict) and pf.get("group"):
        return str(pf["group"])
    try:
        return f"data:{_crop(default_resolved(B or {}).get('product'))}"
    except ValueError:
        return "data:None"


def field_changes(changed, S: dict, R: dict) -> tuple:
    """What 'Apply to all' carries of the fields typed on a file (changed: their keys; S: the file's settings, R: their
    import): ([(keys, values)] in the order of step 2, values None for a field taken back (set to SMS's default: each
    file gets its own default for it again), the keys a product chosen filled in). A product chosen comes first:
    (("product",), {"product": its crop key}) for the product named (the product of the file's data included: each
    file it reaches gets that product), None for 'unknown' (taken back: each file it reaches goes back to its data's
    product); the weight to volume, dry moisture or limits it filled in are part of it, not values of their own (each
    file the product reaches gets that product's own, on its own basis)."""
    ch = set(changed or ())
    prod = "product" in ch
    src, dfl = R.get("sources") or {}, R.get("defaults") or {}
    out, borne = [], set()
    if prod:
        pk = _crop(S.get("product"))
        out.append((("product",), {"product": pk} if pk else None))
    for keys in CHANGE_GROUPS:
        if not ch.intersection(keys):
            continue
        k = keys[0]
        if k in si.RESOLVED_KEYS:
            back = src.get(k) != si.SRC_YOU or _same_value(R.get(k), dfl.get(k))
            if back and prod:
                borne.add(k)
                continue
            out.append((keys, None if back else {k: S.get(k)}))
        elif len(keys) == 2:                             # a manual swath or moisture: the box with its value
            out.append((keys, {k: True, keys[1]: S.get(keys[1])} if S.get(k) else None))
        elif k in FLAG_KEYS:
            out.append((keys, {k: True} if S.get(k) else None))
        else:                                            # a delay or the flow shift: 0 is SMS's default
            out.append((keys, None if _same_value(S.get(k), 0.0) else {k: float(S.get(k) or 0.0)}))
    return out, borne


def own_settings(Dt: dict, R0t: dict) -> dict:
    """A file's own import settings (mode custom: the product chosen, the values the user typed, the flags, delays and
    flow shift, changed_settings); {} for a file on its default import."""
    IM = Dt.get("sms_import") or {}
    if import_mode(Dt) != "custom" or not isinstance(IM.get("resolved"), dict):
        return {}
    return changed_settings({**IM["resolved"], "sources": IM.get("sources")}, R0t)


def _same_settings(a: dict, b: dict) -> bool:
    """Two sets of import settings are the same, key by key (sms_import.settings fills in the others)."""
    A, B_ = si.settings(a), si.settings(b)
    return all(((A[k] or None) == (B_[k] or None)) if k == "product" else _same_value(A[k], B_[k]) for k in A)


def _product_value(B: dict, p, k: str):
    """The value SMS's import gives the setting k of a file (its basis B) with the product p (None: its data's)."""
    try:
        R = si.resolve(si.settings({"product": p} if p else {}), p or (B or {}).get("crop"), (B or {}).get("monitor"),
                       (B or {}).get("fmt"))
    except ValueError:
        return object()                                  # (never the same as a value)
    return R.get(k)


def _left(out: dict, left: str, t: str, other, pt) -> None:
    """A file Apply to all leaves as it is, in the list of its kind: a file of another product or another choice of
    it (other: why the product, weight to volume or dry moisture typed do not go to it, as apply_to_all_plan's
    other_why_of says it; False: they do) in its own words."""
    if left == "same" and other:
        out["other_product"].append(t)
        out["other_of"][t] = pt
        out["other_why_of"][t] = other if isinstance(other, str) else out["other_why"]
    else:
        out[left].append(t)


def apply_to_all_plan(tag: str, S_f: dict, changed=None) -> dict:
    """What 'Apply to all N harvest files' does with the settings S_f of `tag` (amendment A1 of the redesign: a merge
    field by field). The change is the fields typed on `tag` (changed: their keys; default: typed_fields against what
    its fields started from), a field set back to SMS's default included ('taken back'). Every other harvest file
    starts from its own settings (its custom settings, none on its default) and gets only the fields changed: a field
    taken back is removed from its own settings; the weight to volume and dry moisture only when the product of its
    import in use is the product of `tag`'s import (after the change; 'not known' counts as one product). A product
    named (or taken back: 'unknown') on `tag` goes to the files that were what `tag` was before the change: the same
    product in their import in use and the same own choice of it (none: each on its data's product; or the same
    product chosen by the same hands, product_group: on a file of the same data, or given with `tag`'s by Apply to all
    or by 0.3.0's step 1; never a file of another product, nor one whose own product `tag` did not give it); it
    travels with its own weight to volume and dry moisture, and with the limits it filled in on `tag` where it changes
    them on the file's own basis, each file getting that product's values on its own basis (its other own settings
    stay). A file whose settings this leaves as they were, or whose import they give again, is left exactly as it is
    (import, own settings, cleaning).
    {"targets": {t: its settings}, "changes": {t: ['Max. yield volume none → 150.00', ...]}, "how": {t: 'custom' |
    'default' (back to its SMS default) | 'older_readings' (back to an older version's readings) | 'today' (an older
    rule's import replaced by today's rule plus the change)}, "same": left as they are (the change brings them
    nothing), "older": the same, on an older rule's import kept as their default (D7), "older_decode": the same, on the
    readings an older version decoded, "other_product": the same, of another product or another choice of it (the
    product, weight to volume or dry moisture typed do not go to them; "other_of": {t: the product of its import in
    use}, "other_why": 'product' | 'crop', "other_why_of": {t: why it is left: 'product' (another product), 'crop'
    (a weight to volume or dry moisture of another product), 'hand' (the same product chosen on it for its own data),
    'given' (given with another choice; "other_group": {t: that group}), 'data' (its data's own where `tag` had
    chosen it)}), "as_is": files not imported as SMS ('None'), left as they are, "pending": files whose data's crop
    could not be read yet (their readings away, or there but not readable: "why" in their basis), "away": files
    the change would reach whose readings are not at hand ("away_at": {t: where they were}; "away_in_work": those
    whose readings were inside the work folder; Apply on each once they are back), "failed": files on the readings
    their failed SMS import left (no import as SMS to change: Apply on each tries it again),
    "skipped": files of an older version that kept no record of their import, "unresolved": files whose settings
    could not be resolved ("unresolved_why": {t: the reason}); "product_to": the files the product goes to,
    "product_from": what their record keeps of where it came from (None: no product chosen)}. Planters are not
    listed. ValueError when `tag` keeps no record of its import."""
    D = ss.datasets[tag]
    B = import_basis(D)
    if B is None:
        raise ValueError(f"{tag} keeps no record of its import: open the data again (step 1) to change it")
    if B.get("pending"):
        raise ValueError(f"{tag}: {basis_pending_note(B)}")
    S_f = si.settings(S_f)
    R = si.resolve(S_f, S_f.get("product") or B.get("crop"), B.get("monitor"), B.get("fmt"))
    R0 = default_resolved(B)
    if changed is None:
        V = step2_start(D)
        changed = typed_fields(S_f, V["RP"], V["RS"])
    entries, borne = field_changes(changed, S_f, R)
    prod = _crop(R.get("product"))
    # what the file was before the change (the files a product chosen on it reaches): its product in use, its own
    # choice of it
    p_was, own_was = _crop(_in_use_product(D, B)), _crop(own_settings(D, R0).get("product"))
    g_was = product_group(D, B) if own_was else f"data:{_crop(R0.get('product'))}"
    p_new = next((v for k, v in entries if k == ("product",)), False)    # False: no product typed
    out = {"targets": {}, "changes": {}, "how": {}, "same": [], "older": [], "older_decode": [], "other_product": [],
           "other_of": {}, "other_why": "product" if p_new is not False else "crop", "other_why_of": {},
           "other_group": {}, "as_is": [], "failed": [], "skipped": [], "pending": [], "unresolved": [],
           "unresolved_why": {}, "away": [], "away_at": {}, "away_in_work": [], "product_to": [],
           "product_from": {"by": "all", "group": g_was} if p_new else None, "was": p_was, "now": prod}
    for t, Dt in ss.datasets.items():
        if t == tag:
            continue
        settle_basis(t)                                  # a basis not read yet, its readings back: read now
        Bt, DFt = import_basis(Dt), default_of(Dt)
        if not Dt.get("yield", True):
            continue                                     # a planter or sprayer file: not a harvest file
        if Bt is None:
            out["skipped"].append(t)                     # (a file of an older version that kept no record)
            continue
        if Bt.get("pending"):
            out["pending"].append(t)                     # (its data's crop not read yet: nothing to merge on)
            continue
        mode_t = import_mode(Dt)
        if mode_t == "as_is":
            # 'None' is its own choice: not SMS's import to change; on the readings a failed import left: none either
            out["failed" if failed_in_use(Dt) else "as_is"].append(t)
            continue
        if DFt.get("error") and mode_t != "custom":     # (own settings on a failed default: a file as any other)
            out["failed"].append(t)
            continue
        older_t = mode_t == "default" and bool(DFt.get("older")) and not DFt.get("older_decode")
        left = "older" if older_t else ("older_decode" if mode_t == "default" and DFt.get("older_decode") else "same")
        try:
            R0t = default_resolved(Bt)
            pt = _crop(_in_use_product(Dt, Bt))
            own = own_settings(Dt, R0t)
            merged = dict(own)
            own_p = _crop(own.get("product"))
            g_t = product_group(Dt, Bt) if own_p else None
            gets = (p_new is not False and pt == p_was and own_p == own_was and (own_p is None or g_t == g_was))
            # a product typed that does not go to this file, and why (amendment A1.3): another product; its product
            # chosen on it for its own data; given with another choice (Apply to all from another file, 0.3.0's
            # step 1); its data's own where this file had chosen it
            other = False
            if p_new is not False and not gets:
                pf_t = (Dt.get("sms_import") or {}).get("product_from")
                given = isinstance(pf_t, dict) and bool(pf_t.get("group"))
                other = ("product" if pt != p_was else ("given" if given else "hand") if own_p else "data")
                if other == "given":
                    out["other_group"][t] = g_t
            if gets:
                # the product with its own weight to volume, dry moisture and the limits it filled in (this file's
                # values of them for another product go; a limit of its own that the product does not change on this
                # file's basis stays)
                new_p = (p_new or {}).get("product")
                keep = {k: own[k] for k in borne if k in own and k not in ("test_weight_lb_bu", "dry_moisture_pct")
                        and _same_value(_product_value(Bt, own.get("product"), k), _product_value(Bt, new_p, k))}
                for k in ("product", "test_weight_lb_bu", "dry_moisture_pct", *borne):
                    merged.pop(k, None)
                merged.update(p_new or {})
                merged.update(keep)
            p_after = (_crop(merged.get("product")) or _crop(R0t.get("product"))) if gets else pt
            for keys, vals in entries:
                if keys == ("product",):
                    continue
                if keys[0] in CROP_SETTING_KEYS and p_after != prod:
                    other = other or "crop"
                    continue                             # another product's weight to volume or dry moisture
                if vals is None:
                    for k in keys:
                        merged.pop(k, None)
                else:
                    merged.update(vals)
            if _same_settings(merged, own):
                _left(out, left, t, other, pt)
                continue
            S_t = si.settings(merged)
            Rt = si.resolve(S_t, S_t.get("product") or Bt.get("crop"), Bt.get("monitor"), Bt.get("fmt"))
        except ValueError as e:
            out["unresolved"].append(t)
            out["unresolved_why"][t] = str(e)
            continue
        RSt = (Dt.get("sms_import") or {}).get("resolved")
        if isinstance(RSt, dict) and same_import(Rt, RSt):
            _left(out, left, t, other, pt)               # the import it already has
            continue
        src_t = ew.resolve_moved(Bt.get("all_readings"), ss.workdir) if Bt.get("all_readings") else None
        if not src_t or not os.path.exists(src_t):
            # the readings it would be imported from are not at hand (a drive not plugged in): named as left, with
            # the way to finish it, never as a file this changes
            out["away"].append(t)
            out["away_at"][t] = _where(src_t or Bt.get("all_readings"))
            if _in_folder(src_t or Bt.get("all_readings"), ss.workdir):
                out["away_in_work"].append(t)            # (inside the work folder: they cannot come back by themselves)
            continue
        out["targets"][t] = merged
        if gets:
            out["product_to"].append(t)
        out["changes"][t] = import_changes(RSt if isinstance(RSt, dict) else R0t, Rt)
        out["how"][t] = ("today" if older_t else
                         ("older_readings" if DFt.get("older_decode") else "default") if same_import(Rt, R0t) else
                         "custom")
    return out


def _them(names: list) -> tuple:
    """('it is', 'it') for one file, ('they are', 'them') for more."""
    return ("it is", "it") if len(names) == 1 else ("they are", "them")


def older_kept_line(names: list, after: bool = False) -> str:
    """The files Apply to all leaves on an older rule's import kept as their default (D7), in their own words."""
    one = len(names) == 1
    imp = "import" if one else "imports"
    return ((f"Kept on the older rule's {imp} (Apply on {'it' if one else 'each'} to update it): " if after else
             f"Apply to all keeps the older rule's {imp} of ") + ", ".join(names)
            + ("." if after else f" (Apply on {'it' if one else 'each'} to update it)."))


HOW_TAIL = {"default": "back on its SMS default", "older_readings": "back to the older version's readings, not SMS's "
            "default", "today": "its older rule's import replaced by today's rule plus this change"}


def plan_changes_text(P: dict, t: str) -> str:
    """'Max. yield volume none → 150.00; back on its SMS default': what Apply to all changes in a file it reaches."""
    return "; ".join(list(P["changes"].get(t) or []) + ([HOW_TAIL[P["how"][t]]] if P["how"].get(t) in HOW_TAIL
                                                         else []))


def plan_left_lines(P: dict, after: bool = False) -> list:
    """The files Apply to all leaves as they are, each kind in its own words, before the click (after: once done)."""
    out = []
    if P.get("same"):
        s = P["same"]
        out.append(f"Left as {_them(s)[0]} (this change brings {_them(s)[1]} nothing): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: this change brings {_them(s)[1]} nothing.")
    whys, groups = P.get("other_why_of") or {}, P.get("other_group") or {}
    kinds = []
    for kind in ("product", "crop", "hand", "given", "data"):
        s = [t for t in P.get("other_product") or [] if whys.get(t, P.get("other_why")) == kind]
        if kind == "given":
            # given with another choice: by 0.3.0's step 1 and by Apply to all are each told in their own words
            kinds += [(kind, x) for x in ([t for t in s if groups.get(t) == PRODUCT_FROM_030["group"]],
                                          [t for t in s if groups.get(t) != PRODUCT_FROM_030["group"]]) if x]
        elif s:
            kinds.append((kind, s))
    for kind, s in kinds:
        # each reason in its own words (amendment A1.3): another product; a weight to volume or dry moisture of
        # another product; the same product chosen on the file for its own data, given with another choice, or its
        # data's own where this file had chosen it
        one = len(s) == 1
        names = ", ".join(f"{t} (Product {P['other_of'].get(t) or 'unknown'})" for t in s)
        p_ = P["other_of"].get(s[0]) or "unknown"
        same_choice = "a product chosen here goes only to files whose product came from the same choice as this file's"
        if kind == "product":
            why = (f"{'it keeps its' if one else 'each keeps its'} own product; a product chosen here goes only to "
                   f"files that had this file's product ({P.get('was') or 'unknown'}) and the same own choice of it")
        elif kind == "crop":
            why = ("a weight to volume or dry moisture goes only to files of this file's product "
                   f"({P.get('now') or 'unknown'})")
        elif kind == "hand":
            data_ = ", ".join(sorted({str(_crop(default_resolved(import_basis(ss.datasets[t]) or {}).get("product"))
                                          or "not known") for t in s}))
            why = ((f"its {p_} was chosen on it for its own data ({data_})" if one else
                    f"the product of each was chosen on it for its own data ({data_})")
                   + f", not with this file's choice: {same_choice}")
        elif kind == "given":
            by_030 = groups.get(s[0]) == PRODUCT_FROM_030["group"]
            why = ((f"its {p_} was" if one else "the product of each was")
                   + (" given by 0.3.0's step 1 to the files opened together" if by_030 else
                      " given by Apply to all with another file's choice")
                   + f", not with this file's: {same_choice}")
        else:
            why = ((f"its {p_} is its data's own" if one else "the product of each is its data's own")
                   + f", where this file's was chosen: {same_choice}")
        out.append(f"Left as {_them(s)[0]}: {names}; {why}." if after else
                   f"Apply to all leaves {names} as {_them(s)[0]}: {why}.")
    if P.get("older"):
        out.append(older_kept_line(P["older"], after=after))
    for t in P.get("older_decode") or []:
        way = older_decode_way(ss.datasets.get(t) or {})
        out.append(f"{t} stays on the older version's readings (Older rule): this change brings it nothing; to get "
                   f"SMS's default, {way}." if after else
                   f"Apply to all leaves {t} on the older version's readings (Older rule): to get SMS's default, "
                   f"{way}.")
    if P.get("as_is"):
        s = P["as_is"]
        out.append(f"Left as {_them(s)[0]} (no import as SMS, 'None' in step 2): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: no import as SMS ('None' in step 2).")
    if P.get("failed"):
        s = P["failed"]
        one = len(s) == 1
        why = (f"{'its' if one else 'their'} SMS import failed: Apply on {'it' if one else 'each'} tries it again")
        out.append(f"Left as {_them(s)[0]} ({why}): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: {why}.")
    if P.get("skipped"):
        s = P["skipped"]
        one = len(s) == 1
        why = (f"{'it keeps' if one else 'they keep'} no record of {'its' if one else 'their'} import: open "
               f"{'its' if one else 'their'} data again (step 1)")
        out.append(f"Not imported again ({why}): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: {why}.")

    def why_unread(t):
        return (import_basis(ss.datasets.get(t) or {}) or {}).get("why")
    if [t for t in P.get("pending") or [] if not why_unread(t)]:
        s = [t for t in P["pending"] if not why_unread(t)]
        one = len(s) == 1
        why = (f"the crop of {'its' if one else 'their'} data could not be read yet ({'its' if one else 'their'} "
               f"readings are not at hand): reconnect the drive and open the work again, then Apply on "
               f"{'it' if one else 'each'}")
        out.append(f"Not imported again ({why}): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: {why}.")
    for t in [t for t in P.get("pending") or [] if why_unread(t)]:
        # there but not readable (held open by another program): its own reason, and the way on
        why = (f"the crop of its data could not be read yet ({why_unread(t)}): {unread_advice(why_unread(t))}, then "
               "Apply on it")
        out.append(f"Not imported again ({why}): {t}." if after else f"Apply to all leaves {t} as it is: {why}.")
    inw = set(P.get("away_in_work") or ())
    for s, gone in (([t for t in P.get("away") or [] if t not in inw], False),
                    ([t for t in P.get("away") or [] if t in inw], True)):
        if not s:
            continue
        one = len(s) == 1
        at_ = "; ".join(f"{t}: {(P.get('away_at') or {}).get(t)}" for t in s)
        why = ((f"{'its' if one else 'their'} readings are no longer in the work folder ({at_}): open "
                f"{'its' if one else 'their'} data again (step 1) to import {'it' if one else 'them'} with this "
                "change") if gone else
               (f"{'its' if one else 'their'} readings are not at hand ({at_}): reconnect the drive, then choose "
                f"{'it' if one else 'each'} in step 2 and Apply the same change on it"))
        out.append(f"Not imported again ({why}): {', '.join(s)}." if after else
                   f"Apply to all leaves {', '.join(s)} as {_them(s)[0]}: {why}.")
    for t in P.get("unresolved") or []:
        why = f"its settings could not be resolved ({(P.get('unresolved_why') or {}).get(t)}): Apply on it says why"
        out.append(f"Not imported again: {t} ({why})." if after else f"Apply to all leaves {t} as it is: {why}.")
    return out


def apply_to_all(tag: str, S_f: dict, progress=None, failed: list | None = None, warns: list | None = None,
                 changed=None) -> str:
    """'Apply to all N harvest files': the settings S_f on `tag`, and the fields changed on it (changed: their keys,
    as apply_to_all_plan) merged into the own settings of every other harvest file they reach, each line naming what
    changed in that file (its other own settings stay; a product chosen reaches only the files of the product `tag`
    had, with that product's own values; for another product, the weight to volume and dry moisture stay; its cleaning
    is set aside). A file the change brings nothing is left exactly as it is (its import, own settings and cleaning)
    and named; so are files not imported as SMS, on an older rule's import it does not reach, on the readings a failed
    SMS import left and files of an older version. progress(tag, i, n): before each file. failed: receives a line per
    other file that could not be imported (that file unchanged, with the way to finish it; without the list those
    lines join the others). warns: as apply_custom. A product chosen is recorded in each file it goes to as given by
    Apply to all (product_from). Returns the lines for the user."""
    P = apply_to_all_plan(tag, S_f, changed)
    targets = P["targets"]
    if progress:
        progress(tag, 1, len(targets) + 1)
    lines = [apply_custom(tag, S_f, warns=warns, product_from=P.get("product_from"))]
    for i, (t, S_t) in enumerate(targets.items()):
        if progress:
            progress(t, i + 2, len(targets) + 1)
        try:
            line = apply_custom(t, S_t, warns=warns,
                                product_from=P.get("product_from") if t in P["product_to"] else None)
            ch = plan_changes_text(P, t)
            lines.append(line + (f" Changed in {t}: {ch}." if ch else ""))
        except ValueError as e:
            msg = str(e) if str(e).startswith(t) else f"{t}: {e}"
            why = _error_reason(e.__cause__) if isinstance(e.__cause__, Exception) else default_failed_reason(t)
            if why:
                # its write failed (its own import, or its SMS default it goes back to): what to do and the way to
                # finish it, in place of 'try again' (Apply to all no longer reaches it once the others changed)
                tail = f"; {retry_advice(why)}"
                msg = (msg[:-len(tail)] if msg.endswith(tail) else msg) + f"; {finish_advice(why)}"
            (failed if failed is not None else lines).append(msg)
    lines += plan_left_lines(P, after=True)
    return " ".join(lines)


def _same_active(D: dict, DF: dict) -> bool:
    """The active import of a file is its default block's (same file, count and record)."""
    def norm(p):
        return os.path.normcase(os.path.abspath(str(p))) if p else ""

    def rec(x):
        return json.dumps(x, sort_keys=True, default=str)
    return (norm(D.get("shp")) == norm(DF.get("shp")) and int(D.get("n") or 0) == int(DF.get("n") or 0)
            and rec(D.get("sms_import")) == rec(DF.get("sms_import")))


def _label_crop(label) -> str | None:
    """The crop part of an extracted file's label ('<field> · <season> · <crop>'), None for 'crop?'."""
    parts = str(label or "").split(" · ")
    c = parts[-1].strip() if len(parts) >= 3 else ""
    return c if c and c != "crop?" else None


def basis_of_record(D: dict, legacy: bool = False) -> dict | None:
    """The basis of a file saved without one (a work of an earlier version): the file of all readings, the crop, the
    monitor's crop definition and the format (amendment A1.3). Raw data: the decode report's (raw_data_crop), never a
    product typed before extracting nor the crop the record names. A point export: always read from the export itself
    as a fresh open reads it (export_basis_now: its Deere metadata, then its Crop / Product column, a monitor product
    the record keeps), never the crop its record names; marked 'pending' while the export cannot be read. None for a
    planter or sprayer file, a folder rebuilt from its files (legacy), a file with the first import (the minimum
    only)."""
    IM = D.get("sms_import") if isinstance(D.get("sms_import"), dict) and D.get("sms_import") else None
    if legacy or not D.get("yield", True) or (D.get("import_min") and IM is None):
        return None
    if D.get("kind") == "raw":
        src = D.get("source") if isinstance(D.get("source"), dict) else {}
        allr = (IM or {}).get("all_readings") or src.get("decoded_shp") or (D.get("shp") if IM is None else None)
        if not allr:
            return None
        crop, mon = raw_data_crop(D)
        fmt = (IM or {}).get("fmt") or import_fmt(src or None)
        return {"all_readings": allr, "crop": crop, "monitor": mon, "fmt": fmt}
    if D.get("kind") != "export":
        return None
    # read from the export itself, never from the crop the record names (pending while it cannot be read)
    return export_basis_now(D, IM)


def raw_data_crop(D: dict) -> tuple:
    """(crop, monitor product) of the data of a raw file saved without a basis, from its decode report, as the data
    gives them (amendment A1.3). The report is the data's unless the decoder wrote the product it was given (0.3.0's
    step 1) as the task's crop (0.3.0's ISOXML reader: the report's crop is the product, its options name it, the
    label still names the task's crop): then the crop is the label's (None for 'crop?') and the report's monitor
    product, the product's, is not taken. A crop the record names is never taken: 0.3.0 recorded the product chosen
    there (its step 1, or its file panel on data that names no crop)."""
    IM = D.get("sms_import") if isinstance(D.get("sms_import"), dict) and D.get("sms_import") else {}
    rep = D.get("report") if isinstance(D.get("report"), dict) else {}
    src = D.get("source") if isinstance(D.get("source"), dict) else {}
    o = rep.get("options") if isinstance(rep.get("options"), dict) else {}
    lab = _label_crop(D.get("label"))
    named = rep.get("crop_name") or src.get("crop_name")
    oc = _crop(o.get("crop"))
    if oc and oc != _crop(lab) and _crop(named) == oc:
        return lab, None                                 # the decoder's crop is the product it was given
    mon = IM.get("monitor") if IM.get("monitor") is not None else rep.get("monitor_product")
    return named or lab, mon


def product_origin_030(D: dict) -> str | None:
    """Who gave the product of a file's import as 0.3.0 saved it (a record without a default block), as far as the
    record can tell (amendment A1.3): 'step1' (0.3.0's step 1 gave it: a raw file whose decode report names that
    product as the decoder's option; a point export whose record names no crop, as 0.3.0's open records it with
    step 1's product), 'maybe' (the record cannot tell: a point export whose record names the product as its crop,
    which 0.3.0's file panel writes both for step 1's product imported again and for a product chosen on data that
    names no crop; a record of an export with Deere metadata, identical either way), 'hand' (chosen in 0.3.0's file
    panel: the record keeps the data's crop, or the raw file was decoded with another product or none), or None (no
    product chosen)."""
    IM = D.get("sms_import") if isinstance(D.get("sms_import"), dict) else None
    p = _crop(((IM or {}).get("resolved") or {}).get("product"))
    if not p:
        return None
    if D.get("kind") == "raw":
        o = (D.get("report") or {}).get("options") if isinstance(D.get("report"), dict) else None
        return "step1" if isinstance(o, dict) and _crop(o.get("crop")) == p else "hand"
    if IM.get("crop") is None:
        return "step1"
    mon = IM.get("monitor") if isinstance(IM.get("monitor"), dict) else None
    if _crop(IM["crop"]) == p or (mon and _crop(IM["crop"]) == _crop(mon.get("crop"))):
        return "maybe"
    return "hand"


def step1_products_030(datasets: dict) -> list:
    """The products a saved work of 0.3.0 shows its step 1 gave (product_origin_030 'step1' of any of its files saved
    without a default block, or with one whose basis is still to be read, and what such a block kept of them): a
    product whose origin a record cannot tell counts as step 1's only when one of these is it (amendment A1.3)."""
    out = set()
    for D in (datasets or {}).values():
        if not isinstance(D, dict):
            continue
        DF = D.get("import_default") if isinstance(D.get("import_default"), dict) else {}
        pending = bool((DF.get("basis") or {}).get("pending"))
        if pending:
            out.update(DF.get("step1") or ())
        if (not DF or pending) and product_origin_030(D) == "step1":
            out.add(_crop(D["sms_import"]["resolved"]["product"]))
    return sorted(x for x in out if x)


def basis_pending(D: dict) -> bool:
    """The basis of a file of an earlier version could not be read yet (its export not at hand when the work was
    opened): nothing is known of its SMS default until its readings are back (settle_basis)."""
    return bool((default_of(D).get("basis") or {}).get("pending"))


BASIS_PENDING_NOTE = ("the crop of its data could not be read yet (its readings are not at hand): SMS's default "
                      "import of this file is told once they are back (reconnect the drive and open the work again); "
                      "the import in use stays as it is")


def basis_pending_note(B: dict | None) -> str:
    """Why the basis of a file could not be read yet, in the words of its cause: its readings away (BASIS_PENDING_NOTE),
    or there but not readable ('why': held open by another program, a read error), read again at the next action."""
    why = (B or {}).get("why") if isinstance(B, dict) else None
    if not why:
        return BASIS_PENDING_NOTE
    return (f"the crop of its data could not be read yet ({why}): {unread_advice(why)}; it is read again at the next "
            "action on this page, and the import in use stays as it is until then")


UNREAD_ADVICE = "check that the export is complete (its .shp, .shx and .dbf), or open its data again (step 1)"


def unread_advice(why: str | None) -> str:
    """What to do about an export that is there but could not be read for this reason, as retry_advice words a failed
    write: close the program that holds it (a file held open, access denied), else UNREAD_ADVICE (a part missing or
    damaged, a read that failed)."""
    return "close the program that holds it" if held_reason(why) else UNREAD_ADVICE


def basis_pending_note_of(D: dict) -> str:
    return basis_pending_note(default_of(D).get("basis"))


def classify_import(D: dict, legacy: bool = False, step1=None) -> dict:
    """The import mode of a file of a saved work, and (a work of an earlier version) a default block: record only,
    no file written (it runs when a work is opened). A planter or sprayer file, a rebuilt folder, a file with the
    first import: mode default, no basis. An export or raw file saved with the import off: mode as_is, its default
    built later (ensure_default). An import with no value of the user's, the flags off, no delay or flow shift and the
    data's own product (a raw file decoded as a fresh extraction decodes it): mode default, the default = the saved
    import (labelled 'older' when today's rule gives other values: kept as saved, D7). Any other: mode custom, its
    default built later; a product of 0.3.0's step 1 (product_origin_030; step1: the products the work shows its
    step 1 gave) gets the group '0.3.0', one chosen by hand none. A basis that cannot be read now (the export not at
    hand) is not taken as known: the block keeps it as pending, with no mode or group decided from it, and the file
    is classified once its readings are back. A work of this version keeps its mode, unless an earlier version
    imported the file again (its record no longer the default's)."""
    IM = D.get("sms_import") if isinstance(D.get("sms_import"), dict) and D.get("sms_import") else None
    DF = D.get("import_default")
    if isinstance(DF, dict) and DF and (DF.get("basis") or {}).get("pending"):
        step1 = sorted(set(DF.get("step1") or ()) | set(step1 or ()))
        D.pop("import_default", None)                    # read again: classified now when it can be read
        D.pop("import_mode", None)
        DF = None
    if isinstance(DF, dict) and DF:
        m = import_mode(D)
        if m == "default" and DF.get("shp") and not _same_active(D, DF):
            m = "custom" if IM else "as_is"
        D["import_mode"] = m
        return D
    B = None
    try:
        B = basis_of_record(D, legacy)
    except Exception:                                    # nothing to import it from: no switch in step 2
        B = None
    if B is None:
        D["import_default"] = {"shp": D.get("shp"), "n": D.get("n"), **stamp(D.get("shp")),
                               "sms_import": copy.deepcopy(IM)}
        D["import_mode"] = "default"
        return D
    if B.get("pending"):
        # not read yet: the import in use as saved, nothing decided from a crop not known
        D["import_default"] = {"basis": B, "step1": sorted(step1 or [])}
        if IM is None:
            D["import_mode"] = "as_is"
        return D
    if IM is None:
        D["import_default"] = {"basis": B}
        D["import_mode"] = "as_is"
        return D
    RS = IM.get("resolved") or {}
    try:
        R0 = default_resolved(B)
    except ValueError:
        R0 = {}
    plain = (not any(RS.get(k) for k in FLAG_KEYS)
             and all(abs(float(RS.get(k) or 0.0)) < 1e-9 for k in DELAY_KEYS))
    SRC = IM.get("sources")
    if isinstance(SRC, dict) and "sources" in IM:
        default = plain and si.SRC_YOU not in SRC.values() and (RS.get("product") or None) == (R0.get("product") or None)
        ref = R0
    else:                                                # a record without sources: compared as a fresh open
        default = plain
        FR = fresh_export_import(D) if D.get("kind") == "export" else None
        ref = FR["R"] if FR else R0
    if default and D.get("kind") == "raw" and decoded_with_choice(D):
        # readings decoded with a product or values of 0.3.0's step 1: not a fresh extraction's file, so no pointer
        # default; the default is decoded again from the raw data and the import in use stays (ensure_default)
        default = False
    if not default:
        p = _crop(RS.get("product"))
        if p and p != _crop(R0.get("product")):
            origin = product_origin_030(D)
            if origin == "step1" or (origin == "maybe" and p in set(step1 or ())):
                # 0.3.0's step 1 gave it (one product for the files opened together): Apply to all reaches them as
                # one; a product chosen by hand stays that file's own (group data:<its data's product>)
                IM["product_from"] = dict(PRODUCT_FROM_030)
        D["import_default"] = {"basis": B}
        D["import_mode"] = "custom"
        return D
    D["import_default"] = {"shp": D.get("shp"), "n": D.get("n"), **stamp(D.get("shp")),
                           "sms_import": copy.deepcopy(IM), "basis": B,
                           "older": import_changes(RS, ref, IMPORT_KEYS_SHOWN) or None}
    if D.get("kind") == "raw":
        D["import_default"]["source"] = copy.deepcopy(D.get("source"))
    D["import_mode"] = "default"
    return D


def settle_basis(tag: str) -> bool:
    """A file whose basis could not be read when its work was opened (basis_pending), once its readings are back:
    classified as at the open (classify_import), then the work saved. True when that was done now."""
    D = ss.datasets.get(tag)
    if not isinstance(D, dict) or not basis_pending(D):
        return False
    B = import_basis(D) or {}
    src = ew.resolve_moved(B.get("all_readings"), ss.workdir) if B.get("all_readings") else None
    if not src or not os.path.exists(src):
        # its readings away now: the reason it could not be read no longer holds (the words of readings not at hand)
        B.pop("why", None)
        return False
    classify_import(D)
    if basis_pending(D):
        return False
    save_current(quiet=True)
    return True


def _point_count(shp: str) -> int | None:
    try:
        import pyogrio
        return int(pyogrio.read_info(shp)["features"])
    except Exception:
        return None


def _build_key(tag: str) -> tuple:
    """What a failed build of a file's default import depends on: the work, its readings and the default's file,
    each with its time on disk."""
    D = ss.datasets.get(tag) or {}
    B, DF = import_basis(D) or {}, default_of(D)
    src = ew.resolve_moved(B.get("all_readings"), ss.workdir) if B.get("all_readings") else None
    return (str(ss.get("workdir")), str(src), mtime(src), str(DF.get("shp")), mtime(DF.get("shp")))


# a full Windows path in an error message (C:\... or C:/..., \\server\... or //server/...): its folders (spaces and
# dots allowed; none of them a space before another path), then a file name up to its extension when a space, a
# quote, ',', ';', ')' or ': ' (or the end) follows it; a path with no such file name: up to a quote, ': ', another
# path or the end
_PATH_START = r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\|(?<![:\w])//)"
_PATH_CHAR = r"(?:(?!\s" + _PATH_START + r")[^'\"\n\\/:])"
_PATH_IN_TEXT = re.compile(_PATH_START + r"(?:(?:" + _PATH_CHAR + r"*[\\/])*" + _PATH_CHAR
                           + r"*?\.[A-Za-z0-9]{1,5}(?=[\s'\",;)]|:\s|:$|$)"
                           + r"|[^'\"\n]*?(?=['\"]|: |:$|\n|$|\s" + _PATH_START + r"))")


def _error_reason(e: BaseException) -> str:
    """'PermissionError: Access is denied': an error in a few words (no Windows error number, no full path: a path in
    the message, as GDAL's 'Failed to create file C:/.../x.shp: ...', is named by its file name only)."""
    if isinstance(e, OSError) and e.strerror:
        return f"{type(e).__name__}: {e.strerror}"
    msg = re.sub(r"\[(?:WinError|Errno) \d+\]\s*", "", str(e))
    msg = _PATH_IN_TEXT.sub(lambda m: ntpath.basename(m.group(0).rstrip("\\/ ")) or "a folder", msg)
    return f"{type(e).__name__}: {msg}".strip()


def finish_advice(why: str | None) -> str:
    """The way to finish a file Apply to all could not import (its write failed for this reason): what retry_advice
    says to do, then Apply on that file (Apply to all no longer reaches it once the others changed)."""
    a = retry_advice(why)
    lead = a[:-len(" and try again")] + ", then " if a.endswith(" and try again") else ""
    return f"{lead}choose it in step 2 and Apply the same change on it"


def held_reason(why: str | None) -> bool:
    """The reason (_error_reason) is a file held open by another program or an access denied (the words retry_advice
    tests for a failed write)."""
    w = str(why or "").lower()
    return any(x in w for x in ("permissionerror", "permission denied", "access is denied",
                                "being used by another process", "sharing violation"))


def retry_advice(why: str | None) -> str:
    """What to do about a write that failed for this reason (_error_reason): close the program that holds its files
    (a file held open, access denied), free disk space (a full disk), else try again (step 1 keeps the reason)."""
    w = str(why or "").lower()
    if any(x in w for x in ("permissionerror", "permission denied", "access is denied", "being used by another process",
                            "sharing violation")):
        return "close the program that holds its files and try again"
    if any(x in w for x in ("no space left", "not enough space", "disk full", "disk is full")):
        return "free disk space and try again"
    return "try again (step 1 keeps the reason)"


def default_failed_reason(tag: str) -> str | None:
    """Why SMS's default import of a file could not be made in this session (the error in a few words), while its
    files are as they were then; None otherwise."""
    f = (ss.get("default_failed") or {}).get(tag)
    if isinstance(f, (tuple, list)) and len(f) == 2 and tuple(f[0]) == _build_key(tag):
        return str(f[1])
    return None


def default_needs_build(tag: str, retry: bool = False) -> bool:
    """The default import of a harvest file with a basis is missing, or its file no longer matches it (its count, or
    its content when its time on disk changed: an earlier version imported the file again under the default's name),
    and its readings are there to build it from; or it was built from readings an older version decoded with a
    product while the raw data was not at hand, and the raw data is back. A file whose time alone changed (a work
    copied or unzipped without its files' times) is the same import: its new time is kept, nothing is built again. A
    block without a content signature (an earlier build of 0.3.1) whose import is an older rule's, in use: kept as
    saved (D7). A build that failed is not tried again in this session while its files are as they were (retry: an
    action of the user's tries it again; opening the work again does too). A basis not read yet is read first, once
    its readings are back (settle_basis); until then nothing is built."""
    settle_basis(tag)
    D = ss.datasets.get(tag) or {}
    B = import_basis(D)
    if not D.get("yield", True) or B is None or B.get("pending"):
        return False
    DF = default_of(D)
    if DF.get("error"):
        return False
    if not retry and default_failed_reason(tag) is not None:
        return False
    src = ew.resolve_moved(B["all_readings"], ss.workdir)
    if not src or not os.path.exists(src):
        return False
    shp = DF.get("shp")
    if not shp:
        return True                                      # never built (a work of an earlier version)
    if DF.get("older_decode") and DF.get("raw_gone"):
        root = _raw_root(D)
        if root and os.path.isdir(root):
            return True                                  # the raw data is back: decoded again for SMS's default
    if not os.path.exists(shp):
        # gone from disk: built again while another import is on screen; the file on screen itself gone has no
        # default to fall back to (step 2 says so and offers to remove the file)
        return os.path.normcase(os.path.abspath(str(D.get("shp") or ""))) != os.path.normcase(os.path.abspath(shp))
    if DF.get("mtime") is not None and abs(mtime(shp) - float(DF["mtime"])) > 2.0:
        if DF.get("sig"):
            if content_sig(shp) != DF["sig"]:
                return True
        elif not (DF.get("older") and import_mode(D) == "default" and _same_active(D, DF)):
            return True
        DF.update(stamp(shp))                            # the same file, another time on disk
    n = _point_count(shp)
    return DF.get("n") is not None and n is not None and n != int(DF["n"])


def _rebase_own_import(tag: str, D: dict, B: dict, src: str, rep_dec: dict | None, folder: str) -> bool:
    """Own settings (mode custom) made from the readings an older version decoded with a product, once the raw data
    was decoded again for SMS's default (decode_default): the import in use made again from the new readings with the
    values step 2 shows (what Apply with nothing typed imports), under a temporary name. When that is the import in
    use reading for reading (the same settings, the same content), the record follows the new readings: the file in
    use and its cleaning stay, and step 2 no longer says it was made from an older decode (it is decided by content,
    not by the readings' path). The temporary file goes either way. True when the record follows them."""
    IM = D.get("sms_import") or {}
    RS = IM.get("resolved")
    if not isinstance(RS, dict) or not D.get("shp") or not os.path.exists(D["shp"]):
        return False
    S = {k: RS.get(k) for k in si.DEFAULTS}
    if not S.get("use_manual_moisture"):
        S["manual_moisture_pct"] = None                  # empty: the dry moisture, as the field gives it
    nxt = _next_path(folder, tag, in_use=(D.get("shp"), default_of(D).get("shp")))
    try:
        S = si.settings(S)
        R = si.resolve(S, S.get("product") or B.get("crop"), B.get("monitor"), B.get("fmt"))
        if not same_import(R, RS):
            return False
        labels = crop_labels(D, B, R, rep=rep_dec, src=src)
        _remove_files(_parts(os.path.splitext(nxt)[0]))
        rep = si.apply(src, nxt, R, labels=labels, keep_crop=label_keep(D, R))
        sig = content_sig(rep["path"])
        if sig is None or sig != content_sig(D["shp"]):
            return False
    except Exception:                                    # not made: the import in use stays as it is
        return False
    finally:
        _remove_files(_parts(os.path.splitext(nxt)[0]))
    DF = default_of(D)
    rec = _import_record(R, rep, src, B.get("monitor"), B.get("fmt"), B.get("crop"))
    rec["mode"] = "custom"
    if isinstance(IM.get("product_from"), dict):
        rec["product_from"] = dict(IM["product_from"])  # the same product: where it came from stays
    D["sms_import"] = rec
    _follow_default_decode(D, DF)                        # the decode the import is now made from
    if D.get("kind") == "raw" and isinstance(DF.get("source"), dict):
        D["source"] = _summary_crop(source_with_import(DF["source"], R, rep.get("applied"), src_shp=src,
                                                       report=D.get("report")),
                                    labels if rep.get("relabelled") else None)
    return True


def ensure_default(tag: str, retry: bool = False) -> str | None:
    """Builds the default import of a file when it is missing or no longer matches its file (default_needs_build):
    SMS's default settings on its readings, <decoded or imported>/<tag>_imported_default.shp; a raw file's source
    with that import's options. A raw file an earlier version decoded with a product (or its own weight and moisture)
    is first decoded again from its raw data as a fresh extraction decodes it (decode_default): its default is then
    what a fresh open of the same data gives, never the readings of that product; when the raw data is not at hand,
    the default is built from those readings and labelled as the older version's ('Older rule'), not as SMS's
    default. A file in mode default then reads it too: when that changes the data in use (the raw data back, or the
    default's file changed on disk), the cleaning made on the earlier data is set aside (as an Apply does), said in
    step 1's note and in the work message. Saves the work. Returns a note for step 1 when the default cannot be built
    (its readings gone, the import failed: said once, the build is not tried again on every run of the page) or when
    it was decoded again or set a cleaning aside, else None."""
    settle_basis(tag)
    D = ss.datasets.get(tag)
    B = import_basis(D or {})
    if not D or B is None or not D.get("yield", True):
        return None
    if B.get("pending"):
        return basis_pending_note(B)                      # nothing is built from a crop not read yet
    DF = default_of(D)
    src = ew.resolve_moved(B["all_readings"], ss.workdir)
    if not src or not os.path.exists(src):
        return DEFAULT_GONE_NOTE if not (DF.get("shp") and os.path.exists(DF["shp"])) else None
    if not default_needs_build(tag, retry=retry):
        return None
    failed = ss.setdefault("default_failed", {})
    # the data in use when it is the default (mode default): what its cleaning was made from (the file is replaced):
    # the default's content as recorded, or its file as it is now
    was_older = bool(DF.get("older_decode"))
    had = import_mode(D) == "default" and has_cleaning(tag)
    old_sigs = ({DF.get("sig"), content_sig(D.get("shp"))} - {None}) if had else set()
    # the files the default and the import in use were, with their readings (removed below once nothing names them)
    prev = (D.get("shp"), (D.get("sms_import") or {}).get("all_readings"), DF.get("shp"),
            (DF.get("basis") or {}).get("all_readings"))
    dec, older_decode, why_old, raw_gone = None, None, None, False
    choice = decoded_with_choice(D)
    if choice:
        try:
            dec = decode_default(tag, D)
        except Exception as e:                           # the raw data gone or refused: the readings as they are
            root = _raw_root(D)
            raw_gone = not (root and os.path.isdir(root))
            # a reason in a few words (no folder path); once the raw data is back it is decoded again
            older_decode = choice
            why_old = ("its raw data is not at hand" if raw_gone
                       else f"its raw data could not be decoded again ({type(e).__name__})")
    rep_dec = None
    if dec is not None:
        rep_dec = dec["report"]
        crop_d = rep_dec.get("crop_name") or _label_crop(D.get("label")) or None
        B = {"all_readings": dec["shp"], "crop": None if crop_d is None else str(crop_d),
             "monitor": copy.deepcopy(rep_dec.get("monitor_product")), "fmt": rep_dec.get("format") or B.get("fmt")}
        src = dec["shp"]
    R0 = default_resolved(B)
    folder = os.path.join(ss.workdir, "decoded" if D.get("kind") == "raw" else "imported")
    os.makedirs(folder, exist_ok=True)
    labels = crop_labels(D, B, R0, rep=rep_dec, src=src)  # a file an earlier version decoded with another product
    # written under a temporary name and swapped in once complete: the default may be the import in use
    nxt = _next_path(folder, tag, in_use=(D.get("shp"), DF.get("shp")))
    _remove_files(_parts(os.path.splitext(nxt)[0]))
    try:
        rep = si.apply(src, nxt, R0, labels=labels, keep_crop=label_keep(D, R0))
    except Exception as e:
        _remove_files(_parts(os.path.splitext(nxt)[0]))
        # said once; not tried again until its files change (the reason stays for step 1's import line)
        failed[tag] = (_build_key(tag), _error_reason(e))
        return (f"SMS's default import of this file could not be made ({_error_reason(e)}): step 1 shows the "
                "import in use")
    note_swap = None
    if os.path.normcase(os.path.abspath(rep["path"])) != os.path.normcase(os.path.abspath(src)):
        path, w = _swap_in(nxt, os.path.join(folder, f"{tag}{DEFAULT_SUFFIX}.shp"))
        rep = {**rep, "path": path}
        note_swap = "; ".join(w) or None
    rec = _import_record(R0, rep, src, B.get("monitor"), B.get("fmt"), B.get("crop"))
    if D.get("kind") == "export" and B.get("crop") is None and B.get("monitor") is None:
        # read again from its readings, as a fresh open notes it (0.3.0 never read the column with step 1's product)
        try:
            note = data_crops(src)[1]
        except Exception:                                # (no note)
            note = None
    else:
        note = (DF.get("sms_import") or D.get("sms_import") or {}).get("crops_note")
    if note:
        rec["notes"].append(note)
        rec["crops_note"] = note
    new = {"shp": rep["path"], "n": int(rep["n_out"]), **stamp(rep["path"]), "sms_import": rec,
           "basis": dict(B), "error": None, "older": None}
    if older_decode:
        new.update({"older": [why_old], "older_decode": older_decode, "raw_gone": raw_gone})
    if D.get("kind") == "raw":
        if dec is not None:
            base, rep_src = dec["source"], rep_dec
            new.update({"report": rep_dec, "zip": dec.get("zip")})
        else:
            base = DF.get("source") if isinstance(DF.get("source"), dict) else D.get("source")
            rep_src = DF.get("report") if isinstance(DF.get("report"), dict) else D.get("report")
            if isinstance(DF.get("report"), dict):
                new.update({"report": DF["report"], "zip": DF.get("zip")})
        new["source"] = _summary_crop(source_with_import(base, R0, rep.get("applied"), src_shp=src, report=rep_src),
                                      labels if rep.get("relabelled") else None)
    D["import_default"] = new
    notes = [note_swap] if note_swap else []
    if not note_swap:
        # swapped in: an import a swap blocked earlier left under a temporary name, referenced by nothing, goes
        prev += tuple(os.path.join(folder, s_ + ".shp") for s_ in _next_stems(folder, tag))
    back = was_older and not older_decode                # the raw data is back: decoded again for SMS's default
    IMu = D.get("sms_import") or {}
    other_readings = (dec is not None and import_mode(D) == "custom" and bool(IMu.get("all_readings"))
                      and _norm_p(ew.resolve_moved(IMu["all_readings"], ss.workdir)) != _norm_p(src))
    if other_readings and _rebase_own_import(tag, D, B, src, rep_dec, folder):
        # own settings made from the older readings give the same import from the new ones: it stays, made from them
        # (the older readings stay on disk until an action of the user's replaces that import)
        old_r = _norm_p(ew.resolve_moved(IMu["all_readings"], ss.workdir))
        prev = tuple(x for x in prev if not (x and _norm_p(ew.resolve_moved(x, ss.workdir)) == old_r))
        if back:
            notes.append("its raw data is back: SMS's default import (step 1) was decoded again from it; the import "
                         "in use (step 2) is the same, reading for reading, from those readings, so it and its "
                         "cleaning stay")
        back = False
    if import_mode(D) == "default":
        D["shp"], D["n"], D["sms_import"] = new["shp"], new["n"], copy.deepcopy(rec)
        if "source" in new:
            D["source"] = copy.deepcopy(new["source"])
        _follow_default_decode(D, new)
        if had and new.get("sig") not in old_sigs:
            # the cleaning was made on other data than the default made now: set aside, as an Apply does
            why = ("its raw data is back: SMS's default import was decoded again from it, and the cleaning made on "
                   "the older version's readings was set aside: clean it again in step 3" if back else
                   "SMS's default import of this file was made again (its file had changed on disk), and the "
                   "cleaning made on the earlier file was set aside: clean it again in step 3")
            warn = drop_cleaning(tag)
            work_msg_line(tag, why)
            notes.append(why + "".join(f"; {w}" for w in warn))
        elif back:
            notes.append("its raw data is back: SMS's default import was decoded again from it")
    elif back:
        notes.append("its raw data is back: SMS's default import (step 1) was decoded again from it; the import in "
                     "use (step 2) stays")
    notes += drop_unreferenced(tag, prev)                # (the older version's readings and import, now unused)
    failed.pop(tag, None)
    save_current(quiet=True)
    return "; ".join(notes) or None


def reapply_after_extract(made: dict, warn=None) -> list:
    """A file extracted again from the same input: its custom import (step 2) applied again on the new default, or a
    line that a file once as the monitor logged it is now SMS's default. Returns the status lines; warn(line): each
    warning of the import again (a file held open), else they join its line."""
    lines = []
    for t in list(made):
        what = (ss.datasets.get(t) or {}).pop("_reapply", None)
        if not what:
            continue
        if what[0] == "custom":
            try:
                w = []
                apply_custom(t, what[1], warns=w, product_from=what[2] if len(what) > 2 else None)
                lines.append(f"{t}: your import settings were applied again" + ("" if warn else _set_aside(False, w)))
                for w_ in w if warn else []:
                    warn(f"{t}: {w_}")
            except ValueError as e:
                D_t = ss.datasets.get(t) or {}                 # the earlier own import, referenced no more, goes
                w = delete_custom_import(t, keep=(D_t.get("shp"), default_of(D_t).get("shp")))
                lines.append(f"{t}: your import settings could not be applied again ({e})"
                             + ("" if warn else _set_aside(False, w)))
                for w_ in w if warn else []:
                    warn(f"{t}: {w_}")
        else:
            lines.append(f"{t}: extracted again with SMS's default (it was as the monitor logged it)")
    return lines


def width_audit(df: pd.DataFrame) -> list:
    """The header width each combine logged: [{combine, logged width (ft) = the widest width logged by at least
    HEADER_SHARE of its readings (else the most common), readings at it (%), wider (%), within 1 ft below (%) = the
    width trimmed by the overlap, narrower (%) = more than 1 ft narrower: partial passes and sections off, narrowest
    (ft), widest (ft)}] (the shares add up to 100); [] without a width column."""
    det = yc.detect_columns([c for c in df.columns if c not in ("lon", "lat")])
    wcol = det.get("width_ft")
    if not wcol or wcol not in df:
        return []
    w = pd.to_numeric(df[wcol], errors="coerce").round(1)
    key = None
    if det.get("machine"):
        key = df[det["machine"]].astype(str).to_numpy()
    elif det.get("dataset"):
        dm = sms.dataset_machines(df[det["dataset"]])
        key = np.asarray(dm[0]).astype(str) if dm is not None else None
    if key is None:
        key = np.full(len(df), "all readings")
    rows = []
    for m, g in pd.DataFrame({"m": key, "w": w.to_numpy(float)}).groupby("m"):
        v = g["w"].dropna()
        v = v[v > 0]
        if not len(v):
            continue
        share = v.value_counts(normalize=True)
        big = share[share >= HEADER_SHARE]
        # the header: the widest width a material share of the readings logged (a monitor that trims the width by
        # the overlap logs most readings a little narrower than the header); else the most common width
        full = float(big.index.max()) if len(big) else float(share.index[0])
        rows.append({"combine": str(m), "logged width (ft)": full, "readings at it (%)": 100 * float((v == full).mean()),
                     "wider (%)": 100 * float((v > full + 0.05).mean()),
                     "within 1 ft below (%)": 100 * float(((v < full - 0.05) & (v >= full - 1.0 - 1e-9)).mean()),
                     "narrower (%)": 100 * float((v < full - 1.0 - 1e-9).mean()), "narrowest (ft)": float(v.min()),
                     "widest (ft)": float(v.max())})
    return rows


HEADER_SHARE = 0.05              # a width logged by at least 5 % of a combine's readings can be its header's


def width_audit_box(df: pd.DataFrame):
    """Step 1: the header width as logged, per combine, to check against the real header."""
    WA = width_audit(df)
    if not WA:
        return
    ws_ = sorted({float(r["logged width (ft)"]) for r in WA})
    with st.expander("Header width: " + (f"{ws_[0]:g} ft" if len(ws_) == 1 else f"{ws_[0]:g}-{ws_[-1]:g} ft")
                     + (f" ({len(WA)} combines)" if len(WA) > 1 else ""), type="compact"):
        st.dataframe(pd.DataFrame(WA), hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%.1f")
                                    for c in ("logged width (ft)", "readings at it (%)", "wider (%)",
                                              "within 1 ft below (%)", "narrower (%)", "narrowest (ft)", "widest (ft)")})
        widths = sorted({r["logged width (ft)"] for r in WA})
        st.caption("The width the monitor logged on each reading: SMS and OCED use it (the manual swath of the import "
                   "settings is used only when 'Manual swath' is ticked). The logged width taken as the header's is "
                   f"the widest one at least {100 * HEADER_SHARE:g} % of the combine's readings logged (else the most "
                   "common): a monitor that trims the width by the overlap logs many readings up to 1 ft narrower "
                   "(within 1 ft below); more than 1 ft narrower are partial passes or sections off. "
                   + (f"The combines logged different widths ({', '.join(f'{x:g}' for x in widths)} ft): check each "
                      "header. " if len(widths) > 1 else "")
                   + "The bu/ac of a manual swath are scaled by logged / manual; the grain mass is kept. If it is not "
                     "your header's width, switch off SMS's default in step 2, tick Manual swath, set the real width "
                     "and Apply.")


def _same_value(a, b) -> bool:
    """Two settings values are the same: None only equals None, numbers within 1e-6, else equal."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    try:
        return abs(float(a) - float(b)) <= 1e-6
    except (TypeError, ValueError):
        return str(a) == str(b)


def import_as_sms(shp: str, tag: str, folder: str, crop=None, monitor=None, fmt=None, R=None, S=None):
    """The data as SMS imports it (its Processing Settings S, SMS's defaults when None: every file opens with them;
    the empty values filled in as SMS does for this source, engine/sms_import.resolve with the crop, the monitor's
    crop definition and the format): engine/sms_import.apply writes <folder>/<tag>_imported.shp (the kept records
    byte for byte, the recomputed cells patched). Returns (path, n imported or None, the record of the import or
    None); the file itself when the import is off or changes nothing. A point file naming more than one crop is
    imported with no product (nothing converted) and its record says so."""
    S = si.settings(S or {})
    if not S["on"]:
        return shp, None, None
    note = None
    if crop is None and monitor is None and not S.get("product"):
        crop, note = data_crops(shp)
    if not (isinstance(R, dict) and "sources" in R):
        R = si.resolve(S, crop, monitor, fmt)
    os.makedirs(folder, exist_ok=True)
    rep = si.apply(shp, os.path.join(folder, f"{tag}_imported.shp"), R)
    rec = _import_record(R, rep, shp, monitor, fmt, crop)
    if note:
        rec["notes"].append(note)
        rec["crops_note"] = note
    return rep["path"], int(rep["n_out"]), rec


def extract(cand, chosen_units, opts, kw, log, warn=None):
    """The chosen units as one shapefile per field, season and crop (engine.run.decode on each group), each imported
    as SMS imports it with its Processing Settings untouched (the default import of the file, kept beside the active
    one: import_default). The decoder gets the one-sided shrink of SMS's import; a John Deere file or ISOXML task
    data keeps the crop of the file and its values (as SMS); any other source gets the product's. The import then
    resolves its settings with the decode report's crop definition (monitor_product) or, for a Case IH / New Holland
    card, its SMS product (crop_name). A group whose crop has no weight on the card is decoded again with SMS's
    values for data without a product (a warning says so: the product can be chosen in step 2); a group the decoder
    still refuses (ValueError) is passed to warn and the others go on; a group whose import fails is the decoded
    readings as they are (mode as_is, its default marked 'error'). A tag another raw input of this work already has
    gets a suffix instead of replacing that file; the same input extracted again replaces its file (and its cleaning
    moves to superseded/); a custom import of the replaced file is applied again after the extraction
    (reapply_after_extract, made[tag]['_reapply'])."""
    groups = {}
    for u in chosen_units:
        groups.setdefault((u.field or "", u.year, str(u.crop or "").strip().lower()), []).append(u)
    made, failed = {}, []
    S_i = si.settings({})
    fmt = cand.get("decoder")
    root = os.path.normcase(os.path.abspath(cand["probe"].root))
    for (field, year, crop), us in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0, kv[0][2])):
        base = er.candidate_tag(cand, us)
        tag = fit_tag(base)
        if tag.casefold() in {m.casefold() for m in made}:         # the same field and season in two crops
            tag = fit_tag(f"{fit_tag(base, max(6, tag_budget() - 12))}_{crop or 'crop'}")
        prev = next((t for t in ss.datasets if t.casefold() == tag.casefold()), None)
        if prev is None and tag.casefold() in {str(t).casefold() for t in (ss.get("away") or {})}:
            tag = free_tag(tag, cand["probe"].root, also=made)   # a file set aside (its points away) keeps its tag
        reapply = None
        if prev is not None:
            D_p = ss.datasets[prev]
            r_prev = (ew.input_root(D_p, ss.workdir) if hasattr(ew, "input_root")
                      else (D_p.get("report") or {}).get("input_root"))
            if D_p.get("kind") != "raw" or (r_prev and os.path.normcase(os.path.abspath(r_prev)) != root):
                tag = free_tag(tag, cand["probe"].root, also=made)   # another input's file: both are kept
            else:
                tag = prev                                         # the same input again: it replaces its file
                # its own import settings (step 2) are applied again on the new default; as logged: said
                if import_mode(D_p) == "custom" and import_basis(D_p) and D_p.get("sms_import"):
                    IMp = D_p["sms_import"]
                    try:
                        R0p = default_resolved(import_basis(D_p))
                        reapply = ("custom", si.settings(changed_settings(
                            {**(IMp.get("resolved") or {}), "sources": IMp.get("sources")}, R0p)),
                            IMp.get("product_from"))      # where its own product came from stays (A1.3)
                    except ValueError:
                        reapply = None
                elif import_mode(D_p) == "as_is" and not failed_in_use(D_p):
                    reapply = ("as_logged", None)
        # the user's import of a file whose settings are applied again: replaced by that import (its swap says once
        # when a program holds it open), not deleted here first
        old_own = ss.datasets[prev].get("shp") if (reapply and reapply[0] == "custom") else None
        log(f"extracting {field or '(no field)'} {year or ''} ({len(us)} unit(s)) ...")
        kw_g = dict(kw)
        if isinstance(kw.get("totals_only"), (list, tuple)):
            # the tasks with totals only of THIS field and season (each file's Summary holds its own field's)
            want = {str(x) for x in kw["totals_only"]}
            kw_g["totals_only"] = [r["id"] for r in totals_only_of(cand, us) if str(r["id"]) in want] or None
        where = f"{field or '(no field)'} {year or ''}"
        d, no_product, err0 = decode_for_default(cand, [u.id for u in us], opts, crop, kw_g, ss.workdir, tag, log,
                                                 where)
        if d is None:
            if warn is None:
                raise err0
            failed.append(f"{where}: {err0}")
            warn(failed[-1])
            continue
        d.pop("df", None)
        drop_cleaning(d["tag"])                          # extracted again: its old cleaning no longer applies
        rep = d["report"]
        if no_product:
            rep.setdefault("warnings", []).append(no_product)
            if isinstance(d.get("source"), dict):
                d["source"]["warnings"] = list(d["source"].get("warnings") or []) + [no_product]
            log(no_product)
            if warn is not None:
                warn(no_product)
        t = rep.get("totals") or {}
        mon = rep.get("monitor_product")
        fmt_d = rep.get("format") or fmt
        crop_i = rep.get("crop_name") or crop or None
        err_i = None
        try:
            R_i = si.resolve(S_i, crop_i, mon, fmt_d)
            shp_i, n_i, rec = import_as_sms(d["shp"], d["tag"], os.path.join(ss.workdir, "decoded"), crop=crop_i,
                                            monitor=mon, fmt=fmt_d, R=R_i)
        except Exception as e:                            # the decoded readings as they are; step 2 tries again
            shp_i, n_i, rec, err_i = d["shp"], None, None, f"{type(e).__name__}: {e}"
            w = (f"{d['tag']}: SMS's import failed ({err_i}): the decoded readings are used as they are; step 2 can "
                 "try the import again")
            log(w)
            if warn is not None:
                warn(w)
        if rec:
            log(f"import as SMS: {rec['n_all'] - rec['n_in']:,} of {rec['n_all']:,} readings left out"
                + (" (" + ", ".join(f"{k} {v:,}" for k, v in rec["left_out"].items()) + ")" if rec["left_out"] else "")
                + f"; {rec['settings']}; where the values came from: {sources_line(rec)}")
        al = rep.get("alignment")
        if isinstance(al, dict) and al:
            log("grain and moisture of the readings: " + ", ".join(f"{k} {v:,}" if isinstance(v, (int, float))
                                                                    else f"{k} {v}" for k, v in al.items()))
        if prev is not None and tag == prev:
            dd = os.path.join(ss.workdir, DEFAULT_DECODE_DIR, "decoded")          # an earlier default's decode
            for w_ in (_remove_files(p for s_ in ("_decoded", "_decode_report")
                                     for p in _parts(os.path.join(dd, d["tag"] + s_)))
                       + delete_custom_import(d["tag"], keep=(shp_i, d["shp"], old_own))):   # the user's import
                log(f"{d['tag']}: {w_}")
                if warn is not None:
                    warn(f"{d['tag']}: {w_}")
        n_d = n_i if n_i is not None else d["n"]
        made[d["tag"]] = {"tag": d["tag"], "shp": shp_i, "zip": d["zip"], "n": n_d,
                          "kind": "raw", "op": "harvest", "yield": True,
                          "label": f"{field or '(no field)'} · {year or 'no season'} · {crop or 'crop?'}",
                          "source": d["source"], "report": rep, "area_ac": t.get("area_ac"),
                          "units": [u.label for u in us], "sms_import": rec,
                          "inputs_left_out": list(rep.get("inputs_left_out") or []),
                          "import_default": {"shp": shp_i, "n": n_d, **stamp(shp_i),
                                             "sms_import": copy.deepcopy(rec), "source": copy.deepcopy(d["source"]),
                                             "basis": {"all_readings": d["shp"],
                                                       "crop": rec.get("crop") if rec else crop_i,
                                                       "monitor": copy.deepcopy(mon), "fmt": fmt_d},
                                             "error": err_i},
                          "import_mode": "as_is" if err_i else "default"}
        if reapply:
            made[d["tag"]]["_reapply"] = reapply
    if not made and failed:
        raise ValueError("; ".join(failed))
    return made


def decode_for_default(cand, unit_ids, opts, crop, kw: dict, out: str, tag: str, log, where: str) -> tuple:
    """The units decoded for SMS's default import (extract; decode_default): the decoder gets the one-sided shrink of
    SMS's import; a John Deere file and ISOXML task data keep the file's crop and values, any other source the
    product's lb/bu and moisture (crop: the units' crop as the input names it). A crop the card gives no weight (a
    partial card copy, a crop number it does not list) is decoded again with SMS's values for data without a product;
    the product can be chosen in step 2. Writes <out>/decoded/<tag>_decoded.*. (the decode or None, the line saying
    it was decoded with the no-product values or None, the decoder's error or None)."""
    S_i = si.settings({})
    fmt = cand.get("decoder")
    sh = "symmetric" if S_i["expand_dry_moisture"] else "one_sided"
    if si.format_family(fmt) in si.FILE_CROP_FAMILIES:
        opts_g = dataclasses.replace(opts, shrink=sh)
    else:
        R_pre = si.resolve(S_i, crop, None, fmt)
        opts_g = dataclasses.replace(
            opts, shrink=sh,
            test_weight_lb_bu=R_pre["test_weight_lb_bu"] if R_pre["product"] else opts.test_weight_lb_bu,
            std_moisture_pct=R_pre["dry_moisture_pct"] if R_pre["product"] else opts.std_moisture_pct)
    d, err0, no_product = None, None, None
    try:
        d = er.decode(cand, list(unit_ids), opts_g, out, log=log, tag=tag, **kw)
    except ValueError as e:
        err0 = e
    if d is None and "test_weight_lb_bu" in str(err0):
        tw_n, sm_n = no_product_values()
        try:
            d = er.decode(cand, list(unit_ids), dataclasses.replace(
                opts_g, test_weight_lb_bu=tw_n, std_moisture_pct=sm_n), out, log=log, tag=tag, **kw)
            no_product = f"{where}: " + NO_PRODUCT_DECODE.format(tw_n, sm_n)
        except ValueError:
            d = None
    return d, no_product, err0


def no_product_values() -> tuple:
    """(lb/bu, dry moisture %) SMS gives data without a product (engine/formats/isoxml.py ISO_SMS_NO_PRODUCT)."""
    try:
        from engine.formats import isoxml
        return tuple(float(x) for x in isoxml.ISO_SMS_NO_PRODUCT)
    except Exception:                                    # the reader not loadable: SMS's values
        return 56.0, 13.0


def inputs_left_out_of(D: dict) -> list:
    """The inputs left out when the data of a file of the work was opened (a damaged zip among the zips given): the
    file's own list, else the work's (a file extracted before it was kept per file)."""
    if isinstance(D, dict) and isinstance(D.get("inputs_left_out"), list):
        return [str(w) for w in D["inputs_left_out"]]
    return [str(w) for w in (ss.get("left_out") or [])]


def clean_one(tag: str, sset: dict, log=lambda m: None) -> dict:
    """The SMS 3-sigma sequence on one extracted file (yield_clean through engine.run.clean, method sms3sigma; the
    file's boundary, grower's data and combine factor from settings_of), then <tag>_sms3s_clean.shp / .zip in
    clean_shapefiles/, and next to it the same readings as a shapefile for DIFM (write_difm): with the adjusted yield,
    <tag>_sms3s_clean_adjusted_DIFM.zip, when the cleaning adjusted it (the default of step 4's question), else
    <tag>_sms3s_clean_DIFM.zip; the other one, of an earlier cleaning, is removed (difm_new_cleaning).
    'Validate only' (scale_ticket.use 'validate'): the engine writes no adjusted yields (Yld_Level,
    Yld_Lvl_Sy) and applies no combine factor because of the weight; dbf_drop_fields / record_without_level only act
    on what an older engine would still write."""
    D = ss.datasets[tag]
    if not D.get("yield", True):
        return clean_applied(tag, sset, log=log)
    refresh_boundary(tag)
    out = os.path.join(ss.workdir, "clean", tag)
    cdir = os.path.join(ss.workdir, "clean_shapefiles")
    os.makedirs(cdir, exist_ok=True)
    with cleaning_guard(tag, out, [os.path.join(cdir, f"{tag}_sms3s_clean")],
                        files=[os.path.join(cdir, f"{tag}_sms3s_clean" + e)
                               for e in (ed.ZIP_SUFFIX, ed.ADJUSTED_ZIP_SUFFIX)]) as lg_state:
        lg = guarded_log(log, lg_state)
        settings = settings_of(tag, sset)
        R = er.clean(D["shp"], out, settings, log=lg, source=D.get("source"),
                     inputs_left_out=inputs_left_out_of(D))
        F = R["files"]
        src = os.path.splitext(F["difm_ready_shp"])[0]
        stem = os.path.join(cdir, os.path.basename(src))     # <tag>_sms3s_clean, the name the report gives
        G = ss.grower.get(tag) or {}
        adjusted = bool(settings.get("scale_ticket")) and G.get("use", "validate") == "adjust"
        box = {}

        def finish():
            box["dropped"] = [] if adjusted else dbf_drop_fields(stem + ".dbf", LEVEL_COLUMNS)
            box["zip"] = zip_shapefile(stem + ".shp", stem + ".zip")
        publish_set(src, stem, er.SHP_EXTS, then=finish)
        dropped = box["dropped"]
        if dropped:
            R = record_without_level(R, dropped)
        res = {"R": R, "shp": stem + ".shp", "zip": box["zip"], "flagged_shp": F.get("flagged_shp"),
               "flagged_zip": F.get("flagged_zip"), "report_pdf": F.get("report_pdf"), "json": F.get("json"),
               "settings": dict(sset), "config": file_config(tag, sset), "adjusted": adjusted, "dropped": dropped,
               "boundary": boundary_of(tag) if settings.get("aoi") else None, "kind": "sms",
               "at": dt.datetime.now().strftime("%H:%M:%S")}
        difm_new_cleaning(tag, res)
    return finish_cleaning(tag, res, lg_state)


def difm_map_column(R: dict | None) -> str | None:
    """The column a harvest cleaning names the one to map (engine/run.py recommended_yield_column), for the warning
    of its shapefile for DIFM when that file does not carry it; None when the record cannot say."""
    if not R:
        return None
    try:
        return er.recommended_yield_column(R)[0]
    except Exception:                                    # noqa: BLE001 - only names the column in a warning
        return None


DIFM_RECORD = "shapefile_for_difm"       # the cleaning record's entry: which shapefile for DIFM was generated


def difm_adjustment(clean_shp: str | None, R: dict | None, kind: str | None = None) -> dict | None:
    """What a harvest cleaning adjusted the yield by, with the column of its clean shapefile that carries it
    (engine/difm.py adjustment_of: Yld_Harm = the clean dry yield x the combine factor; Yld_Level = the clean dry yield
    x the combine factor x L when the grower's weight was used to adjust). None when the cleaning adjusted nothing (no
    combine factor applied, no grower's weight or one used to validate only), for a planter / sprayer file, and when
    the clean shapefile does not hold the column. With it step 4 asks which yield the shapefile for DIFM carries."""
    if kind == "a3" or not clean_shp or not R:
        return None
    try:
        return ed.adjustment_of(R, ed.field_names(clean_shp))
    except Exception:                                    # noqa: BLE001 - a file or record that cannot say: no question
        return None


def difm_yield_of(C: dict, adj: dict | None) -> str:
    """The yield the shapefile for DIFM of a cleaning carries, 'monitor' (3-sigma only) or 'adjusted': 'monitor' when
    the cleaning adjusted nothing (adj None); else the choice of step 4 (C['difm_yield']); else the one its cleaning
    record says was generated (a work opened again keeps the choice); else 'adjusted', the default."""
    if adj is None:
        return "monitor"
    pick = C.get("difm_yield")
    if pick not in ed.YIELDS:
        rec = (C.get("R") or {}).get(DIFM_RECORD)
        pick = rec.get("yield") if isinstance(rec, dict) else None
    return pick if pick in ed.YIELDS else "adjusted"


def difm_note_record(C: dict, W: dict | None, adj: dict | None):
    """The cleaning record (JSON) of a cleaning that adjusted the yield says which shapefile for DIFM was generated
    (the one of the choice of step 4) and what the adjustment was: R['shapefile_for_difm'] = {file, yield, label,
    line, column (of the clean file, in Yld_Vol_Dr), adjustment {column, combine factors, level ...}, other_file}.
    Only that entry of the JSON changes (written through a temporary file). Nothing is recorded for a cleaning that
    adjusted nothing (one file, the monitor's yield), for a write that failed, or when the record cannot be written
    (the session keeps the choice)."""
    R = C.get("R")
    if adj is None or not isinstance(R, dict) or not W or not W.get("zip") or W.get("error"):
        return
    which = "adjusted" if W.get("yield") == "adjusted" else "monitor"
    rec = {"file": os.path.basename(W["zip"]), "yield": which, "label": ed.yield_label(which, adj),
           "line": ed.yield_line(which, adj),
           "column": adj["column"] if which == "adjusted" else adj.get("monitor_column"),
           "adjustment": {k: adj.get(k) for k in ("column", "parts", "combine", "level", "per_machine_level", "what")},
           "other_file": os.path.basename(ed.zip_path_for(C["shp"], which != "adjusted"))}
    if R.get(DIFM_RECORD) == rec:
        return
    R[DIFM_RECORD] = rec
    p = C.get("json")
    if not p or not os.path.isfile(p):
        return
    tmp = os.path.join(os.path.dirname(p), "~difm_record.tmp")
    try:
        with open(p, encoding="utf-8") as fh:
            J = json.load(fh)
        if J.get(DIFM_RECORD) == rec:
            return
        J[DIFM_RECORD] = rec
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(J, fh, indent=1, default=yc._json_default)
        os.replace(tmp, p)
    except (OSError, ValueError):                        # the record is held open or unreadable: the session has it
        pass
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def difm_basis(tag: str, R: dict | None) -> dict:
    """What the import of the file `tag` knows, for the fields of the shapefile for DIFM that its clean file does not
    hold (engine/difm.py import_basis): the weight to volume of the import the cleaning ran with (its record R), when
    that import computed the file's yields with it; the crop it read; and, for an Operations Center export, the field
    and the combines its metadata names (the '-Deere-Metadata.json' beside the file the import read, found again
    under a moved work folder)."""
    D = ss.datasets.get(tag) if tag else None
    IM = D.get("sms_import") if isinstance(D, dict) else None
    p = IM.get("all_readings") if isinstance(IM, dict) else None
    try:
        p = ew.resolve_moved(p, ss.workdir) if p else None
    except Exception:                                    # noqa: BLE001 - no path to look beside: no metadata
        p = None
    return ed.import_basis(R, imported=p)


def write_difm(tag: str, clean_shp: str, R: dict | None, kind: str | None = None, which: str | None = None) -> dict:
    """The clean file of `tag` as a shapefile for DIFM (engine/difm.py), next to its clean shapefile in
    clean_shapefiles/; a harvest in the layout of an SMS shapefile export (write_zip): `which` 'adjusted' (the
    default when the cleaning adjusted the yield, difm_adjustment) writes <clean shapefile>_adjusted_DIFM.zip with the
    adjusted yield, 'monitor' <clean shapefile>_DIFM.zip with the monitor's (3-sigma only; the only one for a cleaning
    that adjusted nothing); a planter / sprayer file (kind 'a3') <clean shapefile>_DIFM.zip with its own columns and
    its dates as dBASE dates (write_applied_zip). A field of the layout that a harvest's clean file does not hold is
    filled from what the file's import knows (difm_basis), else left empty. The clean shapefile itself is never
    touched. Returns the writer's
    result, with error None; when it cannot be written, {zip: None, error, yield} (the cleaning stands and its clean
    shapefile is handed out; a DIFM zip of that name of an earlier cleaning of the file is removed, so that none of
    another cleaning is offered)."""
    R = R or {}
    adj = difm_adjustment(clean_shp, R, kind)
    which = "monitor" if adj is None else (which if which in ed.YIELDS else "adjusted")
    zp = ed.zip_path_for(clean_shp, which == "adjusted")
    src = (ss.datasets.get(tag) or {}).get("source")
    try:
        if kind == "a3":
            W = ed.write_applied_zip(clean_shp, zp, source=src)
        else:
            W = ed.write_zip(clean_shp, zp, source=src, columns=R.get("columns"), map_column=difm_map_column(R),
                             adjustment=adj, adjusted=which == "adjusted", basis=difm_basis(tag, R))
        W["error"] = None
        return W
    except Exception as e:                               # noqa: BLE001 - the cleaning stands without this file
        try:
            if os.path.isfile(zp):
                os.remove(zp)
        except OSError:
            pass
        msg = str(e) if isinstance(e, (ValueError, OSError)) else f"{type(e).__name__}: {e}"
        return {"zip": None, "error": msg, "yield": which, "notes": [], "warnings": []}


def difm_new_cleaning(tag: str, res: dict):
    """A cleaning just made (res, its result): its shapefile for DIFM is written with the default yield (the adjusted
    one when the cleaning adjusted the yield: each new cleaning starts from the default, as its question in step 4),
    the cleaning record says which, and the DIFM zip of the other name, which an earlier cleaning of the file left, is
    removed so that clean_shapefiles/ holds none of another cleaning (it is written again when step 4's choice asks
    for it)."""
    kind = res.get("kind")
    adj = difm_adjustment(res["shp"], res.get("R"), kind)
    which = difm_yield_of(res, adj)
    res["difm"] = write_difm(tag, res["shp"], res.get("R"), kind, which)
    if kind != "a3":
        other = ed.zip_path_for(res["shp"], which != "adjusted")
        try:
            if os.path.isfile(other):
                os.remove(other)
        except OSError:                                  # held open: step 4 writes it again before offering it
            pass
        difm_note_record(res, res["difm"], adj)


def difm_of(tag: str, C: dict) -> dict | None:
    """The shapefile for DIFM of a cleaning (write_difm): for a harvest whose cleaning adjusted the yield the one of
    the choice of step 4 (difm_yield_of: the adjusted yield by default; the other file, when it was written, stays
    where it is). None without a clean shapefile. A cleaning to clean again (C['clean_again']: an older version's, or
    files replaced) gets none: {zip: None, blocked: the reason}. Else its zip when it is there and not older than the
    clean shapefile: the writer's result of this session, or (a work opened again, a choice changed back) the zip read
    back with its warnings (engine/difm.py read_zip, nothing written); else written now (a work cleaned by an earlier
    version of OCED, a clean shapefile changed since, a zip not in this layout or written by an earlier version with
    15 decimals, a choice not written yet). The
    cleaning record is told which one was generated (difm_note_record). A write that failed is not tried again for
    the same clean shapefile and choice until the user asks (step 4's 'Write it again', retry_difm)."""
    if not C.get("shp") or not os.path.exists(C["shp"]):
        return None
    if C.get("clean_again"):
        return {"zip": None, "error": None, "blocked": C["clean_again"], "notes": [], "warnings": []}
    a3_ = C.get("kind") == "a3"
    R = C.get("R") or {}
    adj = difm_adjustment(C["shp"], R, C.get("kind"))
    which = difm_yield_of(C, adj)
    zp = ed.zip_path_for(C["shp"], which == "adjusted")
    base = os.path.splitext(C["shp"])[0]
    newest = max(mtime(base + e) for e in (".shp", ".shx", ".dbf"))
    W = C.get("difm")
    if W and W.get("error") and W.get("for") == newest and W.get("yield", which) == which:
        return W                                             # failed on this clean shapefile already
    if os.path.isfile(zp) and mtime(zp) >= newest:
        if W and W.get("zip") == zp and W.get("error") is None:
            difm_note_record(C, W, adj)
            return W
        try:
            W = ed.read_zip(zp, applied=a3_, map_column=None if a3_ else difm_map_column(R),
                            columns=R.get("columns"), adjustment=adj, adjusted=which == "adjusted")
            W["error"] = None
            C["difm"] = W
            difm_note_record(C, W, adj)
            return W
        except ValueError:                               # not this layout (another version's zip): written again
            pass
    W = write_difm(tag, C["shp"], C.get("R"), C.get("kind"), which)
    W["for"] = newest
    C["difm"] = W
    difm_note_record(C, W, adj)
    return W


def difm_question(tag: str, C: dict) -> dict | None:
    """Step 4, where the shapefile for DIFM of a harvest file is generated: when its cleaning adjusted the yield (a
    combine factor applied and / or the grower's weight used to adjust), the choice of the yield the file carries,
    3-sigma only (the monitor's) or the adjusted one (the default); the answer is kept in C['difm_yield'] (difm_of
    then writes or shows that file). No question, and None, for a cleaning that adjusted nothing, a planter / sprayer
    file and a cleaning to clean again. The question is keyed by the cleaning (the clean file's time), so each new
    cleaning starts from the default; a work opened again starts from the choice its cleaning record holds. Returns
    the adjustment (difm_adjustment)."""
    if C.get("clean_again") or not C.get("shp") or not os.path.exists(C["shp"]):
        return None
    adj = difm_adjustment(C["shp"], C.get("R"), C.get("kind"))
    if adj is None:
        C.pop("difm_yield", None)
        return None
    opts = ["monitor", "adjusted"]
    C["difm_yield"] = st.radio(
        "Shapefile for DIFM: which yield does it carry?", opts, index=opts.index(difm_yield_of(C, adj)),
        format_func=lambda k: ed.yield_label(k, adj), horizontal=True,
        key=f"difm_y_{file_key(tag)}_{key_of(str(mtime(C['shp'])))}",
        help="The cleaning adjusted the yield: " + adj["what"] + ". Adjusted: the file DIFM reads carries that yield. "
             "3-sigma only: the monitor's yield as cleaned. Each choice has its own file name (About the file for "
             "DIFM).")
    return adj


def retry_difm(tag: str):
    """'Write it again' (a callback): the failed write of the shapefile for DIFM of `tag` is forgotten, so that step 4
    writes it on this run."""
    C = (ss.get("cleaned") or {}).get(tag)
    if C:
        C.pop("difm", None)


def raised_by_oced(e: BaseException) -> bool:
    """Whether an exception was raised by a 'raise' statement of OCED's own code (app/ or engine/: a plain message for
    the user) rather than inside a library (numpy, pandas ...) or by an operation OCED's code made (int(NaN), arrays
    of two lengths, max([]), an unpacking ...): a ValueError of that kind is a defect, shown with its traceback. A
    builtin or a numpy operation raises from C, without a frame of its own, so its last frame is the OCED line that
    called it: what tells them apart is the instruction that raised (RAISE_VARARGS), not the file."""
    import dis
    import linecache
    tb, last = e.__traceback__, None
    while tb is not None:
        last, tb = tb, tb.tb_next
    if last is None:
        return True
    code = last.tb_frame.f_code
    f = os.path.normcase(os.path.abspath(code.co_filename))
    if not any(f.startswith(os.path.normcase(os.path.join(ROOT, d)) + os.sep) for d in ("app", "engine")):
        return False
    try:
        op = next((i.opname for i in dis.get_instructions(code) if i.offset == last.tb_lasti), None)
    except Exception:                                        # noqa: BLE001 - then the source line tells
        op = None
    if op is not None:
        return op == "RAISE_VARARGS"
    return linecache.getline(code.co_filename, last.tb_lineno).lstrip().startswith("raise")


class FileInUse(ValueError):
    """A file the cleaning must replace is held open by another program, or another tab is cleaning the same file."""


LOCK_NAME, LOCK_STALE_S = ".oced_cleaning.lock", 3 * 3600.0


def pid_alive(pid: int) -> bool:
    """Whether a process with this id runs on this computer (Windows: OpenProcess + GetExitCodeProcess; elsewhere
    signal 0). True when it cannot be told, so that a lock is only dropped when its process is surely gone."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, int(pid))         # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return ctypes.GetLastError() == 5                # access denied: it exists
            try:
                code = ctypes.c_ulong()
                ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
                return not ok or code.value == 259               # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        except Exception:                                    # pragma: no cover
            return True
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:                                          # pragma: no cover - exists, not ours
        return True
    return True


def lock_is_stale(p: str) -> bool:
    """A cleaning lock left by a run that can no longer be running: older than LOCK_STALE_S, written by another start
    of this app's server (its window was closed during a cleaning), or by a process that is gone (a crash, a power
    loss). A lock of this server is a cleaning in another tab of it: not stale."""
    try:
        if dt.datetime.now().timestamp() - os.path.getmtime(p) > LOCK_STALE_S:
            return True
        with open(p, encoding="utf-8") as fh:
            txt = fh.read().strip()
    except OSError:
        return False
    parts = txt.split(" ", 1)
    try:
        pid = int(parts[0])
    except ValueError:
        return False                                         # being written this moment (or not ours): wait
    if pid == os.getpid():
        return len(parts) > 1 and parts[1].strip() != server_token().split(" ", 1)[1]
    return not pid_alive(pid)


WIN_PATH_MAX = 259               # the longest path Windows opens without long-path support. A constant, also on a
                                 # computer where long paths are turned on: OCED's outputs must open in Explorer, SMS
                                 # and QGIS on any computer, and PATH_LIMIT (250, the budget of every path this app
                                 # writes) rests on the same limit
REOPEN_ADVICE = "Open the raw data again (step 1): a new work gets a short folder and file name."


class PathTooLong(ValueError):
    """A file the cleaning writes or replaces would sit on a path longer than Windows opens."""


def _too_long(e: OSError, *paths) -> bool:
    """Whether `e` comes from a path past what Windows opens (not from a file held open by another program)."""
    if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33):
        return False
    return (getattr(e, "winerror", None) == 206 or "too long" in str(e).lower()
            or any(len(os.path.abspath(q)) > WIN_PATH_MAX for q in paths))


def _long_path_msg(p: str, what: str, advice: str | None = None) -> str:
    """'<what> would be N characters long, over the 259 Windows opens (<path>).' and what to do: `advice`, else
    REOPEN_ADVICE."""
    q = os.path.abspath(p)
    return (f"{what} would be {len(q)} characters long, over the {WIN_PATH_MAX} Windows opens ({q}). "
            + (REOPEN_ADVICE if advice is None else advice))


def _new_work_len(workdir: str) -> int:
    """How long the folder of a new work of the same input would be (Open in step 1): WORKSPACE, the time stamp
    (YYYYmmdd-HHMMSS_) and as much of the input's name as the name of `workdir` holds, WORK_FOLDER_CHARS at most."""
    name = len(os.path.basename(os.path.abspath(workdir))) - 16
    return len(os.path.join(os.path.abspath(WORKSPACE), "")) + 16 + min(max(name, 1), WORK_FOLDER_CHARS)


def clean_depth(wd_len: int, n: int, harvest: bool = True) -> int:
    """The longest path a cleaning of a file whose tag has n characters writes or moves in a work folder of wd_len
    characters, a cleaning again included (cleaning_guard.deepest): its report, clean/<tag>/<tag> + LONGEST_OUTPUT (a
    harvest file) or + engine/clean/applied3s.py REPORT_SUFFIX (an as-applied file), the name publish_set moves the
    clean set handed out to, clean_shapefiles/<tag>_sms3s_clean (_3s_clean) + its longest extension + .bak, and its
    shapefile for DIFM (engine/difm.py, written under a shorter temporary name): for a harvest file the longer of its
    two names, clean_shapefiles/<tag>_sms3s_clean_adjusted_DIFM.zip (the adjusted yield; whether a cleaning adjusts
    it is only known once it ran), for an as-applied file <tag>_3s_clean_DIFM.zip."""
    report = len(os.sep + "clean" + os.sep + os.sep) + 2 * n + len(LONGEST_OUTPUT if harvest else a3.REPORT_SUFFIX)
    bak = (len(os.sep + "clean_shapefiles" + os.sep) + n + len("_sms3s_clean" if harvest else "_3s_clean")
           + max(len(e) for e in tuple(er.SHP_EXTS) + (".zip",)) + len(".bak"))
    difm = len(os.sep + "clean_shapefiles" + os.sep) + n + len("_sms3s_clean_adjusted_DIFM.zip" if harvest else
                                                                "_3s_clean_DIFM.zip")
    return wd_len + max(report, bak, difm)


def clean_tag_room(wd_len: int, harvest: bool = True) -> int:
    """The most characters a file's tag may have for the file to be cleaned, and cleaned again, in a work folder of
    wd_len characters (clean_depth within WIN_PATH_MAX); 0 when no tag fits."""
    return max((n for n in range(1, 61) if clean_depth(wd_len, n, harvest) <= WIN_PATH_MAX), default=0)


def workspace_room() -> int:
    """The longest workspace folder in which any new work can clean, and clean again, a harvest file whose tag has
    TAG_FLOOR characters (the most tag_budget gives in a folder that deep): clean_depth within WIN_PATH_MAX for a work
    folder name of the full 16 + WORK_FOLDER_CHARS characters."""
    return WIN_PATH_MAX - (1 + 16 + WORK_FOLDER_CHARS) - clean_depth(0, TAG_FLOOR)


def workspace_advice(room: int | None = None, what: str = "a cleaning", as_deep: bool = True) -> str:
    """What to do when the workspace folder itself is too deep (a new work in it would be as deep): a shorter
    workspace (of at most `room` characters, default workspace_room) through the environment variable OCED_WORKSPACE,
    which OCED reads when it starts (WORKSPACE), or, when the workspace is the 'workspace' folder inside OCED's own
    folder, OCED installed closer to the drive's root. setx changes the programs started after it, not the Command
    Prompt it is typed in, so OCED is started again from Explorer or a new window. The saved works (list_works) and
    cn1_card_names.json (write_native's registry) are read from WORKSPACE: they stay in the old folder unless moved.
    as_deep False leaves out that a new work would be as deep (when the caller has just said to open the data
    again)."""
    ws = os.path.abspath(WORKSPACE)
    env = bool(os.environ.get("OCED_WORKSPACE"))
    how = ("set OCED_WORKSPACE to a short folder (in a Command Prompt: setx OCED_WORKSPACE C:\\OCED_work; setx reaches "
           "the programs started after it, not that Command Prompt), close OCED's black window, start OCED again with "
           "a double click on run_oced.bat (or from a new Command Prompt) and open the raw data again (step 1)")
    keep = (f" The saved works and cn1_card_names.json (the Case IH card names already given, so that none is given "
            f"twice) stay in {ws}: to keep them, move them into the new folder while OCED is closed.")
    return (f"The workspace folder {ws} is {len(ws)} characters long ("
            + ("set by the environment variable OCED_WORKSPACE" if env else
               "the folder 'workspace' inside OCED's folder")
            + ("): a new work in it would be as deep, and " if as_deep else "): ")
            + f"{what} needs a workspace folder of at most "
              f"{workspace_room() if room is None else room} characters. "
            + ("To move it, " + how + "." if env else
               "To give OCED a shorter one, " + how + "; or install OCED in a folder closer to the drive's root "
               "(INSTALAR.txt).") + keep)


def deep_work_msg(workdir: str | None, files: dict | None = None) -> str:
    """Step 1, before anything is cleaned: '' when every file of the work, `files` ({tag: True for a harvest file,
    False for an as-applied one}), can be cleaned and cleaned again in the work folder `workdir` (clean_depth within
    WIN_PATH_MAX); before any file is extracted, when a harvest file whose tag has TAG_FLOOR characters can (the most
    tag_budget gives in a folder that deep; where it gives more, every file fits). Else the warning: the longest names
    of each kind that can be (clean_tag_room), the files of the work that are longer, and what to do: open the raw
    data again when a new work fits them (its tags at most TAG_FLOOR characters, as in cleaning_guard.advice), else a
    shorter workspace."""
    if not workdir:
        return ""
    wd = os.path.abspath(workdir)
    n = len(wd)
    bad = {t: h for t, h in (dict(files or {}) or {"x" * TAG_FLOOR: True}).items()
           if clean_depth(n, len(t), h) > WIN_PATH_MAX}
    if not bad:
        return ""
    k_h, k_a = clean_tag_room(n, True), clean_tag_room(n, False)       # k_a >= k_h: an as-applied set is shorter
    room = ("No file can be cleaned and cleaned again in it." if not k_a else
            "In it no harvest file can be cleaned and cleaned again, and an as-applied file only when its name has at "
            f"most {k_a} characters." if not k_h else
            f"In it a file can be cleaned and cleaned again only when its name has at most {k_h} characters (an "
            f"as-applied file: {k_a}).")
    names = sorted(bad, key=str.casefold)
    which = (f" {'The file' if len(names) == 1 else 'The files'} {', '.join(names)} of this work "
             f"{'is' if len(names) == 1 else 'are'} longer." if files else "")
    fits = all(clean_depth(_new_work_len(wd), min(len(t), TAG_FLOOR), h) <= WIN_PATH_MAX for t, h in bad.items())
    return (f"This work's folder is {n} characters long, and Windows opens a path of at most {WIN_PATH_MAX} "
            f"characters. {room}{which} " + (REOPEN_ADVICE if fits else workspace_advice()))


def _held_open(paths, advice: str | None = None) -> str | None:
    """The first of `paths` that another program holds open (Windows refuses to rename it), else None. The trial
    rename never lengthens a path past what Windows opens (a short name in the same folder then); a path that is too
    long raises PathTooLong (with the length of the path that is: the file's own, or the short name's when the folder
    is too deep even for it; `advice` = what to do, else REOPEN_ADVICE) instead of being reported as held open. A
    file that cannot be renamed back raises FileInUse with both its names (it is left under the check's name)."""
    for p in paths:
        if not os.path.isfile(p):
            continue
        tmp = p + ".oced_chk"
        if len(os.path.abspath(tmp)) > WIN_PATH_MAX:
            tmp = os.path.join(os.path.dirname(p),
                               "~" + hashlib.md5(os.path.basename(p).encode("utf-8")).hexdigest()[:8] + ".chk")
        try:
            os.replace(p, tmp)
        except OSError as e:
            if _too_long(e, p, tmp):
                if len(os.path.abspath(p)) > WIN_PATH_MAX:
                    raise PathTooLong("Nothing was changed: "
                                      + _long_path_msg(p, os.path.basename(p), advice)) from None
                raise PathTooLong(f"Nothing was changed: {os.path.basename(p)} cannot be checked for another program "
                                  f"holding it open: the check renames it for a moment, to {os.path.basename(tmp)} in "
                                  "its folder, and that path" + _long_path_msg(tmp, "", advice)) from None
            return p
        try:
            os.replace(tmp, p)
        except OSError:
            try:
                os.replace(tmp, p)                       # once more: a program that opened it may have let go
            except OSError:
                raise FileInUse(f"{os.path.basename(p)} was renamed for a moment, to {os.path.basename(tmp)}, to check "
                                "that no other program holds it open, and could not be renamed back (a program "
                                "opened it in that moment?). The cleaning did not run. Close that program, rename "
                                f"{os.path.abspath(tmp)} back to {os.path.basename(p)}, then clean again.") from None
    return None


class cleaning_guard:
    """Around one cleaning of `tag`: a lock file in its clean folder (a second tab cleaning the same file of the same
    work is refused instead of mixing two runs' outputs) and, before the engine runs, a check that none of the
    previous run's outputs (clean/<tag>/ and the published sets of `stems`) is held open by another program, so that
    nothing is half-replaced. Before anything, every path the cleaning will write or move must be within what Windows
    opens (deepest): `longest` is the longest name this kind of cleaning writes in clean/<tag>/ after the tag
    (LONGEST_OUTPUT for a harvest, engine/clean/applied3s.py REPORT_SUFFIX for an as-applied file); `files` are
    single files the cleaning writes or replaces besides the sets of `stems` (the shapefile for DIFM). Yields
    the state of guarded_log."""

    def __init__(self, tag: str, out: str, stems, longest: str = LONGEST_OUTPUT, files=()):
        self.tag, self.out, self.stems, self.longest, self.lock = tag, out, list(stems), longest, None
        self.files = list(files)

    def deepest(self) -> list:
        """The paths of this cleaning nearest to WIN_PATH_MAX, as (path, what it is, how often the tag is in it below
        the work folder): the report (the longest name of clean/<tag>/), the clean shapefile handed out and, for each
        file of the set handed out now, the name publish_set moves it aside to while the new set replaces it, and the
        single files (`files`)."""
        k = 2 if os.path.basename(os.path.normpath(self.out)) == self.tag else 1
        out = [(os.path.join(self.out, self.tag + self.longest), "its report", k)]
        for s in self.stems:
            k = 1 if os.path.basename(s).startswith(self.tag) else 0
            out.append((s + ".shp", "its clean shapefile", k))
            out += [(s + e + ".bak", f"the clean shapefile handed out now is moved aside while the new one replaces "
                                     f"it, to {os.path.basename(s + e)}.bak, which", k)
                    for e in tuple(er.SHP_EXTS) + (".zip",) if os.path.exists(s + e)]
        out += [(f, f"its {os.path.basename(f)}", 1 if os.path.basename(f).startswith(self.tag) else 0)
                for f in self.files]
        return out

    def advice(self) -> str:
        """What to do about a path that is too long: open the raw data again when a new work (its folder in
        WORKSPACE, the tag at most TAG_FLOOR characters) brings every path of deepest() within WIN_PATH_MAX; else a
        shorter workspace (workspace_advice)."""
        wd = os.path.dirname(os.path.dirname(os.path.abspath(self.out)))          # out = <work>/clean/<tag>
        cut = max(0, len(self.tag) - TAG_FLOOR)
        new = [_new_work_len(wd) + len(os.path.abspath(p)) - len(wd) - k * cut for p, _, k in self.deepest()]
        return REOPEN_ADVICE if max(new) <= WIN_PATH_MAX else workspace_advice()

    def __enter__(self):
        for p, what, _ in self.deepest():
            if len(os.path.abspath(p)) > WIN_PATH_MAX:      # e.g. a work saved by 0.2.0 with a long file name
                raise PathTooLong("not cleaned, nothing was changed: " + _long_path_msg(p, what, self.advice()))
        os.makedirs(self.out, exist_ok=True)
        p = os.path.join(self.out, LOCK_NAME)
        try:
            if os.path.exists(p) and lock_is_stale(p):
                os.remove(p)                             # left by a run that never finished
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise FileInUse(f"{self.tag} is being cleaned in another tab or window of this work: wait for it to "
                            "finish, then open the work again (Saved works)") from None
        os.write(fd, server_token().encode())
        os.close(fd)
        self.lock = p
        olds = [os.path.join(self.out, n) for n in os.listdir(self.out) if n != LOCK_NAME]
        olds += [s + e for s in self.stems for e in tuple(er.SHP_EXTS) + (".zip",)] + self.files
        try:
            held = _held_open(olds, self.advice())
        except BaseException:                            # too long, or a file the check could not rename back
            self._unlock()
            raise
        if held:
            self._unlock()
            raise FileInUse(f"{os.path.basename(held)} is open in another program (QGIS, a spreadsheet, SMS, a PDF "
                            "viewer ...): close it and clean again. Nothing was changed: the previous cleaning's "
                            "files are as they were.")
        return {"exc": None}

    def _unlock(self):
        if self.lock:
            try:
                os.remove(self.lock)
            except OSError:
                pass
            self.lock = None

    def __exit__(self, *exc):
        self._unlock()
        return False


def guarded_log(log, state: dict):
    """The engine's log through `log` (the status box), which a click on the page cannot interrupt: Streamlit stops a
    run at its next call when another widget changed (a rerun request), and that call is inside the engine while it
    writes its outputs. The first such stop is kept in state['exc'] and raised again by finish_cleaning, once every
    output is written and published."""
    def f(m):
        if state.get("exc") is None:
            try:
                log(m)
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException as e:                   # Streamlit's rerun / stop request
                state["exc"] = e
    return f


def finish_cleaning(tag: str, res: dict, state: dict) -> dict:
    """The result of a finished cleaning; when the page asked for a new run while it was running, the result is
    kept and saved first, then the run is let go."""
    if state.get("exc") is not None:
        ss.cleaned[tag] = res
        save_current(quiet=True)
        raise state["exc"]
    return res


def publish_set(src_stem: str, dst_stem: str, exts, then=None):
    """Publishes the files src_stem + ext as dst_stem + ext (the clean shapefile set in clean_shapefiles/, its zip
    included), all or none: the files there now are first moved aside (.bak); when one of them is held open by
    another program, those already moved come back and FileInUse says which file to close. `then` (writing the zip,
    trimming the .dbf) runs on the new set; any failure puts the previous set back."""
    exts = tuple(dict.fromkeys(exts))                   # each extension once (a caller may name the .zip itself)
    every = tuple(dict.fromkeys(exts + (".zip",)))
    olds = [dst_stem + e for e in every if os.path.exists(dst_stem + e)]
    moved = []
    for p in olds:
        try:
            os.replace(p, p + ".bak")
            moved.append(p)
        except OSError as e:
            for q in reversed(moved):
                os.replace(q + ".bak", q)
            if _too_long(e, p, p + ".bak"):
                raise PathTooLong("the cleaning ran (its report and records are in clean/), but the clean shapefile "
                                  "handed out is still the previous one: "
                                  + _long_path_msg(p + ".bak", os.path.basename(p) + ".bak")) from None
            raise FileInUse(f"{os.path.basename(p)} is open in another program: close it and clean again. The "
                            "cleaning ran (its report and records are in clean/), but the clean shapefile handed out "
                            "is still the previous one.") from None
    try:
        for e in exts:
            if os.path.exists(src_stem + e):
                shutil.copyfile(src_stem + e, dst_stem + e)
        if then is not None:
            then()
    except BaseException:
        for e in every:                                  # the new set, part written: out, the previous one back
            if os.path.exists(dst_stem + e):
                try:
                    os.remove(dst_stem + e)
                except OSError:
                    pass
        for q in moved:
            try:
                os.replace(q + ".bak", q)
            except OSError:
                pass
        raise
    for q in moved:
        try:
            os.remove(q + ".bak")
        except OSError:
            pass


def refresh_boundary(tag: str):
    """The boundary of `tag` read again just before a cleaning, so that the box, the outline on the clean maps and the
    'settings changed' check describe the file the engine clips to (it may have been edited on disk since Use)."""
    B = ss.boundary.get(tag)
    if not B or B.get("needs_choice") or not os.path.exists(B.get("path") or ""):
        return
    nb = load_boundary(tag, ("path", B["path"]), B.get("feature") or None)
    if not nb.get("fields"):
        nb["fields"] = B.get("fields") or []
    ss.boundary[tag] = nb


# ------------------------------------------------------------------------------------------------ as-applied 3-sigma
A3_KEYS = ("attributes", "repeat", "min_value", "k_sd", "max_passes", "group_by", "clip")


def a3_defaults(op: dict) -> dict:
    """The 3-sigma settings a planter / sprayer file starts with: the applied rate (the first one found) and the
    speed, the rate as the main attribute, readings with no product (rate <= 0) removed at import."""
    attrs = op["rates"][:1] + ([op["speed"]] if op.get("speed") else [])
    return {"attributes": attrs, "repeat": op["rates"][0] if op["rates"] else (attrs[0] if attrs else None),
            "min_value": 0.0, "k_sd": float(a3.DEFAULTS["k_sd"]), "max_passes": int(a3.DEFAULTS["max_passes"]),
            "group_by": "auto", "clip": True}


def swath_passes_of(S) -> int:
    """The passes of Optimize Swath Widths a dict of SMS 3-sigma settings holds (1 to sms.SWATH_PASSES_MAX); the
    default, 1, when it holds none or no such number (settings kept before the passes had a control on the screen:
    every cleaning the app made then ran one pass)."""
    try:
        v = int((S or {}).get("swath_passes"))
    except (TypeError, ValueError, AttributeError):
        return int(sms.DEFAULTS["swath_passes"])
    return v if 1 <= v <= sms.SWATH_PASSES_MAX else int(sms.DEFAULTS["swath_passes"])


def sset_for(tag: str) -> dict:
    """The cleaning settings of one file: the SMS sequence of the harvest panel for a yield file, the file's own
    3-sigma settings for any other (its panel's, else the defaults of its columns)."""
    D = ss.datasets[tag]
    if D.get("yield", True):
        S = dict(ss.get("smsset") or {k: sms.DEFAULTS[k] for k in SMS_SET_KEYS})
        S["swath_passes"] = swath_passes_of(S)           # settings kept before the passes had a control: 1
        return S
    if tag in ss.a3set:
        return dict(ss.a3set[tag])
    df = read_points(D["shp"], mtime(D["shp"]))
    return a3_defaults(a3.detect_operation([c for c in df.columns if c not in ("lon", "lat")], df))


def a3_panel(tag: str, op: dict, df: pd.DataFrame) -> dict:
    """The 3-sigma settings of a planter / sprayer / other point file (each file keeps its own)."""
    TKa = file_key(tag)
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
    shapefile in clean_shapefiles/ and next to it the same readings as a shapefile for DIFM, <tag>_3s_clean_DIFM.zip
    (write_difm: its own columns, its dates as dBASE dates)."""
    D = ss.datasets[tag]
    if not aset.get("attributes"):
        raise ValueError("choose the attributes to clean (step 3)")
    refresh_boundary(tag)
    out = os.path.join(ss.workdir, "clean", tag)
    cdir = os.path.join(ss.workdir, "clean_shapefiles")
    with cleaning_guard(tag, out, [os.path.join(cdir, f"{tag}_3s_clean")], longest=a3.REPORT_SUFFIX,
                        files=[os.path.join(cdir, f"{tag}_3s_clean" + ed.ZIP_SUFFIX)]) as lg_state:
        log = guarded_log(log, lg_state)
        res = _clean_applied_run(tag, aset, out, cdir, log)
    return finish_cleaning(tag, res, lg_state)


def _clean_applied_run(tag: str, aset: dict, out: str, cdir: str, log) -> dict:
    D = ss.datasets[tag]
    B = boundary_of(tag)
    use_b = B is not None and aset.get("clip", True)
    R = a3.run(D["shp"], out, {k: aset[k] for k in A3_KEYS}, boundary=B["path"] if use_b else None,
               feature=er.feature_setting(B.get("feature")) if use_b else None, tag=tag, log=log,
               inputs_left_out=inputs_left_out_of(D))
    F = R["files"]
    os.makedirs(cdir, exist_ok=True)
    src = os.path.splitext(F["clean_shp"])[0]
    stem = os.path.join(cdir, os.path.basename(src))
    publish_set(src, stem, tuple(er.SHP_EXTS) + (".zip",))
    return {"R": R, "shp": stem + ".shp", "zip": stem + ".zip", "flagged_shp": F.get("flagged_shp"),
            "flagged_zip": F.get("flagged_zip"), "report_pdf": F.get("report_pdf"), "json": F.get("json"),
            "settings": dict(aset), "config": file_config(tag, aset), "adjusted": False, "dropped": [],
            "boundary": B if use_b else None, "kind": "a3", "at": dt.datetime.now().strftime("%H:%M:%S"),
            "difm": write_difm(tag, stem + ".shp", R, "a3")}


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
    MF = ((R2.get("machines") or {}).get("factor_applied") or {}).values()
    R2["yield_column_for_difm"] = ("Yld_Harm" if ("Yld_Harm" in R2["difm_ready_added_columns"]
                                                and any(abs(float(v) - 1) > 1e-9 for v in MF))
                                   else (R2.get("columns") or {}).get("yield") or "Yld_Vol_Dr")
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


# ------------------------------------------------------------------------------------------------ saved works
SMS_WIDGET_KEYS = ("k_sd", "group_by", "max_passes", "min_yield", "t_clip", "t_swath", "t_speed", "t_moist", "t_yield",
                   "filter_order", "swath_scope", "swath_bias", "swath_passes", "min_yield_v")
# the SMS 3-sigma settings of the harvest panel (sset): what one cleaning of a yield file runs with
SMS_SET_KEYS = ("k_sd", "group_by", "max_yield_passes", "min_yield", "clip", "swath", "speed", "moisture", "yield",
                "filter_order", "swath_scope", "swath_bias", "swath_passes")


def default_work_name() -> str:
    """The name a work gets until the user types one: its file on screen (the tag, e.g. the field and season of a
    card), with '+N' for its other files; else the name of its folder."""
    tags = list(ss.get("datasets") or {})
    if tags:
        a = ss.get("active") if ss.get("active") in tags else tags[0]
        return a + (f" +{len(tags) - 1}" if len(tags) > 1 else "")
    return ew.folder_name(ss.workdir) if ss.get("workdir") else "work"


def request_save():
    """Save (a callback, which runs before the page): the save itself waits until the page has read every setting
    of the file on screen in this run (save_requested), so that a value typed just before the click is saved too."""
    ss.save_request = True


def save_requested():
    """Runs the save asked for by the Save button, once the settings of this run are complete."""
    if ss.pop("save_request", False):
        save_current()


def work_record(name: str | None = None) -> dict:
    """The current work as a saved-work record (engine/works.py); the creation time of an earlier save is kept. A file
    set aside when the work was opened (its points away: ss.away) is written back as it was saved, with its cleaning,
    grower's data, boundary and settings, in its place among the files."""
    prev = ew.load_work(ss.workdir) if os.path.exists(ew.work_path(ss.workdir)) else None
    away = {t: A for t, A in (ss.get("away") or {}).items() if t not in ss.datasets}
    ds = {t: (ss.datasets[t] if t in ss.datasets else away[t]["dataset"]) for t in (ss.get("away_order") or [])
          if t in ss.datasets or t in away}
    ds.update({t: D for t, D in ss.datasets.items() if t not in ds})
    ds.update({t: A["dataset"] for t, A in away.items() if t not in ds})

    def merged(cur, k):
        return {**(cur or {}), **{t: A[k] for t, A in away.items() if k in A}}
    return ew.make_record(ss.workdir, name or ss.get("work_name") or default_work_name(),
                          input_label=ss.get("input_label"), active=ss.active, datasets=ds,
                          boundary=merged(ss.boundary, "boundary"), grower=merged(ss.grower, "grower"),
                          smsset=ss.get("smsset"), a3set=merged(ss.a3set, "a3set"),
                          cleaned=merged(ss.cleaned, "cleaned"), app_version=VERSION,
                          created=(prev or {}).get("created"), combines=merged(ss.get("cfset") or {}, "combines"),
                          inputs_left_out=ss.get("left_out") or [])


def save_current(quiet: bool = False, even_empty: bool = False):
    """Saves the current work into its work folder (oced_work.json). quiet: the automatic save after an extraction
    or a cleaning (a failure is only a toast). A work whose files are all set aside (ss.away) is saved too; even_empty:
    also one left with no file (its last file set aside removed from it)."""
    if not ss.get("workdir") or not (ss.datasets or ss.get("away") or even_empty):
        return
    try:
        ew.save_work(ss.workdir, work_record())
        ss.work_saved = ss.workdir
        ss.work_saved_at = dt.datetime.now().strftime("%H:%M")
        if not quiet:
            st.toast(f"Saved: {ss.get('work_name') or default_work_name()}", icon=":material/save:")
    except OSError as e:
        st.toast(f"The work could not be saved ({_error_reason(e)})", icon=":material/error:")


def restore_work(wd: str):
    """Opens a saved work: the files, their boundaries, the grower's data, the settings and the cleanings come back
    as they were (the cleaning results are read from their JSON; nothing runs again)."""
    rec = ew.load_work(wd)
    if rec is None or rec.get("error"):
        ss.work_msg = ("error", f"This work cannot be opened: {(rec or {}).get('error') or 'nothing in it'}")
        return
    if ss.get("workdir") and ss.datasets and os.path.normcase(str(ss.workdir)) != os.path.normcase(str(wd)):
        save_current(quiet=True)                         # the outgoing work, as it is on screen
    start_over()
    for k in SMS_WIDGET_KEYS + ("active_pick",):
        ss.pop(k, None)
    ss.workdir = wd
    ss.input_label = rec.get("input_label")
    ss.left_out = ew.inputs_left_out(rec)              # said again in step 1, and in the 'Opened ...' message
    probs, resolved_by_clean = [], []                  # the lines a new cleaning of that file answers
    ss.datasets = {}
    back_default = set()                               # files whose own import is gone: back to SMS's default
    for t, D in (rec.get("datasets") or {}).items():
        DF = default_of(D)
        if D.get("shp") and os.path.exists(D["shp"]):
            ss.datasets[t] = D
        elif DF.get("shp") and os.path.exists(DF["shp"]) and import_mode(D) != "default" \
                and derived_import(t, D.get("shp")):
            # the file of its own import is gone, its default import is there: back to it (record only, no file
            # written: this runs in the Open callback). Not for a file in use read in place (the export as it is,
            # an import that changed nothing): its folder is away, set aside below
            D["shp"], D["n"] = DF["shp"], DF.get("n")
            D["sms_import"] = copy.deepcopy(DF.get("sms_import"))
            if D.get("kind") == "raw" and "source" in DF:
                D["source"] = copy.deepcopy(DF["source"])
            _follow_default_decode(D, DF)
            D["import_mode"] = "as_is" if DF.get("error") else "default"
            ss.datasets[t] = D
            back_default.add(t)
            probs.append(f"{t}: its import with your settings is no longer on disk: it is back to "
                         + ("the import of the older version's readings (Older rule)" if DF.get("older_decode")
                            else "SMS's default import") + " (step 2 can apply your settings again)")
        else:
            # its points away (a drive not plugged in): set aside with its cleaning, grower's data and boundary, and
            # written back unchanged by every save of the work (work_record), never dropped from it
            ss.away[t] = {"dataset": D}
            probs.append(away_line(t, D, t in (rec.get("cleaned") or {})))
    ss.away_order = list(rec.get("datasets") or {})
    # the products the work shows 0.3.0's step 1 gave (a product a record cannot tell the origin of: amendment A1.3)
    step1 = step1_products_030(rec.get("datasets") or {})
    for t, D in ss.datasets.items():                   # the import mode and default of every file (record only)
        classify_import(D, legacy=bool(rec.get("legacy")), step1=step1)
    for t, A_ in ss.away.items():                      # what the work keeps of a file set aside, as saved
        for k in ("grower", "a3set", "combines", "boundary", "cleaned"):
            if t in (rec.get(k) or {}):
                A_[k] = rec[k][t]
    ss.grower = {t: G for t, G in (rec.get("grower") or {}).items() if t in ss.datasets}
    ss.a3set = {t: A for t, A in (rec.get("a3set") or {}).items() if t in ss.datasets}
    ss.smsset = rec.get("smsset")
    ss.cfset = {t: c for t, c in (rec.get("combines") or {}).items() if t in ss.datasets}
    for t, B in (rec.get("boundary") or {}).items():
        if t not in ss.datasets:
            continue
        try:
            ss.boundary[t] = load_boundary(t, ("path", B["path"]), B.get("feature") or None)
        except Exception as e:
            probs.append(f"{t}: the boundary {B.get('path')} could not be read ({e})")
    for t, C in (rec.get("cleaned") or {}).items():
        if t not in ss.datasets:
            continue
        try:
            with open(C["json"], encoding="utf-8") as fh:
                R = json.load(fh)
        except (OSError, ValueError, TypeError) as e:
            probs.append(f"{t}: its cleaning record could not be read ({e})")
            resolved_by_clean.append(probs[-1])
            continue
        if not C.get("shp") or not os.path.exists(C["shp"]):
            probs.append(f"{t}: its clean shapefile is no longer at {C.get('shp')}")
            resolved_by_clean.append(probs[-1])
            continue
        ss.cleaned[t] = {**C, "R": R, "config": C.get("config"),
                         "boundary": boundary_of(t) if (R.get("aoi") or R.get("boundary")) else None}
        why = C.get("clean_again") or (ew.clean_again_reason(R, C.get("flagged_shp"))
                                       if (C.get("kind") != "a3" and hasattr(ew, "clean_again_reason")) else None)
        if not why and t in back_default:
            why = "it was cleaned from your import settings, whose file is gone (the file is back to SMS's default): " \
                  "clean it again"
        n_shp, n_dbf = shapefile_counts(C["shp"])
        if not why and R.get("n_kept") is not None and (n_shp != n_dbf or n_shp != int(R["n_kept"])):
            why = (f"its clean shapefile holds {n_shp:,} points and {n_dbf:,} attribute rows, its cleaning record "
                   f"{int(R['n_kept']):,} kept readings (a cleaning that did not finish, or files replaced by hand): "
                   "clean it again")
        if why:
            ss.cleaned[t]["clean_again"] = why
            probs.append(f"{t}: {why}")
            resolved_by_clean.append(probs[-1])
    # decoded or imported by an older version: a new cleaning does not change that (one line for the old decodes)
    olds = [t for t, D in ss.datasets.items() if old_decode(D)]
    if len(olds) == 1:
        probs.append(f"{olds[0]}: {OLD_DECODE_LINE}")
    elif olds:
        probs.append(f"{len(olds)} files ({', '.join(olds)}): {OLD_DECODE_LINES}")
    for t, D in ss.datasets.items():
        why_imp = old_export_import(D)
        if why_imp:
            probs.append(f"{t}: {why_imp}")
    for t, C in ss.cleaned.items():          # what each cleaning ran with: saved, or confirmed by its record
        ss.cleaned[t]["config"] = config_of_cleaning(t, C, C["R"])
    if ss.left_out:
        probs.append(f"when its data was opened, {len(ss.left_out)} damaged zip(s) of the input were left out: what "
                     "was in them is not in this work (step 1 names them)")
    act = rec.get("active")
    ss.active = act if act in ss.datasets else next(iter(ss.datasets), None)
    ss.work_name, ss.work_name_for = rec.get("name") or default_work_name(), wd
    ss.work_saved = None if rec.get("legacy") else wd
    ss.work_saved_at = None
    ss.work_msg = (("warning" if probs else "ok"),
                   f"Opened {ss.work_name}: {len(ss.datasets)} file(s), {len(ss.cleaned)} cleaned"
                   + (" (an older work: Save keeps it in the list with its name)" if rec.get("legacy") else "")
                   + ("".join(f"\n- {x}" for x in probs)))
    ss.work_msg_resolved = [f"- {x}" for x in resolved_by_clean]


OLD_DECODE_LINE = ("extracted by an older version of OCED: its readings and their import are not the current ones "
                   "(a new cleaning keeps them); open the raw data again (step 1) for the current decode and import "
                   "as SMS")
OLD_DECODE_LINES = OLD_DECODE_LINE.replace("its readings and their import are", "their readings and imports are")


def old_decode(D: dict) -> str:
    """Why a raw file was extracted by an older version of OCED (engine/formats/native_write.py decode_outdated: its
    decode report lacks what every decode of its format now carries), else ''."""
    if not isinstance(D, dict) or D.get("kind") != "raw" or not isinstance(D.get("source"), dict):
        return ""
    rep = D.get("report")
    return nw.decode_outdated({**D["source"], "report": rep} if isinstance(rep, dict) else writer_source(D))


def forget_work_msg(tag: str):
    """A file cleaned again: the lines of the 'Opened ...' message about it that a new cleaning answers ('<tag>: ...
    clean it again', its clean file or record gone) go; a boundary that could not be read or a file extracted by an
    older version stays said. Once no line is left the message is a plain 'opened'."""
    msg = ss.get("work_msg")
    if not msg or msg[0] not in ("warning", "ok"):
        return
    done = set(ss.get("work_msg_resolved") or [])
    lines = str(msg[1]).split("\n")
    keep = [x for x in lines[1:] if not (x.startswith(f"- {tag}: ") and x in done)]
    if len(keep) != len(lines) - 1:
        ss.work_msg = (None if (not keep and lines[0] == WORK_MSG_HEAD) else
                       ("warning" if keep else "ok", "\n".join(lines[:1] + keep)))


WORK_MSG_HEAD = "In this work:"      # the head of a work message started by a line about a file (work_msg_line)


def drop_work_msg_file(tag: str):
    """A file removed from its work: every line of the work message about it ('- <tag>: ...') goes, whatever it says
    (a file set aside that 'stays in this work' no longer does); the one line of several files extracted by an older
    version names the others only (one left: that file's own line). Once no line is left the message is a plain
    'opened' (or none, under a head of its own)."""
    msg = ss.get("work_msg")
    if msg and msg[0] in ("warning", "ok"):
        lines = str(msg[1]).split("\n")
        keep, many = [], re.compile(r"- \d+ files \((.*)\): " + re.escape(OLD_DECODE_LINES) + "$")
        for x in lines[1:]:
            m = many.match(x)
            if m and tag in m.group(1).split(", "):
                # the one line of several files extracted by an older version: the file leaves its list
                rest = [t for t in m.group(1).split(", ") if t != tag]
                if len(rest) == 1:
                    keep.append(f"- {rest[0]}: {OLD_DECODE_LINE}")
                elif rest:
                    keep.append(f"- {len(rest)} files ({', '.join(rest)}): {OLD_DECODE_LINES}")
            elif not x.startswith(f"- {tag}: "):
                keep.append(x)
        if keep != lines[1:]:
            ss.work_msg = (None if (not keep and lines[0] == WORK_MSG_HEAD) else
                           ("warning" if keep else "ok", "\n".join(lines[:1] + keep)))
    ss.work_msg_resolved = [x for x in (ss.get("work_msg_resolved") or []) if not x.startswith(f"- {tag}: ")]


def work_msg_line(tag: str, line: str):
    """A line '<tag>: <line>' added to the work message of the sidebar (under the 'Opened ...' head, or a head of its
    own when there is none), once; a new cleaning of the file answers it (forget_work_msg)."""
    x = f"- {tag}: {line}"
    msg = ss.get("work_msg")
    if msg and msg[0] in ("ok", "warning"):
        lines = str(msg[1]).split("\n")
        if x not in lines:
            ss.work_msg = ("warning", "\n".join(lines + [x]))
    else:
        ss.work_msg = ("warning", f"{WORK_MSG_HEAD}\n{x}")
    ss.work_msg_resolved = list(ss.get("work_msg_resolved") or []) + [x]


def shapefile_counts(shp: str) -> tuple[int, int]:
    """(points in the .shp as GDAL reads it, records in the .dbf header) of a shapefile; -1 where unreadable."""
    try:
        import pyogrio
        n_shp = int(pyogrio.read_info(shp)["features"])
    except Exception:
        n_shp = -1
    try:
        with open(os.path.splitext(shp)[0] + ".dbf", "rb") as fh:
            n_dbf = int.from_bytes(fh.read(8)[4:8], "little")
    except OSError:
        n_dbf = -1
    return n_shp, n_dbf


def open_picked():
    restore_work(ss.get("work_pick"))


def workspace_usage() -> dict:
    """The disk the workspace takes: {total, n, unused: [(work folder, bytes)]} where unused are the folders that no
    saved work, extraction or cleaning lists (inputs opened and left, failed opens of older versions) and that are
    not the work on screen."""
    out = {"total": 0, "n": 0, "unused": []}
    try:
        entries = [e.path for e in os.scandir(WORKSPACE) if e.is_dir()]
    except OSError:
        return out
    cur = os.path.normcase(os.path.abspath(ss.workdir)) if ss.get("workdir") else None
    for wd in entries:
        size = 0
        for dp, _dn, fn in os.walk(wd):
            for f in fn:
                try:
                    size += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        out["total"] += size
        out["n"] += 1
        try:
            unused = ew.load_work(wd) is None
        except Exception:
            unused = False
        if unused and os.path.normcase(os.path.abspath(wd)) != cur:
            out["unused"].append((wd, size))
    return out


def remove_work_folder(wd: str) -> bool:
    """Deletes one work folder for good: only a folder directly inside the workspace, never the work on screen."""
    p = os.path.normcase(os.path.abspath(wd))
    if os.path.normcase(os.path.dirname(p)) != os.path.normcase(os.path.abspath(WORKSPACE)):
        return False
    if ss.get("workdir") and p == os.path.normcase(os.path.abspath(ss.workdir)):
        return False
    shutil.rmtree(wd, ignore_errors=True)
    return not os.path.exists(wd)


def workspace_block(works: list):
    """Sidebar: what the work folders take on disk, the folders nothing lists (removable), and deleting a saved
    work. Measured on request (walking a large workspace takes a moment)."""
    with st.expander("Workspace: disk use and clean-up", icon=":material/hard_drive:"):
        st.caption(f"Work folders in {WORKSPACE}. Every Open makes one (with its copy of the input).")
        if st.button("Measure the disk use", key="ws_measure", icon=":material/data_usage:"):
            ss.ws_usage = workspace_usage()
        U = ss.get("ws_usage")
        if U:
            un_b = sum(b for _, b in U["unused"])
            st.caption(f"{U['n']} work folder(s), {U['total'] / 2 ** 30:,.2f} GB; {len(U['unused'])} without a saved "
                       f"work, extraction or cleaning ({un_b / 2 ** 30:,.2f} GB): inputs opened and left.")
            if U["unused"]:
                ok = st.checkbox("Remove them for good (the copies of the inputs in them; the original files stay "
                                 "where they are)", key="ws_rm_ok")
                if st.button(f"Remove {len(U['unused'])} unused folder(s)", key="ws_rm", disabled=not ok,
                             icon=":material/delete_sweep:"):
                    n = sum(remove_work_folder(wd) for wd, _ in U["unused"]
                            if dt.datetime.now().timestamp() - mtime(wd) > 600)   # not one another tab is opening
                    ss.ws_usage = None
                    ss.pop("ws_rm_ok", None)
                    st.toast(f"{n} unused folder(s) removed", icon=":material/delete_sweep:")
                    st.rerun()
        if works:
            w = ss.get("work_pick")
            by = {x["workdir"]: x for x in works}
            if w in by:
                is_cur = bool(ss.get("workdir")) and os.path.normcase(os.path.abspath(w)) == os.path.normcase(
                    os.path.abspath(ss.workdir))
                ok2 = st.checkbox(f"Delete the work '{by[w]['name']}' and its folder for good (it cannot be undone)",
                                  key=f"ws_del_ok_{key_of(w)}", disabled=is_cur)   # one box per work chosen
                if st.button("Delete the selected work", key="ws_del", disabled=not ok2 or is_cur,
                             icon=":material/delete_forever:",
                             help="The work on screen cannot be deleted: open another one or Start over first."):
                    done = remove_work_folder(w)
                    ss.pop(f"ws_del_ok_{key_of(w)}", None)
                    ss.pop("work_pick", None)
                    ss.ws_usage = None
                    st.toast("Deleted" if done else "It could not be deleted (a file in it is open?)",
                             icon=":material/delete_forever:")
                    st.rerun()


def select_file(tag: str):
    """A file of the action tree: shown in steps 1 to 4."""
    ss.active = tag
    ss["active_pick"] = tag


def works_signature() -> tuple:
    """What the list of saved works depends on: each work folder and the time of its oced_work.json."""
    out = []
    try:
        for e in os.scandir(WORKSPACE):
            if e.is_dir():
                wp = os.path.join(e.path, ew.WORK_FILE)
                out.append((e.name, e.stat().st_mtime, os.path.getmtime(wp) if os.path.exists(wp) else 0.0))
    except OSError:
        pass
    return (os.path.normcase(WORKSPACE),) + tuple(sorted(out))     # another workspace is another list


@st.cache_data(show_spinner=False, max_entries=4)
def list_works_cached(sig: tuple) -> list:
    """ew.list_works, read again only when a work folder or a saved work changed."""
    return ew.list_works(WORKSPACE)


def saved_works_block():
    """The top of the sidebar: the name of this work with Save, and the saved works with Open."""
    st.subheader("Saved works", anchor=False)
    if ss.workdir and ss.datasets:
        if ss.get("work_name_for") != ss.workdir:
            rec0 = ew.load_work(ss.workdir) if os.path.exists(ew.work_path(ss.workdir)) else None
            ss.work_name = (rec0 or {}).get("name") or default_work_name()
            ss.work_name_for = ss.workdir
            ss.work_saved = ss.workdir if rec0 else None
        with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
            st.text_input("This work", key="work_name", help="The name it is listed with. Saving keeps the files, the "
                          "boundaries, the grower's data, the settings and the cleanings of this work, to open it "
                          "again later.")
            st.button("Save", icon=":material/save:", key="work_save", type="primary", on_click=request_save)
        global SAVE_PH
        SAVE_PH = st.empty()                   # filled at the end of the page, after an automatic save of this run
        SAVE_PH.caption(save_status_text())
    try:
        works = list_works_cached(works_signature())
    except Exception as e:                               # a broken folder must not take the sidebar down
        st.caption(f"The saved works could not be listed: {e}")
        works = []
    if works:
        by = {w["workdir"]: w for w in works}
        if ss.get("work_pick") not in by:
            ss.work_pick = next(iter(by))
        st.selectbox("Open a saved work", list(by), key="work_pick", format_func=lambda w: ew.work_label(by[w]))
        st.button("Open", icon=":material/folder_open:", key="work_open", on_click=open_picked,
                  help="Brings the work back as it was saved: the files, the maps, the settings and the cleanings "
                       "(nothing runs again).")
    else:
        st.caption("No saved work yet.")
    global WORK_MSG_PH
    WORK_MSG_PH = st.empty()                   # drawn again at the end of the page: a cleaning of this run changes it
    draw_work_msg()
    workspace_block(works)


SAVE_PH = WORK_MSG_PH = None


def draw_work_msg():
    """The 'Opened ...' message of the sidebar, in its placeholder (empty when there is none)."""
    if WORK_MSG_PH is None:
        return
    msg = ss.get("work_msg")
    if not msg:
        WORK_MSG_PH.empty()
        return
    if msg[0] in ("ok", "warning"):
        # the counts as they are now (an Apply sets a cleaning aside, a file is removed ...), not as opened
        msg = (msg[0], re.sub(r"^(Opened .*): \d+ file\(s\), \d+ cleaned",
                              lambda m: f"{m.group(1)}: {len(ss.datasets)} file(s), {len(ss.cleaned)} cleaned",
                              str(msg[1]), count=1))
    (WORK_MSG_PH.success if msg[0] == "ok" else WORK_MSG_PH.warning if msg[0] == "warning" else WORK_MSG_PH.error)(
        msg[1], icon=":material/folder_open:")


def save_status_text() -> str:
    return (("Saved" + (f" at {ss.work_saved_at}" if ss.get("work_saved_at") else "")
             if ss.get("work_saved") == ss.workdir else "Not saved yet")
            + " · saved automatically after each extraction and cleaning")


def _tick(ok: bool) -> str:
    return ":material/check_circle:" if ok else ":material/radio_button_unchecked:"


def action_tree():
    """The action tree of the sidebar: what was done in each step, file by file; a file name shows that file."""
    st.subheader("Action tree", anchor=False)
    DSx = ss.datasets
    with st.expander("1 · Raw data", icon=":material/upload_file:", expanded=True):
        st.caption(f"{_tick(bool(DSx))} " + (html.escape(str(ss.get("input_label"))) if ss.get("input_label")
                                              else ("opened from a saved work" if DSx else "nothing opened")))
        for t, D in DSx.items():
            st.button(t, key=f"tree_f_{key_of(t)}", type="tertiary", on_click=select_file, args=(t,),
                      icon=":material/arrow_right:" if t == ss.active else ":material/description:",
                      help="Show this file in steps 1 to 4")
            n1 = default_of(D).get("n") if default_of(D).get("shp") else D.get("n")
            st.caption(f"{int(n1 or 0):,} readings · {html.escape(str(D.get('label') or ''))}")
    with st.expander("2 · Import settings", icon=":material/tune:", expanded=bool(DSx)):
        if not DSx:
            st.caption("nothing yet")
        for t, D in DSx.items():
            w = import_word(t, D)
            st.caption(f"**{html.escape(t)}**: {html.escape(w)}"
                       + (f" · {int(D.get('n') or 0):,} readings" if import_mode(D) != "default" else ""))
    with st.expander("3 · Cleaning", icon=":material/cleaning_services:", expanded=bool(DSx)):
        if not DSx:
            st.caption("nothing yet")
        for t, D in DSx.items():
            B, G, C = boundary_of(t), ss.grower.get(t) or {}, ss.cleaned.get(t)
            lines = [f"**{html.escape(t)}**",
                     f"{_tick(bool(B))} boundary: " + (f"{html.escape(B['name'])} · {B['area_ac']:,.2f} ac" if B
                                                       else "none")]
            if D.get("yield", True):
                T_ = grower_ticket(G)
                lines.append(f"{_tick(bool(T_))} grower's data: " + (
                    er.ticket_label(T_) + (" · adjust" if G.get("use") == "adjust" else " · validate") if T_
                    else "not given"))
            if C:
                R = C["R"]
                stale = C.get("config") != file_config(t, sset_for(t)) or bool(C.get("clean_again"))
                lines.append(f"{_tick(True)} cleaned {html.escape(str(C.get('at') or ''))}: {int(R['n_kept']):,} of "
                             f"{int(R['n_in']):,} kept ({float(R['removed_pct']):.2f} % removed)"
                             + (" · :orange[settings changed: clean again]" if stale else ""))
                L = R.get("level") or {}
                if L.get("factor") is not None:
                    # the L the band is computed on (after the combine factor), not the one before it
                    lines.append(f"{_tick(True)} L = {html.escape(er.level_factor_text(L))} · "
                                 + html.escape(str((L.get("closure") or {}).get("band") or ""))
                                 + (" · adjusted" if C.get("adjusted") else " · validated"))
            else:
                lines.append(f"{_tick(False)} not cleaned yet")
            st.caption("  \n".join(lines))
    with st.expander("4 · Clean files and reports", icon=":material/download:", expanded=bool(ss.cleaned)):
        if not ss.cleaned:
            st.caption("nothing cleaned yet")
        for t, C in ss.cleaned.items():
            nat = "".join(f"  \n{_tick(not NR.get('stale'))} {html.escape(str(NR.get('label') or fid), quote=False)}"
                          + (" · from an earlier cleaning" if NR.get("stale") else "")
                          for fid, NR in native_results(t, C).items())
            st.caption(f"{_tick(os.path.exists(C['shp']))} {html.escape(os.path.basename(C['shp']))}  \n"
                       f"{_tick(bool(C.get('report_pdf')) and os.path.exists(C.get('report_pdf') or ''))} report (PDF)"
                       + nat)
        if ss.workdir:
            st.caption("Work folder")
            st.code(ss.workdir, language=None, wrap_lines=True)


def _mean_of(df: pd.DataFrame, col) -> float | None:
    """The plain mean of a column's finite values (as the map statistics and SMS Edit Legend give it)."""
    if not col or col not in df:
        return None
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    v = v[np.isfinite(v)]
    return float(v.mean()) if len(v) else None


def area_of(df: pd.DataFrame):
    """The area (ac) each reading swept: distance x width (ft); None without both columns."""
    cc = yc.detect_columns([c for c in df.columns if c not in ("lon", "lat")])
    if not (cc.get("distance_ft") and cc.get("width_ft")):
        return None
    return (pd.to_numeric(df[cc["distance_ft"]], errors="coerce").to_numpy(float)
            * pd.to_numeric(df[cc["width_ft"]], errors="coerce").to_numpy(float) / 43560.0)


def avg_of(df: pd.DataFrame, col) -> float | None:
    """The Average of the SMS summary: the area-weighted mean, sum(value x area) / sum(area) = the total divided by
    the area. None without the distance and width columns."""
    if not col or col not in df:
        return None
    a = area_of(df)
    if a is None:
        return None
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    ok = np.isfinite(v) & np.isfinite(a) & (a > 0)
    return float((v[ok] * a[ok]).sum() / a[ok].sum()) if ok.any() else None


def per_area(unit: str) -> bool:
    """A per-area unit (bu/ac, lb/ac, gal/ac, kg/ha ...): its SMS Average is the area-weighted one."""
    u = str(unit or "").lower().replace(" ", "")
    return u.endswith("/ac") or u.endswith("/ha")


def combines_of(df: pd.DataFrame) -> tuple[list, str]:
    """The combines a harvest point file names, as the engine finds them: ([{combine, readings, mean dry yield}],
    where they come from). The machine column; else the sources SMS writes at the end of the dataset names, or
    dataset names that are VINs; else one combine."""
    det = yc.detect_columns([c for c in df.columns if c not in ("lon", "lat")])
    key, basis = None, "one combine (no machine column, no combine in the dataset names)"
    if det.get("machine"):
        key, basis = df[det["machine"]].astype(str).to_numpy(), f"the machine column {det['machine']}"
    elif det.get("dataset"):
        dm = sms.dataset_machines(df[det["dataset"]])
        if dm is not None:
            key, basis = np.asarray(dm[0]).astype(str), "the dataset names"
    if key is None:
        return [], basis
    y = pd.to_numeric(df[det["yield"]], errors="coerce") if det.get("yield") else pd.Series(np.nan, index=df.index)
    g = pd.DataFrame({"combine": key, "y": y.to_numpy(float)}).groupby("combine")
    rows = [{"combine": str(m), "readings": int(len(v)), "mean dry yield (bu/ac)": float(v["y"].mean())}
            for m, v in g]
    return (rows if len(rows) >= 2 else []), basis


def combine_settings(tag: str) -> dict:
    """The combine-factor settings of a file (off by default: the user decides, also with several combines)."""
    c = dict(ss.cfset.get(tag) or {})
    return {"on": bool(c.get("on", False)), "method": c.get("method") or "auto", "reference": c.get("reference") or "auto",
            "max_pct": float(c.get("max_pct") or 10.0), "ticket_confirms": bool(c.get("ticket_confirms", True))}


# why a factor was not applied, for a cleaning record without the engine's own sentence (R['machines']['advice'],
# which also reads the grower's weight test: an older engine): the gate alone
GATE_TEXT = {
    "above_max_factor": "above the max factor ({mx:g} %), proven by the passes side by side",
    "above_max_factor_unconfirmed": "above the max factor ({mx:g} %) and not proven by the passes side by side",
    "ci_includes_1": "not proven: its 95 % interval includes 1",
    "sizes_disagree": "the 30 m and the 50 m cells disagree",
    "below_min_factor": "below 1 %: nothing to correct",
    "spatially_inconsistent": "one factor does not fit both halves of the field",
    "no_link": "it never harvested side by side with the reference",
    "too_few_pairs": "too few passes side by side with the reference",
    "layout": "the method does not hold for how the combines shared the field (blocks)",
}


def factor_outcome(R: dict) -> dict | None:
    """What the combine factor of a cleaning did: None when it was switched off (or one combine); else {applied
    {combine: factor}, blocked [{combine, factor, ci_lo, ci_hi, cells, pass_pairs, why}], proposed seams, text}."""
    M = R.get("machines") or {}
    S = (R.get("settings") or {}).get("machines") or {}
    if not M or not S.get("harmonise"):
        return None
    mx = 100 * float(S.get("max_factor") or 0.1)
    fa = {str(k): float(v) for k, v in (M.get("factor_applied") or {}).items()}
    applied = {m: f for m, f in fa.items() if abs(f - 1) > 1e-9}
    advice = {str(k): str(v) for k, v in (M.get("advice") or {}).items() if v}
    blocked = []
    for t in M.get("tests") or []:
        m = str(t.get("machine"))
        if t.get("primary") and m not in applied and t.get("factor") is not None:
            why = advice.get(m)                          # the engine's sentence: the gate and the weight's test
            if not why:
                why = GATE_TEXT.get(str(t.get("gate")), str(t.get("gate") or "not applied")).format(mx=mx)
                if str(t.get("gate")) == "above_max_factor" and not M.get("ticket_test"):
                    why += ": raise the max factor to apply it, or give the grower's weight, which can confirm it"
            blocked.append({"combine": m, "factor": float(t["factor"]), "ci_lo": t.get("ci_lo"), "ci_hi": t.get("ci_hi"),
                            "cells": t.get("n_cells"), "pass_pairs": t.get("n_pass_pairs"), "why": why})
    return {"applied": applied, "blocked": blocked, "reference": M.get("reference"),
            "proposed": (M.get("proposed") or {}).get("seams"), "seams": M.get("seams") or {}}


def factor_outcome_box(R: dict):
    """The factor of the last cleaning in a box: applied (to whom) or not applied (why, and what it would do)."""
    FO = factor_outcome(R)
    if FO is None:
        return
    if FO["applied"]:
        txt = ("The combine factor of the last cleaning was applied: "
               + ", ".join(f"{m} x {f:.4f}" for m, f in FO["applied"].items())
               + f" (the reference {FO['reference']} x 1). The corrected yield is one pill away on the clean map.")
        tone = ("#E8F7F0", "#00784D")
    else:
        tone = ("#FFF5E5", "#9A5B00")
        txt = "The combine factor was switched on but NOT applied in the last cleaning"
        if FO["blocked"]:
            parts = []
            for b in FO["blocked"]:
                ci = (f", 95 % interval {float(b['ci_lo']):.4f}-{float(b['ci_hi']):.4f}"
                      if b.get("ci_lo") is not None and b.get("ci_hi") is not None else "")
                ev = (f", {int(b['cells'])} cells / {int(b['pass_pairs'])} pass pairs" if b.get("cells") else "")
                parts.append(f"{b['combine']} would need x {b['factor']:.4f} ({100 * (b['factor'] - 1):+.2f} %{ci}{ev}): "
                             f"{b['why']}")
            txt += ": " + "; ".join(parts) + "."
        else:
            txt += ": no factor could be estimated (the combines did not harvest enough passes side by side)."
        P_ = FO.get("proposed") or {}
        if P_ and (P_.get("different_combines") or {}).get("after", {}).get("median_pct") is not None:
            db = FO["seams"].get("different_combines", {}).get("before", {}).get("median_pct")
            da = P_["different_combines"]["after"]["median_pct"]
            sc = (FO["seams"].get("same_combine") or {}).get("median_pct")
            if db is not None:
                txt += (f" If it were applied, the passes side by side of different combines would go from {db:.2f} % to "
                        f"{da:.2f} %" + (f" (the same combine's own passes: {sc:.2f} %)" if sc is not None else "") + ": "
                        + ("it would bring them closer." if da < db else "it would make the seams WORSE, so the "
                           "difference is not a calibration difference between the combines."))
    st.html(f'<div class="oced-verdict" style="background:{tone[0]};border-color:{tone[1]};color:#1F2937">'
            f'{html.escape(txt)}</div>')


def seams_panel(C: dict | None):
    """Beside the combine factor: the differences between neighbouring passes of different combines and of the same
    combine, from the last cleaning of the file (R['machines']['seams'], a diagnostic that never changes the data)."""
    st.markdown("**Passes side by side** · the last cleaning of this file",
                help="Neighbouring passes of different combines and of the same combine, on the kept readings of the "
                     "last cleaning: a diagnostic that never changes the data. Per pair: the median difference of the "
                     "stretches side by side, and how much the first combine reads above (+) or below (-) the second.")
    SM = ((((C or {}).get("R") or {}).get("machines") or {}).get("seams")) or None
    if C and C.get("R"):
        factor_outcome_box(C["R"])
    if not SM:
        st.caption("After a cleaning.", help="Clean the file once: the differences between neighbouring passes of "
                                             "different combines and of the same combine appear here. Then decide on "
                                             "the factor and clean again.")
        return
    sc, db, da = SM["same_combine"], SM["different_combines"]["before"], SM["different_combines"]["after"]
    moved = bool(SM["different_combines"].get("factor_moved_them"))
    L_ = f"{float(SM.get('stretch_m') or 50):g} m"

    def pct(x):
        return "-" if x is None else f"{float(x):.2f} %"
    cards = [{"label": "Different combines, side by side", "value": pct(db.get("median_pct")),
              "delta": f"{db['pass_pairs']} pass pairs · {db['stretches']:,} stretches of {L_}",
              "help": "The median difference between neighbouring passes of two different combines: in stretches of "
                      f"{L_} along each pair of passes, how much the higher side reads above the lower one."
                      + (" Before the combine factor." if moved else "")},
             {"label": "Same combine, its own passes side by side", "value": pct(sc.get("median_pct")),
              "delta": f"{sc['pass_pairs']} pass pairs · {sc['stretches']:,} stretches of {L_}",
              "help": "The same measure between neighbouring passes of one combine: the field's own pass-to-pass "
                      "difference (the ground, the direction of travel, the overlap, the flow delay)."}]
    if moved:
        cards.append({"label": "Different combines, after the factor", "value": pct(da.get("median_pct")),
                      "delta": (f"{float(da['median_pct']) - float(db['median_pct']):+.2f} points by the factor"
                                if da.get("median_pct") is not None and db.get("median_pct") is not None else None),
                      "help": "The same measure after the combine factor of the last cleaning."})
    card_row(cards, key="res_cards_seam")
    final = da.get("median_pct") if moved else db.get("median_pct")
    if not db["stretches"]:
        tone, txt = ("#F3F7FC", "#00358E"), "The combines never harvested neighbouring passes: there is no seam between them."
    elif not sc["stretches"] or final is None or sc.get("median_pct") is None:
        tone, txt = ("#F3F7FC", "#00358E"), "No two passes of the same combine are neighbours: nothing to compare with."
    elif float(final) <= float(sc["median_pct"]):
        tone = ("#E8F7F0", "#00784D")
        txt = (f"Between the combines {float(final):.2f} % ≤ the same combine's own {float(sc['median_pct']):.2f} %: the "
               "difference between the combines is no larger than the field's own pass-to-pass difference, so it is not "
               "a difference between the machines and a factor would not remove it.")
    else:
        tone = ("#FFF5E5", "#9A5B00")
        txt = (f"Between the combines {float(final):.2f} % > the same combine's own {float(sc['median_pct']):.2f} % by "
               f"{float(final) - float(sc['median_pct']):.2f} points: part of it may be a calibration difference between "
               "the combines. The factor tests it on the passes side by side and applies it only where it is proven.")
    if db["stretches"] and int(db.get("pass_pairs") or 0) < 5:
        txt += f" Only {db['pass_pairs']} pass pair(s) of different combines are neighbours: too few to tell."
    st.html(f'<div class="oced-verdict" style="background:{tone[0]};border-color:{tone[1]};color:#1F2937">'
            f'{html.escape(txt)}</div>')
    if SM.get("pairs"):
        rows = []
        for p_ in SM["pairs"]:
            r_ = {"combines": f"{p_['a']} vs {p_['b']}", "pass pairs": p_["pass_pairs"],
                  "difference (%)": p_["median_pct_before"], "first above second (%)": p_["a_over_b_pct_before"]}
            if moved:
                r_["difference after (%)"] = p_["median_pct_after"]
                r_["first above second after (%)"] = p_["a_over_b_pct_after"]
            rows.append(r_)
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format="%+.2f" if "above" in c else "%.2f")
                                    for c in ("difference (%)", "first above second (%)", "difference after (%)",
                                              "first above second after (%)")})


def card_row(cards: list, key: str):
    """Cards side by side in one row, all the same width and height (st.columns + height='stretch'), the delta text
    under the value wrapping inside its card."""
    cards = [c for c in cards if c]
    if not cards:
        return
    with st.container(key=key):
        for col, c in zip(st.columns(len(cards), gap="small"), cards):
            with col:
                st.metric(c["label"], c["value"], delta=c.get("delta"), delta_color="off", delta_arrow="off",
                          help=c.get("help"), border=True, height="stretch",
                          delta_description=c.get("delta_description"))


STEP_SHORT = {"S0": "import check", "S1": "clip", "S2": "swath", "S5": "yield"}
ATTR_SHORT = {"moisture": "moisture", "speed": "speed", "dry yield": "yield"}


def step_order(R: dict | None) -> str:
    """The filter order a cleaning ran with (its record's; an SMS cleaning record without one ran speed, then
    moisture: engine/clean/sms3sigma.py filter_order_of)."""
    M = (R or {}).get("sms3sigma")
    return sms.filter_order_of(M) if isinstance(M, dict) and M else sms.DEFAULTS["filter_order"]


def step_attr(fid: str, row: dict | None = None, R: dict | None = None) -> str | None:
    """The attribute a step filtered ('moisture', 'speed', 'dry yield' or None): the cascade row's own, else the
    record's filter order (never S3 = speed / S4 = moisture by the step id)."""
    if isinstance(row, dict) and row.get("attribute"):
        return str(row["attribute"])
    info = sms.step_info(step_order(R)).get(str(fid)[:2]) or {}
    return info.get("attribute")


def step_short(fid: str, row: dict | None = None, R: dict | None = None) -> str:
    """'moisture' / 'speed' / 'swath' ... for a step id of a cleaning, from what the step filtered."""
    a = step_attr(fid, row, R)
    return ATTR_SHORT.get(a, a) if a else STEP_SHORT.get(str(fid)[:2], (row or {}).get("name") or "")


def step_color(fid: str, row: dict | None = None, R: dict | None = None) -> str:
    """The colour of a step on the map of the removed points: by what it filtered (moisture blue, speed cyan), so that
    a cleaning made speed first keeps the colours of its filters."""
    a = step_attr(fid, row, R)
    return ATTR_COLORS.get(a) or STEP_COLORS.get(str(fid)[:2], "#FF8F00")


def step_effects(tag: str, C: dict) -> list | None:
    """How each step of an SMS 3-sigma cleaning moved the mean (plain) and the Average (SMS, total / area) of the dry
    yield, from the flagged file (every reading with Keep, Rem_By = the step that removed it, Swath_Scl = the per-area
    scale of S2, Dist_Opt x Wdth_Opt = its area after S2). Rows: the import it started from (start_word), then every
    step that removed or changed something: {step, label, removed, mean, avg, d_mean, d_avg}; the last row is the
    clean file.
    None for a planter / sprayer file or without the flagged file."""
    R = C["R"]
    fl = C.get("flagged_shp")
    if C.get("kind") == "a3" or not fl or not os.path.exists(fl):
        return None
    f = read_points(fl, mtime(fl))
    cc = yc.detect_columns([c for c in f.columns if c not in ("lon", "lat")])
    ycol = (R.get("columns") or {}).get("yield") or cc.get("yield")
    if not ycol or ycol not in f or "Rem_By" not in f:
        return None
    y = pd.to_numeric(f[ycol], errors="coerce").to_numpy(float)
    sc = (pd.to_numeric(f["Swath_Scl"], errors="coerce").to_numpy(float) if "Swath_Scl" in f else np.ones(len(f)))
    sc = np.where(np.isfinite(sc) & (sc > 0), sc, 1.0)
    a0 = area_of(f)
    a1 = a0
    if a0 is not None and "Dist_Opt" in f and "Wdth_Opt" in f:
        a1 = (pd.to_numeric(f["Dist_Opt"], errors="coerce").to_numpy(float)
              * pd.to_numeric(f["Wdth_Opt"], errors="coerce").to_numpy(float) / 43560.0)
    rem = f["Rem_By"].astype(object).where(f["Rem_By"].notna(), "").astype(str).to_numpy()

    def stats(v, a, m):
        v_, ok = v[m], np.isfinite(v[m])
        mean = float(v_[ok].mean()) if ok.any() else None
        avg = None
        if a is not None:
            aa = a[m]
            g = ok & np.isfinite(aa) & (aa > 0)
            avg = float((v_[g] * aa[g]).sum() / aa[g].sum()) if g.any() else None
        return mean, avg
    D = ss.datasets[tag]
    rawdf = read_points(D["shp"], mtime(D["shp"]))
    rcol = yc.detect_columns([c for c in rawdf.columns if c not in ("lon", "lat")]).get("yield")
    other = cleaning_on_other_import(tag)                # its import is no longer on disk: no numbers of it
    rows = [{"step": "raw", "label": cleaning_start_word(tag), "removed": None,
             "mean": None if other else _mean_of(rawdf, rcol), "avg": None if other else avg_of(rawdf, rcol)}]
    alive = np.ones(len(f), bool)
    n_out = (int(R.get("n_read") or len(f)) if other else len(rawdf)) - len(f)
    if n_out > 0:                                     # the clip before S0: those readings are not in the flagged file
        m_, a_ = stats(y, a0, alive)
        rows.append({"step": "S1", "label": "S1 clip", "removed": int(n_out), "mean": m_, "avg": a_})
    cur_y, cur_a = y, a0
    for r in R.get("cascade") or []:
        fid = str(r.get("filter") or "")
        kill = (rem == fid) & alive
        alive = alive & ~kill
        swath = fid.startswith("S2")
        if swath:
            cur_y, cur_a = y * sc, a1
        if not kill.any() and not swath:
            continue
        m_, a_ = stats(cur_y, cur_a, alive)
        lab = f"{fid} {step_short(fid, r, R)}".strip()
        rows.append({"step": fid, "label": lab, "removed": int(kill.sum()), "mean": m_, "avg": a_})
    for i, r in enumerate(rows):
        prev = rows[i - 1] if i else None
        r["d_mean"] = (r["mean"] - prev["mean"]) if (prev and r["mean"] is not None and prev["mean"] is not None) else None
        r["d_avg"] = (r["avg"] - prev["avg"]) if (prev and r["avg"] is not None and prev["avg"] is not None) else None
    return rows


def start_step(D: dict) -> int:
    """The step whose data the cleaning of a file starts from: 1 (SMS's default import, or a file with no import,
    or one whose SMS import failed and is used as it is), 2 (your settings, or the file as it is / as logged)."""
    if not D.get("yield", True):
        return 1
    mode = import_mode(D)
    return 2 if mode == "custom" or (mode == "as_is" and not failed_in_use(D)) else 1


def kind_word(kind: str) -> str:
    """An import kind (import_kind) in words inside a line: 'SMS default', 'your settings', 'as it is', 'as logged',
    'older rule', 'import failed'. The one table of these words is brand.BADGE_WORDS (the badges say the same)."""
    w = brand.BADGE_WORDS.get(kind) or brand.BADGE_WORDS["as_is"]
    return w if kind == "default" else w[0].lower() + w[1:]


def start_word(tag: str, D: dict) -> str:
    """The import a cleaning starts from, in the words of step 3's yield path and Steps tab: 'SMS default (step 1)',
    'your settings (step 2)' ... (never 'raw data': step 1 is the raw data, step 2 a change of it)."""
    return f"{kind_word(import_kind(tag, D))} (step {start_step(D)})"


def cleaning_on_other_import(tag: str) -> bool:
    """The kept cleaning of a file was made from the user's settings while the file is no longer on them (a work
    reopened after its own import's file was deleted: the file is back on SMS's default, the cleaning is to be cleaned
    again)."""
    D = ss.datasets.get(tag) or {}
    IMc = ((ss.cleaned.get(tag) or {}).get("R") or {}).get("sms_import")
    return (isinstance(IMc, dict) and IMc.get("mode") == "custom" and bool(D.get("yield", True))
            and import_kind(tag, D) != "custom")


def cleaning_start_word(tag: str) -> str:
    """The import a kept cleaning started from, by its step (start_word; 'your settings (step 2)' for a cleaning
    made from own settings the file is no longer on)."""
    if cleaning_on_other_import(tag):
        return f"{kind_word('custom')} (step 2)"
    return start_word(tag, ss.datasets[tag])


def _keep_min_yield():
    """Step 3's S0 minimum (files not imported as SMS): its value kept for the runs that do not draw it."""
    ss["min_yield_v"] = ss.get("min_yield")


def import_kind(tag: str, D: dict) -> str:
    """The badge of the import a file's cleaning starts from (brand.BADGE_WORDS): 'default', 'custom', 'as_is',
    'as_logged', 'older' or 'failed' (a planter or sprayer file: 'as_is')."""
    mode, DF = import_mode(D), default_of(D)
    IM = import_record_of(tag) or {}
    if not D.get("yield", True):
        return "as_is"
    if basis_pending(D):
        return "older"                                   # an earlier version's import, its basis not read yet
    if failed_in_use(D):
        return "failed"
    if mode == "custom":
        return "custom"
    if mode == "as_is":
        return "as_logged" if D.get("kind") == "raw" else "as_is"
    if not isinstance(IM.get("resolved"), dict) or DF.get("older"):
        return "older"
    return "default"


_CHANGE_LABELS = ("Product", "Weight to volume", "Dry moisture", "Expand dry moisture", "Manual swath",
                  "Manual moisture", "Min. yield volume", "Max. yield volume", "Start delay", "Stop delay",
                  "Flow shift")


def own_changes(R0: dict, IM: dict | None) -> list:
    """What the user's own values of an import record (step 2) change against SMS's default R0, as import_changes
    gives it: the values the record says are the user's, the product chosen, the flags, delays and flow shift; a
    value an older OCED rule gave (an import of 0.3.0 kept its minimum of 5 bu/ac) is not named."""
    RS = (IM or {}).get("resolved") or {}
    own = changed_settings({**RS, "sources": (IM or {}).get("sources")}, R0)
    out = import_changes(R0, {**{k: R0.get(k) for k in si.DEFAULTS}, **own})
    if R0.get("product") and not RS.get("product") and isinstance(RS, dict) and RS:
        # no product kept where SMS's default has one (an import of 0.3.0 'unknown' on data of a known crop)
        out.insert(0, f"Product {R0['product']} → unknown")
    if not out and older_import_rules(IM):
        # own values today's rule gives too (a minimum of 0): the values of the older rule that differ, so that the
        # line names what the import in use is, never 'your values' with nothing named
        out = [f"{x} (older rule)" for x in import_changes(R0, RS, IMPORT_KEYS_SHOWN)]
    return out


def custom_changes(tag: str, D: dict, IM: dict | None = None) -> list:
    """What a file's own import settings (step 2; IM: another record of them, a cleaning's) change against its SMS
    default (own_changes)."""
    try:
        R0 = default_resolved(import_basis(D))
    except ValueError:
        R0 = si.resolve(si.settings({}))
    return own_changes(R0, IM if IM is not None else import_record_of(tag))


def _your_settings_word(ch: list) -> str:
    return "your settings" + (f": {change_short(ch[0])}" + (f" and {len(ch) - 1} more" if len(ch) > 1 else "")
                              if ch else "")


def change_short(ch: str) -> str:
    """'Max. yield volume none → 150.00' -> 'max. yield volume 150.00': a change named by its new value."""
    left, arrow, right = str(ch).partition(" → ")
    if not arrow:
        return str(ch)
    lab = next((x for x in _CHANGE_LABELS if left.startswith(x)), left)
    return f"{lab[0].lower()}{lab[1:]} {right}"


def import_word(tag: str, D: dict | None = None) -> str:
    """The import of a file in words (step 4's table, the action tree): 'SMS default', 'your settings: max. yield
    volume 150.00', 'as it is', 'as logged', 'older rule', 'import failed', 'nothing to import' (a planter or
    sprayer file)."""
    D = D if D is not None else (ss.datasets.get(tag) or {})
    if not D.get("yield", True):
        return "nothing to import"
    kind = import_kind(tag, D)
    if kind == "custom":
        ch = custom_changes(tag, D)
        if not ch and older_decode_word(D):
            return OLDER_DECODE_WORD                     # (no value of the user's: its readings differ, as step 2 says)
        return _your_settings_word(ch)
    return kind_word(kind)


def cleaning_import_word(tag: str) -> str:
    """Step 4's import of a cleaning: the file's import (import_word), or the user's settings the cleaning was made
    with when the file is no longer on them (a work reopened after its own import's file was deleted keeps that
    cleaning, to be cleaned again)."""
    D = ss.datasets.get(tag) or {}
    if cleaning_on_other_import(tag):
        return _your_settings_word(custom_changes(tag, D, ss.cleaned[tag]["R"]["sms_import"]))
    return import_word(tag, D)


def starts_from_line(tag: str, D: dict, min3: float | None = None, pending: bool = False):
    """Step 3's first line: the import the cleaning starts from, with its badge, its readings and S0's minimum (the
    import's, or min3, step 3's own, for a file with no import); an orange line when step 2 has values not
    applied."""
    DF = default_of(D)
    n = int(D.get("n") or 0)
    if not n and D.get("shp") and os.path.exists(D["shp"]):
        n = len(read_points(D["shp"], mtime(D["shp"])))
    harvest = bool(D.get("yield", True))
    IM = import_record_of(tag) or {}
    kind = import_kind(tag, D)
    step = start_step(D)
    text = f"step {step}: {n:,} readings"
    hlp = []
    if kind == "custom":
        ch = custom_changes(tag, D)
        dec_w = older_decode_word(D) if not ch else None
        hlp.append("Your settings (step 2): " + ("; ".join(ch) if ch else
                                                 f"{OLDER_DECODE_WORD} (decoded by an older OCED with {dec_w}; nothing "
                                                 "of yours differs from SMS's default)" if dec_w else "your values")
                   + ".")
    elif kind == "older" and basis_pending(D):
        # (step 2 offers no change until its readings are back)
        hlp.append("Imported by an earlier version of OCED, kept as it is: " + basis_pending_note_of(D)
                   + ". Its import settings can be changed once " + ("it can be read." if
                                                                     (default_of(D).get("basis") or {}).get("why")
                                                                     else "its readings are back."))
    elif kind == "older":
        hlp.append("Imported by an older OCED rule" + (f": {'; '.join(DF['older'])}" if DF.get("older") else "")
                   + ". Step 2 imports it with today's rule.")
    elif kind == "failed":
        hlp.append(f"SMS's import of this file failed ({DF['error']}): the readings as the file gives them.")
    if harvest:
        mn, has_imp = import_min_yield(tag)
        if has_imp:
            # the import's own value, written as steps 1 and 2 write it (0 is '0.000 bu/ac', no value 'none')
            mn_imp = (IM.get("resolved") or {}).get("min_yield")
            text += " · S0 minimum " + (f"{float(mn_imp):,.3f} bu/ac" if mn_imp not in (None, si.AUTO) else "none")
            src_min = (IM.get("sources") or {}).get("min_yield")
            hlp.append("S0 takes the minimum of this file's import (the import left out the readings below it)."
                       if mn is not None else
                       "S0 minimum: none above 0, as SMS's generic import of a point file has none: S0 leaves "
                       "out only a reading with no plausible position or no dry yield, or a negative one; readings at "
                       "0 stay, as in SMS." if src_min == si.SRC_POINT else
                       "S0 minimum: none, as the import settings of this file have none above 0"
                       + (f" ({SOURCE_LABEL.get(src_min, src_min)})" if src_min else "")
                       + ": S0 leaves out only a reading with no plausible position or no dry yield, or a negative "
                         "one.")
        else:
            m3 = float(min3 or 0)
            text += " · S0 minimum " + ("none" if m3 <= 0 else f"{m3:,.3f} bu/ac")
            hlp.append("Not imported as SMS: S0 takes the minimum of step 3 (S0 minimum, in the settings).")
    elif kind == "as_is":
        hlp.append("A planter or sprayer file is used as written.")
    st.markdown(f"Starts from {brand.import_badge(kind)} {html.escape(text)}", unsafe_allow_html=True,
                help=" ".join(hlp) or None)
    if pending:
        st.caption(":orange[Step 2 has values not applied: the cleaning uses the import above.]")


SEQ_HELP = ("The sequence of Ag Leader SMS Advanced: S0 the import check, S1 the clip to the field boundary, S2 "
            "Optimize Swath Widths, then the mean ± k SD of the moisture, the speed and the dry yield (another yield "
            "pass while the SD falls by more than 25 %). The full text: What OCED reads, in the sidebar.")
A3_SEQ_HELP = ("S0: no position, or the main attribute missing or at or below the minimum (no product applied). S1: "
               "the clip to the field boundary. Then one 3-sigma step per attribute, the speed first: the mean ± k SD "
               "of the points still alive; the main attribute again while its SD falls by more than 25 %.")
SMS3S_TEXT = ("S0 import check (no position, no yield, dry yield below the SMS import minimum) · S1 Clip To Field "
              "Boundary (the readings outside the boundary of the file; a point on the edge is inside) · S2 Optimize "
              "Swath Widths (overlapping strips removed or narrowed, per-area values scaled) · S3 and S4, the moisture "
              "and the speed in the order of the filters (More settings), and S5 dry yield: keep the mean ± k SD of "
              "the points still alive (a reading without a moisture or a speed is not removed by that filter), "
              "another yield pass while the SD falls by more than 25 %. With several combines, the combine factor "
              "runs after these steps when you switch it on.")
GROUP_SHORT = {"auto": "auto", "task": "per task", "machine": "per combine", "field": "one for the field"}


def settings_summary(tag: str, IS_Y: bool, P0: dict, n_combines: int = 0) -> str:
    """The line of step 3's folded settings: 'k 3.0 · auto · 3 passes · S1-S5 on · boundary ✓ · grower 110,000 lb,
    validate · combine factor off', from the values on screen (the widgets' state, else the saved settings)."""
    TKs = file_key(tag)
    B = ss.boundary.get(tag)
    bnd = "boundary ✓" if (B and not B.get("needs_choice")) else "boundary: choose the field" if B else "no boundary"
    if not IS_Y:
        A = ss.a3set.get(tag) or {}
        k = ss.get(f"a3_k_{TKs}", A.get("k_sd", a3.DEFAULTS["k_sd"]))
        attrs = ss.get(f"a3_attrs_{TKs}", A.get("attributes") or [])
        mp = ss.get(f"a3_mp_{TKs}", A.get("max_passes", a3.DEFAULTS["max_passes"]))
        return " · ".join([f"k {float(k):.1f}", f"{len(attrs)} attribute{'s' if len(attrs) != 1 else ''}",
                           f"{int(mp)} passes", bnd])
    D0 = sms.DEFAULTS
    k = ss.get("k_sd", P0.get("k_sd", D0["k_sd"]))
    gb = ss.get("group_by", P0.get("group_by", "auto"))
    mp = ss.get("max_passes", P0.get("max_yield_passes", D0["max_yield_passes"]))
    fo = ss.get("filter_order") if ss.get("filter_order") in sms.FILTER_ORDERS else P0.get("filter_order")
    SI_ = sms.step_info(fo if fo in sms.FILTER_ORDERS else D0["filter_order"])
    on = {"S1": ss.get("t_clip", P0.get("clip", D0["clip"])), "S2": ss.get("t_swath", P0.get("swath", D0["swath"]))}
    for fid in ("S3", "S4"):
        a = SI_[fid]["attribute"]
        on[fid] = ss.get("t_moist" if a == "moisture" else "t_speed", P0.get(a, D0[a]))
    on["S5"] = ss.get("t_yield", P0.get("yield", D0["yield"]))
    off = [f for f, v in on.items() if not v]
    parts = [f"k {float(k):.1f}", GROUP_SHORT.get(gb, str(gb)), f"{int(mp)} passes",
             "S1-S5 on" if not off else ", ".join(off) + " off", bnd]
    G = ss.grower.get(tag) or {}
    w = ss.get(f"gw_w_{TKs}", G.get("weight"))
    if w:
        u = ss.get(f"gw_u_{TKs}", G.get("unit") or "lb")
        use = ss.get(f"gw_use_{TKs}", G.get("use") or "validate")
        parts.append(f"grower {er.ticket_label({'value': float(w), 'unit': u})}, {use}")
    else:
        parts.append("no grower's weight")
    if n_combines >= 2:
        parts.append("combine factor " + ("on" if ss.get(f"cf_on_{TKs}", combine_settings(tag)["on"]) else "off"))
    return " · ".join(parts)


def result_numbers(tag: str, C: dict) -> dict | None:
    """The numbers of a cleaning that step 3 shows (the strip and the yield path): the clean file against the import
    it started from, the combine factor and the grower's data. None when the clean file has no value to show."""
    R = C["R"]
    L = R.get("level") or {}
    A3 = C.get("kind") == "a3"
    D = ss.datasets[tag]
    cdf = read_points(C["shp"], mtime(C["shp"]))
    raw = read_points(D["shp"], mtime(D["shp"]))
    a_ = area_of(cdf)
    other = (not A3) and cleaning_on_other_import(tag)    # made from an import no longer on disk: not compared
    X = {"A3": A3, "L": L, "CL": L.get("closure") or {}, "step": 2 if other else start_step(D),
         "start": cleaning_start_word(tag), "other": other, "FM": R.get("final_map") or {},
         "area": (float(a_[np.isfinite(a_)].sum()) or None) if a_ is not None else None}
    if A3:
        col = R.get("main")
        unit = (R.get("units") or {}).get(col) if isinstance(R.get("units"), dict) else None
        unit = unit or (ATTR_INFO.get(col) or ("", "", ""))[1] or ""
        X.update(col=col, unit=unit, raw_m=_mean_of(raw, col), cl_m=_mean_of(cdf, col))
        X["raw_a"], X["cl_a"] = (avg_of(raw, col), avg_of(cdf, col)) if per_area(unit) else (None, None)
        return X if X["cl_m"] is not None else None
    cc = yc.detect_columns([c for c in cdf.columns if c not in ("lon", "lat")])
    ycol = (R.get("columns") or {}).get("yield") or cc.get("yield")
    rcol = yc.detect_columns([c for c in raw.columns if c not in ("lon", "lat")]).get("yield")
    X.update(ycol=ycol, raw_m=None if other else _mean_of(raw, rcol), cl_m=_mean_of(cdf, ycol),
             raw_a=None if other else avg_of(raw, rcol), cl_a=avg_of(cdf, ycol))
    if X["cl_m"] is None:
        return None
    # the combine factor (several combines, when switched on and proven): Yld_Harm = the cleaned yield x the factor
    MF = {str(k): float(v) for k, v in ((R.get("machines") or {}).get("factor_applied") or {}).items()}
    harm_on = "Yld_Harm" in cdf.columns and any(abs(v - 1) > 1e-9 for v in MF.values())
    X["harm_on"] = harm_on
    X["h_m"], X["h_a"] = ((_mean_of(cdf, "Yld_Harm"), avg_of(cdf, "Yld_Harm")) if harm_on else (X["cl_m"], X["cl_a"]))
    X["fac_txt"] = ", ".join(f"{m} x {v:.4f}" for m, v in MF.items() if abs(v - 1) > 1e-9)
    fcol = R.get("yield_column_for_difm")
    fcol = fcol if (fcol and fcol in cdf.columns) else ycol
    Lf = L.get("factor_final") if L.get("factor_final") is not None else L.get("factor")   # the L in the file
    adjusted = bool(C.get("adjusted")) and bool(L) and fcol not in (ycol, "Yld_Harm") and _mean_of(cdf, fcol) is not None
    TT = (R.get("machines") or {}).get("ticket_test") or {}
    X["would"] = [str(m) for m in (TT.get("would_apply") or [])] if not adjusted else []
    if adjusted:
        X["fin_m"], X["fin_a"] = _mean_of(cdf, fcol), avg_of(cdf, fcol)
    else:
        X["fin_m"], X["fin_a"] = X["h_m"], X["h_a"]
        fcol = "Yld_Harm" if harm_on else ycol
    X.update(fcol=fcol, Lf=Lf, adjusted=adjusted, gro_ac=None, mon_ac=None, area_y=None)
    if L:
        # one stated area for both per-acre figures: the grower's acres (a yield per acre), else the area harvested,
        # every strip once (after Optimize Swath Widths: the area the SMS averages are over), else the swept area
        area_s = float(L.get("monitor_area_ac") or L.get("export_area_ac") or 0)
        area_y = float(L.get("ticket_area_ac") or 0) if L.get("ticket_unit") == "bu/ac" else area_s
        if area_y > 0:
            X["area_y"] = area_y
            X["gro_ac"] = float(L["scale_ticket_bu"]) / area_y
            X["mon_ac"] = float(L.get("monitor_total_final_bu", L["export_total_bu"])) / area_y
    X["d_fin"] = float(X["CL"].get("diff_final_pct", X["CL"].get("diff_pct", 0)) or 0)   # the monitor vs the grower
    X["area_src"] = (L.get("ticket_area_source") if L.get("ticket_unit") == "bu/ac" and L.get("ticket_area_ac")
                     else L.get("monitor_area_source")) or "the area the readings swept"
    return X


def result_strip(tag: str, C: dict):
    """Step 3's strip after a cleaning (key res_cards): the readings kept, the area of the kept readings, the mean
    and the average dry yield of the clean file against the import it started from; the final yield when a
    correction was applied (the grower's weight with 'adjust', the combine factor) and the monitor against the
    grower's weight when it was only compared."""
    X = result_numbers(tag, C)
    if X is None:
        return
    R = C["R"]
    s = X["step"]
    sw = ((R.get("sms3sigma") or {}).get("swath") or {}) if not X["A3"] else {}
    bias = {str(k): float(v) for k, v in (sw.get("lateral_bias_ft") or {}).items() if v is not None}
    hk = (f"Of the {int(R.get('n_read') or R['n_in']):,} readings the cleaning started from (step {s})"
          + (f"; {int(R['n_in']):,} inside the boundary (S1 clipped {clipped_of(C):,})" if C.get("boundary") else "")
          + (f"; S2 narrowed {int(sw.get('n_narrowed') or 0):,}" + (f" over {sw['scope']}" if sw.get("scope") else "")
             if not X["A3"] else "")
          + (" (lateral offset of the logged points: " + ", ".join(f"{k} {v:+.2f} ft" for k, v in bias.items()) + ")"
             if bias else "") + ". Each step's count is in the Steps tab.")
    # the readings the cleaning started from, less those outside the boundary (S1 runs first): said, so that the
    # count of step 1 / 2 and this one tell the same story
    n_cl = clipped_of(C) if C.get("boundary") else 0
    cards = [{"label": "Readings kept", "value": f"{R['n_kept']:,}",
              "delta": f"of {int(R['n_in']):,}" + (" inside the boundary" if n_cl else "")
                       + f" · {float(R['removed_pct']):.2f} % removed", "help": hk}]
    FM = X["FM"]
    if X["area"]:
        cards.append({"label": "Area of the kept readings", "value": f"{X['area']:,.2f} ac",
                      "help": "Distance x width of the kept readings"
                              + ("" if X["A3"] else ", after S2 narrowed the overlapping strips") + "."
                              + (f" The cleaning record gives {float(FM['area_ac']):,.2f} ac (what the SMS Summary of "
                                 "the clean file shows)." if FM.get("area_ac") else "")})

    def vs(a, b, unit):
        return None if (a is None or b is None) else f"{a - b:+.2f} {unit} vs step {s}".replace("  ", " ")
    if X["A3"]:
        col, unit = X["col"], X["unit"]
        cards.append({"label": f"Mean {col}, cleaned", "value": f"{X['cl_m']:,.2f} {unit}".strip(),
                      "delta": vs(X["cl_m"], X["raw_m"], unit),
                      "help": "The plain mean of the kept readings (as SMS Edit Legend), against every reading of "
                              "the file."})
        if X["cl_a"] is not None:
            cards.append({"label": f"Average {col}, cleaned (SMS)", "value": f"{X['cl_a']:,.2f} {unit}".strip(),
                          "delta": vs(X["cl_a"], X["raw_a"], unit),
                          "help": "As the SMS summary: the area-weighted average, the total divided by the area."})
        cards.append({"label": "Passes of " + str(R.get("main")), "value": f"{R.get('passes', 1)}",
                      "help": "The 3-sigma passes of the main attribute (another while its SD falls by more than "
                              "25 %)."})
        card_row(cards, key="res_cards")
        return
    ycol, L, CL = X["ycol"], X["L"], X["CL"]
    cards.append({"label": "Mean dry yield, cleaned", "value": f"{X['cl_m']:,.2f} bu/ac",
                  "delta": vs(X["cl_m"], X["raw_m"], "bu/ac"),
                  "help": f"The plain mean of {ycol} over the kept readings (as SMS Edit Legend): the monitor's yield "
                          f"after the clip and the 3-sigma steps, against the import the cleaning started from (step "
                          f"{s}, every reading)."})
    if X["cl_a"] is not None:
        cards.append({"label": "Average dry yield, cleaned (SMS)", "value": f"{X['cl_a']:,.2f} bu/ac",
                      "delta": vs(X["cl_a"], X["raw_a"], "bu/ac"),
                      "help": f"As the SMS summary: the Average of {ycol}, area-weighted (the total divided by the "
                              "area)." + (f" The cleaning record gives {float(FM['average_area_weighted']):,.2f} bu/ac."
                                          if FM.get("average_area_weighted") is not None and FM.get("column") == ycol
                                          else "")})
    if X["adjusted"] or X["harm_on"]:
        fcol = X["fcol"]
        cards.append({"label": f"Final yield ({fcol})", "value": f"{X['fin_m']:,.2f} bu/ac",
                      "delta": " · ".join(x for x in (
                          f"average (SMS) {X['fin_a']:,.2f}" if X["fin_a"] is not None else "",
                          f"monitor vs grower {X['d_fin']:+.2f} %" if (X["adjusted"] and CL) else "") if x) or None,
                      "help": "The column to map (the file for DIFM carries it): the cleaned yield"
                              + (f" x the combine factor ({X['fac_txt']})" if X["harm_on"] else "")
                              + (f" x L {float(X['Lf']):.4f} (grower / monitor)" if X["adjusted"] and X["Lf"] is not None
                                 else "") + f". The monitor's {ycol} stays as logged. The mean of the kept readings; "
                                            "the Yield path tab shows each change."})
    if CL and not X["adjusted"]:
        Lf = X["Lf"]
        cards.append({"label": "Monitor vs grower", "value": f"{X['d_fin']:+.2f} %",
                      "delta": (f"grower {X['gro_ac']:,.2f} · monitor {X['mon_ac']:,.2f} bu/ac over "
                                f"{X['area_y']:,.2f} ac" if X["gro_ac"] is not None else None),
                      "help": "The monitor's total against the grower's weight on the same basis"
                              + (", after the combine factor" if L.get("combine_factor_changed_total") else "")
                              + ": + = the monitor read more (L = grower / monitor = "
                              + (f"{float(Lf):.4f}" if Lf is not None else "per combine") + "). Validate only: "
                              "compared, not applied"
                              + (f"; it would confirm the combine factor of {', '.join(X['would'])}" if X["would"]
                                 else "") + ". The Grower's data tab has the details."})
    card_row(cards, key="res_cards")


def yield_path_box(tag: str, C: dict):
    """'What made the final yield' (the Yield path tab): the import the cleaning started from (named by its step),
    what the cleaning changed (each step's share: the table under it), the combine factor and the grower's data
    (applied with 'adjust', only compared with 'validate'), as the plain mean (SMS Edit Legend) and as the Average of
    the SMS summary (total / area)."""
    X = result_numbers(tag, C)
    if X is None or X["A3"]:
        return
    R = C["R"]
    L, harm_on, adjusted, Lf = X["L"], X["harm_on"], X["adjusted"], X["Lf"]

    def path(r, c, h, f):
        # only what moved the yield: the cleaning, a combine factor, the grower's data (the cards' "?" say what the
        # mean and the average are; the Combines and Grower's data tabs the rest)
        s_ = [f"{r:,.2f} &rarr; cleaning {c - r:+.2f} &rarr; <b>{c:,.2f}</b>" if r is not None
              else f"cleaned <b>{c:,.2f}</b>"]
        if harm_on and h is not None:
            s_.append(f"combine factor {h - c:+.2f} &rarr; <b>{h:,.2f}</b>")
        elif factor_outcome(R) is not None:
            s_.append("combine factor not applied (Combines tab)")
        if adjusted and f is not None and h is not None:
            s_.append(f"grower &times; L {Lf:.4f} {f - h:+.2f} &rarr; <b>{f:,.2f}</b>")
        elif L:
            s_.append("grower: compared only" + (f" (adjusted {h * float(Lf):,.2f})" if (Lf and h is not None) else ""))
        return " &rarr; ".join(s_)
    fcol, ycol = X["fcol"], X["ycol"]
    lines = ["<b>What made the final yield</b> &middot; from " + html.escape(X["start"])
             + (f" &middot; map {html.escape(fcol)}" if fcol != ycol else ""),
             "Mean: " + path(X["raw_m"], X["cl_m"], X["h_m"], X["fin_m"])]
    if X["cl_a"] is not None:
        lines.append("Average (SMS): " + path(X["raw_a"], X["cl_a"], X["h_a"], X["fin_a"]))
    note = ("<br><span class=\"oced-note\">Combine factor: " + html.escape(X["fac_txt"]) + "</span>") if harm_on else ""
    st.html('<div class="oced-path">' + "<br>".join(lines) + note + "</div>")
    if adjusted and X["gro_ac"] is not None:
        gap = L.get("yld_level_vs_ticket_pct")
        st.caption(f"Grower: {X['gro_ac']:,.2f} bu/ac over every reading processed",
                   help="L = grower / monitor is set on the totals of every reading processed (the scale weighed all "
                        f"the grain): the grower's bu/ac is that total over {X['area_y']:,.2f} ac ({X['area_src']}). "
                        "The final mean and average are over the kept readings only, so they differ from it"
                        + (f"; the adjusted column of every processed reading sums to {gap:+.2f} % of the weight "
                           "compared" if gap is not None and abs(float(gap)) > 0.05 else "") + ".")


def all_clean_zip() -> str | None:
    """clean_shapefiles/OCED_clean_shapefiles.zip, the clean shapefiles of every cleaned file of the work, when there
    are at least two (None otherwise; a zip left from more cleanings is removed). Written again only when a clean file
    changed since (a large field takes seconds to zip), under a temporary name swapped in at the end; a clean
    shapefile whose .shp and .dbf do not hold the same number of records is left out."""
    if not ss.get("workdir"):
        return None
    zp = os.path.join(ss.workdir, "clean_shapefiles", "OCED_clean_shapefiles.zip")
    C = {t: c for t, c in ss.cleaned.items() if c.get("shp") and os.path.exists(c["shp"])}
    if len(C) < 2:
        if os.path.exists(zp):
            try:
                os.remove(zp)
            except OSError:
                pass
        return None
    parts = []
    for t, c in C.items():
        base = os.path.splitext(c["shp"])[0]
        parts.append((t, base, tuple(mtime(base + e) for e in er.SHP_EXTS)))
    sig = (zp, tuple(parts))
    if os.path.exists(zp) and ss.get("_all_zip_sig") == sig:
        return zp
    tmp = zp + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for t, base, _ in parts:
            n_shp, n_dbf = shapefile_counts(base + ".shp")
            if n_shp != n_dbf:
                continue
            for e in er.SHP_EXTS:
                if os.path.exists(base + e):
                    z.write(base + e, f"{t}/{os.path.basename(base)}{e}")
    try:
        os.replace(tmp, zp)
    except OSError:                                      # the zip is open elsewhere: the previous one stays
        try:
            os.remove(tmp)
        except OSError:
            pass
        return zp if os.path.exists(zp) else None
    ss["_all_zip_sig"] = sig
    return zp


# ------------------------------------------------------------------------------------------------ the monitor's format
NATIVE_DIR = "native"            # <work folder>/native/<tag>/: the clean harvest written in the monitor's format
NATIVE_CAVEAT = ("Not yet tested in SMS: read it into a scratch SMS project, not into the project that holds the "
                 "original data, and do not run Clip / Optimize Swath Widths / 3-sigma on it again.")
NATIVE_HOW = {
    "cnh_cn1": "Unzip it and read it in SMS with Read File(s) > Case IH > AFS Pro 700 (*.vy1), searching the unzipped "
               "folder. Every write gets a new card folder name (SMS refuses a card name it has archived); the task "
               "ids are the original card's.",
    "jd_gs3_rcd": "Unzip it to a folder or a USB stick and read it in SMS as a GreenStar 3 card (start / stop delay "
                  "0). New file ids are written, so SMS does not take it for the card it archived.",
    "jd_jdl": "Unzip it and read it into SMS as raw .jdl logs. If SMS says a file is already archived, rename the .jdl "
              "files with a suffix and import again.",
    "isoxml": "Read it with SMS's ISOXML / TASKDATA import and map the grower, farm, field and product at import.",
}
NATIVE_SETTINGS = ("Use the Processing Settings of the raw read (the clean run's weight to volume, dry moisture and "
                   "min / max yield; expand dry moisture off, start / stop delay 0, flow shift 0, manual swath off) and "
                   "compare SMS's Summary and points with the totals shown here.")
NATIVE_SETTINGS_NAMED = ("Use the SMS settings named in the line beside the writer (where a line names them; for any "
                         "other writer the Processing Settings of the raw read) and compare SMS's Summary and points "
                         "with the totals shown here.")
# a line beside the writer says only that the grain timing differs (no settings to name): the raw read's settings, and
# why its totals will not match
NATIVE_SETTINGS_TIMING = NATIVE_SETTINGS[:-1] + " (the line beside the writer says why the totals differ)."
NATIVE_FILE_LABEL = {"cnh_cn1": "CNH_clean_card", "jd_gs3_rcd": "GS3_clean_card", "jd_jdl": "JDL_clean_logs",
                     "isoxml": "ISOXML_TASKDATA"}
NATIVE_LOOSE = ("notes", "warnings")
# the folder each writer writes into under native/<tag>/ (short: the tag is in the path once already), and the most
# characters a writer adds after that folder besides the input card's own tree (ISOXML: _<14-digit stamp> and
# TASKDATA/LINKLIST.XML; Case IH: <8>.cn1/; Gen4: _<15-character stamp> when the folder is there already)
NATIVE_OUT_NAME = {"cnh_cn1": "cn1", "jd_gs3_rcd": "gs3", "jd_jdl": "jdl", "isoxml": "isoxml"}
NATIVE_OUT_KEY = {"jd_gs3_rcd": "folder_name"}            # the writer's own name for the option (else out_name)
NATIVE_EXTRA = {"cnh_cn1": len("/12345678.cn1"), "jd_jdl": len("_20261111-120000"),
                "isoxml": len("_20261111120000/TASKDATA/LINKLIST.XML")}


def native_dir(tag: str) -> str:
    return os.path.join(ss.workdir, NATIVE_DIR, tag)


def _input_tree_depth(root: str | None, fid: str) -> int:
    """The longest path a writer copies from the input card (relative to where it starts the card in its folder):
    every file under the input folder (a Case IH card: below its .cn1 folder; a GreenStar 3 card: from the folder
    above its cards, as the writer keeps their own folder names; Gen4 logs: below the folder that holds JD-Data, under
    a number when there are several, as the writer writes them: jd_jdl_write.out_relpath). 0 without an input
    folder."""
    if not root or not os.path.isdir(root):
        return 0
    base = root
    if fid == "jd_jdl":
        from engine.formats import jd_jdl_write as jw
        roots = jw.record_roots(root)
        return max((len(jw.out_relpath(os.path.join(d, f), roots)) for d, _, fs in os.walk(root) for f in fs),
                   default=0)
    if fid == "jd_gs3_rcd":
        from engine.formats import jd_gs3_rcd_write as gw
        cards = sorted({gw._card_root(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs
                        if f.lower().endswith(".fdl")})
        if cards:
            base = os.path.commonpath(cards) if len(cards) > 1 else os.path.dirname(cards[0])
    best = 0
    for d, _, fs in os.walk(root):
        for f in fs:
            rel = os.path.relpath(os.path.join(d, f), base)
            if fid == "cnh_cn1":
                parts = re.split(r"[\\/]", rel)
                cut = max((i for i, x in enumerate(parts) if x.lower().endswith(".cn1")), default=-1)
                rel = os.sep.join(parts[cut + 1:])
            best = max(best, len(rel))
    return best


def native_depth(t: str, fid: str, src: dict | None) -> int:
    """The longest path the writer of fid will create for the file `t` (native/<tag>/<NATIVE_OUT_NAME>/...): the work
    folder, the tag, the writer's folder, what the writer adds and the input card's own tree."""
    root = (src or {}).get("input_root") if fid != nw.ISOXML else None
    return (len(os.path.abspath(native_dir(t))) + 1 + len(NATIVE_OUT_NAME.get(fid, fid)) + NATIVE_EXTRA.get(fid, 0)
            + (1 + _input_tree_depth(root, fid) if root else 0))


def writer_source(D: dict) -> dict | None:
    """The decode source a writer reads (engine.run.decode_source of a raw dataset), its paths found again under the
    work folder when the work was moved or reopened elsewhere (the input folder, the decode report, the decoded
    file: engine/works.py resolve_moved) and the decode report the work keeps (the same report old_decode reads, so
    that the step-4 buttons and the 'older version' message agree when its JSON is gone). A point export has no raw
    source (ISOXML only): its import's weight to volume and dry moisture as {kind 'export', options}, else None."""
    src = D.get("source")
    if not isinstance(src, dict) or src.get("kind") != "decoded":
        # a point export: no raw source, only what its import as SMS used (the weight to volume and the dry moisture
        # the ISOXML writer needs when the file's columns do not give them)
        RS = (D.get("sms_import") or {}).get("resolved") or {}
        if not (RS.get("test_weight_lb_bu") or RS.get("dry_moisture_pct") is not None):
            return None
        return {"kind": "export", "format": None, "label": D.get("label"),
                "options": {"test_weight_lb_bu": RS.get("test_weight_lb_bu"),
                            "std_moisture_pct": RS.get("dry_moisture_pct"),
                            "crop": si.crop_key(RS.get("product")) if RS.get("product") else None}}
    s = dict(src)
    wd = ss.workdir
    root = ew.input_root(D, wd) if hasattr(ew, "input_root") else s.get("input_root")
    if root:
        s["input_root"] = root
    for k in ("decode_report", "decoded_shp"):
        if s.get(k):
            s[k] = ew.resolve_moved(ew.abspath(s[k], wd), wd)
    if isinstance(D.get("report"), dict) and not isinstance(s.get("report"), dict):
        s["report"] = D["report"]
    return s


def clean_machines(shp: str) -> list:
    """The machines of a clean file as a writer keys them (its machine column, else its dataset column)."""
    try:
        import pyogrio
        cols = list(pyogrio.read_info(shp)["fields"])
        det = yc.detect_columns(cols)
        col = det.get("machine") or det.get("dataset")
        if not col:
            return []
        v = pyogrio.read_dataframe(shp, columns=[col], read_geometry=False)[col].astype(str)
        return sorted(set(v.replace({"": np.nan, "nan": np.nan, "None": np.nan}).dropna()))
    except Exception:                                    # no list: the writers apply nothing then
        return []


def native_factors(C: dict) -> tuple[dict | None, str]:
    """What the clean yields of a cleaning contain besides the monitor's grain: ({machine: factor} for the written
    grain, the text), None when nothing was applied in step 3. The combine factor applied (factor_outcome) times,
    when the yields were adjusted to the grower's weight, the L in the file (factor_final: after the combine factor),
    for every machine of the clean file. The writers rebuild the grain from the raw records (CNH, GreenStar 3, Gen4)
    or from the clean file's Yld_Mass_W (ISOXML), which hold neither, so the same factors apply to every format."""
    R = C.get("R") or {}
    FO = factor_outcome(R)
    applied = dict((FO or {}).get("applied") or {})
    L = R.get("level") or {}
    Lf = None
    if C.get("adjusted") and L:
        Lf = L.get("factor_final") if L.get("factor_final") is not None else L.get("factor")
    if not applied and Lf is None:
        return None, ""
    machines = sorted(set(clean_machines(C["shp"])) | set(applied)
                      | {str(k) for k in ((R.get("machines") or {}).get("factor_applied") or {})})
    if not machines:
        return None, "the clean file names no machine: no factor can be written"
    f = {m: float(applied.get(m, 1.0)) * (float(Lf) if Lf is not None else 1.0) for m in machines}
    parts = []
    if applied:
        parts.append("the combine factor (" + ", ".join(f"{m} x {v:.4f}" for m, v in applied.items()) + ")")
    if Lf is not None:
        parts.append(f"the grower's level L {float(Lf):.4f}")
    return f, " and ".join(parts)


def _native_summary(res: dict, factors: bool = False) -> dict:
    """The writer's own check in one line: {ok (True / False / None), line, problems}. factors: the written grain
    carries the factors of step 3 (the GreenStar 3 writer then compares it with the clean file x the factor)."""
    fid = res.get("format_id")
    chk = res.get("check") or {}
    if fid == "cnh_cn1" and chk:
        line = (f"decoded back: {int(chk.get('readings_written') or 0):,} readings on the written card, "
                f"{int(chk.get('readings_kept') or 0):,} kept, {int(chk.get('readings_clean') or 0):,} clean rows")
        return {"ok": bool(chk.get("ok")), "line": line, "problems": list(chk.get("problems") or [])}
    if fid == "jd_gs3_rcd" and chk:
        if chk.get("error"):
            return {"ok": False, "line": f"the written card could not be checked: {chk['error']}", "problems": []}
        miss, extra = int(chk.get("missing") or 0), int(chk.get("extra") or 0)
        ngd = int(chk.get("n_grain_differs") or 0)
        mx = (chk.get("max_abs") or {}).get("wet_kg")
        kb = int(chk.get("kept_below_min") or 0)        # kept readings a reader with the minimum yield leaves out
        line = (f"decoded back: {int(chk.get('decoded') or 0):,} readings, {int(chk.get('matched') or 0):,} matched, "
                f"{miss:,} missing, {extra:,} extra"
                + (f" ({kb:,} of the kept readings read below the minimum yield and are not given back)" if kb else "")
                + f"; the grain of {ngd:,} reading(s) differs from the clean file"
                + (" x the factor of its combine" if factors else "") + " by more than 0.5 g"
                + (f" (at most {float(mx) * 2.20462262185:,.2f} lb)" if (ngd and mx is not None) else ""))
        # the writer reports a reading's grain that moved to a neighbouring record as a note, not as a failure: the
        # written grain total is in the counts line (grain kept x factor / written)
        return {"ok": miss == 0 and extra == 0, "line": line, "problems": []}
    if fid == "jd_jdl" and chk:
        line = (f"decoded back: {int(chk.get('n_matched') or 0):,} of {int(res.get('n_kept') or 0):,} kept readings, "
                f"{int(chk.get('n_missing') or 0):,} missing, {int(chk.get('n_extra') or 0):,} extra")
        return {"ok": bool(chk.get("ok")), "line": line, "problems": []}
    V = res.get("verify") or {}
    if fid == nw.ISOXML and V:
        # a reading with no grain is written but is not a point when the set is read (SMS: no flow, no point)
        ng = int(V.get("n_no_grain") or 0)
        line = (f"{int(res.get('n_kept') or 0):,} readings written, read back as {int(V.get('n_points') or 0):,} "
                "points" + (f" ({ng:,} readings with no grain are not points)" if ng else "")
                + f", {int(V.get('n_matched') or 0):,} matched; area "
                f"of a reading within {100 * float(V.get('p99_area_rel') or 0):.2f} % (99th percentile), the largest "
                f"{100 * float(V.get('max_area_rel') or 0):.2f} %")
        ok = int(V.get("n_points") or -1) == int(V.get("n_matched") or -2) == int(res.get("n_kept") or -3) - ng
        return {"ok": ok, "line": line, "problems": []}
    return {"ok": None, "line": "no check of the written file", "problems": []}


def _totals_rows(res: dict) -> list:
    """The totals table of a write: [{'': what, n, area_ac, wet_lb, dry_bu, bu_ac, moisture_pct}]."""
    def row(what, T):
        if not isinstance(T, dict) or not T:
            return None
        n = T.get("n", T.get("gps_count", T.get("n_points")))
        return {"": what, "readings": None if n is None else int(n), "area (ac)": T.get("area_ac"),
                "wet (lb)": T.get("wet_lb"), "dry (bu)": T.get("dry_bu"),
                "dry yield (bu/ac)": T.get("bu_ac", (T["dry_bu"] / T["area_ac"]) if (T.get("dry_bu") is not None
                                                                                     and T.get("area_ac")) else None),
                "moisture (%)": T.get("moisture_pct")}
    fid = res.get("format_id")
    out = []
    if fid == "cnh_cn1":
        out = [row("the clean file", res.get("clean_totals")), row("the card's points", res.get("points_totals")),
               row("what the SMS Summary should show", res.get("expected_summary"))]
    elif fid == "jd_gs3_rcd":
        out = [row("what SMS should show if it reads the card as OCED does", res.get("expected_summary"))]
    elif fid == "jd_jdl":
        ES = res.get("expected_summary") or {}
        out = [row("the logs as read", ES.get("all") if isinstance(ES, dict) else None),
               row("the clean file", res.get("clean_summary"))]
    elif fid == nw.ISOXML:
        V = res.get("verify") or {}
        out = [row("written", res.get("totals")), row("read back", V.get("totals_read"))]
    return [r for r in out if r]


def native_record(t: str, C: dict, res: dict, opts: dict) -> dict:
    """The small record of one write kept next to it (native/<tag>/<format>.json): what the page shows of it, the zip
    relative to the work folder, the clean file it was written from (its modification time: a later cleaning makes
    the write stale) and the options."""
    keep = {}
    for k in ("format_id", "label", "native", "sms_tested", "n_kept", "n_removed", "n_not_offered", "logs_written",
              "logs_in_units", "mode", "totals_mode"):
        if res.get(k) is not None:
            keep[k] = res[k]
    if res.get("format_id") == "cnh_cn1":
        keep["card_names"] = sorted(str(v) for v in (res.get("card_names") or {}).values())
    if res.get("format_id") == "jd_gs3_rcd":
        G_ = ((res.get("grain") or {}).get("kg") or {})
        keep["grain_lb"] = {k: float(G_[k]) * 2.20462262185 for k in ("kept_x_factor", "written") if G_.get(k) is not None}
    ES = res.get("expected_summary") if isinstance(res.get("expected_summary"), dict) else {}
    if int(ES.get("n_below_min") or 0) > 0:              # written, but below the reader's minimum yield
        keep["below_min"] = {"n": int(ES["n_below_min"]), "min_yield": ES.get("min_yield")}
    elif "n_below_min" not in ES and (opts.get("factors") or not opts.get("widths", True)
                                      or written_min_yield(t)[1]):
        # a writer that does not count them (its totals then hold them): the readings written whose dry yield x the
        # factor of their combine (with the logged widths: their logged yield) falls below the minimum of the reader
        # (the import's; for a point export written as ISOXML task data, SMS's minimum for task data)
        BM = below_min_written(t, C, opts.get("factors") or {}, widths=bool(opts.get("widths", True)))
        if BM:
            keep["below_min"] = {**BM, "in_totals": True}
    if res.get("format_id") == nw.ISOXML:
        keep["machines"] = [{k: m.get(k) for k in ("machine", "n_readings", "sections", "section_mm", "header_mm")}
                            for m in (res.get("machines") or [])]
        keep["index_csv"] = ew.relpath(res.get("index_csv"), ss.workdir) if res.get("index_csv") else None
    wd = ss.workdir
    tot = _totals_rows(res)
    if opts.get("factors"):                              # the written grain carries them, the clean file not
        for r in tot:
            if r[""] == "the clean file":
                r[""] = "the clean file (without the factors of step 3)"
    return {**keep, "zip": ew.relpath(res.get("zip"), wd), "path": ew.relpath(res.get("path"), wd),
            "files_changed": len(res.get("files_changed") or []), "notes": [str(x) for x in res.get("notes") or []],
            "warnings": [str(x) for x in res.get("warnings") or []],
            "check": _native_summary(res, factors=bool(opts.get("factors"))),
            "totals": tot, "written_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "clean_shp": os.path.basename(C["shp"]), "clean_mtime": mtime(C["shp"]), "options": opts,
            "app_version": VERSION}


def written_min_yield(t: str) -> tuple:
    """(minimum, raised): the minimum yield SMS applies when it reads the clean harvest of `t` written in a monitor's
    format. Raw monitor data is written in its own format and read with the minimum of the file's import (raised
    False). A point export, imported as SMS's generic import (no minimum above 0), is written as ISOXML task data,
    which SMS reads as raw data: the minimum SMS gives ISOXML task data (raised True when it lies above the import's),
    unless the user typed the import's minimum."""
    IM = (ss.datasets.get(t) or {}).get("sms_import") or {}
    RS = IM.get("resolved") or {}
    lo = RS.get("min_yield")
    if IM.get("family") != "point" or (IM.get("sources") or {}).get("min_yield") == si.SRC_YOU:
        return lo, False
    try:
        iso = si.resolve(si.settings({"product": RS.get("product")} if RS.get("product") else {}), None, None,
                         "isoxml")["min_yield"]
    except ValueError:
        iso = si.SMS_JD_MIN_YIELD
    own = 0.0 if lo in (None, si.AUTO) else float(lo)
    return (iso, True) if iso is not None and float(iso) > own else (lo, False)


def below_min_written(t: str, C: dict, factors: dict | None, widths: bool = True) -> dict | None:
    """{n, min_yield} of the readings of `t` written whose dry yield x the factor of their combine falls below the
    minimum yield of the file's import as SMS: written, but a reader with that minimum (SMS) leaves them out. The dry
    yield is the clean file's yield column as the cleaning finds it (yc.detect_columns: Yld_Vol_Dr, an Operations
    Center VRYIELDVOL ...); widths False: the writers keep the logged width of a narrowed reading, which then reads
    its logged yield, the clean one / Swath_Scl. The minimum is the reader's (written_min_yield): for a point export,
    whose clean file keeps the readings below SMS's minimum for raw data, they count also without factors. None when
    there are none, no minimum or no dry yield column."""
    lo, raised = written_min_yield(t)
    factors = factors or {}
    if (not factors and widths and not raised) or lo is None or lo == si.AUTO:
        return None
    try:
        import pyogrio
        cols = list(pyogrio.read_info(C["shp"])["fields"])
        det = yc.detect_columns(cols)
        mcol = det.get("machine") or det.get("dataset")
        ycol = det.get("yield")
        if not ycol:
            return None
        scol = "Swath_Scl" if (not widths and "Swath_Scl" in cols) else None
        df = pyogrio.read_dataframe(C["shp"], columns=[ycol] + [c for c in (mcol, scol) if c], read_geometry=False)
    except Exception:                                    # the count is a note: no count, no note
        return None
    f = (df[mcol].astype(str).map(lambda m: float(factors.get(m, 1.0))).to_numpy(float) if mcol
         else np.ones(len(df)))
    y = pd.to_numeric(df[ycol], errors="coerce").to_numpy(float)
    if scol:
        s = pd.to_numeric(df[scol], errors="coerce").to_numpy(float)
        y = np.where(np.isfinite(s) & (s > 0), y / np.where(s > 0, s, 1.0), y)
    n = int((y * f < float(lo)).sum())
    return {"n": n, "min_yield": float(lo)} if n else None


def native_results(t: str, C: dict | None) -> dict:
    """{format id: record} of the clean harvest of `t` written in a monitor's format (native/<tag>/<format>.json),
    each with 'zip_abs' (the zip, found again under a moved work folder) and 'stale' (written from another cleaning
    than the one on screen, or its zip is gone)."""
    out = {}
    if not ss.get("workdir") or not C or not C.get("shp"):
        return out
    d = native_dir(t)
    if not os.path.isdir(d):
        return out
    for n in sorted(os.listdir(d)):
        if not n.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(d, n), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(rec, dict) or not rec.get("format_id"):
            continue
        z = ew.resolve_moved(ew.abspath(rec.get("zip"), ss.workdir), ss.workdir) if rec.get("zip") else None
        rec["zip_abs"] = z if (z and os.path.exists(z)) else None
        same = (rec.get("clean_shp") == os.path.basename(C["shp"])
                and abs(float(rec.get("clean_mtime") or 0) - mtime(C["shp"])) < 1e-3)
        rec["stale"] = (not same) or rec["zip_abs"] is None
        out[str(rec["format_id"])] = rec
    return out


NATIVE_ASIDE = "~"               # an earlier Case IH / GreenStar 3 card set waits under <name>~ while a new one is
                                 # written (native_set_aside)
NATIVE_REPLACED = ("cnh_cn1", "jd_gs3_rcd")     # writers that write their card folder again under the same name


def _remove_path(p: str):
    shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)


def native_put_back(moved) -> list:
    """After a write that was refused or failed: what the writer left in place of the earlier set is removed and the
    earlier set (native_set_aside) moved back. Returns the asides that could not be put back."""
    left = []
    for p, a in reversed(moved):
        try:
            if os.path.lexists(p):
                _remove_path(p)
            os.replace(a, p)
        except OSError:
            left.append(a)
    return left


def native_drop_aside(moved) -> list:
    """After a write that succeeded: the earlier set moved aside is removed. Returns the names that could not be."""
    left = []
    for _, a in moved:
        try:
            _remove_path(a)
        except OSError:
            left.append(os.path.basename(a))
    return left


def native_written_only(folder: str, fmt_id: str) -> bool:
    """Whether the card folder `folder` holds only what the writer of fmt_id writes there, the test the writer itself
    makes before it replaces such a folder: Case IH (engine/formats/cnh_cn1_write.py), only .cn1 card folders;
    GreenStar 3 (engine/formats/jd_gs3_rcd_write.py _check_output), only card files (_OUT_EXTS) at any depth."""
    if not os.path.isdir(folder) or os.path.islink(folder):
        return False
    if fmt_id == "cnh_cn1":
        return all(x.lower().endswith(".cn1") and os.path.isdir(os.path.join(folder, x)) for x in os.listdir(folder))
    from engine.formats import jd_gs3_rcd_write as gw
    return all(f.lower().endswith(gw._OUT_EXTS) for _, _, fs in os.walk(folder) for f in fs)


def native_set_aside(out: str, fmt_id: str) -> list:
    """Case IH and GreenStar 3 (NATIVE_REPLACED): the card set written before under `out` (its folder
    native/<tag>/<cn1|gs3> and its zip) moved aside to the same name + NATIVE_ASIDE, so that a write that is refused
    or fails leaves it as it was (native_put_back) and one that succeeds replaces it (native_drop_aside), as the other
    formats' sets are replaced once the new one is written (drop_earlier_sets). One character longer: native_depth
    keeps a write within PATH_LIMIT (250), the aside within the 259 Windows opens. An aside left behind is dealt with
    first: the writers write the zip last, so a set with its zip is whole (a write that finished, whose aside could
    not be removed: the aside goes), and a set without it was left half-written by a write that stopped (the app
    closed): it goes and the aside is put back. A card folder that holds
    anything the writer does not write (native_written_only) is not moved: the writer refuses it, as it refuses any
    such folder, and nothing changes. Returns the (path, aside) pairs moved; ValueError, nothing changed, when a file
    of the earlier set is held open."""
    base = NATIVE_OUT_NAME.get(fmt_id)
    if fmt_id not in NATIVE_REPLACED or not base:
        return []
    pairs = [(os.path.join(out, base), os.path.join(out, base + NATIVE_ASIDE)),
             (os.path.join(out, base + ".zip"), os.path.join(out, base + NATIVE_ASIDE + ".zip"))]
    whole = os.path.lexists(pairs[1][0])                 # the zip is written last: the set in place is complete
    for p, a in pairs:
        if os.path.lexists(a):
            try:
                if whole and os.path.lexists(p):
                    _remove_path(a)                      # a write that finished: its aside is stale
                else:
                    if os.path.lexists(p):
                        _remove_path(p)                  # half-written by a write that stopped
                    os.replace(a, p)
            except OSError:
                pass                                     # then moving the set aside below says what to close
    if os.path.lexists(pairs[0][0]) and not native_written_only(pairs[0][0], fmt_id):
        return []
    moved = []
    for p, a in pairs:
        if not os.path.lexists(p):
            continue
        try:
            os.replace(p, a)
        except OSError:
            native_put_back(moved)
            raise ValueError(f"not written, nothing was changed: the earlier write {p} could not be moved aside while "
                             "the new one is written (a file of it is open in another program?): close it and write "
                             "again.") from None
        moved.append((p, a))
    return moved


def native_room(rest: int) -> int:
    """The longest workspace folder in which a new work can write a file in the monitor's format whose deepest path
    adds `rest` characters to the work folder and the tag (native_depth: native/, the writer's folder, what it adds
    and the input card's own tree), whatever the file's name: a work folder name of the full 16 + WORK_FOLDER_CHARS
    characters and the longest tag tag_budget gives there. As x + tag_budget_for(x) never falls as x grows, the first
    length from the top that fits is the longest. 0: none."""
    for n in range(PATH_LIMIT, 0, -1):
        x = n + 1 + 16 + WORK_FOLDER_CHARS
        if x + tag_budget_for(x) + rest <= PATH_LIMIT:
            return n
    return 0


def native_too_deep_msg(t: str, deep: int) -> str:
    """Step 4's refusal of a write whose deepest path (native_depth) would be `deep` characters, over PATH_LIMIT, and
    what to do. A new work of the same input (Open in step 1) has a folder of _new_work_len characters, and its tag
    for the file is the file's name cut to tag_budget_for that folder (fit_tag): not shorter than the tag the file has
    now when that fits the budget, and longer when this tag was cut shorter. Open the data again when the write fits
    there whatever tag the new work gives; when it fits only with the tag the file has now, the same and what to do
    should the write be refused there too; else a shorter workspace (workspace_advice, of at most what native_room
    gives), or, when no workspace is short enough, that the input's own folder tree is too deep."""
    wd = os.path.abspath(ss.workdir)
    rest = deep - len(wd) - len(t)                       # the tag is in native/<tag>/ once
    new = _new_work_len(wd)
    b = tag_budget_for(new)
    room = native_room(rest)
    deep_tree = "the input's own folder tree is too deep to be written below any work folder."
    ws = workspace_advice(room, "this write") if room >= len("C:\\OCED") else deep_tree
    again = "open the data again (step 1), then clean and write it in the new work."
    if new + b + rest <= PATH_LIMIT:
        what = again
    elif new + min(len(t), b) + rest <= PATH_LIMIT:
        then = workspace_advice(room, "this write", as_deep=False) if room >= len("C:\\OCED") else deep_tree
        what = (again + f" A new work may give the file a longer name than {t} (up to {b} characters), and the write "
                "would be refused there too: then " + then[:1].lower() + then[1:])
    else:
        what = ws
    return (f"not written: the deepest file would be {deep} characters long, {deep - PATH_LIMIT} over the {PATH_LIMIT} "
            f"this app keeps to (Windows opens a path up to 259). The work folder {ss.workdir} is {len(wd)} "
            "characters: " + what[:1].lower() + what[1:])


def _cleaning_import(t: str, C: dict | None) -> dict:
    """The import record the cleaning on screen was made from (its settings['sms_import']), else the file's."""
    IM = (((C or {}).get("R") or {}).get("settings") or {}).get("sms_import")
    return IM if isinstance(IM, dict) else ((ss.datasets.get(t) or {}).get("sms_import") or {})


TIMING_KEYS = (("flow_shift_s", "flow shift"), ("start_delay_s", "start delay"), ("stop_delay_s", "stop delay"))


def _monitor_crop_text(keeps) -> str:
    """The monitor's crop in the step-4 line: its name when it is an SMS product name, else the card's own text
    quoted, with the SMS product it stands for (a GreenStar 3 card's name cut at its field's width: "'Wheat (Hard Red
    Spri' (as the monitor stores it; SMS: Wheat - Spring)")."""
    s = str(keeps or "").strip()
    if not s:
        return "of the card"
    if si.sms_product(s) == s:
        return s
    k = si.crop_key(s)
    sms = si.sms_product(s) or (common.product_name(k) if k else None)
    return f"'{s}' (as the monitor stores it" + (f"; SMS: {sms})" if sms and sms != s else ")")


def native_read_settings(t: str, C: dict | None, fid: str) -> dict | None:
    """What SMS must be told to read the clean harvest of `t` written in the format fid with the clean file's yields,
    when its own read of that file would not give them: {keeps, product, tw, dm, manual, expand, timing, text}; None
    when SMS's read with its Processing Settings untouched gives them (or the import kept no record). A monitor's own
    format (Case IH card, GreenStar 3 card, Gen4 logs) keeps the crop, calibration, moisture and grain timing the
    monitor logged: SMS reads it as it reads the original data (the file's default import, step 1), so another
    product, weight to volume, dry moisture, Expand Dry Moisture or Use Manual Moisture of the cleaning's import must be
    set in SMS; a flow shift or start / stop delay of the cleaning's import ('timing': [(name, seconds)]) moved the
    grain between readings, which the file does not carry, so no read of it gives the clean file's yields exactly (the
    line says so). ISOXML task data written from the clean readings names the crop of the clean file and carries its
    moisture: SMS gives such a task its own weight and dry moisture for that crop (isoxml.ISO_SMS_CROPS, else the
    product table)."""
    D = ss.datasets.get(t) or {}
    IM = _cleaning_import(t, C)
    RS = IM.get("resolved") if isinstance(IM.get("resolved"), dict) else None
    if not RS or not RS.get("test_weight_lb_bu") or RS.get("dry_moisture_pct") is None:
        return None
    P = si.crop_key(RS.get("product")) if RS.get("product") else None
    timing = []
    if fid == nw.ISOXML:
        sv = iso_crops().get(P) if P else None
        mon = ({"crop": P, "test_weight_lb_bu": sv[0], "dry_moisture_pct": sv[1], "basis": "sms_crop"} if sv else
               ({"crop": P} if P else None))
        try:
            R0 = si.resolve(si.settings({}), P, mon, "isoxml")
        except ValueError:
            return None
        keeps, manual = None, False                       # the written task data carries the clean moisture
    else:
        IM0 = default_of(D).get("sms_import") or {}
        R0 = IM0.get("resolved") if isinstance(IM0.get("resolved"), dict) else None
        if R0 is None:
            B = import_basis(D)
            if B is None:
                return None
            R0 = default_resolved(B)
        keeps = IM0.get("crop") or (import_basis(D) or {}).get("crop") or R0.get("product") or None
        manual = bool(RS.get("use_manual_moisture"))
        for k, what in TIMING_KEYS:                       # the grain moved between readings by the import
            x = RS.get(k)
            if x is not None and float(x) != 0.0 and not _same_value(float(x), float(R0.get(k) or 0.0)):
                timing.append((what, float(x)))
    same = (si.crop_key(R0.get("product")) == P and _same_value(R0.get("test_weight_lb_bu"), RS["test_weight_lb_bu"])
            and _same_value(R0.get("dry_moisture_pct"), RS["dry_moisture_pct"])
            and bool(R0.get("expand_dry_moisture")) == bool(RS.get("expand_dry_moisture")) and not manual)
    if same and not timing:
        return None
    name = IM.get("sms_product") or (common.product_name(P) if P else None) or "the product"
    out = {"keeps": keeps, "product": name, "tw": float(RS["test_weight_lb_bu"]), "dm": float(RS["dry_moisture_pct"]),
           "manual": (float(RS["manual_moisture_pct"]) if (manual and RS.get("manual_moisture_pct") is not None)
                      else None), "expand": bool(RS.get("expand_dry_moisture")), "timing": timing}

    def v(x):                                            # 2 decimals, more when the value has them (a card's own)
        return f"{x:.2f}" if abs(x - round(x, 2)) < 1e-9 else f"{round(x, 4):g}"
    how = (f"product {name}, weight to volume {v(out['tw'])} lb/bu, dry moisture {v(out['dm'])} %"
           + (", Expand Dry Moisture on" if out["expand"] else "")
           + (f", Use Manual Moisture {v(out['manual'])} %" if out["manual"] is not None else ""))
    if fid == nw.ISOXML:
        out["text"] = ("This file names the crop of the clean file and carries its moisture, but SMS gives such task "
                       "data its own weight to volume and dry moisture for that crop: to get the clean file's yields, "
                       f"read it into SMS with {how}.")
        return out
    crop_t = _monitor_crop_text(keeps)
    late = ""
    if timing:
        tm = ", ".join(f"{w} {x:g} s" for w, x in timing)
        late = (f"the cleaning's import moved the grain between readings ({tm}) and this file keeps the grain timing "
                "the monitor logged, so no read of it gives the clean file's yields exactly: neither SMS's default "
                "read nor the same " + ("values" if len(timing) > 1 else "value") + " set in SMS reproduces them")
    if same:
        out["text"] = f"This file keeps the monitor's crop {crop_t} and its logged moisture, but {late}."
    elif timing:
        out["text"] = (f"This file keeps the monitor's crop {crop_t} and its logged moisture: read it into SMS with "
                       f"{how} for the clean file's crop and moisture; but {late}.")
    else:
        out["text"] = (f"This file keeps the monitor's crop {crop_t} and its logged moisture: to get the clean file's "
                       f"yields, read it into SMS with {how}.")
    return out


def native_caveat_text(note: str, RD: dict | None) -> str:
    """A writer's 'not yet tested in SMS' note when step 4 names how SMS reads the written file (RD, first in the
    notes): it points at the settings of that first note, not at the Processing Settings of the raw read (with those
    SMS gives other yields than the clean file's)."""
    s = str(note)
    if not RD or "Processing Settings of the raw read" not in s:
        return note
    if "read it into SMS with" not in str(RD.get("text")):       # only the grain timing differs: the raw read's
        return s.replace("the Processing Settings of the raw read", "the Processing Settings of the raw read (the "
                                                                    "first note says why its yields still differ)")
    return s.replace("the Processing Settings of the raw read", "the settings named in the first note")


def write_native(t: str, C: dict, fmt_id: str, opts: dict, log=print) -> dict:
    """Writes the clean harvest of `t` in the format fmt_id (engine/formats/native_write.py write) into
    native/<tag>/ and keeps its record there (native/<tag>/<format>.json). opts: widths, apply (the factors of step
    3), new_ids, advanced (the writer's own options). Raises ValueError (the writers' plain messages; for a Gen4 card
    jd_jdl_write.JdlReferenceError with .logs)."""
    D = ss.datasets[t]
    src = writer_source(D)
    fac, _ = native_factors(C) if opts.get("apply") else (None, "")
    out = native_dir(t)
    deep = native_depth(t, fmt_id, src)
    if deep > PATH_LIMIT:                                # Windows opens a path up to 259 characters
        raise ValueError(native_too_deep_msg(t, deep))
    os.makedirs(out, exist_ok=True)
    adv = dict(opts.get("advanced") or {})
    adv.setdefault(NATIVE_OUT_KEY.get(fmt_id, "out_name"), NATIVE_OUT_NAME.get(fmt_id, fmt_id))
    if fmt_id == "cnh_cn1":
        adv.setdefault("registry", os.path.join(WORKSPACE, "cn1_card_names.json"))   # one name never given twice
    RS_c = _cleaning_import(t, C).get("resolved") or {}
    if RS_c.get("use_manual_moisture") and RS_c.get("manual_moisture_pct") is not None:
        adv["manual_moisture_pct"] = float(RS_c["manual_moisture_pct"])   # the file keeps the logged moisture
    moved = native_set_aside(out, fmt_id)               # a Case IH / GreenStar 3 card written before
    try:
        res = nw.write(fmt_id, src, C["shp"], out, widths=bool(opts.get("widths", True)), factors=fac,
                       new_ids=bool(opts.get("new_ids", True)), log=log, isoxml_fallback=src is not None, **adv)
    except BaseException as e:                           # refused or failed: the earlier set comes back as it was
        back = native_put_back(moved)
        kept = (" The earlier write could not be put back: it is in " + ", ".join(back) + ".") if back else ""
        if isinstance(e, OSError) and (getattr(e, "winerror", None) == 206 or "too long" in str(e).lower()):
            raise ValueError(f"not written: a path of the output is too long for Windows ({e.filename or e}). Open the "
                             "data again in a shorter workspace folder (closer to the drive's root)." + kept) from None
        if kept and isinstance(e, Exception):
            raise ValueError(f"not written ({type(e).__name__}: {e}).{kept}") from e
        raise
    adv.pop("registry", None)
    for k in ("out_name", "folder_name", "manual_moisture_pct"):
        adv.pop(k, None)
    RD = native_read_settings(t, C, fmt_id)
    if RD:                                               # how SMS reads it with the clean file's yields
        res = {**res, "notes": [RD["text"]] + [native_caveat_text(n, RD) for n in (res.get("notes") or [])
                                               if n != RD["text"]]}
    left = drop_earlier_sets(out, fmt_id, res) + native_drop_aside(moved)
    if left:
        res = {**res, "warnings": list(res.get("warnings") or []) + [
            "an earlier write of this format could not be removed (a file of it is open?): "
            + ", ".join(os.path.join(out, n) for n in left)]}
    rec = native_record(t, C, res, {"widths": bool(opts.get("widths", True)), "factors": fac,
                                    "new_ids": bool(opts.get("new_ids", True)), "advanced": adv})
    p = os.path.join(out, f"{fmt_id}.json")
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, default=yc._json_default)
    os.replace(p + ".tmp", p)
    return rec


def drop_earlier_sets(out: str, fmt_id: str, res: dict) -> list:
    """One written set per format under native/<tag>/: the Gen4 and ISOXML writers do not overwrite an earlier set
    (the Gen4 one adds a time stamp when its folder is there, ISOXML stamps every set), so once a new write succeeded
    the earlier sets of the same format (folder, zip, ISOXML index) are removed, as the Case IH and GreenStar 3
    writers replace theirs. Returns the names that could not be removed."""
    base = NATIVE_OUT_NAME.get(fmt_id)
    if fmt_id not in ("jd_jdl", nw.ISOXML) or not base or not os.path.isdir(out):
        return []
    keep = {os.path.normcase(os.path.basename(str(res.get(k)))) for k in ("path", "zip", "index_csv") if res.get(k)}
    pat = re.compile(rf"^{re.escape(base)}(_\d{{8}}-?\d{{6}})?(\.zip|_index\.csv)?$", re.I)
    left = []
    for n in sorted(os.listdir(out)):
        if not pat.match(n) or os.path.normcase(n) in keep:
            continue
        p = os.path.join(out, n)
        try:
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        except OSError:
            left.append(n)
    return left


def _native_result_view(t: str, fid: str, NR: dict, key: str):
    """The last write of one format: its download, counts, the writer's check, the totals, warnings and notes."""
    stale = NR.get("stale")
    head = (f"**{NR.get('label') or fid}** · written {NR.get('written_at') or ''}"
            + (" · experimental" if fid == nw.ISOXML else ""))
    st.markdown(head)
    if stale:
        st.warning("Written from an earlier cleaning of this file (or its zip is gone): write it again to match the "
                   "clean file on screen.", icon=":material/sync_problem:")
    if NR.get("zip_abs"):
        zp = NR["zip_abs"]
        st.download_button(f"Download the {NR.get('label') or fid} (.zip)", data=lambda p=zp: open(p, "rb").read(),
                           file_name=f"{t}_{NATIVE_FILE_LABEL.get(fid, fid)}.zip", mime="application/zip",
                           key=f"nw_dl_{fid}_{key}", on_click="ignore", icon=":material/folder_zip:",
                           type="secondary" if stale else "primary")
    nk, nr = NR.get("n_kept"), NR.get("n_removed")
    parts = []
    if nk is not None:
        parts.append(f"{int(nk):,} readings kept")
    if nr is not None:
        parts.append(f"{int(nr):,} removed (" + ("set to not harvesting, none deleted" if fid != nw.ISOXML else
                                                 "not written") + ")")
    if NR.get("n_not_offered"):
        parts.append(f"{int(NR['n_not_offered']):,} harvest records the decoder never offered as readings (also set "
                     "to not harvesting)")
    if NR.get("logs_written") is not None:
        parts.append(f"{NR['logs_written']} of {NR.get('logs_in_units')} logs written")
    parts.append(f"{int(NR.get('files_changed') or 0):,} files changed")
    if NR.get("card_names"):
        parts.append("card folder " + ", ".join(NR["card_names"]))
    GL = NR.get("grain_lb") or {}
    if GL.get("kept_x_factor") is not None and GL.get("written") is not None:
        parts.append(f"grain kept x factor {GL['kept_x_factor']:,.0f} lb, written {GL['written']:,.0f} lb")
    st.caption("; ".join(parts) + ".")
    CK = NR.get("check") or {}
    if CK.get("ok") is False:
        st.error("The writer's own check: " + str(CK.get("line") or "") + (": " + "; ".join(CK["problems"][:5])
                                                                         if CK.get("problems") else ""),
                 icon=":material/error:")
    elif CK.get("line"):
        st.caption("The writer's own check (" + ("read back with the writer's own reader" if fid == nw.ISOXML else
                                                 "decoded back with OCED's decoder") + "): " + str(CK["line"]) + ".")
    BM = NR.get("below_min") or {}
    if BM.get("n"):
        st.caption(f"{int(BM['n']):,} of the readings written fall below the minimum yield"
                   + (f" ({float(BM['min_yield']):g} bu/ac dry)" if BM.get("min_yield") is not None else "")
                   + (" once the factors of step 3 are applied" if (NR.get("options") or {}).get("factors") else "")
                   + (" (written with the logged widths: a narrowed reading reads its logged, lower yield)"
                      if (NR.get("options") or {}).get("widths") is False else "")
                   + (": SMS leaves them out, so its points should count that many fewer than the readings in the "
                      "totals below (which count them)." if BM.get("in_totals") else
                      ": SMS leaves them out, so 'what SMS should show' counts that many readings fewer than were "
                      "written."))
    if NR.get("totals"):
        st.dataframe(pd.DataFrame(NR["totals"]), hide_index=True,
                     column_config={c: st.column_config.NumberColumn(format=f)
                                    for c, f in (("area (ac)", "%.2f"), ("wet (lb)", "%.0f"), ("dry (bu)", "%.1f"),
                                                 ("dry yield (bu/ac)", "%.2f"), ("moisture (%)", "%.2f"),
                                                 ("readings", "%d"))})
    if NR.get("index_csv"):
        st.caption("Index of the readings written (one row per reading, its record in the set): "
                   + (NR["index_csv"] if os.path.isabs(NR["index_csv"]) else os.path.join(ss.workdir, NR["index_csv"])))
    if NR.get("machines"):
        st.caption("Sections per combine: " + "; ".join(
            f"{m.get('machine')}: {m.get('sections')} x {float(m.get('section_mm') or 0) / 1000:.3f} m"
            for m in NR["machines"]))
    for w in NR.get("warnings") or []:
        st.warning(w, icon=":material/warning:")
    if NR.get("notes"):
        with st.expander(f"What the writer did ({len(NR['notes'])} notes)", icon=":material/notes:", type="compact"):
            for n in NR["notes"]:
                st.caption(str(n))


def native_block(t: str, C: dict):
    """Step 4, one clean harvest file: the clean data in the same raw format as imported (the monitor's own writer
    of its source), ISOXML TASKDATA as the fallback (the only option besides the shapefile for a point export), each
    option from engine/formats/native_write.py options(); an option that cannot be written is shown disabled with
    the reason. Writes run with the log, into native/<tag>/, and their result stays on the page."""
    D = ss.datasets.get(t)
    if not D or C.get("kind") == "a3" or not C.get("shp") or not os.path.exists(C["shp"]):
        return
    src = writer_source(D)
    try:
        opts = nw.options(src, isoxml_fallback=src is not None)
    except Exception as e:                               # a writer that cannot even list itself: said, never fatal
        st.warning(f"The formats of the monitor cannot be listed ({type(e).__name__}: {e}).", icon=":material/warning:")
        return
    key = file_key(t)
    native = [o for o in opts if o.get("native")]
    title = ("Same raw format as imported: " + native[0]["label"] if native else
             "Monitor format: ISOXML TASKDATA (this file is a point export, not raw monitor data)")
    NRs = native_results(t, C)
    how = [NATIVE_HOW[o["id"]] for o in opts if o.get("available") and NATIVE_HOW.get(o["id"])]
    with st.container(border=True, key=f"nw_box_{key}"):
        st.markdown(f"**Save the clean file as** · {html.escape(title)}",
                    help=(how[0] if how else "The clean readings in the raw format they were imported from, to read "
                                             "into SMS as monitor data.") + " More: How to read it into SMS, below.")
        st.caption(":orange[Not yet tested in SMS]", help=NATIVE_CAVEAT)
        fac, fac_txt = native_factors(C)
        with st.container(horizontal=True, vertical_alignment="bottom"):
            widths = st.checkbox("Write the clean swath widths (after Optimize Swath Widths)", value=True,
                                 key=f"nw_w_{key}",
                                 help="On: each kept reading carries the width (and distance) the cleaning left it, so "
                                      "its yield is the clean one. Off: the widths as logged (the narrowed readings "
                                      "then read their logged, lower yield).")
            # keyed by the cleaning it belongs to (the clean file's time and the factors): each new cleaning starts
            # from the default (on whenever step 3 applied something) instead of a state kept from an earlier one
            fkey = key_of(f"{mtime(C['shp'])}|{json.dumps(fac, sort_keys=True, default=str)}")
            apply = st.checkbox("Apply the factors of step 3 to the written grain", value=fac is not None,
                                key=f"nw_f_{key}_{fkey}", disabled=fac is None,
                                help=("The clean yields of this file contain " + fac_txt + ": on, the grain of each "
                                      "combine is multiplied so that the written file reads as the column to map. Off: "
                                      "the monitor's grain as logged.") if fac is not None else
                                     "Nothing was applied in step 3 (no combine factor, the grower's data not used to "
                                     "adjust): the monitor's grain is written.")
            new_ids = st.checkbox("New file ids", value=True, key=f"nw_id_{key}",
                                  help="New card folder names / file ids, so that SMS does not take the written data for "
                                       "the original it has archived. Off only to compare with the original byte for "
                                       "byte.")
        adv = {}
        fmts = {o["id"] for o in opts if o.get("available")}
        if fmts & {"cnh_cn1", nw.ISOXML, "jd_jdl"} and st.toggle("Advanced options of the writers",
                                                                  key=f"nw_adv_{key}"):
            with st.container(border=True):
                if "cnh_cn1" in fmts:
                    adv["cnh_cn1"] = {
                        "mode": st.radio("Case IH card: the removed readings", ["header_up", "drop"], horizontal=True,
                                         key=f"nw_cm_{key}", format_func={
                                             "header_up": "header up (their logging bit cleared, nothing deleted)",
                                             "drop": "taken out (record counter gaps: not proven in SMS)"}.get),
                        "totals": st.radio("Case IH card: the totals of the SMS Summary", ["points", "scaled", "original"],
                                           horizontal=True, key=f"nw_ct_{key}", format_func={
                                               "points": "the kept readings (the Summary = the clean points)",
                                               "scaled": "the display's totals in proportion",
                                               "original": "the display's totals as they are"}.get)}
                if nw.ISOXML in fmts:
                    adv[nw.ISOXML] = {
                        "lead_in": st.radio("ISOXML: lead-in records", ["gaps", "always"], horizontal=True,
                                            key=f"nw_li_{key}", format_func={
                                                "gaps": "only where a reading does not follow the previous one",
                                                "always": "before every reading (exact area; each duration from the "
                                                          "previous record)"}.get),
                        "max_sections": int(st.number_input("ISOXML: sections per header (most)", 16, 64, 64, 1,
                                                            key=f"nw_ms_{key}"))}
                if "jd_jdl" in fmts:
                    adv["jd_jdl"] = {"drop_logs": st.checkbox(
                        "Gen4: leave out the logs with no kept reading", value=False, key=f"nw_dl_{key}",
                        help="OCED re-reads the card with another local projection origin: distances and per-area "
                             "values then differ very slightly from the full card (the notes of the write say how "
                             "much).")}
        ref = ss.get(f"nw_ref_{key}")
        with st.container(horizontal=True):
            clicks = {}
            for o in opts:
                lab = ("Write the " + o["label"] if o.get("native") else
                       f"Write {o['label']} (experimental)")
                clicks[o["id"]] = st.button(lab, key=f"nw_go_{o['id']}_{key}", disabled=not o.get("available"),
                                            type="primary" if (o.get("native") and o.get("available")) else "secondary",
                                            icon=":material/save:")
        native_ok = any(o.get("native") and o.get("available") for o in opts)
        avail = [o for o in opts if o.get("available")]
        named = False                                    # a line names the SMS settings of a writer
        timing_only = False                              # a line says only that the grain timing differs
        for o in avail:                                  # how SMS reads it with the clean file's yields
            RD = native_read_settings(t, C, o["id"])
            if RD:
                st.caption((f"{o['label']}: " if len(avail) > 1 else "") + RD["text"])
                named = named or "read it into SMS with" in RD["text"]
                timing_only = timing_only or (bool(RD.get("timing")) and "read it into SMS with" not in RD["text"])
        for o in opts:
            if not o.get("available") and o.get("reason"):
                # why it cannot be written, in sight (its button above is disabled)
                st.caption(f"{o['label']}: not available - {o['reason']}.")
        go = next((fid for fid, c in clicks.items() if c), None)
        shift = False
        if ref and ref.get("fid") and not go:
            st.warning(ref["msg"], icon=":material/warning:")
            if st.button(f"Write anyway: {ref['n']:,} kept readings of {ref['k']} log(s) are placed {ref['x']:.3f} m "
                         "sideways (the strip they cover, their width, area, grain and moisture are unchanged)",
                         key=f"nw_shift_{key}", icon=":material/warning:"):
                go, shift = ref["fid"], True
        if go:
            ss.pop(f"nw_ref_{key}", None)
            o = next(x for x in opts if x["id"] == go)
            run_opts = {"widths": bool(widths), "apply": bool(apply), "new_ids": bool(new_ids),
                        "advanced": {**adv.get(go, {}), **({"allow_reference_shift": True} if shift else {})}}
            with st.status(f"Writing the {o['label']} and checking it (seconds; a few minutes for a large set of Gen4 "
                           "logs) ...", expanded=True) as status:
                state = {"exc": None}
                lg = guarded_log(status.text, state)
                try:
                    rec = write_native(t, C, go, run_opts, log=lg)
                    status.update(label=f"{o['label']}: {int(rec.get('n_kept') or 0):,} readings written"
                                        + ("" if (rec.get("check") or {}).get("ok") is not False else
                                           " - the check found differences"),
                                  state="complete" if (rec.get("check") or {}).get("ok") is not False else "error",
                                  expanded=False)
                except ValueError as e:
                    logs = getattr(e, "logs", None)
                    if logs and type(e).__name__ == "JdlReferenceError":
                        # the writer names its option; on this page it is the 'Write anyway' button below
                        msg = re.sub(r"Write it anyway with allow_reference_shift=True",
                                     "Use the 'Write anyway' button below to write them", str(e))
                        ss[f"nw_ref_{key}"] = {"fid": go, "msg": msg,
                                               "n": int(sum(int(x.get("kept_readings") or 0) for x in logs)),
                                               "k": len(logs), "x": float(max(abs(float(x.get("move_m") or 0))
                                                                              for x in logs))}
                        status.update(label=f"{o['label']}: not written (see below)", state="error", expanded=False)
                    else:
                        status.update(label=f"{o['label']}: not written", state="error", expanded=False)
                        st.error(str(e), icon=":material/error:")
                except Exception as e:                   # shown, never swallowed
                    status.update(label=f"{o['label']}: the write failed", state="error", expanded=False)
                    st.exception(e)
            if state.get("exc") is not None:             # the page asked for a new run while writing: now
                raise state["exc"]
            if ss.get(f"nw_ref_{key}"):
                st.rerun()
            NRs = native_results(t, C)
        with st.expander("How to read it into SMS", type="compact"):
            for o in opts:                                   # what each format that can be written holds
                if o.get("available") and o.get("reason"):
                    st.caption(f"{o['label']}: {o['reason']}.")
            st.caption(" ".join(how + [NATIVE_SETTINGS_NAMED if named else
                                       NATIVE_SETTINGS_TIMING if timing_only else NATIVE_SETTINGS]))
        for fid in [o["id"] for o in opts] + [f for f in NRs if f not in {o["id"] for o in opts}]:
            if fid in NRs:
                st.divider()
                _native_result_view(t, fid, NRs[fid], key)


# ------------------------------------------------------------------------------------------------ steps 1 and 2: views
# Step 1 shows a file's default import (default_view: what SMS's import gives it, its Processing Settings untouched),
# step 2 its import settings and, once own values are applied, the import in use (active_view) beside step 1's.
_DEFAULTS_FAMILY = {"jd_gs3_rcd": "gs3", "jd_jdl": "jdl", "isoxml": "isoxml", "cnh_cn1": "cnh",
                    si.POINT_EXPORT: "point", si.OPS_CENTER: "point"}
_DEFAULTS_TAIL = "no expand, manual swath or moisture, no delays."


def sms_defaults_text(family: str | None = None) -> str:
    """What SMS's import gives a source with its Processing Settings untouched (each file's default import, step 1).
    family: one source ('gs3', 'jdl', 'isoxml', 'cnh', 'point', or a format id such as jd_gs3_rcd or point_export):
    one sentence; None: every source, with SMS's product tables (the sidebar)."""
    f = _DEFAULTS_FAMILY.get(str(family), family)
    one = {"gs3": "GreenStar 3 card: the card crop's weight and dry moisture, 5.000-10,000.00 bu/ac, " + _DEFAULTS_TAIL,
           "jdl": "Gen4 logs: SMS's weight and dry moisture for the file's crop, 5.000-10,000.00 bu/ac, "
                  + _DEFAULTS_TAIL,
           "isoxml": "ISOXML task data: SMS's weight and dry moisture for the task's crop, 5.000-10,000.00 bu/ac, "
                     + _DEFAULTS_TAIL,
           "cnh": "Case IH / New Holland card: SMS's product table by the crop name (weight, dry moisture, limits), "
                  + _DEFAULTS_TAIL,
           "point": "Point export: SMS's generic import, every reading kept (min 0, no max), the product table's "
                    "weight and dry moisture, " + _DEFAULTS_TAIL}
    if f is not None:
        return one.get(f, "")
    prod_txt = "; ".join(f"{p} {v[0]:g} lb/bu, {v[1]:g} %, {v[2]:g}-{v[3]:,.0f}" for p, v in si.SMS_PRODUCTS.items()
                         if p != "Barley - Spring")
    jd_txt = "; ".join(f"{k} {v[1]:g} lb/bu, {v[2]:g} %" for k, v in common.JD_SMS_CROPS.items())
    iso_txt = "; ".join(f"{k} {v[0]:g} lb/bu, {v[1]:g} %" for k, v in iso_crops().items())
    return "\n\n".join([
        "**GreenStar 3 cards:** the weight to volume and dry moisture of the card's own crop definition; min 5.000 "
        "and max 10,000.00 bu/ac.",
        f"**Gen4 .jdl logs:** what SMS gives the file's crop ({jd_txt}; another crop: SMS's product table), not the "
        "values the file states; min 5.000 and max 10,000.00 bu/ac (set the max in step 2 if SMS holds another for "
        "the product).",
        f"**ISOXML task data:** what SMS gives the task's crop ({iso_txt}; another crop OCED knows: SMS's product "
        "table), not the density and reference moisture of the log; a crop code OCED does not know: the log's own "
        "density and reference moisture ('from the file', with a warning to check the product); no crop and no "
        "density: 56 lb/bu, 13 %, SMS's values for a dataset without a product. Min 5.000 and max 10,000.00 bu/ac.",
        f"**Case IH / New Holland cards:** SMS's product table by the crop name ({prod_txt} bu/ac; another crop: the "
        "crop table, 5-300); a unit whose crop has no weight on the card: 56 lb/bu, 13 %, with a warning (choose the "
        "product in step 2).",
        "**Point exports** (a shapefile, a KML / KMZ, an Operations Center or SMS export): as SMS's generic import of "
        "a point file holds them, every reading kept (min 0, no max), with the weight to volume and dry moisture of "
        "SMS's product table by the crop name; a crop OCED cannot name keeps the file's own yields. Readings logged "
        "with a swath width of 0 stay in the import and are removed by S2 of the cleaning.",
        "**Everywhere:** expand dry moisture off, no manual swath or moisture, delays and flow shift 0. Step 2 "
        "changes any of them per file and says where every value came from."])


SWITCH_HELP = "On: as SMS imports it (step 1). Off: your own values, then Apply. "
# decoding options of step 1 that are not SMS's ((decoder keyword, value, how the badge line names it))
NON_SMS_DECODING = (("calibration", "latest", "crop's latest calibration"), ("time_basis", "period",
                                                                              "one logging period"),
                    ("alignment", "shift", "fixed time shift"), ("points", "ops_center", "one point per flow sample"),
                    ("time_logs", "joined", "joined time logs"))


def decoding_not_sms(source: dict | None, report: dict | None = None) -> list:
    """The decoding options of a raw file that are not SMS's (Decoding options, step 1): ['crop's latest
    calibration', ...]; [] for SMS's choices or a point export."""
    kw = None
    for x in (source, report):
        if isinstance(x, dict) and isinstance(x.get("decoder_kwargs"), dict):
            kw = x["decoder_kwargs"]
            break
    return [txt for k, v, txt in NON_SMS_DECODING if kw and str(kw.get(k)) == v]


def import_values_text(RS: dict) -> str:
    """'wheat · 60.00 lb/bu · 13.50 % · 5.000-300.00 bu/ac': the product, weight to volume, dry moisture and yield
    volume limits of a resolved import."""
    parts = [str(RS.get("product") or "product not known")]
    if RS.get("test_weight_lb_bu"):
        parts.append(f"{float(RS['test_weight_lb_bu']):,.2f} lb/bu")
    if RS.get("dry_moisture_pct") is not None:
        parts.append(f"{float(RS['dry_moisture_pct']):.2f} %")
    mn, mx = RS.get("min_yield"), RS.get("max_yield")
    mn = None if mn in (None, si.AUTO) else float(mn)
    mx = None if mx is None else float(mx)
    parts.append(f"{mn:,.3f}-{mx:,.2f} bu/ac" if mn is not None and mx is not None else
                 f"min {mn:,.3f} bu/ac, no maximum" if mn is not None else
                 f"no minimum, max {mx:,.2f} bu/ac" if mx is not None else "no minimum or maximum")
    return " · ".join(parts)


def badge_line(kind: str, text: str, help: str | None = None):
    """One line with the badge of an import before it (brand.import_badge) and its "?"."""
    st.markdown(f"{brand.import_badge(kind)} {html.escape(str(text))}", unsafe_allow_html=True, help=help or None)


def active_view(D: dict) -> dict:
    """The import in use of a file (step 2, steps 3 and 4 read it), in the form of default_view."""
    out = {k: D.get(k) for k in ("shp", "n", "sms_import", "report", "op", "yield", "area_ac", "zip", "source", "kind",
                                 "label", "import_min")}
    out.update({"error": None, "older": None, "is_default": False})
    return out


def step1_badge(V: dict, D: dict, tag: str | None = None) -> tuple:
    """(kind, text, help) of step 1's import line for the view V of the file D (tag: its name, for the reason a build
    of its default import failed in this session)."""
    IM = V.get("sms_import") or {}
    if not V.get("yield", True):
        return ("as_is", "not a yield file", "SMS imports harvest data with Processing Settings; a planter or "
                "sprayer file is used as written.")
    if V.get("error"):
        return "failed", "the readings as the file gives them", f"{V['error']}. Step 2 can try the import again."
    if basis_pending(D):
        # a file of an earlier version whose data's crop could not be read yet: its import as saved, nothing told
        txt = (import_values_text(IM["resolved"]) if isinstance(IM.get("resolved"), dict) else
               "the export as written")
        return ("older", txt, "Imported by an earlier version of OCED, kept as it is: "
                + basis_pending_note_of(D) + ".")
    # the import in use stands in for SMS's default: why (the build failed in this session, or its readings are gone)
    why_f = default_failed_reason(tag) if tag else None
    gone = ("The import in use (step 2): SMS's default import of this file could not be made "
            f"({why_f}); an action in step 2 or opening the work again tries it again." if why_f else
            "The import in use (step 2): SMS's default import of this file cannot be made again, its readings are no "
            "longer on disk.")
    if not isinstance(IM.get("resolved"), dict):
        if V.get("is_default") or import_basis(D) is None:
            return "older", "no record of the import", "Open the data again for SMS's default import."
        if D.get("kind") == "raw":
            return "as_logged", "the monitor's own weight and moisture", gone
        return "as_is", "the export as written", gone
    txt = import_values_text(IM["resolved"])
    if not V.get("is_default") and import_mode(D) == "custom":
        return "custom", txt, gone
    if V.get("older_decode"):
        # named by the decode its yields come from (the product the readings carry), not 'product not known'
        return "older", older_decode_text(V, IM["resolved"]), older_decode_help(D, V)
    if V.get("older"):
        return ("older", txt, f"Imported by an older OCED rule: {'; '.join(V['older'])}. Step 2 imports it with "
                "today's rule.")
    hlp = ("Imported as Ag Leader SMS imports this kind of file, its Processing Settings untouched. Step 2 can change "
           "them. The record is under Import details.")
    dec = decoding_not_sms(V.get("source"), V.get("report"))
    if dec:
        txt += " · decoded with: " + ", ".join(dec)
        hlp += " This decoding option is not SMS's: Decoding options, step 1."
    return "default", txt, hlp


def located_in(df: pd.DataFrame) -> int:
    """The readings of a point table with a plausible position (finite lon and lat)."""
    if not len(df):
        return 0
    return int((np.isfinite(pd.to_numeric(df["lon"], errors="coerce"))
                & np.isfinite(pd.to_numeric(df["lat"], errors="coerce"))).sum())


def view_numbers(V: dict) -> dict:
    """The numbers of the strip of a view: {df, det, op, n, located, area, mean, avg, ycol}."""
    shp = V.get("shp")
    df = read_points(shp, mtime(shp))
    det = yc.detect_columns([c for c in df.columns if c not in ("lon", "lat")])
    out = {"df": df, "det": det, "n": len(df), "op": operation_of(shp, mtime(shp)), "ycol": det.get("yield"),
           "mean": None, "avg": None}
    out["located"] = located_in(df)
    a0 = area_of(df)
    out["area"] = float(a0[np.isfinite(a0) & (a0 > 0)].sum()) if a0 is not None else 0.0
    if V.get("yield", True) and det.get("yield"):
        yv = pd.to_numeric(df[det["yield"]], errors="coerce")
        if yv.notna().any():
            out["mean"] = float(yv.mean())
            out["avg"] = avg_of(df, det["yield"])
    return out


def _import_record_view(V: dict) -> dict:
    """The import record of a view ({} without one; a work saved with the first import: its minimum only)."""
    IM = V.get("sms_import") or {}
    if not IM and V.get("import_min"):
        o = V["import_min"]
        IM = {"left_out": ({"below the min. yield volume": int(o.get("left_out") or 0)} if o.get("left_out") else {}),
              "n_all": o.get("n_all"), "settings": f"min. yield volume {float(o.get('min_yield') or 0):g} bu/ac"}
    return IM


def readings_help(V: dict, n: int) -> str:
    """The "?" of the Readings card (the rest of the record is under Import details)."""
    IM = _import_record_view(V)
    if not IM:
        return ("SMS's import of this file failed: the readings as the file gives them." if V.get("error") else
                "Not imported as SMS: the readings as the file gives them.")
    lo = IM.get("left_out") or {}
    h = (f"{n:,} of {int(IM.get('n_all') or n):,} readings; "
         + ("left out: " + ", ".join(f"{k} {int(v):,}" for k, v in lo.items()) if lo else "none left out")
         + (f"; recomputed: {', '.join(IM['changed'])}" if IM.get("changed") else "") + ".")
    notes = " ".join(str(x) for x in (IM.get("notes") or []))
    if notes and len(h) + len(notes) < 300:
        return h + " " + notes
    return h + " The rest is under Import details."


def data_strip(V: dict, key: str, compare: dict | None = None) -> dict:
    """The strip of cards of a view (step 1: every card; step 2, compare = step 1's view: readings, area, mean and
    average, each with its difference to step 1). Returns view_numbers(V)."""
    N = view_numbers(V)
    df, det, OPX = N["df"], N["det"], N["op"]
    IM = _import_record_view(V)
    harvest = bool(V.get("yield", True))
    card_sum = bool((V.get("report") or {}).get("sms_summary"))
    avg_label = "Average dry yield of the readings" if card_sum else "Average dry yield (SMS)"
    avg_help = ("The area-weighted average of the readings (each reading's yield x its area, added up, divided by "
                "the area). SMS's Summary of a Case IH card is the display's own totals: the SMS Summary line."
                if card_sum else "As the SMS summary: the area-weighted average, the total divided by the area.")
    if compare is not None:
        C = view_numbers(compare)

        def d(a, b, fmt, unit=""):
            if a is None or b is None:
                return None
            x = a - b
            return ("0" if abs(x) < 0.005 else f"{x:+,{fmt}}") + (f" {unit}" if unit else "")
        cards = [{"label": "Readings", "value": f"{N['n']:,}", "delta": d(N["n"], C["n"], "d"),
                  "delta_description": "vs step 1", "help": readings_help(V, N["n"])},
                 {"label": "Area harvested", "value": f"{N['area']:,.2f} ac", "delta": d(N["area"], C["area"], ".2f",
                                                                                         "ac"),
                  "delta_description": "vs step 1", "help": "The strips the readings swept (distance x width), "
                                                            "added up."} if N["area"] > 0 else None]
        if N["mean"] is not None:
            cards.append({"label": "Mean dry yield", "value": f"{N['mean']:,.2f} bu/ac",
                          "delta": d(N["mean"], C["mean"], ".2f", "bu/ac"), "delta_description": "vs step 1",
                          "help": "The plain mean of the readings (as SMS Edit Legend)."})
        if N["avg"] is not None:
            cards.append({"label": avg_label, "value": f"{N['avg']:,.2f} bu/ac",
                          "delta": d(N["avg"], C["avg"], ".2f", "bu/ac"), "delta_description": "vs step 1",
                          "help": avg_help})
        card_row(cards, key)
        return N
    op_lab = a3.OPERATION_LABEL.get(V.get("op") or "harvest", "Point data")
    n_left = sum(int(v) for v in (IM.get("left_out") or {}).values())
    cards = [{"label": "Operation", "value": op_lab.split(" (")[0], "help": op_lab},
             {"label": "Readings", "value": f"{N['n']:,}", "delta": f"{n_left:,} left out at import" if n_left else None,
              "help": readings_help(V, N["n"])}]
    if N["area"] > 0:
        cards.append({"label": "Area harvested" if harvest else "Area covered", "value": f"{N['area']:,.2f} ac",
                      "help": "The strips the readings swept (distance x width), added up."
                              + (f" Every decoded reading, before the import as SMS: {float(V['area_ac']):,.2f} ac."
                                 if V.get("area_ac") and abs(float(V["area_ac"]) - N["area"]) > 0.005 else "")})
    if harvest:
        if N["mean"] is not None:
            cards.append({"label": "Mean dry yield", "value": f"{N['mean']:,.2f} bu/ac",
                          "help": "The plain mean of the readings (as SMS Edit Legend)."})
        if N["avg"] is not None:
            cards.append({"label": avg_label, "value": f"{N['avg']:,.2f} bu/ac", "help": avg_help})
    elif OPX["rates"]:
        r0 = OPX["rates"][0]
        rv = pd.to_numeric(df[r0], errors="coerce")
        u0 = OPX["units"].get(r0, "")
        if rv.notna().any():
            cards.append({"label": "Mean applied rate", "value": f"{rv.mean():,.2f} {u0}".strip(),
                          "help": f"{r0}, every reading: the plain mean (as SMS Edit Legend)."})
            ra = avg_of(df, r0) if per_area(u0) else None
            if ra is not None:
                cards.append({"label": "Average applied rate (SMS)", "value": f"{ra:,.2f} {u0}".strip(),
                              "help": "As the SMS summary: area-weighted, the total divided by the area."})
    tcol = det.get("time")
    tt = pd.to_datetime(df[tcol], errors="coerce") if tcol else None
    if tt is not None and tt.notna().any():
        cards.append({"label": "Date", "value": f"{tt.min():%d %b %Y}" + (
            f" – {tt.max():%d %b}" if tt.max().date() != tt.min().date() else ""),
            "help": "The first and the last reading."})
    mcol = det.get("machine")
    if mcol:
        cards.append({"label": "Machines", "value": f"{df[mcol].astype(str).replace('', np.nan).nunique():,}",
                      "help": f"The machines the readings name ({mcol})."})
    card_row(cards, key)
    return N


def sms_summary_line(rep: dict | None, IM: dict | None):
    """A Case IH card: the display's own totals (its SMS Summary) in one line, the rest in its "?"."""
    SS_T, _, SS_how = sms_summary_view(rep, IM)
    if not SS_T.get("area_ac"):
        return
    parts = [f"{SS_T['area_ac']:,.2f} ac"]
    if SS_T.get("bu_ac") is not None:
        parts += [f"{SS_T['dry_bu']:,.1f} bu dry", f"{SS_T['bu_ac']:,.2f} bu/ac"]
    elif SS_T.get("wet_lb") is not None:
        parts.append(f"{SS_T['wet_lb']:,.0f} lb wet")
    more = [x for x in (f"{SS_T['wet_lb']:,.0f} lb wet" if SS_T.get("wet_lb") is not None and
                        SS_T.get("bu_ac") is not None else "",
                        f"moisture {SS_T['moisture_pct']:.2f} %" if SS_T.get("moisture_pct") is not None else "") if x]
    st.caption("SMS Summary (the display's totals): " + " · ".join(parts),
               help="The display's own totals on the card, not the sum of the readings"
                    + (f" ({', '.join(more)})" if more else "") + f"; {SS_how}. Each dataset under What the decoder "
                    "reported.")


def import_details_box(V: dict):
    """Step 1's 'Import details': the record of the import (readings in and left out, what was recomputed, the
    settings and where each value came from, the notes) and how a point export is imported."""
    IM = _import_record_view(V)
    with st.expander("Import details", type="compact"):
        if V.get("error"):
            st.caption(f"SMS's import of this file failed ({V['error']}): its readings are shown as the file gives "
                       "them. Step 2 can try the import again.")
        if IM:
            lo = IM.get("left_out") or {}
            st.markdown(f"**{int(IM.get('n_in') or V.get('n') or 0):,} of {int(IM.get('n_all') or 0):,} readings "
                        "imported**" + ("; left out: " + ", ".join(f"{k} {int(v):,}" for k, v in lo.items()) if lo
                                        else "; none left out"))
            st.caption((f"Recomputed: {', '.join(IM['changed'])} (the dry yield computed again from the wet mass)."
                        if IM.get("changed") else
                        "Imported with no column recomputed: its product is not known, so the file's own yields are "
                        "used (choosing the product in step 2 converts them)." if own_point_yields(IM) else
                        "No column recomputed.")
                       + (f" Settings: {IM['settings']}." if IM.get("settings") else ""))
            if IM.get("sources"):
                st.caption("Where the values came from: " + sources_line(IM) + ".")
            for n_ in IM.get("notes") or []:
                st.caption(str(n_))
            if V.get("kind") == "export":
                st.caption(("Imported as SMS's generic import of a point file holds it: every reading kept, unless a "
                            "yield volume limit is set in step 2." if IM.get("family") == "point" else
                            "Imported as SMS imports it.") + " Its attributes are the vendor's columns.")
        elif not V.get("error"):
            st.caption("A point export is used as it is: its attributes are the vendor's columns."
                       + ("" if V.get("yield", True) else " Not a yield file: it is cleaned with the 3-sigma of the "
                          "attributes you choose (the applied rate, the speed ...).") if V.get("kind") == "export" else
                       "Not imported as SMS: the data as it is.")


def decoder_report_box(V: dict, D: dict):
    """Step 1's 'What the decoder reported' (raw data): units, points, machines, the SMS Summary of each dataset,
    what was not exported as readings, the alignment, the section layouts and the decoder's warnings."""
    rep = V.get("report")
    if not rep:
        return
    _, SS_D, SS_how = sms_summary_view(rep, V.get("sms_import"))
    with st.expander("What the decoder reported", type="compact"):
        st.caption("Units: " + "; ".join(D.get("units") or []))
        if rep.get("points"):
            st.caption("Points: " + {"sms": "as SMS Advanced reads the .jdl",
                                     "ops_center": "one per flow sample, as Operations Center"}.get(
                str(rep["points"]), str(rep["points"])) + ".")
        if rep.get("machines"):
            st.dataframe(pd.DataFrame(rep["machines"]), hide_index=True)
        if SS_D is not None:
            st.caption("SMS Summary of each dataset: " + str(rep["sms_summary"].get("what") or "")
                       + f" Dry volume and yield {SS_how}.")
            st.dataframe(SS_D, hide_index=True,
                         column_config={c: st.column_config.NumberColumn(
                             "readings decoded (before the import's min / max)", format="%d")
                             for c in ("decoded_readings", "readings")})
            st.caption("The SMS GPS count is the readings left after the import (the Readings card).")
        if rep.get("pre_step"):
            st.dataframe(pd.DataFrame([{"not exported as readings": PRE_STEP_LABEL.get(str(k), str(k)),
                                        "records": v} for k, v in rep["pre_step"].items()]), hide_index=True)
        if rep.get("sessions_left_out"):
            st.caption(f"{int(rep['sessions_left_out']):,} GreenStar 3 session(s) found twice in the input were read "
                       "once (the copies left out).")
        al = rep.get("alignment")
        if isinstance(al, dict) and al:
            st.caption("Grain and moisture of the readings (" + str(al.get("method") or "") + "): "
                       + ", ".join(f"{k.replace('_', ' ')} {v:,.0f}" if isinstance(v, (int, float)) else
                                   f"{k.replace('_', ' ')} {v}" for k, v in al.items() if k != "method") + ".")
        for i, dd in enumerate(rep.get("details") or []):
            lays = (dd or {}).get("layouts") if isinstance(dd, dict) else None
            if isinstance(lays, list) and len(lays) > 1:
                st.caption(f"{dd.get('unit') or dd.get('machine') or f'Unit {i + 1}'}: {len(lays)} section layouts "
                           "in its logs (each reading takes the layout of its own log file)")
                st.dataframe(pd.DataFrame(lays), hide_index=True)
        for w in rep.get("warnings") or []:
            st.warning(w, icon=":material/warning:")


def extracted_units(root: str) -> dict:
    """{unit id: tag} of the raw files of this work extracted from the input at root (step 1 marks them)."""
    r = os.path.normcase(os.path.abspath(str(root)))
    out = {}
    for t, D in (ss.datasets or {}).items():
        if D.get("kind") != "raw":
            continue
        ir = ew.input_root(D, ss.workdir)
        if not ir or os.path.normcase(os.path.abspath(ir)) != r:
            continue
        for u in (D.get("source") or {}).get("unit_ids") or []:
            out[str(u)] = t
    return out


def _pick_file():
    """The File picker of step 1: that file in steps 1 to 4."""
    ss.active = ss.get("active_pick")


def _keep_settings(TKi: str, TKm: str | None = None):
    """'Keep my settings' (or the dialog closed): the switch of step 2 off, the file unchanged, the dialog closed."""
    ss[f"fi_def_{TKi}"] = False
    if TKm:
        ss.pop(f"fi_ask_{TKm}", None)


def _switch_changed(tag: str, TKm: str, TKi: str):
    """The switch of step 2 turned on over a file with own settings and a cleaning: the switch stays off (the data on
    screen is still the file's own import) and the dialog asks first."""
    D = ss.datasets.get(tag) or {}
    if ss.get(f"fi_def_{TKi}") and import_mode(D) != "default" and has_cleaning(tag):
        ss[f"fi_def_{TKi}"] = False
        ss[f"fi_ask_{TKm}"] = True


def _back_go(tag: str, TKm: str):
    """'Back to SMS's default' in the dialog of step 2 (a callback: a pointer swap and deletes)."""
    ss.pop(f"fi_ask_{TKm}", None)
    w = []
    try:
        ss[f"fi_msg_{TKm}"] = back_to_default(tag, warns=w)
    except ValueError as e:
        ss[f"fi_err_{TKm}"] = str(e)
    if w:
        ss[f"fi_warn_{TKm}"] = w


def _ask_back_to_default(tag: str, TKm: str, TKi: str):
    """The switch turned back on over a file with a cleaning: ask first (the cleaning is set aside)."""
    @st.dialog("Back to SMS's default?", on_dismiss=functools.partial(_keep_settings, TKi, TKm))
    def ask():
        st.markdown(f"The cleaning of {html.escape(tag)} is set aside (moved to superseded/) and the file goes back to "
                    "SMS's default.")
        with st.container(horizontal=True):
            if st.button("Back to SMS's default", key=f"fi_backgo_{TKm}", type="primary", icon=":material/undo:",
                         on_click=_back_go, args=(tag, TKm)):
                st.rerun()
            if st.button("Keep my settings", key=f"fi_backno_{TKm}", on_click=_keep_settings, args=(TKi, TKm)):
                st.rerun()
    ask()


def _start(key: str, v) -> dict:
    """A field of step 2 that may be empty: its starting value goes into the session state on its first draw (the
    product callback sets the weight, moisture and limits there too), and the widget's own default is always None,
    so that a field the user empties stays empty (the browser commits the widget's default for an emptied field; a
    default of None also keeps Streamlit from warning about a value set both ways)."""
    if key not in ss:
        ss[key] = v
    return {"value": None}


HOW_LABEL = {"sms": "As SMS", "none": "None: the file as it is", "none_raw": "None: as the monitor logged it"}
IMPORT_FIELDS = ("prod", "tw", "dm", "exp", "ums", "msw", "umm", "mm", "min", "max", "sd", "ed", "fs")   # fi_<x>_


def step3_min() -> float:
    """Step 3's own S0 minimum (bu/ac; the files not imported as SMS take it): the value on screen, else the one kept
    for the runs that do not draw it, else the saved settings' or SMS's."""
    P0 = ss.get("smsset") or {}
    m0 = P0.get("min_yield", sms.DEFAULTS["min_yield"])
    m = ss.get("min_yield", ss.get("min_yield_v", 0.0 if m0 is None else m0))
    return 0.0 if m is None else float(m)


def none_text(is_raw: bool) -> str:
    """The line of step 2's 'None' (the S0 minimum of an export as step 3 holds it now)."""
    if is_raw:
        return "The monitor's own weight and moisture and its dry-yield convention: the file is decoded again."
    m = step3_min()
    return ("The export as written: nothing left out or recomputed. Step 3's S0 minimum then applies (now "
            + ("none" if m <= 0 else f"{m:,.3f} bu/ac") + "; set in step 3).")


def _located_count(shp: str | None) -> int:
    """The readings of a file with a plausible position (0 when it is not there)."""
    if not shp or not os.path.exists(str(shp)):
        return 0
    return located_in(read_points(shp, mtime(shp)))


def import_panel(tag: str, D: dict, V1: dict, outline=None) -> bool:
    """Step 2 of a file: the switch 'Use SMS's default settings' (on: the data is step 1's; off: the import
    settings, editable, with Apply; back on: back to the default, asked first when the file has a cleaning), the
    'Your settings' line, and the strip and map of the changed data on step 1's colour scale. Planter / sprayer files
    and files with no record of their import get one line and no switch. Returns True when values are typed and not
    applied (step 3 says so)."""
    if not D.get("yield", True):
        st.caption("Nothing to import: a planter or sprayer file is used as it is.",
                   help="SMS imports harvest data with its Processing Settings; a planter or sprayer file is used as "
                        "written, and step 3 cleans it with the 3-sigma of the attributes you choose.")
        return False
    B = import_basis(D)
    if B is None:
        st.caption("This file keeps no record of its import: open the data again (step 1) to change it.",
                   help="A folder of an earlier version rebuilt from its files, or a file imported with the first "
                        "import (the minimum only): opening its data again imports it with SMS's default.")
        return False
    if B.get("pending"):
        note_ = basis_pending_note(B)
        st.caption(":orange[The crop of this file's data could not be read yet: its import stays as it is]",
                   help=note_[0].upper() + note_[1:] + ". Its import settings can be changed once "
                        + ("it can be read." if B.get("why") else "its readings are back."))
        return False
    DF, mode = default_of(D), import_mode(D)
    err = DF.get("error")
    is_raw = D.get("kind") == "raw"
    IM = D.get("sms_import") or {}
    # the values shown: the active import's; with no import as SMS, the default's (SMS's default when it failed); an
    # import made under an older rule: the fields offer today's values, so that one Apply updates it
    V2s = step2_start(D)
    R0, IMv, RS, RP, SRCP = V2s["R0"], V2s["IMv"], V2s["RS"], V2s["RP"], V2s["SRCP"]
    mon_p, fmt_p, old_imp = V2s["monitor"], V2s["fmt"], V2s["old_imp"]
    TKm = file_key(tag)
    # the widgets are keyed by the import they show: every applied import (and another mode) gets new widgets that
    # start from the file's real state; while the user only edits, the keys stay
    TKi = key_of(f"{TKm}|{ss.workdir}|{mode}|{IM.get('settings')}|{D.get('n')}|{mtime(D['shp'])}")
    def_ready = bool(DF.get("shp")) and os.path.exists(str(DF.get("shp")))
    on = st.toggle("Use SMS's default settings", key=f"fi_def_{TKi}", value=(mode == "default"),
                   disabled=bool(err) or (mode != "default" and not def_ready),
                   on_change=_switch_changed, args=(tag, TKm, TKi),
                   help=SWITCH_HELP + sms_defaults_text(B.get("fmt")))
    if ss.get(f"fi_err_{TKm}"):
        st.error(ss.pop(f"fi_err_{TKm}"), icon=":material/error:")
    if ss.get(f"fi_msg_{TKm}"):
        st.success(ss.pop(f"fi_msg_{TKm}"), icon=":material/check_circle:")
    for w_ in ss.pop(f"fi_warn_{TKm}", None) or []:
        st.warning(w_, icon=":material/warning:")
    if ss.get(f"fi_ask_{TKm}"):
        if mode != "default" and has_cleaning(tag):
            _ask_back_to_default(tag, TKm, TKi)          # the switch stays off behind it: the import in use, as it is
        else:
            ss.pop(f"fi_ask_{TKm}", None)
    if on and mode != "default":
        if has_cleaning(tag):                            # (the switch set without its callback): asked first too
            if not ss.get(f"fi_ask_{TKm}"):
                _ask_back_to_default(tag, TKm, TKi)
            on = False
        else:
            try:
                with st.spinner("Back to SMS's default import ..."):
                    w_back = []
                    ss[f"fi_msg_{TKm}"] = back_to_default(tag, warns=w_back)
                    if w_back:
                        ss[f"fi_warn_{TKm}"] = w_back
            except ValueError as e:
                st.error(str(e), icon=":material/error:")
                on = False
            else:
                st.rerun()
    unknown = RS.get("test_weight_lb_bu") is None or RS.get("dry_moisture_pct") is None

    # a default made from the readings an older version decoded with a product (its raw data not at hand or not
    # decoded again): no Apply makes SMS's default of it; its raw data does
    dec_old = older_decode_help(D) if DF.get("older_decode") else ""

    def notices():
        older_txt = ("; ".join(DF["older"]) + "." if (DF.get("older") and mode == "default") else
                     old_imp[0].upper() + old_imp[1:] + "." if old_imp else "")
        if dec_old and not on and mode == "default":
            st.caption(":orange[Decoded by an older OCED]", help=dec_old)
        elif older_txt and not on:
            st.caption(":orange[Imported by an older OCED rule]",
                       help=older_txt + " Apply imports it with today's rule (the fields show today's values).")
        if unknown and own_point_yields(IMv):
            st.caption("Product not known: the file's own yields are used", help=OWN_YIELDS_TEXT)
        elif unknown:
            st.caption(":orange[Product not recognised]",
                       help="The yields are as the file gives them. Choose the product under Edit the settings to "
                            "convert them with its weight to volume and dry moisture.")
        if old_decode(D):
            st.caption(":orange[Extracted by an older OCED]",
                       help="This file was extracted by an older version of OCED: importing it again re-imports the "
                            "readings that version decoded. Open the raw data again (step 1) for the current decode.")
    if on:
        if _located_count(D["shp"]):
            st.caption("The data is as in step 1.")
        else:                                            # the page stops here: the way on is to change the import
            st.caption(":orange[The data is as in step 1, with no reading to clean: switch this off to change the "
                       "import (the min. yield volume or another value), then Apply.]")
        if dec_old:
            st.caption(":orange[Decoded by an older OCED]", help=dec_old)
        elif DF.get("older"):
            st.caption(":orange[Imported by an older OCED rule]",
                       help="; ".join(DF["older"]) + ". Switch off and Apply to import it with today's rule (the "
                                                     "fields show today's values).")
        notices()
        return False
    # a failed import in use is not a choice of 'None': the import to apply is 'As SMS' (Apply tries it again, nothing
    # is pending); an import of an older rule: Apply imports it with today's values (the fields show them)
    retry = failed_in_use(D)
    # (an older version's decode is not refreshed by an Apply: the same readings give the same import)
    older_rule = bool(DF.get("older")) and mode == "default" and not DF.get("older_decode")
    # own settings made from readings other than step 1's (an older version decoded them with a product; its raw data
    # was decoded again since for SMS's default) that give another import from step 1's readings (one that gives the
    # same import, reading for reading, already follows them: ensure_default, _rebase_own_import): Apply imports them
    # again from step 1's readings
    other_dec = (mode == "custom" and bool(IM.get("all_readings")) and isinstance(DF.get("report"), dict)
                 and _norm_p(ew.resolve_moved(IM["all_readings"], ss.workdir))
                 != _norm_p(ew.resolve_moved(B["all_readings"], ss.workdir)))
    refresh = bool(old_imp) or older_rule or other_dec
    # step 1 shows an older rule's import (D7): what Apply changes in it (own settings that keep an older rule's
    # value name only the user's values; the orange caption says the rest)
    older_ch = import_changes(RS, RP, IMPORT_KEYS_SHOWN) if older_rule else []
    if mode == "default" and DF.get("older_decode"):
        st.caption("Still the older version's readings (Older rule): change a value and Apply.")
    elif mode == "default" and not refresh:
        st.caption("Still SMS's default: change a value and Apply.")
    elif mode == "default":
        pass                                             # the older rule: its caption (notices) and the line under Edit
    elif mode == "custom":
        ch = own_changes(R0, IM)                         # the user's values only (not an older rule's)
        dec_w = older_decode_word(D) if not ch else None
        if not ch and (other_dec or dec_w):
            # (no value of the user's: the readings are what differs, its raw data at hand or not)
            badge_line("custom", OLDER_DECODE_WORD,
                       help="Nothing of yours differs from SMS's default: these readings were decoded by an older "
                            f"OCED with {dec_w or 'a product'}. The settings and where each value came from: Import "
                            "details, under the map.")
        else:
            badge_line("custom", (", ".join(ch[:3]) + (f" and {len(ch) - 3} more" if len(ch) > 3 else "")) if ch
                       else "your values",
                       help="Changed against SMS's default: " + ("; ".join(ch) if ch else "nothing") + ". The settings "
                            "and where each value came from: Import details, under the map.")
    elif retry:
        badge_line("failed", "the readings as the file gives them",
                   help=f"SMS's import of this file failed ({err}). Apply with 'As SMS' tries it again.")
    elif is_raw:
        badge_line("as_logged", "the monitor's own weight and moisture, its dry-yield convention",
                   help="Decoded again as the monitor logged it: no import as SMS, nothing left out or recomputed.")
    else:
        badge_line("as_is", "the export as written: nothing left out or recomputed",
                   help="No import as SMS: every reading of the export as it is. Step 3's S0 minimum then applies.")
    notices()
    if other_dec:
        st.caption(":orange[Made from an older decode]",
                   help="This import was made from the readings an older OCED decoded with a product, not from those "
                        "step 1 shows (SMS's default decode of the raw data). Apply imports it again with these values "
                        "from step 1's readings (its cleaning is then set aside).")
    cur_how = "none" if (mode == "as_is" and not retry) else "sms"
    pending = False
    # own settings that leave no reading with a position: the fields to change them open (steps 3 and 4 wait)
    no_reading = mode != "default" and not retry and not _located_count(D["shp"])
    with st.expander("Edit the settings", type="compact", key=f"fi_edit_{TKi}",
                     expanded=(mode == "default" or retry or no_reading)):
        with st.container(key=f"imp_panel_{TKm}"):
            how = st.segmented_control(
                "Import", ["sms", "none"], default=cur_how, required=True,
                key=f"fi_how_{TKi}",
                format_func=lambda h: HOW_LABEL["none_raw" if (h == "none" and is_raw) else h],
                help="As SMS: imported with the values below. None: the export as written (raw: decoded again with "
                     "the monitor's own values), nothing left out or recomputed; step 3's S0 minimum then applies.")
            how = how or "sms"
            S_f, changed_vals = None, []
            if how == "none":
                st.caption(none_text(is_raw))
                # the fields are not drawn with 'None': the values typed in them are kept (set again, so that
                # Streamlit does not drop them) for 'As SMS' again in this file
                for k_ in [f"fi_{n_}_{TKi}" for n_ in IMPORT_FIELDS]:
                    if k_ in ss:
                        ss[k_] = ss[k_]
            else:
                def came(k, text=""):
                    s = SRCP.get(k)
                    lab = str(SOURCE_LABEL.get(s, s) or "")
                    lab = lab[5:] if lab.startswith("from ") else lab
                    return ((f"From: {lab}. " if s else "") + text).strip() or None
                prods = sorted(common.CROPS)
                p0 = RP.get("product") if RP.get("product") in prods else None
                # the data's product as SMS's default resolves it for the file's basis: its crop name, else the
                # monitor's crop definition (an export whose Deere metadata gives a crop id only)
                p_data = _crop(R0.get("product"))
                brand.group_label("Operation")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    f_prod = st.selectbox(
                        "Product", [None] + prods, index=([None] + prods).index(p0), key=f"fi_prod_{TKi}",
                        format_func=lambda c: "unknown" if c is None else c, on_change=_fi_product_changed,
                        args=(TKi, mon_p, fmt_p, V2s.get("crop")),
                        help=("From: you. " if (p0 and p0 != p_data) else "From: the data's crop. " if p0 else "")
                        + "Another product fills in its weight to volume, dry moisture and yield volume limits for "
                          "this kind of file.")
                    ss[f"fi_prodwas_{TKi}"] = f_prod      # what the field shows (a product chosen next: from it)
                    f_tw = st.number_input("Weight to volume (lb/bu)", min_value=1.0, max_value=200.0, step=0.5,
                                           **_start(f"fi_tw_{TKi}", None if RP.get("test_weight_lb_bu") is None else
                                                    float(RP["test_weight_lb_bu"])), format="%.2f",
                                           key=f"fi_tw_{TKi}",
                                           placeholder="as the file gives it",
                                           help=came("test_weight_lb_bu", "Turns the wet mass into bushels."))
                    f_dm = st.number_input("Dry moisture (%)", min_value=0.0, max_value=60.0, step=0.1,
                                           **_start(f"fi_dm_{TKi}", None if RP.get("dry_moisture_pct") is None else
                                                    float(RP["dry_moisture_pct"])), format="%.2f",
                                           key=f"fi_dm_{TKi}",
                                           placeholder="as the file gives it",
                                           help=came("dry_moisture_pct", "The moisture the dry yield is given at."))
                    f_exp = st.checkbox("Expand dry moisture", value=bool(RS.get("expand_dry_moisture")),
                                        key=f"fi_exp_{TKi}",
                                        help="Off (SMS's default): grain drier than the dry moisture is not raised to "
                                             "it. On: dry yield = wet x (100 - M) / (100 - dry moisture) both ways.")
                brand.group_label("Swath and moisture")
                shp_w = V1["shp"] if os.path.exists(str(V1.get("shp") or "")) else D["shp"]
                WA_ = width_audit(read_points(shp_w, mtime(shp_w)))         # the width the monitor logged
                w_log = max((r["logged width (ft)"] for r in WA_), default=None)
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    f_ums = st.checkbox("Manual swath", value=bool(RS.get("use_manual_swath")), key=f"fi_ums_{TKi}",
                                        help="Replaces the width the monitor logged"
                                             + (f" (step 1: {w_log:g} ft)" if w_log else "")
                                             + ". Per-area values are scaled by logged / manual; the grain mass is "
                                               "kept.")
                    w0 = (float(RS.get("manual_swath_ft") or 15.0) if (RS.get("use_manual_swath") or not w_log)
                          else float(w_log))
                    f_msw = st.number_input("Width (ft)", 0.1, 300.0, w0, 0.5, format="%.2f", key=f"fi_msw_{TKi}",
                                            disabled=not f_ums, help="The real width of the header.")
                    f_umm = st.checkbox("Manual moisture", value=bool(RS.get("use_manual_moisture")),
                                        key=f"fi_umm_{TKi}", help="Replaces the moisture of every reading.")
                    mm0 = next((float(RP[k]) for k in ("manual_moisture_pct", "dry_moisture_pct")
                                if RP.get(k) is not None), None)
                    f_mm = st.number_input("Moisture (%)", min_value=0.0, max_value=80.0, step=0.1,
                                           **_start(f"fi_mm_{TKi}", mm0), format="%.2f", key=f"fi_mm_{TKi}",
                                           disabled=not f_umm, placeholder="= the dry moisture",
                                           help="Empty = the dry moisture.")
                brand.group_label("Filter")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    f_min = st.number_input("Min. yield volume (bu/ac)", min_value=0.0, max_value=1e4, step=1.0,
                                            **_start(f"fi_min_{TKi}", None if RP.get("min_yield") in (None, si.AUTO)
                                                     else float(RP["min_yield"])),
                                            format="%.3f", key=f"fi_min_{TKi}", placeholder="no minimum",
                                            help=came("min_yield", "A reading with no dry yield or one below this is "
                                                                   "left out. Empty = no minimum."))
                    f_max = st.number_input("Max. yield volume (bu/ac)", min_value=0.0, max_value=1e5, step=10.0,
                                            **_start(f"fi_max_{TKi}", None if RP.get("max_yield") is None else
                                                     float(RP["max_yield"])),
                                            format="%.2f", key=f"fi_max_{TKi}", placeholder="no maximum",
                                            help=came("max_yield", "A reading above this is left out. Empty = no "
                                                                   "maximum."
                                                      + (" When SMS holds another maximum for the product, type it "
                                                         "here." if SRCP.get("max_yield") == si.SRC_JD else "")))
                brand.group_label("Equipment")
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    f_sd = st.number_input("Start delay (s)", 0.0, 600.0, float(RS.get("start_delay_s") or 0.0), 0.5,
                                           format="%.2f", key=f"fi_sd_{TKi}",
                                           help="The first seconds of every pass left out.")
                    f_ed = st.number_input("Stop delay (s)", 0.0, 600.0, float(RS.get("stop_delay_s") or 0.0), 0.5,
                                           format="%.2f", key=f"fi_ed_{TKi}",
                                           help="The last seconds of every pass left out.")
                    f_fs = st.number_input("Flow shift (s)", -600.0, 600.0, float(RS.get("flow_shift_s") or 0.0), 0.5,
                                           format="%.2f", key=f"fi_fs_{TKi}",
                                           help="The grain mass of a reading moved to the position logged that many "
                                                "seconds earlier (+) or later (-).")
                # a value that does not act (the manual swath / moisture while its box is unticked) keeps the
                # recorded one
                S_f = {"on": True, "product": f_prod, "test_weight_lb_bu": f_tw, "dry_moisture_pct": f_dm,
                       "expand_dry_moisture": bool(f_exp), "use_manual_swath": bool(f_ums),
                       "manual_swath_ft": f_msw if f_ums else RS.get("manual_swath_ft", 15.0),
                       "use_manual_moisture": bool(f_umm),
                       # unticked: empty, so that the manual moisture follows the dry moisture of the product
                       "manual_moisture_pct": f_mm if f_umm else None, "min_yield": f_min,
                       "max_yield": f_max, "start_delay_s": f_sd, "stop_delay_s": f_ed, "flow_shift_s": f_fs}
                if f_prod is None and p_data and _crop(RP.get("product")) == p_data and not (
                        IM.get("product_from") or own_settings(D, R0).get("product")):
                    # 'unknown' on a file whose product in use is its data's own (no product of its own to take
                    # back): the same product, nothing typed
                    S_f["product"] = RP.get("product")
                # against the values the fields started from (an older rule's import: today's values)
                changed_vals = typed_fields(S_f, RP, RS)
            pending = how != cur_how or bool(changed_vals)
            changed = pending or ((retry or refresh) and how == "sms")
            if pending or (how == "sms" and older_ch):
                # an older rule's import: what Apply changes in the import in use (today's values with nothing typed)
                word = {"sms": "as SMS", "none": "as logged" if is_raw else "as it is"}
                nap = ([f"Import {word[cur_how]} → {word[how]}"] if how != cur_how else []) + (
                    import_changes(RS if older_ch else RP, S_f) if S_f is not None else [])
                # the first three changes, and every yield volume limit that changes (never hidden behind 'more')
                shown = nap[:3] + [x for x in nap[3:] if x.startswith(("Min. yield volume", "Max. yield volume"))]
                st.caption(":orange[Not applied: " + (", ".join(shown) + (f" and {len(nap) - len(shown)} more"
                                                                          if len(nap) > len(shown) else "")
                                                       if nap else "the values above") + "]",
                           help=("The import in use is an older OCED rule's (step 1 shows it). Apply imports the file "
                                 "with these values: steps 1 and 2 then show that import." if older_ch else None))
            # the other harvest files (each named by the plan: reached or left, one with no record of its import too)
            others = [t for t, D_ in ss.datasets.items() if t != tag and D_.get("yield", True)]
            # what Apply to all would do (amendment A1: the fields typed, merged into each file's own settings): the
            # files they reach, each with what changes in it (its cleaning set aside), and the files left as they are.
            # Nothing typed (an older rule's import refreshed, a failed import tried again): this file only
            typed = how == "sms" and S_f is not None and bool(changed_vals)
            # the readings this file is imported from (a raw file on 'None' is decoded again from its raw data): not
            # at hand, no Apply can change its import, nor Apply to all from it (amendment A1: never a promise the
            # click does not keep)
            src_me = ew.resolve_moved(B["all_readings"], ss.workdir)
            me_away = (how == "sms" or not is_raw) and not (src_me and os.path.exists(src_me))
            # a raw file on 'None' is decoded again from its raw data: that folder not at hand, no Apply either
            raw_root = _raw_root(D) if (is_raw and how == "none" and changed) else None
            raw_away = is_raw and how == "none" and changed and not raw_at_hand(tag, D, raw_root)
            plan = {}
            if raw_away:
                st.caption(f":orange[The raw data of {tag} is not at hand ({_folder_name(raw_root)}): reconnect the "
                           "drive or open it again (step 1) to decode it as the monitor logged it.]")
            elif me_away:
                at_ = _where(src_me or B["all_readings"])
                st.caption(":orange[" + (
                    f"The readings {tag} is imported from are no longer in the work folder ({at_}): open its data "
                    "again (step 1) to change its import" if _in_folder(src_me or B["all_readings"], ss.workdir) else
                    f"The readings {tag} is imported from are not at hand ({at_}): reconnect the drive to change its "
                    "import") + ("; to change the other files, choose one of them in the File list and type the "
                                 "change on it" if others else "") + ".]")
            elif others and typed:
                try:
                    plan = apply_to_all_plan(tag, S_f, changed_vals)
                except ValueError:
                    plan = {}
            reach = list(plan.get("targets") or [])
            aside = [t for t in reach if has_cleaning(t)]
            left = plan_left_lines(plan) if plan else []
            if not me_away and not raw_away and (has_cleaning(tag) or reach or left):
                st.caption(":orange[" + " ".join(x for x in (
                    f"Applying sets aside the cleaning of {tag}: clean it again in step 3." if has_cleaning(tag)
                    else "",
                    ("Apply to all also changes " + ", ".join(f"{t} ({plan_changes_text(plan, t)})" for t in reach)
                     + ".") if reach else "",
                    f"Apply to all also sets aside the cleaning of {', '.join(aside)}." if aside else "",
                    *left) if x) + "]")
            with st.container(horizontal=True, vertical_alignment="center", key="run_go_imp"):
                go = st.button(f"Apply to {tag}", key=f"fi_go_{TKi}", type="primary" if changed else "secondary",
                               disabled=not changed or me_away or raw_away, icon=":material/check:",
                               help="Imports this file again from all its readings with these values; step 2 then "
                                    "shows the changed data and step 3 cleans it.")
                go_all = (st.button(f"Apply to all {len(others) + 1} harvest files", key=f"fi_goall_{TKi}",
                                    disabled=not typed or me_away,
                                    help="The fields you changed here, each set in the own settings of every other "
                                         "harvest file (" + ", ".join(others) + "): its other settings stay, the "
                                         "weight to volume and dry moisture go only to files of the same product, and "
                                         "a field set back to SMS's default is taken back from each. A product chosen "
                                         "goes to the files that had this file's product (the same choice of it, or "
                                         "each its data's), with that product's own weight to volume, dry moisture "
                                         "and limits for each file; a file of another product, or one whose product "
                                         "was chosen on it for other data, keeps its own; 'unknown' takes the product "
                                         "back. A file they bring nothing keeps its import and its cleaning. With "
                                         "nothing typed, Apply changes this file only.")
                          if others else False)
            if go or go_all:
                prog = st.empty()
                fails, held_w = [], []                    # files not imported; files held open (warnings)
                with st.spinner(f"Decoding {tag} again as the monitor logged it (seconds to a minute) ..."
                                if (how == "none" and is_raw) else "Importing the file again ..."):
                    try:
                        ss[f"fi_msg_{TKm}"] = (
                            apply_to_all(tag, S_f, progress=lambda t, i, n: prog.caption(
                                f"Importing {t} again ({i} of {n}) ..."), failed=fails, warns=held_w,
                                changed=changed_vals) if go_all else
                            apply_as_is(tag, warns=held_w) if how == "none" else
                            apply_custom(tag, S_f, warns=held_w))
                        if fails or held_w:
                            ss[f"fi_warn_{TKm}"] = fails + held_w
                    except ValueError as e:
                        st.error(str(e), icon=":material/error:")
                        return pending
                    except Exception as e:                   # shown, never swallowed
                        st.exception(e)
                        return pending
                st.rerun()
    if mode == "default" or retry:                       # (a failed import: step 1's readings, nothing changed)
        return pending
    # ---- the changed data: four cards against step 1 and its map, on step 1's colour scale
    V2 = active_view(D)
    N2 = data_strip(V2, "strip_2", compare=V1)
    RS_a, RS_1 = IM.get("resolved") or {}, ((V1.get("sms_import") or {}).get("resolved") or {})
    if (V2.get("report") or {}).get("sms_summary") and any(
            not _same_value(RS_a.get(k), RS_1.get(k)) for k in ("test_weight_lb_bu", "dry_moisture_pct",
                                                                 "expand_dry_moisture")):
        sms_summary_line(V2.get("report"), D.get("sms_import"))
    if not N2["located"]:
        st.warning("Your settings leave no reading with a position: change them and Apply again, or switch back to "
                   "SMS's default.", icon=":material/warning:")
        return pending
    mb2 = map_box(f"imp_{key_of(D['shp'])}", map_folded(tag))
    with mb2:
        if mb2.open:
            explorer(D["shp"], key=f"imp_{key_of(D['shp'])}", default=ss.get(f"attr_raw_{key_of(V1['shp'])}"),
                     scale_of=V1["shp"], outline=outline, height=440, extras=False,
                     data=f"{kind_word(import_kind(tag, D))} (step 2)")
    import_details_box(V2)
    explorer_extras(D["shp"])
    return pending


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
    with st.expander("What OCED reads", icon=":material/info:"):
        st.caption("The data of combines, planters and sprayers in four steps: 1 the raw data with SMS's default "
                   "import and the map of every attribute, 2 the import settings, 3 the 3-sigma cleaning with the clip "
                   "to the field boundary and the grower's data to validate or adjust the yields, 4 the clean files "
                   "and reports.")
        st.caption("Combines, raw: Case IH / New Holland .cn1 cards, John Deere Gen4 / G5 logs (JD-Data .jdl), John "
                   "Deere GreenStar 3 cards (.fdd / .fdl), ISOXML harvest task data (TASKDATA.XML with its TLG time "
                   "logs, any number of sets). Point exports of combines, planters and sprayers: SMS and "
                   "Operations Center shapefiles (yield also as .kml / .kmz), or any point shapefile of a machine.")
        with st.expander("SMS's default import, by source", type="compact"):
            st.caption(sms_defaults_text(None))
        with st.expander("The SMS 3-sigma cleaning", type="compact"):
            st.caption(SMS3S_TEXT)
    saved_works_block()


def _away_where(A: dict) -> str:
    """Where the points of a file set aside were: '(the folder X)', '(in the work folder: the folder decoded)'."""
    shp = str((A.get("dataset") or {}).get("shp") or "")
    inside = bool(ss.get("workdir")) and _in_folder(shp, ss.workdir)
    return f"({'in the work folder: ' if inside else ''}{_folder_name(os.path.dirname(shp))})"


def _ask_remove_away(t: str):
    ss[f"rm_away_ask_{file_key(t)}"] = True


def _keep_away(t: str):
    ss.pop(f"rm_away_ask_{file_key(t)}", None)


def _remove_away(t: str):
    """A file set aside taken out of its work (asked first): its cleaning, boundary, grower's data and settings go
    with it; the files in the work folder stay. The work is saved without it."""
    ss.pop(f"rm_away_ask_{file_key(t)}", None)
    (ss.get("away") or {}).pop(t, None)
    ss.away_order = [x for x in (ss.get("away_order") or []) if x != t]
    drop_work_msg_file(t)                                # its 'it stays in this work' line no longer holds
    save_current(quiet=True, even_empty=True)
    ss["rm_away_msg"] = f"{t} was removed from this work (the files in the work folder stay)."


def away_files_block():
    """Step 1: the files of the work set aside when it was opened (their points not at hand), with where their points
    were, the way back, and a button per file to take it out of the work (asked first, since its cleaning goes with
    it): a file whose points are gone for good never stays in the work against the user's will."""
    if ss.get("rm_away_msg"):
        st.success(ss.pop("rm_away_msg"), icon=":material/check_circle:")
    away_ = {t: A for t, A in (ss.get("away") or {}).items() if t not in ss.datasets}
    if not away_:
        return
    clean_ = [t for t, A in away_.items() if A.get("cleaned")]
    inside = [t for t, A in away_.items() if _away_where(A).startswith("(in the work folder")]
    ways = (["reconnect the drive and open the work again"] if len(inside) < len(away_) else []) + (
        ["points that were in the work folder come back only by opening the data again (step 1)"] if inside else [])
    st.caption(":orange[Set aside, their points away: " + ", ".join(f"{t} {_away_where(A)}" for t, A in away_.items())
               + ". They stay in this work" + (f" (with the cleaning of {', '.join(clean_)})" if clean_ else "")
               + ": " + "; ".join(ways) + ". A file you no longer need can be removed from this work.]")
    with st.container(horizontal=True):
        for t in away_:
            k_ = file_key(t)
            if ss.get(f"rm_away_ask_{k_}"):
                continue
            st.button(f"Remove {t} from this work", key=f"rm_away_{k_}", icon=":material/delete:",
                      on_click=_ask_remove_away, args=(t,),
                      help="Asked first. Its cleaning, boundary, grower's data and settings go with it; the files in "
                           "the work folder stay.")
    for t, A in away_.items():
        k_ = file_key(t)
        if not ss.get(f"rm_away_ask_{k_}"):
            continue
        st.warning(f"Remove {t} from this work? " + ("Its cleaning, boundary" if A.get("cleaned") else "Its boundary")
                   + ", grower's data and settings go with it; the files in the work folder stay.",
                   icon=":material/warning:")
        with st.container(horizontal=True):
            st.button("Remove", key=f"rm_away_yes_{k_}", type="primary", on_click=_remove_away, args=(t,))
            st.button("Keep it", key=f"rm_away_no_{k_}", on_click=_keep_away, args=(t,))


def end_of_page():
    """What every run draws last: the action tree in the sidebar, the Save the page asked for, the save status."""
    with st.sidebar:
        action_tree()
    save_requested()                     # a Save the page did not reach in step 3 (it is saved here at the latest)
    if SAVE_PH is not None:
        SAVE_PH.caption(save_status_text())
    draw_work_msg()                      # the 'Opened ...' message as a cleaning of this run left it


# ------------------------------------------------------------------------------------------------ 1 raw data
# Step 1 is the raw data only, imported with SMS's default for its format (no import setting here): the open row,
# the input and its units, then the file's import line, its strip of cards, its map and the details.
with st.container(border=True, key="oced_step_1"):
    brand.step_header(1, "Raw data", "Open the files of a combine, planter or sprayer")
    with (st.expander("Open other data", type="compact", key="open_box") if ss.datasets else st.container()):
        c_up, c_path = st.columns([1.35, 1], vertical_alignment="bottom")
        with c_up:
            ups = st.file_uploader("Upload files", accept_multiple_files=True,
                                   key=f"uploads_{int(ss.get('up_nonce') or 0)}",
                                   help="Combines: a zipped card or JD-Data folder, the files of a GreenStar card, "
                                        "zipped ISOXML task data (TASKDATA sets, also a zip of zips), a yield "
                                        "point export or its .kml / .kmz. Planters and sprayers: the as-applied point "
                                        "export (.shp + .shx + .dbf + .prj, or a zip). Any other point shapefile of a "
                                        "machine too.")
        with c_path:
            with st.container(horizontal=True, vertical_alignment="bottom"):
                st.text_input("or a file or folder on this computer", key="path_in",
                              placeholder=r"C:\...\JD-Data   or   C:\...\card.cn1",
                              help="A folder is read where it is; a .zip is unpacked into the work folder.")
                if st.button("Open", type="primary", icon=":material/folder_open:", key="open_btn"):
                    p_in = (ss.get("path_in") or "").strip()
                    # a path is the user's latest choice unless it is the one opened last (still typed in the box)
                    fresh_path = bool(p_in) and p_in != str(ss.get("last_open_path") or "")
                    if ups and fresh_path:
                        st.toast("Both files to upload and a path are given: remove the uploaded files or empty the "
                                 "path, then Open", icon=":material/warning:")
                    elif ups:
                        request_open(("upload", ups))
                    elif p_in:
                        request_open(("path", p_in))
                    else:
                        st.toast("Upload files or type a path first", icon=":material/info:")
    if ss.open_request:
        req, ss.open_request = ss.open_request, None
        with st.spinner("Unpacking and recognising the input ..."):
            opened = do_open(req)
        if opened:
            if req[0] == "upload":                       # the upload field empties: a path typed next is opened
                ss.up_nonce = int(ss.get("up_nonce") or 0) + 1
            st.rerun()
    if ss.open_error:
        st.error(ss.open_error, icon=":material/error:")
        if ss.open_exc is not None:
            st.exception(ss.open_exc)
        if ss.get("open_fail_log"):
            with st.expander("Details of the input that could not be opened", type="compact"):
                st.text("\n".join(ss.open_fail_log))
        if ss.datasets:
            st.caption("The work on screen is unchanged.")
    deep = deep_work_msg(ss.get("workdir"), {t: bool(D.get("yield", True)) for t, D in (ss.datasets or {}).items()})
    if deep:                                             # said before anything is extracted or cleaned in it
        st.warning(deep, icon=":material/warning:")
    cands, cand, cand_lab = ss.cands, None, None
    if cands is None and ss.datasets:
        st.caption(f":material/folder_open: Saved work **{ss.get('work_name') or default_work_name()}**"
                   + (f" · {ss.input_label}" if ss.get("input_label") else "")
                   + f" · {len(ss.datasets)} file" + ("s" if len(ss.datasets) != 1 else ""),
                   help="Open other data above to start a new work.")
        for w in (ss.get("left_out") or []):                 # left out when this work's data was opened
            st.warning(w, icon=":material/warning:")
    if cands is not None:
        if not cands:
            st.error(cands.message or "Nothing that OCED can read was found.", icon=":material/help:")
        else:
            labels = cand_labels(cands)
            idx = (st.selectbox("Several datasets were found: which one?", range(len(cands)),
                                format_func=lambda i: labels[i], key="cand_idx", index=None,
                                placeholder="choose a dataset ...") if len(cands) > 1 else 0)
            cand = cands[idx] if idx is not None else None
            cand_lab = labels[idx] if idx is not None else None
            same_harvest_warning(cands)
        for w in (getattr(cands, "left_out", None) or []):   # a damaged zip among those of the input, passed over
            st.warning(w, icon=":material/warning:")
        lab_full = (cand_lab or cand["label"]) if cand is not None else ""
        with st.expander("Unpacking log", type="compact"):
            # the whole line of the dataset when the line above is cut short (its field, crop and farm ...)
            st.text("\n".join(([lab_full] if cand_line(lab_full) != lab_full else []) + list(ss.open_log))
                    or "nothing")                          # open_input logged every note once
    if cand is not None:
        icon = ":material/memory:" if cand["kind"] == "raw" else ":material/scatter_plot:"
        st.success(cand_line(cand_lab or cand["label"]), icon=icon)
        for w in (getattr(cand.get("probe"), "warnings", None) or []):
            st.warning(w, icon=":material/warning:")
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
                done_tags = extracted_units(root)            # the units of this input already in the work
                k_ex = len(set(done_tags.values()))
                n_ex = int(ss.get(f"extract_n_{CK}") or 0)   # extractions of this input in this session
                if ss.pop(f"src_collapse_{CK}", False):      # an extraction of the run before: the box folds
                    ss[f"src_box_{CK}"] = False
                box_kw = {} if f"src_box_{CK}" in ss else {"expanded": True}
                with st.expander("Extract more of this input" if k_ex else "Extract", key=f"src_box_{CK}",
                                 on_change="rerun", **box_kw):
                    U = pd.DataFrame([dataclasses.asdict(u) for u in units])
                    U["field"] = U["field"].replace("", "(no field)")
                    U = U.sort_values(["field", "year", "start"], na_position="last").reset_index(drop=True)
                    U.insert(0, "file", [done_tags.get(str(i), "") for i in U["id"]])
                    n_fields = U["field"].nunique()
                    st.markdown(f"Tick the units to extract · **{len(U):,} unit{'s' if len(U) != 1 else ''} in "
                                f"{n_fields:,} field{'s' if n_fields != 1 else ''}**",
                                help="Each field, season and crop becomes its own shapefile. The most recent season "
                                     "is pre-selected; the column 'file' names a file of this work already extracted "
                                     "from the unit.")
                    # a new table after every extraction: the most recent season the first time, nothing selected
                    # once files of this input are in the work
                    ev = st.dataframe(U[["file", "field", "year", "crop", "machine", "n_records", "start", "end",
                                         "label"]],
                                      hide_index=True, on_select="rerun", selection_mode="multi-row",
                                      key=f"units_{CK}_{n_ex}",
                                      selection_default={"selection": {"rows": [] if k_ex else
                                                                       [int(i) for i in U.index[U["default"]]]}},
                                      column_config={"n_records": st.column_config.NumberColumn("records",
                                                                                                format="%d"),
                                                     "label": st.column_config.TextColumn("unit", width="large")})
                    chosen_ids = U.iloc[list(ev.selection.rows)]["id"].tolist()
                    chosen = [u for u in units if u.id in set(chosen_ids)]
                    groups = sorted({(u.field or "(no field)", u.year) for u in chosen},
                                    key=lambda g: (g[0], g[1] or 0))
                    again = sorted({done_tags[str(i)] for i in chosen_ids if str(i) in done_tags})
                    if again:
                        cl = [t for t in again if has_cleaning(t)]
                        st.caption(":orange[Extracting " + ", ".join(again) + " again replaces "
                                   + ("it" if len(again) == 1 else "them")
                                   + (" and sets aside " + ("its" if len(again) == 1 else "their") + " cleaning"
                                      if cl else "")
                                   + (" (your import settings are applied again)"
                                      if any(import_mode(ss.datasets[t]) == "custom" for t in again) else "") + "]")
                    fid = cand["decoder"]
                    dflt = detect.default_options(fid)
                    with st.expander("Decoding options", type="compact"):
                        kw = {}
                        if fid == "cnh_cn1":
                            kw["calibration"] = st.segmented_control(
                                "Calibration curve", ["task", "latest"], default="task", required=True,
                                key=f"cal_{CK}", format_func={"task": "Each task's own (as SMS)",
                                                              "latest": "Crop's latest"}.get)
                            kw["time_basis"] = st.segmented_control(
                                "Time and distance of a reading", ["sms", "period"], default="sms", required=True,
                                key=f"tb_{CK}", format_func={"sms": "Its record's own (as SMS)",
                                                             "period": "One logging period (the display's clock)"}.get)
                            TO = totals_only_of(cand, chosen)
                            if TO:
                                if st.checkbox(f"Add the totals of the {len(TO)} task(s) whose log is not on the card "
                                               "to the SMS Summary", value=False, key=f"cnh_tot_{CK}",
                                               help="SMS lists such a task as a dataset with an area and a weight and "
                                                    "no point (the display kept its totals, not its log): "
                                                    + "; ".join(f"{r.get('label') or r.get('task')} "
                                                                f"({float(r.get('area_ac') or 0):,.2f} ac)"
                                                                for r in TO[:6])
                                                    + (" ..." if len(TO) > 6 else "")
                                                    + ". They add to the Summary only, never to the readings."):
                                    kw["totals_only"] = [r["id"] for r in TO]
                        elif fid == "jd_gs3_rcd":
                            from engine.formats import jd_gs3_rcd as gs3
                            kw["alignment"] = st.segmented_control(
                                "Grain and moisture of a reading", ["sms", "shift"], default="sms", required=True,
                                key=f"al_{CK}", format_func={"sms": "As SMS (no grain lost)",
                                                             "shift": "Fixed time shift (earlier versions)"}.get,
                                help="As SMS: the grain and the moisture of each reading as SMS holds them after "
                                     "reading the card. Fixed time shift: the delays below move them by fixed times.")
                            with st.container(horizontal=True):
                                kw["flow_delay_s"] = st.number_input("Grain flow delay (s)", 0.0, 60.0,
                                                                     gs3.FLOW_DELAY_S, 1.0, key=f"fd_{CK}")
                                kw["moisture_delay_s"] = st.number_input("Moisture delay (s)", 0.0, 60.0,
                                                                         gs3.MOISTURE_DELAY_S, 1.0, key=f"md_{CK}")
                        elif fid == "jd_jdl":
                            kw["points"] = st.segmented_control(
                                "Points", ["sms", "ops_center"], default="sms", required=True, key=f"pts_{CK}",
                                format_func={"sms": "As SMS Advanced reads the .jdl",
                                             "ops_center": "One per flow sample, as Operations Center"}.get,
                                help="As SMS Advanced: the points SMS makes of the logs (the file then holds what "
                                     "SMS holds after its import). As Operations Center: one reading per flow sample.")
                        elif fid == "isoxml":
                            kw["time_logs"] = st.segmented_control(
                                "Time logs", ["sms", "joined"], default="sms", required=True, key=f"isl_{CK}",
                                format_func={"sms": "Each on its own (as SMS)",
                                             "joined": "Joined where one follows the other"}.get,
                                help="As SMS: every time log file is read on its own, so the grain of its first "
                                     "seconds goes to no reading and its last seconds are no readings. Joined: the "
                                     "logs that follow each other without a gap are read as one, which keeps those "
                                     "readings (more readings and grain than SMS holds).")
                    with st.container(key="run_go"):
                        go = st.button(f"Extract {len(groups)} file" + ("s" if len(groups) != 1 else "") if groups
                                       else "Extract", type="primary", icon=":material/file_export:",
                                       disabled=not chosen, key=f"extract_{CK}",
                                       help="Each field, season and crop becomes a file.")
                    if go:
                        opts = dataclasses.replace(dflt)
                        done = {"log": [], "warnings": []}
                        with st.status("Extracting ...", expanded=True) as status:
                            try:
                                made = extract(cand, chosen, opts, kw,
                                               lambda m: (done["log"].append(str(m)), status.text(m)),
                                               warn=lambda m: (done["warnings"].append(str(m)),
                                                               st.warning(m, icon=":material/warning:")))
                                ss.datasets.update(made)
                                again_l = reapply_after_extract(              # a custom import of a replaced file
                                    made, warn=lambda m: (done["warnings"].append(str(m)),
                                                          st.warning(m, icon=":material/warning:")))
                                for m in again_l:
                                    done["log"].append(m)
                                    status.text(m)
                                ss.active = next(iter(made), ss.active)
                                ss["active_pick"] = ss.active            # the File picker follows
                                save_current(quiet=True)
                                done["label"] = (f"Extracted {len(made)} file(s): "
                                                 + ", ".join(f"{m['tag']} ({int(ss.datasets[m['tag']]['n']):,} "
                                                             "readings)" for m in made.values())
                                                 + "".join(f"; {m}" for m in again_l))
                                status.update(label=done["label"], state="complete", expanded=False)
                                # the sidebar (this work, Save, the saved works) was drawn before the extraction:
                                # the page is drawn again, with this extraction's account under the box (folded)
                                ss[f"extract_done_{CK}"] = done
                                ss[f"src_collapse_{CK}"] = True
                                ss[f"extract_n_{CK}"] = n_ex + 1         # a new table, from its default
                            except ValueError as e:
                                status.update(label="Extraction stopped", state="error")
                                st.error(str(e), icon=":material/error:")
                            except Exception as e:                   # shown, never swallowed
                                status.update(label="Extraction failed", state="error")
                                st.exception(e)
                        if ss.get(f"extract_done_{CK}") is done:
                            st.rerun()
                done = ss.pop(f"extract_done_{CK}", None)       # the extraction of the run before: under the box
                if done:
                    with st.status(done["label"], state="complete", expanded=False):
                        for m in done["log"]:
                            st.text(m)
                    for m in done["warnings"]:
                        st.warning(m, icon=":material/warning:")
        else:
            # a point export is known by the file it comes from, not by its name: two exports with the same file name
            # (one per combine folder) are two files of the work, each with its own tag
            src = src_of(cand)
            existing = next((t for t, d in ss.datasets.items() if d.get("kind") == "export" and (
                d.get("src") or os.path.normcase(os.path.abspath(str((d.get("sms_import") or {}).get("all_readings")
                                                                     or d.get("shp"))))) in
                (src, os.path.normcase(os.path.abspath(cand["path"])))), None)
            if existing is None:
                if cand.get("sections") and not cand.get("source_path"):
                    twins = [c for c in cands if c is not cand and c.get("kind") == "export" and
                             os.path.basename(c.get("source_path") or c["path"]).lower()
                             == os.path.basename(cand["path"]).lower()]
                    wd_sec = os.path.join(ss.workdir, "sections", key_of(src)) if twins else ss.workdir
                    with st.spinner("One point per header section: collapsing to one reading per combine and "
                                    "second ..."):
                        er.use_candidate(cand, wd_sec, log=ss.open_log.append)
                tag = free_tag(er.candidate_tag(cand), src)
                n0 = int(cand.get("n") or 0)
                err_i = None
                if cand.get("yield", True):
                    # SMS's default import, the file's default (step 1); a failure opens the file as it is
                    try:
                        shp_i, n_i, rec = import_as_sms(cand["path"], tag, os.path.join(ss.workdir, "imported"),
                                                        crop=cand.get("crop"), monitor=cand.get("monitor_product"),
                                                        fmt=import_fmt(None, cand))
                    except Exception as e:
                        shp_i, n_i, rec, err_i = cand["path"], None, None, f"{type(e).__name__}: {e}"
                else:
                    shp_i, n_i, rec = cand["path"], None, None
                n_d = n_i if n_i is not None else n0
                if not cand.get("yield", True):
                    imp_d = {"shp": shp_i, "n": n_d, **stamp(shp_i), "sms_import": None}
                elif rec is None:
                    imp_d = {"shp": shp_i, "n": n_d, **stamp(shp_i), "sms_import": None, "error": err_i,
                             "basis": export_import_basis_of(cand["path"], cand)}
                else:
                    imp_d = {"shp": shp_i, "n": n_d, **stamp(shp_i), "sms_import": copy.deepcopy(rec),
                             "basis": {"all_readings": cand["path"], "crop": rec.get("crop"),
                                       "monitor": copy.deepcopy(rec.get("monitor")), "fmt": rec.get("fmt")}}
                base_name = os.path.basename(cand.get("source_path") or cand["path"])
                same = [c for c in cands if c.get("kind") == "export" and c is not cand and
                        os.path.basename(c.get("source_path") or c["path"]).lower() == base_name.lower()]
                ss.datasets[tag] = {"tag": tag, "shp": shp_i, "zip": None, "n": n_d,
                                    "kind": "export", "src": src,
                                    "label": (os.path.join(os.path.basename(os.path.dirname(src)), base_name) if same
                                              else base_name),
                                    "op": cand.get("operation") or "harvest", "yield": bool(cand.get("yield", True)),
                                    "source": None, "report": None, "area_ac": None, "units": [],
                                    "sms_import": rec,
                                    "inputs_left_out": [str(w) for w in (cand.get("inputs_left_out") or [])],
                                    "import_default": imp_d, "import_mode": "as_is" if err_i else "default"}
                save_current(quiet=True)             # listed in Saved works with its import from now on
                existing = tag
            if ss.get("last_cand") != src:           # a new choice in the list: that file on screen
                ss.last_cand = src
                ss.active = existing
                ss["active_pick"] = existing
                st.rerun()                           # the sidebar (this work, Save) is drawn again with the file

    DS = ss.datasets
    if not DS:
        # the next action: open the data, choose one of its datasets, or tick its units and Extract
        st.info("Choose the dataset to work on in the list above." if (cands and cand is None) else
                "Tick the units to extract and click Extract: each field, season and crop becomes a file." if (
                    cand is not None and cand.get("kind") == "raw" and ss.units.get(cand["probe"].root)) else
                "Open the data of a field: the import settings, the cleaning and the clean files follow.",
                icon=":material/arrow_upward:")
        away_files_block()                               # a work whose every file is set aside: the way out
        end_of_page()
        st.stop()
    brand.rule()
    tags = list(DS)
    if ss.active not in tags:
        ss.active = tags[0]
    D = DS[ss.active]
    # SMS's default import of the file picked (a work of an earlier version), before the picker names its readings
    if default_needs_build(ss.active):
        with st.spinner("Preparing SMS's default import of this file ..."):
            default_note = ensure_default(ss.active)
    else:
        default_note = ensure_default(ss.active)         # only says when its readings are gone
    if len(tags) > 1:
        ss["active_pick"] = ss.active
        st.selectbox("File", tags, key="active_pick", on_change=_pick_file,
                     format_func=lambda t: f"{t} · {int(default_view(DS[t]).get('n') or DS[t].get('n') or 0):,} "
                                           "readings")
    away_files_block()
    if (not D.get("shp") or not os.path.exists(D["shp"])) and import_mode(D) != "default" \
            and default_of(D).get("shp") and os.path.exists(default_of(D)["shp"]) \
            and derived_import(ss.active, D.get("shp")):
        # the file of its own import is gone, its default import is there: back to it (a default still made from the
        # readings an older version decoded is named as such, with the way to SMS's default). A file in use read in
        # place (the export as it is, an import that changed nothing) is not: its folder is away (the error below),
        # and its record and cleaning stay as they are
        gone_ = f"{ss.active}: its import with your settings is no longer on disk: back to "
        try:
            st.warning(back_to_default(ss.active, msg=(
                gone_ + "the import of the older version's readings (Older rule), not SMS's default. To get SMS's "
                f"default (today's rule), {older_decode_way(D)}." if default_of(D).get("older_decode") else
                gone_ + "SMS's default import.")), icon=":material/warning:")
        except ValueError:
            pass
    if not D.get("shp") or not os.path.exists(D["shp"]):
        st.error(f"The points of this file are no longer at {D.get('shp')}: reconnect the drive or the folder they "
                 "were read from, or remove the file from this work.", icon=":material/error:")
        if st.button("Remove this file from the work", key=f"rm_file_{file_key(ss.active)}", icon=":material/delete:",
                     help="Its cleaning, boundary and grower's data go with it; the files in the work folder stay."):
            if D.get("src") and D.get("src") == ss.get("last_cand"):
                ss.cands, ss.last_cand = None, None     # the list of step 1 would import the export again
            for d_ in (ss.datasets, ss.cleaned, ss.boundary, ss.grower, ss.a3set, ss.cfset):
                d_.pop(ss.active, None)
            drop_work_msg_file(ss.active)
            ss.active = next(iter(ss.datasets), None)
            ss.pop("active_pick", None)
            save_current(quiet=True, even_empty=True)    # (its only file removed: saved with none)
            st.rerun()
        end_of_page()
        st.stop()
    V1 = default_view(D)                                 # step 1: SMS's default import of the file
    if not V1.get("shp") or not os.path.exists(V1["shp"]):
        V1 = active_view(D)
    kind1, text1, help1 = step1_badge(V1, D, ss.active)
    badge_line(kind1, text1, help1)
    if default_note:
        st.caption(f":orange[{default_note[0].upper() + default_note[1:]}.]")
    IM1 = V1.get("sms_import") or {}
    if IM1 and V1.get("yield", True) and unknown_point_product(IM1):
        st.warning(UNKNOWN_POINT_PRODUCT, icon=":material/warning:")
    N1 = data_strip(V1, "strip_1")
    if IM1.get("crops_note"):
        st.warning(IM1["crops_note"][0].upper() + IM1["crops_note"][1:] + ".", icon=":material/warning:")
    sms_summary_line(V1.get("report"), V1.get("sms_import"))
    B_ = boundary_of(ss.active)
    OPX1 = N1["op"]
    if not N1["located"]:
        # an import that left no reading (every yield below the min. yield volume, an export without points): no map;
        # step 2 can change the import
        st.warning(("The import left no reading with a position" if IM1.get("n_all") else
                    "This file holds no reading with a position") + ": nothing to map. Change the min. yield volume "
                   "(or another value) in step 2, or open another file.", icon=":material/warning:")
    else:
        dflt_attr = (("Yld_Vol_Dr" if "Yld_Vol_Dr" in N1["df"] else N1["det"].get("yield")) if V1.get("yield", True)
                     else (OPX1["rates"][0] if OPX1["rates"] else None))
        mb1 = map_box(f"raw_{key_of(V1['shp'])}", map_folded(ss.active))
        with mb1:
            if mb1.open:
                explorer(V1["shp"], key=f"raw_{key_of(V1['shp'])}", default=dflt_attr,
                         outline=B_["outline"] if B_ else None, height=520, extras=False,
                         data=f"{kind_word(kind1)} (step 1)")
    # the details, one compact line each: the header width as logged, the import record, the decoder's report, the
    # attributes, the first records, the extracted points
    if V1.get("yield", True):
        width_audit_box(N1["df"])
    import_details_box(V1)
    decoder_report_box(V1, D)
    explorer_extras(V1["shp"])
    if V1.get("zip"):
        download("Extracted points (.zip)", V1["zip"], "application/zip", key=f"dl_ext_{ss.active}",
                 help="Every decoded reading, before the import as SMS.")
    if (N1["located"] if _norm_p(V1["shp"]) == _norm_p(D["shp"]) else _located_count(D["shp"])):
        brand.next_step(3, "Cleaning", note="2 · Import settings only to change them")
    else:                                                # the page stops after step 2: its settings first
        brand.next_step(2, "Import settings", note="nothing to clean yet")

# ------------------------------------------------------------------------------------------------ 2 import settings
# Step 2: the switch 'Use SMS's default settings' (on: the data is step 1's), off: the import settings of the file
# with Apply; once applied, the changed data (its strip and its map, on step 1's scale). Step 3 cleans what step 2
# holds.
with st.container(border=True, key="oced_step_2"):
    brand.step_header(2, "Import settings", (f"{ss.active} · {tags.index(ss.active) + 1} of {len(tags)}"
                                             if len(tags) > 1 else "SMS's default, or your own values"))
    IMPORT_PENDING = import_panel(ss.active, D, V1, outline=B_["outline"] if B_ else None)
    D = DS[ss.active]
    df0 = read_points(D["shp"], mtime(D["shp"]))            # the import in use: what step 3 cleans
    OPX = operation_of(D["shp"], mtime(D["shp"]))
    n_located = located_in(df0)
    if n_located:
        brand.next_step(3, "Cleaning")
if not n_located:
    # nothing to clean: the page stops after step 2 (its settings can be changed and applied)
    end_of_page()
    st.stop()

# ------------------------------------------------------------------------------------------------ 3 SMS 3-sigma
# Step 3: the import it starts from (with S0's minimum), the sequence, the settings (folded into one line once the
# file is cleaned), Clean; then the strip of the result, the clean map under it (its statistics at its side) and the
# details in tabs.
with st.container(border=True, key="oced_step_3"):
    IS_Y = bool(D.get("yield", True))
    TK = file_key(ss.active)
    seam_box = None
    D0 = sms.DEFAULTS
    sub_n = f"{ss.active} · {tags.index(ss.active) + 1} of {len(tags)}" if len(tags) > 1 else ""
    C_prev = ss.cleaned.get(ss.active)
    folded = bool(C_prev) and os.path.exists(str(C_prev.get("shp") or ""))   # settings in one line after a cleaning
    MCH, mbasis = combines_of(df0) if IS_Y else ([], "")
    P0 = ss.get("smsset") or {}
    if IS_Y:
        brand.step_header(3, "Cleaning: SMS 3-sigma", sub_n or "With the field boundary and the grower's data")
        f_order0 = P0.get("filter_order") if P0.get("filter_order") in sms.FILTER_ORDERS else D0["filter_order"]
        f_order = ss.get("filter_order") if ss.get("filter_order") in sms.FILTER_ORDERS else f_order0
        SI = sms.step_info(f_order)
        has_imp = import_min_yield(ss.active)[1]
        # None: the S0 of a cleaning that ran with no minimum (a work rebuilt from its cleaning record)
        min0 = P0.get("min_yield", D0["min_yield"])
        min0 = 0.0 if min0 is None else float(min0)
        min_kept = float(ss.get("min_yield_v", min0))   # step 3's own minimum (files not imported as SMS)
        starts_from_line(ss.active, D, None if has_imp else float(ss.get("min_yield", min_kept)), IMPORT_PENDING)
        st.caption(f"S0 import check → S1 clip → S2 swath → S3 {SI['S3']['attribute']} → S4 {SI['S4']['attribute']} "
                   "→ S5 dry yield", help=SEQ_HELP)
    else:
        brand.step_header(3, "Cleaning: 3-sigma", sub_n or "With the field boundary")
        starts_from_line(ss.active, D)
        st.caption("S0 import check → S1 clip → 3-sigma per attribute", help=A3_SEQ_HELP)
    set_key = f"set_box_{TK}_{key_of(str(C_prev.get('at')) + '|' + str(mtime(C_prev['shp'])))}" if folded else None
    set_box = (st.expander("Settings · " + settings_summary(ss.active, IS_Y, P0, len(MCH)), key=set_key)
               if folded else st.container())
    with set_box:
        if IS_Y:
            with st.container(key="method_panel"):
                with st.container(horizontal=True, vertical_alignment="bottom"):
                    k_sd = st.number_input("k (SD)", 1.0, 6.0, float(P0.get("k_sd", D0["k_sd"])), 0.5, key="k_sd",
                                           help="Keep mean ± k standard deviations (3 = the 3-sigma of SMS).")
                    gm = list(sms.GROUP_MODES)
                    group_by = st.selectbox("Mean and SD per", gm, index=gm.index(P0.get("group_by", "auto")),
                                            key="group_by", format_func=GROUP_LABEL.get,
                                            help="auto: one mean and SD per combine over all its tasks and days (one "
                                                 "for the field when one combine cut it). task: each dataset (one "
                                                 "combine on one day). combine: one per combine. field: one for every "
                                                 "reading of the file.")
                    max_passes = st.number_input("Yield passes (max)", 1, 10,
                                                 int(P0.get("max_yield_passes", D0["max_yield_passes"])), 1,
                                                 key="max_passes",
                                                 help="Another yield pass runs while the SD falls by more than 25 %, "
                                                      "up to this many.")
                    if has_imp:
                        # S0 takes the import's minimum (the Starts-from line gives it): step 3's own minimum, which
                        # the files not imported as SMS take, stays as it was
                        min_yield = min_kept
                    else:
                        min_yield = st.number_input("S0 minimum (bu/ac)", 0.0, 50.0, min_kept, 1.0, key="min_yield",
                                                    on_change=_keep_min_yield,
                                                    help="S0 drops the readings below this (files not imported as "
                                                         "SMS).")
                with st.container(horizontal=True):
                    clip = st.toggle("S1 Clip To Field Boundary", value=bool(P0.get("clip", D0["clip"])),
                                     key="t_clip", help="Needs the boundary of the file (below); a file without one "
                                                        "is not clipped.")
                    swath = st.toggle("S2 Optimize Swath Widths", value=bool(P0.get("swath", D0["swath"])),
                                      key="t_swath")
                    flt = {}
                    for fid in ("S3", "S4"):             # the two filters in the order chosen (keys unchanged)
                        a = SI[fid]["attribute"]
                        flt[a] = st.toggle(f"{fid} {a}", value=bool(P0.get(a, D0[a])),
                                           key="t_moist" if a == "moisture" else "t_speed")
                    yld = st.toggle("S5 dry yield", value=bool(P0.get("yield", D0["yield"])), key="t_yield")
                with st.expander("More settings", type="compact", key="more_sms"):
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        fo_opts = list(sms.FILTER_ORDER_LABELS)
                        f_order = st.selectbox("Order of the filters", fo_opts, index=fo_opts.index(f_order0),
                                               key="filter_order", format_func=sms.FILTER_ORDER_LABELS.get,
                                               help="S3 and S4: moisture, then speed is the method. Speed, then "
                                                    "moisture repeats an SMS cleaning made in that earlier order.")
                        sc_opts = list(sms.SWATH_SCOPES)
                        sw_scope = st.selectbox("Optimize Swath Widths over", sc_opts,
                                                index=sc_opts.index(P0.get("swath_scope") if P0.get("swath_scope")
                                                                    in sc_opts else D0["swath_scope"]),
                                                key="swath_scope", format_func=SWATH_SCOPE_LABEL.get,
                                                help="All combines: one SMS instance holds every combine, so a strip "
                                                     "one combine cut is overlap for the others (the default). Each "
                                                     "combine alone: one instance per combine. Not yet established "
                                                     "against SMS: keep the default unless you repeat such a "
                                                     "cleaning.")
                        bi_opts = list(sms.SWATH_BIASES)
                        sw_bias = st.selectbox("Lateral offset check", bi_opts,
                                               index=bi_opts.index(P0.get("swath_bias") if P0.get("swath_bias")
                                                                   in bi_opts else D0["swath_bias"]),
                                               key="swath_bias", format_func=SWATH_BIAS_LABEL.get,
                                               help="A combine whose logged points sit beside the centre of the strip "
                                                    "it cut. Warn (the default): the warnings say so. Auto: the points "
                                                    "are moved back before S2 (not yet established against SMS). Off: "
                                                    "not measured.")
                        sw_passes = st.number_input("Optimize Swath Widths passes", 1, int(sms.SWATH_PASSES_MAX),
                                                    swath_passes_of(P0), 1, key="swath_passes",
                                                    help="1 (the default): Clip To Field Boundary and Optimize Swath "
                                                         "Widths run once. 2 or 3 repeat an SMS cleaning whose chain "
                                                         "had them that many times. Keep 1 unless you repeat such a "
                                                         "cleaning.")
            sset = {"k_sd": float(k_sd), "group_by": group_by, "max_yield_passes": int(max_passes),
                    "min_yield": float(min_yield), "clip": bool(clip), "swath": bool(swath),
                    "speed": bool(flt["speed"]), "moisture": bool(flt["moisture"]), "yield": bool(yld),
                    "filter_order": f_order, "swath_scope": sw_scope, "swath_bias": sw_bias,
                    "swath_passes": int(sw_passes)}
            ss.smsset = dict(sset)
        else:
            sset = a3_panel(ss.active, OPX, df0)
        clip = bool(sset.get("clip", True))
        # ---- the field boundary and the grower's data of the file on screen (each file keeps its own)
        c_b, c_g = st.columns(2, gap="medium")
        with c_b:
            with st.container(key=f"field_box_b_{TK}"):
                st.markdown("**Field boundary (S1)**")
                B = ss.boundary.get(ss.active)
                if B:
                    if B["needs_choice"]:
                        st.info(f"{B['name']} · {len(B.get('fields') or [])} fields in one file",
                                icon=":material/crop_free:")
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
                                             default=[v for v in (B.get("feature") or []) if v in opts],
                                             key=f"bnd_feat_{TK}", format_func=lab.get,
                                             placeholder="choose the field ...",
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
                        st.caption(":orange[Looks like a trial plan]",
                                   help="This file looks like a trial plan (plots): S1 clips to the plots, not to a "
                                        "field boundary. Give the field boundary to keep the alleys and the border.")
                    for w in B.get("warnings") or []:
                        st.caption(w)
                    if st.button("Remove the boundary", icon=":material/delete:", key=f"bnd_rm_{TK}"):
                        ss.boundary.pop(ss.active, None)
                        st.rerun()
                else:
                    bup = st.file_uploader("Boundary file", accept_multiple_files=True,
                                           key=f"bnd_up_{TK}_{int(ss.get('up_nonce') or 0)}", type=BOUNDARY_TYPES,
                                           help="A .zip (a shapefile or an SMS 'Boundaries' export), the .shp + .shx "
                                                "+ .dbf + .prj of a shapefile, a .geojson, .gpkg, .kml or .kmz. "
                                                "Without a boundary S1 is skipped and every reading of the file goes "
                                                "into the cleaning.")
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        bpath = st.text_input("or a file on this computer", key=f"bnd_path_{TK}",
                                              placeholder=r"C:\...\field boundary.zip")
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
        with c_g:
            if not IS_Y:
                with st.container(key=f"field_box_g_{TK}"):
                    st.markdown("**What the file is**", help="Recognised from the column names. The grower's data "
                                                             "(total weight, moisture, bushel weight) apply to harvest "
                                                             "files.")
                    rows_i = [("Operation", OPX["label"]),
                              ("Applied rate", ", ".join(OPX["rates"]) or "none found (choose the attributes at the left)"),
                              ("Target rate", ", ".join(OPX["targets"]) or "-"), ("Speed", OPX["speed"] or "-"),
                              ("Machine", OPX["machine"] or "-"), ("Dataset", OPX["dataset"] or "-")]
                    if OPX["product"]:
                        pv = df0[OPX["product"]].astype(str).replace({"": np.nan, "nan": np.nan}).dropna().unique()
                        rows_i.append(("Product", ", ".join(map(str, pv[:5])) + (f" … ({len(pv)})" if len(pv) > 5
                                                                                 else "")))
                    st.dataframe(pd.DataFrame(rows_i, columns=["", "in this file"]), hide_index=True)
            else:
                G0 = ss.grower.get(ss.active) or {}
                with st.expander("Grower's weight · optional", key=f"gw_box_{TK}", expanded=bool(G0.get("weight"))):
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        g_unit_prev = ss.get(f"gw_u_{TK}", G0.get("unit") or "lb")
                        per_ac = g_unit_prev == "bu/ac"
                        g_w = st.number_input("Yield of the field" if per_ac else "Total weight of the field", 0.0,
                                              1e12, value=G0.get("weight"), step=1.0 if per_ac else 100.0,
                                              key=f"gw_w_{TK}",
                                              format=("%.2f" if per_ac else "%.3f" if g_unit_prev == "t" else "%.0f"),
                                              placeholder="optional",
                                              help="What the grower got for this field (scale tickets or the grain "
                                                   "cart), as written, in the unit at the right; bu/ac when the "
                                                   "grower gives the yield per acre (it is made a total with the "
                                                   "acres).")
                        g_unit = st.segmented_control("Unit", list(er.TICKET_UNITS), default=G0.get("unit") or "lb",
                                                      required=True, key=f"gw_u_{TK}",
                                                      format_func=TICKET_UNIT_LABEL.get)
                    B_g = boundary_of(ss.active)
                    # the boundary's acres only when S1 clips to it: with the clip off the monitor total is the whole
                    # file's, and the engine then takes the area harvested
                    B_c = B_g if (B_g and clip) else None
                    g_area = None
                    if g_unit == "bu/ac":
                        ph = (f"empty = the boundary, {B_c['area_ac']:,.2f} ac" if B_c else
                              "empty = the area harvested (every strip once)"
                              + (" - S1 is off: type the grower's acres" if B_g else ""))
                        g_area = st.number_input("Acres the yield is over", 0.0, 1e7, value=G0.get("area_ac"),
                                                 step=1.0, key=f"gw_a_{TK}", format="%.2f", placeholder=ph,
                                                 help="The grower's acres for this yield. Empty: the field "
                                                      "boundary's area; without a boundary or with the clip off, the "
                                                      "area harvested, every strip once. bu/ac x acres = the "
                                                      "grower's total in bushels.")
                    with st.container(horizontal=True, vertical_alignment="bottom"):
                        g_basis = st.segmented_control("Weighed", ["wet", "dry"], default=G0.get("basis") or "wet",
                                                       required=True, key=f"gw_b_{TK}",
                                                       format_func={"wet": "As delivered (wet)",
                                                                    "dry": "At the standard moisture"}.get,
                                                       help="As delivered: compared with the monitor's wet total (or, "
                                                            "with the grain moisture, brought to the standard "
                                                            "moisture, one-sided: grain drier than the standard stays "
                                                            "as weighed). At the standard moisture: compared with the "
                                                            "file's dry total.")
                        g_m = st.number_input("Grain moisture (%)", 0.0, 60.0, value=G0.get("moisture"), step=0.1,
                                              key=f"gw_m_{TK}", placeholder="optional", disabled=g_basis != "wet",
                                              help="The moisture of the grain the grower weighed: the weight is "
                                                   "brought to the standard moisture and compared with the "
                                                   "monitor's dry total.")
                        g_tw = st.number_input("Bushel weight (lb/bu)", 1.0, 100.0, value=G0.get("test_weight"),
                                               step=0.1, key=f"gw_tw_{TK}", placeholder="optional",
                                               help="The weight of the grower's bushel. A weight in lb, kg or t is "
                                                    "compared as a mass, in the file's bushels: this value is then "
                                                    "only reported. Bushels (bu, bu/ac) use it only when you say "
                                                    "below that they are bushels of this weight.")
                    g_bush = G0.get("bushels") or "given"
                    if g_unit in ("bu", "bu/ac") and g_tw:
                        g_bush = st.segmented_control("The grower's bushels are", list(GROWER_BUSHELS),
                                                      default=G0.get("bushels") or "given", required=True,
                                                      key=f"gw_bu_{TK}", format_func=GROWER_BUSHELS.get,
                                                      help="As given: trade bushels (an elevator's weight / its "
                                                           "standard bushel), compared as they are. Bushels of the "
                                                           "bushel weight above: measured by volume, so converted "
                                                           "through its mass (bu x that weight / the file's bushel "
                                                           "weight).") or "given"
                    g_use = st.segmented_control("Use it to", list(GROWER_USE),
                                                 default=G0.get("use") or "validate", required=True,
                                                 key=f"gw_use_{TK}", format_func=GROWER_USE.get, disabled=not g_w,
                                                 help="Validate: the monitor's total against the grower's, L = "
                                                      "grower / monitor and a verdict; the clean file does not "
                                                      "change. Adjust: also Yld_Level = the dry yield x the combine "
                                                      "factor x L in the clean file, and the weight may confirm a "
                                                      "combine factor above the max; the monitor's columns stay as "
                                                      "logged.")
                    with st.expander("More", type="compact", key=f"gw_more_{TK}"):
                        with st.container(horizontal=True, vertical_alignment="bottom"):
                            crops = [None] + sorted(common.CROPS)
                            g_crop = st.selectbox("Crop", crops, index=crops.index(G0.get("crop"))
                                                  if G0.get("crop") in crops else 0, key=f"gw_c_{TK}",
                                                  format_func=lambda c: "from the file" if c is None else c,
                                                  help="For the standard moisture and the crop's bushel weight when "
                                                       "the file does not give them.")
                            g_sm = st.number_input("Standard moisture (%)", 0.0, 40.0, value=G0.get("std_moisture"),
                                                   step=0.5, key=f"gw_sm_{TK}", placeholder="decoder / crop table")
                            bf_opts = list(BUSHEL_FROM_LABEL)
                            g_bf = st.selectbox("Bushel of the monitor's total", bf_opts,
                                                index=bf_opts.index(G0.get("bushel_from") if G0.get("bushel_from")
                                                                    in bf_opts else "file"),
                                                key=f"gw_bf_{TK}", format_func=BUSHEL_FROM_LABEL.get,
                                                help="The file's (the default): its own wet mass / wet volume, the "
                                                     "bushel the monitor's volume columns are in. The declared one: "
                                                     "the import's weight to volume, else the crop table, for a file "
                                                     "whose mass column is not in lb/ac (the cleaning warns when the "
                                                     "two differ by more than 0.5 %).")
                    ss.grower[ss.active] = {"weight": float(g_w) if g_w else None, "unit": g_unit or "lb",
                                            "basis": g_basis or "wet", "moisture": g_m if g_basis == "wet" else None,
                                            "test_weight": g_tw, "crop": g_crop, "std_moisture": g_sm,
                                            "use": g_use or "validate", "area_ac": g_area or None,
                                            "bushels": g_bush if (g_unit in ("bu", "bu/ac") and g_tw) else None,
                                            "bushel_from": g_bf if g_bf != "file" else None}
                    T_ = grower_ticket(ss.grower[ss.active])
                    if T_ is not None:
                        try:
                            conv = er.ticket_conversion(T_, test_weight=settings_of(ss.active, sset).get(
                                "test_weight_lb_bu"), shp=D["shp"], crop=g_crop,
                                area_ac=(B_c["area_ac"] if B_c else None), area_source="the field boundary")
                        except ValueError as e:
                            conv = {"error": str(e), "text": str(e)}
                        if conv.get("error"):
                            st.warning(f"{er.ticket_label(T_)}: {conv['error']}", icon=":material/warning:")
                        else:
                            # the totals in one line (a yield per acre: over its acres first), the rest behind "?"
                            per_ac_ = (f"x {float(conv['area_ac']):,.2f} ac "
                                       if T_.get("unit") == "bu/ac" and conv.get("area_ac") else "")
                            short = (f"{per_ac_}= {conv['lb']:,.0f} lb · {conv['bu']:,.2f} bu at "
                                     f"{float(conv['test_weight']):.2f} lb/bu"
                                     if (conv.get("lb") is not None and conv.get("bu") is not None
                                         and conv.get("test_weight")) else conv["text"])
                            st.caption(short, help=f"{er.ticket_label(T_)} {conv['text']}"
                                       + (f"; {T_['moisture_pct']:g} % grain moisture"
                                          if T_["moisture_pct"] is not None else "")
                                       + ("; weighed as delivered." if T_["basis"] == "wet" else
                                          "; at the standard moisture.")
                                       + (f" The grower's bushel weight {float(g_tw):.2f} lb/bu is reported, not "
                                          "used: the weight is compared as a mass."
                                          if (g_tw and g_unit in ("lb", "kg", "t")) else ""))
        # ---- several combines: the combine factor, switched on by the user, beside the passes side by side
        if IS_Y:
            CF0 = combine_settings(ss.active)
            if len(MCH) < 2:
                st.caption("One combine: no combine factor.",
                           help=(f"Read from {mbasis}." if mbasis.startswith("the ") else
                                 mbasis[:1].upper() + mbasis[1:] + ".") + " A combine factor needs two combines or "
                                                                          "more.")
                cf_on, cf_m, cf_ref, cf_max, cf_tc = (False, CF0["method"], CF0["reference"], CF0["max_pct"],
                                                      CF0["ticket_confirms"])
            else:
                with st.container(key=f"field_box_m_{TK}"):
                    st.markdown(f"**Combine factor** · {len(MCH)} combines",
                                help=f"The combines from {mbasis}, with their readings and mean dry yield in the table. "
                                     "Off by default: you decide, from the passes side by side at the right.")
                    c_l, c_r = st.columns([1, 1.15], gap="medium")
                    with c_l:
                        cf_on = st.toggle("Apply the combine factor", value=CF0["on"], key=f"cf_on_{TK}",
                                          help="It runs after the 3-sigma steps on the kept readings and applies a "
                                               "factor to a combine only where the passes side by side prove it "
                                               "(Yld_Harm = the cleaned yield x the factor).")
                        cf_m_now = ss.get(f"cf_m_{TK}") if ss.get(f"cf_m_{TK}") in CF_HELP else CF0["method"]
                        cf_m = st.segmented_control("How to compute the factor", CF_METHODS, default=CF0["method"],
                                                    required=True, key=f"cf_m_{TK}", format_func=CF_LABEL.get,
                                                    disabled=not cf_on, help=CF_HELP[cf_m_now]) or "auto"
                        names_m = [r["combine"] for r in MCH]
                        with st.container(horizontal=True, vertical_alignment="bottom"):
                            refs = ["auto"] + names_m
                            cf_ref = st.selectbox("Reference combine", refs,
                                                  index=refs.index(CF0["reference"]) if CF0["reference"] in refs else 0,
                                                  key=f"cf_ref_{TK}", disabled=not cf_on,
                                                  format_func=lambda m: "auto (the most kept readings)" if m == "auto"
                                                  else m)
                            cf_max = st.number_input("Max factor (%)", 1.0, 50.0, CF0["max_pct"], 1.0,
                                                     key=f"cf_max_{TK}", disabled=not cf_on,
                                                     help="A proven difference larger than this is reported but not "
                                                          "applied, unless the grower's weight confirms it (with "
                                                          "'Validate and adjust the yields' only).")
                        # 'Validate only' changes nothing in the clean file: the weight then confirms no factor (the
                        # engine reports the factor it would confirm)
                        g_use_now = ss.get(f"gw_use_{TK}") or (ss.grower.get(ss.active) or {}).get("use") or "validate"
                        cf_tc = st.toggle("The grower's weight may confirm a factor above the max",
                                          value=CF0["ticket_confirms"], key=f"cf_tc_{TK}", disabled=not cf_on,
                                          help="With 'Validate and adjust the yields': applied when the monitor total "
                                               "with the factor closes with the grower's weight (within 1 %) and "
                                               "without it does not (more than 3 %). With 'Validate only' the weight "
                                               "confirms nothing; the Combines tab says which factor it would "
                                               "confirm.")
                        if cf_on and cf_tc and g_use_now != "adjust":
                            st.caption("Validate only: the grower's weight confirms no factor (it is compared, never "
                                       "applied).")
                        st.dataframe(pd.DataFrame(MCH), hide_index=True,
                                     column_config={"readings": st.column_config.NumberColumn(format="%d"),
                                                    "mean dry yield (bu/ac)": st.column_config.NumberColumn(
                                                        format="%.2f")})
                    with c_r:
                        seam_box = st.container()        # filled after the cleaning of this run (below)
            ss.cfset[ss.active] = {"on": bool(cf_on) and len(MCH) >= 2, "method": cf_m, "reference": cf_ref,
                                   "max_pct": float(cf_max), "ticket_confirms": bool(cf_tc)}

    save_requested()                     # Save: every setting of the file on screen is read in this run by now
    many = False
    with st.container(horizontal=True, key="run_go_box"):
        with st.container(key="run_go_2"):
            one = st.button(f"Clean {ss.active}", type="primary", icon=":material/cleaning_services:", key="clean_one")
        if len(DS) > 1:
            many = st.button(f"Clean all {len(DS)} files", icon=":material/done_all:", key="clean_all",
                             help="Each file with its own import, boundary and grower's data.")
    todo = [ss.active] if one else (list(DS) if many else [])
    # every file's SMS default brought up to date first, as step 1 does for the file on screen (a raw file of an
    # earlier version decoded again from its raw data, a default whose file changed made again; the same rules set a
    # cleaning aside), so that no file is cleaned on an older import and that cleaning then set aside
    pre_notes = {}
    for t in todo:
        if default_needs_build(t):
            with st.spinner(f"Preparing SMS's default import of {t} ..."):
                pre_notes[t] = ensure_default(t)
    done = []
    for t in todo:
        with st.status(f"SMS 3-sigma on {t} ...", expanded=True) as status:
            lines_ = []

            def log_(m, _s=status, _l=lines_):
                _l.append(str(m))
                _s.text(m)
            if pre_notes.get(t):
                log_(f"{t}: {pre_notes[t]}")
            try:
                ss.cleaned[t] = clean_one(t, sset if t == ss.active else sset_for(t), log=log_)
                forget_work_msg(t)                                   # its 'clean it again' of the opened work
                R = ss.cleaned[t]["R"]
                n_rd = int(R.get("n_read") or R["n_in"])
                inside = n_rd > R["n_in"] and bool(ss.cleaned[t].get("boundary"))
                lab_ = (f"{t}: {n_rd:,} readings" + (f", {R['n_in']:,} inside the boundary" if inside else "")
                        + f" → {R['n_kept']:,} kept ({R['removed_pct']:.2f} % removed)")
                status.update(label=lab_, state="complete", expanded=False)
                done.append({"label": lab_, "log": lines_[-400:]})
            except FileInUse as e:                                   # a file to close, or another tab: one line
                status.update(label=f"{t}: not cleaned", state="error")
                st.error(str(e), icon=":material/lock:")
            except ValueError as e:                                  # a plain reason (settings, a field too large)
                status.update(label=f"{t}: not cleaned", state="error")
                if raised_by_oced(e):
                    st.error(f"{t}: {e}", icon=":material/error:")
                else:                                                # numpy / pandas ...: a defect, with its trace
                    st.exception(e)
            except Exception as e:                                   # shown, never swallowed
                status.update(label=f"{t}: the cleaning failed", state="error")
                st.exception(e)
    if todo and any(t in ss.cleaned for t in todo):
        save_current(quiet=True)
    if todo and len(done) == len(todo):
        # every file cleaned: the page again, its settings folded into one line, the status of each file under Clean
        ss["clean_status"] = done
        st.rerun()
    for s_ in ss.pop("clean_status", None) or []:
        with st.status(s_["label"], state="complete", expanded=False):
            st.text("\n".join(s_["log"]) or " ")
    if seam_box is not None:
        with seam_box:
            seams_panel(ss.cleaned.get(ss.active))
    C = ss.cleaned.get(ss.active)
    if C and not os.path.exists(C["shp"]):
        st.warning(f"The clean shapefile of this file is no longer at {C['shp']}: clean it again.",
                   icon=":material/sync_problem:")
    if C and os.path.exists(C["shp"]):
        R = C["R"]
        A3 = C.get("kind") == "a3"
        if C.get("clean_again"):
            st.warning(f"This cleaning was {C['clean_again']}" if C["clean_again"].startswith("made by") else
                       f"This cleaning: {C['clean_again']}", icon=":material/sync_problem:")
        if C.get("config") != file_config(ss.active, sset):
            st.warning("The settings, the boundary or the grower's data changed since this file was cleaned: clean it "
                       "again to apply them.", icon=":material/sync_problem:")
        M3 = R.get("sms3sigma") or {}
        L = R.get("level") or {}
        CL = L.get("closure") or {}
        # ---- the strip of the result, the clean map right under it (its statistics at its side)
        result_strip(ss.active, C)
        cols_clean = read_points(C["shp"], mtime(C["shp"])).columns
        ycol0 = (R.get("columns") or {}).get("yield") or "Yld_Vol_Dr"
        ycol0 = ycol0 if ycol0 in cols_clean else ("Yld_Vol_Dr" if "Yld_Vol_Dr" in cols_clean else None)
        corr = None if A3 else corrected_column(C, cols_clean, ycol0)
        explorer(C["shp"], key=f"clean_{key_of(C['shp'])}", height=520, default=(R["main"] if A3 else ycol0),
                 base_for={corr[0]: ycol0} if (corr and ycol0) else None,
                 labels={corr[0]: f"Final yield ({corr[0]})"} if corr else None,
                 col_help={corr[0]: corr[1]} if corr else None,
                 outline=C["boundary"]["outline"] if C.get("boundary") else None, extras=False,
                 data="clean (step 3)")
        # ---- the details, in tabs
        RM = R.get("machines") if not A3 else None
        tab_names = ((["Yield path"] if not A3 else []) + ["Steps", "Limits", "Removed points"]
                     + (["Grower's data"] if L else []) + (["Combines"] if RM else []))
        tabs_ = dict(zip(tab_names, st.tabs(tab_names, key="res_tab")))
        if not A3:
            with tabs_["Yield path"]:
                yield_path_box(ss.active, C)
                eff_ = step_effects(ss.active, C)
                if eff_:
                    st.markdown("**How each step moved the dry yield** (bu/ac)",
                                help="How much the mean (SMS Edit Legend) or the average (SMS summary, total / area) "
                                     "moved when each step removed its readings; together they make the cleaning's "
                                     "change. S2 also narrows the overlapping strips: their bu/ac rise, their area "
                                     "falls.")
                    st.dataframe(pd.DataFrame([{"step": e["label"], "readings removed": e["removed"],
                                                "mean after": e["mean"], "change of the mean": e["d_mean"],
                                                "average after (SMS)": e["avg"], "change of the average": e["d_avg"]}
                                               for e in eff_]), hide_index=True,
                                 column_config={"readings removed": st.column_config.NumberColumn(format="%d"),
                                                "mean after": st.column_config.NumberColumn(format="%.2f"),
                                                "change of the mean": st.column_config.NumberColumn(format="%+.2f"),
                                                "average after (SMS)": st.column_config.NumberColumn(format="%.2f"),
                                                "change of the average": st.column_config.NumberColumn(
                                                    format="%+.2f")})
        with tabs_["Steps"]:
            st.markdown("**The steps of this cleaning**",
                        help=("S1 runs first here: the readings outside the boundary are set aside before S0, so the "
                              "monitor total that the grower's weight is compared with is the field's. SMS clips "
                              "after its import check; the points kept are the same.")
                        if (C.get("boundary") and not A3) else None)
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
            # the numbers before the long criterion, which wraps in its own width (rows taller than 4rem wrap)
            st.dataframe(steps_df[["filter", "name", "on", "removed", "remaining", "criterion"]], hide_index=True,
                         row_height=66, column_config={"filter": st.column_config.TextColumn(width=50),
                                                       "name": st.column_config.TextColumn(width=190),
                                                       "on": st.column_config.CheckboxColumn(width=40),
                                                       "removed": st.column_config.NumberColumn(width=80),
                                                       "remaining": st.column_config.NumberColumn(width=90),
                                                       "criterion": st.column_config.TextColumn(width=440)})
            if not A3:
                sw = M3.get("swath") or {}
                bias = {str(k): float(v) for k, v in (sw.get("lateral_bias_ft") or {}).items() if v is not None}
                moved = {str(k): float(v) for k, v in (sw.get("lateral_bias_moved_ft") or {}).items() if v}
                n_sp = int(sw.get("swath_passes") or 1)
                st.caption(" · ".join(x for x in (
                    f"S1 clipped {clipped_of(C):,}" if C.get("boundary") else "",
                    f"S2 narrowed {int(sw.get('n_narrowed') or 0):,}" + (f" over {sw['scope']}" if sw.get("scope")
                                                                          else ""),
                    f"{n_sp} passes of Clip + Optimize Swath Widths" if n_sp > 1 else "") if x),
                    help="S2 narrows the readings whose strip overlapped ground already cut to the new strip and "
                         "scales their per-area values (mass kept)."
                         + (f" Order of the readings: {sw['order']}." if sw.get("order") else "")
                         + (" Lateral offset of the logged points from the centre of the strip cut: "
                            + ", ".join(f"{k} {v:+.2f} ft" for k, v in bias.items()) + "." if bias else "")
                         + (" Moved back before S2: " + ", ".join(f"{k} {v:+.2f} ft" for k, v in moved.items())
                            + "." if moved else ""))
            # the other warnings of the cleaning (S2's lateral offset, readings without a value, a file too spread
            # out ...); the grower's weight and the limits tabs show theirs
            W_ = [w for w in R.get("warnings") or [] if str(w).startswith("input: ") or not (
                "ticket" in w.lower() or "level" in w.lower() or "group" in w.lower() or "S5a" in w)]
            # the decoder's own warnings are shown once, under 'What the decoder reported' of step 1
            W_dec = [w for w in W_ if str(w).startswith("decoder: ")] if D.get("report") else []
            for w in W_:
                if w not in W_dec:
                    st.warning(w, icon=":material/warning:")
            if W_dec:
                st.caption(f"The decoder's {len(W_dec)} warning(s) are under 'What the decoder reported' (step 1).")
        with tabs_["Limits"]:
            steps = R.get("steps") if A3 else ((R.get("sms3sigma") or {}).get("steps") or [])
            if steps:
                st.markdown("**Limits per step**",
                            help="Mean and SD of the points still alive before each step, and the limits typed into "
                                 "Filter Data (mean ± k SD, rounded to 2 decimals); a reading without a value of the "
                                 "attribute is not removed by that step.")
                grp = str(((R if A3 else (R.get("sms3sigma") or {})).get("grouping") or {}).get("rule", ""))
                st.caption(("Grouping: " + grp if grp else "")
                           + (("; " if grp else "") + "order of the filters: "
                              + str(sms.FILTER_ORDER_LABELS.get(step_order(R), step_order(R))) if not A3 else ""))
                cols = [c for c in ["group", "step", "attribute", "n_before", "mean", "sd", "lo", "hi", "unit",
                                    "removed", "n_after", "sd_drop_pct", "no_value"] if c in pd.DataFrame(steps)]
                st.dataframe(pd.DataFrame(steps)[cols], hide_index=True,
                             column_config={"mean": st.column_config.NumberColumn(format="%.3f"),
                                            "sd": st.column_config.NumberColumn(format="%.3f"),
                                            "lo": st.column_config.NumberColumn("low", format="%.2f"),
                                            "hi": st.column_config.NumberColumn("high", format="%.2f"),
                                            "sd_drop_pct": st.column_config.NumberColumn("SD drop %", format="%.2f"),
                                            "no_value": st.column_config.NumberColumn(
                                                "without a value (kept by this step)", format="%d")})
                IMX = None if A3 else (R.get("sms3sigma") or {}).get("import_max")
                if IMX and IMX.get("groups"):
                    mx_txt = ("no maximum" if IMX.get("max_yield") is None else
                              f"{float(IMX['max_yield']):,.2f} bu/ac")
                    src_txt = SOURCE_LABEL.get(str(IMX.get("max_yield_source")), IMX.get("max_yield_source")) or ""
                    st.markdown(f"**Import maximum {mx_txt}**" + (f" ({src_txt})" if src_txt else "")
                                + f"; left out at import: {int(IMX.get('left_out') or 0):,}",
                                help="Next to each group's S5a: the readings the import's maximum left out before the "
                                     "cleaning. A maximum below the S5a high limit cut readings the 3-sigma step would "
                                     "have kept; with the readings left out and one yield pass, the SD of S5a would be "
                                     "larger. A warning is given only for a maximum you typed.")
                    st.dataframe(pd.DataFrame([{
                        "group": g["group"], "S5a high (bu/ac)": g.get("s5a_hi"),
                        "left out by the import maximum": g.get("left_out"), "yield passes": g.get("passes"),
                        "maximum below the S5a high": bool(g.get("max_below_s5a_hi")),
                        "one pass after readings left out": bool(g.get("one_pass_after_left_out"))}
                        for g in IMX["groups"]]), hide_index=True,
                        column_config={"S5a high (bu/ac)": st.column_config.NumberColumn(format="%.2f")})
                for w in [w for w in R.get("warnings") or [] if ("group" in w.lower() or "S5a" in w)
                          and "ticket" not in w.lower() and not str(w).startswith("input: ")]:
                    st.warning(w, icon=":material/warning:")
        with tabs_["Removed points"]:
            fl = C.get("flagged_shp")
            if fl and os.path.exists(fl):
                st.markdown("**Removed points**",
                            help="Every reading of the file: kept in green (faint), the removed ones in the colour of "
                                 "the step that removed them."
                                 + (" The readings outside the boundary (S1) are not drawn; the cyan line is the "
                                    "boundary." if C.get("boundary") else ""))
                F_ = read_points(fl, mtime(fl))
                rb = F_["Rem_By"].astype(str).str[:2]
                grp = np.where(pd.to_numeric(F_["Keep"], errors="coerce").to_numpy(float) == 1, "kept", rb)
                rows = np.flatnonzero(np.isfinite(F_["lon"].to_numpy()) & np.isfinite(F_["lat"].to_numpy()))
                if len(rows) > MAP_N:
                    rows = np.sort(np.random.default_rng(0).choice(rows, MAP_N, replace=False))
                g = grp[rows]
                rowby = {str(r["filter"])[:2]: r for r in R.get("cascade") or []}
                colour = {k: (STEP_COLORS["kept"] if k == "kept" else
                              (STEP_COLORS.get(k, "#FF8F00") if A3 else step_color(k, rowby.get(k), R)))
                          for k in set(grp)}
                cols_ = [colour.get(x, "#FF8F00") for x in g]
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
                # the record's own row names (a cleaning made speed first keeps its names)
                names = {str(r["filter"])[:2]: str(r.get("name") or "").split(", pass")[0] for r in R["cascade"]}
                st.html('<div style="display:flex;flex-wrap:wrap">' + "".join(
                    f'<span style="display:inline-flex;align-items:center;gap:6px;margin:2px 14px 2px 0;'
                    f'font-size:0.86rem"><span style="width:12px;height:12px;border-radius:50%;'
                    f'background:{colour.get(k, "#FF8F00")};border:1px solid #1F2937"></span><b>'
                    f'{html.escape("kept" if k == "kept" else k + " " + names.get(k, ""))}</b> {int(n):,} points</span>'
                    for k, n in vc.items()) + "</div>")
        if L:
            with tabs_["Grower's data"]:
                # one stated area for the per-acre rows: the area harvested (every strip once), else the swept one
                area = float(L.get("monitor_area_ac") or L.get("export_area_ac") or 0)
                area_src = L.get("monitor_area_source") or "the area the readings swept"
                harm = bool(L.get("combine_factor_changed_total"))
                mon = float(L.get("monitor_total_final_bu", L["export_total_bu"]))   # after the combine factor
                gro = float(L["scale_ticket_bu"])
                # a grower's yield per acre: both means over the grower's acres, so the grower's column shows the
                # figure given and the monitor's is its total over the same acres
                area_y = float(L.get("ticket_area_ac") or 0) if L.get("ticket_unit") == "bu/ac" else area
                pct = (lambda m, g: f"{100 * (m / g - 1):+.2f} %" if g else "—")
                basis_txt = ("at the standard moisture" if L.get("ticket_bu_at_standard") is not None or
                             str(L.get("comparison_basis") or "").startswith("dry") else "as delivered")
                icol = L.get("integral_column")
                rows_v = [{"": f"Total (bu, {basis_txt}" + (f"; {icol}" if icol else "")
                               + ("; after the combine factor" if harm else "") + ")",
                           "monitor": f"{mon:,.0f}", "grower": f"{gro:,.0f}", "monitor vs grower": pct(mon, gro)}]
                if harm:
                    rows_v.append({"": "Total as logged, before the combine factor (bu)",
                                   "monitor": f"{float(L['export_total_bu']):,.0f}", "grower": f"{gro:,.0f}",
                                   "monitor vs grower": pct(float(L["export_total_bu"]), gro)})
                if area_y > 0:
                    lab = f"Mean yield (bu/ac, {basis_txt}" + (f", over {area_y:,.2f} ac)" if area_y != area else ")")
                    rows_v.append({"": lab, "monitor": f"{mon / area_y:,.2f}", "grower": f"{gro / area_y:,.2f}",
                                   "monitor vs grower": pct(mon, gro)})
                lb_mon = L.get("export_total_harmonised_lb") if harm else None
                lb_mon = float(lb_mon if lb_mon is not None else (L.get("export_total_lb") or 0))
                if L.get("ticket_lb") and lb_mon and L.get("ticket_basis") == "wet":
                    rows_v.append({"": "Total weight as delivered (lb)", "monitor": f"{lb_mon:,.0f}",
                                   "grower": f"{L['ticket_lb']:,.0f}", "monitor vs grower": pct(lb_mon, L["ticket_lb"])})
                st.dataframe(pd.DataFrame(rows_v), hide_index=True)
                band = CL.get("band", "")
                tone = ("#E8F7F0", "#00784D") if band in ("<= 1 %", "1-3 %") else (
                    ("#FFF5E5", "#9A5B00") if band == "3-10 %" else ("#FDECEC", "#B42318"))
                st.html(f'<div class="oced-verdict" style="background:{tone[0]};border-color:{tone[1]};color:#1F2937">'
                        f'<b style="color:{tone[1]}">L = {html.escape(er.level_factor_text(L))} · band '
                        f'{html.escape(band)}</b><br>{html.escape(CL.get("verdict", ""))}</div>')
                facts = [f"Compared on the {L.get('comparison_basis') or L.get('basis')} basis, over the "
                         f"{area:,.2f} ac of {area_src}"
                         + (" inside the boundary" if C.get("boundary") else "") + "."]
                if any(r[""].startswith("Total weight") for r in rows_v) and L.get("ticket_bu_at_standard") is not None:
                    facts.append("The weights as delivered also differ by the moisture of the grain: the verdict "
                                 "compares both at the standard moisture.")
                if L.get("ticket_caption"):
                    facts.append("Grower's weight: " + str(L["ticket_caption"]) + ".")
                if L.get("ticket_bu_at_standard") is not None:
                    facts.append(f"At {L['ticket_moisture_pct']:g} % grain moisture: {L['ticket_bu']:,.0f} bu as "
                                 f"delivered = {L['ticket_bu_at_standard']:,.0f} bu at the standard moisture.")
                if L.get("test_weight_used") and not L.get("ticket_caption"):
                    facts.append(f"Bushel weight {L['test_weight_used']:.2f} lb/bu ({L.get('test_weight_source')}).")
                if L.get("test_weight_grower") and not L.get("grower_bushels_applied"):
                    facts.append(f"The grower's bushel weight {float(L['test_weight_grower']):.2f} lb/bu is reported: "
                                 "the comparison is in the file's bushels"
                                 + (f" ({float(L['test_weight_used']):.2f} lb/bu)" if L.get("test_weight_used") else "")
                                 + (f"; in the grower's bushels the weight is {float(L['ticket_bu_grower']):,.0f} bu"
                                    if L.get("ticket_bu_grower") else "") + ".")
                facts.append("Adjusted: Yld_Level = the dry yield x the combine factor x L is in the clean file (map "
                             "it to use the grower's level); the monitor's columns stay as logged." if C.get("adjusted")
                             else "Validation only: the clean file keeps the monitor's yields (no Yld_Level) and the "
                                  "weight confirmed no combine factor. Choose 'Validate and adjust the yields' and "
                                  "clean again to add the adjusted column.")
                lcol = "Yld_Lvl_Sy" if R.get("yield_column_for_difm") == "Yld_Lvl_Sy" else "Yld_Level"
                gap = L.get("yld_lvl_sy_vs_ticket_pct" if lcol == "Yld_Lvl_Sy" else "yld_level_vs_ticket_pct")
                if C.get("adjusted") and gap is not None and abs(float(gap)) > 0.05:
                    facts.append(f"{lcol} of every processed reading sums to {float(gap):+.2f} % of the weight "
                                 "compared (a wet weight without its moisture is compared with the wet yield, while "
                                 "the dry yield is leveled).")
                CSg = L.get("card_summary")
                if isinstance(CSg, dict) and CSg.get("readings_wet_lb") and CSg.get("summary_wet_lb"):
                    facts.append(f"Case IH / New Holland card: the readings hold {float(CSg['readings_wet_lb']):,.0f} "
                                 f"lb wet against the card's own Summary {float(CSg['summary_wet_lb']):,.0f} lb (what "
                                 "SMS shows for it): L against the Summary about "
                                 f"{float(CSg.get('factor_against_summary') or 0):.4f} (an estimate: L x the card's "
                                 "readings / its Summary, the gap taken as even over the card, whose Summary also "
                                 "holds the readings outside the boundary). L above is against the readings, so "
                                 "Yld_Level sums to the grower's weight.")
                st.caption(facts[0])
                if len(facts) > 1:
                    with st.expander("How this works", type="compact"):
                        for f_ in facts[1:]:
                            st.caption(f_)
                if C.get("adjusted") and gap is not None and abs(float(gap)) > 0.1:
                    st.warning(f"{lcol} does not sum to the grower's weight: {float(gap):+.2f} % (give the grain "
                               "moisture of a wet weight, or the weight at the standard moisture, to level the dry "
                               "yield to it).", icon=":material/warning:")
                for w in [w for w in R.get("warnings") or [] if ("ticket" in w.lower() or "level" in w.lower())
                          and not str(w).startswith("input: ")]:
                    st.warning(w, icon=":material/warning:")
        if RM:
            with tabs_["Combines"]:
                fa = RM.get("factor_applied") or {}
                means = RM.get("means") or {}
                light = RM.get("light") or {}
                used = RM.get("method_used") or {}
                lay = RM.get("layout_class") or {}
                rows_c = []
                for m in sorted(set(fa) | set(means)):
                    mm = means.get(m) or {}
                    lc = lay.get(m) or {}
                    rows_c.append({"combine": m, "readings": mm.get("n"), "kept": mm.get("n_kept"),
                                   "mean cleaned (bu/ac)": mm.get("cleaned_map_mean"), "factor": fa.get(m),
                                   "method": used.get(m) or ("reference" if m == RM.get("reference") else ""),
                                   "layout": (lc.get("local") or "") if isinstance(lc, dict) else str(lc),
                                   "light": {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(light.get(m), ""),
                                   "decision": (RM.get("decision") or {}).get(m, "")})
                on_ = bool(((R.get("settings") or {}).get("machines") or {}).get("harmonise"))
                st.markdown("**The combine factor of this cleaning**: " + ("switched on" if on_ else
                                                                           "switched off (every factor 1)"),
                            help=f"Combines from {RM.get('basis') or 'the data'}; reference "
                                 f"{RM.get('reference') or '-'}. Layout = how the combine shared the field with the "
                                 "reference (interleaved, mixed, blocks); light = how far the method can be trusted "
                                 "on that layout.")
                st.dataframe(pd.DataFrame(rows_c), hide_index=True,
                             column_config={"readings": st.column_config.NumberColumn(format="%d"),
                                            "kept": st.column_config.NumberColumn(format="%d"),
                                            "mean cleaned (bu/ac)": st.column_config.NumberColumn(format="%.2f"),
                                            "factor": st.column_config.NumberColumn(format="%.4f"),
                                            "decision": st.column_config.TextColumn(width="large")})
                FO_ = factor_outcome(R)
                if FO_ is not None and not FO_["applied"]:
                    factor_outcome_box(R)
                SMx = RM.get("seams") or {}
                if SMx.get("text"):
                    st.caption(SMx["text"])
        explorer_extras(C["shp"])
    if ss.cleaned:
        brand.next_step(4, "Clean files and reports")

# ------------------------------------------------------------------------------------------------ 4 clean files
with st.container(border=True, key="oced_step_4"):
    brand.step_header(4, "Clean files and reports",
                      "The clean shapefile, the file for DIFM and the report of each cleaned file")
    if not ss.cleaned:
        st.info("Clean a file in step 3: its clean shapefile appears here.", icon=":material/info:")
    else:
        kinds = {"a3" if c.get("kind") == "a3" else "harvest" for c in ss.cleaned.values()}
        flagged = "; ".join(
            (["for a harvest file every reading inside the boundary (the readings S1 clipped are not in it: their "
              "number is in step 3)"] if "harvest" in kinds else [])
            + (["for a planter or sprayer file every reading, the clipped ones with Rem_By S1"] if "a3" in kinds
               else []))
        with st.expander("What each file is", type="compact", icon=":material/help:"):
            st.caption("Clean shapefile = the kept readings with every attribute of the file, inside the field boundary "
                       "when one was given. A harvest file is written as SMS exports it after Optimize Swath Widths (the "
                       "narrowed readings carry their new width and scaled per-area values; Wdth_Raw and Swath_Scl "
                       "added; with the yields adjusted, also Yld_Level, the dry yield leveled to the grower's weight). "
                       "Removed % = of the readings inside the boundary. Flagged = the readings with Keep and the step "
                       f"that removed each (Rem_By): {flagged}. "
                       "Report = the steps, the limits, the statistics and the maps (PDF). Save the clean file "
                       "as = the same clean readings in the raw format they were imported from (or ISOXML), to read "
                       "into SMS as monitor data: not yet tested in SMS. The files are also in the work folder: "
                       + os.path.join(ss.workdir or "", "clean_shapefiles") + " and "
                       + os.path.join(ss.workdir or "", NATIVE_DIR) + ". A Case IH card written also adds its folder "
                       "name to " + os.path.join(WORKSPACE, "cn1_card_names.json") + ", the list of the card names "
                       "written in this workspace (outside the work folder, so that no name is given twice).")
        rows = []
        for t, c in ss.cleaned.items():
            R = c["R"]
            Lc = R.get("level") or {}
            rows.append({"file": t, "import": cleaning_import_word(t), "readings in": R.get("n_read") or R["n_in"],
                         "clipped (S1)": clipped_of(c) if c.get("boundary") else None,
                         "kept": R["n_kept"], "removed (%)": R["removed_pct"],
                         "cleaned on": (", ".join(R["attributes"]) if c.get("kind") == "a3" else "SMS S0-S5"),
                         "monitor vs grower (%)": (Lc.get("closure") or {}).get(
                             "diff_final_pct", (Lc.get("closure") or {}).get("diff_pct")),
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
                                    "clipped (S1)": st.column_config.NumberColumn(format="%d"),
                                    "import": st.column_config.TextColumn(
                                        help="The import the cleaning started from (step 2): SMS's default, your "
                                             "settings, the file as it is or as the monitor logged it.")})
        zp = all_clean_zip()
        if zp and len(ss.cleaned) > 1:
            download(f"All {len(ss.cleaned)} clean shapefiles (.zip)", zp, "application/zip", key="dl_all",
                     primary=True, icon=":material/folder_zip:")
        for t, c in ss.cleaned.items():
            st.markdown(f"**{t}**")
            row4 = st.container(horizontal=True)             # the downloads, filled once the yield is chosen
            adj4 = difm_question(t, c)                       # asked only when the cleaning adjusted the yield
            Wd = difm_of(t, c)
            with row4:
                download("Clean shapefile (.zip)", c["zip"], "application/zip", key=f"dl_clean_{t}", primary=True,
                         icon=":material/cloud_download:")
                if Wd and Wd.get("zip"):
                    download("Shapefile for DIFM (.zip)", Wd["zip"], "application/zip", key=f"dl_difm_{t}",
                             icon=":material/upload_file:")
                download("Flagged points (.zip)", c.get("flagged_zip"), "application/zip", key=f"dl_flag_{t}")
                download("Report (PDF)", c.get("report_pdf"), "application/pdf", key=f"dl_pdf_{t}",
                         icon=":material/picture_as_pdf:")
                download("Cleaning record (JSON)", c.get("json"), "application/json", key=f"dl_json_{t}",
                         icon=":material/data_object:")
            if Wd and Wd.get("zip"):
                if c.get("kind") == "a3":
                    st.caption("For DIFM: its own columns and dates; the rate's unit is chosen in DIFM",
                               help="The same clean readings with their own columns and their dates as dBASE dates, "
                                    "as SMS's as-applied exports carry them, in WGS 84; the rate's unit is chosen in "
                                    "DIFM's Define Features. Not yet tried on DIFM.")
                    with st.expander("About the file for DIFM", type="compact"):
                        st.caption(f"Shapefile for DIFM ({os.path.basename(Wd['zip'])}): the same clean readings with "
                                   "its own columns and its dates as dBASE dates, as SMS's as-applied exports carry "
                                   "them, in WGS 84 (the rate's unit is chosen in DIFM's Define Features); not yet "
                                   "tried on DIFM. The clean shapefile keeps its columns as they are.")
                else:
                    oth4 = ed.zip_path_for(c["shp"], Wd.get("yield") != "adjusted")
                    st.caption("For DIFM: Yld_Vol_Dr as the yield; swath and moisture mapped · "
                               + ed.yield_label(Wd.get("yield") or "monitor", adj4),
                               help="In DIFM's Define Features map Yld_Vol_Dr (or Yld_Mass_D, the same yield by mass) "
                                    "as the yield, Swth_Wdth_ as the swath width and Moisture__ as the moisture. What "
                                    "the file holds: About the file for DIFM.")
                    with st.expander("About the file for DIFM", type="compact"):
                        st.caption(f"Shapefile for DIFM ({os.path.basename(Wd['zip'])}): "
                                   + (Wd.get("line") or ed.yield_line(Wd.get("yield") or "monitor", adj4)) + ". The "
                                   "same clean readings in the layout of an SMS shapefile export, the layout DIFM "
                                   "reads (Yld_Mass_D, Yld_Vol_Dr, Track_deg_, Distance_f, Elevation_, Moisture__, "
                                   "Y_Offset_f, Speed_mph_, Time = the date of each reading, Swth_Wdth_), its numbers "
                                   "with 6 decimals; a field the clean file does not hold is filled only with what "
                                   "follows exactly from it and from the file's import (mass = volume x the import's "
                                   "lb/bu), else left empty; the clean shapefile keeps every column."
                                   + (f" The file of the other choice, {os.path.basename(oth4)}, was written too and "
                                      "stays in the folder." if (adj4 and os.path.isfile(oth4)
                                                                 and mtime(oth4) >= mtime(c["shp"])) else ""))
                for w in Wd.get("warnings") or []:
                    st.warning(f"Shapefile for DIFM: {w}.", icon=":material/warning:")
            elif Wd and Wd.get("blocked"):
                st.info(f"Shapefile for DIFM: not offered until the file is cleaned again (this cleaning: "
                        f"{Wd['blocked']}).", icon=":material/sync_problem:")
            elif Wd is not None:
                err = str(Wd.get("error") or "")
                held = "WinError 5" in err or "WinError 32" in err or "Permission denied" in err
                zp4 = None if c.get("kind") == "a3" else ed.zip_path_for(c["shp"], c.get("difm_yield") == "adjusted")
                if zp4 and not held and len(os.path.abspath(zp4)) > WIN_PATH_MAX:
                    st.warning(_long_path_msg(zp4, "The shapefile for DIFM")       # a work folder too deep for the name
                               + " The clean shapefile is not affected.", icon=":material/warning:")
                else:
                    st.warning("The shapefile for DIFM could not be written"
                               + (": its zip is open in another program (close it, then write it again)"
                                  if held else "")
                               + f": {err}. The clean shapefile is not affected.", icon=":material/warning:")
                st.button("Write it again", key=f"difm_retry_{t}", on_click=retry_difm, args=(t,),
                          icon=":material/refresh:", help="Once the file is no longer held open by another program.")
            native_block(t, c)

# ------------------------------------------------------------------------------------------------ action tree
end_of_page()
