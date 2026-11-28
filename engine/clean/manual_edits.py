# -*- coding: utf-8 -*-
"""Readings removed or kept by hand, then the SMS 3-sigma cleaning run again (the engine side).

The user looks at the result of a cleaning (the replay of the harvest: kept readings in colour, removed readings in
grey), picks readings that should leave and readings the filters removed that should stay, and reprocesses. The picks
travel in a small JSON file, the EDITS FILE:

    {"format": "oced-manual-edits", "version": 1,
     "note": "free text (optional)",
     "remove": ["<key of a reading>", ...],         # readings removed by hand
     "keep":   ["<key of a reading>", ...]}         # readings kept by hand

    from engine.clean import manual_edits as me
    E = me.write_edits("edits.json", remove=[...], keep=[...], note="...")   # writes the file, returns it read back
    E = me.read_edits("edits.json")         # or read_edits(dict): validated, keys sorted and made unique, sha256
    settings["manual_edits"] = "edits.json"  # or the dict: engine.run.clean / yield_clean.run take it
    # command line: python -m engine.run <inputs> --out <dir> --manual-edits edits.json
    keys, info = me.flagged_keys("<tag>_sms3s_flagged.shp")   # the key of every reading of a flagged file

THE KEY OF A READING (reading_keys). Five fields joined by '|': the combine (column Machine / VIN / Combine), the
dataset (Dataset / Task / Load ...), the record id (Obj__Id / ObjectId / Record ...), the time (Time / Timestamp ...)
and, only when the file has neither a record id nor a time column, the logged position (longitude and latitude in
WGS 84 with 7 decimals, about 1 cm). A field the file has no column for is empty. The columns are found by their names
(yield_clean.detect_columns, never by the settings' column overrides), so the same names give the same key in the
file the cleaning reads and in its flagged file, which carries those columns byte for byte. Every value is read as
text (a whole number as its digits; a time as the text the file holds, or, for a date-type field, as pandas writes the
date it reads, e.g. '2026-09-24 00:00:00', the same on both sides; no float formatting is involved unless the position
is used), so the key does not depend on the order of the rows and is the same every time the same raw data is decoded and
imported with the same settings (the decoders number their records and write their times deterministically).
Readings that share a key (no column tells them apart) are one key: an edit then applies to all of them; the count of
readings that share a key is reported (key info 'n_shared').

THE STEPS (sms3sigma.run_cascade with manual=Edits):
  SM  Removed by hand: the readings of the remove list that are still alive after Optimize Swath Widths leave in a
      step of their own, after S2 (and the repeated clip S1b) and before S3. The mean and the SD of S3, S4 and S5 are
      therefore computed without them. They stay in S0, S1 and S2 exactly as before: the ground they covered was
      harvested, so the widths of their neighbours do not change. Rem_By = 'SM' in the flagged file; the cascade row
      'SM' names it. 'SM' cannot be read as any SMS step (S0, S1, S1b, S2, S3, S4, S5a ...): its second character is
      a letter.
  Kept by hand (KEEP_RULE): a reading of the keep list that is alive after S2 is never cut by S3, S4 or S5 (any
      pass). It takes part in the statistics of every one of those steps like any reading that is still present: the
      mean and SD of each step are computed with it, and the SD after a cut (the one that decides another yield pass)
      is the SD of the readings left after the cut, it included.
  A reading cut by the import's yield range, by the clip (S1, S1b, or set aside before the cleaning as outside the
  field of interest), by the import check S0 or by the swath step S2 cannot be kept by hand (outside the boundary, no
  plausible position or yield, or no width to compute a yield per area): such a key is not applied, it is reported
  with the reason, and the run goes on. The same holds for a remove key whose reading was already cut by them. A key
  in both lists is an error before anything runs. A key that matches no reading is a warning (count and the first
  ten) in the record, the report and the command line; it is never dropped in silence.

WHAT IS WRITTEN DOWN: R['manual_edits'] in the cleaning record (record()): the edits file's hash, the counts asked /
applied / not found / not applied (with reasons) of each list, the counts per combine (and per rate of a trial design
with a rate column), for every reading kept by hand the step that cut it in the automatic cleaning and the first
step of this cleaning whose limits it lies outside, and the AUTOMATIC result beside the edited one (points kept, acres,
dry bushels, area-weighted yield, limits and yield passes per combine) from the same steps run without the edits.
The record also counts the OTHER READINGS whose fate moved (in neither list, but cut by the automatic cleaning and kept
now, kept by it and cut now, or cut by another step): the readings removed by hand leave the statistics and the
readings kept by hand stay in them, so the limits of S3-S5 move and with them the fate of readings nobody picked.
A warning (R['warnings']: the report, the command line) says that the cleaning includes manual edits, with those
counts; when the edits change nothing (no reading removed by hand and every reading kept by hand kept by the automatic
cleaning too, e.g. only stale keys) it says instead that an edits file was given and the result is the automatic one. The flagged
file of a cleaning with edits has two more columns (FLAG_COLUMNS): Man_Edit ('R' removed by hand, 'K' kept by hand,
'N' asked but not applied, '' none) and Rem_Auto (the step that removed the reading in the automatic cleaning, ''
kept). The clean file never changes its columns. Without an edits file, or with one whose two lists are empty, the
cleaning is the automatic one, byte for byte (settle() drops the setting).

THE SWATH STEP ONCE (swath_once): S0-S2 do not depend on the edits, so the automatic run beside the edited one takes
the results of Optimize Swath Widths recorded in the edited run when its inputs are identical (compared array by
array), instead of computing them again; any difference in the inputs calls the module as usual.
"""
from __future__ import annotations

import contextlib
import copy
import functools
import hashlib
import json
import math
import os
import threading

import numpy as np
import pandas as pd

