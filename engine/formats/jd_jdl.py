# -*- coding: utf-8 -*-
"""John Deere Gen4 / G5 display logs (``JD-Data/log/<year>/<guid>.jdl``, X9 / S-series combines) -> standard readings.

METHOD (byte layout and evidence in docs/formats/jd_jdl.md; numbers from tools/validate_jd_jdl.py; tests in
tests/test_jd_jdl.py)

Container. A .jdl file is a sequence of frames ``0x0D | uint32 LE length | protobuf message``, read without a .proto by
walking the protobuf wire format along KNOWN paths only (never guessing whether a byte string is a sub-message).
Frame 0 is a small header; the frame with top-level field 5 holds the DEFINITIONS of the file (machine VIN / model,
header width and geometry, the section-control sections, every logged channel with its ISO 11783 DDI, unit, factor and
offset, client / farm / field names, crop, variety, test weight, standard moisture). Every other frame holds one
~30 s DATA BLOCK (frame field 4): header {3 sequence, 4 start offset in ms (signed) from the file reference time,
5 duration ms} and the records {1 record types, 2 element / channel ids, 3 record bodies}.

Delta streams. Every record is an anchored delta stream: the anchor fields hold the LAST value of the previous block
(the carry) and its time; packed zig-zag varint arrays hold the new samples as differences.
    sample time  = file reference + block start + cumsum(time deltas)      (the anchor time is NOT the base)
    sample value = (anchor + cumsum(value deltas)) / factor + offset
Evidence: block after block, anchor_k+1 = anchor_k + sum(deltas_k) and anchor time_k+1 = last sample time_k, exactly.
A record with no anchor at all (first block of a log session) is absolute (anchor 0: its first latitude delta is
52.50e9 = 52.50 deg). Raw values <= -2^31 are "not available" and dropped.
    type 3 = one logged channel (id -> DDI / unit / factor / offset from the definitions)
    type 1 = GNSS receiver, 5 Hz: lat, lon x 1e9 deg (anchors 1, 2 / deltas 12, 13), altitude mm (4 / 16), time (- / 10)
    type 2 = the header element, 5 Hz: the two END POINTS of the cutter bar as placed by the display (antenna + the
             configured header offset), lat/lon x 1e9 deg (anchors 1-4 / deltas 17-20), time (- / 15)
    type 4 = condensed section work state per group of 16 sections: carry state (3), change times (1), new states (2)

Readings. One reading per sample of DDI 510 (wet mass flow, mg/s, 1 Hz), the clock of the yield channels. The yield
channels (DDI 510, 6 moisture, 39/43 yields) carry a -14 s delay in their definitions and are logged already shifted
to the moment the crop was cut. Matching the Ops Center export of the reference harvest point by point fixes the rest
of the timing (scan in tools/validate_jd_jdl.py, same optimum on all four combines):
    position     the header centre at t + POS_LAG_MS (0.8 s): Ops Center's flow at a point = DDI 510 interpolated
                 0.8 s earlier; moved along the bar to the centre of the ACTIVE sections (type-4 states at the same
                 instant; ISO 11783 y is positive to the right of travel - the side is read, not assumed)
    width        DDI 12001 (active cutting width) at t + POS_LAG_MS + WIDTH_LAG_MS (the logged width trails the
                 section states by 0.8 s); without that channel, or when it reads wider than the header (Trial 23:
                 64.256 m on a 13.716 m header), the sum of the active sections at the position time
    Duration_s   time since the previous flow sample (gaps longer than DT_MAX_S -> the median interval, counted)
    distance     path of the full-width header centre (5 Hz end points) over the reading interval; speed = distance
                 / duration. Ops Center speed is this track speed; the wheel speed DDI 560 reads 0.6-3.3 % low and is
                 only a diagnostic
    wet mass     flow x duration = the display's calibrated wet grain mass; the resulting wet yield equals the
                 monitor's own DDI 39 yield (median ratio 0.999 on every combine)
    heading      perpendicular to the cutter bar, pointing in the direction of travel (sign fixed per machine)
    moisture     DDI 6 (ppm -> %), nearest sample within 1.5 s of t; over a gap in the moisture channel the last
                 sample is held for up to MOIST_HOLD_MS (10 s), as Ops Center does (Trial 29: 9 readings in gaps of
                 3 and 6 s carry the previous value in the export, 12.9 and 13.1 %)
    elevation    GNSS antenna altitude at the position time, ft (= Ops Center Elevation_)
Only readings the vendor software exports are kept; the rest are counted in report["pre_step"] by reason, in this
order: header_up (logged width 0), no_position (no header sample within 1 s, or outside the position record),
stationary (track speed below V_MIN_KMH), position_outlier (more than 50 km from the machine's median position),
no_moisture (the moisture channel exists but has no sample within the hold time, so there is no dry yield).
Readings are never dropped by yield value - the cleaning does that (Ops Center itself drops readings below 5 bu/ac).

Yield. common.yield_columns from the wet mass and area. Test weight: DDI 8 / the monitor's crop record. Standard
moisture: DecodeOptions > OPS_CENTER_STD_MOISTURE (measured: Ops Center applies 13.5 % to wheat, the monitor's crop
record says 13.0 %, a warning records the difference) > the monitor's crop record > common.CROPS. A crop chosen in
DecodeOptions.crop that differs from the monitor's replaces the monitor's test weight and standard moisture as well
(they belong to the monitor's crop) and becomes the Product; a warning records it. The John Deere dry
convention measured on the export is ONE-SIDED shrink (grain drier than the standard is not credited; it explains 100 %
of the export's Yld_Vol_Dr / Yld_Vol_We); it is this format's default (``default_options()``; ``decode(opts=None)``).
"""
from __future__ import annotations

import dataclasses
import os
import struct
import time as _time

import numpy as np
import pandas as pd

from . import common as C

FORMAT_ID = "jd_jdl"
LABEL = "John Deere Gen4 / G5 display logs (JD-Data/log/*.jdl)"

DEFAULT_SHRINK = "one_sided"         # measured on the Ops Center export of the reference harvest (docs/formats/jd_jdl.md)
# Standard moisture John Deere Operations Center applies when it computes Yld_Vol_Dr, MEASURED per crop on a reference
# export (it can differ from the monitor's own crop record: Trial 29 wheat, monitor 13.0 %, Ops Center 13.5 %).
# Crops not listed fall back to the monitor's crop record, then to common.CROPS.
OPS_CENTER_STD_MOISTURE = {"wheat": 13.5}
NA_RAW = -2147483648                 # raw values <= this are "not available"
DT_MAX_S = 3.0                       # a flow interval longer than this is a logging gap -> nominal duration
POS_MAX_GAP_MS = 1000                # the header position must have a sample within 1 s of the reading
MOIST_TOL_MS = 1500
MOIST_HOLD_MS = 10_000               # over a moisture gap hold the last sample this long (Ops Center holds it, 6 s seen)
V_MIN_KMH = 0.3                      # below this the combine is stationary (Ops Center keeps >= 0.181 mph = 0.29 km/h)
POS_LAG_MS = 800                     # the flow sample at t belongs to the header position at t + 0.8 s (Ops Center, docs)
WIDTH_LAG_MS = 800                   # DDI 12001 (logged width) reports the section state 0.8 s after the position (docs)
WIDTH_TOL = 0.02                     # a DDI 12001 width more than 2 % over the header's is not an active width
MONITOR_RATIO_TOL = 0.10             # decoded / monitor wet yield (DDI 39) farther than this from 1: warn
VALIDATION_NOTE = "docs/formats/jd_jdl.md (Trial 29 2026: Ops Center point match and grain-cart level)"
OUTLIER_KM = 50.0                    # fixes farther than this from the machine's median position are garbage (lat 0 / lon 0)
DDI_FLOW, DDI_MOIST, DDI_YWET, DDI_YDRY, DDI_SPEED, DDI_WIDTH, DDI_TW, DDI_STDM = 510, 6, 39, 43, 560, 12001, 8, 75
WANT = {(DDI_FLOW, "mg1sec-1"), (DDI_MOIST, "ppm"), (DDI_YWET, "bu1ac-1"), (DDI_YDRY, "bu1ac-1"),
        (DDI_SPEED, "km1hr-1"), (DDI_WIDTH, "m"), (DDI_TW, "lb1bu-1"), (DDI_STDM, "prcnt")}
