# -*- coding: utf-8 -*-
"""0.3.7 repair round, on synthetic data only: the hover text of a reading removed by hand (Edit points) says so and
the clip line says how much was cut away (engine/clean/small_area.py reading_text); step 2's files without cleaning
are written only when asked for or after an edit there, so opening a work writes nothing new into it; the DIFM file
without cleaning speaks of the data in use; after Apply step 2 says the edits once; a small area measured by 0.3.6
(its record only, the polygon file in the cleaning's small_area_input/) is kept with the file, drawn, copied out of
the cleaning's folder before the next cleaning and measured again, and the small-area map draws the readings removed
by hand apart from the ones the cleaning removed.

    python -m pytest -q tests/test_v037_repair.py
"""
from __future__ import annotations

import json
import os
import shutil
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
from engine import run as er  # noqa: E402
from engine.clean import manual_edits as me  # noqa: E402
from engine.clean import small_area as sa  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
N_SMALL = 3000


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("rep"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:N_SMALL].copy()
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
    return {"R": R, "S": S, "poly": poly, "dir": d, "shp": shp}


# ------------------------------------------------------------------------------------------------ the engine
def test_the_hover_says_removed_by_hand_and_how_much_was_cut(field, tmp_path):
    M0 = sa.detail_of(field["R"]["files"]["flagged_zip"], field["poly"], "clip", margin_m=0)
    D0 = M0["readings"]["P1"]
    keys = [str(k) for k in me.flagged_keys(field["R"]["files"]["flagged_shp"])[0]]
    counted = np.asarray(D0["idx"])[np.asarray(D0["counted"], bool)]
    # 8 readings counted in P1 removed by hand (the keys of the flagged file's rows, as the replay gives them)
    rows = [int(r) for r in counted[:8]]
    ep = me.write_edits(str(tmp_path / "e.json"), remove=[keys[r] for r in rows])
    B = yc.run(field["shp"], str(tmp_path / "b"), dict(field["S"], manual_edits=ep["file"]), log=lambda m: None)
    fb = pyogrio.read_dataframe(B["files"]["flagged_shp"], read_geometry=False)
    assert (fb["Rem_By"] == me.STEP).sum() == 8
    M = sa.detail_of(B["files"]["flagged_zip"], field["poly"], "clip", margin_m=10)
    D = M["readings"]["P1"]
    hand = [j for j in range(len(D["idx"])) if sa.removed_by_hand(D, j)]
    auto = [j for j in range(len(D["idx"])) if D["why"][j] == "removed" and not sa.removed_by_hand(D, j)]
    assert len(hand) == 8 and auto
    for j in hand:
        L = sa.reading_text(D, j, "P1", "clip")
        assert L[1] == "Removed by hand (Edit points): its yield is not used"
        assert not any("Removed by the cleaning" in x for x in L)
    L = sa.reading_text(D, auto[0], "P1", "clip")
    assert L[1].startswith("Removed by the cleaning (") and "SM" not in L[1]
    # a straddling counted reading: the share inside, the area counted, and the part cut off
    sh = np.asarray(D["share"], float)
    j = int(np.flatnonzero(np.asarray(D["counted"]) & (sh > 0.2) & (sh < 0.8))[0])
    a, full = float(D["area_ac"][j]), float(D["full_ac"][j])
    line = next(x for x in sa.reading_text(D, j, "P1", "clip") if x.startswith("Clip: "))
    assert line == (f"Clip: {100 * sh[j]:.0f} % inside: {a:.5f} of {full:.5f} ac counted; "
                    f"{100 * (1 - sh[j]):.0f} % cut off: {full - a:.5f} ac")
    # a reading whole inside: no 'cut off'
    jw = int(np.flatnonzero(np.asarray(D["counted"]) & (sh >= 0.9999))[0])
    assert "cut off" not in " ".join(sa.reading_text(D, jw, "P1", "clip"))
    # the figures are the ones of a run of the module (the text changed, not the calculation)
    rec = sa.run(B["files"]["flagged_zip"], field["poly"], str(tmp_path / "r"), "x", "clip", log=lambda m: None)
    c = np.asarray(D["counted"], bool)
    assert float(np.asarray(D["bu"])[c].sum()) == pytest.approx(rec["polygons"][0]["kept"]["total_dry_bu"],
                                                                 rel=1e-12)


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


def _files_under(d):
    out = {}
    for r, _, fs in os.walk(d):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, d)] = os.path.getmtime(p)
    return out


def _imp_key(at):
    import hashlib
    D = at.session_state["datasets"][at.session_state["active"]]
    return "imp_" + hashlib.md5(str(D["shp"]).encode("utf-8")).hexdigest()[:8], D["shp"]


