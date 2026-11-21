# -*- coding: utf-8 -*-
"""0.3.7, the field files of step 1 (app/oced.py) through Streamlit's AppTest, synthetic data only: one field
boundary and one management zone map given once for every harvest file of the work; the boundary resolver (a file's
own wins, 'No boundary for this file', a file the boundary does not cover gets none, a boundary file of several fields
gives each file the polygon holding most of its readings); the files given before Open, Start over and Open other
data; a polygon file found in the input (offered, never applied by itself); the zone map in both replays of two files;
saved works; step 3's boxes outside the folded settings after a cleaning.

    python -m pytest -q tests/test_app_field_files.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import geopandas as gpd
import numpy as np
import pytest
from shapely.affinity import translate
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import M_PER_DEG_LAT, _rect, make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
NORTH_M = 450.0                          # the second file: the same passes 450 m north (inside 'Synthetic 2')


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _run(at):
    at.run()
    assert not at.exception, [str(e.value)[:800] for e in at.exception]


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """A folder with two point exports: the synthetic field and the same passes 450 m north (a second field), the
    single boundary, the boundary file of the two fields, and a zone map of two zones over both."""
    d = str(tmp_path_factory.mktemp("two"))
    F = make_field(os.path.join(d, "f"))
    data = os.path.join(d, "data")
    os.makedirs(data)
    g = gpd.read_file(F["shp"])
    g.to_file(os.path.join(data, "Field_south.shp"), engine="pyogrio")
    gn = g.copy()
    gn["geometry"] = gn.geometry.apply(lambda p: translate(p, 0, NORTH_M / M_PER_DEG_LAT))
    gn["Machine"] = "COMBINE-B"
    gn.to_file(os.path.join(data, "Field_north.shp"), engine="pyogrio")
    zp = os.path.join(d, "zones.geojson")
    gpd.GeoDataFrame({"zone": [1, 2]}, geometry=[_rect(-10, 250, -20, 700), _rect(250, 520, -20, 700)],
                     crs="EPSG:4326").to_file(zp, driver="GeoJSON")
    own = os.path.join(d, "own.geojson")
    gpd.GeoDataFrame({"Name": ["own"]}, geometry=[_rect(-2, 300, NORTH_M - 5, NORTH_M + 220)],
                     crs="EPSG:4326").to_file(own, driver="GeoJSON")          # part of the north field
    return {"folder": data, "boundary": F["boundary"], "two_fields": F["two_fields"], "zones": zp, "own": own}


def _open_both(at, folder):
    """Open the folder and import both exports (the list of datasets: one, then the other)."""
    at.text_input(key="path_in").input(folder)
    at.button(key="open_btn").click()
    _run(at)
    for i in (0, 1):
        at.selectbox(key="cand_idx").set_value(i)
        _run(at)
    tags = list(at.session_state["datasets"])
    assert len(tags) == 2, tags
    south = next(t for t in tags if "south" in t.lower())
    north = next(t for t in tags if "north" in t.lower())
    return south, north


def _show(at, tag):
    at.session_state["active"] = tag
    at.session_state["active_pick"] = tag
    _run(at)


def _clean_all(at):
    at.button(key="clean_all").click()
    _run(at)
    assert not at.error, [e.value for e in at.error]


def test_one_field_boundary_for_every_file_given_before_open(two, tmp_path, monkeypatch):
    """The boundary typed in the panel before Open is the work's field boundary: the file it covers is clipped to it
    (the record's field of interest is the field file), step 3 says 'From the field files'; the file 450 m north is
    not covered: no boundary, and step 3 says so."""
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="ff_path_b").input(two["boundary"])
    _run(at)
    assert not (at.session_state["field_files"] or {}).get("boundary")         # nothing applied before Open
    south, north = _open_both(at, two["folder"])
    FB = at.session_state["field_files"]["boundary"]
    assert FB and os.path.normcase(FB["path"]) == os.path.normcase(os.path.abspath(two["boundary"]))
    assert "ff_path_b" not in at.session_state.filtered_state                 # the panel is empty again
    _show(at, south)
    assert any(s.value.startswith("From the field files (step 1): Synthetic_boundary.geojson") for s in at.success)
    _show(at, north)
    assert any("The field files' boundary holds 0 % of this file's readings: not used for it" in i.value
               for i in at.info)
    _clean_all(at)
    Cs, Cn = at.session_state["cleaned"][south], at.session_state["cleaned"][north]
    assert os.path.normcase(Cs["R"]["settings"]["aoi"]["file"]) == os.path.normcase(os.path.abspath(two["boundary"]))
    assert not (Cn["R"]["settings"].get("aoi") or {}).get("file")
    assert Cs["R"]["n_read"] > Cs["R"]["n_in"]                                # the clip set readings aside


def test_several_fields_own_boundary_no_boundary_and_clean_again(two, tmp_path, monkeypatch):
    """A boundary file of two fields: each file gets the polygon holding most of its readings. An own boundary wins;
    'No boundary for this file' cleans without the clip; 'Use the field files' boundary' brings it back. Changing the
    field boundary after the cleaning says 'clean again' for the files that used it only."""
    at = _app(tmp_path / "ws", monkeypatch)
    south, north = _open_both(at, two["folder"])
    at.text_input(key="ff_path_b").input(two["two_fields"])
    at.button(key="ff_use_b").click()
    _run(at)
    FB = at.session_state["field_files"]["boundary"]
    assert FB["needs_choice"] and len(FB["fields"]) == 2
    _clean_all(at)
    for t, k in ((south, 1), (north, 2)):
        A = at.session_state["cleaned"][t]["R"]["settings"]["aoi"]
        assert os.path.normcase(A["file"]) == os.path.normcase(os.path.abspath(two["two_fields"]))
        assert A["feature"] == k, (t, A["feature"])
    assert at.session_state["field_files"]["feature"] == {south: [1], north: [2]}
    # the north file: its own boundary wins; the south file: no boundary for this file
    _show(at, north)
    tk_n = next(str(b.key) for b in at.button if str(b.key).startswith("bnd_ff_other_"))[len("bnd_ff_other_"):]
    at.button(key=f"bnd_ff_other_{tk_n}").click()
    _run(at)
    at.text_input(key=f"bnd_path_{tk_n}").input(two["own"])
    at.button(key=f"bnd_use_{tk_n}").click()
    _run(at)
    assert at.session_state["boundary"][north]["name"] == "own.geojson"
    assert at.session_state["field_files"]["use"][north] == "own"
    assert any("This file's own boundary" in str(c.value) for c in at.caption)
    at.button(key="clean_one").click()
    _run(at)
    assert os.path.normcase(at.session_state["cleaned"][north]["R"]["settings"]["aoi"]["file"]) == os.path.normcase(
        os.path.abspath(two["own"]))
    _show(at, south)
    tk_s = next(str(b.key) for b in at.button if str(b.key).startswith("bnd_ff_none_"))[len("bnd_ff_none_"):]
    at.button(key=f"bnd_ff_none_{tk_s}").click()
    _run(at)
    assert any(i.value.startswith("No boundary for this file") for i in at.info)
    at.button(key="clean_one").click()
    _run(at)
    assert not (at.session_state["cleaned"][south]["R"]["settings"].get("aoi") or {}).get("file")
    at.button(key=f"bnd_ff_back_{tk_s}").click()
    _run(at)
    assert south not in at.session_state["field_files"]["use"]
    at.button(key="clean_one").click()
    _run(at)
    assert at.session_state["cleaned"][south]["R"]["settings"]["aoi"]["feature"] == 1
    # the field boundary changed: the south file (it uses it) is to clean again, the north one (its own) is not
    at.button(key="ff_chg_b").click()
    _run(at)
    at.text_input(key="ff_path_b").input(two["boundary"])
    at.button(key="ff_use_b").click()
    _run(at)
    _show(at, south)
    assert any("changed since this file was cleaned" in w.value for w in at.warning)
    _show(at, north)
    assert not any("changed since this file was cleaned" in w.value for w in at.warning)


def test_pending_files_start_over_and_open_other_data(two, tmp_path, monkeypatch):
    """A failed open keeps the files given in the panel; Start over empties them; Open other data does not carry the
    old work's field files over."""
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="ff_path_b").input(two["boundary"])
    at.text_input(key="ff_path_z").input(two["zones"])
    _run(at)
    at.text_input(key="path_in").input(str(tmp_path / "nothing_here"))
    at.button(key="open_btn").click()
    _run(at)
    assert at.error and at.session_state["ff_path_b"] == two["boundary"]       # the open failed: still in the panel
    at.button(key="start_over").click()
    _run(at)
    assert not at.session_state.filtered_state.get("ff_path_b") and not at.session_state.filtered_state.get(
        "ff_path_z")
    # the files given, then Open: the work has them; another input opened: none of them
    at.text_input(key="ff_path_b").input(two["boundary"])
    at.text_input(key="ff_path_z").input(two["zones"])
    _run(at)
    at.text_input(key="path_in").input(os.path.join(two["folder"], "Field_south.shp"))
    at.button(key="open_btn").click()
    _run(at)
    F = at.session_state["field_files"]
    assert F["boundary"]["name"] == "Synthetic_boundary.geojson" and F["zones"]["name"] == "zones.geojson"
    at.text_input(key="path_in").input(os.path.join(two["folder"], "Field_north.shp"))
    at.button(key="open_btn").click()
    _run(at)
    F2 = at.session_state["field_files"]
    assert not F2.get("boundary") and not F2.get("zones")


