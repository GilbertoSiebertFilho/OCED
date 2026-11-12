# -*- coding: utf-8 -*-
"""Write the CLEAN harvest back as a Case IH / New Holland AFS Pro 700 card (.cn1), the format it came in.

    from engine.formats import cnh_cn1_write as W
    ok, why = W.can_write(dec["source"])                            # (False, reason) when the card cannot be written
    res = W.write_clean(dec["source"], clean_shp, out_dir)          # widths=True, factors=None, new_ids=True
    res["zip"]                                                      # the card(s), for Read File(s) > Case IH in SMS

NOT YET TESTED IN SMS: everything below is checked by decoding the written card with OCED's own decoder (the decoder
reproduces SMS's points and Summary of the original cards); whether Ag Leader SMS reads the written card as it reads
the monitor's own is not established until a written card has been read into a scratch SMS project.

What is written (the three levels):
  1  the kept readings: a copy of each card that holds the decoded tasks in which every reading the cleaning REMOVED
     (import minimum / maximum, boundary clip, readings removed by Optimize Swath Widths, the 3-sigma filters) is no
     longer a reading, every other record byte for byte. Two ways (mode):
       "header_up" (default)  the removed reading's .tlo record gets its logging bit cleared (.tlo[0] bit 0, "area
                              counting off", what the display writes with the header up): 2 bytes per removed reading
                              (the bit and the record checksum), no record taken out, the streams keep their counters.
                              Ag Leader SMS makes no point of such a record: on cards whose point counts SMS matches
                              exactly, records with the logging bit off but a valid fix, flow, distance, interval,
                              width and a yield inside the import limits are not points in SMS.
       "drop"                 the removed reading's records are taken out of .tlo, .tlh and .tlt. The record counter
                              then has gaps; the .tlh of tasks SMS reads can have gaps, their .tlo none was seen,
                              so whether a vendor reader accepts gaps in .tlo is not established. Where the display
                              restarted during a task (the record counter goes back; the decoder pairs the streams
                              restart by restart) the first and the last record of each restart run are never taken
                              out: a removed reading there gets its logging bit cleared, so that no stream loses a
                              restart the other keeps.
     Records that never were readings (header up, no GNSS fix, flow sample invalid, not moving, interval 0, width 0)
     stay as they are. No grain moves: a reading's mass is its own record's flow x interval, so a removed reading's
     grain is not given to any kept one.
  2  widths=True: the swath of each kept reading as the cleaning left it. Optimize Swath Widths narrows a reading
     (Swth_Wdth_), may shorten it (Distance_f, and so the speed) and moves a narrowed reading to the centre of its
     uncovered strip; the writer puts the clean width in .tlo[4:6] (mm), the distance in .tlo[2:4] (mm, scaled by
     clean / decoded Distance_f, so it does not depend on the decoder's time basis) and moves the two header ends
     (.tlo[25:33], [33:41]) so that their midpoint - the position every reader uses - is the clean position and their
     span follows the clean width; the logged antenna point (.tlo[6:14]) moves by the same amount, so that it keeps its
     offset from the header centre. The grain flow, moisture and interval are untouched, so a reader's yield = flow x
     interval / (distance x width) is the clean, rescaled yield. widths=False keeps the logged widths: a warning gives
     how many readings of the clean file were narrowed or shortened, whose yields on the card are then not the clean
     file's.
  3  factors={machine: factor}: the grain mass of every task of that combine multiplied by the factor, by scaling the
     task's calibration curve (.tsh[5:27], 11 x uint16, flow = (curve(u) - 1000) / 100: curve' = 1000 + f x
     (curve - 1000) on every defined point, point 0 included when it is not 1000, which moves the low-flow cut-off by
     the same factor) and the display's own total weight; the curve is stored in whole units, so the factor is met to
     about 1e-4 of the flow (the check gives the largest deviation).

Record checksum. Every CNH1 record carries an 8-bit checksum at header byte [8]:
    rec[8] = (rec[9] + sum(rec[10:])) mod 256          (rec[9] is a per-file-type constant, kept)
It holds on every complete record of the cards checked (every file type, catalogue files included; the one exception
is a record cut short at the end of a file). Bytes changed without it are a likely reason for a vendor reader to skip
the harvest logs of a card whose task ids were renamed by hand. The writer
recomputes it for every record it changes and checks every record of every file it writes. The .tso and .tsh of a
task hold one record each (on every card seen); a file of several records is refused.

Counts and totals of a task (the .tso / .tsh / .tst records): what they follow (stored value against the record
quantity it tracks) and what the writer does:
    .tso[163:167]  logging records (bit 0 of .tlo[0])        = the count: decreased by the readings removed (both
                                                               modes)
    .tso[167:171]  records with logging off                   = the count: increased by the readings whose logging bit
                                                               is cleared
    .tso[171:175]  logging records with a valid flow sample  about that count: scaled by that count left / before
    .tso[183:187]  logged distance, cm                        about sum(speed x 1 s) over the logging records: scaled
                                                               likewise
    .tso[187:191]  header-up distance, cm                     about sum(speed x 1 s) over the records with logging
                                                               off: the distance of the records whose logging
                                                               bit is cleared moves here from [183] (the task's total
                                                               distance stays); unchanged in "drop" mode for the
                                                               records taken out
    .tso[195:199]  the display's area counter, x 0.01 m2     shown by SMS as the dataset's Area: see totals
    .tso[199:203]  (newer display software) a share of the logging records: scaled by the logging records left /
                                                               before (meaning inferred, not established)
    .tso[203:207]  (same tasks)                               a multiple of the logged distance: scaled like [183]
                                                               (meaning inferred, not established)
    .tso[175:179]  a multiple of the records with logging off: no rule found, left as it is (STALE in "header_up"
                   mode, where the logging-off records grow); [179:183], [191:195], .tst and the task's times: not
                   about readings (no word follows a record quantity), unchanged
    .tsh[29:89]    calibration bins: seconds and raw-count sums per curve segment (what SMS's Summary weighs)
    .tsh[96:100]   the display's total weight, kg; [100:104] kg x moisture (the Summary's moisture)
    .tsh[89:93], [4] bit 3   scale weight of a calibration load and its flag: unchanged (a warning names the task)
The totals of the Summary (area counter, bins, weight, kg x moisture), option totals:
    "points" (default)  set from the kept readings as SMS reads them from the written card (interval byte basis): the
                        area = their area, the bins = their seconds and their raw counts compensated so that the bins
                        weigh exactly their wet mass on the task's (written) curve, the weight and kg x moisture = their
                        mass and mass x moisture. The Summary SMS should show is then the clean points' area and wet
                        weight (to the bins' whole seconds); the dry volume differs by the one-sided shrink taken at
                        the average moisture instead of per point.
    "scaled"            the display's own accumulators reduced in proportion to what is left (the original card's
                        ratio of display totals to its points is kept: a display that counted more area than its
                        readings still does on the written card).
    "original"          only the record counts change.
The display totals are the display's own accumulators (they count records the log does not hold, on the display
clock), so only "points" makes the Summary agree with the clean file. write_clean returns the Summary expected for the
written card (the decoder's report["sms_summary"] of it: "expected_summary"), the clean file's own totals
("clean_totals") and their relative differences ("summary_vs_clean"), with a warning above SUMMARY_TOL.
With nothing removed and nothing changed every ratio is exactly 1 and every file of "scaled" / "original" is the
original byte for byte ("points" rewrites the totals of the Summary even then).

Identifiers. The vendor software refuses a card whose FOLDER NAME it has already archived (its vault is keyed on
<name>.cn1, not on the content: a card is read again only under a new folder name); renaming task ids
inside a card made it skip the harvest logs. new_ids=True therefore gives every written card a new folder name in the
display's pattern (YYMMDD, hour letter A = 0 h, minute // 6: the time of writing) and keeps every id inside the card.
The names already used are kept in a small registry (a JSON file, by default <out_dir>/../cn1_card_names.json; pass
registry= one file for the whole work space) together with every .cn1 folder under out_dir and the input cards'
names: a name is never given twice. card_names={original card folder name: new name} sets the names by hand. The task
ids are those of the original card: read the written card into a project that does not hold the original card's
datasets.

What the written card holds: per card, every file outside the field folders (index.vy1, COMBINES/, shared/ catalogue
files, log/ - whatever the case of their names, each file under its own name), and in the field folders only the
files of the cleaned tasks, under their own names. Tasks with no kept reading, tasks of the card that were not decoded,
and the field's other files (.ags guidance lines) are left out (listed in the notes). A partial card copy (no
index.vy1) is refused: the vendor software reads a <name>.cn1 folder with its index file only. The output is never
written inside the input folder, and the input is never changed.

THE KEY from a clean row back to the raw records: (Dataset, Obj__Id) of the clean row -> the row of the decoded file
(source["decoded_shp"], the readings in the order the decoder wrote them) -> the task's records, by aligning the
decoded rows with the writer's own reading of the task's streams on (Time, position, moisture) in record order (the
decoded rows are the task's readings in .tlo order, or a subsequence of them for an older decoder that read only the
first record of a repeated counter). Every clean row is then checked on Time and moisture. (Machine, Time) alone is
NOT a key: the display clock has 1 s steps and repeats seconds. No decoder column is added.

Pure engine code (no Streamlit, no app import).
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
import re
import shutil
import struct
import zipfile

import numpy as np
import pandas as pd

from engine.formats import cnh_cn1 as C
from engine.formats.common import DecodeOptions, FT_PER_M, LB_PER_KG, SQFT_PER_AC, dataset_name

FORMAT_ID = C.FORMAT_ID
LABEL = "Case IH / New Holland AFS Pro 700 card (.cn1)"
TASK_EXTS = C.TASK_EXTS
TLT_LEN = 14                                     # .tlt payload bytes (the record is joined, not decoded)
MODES = ("header_up", "drop")
TOTALS = ("points", "scaled", "original")
DEFAULT_MODE, DEFAULT_TOTALS = "header_up", "points"
POS_TOL_DEG = 1e-9                               # a clean position farther than this from the decoded one is a move
HOUR_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWX"        # card name: YYMMDD + hour letter + digit
SUMMARY_TOL = 0.03                               # warn when the expected Summary and the clean totals differ by more
REGISTRY_NAME = "cn1_card_names.json"
NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
CAVEAT = ("not yet tested in SMS: the written card is checked with OCED's decoder only; read it into a scratch SMS "
          "project (Read File(s) > Case IH > AFS Pro 700, the Processing Settings of the raw read) before using it")


class CardWriteError(ValueError):
    """The clean file or the card cannot be written back in this format (a plain message for the user)."""


# ===================================================================================================== records
def checksum(rec) -> int:
    """The 8-bit checksum a CNH1 record carries at header byte [8]: (rec[9] + sum(rec[10:])) mod 256."""
    return (rec[9] + sum(rec[10:])) & 0xFF


def set_checksum(buf: bytearray, off: int, size: int) -> None:
    buf[off + 8] = (buf[off + 9] + sum(buf[off + 10:off + size])) & 0xFF


def check_file(path: str) -> tuple[int, int, int]:
    """(records, records with a wrong checksum or cut short, bytes outside records) of a CNH1 file."""
    b = open(path, "rb").read()
    n = bad = stray = i = 0
    while i <= len(b) - C.HDR:
        if b[i:i + 4] != C.MAGIC:
            j = b.find(C.MAGIC, i + 1)
            stray += (len(b) if j < 0 else j) - i
            if j < 0:
                return n, bad, stray
            i = j
            continue
        size = C.HDR + struct.unpack_from("<I", b, i + 4)[0]
        n += 1
        if i + size > len(b):
            bad += 1
            stray += len(b) - i
            return n, bad, stray
        bad += checksum(b[i:i + size]) != b[i + 8]
        i += size
    return n, bad, stray + max(0, len(b) - i)


def stream_index(b: bytes, length: int):
    """Offsets and sizes of the records of a log stream that C.read_stream returns (payload >= length), in file order:
    the record i of read_stream's arrays starts at offsets[i]."""
    if len(b) >= C.HDR + 4 and b[:4] == C.MAGIC:
        n0 = struct.unpack_from("<I", b, 4)[0]
        st = C.HDR + n0
        if n0 >= length and len(b) % st == 0:
            R = np.frombuffer(b, np.uint8).reshape(-1, st)
            if (R[:, :4] == np.frombuffer(C.MAGIC, np.uint8)).all() and (R[:, 4:8].copy().view("<u4").ravel() == n0).all():
                k = len(R)
                return np.arange(k, dtype=np.int64) * st, np.full(k, st, np.int64)
    offs, sizes, i = [], [], 0
    while i <= len(b) - C.HDR:
        if b[i:i + 4] != C.MAGIC:
            j = b.find(C.MAGIC, i + 1)
            if j < 0:
                break
            i = j
            continue
        n = struct.unpack_from("<I", b, i + 4)[0]
        if n >= length:
            offs.append(i)
            sizes.append(min(C.HDR + n, len(b) - i))
        i += C.HDR + n
    return np.array(offs, np.int64), np.array(sizes, np.int64)


