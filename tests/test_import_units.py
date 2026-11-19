# -*- coding: utf-8 -*-
"""The import as SMS warns about the units of a harvest point file and changes nothing (synthetic data only): the
file's own bushel (its mass / volume) against the weight to volume the import converts with (a mass column in kg/ha
read as lb/ac, volumes made at another bushel weight), moisture given as a fraction, widths in inches; silent on a
file in the expected units; the warnings reach the cleaning's warnings on the command line.

    python -m pytest -q tests/test_import_units.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd
import pyogrio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine import sms_import as si  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

LAT0, LON0, M_PER_DEG = 51.80, -114.10, 111_320.0


def _frame(n=300, lb_bu=60.0, seed=3):
    """n readings with the columns of an SMS point export of wheat made at lb_bu (wet and dry mass and volume)."""
    rng = np.random.default_rng(seed)
    moist = 14.0 + rng.normal(0, 1.0, n)
    wet = 3900 + rng.normal(0, 250, n)
    f = np.where(moist > 13.5, (100 - moist) / 86.5, 1.0)
    return pd.DataFrame({"Product": "Wheat", "Distance_f": 6.6, "Swth_Wdth_": 30.0, "Duration_s": 1.0,
                         "Moisture__": moist, "Yld_Mass_W": wet, "Yld_Vol_We": wet / lb_bu, "Yld_Mass_D": wet * f,
                         "Yld_Vol_Dr": wet * f / lb_bu, "x": np.arange(n) * 2.0, "y": 0.0})


def _write(df, shp):
    import geopandas as gpd
    lon = LON0 + df["x"].to_numpy() / (M_PER_DEG * np.cos(np.radians(LAT0)))
    lat = LAT0 + df["y"].to_numpy() / M_PER_DEG
    os.makedirs(os.path.dirname(shp), exist_ok=True)
    g = gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    g.to_file(shp, engine="pyogrio")
    return shp


def _wheat():
    return si.resolve(si.settings({"product": "wheat"}), "wheat", None, "point_export")


def test_a_file_in_the_expected_units_gives_no_warning(tmp_path):
    shp = _write(_frame(), str(tmp_path / "a" / "a.shp"))
    rep = si.apply(shp, str(tmp_path / "a_imp.shp"), _wheat())
    assert rep["warnings"] == []
    # a monitor's bushel 0.02 % off the product's (a GreenStar 3 card's 60.0098) is the same bushel
    shp = _write(_frame(lb_bu=60.0098), str(tmp_path / "b" / "b.shp"))
    assert si.apply(shp, str(tmp_path / "b_imp.shp"), _wheat())["warnings"] == []


def test_a_mass_column_in_kg_per_ha_is_named(tmp_path):
    df = _frame()
    df["Yld_Mass_W"] *= si.KG_HA_PER_LB_AC
    df["Yld_Mass_D"] *= si.KG_HA_PER_LB_AC
    shp = _write(df, str(tmp_path / "k" / "k.shp"))
    rep = si.apply(shp, str(tmp_path / "k_imp.shp"), _wheat())
    assert len(rep["warnings"]) == 1
    w = rep["warnings"][0]
    assert "67.25 lb/bu" in w and "60.00 lb/bu" in w and "kg/ha" in w and "12.08 % too high" in w
    # the same ratio from a file made at a bushel weight 12 % heavier: named too
    assert "or the file was made at 67.25 lb/bu, a bushel 12.1 % heavier" in w
    # a warning only: the import computes what it computed before the check existed
    e = pyogrio.read_dataframe(rep["path"], read_geometry=False)
    m = df["Moisture__"].to_numpy()
    f = np.where(m > 13.5, (100 - m) / 86.5, 1.0)
    assert np.allclose(e["Yld_Vol_Dr"].to_numpy(float), df["Yld_Mass_W"].to_numpy() * f / 60.0, rtol=1e-6)


def test_volumes_made_at_another_bushel_are_named_with_the_effect(tmp_path):
    shp = _write(_frame(lb_bu=62.0), str(tmp_path / "s" / "s.shp"))
    rep = si.apply(shp, str(tmp_path / "s_imp.shp"), _wheat())
    assert len(rep["warnings"]) == 1
    w = rep["warnings"][0]
    assert "62.00 lb/bu" in w and "+3.33 %" in w and "kg/ha" not in w
    # no wet volume: the dry pair gives the file's bushel
    df = _frame(lb_bu=62.0).drop(columns=["Yld_Vol_We"])
    shp = _write(df, str(tmp_path / "d" / "d.shp"))
    rep = si.apply(shp, str(tmp_path / "d_imp.shp"), _wheat())
    assert len(rep["warnings"]) == 1 and "Yld_Mass_D / Yld_Vol_Dr" in rep["warnings"][0]


def test_no_bushel_warning_when_the_import_keeps_the_files_own_yields(tmp_path):
    """A product not known: the file's yields are kept, nothing is converted, so its bushel is not compared."""
    shp = _write(_frame(lb_bu=62.0).assign(Product="Variety 7"), str(tmp_path / "v" / "v.shp"))
    rep = si.apply(shp, str(tmp_path / "v_imp.shp"), si.resolve(si.settings(), "Variety 7", None, "point_export"))
    assert rep["own_yields"] and rep["warnings"] == []


