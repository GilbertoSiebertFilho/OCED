# -*- coding: utf-8 -*-
"""Works saved by OCED 0.3.0 opened by 0.3.1 (amendment A1.3 of the redesign), through Streamlit's AppTest on
synthetic data only. Each 0.3.0 record is built by hand in the test from a work of this version, in the shapes 0.3.0
leaves: a point export whose record names no crop (step 1's product) or names the product chosen as its crop (its
file panel imported again a file whose record had none); an export with Deere metadata that gives a crop id and no
name; raw task data decoded with step 1's product (0.3.0's ISOXML reader took the product for the task's crop) or
with a product chosen on data that names no crop; a card decoded with step 1's product whose import has the data's
own product; files whose points are away when the work is opened. The basis of each file is read from its data,
never from the crop its record names; a basis that cannot be read yet is not taken as known; 0.3.0's group of a
product is given only where the work shows its step 1 gave it; a file whose points are away stays in the work.

    python -m pytest -q tests/test_app_works_030.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import sms_import as si  # noqa: E402
from tests.app_steps import (_apply_import, _apply_to_all, _badge_lines, _set_import, _starts_from,  # noqa: E402
                             _switch_off, by_key)
from tests.test_app_steps import (_D, _app, _clean, _extract, _open, _orange, _pick, _prod, _reopen,  # noqa: E402
                                  _sig, field)

assert field                                             # (the module fixture of the synthetic field)
FROM_030 = {"by": "0.3.0", "group": "0.3.0"}
HAND = "not with this file's choice: a product chosen here goes only to files whose product came from the same choice"


def _exports(root, field, parts):
    """Point exports under root, each in a folder of its own: {name: (rows, product)}; product None: the synthetic
    field's own (Wheat); 'DROP': no Product column; a list: those names in turn (two crops); a dict: the
    -Deere-Metadata.json written beside it, with no Product column."""
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    for sub, (rows, prod) in parts.items():
        os.makedirs(os.path.join(root, sub))
        p = g.iloc[rows].copy()
        if prod == "DROP" or isinstance(prod, dict):
            p = p.drop(columns=["Product"])
        elif isinstance(prod, list):
            p["Product"] = [prod[i % len(prod)] for i in range(len(p))]
        elif prod:
            p["Product"] = prod
        shp = os.path.join(root, sub, f"Harvest_{sub}.shp")
        p.to_file(shp, engine="pyogrio")
        if isinstance(prod, dict):
            json.dump(prod, open(os.path.splitext(shp)[0] + "-Deere-Metadata.json", "w", encoding="utf-8"))
    return root


def _open_each(at, root, n):
    """Every dataset of the folder opened; their tags, sorted."""
    _open(at, root)
    for i in range(n):
        at.selectbox(key="cand_idx").select_index(i).run()
        assert not at.exception, at.exception
    tags = sorted(at.session_state["datasets"])
    assert len(tags) == n, tags
    return tags


def _as_0_3_0(at, wd, edits):
    """The saved work as 0.3.0 left it: each file of `edits` with its import under the default's name, no default
    block and no mode, its record without what 0.3.0 never wrote (mode, revision, own_yields, product_from), then
    edits[tag] (a dict of record keys, or a function of the dataset's record) applied."""
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    for t, ed in edits.items():
        D = _D(at, t)
        Dr = rec["datasets"][t]
        if D.get("sms_import") and D["import_default"].get("shp") and \
                os.path.normcase(D["shp"]) != os.path.normcase(D["import_default"]["shp"]):
            own, dflt = os.path.splitext(D["shp"])[0], os.path.splitext(D["import_default"]["shp"])[0]
            if os.path.normcase(dflt) == os.path.normcase(os.path.splitext(D["import_default"]["basis"]
                                                                          ["all_readings"])[0]):
                dflt = os.path.join(os.path.dirname(dflt), f"{t}_imported")    # (0.3.0's name; the readings stay)
            for q in glob.glob(dflt + ".*"):
                os.remove(q)
            for q in glob.glob(own + ".*"):
                os.replace(q, dflt + q[len(own):])
            Dr["shp"] = os.path.relpath(dflt + ".shp", wd) if not os.path.isabs(Dr["shp"]) else dflt + ".shp"
        for k in ("import_default", "import_mode"):
            Dr.pop(k, None)
        IM = Dr.get("sms_import")
        if isinstance(IM, dict):
            for k in ("mode", "revision", "own_yields", "product_from"):
                IM.pop(k, None)
        if callable(ed):
            ed(Dr)
        elif isinstance(IM, dict):
            IM.update(ed)
    json.dump(rec, open(p, "w", encoding="utf-8"))
    return rec


def _work_file(wd):
    return json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ point exports
def test_a_0_3_0_export_whose_record_names_the_product_as_its_crop_gets_its_basis_from_the_export(field, tmp_path,
                                                                                                  monkeypatch):
    """0.3.0's file panel imported again a file whose record had no crop: its record names the product as the crop
    (barley; nothing typed, or a maximum typed too), on a Wheat export, an export with no Product column, one that
    names two crops, and one whose Deere metadata gives a crop id only (the record keeps the monitor's wheat beside
    crop 'barley'). Each file's basis is read from the export, as a fresh open reads it: mode custom with barley as
    the user's product, its SMS default byte for byte a fresh open's (the two-crop file with the note a fresh open
    records), step 1 never 'barley'. Nothing in the work shows 0.3.0's step 1 gave barley, so no file gets the group
    0.3.0. Back to SMS's default gives the fresh default."""
    root = _exports(str(tmp_path / "in"), field, {"W1": (slice(None), None), "W2": (slice(0, None, 2), None),
                                                  "N": (slice(1, None, 2), "DROP"),
                                                  "T": (slice(0, None, 3), ["Wheat", "Canola"]),
                                                  "M": (slice(1, None, 3), {"CropId": 25})})
    at = _app(tmp_path / "ws", monkeypatch)
    tags = _open_each(at, root, 5)
    m, n, t2, w1, w2 = tags
    wd = at.session_state["workdir"]
    fresh = {t: _sig(_D(at, t)["import_default"]["shp"]) for t in tags}
    note = _D(at, t2)["import_default"]["sms_import"].get("crops_note")
    assert note and "more than one crop" in note
    assert _D(at, m)["sms_import"]["monitor"]["crop"] == "wheat" and _D(at, m)["sms_import"]["crop"] is None
    data = {t: _D(at, t)["import_default"]["basis"] for t in tags}
    for t in tags:
        _pick(at, t)
        _apply_import(at, prod="barley", **({"max": 150.0} if t == w2 else {}))
        assert _prod(at, t)[:2] == ("custom", "barley")
    def older_min(Dr):                                    # (and 0.3.0's minimum of 5 bu/ac: an older rule's import)
        Dr["sms_import"]["crop"] = "barley"
        Dr["sms_import"]["resolved"]["min_yield"] = 5.0
        Dr["sms_import"]["sources"]["min_yield"] = si.SRC_TABLE
    _as_0_3_0(at, wd, {t: (older_min if t == w1 else {"crop": "barley"}) for t in tags})
    _reopen(at, wd)
    # the work message says what importing it again with its own product gives (the data's crop is read from the
    # export, so barley is the user's), never what a fresh open does
    msg = at.session_state["work_msg"][1]
    assert (f"- {w1}: imported by an older version of OCED (product barley, 48.00 lb/bu, 14.5 %, from 5 bu/ac, no "
            "maximum); imported again with your settings under today's rule it is imported as SMS with product "
            "barley") in msg, msg
    for t in tags:
        D = _D(at, t)
        B = D["import_default"]["basis"]
        def mon(M):                                       # (the monitor's crop definition, without its wording)
            return {x: v for x, v in M.items() if x != "source"} if isinstance(M, dict) else M
        assert (B["crop"], mon(B["monitor"])) == (data[t]["crop"], mon(data[t]["monitor"])), (t, B)
        assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["product"] == "barley", t
        assert "product_from" not in D["sms_import"], t        # no file of the work shows step 1 gave barley
        _pick(at, t)
        DF = _D(at, t)["import_default"]
        assert _sig(DF["shp"]) == fresh[t], t
        b1 = _badge_lines(at)
        assert b1[0].startswith("SMS default") and "barley" not in b1[0], (t, b1)
    assert _D(at, t2)["import_default"]["sms_import"].get("crops_note") == note
    assert _D(at, w2)["sms_import"]["resolved"]["max_yield"] == 150.0
    _pick(at, w1)
    _apply_import(at, prod="wheat")                       # the data's own crop: back to the fresh default
    assert _prod(at, w1)[:2] == ("default", "wheat") and _sig(_D(at, w1)["shp"]) == fresh[w1]


def test_0_3_0s_group_of_a_product_only_where_the_work_shows_its_step_1_gave_it(field, tmp_path, monkeypatch):
    """A 0.3.0 work: A opened with step 1's barley (its record names no crop), B the same and then imported again in
    the file panel (its record names barley as its crop), C a Wheat export with barley chosen by hand in the file panel
    (its record keeps the data's crop), with 0.3.0's limits. A gets the group 0.3.0; B too, because A shows step 1
    gave barley in this work; C none (chosen by hand). Wheat named for all on A reaches B and leaves C, named in its
    own words; oats for all from C leaves A and B, given by 0.3.0's step 1. The work message says what importing C
    again with its settings gives, not what a fresh open does."""
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                                  "C": (slice(1, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c = _open_each(at, root, 3)
    wd = at.session_state["workdir"]
    fresh = {t: _sig(_D(at, t)["import_default"]["shp"]) for t in (a, b, c)}
    for t in (a, b, c):
        _pick(at, t)
        _apply_import(at, prod="barley")

    def older_limits(crop):
        def ed(Dr):
            IM = Dr["sms_import"]
            IM["crop"] = crop
            IM["resolved"].update({"min_yield": 5.0, "max_yield": 200.0})
            IM["sources"].update({"min_yield": si.SRC_TABLE, "max_yield": si.SRC_TABLE})
        return ed
    _as_0_3_0(at, wd, {a: {"crop": None}, b: {"crop": "barley"}, c: older_limits("Wheat")})
    _reopen(at, wd)
    assert [_D(at, t)["sms_import"].get("product_from") for t in (a, b, c)] == [FROM_030, FROM_030, None]
    msg = at.session_state["work_msg"][1]
    assert (f"- {c}: imported by an older version of OCED (product barley, 48.00 lb/bu, 14.5 %, 5-200 bu/ac); imported "
            "again with your settings under today's rule it is imported as SMS with product barley") in msg, msg
    _pick(at, c)
    _set_import(at, prod="oats")
    line = _orange(at)
    assert (f"Apply to all leaves {a} (Product barley), {b} (Product barley) as they are: the product of each was "
            "given by 0.3.0's step 1 to the files opened together, not with this file's: a product chosen here goes "
            "only to files whose product came from the same choice") in line, line
    _pick(at, a)
    _set_import(at, prod="wheat")
    line = _orange(at)
    assert f"Apply to all also changes {b} (Product barley → wheat;" in line, line
    assert (f"Apply to all leaves {c} (Product barley) as it is: its barley was chosen on it for its own data "
            f"(wheat), {HAND}") in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert [_prod(at, t)[:2] for t in (a, b, c)] == [("default", "wheat"), ("default", "wheat"), ("custom", "barley")]
    assert [_sig(_D(at, t)["shp"]) for t in (a, b)] == [fresh[a], fresh[b]]


def test_a_basis_that_cannot_be_read_yet_is_not_taken_as_known(field, tmp_path, monkeypatch):
    """0.3.0 exports read in place, their folder away the first time the work is opened: A (step 1's barley, its
    record names no crop), B (the same, imported again in the file panel: its record names barley as its crop), E
    (step 1's wheat on wheat data), U (step 1's barley, then 'unknown' in the file panel: no product kept), O (a
    record of the first version: no sources), M (barley chosen on an export whose Deere metadata gives a crop id: its
    record keeps the monitor's wheat), beside K, whose folder is there. Away: nothing is decided from a crop not read
    (no mode, no group), step 1 says the crop could not be read yet, step 2 offers no change, step 3 starts from an
    earlier version's import kept as it is, the work message names no older import, and Apply to all from K leaves
    them, named with that reason, before and after the click; M keeps the monitor product its record names (not
    pending) and is left because its readings are not at hand. The work is saved with the bases still to read. A, E
    and M back: Apply to all's plan reads A and E before they are viewed. Opened again with B, O and U still away,
    then back: Clean all reads them, and B gets the group 0.3.0 from what A showed when the work was first opened.
    Opened again, every file is what a present open makes of it: A custom on its wheat default with the group 0.3.0,
    E on its older rule's import (D7), U custom with its product named, O on its older rule's import."""
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None), "B": (slice(1, None, 4), None),
                                                  "E": (slice(0, None, 2), None), "U": (slice(1, None, 2), None),
                                                  "O": (slice(0, None, 3), None), "K": (slice(1, None, 3), None),
                                                  "M": (slice(2, None, 3), {"CropId": 25})})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, e, k, m, o, u = _open_each(at, root, 7)
    wd = at.session_state["workdir"]
    fresh = _sig(_D(at, a)["import_default"]["shp"])
    for t in (a, b, u, m):
        _pick(at, t)
        _apply_import(at, prod="barley")

    def first_version(Dr):
        Dr["sms_import"] = {x: Dr["sms_import"][x] for x in ("resolved", "settings", "left_out", "n_all", "n_in",
                                                            "all_readings", "changed", "notes")}
        Dr["sms_import"]["resolved"].update({"product": None, "test_weight_lb_bu": None, "dry_moisture_pct": None,
                                             "min_yield": 5.0, "max_yield": 300.0})

    def unknown(Dr):
        Dr["sms_import"]["crop"] = None
        Dr["sms_import"]["resolved"]["product"] = None

    def older_rule(Dr):                                   # step 1's wheat: 0.3.0's limits for a point export
        IM = Dr["sms_import"]
        IM["crop"] = None
        IM["resolved"].update({"min_yield": 5.0, "max_yield": 300.0})
        IM["sources"].update({"min_yield": si.SRC_TABLE, "max_yield": si.SRC_TABLE})
    _as_0_3_0(at, wd, {a: {"crop": None}, b: {"crop": "barley"}, e: older_rule, u: unknown, o: first_version,
                       m: {"crop": "barley"}})
    pend = (a, b, e, u, o)
    for x in ("A", "B", "E", "U", "O", "M"):              # their folders away (a drive not plugged in)
        os.replace(os.path.join(root, x), str(tmp_path / f"away_{x}"))
    _reopen(at, wd)
    for t in pend:
        D = _D(at, t)
        assert D["import_default"]["basis"].get("pending") and "import_mode" not in D, t
        assert "product_from" not in D["sms_import"], t
    Bm = _D(at, m)["import_default"]["basis"]             # the monitor product its record keeps is the data's
    assert not Bm.get("pending") and Bm["monitor"]["crop"] == "wheat" and _D(at, m)["import_mode"] == "custom", Bm
    msg = at.session_state["work_msg"][1]
    assert not any(f"- {t}: imported by an older version" in msg for t in pend), msg
    _pick(at, a)
    b1 = _badge_lines(at)
    assert b1[0].startswith("Older rule") and "not known" not in b1[0], b1
    cap = " ".join(c.value for c in at.caption)
    assert "The crop of its data could not be read yet" in cap and "could not be read yet: its import stays" in cap
    assert by_key(at.toggle, "fi_def_") is None
    assert any(x.startswith("Starts from Older rule") for x in b1), b1
    sf = _starts_from(at).help
    assert sf.startswith("Imported by an earlier version of OCED, kept as it is: the crop of its data could not be "
                         "read yet") and "Step 2 imports it" not in sf, sf
    _pick(at, k)
    _set_import(at, max=150.0)
    why = ("the crop of their data could not be read yet (their readings are not at hand): reconnect the drive and "
           "open the work again, then Apply on each")
    away = (f"its readings are not at hand ({m}: Harvest_M.shp in the folder M): reconnect the drive, then choose it "
            "in step 2 and Apply the same change on it")
    line = _orange(at)
    assert f"as they are: {why}." in line and all(f"{t}, " in line or f"{t} as" in line for t in pend), line
    assert f"Apply to all leaves {m} as it is: {away}." in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    msg = " ".join(x.value for x in at.success)
    assert f"Not imported again ({why}): " in msg and all(t in msg for t in pend), msg
    assert f"Not imported again ({away}): {m}." in msg, msg
    saved = _work_file(wd)["datasets"]
    assert all(saved[t]["import_default"]["basis"].get("pending") for t in pend)
    # A, E and M back: Apply to all's plan reads A and E before either is viewed
    for x in ("A", "E", "M"):
        os.replace(str(tmp_path / f"away_{x}"), os.path.join(root, x))
    _set_import(at, max=160.0)
    for t in (a, e):
        assert not _D(at, t)["import_default"]["basis"].get("pending"), t
    left = [t for t in at.session_state["datasets"] if t in (b, o, u)]
    assert f"Apply to all leaves {', '.join(left)} as they are: {why}." in _orange(at), _orange(at)
    # opened again with B, O and U away, then back: Clean all reads them; B gets the group 0.3.0 from what A showed
    _reopen(at, wd)
    assert all(_D(at, t)["import_default"]["basis"].get("pending") for t in (b, o, u))
    for x in ("B", "O", "U"):
        os.replace(str(tmp_path / f"away_{x}"), os.path.join(root, x))
    at.button(key="clean_all").click().run()
    assert not at.exception, at.exception
    for t in (b, o, u):
        assert not _D(at, t)["import_default"]["basis"].get("pending"), t
    assert _D(at, b)["sms_import"].get("product_from") == FROM_030
    _pick(at, a)
    D = _D(at, a)
    assert D["import_mode"] == "custom" and si.crop_key(D["import_default"]["basis"]["crop"]) == "wheat"
    assert D["sms_import"].get("product_from") == FROM_030 and _sig(D["import_default"]["shp"]) == fresh
    _reopen(at, wd)
    assert _D(at, e)["import_mode"] == "default" and _D(at, e)["import_default"].get("older")
    assert _D(at, o)["import_mode"] == "default" and _D(at, o)["import_default"].get("older")
    assert not any("→ unknown" in x for x in _D(at, o)["import_default"]["older"]), _D(at, o)["import_default"]
    _pick(at, u)
    assert _D(at, u)["import_mode"] == "custom" and "product_from" not in _D(at, u)["sms_import"]
    _switch_off(at)
    yours = [x for x in _badge_lines(at) if x.startswith("Your settings")]
    assert yours and yours[0].startswith("Your settings Product wheat → unknown") and "(older rule)" not in yours[0], \
        _badge_lines(at)


