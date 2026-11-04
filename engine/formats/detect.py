# -*- coding: utf-8 -*-
"""Unpack what the user gave the app and find what is in it: point exports and raw monitor datasets.

    from engine.formats import detect
    roots = detect.unpack(["Harvest trial 19.zip"], "work/input")
    cands = detect.detect(roots)            # list of candidates (+ cands.notes, cands.message)

unpack(paths, dest)
    Copies each file into dest and extracts every .zip into dest/<zip stem>/, recursively (a zip of per-combine zips,
    as the John Deere Operations Center hands out raw logs, is fully unpacked). Folder structure is kept: raw formats
    are recognised by their folder layout (a .cn1 card folder, JD-Data/log, RCD/EIC/Documentation). Folders are read
    IN PLACE by default (``copy_folders=False``): a 2-3 GB monitor card is not duplicated, nothing is written into it,
    and only the zips found inside it are extracted into dest. Guards, each a ValueError with a clear message: a zip
    member whose path leaves its target folder (zip slip: absolute paths, drive letters, '..'), more than
    MAX_MEMBERS members, more than MAX_TOTAL_BYTES unpacked in total, a member with a compression ratio above
    MAX_RATIO and more than 100 MB unpacked (zip bomb), zips nested deeper than MAX_DEPTH, a corrupt zip or member
    (bad CRC, truncated data: the partial file is removed), a member that cannot be written (OSError).
    Last, every .kml / .kmz of yield POINTS under the roots (an SMS "Export to Google Earth": placemarks with a Point
    and attributes; engine/formats/kml_points.py) is converted to a point shapefile with the SMS shapefile column names
    in dest/<kml stem>__kml/, which detect() then lists like any export. A boundary KML is left as it is; a damaged
    yield KML is a ValueError (a partial export would give a wrong field total).

detect(roots)
    Every point shapefile under the roots with a detectable yield column (engine/clean/yield_clean.detect_columns:
    dry or wet yield, or wet mass) becomes an "export" candidate (an Ag Leader SMS or John Deere Ops Center export, or
    a shapefile the app decoded earlier); a point layer without one (a planter or sprayer as-applied file, or other
    points of a machine) is an "export" too, with its "operation" (engine/clean/applied3s.detect_operation) and
    "yield" False; polygon and line shapefiles (boundaries, as-applied polygons, yield polygons) are ignored with a
    note, because the cleaning works on the logged points. The same export found twice (a zip next to its unpacked copy: same file stem,
    feature count and .dbf size) is listed once, and so is the same raw dataset found twice (same decoder and same
    data files by name and size, or one a subset of the other: the larger is kept). Every decoder in
    DECODERS runs its cheap ``probe`` (header reads only, no decoding) on every root; a probe that recognises its
    format gives a "raw" candidate. A probe that fails is recorded as a note, never raised: unknown content gives an
    empty list with ``.message`` listing the supported inputs.

The decoders' contract is engine/formats/common.py. The decoder modules are imported lazily so that a broken
decoder only disables its own format (recorded in the notes).
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import stat
import zipfile
import zlib

from engine.formats import common

DECODERS = ["cnh_cn1", "jd_jdl", "jd_gs3_rcd"]          # module names in engine/formats (FORMAT_ID == module name)
# the vendor software's dry-yield convention, the default of each decoder (docs/formats/*.md)
VENDOR_SHRINK = {"cnh_cn1": "one_sided", "jd_jdl": "one_sided", "jd_gs3_rcd": "one_sided"}

MAX_MEMBERS = 200_000
MAX_TOTAL_BYTES = 40 * 1024 ** 3          # 40 GB unpacked in one call
MAX_RATIO = 400.0                         # unpacked / compressed per member ...
MAX_RATIO_MIN_BYTES = 100 * 1024 ** 2     # ... checked for members above 100 MB unpacked
MAX_DEPTH = 6                             # zips inside zips
_SKIP_DIRS = {"__MACOSX", ".git", "$RECYCLE.BIN", "System Volume Information"}

SUPPORTED_TEXT = (
    "Supported inputs:\n"
    "- yield POINT export as a shapefile (.shp + .shx + .dbf + .prj, zipped or not): Ag Leader SMS, John Deere "
    "Operations Center, or any point file with yield, speed, heading, distance and swath width columns;\n"
    "- planter and sprayer as-applied POINT exports (shapefile, zipped or not), or any other point layer of a "
    "machine;\n"
    "- the same points as a .kml / .kmz (SMS 'Export to Google Earth' of the yield points, zipped or not);\n"
    "- Case IH / New Holland AFS Pro 700 card: the whole '<name>.cn1' folder (zipped or the folder itself);\n"
    "- John Deere Gen4 / G5 / X9 display logs: the JD-Data folder with log/*.jdl (one zip per combine is fine);\n"
    "- John Deere GreenStar 3 (2630) card: the RCD/EIC/Documentation folder with the .fdd + .fdl pairs."
)


class Candidates(list):
    """A list of candidate dicts, plus ``notes`` (what was ignored or failed) and ``message`` (for the user)."""

    def __init__(self, items=(), notes=None, message=""):
        super().__init__(items)
        self.notes = list(notes or [])
        self.message = message


def decoder(format_id: str):
    """The decoder module of a FORMAT_ID (ValueError for an unknown id)."""
    if format_id not in DECODERS:
        raise ValueError(f"unknown raw format {format_id!r}; formats are {DECODERS}")
    return importlib.import_module(f"engine.formats.{format_id}")


def default_options(format_id: str) -> common.DecodeOptions:
    """DecodeOptions with the vendor's shrink convention (the contract's dataclass defaults to 'symmetric')."""
    mod = decoder(format_id)
    if hasattr(mod, "default_options"):
        return mod.default_options()
    if hasattr(mod, "DEFAULT_OPTIONS"):
        import dataclasses
        return dataclasses.replace(mod.DEFAULT_OPTIONS)
    return common.DecodeOptions(shrink=VENDOR_SHRINK.get(format_id, "symmetric"))


# ================================================================================================ unpack
def _safe_target(base: str, member: str) -> str | None:
    """Absolute path of a zip member under base, or None when it would leave base (zip slip). Windows drops trailing
    dots and spaces from a path component, so '.. ' and '...' count as '..'."""
    name = member.replace("\\", "/")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p.rstrip(" .") in ("", "..") for p in parts):
        return None
    target = os.path.abspath(os.path.join(base, *parts))
    base_abs = os.path.abspath(base)
    if os.path.commonpath([os.path.normcase(target), os.path.normcase(base_abs)]) != os.path.normcase(base_abs):
        return None
    return target


def _free_name(path: str) -> str:
    """path, or path_2, path_3 ... when it already exists."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem}_{i}{ext}"):
        i += 1
    return f"{stem}_{i}{ext}"