def test_moisture_as_a_fraction_and_width_in_inches(tmp_path):
    df = _frame()
    df["Moisture__"] = df["Moisture__"] / 100.0
    shp = _write(df, str(tmp_path / "m" / "m.shp"))
    rep = si.apply(shp, str(tmp_path / "m_imp.shp"), _wheat())
    assert len(rep["warnings"]) == 1 and "looks like a fraction" in rep["warnings"][0]
    # a manual moisture replaces the column: nothing to warn about
    R = si.resolve(si.settings({"product": "wheat", "use_manual_moisture": True, "manual_moisture_pct": 14.0}),
                   "wheat", None, "point_export")
    assert si.apply(shp, str(tmp_path / "m2_imp.shp"), R)["warnings"] == []
    # a moisture sensor that logged 0 everywhere is not a fraction
    shp = _write(_frame().assign(Moisture__=0.0), str(tmp_path / "z" / "z.shp"))
    assert si.apply(shp, str(tmp_path / "z_imp.shp"), _wheat())["warnings"] == []
    df = _frame()
    df["Swth_Wdth_"] = 30.0 * 12
    shp = _write(df, str(tmp_path / "i" / "i.shp"))
    rep = si.apply(shp, str(tmp_path / "i_imp.shp"), _wheat())
    assert len(rep["warnings"]) == 1 and "median of 360.00" in rep["warnings"][0] and "30.00 ft if inches" in rep["warnings"][0]


def test_the_command_line_carries_the_import_warnings_into_the_cleaning(tmp_path):
    F = make_field(str(tmp_path / "f"))
    g = pyogrio.read_dataframe(F["shp"])
    for c in ("Yld_Mass_W", "Yld_Mass_D"):
        g[c] = g[c] * si.KG_HA_PER_LB_AC
    shp = os.path.join(str(tmp_path / "kg"), "Synthetic_kg.shp")
    os.makedirs(os.path.dirname(shp))
    g.to_file(shp, engine="pyogrio")
    work = str(tmp_path / "w")
    assert er.main([shp, "--out", work, "--tag", "kg", "--product", "wheat"]) == 0
    R = json.load(open(glob.glob(os.path.join(work, "output*", "kg*_cleaning.json"))[0], encoding="utf-8"))
    assert len(R["sms_import"]["warnings"]) == 1
    assert [w for w in R["warnings"] if w.startswith("import as SMS: ") and "kg/ha" in w]
    work = str(tmp_path / "w0")
    assert er.main([F["shp"], "--out", work, "--tag", "ok", "--product", "wheat"]) == 0
    R = json.load(open(glob.glob(os.path.join(work, "output*", "ok*_cleaning.json"))[0], encoding="utf-8"))
    assert R["sms_import"]["warnings"] == [] and not [w for w in R["warnings"] if w.startswith("import as SMS")]