def test_files_whose_points_are_away_stay_in_the_work(field, tmp_path, monkeypatch):
    """A 0.3.0 work with an export opened with the import off (its file in use is the export itself, no default
    block) and cleaned, beside an export whose folder stays. The first folder is away when the work is opened: that
    file is set aside with its cleaning, named on the page; viewing the other file and applying a setting on it (each
    saves the work) keep it in the work file. With the folder back, the work opens with both files and the first
    one's cleaning (the second's was set aside by the setting applied)."""
    root = _exports(str(tmp_path / "in"), field, {"X": (slice(None), None), "Y": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    x, y = _open_each(at, root, 2)
    wd = at.session_state["workdir"]
    _pick(at, x)
    _apply_import(at, how="none")
    _clean(at)
    _pick(at, y)
    _clean(at)
    _as_0_3_0(at, wd, {x: {}})                            # as 0.3.0 saved it: the export itself, no default block
    os.replace(os.path.join(root, "X"), str(tmp_path / "x_away"))
    _reopen(at, wd)
    assert list(at.session_state["datasets"]) == [y] and x in at.session_state["away"]
    assert any(f"{x} (the folder X)" in c.value and "Set aside" in c.value for c in at.caption)
    _apply_import(at, max=150.0)                          # (saves the work)
    rec = _work_file(wd)
    # (Y's cleaning was set aside by the maximum applied; X's stays)
    assert set(rec["datasets"]) == {x, y} and set(rec["cleaned"]) == {x}, (rec["datasets"].keys(), rec["cleaned"].keys())
    os.replace(str(tmp_path / "x_away"), os.path.join(root, "X"))
    _reopen(at, wd)
    assert set(at.session_state["datasets"]) == {x, y} and set(at.session_state["cleaned"]) == {x}
    assert _D(at, x)["import_mode"] == "as_is"


# ------------------------------------------------------------------------------------------------ raw data
def _iso_task(tmp_path, **kw):
    from tests import synthetic_isoxml as SI
    R = SI.harvest(n_pass=4, n=40)
    return SI.write_set(str(tmp_path / "iso" / "s1" / "TASKDATA"), R, **kw)["folder"]


def _decode_with(at, root, t, wd, crop):
    """The task decoded as 0.3.0 decoded it with step 1's product (the decoder got the crop), into the work: the
    decode's {shp, report}."""
    import dataclasses

    from engine import run as er
    from engine.formats import detect
    D = _D(at, t)
    cand = next(c for c in detect.detect([root]) if c.get("kind") == "raw")
    o = dataclasses.replace(detect.default_options(cand["decoder"]), shrink="one_sided", crop=crop)
    d = er.decode(cand, D["source"]["unit_ids"], o, wd, log=lambda m: None, tag=t,
                  **dict(D["source"].get("decoder_kwargs") or {}))
    return {"shp": d["shp"], "report": json.load(open(d["report_json"], encoding="utf-8"))}


@pytest.mark.parametrize("crop_attr", [("P094_Crop_Type", 48), None], ids=["wheat", "no crop"])
def test_0_3_0_task_data_decoded_with_step_1s_product_gets_its_crop_from_the_task(crop_attr, tmp_path, monkeypatch):
    """ISOXML task data (of wheat, or naming a product and no crop) extracted by 0.3.0 with step 1's barley: its decode
    report names barley as the task's crop (and its monitor product barley's), its readings decoded with it. The
    basis is the task's own (its label: wheat, or no known crop), the readings are decoded again from the raw data for
    SMS's default (byte for byte a fresh extraction's), the file keeps 0.3.0's barley as its own with the group 0.3.0,
    and step 1 never says 'SMS default barley'."""
    task = _iso_task(tmp_path, crop_attr=crop_attr)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, task)
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    crop0 = _D(at)["import_default"]["basis"]["crop"]
    assert si.crop_key(crop0) == ("wheat" if crop_attr else None)
    fresh = _sig(_D(at)["import_default"]["shp"])
    _apply_import(at, prod="barley")
    dec = _decode_with(at, task, t, wd, "barley")
    assert si.crop_key(dec["report"]["crop_name"]) == "barley" and dec["report"]["options"]["crop"] == "barley"

    def step1_barley(Dr):
        Dr["report"] = dec["report"]
        Dr["sms_import"].update({"crop": "barley", "all_readings": dec["shp"],
                                 "monitor": dec["report"].get("monitor_product")})
        Dr["source"]["options"]["crop"] = "barley"
    _as_0_3_0(at, wd, {t: step1_barley})
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["product"] == "barley"
    assert D["sms_import"].get("product_from") == FROM_030
    assert si.crop_key(D["import_default"]["basis"]["crop"]) == si.crop_key(crop0)
    assert _sig(D["import_default"]["shp"]) == fresh
    b1 = _badge_lines(at)
    assert b1[0].startswith("SMS default") and "barley" not in b1[0], b1


def test_0_3_0_raw_data_of_no_crop_with_a_product_chosen_by_hand(tmp_path, monkeypatch):
    """ISOXML task data that names no crop, extracted untouched by 0.3.0, then barley chosen in its file panel (its
    record then names barley as the crop): the data's crop is not known (the record's crop is never taken), so the
    file is custom with barley as the user's product (no group 0.3.0) and its SMS default is a fresh extraction's."""
    task = _iso_task(tmp_path, crop_attr=None, density=False, product="")     # no crop, no product name
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, task)
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    assert _D(at)["import_default"]["basis"]["crop"] is None or not si.crop_key(_D(at)["import_default"]["basis"]["crop"])
    fresh = _sig(_D(at)["import_default"]["shp"])
    crop0 = _D(at)["import_default"]["basis"]["crop"]
    _apply_import(at, prod="barley")
    _as_0_3_0(at, wd, {t: {"crop": "barley"}})
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "custom" and "product_from" not in D["sms_import"]
    assert D["import_default"]["basis"]["crop"] == crop0 and _sig(D["import_default"]["shp"]) == fresh
    assert _badge_lines(at)[0].startswith("SMS default") and "barley" not in _badge_lines(at)[0]


