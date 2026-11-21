# -*- coding: utf-8 -*-
"""Saved works: one oced_work.json per work folder, so that a work (the files extracted, their boundaries, the
grower's data, the settings and the cleanings) can be saved and opened again after the app is closed.

    from engine import works as ew
    ew.list_works(workspace)            # every work folder that can be opened, newest first
    rec = ew.load_work(workdir)         # the record of one folder (saved, else rebuilt from its files, else None)
    ew.save_work(workdir, rec)          # atomic write (tmp + os.replace)

The app (app/oced.py) builds the record from its session state (work_record) and restores the session from it
(restore_work), without running anything again: the cleaning results are read back from their cleaning JSON.
Paths are kept RELATIVE to the work folder when they lie inside it, so a moved workspace still opens; paths outside
it (a monitor card or a boundary read in place) stay absolute. That holds for the paths inside a dataset's decode
report and source too (the input folder the card was decoded from, "input_root", the decode report JSON and the
decoded shapefile), so that a reopened or moved work can still write the clean data back in the monitor's own format
(engine/formats/native_write.py). A path saved absolute that no longer exists is looked for again under the work
folder (resolve_moved), from the part that follows the work folder's own name.
A cleaning whose record was made by an older engine and lacks what the app now shows (clean_again_reason) carries
'clean_again' with the reason, so that the app can ask for a new cleaning instead of showing old numbers as new.

Record, version 1:
    version, name, created, updated (ISO), app_version, input_label, active
    inputs_left_out  the inputs left out when the work's data was opened (a damaged zip among the zips given: one
                     sentence each with the reason), [] when none; the app says them again when the work is opened
    datasets  {tag: the app's dataset dict (shp, zip relative; report.input_root and source.input_root,
                     source.decode_report, source.decoded_shp relative when inside the work folder; the default
                     import of the file, import_default {shp, n, mtime, sig, sms_import, source, basis, error, older;
                     a raw file decoded again for SMS's default also report, zip, older_decode, raw_gone}, with the
                     same paths relative, and import_mode default | custom | as_is)}
    boundary  {tag: {path, feature}}             the boundary file of each extracted file
    grower    {tag: the grower's data dict}      weight, unit, basis, moisture, test_weight, crop, std_moisture, use,
                                                 area_ac
    smsset    the SMS 3-sigma settings of the harvest panel, or None
    a3set     {tag: the 3-sigma settings of a planter / sprayer file}
    combines  {tag: the combine-factor settings (on, method, reference, max_pct, ticket_confirms)}
    cleaned   {tag: {json, shp, zip, flagged_shp, flagged_zip, report_pdf, settings, config, adjusted, dropped, kind,
                     at}}                        config: what the cleaning ran with (the app's file_config: settings,
                                                 boundary [path, fields, fingerprint], grower, combines), its boundary
                                                 path relative like the others, so that a change made after the
                                                 cleaning and saved with the work still says 'clean again'
    field_files  (0.3.7, optional; absent in older works: they open as before, without field files)
              {boundary: {path, feature, fingerprint} | None,        the field boundary given once for the work
               zones: {path, name, column, fingerprint, stamp} | None,    the work's management zone map
               use: {tag: 'own' | 'none'} (absent = the field boundary),
               feature: {tag: [polygon indices]} (the polygon of a several-field boundary file each file uses),
               found: [{path, name, kinds, n_polygons, area_ac}]}   polygon files found in the input (never applied)
    small_area  (0.3.7, optional) {tag: {path, name, rule}}  the small area kept per harvest file, measured again
                after every cleaning of it (its polygon file copied into the work, small_area/<tag>/)
A folder written before saved works existed (decoded/ and clean/<tag>/*_cleaning.json, no oced_work.json) is listed
with legacy=True, its record rebuilt in memory from those files; nothing is written into it until it is saved. Such a
record holds no inputs_left_out of its own: inputs_left_out(record) takes what its files carry (the decode reports
and the cleaning records).
Pure Python (no Streamlit), so that it can be unit-tested.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import os
import re
import tempfile

WORK_FILE = "oced_work.json"
SCHEMA_VERSION = 1
_STAMP = re.compile(r"^(\d{8})-(\d{6})_(.*)$")        # the work folder name: <YYYYmmdd-HHMMSS>_<name>
PATH_KEYS_D = ("shp", "zip")
PATH_KEYS_C = ("json", "shp", "zip", "flagged_shp", "flagged_zip", "report_pdf")
PATH_KEYS_REPORT = ("input_root",)                                  # in a dataset's decode report
PATH_KEYS_SOURCE = ("input_root", "decode_report", "decoded_shp")   # in a dataset's source (engine.run.decode_source)
PATH_KEYS_IMPORT = ("all_readings",)                                # in a dataset's sms_import record (and in
                                                                    # its default import's basis)
PATH_KEYS_DEFAULT = ("shp", "zip")                                  # in a dataset's import_default


# ================================================================================================ paths
def _norm(p: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(p))))


def relpath(path, workdir: str):
    """`path` relative to the work folder (forward slashes) when it lies inside it, else unchanged; None stays None."""
    if not path:
        return path
    p, w = _norm(path), _norm(workdir)
    if p == w or p.startswith(w + os.sep):
        return os.path.relpath(os.path.abspath(str(path)), os.path.abspath(workdir)).replace("\\", "/")
    return str(path)


def abspath(rel, workdir: str):
    """The absolute path of a relative one (relative to the work folder); an absolute path or None unchanged."""
    if not rel:
        return rel
    return str(rel) if os.path.isabs(str(rel)) else os.path.normpath(os.path.join(workdir, str(rel)))


def resolve_moved(path, workdir: str):
    """A path stored absolute that lies in another folder of this work folder's name (the work moved, or copied: an
    older record kept the paths absolute), found again under the work folder: the part of it after the work folder's
    own name (<old workspace>/<work>/input/card -> <workdir>/input/card) when that exists, even when the original is
    still there (a copy of a work reads its own files, never the folder it was copied from). Otherwise the path
    unchanged (an input read in place elsewhere stays where it was, and says so when it is gone)."""
    if not path or not os.path.isabs(str(path)):
        return path
    p, w = _norm(path), _norm(workdir)
    if p == w or p.startswith(w + os.sep):
        return path                                      # inside this work folder already
    name = os.path.basename(os.path.normpath(workdir))
    parts = re.split(r"[\\/]+", str(path))
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == name and i < len(parts) - 1:
            cand = os.path.normpath(os.path.join(workdir, *parts[i + 1:]))
            if os.path.exists(cand):
                return cand
    return path


def rebase_cleaning_files(R: dict, clean_dir: str, workdir: str) -> dict:
    """A cleaning record (its JSON, read from `clean_dir`, the folder that holds it in this work) whose paths were
    written in another folder (the work moved or copied: the JSON keeps them absolute): every path of R['files'] (the
    figures too) and of R['small_area']['files'] that lies in the folder the cleaning was written in (R['files']['dir'],
    else the folder of R['files']['json']) is put under `clean_dir`, whether that file is there or not (a file the
    copy lacks is never looked for in the folder it was copied from); any other absolute path is resolved by
    resolve_moved. In place; returns R. Nothing is written to disk (opening a work writes nothing)."""
    F = R.get("files") if isinstance(R, dict) else None
    if not isinstance(F, dict) or not clean_dir:
        return R
    old = F.get("dir") or (os.path.dirname(str(F["json"])) if F.get("json") else None)
    if not old:
        return R
    o, n = _norm(old), os.path.abspath(clean_dir)

    def fix(p):
        if not isinstance(p, str) or not p or not os.path.isabs(p):
            return p
        q = _norm(p)
        if q == o:
            return n
        if q.startswith(o + os.sep):
            return os.path.join(n, os.path.relpath(os.path.abspath(p), os.path.abspath(old)))
        return resolve_moved(p, workdir) if workdir else p

    def walk(d):
        for k, v in list(d.items()):
            if isinstance(v, dict):
                walk(v)
            elif isinstance(v, str):
                d[k] = fix(v)
    if _norm(old) == _norm(clean_dir):
        return R
    walk(F)
    SA = R.get("small_area")
    if isinstance(SA, dict) and isinstance(SA.get("files"), dict):
        walk(SA["files"])
    return R


def _paths(d, keys, fn):
    """A copy of dict d with fn applied to the values of `keys` that it holds (None stays None)."""
    if not isinstance(d, dict):
        return d
    out = dict(d)
    for k in keys:
        if out.get(k):
            out[k] = fn(out[k])
    return out


def _dataset_paths(D: dict, fn) -> dict:
    """The dataset dict with fn applied to every path it holds: shp, zip, the decode report's input folder, the
    source's input folder / decode report / decoded shapefile, the import's file of all readings, and the same paths
    of its default import (import_default: its shapefile and extracted points, the file of all readings of its basis
    and of its record, its source's paths, its decode report's input folder)."""
    d = _paths(D, PATH_KEYS_D, fn)
    if isinstance(d.get("report"), dict):
        d["report"] = _paths(d["report"], PATH_KEYS_REPORT, fn)
    if isinstance(d.get("source"), dict):
        d["source"] = _paths(d["source"], PATH_KEYS_SOURCE, fn)
    if isinstance(d.get("sms_import"), dict):
        d["sms_import"] = _paths(d["sms_import"], PATH_KEYS_IMPORT, fn)
    if isinstance(d.get("import_default"), dict):
        DF = _paths(d["import_default"], PATH_KEYS_DEFAULT, fn)
        if isinstance(DF.get("basis"), dict):
            DF["basis"] = _paths(DF["basis"], PATH_KEYS_IMPORT, fn)
        if isinstance(DF.get("sms_import"), dict):
            DF["sms_import"] = _paths(DF["sms_import"], PATH_KEYS_IMPORT, fn)
        if isinstance(DF.get("source"), dict):
            DF["source"] = _paths(DF["source"], PATH_KEYS_SOURCE, fn)
        if isinstance(DF.get("report"), dict):          # a raw file decoded again for SMS's default
            DF["report"] = _paths(DF["report"], PATH_KEYS_REPORT, fn)
        d["import_default"] = DF
    return d


def input_root(D: dict, workdir: str | None = None):
    """The input folder a dataset was decoded from (its source's, else its decode report's), absolute, found again
    under the work folder when the work was moved; None for a point export."""
    root = None
    for part in ("source", "report"):
        x = D.get(part)
        if isinstance(x, dict) and x.get("input_root"):
            root = x["input_root"]
            break
    if root and workdir:
        root = resolve_moved(abspath(root, workdir), workdir)
    return root


def inputs_left_out(rec: dict | None) -> list:
    """The inputs left out when a work's data was opened: the record's own list; a record without one (a folder
    rebuilt from its files) takes what its files carry (a dataset's 'inputs_left_out', else its decode report's)."""
    if not isinstance(rec, dict):
        return []
    if isinstance(rec.get("inputs_left_out"), list):
        return [str(w) for w in rec["inputs_left_out"]]
    out = []
    for D in (rec.get("datasets") or {}).values():
        if not isinstance(D, dict):
            continue
        rep = D.get("report") if isinstance(D.get("report"), dict) else {}
        for w in (D.get("inputs_left_out") or rep.get("inputs_left_out") or []):
            if str(w) not in out:
                out.append(str(w))
    return out


def work_path(workdir: str) -> str:
    return os.path.join(workdir, WORK_FILE)


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def folder_name(workdir: str) -> str:
    """The name part of a work folder <stamp>_<name>, else the folder name."""
    b = os.path.basename(os.path.normpath(workdir))
    m = _STAMP.match(b)
    return m.group(3) if m else b


def folder_time(workdir: str) -> str | None:
    """The ISO time of a work folder's stamp, else None."""
    m = _STAMP.match(os.path.basename(os.path.normpath(workdir)))
    if not m:
        return None
    try:
        return _dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").isoformat(timespec="seconds")
    except ValueError:
        return None


