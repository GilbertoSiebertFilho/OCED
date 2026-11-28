# -*- coding: utf-8 -*-
"""0.4.0: the grower's weight with its decimals and weighed dry unless told otherwise, on synthetic data only
(tests/synthetic.py). The weight's texts (engine/clean/yield_clean.py ticket_value_text and the ticket's caption,
engine/run.py ticket_conversion / level_caption) write it with two decimals, never rounded to a whole number; a
weight given to the engine or the command line without its basis is taken at the standard moisture (dry), as
delivered (wet) when its grain moisture comes with it, and settings without a weight keep the default ticket as it
was; in the app the weight field shows two decimals (four in t) with a step that takes them, the 'Weighed' choice of
a fresh work is 'At the standard moisture' (dry), and a saved work keeps the basis it was saved with.

    python -m pytest -q tests/test_grower_weight_decimals.py
"""
from __future__ import annotations

import glob
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("gw_field")))


# ------------------------------------------------------------------------------------------------ the texts
@pytest.mark.parametrize("value, unit, text", [
    (4451.5, "lb", "4,451.50 lb"), (1_500_000, "lb", "1,500,000.00 lb"), (9000, "bu", "9,000.00 bu"),
    (7500.5, "bu", "7,500.50 bu"), (50, "bu/ac", "50.00 bu/ac"), (50.25, "bu/ac", "50.25 bu/ac"),
    (2019.25, "kg", "2,019.25 kg"), (200, "t", "200.00 t"), (0.5, "t", "0.50 t"), (200.1234, "t", "200.1234 t")])
def test_the_weight_is_written_with_two_decimals(value, unit, text):
    assert yc.ticket_value_text(value, unit) == text
    assert er.ticket_label({"value": value, "unit": unit}) == text


def test_the_tickets_caption_keeps_the_decimals():
    """4,451.5 lb: the caption, the conversion text and the level line say 4,451.50 lb, not 4,452."""
    T = {"value": 4451.5, "unit": "lb", "basis": "dry", "moisture_pct": None, "note": None}
    s = yc.ticket_summary({"scale_ticket": T}, 60.0, "the file")
    assert s["caption"].startswith("4,451.50 lb = 74.19 bu at 60.00 lb/bu"), s["caption"]
    c = er.ticket_conversion(dict(T, unit="kg"), file_tw=60.0)
    assert c["text"] == f"= {4451.5 * er.LB_PER_KG:,.2f} lb = {4451.5 * er.LB_PER_KG / 60:,.2f} bu at 60.00 lb/bu " \
                        "(test weight from the file)"
    c = er.ticket_conversion({"value": 74.25, "unit": "bu", "basis": "dry"}, file_tw=60.0)
    assert c["text"] == "= 4,455.00 lb at 60.00 lb/bu (test weight from the file)"
    L = {"export_total_bu": 80.125, "ticket_bu": 74.19, "factor": 0.926, "ticket_unit": "lb", "ticket_value": 4451.5}
    assert er.level_caption({"level": L}) == ("monitor 80.12 bu vs scale 74.19 bu (-7.41 %); the grower said "
                                              "4,451.50 lb")


# ------------------------------------------------------------------------------------------------ the basis
def test_a_weight_without_its_basis_is_dry_in_the_engine():
    no = yc.merge_settings({})
    assert no["scale_ticket"]["value"] is None and no["scale_ticket"]["basis"] == "wet"        # as it was
    assert yc.merge_settings({"scale_ticket": {"value": None}})["scale_ticket"]["basis"] == "wet"
    assert yc.ticket_spec(no) is None
    S = yc.merge_settings({"scale_ticket": {"value": 4451.5, "unit": "lb"}})
    assert S["scale_ticket"]["basis"] == "dry" and yc.ticket_spec(S)["basis"] == "dry"
    S = yc.merge_settings({"scale_ticket": {"value": 4451.5, "unit": "lb", "basis": None}})
    assert S["scale_ticket"]["basis"] == "dry"
    S = yc.merge_settings({"scale_ticket": {"value": 4451.5, "unit": "lb", "moisture_pct": 15.0}})
    assert S["scale_ticket"]["basis"] == "wet"                                 # a moisture comes with a wet weight
    for b in ("wet", "dry"):
        assert yc.merge_settings({"scale_ticket": {"value": 1.0, "basis": b}})["scale_ticket"]["basis"] == b
    # the legacy alias in bushels keeps its v1 default
    S = yc.merge_settings({"scale_ticket_bu": 100.0})
    assert S["scale_ticket_basis"] == "wet" and yc.ticket_spec(S)["basis"] == "wet"
    # engine/run.py's own reading of a ticket (the app's caption, the compat path)
    assert er.ticket_settings({"scale_ticket": {"value": 10.0}})["basis"] == "dry"
    assert er.ticket_settings({"scale_ticket": {"value": 10.0, "moisture_pct": 14.0}})["basis"] == "wet"
    assert er.ticket_settings({"scale_ticket": {"value": 10.0, "basis": "wet"}})["basis"] == "wet"
    assert er.ticket_settings({"scale_ticket_bu": 10.0})["basis"] == "wet"
    assert er.ticket_settings({}) is None


