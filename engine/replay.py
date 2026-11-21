# -*- coding: utf-8 -*-
"""Harvest replay: the readings of a yield file played back on a map, combine by combine, as they were logged.

    from engine import replay
    P = replay.replay_payload(shp, outline=rings)          # the data of the player (a dict, JSON-ready)
    html = replay.replay_html(P)                           # one self-contained HTML document (a string)

    python -m engine.replay <shapefile or zip> [--boundary FILE] [--raw FOLDER] [--make COMBINE=MAKE] --out replay.html
    python -m engine.replay <shapefile or zip> --zones ZONE_MAP [--zone-column NAME] [--zone-csv zone_yield.csv] --out ...

With a management zone map (engine/zones.py: a polygon file the user made elsewhere, OCED never builds one) the player
also shows the zones, the yield of each zone while the combines harvest and, at the end, whether the zones agree with
the yield; zone_yield.csv holds the table.

It reads data only: nothing here changes a calculation or a file of the import or of the cleaning.

What it plays (replay_payload):
- the readings of a point file: an import (decoded raw data or a point export, step 1 / 2 of the app) or the flagged
  file of a cleaning (every reading with Keep and the step that removed it, Rem_By);
- per combine (the Machine column; one combine when the file has none) the time of each reading, its position, the
  direction of travel, the swath width, the lateral offset, the distance travelled, dry yield, moisture and speed,
  and (a cleaning) kept / removed with the step;
- the ground each reading covered is the app's own strip (yield_clean.swept_strips, the geometry of the app's maps:
  the header line at the previous reading of the same sequence to the header line at this one, or a rectangle
  Distance back along the travel); an SMS 3-sigma output (Swath_Scl in the file) is drawn as SMS draws it
  (swath_quads: a rectangle Distance back along the logged heading, centred on the point). The player rebuilds each
  strip from the reading's position, direction, width, offset, distance and a link bit, by the same rule.

Time (reading_times): the readings' own clock (the Time column with a time of day), John Deere decoders' UTC and times
that carry their zone (an Operations Center IsoTime) shown in this computer's clock time; the combines are synchronised on that clock. A file without a time of day: each
dataset's start time when every dataset name carries one ('YY/MM/DD-HH:MM:SS', the SMS / CNH dataset name) plus the
readings' durations; else the file order with each reading's duration, one reading after the other (combines are
then NOT shown working together). The player says which. No clock time is ever made up.

Idle time: a gap of more than IDLE_GAP_S between two readings of a combine breaks its activity; a time when no combine
works for more than IDLE_SKIP_S is skipped in playback when 'skip idle time' is on (the clock keeps the real time).

Size: every column is quantised (positions 1e-7 deg, about 1 cm; direction 0.1 deg; width, offset and distance 1 cm;
yield 0.1 bu/ac; moisture and speed 0.01), delta coded and written as zig-zag LEB128 varints in base64: about 12 bytes
a reading, 130,000 readings in about 2 MB. Above max_bytes the readings are thinned (every k-th of each combine, the
distance of the readings skipped added to the one kept), and the player says so.

The make of a combine (make_of): a John Deere display log (.jdl, a GreenStar 3 card) whose serial is a John Deere PIN
(1H0...) is a John Deere; a Case IH / New Holland card tells the make in its combine folder (COMBINES/<id>/<id>.agp:
'Axial Flow ...' = Case IH, 'New Holland CR' = New Holland) and in its display logs ('vehicle_brand: 0x1' = Case IH,
'0x2' = New Holland), read by make_hints(raw folder); ISOXML and point exports from their machine text. Nothing that
tells: the app's own colours (navy, light blue). The caller can set the make of any combine.

Edits by hand (a cleaning, engine/clean/manual_edits.py): the payload of a flagged file carries, for the card of a
reading, the values the filters compared (yf: the dry yield x Swath_Scl of S5; sf: the speed after the swath step of
S4; wl: the logged width when the strip is drawn with the narrowed one), the limits of each combine (P['limits'],
from the cleaning record) and, after a cleaning with an edits file, each reading's mark (e: removed by hand, kept by
hand, asked but not applied, its fate moved without a mark, and the step of the automatic cleaning) with the record's
summary (P['manual']). With edit=True (the app) it also carries P['edit']: whether the readings can be marked here
(every reading of the file, not thinned) and a token of the flagged file; edit_keys() turns the player's marks
(combine number, reading index) into the engine's reading keys (manual_edits.flagged_keys) and refuses a reading cut
by the import range, the clip or the swath step. Nothing here writes an edits file or runs a cleaning.
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import html as _html
import io
import json
import math
import os
import re
import sys
import zipfile

import numpy as np
import pandas as pd

from engine.clean import yield_clean

FORMAT_VERSION = 1
IDLE_GAP_S = 45.0          # a gap between two readings of one combine longer than this breaks its activity
IDLE_SKIP_S = 90.0         # a time with no combine working longer than this is skipped in playback
MAX_BYTES = 5_500_000      # the encoded readings (base64) above this are thinned
EDIT_MAX_BYTES = 16_000_000   # a cleaning replay the app can edit: every reading up to this, else no edit mode
EDIT_STATES = {"R": 1, "K": 2, "N": 3}   # Man_Edit -> the mark of the payload (0: none)
UNMARKABLE = {"S0": "cut by the import range (S0), which edits by hand cannot change",
              "S1": "cut by the clip to the boundary (S1), which edits by hand cannot change",
              "S2": "cut by the swath step (S2, Optimize Swath Widths), which edits by hand cannot change"}
FT = 0.3048
PALETTE_CAT = ["#FFC20E", "#00E5FF", "#FF4FA3", "#76FF03", "#FF8F00", "#B388FF", "#FFFFFF", "#00B373", "#FF5252",
               "#90A4AE", "#1DE9B6", "#F4FF81"]          # the app's categorical palette (app/oced.py PALETTE_CAT)
UTC_FORMATS = ("jd_jdl", "jd_gs3_rcd")                   # the decoders that write UTC times (engine/difm.py)
STEP_NAMES = {"S0": "S0 import check", "S1": "S1 clip to the boundary", "S2": "S2 Optimize Swath Widths",
              "S3": "S3", "S4": "S4", "S5": "S5 dry yield"}
_ZONED = re.compile(r"\d{2}:\d{2}(:\d{2}(\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})$")   # an ISO time with its zone
_STAMP = re.compile(r"(\d{2})/(\d{2})/(\d{2})-(\d{2}):(\d{2}):(\d{2})")

# ------------------------------------------------------------------------------------------------- makes
# Colours of each make (body, darker body, accent, trim, rims, header, reel bats, roof). Colours only: no logo, no
# name is drawn on the machine.
MAKES = {
    "john_deere": {"label": "John Deere", "body": "#367C2B", "dark": "#24561C", "accent": "#FFDE00",
                   "trim": "#1E2A1A", "rim": "#FFDE00", "header": "#367C2B", "reel": "#FFDE00", "roof": "#2E6B25"},
    "case_ih": {"label": "Case IH", "body": "#C4122F", "dark": "#8E0C21", "accent": "#1C1C1C", "trim": "#3E4246",
                "rim": "#C9CDD2", "header": "#C4122F", "reel": "#26282B", "roof": "#2A2C2F"},
    "new_holland": {"label": "New Holland", "body": "#F5C400", "dark": "#C99F00", "accent": "#0D3B8C",
                    "trim": "#3A3F45", "rim": "#D7DADD", "header": "#F5C400", "reel": "#0D3B8C", "roof": "#F7F7F2"},
    "claas": {"label": "Claas", "body": "#B5C42A", "dark": "#8C991B", "accent": "#FFFFFF", "trim": "#8A9096",
              "rim": "#D52B1E", "header": "#B5C42A", "reel": "#E9ECEF", "roof": "#FFFFFF"},
    "massey_ferguson": {"label": "Massey Ferguson", "body": "#C8102E", "dark": "#900B21", "accent": "#D3D7DB",
                        "trim": "#8A9096", "rim": "#D3D7DB", "header": "#C8102E", "reel": "#D9DCDF", "roof": "#E4E7EA"},
    "fendt": {"label": "Fendt", "body": "#2F5A2C", "dark": "#1E3D1C", "accent": "#C9CDD1", "trim": "#2A2E2A",
              "rim": "#C1121F", "header": "#2F5A2C", "reel": "#C9CDD1", "roof": "#1F2420"},
    "gleaner": {"label": "Gleaner", "body": "#B9BEC4", "dark": "#8D9399", "accent": "#1A1A1A", "trim": "#2C2F33",
                "rim": "#1A1A1A", "header": "#B9BEC4", "reel": "#1A1A1A", "roof": "#2A2D31"},
    "generic": {"label": "Make not known", "body": "#00358E", "dark": "#00255F", "accent": "#009CDE",
                "trim": "#1B2B44", "rim": "#9CC9EE", "header": "#00358E", "reel": "#009CDE", "roof": "#E8F3FB"},
}
# words in a model, vehicle or device text -> make (checked in this order, case ignored)
MAKE_WORDS = [
    ("new_holland", r"new\s*holland|\bCR\s?\d|\bCX\s?\d|\bTC\s?\d|\bNH\b"),
    ("case_ih", r"axial[\s-]*flow|\bcase\b|case\s*ih|\bAF\s?\d{3,4}\b"),
    ("claas", r"claas|lexion|tucano|trion|\bavero\b"),
    ("massey_ferguson", r"massey|\bMF\s?\d"),
    ("fendt", r"fendt"),
    ("gleaner", r"gleaner"),
    ("john_deere", r"john\s*deere|\bdeere\b|^1H0|\bS[67]\d0\b|\bX9\s?\d{3,4}\b|\bT[56]\d0\b"),
]
CNH_BRAND = {1: "case_ih", 2: "new_holland"}          # 'vehicle_brand: 0x1' in a CNH card's display log


def make_of(text: str | None = None, src_fmt: str | None = None, machine: str | None = None,
            hint: dict | None = None) -> tuple[str, str]:
    """(make key of MAKES, why) of one combine: a hint read from the raw data (make_hints) first, then its model /
    vehicle / device text, then the format (a John Deere log with a John Deere PIN). 'generic' when nothing tells."""
    if hint and hint.get("make") in MAKES:
        return hint["make"], hint.get("why") or "from the raw data"
    no_make_why = (hint or {}).get("why")
    fmt = str(src_fmt or "")
    if fmt in UTC_FORMATS and not str(text or "").strip():
        m = str(machine or "").strip().upper()
        if not m or m.startswith("1H0"):
            return "john_deere", "a John Deere display log" + (" with a John Deere serial (1H0...)" if m else "")
        return "generic", (f"logged by a John Deere display, but the serial {machine} is not a John Deere one (1H0...): "
                           "the make is not told")
    for t in (text, machine):
        s = str(t or "")
        if not s.strip():
            continue
        for key, rx in MAKE_WORDS:
            if re.search(rx, s, flags=re.I):
                if key == "john_deere" and src_fmt not in UTC_FORMATS and not re.search(r"deere|^1H0", s, re.I):
                    continue                                  # a model number alone says John Deere only on its logs
                return key, f"the machine text '{s.strip()[:40]}'"
    if fmt == "cnh_cn1":
        return "generic", "a Case IH / New Holland card that does not say which (no combine folder text read)"
    if fmt == "isoxml":
        return "generic", no_make_why or "ISOXML task data: the make is not told"
    return "generic", no_make_why or "the file does not tell the make"


def _strings(b: bytes, n: int = 4) -> list:
    return [m.group().decode("latin-1") for m in re.finditer(rb"[\x20-\x7e]{%d,}" % n, b)]


def _walk(root: str, max_files: int = 200_000):
    """(relative name, size, reader) of every file under a folder or in a zip (nested zips included)."""
    def in_zip(zf, prefix):
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.lower().endswith(".zip") and info.file_size < 2_000_000_000:
                try:
                    inner = zipfile.ZipFile(io.BytesIO(zf.read(name)))
                except Exception:                                   # noqa: BLE001 - a damaged inner zip: skipped
                    continue
                yield from in_zip(inner, prefix + name + "!")
                continue
            yield prefix + name, info.file_size, (lambda zf=zf, name=name: zf.read(name))
    if os.path.isfile(root) and root.lower().endswith(".zip"):
        with zipfile.ZipFile(root) as zf:
            yield from in_zip(zf, "")
        return
    k = 0
    for d, _, files in os.walk(root):
        for f in files:
            k += 1
            if k > max_files:
                return
            p = os.path.join(d, f)
            if f.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(p) as zf:
                        yield from in_zip(zf, os.path.relpath(p, root) + "!")
                except (OSError, zipfile.BadZipFile):
                    continue
            else:
                yield os.path.relpath(p, root), os.path.getsize(p), (lambda p=p: open(p, "rb").read())


def make_hints(root: str | None) -> dict:
    """What raw monitor data says of the make of each combine, read in place from a folder or a zip:
    {vehicle id: {"make", "model", "why"}}. A Case IH / New Holland card: the model family in
    COMBINES/<id>/<id>.agp ('Axial Flow 30 Series' -> Case IH, 'New Holland CR' -> New Holland) for that combine, else
    the 'vehicle_brand' of the card's display logs (log/*.txt: 0x1 Case IH, 0x2 New Holland) when the card names one
    brand; the key is the combine folder (the decoded Machine starts with it). ISOXML: the task controller's maker
    (TaskControllerManufacturer) for the serials of its devices. {} when nothing is found or the root is missing."""
    if not root or not os.path.exists(root):
        return {}
    cards: dict = {}                    # card prefix -> {"vehicles": {id: model}, "brands": set}
    iso: dict = {}
    n_logs = 0
    for name, size, read in _walk(root):
        low = name.replace("\\", "/").lower()
        card = low.split(".cn1/")[0] if ".cn1/" in low else ""
        if "/combines/" in "/" + low and low.endswith(".agp") and size < 2_000_000:
            vid = name.replace("\\", "/").split("/")[-2]
            model = next((s.strip() for s in _strings(read()) if re.search(r"axial|holland|\bCR\b|series", s, re.I)),
                         "")
            cards.setdefault(card, {"vehicles": {}, "brands": set()})["vehicles"][vid] = model
        elif ".cn1/" in low and "/log/" in low and low.endswith(".txt") and size < 2_000_000 and n_logs < 400:
            n_logs += 1
            for m in re.finditer(rb"vehicle_brand: 0x([0-9A-Fa-f]+)", read()):
                cards.setdefault(card, {"vehicles": {}, "brands": set()})["brands"].add(int(m.group(1), 16))
        elif ".cn1/" in low and "/combines/" in low and size == 0:
            continue
        elif low.endswith("taskdata.xml") and size < 50_000_000:
            b = read()
            tc = re.search(rb'TaskControllerManufacturer="([^"]*)"', b)
            for m in re.finditer(rb"<DVC\b[^>]*>", b):
                ser = re.search(rb'\bE="([^"]*)"', m.group())
                if ser and ser.group(1):
                    iso[ser.group(1).decode("latin-1")] = tc.group(1).decode("latin-1") if tc else ""
    out = {}
    for card, C in cards.items():
        brands = sorted(C["brands"])
        for vid, model in C["vehicles"].items():
            key, why = (None, "")
            for k, rx in MAKE_WORDS[:2]:
                if model and re.search(rx, model, re.I):
                    key, why = k, f"the card's combine folder {vid} says '{model}'"
                    break
            if key is None and len(brands) == 1 and brands[0] in CNH_BRAND:
                key, why = CNH_BRAND[brands[0]], f"the card's display logs say vehicle_brand 0x{brands[0]:X}"
            if key:
                out[vid] = {"make": key, "model": model, "why": why}
        if len(brands) == 1 and brands[0] in CNH_BRAND:      # combines of the card without a folder text
            out.setdefault(f"*{card}", {"make": CNH_BRAND[brands[0]], "model": "",
                                        "why": f"the card's display logs say vehicle_brand 0x{brands[0]:X}"})
    for ser, tc in iso.items():
        for k, rx in MAKE_WORDS:
            if tc and re.search(rx, tc, re.I):
                out[ser] = {"make": k, "model": tc, "why": f"the ISOXML task controller is '{tc}'"}
                break
        else:
            if tc:
                out[ser] = {"make": None, "model": tc, "why": f"the ISOXML task controller is '{tc}' (it does not "
                                                              "tell Case IH from New Holland)" if "cnh" in tc.lower()
                            else f"the ISOXML task controller is '{tc}'"}
    return out


def _hint_for(machine: str, hints: dict) -> dict | None:
    """The hint of a combine: its own id, the combine folder its id starts with, else a card-wide brand (one card)."""
    if not hints:
        return None
    m = str(machine or "")
    if m in hints:
        return hints[m]
    for vid, h in hints.items():
        if not vid.startswith("*") and vid and m.upper().startswith(vid.upper()):
            return h
    cards = [h for k, h in hints.items() if k.startswith("*")]
    makes = {h["make"] for h in cards}
    return cards[0] if len(makes) == 1 else None


# ------------------------------------------------------------------------------------------------- reading the file
def _read(path: str):
    """(GeoDataFrame in WGS 84, source path shown) of a point shapefile, or of the first .shp in a zip."""
    import pyogrio
    src = path
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as zf:
            shps = sorted(n for n in zf.namelist() if n.lower().endswith(".shp"))
        if not shps:
            raise ValueError(f"{os.path.basename(path)}: no shapefile inside the zip")
        prefer = [n for n in shps if "flagged" in n.lower()] or shps
        src = f"/vsizip/{path}/{prefer[0]}"
    g = pyogrio.read_dataframe(src)
    if g.crs is not None and not g.crs.equals("EPSG:4326"):
        g = g.to_crs("EPSG:4326")
    return g


def _text(s) -> np.ndarray:
    """The values of a column as Python strings, '' where empty (pandas' string dtype keeps NaN in astype(str))."""
    v = pd.Series(s).astype(object)
    return v.where(v.notna(), "").map(lambda x: "" if str(x) in ("None", "nan", "NaN", "<NA>") else str(x)).to_numpy(
        object)


def _num(g, col) -> np.ndarray:
    if not col or col not in g:
        return np.full(len(g), np.nan)
    return pd.to_numeric(g[col], errors="coerce").to_numpy(float)


def _clock_offset_h(epoch_s: float) -> float:
    """Hours from UTC to this computer's clock time at an instant (daylight time included), as SMS shows UTC logs."""
    try:
        local = _dt.datetime.fromtimestamp(epoch_s)
        utc = _dt.datetime.fromtimestamp(epoch_s, _dt.timezone.utc).replace(tzinfo=None)
        return (local - utc).total_seconds() / 3600.0
    except (OSError, OverflowError, ValueError):
        return 0.0


def reading_times(g, det: dict, src_fmt: str | None = None) -> tuple[np.ndarray, dict]:
    """(seconds of each reading on one clock, basis) of the readings in file order. basis["kind"]: "clock" (the
    readings' own time of day, the combines synchronised), "dataset" (each dataset's start time in its name plus the
    durations, file order within a dataset), "order" (no clock: the file order with each reading's duration, one
    reading after another). basis["zone"]: what the clock shows; basis["note"]: the sentence the player shows. The
    seconds are since 1970-01-01 of the clock shown (a UTC log is moved to this computer's clock time)."""
    n = len(g)
    tcol = det.get("time")
    dur = _num(g, det.get("duration_s"))
    med = float(np.nanmedian(dur)) if np.isfinite(dur).any() else 1.0
    dur = np.where(np.isfinite(dur) & (dur > 0) & (dur < 600), dur, med if med > 0 else 1.0)
    if tcol and tcol in g and n:
        t, has_tod = yield_clean._parse_time(g[tcol])
        if has_tod:
            secs = t.astype("datetime64[ns]").astype("int64").to_numpy() / 1e9
            ok = t.notna().to_numpy()
            secs = np.where(ok, secs, np.nan)
            raw = _text(g[tcol])
            sample = [v for v in raw[: min(len(raw), 2000)] if v][:200]
            zoned = bool(sample) and sum(bool(_ZONED.search(v.strip())) for v in sample) >= 0.8 * len(sample)
            if str(src_fmt or "") in UTC_FORMATS or zoned:
                first = float(np.nanmin(secs))
                hours = np.floor(np.where(ok, secs, first) / 3600.0)
                uh = np.unique(hours)
                off = {h: _clock_offset_h(h * 3600.0) for h in uh}
                shift = np.array([off[h] for h in hours]) * 3600.0
                secs = secs + shift
                offs = sorted(set(off.values()))
                zone = "this computer's clock time (UTC " + ", ".join(f"{o:+g} h" for o in offs) + ")"
                note = ("Clock: the readings' own times (" + ("with their time zone" if zoned else "UTC in the logs")
                        + "), shown in " + zone + ".")
            else:
                zone = "the monitor's clock"
                note = "Clock: the readings' own times, as the monitor logged them."
            if np.isnan(secs).any():                            # a reading without a time: its predecessor + duration
                for i in np.flatnonzero(np.isnan(secs)):
                    secs[i] = secs[i - 1] + dur[i] if i > 0 and np.isfinite(secs[i - 1]) else np.nan
                first_ok = np.flatnonzero(np.isfinite(secs))
                if len(first_ok):
                    j0 = first_ok[0]
                    secs[:j0] = secs[j0] - np.cumsum(dur[:j0][::-1])[::-1]
            return secs, {"kind": "clock", "zone": zone, "note": note, "column": tcol}
    dcol = det.get("dataset")
    if dcol and dcol in g and n:
        names = _text(g[dcol])
        starts = {}
        for nm in pd.unique(names):
            m = _STAMP.search(nm)
            if not m:
                starts = None
                break
            yy, mo, dd, hh, mi, ss_ = (int(x) for x in m.groups())
            try:
                starts[nm] = _dt.datetime(2000 + yy, mo, dd, hh, mi, ss_).replace(tzinfo=_dt.timezone.utc).timestamp()
            except ValueError:
                starts = None
                break
        if starts:
            secs = np.empty(n)
            for nm in starts:
                idx = np.flatnonzero(names == nm)
                secs[idx] = starts[nm] + np.r_[0.0, np.cumsum(dur[idx])[:-1]]
            return secs, {"kind": "dataset", "zone": "the dataset names' clock",
                          "note": "No time of day in the file: each dataset starts at the time in its name, then its "
                                  "readings follow one another by their durations (file order)."}
    secs = np.r_[0.0, np.cumsum(dur)[:-1]] if n else np.zeros(0)
    return secs, {"kind": "order", "zone": "time since the first reading",
                  "note": "No clock in the file: the readings play in the file order, one after another, each for its "
                          "duration. Combines are not shown working at the same time."}


# ------------------------------------------------------------------------------------------------- encoding
def _varint(values) -> str:
    """base64 of the zig-zag LEB128 varints of the deltas of an int64 array (the first value from 0)."""
    v = np.asarray(values, np.int64)
    if not len(v):
        return ""
    if (v == v[0]).all():
        return f"={int(v[0])}"                              # a constant column: one number
    d = np.diff(v, prepend=np.int64(0))
    z = ((d << 1) ^ (d >> 63)).astype(np.uint64)
    nb = np.ones(len(z), np.int64)
    for k in range(1, 10):
        nb += (z >= np.uint64(1) << np.uint64(7 * k)).astype(np.int64)
    out = np.zeros(int(nb.sum()), np.uint8)
    pos = np.r_[0, np.cumsum(nb)[:-1]]
    for k in range(int(nb.max())):
        m = nb > k
        byte = ((z[m] >> np.uint64(7 * k)) & np.uint64(0x7F)).astype(np.uint8)
        byte |= np.where(nb[m] > k + 1, 0x80, 0).astype(np.uint8)
        out[pos[m] + k] = byte
    return base64.b64encode(out.tobytes()).decode("ascii")


def decode_varint(b64: str, n: int | None = None) -> np.ndarray:
    """The int64 values of _varint (the inverse, for the tests and the size checks; n: the length of a constant)."""
    if b64.startswith("="):
        return np.full(int(n or 1), int(b64[1:]), np.int64)
    raw = np.frombuffer(base64.b64decode(b64), np.uint8)
    vals, cur, shift = [], 0, 0
    for byte in raw.tolist():
        cur |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        vals.append((cur >> 1) ^ -(cur & 1))
        cur, shift = 0, 0
    return np.cumsum(np.array(vals, np.int64)) if vals else np.zeros(0, np.int64)


def _q(v, scale, missing=-1, lo=None) -> np.ndarray:
    """Quantised integers of v / scale; NaN -> missing (values are clipped at lo first when given)."""
    v = np.asarray(v, float)
    if lo is not None:
        v = np.where(np.isfinite(v), np.maximum(v, lo), v)
    q = np.where(np.isfinite(v), np.round(v / scale), missing)
    return q.astype(np.int64)


# ------------------------------------------------------------------------------------------------- colour scales
def _scale(values, cmap: str, n: int = 11) -> dict:
    """{lo, hi, stops}: the 2nd to 98th percentile of the values (the app's map scale) and n hex stops of the map."""
    f = np.asarray(values, float)
    f = f[np.isfinite(f)]
    lo, hi = (float(np.percentile(f, 2)), float(np.percentile(f, 98))) if len(f) else (0.0, 1.0)
    if hi <= lo and len(f):
        lo, hi = float(f.min()), float(f.max())
    if hi <= lo:
        hi = lo + 1.0
    try:
        import matplotlib
        cm = matplotlib.colormaps[cmap]
        stops = [matplotlib.colors.to_hex(cm(x)) for x in np.linspace(0, 1, n)]
    except Exception:                                     # noqa: BLE001 - matplotlib missing: a plain ramp
        stops = ["#d73027", "#fc8d59", "#fee08b", "#d9ef8b", "#91cf60", "#1a9850"]
    return {"lo": round(lo, 3), "hi": round(hi, 3), "stops": stops}


def _short_name(machine: str) -> str:
    """A short tag of a combine id: the serial number of a 17-character PIN (its last 6), else the id."""
    m = str(machine or "").strip()
    if len(m) >= 13 and re.fullmatch(r"[A-Z0-9-]+", m.upper()) and re.search(r"\d{6}$", m):
        return m[-6:]
    return m[:14] or "Combine"


# ------------------------------------------------------------------------------------------------- the payload
def replay_payload(path: str, kind: str = "auto", outline=None, title: str | None = None, makes: dict | None = None,
                   hints: dict | None = None, steps: dict | None = None, max_bytes: int = MAX_BYTES,
                   yield_col: str | None = None, g=None, rows: bool = False, zones=None,
                   zone_column: str | None = None, record: dict | None = None, edit: bool = False) -> dict:
    """The data of the player for a point file (see the module text). kind: "import", "clean" (a flagged file: Keep
    and Rem_By) or "auto". outline: the field boundary as rings of [lon, lat]. makes: {combine id: make key} set by
    the caller (wins over everything). hints: make_hints() of the raw data. steps: {Rem_By code: name} of the
    cleaning's steps. g: the table already read (WGS 84), else the file is read. rows: each combine also carries
    "rows", the file record of each of its readings (for the tests; not sent to the player). zones: a management
    zone map (engine.zones: a file path with zone_column, or a ZoneMap from zones.prepare): the payload then carries
    "zones" (zone_part) and each combine the column "zb" (zone index x 2 + border flag of each reading); without it
    the payload is the same as before. record: the cleaning record (R) of a flagged file, for the limits of each combine
    and the summary of the edits by hand; edit: the app's replay of a cleaning, where readings can be marked (see the
    module text; rows are then always carried). Pure: reads the files, writes nothing."""
    if g is None:
        g = _read(path)
    fields = [c for c in g.columns if c != "geometry"]
    det = yield_clean.detect_columns(fields)
    if kind == "auto":
        kind = "clean" if ("Keep" in fields and "Rem_By" in fields) else "import"
    sms_out = "Swath_Scl" in fields
    n_file = len(g)
    lon = g.geometry.x.to_numpy(float) if n_file else np.zeros(0)
    lat = g.geometry.y.to_numpy(float) if n_file else np.zeros(0)
    ok = np.isfinite(lon) & np.isfinite(lat) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180)
    src_fmt = None
    if "Src_Fmt" in g:
        u = pd.unique(_text(g["Src_Fmt"]))
        src_fmt = str(u[0]) if len(u) == 1 else None
    secs, basis = reading_times(g, det, src_fmt)
    ok &= np.isfinite(secs)
    ycol = yield_col if (yield_col and yield_col in g) else det.get("yield")
    yld = _num(g, ycol)
    moi = _num(g, det.get("moisture"))
    spd = _num(g, det.get("speed_mph"))
    dur = _num(g, det.get("duration_s"))
    wcol = "Wdth_Opt" if ("Wdth_Opt" in g and kind == "clean") else (det.get("width_ft") or
                                                                     ("Wdth_Opt" if "Wdth_Opt" in g else None))
    wid_m = _num(g, wcol) * FT
    dcol = det.get("distance_ft")
    dist_m = (_num(g, dcol) if dcol else _num(g, det.get("speed_mph")) * 1.46667 * dur) * FT
    hdg = _num(g, det.get("heading"))
    ocol = None if sms_out else yield_clean.sms_mod.y_offset_column(fields)
    off_m = _num(g, ocol) * FT if ocol else np.zeros(n_file)
    keep = (pd.to_numeric(g["Keep"], errors="coerce").fillna(1).to_numpy(int) if kind == "clean" and "Keep" in g
            else np.ones(n_file, int))
    remby = _text(g["Rem_By"]) if kind == "clean" and "Rem_By" in g else np.full(n_file, "", object)
    card = {}                                   # a cleaning: the values its filters compared, where they differ
    if kind == "clean":
        if "Swath_Scl" in g and ycol == det.get("yield"):
            card["yf"] = (yld * np.nan_to_num(_num(g, "Swath_Scl"), nan=1.0), 0.1)        # S5: Yld_Vol_Dr x scale
        if "Dist_Opt" in g and dcol:
            d_log, d_opt = _num(g, dcol), _num(g, "Dist_Opt")
            with np.errstate(divide="ignore", invalid="ignore"):
                card["sf"] = (np.where(d_log > 0, spd * d_opt / d_log, spd), 0.01)        # S4: after the swath step
        if wcol == "Wdth_Opt" and det.get("width_ft"):
            card["wl"] = (_num(g, det["width_ft"]) * FT, 0.01)                          # the logged width (m)
        base = {"yf": yld, "sf": spd, "wl": wid_m}
        card = {k: v for k, v in card.items()
                if not np.allclose(np.nan_to_num(v[0], nan=-1.0), np.nan_to_num(base[k], nan=-1.0), atol=1e-9)}
    man = _text(g["Man_Edit"]) if kind == "clean" and "Man_Edit" in g else None
    rauto = _text(g["Rem_Auto"]) if man is not None and "Rem_Auto" in g else None
    rows = rows or edit
    mcol = det.get("machine")
    machines = _text(g[mcol]) if mcol else np.full(n_file, "", object)
    zm = None
    if zones is not None:                                      # the management zone of each reading (engine/zones.py)
        from engine import zones as zones_mod
        zm = zones if isinstance(zones, zones_mod.ZoneMap) else zones_mod.prepare(str(zones), zone_column)
        zi_all = np.full(n_file, zm.n, np.int64)
        bd_all = np.zeros(n_file, bool)
        if ok.any():
            try:
                zi_ok, bd_ok, zinfo = zm.assign(lon[ok], lat[ok], wid_m[ok])
            except Exception as e:                              # noqa: BLE001 - said in the zone map's words
                raise zones_mod.ZoneMapError(f"the management zone map {zm.file} cannot be laid over the readings: "
                                             f"{str(e).strip() or type(e).__name__}") from e
            zi_all[ok], bd_all[ok] = zi_ok, bd_ok
        else:
            zinfo = {"map_ac": [0.0] * zm.n, "overlap_ac": 0.0, "notes": [], "geoms": [], "crs": None}
        zst = {"zi": [], "bd": [], "a": [], "y": [], "use": [], "c": []}
    lat0 = float(np.nanmedian(lat[ok])) if ok.any() else 0.0
    lon0 = float(np.nanmedian(lon[ok])) if ok.any() else 0.0
    R = 6371008.8
    kx = math.cos(math.radians(lat0)) * math.pi / 180 * R
    ky = math.pi / 180 * R
    x_all, y_all = (lon - lon0) * kx, (lat - lat0) * ky       # a local north-aligned plane, metres
    # sequences as the app's strips (preview_swaths): file order, a change of Run_Id / Pass_Id / dataset / machine,
    # a step > 1.5 x Distance + 0.3 m, a heading change > 60 deg
    seq_cols = [c for c in ("Run_Id", "Pass_Id") if c in fields] + [c for c in (det.get("dataset"), mcol) if c]
    seq_vals = {c: _text(g[c]) for c in seq_cols}
    step_names = dict(STEP_NAMES)
    step_names.update(steps or (step_names_of(record) if record else {}))
    t_lo = float(np.nanmin(secs[ok])) if ok.any() else 0.0      # every time is sent from the first reading
    combos = [m for m in pd.unique(machines[ok])] if ok.any() else []
    combos = sorted(combos, key=lambda m: (float(np.nanmin(secs[ok & (machines == m)])), str(m)))   # who starts first
    makes = dict(makes or {})
    codes = sorted({c for c in remby[ok] if c}, key=lambda s: (s[:2], s))
    code_idx = {c: i + 1 for i, c in enumerate(codes)}          # 0 = kept
    auto_codes = (sorted({c for c in rauto[ok] if c} | set(codes), key=lambda s: (s[:2], s))
                  if rauto is not None else [])
    auto_idx = {c: i + 1 for i, c in enumerate(auto_codes)}
    out_c, total_bytes, n_used = [], 0, int(ok.sum())
    all_y, all_m, all_s = [], [], []
    for ci, m in enumerate(combos):
        idx = np.flatnonzero(ok & (machines == m))
        # time order, file order kept among equal times
        idx = idx[np.argsort(secs[idx], kind="stable")]
        x, y = x_all[idx], y_all[idx]
        new = np.zeros(len(idx), bool)
        if len(idx):
            new[0] = True
        for c in seq_cols:
            v = seq_vals[c][idx]
            new[1:] |= v[1:] != v[:-1]
        h = hdg[idx]
        dh = np.abs(((np.diff(h) + 180) % 360) - 180)
        new[1:] |= ~(dh <= 60) & np.isfinite(dh)
        d = dist_m[idx]
        with np.errstate(invalid="ignore"):
            new[1:] |= ~(np.hypot(np.diff(x), np.diff(y)) <= 1.5 * np.nan_to_num(d[1:]) + 0.3)
        # the travel direction and the link bit of yield_clean.swept_strips (the same rule, max_step_factor 3)
        step = np.r_[np.nan, np.hypot(np.diff(x), np.diff(y))] if len(idx) else np.zeros(0)
        prev_ok = np.r_[False, np.ones(max(len(idx) - 1, 0), bool)]
        with np.errstate(invalid="ignore"):
            link = ~new & prev_ok & (step > 0) & (step <= 3.0 * np.nan_to_num(d) + 1.0)
        if sms_out:
            link[:] = False
            th = np.radians(np.where(np.isfinite(h), h, 0.0))
            tx, ty = np.sin(th), np.cos(th)
        else:
            hh = np.where(np.isfinite(h), h, 0.0)
            tx, ty = yield_clean.travel_direction(x, y, hh, link)
        ang = (np.degrees(np.arctan2(tx, ty)) + 360.0) % 360.0
        # the heading the machine is drawn with: the travel direction smoothed over +-2 readings of the sequence
        t_m = secs[idx]
        w = wid_m[idx]
        oo = np.nan_to_num(off_m[idx])
        working = np.r_[True, np.diff(t_m) <= IDLE_GAP_S] if len(idx) else np.zeros(0, bool)
        # activity: the runs of readings without a gap > IDLE_GAP_S
        cut = np.flatnonzero(~working)
        bounds = np.r_[0, cut, len(idx)]
        runs = [[float(t_m[a]), float(t_m[b - 1] + max(np.nan_to_num(dur[idx][b - 1]), 0.0))]
                for a, b in zip(bounds[:-1], bounds[1:]) if b > a]
        code = np.array([code_idx.get(c, 0) if not k else 0 for c, k in zip(remby[idx], keep[idx])], np.int64)
        flags = link.astype(np.int64) | (np.where(keep[idx] == 1, 0, 1) << 1) | (code << 2)
        area_ac = np.where(np.isfinite(w) & np.isfinite(d) & (w > 0) & (d > 0), w * d / 4046.8564224, 0.0)
        cols = {
            "t": _q(t_m - t_lo, 0.1, missing=0),                     # deciseconds since the first reading
            "lon": _q(lon[idx] - lon0, 1e-7, missing=0), "lat": _q(lat[idx] - lat0, 1e-7, missing=0),
            "dir": _q(ang, 0.1, missing=0),
            "w": _q(w, 0.01, missing=0, lo=0), "d": _q(d, 0.01, missing=0, lo=0),
            "off": _q(oo, 0.01, missing=0),
            "y": _q(yld[idx], 0.1, lo=0), "m": _q(moi[idx], 0.01, lo=0), "s": _q(spd[idx], 0.01, lo=0),
            "f": flags,
        }
        for k_, (v_, sc_) in card.items():
            cols[k_] = _q(v_[idx], sc_, lo=0)
        if man is not None:
            st_ = np.array([EDIT_STATES.get(x, 0) for x in man[idx]], np.int64)
            ra_ = rauto[idx] if rauto is not None else remby[idx]
            moved = (st_ == 0) & (ra_ != remby[idx])
            cols["e"] = st_ | (moved.astype(np.int64) << 2) | (np.array([auto_idx.get(x, 0) for x in ra_], np.int64)
                                                              << 3)
        if zm is not None:
            cols["zb"] = zi_all[idx] * 2 + bd_all[idx].astype(np.int64)
            zst["zi"].append(zi_all[idx])
            zst["bd"].append(bd_all[idx])
            zst["a"].append(area_ac)
            zst["y"].append(yld[idx])
            zst["use"].append(keep[idx] == 1 if kind == "clean" else np.ones(len(idx), bool))
            zst["c"].append(np.full(len(idx), ci, np.int64))
        all_y.append(yld[idx][keep[idx] == 1] if kind == "clean" else yld[idx])
        all_m.append(moi[idx])
        all_s.append(spd[idx])
        mk_given = makes.get(m)
        hint = _hint_for(m, hints or {})
        model = (hint or {}).get("model") or ""
        if mk_given in MAKES:
            mk, why = mk_given, "set by hand"
        else:
            mk, why = make_of(None, src_fmt, m, hint)
        y_ok = np.isfinite(yld[idx]) & (keep[idx] == 1)
        out_c.append({
            "id": m or "Combine", "name": _short_name(m) if m else "Combine", "num": ci + 1,
            "color": PALETTE_CAT[ci % len(PALETTE_CAT)], "make": mk, "make_why": why, "model": model,
            "n": int(len(idx)), "runs": runs, "cols": cols,
            # the acres of the readings counted (a cleaning: the kept ones), as the bushels and the panel's numbers
            "area_ac": float(area_ac[keep[idx] == 1].sum()) if kind == "clean" else float(area_ac.sum()),
            "bu": float(np.nansum(np.where(y_ok, yld[idx], 0.0) * area_ac)),
            "t0": float(t_m[0]) if len(idx) else None, "t1": float(t_m[-1]) if len(idx) else None,
        })
        if rows:
            out_c[-1]["rows"] = idx.tolist()
    # thinning: every k-th reading of each combine, the distance of the readings skipped added to the one kept
    enc_cols = ("t", "lon", "lat", "dir", "w", "d", "off", "y", "m", "s", "f")
    thin = 1
    while True:
        total_bytes = 0
        for C in out_c:
            C["enc"] = _encode_cols(C["cols"], thin)
            total_bytes += sum(len(v) for v in C["enc"].values())
        if total_bytes <= max_bytes or thin >= 64:
            break
        thin = int(math.ceil(thin * total_bytes / max_bytes * 1.05)) if thin == 1 else thin + 1
    for C in out_c:
        C["data"] = C.pop("enc")
        C.pop("cols")
        C["n_shown"] = len(range(0, C["n"], thin)) if thin > 1 else C["n"]
    ally = np.concatenate(all_y) if all_y else np.zeros(0)
    allm = np.concatenate(all_m) if all_m else np.zeros(0)
    alls = np.concatenate(all_s) if all_s else np.zeros(0)
    t_hi = max((r[1] for C in out_c for r in C["runs"]), default=t_lo)
    # the times no combine works longer than IDLE_SKIP_S: skipped in playback
    ivs = sorted(r for C in out_c for r in C["runs"])
    gaps, cur = [], None
    for a, b in ivs:
        if cur is None:
            cur = [a, b]
        elif a > cur[1]:
            if a - cur[1] > IDLE_SKIP_S:
                gaps.append([cur[1], a])
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    for C in out_c:
        C["runs"] = [[round(a - t_lo, 1), round(b - t_lo, 1)] for a, b in C["runs"]]
        C["t0"] = round(C["t0"] - t_lo, 1) if C["t0"] is not None else None
        C["t1"] = round(C["t1"] - t_lo, 1) if C["t1"] is not None else None
    units = {"yield": "bu/ac", "moisture": "%", "speed": "mph"}
    area_tot = sum(C["area_ac"] for C in out_c)
    bu_tot = sum(C["bu"] for C in out_c)
    removed = {}
    if kind == "clean":
        for c in codes:
            removed[c] = int(sum(1 for x, k in zip(remby[ok], keep[ok]) if x == c and not k))
    P = {
        "v": FORMAT_VERSION, "kind": kind, "title": title or os.path.splitext(os.path.basename(path))[0],
        "file": os.path.basename(path), "n_file": int(n_file), "n": int(n_used), "thin": int(thin),
        "t0": float(t_lo), "t_end": round(t_hi - t_lo, 1), "basis": basis, "idle": [[round(a - t_lo, 1),
                                                                                    round(b - t_lo, 1)] for a, b in gaps],
        "idle_gap_s": IDLE_GAP_S, "idle_skip_s": IDLE_SKIP_S, "sms_rect": bool(sms_out),
        "src_fmt": src_fmt, "center": [lon0, lat0],
        "bbox": ([float(lon[ok].min()), float(lat[ok].min()), float(lon[ok].max()), float(lat[ok].max())]
                 if ok.any() else None),
        "outline": [[[round(float(a), 7), round(float(b), 7)] for a, b in ring] for ring in (outline or [])],
        "columns": {"yield": ycol, "moisture": det.get("moisture"), "speed": det.get("speed_mph"),
                    "width": wcol, "distance": dcol, "heading": det.get("heading"), "machine": mcol,
                    "time": det.get("time"), "offset": ocol},
        "units": units,
        "scales": {"yield": _scale(ally, "RdYlGn"), "moisture": _scale(allm, "YlGnBu"),
                   "speed": _scale(alls, "plasma")},
        "steps": [{"code": c, "idx": code_idx[c], "name": step_names.get(c) or step_names.get(c[:2]) or c,
                   "n": removed.get(c, 0)} for c in codes],
        "combines": out_c, "makes": MAKES,
        "totals": {"area_ac": round(area_tot, 3), "bu": round(bu_tot, 2),
                   "bu_ac": round(bu_tot / area_tot, 2) if area_tot > 0 else None, "n": int(n_used),
                   "kept": int((keep[ok] == 1).sum()), "removed": int((keep[ok] != 1).sum())},
        "bytes": int(total_bytes),
    }
    if kind == "clean":
        P["step_names"] = {c: step_names.get(c) or step_names.get(c[:2]) or c for c in (set(codes) | set(auto_codes))}
        if card:
            P["card_cols"] = sorted(card)
        lim = limits_of(record, [C["id"] for C in out_c])
        if lim:
            P["limits"] = lim
        if man is not None:
            P["auto_codes"] = auto_codes
            P["manual"] = manual_part(record, man[ok], (rauto if rauto is not None else remby)[ok], remby[ok])
        if edit:
            # the fate each reading gets when the marks do not name it: an edit of this cleaning that the marks do not
            # hold any more goes back to the automatic cleaning (Rem_Auto), any other reading keeps its fate (as
            # edit_keys counts kept_after)
            fate = keep == 1
            if man is not None:
                fate = np.where(np.isin(man.astype(str), ["R", "K"]), (rauto == "") if rauto is not None else fate, fate)
            shared, in_group = _shared_groups(g, out_c, fate) if thin == 1 else ([], np.zeros(n_file, bool))
            P["edit"] = edit_part(path, thin, n_used, n_file, g, kept_outside=int((fate & ~ok & ~in_group).sum()))
            if shared:
                P["edit"]["shared"] = shared
    if zm is not None:
        P["zones"] = zone_part(zm, zinfo, {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in zst.items()},
                               [C["name"] for C in out_c], P["center"], kind)
        P["zone_bytes"] = int(sum(len(C["data"].get("zb", "")) for C in out_c)
                              + len(json.dumps(_clean_floats(P["zones"]), separators=(",", ":"), default=_json_default)))
    return P


