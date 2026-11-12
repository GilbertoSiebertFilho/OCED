# -*- coding: utf-8 -*-
"""The grower's weight and the combine factor against a KNOWN truth (tests/synthetic.make_two_combines: two combines
side by side on alternate passes, one reading 5 % or 15 % high, a weight computed from the grain itself).

What must hold, each with the size of the error it guards against:
  - a weight in lb / kg / t is compared as a MASS: another bushel weight than the file's (63 against 60 lb/bu) must
    not move L (it made L wrong by the ratio of the two bushel weights);
  - a weight at the standard moisture is compared with the file's own dry yield (one-sided shrink), the column that is
    leveled, so Yld_Level sums to the weight (the symmetric total made L 1.5 % too low on this field);
  - a yield per acre without acres is over the ground harvested, every strip once, not over the swept area (+3.0 %);
  - with a combine factor the level in the file (factor_final) goes with the monitor total after the factor;
  - 'validate only' applies no combine factor because of the weight;
  - machine x machine is estimated on the yield of the map (after Optimize Swath Widths), the one it is applied to;
  - the cleaning record, the PDF and engine.run name the same column to map; Yld_Harm only when a factor was applied;
  - a max factor of 1 % cleans the file.

    python -m pytest -q tests/test_level.py
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
from engine.clean import yield_clean as yc  # noqa: E402
from engine.report import clean_report as cr  # noqa: E402
from tests.synthetic import make_two_combines  # noqa: E402

FT2_PER_AC = 43560.0
LB_PER_KG = 2.20462262185


def _ticket(value, unit, basis="wet", **kw):
    return {"value": value, "unit": unit, "basis": basis, "moisture_pct": None, "note": None, **kw}


class Field:
    """One synthetic field and its cleanings, each run once."""

    def __init__(self, folder, bias):
        self.folder = folder
        self.F = make_two_combines(os.path.join(folder, "data"), bias_b=bias)
        self.T = self.F["truth"]
        self.runs = {}

    def clean(self, name, ticket=None, settings=None, **machines):
        if name not in self.runs:
            S = {"method": "sms3sigma", "tag": name, "moisture": {"standard_pct": self.T["std_moist"]},
                 "machines": {"harmonise": False, **machines}, **(settings or {})}
            if ticket is not None:
                S["scale_ticket"] = ticket
            self.runs[name] = er.clean(self.F["shp"], os.path.join(self.folder, name), S, log=lambda m: None)
        return self.runs[name]


@pytest.fixture(scope="module")
def f5(tmp_path_factory):
    return Field(str(tmp_path_factory.mktemp("f5")), 1.05)


@pytest.fixture(scope="module")
def f15(tmp_path_factory):
    return Field(str(tmp_path_factory.mktemp("f15")), 1.15)


def _flagged_total(R, column):
    """Sum of a yield column of the flagged file over the map's area (the optimised distance x width): what the
    column 'sums to', computed from the file alone."""
    df = pyogrio.read_dataframe(R["files"]["flagged_shp"], read_geometry=False)
    return float((df[column].fillna(0) * df["Dist_Opt"] * df["Wdth_Opt"] / FT2_PER_AC).sum())


def _clean_fields(R):
    return list(pyogrio.read_info(R["files"]["difm_ready_shp"])["fields"])


# ---------------------------------------------------------------------------------------------- the bushels (pure)
def test_ticket_summary_compares_mass_whatever_the_bushel_weight():
    """lb / kg / t: bushels of the file whatever other bushel weight is given; bu: as given, or bushels of the
    grower's own bushel weight when the ticket carries it."""
    lb = 240_000.0
    for value, unit in ((lb, "lb"), (lb / LB_PER_KG, "kg"), (lb / LB_PER_KG / 1000.0, "t")):
        for explicit in (False, True):
            s = yc.ticket_summary({"scale_ticket": _ticket(value, unit)}, 60.0, "the file", grower_test_weight=63.0,
                                  grower_explicit=explicit)
            assert s["ticket_bu"] == pytest.approx(lb / 60.0)             # never lb / 63
            assert s["ticket_lb"] == pytest.approx(lb)
            assert s["ticket_bu_grower"] == pytest.approx(lb / 63.0)      # reported, not compared
            assert s["bushels_differ"] and "not compared" in s["caption"]
    # bushels given, another bushel weight only in the settings: compared as given
    s = yc.ticket_summary({"scale_ticket": _ticket(4000.0, "bu")}, 60.0, "the file", grower_test_weight=63.0)
    assert s["ticket_bu"] == pytest.approx(4000.0) and s["ticket_lb"] == pytest.approx(4000.0 * 60.0)
    assert "compared as given" in s["caption"] and not s["grower_bushels_applied"]
    # the grower's own bushel weight: his bushels weigh 63 lb, the same grain is 4000 x 63 / 60 of the file's bushels
    s = yc.ticket_summary({"scale_ticket": _ticket(4000.0, "bu", test_weight_lb_bu=63.0)}, 60.0, "the file",
                          grower_test_weight=63.0, grower_explicit=True)
    assert s["ticket_lb"] == pytest.approx(252_000.0) and s["ticket_bu"] == pytest.approx(252_000.0 / 60.0)
    assert s["ticket_bu_grower"] == pytest.approx(4000.0) and s["grower_bushels_applied"]
    # a yield per acre the same way
    s = yc.ticket_summary({"scale_ticket": _ticket(50.0, "bu/ac", test_weight_lb_bu=63.0)}, 60.0, "the file",
                          area_ac=100.0, area_source="the field boundary", grower_test_weight=63.0, grower_explicit=True)
    assert s["ticket_bu"] == pytest.approx(50.0 * 100.0 * 63.0 / 60.0)
    # one bushel weight (or two within 0.5 %): nothing changes
    s = yc.ticket_summary({"scale_ticket": _ticket(lb, "lb")}, 60.0, "the file", grower_test_weight=60.2)
    assert s["ticket_bu"] == pytest.approx(lb / 60.0) and not s["bushels_differ"] and s["ticket_bu_grower"] is None
    # no bushel known for the file: the one given is all there is
    s = yc.ticket_summary({"scale_ticket": _ticket(lb, "lb")}, None, None, grower_test_weight=63.0)
    assert s["ticket_bu"] == pytest.approx(lb / 63.0)
    with pytest.raises(ValueError, match="test weight"):
        yc.ticket_summary({"scale_ticket": _ticket(lb, "lb")})