KG_PER_LB = 1.0 / C.LB_PER_KG
_D = struct.Struct("<d")
_F = struct.Struct("<f")
_I = struct.Struct("<I")


class JdlError(ValueError):
    pass


def default_options() -> C.DecodeOptions:
    """DecodeOptions with this format's default shrink convention (John Deere: one-sided)."""
    return C.DecodeOptions(shrink=DEFAULT_SHRINK)


# ================================================================================================ protobuf wire walking
def _varint(b, i):
    r = 0
    s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if x < 0x80:
            return r, i
        s += 7


def _s64(v):
    return v - (1 << 64) if v >= (1 << 63) else v


def _fields(b):
    """Shallow walk of one protobuf message -> list of (field, wiretype, value); length-delimited values stay bytes."""
    out = []
    i, n = 0, len(b)
    while i < n:
        key, i = _varint(b, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, i = _varint(b, i)
        elif wt == 2:
            ln, i = _varint(b, i)
            v = b[i:i + ln]
            i += ln
        elif wt == 1:
            v = _D.unpack_from(b, i)[0]
            i += 8
        elif wt == 5:
            v = _F.unpack_from(b, i)[0]
            i += 4
        else:
            raise JdlError(f"unsupported wire type {wt} (field {f})")
        out.append((f, wt, v))
    return out


def _first(fs, f, default=None):
    for a, _, v in fs:
        if a == f:
            return v
    return default


def _all(fs, f):
    return [v for a, _, v in fs if a == f]


def _num(v):
    """Scalar of a wt0 (varint, signed) or wt1 (double) field."""
    if v is None:
        return None
    return _s64(v) if isinstance(v, int) else float(v)


def _str(v):
    return v.decode("utf-8", errors="replace") if isinstance(v, (bytes, bytearray)) else ""


def _uvarints(b) -> np.ndarray:
    """Packed varints -> uint64 array (vectorised)."""
    if not b:
        return np.zeros(0, np.uint64)
    a = np.frombuffer(b, np.uint8)
    end = a < 0x80
    starts = np.r_[0, np.flatnonzero(end)[:-1] + 1]
    grp = np.cumsum(np.r_[0, end[:-1]].astype(np.int64))
    pos = (np.arange(len(a)) - starts[grp]).astype(np.uint64)
    vals = (a & 0x7F).astype(np.uint64) << (np.uint64(7) * pos)
    return np.add.reduceat(vals, starts)


def _zz(b) -> np.ndarray:
    """Packed zig-zag varints -> int64 array."""
    u = _uvarints(b)
    return (u >> np.uint64(1)).astype(np.int64) ^ -((u & np.uint64(1)).astype(np.int64))


# ================================================================================================ file level
def _read_frames(path, max_bytes=None):
    """Frame payloads of a .jdl file. Returns (payloads, warning or None). A truncated last frame is dropped."""
    with open(path, "rb") as fh:
        data = fh.read() if max_bytes is None else fh.read(max_bytes)
    out, i, n = [], 0, len(data)
    while i + 5 <= n:
        if data[i] != 0x0D:
            return out, f"{os.path.basename(path)}: bad frame marker 0x{data[i]:02x} at byte {i}; rest of file ignored"
        ln = _I.unpack_from(data, i + 1)[0]
        if i + 5 + ln > n:
            if max_bytes is None:
                return out, f"{os.path.basename(path)}: truncated last frame at byte {i}"
            break
        out.append(data[i + 5:i + 5 + ln])
        i += 5 + ln
    return out, None


@dataclasses.dataclass
class FileMeta:
    path: str
    guid: str = ""
    ref_ms: int = 0
    vin: str = ""
    model: str = ""
    width_m: float = float("nan")
    display: str = ""
    software: str = ""
    client: str = ""
    farm: str = ""
    field: str = ""
    crop: str = ""
    variety: str = ""
    tw_kg_bu: float | None = None
    std_moisture: float | None = None
    year: int | None = None
    header_id: int | None = None
    header_xyz_mm: tuple = ()
    gnss_id: int | None = None
    gnss_xyz_m: tuple = ()
    channels: dict = dataclasses.field(default_factory=dict)    # id -> (ddi, unit, offset, factor, delay_s)
    sections: pd.DataFrame | None = None    # id, width_m, y_m, cws_id, cws_idx, grp (left-to-right rank of the group)
    size: int = 0


def _parse_definitions(pay, path) -> FileMeta | None:
    """The definition frame (top-level field 5) -> FileMeta; None when the payload is not a definition frame."""
    top = _fields(pay)
    blk = _first(top, 5)
    if blk is None:
        return None
    b = _fields(blk)
    m = FileMeta(path=path, guid=_str(_first(b, 2)), ref_ms=_num(_first(b, 3)) or 0, display=_str(_first(b, 5)),
                 software=_str(_first(b, 24)), year=_num(_first(b, 17)), size=os.path.getsize(path))
    for key, attr in ((11, "client"), (12, "farm"), (13, "field")):
        x = _first(b, key)
        if x is not None:
            setattr(m, attr, _str(_first(_fields(_first(_fields(x), 1, b"")), 2, b"")).strip())
    crop = _first(b, 21)
    if crop is not None:
        cf = _fields(crop)
        c1 = _first(cf, 1)
        if c1 is not None:
            c1f = _fields(c1)
            m.crop = _str(_first(c1f, 2)).strip()
            for key, attr in ((5, "tw_kg_bu"), (6, "std_moisture")):
                x = _first(c1f, key)
                if x is not None:
                    xf = _fields(x)
                    v, unit = _first(xf, 1), _str(_first(xf, 3))
                    if v is not None:
                        v = float(v)
                        if attr == "tw_kg_bu" and unit == "lb1bu-1":
                            v = v * KG_PER_LB
                        setattr(m, attr, v)
        c2 = _first(cf, 2)                                # 21.2.1.1.2 = variety name
        if c2 is not None:
            v1 = _first(_fields(c2), 1)
            v2 = _first(_fields(v1), 1) if v1 is not None else None
            if v2 is not None:
                m.variety = _str(_first(_fields(v2), 2)).strip()
    eq = _first(b, 10)
    if eq is None:
        return m
    eqf = _fields(eq)
    rcv = _first(eqf, 3)
    if rcv is not None:
        rf = _fields(rcv)
        m.gnss_id = _first(rf, 1)
        g = _first(rf, 3)
        if g is not None:
            gf = _fields(g)
            m.gnss_xyz_m = tuple(float(_first(gf, k, 0.0)) for k in (1, 2, 3))
    secs = []
    for mach in _all(eqf, 2):                             # machine device(s): the combine (and any implement device)
        mf = _fields(mach)
        if not m.vin and _first(mf, 4) is not None:
            m.vin = _str(_first(mf, 4)).strip()
            m.model = _str(_first(mf, 5)).strip()
            w = _first(mf, 6)
            m.width_m = float(w) if w is not None else float("nan")
        if m.gnss_id is None:
            m.gnss_id = _first(mf, 26)
        for el in _all(mf, 7):                            # device elements
            ef = _fields(el)
            hdr = _first(ef, 3)                           # the header (cutter bar) element: id + geometry (mm)
            if hdr is not None and m.header_id is None:
                hf = _fields(hdr)
                m.header_id = _first(hf, 1)
                g = _first(hf, 3)
                if g is not None:
                    gf = _fields(g)
                    m.header_xyz_mm = tuple(float(_first(gf, k, 0.0)) for k in (1, 2, 3))
            for s in _all(ef, 4):                         # sections: id, width (m), offsets (mm), work-state group
                sf = _fields(s)
                cws = _first(sf, 7)
                if cws is None:
                    continue                              # the boom-level element (whole header), not a section
                g = _fields(_first(sf, 3, b""))
                secs.append((_first(sf, 1), float(_first(sf, 2, 0.0)), float(_first(g, 2, 0.0)) / 1000.0, cws,
                             _first(sf, 16, 0)))
            for c in _all(ef, 5):                         # logged channels
                cf = _fields(c)
                cid = _first(cf, 1)
                off = _first(cf, 3)
                fac = _first(cf, 4)
                m.channels[cid] = (_first(cf, 2), _str(_first(cf, 5)), float(off) if off is not None else 0.0,
                                   float(fac) if fac else 1.0, _first(cf, 9))
    if secs:
        sec = pd.DataFrame(secs, columns=["id", "width_m", "y_m", "cws_id", "cws_idx"]).sort_values("y_m")
        # element ids change between log sessions of the same machine: the work-state groups are identified by their
        # left-to-right rank instead (the section layout of a header does not change)
        rank = sec.groupby("cws_id").y_m.min().rank(method="first").astype(int) - 1
        sec["grp"] = sec.cws_id.map(rank).astype(int)
        m.sections = sec.reset_index(drop=True)
    return m


def read_meta(path) -> FileMeta | None:
    """Definitions of one .jdl without decoding its data (reads only the first frames)."""
    with open(path, "rb") as fh:
        head = fh.read(5)
        if len(head) < 5 or head[0] != 0x0D:
            return None
        ln0 = _I.unpack_from(head, 1)[0]
        fh.seek(5 + ln0)
        h1 = fh.read(5)
        if len(h1) < 5 or h1[0] != 0x0D:
            return None
        ln1 = _I.unpack_from(h1, 1)[0]
        pay = fh.read(ln1)
    try:
        return _parse_definitions(pay, path)
    except (IndexError, JdlError, struct.error):
        return None


@dataclasses.dataclass
class FileData:
    meta: FileMeta
    samples: dict            # (ddi, unit) -> [t_ms int64 array, value float array]
    gnss: pd.DataFrame       # t_ms, lat, lon, alt_m
    ends: pd.DataFrame       # t_ms, lat1, lon1, lat2, lon2   (header end points)
    cws: dict                # group rank -> (t_ms int64 array, states uint8 2-D array (n_events x n_sections))
    n_blocks: int = 0
    n_records: int = 0
    n_absolute: int = 0      # records without a carry (first block of a log session): absolute arrays
    n_incomplete: int = 0    # position records missing a delta array (skipped)
    warnings: list = dataclasses.field(default_factory=list)


def _stream(rec_fields, anchors, deltas, t_delta, bs):
    """Anchored delta stream of a type-1 / type-2 record -> (t_ms, [value arrays], absolute), "carry" (no new samples)
    or None (malformed).
    A record with NONE of its anchors is an absolute record (first block of a log session): the first delta is the
    absolute value, i.e. the anchor is 0 (verified: the first latitude delta of such records is 52.50e9 = 52.50 deg)."""
    d = {a: v for a, _, v in rec_fields}
    if t_delta not in d:
        return "carry"                                   # anchors only: no new sample in this block
    if any(k not in d for k in deltas):
        return None
    have = [a in d for a in anchors]
    if any(have) and not all(have):
        return None
    dts = _zz(d[t_delta])
    arrs = [_zz(d[k]) for k in deltas]
    n = min([len(dts)] + [len(x) for x in arrs])
    if n == 0:
        return None
    t = bs + np.cumsum(dts[:n])
    absolute = not any(have)
    vals = [(0.0 if absolute else float(_num(d[a]))) + np.cumsum(x[:n]).astype(float) for a, x in zip(anchors, arrs)]
    return t, vals, absolute


def decode_file(path, meta: FileMeta | None = None) -> FileData:
    """Decode the data blocks of one .jdl (only the channels in WANT, the GNSS, the header ends and the section states)."""
    frames, warn = _read_frames(path)
    if meta is None:
        meta = next((x for x in (_parse_definitions(p, path) for p in frames[:3]) if x is not None), None)
        if meta is None:
            raise JdlError(f"{os.path.basename(path)}: no definition frame")
    ref = int(meta.ref_ms)
    want = {cid: c for cid, c in meta.channels.items() if (c[0], c[1]) in WANT}
    S = {}
    G, E = [], []
    CW = {}
    out = FileData(meta=meta, samples={}, gnss=None, ends=None, cws={})
    if warn:
        out.warnings.append(warn)
    for pay in frames:
        for f, wt, blk in _fields(pay):
            if f != 4 or wt != 2:
                continue
            hf = _fields(blk)
            bs = ref + _s64(_first(hf, 4, 0))
            out.n_blocks += 1
            for v9 in _all(hf, 9):
                types, ids, recs = [], None, []
                for f3, wt3, v3 in _fields(v9):
                    if f3 == 1:
                        if wt3 == 0:
                            types.append(v3)
                        else:
                            types.extend(_uvarints(v3).tolist())
                    elif f3 == 2 and wt3 == 2:
                        ids = _uvarints(v3).tolist()
                    elif f3 == 3 and wt3 == 2:
                        recs.append(v3)
                if ids is None:
                    continue
                if not (len(types) == len(ids) == len(recs)):
                    out.warnings.append(f"{os.path.basename(path)}: block with {len(types)} types / {len(ids)} ids / "
                                        f"{len(recs)} records skipped")
                    continue
                out.n_records += len(recs)
                for t, cid, raw in zip(types, ids, recs):
                    if t == 3:
                        c = want.get(cid)
                        if c is None:
                            continue
                        d = {a: (w, v) for a, w, v in _fields(raw)}
                        if 2 not in d or 3 not in d or d[2][0] != 2 or d[3][0] != 2:
                            continue                                    # carry only, no new samples
                        if 1 in d:
                            v0 = _num(d[1][1])
                        else:                                           # absolute record (no carry): anchor 0
                            v0 = 0
                            out.n_absolute += 1
                        dts, dvs = _zz(d[2][1]), _zz(d[3][1])
                        n = min(len(dts), len(dvs))
                        if n == 0:
                            continue
                        raw_v = float(v0) + np.cumsum(dvs[:n]).astype(float)
                        ok = raw_v > NA_RAW
                        key = (c[0], c[1])
                        S.setdefault(key, [[], []])
                        S[key][0].append((bs + np.cumsum(dts[:n]))[ok])
                        S[key][1].append(raw_v[ok] / c[3] + c[2])
                    elif t == 1 and (meta.gnss_id is None or cid == meta.gnss_id):
                        r = _stream(_fields(raw), (1, 2, 4), (12, 13, 16), 10, bs)
                        if r is None:
                            out.n_incomplete += 1
                        if r is None or r == "carry":
                            continue
                        out.n_absolute += r[2]
                        G.append((r[0], r[1][0] / 1e9, r[1][1] / 1e9, r[1][2] / 1000.0))
                    elif t == 2 and (meta.header_id is None or cid == meta.header_id):
                        r = _stream(_fields(raw), (1, 2, 3, 4), (17, 18, 19, 20), 15, bs)
                        if r is None:
                            out.n_incomplete += 1
                        if r is None or r == "carry":
                            continue
                        out.n_absolute += r[2]
                        E.append((r[0], *(x / 1e9 for x in r[1])))
                    elif t == 4:
                        d = _fields(raw)
                        ev_t, ev_s = [], []
                        carry = _first(d, 3)
                        t12 = _first(d, 12)
                        if carry is not None and t12 is not None:
                            ev_t.append(np.array([ref + _s64(t12)], np.int64))
                            ev_s.append([_first(_fields(carry), 1, b"")])
                        times = _first(d, 1)
                        states = _all(d, 2)
                        if times is not None and states:
                            tt = bs + np.cumsum(_zz(times))
                            k = min(len(tt), len(states))
                            ev_t.append(tt[:k])
                            ev_s.append([_first(_fields(s), 1, b"") for s in states[:k]])
                        if ev_t:
                            lst = CW.setdefault(cid, [[], []])
                            lst[0].extend(ev_t)
                            lst[1].extend(ev_s)
    for key, (tt, vv) in S.items():
        out.samples[key] = [np.concatenate(tt), np.concatenate(vv)]
    cols = ["t_ms", "lat", "lon", "alt_m"]
    out.gnss = (pd.DataFrame({c: np.concatenate([g[i] for g in G]) for i, c in enumerate(cols)}) if G
                else pd.DataFrame(columns=cols))
    cols = ["t_ms", "lat1", "lon1", "lat2", "lon2"]
    out.ends = (pd.DataFrame({c: np.concatenate([e[i] for e in E]) for i, c in enumerate(cols)}) if E
                else pd.DataFrame(columns=cols))
    for cid, (tt, ss) in CW.items():
        flat = [s for grp in ss for s in grp]
        width = max((len(s) for s in flat), default=0)
        arr = np.zeros((len(flat), width), np.uint8)
        for i, s in enumerate(flat):
            arr[i, :len(s)] = np.frombuffer(s, np.uint8)
        grp = (meta.sections.loc[meta.sections.cws_id == cid, "grp"].iloc[0]
               if meta.sections is not None and (meta.sections.cws_id == cid).any() else None)
        if grp is None:
            continue                                      # a work-state group that maps to no section
        out.cws[int(grp)] = (np.concatenate(tt).astype(np.int64), arr)
    return out


# ================================================================================================ discovery
def _jdl_files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "__MACOSX"]
        out.extend(os.path.join(dp, f) for f in fn if f.lower().endswith(".jdl"))
    return sorted(out)