def limits_of(R: dict | None, combines: list) -> dict:
    """{combine id: {step code: [lo, hi, attribute, unit]}} from a cleaning record's sms3sigma steps: a combine's own
    group when the record has one by its name, else the single group of the cleaning (all combines as one group).
    {} when the record cannot say (no record, other groups): the card then shows no limits."""
    steps = ((R or {}).get("sms3sigma") or {}).get("steps") or []
    by = {}
    for r in steps:
        if r.get("lo") is None and r.get("hi") is None:
            continue
        by.setdefault(str(r.get("group")), {})[str(r.get("step"))] = [r.get("lo"), r.get("hi"), r.get("attribute"),
                                                                      r.get("unit")]
    out = {}
    for m in combines:
        if str(m) in by:
            out[str(m)] = by[str(m)]
        elif len(by) == 1:
            out[str(m)] = next(iter(by.values()))
    return out


def manual_part(R: dict | None, man, rauto, remby) -> dict:
    """The player's summary of a cleaning with edits by hand: the record's headline (manual_edits.summary_text), the
    readings removed / kept by hand, the readings whose fate moved without a mark, and the automatic and the edited
    totals (all combines and per combine). Counts from the flagged file when the record is not there."""
    from engine.clean import manual_edits as me
    X = (R or {}).get("manual_edits") or {}
    out = {"removed_by_hand": int(np.sum(man == "R")), "kept_by_hand": int(np.sum(man == "K")),
           "not_applied": int(np.sum(man == "N")), "moved": int(np.sum((man == "") & (rauto != remby)))}
    if X:
        out["summary"] = me.summary_text(R)
        out["title"] = me.title_label(R)
        out["changes_result"] = bool(X.get("changes_result", True))
        for k in ("automatic", "edited"):
            cb = (X.get(k) or {}).get("combines") or {}
            out[k] = {m: {f: v.get(f) for f in ("points", "acres", "dry_bu", "yield_bu_ac")} for m, v in cb.items()}
    return out