def test_a_0_3_0_card_decoded_with_a_product_and_imported_with_its_data_s_own_is_no_pointer_default(tmp_path,
                                                                                                   monkeypatch):
    """A Case IH card that names its crop (wheat), extracted by 0.3.0 with step 1's barley, then wheat chosen in its
    file panel (the import in use has the data's own product, its readings decoded with barley): not a fresh
    extraction's file, so it is not kept as a plain 'SMS default'. Step 1's SMS default is decoded again from the raw
    data; the import in use and its cleaning stay, named in step 2 by its readings ('made from an older decode').
    Opened with the raw data away, the default is the older version's readings and the import in use is still named
    by its readings, in step 2, in step 3's help, in step 4's table and in the sidebar, never 'your values'."""
    from tests.test_app_steps import _card_030
    K = _card_030(tmp_path, monkeypatch, crop_on_card=True)
    at, t, wd = K["at"], K["t"], K["wd"]
    rec = json.loads(K["work_030"])
    RS = rec["datasets"][t]["sms_import"]["resolved"]
    RS.update({"product": "wheat", "test_weight_lb_bu": 60.0, "dry_moisture_pct": 13.5})
    assert rec["datasets"][t]["report"]["options"]["crop"] == "barley"
    json.dump(rec, open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8"))
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "custom" and "product_from" not in D["sms_import"]
    assert not D["import_default"].get("older") and not D["import_default"].get("older_decode")
    assert (D["import_default"]["report"].get("options") or {}).get("crop") is None        # decoded again
    assert _badge_lines(at)[0].startswith("SMS default") and t in at.session_state["cleaned"]
    assert [x for x in _badge_lines(at) if x.startswith("Your settings")] == ["Your settings made from an older "
                                                                              "decode"], _badge_lines(at)
    # (its raw data at hand: the file's own decode report names the product: step 3, step 4 and the sidebar too)
    assert "made from an older decode (decoded by an older OCED with product barley" in _starts_from(at).help
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["made from an older decode"], list(T4["import"])
    assert any(c.value.startswith(f"**{t}**: made from an older decode") for c in at.sidebar.caption)
    # the raw data away the first time the work is opened
    json.dump(rec, open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8"))
    os.replace(str(tmp_path / "cnh"), str(tmp_path / "cnh_away"))
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "custom" and D["import_default"].get("older_decode"), D["import_default"]
    assert [x for x in _badge_lines(at) if x.startswith("Your settings")] == ["Your settings made from an older "
                                                                              "decode"], _badge_lines(at)
    assert "made from an older decode (decoded by an older OCED with product barley" in _starts_from(at).help
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["made from an older decode"], list(T4["import"])
    assert any(c.value.startswith(f"**{t}**: made from an older decode") for c in at.sidebar.caption)


# ------------------------------------------------------------------------------------------------ step 2 and Apply to all
def test_a_product_chosen_keeps_a_limit_it_does_not_change_on_the_file(field, tmp_path, monkeypatch):
    """A point export with its own maximum: barley chosen in step 2 leaves the maximum shown (no product sets one on
    a point export), so Apply on it alone keeps it, as Apply to all keeps it on every file it reaches."""
    from tests.test_app_steps import _exports as _exp
    root = _exp(tmp_path, field, {"A": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root / "A" / "Harvest_A.shp")
    _apply_import(at, max=150.0)
    _set_import(at, prod="barley")
    assert by_key(at.number_input, "fi_max_").value == 150.0
    assert by_key(at.number_input, "fi_tw_").value == 48.0
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, at.session_state["active"]) == ("custom", "barley", 48.0, 14.5, 150.0)


def test_apply_to_all_names_how_to_finish_a_target_whose_default_fails(field, tmp_path, monkeypatch):
    """A maximum applied to all, then taken back for all: B goes back to its SMS default, which has to be built again
    and cannot be written (a full disk). B keeps its import and its line names the reason and the way to finish it
    (Apply on it), not 'try again', which Apply to all can no longer do."""
    from tests.test_app_steps import _exports as _exp
    from tests.test_app_steps import _open_all
    root = _exp(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b = _open_all(at, root, 2)
    _pick(at, a)
    _apply_to_all(at, max=150.0)
    for q in glob.glob(os.path.splitext(_D(at, b)["import_default"]["shp"])[0] + ".*"):
        os.remove(q)
    real = si.apply

    def full(src, out, R, *x, **kw):
        if "Harvest_B" in str(out):
            raise OSError(28, "No space left on device")
        return real(src, out, R, *x, **kw)
    monkeypatch.setattr(si, "apply", full)
    _set_import(at, max=None)
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    warn = " ".join(w.value for w in at.warning)
    assert (f"{b}: SMS's default import of this file could not be made (OSError: No space left on device): the file "
            "and its import are unchanged; free disk space, then choose it in step 2 and Apply the same change on it"
            ) in warn, warn
    assert "free disk space and try again" not in warn, warn
    assert _prod(at, a)[0] == "default" and _prod(at, b)[0] == "custom" and _prod(at, b)[4] == 150.0


def test_extracting_again_keeps_where_a_product_came_from(tmp_path, monkeypatch):
    """A raw file with a product of its own whose record names where it came from (0.3.0's step 1): extracted again
    from the same input, its own settings are applied again and the record keeps that group."""
    from tests import synthetic_jdl as SJ
    from tests.app_steps import _extract_again
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at)
    t = at.session_state["active"]
    _apply_import(at, prod="barley")
    _D(at, t)["sms_import"]["product_from"] = dict(FROM_030)
    _extract_again(at)
    assert _prod(at, t)[:2] == ("custom", "barley") and _D(at, t)["sms_import"].get("product_from") == FROM_030


def test_apply_to_all_counts_a_file_with_no_record_and_keeps_a_group_on_the_same_product(field, tmp_path,
                                                                                           monkeypatch):
    """A file that keeps no record of its import is counted on the button and named as left, before and after the
    click. A 0.3.0 file of step 1's barley applied again with that product (a maximum typed) keeps its group, so a
    product chosen for all on another file of step 1's barley still reaches it."""
    from tests.test_app_steps import _as_0_3_0_with_step_1s_product
    from tests.test_app_steps import _exports as _exp
    from tests.test_app_steps import _open_all
    root = _exp(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                  "U": (slice(1, None, 2), "Variety1")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, u = _open_all(at, root, 3)
    wd = at.session_state["workdir"]
    for t in (a, u):
        _pick(at, t)
        _apply_import(at, prod="barley")
    _as_0_3_0_with_step_1s_product(at, wd, (a, u))
    _reopen(at, wd)
    _pick(at, u)
    assert _D(at, u)["sms_import"].get("product_from") == FROM_030
    _apply_import(at, max=120.0)
    assert _D(at, u)["sms_import"].get("product_from") == FROM_030
    _D(at, b)["import_default"].pop("basis", None)        # B keeps no record of its import
    _pick(at, a)
    _set_import(at, prod="oats")
    g = by_key(at.button, "fi_goall_")
    assert g.label == "Apply to all 3 harvest files" and not g.disabled, g.label
    line = _orange(at)
    assert f"Apply to all also changes {u} (Product barley → oats;" in line, line
    assert (f"Apply to all leaves {b} as it is: it keeps no record of its import: open its data again (step 1)."
            in line), line
    g.click().run()
    assert not at.exception, at.exception
    assert _prod(at, u)[:2] == ("custom", "oats") and _prod(at, u)[4] == 120.0
    msg = " ".join(s.value for s in at.success)
    assert f"Not imported again (it keeps no record of its import: open its data again (step 1)): {b}." in msg, msg


def test_own_settings_of_0_3_0_that_today_s_rule_cannot_name_are_named(field, tmp_path, monkeypatch):
    """A 0.3.0 import with a minimum of 0 typed (today's default) beside the older rule's maximum of 300: step 2's
    'Your settings' line names the older rule's value instead of 'your values'."""
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, os.path.join(root, "A", "Harvest_A.shp"))
    a, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)

    def min0(Dr):
        IM = Dr["sms_import"]
        IM["resolved"].update({"min_yield": 0.0, "max_yield": 300.0})
        IM["sources"].update({"min_yield": si.SRC_YOU, "max_yield": si.SRC_TABLE})
    _as_0_3_0(at, wd, {a: min0})
    _reopen(at, wd)
    assert _D(at, a)["import_mode"] == "custom"
    yours = [x for x in _badge_lines(at) if x.startswith("Your settings")]
    assert yours and "Max. yield volume none → 300.00 (older rule)" in yours[0], _badge_lines(at)


def test_a_0_3_0_export_keeps_the_monitor_product_its_record_names_when_its_metadata_is_gone(field, tmp_path,
                                                                                           monkeypatch):
    """An Operations Center export whose Deere metadata gives a crop id (wheat), barley chosen in 0.3.0's file panel
    (its record names barley and keeps the monitor's wheat). The metadata no longer beside the export when the work
    is opened: the basis keeps the monitor's wheat (0.3.0 took it only from the metadata), so the file is custom with
    barley as the user's product and its SMS default is wheat's, a fresh open's byte for byte."""
    root = _exports(str(tmp_path / "in"), field, {"M": (slice(None), {"CropId": 25})})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, os.path.join(root, "M", "Harvest_M.shp"))
    m, wd = at.session_state["active"], at.session_state["workdir"]
    B0 = dict(_D(at, m)["import_default"]["basis"])
    fresh = _sig(_D(at, m)["import_default"]["shp"])
    _apply_import(at, prod="barley")
    _as_0_3_0(at, wd, {m: {"crop": "barley"}})
    for q in (os.path.join(root, "M", "Harvest_M"), os.path.splitext(B0["all_readings"])[0]):   # (and the work's copy)
        if os.path.exists(q + "-Deere-Metadata.json"):
            os.remove(q + "-Deere-Metadata.json")
    assert not glob.glob(os.path.join(wd, "**", "*-Deere-Metadata.json"), recursive=True)
    _reopen(at, wd)
    D = _D(at, m)
    B = D["import_default"]["basis"]
    assert not B.get("pending") and B["monitor"]["crop"] == "wheat" and B["fmt"] == B0["fmt"], B
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["product"] == "barley"
    assert _sig(_D(at, m)["import_default"]["shp"]) == fresh
    assert _badge_lines(at)[0].startswith("SMS default") and "barley" not in _badge_lines(at)[0]


