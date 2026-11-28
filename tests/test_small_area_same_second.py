# -*- coding: utf-8 -*-
"""0.4.0: the small area's grain / ground on a point export whose times are whole seconds, synthetic data only (the
hand-worked field of test_small_area_ground): two different readings of one combine in one second are two readings
(they differ in their logged position), not one reading logged twice; a reading the import left out in the second of
a kept one is still read from the decoded file; a true duplicate (same machine, time and position) is counted once;
a flagged file without X_log / Y_log whose point moved still finds its own reading among the readings of its second.

    python -m pytest -q tests/test_small_area_same_second.py
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import small_area as sa  # noqa: E402
from tests import test_small_area_ground as T  # noqa: E402

SECOND = "2026-09-01 10:00:06"         # pass 1: the strips at y = 60 m and y = 70 m both logged in this second
PASS2 = "2026-09-01 10:01:00"          # pass 2's first reading: the reading the import left out shares its second


def _rows(true_dup=False):
    rows = T._rows()
    r = list(rows[7])                  # pass 1's strip at y = 70 m, logged in the second of the strip at y = 60 m
    r[1] = SECOND
    rows[7] = tuple(r)
    if true_dup:                       # the strip at y = 60 m logged twice: same machine, time and position
        rows.append(rows[6])
    return rows


def _frame(rows, x_log=True, shift_m=0.0):
    df = pd.DataFrame(rows, columns=["Machine", "Time", "x", "y", "Track_deg_", "Yld_Vol_Dr", "Keep", "Rem_By"])
    df["x"] += T.X0
    df["y"] += T.Y0
    df["Distance_f"] = 10.0 * T.M_FT
    df["Swth_Wdth_"] = 10.0 * T.M_FT
    df["Dist_Opt"], df["Wdth_Opt"], df["Swath_Scl"] = df["Distance_f"], df["Swth_Wdth_"], 1.0
    df["Moisture__"] = 14.0
    df["Dataset"] = "d1"
    df["Obj__Id"] = np.arange(1, len(df) + 1)
    if x_log:
        from pyproj import Transformer
        lon, lat = Transformer.from_crs(T.CRS, "EPSG:4326", always_xy=True).transform(df["x"].to_numpy(),
                                                                                     df["y"].to_numpy())
        df["X_log"], df["Y_log"] = np.round(lon, 12), np.round(lat, 12)
    geom = [Point(a + shift_m, b) for a, b in zip(df["x"], df["y"])]
    return gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=geom, crs=T.CRS)


def _decoded(path, rows, extra_time=PASS2):
    """Every reading of `rows` (logged where the rows put them) and one more the import leaves out (180 lb/ac wet, 3
    bu/ac at 60 lb/bu, below its 5 bu/ac minimum) inside the polygon at x = 20 m, y = 30 m, logged at extra_time."""
    fl = _frame(rows)
    d = pd.DataFrame({"Machine": fl["Machine"], "Time": fl["Time"], "Dataset": fl["Dataset"], "Obj__Id": fl["Obj__Id"],
                      "Track_deg_": fl["Track_deg_"], "Distance_f": fl["Distance_f"], "Swth_Wdth_": fl["Swth_Wdth_"],
                      "Moisture__": 12.0, "Yld_Mass_W": fl["Yld_Vol_Dr"] * 60.0, "Yld_Vol_Dr": fl["Yld_Vol_Dr"]})
    g = gpd.GeoDataFrame(d, geometry=list(fl.geometry), crs=T.CRS)
    extra = gpd.GeoDataFrame({"Machine": ["C1"], "Time": [extra_time], "Dataset": ["d1"], "Obj__Id": [99],
                              "Track_deg_": [0.0], "Distance_f": [10.0 * T.M_FT], "Swth_Wdth_": [10.0 * T.M_FT],
                              "Moisture__": [12.0], "Yld_Mass_W": [T.W_LO], "Yld_Vol_Dr": [T.W_LO / 60.0]},
                             geometry=[Point(T.X0 + 20.0, T.Y0 + 30.0)], crs=T.CRS)
    pd.concat([g, extra], ignore_index=True).to_crs(4326).to_file(path)
    D, note = sa.decoded_values(path, T.IMPORT_REC)
    assert note is None
    return D


def test_two_readings_of_one_second_are_two_readings_and_the_left_out_one_is_read(tmp_path):
    rows = _rows()
    D = _decoded(str(tmp_path / "x_decoded.shp"), rows)
    M = sa.measure_all(_frame(rows), T._polys(), "clip", "ground", decoded=D)
    G = M["polygons"][0]["ground"]
    # the same figures as the field whose times differ (test_small_area_ground): nothing dropped, the left-out read
    assert M["duplicates"] == 0 and M["decoded_added"] == 1
    assert G["readings"] == 14 and G["import_left_out"] == 1
    assert G["grain_bu"] == pytest.approx((800 + 50 + 100 + 3) * T.A1, rel=1e-6)
    assert G["ground_ac"] == pytest.approx(12 * T.A1, rel=1e-6)
    assert not any("logged twice" in n for n in M["ground_notes"])
    # said: two readings (the strip at y = 70 m, and the left-out reading in pass 2's first second) share a machine
    # and time with another reading at another position
    assert any(n.startswith("2 reading(s) share the machine and the time of another reading but not its logged "
                            "position") for n in M["ground_notes"]), M["ground_notes"]


def test_without_the_decoded_file_both_readings_of_the_second_count(tmp_path):
    M = sa.measure_all(_frame(_rows()), T._polys(), "clip", "ground")
    G = M["polygons"][0]["ground"]
    assert M["duplicates"] == 0
    assert G["readings"] == 13 and G["grain_bu"] == pytest.approx((800 + 50 + 100) * T.A1, rel=1e-6)
    assert G["ground_ac"] == pytest.approx(11 * T.A1, rel=1e-6)


def test_a_true_duplicate_is_still_counted_once(tmp_path):
    rows = _rows(true_dup=True)
    D = _decoded(str(tmp_path / "x_decoded.shp"), _rows())
    M = sa.measure_all(_frame(rows), T._polys(), "clip", "ground", decoded=D)
    G = M["polygons"][0]["ground"]
    assert M["duplicates"] == 1 and M["decoded_added"] == 1
    assert G["readings"] == 14 and G["grain_bu"] == pytest.approx((800 + 50 + 100 + 3) * T.A1, rel=1e-6)
    assert any(n == "1 reading(s) logged twice (same machine, time and position): counted once"
               for n in M["ground_notes"]), M["ground_notes"]


def test_a_flagged_file_without_the_logged_position_finds_its_own_reading(tmp_path):
    """No X_log / Y_log and every point 0.4 m east of where it was logged (as Optimize Swath Widths moves a narrowed
    reading): the reading the import left out in the second of the strip at y = 20 m is still the one added."""
    rows = T._rows()
    D = _decoded(str(tmp_path / "x_decoded.shp"), rows, extra_time=rows[2][1])
    A = sa.ground_readings(_frame(rows, x_log=False, shift_m=0.4), T.CRS, decoded=D)
    add = np.flatnonzero(A["src"] == "decoded")
    assert A["decoded_added"] == 1 and len(add) == 1 and A["duplicates"] == 0
    assert A["x"][add[0]] == pytest.approx(T.X0 + 20.0, abs=1e-3) and A["y"][add[0]] == pytest.approx(T.Y0 + 30.0,
                                                                                                       abs=1e-3)


def test_one_reading_per_second_is_matched_by_machine_and_time_as_before(tmp_path):
    """A machine + time held by one reading on each side is one reading, wherever the flagged file put it."""
    rows = T._rows()
    D = _decoded(str(tmp_path / "x_decoded.shp"), rows, extra_time="2026-09-01 10:02:00")
    A = sa.ground_readings(_frame(rows, x_log=False, shift_m=3.0), T.CRS, decoded=D)
    assert A["decoded_added"] == 1 and A["duplicates"] == 0 and A["notes"] == []


def test_a_time_column_of_the_date_only_tells_the_readings_apart_by_position(tmp_path):
    """A time column that holds the date only (as an SMS export's Time): every reading of the combine shares its
    machine and time; the readings are still each counted, and the reading the import left out is still read."""
    day = "2026-09-01"
    rows = [(r[0], day) + tuple(r[2:]) for r in T._rows()]
    D = _decoded(str(tmp_path / "x_decoded.shp"), rows, extra_time=day)
    M = sa.measure_all(_frame(rows), T._polys(), "clip", "ground", decoded=D)
    G = M["polygons"][0]["ground"]
    assert M["duplicates"] == 0 and M["decoded_added"] == 1
    assert G["readings"] == 14 and G["grain_bu"] == pytest.approx((800 + 50 + 100 + 3) * T.A1, rel=1e-6)
    assert G["ground_ac"] == pytest.approx(12 * T.A1, rel=1e-6)


def test_many_readings_of_one_machine_and_time_are_matched_in_one_pass(tmp_path):
    """3,000 readings of one combine under one date, a flagged file without X_log / Y_log whose points all moved 0.3 m
    east (every one matched by the nearest reading of the decoded file, the tree search), and one reading the import
    left out: it is the one added, and it takes seconds, not minutes."""
    import time
    n = 3000
    rows = [("C1", "2026-09-01", 50.0, 2.0 * i, 0.0, 100.0, 1, "") for i in range(n)]
    D = _decoded(str(tmp_path / "x_decoded.shp"), rows, extra_time="2026-09-01")
    t0 = time.perf_counter()
    A = sa.ground_readings(_frame(rows, x_log=False, shift_m=0.3), T.CRS, decoded=D, grid_heading=False)
    took = time.perf_counter() - t0
    add = np.flatnonzero(A["src"] == "decoded")
    assert A["decoded_added"] == 1 and len(add) == 1 and A["duplicates"] == 0 and A["n"] == n + 1
    assert A["x"][add[0]] == pytest.approx(T.X0 + 20.0, abs=1e-3)
    assert took < 60, took
    # with X_log / Y_log: every reading at its own spot, the same answer
    A2 = sa.ground_readings(_frame(rows), T.CRS, decoded=D, grid_heading=False)
    add2 = np.flatnonzero(A2["src"] == "decoded")
    assert A2["decoded_added"] == 1 and A2["x"][add2[0]] == pytest.approx(T.X0 + 20.0, abs=1e-3)