SETTING = "manual_edits"              # the settings key (yield_clean.merge_settings)
FORMAT = "oced-manual-edits"
VERSION = 1
FILE_KEYS = ("format", "version", "note", "remove", "keep")
DERIVED_KEYS = ("sha256", "file", "file_sha256", "n_duplicates")     # what read_edits adds (accepted back)
STEP = "SM"
STEP_NAME = "Removed by hand"
STEP_GROUP = "Manual edits (SM)"
STEP_SOURCE = "the user's choice (manual edits file); not an SMS step"
FLAG_EDIT, FLAG_AUTO = "Man_Edit", "Rem_Auto"
MARK_REMOVED, MARK_KEPT, MARK_NOT_APPLIED = "R", "K", "N"
KEY_SEP = "|"
KEY_FIELDS = ("machine", "dataset", "order", "time", "position")
POS_DECIMALS = 7
FIRST_N = 10
FT2_PER_AC = 43560.0
KEEP_RULE = ("a reading kept by hand is never cut by S3, S4 or S5 (any pass); it takes part in the mean and SD of "
             "every one of those steps like any reading still present, and in the SD after a cut that decides another "
             "yield pass")
REMOVE_RULE = ("a reading removed by hand leaves in step SM, after Optimize Swath Widths (S2) and before S3: it stays "
               "in the clip and the swath step as before, and the means and SDs of S3, S4 and S5 are computed without "
               "it")
# why a key is not applied: the step that cut its reading before the manual step
CUT_BEFORE = {"S0": "cut by S0, the SMS import check (no plausible position or yield, or below the import minimum)",
              "S1": "cut by S1, the clip (outside the field of interest)",
              "S1b": "cut by S1b, the repeated clip (outside the field of interest)",
              "S2": "cut by S2, Optimize Swath Widths (fully overlapped, or no swath width)"}
ASIDE = "set aside before the cleaning by the clip (outside the field of interest)"
IMPORT_LEFT_OUT = "left out by the import as SMS (outside its yield range)"


