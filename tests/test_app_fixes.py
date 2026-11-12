# -*- coding: utf-8 -*-
"""The app (app/oced.py) after the final verification, on synthetic data only: an as-applied file cleaned twice, a
changed setting that survives Save + Open as 'clean again', the 'Apply the factors' checkbox of a new cleaning, a
cleaning lock left by a process that is gone, an import that leaves no reading, ISOXML input named without a
contradiction, the 'clean it again' line of an opened work once the file is cleaned again, a re-import whose weight
reaches the writer of the monitor's format, the depth of each writer's output (short folder names, the estimate the
app checks before writing), and a ValueError raised inside a library shown with its traceback.

    python -m pytest -q tests/test_app_fixes.py
"""
from __future__ import annotations

import ast
import glob
import io
import json
import os
import re
import shutil
import sys
import zipfile

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_applied, make_field, make_two_combines  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
STALE = "settings, the boundary or the grower's data changed"


def _by_key(items, prefix):
    return next(x for x in items if str(x.key or "").startswith(prefix))


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception


def _clean(at):
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at.session_state["cleaned"][at.session_state["active"]]


def _app_function(*names, **ns):
    """Functions of app/oced.py with the globals they need, without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(fns, []), APP, "exec"), ns)
    return [ns[n] for n in names]


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


# ------------------------------------------------------------------------------------------------ step 3
def test_as_applied_file_cleaned_twice(tmp_path, monkeypatch):
    """R1: the second cleaning of a planter file publishes its clean set (the .zip listed once), nothing left
    aside (.bak) and no 'open in another program'."""
    A = make_applied(str(tmp_path / "data"), "seeding")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, A["shp"])
    first = _clean(at)["at"]
    os.utime(A["shp"])
    C = _clean(at)
    cdir = os.path.join(at.session_state["workdir"], "clean_shapefiles")
    assert C["at"] >= first and os.path.exists(C["zip"])
    assert not glob.glob(os.path.join(cdir, "*.bak")) and not glob.glob(os.path.join(cdir, "*.oced_chk"))
    # RA-2: the flagged file of a planter file holds every reading (the clipped ones with Rem_By S1): said so
    cap = next(c.value for c in at.caption if "Flagged = " in c.value)
    assert "for a planter or sprayer file every reading, the clipped ones with Rem_By S1" in cap
    assert "for a harvest file" not in cap
    assert len(pyogrio.read_dataframe(C["flagged_shp"], read_geometry=False)) == A["n"]


def test_a_change_after_the_cleaning_survives_save_and_open(field, tmp_path, monkeypatch):
    """R3: the cleaning's config is saved with the work: a standard moisture changed after the cleaning still says
    'clean again' once the work is saved and opened again (it was compared with a config rebuilt from the changed
    state). VA-9: the 'clean it again' line of an opened work goes once that file is cleaned again."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.number_input, "gw_w_").set_value(110_000.0).run()
    C0 = _clean(at)
    assert not any(STALE in w.value for w in at.warning)
    crit = C0["R"]["cascade"][0]["criterion"]                  # VA-11: one 'the'
    assert "(the file's Import as SMS minimum)" in crit and "the the" not in crit
    _by_key(at.number_input, "gw_sm_").set_value(16.0).run()
    assert any(STALE in w.value for w in at.warning)
    at.button(key="work_save").click().run()
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert at.session_state["grower"][at.session_state["active"]]["std_moisture"] == 16.0
    assert any(STALE in w.value for w in at.warning)
    # an older cleaning flagged in the saved work: its line in the 'Opened ...' message, gone after a new cleaning
    t, wd = at.session_state["active"], at.session_state["workdir"]
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    rec["cleaned"][t]["clean_again"] = "made by an older version (synthetic): clean it again"
    json.dump(rec, open(p, "w", encoding="utf-8"))
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and f"- {t}: made by an older version (synthetic)" in text
    _clean(at)
    kind, text = at.session_state["work_msg"]
    assert kind == "ok" and "synthetic" not in text and not any(STALE in w.value for w in at.warning)
    # AF-3: the sidebar drawn by the run of the cleaning already shows the message as the cleaning left it
    assert not any("synthetic" in w.value for w in at.sidebar.warning)
    assert any(s.value.startswith("Opened ") for s in at.sidebar.success)


def test_a_lost_boundary_stays_said_after_a_new_cleaning(field, tmp_path, monkeypatch):
    """RA-4: an opened work whose boundary file is gone says so; cleaning the file again (now without its boundary,
    no clip) does not turn that line into a plain 'opened': only the lines a cleaning answers go."""
    bnd = str(tmp_path / "bnd" / "Synthetic_boundary.geojson")
    os.makedirs(os.path.dirname(bnd))
    shutil.copy(field["boundary"], bnd)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.text_input, "bnd_path_").input(bnd)
    _by_key(at.button, "bnd_use_").click().run()
    assert _clean(at)["boundary"]
    at.button(key="work_save").click().run()
    os.rename(bnd, bnd + ".gone")
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    t = at.session_state["active"]
    line = f"- {t}: the boundary {bnd} could not be read"
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text
    assert not _clean(at).get("boundary")
    cap = next(c.value for c in at.caption if "Flagged = " in c.value)            # RA-2: a harvest file
    assert "for a harvest file every reading inside the boundary" in cap and "planter" not in cap
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text
    assert any(line in w.value for w in at.sidebar.warning)