def _file_token(path: str, n_file: int) -> str:
    """The token of the flagged file a payload was built from: md5 of its .dbf (every value and mark) and the count."""
    import hashlib
    h = hashlib.md5(str(n_file).encode())
    dbf = os.path.splitext(path)[0] + ".dbf" if path and not path.lower().endswith(".zip") else None
    try:
        with open(dbf if dbf and os.path.exists(dbf) else path, "rb") as fh:
            for b in iter(lambda: fh.read(1 << 20), b""):
                h.update(b)
    except (OSError, TypeError):
        pass
    return h.hexdigest()


def _shared_groups(g, out_c: list, fate) -> tuple:
    """The readings of the player that share a reading key with another record of the file (manual_edits.flagged_keys:
    the engine removes or keeps every record of a key together): [{m: [[combine num, index], ...], hn: records of the
    key not in the player, hk: those of them kept when the marks do not name the key}], and the file rows they cover
    (left out of kept_outside: the player counts them per group). [] when every key is the file's only record."""
    from engine.clean import manual_edits as me
    F = pd.DataFrame(g.drop(columns="geometry")) if "geometry" in g else g
    keys = pd.Series([str(k) for k in me.flagged_keys(F)[0]], index=range(len(F)))
    in_group = np.zeros(len(F), bool)
    dup = keys.duplicated(keep=False)
    if not dup.any():
        return [], in_group
    pos = {int(r): [C["num"], i] for C in out_c for i, r in enumerate(C.get("rows") or [])}
    out = []
    for _, rows_k in keys[dup].groupby(keys[dup]).groups.items():
        rows_k = [int(r) for r in rows_k]
        mem = [pos[r] for r in rows_k if r in pos]
        if not mem:                                      # no record of the key in the player: kept_outside counts them
            continue
        hid = [r for r in rows_k if r not in pos]
        in_group[rows_k] = True
        out.append({"m": mem, "hn": len(hid), "hk": int(sum(bool(fate[r]) for r in hid))})
    return out, in_group


