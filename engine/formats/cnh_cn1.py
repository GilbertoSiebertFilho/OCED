# -*- coding: utf-8 -*-
"""Decoder for the Case IH / New Holland AFS Pro 700 data card (a ``<name>.cn1`` folder with ``index.vy1``).

The card is decoded byte by byte, without any vendor software, into the standard table of engine/formats/common.py
(one row = one yield reading at the HEADER CENTRE). Every number below was established on the card of Trial 19
Trial 19 (field A, barley 2026, one Case IH Axial-Flow, display serial withheld) by matching the decoded records one by
one to the Ag Leader SMS export of the SAME card (33,017 points); the evidence and the validation table are in
docs/formats/cnh_cn1.md and are reproduced by tools/validate_cnh_cn1.py and tests/test_cnh_cn1.py.

Card layout
    <card>.cn1/index.vy1                     CNH1 record naming the display; marks the folder as a card
    <card>.cn1/COMBINES/<veh>/<veh>.ycs      crop table, 147 records x 244 B (record index = crop number)
    <card>.cn1/COMBINES/<veh>/<veh>.ycc      current yield calibration of each crop, 147 records x 65 B
    <card>.cn1/shared/growers.gws            grower names;  shared/<farm>.fms  farm name (parent = grower)
    <card>.cn1/shared/<farm>.fmd/<field>.fls field name (parent = farm)
    <card>.cn1/shared/<farm>.fmd/<field>.fld/<task>.{tso,tsh,tst,tlo,tlh,tlt}   one task (= one SMS dataset)

Records: b"CNH1" + uint32 payload length + 2 B + 1 B type + 8 B id + 8 B parent id + 6 B time (year-1970, month,
day, hour, minute, second; display clock) = 33 B header, then the payload. In the log streams (.tlo/.tlh/.tlt) the id
starts with a uint32 record counter that joins the streams. All integers little-endian.

    .tso payload  [0:19] task name 'YY/MM/DD-HH:MM:SS' (an optional leading '#'/'%'), [19:25] start time,
                  [33:48] operation ('Grain Harv'), [52] crop number, [53:70] vehicle serial, [159:163] int16 lat and
                  int16 lon ORIGIN (integer degrees, differs between tasks), [163:167] number of logging records.
    .tsh payload  [4] flags (bit 3 set on the tasks used as calibration loads), [5:27] the task's calibration curve
                  (11 x uint16), [27:29] moisture-compensation coefficient (x1e-4 per moisture point), [96:100] the
                  display's own task total (kg) computed with the calibration active while harvesting.
    .tlo (41 B)   [0] logging flags: bit 0 = area counting on (the records with bit 0 set are the .tso's count of
                  logging records); a newer display software also sets bit 2 (Trial 25 card, 2026: values 0, 1, 4, 5,
                  60 % of the harvest at 5), [1] interval x0.1 s (see "time basis"), [2:4] distance of
                  the record in mm (= speed x [1]), [4:6] active cut width mm, [6:10]/[10:14] lat/lon int32 x1e-8 deg
                  ADDED to the task origin, [14:18] altitude mm, [18] GNSS status (0 = no fix; the position is then
                  0x80000001 or 0), [19:23] GNSS time of day ms (UTC), [23:25] heading x0.1 deg,
                  [25:33] and [33:41] lat/lon of the two header ENDS (same encoding).
    .tlh (17 B)   [1:3] raw mass-flow count hA, [5] grain moisture x0.1 % (hB), [11] 255 = flow sample invalid.
    .ycs payload  [2:4] test weight lb/bu x10, [4] standard moisture x10 (the one SMS uses), [6] a second moisture.
    .ycc payload  [0:22] current calibration curve (11 x uint16), [46] moisture-compensation coefficient.

Mass flow (wet); reproduces SMS's Crop_Flw_M within 0.5 % on 99.98 % of the 33,017 points (median absolute
difference 0.00003 lb/s = the rounding of the export):
    M = hB / 10                                    grain moisture, %
    u = hA / 1000 * (1 + c * (14.0 - M))           c = .tsh[27:29] / 10000 (0.0075 on this card)
    x = curve interpolated at u = 0, 1, ..., 10    (the task's .tsh curve; linear extrapolation above 10)
    flow (lb/s) = (x - 1000) / 100                 negative values (u < ~0.2, empty machine) are set to 0
Only two combinations of (raw step, coefficient, reference moisture) are identifiable; with the raw step at 1000
counts the fitted coefficient equals the one stored in the task (75 -> 0.0075) and the reference moisture is 14.0 %.
Fitted on crop 17 (barley), the formula reproduces every task of the card, including the two whose level looked
"unexplained" with the earlier approximation (1.714 g/s x the curve read on the .ycc's second array: I1 x1.038 = no
moisture term, it was harvested at 8.7 % moisture; I5 x0.878 = wrong raw axis for its older curve). The second
11-point array of the .ycc is NOT used. Across crops it is checked against the display's own task totals (.tsh @96):
decoded / display = 1.002-1.003 on the 2024 canola tasks (5.5 % moisture) and 0.996-1.000 on the 2025 wheat tasks.

Which curve: each task carries the curve stored in its .tsh (what the display and SMS use; option
``calibration="task"``, the default). When the operator recalibrates, only the tasks used as calibration loads are
rewritten with the new curve; older tasks keep theirs. ``calibration="latest"`` applies the crop's current .ycc curve
to every task instead. Every task whose curve differs from the current one, or whose decoded mass differs from the
display's own total (.tsh @96) by more than 2 %, gets a warning with the factor.

Time basis: the display writes ONE record per second of its clock (card-wide, over 2.35 million consecutive logging
records, the display-clock steps sum to 0.9995 s per record and the GNSS clock to 1.0008 s). Byte [1] is not the time a
record covers: it sums to 1.024 s per record card-wide (+2 to +19 % per task) and the distance [2:4] is speed x [1].
A record therefore represents the logging period P (the median display-clock step, 1 s), and
    speed = [2:4] / [1],   Distance_f = speed x P,   wet mass = flow x P.
The per-point yield (flow / speed / width) is identical to SMS's; SMS's Duration_s and Distance_f use byte [1], so its
mass and area are inflated together on the records with [1] > 1 s (the totals differ, the yields do not). The
display's own task totals (.tsh @96) confirm one second per record (decoded / display = 1.003 and 1.002 on the two 2026
tasks harvested with an unchanged calibration; with byte [1] it would be 1.013 and 1.138).

Kept readings (pre-step, counted by reason): logging bit on, valid GNSS fix, valid flow sample, distance > 0,
interval byte > 0, cut width > 0. Nothing is dropped by yield value (SMS also drops yields outside 5-200 bu/ac; the
cleaning does that here). Position = midpoint of the two header ends (SMS uses the same point, < 1.3 mm).
Dry yield: one-sided shrink at the crop's standard moisture (.ycs [4]) - SMS's rule on 100 % of the points - is this
format's default (DEFAULT_OPTIONS / DEFAULT_SHRINK).
"""
from __future__ import annotations