def _scan(root):
    """Definitions of every .jdl under root, de-duplicated by file GUID and size. -> (list[FileMeta], warnings)"""
    metas, warns, seen = [], [], set()
    bad = dup = 0
    for p in _jdl_files(root):
        m = read_meta(p)
        if m is None or not m.vin:
            bad += 1
            continue
        key = (m.guid or os.path.basename(p).lower(), m.size)
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        metas.append(m)
    if bad:
        warns.append(f"{bad} .jdl file(s) without a readable definition frame were ignored")
    if dup:
        warns.append(f"{dup} duplicate .jdl file(s) (same GUID and size, e.g. a zip unpacked twice) were ignored")
    return metas, warns


def _crop_key(name):
    s = (name or "").lower()
    for k in ("durum", "wheat", "barley", "canola", "oats", "flax", "peas", "lentils", "rye", "corn", "soybeans"):
        if k in s or (k.endswith("s") and k[:-1] in s):
            return k
    return None


def _season(m: FileMeta) -> int:
    """Harvest year of a file: the definition's year field, else the UTC year of its reference time."""
    return int(m.year) if m.year else int(pd.Timestamp(m.ref_ms, unit="ms").year)


def _unit_key(m: FileMeta):
    """machine x field x crop x season: one JD-Data/log tree can hold several <year> folders, and two seasons of the
    same field must not be decoded into one dataset."""
    return f"{m.vin}::{m.field}::{m.crop}::{_season(m)}"