def extract_zip(zpath: str, dest_dir: str, budget: dict, depth: int = 0, log=print) -> str:
    """Extract one zip into dest_dir (created) with the guards, then every zip it contains, recursively."""
    if depth > MAX_DEPTH:
        raise ValueError(f"{os.path.basename(zpath)}: zips nested more than {MAX_DEPTH} levels deep")
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{os.path.basename(zpath)} is not a readable zip file ({e})") from None
    with zf:
        infos = zf.infolist()
        budget["members"] += len(infos)
        if budget["members"] > MAX_MEMBERS:
            raise ValueError(f"more than {MAX_MEMBERS:,} files inside the zip(s): refusing to unpack")
        for i in infos:
            if i.is_dir():
                continue
            if i.file_size > MAX_RATIO_MIN_BYTES and i.file_size > MAX_RATIO * max(i.compress_size, 1):
                raise ValueError(f"{os.path.basename(zpath)}: member {i.filename!r} expands {i.file_size / max(i.compress_size, 1):,.0f}"
                                 " times (zip bomb?): refusing to unpack")
            budget["bytes"] += i.file_size
            if budget["bytes"] > MAX_TOTAL_BYTES:
                raise ValueError(f"the zip(s) unpack to more than {MAX_TOTAL_BYTES / 1024 ** 3:.0f} GB: refusing")
        os.makedirs(dest_dir, exist_ok=True)
        inner = []
        for i in infos:
            target = _safe_target(dest_dir, i.filename)
            if target is None:
                raise ValueError(f"{os.path.basename(zpath)}: member {i.filename!r} would be written outside the "
                                 "unpack folder (zip slip): refusing to unpack")
            if i.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(i) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
            except (zipfile.BadZipFile, zlib.error, EOFError, OSError, NotImplementedError, RuntimeError) as e:
                try:
                    if os.path.isfile(target):
                        os.remove(target)
                except OSError:
                    pass
                raise ValueError(f"{os.path.basename(zpath)}: member {i.filename!r} could not be unpacked "
                                 f"({type(e).__name__}: {e}); the zip is damaged or uses an unsupported "
                                 "compression - make a new zip") from None
            if target.lower().endswith(".zip"):
                inner.append(target)
    budget["zips"] += 1
    for z in inner:
        sub = _free_name(os.path.splitext(z)[0])
        log(f"  unpacking nested {os.path.relpath(z, dest_dir)}")
        extract_zip(z, sub, budget, depth + 1, log=log)
    return dest_dir