def _json_default(v):
    """numpy numbers, paths, dates and sets in a record: as JSON can hold them."""
    try:
        import numpy as np
        if isinstance(v, np.integer):
            return int(v)
        if isinstance(v, np.floating):
            return float(v)
        if isinstance(v, np.bool_):
            return bool(v)
        if isinstance(v, np.ndarray):
            return v.tolist()
    except ImportError:                                  # pragma: no cover
        pass
    if isinstance(v, (set, tuple)):
        return list(v)
    return str(v)


# ================================================================================================ save / load
def make_record(workdir: str, name: str, *, input_label=None, active=None, datasets=None, boundary=None, grower=None,
                smsset=None, a3set=None, cleaned=None, app_version=None, created=None, combines=None,
                inputs_left_out=None, field_files=None, small_area=None) -> dict:
    """A record from the app's state; every path inside the work folder made relative. field_files and small_area
    (0.3.7) are written only when the work has them (an older work's record is unchanged)."""
    ds = {}
    for t, D in (datasets or {}).items():
        d = {k: v for k, v in D.items() if k != "df"}
        if isinstance(d.get("source"), dict) and not d["source"].get("input_root") and isinstance(
                d.get("report"), dict) and d["report"].get("input_root"):
            d["source"] = {**d["source"], "input_root": d["report"]["input_root"]}   # what a writer reads first
        d = _dataset_paths(d, lambda p: relpath(p, workdir))
        for k in PATH_KEYS_D:
            d[k] = relpath(d.get(k), workdir)
        ds[t] = d
    bd = {t: {"path": relpath(B.get("path"), workdir), "feature": list(B.get("feature") or [])}
          for t, B in (boundary or {}).items() if B and B.get("path")}
    cl = {}
    for t, C in (cleaned or {}).items():
        c = {k: C.get(k) for k in ("settings", "adjusted", "dropped", "kind", "at", "clean_again")}
        for k in PATH_KEYS_C:
            c[k] = relpath(C.get(k), workdir)
        c["config"] = _config_paths(C.get("config"), lambda p: relpath(p, workdir))
        cl[t] = c
    rec = {"version": SCHEMA_VERSION, "name": clean_name(name) or folder_name(workdir),
           "created": created or _now(), "updated": _now(), "app_version": app_version,
           "input_label": input_label, "inputs_left_out": [str(w) for w in (inputs_left_out or [])],
           "active": active, "datasets": ds, "boundary": bd,
           "grower": {t: dict(G) for t, G in (grower or {}).items() if G},
           "smsset": dict(smsset) if smsset else None, "a3set": {t: dict(A) for t, A in (a3set or {}).items()},
           "combines": {t: dict(c) for t, c in (combines or {}).items() if c}, "cleaned": cl}
    ff = field_files_record(field_files, lambda p: relpath(p, workdir))
    if ff:
        rec["field_files"] = ff
    sa = {t: {"path": relpath(A.get("path"), workdir), "name": A.get("name") or os.path.basename(str(A.get("path"))),
              "rule": A.get("rule"),
              # 0.3.7: the figure, the calibration CV and the interior cut, kept only when not the default
              **{k: A[k] for k in ("method", "cv", "interior") if A.get(k) not in (None, "", 0, 0.0, "ground")}}
          for t, A in (small_area or {}).items() if A and A.get("path")}
    if sa:
        rec["small_area"] = sa
    return rec