def test_a_file_extracted_by_an_older_version_is_said(tmp_path, monkeypatch):
    """AF-1 / AF-2: a saved work whose raw file was decoded by an older version of OCED (its decode report lacks what
    every decode of the format now carries: Gen4 logs, the points mode) says so when opened, and still after a new
    cleaning (the readings and their import stay the old ones); its import panel says that importing again re-imports
    those readings; the monitor's format is not offered (it would not match the clean file), ISOXML is."""
    from tests import synthetic_jdl as SJ
    card = SJ.make_card(str(tmp_path / "jdl"))["root"]
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    at.toggle(key="t_speed").set_value(False).run()          # the synthetic logs drive at one speed
    at.toggle(key="t_moist").set_value(False).run()
    _clean(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    bs = {b.key[len("nw_go_"):].rsplit("_", 1)[0]: b for b in at.button if str(b.key or "").startswith("nw_go_")}
    assert not bs["jd_jdl"].disabled and bs["isoxml"].disabled
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    rec["datasets"][t]["report"].pop("points")
    json.dump(rec, open(p, "w", encoding="utf-8"))
    [rp] = glob.glob(os.path.join(wd, "decoded", "*_decode_report.json"))
    rep = json.load(open(rp, encoding="utf-8"))
    rep.pop("points")
    json.dump(rep, open(rp, "w", encoding="utf-8"))
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    line = f"- {t}: extracted by an older version of OCED"
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text
    assert any("extracted by an older version of OCED: importing it again" in c.value for c in at.caption)
    bs = {b.key[len("nw_go_"):].rsplit("_", 1)[0]: b for b in at.button if str(b.key or "").startswith("nw_go_")}
    assert bs["jd_jdl"].disabled and not bs["isoxml"].disabled
    _clean(at)
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text
    assert any(line in w.value for w in at.sidebar.warning)


def test_an_old_greenstar_work_without_its_decode_report_file(tmp_path, monkeypatch):
    """R4E-1: a GreenStar 3 work saved by the first published version (its report without 'alignment', its source
    without 'unit_ids') whose decode report JSON is gone: the page says 'extracted by an older version' AND the card
    format stays unavailable with that reason (the buttons read the report the work keeps, as the message does)."""
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    card = gs3_card(str(tmp_path / "gs3"))["root"]
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    at.toggle(key="t_speed").set_value(False).run()
    at.toggle(key="t_moist").set_value(False).run()
    _clean(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    rec["datasets"][t]["report"].pop("alignment")
    rec["datasets"][t]["source"].pop("unit_ids")
    json.dump(rec, open(p, "w", encoding="utf-8"))
    [rp] = glob.glob(os.path.join(wd, "decoded", "*_decode_report.json"))
    os.replace(rp, os.path.join(str(tmp_path), "moved_away.json"))
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and f"- {t}: extracted by an older version of OCED" in text
    bs = {b.key[len("nw_go_"):].rsplit("_", 1)[0]: b for b in at.button if str(b.key or "").startswith("nw_go_")}
    assert bs["jd_gs3_rcd"].disabled and not bs["isoxml"].disabled
    assert any("extracted by an older version of OCED" in c.value and "not available" in c.value for c in at.caption)


OLD_IMPORT_KEYS = ("resolved", "settings", "left_out", "n_all", "n_in", "all_readings", "changed", "notes")


def _old_style_import(p, t, **resolved):
    """The work's import record of `t` as the first published version kept it (no sources, no format), with
    `resolved` replacing values."""
    rec = json.load(open(p, encoding="utf-8"))
    IM = rec["datasets"][t]["sms_import"]
    IM = {k: v for k, v in IM.items() if k in OLD_IMPORT_KEYS}
    IM["resolved"] = {**IM["resolved"], **resolved}
    rec["datasets"][t]["sms_import"] = IM
    json.dump(rec, open(p, "w", encoding="utf-8"))


def test_an_export_imported_by_an_older_version_is_said(tmp_path, monkeypatch):
    """C-2: an Operations Center export (crop in its Deere metadata) saved by the first published version, which did
    not read that crop (product unknown, 5-300 bu/ac): opening the work says it was imported by an older version and
    how this version imports it, also after a new cleaning; an export whose import would be the same is not said."""
    F = make_field(str(tmp_path / "ops"))
    stem = os.path.splitext(F["shp"])[0]
    json.dump({"CropName": "Wheat (Hard Red Spring)", "CropId": 25},
              open(stem + "-Deere-Metadata.json", "w", encoding="utf-8"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, F["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    IM = at.session_state["datasets"][t]["sms_import"]
    assert IM["fmt"] == "jd_ops_center" and IM["resolved"]["max_yield"] == 10_000.0
    _clean(at)
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    _old_style_import(p, t, product=None, test_weight_lb_bu=None, dry_moisture_pct=None, max_yield=300.0)
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    line = f"- {t}: imported by an older version of OCED (product unknown"
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text and "10,000 bu/ac" in text, text
    _clean(at)
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and line in text
    assert any(line in w.value for w in at.sidebar.warning)
    # the same import recorded without its sources, values as this version gives them: nothing to say
    at.button(key="work_save").click().run()
    _old_style_import(p, t, **{k: IM["resolved"][k] for k in ("product", "test_weight_lb_bu", "dry_moisture_pct",
                                                                "min_yield", "max_yield")})
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert "imported by an older version" not in at.session_state["work_msg"][1]


def test_import_again_of_an_export_imported_by_an_older_version(tmp_path, monkeypatch):
    """C-2: 'Import this file again' on an Operations Center export whose import the first published version recorded
    (product unknown, 5-300 bu/ac). The panel shows the values a fresh open gives (also after another product is
    chosen), so with nothing typed the file gets the fresh open's import (no value labelled 'you', the readings above
    300 bu/ac kept) and the older-version line goes; a value typed in the panel is the user's ('you')."""
    from engine import sms_import as si
    F = make_field(str(tmp_path / "ops"))
    g = pyogrio.read_dataframe(F["shp"])
    ok = g.index[(g["Yld_Vol_Dr"].between(40, 120)) & (g["Moisture__"] < 20) & (g["Speed_mph_"] < 6)][:25]
    k = 450.0 / g.loc[ok, "Yld_Vol_Dr"]                  # above an old 300 bu/ac maximum, below 10,000
    for c in ("Yld_Vol_Dr", "Yld_Vol_We", "Yld_Mass_W", "Yld_Mass_D"):
        g.loc[ok, c] = g.loc[ok, c] * k
    pyogrio.write_dataframe(g, F["shp"])
    stem = os.path.splitext(F["shp"])[0]
    json.dump({"CropName": "Wheat (Hard Red Spring)", "CropId": 25},
              open(stem + "-Deere-Metadata.json", "w", encoding="utf-8"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, F["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    D = at.session_state["datasets"][t]
    n_fresh, R_fresh = D["n"], dict(D["sms_import"]["resolved"])
    assert R_fresh["max_yield"] == 10_000.0 and R_fresh["product"] == "wheat"
    shown = ("product", "test_weight_lb_bu", "dry_moisture_pct", "min_yield", "max_yield")
    p = os.path.join(wd, "oced_work.json")
    line = f"- {t}: imported by an older version of OCED"

    def reopen_old():
        at.button(key="work_save").click().run()
        _old_style_import(p, t, product=None, test_weight_lb_bu=None, dry_moisture_pct=None, max_yield=300.0)
        at.button(key="start_over").click().run()
        at.button(key="work_open").click().run()
        assert not at.exception, at.exception
        assert line in at.session_state["work_msg"][1]

    reopen_old()
    assert _by_key(at.selectbox, "fi_prod_").value == "wheat"
    assert _by_key(at.number_input, "fi_max_").value == 10_000.0
    assert _by_key(at.number_input, "fi_tw_").value == 60.0
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    D = at.session_state["datasets"][t]
    IM = D["sms_import"]
    assert {k: IM["resolved"][k] for k in shown} == {k: R_fresh[k] for k in shown}
    assert si.SRC_YOU not in IM["sources"].values(), IM["sources"]
    assert D["n"] == n_fresh
    assert line not in at.session_state["work_msg"][1]
    # another product: the panel gives what this version gives that product for this export (max 10,000)
    reopen_old()
    _by_key(at.selectbox, "fi_prod_").select("barley").run()
    assert _by_key(at.number_input, "fi_max_").value == 10_000.0
    # a value typed in the panel is the user's: labelled 'you'
    reopen_old()
    _by_key(at.number_input, "fi_max_").set_value(300.0).run()
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    IM = at.session_state["datasets"][t]["sms_import"]
    assert IM["resolved"]["max_yield"] == 300.0 and IM["sources"]["max_yield"] == si.SRC_YOU
    assert at.session_state["datasets"][t]["n"] == n_fresh - len(ok)
    assert line not in at.session_state["work_msg"][1]


def _extract(at):
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception


def test_old_decode_of_several_files_is_one_line(tmp_path, monkeypatch):
    """E2E-11 (c): a work of several files extracted by an older version says so in one line naming them, not once
    per file."""
    from tests import synthetic_jdl as SJ
    card = SJ.make_card(str(tmp_path / "jdl"))["root"]
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    _extract(at)
    at.run()
    t, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    rec["datasets"][t]["report"].pop("points")
    rec["datasets"]["Second_file"] = json.loads(json.dumps(rec["datasets"][t]))
    rec["datasets"]["Second_file"]["tag"] = "Second_file"
    json.dump(rec, open(p, "w", encoding="utf-8"))
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    kind, text = at.session_state["work_msg"]
    assert kind == "warning" and text.count("extracted by an older version of OCED") == 1, text
    assert "their readings and imports are not the current ones" in text and "its readings" not in text, text
    assert f"- 2 files ({', '.join(sorted([t, 'Second_file'], key=list(rec['datasets']).index))}): extracted" in text


def test_step_one_texts_say_where_the_values_come_from(tmp_path, monkeypatch):
    """E2E-2 / E2E-3: the step-1 weight to volume and dry moisture name where each John Deere source's values come
    from (not 'the file's' for every John Deere file), and the path box does not promise 'nothing is copied'."""
    at = _app(tmp_path / "ws", monkeypatch)
    assert "nothing is copied" not in str(at.text_input(key="path_in").placeholder)
    at.selectbox(key="si_prod").set_value("wheat").run()
    tw, dm = at.number_input(key="si_tw"), at.number_input(key="si_dm")
    assert "the file's" not in str(tw.placeholder) and "the file's" not in str(dm.placeholder)
    assert "Gen4 logs and Operations Center exports: SMS's value for the file's crop" in str(tw.help)


def test_the_sidebar_holds_the_work_in_the_run_of_the_extract_click(tmp_path, monkeypatch):
    """E2E-12: in the run of the Extract click the sidebar already holds the new work (its name and Save, and the
    saved works list), and the extraction's account stays on the page."""
    from tests import synthetic_jdl as SJ
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at)
    assert at.text_input(key="work_name").value and at.button(key="work_save")
    assert any(str(o).startswith(str(at.text_input(key="work_name").value))
               for o in at.selectbox(key="work_pick").options)
    assert any(str(s.label).startswith("Extracted 1 file(s)") for s in at.status)


def test_no_decoder_validation_note_is_shown(tmp_path, monkeypatch):
    """E2E-10: a Gen4 file's page shows no note of the decoder's validation on other fields; the decode report
    carries no list of open differences either."""
    from tests import synthetic_jdl as SJ
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at)
    at.run()
    caps = [c.value for c in at.caption]
    assert not any("Known open differences" in c or "validation on other fields" in c or "Open residuals" in c
                   or "points='sms'" in c for c in caps), caps


def test_the_decoder_warnings_are_shown_once(tmp_path, monkeypatch):
    """E2E-11 (b): the decoder's warnings are shown in step 2 ('What the decoder reported'), not again in step 3."""
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, gs3_card(str(tmp_path / "gs3"))["root"])
    _extract(at)
    at.toggle(key="t_speed").set_value(False).run()
    at.toggle(key="t_moist").set_value(False).run()
    _clean(at)
    rep_w = at.session_state["datasets"][at.session_state["active"]]["report"]["warnings"]
    assert rep_w
    assert not any(w.value.startswith("decoder: ") for w in at.warning), [w.value for w in at.warning]
    assert all(sum(w.value == x for w in at.warning) == 1 for x in rep_w)


def test_apply_factors_follows_each_cleaning(tmp_path, monkeypatch):
    """R4 / VA-6: 'Apply the factors of step 3' is keyed by the cleaning it belongs to: after a first cleaning
    without a factor (off, disabled) and a second one that applies a combine factor, it is on (its default)."""
    two = make_two_combines(str(tmp_path / "two"), bias_b=1.15)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, two["shp"])
    _clean(at)
    ap = _by_key(at.checkbox, "nw_f_")
    assert ap.value is False and ap.disabled
    _by_key(at.toggle, "cf_on_").set_value(True).run()
    _by_key(at.number_input, "cf_max_").set_value(20.0).run()
    C = _clean(at)
    assert any(abs(float(v) - 1) > 1e-6 for v in C["R"]["machines"]["factor_applied"].values())
    ap = _by_key(at.checkbox, "nw_f_")
    assert ap.value is True and not ap.disabled


def test_a_lock_of_a_gone_process_does_not_block(field, tmp_path, monkeypatch):
    """R5: a cleaning lock whose process is gone (a closed window, a crash) is stale: the next cleaning runs; a lock
    of this server (another tab cleaning now) still refuses, with its message."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _clean(at)
    lock = os.path.join(at.session_state["workdir"], "clean", at.session_state["active"], ".oced_cleaning.lock")
    with open(lock, "w") as fh:
        fh.write("999999 20260101000000000000")
    _clean(at)
    assert not os.path.exists(lock)
    with open(lock, "w") as fh:
        fh.write(f"{os.getpid()}")                              # this server (the app runs in this process): a tab
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert any("is being cleaned in another tab" in e.value for e in at.error)
    os.remove(lock)


def test_a_library_value_error_keeps_its_traceback():
    """R7 / RA-1: a ValueError raised by a 'raise' of OCED's own code is a plain message; one raised inside a library
    or by an operation OCED's code made (numpy arrays of two lengths, int(NaN), max([]) ..., which raise from C with
    OCED's line as their last frame) is a defect and keeps its traceback (st.exception)."""
    [raised] = _app_function("raised_by_oced", os=os, ROOT=ROOT)

    def ours():
        raise ValueError("a plain reason")
    try:
        ours()
    except ValueError as e:
        mine = e
    assert not raised(mine)          # this test file is not app/ or engine/
    # functions compiled as if they were in engine/: an explicit raise is OCED's, an operation's error is not
    code = ("import numpy as np\n"
            "def plain():\n    raise ValueError('x')\n"
            "def plain_lines():\n    raise ValueError(\n        'a reason '\n        'on two lines')\n"
            "def wrapped():\n    try:\n        broadcast()\n    except ValueError as e:\n"
            "        raise ValueError('a plain reason') from e\n"
            "def broadcast():\n    return np.zeros(3) + np.zeros(4)\n"
            "def int_nan():\n    return int(float('nan'))\n"
            "def max_empty():\n    return max([])\n"
            "def unpack():\n    a, b = [1, 2, 3]\n"
            "def index():\n    return [1].index(5)\n"
            "def reraised():\n    try:\n        broadcast()\n    except ValueError:\n        raise\n")
    ns = {}
    exec(compile(code, os.path.join(ROOT, "engine", "x.py"), "exec"), ns)
    got = {}
    for name in ("plain", "plain_lines", "wrapped", "broadcast", "int_nan", "max_empty", "unpack", "index", "reraised"):
        try:
            ns[name]()
        except ValueError as e:
            got[name] = raised(e)
    assert got == {"plain": True, "plain_lines": True, "wrapped": True, "broadcast": False, "int_nan": False,
                   "max_empty": False, "unpack": False, "index": False, "reraised": False}


# ------------------------------------------------------------------------------------------------ steps 1 and 2
def test_an_import_that_leaves_no_reading(field, tmp_path, monkeypatch):
    """VA-2: every yield below the min. yield volume: step 2 says so, offers the import settings, and does not crash
    (it crashed drawing an empty map)."""
    g = pyogrio.read_dataframe(field["shp"])
    for c in [c for c in g.columns if c.startswith(("Yld_Vol", "Yld_Mass"))]:
        g[c] = 0.5
    low = str(tmp_path / "low" / "Synthetic_low.shp")
    os.makedirs(os.path.dirname(low))
    g.to_file(low, engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, low)
    assert any("The import left no reading" in w.value for w in at.warning)
    assert not [b for b in at.button if b.key == "clean_one"]


def test_isoxml_input_message(tmp_path, monkeypatch):
    """VA-8: ISOXML task data is named as found, without the contradicting 'empty zip or folder?'."""
    zp = str(tmp_path / "Task data.zip")
    with zipfile.ZipFile(zp, "w") as z:
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zi:
            zi.writestr("TASKDATA/TASKDATA.XML", b"<ISO11783_TaskData/>")
            zi.writestr("TASKDATA/TLG00001.XML", b"<TIM/>")
            zi.writestr("TASKDATA/TLG00001.BIN", b"\x00" * 32)
        z.writestr("TASKDATA-0000000000-200001010000.zip", inner.getvalue())
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, zp)
    err = str(at.session_state["open_error"])
    assert err.startswith("ISOXML task data was found") and "empty zip or folder" not in err


def test_reimport_reaches_the_writer_options(tmp_path, monkeypatch):
    """R6: 'Import this file again' with another weight to volume also sets the decode options the writer of the
    monitor's format decodes the card with, so its totals are on the clean file's weight (the dry totals of the
    written card and the clean file then differ as their wet ones do)."""
    from tests.synthetic_cn1 import make_card
    card = make_card(str(tmp_path / "cnh_in"))["card"]
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    # VA-5: a Case IH card's SMS Summary is the display's totals (the caption): the readings' average is not 'SMS'
    labels = [m.label for m in at.metric]
    assert "Average dry yield of the readings" in labels and "Average dry yield (SMS)" not in labels
    t = at.session_state["active"]
    tw0 = float(at.session_state["datasets"][t]["sms_import"]["resolved"]["test_weight_lb_bu"])
    _by_key(at.number_input, "fi_tw_").set_value(round(tw0 * 1.10, 2)).run()
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    D = at.session_state["datasets"][t]
    tw1 = float(D["sms_import"]["resolved"]["test_weight_lb_bu"])
    assert tw1 == pytest.approx(tw0 * 1.10, abs=0.01)
    assert D["source"]["options"]["test_weight_lb_bu"] == pytest.approx(tw1)
    assert D["source"]["options"]["std_moisture_pct"] == pytest.approx(D["sms_import"]["resolved"]["dry_moisture_pct"])
    # RA-5: the report's source paragraph (the calibration summary) gives the new weight and moisture too
    cs = D["source"]["calibration_summary"]
    dm1 = float(D["sms_import"]["resolved"]["dry_moisture_pct"])
    assert f"test weight {round(tw1, 4):g} lb/bu" in cs and cs.count("test weight") == 1, cs
    assert f"standard moisture {round(dm1, 4):g} %" in cs and cs.count("standard moisture") == 1, cs
    _clean(at)
    _by_key(at.button, "nw_go_cnh_cn1_").click().run()
    assert not at.exception, at.exception
    rec = json.load(open(glob.glob(os.path.join(at.session_state["workdir"], "native", "*", "cnh_cn1.json"))[0],
                         encoding="utf-8"))
    rows = {r[""]: r for r in rec["totals"]}
    cl, ex = rows["the clean file"], rows["what the SMS Summary should show"]
    assert ex["dry (bu)"] / cl["dry (bu)"] == pytest.approx(ex["wet (lb)"] / cl["wet (lb)"], rel=0.01)
    assert not any("dry +" in w for w in rec["warnings"])


# ------------------------------------------------------------------------------------------------ step 4
def test_readings_below_the_minimum_once_the_factors_apply(field, tmp_path, monkeypatch):
    """RA-3: the yields adjusted to a low grower's weight (L about 0.07): most readings written fall below the import's
    5 bu/ac minimum once the factor applies. A writer that does not count them itself (ISOXML here, also Gen4 logs and
    Case IH cards) gets the count from the clean file x the factor, and the page says that its totals hold them."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.number_input, "gw_w_").set_value(10.0).run()
    f0 = (_clean(at)["R"].get("level") or {}).get("factor")
    _by_key(at.number_input, "gw_w_").set_value(round(10.0 * 0.07 / float(f0), 4)).run()
    _by_key(at.button_group, "gw_use_").set_value("adjust").run()
    C = _clean(at)
    L = float(C["R"]["level"]["factor"])
    assert L == pytest.approx(0.07, rel=0.01) and _by_key(at.checkbox, "nw_f_").value is True
    _by_key(at.button, "nw_go_isoxml_").click().run()
    assert not at.exception, at.exception
    [p] = glob.glob(os.path.join(at.session_state["workdir"], "native", "*", "isoxml.json"))
    rec = json.load(open(p, encoding="utf-8"))
    fac = rec["options"]["factors"]
    g = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    n = int((g["Yld_Vol_Dr"].astype(float) * g["Machine"].astype(str).map(fac).astype(float) < 5.0).sum())
    assert n > 0 and rec["below_min"] == {"n": n, "min_yield": 5.0, "in_totals": True}
    assert any(c.value.startswith(f"{n:,} of the readings written fall below the minimum yield (5 bu/ac dry) once the "
                                  "factors of step 3 are applied: SMS leaves them out, so its points") for c in at.caption)
    # the ISOXML set is read back by the writer's own reader, not decoded by an OCED decoder
    assert any(c.value.startswith("The writer's own check (read back with the writer's own reader): ")
               for c in at.caption)


@pytest.mark.parametrize("variant", ["logged_widths", "ops_center_columns"])
def test_readings_below_the_minimum_as_the_written_set_reads(variant, tmp_path, monkeypatch):
    """R4A-1 / C-1: the count of readings written below the import's minimum is the count of the written ISOXML set
    read back (dry mass per area / the weight to volume < 5 bu/ac), also when the set keeps the logged widths
    ('Write the clean swath widths' off: a narrowed reading reads its logged, lower yield) and when the dry yield
    column has its Operations Center name (VRYIELDVOL, no Yld_Vol_Dr)."""
    from engine.formats import isoxml_write as IW
    two = make_two_combines(str(tmp_path / "two"))
    shp = two["shp"]
    if variant == "ops_center_columns":
        g = pyogrio.read_dataframe(shp).rename(columns={"Yld_Vol_Dr": "VRYIELDVOL"})
        os.makedirs(tmp_path / "ops")
        shp = str(tmp_path / "ops" / "Synthetic_ops_names.shp")
        g.to_file(shp, engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, shp)
    t = at.session_state["active"]
    _by_key(at.number_input, "gw_w_").set_value(10.0).run()
    f0 = (_clean(at)["R"].get("level") or {}).get("factor")
    _by_key(at.number_input, "gw_w_").set_value(round(10.0 * 0.09 / float(f0), 4)).run()
    _by_key(at.button_group, "gw_use_").set_value("adjust").run()
    C = _clean(at)
    cols = list(pyogrio.read_info(C["shp"])["fields"])
    if variant == "logged_widths":
        g = pyogrio.read_dataframe(C["shp"], read_geometry=False)
        assert (g["Swath_Scl"].astype(float) > 1.0001).sum() > 0                  # some readings were narrowed
        _by_key(at.checkbox, "nw_w_").set_value(False).run()
    else:
        assert "VRYIELDVOL" in cols and "Yld_Vol_Dr" not in cols
    _by_key(at.button, "nw_go_isoxml_").click().run()
    assert not at.exception, at.exception
    [p] = glob.glob(os.path.join(at.session_state["workdir"], "native", "*", "isoxml.json"))
    rec = json.load(open(p, encoding="utf-8"))
    assert rec["options"]["widths"] is (variant != "logged_widths") and rec["options"]["factors"]
    [tdir] = glob.glob(os.path.join(at.session_state["workdir"], "native", "*", "isoxml*", "TASKDATA"))
    tw = float(at.session_state["datasets"][t]["sms_import"]["resolved"]["test_weight_lb_bu"])
    P = IW.read_points(tdir)
    n_read = int((P["dry_lbac"].astype(float) / tw < 5.0).sum())
    assert n_read > 0 and (rec.get("below_min") or {}).get("n") == n_read, (rec.get("below_min"), n_read)
    assert any(c.value.startswith(f"{n_read:,} of the readings written fall below the minimum yield") for c in at.caption)


def _longest(root):
    return max((len(os.path.relpath(os.path.join(d, f), root)) for d, _, fs in os.walk(root) for f in fs), default=0)


def test_native_output_depth_is_what_the_app_checks(tmp_path):
    """VA-3: each writer writes into a short folder (cn1 / gs3 / jdl / isoxml) under native/<tag>/ (the tag once in
    the path), and the depth the app checks before writing (native_depth) is the deepest path the writer creates:
    exact for the Case IH card, the GreenStar 3 card and ISOXML, at most the 16 characters of a time stamp over for
    Gen4 logs (added only when the folder exists already)."""
    from engine import run as er
    from engine.formats import native_write as nw
    from tests import synthetic_jdl as SJ
    from tests.synthetic_cn1 import make_card as cn1_card
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    ns = {"os": os, "re": re, "nw": nw}
    src_ns = open(APP, encoding="utf-8").read()
    for name in ("NATIVE_OUT_NAME", "NATIVE_OUT_KEY", "NATIVE_EXTRA"):
        m = re.search(rf"^{name} = .*?(?=^\S)", src_ns, re.S | re.M)
        exec(m.group(0), ns)
    out_dir = str(tmp_path / "work" / "native" / "TAG")
    _, depth = _app_function("_input_tree_depth", "native_depth", **ns)
    ns = depth.__globals__                                      # the functions' own globals: native_dir set below
    cases = (("cnh_cn1", lambda d: cn1_card(d)["card"]), ("jd_gs3_rcd", lambda d: gs3_card(d)["root"]),
             ("jd_jdl", lambda d: SJ.make_card(d)["root"]))
    for fid, mk in cases:
        d = str(tmp_path / fid)
        card = mk(os.path.join(d, "in"))
        wd = os.path.join(d, "work")
        cand = [c for c in er.open_input([card], wd, log=lambda m: None) if c.get("kind") == "raw"][0]
        dec = er.decode(cand, [u.id for u in er.list_units(cand)], None, wd, log=lambda m: None, tag="TAG")
        out = os.path.join(out_dir, fid)
        kw = {ns["NATIVE_OUT_KEY"].get(fid, "out_name"): ns["NATIVE_OUT_NAME"][fid]}
        res = nw.write(fid, dec["source"], dec["shp"], out, log=lambda m: None, **kw)
        assert os.path.basename(res["path"]) == ns["NATIVE_OUT_NAME"][fid]
        ns["native_dir"] = lambda t, o=out: o
        est = depth("TAG", fid, dec["source"]) - len(os.path.abspath(out)) - 1
        real = _longest(out)
        assert real <= est <= real + (16 if fid == "jd_jdl" else 0), (fid, real, est)
    # ISOXML of a point export: isoxml_<stamp>/TASKDATA/LINKLIST.XML
    F = make_field(str(tmp_path / "exp"))
    out = os.path.join(out_dir, "isoxml")
    src = {"kind": "export", "options": {"test_weight_lb_bu": 60.0, "std_moisture_pct": 13.5}}
    res = nw.write(nw.ISOXML, src, F["shp"], out, log=lambda m: None, isoxml_fallback=True, out_name="isoxml")
    assert re.fullmatch(r"isoxml_\d{14}", os.path.basename(res["path"]))
    ns["native_dir"] = lambda t: out
    assert depth("TAG", nw.ISOXML, src) - len(os.path.abspath(out)) - 1 == _longest(out)


# ------------------------------------------------------------------------------------------------ long paths
def _app_defs(ns, *names):
    """Functions, classes and module-level constants of app/oced.py by name, run into the namespace `ns` (the globals
    they need), without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    nodes = [n for n in tree.body if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names)
             or (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in names)]
    exec(compile(ast.Module(nodes, []), APP, "exec"), ns)
    return ns


def _long_path_ns(workspace=None):
    """The app's long-path checks with their globals; WORKSPACE = `workspace` (default a short folder)."""
    import hashlib
    from engine import run as er
    from engine.clean import applied3s as a3
    ns = {"os": os, "hashlib": hashlib, "shutil": shutil, "er": er, "a3": a3, "LOCK_NAME": ".oced_cleaning.lock",
          "WORKSPACE": os.path.abspath(str(workspace) if workspace else os.sep + "ws"),
          "server_token": lambda: "1 test", "lock_is_stale": lambda p: False}
    return _app_defs(ns, "WIN_PATH_MAX", "PATH_LIMIT", "LONGEST_OUTPUT", "TAG_FLOOR", "WORK_FOLDER_CHARS",
                     "REOPEN_ADVICE", "FileInUse", "PathTooLong", "_too_long", "_long_path_msg", "_new_work_len",
                     "clean_depth", "clean_tag_room", "workspace_room", "workspace_advice", "deep_work_msg",
                     "_held_open", "publish_set", "cleaning_guard")


def _path_of_length(base, n, ch="d"):
    """A path under `base` (not made) whose absolute form is n characters long."""
    d = os.path.abspath(str(base))
    assert n - len(d) >= 2, (len(d), n)
    while len(d) < n:
        r = n - len(d)
        step = r if r <= 41 else min(41, r - 2)          # never leave one character (a separator alone)
        d = os.path.join(d, ch * (step - 1))
    assert len(d) == n
    return d


def _long_paths_on(base) -> bool:
    """Whether this computer opens a path over 259 characters (Windows with long paths turned on, or another
    system): a file at 270 characters is written under `base`."""
    d = _path_of_length(base, 240)
    try:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "x" * 29), "wb") as fh:
            fh.write(b"x")
    except OSError:
        return False
    return True