def _record_root(root, metas):
    """The folder that holds every JD-Data tree (the parent of JD-Data), or the files' common folder without one."""
    tops = []
    for m in metas:
        parts = os.path.normpath(m.path).split(os.sep)
        low = [x.lower() for x in parts]
        tops.append(os.sep.join(parts[:low.index("jd-data")]) if "jd-data" in low else os.path.dirname(m.path))
    try:
        rr = os.path.commonpath(tops)
    except ValueError:
        return root
    return rr if os.path.normcase(rr).startswith(os.path.normcase(os.path.abspath(root))) else root


def probe(root: str) -> C.Probe | None:
    """Recognise John Deere .jdl logs anywhere under root (only the definition frame of each file is read)."""
    metas, warns = _scan(root)
    if not metas:
        return None
    vins = sorted({m.vin for m in metas})
    models = {m.vin: m.model for m in metas}
    fields = sorted({m.field for m in metas if m.field})
    crops = sorted({m.crop for m in metas if m.crop})
    clients = sorted({x for m in metas for x in (m.client, m.farm) if x})
    summary = (f"{len(metas)} John Deere .jdl log file(s), {len(vins)} machine(s) "
               f"({', '.join(models[v] + ' ' + v[-6:] for v in vins)}); field: {', '.join(fields) or '(none)'}; "
               f"crop: {', '.join(crops) or '(none)'}; client/farm: {', '.join(clients) or '(none)'}")
    return C.Probe(format_id=FORMAT_ID, label=LABEL, root=_record_root(os.path.abspath(root), metas), summary=summary,
                   n_files=len(metas), machines=[f"{models[v]} {v}" for v in vins], warnings=warns)


def _block_span(path, ref):
    """(first sample time, last sample time) of a file from its block headers only (no record decoding)."""
    frames, _ = _read_frames(path)
    t0, t1 = None, None
    for pay in frames:
        for f, wt, blk in _fields(pay):
            if f != 4 or wt != 2:
                continue
            hf = []
            i, n = 0, len(blk)
            while i < n:                      # walk only the block header, stop at the data (field 9)
                key, j = _varint(blk, i)
                fn, w = key >> 3, key & 7
                if fn == 9:
                    break
                if w == 0:
                    v, j = _varint(blk, j)
                elif w == 2:
                    ln, j = _varint(blk, j)
                    v = None
                    j += ln
                elif w == 1:
                    v = None
                    j += 8
                else:
                    v = None
                    j += 4
                hf.append((fn, w, v))
                i = j
            s = ref + _s64(_first(hf, 4, 0))
            e = s + (_first(hf, 5, 0) or 0)
            t0 = s if t0 is None else min(t0, s)
            t1 = e if t1 is None else max(t1, e)
    return t0, t1


