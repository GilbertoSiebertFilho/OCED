# -*- coding: utf-8 -*-
"""0.3.7, Play the harvest and Edit points after the raw data (step 2), on synthetic data only: the replay of the
imported readings with an edits file (engine/replay.py, stage 'import'), the keys of the import file
(manual_edits.file_keys, the same as the cleaning's), merge_marks (one edits file for both replays), the cleaning with
readings removed in step 2 (step SM: S1 and S2 as the automatic cleaning, the monitor total unchanged), and the app's
flow: marks -> edits file -> the edited copy byte for byte -> the files without cleaning (the shapefile and the one
for DIFM) -> 'clean again' on a cleaned file -> a removal outside the boundary kept through a step-3 reprocess.

    python -m pytest -q tests/test_replay_import_edits.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile

import geopandas as gpd
import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import replay as rp  # noqa: E402
from engine.clean import manual_edits as me  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import BOUNDARY_X_M, make_field  # noqa: E402

N_SMALL = 2000
APP = os.path.join(ROOT, "app", "oced.py")


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("field"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:N_SMALL].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    return dict(F, shp=shp, df=F["df"].iloc[:N_SMALL].reset_index(drop=True))


def _settings(F, **kw):
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    S.update(kw)
    return S


def _edit_payload(shp, E):
    return rp.replay_payload(shp, kind="import", edits=E, edit=True, max_bytes=rp.EDIT_MAX_BYTES)


def _decode(C, k):
    return rp.decode_varint(C["data"][k], C["n_shown"]).astype(np.int64)


# ------------------------------------------------------------------------------------------------ the engine
def test_import_keys_are_the_cleaning_keys(field, tmp_path):
    """file_keys of the import = the keys the cleaning's flagged file gives the same readings."""
    R = yc.run(field["shp"], str(tmp_path / "out"), _settings(field), log=lambda m: None)
    k_imp = [str(k) for k in me.file_keys(field["shp"])[0]]
    k_fl = [str(k) for k in me.flagged_keys(R["files"]["flagged_shp"])[0]]
    assert len(set(k_imp)) == len(k_imp) == N_SMALL
    assert set(k_fl) <= set(k_imp) and len(k_fl) < len(k_imp)          # the flagged file: inside the boundary only


def test_the_payload_with_edits_counts_the_edited_data(field, tmp_path):
    keys = [str(k) for k in me.file_keys(field["shp"])[0]]
    E = me.write_edits(str(tmp_path / "e.json"), remove=keys[100:130])
    P0 = rp.replay_payload(field["shp"], kind="import")
    P = _edit_payload(field["shp"], E)
    assert "edit" not in P0 and "manual" not in P0
    assert P["edit"]["ok"] and P["edit"]["stage"] == "import" and P["edit"]["min_kept"] == 1
    assert P["manual"]["stage"] == "import" and P["manual"]["removed_by_hand"] == 30
    assert P["totals"]["removed"] == 30 and P["totals"]["kept"] == P0["totals"]["n"] - 30
    assert P["totals"]["area_ac"] < P0["totals"]["area_ac"] and P["totals"]["bu"] < P0["totals"]["bu"]
    st = np.concatenate([_decode(C, "e") for C in P["combines"]])
    f = np.concatenate([_decode(C, "f") for C in P["combines"]])
    assert int(((st & 3) == 1).sum()) == 30 and int(((f >> 1) & 1).sum()) == 30
    assert [s["code"] for s in P["steps"]] == ["SM"] and P["steps"][0]["n"] == 30
    rows = np.concatenate([np.asarray(C["rows"]) for C in P["combines"]])
    rm_rows = set(rows[(st & 3) == 1].tolist())
    assert rm_rows == set(range(100, 130))
    # the token: the import and its edits; another edits file, another token
    E2 = me.write_edits(str(tmp_path / "e2.json"), remove=keys[100:131])
    assert _edit_payload(field["shp"], E2)["edit"]["token"] != P["edit"]["token"]
    assert _edit_payload(field["shp"], {})["edit"]["token"] not in (P["edit"]["token"],)
    # a thinned replay cannot be edited
    Pt = rp.replay_payload(field["shp"], kind="import", edits=E, edit=True, max_bytes=20_000)
    assert Pt["thin"] > 1 and not Pt["edit"]["ok"] and "too many readings" in Pt["edit"]["why"]
    # the zone statistics count the edited data, raw readings (not cleaned)
    zp = str(tmp_path / "z.geojson")
    from tests.synthetic import _rect
    gpd.GeoDataFrame({"zone": [1, 2]}, geometry=[_rect(-10, 250, -20, 250), _rect(250, 520, -20, 250)],
                     crs="EPSG:4326").to_file(zp, driver="GeoJSON")
    Pz0 = rp.replay_payload(field["shp"], kind="import", zones=zp, zone_column="zone")
    Pz = rp.replay_payload(field["shp"], kind="import", zones=zp, zone_column="zone", edits=E)
    n0 = sum(z["n"] for z in Pz0["zones"]["stats"]["all"]["zones"])
    n1 = sum(z["n"] for z in Pz["zones"]["stats"]["all"]["zones"])
    assert n0 - n1 == 30 and Pz["zones"]["raw"] is True


