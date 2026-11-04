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
it (a monitor card or a boundary read in place) stay absolute.

Record, version 1:
    version, name, created, updated (ISO), app_version, input_label, active
    datasets  {tag: the app's dataset dict (shp, zip relative)}
    boundary  {tag: {path, feature}}             the boundary file of each extracted file
    grower    {tag: the grower's data dict}      weight, unit, basis, moisture, test_weight, crop, std_moisture, use,
                                                 area_ac
    smsset    the SMS 3-sigma settings of the harvest panel, or None
    a3set     {tag: the 3-sigma settings of a planter / sprayer file}
    combines  {tag: the combine-factor settings (on, method, reference, max_pct, ticket_confirms)}
    cleaned   {tag: {json, shp, zip, flagged_shp, flagged_zip, report_pdf, settings, adjusted, dropped, kind, at}}
A folder written before saved works existed (decoded/ and clean/<tag>/*_cleaning.json, no oced_work.json) is listed
with legacy=True, its record rebuilt in memory from those files; nothing is written into it until it is saved.
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
                smsset=None, a3set=None, cleaned=None, app_version=None, created=None, combines=None) -> dict:
    """A record from the app's state; every path inside the work folder made relative."""
    ds = {}
    for t, D in (datasets or {}).items():
        d = {k: v for k, v in D.items() if k != "df"}
        for k in PATH_KEYS_D:
            d[k] = relpath(d.get(k), workdir)
        ds[t] = d
    bd = {t: {"path": relpath(B.get("path"), workdir), "feature": list(B.get("feature") or [])}
          for t, B in (boundary or {}).items() if B and B.get("path")}
    cl = {}
    for t, C in (cleaned or {}).items():
        c = {k: C.get(k) for k in ("settings", "adjusted", "dropped", "kind", "at")}
        for k in PATH_KEYS_C:
            c[k] = relpath(C.get(k), workdir)
        cl[t] = c
    return {"version": SCHEMA_VERSION, "name": clean_name(name) or folder_name(workdir),
            "created": created or _now(), "updated": _now(), "app_version": app_version,
            "input_label": input_label, "active": active, "datasets": ds, "boundary": bd,
            "grower": {t: dict(G) for t, G in (grower or {}).items() if G},
            "smsset": dict(smsset) if smsset else None, "a3set": {t: dict(A) for t, A in (a3set or {}).items()},
            "combines": {t: dict(c) for t, c in (combines or {}).items() if c}, "cleaned": cl}


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
    rec["datasets"] = {t: {**D, **{k: abspath(D.get(k), workdir) for k in PATH_KEYS_D}}
                       for t, D in (rec.get("datasets") or {}).items()}
    rec["boundary"] = {t: {**B, "path": abspath(B.get("path"), workdir)} for t, B in (rec.get("boundary") or {}).items()}
    rec["cleaned"] = {t: {**C, **{k: abspath(C.get(k), workdir) for k in PATH_KEYS_C}}
                      for t, C in (rec.get("cleaned") or {}).items()}
    return rec


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
    """A work folder without oced_work.json, rebuilt from its files: decoded/<tag>_decoded.shp (extracted files) and
    clean/<tag>/*_cleaning.json (cleanings, with the settings the engine received: the boundary, the grower's data,
    the SMS or 3-sigma settings). None when the folder holds neither."""
    decoded = sorted(glob.glob(os.path.join(workdir, "decoded", "*_decoded.shp")))
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
                gr[tag] = {"weight": T["value"], "unit": T.get("unit") or "lb", "basis": T.get("basis") or "wet",
                           "moisture": T.get("moisture_pct"), "test_weight": S.get("test_weight_lb_bu"),
                           "crop": S.get("crop"), "std_moisture": (S.get("moisture") or {}).get("standard_pct"),
                           "use": ("validate" if (R.get("oced") or {}).get("grower_use") == "validate" else "adjust"),
                           "area_ac": T.get("area_ac")}
            M = S.get("sms3sigma") or {}
            if M and smsset is None:
                smsset = {k: M[k] for k in ("k_sd", "group_by", "max_yield_passes", "min_yield", "clip", "swath",
                                            "speed", "moisture", "yield") if k in M}
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
    """'Trial 50 · 4 Nov 12:13 · 1 file, 1 cleaned' for the list of saved works."""
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
