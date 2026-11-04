# -*- coding: utf-8 -*-
"""One API from the user's files to the clean shapefile; used by the Streamlit app and by the command line.

    python -m engine.run <file|folder|zip> [more ...] --out <dir> [--crop C] [--units all|id,id] [--field NAME]
                         [--year Y] [--allow-mixed] [--settings s.json] [--boundary FILE]
                         [--scale-ticket VALUE --ticket-unit lb|kg|bu|t --ticket-basis wet|dry --ticket-moisture PCT]
                         [--scale-ticket-bu BU] [--aoi FILE] [--reference-machine ID] [--machine-total VIN=BU ...]
                         [--factor-method auto|cells|track|point|machine]
                         [--standard-moisture PCT] [--shrink auto|one_sided|symmetric] [--candidate N] [--list]

    from engine import run
    cands = run.open_input(["harvest.zip"], "work")                    # what is in the input
    dec = run.decode(cands[0], None, None, "work")                   # raw candidate -> standard point shapefile
    R = run.clean(dec["shp"], "work/output", {"scale_ticket": {"value": 1500000, "unit": "lb"}})
    R["files"]["difm_ready_zip"]                                      # the upload; R["level"]["factor"] is L

Grower's weight (scale ticket). settings["scale_ticket"] = {"value", "unit" (lb | kg | bu | t), "basis" (wet | dry),
"moisture_pct", "note"} is the weight the grower got for the field; the cleaning converts it to bushels with the test
weight (settings.test_weight_lb_bu > the file's own median Yld_Mass_W / Yld_Vol_We > the crop table), levels the map
to it (L = ticket / monitor total; Yld_Level and Yld_Lvl_Sy = the leveled dry yields) and, with several combines, uses
it as a closure test for a paired factor above max_factor (R["machines"]["ticket_test"]). The legacy scale_ticket_bu
stays an alias (unit bu). ticket_conversion() below is the same conversion for the app's caption and the CLI, and
compat_settings() translates the dict to scale_ticket_bu for a cleaning engine that does not know it yet.

The input is either a yield POINT export (Ag Leader SMS, John Deere Operations Center) or a raw monitor dataset
(engine/formats: Case IH / New Holland .cn1 card, John Deere .jdl logs, John Deere GreenStar 3 .fdd/.fdl card). A raw
dataset is first decoded into the standard schema of engine/formats/common.py (the SMS / Ops Center column names and
units), written as a point shapefile, and from then on cleaned exactly like an export by engine/clean/yield_clean.py.
So the clean file has the same columns whatever the source, and the column to map is Yld_Vol_Dr (or
Yld_Harm when several combines were harmonised; Yld_Level when a scale ticket levels the map).

Work folder layout (one per run; the app makes workspace/<YYYYmmdd-HHMMSS>_<tag>/):
    input/     uploaded files and every zip unpacked (folders on this computer are read in place, not copied); when
               the folder is reused (the CLI's --out) each call unpacks into a new input_2/, input_3/ ... and detects
               only what that call unpacked, so an earlier run's input is never picked up again
    decoded/   <tag>_decoded.shp(+.zip) and <tag>_decode_report.json  (raw inputs only: all readings, uncleaned)
    output/    the cleaning outputs (yield_clean.run): <tag>_clean.zip, report PDF, flagged points, JSON, figures

One file per field and season: decode() refuses units of more than one field, crop or season (the cleaning and the overlap
filter expect one harvest: seasons on top of each other look like overlap and make the automatic F8 meaningless)
unless allow_mixed=True, and then records a warning. The CLI picks the units as the app does: --field (exact name first,
else a substring) restricted to that field's latest season unless --year is given; without --field, the field with
the most records among the pre-selected (latest-season) units.

Field of interest (AOI): a boundary or trial-design polygon file (read_plan; engine/clean/aoi.py when present) can
define the field instead of the monitor's field names, which are unreliable on cards with many fields. With an AOI the
app measures, per unit of the latest season, the share of its readings inside the AOI + 50 m (units_inside_aoi: every
unit is decoded once and its positions cached in workdir/decoded/aoi_cache/), pre-selects the units with >= 20 % inside
and hides those with < 1 %; mixed_units(..., aoi=True) then no longer refuses several monitor fields (the AOI defines
the field) but still refuses mixed crops and seasons. The AOI goes to the cleaning as settings["aoi"]["file"]
(clip before the cascade, output clip, Plot_Id / Tgt_Rate columns, in-plot F8 dose-response: engine/clean/yield_clean.py).

Settings compatibility: clean() passes the settings through unchanged when the cleaning engine knows the v2 keys
(crop, aoi, moisture, machines); with an engine that lacks them (compat_settings) aoi.file becomes the old 'boundary'
and machines.harmonise the old 'harmonise_machines', the other v2 keys are dropped and each drop is logged.

Nothing here changes a number of the decoders or of the cleaning: the decoders keep their own vendor conventions
(detect.default_options: one-sided shrink, the convention of SMS / Ops Center measured in docs/formats/*.md) unless
the caller overrides them, and every warning of the decoder and of the cleaning is passed on: clean(..., source=
decode_result) copies the decoder's warnings and the decoder / units / calibration into the cleaning JSON and PDF.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import json
import os
import sys
import traceback
import zipfile

import numpy as np
import pandas as pd

from engine.formats import common, detect
from engine.clean import yield_clean

__version__ = "2.6.1"
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHP_EXTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


# ================================================================================================ work folders
def new_workdir(base: str, tag: str) -> str:
    """base/<YYYYmmdd-HHMMSS>_<tag>/ with input/, decoded/ and output/ (a numeric suffix if the name exists)."""
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    t = yield_clean.sanitise_tag(tag)[:40] or "run"
    d = os.path.join(os.path.abspath(base), f"{stamp}_{t}")
    i = 2
    while os.path.exists(d):
        d = os.path.join(os.path.abspath(base), f"{stamp}_{t}_{i}")
        i += 1
    for sub in ("input", "decoded", "output"):
        os.makedirs(os.path.join(d, sub))
    return d


def free_output_dir(workdir: str) -> str:
    """workdir/output, or output_2, output_3 ... when the previous one already holds a run (one folder per run, so
    the fixed-name figures of two runs never overwrite each other)."""
    d = os.path.join(workdir, "output")
    i = 2
    while os.path.isdir(d) and os.listdir(d):
        d = os.path.join(workdir, f"output_{i}")
        i += 1
    os.makedirs(d, exist_ok=True)
    return d


def zip_files(paths, zpath: str) -> str:
    """Zip the existing files of `paths` (flat, no folders) into zpath."""
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if os.path.exists(p):
                z.write(p, os.path.basename(p))
    return zpath


# ================================================================================================ input
def free_input_dir(workdir: str) -> str:
    """workdir/input, or input_2, input_3 ... when the previous one already holds files (a reused work folder)."""
    d = os.path.join(workdir, "input")
    i = 2
    while os.path.isdir(d) and os.listdir(d):
        d = os.path.join(workdir, f"input_{i}")
        i += 1
    os.makedirs(d, exist_ok=True)
    return d


def open_input(paths, workdir: str, copy_folders: bool = False, log=print) -> detect.Candidates:
    """Unpack `paths` into a fresh workdir/input (free_input_dir: zips recursively; folders read in place unless
    copy_folders) and detect what is there, under the roots of THIS call only. Returns detect.Candidates (a list;
    .notes and .message for the user)."""
    roots = detect.unpack(paths, free_input_dir(workdir), copy_folders=copy_folders, log=log)
    c = detect.detect(roots)
    c.roots = list(roots)              # kept for the saved field (engine/fields.py): detect(roots) reopens the input
    prepare_candidates(c, workdir, log=log)
    for x in c:
        log("found: " + x["label"])
    for n in c.notes:
        log("note: " + n)
    if c.message:
        log(c.message)
    return c


def prepare_candidates(cands, workdir: str, log=print):
    """Mark the Ops Center section-element exports among cands (engine.formats.ops_sections: one point per header
    element and second): "sections" True and a label that says so. Cheap (a sample of the records); the collapse
    itself waits for use_candidate, so that a zip of several large exports only collapses the one chosen."""
    from engine.formats import ops_sections
    for x in cands:
        if x.get("kind") != "export" or x.get("source_path"):
            continue
        try:
            if ops_sections.is_section_export(x["path"]):
                x["sections"] = True
                x["label"] = (f"Point export · {os.path.basename(x['path'])} · {x['n']:,} section points (one per "
                              "header element and second: read as one reading per combine and second)")
        except Exception as e:          # reported, never fatal: the export is read as it is
            cands.notes.append(f"{os.path.basename(x['path'])}: section check failed ({type(e).__name__}: {e})")


def use_candidate(cand: dict, workdir: str, log=print) -> dict:
    """The candidate ready to read: a section-element export (prepare_candidates) is collapsed to its per-second
    readings once per work folder, into workdir/sections/<stem>_per_second.shp (made again when the source is newer),
    and the candidate points at that file ("source_path" keeps the export). Updates cand in place and returns it."""
    if not cand.get("sections") or cand.get("source_path"):
        return cand
    from engine.formats import ops_sections
    import pyogrio
    src = cand["path"]
    out = os.path.join(workdir, "sections", os.path.splitext(os.path.basename(src))[0] + "_per_second.shp")
    if not (os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src)):
        log(f"{os.path.basename(src)}: one point per header section, collapsing to one reading per second ...")
        ops_sections.collapse(src, out, log=log)
    info = pyogrio.read_info(out)
    n = int(info["features"])
    cand.update({"source_path": src, "path": os.path.abspath(out), "n": n, "columns": list(info["fields"]),
                 "label": f"Point export · {os.path.basename(src)} · {cand['n']:,} section points → {n:,} readings "
                          "(one per combine and second)"})
    return cand


def list_units(candidate: dict) -> list:
    """The selectable units (common.Unit) of a raw candidate."""
    if candidate.get("kind") != "raw":
        raise ValueError("only a raw monitor dataset has units to choose")
    return detect.decoder(candidate["decoder"]).list_units(candidate["probe"].root)


def candidate_tag(candidate: dict, units=None) -> str:
    """A short output name: the export's file stem, or '<field>_<year>' of the chosen units (else the format id)."""
    if candidate.get("kind") == "export":
        return yield_clean.sanitise_tag(os.path.splitext(os.path.basename(candidate["path"]))[0]) or "yield"
    units = units or []
    fields = sorted({u.field for u in units if u.field})
    years = sorted({u.year for u in units if u.year})
    parts = [fields[0] if len(fields) == 1 else (f"{len(fields)}fields" if fields else candidate["decoder"])]
    if years:
        parts.append(str(years[-1]) if len(years) == 1 else f"{years[0]}-{years[-1]}")
    return yield_clean.sanitise_tag("_".join(parts))[:60] or candidate["decoder"]


# ================================================================================================ decode
def mixed_units(units, aoi: bool = False) -> list[str]:
    """What makes a selection of units more than one harvest: several fields, crops or seasons ([] = one harvest).
    aoi=True: a field of interest defines the field, so several monitor field names are not a mix (the monitor's
    field names are unreliable on cards with many fields); crops and seasons are still checked."""
    out = []
    fields = sorted({u.field or "(no field)" for u in units})
    crops = sorted({str(u.crop).strip().lower() for u in units if str(u.crop or "").strip()})
    years = sorted({int(u.year) for u in units if u.year})
    if len(fields) > 1 and not aoi:
        out.append(f"{len(fields)} fields ({', '.join(fields)})")
    if len(crops) > 1:
        out.append(f"{len(crops)} crops ({', '.join(crops)})")
    if len(years) > 1:
        out.append(f"{len(years)} seasons ({', '.join(map(str, years))})")
    return out