def test_import_marks_become_keys(field, tmp_path):
    keys = [str(k) for k in me.file_keys(field["shp"])[0]]
    E = me.write_edits(str(tmp_path / "e.json"), remove=keys[10:15])
    P = _edit_payload(field["shp"], E)
    C = P["combines"][0]
    pos = {r: i for i, r in enumerate(C["rows"])}
    # the marks the player sends: the edits shown (rows 10-14) but row 12 put back, two more rows removed, a keep
    # mark and a reading not of this replay
    rm = [[C["num"], pos[r]] for r in (10, 11, 13, 14, 40, 41)] + [[C["num"], 10 ** 6]]
    K = rp.edit_keys(P, {"token": P["edit"]["token"], "remove": rm, "keep": [[C["num"], pos[50]]]}, field["shp"])
    assert K["stage"] == "import" and K["remove"] == sorted(keys[r] for r in (10, 11, 13, 14, 40, 41))
    assert K["keep"] == [] and {x["mark"] for x in K["refused"]} == {"keep", "remove"}
    assert K["kept_after"] == N_SMALL - 6 and len(K["seen"]) == N_SMALL
    with pytest.raises(ValueError, match="another version"):
        rp.edit_keys(P, {"token": "0" * 32, "remove": rm}, field["shp"])
    with pytest.raises(ValueError, match="stage"):
        rp.edit_keys(P, {"token": P["edit"]["token"], "remove": rm}, field["shp"], stage="clean")
    M = me.merge_marks(E, K, K["seen"], "import")
    assert M["remove"] == K["remove"] and M["keep"] == []


def test_keys_by_position_and_shared_keys(field, tmp_path):
    """A file with neither a record id nor a time: the key is the position (as the cleaning's); readings that share
    a key (the same position) are named once and edited together."""
    g = gpd.read_file(field["shp"]).drop(columns=["Obj__Id", "Time"]).iloc[:400].copy()
    import pandas as pd
    g = gpd.GeoDataFrame(pd.concat([g, g.iloc[[5]]], ignore_index=True), geometry="geometry", crs=g.crs)
    shp = str(tmp_path / "nopos.shp")
    g.to_file(shp, engine="pyogrio")
    keys, info = me.file_keys(shp)
    assert info["position"] and info["n_shared"] == 2
    k0 = me.reading_keys(gpd.read_file(shp).drop(columns="geometry"), me.key_columns(g.columns),
                         me._lonlat_of(gpd.read_file(shp)))[0]
    assert list(map(str, keys)) == list(map(str, k0))
    P = _edit_payload(shp, {})
    assert P["edit"]["ok"] and P["edit"].get("shared")


