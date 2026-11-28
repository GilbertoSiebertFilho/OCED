# -*- coding: utf-8 -*-
"""0.4.0: a negative 3-sigma lower limit of the dry yield is SHOWN as the import minimum in force (display only:
engine/report/limits_shown.py), on synthetic data only. When mean - k SD of a yield pass is negative the filter types
0 and cuts nothing below (the record keeps lo = 0.0); the lowest dry yield the 3-sigma steps see is the import's
minimum, so the replay's card, step 3's Limits and Steps tabs, the cleaning report (limits table, cascade, figure
caption) and the manual-edits table show '5.00 bu/ac (import minimum; 3-sigma gave -40.00, so no cut below)', or
'0.00 bu/ac (3-sigma gave -40.00: no cut below; import minimum 0)' without a minimum. A positive mean - k SD, a floor
above 0 and the moisture and speed steps are shown as before; the cleaning and its files do not change.

    python -m pytest -q tests/test_negative_low_limit.py
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import replay as rp  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from engine.report import limits_shown as ls  # noqa: E402
from tests.synthetic import make_field  # noqa: E402

WIDE_SD = 40.0           # the yield noise that makes mean - 3 SD of the dry yield negative


def _R(min_yield=5.0, k=3.0, dec=2, floor=0.0):
    return {"sms3sigma": {"settings": {"k_sd": k, "round_decimals": dec, "yield_floor": floor},
                          "min_yield": {"value": min_yield, "source": "test"}}}


def _step(mean, sd, lo, hi=150.0, attribute="dry yield", step="S5a"):
    return {"group": "field", "step": step, "attribute": attribute, "unit": "bu/ac", "mean": mean, "sd": sd,
            "lo": lo, "hi": hi, "n_before": 100, "removed": 3, "n_after": 97}


# ------------------------------------------------------------------------------------------------ the texts themselves
def test_a_negative_lower_limit_is_shown_as_the_import_minimum_5():
    s = _step(70.0, 30.72, 0.0)                     # 70 - 3 x 30.72 = -22.16
    L = ls.low_shown(s, _R(5.0))
    assert L["value"] == 5.0 and L["raw"] == -22.16 and L["minimum"] == 5.0
    assert L["text"] == "5.00 bu/ac (import minimum; 3-sigma gave -22.16, so no cut below)"
    assert ls.low_text(s, _R(5.0)) == L["text"]
    assert ls.range_text(s, _R(5.0)) == "5.00 bu/ac (import minimum; 3-sigma gave -22.16, so no cut below) to 150.00"
    assert s["lo"] == 0.0                           # the step row itself is not touched


@pytest.mark.parametrize("minimum", [0.0, None])
def test_a_negative_lower_limit_without_a_minimum_says_import_minimum_0(minimum):
    s = _step(70.0, 30.72, 0.0)
    L = ls.low_shown(s, _R(minimum))
    assert L["value"] == 0.0 and L["minimum"] is None
    assert L["text"] == "0.00 bu/ac (3-sigma gave -22.16: no cut below; import minimum 0)"


@pytest.mark.parametrize("minimum", [5.0, 0.0])
def test_a_positive_lower_limit_is_shown_as_before(minimum):
    s = _step(70.0, 10.0, 40.0, 100.0)
    assert ls.low_shown(s, _R(minimum)) is None
    assert ls.low_text(s, _R(minimum)) == "40.00" and ls.range_text(s, _R(minimum)) == "40.00-100.00"


def test_moisture_speed_a_floor_and_no_limit_are_shown_as_before():
    assert ls.low_shown(_step(14.0, 6.0, 0.0, 32.0, attribute="moisture", step="S3"), _R()) is None
    assert ls.low_shown(_step(4.0, 2.0, 0.0, 10.0, attribute="speed", step="S4"), _R()) is None
    assert ls.low_shown(_step(70.0, 30.72, 10.0), _R(5.0, floor=10.0)) is None      # a floor above 0 cuts
    assert ls.low_shown(_step(None, None, None, None), _R()) is None
    assert ls.range_text(_step(None, None, None, None), _R()) == "-"


def test_the_import_minimum_comes_from_the_record():
    s = _step(70.0, 30.72, 0.0)
    # the import's resolved minimum when the record has no S0 minimum of its own (an older record)
    R = {"sms3sigma": {"settings": {"k_sd": 3.0, "round_decimals": 2}}, "sms_import": {"resolved": {"min_yield": 5.0}}}
    assert ls.low_shown(s, R)["minimum"] == 5.0
    assert ls.import_minimum({"sms3sigma": {"min_yield": {"value": None}}}) is None
    assert ls.import_minimum({"sms3sigma": {"min_yield": {"value": 7.5}}}) == 7.5


def test_the_cascade_criterion_is_shown_with_the_minimum_one_group_and_several():
    R = _R(5.0)
    R["sms3sigma"]["steps"] = [_step(70.0, 30.72, 0.0, 162.16)]
    row = {"filter": "S5a", "on": True, "criterion": "dry yield (scaled) outside mean +/- 3 SD: 0.00-162.16 bu/ac "
                                                     "(SD 30.72 -> 29.00, 5.60 % drop)"}
    assert ls.criterion_shown(R, row) == ("dry yield (scaled) outside mean +/- 3 SD: lower 5.00 bu/ac (import minimum; "
                                          "3-sigma gave -22.16, so no cut below), upper 162.16 bu/ac (SD 30.72 -> "
                                          "29.00, 5.60 % drop)")
    assert ls.criterion_shown(R, {"filter": "S3", "on": True, "criterion": "x 0.00-1.00"}) == "x 0.00-1.00"
    R["sms3sigma"]["steps"] = [_step(70.0, 30.72, 0.0, 162.16), dict(_step(70.0, 10.0, 40.0, 100.0), group="B")]
    many = {"filter": "S5a", "on": True, "criterion": "dry yield (scaled) outside mean +/- 3 SD per machine in 2 "
                                                      "group(s), lower limit floored at 0 (see the limits table)"}
    assert ls.criterion_shown(R, many) == ("dry yield (scaled) outside mean +/- 3 SD per machine in 2 group(s), where "
                                           "3-sigma gave a negative lower limit (1 of 2 groups), the lower limit in "
                                           "force is the import minimum 5.00 bu/ac (no cut below) (see the limits "
                                           "table)")
    R["sms3sigma"]["steps"] = [_step(70.0, 10.0, 40.0, 100.0)]
    pos = {"filter": "S5a", "on": True, "criterion": "dry yield (scaled) outside mean +/- 3 SD: 40.00-100.00 bu/ac"}
    assert ls.criterion_shown(R, pos) == pos["criterion"]


# --------------------------------------------------------------------------------------- a cleaning: record and report
def _clean(tmp, sd, min_yield):
    F = make_field(str(tmp / "in"), yield_sd=sd)
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn", "sms3sigma": {"min_yield": min_yield},
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    return yc.run(F["shp"], str(tmp / "out"), S, log=lambda m: None)


@pytest.fixture(scope="module")
def neg5(tmp_path_factory):
    return _clean(tmp_path_factory.mktemp("neg5"), WIDE_SD, 5.0)


@pytest.fixture(scope="module")
def pos5(tmp_path_factory):
    return _clean(tmp_path_factory.mktemp("pos5"), 5.0, 5.0)


def _story_texts(story) -> list:
    """The text of every paragraph of a report story, table cells included."""
    out = []
    for f in story:
        if hasattr(f, "_cellvalues"):
            for row in f._cellvalues:
                out += [getattr(c, "text", str(c)) for c in row]
        else:
            out.append(getattr(f, "text", ""))
    return out


def test_the_record_keeps_lo_0_and_the_report_shows_the_import_minimum(neg5):
    from engine.report import clean_report as cr
    R = neg5
    s5 = next(s for s in R["sms3sigma"]["steps"] if s["step"] == "S5a")
    raw = s5["mean"] - 3 * s5["sd"]
    assert raw < 0 and s5["lo"] == 0.0              # the filter typed 0: the record is unchanged
    with open(R["files"]["json"], encoding="utf-8") as fh:
        J = json.load(fh)
    assert next(s for s in J["sms3sigma"]["steps"] if s["step"] == "S5a")["lo"] == 0.0
    want = f"5.00 bu/ac (import minimum; 3-sigma gave {ls.round_half_up(raw, 2):.2f}, so no cut below)"
    assert ls.low_text(s5, R) == want
    story = []
    cr._section_sms_limits(story, R, 3)
    T = _story_texts(story)
    assert "5.00*" in T
    assert any(t.startswith("* The low limit in force") and want in t for t in T)
    # the moisture and speed rows keep their numbers
    for s in R["sms3sigma"]["steps"]:
        if s["attribute"] in ("moisture", "speed") and s["lo"] is not None:
            assert f"{s['lo']:.2f}" in T
    crit = ls.criterion_shown(R, next(c for c in R["cascade"] if c["filter"] == "S5a"))
    assert f"lower {want}, upper {s5['hi']:.2f} bu/ac" in crit
    assert next(c for c in R["cascade"] if c["filter"] == "S5a")["criterion"].count(": 0.00-") == 1


def test_a_positive_lower_limit_leaves_the_report_as_it_was(pos5):
    from engine.report import clean_report as cr
    R = pos5
    assert all(ls.low_shown(s, R) is None for s in R["sms3sigma"]["steps"])
    story = []
    cr._section_sms_limits(story, R, 3)
    T = _story_texts(story)
    assert not any("*" in t for t in T) and not any("import minimum" in t for t in T)
    for s in R["sms3sigma"]["steps"]:
        if s["lo"] is not None:
            assert f"{s['lo']:.2f}" in T
    for c in R["cascade"]:
        assert ls.criterion_shown(R, c) == c["criterion"]


def test_the_replay_card_carries_the_minimum_and_says_whose_limits(neg5, pos5):
    P = rp.replay_payload(neg5["files"]["flagged_shp"], kind="clean", record=neg5)
    s5 = next(s for s in neg5["sms3sigma"]["steps"] if s["step"] == "S5a")
    for cid, L in P["limits"].items():
        assert L["S5a"][:2] == [0.0, s5["hi"]]                       # the filter's own limits stay
        assert L["S5a"][4] == {"v": 5.0, "why": ls.low_shown(s5, neg5)["reason"]}
        assert all(len(v) == 4 for k, v in L.items() if not k.startswith("S5"))
    assert "limits_of" not in P                                       # one combine: its own limits
    h = rp.replay_html(P)
    assert "3-sigma limits of this combine" in h and "3-sigma limits of all the combines (one group)" in h
    P2 = rp.replay_payload(pos5["files"]["flagged_shp"], kind="clean", record=pos5)
    assert all(len(v) == 4 for L in P2["limits"].values() for v in L.values())


def test_limits_shared_by_several_combines_are_named_so():
    R = {"sms3sigma": {"steps": [_step(70.0, 10.0, 40.0, 100.0)]}}
    assert rp.limits_shared(R, ["A", "B"]) and not rp.limits_shared(R, ["A"])
    R2 = {"sms3sigma": {"steps": [dict(_step(70.0, 10.0, 40.0), group="A"), dict(_step(70.0, 10.0, 40.0), group="B")]}}
    assert not rp.limits_shared(R2, ["A", "B"])


# ---------------------------------------------------------------------------------------------- the app (lazy tabs)
def _limits_df(d):
    for e in d.at.dataframe:
        cols = list(e.value.columns)
        if "lo" in cols and "hi" in cols and "step" in cols:
            return e, json.loads(e.proto.columns or "{}")
    raise AssertionError("no limits table")


def _criteria(d) -> list:
    return next(list(e.value["criterion"]) for e in d.at.dataframe if "criterion" in e.value.columns)


def _app_clean(field_shp, tmp_path, monkeypatch, min_yield=None):
    from tests.test_app_tabs import Drive, _open
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field_shp)
    if min_yield is not None:                       # step 1: the import's own minimum, applied
        d.at.toggle(key=d.key("fi_def_", "toggle")).set_value(False)
        d.run()
        d.at.number_input(key=d.key("fi_min_", "number_input")).set_value(float(min_yield))
        d.run()
        d.click(d.key("fi_go_"))
    d.open(3)
    d.click("clean_one")
    return d, d.at.session_state["cleaned"][d.at.session_state["active"]]["R"]


@pytest.mark.lazy_tabs
@pytest.mark.parametrize("min_yield", [None, 5.0])
def test_step_3_limits_and_steps_tabs_show_the_import_minimum(tmp_path, monkeypatch, min_yield):
    F = make_field(str(tmp_path / "in"), yield_sd=WIDE_SD)
    d, R = _app_clean(F["shp"], tmp_path, monkeypatch, min_yield)
    s5 = next(s for s in R["sms3sigma"]["steps"] if s["step"] == "S5a")
    assert s5["lo"] == 0.0 and s5["mean"] - 3 * s5["sd"] < 0
    raw = f"{ls.round_half_up(s5['mean'] - 3 * s5['sd'], 2):.2f}"
    want = (f"5.00 bu/ac (import minimum; 3-sigma gave {raw}, so no cut below)" if min_yield else
            f"0.00 bu/ac (3-sigma gave {raw}: no cut below; import minimum 0)")
    e, cfg = _limits_df(d)
    rows = e.value.to_dict("records")
    assert [r["lo"] for r in rows if r["step"] == "S5a"] == [want]
    for r, s in zip(rows, R["sms3sigma"]["steps"]):
        if s["attribute"] != "dry yield" and s["lo"] is not None:
            assert r["lo"] == f"{s['lo']:.2f}"                    # moisture and speed: their own numbers
    crit = [c for c in _criteria(d) if c.startswith("dry yield (scaled)")]
    assert crit and f"lower {want}, upper {s5['hi']:.2f} bu/ac" in crit[0]


@pytest.mark.lazy_tabs
def test_step_3_limits_of_a_positive_lower_limit_are_numbers_as_before(tmp_path, monkeypatch):
    F = make_field(str(tmp_path / "in"))
    d, R = _app_clean(F["shp"], tmp_path, monkeypatch)
    e, cfg = _limits_df(d)
    assert str(e.value["lo"].dtype).startswith("float")
    lo = [s["lo"] for s in R["sms3sigma"]["steps"]]
    assert [None if v != v else v for v in e.value["lo"].tolist()] == lo
    assert not any("import minimum" in c for c in _criteria(d))
