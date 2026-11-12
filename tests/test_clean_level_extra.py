# -*- coding: utf-8 -*-
"""The grower's weight, second set, against the KNOWN truth of tests/synthetic.make_two_combines (synthetic only):

  - one rule for a weight 'at the standard moisture' and the same weight entered wet with its grain moisture = the
    standard: the file's one-sided rule (as SMS reports its dry total), one L, Yld_Level sums to it;
  - the OCCD method maps Yld_Lvl_Sy when the sessions recommend the symmetric basis, so the weight is compared with
    Yld_Dry_Sy and the column named sums to it (the note says so only when it does);
  - a mass column that is not lb/ac (kg/ha) is reported with both bushels and their ratio, and the declared bushel
    can be made to win (scale_ticket.bushel_from);
  - a legacy scale_ticket_bu run names one column to map everywhere (the cleaning record, engine.run, the PDF);
  - full runs in kg and t give the L of the run in lb;
  - an overlap that is not a whole number of feet: the acres of a yield per acre within what S2's whole-foot cuts
    allow;
  - validate only with the reference set explicitly, and the mirror case (the high-reading combine as the reference:
    the weight refutes the factor);
  - the advice for a weight given with per-machine totals, and for a candidate left out when a subset is confirmed.

    python -m pytest -q tests/test_clean_level_extra.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import machines as mc  # noqa: E402
from engine.report import clean_report as cr  # noqa: E402
from tests.synthetic import WIDTH_FT, make_two_combines  # noqa: E402

FT2_PER_AC = 43560.0
LB_PER_KG = 2.20462262185


def _ticket(value, unit, basis="wet", **kw):
    return {"value": value, "unit": unit, "basis": basis, "moisture_pct": None, "note": None, **kw}


class Field:
    def __init__(self, folder, bias, **kw):
        self.folder = folder
        self.F = make_two_combines(os.path.join(folder, "data"), bias_b=bias, **kw)
        self.T = self.F["truth"]
        self.runs = {}

    def clean(self, name, ticket=None, settings=None, shp=None, **machines):
        if name not in self.runs:
            S = {"method": "sms3sigma", "tag": name, "moisture": {"standard_pct": self.T["std_moist"]},
                 "machines": {"harmonise": False, **machines}, **(settings or {})}
            if ticket is not None:
                S["scale_ticket"] = ticket
            self.runs[name] = er.clean(shp or self.F["shp"], os.path.join(self.folder, name), S, log=lambda m: None)
        return self.runs[name]


@pytest.fixture(scope="module")
def f5(tmp_path_factory):
    return Field(str(tmp_path_factory.mktemp("f5x")), 1.05)


@pytest.fixture(scope="module")
def f15(tmp_path_factory):
    return Field(str(tmp_path_factory.mktemp("f15x")), 1.15)


def _flagged(R, column, area="opt"):
    df = pyogrio.read_dataframe(R["files"]["flagged_shp"], read_geometry=False)
    a = (df["Dist_Opt"] * df["Wdth_Opt"] if area == "opt" else df["Distance_f"] * df["Swth_Wdth_"]) / FT2_PER_AC
    return float((df[column].fillna(0) * a).sum())


def _texts(story):
    """Every text of a report story (paragraphs and table cells)."""
    out = []
    for f in story:
        if hasattr(f, "text"):
            out.append(str(f.text))
        for row in getattr(f, "_cellvalues", []) or []:
            for c in row:
                out.append(str(getattr(c, "text", c)))
    return out


def test_one_rule_for_at_the_standard_and_wet_at_the_standard(f5):
    """V-level-4: the SMS dry total is one-sided (expand dry moisture off), so a wet weight whose grain moisture is
    the standard and the same figure 'at the standard moisture' are one weight: the same L, and Yld_Level sums to it.
    A wet weight drier than the standard stays as weighed (no credit), as the file's dry yield."""
    T = f5.T
    D = f5.clean("dry", _ticket(T["dry_bu"], "bu", "dry"))
    W = f5.clean("wet_std", _ticket(T["dry_bu"], "bu", "wet", moisture_pct=T["std_moist"]))
    assert W["level"]["factor"] == pytest.approx(D["level"]["factor"], rel=1e-12)
    assert W["level"]["integral_column"] == D["level"]["integral_column"] == "Yld_Vol_Dr"
    assert W["level"]["ticket_bu_at_standard"] == pytest.approx(T["dry_bu"])
    for R in (D, W):
        assert abs(R["level"]["yld_level_vs_ticket_pct"]) < 1e-6
        assert _flagged(R, "Yld_Level") == pytest.approx(T["dry_bu"], rel=2e-5)
        assert "sum to the scale" in R["yield_column_note"]
    # drier than the standard: x min(1, (100 - m) / (100 - Ms)) = 1
    Wd = f5.clean("wet_dry", _ticket(T["dry_bu"], "bu", "wet", moisture_pct=T["std_moist"] - 2.0))
    assert Wd["level"]["ticket_bu_at_standard"] == pytest.approx(T["dry_bu"])
    # wetter: shrunk as the file shrinks a reading at that moisture
    m = T["std_moist"] + 3.0
    Ww = f5.clean("wet_wet", _ticket(T["dry_bu"], "bu", "wet", moisture_pct=m))
    assert Ww["level"]["ticket_bu_at_standard"] == pytest.approx(T["dry_bu"] * (100 - m) / (100 - T["std_moist"]))
    assert "one-sided" in Ww["level"]["comparison_basis"]


