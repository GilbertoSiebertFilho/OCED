# -*- coding: utf-8 -*-
"""0.3.7, section J: the small area's yield is grain / ground (engine/clean/small_area.py), on a synthetic field
worked out by hand: a no-grain run inside a pass (grain / ground keeps its ground, the cleaned map average drops it),
two passes that overlap (the union counted once), a reading the import left out below its minimum (read from the
decoded file), a reading logged twice (counted once), SMS's query on a straddling reading, the spread inside the
polygon (moving-block bootstrap, fixed seed), the calibration range and the pair table, the heading turned from true
to grid north, the interior cut, the CSV / ground shapefile / record, the hover text and a 0.3.6 record.

    python -m pytest -q tests/test_small_area_ground.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import small_area as sa  # noqa: E402

CRS = "EPSG:32612"
X0, Y0 = 500000.0, 5700000.0          # on the zone's central meridian: no meridian convergence there
M_FT = 1 / 0.3048
A1 = 100.0 / 4046.8564224            # one strip: 10 m x 10 m, in acres
W_LO = 180.0                          # the reading the import leaves out: 180 lb/ac wet = 3 bu/ac at 60 lb/bu


def _rows():
    """(machine, time, x, y, heading, yield, keep, rem): pass 1 north along x = 50 m (ten 10 m strips inside the
    polygon 0..100 m, two of them no grain, removed by S5a; one more straddling the north edge, half inside), pass 2
    along x = 55 m (two strips overlapping pass 1 by 5 m, 50 bu/ac), a reading south of the polygon (outside)."""
    out = [("C1", "2026-09-01 10:00:00", 50.0, -5.0, 0.0, 100.0, 1, "")]           # outside
    for i in range(10):
        y = 10.0 * (i + 1)
        zero = i in (3, 4)
        out.append(("C1", f"2026-09-01 10:00:{i + 1:02d}", 50.0, y, 0.0, 0.0 if zero else 100.0,
                    0 if zero else 1, "S5a" if zero else ""))
    out.append(("C1", "2026-09-01 10:00:11", 50.0, 105.0, 0.0, 100.0, 1, ""))      # straddling: half inside
    out.append(("C1", "2026-09-01 10:01:00", 55.0, 70.0, 0.0, 50.0, 1, ""))        # pass 2
    out.append(("C1", "2026-09-01 10:01:01", 55.0, 80.0, 0.0, 50.0, 1, ""))
    return out


def _flagged(dup=True):
    rows = _rows()
    if dup:                                                    # pass 2's first reading logged twice
        rows = rows + [rows[-2]]
    df = pd.DataFrame(rows, columns=["Machine", "Time", "x", "y", "Track_deg_", "Yld_Vol_Dr", "Keep", "Rem_By"])
    df["x"] += X0
    df["y"] += Y0
    df["Distance_f"] = 10.0 * M_FT
    df["Swth_Wdth_"] = 10.0 * M_FT
    df["Dist_Opt"], df["Wdth_Opt"], df["Swath_Scl"] = df["Distance_f"], df["Swth_Wdth_"], 1.0
    df["Moisture__"] = 14.0
    df["Dataset"] = "d1"
    df["Obj__Id"] = np.arange(1, len(df) + 1)
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(df["x"].to_numpy(), df["y"].to_numpy())
    df["X_log"], df["Y_log"] = np.round(lon, 12), np.round(lat, 12)
    return gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=[Point(a, b) for a, b in
                                                                    zip(df["x"] + 0, df["y"] + 0)], crs=CRS)


def _decoded(path):
    """The decoded file: every reading of the flagged file (wet mass x 60 = its dry yield) and one more, inside the
    polygon at x = 20 m, of 180 lb/ac wet (3 bu/ac), which the import's minimum of 5 bu/ac leaves out."""
    fl = _flagged(dup=False)
    d = pd.DataFrame({"Machine": fl["Machine"], "Time": fl["Time"], "Dataset": fl["Dataset"], "Obj__Id": fl["Obj__Id"],
                      "Track_deg_": fl["Track_deg_"], "Distance_f": fl["Distance_f"], "Swth_Wdth_": fl["Swth_Wdth_"],
                      "Moisture__": 12.0, "Yld_Mass_W": fl["Yld_Vol_Dr"] * 60.0, "Yld_Vol_Dr": fl["Yld_Vol_Dr"]})
    g = gpd.GeoDataFrame(d, geometry=list(fl.geometry), crs=CRS)
    extra = gpd.GeoDataFrame({"Machine": ["C1"], "Time": ["2026-09-01 10:02:00"], "Dataset": ["d1"], "Obj__Id": [99],
                              "Track_deg_": [0.0], "Distance_f": [10.0 * M_FT], "Swth_Wdth_": [10.0 * M_FT],
                              "Moisture__": [12.0], "Yld_Mass_W": [W_LO], "Yld_Vol_Dr": [W_LO / 60.0]},
                             geometry=[Point(X0 + 20.0, Y0 + 30.0)], crs=CRS)
    g = pd.concat([g, extra], ignore_index=True).to_crs(4326)
    g.to_file(path)
    return path