def field_files_record(ff, fn) -> dict | None:
    """The work's field files (0.3.7) as kept in the record, fn applied to every path (relpath on save, the absolute
    path on load); None when the work has none (no boundary, no zone map, nothing found, no choice per file)."""
    if not isinstance(ff, dict):
        return None
    B, Z = ff.get("boundary"), ff.get("zones")
    out = {"boundary": ({"path": fn(B["path"]), "feature": list(B.get("feature") or []) or None,
                         "fingerprint": B.get("fingerprint")} if isinstance(B, dict) and B.get("path") else None),
           "zones": ({"path": fn(Z["path"]), "name": Z.get("name") or os.path.basename(str(Z["path"])),
                      "column": Z.get("column"), "fingerprint": Z.get("fingerprint"),
                      "stamp": list(Z.get("stamp") or []) or None} if isinstance(Z, dict) and Z.get("path") else None),
           "use": {str(t): str(u) for t, u in (ff.get("use") or {}).items() if u in ("own", "none")},
           "feature": {str(t): [int(x) for x in v] for t, v in (ff.get("feature") or {}).items() if v},
           "found": [{"path": fn(f["path"]), "name": f.get("name") or os.path.basename(str(f["path"])),
                      "kinds": list(f.get("kinds") or []), "n_polygons": f.get("n_polygons"),
                      "area_ac": f.get("area_ac")} for f in (ff.get("found") or []) if isinstance(f, dict)
                     and f.get("path")]}
    if not (out["boundary"] or out["zones"] or out["use"] or out["feature"] or out["found"]):
        return None
    return out