def test_occd_method_names_a_column_that_sums_to_the_weight(f5):
    """V-level-0: the OCCD method maps Yld_Lvl_Sy when the sessions recommend the symmetric basis (most readings are
    below the standard here); the weight at the standard moisture is then compared with Yld_Dry_Sy, so the column
    named sums to it (it read +1.2 % before), and the note's 'sum to the scale' is measured, not assumed."""
    T = f5.T
    R = f5.clean("occd_dry", _ticket(T["dry_bu"], "bu", "dry"), settings={"method": "occd"})
    L = R["level"]
    assert R["sessions"]["recommendation"]["map_column"] == "Yld_Dry_Sy"
    assert R["yield_column_for_difm"] == "Yld_Lvl_Sy" and L["integral_column"] == "Yld_Dry_Sy"
    assert abs(L["yld_lvl_sy_vs_ticket_pct"]) < 1e-6
    assert _flagged(R, "Yld_Lvl_Sy", area="logged") == pytest.approx(T["dry_bu"], rel=1e-5)
    assert "sum to the scale" in R["yield_column_note"]
    assert cr._difm_column(R)[0] == "Yld_Lvl_Sy" and "sum to the scale" in cr._difm_column(R)[1]
    assert er.recommended_yield_column(R)[0] == "Yld_Lvl_Sy"
    # Yld_Level (the one-sided yield x L) is the other column now: it reads below the weight, and says so
    assert L["yld_level_vs_ticket_pct"] < -0.5
    # a record whose column does not sum to the weight is never told it does
    off = dict(R, level=dict(L, yld_lvl_sy_vs_ticket_pct=1.168))
    assert "sum to the scale" not in cr._difm_column(off)[1] and "+1.17 %" in cr._difm_column(off)[1]


def test_a_mass_column_in_kg_ha_is_reported_and_the_declared_bushel_can_win(f5, tmp_path):
    """V-level-1: wet mass written in kg/ha (x 1.12085) while the volumes are bu/ac of 60 lb: the file's ratio says
    67.25 lb/bu. The cleaning warns with both bushels and their ratio; bushel_from 'declared' makes the 60 lb/bu of the
    settings win and L is the true one again."""
    T = f5.T
    df = pyogrio.read_dataframe(f5.F["shp"])
    df["Yld_Mass_W"] = df["Yld_Mass_W"] * 1.12085
    shp = str(tmp_path / "kgha.shp")
    df.to_file(shp, engine="pyogrio")
    tk = _ticket(T["wet_lb"], "lb")
    F = f5.clean("kgha_file", tk, settings={"test_weight_lb_bu": 60.0}, shp=shp)
    w = [x for x in F["warnings"] if "the file's own bushel" in x]
    assert len(w) == 1 and "ratio 1.120" in w[0] and "kg/ha" in w[0] and "bushel_from" in w[0]
    true_L = T["wet_bu"] / T["monitor_wet_bu"]
    assert F["level"]["factor"] == pytest.approx(true_L / 1.12085, rel=1e-4)        # the file's bushel: -10.78 %
    D = f5.clean("kgha_decl", dict(tk, bushel_from="declared"), settings={"test_weight_lb_bu": 60.0}, shp=shp)
    assert D["level"]["factor"] == pytest.approx(true_L, rel=1e-6)
    assert D["level"]["test_weight_used"] == pytest.approx(60.0) and "declared" in D["level"]["test_weight_source"]
    assert not any("the file's own bushel" in x and "bushel_from 'file'" in x for x in D["warnings"])
    with pytest.raises(ValueError, match="bushel_from"):
        er.clean(f5.F["shp"], str(tmp_path / "bad"), {"scale_ticket": dict(tk, bushel_from="grower")},
                 log=lambda m: None)


def test_legacy_scale_ticket_bu_names_one_column(f5):
    """V-level-2: the legacy scale_ticket_bu maps the yield and offers Yld_Level; the cleaning record, engine.run and
    the PDF agree (engine.run said Yld_Level, the record and the PDF Yld_Vol_Dr)."""
    T = f5.T
    R = f5.clean("legacy", settings={"scale_ticket_bu": T["dry_bu"], "scale_ticket_basis": "dry"})
    col = R["yield_column_for_difm"]
    assert col == "Yld_Vol_Dr" and R["level_column_for_difm"] == "Yld_Level"
    assert er.recommended_yield_column(R)[0] == col == cr._difm_column(R)[0]
    assert er.leveled_column(R) is None
    assert "Yld_Level instead" in er.difm_note(R)


