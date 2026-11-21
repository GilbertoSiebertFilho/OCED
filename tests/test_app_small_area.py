# -*- coding: utf-8 -*-
"""0.3.6 in the app (app/oced.py) through Streamlit's AppTest, synthetic data only: the boxes above a map show the
total dry bushels and follow the attribute chosen on the map (moisture, speed: its mean and area-weighted average
with its unit, no total), in step 1 and step 3; the small area cut after the cleaning in step 3 gives the same
figures as the engine module (the command line's route).

    python -m pytest -q tests/test_app_small_area.py
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import pytest
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _run(at):
    at.run()
    assert not at.exception, [str(e.value)[:500] for e in at.exception]


def _metric(at, label):
    m = [x for x in at.metric if x.label == label]
    return m[0] if m else None


def _key(at, prefix):
    return next(k for k in at.session_state.filtered_state if str(k).startswith(prefix))


def _numbers(shp, col):
    df = pyogrio.read_dataframe(shp, read_geometry=False)
    v = pd.to_numeric(df[col], errors="coerce").to_numpy(float)
    a = df["Distance_f"].to_numpy(float) * df["Swth_Wdth_"].to_numpy(float) / 43560.0
    ok = np.isfinite(v) & np.isfinite(a) & (a > 0)
    return float(np.nanmean(v)), float((v[ok] * a[ok]).sum() / a[ok].sum()), float((v[ok] * a[ok]).sum())


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


def test_boxes_total_bu_follow_the_attribute_and_small_area(field, tmp_path, monkeypatch):
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(str(field["shp"]))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    V1 = at.session_state["datasets"][at.session_state["active"]]
    shp1 = V1["shp"]
    m, a, t = _numbers(shp1, "Yld_Vol_Dr")
    assert _metric(at, "Total dry bu").value == f"{t:,.1f} bu"
    # step 1: moisture chosen on the map -> the boxes give the moisture's mean and average, no total
    k1 = _key(at, "attr_raw_")
    at.session_state[k1] = "Moisture__"
    _run(at)
    mm, ma, _ = _numbers(shp1, "Moisture__")
    assert _metric(at, "Mean moisture").value == f"{mm:,.2f} %"
    assert _metric(at, "Average moisture, area-weighted").value == f"{ma:,.2f} %"
    assert _metric(at, "Total dry bu") is None and _metric(at, "Mean dry yield") is None
    # step 1: speed, in mph
    at.session_state[k1] = "Speed_mph_"
    _run(at)
    sm1, sa1, _ = _numbers(shp1, "Speed_mph_")
    assert _metric(at, "Mean speed").value == f"{sm1:,.2f} mph"
    assert _metric(at, "Average speed, area-weighted").value == f"{sa1:,.2f} mph"
    assert _metric(at, "Total dry bu") is None
    at.session_state[k1] = "Yld_Vol_Dr"
    _run(at)
    assert _metric(at, "Mean dry yield").value == f"{m:,.2f} bu/ac"

    # step 3: the cleaning, the total of the clean file, then speed chosen on the clean map
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    C = at.session_state["cleaned"][at.session_state["active"]]
    cm, ca, ct = _numbers(C["shp"], "Yld_Vol_Dr")
    tot = _metric(at, "Total dry bu, cleaned")
    assert tot is not None and tot.value == f"{ct:,.1f} bu"
    assert _metric(at, "Average dry yield, cleaned (SMS)").value == f"{ca:,.2f} bu/ac"
    k3 = _key(at, "attr_clean_")
    for col, lab, unit in (("Speed_mph_", "speed", "mph"), ("Moisture__", "moisture", "%")):
        at.session_state[k3] = col
        _run(at)
        sm, sa_, _ = _numbers(C["shp"], col)
        assert _metric(at, f"Mean {lab}, cleaned").value == f"{sm:,.2f} {unit}"
        assert _metric(at, f"Average {lab}, cleaned, area-weighted").value == f"{sa_:,.2f} {unit}"
        assert _metric(at, "Total dry bu, cleaned") is None and _metric(at, "Mean dry yield, cleaned") is None
    at.session_state[k3] = "Yld_Vol_Dr"
    _run(at)
    assert _metric(at, "Total dry bu, cleaned") is not None

    # the small area: a polygon in the middle of the field, footprint clipped
    g = gpd.read_file(C["shp"])
    x0, x1, y0, y1 = g.geometry.x.min(), g.geometry.x.max(), g.geometry.y.min(), g.geometry.y.max()
    poly = tmp_path / "small.geojson"
    gpd.GeoDataFrame({"name": ["mid", "low"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.3, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.6),
                               box(x0, y0, x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.2)],
                     crs=4326).to_file(poly, driver="GeoJSON")
    ks = _key(at, "sa_rule_")[len("sa_rule_"):]
    at.text_input(key=f"sa_path_{ks}").input(str(poly))
    at.selectbox(key=f"sa_rule_{ks}").set_value("clip")
    at.button(key=f"sa_go_{ks}").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    S = at.session_state["cleaned"][at.session_state["active"]]["R"]["small_area"]
    assert S["rule"] == "clip" and [p["name"] for p in S["polygons"]] == ["mid", "low"]
    from engine.clean import small_area as sa
    rec = sa.run(C["R"]["files"]["flagged_zip"], str(poly), str(tmp_path / "cli"), "x", "clip", log=lambda m: None)
    assert rec["polygons"] == S["polygons"]                  # the app's figures = the engine module's
    tab = next(d.value for d in at.dataframe if "total dry bu" in d.value.columns)
    assert list(tab["polygon"]) == ["mid", "mid", "low", "low"]
    assert tab["total dry bu"].iloc[0] == pytest.approx(S["polygons"][0]["kept"]["total_dry_bu"])
