# -*- coding: utf-8 -*-
"""The steps of 0.3.1 through Streamlit's AppTest, on synthetic data only: step 1 shows the raw data with SMS's
default import (no setting there), step 2 the import settings behind the switch 'Use SMS's default settings' (Apply,
back to the default and its dialog, 'None', values equal to the default, Apply to all, failures), step 3 starts
from what step 2 holds, step 4 names the import of each cleaning. An untouched flow gives the numbers it gave before
the steps were laid out again; works saved by 0.3.0 open with their imports, cleanings and outputs; no new file
passes the path limit.

    python -m pytest -q tests/test_app_steps.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import sms_import as si  # noqa: E402
from tests.app_steps import (_apply_import, _apply_to_all, _back_to_default, _badge_lines, _extract_again,  # noqa: E402
                             _first_metric, _last_metric, _set_import, _starts_from, _switch_off, by_key, switch)
from tests.synthetic import make_applied, make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
PATH_LIMIT = 250

# 0.3.0's step-1 panel 'Import as SMS' untouched (its widgets at their start values): what it gave every file
PANEL_030 = {"on": True, "product": None, "test_weight_lb_bu": None, "dry_moisture_pct": None,
             "expand_dry_moisture": False, "use_manual_swath": False, "manual_swath_ft": 15.0,
             "use_manual_moisture": False, "manual_moisture_pct": None, "min_yield": si.AUTO, "max_yield": None,
             "start_delay_s": 0.0, "stop_delay_s": 0.0, "flow_shift_s": 0.0}

# an untouched flow (open or extract, clean, nothing else) on the synthetic data, as the app gave it before its steps
# were laid out again: readings, readings cleaned, kept, removed %, the readings each step removed, the mean and the
# sum of the clean dry yield
UNTOUCHED = {
    "export": (5952, 5952, 5743, 3.511424731, [("S0", 0), ("S1", 0), ("S2", 0), ("S3", 59), ("S4", 57), ("S5a", 90),
                                                ("S5b", 3)], 66.043517, 379287.9208),
    "jdl": (121, 121, 120, 0.826446281, [("S0", 0), ("S1", 0), ("S2", 0), ("S3", 0), ("S4", 0), ("S5a", 1),
                                         ("S5b", 0)], 66.026779, 7923.2135),
    "cnh": (488, 488, 485, 0.614754098, [("S0", 0), ("S1", 0), ("S2", 0), ("S3", 0), ("S4", 0), ("S5a", 3)],
            46.897265, 22745.1737),
    "isoxml": (160, 160, 151, 5.625, [("S0", 0), ("S1", 0), ("S2", 0), ("S3", 0), ("S4", 3), ("S5a", 5),
                                      ("S5b", 1)], 56.106203, 8472.0367),
}


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


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


def _extract(at):
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception


def _clean(at, key="clean_one"):
    at.button(key=key).click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at.session_state["cleaned"].get(at.session_state["active"])


def _D(at, tag=None):
    return at.session_state["datasets"][tag or at.session_state["active"]]


def _files(wd, pattern):
    return glob.glob(os.path.join(wd, "**", pattern), recursive=True)


def _as_saved_by_0_3_0(wd, tag):
    """The saved work as 0.3.0 kept it: one import per file (no default import beside it, no mode)."""
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    for k in ("import_default", "import_mode"):
        rec["datasets"][tag].pop(k, None)
    json.dump(rec, open(p, "w", encoding="utf-8"))
    return rec


def _reopen(at, wd):
    at.button(key="start_over").click().run()
    at.selectbox(key="work_pick").set_value(wd).run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception


# ------------------------------------------------------------------------------------------------ no number changes
def test_sms_default_settings_are_those_of_0_3_0_untouched():
    """Every file opens with si.settings({}): key for key what 0.3.0's untouched step-1 panel gave."""
    assert si.settings({}) == si.settings(PANEL_030) == si.settings(None)


@pytest.mark.parametrize("kind", list(UNTOUCHED))
def test_an_untouched_flow_gives_the_numbers_of_before(kind, tmp_path, monkeypatch):
    """Open (raw data: extract), clean, no setting touched: the readings, the cascade and the clean dry yield are the
    numbers the app gave before its steps were laid out again; the file is on SMS's default import, step 2's switch
    on, and step 3 starts from step 1."""
    from tests import synthetic_cn1 as SC, synthetic_isoxml as SI, synthetic_jdl as SJ
    at = _app(tmp_path / "ws", monkeypatch)
    off = ()
    if kind == "export":
        _open(at, make_field(str(tmp_path / "f"))["shp"])
    elif kind == "jdl":
        _open(at, SJ.make_card(str(tmp_path / "jdl"))["root"])
        off = ("t_speed", "t_moist")                     # the synthetic logs drive at one speed and one moisture
    elif kind == "cnh":
        _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    else:
        a = SI.write_set(str(tmp_path / "iso" / "s1" / "TASKDATA"), SI.harvest(n_pass=4, n=40))["folder"]
        _open(at, os.path.dirname(a))
    if kind != "export":
        _extract(at)
    for k in off:
        at.toggle(key=k).set_value(False).run()
    D = _D(at)
    assert D["import_mode"] == "default" and D["shp"] == D["import_default"]["shp"] and switch(at).value
    assert "step 1" in _starts_from(at).value
    C = _clean(at)
    R = C["R"]
    y = pyogrio.read_dataframe(C["shp"], read_geometry=False)["Yld_Vol_Dr"].astype(float)
    n, n_in, n_kept, pct, cascade, mean, total = UNTOUCHED[kind]
    assert (D["n"], R["n_in"], R["n_kept"]) == (n, n_in, n_kept)
    assert R["removed_pct"] == pytest.approx(pct, abs=1e-8)
    assert [(c.get("filter"), c.get("removed")) for c in R["cascade"]] == cascade
    assert float(y.mean()) == pytest.approx(mean, abs=1e-6) and float(y.sum()) == pytest.approx(total, abs=1e-3)
    assert "mode" not in (R.get("sms_import") or {})          # the default import's record, as before


# ------------------------------------------------------------------------------------------------ R1 / R2
def test_own_settings_leave_step_1_as_it_was(field, tmp_path, monkeypatch):
    """R1: after Apply (max 150) step 1's strip and its file (path, time) are the default import's; step 2 draws its
    own strip against step 1, the 'Your settings' line naming the change, its own map; its settings fold; the switch
    stays off; step 3 starts from step 2; the report names the import as your settings."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t = at.session_state["active"]
    DF = dict(_D(at)["import_default"])
    shp1, mt1, n1 = DF["shp"], os.path.getmtime(DF["shp"]), _first_metric(at, "Readings").value
    assert not [m for m in at.metric if m.proto.delta_description == "vs step 1"]   # nothing applied: one strip
    assert [c.value for c in at.caption if c.value == "The data is as in step 1."]
    _apply_import(at, max=150.0)
    D = _D(at)
    assert D["import_mode"] == "custom" and D["shp"].endswith("_imported_custom.shp")
    assert D["import_default"]["shp"] == shp1 and os.path.getmtime(shp1) == mt1
    assert _first_metric(at, "Readings").value == n1
    r2 = _last_metric(at, "Readings")
    assert r2.proto.delta_description == "vs step 1" and r2.value == f"{D['n']:,}" and D["n"] < int(n1.replace(",", ""))
    assert {m.label for m in at.metric if m.proto.delta_description == "vs step 1"} == {
        "Readings", "Area harvested", "Mean dry yield", "Average dry yield (SMS)", "Total dry bu"}   # 0.3.6: the total
    assert any(b.startswith("Your settings") and "Max. yield volume" in b for b in _badge_lines(at))
    assert by_key(at.button_group, "attr_imp_") is not None and by_key(at.button_group, "attr_raw_") is not None
    assert next(e for e in at.expander if e.label == "Edit the settings").proto.expanded is False
    assert switch(at).value is False
    sf = _starts_from(at)
    assert "Your settings" in sf.value and f"step 2: {D['n']:,} readings" in sf.value
    C = _clean(at)
    assert C["R"]["sms_import"]["mode"] == "custom" and C["R"]["sms_import"]["resolved"]["max_yield"] == 150.0
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["your settings: max. yield volume 150.00"]
    assert any(c.value == f"**{t}**: your settings: max. yield volume 150.00 · {D['n']:,} readings"
               for c in at.sidebar.caption)
    # the report's import line names it
    import pymupdf
    text = " ".join(pg.get_text() for pg in pymupdf.open(C["report_pdf"])).replace("\n", " ")
    assert "Your settings (step 2):" in text


def test_back_to_the_default(field, tmp_path, monkeypatch):
    """The switch back on: at once with no cleaning (the custom import deleted); with a cleaning a dialog asks first:
    'Keep my settings' leaves everything (the switch off again), 'Back to SMS's default' sets the cleaning aside
    (superseded/) and deletes the custom import."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)
    assert _files(wd, f"{t}_imported_custom.shp")
    _back_to_default(at)
    D = _D(at)
    assert D["import_mode"] == "default" and D["shp"] == D["import_default"]["shp"] and switch(at).value
    assert not _files(wd, f"{t}_imported_custom.*")
    assert not [m for m in at.metric if m.proto.delta_description == "vs step 1"]
    # with a cleaning: the dialog
    _apply_import(at, max=150.0)
    _clean(at)
    switch(at).set_value(True).run()
    assert not at.exception, at.exception
    assert by_key(at.button, "fi_backgo_") is not None and by_key(at.button, "fi_backno_") is not None
    assert _D(at)["import_mode"] == "custom" and t in at.session_state["cleaned"]
    by_key(at.button, "fi_backno_").click().run()
    assert not at.exception, at.exception
    assert _D(at)["import_mode"] == "custom" and t in at.session_state["cleaned"] and switch(at).value is False
    assert by_key(at.button, "fi_backgo_") is None
    _back_to_default(at, confirm=True)
    assert _D(at)["import_mode"] == "default" and t not in at.session_state["cleaned"]
    assert not _files(wd, f"{t}_imported_custom.*")
    assert glob.glob(os.path.join(wd, "superseded", "*", f"{t}_sms3s_cleaning.json"))
    assert switch(at).value


def test_values_equal_to_the_default_go_back_to_it(field, tmp_path, monkeypatch):
    """Apply with SMS's own values: the default import again, no custom file; Apply stays disabled while nothing
    differs from what is applied, and 'Not applied' names what differs."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _switch_off(at)
    assert by_key(at.button, "fi_go_").disabled and not any("Not applied:" in c.value for c in at.caption)
    tw0 = float(by_key(at.number_input, "fi_tw_").value)
    _set_import(at, tw=tw0 + 2.0)
    assert any(c.value.startswith(f":orange[Not applied: Weight to volume {tw0:,.2f} → {tw0 + 2:,.2f}")
               for c in at.caption)
    by_key(at.button, "fi_go_").click().run()
    assert _D(at)["import_mode"] == "custom"
    _apply_import(at, tw=tw0)                            # SMS's value again
    D = _D(at)
    assert D["import_mode"] == "default" and D["shp"] == D["import_default"]["shp"]
    assert not _files(wd, f"{t}_imported_custom.*") and not _files(wd, f"{t}_imported_next.*")
    assert any("SMS's default" in s.value for s in at.success)


def test_none_uses_the_export_as_it_is(field, tmp_path, monkeypatch):
    """'None: the file as it is': every point of the export, no import as SMS; step 3 then has its own S0 minimum
    (min_yield), named on the Starts-from line."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, how="none")
    D = _D(at)
    assert D["import_mode"] == "as_is" and D["sms_import"] is None and D["n"] == field["n"]
    assert any(b.startswith("As it is") for b in _badge_lines(at))
    m = at.number_input(key="min_yield")
    assert not m.disabled
    sf = _starts_from(at)
    assert "As it is" in sf.value and f"S0 minimum {float(m.value):,.3f} bu/ac" in sf.value
    assert "Not imported as SMS" in sf.help
    C = _clean(at)
    assert "sms_import" not in C["R"] or not C["R"]["sms_import"]
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["as it is"]


def test_several_files_each_on_its_own_import(field, tmp_path, monkeypatch):
    """Two exports: own settings on A only; 'Clean all' cleans A on them and B on its default; step 4 names each
    import; 'Apply to all' gives B the changed maximum on its own default and sets both cleanings aside."""
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    root = tmp_path / "in"
    for sub, part in (("A", g), ("B", g.iloc[::2])):
        os.makedirs(root / sub)
        part.to_file(str(root / sub / f"Harvest_{sub}.shp"), engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root)
    for i in (0, 1):
        at.selectbox(key="cand_idx").select_index(i).run()
        assert not at.exception, at.exception
    tags = list(at.session_state["datasets"])
    assert len(tags) == 2
    a, b = sorted(tags)
    at.selectbox(key="active_pick").set_value(a).run()
    assert at.session_state["active"] == a
    _apply_import(at, max=150.0)
    assert _D(at, a)["import_mode"] == "custom" and _D(at, b)["import_mode"] == "default"
    _clean(at, key="clean_all")
    Ca, Cb = at.session_state["cleaned"][a], at.session_state["cleaned"][b]
    assert Ca["R"]["sms_import"]["resolved"]["max_yield"] == 150.0 and Cb["R"]["sms_import"]["resolved"]["max_yield"] is None
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert dict(zip(T4["file"], T4["import"])) == {a: "your settings: max. yield volume 150.00", b: "SMS default"}
    _set_import(at, max=120.0)
    assert any(f"Apply to all also sets aside the cleaning of {b}" in c.value for c in at.caption)
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    for t in (a, b):
        D = _D(at, t)
        assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["max_yield"] == 120.0
        assert t not in at.session_state["cleaned"]
    assert _D(at, b)["sms_import"]["resolved"]["product"] == _D(at, b)["import_default"]["sms_import"]["resolved"][
        "product"]


def test_a_planter_file_has_no_import_settings(tmp_path, monkeypatch):
    """A planter file: no switch in step 2 (one line, its '?'), step 3 the 3-sigma of its attributes, step 4 names
    'nothing to import'."""
    A = make_applied(str(tmp_path / "data"), "seeding")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, A["shp"])
    assert switch(at) is None
    cap = next(c for c in at.caption if c.value.startswith("Nothing to import"))
    assert "planter or sprayer" in cap.help
    assert by_key(at.multiselect, "a3_attrs_") is not None
    assert any(b.startswith("As it is") for b in _badge_lines(at))
    _clean(at)
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["nothing to import"]


