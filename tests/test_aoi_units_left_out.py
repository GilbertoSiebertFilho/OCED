# -*- coding: utf-8 -*-
"""The field of interest's pre-selection of units on the command line (synthetic data only): a unit left out
although some of its readings lie inside the field of interest is named with its share (a warning, also in the
cleaning's warnings and its inputs left out); nothing is said when every unit is taken.

    python -m pytest -q tests/test_aoi_units_left_out.py
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from tests import synthetic_cn1 as SC  # noqa: E402


def _poly_wgs84(parts_xy):
    """A polygon (union of rectangles in the synthetic card's local metres, x east / y north) in WGS 84."""
    import numpy as np
    from shapely.geometry import box
    from shapely.ops import unary_union
    m_lon = SC.M_PER_DEG_LAT * np.cos(np.radians(SC.LAT0))
    rects = [box(SC.LON0 + x0 / m_lon, SC.LAT0 + y0 / SC.M_PER_DEG_LAT, SC.LON0 + x1 / m_lon,
                 SC.LAT0 + y1 / SC.M_PER_DEG_LAT) for x0, y0, x1, y1 in parts_xy]
    return unary_union(rects)


def test_a_unit_left_out_by_the_field_of_interest_is_named(tmp_path):
    """Task 1 (y 200-209 m) lies inside the field; an arm of the field reaches within 50 m of the start of task 2's
    first pass (y 400 m): about a tenth of task 2's readings are inside the field + 50 m, under the 20 % that
    pre-selects a unit, so task 2 is left out, and that is said with its share."""
    import geopandas as gpd
    card = SC.make_card(str(tmp_path / "cnh"))
    field = _poly_wgs84([(-5, 190, 305, 220), (-5, 190, 10, 360)])
    bnd = str(tmp_path / "field.geojson")
    gpd.GeoDataFrame({"Name": ["Synthetic"]}, geometry=[field], crs="EPSG:4326").to_file(bnd, driver="GeoJSON")
    work = str(tmp_path / "w")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert er.main([card["root"], "--out", work, "--aoi", bnd, "--tag", "aoi"]) == 0
    txt = out.getvalue()
    left = [ln for ln in txt.splitlines() if "WARNING: unit " in ln]
    assert len(left) == 1 and "SYNTSK02" in left[0] and "under the 20 %" in left[0] and "--units" in left[0]
    share = float(left[0].split("left out: ")[1].split(" %")[0])
    assert 0 < share < 20
    R = json.load(open(glob.glob(os.path.join(work, "output*", "aoi*_cleaning.json"))[0], encoding="utf-8"))
    assert [w for w in R["warnings"] if w.startswith("input: unit ") and "SYNTSK02" in w]
    assert any("SYNTSK02" in w for w in R["inputs_left_out"])
    # the whole of both tasks inside: nothing left out, nothing said
    both = str(tmp_path / "both.geojson")
    gpd.GeoDataFrame({"Name": ["Synthetic"]}, geometry=[_poly_wgs84([(-5, 190, 305, 420)])],
                     crs="EPSG:4326").to_file(both, driver="GeoJSON")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert er.main([card["root"], "--out", str(tmp_path / "w2"), "--aoi", both, "--tag", "both"]) == 0
    assert "WARNING: unit " not in out.getvalue()
    R = json.load(open(glob.glob(os.path.join(str(tmp_path / "w2"), "output*", "both*_cleaning.json"))[0],
                       encoding="utf-8"))
    assert not [w for w in R["warnings"] if w.startswith("input: unit ")]
