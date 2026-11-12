# -*- coding: utf-8 -*-
"""Write the CLEAN harvest back as a John Deere GreenStar 3 (2630) card, the format it was decoded from
(engine/formats/jd_gs3_rcd.py), so that a reader of raw monitor data reads the clean readings with the monitor's own
attributes and units. NOT YET TESTED IN AG LEADER SMS: everything below is proven with OCED's own decoder only.

    from engine.formats import jd_gs3_rcd_write as W
    ok, why = W.can_write(source)
    R = W.write_clean(source, clean_shp, out_dir, widths=True, factors=None, new_ids=True, removed_as_harvest="buffer")
    R["path"], R["zip"], R["n_kept"], R["n_removed"], R["files_changed"], R["notes"], R["warnings"], R["check"]
    R["n_removed_harvest"], R["min_yield_needed"]     # removed readings left with 0 kg; the minimum to read it with

Interface shared by every native writer (engine/formats/native_write.py dispatches to it): FORMAT_ID, LABEL,
can_write(source) -> (bool, reason), write_clean(...) -> dict; a plain-message WriteError (a ValueError) when the input
cannot be written: EmptyCleanError (no reading in the clean file), NotThisSourceError (the clean file or the source is
not a decode of this card), InputGoneError (the decoded card is no longer on disk), OutputError (the output would lie
in, contain or replace the input, or replace a folder that is not a written card).

What is written, for every card the decoded readings came from (the folder above GS3_2630 / RCD), and nothing else:
  * the sessions (.fdl + .fdd) that hold at least one log block of the decoded units, the copy the decoder read;
  * the load files (.fdr) those .fdl files cite, and the card's version file(s) (global.ver).
Sessions of other fields, crops, years or operations, the duplicate copies of a session, zip archives and any other
file are left out (counted in the notes): a reader of the written card cannot import them a second time under new
ids. A log block of another unit inside a written session is kept (the .fdl offsets stay right) but neutralised: every
record not harvesting and 0 kg of grain (warning). The files are written byte for byte except:
  Level 1 (always) - only the readings the clean file keeps are harvest readings that hold grain, each the grain it
    decodes to.
    * Nothing is deleted and every record keeps its size. A record is at once a position (its reading) and a grain /
      moisture record that belongs to the position logged FLOW_DELAY_S / MOISTURE_DELAY_S (14 s / 18 s) earlier;
      deleting one would move grain and moisture onto other readings and change the duration of the next one.
    * A harvest record (header down, at least one section recording) that is not a kept reading is either left a
      harvest reading as the monitor logged it, its grain record set to 0 kg (Grain, below), or set to "not
      harvesting": its header status and the recording status of every section become Off (enumerations stored as
      absolute int16 indices, so 1 + n_sections values change in place). removed_as_harvest chooses which are left:
        "buffer" (default) those next to a kept reading (the record just before or just after it in the same log
                 block, no pause of the log between: run_neighbours); the others are switched off;
        "full"   all of them: the harvest state of every record as the monitor logged it;
        "none"   none: every one switched off.
      Switching off a record next to a kept reading makes that reading the first or last of a harvesting run on the
      written card where the raw card had none, and Ag Leader SMS leaves out some readings at the edge of a run (seen
      in SMS on a card written with every one switched off: the readings it left out sat at such new edges, and at
      the raw card's own edges it leaves out the same readings on both cards); "buffer" and "full" make no such edge
      (n_new_run_edges 0), "buffer" with the fewest records left. The records left read 0 kg (0 bu/ac; no yield
      where they cover no area), so THE CARD MUST BE READ WITH A MINIMUM YIELD ABOVE 0: the import's minimum (SMS's
      Processing Settings for these cards, 5 bu/ac; OCED's import minimum, the same) leaves them out, as it leaves
      out the raw card's readings without grain; read with a minimum of 0 they become points of 0 yield (the result
      says so: min_yield_needed, n_removed_harvest, n_not_offered_harvest and a note). Two kinds, counted apart: the
      decoded readings the clean file left out (the import's minimum / maximum, clip, swath, 3-sigma; n_removed), and
      the harvest records the decoder never offered as a reading (no valid position; with the fixed-shift alignment
      also standing, or without a grain / moisture record 14 / 18 s later; n_not_offered).
    * Grain: the written card holds grain ONLY in the grain records of the kept readings. Each kept reading's own
      grain record (the record it takes by the decoder's alignment: jd_gs3_rcd.sms_align, or the fixed shift) gets the
      grain the decoder gives that reading on the original card - with sms_align that includes the grain carried to
      it from records no reading took - times the level-3 factor, rounded to the channel's resolution (1 g); every
      other grain record of the decoded units becomes 0 kg (each change written as two int16 deltas, the record's own
      and the next record's, so every other value stays exact). A reader that matches records to positions as the
      decoder does therefore reads each kept reading with the clean file's grain whatever rule it uses to carry grain
      no reading took (none is left to carry), and no grain of a removed reading, a removed session or a clipped area
      can move into a kept reading. A kept reading that took no grain record of its own (the log paused within
      FLOW_DELAY_S after it) and held only carried grain reads 0 kg on the written card: count, kg and the largest
      value are a warning (such readings are rare and hold little grain; a 5 bu/ac minimum yield then drops them).
  Level 2 (widths=True) - the clean swath width and distance of each kept reading.
    * The width of a reading is the sum of the widths of its recording sections (the .fdl fixes the section widths
      per log block), so a narrower width is written by switching sections off: the contiguous run of recording
      sections whose total width is nearest the clean width (ties: the wider) and, among those, whose centre is
      nearest to the side the clean point moved to. The written width is therefore the clean width ROUNDED TO WHOLE
      SECTIONS; the yield follows (mass / (distance x written width)), and the decoder puts such a reading at the
      centre of its recording sections.
    * A changed distance is written in the implement point's DeltaDistance channel (1 cm resolution, the next
      record's delta corrected); speed = distance / duration follows.
  Level 3 (factors={machine: f}) - the grain of every kept reading of that machine multiplied by f (the meter's
    calibration number in the .fdl is left as the monitor wrote it).
  new_ids (default True) - every written .fdd / .fdl / .fdr whose name is a GreenStar id gets a new id: group 3 of the
    GUID, '1000' -> '1xyz' (same length, version digit kept; random unless id_tag is given), in the file names and in
    every .fdl / .fdr that cites them, so that a reader that archives cards by file name (SMS refuses a file it has
    archived) takes the card as new. Group 1 (the session start in hex UTC seconds, read by jd_gs3_rcd.guid_time) is
    kept and the decoder accepts any '1xxx' in group 3, so a written card probes with its date span.

Key from a clean row back to its record: (Machine, Time), Time being the decoder's own text (UTC, or local by the
decode's tz_offset_h; 0.1 s). Positions are not a key (Optimize Swath Widths moves points sideways). Duplicate clean
rows count once (warning). No column is added to the decoded output.

What else on a card describes the records: the .fdl gives each log block its
byte offset in the .fdd (EvenByteDelta filePosition) and the .fdd name (filePathName); the .fdd block header holds the
column list with resolution / limit / initial value, and the GUIDs of the data format, session, task and field; a .fdr
holds a load's number and name; global.ver a version. No record count, total, area or mass counter, checksum or CRC
was found in any of them. The writer keeps the size of every record (every filePosition stays right), keeps the
column lists, and renames consistently. A header / section value not held as a dense value, or a grain change a dense
delta cannot hold, makes the writer refuse the card (or, for grain, leave that record as logged, with a warning)
rather than change record sizes.

check (default True): the written card is decoded again with the source's decoder options and compared with the clean
file (R["check"]: decoded back, extra, missing, largest differences, the totals a reader should show).

Validation with OCED's decoder (sms_align) on GreenStar 3 cards of several combines, each with every decoded reading
kept, a random half, a clip and the 3-sigma clean with the field boundary: every kept reading decodes back with
identical position, time, duration, distance, width (widths=False) and moisture and its grain within 0.5 g, apart
from the readings without a grain record of their own above; no removed reading decodes back at or above the minimum
yield (those left as harvest readings decode with 0 kg, below it); the written card leaves 0 kg for a reader to
carry. Compensating at the kept readings instead (the earlier version) left grain to carry and
could move it into a kept reading.
An empty clean file is refused. Pure engine code: no Streamlit, no app imports.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import secrets
import shutil
import struct
import time
import zipfile

import numpy as np
import pandas as pd

from engine.formats import common as C
from engine.formats import jd_gs3_rcd as G

FORMAT_ID = G.FORMAT_ID
LABEL = "John Deere GreenStar 3 (2630) card"

_DENSE_FMT = {1: "<h", 3: "<h", 4: "<i"}
_INT_MAX = {"<h": 32767, "<i": 2 ** 31 - 1}
_GUID_NAME = re.compile(r"^([0-9a-f]{8}-0000-)(1[0-9a-f]{3})(-[0-9a-f]{4}-[0-9a-f]{12})$")
_CARD_FILES = (".fdd", ".fdl", ".fdr")
_OUT_EXTS = (".fdd", ".fdl", ".fdr", ".ver")    # what a written card holds (a folder of only these may be replaced)
WIDTH_TOL_FT = 0.01        # a clean width this much below the logged one counts as narrowed
DIST_MIN_CM = 0.5          # a clean distance changed by less than this is left as logged
GRAIN_TOL_KG = 0.0005      # the check: a kept reading's grain counts as equal within half the channel's 1 g
# write_clean(removed_as_harvest=...): which harvest records that are not kept readings stay harvest readings with
# 0 kg of grain (the first is the default; Level 1 in the module docstring)
REMOVED_AS_HARVEST = ("buffer", "full", "none")


class WriteError(ValueError):
    """The clean file or the card cannot be written back in this format (plain message for the user)."""


class EmptyCleanError(WriteError):
    """The clean file holds no reading."""


class NotThisSourceError(WriteError):
    """The clean file, or the source, is not a decode of this card."""


class InputGoneError(WriteError):
    """The decoded card is no longer on disk."""


class OutputError(WriteError):
    """The output folder would lie in, contain or replace the input, or replace a folder that is not a written card."""


# ------------------------------------------------------------------------------------------------- record layout
class Layout:
    """Byte layout of the records of one log block (the grammar of jd_gs3_rcd.decode_block).

    columns    the block's column definitions (jd_gs3_rcd.read_columns); index: {name: column number}
    starts     byte offset of each record in the block
    states     (n, ncols) column state of each record (jd_gs3_rcd.ST_DELTA / ST_NONE / ST_HOLD / ST_TLV)
    dense_off  (n, ncols) byte offset in the block of the column's dense value, -1 where it has none
    end        byte offset just after the end marker
    """

    def __init__(self, blk: bytes):
        cols, p = G.read_columns(blk)
        nc = len(cols)
        nb = (nc + 7) // 8
        pre = 3 + 3 * nb
        cache: dict[bytes, int] = {}
        pat_st, pat_off, pat_size = [], [], []
        starts, pidx = [], []
        end = len(blk)
        ended = False
        while p + 2 <= end:
            typ = blk[p] | (blk[p + 1] << 8)
            if typ == G._END_TYPE:
                p += 2
                ended = True
                break
            if typ != G._REC_TYPE:
                raise WriteError(f"record marker expected at byte {p}, found {typ}")
            ng = blk[p + 2]
            key = bytes(blk[p + 3:p + pre])
            k = cache.get(key)
            if k is None:
                bm = [int.from_bytes(key[j * nb:(j + 1) * nb], "little") for j in range(3)]
                st = np.array([((bm[0] >> c) & 1) | (((bm[1] >> c) & 1) << 1) | (((bm[2] >> c) & 1) << 2)
                               for c in range(nc)], np.int8)
                off = np.full(nc, -1, np.int64)
                o = pre
                for c in range(nc):
                    if st[c] == G.ST_DELTA:
                        off[c] = o
                        o += struct.calcsize(_DENSE_FMT[cols[c]["type"]])
                k = cache[key] = len(pat_st)
                pat_st.append(st)
                pat_off.append(off)
                pat_size.append(o)
            starts.append(p)
            pidx.append(k)
            q = p + pat_size[k]
            for _ in range(ng):
                t, ln = struct.unpack_from("<HH", blk, q)
                if t != G._GROUP_TYPE:
                    raise WriteError(f"sparse group expected at byte {q}")
                mask = int.from_bytes(blk[q + 4:q + 4 + ln], "little")
                q += 4 + ln
                for c in range(nc):
                    if not (mask >> c) & 1:
                        q += 4 + struct.unpack_from("<HH", blk, q)[1]
            p = q
        if not ended:
            raise WriteError("log block without its end marker")
        self.columns = cols
        self.index = {c["name"]: i for i, c in enumerate(cols)}
        self.starts = np.asarray(starts, np.int64)
        pidx = np.asarray(pidx, np.int64)
        self.states = np.asarray(pat_st, np.int8)[pidx] if len(pidx) else np.zeros((0, nc), np.int8)
        rel = np.asarray(pat_off, np.int64)[pidx] if len(pidx) else np.zeros((0, nc), np.int64)
        self.dense_off = np.where(rel >= 0, rel + self.starts[:, None], -1)
        self.end = p
        self.n = len(starts)

    def enum_index(self, col: str, suffix: str) -> int:
        """Index of the first value of enumeration column ``col`` whose name ends in ``suffix`` ('On' / 'Off')."""
        names = self.columns[self.index[col]].get("enum") or []
        hits = [i for i, nm in enumerate(names) if nm.endswith(suffix)]
        if not hits:
            raise WriteError(f"column {col} has no value ending in {suffix!r} ({names})")
        return hits[0]

    def enum_value(self, buf, i: int, col: str):
        """The dense enumeration index of record i in column ``col`` (None when the record does not hold it dense)."""
        c = self.index[col]
        if self.states[i, c] != G.ST_DELTA:
            return None
        return struct.unpack_from("<h", buf, int(self.dense_off[i, c]))[0]


def set_enum(buf: bytearray, L: Layout, rows, col: str, value: int) -> int:
    """Write the enumeration index ``value`` into column ``col`` of the records ``rows`` (in place). Every record must
    hold the column as a dense value (true of every header / section column of the cards seen). Returns the number
    of values that changed."""
    c = L.index[col]
    rows = np.asarray(rows, np.int64)
    if not len(rows):
        return 0
    if np.any(L.states[rows, c] != G.ST_DELTA):
        raise WriteError(f"column {col}: a record holds it in a form this writer does not rewrite in place")
    n = 0
    for o in L.dense_off[rows, c].tolist():
        if struct.unpack_from("<h", buf, o)[0] != value:
            struct.pack_into("<h", buf, o, value)
            n += 1
    return n


def correct_numeric(buf: bytearray, L: Layout, col: str, e) -> np.ndarray:
    """Add e[i] x resolution to the value of column ``col`` in record i, in place, by rewriting dense deltas: record
    i's delta becomes delta + e[i] - e[i-1] (e[i-1] counts 0 after a record with no value, where the decoder restarts
    the chain from 0), so every record keeps its value unless its own e is not 0. Returns the indices of the records
    whose new delta cannot be written in place (the record holds no dense delta, or the new delta is outside the
    integer range or above the column's limit); nothing is written when that list is not empty."""
    c = L.index[col]
    cd = L.columns[c]
    fmt = _DENSE_FMT[cd["type"]]
    st = L.states[:, c]
    e = np.asarray(e, np.int64).copy()
    none = st == G.ST_NONE
    e[none] = 0
    e_prev = np.zeros_like(e)
    e_prev[1:] = np.where(none[:-1], 0, e[:-1])
    step = e - e_prev
    tlv = st == G.ST_TLV
    need = np.flatnonzero(~none & np.where(tlv, e != 0, step != 0))
    bad = need[st[need] != G.ST_DELTA].tolist()
    lim = float(cd.get("limit") or 0.0)
    res = float(cd.get("res") or 1.0)
    new = {}
    for i in need[st[need] == G.ST_DELTA].tolist():
        o = int(L.dense_off[i, c])
        d = struct.unpack_from(fmt, buf, o)[0] + int(step[i])
        if abs(d) > _INT_MAX[fmt] or (lim > 0 and abs(d) * res > lim * (1 + 1e-9)):
            bad.append(i)
        else:
            new[o] = d
    if bad:
        return np.asarray(sorted(set(bad)), np.int64)
    for o, d in new.items():
        struct.pack_into(fmt, buf, o, d)
    return np.zeros(0, np.int64)


# ------------------------------------------------------------------------------------------------- source
def _resolve_source(source) -> tuple[str, list | None, float | None, dict, dict]:
    """(input root, unit ids, tz offset h, decoder kwargs, decode report) of a decode, from engine.run.decode()['source']
    (input root and unit ids from its decode report JSON when the dict itself does not carry them)."""
    if not isinstance(source, dict):
        raise NotThisSourceError("source must be the dict engine.run.decode returns under 'source'")
    fmt = source.get("format")
    if fmt not in (None, FORMAT_ID):
        raise NotThisSourceError(f"this writer writes John Deere GreenStar 3 cards ({FORMAT_ID}), not {fmt!r}")
    if source.get("kind") not in (None, "decoded"):
        raise NotThisSourceError("only a raw card decoded by OCED can be written back as a card (this source is "
                                 f"{source.get('kind')!r})")
    rep = {}
    p = source.get("decode_report")
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            rep = json.load(fh)
    if rep.get("format") not in (None, FORMAT_ID):
        raise NotThisSourceError(f"the decode report is of {rep.get('format')!r}, not a GreenStar 3 card")
    root = source.get("input_root") or rep.get("input_root")
    if not root or not os.path.isdir(root):
        raise InputGoneError("the decoded card is not found (no input folder in the source or its decode report, or "
                             "the folder is gone): write the clean card from the work folder the data was decoded in")
    units = source.get("unit_ids") or rep.get("units")
    opts = source.get("options") or rep.get("options") or {}
    tz = source["tz_offset_h"] if "tz_offset_h" in source else opts.get("tz_offset_h")
    kw = dict(source.get("decoder_kwargs") or rep.get("decoder_kwargs") or {})
    return root, (list(units) if units else None), tz, kw, rep


def can_write(source) -> tuple[bool, str]:
    """(True, '') when ``source`` (engine.run.decode()['source']) is a GreenStar 3 card decode whose card is still on
    disk; else (False, the reason in plain words). Cheap: reads no log data."""
    if not isinstance(source, dict) or source.get("format") != FORMAT_ID:
        fmt = source.get("format") if isinstance(source, dict) else None
        return False, f"not a John Deere GreenStar 3 card decode (format {fmt!r})"
    try:
        root, _, _, _, _ = _resolve_source(source)
    except WriteError as e:
        return False, str(e)
    if not G.find_sessions(root):
        return False, "no GreenStar 3 session (.fdl + .fdd) in the input folder any more"
    return True, ""


def _card_root(path: str, root: str) -> str:
    """The folder a GreenStar card starts at: the parent of 'GS3_2630' when the path has one, else the parent of the
    folder above 'RCD' (<profile>/RCD/EIC/Documentation/<xx>/<guid>.fdl); never above the input root."""
    parts = os.path.normpath(path).split(os.sep)
    low = [x.lower() for x in parts]
    out = os.path.dirname(path)
    for name, up in (("gs3_2630", 0), ("rcd", 1)):
        if name in low:
            i = len(low) - 1 - low[::-1].index(name)
            out = os.sep.join(parts[:max(i - up, 1)])
            break
    root = os.path.normpath(root)
    try:
        if os.path.commonpath([out, root]) == os.path.normpath(out) and os.path.normpath(out) != root:
            return root                                  # the card starts above what was given: stop at the input
    except ValueError:
        pass
    return out


def _real(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _within(a: str, b: str) -> bool:
    """a is b or lies inside b (both _real paths)."""
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                                   # another drive
        return False


def _check_output(out_dir: str, name: str, root: str) -> str:
    """The card folder to write (out_dir/name). OutputError when it would be or lie in the input folder, contain it,
    when out_dir lies in the input folder, or when it exists and holds anything but card files. Returns its path."""
    if not name or name in (".", "..") or any(s in name for s in ("/", "\\", ":")):
        raise OutputError(f"the card folder name {name!r} is not a plain folder name")
    dest = os.path.join(out_dir, name)
    r, o, d = _real(root), _real(out_dir), _real(dest)
    if _within(o, r) or _within(d, r):
        raise OutputError("the output folder lies inside the input card folder: choose a folder outside it (the "
                          "written card must never sit in, or replace, the original)")
    if _within(r, d):
        raise OutputError("the output card folder would contain the input card folder: choose another folder")
    if os.path.isfile(dest):
        raise OutputError(f"{dest} exists and is a file: choose another folder")
    if os.path.isdir(dest):
        other = [f for _, _, fs in os.walk(dest) for f in fs if not f.lower().endswith(_OUT_EXTS)]
        if other:
            raise OutputError(f"{dest} exists and holds files that are not a written card ({other[:3]}): choose "
                              "another folder")
    return dest


# ------------------------------------------------------------------------------------------------- records
def _records(root: str, units, tz) -> tuple[list[dict], pd.DataFrame, list[dict]]:
    """Every record of the harvest blocks of the decoded units with the decoder's key (Machine, Time) and what the
    writer needs (grain, moisture, harvest state, width, distance, implement point). units None = the decoder's
    pre-selected units (jd_gs3_rcd.list_units, Unit.default), as jd_gs3_rcd.decode takes them."""
    allb = G._harvest_blocks(root)
    want = set(units) if units else {u.id for u in G.list_units(root) if u.default}
    blocks = [m for m in allb if G._unit_id(m) in want]
    if not blocks:
        raise NotThisSourceError("no harvest log block of the decoded units on the card")
    frames, cache = [], {}
    for bi, m in enumerate(blocks):
        if m["fdd"] not in cache:
            cache.clear()
            with open(m["fdd"], "rb") as fh:
                cache[m["fdd"]] = fh.read()
        d, _ = G.block_frame(m, cache[m["fdd"]][m["file_position"]:m["end_position"]])
        mach = m["machine_serial"] or m["machine"] or "unknown machine"
        start = m["start_utc"] if m["start_utc"] is not None else G.guid_time(m["fdd"])
        tloc = d.t_utc + pd.to_timedelta(tz or 0.0, unit="h")
        ivl = m.get("log_interval_ms", np.nan) / 1000.0
        # whole milliseconds since 1970 (ElapsedTime is in ms; independent of the datetime unit pandas picks)
        t_ms = int(round(start.timestamp() * 1000.0)) + np.round(np.nan_to_num(d.elapsed_s.to_numpy()) * 1000.0
                                                                 ).astype(np.int64)
        la, lo = d.lat_imp.to_numpy(), d.lon_imp.to_numpy()
        gnss = (np.isfinite(la) & np.isfinite(lo) & ~((np.abs(la) < 1e-6) & (np.abs(lo) < 1e-6))
                & (np.abs(la) <= 90) & (np.abs(lo) <= 180) & (d.signal.to_numpy() != "dtiSignalTypeUnknown"))
        frames.append(pd.DataFrame({
            "bi": bi, "k": np.arange(len(d)), "Machine": mach,
            "Time": tloc.dt.strftime("%Y-%m-%d %H:%M:%S.") + (tloc.dt.microsecond // 100000).astype(str),
            "t_s": t_ms / 1000.0, "t_ms": t_ms, "dt_s": d.dt_s.to_numpy(),
            "ivl_s": ivl if np.isfinite(ivl) and ivl > 0 else 1.0,
            "wet_kg": d.wet_kg.to_numpy(), "moisture_pct": d.moisture_pct.to_numpy(),
            "harvest": d.header_on.to_numpy() & (d.sections_on.to_numpy() > 0), "gnss_ok": gnss,
            "width_m": d.active_width_m.to_numpy(), "dd_m": d.dd_imp_m.to_numpy(),
            "lat": d.lat_imp.to_numpy(), "lon": d.lon_imp.to_numpy(), "head_deg": d.head_imp.to_numpy()}))
    R = pd.concat(frames, ignore_index=True)
    others = [m for m in allb if G._unit_id(m) not in want]
    return blocks, R, others


def _alignment(kw: dict | None) -> tuple[str, float, float]:
    """(method, flow delay s, moisture delay s) of the decode: decoder kwargs, else the decoder's defaults."""
    kw = kw or {}
    fd = float(kw.get("flow_delay_s") or G.FLOW_DELAY_S)
    md = float(kw.get("moisture_delay_s") or G.MOISTURE_DELAY_S)
    method = kw.get("alignment") or ("sms" if hasattr(G, "sms_align") else "shift")
    if method == "sms" and not hasattr(G, "sms_align"):
        method = "shift"
    return method, fd, md


def _by_machine(R: pd.DataFrame):
    """(machine, row indices in time order) for every machine of R."""
    mach = R.Machine.astype(str).to_numpy()
    tms = R.t_ms.to_numpy()
    for m in np.unique(mach):
        idx = np.flatnonzero(mach == m)
        yield m, idx[np.argsort(tms[idx], kind="stable")]


def taken_records(R: pd.DataFrame, kw: dict | None = None) -> tuple[np.ndarray, str]:
    """For every record of R as a position: the row of R whose grain the decoder in use gives it (-1: none).
    jd_gs3_rcd.sms_align when the decoder has it (row numbers as 'mass', pending 'drop': its output is the record
    each position took), else the decoder's fixed shift (jd_gs3_rcd._shift_in_time). kw: the decoder kwargs of the
    decode (flow_delay_s, moisture_delay_s, alignment). R needs Machine, t_s, t_ms, ivl_s, wet_kg, moisture_pct."""
    method, fd, md = _alignment(kw)
    out = np.full(len(R), -1, np.int64)
    rows = np.arange(len(R), dtype=float)
    if method == "sms":
        mass = R.wet_kg.to_numpy()
        tms = R.t_ms.to_numpy()
        for _, idx in _by_machine(R):
            tag = np.where(np.isfinite(mass[idx]), rows[idx] + 1.0, np.nan)
            a = G.sms_align(tms[idx], tag, R.moisture_pct.to_numpy()[idx], np.ones(len(idx), bool), fd, md,
                            float(np.median(R.ivl_s.to_numpy()[idx])), pending="drop")
            w = np.nan_to_num(a["wet_kg"], nan=0.0)
            out[idx] = np.where(w > 0, np.round(w).astype(np.int64) - 1, -1)
        return out, f"sms_align (one to one in time order, flow {fd:g} s, moisture {md:g} s)"
    v = G._shift_in_time(R.t_s.to_numpy(), R.Machine.astype(str).to_numpy(), rows, fd)
    ok = np.isfinite(v)
    out[ok] = v[ok].astype(np.int64)
    return out, f"fixed shift (the record logged {fd:g} s later, within 0.6 s)"


def decoded_mask(R: pd.DataFrame, take: np.ndarray, kw: dict | None = None) -> np.ndarray:
    """The records the decoder offers as readings (jd_gs3_rcd.decode's own steps): header down, a section recording,
    a valid position; with the fixed-shift alignment also moving (MIN_SPEED_MS) with a grain and a moisture record
    flow_delay / moisture_delay later."""
    method, fd, md = _alignment(kw)
    ok = R.harvest.to_numpy() & R.gnss_ok.to_numpy()
    if method == "sms":
        return ok
    ivl = R.ivl_s.to_numpy().astype(float)
    dur = R.dt_s.to_numpy().astype(float).copy()
    gap = ~np.isfinite(dur) | (dur < 0.5 * ivl) | (dur > 2.5 * ivl)
    dur[gap] = ivl[gap]
    with np.errstate(invalid="ignore", divide="ignore"):
        moving = R.dd_m.to_numpy() / dur >= G.MIN_SPEED_MS
    wet = R.wet_kg.to_numpy()
    has_mass = (take >= 0) & np.isfinite(wet[np.maximum(take, 0)])
    mo = G._shift_in_time(R.t_s.to_numpy(), R.Machine.astype(str).to_numpy(), R.moisture_pct.to_numpy(), md)
    return ok & moving & has_mass & np.isfinite(mo)


def decoded_grain(R: pd.DataFrame, take: np.ndarray, kw: dict | None = None) -> np.ndarray:
    """kg of wet grain the decoder gives each record as a reading on the ORIGINAL card (NaN where it is not a
    harvest reading): sms_align with the grain no reading took carried to the readings next to it, or the grain of
    the record the fixed shift takes."""
    method, fd, md = _alignment(kw)
    wet = R.wet_kg.to_numpy()
    if method != "sms":
        return np.where(take >= 0, wet[np.maximum(take, 0)], np.nan)
    out = np.full(len(R), np.nan)
    h0 = R.harvest.to_numpy() & R.gnss_ok.to_numpy()
    for _, idx in _by_machine(R):
        a = G.sms_align(R.t_ms.to_numpy()[idx], wet[idx], R.moisture_pct.to_numpy()[idx], h0[idx], fd, md,
                        float(np.median(R.ivl_s.to_numpy()[idx])))
        out[idx] = a["wet_kg"]
    return out


def grain_targets(R: pd.DataFrame, take: np.ndarray, a0: np.ndarray, keep: np.ndarray,
                  factor_of_row: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """The grain (kg) each record of the decoded units holds on the written card: the decoder's grain of the kept
    reading that takes it (a0 x factor) for the kept readings' own grain records, 0 for every other record with a
    grain value, NaN where the record has none. Returns (target per row, {"n_own", "n_lost", "kg_lost", "kg_lost_max"})
    - lost: kept readings that take no grain record and so cannot hold the (carried) grain a0 gives them."""
    wet = R.wet_kg.to_numpy()
    f = np.ones(len(R)) if factor_of_row is None else np.asarray(factor_of_row, float)
    tgt = np.where(np.isfinite(wet), 0.0, np.nan)
    own = keep & (take >= 0)
    tgt[take[own]] = np.nan_to_num(a0[own]) * f[own]
    lost = keep & (take < 0) & (np.nan_to_num(a0) > 0)
    return tgt, {"n_own": int(own.sum()), "n_lost": int(lost.sum()), "kg_lost": float(np.nansum(a0[lost])),
                 "kg_lost_max": float(np.nanmax(a0[lost])) if lost.any() else 0.0}


def run_neighbours(R: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(prev, next) per record of R (_records: the records of each log block in order): True where the record just
    before / just after it is in the same log block with no pause of the log between (the next record logged at most
    jd_gs3_rcd.LOG_BREAK log intervals later, the decoder's own pause)."""
    n = len(R)
    if n < 2:
        return np.zeros(n, bool), np.zeros(n, bool)
    bi = R.bi.to_numpy()
    d = np.diff(R.t_ms.to_numpy().astype(np.int64))
    lim = float(getattr(G, "LOG_BREAK", 2.5)) * 1000.0 * R.ivl_s.to_numpy().astype(float)[1:]
    same = (bi[1:] == bi[:-1]) & (d >= 0) & (d <= lim)
    return np.r_[False, same], np.r_[same, False]


def left_as_harvest(R: pd.DataFrame, keep: np.ndarray, harvest: np.ndarray, mode: str = REMOVED_AS_HARVEST[0]
                    ) -> np.ndarray:
    """The harvest records that are not kept readings and stay harvest readings on the written card (header and
    sections as logged, their grain record 0 kg): mode "buffer" those next to a kept reading (run_neighbours),
    "full" all of them, "none" none."""
    keep = np.asarray(keep, bool)
    cand = np.asarray(harvest, bool) & ~keep
    if mode == "none":
        return np.zeros(len(cand), bool)
    if mode == "full":
        return cand
    if mode != "buffer":
        raise WriteError(f"removed_as_harvest must be one of {', '.join(REMOVED_AS_HARVEST)}, not {mode!r}")
    prev, nxt = run_neighbours(R)
    return cand & ((np.r_[False, keep[:-1]] & prev) | (np.r_[keep[1:], False] & nxt))


def new_run_edges(R: pd.DataFrame, keep: np.ndarray, harvest_logged: np.ndarray, harvest_written: np.ndarray
                  ) -> np.ndarray:
    """The kept readings that start or end a harvesting run on the written card but not on the card as logged: a
    record next to them (run_neighbours) harvesting as logged and not as written."""
    prev, nxt = run_neighbours(R)
    gone = np.asarray(harvest_logged, bool) & ~np.asarray(harvest_written, bool)
    return np.asarray(keep, bool) & ((np.r_[False, gone[:-1]] & prev) | (np.r_[gone[1:], False] & nxt))


# ------------------------------------------------------------------------------------------------- clean file
def _read_clean(clean_shp: str) -> pd.DataFrame:
    import pyogrio
    if not clean_shp or not os.path.exists(clean_shp):
        raise EmptyCleanError(f"the clean file {clean_shp!r} is not found")
    have = set(pyogrio.read_info(clean_shp)["fields"])
    miss = {"Machine", "Time"} - have
    if miss:
        raise NotThisSourceError(f"the clean file has no {sorted(miss)} column: it does not come from a decoded card")
    cols = [c for c in ("Machine", "Time", "Swth_Wdth_", "Distance_f", "Duration_s", "Moisture__", "Yld_Mass_W")
            if c in have]
    df = pyogrio.read_dataframe(clean_shp, columns=cols)
    if len(df) and df.crs is not None and not df.crs.equals("EPSG:4326"):
        df = df.to_crs("EPSG:4326")
    out = pd.DataFrame(df.drop(columns="geometry"))
    out["lon"] = df.geometry.x.to_numpy() if len(df) else np.zeros(0)
    out["lat"] = df.geometry.y.to_numpy() if len(df) else np.zeros(0)
    out["Machine"] = out["Machine"].astype(str)
    out["Time"] = out["Time"].astype(str)
    return out


def _lateral_m(lat0, lon0, head_deg, lat1, lon1) -> np.ndarray:
    """Metres from point 0 to point 1, to the right of the heading (local plane)."""
    k = 111_320.0
    dx = (np.asarray(lon1, float) - np.asarray(lon0, float)) * k * np.cos(np.radians(np.asarray(lat0, float)))
    dy = (np.asarray(lat1, float) - np.asarray(lat0, float)) * k
    h = np.radians(np.asarray(head_deg, float))
    return dx * np.cos(h) - dy * np.sin(h)


def section_window(on_secs: list, width_m: float, s_m: float) -> list:
    """The contiguous run of recording sections (on_secs: [(id, width_m, lateral_m)] sorted by lateral offset, + =
    right) whose total width is nearest width_m (ties: the wider), then whose centre is nearest s_m."""
    best, key = list(on_secs), None
    for a in range(len(on_secs)):
        w = cw = 0.0
        for b in range(a, len(on_secs)):
            w += on_secs[b][1]
            cw += on_secs[b][1] * on_secs[b][2]
            kk = (round(abs(w - width_m), 6), -w, abs(cw / w - s_m) if w > 0 else 0.0)
            if key is None or kk < key:
                best, key = list(on_secs[a:b + 1]), kk
    return best


# ------------------------------------------------------------------------------------------------- new ids
def new_id_map(paths, tag: int | None = None) -> dict:
    """{old id: new id} for the card files named by a GreenStar id (<8 hex>-0000-1xyz-<4>-<12>): group 3 becomes
    '1' + 3 hex digits (from ``tag``; default random) that no file id of the card uses - the same length, the version
    digit kept; each group-3 value of the card gets its own new value, so no two files end up with one id."""
    guids = sorted({os.path.splitext(os.path.basename(p))[0] for p in paths if str(p).lower().endswith(_CARD_FILES)})
    guids = [g for g in guids if _GUID_NAME.match(g)]
    used = {_GUID_NAME.match(g).group(2) for g in guids}
    tag = secrets.randbelow(0xFFF) + 1 if tag is None else (int(tag) % 0x1000 or 1)
    new_g3 = {}
    for old in sorted(used):
        for _ in range(0x1000):
            g3 = f"1{tag:03x}"
            tag = tag % 0xFFF + 1
            if g3 not in used and g3 not in new_g3.values():
                new_g3[old] = g3
                break
        else:
            raise WriteError("no free id value left for the card files")
    return {g: _GUID_NAME.sub(lambda mm: mm.group(1) + new_g3[mm.group(2)] + mm.group(3), g) for g in guids}


def _n_diff(a: bytes, b: bytes) -> int:
    if a == b:
        return 0
    n = min(len(a), len(b))
    return int(np.count_nonzero(np.frombuffer(a[:n], np.uint8) != np.frombuffer(b[:n], np.uint8))) + abs(len(a) - len(b))


# ------------------------------------------------------------------------------------------------- card files
def _card_files(blocks: list[dict], root: str) -> dict:
    """What to write: {"roots", "sessions" (.fdl of the decoded blocks), "fdr" (the load files they cite), "ver",
    "blocks" {fdl: every block of that session (jd_gs3_rcd.read_fdl)}, "left_out" {kind: count}}."""
    roots = sorted({_card_root(m["fdl"], root) for m in blocks})
    sessions = sorted({m["fdl"] for m in blocks})
    allb = {f: G.read_fdl(f) for f in sessions}
    refs = {m["load_ref"].lower() for bs in allb.values() for m in bs if m.get("load_ref")}
    fdr, ver, left = [], [], {"sessions": 0, "load files": 0, "zip archives": 0, "other files": 0}
    keep_ses = {os.path.normcase(os.path.abspath(f)) for f in sessions}
    seen = set()
    for r0 in roots:
        for d, _, fs in os.walk(r0):
            for f in fs:
                p = os.path.join(d, f)
                k = os.path.normcase(os.path.abspath(p))
                if k in seen:
                    continue
                seen.add(k)
                low = f.lower()
                if low.endswith(".fdl"):
                    left["sessions"] += k not in keep_ses
                elif low.endswith(".fdd"):
                    pass                                  # counted with its .fdl
                elif low.endswith(".fdr"):
                    if low[:-4] in refs:
                        fdr.append(p)
                    else:
                        left["load files"] += 1
                elif low.endswith(".ver"):
                    ver.append(p)
                elif low.endswith(".zip"):
                    left["zip archives"] += 1
                else:
                    left["other files"] += 1
    return {"roots": roots, "sessions": sessions, "fdr": sorted(fdr), "ver": sorted(ver), "blocks": allb,
            "left_out": left}


def _neutralise(blk: bytearray, m: dict, st: dict) -> None:
    """A log block of another unit inside a written session: every record not harvesting and 0 kg of grain."""
    L = Layout(bytes(blk))
    d, _ = G.block_frame(m, bytes(blk))
    harv = np.flatnonzero(d.header_on.to_numpy() & (d.sections_on.to_numpy() > 0))
    hc = m["header_col"] if m["header_col"] in L.index else None
    if len(harv):
        if hc:
            st["values_flag"] += set_enum(blk, L, harv, hc, L.enum_index(hc, "Off"))
        for s in m["sections"]:
            if s["col"] in L.index:
                st["values_flag"] += set_enum(blk, L, harv, s["col"], L.enum_index(s["col"], "Off"))
    st["n_other_flagged"] += len(harv)
    mc = m["mass_col"]
    if mc in L.index:
        res = float(L.columns[L.index[mc]]["res"])
        v = d.wet_kg.to_numpy()
        e = np.where(np.isfinite(v), -np.round(np.nan_to_num(v) / res), 0).astype(np.int64)
        if len(correct_numeric(blk, L, mc, e)):
            raise WriteError(f"block {m['block']} of another field in a written session: its grain cannot be set to "
                             "0 in place")
        st["kg_other_zeroed"] += float(np.nansum(v))


# ------------------------------------------------------------------------------------------------- main
def write_clean(source: dict, clean_shp: str, out_dir: str, *, widths: bool = True, factors: dict | None = None,
                new_ids: bool = True, log=print, id_tag: int | None = None, folder_name: str | None = None,
                check: bool = True, removed_as_harvest: str = REMOVED_AS_HARVEST[0]) -> dict:
    """Write the readings of ``clean_shp`` back into a copy of the GreenStar 3 card(s) they were decoded from.

    source      engine.run.decode(...)['source'] of the decode that made the readings (its decode report gives the
                input root, the unit ids and the time basis; 'input_root' / 'unit_ids' in the dict take precedence).
    clean_shp   the clean point file OCED wrote: any non-empty subset of the decoded readings (Machine, Time as
                decoded).
    out_dir     where the card folder (<input folder>_clean) and its zip are written; never in the input folder.
    widths      level 2: write the clean swath width (whole sections) and distance of each kept reading.
    factors     level 3: {machine (the clean file's Machine): factor} on the grain of that machine's kept readings.
    new_ids     give the card files new GreenStar ids so that a reader that archives by file name takes them as new.
    id_tag      the 3 hex digits of the new ids (default random); folder_name: the card folder's name.
    check       decode the written card again and compare it with the clean file (R["check"]).
    removed_as_harvest  which harvest records that are not kept readings stay harvest readings with 0 kg of grain
                (the card must then be read with a minimum yield above 0: R["min_yield_needed"]): "buffer" (default)
                those next to a kept reading, so that no kept reading starts or ends a harvesting run the raw card
                did not have; "full" all of them; "none" none (every one switched off).
    Returns {"path", "zip", "n_kept", "n_removed", "n_not_offered", "files_changed", "notes", "warnings", "grain",
    "check", "expected_summary", ...}. Raises WriteError (the subclasses above) with a plain message.
    """
    t0 = time.time()
    if removed_as_harvest not in REMOVED_AS_HARVEST:
        raise WriteError(f"removed_as_harvest must be one of {', '.join(REMOVED_AS_HARVEST)}, not "
                         f"{removed_as_harvest!r}")
    notes, warnings = [], []
    root, units, tz, kw, rep = _resolve_source(source)
    name = folder_name or (os.path.basename(os.path.normpath(root)) + "_clean")
    dest = _check_output(out_dir, name, root)
    CL = _read_clean(clean_shp)
    n_clean = len(CL)
    if not n_clean:
        raise EmptyCleanError("the clean file holds no reading: there is nothing to write back")
    blocks, R, others = _records(root, units, tz)
    method, fd, md = _alignment(kw)

    # ---- key: (Machine, Time) of the clean rows -> records
    dup_r = R.duplicated(["Machine", "Time"], keep=False)
    if dup_r.any():
        warnings.append(f"{int(dup_r.sum())} records share their machine and time with another record; a clean reading "
                        "with such a key keeps all of them")
    dup_c = CL.duplicated(["Machine", "Time"], keep="first").to_numpy()
    n_dup = int(dup_c.sum())
    if n_dup:
        warnings.append(f"{n_dup:,} rows of the clean file repeat the machine and time of another row: each reading is "
                        "written once")
        CL = CL[~dup_c].reset_index(drop=True)
    R["row"] = np.arange(len(R))
    J = CL.merge(R[["Machine", "Time", "row"]], on=["Machine", "Time"], how="left")
    unmatched = int(J.row.isna().sum())
    if unmatched == len(J):
        raise NotThisSourceError("no clean reading matches a record of the card by machine and time: the clean file "
                                 "does not come from this decode (another card, or another time basis)")
    if unmatched:
        warnings.append(f"{unmatched:,} clean readings match no record of the card (machine + time): they are not in "
                        "the written card")
    J = J.dropna(subset=["row"]).copy()
    J["row"] = J.row.astype(np.int64)
    take, how = taken_records(R, kw)
    decoded = decoded_mask(R, take, kw)
    harvest = R.harvest.to_numpy()
    matched = np.zeros(len(R), bool)
    matched[J.row.to_numpy()] = True
    keep = matched & decoded
    n_kept_nd = int((matched & ~decoded).sum())
    if n_kept_nd:
        warnings.append(f"{n_kept_nd:,} clean readings fall on records the decoder does not offer as readings (header "
                        "up, no section recording or no valid position): they are not harvest readings on the written "
                        "card")
    if not keep.any():
        raise NotThisSourceError("none of the clean readings is a harvest reading of the card")
    # the harvest records that are not kept readings: those removed_as_harvest leaves stay harvest readings (0 kg of
    # grain below), the others are switched off; "buffer" / "full" give no kept reading a run edge the card did not have
    stay = left_as_harvest(R, keep, harvest, removed_as_harvest)
    flag = harvest & ~keep & ~stay
    removed = decoded & ~keep
    not_offered = harvest & ~decoded
    n_rem, n_no = int(removed.sum()), int(not_offered.sum())
    n_rem_left, n_no_left = int((removed & stay).sum()), int((not_offered & stay).sum())
    n_left = n_rem_left + n_no_left
    n_edges = int(new_run_edges(R, keep, harvest, harvest & ~flag).sum())
    mp0 = rep.get("monitor_product") if isinstance(rep.get("monitor_product"), dict) else {}
    min_need = float(mp0["min_yield"]) if mp0.get("min_yield") is not None else float(G.MONITOR_MIN_YIELD)

    # ---- grain: only the kept readings' own grain records hold grain, each the decoder's grain of that reading
    wet = R.wet_kg.to_numpy()
    a0 = decoded_grain(R, take, kw)
    factors = {str(k): float(v) for k, v in (factors or {}).items() if v is not None}
    unknown_f = sorted(set(factors) - set(R.Machine.unique()))
    if unknown_f:
        warnings.append(f"factors given for machines that are not on the card: {unknown_f}")
    f_row = R.Machine.map(lambda mm: factors.get(str(mm), 1.0)).to_numpy(float)
    tgt, ginfo = grain_targets(R, take, a0, keep, f_row)
    own_rec = np.zeros(len(R), bool)
    own_rec[take[keep & (take >= 0)]] = True

    # ---- level 2 targets: width (sections) and distance of the kept readings
    wtarget, dtarget, narrowed = {}, {}, set()
    Jk = J[keep[J.row.to_numpy()]]
    if "Swth_Wdth_" in Jk:
        rr = Jk.row.to_numpy()
        wc = Jk.Swth_Wdth_.to_numpy(float) / C.FT_PER_M
        nar = np.isfinite(wc) & (wc > 0) & (wc < R.width_m.to_numpy()[rr] - WIDTH_TOL_FT / C.FT_PER_M)
        narrowed = set(rr[nar].tolist())                  # narrower in the clean file (written or not)
        if widths and nar.any():
            s = _lateral_m(R.lat.to_numpy()[rr[nar]], R.lon.to_numpy()[rr[nar]], R.head_deg.to_numpy()[rr[nar]],
                           Jk.lat.to_numpy()[nar], Jk.lon.to_numpy()[nar])
            wtarget = {int(r): (float(w), float(x)) for r, w, x in zip(rr[nar], wc[nar], s)}
        if widths and "Distance_f" in Jk:
            dc = Jk.Distance_f.to_numpy(float) / C.FT_PER_M
            dr = R.dd_m.to_numpy()[rr]
            ch = np.isfinite(dc) & np.isfinite(dr) & (np.abs(dc - dr) * 100.0 >= DIST_MIN_CM)
            dtarget = {int(r): float(d) for r, d in zip(rr[ch], dc[ch])}

    # ---- edit the log blocks in memory, per .fdd of the written sessions
    files = _card_files(blocks, root)
    bi_arr = R.bi.to_numpy()
    st = dict(values_flag=0, values_width=0, width_err_ft=[], n_narrowed=0, width_skipped=0, n_dist=0, dist_failed=0,
              n_grain_changed=0, own_left=0, kg_own_left=0.0, other_left=0, kg_other_left=0.0, n_other_flagged=0,
              kg_other_zeroed=0.0, n_other_blocks=0, n_nonharvest_blocks=0)
    new_kg = wet.copy()
    by_fdd: dict[str, list] = {}
    for bi, m in enumerate(blocks):
        by_fdd.setdefault(m["fdd"], []).append(bi)
    decoded_keys = {(m["fdl"], m["block"]) for m in blocks}
    edited = {}
    for fdd, bis in by_fdd.items():
        with open(fdd, "rb") as fh:
            data = bytearray(fh.read())
        orig = bytes(data)
        for bi in bis:
            m = blocks[bi]
            rows = np.flatnonzero(bi_arr == bi)
            lo, hi = m["file_position"], m["end_position"]
            blk = bytearray(data[lo:hi])
            L = Layout(bytes(blk))
            if L.n != len(rows):
                raise WriteError(f"{os.path.basename(fdd)} block {m['block']}: {L.n} records in the layout, "
                                 f"{len(rows)} decoded")
            if not len(rows):
                continue
            secs = [s for s in m["sections"] if s["col"] in L.index]
            hc = m["header_col"] if m["header_col"] in L.index else None
            # level 1: every harvest record that is not a kept reading is no longer a harvest reading
            k = np.flatnonzero(flag[rows])
            if len(k):
                if hc:
                    st["values_flag"] += set_enum(blk, L, k, hc, L.enum_index(hc, "Off"))
                for s in secs:
                    st["values_flag"] += set_enum(blk, L, k, s["col"], L.enum_index(s["col"], "Off"))
            # level 2: sections of the narrowed kept readings
            if wtarget:
                for j in np.flatnonzero(np.isin(rows, list(wtarget))).tolist():
                    w, sm = wtarget[int(rows[j])]
                    on, ok = [], True
                    for si, s in enumerate(secs):
                        v = L.enum_value(blk, j, s["col"])
                        if v is None:
                            ok = False
                            break
                        if v == L.enum_index(s["col"], "On"):
                            on.append((si, s["width_m"], s["lateral_m"] if np.isfinite(s["lateral_m"]) else 0.0))
                    if not ok or not on:
                        st["width_skipped"] += 1
                        continue
                    on.sort(key=lambda x: x[2])
                    win = section_window(on, w, sm)
                    keep_ids = {x[0] for x in win}
                    for si, _, _ in on:
                        if si not in keep_ids:
                            st["values_width"] += set_enum(blk, L, [j], secs[si]["col"],
                                                           L.enum_index(secs[si]["col"], "Off"))
                    wn = sum(x[1] for x in win)
                    st["n_narrowed"] += int(wn < sum(x[1] for x in on) - 1e-9)
                    st["width_err_ft"].append((wn - w) * C.FT_PER_M)
            # level 2: distance of the implement point
            if dtarget:
                navs = {nv["type"]: nv for nv in reversed(m["nav"])}
                nav = navs.get("dtiComputedImplement") or navs.get("dtiVehicleGPS")
                ddcol = nav.get("vrDeltaDistance") if nav else None
                jj = np.flatnonzero(np.isin(rows, list(dtarget)))
                if ddcol in L.index and len(jj):
                    f_m = G._UOM_M.get(nav.get("dd_uom") or "", np.nan)
                    res = float(L.columns[L.index[ddcol]]["res"])
                    e = np.zeros(L.n, np.int64)
                    for j in jj.tolist():
                        r = int(rows[j])
                        e[j] = int(round((dtarget[r] - R.dd_m.to_numpy()[r]) / f_m / res))
                    for _ in range(6):
                        bad = correct_numeric(blk, L, ddcol, e)
                        if not len(bad):
                            break
                        drop = np.unique(np.clip(np.r_[bad, bad - 1], 0, L.n - 1))
                        st["dist_failed"] += int(np.count_nonzero(e[drop]))
                        e[drop] = 0
                    else:
                        st["dist_failed"] += int(np.count_nonzero(e))
                        e[:] = 0
                    st["n_dist"] += int(np.count_nonzero(e))
            # grain: each record its target (the kept readings' own records their grain, every other record 0 kg)
            mc = m["mass_col"]
            if mc in L.index:
                res = float(L.columns[L.index[mc]]["res"])
                v = wet[rows]
                ok = np.isfinite(v)
                kv = np.round(np.nan_to_num(v) / res)                  # the logged value in steps of res
                tq = np.round(np.nan_to_num(tgt[rows]) / res)          # the target, rounded half to even
                e = np.where(ok, tq - kv, 0).astype(np.int64)
                scale = factors.get(str(R.Machine.iloc[rows[0]]), 1.0) != 1.0
                for _ in range(8):
                    bad = correct_numeric(blk, L, mc, e)
                    if not len(bad):
                        break
                    near = np.unique(np.clip(np.r_[bad, bad - 1], 0, L.n - 1))
                    near = near[e[near] != 0]
                    if scale and own_rec[rows[near]].any():
                        raise WriteError(f"{os.path.basename(fdd)} block {m['block']}: the combine factor gives "
                                         f"grain values this card cannot hold (records {bad[:5].tolist()})")
                    if not len(near):
                        raise WriteError(f"{os.path.basename(fdd)} block {m['block']}: grain deltas cannot be written")
                    for j in near.tolist():                               # these records stay as logged
                        if own_rec[rows[j]]:
                            st["own_left"] += 1
                            st["kg_own_left"] += float(abs(e[j]) * res)
                        else:
                            st["other_left"] += 1
                            st["kg_other_left"] += float(v[j])
                    e[near] = 0
                else:
                    raise WriteError(f"{os.path.basename(fdd)} block {m['block']}: grain deltas cannot be written")
                new_kg[rows[ok]] = (kv[ok] + e[ok]) * res
                st["n_grain_changed"] += int(np.count_nonzero(e))
            if len(blk) != hi - lo:
                raise WriteError("internal: a log block changed size")
            data[lo:hi] = blk
        # blocks of the written sessions that are not decoded: the harvest of another unit is neutralised
        for f in files["sessions"]:
            if os.path.normcase(os.path.splitext(f)[0] + ".fdd") != os.path.normcase(fdd):
                continue
            for mb in files["blocks"][f]:
                if (mb["fdl"], mb["block"]) in decoded_keys:
                    continue
                if mb["op_class"] == "dtiHarvest" and mb["mass_col"]:
                    lo, hi = mb["file_position"], mb["end_position"]
                    blk = bytearray(data[lo:hi])
                    _neutralise(blk, mb, st)
                    if len(blk) != hi - lo:
                        raise WriteError("internal: a log block changed size")
                    data[lo:hi] = blk
                    st["n_other_blocks"] += 1
                else:
                    st["n_nonharvest_blocks"] += 1
        if bytes(data) != orig:
            edited[os.path.normcase(os.path.abspath(fdd))] = bytes(data)

    # ---- output tree: only the written sessions, the load files they cite and the version files
    roots = files["roots"]
    base = os.path.commonpath(roots) if len(roots) > 1 else os.path.dirname(roots[0])
    src_files = sorted({p for f in files["sessions"] for p in (f, os.path.splitext(f)[0] + ".fdd")}
                       | set(files["fdr"]) | set(files["ver"]))
    for p in src_files:
        if not os.path.exists(p):
            raise InputGoneError(f"{os.path.basename(p)} is no longer in the input folder")
    if os.path.isdir(dest):
        shutil.rmtree(dest)                               # a card written before (_check_output checked it)
    os.makedirs(dest)
    idmap = new_id_map(src_files, id_tag) if new_ids else {}
    pairs = [(a.encode("latin1"), b.encode("latin1")) for a, b in idmap.items()]
    files_changed, bytes_changed = [], {}
    for p in src_files:
        rel = os.path.relpath(p, base)
        stem, ext = os.path.splitext(os.path.basename(rel))
        new_rel = os.path.join(os.path.dirname(rel), idmap[stem] + ext) if stem in idmap else rel
        q = os.path.join(dest, new_rel)
        os.makedirs(os.path.dirname(q), exist_ok=True)
        with open(p, "rb") as fh:
            raw = fh.read()
        key = os.path.normcase(os.path.abspath(p))
        out = edited.get(key, raw)
        if pairs and ext.lower() in (".fdl", ".fdr"):
            for a, b in pairs:
                out = out.replace(a, b)
        with open(q, "wb") as fh:
            fh.write(out)
        shutil.copystat(p, q)
        nd = _n_diff(raw, out)
        if nd or new_rel != rel:
            what = (["log records"] if key in edited else []) + (["ids cited"] if nd and key not in edited else []) \
                + (["renamed (new id)"] if new_rel != rel else [])
            files_changed.append({"file": new_rel.replace(os.sep, "/"), "from": rel.replace(os.sep, "/"),
                                  "bytes_changed": int(nd), "size": len(out), "what": ", ".join(what)})
            bytes_changed[new_rel.replace(os.sep, "/")] = int(nd)
    zpath = os.path.join(out_dir, name + ".zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, ds, fs in os.walk(dest):
            ds.sort()
            rel_d = os.path.relpath(d, dest)
            if rel_d != ".":
                z.writestr(zipfile.ZipInfo(rel_d.replace(os.sep, "/") + "/"), b"")
            for f in sorted(fs):
                p = os.path.join(d, f)
                z.write(p, os.path.relpath(p, dest).replace(os.sep, "/"))

    # ---- grain accounting (kg wet; the clean file's grain is the decoder's grain of the kept readings)
    kg = {"card": float(np.nansum(wet)), "decoded": float(np.nansum(a0[decoded])),
          "kept": float(np.nansum(a0[keep])), "removed": float(np.nansum(a0[removed])),
          "kept_x_factor": float(np.nansum(a0[keep] * f_row[keep])), "written": float(np.nansum(new_kg)),
          "kept_without_own_record": ginfo["kg_lost"], "max_kept_without_own_record": ginfo["kg_lost_max"],
          "left_as_logged_other": st["kg_other_left"]}
    kg["not_on_a_reading"] = kg["card"] - kg["decoded"]
    grain = {"kg": kg, "n_kept_without_own_record": ginfo["n_lost"], "n_own_records": ginfo["n_own"],
             "n_values_changed": st["n_grain_changed"], "own_left_as_logged": st["own_left"],
             "other_left_as_logged": st["other_left"]}

    # ---- what was done
    nk = int(keep.sum())
    notes.append(f"{nk:,} clean readings stay harvest readings; {n_rem:,} decoded readings the clean file left out "
                 f"(the import's minimum / maximum and the cleaning): {n_rem - n_rem_left:,} set to not harvesting, "
                 f"{n_rem_left:,} left as harvest readings with 0 kg of grain; no record deleted, every record keeps "
                 f"its size")
    if n_no:
        notes.append(f"{n_no:,} more harvest records the decoder never offered as a reading (no valid position"
                     + ("" if method == "sms" else
                        f"; standing, or no grain / moisture record {fd:g} / {md:g} s later")
                     + f"), independent of the cleaning: {n_no - n_no_left:,} set to not harvesting, {n_no_left:,} "
                     "left as logged with 0 kg of grain")
    if n_left:
        notes.append(f"READ THIS CARD WITH A MINIMUM YIELD ABOVE 0: the import's minimum, {min_need:g} bu/ac dry (SMS's "
                     "Processing Settings for GreenStar 3 cards; OCED's import minimum). "
                     f"{n_left:,} harvest records the clean file does not hold ({n_rem_left:,} readings the import's "
                     "minimum / maximum or the cleaning removed"
                     + (f", {n_no_left:,} records never offered as a reading" if n_no_left else "")
                     + ") stay harvest readings with 0 kg of grain ("
                     + ("each next to a kept reading" if removed_as_harvest == "buffer" else "all of them, as logged")
                     + "), so that no kept reading starts or ends a harvesting run the raw card did not have (SMS "
                     "leaves out some readings at the edge of a run); that minimum leaves them out, as it leaves out "
                     f"the raw card's readings without grain. Read with a minimum of 0 they would be up to {n_left:,} "
                     "points of 0 yield")
    if min_need <= 0 and n_left:
        warnings.append(f"the import's minimum yield of this card is {min_need:g} bu/ac: the {n_left:,} harvest records "
                        "left with 0 kg of grain would be read as points of 0 yield; write with "
                        "removed_as_harvest='none' or read the card with a minimum above 0")
    edge_txt = (f"run edges: {n_edges:,} kept readings start or end a harvesting run the raw card did not have (a "
                "record next to them switched off)")
    if n_edges:
        warnings.append(edge_txt + ": SMS leaves out some readings at the edge of a run, so it may read fewer "
                        "readings than the clean file holds (removed_as_harvest 'buffer' or 'full' makes none)")
    else:
        notes.append(edge_txt)
    if abs(kg["not_on_a_reading"]) > 0.05:
        notes.append(f"{kg['not_on_a_reading']:,.1f} kg of the card's {kg['card']:,.1f} kg wet grain "
                     f"({100.0 * kg['not_on_a_reading'] / max(kg['card'], 1e-9):.2f} %) is on no decoded reading and "
                     "so not on the written card, independent of the cleaning (a reader of the original card that "
                     "carries such grain would read it)")
    notes.append(f"header and every section Off in {st['values_flag']:,} values")
    notes.append(f"grain: only the {ginfo['n_own']:,} grain records the kept readings take ({how}) hold grain, each "
                 f"the decoder's grain of that reading{' x the factor' if factors else ''}: {kg['written']:,.1f} kg "
                 f"wet written for {kg['kept_x_factor']:,.1f} kg in the clean readings; every other grain record "
                 f"0 kg ({kg['removed']:,.1f} kg of the removed readings not written); {st['n_grain_changed']:,} "
                 "grain values rewritten, nothing left for a reader to carry into a kept reading")
    if ginfo["n_lost"]:
        warnings.append(f"{ginfo['n_lost']:,} kept readings took no grain record of their own (the log paused within "
                        f"{fd:g} s after them) and held only grain the decoder carried to them: "
                        f"{ginfo['kg_lost']:,.2f} kg wet ({100.0 * ginfo['kg_lost'] / max(kg['kept'], 1e-9):.3f} % of "
                        f"the kept grain, at most {ginfo['kg_lost_max']:.2f} kg in one reading) cannot be written on "
                        "the card: they read 0 kg there (a reader's minimum yield then drops them)")
    if st["own_left"]:
        warnings.append(f"{st['own_left']} kept readings keep their logged grain: the decoder's value cannot be "
                        f"written in place ({st['kg_own_left']:,.2f} kg)")
    if st["other_left"]:
        warnings.append(f"{st['other_left']} grain records outside the kept readings could not be set to 0 in place "
                        f"({st['kg_other_left']:,.2f} kg): a reader that carries grain may move it into nearby "
                        "readings")
    if method != "sms":
        warnings.append("the readings were decoded with the fixed-shift alignment, not the one Ag Leader SMS uses "
                        "(sms_align): a reader that matches records as SMS does may give some kept readings another "
                        "grain record (0 kg on the written card) near the pauses of the log")
    if widths:
        e = np.asarray(st["width_err_ft"], float)
        if len(e):
            secw = np.nanmedian([s["width_m"] for m in blocks for s in m["sections"]]) * C.FT_PER_M
            notes.append(f"level 2: {len(e):,} kept readings are narrower in the clean file; written as whole sections "
                         f"({secw:.2f} ft each): {st['n_narrowed']:,} narrowed, written minus clean width mean "
                         f"{e.mean():+.2f} ft, |difference| max {np.abs(e).max():.2f} ft")
            warnings.append("swath widths are written in whole sections, not to the foot: a narrowed reading's width "
                            "and yield in the card differ from the clean file's by the rounding of its width")
        else:
            notes.append("level 2: no kept reading is narrower in the clean file than on the card")
        if st["width_skipped"]:
            warnings.append(f"level 2: {st['width_skipped']} narrowed readings left at their logged width (sections "
                            "not held in a form this writer rewrites)")
        notes.append(f"level 2: {st['n_dist']:,} distances written as in the clean file (1 cm resolution)"
                     + (f"; {st['dist_failed']} left as logged" if st["dist_failed"] else ""))
    if factors:
        notes.append("level 3: grain x factor (" + ", ".join(f"{k} x {v:g}" for k, v in factors.items())
                     + "), rounded to the channel's resolution; the meter's calibration number in the .fdl is left as "
                     "the monitor wrote it (the monitor's own load totals are not the factored grain)")
    lo_ = {k: v for k, v in files["left_out"].items() if v}
    if lo_ or others:
        notes.append("not written: " + ", ".join(f"{v} {k}" for k, v in lo_.items())
                     + (f"{'; ' if lo_ else ''}{len(others)} harvest log block(s) of other fields / crops / years"
                        if others else "")
                     + " (other fields, crops, years or operations, duplicate copies and archives are not part of the "
                     "clean card)")
    if st["n_other_blocks"]:
        warnings.append(f"{st['n_other_blocks']} log block(s) of another field / crop / year share a session with the "
                        f"decoded loads: kept so that the session stays readable, with every record not harvesting "
                        f"({st['n_other_flagged']:,} records) and 0 kg grain ({st['kg_other_zeroed']:,.1f} kg)")
    if st["n_nonharvest_blocks"]:
        warnings.append(f"{st['n_nonharvest_blocks']} log block(s) of another operation share a session with the "
                        "decoded loads: copied as the monitor wrote them")
    if idmap:
        n_ren = sum(1 for f in files_changed if "renamed" in f["what"])
        notes.append(f"new ids: {n_ren} card files renamed ({len(idmap)} ids; group 3 of the id "
                     f"{'/'.join(sorted({_GUID_NAME.match(g).group(2) for g in idmap}))} -> "
                     f"{'/'.join(sorted({_GUID_NAME.match(g).group(2) for g in idmap.values()}))}), the ids cited in "
                     "the .fdl / .fdr files replaced; group 1 (the session start) kept")
    notes.append("left as the monitor wrote it: record count and size of every log block (every filePosition of the "
                 ".fdl stays right), column lists, times, positions, moisture, crop / machine / field set-up, load "
                 "files, global.ver")
    notes.append("not yet tested in Ag Leader SMS: unzip the card to a folder or a USB stick and read it in a scratch "
                 "project first (start / stop delay 0"
                 + (f", minimum yield {min_need:g} bu/ac, not 0" if n_left else "")
                 + "); do not run Clip, Optimize Swath Widths or the 3-sigma filters on it again (they would remove or "
                 "narrow readings a second time)")
    res = {"path": dest, "zip": zpath, "n_kept": nk, "n_removed": n_rem, "n_not_offered": n_no,
           "removed_as_harvest": removed_as_harvest, "n_removed_harvest": n_rem_left,
           "n_not_offered_harvest": n_no_left, "n_new_run_edges": n_edges,
           "min_yield_needed": min_need if n_left else None,
           "files_changed": files_changed, "notes": notes, "warnings": warnings, "format": FORMAT_ID,
           "alignment": how, "id_map": idmap, "n_clean_rows": int(n_clean), "n_duplicate_rows": n_dup,
           "n_unmatched": unmatched, "n_records": int(len(R)), "grain": grain,
           "n_width_changed": len(st["width_err_ft"]), "n_distance_changed": st["n_dist"],
           "bytes_changed": bytes_changed, "left_out": files["left_out"]}
    if check:
        try:
            res["check"] = check_written(res["path"], source, J, keep, rep, units, kw, narrowed=narrowed,
                                         factors=factors, left=R.loc[stay, ["Machine", "Time"]])
        except Exception as e:                            # the card is written; the check reports, never hides it
            res["check"] = {"error": f"{type(e).__name__}: {e}"}
        ck = res["check"]
        if ck.get("error"):
            warnings.append(f"the written card could not be decoded again for the check: {ck['error']}")
        else:
            res["expected_summary"] = ck.get("expected_summary")
            if ck["missing"] or ck["extra"]:
                warnings.append(f"check: decoding the written card gives {ck['decoded']:,} readings: {ck['missing']:,} "
                                f"kept readings missing, {ck['extra']:,} readings that are not in the clean file")
            xb = int(ck.get("extra_below_min") or 0)
            notes.append(f"check: the written card decodes to {ck['decoded']:,} readings ({ck['matched']:,} of the "
                         f"{nk:,} kept, {ck['extra']:,} others"
                         + (f", {xb:,} harvest records left with 0 kg, below the minimum yield" if xb else "")
                         + "); read with the import's minimum it holds "
                         + ("exactly the clean readings" if not (ck["missing"] or ck["extra"]) else
                            "NOT exactly the clean readings")
                         + f"; grain differs by more than {GRAIN_TOL_KG * 1000:g} g from the clean file"
                         f"{' x the factor' if factors else ''} on {ck['n_grain_differs']:,} readings")
            nb = int((ck.get("expected_summary") or {}).get("n_below_min") or 0)
            if nb:
                es = ck["expected_summary"]
                xl = int(es.get("n_left_below_min") or 0)
                notes.append(f"{nb:,} reading(s) of the written card fall below the minimum yield of "
                             f"{float(es.get('min_yield') or 0):g} bu/ac dry"
                             + (f" ({xl:,} the harvest records left with 0 kg, {nb - xl:,} kept readings"
                                + (" once the factors are applied" if factors else "") + ")" if xl else
                                (" once the factors are applied" if factors else ""))
                             + ": a reader with that minimum (SMS) leaves them out, so the expected Summary counts "
                             f"{int(es.get('gps_count') or 0):,} readings")
    log(f"written {dest} in {time.time() - t0:.1f} s: {nk:,} kept, {n_rem:,} removed, {n_no:,} never offered, "
        f"{n_left:,} left as harvest records with 0 kg, {n_edges:,} new run edges, "
        f"{st['n_grain_changed']:,} grain values rewritten, {len(files_changed)} files changed")
    return res


def _options(source: dict, rep: dict) -> C.DecodeOptions:
    o = dict(source.get("options") or rep.get("options") or {})
    names = {f.name for f in dataclasses.fields(C.DecodeOptions)}
    o = {k: v for k, v in o.items() if k in names}
    o.setdefault("shrink", "one_sided")
    return C.DecodeOptions(**o)


def check_written(path: str, source: dict, J: pd.DataFrame, keep: np.ndarray, rep: dict, units, kw: dict,
                  narrowed=(), factors: dict | None = None, left: pd.DataFrame | None = None) -> dict:
    """Decode the written card with the source's options and compare it with the kept clean rows (J: the clean rows
    with the record row they match): {"decoded", "matched", "missing", "extra", "n_grain_differs", "max_abs"
    {attribute: largest |written - clean|}, "expected_summary"}. A clean row's grain is its Yld_Mass_W x area (lb ->
    kg); positions are compared on the readings level 2 did not narrow (``narrowed``: their record rows; a narrowed
    reading sits at the centre of its recording sections, the clean point where the cleaning moved it). The expected
    summary is what a reader that reads the card as the decoder does and applies the monitor product's minimum /
    maximum yield should show (n_below_min: the decoded readings below that minimum). factors: the level-3 factors
    written ({machine: f}); a clean row's grain is then compared x the factor of its machine. left: (Machine, Time)
    of the harvest records the writer left as harvest readings with 0 kg (removed_as_harvest): a reading of the
    written card the clean file does not hold is "extra_below_min", not "extra", when it is one of them, reads no
    grain and falls below the minimum yield (or has no yield): the card read with that minimum is then exactly the
    clean readings."""
    df, r2 = G.decode(path, units, _options(source, rep), log=lambda m: None, **kw)
    mp = r2.get("monitor_product") or {}
    lo, hi = mp.get("min_yield", G.MONITOR_MIN_YIELD), mp.get("max_yield", G.MONITOR_MAX_YIELD)
    yd = df.Yld_Vol_Dr.to_numpy(float)
    below = ~(np.isfinite(yd) & (yd >= lo))                   # what a reader with that minimum leaves out
    ck = J[keep[J.row.to_numpy()]]
    M = ck.merge(df.assign(_below=below), on=["Machine", "Time"], how="outer", suffixes=("_c", ""), indicator=True)
    both = M[M._merge == "both"]
    ro = M[M._merge == "right_only"]
    lk = set() if left is None else set(zip(left.Machine.astype(str), left.Time.astype(str)))
    is_left = np.fromiter(((str(a), str(b)) in lk for a, b in zip(ro.Machine, ro.Time)), bool, len(ro))
    no_grain = ~(np.nan_to_num(ro.Yld_Mass_W.to_numpy(float)) > 0)
    ok_left = is_left & ro._below.to_numpy().astype(bool) & no_grain
    out = {"decoded": int(len(df)), "matched": int(len(both)), "missing": int((M._merge == "left_only").sum()),
           "extra": int((~ok_left).sum()), "extra_below_min": int(ok_left.sum()),
           "decoded_at_min": int((~below).sum()),
           "max_abs": {}, "n_grain_differs": 0}
    for c, tol in (("Duration_s", 1e-6), ("Distance_f", 0.5 / 30.48), ("Swth_Wdth_", WIDTH_TOL_FT),
                   ("Moisture__", 1e-6)):
        if c + "_c" in both:
            dv = np.abs(both[c].to_numpy(float) - both[c + "_c"].to_numpy(float))
            out["max_abs"][c] = float(np.nanmax(dv, initial=0.0))
            out[f"n_{c.rstrip('_')}_differs"] = int(np.count_nonzero(dv > tol))
    if {"Yld_Mass_W_c", "Distance_f_c", "Swth_Wdth__c"} <= set(both.columns):
        def kgw(sfx):
            return (both["Yld_Mass_W" + sfx] * both["Distance_f" + sfx] * both["Swth_Wdth_" + sfx] / C.SQFT_PER_AC
                    / C.LB_PER_KG).to_numpy(float)
        fx = both.Machine.astype(str).map(lambda mm: (factors or {}).get(mm, 1.0)).to_numpy(float)
        dk = np.abs(kgw("") - kgw("_c") * fx)
        out["max_abs"]["wet_kg"] = float(np.nanmax(dk, initial=0.0))
        out["n_grain_differs"] = int(np.count_nonzero(dk > GRAIN_TOL_KG + 1e-9))
    if len(both):
        same_w = ~both.row.isin(list(narrowed)).to_numpy()
        dpos = np.hypot((both.lon.to_numpy() - both.lon_c.to_numpy()) * 111_320.0
                        * np.cos(np.radians(both.lat.to_numpy())), (both.lat.to_numpy() - both.lat_c.to_numpy())
                        * 111_320.0)
        out["max_abs"]["position_m"] = float(np.nanmax(dpos[same_w], initial=0.0))
    s = df[(df.Yld_Vol_Dr >= lo) & (df.Yld_Vol_Dr <= hi)]
    area = (s.Distance_f * s.Swth_Wdth_ / C.SQFT_PER_AC).to_numpy(float)
    wet_lb = float(np.nansum(s.Yld_Mass_W.to_numpy(float) * area))
    dry_bu = float(np.nansum(s.Yld_Vol_Dr.to_numpy(float) * area))
    a = float(area.sum())
    out["expected_summary"] = {
        "what": f"the written card read as the decoder reads it, then minimum {lo:g} / maximum {hi:g} bu/ac dry",
        "gps_count": int(len(s)), "area_ac": a, "wet_lb": wet_lb, "dry_bu": dry_bu,
        "moisture_pct": float(np.nansum(s.Moisture__.to_numpy(float) * area) / a) if a > 0 else None,
        "bu_ac": dry_bu / a if a > 0 else None, "n_below_min": int((df.Yld_Vol_Dr < lo).sum()),
        "n_left_below_min": int((ok_left & (ro.Yld_Vol_Dr.to_numpy(float) < lo)).sum()),
        "min_yield": lo, "max_yield": hi}
    return out