def test_caption_before_the_cleaning_uses_the_files_bushel():
    """engine.run.ticket_conversion (the app's caption): the same rule as the cleaning."""
    c = er.ticket_conversion(_ticket(240_000.0, "lb"), test_weight=63.0, file_tw=60.0)
    assert c["bu"] == pytest.approx(4000.0) and c["bu_grower"] == pytest.approx(240_000.0 / 63.0)
    assert c["test_weight"] == 60.0
    c = er.ticket_conversion(_ticket(4000.0, "bu"), test_weight=63.0, file_tw=60.0)
    assert c["bu"] == pytest.approx(4000.0) and "compared as given" in c["text"]
    c = er.ticket_conversion(_ticket(4000.0, "bu", test_weight_lb_bu=63.0), file_tw=60.0)
    assert c["bu"] == pytest.approx(4000.0 * 63 / 60) and c["lb"] == pytest.approx(252_000.0)
    c = er.ticket_conversion(_ticket(240_000.0, "lb"), test_weight=63.0)           # no file: the weight given
    assert c["bu"] == pytest.approx(240_000.0 / 63.0) and not c["bushels_differ"]
    assert er.ticket_settings({"scale_ticket": _ticket(1.0, "bu", use="Validate")})["use"] == "validate"
    with pytest.raises(ValueError, match="use"):
        er.ticket_settings({"scale_ticket": _ticket(1.0, "bu", use="level")})


def test_max_factor_at_one_percent_is_accepted():
    """The app's 'Max factor' at its minimum (1 %) met the default min_factor (1 %) and every cleaning failed."""
    S = yc.merge_settings({"machines": {"harmonise": True, "max_factor": 0.01}})
    assert S["machines"]["min_factor"] == pytest.approx(0.005) and S["machines"]["max_factor"] == 0.01
    assert yc.merge_settings({"machines": {"harmonise": False, "max_factor": 0.01}})["machines"]["max_factor"] == 0.01
    with pytest.raises(ValueError, match="min_factor"):
        yc.merge_settings({"machines": {"min_factor": 0.05, "max_factor": 0.02}})