import collections
import glob
import os
import re
import struct
import time as _time

import numpy as np
import pandas as pd

from engine.formats.common import (DecodeOptions, Probe, Unit, FT_PER_M, MPH_PER_MS, SQFT_PER_AC, LB_PER_KG,
                                   dataset_name, summarize, yield_columns, check_standard)

FORMAT_ID = "cnh_cn1"
LABEL = "Case IH / New Holland AFS Pro 700 card (.cn1)"
DEFAULT_SHRINK = "one_sided"                       # SMS's rule for this format (100 % of the reference points)
DEFAULT_OPTIONS = DecodeOptions(shrink=DEFAULT_SHRINK)

MAGIC = b"CNH1"
HDR = 33
TLO_LEN, TLH_LEN, YCS_LEN, YCC_LEN = 41, 17, 244, 65
NO_FIX = -2147483647                               # 0x80000001: position offset written when there is no fix
# flow calibration constants (fitted on crop 17, see the module docstring)
RAW_STEP = 1000.0                                  # raw counts per curve index
FLOW_ZERO = 1000.0                                 # curve value of zero flow
FLOW_SCALE_LB_S = 0.01                             # lb/s per curve unit
MOIST_REF = 14.0                                   # reference moisture of the compensation, %
DISPLAY_TOL = 0.02                                 # warn when decoded mass / display total differs by more
CURVE_TOL = 0.01                                   # warn when the latest calibration changes a task's mass by more
# crop numbers whose name is confirmed by the vendor software reading this format (SMS "Product")
CROP_NAMES = {17: "Barley - Fall"}
# best guess from (test weight, standard moisture) when the number is not confirmed; shown with a "?"
CROP_GUESS = {(48.0, 14.5): "barley", (50.0, 8.5): "canola", (60.0, 13.5): "wheat", (32.0, 14.0): "oats"}


# ===================================================================================================== record level
def _time_tuple(h):
    y, mo, d, hh, mi, ss = h[27:33]
    try:
        return pd.Timestamp(year=1970 + y, month=mo, day=d, hour=hh, minute=mi, second=ss)
    except ValueError:
        return pd.NaT


def read_records(path):
    """Every CNH1 record of a file: list of dicts {type, id, parent, time, payload}. Bytes between records are skipped."""
    b = open(path, "rb").read()
    out, i = [], 0
    while i <= len(b) - HDR:
        if b[i:i + 4] != MAGIC:
            j = b.find(MAGIC, i + 1)
            if j < 0:
                break
            i = j
            continue
        n = struct.unpack_from("<I", b, i + 4)[0]
        h = b[i:i + HDR]
        out.append(dict(type=h[10], id=h[11:19], parent=h[19:27], time=_time_tuple(h), payload=b[i + HDR:i + HDR + n]))
        i += HDR + n
    return out


def read_stream(path, length):
    """Fixed-length log stream -> (counter int64[n], time int64[n, 6] (y-1970, mo, d, h, mi, s), payload uint8[n, L],
    n_irregular, record_length). `length` is the known layout (the first L payload bytes); a newer display software
    appends bytes to the record (card CARD20, 2026: .tlo of 50 bytes, record type 3, instead of 41, type 2 -- the
    first 41 bytes unchanged, then a 0/1 flag and 8 x 0xFF), so a record of `length` or more bytes is read and only
    the first `length` bytes are used. Records shorter than `length` are skipped and counted. record_length is the
    payload length found on the card (the most common one). Fast path when every record sits on a regular stride."""
    b = np.fromfile(path, np.uint8)
    if len(b) >= HDR + 4:
        n0 = int(struct.unpack_from("<I", b, 4)[0])
        st = HDR + n0
        if n0 >= length and len(b) % st == 0:
            R = b.reshape(-1, st)
            magic_ok = (R[:, :4] == np.frombuffer(MAGIC, np.uint8)).all()
            if magic_ok and (R[:, 4:8].copy().view("<u4").ravel() == n0).all():
                return (R[:, 11:15].copy().view("<u4").ravel().astype(np.int64), R[:, 27:33].astype(np.int64),
                        R[:, HDR:HDR + length], 0, n0)
    recs = read_records(path)
    keep = [r for r in recs if len(r["payload"]) >= length]
    if not keep:
        return np.zeros(0, np.int64), np.zeros((0, 6), np.int64), np.zeros((0, length), np.uint8), len(recs), None
    lengths = collections.Counter(len(r["payload"]) for r in keep)
    ctr = np.array([struct.unpack_from("<I", r["id"], 0)[0] for r in keep], np.int64)
    tm = np.array([[0, 0, 0, 0, 0, 0] if pd.isna(r["time"]) else
                   [r["time"].year - 1970, r["time"].month, r["time"].day, r["time"].hour, r["time"].minute,
                    r["time"].second] for r in keep], np.int64)
    P = np.frombuffer(b"".join(r["payload"][:length] for r in keep), np.uint8).reshape(-1, length)
    return ctr, tm, P, len(recs) - len(keep), lengths.most_common(1)[0][0]