def test_merge_marks_keeps_what_a_replay_does_not_show():
    E = {"remove": ["a", "b", "x"], "keep": ["k", "y"]}
    seen = ["a", "b", "k", "c"]
    # step 2: b put back, c removed; x (not shown) stays; k removed in step 2 leaves 'keep'; y (not shown) stays
    M = me.merge_marks(E, {"remove": ["a", "c", "k"], "keep": []}, seen, "import")
    assert M == {"remove": ["a", "c", "k", "x"], "keep": ["y"]}
    # step 3: shows a, k; the marks keep k and remove a; x and y (not shown) stay
    M3 = me.merge_marks(E, {"remove": ["a"], "keep": ["k"]}, ["a", "b", "k"], "clean")
    assert M3 == {"remove": ["a", "x"], "keep": ["k", "y"]}
    assert not set(M["remove"]) & set(M["keep"]) and not set(M3["remove"]) & set(M3["keep"])
    with pytest.raises(ValueError):
        me.merge_marks(E, {"remove": [], "keep": ["a"]}, seen, "import")
    assert me.merge_marks(None, {"remove": [], "keep": []}, [], "import") == {"remove": [], "keep": []}


def test_a_cleaning_with_step2_removals(field, tmp_path):
    """The readings removed in step 2 (keys of the import) leave in step SM: S1 and S2 as the automatic cleaning
    (every width and distance of the flagged file the same), the monitor total the grower's weight is compared with
    unchanged, the record counts them."""
    keys = [str(k) for k in me.file_keys(field["shp"])[0]]
    x = field["df"]["x"].to_numpy()
    inside = np.flatnonzero(x < BOUNDARY_X_M - 30)
    pick = [keys[i] for i in inside[200:240]]
    ep = me.write_edits(str(tmp_path / "e.json"), remove=pick)
    T = {"value": 80000.0, "unit": "lb", "basis": "wet", "use": "validate"}
    A = yc.run(field["shp"], str(tmp_path / "a"), _settings(field, scale_ticket=T), log=lambda m: None)
    B = yc.run(field["shp"], str(tmp_path / "b"), _settings(field, scale_ticket=T, manual_edits=ep["file"]),
               log=lambda m: None)
    fa = pyogrio.read_dataframe(A["files"]["flagged_shp"], read_geometry=False)
    fb = pyogrio.read_dataframe(B["files"]["flagged_shp"], read_geometry=False)
    assert (fb["Rem_By"] == "SM").sum() == 40 and (fb["Man_Edit"] == "R").sum() == 40
    for c in ("Wdth_Opt", "Dist_Opt", "Swath_Scl"):
        assert np.array_equal(fa[c].to_numpy(float), fb[c].to_numpy(float), equal_nan=True), c
    s12 = fa["Rem_By"].fillna("").astype(str).str[:2].isin(["S0", "S1", "S2"])
    assert np.array_equal(s12.to_numpy(), fb["Rem_By"].fillna("").astype(str).str[:2].isin(
        ["S0", "S1", "S2"]).to_numpy())
    assert A["level"]["export_total_bu"] == pytest.approx(B["level"]["export_total_bu"], rel=0, abs=1e-9)
    assert B["manual_edits"]["remove"]["readings_applied"] == 40 and B["n_kept"] < A["n_kept"]


def test_the_player_knows_the_import_stage():
    h = open(rp.PLAYER, encoding="utf-8").read()
    assert 'ED.stage === "import"' in h and "Apply these edits" in h and "Applying in the app" in h
    assert "put it back" in h and "Kept / removed by hand" in h and 'id="b-sa"' in h


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


def _md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def _imp_key(at):
    D = at.session_state["datasets"][at.session_state["active"]]
    return "imp_" + hashlib.md5(str(D["shp"]).encode("utf-8")).hexdigest()[:8], D["shp"]


def _send(at, key, shp, rows, E=None):
    """The marks the step-2 player would send: every reading of `rows` (file rows of the import) removed."""
    import replay_view
    P = _edit_payload(shp, E if E is not None else {})
    C = P["combines"][0]
    pos = {r: i for i, r in enumerate(C["rows"])}
    at.session_state[f"replay_box_{key}"] = True
    at.session_state[replay_view.marks_key(key)] = {"token": P["edit"]["token"], "remove": [[C["num"], pos[r]]
                                                                                           for r in rows],
                                                    "keep": [], "changed": len(rows)}
    _run(at)