def _counters(b: bytes, offs):
    return np.array([struct.unpack_from("<I", b, int(o) + 11)[0] for o in offs], np.int64) if len(offs) else \
        np.zeros(0, np.int64)


def _join_index(co, cx):
    """For every .tlo record, the index of the record of another stream with the same (run, counter) - the join of
    C.read_task - or -1 (also for a repeated key after its first record, which read_task does not read)."""
    ro, rx = C.stream_runs(co), C.stream_runs(cx)
    paired = (int(ro[-1]) + 1 if len(ro) else 0) == (int(rx[-1]) + 1 if len(rx) else 0)
    ko, kx = ((ro << 32) | co, (rx << 32) | cx) if paired else (co, cx)
    out = np.full(len(ko), -1, np.int64)
    if len(kx) and len(ko):
        kx_u, ix = np.unique(kx, return_index=True)
        pos = np.clip(np.searchsorted(kx_u, ko), 0, len(kx_u) - 1)
        hit = kx_u[pos] == ko
        out = np.where(hit, ix[pos], -1)
    first = np.zeros(len(ko), bool)
    if len(ko):
        _, io_first = np.unique(ko, return_index=True)
        first[io_first] = True
    return np.where(first, out, -1)


class TaskStreams:
    """The three log streams of one task (files = the catalogue row's {extension: path}, any case), and for every row
    of C.read_task (the joined records) the index of its record in each stream. Raises when the join no longer
    reproduces the decoder's."""

    def __init__(self, files: dict):
        self.files = files
        self.bytes, self.offs, self.sizes = {}, {}, {}
        for ext, L in ((".tlo", C.TLO_LEN), (".tlh", C.TLH_LEN), (".tlt", TLT_LEN)):
            p = files.get(ext)
            if p and os.path.isfile(p):
                b = open(p, "rb").read()
                self.bytes[ext] = b
                self.offs[ext], self.sizes[ext] = stream_index(b, L)
        name = os.path.basename(files[".tso"])
        co = _counters(self.bytes[".tlo"], self.offs[".tlo"])
        ch = _counters(self.bytes[".tlh"], self.offs[".tlh"])
        jh = _join_index(co, ch)
        rows = np.nonzero(jh >= 0)[0]
        self.io, self.ih = rows, jh[rows]
        self.co, self.ch, self.ct = co, ch, None
        if ".tlt" in self.bytes:
            self.ct = _counters(self.bytes[".tlt"], self.offs[".tlt"])
            self.it = _join_index(co, self.ct)[rows]
        else:
            self.it = np.full(len(rows), -1, np.int64)
        self.df, self.notes = C.read_task(os.path.splitext(files[".tso"])[0])
        if len(self.df) != len(self.io) or not np.array_equal(self.df["ctr"].to_numpy(), co[self.io]):
            raise RuntimeError(f"{name}: the writer's stream join does not reproduce the decoder's "
                               f"({len(self.io)} vs {len(self.df)} records): engine/formats/cnh_cn1.py read_task changed")
        bh = self.bytes[".tlh"]
        hA = np.array([struct.unpack_from("<H", bh, int(self.offs[".tlh"][k]) + C.HDR + 1)[0] for k in self.ih], float)
        if not np.array_equal(hA, self.df["hA"].to_numpy(float)):
            raise RuntimeError(f"{name}: the .tlh records of the writer's join differ from the decoder's")


# ===================================================================================================== source
def _source_parts(source: dict):
    """(decode report, input root, unit ids, DecodeOptions, decoder kwargs, decoded shapefile) of a decode."""
    if not isinstance(source, dict):
        raise CardWriteError("no decode of a raw card: the clean data did not come from a Case IH / New Holland card")
    rep = source.get("report")
    if rep is None and source.get("decode_report") and os.path.isfile(source["decode_report"]):
        with open(source["decode_report"], encoding="utf-8") as f:
            rep = json.load(f)
    rep = rep or {}
    fmt = source.get("format") or rep.get("format")
    if fmt != FORMAT_ID:
        raise CardWriteError(f"this writer writes {FORMAT_ID} cards; the source was decoded by {fmt!r}")
    root = source.get("input_root") or rep.get("input_root")
    if not root or not os.path.isdir(root):
        raise CardWriteError(f"the card the data was decoded from is not on this computer any more ({root!r}): open the "
                             "raw input again and decode it")
    units = source.get("unit_ids") or [u["id"] for u in (rep.get("units") or []) if isinstance(u, dict) and u.get("id")]
    if not units:
        raise CardWriteError("the decode report lists no decoded task (units)")
    o = dict(source.get("options") or rep.get("options") or {})
    names = {f.name for f in dataclasses.fields(DecodeOptions)}
    opts = DecodeOptions(**{k: v for k, v in o.items() if k in names})
    kw = dict(source.get("decoder_kwargs") or rep.get("decoder_kwargs") or {})
    return rep, root, list(units), opts, kw, source.get("decoded_shp")


