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
    # above the clean map: the key numbers and what the grower's data did to the final yield
    labels = [m.label for m in at.metric]
    assert "Mean dry yield, cleaned" in labels and any(x.startswith("Grower's yield") for x in labels)
    final = next(m for m in at.metric if m.label.startswith("Final yield"))
    if use == "adjust":
        assert final.label.startswith("Final yield (Yld_") and "by the grower's data" in final.delta
    else:
        assert final.label == "Final yield (clean file)" and final.delta == "unchanged: validate only"
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


def test_engine_grower_yield_per_acre(field, tmp_path):
    """bu/ac: the grower's yield per acre x the boundary's area (or the acres given) is the total compared."""
    wd = er.new_workdir(str(tmp_path), "syn")
    cand = er.open_input([field["shp"]], wd)[0]
    base = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
            "aoi": {"file": field["boundary"], "buffer_m": 0.01, "clip_output": True, "feature": None},
            "test_weight_lb_bu": 60.0}
    S = {**base, "scale_ticket": {"value": 52.0, "unit": "bu/ac", "basis": "dry", "moisture_pct": None, "note": None}}
    R = er.clean(cand["path"], str(tmp_path / "out1"), S, log=lambda m: None)
    L, area = R["level"], R["aoi"]["area_ac"]
    assert L["ticket_unit"] == "bu/ac" and L["ticket_value"] == 52.0
    assert L["ticket_area_ac"] == pytest.approx(area) and L["ticket_area_source"] == "the field boundary"
    assert L["ticket_bu"] == pytest.approx(52.0 * area)
    assert L["factor"] == pytest.approx(52.0 * area / L["export_total_bu"])
    assert "bu/ac x" in L["ticket_caption"]
    # the grower's own acres win over the boundary; an alias of the unit is accepted
    S2 = {**base, "scale_ticket": {"value": 52.0, "unit": "bu_ac", "basis": "dry", "moisture_pct": None, "note": None,
                                   "area_ac": 100.0}}
    R2 = er.clean(cand["path"], str(tmp_path / "out2"), S2, log=lambda m: None)
    assert R2["level"]["ticket_bu"] == pytest.approx(5200.0)
    assert R2["level"]["ticket_area_source"] == "the grower's acres"
    # acres only belong to a yield per acre
    S3 = {**base, "scale_ticket": {"value": 9000.0, "unit": "bu", "basis": "dry", "moisture_pct": None, "note": None,
                                   "area_ac": 100.0}}
    with pytest.raises(ValueError, match="area_ac"):
        er.clean(cand["path"], str(tmp_path / "out3"), S3, log=lambda m: None)
    # the caption of the app before the cleaning
    conv = er.ticket_conversion({"value": 52.0, "unit": "bu/ac", "basis": "dry"}, test_weight=60.0, area_ac=106.26,
                                area_source="the field boundary")
    assert conv["bu"] == pytest.approx(52.0 * 106.26) and "106.26 ac (the field boundary)" in conv["text"]


