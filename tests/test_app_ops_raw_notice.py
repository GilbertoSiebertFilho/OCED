# -*- coding: utf-8 -*-
"""Step 1 of the app (app/oced.py) for an Operations Center export, on synthetic data only: a section-element
export says that Operations Center has already reprocessed its data (its raw map will not equal SMS's read of the
raw monitor files), a per-second export does not; the map's side heading says what the dry yield column is computed
from when the import computed it again from the wet mass (an Operations Center VRYIELDVOL), and a raw decode's
heading names its column alone.

    python -m pytest -q tests/test_app_ops_raw_notice.py
"""
from __future__ import annotations

import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.test_inputs import _deere_metadata, _ops_frame, _section_export, _write_points  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
NOTICE = "Operations Center has already reprocessed these data"


def _app(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception


def _texts(at):
    return [str(x.value) for x in list(at.info) + list(at.markdown) + list(at.caption)]


def _app_functions(names, **ns):
    tree = ast.parse(open(APP, encoding="utf-8").read())
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(fns, []), APP, "exec"), ns)
    return ns


def test_a_section_export_says_its_raw_map_is_not_sms(tmp_path, monkeypatch):
    shp, *_ = _section_export(str(tmp_path / "in"))
    at = _app(tmp_path, monkeypatch)
    _open(at, os.path.dirname(shp))
    infos = [str(x.value) for x in at.info]
    assert any(NOTICE in t and ".jdl / GreenStar" in t for t in infos), infos
    md = [t for t in _texts(at) if "`VRYIELDVOL`" in t]
    assert md and all("computed from WetMass / 48.00 lb/bu, dried to 14.50 %" in t for t in md), md


def test_a_per_second_export_has_no_notice_but_names_what_the_yield_is(tmp_path, monkeypatch):
    shp = _write_points(_ops_frame(120), str(tmp_path / "in" / "Ops_Harvest_2026-09-14_00.shp"))
    _deere_metadata(shp)
    at = _app(tmp_path, monkeypatch)
    _open(at, os.path.dirname(shp))
    assert not any(NOTICE in str(x.value) for x in at.info)
    md = [t for t in _texts(at) if "`VRYIELDVOL`" in t]
    assert md and all("computed from WetMass / 60.00 lb/bu, dried to 13.50 %" in t for t in md), md


def test_yield_sources_only_for_a_point_import_that_converted_the_yields():
    import engine.sms_import as si
    from engine.clean import yield_clean as yc
    ns = _app_functions({"yield_sources", "yields_converted", "is_sections_file"}, si=si, yc=yc, os=os)
    ys, isf = ns["yield_sources"], ns["is_sections_file"]
    cols = ["DISTANCE", "SWATHWIDTH", "WetMass", "Moisture", "VRYIELDVOL", "Machine"]
    IM = {"family": "point", "applied": {"weight_and_moisture": True},
          "resolved": {"test_weight_lb_bu": 60.0, "dry_moisture_pct": 13.5, "expand_dry_moisture": False}}
    assert ys({"sms_import": IM}, cols) == {"VRYIELDVOL": "computed from WetMass / 60.00 lb/bu, dried to 13.50 %"}
    assert ys({"sms_import": {**IM, "applied": {"weight_and_moisture": False}}}, cols) == {}
    assert ys({"sms_import": {**IM, "family": "raw"}}, cols) == {}
    assert ys({"sms_import": None}, cols) == {}
    no_moist = [c for c in cols if c != "Moisture"]
    assert ys({"sms_import": IM}, no_moist)["VRYIELDVOL"].endswith("the file's own dry / wet ratio")
    assert isf(os.path.join("w", "sections", "Field_Harvest_per_second.shp"))
    assert isf(os.path.join("w", "sections", "k1", "sections", "F_per_second.shp"))
    assert not isf(os.path.join("w", "imported", "F_per_second.shp"))
    assert not isf(os.path.join("w", "sections", "F.shp")) and not isf(None)
