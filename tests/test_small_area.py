# -*- coding: utf-8 -*-
"""0.3.6: the small area cut AFTER the whole-field cleaning (engine/clean/small_area.py, engine.run
small_area_after_clean, --small-area / --edge-rule), on synthetic data worked out by hand: the three edge rules on a
reading inside, readings straddling the edge (one with its logged point outside, one inside), a reading the cleaning
removed and one outside; several polygons; the kept figures on the clean file's yield and area (Yld_Vol_Dr x
Swath_Scl over Dist_Opt x Wdth_Opt) and the figures without the cleaning; the command line leaves the clean and
flagged files as they are.

    python -m pytest -q tests/test_small_area.py
"""
from __future__ import annotations

import hashlib
import json
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

from engine.clean import small_area as sa  # noqa: E402

CRS = "EPSG:32612"
FT = 0.3048
AC = 43560.0


def _flagged():
    """Five readings around the polygon 0..100 m x 0..100 m (UTM metres; distances and widths in ft):
    A inside (narrowed by S2: Wdth_Opt 5 ft of 10, Swath_Scl 2), B straddling the east edge with its logged point
    outside, C straddling it with its logged point inside (heading west: its strip lies east of the point), D inside
    but removed by S4, E far outside (inside the second polygon)."""
    rows = [
        # name, x, y, heading, dist ft, width ft, Dist_Opt, Wdth_Opt, Swath_Scl, yield, moisture, keep, rem
        ("A", 50.0, 50.0, 90.0, 10.0, 10.0, 10.0, 5.0, 2.0, 100.0, 14.0, 1, ""),
        ("B", 101.0, 50.0, 90.0, 20.0, 10.0, 20.0, 10.0, 1.0, 50.0, 15.0, 1, ""),
        ("C", 99.0, 20.0, 270.0, 20.0, 10.0, 20.0, 10.0, 1.0, 80.0, 16.0, 1, ""),
        ("D", 30.0, 30.0, 0.0, 10.0, 10.0, 10.0, 10.0, 1.0, 300.0, 18.0, 0, "S4"),
        ("E", 500.0, 500.0, 0.0, 10.0, 10.0, 10.0, 10.0, 1.0, 60.0, 13.0, 1, ""),
    ]
    df = pd.DataFrame(rows, columns=["Name", "x", "y", "Track_deg_", "Distance_f", "Swth_Wdth_", "Dist_Opt",
                                     "Wdth_Opt", "Swath_Scl", "Yld_Vol_Dr", "Moisture__", "Keep", "Rem_By"])
    return _as_flagged(df)


def _as_flagged(df):
    """The flagged file as OCED writes it: X_log / Y_log = the logged point in WGS 84 (12 decimals), the point
    geometry (here UTM) = the logged point, except a reading Optimize Swath Widths narrowed: moved sideways by half
    the cut toward the strip it kept (here to the right of its heading, as S2 may)."""
    from pyproj import Transformer
    lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(df["x"].to_numpy(), df["y"].to_numpy())
    df = df.copy()
    df["X_log"], df["Y_log"] = np.round(lon, 12), np.round(lat, 12)
    cut_m = (df["Swth_Wdth_"] - df["Wdth_Opt"]).to_numpy() * FT / 2
    th = np.radians(df["Track_deg_"].to_numpy())
    gx = df["x"].to_numpy() + np.cos(th) * cut_m          # the right of the heading: (cos, -sin) of the compass angle
    gy = df["y"].to_numpy() - np.sin(th) * cut_m
    return gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=[Point(a, b) for a, b in zip(gx, gy)], crs=CRS)


def _polys():
    return gpd.GeoDataFrame({"name": ["Plot 1", "far"]}, geometry=[box(0, 0, 100, 100), box(490, 490, 510, 510)],
                            crs=CRS)


def _poly(M, name):
    return next(p for p in M["polygons"] if p["name"] == name)


def test_whole_footprint_rule_counts_only_strips_entirely_inside():
    M = sa.measure(_flagged(), _polys(), "full")
    k, r = _poly(M, "Plot 1")["kept"], _poly(M, "Plot 1")["raw"]
    a_A = 10 * 5 / AC                                   # Dist_Opt x Wdth_Opt
    assert k["readings"] == 1 and k["area_ac"] == pytest.approx(a_A)
    assert k["total_dry_bu"] == pytest.approx(200 * a_A) and k["dry_yield_bu_ac"] == pytest.approx(200)
    # without the cleaning: A (logged width 10 ft, no Swath_Scl) and D (removed by S4)
    a_A0, a_D = 10 * 10 / AC, 10 * 10 / AC
    assert r["readings"] == 2 and r["area_ac"] == pytest.approx(a_A0 + a_D)
    assert r["total_dry_bu"] == pytest.approx(100 * a_A0 + 300 * a_D)
    assert r["mean_bu_ac"] == pytest.approx(200) and r["sd_bu_ac"] == pytest.approx(100)   # population SD
    assert r["removed_by_cleaning"] == 1 and r["removed_by_step"] == {"S4": 1}
    assert r["moisture_mean_pct"] == pytest.approx(16.0)


