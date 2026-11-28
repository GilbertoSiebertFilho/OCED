# -*- coding: utf-8 -*-
"""0.4.0: the small area measures a file cleaned under its own column names (an Operations Center point export:
VRYIELDVOL, DISTANCE, SWATHWIDTH, Heading, Moisture ...), synthetic data only. It reads the columns the cleaning read
(the cleaning record's 'columns'), with the cleaning's units (speed x duration when there is no distance column, the
settings' harvester width when there is no width column); the same field under OCED's names gives the same figures and
the same bytes; the texts name the column read; a file with OCED's names keeps the record of before (no 'columns' key,
the texts of 0.3.8 word for word); a column that is not there is said in plain words.

    python -m pytest -q tests/test_small_area_own_columns.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import engine.run as er  # noqa: E402
from engine.clean import small_area as sa  # noqa: E402
from tests.synthetic import OPS_COLUMNS, make_ops_export  # noqa: E402

CRS = "EPSG:32612"


def _plots(flagged_shp, path):
    G = gpd.read_file(flagged_shp)
    x0, x1, y0, y1 = G.geometry.x.min(), G.geometry.x.max(), G.geometry.y.min(), G.geometry.y.max()
    gpd.GeoDataFrame({"name": ["P1", "P2"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.31, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.62),
                               box(x0 + 0.0001, y0, x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.22)],
                     crs=4326).to_file(path, driver="GeoJSON")
    return str(path)


def _members(path):
    with zipfile.ZipFile(path) as z:
        return {os.path.splitext(n)[1]: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """The same synthetic readings as an Operations Center export and under OCED's names, both cleaned (SMS 3-sigma,
    the field clip) and measured on the same two plots."""
    d = str(tmp_path_factory.mktemp("own_cols"))
    F = make_ops_export(d, n_rows=4000)
    out = {}
    for lab, shp in (("ops", F["shp"]), ("oced", F["oced_shp"])):
        S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": lab,
             "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
        out[lab] = {"R": er.clean(shp, os.path.join(d, "out_" + lab), S, log=lambda m: None)}
    poly = _plots(out["oced"]["R"]["files"]["flagged_shp"], os.path.join(d, "plots.geojson"))
    for lab in out:
        out[lab]["rec"] = er.small_area_after_clean(out[lab]["R"], poly, "clip", log=lambda m: None)
    out["poly"], out["F"] = poly, F
    return out


def test_the_export_keeps_its_own_names_and_the_cleaning_reads_them(two):
    R = two["ops"]["R"]
    names = list(gpd.read_file(two["F"]["shp"]).columns)
    assert names[:len(OPS_COLUMNS)] == OPS_COLUMNS and "Yld_Vol_Dr" not in names
    C = R["columns"]
    assert (C["yield"], C["distance_ft"], C["width_ft"], C["heading"], C["moisture"]) == \
        ("VRYIELDVOL", "DISTANCE", "SWATHWIDTH", "Heading", "Moisture")
    fl = gpd.read_file(R["files"]["flagged_shp"])
    assert "Yld_Vol_Dr" not in fl.columns and {"VRYIELDVOL", "Swath_Scl", "Wdth_Opt", "Dist_Opt"} <= set(fl.columns)


def test_measure_works_and_equals_the_same_field_under_oced_names(two):
    a, b = two["ops"]["rec"], two["oced"]["rec"]
    assert [p["name"] for p in a["polygons"]] == ["P1", "P2"]
    assert all(p["kept"]["readings"] > 20 and p["ground"]["readings"] > 20 for p in a["polygons"])
    assert a["polygons"] == b["polygons"]                 # every figure of every set, exactly
    with open(a["files"]["csv"], "rb") as f1, open(b["files"]["csv"], "rb") as f2:
        assert f1.read() == f2.read()
    for k in ("parts_zip", "ground_zip"):                 # only SA_ columns: the same bytes
        assert _members(a["files"][k]) == _members(b["files"][k]), k
    # the clean file's own average area-weighted over the kept readings: the cleaning's, whatever the names
    assert two["ops"]["R"]["final_map"]["average_area_weighted"] == two["oced"]["R"]["final_map"][
        "average_area_weighted"]


def test_the_cleaned_map_average_is_the_clean_files_own(two):
    """Per polygon, the cleaned map average recomputed from the clean shapefile itself (its VRYIELDVOL already x
    Swath_Scl, its DISTANCE x SWATHWIDTH the optimised area), independently of the small area's code."""
    import shapely
    R, rec = two["ops"]["R"], two["ops"]["rec"]
    g = gpd.read_file(R["files"]["difm_ready_shp"])
    utm = g.estimate_utm_crs()
    gm, P = g.to_crs(utm), sa.read_polygons(two["poly"])[0].to_crs(utm)
    h = np.radians(g["Heading"].to_numpy(float))
    L, W = g["DISTANCE"].to_numpy(float) * 0.3048, g["SWATHWIDTH"].to_numpy(float) * 0.3048
    full = g["DISTANCE"].to_numpy(float) * g["SWATHWIDTH"].to_numpy(float) / 43560.0
    yv = g["VRYIELDVOL"].to_numpy(float)
    for p, poly in zip(rec["polygons"], P.geometry):
        num = den = 0.0
        for i in range(len(g)):
            x, y = gm.geometry.x.iloc[i], gm.geometry.y.iloc[i]
            f, s = np.array([np.sin(h[i]), np.cos(h[i])]), np.array([np.cos(h[i]), -np.sin(h[i])]) * W[i] / 2
            e = np.array([x, y])
            fp = shapely.Polygon([e - s, e + s, e - L[i] * f + s, e - L[i] * f - s])
            if fp.area > 0 and fp.intersects(poly):
                a = fp.intersection(poly).area / fp.area * full[i]
                num, den = num + yv[i] * a, den + a
        assert p["kept"]["dry_yield_bu_ac"] == pytest.approx(num / den, abs=2e-4)


