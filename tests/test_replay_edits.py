# -*- coding: utf-8 -*-
"""Readings removed or kept by hand from the harvest replay of a cleaning (engine/replay.py edit_part / edit_keys,
app/replay_view.py two-way player, app/oced.py apply_marks), on synthetic data only: the payload's edit fields and the
card's values, the marks turned into the engine's reading keys, readings cut by the import range, the clip or the
swath step refused, no edit mode on the replay of the imported readings, and the app's flow with the component's value
simulated: marks -> edits file -> cleaning again -> 'Remove all edits' gives the automatic files byte for byte.

    python -m pytest -q tests/test_replay_edits.py
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import replay as rp  # noqa: E402
from engine.clean import manual_edits as me  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.synthetic_replay import make_two_at_once  # noqa: E402

N_SMALL = 2000
APP = os.path.join(ROOT, "app", "oced.py")


def _md5(path):
    with open(path, "rb") as f:
        b = bytearray(f.read())
    if path.lower().endswith(".dbf"):
        b[1:4] = b"\0\0\0"                                  # the date of the last update (UTC day of the run)
    return hashlib.md5(bytes(b)).hexdigest()


def _settings(F, **kw):
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    S.update(kw)
    return S


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    import geopandas as gpd
    d = str(tmp_path_factory.mktemp("field"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:N_SMALL].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    return dict(F, shp=shp)


@pytest.fixture(scope="module")
def auto(field, tmp_path_factory):
    R = yc.run(field["shp"], str(tmp_path_factory.mktemp("auto")), _settings(field), log=lambda m: None)
    fl = R["files"]["flagged_shp"]
    P = rp.replay_payload(fl, kind="clean", record=R, edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(fl, read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    F["key"] = me.flagged_keys(F)[0]
    return {"R": R, "P": P, "F": F, "flagged": fl}


def _where(P, F, pred, n):
    """n (combine num, index) of the payload whose file row satisfies pred(row of F)."""
    out = []
    for C in P["combines"]:
        for i, r in enumerate(C["rows"]):
            if pred(F.iloc[r]):
                out.append([C["num"], i])
                if len(out) == n:
                    return out
    return out


def _decode(P, C, k):
    return rp.decode_varint(C["data"][k], C["n_shown"]).astype(float)


def test_the_payload_of_a_cleaning_carries_the_card_and_the_edit_fields(auto):
    P, R = auto["P"], auto["R"]
    E = P["edit"]
    assert E["ok"] and E["why"] == "" and re.fullmatch(r"[0-9a-f]{32}", E["token"]) and E["n"] == P["n"]
    assert P["thin"] == 1 and all(len(C["rows"]) == C["n"] for C in P["combines"])
    # every reading of the file is in the payload exactly once
    rows = sorted(r for C in P["combines"] for r in C["rows"])
    assert rows == list(range(P["n_file"])) and P["n_file"] == len(auto["F"])
    # the limits of the card: the record's, per combine
    steps = [s for s in R["sms3sigma"]["steps"] if s.get("lo") is not None]
    for C in P["combines"]:
        L = P["limits"][C["id"]]
        for s in steps:
            if s["group"] == C["id"]:
                assert L[s["step"]][:2] == [s["lo"], s["hi"]]
        assert {"S3", "S4"} <= set(L) and any(k.startswith("S5") for k in L)
    # the values the filters compared, where they differ from the logged ones; no edit marks without edits
    assert set(P.get("card_cols") or []) <= {"yf", "sf", "wl"}
    assert all("e" not in C["data"] for C in P["combines"]) and "manual" not in P
    assert P["step_names"]["S5a"].startswith("S5a")
    # the HTML: the file rows never reach the page; the switch only in the app's player
    h0, h1 = rp.replay_html(P), rp.replay_html(P, embedded=True, edit=True)
    assert '"rows"' not in h0 and '"rows"' not in h1 and all("rows" in C for C in P["combines"])
    assert '"edit": false' in h0 and '"edit": true' in h1
    assert 'id="b-edit"' in h1 and 'id="epanel"' in h1 and 'id="rp-card"' in h1


def test_the_card_values_are_the_ones_the_filters_compared(auto):
    """yf = the dry yield x Swath_Scl (S5), sf = the speed after the swath step (S4): the payload's quantised values
    are within half a step of the file's."""
    P, F = auto["P"], auto["F"]
    for C in P["combines"]:
        r = np.asarray(C["rows"])
        if "yf" in C["data"]:
            yf = _decode(P, C, "yf") * P["y_q"]
            want = F["Yld_Vol_Dr"].to_numpy(float)[r] * F["Swath_Scl"].to_numpy(float)[r]
            assert np.nanmax(np.abs(yf - want)) <= P["y_q"] / 2 + 1e-9
        if "sf" in C["data"]:
            sf = _decode(P, C, "sf") * 0.01
            d0, d1 = F["Distance_f"].to_numpy(float)[r], F["Dist_Opt"].to_numpy(float)[r]
            want = np.where(d0 > 0, F["Speed_mph_"].to_numpy(float)[r] * d1 / d0, F["Speed_mph_"].to_numpy(float)[r])
            assert np.nanmax(np.abs(sf - want)) <= 0.005 + 1e-9


