# -*- coding: utf-8 -*-
"""A boundary without a .prj (synthetic data only): in projected coordinates it gives a clear message naming the file
and its coordinates instead of a geometry error, through both readers; in degrees it is read as WGS 84 as before.

    python -m pytest -q tests/test_boundary_no_prj.py
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import aoi  # noqa: E402

LAT0, LON0, M_PER_DEG = 51.80, -114.10, 111_320.0


def _field():
    import numpy as np
    from shapely.geometry import box
    m_lon = M_PER_DEG * np.cos(np.radians(LAT0))
    return box(LON0, LAT0, LON0 + 300 / m_lon, LAT0 + 200 / M_PER_DEG)


def test_a_projected_boundary_without_prj_gives_a_clear_message(tmp_path):
    import geopandas as gpd
    field = _field()
    g = gpd.GeoDataFrame({"Name": ["Synthetic"]}, geometry=[field], crs="EPSG:4326")
    utm = str(tmp_path / "utm" / "field.shp")
    os.makedirs(os.path.dirname(utm))
    g.to_crs(g.estimate_utm_crs()).to_file(utm)
    os.remove(utm[:-4] + ".prj")
    for reader in (aoi.read_plan, er._read_plan_fallback):
        with pytest.raises(ValueError, match=r"no coordinate system \(\.prj\) and its coordinates .* are not degrees"):
            reader(utm)
    # in degrees without a .prj: read as WGS 84 with the note, as before
    deg = str(tmp_path / "deg" / "field.shp")
    os.makedirs(os.path.dirname(deg))
    g.to_file(deg)
    os.remove(deg[:-4] + ".prj")
    P = er.read_plan(deg)
    assert any("taken as WGS 84" in w for w in P["warnings"])
    assert er._read_plan_fallback(deg)["area_ac"] == pytest.approx(P["area_ac"], rel=1e-9)
    assert P["area_ac"] == pytest.approx(er.read_plan(str(tmp_path / "deg" / "field.shp"))["area_ac"])
    assert 14.0 < P["area_ac"] < 15.6                    # 300 m x 200 m = 14.83 ac
