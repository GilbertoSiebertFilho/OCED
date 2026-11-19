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


def test_yield_per_acre_over_a_boundary_larger_than_the_ground_is_warned(f5):
    """bu/ac without acres is made a total over the boundary (the documented default, not changed): when the boundary
    and the ground harvested once differ by more than 2 %, a warning names both areas and both L; L over the
    harvested ground = L over the boundary x harvested / boundary. Acres given: no such warning."""
    import geopandas as gpd
    from tests.synthetic import _rect
    T = f5.T
    df = f5.F["df"]
    big = os.path.join(f5.folder, "big_boundary.geojson")
    gpd.GeoDataFrame({"Name": ["big"]}, geometry=[_rect(-60.0, float(df["x"].max()) + 60.0, -60.0,
                                                         float(df["y"].max()) + 60.0)], crs="EPSG:4326").to_file(
        big, driver="GeoJSON")
    aoi = {"aoi": {"file": big, "buffer_m": 0.01, "clip_output": True}}
    R = f5.clean("buac_big", _ticket(T["dry_bu"] / T["ground_ac"], "bu/ac", "dry"), settings=aoi)
    L = R["level"]
    ck = L["ticket_area_check"]
    assert ck["boundary_ac"] == pytest.approx(L["ticket_area_ac"]) and L["ticket_area_source"] == "the field boundary"
    assert ck["harvested_once_ac"] == pytest.approx(R["sms3sigma"]["area_after_swath_ac"])
    assert ck["boundary_vs_harvested_pct"] > 30
    assert ck["factor_over_boundary"] == pytest.approx(L["factor_final"] if L["factor_final"] is not None
                                                       else L["factor"])
    assert ck["factor_over_harvested"] == pytest.approx(ck["factor_over_boundary"] * ck["harvested_once_ac"]
                                                        / ck["boundary_ac"])
    assert ck["factor_over_harvested"] == pytest.approx(T["dry_bu"] / T["monitor_dry_bu"], rel=3e-3)
    w = [x for x in R["warnings"] if x.startswith("grower's weight:") and "harvested once" in x]
    assert len(w) == 1 and f"{ck['boundary_ac']:,.2f} ac" in w[0] and f"{ck['harvested_once_ac']:,.2f} ac" in w[0]
    assert f"L = {ck['factor_over_boundary']:.4f}" in w[0] and f"would be {ck['factor_over_harvested']:.4f}" in w[0]
    R2 = f5.clean("buac_big_acres", _ticket(T["dry_bu"] / T["ground_ac"], "bu/ac", "dry", area_ac=T["ground_ac"]),
                  settings=aoi)
    assert "ticket_area_check" not in R2["level"]
    assert not any("harvested once" in x for x in R2["warnings"])


def test_the_leveled_column_sums_are_said_for_every_reading_and_for_the_clean_file(f5):
    """The processed readings x L sum to the weight compared; the clean file (read back) sums to less, by the grain
    of the readings the cleaning removed: the record, the note, the PDF's sentence and engine.run give both."""
    T = f5.T
    R = f5.clean("lb_sums", _ticket(T["wet_lb"], "lb"))
    L = R["level"]
    clean = pyogrio.read_dataframe(R["files"]["difm_ready_shp"], read_geometry=False)
    c_sum = float((clean["Yld_Level"] * clean["Distance_f"] * clean["Swth_Wdth_"] / FT2_PER_AC).sum())
    assert L["clean_file_level_column"] == "Yld_Level"
    assert L["clean_file_level_sum_bu"] == pytest.approx(c_sum, rel=1e-6)
    tick = L["ticket_compared_bu"]
    assert L["clean_file_level_vs_ticket_pct"] == pytest.approx(100 * (c_sum / tick - 1), abs=1e-6)
    assert L["removed_share_of_leveled_pct"] == pytest.approx(100 * (1 - c_sum / L["yld_level_integral_bu"]))
    assert L["removed_share_of_leveled_pct"] > 0 and L["clean_file_level_vs_ticket_pct"] < L["yld_level_vs_ticket_pct"]
    gap_txt = f"{L['clean_file_level_vs_ticket_pct']:+.2f} %"
    assert "over every processed reading" in R["yield_column_note"] and gap_txt in R["yield_column_note"]
    assert "the values read back from the clean file" in R["yield_column_note"]
    assert L["difm_note"] == R["yield_column_note"]
    assert gap_txt in cr._difm_column(R)[1] and "over every processed reading" in cr._difm_column(R)[1]
    assert gap_txt in er.difm_note(R)