def unpack(paths, dest: str, copy_folders: bool = False, log=print) -> list[str]:
    """Copy / extract `paths` (files or folders) into dest. Returns the roots to scan with detect(): dest itself plus,
    with copy_folders False, every given folder (read in place). Raises ValueError on a guard or a missing path."""
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    budget = {"members": 0, "bytes": 0, "zips": 0}
    roots = [dest]
    for p in paths:
        p = os.path.abspath(str(p).strip().strip('"'))
        if not os.path.exists(p):
            raise ValueError(f"not found: {p}")
        name = os.path.basename(p.rstrip("\\/")) or "input"
        if os.path.isdir(p):
            if copy_folders:
                tgt = _free_name(os.path.join(dest, name))
                log(f"copying folder {p}")
                shutil.copytree(p, tgt)
                zips = [os.path.join(dp, f) for dp, dn, fn in os.walk(tgt) for f in fn if f.lower().endswith(".zip")]
            else:
                log(f"reading folder in place: {p}")
                roots.append(p)
                zips = []
                for dp, dn, fn in os.walk(p):
                    dn[:] = [d for d in dn if d not in _SKIP_DIRS]
                    zips += [os.path.join(dp, f) for f in fn if f.lower().endswith(".zip")]
            for z in zips:
                rel = os.path.relpath(os.path.splitext(z)[0], p if not copy_folders else tgt)
                sub = _free_name(os.path.join(dest, name + "__zips", rel))
                log(f"unpacking {os.path.relpath(z, os.path.dirname(p))}")
                extract_zip(z, sub, budget, 1, log=log)
        elif p.lower().endswith(".zip"):
            log(f"unpacking {name}")
            extract_zip(p, _free_name(os.path.join(dest, os.path.splitext(name)[0])), budget, 0, log=log)
        else:
            # a shapefile is several files: copy every sibling with the same stem (.shx, .dbf, .prj, .cpg, ...)
            files = [p]
            if p.lower().endswith(".shp"):
                stem = os.path.splitext(name)[0].lower()
                d = os.path.dirname(p)
                files = [os.path.join(d, f) for f in os.listdir(d)
                         if os.path.splitext(f)[0].lower() == stem and os.path.isfile(os.path.join(d, f))]
            for f in files:
                tgt = os.path.join(dest, os.path.basename(f))
                if os.path.normcase(os.path.abspath(tgt)) != os.path.normcase(f):
                    shutil.copy2(f, tgt)
                    os.chmod(tgt, stat.S_IREAD | stat.S_IWRITE)
    if budget["zips"]:
        log(f"unpacked {budget['zips']} zip(s), {budget['members']:,} entries, {budget['bytes'] / 1024 ** 2:,.1f} MB")
    _convert_kml_points(roots, dest, log=log)
    return roots


