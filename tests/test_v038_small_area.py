# -*- coding: utf-8 -*-
"""0.3.8, the small area's display, on synthetic data only: the hover of the small area's map is short (what happened
to the reading, the share of its strip inside, the yield used, the bushels) and a click shows the whole calculation in
a card under the map; the harvest replay's small area (its polygons' figures and each reading's share) and the table
'Before and after the edits by hand' are grain / ground, the figures of the table the small area leads with, with the
cleaned map average beside them only where it is labelled so. A small area of 0.3.6 keeps its cleaned map average.

    python -m pytest -q tests/test_v038_small_area.py
"""
from __future__ import annotations

import ast
import json
import os
import sys

import geopandas as gpd
import numpy as np
import pyogrio
import pytest
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import replay as rp  # noqa: E402
from engine.clean import small_area as sa  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests import test_small_area_ground as T  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
SHORT_LINES = 4          # the hover: at most this many lines
SHORT_CHARS = 48         # of at most this many characters


@pytest.fixture(scope="module")
def dec(tmp_path_factory):
    p = T._decoded(str(tmp_path_factory.mktemp("dec38") / "x_decoded.shp"))
    D, note = sa.decoded_values(p, T.IMPORT_REC)
    assert note is None
    return D


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("sa38"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:3000].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    R = yc.run(shp, os.path.join(d, "out"), S, log=lambda m: None)
    G = gpd.read_file(R["files"]["flagged_shp"])
    x0, x1, y0, y1 = G.geometry.x.min(), G.geometry.x.max(), G.geometry.y.min(), G.geometry.y.max()
    poly = os.path.join(d, "plots.geojson")
    gpd.GeoDataFrame({"name": ["P1", "P2"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.31, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.62),
                               box(x0 + 0.0001, y0, x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.22)],
                     crs=4326).to_file(poly, driver="GeoJSON")
    return {"R": R, "poly": poly, "dir": d, "shp": shp}