def test_no_sentence_says_the_leveled_column_sums_to_the_weight_without_its_qualifier(f5):
    """A Case IH / New Holland card whose readings differ from its Summary (the card warning fires): no warning, note
    or rule says 'sums to the grower's weight' without 'over every processed reading', since the clean file sums
    less (the readings the cleaning removed)."""
    T = f5.T
    src = {"format": "cnh_cn1", "label": "synthetic card", "totals": {"wet_lb": T["wet_lb"] * 1.04},
           "sms_summary": {"wet_lb": T["wet_lb"]}}
    S = {"method": "sms3sigma", "tag": "cnh_card", "moisture": {"standard_pct": T["std_moist"]},
         "machines": {"harmonise": False}, "scale_ticket": _ticket(T["dry_bu"], "bu", "dry")}
    R = er.clean(f5.F["shp"], os.path.join(f5.folder, "cnh_card"), S, log=lambda m: None, source=src)
    w = [x for x in R["warnings"] if "card's own Summary" in x]
    assert len(w) == 1 and "over every processed reading" in w[0]
    assert R["level"]["clean_file_level_vs_ticket_pct"] < -0.05       # the clean file does sum less
    texts = list(R["warnings"]) + list(R.get("notes") or []) + [R["level"]["rule"], R["yield_column_note"],
                                                                cr._difm_column(R)[1], er.difm_note(R)]
    for t in texts:
        for bad in ("sums to the grower's weight", "integrates to it"):
            if bad in t:
                i = t.index(bad)
                assert "over every processed reading" in t[max(0, i - 160): i + 200], t


def test_grain_set_aside_by_the_field_of_interest_names_the_whole_file_L(f5):
    """A field of interest that leaves out the last 15 m of 600 m passes (about 2.5 % of the grain, under the 5 % of
    the older warning): L is unchanged (the weight is taken as the field of interest's) and a warning names the
    set-aside grain and the L of the whole file. Without a field of interest: no such warning."""
    import geopandas as gpd
    from tests.synthetic import _rect
    T = f5.T
    df = f5.F["df"]
    cut = os.path.join(f5.folder, "cut_boundary.geojson")
    gpd.GeoDataFrame({"Name": ["cut"]}, geometry=[_rect(-60.0, float(df["x"].max()) - 15.0, -60.0,
                                                         float(df["y"].max()) + 60.0)], crs="EPSG:4326").to_file(
        cut, driver="GeoJSON")
    R = f5.clean("lb_cut", _ticket(T["wet_lb"], "lb"), settings={"aoi": {"file": cut, "buffer_m": 0.01,
                                                                         "clip_output": True}})
    L = R["level"]
    share = L["set_aside_integral_bu"] / L["export_total_bu"]
    assert 0.01 < share < 0.05
    assert L["factor_whole_file"] == pytest.approx(L["scale_ticket_bu"] / (L["export_total_bu"]
                                                                           + L["set_aside_integral_bu"]))
    w = [x for x in R["warnings"] if "set aside by the field of interest" in x]
    assert len(w) == 1 and f"L = {L['factor']:.4f}" in w[0] and f"{L['factor_whole_file']:.4f} (whole file)" in w[0]
    R0 = f5.clean("lb_sums", _ticket(T["wet_lb"], "lb"))
    assert not any("set aside" in x for x in R0["warnings"])