def test_advice_never_says_raise_the_max_after_the_scale_refuted():
    t = {"machine": "B", "method": "cells", "primary": True, "cell_m": 30, "factor": 0.87, "gate": "above_max_factor",
         "excludes_one": True}
    P = {"max_factor": 0.10}
    no_weight = mc.factor_advice([dict(t)], {"B": 1.0}, P, None, ticket_given=False)["B"]
    assert "raise the max factor to apply it, or give the grower's weight" in no_weight
    refuted = mc.factor_advice([dict(t)], {"B": 1.0}, P, {"would_apply": [], "why": "the monitor total already "
                                                         "agrees with the grower's weight"}, ticket_given=True)["B"]
    assert "did NOT confirm" in refuted and "raise the max factor to apply" not in refuted
    unproven = mc.factor_advice([dict(t, gate="above_max_factor_unconfirmed", excludes_one=False)], {"B": 1.0}, P)["B"]
    assert "not proven" in unproven and "did not confirm" not in unproven
    assert mc.factor_advice([dict(t, gate="applied")], {"B": 0.87}, P) == {}          # applied: nothing to explain


# ---------------------------------------------------------------------------------------------- the synthetic field
def test_synthetic_truth(f5):
    """The field is what the tests assume: B reads 5 % high, the swept area is 3 % more than the ground, and most
    readings are drier than the standard moisture (so the one-sided and the symmetric dry totals differ)."""
    T = f5.T
    b = T["by_machine"]["COMBINE-B"]
    assert b["monitor_wet_bu"] / b["true_wet_bu"] == pytest.approx(1.05)
    assert T["swept_ac"] / T["ground_ac"] == pytest.approx(1.030, abs=0.002)
    assert T["share_below_standard"] > 0.7 and T["dry_sym_bu"] / T["dry_bu"] > 1.01
    assert T["wet_lb"] == pytest.approx(T["wet_bu"] * 60.0)


def test_weight_in_lb_with_another_bushel_weight_and_the_combine_factor(f5):
    """The grower's weight in lb = the grain itself, a bushel weight of 63 lb/bu where the app writes it today
    (settings.test_weight_lb_bu), the file's bushel 60, the combine factor on: L before the factor is the ratio of
    the masses (0.9763; 60 / 63 lower before), the factor of B is 1 / 1.05, and the level in the file is 1 with the
    monitor total after the factor."""
    T = f5.T
    R = f5.clean("lb63", _ticket(T["wet_lb"], "lb"), settings={"test_weight_lb_bu": 63.0}, harmonise=True,
                 method="auto")
    L, C = R["level"], R["level"]["closure"]
    true_L = T["wet_bu"] / T["monitor_wet_bu"]
    assert L["factor"] == pytest.approx(true_L, rel=1e-6)                       # mass against mass
    assert L["ticket_bu"] == pytest.approx(T["wet_lb"] / 60.0) and L["test_weight_used"] == pytest.approx(60.0)
    assert L["ticket_bu_grower"] == pytest.approx(T["wet_lb"] / 63.0) and L["test_weight_grower"] == 63.0
    # the lb row and the bu row of the app's table give the same percentage
    assert L["export_total_lb"] / L["ticket_lb"] == pytest.approx(L["export_total_bu"] / L["scale_ticket_bu"], rel=1e-9)
    # the combine factor: B x 1 / 1.05, proven on the passes side by side
    fa = R["machines"]["factor_applied"]
    assert fa["COMBINE-A"] == 1.0 and fa["COMBINE-B"] == pytest.approx(1 / 1.05, rel=0.01)
    # the level in the file belongs to the monitor total AFTER the factor
    assert L["factor_final"] == pytest.approx(1.0, abs=0.01)
    assert L["factor_before_harmonisation"] == L["factor"] and L["combine_factor_changed_total"]
    assert L["monitor_total_final_bu"] == pytest.approx(L["export_total_harmonised_bu"])
    assert C["factor_final"] == L["factor_final"] and C["diff_final_pct"] == C["diff_after_pct"]
    assert C["monitor_final_bu"] * L["factor_final"] == pytest.approx(L["scale_ticket_bu"], rel=1e-9)
    assert abs(C["diff_final_pct"]) < 1.0 and C["band"] == "<= 1 %" and abs(C["diff_pct"]) > 2.0
    cap = er.level_caption(R)
    assert "with the combine factor" in cap and f"{L['export_total_harmonised_bu']:,.0f} bu" in cap
    assert er.level_factor_text(L).startswith(f"{L['factor_final']:.4f} (before the combine harmonisation")
    # leveled: the wet yield x factor x L sums to the weight, in the file's bushel
    assert L["leveled_export_integral_bu"] == pytest.approx(T["wet_lb"] / 60.0, rel=1e-9)
    assert R["yield_column_for_difm"] == "Yld_Level" and {"Yld_Harm", "Yld_Level"} <= set(_clean_fields(R))


