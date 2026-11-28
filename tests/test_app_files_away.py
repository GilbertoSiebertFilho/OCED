# -*- coding: utf-8 -*-
"""Files whose points are away, products taken back and the files Apply to all leaves (amendment A1.3 of the
redesign and its first verification round), through Streamlit's AppTest on synthetic data only. A file in use read in
place (the export as it is) whose folder is away keeps its import and its cleaning, at an open and while a session
runs; only an import the app derived inside the work folder that is gone sends a file back to its SMS default. A file
set aside says where its points were and can be removed from its work; a new file never takes its tag. 'unknown'
takes a product back to the data's own (a Case IH card of barley goes back to its SMS default, 5-200 bu/ac; an export
whose Deere metadata gives only a crop id is on its data's own product); Apply to all leaves a file whose readings are
not at hand, and tells each origin of a product given in its own words. Verification round 2: a file removed from its
work leaves the work message and is saved out of the work, its only file too; a file whose own readings are not at
hand offers no Apply; imports the app derived that are gone send a file back to its SMS default.

    python -m pytest -q tests/test_app_files_away.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.app_steps import _apply_import, _badge_lines, _extract_again, _set_import, by_key  # noqa: E402
from tests.test_app_steps import (_D, _app, _clean, _exports, _extract, _open, _open_all, _orange, _pick,  # noqa: E402
                                  _reopen, field)

assert field                                             # (the module fixture of the synthetic field)


def _work_file(wd):
    return json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))


def _p(at, t):
    """(mode, product, weight to volume, dry moisture, min., max. yield volume) of a file's import in use."""
    D = _D(at, t)
    R = (D.get("sms_import") or {}).get("resolved") or {}
    return (D.get("import_mode"), R.get("product"), R.get("test_weight_lb_bu"), R.get("dry_moisture_pct"),
            R.get("min_yield"), R.get("max_yield"))


def _fields(at):
    return {k: by_key(at.number_input, f"fi_{k}_").value for k in ("tw", "dm", "min", "max")}


def _not_applied(at):
    return [c.value for c in at.caption if "Not applied" in c.value]


# ------------------------------------------------------------------------------------------------ files away
def test_an_export_read_in_place_keeps_its_import_and_cleaning_while_its_folder_is_away(field, tmp_path, monkeypatch):
    """An export on 'None' (the export itself in use, read in place), cleaned, its SMS default built inside the work.
    Its folder away while the session runs: the page says its points are not at hand and changes nothing (no back to
    SMS's default, the cleaning kept). Away when the work is opened: the file is set aside with its cleaning (its
    default inside the work does not make its import 'gone'), and another input opened next saves the work with it.
    With the folder back: 'None' as before, the same file in use, its cleaning not flagged."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None)})
    other = tmp_path / "other"
    os.makedirs(other)
    shutil.copytree(root / "B", other / "Z")
    at = _app(tmp_path / "ws", monkeypatch)
    a, b = _open_all(at, root, 2)
    wd = at.session_state["workdir"]
    _pick(at, a)
    _apply_import(at, how="none")
    C0 = _clean(at)
    D = _D(at, a)
    shp0 = os.path.normcase(D["shp"])
    assert D["import_mode"] == "as_is" and os.path.exists(D["import_default"]["shp"])
    assert os.path.normcase(os.path.dirname(D["import_default"]["shp"])).startswith(os.path.normcase(wd))
    # away while the session runs (a drive unplugged): nothing changes
    os.replace(root / "A", tmp_path / "away_A")
    _pick(at, b)
    _pick(at, a)
    assert any("The points of this file are no longer at" in e.value for e in at.error)
    assert not any("no longer on disk" in w.value for w in at.warning), [w.value for w in at.warning]
    D = _D(at, a)
    assert D["import_mode"] == "as_is" and os.path.normcase(D["shp"]) == shp0
    assert a in at.session_state["cleaned"] and not at.session_state["cleaned"][a].get("clean_again")
    assert os.path.exists(C0["shp"])
    _pick(at, b)
    at.button(key="work_save").click().run()
    assert _work_file(wd)["datasets"][a]["import_mode"] == "as_is"
    # away when the work is opened: set aside, then another input opened (the outgoing work is saved)
    _reopen(at, wd)
    assert a in at.session_state["away"] and a not in at.session_state["datasets"]
    msg = at.session_state["work_msg"][1]
    assert (f"{a}: its points are no longer in the folder A: it stays in this work, set aside with its cleaning, "
            "until they are back (reconnect the drive and open the work again), or remove it from this work (step 1)"
            ) in msg, msg
    assert "no longer on disk" not in msg and "clean it again" not in msg, msg
    _open(at, other)
    assert at.session_state["workdir"] != wd
    rec = _work_file(wd)
    assert rec["datasets"][a]["import_mode"] == "as_is" and a in rec["cleaned"]
    os.replace(tmp_path / "away_A", root / "A")
    _reopen(at, wd)
    _pick(at, a)
    D = _D(at, a)
    assert D["import_mode"] == "as_is" and os.path.normcase(D["shp"]) == shp0
    assert a in at.session_state["cleaned"] and not at.session_state["cleaned"][a].get("clean_again")
    assert "no longer on disk" not in at.session_state["work_msg"][1]


def test_an_import_of_the_users_that_is_gone_still_goes_back_to_sms_default(field, tmp_path, monkeypatch):
    """The import the app wrote with the user's settings (inside the work folder) deleted: at the next open the file
    goes back to SMS's default import and its cleaning is flagged to be cleaned again, as before."""
    root = _exports(tmp_path, field, {"A": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root / "A" / "Harvest_A.shp")
    a, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)
    _clean(at)
    own = _D(at, a)["shp"]
    assert own.endswith("_imported_custom.shp")
    at.button(key="work_save").click().run()
    for q in glob.glob(os.path.splitext(own)[0] + ".*"):
        os.remove(q)
    _reopen(at, wd)
    assert _D(at, a)["import_mode"] == "default" and a not in at.session_state["away"]
    msg = at.session_state["work_msg"][1]
    assert f"{a}: its import with your settings is no longer on disk: it is back to SMS's default import" in msg, msg
    assert at.session_state["cleaned"][a].get("clean_again")