def test_full_runs_in_kg_and_t_match_lb(f5):
    T = f5.T
    lb = f5.clean("lb", _ticket(T["wet_lb"], "lb"))
    for unit, v in (("kg", T["wet_lb"] / LB_PER_KG), ("t", T["wet_lb"] / LB_PER_KG / 1000.0)):
        R = f5.clean(unit, _ticket(v, unit))
        assert R["level"]["factor"] == pytest.approx(lb["level"]["factor"], rel=1e-9)
        assert R["level"]["ticket_lb"] == pytest.approx(T["wet_lb"], rel=1e-9)
        assert R["level"]["factor"] == pytest.approx(T["wet_bu"] / T["monitor_wet_bu"], rel=1e-6)


def test_yield_per_acre_with_an_overlap_that_is_not_whole_feet(tmp_path):
    """V-level-3: every 8th pass only 22.5 ft from the previous one (7.5 ft of the 30 ft header over ground already
    cut). S2 cuts whole feet from the edge, so it keeps 22 or 23 ft where 22.5 ft are new: the acres of a yield per
    acre without acres (the area harvested after S2) are within that quantum of the ground (0.5 ft of 22.5 ft on one
    pass in eight: 0.28 % at most), not exactly the ground."""
    F = Field(str(tmp_path), 1.05, narrow_gap_m=22.5 * 0.3048)
    T = F.T
    R = F.clean("buac", _ticket(T["dry_bu"] / T["ground_ac"], "bu/ac", "dry"))
    L = R["level"]
    quantum = 0.5 / 22.5 / 8
    assert abs(L["ticket_area_ac"] / T["ground_ac"] - 1) <= quantum + 1e-4
    assert L["export_area_ac"] / T["ground_ac"] - 1 > 0.02                   # the swept area: the overlap twice
    assert L["factor"] == pytest.approx(T["dry_bu"] / T["monitor_dry_bu"], rel=quantum + 2e-3)
    assert WIDTH_FT == 30.0


def test_validate_only_with_the_reference_set_and_its_mirror(f15):
    """V-level-3: the reference named explicitly. A = the unbiased combine: the weight would confirm B's factor
    (validate only: not applied). B = the reference (it reads 15 % high): the candidate is A's factor (x 1.15, it
    would raise the total away from the weight), so the weight refutes it and nothing is applied."""
    T = f15.T
    kw = dict(harmonise=True, method="auto", max_factor=0.10, ticket_confirms=True)
    V = f15.clean("validate_A", _ticket(T["wet_lb"], "lb", use="validate"), reference="COMBINE-A", **kw)
    tt = V["machines"]["ticket_test"]
    assert V["machines"]["reference"] == "COMBINE-A" and tt["would_apply"] == ["COMBINE-B"] and not tt["applied"]
    assert set(V["machines"]["factor_applied"].values()) == {1.0}
    M = f15.clean("adjust_B", _ticket(T["wet_lb"], "lb"), reference="COMBINE-B", **kw)
    tm = M["machines"]["ticket_test"]
    assert M["machines"]["reference"] == "COMBINE-B"
    assert not tm["applied"] and set(M["machines"]["factor_applied"].values()) == {1.0}
    assert tm["candidates"] == ["COMBINE-A"] and tm["with"]["diff_pct"] > tm["without"]["diff_pct"] > 0
    adv = M["machines"]["advice"]["COMBINE-A"]
    assert "did NOT confirm" in adv and "raise the max factor to apply" not in adv
    # the report: the closure row of the factor above the max is printed (there is a candidate) with its verdict
    story = []
    cr._section_level(story, M, 7)
    txt = " ".join(_texts(story))
    assert "Factor above the max (ticket closure test)" in txt and "not confirmed" in txt


def test_report_prints_no_closure_test_without_a_candidate(f5):
    """A-49: with an ordinary factor applied (no candidate above the max) the PDF no longer says 'factor not
    applied', and L goes with the monitor total after the factor."""
    T = f5.T
    R = f5.clean("lb_factor", _ticket(T["wet_lb"], "lb"), harmonise=True, method="auto")
    assert R["machines"]["factor_applied"]["COMBINE-B"] != 1.0
    story = []
    cr._section_level(story, R, 7)
    txt = " ".join(_texts(story))
    assert "ticket closure test" not in txt.lower() and "factor not applied" not in txt
    assert "with the combine factor" in txt
    assert "Monitor totals" in txt and "dry as the file (one-sided)" in txt and "dry, symmetric" in txt