def select_units(units, field: str | None = None, year: int | None = None, ids=None, everything: bool = False):
    """The units the CLI decodes, chosen as the app does. ids: explicit unit ids (after the field / year filter);
    everything: every unit (after the filter). Otherwise one harvest: --field keeps that field (exact name, case-
    insensitive, else a substring) and its latest season unless `year` is given; without `field`, the pre-selected
    (latest-season) units of the field with the most records. Returns (units, note)."""
    sel, note = list(units), ""
    if field:
        exact = [u for u in sel if (u.field or "").strip().lower() == field.strip().lower()]
        sel = exact or [u for u in sel if field.strip().lower() in (u.field or "").lower()]
    if year:
        sel = [u for u in sel if u.year == year]
    if ids is not None:
        ids = list(ids)
        have = {u.id for u in sel}
        bad = [w for w in ids if w not in have]
        if bad:
            raise ValueError(f"unit id(s) not available (after --field/--year): {bad}")
        return [u for u in sel if u.id in ids], note
    if everything or not sel:
        return sel, note
    if field and not year:
        last = max((u.year for u in sel if u.year), default=None)
        if last is not None:
            sel = [u for u in sel if u.year == last]
            note = f"latest season of the field: {last} (another one with --year)"
    elif not field:
        pool = [u for u in sel if u.default] or sel
        rec = {}
        for u in pool:
            rec[u.field or ""] = rec.get(u.field or "", 0) + int(u.n_records or 0)
        best = max(sorted(rec), key=lambda f: rec[f])
        sel = [u for u in pool if (u.field or "") == best]
        if len(rec) > 1:
            note = (f"field {best or '(no field)'!r} (most records of the {len(rec)} fields pre-selected; another one "
                    "with --field, all with --units all --allow-mixed)")
    return sel, note


def decode_source(dec: dict) -> dict:
    """What clean(source=...) records about a decoded input: decoder, units, crop / test weight / standard moisture /
    shrink, the decoder's options and warnings, and where the decode report is."""
    rep = dec["report"]
    cal = rep.get("calibration") or {}
    df = dec.get("df")
    parts = []

    def vals(v):
        if isinstance(v, dict):
            v = list(v.values())
        if isinstance(v, (list, tuple, set)):
            v = sorted({str(x) for x in v if x is not None})
            return ", ".join(v)
        return "" if v is None else str(v)
    crop = vals(cal.get("crop"))
    if not crop and df is not None and len(df):
        crop = ", ".join(sorted(df["Product"].astype(str).unique())[:5])
    tw = vals(cal.get("test_weight_lb_bu"))
    if not tw and df is not None and len(df):
        r = (df.Yld_Mass_W / df.Yld_Vol_We).replace([np.inf, -np.inf], np.nan).dropna()
        tw = f"{r.median():.2f}" if len(r) else ""
    sm = vals(cal.get("std_moisture_pct"))
    units_cal = cal.get("units")
    if isinstance(units_cal, list) and units_cal and isinstance(units_cal[0], dict):
        crop = crop or vals([u.get("crop_used") for u in units_cal])
        tw = vals([u.get("test_weight_lb_bu") for u in units_cal]) or tw
        sm = sm or vals([u.get("std_moisture_pct") for u in units_cal])
    if crop:
        parts.append(f"crop {crop}")
    if tw:
        parts.append(f"test weight {tw} lb/bu")
    if sm:
        parts.append(f"standard moisture {sm} %")
    parts.append(f"shrink {rep['options']['shrink'].replace('_', '-')}")
    if rep.get("decoder_kwargs"):
        parts.append("decoder options " + ", ".join(f"{k} = {v}" for k, v in rep["decoder_kwargs"].items()))
    ch = cal.get("mass_channel") or cal.get("channel")
    if ch:
        parts.append(f"mass channel: {str(ch)[:160]}")
    return {"kind": "decoded", "format": rep.get("format"), "label": rep.get("label"),
            "units": list(rep.get("unit_labels") or []), "calibration_summary": "; ".join(parts),
            "options": rep.get("options"), "decoder_kwargs": rep.get("decoder_kwargs"), "totals": rep.get("totals"),
            "n_readings": dec.get("n"), "decode_report": dec.get("report_json"), "decoded_shp": dec.get("shp"),
            "time_basis": rep.get("time_basis"),                      # "UTC" | "local" | "unknown" (sessions: the day)
            "tz_offset_h": (rep.get("options") or {}).get("tz_offset_h"),
            "warnings": list(rep.get("warnings") or [])}


def decode(candidate: dict, unit_ids, opts: common.DecodeOptions | None, workdir: str, log=print, tag: str | None = None,
           allow_mixed: bool = False, aoi: bool = False, **decoder_kwargs) -> dict:
    """Decode the chosen units of a raw candidate and write workdir/decoded/<tag>_decoded.shp (+ .zip, + report JSON).

    unit_ids None = the decoder's pre-selected units (Unit.default). opts None = detect.default_options (the vendor's
    convention). decoder_kwargs go to the decoder (cnh_cn1: calibration; jd_gs3_rcd: flow_delay_s, moisture_delay_s).
    Units of more than one field, crop or season (mixed_units) raise ValueError unless allow_mixed, which records a
    warning instead; aoi=True (a field of interest is given) lets several monitor field names through. Returns {shp, zip, report, report_json, tag, n, df, source}; raises ValueError for user-fixable
    problems. Pass the result's 'source' to clean() so that the cleaning JSON / PDF carry the decoder's warnings."""
    if candidate.get("kind") != "raw":
        raise ValueError("decode() takes a raw monitor candidate; an export goes straight to clean()")
    fid = candidate["decoder"]
    mod = detect.decoder(fid)
    root = candidate["probe"].root
    units = mod.list_units(root)
    by_id = {u.id: u for u in units}
    if unit_ids is None:
        unit_ids = [u.id for u in units if u.default]
    unit_ids = list(unit_ids)
    if not unit_ids:
        raise ValueError("no unit selected: choose at least one task / machine / load to decode")
    unknown = [u for u in unit_ids if u not in by_id]
    if unknown:
        raise ValueError(f"unknown unit id(s) {unknown[:5]}; ids are {list(by_id)[:10]} ...")
    opts = opts if opts is not None else detect.default_options(fid)
    chosen = [by_id[u] for u in unit_ids]
    mixed = mixed_units(chosen, aoi=aoi)
    if mixed and not allow_mixed:
        raise ValueError("the selected units are more than one harvest: " + "; ".join(mixed) + ". The cleaning and the "
                         "overlap filter expect one field, one crop and one season per file: select the units of one "
                         "harvest (CLI: --field / --year), or allow mixing explicitly (--allow-mixed)")
    tag = yield_clean.sanitise_tag(tag) if tag else candidate_tag(candidate, chosen)
    log(f"decoding {len(unit_ids)} unit(s) with {mod.LABEL} (shrink {opts.shrink}, crop "
        f"{opts.crop or 'from the monitor'})")
    try:
        df, rep = mod.decode(root, unit_ids, opts, log=log, **decoder_kwargs)
    except KeyError as e:                          # a decoder's unknown-unit KeyError -> the app's error path
        raise ValueError(f"decoder error: {e}") from None
    if df is None or not len(df):
        raise ValueError("the selected units hold no yield readings (header down, moving, with grain flow)")
    rep = dict(rep)
    rep["warnings"] = list(rep.get("warnings") or [])
    rep["label"] = rep.get("label") or mod.LABEL
    rep["format"] = rep.get("format") or fid
    if mixed:
        rep["warnings"].append("units of more than one harvest decoded together (allowed explicitly): "
                               + "; ".join(mixed) + ". The cleaning expects one field, crop and season per file")
    rep["options"] = dataclasses.asdict(opts)
    rep["decoder_kwargs"] = dict(decoder_kwargs)
    rep["unit_labels"] = [u.label for u in chosen]
    rep["input_root"] = root
    d = os.path.join(workdir, "decoded")
    os.makedirs(d, exist_ok=True)
    crop_key = opts.crop if (opts.crop in common.CROPS) else None
    if crop_key is None:
        # one crop for the whole file only when every unit names the same known crop: a mixed decode with a crop the
        # decoder cannot name (Trial 25: canola + 'crop 47') labelled every record with the known one
        used = [str(u.get("crop_used")).strip().lower() if u.get("crop_used") else None
                for u in ((rep.get("calibration") or {}).get("units") or []) if isinstance(u, dict)]
        crop_key = used[0] if used and len(set(used)) == 1 and used[0] in common.CROPS else None
    shp = common.write_standard(df, os.path.join(d, f"{tag}_decoded.shp"), extra={"Crop": crop_key})
    stem = os.path.splitext(shp)[0]
    zpath = zip_files([stem + e for e in SHP_EXTS], stem + ".zip")
    rj = os.path.join(d, f"{tag}_decode_report.json")
    with open(rj, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, default=_json_default)
    log(f"decoded {len(df):,} readings -> {shp}")
    out = {"shp": shp, "zip": zpath, "report": rep, "report_json": rj, "tag": tag, "n": int(len(df)), "df": df}
    out["source"] = decode_source(out)
    return out


def _json_default(v):
    if dataclasses.is_dataclass(v):
        return dataclasses.asdict(v)
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, float) and not np.isfinite(v):
        return None
    return str(v)


# ================================================================================================ clean
V2_SETTING_KEYS = ("crop", "aoi", "moisture", "machines")   # the v2 settings (shared spec, section 1)


def engine_knows_v2() -> bool:
    """True when the cleaning engine's DEFAULT_SETTINGS hold every v2 key (crop, aoi, moisture, machines)."""
    return all(k in yield_clean.DEFAULT_SETTINGS for k in V2_SETTING_KEYS)


# ------------------------------------------------------------------------------------------------ grower's weight
TICKET_UNITS = ("lb", "kg", "bu", "t")
LB_PER_KG = 2.20462262185
LB_PER_UNIT = {"lb": 1.0, "kg": LB_PER_KG, "t": 1000.0 * LB_PER_KG}       # bu needs the test weight
TICKET_DEFAULT = {"value": None, "unit": "lb", "basis": "wet", "moisture_pct": None, "note": None}
UNIT_LABEL = {"lb": "lb", "kg": "kg", "bu": "bu", "t": "t"}


def engine_knows_ticket() -> bool:
    """True when the cleaning engine's DEFAULT_SETTINGS hold the v2 'scale_ticket' dict."""
    return "scale_ticket" in yield_clean.DEFAULT_SETTINGS


def ticket_settings(settings: dict | None) -> dict | None:
    """The grower's weight of a settings dict as the v2 dict {value, unit, basis, moisture_pct, note}, or None when
    no ticket is given: settings['scale_ticket'] when its value is set, else the legacy scale_ticket_bu (unit bu,
    basis scale_ticket_basis). Raises ValueError for a bad unit / basis / value."""
    S = settings or {}
    t = S.get("scale_ticket")
    if isinstance(t, dict) and t.get("value") is not None:
        out = {**TICKET_DEFAULT, **{k: t.get(k) for k in TICKET_DEFAULT if k in t}}
    elif S.get("scale_ticket_bu"):
        out = {**TICKET_DEFAULT, "value": S["scale_ticket_bu"], "unit": "bu",
               "basis": S.get("scale_ticket_basis") or "wet"}
    else:
        return None
    try:
        out["value"] = float(out["value"])
    except (TypeError, ValueError):
        raise ValueError(f"scale_ticket.value must be a number, not {out['value']!r}") from None
    if not np.isfinite(out["value"]) or out["value"] <= 0:
        raise ValueError(f"scale_ticket.value must be a positive weight, not {out['value']!r}")
    out["unit"] = str(out.get("unit") or "lb").strip().lower()
    if out["unit"] not in TICKET_UNITS:
        raise ValueError(f"scale_ticket.unit must be one of {', '.join(TICKET_UNITS)}, not {out['unit']!r}")
    out["basis"] = str(out.get("basis") or "wet").strip().lower()
    if out["basis"] not in ("wet", "dry"):
        raise ValueError(f"scale_ticket.basis must be 'wet' or 'dry', not {out['basis']!r}")
    if out.get("moisture_pct") is not None:
        out["moisture_pct"] = float(out["moisture_pct"])
        if not 0 <= out["moisture_pct"] < 100:
            raise ValueError(f"scale_ticket.moisture_pct must be a percentage, not {out['moisture_pct']!r}")
        if out["basis"] == "dry":
            raise ValueError("scale_ticket.moisture_pct only applies to the wet basis (a dry-basis weight is already at "
                             "the standard moisture): drop it or give the weight with basis 'wet'")
    return out