def test_app_grower_yield_per_acre(field, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click().run()
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    _by_key(at.button_group, "gw_u_").set_value("bu/ac").run()
    assert not at.exception, at.exception
    assert _by_key(at.number_input, "gw_w_").label == "Yield of the field"
    assert _by_key(at.number_input, "gw_a_").label == "Acres the yield is over"
    _by_key(at.number_input, "gw_w_").set_value(52.0).run()
    _by_key(at.button_group, "gw_b_").set_value("dry").run()
    assert not at.exception, at.exception
    assert any("bu/ac x" in c.value and "(the field boundary)" in c.value for c in at.caption)
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    v = next(d.value for d in at.dataframe if "grower" in d.value.columns)
    row = v[v.iloc[:, 0].str.startswith("Mean yield")].iloc[0]
    assert row["grower"] == "52.00"


def test_works_save_open_and_older_folders(field, tmp_path):
    """engine/works.py: a record keeps its paths relative to the work folder; a folder from before saved works is
    rebuilt from its decoded / clean files (boundary, grower's data, SMS settings from the cleaning record)."""
    from engine import works as ew
    ws = tmp_path / "ws"
    wd = er.new_workdir(str(ws), "syn")
    cand = er.open_input([field["shp"]], wd)[0]
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": field["boundary"], "buffer_m": 0.01, "clip_output": True, "feature": None},
         "scale_ticket": {"value": 52.0, "unit": "bu/ac", "basis": "dry", "moisture_pct": None, "note": None}}
    R = er.clean(cand["path"], os.path.join(wd, "clean", "syn"), S, log=lambda m: None)
    # an older folder: no oced_work.json, rebuilt from clean/syn/*_cleaning.json
    rec = ew.load_work(wd)
    assert rec["legacy"] and list(rec["cleaned"]) == ["syn"] and list(rec["datasets"]) == ["syn"]
    assert rec["boundary"]["syn"]["path"] == field["boundary"]
    assert rec["grower"]["syn"]["unit"] == "bu/ac" and rec["grower"]["syn"]["weight"] == 52.0
    assert rec["smsset"]["k_sd"] == 3.0
    # saved: relative paths inside the folder, absolute outside it; read back absolute
    C = {"json": R["files"]["json"], "shp": R["files"]["difm_ready_shp"], "zip": R["files"]["difm_ready_zip"],
         "kind": "sms", "at": "12:00:00", "adjusted": True, "dropped": [], "settings": {"k_sd": 3.0}}
    new = ew.make_record(wd, "  Trial 50  ", input_label="card", active="syn", datasets=rec["datasets"],
                         boundary={"syn": {"path": field["boundary"], "feature": []}}, grower=rec["grower"],
                         smsset=rec["smsset"], a3set={}, cleaned={"syn": C}, app_version="t")
    assert new["name"] == "Trial 50" and not os.path.isabs(new["cleaned"]["syn"]["json"])
    assert new["boundary"]["syn"]["path"] == field["boundary"]           # outside the folder: absolute
    ew.save_work(wd, new)
    back = ew.load_work(wd)
    assert not back["legacy"] and back["cleaned"]["syn"]["json"] == os.path.normpath(R["files"]["json"])
    works = ew.list_works(str(ws))
    assert [w["name"] for w in works] == ["Trial 50"] and works[0]["n_cleaned"] == 1
    assert "Trial 50" in ew.work_label(works[0])


def test_app_save_and_open_a_work(field, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click().run()
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    _by_key(at.number_input, "gw_w_").set_value(110_000.0).run()
    _by_key(at.number_input, "gw_tw_").set_value(60.0).run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    # saved automatically after the cleaning; then a name and Save
    saved = glob.glob(str(tmp_path / "ws" / "*" / "oced_work.json"))
    assert len(saved) == 1
    at.text_input(key="work_name").input("Synthetic work").run()
    at.button(key="work_save").click().run()
    assert not at.exception, at.exception
    # the action tree shows the file and its cleaning
    assert any(str(b.key or "").startswith("tree_f_") for b in at.button)
    assert any("cleaned" in c.value and "kept" in c.value for c in at.caption)
    # start over, then open the saved work: the cleaning comes back without running again
    at.button(key="start_over").click().run()
    assert not at.exception, at.exception
    assert not any(m.label == "Clipped (S1)" for m in at.metric)
    assert "Synthetic work" in at.selectbox(key="work_pick").format_func(at.selectbox(key="work_pick").value)
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert any(m.label == "Clipped (S1)" and m.value == f"{field['n'] - field['n_inside']:,}" for m in at.metric)
    assert any("Synthetic_boundary.geojson" in s.value for s in at.success)
    assert _by_key(at.number_input, "gw_w_").value == 110_000.0
    assert not any("settings, the boundary or the grower's data changed" in w.value for w in at.warning)