IMPORT_REC = {"resolved": {"on": True, "product": None, "test_weight_lb_bu": 60.0, "dry_moisture_pct": 13.5,
                           "expand_dry_moisture": False, "use_manual_swath": False, "manual_swath_ft": 15.0,
                           "use_manual_moisture": False, "manual_moisture_pct": None, "min_yield": 5.0,
                           "max_yield": None, "start_delay_s": 0.0, "stop_delay_s": 0.0, "flow_shift_s": 0.0},
              "family": "john_deere", "sources": {}, "left_out": {"below the min. yield volume": 1}}


def _polys():
    return gpd.GeoDataFrame({"name": ["P"]}, geometry=[box(X0, Y0, X0 + 100, Y0 + 100)], crs=CRS)


@pytest.fixture(scope="module")
def dec(tmp_path_factory):
    p = _decoded(str(tmp_path_factory.mktemp("dec") / "x_decoded.shp"))
    D, note = sa.decoded_values(p, IMPORT_REC)
    assert note is None and len(D) == 15
    return {"path": p, "D": D}


def test_the_import_values_of_the_decoded_file(dec):
    D = dec["D"]
    lo = D[D["step"] != ""]
    # below the minimum: the extra reading and the two no-grain ones (those are in the flagged file here)
    assert len(lo) == 3 and set(lo["step"]) == {"below the min. yield volume"}
    x = D[D["time"] == "2026-09-01 10:02:00"].iloc[0]
    assert x["step"] == "below the min. yield volume" and x["machine"] == "C1"
    assert x["dry_bu_ac"] == pytest.approx(W_LO / 60.0)
    assert (D[D["step"] == ""]["dry_bu_ac"].to_numpy() >= 50).all()


