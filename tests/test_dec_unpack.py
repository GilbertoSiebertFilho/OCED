# -*- coding: utf-8 -*-
"""Unpacking and detection (engine/formats/detect.py) on synthetic inputs: a zip beside its own unpacked copy is read
once (in place and with copy_folders), names Windows treats specially are made legal while zip slip is still refused,
a failed unpack leaves nothing behind, one harvest given partly zipped and partly loose is one dataset, files beyond
the Windows path limit are named, and an Operations Center export carries the product SMS gives its crop.

    python -m pytest -q tests/test_dec_unpack.py
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import detect  # noqa: E402
from engine.formats import ops_sections as ops  # noqa: E402
from tests import synthetic_jdl as S  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.test_inputs import _deere_metadata, _ops_frame, _write_points  # noqa: E402

QUIET = lambda m: None  # noqa: E731
WINDOWS = os.name == "nt"


def _zip(folder, zpath, prefix=""):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, files in os.walk(folder):
            for f in files:
                p = os.path.join(d, f)
                z.write(p, os.path.join(prefix, os.path.relpath(p, folder)).replace("\\", "/"))
    return zpath


def _export_zip(tmp_path, members):
    """A zip holding the synthetic export's files under the given member stems ({stem: folder or ''})."""
    f = make_field(str(tmp_path / "src"))
    zp = str(tmp_path / "in.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for stem in members:
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                p = os.path.splitext(f["shp"])[0] + ext
                if os.path.exists(p):
                    z.write(p, stem + ext)
    return zp, f["n"]


def test_a_zip_beside_its_unpacked_copy_is_read_once(tmp_path):
    """V-exports-2 (b): a folder that holds a zip and the folder the zip unpacks to: read in place, the zip is not
    unpacked and the export is listed once; with copy_folders the same."""
    f = make_field(str(tmp_path / "data" / "Harvest"))
    _zip(os.path.dirname(f["shp"]), str(tmp_path / "data" / "Harvest.zip"))
    for copy in (False, True):
        log = []
        dest = str(tmp_path / f"work_{copy}" / "input")
        roots = detect.unpack([str(tmp_path / "data")], dest, copy_folders=copy, log=log.append)
        cands = detect.detect(roots)
        assert [c["n"] for c in cands if c["kind"] == "export"] == [f["n"]], (copy, [c["label"] for c in cands])
        assert any("holds the same files, not unpacked" in m for m in log)
        assert not os.path.exists(os.path.join(dest, "data__zips"))


@pytest.mark.skipif(not WINDOWS, reason="names Windows treats specially")
def test_names_windows_treats_specially_are_made_legal(tmp_path):
    """A-19: a zip whose stem ends with a space, given by path; a folder in a zip that ends with a space; a ':' and a
    '?' in a name; a member called NUL: every one opens, under a legal name. Zip slip is still refused."""
    zp, n = _export_zip(tmp_path, ["Harvest /Harvest", "Harvest 10:30", "a?b/Harvest", "NUL"])
    spaced = str(tmp_path / "Synthetic field .zip")
    shutil.copyfile(zp, spaced)
    cands = detect.detect(detect.unpack([spaced], str(tmp_path / "w" / "input"), log=QUIET))
    names = sorted(os.path.basename(c["path"]) for c in cands if c["kind"] == "export")
    # 'Harvest /Harvest' and 'a?b/Harvest' are the same export (same stem, points and .dbf): listed once
    assert names == ["Harvest 10_30.shp", "Harvest.shp", "_NUL.shp"] and all(c["n"] == n for c in cands)
    base = tmp_path / "w" / "input" / "Synthetic field"
    assert (base / "Harvest" / "Harvest.shp").is_file() and (base / "a_b" / "Harvest.shp").is_file()
    assert any("same export as" in x for x in cands.notes)
    # a nested zip whose stem ends with a space
    outer = str(tmp_path / "outer.zip")
    with zipfile.ZipFile(outer, "w") as z:
        z.write(zp, "combine 1 .zip")
    cands = detect.detect(detect.unpack([outer], str(tmp_path / "w2" / "input"), log=QUIET))
    assert len([c for c in cands if c["kind"] == "export"]) == 3
    for bad in ("../x.shp", "a/../../x.shp", "/abs.shp", "C:/x.shp", "c:x.shp", ".. /x.shp", "a/.../x.shp", "..."):
        assert detect._safe_target(str(tmp_path / "base"), bad) is None, bad
    assert detect.legal_part('a<b>c:d"e|f?g*h') == "a_b_c_d_e_f_g_h" and detect.legal_part("LPT1.txt") == "_LPT1.txt"
    assert detect.legal_part("name. ") == "name" and detect.legal_part("CONSOLE") == "CONSOLE"


def test_a_failed_unpack_leaves_nothing_behind(tmp_path):
    """A-2 (4): the file system refuses a member (a folder that has a file's name): the ValueError says it is not the
    zip, and what the call unpacked before is removed (the work folder's earlier content stays)."""
    good = str(tmp_path / "good.zip")
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("x/1.txt", b"one")
    clash = str(tmp_path / "clash.zip")
    with zipfile.ZipFile(clash, "w") as z:
        z.writestr("a", b"a file")
        z.writestr("a/b.txt", b"needs a folder with the name of that file")
    dest = tmp_path / "work" / "input"
    dest.mkdir(parents=True)
    (dest / "earlier.txt").write_text("kept")
    with pytest.raises(ValueError) as err:
        detect.unpack([good, clash], str(dest), log=QUIET)
    assert "the file system refused" in str(err.value) and "damaged" not in str(err.value)
    assert sorted(os.listdir(dest)) == ["earlier.txt"]


def _card(folder, vin, monkeypatch, offset=0):
    import types
    import uuid
    monkeypatch.setattr(S, "VIN", vin)
    monkeypatch.setattr(S, "uuid", types.SimpleNamespace(UUID=lambda int: uuid.UUID(int=int + offset)))
    return S.make_card(str(folder))


def test_one_harvest_partly_zipped_partly_loose_is_one_dataset(tmp_path, monkeypatch):
    """A-18: a folder with one combine's logs unpacked and another combine's logs still zipped, given by path, and the
    same as an upload (a zip and loose logs in one folder): one raw dataset with both combines, not two datasets of
    the same field."""
    a = _card(tmp_path / "a", "1SYNTH000TEST000A", monkeypatch)
    b = _card(tmp_path / "b", "1SYNTH000TEST000B", monkeypatch, offset=16)
    mixed = tmp_path / "mixed"
    shutil.copytree(a["root"], mixed / "A")
    _zip(b["root"], str(mixed / "B.zip"))
    log = []
    cands = er.open_input([str(mixed)], str(tmp_path / "work"), log=log.append)
    raw = [c for c in cands if c["kind"] == "raw"]
    assert len(raw) == 1 and len(raw[0]["probe"].machines) == 2, [c["label"] for c in cands]
    assert any("both loose and inside its zip" in m for m in log)
    units = er.list_units(raw[0])
    assert sorted(u.machine for u in units) == ["1SYNTH000TEST000A", "1SYNTH000TEST000B"]
    # a folder holding only zips, or only loose logs, is read as before (in place, no copy)
    only = tmp_path / "only_loose"
    shutil.copytree(a["root"], only / "A")
    roots = detect.unpack([str(only)], str(tmp_path / "work2" / "input"), log=QUIET)
    assert str(only) in roots


@pytest.mark.skipif(not WINDOWS, reason="the 259-character limit is Windows'")
def test_files_beyond_the_path_limit_are_named(tmp_path):
    """A-2 (5): a folder read in place with a file beyond 259 characters: the note says it is not read."""
    deep = os.path.join(str(tmp_path / "in"), *(["d" * 40] * 6))
    os.makedirs(detect._long(deep))
    with open(detect._long(os.path.join(deep, "x" * 30 + ".shp")), "wb") as fh:
        fh.write(b"0")
    assert detect.files_beyond_limit(str(tmp_path / "in")) == 1
    cands = detect.detect([str(tmp_path / "in")])
    assert any("1 file(s) in it have a path longer than the 259 characters" in n for n in cands.notes)


def test_an_operations_center_export_carries_what_sms_gives_its_crop(tmp_path):
    """UPDATE 4: the export's metadata names the crop (CropName / CropId): the candidate carries monitor_product with
    SMS's values for it (Wheat (Hard Red Spring): 60 lb/bu, 13.5 %, 5-10,000 bu/ac); a section-element export keeps
    them through the collapse (the metadata is copied beside the per-second file)."""
    shp = _write_points(_ops_frame(60), str(tmp_path / "in" / "Ops_Harvest_2026-09-14_00.shp"))
    _deere_metadata(shp)
    cands = detect.detect(str(tmp_path / "in"))
    mp = cands[0]["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"], mp["min_yield"], mp["max_yield"]) == (
        "wheat", 60.0, 13.5, 5.0, 10_000.0)
    assert "Deere-Metadata.json" in mp["source"]
    _deere_metadata(shp, crop="Lentils")
    mp = detect.detect(str(tmp_path / "in"))[0]["monitor_product"]
    assert mp["crop"] == "lentils" and mp["dry_moisture_pct"] is None
    df = _ops_frame(40)
    rows = []
    for k in range(3):                                          # three header elements per second
        d = df.copy()
        d["SECTIONID"] = k
        d["SWATHWIDTH"] = 40.0 / 3
        d["y"] = (k - 1) * 4.0
        rows.append(d)
    import pandas as pd
    sec = _write_points(pd.concat(rows, ignore_index=True), str(tmp_path / "sec" / "Sec_Harvest_2026-09-14_00.shp"))
    _deere_metadata(sec, crop="Barley")
    out = str(tmp_path / "out" / "per_second.shp")
    info = ops.collapse(sec, out, log=QUIET)
    assert info["crop"] == "Barley" and info["monitor_product"]["dry_moisture_pct"] == 15.0
    assert os.path.isfile(str(tmp_path / "out" / "per_second-Deere-Metadata.json"))
    assert detect.detect(str(tmp_path / "out"))[0]["crop"] == "Barley"
    assert len(pyogrio.read_dataframe(out, read_geometry=False)) == 40