def can_write(source: dict | None) -> tuple[bool, str]:
    """(True, "") when write_clean can write this decode back as a card, else (False, the reason). Cheap: reads the
    decode report and looks for each decoded task's card (index.vy1, any case) and .tso; decodes nothing."""
    try:
        _rep, root, units, _o, _k, _d = _source_parts(source)
    except ValueError as e:
        return False, str(e)
    partial, gone = [], []
    for u in units:
        rel_card, _, rel_task = str(u).partition("::")
        card = os.path.normpath(os.path.join(root, rel_card)) if rel_card not in ("", ".") else root
        if not os.path.isdir(card):
            gone.append(u)
        elif not C._is_card(card):
            partial.append(u)
        elif rel_task and not C.task_file(os.path.join(card, rel_task), ".tso"):
            gone.append(u)
    if gone:
        return False, f"{len(gone)} decoded task(s) are not on the card under {root} any more: decode the raw input again"
    if partial:
        return False, ("the data was decoded from a partial copy of the card (no index.vy1 / INDEX.VY1): the vendor "
                       "software reads a <name>.cn1 folder with its index file only; upload the whole card folder")
    return True, ""


def _readings(r: dict, ts: TaskStreams, opts: DecodeOptions):
    """The readings of one task as the decoder makes them: (rows of ts.df, Time strings, lon, lat, moisture, Dataset)."""
    df = ts.df
    keep, _ = C.select_readings(df)
    rows = np.nonzero(keep)[0]
    g = df.iloc[rows]
    mid_ok = ~g.ends_bad.to_numpy()
    lat = np.where(mid_ok, (g.latL.to_numpy() + g.latR.to_numpy()) / 2, g.lat0.to_numpy())
    lon = np.where(mid_ok, (g.lonL.to_numpy() + g.lonR.to_numpy()) / 2, g.lon0.to_numpy())
    tloc = g.disp_time
    if opts.tz_offset_h is not None:
        off = C._utc_offset_h(df)
        if off is not None:
            tloc = tloc + pd.to_timedelta(opts.tz_offset_h - off, unit="h")
    times = tloc.dt.strftime("%Y-%m-%d %H:%M:%S.0").to_numpy() if len(g) else np.array([], object)
    ds = dataset_name(r["task"], r["start"] if not pd.isna(r["start"]) else g.disp_time.min()) if len(g) else r["task"]
    return rows, times, lon, lat, g.hB.to_numpy() / 10.0, ds


def _align(dec_rows: pd.DataFrame, times, lon, lat, moist):
    """Reading index (into the task's readings) of every decoded row, matched in order on (Time, position,
    moisture). The decoded rows (sorted by Obj__Id) are the task's readings or an ordered subset of them."""
    n = len(times)
    out = np.full(len(dec_rows), -1, np.int64)
    t, x, y, m = (dec_rows["Time"].astype(str).to_numpy(), dec_rows["_lon"].to_numpy(float),
                  dec_rows["_lat"].to_numpy(float), dec_rows["Moisture__"].to_numpy(float))
    j = 0
    for k in range(len(dec_rows)):
        while j < n and not (times[j] == t[k] and abs(lon[j] - x[k]) < 1e-7 and abs(lat[j] - y[k]) < 1e-7
                             and abs(moist[j] - m[k]) < 0.051):
            j += 1
        if j >= n:
            break
        out[k] = j
        j += 1
    return out


def _point_totals(df) -> dict:
    """Totals of a set of points in the standard schema: n, area (Distance_f x Swth_Wdth_), wet lb (Yld_Mass_W x
    area), dry bu (Yld_Vol_Dr x area), dry bu/ac, moisture weighted by the area."""
    if df is None or not len(df):
        return {"n": 0, "area_ac": 0.0, "wet_lb": 0.0, "dry_bu": 0.0, "bu_ac": None, "moisture_pct": None}

    def num(c):
        return pd.to_numeric(df[c], errors="coerce").to_numpy(float) if c in df.columns else np.full(len(df), np.nan)
    a = num("Distance_f") * num("Swth_Wdth_") / SQFT_PER_AC
    ok = np.isfinite(a) & (a > 0)
    area = float(a[ok].sum())
    wet = float(np.nansum((num("Yld_Mass_W") * a)[ok]))
    dry = float(np.nansum((num("Yld_Vol_Dr") * a)[ok]))
    m = num("Moisture__")
    k = ok & np.isfinite(m)
    return {"n": int(len(df)), "area_ac": area, "wet_lb": wet, "dry_bu": dry, "bu_ac": dry / area if area > 0 else None,
            "moisture_pct": float((m[k] * a[k]).sum() / a[k].sum()) if k.any() and a[k].sum() > 0 else None}


def _rel(a, b):
    return None if a is None or b is None or not b else float(a) / float(b) - 1.0