def file_test_weight(shp: str) -> float | None:
    """The file's own test weight: median(Yld_Mass_W / Yld_Vol_We) of a standard-schema point file (lb/bu); None when
    either column is missing or the ratio cannot be read."""
    try:
        import pyogrio
        fields = list(pyogrio.read_info(shp)["fields"])
        if "Yld_Mass_W" not in fields or "Yld_Vol_We" not in fields:
            return None
        df = pyogrio.read_dataframe(shp, columns=["Yld_Mass_W", "Yld_Vol_We"], read_geometry=False)
        r = (pd.to_numeric(df.Yld_Mass_W, errors="coerce") / pd.to_numeric(df.Yld_Vol_We, errors="coerce"))
        r = r.replace([np.inf, -np.inf], np.nan).dropna()
        r = r[r > 0]
        return float(r.median()) if len(r) else None
    except Exception:
        return None


def ticket_conversion(ticket: dict | None, test_weight: float | None = None, shp: str | None = None,
                      crop: str | None = None, file_tw: float | None = None) -> dict | None:
    """The grower's weight in every unit, for the caption of the app, the CLI summary and the compat path:
    {value, unit, basis, moisture_pct, lb, bu, test_weight, test_weight_source, text, error}. The test weight is
    `test_weight` (settings.test_weight_lb_bu) > the file's own ratio (file_tw, or read from shp) > the crop table
    (engine.formats.common.CROPS) > error "give test_weight_lb_bu". bu = lb / test weight; a ticket already in bu
    needs no test weight (lb is then given only when one is known). ticket None -> None."""
    t = ticket_settings({"scale_ticket": ticket}) if isinstance(ticket, dict) else None
    if t is None:
        return None
    tw, src = None, None
    if test_weight:
        tw, src = float(test_weight), "test weight given"
    else:
        ftw = file_tw if file_tw is not None else (file_test_weight(shp) if shp else None)
        if ftw:
            tw, src = float(ftw), "test weight from the file"            # median Yld_Mass_W / Yld_Vol_We
        elif crop and str(crop).lower() in common.CROPS:
            tw, src = float(common.CROPS[str(crop).lower()][0]), f"test weight of the crop table: {str(crop).lower()}"
    out = {**t, "lb": None, "bu": None, "test_weight": tw, "test_weight_source": src, "text": "", "error": None}
    v, u = t["value"], t["unit"]
    if u == "bu":
        out["bu"] = v
        out["lb"] = v * tw if tw else None
        out["text"] = (f"= {out['lb']:,.0f} lb at {tw:.2f} lb/bu ({src})" if tw else
                       "(bushels as given: no conversion needed)")
        return out
    out["lb"] = v * LB_PER_UNIT[u]
    if not tw:
        out["error"] = ("no test weight to convert the weight to bushels (the file has no Yld_Mass_W / Yld_Vol_We and "
                        "no crop is set): give test_weight_lb_bu")
        out["text"] = f"{v:,.0f} {u}" + (f" = {out['lb']:,.0f} lb" if u != "lb" else "") + "; " + out["error"]
        return out
    out["bu"] = out["lb"] / tw
    out["text"] = (f"= {out['bu']:,.1f} bu at {tw:.2f} lb/bu ({src})" if u == "lb" else
                   f"= {out['lb']:,.0f} lb = {out['bu']:,.1f} bu at {tw:.2f} lb/bu ({src})")
    return out


def ticket_label(ticket: dict | None) -> str:
    """'1,500,000 lb' / '9,000 bu' for the tree row and the summaries ('' without a ticket)."""
    t = ticket if (isinstance(ticket, dict) and ticket.get("value")) else None
    if not t:
        return ""
    return yield_clean.ticket_value_text(float(t["value"]), str(t.get("unit") or "lb"))


def compared_ticket_bu(L: dict):
    """The bushels the engine compared the monitor total with: the ticket brought to the standard moisture when the
    ticket's moisture was applied (ticket_compared_bu / ticket_bu_at_standard), else the ticket in bu (None without)."""
    if L.get("ticket_bu_at_standard") is not None:
        return L.get("ticket_compared_bu", L["ticket_bu_at_standard"])
    return L.get("ticket_bu", L.get("scale_ticket_bu"))


def level_factor_text(L: dict) -> str:
    """'0.9975 (before the combine harmonisation 0.9481)' / '1.1099': the level applied to the columns (factor_final)
    first, the pre-harmonisation factor only when a combine factor changed it."""
    f = L.get("factor")
    ff = L.get("factor_final")
    if ff is None:
        ff = L.get("factor_harmonised", f)
    if ff is None:
        return "-"
    s = f"{float(ff):.4f}"
    if f is not None and abs(float(ff) - float(f)) > 1e-9:
        s += f" (before the combine harmonisation {float(f):.4f})"
    return s


def level_caption(R: dict) -> str:
    """'monitor 38,613 bu vs scale 36,608 bu (-5.2 %)' from R['level'] ('' without a level). With a wet ticket plus its
    moisture the scale figure is the ticket at the standard moisture, the one L and the closure use: 'monitor 7,749 bu
    vs scale S bu (+12.4 %; the ticket at 12 % = S bu at 14.5 %)'."""
    L = R.get("level") or {}
    if not L:
        return ""
    mon = L.get("export_total_bu", L.get("export_integral_bu"))
    tick = compared_ticket_bu(L)
    f = L.get("factor")
    if mon is None or tick is None:
        return f"level factor {f:.4f}" if f is not None else ""
    s = f"monitor {float(mon):,.0f} bu vs scale {float(tick):,.0f} bu ({100 * (float(tick) / float(mon) - 1):+.1f} %"
    if L.get("ticket_bu_at_standard") is not None and L.get("ticket_bu") is not None:
        ms = (R.get("moisture") or {}).get("standard_pct")
        s += (f"; {float(L['ticket_bu']):,.0f} bu at {float(L['ticket_moisture_pct']):g} % = {float(tick):,.0f} bu"
              + (f" at {float(ms):g} %" if ms is not None else " at the standard moisture"))
    s += ")"
    if L.get("ticket_unit") and L.get("ticket_unit") != "bu" and L.get("ticket_value") is not None:
        s += f"; the scale said {ticket_label({'value': L['ticket_value'], 'unit': L['ticket_unit']})}"
        if L.get("test_weight_used"):
            s += f" at {float(L['test_weight_used']):.2f} lb/bu"
    return s


def enrich_level(R: dict, settings: dict | None, shp: str | None = None) -> dict:
    """Compat only: with a cleaning engine that does not report the v2 ticket keys, add to R['level'] the ticket in
    its unit (ticket_value, ticket_unit, ticket_lb, ticket_bu, test_weight_used, test_weight_source) from the
    settings' conversion and a closure dict {monitor_total_bu, ticket_bu, diff_pct, after_harmonisation_bu,
    diff_after_pct, verdict} from the numbers the engine did report. Keys the engine wrote are never overwritten."""
    L = R.get("level")
    if not isinstance(L, dict):
        return R
    t = ticket_settings(settings)
    if t is not None and "ticket_bu" not in L:
        conv = ticket_conversion(t, test_weight=(settings or {}).get("test_weight_lb_bu"), shp=shp,
                                 crop=(settings or {}).get("crop"))
        L.update(ticket_value=t["value"], ticket_unit=t["unit"], ticket_basis=t["basis"],
                 ticket_moisture_pct=t.get("moisture_pct"), ticket_lb=conv.get("lb"),
                 ticket_bu=(conv.get("bu") if conv.get("bu") is not None else L.get("scale_ticket_bu")),
                 test_weight_used=conv.get("test_weight"), test_weight_source=conv.get("test_weight_source"))
    if "closure" not in L and L.get("export_total_bu") and L.get("scale_ticket_bu"):
        mon, tick = float(L["export_total_bu"]), float(L.get("ticket_bu") or L["scale_ticket_bu"])
        after = L.get("export_total_harmonised_bu")
        c = {"monitor_total_bu": mon, "ticket_bu": tick, "diff_pct": 100 * (mon / tick - 1),
             "after_harmonisation_bu": after, "diff_after_pct": (100 * (float(after) / tick - 1) if after else None)}
        d = c["diff_after_pct"] if c["diff_after_pct"] is not None else c["diff_pct"]
        c["verdict"] = (f"the monitor total is {d:+.2f} % from the scale" + (" after the combine harmonisation" if after else "")
                        + ("; L is a small calibration step" if abs(d) <= 3 else
                           "; check the ticket coverage before trusting L" if abs(d) > 10 else
                           "; the monitor needs recalibration (> 3 %)"))
        L["closure"] = c
    return R


def compat_settings(settings: dict | None, shp: str | None = None) -> tuple[dict, list[str]]:
    """(settings for this engine, notes). With an engine that knows the v2 keys the settings pass through unchanged
    (a deep copy). Otherwise the v2 keys are translated to what the old engine understands: aoi.file -> boundary
    (level diagnostics only), machines.harmonise -> harmonise_machines; crop, moisture and the other aoi / machines
    options are dropped, one note per drop (the caller logs them as warnings). Independently of that, with an engine
    that lacks settings['scale_ticket'] the grower's weight is converted to bushels (ticket_conversion with `shp` for
    the file's test weight) and passed as the legacy scale_ticket_bu / scale_ticket_basis, with a note; the ticket's
    moisture cannot be used by such an engine (noted)."""
    import copy
    S = copy.deepcopy(settings or {})
    notes = []
    if "scale_ticket" in S and not engine_knows_ticket():
        t = ticket_settings({"scale_ticket": S.pop("scale_ticket")})
        if t is not None:
            conv = ticket_conversion(t, test_weight=S.get("test_weight_lb_bu"), shp=shp, crop=S.get("crop"))
            if conv.get("bu"):
                S["scale_ticket_bu"] = float(conv["bu"])
                S["scale_ticket_basis"] = t["basis"]
                notes.append(f"cleaning engine without settings['scale_ticket']: the grower's weight {ticket_label(t)} "
                             f"{conv['text']} was passed as scale_ticket_bu (no Yld_Lvl_Sy column, no closure test)")
                if t.get("moisture_pct") is not None:
                    notes.append("cleaning engine without settings['scale_ticket']: the ticket moisture "
                                 f"{t['moisture_pct']:g} % is ignored (the ticket is compared on the {t['basis']} basis)")
            else:
                notes.append(f"the grower's weight {ticket_label(t)} was dropped: {conv.get('error')}")
    if engine_knows_v2():
        return S, notes
    known = set(yield_clean.DEFAULT_SETTINGS)
    aoi = S.pop("aoi", None)
    if isinstance(aoi, dict) and aoi.get("file"):
        if "boundary" in known and not S.get("boundary"):
            S["boundary"] = aoi["file"]
            notes.append("cleaning engine without the field-of-interest step: the AOI file is used as the level "
                         "boundary only (no clip, no Plot_Id / Tgt_Rate columns)")
        else:
            notes.append("cleaning engine without the field-of-interest step: settings['aoi'] ignored")
    mach = S.pop("machines", None)
    if isinstance(mach, dict):
        if "harmonise" in mach and "harmonise_machines" in known and "harmonise_machines" not in S:
            S["harmonise_machines"] = bool(mach["harmonise"])
        rest = sorted(k for k in mach if k != "harmonise")
        if rest:
            notes.append("cleaning engine without the v2 machine options: machines." + ", machines.".join(rest)
                         + " ignored (paired-cell harmonisation of v1 used)")
    for k in ("crop", "moisture"):
        if k in S:
            S.pop(k)
            notes.append(f"cleaning engine without settings['{k}']: ignored")
    return S, notes