def test_grain_over_ground_by_hand(dec):
    M = sa.measure_all(_flagged(), _polys(), "clip", "ground", decoded=dec["D"])
    p = M["polygons"][0]
    G = p["ground"]
    # grain: 8 x 100 + 2 x 0 (no grain, removed) + 0.5 x 100 (straddling) + 2 x 50 (pass 2) + 3 (left out), in strips
    assert G["grain_bu"] == pytest.approx((800 + 50 + 100 + 3) * A1, rel=1e-6)
    # ground: pass 1 = 10 strips (1000 m2), pass 2 adds its 5 m outside pass 1 (100 m2), the left-out strip 100 m2
    assert G["ground_ac"] == pytest.approx(12 * A1, rel=1e-6)
    assert G["dry_yield_bu_ac"] == pytest.approx((800 + 50 + 100 + 3) / 12, rel=1e-6)
    assert G["readings"] == 14 and G["import_left_out"] == 1 and G["removed_by_cleaning"] == 2
    assert G["ground_pct"] == pytest.approx(12.0)
    assert G["below_min_ground_pct"] == pytest.approx(100 / 12)
    assert G["removed_grain_bu"] == pytest.approx(0.0) and G["left_out_grain_bu"] == pytest.approx(3 * A1)
    assert M["duplicates"] == 1 and M["decoded_added"] == 1
    assert any("logged twice" in n for n in M["ground_notes"])
    # the parts of the ground of the readings sum to the ground (the overlaps once)
    rows = M["ground_rows"]["P"]
    assert float(np.asarray(rows["ground_ac"])[rows["touch"]].sum()) == pytest.approx(G["ground_ac"], rel=1e-6)
    assert float(np.asarray(rows["grain"])[rows["touch"]].sum()) == pytest.approx(G["grain_bu"], rel=1e-12)
    # beside it: the cleaned map average drops the no-grain run's ground and counts the overlaps (and the reading
    # logged twice) twice: 8 x 100 + 0.5 x 100 + 3 x 50 over 11.5 strips
    k = p["kept"]
    assert k["readings"] == 12 and k["area_ac"] == pytest.approx(11.5 * A1)
    assert k["dry_yield_bu_ac"] == pytest.approx(1000 / 11.5)
    # SMS's query: the straddling strip is not counted (its whole strip is not inside)
    assert p["sms"]["readings"] == 11 and p["sms"]["dry_yield_bu_ac"] == pytest.approx(950 / 11)
    assert p["figure"] == G["dry_yield_bu_ac"]


def test_without_the_decoded_file_from_the_flagged_file_only(tmp_path):
    fl = tmp_path / "x_flagged.shp"
    _flagged().to_file(fl)
    poly = tmp_path / "p.geojson"
    _polys().to_crs(4326).to_file(poly, driver="GeoJSON")
    rec = sa.run(str(fl), str(poly), str(tmp_path / "o"), "x", log=lambda m: None, import_rec=IMPORT_REC)
    G = rec["polygons"][0]["ground"]
    assert not rec["decoded"]["used"] and "flagged file only" in rec["decoded"]["note"]
    assert "1 readings the import left out are not counted" in rec["decoded"]["note"]
    assert G["import_left_out"] == 0 and G["ground_ac"] == pytest.approx(11 * A1, rel=1e-6)
    assert G["grain_bu"] == pytest.approx(950 * A1, rel=1e-6)