# ------------------------------------------------------------------------------------------------ saved works
def test_a_moved_work_finds_its_default_and_its_own_settings(field, tmp_path, monkeypatch):
    """A work with own settings, saved, its workspace moved and the work opened again: the default import and the
    custom one are found in the moved folder (nothing rebuilt), the cleaning kept."""
    at = _app(tmp_path / "ws1", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, max=150.0)
    _clean(at)
    at.button(key="work_save").click().run()
    shutil.move(str(tmp_path / "ws1"), str(tmp_path / "ws2"))
    at2 = _app(tmp_path / "ws2", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    D = _D(at2)
    ws2 = str(tmp_path / "ws2")
    assert D["import_mode"] == "custom" and D["shp"].startswith(ws2) and D["import_default"]["shp"].startswith(ws2)
    assert os.path.exists(D["shp"]) and os.path.exists(D["import_default"]["shp"])
    assert not _files(ws2, "*_imported_default.shp")
    assert at2.session_state["active"] in at2.session_state["cleaned"]


def test_a_0_3_0_work_opens_with_its_cleaning_and_outputs(field, tmp_path, monkeypatch):
    """A work saved by 0.3.0 with SMS's default import (one import per file in its record): opened on the default,
    nothing rebuilt, its cleaning and its outputs back in step 4 (the clean shapefile, the report, the DIFM file)."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    C0 = _clean(at)
    at.button(key="work_save").click().run()
    _as_saved_by_0_3_0(wd, t)
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "default" and not D["import_default"].get("older")
    assert D["import_default"]["shp"] == D["shp"] and not _files(wd, "*_imported_default.shp")
    C = at.session_state["cleaned"][t]
    assert C["R"]["n_kept"] == C0["R"]["n_kept"] and os.path.exists(C["shp"]) and os.path.exists(C["report_pdf"])
    labels = {d.label for d in at.get("download_button")}
    assert {"Clean shapefile (.zip)", "Report (PDF)", "Shapefile for DIFM (.zip)"} <= labels
    assert any(b.startswith("SMS default") for b in _badge_lines(at)) and switch(at).value


def test_a_0_3_0_work_imported_again_keeps_its_import(field, tmp_path, monkeypatch):
    """A work saved by 0.3.0 whose file was imported again with own values (0.3.0 wrote that import over the file's
    import): opened on that import (mode custom, its cleaning kept), and SMS's default import is made again from the
    readings for step 1 (<tag>_imported_default); cleaned again, its record names the import as the user's."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)
    C0 = _clean(at)
    at.button(key="work_save").click().run()
    D0 = _D(at)
    own, dflt = os.path.splitext(D0["shp"])[0], os.path.splitext(D0["import_default"]["shp"])[0]
    for p in glob.glob(dflt + ".*"):                     # 0.3.0: one file, the import with the user's values
        os.remove(p)
    for p in glob.glob(own + ".*"):
        os.replace(p, dflt + p[len(own):])
    rec = _as_saved_by_0_3_0(wd, t)
    rec["datasets"][t]["shp"] = os.path.relpath(dflt + ".shp", wd) if not os.path.isabs(rec["datasets"][t]["shp"]) \
        else dflt + ".shp"
    rec["datasets"][t]["sms_import"].pop("mode", None)    # 0.3.0's record names no mode
    json.dump(rec, open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8"))
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["max_yield"] == 150.0
    assert os.path.normcase(D["shp"]) == os.path.normcase(dflt + ".shp")
    assert t in at.session_state["cleaned"] and at.session_state["cleaned"][t]["R"]["n_kept"] == C0["R"]["n_kept"]
    assert D["import_default"]["shp"].endswith("_imported_default.shp") and os.path.exists(D["import_default"]["shp"])
    assert _first_metric(at, "Readings").value == f"{field['n']:,}"            # step 1: SMS's default again
    assert "Your settings" in _starts_from(at).value
    C = _clean(at)                                        # its report names the import as the user's settings
    assert C["R"]["sms_import"]["mode"] == "custom"


def test_a_legacy_folder_and_a_changed_default(field, tmp_path, monkeypatch):
    """A work folder of an earlier version with no saved work (rebuilt from its files): no switch in step 2. A default
    import whose time on disk alone changed is the same import; one whose file was written again since the work was
    saved is made again (<tag>_imported_default); made as it was recorded, its cleaning stays."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _clean(at)
    at.button(key="work_save").click().run()
    shp = _D(at)["import_default"]["shp"]
    _later(shp, 3600)                                     # a copy that did not keep the files' times
    _reopen(at, wd)
    assert _D(at)["shp"] == shp and not _files(wd, f"{t}_imported_default.*")
    g = pyogrio.read_dataframe(shp)                       # the default's file written again since
    g.loc[g.index[0], "Yld_Vol_Dr"] = float(g["Yld_Vol_Dr"].iloc[0]) + 1.0
    g.to_file(shp, engine="pyogrio")
    _later(shp, 7200)
    _reopen(at, wd)
    D = _D(at)
    assert D["import_default"]["shp"].endswith(f"{t}_imported_default.shp") and D["shp"] == D["import_default"]["shp"]
    assert D["n"] == field["n"] and t in at.session_state["cleaned"]    # made again as it was cleaned: kept
    os.remove(os.path.join(wd, "oced_work.json"))         # a folder of an earlier version
    _reopen(at, wd)
    assert switch(at) is None
    assert any(c.value.startswith("This file keeps no record of its import") for c in at.caption)


def _dbf_date(shp, ymd):
    """The date of the last update in a shapefile's .dbf header (bytes 1-3: years since 1900, month, day) set, as a
    file written that day has it."""
    p = os.path.splitext(shp)[0] + ".dbf"
    b = bytearray(open(p, "rb").read())
    b[1:4] = bytes(ymd)
    open(p, "wb").write(bytes(b))


def test_a_default_written_on_another_day_is_the_same_import(field, tmp_path, monkeypatch):
    """An import is known by its content, not by the day its file was written (the .dbf header's date): a default
    whose header date and time on disk changed is the same import (not made again, its cleaning stays), and a default
    made again on another day than its file was written, giving the same content, keeps its cleaning."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    C0 = _clean(at)
    at.button(key="work_save").click().run()
    shp = _D(at)["import_default"]["shp"]
    _dbf_date(shp, (101, 1, 2))                           # as written on another day
    _later(shp, 3600)
    _reopen(at, wd)
    D = _D(at)
    assert os.path.normcase(D["shp"]) == os.path.normcase(shp) and not _files(wd, f"{t}_imported_default.*")
    assert at.session_state["cleaned"][t]["shp"] == C0["shp"]
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    rec["datasets"][t]["import_default"]["mtime"] = 0.0   # a record of an earlier build: its time only, another time
    rec["datasets"][t]["import_default"].pop("sig", None)
    json.dump(rec, open(p, "w", encoding="utf-8"))
    _reopen(at, wd)                                       # made again today from the same readings
    D = _D(at)
    assert D["import_default"]["shp"].endswith(f"{t}_imported_default.shp") and D["shp"] == D["import_default"]["shp"]
    assert at.session_state["cleaned"].get(t, {}).get("shp") == C0["shp"]
    assert not any("set aside" in c.value for c in at.caption)


# ------------------------------------------------------------------------------------------------ failures
def test_a_failed_import_and_a_failed_apply(field, tmp_path, monkeypatch):
    """SMS's import raising at open: the file opens as it is ('Import failed' in step 1, the switch greyed); Apply in
    step 2 tries again and the import becomes the default. An Apply whose import raises leaves the file and its own
    import as they were (no temporary file left)."""
    real = si.apply

    def boom(*a, **k):
        raise OSError("synthetic write failure")
    monkeypatch.setattr(si, "apply", boom)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    D = _D(at)
    assert D["import_mode"] == "as_is" and D["sms_import"] is None and "synthetic write failure" in D["import_default"][
        "error"]
    assert any(b.startswith("Import failed") for b in _badge_lines(at))
    assert switch(at).disabled
    monkeypatch.setattr(si, "apply", real)
    go = by_key(at.button, "fi_go_")
    assert go is not None and not go.disabled
    go.click().run()
    assert not at.exception, at.exception
    D = _D(at)
    assert D["import_mode"] == "default" and D["sms_import"] and not D["import_default"].get("error")
    _apply_import(at, max=150.0)
    D = _D(at)
    shp, n, mt = D["shp"], D["n"], os.path.getmtime(D["shp"])
    monkeypatch.setattr(si, "apply", boom)
    _set_import(at, max=100.0)
    by_key(at.button, "fi_go_").click().run()
    monkeypatch.setattr(si, "apply", real)
    assert not at.exception, at.exception
    assert any("could not be imported with these settings" in e.value for e in at.error)
    D = _D(at)
    assert (D["shp"], D["n"], os.path.getmtime(shp)) == (shp, n, mt) and D["sms_import"]["resolved"]["max_yield"] == 150.0
    assert not _files(at.session_state["workdir"], "*_imported_next.*")


def test_a_card_crop_without_a_weight(tmp_path, monkeypatch):
    """A Case IH unit whose crop has no weight on the card (no crop table, a crop number the decoder does not know):
    extracted with SMS's values for data without a product (56 lb/bu, 13 %), said in a warning; a product chosen in
    step 2 converts the yields from the wet mass and reaches the decode options."""
    from engine.formats import cnh_cn1 as CN
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    for p in glob.glob(os.path.join(cd["card"], "COMBINES", "*", "*.ycs")):
        os.remove(p)
    for p in glob.glob(os.path.join(cd["card"], "**", "*.tso"), recursive=True):
        b = bytearray(open(p, "rb").read())
        b[CN.HDR + 52] = 99
        open(p, "wb").write(bytes(b))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    D = _D(at)
    assert "decoded with SMS's values for data without a product (56 lb/bu, 13 %)" in " ".join(
        D["report"].get("warnings") or [])
    assert any("data without a product" in w.value for w in at.warning)
    assert D["import_mode"] == "default" and D["sms_import"]["resolved"]["test_weight_lb_bu"] is None
    _apply_import(at, prod="wheat")
    D = _D(at)
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["test_weight_lb_bu"] == 60.0
    assert D["sms_import"]["applied"]["weight_and_moisture"]
    assert D["source"]["options"]["crop"] == "wheat" and D["source"]["options"]["test_weight_lb_bu"] == 60.0
    # the decoder's note names the product chosen; the record's totals are on that product, as 0.3.0's decode with
    # the product gave them
    note = " ".join(D["source"]["warnings"])
    assert "choose the product in step 2" not in note and "product wheat chosen in step 2 (60 lb/bu, 13.5 %)" in note
    import dataclasses
    from engine import run as er
    from engine.formats import detect
    cand = next(c for c in detect.detect([cd["card"]]) if c.get("kind") == "raw")
    o = dataclasses.replace(detect.default_options(cand["decoder"]), shrink="one_sided", crop="wheat",
                            test_weight_lb_bu=60.0, std_moisture_pct=13.5)
    d = er.decode(cand, D["source"]["unit_ids"], o, str(tmp_path / "dec"), log=lambda m: None, tag="w",
                  **dict(D["source"].get("decoder_kwargs") or {}))
    for k in ("bu_wet", "bu_dry"):
        assert D["source"]["totals"][k] == pytest.approx(d["report"]["totals"][k], rel=1e-9), k
    if d["source"].get("sms_summary"):
        assert D["source"]["sms_summary"]["dry_bu"] == pytest.approx(d["source"]["sms_summary"]["dry_bu"], rel=1e-9)
    C = _clean(at)
    assert not any("choose the product in step 2" in w for w in C["R"].get("warnings") or [])
    # the card names no crop OCED knows: its Product stays, the Crop column says the product chosen (as 0.3.0)
    g0 = pyogrio.read_dataframe(D["import_default"]["shp"], read_geometry=False)
    g1 = pyogrio.read_dataframe(D["shp"], read_geometry=False)
    assert "Crop" not in g0.columns and set(g1["Crop"]) == {"wheat"} and set(g1["Product"]) == set(g0["Product"])
    assert str(D["source"]["calibration_summary"]).startswith("crop wheat;")


# ------------------------------------------------------------------------------------------------ paths and keys
def test_new_files_stay_within_the_path_limit(tmp_path, monkeypatch):
    """With a workspace 130 characters deep, the imports step 2 writes (own settings, the raw data decoded again as
    the monitor logged it) and the default made again stay within the path limit."""
    from tests import synthetic_jdl as SJ
    pad = 130 - len(str(tmp_path)) - len(os.sep + "OCED_workspace") - 1
    if pad < 4:
        pytest.skip("the temporary folder is already too deep for this test")
    deep = tmp_path / ("d" * pad) / "OCED_workspace"
    at = _app(deep, monkeypatch)
    _open(at, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=80.0)
    assert _files(wd, f"{t}_imported_custom.shp")
    _apply_import(at, how="none")
    assert _D(at)["import_mode"] == "as_is" and _files(os.path.join(wd, "as_logged"), "*.shp")
    longest = max(len(os.path.join(dp, f)) for dp, _, fn in os.walk(wd) for f in fn)
    assert longest <= PATH_LIMIT, longest


def test_steps_1_and_2_on_the_same_file_and_an_extraction_again(field, tmp_path, monkeypatch):
    """An export whose default import changes nothing (its own yields) used as it is: steps 1 and 2 draw the same
    file with keys of their own (no duplicate widget). A raw file extracted again with own settings gets them again."""
    from tests import synthetic_jdl as SJ
    g = pyogrio.read_dataframe(field["shp"])
    v = str(tmp_path / "var" / "Synthetic_variety.shp")
    os.makedirs(os.path.dirname(v))
    g.assign(Product="Variety 7").to_file(v, engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, v)
    _apply_import(at, how="none")
    D = _D(at)
    assert os.path.normcase(D["shp"]) == os.path.normcase(D["import_default"]["shp"])
    assert by_key(at.button_group, "attr_raw_") is not None and by_key(at.button_group, "attr_imp_") is not None
    at2 = _app(tmp_path / "ws2", monkeypatch)
    _open(at2, SJ.make_card(str(tmp_path / "jdl"))["root"])
    _extract(at2)
    _apply_import(at2, max=80.0)
    t = at2.session_state["active"]
    _extract_again(at2)
    D = _D(at2, t)
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["max_yield"] == 80.0
    assert os.path.exists(D["shp"]) and D["shp"].endswith("_imported_custom.shp")


# ------------------------------------------------------------------------------------------------ checks of round 5
NULLABLE = ("tw", "dm", "mm", "min", "max")


def _fields(at):
    return {n: by_key(at.number_input, f"fi_{n}_") for n in NULLABLE}


def _vs(at, step):
    return [m for m in at.metric if m.proto.delta_description == f"vs step {step}"]


def test_an_emptied_field_of_step_2_stays_empty(field, tmp_path, monkeypatch):
    """The fields of step 2 that may be empty (weight to volume, dry moisture, moisture, min and max) have no default
    of their own on any run, so that the browser keeps an emptied field empty (it commits the widget's default),
    not at the field's lowest value; their values stay what they were (the start values, then the applied ones)."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _switch_off(at)
    start = {n: w.value for n, w in _fields(at).items()}
    assert start["tw"] and start["dm"] is not None and start["max"] is None
    for _ in range(2):                                    # the first draw, then after a rerun
        for n, w in _fields(at).items():
            assert not w.proto.HasField("default"), n
            assert n == "min" or w.value == start[n], (n, w.value)
        by_key(at.number_input, "fi_min_").set_value(10.0).run()
        assert not at.exception, at.exception
    _apply_import(at, max=150.0)
    at.run()
    f = _fields(at)
    assert f["max"].value == 150.0 and f["tw"].value == start["tw"]
    assert not any(w.proto.HasField("default") for w in f.values())


def test_step_3_names_the_import_it_starts_from_and_the_dialog_keeps_the_switch_off(field, tmp_path, monkeypatch):
    """Step 3's yield path and Steps table name the import the cleaning started from by its step ('your settings
    (step 2)', never 'raw data'), with no colour written in the page (the brand's classes, light and dark); the
    switch turned on over a cleaned file stays off behind the dialog, step 2 still showing the file's own import."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, min=60.0)
    _clean(at)
    box = [h.proto.body for h in at.get("html") if "oced-path" in h.proto.body]
    assert box and "from your settings (step 2)" in box[0] and "raw data" not in box[0].lower()
    assert "color:" not in box[0]
    T = next(d.value for d in at.dataframe if "mean after" in d.value.columns)
    assert T["step"].iloc[0] == "your settings (step 2)"
    n2 = len(_vs(at, 1))
    assert n2 == 5                                       # 0.3.6: the total in bushels too
    switch(at).set_value(True).run()
    assert not at.exception, at.exception
    assert by_key(at.button, "fi_backgo_") is not None and switch(at).value is False and len(_vs(at, 1)) == n2
    by_key(at.button, "fi_backno_").click().run()
    assert by_key(at.button, "fi_backgo_") is None and switch(at).value is False
    assert _D(at)["import_mode"] == "custom" and at.session_state["active"] in at.session_state["cleaned"]


def test_a_product_chosen_in_step_2_labels_the_readings(tmp_path, monkeypatch):
    """A raw card whose yields are converted with another product in step 2: every reading of the import (and of the
    clean file) says that product (Product: its SMS name since 0.3.2, Crop: its key), the manual moisture follows the
    product's dry moisture and the source summary names the crop; back to SMS's default, the card's own labels again."""
    from tests import synthetic_cn1 as SC
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    _extract(at)
    g0 = pyogrio.read_dataframe(_D(at)["shp"], read_geometry=False)
    p0, c0 = set(g0["Product"]), set(g0["Crop"])
    assert c0 == {"wheat"} and p0 != {"barley"}
    _apply_import(at, prod="barley")
    D = _D(at)
    g1 = pyogrio.read_dataframe(D["shp"], read_geometry=False)
    assert set(g1["Product"]) == {"Barley - Fall"} and set(g1["Crop"]) == {"barley"}     # 0.3.2: SMS's name
    RS = D["sms_import"]["resolved"]
    assert RS["product"] == "barley" and RS["manual_moisture_pct"] == RS["dry_moisture_pct"]
    assert str(D["source"]["calibration_summary"]).startswith("crop Barley - Fall;")
    C = _clean(at)
    g2 = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    assert set(g2["Product"]) == {"Barley - Fall"} and set(g2["Crop"]) == {"barley"}
    _back_to_default(at, confirm=True)
    g3 = pyogrio.read_dataframe(_D(at)["shp"], read_geometry=False)
    assert set(g3["Product"]) == p0 and set(g3["Crop"]) == c0


def test_a_new_import_is_written_beside_the_one_in_use(field, tmp_path, monkeypatch):
    """An Apply whose import writes part of a file and then fails leaves the import in use byte for byte; a swap
    blocked by a file held open leaves the new import under its temporary name, and the next Apply that fails keeps
    it (no traceback, the message true); the next one that works swaps it in and leaves no temporary file."""
    import hashlib
    real = si.apply
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)

    def digest(shp):
        return {e: hashlib.md5(open(os.path.splitext(shp)[0] + e, "rb").read()).hexdigest() for e in (".shp", ".dbf")}

    def broken(src, out, R, *a, **k):                    # writes where it was told to, then fails
        for e in (".shp", ".dbf"):
            open(os.path.splitext(out)[0] + e, "wb").write(b"broken")
        raise OSError("synthetic write failure")
    for held in (False, True):
        shp = _D(at)["shp"]
        before = digest(shp)
        monkeypatch.setattr(si, "apply", broken)
        _set_import(at, max=130.0)
        by_key(at.button, "fi_go_").click().run()
        monkeypatch.setattr(si, "apply", real)
        assert not at.exception, at.exception
        assert any("the file and its import are unchanged" in e.value for e in at.error)
        assert _D(at)["shp"] == shp and digest(shp) == before
        if not held:
            fh = open(os.path.splitext(shp)[0] + ".dbf", "rb")       # held open by another program
            try:
                _apply_import(at, max=140.0)
            finally:
                fh.close()
            assert _D(at)["shp"].endswith(f"{t}_imported_next.shp")
            # a warning of its own, the file named once, no Windows error text
            assert any("The previous import" in w.value for w in at.warning)
            assert not any("could not" in s.value for s in at.success)
            assert not any("WinError" in w.value or w.value.count(f"{t}_imported_custom") > 1 for w in at.warning)
    _apply_import(at, max=120.0)
    D = _D(at)
    assert D["shp"].endswith(f"{t}_imported_custom.shp") and D["sms_import"]["resolved"]["max_yield"] == 120.0
    assert not _files(wd, f"{t}_imported_next*")


def test_a_failed_import_untouched_and_then_own_settings(field, tmp_path, monkeypatch):
    """A file whose SMS import failed at open, nothing touched: nothing 'not applied' in steps 2 and 3 and no second
    strip (step 2 is step 1's data), Apply still tries again; own settings applied then: step 3 starts from step 2
    and its cards compare with step 2."""
    real = si.apply

    def boom(*a, **k):
        raise OSError("synthetic write failure")
    monkeypatch.setattr(si, "apply", boom)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    monkeypatch.setattr(si, "apply", real)
    at.run()
    assert not any("Not applied" in c.value or "values not applied" in c.value for c in at.caption)
    assert not _vs(at, 1) and by_key(at.button_group, "attr_imp_") is None
    assert not by_key(at.button, "fi_go_").disabled
    _apply_import(at, max=150.0)
    D = _D(at)
    assert D["import_mode"] == "custom" and D["import_default"].get("error")
    assert "step 2:" in _starts_from(at).value
    _clean(at)
    assert [m for m in at.metric if m.label == "Mean dry yield, cleaned" and "vs step 2" in str(m.delta)]


def test_apply_to_all_says_what_it_changes_and_what_failed(field, tmp_path, monkeypatch):
    """'Apply to all' names, before the click and after it, what it changes in each file (field: old → new); the
    file's own settings it does not change stay. A file it could not import is a warning (named once), not part of
    the success line, and keeps its own settings."""
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    root = tmp_path / "in"
    for sub, part in (("A", g), ("B", g.iloc[::2])):
        os.makedirs(root / sub)
        part.to_file(str(root / sub / f"Harvest_{sub}.shp"), engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root)
    for i in (0, 1):
        at.selectbox(key="cand_idx").select_index(i).run()
    a, b = sorted(at.session_state["datasets"])
    at.selectbox(key="active_pick").set_value(b).run()
    _apply_import(at, min=10.0)
    at.selectbox(key="active_pick").set_value(a).run()
    _set_import(at, max=120.0)
    line = _orange(at)
    assert f"Apply to all also changes {b} (Max. yield volume none → 120.00)." in line, line
    assert "replaces the own settings" not in line, line
    real = si.apply

    def fail_b(src, out, R, *x, **k):
        if "Harvest_B" in str(src):
            raise OSError(28, "No space left on device")
        return real(src, out, R, *x, **k)
    monkeypatch.setattr(si, "apply", fail_b)
    by_key(at.button, "fi_goall_").click().run()
    monkeypatch.setattr(si, "apply", real)
    assert not at.exception, at.exception
    w = [x.value for x in at.warning if "could not be imported" in x.value]
    assert len(w) == 1 and w[0].count(b) == 1
    # its reason and the way to finish it: Apply to all no longer reaches it once the other file changed
    assert w[0].endswith("(OSError: No space left on device): the file and its import are unchanged; free disk "
                         "space, then choose it in step 2 and Apply the same change on it"), w
    assert not any("could not be imported" in s.value for s in at.success)
    assert _D(at, b)["sms_import"]["resolved"]["min_yield"] == 10.0
    _apply_to_all(at, max=110.0)
    msg = " ".join(s.value for s in at.success)
    assert f"Changed in {b}: Max. yield volume none → 110.00." in msg and "were replaced" not in msg, msg
    RB = _D(at, b)["sms_import"]["resolved"]
    assert RB["max_yield"] == 110.0 and RB["min_yield"] == 10.0        # its own minimum stays
    # settings that cannot be resolved for a file: named with their reason, not as a file with no record
    real_r = si.resolve

    def refuse(S, *x, **k):
        if (S or {}).get("min_yield") == 10.0 and (S or {}).get("max_yield") == 105.0:
            raise ValueError("synthetic refusal")
        return real_r(S, *x, **k)
    monkeypatch.setattr(si, "resolve", refuse)
    _set_import(at, max=105.0)
    line = _orange(at)
    monkeypatch.setattr(si, "resolve", real_r)
    assert (f"Apply to all leaves {b} as it is: its settings could not be resolved (synthetic refusal): Apply on it "
            "says why.") in line and "no record" not in line, line


def test_older_values_are_not_the_users_and_step_4_names_a_kept_cleanings_import(field, tmp_path, monkeypatch):
    """A work whose own import still carries an older rule's minimum: step 2 names only the user's change, nothing is
    'not applied' with nothing typed; reopened after its own import's file was deleted, the cleaning kept (to be
    cleaned again) is named in steps 3 and 4 by the settings it was made with, and step 3 compares it with no import
    it did not start from."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=150.0)
    _clean(at)
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    IM = rec["datasets"][t]["sms_import"]
    IM["revision"], IM["resolved"]["min_yield"], IM["sources"]["min_yield"] = 1, 5.0, si.SRC_TABLE
    json.dump(rec, open(p, "w", encoding="utf-8"))
    _reopen(at, wd)
    assert _D(at)["import_mode"] == "custom"
    line = next(x for x in _badge_lines(at) if x.startswith("Your settings"))
    assert "Max. yield volume" in line and "Min. yield volume" not in line
    assert not any("Not applied" in c.value or "values not applied" in c.value for c in at.caption)
    for f in glob.glob(os.path.splitext(_D(at)["shp"])[0] + ".*"):
        os.remove(f)
    _reopen(at, wd)
    assert _D(at)["import_mode"] == "default" and at.session_state["cleaned"][t].get("clean_again")
    T4 = next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)
    assert list(T4["import"]) == ["your settings: max. yield volume 150.00"]
    box = [h.proto.body for h in at.get("html") if "oced-path" in h.proto.body]
    T = next(d.value for d in at.dataframe if "mean after" in d.value.columns)
    assert "from your settings (step 2)" in box[0] and T["step"].iloc[0] == "your settings (step 2)"
    assert not any(" vs step" in str(m.delta) for m in at.metric if m.label.endswith(", cleaned"))
    assert not any(" vs step" in str(m.delta) for m in at.metric if m.label.endswith("cleaned (SMS)"))


def test_a_0_3_0_card_extracted_with_another_product_gets_its_own_labels_back(tmp_path, monkeypatch):
    """A raw file 0.3.0 extracted with a product chosen before extracting (its decoded readings labelled with that
    product, the decode report's options naming it): SMS's default import made again for step 1 is labelled with the
    card's own crop, whether it is decoded again from the card or, the card not at hand, made from those readings
    (then named the older version's import)."""
    from tests import synthetic_cn1 as SC
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    g0 = pyogrio.read_dataframe(_D(at)["import_default"]["shp"], read_geometry=False)
    own = (set(g0["Product"]), set(g0["Crop"]))
    _apply_import(at, prod="barley")
    at.button(key="work_save").click().run()
    allr = _D(at)["sms_import"]["all_readings"]
    g = pyogrio.read_dataframe(allr)
    g.assign(Product="barley", Crop="barley").to_file(allr, engine="pyogrio")     # as 0.3.0's decoder wrote them
    rec = _as_saved_by_0_3_0(wd, t)
    rec["datasets"][t]["report"].setdefault("options", {})["crop"] = "barley"
    work_030 = json.dumps(rec)
    for gone in (False, True):
        open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8").write(work_030)
        if gone:
            os.replace(tmp_path / "cnh", tmp_path / "cnh_away")
        _reopen(at, wd)
        D = _D(at)
        assert D["import_mode"] == "custom" and os.path.exists(D["import_default"]["shp"])
        assert os.path.normcase(D["import_default"]["shp"]) != os.path.normcase(allr)
        g1 = pyogrio.read_dataframe(D["import_default"]["shp"], read_geometry=False)
        assert (set(g1["Product"]), set(g1["Crop"])) == own
        assert _badge_lines(at)[0].startswith("Older rule" if gone else "SMS default")


# ------------------------------------------------------------------------------------------------ checks of round 6
def _as_older_rule(Dr: dict):
    """A file's record as 0.3.0 kept an import made under an older rule (values the user did not type, no mode, no
    default block)."""
    IM = Dr["sms_import"]
    for k in ("revision", "mode"):
        IM.pop(k, None)
    IM["fmt"], IM["family"] = None, None
    IM["sources"] = {**IM["sources"], "min_yield": si.SRC_TABLE, "max_yield": si.SRC_TABLE}
    for k in ("import_default", "import_mode"):
        Dr.pop(k, None)


def _older_rule_work(at, field):
    """An export imported under an older rule (5-300 bu/ac, values the user did not type), cleaned and saved as 0.3.0
    kept it (one import per file, under the name <tag>_imported), then opened again: (tag, work folder, the readings
    of that import)."""
    _open(at, field["shp"])
    _apply_import(at, min=5.0, max=300.0)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    n_old = _D(at)["n"]
    _clean(at)
    at.button(key="work_save").click().run()
    D0 = _D(at)
    own, dflt = os.path.splitext(D0["shp"])[0], os.path.splitext(D0["import_default"]["shp"])[0]
    for p in glob.glob(dflt + ".*"):
        os.remove(p)
    for p in glob.glob(own + ".*"):
        os.replace(p, dflt + p[len(own):])
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    _as_older_rule(rec["datasets"][t])
    rec["datasets"][t]["shp"] = (os.path.relpath(dflt + ".shp", wd) if not os.path.isabs(rec["datasets"][t]["shp"])
                                 else dflt + ".shp")
    json.dump(rec, open(p, "w", encoding="utf-8"))
    _reopen(at, wd)
    return t, wd, n_old


def _later(shp, s):
    """The parts of a shapefile s seconds later on disk (a copy that did not keep the files' times)."""
    for p in glob.glob(os.path.splitext(shp)[0] + ".*"):
        st_ = os.stat(p)
        os.utime(p, (st_.st_atime + s, st_.st_mtime + s))


def test_an_older_rule_import_stays_through_a_copy_and_step_2_says_what_apply_changes(field, tmp_path, monkeypatch):
    """D7: the import an older rule made stays the file's import (step 1, Older rule, its readings) when the work is
    copied without its files' times, also from a record saved before imports were known by their content; its
    cleaning record says it is an older rule's; switched off, step 2 says what Apply changes in it, and once applied
    that steps 1 and 2 show the new import (the older import's files, referenced no more, are gone)."""
    at = _app(tmp_path / "ws", monkeypatch)
    t, wd, n_old = _older_rule_work(at, field)
    D = _D(at)
    assert D["import_mode"] == "default" and D["import_default"]["older"] and D["n"] == n_old
    shp = D["shp"]
    C = _clean(at)                                        # saved by this version, its default block with it
    assert C["R"]["sms_import"]["mode"] == "older" and C["R"]["sms_import"]["older"]
    p = os.path.join(wd, "oced_work.json")
    for no_sig in (False, True):
        if no_sig:
            rec = json.load(open(p, encoding="utf-8"))
            rec["datasets"][t]["import_default"].pop("sig", None)
            json.dump(rec, open(p, "w", encoding="utf-8"))
        _later(shp, 3600)
        _reopen(at, wd)
        D = _D(at)
        assert (D["import_mode"], D["n"], os.path.normcase(D["shp"])) == ("default", n_old, os.path.normcase(shp))
        assert D["import_default"]["older"] and any(b.startswith("Older rule") for b in _badge_lines(at))
        assert not _files(wd, f"{t}_imported_default.*") and t in at.session_state["cleaned"]
    _switch_off(at)
    caps = [c.value for c in at.caption]
    assert not any(c.startswith("Still SMS's default") for c in caps), caps
    na = "Not applied: Min. yield volume 5.000 → 0.000, Max. yield volume 300.00 → none"
    assert any(na in c for c in caps), caps
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    msg = " ".join(s.value for s in at.success)
    assert f"Steps 1 and 2 now show it; the older rule's import had {n_old:,} readings." in msg
    assert _D(at)["n"] == field["n"] and not _D(at)["import_default"].get("older")
    assert _D(at)["shp"].endswith(f"{t}_imported_default.shp") and not glob.glob(os.path.splitext(shp)[0] + ".*")


def test_the_default_made_again_is_written_beside_the_import_in_use(field, tmp_path, monkeypatch):
    """SMS's default import made again while it is the import in use (its record no longer matches its file): written
    under a temporary name and swapped in; an import that writes part of a file and then fails leaves the import in
    use byte for byte (a line says so once, with the reason and no path, no traceback, no temporary file) and is not
    tried again on every run of the page; opening the work again tries it again."""
    import hashlib
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    t, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")

    def stale():                                          # as a record of an earlier build: time only, another time
        rec = json.load(open(p, encoding="utf-8"))
        rec["datasets"][t]["import_default"]["mtime"] = 0.0
        rec["datasets"][t]["import_default"].pop("sig", None)
        json.dump(rec, open(p, "w", encoding="utf-8"))

    def digest(shp):
        return {e: hashlib.md5(open(os.path.splitext(shp)[0] + e, "rb").read()).hexdigest() for e in (".shp", ".dbf")}
    stale()
    _reopen(at, wd)
    D = _D(at)
    assert D["import_mode"] == "default" and D["shp"].endswith(f"{t}_imported_default.shp")
    shp, before = D["shp"], digest(D["shp"])
    stale()
    real = si.apply
    calls = []

    def broken(src, out, R, *a, **k):
        calls.append(out)
        for e in (".shp", ".dbf"):
            open(os.path.splitext(out)[0] + e, "wb").write(b"broken")
        raise OSError("synthetic write failure")
    monkeypatch.setattr(si, "apply", broken)
    _reopen(at, wd)
    assert _D(at)["shp"] == shp and digest(shp) == before
    assert any("could not be made (OSError: synthetic write failure)" in c.value for c in at.caption)
    assert not _files(wd, f"{t}_imported_next*")
    n_calls = len(calls)
    for _ in range(2):                                    # not tried again on every run; said once
        at.run()
        assert not at.exception, at.exception
    assert len(calls) == n_calls and not any("could not be made" in c.value for c in at.caption)

    def held(src, out, R, *a, **k):
        raise PermissionError(13, "Access is denied", out)
    monkeypatch.setattr(si, "apply", held)
    _reopen(at, wd)                                       # opened again: tried again
    note = [c.value for c in at.caption if "could not be made" in c.value]
    assert note and "(PermissionError: Access is denied)" in note[0] and "imported" not in note[0], note
    monkeypatch.setattr(si, "apply", real)
    _reopen(at, wd)                                       # made again, known by its content from now on
    assert _D(at)["shp"] == shp and digest(shp) == before and _D(at)["import_default"]["sig"]


def test_a_default_that_cannot_be_made_keeps_its_reason_without_a_path(field, tmp_path, monkeypatch):
    """SMS's default import that cannot be made again while own settings are in use (its file gone, the write failing
    with an error that names the full path, as GDAL's do): step 1's note names the file only, once; on later runs
    step 1's import line still gives that reason, not 'its readings are no longer on disk'. An Apply that fails on a
    file held open says so without the path either."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, max=150.0)
    t = at.session_state["active"]
    for q in glob.glob(os.path.splitext(_D(at)["import_default"]["shp"])[0] + ".*"):
        os.remove(q)
    real = si.apply

    def gdal(src, out, R, *a, **k):
        raise RuntimeError(f"Failed to create file {out}: No such file or directory")
    monkeypatch.setattr(si, "apply", gdal)
    at.run()
    assert not at.exception, at.exception
    note = [c.value for c in at.caption if "could not be made" in c.value]
    assert note and f"(RuntimeError: Failed to create file {t}_imported_next.shp: No such file" in note[0], note
    assert ":\\" not in note[0] and ":/" not in note[0], note
    at.run()
    assert not any("could not be made" in c.value for c in at.caption)
    helps = [m.help or "" for m in at.markdown if "oced-badge" in m.value]
    assert "could not be made (RuntimeError: Failed to create file" in helps[0], helps
    assert "no longer on disk" not in helps[0] and ":\\" not in helps[0], helps

    def held(src, out, R, *a, **k):
        raise PermissionError(13, "Access is denied", out)
    monkeypatch.setattr(si, "apply", held)
    _set_import(at, max=100.0)
    by_key(at.button, "fi_go_").click().run()
    monkeypatch.setattr(si, "apply", real)
    err = [e.value for e in at.error if "could not be imported" in e.value]
    assert err and "(PermissionError: Access is denied)" in err[0] and ":\\" not in err[0], err


def test_steps_1_and_2_lead_to_the_next_action(field, tmp_path, monkeypatch):
    """Step 1 with an input open and nothing in the work names the next action (tick the units and Extract; choose a
    dataset); step 2's 'None' gives the S0 minimum step 3 holds now; own settings that leave no reading open the
    fields to change them."""
    import geopandas as gpd
    from tests import synthetic_cn1 as SC
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    assert any("Tick the units to extract and click Extract" in i.value for i in at.info), [i.value for i in at.info]
    g = gpd.read_file(field["shp"])
    for sub in ("A", "B"):
        os.makedirs(tmp_path / "two" / sub)
        g.to_file(str(tmp_path / "two" / sub / f"Harvest_{sub}.shp"), engine="pyogrio")
    at = _app(tmp_path / "ws2", monkeypatch)
    _open(at, tmp_path / "two")
    assert any(i.value.startswith("Choose the dataset") for i in at.info), [i.value for i in at.info]
    at = _app(tmp_path / "ws3", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, how="none")
    at.number_input(key="min_yield").set_value(2.0).run()
    assert any("Step 3's S0 minimum then applies (now 2.000 bu/ac" in c.value for c in at.caption)
    _apply_import(at, how="sms", min=9999.0)
    assert any("leave no reading with a position" in w.value for w in at.warning)
    assert [e.proto.expanded for e in at.expander if e.label == "Edit the settings"] == [True]


def test_none_as_logged_after_a_failed_import_is_named_as_logged(tmp_path, monkeypatch):
    """A raw file whose SMS import failed at extraction: steps 3 and 4 name that import by the badge's words ('import
    failed'); 'None: as the monitor logged it' applied, steps 2 to 4 name it 'as logged' (step 1 still says the import
    failed), step 2 shows its strip and keeps the choice, and the cleaning starts from step 2."""
    from tests import synthetic_cn1 as SC
    real = si.apply

    def boom(*a, **k):
        raise OSError("synthetic write failure")
    monkeypatch.setattr(si, "apply", boom)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    _extract(at)
    monkeypatch.setattr(si, "apply", real)
    at.run()
    _clean(at)

    def step4():
        return list(next(d.value for d in at.dataframe if "import" in d.value.columns and "kept" in d.value.columns)[
            "import"])
    box = [h.proto.body for h in at.get("html") if "oced-path" in h.proto.body]
    T = next(d.value for d in at.dataframe if "mean after" in d.value.columns)
    assert "from import failed (step 1)" in box[0] and T["step"].iloc[0] == "import failed (step 1)"
    assert step4() == ["import failed"]
    _apply_import(at, how="none")
    D = _D(at)
    assert D["import_mode"] == "as_is" and os.sep + "as_logged" + os.sep in D["shp"]
    b = _badge_lines(at)
    assert b[0].startswith("Import failed") and any(x.startswith("As logged") for x in b[1:]), b
    assert "As logged" in _starts_from(at).value and "step 2:" in _starts_from(at).value
    assert by_key(at.button_group, "fi_how_").value == "none" and by_key(at.button, "fi_go_").disabled
    assert _vs(at, 1)                                     # step 2's strip of the data as logged
    _clean(at)
    assert step4() == ["as logged"]


def test_held_files_are_warnings_and_the_sidebar_counts_what_is_cleaned(tmp_path, monkeypatch):
    """A file another program holds open: after an extraction again (named once), and after going back to SMS's
    default, a warning names it (not the line of what was done, no Windows error text); the sidebar's 'Opened ...'
    line counts the cleanings as they are, not as they were opened."""
    from tests import synthetic_cn1 as SC
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, SC.make_card(str(tmp_path / "cnh"))["card"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    _apply_import(at, max=80.0)
    fh = open(os.path.splitext(_D(at)["shp"])[0] + ".dbf", "rb")
    try:
        _extract_again(at)
        w = [x.value for x in at.warning]
    finally:
        fh.close()
    assert sum(f"{t}_imported_custom" in x for x in w) == 1 and not any("WinError" in x for x in w), w
    assert _D(at)["sms_import"]["resolved"]["max_yield"] == 80.0
    _clean(at)
    at.button(key="work_save").click().run()
    _reopen(at, wd)

    def opened():
        return [s.value for s in at.success if s.value.startswith("Opened")]
    assert opened() and "1 file(s), 1 cleaned" in opened()[0]
    fh = open(os.path.splitext(_D(at)["shp"])[0] + ".dbf", "rb")
    try:
        _back_to_default(at, confirm=True)
    finally:
        fh.close()
    assert _D(at)["import_mode"] == "default"
    assert any("could not be deleted" in x.value for x in at.warning)
    assert not any("could not" in s.value for s in at.success)
    assert opened() and "1 file(s), 0 cleaned" in opened()[0]


def test_a_cleaning_inside_the_boundary_says_so(field, tmp_path, monkeypatch):
    """With a boundary, step 3's count of the readings kept and the status of the cleaning say that they are counted
    inside the boundary (step 1 / 2's readings are more)."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    by_key(at.text_input, "bnd_path_").input(field["boundary"])
    by_key(at.button, "bnd_use_").click().run()
    C = _clean(at)
    R = C["R"]
    assert int(R["n_read"]) > int(R["n_in"])
    m = next(x for x in at.metric if x.label == "Readings kept")
    assert f"of {int(R['n_in']):,} inside the boundary" in str(m.delta)
    assert any(f"{int(R['n_read']):,} readings, {int(R['n_in']):,} inside the boundary" in s.label for s in at.status)


# ------------------------------------------------------------------------------------------------ Apply to all
def _exports(tmp_path, field, parts):
    """Point exports, each in a folder of its own under <tmp>/in: {letter: (rows, product)} (product None: the
    synthetic field's own, wheat). Returns that folder."""
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    root = tmp_path / "in"
    for sub, (rows, prod) in parts.items():
        os.makedirs(root / sub)
        p = g.iloc[rows].copy()
        if prod:
            p["Product"] = prod
        p.to_file(str(root / sub / f"Harvest_{sub}.shp"), engine="pyogrio")
    return root


def _open_all(at, root, n):
    """The n datasets of the folder opened; their tags, sorted."""
    _open(at, root)
    for i in range(n):
        at.selectbox(key="cand_idx").select_index(i).run()
        assert not at.exception, at.exception
    tags = sorted(at.session_state["datasets"])
    assert len(tags) == n, tags
    return tags


def _pick(at, t):
    at.selectbox(key="active_pick").set_value(t).run()
    assert not at.exception, at.exception
    assert at.session_state["active"] == t


def _state(at, t):
    """What Apply to all must leave as it is in a file it brings nothing: its import (file, readings, time on disk,
    settings), its mode and its cleaning."""
    D = _D(at, t)
    C = at.session_state["cleaned"].get(t)
    return (os.path.normcase(D["shp"]), D["n"], os.path.getmtime(D["shp"]), D["import_mode"],
            json.dumps((D.get("sms_import") or {}).get("resolved"), sort_keys=True), (C or {}).get("shp"))


def _orange(at):
    return " ".join(c.value for c in at.caption if c.value.startswith(":orange["))


def test_apply_to_all_leaves_a_file_of_another_product_as_it_is(field, tmp_path, monkeypatch):
    """A weight to volume changed on a wheat file and applied to all: the other wheat file gets it (its cleaning set
    aside); the canola files get nothing of it, so each stays exactly as it was (its import, its own settings, its
    cleaning). The orange line names, before the click, the files that change and those that do not."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), "Canola"),
                                      "C": (slice(1, None, 2), None), "D": (slice(0, None, 3), "Canola")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c, d = _open_all(at, root, 4)
    for t in (b, c):
        _pick(at, t)
        _clean(at)
    _pick(at, d)
    _apply_import(at, max=150.0)
    _clean(at)
    before = {t: _state(at, t) for t in (b, d)}
    _pick(at, a)
    tw = float(_D(at, a)["sms_import"]["resolved"]["test_weight_lb_bu"])
    assert tw != float(_D(at, b)["sms_import"]["resolved"]["test_weight_lb_bu"])
    _set_import(at, tw=tw + 2.0)
    line = _orange(at)
    assert f"Apply to all also changes {c} (Weight to volume {tw:,.2f} → {tw + 2:,.2f})." in line, line
    assert f"also sets aside the cleaning of {c}." in line, line
    assert (f"Apply to all leaves {b} (Product canola), {d} (Product canola) as they are: a weight to volume or dry "
            "moisture goes only to files of this file's product (wheat).") in line, line
    assert "replaces the own settings" not in line and "brings them nothing" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    for t in (a, c):
        assert _D(at, t)["sms_import"]["resolved"]["test_weight_lb_bu"] == tw + 2.0
    assert c not in at.session_state["cleaned"]
    assert {t: _state(at, t) for t in (b, d)} == before
    assert _D(at, d)["import_mode"] == "custom" and _D(at, d)["sms_import"]["resolved"]["max_yield"] == 150.0
    msg = " ".join(s.value for s in at.success)
    assert (f"Left as they are: {b} (Product canola), {d} (Product canola); a weight to volume or dry moisture goes "
            "only to files of this file's product (wheat).") in msg, msg
    assert f"{b}: these are SMS's default" not in msg


def test_apply_to_all_is_off_with_nothing_typed_and_reaches_an_older_rule_only_by_a_field(field, tmp_path, monkeypatch):
    """A work of 0.3.0: two files imported under an older rule and one on today's SMS default, all cleaned. With
    nothing typed on an older rule's file, 'Apply to all' is off: Apply brings today's rule to that file only, the
    others keep their import and their cleaning. A field taken back that the other older rule's file does not have
    leaves it on its older rule's import (named as such, before and after the click); a maximum typed reaches it, and
    the orange line says its older rule's import is replaced by today's rule plus the change."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c = _open_all(at, root, 3)
    wd = at.session_state["workdir"]
    for t in (a, b):
        _pick(at, t)
        _apply_import(at, min=5.0, max=300.0)
        _clean(at)
    _pick(at, c)
    _clean(at)
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    for t in (a, b):
        _as_older_rule(rec["datasets"][t])
    json.dump(rec, open(p, "w", encoding="utf-8"))
    _reopen(at, wd)
    assert all(_D(at, t)["import_default"].get("older") for t in (a, b))
    assert all(t in at.session_state["cleaned"] for t in (a, b, c))
    before = {t: _state(at, t) for t in (b, c)}
    _pick(at, a)
    _switch_off(at)
    assert by_key(at.button, "fi_goall_").disabled and not by_key(at.button, "fi_go_").disabled
    assert "Apply to all" not in _orange(at), _orange(at)
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert not _D(at, a)["import_default"].get("older") and _D(at, a)["n"] == field["n"]
    assert {t: _state(at, t) for t in (b, c)} == before and all(t in at.session_state["cleaned"] for t in (b, c))
    _apply_import(at, max=150.0)                          # on this file only, then taken back from every file
    _set_import(at, max=None)
    line = _orange(at)
    assert f"Apply to all keeps the older rule's import of {b} (Apply on it to update it)." in line, line
    assert f"Apply to all leaves {c} as it is" in line and "also changes" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _D(at, a)["import_mode"] == "default" and {t: _state(at, t) for t in (b, c)} == before
    msg = " ".join(x.value for x in at.success)
    assert f"Kept on the older rule's import (Apply on it to update it): {b}." in msg, msg
    assert f"this change brings it nothing): {c}." in msg and f"nothing): {b}" not in msg, msg
    _set_import(at, max=150.0)                            # a field that applies to the older rule's file
    line = _orange(at)
    assert (f"Apply to all also changes {b} (Min. yield volume 5.000 → 0.000; Max. yield volume 300.00 → 150.00; its "
            f"older rule's import replaced by today's rule plus this change), {c} (Max. yield volume none → 150.00).") \
        in line, line
    assert f"also sets aside the cleaning of {b}, {c}." in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    RB = _D(at, b)["sms_import"]["resolved"]
    assert _D(at, b)["import_mode"] == "custom" and (RB["min_yield"], RB["max_yield"]) == (0.0, 150.0)
    assert b not in at.session_state["cleaned"] and c not in at.session_state["cleaned"]
    msg = " ".join(x.value for x in at.success)
    assert f"Changed in {b}: Min. yield volume 5.000 → 0.000; Max. yield volume 300.00 → 150.00; its older" in msg, msg


def test_apply_to_all_leaves_a_file_the_change_brings_nothing(field, tmp_path, monkeypatch):
    """A field set back to SMS's default on one file and applied to all: a file on its default and a file with another
    own setting (a maximum) have no such setting to take back, so both stay exactly as they were (import, own settings,
    cleaning), as the orange line says; the file itself goes back to its default. A maximum a file already has leaves
    it as it is too, while it reaches a file on its default."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c = _open_all(at, root, 3)
    _pick(at, a)
    _apply_import(at, min=10.0)
    _pick(at, b)
    _clean(at)
    _pick(at, c)
    _apply_import(at, max=150.0)
    _clean(at)
    before = {t: _state(at, t) for t in (b, c)}
    _pick(at, a)
    _set_import(at, min=0.0)
    line = _orange(at)
    assert f"Apply to all leaves {b}, {c} as they are: this change brings them nothing." in line, line
    assert "also changes" not in line and "sets aside" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _D(at, a)["import_mode"] == "default" and {t: _state(at, t) for t in (b, c)} == before
    assert _D(at, c)["import_mode"] == "custom" and all(t in at.session_state["cleaned"] for t in (b, c))
    msg = " ".join(x.value for x in at.success)
    assert f"Left as they are (this change brings them nothing): {b}, {c}." in msg, msg
    _set_import(at, max=150.0)                            # C has that maximum already, B does not
    line = _orange(at)
    assert f"Apply to all also changes {b} (Max. yield volume none → 150.00)." in line, line
    assert f"Apply to all leaves {c} as it is" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _D(at, b)["import_mode"] == "custom" and _D(at, b)["sms_import"]["resolved"]["max_yield"] == 150.0
    assert b not in at.session_state["cleaned"] and _state(at, c) == before[c]


def test_apply_to_all_takes_a_setting_back_from_every_file(field, tmp_path, monkeypatch):
    """A maximum applied to all, then emptied on one file and applied to all again: it is taken back from every file
    that has it (one setting for every file, both ways). A file with another own setting (a minimum) keeps it; a file
    with only that maximum goes back to its SMS default; a file already on its default keeps its import and its
    cleaning. The orange line names what changes in each file, before the click; the line after it too."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), None), "D": (slice(0, None, 3), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c, d = _open_all(at, root, 4)
    _pick(at, a)
    _apply_to_all(at, max=150.0)
    assert all(_D(at, t)["import_mode"] == "custom" and _D(at, t)["sms_import"]["resolved"]["max_yield"] == 150.0
               for t in (a, b, c, d))
    _pick(at, c)
    _back_to_default(at)                                  # no cleaning: at once
    assert _D(at, c)["import_mode"] == "default"
    _clean(at)
    _pick(at, b)
    _apply_import(at, min=10.0)
    _clean(at)
    before = _state(at, c)
    _pick(at, a)
    _set_import(at, max=None)
    line = _orange(at)
    assert (f"Apply to all also changes {b} (Max. yield volume 150.00 → none), {d} (Max. yield volume 150.00 → none; "
            "back on its SMS default).") in line, line
    assert f"also sets aside the cleaning of {b}." in line and f"Apply to all leaves {c} as it is" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    for t in (a, d):
        D = _D(at, t)
        assert D["import_mode"] == "default" and D["shp"] == D["import_default"]["shp"], t
    RB = _D(at, b)["sms_import"]["resolved"]
    assert _D(at, b)["import_mode"] == "custom" and RB["min_yield"] == 10.0 and RB["max_yield"] is None
    assert b not in at.session_state["cleaned"] and _state(at, c) == before and c in at.session_state["cleaned"]
    msg = " ".join(x.value for x in at.success)
    assert f"Changed in {b}: Max. yield volume 150.00 → none." in msg, msg
    assert f"Left as it is (this change brings it nothing): {c}." in msg and "were replaced" not in msg, msg


def test_apply_to_all_matches_a_crop_value_on_the_product_of_the_import_in_use(field, tmp_path, monkeypatch):
    """A weight to volume changed on a wheat file and applied to all does not reach a file of the same data that the
    user set to barley in step 2 (the product of its import in use): it keeps its import and its cleaning. A maximum
    applied to all then reaches it and it keeps its own product and weight to volume (no crop's values of another)."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b = _open_all(at, root, 2)
    _pick(at, b)
    _apply_import(at, prod="barley")
    RB0 = dict(_D(at, b)["sms_import"]["resolved"])
    assert RB0["product"] == "barley"
    _clean(at)
    before = _state(at, b)
    _pick(at, a)
    tw = float(_D(at, a)["sms_import"]["resolved"]["test_weight_lb_bu"])
    assert tw != float(RB0["test_weight_lb_bu"])
    _set_import(at, tw=tw + 2.0)
    line = _orange(at)
    assert f"Apply to all leaves {b} (Product barley) as it is: a weight to volume" in line, line
    assert "replaces the own settings" not in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _D(at, a)["sms_import"]["resolved"]["test_weight_lb_bu"] == tw + 2.0
    assert _state(at, b) == before and b in at.session_state["cleaned"]
    _set_import(at, max=150.0)                            # not about the crop: it reaches B, B stays barley
    line = _orange(at)
    assert f"Apply to all also changes {b} (Max. yield volume none → 150.00)." in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    RB = _D(at, b)["sms_import"]["resolved"]
    assert RB["product"] == "barley" and RB["max_yield"] == 150.0
    assert (RB["test_weight_lb_bu"], RB["dry_moisture_pct"]) == (RB0["test_weight_lb_bu"], RB0["dry_moisture_pct"])
    assert b not in at.session_state["cleaned"]


def test_apply_to_all_brings_a_crop_value_to_files_of_its_product_only(field, tmp_path, monkeypatch):
    """A weight to volume changed on a wheat file reaches a file of canola data that the user set to wheat in step 2
    (the product of its import in use): it gets that weight and stays wheat (never one crop's product with another
    crop's weight). A file of canola data on its default is not reached: it keeps its import and its cleaning."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), "Canola"),
                                      "D": (slice(1, None, 2), "Canola")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, d = _open_all(at, root, 3)
    _pick(at, b)
    _apply_import(at, prod="wheat")
    assert _D(at, b)["sms_import"]["resolved"]["product"] == "wheat"
    _clean(at)
    _pick(at, d)
    _clean(at)
    before = _state(at, d)
    _pick(at, a)
    tw = float(_D(at, a)["sms_import"]["resolved"]["test_weight_lb_bu"])
    assert float(_D(at, b)["sms_import"]["resolved"]["test_weight_lb_bu"]) == tw
    _set_import(at, tw=tw + 2.0)
    line = _orange(at)
    assert f"Apply to all also changes {b} (Weight to volume {tw:,.2f} → {tw + 2:,.2f})." in line, line
    assert f"Apply to all leaves {d} (Product canola) as it is: a weight to volume" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    RB = _D(at, b)["sms_import"]["resolved"]
    assert RB["product"] == "wheat" and RB["test_weight_lb_bu"] == tw + 2.0 and b not in at.session_state["cleaned"]
    assert _state(at, d) == before and d in at.session_state["cleaned"]


def _prod(at, t):
    """(mode, product, weight to volume, dry moisture, max. yield volume) of a file's import in use."""
    R = _D(at, t)["sms_import"]["resolved"]
    return _D(at, t)["import_mode"], R["product"], R["test_weight_lb_bu"], R["dry_moisture_pct"], R["max_yield"]


def test_apply_to_all_chooses_the_product_once_for_files_of_an_unknown_crop(field, tmp_path, monkeypatch):
    """Three exports whose product is not known and one of wheat: a product chosen on one of them and applied to all
    reaches the other two ('not known' is one product), each with that product's weight to volume and dry moisture,
    never the wheat file (another product: left as it is, its cleaning kept). Chosen again (another product), it
    reaches the files Apply to all gave the first one; taken back, it is taken back from them (each back on its SMS
    default)."""
    root = _exports(tmp_path, field, {"A": (slice(None), "Variety1"), "B": (slice(0, None, 2), "Variety1"),
                                      "C": (slice(1, None, 2), "Variety1"), "D": (slice(0, None, 3), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c, d = _open_all(at, root, 4)
    assert [_prod(at, t)[:2] for t in (a, b, c, d)] == [("default", None)] * 3 + [("default", "wheat")]
    _pick(at, d)
    _clean(at)
    before = _state(at, d)
    _pick(at, a)
    _set_import(at, prod="barley")
    g = by_key(at.button, "fi_goall_")
    assert g.label == "Apply to all 4 harvest files" and not g.disabled
    line = _orange(at)
    ch = "Product unknown → barley; Weight to volume none → 48.00; Dry moisture none → 14.50"
    assert f"Apply to all also changes {b} ({ch}), {c} ({ch})." in line, line
    own = "it keeps its own product; a product chosen here goes only to files that had this file's product"
    assert f"Apply to all leaves {d} (Product wheat) as it is: {own} (unknown) and the same own choice of it." in line, \
        line
    g.click().run()
    assert not at.exception, at.exception
    assert [_prod(at, t) for t in (a, b, c)] == [("custom", "barley", 48.0, 14.5, None)] * 3
    assert _state(at, d) == before and d in at.session_state["cleaned"]
    msg = " ".join(s.value for s in at.success)
    assert f"Changed in {b}: {ch}." in msg and f"Left as it is: {d} (Product wheat); {own} (unknown)" in msg, msg
    _set_import(at, prod="wheat")                         # the product chosen again: the files that had it follow
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert [_prod(at, t) for t in (a, b, c)] == [("custom", "wheat", 60.0, 13.5, None)] * 3
    assert _state(at, d) == before
    by_key(at.selectbox, "fi_prod_").select_index(0).run()        # 'unknown' again: each back on its SMS default
    assert not at.exception, at.exception
    line = _orange(at)
    assert (f"{b} (Product wheat → unknown; Weight to volume 60.00 → none; Dry moisture 13.50 → none; back on its SMS "
            "default)") in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    for t in (a, b, c):
        D = _D(at, t)
        assert D["import_mode"] == "default" and D["shp"] == D["import_default"]["shp"], t
    assert _state(at, d) == before


def test_apply_to_all_carries_a_product_with_its_own_values_to_files_of_the_same_product(field, tmp_path,
                                                                                         monkeypatch):
    """A product chosen on a wheat file, with a weight to volume typed, applied to all: the other wheat file gets the
    product and that weight (its own weight for wheat goes, its own maximum stays); a canola file set to wheat in step
    2 keeps its product (its own choice, not this file's), and a canola file is of another product: both are left as
    they are, with their cleanings."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), "Canola"), "D": (slice(0, None, 3), "Canola")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c, d = _open_all(at, root, 4)
    _pick(at, b)
    _apply_import(at, tw=62.0, max=150.0)
    _pick(at, c)
    _apply_import(at, prod="wheat")
    _clean(at)
    _pick(at, d)
    _clean(at)
    before = {t: _state(at, t) for t in (c, d)}
    _pick(at, a)
    _set_import(at, prod="barley")
    _set_import(at, tw=50.0)
    line = _orange(at)
    assert (f"Apply to all also changes {b} (Product wheat → barley; Weight to volume 62.00 → 50.00; Dry moisture "
            "13.50 → 14.50).") in line, line
    assert (f"Apply to all leaves {d} (Product canola) as it is: it keeps its own product; a product chosen here goes "
            "only to files that had this file's product (wheat) and the same own choice of it.") in line, line
    # C has wheat too, chosen on it for its canola data: left in its own words (amendment A1.3)
    assert (f"Apply to all leaves {c} (Product wheat) as it is: its wheat was chosen on it for its own data (canola), "
            "not with this file's choice: a product chosen here goes only to files whose product came from the same "
            "choice as this file's.") in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, a) == ("custom", "barley", 50.0, 14.5, None)
    assert _prod(at, b) == ("custom", "barley", 50.0, 14.5, 150.0)
    assert {t: _state(at, t) for t in (c, d)} == before and all(t in at.session_state["cleaned"] for t in (c, d))
    assert _prod(at, c)[:3] == ("custom", "wheat", 60.0)


def test_apply_to_all_reaches_own_settings_on_a_failed_default_and_names_a_failed_import(field, tmp_path,
                                                                                         monkeypatch):
    """Two exports whose SMS default import failed at open: one with own settings applied since (a working import as
    SMS), one still on the readings the failed import left. A minimum applied to all reaches the first (its own
    maximum stays) and leaves the second, which is counted on the button and named before and after the click with
    its reason (Apply on it tries the import again), never as a file with no import to change."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "F": (slice(0, None, 2), None),
                                      "G": (slice(1, None, 2), None)})
    real = si.apply

    def failing(src, *x, **k):
        if os.path.basename(str(src)) in ("Harvest_F.shp", "Harvest_G.shp"):
            raise OSError("synthetic write failure")
        return real(src, *x, **k)
    monkeypatch.setattr(si, "apply", failing)
    at = _app(tmp_path / "ws", monkeypatch)
    a, f, g = _open_all(at, root, 3)
    monkeypatch.setattr(si, "apply", real)
    at.run()
    assert all(_D(at, t)["import_default"].get("error") for t in (f, g))
    _pick(at, f)
    _apply_import(at, max=150.0)
    assert _D(at, f)["import_mode"] == "custom" and _D(at, f)["import_default"].get("error")
    before = _state(at, g)
    _pick(at, a)
    _set_import(at, min=5.0)
    b = by_key(at.button, "fi_goall_")
    assert b.label == "Apply to all 3 harvest files", b.label
    line = _orange(at)
    assert f"Apply to all also changes {f} (Min. yield volume 0.000 → 5.000)." in line, line
    assert f"Apply to all leaves {g} as it is: its SMS import failed: Apply on it tries it again." in line, line
    b.click().run()
    assert not at.exception, at.exception
    RF = _D(at, f)["sms_import"]["resolved"]
    assert (RF["min_yield"], RF["max_yield"]) == (5.0, 150.0)
    assert _state(at, g) == before
    msg = " ".join(s.value for s in at.success)
    assert f"Left as it is (its SMS import failed: Apply on it tries it again): {g}." in msg, msg
    assert "no import as SMS to change" not in msg, msg


def test_apply_to_all_names_and_keeps_a_file_on_none(field, tmp_path, monkeypatch):
    """A file on 'Import: None' (as it is), cleaned: Apply to all names it as left as it is, before and after the
    click, and leaves its import and its cleaning exactly as they were."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b = _open_all(at, root, 2)
    _pick(at, b)
    _apply_import(at, how="none")
    assert _D(at, b)["import_mode"] == "as_is"
    _clean(at)
    before = _state(at, b)
    _pick(at, a)
    _set_import(at, max=150.0)
    assert f"Apply to all leaves {b} as it is: no import as SMS ('None' in step 2)." in _orange(at), _orange(at)
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _state(at, b) == before and b in at.session_state["cleaned"]
    msg = " ".join(s.value for s in at.success)
    assert f"Left as it is (no import as SMS, 'None' in step 2): {b}." in msg, msg


def _sig(shp):
    """The content of a shapefile: its .shp and its .dbf (without the date in the .dbf header)."""
    import hashlib
    h, base = hashlib.md5(), os.path.splitext(shp)[0]
    h.update(open(base + ".shp", "rb").read())
    b = open(base + ".dbf", "rb").read()
    h.update(b[:1] + b[4:])
    return h.hexdigest()


def _as_0_3_0_with_step_1s_product(at, wd, tags):
    """The saved work as 0.3.0 left point exports opened with a product chosen in step 1 (one product for every
    file): each file's import under the default's name, no default block, and a record that names no crop, monitor
    product, format, revision nor mode (0.3.0 never read the data's crop when step 1 had a product), its import without
    the crop labels this version writes."""
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    for t in tags:
        D = _D(at, t)
        own, dflt = os.path.splitext(D["shp"])[0], os.path.splitext(D["import_default"]["shp"])[0]
        for q in glob.glob(dflt + ".*"):
            os.remove(q)
        for q in glob.glob(own + ".*"):
            os.replace(q, dflt + q[len(own):])
        # 0.3.0 wrote no crop labels in a point export's import: the ones this version writes (Product, Crop) go
        g = pyogrio.read_dataframe(dflt + ".shp")
        if "Crop" in g.columns:
            g0 = pyogrio.read_dataframe(D["import_default"]["basis"]["all_readings"], read_geometry=False)
            assert len(g0) == len(g)
            g = g.drop(columns=["Crop"]).assign(Product=g0["Product"].to_numpy())
            pyogrio.write_dataframe(g, dflt + ".shp")
        Dr = rec["datasets"][t]
        for k in ("import_default", "import_mode"):
            Dr.pop(k, None)
        Dr["shp"] = os.path.relpath(dflt + ".shp", wd) if not os.path.isabs(Dr["shp"]) else dflt + ".shp"
        IM = Dr["sms_import"]
        for k in ("mode", "revision", "own_yields", "product_from"):
            IM.pop(k, None)
        IM.update({"crop": None, "monitor": None, "fmt": None})
    json.dump(rec, open(p, "w", encoding="utf-8"))


def test_a_0_3_0_export_imported_with_step_1s_product_keeps_its_datas_crop(field, tmp_path, monkeypatch):
    """Point exports 0.3.0 opened with barley chosen in step 1 (its record names no crop then): two of wheat data, two
    of an unknown product. Opened again, a wheat file's SMS default is wheat's, byte for byte the default of a fresh
    open, and choosing wheat on it goes back to that default. The product taken back for all on an unknown file sends
    the other wheat file to its wheat default (0.3.0's one product for many files); wheat named for all on a wheat
    file goes to every file 0.3.0 gave barley, the unknown ones too (wheat, not their data's 'not known')."""
    root = _exports(tmp_path, field, {"A1": (slice(None), None), "A2": (slice(0, None, 2), None),
                                      "U1": (slice(1, None, 2), "Variety1"), "U2": (slice(0, None, 3), "Variety1")})
    at = _app(tmp_path / "ws", monkeypatch)
    a1, a2, u1, u2 = _open_all(at, root, 4)
    wd = at.session_state["workdir"]
    assert [_prod(at, t)[:2] for t in (a1, a2, u1, u2)] == [("default", "wheat")] * 2 + [("default", None)] * 2
    fresh = {t: _sig(_D(at, t)["import_default"]["shp"]) for t in (a1, a2)}
    for t in (a1, a2, u1, u2):
        _pick(at, t)
        _apply_import(at, prod="barley")
    _as_0_3_0_with_step_1s_product(at, wd, (a1, a2, u1, u2))
    keep = str(tmp_path / "work_030")
    shutil.copytree(wd, keep)
    _reopen(at, wd)
    _pick(at, a1)
    D, DF = _D(at, a1), _D(at, a1)["import_default"]
    assert D["import_mode"] == "custom" and D["sms_import"]["resolved"]["product"] == "barley"
    assert D["sms_import"]["product_from"]["by"] == "0.3.0" and si.crop_key(DF["basis"]["crop"]) == "wheat"
    R0 = DF["sms_import"]["resolved"]
    assert (R0["product"], R0["test_weight_lb_bu"], R0["dry_moisture_pct"]) == ("wheat", 60.0, 13.5)
    assert _sig(DF["shp"]) == fresh[a1]
    b1 = _badge_lines(at)
    assert b1[0].startswith("SMS default") and "wheat" in b1[0] and "not known" not in b1[0], b1
    _apply_import(at, prod="wheat")                       # the data's own crop: back to its SMS default
    assert _prod(at, a1)[:2] == ("default", "wheat") and _sig(_D(at, a1)["shp"]) == fresh[a1]
    assert "these are SMS's default settings: back to the default import" in " ".join(x.value for x in at.success)
    _pick(at, u1)
    _switch_off(at)
    by_key(at.selectbox, "fi_prod_").select_index(0).run()        # 'unknown': taken back for all, each on its data's
    assert not at.exception, at.exception
    line = _orange(at)
    assert (f"{a2} (Product barley → wheat; Weight to volume 48.00 → 60.00; Dry moisture 14.50 → 13.50; back on its "
            "SMS default)") in line, line
    assert f"{u2} (Product barley → unknown;" in line and f"Apply to all leaves {a1} (Product wheat) as it is" in line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert [_prod(at, t)[:2] for t in (a1, a2, u1, u2)] == [("default", "wheat")] * 2 + [("default", None)] * 2
    assert _sig(_D(at, a2)["shp"]) == fresh[a2]
    # the same 0.3.0 work again: wheat named for all on a wheat file
    at.button(key="start_over").click().run()
    shutil.rmtree(wd)
    shutil.copytree(keep, wd)
    at.selectbox(key="work_pick").set_value(wd).run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    _pick(at, a1)
    _set_import(at, prod="wheat")
    line = _orange(at)
    ch = "Product barley → wheat; Weight to volume 48.00 → 60.00; Dry moisture 14.50 → 13.50"
    assert f"Apply to all also changes {a2} ({ch}; back on its SMS default), {u1} ({ch}), {u2} ({ch})." in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert [_prod(at, t) for t in (a1, a2)] == [("default", "wheat", 60.0, 13.5, None)] * 2
    assert [_prod(at, t) for t in (u1, u2)] == [("custom", "wheat", 60.0, 13.5, None)] * 2


def test_apply_to_all_never_takes_a_product_chosen_on_a_file_of_other_data(field, tmp_path, monkeypatch):
    """Two wheat exports (B with its own weight to volume and maximum) and two canola ones, C set to barley by hand and
    cleaned. Barley chosen on A for all reaches B (its own weight goes with the product, its maximum stays), never the
    canola files, each named with its product. Wheat named on A again reaches B (barley as Apply to all gave it) and
    still not C, whose barley was chosen on it: C keeps its import and its cleaning."""
    root = _exports(tmp_path, field, {"A": (slice(None), None), "B": (slice(0, None, 2), None),
                                      "C": (slice(1, None, 2), "Canola"), "E": (slice(0, None, 3), "Canola")})
    at = _app(tmp_path / "ws", monkeypatch)
    a, b, c, e = _open_all(at, root, 4)
    _pick(at, b)
    _apply_import(at, tw=62.0, max=150.0)
    _pick(at, c)
    _apply_import(at, prod="barley")
    _clean(at)
    _pick(at, e)
    _clean(at)
    before = {t: _state(at, t) for t in (c, e)}
    own = "each keeps its own product; a product chosen here goes only to files that had this file's product"
    _pick(at, a)
    _set_import(at, prod="barley")
    line = _orange(at)
    assert (f"Apply to all also changes {b} (Product wheat → barley; Weight to volume 62.00 → 48.00; Dry moisture "
            "13.50 → 14.50).") in line, line
    assert f"Apply to all leaves {c} (Product barley), {e} (Product canola) as they are: {own} (wheat)" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, b) == ("custom", "barley", 48.0, 14.5, 150.0)
    assert {t: _state(at, t) for t in (c, e)} == before
    _set_import(at, prod="wheat")                         # A's data's own crop, named: the files that had barley
    line = _orange(at)
    assert (f"Apply to all also changes {b} (Product barley → wheat; Weight to volume 48.00 → 60.00; Dry moisture "
            "14.50 → 13.50).") in line, line
    hand = (f"{c} (Product barley) as it is: its barley was chosen on it for its own data (canola), not with this "
            "file's choice: a product chosen here goes only to files whose product came from the same choice as this "
            "file's.")
    assert f"Apply to all leaves {e} (Product canola) as it is: it keeps its own product" in line, line
    assert f"Apply to all leaves {hand}" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, a) == ("default", "wheat", 60.0, 13.5, None)
    assert _prod(at, b) == ("custom", "wheat", 60.0, 13.5, 150.0)
    assert {t: _state(at, t) for t in (c, e)} == before and all(t in at.session_state["cleaned"] for t in (c, e))
    msg = " ".join(x.value for x in at.success)
    assert f"Left as it is: {e} (Product canola); it keeps its own product" in msg, msg
    assert (f"Left as it is: {c} (Product barley); its barley was chosen on it for its own data (canola), not with "
            "this file's choice") in msg, msg


def test_apply_to_all_keeps_a_limit_the_product_does_not_change_and_a_product_chosen_by_hand(field, tmp_path,
                                                                                            monkeypatch):
    """Exports of an unknown product (U2 with its own maximum) and a canola export set to barley by hand (Cb), with a
    Case IH card of an unknown crop. Barley chosen on the card (its table fills in a maximum) for all: the exports get
    barley, U2 keeps its own maximum (barley sets none on a point export), Cb is left. Wheat chosen on an unknown export
    for all then reaches the files Apply to all gave barley, the card too, never Cb (its barley chosen on it)."""
    from engine.formats import cnh_cn1 as CN
    from tests import synthetic_cn1 as SC
    root = _exports(tmp_path, field, {"U1": (slice(None), "Variety1"), "U2": (slice(0, None, 2), "Variety1"),
                                      "Cb": (slice(1, None, 2), "Canola")})
    cd = SC.make_card(str(root / "CNH"))
    for q in glob.glob(os.path.join(cd["card"], "COMBINES", "*", "*.ycs")):
        os.remove(q)
    for q in glob.glob(os.path.join(cd["card"], "**", "*.tso"), recursive=True):
        bb = bytearray(open(q, "rb").read())
        bb[CN.HDR + 52] = 99
        open(q, "wb").write(bytes(bb))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root)
    for i in range(len(at.selectbox(key="cand_idx").options)):
        at.selectbox(key="cand_idx").select_index(i).run()
        assert not at.exception, at.exception
        if by_key(at.button, "extract_") is not None:
            _extract(at)
    tags = sorted(at.session_state["datasets"])
    assert len(tags) == 4, tags
    card = next(t for t in tags if _D(at, t).get("kind") == "raw")
    u1, u2, cb = "Harvest_U1", "Harvest_U2", "Harvest_Cb"
    assert _prod(at, card)[:2] == ("default", None)
    _pick(at, u2)
    _apply_import(at, max=150.0)
    _pick(at, cb)
    _apply_import(at, prod="barley")
    _clean(at)
    before = _state(at, cb)
    _pick(at, card)
    _set_import(at, prod="barley")
    assert by_key(at.number_input, "fi_max_").value is not None      # the card's table fills in a maximum
    line = _orange(at)
    ch = "Product unknown → barley; Weight to volume none → 48.00; Dry moisture none → 14.50"
    assert f"{u1} ({ch})" in line and f"{u2} ({ch})" in line and "150.00 → none" not in line, line
    assert f"Apply to all leaves {cb} (Product barley) as it is: it keeps its own product" in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, u1) == ("custom", "barley", 48.0, 14.5, None)
    assert _prod(at, u2) == ("custom", "barley", 48.0, 14.5, 150.0)
    assert _state(at, cb) == before
    _pick(at, u1)
    _set_import(at, prod="wheat")
    line = _orange(at)
    ch = "Product barley → wheat; Weight to volume 48.00 → 60.00; Dry moisture 14.50 → 13.50"
    assert f"{u2} ({ch})" in line and f"{card} (Product barley → wheat" in line, line
    assert (f"Apply to all leaves {cb} (Product barley) as it is: its barley was chosen on it for its own data "
            "(canola), not with this file's choice") in line, line
    by_key(at.button, "fi_goall_").click().run()
    assert not at.exception, at.exception
    assert _prod(at, u2) == ("custom", "wheat", 60.0, 13.5, 150.0) and _prod(at, card)[:2] == ("custom", "wheat")
    assert _state(at, cb) == before and cb in at.session_state["cleaned"]


def test_a_default_whose_write_failed_gives_its_reason_once(field, tmp_path, monkeypatch):
    """Own settings, the default's files gone and its write failing (not a held file, not a full disk): Apply with
    SMS's values imports the default once (no second try) and says why, with no full path and no advice about a held
    file; a write refused (access denied) says to close the program that holds the files."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, max=150.0)
    t = at.session_state["active"]
    for q in glob.glob(os.path.splitext(_D(at)["import_default"]["shp"])[0] + ".*"):
        os.remove(q)
    calls = []

    def gdal(src, out, R, *a, **k):
        calls.append(out)
        raise RuntimeError(f"Failed to create file {out}: No such file or directory")
    monkeypatch.setattr(si, "apply", gdal)
    at.run()
    calls.clear()
    _set_import(at, max=None)                             # SMS's default values: back to the default
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    err = [e.value for e in at.error]
    assert len(calls) == 1 and len(err) == 1, (calls, err)
    assert (f"{t}: SMS's default import of this file could not be made (RuntimeError: Failed to create file "
            f"{t}_imported_next.shp: No such file or directory): the file and its import are unchanged; try again "
            "(step 1 keeps the reason)") in err[0], err
    assert ":\\" not in err[0] and "close the program" not in err[0], err
    assert _D(at)["import_mode"] == "custom"

    def held(src, out, R, *a, **k):
        raise PermissionError(13, "Access is denied", out)
    monkeypatch.setattr(si, "apply", held)
    at.run()
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    err = [e.value for e in at.error]
    assert err and "(PermissionError: Access is denied)" in err[0] and "close the program that holds" in err[0], err


def test_messages_name_a_file_and_its_folder_never_a_full_path(field, tmp_path, monkeypatch):
    """The readings of a file gone (moved out of the work's input folder): step 2 says so in place of what Apply would
    do, with own settings and with 'None', naming the file and its folder only, and offers no Apply (amendment A1.3,
    verification round 2); opening an input that fails, and a save that fails, give the error in a few words, with no
    full path and no Windows error number."""
    from engine import run as er
    from engine import works as ew
    root = _exports(tmp_path, field, {"A": (slice(None), None)})
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, root / "A" / "Harvest_A.shp")
    _apply_import(at, max=150.0)
    rd = os.path.splitext(_D(at)["import_default"]["basis"]["all_readings"])[0]
    assert os.path.basename(rd) == "Harvest_A" and os.path.basename(os.path.dirname(rd)) == "input", rd
    away = str(tmp_path / "away")
    os.makedirs(away)
    parts = glob.glob(rd + ".*")
    for q in parts:
        os.replace(q, os.path.join(away, os.path.basename(q)))
    try:
        t = at.session_state["active"]
        said = (f"The readings {t} is imported from are no longer in the work folder (Harvest_A.shp in the folder "
                "input): open its data again (step 1) to change its import.")
        for how in ("sms", "none"):
            _set_import(at, **({"max": 140.0} if how == "sms" else {"how": "none"}))
            line = _orange(at)
            assert said in line, (how, line)
            assert str(tmp_path) not in line and ":\\" not in line, line
            assert by_key(at.button, "fi_go_").disabled, how
    finally:
        for q in parts:
            os.replace(os.path.join(away, os.path.basename(q)), q)

    def broken(paths, wd, log=None):
        raise RuntimeError(r"[WinError 5] cannot read C:\Users\user.name 2\run v1.2 data\z.shp: bad header")
    monkeypatch.setattr(er, "open_input", broken)
    at.text_input(key="path_in").input(str(root / "A" / "Harvest_A.shp"))
    at.button(key="open_btn").click().run()
    assert at.session_state["open_error"] == "Opening failed (RuntimeError: cannot read z.shp: bad header)"

    def refused(wd, rec):
        raise PermissionError(13, "Access is denied", os.path.join(wd, "oced_work.json"))
    monkeypatch.setattr(ew, "save_work", refused)
    at.button(key="work_save").click().run()
    toasts = [x.value for x in at.toast]
    assert "The work could not be saved (PermissionError: Access is denied)" in toasts, toasts


def test_a_default_swapped_in_removes_an_import_a_blocked_swap_left(field, tmp_path, monkeypatch):
    """An import a swap blocked earlier left under a temporary name (<tag>_imported_next2), named by nothing: once
    SMS's default is made again and swapped in, it goes; the import in use (own settings) stays."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, max=150.0)
    t = at.session_state["active"]
    dflt = os.path.splitext(_D(at)["import_default"]["shp"])[0]
    left = os.path.join(os.path.dirname(dflt), f"{t}_imported_next2")
    for q in glob.glob(dflt + ".*"):
        os.replace(q, left + q[len(dflt):])
    assert glob.glob(left + ".*")
    at.run()
    assert not at.exception, at.exception
    DF = _D(at)["import_default"]
    assert os.path.exists(DF["shp"]) and not glob.glob(left + ".*"), glob.glob(left + ".*")
    assert _D(at)["import_mode"] == "custom" and _D(at)["sms_import"]["resolved"]["max_yield"] == 150.0
    assert os.path.exists(_D(at)["shp"])


def test_error_reasons_name_a_file_never_its_full_path():
    """An error in a few words names a path in it by its file name only: folders with spaces and dots (a user name, a
    version, a date), two paths in one message (the words between them kept), quoted paths, //server and \\\\server
    paths; a drive-like 'D:5' and a URL stay as they are. The advice after a failed write follows its reason."""
    import ntpath
    import re

    from tests.test_app_fixes import _app_defs
    ns = _app_defs({"re": re, "os": os, "ntpath": ntpath}, "_PATH_START", "_PATH_CHAR", "_PATH_IN_TEXT",
                   "_error_reason", "retry_advice")
    er_, adv = ns["_error_reason"], ns["retry_advice"]
    BS = "\\"
    cases = {r"cannot open C:\a b\x.shp (see the docs/notes)": "cannot open x.shp (see the docs/notes)",
             "Failed to create file C:/Users/u/OCED work/run 2026.11.13 data/x_imported_next.shp: Permission denied":
                 "Failed to create file x_imported_next.shp: Permission denied",
             r"bad value in C:\data\file.v2 backup\a.shp": "bad value in a.shp",
             r"C:\Users\user.name 2\x.shp locked": "x.shp locked",
             r"C:\proj\run v1.2 final\x.shp locked": "x.shp locked",
             r"C:\work\20261113-164243_run v1.2 data\decoded\F_imported_next.dbf: denied":
                 "F_imported_next.dbf: denied",
             r"C:\dir\sub, then D:\e\f.dbf; done": "sub, then f.dbf; done",
             r"C:\a\x.shp and C:\b\y.shp": "x.shp and y.shp",
             r"C:\a\x.shp and //srv/share/y.shp": "x.shp and y.shp",
             r"Error in 'C:\x\y z\a.shp' and 'C:\x\b.dbf'": "Error in 'a.shp' and 'b.dbf'",
             r"C:\Temp\x.shp: No such file": "x.shp: No such file",
             BS * 2 + r"server\share\y.shp, z": "y.shp, z",
             "see //server/share/dir/y.shp": "see y.shp",
             r"field D:5 has C:\a\b with no extension": "field D:5 has b with no extension",
             "url https://a.b/c.html failed": "url https://a.b/c.html failed",
             r"[WinError 32] in use: C:\a\x.dbf": "in use: x.dbf"}
    for msg, want in cases.items():
        assert er_(RuntimeError(msg)) == "RuntimeError: " + want, msg
    assert er_(PermissionError(13, "Access is denied", r"C:\x\y.dbf")) == "PermissionError: Access is denied"
    assert adv("PermissionError: Access is denied").startswith("close the program that holds its files")
    assert adv("OSError: No space left on device").startswith("free disk space")
    assert adv("RuntimeError: Failed to create file x.shp: No such file or directory") == ("try again (step 1 keeps "
                                                                                          "the reason)")


def test_a_blocked_rename_names_the_file_never_its_full_path(tmp_path, monkeypatch):
    """An import written under its temporary name whose rename is refused (a part held open): the temporary file stays
    in use, every part renamed before is put back, and the warning names the part by its file name only."""
    import ntpath
    import re

    from tests.test_app_fixes import _app_defs
    ns = _app_defs({"re": re, "os": os, "ntpath": ntpath}, "_PATH_START", "_PATH_CHAR", "_PATH_IN_TEXT",
                   "_error_reason", "_parts", "_remove_files", "_swap_in")
    d = tmp_path / "run v1.2 data" / "imported"
    os.makedirs(d)
    nxt = str(d / "T_imported_next.shp")
    for e in (".dbf", ".shp", ".shx"):
        open(nxt[:-4] + e, "wb").write(e.encode())
    real = os.replace

    def held(a, b):
        if a.endswith(".shp"):
            raise PermissionError(13, "Access is denied", a)
        return real(a, b)
    monkeypatch.setattr(os, "replace", held)
    path, w = ns["_swap_in"](nxt, str(d / "T_imported_custom.shp"))
    monkeypatch.setattr(os, "replace", real)
    assert path == nxt and w == ["T_imported_next.shp could not be renamed (PermissionError: Access is denied): the "
                                 "new import is T_imported_next.shp"], w
    assert sorted(os.listdir(d)) == ["T_imported_next.dbf", "T_imported_next.shp", "T_imported_next.shx"]


def test_the_decoders_own_words_stay_for_the_same_weight_and_moisture():
    """The decode source of a raw file for an import that converts its yields: a weight to volume or dry moisture equal
    to the decoder's keeps the decoder's own words for it; another value is written in."""
    import copy
    import re

    from tests.test_app_fixes import _app_defs
    ns = _app_defs({"re": re, "copy": copy, "si": si}, "NO_PRODUCT_TAIL", "_same_value", "source_with_import")
    cs = ("flow 2.00 g/s per count; test weight 48.0 lb/bu (the monitor's profile); standard moisture 14.50 % (the "
          "monitor's profile); shrink one-sided")
    src = {"options": {"crop": None, "test_weight_lb_bu": 48.0, "std_moisture_pct": 14.5, "shrink": "one_sided"},
           "calibration_summary": cs}
    R = {"product": None, "test_weight_lb_bu": 48.0, "dry_moisture_pct": 14.5, "expand_dry_moisture": False}
    s = ns["source_with_import"](src, R, {"weight_and_moisture": True})
    assert s["calibration_summary"] == cs and s is not src
    s = ns["source_with_import"](src, {**R, "test_weight_lb_bu": 60.0}, {"weight_and_moisture": True})
    assert "test weight 60.00 lb/bu" in s["calibration_summary"] and "48.0" not in s["calibration_summary"]
    assert "standard moisture 14.50 % (the monitor's profile)" in s["calibration_summary"]
    assert s["options"]["test_weight_lb_bu"] == 60.0 and src["options"]["test_weight_lb_bu"] == 48.0


def test_a_custom_import_names_a_four_decimal_test_weight_as_its_import_row_does():
    """0.3.2 (R2): a custom import of a card whose test weight has 4 decimals (60.0098 lb/bu): with another dry
    moisture the decoder's own words stay for the weight and the report's Source paragraph gives it with 2 decimals;
    with Use Manual Moisture and another weight, the app writes it with 2 decimals; either way the Source paragraph
    and the Import as SMS row say 60.01 lb/bu (one rule, 2 decimals)."""
    import copy
    import re

    from engine.report import clean_report as cr
    from tests.test_app_fixes import _app_defs
    ns = _app_defs({"re": re, "copy": copy, "si": si}, "NO_PRODUCT_TAIL", "_same_value", "source_with_import")
    cs = ("flow 2.00 g/s per count; test weight 60.0098 lb/bu; standard moisture 13.0 %; shrink one-sided")
    src = {"label": "Synthetic card", "options": {"crop": None, "test_weight_lb_bu": 60.0098, "std_moisture_pct": 13.0,
                                                  "shrink": "one_sided"}, "calibration_summary": cs}
    R0 = {"product": None, "test_weight_lb_bu": 60.0098, "dry_moisture_pct": 13.0, "expand_dry_moisture": False,
          "use_manual_moisture": False, "manual_moisture_pct": None, "use_manual_swath": False,
          "manual_swath_ft": None, "min_yield": 5.0, "max_yield": 10000.0, "start_delay_s": 0.0, "stop_delay_s": 0.0,
          "flow_shift_s": 0.0}
    for R in ({**R0, "dry_moisture_pct": 12.0},
              {**R0, "test_weight_lb_bu": 60.0098 + 1e-3, "use_manual_moisture": True, "manual_moisture_pct": 16.0}):
        s = ns["source_with_import"](src, R, {"weight_and_moisture": True})
        txt = cr._source_text({"source": s, "sms_import": {"resolved": R}})
        assert re.findall(r"test weight ([\d.]+) lb/bu", txt) == ["60.01"], txt
        assert "60.0098" not in txt and "weight to volume 60.01 lb/bu" in si.describe(R)


def test_an_older_decodes_line_and_help_name_what_its_yields_carry():
    """A default made from the readings an older version decoded with a product: its line names the decode's values
    when the import keeps the yields, else the import's (the product not known when it has none); its help calls it SMS's
    conversion when the import converts the yields, with the way to confirm SMS's default only when the decoding options
    were not SMS's, and 'not SMS's default import' when the import keeps the decode's yields."""
    from tests.test_app_fixes import _app_defs
    way = "put its raw data back in the folder card (reconnect the drive) and open the work again for SMS's default"
    ns = _app_defs({"si": si, "older_decode_way": lambda D: way, "default_view": lambda D: D,
                    "decoding_not_sms": lambda s_, r: list((r or {}).get("not_sms") or [])},
                   "older_decode_text", "older_decode_help", "yields_converted", "_tw_dm_text", "older_decode_values",
                   "import_values_text")
    RS = {"product": None, "test_weight_lb_bu": 50.0, "dry_moisture_pct": 13.0, "min_yield": 0.0, "max_yield": None}
    conv = {"older_decode": "product barley", "older": ["its raw data is not at hand"], "report": {},
            "sms_import": {"applied": {"weight_and_moisture": True}, "resolved": RS}}
    kept = {**conv, "report": {"options": {"test_weight_lb_bu": 48.0, "std_moisture_pct": 14.5}},
            "sms_import": {"applied": {"weight_and_moisture": False}, "resolved": RS}}
    assert ns["older_decode_text"](conv, RS) == ("decoded by an older OCED with product barley, the yields converted "
                                                 "with the product not known (50.00 lb/bu, 13.00 %) · min 0.000 "
                                                 "bu/ac, no maximum")
    assert ns["older_decode_text"](kept, RS) == ("decoded by an older OCED with product barley (48.00 lb/bu, 14.50 %) "
                                                 "· min 0.000 bu/ac, no maximum")
    assert ns["older_decode_help"](conv) == ("Decoded by an older OCED with product barley (its raw data is not at "
                                             "hand); the import converts its yields with its weight to volume and dry "
                                             "moisture as SMS's default does.")
    wheat = {**conv, "sms_import": {**conv["sms_import"], "resolved": {**RS, "product": "wheat"}}}
    h = ns["older_decode_help"]({**wheat, "report": {"not_sms": ["the crop's latest calibration"]}})
    assert h == ("Decoded by an older OCED with product barley (its raw data is not at hand); the import converts its "
                 f"yields with wheat as SMS's default does; its decoding options are not SMS's: to confirm SMS's "
                 f"default, {way}."), h
    assert "not SMS's default import" not in ns["older_decode_help"](wheat)
    assert ns["older_decode_help"](kept) == ("Decoded by an older OCED with product barley, not as SMS's default "
                                             "decodes it, so this is not SMS's default import (its raw data is not at "
                                             f"hand). To get SMS's default, {way}.")


# ------------------------------------------------------------------------------------------------ works of 0.3.0
def _card_030(tmp_path, monkeypatch, crop_on_card: bool = False) -> dict:
    """A Case IH card whose crop the card does not define (crop_on_card: the card names its crop, a wheat), extracted
    by 0.3.0 with a product chosen before extracting (barley: every reading decoded with it, the import under the
    default's name, no default block), cleaned and saved: {at, t, wd, work_030: the saved work as 0.3.0 left it, imp:
    the shapefile of 0.3.0's import, fresh: SMS's default import of a fresh open (its table), warn0: the fresh open's
    'crop not known' warnings, C0: the cleaning}."""
    import dataclasses

    from engine import run as er
    from engine.formats import cnh_cn1 as CN
    from engine.formats import detect
    from tests import synthetic_cn1 as SC
    cd = SC.make_card(str(tmp_path / "cnh"))
    for p in glob.glob(os.path.join(cd["card"], "COMBINES", "*", "*.ycs")) if not crop_on_card else ():
        os.remove(p)
    for p in glob.glob(os.path.join(cd["card"], "**", "*.tso"), recursive=True) if not crop_on_card else ():
        b = bytearray(open(p, "rb").read())
        b[CN.HDR + 52] = 99
        open(p, "wb").write(bytes(b))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cd["card"])
    _extract(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    fresh = pyogrio.read_dataframe(_D(at)["import_default"]["shp"], read_geometry=False)
    warn0 = [w for w in _D(at)["report"].get("warnings") or [] if "crop not known" in w]
    assert bool(warn0) != crop_on_card
    _apply_import(at, prod="barley")
    C0 = _clean(at)
    at.button(key="work_save").click().run()
    # as 0.3.0 left it: every reading decoded with barley, the import under the default's name, no default block
    D = _D(at)
    cand = next(c for c in detect.detect([cd["card"]]) if c.get("kind") == "raw")
    Rb = si.resolve(si.settings({"product": "barley"}), None, None, cand["decoder"])
    o = dataclasses.replace(detect.default_options(cand["decoder"]), shrink="one_sided", crop="barley",
                            test_weight_lb_bu=Rb["test_weight_lb_bu"], std_moisture_pct=Rb["dry_moisture_pct"])
    d = er.decode(cand, D["source"]["unit_ids"], o, wd, log=lambda m: None, tag=t,
                  **dict(D["source"].get("decoder_kwargs") or {}))
    assert os.path.normcase(d["shp"]) == os.path.normcase(D["sms_import"]["all_readings"])
    own, dflt = os.path.splitext(D["shp"])[0], os.path.splitext(D["import_default"]["shp"])[0]
    for p in glob.glob(dflt + ".*"):
        os.remove(p)
    for p in glob.glob(own + ".*"):
        os.replace(p, dflt + p[len(own):])
    rec = _as_saved_by_0_3_0(wd, t)
    Dr = rec["datasets"][t]
    Dr["shp"] = os.path.relpath(dflt + ".shp", wd) if not os.path.isabs(Dr["shp"]) else dflt + ".shp"
    Dr["report"] = json.load(open(d["report_json"], encoding="utf-8"))
    Dr["sms_import"].pop("mode", None)
    return {"at": at, "t": t, "wd": wd, "work_030": json.dumps(rec), "imp": dflt + ".shp", "fresh": fresh,
            "warn0": warn0, "C0": C0, "readings": d["shp"]}


def test_a_0_3_0_card_decoded_with_a_product_gets_sms_default_from_its_raw_data(tmp_path, monkeypatch):
    """A Case IH card whose crop the card does not define, extracted by 0.3.0 with a product chosen before extracting
    (its readings decoded with that product): step 1's SMS default is the raw data decoded again as a fresh open
    decodes it (the same yields and warnings, no product's label), never those readings; the import in use and its
    cleaning stay. With the raw data gone, step 1 names that import the older version's ('Older rule'), not SMS's
    default; once the raw data is back, the default is decoded again. Back to SMS's default, the file reads that
    decode, and 0.3.0's import and readings, named by nothing any more, are removed."""
    import numpy as np
    K = _card_030(tmp_path, monkeypatch)
    at, t, wd, work_030, fresh, C0 = K["at"], K["t"], K["wd"], K["work_030"], K["fresh"], K["C0"]
    dflt = os.path.splitext(K["imp"])[0]
    p = os.path.join(wd, "oced_work.json")

    def sms_default_from_the_raw_data():
        D = _D(at)
        DF = D["import_default"]
        g = pyogrio.read_dataframe(DF["shp"], read_geometry=False)
        assert len(g) == len(fresh) and "Crop" not in g.columns
        assert np.allclose(g["Yld_Vol_Dr"].to_numpy(float), fresh["Yld_Vol_Dr"].to_numpy(float), equal_nan=True)
        assert _badge_lines(at)[0].startswith("SMS default") and _first_metric(at, "Readings").value == f"{len(g):,}"
        assert not DF.get("older") and not DF.get("older_decode")
        assert D["import_mode"] == "custom" and os.path.normcase(D["shp"]) == os.path.normcase(dflt + ".shp")
        assert at.session_state["cleaned"][t]["R"]["n_kept"] == C0["R"]["n_kept"]
        # the own settings give the same import from step 1's readings, reading for reading: the record follows them
        # (decided by content, not by the readings' path), so step 2 does not call it made from an older decode
        assert (os.path.normcase(os.path.abspath(D["sms_import"]["all_readings"]))
                == os.path.normcase(os.path.abspath(DF["basis"]["all_readings"])))
        assert not any(c.value == ":orange[Made from an older decode]" for c in at.caption)
        # 0.3.0's product stays one for the files opened together (Apply to all reaches them as one)
        assert D["sms_import"].get("product_from") == {"by": "0.3.0", "group": "0.3.0"}
        # the warning names the field and season, as a fresh extraction does
        assert [w for w in DF["report"].get("warnings") or [] if "crop not known" in w] == K["warn0"]
    for gone in (False, True):
        open(p, "w", encoding="utf-8").write(work_030)
        if gone:
            os.replace(tmp_path / "cnh", tmp_path / "cnh_away")    # the raw data not at hand
        _reopen(at, wd)
        if not gone:
            sms_default_from_the_raw_data()
            continue
        D = _D(at)
        b1 = _badge_lines(at)
        assert b1[0].startswith("Older rule") and not any(x.startswith("SMS default") for x in b1), b1
        # named by the decode its yields carry, not as readings of no product
        assert "decoded by an older OCED with product barley (" in b1[0] and "not known" not in b1[0], b1
        assert D["import_default"]["older_decode"] == "product barley" and t in at.session_state["cleaned"]
        assert D["import_mode"] == "custom" and os.path.normcase(D["shp"]) == os.path.normcase(dflt + ".shp")
    os.replace(tmp_path / "cnh_away", tmp_path / "cnh")    # back: decoded again for SMS's default
    _reopen(at, wd)
    sms_default_from_the_raw_data()
    _back_to_default(at, confirm=True)
    D = _D(at)
    assert D["shp"] == D["import_default"]["shp"] and not (D["report"].get("options") or {}).get("crop")
    assert not glob.glob(dflt + ".*") and not glob.glob(os.path.splitext(K["readings"])[0] + ".s*")
    old = os.path.splitext(K["readings"])[0]                # (their zip and decode report, named by nothing, go too)
    assert not os.path.exists(old + ".zip") and not os.path.exists(old[:-len("_decoded")] + "_decode_report.json")


def test_a_0_3_0_card_of_a_named_crop_decoded_with_another_product_names_the_yields_converted(tmp_path, monkeypatch):
    """A Case IH card that names its crop, extracted by 0.3.0 with another product chosen before extracting (its
    readings decoded with that product's weight and moisture), opened while its raw data is away: SMS's default of
    those readings converts their yields with the card's crop, so step 1's line and the report's import line name the
    weight and moisture the yields now carry (the card crop's), with the decode's product named for the readings."""
    import numpy as np
    K = _card_030(tmp_path, monkeypatch, crop_on_card=True)
    at, t, wd = K["at"], K["t"], K["wd"]
    open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8").write(K["work_030"])
    os.replace(tmp_path / "cnh", tmp_path / "cnh_away")    # the raw data not at hand
    _reopen(at, wd)
    DF = _D(at)["import_default"]
    IM, R = DF["sms_import"], DF["sms_import"]["resolved"]
    assert DF["older_decode"] == "product barley" and R["product"] == "wheat"
    assert IM["applied"]["weight_and_moisture"] is True
    tw, dm = float(R["test_weight_lb_bu"]), float(R["dry_moisture_pct"])
    o = _D(at)["report"]["options"]
    assert (o["crop"], o["test_weight_lb_bu"]) == ("barley", 48.0) and tw != 48.0
    # the yields of SMS's default are the card crop's conversion of the readings, not those the decode gave them
    y_dec = pyogrio.read_dataframe(DF["basis"]["all_readings"], read_geometry=False)["Yld_Vol_Dr"].to_numpy(float)
    y_imp = pyogrio.read_dataframe(DF["shp"], read_geometry=False)["Yld_Vol_Dr"].to_numpy(float)
    assert abs(np.nanmean(y_imp) / np.nanmean(y_dec) - 1) > 0.05
    b1 = _badge_lines(at)
    assert b1[0].startswith("Older rule"), b1
    assert (f"decoded by an older OCED with product barley, the yields converted with wheat ({tw:,.2f} lb/bu, "
            f"{dm:.2f} %)") in b1[0] and "48.00 lb/bu" not in b1[0], b1
    # SMS's conversion of those readings (the card's decoding options are SMS's): not called 'not SMS's default'
    h1 = next(m.help for m in at.markdown if "oced-badge" in m.value)
    assert h1 == ("Decoded by an older OCED with product barley (its raw data is not at hand); the import converts its "
                  "yields with wheat as SMS's default does."), h1
    _back_to_default(at, confirm=True)                     # on the older version's readings
    assert _D(at)["import_mode"] == "default"
    C = _clean(at)
    from engine.report import clean_report as CR
    S = (C.get("R") or {}).get("settings") or C.get("settings") or {}
    line = CR._import_text(S["sms_import"])
    assert line.startswith("Decoded by an older OCED with product barley, kept (its raw data is not at hand): the "
                           f"yields converted with product wheat; weight to volume {tw:,.2f} lb/bu; dry moisture "
                           f"{dm:.2f} %"), line
    assert "as that decode gives them" not in line and "48.00" not in line, line
    assert S["test_weight_lb_bu"] == tw and S["moisture"]["standard_pct"] == dm
    _set_import(at, how="none")                           # decoded again as logged: the raw data is away
    line = _orange(at)
    assert (f"The raw data of {t} is not at hand (the folder " in line and "): reconnect the drive or open it again "
            "(step 1) to decode it as the monitor logged it." in line and str(tmp_path) not in line), line
    assert "Applying sets aside" not in line and by_key(at.button, "fi_go_").disabled, line


def test_a_0_3_0_card_cleaned_on_its_older_decode_is_set_aside_when_its_raw_data_is_back(tmp_path, monkeypatch):
    """The 0.3.0 card opened while its raw data is away: back to SMS's default gives the older version's readings
    ('Older rule', as its line says), and step 2 says to put the raw data back for SMS's
    default (Apply with SMS's values imports nothing again). Cleaned there; once the raw data is back, SMS's default is
    decoded again and becomes the import in use, so that cleaning is set aside (step 1 and the work message say so,
    the older readings go) and a new cleaning starts from step 1's readings."""
    K = _card_030(tmp_path, monkeypatch)
    at, t, wd = K["at"], K["t"], K["wd"]
    open(os.path.join(wd, "oced_work.json"), "w", encoding="utf-8").write(K["work_030"])
    os.replace(tmp_path / "cnh", tmp_path / "cnh_away")    # the raw data not at hand
    _reopen(at, wd)
    D = _D(at)
    assert D["import_default"]["older_decode"] and D["import_mode"] == "custom" and t in at.session_state["cleaned"]
    _back_to_default(at, confirm=True)
    D, DF = _D(at), _D(at)["import_default"]
    assert D["import_mode"] == "default" and D["shp"] == DF["shp"] and DF["older_decode"]
    assert t not in at.session_state["cleaned"] and os.path.exists(K["readings"])   # (the readings of that import)
    msg = " ".join(x.value for x in at.success)
    assert "back to the import of the older version's readings (Older rule), not SMS's default" in msg, msg
    assert "put its raw data back in the folder" in msg and str(tmp_path) not in msg, msg
    dec = [c for c in at.caption if c.value == ":orange[Decoded by an older OCED]"]
    assert dec and "put its raw data back" in dec[0].help and "today's rule" not in dec[0].help, dec
    _switch_off(at)
    assert any(c.value.startswith("Still the older version's readings") for c in at.caption)
    assert by_key(at.button, "fi_go_").disabled                   # Apply with SMS's values: nothing to import again
    C1 = _clean(at)
    assert int(C1["R"]["n_in"]) == int(D["n"])
    at.button(key="work_save").click().run()
    os.replace(tmp_path / "cnh_away", tmp_path / "cnh")    # back
    _reopen(at, wd)
    D, DF = _D(at), _D(at)["import_default"]
    assert not DF.get("older_decode") and D["import_mode"] == "default" and D["shp"] == DF["shp"]
    assert _badge_lines(at)[0].startswith("SMS default")
    assert t not in at.session_state["cleaned"] and not os.path.exists(C1["shp"])
    assert glob.glob(os.path.join(wd, "superseded", "**", os.path.basename(C1["shp"])), recursive=True)
    note = [c.value for c in at.caption if "Its raw data is back: SMS's default import was decoded again" in c.value]
    assert note and "the cleaning made on the older version's readings was set aside" in note[0], note
    assert "was set aside: clean it again in step 3" in at.session_state["work_msg"][1]
    assert not os.path.exists(K["readings"])                       # the older readings, named by nothing any more
    assert f"{int(DF['n']):,}" in _starts_from(at).value
    C2 = _clean(at)
    assert int(C2["R"]["n_in"]) == int(DF["n"]) and _first_metric(at, "Readings").value == f"{int(DF['n']):,}"
    assert "set aside" not in str((at.session_state["work_msg"] or ("", ""))[1])


def test_clean_all_brings_every_default_up_to_date_first(tmp_path, monkeypatch):
    """The 0.3.0 card work with two files on the older version's readings (mode default; the second a copy under
    another name, its own files), opened again once the raw data is back: only the file on screen is decoded again
    at once. 'Clean all' first brings the other file's SMS default up to date (decoded again from its raw data), so it
    is cleaned on step 1's readings, and picking it afterwards keeps that cleaning."""
    K = _card_030(tmp_path, monkeypatch)
    at, t, wd = K["at"], K["t"], K["wd"]
    p = os.path.join(wd, "oced_work.json")
    open(p, "w", encoding="utf-8").write(K["work_030"])
    os.replace(tmp_path / "cnh", tmp_path / "cnh_away")    # the raw data not at hand
    _reopen(at, wd)
    _back_to_default(at, confirm=True)                     # on the older version's readings
    assert _D(at)["import_mode"] == "default" and _D(at)["import_default"]["older_decode"]
    at.button(key="work_save").click().run()
    t2 = t + "_b"                                          # a second file: the same, under another name
    rec = json.load(open(p, encoding="utf-8"))
    txt = json.dumps(rec["datasets"][t])
    for s in ("_imported_default", "_decoded", "_decode_report", "_imported"):
        txt = txt.replace(f"{t}{s}", f"{t2}{s}")
    rec["datasets"][t2] = {**json.loads(txt), **({"tag": t2} if "tag" in rec["datasets"][t] else {})}
    for k in ("boundary", "grower"):
        if isinstance(rec.get(k), dict) and t in rec[k]:
            rec[k][t2] = rec[k][t]
    rec["active"] = t
    json.dump(rec, open(p, "w", encoding="utf-8"))
    for f in glob.glob(os.path.join(wd, "**", f"{t}_*"), recursive=True):
        rel = os.path.relpath(f, wd).split(os.sep)
        if os.path.isfile(f) and rel[0] not in ("clean", "superseded"):
            shutil.copy2(f, os.path.join(os.path.dirname(f), os.path.basename(f).replace(f"{t}_", f"{t2}_", 1)))
    os.replace(tmp_path / "cnh_away", tmp_path / "cnh")    # the raw data back
    _reopen(at, wd)
    assert at.session_state["active"] == t and sorted(at.session_state["datasets"]) == sorted([t, t2])
    assert not _D(at, t)["import_default"].get("older_decode")               # on screen: decoded again
    assert _D(at, t2)["import_default"].get("older_decode")                  # the other: not yet
    at.button(key="clean_all").click().run()
    assert not at.exception, at.exception
    D2 = _D(at, t2)
    assert not D2["import_default"].get("older_decode") and D2["shp"] == D2["import_default"]["shp"]
    C2 = at.session_state["cleaned"][t2]
    assert int(C2["R"]["n_in"]) == int(D2["n"]) == int(_D(at, t)["n"])
    _pick(at, t2)
    assert at.session_state["cleaned"].get(t2, {}).get("shp") == C2["shp"]
    assert not any("set aside" in c.value for c in at.caption), [c.value for c in at.caption if "set aside" in c.value]


# ------------------------------------------------------------------------------------------------ steps 1 and 2
def test_steps_1_and_2_when_nothing_is_left_and_values_typed_through_none(field, tmp_path, monkeypatch):
    """SMS's default leaves no reading: step 1 leads to step 2 (no 'Next: 3', the page stops after step 2) and step 2
    says to switch off its switch. The maps name their data (step 1's import, step 2's, the clean file). Values typed
    in step 2 stay through 'None' and back to 'As SMS' in the same file (still 'not applied')."""
    import numpy as np
    g = pyogrio.read_dataframe(field["shp"])
    for col in ("Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr"):
        g[col] = np.nan
    v = str(tmp_path / "none" / "Synthetic_no_yield.shp")
    os.makedirs(os.path.dirname(v))
    g.to_file(v, engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, v)
    nxt = [h.proto.body for h in at.get("html") if "oced-next" in h.proto.body]
    assert nxt and not any("#oced-step-3" in x for x in nxt) and any("#oced-step-2" in x for x in nxt), nxt
    assert any("switch this off to change the import" in c.value for c in at.caption)
    at = _app(tmp_path / "ws2", monkeypatch)
    _open(at, field["shp"])

    def heads():
        return [m.value.split("`Yld_Vol_Dr`")[1] for m in at.markdown if "`Yld_Vol_Dr`" in m.value]
    assert heads() == [" · SMS default (step 1)"], heads()
    _set_import(at, min=7.0, max=150.0, sd=2.0)
    by_key(at.button_group, "fi_how_").set_value("none").run()
    assert not at.exception, at.exception
    by_key(at.button_group, "fi_how_").set_value("sms").run()
    assert not at.exception, at.exception
    assert {n: by_key(at.number_input, f"fi_{n}_").value for n in ("min", "max", "sd")} == {
        "min": 7.0, "max": 150.0, "sd": 2.0}
    assert any("Not applied" in c.value and "Max. yield volume none → 150.00" in c.value for c in at.caption)
    by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert _D(at)["sms_import"]["resolved"]["start_delay_s"] == 2.0
    assert heads() == [" · SMS default (step 1)", " · your settings (step 2)"], heads()
    _clean(at)
    assert " · clean (step 3)" in heads(), heads()


def test_none_on_an_export_whose_import_failed_keeps_its_cleaning(field, tmp_path, monkeypatch):
    """An export whose SMS import failed is used as the file gives it; 'None' applied then uses the same file: its
    cleaning stays, and step 2 shows 'None' as applied (no 'not applied' line, Apply off, 'As it is')."""
    real = si.apply

    def boom(*a, **k):
        raise OSError("synthetic write failure")
    monkeypatch.setattr(si, "apply", boom)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    monkeypatch.setattr(si, "apply", real)
    at.run()
    t = at.session_state["active"]
    C0 = _clean(at)
    _apply_import(at, how="none")
    assert t in at.session_state["cleaned"] and at.session_state["cleaned"][t]["shp"] == C0["shp"]
    assert not any("set aside" in s.value for s in at.success)
    assert not any("Not applied" in c.value for c in at.caption) and by_key(at.button, "fi_go_").disabled
    b = _badge_lines(at)
    assert b[0].startswith("Import failed") and any(x.startswith("As it is") for x in b[1:]), b
    assert _D(at)["import_mode"] == "as_is" and "As it is" in _starts_from(at).value


def test_the_report_names_the_import_of_a_cleaning():
    """The report's import line names the user's settings, an older rule's import kept as saved and an older
    version's decode."""
    from engine.report import clean_report as CR
    base = {"settings": "min. yield volume 5.000 bu/ac", "n_all": 10, "n_in": 9}
    assert CR._import_text({**base, "mode": "custom"}).startswith("Your settings (step 2): min. yield volume")
    txt = CR._import_text({**base, "mode": "older", "older": ["Min. yield volume 5.000 → 0.000"]})
    assert txt.startswith("An older OCED rule, kept as saved (Min. yield volume 5.000 → 0.000): min. yield"), txt
    txt = CR._import_text({**base, "mode": "older", "older": ["its raw data is not at hand"],
                           "older_decode": "product barley"})
    assert txt.startswith("Decoded by an older OCED with product barley, kept (its raw data is not at hand): min."), txt
    # its yields are those of that decode (the product's weight and moisture), not 'product unknown; -'
    txt = CR._import_text({**base, "settings": "product unknown; weight to volume - lb/bu; dry moisture - %; expand "
                           "dry moisture off; yield volume 5.000-300.00 bu/ac", "mode": "older",
                           "older": ["its raw data is not at hand"], "older_decode": "product barley",
                           "older_decode_values": "48.00 lb/bu, 14.50 %"})
    assert ("kept (its raw data is not at hand): the yields as that decode gives them (48.00 lb/bu, 14.50 %); expand "
            "dry moisture off; yield volume 5.000-300.00 bu/ac") in txt and "product unknown" not in txt, txt
    # ... nor, where the values came from, 'weight to volume none, dry moisture none' of an import that converts nothing
    R = si.resolve(si.settings({}), None, None, "cnh_cn1")
    imp = {**base, "settings": si.describe(R), "sources_text": si.describe_sources(R), "mode": "older",
           "older": ["its raw data is not at hand"], "older_decode": "product barley",
           "older_decode_values": "48.00 lb/bu, 14.50 %"}
    txt = CR._import_text(imp)
    assert "the yields as that decode gives them (48.00 lb/bu, 14.50 %)" in txt, txt
    assert "; values from: min. yield volume 5.000 bu/ac" in txt and "none" not in txt.split("values from:")[1], txt
    # an import that converted those readings' yields with its own product: its product, weight and moisture
    Rw = si.resolve(si.settings({}), "wheat", None, "cnh_cn1")
    txt = CR._import_text({**base, "settings": si.describe(Rw), "sources_text": si.describe_sources(Rw),
                           "mode": "older", "older": ["its raw data is not at hand"], "older_decode": "product barley",
                           "older_decode_converted": True})
    assert txt.startswith("Decoded by an older OCED with product barley, kept (its raw data is not at hand): the yields "
                          "converted with product wheat; weight to volume 60.00 lb/bu; dry moisture 13.50 %"), txt
    assert "values from: SMS product Wheat - Spring: weight to volume 60.00 lb/bu" in txt, txt
    assert CR._import_text(base).startswith("min. yield volume")


def _s2_help(at):
    hs = [str(c.help) for c in at.caption if c.help and "S2 narrows the readings" in str(c.help)]
    assert len(hs) == 1, hs
    return hs[0]


def test_the_s2_help_names_the_order_of_the_readings_of_a_timed_point_file(tmp_path, monkeypatch):
    """0.3.2 (M10): step 3's S2 line says, behind its "?", the order S2 took: a point file with a time per reading in
    time order; the rest of the help stays."""
    from engine.clean import sms3sigma as sms
    from tests.synthetic_strips import make_strips
    F = make_strips(str(tmp_path / "f"), "Strip A", "Strip B", times=("2026-09-14 10:00:00", "2026-09-14 09:00:00"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, F["shp"])
    sw = _clean(at)["R"]["sms3sigma"]["swath"]
    assert sw["order_basis"] == sms.ORDER_TIME, sw
    h = _s2_help(at)
    assert ("Order of the readings: " + sw["order"] + ".") in h and h.count("Order of the readings") == 1, h
    assert h.startswith("S2 narrows the readings") and "(mass kept). Order of" in h, h


def test_the_s2_help_names_the_file_order_of_an_untimed_point_file(tmp_path, monkeypatch):
    """0.3.2 (M10, M12): a point file without a time per reading: the help says the file's own row order, and why in
    the user's words (no setting name)."""
    from engine.clean import sms3sigma as sms
    from tests.synthetic_strips import make_strips
    F = make_strips(str(tmp_path / "f"), "Strip U", "Strip D 9/14/2026")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, F["shp"])
    sw = _clean(at)["R"]["sms3sigma"]["swath"]
    assert sw["order_basis"] == sms.ORDER_FILE, sw
    h = _s2_help(at)
    assert h.count("Order of the readings: the file's own row order") == 1, h
    assert "swath_order" not in h and "cols[" not in " ".join(str(w.value) for w in at.warning), h


def test_long_values_wrap_instead_of_being_cut(field, tmp_path, monkeypatch):
    """0.3.2 (M13): at a 1440-px window nothing is cut: a card's value (a date range) wraps inside its card, the map's
    statistics name each statistic in full beside its value, and the steps table gives its numbers before the long
    criterion, which wraps in its own width (no side scroll)."""
    import re
    css = open(os.path.join(ROOT, "app", "brand.py"), encoding="utf-8").read()
    assert re.search(r'st-key-strip_"\] \[data-testid="stMetricValue"\] p,[^}]*white-space: normal; overflow: visible;'
                     r'\s*text-overflow: clip', css), "a card's value is not wrapped"
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _clean(at)
    steps = next(d for d in at.dataframe if "filter" in d.value.columns)
    assert list(steps.value.columns) == ["filter", "name", "on", "removed", "remaining", "criterion"]
    assert steps.proto.row_height > 64                    # taller than 4rem: the criterion wraps
    stats = next(d for d in at.dataframe if "statistic" in d.value.columns)
    cfg = json.loads(stats.proto.columns)
    assert cfg["statistic"]["width"] + cfg["value"]["width"] <= 310


def test_step_2_boxes_follow_the_attribute_of_its_map(field, tmp_path, monkeypatch):
    """0.3.6: with own import settings, step 2's boxes follow the attribute chosen on step 2's map (moisture: its mean
    and area-weighted average in %, no total) and come back to the yield and the total; step 1's boxes stay on yield."""
    import numpy as np
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _apply_import(at, max=150.0)
    D = _D(at)
    k2 = next(k for k in at.session_state.filtered_state if str(k).startswith("attr_imp_"))
    at.session_state[k2] = "Moisture__"
    at.run()
    assert not at.exception, at.exception
    df = pyogrio.read_dataframe(D["shp"], read_geometry=False)
    v = df["Moisture__"].astype(float).to_numpy()
    a = (df["Distance_f"].astype(float) * df["Swth_Wdth_"].astype(float)).to_numpy() / 43560.0
    ok = np.isfinite(v) & np.isfinite(a) & (a > 0)
    mm, ma = float(np.nanmean(v)), float((v[ok] * a[ok]).sum() / a[ok].sum())
    assert [m.value for m in at.metric if m.label == "Mean moisture"] == [f"{mm:,.2f} %"]
    assert [m.value for m in at.metric if m.label == "Average moisture, area-weighted"] == [f"{ma:,.2f} %"]
    assert [m.label for m in at.metric].count("Total dry bu") == 1              # step 1's only
    assert [m.label for m in at.metric].count("Mean dry yield") == 1
    at.session_state[k2] = "Yld_Vol_Dr"
    at.run()
    assert not at.exception, at.exception
    assert [m.label for m in at.metric].count("Total dry bu") == 2
    assert not [m for m in at.metric if m.label == "Mean moisture"]