def test_0_3_0_task_data_decoded_with_its_own_crop_as_step_1s_product_stays_on_its_import(tmp_path, monkeypatch):
    """ISOXML task data of wheat extracted by 0.3.0 with step 1's wheat (the decoder got the data's own crop): its
    readings are decoded as a fresh extraction decodes them, so the file stays on its import as SMS's default."""
    task = _iso_task(tmp_path, crop_attr=("P094_Crop_Type", 48))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, task)
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    dec = _decode_with(at, task, t, wd, "wheat")

    def step1_wheat(Dr):
        Dr["report"] = dec["report"]
        Dr["sms_import"].update({"crop": "wheat", "monitor": dec["report"].get("monitor_product")})
        Dr["source"]["options"]["crop"] = "wheat"
    _as_0_3_0(at, wd, {t: step1_wheat})
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "default" and not D["import_default"].get("older_decode"), D["import_default"]
    assert _badge_lines(at)[0].startswith("SMS default")


def test_apply_to_all_names_each_origin_of_a_product_it_leaves(field, tmp_path, monkeypatch):
    """Oats chosen on E (wheat data, barley chosen on it by hand): the files of barley are left, each origin of their
    product in its own words: A, a 0.3.0 file of step 1's barley (given by 0.3.0's step 1); C and D, canola data
    given barley by Apply to all from C (given by Apply to all with another file's choice); F, barley data on its
    own product (its data's own)."""
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None), "C": (slice(0, None, 2), "Canola"),
                                                  "D": (slice(1, None, 2), "Canola"), "E": (slice(0, None, 3), None),
                                                  "F": (slice(1, None, 3), "Barley")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, c, d, e, f = _open_each(at, root, 5)
    wd = at.session_state["workdir"]
    _pick(at, c)
    _apply_to_all(at, prod="barley")                      # C and D: barley given by Apply to all (canola data)
    for t in (a, e):
        _pick(at, t)
        _apply_import(at, prod="barley")
    _as_0_3_0(at, wd, {a: {"crop": None}})                # A: as 0.3.0 saved step 1's barley
    _reopen(at, wd)
    assert _D(at, a)["sms_import"].get("product_from") == FROM_030
    assert [_D(at, t)["sms_import"].get("product_from") for t in (c, d)] == [{"by": "all", "group": "data:canola"}] * 2
    _pick(at, e)
    _set_import(at, prod="oats")
    line = _orange(at)
    same = "a product chosen here goes only to files whose product came from the same choice as this file's"
    assert (f"Apply to all leaves {a} (Product barley) as it is: its barley was given by 0.3.0's step 1 to the files "
            f"opened together, not with this file's: {same}.") in line, line
    assert (f"Apply to all leaves {c} (Product barley), {d} (Product barley) as they are: the product of each was "
            f"given by Apply to all with another file's choice, not with this file's: {same}.") in line, line
    assert (f"Apply to all leaves {f} (Product barley) as it is: its barley is its data's own, where this file's was "
            f"chosen: {same}.") in line, line