def test_run_record_csv_ground_shapefile_and_options(dec, tmp_path):
    fl = tmp_path / "x_flagged.shp"
    _flagged().to_file(fl)
    poly = tmp_path / "p.geojson"
    two = gpd.GeoDataFrame({"name": ["P", "Q"]}, geometry=[box(X0, Y0, X0 + 100, Y0 + 100),
                                                          box(X0 + 40, Y0, X0 + 60, Y0 + 60)], crs=CRS)
    two.to_crs(4326).to_file(poly, driver="GeoJSON")
    rec = sa.run(str(fl), str(poly), str(tmp_path / "o"), "x", log=lambda m: None, method="ground", cv_pct=5.0,
                 decoded=dec["path"], import_rec=IMPORT_REC)
    assert json.dumps(rec) and rec["method"] == "ground" and rec["decoded"]["used"] and rec["decoded"]["added"] == 1
    P, Q = rec["polygons"]
    assert P["ground"]["dry_yield_bu_ac"] == pytest.approx((800 + 50 + 100 + 3) / 12, rel=1e-6)
    # the calibration range: +- 1.96 x CV x the figure; the pair table: +- 1.96 x sqrt((CV y1)^2 + (CV y2)^2)
    y1, y2 = P["figure"], Q["figure"]
    assert P["calibration"]["half"] == pytest.approx(1.96 * 0.05 * y1)
    assert P["calibration"]["lo"] == pytest.approx(y1 - 1.96 * 0.05 * y1)
    (pr,) = rec["pairs"]
    assert pr["a"] == "P" and pr["b"] == "Q" and pr["diff"] == pytest.approx(y1 - y2)
    assert pr["half"] == pytest.approx(1.96 * math.hypot(0.05 * y1, 0.05 * y2))
    assert pr["beyond"] == (abs(y1 - y2) > pr["half"])
    # the CSV: the 0.3.6 rows and columns, the new columns on the 'kept' rows
    t = pd.read_csv(rec["files"]["csv"])
    assert list(t.columns) == sa.CSV_COLUMNS and len(t) == 4 and set(t["set"]) == {"kept", "raw"}
    r = t[(t.polygon == "P") & (t.set == "kept")].iloc[0]
    assert r["method"] == "ground" and r["ground_ac"] == pytest.approx(12 * A1, rel=1e-5)
    assert r["sms_dry_yield_bu_ac"] == pytest.approx(950 / 11) and r["calibration_cv_pct"] == pytest.approx(5.0)
    # the ground shapefile: every reading's clipped strip; SA_Grain sums to the grain, SA_GrndAc to the ground
    g = gpd.read_file("zip://" + rec["files"]["ground_zip"].replace("\\", "/"))
    gp = g[g.SA_Poly == "P"]
    assert gp["SA_Grain"].sum() == pytest.approx(P["ground"]["grain_bu"], rel=1e-6)
    assert gp["SA_GrndAc"].sum() == pytest.approx(P["ground"]["ground_ac"], rel=1e-6)
    assert set(gp["SA_Status"]) == {"kept", "removed", "left_out"}
    # the method chosen leads; the three are always there
    rs = sa.run(str(fl), str(poly), str(tmp_path / "o2"), "x", log=lambda m: None, method="sms",
                decoded=dec["path"], import_rec=IMPORT_REC)
    assert rs["polygons"][0]["figure"] == pytest.approx(950 / 11) and rs["method_text"] == "as SMS's query"
    assert rs["polygons"][0]["ground"]["grain_bu"] == pytest.approx(P["ground"]["grain_bu"])
    assert rs["pairs"] == [] and rs["polygons"][0]["calibration"] is None          # no CV: no range


def test_the_hover_of_a_straddling_reading(dec):
    M = sa.measure_all(_flagged(), _polys(), "clip", "ground", decoded=dec["D"])
    D = M["ground_rows"]["P"]
    j = int(np.flatnonzero(np.asarray(D["touch"]) & (np.asarray(D["share"]) > 0.4) & (np.asarray(D["share"]) < 0.6))[0])
    L = sa.ground_text(D, j, "P", M["cleaned_rows"]["P"])
    assert L[1] == "Kept by the cleaning"
    assert f"Clipped by the line: 50 % inside: {0.5 * A1:.5f} of {A1:.5f} ac" in L
    assert f"Grain counted 100.00 bu/ac x {A1:.5f} ac x 50.0 % = {50 * A1:.4f} bu" in L
    # its half inside lies on the strip before it (the same pass, 5 m back): no new ground
    assert f"Its part of the ground {0.0:.5f} ac ({0.5 * A1:.5f} ac already covered by earlier readings)" in L
    assert "SMS's query: its strip is not whole inside: not counted" in L
    assert f"Cleaned map average: {0.5 * A1:.5f} ac, {50 * A1:.4f} bu" in L
    # a pass-2 strip overlapping pass 1: half its strip already covered by an earlier reading
    k = int(np.flatnonzero(np.asarray(D["yield"]) == 50.0)[0])
    L2 = sa.ground_text(D, k, "P", M["cleaned_rows"]["P"])
    assert any("already covered by earlier readings" in x for x in L2)
    assert "SMS's query: whole strip inside: counted" in L2
    # a no-grain reading the cleaning removed: counted in grain / ground, not in the cleaned map
    r = int(np.flatnonzero(np.asarray(D["status"]) == "removed")[0])
    L3 = sa.ground_text(D, r, "P", M["cleaned_rows"]["P"])
    assert L3[1].startswith("Removed by the cleaning (S5a)") and "counted in grain / ground" in L3[1]
    # the reading the import left out
    q = int(np.flatnonzero(np.asarray(D["status"]) == "left_out")[0])
    assert "read from the decoded file" in sa.ground_text(D, q, "P")[1]