def _u16(A, o):
    return A[:, o].astype(np.int64) | (A[:, o + 1].astype(np.int64) << 8)


def _i32(A, o):
    return A[:, o:o + 4].copy().view("<i4").ravel().astype(np.int64)


def _cstr(b):
    return b.split(b"\0")[0].decode("latin-1").strip()


# ===================================================================================================== card catalogue
def _is_card(d):
    p = os.path.join(d, "index.vy1")
    if os.path.isfile(p):
        with open(p, "rb") as f:
            return f.read(4) == MAGIC
    return False


def _has_cnh_tasks(d):
    """A folder holding <field>.fld sub-folders with CNH1 .tso files (a card copied without its .cn1 parent)."""
    for fld in glob.glob(os.path.join(glob.escape(d), "*.fld")):
        for tso in glob.glob(os.path.join(glob.escape(fld), "*.tso"))[:1]:
            with open(tso, "rb") as f:
                return f.read(4) == MAGIC
    return False


def find_cards(root):
    """Card folders under root: [(folder, complete)]; complete = has index.vy1. Partial copies (loose .fld folders,
    no index) are returned only when no complete card holds them."""
    full, partial = [], []
    for d, dirs, files in os.walk(root):
        dirs.sort()
        if "index.vy1" in files and _is_card(d):
            full.append(d)
            dirs[:] = []                                  # the card's sub-folders belong to it
            continue
        if any(x.lower().endswith(".fld") for x in dirs) and _has_cnh_tasks(d):
            partial.append(d)
            dirs[:] = [x for x in dirs if not x.lower().endswith(".fld")]
    # a partial copy whose fields are all on a complete card next to it is the same data twice: keep the card
    on_cards = {os.path.basename(f).lower() for c in full
                for f in glob.glob(os.path.join(glob.escape(c), "**", "*.fld"), recursive=True)}
    partial = [d for d in partial if not {x.lower() for x in os.listdir(d) if x.lower().endswith(".fld")} <= on_cards]
    return [(d, True) for d in full] + [(d, False) for d in partial]


def _names(card):
    """{id: name} of growers, farms and fields found anywhere in the card, and {farm id: grower id}."""
    names, parent = {}, {}
    for p in glob.glob(os.path.join(glob.escape(card), "**", "*.gws"), recursive=True) + \
            glob.glob(os.path.join(glob.escape(card), "**", "*.fms"), recursive=True) + \
            glob.glob(os.path.join(glob.escape(card), "**", "*.fls"), recursive=True):
        try:
            for r in read_records(p):
                rid = _cstr(r["id"])
                if rid:
                    names[rid] = _cstr(r["payload"])
                    parent[rid] = _cstr(r["parent"])
        except OSError:
            continue
    return names, parent


def _crop_tables(card):
    """{vehicle folder name: {"ycs": {crop: payload}, "ycc": {crop: (time, payload)}}} for every .ycs/.ycc found."""
    out = {}
    for ext, L in (("ycs", YCS_LEN), ("ycc", YCC_LEN)):
        for p in glob.glob(os.path.join(glob.escape(card), "**", "*." + ext), recursive=True):
            veh = os.path.splitext(os.path.basename(p))[0]
            d = out.setdefault(veh, {"ycs": {}, "ycc": {}})
            for r in read_records(p):
                if len(r["payload"]) != L:
                    continue
                k = struct.unpack_from("<I", r["id"], 0)[0]
                d[ext][k] = r["payload"] if ext == "ycs" else (r["time"], r["payload"])
    return out


def _vehicle_tables(tables, vehicle):
    """The crop tables of the combine that logged a task: the COMBINES folder whose name starts the vehicle serial
    ('ABCDE' for 'ABCDE0000000'). Returns (folder name or None, tables or None, note)."""
    hits = [v for v in tables if vehicle.upper().startswith(v.upper())]
    if hits:
        v = max(hits, key=len)
        return v, tables[v], ""
    if len(tables) == 1:
        v = next(iter(tables))
        return v, tables[v], f"no crop table named after vehicle {vehicle!r}; used the only one on the card ({v})"
    return None, None, f"no crop table for vehicle {vehicle!r}"


def _crop_info(tbl, k):
    """(test weight lb/bu, standard moisture %, second moisture %, product name, crop key) of crop number k."""
    if tbl is None or k not in tbl["ycs"]:
        return None, None, None, f"crop {k}", None
    p = tbl["ycs"][k]
    tw, m4, m6 = struct.unpack_from("<H", p, 2)[0] / 10.0, p[4] / 10.0, p[6] / 10.0
    if k in CROP_NAMES:
        name = CROP_NAMES[k]
        key = name.split(" ")[0].lower()
    else:
        key = CROP_GUESS.get((tw, m4))
        name = f"crop {k}" + (f" ({key}?)" if key else "")
    return tw, m4, m6, name, key