def _convert_kml_points(roots, dest, log=print):
    """Every KML / KMZ of yield points under the roots -> a point shapefile in dest/<kml stem>__kml/ (kml_points)."""
    found, seen = [], set()
    for r in roots:
        for dp, dn, fn in os.walk(r):
            dn[:] = [d for d in dn if d not in _SKIP_DIRS]
            for f in fn:
                p = os.path.abspath(os.path.join(dp, f))
                if f.lower().endswith((".kml", ".kmz")) and os.path.normcase(p) not in seen:
                    seen.add(os.path.normcase(p))
                    found.append(p)
    if not found:
        return
    from engine.formats import kml_points
    for p in found:
        if not kml_points.looks_like_points(p):
            continue                                      # a boundary or a map overlay, not yield points
        out = _free_name(os.path.join(dest, os.path.splitext(os.path.basename(p))[0] + "__kml"))
        try:
            _, _, notes = kml_points.to_shapefile(p, out, log=log)
        except OSError as e:
            raise ValueError(f"{os.path.basename(p)}: the KML could not be converted ({type(e).__name__}: {e})") from None
        for m in notes:
            log(m)


# ================================================================================================ detect
def _walk(root):
    for dp, dn, fn in os.walk(root):
        dn[:] = sorted(d for d in dn if d not in _SKIP_DIRS and not d.startswith("."))
        yield dp, sorted(fn)


_KML_DIR = re.compile(r"__kml(_\d+)?$")                 # the folders unpack() writes converted KML points into


def _exports(root, notes):
    import pyogrio
    out = []
    for dp, fn in _walk(root):
        low = {f.lower(): f for f in fn}
        for f in fn:
            if not f.lower().endswith(".shp"):
                continue
            path = os.path.join(dp, f)
            stem = os.path.splitext(f)[0].lower()
            missing = [e for e in (".shx", ".dbf") if stem + e not in low]
            if missing:
                notes.append(f"{os.path.relpath(path, root)}: ignored, {' and '.join(missing)} missing next to it")
                continue
            try:
                info = pyogrio.read_info(path)
            except Exception as e:          # an unreadable file is reported, never fatal
                notes.append(f"{os.path.relpath(path, root)}: ignored, not readable ({e})")
                continue
            gt = str(info.get("geometry_type") or "")
            if "point" not in gt.lower() or "multipoint" in gt.lower():
                notes.append(f"{os.path.relpath(path, root)}: {gt or 'no'} geometry, ignored (OCED reads the "
                             "logged POINTS of a machine)")
                continue
            from engine.clean.yield_clean import detect_columns
            det = detect_columns(list(info["fields"]))
            is_yield = bool(det["yield"] or det["yield_wet"] or det["wet_mass_lbac"])
            if is_yield:
                operation, op_label = "harvest", "Yield export"
            else:
                # OCED: a planter or sprayer as-applied layer, or any other point layer of a machine; cleaned by
                # engine/clean/applied3s.py (3-sigma on the attributes chosen) instead of the yield cleaning
                from engine.clean.applied3s import detect_operation
                op = detect_operation(list(info["fields"]))
                operation, op_label = op["operation"], op["label"]
            if stem + ".prj" not in low:
                notes.append(f"{os.path.relpath(path, root)}: no .prj next to it; the cleaning will refuse it "
                             "(it cannot measure distances without a coordinate system)")
            dbf = os.path.join(dp, low[stem + ".dbf"])
            kml = " (converted from KML)" if _KML_DIR.search(os.path.basename(dp)) else ""
            out.append({"kind": "export", "path": os.path.abspath(path), "n": int(info["features"]),
                        "columns": list(info["fields"]), "geometry_type": gt, "crs": info.get("crs"),
                        "same_key": (stem, int(info["features"]), os.path.getsize(dbf)),
                        "operation": operation, "yield": is_yield,
                        "label": (f"Point export{kml} · {f} · {int(info['features']):,} points" if is_yield else
                                  f"{op_label}{kml} · {f} · {int(info['features']):,} points")})
    return out


# data files that identify a raw dataset (a copy of the same dataset has the same names and sizes)
_RAW_DATA_EXT = {"jd_jdl": (".jdl",), "jd_gs3_rcd": (".fdl", ".fdd"), "cnh_cn1": None}    # None = every file