# ============================================================================================ the edits file
def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(E: dict) -> str:
    """The content of an edits file as one canonical JSON text (sorted keys and lists, no spaces): its sha256 is the
    hash of the edits whatever the layout of the file."""
    return json.dumps({k: E.get(k) for k in FILE_KEYS}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _key_list(v, name) -> tuple:
    if v is None:
        return [], 0
    if not isinstance(v, (list, tuple)):
        raise ValueError(f"manual edits: '{name}' must be a list of reading keys, not {type(v).__name__}")
    bad = [x for x in v if not isinstance(x, str) or not x]
    if bad:
        raise ValueError(f"manual edits: '{name}' holds {len(bad)} value(s) that are not reading keys (non-empty "
                         f"text), e.g. {bad[0]!r}")
    u = sorted(set(v))
    return u, len(v) - len(u)


def read_edits(src) -> dict | None:
    """The edits file (a path) or object (a dict), validated: {format, version, note, remove, keep (sorted, each key
    once), sha256 (of canonical()), file, file_sha256 (the file's bytes; None for a dict), n_duplicates (keys given
    twice in one list, counted once)}. None for None. ValueError: not an edits file, a wrong version, keys that are
    not text, or a key in both lists (named, with the first ones)."""
    if src is None:
        return None
    path, fsha = None, None
    if isinstance(src, (str, os.PathLike)):
        path = os.path.abspath(os.fspath(src))
        try:
            with open(path, "rb") as f:
                raw = f.read()
        except OSError as e:
            raise ValueError(f"manual edits: cannot read {path}: {e}") from None
        fsha = hashlib.sha256(raw).hexdigest()
        try:
            D = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ValueError(f"manual edits: {os.path.basename(path)} is not a JSON file ({e})") from None
    elif isinstance(src, dict):
        D = copy.deepcopy(src)
        path, fsha = D.get("file"), D.get("file_sha256")
    else:
        raise ValueError(f"manual edits must be a file path or a dict, not {type(src).__name__}")
    if not isinstance(D, dict):
        raise ValueError("manual edits: the file must hold one JSON object {version, remove, keep, note}")
    unknown = set(D) - set(FILE_KEYS) - set(DERIVED_KEYS)
    if unknown:
        raise ValueError(f"manual edits: unknown key(s) {sorted(unknown)}; an edits file holds {list(FILE_KEYS)}")
    if D.get("format", FORMAT) != FORMAT:
        raise ValueError(f"manual edits: format {D.get('format')!r} is not {FORMAT!r}")
    v = D.get("version")
    if isinstance(v, bool) or not isinstance(v, int) or v != VERSION:
        raise ValueError(f"manual edits: version {v!r} is not supported (this engine reads version {VERSION})")
    note = D.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError("manual edits: 'note' must be text or null")
    rem, d1 = _key_list(D.get("remove"), "remove")
    kee, d2 = _key_list(D.get("keep"), "keep")
    both = sorted(set(rem) & set(kee))
    if both:
        raise ValueError(f"manual edits: {len(both)} key(s) are in both lists, removed and kept by hand (first: "
                         + "; ".join(both[:FIRST_N]) + "). A reading is either removed or kept: correct the file")
    E = {"format": FORMAT, "version": VERSION, "note": note, "remove": rem, "keep": kee}
    E.update(sha256=_sha(canonical(E)), file=path, file_sha256=fsha, n_duplicates=int(d1 + d2))
    return E


def write_edits(path, remove=(), keep=(), note=None) -> dict:
    """Write an edits file (UTF-8, the keys sorted and each once, one key per line) and return it read back
    (read_edits). The same lists and note always give the same bytes. ValueError as read_edits (nothing written)."""
    E = read_edits({"format": FORMAT, "version": VERSION, "note": note, "remove": list(remove), "keep": list(keep)})
    path = os.path.abspath(os.fspath(path))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    text = json.dumps({k: E[k] for k in FILE_KEYS}, ensure_ascii=False, indent=1) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return read_edits(path)


def is_empty(E) -> bool:
    return E is None or (not E.get("remove") and not E.get("keep"))


def settle(S: dict) -> dict:
    """settings['manual_edits'] read and validated in place (yield_clean.merge_settings): dropped when absent, None or
    with two empty lists (the cleaning is then the automatic one, byte for byte); ValueError for a method other than
    sms3sigma (the steps are those of the SMS 3-sigma sequence)."""
    E = read_edits(S.pop(SETTING, None))
    if is_empty(E):
        return S
    if S.get("method") != "sms3sigma":
        raise ValueError(f"manual edits are a step of the SMS 3-sigma cleaning: set method 'sms3sigma' (method is "
                         f"{S.get('method')!r})")
    S[SETTING] = E
    return S


# ============================================================================================ the key of a reading
def key_columns(columns) -> dict:
    """{machine, dataset, order, time: column or None} found by name in `columns` (yield_clean.detect_columns)."""
    from engine.clean.yield_clean import detect_columns
    d = detect_columns([c for c in columns if c != "geometry"])
    return {k: d.get(k) for k in ("machine", "dataset", "order", "time")}


def _text(values) -> list:
    """Every value as text: '' for no value, a whole number as its digits, a time as pandas writes it, else str()."""
    out = []
    for v in (values.tolist() if hasattr(values, "tolist") else list(values)):
        if v is None:
            out.append("")
        elif isinstance(v, (bool, np.bool_)):
            out.append(str(bool(v)))
        elif isinstance(v, (int, np.integer)):
            out.append(str(int(v)))
        elif isinstance(v, (float, np.floating)):
            f = float(v)
            out.append("" if not math.isfinite(f) else (str(int(f)) if f.is_integer() else repr(f)))
        elif isinstance(v, pd.Timestamp):
            out.append("" if pd.isna(v) else str(v))
        else:
            s = str(v).strip()
            out.append("" if s in ("nan", "NaT", "None") else s)
    return out


def reading_keys(df, columns: dict | None = None, lonlat=None) -> tuple:
    """(keys, info): the key of every row of `df` (the attribute table of a yield file: the file the cleaning reads, or
    its flagged file) and {columns, rule, n, n_unique, n_shared, shared_first}. columns: key_columns() (default: found
    in df). lonlat: (lon, lat) arrays in WGS 84, needed only when the file has neither a record id nor a time column.
    ValueError when the readings cannot be told apart at all."""
    kc = dict(columns) if columns is not None else key_columns(df.columns)
    n = len(df)
    blank = [""] * n
    parts = [(_text(df[kc[k]]) if kc.get(k) else blank) for k in ("machine", "dataset", "order", "time")]
    use_pos = not kc.get("order") and not kc.get("time")
    if use_pos:
        if lonlat is None:
            raise ValueError("manual edits: the file has no record id and no time column, and no position was given: "
                             "its readings cannot be told apart")
        lon, lat = (np.asarray(v, float) for v in lonlat)
        pos = [(f"{a:.{POS_DECIMALS}f},{b:.{POS_DECIMALS}f}" if math.isfinite(a) and math.isfinite(b) else "")
               for a, b in zip(lon.tolist(), lat.tolist())]
    else:
        pos = blank
    keys = np.array([KEY_SEP.join(t) for t in zip(*parts, pos)], dtype=object) if n else np.array([], dtype=object)
    s = pd.Series(keys, dtype=object)
    dup = s.duplicated(keep=False).to_numpy() if n else np.zeros(0, bool)
    info = {"columns": kc, "position": bool(use_pos),
            "rule": ("machine | dataset | record id | time | position, each from its column (empty when the file has "
                     "none); the position (lon,lat WGS 84, 7 decimals) only without a record id and a time"),
            "n": int(n), "n_unique": int(s.nunique()), "n_shared": int(dup.sum()),
            "shared_first": sorted(set(keys[dup].tolist()))[:FIRST_N]}
    return keys, info


def flagged_keys(flagged) -> tuple:
    """(keys, info) of a flagged file (a path, or its table read with the columns X_log / Y_log when the position is
    needed), in the file's row order: the keys an edits file takes (the replay computes them with this function)."""
    if isinstance(flagged, (str, os.PathLike)):
        import pyogrio
        F = pyogrio.read_dataframe(os.fspath(flagged), read_geometry=False)
    else:
        F = flagged
    kc = key_columns(F.columns)
    ll = None
    if not kc.get("order") and not kc.get("time"):
        ll = (pd.to_numeric(F["X_log"], errors="coerce").to_numpy(float),
              pd.to_numeric(F["Y_log"], errors="coerce").to_numpy(float))
    return reading_keys(F, kc, ll)


def file_keys(src) -> tuple:
    """(keys, info) of every reading of the point file a cleaning reads (the import in use; a path, or that file read
    with geopandas in its own CRS), in its row order: the keys the cleaning gives the same readings (prepare(): the
    same columns; the position, when the file has neither a record id nor a time, as the flagged file's X_log / Y_log
    read back). The replay of the imported readings (step 2 of the app) marks readings with them, so a reading removed
    by hand there is the same key as in the replay of its cleaning."""
    if isinstance(src, (str, os.PathLike)):
        import geopandas as gpd
        g0 = gpd.read_file(os.fspath(src))
    else:
        g0 = src
    kc = key_columns(g0.columns)
    ll = _lonlat_of(g0) if (not kc.get("order") and not kc.get("time")) else None
    return reading_keys(g0.drop(columns="geometry") if "geometry" in g0 else g0, kc, ll)


MERGE_STAGES = ("import", "clean")


def merge_marks(E_old, marks: dict, seen, stage: str) -> dict:
    """The edits file's two lists after the marks of one replay (one edits file per harvest file, whichever replay the
    marks come from). E_old: the edits now (read_edits, or None); marks: {remove, keep} keys the replay sends (all its
    marks, those it shows of E_old included); seen: the keys of every reading of that replay; stage: 'import' (the
    replay of the imported readings, step 2: it removes or puts back, never keeps) or 'clean' (the replay of a
    cleaning). A key the replay does not show is kept as it is (a removal made in step 2 outside the boundary stays
    through every reprocess of step 3):
        remove = (old remove - seen) | the marks' removes
        keep   = (old keep - seen) | the marks' keeps        (clean)
        keep   = old keep - the marks' removes               (import: a reading removed there leaves 'keep')
    Returns {remove, keep} (sorted; never a key in both: a removal wins)."""
    if stage not in MERGE_STAGES:
        raise ValueError(f"merge_marks: stage {stage!r} is not one of {MERGE_STAGES}")
    seen = {str(k) for k in (seen or ())}
    old_r = {str(k) for k in ((E_old or {}).get("remove") or [])}
    old_k = {str(k) for k in ((E_old or {}).get("keep") or [])}
    m_r = {str(k) for k in ((marks or {}).get("remove") or [])}
    m_k = {str(k) for k in ((marks or {}).get("keep") or [])}
    if stage == "import" and m_k:
        raise ValueError("merge_marks: the replay of the imported readings removes or puts back readings, it never "
                         "keeps them by hand")
    remove = (old_r - seen) | m_r
    keep = ((old_k - seen) | m_k) if stage == "clean" else (old_k - m_r)
    return {"remove": sorted(remove), "keep": sorted(keep - remove)}


XLOG_DECIMALS = 12           # the flagged file writes X_log / Y_log (WGS 84) with 12 decimals (yield_clean.write_all)


def _lonlat_of(g0):
    """(lon, lat) of every record of the file read by the cleaning, in WGS 84, exactly as the flagged file's X_log /
    Y_log read back (the same transform, then the 12-decimal text of the file), so that a position rounded to 7
    decimals gives the same key on both sides."""
    x, y = g0.geometry.x.to_numpy(float), g0.geometry.y.to_numpy(float)
    from engine.clean.yield_clean import _is_wgs84
    crs = g0.crs
    if crs is not None and not _is_wgs84(crs):            # as write_all: reprojected unless WGS 84
        from pyproj import Transformer
        x, y = (np.asarray(v, float) for v in Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(x, y))
    rt = (lambda v: np.array([float(f"{a:.{XLOG_DECIMALS}f}") if math.isfinite(a) else a for a in v.tolist()]))
    return rt(np.asarray(x, float)), rt(np.asarray(y, float))


# ============================================================================================ matched to a cleaning
class Edits:
    """An edits file matched to the readings of one cleaning (prepare()). remove / keep: bool per reading of the
    processed set g (its order). apply() is the step SM inside sms3sigma.run_cascade."""

    def __init__(self, E, keys, info, aside_keys=(), import_keys=()):
        self.E, self.keys, self.key_info = E, keys, info
        rs, ks, kl = set(E["remove"]), set(E["keep"]), keys.tolist()      # a set lookup: linear in the readings
        self.remove = np.fromiter((k in rs for k in kl), dtype=bool, count=len(kl))
        self.keep = np.fromiter((k in ks for k in kl), dtype=bool, count=len(kl))
        present = set(keys.tolist())
        self.aside = set(aside_keys) - present
        self.import_out = set(import_keys) - present - self.aside
        self.why_before = None          # the step that removed each reading before SM ('' alive), set by apply()
        self.removed = self.kept = None

    def apply(self, alive, why, rows, log=print):
        """The step SM of run_cascade: the readings removed by hand that are still alive leave (Rem_By 'SM'); returns
        (alive, kept by hand: bool per reading, the readings S3-S5 must not cut). Appends the cascade row."""
        self.why_before = np.asarray(why, dtype=object).copy()
        rm = self.remove & alive
        why[rm] = STEP
        alive = alive & ~rm
        kp = self.keep & alive
        self.removed, self.kept = rm, kp
        crit = (f"readings removed by hand (manual edits file, {len(self.E['remove']):,} key(s)): after the swath step "
                "and before the 3-sigma filters, so their means and SDs are computed without them")
        if len(self.E["keep"]):
            crit += (f"; {int(kp.sum()):,} reading(s) kept by hand ({len(self.E['keep']):,} key(s)) are not cut by "
                     "S3-S5")
        rows.append(dict(filter=STEP, name=STEP_NAME, criterion=crit, source=STEP_SOURCE, group=STEP_GROUP,
                         attribute=None, on=True, removed=int(rm.sum()), remaining=int(alive.sum())))
        log(f"  {STEP:<4} removed {int(rm.sum()):>7,}  remaining {int(alive.sum()):>7,}  (by hand; "
            f"{int(kp.sum()):,} kept by hand)")
        return alive, kp

    # ---- per list: asked / applied / not found / not applied
    def _list_counts(self, which):
        keys_l = self.E[which]
        mask = self.remove if which == "remove" else self.keep
        applied_mask = self.removed if which == "remove" else self.kept
        present = set(self.keys[mask].tolist())
        applied_keys = set(self.keys[applied_mask].tolist())
        reasons, not_applied = {}, []
        first = {}
        for i in np.flatnonzero(mask).tolist():
            first.setdefault(self.keys[i], i)
        for k in sorted(present - applied_keys):
            step = str(self.why_before[first[k]]) if self.why_before is not None else ""
            r = CUT_BEFORE.get(step, f"cut by {step}" if step else "not alive at the manual step")
            reasons[r] = reasons.get(r, 0) + 1
            not_applied.append({"key": k, "reason": r, "step": step})
        for k in sorted(self.aside & set(keys_l)):
            reasons[ASIDE] = reasons.get(ASIDE, 0) + 1
            not_applied.append({"key": k, "reason": ASIDE, "step": "S1"})
        for k in sorted(self.import_out & set(keys_l)):
            reasons[IMPORT_LEFT_OUT] = reasons.get(IMPORT_LEFT_OUT, 0) + 1
            not_applied.append({"key": k, "reason": IMPORT_LEFT_OUT, "step": "import"})
        found = present | (self.aside & set(keys_l)) | (self.import_out & set(keys_l))
        nf = sorted(set(keys_l) - found)
        return {"asked": len(keys_l), "applied": len(applied_keys), "readings_applied": int(applied_mask.sum()),
                "not_found": len(nf), "not_found_first": nf[:FIRST_N], "not_applied": len(not_applied),
                "not_applied_reasons": reasons, "not_applied_keys": not_applied}

    def flag_values(self, why_auto):
        """(Man_Edit, Rem_Auto) per reading of g: the two columns of the flagged file of a cleaning with edits."""
        mark = np.array([""] * len(self.keys), dtype=object)
        mark[(self.remove | self.keep)] = MARK_NOT_APPLIED
        mark[self.removed] = MARK_REMOVED
        mark[self.kept] = MARK_KEPT
        return mark, np.asarray(why_auto, dtype=object).astype(str)


def prepare(E, g, g0, g_aside=None, import_record=None) -> Edits:
    """The edits file E (read_edits) matched to the cleaning: g the processed set (column _row = the record's index in
    g0), g0 every record of the file the cleaning reads, g_aside the records set aside by the clip before the cleaning,
    import_record the file's import as SMS record (its all_readings file, when it is on disk, tells the keys the
    import left out)."""
    kc = key_columns(g0.columns)
    ll = _lonlat_of(g0) if (not kc.get("order") and not kc.get("time")) else None
    keys0, info = reading_keys(g0.drop(columns="geometry"), kc, ll)
    keys = keys0[g["_row"].to_numpy(np.int64)]
    aside = keys0[g_aside["_row"].to_numpy(np.int64)].tolist() if g_aside is not None and len(g_aside) else []
    imp = []
    allr = (import_record or {}).get("all_readings") if isinstance(import_record, dict) else None
    wanted = set(E["remove"]) | set(E["keep"])
    if allr and os.path.isfile(str(allr)) and (wanted - set(keys0.tolist())):
        try:
            import geopandas as gpd
            A = gpd.read_file(str(allr))
            kca = key_columns(A.columns)
            lla = _lonlat_of(A) if (not kca.get("order") and not kca.get("time")) else None
            imp = reading_keys(A.drop(columns="geometry"), kca, lla)[0].tolist()
        except Exception:                    # a diagnostic only: the key is then reported as not found
            imp = []
    return Edits(E, keys, info, aside, imp)


# ============================================================================================ the record
def _summary(alive, in_aoi, machine, d_ft, w_ft, y):
    """{combine: {points, acres, dry_bu, yield_bu_ac}} + 'ALL' of the readings of the clean file (alive, inside)."""
    k = np.asarray(alive, bool) & (np.asarray(in_aoi, bool) if in_aoi is not None else True)
    ac = np.where(k, np.nan_to_num(d_ft * w_ft) / FT2_PER_AC, 0.0)
    bu = np.where(k, np.nan_to_num(y) * ac, 0.0)
    out = {}
    for m in list(dict.fromkeys(machine.tolist())) + ["ALL"]:
        s = k if m == "ALL" else (k & (machine == m))
        a, b = float(ac[s].sum()), float(bu[s].sum())
        out[str(m)] = {"points": int(s.sum()), "acres": a, "dry_bu": b, "yield_bu_ac": (b / a if a > 0 else None)}
    return out


def _groups(CS):
    """{group: {yield_passes, steps: [{step, attribute, n_before, mean, sd, lo, hi, removed, n_after, sd_after}]}}."""
    out = {}
    for s in CS["steps"]:
        G = out.setdefault(str(s["group"]), {"yield_passes": CS["yield_passes"].get(s["group"]), "steps": []})
        G["steps"].append({k: s.get(k) for k in ("step", "attribute", "n_before", "mean", "sd", "lo", "hi", "removed",
                                                 "n_after", "sd_after")})
    return out


def _outside(CS, gi, vals) -> str | None:
    """The first step of the cleaning CS whose limits (in the reading's group) the values lie outside, else None."""
    for s in CS["steps"]:
        if s["group"] != gi or s.get("lo") is None:
            continue
        v = vals.get(s["attribute"])
        if v is not None and math.isfinite(v) and not (s["lo"] <= v <= s["hi"]):
            return s["step"]
    return None


OTHER_RULE = ("readings in neither list whose fate differs from the automatic cleaning: the readings removed by hand "
              "leave the means and SDs of S3-S5 and the readings kept by hand stay in them, so the limits move and "
              "readings nobody picked come back, are cut, or are cut by another step")


def other_readings(M: Edits, why_auto, why_edit, machine) -> dict:
    """The readings in neither list (Man_Edit '' in the flagged file) whose fate differs from the automatic cleaning:
    came_back (cut by the automatic cleaning, kept now), newly_cut (kept by it, cut now), cut_by_another_step (cut in
    both, by another step); in total, per combine and per change ('S5b -> kept', 'kept -> S4', ...)."""
    wa = np.asarray(why_auto, dtype=object).astype(str)
    we = np.asarray(why_edit, dtype=object).astype(str)
    neither = ~(M.remove | M.keep)
    kinds = {"came_back": neither & (wa != "") & (we == ""), "newly_cut": neither & (wa == "") & (we != ""),
             "cut_by_another_step": neither & (wa != "") & (we != "") & (wa != we)}
    out = {k: int(v.sum()) for k, v in kinds.items()}
    out["total"] = int(sum(out.values()))
    ch = neither & (wa != we)
    by_m = {}
    for m in dict.fromkeys(machine[ch].tolist()):
        s = machine == m
        by_m[str(m)] = {k: int((v & s).sum()) for k, v in kinds.items()}
    by_change = {}
    for a, e in zip(wa[ch].tolist(), we[ch].tolist()):
        t = f"{a or 'kept'} -> {e or 'kept'}"
        by_change[t] = by_change.get(t, 0) + 1
    out.update(by_combine=by_m, by_change=dict(sorted(by_change.items())), rule=OTHER_RULE)
    return out


def record(M: Edits, CS: dict, CS_auto: dict, g, values: dict, plan=None) -> dict:
    """R['manual_edits']: what the edits did, beside the automatic result. CS / CS_auto: run_cascade with and without
    the edits; values: {'moisture', 'speed', 'dry yield'} arrays per reading of g (the values the steps filter)."""
    E = M.E
    machine = g["_machine"].astype(str).to_numpy(dtype=object)
    d_ft, w_ft = np.asarray(CS["dist_ft_new"], float), np.asarray(CS["width_ft_new"], float)
    ins = CS.get("in_aoi_sms")
    auto = {"combines": _summary(CS_auto["alive"], ins, machine, d_ft, w_ft, np.asarray(CS_auto["y_map"], float)),
            "groups": _groups(CS_auto)}
    edit = {"combines": _summary(CS["alive"], ins, machine, d_ft, w_ft, np.asarray(CS["y_map"], float)),
            "groups": _groups(CS)}
    by_m = {}
    for m in dict.fromkeys(machine.tolist()):
        s = machine == m
        by_m[str(m)] = {"removed_by_hand": int((M.removed & s).sum()), "kept_by_hand": int((M.kept & s).sum())}
    gkey = np.asarray(CS["group_key"]).astype(str)
    why_a = np.asarray(CS_auto["why"], dtype=object).astype(str)
    why_e = np.asarray(CS["why"], dtype=object).astype(str)
    kept_rows = []
    for i in np.flatnonzero(M.kept):
        v = {a: (float(arr[i]) if arr is not None else None) for a, arr in values.items()}
        kept_rows.append({"key": str(M.keys[i]), "combine": str(machine[i]), "group": str(gkey[i]),
                          "automatic_step": str(why_a[i]) or None, "outside_limits_of": _outside(CS, gkey[i], v),
                          "values": {a: (None if x is None or not math.isfinite(x) else round(x, 4))
                                     for a, x in v.items()}})
    rates = None
    if plan is not None and getattr(plan, "is_plan", False) and getattr(plan, "rate_col", None) and "Tgt_Rate" in g:
        r = pd.to_numeric(g["Tgt_Rate"], errors="coerce").to_numpy(float)
        lab = np.array([(f"{x:g}" if math.isfinite(x) else "outside the plots") for x in r.tolist()], dtype=object)
        rates = {}
        for L in dict.fromkeys(lab[M.removed | M.kept].tolist()):
            s = lab == L
            rates[str(L)] = {"removed_by_hand": int((M.removed & s).sum()), "kept_by_hand": int((M.kept & s).sum())}
    R = {"format": E["format"], "version": E["version"], "sha256": E["sha256"], "file": E.get("file"),
         "file_sha256": E.get("file_sha256"), "note": E.get("note"), "n_duplicates": E.get("n_duplicates", 0),
         "step": {"id": STEP, "name": STEP_NAME, "placed": "after S2 (and S1b), before S3"},
         "remove_rule": REMOVE_RULE, "keep_rule": KEEP_RULE, "key": M.key_info,
         "remove": M._list_counts("remove"), "keep": M._list_counts("keep"),
         "by_combine": by_m, "by_rate": rates,
         "by_rate_note": (None if rates is not None else "no trial design with a rate column in the field of "
                                                         "interest: no counts per rate"),
         "changes_result": bool((why_a != why_e).any()), "other_readings": other_readings(M, why_a, why_e, machine),
         "kept_by_hand": kept_rows, "automatic": auto, "edited": edit,
         "automatic_note": "the same steps on the same readings without the edits file (run in the same cleaning)"}
    return R


INTERNAL_EDIT, INTERNAL_AUTO = "_man_edit", "_rem_auto"     # their columns in the processed table g
SWATH_FUNCTIONS = ("optimize_swath", "optimize_swath_each")    # engine.clean.sms_swath, memoised by swath_once
_MEMO = threading.local()                                      # per thread: one cleaning at a time


def _same(a, b) -> bool:
    """a and b identical (arrays element by element, NaN equal to NaN; dicts, lists and tuples item by item)."""
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if not (isinstance(a, np.ndarray) and isinstance(b, np.ndarray)) or a.shape != b.shape or a.dtype != b.dtype:
            return False
        return bool(np.array_equal(a, b, equal_nan=a.dtype.kind in "fc"))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    try:
        return type(a) is type(b) and bool(a == b)
    except Exception:
        return False


def _memoised(fn):
    """fn recorded (mode 'record') or answered from the record when called with identical inputs (mode 'replay'),
    only inside swath_once in this thread; a call nested in another (optimize_swath inside optimize_swath_each) and
    every call outside swath_once go straight to fn."""
    if getattr(fn, "_oced_manual_memo", False):
        return fn

    @functools.wraps(fn)
    def w(*a, **k):
        st = getattr(_MEMO, "state", None)
        if st is None or st["depth"]:
            return fn(*a, **k)
        if st["mode"] == "replay":
            for a0, k0, res in st["calls"]:
                if _same(a0, a) and _same(k0, k):
                    st["hits"] += 1
                    return copy.deepcopy(res)
            st["misses"] += 1
        st["depth"] += 1
        try:
            res = fn(*a, **k)
        finally:
            st["depth"] -= 1
        if st["mode"] == "record":
            st["calls"].append((copy.deepcopy(a), copy.deepcopy(k), copy.deepcopy(res)))
        return res

    w._oced_manual_memo = True
    return w


@contextlib.contextmanager
def swath_once(M):
    """Around the edited cleaning and the automatic one beside it (yield_clean.clean): Optimize Swath Widths runs once,
    the automatic run takes its results when its inputs are identical. M None (no edits): nothing at all."""
    if M is None:
        yield
        return
    from engine.clean import sms_swath
    for name in SWATH_FUNCTIONS:
        if hasattr(sms_swath, name):
            setattr(sms_swath, name, _memoised(getattr(sms_swath, name)))
    _MEMO.state = {"mode": "record", "calls": [], "depth": 0, "hits": 0, "misses": 0}
    try:
        yield
    finally:
        _MEMO.state = None


def automatic_beside(M: Edits, CS: dict, run_cascade, cargs: tuple, ckw: dict, g, plan, warnings: list,
                     log=print) -> dict:
    """After the cleaning with the edits (CS): the same steps on the same readings without them (run_cascade(*cargs,
    **ckw), silent), the record (record()), its warnings appended to `warnings`, and the flagged-file marks in g
    (INTERNAL_EDIT, INTERNAL_AUTO). Returns the record (R['manual_edits'])."""
    log("  manual edits: the automatic cleaning (the same steps without the edits file), for the record ...")
    st = getattr(_MEMO, "state", None)
    if st is not None:
        st["mode"] = "replay"                # the swath step's results of the edited run (swath_once)
    CS_auto = run_cascade(*cargs, log=lambda m: None, warnings=[], notes=[], **ckw)
    if st is not None:
        log(f"  manual edits: Optimize Swath Widths taken from the edited run {st['hits']} time(s), computed again "
            f"{st['misses']} time(s)")
    arrays = cargs[3]
    moi = arrays.get("moi")
    values = {"moisture": (moi.to_numpy(float) if moi is not None else None),
              "speed": np.asarray(CS["speed_new"], float), "dry yield": np.asarray(CS["y_map"], float)}
    X = record(M, CS, CS_auto, g, values, plan)
    warnings.extend(warnings_of(X))
    g[INTERNAL_EDIT], g[INTERNAL_AUTO] = M.flag_values(CS_auto["why"])
    return X


def flagged_columns(G) -> list:
    """The flagged-file columns of a cleaning with edits ([] without: the flagged file keeps today's columns):
    Man_Edit C 1 (R / K / N / ''), Rem_Auto C 4 (the step of the automatic cleaning, '' kept)."""
    if INTERNAL_EDIT not in G:
        return []
    return [(FLAG_EDIT, "C", G[INTERNAL_EDIT].values, 1, 0), (FLAG_AUTO, "C", G[INTERNAL_AUTO].values, 4, 0)]


def _fig(v, d=2) -> str:
    return "-" if v is None else f"{float(v):,.{d}f}"


def changes_result(X) -> bool:
    """True when the edits change the cleaning (some reading has another fate than in the automatic cleaning)."""
    X = X or {}
    if "changes_result" in X:
        return bool(X["changes_result"])
    return bool((X.get("remove") or {}).get("readings_applied") or (X.get("keep") or {}).get("readings_applied"))


def title_label(R: dict) -> str:
    """The words the report's title adds: 'WITH MANUAL EDITS', 'edits file given, no change', or ''."""
    X = R.get("manual_edits")
    if not X:
        return ""
    return "WITH MANUAL EDITS" if changes_result(X) else "edits file given, no change (automatic result)"


def summary_text(R: dict) -> str:
    """One plain sentence: this cleaning includes manual edits, with the counts, the readings in neither list whose
    fate moved, and the automatic figures (or: an edits file was given and the result is the automatic one)."""
    X = R.get("manual_edits") or {}
    if not X:
        return ""
    rm, kp = X.get("remove") or {}, X.get("keep") or {}
    a = ((X.get("automatic") or {}).get("combines") or {}).get("ALL") or {}
    e = ((X.get("edited") or {}).get("combines") or {}).get("ALL") or {}
    fname = (f"edits file {os.path.basename(str(X.get('file') or 'given as an object'))}, sha256 "
             f"{str(X.get('sha256'))[:12]}")
    asked = (f"{rm.get('applied', 0):,} of {rm.get('asked', 0):,} remove key(s) and {kp.get('applied', 0):,} of "
             f"{kp.get('asked', 0):,} keep key(s) applied")
    if not changes_result(X):
        return (f"AN EDITS FILE WAS GIVEN BUT IT CHANGES NOTHING ({fname}): no reading was removed by hand and no "
                f"reading cut by the automatic cleaning was kept by hand ({asked}); the result is the automatic "
                f"cleaning: {a.get('points', 0):,} points, {_fig(a.get('acres'))} ac, {_fig(a.get('dry_bu'))} dry bu, "
                f"{_fig(a.get('yield_bu_ac'))} bu/ac")
    o = X.get("other_readings") or {}
    other = ""
    if o:
        other = (f"; {o.get('total', 0):,} other reading(s), in neither list, changed fate because the limits moved "
                 f"({o.get('came_back', 0):,} came back, {o.get('newly_cut', 0):,} newly cut, "
                 f"{o.get('cut_by_another_step', 0):,} cut by another step)")
    return (f"THIS CLEANING INCLUDES MANUAL EDITS: {rm.get('readings_applied', 0):,} reading(s) removed by hand "
            f"and {kp.get('readings_applied', 0):,} kept by hand ({asked}){other}; {fname}. "
            f"Automatic cleaning: {a.get('points', 0):,} points, {_fig(a.get('acres'))} ac, {_fig(a.get('dry_bu'))} "
            f"dry bu, {_fig(a.get('yield_bu_ac'))} bu/ac; with the edits: {e.get('points', 0):,} points, "
            f"{_fig(e.get('acres'))} ac, {_fig(e.get('dry_bu'))} dry bu, {_fig(e.get('yield_bu_ac'))} bu/ac")


def warnings_of(X: dict) -> list:
    """The warnings of a cleaning with edits (R['warnings']): the headline, the keys not found, the keys not applied."""
    out = [summary_text({"manual_edits": X})]
    for which, label in (("remove", "removed by hand"), ("keep", "kept by hand")):
        c = X[which]
        if c["not_found"]:
            out.append(f"manual edits: {c['not_found']:,} key(s) of the '{which}' list ({label}) match no reading of "
                       f"this file (first ten: {'; '.join(c['not_found_first'])}): not applied. Another field, other "
                       "raw data or other import settings give other keys")
        if c["not_applied"]:
            out.append(f"manual edits: {c['not_applied']:,} key(s) of the '{which}' list ({label}) were not applied: "
                       + "; ".join(f"{n:,} {r}" for r, n in c["not_applied_reasons"].items()))
    if X.get("n_duplicates"):
        out.append(f"manual edits: {X['n_duplicates']:,} key(s) were given twice in one list (counted once)")
    if (X.get("key") or {}).get("n_shared"):
        out.append(f"manual edits: {X['key']['n_shared']:,} readings of this file share their key with another (no "
                   "column tells them apart): an edit of such a key applies to all of them")
    return out


# ============================================================================================ the report
def report_section(story, R, num) -> int:
    """The section 'Manual edits' of the cleaning report (engine/report/clean_report.make_report); returns num + 1."""
    from reportlab.platypus import Paragraph
    from engine.report import clean_report as cr
    X = R["manual_edits"]
    e_ = cr._e
    story.append(Paragraph(f"{num}. Manual edits (readings removed or kept by hand)", cr.H2))
    story.append(Paragraph(e_(summary_text(R)) + ".", cr.WARN))
    story.append(Paragraph(e_(f"Removed by hand: {REMOVE_RULE}. Kept by hand: {KEEP_RULE}. A reading cut by the "
                              "import, the clip or the swath step cannot be kept by hand. The automatic result is the "
                              "same steps run on the same readings without the edits file, in this cleaning.")
                           + (f" Note of the edits file: {e_(X['note'])}." if X.get("note") else ""), cr.BODY))
    rows = [["List", "Keys asked", "Applied (readings)", "Not found", "Not applied (reason)"]]
    for which, label in (("remove", "removed by hand"), ("keep", "kept by hand")):
        c = X[which]
        rows.append([label, f"{c['asked']:,}", f"{c['applied']:,} ({c['readings_applied']:,})", f"{c['not_found']:,}",
                     e_("; ".join(f"{n:,} {r}" for r, n in c["not_applied_reasons"].items()) or "-")])
    story.append(cr._table(rows, [1.0 * cr.inch, 0.8 * cr.inch, 1.1 * cr.inch, 0.8 * cr.inch,
                                  cr.TEXT_W - 3.7 * cr.inch]))
    A, Ed = X["automatic"]["combines"], X["edited"]["combines"]
    rows = [["Combine", "By hand: removed / kept", "Points (auto -> edited)", "Acres", "Dry bu", "bu/ac"]]
    for m in Ed:
        h = X["by_combine"].get(m) or {}
        rows.append([e_(m), (f"{h.get('removed_by_hand', 0):,} / {h.get('kept_by_hand', 0):,}" if h else "-"),
                     f"{A[m]['points']:,} -> {Ed[m]['points']:,}",
                     f"{_fig(A[m]['acres'])} -> {_fig(Ed[m]['acres'])}", f"{_fig(A[m]['dry_bu'], 1)} -> "
                     f"{_fig(Ed[m]['dry_bu'], 1)}", f"{_fig(A[m]['yield_bu_ac'])} -> {_fig(Ed[m]['yield_bu_ac'])}"])
    story.append(cr._table(rows, [1.5 * cr.inch, 1.0 * cr.inch, 1.2 * cr.inch, 1.1 * cr.inch, 1.1 * cr.inch,
                                  cr.TEXT_W - 5.9 * cr.inch]))
    o = X.get("other_readings") or {}
    if o.get("total"):
        story.append(Paragraph(e_(f"Other readings whose fate moved ({o['total']:,}): {OTHER_RULE}. By change: "
                                  + "; ".join(f"{t} {n:,}" for t, n in o["by_change"].items()) + "."), cr.BODY))
        rows = [["Combine", "Came back", "Newly cut", "Cut by another step"]]
        for m, v in o["by_combine"].items():
            rows.append([e_(m), f"{v['came_back']:,}", f"{v['newly_cut']:,}", f"{v['cut_by_another_step']:,}"])
        story.append(cr._table(rows, [1.6 * cr.inch, 1.1 * cr.inch, 1.1 * cr.inch, 1.4 * cr.inch]))
    rows = [["Group", "Step", "Attribute", "Limits automatic", "Limits edited", "Removed (auto -> edited)"]]
    GA, GE = X["automatic"]["groups"], X["edited"]["groups"]
    from engine.report import limits_shown as lshow
    # display only: a dry-yield lower limit whose mean - k SD was negative is shown as the import minimum in force
    lim = (lambda t: lshow.range_text(t, R))
    for gname in GE:
        sa = {s["step"]: s for s in (GA.get(gname) or {}).get("steps", [])}
        for s in GE[gname]["steps"]:
            a = sa.get(s["step"]) or {}
            rows.append([e_(gname), e_(s["step"]), e_(s["attribute"]), e_(lim(a)) if a else "(no pass)", e_(lim(s)),
                         f"{a.get('removed', '-') if a else '-'} -> {s.get('removed')}"])
        for s in (GA.get(gname) or {}).get("steps", []):
            if not any(t["step"] == s["step"] for t in GE[gname]["steps"]):
                rows.append([e_(gname), e_(s["step"]), e_(s["attribute"]), e_(lim(s)), "(no pass)",
                             f"{s.get('removed')} -> -"])
    story.append(cr._table(rows, [1.5 * cr.inch, 0.5 * cr.inch, 0.8 * cr.inch, 1.3 * cr.inch, 1.3 * cr.inch,
                                  cr.TEXT_W - 5.4 * cr.inch], small=True))
    if X.get("by_rate"):
        rows = [["Rate", "Removed by hand", "Kept by hand"]]
        for r_, v in X["by_rate"].items():
            rows.append([e_(r_), f"{v['removed_by_hand']:,}", f"{v['kept_by_hand']:,}"])
        story.append(cr._table(rows, [1.6 * cr.inch, 1.3 * cr.inch, 1.3 * cr.inch]))
    story.append(Paragraph("Every key, its reading and the step that cut a reading kept by hand in the automatic "
                           "cleaning are in the cleaning record (manual_edits); the flagged file marks them in Man_Edit "
                           "(R removed, K kept, N not applied) and Rem_Auto (the automatic step).", cr.CAP))
    return num + 1