def _task_meta(tso_path):
    so = open(tso_path, "rb").read()
    p = so[HDR:]
    name = _cstr(p[:19])
    start = pd.Timestamp(year=1970 + p[19], month=p[20], day=p[21], hour=p[22], minute=p[23], second=p[24]) \
        if 1 <= p[20] <= 12 and 1 <= p[21] <= 31 else pd.NaT
    if pd.isna(start):
        m = re.search(r"(\d\d)/(\d\d)/(\d\d)-(\d\d):(\d\d):(\d\d)", name)
        if m:
            y, mo, d, hh, mi, ss = map(int, m.groups())
            start = pd.Timestamp(2000 + y, mo, d, hh, mi, ss)
    season = re.search(rb"[0-9A-Z]{8}((?:19|20)\d\d)\x00", p)
    olat, olon = struct.unpack_from("<hh", so, 192) if len(so) >= 196 else (0, 0)
    n_log = struct.unpack_from("<I", so, 196)[0] if len(so) >= 200 else 0
    return dict(name=name, start=start, end=_time_tuple(so[:HDR]), op=_cstr(p[33:48]), crop=p[52] if len(p) > 52 else -1,
                vehicle=_cstr(p[53:70]), season=int(season.group(1)) if season else (start.year if not pd.isna(start) else None),
                origin=(olat, olon), n_log=n_log)


def _task_sh(tsh_path):
    b = open(tsh_path, "rb").read()
    p = b[HDR:]
    return dict(flags=p[4], curve=np.array(struct.unpack_from("<11H", p, 5), float), written=_time_tuple(b[:HDR]),
                comp=struct.unpack_from("<H", p, 27)[0], display_kg=struct.unpack_from("<I", p, 96)[0] if len(p) >= 100 else None)


def catalogue(root):
    """Every harvest task with logged records under root: list of dicts (one per unit) + the cards found."""
    cards = find_cards(root)
    rows = []
    for card, complete in cards:
        names, parent = _names(card)
        tables = _crop_tables(card)
        rel = os.path.relpath(card, root).replace("\\", "/")
        for tso in sorted(glob.glob(os.path.join(glob.escape(card), "**", "*.fld", "*.tso"), recursive=True)):
            base = tso[:-4]
            if not (os.path.isfile(base + ".tlo") and os.path.getsize(base + ".tlo") > 0 and os.path.isfile(base + ".tlh")):
                continue
            try:
                meta = _task_meta(tso)
            except (OSError, struct.error, ValueError):
                continue
            if meta["n_log"] == 0:
                continue
            fld = os.path.basename(os.path.dirname(base))
            fid = os.path.splitext(fld)[0]
            farm = parent.get(fid, "")
            veh_dir, tbl, note = _vehicle_tables(tables, meta["vehicle"])
            tw, m4, m6, prod, key = _crop_info(tbl, meta["crop"])
            task = os.path.basename(base)
            rows.append(dict(
                id=f"{rel}::{os.path.relpath(base, card).replace(os.sep, '/')}", card=card, card_complete=complete,
                base=base, task=task, field_id=fid, field=names.get(fid, fid), farm_id=farm, farm=names.get(farm, farm),
                grower=names.get(parent.get(farm, ""), parent.get(farm, "")), vehicle=meta["vehicle"], veh_dir=veh_dir,
                tables=tbl, table_note=note, crop=meta["crop"], tw=tw, std_m=m4, m6=m6, product=prod, crop_key=key,
                season=meta["season"], start=meta["start"], end=meta["end"], n_log=meta["n_log"], op=meta["op"],
                task_name=meta["name"], origin=meta["origin"],
                # the season of a unit is its HARVEST year (task start on the display clock); the card's season tag is
                # set per field by the operator and is not always moved on (card CARD20: field T20 tagged 2025,
                # harvested September 2026; reference card: field B 2022 harvested 2023, field C 2023 harvested 2024)
                year=meta["start"].year if not pd.isna(meta["start"]) else meta["season"]))
    return _one_per_task(rows), cards


def _one_per_task(rows):
    """One row per task over every card copy under the root. A grower's upload can hold the same card twice
    (WeTransfer of 2026-10-16: CARD20.cn1 and CARD20_2.cn1/CARD20.cn1, byte-identical): every task would be
    listed and decoded twice, doubling the readings and leaving each point on top of its copy (the cleaning then
    removes everything). A task is the display's task id + vehicle; the copy with the most logging records is kept
    (a later copy of a card can hold a task that grew after the first copy), a complete card before a partial one,
    then the first in folder order. Kept rows carry copies = how many card copies hold that task."""
    out, index = [], {}
    for r in rows:
        k = (r["vehicle"], r["task"])
        if k not in index:
            index[k] = len(out)
            out.append(dict(r, copies=1))
            continue
        cur = out[index[k]]
        if (r["n_log"], r["card_complete"]) > (cur["n_log"], cur["card_complete"]):
            out[index[k]] = dict(r, copies=cur["copies"] + 1)
        else:
            cur["copies"] += 1
    return out


def probe(root):
    """Cheap recognition (folder walk + a few file headers, no log decoding). A task id found on more than one copy of
    the card is counted once and reported (see _one_per_task)."""
    cards = find_cards(root)
    if not cards:
        return None
    n_files, vehicles, fields, warns = 0, set(), set(), []
    tasks, repeated = set(), set()
    for card, complete in cards:
        for d, _, files in os.walk(card):
            n_files += len(files)
        for tso in glob.glob(os.path.join(glob.escape(card), "**", "*.fld", "*.tso"), recursive=True):
            if os.path.isfile(tso[:-4] + ".tlo") and os.path.getsize(tso[:-4] + ".tlo") > 0:
                task = os.path.basename(tso)[:-4]
                (repeated if task in tasks else tasks).add(task)
                fields.add(os.path.basename(os.path.dirname(tso)))
                try:
                    with open(tso, "rb") as f:
                        vehicles.add(_cstr(f.read(HDR + 70)[HDR + 53:HDR + 70]))
                except OSError:
                    pass
        if not complete:
            warns.append(f"{os.path.basename(card) or card}: partial card copy (no index.vy1 / .cn1 parent); names or "
                         "the crop table may be missing")
    if repeated:
        warns.append(f"{len(repeated)} task log(s) are on more than one copy of the card in this upload (same task id): "
                     "each task is listed and decoded once, from the copy with the most records")
    rec_root = cards[0][0] if len(cards) == 1 else root
    count = {}
    for c, _ in cards:
        count[os.path.basename(c)] = count.get(os.path.basename(c), 0) + 1
    names = ", ".join(n if k == 1 else f"{n} ({k} copies)" for n, k in sorted(count.items()))
    return Probe(format_id=FORMAT_ID, label=LABEL, root=rec_root,
                 summary=f"AFS Pro 700 card {names}: {len(tasks)} task logs on {len(fields)} fields, "
                         f"combine(s) {', '.join(sorted(v for v in vehicles if v)) or '?'}",
                 n_files=n_files, machines=sorted(v for v in vehicles if v), warnings=warns)