def _left_out_case(tmp_path, ticket=None, source=None, low_every=None):
    """A synthetic export imported as SMS with a 5 bu/ac minimum (its near-zero readings left out), cleaned with the
    boundary (20 m short of the passes) and a wet weight in lb: (R, record, the export's frame). low_every: every
    so many readings logged a twentieth of their grain (low flow), so that more grain is left out at import."""
    import geopandas as gpd
    from engine.clean import sms3sigma as sms
    from tests.synthetic import make_field
    F = make_field(str(tmp_path / "f"))
    if low_every:
        g = gpd.read_file(F["shp"])
        low = (np.arange(len(g)) % int(low_every)) == 0
        for c in ("Yld_Mass_W", "Yld_Vol_We", "Yld_Vol_Dr", "Yld_Mass_D"):
            if c in g:
                g.loc[low, c] = g.loc[low, c].astype(float) * 0.05
        F = dict(F, shp=str(tmp_path / "low.shp"))
        g.to_file(F["shp"], engine="pyogrio")
    shp_i, _n, rec = er.import_as_sms(F["shp"], "lo", str(tmp_path / "imp"), {"min_yield": 5.0, "product": "wheat"},
                                      crop="wheat", log=lambda m: None, fmt=er.import_format(None, {"kind": "export"}))
    RS = rec["resolved"]
    S = {"method": "sms3sigma", "tag": "lo", "sms3sigma": {"min_yield": 5.0}, "machines": {"harmonise": False},
         "sms_import": rec, "test_weight_lb_bu": RS["test_weight_lb_bu"],
         "moisture": {"standard_pct": RS["dry_moisture_pct"]},
         "scale_ticket": _ticket(100000.0, "lb") if ticket is None else ticket,
         "aoi": {"file": F["boundary"], "buffer_m": float(sms.DEFAULTS["clip_tolerance_m"]), "clip_output": True}}
    R = er.clean(shp_i, str(tmp_path / "out"), S, log=lambda m: None, source=source)
    return R, rec, gpd.read_file(F["shp"]), F


def test_the_grain_the_import_left_out_is_in_the_total_L_is_built_on(tmp_path):
    """The readings the import left out below its minimum still carry grain the scale weighed: computed again from
    the file of every reading with the import's own settings, inside the field of interest, on the basis of the
    monitor total, they are in the monitor total L is built on (L compares all the grain the monitor logged there
    with all the grain weighed); the record names them and gives L of the processed readings alone."""
    import geopandas as gpd
    from engine import sms_import as si
    R, rec, g0, F = _left_out_case(tmp_path)
    L = R["level"]
    lo = L["import_left_out"]
    assert rec["left_out"]["below the min. yield volume"] > 0
    # by hand: the import's dry yield (wet mass / 60 one-sided to 13.5 %) below 5, inside the boundary + 1 cm
    M = g0["Moisture__"].to_numpy(float)
    wet_bu = g0["Yld_Mass_W"].to_numpy(float) / 60.0
    dry = wet_bu * np.minimum(1.0, (100 - M) / 86.5)
    utm = g0.estimate_utm_crs()
    poly = gpd.read_file(F["boundary"]).to_crs(utm).geometry.union_all().buffer(0.01)
    ins = g0.geometry.to_crs(utm).within(poly).to_numpy()
    low = dry < 5.0
    area = g0["Distance_f"].to_numpy(float) * g0["Swth_Wdth_"].to_numpy(float) / FT2_PER_AC
    st = lo["steps"]["below the min. yield volume"]
    assert st["n"] == int((low & ins).sum()) and lo["n_outside_field"] == int((low & ~ins).sum())
    assert st["bu"] == pytest.approx(float((wet_bu * area)[low & ins].sum()), rel=1e-9)
    assert st["n"] > 0 and lo["basis"] == "wet" and lo["below_min_bu"] == pytest.approx(st["bu"])
    proc = L["processed_set_integral_bu"]
    assert lo["share_of_monitor_pct"] == pytest.approx(100 * st["bu"] / proc)
    assert lo["included_in_L"] is True and L["import_left_out_in_total_bu"] == pytest.approx(st["bu"])
    assert L["export_total_bu"] == pytest.approx(proc + st["bu"])
    assert L["factor"] == pytest.approx(L["ticket_compared_bu"] / (proc + st["bu"]))
    assert lo["factor_with_below_min"] == pytest.approx(L["factor"])
    assert lo["factor_processed_only"] == pytest.approx(L["ticket_compared_bu"] / proc)
    assert f"plus the {st['n']:,} readings Import as SMS left out below its minimum" in L["source"]
    # the leveled total (the processed readings and the left-out ones x L) is the weight: no level warning
    assert L["leveled_export_integral_bu"] == pytest.approx(L["ticket_compared_bu"], rel=1e-9)
    assert not any(w.startswith("the leveled export integrates to") for w in R["warnings"])
    # the same computation as the import itself: its counts per step
    lo_all = si.left_out_readings(rec["all_readings"], dict(rec["resolved"], family=rec["family"],
                                                             sources=rec["sources"]))
    assert dict(lo_all["step"].value_counts()) == rec["left_out"]
    txt = cr._left_out_text(L)
    assert "below the min. yield volume" in txt and "they are in the monitor total L is built on" in txt
    assert "carry the rest" in R["yield_column_note"] and "in the monitor total L is built on" in R["yield_column_note"]