def edit_part(path: str, thin: int, n_used: int, n_file: int, g, kept_outside: int = 0) -> dict:
    """P['edit'] of the app's replay of a cleaning: ok when every reading is in the player (not thinned); why: the
    reason when not; token: of the flagged file (the marks sent back must name it); min_kept: the fewest kept readings
    a clean file can have (yield_clean.MIN_KEPT: fewer and the cleaning stops); kept_outside: the kept readings of the
    file that are not in the player (no position or time) with the fate the marks give them, which the player adds
    to its count of what the marks leave (replay_payload also adds 'shared': the readings that share a key)."""
    fields = set(g.columns)
    if not {"Keep", "Rem_By"} <= fields:
        ok, why = False, "this file is not the flagged file of a cleaning (no Keep / Rem_By)"
    elif thin > 1:
        ok, why = False, (f"this field has too many readings to edit here ({n_file:,}): the replay shows 1 in {thin}, "
                          "and a reading you cannot see is never marked")
    else:
        ok, why = True, ""
    out = {"ok": ok, "why": why, "token": _file_token(path, n_file), "n": int(n_used),
           "min_kept": int(yield_clean.MIN_KEPT), "kept_outside": int(kept_outside),
           "rule": "remove: a kept reading; keep: a reading the moisture, speed or yield filter removed; the import "
                   "range (S0), the clip (S1) and the swath step (S2) cannot be undone by hand"}
    if n_used < n_file:
        out["note"] = (f"{n_file - n_used:,} reading(s) of the file have no position or time and are not in the replay: "
                       "they keep their fate")
    return out