def test_a_polygon_file_found_in_the_input_is_offered_never_applied(two, tmp_path, monkeypatch):
    """A folder with a point export, a boundary shapefile and a yield export of polygons: the boundary is listed
    under 'Found in the input' and applied only by 'Use as the boundary'; the polygon yield export is not listed."""
    d = tmp_path / "input"
    shutil.copytree(two["folder"], d)
    for f in os.listdir(d):
        if f.startswith("Field_north"):
            os.remove(d / f)
    gpd.read_file(two["boundary"]).to_file(d / "Field_boundary.shp")
    polys = [box(-114.1 + i * 1e-4, 51.8, -114.1 + (i + 1) * 1e-4, 51.8001) for i in range(30)]
    gpd.GeoDataFrame({"Yld_Vol_Dr": np.linspace(40, 80, 30), "Moisture__": 14.0}, geometry=polys,
                     crs="EPSG:4326").to_file(d / "Yield_polygons.shp")
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(str(d))
    at.button(key="open_btn").click()
    _run(at)
    if at.session_state["cands"] is not None and len(at.session_state["cands"]) > 1:
        at.selectbox(key="cand_idx").set_value(0)
        _run(at)
    F = at.session_state["field_files"]
    names = [f["name"] for f in F["found"]]
    assert names == ["Field_boundary.shp"], names
    assert not F.get("boundary")                                                # never applied by itself
    assert any("Found in the input" in str(c.value) for c in at.caption)
    at.button(key="ff_found_b_0").click()
    _run(at)
    assert at.session_state["field_files"]["boundary"]["name"] == "Field_boundary.shp"