def test_a_file_whose_points_in_the_work_folder_are_gone_is_set_aside_and_can_be_removed(field, tmp_path,
                                                                                         monkeypatch):
    """A raw file whose decoded readings inside the work folder were deleted (no cleaning) beside a cleaned export:
    set aside at the open, the message says its points are no longer in the work folder and that its data must be
    opened again (never 'reconnect the drive', never 'with its cleaning'); step 1 names it and offers to remove it,
    asked first ('Keep it' keeps it). Removed, the work file no longer lists it, and the sidebar's work message no
    longer says it stays in the work (the plain 'Opened ...')."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    shp = _D(at, t)["shp"]
    assert os.path.normcase(shp).startswith(os.path.normcase(wd))
    at.button(key="work_save").click().run()
    for q in glob.glob(os.path.splitext(shp)[0] + ".*"):
        os.remove(q)
    _reopen(at, wd)
    assert t in at.session_state["away"] and not at.session_state["datasets"]
    msg = at.session_state["work_msg"][1]
    line = next(x for x in msg.split("\n") if x.startswith(f"- {t}:"))
    assert line == (f"- {t}: its points are no longer in the work folder (the folder decoded): it stays in this work, "
                    "set aside; open its data again (step 1) to import it again, or remove it from this work (step 1)"
                    ), line
    cap = " ".join(c.value for c in at.caption if "Set aside" in c.value)
    assert f"{t} (in the work folder: the folder decoded)" in cap and "reconnect the drive" not in cap, cap
    assert "with the cleaning" not in cap, cap
    by_key(at.button, "rm_away_").click().run()
    assert not at.exception, at.exception
    assert any(f"Remove {t} from this work?" in w.value for w in at.warning)
    by_key(at.button, "rm_away_no_").click().run()
    assert t in at.session_state["away"] and t in _work_file(wd)["datasets"]
    by_key(at.button, "rm_away_").click().run()
    by_key(at.button, "rm_away_yes_").click().run()
    assert not at.exception, at.exception
    assert t not in at.session_state["away"]
    assert t not in _work_file(wd)["datasets"]
    assert any(f"{t} was removed from this work" in s.value for s in at.success)
    kind, msg = at.session_state["work_msg"]
    assert kind == "ok" and not any(x.startswith(f"- {t}:") for x in msg.split("\n")), msg
    assert not any("stays in this work" in str(x.value) for x in (*at.sidebar.warning, *at.sidebar.success,
                                                                   *at.warning, *at.caption)), msg


def test_a_file_set_aside_with_its_cleaning_is_named_so_and_keeps_what_the_work_holds_of_it(field, tmp_path,
                                                                                           monkeypatch):
    """An export on 'None', cleaned, with a boundary, grower's data, 3-sigma and combine settings in the work file, its
    folder away at the open: step 1 names it with its cleaning; a setting applied on the other file (a save) writes
    every part of it back unchanged."""
    root = _exports(tmp_path, field, {"X": (slice(None), None), "Y": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    x, y = _open_all(at, root, 2)
    wd = at.session_state["workdir"]
    _pick(at, x)
    _apply_import(at, how="none")
    _clean(at)
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    extra = {"grower": {"weight": 1000.0, "unit": "lb", "use": "validate"}, "a3set": {"k": 3.0},
             "combines": {"on": True, "method": "auto"},
             "boundary": {"path": os.path.join(str(tmp_path), "nowhere", "b.shp"), "feature": [0]}}
    for k, v in extra.items():
        rec.setdefault(k, {})[x] = v
    json.dump(rec, open(p, "w", encoding="utf-8"))
    os.replace(root / "X", tmp_path / "x_away")
    _reopen(at, wd)
    cap = " ".join(c.value for c in at.caption if "Set aside" in c.value)
    assert f"{x} (the folder X)" in cap and f"with the cleaning of {x}" in cap, cap
    _apply_import(at, max=150.0)                          # (on Y: saves the work)
    after = _work_file(wd)
    for k, v in extra.items():
        assert after[k].get(x) == v, (k, after[k].get(x))
    assert x in after["cleaned"] and after["datasets"][x]["import_mode"] == "as_is"


def test_a_new_file_never_takes_the_tag_of_a_file_set_aside(field, tmp_path, monkeypatch):
    """A file set aside keeps its tag: an export of the same name picked next, and a raw unit extracted again, each get
    a tag of their own (the file set aside is kept in the work)."""
    import geopandas as gpd
    root = _exports(tmp_path, field, {"X": (slice(None), None)})
    os.makedirs(root / "Z")                               # another export of the same name (other readings)
    gpd.read_file(field["shp"]).iloc[::2].to_file(str(root / "Z" / "Harvest_X.shp"), engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root)
    at.selectbox(key="cand_idx").select_index(0).run()
    x = at.session_state["active"]
    ds = at.session_state["datasets"]
    at.session_state["away"][x] = {"dataset": ds.pop(x)}         # (as an open sets it aside)
    at.selectbox(key="cand_idx").select_index(1).run()
    assert not at.exception, at.exception
    z = at.session_state["active"]
    assert z and z.casefold() != x.casefold() and x in at.session_state["away"], (x, z)
    assert {x, z} <= set(_work_file(at.session_state["workdir"])["datasets"])
    from tests import synthetic_jdl as SJ
    at2 = _app(tmp_path / "ws2", monkeypatch)
    _open(at2, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at2)
    t = at2.session_state["active"]
    at2.session_state["away"][t] = {"dataset": at2.session_state["datasets"].pop(t)}
    _extract_again(at2)
    t2 = at2.session_state["active"]
    assert t2 and t2.casefold() != t.casefold() and t in at2.session_state["away"], (t, t2)


# ------------------------------------------------------------------------------------------------ a product taken back
def _barley_card(tmp_path, monkeypatch):
    """A synthetic Case IH card whose crop number is barley's (SMS: 48 lb/bu, 14.5 %, 5-200 bu/ac), extracted."""
    from tests import synthetic_cn1 as SC
    monkeypatch.setattr(SC, "CROP", 17)
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t = at.session_state["active"]
    assert _p(at, t) == ("default", "barley", 48.0, 14.5, 5.0, 200.0)
    return at, t