def test_paired_cells_of_a_moisture_column_without_values():
    """Cells are paired on the yield; the moisture is a diagnostic. A moisture column that holds no value at all, or
    none for one of the two groups (a header that logs no moisture), gives cells with an empty moisture instead of
    stopping the cleaning (the sessions diagnostic and the combine factor both pair cells)."""
    import pandas as pd
    from engine.clean import machines
    rng = np.random.default_rng(3)
    n = 400
    d = pd.DataFrame({"_x": rng.uniform(0, 120, n), "_y": rng.uniform(0, 120, n),
                      "g": np.where(np.arange(n) % 2 == 0, "A", "B"), "_yv": 60 + rng.normal(0, 3, n),
                      "Pass_Id": np.arange(n) // 20})
    base = machines.paired_cells(d, "g", "A", "B", 30)
    assert len(base) > 5 and base["ma"].isna().all() and base["mb"].isna().all()
    none = machines.paired_cells(d.assign(_mv=np.nan), "g", "A", "B", 30)
    assert len(none) == len(base) and none["ma"].isna().all() and none["mb"].isna().all()
    assert np.allclose(none["log_ratio"], base["log_ratio"])
    assert machines.ratio_estimate(none, reps=50)["moisture_diff"] is None
    one = machines.paired_cells(d.assign(_mv=np.where(d["g"] == "A", 14.0, np.nan)), "g", "A", "B", 30)
    assert len(one) == len(base) and np.allclose(one["ma"], 14.0) and one["mb"].isna().all()
    both = machines.paired_cells(d.assign(_mv=np.where(d["g"] == "A", 14.0, 15.0)), "g", "A", "B", 30)
    assert machines.ratio_estimate(both, reps=50)["moisture_diff"] == pytest.approx(1.0)


def test_advice_for_totals_and_for_a_candidate_left_out():
    """V-level-6: a weight given with per-machine totals (no closure test runs: the totals level each combine) and a
    candidate not chosen when the weight confirmed another one."""
    t = {"machine": "B", "method": "cells", "primary": True, "cell_m": 30, "factor": 0.87, "gate": "above_max_factor",
         "excludes_one": True}
    P = {"max_factor": 0.10}
    tot = mc.factor_advice([dict(t)], {"B": 1.0}, P, None, ticket_given=True, ticket_skipped="totals")["B"]
    assert "per-machine totals" in tot and "switched off" not in tot and "ticket_confirms" not in tot
    off = mc.factor_advice([dict(t)], {"B": 1.0}, P, None, ticket_given=True, ticket_skipped="switched_off")["B"]
    assert "ticket_confirms off" in off
    tA = dict(t, machine="A", factor=1.12)
    tt = {"machines": ["B"], "would_apply": [], "applied": True, "why": None,
          "verdict": "the paired factor of B is confirmed and applied"}
    adv = mc.factor_advice([dict(tA), dict(t)], {"A": 1.0, "B": 0.87}, P, tt, ticket_given=True)
    assert set(adv) == {"A"}
    assert "confirmed the factor of B only" in adv["A"] and "B is confirmed and applied" not in adv["A"]


def test_report_texts_follow_the_run(f5):
    """A-54 / REP-level-2: the method sentence lists the steps that ran; the sessions row is a diagnostic when the
    file maps another column; the settings table of an SMS run leaves out the OCCD-only and the v1 alias keys; the
    summary gives the kept area and the area-weighted average of the column to map."""
    T = f5.T
    R = f5.clean("dry", _ticket(T["dry_bu"], "bu", "dry"))
    m = cr._sms_method_text(R)
    assert "Optimize Swath Widths" in m and "moisture, speed and dry yield" in m and "clip" not in m   # no boundary
    se = cr._sessions_brief(R)
    assert "would recommend Yld_Dry_Sy" in se and "map Yld_Dry_Sy as the yield" not in se
    _rows, _off, gen = cr._settings_rows(R["settings"])
    keys = [r[0] for r in gen[1:]]
    assert "lag_correction" not in keys and "scale_ticket_bu" not in keys and "harmonise_machines" not in keys
    assert "scale_ticket" in keys
    fm = R["final_map"]
    cl = pyogrio.read_dataframe(R["files"]["difm_ready_shp"], read_geometry=False)
    a = cl["Distance_f"] * cl["Swth_Wdth_"] / FT2_PER_AC
    assert fm["area_ac"] == pytest.approx(float(a.sum()), rel=1e-9)
    assert fm["average_area_weighted"] == pytest.approx(float((cl[fm["column"]] * a).sum() / a.sum()), rel=1e-9)
    off = dict(R, cascade=[dict(c, on=False) if c["filter"] == "S2" else c for c in R["cascade"]])
    assert "Optimize Swath Widths" not in cr._sms_method_text(off)
