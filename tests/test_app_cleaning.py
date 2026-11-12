# -*- coding: utf-8 -*-
"""Step 3 of the app (app/oced.py) through Streamlit's AppTest, on synthetic data only: the SMS 3-sigma panel
follows the method (the order of the filters, the mean and SD groups, the scope of Optimize Swath Widths, the
lateral offset check) and names every step by what it filtered; the grower's weight is compared as a mass in the
file's bushels, validates without changing the clean file (not even a combine factor) or adjusts it, and every L on
the page is the one in the file (after the combine factor); a cleaning of an older method asks to be made again.

    python -m pytest -q tests/test_app_cleaning.py
"""
from __future__ import annotations

import glob
import html
import json
import os
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_field, make_two_combines  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


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


def _html(at, cls):
    return [h.proto.body for h in at.get("html") if cls in h.proto.body]


def _metric(at, label):
    return next(m for m in at.metric if m.label == label)


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """Two combines, COMBINE-B reading 15 % high: a factor above the 10 % max that the true weight confirms."""
    return make_two_combines(str(tmp_path_factory.mktemp("two")), bias_b=1.15)


# ------------------------------------------------------------------------------------------------ the SMS panel
def test_app_filter_order_names_and_panel_settings(field, tmp_path, monkeypatch):
    """Moisture then speed by default (S3 moisture, S4 speed); speed then moisture on request, and the toggles, the
    step table and the map of the removed points take the names of the run's own order; the scope of Optimize
    Swath Widths and the lateral offset check reach the engine; the limits table counts the readings without a
    value."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    labels = [t.label for t in at.toggle if t.key in ("t_moist", "t_speed")]
    assert labels == ["S3 moisture", "S4 speed"]
    assert at.selectbox(key="filter_order").value == "moisture_speed"
    gb = at.selectbox(key="group_by")
    assert gb.format_func("auto").startswith("auto: one mean and SD per combine")
    assert gb.format_func("task").startswith("task: each dataset")
    at.selectbox(key="filter_order").set_value("speed_moisture").run()
    assert [t.label for t in at.toggle if t.key in ("t_moist", "t_speed")] == ["S3 speed", "S4 moisture"]
    at.selectbox(key="swath_scope").set_value("machine").run()
    at.selectbox(key="swath_bias").set_value("off").run()
    C = _clean(at)
    M = C["R"]["sms3sigma"]
    assert M["filter_order"] == "speed_moisture" and M["settings"]["swath_scope"] == "machine"
    assert M["settings"]["swath_bias"] == "off" and M["method_revision"] >= 2
    rows = {r["filter"]: r for r in C["R"]["cascade"]}
    assert rows["S3"]["attribute"] == "speed" and rows["S4"]["attribute"] == "moisture"
    steps = next(d.value for d in at.dataframe if "readings removed" in d.value.columns)
    assert not any(s.startswith("S3 moisture") or s.startswith("S4 speed") for s in steps["step"])
    assert any("without a value (kept by this step)" in str(c) or c == "no_value" for d in at.dataframe
               for c in d.value.columns)
    legend = " ".join(h for h in _html(at, "points</span>"))
    if (rows["S3"]["removed"] or 0) > 0:
        assert "S3 Speed mean" in legend
    # the default order again: the cleaning on screen no longer matches the settings
    at.selectbox(key="filter_order").set_value("moisture_speed").run()
    assert any("changed since this file was cleaned" in w.value for w in at.warning)


def test_app_old_method_cleaning_asks_to_clean_again(field, tmp_path, monkeypatch):
    """A saved work whose cleaning record has no method revision (the method before the filter order became a
    setting) and whose settings have no filter order opens with 'clean it again'."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    C = _clean(at)
    at.button(key="work_save").click().run()
    assert not at.exception, at.exception
    with open(C["json"], encoding="utf-8") as fh:
        R = json.load(fh)
    R["sms3sigma"].pop("method_revision", None)
    R["sms3sigma"].pop("filter_order", None)
    with open(C["json"], "w", encoding="utf-8") as fh:
        json.dump(R, fh)
    wp = os.path.join(at.session_state["workdir"], "oced_work.json")
    W = json.load(open(wp, encoding="utf-8"))
    for k in ("filter_order", "swath_scope", "swath_bias"):
        W["smsset"].pop(k, None)
    json.dump(W, open(wp, "w", encoding="utf-8"))
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    assert any("older version of the SMS 3-sigma method" in w.value for w in at2.warning)