UNREAD = "check that the export is complete (its .shp, .shx and .dbf), or open its data again (step 1)"


@pytest.mark.parametrize("how", ["read_error", "held", "io_error", "no_shx", "cut_dbf", "zero_dbf"])
def test_a_0_3_0_export_that_cannot_be_read_at_the_open_is_not_taken_as_naming_no_crop(how, field, tmp_path,
                                                                                       monkeypatch):
    """A 0.3.0 export of step 1's barley (its record names no crop) whose file is there but cannot be read when the
    work is first opened (its reader fails with an access denied or an input/output error; on Windows, another program
    holds its .dbf with no sharing, which GDAL would read as a file with no columns; its .shx is missing; its .dbf is
    cut after 40 bytes, or 0 bytes long: a header that is not valid): its basis is pending, never 'no crop', and saved so; step 1's
    badge, steps 1, 2 and 3 and Apply to all from K, before and after its click, tell the reason it could not be read
    (the first sentence of the reader's message) and the way on that follows its cause: close the program that holds
    it for an access denied or a file held, else check that the export is complete; never to reconnect a drive.
    Readable again, the next open reads the data's wheat: the file is custom with barley of 0.3.0's step 1 and its SMS
    default is a fresh open's, byte for byte."""
    if how == "held" and os.name != "nt":
        pytest.skip("a file held with no sharing is a Windows case")
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None), "K": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, k = _open_each(at, root, 2)
    wd = at.session_state["workdir"]
    _pick(at, a)
    fresh = _sig(_D(at, a)["import_default"]["shp"])
    readings = _D(at, a)["import_default"]["basis"]["all_readings"]      # (the export the work reads)
    _apply_import(at, prod="barley")
    _as_0_3_0(at, wd, {a: {"crop": None}})
    real, held = pyogrio.read_info, {"on": how in ("read_error", "io_error")}

    def info(path, *x, **kw):
        if held["on"] and os.path.basename(str(path)).lower() == "harvest_a.shp":
            if how == "io_error":
                raise OSError(5, "Input/output error")
            raise PermissionError(13, "The process cannot access the file because it is being used by another "
                                      "process")
        return real(path, *x, **kw)
    monkeypatch.setattr(pyogrio, "read_info", info)
    stem = os.path.splitext(readings)[0]
    keep = {}
    for ext in ({"no_shx": [".shx"], "cut_dbf": [".dbf"], "zero_dbf": [".dbf"]}.get(how) or []):
        keep[ext] = open(stem + ext, "rb").read()
        if ext == ".shx":
            os.remove(stem + ext)
        else:
            open(stem + ext, "wb").write(keep[ext][:0 if how == "zero_dbf" else 40])
    k32 = h = None
    if how == "held":
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.CreateFileW.restype = ctypes.c_void_p
        h = k32.CreateFileW(stem + ".dbf", 0x80000000, 0, None, 3, 0x80, None)
        assert h not in (None, ctypes.c_void_p(-1).value)
    advice = "close the program that holds it" if how in ("read_error", "held") else UNREAD
    other = UNREAD if how in ("read_error", "held") else "close the program"
    try:
        _reopen(at, wd)
        B = _D(at, a)["import_default"]["basis"]
        assert B.get("pending") and B.get("crop") is None, B
        why = {"read_error": "Harvest_A.shp could not be read: PermissionError: ",
               "held": "Harvest_A.dbf could not be read: PermissionError: ",
               "io_error": "Harvest_A.shp could not be read: OSError: Input/output error",
               "no_shx": "Harvest_A.shp could not be read: ",
               "cut_dbf": "Harvest_A.dbf could not be read: its header is not valid (the file is cut or damaged)",
               "zero_dbf": "Harvest_A.dbf could not be read: its header is not valid (the file is cut or damaged)"}[how]
        assert B.get("why", "").startswith(why), B
        if how in ("io_error", "cut_dbf", "zero_dbf"):
            assert B["why"] == why, B
        if how == "no_shx":                               # the first sentence of the reader's message only
            assert "Harvest_A.shx" in B["why"] and "SHAPE_RESTORE_SHX" not in B["why"], B
        _pick(at, a)
        badge = next(m.help for m in at.markdown if "oced-badge" in m.value)
        said = [c.value for c in at.caption] + [str(c.help) for c in at.caption if c.help] + [_starts_from(at).help]
        told = [x for x in said + [str(badge)] if "could not be read yet (" in x]
        assert len(told) >= 4 and all(B["why"] in x and advice in x and other not in x for x in told), told
        assert B["why"] in str(badge) and advice in str(badge), badge
        assert not any("reconnect the drive" in x for x in told), told
        h2 = next(c.help for c in at.caption if c.value.startswith(":orange[The crop of this file's data could not"))
        assert str(h2).endswith(". Its import settings can be changed once it can be read."), h2
        assert ". Its import settings can be changed once it can be read." in str(_starts_from(at).help)
        _pick(at, k)
        _set_import(at, max=150.0)
        assert (f"Apply to all leaves {a} as it is: the crop of its data could not be read yet ({B['why']}): "
                f"{advice}, then Apply on it." in _orange(at)), _orange(at)
        by_key(at.button, "fi_goall_").click().run()
        assert not at.exception, at.exception
        done = " ".join(s.value for s in at.success)
        assert (f"Not imported again (the crop of its data could not be read yet ({B['why']}): {advice}, then Apply "
                f"on it): {a}.") in done, done
        at.button(key="work_save").click().run()
        assert _work_file(wd)["datasets"][a]["import_default"]["basis"].get("pending")
    finally:
        held["on"] = False
        if h is not None:
            k32.CloseHandle(ctypes.c_void_p(h))
        for ext, b in keep.items():
            open(stem + ext, "wb").write(b)
    _reopen(at, wd)
    _pick(at, a)                                          # (its SMS default is built when it is viewed)
    D = _D(at, a)
    assert not D["import_default"]["basis"].get("pending")
    assert si.crop_key(D["import_default"]["basis"]["crop"]) == "wheat", D["import_default"]["basis"]
    assert D["import_mode"] == "custom" and D["sms_import"].get("product_from") == FROM_030
    assert _sig(D["import_default"]["shp"]) == fresh


