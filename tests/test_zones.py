# -*- coding: utf-8 -*-
"""Management zones in the harvest replay (engine/zones.py, the zone part of engine/replay.py) on synthetic data only:
the reader (every format of the boundary reader, a file without a coordinate system both ways, more than 12 classes
refused, an invalid polygon repaired, other geometries dropped), the class column, the assignment of the readings
(border flag, outside the zones, overlap), the statistics and the agreement against numbers worked out by hand, the
payload with and without a zone map, the HTML controls only with one, the CSV and the command line.

    python -m pytest -q tests/test_zones.py
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import replay as rp  # noqa: E402
from engine import zones as zn  # noqa: E402
from tests.synthetic import WIDTH_FT, _lonlat, _rect  # noqa: E402
from tests.synthetic_replay import make_two_at_once  # noqa: E402

FT = 0.3048


def _gdf(polys, **cols):
    import geopandas as gpd
    return gpd.GeoDataFrame(dict(cols), geometry=list(polys), crs="EPSG:4326")


def _two_zone_map(x_split=150.0, y0=-20.0, y1=200.0, x0=-10.0, x1=320.0):
    """Zone 1 west of x_split, zone 2 east of it (metres of the synthetic plane), with the columns of a typical
    prescription export: zone, label (text), area_ac and a rate."""
    return _gdf([_rect(x0, x_split, y0, y1), _rect(x_split, x1, y0, y1)], zone=[1, 2], label=["West", "East"],
                area_ac=[10.123, 11.456], Rx_seed=[120.5, 140.25])


def _write_all(folder, g):
    """The same zone map in every format of the boundary reader: {format: path}."""
    os.makedirs(folder, exist_ok=True)
    out = {}
    shp = os.path.join(folder, "zones.shp")
    g.to_file(shp, engine="pyogrio")
    out["shp"] = shp
    z = os.path.join(folder, "zones_shp.zip")
    with zipfile.ZipFile(z, "w") as zf:
        for e in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            if os.path.exists(os.path.join(folder, "zones" + e)):
                zf.write(os.path.join(folder, "zones" + e), "zones" + e)
    out["zip"] = z
    out["geojson"] = os.path.join(folder, "zones.geojson")
    g.to_file(out["geojson"], driver="GeoJSON", engine="pyogrio")
    out["gpkg"] = os.path.join(folder, "zones.gpkg")
    g.to_file(out["gpkg"], driver="GPKG", engine="pyogrio")
    out["kml"] = os.path.join(folder, "zones.kml")
    g.to_file(out["kml"], driver="KML", engine="pyogrio")
    out["kmz"] = os.path.join(folder, "zones.kmz")
    with zipfile.ZipFile(out["kmz"], "w") as zf:
        zf.write(out["kml"], "doc.kml")
    return out


# ------------------------------------------------------------------------------------------------ the reader
def test_reader_reads_every_format_the_boundary_reader_reads(tmp_path):
    paths = _write_all(str(tmp_path / "fmt"), _two_zone_map())
    areas = {}
    for fmt, p in paths.items():
        zm = zn.prepare(p)
        assert zm.column == "zone", (fmt, zm.column, zm.columns)
        assert zm.labels == ["1", "2"] and zm.numeric, fmt
        crs, _, _ = zm.metric(*_lonlat([0.0, 300.0], [0.0, 100.0]))
        geoms, overlap, _ = zm.metric_geoms(crs)
        areas[fmt] = [g.area for g in geoms]
        assert overlap == 0
    ref = areas["shp"]
    for fmt, a in areas.items():
        assert np.allclose(a, ref, rtol=1e-6), (fmt, a, ref)
    # 160 m x 220 m and 170 m x 220 m of the synthetic plane (its own small scale error aside)
    assert np.allclose(ref, [160 * 220, 170 * 220], rtol=5e-3)


def test_column_ranking_and_class_order(tmp_path):
    g = _gdf([_rect(0, 10, 0, 10), _rect(10, 20, 0, 10), _rect(20, 30, 0, 10)],
             area_ac=[1.5, 2.5, 3.5], Rx_seed=[100.0, 120.0, 90.0], DN=[3, 1, 2], name=["c", "b", "a"])
    cols = [c["column"] for c in zn.zone_columns(g)]
    assert cols[:2] == ["DN", "Rx_seed"]          # an exact hint name first, then a name with a hint word in it
    assert cols[2:] == ["area_ac", "name"]        # then the others, in the file's order
    g2 = g.assign(MZ=[1, 1, 2], gridcode=[5, 6, 7])
    assert [c["column"] for c in zn.zone_columns(g2)][:2] == ["MZ", "gridcode"]      # exact hint names first
    assert zn.order_classes([10, 2, 1]) == [1, 2, 10]
    assert zn.order_classes(["Zone 10", "Zone 2", "zone 1"]) == ["zone 1", "Zone 2", "Zone 10"]
    assert zn.order_classes(["10", "9", "1.5"]) == ["1.5", "9", "10"]
    assert [zn.label_of(v) for v in (1.0, 2, 2.5, " High ")] == ["1", "2", "2.5", "High"]
    zm = zn.prepare(_save(tmp_path, g2, "rank.geojson"), "name")
    assert zm.labels == ["a", "b", "c"] and not zm.numeric
    assert len(set(zm.colours)) == 3


def _save(tmp_path, g, name):
    p = str(tmp_path / name)
    g.to_file(p, engine="pyogrio")
    return p


def test_more_than_twelve_classes_is_refused(tmp_path):
    polys = [_rect(i * 10, i * 10 + 10, 0, 10) for i in range(13)]
    g = _gdf(polys, ndvi=[0.1 * i for i in range(13)], zone=[1 + i % 3 for i in range(13)])
    p = _save(tmp_path, g, "many.geojson")
    assert [c["column"] for c in zn.zone_columns(g)] == ["zone"]          # 13 values: not a candidate
    with pytest.raises(zn.ZoneMapError, match=r"'ndvi' of many.geojson holds 13 different values.*at most 12"):
        zn.prepare(p, "ndvi")
    g1 = _gdf(polys, ndvi=[0.1 * i for i in range(13)])
    with pytest.raises(zn.ZoneMapError, match="no column of only.geojson can define the management zones"):
        zn.prepare(_save(tmp_path, g1, "only.geojson"))


def test_no_coordinate_system_degrees_and_metres(tmp_path):
    g = _two_zone_map()
    d = tmp_path / "nocrs"
    d.mkdir()
    p = str(d / "deg.shp")
    g.to_file(p, engine="pyogrio")
    os.remove(str(d / "deg.prj"))
    zm = zn.prepare(p)
    assert zm.labels == ["1", "2"] and any("no coordinate system" in n and "WGS 84" in n for n in zm.notes)
    gm = g.to_crs("EPSG:32612")
    pm = str(d / "metres.shp")
    gm.to_file(pm, engine="pyogrio")
    os.remove(str(d / "metres.prj"))
    with pytest.raises(zn.ZoneMapError, match=r"metres.shp has no coordinate system and its coordinates are not "
                                              r"degrees \(x [\d,.]+ to [\d,.]+, y [\d,.]+ to [\d,.]+\)"):
        zn.prepare(pm)


def test_invalid_polygon_repaired_and_other_geometries_dropped(tmp_path):
    from shapely.geometry import LineString, Point, Polygon
    lo, la = _lonlat([0, 100, 0, 100, 0], [0, 100, 100, 0, 0])            # a bow tie: invalid
    bow = Polygon(list(zip(lo, la)))
    assert not bow.is_valid
    pt = Point(*_lonlat(5.0, 5.0))
    ln = LineString(list(zip(*_lonlat([0, 50], [0, 0]))))
    g = _gdf([bow, _rect(200, 300, 0, 100), pt, ln], zone=[1, 2, 3, 4])
    p = _save(tmp_path, g, "mixed.geojson")
    zm = zn.prepare(p)
    assert zm.labels == ["1", "2"]                              # the point and the line are not zones
    assert any("2 feature(s) of mixed.geojson are not polygons" in n for n in zm.notes)
    assert any("1 invalid polygon(s) of mixed.geojson repaired" in n for n in zm.notes)
    assert zm.geoms[0].is_valid and zm.geoms[0].area > 0


# ------------------------------------------------------------------------------------------------ the assignment
def test_assignment_border_outside_and_overlap(tmp_path):
    # zone 1 x 0..100, zone 2 x 90..200 (they overlap on 90..100: that ground is zone 1's, the first in order)
    g = _gdf([_rect(0, 100, 0, 100), _rect(90, 200, 0, 100)], zone=[1, 2])
    zm = zn.prepare(_save(tmp_path, g, "ov.geojson"))
    pts = [(50, 50, 4), (95, 50, 4), (150, 50, 4), (250, 50, 4), (101, 50, 4), (103, 50, 4), (5, 50, np.nan),
           (2, 50, np.nan), (201, 50, 4)]
    x, y, w = (np.array(v, float) for v in zip(*pts))
    lon, lat = _lonlat(x, y)
    zi, bd, info = zm.assign(lon, lat, w)
    assert zi.tolist() == [0, 0, 1, 2, 1, 1, 0, 0, 2]
    # 101: 1 m from the border between the zones (half of a 4 m swath = 2 m); 103: 3 m, no; 2: 2 m from the outer
    # edge with no width (3 m); 5: 5 m, no; 201: outside, 1 m from the outer edge
    assert bd.tolist() == [False, False, False, False, True, False, False, True, True]
    assert info["overlap_ac"] == pytest.approx(10 * 100 * zn.AC_PER_M2, rel=0.01)
    assert any("management zones 1 and 2 overlap" in n for n in info["notes"])
    assert info["map_ac"][0] == pytest.approx(100 * 100 * zn.AC_PER_M2, rel=0.01)
    assert info["map_ac"][1] == pytest.approx(100 * 100 * zn.AC_PER_M2, rel=0.01)      # 100..200 once the overlap went


# ------------------------------------------------------------------------------------------------ statistics by hand
def _hand():
    #          zone border acres yield  used  combine
    rows = [(0, 0, 1.0, 50.0, 1, 0),
            (0, 0, 2.0, 80.0, 1, 1),
            (0, 1, 1.0, 20.0, 1, 0),      # on a border
            (1, 0, 1.0, 100.0, 1, 0),
            (1, 0, 1.0, np.nan, 1, 1),    # no yield: its acres count, no bushels
            (1, 0, 3.0, 60.0, 0, 0),      # removed by the cleaning: not counted
            (2, 0, 0.5, 40.0, 1, 1)]      # outside the zones
    a = np.array(rows, float)
    return (a[:, 0].astype(int), a[:, 1].astype(bool), a[:, 2], a[:, 3], a[:, 4].astype(bool), a[:, 5].astype(int))


def test_statistics_worked_out_by_hand():
    zi, bd, ac, y, use, c = _hand()
    S = zn.zone_stats(zi, bd, ac, y, use, c, ["1", "2"], [10.0, 4.0], ["A", "B"])
    z1, z2, out = S["interior"]["zones"]
    # zone 1 interior: readings 50 (1 ac) and 80 (2 ac): 210 bu on 3 ac = 70 bu/ac; mean 65, SD 15; 1 left out
    assert (z1["n"], z1["acres"], z1["bu"], z1["yield"], z1["mean"], z1["sd"]) == (2, 3.0, 210.0, 70.0, 65.0, 15.0)
    assert z1["n_border"] == 1 and z1["share"] == pytest.approx(0.3) and z1["map_ac"] == 10.0
    # zone 2: 100 bu on 1 ac and 1 ac without a yield: 100 bu on 2 ac = 50 bu/ac; the mean of the one yield
    assert (z2["n"], z2["acres"], z2["bu"], z2["yield"], z2["mean"], z2["sd"], z2["n_y"]) == (2, 2.0, 100.0, 50.0,
                                                                                                100.0, 0.0, 1)
    assert z2["share"] == pytest.approx(0.5)
    assert (out["label"], out["n"], out["acres"], out["bu"], out["yield"], out["map_ac"]) == (zn.OUTSIDE, 1, 0.5, 20.0,
                                                                                              40.0, None)
    a1 = S["all"]["zones"][0]                       # with the border reading: 230 bu on 4 ac; SD of 50, 80, 20
    assert (a1["n"], a1["acres"], a1["bu"], a1["yield"], a1["mean"]) == (3, 4.0, 230.0, 57.5, 50.0)
    assert a1["sd"] == pytest.approx(np.sqrt(600.0))
    assert S["interior"]["in_zones"]["yield"] == pytest.approx(310.0 / 5.0)
    byc = {(C["name"], r["label"]): r for C in S["interior"]["by_combine"] for r in C["zones"]}
    assert byc[("A", "1")]["yield"] == 50.0 and byc[("B", "1")]["yield"] == 80.0
    assert byc[("A", "2")]["yield"] == 100.0 and byc[("B", "2")]["yield"] == 0.0     # 1 ac with no yield
    cells = {(r[0], r[1], r[2]): r[3:] for r in S["cells"]}
    assert cells[(0, 0, 0)] == [1, 1.0, 50.0, 1, 50.0, 2500.0]
    assert cells[(0, 0, 1)] == [1, 1.0, 20.0, 1, 20.0, 400.0]
    assert cells[(1, 1, 0)] == [1, 1.0, 0.0, 0, 0.0, 0.0]
    assert (0, 1, 0) in cells and cells[(0, 1, 0)][0] == 1                  # the removed reading is not in it


def test_agreement_worked_out_by_hand():
    zi, bd, ac, y, use, c = _hand()
    S = zn.zone_stats(zi, bd, ac, y, use, c, ["1", "2"], [10.0, 4.0], ["A", "B"])
    A = zn.agreement(S, zi, bd, ac, y, use, c, ["1", "2"], ["A", "B"])
    # interior readings with a yield in a zone: 50 (1 ac) and 80 (2 ac) in zone 1, 100 (1 ac) in zone 2.
    # mean 77.5; total SS = 27.5^2 + 2 x 2.5^2 + 22.5^2 = 1275; zone means 70 and 100: between SS = 3 x 7.5^2 + 22.5^2
    # = 675; eta squared = 675 / 1275
    assert A["eta2"] == pytest.approx(675.0 / 1275.0, abs=1e-12)
    assert A["n"] == 3 and A["order_own"] == ["1", "2"] and A["order_by_yield"] == ["2", "1"]
    assert A["per_combine"] == [] and A["rank_rho"] is None


def test_agreement_inside_each_combine():
    n = zn.MIN_COMBINE_READINGS
    zi = np.r_[np.zeros(n), np.ones(n), np.zeros(n), np.ones(n)].astype(int)
    c = np.r_[np.zeros(2 * n), np.ones(2 * n)].astype(int)
    y = np.r_[np.full(n, 50.0), np.full(n, 70.0), np.full(n, 80.0), np.full(n, 75.0)]
    ac = np.full(4 * n, 0.01)
    bd = np.zeros(4 * n, bool)
    use = np.ones(4 * n, bool)
    S = zn.zone_stats(zi, bd, ac, y, use, c, ["1", "2"], [5.0, 5.0], ["A", "B"])
    A = zn.agreement(S, zi, bd, ac, y, use, c, ["1", "2"], ["A", "B"])
    assert A["order_by_yield"] == ["1", "2"]                    # 65 and 72.5 over the field
    pc = {p["name"]: p for p in A["per_combine"]}
    assert pc["A"]["order_by_yield"] == ["1", "2"] and pc["A"]["same_as_field"]
    assert pc["B"]["order_by_yield"] == ["2", "1"] and not pc["B"]["same_as_field"]
    # a combine below the minimum in a zone: not compared (then fewer than two combines: no table)
    S2 = zn.zone_stats(zi[: 2 * n + 10], bd[: 2 * n + 10], ac[: 2 * n + 10], y[: 2 * n + 10], use[: 2 * n + 10],
                       c[: 2 * n + 10], ["1", "2"], [5.0, 5.0], ["A", "B"])
    A2 = zn.agreement(S2, zi[: 2 * n + 10], bd[: 2 * n + 10], ac[: 2 * n + 10], y[: 2 * n + 10], use[: 2 * n + 10],
                      c[: 2 * n + 10], ["1", "2"], ["A", "B"])
    assert A2["per_combine"] == []


def test_csv_table():
    zi, bd, ac, y, use, c = _hand()
    S = zn.zone_stats(zi, bd, ac, y, use, c, ["1", "2"], [10.0, 4.0], ["A", "B"])
    rows = list(csv.DictReader(io.StringIO(zn.csv_text(S))))
    assert list(rows[0].keys()) == zn.CSV_FIELDS
    first = rows[0]
    assert (first["version"], first["combine"], first["zone"], first["label"], first["readings"],
            first["border_readings_left_out"], first["yield_bu_ac"]) == ("interior", "all combines", "1", "1", "2", "1",
                                                                         "70.000")
    assert any(r["label"] == zn.OUTSIDE and r["zone"] == "" for r in rows)
    assert any(r["version"] == "all" and r["combine"] == "1 A" for r in rows)
    raw = list(csv.DictReader(io.StringIO(zn.csv_text(S, raw=True))))
    assert raw[0]["version"] == "interior (raw, not cleaned)"


# ------------------------------------------------------------------------------------------------ the payload
@pytest.fixture(scope="module")
def two(tmp_path_factory):
    return make_two_at_once(str(tmp_path_factory.mktemp("zones_two")))


@pytest.fixture(scope="module")
def zone_file(tmp_path_factory, two):
    d = tmp_path_factory.mktemp("zones_map")
    g = _two_zone_map(y1=float(two["df"]["y"].max()) + 30)
    p = str(d / "zones_rx.geojson")
    g.to_file(p, engine="pyogrio")
    return p


def test_payload_without_a_zone_map_is_unchanged(two, zone_file):
    P0 = rp.replay_payload(two["shp"])
    Pz = rp.replay_payload(two["shp"], zones=zone_file)
    assert "zones" not in P0 and "zone_bytes" not in P0
    assert all("zb" not in C["data"] for C in P0["combines"])
    for C0, Cz in zip(P0["combines"], Pz["combines"]):
        assert {k: v for k, v in Cz["data"].items() if k != "zb"} == C0["data"]
        assert {k: v for k, v in Cz.items() if k != "data"} == {k: v for k, v in C0.items() if k != "data"}
    skip = {"zones", "zone_bytes", "bytes", "combines"}
    assert {k: v for k, v in Pz.items() if k not in skip} == {k: v for k, v in P0.items() if k not in skip}
    assert Pz["zone_bytes"] > 0 and Pz["bytes"] > P0["bytes"]


def test_payload_zones_of_every_reading(two, zone_file):
    P = rp._clean_floats(rp.replay_payload(two["shp"], zones=zone_file, rows=True))
    Z = P["zones"]
    assert [c["label"] for c in Z["classes"]] == ["1", "2"] and Z["column"] == "zone" and Z["raw"]
    df = two["df"]
    half = WIDTH_FT * FT / 2
    xs, zs, bs = [], [], []
    for C in P["combines"]:
        zb = rp.decode_varint(C["data"]["zb"], C["n_shown"])
        rows = np.asarray(C["rows"])
        xs.append(df["x"].to_numpy()[rows])
        zs.append(zb >> 1)
        bs.append((zb & 1).astype(bool))
    x, z, b = np.concatenate(xs), np.concatenate(zs), np.concatenate(bs)
    sure = np.abs(x - 150.0) > 0.05                      # the synthetic plane and UTM differ by millimetres
    assert sure.sum() > 0.99 * len(x)
    assert (z[sure] == np.where(x[sure] < 150.0, 0, 1)).all()
    sure_b = np.abs(np.abs(x - 150.0) - half) > 0.05
    assert (b[sure_b] == (np.abs(x[sure_b] - 150.0) < half)).all()
    assert 0 < b.sum() < len(b)
    # the statistics: every reading (an import), acres = distance x width, bushels = yield x acres
    area = df["Distance_f"].to_numpy() * FT * WIDTH_FT * FT / 4046.8564224
    yl = df["Yld_Vol_Dr"].to_numpy()
    xo = df["x"].to_numpy()
    for ver in ("interior", "all"):
        S = Z["stats"][ver]["zones"]
        assert sum(r["n"] for r in S) + (sum(r["n_border"] for r in S) if ver == "interior" else 0) == len(df)
    allz = Z["stats"]["all"]["zones"]
    west = xo < 150.0
    assert allz[0]["n"] == int(west.sum()) and allz[1]["n"] == int((~west).sum()) and allz[2]["n"] == 0
    assert allz[0]["acres"] == pytest.approx(area[west].sum(), rel=1e-12)
    assert allz[1]["bu"] == pytest.approx((yl * area)[~west].sum(), rel=1e-12)
    assert allz[0]["sd"] == pytest.approx(float(yl[west].std()), rel=1e-12)
    # the cells (combine, zone, border) add up to the zones
    cells = np.array(Z["cells"], float)
    for k in (0, 1):
        assert cells[cells[:, 1] == k, 3].sum() == allz[k]["n"]
        assert cells[cells[:, 1] == k, 4].sum() == pytest.approx(allz[k]["acres"], rel=1e-12)
    assert Z["agreement"]["eta2"] is not None and 0 <= Z["agreement"]["eta2"] <= 1
    rings = Z["classes"][0]["rings"]
    assert len(rings["n"]) == 1 and rings["n"][0] >= 4 and Z["classes"][0]["chips"]


def test_cleaning_replay_counts_the_kept_readings_and_says_raw_otherwise(tmp_path, two, zone_file):
    import geopandas as gpd
    g = gpd.read_file(two["shp"])
    keep = np.ones(len(g), int)
    keep[::4] = 0
    g["Keep"] = keep
    g["Rem_By"] = np.where(keep == 1, "", "S4")
    p = str(tmp_path / "flagged.shp")
    g.to_file(p, engine="pyogrio")
    P = rp._clean_floats(rp.replay_payload(p, kind="clean", zones=zone_file))
    Z = P["zones"]
    assert not Z["raw"] and Z["kind"] == "clean"
    S = Z["stats"]["all"]["zones"]
    assert sum(r["n"] for r in S) == int(keep.sum())
    P0 = rp._clean_floats(rp.replay_payload(two["shp"], zones=zone_file))
    assert P0["zones"]["raw"]


def test_html_zone_controls_only_with_a_zone_map(two, zone_file, tmp_path):
    P0 = rp._clean_floats(rp.replay_payload(two["shp"]))
    Pz = rp._clean_floats(rp.replay_payload(two["shp"], zones=zone_file))
    h0, hz = rp.replay_html(P0), rp.replay_html(Pz)
    for el in ('id="zpanel"', 'id="views"', 'id="t-zb"', 'id="rp-zcard"', 'id="b-zcard"'):
        assert el not in h0 and el in hz, el
    assert "<!--zones-->" not in h0 and "<!--zones-->" in hz
    data0 = json.loads(re.search(r'type="application/json">(.*?)</script>', h0, re.S).group(1))
    assert "zones" not in data0
    # the addresses in the file: the satellite tiles only
    assert set(re.findall(r"https?://[a-zA-Z0-9.-]+", hz)) == {"https://server.arcgisonline.com"}


def test_labels_from_the_file_are_escaped(tmp_path, two):
    g = _gdf([_rect(-10, 150, -20, 200), _rect(150, 320, -20, 200)], zone=["<b>low</b>", "</script><i>x"])
    p = str(tmp_path / "evil & 'zones'.geojson")
    g.to_file(p, engine="pyogrio")
    P = rp._clean_floats(rp.replay_payload(two["shp"], zones=p, zone_column="zone"))
    h = rp.replay_html(P)
    assert "</script><i>" not in h and "<b>low</b>" not in h
    data = json.loads(re.search(r'type="application/json">(.*?)</script>', h, re.S).group(1))
    assert [c["label"] for c in data["zones"]["classes"]] == ["</script><i>x", "<b>low</b>"]
    # the player writes every label and name through esc() (no raw insertion of file text into the page)
    assert "esc(z.name)" in h and "esc(ZM.file)" in h and "esc(ZM.column)" in h


def test_command_line_with_zones(tmp_path, two, zone_file, capsys):
    out = str(tmp_path / "replay.html")
    csvp = str(tmp_path / "zone_yield.csv")
    assert rp.main([two["shp"], "--zones", zone_file, "--zone-column", "zone", "--zone-csv", csvp, "--out", out]) == 0
    txt = capsys.readouterr().out
    assert "management zones from zones_rx.geojson (column zone): 2 zones" in txt and "raw, not cleaned" in txt
    assert os.path.exists(out) and 'id="zpanel"' in open(out, encoding="utf-8").read()
    rows = list(csv.DictReader(open(csvp, encoding="utf-8")))
    assert rows and rows[0]["version"].startswith("interior")
    assert rp.main([two["shp"], "--zones", zone_file, "--zone-column", "nope", "--out", out]) == 2
    assert "has no column 'nope'" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        rp.main([two["shp"], "--zone-csv", csvp, "--out", out])


def _with_machine(tmp_path, two, name):
    import geopandas as gpd
    g = gpd.read_file(two["shp"])
    g.loc[g["Machine"] == "COMBINE-B", "Machine"] = name
    p = str(tmp_path / "renamed.shp")
    g.to_file(p, engine="pyogrio")
    return p


def test_a_name_that_opens_a_comment_does_not_stop_the_player(tmp_path, two):
    """'<!--<script' in a zone label, and in a machine name without any zone map: the data block still ends at its
    own </script> and holds no '<' at all; the names come back intact."""
    g = _gdf([_rect(-10, 150, -20, 400), _rect(150, 320, -20, 400)], zone=["<!--<script>alert(1)", "b"])
    zp = str(tmp_path / "z.geojson")
    g.to_file(zp, engine="pyogrio")
    cases = ((rp._clean_floats(rp.replay_payload(two["shp"], zones=zp)), "<!--<script>alert(1)"),
             (rp._clean_floats(rp.replay_payload(_with_machine(tmp_path, two, "<!--<script>x"))), "<!--<script>x"))
    for P, want in cases:
        h = rp.replay_html(P)
        m = re.search(r'<script id="rp-data" type="application/json">(.*?)</script>', h, re.S)
        assert m and "<" not in m.group(1)
        assert h[m.end():].lstrip().startswith("<script")          # the player's own script follows the data
        D = json.loads(m.group(1))
        names = [c["label"] for c in D["zones"]["classes"]] if "zones" in D else [C["id"] for C in D["combines"]]
        assert want in names


def test_the_title_is_escaped(two):
    h = rp.replay_html(rp._clean_floats(rp.replay_payload(two["shp"])), title="a</title><script>x")
    t = re.search(r"<title>(.*?)</title>", h, re.S).group(1)
    assert "<" not in t and "a&lt;/title&gt;&lt;script&gt;x" in t
    assert "__TITLE__" not in h and "__PAYLOAD__" not in h


def test_totals_of_a_cleaning_count_the_kept_readings(tmp_path, two):
    import geopandas as gpd
    g = gpd.read_file(two["shp"])
    keep = np.ones(len(g), int)
    keep[::3] = 0
    g["Keep"] = keep
    g["Rem_By"] = np.where(keep == 1, "", "S4")
    p = str(tmp_path / "flagged.shp")
    g.to_file(p, engine="pyogrio")
    P = rp.replay_payload(p, kind="clean")
    T = P["totals"]
    assert T["kept"] == int(keep.sum()) and T["removed"] == int((keep == 0).sum())
    w = g["Swth_Wdth_"].to_numpy(float) * FT
    d = g["Distance_f"].to_numpy(float) * FT
    ac = np.where((w > 0) & (d > 0), w * d / 4046.8564224, 0.0)
    assert T["area_ac"] == pytest.approx(float(ac[keep == 1].sum()), abs=2e-3)
    assert T["bu_ac"] == pytest.approx(T["bu"] / T["area_ac"], abs=0.01)


def test_a_zip_that_is_not_a_zip_is_a_clear_error(tmp_path, two, capsys):
    p = str(tmp_path / "zones.zip")
    open(p, "wb").write(b"this is not a zip archive" * 40)
    with pytest.raises(zn.ZoneMapError, match="zones.zip cannot be read: it is not a zip archive"):
        zn.prepare(p)
    out = str(tmp_path / "replay.html")
    assert rp.main([two["shp"], "--zones", p, "--out", out]) == 2
    err = capsys.readouterr().err
    assert err.startswith("error: the management zone map zones.zip cannot be read") and "Traceback" not in err
    # whatever else fails while the file is prepared is said in the zone map's words too
    g = _gdf([_rect(0, 10, 0, 10)], zone=[1])
    q = str(tmp_path / "ok.geojson")
    g.to_file(q, engine="pyogrio")
    import shapely
    real = shapely.union_all

    def boom(*a, **k):
        raise RuntimeError("GEOS said no")
    try:
        shapely.union_all = boom
        with pytest.raises(zn.ZoneMapError, match="ok.geojson cannot be used: GEOS said no"):
            zn.prepare(q)
    finally:
        shapely.union_all = real


def test_a_zone_map_that_misses_the_harvest_is_said(tmp_path, two):
    """All readings outside the zones (a map of another place): a note asks whether it is this field's; most of
    them outside: a note says the map covers part of it; a map over the harvest: no note."""
    ymax = float(two["df"]["y"].max()) + 30
    far = _gdf([_rect(5000, 5100, 5000, 5100), _rect(5100, 5200, 5000, 5100)], zone=[1, 2])
    part = _gdf([_rect(-10, 40, -20, ymax), _rect(40, 60, -20, ymax)], zone=[1, 2])
    notes = {}
    for name, g in (("far", far), ("part", part), ("full", _two_zone_map(y1=ymax))):
        p = str(tmp_path / f"{name}.geojson")
        g.to_file(p, engine="pyogrio")
        Z = rp.replay_payload(two["shp"], zones=p)["zones"]
        notes[name] = Z["coverage_note"]
        if Z["coverage_note"]:
            assert Z["notes"][0] == Z["coverage_note"]
    assert notes["far"].startswith("none of the") and "is it the zone map of this field" in notes["far"]
    assert "fall outside the management zones" in notes["part"] and "covers only part" in notes["part"]
    assert notes["full"] is None


def test_agreement_needs_the_minimum_of_readings_in_each_zone_of_a_combine():
    """A combine is compared only with MIN_COMBINE_READINGS interior readings in at least two zones: one reading
    fewer in each zone and it is not."""
    n = zn.MIN_COMBINE_READINGS

    def run(nb):
        zi = np.r_[np.zeros(n), np.ones(n), np.zeros(nb), np.ones(nb), np.zeros(n), np.ones(n)].astype(int)
        c = np.r_[np.zeros(2 * n), np.ones(2 * nb), np.full(2 * n, 2)].astype(int)
        y = np.r_[np.full(n, 50.0), np.full(n, 70.0), np.full(nb, 80.0), np.full(nb, 75.0), np.full(n, 40.0),
                  np.full(n, 60.0)]
        m = len(zi)
        ac, bd, use = np.full(m, 0.01), np.zeros(m, bool), np.ones(m, bool)
        S = zn.zone_stats(zi, bd, ac, y, use, c, ["1", "2"], [5.0, 5.0], ["A", "B", "C"])
        return zn.agreement(S, zi, bd, ac, y, use, c, ["1", "2"], ["A", "B", "C"])
    assert sorted(p["name"] for p in run(n - 1)["per_combine"]) == ["A", "C"]
    assert sorted(p["name"] for p in run(n)["per_combine"]) == ["A", "B", "C"]


def test_agreement_per_combine_says_how_close_its_order_is():
    """Each combine: its own order, the field's order of the same zones, a rank agreement (3 zones or more) and
    whether its lowest and highest zone are the field's."""
    n = zn.MIN_COMBINE_READINGS
    zi = np.tile(np.repeat([0, 1, 2], n), 2)
    c = np.repeat([0, 1], 3 * n)
    y = np.r_[np.repeat([50.0, 60.0, 70.0], n), np.repeat([50.0, 80.0, 75.0], n)]
    m = len(zi)
    ac, bd, use = np.full(m, 0.01), np.zeros(m, bool), np.ones(m, bool)
    labels = ["1", "2", "3"]
    S = zn.zone_stats(zi, bd, ac, y, use, c, labels, [5.0] * 3, ["A", "B"])
    A = zn.agreement(S, zi, bd, ac, y, use, c, labels, ["A", "B"])
    assert A["order_by_yield"] == ["1", "2", "3"]                # 50, 70, 72.5
    pa, pb = A["per_combine"]
    assert pa["same_as_field"] and pa["rho_field"] == pytest.approx(1.0) and pa["same_highest"] and pa["same_lowest"]
    assert pb["order_by_yield"] == ["1", "3", "2"] and pb["field_order"] == ["1", "2", "3"]
    assert not pb["same_as_field"] and pb["same_lowest"] and not pb["same_highest"]
    assert pb["rho_field"] == pytest.approx(0.5)                 # ranks 1 3 2 against 1 2 3


def test_thinning_does_not_change_the_zone_statistics(two, zone_file):
    P1 = rp.replay_payload(two["shp"], zones=zone_file)
    Pt = rp.replay_payload(two["shp"], zones=zone_file, max_bytes=2000)
    assert Pt["thin"] > 1
    assert Pt["zones"]["stats"] == P1["zones"]["stats"] and Pt["zones"]["cells"] == P1["zones"]["cells"]


def test_player_keeps_its_guards():
    """The player's own guards, present in the page (the behaviour itself is shown in a browser, outside the
    repository): space held down toggles once; a zoom step starts from the running zoom's target; fit keeps the
    field out of every card, panel, legend and bar; a cell thinned away still ends on its total."""
    h = open(rp.PLAYER, encoding="utf-8").read()
    assert 'if (k === " ") { ev.preventDefault(); if (!ev.repeat) togglePlay(); }' in h
    assert "const b = fly ? fly.b : { cx: S.cx, cy: S.cy, z: S.z };" in h
    assert "obs = overlayRects()" in h and all(s_ in h for s_ in ('"#zpanel"', '"#legend"', '".rp-bar"', '"#panel"'))
    assert "every reading of this cell thinned away" in h