def test_logged_point_rule_counts_c_whole_and_not_b():
    M = sa.measure(_flagged(), _polys(), "point")
    k = _poly(M, "Plot 1")["kept"]
    a_A, a_C = 10 * 5 / AC, 20 * 10 / AC
    assert k["readings"] == 2 and k["area_ac"] == pytest.approx(a_A + a_C)
    assert k["total_dry_bu"] == pytest.approx(200 * a_A + 80 * a_C)
    assert k["min_bu_ac"] == pytest.approx(80) and k["max_bu_ac"] == pytest.approx(200)
    assert k["mean_bu_ac"] == pytest.approx(140)
    assert k["dry_yield_bu_ac"] == pytest.approx((200 * a_A + 80 * a_C) / (a_A + a_C))


def test_clip_rule_counts_the_overlap_only():
    M = sa.measure(_flagged(), _polys(), "clip")
    k = _poly(M, "Plot 1")["kept"]
    L = 20 * FT                                         # B and C: 20 ft strips crossing x = 100 m
    share_B = (100 - (101 - L)) / L                     # B: from 101 - L to 101, inside up to 100
    share_C = (100 - 99) / L                            # C: from 99 to 99 + L, inside up to 100
    a_A, a_B, a_C = 10 * 5 / AC, share_B * 200 / AC, share_C * 200 / AC
    assert k["readings"] == 3
    assert k["area_ac"] == pytest.approx(a_A + a_B + a_C, rel=1e-9)
    assert k["total_dry_bu"] == pytest.approx(200 * a_A + 50 * a_B + 80 * a_C, rel=1e-9)
    assert k["dry_yield_bu_ac"] == pytest.approx((200 * a_A + 50 * a_B + 80 * a_C) / (a_A + a_B + a_C), rel=1e-9)


def test_several_polygons_named_and_counted_each():
    for rule in sa.EDGE_RULES:
        M = sa.measure(_flagged(), _polys(), rule)
        assert [p["name"] for p in M["polygons"]] == ["Plot 1", "far"]
        f = _poly(M, "far")
        assert f["kept"]["readings"] == 1 and f["kept"]["dry_yield_bu_ac"] == pytest.approx(60)
        assert f["area_ac"] == pytest.approx(400 / 4046.8564224)


def test_polygons_without_a_name_are_numbered_and_bad_rule_refused(tmp_path):
    p = tmp_path / "two.geojson"
    gpd.GeoDataFrame({"v": [1, 2]}, geometry=[box(0, 0, 100, 100), box(490, 490, 510, 510)],
                     crs=CRS).to_crs(4326).to_file(p, driver="GeoJSON")
    G, _ = sa.read_polygons(str(p))
    assert G["name"].tolist() == ["1", "2"]
    with pytest.raises(ValueError):
        sa.rule_key("inside-ish")
    with pytest.raises(ValueError):
        sa.read_polygons(str(tmp_path / "missing.zip"))


def test_run_writes_the_csv_and_the_points_of_the_kept_readings(tmp_path):
    fl = tmp_path / "x_flagged.shp"
    _flagged().to_file(fl)
    pz = tmp_path / "polys.geojson"
    _polys().to_crs(4326).to_file(pz, driver="GeoJSON")
    rec = sa.run(str(fl), str(pz), str(tmp_path / "out"), "x", "point", log=lambda m: None)
    t = pd.read_csv(rec["files"]["csv"])
    assert len(t) == 4 and set(t["set"]) == {"kept", "raw"}
    row = t[(t.polygon == "Plot 1") & (t.set == "kept")].iloc[0]
    assert row["readings"] == 2
    g = gpd.read_file("zip://" + rec["files"]["zip"].replace("\\", "/"))
    assert sorted(g["Name"]) == ["A", "C", "E"] and set(g["SA_Poly"]) == {"Plot 1", "far"}
    assert json.dumps(rec)                               # JSON-safe for the cleaning record


def _md5s(z):
    with zipfile.ZipFile(z) as f:
        return {n: hashlib.md5(f.read(n)).hexdigest() for n in f.namelist()}