def save_work(workdir: str, record: dict) -> str:
    """Writes oced_work.json atomically (a temporary file, then os.replace). Returns its path."""
    os.makedirs(workdir, exist_ok=True)
    path = work_path(workdir)
    fd, tmp = tempfile.mkstemp(prefix=".oced_work_", suffix=".json", dir=workdir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, ensure_ascii=False, default=_json_default)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def load_work(workdir: str) -> dict | None:
    """The record of a work folder with absolute paths: oced_work.json when it is there, else the record rebuilt from
    the folder's files (legacy=True), else None. A record that cannot be read carries 'error'."""
    p = work_path(workdir)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError) as e:
            return {"name": folder_name(workdir), "workdir": workdir, "error": f"{type(e).__name__}: {e}",
                    "datasets": {}, "cleaned": {}, "updated": folder_time(workdir)}
        rec["legacy"] = False
    else:
        rec = legacy_record(workdir)
        if rec is None:
            return None
    return absolute(rec, workdir)


def absolute(rec: dict, workdir: str) -> dict:
    """The record with every stored path made absolute again (relative to `workdir`)."""
    rec = dict(rec)
    rec["workdir"] = workdir

    def back(p):
        return resolve_moved(abspath(p, workdir), workdir)
    rec["datasets"] = {t: _dataset_paths({**D, **{k: abspath(D.get(k), workdir) for k in PATH_KEYS_D}}, back)
                       for t, D in (rec.get("datasets") or {}).items()}
    rec["boundary"] = {t: {**B, "path": back(B.get("path"))} for t, B in (rec.get("boundary") or {}).items()}
    if rec.get("field_files"):
        rec["field_files"] = field_files_record(rec["field_files"], back)
    if rec.get("small_area"):
        rec["small_area"] = {t: {**A, "path": back(A.get("path"))} for t, A in rec["small_area"].items()
                             if isinstance(A, dict) and A.get("path")}
    rec["cleaned"] = {t: {**C, **{k: back(C.get(k)) for k in PATH_KEYS_C},
                          "config": _config_paths(C.get("config"), lambda p: os.path.abspath(back(p)))}
                      for t, C in (rec.get("cleaned") or {}).items()}
    return rec