def test_weight_at_the_standard_moisture_is_compared_with_the_files_dry_yield(f5):
    """'At the standard moisture': against the file's own dry yield (one-sided), so L is right and Yld_Level sums to
    the weight; the cleaning record, the PDF and engine.run name the same column although the sessions diagnostic
    would recommend the symmetric basis."""
    T = f5.T
    R = f5.clean("dry", _ticket(T["dry_bu"], "bu", "dry"))
    L = R["level"]
    assert R["moisture"]["shrink"] == "one_sided" and L["integral_column"] == "Yld_Vol_Dr"
    assert L["comparison_basis"].startswith("dry") and "one-sided" in L["comparison_basis"]
    assert L["export_total_bu"] == pytest.approx(T["monitor_dry_bu"], rel=1e-6)          # not the symmetric total
    assert L["monitor_total_dry_sym_bu"] / L["monitor_total_dry_bu"] == pytest.approx(T["dry_sym_bu"] / T["dry_bu"],
                                                                                      rel=1e-3)
    assert L["monitor_total_dry_sym_bu"] / L["monitor_total_dry_bu"] > 1.01           # what L was too low by
    assert L["factor"] == pytest.approx(T["dry_bu"] / T["monitor_dry_bu"], rel=1e-6)
    assert abs(L["yld_level_vs_ticket_pct"]) < 1e-6
    assert _flagged_total(R, "Yld_Level") == pytest.approx(T["dry_bu"], rel=2e-5)        # from the file itself
    # one column to map, everywhere
    assert R["sessions"]["recommendation"]["map_column"] == "Yld_Dry_Sy"                 # the diagnostic disagrees
    assert "Yld_Lvl_Sy" in R["difm_ready_added_columns"]
    assert R["yield_column_for_difm"] == "Yld_Level"
    assert cr._difm_column(R)[0] == "Yld_Level" and er.recommended_yield_column(R)[0] == "Yld_Level"
    assert R["final_map"]["column"] == "Yld_Level"
    # harmonisation off: no Yld_Harm in the clean file
    assert "Yld_Harm" not in _clean_fields(R)


def test_yield_per_acre_without_acres_is_over_the_ground_once(f5):
    """bu/ac, no acres, no boundary: x the area harvested (every strip once, after Optimize Swath Widths), which is
    the ground; the swept area counts 3 % twice on this field."""
    T = f5.T
    R = f5.clean("buac", _ticket(T["dry_bu"] / T["ground_ac"], "bu/ac", "dry"))
    L = R["level"]
    assert L["ticket_area_ac"] == pytest.approx(T["ground_ac"], rel=2e-3)
    assert L["ticket_area_ac"] == pytest.approx(R["sms3sigma"]["area_after_swath_ac"])
    assert "every strip once" in L["ticket_area_source"] and "no boundary" in L["ticket_area_source"]
    assert L["export_area_ac"] == pytest.approx(T["swept_ac"], rel=1e-6)                 # the swept area, still reported
    assert L["export_area_ac"] / L["ticket_area_ac"] > 1.025
    assert L["monitor_area_ac"] == L["ticket_area_ac"]
    assert L["factor"] == pytest.approx(T["dry_bu"] / T["monitor_dry_bu"], rel=3e-3)     # +1.4 % before
    assert "every strip once" in L["ticket_caption"]


def test_machine_x_machine_is_estimated_on_the_mapped_yield(f5):
    """B overlaps more than A, so before Optimize Swath Widths its logged yield reads lower and hides its +5 %:
    estimated there the factor was 1.011 (CI includes 1, nothing applied); on the yield of the map it is the ratio of
    the two map means, 1 / 1.05."""
    R = f5.clean("machine", harmonise=True, method="machine")
    M = R["machines"]
    row = next(r for r in M["methods"] if r["method"] == "machine" and r["machine"] == "COMBINE-B")
    assert row["factor"] == pytest.approx(M["whole_field_ratio"]["COMBINE-B"], rel=1e-9)
    assert row["factor"] == pytest.approx(1 / 1.05, rel=0.01)
    assert M["factor_applied"]["COMBINE-B"] == pytest.approx(row["factor"])
    # after the factor the two combines' means of the map agree
    cl = pyogrio.read_dataframe(R["files"]["difm_ready_shp"], read_geometry=False)
    means = cl.groupby("Machine")["Yld_Harm"].mean()
    assert means["COMBINE-A"] == pytest.approx(means["COMBINE-B"], rel=1e-3)
    assert R["yield_column_for_difm"] == "Yld_Harm"
    assert er.recommended_yield_column(R)[0] == "Yld_Harm" and cr._difm_column(R)[0] == "Yld_Harm"