def test_a_section_export_names_its_combines_by_their_serials(tmp_path):
    """VA-14: the Machine column of an Operations Center export holds the combine's index ('1', '2'); its Deere
    metadata gives each index its serial (MachineUsage), the name SMS gives the datasets: the per-second readings of
    the collapse carry the serial (an index without one keeps its value), so that the per-combine cleaning, the clean
    file and the ISOXML devices name the combines."""
    import json
    import pandas as pd
    rows = []
    for m in (1, 2):
        df = _ops_frame(20)
        df["Machine"] = m
        df["y"] = df["y"] + 30.0 * m
        for k in range(2):
            d = df.copy()
            d["SECTIONID"] = k
            d["SWATHWIDTH"] = 20.0
            d["y"] = d["y"] + (k - 0.5) * 6.0
            rows.append(d)
    sec = _write_points(pd.concat(rows, ignore_index=True), str(tmp_path / "sec" / "Sec_Harvest_2026-09-14_00.shp"))
    _deere_metadata(sec, crop="Barley")
    mp = os.path.splitext(sec)[0] + "-Deere-Metadata.json"
    meta = json.load(open(mp, encoding="utf-8"))
    meta["MachineUsage"] = {"1": {"MachineSerial": "SYNTHVIN000000001"}, "2": {"MachineSerial": ""}}
    json.dump(meta, open(mp, "w", encoding="utf-8"))
    out = str(tmp_path / "out" / "per_second.shp")
    info = ops.collapse(sec, out, log=QUIET)
    d = pyogrio.read_dataframe(out, read_geometry=False)
    assert info["machines_renamed"] == {"1": "SYNTHVIN000000001"} and len(d) == 40
    assert d["Machine"].astype(str).value_counts().to_dict() == {"SYNTHVIN000000001": 20, "2": 20}
