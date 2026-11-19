# -*- coding: utf-8 -*-
"""The app (app/oced.py, Streamlit's AppTest, synthetic data only) shows the import's unit warning and the warning of a
file that does not tell its combines apart: a point export with its mass columns in kg/ha (read as lb/ac) and no
machine column. After opening it the unit warning is on the page; after cleaning it with the app's defaults both are.
Nothing of the cleaning depends on them.

    python -m pytest -q tests/test_app_unit_group_warnings.py
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import sms_import as si  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


def _by_key(items, prefix):
    return next((x for x in items if str(x.key or "").startswith(prefix)), None)


def _page_warnings(at):
    return [str(w.value) for w in at.warning]


def test_app_shows_the_unit_and_the_one_group_warnings(tmp_path, monkeypatch):
    import geopandas as gpd
    from streamlit.testing.v1 import AppTest
    F = make_field(str(tmp_path / "data"))
    g = gpd.read_file(F["shp"]).drop(columns=["Machine"])
    for c in ("Yld_Mass_W", "Yld_Mass_D"):
        g[c] = g[c] * si.KG_HA_PER_LB_AC
    shp = str(tmp_path / "in" / "kgha" / "kgha.shp")
    os.makedirs(os.path.dirname(shp))
    g.to_file(shp, engine="pyogrio")
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    at.text_input(key="path_in").input(shp)
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert any("kg/ha" in w and "the file's own bushel" in w for w in _page_warnings(at))
    b = _by_key(at.button, "clean_one")
    assert b is not None
    b.click().run()
    assert not at.exception, at.exception
    W = _page_warnings(at)
    assert any("kg/ha" in w for w in W)
    assert any("does not tell the combines apart" in w for w in W)
    R = at.session_state["cleaned"][at.session_state["active"]]["R"]
    assert any(w.startswith("import as SMS: ") and "kg/ha" in w for w in R["warnings"])