def test_app_step2_edits_files_without_cleaning_and_a_cleaning(field, tmp_path, monkeypatch):
    import replay_view  # noqa: F401
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click()
    _run(at)
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    key, shp = _imp_key(at)
    # no edits: nothing written until asked; then the files without cleaning are the import in use as it is
    z0 = os.path.join(wd, "without_cleaning", f"{tag}_in_use.zip")
    assert not os.path.exists(os.path.dirname(z0))
    at.button(key=next(b.key for b in at.button if str(b.key).startswith("asis_make_"))).click()
    _run(at)
    assert os.path.isfile(z0) and os.path.isfile(z0[:-4] + "_DIFM.zip")
    labels = [b.label for b in at.get("download_button")]
    assert "Shapefile without cleaning (.zip)" in labels and "For DIFM, without cleaning (.zip)" in labels
    assert "Shapefile for DIFM (.zip)" not in labels                     # (step 4's label: only for a clean file)
    # the replay of the imported readings: the two-way player, stage import
    at.session_state[f"replay_box_{key}"] = True
    _run(at)
    html = next(json.loads(e.proto.json)["html"] for e in at.get("bidi_component")
                if "oced_replay_player" in str(getattr(e.proto, "component_name", "")))
    Pp = json.loads(re.search(r'type="application/json">(.*?)</script>', html, re.S).group(1))
    assert Pp["kind"] == "import" and Pp["edit"]["stage"] == "import" and '"edit": true' in html
    # 25 readings removed (5 of them outside the boundary: x beyond it)
    x = field["df"]["x"].to_numpy()
    out_rows = [int(i) for i in np.flatnonzero(x > BOUNDARY_X_M + 5)[:5]]
    in_rows = [int(i) for i in np.flatnonzero(x < BOUNDARY_X_M - 30)[300:320]]
    rows = in_rows + out_rows
    _send(at, key, shp, rows)
    ep = os.path.join(wd, "edits", tag, f"{tag}_manual_edits.json")
    E = me.read_edits(ep)
    keys = [str(k) for k in me.file_keys(shp)[0]]
    assert E["remove"] == sorted(keys[r] for r in rows) and E["keep"] == [] and "step 2" in E["note"]
    assert any(s.value.startswith("Edits by hand: 25 reading(s) removed (marked in Play the harvest)")
               for s in at.success)
    assert not any(i.value.startswith("Edits by hand: ") for i in at.info)  # said once after Apply
    # the edited copy: byte for byte the import's records without the 25
    side = json.load(open(os.path.join(wd, "edits", tag, f"{tag}_edited.json"), encoding="utf-8"))
    assert side["n_removed"] == 25 and side["way"].startswith("byte")
    ed_shp = os.path.join(wd, "edits", tag, f"{tag}_edited.shp")
    a, b = yc._read_dbf(os.path.splitext(shp)[0] + ".dbf"), yc._read_dbf(os.path.splitext(ed_shp)[0] + ".dbf")
    keep_rows = [i for i in range(len(keys)) if i not in set(rows)]
    assert b["n"] == len(keep_rows) and np.array_equal(b["recs"], a["recs"][keep_rows])
    sa, sb = yc._read_shp(shp), yc._read_shp(ed_shp)
    assert [sb["contents"][i] for i in range(len(keep_rows))] == [sa["contents"][i] for i in keep_rows]
    m0 = os.path.getmtime(ed_shp)
    _run(at)                                                                 # not made again: the sidecar matches
    assert os.path.getmtime(ed_shp) == m0
    # the files without cleaning: the edited copy zipped, the DIFM file with n - 25 readings
    z1 = os.path.join(wd, "without_cleaning", f"{tag}_edited.zip")
    with zipfile.ZipFile(z1) as zf:
        assert sorted(n[-4:] for n in zf.namelist())[:3] == [".cpg", ".dbf", ".prj"]
    dz = z1[:-4] + "_DIFM.zip"
    gd = gpd.read_file("zip://" + dz.replace("\\", "/"))
    assert len(gd) == len(keep_rows)
    assert {"Yld_Vol_Dr", "Swth_Wdth_", "Moisture__", "Distance_f"} <= set(gd.columns)
    assert any(i.value.startswith("Edits by hand: 25 reading(s) removed (marked in Play the harvest)")
               for i in at.info)
    # a cleaning: the 20 inside the boundary leave in SM; the 5 outside are set aside by the clip, reported
    at.text_input(key=next(k for k in at.session_state.filtered_state if str(k).startswith("bnd_path_"))).input(
        field["boundary"])
    at.button(key=next(b.key for b in at.button if str(b.key).startswith("bnd_use_"))).click()
    _run(at)
    at.button(key="clean_one").click()
    _run(at)
    C = at.session_state["cleaned"][tag]
    X = C["R"]["manual_edits"]["remove"]
    assert X["readings_applied"] == 20 and X["not_applied"] == 5
    # step 2 again: two more removed; the cleaned file is to clean again (nothing is cleaned by step 2)
    E1 = me.read_edits(ep)
    rows2 = rows + in_rows_extra(x)
    _send(at, key, shp, rows2, E1)
    assert len(me.read_edits(ep)["remove"]) == 27
    assert any("changed since this file was cleaned" in w.value for w in at.warning)
    assert at.session_state["cleaned"][tag]["at"] == C["at"]
    # a step-3 reprocess with the replay's marks: the 5 removals outside the boundary (not in its replay) stay
    from tests.test_replay_edits import _where
    ck = next(k for k in at.session_state.filtered_state if str(k).startswith("replay_box_clean_"))[len("replay_box_"):]
    at.button(key="clean_one").click()
    _run(at)
    C2 = at.session_state["cleaned"][tag]
    P3 = rp.replay_payload(C2["flagged_shp"], kind="clean", record=C2["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F3 = pyogrio.read_dataframe(C2["flagged_shp"], read_geometry=False)
    F3["Rem_By"] = F3["Rem_By"].fillna("").astype(str)
    base = _where(P3, F3, lambda r: r["Rem_By"] == "SM", 10 ** 6)
    more = _where(P3, F3, lambda r: r["Rem_By"] == "", 3)
    import replay_view
    at.session_state[f"replay_box_{ck}"] = True
    at.session_state[replay_view.marks_key(ck)] = {"token": P3["edit"]["token"], "remove": base + more, "keep": [],
                                                  "changed": 3}
    _run(at)
    E3 = me.read_edits(ep)
    assert len(E3["remove"]) == 30 and set(keys[r] for r in out_rows) <= set(E3["remove"])
    assert "step 3" in E3["note"]


def in_rows_extra(x):
    return [int(i) for i in np.flatnonzero(x < BOUNDARY_X_M - 30)[400:402]]


def test_app_edited_copy_by_gdal_when_the_bytes_cannot_be_copied(field, tmp_path, monkeypatch):
    """The import's bytes cannot be copied (byte_copy_source says why): the edited copy is written through GDAL,
    the same readings without the ones removed by hand; the sidecar says which way."""
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click()
    _run(at)
    monkeypatch.setattr(yc, "byte_copy_source", lambda src, g0: (None, "a test: no byte copy"))
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    key, shp = _imp_key(at)
    _send(at, key, shp, [3, 4, 5])
    side = json.load(open(os.path.join(wd, "edits", tag, f"{tag}_edited.json"), encoding="utf-8"))
    assert side["way"].startswith("geopandas") and "a test" in side["way"] and side["n"] == N_SMALL - 3
    g = gpd.read_file(os.path.join(wd, "edits", tag, f"{tag}_edited.shp"))
    g0 = gpd.read_file(shp)
    assert len(g) == N_SMALL - 3
    assert np.allclose(g["Yld_Vol_Dr"].to_numpy(), np.delete(g0["Yld_Vol_Dr"].to_numpy(), [3, 4, 5]))
    # 'Remove all edits' of step 2: the readings as imported again
    at.button(key="imp_edits_remove").click()
    _run(at)
    assert not os.path.exists(os.path.join(wd, "edits", tag, f"{tag}_manual_edits.json"))
    assert os.path.isfile(os.path.join(wd, "without_cleaning", f"{tag}_in_use.zip"))