def test_marks_become_the_keys_of_the_flagged_file(auto):
    P, F = auto["P"], auto["F"]
    rm = _where(P, F, lambda r: r["Rem_By"] == "", 7)
    kp = _where(P, F, lambda r: r["Rem_By"][:2] in ("S3", "S4", "S5"), 5)
    K = rp.edit_keys(P, {"token": P["edit"]["token"], "remove": rm, "keep": kp}, auto["flagged"])
    by = {C["num"]: C for C in P["combines"]}
    want_rm = sorted(F["key"].iloc[by[n]["rows"][i]] for n, i in rm)
    want_kp = sorted(F["key"].iloc[by[n]["rows"][i]] for n, i in kp)
    assert K["remove"] == want_rm and K["keep"] == want_kp and not K["refused"]
    assert K["n_remove"] == 7 and K["n_keep"] == 5 and K["key_info"]["n_shared"] == 0
    # a DataFrame of the flagged file gives the same keys as its path
    assert rp.edit_keys(P, {"token": P["edit"]["token"], "remove": rm, "keep": kp}, F.drop(columns="key")) == K


def test_marks_on_readings_cut_by_the_import_range_the_clip_or_the_swath_step_are_refused(auto):
    P, F = auto["P"], auto["F"].drop(columns="key").copy()
    # S0 is in the synthetic cleaning; S1 and S2 are given to two kept readings of this copy of the flagged table
    s0 = _where(P, F, lambda r: r["Rem_By"] == "S0", 1)
    k2 = _where(P, F, lambda r: r["Rem_By"] == "", 4)
    by = {C["num"]: C for C in P["combines"]}
    F.loc[by[k2[0][0]]["rows"][k2[0][1]], "Rem_By"] = "S1"
    F.loc[by[k2[1][0]]["rows"][k2[1][1]], "Rem_By"] = "S2"
    marks = {"token": P["edit"]["token"], "keep": s0 + [k2[0], k2[1], k2[2]], "remove": [k2[3], [99, 0], [1, 10 ** 7]]}
    K = rp.edit_keys(P, marks, F)
    why = [x["reason"] for x in K["refused"]]
    assert len(K["refused"]) == 6 and K["keep"] == [] and len(K["remove"]) == 1
    assert sum("import range (S0)" in w for w in why) == 1 and sum("clip to the boundary (S1)" in w for w in why) == 1
    assert sum("swath step (S2" in w for w in why) == 1 and sum("kept already" in w for w in why) == 1
    assert sum(w == "not a reading of this replay" for w in why) == 2
    # removed by hand cannot also be kept by hand; a token of another version applies nothing
    F2 = F.assign(Man_Edit="")                       # a reading kept by hand: removable and keepable
    F2.loc[by[k2[3][0]]["rows"][k2[3][1]], "Man_Edit"] = "K"
    with pytest.raises(ValueError, match="both remove and keep"):
        rp.edit_keys(P, {"token": P["edit"]["token"], "remove": [k2[3]], "keep": [k2[3]]}, F2)
    with pytest.raises(ValueError, match="another version"):
        rp.edit_keys(P, {"token": "0" * 32, "remove": [k2[3]]}, F)