def test_the_spread_has_a_fixed_seed_and_is_zero_for_an_even_yield():
    rng = np.random.default_rng(1)
    y = 60 + 10 * rng.standard_normal(200)
    a = np.full(200, 0.002)
    pid = np.repeat(np.arange(4), 50)
    seg = np.full(200, 3.0)
    s1 = sa._spread(y, a, pid, seg, 0.4, "Plot 1")
    s2 = sa._spread(y, a, pid, seg, 0.4, "Plot 1")
    assert s1 == s2 and s1["passes"] == 4 and s1["draws"] == sa.N_BOOT and s1["lo"] < s1["point"] < s1["hi"]
    assert s1["point"] == pytest.approx(float((y * a).sum()) / 0.4)
    flat = sa._spread(np.full(200, 55.0), a, pid, seg, 0.4, "Plot 1")
    assert flat["pct"] == pytest.approx(0.0, abs=1e-9) and flat["lo"] == pytest.approx(flat["hi"])
    # the blocks are whole stretches of one pass: about BLOCK_M of readings 3 m apart = 10 readings
    assert round(sa.BLOCK_M / 3.0) == 10


def test_the_heading_is_turned_from_true_to_grid_north():
    # 3 deg east of the central meridian (-111) at 51 N: convergence atan(tan(3 deg) sin(51 deg))
    g = sa.grid_convergence_deg([-108.0, -111.0], [51.0, 51.0], CRS)
    # east of the central meridian true north points west of grid north: its grid azimuth is minus the convergence
    assert g[0] == pytest.approx(-math.degrees(math.atan(math.tan(math.radians(3)) * math.sin(math.radians(51)))),
                                 abs=0.01)
    assert g[1] == pytest.approx(0.0, abs=1e-6)
    # a strip logged heading true north there lies along the grid azimuth of true north
    fl = _flagged(dup=False)
    off = 3 * 111320 * math.cos(math.radians(51))          # move the readings about 3 deg east
    fl = gpd.GeoDataFrame(fl.drop(columns="geometry"), geometry=fl.geometry.translate(off, 0), crs=CRS)
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(fl.geometry.x.to_numpy(),
                                                                                fl.geometry.y.to_numpy())
    fl["X_log"], fl["Y_log"] = lon, lat
    A = sa.ground_readings(fl, CRS)
    assert A["convergence_deg"] == pytest.approx(g[0], abs=0.05)
    assert np.allclose(A["heading"], A["heading_true"] + sa.grid_convergence_deg(A["lon"], A["lat"], CRS))
    A0 = sa.ground_readings(fl, CRS, grid_heading=False)
    assert np.allclose(A0["heading"], A0["heading_true"])


def test_the_interior_cut_takes_metres_off_each_end_along_the_long_axis(dec):
    polys = gpd.GeoDataFrame({"name": ["long"]}, geometry=[box(X0 + 30, Y0, X0 + 70, Y0 + 100)], crs=CRS)
    P, notes = sa.interior_polygons(polys, 10.0, CRS)
    assert not notes and P.geometry.iloc[0].area == pytest.approx(40 * 80)
    M = sa.measure_all(_flagged(), polys, "clip", "ground", decoded=dec["D"], interior_m=10.0)
    assert M["polygons"][0]["area_ac"] == pytest.approx(3200 / 4046.8564224)
    G = M["polygons"][0]["ground"]
    # inside y 10..90: pass 1's strips 2..9 (y 10..90) whole, pass 2's two strips (x 50..60 in 30..70)
    assert G["ground_ac"] == pytest.approx((8 * 100 + 2 * 50) / 4046.8564224, rel=1e-6)
    short, n2 = sa.interior_polygons(polys, 60.0, CRS)
    assert n2 and short.geometry.iloc[0].area == pytest.approx(4000)


