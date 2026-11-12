# -*- coding: utf-8 -*-
"""Save the CLEAN harvest in a monitor format, next to the clean shapefile: which formats a cleaned file can be saved
in, and the one call that writes it. The app shows only these two functions.

    from engine.formats import native_write as NW
    for o in NW.options(D.get("source")):       # [{"id", "label", "available", "reason", "native"}]
        ...                                     # the monitor's own format first, ISOXML always last
    res = NW.write(o["id"], D.get("source"), clean_shp, out_dir, widths=True, factors=None, new_ids=True, log=log)
    res["zip"], res["n_kept"], res["n_removed"], res["files_changed"], res["notes"], res["warnings"]

What is offered:
  * a clean file decoded from raw monitor data (source = engine.run.decode(...)["source"], source["format"] one of the
    raw decoders): the writer of that format, engine/formats/<format id>_write.py, when this version of OCED has it
    (it is imported only then, and an import error makes the option unavailable with the reason, not the app fail);
    available when its can_write(source) says so (e.g. the raw input is still on this computer).
    A raw source decoded by an older version of OCED (decode_outdated: its report lacks a key every decode of this
    version carries) is not offered in its own format: the writer decodes the input again with the current model,
    so it would write readings the clean file does not hold.
  * ISOXML TASKDATA (engine/formats/isoxml_write.py, not the source's format), always the last entry: available for a
    clean file without a raw source (an SMS / Operations Center export, a KML conversion: source None); for a raw
    source it is listed as not available (the clean data is saved in the format it came in), unless
    isoxml_fallback=True and the source's own writer cannot write.
  * a clean file decoded from ISOXML task data (source["format"] "isoxml"): ISOXML is the monitor's own format, so
    the one entry is the ISOXML writer, as the native format. It writes a NEW task data set from the clean readings
    (one task and one time log per combine, more where needed), not a copy of the display's own set: the reason of
    the entry says what is not carried over (ISOXML_NATIVE_NOTE).
Every writer follows one interface: FORMAT_ID, LABEL, can_write(source) -> (bool, reason), write_clean(source,
clean_shp, out_dir, *, widths=True, factors=None, new_ids=True, log=print, ...) returning at least {"path", "zip",
"n_kept", "n_removed", "files_changed", "notes", "warnings"} and raising ValueError (or a subclass) with a plain message
when it cannot write. write() checks the choice again, refuses an output folder inside the raw input, passes a
writer's own advanced options through (those it does not take are named in a warning) and adds "format_id", "label",
"native" and "sms_tested" to the result.

NOT YET TESTED IN SMS: no file written by any of these writers has been read into SMS yet; every result says so.
Pure engine code (no Streamlit, no app import).
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import os
import re

ISOXML = "isoxml"
RAW_FORMATS = ("cnh_cn1", "jd_jdl", "jd_gs3_rcd", "isoxml")   # the raw decoders (engine/formats/detect.py DECODERS)
REQUIRED_KEYS = ("path", "zip", "n_kept", "n_removed", "files_changed", "notes", "warnings")
SMS_CAVEAT = ("not yet tested in SMS: read the written file into a scratch SMS project, with the Processing Settings "
              "of the raw read, and compare its Summary and points with the clean file before using it")


# a key every decode report of this version carries for its format, and the reports of OCED's first published version
# did not: a decode without it followed an older model of how SMS reads that format
DECODE_MARKERS = {"cnh_cn1": "sms_summary", "jd_gs3_rcd": "alignment", "jd_jdl": "points", "isoxml": "time_logs"}
ISOXML_NATIVE_LABEL = "ISOXML TASKDATA (a new task data set of the clean readings)"
ISOXML_NATIVE_NOTE = ("a new TASKDATA set is written from the clean readings (one task and one time log per combine, "
                      "more where its readings cannot follow each other in one log; every reading where and when "
                      "the clean file has it): the display's own set is not copied, so its "
                      "maker's attributes and extra files, its guidance lines, its other devices and its task totals "
                      "are not in it, and the removed readings are left out, not kept as records with the header up")
OLD_DECODE = ("extracted by an older version of OCED, whose decode of these files is not the current model of how SMS "
              "reads them: written now, the file would not match the clean file. Open the raw data again and clean it, "
              "then write the monitor's format")


class NativeWriteError(ValueError):
    """The chosen format cannot be written for this clean file (a plain message for the user)."""


def _raw_formats() -> tuple:
    try:
        from engine.formats import detect
        return tuple(detect.DECODERS)
    except Exception:                                    # noqa: BLE001 - the constant is the same list
        return RAW_FORMATS


def raw_format(source) -> str | None:
    """The raw decoder a clean file came from (source["format"]), or None for an export / no source."""
    if not isinstance(source, dict):
        return None
    fmt = source.get("format") or (source.get("report") or {}).get("format")
    return fmt if fmt in _raw_formats() else None


def _module(fmt_id: str):
    """(writer module, "") or (None, why not): engine/formats/<fmt_id>_write.py, imported only if it exists."""
    if not isinstance(fmt_id, str) or not re.fullmatch(r"[a-z0-9_]+", fmt_id):
        return None, f"unknown format {fmt_id!r}"
    name = f"engine.formats.{fmt_id}_write"
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        return None, f"this version of OCED has no writer for {fmt_id}"
    try:
        mod = importlib.import_module(name)
    except Exception as e:                               # noqa: BLE001 - a broken writer must not break the app
        return None, f"the {fmt_id} writer could not be loaded ({type(e).__name__}: {e})"
    missing = [a for a in ("FORMAT_ID", "LABEL", "write_clean") if not hasattr(mod, a)]
    if missing:
        return None, f"the {fmt_id} writer lacks {', '.join(missing)}"
    return mod, ""


def _can(mod, source) -> tuple[bool, str]:
    fn = getattr(mod, "can_write", None)
    if fn is None:
        return True, "the writer does not check beforehand: it may refuse when writing"
    try:
        ok, why = fn(source)
    except Exception as e:                               # noqa: BLE001 - reported as the reason
        return False, f"the check failed ({type(e).__name__}: {e})"
    return bool(ok), str(why or "")


def _report(source) -> dict | None:
    """The decode report of a source: source["report"], else its decode_report JSON; None when there is none."""
    if not isinstance(source, dict):
        return None
    rep = source.get("report")
    if rep is None and source.get("decode_report") and os.path.isfile(source["decode_report"]):
        try:
            with open(source["decode_report"], encoding="utf-8") as f:
                rep = json.load(f)
        except (OSError, ValueError):
            rep = None
    return rep if isinstance(rep, dict) else None


def decode_outdated(source) -> str:
    """OLD_DECODE when this raw source was decoded by an older version of OCED, else "" (also for an export or a
    format without a marker). Its decode report (source["report"], else its decode_report JSON) lacks the key of
    DECODE_MARKERS that every decode of its format now carries; without a report to read, the source itself lacks
    "unit_ids", which every engine.run.decode_source of this version writes and the first published version did not
    (a writer cannot tell then which units and which model the decode used, and the GreenStar 3 writer would fall
    back to the decoder's defaults)."""
    key = DECODE_MARKERS.get(raw_format(source))
    if key is None:
        return ""
    rep = _report(source)
    if rep is None:
        return OLD_DECODE if "unit_ids" not in source else ""
    return OLD_DECODE if key not in rep else ""


def _input_root(source) -> str | None:
    if not isinstance(source, dict):
        return None
    if source.get("input_root"):
        return source["input_root"]
    return (_report(source) or {}).get("input_root")


def _inside(path: str, folder: str) -> bool:
    p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    f = os.path.normcase(os.path.realpath(os.path.abspath(folder)))
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def options(source, isoxml_fallback: bool = False) -> list:
    """The formats the clean file of this source can be saved in: [{"id", "label", "available", "reason",
    "native"}], the monitor's own format first (raw sources only), ISOXML always last. reason says why an option is
    not available (or a caveat). isoxml_fallback=True also makes ISOXML available for a raw source whose own writer
    cannot write."""
    out = []
    fmt = raw_format(source)
    native_ok, native_why = False, ""
    if fmt == ISOXML:                                    # the source's own format is ISOXML: one entry, native
        mod, why = _module(ISOXML)
        if mod is None:
            ok = False
        elif decode_outdated(source):
            ok, why = False, decode_outdated(source)
        else:
            ok, why = _can(mod, source)
            why = why or ISOXML_NATIVE_NOTE
        return [{"id": ISOXML, "label": ISOXML_NATIVE_LABEL, "available": bool(ok), "reason": why, "native": True}]
    if fmt:
        mod, why = _module(fmt)
        label = (mod.LABEL if mod is not None else
                 f"{(source or {}).get('label') or fmt} (the monitor's own format)")
        if mod is None:
            ok, why = False, why
        elif decode_outdated(source):
            ok, why = False, decode_outdated(source)
        else:
            ok, why = _can(mod, source)
        native_ok, native_why = ok, why
        out.append({"id": fmt, "label": label, "available": bool(ok), "reason": why, "native": True})
    iso, why = _module(ISOXML)
    if iso is None:
        out.append({"id": ISOXML, "label": "ISOXML TASKDATA (not the source's format)", "available": False,
                    "reason": why, "native": False})
        return out
    if fmt is None:
        ok, why = _can(iso, source)
    elif isoxml_fallback and not native_ok:
        ok, why = True, f"offered because the source's own format cannot be written: {native_why}"
    else:
        ok, why = False, ("the clean data came from raw monitor data and is saved in that format (above); ISOXML is "
                          "offered for exports without a raw source")
    out.append({"id": ISOXML, "label": iso.LABEL, "available": bool(ok), "reason": why, "native": False})
    return out


def write(fmt_id: str, source, clean_shp: str, out_dir: str, *, widths: bool = True, factors: dict | None = None,
          new_ids: bool = True, log=print, isoxml_fallback: bool = False, **advanced) -> dict:
    """Write the clean file in the format fmt_id (an "id" of options(source)) into out_dir. advanced = the writer's
    own options (cnh_cn1: mode, totals, verify, card_names, registry; isoxml: lead_in, max_sections; ...): those the
    writer does not take are left out and named in a warning. Returns the writer's result plus "format_id", "label",
    "native" and "sms_tested". Raises ValueError (NativeWriteError or the writer's own) with a plain message."""
    opts = {o["id"]: o for o in options(source, isoxml_fallback=isoxml_fallback)}
    if fmt_id not in opts:
        raise NativeWriteError(f"{fmt_id!r} is not offered for this clean file (offered: {', '.join(opts)})")
    if not opts[fmt_id]["available"]:
        raise NativeWriteError(opts[fmt_id]["reason"] or f"{fmt_id} cannot be written for this clean file")
    root = _input_root(source)
    if root and os.path.isdir(root) and _inside(out_dir, root):
        raise NativeWriteError("the output folder is inside the raw input's folder: choose a folder outside it")
    mod, why = _module(fmt_id)
    if mod is None:
        raise NativeWriteError(why)
    sig = inspect.signature(mod.write_clean)
    takes_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    passed = {k: v for k, v in advanced.items() if takes_any or k in sig.parameters}
    ignored = sorted(set(advanced) - set(passed))
    res = mod.write_clean(source, clean_shp, out_dir, widths=widths, factors=factors, new_ids=new_ids, log=log,
                          **passed)
    res = dict(res or {})
    res.setdefault("warnings", [])
    res.setdefault("notes", [])
    res["warnings"] = list(res["warnings"])
    res["notes"] = list(res["notes"])
    if ignored:
        res["warnings"].append(f"options {ignored} are not options of the {fmt_id} writer: not used")
    for k in REQUIRED_KEYS:
        if k not in res:
            res[k] = None
            res["warnings"].append(f"the {fmt_id} writer returned no {k!r}")
    if not res.get("sms_tested"):
        res["sms_tested"] = False
        if not any("not yet tested in SMS" in str(n) for n in res["notes"] + res["warnings"]):
            res["notes"].append(SMS_CAVEAT)
    own = fmt_id == ISOXML and raw_format(source) == ISOXML      # ISOXML task data saved as ISOXML
    if own and ISOXML_NATIVE_NOTE not in res["notes"]:
        res["notes"].append(ISOXML_NATIVE_NOTE)
    res.update(format_id=fmt_id, label=ISOXML_NATIVE_LABEL if own else mod.LABEL, native=fmt_id != ISOXML or own)
    return res