def test_unknown_on_a_card_of_barley_takes_the_product_back_to_its_sms_default(tmp_path, monkeypatch):
    """A Case IH card of barley: wheat chosen names every change, the maximum too (200 to 300); 'unknown' chosen
    again before any Apply puts the fields back on the card's own values and leaves nothing to apply. Wheat applied,
    then 'unknown' chosen: the fields show the card's own barley values and Apply puts the card back on its SMS
    default (5-200 bu/ac), not on its own settings with a maximum nobody typed."""
    at, t = _barley_card(tmp_path, monkeypatch)
    _set_import(at, prod="wheat")
    assert _fields(at) == {"tw": 60.0, "dm": 13.5, "min": 5.0, "max": 300.0}
    assert _not_applied(at) == [":orange[Not applied: Product barley → wheat, Weight to volume 48.00 → 60.00, Dry "
                                "moisture 14.50 → 13.50, Max. yield volume 200.00 → 300.00]"], _not_applied(at)
    by_key(at.selectbox, "fi_prod_").select_index(0).run()      # 'unknown'
    assert not at.exception, at.exception
    assert _fields(at) == {"tw": 48.0, "dm": 14.5, "min": 5.0, "max": 200.0}
    assert not _not_applied(at) and by_key(at.button, "fi_go_").disabled
    _apply_import(at, prod="wheat")
    assert _p(at, t) == ("custom", "wheat", 60.0, 13.5, 5.0, 300.0)
    _set_import(at)
    by_key(at.selectbox, "fi_prod_").select_index(0).run()
    assert not at.exception, at.exception
    assert _fields(at) == {"tw": 48.0, "dm": 14.5, "min": 5.0, "max": 200.0}
    assert _not_applied(at) == [":orange[Not applied: Product wheat → unknown, Weight to volume 60.00 → 48.00, Dry "
                                "moisture 13.50 → 14.50, Max. yield volume 300.00 → 200.00]"], _not_applied(at)
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert _p(at, t) == ("default", "barley", 48.0, 14.5, 5.0, 200.0)
    assert not any(x.startswith("Your settings") for x in _badge_lines(at)), _badge_lines(at)