def test_the_command_line_takes_a_weight_without_basis_dry(field, tmp_path):
    w = str(tmp_path / "cli")
    assert er.main([field["shp"], "--out", w, "--tag", "gw", "--scale-ticket", "100000.5", "--ticket-unit", "lb"]) == 0
    [p] = glob.glob(os.path.join(w, "output*", "gw*_cleaning.json"))
    R = json.load(open(p, encoding="utf-8"))
    T = R["settings"]["scale_ticket"]
    assert T["value"] == 100000.5 and T["basis"] == "dry" and R["level"]["ticket_basis"] == "dry"
    w2 = str(tmp_path / "cli2")
    assert er.main([field["shp"], "--out", w2, "--tag", "gw", "--scale-ticket", "100000.5", "--ticket-unit", "lb",
                    "--ticket-moisture", "15"]) == 0
    [p] = glob.glob(os.path.join(w2, "output*", "gw*_cleaning.json"))
    assert json.load(open(p, encoding="utf-8"))["settings"]["scale_ticket"]["basis"] == "wet"


# ------------------------------------------------------------------------------------------------ the app
def _by_key(items, prefix):
    return next(x for x in items if str(x.key or "").startswith(prefix))


def _app(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception


def test_app_weight_field_takes_decimals_and_weighed_defaults_to_dry(field, tmp_path, monkeypatch):
    """The weight field: two decimals for lb, kg, bu and bu/ac, four for t (as the engine writes a tonne weight), a
    step of its last decimal; 4,451.5 lb is kept as typed. A fresh work's 'Weighed' is dry; a work saved with wet opens with wet."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    w = _by_key(at.number_input, "gw_w_")
    assert (w.proto.format, w.proto.step) == ("%.2f", 0.01)
    assert _by_key(at.button_group, "gw_b_").value == "dry"
    for unit, fmt, step in (("kg", "%.2f", 0.01), ("bu", "%.2f", 0.01), ("bu/ac", "%.2f", 0.01),
                            ("t", "%.4f", 0.0001), ("lb", "%.2f", 0.01)):
        _by_key(at.button_group, "gw_u_").set_value(unit).run()
        w = _by_key(at.number_input, "gw_w_")
        assert (w.proto.format, w.proto.step) == (fmt, pytest.approx(step)), unit
    _by_key(at.number_input, "gw_w_").set_value(4451.5).run()
    assert not at.exception, at.exception
    t = at.session_state["active"]
    G = at.session_state["grower"][t]
    assert G["weight"] == 4451.5 and G["unit"] == "lb" and G["basis"] == "dry"
    assert _by_key(at.number_input, "gw_w_").value == 4451.5
    assert any(str(c.value).startswith("= 4,451.50 lb") for c in at.caption), [c.value for c in at.caption]
    # wet chosen and saved: the work opens with wet (its own basis), and the moisture box is open for it
    _by_key(at.button_group, "gw_b_").set_value("wet").run()
    assert at.session_state["grower"][t]["basis"] == "wet"
    at.button(key="work_save").click().run()
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    t = at.session_state["active"]
    assert at.session_state["grower"][t]["basis"] == "wet" and at.session_state["grower"][t]["weight"] == 4451.5
    assert _by_key(at.button_group, "gw_b_").value == "wet"
    assert not _by_key(at.number_input, "gw_m_").proto.disabled


def test_the_weight_box_has_its_own_row_and_no_stepper():
    """0.4.0: the weight box is not in a row with the Unit control (beside it, about 300 px, the box showed a few
    digits in a two-column layout): the Unit is drawn under it, and the box's +/- buttons are hidden (brand CSS)."""
    src = open(APP, encoding="utf-8").read()
    panel = src.split('key=f"gw_box_{TK}"', 1)[1].split('key=f"gw_u_{TK}"', 1)[0]
    assert 'key=f"gw_w_{TK}"' in panel and "horizontal=True" not in panel and "in the unit below" in panel
    sys.path.insert(0, os.path.join(ROOT, "app"))
    import brand
    css = brand._css()
    for t in ("stNumberInputStepDown", "stNumberInputStepUp"):
        assert f'[class*="st-key-gw_w_"] [data-testid="{t}"]' in css
