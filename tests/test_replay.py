# -*- coding: utf-8 -*-
"""The harvest replay (engine/replay.py, app/replay_view.py) on synthetic data only: the payload (order and clock of
two combines working at the same time, the fallback without a clock, idle time, heading, the quantisation round trip,
the size cap), the strips are the app's map strips, the make of each combine, the HTML is one self-contained document
with no address but the satellite tiles, and the command line (the app's sections: test_replay_app.py).

    python -m pytest -q tests/test_replay.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import replay as rp  # noqa: E402
from engine import run as er  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.synthetic_replay import make_two_at_once  # noqa: E402


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    return make_two_at_once(str(tmp_path_factory.mktemp("replay_two")))


@pytest.fixture(scope="module")
def P2(two):
    return rp.replay_payload(two["shp"], rows=True)


def _cols(P, C):
    return rp.payload_columns(P, C)


# ------------------------------------------------------------------------------------------------ the payload
def test_two_combines_share_one_clock(two, P2):
    """Two combines working at the same time: one clock for both (each starts at 0 s, the file order A then B does
    not put B after A), the readings of each in time order, and each reading's time is its own clock time."""
    assert P2["kind"] == "import" and P2["basis"]["kind"] == "clock"
    assert [C["id"] for C in P2["combines"]] == ["COMBINE-A", "COMBINE-B"]
    df = two["df"]
    for C in P2["combines"]:
        c = _cols(P2, C)
        assert np.all(np.diff(c["t"]) >= 0)
        truth = df.iloc[C["rows"]]["t"].to_numpy()
        assert np.allclose(c["t"], truth - truth.min() + (truth.min() - df["t"].min()), atol=0.051)
    a, b = (_cols(P2, C)["t"] for C in P2["combines"])
    assert a[0] == 0 and b[0] == 0                       # both start at the first reading of the field
    assert b[-1] < a[-1] + 1                            # B ends before A ends + 1 s (not after it)
    assert P2["t_end"] >= max(a[-1], b[-1])
    assert P2["t0"] == pytest.approx(two["t0"].timestamp(), abs=1)   # the monitor's clock, as written
    assert P2["combines"][0]["num"] == 1 and P2["combines"][0]["color"] != P2["combines"][1]["color"]


def test_file_order_does_not_matter(tmp_path, two):
    """The same readings shuffled in the file: the same payload columns (each combine in time order)."""
    import geopandas as gpd
    g = gpd.read_file(two["shp"])
    sh = g.sample(frac=1.0, random_state=1).reset_index(drop=True)
    p = str(tmp_path / "shuffled.shp")
    sh.to_file(p, engine="pyogrio")
    A = rp.replay_payload(two["shp"])
    B = rp.replay_payload(p)
    for ca, cb in zip(A["combines"], B["combines"]):
        assert ca["id"] == cb["id"] and ca["n"] == cb["n"]
        xa, xb = _cols(A, ca), _cols(B, cb)
        for k in ("t", "lon", "lat", "y", "m", "s", "w"):
            assert np.allclose(xa[k], xb[k], equal_nan=True), k


def test_quantisation_round_trip(two, P2):
    """Every column back within its quantum: 1e-7 deg, 0.1 s, 0.1 bu/ac, 0.01 % and mph, 1 cm."""
    df = two["df"]
    from tests.synthetic import _lonlat
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    for C in P2["combines"]:
        r = np.array(C["rows"])
        c = _cols(P2, C)
        assert np.max(np.abs(c["lon"] - lon[r])) <= 1.01e-7
        assert np.max(np.abs(c["lat"] - lat[r])) <= 1.01e-7
        assert np.max(np.abs(c["y"] - df["Yld_Vol_Dr"].to_numpy()[r])) <= 0.0501
        assert np.max(np.abs(c["m"] - df["Moisture__"].to_numpy()[r])) <= 0.00501
        assert np.max(np.abs(c["s"] - df["Speed_mph_"].to_numpy()[r])) <= 0.00501
        assert np.max(np.abs(c["w"] - df["Swth_Wdth_"].to_numpy()[r] * 0.3048)) <= 0.00501
        assert np.max(np.abs(c["d"] - df["Distance_f"].to_numpy()[r] * 0.3048)) <= 0.00501


def test_varint_round_trip():
    v = np.array([0, 5, -3, 2 ** 40, -(2 ** 33), 7, 7, 7, 127, 128, -64, -65])
    assert np.array_equal(rp.decode_varint(rp._varint(v)), v)
    assert rp._varint([4, 4, 4]) == "=4" and np.array_equal(rp.decode_varint("=4", 3), [4, 4, 4])