# ===================================================================================================== writing
def _inside(path: str, folder: str) -> bool:
    """True when path is folder or lies inside it (case and separators ignored, links resolved)."""
    p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    f = os.path.normcase(os.path.realpath(os.path.abspath(folder)))
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def _read_registry(path: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return [x for x in (d.get("cards") if isinstance(d, dict) else d) or [] if isinstance(x, dict)]
    except (OSError, ValueError):
        return []


def _taken_names(registry: str, out_dir: str, root: str) -> set:
    """Lower-case card names (without .cn1) that must not be given again: the registry's, every .cn1 folder under
    out_dir (three levels) and every card folder of the input."""
    taken = {str(x.get("name", "")).lower() for x in _read_registry(registry)}
    base = out_dir.rstrip("\\/").count(os.sep)
    for d, dirs, _ in os.walk(out_dir):
        if d.count(os.sep) - base >= 3:
            dirs[:] = []
        for x in dirs:
            if x.lower().endswith(".cn1"):
                taken.add(x[:-4].lower())
    for card, _ in C.find_cards(root):
        nm = os.path.basename(card.rstrip("\\/"))
        taken.add((nm[:-4] if nm.lower().endswith(".cn1") else nm).lower())
    taken.discard("")
    return taken


def _new_card_name(old: str, taken: set, now=None) -> str:
    """A card folder name as the display makes it - YYMMDD, the hour as a letter (A = 0 h) and the minute // 6 (the
    name of the display's session log, log/<name>.txt, on the cards seen) - at the time of writing; the next free one
    when it is the old name or already taken."""
    now = now or _dt.datetime.now()
    day = now.strftime("%y%m%d")
    first = HOUR_LETTERS[now.hour]
    d0 = str(now.minute // 6)
    for c1 in [first] + [c for c in HOUR_LETTERS if c != first]:
        for c2 in d0 + "".join(c for c in "0123456789" if c != d0):
            name = f"{day}{c1}{c2}"
            if name.lower() != old.lower() and name.lower() not in taken:
                taken.add(name.lower())
                return name
    raise CardWriteError("no free card name left for today (240 names a day): pass card_names= to name the cards")


def _copy_skeleton(card: str, dst: str) -> int:
    """Copy every file of the card except those inside field folders (*.fld, any case), each under its own name.
    Returns the number of files."""
    n = 0
    for d, dirs, files in os.walk(card):
        dirs[:] = [x for x in sorted(dirs) if not x.lower().endswith(".fld")]
        rel = os.path.relpath(d, card)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            shutil.copyfile(os.path.join(d, f), os.path.join(dst, rel, f))
            n += 1
    return n


def _on_disk(path: str) -> str:
    """path with its file name spelt as the folder lists it (on a case-insensitive file system C.task_file can return
    'X.tlo' for the file 'X.TLO'; the written card keeps the original spelling)."""
    d, n = os.path.split(path)
    try:
        hit = {x.lower(): x for x in os.listdir(d)}.get(n.lower())
    except OSError:
        hit = None
    return os.path.join(d, hit) if hit else path


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _cut(b: bytes, offs, sizes, drop) -> bytes:
    """b without the records `drop` (indices into offs / sizes); every other byte kept, in order."""
    drop = np.unique(np.asarray(drop, np.int64))
    drop = drop[drop >= 0]
    if not len(drop):
        return bytes(b)
    parts, cur = [], 0
    for k in drop:
        o, s = int(offs[k]), int(sizes[k])
        parts.append(b[cur:o])
        cur = o + s
    parts.append(b[cur:])
    return b"".join(parts)


def _run_edges(ctr, idx):
    """True where the stream record idx is the last record before, or the first record after, a place where the
    record counter goes back (a display restart: C.stream_runs). idx -1 = no record."""
    idx = np.asarray(idx, np.int64)
    out = np.zeros(len(idx), bool)
    if ctr is None or len(ctr) < 2 or not len(idx):
        return out
    back = np.nonzero(np.diff(np.asarray(ctr, np.int64)) <= 0)[0]
    if not len(back):
        return out
    edge = np.zeros(len(ctr), bool)
    edge[back] = True
    edge[back + 1] = True
    ok = idx >= 0
    out[ok] = edge[idx[ok]]
    return out


def _scaled(v: int, num: float, den: float) -> int:
    if den <= 0 or num == den:
        return int(v)
    return int(max(0, round(v * num / den)))


def _one_record(b: bytes, what: str) -> None:
    if len(b) < C.HDR or b[:4] != C.MAGIC or C.HDR + struct.unpack_from("<I", b, 4)[0] != len(b):
        raise CardWriteError(f"{what}: not one CNH1 record (the writer rewrites a task's .tso / .tsh as one record)")


def _tsh(b: bytes):
    p = b[C.HDR:]
    full = len(p) >= C.TSH_TOTALS
    return dict(flags=p[4], curve=np.array(struct.unpack_from("<11H", p, 5), float), comp=struct.unpack_from("<H", p, 27)[0],
                offset=(p[95] - 100) / 10.0 if full else 0.0,
                scale_kg=struct.unpack_from("<I", p, 89)[0] / 10.0 if full else 0.0, full=full)


def points_bins(hA, moisture, dur_s, curve, comp, offset):
    """The .tsh totals of a set of readings as the Summary weighs them (module docstring, totals="points"):
    (seconds[10] uint16, counts[10] uint32, kg, kg x sensor moisture) such that C.bins_wet_lb(seconds, counts, the
    average moisture, curve, comp) is the readings' wet mass (sum of flow x duration on `curve`), up to the bins'
    whole seconds and counts."""
    hA, M, d = (np.asarray(x, float) for x in (hA, moisture, dur_s))
    flow, _ = C.flow_lb_s(hA, M, curve, comp)
    wet = flow * d
    kg = wet / LB_PER_KG
    kg_t = int(round(float(kg.sum())))
    kgm = int(max(0, round(float((kg * (M - offset)).sum()))))
    m_avg = kgm / kg_t + offset if kg_t else None
    k = 1.0 + comp / 1e4 * (C.MOIST_REF - (C.MOIST_REF if m_avg is None else m_avg))
    last = C.curve_last_point(curve)
    seg = np.clip(np.floor(hA / C.RAW_STEP).astype(np.int64), 0, C.BINS - 1)
    secs = np.zeros(C.BINS, np.int64)
    cnts = np.zeros(C.BINS, np.int64)
    for i in range(C.BINS):
        s = seg == i
        if not s.any():
            continue
        n_i = int(min(65535, max(0, round(float(d[s].sum())))))
        secs[i] = n_i
        if n_i == 0 or last < 1:
            continue
        j = min(i, last - 1)
        slope = (curve[j + 1] - curve[j]) * C.FLOW_SCALE_LB_S
        a = (curve[j] - j * (curve[j + 1] - curve[j]) - C.FLOW_ZERO) * C.FLOW_SCALE_LB_S
        if slope > 0 and k > 0:
            u = (float(wet[s].sum()) / n_i - a) / slope              # the mean compensated count that weighs it
            cnts[i] = int(min(2 ** 32 - 1, max(0, round(u * C.RAW_STEP / k * n_i))))
        else:
            cnts[i] = int(min(2 ** 32 - 1, round(float((hA[s] * d[s]).sum()))))
    return secs, cnts, kg_t, kgm


def write_clean(source: dict, clean_shp: str, out_dir: str, *, widths: bool = True, factors: dict | None = None,
                new_ids: bool = True, log=print, mode: str = DEFAULT_MODE, totals: str = DEFAULT_TOTALS,
                verify: bool = True, card_names: dict | None = None, registry: str | None = None,
                out_name: str | None = None) -> dict:
    """Write the clean readings of clean_shp back into copies of the cards they were decoded from (module docstring).

    source = engine.run.decode(...)["source"]: its decode report gives the card folder (input_root), the tasks (units)
    and the decode options; its decoded_shp the readings in decoder order. clean_shp = the clean point file (a subset
    of the decoded readings; Dataset, Obj__Id, Time and Moisture__ as decoded). factors = {Machine: factor} or None.
    Advanced options: mode "header_up" (default: the removed readings' records get their logging bit cleared) or
    "drop" (their records are taken out); totals "points" (default: the Summary = the kept readings), "scaled" (the
    display's totals in proportion) or "original"; verify (decode the written card and compare, default True);
    card_names {original card folder name: new folder name} (else new names in the display's pattern when new_ids);
    registry = the JSON file of the card names already written (default <out_dir>/../cn1_card_names.json);
    out_name = the name of the folder in out_dir that holds the card(s) (default <clean file name>_cn1).
    Returns {"path": the folder holding the written card(s), "zip", "cards", "n_kept", "n_removed", "files_changed",
    "notes", "warnings", "tasks", "expected_summary", "clean_totals", "summary_vs_clean", "check", ...}.
    Raises CardWriteError (a ValueError) with a plain message when it cannot write."""
    import pyogrio

    if mode not in MODES:
        raise CardWriteError(f"mode must be one of {MODES}")
    if totals not in TOTALS:
        raise CardWriteError(f"totals must be one of {TOTALS}")
    rep, root, unit_ids, opts, kw, decoded_shp = _source_parts(source)
    if not clean_shp or not os.path.isfile(clean_shp):
        raise CardWriteError(f"the clean file {clean_shp!r} is not there")
    out_dir = os.path.abspath(out_dir)
    if _inside(out_dir, root):
        raise CardWriteError("the output folder is inside the input card's folder: choose a folder outside it (the "
                             "written card would be read as part of the input)")
    factors = {str(k): float(v) for k, v in (factors or {}).items() if v is not None}
    notes, warnings = [], []
    rows, _cards = C.catalogue(root)
    by_id = {r["id"]: r for r in rows}
    missing = [u for u in unit_ids if u not in by_id]
    if missing:
        raise CardWriteError(f"the decoded tasks {missing[:3]} are not on the card under {root} any more")
    partial = sorted({os.path.basename(by_id[u]["card"]) for u in unit_ids if not by_id[u]["card_complete"]})
    if partial:
        raise CardWriteError(f"{', '.join(partial[:3])}: a partial copy of the card (no index.vy1 / INDEX.VY1): the "
                             "vendor software reads a <name>.cn1 folder with its index file only; upload the whole card")

    # ---- the clean rows and the decoded rows
    clean = pyogrio.read_dataframe(clean_shp)
    if not len(clean):
        raise CardWriteError("the clean file has no readings: there is nothing to write")
    for c in ("Dataset", "Obj__Id", "Time", "Moisture__", "Swth_Wdth_", "Distance_f"):
        if c not in clean.columns:
            raise CardWriteError(f"the clean file has no {c} column: it is not a file OCED cleaned from a decoded card")
    clean["_lon"], clean["_lat"] = clean.geometry.x.to_numpy(), clean.geometry.y.to_numpy()
    if decoded_shp and os.path.isfile(decoded_shp):
        dec = pyogrio.read_dataframe(decoded_shp)
        dec["_lon"], dec["_lat"] = dec.geometry.x.to_numpy(), dec.geometry.y.to_numpy()
        dec = pd.DataFrame(dec.drop(columns="geometry"))
    else:
        dec = None
        warnings.append("the decoded file of this decode is not on this computer: the clean rows are matched to the "
                        "card by Obj__Id under the current decoder (checked on Time and moisture)")
    record_time = ((rep.get("calibration") or {}).get("record_time")) or kw.get("time_basis")

    if out_name is not None and (not str(out_name).strip() or any(c in str(out_name) for c in '/\\:')):
        raise CardWriteError(f"the output folder name {out_name!r} is not a plain folder name")
    out_root = os.path.join(out_dir, str(out_name) if out_name else
                            os.path.splitext(os.path.basename(clean_shp))[0] + "_cn1")
    if _inside(root, out_root) or _inside(clean_shp, out_root):
        raise CardWriteError(f"{out_root} holds the input card or the clean file: choose another output folder")
    os.makedirs(out_dir, exist_ok=True)
    if os.path.isdir(out_root):
        if any(not (x.lower().endswith(".cn1") and os.path.isdir(os.path.join(out_root, x))) for x in os.listdir(out_root)):
            raise CardWriteError(f"{out_root} exists and holds other files: choose another output folder")
    reg_path = os.path.abspath(registry) if registry else os.path.join(os.path.dirname(out_dir), REGISTRY_NAME)
    taken = _taken_names(reg_path, out_dir, root)

    # ---- per task: readings, decoded rows, kept / removed readings
    plans, n_kept, n_removed = [], 0, 0
    clean_ds = clean["Dataset"].astype(str).to_numpy()
    clean_oid = clean["Obj__Id"].astype(np.int64).to_numpy()
    matched = np.zeros(len(clean), bool)
    for uid in unit_ids:
        r = by_id[uid]
        if not r["has_log"]:
            notes.append(f"{r['task']}: totals only (no log on the card): not written")
            continue
        ts = TaskStreams(r["files"])
        rws, times, lon, lat, moist, ds = _readings(r, ts, opts)
        sel = np.nonzero(clean_ds == ds)[0]
        if dec is not None:
            d = dec[dec["Dataset"].astype(str) == ds].sort_values("Obj__Id")
            pos = _align(d, times, lon, lat, moist)
            if (pos < 0).any():
                raise CardWriteError(f"{r['task']}: {int((pos < 0).sum())} of the {len(d)} decoded readings were not "
                                     "found on the card (the card or the decoder changed since the decode)")
            oids = d["Obj__Id"].astype(np.int64).to_numpy()
            dsw, dsd = d["Swth_Wdth_"].to_numpy(float), d["Distance_f"].to_numpy(float)
            dlon, dlat = d["_lon"].to_numpy(float), d["_lat"].to_numpy(float)
        else:
            pos = np.arange(len(rws))
            oids = pos + 1
            g = ts.df.iloc[rws]
            dsw = g["width_m"].to_numpy(float) * FT_PER_M
            spd = g["dist_mm"].to_numpy(float) / 1000.0 / g["dt_byte"].to_numpy(float)
            dsd = (g["dist_mm"].to_numpy(float) / 1000.0 if record_time != "period" else spd * C._period_s(ts.df)[0]) * FT_PER_M
            dlon, dlat = lon, lat
        o2k = {int(o): k for k, o in enumerate(oids)}
        kk = np.array([o2k.get(int(o), -1) for o in clean_oid[sel]], np.int64)
        if (kk < 0).any():
            raise CardWriteError(f"{r['task']}: {int((kk < 0).sum())} clean rows have an Obj__Id this decode does not have")
        kept_read = pos[kk]
        if len(np.unique(kept_read)) != len(kept_read):
            raise CardWriteError(f"{r['task']}: the clean file holds a reading twice")
        bad = (clean["Time"].astype(str).to_numpy()[sel] != times[kept_read]) | \
              (np.abs(clean["Moisture__"].to_numpy(float)[sel] - moist[kept_read]) > 0.051)
        if bad.any():
            raise CardWriteError(f"{r['task']}: {int(bad.sum())} clean rows do not match their reading on the card (Time "
                                 "/ moisture): the clean file is not from this decode")
        matched[sel] = True
        # every reading of the task that is not in the clean file goes, also the ones the decoder of the clean file
        # did not make (an older decoder read only the first record of a counter repeated after a display restart)
        removed_read = np.setdiff1d(np.arange(len(rws)), kept_read)
        unseen = len(rws) - len(pos)
        if unseen:
            notes.append(f"{r['task']}: {unseen} readings of the card are not in the decoded file (an older decoder "
                         "did not read them): they are not in the clean file and are left out too")
        n_kept += len(sel)
        n_removed += len(removed_read)
        cv = {"Swth_Wdth_": clean["Swth_Wdth_"].to_numpy(float)[sel], "Distance_f": clean["Distance_f"].to_numpy(float)[sel],
              "_lon": clean["_lon"].to_numpy(float)[sel], "_lat": clean["_lat"].to_numpy(float)[sel],
              "Swth_dec": dsw[kk], "Dist_dec": dsd[kk], "lon_dec": dlon[kk], "lat_dec": dlat[kk]}
        plans.append(dict(r=r, ts=ts, rws=rws, sel=sel, kept_read=kept_read, removed_read=removed_read, ds=ds, cv=cv,
                          n_decoded=int(len(pos))))
    if not matched.all():
        other = sorted(set(clean_ds[~matched]))[:5]
        raise CardWriteError(f"{int((~matched).sum())} clean rows belong to datasets that are not tasks of this decode: "
                             f"{other}")
    if not widths:
        ch = [(P["cv"], (np.abs(P["cv"]["Swth_Wdth_"] - P["cv"]["Swth_dec"]) > 1e-6)
               | (np.abs(P["cv"]["Distance_f"] - P["cv"]["Dist_dec"]) > 1e-6)) for P in plans]
        n_ch = int(sum(int(m.sum()) for _, m in ch))
        if n_ch:
            dev = max(float(np.max(np.abs(v["Swth_dec"][m] * v["Dist_dec"][m] / (v["Swth_Wdth_"][m] * v["Distance_f"][m])
                                          - 1))) for v, m in ch if m.any())
            warnings.append(f"widths=False: {n_ch:,} readings of the clean file were narrowed or shortened by Optimize "
                            "Swath Widths; the card keeps their logged widths and distances, so their yields on the "
                            f"card differ from the clean file's (by up to {100 * dev:.1f} %)")

    # ---- the card names
    card_order = []
    for P in plans:
        if len(P["sel"]) and P["r"]["card"] not in card_order:
            card_order.append(P["r"]["card"])
    names_by_card = {}
    given = {str(k).lower().removesuffix(".cn1"): str(v) for k, v in (card_names or {}).items()}
    for card in card_order:
        old = os.path.basename(card.rstrip("\\/"))
        stem, ext = (old[:-4], old[-4:]) if old.lower().endswith(".cn1") else (old, ".cn1")
        if stem.lower() in given:
            nm = given[stem.lower()].removesuffix(".cn1").removesuffix(".CN1")
            if not NAME_RE.fullmatch(nm):
                raise CardWriteError(f"card name {nm!r}: letters, digits, '_' and '-' only (up to 64)")
            if nm.lower() in taken:
                raise CardWriteError(f"card name {nm!r} is already used (an earlier write, the output folder or the "
                                     "input): SMS refuses a card name it has archived; choose another")
            taken.add(nm.lower())
        elif new_ids:
            nm = _new_card_name(stem, taken)
        else:
            nm = stem
            warnings.append(f"{old}: new_ids=False keeps the card's own folder name: SMS refuses a card name it has "
                            "already archived (read it into a project that never read the original card)")
        names_by_card[card] = nm + ext

    # ---- write each card: a card written before in out_root is replaced only now, after every refusal above
    if os.path.isdir(out_root):
        shutil.rmtree(out_root)
    os.makedirs(out_root)
    tasks_rep, files_changed = [], []
    for card in card_order:
        old = os.path.basename(card.rstrip("\\/"))
        nf = _copy_skeleton(card, os.path.join(out_root, names_by_card[card]))
        notes.append(f"card {old} -> {names_by_card[card]}: {nf} files outside the field folders copied byte for byte")
    for P in plans:
        r = P["r"]
        if not len(P["sel"]):
            notes.append(f"{r['task']}: no reading kept: the task is left out of the written card")
            tasks_rep.append(dict(task=r["task"], dataset=P["ds"], machine=r["vehicle"], kept=0,
                                  removed=int(len(P["removed_read"])), written=False))
            continue
        out_card = os.path.join(out_root, names_by_card[r["card"]])
        info, dst = _write_task(P, out_card, widths, factors.get(str(r["vehicle"])), mode, totals, kw, warnings)
        tasks_rep.append(info)
        for ext, p in r["files"].items():
            if p and dst.get(ext) and os.path.isfile(dst[ext]):
                if open(p, "rb").read() != open(dst[ext], "rb").read():
                    files_changed.append(os.path.relpath(dst[ext], out_root).replace("\\", "/"))
    written_tasks = {P["r"]["task"].lower() for P in plans if len(P["sel"])}
    for card, name in names_by_card.items():
        for f in sorted({os.path.dirname(P["r"]["files"][".tso"]) for P in plans if P["r"]["card"] == card}):
            left = [x for x in os.listdir(f) if os.path.splitext(x)[0].lower() not in written_tasks]
            if left:
                notes.append(f"{name}/{os.path.relpath(f, card)}: {len(left)} other files of the field folder (other "
                             "tasks, guidance lines) left out")
    unused = [r for r in rows if r["card"] in names_by_card and r["id"] not in unit_ids]
    if unused:
        notes.append(f"{len(unused)} other task(s) of the card(s) were not decoded and are not written")
    mx = [m for m in factors if m not in {str(P["r"]["vehicle"]) for P in plans}]
    if mx:
        warnings.append(f"factor(s) for {mx}: no task of that combine in this file")

    # ---- every record of every written file must carry a valid checksum
    n_rec = n_bad = 0
    for d, _, files in os.walk(out_root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                if fh.read(4) != C.MAGIC:
                    continue
            k, bad, _ = check_file(p)
            n_rec += k
            n_bad += bad
    if n_bad:
        warnings.append(f"{n_bad} of {n_rec:,} records of the written card carry a wrong checksum (copied as found)")
    notes.append(f"checksums: {n_rec:,} records of the written card(s) checked, {n_bad} wrong")
    notes.append({"header_up": "mode header_up: each removed reading's record has its logging bit cleared (header up)",
                  "drop": "mode drop: each removed reading's records are taken out of the three log streams"}[mode])
    notes.append({"points": "totals points: the Summary totals of each task (area, weight, moisture, calibration bins) "
                            "are the kept readings'",
                  "scaled": "totals scaled: the display's own totals reduced in proportion to what is left",
                  "original": "totals original: the display's totals as they were (only the record counts change)"}[totals])
    if mode == "header_up":
        notes.append(".tso[175:179] (a header-up count with no rule found) is left as it was although the header-up "
                     "records grow; .tso[199:207] (newer display software) are scaled by the share left (meaning not "
                     "established)")
    notes.append(CAVEAT)

    zpath = out_root + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, files in os.walk(out_root):
            for f in sorted(files):
                p = os.path.join(d, f)
                z.write(p, os.path.relpath(p, out_root))
    # ---- what the clean file holds (x factor) and what SMS should show for the card
    clean_tot = _point_totals(clean)
    fac = clean["Machine"].astype(str).map(lambda m: factors.get(m, 1.0)).to_numpy(float) \
        if "Machine" in clean.columns and factors else np.ones(len(clean))
    intended = None
    if factors:
        c2 = clean.copy()
        for c in ("Yld_Mass_W", "Yld_Vol_Dr"):
            if c in c2.columns:
                c2[c] = pd.to_numeric(c2[c], errors="coerce") * fac
        intended = _point_totals(c2)
    res = {"path": out_root, "zip": zpath, "cards": [os.path.join(out_root, n) for n in names_by_card.values()],
           "card_names": {os.path.basename(c): n for c, n in names_by_card.items()},
           "n_kept": int(n_kept), "n_removed": int(n_removed), "files_changed": sorted(files_changed),
           "notes": notes, "warnings": warnings, "tasks": tasks_rep, "mode": mode, "totals": totals,
           "widths": bool(widths), "factors": factors, "new_ids": bool(new_ids), "records_checked": int(n_rec),
           "records_bad_checksum": int(n_bad), "registry": reg_path, "clean_totals": clean_tot,
           "intended_totals": intended or clean_tot, "expected_summary": None, "summary_vs_clean": None,
           "sms_tested": False,
           "key": "clean (Dataset, Obj__Id) -> decoded row -> task records aligned on (Time, position, moisture)"}
    if verify and names_by_card:
        try:
            chk = verify_written(res, source, clean_shp, kept={P["ds"]: P["kept_read"] for P in plans},
                                 clean_vals={P["ds"]: P["cv"] for P in plans})
            res["check"] = chk
            res["expected_summary"] = chk.get("summary")
            if not chk["ok"]:
                warnings.append("the decode of the written card does not give the intended readings: " +
                                "; ".join(chk["problems"][:5]))
        except Exception as e:  # noqa: BLE001 - the card is written; the check is reported, not fatal
            warnings.append(f"the check of the written card failed: {e}")
    S, T = res["expected_summary"], res["intended_totals"]

    def _cmp(a, b):
        return {"area": _rel(a.get("area_ac"), b["area_ac"]), "wet": _rel(a.get("wet_lb"), b["wet_lb"]),
                "dry": _rel(a.get("dry_bu"), b["dry_bu"]), "bu_ac": _rel(a.get("bu_ac"), b["bu_ac"])}
    res["points_totals"] = (res.get("check") or {}).get("points_written")
    if res["points_totals"]:
        res["points_vs_clean"] = _cmp(res["points_totals"], T)
    if S:
        cmp = _cmp(S, T)
        res["summary_vs_clean"] = cmp
        if res["points_totals"]:
            res["summary_vs_points"] = _cmp(S, res["points_totals"])
        off = {k: v for k, v in cmp.items() if v is not None and abs(v) > SUMMARY_TOL}
        if off:
            warnings.append("the Summary SMS should show for the written card differs from the clean file's totals ("
                            + ", ".join(f"{k} {100 * v:+.1f} %" for k, v in off.items()) + f"; totals={totals!r}): "
                            + ("the display counted more than its readings and 'scaled' keeps that ratio; "
                               "totals='points' makes the Summary the clean readings'" if totals != "points" else
                               "see the per-task Summary"))
    elif verify:
        warnings.append("no expected Summary: the written card could not be decoded for the check")
    # ---- remember the names given (an earlier write's names are never given again)
    if names_by_card:
        try:
            reg = _read_registry(reg_path)
            stamp = _dt.datetime.now().isoformat(timespec="seconds")
            reg += [{"name": n[:-4], "original": os.path.basename(c), "written": stamp, "clean": os.path.basename(clean_shp),
                     "path": os.path.join(out_root, n)} for c, n in names_by_card.items()]
            os.makedirs(os.path.dirname(reg_path), exist_ok=True)
            with open(reg_path, "w", encoding="utf-8") as f:
                json.dump({"what": "card folder names written by OCED (SMS refuses a card name it has archived)",
                           "cards": reg}, f, indent=1)
        except OSError as e:
            warnings.append(f"the card names could not be recorded in {reg_path} ({e}): a later write may give the "
                            "same names")
    log(f"wrote {len(names_by_card)} card(s): {n_kept:,} readings kept, {n_removed:,} removed -> {zpath}")
    return res


def _write_task(P, out_card, widths, factor, mode, totals, kw, warnings):
    """Write the files of one task (see write_clean) under their own names. Returns (the task's line of the report,
    {extension: written path})."""
    r, ts, cv = P["r"], P["ts"], P["cv"]
    files, card = r["files"], r["card"]
    dst = {ext: os.path.join(out_card, os.path.relpath(_on_disk(p), card)) for ext, p in files.items() if p}
    for p in dst.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
    df = ts.df
    task = r["task"]
    rws, kept, removed = P["rws"], P["kept_read"], P["removed_read"]
    rem_rows, kept_rows = rws[removed], rws[kept]
    info = dict(task=task, dataset=P["ds"], machine=r["vehicle"], kept=int(len(kept)), removed=int(len(removed)),
                written=True)

    # ---- .tlo: level 2 patches, then drop / flag
    b = bytearray(ts.bytes[".tlo"])
    offs, sizes = ts.offs[".tlo"], ts.sizes[".tlo"]
    so = open(files[".tso"], "rb").read()
    _one_record(so, os.path.basename(files[".tso"]))
    olat, olon = struct.unpack_from("<hh", so, 192)
    d_mm = df["dist_mm"].to_numpy(float)
    w_mm = df["width_m"].to_numpy(float) * 1000.0
    dist_new, w_new = d_mm.copy(), w_mm.copy()
    n_w = n_d = n_p = n_ant = n_patched = 0
    dev = {"width_ft": 0.0, "distance_rel": 0.0, "position_deg": 0.0}
    if widths:
        for k, row in enumerate(kept_rows):
            rec = int(offs[ts.io[row]])
            o = rec + C.HDR
            changed = False
            cw, dw = cv["Swth_Wdth_"][k], cv["Swth_dec"][k]
            if np.isfinite(cw) and np.isfinite(dw) and abs(cw - dw) > 1e-6:
                wmm = int(min(65535, max(1, round(cw / FT_PER_M * 1000.0))))
                struct.pack_into("<H", b, o + 4, wmm)
                w_new[row] = wmm
                dev["width_ft"] = max(dev["width_ft"], abs(wmm / 1000.0 * FT_PER_M - cw))
                n_w += 1
                changed = True
            cd, dd = cv["Distance_f"][k], cv["Dist_dec"][k]
            if np.isfinite(cd) and np.isfinite(dd) and dd > 0 and abs(cd / dd - 1) > 1e-9:
                want = d_mm[row] * cd / dd
                dmm = int(min(65535, max(1, round(want))))
                struct.pack_into("<H", b, o + 2, dmm)
                dist_new[row] = dmm
                dev["distance_rel"] = max(dev["distance_rel"], abs(dmm / want - 1) if want > 0 else 0.0)
                n_d += 1
                changed = True
            x, y = cv["_lon"][k], cv["_lat"][k]
            moved = abs(x - cv["lon_dec"][k]) > POS_TOL_DEG or abs(y - cv["lat_dec"][k]) > POS_TOL_DEG
            if moved or w_new[row] != w_mm[row]:
                if not df["ends_bad"].iat[row]:
                    L = np.array([_i32(b, o + 25), _i32(b, o + 29)], np.int64)
                    R = np.array([_i32(b, o + 33), _i32(b, o + 37)], np.int64)
                    S = np.array([round((y - olat) * 2e8), round((x - olon) * 2e8)], np.int64) if moved else L + R
                    h = np.round((R - L) / 2.0 * (w_new[row] / w_mm[row] if w_mm[row] > 0 else 1.0)).astype(np.int64)
                    Ln = S // 2 - h
                    Rn = S - Ln
                    struct.pack_into("<ii", b, o + 25, int(Ln[0]), int(Ln[1]))
                    struct.pack_into("<ii", b, o + 33, int(Rn[0]), int(Rn[1]))
                    if moved:
                        dev["position_deg"] = max(dev["position_deg"], abs(S[0] / 2e8 + olat - y), abs(S[1] / 2e8 + olon - x))
                        # the antenna point keeps its offset from the header centre (it moves with the centre)
                        a_lat, a_lon = _i32(b, o + 6), _i32(b, o + 10)
                        if a_lat != C.NO_FIX and abs(a_lat) <= 2e8 and abs(a_lon) <= 2e8 and (a_lat or a_lon):
                            dS = S - (L + R)
                            struct.pack_into("<ii", b, o + 6, int(a_lat + round(dS[0] / 2.0)),
                                             int(a_lon + round(dS[1] / 2.0)))
                            n_ant += 1
                elif moved:
                    struct.pack_into("<ii", b, o + 6, int(round((y - olat) * 1e8)), int(round((x - olon) * 1e8)))
                n_p += int(moved)
                changed = True
            if changed:
                set_checksum(b, rec, int(sizes[ts.io[row]]))
                n_patched += 1
    info.update(width_changed=n_w, distance_changed=n_d, moved=n_p, antenna_moved=n_ant,
                rounding={k: float(v) for k, v in dev.items()})
    drop_o = ts.io[rem_rows]
    # a display restart is a place where the record counter goes back; the decoder pairs the streams restart by
    # restart, so the first and last record of every restart run stay (logging bit cleared if removed): dropping them
    # could join two runs in one stream and not in the other
    flag_rows = rem_rows if mode == "header_up" else rem_rows[_run_edges(ts.co, ts.io[rem_rows]) |
                                                              _run_edges(ts.ch, ts.ih[rem_rows]) |
                                                              (_run_edges(ts.ct, ts.it[rem_rows]) if ts.ct is not None
                                                               else np.zeros(len(rem_rows), bool))]
    for k in ts.io[flag_rows]:
        o = int(offs[k])
        b[o + C.HDR] &= 0xFE
        set_checksum(b, o, int(sizes[k]))
    if mode == "header_up":
        out_tlo, drop_h, drop_t = bytes(b), np.zeros(0, np.int64), np.zeros(0, np.int64)
    else:
        cut_rows = np.setdiff1d(rem_rows, flag_rows)
        drop_o = ts.io[cut_rows]
        out_tlo = _cut(bytes(b), offs, sizes, drop_o)
        drop_h, drop_t = ts.ih[cut_rows], ts.it[cut_rows]
        if len(flag_rows):
            info["records_flagged_at_restarts"] = int(len(flag_rows))
        if ".tlt" in ts.bytes and (drop_t < 0).any():
            warnings.append(f"{task}: {int((drop_t < 0).sum())} removed readings have no .tlt record")
        drop_t = drop_t[drop_t >= 0]
    with open(dst[".tlo"], "wb") as f:
        f.write(out_tlo)
    for ext, drop in ((".tlh", drop_h), (".tlt", drop_t)):
        if ext in ts.bytes:
            with open(dst[ext], "wb") as f:
                f.write(_cut(ts.bytes[ext], ts.offs[ext], ts.sizes[ext], drop))
    info["records_dropped"] = {".tlo": int(len(drop_o)) if mode == "drop" else 0, ".tlh": int(len(drop_h)),
                               ".tlt": int(len(drop_t))}
    info["records_flagged"] = int(len(flag_rows))
    info["records_patched_tlo"] = int(n_patched) + info["records_flagged"]

    # ---- totals (.tso / .tsh); .tst copied
    lg = df["logging"].to_numpy()
    fl = df["flow_ok"].to_numpy()
    lg_new = lg.copy()
    lg_new[rem_rows] = False
    dt = df["dt_byte"].to_numpy(float)
    spd0 = np.divide(d_mm, dt, out=np.zeros_like(d_mm), where=dt > 0)
    spd1 = np.divide(dist_new, dt, out=np.zeros_like(d_mm), where=dt > 0)
    A0, A1 = float((spd0 * w_mm)[lg].sum()), float((spd1 * w_new)[lg_new].sum())
    D0, D1 = float(spd0[lg].sum()), float(spd1[lg_new].sum())
    N0, N1 = int(lg.sum()), int(lg_new.sum())
    NF0, NF1 = int((lg & fl).sum()), int((lg_new & fl).sum())
    tsh_b = open(files[".tsh"], "rb").read()
    _one_record(tsh_b, os.path.basename(files[".tsh"]))
    sh = _tsh(tsh_b)
    M = df["hB"].to_numpy() / 10.0
    hA = df["hA"].to_numpy(float)
    flow, _ = C.flow_lb_s(hA, M, sh["curve"], sh["comp"])
    a0, a1 = lg & fl, lg_new & fl
    F0, F1 = float(flow[a0].sum()), float(flow[a1].sum())
    fm = flow * (M - sh["offset"])
    FM0, FM1 = float(fm[a0].sum()), float(fm[a1].sum())
    seg = np.clip((hA // C.RAW_STEP).astype(np.int64), 0, C.BINS - 1)
    nb0 = np.bincount(seg[a0], minlength=C.BINS)[:C.BINS].astype(float)
    nb1 = np.bincount(seg[a1], minlength=C.BINS)[:C.BINS].astype(float)
    sb0 = np.bincount(seg[a0], weights=hA[a0], minlength=C.BINS)[:C.BINS]
    sb1 = np.bincount(seg[a1], weights=hA[a1], minlength=C.BINS)[:C.BINS]

    H0 = C.HDR
    tso = bytearray(so)
    changes = {}
    n_rem = int(len(rem_rows))

    def put(buf, fmt, off, val, name):
        old = struct.unpack_from(fmt, buf, H0 + off)[0]
        struct.pack_into(fmt, buf, H0 + off, val)
        if old != val:
            changes[name] = [old, val]

    def get(buf, off):
        return struct.unpack_from("<I", buf, H0 + off)[0]

    if len(tso) >= H0 + 171:
        put(tso, "<I", 163, max(0, get(tso, 163) - n_rem), ".tso[163] logging records")
        if len(flag_rows):
            put(tso, "<I", 167, get(tso, 167) + int(len(flag_rows)), ".tso[167] records logging off")
    if len(tso) >= H0 + 191 and len(flag_rows) and D0 > 0:
        # the distance of the records whose logging bit is cleared moves from the logged to the header-up distance,
        # in the display's own calibration of [183] (cm per sum of speed x 1 s)
        moved_cm = float(spd0[flag_rows].sum()) * get(tso, 183) / D0
        put(tso, "<I", 187, int(get(tso, 187) + round(moved_cm)), ".tso[187] header-up distance cm")
    if totals in ("scaled", "points") and len(tso) >= H0 + 199:
        for off, num, den, nm in ((171, NF1, NF0, ".tso[171] logging records with flow"),
                                  (183, D1, D0, ".tso[183] distance cm")):
            put(tso, "<I", off, _scaled(get(tso, off), num, den), nm)
        if totals == "scaled":
            put(tso, "<I", 195, _scaled(get(tso, 195), A1, A0), ".tso[195] area 0.01 m2")
        else:
            area = float((dist_new[kept_rows] * w_new[kept_rows]).sum()) / 1e4          # mm2 -> 0.01 m2
            put(tso, "<I", 195, int(min(2 ** 32 - 1, round(area))), ".tso[195] area 0.01 m2")
        if len(tso) >= H0 + 207:
            put(tso, "<I", 199, _scaled(get(tso, 199), N1, N0), ".tso[199] (logging time, inferred)")
            put(tso, "<I", 203, _scaled(get(tso, 203), D1, D0), ".tso[203] (logged distance, inferred)")
    set_checksum(tso, 0, len(tso))
    tsh = bytearray(tsh_b)
    cvv = sh["curve"].copy()
    if factor is not None and abs(factor - 1.0) > 1e-12:
        last = C.curve_last_point(cvv)
        new = cvv.copy()
        new[:last + 1] = np.round(C.FLOW_ZERO + factor * (cvv[:last + 1] - C.FLOW_ZERO))
        new = np.clip(new, 0, 65535)
        struct.pack_into("<11H", tsh, H0 + 5, *[int(v) for v in new])
        changes[".tsh curve"] = [[int(v) for v in cvv], [int(v) for v in new]]
        info["factor"] = factor
        if kw.get("calibration") == "latest":
            warnings.append(f"{task}: decoded with calibration='latest' (the crop's current curve): the factor is "
                            "written on the task's own curve, the one the vendor software uses")
        cvv = new
    scale_kg = factor if (factor is not None and abs(factor - 1.0) > 1e-12) else None
    if totals == "points" and sh["full"]:
        secs, cnts, kg_t, kgm = points_bins(hA[kept_rows], M[kept_rows], dt[kept_rows], cvv, sh["comp"], sh["offset"])
        for i in range(C.BINS):
            put(tsh, "<H", 29 + 2 * i, int(secs[i]), f".tsh bin {i} seconds")
            put(tsh, "<I", 49 + 4 * i, int(cnts[i]), f".tsh bin {i} counts")
        put(tsh, "<I", 96, kg_t, ".tsh[96] display kg")
        put(tsh, "<I", 100, kgm, ".tsh[100] kg x moisture")
        scale_kg = None                                     # the factor is in the curve the totals were made with
    elif totals == "scaled" and sh["full"]:
        for i in range(C.BINS):
            s = struct.unpack_from("<H", tsh, H0 + 29 + 2 * i)[0]
            c = get(tsh, 49 + 4 * i)
            put(tsh, "<H", 29 + 2 * i, min(65535, _scaled(s, nb1[i], nb0[i])), f".tsh bin {i} seconds")
            put(tsh, "<I", 49 + 4 * i, _scaled(c, sb1[i], sb0[i]), f".tsh bin {i} counts")
        put(tsh, "<I", 96, _scaled(get(tsh, 96), F1, F0), ".tsh[96] display kg")
        put(tsh, "<I", 100, _scaled(get(tsh, 100), FM1, FM0), ".tsh[100] kg x moisture")
    if scale_kg is not None:
        if len(tsh) >= H0 + 100:
            put(tsh, "<I", 96, int(round(get(tsh, 96) * scale_kg)), ".tsh[96] display kg")
        if sh["full"]:
            put(tsh, "<I", 100, int(round(get(tsh, 100) * scale_kg)), ".tsh[100] kg x moisture")
    set_checksum(tsh, 0, len(tsh))
    if sh["full"] and sh["flags"] & 0x08:
        warnings.append(f"{task}: a calibration load (scale weight {sh['scale_kg'] * LB_PER_KG:,.0f} lb on the card): "
                        "its scale weight is the whole load's, so do not recalibrate from the written card")
    with open(dst[".tso"], "wb") as f:
        f.write(bytes(tso))
    with open(dst[".tsh"], "wb") as f:
        f.write(bytes(tsh))
    if files.get(".tst") and os.path.isfile(files[".tst"]):
        shutil.copyfile(files[".tst"], dst[".tst"])
    info["totals_changed"] = changes
    info["ratios"] = {"area": A1 / A0 if A0 else None, "distance": D1 / D0 if D0 else None,
                      "flow": F1 / F0 if F0 else None, "logging_records": [N0, N1]}
    return info, dst


# ===================================================================================================== check
def verify_written(res: dict, source: dict, clean_shp: str, kept: dict | None = None, clean_vals: dict | None = None) -> dict:
    """Decode the written card(s) and the original tasks with the decoder and options of the source, and compare
    reading by reading (per dataset, in record order): the readings of the written card must be the kept ones (count,
    Time); Time, duration, moisture, elevation, heading and flow-based values as decoded from the original; width,
    distance, speed and position as the clean file (widths=True) or as decoded from the original; the wet yield =
    original wet mass x factor / written area. A task with no kept reading must have no reading on the written card.
    Returns {ok, problems, deviations, summary, points_written, ...}."""
    import pyogrio
    rep, root, unit_ids, opts, kw, _ = _source_parts(source)
    quiet = lambda m: None                                     # noqa: E731
    units_w = [u.id for u in C.list_units(res["path"])]
    dW, repW = C.decode(res["path"], units_w, opts, log=quiet, **kw)
    by_id = {r["id"]: r for r in C.catalogue(root)[0]}
    units_o = [u for u in unit_ids if by_id.get(u, {}).get("has_log")]
    dO, repO = C.decode(root, units_o, opts, log=quiet, **kw)
    clean = pyogrio.read_dataframe(clean_shp)
    problems = []
    factors = res.get("factors") or {}
    n_exp = 0
    exact = {c: 0 for c in ("Time", "Duration_s", "Elevation_", "Track_deg_", "Moisture__", "lonlat", "Swth_Wdth_",
                            "Distance_f", "Yld_Mass_W", "all_level1")}
    dev = {"width_ft": 0.0, "distance_ft": 0.0, "speed_mph": 0.0, "position_m": 0.0, "wet_yield_rel": 0.0,
           "dry_yield_rel": 0.0, "vs_clean_yield_rel": 0.0}
    empty = 0
    for ds, wo in dO.groupby("Dataset", sort=False):
        ww = dW[dW["Dataset"] == ds].sort_values("Obj__Id")
        idx = np.sort(np.asarray(kept[ds], np.int64)) if kept is not None and ds in kept else None
        if idx is None:
            problems.append(f"{ds}: no kept readings given")
            continue
        if not len(idx):
            empty += 1
            if len(ww):
                problems.append(f"{ds}: no reading kept, {len(ww)} readings decoded from the written card")
            continue
        o = wo.sort_values("Obj__Id").iloc[idx]
        n_exp += len(o)
        if len(ww) != len(o):
            problems.append(f"{ds}: {len(ww)} readings decoded from the written card, {len(o)} kept")
            continue
        for c in ("Time", "Duration_s", "Elevation_", "Track_deg_", "Moisture__"):
            a, b = ww[c].to_numpy(), o[c].to_numpy()
            exact[c] += int(((a == b) | (pd.isna(a) & pd.isna(b))).sum()) if c != "Time" else int((a == b).sum())
        f = factors.get(str(o["Machine"].iloc[0]), 1.0)
        # intended width / distance / position: the clean values (widths=True) at the card's resolution, else original
        order = np.argsort(np.asarray(kept[ds]))
        cv = {k: np.asarray(v)[order] for k, v in (clean_vals or {}).get(ds, {}).items()}
        if res.get("widths") and cv:
            w_int = np.where(np.abs(cv["Swth_Wdth_"] - cv["Swth_dec"]) > 1e-6, cv["Swth_Wdth_"], o["Swth_Wdth_"].to_numpy())
            dd = np.where(cv["Dist_dec"] > 0, cv["Dist_dec"], 1)
            d_int = np.where((cv["Dist_dec"] > 0) & (np.abs(cv["Distance_f"] / dd - 1) > 1e-9),
                             o["Distance_f"].to_numpy() * cv["Distance_f"] / dd, o["Distance_f"].to_numpy())
            moved = (np.abs(cv["_lon"] - cv["lon_dec"]) > POS_TOL_DEG) | (np.abs(cv["_lat"] - cv["lat_dec"]) > POS_TOL_DEG)
            x_int = np.where(moved, cv["_lon"], o["lon"].to_numpy())
            y_int = np.where(moved, cv["_lat"], o["lat"].to_numpy())
        else:
            w_int, d_int = o["Swth_Wdth_"].to_numpy(), o["Distance_f"].to_numpy()
            x_int, y_int = o["lon"].to_numpy(), o["lat"].to_numpy()
        lat0 = np.radians(float(np.mean(y_int)))
        pm = np.hypot((ww["lon"].to_numpy() - x_int) * np.cos(lat0) * 111320.0, (ww["lat"].to_numpy() - y_int) * 111320.0)
        exact["lonlat"] += int(((ww["lon"].to_numpy() == x_int) & (ww["lat"].to_numpy() == y_int)).sum())
        exact["Swth_Wdth_"] += int((ww["Swth_Wdth_"].to_numpy() == w_int).sum())
        exact["Distance_f"] += int((ww["Distance_f"].to_numpy() == d_int).sum())
        dev["width_ft"] = max(dev["width_ft"], float(np.abs(ww["Swth_Wdth_"].to_numpy() - w_int).max()))
        dev["distance_ft"] = max(dev["distance_ft"], float(np.abs(ww["Distance_f"].to_numpy() - d_int).max()))
        sp_int = d_int / ww["Duration_s"].to_numpy() / 1.4666666666666666
        dev["speed_mph"] = max(dev["speed_mph"], float(np.abs(ww["Speed_mph_"].to_numpy() - sp_int).max()))
        dev["position_m"] = max(dev["position_m"], float(pm.max()))
        wet_o = o["Yld_Mass_W"].to_numpy() * o["Distance_f"].to_numpy() * o["Swth_Wdth_"].to_numpy()
        y_int = wet_o * f / (d_int * w_int)
        ok = y_int > 0
        rel = np.abs(ww["Yld_Mass_W"].to_numpy()[ok] / y_int[ok] - 1)
        dev["wet_yield_rel"] = max(dev["wet_yield_rel"], float(rel.max(initial=0)))
        exact["Yld_Mass_W"] += int((ww["Yld_Mass_W"].to_numpy() == o["Yld_Mass_W"].to_numpy()).sum())
        dry_int = o["Yld_Vol_Dr"].to_numpy() * o["Distance_f"].to_numpy() * o["Swth_Wdth_"].to_numpy() * f / (d_int * w_int)
        okd = dry_int > 0
        dev["dry_yield_rel"] = max(dev["dry_yield_rel"],
                                   float(np.abs(ww["Yld_Vol_Dr"].to_numpy()[okd] / dry_int[okd] - 1).max(initial=0)))
        lvl1 = np.ones(len(o), bool)
        for c in ("Time", "Duration_s", "Elevation_", "Speed_mph_", "Distance_f", "Track_deg_", "Swth_Wdth_",
                  "Moisture__", "Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr", "lon", "lat", "Machine",
                  "Field", "Product"):
            a, b = ww[c].to_numpy(), o[c].to_numpy()
            lvl1 &= (a == b) | (pd.isna(a) & pd.isna(b)) if a.dtype.kind == "f" else (a == b)
        exact["all_level1"] += int(lvl1.sum())
        c = clean[clean["Dataset"].astype(str) == ds].sort_values("Obj__Id")
        if len(c) == len(ww) and "Yld_Mass_W" in c.columns:
            yc = c["Yld_Mass_W"].to_numpy(float) * f
            okc = yc > 0
            dev["vs_clean_yield_rel"] = max(dev["vs_clean_yield_rel"],
                                            float(np.abs(ww["Yld_Mass_W"].to_numpy()[okc] / yc[okc] - 1).max(initial=0)))
    extra = sorted(set(dW["Dataset"].astype(str)) - set(dO["Dataset"].astype(str)))
    if extra:
        problems.append(f"datasets on the written card that the original does not have: {extra[:3]}")
    out = {"readings_written": int(len(dW)), "readings_kept": int(n_exp), "readings_clean": int(len(clean)),
           "datasets_without_kept_reading": int(empty), "exact": exact, "deviations": dev}
    if len(dW) != n_exp or n_exp != len(clean):
        problems.append(f"{len(dW):,} readings decoded from the written card, {n_exp:,} kept, {len(clean):,} clean rows")
    for c in ("Time", "Duration_s", "Moisture__", "Track_deg_"):
        if exact[c] != n_exp:
            problems.append(f"{n_exp - exact[c]} readings with another {c}")
    if dev["width_ft"] > 0.002 or dev["distance_ft"] > 0.002 or dev["position_m"] > 0.002:
        problems.append(f"width / distance / position off by up to {dev['width_ft']:.4f} ft / {dev['distance_ft']:.4f} ft "
                        f"/ {dev['position_m']:.4f} m")
    if dev["wet_yield_rel"] > 0.005:
        problems.append(f"wet yield off by up to {100 * dev['wet_yield_rel']:.2f} %")
    S = repW.get("sms_summary") or {}
    out["summary"] = S.get("total")
    out["summary_datasets"] = S.get("datasets")
    out["summary_original"] = (repO.get("sms_summary") or {}).get("total")
    out["points_written"] = _point_totals(dW)
    out["problems"] = problems
    out["ok"] = not problems
    return out