def _file_at_length(base, n):
    """A file whose absolute path is n characters long (a folder of at most 200, then the name)."""
    d = os.path.abspath(str(base))
    while len(d) < min(200, n - 20):
        d = os.path.join(d, "d" * min(40, max(1, 200 - len(d) - 1)))
    os.makedirs(d, exist_ok=True)
    d0 = os.path.join(d, "")
    p = d0 + "f" * (n - len(d0) - 4) + ".shp"
    assert len(p) == n
    with open(p, "wb") as fh:
        fh.write(b"old")
    return p


@pytest.mark.skipif(os.name != "nt", reason="the 260-character path limit is a Windows behaviour")
def test_a_long_path_is_not_reported_as_a_file_held_open(tmp_path):
    """A previous cleaning's file at 255 characters: the trial rename of the held-open check (name + '.oced_chk')
    would pass the 259 Windows opens. It used to fail, and the file was reported 'open in another program'; the check
    now uses a short name in the same folder, finds the file free and leaves it as it was. Held open, it is still
    reported."""
    ns = _long_path_ns()
    p = _file_at_length(tmp_path / "a", 255)
    assert ns["_held_open"]([p]) is None
    assert open(p, "rb").read() == b"old" and os.listdir(os.path.dirname(p)) == [os.path.basename(p)]
    with open(p, "rb"):
        assert ns["_held_open"]([p]) == p
    assert os.listdir(os.path.dirname(p)) == [os.path.basename(p)]