def test_zone_map_of_the_work_in_both_replays_and_a_files_own(two, tmp_path, monkeypatch):
    """The work's zone map shows in the replay of every file ('From the field files'); a file's own zone map wins;
    Remove in the replay removes only the own one."""
    from tests.test_replay_app import _iframes, _payload
    at = _app(tmp_path / "ws", monkeypatch)
    south, north = _open_both(at, two["folder"])
    at.text_input(key="ff_path_z").input(two["zones"])
    at.button(key="ff_use_z").click()
    _run(at)
    for t in (south, north):
        _show(at, t)
        keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_imp_")]
        for k in keys:
            at.session_state[k] = True
        _run(at)
        fr = _iframes(at)
        assert fr and all(_payload(f.proto.srcdoc)["zones"]["file"] == "zones.geojson" for f in fr)
        assert any(s.value.startswith("From the field files (step 1): zones.geojson") for s in at.success)
    # the north file: its own zone map (the boundary file of two fields, column Name) wins
    import hashlib
    imp = "imp_" + hashlib.md5(str(at.session_state["datasets"][north]["shp"]).encode("utf-8")).hexdigest()[:8]
    at.button(key=f"zm_other_b_{imp}").click()
    at.session_state[f"replay_box_{imp}"] = True
    _run(at)
    at.session_state[f"replay_box_{imp}"] = True
    at.text_input(key=f"zm_path_{imp}").input(two["two_fields"])
    at.button(key=f"zm_use_{imp}").click()
    _run(at)
    at.session_state[f"replay_box_{imp}"] = True
    _run(at)
    assert _payload(_iframes(at)[0].proto.srcdoc)["zones"]["file"] == "Synthetic_two_fields.geojson"
    at.session_state[f"replay_box_{imp}"] = True
    at.button(key=f"zm_rm_{imp}").click()
    _run(at)
    at.session_state[f"replay_box_{imp}"] = True
    _run(at)
    assert _payload(_iframes(at)[0].proto.srcdoc)["zones"]["file"] == "zones.geojson"
    assert at.session_state["field_files"]["zones"]["name"] == "zones.geojson"   # the work's stays