def _unit_label(r):
    s, e = r["start"], r["end"]
    span = f"{s:%d %b %H:%M}-{e:%d %b %H:%M}" if not (pd.isna(s) or pd.isna(e)) else "?"
    season = str(r["year"])
    if r["season"] is not None and r["year"] is not None and int(r["season"]) != int(r["year"]):
        season = f"{r['year']} (season tag {r['season']} on the card)"
    return (f"{r['field']} · {season} · {r['product']} · task {r['task']} ({span}) · "
            f"{r['n_log']:,} harvest records")


def list_units(root):
    rows, _ = catalogue(root)
    if not rows:
        return []
    latest = max((r["year"] or 0) for r in rows)
    out = []
    for r in sorted(rows, key=lambda r: (r["field"], r["start"] if not pd.isna(r["start"]) else pd.Timestamp(0))):
        out.append(Unit(id=r["id"], label=_unit_label(r), field=r["field"], crop=r["crop_key"] or r["product"],
                        year=r["year"], start=str(r["start"]), end=str(r["end"]), machine=r["vehicle"],
                        n_records=int(r["n_log"]), default=(r["year"] == latest)))
    return out


# ===================================================================================================== decoding
def curve_last_point(curve):
    """Index of the curve's last defined point: the points after it that sit at the zero value (FLOW_ZERO) are unset.
    A full 11-point curve (reference card) -> 10. A newer display software writes a single-point calibration as
    [1000, 2554, 1000, 1000, ...] (card CARD20, 2026: every task of field T20) -> 1."""
    c = np.asarray(curve, float)
    defined = np.nonzero(c != FLOW_ZERO)[0]
    return int(defined[-1]) if len(defined) else 0


def flow_lb_s(hA, moisture_pct, curve, comp):
    """Wet mass flow (lb/s) from the raw count, the moisture and an 11-point curve (see the module docstring).
    The curve is extended linearly from its last defined segment (curve_last_point): above point 10 for a full curve,
    as before, and above point 1 for a single-point calibration, whose unset points would otherwise fold the flow back
    to zero above u = 1 (field T20 2026: decoded mass 0.3-12.6 % under the display's totals, within 2.3 % once
    extended). Returns (flow, n_negative): values below the curve's zero (u < ~0.2) are set to 0 and counted."""
    hA = np.asarray(hA, float)
    u = hA / RAW_STEP * (1.0 + comp / 1e4 * (MOIST_REF - np.asarray(moisture_pct, float)))
    last = curve_last_point(curve)
    if last < 1:                                         # no defined point: no flow can be computed
        return np.zeros_like(u), 0
    i = np.clip(np.floor(u).astype(np.int64), 0, last - 1)
    x = curve[i] + (u - i) * (curve[i + 1] - curve[i])
    f = (x - FLOW_ZERO) * FLOW_SCALE_LB_S
    neg = f < 0
    return np.where(neg, 0.0, f), int(neg.sum())


def read_task(base):
    """Join the .tlo and .tlh streams of one task on the record counter -> (DataFrame of raw channels, notes)."""
    co, to, O, irr_o, len_o = read_stream(base + ".tlo", TLO_LEN)
    ch, _, H, irr_h, len_h = read_stream(base + ".tlh", TLH_LEN)
    notes = {"record bytes": {".tlo": len_o, ".tlh": len_h}}          # the layout read is TLO_LEN / TLH_LEN
    co_u, io = np.unique(co, return_index=True)
    ch_u, ih = np.unique(ch, return_index=True)
    common, a, b = np.intersect1d(co_u, ch_u, return_indices=True)
    io, ih = io[a], ih[b]
    notes["records in .tlo"] = len(co)
    notes["no .tlh record (counter join)"] = len(co) - len(io)
    notes["records of another length"] = irr_o + irr_h
    O, H, T = O[io], H[ih], to[io]
    notes["logging byte values"] = sorted(int(v) for v in np.unique(O[:, 0]))
    so = open(base + ".tso", "rb").read()
    olat, olon = struct.unpack_from("<hh", so, 192)
    lat_o, lon_o = _i32(O, 6), _i32(O, 10)
    latL, lonL, latR, lonR = _i32(O, 25), _i32(O, 29), _i32(O, 33), _i32(O, 37)
    disp = pd.to_datetime(dict(year=1970 + T[:, 0], month=T[:, 1], day=T[:, 2], hour=T[:, 3], minute=T[:, 4],
                               second=T[:, 5]), errors="coerce")
    df = pd.DataFrame({
        "ctr": common, "disp_time": disp, "logging": (O[:, 0] & 1) == 1, "dt_byte": O[:, 1] / 10.0,
        "dist_mm": _u16(O, 2).astype(float), "width_m": _u16(O, 4) / 1000.0,
        "lat0": olat + lat_o * 1e-8, "lon0": olon + lon_o * 1e-8,
        "latL": olat + latL * 1e-8, "lonL": olon + lonL * 1e-8, "latR": olat + latR * 1e-8, "lonR": olon + lonR * 1e-8,
        "alt_m": np.where(_i32(O, 14) == NO_FIX, np.nan, _i32(O, 14) / 1000.0),
        "gnss": O[:, 18].astype(int), "gnss_ms": _i32(O, 19), "heading": _u16(O, 23) / 10.0,
        "hA": _u16(H, 1).astype(float), "hB": H[:, 5].astype(int), "flow_ok": H[:, 11] != 255,
        "pos_bad": (O[:, 18] == 0) | (np.abs(lat_o) > 2e8) | (np.abs(lon_o) > 2e8) | ((lat_o == 0) & (lon_o == 0)),
        "ends_bad": (np.abs(latL) > 2e8) | (np.abs(lonL) > 2e8) | (np.abs(latR) > 2e8) | (np.abs(lonR) > 2e8)
                    | ((latL == 0) & (lonL == 0)) | ((latR == 0) & (lonR == 0)),
    })
    return df, notes