def test_a_cleaning_whose_report_path_is_too_long_is_refused_before_anything_changes(tmp_path):
    """clean/<tag>/<tag>_sms3s_cleaning_report.pdf over 259 characters (a work saved by 0.2.0 with a long file name
    in a deep workspace): the guard says the path is too long and how to fix it, not that a file is open, and
    creates nothing."""
    ns = _long_path_ns()
    guard = ns["cleaning_guard"]
    base = os.path.abspath(os.path.join(str(tmp_path), "w" * 60, "clean"))
    tag = "T" * ((268 - len(base) - 2 - len(ns["LONGEST_OUTPUT"])) // 2)
    out = os.path.join(base, tag)
    n = len(os.path.join(out, tag + ns["LONGEST_OUTPUT"]))
    assert 260 <= n <= 268
    with pytest.raises(ns["PathTooLong"]) as e:
        with guard(tag, out, []):
            pass
    msg = str(e.value)
    assert f"{n} characters" in msg and "Open the raw data again (step 1)" in msg and "open in another" not in msg
    assert not os.path.exists(out)


@pytest.mark.skipif(os.name != "nt", reason="the 260-character path limit is a Windows behaviour")
def test_publishing_over_a_too_long_path_says_so(tmp_path):
    """The clean shapefile handed out sits at 257 characters, so moving it aside (+ '.bak') passes what Windows
    opens: publish_set says the path is too long (not 'open in another program') and leaves the previous set. LP-6:
    skipped where long paths are turned on (Windows then opens the path and the move succeeds)."""
    if _long_paths_on(tmp_path / "lp"):
        pytest.skip("long paths are turned on here: Windows opens a path over 259 characters")
    ns = _long_path_ns()
    dst = _file_at_length(tmp_path / "b", 257)
    src = str(tmp_path / "src.shp")
    with open(src, "wb") as fh:
        fh.write(b"new")
    with pytest.raises(ns["PathTooLong"]) as e:
        ns["publish_set"](src[:-4], dst[:-4], (".shp",))
    assert "open in another" not in str(e.value) and "characters long" in str(e.value)
    assert open(dst, "rb").read() == b"old"


def test_an_as_applied_cleaning_is_checked_with_its_own_report_name(tmp_path):
    """LP-1: an as-applied cleaning's longest output is <tag>_3s_cleaning_report.pdf (engine/clean/applied3s.py
    REPORT_SUFFIX), 3 characters shorter than a harvest's: at 259 characters it is cleaned (the harvest's name would
    be 262 and is refused), at 260 it is refused with that file's own name and length, and nothing is made."""
    ns = _long_path_ns()
    guard, rs = ns["cleaning_guard"], ns["a3"].REPORT_SUFFIX
    assert rs == "_3s_cleaning_report.pdf"
    tag = "Synthetic_se"
    for n in (259, 260):
        wd = _path_of_length(tmp_path / str(n), n - len(os.path.join(os.sep + "clean", tag, tag + rs)))
        out = os.path.join(wd, "clean", tag)
        stem = os.path.join(wd, "clean_shapefiles", tag + "_3s_clean")
        assert len(os.path.join(out, tag + rs)) == n
        if n == 259:
            with guard(tag, out, [stem], longest=rs):
                assert os.path.isfile(os.path.join(out, ns["LOCK_NAME"]))
            assert os.listdir(out) == []
            with pytest.raises(ns["PathTooLong"], match="262 characters"):
                with guard(tag, out, [stem]):
                    pass
            continue
        with pytest.raises(ns["PathTooLong"]) as e:
            with guard(tag, out, [stem], longest=rs):
                pass
        msg = str(e.value)
        assert f"{tag}_3s_cleaning_report.pdf" in msg and "260 characters" in msg and "sms3s" not in msg
        assert not os.path.exists(out)


def test_app_cleans_an_as_applied_file_by_its_own_report_name(tmp_path, monkeypatch):
    """LP-1 through the app: a planter file in a work folder of 203 characters, its report at 258 characters (the
    harvest report's name would make it 261): no step-1 warning, cleaned twice without an error."""
    A = make_applied(str(tmp_path / "data"), "seeding")
    name = os.path.splitext(os.path.basename(A["shp"]))[0][:20]
    at = _app(_path_of_length(tmp_path / "ws", 203 - 1 - 16 - len(name), "w"), monkeypatch)
    _open(at, A["shp"])
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    rep = os.path.join(wd, "clean", tag, tag + "_3s_cleaning_report.pdf")
    assert len(wd) == 203 and len(tag) == 12 and len(rep) == 258
    assert not any("Windows opens" in w.value for w in at.warning)
    for _ in range(2):
        C = _clean(at)
        assert C["kind"] == "a3" and C["report_pdf"] == rep and os.path.isfile(rep)


def test_a_workspace_too_deep_says_so_and_how_to_move_it(tmp_path, monkeypatch):
    """LP-2: when the workspace folder itself is too deep (a new work there, its tag at the floor of tag_budget, would
    pass 259 characters as well), the refusal says so, gives the most characters a workspace may have and how to
    move it (the environment variable OCED_WORKSPACE, read when OCED starts; else OCED installed closer to the drive's
    root), and does not advise opening the raw data again; step 1 says the same before anything is cleaned. A work
    folder deeper than a new one would be (an older version's long names) still gets 'open the raw data again'."""
    ns0 = _long_path_ns()
    room = ns0["workspace_room"]()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert room == 162 and f"at most {room} characters" in readme
    reopen = ns0["REOPEN_ADVICE"]
    ws = _path_of_length(tmp_path / "ws", 200, "w")
    ns = _long_path_ns(ws)
    wd = os.path.join(ws, "20261111-120000_Synthetic_export")
    tag = "Synthetic_ex"                                         # 12 characters: the floor of tag_budget
    out = os.path.join(wd, "clean", tag)
    for env in (str(ws), None):
        if env:
            monkeypatch.setenv("OCED_WORKSPACE", env)
        else:
            monkeypatch.delenv("OCED_WORKSPACE", raising=False)
        with pytest.raises(ns["PathTooLong"]) as e:
            with ns["cleaning_guard"](tag, out, [os.path.join(wd, "clean_shapefiles", tag + "_sms3s_clean")]):
                pass
        msg = str(e.value)
        assert reopen not in msg and f"The workspace folder {ws} is 200 characters long" in msg
        assert f"at most {room} characters" in msg and "setx OCED_WORKSPACE" in msg and "run_oced.bat" in msg
        assert ("set by the environment variable OCED_WORKSPACE" in msg) == bool(env)
        assert ("install OCED in a folder closer to the drive's root" in msg) == (not env)
        warn = ns["deep_work_msg"](wd)
        assert "Windows opens a path of at most 259 characters" in warn and reopen not in warn
        assert "setx OCED_WORKSPACE" in warn
    assert not os.path.exists(out)
    # a deep work folder in a short workspace: a new work would fit, so opening the raw data again is the advice
    ns = _long_path_ns(tmp_path / "short")
    old = os.path.join(_path_of_length(tmp_path / "old", 200), "x" * 40)
    with pytest.raises(ns["PathTooLong"]) as e:
        with ns["cleaning_guard"](tag, os.path.join(old, "clean", tag), []):
            pass
    assert reopen in str(e.value) and "OCED_WORKSPACE" not in str(e.value)
    assert reopen in ns["deep_work_msg"](old)
    assert ns["deep_work_msg"](os.path.join(str(tmp_path / "short"), "20261111-120000_Synthetic_export")) == ""


def test_app_warns_in_step_1_about_a_workspace_too_deep(tmp_path, monkeypatch):
    """LP-2 through the app: data opened into a workspace of 185 characters gets the warning in step 1, and the
    cleaning is refused with the workspace's advice, not with 'open the raw data again'."""
    F = make_field(str(tmp_path / "data"))
    ws = _path_of_length(tmp_path / "ws", 185, "w")
    at = _app(ws, monkeypatch)
    _open(at, F["shp"])
    warn = [w.value for w in at.warning if "Windows opens" in w.value]
    assert len(warn) == 1 and "setx OCED_WORKSPACE" in warn[0] and f"The workspace folder {ws}" in warn[0]
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    err = [e.value for e in at.error if "nothing was changed" in e.value]
    assert err and "setx OCED_WORKSPACE" in err[0] and "Open the raw data again (step 1): a new" not in err[0]
    assert not at.session_state["cleaned"]


def test_a_published_set_that_cannot_be_moved_aside_is_refused_before_the_cleaning(tmp_path):
    """LP-3: a tag of one character in a work folder of 221 characters: the report (257) fits, but the clean
    shapefile handed out (256) would be moved aside as .shp.bak at 260 while the new one replaces it. The first
    cleaning (nothing handed out yet) is let through; once a set is handed out, the cleaning is refused before the
    engine runs, with the .bak name and its length, and nothing changes."""
    ws = _path_of_length(tmp_path / "ws", 221 - 1 - 16 - 2, "w")
    ns = _long_path_ns(ws)
    wd = os.path.join(ws, "20261111-120000_A1")
    tag, out = "A", os.path.join(wd, "clean", "A")
    stem = os.path.join(wd, "clean_shapefiles", "A_sms3s_clean")
    assert len(wd) == 221 and len(os.path.join(out, tag + ns["LONGEST_OUTPUT"])) == 257
    with ns["cleaning_guard"](tag, out, [stem]):
        pass
    os.makedirs(os.path.dirname(stem))
    with open(stem + ".shp", "wb") as fh:
        fh.write(b"old")
    assert len(stem + ".shp") == 256
    before = sorted(os.listdir(out))
    with pytest.raises(ns["PathTooLong"]) as e:
        with ns["cleaning_guard"](tag, out, [stem]):
            pass
    msg = str(e.value)
    assert "A_sms3s_clean.shp.bak" in msg and "260 characters" in msg and "not cleaned, nothing was changed" in msg
    assert "setx OCED_WORKSPACE" in msg                          # a new work in this workspace would be as deep
    assert sorted(os.listdir(out)) == before and open(stem + ".shp", "rb").read() == b"old"


@pytest.mark.skipif(os.name != "nt", reason="the 260-character path limit is a Windows behaviour")
def test_a_check_name_too_long_gives_its_own_length(tmp_path):
    """LP-4: a file of 253 characters in a folder of 247: even the short name of the held-open check
    (~<8 hex>.chk) is 261 characters. The refusal gives that path's length (261), not the file's own (253)."""
    if _long_paths_on(tmp_path / "lp"):
        pytest.skip("long paths are turned on here: Windows opens a path over 259 characters")
    ns = _long_path_ns()
    d = _path_of_length(tmp_path / "a", 247)
    os.makedirs(d)
    p = os.path.join(d, "f.shp")
    with open(p, "wb") as fh:
        fh.write(b"old")
    with pytest.raises(ns["PathTooLong"]) as e:
        ns["_held_open"]([p])
    msg = str(e.value)
    assert "261 characters long" in msg and "253 characters" not in msg and ".chk" in msg and "f.shp" in msg
    assert os.listdir(d) == ["f.shp"] and open(p, "rb").read() == b"old"


def test_a_file_the_check_cannot_rename_back_is_named(tmp_path, monkeypatch):
    """LP-5: the held-open check renames a file for a moment; when it cannot be renamed back (twice), the message no
    longer says 'Nothing was changed': it names the file it is left under and its own name, and the lock goes."""
    ns = _long_path_ns()
    tag = "Synthetic_ex"
    out = os.path.join(str(tmp_path), "w", "clean", tag)
    os.makedirs(out)
    p = os.path.join(out, tag + "_sms3s_cleaning.json")
    with open(p, "wb") as fh:
        fh.write(b"old")
    real = os.replace

    def replace(a, b):
        if os.path.abspath(b) == os.path.abspath(p):
            raise PermissionError(13, "held by another program")
        return real(a, b)
    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(ns["FileInUse"]) as e:
        with ns["cleaning_guard"](tag, out, []):
            pass
    monkeypatch.setattr(os, "replace", real)
    msg = str(e.value)
    left = [n for n in os.listdir(out) if n != os.path.basename(p)]
    assert left == [os.path.basename(p) + ".oced_chk"] and not os.path.exists(p)
    assert "Nothing was changed" not in msg and os.path.join(out, left[0]) in msg
    assert f"back to {os.path.basename(p)}" in msg and "did not run" in msg


def test_a_write_too_deep_for_any_work_in_this_workspace_says_how_to_move_it(tmp_path, monkeypatch):
    """LP-2 in step 4: a write in the monitor's format whose deepest file would pass PATH_LIMIT says, when a new work
    in this workspace would be as deep, how to move the workspace (with the most characters this write allows it);
    else it says to open the data again."""
    import types
    monkeypatch.setenv("OCED_WORKSPACE", "set")
    tag = "Synthetic_ex"
    old = os.path.join(_path_of_length(tmp_path / "old", 200), "x" * 33)       # a work folder of an older version
    for ws, wd in ((_path_of_length(tmp_path / "ws", 200, "w"), None), (os.path.abspath(str(tmp_path / "short")), old)):
        wd = wd or os.path.join(ws, "20261111-120000_Synthetic_export")
        ns = {"os": os, "WORKSPACE": ws, "ss": types.SimpleNamespace(datasets={tag: {}}, workdir=wd),
              "writer_source": lambda D: None, "native_factors": lambda C: (None, ""),
              "native_dir": lambda t: os.path.join(wd, "native", t), "native_depth": lambda t, f, s: len(wd) + 40}
        ns = _app_defs(ns, "PATH_LIMIT", "WIN_PATH_MAX", "LONGEST_OUTPUT", "TAG_FLOOR", "WORK_FOLDER_CHARS",
                       "_new_work_len", "workspace_room", "workspace_advice", "tag_budget_for", "native_room",
                       "native_too_deep_msg", "write_native")
        with pytest.raises(ValueError) as e:
            ns["write_native"](tag, {}, "cnh_cn1", {})
        msg = str(e.value)
        assert f"the deepest file would be {len(wd) + 40} characters long" in msg
        if wd.startswith(ws):
            assert "setx OCED_WORKSPACE" in msg
            assert f"this write needs a workspace folder of at most {250 - 40 - 37} characters" in msg
        else:
            assert "open the data again (step 1), then clean and write it in the new work" in msg
            assert "OCED_WORKSPACE" not in msg
        assert not os.path.exists(os.path.join(wd, "native"))


def _write_ns(ws, wd, tag, rest):
    """write_native of app/oced.py up to its depth check, WORKSPACE = ws, the work folder wd: native_depth is the work
    folder, the tag and `rest` characters (native/, the writer's folder and the card's own tree); a write that passes
    the check stops at native_set_aside, raising the class returned."""
    import types

    class Reached(Exception):
        pass

    def stop(*a, **k):
        raise Reached

    ns = {"os": os, "WORKSPACE": ws, "ss": types.SimpleNamespace(datasets={tag: {}}, workdir=wd),
          "writer_source": lambda D: None, "native_factors": lambda C: (None, ""), "native_set_aside": stop,
          "native_dir": lambda t: os.path.join(wd, "native", t), "NATIVE_OUT_KEY": {}, "NATIVE_OUT_NAME": {},
          "native_depth": lambda t, f, s: len(os.path.abspath(wd)) + len(t) + rest}
    ns = _app_defs(ns, "PATH_LIMIT", "WIN_PATH_MAX", "LONGEST_OUTPUT", "TAG_FLOOR", "WORK_FOLDER_CHARS",
                   "_new_work_len", "workspace_room", "workspace_advice", "tag_budget_for", "native_room",
                   "native_too_deep_msg", "write_native")
    return ns, Reached


def test_a_write_too_deep_with_a_tag_over_the_floor_gives_a_workspace_that_fits(tmp_path, monkeypatch):
    """LP-2 in step 4, a tag over TAG_FLOOR: tag_budget leaves a file 18 characters in a work folder of 180, so a
    GreenStar 3 write 254 characters deep in a workspace of 143 is as deep in a new work. The refusal says to use a
    shorter workspace (not to open the data again, which gave the same work, tag and depth), of at most 136
    characters: in a workspace of 136 a new work's write fits whatever tag tag_budget gives the file there, in one of
    137 it does not. A work folder deeper than a new one, where the write fits only if a new work keeps the tag the
    file has now, gets 'open the data again' and what to do should the write be refused there too."""
    monkeypatch.setenv("OCED_WORKSPACE", "set")
    tag, rest, name = "Synthetic_export_A", 56, "20261111-120000_Synthetic_export_gs3"
    ws = _path_of_length(tmp_path / "ws", 143, "w")
    wd = os.path.join(ws, name)
    ns, _ = _write_ns(ws, wd, tag, rest)
    assert len(wd) == 180 and len(tag) == 18 == ns["tag_budget_for"](len(wd)) and ns["_new_work_len"](wd) == 180
    with pytest.raises(ValueError) as e:
        ns["write_native"](tag, {}, "jd_gs3_rcd", {})
    msg = str(e.value)
    assert "the deepest file would be 254 characters long" in msg and "open the data again" not in msg
    assert "setx OCED_WORKSPACE" in msg and "this write needs a workspace folder of at most 136 characters" in msg
    assert "characters: the workspace folder" in msg and ": The workspace" not in msg
    assert not os.path.exists(os.path.join(wd, "native"))
    for n, fits in ((136, True), (137, False)):          # a new work there, its tag as long as tag_budget allows
        ws_n = _path_of_length(tmp_path / f"ws{n}", n, "w")
        wd_n = os.path.join(ws_n, name)
        ns_n, reached = _write_ns(ws_n, wd_n, "", rest)
        t_n = (tag + "x" * 60)[:ns_n["tag_budget_for"](len(wd_n))]
        ns_n["ss"].datasets = {t_n: {}}
        with pytest.raises(reached if fits else ValueError):
            ns_n["write_native"](t_n, {}, "jd_gs3_rcd", {})
    # a work folder of 201 (an older version's long name) in a workspace of 140: a new work's folder is 177, where
    # tag_budget gives 19 characters; with rest 55 the write fits there only if the file keeps its 18
    ws = _path_of_length(tmp_path / "ws2", 140, "w")
    wd = os.path.join(ws, "20261111-120000_" + "x" * 44)
    ns, _ = _write_ns(ws, wd, tag, 55)
    assert len(wd) == 201 and ns["_new_work_len"](wd) == 177 and ns["tag_budget_for"](177) == 19
    with pytest.raises(ValueError) as e:
        ns["write_native"](tag, {}, "jd_gs3_rcd", {})
    msg = str(e.value)
    assert "open the data again (step 1), then clean and write it in the new work." in msg
    assert f"a longer name than {tag} (up to 19 characters)" in msg
    assert "at most 138 characters" in msg and "setx OCED_WORKSPACE" in msg
    assert "as deep" not in msg                          # it has just said to open the data again


def test_step_1_warning_counts_the_bak_names_and_the_work_s_own_files(tmp_path):
    """LP-2 in step 1: the longest names said to fit are those a cleaning and a cleaning again fit (the .bak names of
    LP-3 included), as the cleaning guard finds them with a set handed out: in a work folder of 221 no harvest file
    (a 1-character one's .shp.bak would be 260) and an as-applied file of at most 2 characters (3: its shapefile for
    DIFM, <tag>_3s_clean_DIFM.zip, would be 260).
    A work whose own files can be cleaned gets no warning, one that holds a file that cannot names it. Before anything
    is extracted, a work folder of 202 (a workspace of 165 and a name of 20) is warned about: a harvest file's report
    (12 characters, the floor of tag_budget) would be 260 and its shapefile for DIFM with the adjusted yield,
    <tag>_sms3s_clean_adjusted_DIFM.zip, 262 (9 characters at most fit it), an as-applied file's report 257."""
    ws = _path_of_length(tmp_path / "ws", 221 - 1 - 16 - 2, "w")
    ns = _long_path_ns(ws)
    wd = os.path.join(ws, "20261111-120000_A1")
    assert len(wd) == 221
    assert (ns["clean_tag_room"](221, True), ns["clean_tag_room"](221, False)) == (0, 2)
    for tag, harvest, ok in (("A", True, False), ("A1", False, True), ("A12", False, False)):
        out = os.path.join(wd, "clean", tag)
        stem = os.path.join(wd, "clean_shapefiles", tag + ("_sms3s_clean" if harvest else "_3s_clean"))
        os.makedirs(os.path.dirname(stem), exist_ok=True)
        for ext in tuple(ns["er"].SHP_EXTS) + (".zip",):
            with open(stem + ext, "wb") as fh:
                fh.write(b"old")
        kw = {"files": [stem + "_DIFM.zip"]} if harvest else {"longest": ns["a3"].REPORT_SUFFIX,
                                                              "files": [stem + "_DIFM.zip"]}
        if ok:
            with ns["cleaning_guard"](tag, out, [stem], **kw):
                pass
        else:
            with pytest.raises(ns["PathTooLong"]):
                with ns["cleaning_guard"](tag, out, [stem], **kw):
                    pass
        assert (ns["clean_depth"](221, len(tag), harvest) <= 259) == ok
    warn = ns["deep_work_msg"](wd)
    assert "This work's folder is 221 characters long" in warn
    assert ("In it no harvest file can be cleaned and cleaned again, and an as-applied file only when its name has at "
            "most 2 characters.") in warn
    assert ns["deep_work_msg"](wd, {"A1": False}) == ""
    warn = ns["deep_work_msg"](wd, {"A1": False, "B": True})
    assert "The file B of this work is longer." in warn
    ws = _path_of_length(tmp_path / "ws165", 165, "w")
    ns = _long_path_ns(ws)
    wd = os.path.join(ws, "20261111-120000_Synthetic_export_gs3")
    assert len(wd) == 202
    warn = ns["deep_work_msg"](wd)
    assert "In it a file can be cleaned and cleaned again only when its name has at most 9 characters (an " \
           "as-applied file: 13)." in warn and "setx OCED_WORKSPACE" in warn
    assert "The file Synthetic_ex of this work is longer." in ns["deep_work_msg"](wd, {"Synthetic_ex": True})
    assert ns["deep_work_msg"](wd, {"Synthetic_ex": False}) == ""


def test_app_warns_in_step_1_about_a_harvest_file_it_cannot_clean(tmp_path, monkeypatch):
    """LP-2 through the app: a harvest export opened into a work folder of 202 characters gets a 12-character name
    (the floor of tag_budget), whose report would be 260 characters: step 1 warns about it by name before anything
    is cleaned, and the cleaning is refused with the same advice."""
    F = make_field(str(tmp_path / "data"))
    name = os.path.splitext(os.path.basename(F["shp"]))[0][:20]
    ws = _path_of_length(tmp_path / "ws", 202 - 1 - 16 - len(name), "w")
    at = _app(ws, monkeypatch)
    _open(at, F["shp"])
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    assert len(wd) == 202 and len(tag) == 12
    warn = [w.value for w in at.warning if "Windows opens" in w.value]
    assert len(warn) == 1 and f"The file {tag} of this work is longer." in warn[0] and "setx OCED_WORKSPACE" in warn[0]
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    err = [e.value for e in at.error if "nothing was changed" in e.value]
    assert err and "260 characters" in err[0] and "setx OCED_WORKSPACE" in err[0]
    assert not at.session_state["cleaned"]


def test_the_workspace_how_to_says_where_setx_reaches_and_what_stays(tmp_path, monkeypatch):
    """The how-to of a shorter workspace says that setx reaches the programs started after it (OCED started again with
    a double click on run_oced.bat or from a new Command Prompt, not from the one setx was typed in) and that the
    saved works and cn1_card_names.json stay in the old workspace unless moved; README and INSTALAR say the same."""
    ws = os.path.abspath(str(tmp_path / "ws"))
    ns = _long_path_ns(ws)
    for env in (ws, None):
        if env:
            monkeypatch.setenv("OCED_WORKSPACE", env)
        else:
            monkeypatch.delenv("OCED_WORKSPACE", raising=False)
        msg = ns["workspace_advice"]()
        assert "setx reaches the programs started after it, not that Command Prompt" in msg
        assert "a double click on run_oced.bat (or from a new Command Prompt)" in msg
        assert "The saved works and cn1_card_names.json" in msg and f"stay in {ws}: to keep them, move them" in msg
    readme = " ".join(open(os.path.join(ROOT, "README.md"), encoding="utf-8").read().split())
    assert ("start it again with a double click on `run_oced.bat` or from a new Command Prompt (setx does not change "
            "the Command Prompt it is typed in)") in readme
    assert "The saved works and `cn1_card_names.json` (the Case IH card names already given) are read from" in readme
    inst = " ".join(open(os.path.join(ROOT, "INSTALAR.txt"), encoding="utf-8").read().split())
    assert "ou de um Prompt de Comando novo (o setx não muda o Prompt de Comando em que foi digitado)" in inst
    assert "Os trabalhos salvos e o cn1_card_names.json" in inst and "mova-os para a pasta nova" in inst


# ------------------------------------------------------------------------------------------------ card set aside
@pytest.mark.parametrize("fmt", ["cnh_cn1", "jd_gs3_rcd"])
def test_a_write_stopped_half_way_gets_the_earlier_card_back(tmp_path, fmt):
    """A Case IH or GreenStar 3 write that stopped half-way (the app closed) leaves the earlier card set under
    <name>~ (folder and zip) and a half-written <name> folder without its zip (the writers write the zip last). The
    next write puts the earlier set back before it moves it aside, so a write that then fails leaves the earlier card
    whole, its folder and its zip together. A set in place with its zip is whole (a write that finished, whose aside
    could not be removed): then the aside is the stale one and goes."""
    ns = _app_defs({"os": os, "shutil": shutil}, "NATIVE_OUT_NAME", "NATIVE_ASIDE", "NATIVE_REPLACED", "_remove_path",
                   "native_put_back", "native_written_only", "native_set_aside")
    name = ns["NATIVE_OUT_NAME"][fmt]
    card = ("EARLIER.cn1", "a.dat") if fmt == "cnh_cn1" else ("Data", "a.fdd")
    half = ("HALF.cn1", "b.dat") if fmt == "cnh_cn1" else ("Data", "b.fdd")

    def put(folder, parts, text):
        d = os.path.join(folder, parts[0])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, parts[1]), "w") as fh:
            fh.write(text)

    def tree(folder):
        return sorted(os.path.relpath(os.path.join(dp, f), folder) for dp, _, fs in os.walk(folder) for f in fs)

    out = str(tmp_path / "stopped")
    put(os.path.join(out, name + "~"), card, "earlier")
    with open(os.path.join(out, name + "~.zip"), "w") as fh:
        fh.write("earlier zip")
    put(os.path.join(out, name), half, "half")              # no <name>.zip: the write stopped before it
    moved = ns["native_set_aside"](out, fmt)
    assert sorted(p for p, _ in moved) == sorted([os.path.join(out, name), os.path.join(out, name + ".zip")])
    put(os.path.join(out, name), half, "half again")        # the new write fails half-way
    assert ns["native_put_back"](moved) == []
    assert tree(os.path.join(out, name)) == [os.path.join(*card)]
    assert open(os.path.join(out, name + ".zip")).read() == "earlier zip"
    assert sorted(os.listdir(out)) == sorted([name, name + ".zip"])

    out = str(tmp_path / "finished")
    put(os.path.join(out, name + "~"), card, "earlier")
    with open(os.path.join(out, name + "~.zip"), "w") as fh:
        fh.write("earlier zip")
    put(os.path.join(out, name), half, "new")
    with open(os.path.join(out, name + ".zip"), "w") as fh:
        fh.write("new zip")
    moved = ns["native_set_aside"](out, fmt)
    assert ns["native_put_back"](moved) == []
    assert tree(os.path.join(out, name)) == [os.path.join(*half)]
    assert open(os.path.join(out, name + ".zip")).read() == "new zip"
    assert sorted(os.listdir(out)) == sorted([name, name + ".zip"])