def test_idle_time_of_the_field_and_of_one_combine(two, P2):
    """Lunch (both combines stopped) is an idle gap of the field, skipped in playback; A's pause alone breaks A's
    activity but is not an idle gap of the field (B works then)."""
    gaps = P2["idle"]
    assert len(gaps) == 1
    g0, g1 = gaps[0]
    # A paused alone earlier, so its lunch starts pause_s later than B's: the field is idle while both are
    assert g1 - g0 == pytest.approx(two["lunch_s"] + 25 - two["pause_s"], abs=5)
    runs = {C["id"]: C["runs"] for C in P2["combines"]}
    assert len(runs["COMBINE-A"]) == 3 and len(runs["COMBINE-B"]) == 2
    assert P2["idle_skip_s"] < two["lunch_s"] and P2["idle_gap_s"] < two["pause_s"]


def test_heading_from_track_and_from_positions(tmp_path):
    """The direction of travel: east passes 90 deg, west passes 270 deg, with or without a Track column."""
    for track in (True, False):
        F = make_two_at_once(str(tmp_path / f"t{track}"), track=track, n_pass=4)
        P = rp.replay_payload(F["shp"], rows=True)
        C = P["combines"][0]
        c = _cols(P, C)
        p = F["df"].iloc[C["rows"]]["pass"].to_numpy()
        mid = np.r_[False, (p[1:] == p[:-1])] & np.r_[(p[:-1] == p[1:]), False]
        east = mid & (p % 2 == 0)
        west = mid & (p % 2 == 1)
        assert np.max(np.abs(((c["dir"][east] - 90 + 180) % 360) - 180)) < 1.0
        assert np.max(np.abs(((c["dir"][west] - 270 + 180) % 360) - 180)) < 1.0


def test_strips_are_the_apps_map_strips(two, P2):
    """The strips the player rebuilds from the payload are the app's map strips (engine.run.preview_swaths, which
    uses yield_clean.swept_strips): every corner within 5 cm."""
    Q = rp.payload_quads(P2)
    pv = er.preview_swaths(two["shp"], None, n_max=10 ** 9)
    poly = {int(r): np.array(p) for r, p in zip(pv["row"], pv["polygon"]) if p is not None}
    lat0 = P2["center"][1]
    kx, ky = np.cos(np.radians(lat0)) * 111_195.0, 111_195.0
    worst, n = 0.0, 0
    for cid, (rows, q) in Q.items():
        for r, qq in zip(rows, q):
            p = poly.get(int(r))
            if p is None or not np.isfinite(qq).all():
                continue
            d = np.hypot((p[:, None, 0] - qq[None, :, 0]) * kx, (p[:, None, 1] - qq[None, :, 1]) * ky)
            worst = max(worst, d.min(axis=1).max(), d.min(axis=0).max())
            n += 1
    assert n > 0.95 * P2["n"]
    assert worst < 0.05


def test_no_time_of_day_falls_back_and_says_so(tmp_path):
    """A date-only Time (an SMS point export) or no Time: never a made-up clock. With dataset names that carry a start
    time: that start plus the durations; without: the file order, one reading after another."""
    F = make_two_at_once(str(tmp_path / "date"), time="date")
    P = rp.replay_payload(F["shp"])
    assert P["basis"]["kind"] == "order" and "No clock" in P["basis"]["note"]
    a, b = (_cols(P, C)["t"] for C in P["combines"])
    assert np.all(np.diff(a) > 0) and b[0] >= a[-1]     # B after A, in the file order: never shown together
    assert np.allclose(np.diff(a), 1.0, atol=0.051)    # each reading its 1 s duration
    F = make_two_at_once(str(tmp_path / "none"), time="none")
    assert rp.replay_payload(F["shp"])["basis"]["kind"] == "order"
    F = make_two_at_once(str(tmp_path / "stamps"), time="date", dataset_stamps=True)
    P = rp.replay_payload(F["shp"])
    assert P["basis"]["kind"] == "dataset" and "dataset" in P["basis"]["note"]
    a, b = (_cols(P, C)["t"] for C in P["combines"])
    assert a[0] == 0 and b[0] == 0                      # both datasets start at 13:00:00 by their names


def test_times_with_their_zone_are_instants(tmp_path, two):
    """Times that carry their zone (an Operations Center IsoTime, '...Z') are instants: shown in this computer's clock
    time, as UTC logs are; the same times without a zone are shown as written (the monitor's clock)."""
    import geopandas as gpd
    g = gpd.read_file(two["shp"])
    g["Time"] = [str(t).replace(" ", "T") + "Z" for t in g["Time"]]
    p = str(tmp_path / "zoned.shp")
    g.to_file(p, engine="pyogrio")
    P = rp.replay_payload(p)
    assert P["basis"]["kind"] == "clock" and "time zone" in P["basis"]["note"]
    assert "computer's clock" in P["basis"]["zone"]
    off = rp._clock_offset_h(two["t0"].replace(tzinfo=None).timestamp())
    P0 = rp.replay_payload(two["shp"])
    assert "monitor's clock" in P0["basis"]["zone"]
    # the same instant, moved by this computer's offset from UTC (its own zone wherever the tests run)
    assert P["t0"] - P0["t0"] == pytest.approx(off * 3600, abs=3600 * 1.01)