def test_a_record_of_036_is_its_cleaned_map_average():
    old = {"file": "plots.geojson", "rule": "clip", "rule_text": sa.EDGE_RULES["clip"], "polygons": [
        {"name": "A", "area_ac": 1.0, "kept": {"readings": 3, "area_ac": 0.5, "total_dry_bu": 30.0,
                                               "dry_yield_bu_ac": 60.0},
         "raw": {"readings": 3, "area_ac": 0.5, "total_dry_bu": 30.0, "dry_yield_bu_ac": 60.0,
                 "removed_by_cleaning": 0}}]}
    assert sa.method_text(old) == "cleaned map average (0.3.6)"
    assert "cleaned map average (0.3.6)" in sa.summary_text(old)
    assert sa.method_text({"method": "ground"}) == "grain / ground"
    assert sa.method_key("SMS") == "sms" and sa.method_key(None) == "ground"
    with pytest.raises(ValueError):
        sa.method_key("median")
    assert sa.cv_value("") is None and sa.cv_value(0) is None and sa.cv_value("3.2") == pytest.approx(3.2)


def test_command_line_method_cv_interior_and_the_decoded_file_found(tmp_path):
    from engine import run as er
    from tests.synthetic import make_field
    F = make_field(str(tmp_path / "f"))
    fl0 = gpd.read_file(F["shp"])
    x0, x1, y0, y1 = (float(fl0.geometry.x.min()), float(fl0.geometry.x.max()), float(fl0.geometry.y.min()),
                      float(fl0.geometry.y.max()))
    poly = tmp_path / "small.geojson"
    gpd.GeoDataFrame({"name": ["mid", "low"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.3, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.6),
                               box(x0 + (x1 - x0) * 0.1, y0 + (y1 - y0) * 0.1, x0 + (x1 - x0) * 0.25,
                                   y0 + (y1 - y0) * 0.25)], crs=4326).to_file(poly, driver="GeoJSON")
    rc = er.main([F["shp"], "--out", str(tmp_path / "w"), "--tag", "t", "--small-area", str(poly),
                  "--small-area-method", "sms", "--small-area-cv", "4", "--small-area-interior", "5"])
    assert rc == 0
    with open(os.path.join(str(tmp_path / "w"), "output", "t_sms3s_cleaning.json"), encoding="utf-8") as f:
        S = json.load(f)["small_area"]
    assert S["method"] == "sms" and S["cv_pct"] == pytest.approx(4.0) and S["interior_m"] == pytest.approx(5.0)
    p = S["polygons"][0]
    assert p["figure"] == pytest.approx(p["sms"]["dry_yield_bu_ac"]) and p["ground"]["grain_bu"] > 0
    assert p["calibration"]["half"] == pytest.approx(1.96 * 0.04 * p["figure"])
    assert len(S["pairs"]) == 1
    # the cleaning's own decoded file is found (the command line's work folder) or the record says why not
    assert S["decoded"]["used"] or S["decoded"]["note"]
    assert os.path.exists(S["files"]["ground_zip"])
    # the same as the module run on the flagged file with the cleaning JSON beside it (the app's route)
    rec = sa.run(os.path.join(str(tmp_path / "w"), "output", "t_sms3s_flagged.zip"), str(poly), str(tmp_path / "a"),
                 "t", log=lambda m: None, method="sms", cv_pct=4, interior_m=5)
    assert rec["polygons"] == S["polygons"]
