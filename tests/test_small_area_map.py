# -*- coding: utf-8 -*-
"""0.3.7, the small area read reading by reading (engine/clean/small_area.py measure()'s rows) and kept with the file,
on synthetic data only: the hover text of a reading that straddles the polygon's line gives its share and the bushels
the table sums; the polygon shapefile of the counted parts sums to the table (every rule); the replay of the cleaning
carries the polygons and each counted reading's share; in the app the small area is measured again after a reprocess
with Edit points, with the figures before and after the edits (equal to two separate runs), saved with the work, and
removed by 'Remove the small area'.

    python -m pytest -q tests/test_small_area_map.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import replay as rp  # noqa: E402
from engine.clean import small_area as sa  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("sa"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:3000].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    R = yc.run(shp, os.path.join(d, "out"), S, log=lambda m: None)
    G = gpd.read_file(R["files"]["flagged_shp"])
    x0, x1, y0, y1 = G.geometry.x.min(), G.geometry.x.max(), G.geometry.y.min(), G.geometry.y.max()
    poly = os.path.join(d, "plots.geojson")
    gpd.GeoDataFrame({"name": ["P1", "P2"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.31, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.62),
                               box(x0 + 0.0001, y0, x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.22)],
                     crs=4326).to_file(poly, driver="GeoJSON")
    return {"R": R, "poly": poly, "dir": d, "shp": shp, "F": F}


def test_the_rows_sum_to_the_table_and_the_hover_text_of_a_straddling_reading(clean):
    M = sa.detail_of(clean["R"]["files"]["flagged_zip"], clean["poly"], "clip", margin_m=10)
    for p in M["polygons"]:
        D = M["readings"][p["name"]]
        c = np.asarray(D["counted"], bool)
        assert float(np.asarray(D["bu"])[c].sum()) == pytest.approx(p["kept"]["total_dry_bu"], rel=1e-12)
        assert float(np.asarray(D["area_ac"])[c].sum()) == pytest.approx(p["kept"]["area_ac"], rel=1e-12)
        assert int(c.sum()) == p["kept"]["readings"]
        assert "outside" in D["why"] and "removed" in D["why"]            # the readings near it, and removed ones
    D = M["readings"]["P1"]
    sh = np.asarray(D["share"], float)
    j = int(np.flatnonzero(np.asarray(D["counted"]) & (sh > 0.2) & (sh < 0.8))[0])
    lines = sa.reading_text(D, j, "P1", "clip")
    a, full, y, bu = D["area_ac"][j], D["full_ac"][j], D["yield"][j], D["bu"][j]
    assert any(f"{100 * sh[j]:.0f} % inside: {a:.5f} of {full:.5f} ac counted" in x for x in lines)
    assert lines[-1] == f"{y:,.2f} bu/ac x {a:.5f} ac = {bu:.4f} bu, counted in P1"
    assert bu == pytest.approx(y * a) and a == pytest.approx(sh[j] * full)
    assert lines[0].startswith("COMBINE-A") and "record" in lines[0]
    assert sa.polygon_sum_text(M["polygons"][0]).endswith(f"= {M['polygons'][0]['kept']['dry_yield_bu_ac']:,.2f} bu/ac")
    # 'full': a reading crossing the line is not counted and says so
    Mf = sa.detail_of(clean["R"]["files"]["flagged_zip"], clean["poly"], "full", margin_m=0)
    Df = Mf["readings"]["P1"]
    jc = Df["why"].index("full_cross")
    assert "Crosses the line" in " ".join(sa.reading_text(Df, jc, "P1", "full")) and not Df["counted"][jc]


@pytest.mark.parametrize("rule", ["clip", "full", "point"])
def test_the_parts_shapefile_sums_to_the_table(clean, tmp_path, rule):
    rec = sa.run(clean["R"]["files"]["flagged_zip"], clean["poly"], str(tmp_path), "x", rule, log=lambda m: None)
    P = gpd.read_file("zip://" + rec["files"]["parts_zip"].replace("\\", "/"))
    assert {"SA_Poly", "SA_Share", "SA_Area_ac", "SA_Bu", "SA_Rule", "SA_Why", "SA_Row"} <= set(P.columns)
    for p in rec["polygons"]:
        s = P.loc[P["SA_Poly"] == p["name"], "SA_Bu"].sum()
        assert s == pytest.approx(p["kept"]["total_dry_bu"], rel=1e-9)
    pts = gpd.read_file("zip://" + rec["files"]["zip"].replace("\\", "/"))
    for p in rec["polygons"]:
        assert pts.loc[pts["SA_Poly"] == p["name"], "SA_Bu"].sum() == pytest.approx(p["kept"]["total_dry_bu"],
                                                                                     rel=1e-9)
    assert set(P["SA_Rule"]) == {rule}
    # the CSV and the record figures are the 0.3.6 ones: the same columns
    import pandas as pd
    assert list(pd.read_csv(rec["files"]["csv"]).columns) == sa.CSV_COLUMNS


def test_the_replay_of_the_cleaning_carries_the_small_area(clean):
    M = sa.detail_of(clean["R"]["files"]["flagged_zip"], clean["poly"], "clip", margin_m=0)
    X = sa.replay_part(M, M["n"])
    P = rp.replay_payload(clean["R"]["files"]["flagged_shp"], kind="clean", record=clean["R"], small_area=X)
    assert [q["name"] for q in P["small_area"]["polygons"]] == ["P1", "P2"] and P["small_area"]["bbox"]
    assert all(q["rings"] and q["label"] for q in P["small_area"]["polygons"])
    sp = np.concatenate([rp.decode_varint(C["data"]["sp"], C["n_shown"]) for C in P["combines"]])
    n1 = int((sp == 1).sum())
    assert n1 == M["polygons"][0]["kept"]["readings"] and int((sp == 2).sum()) == M["polygons"][1]["kept"]["readings"]
    assert "by_row" not in P["small_area"]
    h = rp.replay_html(P)
    assert '"small_area"' in h and "Zoom to the small area" in h


# ------------------------------------------------------------------------------------------------ the app
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


def test_app_small_area_kept_measured_again_after_edits_saved_and_removed(clean, tmp_path, monkeypatch):
    import replay_view
    from tests.test_replay_edits import _where
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(clean["shp"])
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    ks = next(k for k in at.session_state.filtered_state if str(k).startswith("sa_rule_"))[len("sa_rule_"):]
    at.text_input(key=f"sa_path_{ks}").input(clean["poly"])
    at.button(key=f"sa_go_{ks}").click()
    _run(at)
    A = at.session_state["small_area"][tag]
    kept_copy = os.path.join(wd, "small_area", tag, "plots.geojson")
    assert os.path.normcase(A["path"]) == os.path.normcase(kept_copy) and os.path.isfile(kept_copy)
    C0 = at.session_state["cleaned"][tag]
    S0 = C0["R"]["small_area"]
    assert len(at.get("deck_gl_json_chart")) >= 2                             # the clean map and the small area's
    # the figures of the cleaning shown, as a separate run would give them (its flagged file, kept aside)
    keep = str(tmp_path / "before_flagged.zip")
    shutil.copy(C0["flagged_zip"], keep)
    sep0 = sa.run(keep, kept_copy, str(tmp_path / "sep0"), "x", "clip", log=lambda m: None)
    assert sep0["polygons"] == S0["polygons"]
    # Edit points of the cleaning: 6 kept readings inside P1 removed -> reprocess -> measured again
    P = rp.replay_payload(C0["flagged_shp"], kind="clean", record=C0["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C0["flagged_shp"], read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    M = sa.detail_of(C0["flagged_zip"], kept_copy, "clip", margin_m=0)
    inside = set(np.asarray(M["readings"]["P1"]["idx"])[np.asarray(M["readings"]["P1"]["counted"])].tolist())
    rm = _where(P, F, lambda r: r.name in inside, 6)
    ck = next(k for k in at.session_state.filtered_state if str(k).startswith("replay_box_clean_"))[len("replay_box_"):]
    at.session_state[f"replay_box_{ck}"] = True
    _run(at)
    html = next(json.loads(e.proto.json)["html"] for e in at.get("bidi_component")
                if '"kind":"clean"' in json.loads(e.proto.json)["html"])
    assert '"small_area":{"polygons":[{"name":"P1"' in html                   # the polygons on the replay
    at.session_state[f"replay_box_{ck}"] = True
    at.session_state[replay_view.marks_key(ck)] = {"token": P["edit"]["token"], "remove": rm, "keep": [],
                                                  "changed": 6}
    _run(at)
    C1 = at.session_state["cleaned"][tag]
    S1 = C1["R"]["small_area"]
    assert C1["at"] != C0["at"] or C1["R"].get("manual_edits")
    assert S1["auto"] and S1["measured_after"] == C1["at"] and S1["rule"] == "clip"
    # 0.3.8: the figures before the edits keep grain / ground's too (the figure the small area leads with, and the
    # status of its readings: kept by the cleaning, removed by hand)
    G_ = ("readings", "grain_bu", "ground_ac", "dry_yield_bu_ac", "kept", "removed_by_hand")
    assert S1["before"]["polygons"] == [{"name": p["name"], "kept": p["kept"],
                                         "ground": {f: p["ground"][f] for f in G_}} for p in sep0["polygons"]]
    sep1 = sa.run(C1["flagged_zip"], kept_copy, str(tmp_path / "sep1"), "x", "clip", log=lambda m: None)
    assert sep1["polygons"] == S1["polygons"]
    assert S1["polygons"][0]["kept"]["readings"] < S0["polygons"][0]["kept"]["readings"]
    tabs = [d.value for d in at.dataframe if "bu/ac before" in d.value.columns]
    assert tabs and list(tabs[0]["polygon"]) == ["P1", "P2"]
    assert tabs[0]["readings after"].iloc[0] == S1["polygons"][0]["ground"]["readings"]
    assert tabs[0]["readings before"].iloc[0] == S0["polygons"][0]["ground"]["readings"]
    assert tabs[0]["cleaned map average bu/ac after"].iloc[0] == S1["polygons"][0]["kept"]["dry_yield_bu_ac"]
    # saved with the work, and there again when it is opened
    at.button(key="work_save").click()
    _run(at)
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert W["small_area"][tag] == {"path": f"small_area/{tag}/plots.geojson", "name": "plots.geojson", "rule": "clip"}
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    assert os.path.normcase(at2.session_state["small_area"][tag]["path"]) == os.path.normcase(kept_copy)
    assert at2.session_state["cleaned"][tag]["R"]["small_area"]["polygons"] == S1["polygons"]
    # 'Remove the small area'
    k2 = next(k for k in at2.session_state.filtered_state if str(k).startswith("sa_rule_"))[len("sa_rule_"):]
    at2.button(key=f"sa_rm_{k2}").click()
    _run(at2)
    assert tag not in at2.session_state["small_area"] and "small_area" not in at2.session_state["cleaned"][tag]["R"]
    R_disk = json.load(open(at2.session_state["cleaned"][tag]["json"], encoding="utf-8"))
    assert "small_area" not in R_disk