def test_a_thinned_replay_has_no_edit_mode(auto):
    P = rp.replay_payload(auto["flagged"], kind="clean", record=auto["R"], edit=True, max_bytes=3000)
    assert P["thin"] > 1 and not P["edit"]["ok"] and "never marked" in P["edit"]["why"]
    with pytest.raises(ValueError, match="cannot be edited"):
        rp.edit_keys(P, {"token": P["edit"]["token"], "remove": [[1, 0]]}, auto["flagged"])
    h = rp.replay_html(P, embedded=True, edit=True)
    assert '"edit": true' in h and '"ok":false' in h           # the switch is shown off, with its reason


def test_the_replay_of_the_imported_readings_has_no_edit_mode(field):
    P = rp.replay_payload(field["shp"], kind="import", edit=True)
    assert "edit" not in P and "limits" not in P and "manual" not in P
    assert '"edit": false' in rp.replay_html(P, embedded=True, edit=True)


def test_the_payload_of_an_edited_cleaning_carries_the_marks_and_the_record(field, auto, tmp_path):
    F = auto["F"]
    rm = F.loc[F["Rem_By"] == "", "key"].tolist()[50:62]
    kp = F.loc[F["Rem_By"].str.startswith("S5"), "key"].tolist()[:4]
    path = str(tmp_path / "edits.json")
    me.write_edits(path, remove=rm, keep=kp, note="synthetic")
    R = yc.run(field["shp"], str(tmp_path / "out"), _settings(field, manual_edits=path), log=lambda m: None)
    P = rp.replay_payload(R["files"]["flagged_shp"], kind="clean", record=R, edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    st = np.concatenate([_decode(P, C, "e").astype(int) for C in P["combines"]])
    assert int(np.sum((st & 3) == 1)) == 12 and int(np.sum((st & 3) == 2)) == 4
    M = P["manual"]
    assert M["removed_by_hand"] == 12 and M["kept_by_hand"] == 4 and M["summary"] == me.summary_text(R)
    assert M["edited"]["ALL"]["points"] == R["manual_edits"]["edited"]["combines"]["ALL"]["points"]
    assert M["automatic"]["ALL"]["points"] == auto["R"]["n_kept"]
    assert "SM" in P["auto_codes"] and P["step_names"]["SM"].startswith("SM")
    # the moved bit: readings in neither list whose fate differs from the automatic cleaning
    assert int(np.sum((st & 4) > 0)) == M["moved"] == R["manual_edits"]["other_readings"]["total"]
    # the standalone file shows them read-only
    h = rp.replay_html(P)
    assert '"edit": false' in h and '"removed_by_hand":12' in h


# ------------------------------------------------------------------------------------------------ the app
def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _players(at):
    """(kind, html, component) of every player on the page."""
    out = []
    for e in list(at.get("iframe")) + list(at.get("i_frame")):
        out.append(("iframe", getattr(e.proto, "srcdoc", "") or "", e))
    for e in at.get("bidi_component"):
        if "oced_replay_player" in str(getattr(e.proto, "component_name", "")):
            out.append(("two-way", json.loads(e.proto.json)["html"], e))
    return out


def _payload(html):
    return json.loads(re.search(r'type="application/json">(.*?)</script>', html, re.S).group(1))


def _open(at, keys):
    for k in keys:
        at.session_state[k] = True
    at.run()
    assert not at.exception, at.exception


def test_app_marks_reprocess_and_remove_all_edits(tmp_path, monkeypatch):
    """Step 3: the replay of the cleaning is the two-way player with 'Edit points', the replay of the readings is not.
    The player's marks (simulated as the component sends them) become the edits file of the work, the file is cleaned
    again with it (record, flagged file and steps 3 and 4 say so); a mark on a reading not of the replay is refused;
    'Remove all edits' cleans again without them: the clean and flagged files byte for byte the automatic ones."""
    import replay_view
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    tag = at.session_state["active"]
    wd = at.session_state["workdir"]
    C0 = at.session_state["cleaned"][tag]
    fl0 = C0["flagged_shp"]
    auto_md5 = {p: _md5(p) for p in sorted(glob.glob(os.path.splitext(fl0)[0] + ".*"))
                + sorted(glob.glob(os.path.splitext(C0["shp"])[0] + ".*")) if p.endswith((".shp", ".dbf", ".shx"))}
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]
    _open(at, keys)
    pl = _players(at)
    kinds = sorted((k, _payload(h)["kind"]) for k, h, _ in pl)
    # 0.3.7: the imported readings have Edit points too (stage 'import': removed or put back, nothing cleaned)
    assert kinds == [("two-way", "clean"), ("two-way", "import")]
    assert _payload(next(h for k, h, _ in pl if _payload(h)["kind"] == "import"))["edit"]["stage"] == "import"
    html = next(h for k, h, _ in pl if k == "two-way" and _payload(h)["kind"] == "clean")
    assert '"edit": true' in html and not os.path.exists(os.path.join(wd, "edits"))
    assert {p: _md5(p) for p in auto_md5} == auto_md5                         # opening it changes nothing
    # the marks the player would send: 5 kept readings removed, 3 the moisture / speed filters removed kept, and one
    # reading that is not of this replay
    P = rp.replay_payload(fl0, kind="clean", record=C0["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    Pp = _payload(html)
    assert Pp["edit"]["token"] == P["edit"]["token"]
    F = pyogrio.read_dataframe(fl0, read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    rm = _where(P, F, lambda r: r["Rem_By"] == "", 5)
    kp = _where(P, F, lambda r: r["Rem_By"][:2] in ("S3", "S4"), 3)
    ckey = next(k for k in keys if k.startswith("replay_box_clean_"))[len("replay_box_"):]
    at.session_state[replay_view.marks_key(ckey)] = {"token": P["edit"]["token"], "remove": rm,
                                                     "keep": kp + [[1, 10 ** 6]], "changed": 9}
    _open(at, keys)
    assert not at.error, [e.value for e in at.error]
    ep = os.path.join(wd, "edits", tag, f"{tag}_manual_edits.json")
    E = me.read_edits(ep)
    K = me.flagged_keys(F)[0]
    by = {C["num"]: C for C in P["combines"]}
    assert E["remove"] == sorted(K[by[n]["rows"][i]] for n, i in rm)
    assert E["keep"] == sorted(K[by[n]["rows"][i]] for n, i in kp)
    C1 = at.session_state["cleaned"][tag]
    X = C1["R"]["manual_edits"]
    assert X["remove"]["readings_applied"] == 5 and X["keep"]["readings_applied"] == 3
    assert C1["R"]["n_kept"] == C0["R"]["n_kept"] - 5 + 3 + X["other_readings"]["came_back"] \
        - X["other_readings"]["newly_cut"]
    G = pyogrio.read_dataframe(C1["flagged_shp"], read_geometry=False)
    assert (G["Man_Edit"] == "R").sum() == 5 and (G["Man_Edit"] == "K").sum() == 3
    assert any("1 mark(s) not applied" in s.value for s in at.success)
    assert any(w.value.startswith("THIS CLEANING INCLUDES MANUAL EDITS") for w in at.warning)
    assert any("includes edits by hand" in str(c.value) for c in at.caption)
    assert any(str(i.value).startswith("Edits by hand for this file: 5 reading(s) removed and 3 kept") for i in at.info)
    # the replay comes back with the edited cleaning: its marks, the record's totals beside the automatic ones (the
    # sections opened again: AppTest keeps no expander state across the st.rerun() of the reprocess)
    _open(at, keys)
    P1 = _payload(next(h for k, h, _ in _players(at) if k == "two-way" and _payload(h)["kind"] == "clean"))
    assert P1["manual"]["removed_by_hand"] == 5 and P1["manual"]["kept_by_hand"] == 3
    assert P1["manual"]["automatic"]["ALL"]["points"] == C0["R"]["n_kept"]
    assert P1["edit"]["token"] != P["edit"]["token"]
    # the settings changed warning does not fire: the cleaning ran with the edits file it now has
    assert not any("changed since this file was cleaned" in w.value for w in at.warning)
    # 'Remove all edits': the automatic cleaning again, the same bytes as before any edit
    at.button(key="edits_remove").click()
    _open(at, keys)
    assert not at.error, [e.value for e in at.error]
    C2 = at.session_state["cleaned"][tag]
    assert "manual_edits" not in C2["R"] and not os.path.exists(ep) and os.path.exists(ep[:-5] + "_removed.json")
    assert {p: _md5(p) for p in auto_md5} == auto_md5
    assert not any("MANUAL EDITS" in w.value for w in at.warning)
    assert "edits_remove" not in [b.key for b in at.button]


def test_app_marks_of_an_older_version_of_the_cleaning_apply_nothing(tmp_path, monkeypatch):
    import replay_view
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    at.button(key="clean_one").click().run()
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]
    _open(at, keys)
    ckey = next(k for k in keys if k.startswith("replay_box_clean_"))[len("replay_box_"):]
    at.session_state[replay_view.marks_key(ckey)] = {"token": "f" * 32, "remove": [[1, 3]], "keep": []}
    _open(at, keys)
    assert any("another version of this cleaning" in e.value for e in at.error)
    assert not os.path.exists(os.path.join(at.session_state["workdir"], "edits"))


# ------------------------------------------------------------------------------------------------ marks that stop it
def _version(at):
    """The version the two-way player was mounted with (its html's hash and the tries of the marks)."""
    for e in at.get("bidi_component"):          # the replay of the cleaning (0.3.7: step 2's is two-way too)
        if "oced_replay_player" in str(getattr(e.proto, "component_name", "")):
            d = json.loads(e.proto.json)
            if _payload(d["html"])["kind"] == "clean":
                return d["v"]
    return None


def test_the_marks_say_how_many_readings_they_leave(auto):
    """edit_keys counts the readings the marks leave kept (before the limits move) and gives the minimum of a clean
    file; the payload gives the player the same minimum and the kept readings it does not hold; the player's page has
    the count and the warning below the minimum."""
    P, F = auto["P"], auto["F"]
    E = P["edit"]
    assert E["min_kept"] == yc.MIN_KEPT == 30 and E["kept_outside"] == 0
    kept = F["Keep"].astype(int) == 1
    allk = _where(P, F, lambda r: r["Rem_By"] == "", 10 ** 6)
    assert len(allk) == int(kept.sum())
    K = rp.edit_keys(P, {"token": E["token"], "remove": allk[1:], "keep": []}, auto["flagged"])
    rows_rm = F["key"].isin(K["remove"])
    assert K["min_kept"] == 30 and K["kept_after"] == int((kept & ~rows_rm).sum())
    if F["key"].is_unique:
        assert K["kept_after"] == 1
    kp = _where(P, F, lambda r: r["Rem_By"][:2] in ("S3", "S4", "S5"), 3)
    K2 = rp.edit_keys(P, {"token": E["token"], "remove": allk[:5], "keep": kp}, auto["flagged"])
    rows_rm2, rows_kp2 = F["key"].isin(K2["remove"]), F["key"].isin(K2["keep"])
    assert K2["kept_after"] == int(((kept & ~rows_rm2) | rows_kp2).sum())
    h = rp.replay_html(P)
    assert "function keptAfter()" in h and 'id="e-low"' in h and '"min_kept":30' in h.replace(" ", "")


def test_app_marks_that_stop_the_cleaning_leave_the_edits_as_they_were(tmp_path, monkeypatch):
    """Marks that leave fewer readings than a clean file needs: the cleaning stops, the edits file is put back as it
    was before them (none at first; then 5 removed by hand, byte for byte), the files of the cleaning shown do not
    change, the page says why (and shows no 'Edits by hand: ...' success), and the player is loaded again (its version
    moves although the flagged file is the same), so it does not stay on 'Reprocessing in the app ...'."""
    import replay_view
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    ep = os.path.join(wd, "edits", tag, f"{tag}_manual_edits.json")
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]
    ckey = next(k for k in keys if k.startswith("replay_box_clean_"))[len("replay_box_"):]

    def state():
        C = at.session_state["cleaned"][tag]
        fl = C["flagged_shp"]
        P = rp.replay_payload(fl, kind="clean", record=C["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
        F = pyogrio.read_dataframe(fl, read_geometry=False)
        F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
        md5 = {p: _md5(p) for p in sorted(glob.glob(os.path.splitext(fl)[0] + ".*"))
               + sorted(glob.glob(os.path.splitext(C["shp"])[0] + ".*")) if p.endswith((".shp", ".dbf", ".shx"))}
        return C, P, F, md5

    def send(P, remove, keep=()):
        at.session_state[replay_view.marks_key(ckey)] = {"token": P["edit"]["token"], "remove": list(remove),
                                                         "keep": list(keep), "changed": len(remove) + len(keep)}
        _open(at, keys)

    # 1. no edits yet: every kept reading but one removed
    _open(at, keys)
    v0 = _version(at)
    C0, P0, F0, md5_0 = state()
    kept0 = _where(P0, F0, lambda r: r["Rem_By"] == "", 10 ** 6)
    assert len(kept0) > 60
    send(P0, kept0[1:])
    assert not at.exception, at.exception
    assert not os.path.exists(ep)                                          # put back: no edits file, as before
    W = [w.value for w in at.warning if "the cleaning with the marks of the replay stopped" in w.value]
    assert len(W) == 1 and "needs at least 30" in W[0] and "none: the automatic cleaning" in W[0], W
    assert "leave at least 30 readings kept" in W[0] and "check that filter's thresholds" not in W[0], W
    assert not any(s.value.startswith("Edits by hand:") for s in at.success)
    assert "edits_remove" not in [b.key for b in at.button]                 # no edits box: nothing in place
    assert at.session_state["cleaned"][tag]["flagged_shp"] == C0["flagged_shp"]
    assert {p: _md5(p) for p in md5_0} == md5_0                             # the cleaning shown did not change
    _open(at, keys)
    v1 = _version(at)
    assert v1 and v0 and v1 != v0 and v1.split(":")[0] == v0.split(":")[0]  # same files, the player loaded again
    # 2. five readings removed by hand (a cleaning made with them), then marks that leave too few
    send(P0, kept0[:5])
    assert not at.exception and os.path.exists(ep)
    before = open(ep, "rb").read()
    assert len(me.read_edits(ep)["remove"]) == 5
    _open(at, keys)
    C1, P1, F1, md5_1 = state()
    assert C1["R"]["manual_edits"]["remove"]["readings_applied"] == 5
    base = _where(P1, F1, lambda r: r["Rem_By"] == "SM", 10 ** 6)          # the marks the player starts with
    kept1 = _where(P1, F1, lambda r: r["Rem_By"] == "", 10 ** 6)
    assert len(base) == 5
    send(P1, base + kept1[1:])
    assert not at.exception, at.exception
    assert open(ep, "rb").read() == before                                 # the 5 edits, byte for byte
    W = [w.value for w in at.warning if "the cleaning with the marks of the replay stopped" in w.value]
    assert len(W) == 1 and "the edits of the cleaning shown" in W[0], W
    assert any(str(i.value).startswith("Edits by hand for this file: 5 reading(s) removed") for i in at.info)
    assert {p: _md5(p) for p in md5_1} == md5_1
    # 3. the next cleaning is not stopped by the marks: it gives the cleaning with the 5 edits again
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert at.session_state["cleaned"][tag]["R"]["manual_edits"]["remove"]["readings_applied"] == 5
    assert {p: _md5(p) for p in md5_1} == md5_1


def _start(tmp_path, monkeypatch):
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]
    ckey = next(k for k in keys if k.startswith("replay_box_clean_"))[len("replay_box_"):]
    _open(at, keys)
    C = at.session_state["cleaned"][tag]
    P = rp.replay_payload(C["flagged_shp"], kind="clean", record=C["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C["flagged_shp"], read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    return {"at": at, "tag": tag, "keys": keys, "ckey": ckey, "C": C, "P": P, "F": F,
            "ep": os.path.join(wd, "edits", tag, f"{tag}_manual_edits.json")}


def _send_marks(S, remove):
    import replay_view
    S["at"].session_state[replay_view.marks_key(S["ckey"])] = {"token": S["P"]["edit"]["token"],
                                                               "remove": list(remove), "keep": [],
                                                               "changed": len(remove)}
    _open(S["at"], S["keys"])


def test_app_marks_sent_while_a_file_is_open_elsewhere_apply_nothing(tmp_path, monkeypatch):
    """A clean file held open by another program: nothing is cleaned, so the marks are not applied either (no
    'Edits by hand' success, no edits file left behind); after the file is closed the file cleans as before."""
    S = _start(tmp_path, monkeypatch)
    at = S["at"]
    kept = _where(S["P"], S["F"], lambda r: r["Rem_By"] == "", 10 ** 6)
    fh = open(S["C"]["shp"], "rb")                     # Windows refuses the check's rename while it is open
    try:
        _send_marks(S, kept[1:])
    finally:
        fh.close()
    assert not at.exception, at.exception
    W = [w.value for w in at.warning if "were not applied, since nothing could be cleaned" in w.value]
    assert len(W) == 1 and "mark the readings again once the file is closed" in W[0], [w.value for w in at.warning]
    assert not any(s.value.startswith("Edits by hand:") for s in at.success)
    assert not os.path.exists(S["ep"])
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]


def test_app_a_cleaning_that_fails_after_writing_its_files_keeps_the_marks(tmp_path, monkeypatch):
    """A failure after the engine wrote the files (an OSError while handing them out): the files shown hold the marks'
    cleaning, so the edits file of the marks is kept (they agree) and the page says to clean again."""
    from engine import run as er
    S = _start(tmp_path, monkeypatch)
    at = S["at"]
    real = er.clean

    def boom(*a, **k):
        real(*a, **k)
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(er, "clean", boom)
    import replay_view
    at.session_state[replay_view.marks_key(S["ckey"])] = {"token": S["P"]["edit"]["token"], "keep": [], "changed": 5,
                                                          "remove": _where(S["P"], S["F"],
                                                                           lambda r: r["Rem_By"] == "", 5)}
    for k in S["keys"]:
        at.session_state[k] = True
    at.run()
    monkeypatch.setattr(er, "clean", real)
    # the app shows an unexpected error with its trace (st.exception), by design: only that one
    assert [e.value for e in at.exception] and all("No space left on device" in e.value for e in at.exception)
    assert any("stopped after it had written files" in w.value for w in at.warning), [w.value for w in at.warning]
    assert not any(s.value.startswith("Edits by hand:") for s in at.success)
    assert len(me.read_edits(S["ep"])["remove"]) == 5
    G = pyogrio.read_dataframe(S["C"]["flagged_shp"], read_geometry=False)
    assert int((G["Man_Edit"] == "R").sum()) == 5


def test_app_a_refusal_that_is_not_the_marks_is_said_as_it_is(tmp_path, monkeypatch):
    """A refusal before any file is written that has nothing to do with the marks: the edits file goes back as it was
    (the cleaning shown did not change), and the message gives the engine's reason without blaming the marks."""
    from engine import run as er
    S = _start(tmp_path, monkeypatch)
    at = S["at"]
    md5 = {p: _md5(p) for p in sorted(glob.glob(os.path.splitext(S["C"]["flagged_shp"])[0] + ".*"))
           if p.endswith((".shp", ".dbf", ".shx"))}

    def refuse(*a, **k):
        raise ValueError("synthetic: a setting the engine refuses")
    real = er.clean
    monkeypatch.setattr(er, "clean", refuse)
    _send_marks(S, _where(S["P"], S["F"], lambda r: r["Rem_By"] == "", 5))
    monkeypatch.setattr(er, "clean", real)
    assert not at.exception, at.exception
    W = [w.value for w in at.warning if "the cleaning with the marks of the replay stopped" in w.value]
    assert len(W) == 1 and "synthetic: a setting the engine refuses" in W[0] and "needs at least" not in W[0], W
    assert not os.path.exists(S["ep"]) and {p: _md5(p) for p in md5} == md5