def test_left_out_grain_in_L_is_what_the_texts_give_for_the_processed_readings(tmp_path):
    """A dry weight with the grain of the readings the import left out below its minimum in the monitor total L is
    built on: the leveled column over the processed readings alone sums below the weight by that grain, and every
    text says so with that figure (never '<comparison column> x L sums to the weight compared', never the shrink as
    the reason); the PDF's monitor total names its two parts; the areas stay the processed set's; the rule and the
    card warning say what L is built on."""
    T_bu = 2500.0
    src = {"format": "cnh_cn1", "label": "synthetic card", "totals": {"wet_lb": 1.04e5}, "sms_summary": {"wet_lb": 1e5}}
    R, rec, g0, F = _left_out_case(tmp_path, ticket=_ticket(T_bu, "bu", "dry"), source=src, low_every=10)
    L = R["level"]
    lo = L["import_left_out"]
    assert lo["included_in_L"] and lo["share_of_monitor_pct"] > 0.05 and L["comparison_basis"].startswith("dry")
    tick = L["ticket_compared_bu"]
    gap, pp = L["yld_level_vs_ticket_pct"], L["leveled_processed_vs_ticket_pct"]
    assert pp == pytest.approx(100 * (L["leveled_processed_integral_bu"] / tick - 1))
    assert L["leveled_processed_integral_bu"] + L["import_left_out_leveled_bu"] == pytest.approx(tick, rel=1e-9)
    assert gap == pytest.approx(pp, abs=1e-6) and gap < -0.05      # the dry weight levels the column compared
    assert L["import_left_out_leveled_bu"] == pytest.approx(lo["below_min_bu"] * L["factor"], rel=1e-9)
    n_lo = lo["steps"]["below the min. yield volume"]["n"]
    for t in (R["yield_column_note"], cr._difm_column(R)[1], er.difm_note(R)):
        assert "sums to the weight compared" not in t and "shrinks" not in t, t
        assert f"{gap:+.2f} %" in t and "left out below its minimum" in t, t
    assert f"the {n_lo:,} readings Import as SMS left out below its minimum" in R["yield_column_note"]
    # the PDF's level paragraph: the monitor total and its two parts, the areas of each
    txt = cr._level_text(R)
    assert "all processed points" not in txt
    assert f"{L['processed_set_integral_bu']:,.2f} bu over {L['export_area_ac']:,.2f} ac" in txt
    assert f"{L['import_left_out_in_total_bu']:,.2f} bu over {L['import_left_out_area_ac']:,.2f} ac" in txt
    assert L["import_left_out_area_ac"] == pytest.approx(lo["below_min_area_ac"]) and lo["below_min_area_ac"] > 0
    assert L["area_swept_ac"] == L["export_area_ac"] == L["export_integral_area_ac"]
    # the processed set's swept area, as the SMS 3-sigma record gives it (the left-out readings' acres apart)
    assert L["export_area_ac"] == pytest.approx(R["sms3sigma"]["area_swept_ac"], rel=1e-12)
    assert "plus the readings Import as SMS left out below its minimum" in L["rule"]
    assert "with the readings the import left out below its minimum" in L["rule"]
    w = [x for x in R["warnings"] if "card's own Summary" in x]
    assert len(w) == 1 and f"with the {n_lo:,} readings Import as SMS left out below its minimum" in w[0]
    assert f"{L['import_left_out_in_total_bu']:,.0f} bu of readings the import left out" in er.level_caption(R)