# ------------------------------------------------------------------------------------------------ the grower's data
def test_app_weight_in_lb_is_a_mass_comparison(field, tmp_path, monkeypatch):
    """A weight in lb equal to the monitor's wet mass, with a grower's bushel weight other than the file's: L = 1,
    and the bushel and the pound rows give the same gap (the bushel weight is reported, never used for a mass)."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.number_input, "gw_w_").set_value(100_000.0).run()
    lb = float(_clean(at)["R"]["level"]["export_total_lb"])
    shp = at.session_state["datasets"][at.session_state["active"]]["shp"]
    d = pyogrio.read_dataframe(shp, read_geometry=False)
    tw_file = float(np.median(d["Yld_Mass_W"] / d["Yld_Vol_We"]))
    _by_key(at.number_input, "gw_w_").set_value(round(lb, 3)).run()
    _by_key(at.number_input, "gw_tw_").set_value(round(tw_file + 4.0, 1)).run()
    assert any("is reported, not used" in c.value for c in at.caption)
    C = _clean(at)
    L = C["R"]["level"]
    assert L["factor"] == pytest.approx(1.0, abs=1e-5) and L["test_weight_grower"] == pytest.approx(tw_file + 4.0, abs=0.06)
    S = C["R"]["settings"]
    assert S["scale_ticket"]["use"] == "validate" and S["scale_ticket"]["test_weight_lb_bu"] == pytest.approx(
        round(tw_file + 4.0, 1))
    assert abs(float(S.get("test_weight_lb_bu") or tw_file) - tw_file) < 0.06       # the import's, not the grower's
    tbl = next(dd.value for dd in at.dataframe if "monitor vs grower" in dd.value.columns)
    assert {str(x).replace("-", "+") for x in tbl["monitor vs grower"]} == {"+0.00 %"}
    assert "L = 1.0000" in " ".join(_html(at, "oced-verdict"))


def test_app_grower_bushels_as_given_or_of_the_bushel_weight(field, tmp_path, monkeypatch):
    """A weight in bushels with a bushel weight: compared as given (trade bushels) unless the user says they are
    bushels of that weight, then converted through the mass."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.button_group, "gw_u_").set_value("bu").run()
    _by_key(at.number_input, "gw_w_").set_value(1500.0).run()
    _by_key(at.number_input, "gw_tw_").set_value(66.0).run()
    bu = _by_key(at.button_group, "gw_bu_")
    assert bu.value == "given"
    C1 = _clean(at)
    assert C1["R"]["settings"]["scale_ticket"]["test_weight_lb_bu"] is None
    L1 = C1["R"]["level"]["factor"]
    _by_key(at.button_group, "gw_bu_").set_value("grower").run()
    C2 = _clean(at)
    assert C2["R"]["settings"]["scale_ticket"]["test_weight_lb_bu"] == 66.0
    tw = float(C2["R"]["level"]["test_weight_used"])
    assert C2["R"]["level"]["factor"] == pytest.approx(L1 * 66.0 / tw, rel=1e-6)