def clean(shp: str, out_dir: str, settings: dict | None = None, log=print, source: dict | None = None) -> dict:
    """The cleaning (engine/clean/yield_clean.run): returns its result dict; R['files']['difm_ready_zip'] is the
    clean file and R['yield_column_for_difm'] the column to map. R['advice'] lists the plain checks
    (yield_clean.advice; also in the JSON and PDF). source: decode()['source'] for a decoded raw dataset.
    The settings go through unchanged (compat_settings only translates them for an engine without the v2 keys and
    logs every translation as a warning, which is also appended to R['warnings'])."""
    S, notes = compat_settings(settings, shp=shp)
    for n in notes:
        log("WARNING: " + n)
    R = yield_clean.run(shp, out_dir, S, log=log, source=source)
    if notes:
        R.setdefault("warnings", []).extend(notes)
    enrich_level(R, settings, shp=shp)
    for a in R["advice"]:
        log("CHECK: " + a)
    return R


def advice(R: dict) -> list[str]:
    """The plain checks on a cleaning result (yield_clean.advice; written into the cleaning JSON and PDF too)."""
    return yield_clean.advice(R)


def recommended_yield_column(R: dict) -> tuple[str, str]:
    """(yield column to map, reason). Yld_Vol_Dr (the mapped dry yield) by default; Yld_Harm when a combine factor
    was applied (R['machines']['factor_applied'] has a value other than 1); Yld_Dry_Sy when the sessions diagnostic
    recommends the symmetric dry basis and the column was written to the clean file: the engine says so with
    R['dry_symmetric_column_for_difm'], else R['sessions']['recommendation'] (a dict with map_column / text / reasons,
    or a string naming Yld_Dry_Sy) is read and the column checked against R['difm_ready_added_columns'] when that list
    exists. Priority when both apply: the combine factor wins (Yld_Dry_Sy carries no combine factor, so mapping it
    would undo a proven harmonisation); the reason then says the symmetric basis was recommended too and Harv_Day
    stays the block. The engine's own choice (R['yield_column_for_difm']) is the starting point so that renamed
    clashes (Yld_Harm_2 ...) are respected.

    With a grower's weight (R['level'] and a leveled column in the clean file) the leveled column is the "real"
    yield and wins over everything: Yld_Lvl_Sy (= Yld_Dry_Sy x factor x L) when the sessions recommend the symmetric
    basis and that column was written, else Yld_Level (= mapped dry yield x factor x L); the reason names the ticket
    in its unit and L ("leveled to the grower's weight 1,500,000 lb (L = 0.948): the bu/ac now sum to the scale")."""
    col = R.get("yield_column_for_difm") or "Yld_Vol_Dr"
    ch = ((R.get("sms3sigma") or {}).get("difm_ready_changes") or {}) if R.get("method") == "sms3sigma" else {}
    reason = ("the dry yield as SMS exports it after Optimize Swath Widths"
              + (" (scaled to the optimised area on the narrowed or shortened points)"
                 if int(ch.get("n_scaled_points") or 0) else " (no reading was rescaled)")
              if R.get("method") == "sms3sigma" else "the dry yield as the monitor mapped it")
    lev = leveled_column(R)
    if lev:
        return lev
    if R.get("method") == "sms3sigma":
        # as in SMS: the export's own dry yield (scaled by Optimize Swath Widths); the symmetric column is offered,
        # never preferred (SMS maps Yld_Vol_Dr; the sessions recommendation is an OCCD diagnostic)
        wants, why = sessions_want_symmetric(R)
        if wants and "Yld_Dry_Sy" in (R.get("difm_ready_added_columns") or []):
            reason += ("; the harvest sessions / moisture basis would recommend the symmetric dry yield Yld_Dry_Sy "
                       "(also in the file, scaled the same way)" + (f": {why}" if why else ""))
        return col, reason
    mach = R.get("machines") or {}
    fa = mach.get("factor_applied") or {}
    applied = [m for m, f in fa.items() if f is not None and abs(float(f) - 1.0) > 1e-12]
    harm_wins = bool(applied) and str(col).startswith("Yld_Harm")
    if harm_wins:
        reason = (f"several combines: a harmonisation factor was applied to {', '.join(map(str, applied))} "
                  "(1 for the reference and for every combine whose difference was not proven)")
    ses = R.get("sessions") or {}
    rec = ses.get("recommendation")
    if isinstance(rec, dict):
        wants_sym = str(rec.get("map_column") or "").startswith("Yld_Dry_Sy") or "Yld_Dry_Sy" in str(rec.get("text", ""))
        why = "; ".join(str(x) for x in (rec.get("reasons") or [])) or str(rec.get("text") or "")
    else:
        wants_sym = "Yld_Dry_Sy" in str(rec or "") or bool(ses.get("recommend_symmetric"))
        why = str(rec or "")
    sym_col = R.get("dry_symmetric_column_for_difm")
    if not sym_col and wants_sym:
        written = R.get("difm_ready_added_columns")
        if written is None or "Yld_Dry_Sy" in written:
            sym_col = "Yld_Dry_Sy"
    if sym_col and harm_wins:
        reason += (f"; the harvest sessions / moisture basis also recommend the symmetric dry-matter yield ({sym_col}"
                   f"{': ' + why if why else ''}), but that column carries no combine factor: map {col} and keep "
                   "Harv_Day as a block in the analysis")
    elif sym_col:
        col = sym_col
        reason = ("the harvest sessions / moisture basis recommend the symmetric dry-matter yield"
                  + (f": {why}" if why else "") + "; keep Harv_Day as a block in the analysis")
    return col, reason


def sessions_want_symmetric(R: dict) -> tuple[bool, str]:
    """(the sessions diagnostic recommends the symmetric dry basis, its reasons) from R['sessions']['recommendation']
    (a dict with map_column / text / reasons, or a string naming Yld_Dry_Sy)."""
    ses = R.get("sessions") or {}
    rec = ses.get("recommendation")
    if isinstance(rec, dict):
        wants = str(rec.get("map_column") or "").startswith("Yld_Dry_Sy") or "Yld_Dry_Sy" in str(rec.get("text", ""))
        why = "; ".join(str(x) for x in (rec.get("reasons") or [])) or str(rec.get("text") or "")
    else:
        wants = "Yld_Dry_Sy" in str(rec or "") or bool(ses.get("recommend_symmetric"))
        why = str(rec or "")
    return bool(wants), why


def leveled_column(R: dict) -> tuple[str, str] | None:
    """(column, reason) of the leveled yield when a grower's weight leveled the map and the column is in the
    clean file: Yld_Lvl_Sy when the sessions recommend the symmetric basis and it was written (the engine's
    R['level_symmetric_column_for_difm'] names a renamed clash), else Yld_Level (R['level_column_for_difm']). None
    without a level or when no leveled column reached the clean file."""
    L = R.get("level")
    if not isinstance(L, dict) or not L:
        return None
    added = R.get("difm_ready_added_columns")
    lvl = R.get("level_column_for_difm") or "Yld_Level"
    sym = R.get("level_symmetric_column_for_difm") or (
        "Yld_Lvl_Sy" if (added is not None and "Yld_Lvl_Sy" in added) else None)
    wants, why = sessions_want_symmetric(R)
    sms = R.get("method") == "sms3sigma"                 # as in SMS: the leveled SMS yield, never the symmetric one
    if sym and wants and not sms and (added is None or sym in added):
        col = sym
        basis = "the symmetric dry-matter yield" + (f" ({why})" if why else "") + " x factor x L"
    elif added is None or lvl in added:
        col = lvl
        basis = ("the dry yield scaled by Optimize Swath Widths x L" if sms else "the mapped dry yield x factor x L")
        if sym and wants and not sms:
            basis += f" ({sym} was recommended but not written)"
    else:
        return None
    f = L.get("factor_final")
    if f is None and not L.get("per_machine"):
        f = L.get("factor_harmonised", L.get("factor"))
    tick = ticket_label({"value": L.get("ticket_value", L.get("scale_ticket_bu")), "unit": L.get("ticket_unit", "bu")})
    if L.get("difm_note") and str(L["difm_note"]).startswith(col):
        # the engine's own sentence for the column it wrote (the same numbers; one wording in JSON, PDF and app)
        reason = str(L["difm_note"]).split("=", 1)[1].strip() if "=" in str(L["difm_note"]) else str(L["difm_note"])
    else:
        reason = (f"leveled to the grower's weight {tick}"
                  + (f" (L = {float(f):.3f})" if f is not None else (" (per-machine L)" if L.get("per_machine") else ""))
                  + f": the bu/ac now sum to the scale; {basis}")
    if (R.get("sessions") or {}).get("table"):
        reason += "; keep Harv_Day as a block in the analysis"
    return col, reason


def difm_note(R: dict) -> str:
    """The clean file and which yield column to map, for the CLI summary."""
    col, reason = recommended_yield_column(R)
    s = (f"Upload {os.path.basename(R['files']['difm_ready_zip'])} as the yield data and map the yield to "
         f"{col} ({reason})")
    if R.get("level_column_for_difm") and leveled_column(R) is None:
        s += (f"; to work on the scale-ticket level map {R['level_column_for_difm']} instead (level factor "
              f"{R['level']['factor']:.4f})")
    elif leveled_column(R) is not None:
        L = R["level"]
        mon = L.get("export_total_bu", L.get("export_integral_bu"))
        s += (f". {col} is the real level: the file keeps the monitor's columns"
              + (f" (monitor total {float(mon):,.0f} bu)" if mon is not None else "")
              + " and adds the leveled ones (Yld_Level"
              + (", Yld_Lvl_Sy" if "Yld_Lvl_Sy" in (R.get("difm_ready_added_columns") or []) else "") + ")")
    if R.get("method") == "sms3sigma":
        ch = (R.get("sms3sigma") or {}).get("difm_ready_changes") or {}
        wcol = ch.get("width_column") or "Wdth_Opt"
        added = R.get("difm_ready_added_columns") or ch.get("added") or []
        hw = (R.get("settings") or {}).get("harvester_width_ft")
        raw = ("the original width is in Wdth_Raw" if "Wdth_Raw" in added else
               "the export has no width column: the optimised width is the added column Wdth_Opt and the logged width "
               "was the constant harvester width" + (f" {float(hw):g} ft" if hw is not None else ""))
        n_nar, n_scl, n_sh = (int(ch.get(k) or 0) for k in ("n_narrowed_points", "n_scaled_points",
                                                            "n_shortened_points"))
        if n_nar or n_scl or n_sh:
            s += (f". As in an SMS export after Optimize Swath Widths, {wcol} holds the optimised width on the "
                  f"{n_nar:,} narrowed points and the per-area columns are multiplied by old / new area (Swath_Scl) on "
                  f"the {n_scl:,} narrowed or shortened points"
                  + (f" (the {n_sh:,} shortened ones also carry the new Distance and Speed)" if n_sh else "")
                  + f" (map {wcol} as the swath width; {raw})")
        else:
            s += (f". Optimize Swath Widths changed no reading: {wcol} and the per-area columns are as logged (map "
                  f"{wcol} as the swath width; {raw})")
    extras = []
    if (R.get("sessions") or {}).get("table"):
        extras.append("Harv_Day (calendar day of harvest, a block for a multi-day harvest)")
    aoi = R.get("aoi") or {}
    if aoi.get("n_plots"):
        extras.append("Plot_Id" + (" and Tgt_Rate" if aoi.get("rate_col") else "") + " (from the trial design)")
    if extras:
        s += ". Also available: " + "; ".join(extras)
    M = R.get("methods") or {}
    if R.get("method") == "both" and M.get("sms3sigma"):
        f = (M["sms3sigma"].get("files") or {}).get("difm_ready_zip")
        cm = M.get("comparison") or {}
        s += (f". The SMS 3-sigma file is {f} (map {M['sms3sigma'].get('yield_column_for_difm')} and its optimised "
              "swath width)" + (f"; the two methods agree on {cm['agreement_pct']:.1f} % of the kept points"
                                if cm.get("agreement_pct") is not None else ""))
    return s + "."