def edit_keys(P: dict, marks: dict, flagged) -> dict:
    """The player's marks -> the engine's reading keys. marks: {token, remove: [[combine num, index], ...], keep:
    [...]} (index: the reading's place in its combine, in the payload's order); P: the payload they were made on
    (built with edit=True: its combines carry rows); flagged: the flagged file (path or DataFrame) of that payload.
    Returns {remove, keep (sorted keys), refused [{num, i, mark, reason}], n_remove, n_keep, kept_after, min_kept,
    key_info}: kept_after = the readings of the file kept with these marks before the limits move (a reading removed
    by hand: out; kept by hand: in; an edit of the cleaning shown that the marks no longer hold: its automatic fate,
    Rem_Auto; any other: its fate now), an estimate only, since the 3-sigma limits are computed again with the edits
    (readings come back or go); the cleaning itself stops below min_kept (yield_clean.MIN_KEPT). Raises ValueError
    when the marks are not of this payload (token) or the payload cannot be edited."""
    from engine.clean import manual_edits as me
    E = P.get("edit") or {}
    if not E.get("ok"):
        raise ValueError("this replay cannot be edited: " + (E.get("why") or "no edit data"))
    if str((marks or {}).get("token")) != str(E.get("token")):
        raise ValueError("the marks were made on another version of this cleaning (it changed since the replay was "
                         "built): nothing was applied, mark the readings again")
    F = flagged if isinstance(flagged, pd.DataFrame) else _read(flagged)
    if "geometry" in F:
        F = pd.DataFrame(F.drop(columns="geometry"))
    if len(F) != int(P.get("n_file", -1)):
        raise ValueError("the flagged file does not match the replay (another number of readings): nothing applied")
    keys, info = me.flagged_keys(F)
    remby = _text(F["Rem_By"]) if "Rem_By" in F else np.full(len(F), "", object)
    man = _text(F["Man_Edit"]) if "Man_Edit" in F else np.full(len(F), "", object)
    by_num = {int(C["num"]): C for C in P["combines"]}
    out = {"remove": set(), "keep": set(), "refused": []}
    for mark in ("remove", "keep"):
        for it in (marks.get(mark) or []):
            try:
                num, i = int(it[0]), int(it[1])
                if i < 0:
                    raise IndexError
                r = int(by_num[num]["rows"][i])
            except (KeyError, IndexError, TypeError, ValueError):
                out["refused"].append({"num": None, "i": None, "mark": mark, "reason": "not a reading of this replay"})
                continue
            rb = str(remby[r])
            why = UNMARKABLE.get(rb[:2]) if rb else None
            if why is None and mark == "remove" and rb not in ("", me.STEP):
                why = f"removed by {rb}: only a kept reading can be removed by hand"
            if why is None and mark == "keep" and not (rb[:2] in ("S3", "S4", "S5") or man[r] == "K"):
                why = ("kept already: only a reading the moisture, speed or yield filter removed can be kept by hand"
                       if rb == "" else f"removed by {rb}: it cannot be kept by hand")
            if why:
                out["refused"].append({"num": num, "i": i, "mark": mark, "reason": why})
                continue
            out[mark].add(str(keys[r]))
    both = out["remove"] & out["keep"]
    if both:
        raise ValueError(f"{len(both)} reading(s) were marked both remove and keep: nothing applied")
    # what the marks leave, before the limits move: the rows of the keys (a key can stand for several rows)
    keys_s = [str(k) for k in keys]
    is_rm = np.fromiter((k in out["remove"] for k in keys_s), bool, len(keys_s))
    is_kp = np.fromiter((k in out["keep"] for k in keys_s), bool, len(keys_s))
    kept_now = ((pd.to_numeric(F["Keep"], errors="coerce").fillna(1).to_numpy(int) == 1) if "Keep" in F
                else np.ones(len(F), bool))
    auto_kept = (_text(F["Rem_Auto"]) == "") if "Rem_Auto" in F else kept_now
    dropped_edit = np.isin(man.astype(str), ["R", "K"]) & ~is_rm & ~is_kp
    kept_after = int((is_kp | (~is_rm & np.where(dropped_edit, auto_kept, kept_now))).sum())
    return {"remove": sorted(out["remove"]), "keep": sorted(out["keep"]), "refused": out["refused"],
            "n_remove": len(out["remove"]), "n_keep": len(out["keep"]), "kept_after": kept_after,
            "min_kept": int(yield_clean.MIN_KEPT), "key_info": info}


