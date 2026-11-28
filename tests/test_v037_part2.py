# -*- coding: utf-8 -*-
"""0.3.7 part 2, the app (Streamlit AppTest, synthetic data only): the three items of the recheck of part 1 and its
two minors.

* Step 3's boundary: removing the field boundary clears the per-file 'No boundary for this file' and 'own' choices,
  and the 'No boundary for this file' state offers the uploader / path / Use of the file's own boundary.
* A copied or moved work: the paths of the restored cleaning record are its own folder's, so Measure and 'Remove the
  small area' never write to or delete files of the work it was copied from, and a small area of 0.3.6 (its polygon
  file in the cleaning's small_area_input/) is found in the moved work.
* A small area of 0.3.6 given by its path (read in place; the record names the file only) is found again next to the
  input when it holds the record's polygons, and is not when the file there holds other polygons.

    python -m pytest -q tests/test_v037_part2.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import geopandas as gpd
from shapely.affinity import translate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import run as er  # noqa: E402
from tests.test_app_field_files import _open_both, _show, two  # noqa: E402,F401  (the fixture two)
from tests.test_v037_repair import _app, _run, field  # noqa: E402,F401  (the fixture field)


def _tk(at, prefix):
    return next(str(b.key) for b in at.button if str(b.key).startswith(prefix))[len(prefix):]


def test_no_boundary_for_a_file_offers_its_own_and_removing_the_field_boundary_clears_the_choices(two, tmp_path,
                                                                                                  monkeypatch):
    at = _app(tmp_path / "ws", monkeypatch)
    south, north = _open_both(at, two["folder"])
    at.text_input(key="ff_path_b").input(two["two_fields"])
    at.button(key="ff_use_b").click()
    _run(at)
    # the south file: 'No boundary for this file', then its own boundary given straight from that state
    _show(at, south)
    tk = _tk(at, "bnd_ff_none_")
    at.button(key=f"bnd_ff_none_{tk}").click()
    _run(at)
    assert any(i.value.startswith("No boundary for this file") for i in at.info)
    assert at.session_state["field_files"]["use"][south] == "none"
    at.text_input(key=f"bnd_path_{tk}").input(two["boundary"])
    at.button(key=f"bnd_use_{tk}").click()
    _run(at)
    assert at.session_state["boundary"][south]["name"] == os.path.basename(two["boundary"])
    assert at.session_state["field_files"]["use"][south] == "own"
    # the north file: 'No boundary for this file'; then the field boundary removed: both choices go with it
    _show(at, north)
    tkn = _tk(at, "bnd_ff_none_")
    at.button(key=f"bnd_ff_none_{tkn}").click()
    _run(at)
    assert at.session_state["field_files"]["use"] == {south: "own", north: "none"}
    at.button(key="ff_rm_b").click()
    _run(at)
    assert at.session_state["field_files"]["use"] == {}
    assert at.session_state["boundary"][south]["name"] == os.path.basename(two["boundary"])   # its own stays
    # the north file is not stuck: no 'No boundary' state left, the uploader / path / Use are there
    _show(at, north)
    assert not any(i.value.startswith("No boundary for this file") for i in at.info)
    at.text_input(key=f"bnd_path_{tkn}").input(two["own"])
    at.button(key=f"bnd_use_{tkn}").click()
    _run(at)
    assert at.session_state["boundary"][north]["name"] == "own.geojson"
    assert north not in at.session_state["field_files"]["use"]          # no field boundary: nothing to opt out of


def _clean_and_measure(at, poly):
    at.button(key="clean_one").click()
    _run(at)
    tag = at.session_state["active"]
    ka = next(str(t.key) for t in at.text_input if str(t.key).startswith("sa_path_"))[len("sa_path_"):]
    at.text_input(key=f"sa_path_{ka}").input(poly)                       # 0.4.0: path in step 1, Measure in step 5
    _run(at)                                                             # (drawn once a plot boundary is given)
    k = next(str(b.key) for b in at.button if str(b.key or "").startswith("sa_go_"))[len("sa_go_"):]
    at.button(key=f"sa_go_{k}").click()
    _run(at)
    assert at.session_state["cleaned"][tag]["R"]["small_area"]["method"] == "ground"
    return tag, k


def test_a_copied_work_measures_and_removes_in_its_own_folder(field, tmp_path, monkeypatch):
    at = _app(tmp_path / "ws1", monkeypatch)
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click()
    _run(at)
    tag, k = _clean_and_measure(at, field["poly"])
    at.button(key="work_save").click()
    _run(at)
    wd = at.session_state["workdir"]
    S0 = at.session_state["cleaned"][tag]["R"]["small_area"]
    csv0 = S0["files"]["csv"]
    assert os.path.normcase(csv0).startswith(os.path.normcase(wd))
    # a 0.3.6 small area too: its record in the cleaning JSON, its file in the cleaning's small_area_input/
    C = at.session_state["cleaned"][tag]
    copy = tmp_path / "ws2" / os.path.basename(wd)
    shutil.copytree(wd, copy)
    at2 = _app(tmp_path / "ws2", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    assert os.path.normcase(at2.session_state["workdir"]) == os.path.normcase(str(copy))
    R2 = at2.session_state["cleaned"][tag]["R"]
    for p in [R2["files"]["dir"], R2["files"]["flagged_zip"], R2["files"]["json"], R2["files"]["report_pdf"],
              *[v for v in R2["small_area"]["files"].values() if v]]:
        assert os.path.normcase(str(p)).startswith(os.path.normcase(str(copy))), p
    # Measure again in the copy: written there, the original's files untouched
    m0 = os.path.getmtime(csv0)
    k2 = _tk(at2, "sa_go_")                              # (the key of the copy's own clean file)
    at2.button(key=f"sa_go_{k2}").click()
    _run(at2)
    S2 = at2.session_state["cleaned"][tag]["R"]["small_area"]
    assert os.path.normcase(S2["files"]["csv"]).startswith(os.path.normcase(str(copy)))
    assert os.path.getmtime(csv0) == m0
    # Remove the small area in the copy: the copy's files go, the original's stay
    at2.button(key=f"sa_rm_{k2}").click()
    _run(at2)
    assert not os.path.exists(S2["files"]["csv"]) and os.path.exists(csv0)
    assert all(os.path.exists(v) for v in S0["files"].values() if v)
    # a small area of 0.3.6 in the moved work: found in the copy's small_area_input/, not the original's
    R = json.load(open(C["json"], encoding="utf-8"))
    sdir = os.path.join(R["files"]["dir"], "small_area_input")
    os.makedirs(sdir, exist_ok=True)
    p036 = shutil.copy(field["poly"], os.path.join(sdir, "plots.geojson"))
    er.small_area_after_clean(R, p036, "clip", log=lambda m: None)
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    W.pop("small_area", None)
    json.dump(W, open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8"))
    copy3 = tmp_path / "ws3" / os.path.basename(wd)
    shutil.copytree(wd, copy3)
    os.remove(p036)                                       # only the moved work has it now
    at3 = _app(tmp_path / "ws3", monkeypatch)
    at3.button(key="work_open").click()
    _run(at3)
    A = at3.session_state["small_area"][tag]
    assert os.path.normcase(A["path"]).startswith(os.path.normcase(str(copy3)))
    assert os.path.normcase(os.path.dirname(A["path"])).endswith(os.path.normcase(os.path.join(tag, "small_area_input")))
    assert not any("measured by an earlier version of OCED" in m.value for m in at3.info)


def test_a_036_small_area_given_by_its_path_is_found_again(field, tmp_path, monkeypatch):
    src = tmp_path / "in"
    src.mkdir()
    base = os.path.splitext(field["shp"])[0]
    for e in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        if os.path.exists(base + e):
            shutil.copy(base + e, src)
    poly = shutil.copy(field["poly"], src / "plots.geojson")
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(str(src / os.path.basename(field["shp"])))
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    tag = at.session_state["active"]
    at.button(key="work_save").click()
    _run(at)
    # what 0.3.6 left for a polygon file given by its path: the record only (file name), no small_area_input/
    C = at.session_state["cleaned"][tag]
    R = json.load(open(C["json"], encoding="utf-8"))
    er.small_area_after_clean(R, str(poly), "clip", log=lambda m: None, method="cleaned")
    R = json.load(open(C["json"], encoding="utf-8"))
    R["small_area"].pop("method", None)                  # a record of 0.3.6 has no method
    json.dump(R, open(C["json"], "w", encoding="utf-8"))
    assert not os.path.exists(os.path.join(R["files"]["dir"], "small_area_input"))
    # a file of that name holding other polygons there: not taken, said in the box
    keep = str(poly) + ".right"
    shutil.copy(poly, keep)
    g = gpd.read_file(poly)
    g["geometry"] = g.geometry.apply(lambda q: translate(q, 0.001, 0))
    os.remove(poly)
    g.to_file(poly, driver="GeoJSON")
    at3 = _app(tmp_path / "ws", monkeypatch)
    at3.button(key="work_open").click()
    _run(at3)
    assert tag not in at3.session_state["small_area"]
    assert any("measured by an earlier version of OCED" in m.value for m in at3.info)
    # the file given then, there again: found and kept with the file
    os.remove(poly)
    shutil.copy(keep, poly)
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    A = at2.session_state["small_area"][tag]
    assert os.path.normcase(A["path"]) == os.path.normcase(str(poly)) and A["rule"] == "clip"
    assert not any("measured by an earlier version of OCED" in m.value for m in at2.info)
    assert any("cleaned map average (0.3.6)" in str(m.value) for m in at2.markdown)


def test_a_036_small_area_given_by_path_is_adopted_beside_an_earlier_upload(field, tmp_path, monkeypatch):
    """0.3.6: a polygon file uploaded once (kept in the cleaning's small_area_input/), then the small area measured
    with another file given by its path (the record names that one only): the path-given file is found again and
    adopted, the earlier upload in small_area_input/ notwithstanding; the map's caption of that 0.3.6 record says
    that the table is the cleaned map average and that Measure gives grain / ground."""
    src = tmp_path / "in"
    src.mkdir()
    base = os.path.splitext(field["shp"])[0]
    for e in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        if os.path.exists(base + e):
            shutil.copy(base + e, src)
    poly = shutil.copy(field["poly"], src / "given.geojson")
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(str(src / os.path.basename(field["shp"])))
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    tag = at.session_state["active"]
    at.button(key="work_save").click()
    _run(at)
    C = at.session_state["cleaned"][tag]
    R = json.load(open(C["json"], encoding="utf-8"))
    sdir = os.path.join(R["files"]["dir"], "small_area_input")
    os.makedirs(sdir, exist_ok=True)
    shutil.copy(field["poly"], os.path.join(sdir, "earlier.geojson"))      # the earlier upload, another name
    er.small_area_after_clean(R, str(poly), "clip", log=lambda m: None, method="cleaned")
    R = json.load(open(C["json"], encoding="utf-8"))
    R["small_area"].pop("method", None)                  # a record of 0.3.6 has no method
    json.dump(R, open(C["json"], "w", encoding="utf-8"))
    assert R["small_area"]["file"] == "given.geojson"
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    A = at2.session_state["small_area"][tag]
    assert os.path.normcase(A["path"]) == os.path.normcase(str(poly)) and A["rule"] == "clip"
    assert not any("measured by an earlier version of OCED" in m.value for m in at2.info)
    assert any("cleaned map average (0.3.6)" in str(m.value) for m in at2.markdown)
    caps = [str(c.value) for c in at2.caption]
    assert any("Measure gives grain / ground beside it" in c for c in caps)
    assert not any("Grain / ground counts every one of them" in c for c in caps)