# ------------------------------------------------------------------------------------------------ Apply to all
def test_apply_to_all_leaves_a_file_whose_readings_are_not_at_hand(field, tmp_path, monkeypatch):
    """B on its own settings (its import inside the work), cleaned, its export's folder away: a maximum typed on A
    and applied to all changes C and names B as left, before and after the click, with where its readings were and
    the way to finish it; B keeps its import and its cleaning (never named as a cleaning set aside)."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c = _open_all(at, root, 3)
    _pick(at, b)
    _apply_import(at, max=120.0)
    _clean(at)
    os.replace(root / "B", tmp_path / "away_B")
    _pick(at, a)
    _set_import(at, max=150.0)
    line = _orange(at)
    why = (f"its readings are not at hand ({b}: Harvest_B.shp in the folder B): reconnect the drive, then choose it "
           "in step 1 and Apply the same change on it")
    assert f"Apply to all also changes {c} (Max. yield volume none → 150.00)." in line, line
    assert f"Apply to all leaves {b} as it is: {why}." in line, line
    assert f"{b} (Max." not in line and "sets aside the cleaning of" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    msg = " ".join(s.value for s in at.success)
    assert f"Not imported again ({why}): {b}." in msg, msg
    assert not any("no longer on disk" in w.value for w in at.warning), [w.value for w in at.warning]
    assert _p(at, b)[0] == "custom" and _p(at, b)[5] == 120.0 and b in at.session_state["cleaned"]
    assert _p(at, c)[5] == 150.0


# ------------------------------------------------------------------------------------------------ removed, saved
def test_removing_the_only_file_of_a_work_while_its_folder_is_away_is_saved(field, tmp_path, monkeypatch):
    """One export on 'None' (read in place), cleaned and saved; its folder away while the session runs: 'Remove this
    file from the work', under the error, is saved although no file is left; the next open shows no file, none set
    aside, and a plain 'Opened ...'."""
    root = _exports(tmp_path, field, {"X": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root)                                       # (read in place: its folder opened)
    x, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, how="none")
    _clean(at)
    at.button(key="work_save").click().run()
    assert x in _work_file(wd)["datasets"]
    os.replace(root / "X", tmp_path / "x_away")
    at.run()
    assert any("The points of this file are no longer at" in e.value for e in at.error)
    by_key(at.button, "rm_file_").click().run()
    assert not at.exception, at.exception
    rec = _work_file(wd)
    assert not rec["datasets"] and x not in (rec.get("cleaned") or {}), sorted(rec["datasets"])
    _reopen(at, wd)
    assert not at.session_state["datasets"] and not at.session_state["away"]
    kind, msg = at.session_state["work_msg"]
    assert kind == "ok" and f"- {x}:" not in msg, msg


def test_removing_the_file_on_screen_beside_a_file_set_aside_saves_the_work_with_the_file_set_aside(field, tmp_path,
                                                                                                     monkeypatch):
    """X and Y on 'None'; X's folder deleted and the work opened (X set aside, Y on screen); Y's folder away while the
    session runs and Y removed with 'Remove this file from the work': the work file lists X only, and step 1 still
    offers to remove X."""
    root = _exports(tmp_path, field, {"X": (slice(None), None), "Y": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    x, y = _open_all(at, root, 2)
    wd = at.session_state["workdir"]
    for t in (x, y):
        _pick(at, t)
        _apply_import(at, how="none")
    at.button(key="work_save").click().run()
    shutil.rmtree(root / "X")
    _reopen(at, wd)
    assert x in at.session_state["away"] and list(at.session_state["datasets"]) == [y]
    os.replace(root / "Y", tmp_path / "y_away")
    at.run()
    by_key(at.button, "rm_file_").click().run()
    assert not at.exception, at.exception
    assert sorted(_work_file(wd)["datasets"]) == [x] and x in at.session_state["away"]
    assert any(b.label == f"Remove {x} from this work" for b in at.button), [b.label for b in at.button]


# ------------------------------------------------------------------------------------------------ derived imports gone
def test_an_import_of_the_users_deleted_while_the_session_runs_goes_back_to_sms_default(field, tmp_path, monkeypatch):
    """The import the app wrote with the user's settings deleted while the session runs: the next run of the page puts
    the file back on SMS's default import and sets its cleaning aside, and says so; no 'points no longer at' error."""
    root = _exports(tmp_path, field, {"A": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root / "A" / "Harvest_A.shp")
    a = at.session_state["active"]
    _apply_import(at, max=150.0)
    _clean(at)
    own = _D(at, a)["shp"]
    assert own.endswith("_imported_custom.shp")
    for q in glob.glob(os.path.splitext(own)[0] + ".*"):
        os.remove(q)
    at.run()
    assert not at.exception, at.exception
    D = _D(at, a)
    assert D["import_mode"] == "default" and os.path.exists(D["shp"]) and a not in at.session_state["cleaned"]
    assert any(w.value.startswith(f"{a}: its import with your settings is no longer on disk: back to SMS's default "
                                  "import. Its cleaning was set aside: clean it again in step 3.")
               for w in at.warning), [w.value for w in at.warning]
    assert not any("The points of this file are no longer at" in e.value for e in at.error)


def test_a_card_decoded_as_logged_whose_decode_is_gone_opens_back_on_sms_default(tmp_path, monkeypatch):
    """A Case IH card file on 'None: as the monitor logged it' (its decode under as_logged/), saved, that decode
    deleted: the work opens with the file back on SMS's default import (never set aside), and the message says so."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, how="none")
    shp = _D(at, t)["shp"]
    assert _D(at, t)["import_mode"] == "as_is" and os.path.relpath(shp, wd).startswith("as_logged")
    at.button(key="work_save").click().run()
    for q in glob.glob(os.path.splitext(shp)[0] + ".*"):
        os.remove(q)
    _reopen(at, wd)
    assert t in at.session_state["datasets"] and t not in at.session_state["away"]
    assert _D(at, t)["import_mode"] == "default" and os.path.exists(_D(at, t)["shp"])
    msg = at.session_state["work_msg"][1]
    assert f"- {t}: its import with your settings is no longer on disk: it is back to SMS's default import" in msg, msg


# ------------------------------------------------------------------------------------------------ readings not at hand
def test_apply_to_all_names_readings_gone_from_inside_the_work_folder(field, tmp_path, monkeypatch):
    """Two exports opened from a zip (their readings unpacked into the work's input folder); B on its own settings and
    cleaned; B's readings deleted from that folder. A maximum typed on A: the orange line and the result of Apply to
    all say to open B's data again (never 'reconnect the drive'), and B keeps its import and cleaning. On B itself,
    one line says its readings are no longer in the work folder and Apply and Apply to all are disabled."""
    import zipfile
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None)})
    zp = str(tmp_path / "both.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for q in glob.glob(os.path.join(str(root), "*", "*")):
            z.write(q, os.path.relpath(q, str(root)))
    at = _app(tmp_path / "ws", monkeypatch)
    a, b = _open_all(at, zp, 2)
    wd = at.session_state["workdir"]
    rb = _D(at, b)["import_default"]["basis"]["all_readings"]
    assert os.path.normcase(rb).startswith(os.path.normcase(wd))
    _pick(at, b)
    _apply_import(at, max=120.0)
    _clean(at)
    for q in glob.glob(os.path.splitext(rb)[0] + ".*"):
        os.remove(q)
    _pick(at, a)
    _set_import(at, max=150.0)
    why = (f"its readings are no longer in the work folder ({b}: Harvest_B.shp in the folder B): open its data again "
           "(step 1) to import it with this change")
    line = _orange(at)
    assert f"Apply to all leaves {b} as it is: {why}." in line and "reconnect the drive" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    msg = " ".join(s.value for s in at.success)
    assert f"Not imported again ({why}): {b}." in msg, msg
    assert _p(at, b)[0] == "custom" and _p(at, b)[5] == 120.0 and b in at.session_state["cleaned"]
    _pick(at, b)
    _set_import(at, max=130.0)
    line = _orange(at)
    assert (f"The readings {b} is imported from are no longer in the work folder (Harvest_B.shp in the folder B): "
            "open its data again (step 1) to change its import; to change the other files, choose one of them in the "
            "File list and type the change on it.") in line, line
    assert "sets aside the cleaning" not in line and "Apply to all also changes" not in line, line
    assert by_key(at.button, "fi_go_").disabled and by_key(at.button, "fi_goall_").disabled


def test_apply_is_disabled_while_the_readings_of_the_file_on_screen_are_away(field, tmp_path, monkeypatch):
    """A on SMS's default (its import inside the work), cleaned, beside K; A's export folder away while the session
    runs. A maximum typed on A: no promise of a cleaning set aside or of changes in K, one orange line that says its
    readings are not at hand and how to go on, Apply and Apply to all disabled; A keeps its import and cleaning, K is
    untouched."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "K": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, k = _open_all(at, root, 2)
    _pick(at, a)
    _clean(at)
    before = (_p(at, a), _p(at, k), _D(at, a)["shp"])
    os.replace(root / "A", tmp_path / "away_A")
    _pick(at, k)
    _pick(at, a)
    _set_import(at, max=130.0)
    assert not at.exception, at.exception
    assert _not_applied(at) == [":orange[Not applied: Max. yield volume none → 130.00]"], _not_applied(at)
    line = _orange(at)
    assert (f"The readings {a} is imported from are not at hand (Harvest_A.shp in the folder A): reconnect the drive "
            "to change its import; to change the other files, choose one of them in the File list and type the "
            "change on it.") in line, line
    assert "sets aside the cleaning" not in line and "Apply to all also changes" not in line, line
    assert by_key(at.button, "fi_go_").disabled and by_key(at.button, "fi_goall_").disabled
    assert (_p(at, a), _p(at, k), _D(at, a)["shp"]) == before and a in at.session_state["cleaned"]


# ------------------------------------------------------------------------------------------------ the data's product
def test_unknown_on_an_export_whose_metadata_gives_only_a_crop_id_is_nothing_typed(field, tmp_path, monkeypatch):
    """An export whose Deere metadata gives only a crop id (wheat by the monitor's crop definition, no crop name), on
    its SMS default and cleaned: 'unknown' chosen in the Product field is its data's own product, so nothing is typed
    (no 'Not applied' line, Apply and Apply to all disabled, its cleaning kept); with barley applied on it, the
    Product field's help says 'From: you'."""
    from tests.test_app_works_030 import _exports as _exp
    root = _exp(str(tmp_path / "in"), field, {"M": (slice(None), {"CropId": 25}), "W": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    m, w = _open_all(at, root, 2)
    _pick(at, m)
    B = _D(at, m)["import_default"]["basis"]
    assert not B.get("crop") and (B.get("monitor") or {}).get("crop") == "wheat", B
    assert _p(at, m)[:2] == ("default", "wheat")
    _clean(at)
    _set_import(at)
    by_key(at.selectbox, "fi_prod_").select_index(0).run()      # 'unknown'
    assert not at.exception, at.exception
    assert not _not_applied(at), _not_applied(at)
    assert by_key(at.button, "fi_go_").disabled and by_key(at.button, "fi_goall_").disabled
    assert m in at.session_state["cleaned"]
    assert str(by_key(at.selectbox, "fi_prod_").help).startswith("From: the data's crop.")
    _apply_import(at, prod="barley")
    _set_import(at)
    assert str(by_key(at.selectbox, "fi_prod_").help).startswith("From: you."), by_key(at.selectbox, "fi_prod_").help


# ------------------------------------------------------------------------------------- verification round 3 of A1.3
def test_none_as_logged_offers_no_apply_while_the_raw_data_is_away(tmp_path, monkeypatch):
    """A Case IH card on SMS's default, cleaned; its raw data folder away while the session runs. 'None: as the
    monitor logged it' decodes the raw data again: one orange line says the raw data is not at hand and how to go on,
    no promise of a cleaning set aside, Apply disabled, the file unchanged. 'As SMS' with a maximum typed reads the
    decoded readings inside the work and stays offered. With the raw data back, 'None' is offered again."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t = at.session_state["active"]
    _clean(at)
    before = (_p(at, t), _D(at, t)["shp"])
    os.replace(tmp_path / "cnh", tmp_path / "cnh_away")
    at.run()
    _set_import(at, how="none")
    assert not at.exception, at.exception
    line = _orange(at)
    name = os.path.basename(os.path.normpath(cd["card"]))
    assert (f"The raw data of {t} is not at hand (the folder {name}): reconnect the drive or open it again (step 1) "
            "to decode it as the monitor logged it.") in line, line
    assert "Applying sets aside" not in line and str(tmp_path) not in line, line
    assert by_key(at.button, "fi_go_").disabled
    assert (_p(at, t), _D(at, t)["shp"]) == before and t in at.session_state["cleaned"]
    _set_import(at, how="sms", max=150.0)
    assert "The raw data of" not in _orange(at) and f"Applying sets aside the cleaning of {t}" in _orange(at)
    assert not by_key(at.button, "fi_go_").disabled
    os.replace(tmp_path / "cnh_away", tmp_path / "cnh")
    _set_import(at, how="none")
    assert "The raw data of" not in _orange(at) and not by_key(at.button, "fi_go_").disabled


def test_none_on_a_card_whose_decoded_readings_are_gone_decodes_it_again(tmp_path, monkeypatch):
    """A Case IH card on its own settings (a maximum that leaves readings out, its import in imported/) whose decoded
    readings, the basis of its imports inside the work, are deleted while its card is at hand: 'As SMS' says the
    readings are not at hand and offers no Apply; 'None: as the monitor logged it' decodes the card again, so it is
    offered and its Apply works."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t = at.session_state["active"]
    _apply_import(at, max=20.0)
    B = _D(at, t)["import_default"]["basis"]["all_readings"]
    assert os.path.normcase(_D(at, t)["shp"]) != os.path.normcase(B)
    for q in glob.glob(os.path.splitext(B)[0] + ".*"):
        os.remove(q)
    at.run()
    assert not at.exception, at.exception
    _set_import(at, max=30.0)
    assert f"The readings {t} is imported from are no longer in the work folder" in _orange(at), _orange(at)
    assert by_key(at.button, "fi_go_").disabled
    _set_import(at, how="none")
    assert "The readings" not in _orange(at) and "The raw data of" not in _orange(at), _orange(at)
    _apply_import(at, how="none")
    assert not at.exception, at.exception
    assert _D(at, t)["import_mode"] == "as_is" and not at.error, [e.value for e in at.error]


def test_removing_the_file_on_screen_takes_its_lines_out_of_the_work_message_and_leaves_the_others(field, tmp_path,
                                                                                                  monkeypatch):
    """Two exports on 'None' (read in place), both cleaned and saved; the clean shapefiles of both deleted, so the
    open says a line of each. X's folder then goes away while the session runs and X is removed with 'Remove this file
    from the work': X's line leaves the work message, Y's stays."""
    root = _exports(tmp_path, field, {"X": (slice(None), None), "Y": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    x, y = _open_all(at, root, 2)
    wd = at.session_state["workdir"]
    for t in (x, y):
        _pick(at, t)
        _apply_import(at, how="none")
        _clean(at)
    at.button(key="work_save").click().run()
    for t in (x, y):
        for q in glob.glob(os.path.splitext(at.session_state["cleaned"][t]["shp"])[0] + ".*"):
            os.remove(q)
    _reopen(at, wd)
    _pick(at, x)
    lines = str(at.session_state["work_msg"][1]).split("\n")
    assert [z for z in lines if z.startswith(f"- {x}: ")] and [z for z in lines if z.startswith(f"- {y}: ")], lines
    os.replace(root / "X", tmp_path / "x_away")
    at.run()
    by_key(at.button, "rm_file_").click().run()
    assert not at.exception, at.exception
    assert list(at.session_state["datasets"]) == [y]
    kind, msg = at.session_state["work_msg"]
    lines = msg.split("\n")
    assert kind == "warning" and not [z for z in lines if z.startswith(f"- {x}: ")], msg
    assert [z for z in lines if z.startswith(f"- {y}: ")], msg


def test_removing_the_file_of_the_last_line_under_a_head_of_its_own_leaves_no_message(field, tmp_path, monkeypatch):
    """A work message started by a line about a file in this session ('In this work:' and that line): once that file
    is removed from the work, no message is left (not an empty head)."""
    root = _exports(tmp_path, field, {"X": (slice(None), None), "Y": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    x, y = _open_all(at, root, 2)
    _pick(at, x)
    _apply_import(at, how="none")
    at.session_state["work_msg"] = ("warning", f"In this work:\n- {x}: its cleaning was set aside: clean it again")
    os.replace(root / "X", tmp_path / "x_away")
    at.run()
    by_key(at.button, "rm_file_").click().run()
    assert not at.exception, at.exception
    assert list(at.session_state["datasets"]) == [y]
    assert at.session_state["work_msg"] is None, at.session_state["work_msg"]


def test_the_product_help_says_from_you_for_a_product_chosen_on_data_that_names_none(field, tmp_path, monkeypatch):
    """An export with no Product column (its data names no product): the Product field's help names no source while
    the product is unknown, and 'From: you' once barley is applied on it."""
    from tests.test_app_works_030 import _exports as _exp
    root = _exp(str(tmp_path / "in"), field, {"N": (slice(None), "DROP")})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, os.path.join(root, "N", "Harvest_N.shp"))
    n = at.session_state["active"]
    assert not _D(at, n)["import_default"]["basis"].get("crop")
    _set_import(at)
    h = str(by_key(at.selectbox, "fi_prod_").help)
    assert h.startswith("Another product fills in") and "From:" not in h, h
    _apply_import(at, prod="barley")
    _set_import(at)
    h = str(by_key(at.selectbox, "fi_prod_").help)
    assert h.startswith("From: you. Another product fills in"), h


def test_none_as_logged_offers_no_apply_while_the_raw_data_folder_is_empty(tmp_path, monkeypatch):
    """0.3.2 (M8): the raw data folder of a Case IH card is there but no longer holds its raw data (its content moved
    away while the session runs): 'None: as the monitor logged it' gets the same orange line as a folder away and no
    Apply; the content back, 'None' is offered again."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t = at.session_state["active"]
    _clean(at)
    before = (_p(at, t), _D(at, t)["shp"])
    root = _D(at, t)["source"]["input_root"]
    hold = tmp_path / "content_away"
    hold.mkdir()
    for x in os.listdir(root):
        shutil.move(os.path.join(root, x), str(hold / x))
    assert os.path.isdir(root) and not os.listdir(root)
    at.run()
    _set_import(at, how="none")
    line = _orange(at)
    assert (f"The raw data of {t} is not at hand (the folder {os.path.basename(os.path.normpath(root))}): reconnect "
            "the drive or open it again (step 1) to decode it as the monitor logged it.") in line, line
    assert "Applying sets aside" not in line and by_key(at.button, "fi_go_").disabled
    assert (_p(at, t), _D(at, t)["shp"]) == before
    for x in os.listdir(hold):
        shutil.move(str(hold / x), os.path.join(root, x))
    at.run()
    assert "The raw data of" not in _orange(at) and not by_key(at.button, "fi_go_").disabled


def _raw_source(kind, folder):
    """The input to open of a synthetic raw source: Gen4 logs, ISOXML task data or a Case IH card."""
    if kind == "jd_jdl":
        from tests.synthetic_jdl import make_card
        make_card(folder)
        return folder
    if kind == "isoxml":
        from tests import synthetic_isoxml as SI
        SI.write_set(os.path.join(folder, "TASKDATA"), SI.harvest())
        return folder
    from tests import synthetic_cn1 as SC
    return SC.make_card(folder)["card"]


@pytest.mark.parametrize("kind", ["jd_jdl", "isoxml", "cnh_cn1"])
def test_none_as_logged_offers_no_apply_once_the_raw_files_below_its_folders_are_gone(kind, tmp_path, monkeypatch):
    """0.3.2 (M8): 'None' chosen once while the raw data is there (Apply offered), then every raw file deleted below
    the input folder with every folder and the files at its top kept (its own modification time unchanged; a Case IH
    card's skeleton still looks like a card): 'None' again gets the orange line and no Apply, nothing of the file changed."""
    src = _raw_source(kind, str(tmp_path / "in"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, src)
    _extract(at)
    t = at.session_state["active"]
    if kind == "jd_jdl":                                 # the synthetic logs drive at one speed: no SD to filter on
        at.toggle(key="t_speed").set_value(False).run()
        at.toggle(key="t_moist").set_value(False).run()
    _clean(at)
    before = (_p(at, t), _D(at, t)["shp"])
    root = _D(at, t)["source"]["input_root"]
    _set_import(at, how="none")
    assert "The raw data of" not in _orange(at) and not by_key(at.button, "fi_go_").disabled
    assert "Applying sets aside the cleaning" in _orange(at)
    _set_import(at, how="sms")
    m0 = os.stat(root).st_mtime_ns
    gone = 0
    for d, _, fs in os.walk(root):
        if os.path.normcase(d) == os.path.normcase(root):
            continue                                    # the files at its top stay (the deletion is below)
        for f in fs:
            os.remove(os.path.join(d, f))
            gone += 1
    assert gone and os.stat(root).st_mtime_ns == m0
    at.run()
    _set_import(at, how="none")
    line = _orange(at)
    assert f"The raw data of {t} is not at hand (the folder {os.path.basename(os.path.normpath(root))})" in line, line
    assert "Applying sets aside" not in line and by_key(at.button, "fi_go_").disabled
    assert (_p(at, t), _D(at, t)["shp"]) == before


def test_two_files_of_one_card_each_get_their_own_answer_whether_their_raw_data_is_at_hand(tmp_path):
    """0.3.2 (R3): two files decoded from one synthetic Case IH card (one task each), the raw files of the second
    file's task then deleted: the app's check that the raw data is at hand (raw_at_hand, kept for the session) answers
    each file on its own, whichever is checked first: the first's raw data is there, the second's is not."""
    from engine import run as er
    from engine import works as ew
    from engine.formats import detect
    from tests import synthetic_cn1 as SC
    from tests.test_app_fixes import _app_function

    cd = SC.make_card(str(tmp_path / "in"))
    wd = str(tmp_path / "w")
    cand = [c for c in er.open_input([cd["card"]], wd, log=lambda m: None) if c.get("kind") == "raw"][0]
    ids = sorted(u.id for u in er.list_units(cand))
    assert len(ids) == 2
    D = {t: {"source": dict(er.decode(cand, [u], None, wd, log=lambda m: None, tag=t)["source"])}
         for t, u in zip(("A", "B"), ids)}
    task_b = ids[1].rsplit("/", 1)[-1]
    gone = [f for f in os.listdir(cd["field_dir"]) if f.startswith(task_b + ".")]
    assert gone
    for f in gone:
        os.remove(os.path.join(cd["field_dir"], f))

    class SS(dict):
        __getattr__ = dict.__getitem__

    ns = dict(os=os, ss=SS(workdir=wd), detect=detect, er=er, ew=ew)
    raw_at_hand = _app_function("raw_at_hand", "_raw_candidate", "_tree_sig", "default_of", "_raw_root",
                                "_folder_name", **ns)[0]
    root = raw_at_hand.__globals__["_raw_root"](D["A"])
    for order in (("A", "B"), ("B", "A")):
        ns["ss"].clear()
        ns["ss"]["workdir"] = wd
        got = {t: raw_at_hand(t, D[t], root) for t in order}
        assert got == {"A": True, "B": False}, (order, got)


def test_a_raw_file_already_on_none_says_nothing_of_its_raw_data_away(tmp_path, monkeypatch):
    """0.3.2 (M9, rule P1d of 0.3.1): a card already on 'None' (decoded as the monitor logged it) whose raw data then
    goes away: with no change pending step 2 draws no line about the raw data and no Apply; choosing 'As SMS' needs
    only its readings."""
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t = at.session_state["active"]
    _apply_import(at, how="none")
    assert _D(at, t)["import_mode"] == "as_is"
    os.replace(tmp_path / "cnh", tmp_path / "cnh_away")
    at.run()
    _set_import(at)
    assert "The raw data of" not in _orange(at), _orange(at)
    assert by_key(at.button, "fi_go_").disabled


@pytest.mark.parametrize("why, held", [
    ("PermissionError: [Errno 13] Permission denied: 'x.dbf'", True),
    ("x.dbf could not be read: permissionerror", True),
    ("OSError: [WinError 5] Access is denied", True),
    ("The process cannot access the file because it is being used by another process", True),
    ("a sharing violation on x.dbf", True),
    ("OSError: Input/output error", False),
    ("x.shx is missing", False),
    (None, False)])
def test_held_reason_knows_each_word_of_a_file_held(why, held):
    """0.3.2 (M9, rules P2f, P2g and N9 of 0.3.1): each of the five words of a file held open or an access denied
    makes the advice 'close the program that holds it'; any other reason the advice to check the export."""
    from tests.test_app_fixes import _app_function
    held_reason, unread_advice = _app_function("held_reason", "unread_advice",
                                               UNREAD_ADVICE="check that the export is complete")
    assert held_reason(why) is held
    assert unread_advice(why) == ("close the program that holds it" if held else "check that the export is complete")