def _config_paths(cfg, fn):
    """A cleaning's config (the app's file_config) with fn applied to its boundary path (config['boundary'][0]);
    None (a work saved before configs were kept, or a cleaning without one) stays None."""
    if not isinstance(cfg, dict):
        return None
    out = dict(cfg)
    b = out.get("boundary")
    if isinstance(b, (list, tuple)) and b and b[0]:
        out["boundary"] = [fn(b[0])] + list(b[1:])
    return out


# ================================================================================================ older records
def no_width_readings_at_s2(R: dict, flagged_shp: str | None = None) -> int | None:
    """The readings logged with a swath width of 0 (or less) that reached S2 of an SMS 3-sigma cleaning record R
    (kept, or removed by S2 or a later step), counted in its flagged file (flagged_shp, else R['files']['flagged_shp']:
    every reading inside the boundary with its logged width and Rem_By). 0 when S2 did not run or the cleaning had no
    width column (nothing for the S2 rule of revision 3 to change); None when the flagged file cannot be read."""
    rows = [c for c in (R.get("cascade") or []) if isinstance(c, dict) and c.get("filter") == "S2"]
    wcol = (R.get("columns") or {}).get("width_ft")
    if not rows or not rows[0].get("on") or not wcol:
        return 0
    paths = [p for p in (flagged_shp, (R.get("files") or {}).get("flagged_shp")) if p]
    p = next((q for q in paths if os.path.isfile(q)), None)
    try:
        import numpy as np
        import pyogrio
        g = pyogrio.read_dataframe(p, columns=[wcol, "Rem_By"], read_geometry=False)
        w = np.asarray(g[wcol], dtype=float)
        rem = g["Rem_By"].fillna("").astype(str).str.strip()
    except Exception:
        return None
    return int((np.isfinite(w) & (w <= 0) & ~rem.isin(["S0", "S1"]).to_numpy()).sum())


def file_order_changed(R: dict, flagged_shp: str | None = None) -> bool | None:
    """Whether this engine's S2 would take the readings of an SMS 3-sigma cleaning record R in another order than the
    one R was made with, from method revision 4 (engine/clean/sms3sigma.py FILE_ORDER_REVISION: a point file without
    a time per reading in the file's own row order; swath_order 'file' = the file's own row order for every file).
    True when S2 ran and took its readings in another order than the file's own rows: the setting 'file' over a time
    per reading; or, without a time per reading, the setting 'file', or 'auto' on a point file (its import record)
    that is not an SMS export of GreenStar 4 data, whose rows were not already in the order S2 took (dataset start,
    then record id: yield_clean.export_order), read from its flagged file (the readings in the file's own row order;
    flagged_shp, else the one R names). False when nothing changes; None when the flagged file cannot be read."""
    rows = [c for c in (R.get("cascade") or []) if isinstance(c, dict) and c.get("filter") == "S2"]
    if not rows or not rows[0].get("on"):
        return False
    from engine.clean import sms3sigma as sms
    M = R.get("sms3sigma") or {}
    P = M.get("settings") if isinstance(M.get("settings"), dict) else {}
    mode = str(P.get("swath_order") or "auto").strip().lower()
    timed = str((R.get("order") or {}).get("basis") or "") == "time"
    if mode == "file" and timed:
        return True
    if mode not in ("auto", "file") or timed or (mode == "auto" and not sms.point_import(R.get("sms_import"))):
        return False
    cols = R.get("columns") or {}
    dcol, ocol = cols.get("dataset"), cols.get("order")
    if not dcol:
        return False                          # no dataset column: S2 took the file's row order already
    paths = [p for p in (flagged_shp, (R.get("files") or {}).get("flagged_shp")) if p]
    p = next((q for q in paths if os.path.isfile(q)), None)
    try:
        import numpy as np
        import pyogrio
        from engine.clean import yield_clean as yc
        g = pyogrio.read_dataframe(p, columns=[c for c in (dcol, ocol) if c] + ["Rem_By"], read_geometry=False)
        names = g[dcol].astype(str)
        if mode == "auto" and names.str.contains(sms.GS4_NAME_RE).any():
            return False                      # an SMS export of GreenStar 4 data: its files are re-chained as before
        if ocol:
            old = yc.export_order(g, dcol, ocol)
        else:                                 # file order, then S2 put the datasets in the order of their dates
            ts = names.map(sms.dataset_start).to_numpy(float)
            old = np.argsort(ts, kind="stable") if np.isfinite(ts).all() else np.arange(len(g))
    except Exception:
        return None
    reached = ~g["Rem_By"].fillna("").astype(str).str.strip().isin(["S0", "S1"]).to_numpy()
    seq = old[reached[old]]                   # the file rows that reached S2, in the order S2 took them
    return bool((np.diff(seq) < 0).any())