def select_readings(df):
    """Readings the vendor software exports (pre-step): returns (mask, {reason: n dropped}) in a fixed order."""
    keep = np.ones(len(df), bool)
    counts = {}
    for reason, bad in (("logging off (header up / area counting off)", ~df.logging.values),
                        ("no GNSS fix (status 0 / no position)", df.pos_bad.values),
                        ("flow sample invalid (.tlh[11] = 255)", ~df.flow_ok.values),
                        ("not moving (distance 0)", df.dist_mm.values <= 0),
                        ("interval byte 0 (speed undefined)", df.dt_byte.values <= 0),
                        ("cut width 0", df.width_m.values <= 0)):
        hit = keep & bad
        if hit.any():
            counts[reason] = int(hit.sum())
        keep &= ~bad
    return keep, counts


def _period_s(df):
    """Logging period: median step of the display clock between consecutive records (1 s on the reference card)."""
    t = df["disp_time"].values.astype("datetime64[s]").astype(np.int64)
    st = np.diff(t)
    st = st[(np.diff(df["ctr"].values) == 1) & (st >= 0) & (st <= 10)]
    return float(np.median(st)) if len(st) else 1.0, st


def _utc_offset_h(df):
    """Display clock minus GNSS UTC, rounded to 0.25 h (None when the GNSS time is missing)."""
    tod = (df["disp_time"] - df["disp_time"].dt.normalize()).dt.total_seconds().values
    g = df["gnss_ms"].values / 1000.0
    ok = (df["gnss"].values > 0) & np.isfinite(tod) & (g > 0) & (g < 86400)
    if not ok.any():
        return None
    d = (tod[ok] - g[ok]) / 3600.0
    d = (d + 12) % 24 - 12
    return float(np.round(np.median(d) * 4) / 4)