def _raw_signature(fid, root):
    exts = _RAW_DATA_EXT.get(fid)
    sig = set()
    for dp, fn in _walk(root):
        for f in fn:
            if f.lower().endswith(".zip") or (exts and not f.lower().endswith(exts)):
                continue
            try:
                sig.add((f.lower(), os.path.getsize(os.path.join(dp, f))))
            except OSError:
                continue
    return frozenset(sig)


def detect(roots) -> Candidates:
    """Candidates found under one root (str) or several. Never raises for unknown or broken content."""
    if isinstance(roots, (str, os.PathLike)):
        roots = [roots]
    roots = [os.path.abspath(str(r)) for r in roots]
    notes, cands, seen_exports, seen_raw = [], [], set(), set()
    for r in roots:
        if not os.path.isdir(r):
            notes.append(f"{r}: not a folder")
            continue
        for c in _exports(r, notes):
            key = os.path.normcase(c["path"])
            if key in seen_exports:
                continue
            seen_exports.add(key)
            twin = next((x for x in cands if x["kind"] == "export" and x["same_key"] == c["same_key"]), None)
            if twin is not None:
                notes.append(f"{c['path']}: same export as {twin['path']} (same name, points and .dbf size), "
                             "listed once")
                continue
            cands.append(c)
    for fid in DECODERS:
        try:
            mod = decoder(fid)
        except Exception as e:
            notes.append(f"decoder {fid} could not be loaded ({type(e).__name__}: {e}); that format is unavailable")
            continue
        for r in roots:
            if not os.path.isdir(r):
                continue
            try:
                pr = mod.probe(r)
            except Exception as e:
                notes.append(f"{mod.LABEL}: the probe failed on {r} ({type(e).__name__}: {e})")
                continue
            if pr is None:
                continue
            key = (fid, os.path.normcase(os.path.abspath(pr.root)))
            # the same dataset reached from two roots (a folder and the dest it was unpacked into) counts once
            if key in seen_raw:
                continue
            seen_raw.add(key)
            cands.append({"kind": "raw", "decoder": fid, "probe": pr, "label": f"{pr.label} · {pr.summary}"})
    # a raw dataset found again inside another candidate's folder (probes walk recursively, so the outer one already
    # covers it) is reported once per decoder
    by_fid = {}
    for c in cands:
        if c["kind"] == "raw":
            by_fid.setdefault(c["decoder"], []).append(c)
    drop = set()
    for fid, cs in by_fid.items():
        for a in cs:
            for b in cs:
                if a is b:
                    continue
                ra, rb = os.path.normcase(a["probe"].root), os.path.normcase(b["probe"].root)
                inside = ra != rb and (ra.startswith(rb.rstrip("\\/") + os.sep))
                if inside and a["probe"].n_files <= b["probe"].n_files:
                    drop.add(id(a))
    cands = [c for c in cands if id(c) not in drop]
    # the same raw dataset reached twice by different roots (a folder holding both the zips and their unpacked copy):
    # same decoder and the same data files by name and size, or one a subset of the other -> keep the larger once
    drop = set()
    raw = [c for c in cands if c["kind"] == "raw"]
    sigs = {}
    for i, a in enumerate(raw):
        for b in raw[i + 1:]:
            if a["decoder"] != b["decoder"] or id(a) in drop or id(b) in drop:
                continue
            sa = sigs.setdefault(id(a), _raw_signature(a["decoder"], a["probe"].root))
            sb = sigs.setdefault(id(b), _raw_signature(b["decoder"], b["probe"].root))
            if sa and sb and (sa <= sb or sb <= sa):
                small, big = (a, b) if len(sa) < len(sb) else (b, a)          # equal: keep the first
                drop.add(id(small))
                notes.append(f"{small['probe'].root}: same {small['decoder']} data files as {big['probe'].root}, "
                             "listed once")
    cands = [c for c in cands if id(c) not in drop]
    msg = ""
    if not cands:
        msg = "Nothing usable was recognised in the input.\n" + SUPPORTED_TEXT
    return Candidates(cands, notes, msg)