def clean_again_reason(R: dict | None, flagged_shp: str | None = None) -> str | None:
    """Why a harvest cleaning record (the engine's cleaning JSON) must be made again before the app shows it, or None:
    a grower's weight compared by an engine older than the combine-factor totals (R['level'] without
    'monitor_total_final_bu': the verdict and the factor in the file would be read from the wrong total), an SMS
    3-sigma cleaning of the method's revision 1 (R['sms3sigma'] without 'method_revision': speed filtered before
    moisture and one mean and SD per task, engine/clean/sms3sigma.py METHOD_REVISION), whose steps the app would
    otherwise label in the current order, or one of revision 2 whose S2 met readings logged with a swath width of 0
    (it kept them; from revision 3 S2 removes them, which changes every later step): counted in its flagged file
    (flagged_shp, else the one the record names; no_width_readings_at_s2), or one of revision 3 or earlier whose S2
    order changes from revision 4 (a point file without a time per reading now in the file's own row order:
    file_order_changed); when the flagged file cannot be read the cleaning is not taken as unchanged."""
    if not isinstance(R, dict):
        return None
    lv = R.get("level")
    if isinstance(lv, dict) and lv and "monitor_total_final_bu" not in lv:
        return ("made by an older version (the grower's weight was compared before the combine factor totals were "
                "kept): clean it again")
    M = R.get("sms3sigma")
    if isinstance(M, dict) and M and "method_revision" not in M:
        return ("settings changed: made by an older version of the SMS 3-sigma method (speed filtered before moisture, "
                "one mean and SD per task): clean it again")
    if isinstance(M, dict) and M:
        from engine.clean.sms3sigma import NO_WIDTH_REVISION
        try:
            rev = int(M.get("method_revision") or 0)
        except (TypeError, ValueError):
            rev = 0
        if rev < NO_WIDTH_REVISION:
            n = no_width_readings_at_s2(R, flagged_shp)
            if n is None:
                return ("settings changed: made by an older version of the SMS 3-sigma method, whose S2 kept the "
                        "readings logged with a swath width of 0 (S2 now removes them), and its flagged file could "
                        "not be read to tell whether this file had any: clean it again")
            if n:
                return (f"settings changed: made by an older version of the SMS 3-sigma method, whose S2 kept the {n:,} "
                        "reading(s) logged with a swath width of 0 (S2 now removes them, which changes the later "
                        "steps): clean it again")
        from engine.clean.sms3sigma import FILE_ORDER_REVISION
        if rev < FILE_ORDER_REVISION:
            ch = file_order_changed(R, flagged_shp)
            if ch is None:
                return ("settings changed: made by an older version of the SMS 3-sigma method, whose S2 took the "
                        "readings of a file without a time per reading in the order of its datasets (S2 now takes "
                        "the file's own row order), and its flagged file could not be read to tell whether this "
                        "changes the order: clean it again")
            if ch:
                return ("settings changed: made by an older version of the SMS 3-sigma method, whose S2 took the "
                        "readings in another order (S2 now takes a point file without a time per reading in the "
                        "file's own row order, as SMS holds it; swath_order 'file' is the file's own row order): "
                        "clean it again")
    return None


# ================================================================================================ older folders
def _read_json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _n_points(shp: str) -> int:
    try:
        import pyogrio
        return int(pyogrio.read_info(shp)["features"])
    except Exception:
        return 0