# ================================================================================================ helpers for the app
def preview_points(shp: str, ycol: str | None = None, n: int = 5000, seed: int = 0) -> pd.DataFrame:
    """A random sample of up to n points as lon/lat (WGS 84) + yield, for a map preview."""
    import pyogrio
    info = pyogrio.read_info(shp)
    if ycol is None:
        ycol = yield_clean.detect_columns(list(info["fields"]))["yield"]
    cols = [ycol] if ycol else []
    g = pyogrio.read_dataframe(shp, columns=cols)
    if len(g) > n:
        g = g.sample(n, random_state=seed)
    if g.crs is not None and not g.crs.equals("EPSG:4326"):
        g = g.to_crs("EPSG:4326")
    out = pd.DataFrame({"lon": g.geometry.x.values, "lat": g.geometry.y.values})
    out["yield"] = pd.to_numeric(g[ycol], errors="coerce").values if ycol else np.nan
    return out.dropna(subset=["lon", "lat"])


PREVIEW_N_MAX = 80000       # readings drawn by preview_swaths; above it a random sample of this size


def preview_swaths(shp: str, ycol: str | None = None, n_max: int = PREVIEW_N_MAX, seed: int = 0,
                   width_ft: float | None = None, y_offset: bool = True) -> pd.DataFrame:
    """The readings of a point file as the strips they swept, for the app's maps: lon, lat of the point, the yield,
    and `polygon` = the 4 corners [lon, lat] of the strip. The strip is the ground the header swept since the previous
    reading of the same sequence (yield_clean.swept_strips: consecutive strips tile, so a turn shows no fan of
    overlapping rectangles), across the direction of travel, with the file's Y_Offset when it has one and
    `y_offset` is true (the run's filters.F8.y_offset, so the map shows the footprint F8 used). Sequences
    follow the file order and break at a change of Run_Id / Pass_Id (an OCCD output), dataset or machine, at a step
    longer than 1.5 x Distance + 0.3 m (a removed reading between two kept ones is not bridged) and at a heading
    change > 60 deg; a reading without a usable predecessor gets the rectangle, Distance back along the travel. An SMS
    3-sigma output (Swath_Scl) is drawn as SMS draws it: rectangles with the optimised width (swath_quads). The
    strips are built on the whole file; a random n_max readings are returned when it holds more, each with `row`, its
    record in the file. The width is the
    file's width column (or Wdth_Opt), else `width_ft` (the settings' harvester width); the distance is the file's
    distance column, else speed x duration, as the engine does. The polygon column is absent when the strips cannot
    be built (no heading, no width, no distance, or no coordinate system: the engine refuses such a file itself), and
    None on a reading whose strip cannot be built (the map then draws the point)."""
    import pyogrio
    info = pyogrio.read_info(shp)
    fields = list(info["fields"])
    det = yield_clean.detect_columns(fields)
    if ycol is None:
        ycol = det["yield"]
    hcol, dcol, scol, tcol = det.get("heading"), det.get("distance_ft"), det.get("speed_mph"), det.get("duration_s")
    wcol = det.get("width_ft") or ("Wdth_Opt" if "Wdth_Opt" in fields else None)
    sms_out = "Swath_Scl" in fields
    seq_cols = [c for c in ("Run_Id", "Pass_Id") if c in fields] + [c for c in (det.get("dataset"), det.get("machine"))
                                                                     if c]
    ocol = None if (sms_out or not y_offset) else yield_clean.sms_mod.y_offset_column(fields)
    cols = [c for c in dict.fromkeys([ycol, hcol, dcol, wcol, scol, tcol, ocol] + seq_cols) if c]
    g = pyogrio.read_dataframe(shp, columns=cols)
    if g.crs is not None and not g.crs.equals("EPSG:4326"):
        g = g.to_crs("EPSG:4326")
    out = pd.DataFrame({"lon": g.geometry.x.values, "lat": g.geometry.y.values})
    out["yield"] = pd.to_numeric(g[ycol], errors="coerce").values if ycol else np.nan
    ok = np.isfinite(out["lon"].to_numpy()) & np.isfinite(out["lat"].to_numpy())
    has_w = bool(wcol) or (width_ft is not None and float(width_ft) > 0)
    has_d = bool(dcol) or bool(scol and tcol)
    if hcol and has_w and has_d and ok.any() and g.crs is not None:
        from pyproj import Transformer
        utm = g.iloc[np.flatnonzero(ok)].estimate_utm_crs()
        fwd = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
        back = Transformer.from_crs(utm, "EPSG:4326", always_xy=True)
        x, y = (np.asarray(v, float) for v in fwd.transform(out["lon"].to_numpy(), out["lat"].to_numpy()))
        x, y = np.where(ok, x, np.nan), np.where(ok, y, np.nan)
        num = lambda c: pd.to_numeric(g[c], errors="coerce").to_numpy(float)  # noqa: E731
        hdg = num(hcol)
        dist = (num(dcol) if dcol else num(scol) * 1.46667 * num(tcol)) * 0.3048   # m (ft: mph x s x 1.46667)
        wid = (num(wcol) if wcol else np.full(len(g), float(width_ft))) * 0.3048
        if sms_out:
            q = yield_clean.swath_quads(x, y, hdg, dist, wid)
        else:
            new = np.zeros(len(g), bool)
            for c in seq_cols:
                v = g[c].astype(str).to_numpy()
                new[1:] |= v[1:] != v[:-1]
            dh = np.abs(((np.diff(hdg) + 180) % 360) - 180)
            new[1:] |= ~(dh <= 60)
            with np.errstate(invalid="ignore"):
                new[1:] |= ~(np.hypot(np.diff(x), np.diff(y)) <= 1.5 * np.nan_to_num(dist[1:]) + 0.3)
            off = num(ocol) * 0.3048 if ocol else None
            q = yield_clean.swept_strips(x, y, dist, wid, hdg, new, off)
        rows = np.flatnonzero(ok)                  # the strips link on the whole file; polygons only for the drawn rows
        if len(rows) > n_max:
            rows = np.sort(np.random.default_rng(seed).choice(rows, n_max, replace=False))
        qlon, qlat = back.transform(q[rows, :, 0].ravel(), q[rows, :, 1].ravel())
        ql = np.round(np.c_[np.asarray(qlon, float), np.asarray(qlat, float)].reshape(-1, 4, 2), 7)   # 1 cm
        valid = np.isfinite(ql).all(axis=(1, 2))
        out = out.iloc[rows].copy()
        out["row"] = rows                         # the record of the file (OCED colours the strips by any attribute)
        out["polygon"] = [p.tolist() if v else None for p, v in zip(ql, valid)]
        return out.reset_index(drop=True)
    out = out[ok].copy()
    out["row"] = np.flatnonzero(ok)
    if len(out) > n_max:
        out = out.sample(n_max, random_state=seed)
    return out.reset_index(drop=True)


def colour_by_yield(values, cmap: str = "RdYlGn") -> list[str]:
    """Hex colours from the 2nd-98th percentile range of `values` (NaN -> grey)."""
    import matplotlib
    v = np.asarray(values, float)
    ok = np.isfinite(v)
    if not ok.any():
        return ["#9e9e9e"] * len(v)
    lo, hi = np.nanpercentile(v[ok], [2, 98])
    t = np.clip((v - lo) / (hi - lo if hi > lo else 1.0), 0, 1)
    cm = matplotlib.colormaps[cmap]
    return [matplotlib.colors.to_hex(cm(x)) if np.isfinite(x) else "#9e9e9e" for x in t]


def find_boundary(root: str) -> str | None:
    """The first polygon layer under root (.geojson / .json / .gpkg / .kml / .kmz / .shp), for the optional boundary
    or field of interest."""
    import pyogrio
    for dp, dn, fn in os.walk(root):
        for f in sorted(fn):
            if os.path.splitext(f)[1].lower() not in (".geojson", ".json", ".gpkg", ".kml", ".kmz", ".shp"):
                continue
            p = os.path.join(dp, f)
            try:
                gt = str(pyogrio.read_info(p).get("geometry_type") or "")
            except Exception:
                continue
            if "polygon" in gt.lower():
                return p
    return None


# ================================================================================================ field of interest
AOI_EXTS = (".shp", ".zip", ".geojson", ".json", ".gpkg", ".kml", ".kmz")
AOI_PRESELECT_SHARE = 0.20        # a unit with >= 20 % of its readings inside the AOI + buffer is pre-selected (house)
AOI_HIDE_SHARE = 0.01             # a unit with < 1 % inside is hidden behind "show all units" (house)
AOI_BUFFER_M = 50.0               # the processing buffer of the shared spec (headland context for passes / F7 / F8)
_PLAN_ID_COLS = ("plot", "plot_id", "id", "obj__id")
_PLAN_RATE_COLS = ("rate", "rate_l", "tgt_rate_l")
_PLAN_HEADLAND_TYPES = ("headland", "border")
_PLAN_HEADLAND_AREA_RATIO = 5.0   # no type column: the single polygon larger than 5 x the median plot area is the border


def _aoi_module():
    """engine.clean.aoi when it is installed (the AOI builder's module), else None."""
    try:
        from engine.clean import aoi as mod
    except ImportError:
        return None
    return mod


def read_plan(path: str, id_col: str | None = None, rate_col: str | None = None, headland_types=None,
              feature=None) -> dict:
    """A boundary or trial-design polygon file -> {"gdf", "union", "n_polygons", "n_plots", "headland_polygons",
    "area_ac", "id_col", "rate_col", "rates", "crs", "is_plan", "needs_choice", "fields", "feature"} (the shared
    spec's read_plan). Delegates to engine.clean.aoi.read_plan when that module exists; otherwise the fallback below
    applies the same rules: AOI = union of the polygons; a file with > 1 polygon is a plan (plots) only when it has a
    rate column, a plot column, a polygon typed headland / border, or >= 4 polygons of similar size; otherwise it holds
    several field boundaries and `feature` (1-based, or a list: their union) picks the field of interest
    (needs_choice True until it does). In a plan the
    polygons whose 'type' / 'Type' matches headland_types (default headland, border), or the single untyped polygon
    larger than 5 x the median area, are the headland; id_col auto = plot / Plot_Id / id / Obj__Id (case-insensitive)
    else the row index 1..n; rate_col auto = the first column starting with 'tgt' or named rate / Rate_l /
    Tgt_Rate_l. Any CRS (none -> WGS 84 assumed)."""
    mod = _aoi_module()
    if mod is not None and hasattr(mod, "read_plan"):
        P = mod.read_plan(path, id_col=id_col, rate_col=rate_col,
                          headland_types=tuple(headland_types or _PLAN_HEADLAND_TYPES), feature=feature)
        return P if isinstance(P, dict) else plan_to_dict(P)
    return _read_plan_fallback(path, id_col, rate_col, headland_types, feature=feature)


def plan_to_dict(P) -> dict:
    """The spec dict of an engine.clean.aoi.Plan object (gdf, union, counts, area, id / rate columns, rates, crs),
    plus "plan" (the object itself, for aoi.inside / tag_plots / outline_xy) and "warnings"."""
    gdf = P.gdf
    utm = gdf.estimate_utm_crs()
    d = P.summary(utm) if hasattr(P, "summary") else {}
    rates = d.get("rates")
    if rates is None:
        r = P.rates() if callable(getattr(P, "rates", None)) else None
        rates = sorted({float(v) for v in r.dropna()}) if r is not None else []
    area = d.get("area_ac")
    if area is None:
        import geopandas as gpd
        area = float(gpd.GeoSeries([P.union], crs=gdf.crs).to_crs(utm).area.iloc[0] / 4046.8564224)
    return {"gdf": gdf, "union": P.union, "n_polygons": int(P.n_polygons), "n_plots": int(P.n_plots),
            "headland_polygons": int(getattr(P, "n_headland", d.get("headland_polygons", 0))), "area_ac": float(area),
            "id_col": P.id_col, "rate_col": P.rate_col, "rates": list(rates), "crs": str(gdf.crs), "plan": P,
            "is_plan": bool(getattr(P, "is_plan", P.n_plots > 0)), "needs_choice": bool(getattr(P, "needs_choice", False)),
            "fields": list(getattr(P, "fields", []) or []), "feature": getattr(P, "feature", None),
            "n_fields": int(getattr(P, "n_fields", 0)), "n_in_file": int(getattr(P, "n_in_file", P.n_polygons)),
            "warnings": list(getattr(P, "warnings", []) or [])}