def list_units(root: str) -> list[C.Unit]:
    """One unit per machine x field x crop x season (a machine's logs of one field, all days of one season). The units
    of the latest season are pre-selected."""
    metas, _ = _scan(root)
    groups = {}
    for m in metas:
        groups.setdefault(_unit_key(m), []).append(m)
    latest = max((_season(m) for m in metas), default=None)
    units = []
    for key, ms in sorted(groups.items()):
        ms = sorted(ms, key=lambda x: x.ref_ms)
        spans = [_block_span(m.path, m.ref_ms) for m in ms]
        st = min((s[0] for s in spans if s[0] is not None), default=ms[0].ref_ms)
        en = max((s[1] for s in spans if s[1] is not None), default=ms[-1].ref_ms)
        n_s = int(sum((s[1] - s[0]) for s in spans if s[0] is not None) / 1000)
        m0 = ms[0]
        ts = pd.Timestamp(st, unit="ms", tz="UTC")
        te = pd.Timestamp(en, unit="ms", tz="UTC")
        # a tractor (grain cart) or a sprayer logs the same field and crop on the same display: no mass-flow channel
        harvest = any(v[0] == DDI_FLOW for m in ms for v in m.channels.values())
        label = (f"{m0.field or '(no field)'} · {_season(m0)} · {m0.crop or '?'} · {m0.model} {m0.vin[-6:]} · "
                 f"{ts:%d %b %Y %H:%M} - {te:%d %b %Y %H:%M} UTC · {len(ms)} file(s)"
                 + ("" if harvest else " · no grain-flow channel (not a combine)"))
        units.append(C.Unit(id=key, label=label, field=m0.field, crop=m0.crop, year=_season(m0),
                            start=ts.isoformat(), end=te.isoformat(), machine=m0.vin, n_records=n_s,
                            default=harvest and _season(m0) == latest))
    return units


# ================================================================================================ readings
def _concat_files(fds):
    """Merge the decoded files of one unit into sorted, de-duplicated streams."""
    S = {}
    for fd in fds:
        for k, (t, v) in fd.samples.items():
            S.setdefault(k, [[], []])
            S[k][0].append(t)
            S[k][1].append(v)
    samples = {}
    for k, (tt, vv) in S.items():
        t = np.concatenate(tt)
        v = np.concatenate(vv)
        o = np.argsort(t, kind="stable")
        t, v = t[o], v[o]
        keep = np.r_[True, np.diff(t) > 0]
        samples[k] = (t[keep], v[keep])
    gn = pd.concat([fd.gnss for fd in fds if len(fd.gnss)], ignore_index=True) if any(len(fd.gnss) for fd in fds) else None
    en = pd.concat([fd.ends for fd in fds if len(fd.ends)], ignore_index=True) if any(len(fd.ends) for fd in fds) else None
    if gn is not None:
        gn = gn.sort_values("t_ms", kind="stable").drop_duplicates("t_ms").reset_index(drop=True)
    if en is not None:
        en = en.sort_values("t_ms", kind="stable").drop_duplicates("t_ms").reset_index(drop=True)
    cws = {}
    for fd in fds:
        for cid, (t, s) in fd.cws.items():
            cws.setdefault(cid, [[], []])
            cws[cid][0].append(t)
            cws[cid][1].append(s)
    cw = {}
    for cid, (tt, ss) in cws.items():
        w = max(s.shape[1] for s in ss)
        ss = [np.pad(s, ((0, 0), (0, w - s.shape[1]))) for s in ss]
        t = np.concatenate(tt)
        s = np.concatenate(ss)
        o = np.argsort(t, kind="stable")
        cw[cid] = (t[o], s[o])
    return samples, gn, en, cw


def _step_at(t_src, v_src, t):
    """Value of a step function (last sample at or before t); NaN before the first sample."""
    i = np.searchsorted(t_src, t, side="right") - 1
    out = np.full(len(t), np.nan)
    ok = i >= 0
    out[ok] = v_src[i[ok]]
    return out


def _nearest(t_src, v_src, t, tol):
    if len(t_src) == 0:
        return np.full(len(t), np.nan)
    i = np.clip(np.searchsorted(t_src, t), 1, len(t_src) - 1) if len(t_src) > 1 else np.zeros(len(t), int)
    j = i - 1 if len(t_src) > 1 else i
    pick = np.where(np.abs(t_src[j] - t) <= np.abs(t_src[i] - t), j, i)
    out = v_src[pick].astype(float)
    out[np.abs(t_src[pick] - t) > tol] = np.nan
    return out


def _interval_mean(t_src, v_src, t_end, dur_ms):
    """Mean of the samples in (t_end - dur, t_end] (NaN when none)."""
    cs = np.r_[0.0, np.cumsum(v_src)]
    i1 = np.searchsorted(t_src, t_end, side="right")
    i0 = np.searchsorted(t_src, t_end - dur_ms, side="right")
    n = i1 - i0
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (cs[i1] - cs[i0]) / np.maximum(n, 1), np.nan)


def _gap_ms(t_src, t):
    """Distance (ms) to the nearest source sample; infinite outside the source's time span (no extrapolation)."""
    i = np.clip(np.searchsorted(t_src, t), 0, len(t_src) - 1)
    j = np.clip(i - 1, 0, len(t_src) - 1)
    gap = np.minimum(np.abs(t_src[i] - t), np.abs(t_src[j] - t)).astype(float)
    gap[(t < t_src[0]) | (t > t_src[-1])] = np.inf
    return gap


def _radii(lat0):
    """WGS 84 meridional (M) and prime-vertical (N) radii of curvature at lat0 (m)."""
    a, e2 = 6378137.0, 6.69437999014e-3
    s2 = np.sin(np.radians(lat0)) ** 2
    w = np.sqrt(1.0 - e2 * s2)
    return a * (1.0 - e2) / w ** 3, a / w


def _local_xy(lat, lon, lat0, lon0):
    """East / north metres from (lat0, lon0) on the WGS 84 ellipsoid's local tangent plane (field scale: < 1 mm per
    km of error from the curvature, unlike a mean-radius sphere which is 0.2-0.3 % short at 52 deg N)."""
    M, N = _radii(lat0)
    return (np.radians(np.asarray(lon) - lon0) * N * np.cos(np.radians(lat0)), np.radians(np.asarray(lat) - lat0) * M)


def _local_ll(x, y, lat0, lon0):
    """Inverse of _local_xy."""
    M, N = _radii(lat0)
    return lat0 + np.degrees(np.asarray(y) / M), lon0 + np.degrees(np.asarray(x) / (N * np.cos(np.radians(lat0))))