def legacy_record(workdir: str) -> dict | None:
    """A work folder without oced_work.json, rebuilt from its files: decoded/<tag>_decoded.shp (extracted files; a
    raw file an older version decoded with a product and decoded again for SMS's default by 0.3.1 has its readings in
    sms_default/decoded/<tag>_decoded.shp, taken before decoded/'s) and clean/<tag>/*_cleaning.json (cleanings, with the
    settings the engine received: the boundary, the grower's data, the SMS or 3-sigma settings). None when the folder
    holds neither."""
    by_tag = {}
    for sub in (("decoded",), ("sms_default", "decoded")):     # the second wins for the same tag
        for shp in glob.glob(os.path.join(workdir, *sub, "*_decoded.shp")):
            by_tag[os.path.basename(shp)[:-len("_decoded.shp")]] = shp
    decoded = sorted(by_tag.values(), key=os.path.basename)
    cleanings = sorted(glob.glob(os.path.join(workdir, "clean", "*", "*_cleaning.json")))
    if not decoded and not cleanings:
        return None
    ds, bd, gr, a3s, cl, smsset = {}, {}, {}, {}, {}, None
    for shp in decoded:
        tag = os.path.basename(shp)[:-len("_decoded.shp")]
        z = shp[:-4] + ".zip"
        rp = shp[:-len("_decoded.shp")] + "_decode_report.json"
        rep = _read_json(rp) if os.path.exists(rp) else None
        n = _n_points(shp)
        # the decoder's account (crop, test weight, standard moisture, shrink, units): clean(source=...) reads it, and
        # it changes the cleaning (the 3-sigma groups follow the tasks), so it is rebuilt from the decode report
        src = None
        if isinstance(rep, dict):
            try:
                from engine.run import decode_source
                src = decode_source({"report": rep, "df": None, "n": n, "report_json": rp, "shp": shp})
            except Exception:
                src = None
        if isinstance(src, dict) and isinstance(rep, dict) and rep.get("input_root"):
            src["input_root"] = rep["input_root"]        # the input folder the card was decoded from
        ds[tag] = {"tag": tag, "shp": shp, "zip": z if os.path.exists(z) else None, "n": n, "kind": "raw",
                   "op": "harvest", "yield": True, "label": tag.replace("_", " "), "source": src,
                   "report": rep if isinstance(rep, dict) else None,
                   "area_ac": ((rep or {}).get("totals") or {}).get("area_ac") if isinstance(rep, dict) else None,
                   "units": list((rep or {}).get("unit_labels") or []) if isinstance(rep, dict) else []}
    for js in cleanings:
        R = _read_json(js)
        if not isinstance(R, dict):
            continue
        tag = os.path.basename(os.path.dirname(js))
        a3 = "operation" in R and "sms3sigma" not in R
        F = R.get("files") or {}
        S = R.get("settings") or {}
        src = R.get("input") or F.get("input")
        if tag not in ds and src and os.path.exists(src):
            ds[tag] = {"tag": tag, "shp": src, "zip": None, "n": int(R.get("n_read") or R.get("n_in_file") or 0),
                       "kind": "export", "op": (R.get("operation") if a3 else "harvest") or "harvest", "yield": not a3,
                       "label": os.path.basename(src), "source": None, "report": None, "area_ac": None, "units": []}
        if tag not in ds:
            continue
        if isinstance(R.get("source"), dict) and R["source"].get("kind") == "decoded":
            ds[tag]["source"] = R["source"]              # what the cleaning itself received
        if R.get("inputs_left_out") and not ds[tag].get("inputs_left_out"):
            # the inputs left out when the data was opened, as the cleaning recorded them (inputs_left_out below)
            ds[tag]["inputs_left_out"] = [str(w) for w in R["inputs_left_out"]]
        if a3:
            b = R.get("boundary") or {}
            if b.get("file"):
                bd[tag] = {"path": b["file"], "feature": _features(b.get("feature"))}
            a3s[tag] = {k: S.get(k) for k in ("attributes", "repeat", "min_value", "k_sd", "max_passes", "group_by",
                                               "clip") if k in S}
            shp = F.get("clean_shp")
        else:
            A = S.get("aoi") or {}
            if A.get("file"):
                bd[tag] = {"path": A["file"], "feature": _features(A.get("feature"))}
            T = S.get("scale_ticket") or {}
            if T.get("value"):
                # the grower's own bushel weight and use are in the ticket since the grower's-weight engine; an older
                # record has them only as the import's bushel weight and the app's 'grower_use'
                use = T.get("use") or ("validate" if (R.get("oced") or {}).get("grower_use") == "validate"
                                       else "adjust")
                tw = T["test_weight_lb_bu"] if "test_weight_lb_bu" in T else S.get("test_weight_lb_bu")
                gr[tag] = {"weight": T["value"], "unit": T.get("unit") or "lb", "basis": T.get("basis") or "wet",
                           "moisture": T.get("moisture_pct"), "test_weight": tw,
                           "crop": S.get("crop"), "std_moisture": (S.get("moisture") or {}).get("standard_pct"),
                           "use": use if use in ("adjust", "validate") else "adjust", "area_ac": T.get("area_ac")}
            M = S.get("sms3sigma") or {}
            if M and smsset is None:
                # only the keys the record holds: an older record without filter_order restores without it (the app
                # then says to clean it again), never with a default put in here
                smsset = {k: M[k] for k in ("k_sd", "group_by", "max_yield_passes", "min_yield", "filter_order",
                                            "swath_bias", "swath_scope", "swath_passes", "clip", "swath", "speed",
                                            "moisture", "yield") if k in M}
            shp = F.get("difm_ready_shp")
        # the clean shapefile the app hands out: clean_shapefiles/<the engine's clean file name>
        cshp = os.path.join(workdir, "clean_shapefiles", os.path.basename(shp)) if shp else None
        if not cshp or not os.path.exists(cshp):
            cshp = shp
        cl[tag] = {"json": js, "shp": cshp, "zip": (cshp[:-4] + ".zip") if cshp else None,
                   "flagged_shp": F.get("flagged_shp"), "flagged_zip": F.get("flagged_zip"),
                   "report_pdf": F.get("report_pdf"), "settings": None,
                   "adjusted": (not a3) and "Yld_Level" in (R.get("difm_ready_added_columns") or []),
                   "dropped": list((R.get("oced") or {}).get("columns_left_out") or []),
                   "kind": "a3" if a3 else "sms",
                   "at": _dt.datetime.fromtimestamp(os.path.getmtime(js)).strftime("%H:%M:%S")}
        fl = F.get("flagged_shp")
        if fl and not os.path.exists(fl):                # a folder moved since: its flagged file beside the record
            fl = os.path.join(os.path.dirname(js), os.path.basename(fl))
        why = None if a3 else clean_again_reason(R, fl)
        if why:
            cl[tag]["clean_again"] = why
    if not ds:
        return None
    t0 = folder_time(workdir)
    return {"version": SCHEMA_VERSION, "name": folder_name(workdir), "created": t0, "updated": t0,
            "app_version": None, "input_label": None, "active": next(iter(cl), next(iter(ds))), "datasets": ds,
            "boundary": bd, "grower": gr, "smsset": smsset, "a3set": a3s, "cleaned": cl, "legacy": True}