def _read_plan_fallback(path, id_col=None, rate_col=None, headland_types=None, feature=None) -> dict:
    import geopandas as gpd
    from shapely.ops import unary_union
    path = os.path.abspath(str(path))
    if not os.path.exists(path):
        raise ValueError(f"field of interest not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in AOI_EXTS:
        raise ValueError(f"{os.path.basename(path)}: a field of interest must be a polygon file "
                         f"({', '.join(AOI_EXTS)})")
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        raise ValueError(f"{os.path.basename(path)} could not be read as a polygon layer ({e})") from None
    gdf = gdf[gdf.geometry.notna() & gdf.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if not len(gdf):
        raise ValueError(f"{os.path.basename(path)} holds no polygon")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf.reset_index(drop=True)
    utm = gdf.estimate_utm_crs()
    area_m2 = gdf.to_crs(utm).area.values
    n = len(gdf)
    types = [t for t in headland_types or _PLAN_HEADLAND_TYPES]
    lower = {str(c).lower(): c for c in gdf.columns if c != gdf.geometry.name}
    head = np.zeros(n, bool)
    is_plan, fields, needs_choice, chosen, warnings = False, [], False, None, []
    n_in_file = n
    chosen_l = _feature_list(feature)
    if chosen_l is not None:
        if any(not 1 <= k <= n for k in chosen_l):
            raise ValueError(f"aoi.feature = {feature} but {os.path.basename(path)} holds {n} polygon(s)")
        chosen = chosen_l[0] if len(chosen_l) == 1 else chosen_l
    if n > 1:
        typed = np.zeros(n, bool)
        untyped = np.ones(n, bool)
        if "type" in lower:
            t = gdf[lower["type"]].astype(str).str.strip().str.lower()
            typed = t.isin([x.lower() for x in types]).values
            untyped = (gdf[lower["type"]].isna() | t.isin(["", "nan", "none", "null"])).values
        rc = next((c for c in gdf.columns if str(c).lower().startswith("tgt")), None) or \
            next((lower[c] for c in _PLAN_RATE_COLS if c in lower), None)
        pc = next((lower[c] for c in ("plot", "plot_id") if c in lower), None)
        med_all = float(np.median(area_m2))
        big = area_m2 > _PLAN_HEADLAND_AREA_RATIO * med_all
        cand = area_m2[~big] if big.sum() == 1 else area_m2
        similar = len(cand) >= 4 and float(cand.max()) <= _PLAN_HEADLAND_AREA_RATIO * float(np.median(cand))
        is_plan = bool(rate_col or rc or pc or typed.any() or similar) and chosen is None
        if is_plan:
            head = typed.copy()
            if not typed.any() and big.sum() == 1 and untyped[big][0]:
                head = big
        else:
            namec = next((lower[c] for c in ("name", "field", "field_name", "label") if c in lower), None)
            fields = [{"index": i + 1, "name": (str(gdf[namec].iloc[i]) if namec else ""),
                       "area_ac": float(area_m2[i] / 4046.8564224)} for i in range(n)]
            if chosen is None:
                needs_choice = True
                warnings.append(f"{os.path.basename(path)} holds {n} polygons that are several field boundaries, not a "
                                f"trial plan: choose the field of interest (aoi.feature 1..{n})")
            else:
                gdf = gdf.iloc[[k - 1 for k in chosen_l]].reset_index(drop=True)
                area_m2 = area_m2[[k - 1 for k in chosen_l]]
                n, head = len(chosen_l), np.zeros(len(chosen_l), bool)
    if id_col is None and is_plan:
        id_col = next((lower[c] for c in _PLAN_ID_COLS if c in lower), None)
    elif id_col is not None and id_col not in gdf.columns:
        raise ValueError(f"id column {id_col!r} is not in the plan (columns: {list(lower.values())})")
    if rate_col is None and is_plan:
        rate_col = next((c for c in gdf.columns if str(c).lower().startswith("tgt")), None)
        if rate_col is None:
            rate_col = next((lower[c] for c in _PLAN_RATE_COLS if c in lower), None)
    elif rate_col is not None and rate_col not in gdf.columns:
        raise ValueError(f"rate column {rate_col!r} is not in the plan (columns: {list(lower.values())})")
    gdf["_is_headland"] = head
    gdf["_plot_id"] = (gdf[id_col].astype(str).values if id_col else (np.arange(1, n + 1)).astype(str))
    gdf.loc[gdf["_is_headland"], "_plot_id"] = ""
    plots = ~head if is_plan else np.zeros(n, bool)
    rates = []
    if rate_col and is_plan:
        r = pd.to_numeric(gdf.loc[plots, rate_col], errors="coerce").dropna()
        rates = sorted({float(x) for x in r.unique()})
    union = unary_union(list(gdf.geometry.values))
    area_ac = float(gpd.GeoSeries([union], crs=gdf.crs).to_crs(utm).area.iloc[0] / 4046.8564224)
    return {"gdf": gdf, "union": union, "n_polygons": int(n), "n_plots": int(plots.sum()),
            "headland_polygons": int(head.sum()) if is_plan else 0, "area_ac": area_ac, "id_col": id_col,
            "rate_col": rate_col, "rates": rates, "crs": str(gdf.crs), "is_plan": is_plan, "needs_choice": needs_choice,
            "fields": fields, "feature": chosen, "n_fields": (0 if is_plan else len(fields) or n), "n_in_file": n_in_file,
            "warnings": warnings}


def _feature_list(feature):
    """aoi.feature as a sorted list of 1-based polygon indices (engine.clean.aoi.feature_list when it exists)."""
    mod = _aoi_module()
    if mod is not None and hasattr(mod, "feature_list"):
        return mod.feature_list(feature)
    if feature is None:
        return None
    items = feature if isinstance(feature, (list, tuple)) else str(feature).split(",")
    return sorted({int(str(v).strip()) for v in items if str(v).strip()}) or None


feature_list = _feature_list                 # public name (the app's polygon selector)


def feature_setting(feature):
    """aoi.feature as written in the settings: an int for one polygon, a list for several, None for none."""
    fl = _feature_list(feature)
    return None if fl is None else (fl[0] if len(fl) == 1 else fl)


def plan_union_wgs84(plan: dict):
    """The plan's AOI union as a shapely geometry in WGS 84 (plan = read_plan(...))."""
    import geopandas as gpd
    gs = gpd.GeoSeries([plan["union"]], crs=plan.get("crs") or "EPSG:4326")
    if not gs.crs.equals("EPSG:4326"):
        gs = gs.to_crs("EPSG:4326")
    return gs.iloc[0]


def buffer_wgs84(geom, buffer_m: float):
    """geom (WGS 84) buffered by buffer_m metres in its UTM zone, back in WGS 84 (0 -> the geometry itself)."""
    import geopandas as gpd
    if not buffer_m:
        return geom
    gs = gpd.GeoSeries([geom], crs="EPSG:4326")
    utm = gs.estimate_utm_crs()
    return gs.to_crs(utm).buffer(float(buffer_m)).to_crs("EPSG:4326").iloc[0]


def _quiet(_msg):
    return None


def _unit_readings(candidate: dict, unit_id: str, opts, workdir: str, log=_quiet):
    """(lon, lat, area_ac) arrays of one unit's readings, decoded once and cached in
    workdir/decoded/aoi_cache/<id>.npz; area_ac = Distance_f x Swth_Wdth_, the strip each reading swept (NaN without
    them). A unit that cannot be decoded (ValueError: unknown crop, no reading ...) caches empty arrays; a cache
    written before the area was kept is decoded again."""
    import hashlib
    d = os.path.join(workdir, "decoded", "aoi_cache")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, hashlib.md5(unit_id.encode("utf-8")).hexdigest() + ".npz")
    if os.path.exists(f):
        z = np.load(f)
        if "area" in z.files:
            return z["lon"], z["lat"], z["area"]
    mod = detect.decoder(candidate["decoder"])
    root = candidate["probe"].root
    try:
        df, _ = mod.decode(root, [unit_id], opts, log=_quiet)
        n = len(df) if df is not None else 0

        def num(c):
            return pd.to_numeric(df[c], errors="coerce").values.astype(float) if n and c in df else np.full(n, np.nan)
        lon, lat = num("lon"), num("lat")
        area = num("Distance_f") * num("Swth_Wdth_") / common.SQFT_PER_AC
    except (ValueError, KeyError) as e:
        log(f"unit {unit_id}: not decodable for the AOI check ({e})")
        lon, lat, area = np.array([]), np.array([]), np.array([])
    ok = np.isfinite(lon) & np.isfinite(lat)
    np.savez(f, lon=lon[ok], lat=lat[ok], area=area[ok])
    return lon[ok], lat[ok], area[ok]


def _unit_positions(candidate: dict, unit_id: str, opts, workdir: str, log=_quiet):
    """(lon, lat) arrays of one unit's readings (_unit_readings without the area)."""
    lon, lat, _ = _unit_readings(candidate, unit_id, opts, workdir, log=log)
    return lon, lat


def raw_readings(candidate: dict, units, opts, workdir: str, log=_quiet) -> pd.DataFrame:
    """The raw data as it is, for the app's raw-data and field-of-interest maps: lon, lat (WGS 84), area_ac, unit (id),
    field (the monitor's field name) and machine of every reading of the latest season's units (Unit.default; older
    seasons are left out, as in units_inside_aoi). Shares the positions cache of units_inside_aoi: one decode per unit
    and work folder."""
    opts = opts if opts is not None else detect.default_options(candidate["decoder"])
    parts = []
    for u in units:
        if not u.default:
            continue
        lon, lat, area = _unit_readings(candidate, u.id, opts, workdir, log=log)
        log(f"unit {u.id}: {len(lon):,} readings")
        if len(lon):
            parts.append(pd.DataFrame({"lon": lon, "lat": lat, "area_ac": area, "unit": u.id,
                                       "field": u.field or "(no field)", "machine": str(u.machine or "")}))
    if not parts:
        return pd.DataFrame(columns=["lon", "lat", "area_ac", "unit", "field", "machine"])
    return pd.concat(parts, ignore_index=True)


def export_readings(shp: str) -> pd.DataFrame:
    """Every point of a point export as lon, lat (WGS 84), area_ac (distance x width, or speed x duration x width, as
    the engine does; NaN without them) and group (the dataset column, else the machine column; '' without one), for
    the app's raw-data and field-of-interest maps."""
    import pyogrio
    fields = list(pyogrio.read_info(shp)["fields"])
    det = yield_clean.detect_columns(fields)
    dcol, wcol, scol, tcol = det.get("distance_ft"), det.get("width_ft"), det.get("speed_mph"), det.get("duration_s")
    gcol = det.get("dataset") or det.get("machine")
    g = pyogrio.read_dataframe(shp, columns=[c for c in dict.fromkeys([dcol, wcol, scol, tcol, gcol]) if c])
    if g.crs is not None and not g.crs.equals("EPSG:4326"):
        g = g.to_crs("EPSG:4326")
    nan = np.full(len(g), np.nan)
    num = lambda c: pd.to_numeric(g[c], errors="coerce").to_numpy(float) if c else nan  # noqa: E731
    dist = num(dcol) if dcol else (num(scol) * 1.46667 * num(tcol) if scol and tcol else nan)
    out = pd.DataFrame({"lon": g.geometry.x.values, "lat": g.geometry.y.values,
                        "area_ac": dist * num(wcol) / common.SQFT_PER_AC,
                        "group": g[gcol].astype(str).values if gcol else ""})
    return out[np.isfinite(out["lon"].to_numpy()) & np.isfinite(out["lat"].to_numpy())].reset_index(drop=True)


def units_inside_aoi(candidate: dict, units, aoi_union, opts, workdir: str, buffer_m: float = AOI_BUFFER_M,
                     log=_quiet) -> dict:
    """{unit_id: share of the unit's readings inside aoi_union (WGS 84) buffered by buffer_m} for the units of the
    latest season (Unit.default); a unit of another season gets None (not measured). Every measured unit is decoded
    once (positions cached per work folder), so changing the AOI costs no second decode. A unit with no decodable
    reading gets 0.0."""
    import shapely
    opts = opts if opts is not None else detect.default_options(candidate["decoder"])
    poly = buffer_wgs84(aoi_union, buffer_m)
    shapely.prepare(poly)
    out = {}
    for u in units:
        if not u.default:
            out[u.id] = None
            continue
        lon, lat = _unit_positions(candidate, u.id, opts, workdir, log=log)
        if not len(lon):
            out[u.id] = 0.0
            continue
        inside = shapely.contains_xy(poly, lon, lat)
        out[u.id] = float(inside.mean())
        log(f"unit {u.id}: {100 * out[u.id]:.1f} % of {len(lon):,} readings inside the AOI + {buffer_m:g} m")
    return out


def units_aoi_distance_m(candidate: dict, units, aoi_union, opts, workdir: str) -> dict:
    """{unit_id: distance (m) from the AOI to the unit's nearest reading} for the measured units (cached positions
    of units_inside_aoi are reused; 0 when a reading is inside). For the 'nothing inside' message."""
    import geopandas as gpd
    import shapely
    from pyproj import Transformer
    opts = opts if opts is not None else detect.default_options(candidate["decoder"])
    gs = gpd.GeoSeries([aoi_union], crs="EPSG:4326")
    utm = gs.estimate_utm_crs()
    poly = gs.to_crs(utm).iloc[0]
    tr = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    out = {}
    for u in units:
        if not u.default:
            continue
        lon, lat = _unit_positions(candidate, u.id, opts, workdir)
        if not len(lon):
            continue
        x, y = tr.transform(lon, lat)
        out[u.id] = float(shapely.distance(poly, shapely.points(x, y)).min())
    return out


def machine_summary(shp: str, machine_col: str | None, yield_col: str | None,
                    dataset_col: str | None = None) -> list[dict]:
    """[{machine, n, mean_yield}] of a point file, for the app's reference-combine and per-machine-totals widgets: by
    the machine column; without one, by the sources at the end of the dataset names when they differ (as the cleaning
    tells the combines apart, machines.from_dataset); else one row 'M1' (mean_yield None without a yield column)."""
    import pyogrio
    dataset_col = None if machine_col else dataset_col
    cols = [c for c in dict.fromkeys((machine_col, yield_col, dataset_col)) if c]
    if not cols:
        return []
    df = pyogrio.read_dataframe(shp, columns=cols, read_geometry=False)
    dm = yield_clean.sms_mod.dataset_machines(df[dataset_col]) if dataset_col else None
    m = (df[machine_col].astype(str) if machine_col else
         pd.Series(dm[0] if dm is not None else ["M1"] * len(df)))
    y = pd.to_numeric(df[yield_col], errors="coerce") if yield_col else pd.Series(np.nan, index=df.index)
    g = pd.DataFrame({"m": m.values, "y": y.values}).groupby("m")
    return [{"machine": str(k), "n": int(len(d)), "mean_yield": (None if d.y.notna().sum() == 0 else float(d.y.mean()))}
            for k, d in g]


def export_crop_guess(shp: str, product_col: str = "Product", crop_col: str = "Crop") -> str | None:
    """The crop key of common.CROPS carried by an export: the 'Crop' column a decoded file holds (the crop the decoder
    used, written by engine.run.decode), else the key that the most frequent product name contains; None when
    unknown (a variety name such as 'P1530 G' says nothing about the crop)."""
    import pyogrio
    try:
        info = pyogrio.read_info(shp)
        fields = list(info["fields"])
        if crop_col in fields:
            c = pyogrio.read_dataframe(shp, columns=[crop_col], read_geometry=False)[crop_col].astype(str)
            c = c[c.str.strip() != ""]
            if len(c):
                top = str(c.mode().iloc[0]).strip().lower()
                if top in common.CROPS:
                    return top
        if product_col not in fields:
            return None
        v = pyogrio.read_dataframe(shp, columns=[product_col], read_geometry=False)[product_col].astype(str)
    except Exception:
        return None
    if not len(v):
        return None
    top = str(v.mode().iloc[0]).strip().lower()
    for k in common.CROPS:
        if k in top or (k == "soybeans" and "soy" in top):
            return k
    return None


# ================================================================================================ CLI
def _print(s=""):
    print(s, flush=True)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="python -m engine.run",
                                 description="OCED — Olds College Extract Data: a yield export or raw monitor data -> "
                                             "the clean shapefile of the SMS 3-sigma sequence, in one command.")
    ap.add_argument("inputs", nargs="+", help="file(s), folder(s) or zip(s): a point export or a raw monitor dataset")
    ap.add_argument("--out", required=True, help="work folder (input/, decoded/, output/ are made inside)")
    ap.add_argument("--candidate", type=int, default=None, help="which detected dataset to use (1-based; default: "
                    "the only one, or the only raw dataset; several otherwise -> error listing them)")
    ap.add_argument("--list", action="store_true", help="only list what was detected (and the units of raw data)")
    ap.add_argument("--units", default=None, help="'all', or comma-separated unit ids (default: one harvest, as the "
                    "app: see --field)")
    ap.add_argument("--field", default=None, help="the field to decode (exact name, else a case-insensitive "
                    "substring); its latest season unless --year. Default: the field with the most records among the "
                    "pre-selected (latest-season) units")
    ap.add_argument("--year", type=int, default=None, help="keep only the units of this season")
    ap.add_argument("--allow-mixed", action="store_true", help="allow units of several fields, crops or seasons in "
                    "one file (refused by default: one harvest per file)")
    ap.add_argument("--crop", default=None, help=f"crop for the decoder ({', '.join(common.CROPS)}); default = monitor")
    ap.add_argument("--test-weight", type=float, default=None, help="test weight lb/bu (decoder)")
    ap.add_argument("--std-moisture", type=float, default=None, help="standard moisture %% (decoder)")
    ap.add_argument("--shrink", choices=["auto", "symmetric", "one_sided"], default=None,
                    help="how the dry yield was / is computed: the decoder's convention (default: the vendor's) and "
                         "the cleaning's moisture.shrink (auto = detected from the export)")
    ap.add_argument("--tag", default=None, help="output name prefix")
    ap.add_argument("--settings", default=None, help="cleaning settings JSON (any subset of DEFAULT_SETTINGS)")
    ap.add_argument("--scale-ticket", type=float, default=None, metavar="VALUE",
                    help="the grower's weight for the field (scale ticket) in --ticket-unit: the map is leveled to it "
                         "(L = weight / monitor total; columns Yld_Level and Yld_Lvl_Sy) and it closes the combine test")
    ap.add_argument("--ticket-unit", choices=list(TICKET_UNITS), default=None,
                    help="unit of --scale-ticket (default lb; t = metric tonne). lb / kg / t are converted to bushels "
                         "with the test weight: --test-weight, else the file's own Yld_Mass_W / Yld_Vol_We, else the "
                         "crop. Not for --scale-ticket-bu, which is in bushels")
    ap.add_argument("--ticket-basis", choices=["wet", "dry"], default="wet",
                    help="wet (default): the scale weighed wet grain; dry: the weight is already at the standard moisture")
    ap.add_argument("--ticket-moisture", type=float, default=None, metavar="PCT",
                    help="moisture of the weighed grain, when the ticket gives it (wet basis only)")
    ap.add_argument("--scale-ticket-bu", type=float, default=None, metavar="BU",
                    help="legacy alias: the ticket in bushels through the old scale_ticket_bu setting")
    ap.add_argument("--boundary", default=None, help="field boundary polygon file (level diagnostics only; prefer --aoi)")
    ap.add_argument("--aoi", default=None, help="field of interest: boundary or trial-design polygon file (.shp, .zip, "
                    ".geojson, .gpkg, .kml, .kmz). Records outside it + 50 m are dropped before the cascade, the clean "
                    "file is clipped to it, a design adds Plot_Id / Tgt_Rate; with raw data the units are chosen by "
                    "their share of readings inside it (>= 20 %%) instead of the monitor's field name")
    ap.add_argument("--aoi-feature", default=None, metavar="N[,M...]", help="when the --aoi file holds several "
                    "field boundaries (not a trial plan): the 1-based index of the polygon that is the field of interest, "
                    "or several indices separated by commas when the field is drawn in several polygons (their union)")
    ap.add_argument("--reference-machine", default=None, help="combine id used as the reference for the "
                    "harmonisation (default auto = the one with the most kept points)")
    ap.add_argument("--machine-total", action="append", default=None, metavar="VIN=BU",
                    help="wet bushels harvested by one combine (repeatable): per-machine level factors")
    ap.add_argument("--factor-method", choices=["auto", "cells", "track", "point", "machine"], default=None,
                    help="several combines: how the combine factor is computed (machines.method; auto = the paired "
                         "cells where the combines met on interleaved or mixed passes, no factor where they harvested "
                         "in blocks; the harvest layout and all four methods are reported whatever the choice)")
    ap.add_argument("--standard-moisture", type=float, default=None, help="standard moisture %% of the cleaning's "
                    "moisture basis (default: decoder > inferred from the export > crop table); also the decoder's "
                    "unless --std-moisture is given")
    ap.add_argument("--method", choices=["sms3sigma", "occd"], default="sms3sigma",
                    help="cleaning method: sms3sigma = the Ag Leader SMS 3-sigma sequence (clip, Optimize Swath "
                         "Widths, speed, moisture, dry yield within mean +/- 3 SD), the OCED default and the method "
                         "of the app; occd = the older cascade kept in the engine (not used by the app)")
    ap.add_argument("--sms-group", choices=["auto", "task", "machine", "field"], default=None,
                    help="SMS 3-sigma: where the mean and SD are computed (auto = one group for one combine, one per "
                         "task for several, as in SMS)")
    ap.add_argument("--copy-folders", action="store_true", help="copy input folders into the work folder")
    a = ap.parse_args(argv)
    try:
        return _cli(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:                       # an unexpected failure: one line + the traceback in a log file
        log = None
        try:
            os.makedirs(os.path.abspath(a.out), exist_ok=True)
            log = os.path.join(os.path.abspath(a.out),
                               f"error_{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log")
            with open(log, "w", encoding="utf-8") as f:
                f.write(" ".join(sys.argv) + "\n\n" + traceback.format_exc())
        except OSError:
            log = None
        print(f"error: unexpected {type(e).__name__}: {e}" + (f" (traceback in {log})" if log else ""),
              file=sys.stderr)
        return 3


def _count(n) -> str:
    """An integer count with thousands separators ('?' when unknown)."""
    return f"{int(n):,}" if isinstance(n, (int, float)) and n == n else "?"


def _cli(a) -> int:
    work = os.path.abspath(a.out)
    for sub in ("input", "decoded", "output"):
        os.makedirs(os.path.join(work, sub), exist_ok=True)
    cands = open_input(a.inputs, work, copy_folders=a.copy_folders, log=lambda m: _print("  " + m))
    if not cands:
        raise ValueError(cands.message)
    _print("\nDetected:")
    for i, c in enumerate(cands, 1):
        _print(f"  [{i}] {c['label']}")
    if a.candidate is not None:
        if not 1 <= a.candidate <= len(cands):
            raise ValueError(f"--candidate must be 1..{len(cands)}")
        cand = cands[a.candidate - 1]
    else:
        raw = [c for c in cands if c["kind"] == "raw"]
        if len(cands) == 1:
            cand = cands[0]
        elif len(raw) == 1:
            cand = raw[0]
            _print(f"  using [{cands.index(cand) + 1}], the raw monitor dataset (choose another with --candidate)")
        elif a.list:
            cand = None
        else:
            raise ValueError(f"{len(cands)} datasets were found (listed above): choose one with --candidate N")
    if cand is None:
        return 0
    use_candidate(cand, work, log=lambda m: _print("  " + m))
    units = list_units(cand) if cand["kind"] == "raw" else []
    plan = None
    if a.aoi:
        plan = read_plan(os.path.abspath(a.aoi), feature=a.aoi_feature)
        _print(f"\nField of interest: {os.path.basename(a.aoi)}: {plan['n_polygons']} polygon(s), {plan['n_plots']} "
               f"plot(s), {plan['headland_polygons']} headland polygon(s), {plan['area_ac']:,.1f} ac"
               + (f", rate column {plan['rate_col']} ({', '.join(format(r, 'g') for r in plan['rates'])})"
                  if plan["rate_col"] else "")
               + (f" (polygon(s) {plan['feature']} of {plan.get('n_in_file')} chosen with --aoi-feature)"
                  if plan.get("feature") else ""))
        for w in plan.get("warnings") or []:
            _print("  note: " + str(w))
        if plan.get("needs_choice"):
            raise ValueError(f"{os.path.basename(a.aoi)} holds {plan['n_polygons']} field boundaries, not a trial plan: "
                             "choose the field of interest with --aoi-feature N, or N,M,... for a field drawn in several polygons ("
                             + "; ".join(f"{f['index']} = {f['name'] or 'polygon ' + str(f['index'])} "
                                         f"({f['area_ac']:,.1f} ac)" for f in plan.get("fields") or []) + ")")
    if a.list:
        for u in units:
            _print(f"  {'*' if u.default else ' '} {u.id}\n      {u.label}")
        return 0

    dec = None
    if cand["kind"] == "raw":
        everything = bool(a.units and a.units.strip().lower() == "all")
        ids = None
        if a.units and not everything:
            ids = [x.strip() for x in a.units.split(",") if x.strip()]
        opts = detect.default_options(cand["decoder"])
        std_m = a.std_moisture if a.std_moisture is not None else a.standard_moisture
        opts = dataclasses.replace(opts, crop=a.crop or opts.crop, test_weight_lb_bu=a.test_weight,
                                   std_moisture_pct=std_m,
                                   shrink=a.shrink if a.shrink in ("symmetric", "one_sided") else opts.shrink)
        if plan is not None and ids is None and not everything and not a.field:
            # the field of interest chooses the units: >= 20 % of the readings inside the AOI + 50 m
            _print(f"\nMeasuring the share of every latest-season unit inside the field of interest + "
                   f"{AOI_BUFFER_M:g} m ...")
            shares = units_inside_aoi(cand, units, plan_union_wgs84(plan), opts, work, log=lambda m: _print("  " + m))
            pool = [u for u in units if (shares.get(u.id) or 0.0) >= AOI_PRESELECT_SHARE]
            if a.year:
                pool = [u for u in pool if u.year == a.year]
            if not pool:
                dist = units_aoi_distance_m(cand, units, plan_union_wgs84(plan), opts, work)
                near = min(dist.values()) if dist else float("nan")
                raise ValueError(f"no unit has {100 * AOI_PRESELECT_SHARE:.0f} % of its readings inside the field of "
                                 f"interest; the nearest unit is {near:,.0f} m away (wrong field file, or choose the "
                                 "units with --units)")
            sel = pool
            note = f"{len(pool)} unit(s) with >= {100 * AOI_PRESELECT_SHARE:.0f} % inside the field of interest"
        else:
            sel, note = select_units(units, a.field, a.year, ids, everything)
        if not sel:
            raise ValueError("no unit left to decode; list them with --list")
        if note:
            _print(f"\nUnits: {note}")
        _print(f"\nDecoding {len(sel)} unit(s):")
        for u in sel:
            _print(f"  {u.label}")
        dec = decode(cand, [u.id for u in sel], opts, work, log=lambda m: _print("  " + m), tag=a.tag,
                     allow_mixed=a.allow_mixed, aoi=plan is not None)
        rep = dec["report"]
        t = rep.get("totals") or {}
        _print(f"\nDecoded {dec['n']:,} readings (from {rep.get('n_records_read') or 0:,} records): "
               f"{t.get('area_ac', float('nan')):,.2f} ac, {t.get('bu_wet', float('nan')):,.1f} bu wet, "
               f"{t.get('bu_dry', float('nan')):,.1f} bu dry; time basis {rep.get('time_basis')}")
        for w in rep["warnings"]:
            _print("  decoder warning: " + str(w))
        shp = dec["shp"]
    else:
        shp = cand["path"]

    settings = {}
    if a.settings:
        with open(a.settings, encoding="utf-8") as f:
            settings = json.load(f)
    if a.ticket_moisture is not None and a.ticket_basis == "dry":
        raise ValueError("--ticket-moisture only applies to --ticket-basis wet (a dry-basis weight is already at the "
                         "standard moisture, so the ticket's moisture would be ignored): drop it or give the weight as "
                         "the scale wrote it with --ticket-basis wet")
    if a.scale_ticket is not None:
        settings["scale_ticket"] = {"value": a.scale_ticket, "unit": a.ticket_unit or "lb", "basis": a.ticket_basis,
                                    "moisture_pct": a.ticket_moisture, "note": None}
    if a.scale_ticket_bu is not None:
        if a.ticket_unit is not None or a.ticket_moisture is not None:
            raise ValueError("--scale-ticket-bu is the legacy ticket in bushels and takes no unit or moisture: use "
                             "--scale-ticket VALUE --ticket-unit lb|kg|bu|t [--ticket-moisture PCT] instead")
        settings["scale_ticket_bu"] = a.scale_ticket_bu
        if a.ticket_basis:
            settings["scale_ticket_basis"] = a.ticket_basis
    if a.test_weight is not None and settings.get("scale_ticket"):
        settings.setdefault("test_weight_lb_bu", a.test_weight)   # the same test weight converts the ticket
    if a.boundary:
        settings["boundary"] = os.path.abspath(a.boundary)
    if a.aoi:
        settings.setdefault("aoi", {})["file"] = os.path.abspath(a.aoi)
        if a.aoi_feature is not None:
            settings["aoi"]["feature"] = feature_setting(a.aoi_feature)
    if a.crop:
        settings["crop"] = a.crop
    if a.standard_moisture is not None:
        settings.setdefault("moisture", {})["standard_pct"] = a.standard_moisture
    if a.shrink:
        settings.setdefault("moisture", {})["shrink"] = a.shrink
    if a.reference_machine:
        settings.setdefault("machines", {})["reference"] = a.reference_machine
    if a.factor_method:
        settings.setdefault("machines", {})["method"] = a.factor_method
    if a.machine_total:
        totals = {}
        for item in a.machine_total:
            if "=" not in item:
                raise ValueError(f"--machine-total expects VIN=BU, not {item!r}")
            k, v = item.rsplit("=", 1)
            try:
                totals[k.strip()] = float(v)
            except ValueError:
                raise ValueError(f"--machine-total {item!r}: {v!r} is not a number of bushels") from None
        settings.setdefault("machines", {})["totals_bu"] = totals
    if a.tag or dec:
        settings.setdefault("tag", a.tag or dec["tag"])
    if a.method:
        settings["method"] = a.method
    if settings.get("method") == "sms3sigma":
        # OCED: the SMS sequence alone, as the app runs it (no combine factor after the cleaning)
        settings.setdefault("machines", {}).setdefault("harmonise", False)
    if a.sms_group:
        settings["sms3sigma"] = dict(settings.get("sms3sigma") or {}, group_by=a.sms_group)
    out = free_output_dir(work)
    _print("\nCleaning:")
    R = clean(shp, out, settings, log=lambda m: _print("  " + m), source=dec["source"] if dec else None)
    _print("")
    _print(pd.DataFrame(R["cascade"])[["filter", "on", "removed", "remaining"]].to_string(index=False))
    f8 = R["f8"]
    _print("\nSummary")
    _print(f"  input            {', '.join(a.inputs)}")
    _print(f"  dataset          {cand['label']}")
    if dec:
        _print(f"  decoded points   {dec['zip']}")
    _print(f"  points           {R['n_in']:,} in -> {R['n_kept']:,} kept ({R['removed_pct']:.1f} % removed)")
    if R.get("method") == "sms3sigma":
        M3 = R.get("sms3sigma") or {}
        sw, gr = M3.get("swath") or {}, M3.get("grouping") or {}
        _print(f"  method           SMS 3-sigma, {gr.get('n_groups')} group(s) ({gr.get('mode')}); swath "
               f"{sw.get('n_removed', 0):,} removed, {sw.get('n_narrowed', 0):,} narrowed")
    else:
        _print(f"  F8 overlap       {f8['mode']}, threshold "
               f"{'-' if f8['threshold'] is None else format(100 * f8['threshold'], '.3g') + ' %'}")
        _print(f"  flow delay       best {R['lag']['best_records']} records, applied {R['lag']['applied_records']}")
    if R.get("method") == "both":
        M = R.get("methods") or {}
        m3, cm = M.get("sms3sigma") or {}, M.get("comparison") or {}
        base = M.get("base_dir") or R["files"]["dir"]
        _print(f"  SMS 3-sigma      {m3.get('n_in', 0):,} in -> {m3.get('n_kept', 0):,} kept "
               f"({m3.get('removed_pct', 0):.1f} % removed): "
               f"{os.path.join(base, (m3.get('files') or {}).get('difm_ready_zip') or '')}")
        _print(f"  comparison       agreement {cm.get('agreement_pct', float('nan')):.1f} % of the kept points; mean "
               f"OCCD {cm.get('mean_occd', float('nan')):.2f} vs SMS 3-sigma "
               f"{cm.get('mean_sms3sigma', float('nan')):.2f} bu/ac: "
               f"{os.path.join(base, (cm.get('files') or {}).get('report_pdf') or '')}")
    if "level" in R:
        L = R["level"]
        t = ticket_settings(settings)
        if t is not None:
            conv = ticket_conversion(t, test_weight=settings.get("test_weight_lb_bu"), shp=shp, crop=settings.get("crop"))
            _print(f"  grower's weight  {ticket_label(t)} ({t['basis']} basis"
                   + (f", {t['moisture_pct']:g} % moisture" if t.get("moisture_pct") is not None else "") + ")"
                   + (f" {conv['text']}" if conv and conv.get("text") and t["unit"] != "bu" else ""))
        elif L.get("scale_ticket_bu") is not None:          # per-machine totals: the implied field total
            _print(f"  level ticket     {float(L['scale_ticket_bu']):,.1f} bu ({L.get('scale_ticket_note') or 'per-machine totals'})")
        _print(f"  level factor     {level_factor_text(L)}: {level_caption(R)}")
        c = L.get("closure") or {}
        if c.get("verdict"):
            _print(f"  closure          {c['verdict']}")
        tt = (R.get("machines") or {}).get("ticket_test") or {}
        if tt:
            wo, wi = tt.get("without") or {}, tt.get("with") or {}
            _print(f"  ticket test      without the factor {float(wo.get('total_bu', float('nan'))):,.1f} bu "
                   f"({float(wo.get('diff_pct', float('nan'))):+.2f} %), with it "
                   f"{float(wi.get('total_bu', float('nan'))):,.1f} bu ({float(wi.get('diff_pct', float('nan'))):+.2f} %): "
                   + ("applied" if tt.get("applied") else "not applied")
                   + (f" ({', '.join(map(str, tt.get('machines') or []))})" if tt.get("machines") else ""))
    se = (R.get("machines") or {}).get("seams") or {}
    if se.get("text"):
        _print(f"  seams            {se['text']}")
    fm = R.get("final_map") or {}
    if fm:
        _print(f"  final map        {fm['column']}: mean {fm['mean']:,.1f} bu/ac over {fm['n_points']:,} points "
               f"(fig_clean_final.png); " + "; ".join(fm.get("applied") or []))
    if R.get("aoi"):
        A = R["aoi"]
        _print(f"  field of interest {_count(A.get('n_in'))} records inside + {A.get('buffer_m') or AOI_BUFFER_M:g} m, "
               f"{_count(A.get('n_outside_buffer'))} dropped before the cascade, "
               f"{_count(A.get('n_output_outside_aoi'))} kept points outside the field left out of the clean file")
    _print(f"  warnings         {len(R['warnings'])}" + (" (see the report)" if R["warnings"] else ""))
    for x in R["advice"]:
        _print(f"  check            {x}")
    _print(f"  clean zip   {R['files']['difm_ready_zip']}")
    _print(f"  report           {R['files']['report_pdf']}")
    _print("  " + difm_note(R))
    return 0


if __name__ == "__main__":
    sys.exit(main())