def test_the_texts_and_the_record_name_the_columns_read(two):
    R, rec = two["ops"]["R"], two["ops"]["rec"]
    assert rec["columns"]["yield"] == "VRYIELDVOL" and rec["columns"]["distance_ft"] == "DISTANCE"
    assert rec["yield_rule"] == ("kept: VRYIELDVOL x Swath_Scl over Dist_Opt x Wdth_Opt (as the clean file); without "
                                 "the cleaning: VRYIELDVOL over DISTANCE x SWATHWIDTH of every reading of the flagged "
                                 "file")
    assert rec["ground_rule"].startswith("grain = VRYIELDVOL (as imported) x DISTANCE x SWATHWIDTH x the share")
    assert "Yld_Vol_Dr" not in str(rec)
    # the map's hover and card texts (the app's map data and the replay read detail_of)
    M = sa.detail_of(R["files"]["flagged_zip"], two["poly"], "clip", margin_m=10.0, method="ground")
    D, G = M["readings"]["P1"], M["ground_rows"]["P1"]
    kept = [j for j in range(len(D["idx"])) if D["why"][j] != "removed"]
    assert "(the clean file's: VRYIELDVOL x Swath_Scl)" in sa.reading_text(D, kept[0], "P1", "clip")[1]
    assert any("as imported (VRYIELDVOL)" in line for line in sa.ground_text(G, 0, "P1"))
    assert M["polygons"][0]["kept"] == rec["polygons"][0]["kept"]
    rp = sa.replay_part(M, M["n"])
    assert int((rp["by_row"]["poly"] > 0).sum()) > 40
    # a file under OCED's names: the record of before (no 'columns'), its texts word for word
    rec0 = two["oced"]["rec"]
    assert "columns" not in rec0
    assert rec0["yield_rule"] == ("kept: Yld_Vol_Dr x Swath_Scl over Dist_Opt x Wdth_Opt (as the clean file); without "
                                  "the cleaning: Yld_Vol_Dr over Distance_f x Swth_Wdth_ of every reading of the "
                                  "flagged file")
    assert rec0["ground_rule"].startswith("grain = Yld_Vol_Dr (as imported) x Distance_f x Swth_Wdth_ x the share of "
                                          "the logged strip inside the line, over every reading")


# ------------------------------------------------------------------------------------------------ the column map
def _frame(**cols):
    n = 3
    df = pd.DataFrame({"Keep": [1, 1, 0], "Rem_By": ["", "", "S4"], **cols})
    return gpd.GeoDataFrame(df, geometry=[Point(500000 + 10 * i, 5700000) for i in range(n)], crs=CRS)