def zone_part(zm, info: dict, arr: dict, names: list, center, kind: str) -> dict:
    """The management zones of the player: the zone map (each class's label, colour, map area, outline rings
    simplified by at most zones.SIMPLIFY_M and coded as the readings' columns, label chips), the final statistics
    (zones.zone_stats: interior and all) and the agreement summary (zones.agreement)."""
    from engine import zones as zones_mod
    S = zones_mod.zone_stats(arr["zi"], arr["bd"], arr["a"], arr["y"], arr["use"], arr["c"], zm.labels,
                             info["map_ac"], names)
    A = zones_mod.agreement(S, arr["zi"], arr["bd"], arr["a"], arr["y"], arr["use"], arr["c"], zm.labels, names)
    A["ordered_classes"] = bool(zm.numeric)
    if not zm.numeric:
        A["rank_rho"] = None
    classes = []
    for k in range(zm.n):
        g = info["geoms"][k] if info.get("geoms") else None
        rings, chips = _zone_rings(g, info.get("crs"), center)
        classes.append({"label": zm.labels[k], "colour": zm.colours[k], "map_ac": float(info["map_ac"][k]),
                        "rings": rings, "chips": chips})
    cover = zones_mod.coverage_note(arr["zi"], arr["use"], zm.n, zm.file)
    return {"file": zm.file, "column": zm.column, "classes": classes, "outside": zones_mod.OUTSIDE,
            "numeric": bool(zm.numeric), "kind": kind, "raw": kind != "clean", "coverage_note": cover,
            "notes": ([cover] if cover else []) + list(zm.notes) + list(info.get("notes") or []),
            "overlap_ac": float(info.get("overlap_ac") or 0),
            "border_default_m": zones_mod.BORDER_DEFAULT_M, "simplify_m": zones_mod.SIMPLIFY_M,
            "stats": {"interior": S["interior"], "all": S["all"]}, "cells": S["cells"], "agreement": A}


