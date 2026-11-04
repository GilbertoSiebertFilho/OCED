# -*- coding: utf-8 -*-
"""OCED end to end on a synthetic field (tests/synthetic.py): the engine with the boundary and the grower's weight,
and the app itself through Streamlit's AppTest (open a point export, the attribute buttons, the boundary of the file,
the grower's data, the SMS 3-sigma cleaning, the clean shapefile with and without the adjusted yields).

    python -m pytest -q tests
"""
from __future__ import annotations

import ast
import glob
import os
import shutil
import sys

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from tests.synthetic import make_applied, make_field  # noqa: E402
from engine.clean import applied3s as a3  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("data")))


def _app_function(name):
    """One function of app/oced.py, without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {}
    exec(compile(ast.Module([fn], []), APP, "exec"), ns)
    return ns[name]


def test_engine_clip_and_grower_weight(field, tmp_path):
    wd = er.new_workdir(str(tmp_path), "syn")
    cand = er.open_input([field["shp"]], wd)[0]
    assert cand["kind"] == "export"
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": field["boundary"], "buffer_m": 0.01, "clip_output": True, "feature": None},
         "scale_ticket": {"value": 110_000, "unit": "lb", "basis": "wet", "moisture_pct": None, "note": None},
         "test_weight_lb_bu": 60.0}
    R = er.clean(cand["path"], str(tmp_path / "out"), S, log=lambda m: None)
    assert R["n_read"] == field["n"]
    assert R["n_in"] == field["n_inside"]                      # S1: the readings beyond the boundary set aside
    assert R["sms3sigma"]["clip"]["sms_clip_equivalent"] == field["n"] - field["n_inside"]
    assert 0 < R["removed_pct"] < 10
    L = R["level"]
    assert L["ticket_bu"] == pytest.approx(110_000 / 60.0)
    assert L["factor"] == pytest.approx(L["scale_ticket_bu"] / L["export_total_bu"])
    assert L["closure"]["verdict"]
    fields = list(pyogrio.read_info(R["files"]["difm_ready_shp"])["fields"])
    assert {"Yld_Level", "Wdth_Raw", "Swath_Scl"} <= set(fields)


def test_dbf_drop_fields_keeps_every_other_value(field, tmp_path):
    drop = _app_function("dbf_drop_fields")
    src = os.path.splitext(field["shp"])[0]
    dst = str(tmp_path / "copy")
    for e in er.SHP_EXTS:
        if os.path.exists(src + e):
            shutil.copyfile(src + e, dst + e)
    a = pyogrio.read_dataframe(src + ".shp")
    assert drop(dst + ".dbf", ["Yld_Mass_D", "Elevation_"]) == ["Elevation_", "Yld_Mass_D"]
    b = pyogrio.read_dataframe(dst + ".shp")
    assert list(b.columns) == [c for c in a.columns if c not in ("Yld_Mass_D", "Elevation_")]
    assert all(a[c].equals(b[c]) for c in b.columns if c != "geometry")
    assert a.geometry.equals(b.geometry)
    assert drop(dst + ".dbf", ["Yld_Mass_D"]) == []


def test_two_fields_need_a_choice(field):
    P = er.read_plan(field["two_fields"])
    assert P["needs_choice"] and [f["index"] for f in P["fields"]] == [1, 2]
    assert not er.read_plan(field["two_fields"], feature=1)["needs_choice"]


def _by_key(widgets, prefix):
    return next(w for w in widgets if str(w.key or "").startswith(prefix))


@pytest.mark.parametrize("use", ["validate", "adjust"])
def test_app_end_to_end(field, tmp_path, monkeypatch, use):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    # step 2: the attribute buttons, one per attribute, dry yield first
    pills = _by_key(at.button_group, "attr_raw_")
    assert pills.value == "Yld_Vol_Dr"
    pills.set_value("Moisture__").run()
    assert not at.exception
    # step 3: the boundary of the file and the grower's data
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    assert not at.exception, at.exception
    assert any("Synthetic_boundary.geojson" in s.value for s in at.success)
    _by_key(at.number_input, "gw_w_").set_value(110_000.0).run()
    _by_key(at.number_input, "gw_tw_").set_value(60.0).run()
    _by_key(at.button_group, "gw_use_").set_value(use).run()
    assert not at.exception, at.exception
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    steps = next(d.value for d in at.dataframe if "filter" in d.value.columns)
    assert list(steps["filter"]).count("S1") == 1
    assert steps.iloc[0]["filter"] == "S1" and steps.iloc[0]["removed"] == field["n"] - field["n_inside"]
    tabs = [t.label for t in at.tabs]
    assert "Grower's data" in tabs
    assert any(m.label == "Clipped (S1)" and m.value == f"{field['n'] - field['n_inside']:,}" for m in at.metric)
    clean = glob.glob(str(tmp_path / "ws" / "*" / "clean_shapefiles" / "*_clean.shp"))
    assert len(clean) == 1
    cols = list(pyogrio.read_info(clean[0])["fields"])
    assert ("Yld_Level" in cols) == (use == "adjust")
    assert pyogrio.read_info(clean[0])["features"] < field["n_inside"]
    assert os.path.exists(clean[0][:-4] + ".zip")
    # the report says which column to map, and it is a column of the clean file
    import json
    import pymupdf
    rec = json.load(open(glob.glob(str(tmp_path / "ws" / "*" / "clean" / "*" / "*_cleaning.json"))[0], encoding="utf-8"))
    pdf = glob.glob(str(tmp_path / "ws" / "*" / "clean" / "*" / "*_cleaning_report.pdf"))[0]
    text = " ".join(pg.get_text() for pg in pymupdf.open(pdf)).replace("\n", " ")
    if use == "adjust":
        assert "map Yld_Level as the yield column" in text
    else:
        assert rec["yield_column_for_difm"] == "Yld_Vol_Dr" and "Yld_Level" not in rec["difm_ready_added_columns"]
        assert "map Yld_Vol_Dr as the yield column" in text and "map Yld_Level" not in text
        assert rec["level"]["closure"]["verdict"]                     # the validation is still in the record


@pytest.mark.parametrize("kind,rate", [("seeding", "Rt_Apd_Ct_"), ("application", "Rt_Apd_Vol")])
def test_applied_3sigma(field, tmp_path, kind, rate):
    A = make_applied(str(tmp_path / "data"), kind)
    wd = er.new_workdir(str(tmp_path / "ws"), kind)
    cand = er.open_input([A["shp"]], wd)[0]
    assert cand["kind"] == "export" and cand["operation"] == kind and not cand["yield"]
    R = a3.run(cand["path"], str(tmp_path / "out"), {}, boundary=field["boundary"], tag="syn", log=lambda m: None)
    assert R["main"] == rate and R["attributes"] == ["Speed_mph_", rate]
    rows = {r["filter"]: r for r in R["cascade"]}
    assert rows["S0"]["removed"] == A["n_zero"]                        # no product applied
    assert rows["S1"]["removed"] > 0 and R["n_in"] == A["n"] - rows["S1"]["removed"]
    assert R["passes"] >= 1 and 0 < R["removed_pct"] < 10
    info = pyogrio.read_info(R["files"]["clean_shp"])
    assert info["features"] == R["n_kept"]
    assert list(info["fields"]) == list(pyogrio.read_info(A["shp"])["fields"])       # every attribute kept
    fl = pyogrio.read_dataframe(R["files"]["flagged_shp"], read_geometry=False)
    assert int(fl["Keep"].sum()) == R["n_kept"] and set(fl.loc[fl["Keep"] == 0, "Rem_By"]) <= set(rows) | {
        r["filter"] for r in R["cascade"]}
    assert os.path.getsize(R["files"]["report_pdf"]) > 10_000


def test_app_planter(field, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    A = make_applied(str(tmp_path / "data"), "seeding")
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.text_input(key="path_in").input(A["shp"])
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert any(m.label == "Operation" and m.value == "Seeding" for m in at.metric)
    assert _by_key(at.button_group, "attr_raw_").value == "Rt_Apd_Ct_"
    assert _by_key(at.multiselect, "a3_attrs_").value == ["Rt_Apd_Ct_", "Speed_mph_"]
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    steps = next(d.value for d in at.dataframe if "filter" in d.value.columns)
    assert list(steps["filter"][:2]) == ["S0", "S1"] and steps.iloc[0]["removed"] == A["n_zero"]
    clean = glob.glob(str(tmp_path / "ws" / "*" / "clean_shapefiles" / "*_3s_clean.shp"))
    assert len(clean) == 1 and os.path.exists(clean[0][:-4] + ".zip")