def _readings(fds, meta: FileMeta):
    """One row per DDI 510 sample with every attribute and the reason it is not exported ('' = exported).
    Returns (DataFrame, info dict)."""
    samples, gn, en, cw = _concat_files(fds)
    info = {"warnings": []}
    if (DDI_FLOW, "mg1sec-1") not in samples:
        raise JdlError(f"{meta.vin}: no mass-flow channel (DDI 510) in the logs - not a harvest log?")
    if en is None or not len(en):
        raise JdlError(f"{meta.vin}: no header end-point records (type 2) in the logs")
    t, flow = samples[(DDI_FLOW, "mg1sec-1")]
    n0 = len(t)
    d = pd.DataFrame({"t_ms": t, "flow_mgs": flow})
    dt = np.r_[np.nan, np.diff(t) / 1000.0]
    nominal = float(np.nanmedian(dt)) if n0 > 1 else 1.0
    bad_dt = ~((dt > 0) & (dt <= DT_MAX_S))
    info["nominal_duration_s"] = nominal
    info["n_nominal_duration"] = int(bad_dt.sum())
    d["dur_s"] = np.where(bad_dt, nominal, dt)
    tp = t + POS_LAG_MS                                   # position / geometry time of the reading
    t0p = tp - np.round(d.dur_s.values * 1000.0).astype(np.int64)
    # ---- yield-side channels at the flow time stamp
    info["moisture_channel"] = (DDI_MOIST, "ppm") in samples
    if info["moisture_channel"]:
        tm, vm = samples[(DDI_MOIST, "ppm")]
        mo = _nearest(tm, vm, t, MOIST_TOL_MS)
        held = np.zeros(n0, bool)
        if np.isnan(mo).any() and len(tm):
            k = np.searchsorted(tm, t, side="right") - 1        # last sample at or before t
            held = np.isnan(mo) & (k >= 0)
            held[held] &= (t[held] - tm[k[held]]) <= MOIST_HOLD_MS
            mo[held] = vm[k[held]].astype(float)
        d["moist"] = mo / 1e4
        d["moist_held"] = held
    else:
        d["moist"] = np.nan
        d["moist_held"] = False
        info["warnings"].append(f"{meta.vin}: no moisture channel (DDI 6) - Moisture__ and the dry columns are NaN")
    for ddi, col in ((DDI_YWET, "y39"), (DDI_YDRY, "y43")):
        if (ddi, "bu1ac-1") in samples:
            ty, vy = samples[(ddi, "bu1ac-1")]
            d[col] = _nearest(ty, vy, t, 600)
        else:
            d[col] = np.nan
    # ---- geometry-side channels at the position time
    if (DDI_SPEED, "km1hr-1") in samples:                 # wheel / radar speed: diagnostic only
        tv, vv = samples[(DDI_SPEED, "km1hr-1")]
        d["speed560_kmh"] = _interval_mean(tv, vv, tp, d.dur_s.values * 1000.0)
    else:
        d["speed560_kmh"] = np.nan
    if (DDI_WIDTH, "m") in samples:
        tw, vw = samples[(DDI_WIDTH, "m")]
        d["width_m"] = _step_at(tw, vw, tp + WIDTH_LAG_MS)
    else:
        d["width_m"] = np.nan
    secs = meta.sections
    lay = ["width_m", "y_m", "grp", "cws_idx"]
    if secs is not None and any(fd.meta.sections is None or len(fd.meta.sections) != len(secs) or
                                not np.allclose(fd.meta.sections[lay].values.astype(float), secs[lay].values.astype(float))
                                for fd in fds):
        info["warnings"].append(f"{meta.vin}: the section layout differs between log files - the first file's layout "
                                "is used for the active-width offset")
    d["n_act"] = -1
    d["y_act_m"] = np.nan
    if secs is not None and len(secs) and cw:
        on = np.zeros((n0, len(secs)), bool)
        have = np.zeros(len(secs), bool)
        for col, (cid, ix) in enumerate(zip(secs.grp.values, secs.cws_idx.values)):
            if cid not in cw:
                continue
            ct, cs = cw[cid]
            if ix >= cs.shape[1]:
                continue
            i = np.searchsorted(ct, tp, side="right") - 1
            ok = i >= 0
            on[ok, col] = cs[i[ok], ix] == 1
            have[col] = True
        if have.all():
            w = secs.width_m.values
            ws = on @ w
            d["n_act"] = on.sum(1)
            d["sec_width_m"] = ws
            with np.errstate(invalid="ignore", divide="ignore"):
                d["y_act_m"] = np.where(ws > 0, (on @ (w * secs.y_m.values)) / ws, np.nan)
        else:
            info["warnings"].append(f"{meta.vin}: section states incomplete ({int(have.sum())}/{len(secs)} sections) - "
                                    "readings placed at the full-header centre")
    else:
        info["warnings"].append(f"{meta.vin}: no section-control states in the log - readings placed at the "
                                "full-header centre")
    # DDI 12001 is the ACTIVE cutting width: a sample wider than the header (the sum of its sections, else the
    # defined width) cannot be one (Trial 23, X9 1100 with a 13.716 m header: 64.256 m, held by the step lookup over
    # every later reading - the area 4.7 x too large, the yield 4.7 x too low, F8 removing 93 % of its points)
    hw = float(secs.width_m.sum()) if secs is not None and len(secs) else meta.width_m
    wide = d.width_m.values > hw * (1 + WIDTH_TOL) if np.isfinite(hw) and hw > 0 else np.zeros(n0, bool)
    if wide.any():
        txt = (f"{meta.vin}: the working-width channel (DDI 12001) reads up to {np.nanmax(d.width_m.values):.3f} m on "
               f"{int(wide.sum()):,} flow samples, wider than the header ({hw:.3f} m): not the active width")
        if "sec_width_m" in d:
            d["width_m"] = d.sec_width_m
            info["warnings"].append(txt + " - width = sum of active sections")
        else:
            d.loc[wide, "width_m"] = hw
            info["warnings"].append(txt + " - those samples take the header width (no section states to use)")
    if np.isnan(d.width_m.values).all():
        if "sec_width_m" in d:
            d["width_m"] = d.sec_width_m
            info["warnings"].append(f"{meta.vin}: no working-width channel (DDI 12001) - width = sum of active sections")
        else:
            raise JdlError(f"{meta.vin}: neither a working-width channel (DDI 12001) nor section states")
    # ---- header end points (type 2): garbage fixes far from the machine's median position are removed first
    lat0, lon0 = float(np.median(en.lat1)), float(np.median(en.lon1))
    far = np.hypot(*_local_xy(en.lat1.values, en.lon1.values, lat0, lon0)) > OUTLIER_KM * 1000
    far |= np.hypot(*_local_xy(en.lat2.values, en.lon2.values, lat0, lon0)) > OUTLIER_KM * 1000
    info["end_samples_outlier"] = int(far.sum())
    en = en[~far].reset_index(drop=True)
    et = en.t_ms.values
    ex1, ey1 = _local_xy(en.lat1.values, en.lon1.values, lat0, lon0)
    ex2, ey2 = _local_xy(en.lat2.values, en.lon2.values, lat0, lon0)
    emx, emy = (ex1 + ex2) / 2, (ey1 + ey2) / 2           # full-width header centre, 5 Hz

    def at(tq, a):
        return np.interp(tq.astype(float), et.astype(float), a)
    x1, y1, x2, y2 = at(tp, ex1), at(tp, ey1), at(tp, ex2), at(tp, ey2)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    d["pos_gap_ms"] = np.maximum(_gap_ms(et, tp), _gap_ms(et, t0p))
    # distance = path of the header centre during the reading interval (chord of the 5 Hz track)
    vx, vy = mx - at(t0p, emx), my - at(t0p, emy)
    dist = np.hypot(vx, vy)
    d["dist_m"] = dist
    d["speed_kmh"] = dist / d.dur_s.values * 3.6
    bar = np.hypot(x2 - x1, y2 - y1)
    info["bar_length_m_median"] = float(np.nanmedian(bar))
    # travel direction: perpendicular to the bar; which perpendicular points forward is fixed per machine from the track
    px, py = -(y2 - y1), (x2 - x1)                         # end1 -> end2 rotated +90 deg (counter-clockwise)
    mov = (dist > 0.5) & (d.pos_gap_ms.values <= POS_MAX_GAP_MS)
    dot = (px * vx + py * vy)[mov]
    sgn = 1.0 if np.nansum(np.sign(dot)) >= 0 else -1.0
    info["end1_side"] = "left" if sgn > 0 else "right"
    info["forward_agreement"] = float(np.mean(np.sign(dot) == sgn)) if len(dot) else float("nan")
    d["heading"] = (np.degrees(np.arctan2(sgn * px, sgn * py)) + 360.0) % 360.0
    # centre of the ACTIVE sections: ISO 11783 y is positive to the RIGHT of travel (sign verified on Ops Center
    # Y_Offset_f); the unit vector towards the right end is end1 -> end2 when end1 is the left end
    with np.errstate(invalid="ignore", divide="ignore"):
        rx, ry = sgn * (x2 - x1) / bar, sgn * (y2 - y1) / bar
    yy = np.where(np.isfinite(d.y_act_m.values), d.y_act_m.values, 0.0)
    d["lat"], d["lon"] = _local_ll(mx + rx * yy, my + ry * yy, lat0, lon0)
    d["y_off_m"] = yy
    # elevation: GNSS antenna altitude (type 1) at the position time
    if gn is not None and len(gn):
        gfar = np.hypot(*_local_xy(gn.lat.values, gn.lon.values, lat0, lon0)) > OUTLIER_KM * 1000
        info["gnss_samples_outlier"] = int(gfar.sum())
        g2 = gn[~gfar]
        alt = np.interp(tp.astype(float), g2.t_ms.values.astype(float), g2.alt_m.values)
        alt[_gap_ms(g2.t_ms.values, tp) > POS_MAX_GAP_MS] = np.nan
        d["alt_m"] = alt
    else:
        d["alt_m"] = np.nan
        info["warnings"].append(f"{meta.vin}: no GNSS records (type 1) - Elevation_ is NaN")
    with np.errstate(invalid="ignore", divide="ignore"):
        r560 = d.speed_kmh / d.speed560_kmh
    okv = (d.speed560_kmh > 2) & np.isfinite(r560)
    info["track_over_wheel_speed_median"] = float(np.median(r560[okv])) if okv.any() else None
    # ---- what the vendor software exports (exclusive reasons, in this order)
    reason = np.full(n0, "", object)
    act = d.width_m.values > 0
    if "sec_width_m" in d:
        info["n_width_on_sections_off"] = int((act & (d.n_act.values == 0)).sum())
    reason[~act] = "header_up"
    reason[(reason == "") & (d.pos_gap_ms.values > POS_MAX_GAP_MS)] = "no_position"
    reason[(reason == "") & ~(d.speed_kmh.values >= V_MIN_KMH)] = "stationary"
    d["reason"] = reason
    return d, info