def test_saved_work_keeps_the_field_files_and_says_a_missing_one(two, tmp_path, monkeypatch):
    """Saved and opened again: the field boundary, the zone map and the choices per file come back; a moved work
    folder opens them from its own copy; a field file deleted on disk is one line of the 'Opened' message; a work of
    0.3.5 (no field_files) opens as before."""
    src = tmp_path / "src"
    shutil.copytree(two["folder"], src)
    zp = shutil.copy(two["zones"], tmp_path / "zones_copy.geojson")
    at = _app(tmp_path / "ws", monkeypatch)
    south, north = _open_both(at, str(src))
    at.text_input(key="ff_path_b").input(two["two_fields"])
    at.button(key="ff_use_b").click()
    _run(at)
    at.text_input(key="ff_path_z").input(str(zp))
    at.button(key="ff_use_z").click()
    _run(at)
    _show(at, south)
    _show(at, north)
    at.button(key="work_save").click()
    _run(at)
    wd = at.session_state["workdir"]
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert W["field_files"]["boundary"]["path"] and W["field_files"]["zones"]["name"] == "zones_copy.geojson"
    assert W["field_files"]["feature"] == {south: [1], north: [2]}
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    F = at2.session_state["field_files"]
    assert F["boundary"]["name"] == "Synthetic_two_fields.geojson" and F["zones"]["name"] == "zones_copy.geojson"
    assert F["feature"] == {south: [1], north: [2]}
    # the zone map deleted on disk: one line of the message, the work opens
    os.remove(zp)
    at3 = _app(tmp_path / "ws", monkeypatch)
    at3.button(key="work_open").click()
    _run(at3)
    assert ("the field files' zone map" in str((at3.session_state["work_msg"] or ("", ""))[1])
            or any("the field files' zone map" in w.value for w in at3.warning))
    # a work of 0.3.5: no field_files key at all
    W.pop("field_files", None)
    json.dump(W, open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8"))
    at4 = _app(tmp_path / "ws", monkeypatch)
    at4.button(key="work_open").click()
    _run(at4)
    F4 = at4.session_state["field_files"]
    assert not F4.get("boundary") and not F4.get("zones") and len(at4.session_state["datasets"]) == 2


def test_a_field_file_uploaded_is_kept_in_the_moved_work(two, tmp_path, monkeypatch):
    """The field boundary kept inside the work (field_files/boundary/) is found again when the work folder moves."""
    from engine import works as ew
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(os.path.join(two["folder"], "Field_south.shp"))
    at.button(key="open_btn").click()
    _run(at)
    wd = at.session_state["workdir"]
    kept = os.path.join(wd, "field_files", "boundary")
    os.makedirs(kept)
    p = shutil.copy(two["boundary"], kept)
    at.text_input(key="ff_path_b").input(p)
    at.button(key="ff_use_b").click()
    _run(at)
    at.button(key="work_save").click()
    _run(at)
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert W["field_files"]["boundary"]["path"] == "field_files/boundary/Synthetic_boundary.geojson"
    new = tmp_path / "moved" / os.path.basename(wd)
    shutil.copytree(wd, new)
    rec = ew.load_work(str(new))
    assert os.path.normcase(rec["field_files"]["boundary"]["path"]) == os.path.normcase(
        os.path.join(str(new), "field_files", "boundary", "Synthetic_boundary.geojson"))


def test_step3_boxes_stay_open_after_a_cleaning(two, tmp_path, monkeypatch):
    """After a cleaning only the method folds into 'Settings · ...': the boundary box, the grower's weight and the
    combine factor are outside it (the AppTest element tree); the method's widgets are inside it."""
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(os.path.join(two["folder"], "Field_south.shp"))
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    # a keyed expander is a 'status' block in AppTest's tree (its label, its children)
    def walk(n, out):
        out.append(n)
        for c in (getattr(n, "children", {}) or {}).values():
            walk(c, out)
        return out

    nodes = walk(at._tree, [])
    exps = [n for n in nodes if getattr(n, "type", None) in ("status", "expander")
            and str(getattr(n, "label", "")).startswith("Settings · ")]
    assert len(exps) == 1, [getattr(n, "label", "") for n in nodes if getattr(n, "type", None) == "status"]
    inside = {getattr(n, "key", None) for n in walk(exps[0], [])}
    assert {"k_sd", "max_passes", "t_clip", "t_swath"} <= inside
    assert not any(str(k).startswith(("bnd_path_", "bnd_use_", "gw_w_", "cf_on_")) for k in inside)
    assert any(str(getattr(w, "key", "")).startswith("bnd_path_") for w in at.text_input)
    assert any(str(getattr(w, "key", "")).startswith("gw_w_") for w in at.number_input)