def _app_defs(ns, *names):
    """Functions and module-level constants of app/oced.py by name, run into `ns`, without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in names)]
    exec(compile(ast.Module(nodes, []), APP, "exec"), ns)
    return ns


# ------------------------------------------------------------------------------------------------ the hover, short
def test_the_hover_is_short_and_the_card_holds_the_calculation(dec):
    M = sa.measure_all(T._flagged(), T._polys(), "clip", "ground", decoded=dec, detail_margin_m=10)
    D = M["ground_rows"]["P"]
    n = len(D["idx"])
    for j in range(n):
        H = sa.ground_hover_text(D, j, "P")
        assert len(H) <= SHORT_LINES and max(len(x) for x in H) <= SHORT_CHARS, H
        assert H[-1] == sa.HOVER_CLICK
        assert not any("SMS's query" in x or "Cleaned map average" in x for x in H)
    sh = np.asarray(D["share"], float)
    j = int(np.flatnonzero(np.asarray(D["touch"]) & (sh > 0.4) & (sh < 0.6))[0])
    # 0.4.0: the general map's pattern, 'label: value unit', two decimals (a reading's bushels under 0.1: three
    # significant digits, as the general map's hover writes a small value)
    g = 50 * T.A1
    gs = f"{g:,.2f}" if g >= 0.1 else f"{g:.3g}"
    assert sa.ground_hover_text(D, j, "P") == ["Dry yield: 100.00 bu/ac", "Reading: kept by the cleaning",
                                               f"Inside P: {100 * sh[j]:.2f} % of its strip · {gs} bu", sa.HOVER_CLICK]
    assert sa.ground_hover_fields(D, j, "P") == {"st": "kept by the cleaning", "shl": "Inside P",
                                                 "sh": f"{100 * sh[j]:.2f} % of its strip · {gs} bu",
                                                 "ck": sa.HOVER_CLICK}
    # the whole calculation stays in the card (ground_text), unchanged
    L = sa.ground_text(D, j, "P", M["cleaned_rows"]["P"])
    assert f"Grain counted 100.00 bu/ac x {T.A1:.5f} ac x 50.0 % = {50 * T.A1:.4f} bu" in L
    assert "SMS's query: its strip is not whole inside: not counted" in L
    r = int(np.flatnonzero(np.asarray(D["status"]) == "removed")[0])
    assert sa.ground_hover_text(D, r, "P")[1] == "Reading: removed by the cleaning (S5a)"
    q = int(np.flatnonzero(np.asarray(D["status"]) == "left_out")[0])
    assert sa.ground_hover_text(D, q, "P")[1] == "Reading: left out by the import"
    o = int(np.flatnonzero(~np.asarray(D["touch"], bool))[0])
    H = sa.ground_hover_text(D, o, "P")
    assert H[0] == "Dry yield: 100.00 bu/ac" and H[2] == "Outside P: not counted"
    p = M["polygons"][0]
    h = sa.ground_sum_hover(p).split("\n")
    assert h[:2] == ["Plot P", f"Grain / ground: {p['ground']['dry_yield_bu_ac']:,.2f} bu/ac"]
    assert len(h) <= SHORT_LINES and h[-1] == sa.HOVER_CLICK_SUMS
    assert sa.ground_sum_fields(p)["gg"] == f"{p['ground']['dry_yield_bu_ac']:,.2f} bu/ac"


def test_a_click_picks_the_card_of_the_reading_or_the_line():
    ns = _app_defs({"ss": {}}, "SA_LAYERS", "_sa_pick", "_md_text")
    ss = ns["ss"]
    ss["sa_map_k"] = {"selection": {"indices": {"sa-strips": [4]},
                                    "objects": {"sa-strips": [{"c": 7, "tip": "x"}]}}}
    ns["_sa_pick"]("k", "sig1")
    assert ss["sa_pick_k"] == {"sig": "sig1", "c": 7}
    # the counted part over its strip: the part wins (the same reading, the same card)
    ss["sa_map_k"] = {"selection": {"objects": {"sa-strips": [{"c": 3}], "sa-parts": [{"c": 5}]}}}
    ns["_sa_pick"]("k", "sig1")
    assert ss["sa_pick_k"]["c"] == 5
    ss["sa_map_k"] = {"selection": {"objects": {"sa-lines": [{"c": 11}]}}}
    ns["_sa_pick"]("k", "sig2")
    assert ss["sa_pick_k"] == {"sig": "sig2", "c": 11}
    ss["sa_map_k"] = {"selection": {"indices": {}, "objects": {}}}                 # a click on nothing
    ns["_sa_pick"]("k", "sig2")
    assert ss["sa_pick_k"] is None
    assert ns["_md_text"]("Yld_Vol_Dr x $5 [a]") == "Yld\\_Vol\\_Dr x \\$5 \\[a\\]"


# ------------------------------------------------------------------------------------------------ the replay
def test_the_replay_of_the_small_area_is_grain_over_ground(dec):
    fl = T._flagged()
    M = sa.measure_all(fl, T._polys(), "clip", "ground", decoded=dec)
    X = sa.replay_part(M, M["n"])
    p, q = M["polygons"][0], X["polygons"][0]
    assert X["method"] == "ground"
    for f in ("readings", "grain_bu", "ground_ac", "ground_pct", "dry_yield_bu_ac"):
        assert q[f] == p["ground"][f]
    assert q["cleaned_bu_ac"] == p["kept"]["dry_yield_bu_ac"] != q["dry_yield_bu_ac"]
    # every reading of the flagged file with a part of its strip inside, the two the cleaning removed too; the
    # one outside and the copy of a reading logged twice (counted once) are not; the straddling one at 50 %
    poly, share = X["by_row"]["poly"], X["by_row"]["share"]
    assert np.flatnonzero(poly == 1).tolist() == list(range(1, 14)) and poly[0] == 0 and poly[14] == 0
    assert set(np.flatnonzero((fl["Keep"].to_numpy() == 0))) <= set(np.flatnonzero(poly == 1))
    assert share[11] == 500 and share[1] == 1000
    # a small area of 0.3.6 (measure(), no method): the cleaned map average's counted readings, as before
    X0 = sa.replay_part(sa.measure(fl, T._polys(), "clip"), len(fl))
    assert X0["method"] is None and X0["polygons"][0]["dry_yield_bu_ac"] == p["kept"]["dry_yield_bu_ac"]
    assert int((X0["by_row"]["poly"] == 1).sum()) == p["kept"]["readings"] < int((poly == 1).sum())


def test_the_app_replay_payload_carries_the_lead_figures(clean, tmp_path):
    import replay_view
    R = clean["R"]
    rec = sa.run(R["files"]["flagged_zip"], clean["poly"], str(tmp_path / "r"), "x", "clip", log=lambda m: None)
    assert rec["method"] == "ground"
    fz, poly = R["files"]["flagged_zip"], clean["poly"]
    P = replay_view.payload_of(R["files"]["flagged_shp"], 0.0, "clean", None, {}, {}, {}, "t",
                               None, None, False, None, (fz, poly, 0.0, "clip", "ground", None, 0.0))
    SP = P["small_area"]
    assert SP["method"] == "ground" and [x["name"] for x in SP["polygons"]] == ["P1", "P2"]
    for x, p in zip(SP["polygons"], rec["polygons"]):
        assert x["dry_yield_bu_ac"] == pytest.approx(p["ground"]["dry_yield_bu_ac"], rel=1e-12)
        assert x["grain_bu"] == pytest.approx(p["ground"]["grain_bu"], rel=1e-12)
        assert x["ground_ac"] == pytest.approx(p["ground"]["ground_ac"], rel=1e-12)
        assert x["cleaned_bu_ac"] == pytest.approx(p["kept"]["dry_yield_bu_ac"], rel=1e-12)
    M = sa.detail_of(fz, poly, "clip", margin_m=0.0, method="ground")
    sp = np.concatenate([rp.decode_varint(C["data"]["sp"], C["n_shown"]) for C in P["combines"]])
    for k, name in enumerate(["P1", "P2"], start=1):
        D = M["ground_rows"][name]
        inside = {int(r) for r, t, s, src in zip(D["row"], D["touch"], D["share"], D["src"])
                  if t and s > 0 and src == "flagged"}
        assert int((sp == k).sum()) == len(inside)
    h = rp.replay_html(P)
    assert '"method":"ground"' in h and "grain / ground" in h
    # the 4-tuple of 0.3.7 (a small area of 0.3.6): the cleaned map average
    P0 = replay_view.payload_of(R["files"]["flagged_shp"], 0.0, "clean", None, {}, {}, {}, "t",
                                None, None, False, None, (fz, poly, 0.0, "clip"))
    assert P0["small_area"]["method"] is None
    assert [x["dry_yield_bu_ac"] for x in P0["small_area"]["polygons"]] == \
        [pytest.approx(p["kept"]["dry_yield_bu_ac"], rel=1e-12) for p in rec["polygons"]]


def test_the_map_hover_and_the_card_keep_the_name_as_it_is(clean, tmp_path):
    """The map's tooltip is an html template whose values the chart escapes itself: a polygon name with '<' or '&'
    (from the user's polygon file) reaches the chart as it is (escaped once, there, it shows as text and not as
    markup); the card under the map (markdown, escaped there) keeps the name as it is too."""
    import html as H

    import pandas as pd
    import streamlit as st
    ns = _app_defs({"st": st, "sarea": sa, "np": np, "pd": pd, "html": H}, "small_area_map_data", "SA_MAP_MARGIN_M",
                   "SA_MAP_MAX", "SA_FILL", "SA_LINE", "SA_YIELD", "SA_STRIP_ALPHA", "ATTR_INFO",
                   "rgba_of", "fmt_value")
    G = gpd.read_file(clean["poly"])
    G["name"] = ["Rate <120 & up", "B&B"]
    poly = str(tmp_path / "odd names.geojson")
    G.to_file(poly, driver="GeoJSON")
    fz = clean["R"]["files"]["flagged_zip"]
    MD = ns["small_area_map_data"](fz, 0.0, poly, 0.0, "clip", "ground")
    # 0.4.0: the hover's fields (the general map's 'v', the small area's st / shl / sh, a line's plot / gg / nr)
    texts = ([x["shl"] for x in MD["strips"] + MD["parts"]] + [x["sh"] for x in MD["strips"] + MD["parts"]]
             + [x["plot"] for x in MD["lines"]])
    assert any("Rate <120 & up" in t for t in texts) and any("B&B" in t for t in texts)
    for t in texts + [x["st"] for x in MD["strips"]]:
        assert "&lt;" not in t and "&gt;" not in t and "&amp;" not in t, t
    M = sa.detail_of(fz, poly, "clip", margin_m=0, method="ground")
    assert {x["plot"] for x in MD["lines"]} == {str(p_["name"]) for p_ in M["polygons"]}
    for p_ in M["polygons"]:
        L = [x for x in MD["lines"] if x["plot"] == str(p_["name"])]
        assert L and all(x["gg"] == sa.ground_sum_fields(p_)["gg"] and x["hd"] == "none" and x["pd"] == "inline"
                         for x in L)
    titles = [c["title"] for c in MD["cards"]]
    assert "Polygon Rate <120 & up" in titles and "Polygon B&B" in titles


# ------------------------------------------------------------------------------------------------ before / after
def test_the_before_and_after_rows_are_grain_over_ground():
    ns = _app_defs({}, "before_after_rows")
    G0 = {"readings": 10, "grain_bu": 5.0, "ground_ac": 0.1, "dry_yield_bu_ac": 50.0, "kept": 9, "removed_by_hand": 0}
    G1 = {"readings": 10, "grain_bu": 5.0, "ground_ac": 0.1, "dry_yield_bu_ac": 50.0, "kept": 7, "removed_by_hand": 2}
    K0 = {"readings": 9, "area_ac": 0.09, "total_dry_bu": 4.95, "dry_yield_bu_ac": 55.0}
    K1 = {"readings": 7, "area_ac": 0.07, "total_dry_bu": 3.92, "dry_yield_bu_ac": 56.0}
    SA = {"method": "ground", "polygons": [{"name": "A", "kept": K1, "ground": dict(G1, spread={})}]}
    BF = {"polygons": [{"name": "A", "kept": K0, "ground": G0}]}
    rows, num, ground = ns["before_after_rows"](SA, BF)
    assert ground and rows == [{"polygon": "A", "readings before": 10, "readings after": 10,
                                "ground ac before": 0.1, "ground ac after": 0.1,
                                "grain bu before": 5.0, "grain bu after": 5.0,
                                "bu/ac before": 50.0, "bu/ac after": 50.0,
                                "kept before": 9, "kept after": 7,
                                "removed by hand before": 0, "removed by hand after": 2,
                                "cleaned map average bu/ac before": 55.0, "cleaned map average bu/ac after": 56.0}]
    assert num["ground ac before"] == "%.3f" and num["bu/ac after"] == "%.2f" and "readings before" not in num
    assert not {"kept before", "kept after", "removed by hand before", "removed by hand after"} & set(num)
    # a 'before' without grain / ground (saved before 0.3.8), or a small area of 0.3.6: the cleaned map average
    for SA_, BF_ in ((SA, {"polygons": [{"name": "A", "kept": K0}]}),
                     ({"polygons": SA["polygons"]}, BF)):
        rows, num, ground = ns["before_after_rows"](SA_, BF_)
        assert not ground and rows[0]["bu/ac before"] == 55.0 and rows[0]["bu/ac after"] == 56.0
        assert rows[0]["ac before"] == 0.09 and num["ac before"] == "%.3f"


# ------------------------------------------------------------------------------------------------ the app
def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _run(at):
    at.run()
    assert not at.exception, [str(e.value)[:800] for e in at.exception]


def _sa_chart(at):
    for e in at.get("deck_gl_json_chart"):
        spec = json.loads(e.proto.json)
        if any(L.get("id") == "sa-strips" for L in spec.get("layers") or []):
            return e, spec
    raise AssertionError("no small area map")


def _layer(spec, lid):
    return next(L for L in spec["layers"] if L.get("id") == lid)["data"]


def test_app_short_hover_card_on_click_replay_and_before_after(clean, tmp_path, monkeypatch):
    import replay_view
    from tests.test_replay_edits import _where
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(clean["shp"])
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    tag = at.session_state["active"]
    # 0.4.0: the polygon file is given in step 1 (keys by file), Measure is in step 5, Plots (by clean file), drawn
    # once a plot boundary is given
    ka = next(k for k in at.session_state.filtered_state if str(k).startswith("sa_rule_"))[len("sa_rule_"):]
    at.text_input(key=f"sa_path_{ka}").input(clean["poly"])
    _run(at)
    ks = next(str(b.key) for b in at.button if str(b.key or "").startswith("sa_go_"))[len("sa_go_"):]
    at.button(key=f"sa_go_{ks}").click()
    _run(at)
    S0 = at.session_state["cleaned"][tag]["R"]["small_area"]
    assert S0["method"] == "ground"
    # the map: selectable (one object), its tooltip the general map's hover (map_tooltip: '<b>Dry yield</b>: v',
    # 'Plot <name>' on a line) with the small area's short lines, in its own box; every layer with an id
    import html as H
    e, spec = _sa_chart(at)
    ns = _app_defs({"html": H}, "MAP_TIP_STYLE", "map_tooltip", "SA_TIP_MORE", "SA_TIP_CLASS")
    tt = json.loads(e.proto.tooltip)
    want = ns["map_tooltip"]("Dry yield", plots=True, more=ns["SA_TIP_MORE"], cls=ns["SA_TIP_CLASS"])
    assert list(e.proto.selection_mode) and tt["html"] == want["html"] and tt["style"] == want["style"]
    assert tt["html"].startswith('<div class="oced-sa-tip"><span style="display:{hd}"><b>Dry yield</b>: {v}</span>')
    strips, lines = _layer(spec, "sa-strips"), _layer(spec, "sa-lines")
    rows = strips + _layer(spec, "sa-parts")
    for r in rows:
        L = [f"Dry yield: {r['v']}", f"Reading: {r['st']}", f"{r['shl']}: {r['sh']}", r["ck"]]
        assert len(L) <= SHORT_LINES and max(len(x) for x in L) <= SHORT_CHARS, L
        assert r["v"].endswith(" bu/ac") and "SMS's query" not in " ".join(L) and "Grain counted" not in " ".join(L)
    assert any(r["shl"] == "Inside P1" and " % of its strip · " in r["sh"] for r in rows)
    # the script that keeps the hover inside the map
    assert any("__ocedSaTipFit" in str(h.proto) for h in at.get("html"))
    assert not [k for k in at.session_state.filtered_state if str(k).startswith("sa_card_")]
    # a click on a counted reading (the selection callback's result): its whole calculation under the map
    sig = at.session_state[f"sa_sig_{ks}"]
    s = next(x for x in strips if x["shl"] == "Inside P1" and x["st"] == "kept by the cleaning")
    at.session_state[f"sa_pick_{ks}"] = {"sig": sig, "c": s["c"]}
    _run(at)
    md = " ".join(m.value for m in at.markdown)
    assert "Grain counted" in md and "Its part of the ground" in md and "SMS's query" in md
    assert "Polygon P1" in md and "Cleaned map average" in md
    # the polygon's line: grain / ground's sum and the cleaned map average's, labelled
    at.session_state[f"sa_pick_{ks}"] = {"sig": sig, "c": lines[0]["c"]}
    _run(at)
    md = " ".join(m.value for m in at.markdown)
    p1 = S0["polygons"][0]
    assert "**Polygon P1**" in md and f"= {p1['ground']['dry_yield_bu_ac']:,.2f} bu/ac" in md
    assert "cleaned map average: " in md
    # a pick of another map (its signature) is not shown
    at.session_state[f"sa_pick_{ks}"] = {"sig": "other", "c": lines[0]["c"]}
    _run(at)
    assert "**Polygon P1**" not in " ".join(m.value for m in at.markdown)
    at.session_state[f"sa_pick_{ks}"] = None
    # the replay: the polygons with grain / ground, the figure of the table that leads
    C0 = at.session_state["cleaned"][tag]
    ck = next(k for k in at.session_state.filtered_state if str(k).startswith("replay_box_clean_"))[len("replay_box_"):]
    at.session_state[f"replay_box_{ck}"] = True
    _run(at)
    html = next(json.loads(x.proto.json)["html"] for x in at.get("bidi_component")
                if '"kind":"clean"' in json.loads(x.proto.json)["html"])
    i = html.index('"small_area":{')
    SP = json.loads(html[i + len('"small_area":'):html.index(',"bbox"', i)] + "}")
    assert [x["name"] for x in SP["polygons"]] == ["P1", "P2"]
    for x, p in zip(SP["polygons"], S0["polygons"]):
        assert x["dry_yield_bu_ac"] == pytest.approx(p["ground"]["dry_yield_bu_ac"], rel=1e-12)
        assert x["readings"] == p["ground"]["readings"]
        assert x["cleaned_bu_ac"] == pytest.approx(p["kept"]["dry_yield_bu_ac"], rel=1e-12)
    # Edit points: 6 kept readings inside P1 removed -> reprocess -> 'Before and after the edits by hand'
    P = rp.replay_payload(C0["flagged_shp"], kind="clean", record=C0["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C0["flagged_shp"], read_geometry=False)
    A = at.session_state["small_area"][tag]
    M = sa.detail_of(C0["flagged_zip"], A["path"], "clip", margin_m=0)
    inside = set(np.asarray(M["readings"]["P1"]["idx"])[np.asarray(M["readings"]["P1"]["counted"])].tolist())
    rm = _where(P, F, lambda r: r.name in inside, 6)
    at.session_state[f"replay_box_{ck}"] = True
    at.session_state[replay_view.marks_key(ck)] = {"token": P["edit"]["token"], "remove": rm, "keep": [],
                                                  "changed": 6}
    _run(at)
    S1 = at.session_state["cleaned"][tag]["R"]["small_area"]
    assert S1["before"]["polygons"][0]["ground"] == {f: S0["polygons"][0]["ground"][f]
                                                     for f in ("readings", "grain_bu", "ground_ac", "dry_yield_bu_ac",
                                                               "kept", "removed_by_hand")}
    assert S1["polygons"][0]["kept"]["readings"] == S0["polygons"][0]["kept"]["readings"] - 6
    tab = next(d.value for d in at.dataframe if "bu/ac before" in d.value.columns)
    assert list(tab["polygon"]) == ["P1", "P2"]
    for i_, (b, a) in enumerate(zip(S0["polygons"], S1["polygons"])):
        assert tab["bu/ac before"].iloc[i_] == pytest.approx(b["ground"]["dry_yield_bu_ac"], rel=1e-12)
        assert tab["bu/ac after"].iloc[i_] == pytest.approx(a["ground"]["dry_yield_bu_ac"], rel=1e-12)
        assert tab["readings before"].iloc[i_] == b["ground"]["readings"]
        assert tab["grain bu after"].iloc[i_] == pytest.approx(a["ground"]["grain_bu"], rel=1e-12)
        assert tab["cleaned map average bu/ac before"].iloc[i_] == pytest.approx(b["kept"]["dry_yield_bu_ac"],
                                                                                 rel=1e-12)
        assert tab["cleaned map average bu/ac after"].iloc[i_] == pytest.approx(a["kept"]["dry_yield_bu_ac"],
                                                                                rel=1e-12)
    # the edits by hand take readings out of the cleaned map average, not out of grain / ground
    assert tab["cleaned map average bu/ac before"].iloc[0] != tab["cleaned map average bu/ac after"].iloc[0]
    assert tab["bu/ac after"].iloc[0] == pytest.approx(tab["bu/ac before"].iloc[0], rel=1e-12)
    # ... but they change the status of its readings: the 6 kept ones removed by hand
    assert tab["kept after"].iloc[0] == tab["kept before"].iloc[0] - 6
    assert tab["removed by hand after"].iloc[0] == tab["removed by hand before"].iloc[0] + 6
    assert list(tab["kept after"]) == [a["ground"]["kept"] for a in S1["polygons"]]
    assert any("Before and after the edits by hand** · grain / ground" in m.value for m in at.markdown)
