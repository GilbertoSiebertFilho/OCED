# -*- coding: utf-8 -*-
"""Import as SMS (engine/sms_import.py) on synthetic data only: the defaults per source (John Deere files take the
file's crop definition and 5-10,000 bu/ac, Case IH / New Holland cards SMS's product table), where each value came
from, the crop names mapped to SMS's products, and apply() on the cases the defaults do not reach: the Operations
Center's yield as mass, settings that cannot be applied, a file without moisture, a .dbf with deleted records, holes
in the logging under the flow shift and the delays.

    python -m pytest -q tests/test_import_defaults.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import sms_import as si  # noqa: E402

LAT0, LON0, M_PER_DEG = 51.80, -114.10, 111_320.0
MON = {"crop": "wheat", "test_weight_lb_bu": 60.01, "dry_moisture_pct": 13.0, "source": "synthetic crop record"}


def _write(df, shp):
    import geopandas as gpd
    lon = LON0 + df["x"].to_numpy() / (M_PER_DEG * np.cos(np.radians(LAT0)))
    lat = LAT0 + df["y"].to_numpy() / M_PER_DEG
    os.makedirs(os.path.dirname(shp), exist_ok=True)
    g = gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    g.to_file(shp, engine="pyogrio")
    return shp


# ------------------------------------------------------------------------------------------------ resolve
@pytest.mark.parametrize("fmt", ["jd_gs3_rcd", "jd_jdl", "jd_ops_center"])
def test_john_deere_files_take_the_files_crop(fmt):
    R = si.resolve(si.settings(), "Wheat (Hard Red Spring)", MON, fmt)
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["min_yield"], R["max_yield"]) == (60.01, 13.0, 5.0, 1e4)
    assert R["sources"] == {"test_weight_lb_bu": "file", "dry_moisture_pct": "file",
                            "min_yield": "SMS for John Deere files", "max_yield": "SMS for John Deere files"}
    assert R["manual_moisture_pct"] == 13.0 and not R["expand_dry_moisture"] and R["family"] == "john_deere"
    assert "5.000-10,000.00 bu/ac" in si.describe(R) and "(file)" in si.describe_sources(R)
    # the file carries no crop definition: SMS's product table for the weight and moisture, the same limits
    R = si.resolve(si.settings(), "Barley", None, fmt)
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["min_yield"], R["max_yield"]) == (48.0, 14.5, 5.0, 1e4)
    assert R["sources"]["test_weight_lb_bu"] == "SMS product table"
    # the monitor dict states the limits: they are used
    R = si.resolve(si.settings(), None, dict(MON, min_yield=4.0, max_yield=None), fmt)
    assert R["product"] == "wheat" and R["min_yield"] == 4.0 and R["max_yield"] is None
    # a product chosen that is not the file's crop: that product's weight and moisture, still the John Deere limits
    R = si.resolve(si.settings({"product": "barley"}), "wheat", MON, fmt)
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["max_yield"]) == (48.0, 14.5, 1e4)
    # what the user types always wins and is said to be the user's; a value equal to the file's is the file's
    R = si.resolve(si.settings({"test_weight_lb_bu": 61.5, "dry_moisture_pct": 13.0, "max_yield": 300.0,
                                "min_yield": None}), "wheat", MON, fmt)
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["min_yield"], R["max_yield"]) == (61.5, 13.0, None,
                                                                                                300.0)
    assert R["sources"] == {"test_weight_lb_bu": "you", "dry_moisture_pct": "file", "min_yield": "you",
                            "max_yield": "you"}
    assert R["defaults"]["test_weight_lb_bu"] == 60.01 and "no minimum" in si.describe(R)


TABLE = {   # SMS product: (lb/bu, dry moisture %, min, max), as SMS stores it
    "Wheat - Spring": (60.0, 13.5, 5.0, 300.0), "Wheat - Durum": (60.0, 13.0, 5.0, 300.0),
    "Barley - Fall": (48.0, 14.5, 5.0, 200.0), "Barley - Spring": (48.0, 14.5, 5.0, 200.0),
    "Canola": (50.0, 8.5, 10.0, 400.0), "Field Peas": (60.0, 13.0, 5.0, 200.0),
    "Chick Peas": (60.0, 13.0, 5.0, 200.0), "Lentils": (60.0, 14.0, 5.0, 200.0),
    "Oats - Spring": (32.0, 14.0, 5.0, 200.0), "Flax": (60.0, 10.0, 10.0, 400.0),
    "Rye - Annual": (56.0, 14.0, 0.0, 500.0)}


@pytest.mark.parametrize("name,product", [
    ("Wheat - Spring", "Wheat - Spring"), ("Spring Wheat", "Wheat - Spring"), ("HRS wheat", "Wheat - Spring"),
    ("crop 48 (wheat?)", "Wheat - Spring"), ("DURUM", "Wheat - Durum"), ("Durum Wheat", "Wheat - Durum"),
    ("Wheat - Durum", "Wheat - Durum"), ("Barley - Fall", "Barley - Fall"), ("BARLEY", "Barley - Fall"),
    ("Spring barley", "Barley - Spring"), ("CANOLA", "Canola"), ("Canola - Synthetic hybrid", "Canola"),
    ("Field Peas", "Field Peas"), ("PEAS", "Field Peas"), ("Chick Peas", "Chick Peas"), ("Chickpea", "Chick Peas"),
    ("Lentils", "Lentils"), ("Oats", "Oats - Spring"), ("FLAX", "Flax"), ("Rye", "Rye - Annual")])
def test_case_ih_cards_take_smss_product_table(name, product):
    assert si.sms_product(name) == product
    R = si.resolve(si.settings(), name, {"crop": name, "test_weight_lb_bu": 51.0, "dry_moisture_pct": 11.0},
                   "cnh_cn1")
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["min_yield"], R["max_yield"]) == TABLE[product]
    assert set(R["sources"].values()) == {"SMS product table"} and R["sms_product"] == product
    assert R["product"] == si.PRODUCT_CROP[product] and R["family"] == "cnh"


def test_other_sources_and_names():
    # a crop SMS's table does not hold: the card's own values, else the crop table, 5-300
    R = si.resolve(si.settings(), "corn", {"crop": "corn", "test_weight_lb_bu": 55.0, "dry_moisture_pct": 15.2},
                   "cnh_cn1")
    assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["min_yield"], R["max_yield"]) == (55.0, 15.2, 5.0, 300.0)
    assert R["sources"]["test_weight_lb_bu"] == "file" and R["sources"]["max_yield"] == "OCED default"
    # a point export (no format): SMS's product table, the same as a card
    assert si.resolve(si.settings(), "DURUM")["dry_moisture_pct"] == 13.0
    assert si.resolve(si.settings(), "Canola")["min_yield"] == 10.0
    assert si.resolve(si.settings({"product": "Wheat - Durum"}), None)["product"] == "durum"
    assert si.sms_product("Ryegrass") is None and si.crop_key("Ryegrass") is None and si.crop_key("Corn") == "corn"
    assert si.format_family("jd_jdl") == "john_deere" and si.format_family("cnh_cn1") == "cnh"
    assert si.format_family(None) is None and si.format_family("isoxml") == "isoxml"
    assert si.format_family("some_other_export") is None
    with pytest.raises(ValueError):
        si.settings({"min_yield": "sometimes"})
    assert si.settings()["min_yield"] == si.AUTO and si.settings({"min_yield": None})["min_yield"] is None


# ------------------------------------------------------------------------------------------------ apply
def _ops(n=120, extra=None):
    rng = np.random.default_rng(2)
    wet = 3600 + rng.normal(0, 200, n)
    moist = 13.0 + rng.normal(0, 1.0, n)
    t = pd.Timestamp("2026-09-14 13:00:00") + pd.to_timedelta(np.arange(n), unit="s")
    df = pd.DataFrame({"DISTANCE": 6.6, "SWATHWIDTH": 40.0, "WetMass": wet, "Moisture": moist,
                       "VRYIELDVOL": wet / 60.0, "VRYIELDMAS": wet * 0.98, "Time": t.strftime("%Y-%m-%d %H:%M:%S"),
                       "Machine": 1, "x": np.arange(n) * 2.0, "y": 0.0})
    if extra:
        df = df.assign(**extra)
    return df


def test_operations_center_yield_mass_and_settings_not_applied(tmp_path):
    """VRYIELDMAS is scaled with the manual swath like the other yields (the grain mass kept) and otherwise left as
    the file gives it, with a note; a setting that cannot act is reported as not applied and changes nothing."""
    df = _ops()
    shp = _write(df, str(tmp_path / "ops" / "Ops.shp"))
    keep = {"min_yield": None, "max_yield": 1e5}
    R = si.resolve(si.settings({**keep, "use_manual_swath": True, "manual_swath_ft": 20.0}), "wheat", MON,
                   "jd_ops_center")
    rep = si.apply(shp, str(tmp_path / "a.shp"), R)
    e = pyogrio.read_dataframe(rep["path"], read_geometry=False)
    assert set(rep["changed"]) == {"SWATHWIDTH", "WetMass", "VRYIELDVOL", "VRYIELDMAS"}
    assert np.allclose(e["VRYIELDMAS"].to_numpy(float), 2 * df["VRYIELDMAS"].to_numpy(), rtol=1e-6)
    assert np.allclose(e["WetMass"].to_numpy(float), 2 * df["WetMass"].to_numpy(), rtol=1e-6)
    assert rep["applied"]["manual_swath"] and rep["applied"]["weight_and_moisture"]
    assert any(n.startswith("VRYIELDMAS: the Operations Center's yield as mass") for n in rep["notes"])
    # no per-area yield at all (a width and a moisture only): manual swath and moisture not applied, nothing patched
    d2 = df[["DISTANCE", "SWATHWIDTH", "Moisture", "Time", "Machine", "x", "y"]].copy()
    shp2 = _write(d2, str(tmp_path / "noy" / "No_yield.shp"))
    R = si.resolve(si.settings({"use_manual_swath": True, "manual_swath_ft": 20.0, "use_manual_moisture": True,
                                "manual_moisture_pct": 20.0, "flow_shift_s": 2.0}), "wheat")
    rep = si.apply(shp2, str(tmp_path / "b.shp"), R)
    assert rep["changed"] == [] and rep["path"] == shp2
    assert not any(rep["applied"].values())
    text = " | ".join(rep["notes"])
    assert "manual swath not applied" in text and "manual moisture not applied" in text
    assert "flow shift: the file has no wet mass" in text and "weight to volume and dry moisture not applied" in text


def test_no_moisture_keeps_each_readings_ratio(tmp_path):
    """A copy of a file without its moisture column imports to the same dry yields and the same readings as the
    file with it (each reading keeps its dry / wet ratio), and a manual moisture acts on it."""
    rng = np.random.default_rng(8)
    n = 300
    wet = 3000 + rng.normal(0, 900, n)
    wet[:6] = 150.0
    moist = 14.5 + rng.normal(0, 2.0, n)
    f = np.where(moist > 14.5, (100 - moist) / 85.5, 1.0)
    base = {"Distance_f": 6.6, "Swth_Wdth_": 40.0, "Duration_s": 1.0, "Yld_Mass_W": wet, "Yld_Vol_We": wet / 48.0,
            "Yld_Mass_D": wet * f, "Yld_Vol_Dr": wet * f / 48.0, "Dataset": "d1", "x": np.arange(n) * 2.0, "y": 0.0}
    with_m = _write(pd.DataFrame({**base, "Moisture__": moist}), str(tmp_path / "m" / "With.shp"))
    without = _write(pd.DataFrame(base), str(tmp_path / "n" / "Without.shp"))
    R = si.resolve(si.settings({"max_yield": 60.0}), "Barley - Fall")
    a = si.apply(with_m, str(tmp_path / "a.shp"), R)
    b = si.apply(without, str(tmp_path / "b.shp"), R)
    assert a["n_out"] == b["n_out"] and a["left_out"] == b["left_out"] and b["left_out"]
    ea = pyogrio.read_dataframe(a["path"], read_geometry=False)
    eb = pyogrio.read_dataframe(b["path"], read_geometry=False)
    assert np.allclose(ea["Yld_Vol_Dr"].to_numpy(float), eb["Yld_Vol_Dr"].to_numpy(float), rtol=1e-6)
    assert any(x.startswith("no moisture column: the dry yields keep") for x in b["notes"])
    R = si.resolve(si.settings({"use_manual_moisture": True, "manual_moisture_pct": 18.0, "min_yield": None,
                                "max_yield": 1e5}), "barley")
    c = si.apply(without, str(tmp_path / "c.shp"), R)
    ec = pyogrio.read_dataframe(c["path"], read_geometry=False)
    assert np.allclose(ec["Yld_Vol_Dr"].to_numpy(float) / ec["Yld_Vol_We"].to_numpy(float), 82 / 85.5, rtol=1e-6)


def test_dbf_with_deleted_records(tmp_path):
    """A .dbf with records flagged deleted (GDAL skips them): the import is written from the features GDAL read, so
    every recomputed cell stays on its own reading, and a note says the file was written again."""
    rng = np.random.default_rng(1)
    n = 200
    wet = 3000 + rng.normal(0, 300, n)
    wet[50:55] = 100.0                                      # below the minimum
    d = pd.DataFrame({"Distance_f": 6.6, "Swth_Wdth_": 40.0, "Duration_s": 1.0, "Moisture__": 13.0,
                      "Yld_Mass_W": wet, "Yld_Vol_We": wet / 60.0, "Yld_Mass_D": wet, "Yld_Vol_Dr": wet / 60.0,
                      "Obj__Id": np.arange(1, n + 1), "Dataset": "d1", "x": np.arange(n) * 2.0, "y": 0.0})
    shp = _write(d, str(tmp_path / "del" / "Deleted.shp"))
    dbf = shp[:-4] + ".dbf"
    b = bytearray(open(dbf, "rb").read())
    nrec, hlen, rlen = int.from_bytes(b[4:8], "little"), int.from_bytes(b[8:10], "little"), int.from_bytes(
        b[10:12], "little")
    assert nrec == n
    for i in range(20, 25):
        b[hlen + i * rlen] = 0x2A                           # deleted
    open(dbf, "wb").write(bytes(b))
    g = pyogrio.read_dataframe(shp, read_geometry=False)
    assert len(g) == n - 5
    R = si.resolve(si.settings({"test_weight_lb_bu": 57.0}), "wheat")
    rep = si.apply(shp, str(tmp_path / "imp.shp"), R)
    e = pyogrio.read_dataframe(rep["path"], read_geometry=False)
    assert len(e) == rep["n_out"] == n - 5 - 5
    assert np.allclose(e["Yld_Mass_W"].to_numpy(float) / e["Yld_Vol_We"].to_numpy(float), 57.0, rtol=1e-4)
    assert set(e["Obj__Id"]) == set(range(1, n + 1)) - set(range(21, 26)) - set(range(51, 56))
    assert any("could not be copied record by record" in x for x in rep["notes"])


def _clocked(n_per_run=40, hole_s=60.0, durations=None, time_fmt="%Y-%m-%d %H:%M:%S.%f"):
    """Two runs of logging of one combine at the same place, a hole of hole_s seconds between them (header up)."""
    rows, t = [], pd.Timestamp("2026-09-14 13:00:00")
    for r in range(2):
        for i in range(n_per_run):
            k = r * n_per_run + i
            dur = 1.0 if durations is None else durations[k % len(durations)]
            t = t + pd.Timedelta(seconds=dur)
            rows.append({"Distance_f": 6.6, "Swth_Wdth_": 40.0, "Duration_s": dur, "Moisture__": 13.0,
                         "Yld_Mass_W": 1000.0 + k, "Yld_Vol_We": (1000.0 + k) / 60.0, "Yld_Mass_D": 1000.0 + k,
                         "Yld_Vol_Dr": (1000.0 + k) / 60.0, "Track_deg_": 90.0, "Dataset": "d1",
                         "Time": t.strftime(time_fmt), "Obj__Id": k + 1, "x": i * 2.0, "y": 0.0})
        t = t + pd.Timedelta(seconds=hole_s)
    return pd.DataFrame(rows)


def test_flow_shift_and_delays_see_the_holes_in_the_logging(tmp_path):
    keep = {"min_yield": None, "max_yield": 1e5}
    shp = _write(_clocked(), str(tmp_path / "h" / "Hole.shp"))
    rep = si.apply(shp, str(tmp_path / "a.shp"), si.resolve(si.settings({**keep, "flow_shift_s": 3.0}), "wheat"))
    e = pyogrio.read_dataframe(rep["path"], read_geometry=False)
    assert rep["left_out"] == {"no yield": 6}                # 3 at the end of each run: no grain across the hole
    assert np.allclose(e["Yld_Mass_W"].to_numpy(float), 1000.0 + e["Obj__Id"].to_numpy(float) - 1 + 3)
    # the delays trim both sides of the hole: logging restarted at the same place is a new pass
    rep = si.apply(shp, str(tmp_path / "b.shp"), si.resolve(si.settings({**keep, "start_delay_s": 2.0,
                                                                         "stop_delay_s": 2.0}), "wheat"))
    assert rep["left_out"] == {"start delay": 4, "stop delay": 4}
    # durations alternating 0.995 / 1.005 s: a 3 s shift always takes the grain of the record 3 rows later
    shp = _write(_clocked(durations=[0.995, 1.005], hole_s=0.0), str(tmp_path / "j" / "Jitter.shp"))
    rep = si.apply(shp, str(tmp_path / "c.shp"), si.resolve(si.settings({**keep, "flow_shift_s": 3.0}), "wheat"))
    e = pyogrio.read_dataframe(rep["path"], read_geometry=False)
    assert np.allclose(e["Yld_Mass_W"].to_numpy(float), 1000.0 + e["Obj__Id"].to_numpy(float) - 1 + 3)
    assert rep["left_out"] == {"no yield": 3}
    # a date-only Time and no duration: no clock, the settings are not applied and the notes say so
    d = _clocked(time_fmt="%Y-%m-%d").drop(columns=["Duration_s"])
    shp = _write(d, str(tmp_path / "d" / "Date_only.shp"))
    rep = si.apply(shp, str(tmp_path / "d.shp"), si.resolve(si.settings({**keep, "flow_shift_s": 3.0,
                                                                         "start_delay_s": 1.0}), "wheat"))
    assert rep["n_out"] == len(d) and not rep["applied"]["flow_shift"] and not rep["applied"]["start_stop_delay"]
    text = " | ".join(rep["notes"])
    assert "flow shift: the file needs duration (or time)" in text and "start / stop delay" in text


def test_time_not_parsed_without_a_setting_that_needs_it(tmp_path, monkeypatch):
    from engine.clean import yield_clean as yc
    shp = _write(_clocked(), str(tmp_path / "t" / "T.shp"))

    def boom(v):
        raise AssertionError("the Time column was parsed")
    monkeypatch.setattr(yc, "_parse_time", boom)
    rep = si.apply(shp, str(tmp_path / "a.shp"), si.resolve(si.settings(), "wheat"))
    assert rep["n_in"] == 80


def test_left_out_counts_per_combine(tmp_path):
    df = _ops(extra={"Machine": np.where(np.arange(120) < 60, "A", "B")})
    wet = df["WetMass"].to_numpy().copy()
    wet[[3, 4, 70]] = 60.0                                  # 1 bu/ac
    df["WetMass"] = wet
    shp = _write(df, str(tmp_path / "g" / "Groups.shp"))
    rep = si.apply(shp, str(tmp_path / "a.shp"), si.resolve(si.settings(), "wheat", MON, "jd_ops_center"))
    assert rep["left_out"] == {"below the min. yield volume": 3}
    assert rep["left_out_by_group"] == {"below the min. yield volume": {"A": 2, "B": 1}}


def test_john_deere_crop_values_are_not_called_the_files():
    """F3 / VA-4: a Gen4 log or an Operations Center export carries SMS's weight and dry moisture for its crop
    (common.jd_monitor_product, basis 'sms_crop'), not the file's own: resolve says so (SRC_JD_CROP); a GreenStar 3
    card's own crop definition stays 'file'; a monitor dict saved before 'basis' was kept is told by its source."""
    from engine.formats import common
    mon = common.jd_monitor_product("Barley", "synthetic crop record",
                                    file_values={"test_weight_lb_bu": 47.99, "std_moisture_pct": 14.0})
    for fmt in ("jd_jdl", "jd_ops_center"):
        R = si.resolve(si.settings(), "Barley", mon, fmt)
        assert (R["test_weight_lb_bu"], R["dry_moisture_pct"], R["max_yield"]) == (48.0, 15.0, 1e4)
        assert R["sources"]["test_weight_lb_bu"] == R["sources"]["dry_moisture_pct"] == si.SRC_JD_CROP
        assert "(SMS for this John Deere crop)" in si.describe_sources(R)
    old = {k: v for k, v in mon.items() if k != "basis"}
    assert si.resolve(si.settings(), "Barley", old, "jd_jdl")["sources"]["dry_moisture_pct"] == si.SRC_JD_CROP
    R = si.resolve(si.settings(), "Wheat (Hard Red Spring)", MON, "jd_gs3_rcd")
    assert R["sources"]["dry_moisture_pct"] == si.SRC_FILE
    # what the user types equal to SMS's value stays SMS's; another value is the user's
    R = si.resolve(si.settings({"dry_moisture_pct": 14.0}), "Barley", mon, "jd_jdl")
    assert R["sources"]["dry_moisture_pct"] == si.SRC_YOU and R["sources"]["test_weight_lb_bu"] == si.SRC_JD_CROP