def test_size_cap_thins_and_says_so(two):
    """Above the cap the readings are thinned (every k-th of each combine), the distance of the skipped readings is
    carried by the kept one, and the payload says how many are shown."""
    full = rp.replay_payload(two["shp"])
    P = rp.replay_payload(two["shp"], max_bytes=full["bytes"] // 3)
    assert P["thin"] >= 3 and P["bytes"] <= full["bytes"] // 3
    for Cf, C in zip(full["combines"], P["combines"]):
        assert C["n_shown"] == len(range(0, C["n"], P["thin"])) < C["n"]
        df, dt = _cols(full, Cf)["d"], _cols(P, C)["d"]
        assert dt.sum() == pytest.approx(df[:len(range(0, C["n"], P["thin"])) * P["thin"]].sum(), rel=0.02)
    html = rp.replay_html(P)
    assert "Showing 1 in" in html                       # the player's sentence for a thinned file


def test_size_of_130k_readings_is_small():
    """About 12 bytes a reading: 130,000 readings fit far below the 6 MB of HTML aimed at (estimated from a
    synthetic file of 4,000 readings, the same columns)."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        F = make_two_at_once(d, n_pass=12, pass_len_m=500)
        P = rp.replay_payload(F["shp"])
        per = P["bytes"] / P["n"]
        assert per < 24
        assert per * 130_000 < 5_500_000


# ------------------------------------------------------------------------------------------------ the makes
def test_make_of_the_combine():
    assert rp.make_of(None, "jd_jdl", "1H0X911XAAA000001")[0] == "john_deere"
    assert rp.make_of(None, "jd_gs3_rcd", "")[0] == "john_deere"
    k, why = rp.make_of(None, "jd_jdl", "XYZ0001")
    assert k == "generic" and "not a John Deere" in why
    assert rp.make_of("Axial Flow 50 Series", "cnh_cn1", "X")[0] == "case_ih"
    assert rp.make_of("New Holland CR", "cnh_cn1", "X")[0] == "new_holland"
    assert rp.make_of("LEXION 8800", None, "x")[0] == "claas"
    assert rp.make_of("Massey Ferguson 9545", None, None)[0] == "massey_ferguson"
    assert rp.make_of("Fendt IDEAL", None, None)[0] == "fendt"
    assert rp.make_of("Gleaner S9", None, None)[0] == "gleaner"
    assert rp.make_of(None, "cnh_cn1", "AB123")[0] == "generic"
    assert rp.make_of(None, None, "COMBINE-A")[0] == "generic"
    assert rp.make_of(None, "cnh_cn1", "AB123", {"make": "new_holland", "why": "w"}) == ("new_holland", "w")
    for k, M in rp.MAKES.items():
        assert {"body", "accent", "rim", "header", "reel", "roof", "label"} <= set(M), k


def test_make_hints_from_a_synthetic_card(tmp_path):
    """What a Case IH / New Holland card says of the make: the combine folder's model text, else the display log's
    vehicle_brand (one brand on the card); ISOXML: the task controller's maker. Made-up files."""
    c1 = tmp_path / "AAA.cn1"
    (c1 / "COMBINES" / "AB1C2").mkdir(parents=True)
    (c1 / "COMBINES" / "AB1C2" / "AB1C2.agp").write_bytes(b"CNH1\x00\x10Axial Flow 99 Series\x00\x00")
    (c1 / "log").mkdir()
    (c1 / "log" / "a.txt").write_bytes(b"... vehicle_brand: 0x1, vehicle model value = 1 ...")
    c2 = tmp_path / "BBB.cn1"
    (c2 / "COMBINES" / "ZZ9Y8").mkdir(parents=True)
    (c2 / "COMBINES" / "ZZ9Y8" / "ZZ9Y8.agp").write_bytes(b"CNH1\x00\x00\x00\x00")
    (c2 / "log").mkdir()
    (c2 / "log" / "b.txt").write_bytes(b"vehicle_brand: 0x2, vehicle model value = 2")
    (tmp_path / "TASKDATA").mkdir()
    (tmp_path / "TASKDATA" / "TASKDATA.XML").write_bytes(
        b'<ISO11783_TaskData TaskControllerManufacturer="CLAAS E-Systems"><DVC A="DVC-1" B="x" E="777"/>'
        b'</ISO11783_TaskData>')
    H = rp.make_hints(str(tmp_path))
    assert H["AB1C2"]["make"] == "case_ih" and "Axial" in H["AB1C2"]["model"]
    assert H["ZZ9Y8"]["make"] == "new_holland" and "0x2" in H["ZZ9Y8"]["why"]
    assert H["777"]["make"] == "claas"
    assert rp._hint_for("AB1C2000AB1C2", H)["make"] == "case_ih"   # the decoded Machine starts with the folder
    assert rp.make_hints(str(tmp_path / "nowhere")) == {}


def test_payload_make_from_hints_and_override(two):
    P = rp.replay_payload(two["shp"], hints={"COMBINE-A": {"make": "case_ih", "why": "the card"}},
                          makes={"COMBINE-B": "new_holland"})
    mk = {C["id"]: (C["make"], C["make_why"]) for C in P["combines"]}
    assert mk["COMBINE-A"] == ("case_ih", "the card") and mk["COMBINE-B"] == ("new_holland", "set by hand")
    assert set(P["makes"]) == set(rp.MAKES)


# ------------------------------------------------------------------------------------------------ the HTML
def test_html_is_one_self_contained_document(two, P2):
    html = rp.replay_html(rp._clean_floats(P2))
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert html.count("<html") == 1 and html.rstrip().endswith("</html>") and html.count("</html>") == 1
    urls = set(re.findall(r"https?://[^\s\"'<>)]+", html))
    assert urls and all(u.startswith("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/") for u in urls), urls
    low = html.lower()
    assert not re.search(r"<script[^>]+\bsrc\s*=", low) and "<link" not in low and "@import" not in low
    assert "@font-face" not in low and not re.search(r"url\(\s*['\"]?(https?:)?//", low)
    assert "fetch(" not in html and "XMLHttpRequest" not in html
    data = re.search(r'<script id="rp-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    Pj = json.loads(data)
    assert Pj["n"] == P2["n"] and len(Pj["combines"]) == 2
    assert "Imagery © Esri" in html                    # the tiles' attribution


def test_html_escapes_the_file_text(tmp_path):
    """A machine name with '</script>' cannot end the data block."""
    import geopandas as gpd
    F = make_two_at_once(str(tmp_path / "x"), n_pass=2)
    g = gpd.read_file(F["shp"])
    g["Machine"] = g["Machine"].str.replace("COMBINE-A", "A</script><b>x")
    p = str(tmp_path / "evil.shp")
    g.to_file(p, engine="pyogrio")
    html = rp.replay_html(rp._clean_floats(rp.replay_payload(p)))
    data = re.search(r'<script id="rp-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    assert "A\\u003c/script>" in data and "<" not in data       # every '<' of the data as its JSON escape
    assert json.loads(data)["combines"][0]["id"].startswith("A</script>")


def test_command_line(tmp_path, two, capsys):
    out = str(tmp_path / "r.html")
    assert rp.main([two["shp"], "--boundary", two["boundary"], "--make", "COMBINE-A=claas", "--out", out]) == 0
    html = open(out, encoding="utf-8").read()
    data = json.loads(re.search(r'type="application/json">(.*?)</script>', html, re.S).group(1))
    assert data["outline"] and data["combines"][0]["make"] == "claas"
    assert "2 combine(s)" in capsys.readouterr().out


def test_cleaning_replay_kept_and_removed(tmp_path):
    """The flagged file of a cleaning: kind 'clean', every reading kept or removed with the step that removed it,
    the names of the steps from the cleaning record, the totals of the kept readings."""
    F = make_field(str(tmp_path / "f"))
    R = er.clean(F["shp"], str(tmp_path / "out"), {"method": "sms3sigma", "aoi": {"file": F["boundary"]}},
                 log=lambda m: None)
    fl = R["files"].get("flagged_shp") or glob.glob(str(tmp_path / "out" / "*_flagged.shp"))[0]
    P = rp.build(fl)
    assert P["kind"] == "clean"
    import pyogrio
    keep = pyogrio.read_dataframe(fl, columns=["Keep", "Rem_By"])
    assert P["totals"]["removed"] == int((keep["Keep"] != 1).sum()) > 0
    assert sum(s["n"] for s in P["steps"]) == P["totals"]["removed"]
    names = {s["code"]: s["name"] for s in P["steps"]}
    assert any("moisture" in v for v in names.values()) and any("speed" in v for v in names.values())
    flags = np.concatenate([_cols(P, C)["f"] for C in P["combines"]])
    assert int(((flags >> 1) & 1).sum()) == P["totals"]["removed"]
