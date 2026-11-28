# -*- coding: utf-8 -*-
"""0.4.0 in the app (app/oced.py, through Streamlit's AppTest, the tabs as they run), synthetic data only: an
Operations Center point export (its own column names: VRYIELDVOL, DISTANCE, SWATHWIDTH, Heading, Moisture ...) opened
in step 1 with a plot boundary, cleaned in step 3 and measured in step 5 (Plots): no error, the table of each polygon, the map
of the small area (its texts name VRYIELDVOL), the downloads; the figures and files are the engine's, called directly
on the app's flagged file. (The same readings under OCED's names give the same figures: tests/test_small_area_own_
columns.py, in the engine with the same import; the app's default import of these two files differs, as the export
names no crop.)

    python -m pytest -q tests/test_app_small_area_own_columns.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import small_area as sa  # noqa: E402
from tests.synthetic import make_ops_export  # noqa: E402
from tests.test_app_tabs import Drive, _open, _poly  # noqa: E402

pytestmark = pytest.mark.lazy_tabs


@pytest.fixture(scope="module")
def ops(tmp_path_factory):
    return make_ops_export(str(tmp_path_factory.mktemp("ops_app")), n_rows=3000)


def _measure(d: Drive, shp: str, poly: str):
    _open(d, shp)
    tag = d.at.session_state["active"]
    kp = d.key("sa_path_", "text_input")
    d.at.text_input(key=kp).input(poly)
    d.run()
    d.open(3)
    d.click("clean_one")
    d.open(5)
    d.click(d.key("sa_go_"))
    return tag


def _sa_chart(at):
    for e in at.get("deck_gl_json_chart"):
        spec = json.loads(e.proto.json)
        if any(L.get("id") == "sa-strips" for L in spec.get("layers") or []):
            return spec
    raise AssertionError("no small area map")


def test_an_ops_center_export_is_measured_in_step_5(ops, tmp_path, monkeypatch):
    poly = _poly(ops["shp"], tmp_path / "plots.geojson")
    d = Drive(tmp_path / "ws", monkeypatch)
    tag = _measure(d, ops["shp"], poly)
    assert not d.at.error, [e.value for e in d.at.error]
    R = d.at.session_state["cleaned"][tag]["R"]
    assert R["columns"]["yield"] == "VRYIELDVOL"
    S = R["small_area"]
    assert [p["name"] for p in S["polygons"]] == ["mid", "low"]
    assert all(p["kept"]["readings"] > 0 and p["ground"]["readings"] > 0 for p in S["polygons"])
    assert S["columns"]["yield"] == "VRYIELDVOL" and "Yld_Vol_Dr" not in S["yield_rule"]
    # the table of the cleaned map average in detail: two rows per polygon; its caption names the columns read
    tables = [t.value for t in d.at.dataframe if {"polygon", "readings", "dry yield (bu/ac)", "SD"}
              <= set(t.value.columns)]
    assert tables and len(tables[0]) == 4 and list(tables[0]["readings"]) == ["cleaned", "as imported"] * 2
    assert tables[0]["dry yield (bu/ac)"].tolist() == [S["polygons"][i][s]["dry_yield_bu_ac"]
                                                       for i in (0, 1) for s in ("kept", "raw")]
    cap = [c.value for c in d.at.caption if "Cleaned: the readings the whole-field cleaning kept" in c.value]
    assert cap and "VRYIELDVOL x Swath_Scl over Dist_Opt x Wdth_Opt" in cap[0]
    assert "VRYIELDVOL over DISTANCE x SWATHWIDTH" in cap[0] and "Yld_Vol_Dr" not in cap[0]
    # the map of the small area: drawn, its hover and cards from the engine's rows
    spec = _sa_chart(d.at)
    strips = next(L for L in spec["layers"] if L.get("id") == "sa-strips")["data"]
    assert strips and all(s["v"].endswith(" bu/ac") and s["st"] and s["ck"] for s in strips)
    M = sa.detail_of(R["files"]["flagged_zip"], d.at.session_state["small_area"][tag]["path"], S["rule"],
                     margin_m=10.0, method="ground")
    G = M["ground_rows"]["mid"]
    assert any("as imported (VRYIELDVOL)" in line for line in sa.ground_text(G, 0, "mid"))
    assert M["polygons"][0]["kept"] == S["polygons"][0]["kept"]
    # the downloads of the small area
    dl = [str(b.key) for b in d.at.get("download_button")]
    assert sum(1 for k in dl if k.startswith("sa_dl_")) == 4, dl
    for k in ("csv", "zip", "parts_zip", "ground_zip"):
        assert os.path.exists(S["files"][k]), k


def test_the_app_writes_what_the_engine_writes_for_the_export(ops, tmp_path, monkeypatch):
    """The small area the app measured on the export: the engine's, called directly on the app's flagged file with
    the cleaning's record (the same figures, the same CSV and the same shapefiles, byte for byte)."""
    import hashlib
    import zipfile
    import engine.run as er
    calls = {}
    real_sa = er.small_area_after_clean

    def rec_sa(R, polygons_path, rule="clip", log=print, extra=None, **kw):
        calls["sa"] = (polygons_path, rule, kw)
        return real_sa(R, polygons_path, rule, log=log, extra=extra, **kw)
    monkeypatch.setattr(er, "small_area_after_clean", rec_sa)
    poly = _poly(ops["shp"], tmp_path / "plots.geojson")
    d = Drive(tmp_path / "ws", monkeypatch)
    tag = _measure(d, ops["shp"], poly)
    R = d.at.session_state["cleaned"][tag]["R"]
    S = R["small_area"]
    ppath, rule, kw = calls["sa"]
    assert S["decoded"]["used"]                     # the export itself: every reading, for grain / ground
    rec = sa.run(R["files"]["flagged_zip"], ppath, str(tmp_path / "direct"), "direct", rule, log=lambda m: None,
                 method=kw.get("method"), cv_pct=kw.get("cv_pct"), interior_m=kw.get("interior_m") or 0.0,
                 decoded=kw.get("decoded"), R=R)
    assert rec["polygons"] == S["polygons"] and rec["columns"] == S["columns"]
    assert rec["yield_rule"] == S["yield_rule"] and rec["ground_rule"] == S["ground_rule"]

    def digest(path):
        if path.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                return {os.path.splitext(n)[1]: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    for k in ("csv", "zip", "parts_zip", "ground_zip"):
        assert digest(rec["files"][k]) == digest(S["files"][k]), k