def _send(at, key, shp, rows, E=None):
    import replay_view
    P = rp.replay_payload(shp, kind="import", edits=E if E is not None else {}, edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    C = P["combines"][0]
    pos = {r: i for i, r in enumerate(C["rows"])}
    at.session_state[f"replay_box_{key}"] = True
    at.session_state[replay_view.marks_key(key)] = {"token": P["edit"]["token"],
                                                    "remove": [[C["num"], pos[r]] for r in rows], "keep": [],
                                                    "changed": len(rows)}
    _run(at)


def test_app_step2_files_only_when_asked_and_a_work_opened_gets_nothing_new(field, tmp_path, monkeypatch):
    import replay_view  # noqa: F401
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click()
    _run(at)
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    out = os.path.join(wd, "without_cleaning")
    # nothing written by showing step 2: a button prepares the files
    assert not os.path.exists(out)
    labels = [b.label for b in at.get("download_button")]
    assert "Shapefile without cleaning (.zip)" not in labels
    bk = next(b.key for b in at.button if str(b.key).startswith("asis_make_"))
    at.button(key=bk).click()
    _run(at)
    z0 = os.path.join(out, f"{tag}_in_use.zip")
    assert os.path.isfile(z0) and os.path.isfile(z0[:-4] + "_DIFM.zip")
    labels = [b.label for b in at.get("download_button")]
    assert "Shapefile without cleaning (.zip)" in labels and "For DIFM, without cleaning (.zip)" in labels
    assert not any(str(b.key).startswith("asis_make_") for b in at.button)
    # the DIFM record without cleaning speaks of the data in use
    side = open(z0[:-4] + ".json", encoding="utf-8").read()
    assert "the clean file" not in side and "as cleaned" not in side and "3-sigma only" not in side
    assert "the data in use" in side
    # an edit here: one line says it (success), the files follow the edits by themselves
    key, shp = _imp_key(at)
    _send(at, key, shp, [10, 11, 12, 13])
    ed_lines = [m.value for m in list(at.success) + list(at.info) if m.value.startswith("Edits by hand: ")]
    assert len(ed_lines) == 1 and ed_lines[0].startswith("Edits by hand: 4 reading(s) removed (marked in Play the "
                                                         "harvest)")
    assert ed_lines[0].endswith("Every cleaning of this file removes them too (step SM).")
    z1 = os.path.join(out, f"{tag}_edited.zip")
    assert os.path.isfile(z1) and os.path.isfile(z1[:-4] + "_DIFM.zip") and not os.path.exists(z0)
    _run(at)                                                   # the next run: the line as information, still once
    assert len([m for m in list(at.success) + list(at.info) if m.value.startswith("Edits by hand: ")]) == 1
    at.button(key="work_save").click()
    _run(at)
    before = _files_under(wd)
    # opened again: the files are there for these edits, shown, nothing written
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    assert "Shapefile without cleaning (.zip)" in [b.label for b in at2.get("download_button")]
    after = _files_under(wd)
    assert {k: v for k, v in after.items() if k != "oced_work.json"} == \
        {k: v for k, v in before.items() if k != "oced_work.json"}
    # a work whose files were never prepared (an older one): opening it writes nothing, the button is offered
    shutil.rmtree(out)
    for e in (".shp", ".shx", ".dbf", ".prj", ".cpg", ".json"):
        p = os.path.join(wd, "edits", tag, f"{tag}_edited{e}")
        if os.path.exists(p):
            os.remove(p)
    before = _files_under(wd)
    at3 = _app(tmp_path / "ws", monkeypatch)
    at3.button(key="work_open").click()
    _run(at3)
    assert not os.path.exists(out)
    assert {k: v for k, v in _files_under(wd).items() if k != "oced_work.json"} == \
        {k: v for k, v in before.items() if k != "oced_work.json"}
    assert any(str(b.key).startswith("asis_make_") for b in at3.button)
    assert any("Edits by hand: 4 reading(s) removed" in m.value for m in at3.info)


def _deck_json(at) -> str:
    return " ".join(str(e.proto.json) for e in at.get("deck_gl_json_chart"))


def test_app_small_area_of_036_kept_drawn_copied_and_measured_again(field, tmp_path, monkeypatch):
    import replay_view
    from tests.test_replay_edits import _where
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click()
    _run(at)
    C = at.session_state["cleaned"][tag]
    # what 0.3.6 left: the polygon file in the cleaning's small_area_input/, the small area in the cleaning's record
    R = json.load(open(C["json"], encoding="utf-8"))
    sdir = os.path.join(R["files"].get("dir") or os.path.dirname(C["shp"]), "small_area_input")
    os.makedirs(sdir, exist_ok=True)
    p036 = os.path.join(sdir, "plots.geojson")
    shutil.copy(field["poly"], p036)
    er.small_area_after_clean(R, p036, "clip", log=lambda m: None)
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert tag not in (W.get("small_area") or {})
    # its polygon file gone (from small_area_input/ and from beside the work's input, where a file of that name
    # with the same polygons would be found again): said in the box
    os.rename(p036, p036 + ".away")
    os.rename(field["poly"], field["poly"] + ".away")
    try:
        at1 = _app(tmp_path / "ws", monkeypatch)
        at1.button(key="work_open").click()
        _run(at1)
    finally:
        os.rename(field["poly"] + ".away", field["poly"])
    assert tag not in at1.session_state["small_area"]
    assert any("measured by an earlier version of OCED" in m.value for m in at1.info)
    # its polygon file there: kept with the file, its map drawn, nothing written by opening
    os.rename(p036 + ".away", p036)
    before = _files_under(wd)
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click()
    _run(at2)
    A = at2.session_state["small_area"][tag]
    assert os.path.normcase(A["path"]) == os.path.normcase(p036) and A["rule"] == "clip"
    assert not any("measured by an earlier version of OCED" in m.value for m in at2.info)
    assert "Removed by the cleaning" in _deck_json(at2)                    # the small area's map
    assert {k: v for k, v in _files_under(wd).items() if k != "oced_work.json"} == \
        {k: v for k, v in before.items() if k != "oced_work.json"}
    S0 = at2.session_state["cleaned"][tag]["R"]["small_area"]
    # Edit points of the cleaning: 6 kept readings inside P1 removed -> reprocess: the file copied out of the
    # cleaning's folder first, the small area measured again, before and after the edits
    C0 = at2.session_state["cleaned"][tag]
    P = rp.replay_payload(C0["flagged_shp"], kind="clean", record=C0["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C0["flagged_shp"], read_geometry=False)
    M = sa.detail_of(C0["flagged_zip"], p036, "clip", margin_m=0)
    inside = set(np.asarray(M["readings"]["P1"]["idx"])[np.asarray(M["readings"]["P1"]["counted"])].tolist())
    rm = _where(P, F, lambda r: r.name in inside, 6)
    ck = next(k for k in at2.session_state.filtered_state
              if str(k).startswith("replay_box_clean_"))[len("replay_box_"):]
    at2.session_state[f"replay_box_{ck}"] = True
    at2.session_state[replay_view.marks_key(ck)] = {"token": P["edit"]["token"], "remove": rm, "keep": [],
                                                   "changed": 6}
    _run(at2)
    kept = os.path.join(wd, "small_area", tag, "plots.geojson")
    A = at2.session_state["small_area"][tag]
    assert os.path.normcase(A["path"]) == os.path.normcase(kept) and os.path.isfile(kept)
    S1 = at2.session_state["cleaned"][tag]["R"]["small_area"]
    assert S1["auto"] and S1["polygons"][0]["kept"]["readings"] == S0["polygons"][0]["kept"]["readings"] - 6
    assert S1["before"]["polygons"][0]["kept"] == S0["polygons"][0]["kept"]
    # the map: the 6 removed by hand in purple, their hover says so; the caption counts them
    dj = _deck_json(at2)
    assert "Removed by hand (Edit points)" in dj and "171,71,188" in dj.replace(" ", "")
    # 0.3.8: the hover is short; a click on the reading shows the whole of it under the map
    ks = next(k for k in at2.session_state.filtered_state if str(k).startswith("sa_sig_"))[len("sa_sig_"):]
    spec = next(json.loads(e.proto.json) for e in at2.get("deck_gl_json_chart") if '"sa-strips"' in e.proto.json)
    hand = next(s_ for L_ in spec["layers"] if L_.get("id") == "sa-strips" for s_ in L_["data"]
                if s_["tip"].startswith("Removed by hand (Edit points)"))
    at2.session_state[f"sa_pick_{ks}"] = {"sig": at2.session_state[f"sa_sig_{ks}"], "c": hand["c"]}
    _run(at2)
    assert any("Removed by hand (Edit points): its yield is not used" in m.value for m in at2.markdown)
    assert any("removed by hand (Edit points) in purple (6 here)" in c.value for c in at2.caption)
    tab = next(d.value for d in at2.dataframe if "removed (by step)" in d.value.columns)
    assert "by hand 6" in " ".join(str(v) for v in tab["removed (by step)"])
    # saved: kept with the file in the work
    at2.button(key="work_save").click()
    _run(at2)
    W = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert W["small_area"][tag] == {"path": f"small_area/{tag}/plots.geojson", "name": "plots.geojson", "rule": "clip"}