def _features(f):
    if f is None:
        return []
    return [int(x) for x in (f if isinstance(f, (list, tuple)) else [f])]


# ================================================================================================ listing
def list_works(workspace: str) -> list[dict]:
    """Every work folder of the workspace that can be opened, newest first: {workdir, name, updated, n_files,
    n_cleaned, legacy, error}. Folders with nothing extracted are left out."""
    out = []
    for wd in glob.glob(os.path.join(workspace, "*")):
        if not os.path.isdir(wd):
            continue
        try:
            rec = load_work(wd)
        except Exception as e:                           # a broken folder must not hide the others
            rec = {"name": folder_name(wd), "error": f"{type(e).__name__}: {e}", "datasets": {}, "cleaned": {},
                   "updated": folder_time(wd)}
        if rec is None:
            continue
        out.append({"workdir": wd, "name": rec.get("name") or folder_name(wd),
                    "updated": rec.get("updated") or folder_time(wd) or "", "n_files": len(rec.get("datasets") or {}),
                    "n_cleaned": len(rec.get("cleaned") or {}), "legacy": bool(rec.get("legacy")),
                    "error": rec.get("error")})
    out.sort(key=lambda r: (r["updated"] or "", r["workdir"]), reverse=True)
    return out


def work_label(w: dict) -> str:
    """'My field · 1 Jan 12:00 · 1 file, 1 cleaned' for the list of saved works."""
    when = ""
    if w.get("updated"):
        try:
            when = _dt.datetime.fromisoformat(w["updated"]).strftime("%d %b %H:%M")
        except ValueError:
            when = str(w["updated"])
    nf, nc = int(w.get("n_files") or 0), int(w.get("n_cleaned") or 0)
    s = f"{w.get('name')} · {when} · {nf} file" + ("s" if nf != 1 else "") + f", {nc} cleaned"
    return s + (" · older work" if w.get("legacy") else "") + (" · unreadable" if w.get("error") else "")


def clean_name(name) -> str:
    """A work name as typed, trimmed and without control characters (empty -> '')."""
    s = re.sub(r"[\x00-\x1f]", " ", str(name or "")).strip()
    return s[:80]