def test_an_unreadable_0_3_0_export_whose_folder_then_goes_away_is_told_to_reconnect_the_drive(field, tmp_path,
                                                                                               monkeypatch):
    """The 0.3.0 export of the test above, held by another program when the work is opened (its reason kept in its
    pending basis), then released and its folder moved away while the work is on screen: the reason no longer holds,
    so steps 1, 2 and 3 say its readings are not at hand and to reconnect the drive, never to close a program; the
    basis stays pending, and Save writes it without that reason. With the folder back, the next open reads its wheat."""
    root = _exports(str(tmp_path / "in"), field, {"A": (slice(None), None), "K": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, k = _open_each(at, root, 2)
    wd = at.session_state["workdir"]
    _pick(at, a)
    _apply_import(at, prod="barley")
    _as_0_3_0(at, wd, {a: {"crop": None}})
    real, held = pyogrio.read_info, {"on": True}

    def info(path, *x, **kw):
        if held["on"] and os.path.basename(str(path)).lower() == "harvest_a.shp":
            raise PermissionError(13, "The process cannot access the file because it is being used by another "
                                      "process")
        return real(path, *x, **kw)
    monkeypatch.setattr(pyogrio, "read_info", info)
    _reopen(at, wd)
    _pick(at, a)
    assert _D(at, a)["import_default"]["basis"].get("why"), _D(at, a)["import_default"]["basis"]
    assert any("close the program that holds it" in str(c.help) for c in at.caption if c.help)
    held["on"] = False
    os.replace(os.path.join(root, "A"), str(tmp_path / "a_away"))
    _pick(at, k)
    _pick(at, a)
    assert not at.exception, at.exception
    B = _D(at, a)["import_default"]["basis"]
    assert B.get("pending") and "why" not in B, B
    said = [c.value for c in at.caption] + [str(c.help) for c in at.caption if c.help] + [_starts_from(at).help]
    told = [x for x in said if "could not be read yet (" in x]
    assert told and all("its readings are not at hand" in x and "reconnect the drive" in x for x in told), told
    assert not any("close the program" in x for x in said), said
    at.button(key="work_save").click().run()
    Bw = _work_file(wd)["datasets"][a]["import_default"]["basis"]
    assert Bw.get("pending") and "why" not in Bw, Bw
    os.replace(str(tmp_path / "a_away"), os.path.join(root, "A"))
    _reopen(at, wd)
    _pick(at, a)
    D = _D(at, a)
    assert not D["import_default"]["basis"].get("pending")
    assert si.crop_key(D["import_default"]["basis"]["crop"]) == "wheat", D["import_default"]["basis"]