def test_app_grower_acres_follow_the_clip(field, tmp_path, monkeypatch):
    """A yield per acre with a boundary: the boundary's acres while S1 clips to it; with the clip off the area
    harvested (the engine's rule then), and the page says so."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    _by_key(at.button_group, "gw_u_").set_value("bu/ac").run()
    assert _by_key(at.number_input, "gw_a_").placeholder.startswith("empty = the boundary")
    at.toggle(key="t_clip").set_value(False).run()
    ph = _by_key(at.number_input, "gw_a_").placeholder
    assert ph.startswith("empty = the area harvested") and "S1 is off" in ph


# ------------------------------------------------------------------------------------------------ combine factor
def test_app_validate_only_confirms_no_factor_and_adjust_does(two, tmp_path, monkeypatch):
    """Two combines, B 15 % high (above the 10 % max), the true weight: 'Validate only' applies no factor and says
    which one the weight would confirm; 'adjust' applies it, and the L in the verdict box, the metric and the action
    tree is the L in the file (after the combine factor), beside its band."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, two["shp"])
    _by_key(at.toggle, "cf_on_").set_value(True).run()
    _by_key(at.number_input, "gw_w_").set_value(float(two["truth"]["wet_lb"])).run()
    assert any("Validate only: the grower's weight confirms no factor" in c.value for c in at.caption)
    C = _clean(at)
    M = C["R"]["machines"]
    assert all(abs(float(v) - 1) < 1e-12 for v in M["factor_applied"].values())
    assert M["ticket_test"]["validate_only"] and M["ticket_test"]["would_apply"] == ["COMBINE-B"]
    fin = _metric(at, "Final yield (clean file)")
    assert "it would confirm the combine factor of COMBINE-B" in str(fin.proto.delta)
    shp = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    assert "Yld_Level" not in shp.columns
    _by_key(at.button_group, "gw_use_").set_value("adjust").run()
    C = _clean(at)
    R = C["R"]
    L, CL = R["level"], R["level"]["closure"]
    assert abs(float(R["machines"]["factor_applied"]["COMBINE-B"]) - 1) > 0.05
    assert L["combine_factor_changed_total"] and abs(L["factor_final"] - L["factor"]) > 0.01
    box = " ".join(_html(at, "oced-verdict"))
    assert f"L = {L['factor_final']:.4f} (before the combine harmonisation {L['factor']:.4f}) · band {html.escape(CL['band'])}" in box
    assert _metric(at, "Monitor vs grower").value == f"{CL['diff_final_pct']:+.2f} %"
    assert any(f"L = {L['factor_final']:.4f}" in c.value and "adjusted" in c.value for c in at.caption)
    tbl = next(dd.value for dd in at.dataframe if "monitor vs grower" in dd.value.columns)
    assert any("before the combine factor" in str(x) for x in tbl[""])
    # the map after the correction factors: a yield in bu/ac with its SMS average
    at2 = _app(tmp_path / "ws2", monkeypatch)
    _open(at2, two["shp"])
    _by_key(at2.toggle, "cf_on_").set_value(True).run()
    _by_key(at2.number_input, "cf_max_").set_value(20.0).run()
    C2 = _clean(at2)
    assert abs(float(C2["R"]["machines"]["factor_applied"]["COMBINE-B"]) - 1) > 0.05
    stats = [d.value for d in at2.dataframe if "change vs the clean map" in d.value.columns]
    assert stats and "average (SMS, area-weighted)" in list(stats[0]["statistic"])
    assert any(m.value.startswith("**Dry yield x the combine factor** · bu/ac") for m in at2.markdown)
    # step 4: the combine factor applied in step 3 goes into the written grain by default
    apply = _by_key(at2.checkbox, "nw_f_")
    assert apply.value is True and not apply.disabled
    _by_key(at2.button, "nw_go_isoxml_").click().run()
    assert not at2.exception, at2.exception
    rec = json.load(open(glob.glob(os.path.join(at2.session_state["workdir"], "native", "*", "isoxml.json"))[0],
                         encoding="utf-8"))
    fB = float(C2["R"]["machines"]["factor_applied"]["COMBINE-B"])
    assert rec["options"]["factors"] == pytest.approx({"COMBINE-A": 1.0, "COMBINE-B": fB})
    c = pyogrio.read_dataframe(C2["shp"], read_geometry=False)
    want = float((c.Yld_Mass_W * c.Distance_f * c.Swth_Wdth_ / 43560.0
                  * np.where(c.Machine == "COMBINE-B", fB, 1.0)).sum())
    written = next(r for r in rec["totals"] if r[""] == "written")
    assert written["wet (lb)"] == pytest.approx(want, rel=1e-6)


def test_app_combine_factor_off_reaches_the_engine_as_off(two, tmp_path, monkeypatch):
    """The combine factor switched off: only {'harmonise': False} reaches the engine, so a max factor of 1 % left in
    its panel stops nothing; switched on at 1 % it cleans too."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, two["shp"])
    _by_key(at.toggle, "cf_on_").set_value(True).run()
    _by_key(at.number_input, "cf_max_").set_value(1.0).run()
    C = _clean(at)
    assert C["R"]["settings"]["machines"]["max_factor"] == pytest.approx(0.01)
    _by_key(at.toggle, "cf_on_").set_value(False).run()
    C = _clean(at)
    assert C["R"]["settings"]["machines"]["harmonise"] is False
    sent = json.load(open(glob.glob(os.path.join(at.session_state["workdir"], "clean", "*", "*_cleaning.json"))[0],
                          encoding="utf-8"))
    assert sent["settings"]["machines"]["harmonise"] is False


def test_grower_ticket_carries_use_and_bushels():
    """grower_ticket: 'use' and the grower's bushel weight go in the ticket (never the settings' test weight);
    bushels are converted only when they are the grower's bushels."""
    import ast
    tree = ast.parse(open(APP, encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "grower_ticket")
    ns = {}
    exec(compile(ast.Module([fn], []), APP, "exec"), ns)
    gt = ns["grower_ticket"]
    assert gt({}) is None
    T = gt({"weight": 1000.0, "unit": "lb", "test_weight": 63.0})
    assert T["use"] == "validate" and T["test_weight_lb_bu"] == 63.0 and T["bushel_from"] == "file"
    assert gt({"weight": 50.0, "unit": "bu", "test_weight": 63.0, "use": "adjust"})["test_weight_lb_bu"] is None
    T = gt({"weight": 50.0, "unit": "bu/ac", "test_weight": 63.0, "bushels": "grower", "area_ac": 10.0,
            "bushel_from": "declared"})
    assert T["test_weight_lb_bu"] == 63.0 and T["area_ac"] == 10.0 and T["bushel_from"] == "declared"