def test_factor_switched_on_but_not_applied_and_max_factor_one_percent(f5):
    """A max factor of 1 %: the file is cleaned; the 5 % factor is above it and not applied, so the clean file
    carries no Yld_Harm and every place names the yield itself as the column to map."""
    R = f5.clean("max1", harmonise=True, method="auto", max_factor=0.01)
    M = R["machines"]
    assert set(M["factor_applied"].values()) == {1.0}
    assert R["settings"]["machines"]["min_factor"] == pytest.approx(0.005)
    assert "Yld_Harm" not in R["difm_ready_added_columns"] and "Yld_Harm" not in _clean_fields(R)
    assert R["yield_column_for_difm"] == "Yld_Vol_Dr" and R["final_map"]["column"] == "Yld_Vol_Dr"
    assert cr._difm_column(R)[0] == "Yld_Vol_Dr" and er.recommended_yield_column(R)[0] == "Yld_Vol_Dr"
    assert "Yld_Harm" in list(pyogrio.read_info(R["files"]["flagged_shp"])["fields"])    # the flagged file keeps it
    adv = M["advice"]["COMBINE-B"]
    assert "above the max factor (1 %)" in adv and "raise the max factor to apply it, or give the grower's weight" in adv
    # an older record that names Yld_Harm with every factor 1 is read the same way
    old = dict(R, yield_column_for_difm="Yld_Harm")
    assert cr._difm_column(old)[0] == "Yld_Vol_Dr" and er.recommended_yield_column(old)[0] == "Yld_Vol_Dr"


def test_validate_only_lets_the_weight_apply_no_factor(f15):
    """B reads 15 % high, max factor 10 %, the grower's weight = the grain. Adjust: the weight confirms the factor and
    it is applied (the level is then 1). Validate only: the same test is reported, nothing is applied, no leveled
    column and no Yld_Harm reach the clean file. A weight equal to the monitor's total refutes the factor."""
    T = f15.T
    kw = dict(harmonise=True, method="auto", max_factor=0.10, ticket_confirms=True)
    A = f15.clean("adjust", _ticket(T["wet_lb"], "lb"), **kw)
    assert A["machines"]["ticket_test"]["applied"] and A["machines"]["factor_applied"]["COMBINE-B"] == pytest.approx(
        1 / 1.15, rel=0.01)
    assert A["level"]["factor_final"] == pytest.approx(1.0, abs=0.01) and A["yield_column_for_difm"] == "Yld_Level"
    assert A["machines"]["advice"] == {}
    V = f15.clean("validate", _ticket(T["wet_lb"], "lb", use="validate"), **kw)
    tt = V["machines"]["ticket_test"]
    assert set(V["machines"]["factor_applied"].values()) == {1.0}
    assert tt["validate_only"] and not tt["applied"] and tt["would_apply"] == ["COMBINE-B"]
    assert "validate only" in V["machines"]["advice"]["COMBINE-B"]
    assert V["level"]["use"] == "validate"
    assert V["level"]["factor_final"] == pytest.approx(T["wet_bu"] / T["monitor_wet_bu"], rel=1e-6)   # the validation
    fields = _clean_fields(V)
    assert not {"Yld_Level", "Yld_Lvl_Sy", "Yld_Harm"} & set(fields)
    assert V["yield_column_for_difm"] == "Yld_Vol_Dr" and "level_column_for_difm" not in V
    assert cr._difm_column(V)[0] == "Yld_Vol_Dr" and er.recommended_yield_column(V)[0] == "Yld_Vol_Dr"
    cl = pyogrio.read_dataframe(V["files"]["difm_ready_shp"], read_geometry=False)
    ca = pyogrio.read_dataframe(A["files"]["difm_ready_shp"], read_geometry=False)
    assert cl["Yld_Vol_Dr"].mean() == pytest.approx(ca["Yld_Vol_Dr"].mean(), rel=1e-9)   # the monitor's yields as cleaned
    # the scale refutes the factor: never 'raise the max factor to apply it'
    N = f15.clean("refuted", _ticket(T["monitor_wet_bu"] * 60.0, "lb"), **kw)
    assert set(N["machines"]["factor_applied"].values()) == {1.0} and not N["machines"]["ticket_test"]["applied"]
    adv = N["machines"]["advice"]["COMBINE-B"]
    assert "did NOT confirm" in adv and "raise the max factor to apply" not in adv
    assert np.isclose(N["level"]["factor_final"], 1.0, atol=1e-6)