# ================================================================================================ decode
PRE_STEP_REASONS = ["header_up", "no_position", "stationary", "position_outlier", "no_moisture"]
DIAG_COLUMNS = ["t_ms", "Y_Offset_f", "Yld_Mon_W", "Spd560_mph", "n_act"]


def decode_detailed(root: str, unit_ids=None, opts: C.DecodeOptions | None = None, log=print):
    """decode() plus diagnostic columns (DIAG_COLUMNS: flow time stamp in ms UTC, lateral offset of the active-width
    centre (ft, + = right), the monitor's own wet yield DDI 39 (bu/ac), wheel speed DDI 560 (mph), active sections)."""
    t_start = _time.time()
    opts = opts or default_options()
    metas, warns = _scan(root)
    if not metas:
        raise JdlError(f"no John Deere .jdl logs under {root}")
    groups = {}
    for m in metas:
        groups.setdefault(_unit_key(m), []).append(m)
    missing = [u for u in (unit_ids or []) if u not in groups]
    if missing:
        raise JdlError(f"unknown unit id(s): {missing}")
    sel = sorted(groups) if not unit_ids else list(unit_ids)
    report = {k: None for k in C.DECODE_REPORT_KEYS}
    report.update(format=FORMAT_ID, label=LABEL, units=list(sel), warnings=list(warns))
    pre_total = {k: 0 for k in PRE_STEP_REASONS}
    frames, details, n_read, skipped = [], [], 0, []
    resolved = None
    override = False
    for uid in sel:
        ms = sorted(groups[uid], key=lambda x: x.ref_ms)
        m0 = ms[0]
        log(f"decoding {m0.model} {m0.vin} | {m0.field} | {m0.crop}: {len(ms)} file(s)")
        fds = []
        for m in ms:
            fd = decode_file(m.path, m)
            report["warnings"].extend(fd.warnings)
            fds.append(fd)
        if not any((DDI_FLOW, "mg1sec-1") in fd.samples for fd in fds):
            # a tractor with the grain cart in the same field (Trial 23: a 9460R among the two combines, selected by
            # the field of interest): no grain flow, so the unit is left out and the combines are decoded
            skipped.append(m0.vin)
            report["warnings"].append(f"{m0.vin} ({m0.model}): no mass-flow channel (DDI 510) in its {len(ms)} log(s) - "
                                      "not a combine (a tractor with the grain cart?); this unit was left out")
            continue
        n_inc = sum(fd.n_incomplete for fd in fds)
        if n_inc:
            report["warnings"].append(f"{m0.vin}: {n_inc} malformed position record(s) (time deltas without value "
                                      "deltas) skipped")
        d, info = _readings(fds, m0)
        report["warnings"].extend(info.pop("warnings"))
        n_read += len(d)
        # crop / test weight / standard moisture: option > monitor > crop table
        tw_s = [fd.samples[(DDI_TW, "lb1bu-1")][1] for fd in fds if (DDI_TW, "lb1bu-1") in fd.samples]
        mon_tw = (float(np.median(np.concatenate(tw_s))) if tw_s else
                  (m0.tw_kg_bu * C.LB_PER_KG if m0.tw_kg_bu else None))
        ck = _crop_key(m0.crop)
        # a crop chosen in the options that differs from the monitor's: the monitor's test weight and standard
        # moisture belong to the monitor's crop and are not used (as jd_gs3_rcd)
        override = bool(opts.crop) and ck is not None and opts.crop.strip().lower() != ck
        if override:
            report["warnings"].append(f"{m0.vin}: monitor crop {m0.crop!r} replaced by {opts.crop!r}; the monitor's "
                                      f"test weight ({mon_tw}) and standard moisture ({m0.std_moisture}) are not used")
            mon_tw = None
            sm_src = "option" if opts.std_moisture_pct is not None else "common.CROPS table (crop chosen by the user)"
            crop, tw, sm = opts.resolve(None, None, None)
        else:
            sm_src = ("option" if opts.std_moisture_pct is not None else
                      "Ops Center standard for this crop (OPS_CENTER_STD_MOISTURE)" if ck in OPS_CENTER_STD_MOISTURE
                      else "monitor crop record" if m0.std_moisture is not None else "common.CROPS table")
            crop, tw, sm = opts.resolve(ck, mon_tw, OPS_CENTER_STD_MOISTURE.get(ck, m0.std_moisture))
        if not override and m0.std_moisture is not None and abs(sm - m0.std_moisture) > 1e-6:
            msg = (f"standard moisture {sm:g} % ({sm_src}) differs from the monitor's crop record "
                   f"({m0.std_moisture:g} %); set DecodeOptions.std_moisture_pct to override")
            if msg not in report["warnings"]:
                report["warnings"].append(msg)
        if resolved and (abs(resolved[1] - tw) > 1e-6 or abs(resolved[2] - sm) > 1e-6):
            report["warnings"].append(f"{m0.vin}: test weight / standard moisture differ between units "
                                      f"({resolved[1]:.2f}/{resolved[2]:.2f} vs {tw:.2f}/{sm:.2f})")
        resolved = (crop, tw, sm)
        # garbage positions far from the machine's track, after the vendor filters
        keep = d.reason.values == ""
        if keep.any():
            x, y = _local_xy(d.lat.values, d.lon.values, float(np.median(d.lat[keep])), float(np.median(d.lon[keep])))
            d.loc[keep & (np.hypot(x, y) > OUTLIER_KM * 1000), "reason"] = "position_outlier"
        if info.get("moisture_channel"):
            d.loc[(d.reason.values == "") & d.moist.isna().values, "reason"] = "no_moisture"
        n_h = int(((d.reason.values == "") & d.moist_held.values).sum()) if "moist_held" in d else 0
        if n_h:
            report["warnings"].append(f"{m0.vin}: {n_h} flow sample(s) in a gap of the moisture channel carry the "
                                      f"last moisture sample (held up to {MOIST_HOLD_MS / 1000:g} s, as Ops Center)")
        pre = {k: int((d.reason.values == k).sum()) for k in PRE_STEP_REASONS}
        for k in pre:
            pre_total[k] += pre[k]
        r = d[d.reason.values == ""].reset_index(drop=True)
        tz = opts.tz_offset_h
        ts = pd.to_datetime(r.t_ms.values, unit="ms")
        start = pd.Timestamp(int(r.t_ms.min()) if len(r) else m0.ref_ms, unit="ms")
        if tz is not None:
            ts = ts + pd.to_timedelta(tz, unit="h")
            start = start + pd.Timedelta(hours=tz)
        area_ac = r.width_m.values * r.dist_m.values / 4046.8564224
        wet_lb = r.flow_mgs.values / 1e6 * C.LB_PER_KG * r.dur_s.values
        yc = C.yield_columns(wet_lb, area_ac, r.moist.values, tw, sm, opts.shrink)
        out = pd.DataFrame({
            "Field": m0.field, "Dataset": C.dataset_name(f"{m0.field} {m0.vin[-6:]}".strip(), start),
            "Product": crop if override else (m0.variety or m0.crop), "Obj__Id": np.arange(1, len(r) + 1),
            "Time": ts.strftime("%Y-%m-%d %H:%M:%S.") + ((r.t_ms.values % 1000) // 100).astype(str),
            "Duration_s": r.dur_s.values, "Elevation_": r.alt_m.values * C.FT_PER_M,
            "Speed_mph_": r.speed_kmh.values / 3.6 * C.MPH_PER_MS, "Distance_f": r.dist_m.values * C.FT_PER_M,
            "Track_deg_": r.heading.values, "Swth_Wdth_": r.width_m.values * C.FT_PER_M, "Moisture__": r.moist.values,
            **yc, "Machine": m0.vin, "Src_Fmt": FORMAT_ID, "lon": r.lon.values, "lat": r.lat.values,
            "t_ms": r.t_ms.values, "Y_Offset_f": r.y_off_m.values * C.FT_PER_M, "Yld_Mon_W": r.y39.values,
            "Spd560_mph": r.speed560_kmh.values / 3.6 * C.MPH_PER_MS, "n_act": r.n_act.values})
        frames.append(out)
        # calibration evidence: our wet yield vs the monitor's own wet yield (DDI 39) on full-width readings
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = out.Yld_Vol_We.values / r.y39.values
        okr = np.isfinite(ratio) & (r.y39.values > 10) & (r.speed_kmh.values > 2)
        if okr.sum() >= 30 and abs(float(np.median(ratio[okr])) - 1) > MONITOR_RATIO_TOL:
            report["warnings"].append(
                f"{m0.vin}: the decoded wet yield is {100 * float(np.median(ratio[okr])):.0f} % of the monitor's own wet "
                f"yield (DDI 39, median over {int(okr.sum()):,} readings; validated combines read 99.9 %): the area "
                "(width or distance) or the mass flow was read wrong - check this decode before cleaning it")
        details.append(dict(
            machine=m0.vin, model=m0.model, client=m0.client, farm=m0.farm, field=m0.field, crop=m0.crop,
            variety=m0.variety, display=m0.display, software=m0.software, files=len(ms), n_flow_samples=int(len(d)),
            n_readings=int(len(out)), pre_step=pre, n_absolute_records=int(sum(fd.n_absolute for fd in fds)),
            wet_lb_all_flow_samples=float((d.flow_mgs.values / 1e6 * C.LB_PER_KG * d.dur_s.values).sum()),
            ratio_to_monitor_wet_yield_median=float(np.median(ratio[okr])) if okr.any() else None,
            ratio_to_monitor_wet_yield_p05_p95=([float(np.percentile(ratio[okr], 5)),
                                                 float(np.percentile(ratio[okr], 95))] if okr.any() else None),
            **info))
    if skipped and not frames:
        raise JdlError(f"{', '.join(skipped)}: no mass-flow channel (DDI 510) in the logs - not a harvest log? Select the "
                       "combines' units")
    df = (pd.concat(frames, ignore_index=True) if frames
          else pd.DataFrame(columns=C.STANDARD_NAMES + ["lon", "lat"] + DIAG_COLUMNS))
    crop, tw, sm = resolved if resolved else (None, None, None)
    rows, tot = C.summarize(df) if len(df) else ([], {})
    report.update(n_records_read=int(n_read), n_readings=int(len(df)), pre_step=pre_total, machines=rows, totals=tot,
                  time_basis="UTC" if opts.tz_offset_h is None else "local")
    report["calibration"] = {
        "channel": "DDI 510 mass flow (mg/s, the display's calibrated wet grain flow) x reading duration = wet mass",
        "area": "DDI 12001 active width x path length of the header centre (5 Hz header end points) during the reading",
        "crop": crop, "test_weight_lb_bu": tw, "std_moisture_pct": sm, "shrink": opts.shrink,
        "test_weight_source": "option" if opts.test_weight_lb_bu else (
            "common.CROPS table (crop chosen by the user)" if resolved and override else "monitor DDI 8 / crop record"),
        "std_moisture_source": sm_src if resolved else None,
        "monitor_std_moisture_pct": metas[0].std_moisture,
        "monitor_crop": metas[0].crop,
        "check_monitor_yield": "details[].ratio_to_monitor_wet_yield_median = decoded wet yield / monitor DDI 39",
        "validation": VALIDATION_NOTE}
    report["details"] = details
    report["decode_seconds"] = round(_time.time() - t_start, 1)
    log(f"decoded {len(df):,} readings from {n_read:,} flow samples in {report['decode_seconds']} s")
    return df, report


def decode(root: str, unit_ids=None, opts: C.DecodeOptions | None = None, log=print):
    """Decode the selected units (None = all) -> (DataFrame in the standard schema + lon/lat, decode report).
    opts=None uses default_options() (John Deere one-sided shrink)."""
    df, report = decode_detailed(root, unit_ids, opts, log)
    return df[C.STANDARD_NAMES + ["lon", "lat"]].copy(), report
