# -*- coding: utf-8 -*-
"""The passes of Optimize Swath Widths (the engine setting swath_passes: 1, the method; 2 or 3 repeat an SMS chain
where Clip + Optimize Swath Widths was added that many times) on the screen: a control in step 3 beside the other
SMS 3-sigma settings (default 1) that reaches the cleaning and its record, counts for 'settings changed: clean
again', is kept with the work, and is read back from a work rebuilt from its cleaning records; a work saved before
the control existed is not told to clean again; the report's Optimize Swath Widths line says the passes when there is
more than one. Synthetic data only.

    python -m pytest -q tests/test_app_swath_passes.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import works as ew  # noqa: E402
from engine.clean import sms3sigma as sms  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.test_app_fixes import STALE, _app, _app_function, _by_key, _clean, _open  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


def _s2(R) -> dict:
    return next(r for r in R["cascade"] if r["filter"] == "S2")


def _stale(at) -> bool:
    return any(STALE in w.value for w in at.warning)


def test_the_passes_have_a_control_that_reaches_the_cleaning_and_stays_with_the_work(field, tmp_path, monkeypatch):
    """Step 3 shows 'Optimize Swath Widths passes' (1 to 3, default 1). A cleaning runs with the value on the screen:
    its settings, its record (the engine's own count of the passes it ran) and the S2 line of its cascade say so. A
    change after the cleaning says 'clean again'. Saved and opened again the control shows the saved value, and a
    work rebuilt from its cleaning records (no saved work file) gets the passes of the record."""
    assert sms.DEFAULTS["swath_passes"] == 1 and sms.SWATH_PASSES_MAX == 3
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    box = at.number_input(key="swath_passes")
    assert (box.value, box.min, box.max, box.label) == (1, 1, 3, "Optimize Swath Widths passes")
    assert at.session_state["smsset"]["swath_passes"] == 1
    C1 = _clean(at)
    R1 = C1["R"]
    assert C1["settings"]["swath_passes"] == 1 and C1["config"]["sms3sigma"]["swath_passes"] == 1
    assert R1["settings"]["sms3sigma"]["swath_passes"] == 1 and R1["sms3sigma"]["swath"]["swath_passes"] == 1
    assert "passes)" not in _s2(R1)["criterion"] and not _stale(at)
    # two passes: the cleaning on the screen no longer has the settings on the screen
    at.number_input(key="swath_passes").set_value(2).run()
    assert not at.exception, at.exception
    assert at.session_state["smsset"]["swath_passes"] == 2 and _stale(at)
    C2 = _clean(at)
    R2 = C2["R"]
    assert C2["settings"]["swath_passes"] == 2 and C2["config"]["sms3sigma"]["swath_passes"] == 2
    assert R2["settings"]["sms3sigma"]["swath_passes"] == 2 and R2["sms3sigma"]["swath"]["swath_passes"] == 2
    assert "(2 passes)" in _s2(R2)["criterion"] and not _stale(at)
    assert json.load(open(C2["json"], encoding="utf-8"))["settings"]["sms3sigma"]["swath_passes"] == 2
    # saved and opened again: the control and the settings of the work hold 2, nothing to clean again
    t, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click().run()
    assert json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))["smsset"]["swath_passes"] == 2
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert at.number_input(key="swath_passes").value == 2 and at.session_state["smsset"]["swath_passes"] == 2
    assert at.session_state["cleaned"][t]["config"]["sms3sigma"]["swath_passes"] == 2 and not _stale(at)
    at.number_input(key="swath_passes").set_value(1).run()
    assert _stale(at)
    at.number_input(key="swath_passes").set_value(2).run()
    assert not _stale(at)
    # a work rebuilt from its cleaning records: the passes of the record
    at.button(key="start_over").click().run()
    os.remove(os.path.join(wd, "oced_work.json"))
    rec = ew.load_work(wd)
    assert rec["legacy"] and rec["smsset"]["swath_passes"] == 2


def test_a_work_saved_before_the_control_is_not_told_to_clean_again(field, tmp_path, monkeypatch):
    """A work saved by a version without the control holds no swath_passes in its settings or in the config of its
    cleaning (which ran one pass): opened, it shows 1 and says nothing of cleaning again, with the saved config and
    for a work saved before the config was kept; a real change still says so."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _clean(at)
    t, wd = at.session_state["active"], at.session_state["workdir"]
    at.button(key="work_save").click().run()
    p = os.path.join(wd, "oced_work.json")
    rec = json.load(open(p, encoding="utf-8"))
    assert rec["smsset"].pop("swath_passes") == 1
    assert rec["cleaned"][t]["config"]["sms3sigma"].pop("swath_passes") == 1
    assert rec["cleaned"][t]["settings"].pop("swath_passes") == 1
    for keep_config in (True, False):
        if not keep_config:
            rec["cleaned"][t]["config"] = None
        json.dump(rec, open(p, "w", encoding="utf-8"))
        at.button(key="start_over").click().run()
        at.button(key="work_open").click().run()
        assert not at.exception, at.exception
        assert at.session_state["workdir"] == wd and t in at.session_state["cleaned"]
        assert at.number_input(key="swath_passes").value == 1 and not _stale(at), keep_config
        assert at.session_state["cleaned"][t]["config"]["sms3sigma"]["swath_passes"] == 1
        assert not any("settings changed: clean again" in m.value for m in at.sidebar.markdown)
    at.number_input(key="swath_passes").set_value(3).run()
    assert _stale(at)


def test_the_passes_a_dict_of_settings_holds():
    """swath_passes_of: the value when it is one of 1 to 3, else the default (settings kept before the control)."""
    swath_passes_of, = _app_function("swath_passes_of", sms=sms)
    held = ({"swath_passes": 2}, {"swath_passes": 3.0}, {"swath_passes": "2"})
    assert [swath_passes_of(s) for s in held] == [2, 3, 2]
    assert [swath_passes_of(s) for s in ({}, None, {"swath_passes": None}, {"swath_passes": 0}, {"swath_passes": 9},
                                         {"swath_passes": "two"}, "no settings")] == [1] * 7


def test_the_report_line_says_the_passes_when_there_is_more_than_one():
    from engine.report import clean_report as cr
    sw = {"n_removed": 12, "n_narrowed": 340, "min_width_ft": 7.5, "max_scale": 4.0}
    one = cr._sms_swath_text({"sms3sigma": {"swath": {**sw, "swath_passes": 1}}})
    two = cr._sms_swath_text({"sms3sigma": {"swath": {**sw, "swath_passes": 2}}})
    assert "passes of Clip" not in one and "passes of Clip" not in cr._sms_swath_text({"sms3sigma": {"swath": sw}})
    assert "; 2 passes of Clip + Optimize Swath Widths (an SMS chain where the two were added that many times)" in two
    assert two.replace("; 2 passes of Clip + Optimize Swath Widths (an SMS chain where the two were added that many "
                       "times)", "") == one