def decode(root, unit_ids, opts: DecodeOptions | None = None, log=print, calibration: str = "task"):
    """Decode the chosen units into the standard table + decode report (see the module docstring).

    calibration: "task" (default) = each task's own curve (.tsh), as the display and SMS; "latest" = the crop's
    current curve (.ycc) for every task."""
    t_start = _time.time()
    opts = opts or DEFAULT_OPTIONS
    if calibration not in ("task", "latest"):
        raise ValueError(f"calibration must be 'task' or 'latest', not {calibration!r}")
    rows, _ = catalogue(root)
    by_id = {r["id"]: r for r in rows}
    missing = [u for u in unit_ids if u not in by_id]
    if missing:
        raise ValueError(f"unknown unit id(s): {missing[:5]}")
    warnings, pre, frames, units_rep, cal_units = [], {}, [], [], []
    n_read, longer_seen, tag_seen, copies_seen, partial_seen = 0, set(), set(), [], set()
    bump = lambda k, n: pre.__setitem__(k, pre.get(k, 0) + int(n))   # noqa: E731
    tz_offsets = []
    for uid in unit_ids:
        r = by_id[uid]
        if not r["card_complete"]:
            warnings.append(f"{r['task']}: partial card copy (no index.vy1); names may be missing")
        if r["table_note"]:
            warnings.append(f"{r['task']}: {r['table_note']}")
        if r.get("copies", 1) > 1 and not copies_seen:
            copies_seen.append(r["task"])
            warnings.append(f"the upload holds {r['copies']} copies of the card with the same tasks: each task is "
                            "decoded once (the copy with the most records)")
        lagging_tag = r["season"] is not None and r["year"] is not None and int(r["season"]) != int(r["year"])
        if lagging_tag and (r["field"], r["season"]) not in tag_seen:
            tag_seen.add((r["field"], r["season"]))
            warnings.append(f"{r['field']}: season tag {r['season']} on the card, tasks harvested in {r['year']}: the "
                            "harvest year is used (the operator did not move the field's season on the display)")
        # a crop chosen by the user that differs from the card's crop replaces the card's test weight and standard
        # moisture too (they belong to the card's crop), as jd_gs3_rcd does
        override = bool(opts.crop) and r["crop_key"] is not None and opts.crop.strip().lower() != r["crop_key"]
        try:
            if override:
                crop, tw, sm = opts.resolve(None, None, None)
                warnings.append(f"{r['task']}: card crop {r['product']!r} (crop {r['crop']}) replaced by {opts.crop!r}; "
                                f"the card's test weight ({r['tw']}) and standard moisture ({r['std_m']}) are not used")
            else:
                crop, tw, sm = opts.resolve(r["crop_key"], r["tw"], r["std_m"])
        except ValueError as e:
            raise ValueError(f"{r['task']} ({r['field']} {r['year']}): crop number {r['crop']} has no test weight / "
                             f"standard moisture on this card (crop table .ycs missing or unknown crop): choose the "
                             f"crop or give test_weight_lb_bu and std_moisture_pct ({e})") from None
        df, notes = read_task(r["base"])
        n_read += notes["records in .tlo"]
        if notes["no .tlh record (counter join)"]:
            bump("no .tlh record for the .tlo counter", notes["no .tlh record (counter join)"])
        if notes["records of another length"]:
            warnings.append(f"{r['task']}: {notes['records of another length']} records shorter than the layout skipped")
        for ext, known in ((".tlo", TLO_LEN), (".tlh", TLH_LEN)):
            found = notes["record bytes"][ext]
            if found is not None and found != known and (ext, found) not in longer_seen:
                longer_seen.add((ext, found))
                warnings.append(f"{ext} records of {found} bytes on this card (documented layout {known} bytes): the "
                                f"first {known} are read, the {found - known} appended bytes are ignored (newer display "
                                "software; positions, width, flow and moisture decode as on the reference card)")
        flags = notes["logging byte values"]
        if any(v not in (0, 1) for v in flags) and ("logging bits",) not in longer_seen:
            longer_seen.add(("logging bits",))
            warnings.append(f".tlo[0] holds the values {flags} on this card (newer display software): bit 0 (area "
                            "counting on) decides the logging state, the other bits are ignored")
        period, _ = _period_s(df)
        off = _utc_offset_h(df)
        if off is not None:
            tz_offsets.append(off)
        sh = _task_sh(r["base"] + ".tsh")
        latest = None
        if r["tables"] is not None and r["crop"] in r["tables"]["ycc"]:
            ycc_t, ycc_p = r["tables"]["ycc"][r["crop"]]
            latest = dict(curve=np.array(struct.unpack_from("<11H", ycc_p, 0), float), comp=ycc_p[46], time=ycc_t)
        if curve_last_point(sh["curve"]) < len(sh["curve"]) - 1 and "partial curve" not in partial_seen:
            partial_seen.add("partial curve")
            warnings.append(f"{r['task']}: calibration curve defined up to point {curve_last_point(sh['curve'])} only "
                            "(single-point calibration of a newer display software): the flow is extended linearly "
                            "from its last defined segment")
        if calibration == "latest":
            if latest is None:
                raise ValueError(f"{r['task']}: no current calibration (.ycc) for crop {r['crop']} on the card")
            curve, comp, src = latest["curve"], latest["comp"], f"crop {r['crop']} current curve (.ycc, {latest['time']})"
        else:
            curve, comp, src = sh["curve"], sh["comp"], f"task curve (.tsh of {r['task']})"

        # ---- readings the vendor software exports, everything else counted by reason
        keep, counts = select_readings(df)
        for reason, n in counts.items():
            bump(reason, n)
        all_log = df[df.logging.values & df.flow_ok.values]
        g = df[keep].reset_index(drop=True)
        if not len(g):
            warnings.append(f"{r['task']}: no reading left after the pre-step")
            continue
        M = g.hB.values / 10.0
        fl, n_neg = flow_lb_s(g.hA.values, M, curve, comp)
        if n_neg:
            bump("(kept) flow below the curve zero -> 0 lb/s", n_neg)
        speed = g.dist_mm.values / 1000.0 / g.dt_byte.values                    # m/s
        dist_ft = speed * period * FT_PER_M
        width_ft = g.width_m.values * FT_PER_M
        wet_lb = fl * period
        area_ac = dist_ft * width_ft / SQFT_PER_AC
        y = yield_columns(wet_lb, area_ac, M, tw, sm, opts.shrink)
        mid_ok = ~g.ends_bad.values
        if (~mid_ok).any():
            bump("(kept) header ends missing -> logged point used", (~mid_ok).sum())
            warnings.append(f"{r['task']}: {(~mid_ok).sum()} readings without header ends use the logged point")
        lat = np.where(mid_ok, (g.latL.values + g.latR.values) / 2, g.lat0.values)
        lon = np.where(mid_ok, (g.lonL.values + g.lonR.values) / 2, g.lon0.values)
        tloc = g.disp_time
        if opts.tz_offset_h is not None:
            if off is None:
                warnings.append(f"{r['task']}: no GNSS time to measure the display clock offset; Time left on the "
                                "display clock (tz_offset_h ignored)")
            else:
                tloc = tloc + pd.to_timedelta(opts.tz_offset_h - off, unit="h")
        frames.append(pd.DataFrame({
            "Field": r["field"], "Product": crop if override else r["product"],
            "Dataset": dataset_name(r["task"], r["start"] if not pd.isna(r["start"]) else g.disp_time.min()),
            "Obj__Id": np.arange(1, len(g) + 1), "Time": tloc.dt.strftime("%Y-%m-%d %H:%M:%S.0").values,
            "Duration_s": period, "Elevation_": g.alt_m.values * FT_PER_M, "Speed_mph_": speed * MPH_PER_MS,
            "Distance_f": dist_ft, "Track_deg_": g.heading.values, "Swth_Wdth_": width_ft, "Moisture__": M,
            **y, "Machine": r["vehicle"], "Src_Fmt": FORMAT_ID, "lon": lon, "lat": lat}))

        # ---- calibration bookkeeping for this unit
        Ma = all_log.hB.values / 10.0
        kg_task = flow_lb_s(all_log.hA.values, Ma, sh["curve"], sh["comp"])[0].sum() * period / LB_PER_KG
        kg_used = flow_lb_s(all_log.hA.values, Ma, curve, comp)[0].sum() * period / LB_PER_KG
        kg_latest = flow_lb_s(all_log.hA.values, Ma, latest["curve"], latest["comp"])[0].sum() * period / LB_PER_KG \
            if latest is not None else None
        same_curve = latest is not None and np.array_equal(latest["curve"], sh["curve"]) and latest["comp"] == sh["comp"]
        disp_ratio = kg_task / sh["display_kg"] if sh["display_kg"] else None
        cu = dict(unit=uid, task=r["task"], crop=int(r["crop"]), product=r["product"], curve_used=src,
                  crop_used=crop, test_weight_lb_bu=tw, std_moisture_pct=sm, crop_replaced_by_user=override,
                  curve=[int(v) for v in curve], moisture_comp_per_point=comp / 1e4,
                  task_curve_written=str(sh["written"]), current_curve_written=None if latest is None else str(latest["time"]),
                  task_curve_equals_current=bool(same_curve), calibration_load=bool(sh["flags"] & 0x08),
                  display_total_kg=sh["display_kg"], decoded_total_kg_task_curve=round(float(kg_task), 1),
                  decoded_over_display=None if disp_ratio is None else round(float(disp_ratio), 4),
                  latest_over_task_mass=None if kg_latest is None or kg_task <= 0 else round(float(kg_latest / kg_task), 4),
                  used_total_kg=round(float(kg_used), 1))
        cal_units.append(cu)
        if latest is not None and not same_curve and kg_task > 0 and abs(kg_latest / kg_task - 1) > CURVE_TOL:
            warnings.append(
                f"{r['task']}: its curve differs from crop {r['crop']}'s current calibration ({latest['time']}); "
                f"the current one would change its mass x{kg_latest / kg_task:.3f}"
                + (" (applied: calibration='latest')" if calibration == "latest" else " (not applied: calibration='task', as SMS)"))
        if disp_ratio is not None and abs(disp_ratio - 1) > DISPLAY_TOL:
            warnings.append(
                f"{r['task']}: decoded mass with its stored curve = {kg_task:,.0f} kg vs the display's own total "
                f"{sh['display_kg']:,} kg (x{disp_ratio:.3f}): the calibration in effect while harvesting was replaced "
                "afterwards" + (" (this task was a calibration load)" if sh["flags"] & 0x08 else ""))
        dsum = float(g.dt_byte.sum())
        units_rep.append(dict(id=uid, label=_unit_label(r), task=r["task"], field=r["field"], farm=r["farm"],
                              grower=r["grower"], season=r["year"], card_season_tag=r["season"], crop=int(r["crop"]),
                              product=r["product"],
                              test_weight_lb_bu=tw, std_moisture_pct=sm, n_records=int(len(df)), n_readings=int(len(g)),
                              logging_period_s=period, interval_byte_sum_s=round(dsum, 1),
                              interval_byte_over_period=round(dsum / (period * len(g)), 4) if len(g) else None,
                              display_minus_utc_h=off))
        if abs(period - 1.0) > 1e-9:
            warnings.append(f"{r['task']}: logging period {period:g} s (display clock), not 1 s")
        log(f"  {r['task']} {r['field']} {r['year']}: {len(df):,} records -> {len(g):,} readings "
            f"({units_rep[-1]['product']}, {tw:g} lb/bu, std {sm:g} %)")

    if not frames:
        raise ValueError("no readings decoded from the selected units")
    out = pd.concat(frames, ignore_index=True)
    probs = check_standard(out)
    if probs:
        raise ValueError("decoded table fails the standard schema: " + "; ".join(probs))
    machines, totals = summarize(out)
    tb = "local" if (opts.tz_offset_h is not None or tz_offsets) else "unknown"
    off_txt = sorted(set(tz_offsets))
    report = {
        "format": FORMAT_ID, "label": LABEL, "units": units_rep, "n_records_read": int(n_read), "n_readings": int(len(out)),
        "pre_step": pre, "machines": machines, "totals": totals,
        "time_basis": tb,
        "calibration": {
            "mass_channel": ".tlh[1:3] raw mass-flow count hA (wet grain), with grain moisture .tlh[5]/10 %",
            "formula": "flow_lb_s = (curve(u) - 1000) / 100, u = hA/1000 * (1 + c*(14.0 - M)), curve = 11 points at "
                       "u = 0..10 (linear beyond the last defined point: 10, or 1 for a single-point calibration), "
                       "c = moisture compensation / 10000",
            "curve_source": calibration,
            "interval": "one record = the logging period (median display-clock step, 1 s on the reference card); "
                        "the interval byte .tlo[1] is NOT used for mass or distance",
            "validation": "reference card Trial 19 field A 2026 (crop 17 barley): Crop_Flw_M of the Ag Leader SMS "
                          "export reproduced within 0.5 % on 99.98 % of 33,017 points (all 5 tasks, median ratio "
                          "1.0000) and the wet yield of every point (median ratio 1.0000); decoded/display task "
                          "totals 1.002-1.003 on the 2026 tasks with an unchanged calibration and 0.996-1.003 on the "
                          "2024 canola and 2025 wheat tasks. Validated against SMS on crop 17 only; other crops "
                          "only against the display's own task totals (see decoded_over_display per unit).",
            "shrink": opts.shrink, "units": cal_units,
        },
        "warnings": warnings,
    }
    if off_txt:
        report["calibration"]["time_note"] = (
            f"Time = display clock (local), display - GNSS UTC = {', '.join(f'{o:+.2f}' for o in off_txt)} h"
            + (f"; shifted to UTC{opts.tz_offset_h:+g} h on request" if opts.tz_offset_h is not None else ""))
    if opts.shrink != DEFAULT_SHRINK:
        warnings.append(f"shrink '{opts.shrink}' requested; the vendor software uses '{DEFAULT_SHRINK}' for this format")
    log(f"decoded {len(out):,} readings from {n_read:,} records in {_time.time() - t_start:.1f} s")
    return out, report