def test_command_line_small_area_leaves_the_cleaning_files_as_they_are(tmp_path):
    from engine import run as er
    from tests.synthetic import make_field
    F = make_field(str(tmp_path / "f"))
    fl0 = gpd.read_file(F["shp"])
    x0, x1, y0, y1 = (float(fl0.geometry.x.min()), float(fl0.geometry.x.max()), float(fl0.geometry.y.min()),
                      float(fl0.geometry.y.max()))
    poly = tmp_path / "small.geojson"
    gpd.GeoDataFrame({"name": ["mid"]}, geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.3,
                                                       x0 + (x1 - x0) * 0.6, y0 + (y1 - y0) * 0.6)],
                     crs=4326).to_file(poly, driver="GeoJSON")
    outs = {}
    for name, extra in (("plain", []), ("sa", ["--small-area", str(poly), "--edge-rule", "clip"])):
        rc = er.main([F["shp"], "--out", str(tmp_path / name), "--tag", "t"] + extra)
        assert rc == 0
        outs[name] = os.path.join(str(tmp_path / name), "output")
    for f in ("t_sms3s_clean.zip", "t_sms3s_flagged.zip"):
        a, b = _md5s(os.path.join(outs["plain"], f)), _md5s(os.path.join(outs["sa"], f))
        assert a == b, f
    with open(os.path.join(outs["sa"], "t_sms3s_cleaning.json"), encoding="utf-8") as f:
        R = json.load(f)
    S = R["small_area"]
    assert S["rule"] == "clip" and S["polygons"][0]["name"] == "mid"
    assert os.path.exists(S["files"]["csv"]) and S["polygons"][0]["kept"]["readings"] > 0
    # the same as the engine module read on the flagged file (the app's route)
    rec = sa.run(os.path.join(outs["sa"], "t_sms3s_flagged.zip"), str(poly), str(tmp_path / "again"), "t", "clip",
                 log=lambda m: None)
    assert rec["polygons"] == S["polygons"]
    assert os.path.exists(os.path.join(outs["sa"], "t_sms3s_cleaning_report.pdf"))


def test_the_default_edge_rule_is_the_footprint_clipped_by_the_line():
    """The user's choice (2026-11-20): the polygon's line cuts the footprints by default; the SMS query rule and the
    logged point stay as choices. The app's list starts with the default, the command line takes it by default."""
    import inspect
    from engine import run as er
    assert sa.DEFAULT_RULE == "clip" and list(sa.EDGE_RULES)[0] == "clip"
    assert sa.rule_key(None) == "clip" and sa.rule_key("") == "clip"
    assert inspect.signature(sa.measure).parameters["rule"].default == "clip"
    assert inspect.signature(sa.run).parameters["rule"].default == "clip"
    assert inspect.signature(er.small_area_after_clean).parameters["rule"].default == "clip"
    src = open(er.__file__, encoding="utf-8").read()
    assert 'choices=["clip", "full", "point"], default="clip"' in src


def test_a_narrowed_reading_counts_where_the_cleaning_put_it():
    """Optimize Swath Widths narrowed F (10 ft to 4 ft) and moved it 3 ft to the right of its heading (east): its kept
    footprint lies at the moved point, entirely inside the plot (y 97.98 .. 99.20 m), whereas the same 4 ft strip at
    the logged point (y 99.5) would cross the north edge; the reading as logged (10 ft at y 99.5) crosses it too."""
    rows = [("F", 50.0, 99.5, 90.0, 10.0, 10.0, 10.0, 4.0, 2.5, 40.0, 14.0, 1, "")]
    df = pd.DataFrame(rows, columns=["Name", "x", "y", "Track_deg_", "Distance_f", "Swth_Wdth_", "Dist_Opt",
                                     "Wdth_Opt", "Swath_Scl", "Yld_Vol_Dr", "Moisture__", "Keep", "Rem_By"])
    G = _as_flagged(df)
    assert G.geometry.y.iloc[0] == pytest.approx(99.5 - 3 * FT)
    full = _poly(sa.measure(G, _polys(), "full"), "Plot 1")
    assert full["kept"]["readings"] == 1 and full["kept"]["area_ac"] == pytest.approx(10 * 4 / AC)
    assert full["kept"]["dry_yield_bu_ac"] == pytest.approx(100)          # 40 x Swath_Scl 2.5
    assert full["raw"]["readings"] == 0                                   # 10 ft at the logged point: crosses
    clip = _poly(sa.measure(G, _polys(), "clip"), "Plot 1")
    assert clip["kept"]["area_ac"] == pytest.approx(10 * 4 / AC, rel=1e-9)  # all of it inside
    half = 10 * FT / 2
    assert clip["raw"]["area_ac"] == pytest.approx(10 * 10 / AC * (100 - (99.5 - half)) / (2 * half), rel=1e-6)