def _zone_rings(g, crs, center) -> tuple[dict, list]:
    """({"n": ring lengths, "x", "y": the varint columns of lon / lat - center in 1e-7 deg}, label chips [[lon, lat]])
    of one management zone's polygons (in crs, metres): every ring, simplified by at most zones.SIMPLIFY_M."""
    from engine import zones as zones_mod
    if g is None or g.is_empty or crs is None:
        return {"n": [], "x": "", "y": ""}, []
    import shapely
    from pyproj import Transformer
    tr = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    gs = shapely.simplify(g, zones_mod.SIMPLIFY_M, preserve_topology=True)
    parts = [p for p in getattr(gs, "geoms", [gs]) if p.geom_type == "Polygon" and not p.is_empty]
    ns, xs, ys = [], [], []
    for p in parts:
        for ring in [p.exterior, *p.interiors]:
            c = np.asarray(ring.coords)[:-1]
            if len(c) < 3:
                continue
            lo, la = tr.transform(c[:, 0], c[:, 1])
            ns.append(len(c))
            xs.append(_q(np.asarray(lo) - center[0], 1e-7, missing=0))
            ys.append(_q(np.asarray(la) - center[1], 1e-7, missing=0))
    chips = []
    big = sorted((p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon"), key=lambda p: -p.area)
    total = sum(p.area for p in big) or 1.0
    for p in big[:3]:
        if chips and p.area < 0.15 * total:
            break
        from shapely.ops import polylabel
        try:
            pt = polylabel(p, tolerance=1.0)
        except Exception:                                   # noqa: BLE001 - a degenerate part: its surface point
            pt = p.representative_point()
        lo, la = tr.transform(pt.x, pt.y)
        chips.append([round(float(lo), 7), round(float(la), 7)])
    return ({"n": ns, "x": _varint(np.concatenate(xs)) if xs else "", "y": _varint(np.concatenate(ys)) if ys else ""},
            chips)


def payload_columns(P: dict, C: dict) -> dict:
    """The decoded columns of one combine of a payload, in the player's units: t (s since the first reading), lon, lat
    (deg), dir (deg), w, d, off (m), y (bu/ac), m (%), s (mph), NaN where missing; f (flags)."""
    n = C["n_shown"]
    raw = {k: decode_varint(v, n).astype(float) for k, v in C["data"].items()}
    out = {"t": raw["t"] * 0.1, "lon": P["center"][0] + raw["lon"] * 1e-7, "lat": P["center"][1] + raw["lat"] * 1e-7,
           "dir": raw["dir"] * 0.1, "w": raw["w"] * 0.01, "d": raw["d"] * 0.01, "off": raw["off"] * 0.01,
           "f": raw["f"].astype(np.int64)}
    for k, sc in (("y", 0.1), ("m", 0.01), ("s", 0.01)):
        out[k] = np.where(raw[k] < 0, np.nan, raw[k] * sc)
    return out


def payload_quads(P: dict) -> dict:
    """{combine id: (file rows or None, (n, 4, 2) corners lon/lat)}: the strips the player paints, by the player's
    rule (the port of its JavaScript): linked readings from the header line at the previous reading, else a rectangle
    Distance back along the travel. For the tests: they must be the app's strips (yield_clean.swept_strips)."""
    out = {}
    lat0 = P["center"][1]
    kx = math.cos(math.radians(lat0)) * math.pi / 180 * 6371008.8
    ky = math.pi / 180 * 6371008.8
    for C in P["combines"]:
        c = payload_columns(P, C)
        x, y = (c["lon"] - P["center"][0]) * kx, (c["lat"] - lat0) * ky
        a = np.radians(c["dir"])
        tx, ty = np.sin(a), np.cos(a)
        nx, ny = ty, -tx
        lo, hi = c["off"] - c["w"] / 2, c["off"] + c["w"] / 2
        link = (c["f"] & 1).astype(bool)
        link[0] = False
        px, py, pnx, pny = (np.r_[np.nan, v[:-1]] for v in (x, y, nx, ny))
        bx, by = x - tx * c["d"], y - ty * c["d"]
        lk = link[:, None]
        q = np.stack([np.where(lk, np.c_[px + pnx * lo, py + pny * lo], np.c_[bx + nx * lo, by + ny * lo]),
                      np.where(lk, np.c_[px + pnx * hi, py + pny * hi], np.c_[bx + nx * hi, by + ny * hi]),
                      np.c_[x + nx * hi, y + ny * hi], np.c_[x + nx * lo, y + ny * lo]], axis=1)
        bad = ~(c["w"] > 0) | (~link & ~(c["d"] > 0))
        q[bad] = np.nan
        q[..., 0] = q[..., 0] / kx + P["center"][0]
        q[..., 1] = q[..., 1] / ky + lat0
        out[C["id"]] = (C.get("rows"), q)
    return out


def _encode_cols(cols: dict, thin: int) -> dict:
    """The base64 varint columns, every thin-th reading (thin > 1: the distance of the readings skipped is added to
    the one kept, and the link bit stays only where the step to the previous kept reading is still a link)."""
    if thin <= 1:
        return {k: _varint(v) for k, v in cols.items()}
    n = len(cols["t"])
    keep = np.arange(0, n, thin)
    out = {}
    for k, v in cols.items():
        v = np.asarray(v)
        if k == "d":
            cs = np.cumsum(np.maximum(v, 0))
            prev = np.r_[0, cs[keep[:-1]]] if len(keep) else np.zeros(0)
            vv = cs[keep] - prev
        elif k == "f":
            vv = v[keep].copy()
            vv &= ~1                                            # the link to the previous kept reading: rebuilt below
            ok_link = np.ones(len(keep), bool)
            for j in range(1, len(keep)):
                ok_link[j] = bool(np.all(v[keep[j - 1] + 1:keep[j] + 1] & 1))
            ok_link[0] = False
            vv |= ok_link.astype(np.int64)
        else:
            vv = v[keep]
        out[k] = _varint(vv)
    return out


# ------------------------------------------------------------------------------------------------- the HTML
PLAYER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay_player.html")
TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
TILE_ATTRIBUTION = "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community"


def replay_html(payload: dict, height: int | None = None, embedded: bool = False, title: str | None = None,
                edit: bool = False) -> str:
    """One self-contained HTML document (a string) that plays the payload: the player's script, style and data
    inline; the only address in it is the Esri World Imagery tile server (the app's satellite maps). height: the
    player's height in px (None: the window's); embedded: inside the app (an iframe: the taller / shorter switch
    resizes the frame, the full screen falls back to a new tab); edit: the app's two-way player, with the 'Edit
    points' switch and the marks sent to the page that holds the frame (only when the payload can be edited:
    P['edit']['ok']). Without it (the standalone file) the readings removed and kept by hand are shown, read-only."""
    with open(PLAYER, encoding="utf-8") as fh:
        tpl = fh.read()
    if not payload.get("zones"):                 # no management zone map: the player has no zone control at all
        tpl = re.sub(r"<!--zones-->.*?<!--/zones-->", "", tpl, flags=re.S)
    cfg = {"height": height, "embedded": bool(embedded), "tiles": TILE_URL, "attribution": TILE_ATTRIBUTION,
           "edit": bool(edit and payload.get("edit"))}
    if any("rows" in C for C in payload.get("combines") or []):     # the file rows stay with the caller
        payload = {**payload, "combines": [{k: v for k, v in C.items() if k != "rows"} for C in payload["combines"]]}
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False, default=_json_default, ensure_ascii=False)
    # every '<' of the data written as its JSON escape (read back the same): no name from a file (a zone label, a
    # column, a machine) can end the data block or open a comment in it ('<!--<script' would leave the page blank)
    data = data.replace("<", "\\u003c")
    conf = json.dumps(cfg, ensure_ascii=False).replace("<", "\\u003c")
    t = _html.escape(title or payload.get("title") or "Harvest replay")
    fill = {"__TITLE__": t, "/*__CONFIG__*/null": conf, "__PAYLOAD__": data}
    return re.sub(r"__TITLE__|/\*__CONFIG__\*/null|__PAYLOAD__", lambda m: fill[m.group(0)], tpl)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(type(o))


def _clean_floats(o):
    """NaN / inf -> None in a nested structure (JSON has no NaN)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean_floats(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean_floats(v) for v in o]
    return o


def build(path: str, out: str | None = None, boundary: str | None = None, raw: str | None = None,
          makes: dict | None = None, title: str | None = None, height: int | None = None,
          max_bytes: int = MAX_BYTES, kind: str = "auto", zones=None, zone_column: str | None = None,
          zone_csv: str | None = None) -> dict:
    """The payload of a file (with the boundary rings of a polygon file, the make hints of raw data, the step names
    of a cleaning record found beside a flagged file, a management zone map) and, with out, the standalone HTML
    written there; with zone_csv (and a zone map) the table of the management zones (zones.write_csv)."""
    outline = boundary_rings(boundary) if boundary else None
    hints = make_hints(raw) if raw else {}
    steps = steps_of_record(path)
    P = _clean_floats(replay_payload(path, kind=kind, outline=outline, title=title, makes=makes, hints=hints,
                                     steps=steps, max_bytes=max_bytes, zones=zones, zone_column=zone_column))
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(replay_html(P, height=height))
    if zone_csv and P.get("zones"):
        from engine import zones as zones_mod
        zones_mod.write_csv(P["zones"]["stats"], zone_csv, raw=P["zones"]["raw"])
    return P


def boundary_rings(path: str) -> list:
    """The rings [[lon, lat], ...] of every polygon of a boundary file (exteriors and holes)."""
    import geopandas as gpd
    b = gpd.read_file(path)
    if b.crs is not None and not b.crs.equals("EPSG:4326"):
        b = b.to_crs("EPSG:4326")
    out = []
    for geom in b.geometry:
        if geom is None:
            continue
        for p in getattr(geom, "geoms", [geom]):
            if getattr(p, "geom_type", "") != "Polygon":
                continue
            for ring in [p.exterior, *p.interiors]:
                out.append([[float(x), float(y)] for x, y in ring.coords])
    return out


def steps_of_record(path: str) -> dict:
    """{Rem_By code: step name} from the cleaning record beside a flagged file (<tag>_cleaning.json), else {}."""
    if not path or path.lower().endswith(".zip"):
        return {}
    stem = os.path.splitext(path)[0]
    cand = [stem.replace("_flagged", "_cleaning") + ".json", stem + "_cleaning.json"]
    for c in cand:
        if os.path.exists(c):
            try:
                with open(c, encoding="utf-8") as fh:
                    R = json.load(fh)
            except (OSError, ValueError):
                return {}
            return step_names_of(R)
    return {}


def step_names_of(R: dict | None) -> dict:
    """{Rem_By code: 'S3 moisture'} from a cleaning record's cascade (the filter and its name)."""
    out = {}
    for r in (R or {}).get("cascade") or []:
        f = str(r.get("filter") or "")
        if not f:
            continue
        nm = str(r.get("name") or "").replace(" mean +/- k SD", "").split(", pass")[0]
        attr = r.get("attribute")
        label = f"{f} {attr}" if attr else f"{f} {nm}"
        out[f] = label + (" (pass 2)" if f.endswith("b") else "")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.replay", description="A harvest replay (one HTML file) of a "
                                 "point file: an import, a point export or the flagged file of a cleaning.")
    ap.add_argument("input", help="point shapefile (.shp) or a zip holding one (a flagged zip: the cleaning)")
    ap.add_argument("--out", required=True, help="the HTML file to write")
    ap.add_argument("--boundary", default=None, help="field boundary polygon file (drawn on the map)")
    ap.add_argument("--raw", default=None, help="the raw monitor data (folder or zip) to read the make of each combine")
    ap.add_argument("--make", action="append", default=[], metavar="COMBINE=MAKE",
                    help=f"the make of a combine ({', '.join(MAKES)}); COMBINE may be '*' for every combine")
    ap.add_argument("--title", default=None)
    ap.add_argument("--kind", choices=["auto", "import", "clean"], default="auto")
    ap.add_argument("--max-mb", type=float, default=MAX_BYTES / 1e6, help="encoded readings above this are thinned")
    ap.add_argument("--zones", default=None, help="a management zone map made elsewhere (polygons: zip, shp, geojson, "
                                                  "kml, kmz, gpkg): the yield inside each zone while the combines harvest")
    ap.add_argument("--zone-column", default=None, help="the column of the zone map that holds the zones (default: "
                                                        "the best candidate, such as 'zone')")
    ap.add_argument("--zone-csv", default=None, help="write the table of the management zones (zone_yield.csv) here")
    a = ap.parse_args(argv)
    if (a.zone_column or a.zone_csv) and not a.zones:
        ap.error("--zone-column and --zone-csv need --zones")
    makes = {}
    for s in a.make:
        if "=" not in s:
            ap.error(f"--make {s}: COMBINE=MAKE")
        k, v = s.split("=", 1)
        if v not in MAKES:
            ap.error(f"--make {s}: the make is one of {', '.join(MAKES)}")
        makes[k] = v
    if "*" in makes:
        star = makes.pop("*")
        g = _read(a.input)
        det = yield_clean.detect_columns([c for c in g.columns if c != "geometry"])
        mc = det.get("machine")
        for m in (pd.unique(_text(g[mc])) if mc else [""]):
            makes.setdefault(m, star)
    try:
        P = build(a.input, a.out, boundary=a.boundary, raw=a.raw, makes=makes, title=a.title, kind=a.kind,
                  max_bytes=int(a.max_mb * 1e6), zones=a.zones, zone_column=a.zone_column, zone_csv=a.zone_csv)
    except ValueError as e:                                     # a zone map that cannot be used: the reason, no trace
        if not a.zones:
            raise
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(f"{a.out}: {P['n']:,} readings of {len(P['combines'])} combine(s), {P['kind']}, clock {P['basis']['kind']}, "
          f"thin {P['thin']}, {os.path.getsize(a.out) / 1e6:.2f} MB")
    for C in P["combines"]:
        print(f"  #{C['num']} {C['id']}: {C['n']:,} readings, {MAKES[C['make']]['label']} ({C['make_why']})")
    Z = P.get("zones")
    if Z:
        A = Z["agreement"]
        eta = "n/a" if A.get("eta2") is None else f"{100 * A['eta2']:.0f} %"
        print(f"  management zones from {Z['file']} (column {Z['column']}): {len(Z['classes'])} zones; they account "
              f"for {eta} of the yield variation between readings ({'raw, not cleaned' if Z['raw'] else 'cleaned'})")
        for r in Z["stats"]["interior"]["zones"]:
            if r["n"]:
                y = "-" if r["yield"] is None else f"{r['yield']:.1f}"
                print(f"    {r['label']}: {y} bu/ac, {r['acres']:.1f} ac, {r['n']:,} readings ({r['n_border']:,} on a "
                      "border, left out)")
        for n in Z["notes"]:
            print(f"    note: {n}")
        if a.zone_csv:
            print(f"  {a.zone_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