def test_the_record_s_columns_win_over_the_names(tmp_path):
    """Settings that mapped the yield to another column (settings 'cols'): the small area reads that one, as the
    cleaning did, not the first name it would find."""
    fl = _frame(Yld_Vol_Dr=[10.0, 20.0, 30.0], MyYield=[40.0, 50.0, 60.0], Distance_f=[5.0] * 3,
                Swth_Wdth_=[30.0] * 3, Track_deg_=[90.0] * 3)
    assert sa.prepare(fl)["kept"]["yield"].tolist() == [10.0, 20.0, 30.0]
    R = {"columns": {"yield": "MyYield", "distance_ft": "Distance_f", "width_ft": "Swth_Wdth_",
                     "heading": "Track_deg_", "moisture": None}}
    P = sa.prepare(fl, sa.columns_of(fl, R))
    assert P["kept"]["yield"].tolist() == [40.0, 50.0, 60.0] and P["yield_column"] == "MyYield"
    assert P["columns"]["source"] == "the cleaning record"


def test_no_distance_column_speed_x_duration_and_no_width_the_harvester_width():
    fl = _frame(VRYIELDVOL=[10.0, 20.0, 30.0], VEHICLSPEE=[4.0, 5.0, 2.0], Duration=[1.0, 2.0, 1.0],
                Heading=[90.0, 90.0, 0.0])
    R = {"columns": {"yield": "VRYIELDVOL", "distance_ft": None, "width_ft": None, "heading": "Heading",
                     "speed_mph": "VEHICLSPEE", "duration_s": "Duration"},
         "settings": {"harvester_width_ft": 35.0}}
    P = sa.prepare(fl, sa.columns_of(fl, R))
    # the cleaning's dist_m = speed x 0.44704 x duration, in ft
    assert np.allclose(P["raw"]["len_ft"], np.array([4.0, 10.0, 2.0]) * 0.44704 / 0.3048, rtol=0, atol=1e-12)
    assert P["raw"]["wid_ft"].tolist() == [35.0] * 3 and P["heading"].tolist() == [90.0, 90.0, 0.0]
    assert sa.raw_text(P["columns"]) == ("VRYIELDVOL over (VEHICLSPEE x Duration, speed x duration) x the harvester "
                                         "width 35 ft")


def test_a_missing_column_is_said_in_plain_words():
    fl = _frame(Something=[1.0, 2.0, 3.0], Distance_f=[5.0] * 3, Swth_Wdth_=[30.0] * 3)
    with pytest.raises(ValueError) as e:
        sa.prepare(fl)
    m = str(e.value)
    assert "no dry yield (bu/ac) column" in m and "Clean this file again in step 3" in m and "Measure" in m
    fl = _frame(VRYIELDVOL=[1.0, 2.0, 3.0], SWATHWIDTH=[30.0] * 3)
    with pytest.raises(ValueError, match=r"no distance \(ft\) column"):
        sa.prepare(fl)
    fl = _frame(VRYIELDVOL=[1.0, 2.0, 3.0], DISTANCE=[5.0] * 3)
    with pytest.raises(ValueError, match=r"no swath width \(ft\) column"):
        sa.prepare(fl)


def test_a_harvester_width_in_the_settings_keeps_a_file_with_oced_names_legacy():
    """The settings' harvester width is used only for a file without a width column: a file with OCED's names (its
    Swth_Wdth_ read) keeps the record of 0.3.8 (legacy, no 'columns' key) whatever width the settings hold."""
    fl = _frame(Yld_Vol_Dr=[10.0, 20.0, 30.0], Distance_f=[5.0] * 3, Swth_Wdth_=[30.0] * 3, Track_deg_=[90.0] * 3,
                Moisture__=[14.0] * 3)
    cols = sa.columns_of(fl, {"settings": {"harvester_width_ft": 35.0}})
    assert cols["width_ft"] == "Swth_Wdth_" and cols["harvester_width_ft"] == 35.0
    assert sa.legacy_columns(cols)
    # without a width column the harvester width is the width read: the record names it
    fl2 = _frame(Yld_Vol_Dr=[10.0, 20.0, 30.0], Distance_f=[5.0] * 3, Track_deg_=[90.0] * 3)
    assert not sa.legacy_columns(sa.columns_of(fl2, {"settings": {"harvester_width_ft": 35.0}}))
