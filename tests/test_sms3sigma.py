# -*- coding: utf-8 -*-
"""The SMS 3-sigma sequence on synthetic data (tests/synthetic.py): the order of the two filters and the ids that
follow it, one group per combine whatever travels with the file, readings without a value, the minimum S0 is given,
and the coverage raster of Optimize Swath Widths (narrowing, far-apart blocks of readings).

    python -m pytest -q tests/test_sms3sigma.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import sms3sigma as sms  # noqa: E402
from engine.clean import sms_swath  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.synthetic_combines import make_two_combines  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("one")))


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    return make_two_combines(str(tmp_path_factory.mktemp("two")))


def _clean(shp, sset=None, source=None):
    """(R, g) of the cleaning proper, no files written."""
    S = yc.merge_settings({"method": "sms3sigma", "machines": {"harmonise": False}, "sms3sigma": dict(sset or {})})
    C, _ = yc.resolve_columns(list(pyogrio.read_info(shp)["fields"]), S)
    _g0, g, _gx, _gy, R, _diag = yc.clean(shp, S, C, log=lambda m: None, source=source)
    return R, g


def _limits(R):
    return {(s["group"], s["step"]): (s["attribute"], s["lo"], s["hi"]) for s in R["sms3sigma"]["steps"]}


def test_default_order_is_moisture_then_speed(field):
    assert sms.DEFAULTS["filter_order"] == "moisture_speed"
    assert sms.STEP_INFO["S3"]["attribute"] == "moisture" and sms.STEP_INFO["S4"]["attribute"] == "speed"
    assert [g[0] for g in sms.GROUPS][2:4] == ["Moisture (S3)", "Speed (S4)"]
    R, _g = _clean(field["shp"])
    rows = R["cascade"]
    assert [r["filter"] for r in rows][:6] == ["S0", "S1", "S2", "S3", "S4", "S5a"]
    assert [r["attribute"] for r in rows][:6] == [None, None, None, "moisture", "speed", "dry yield"]
    assert rows[3]["name"].startswith("Moisture") and rows[4]["name"].startswith("Speed")
    L = _limits(R)
    assert L[("field", "S3")] == ("moisture", 10.08, 18.18)
    assert L[("field", "S4")] == ("speed", 2.60, 6.53)
    st = {s["step"]: s for s in R["sms3sigma"]["steps"]}
    assert st["S4"]["n_before"] == st["S3"]["n_after"] == rows[3]["remaining"]      # S4 runs on what S3 left
    M = R["sms3sigma"]
    assert M["filter_order"] == "moisture_speed" and M["method_revision"] == sms.METHOD_REVISION
    assert M["step_attributes"] == {"S3": "moisture", "S4": "speed", "S5": "dry yield"}


def test_old_order_stays_reachable(field):
    """filter_order speed_moisture is the earlier order of the SMS sequence: the same numbers the
    engine gave before the order became a setting (speed 2.61-6.52, then moisture 10.06-18.20)."""
    R, _g = _clean(field["shp"], {"filter_order": "speed_moisture"})
    rows = R["cascade"]
    assert [r["attribute"] for r in rows][3:5] == ["speed", "moisture"]
    assert rows[3]["name"].startswith("Speed") and rows[3]["group"] == "Speed (S3)"
    L = _limits(R)
    assert L[("field", "S3")] == ("speed", 2.61, 6.52)
    assert L[("field", "S4")] == ("moisture", 10.06, 18.20)
    assert (rows[3]["removed"], rows[4]["removed"]) == (57, 59)
    assert sms.step_groups("speed_moisture")[2:4] == [("Speed (S3)", ["S3"]), ("Moisture (S4)", ["S4"])]
    # a cleaning record made before the setting existed ran speed first
    assert sms.filter_order_of({"settings": {"group_by": "auto"}}) == "speed_moisture"
    assert sms.filter_order_of(R["sms3sigma"]) == "speed_moisture"
    with pytest.raises(ValueError, match="filter_order"):
        _clean(field["shp"], {"filter_order": "yield_first"})


def test_auto_is_one_group_per_combine_with_or_without_the_decode_report(two):
    """Two combines, two evenings each, times in UTC crossing the UTC midnight: 'auto' gives one mean and SD per
    combine, and the same groups, limits and kept readings whether the decoder report (source) comes with the file."""
    R1, g1 = _clean(two["shp"], source=two["source"])
    R2, g2 = _clean(two["shp"], source=None)
    for R in (R1, R2):
        G = R["sms3sigma"]["grouping"]
        assert (G["requested"], G["mode"], G["n_groups"], G["n_machines"]) == ("auto", "machine", 2, 2)
        assert sorted(G["groups"]) == ["COMBINE-A", "COMBINE-B"]
        assert "per combine" in G["rule"]
    assert _limits(R1) == _limits(R2)
    assert (g1["Keep"].to_numpy() == g2["Keep"].to_numpy()).all()
    L = _limits(R1)
    assert L[("COMBINE-A", "S3")] == ("moisture", 10.25, 17.99) and L[("COMBINE-B", "S3")] == ("moisture", 12.64, 19.59)
    assert L[("COMBINE-A", "S4")] == ("speed", 2.59, 6.54) and L[("COMBINE-B", "S4")] == ("speed", 4.23, 6.82)
    # the limits are those of the combine's own readings: mean +/- 3 SD (ddof 0), rounded half up to 2 decimals
    df = two["df"]
    a = df.loc[df["Machine"] == "COMBINE-A", "Moisture__"].dropna().to_numpy(float)
    assert L[("COMBINE-A", "S3")][1:] == (sms.round_half_up(a.mean() - 3 * a.std(), 2),
                                          sms.round_half_up(a.mean() + 3 * a.std(), 2))


def test_task_groups_do_not_depend_on_the_decode_report(two):
    """group_by 'task' stays as an explicit choice: combine x local day, the same four tasks without the report
    (the records are in UTC: taken in UTC days each evening would be cut in two, six groups)."""
    R1, g1 = _clean(two["shp"], {"group_by": "task"}, source=two["source"])
    R2, g2 = _clean(two["shp"], {"group_by": "task"}, source=None)
    for R in (R1, R2):
        G = R["sms3sigma"]["grouping"]
        assert (G["mode"], G["n_groups"]) == ("task", 4)
    assert _limits(R1) == _limits(R2) and (g1["Keep"].to_numpy() == g2["Keep"].to_numpy()).all()
    Rf, _ = _clean(two["shp"], {"group_by": "field"})
    assert Rf["sms3sigma"]["grouping"]["n_groups"] == 1


def test_unknown_combines_are_one_group_with_a_warning(two, tmp_path):
    """No machine column and dataset names that do not tell the combines apart: never task by task; one group and
    a warning that says what to do."""
    df = pyogrio.read_dataframe(two["shp"])
    df = df.drop(columns=["Machine", "Src_Fmt"])
    df["Dataset"] = np.where(df["Time"].astype(str) < "2026-09-15 12", "TaskName 9/14/2026 (GreenStar 4 Monitor)",
                             "TaskName 9/15/2026 (GreenStar 4 Monitor)")
    shp = str(tmp_path / "no_machine.shp")
    df.to_file(shp, engine="pyogrio")
    R, _g = _clean(shp)
    G = R["sms3sigma"]["grouping"]
    assert (G["mode"], G["n_groups"], G["n_machines"], G["n_tasks"]) == ("field", 1, None, 2)
    assert any("does not tell the combines apart" in w for w in R["warnings"])
    Rt, _ = _clean(shp, {"group_by": "task"})
    assert Rt["sms3sigma"]["grouping"]["n_groups"] == 2


def test_a_reading_without_a_value_is_not_removed_by_that_filter(two):
    """300 readings of COMBINE-A have no moisture and 200 of COMBINE-B no speed: the 3-sigma steps keep them, count
    them (no_value) and warn; what a step removes is what lies outside its limits."""
    R, g = _clean(two["shp"])
    df = two["df"]
    steps = {(s["group"], s["step"]): s for s in R["sms3sigma"]["steps"]}
    sA, sB = steps[("COMBINE-A", "S3")], steps[("COMBINE-B", "S4")]
    assert sA["no_value"] == 300 and steps[("COMBINE-B", "S3")]["no_value"] == 0
    assert 190 <= sB["no_value"] <= 200                       # a few were removed by the moisture step before
    m = df.loc[df["Machine"] == "COMBINE-A", "Moisture__"].to_numpy(float)
    assert sA["removed"] == int(((m < sA["lo"]) | (m > sA["hi"])).sum())
    kept = g["Keep"].to_numpy() == 1
    assert int((kept & g["Moisture__"].isna().to_numpy()).sum()) > 280       # kept unless another step took them
    assert int((kept & g["Speed_mph_"].isna().to_numpy()).sum()) > 180
    w = [x for x in R["warnings"] if "have no" in x]
    assert any("S3" in x and "no moisture value" in x for x in w)
    assert any("S4" in x and "no speed value" in x for x in w)


def test_s0_takes_the_minimum_it_is_given(field):
    """The file has readings of 2 bu/ac: S0 removes them with the default 5 bu/ac, and only then. A caller whose
    import already applied another minimum (or none) passes it: 0 or None = no check on the yield in S0."""
    low = int((field["df"]["Yld_Vol_Dr"] < 5).sum())
    assert low > 0
    R5, _ = _clean(field["shp"])
    assert R5["cascade"][0]["removed"] == low and "below 5 bu/ac" in R5["cascade"][0]["criterion"]
    for my in (0, 0.0, None):
        R0, _ = _clean(field["shp"], {"min_yield": my})
        assert R0["cascade"][0]["removed"] == 0 and "below" not in R0["cascade"][0]["criterion"]
    R2, _ = _clean(field["shp"], {"min_yield": 1.0})
    assert R2["cascade"][0]["removed"] == 0 and "below 1 bu/ac" in R2["cascade"][0]["criterion"]


def _two_passes(gap_ft=20.0, n=60, width=30.0, step=6.0, x0=0.0, y0=0.0):
    """Two parallel passes heading north, the second `gap_ft` east of the first: x, y (m), heading, distance, width."""
    ft = sms_swath.FT
    ys = np.arange(1, n + 1) * step * ft
    x = np.r_[np.zeros(n), np.full(n, gap_ft * ft)] + x0
    y = np.r_[ys, ys] + y0
    return x, y, np.zeros(2 * n), np.full(2 * n, step), np.full(2 * n, width)


def test_swath_narrows_the_overlapping_pass_and_keeps_the_bushels():
    """A 30 ft header on passes 20 ft apart: the second pass is narrowed by the 10 ft already cut, its per-area
    values scaled by 30 / 20, so width x distance x scale (the grain) is unchanged."""
    x, y, hdg, d, w = _two_passes()
    r = sms_swath.optimize_swath(x, y, hdg, d, w, np.arange(len(x)))
    first, second = slice(0, 60), slice(62, 120)             # the first readings of a pass have no full neighbour
    assert not r["removed"].any()
    assert np.allclose(r["width_ft_new"][first], 30.0)
    assert np.allclose(r["width_ft_new"][second], 20.0) and np.allclose(r["scale"][second], 1.5)
    assert np.allclose(r["shift_ft"][second], 5.0)             # moved to the centre of the kept strip (to the right)
    assert np.allclose((r["width_ft_new"] * r["dist_ft_new"] * r["scale"])[second], 30.0 * 6.0)
    assert r["stats"]["n_narrowed"] >= 58 and r["stats"]["n_blocks"] == 1


def test_swath_far_blocks_get_their_own_raster():
    """A second block of readings 8 km away (the same field name logged elsewhere) would need one raster of
    billions of cells: each block gets its own, with the result of each block cleaned alone."""
    xa, ya, hdg, d, w = _two_passes()
    xb, yb, _h, _d, _w = _two_passes(x0=5600.0, y0=5700.0)
    x, y = np.r_[xa, xb], np.r_[ya, yb]
    H, D, W = np.r_[hdg, hdg], np.r_[d, d], np.r_[w, w]
    r = sms_swath.optimize_swath(x, y, H, D, W, np.arange(len(x)))
    assert r["stats"]["n_blocks"] == 2 and r["stats"]["block_sizes"] == [120, 120]
    assert r["stats"]["raster_cells"] < 1e7                    # not the 5.7 km x 5.7 km of the bounding box
    one = sms_swath.optimize_swath(xa, ya, hdg, d, w, np.arange(len(xa)))
    for k in ("width_ft_new", "dist_ft_new", "scale", "shift_ft", "covered_frac"):
        assert np.allclose(r[k][:120], one[k], equal_nan=True) and np.allclose(r[k][120:], one[k], equal_nan=True)
    assert r["stats"]["n_narrowed"] == 2 * one["stats"]["n_narrowed"]
    assert list(sms_swath.reading_blocks(x, y, 150.0)) == [0] * 120 + [1] * 120


def test_swath_each_set_alone():
    """Two passes cut by two combines: together the second is narrowed by the 10 ft the first already cut; each
    combine alone (one SMS instance per combine) keeps its full width."""
    x, y, hdg, d, w = _two_passes()
    lab = np.array(["A"] * 60 + ["B"] * 60, dtype=object)
    one = sms_swath.optimize_swath(x, y, hdg, d, w, np.arange(len(x)))
    each = sms_swath.optimize_swath_each(lab, x, y, hdg, d, w, np.arange(len(x)))
    assert one["stats"]["n_narrowed"] >= 58 and each["stats"]["n_narrowed"] == 0
    assert np.allclose(each["width_ft_new"], 30.0) and np.allclose(each["scale"], 1.0)
    assert each["stats"]["n_scopes"] == 2 and each["stats"]["scope_sizes"] == [60, 60]
    same = sms_swath.optimize_swath_each(np.array(["A"] * 120, dtype=object), x, y, hdg, d, w, np.arange(len(x)))
    assert np.allclose(same["width_ft_new"], one["width_ft_new"])
    assert same["stats"]["n_narrowed"] == one["stats"]["n_narrowed"]


def test_swath_scope_setting(two, tmp_path):
    """COMBINE-B moved onto the ground COMBINE-A cuts: over the whole operation (default) Optimize Swath Widths
    removes and narrows the overlapped readings; with swath_scope 'machine' each combine is tested against its own
    ground only and nothing overlaps."""
    df = pyogrio.read_dataframe(two["shp"])
    b = (df["Machine"] == "COMBINE-B").to_numpy()
    dlat = -12 * 9.0 / 111_320.0                       # twelve passes south: B on the passes of A
    df.loc[b, "geometry"] = df.loc[b, "geometry"].translate(yoff=dlat)
    shp = str(tmp_path / "overlapping.shp")
    df.to_file(shp, engine="pyogrio")
    R1, _ = _clean(shp)
    R2, _ = _clean(shp, {"swath_scope": "machine"})
    s1, s2 = R1["sms3sigma"]["swath"], R2["sms3sigma"]["swath"]
    assert s1["scope"] == "the whole operation" and s2["scope"] == "each combine alone"
    assert s1["n_removed"] + s1["n_narrowed"] > 1000
    assert s2["n_removed"] == 0 and s2["n_narrowed"] == 0
    assert "own ground" in next(r["criterion"] for r in R2["cascade"] if r["filter"] == "S2")
    with pytest.raises(ValueError, match="swath_scope"):
        _clean(shp, {"swath_scope": "task"})


def test_swath_refuses_one_block_too_large_to_hold():
    """Readings 100 m apart along 7 km x 7 km are one block: the step says what to do instead of asking the
    computer for gigabytes."""
    t = np.arange(0.0, 7000.0, 100.0)
    n = len(t)
    with pytest.raises(ValueError, match="give the field boundary"):
        sms_swath.optimize_swath(t, t, np.full(n, 45.0), np.full(n, 6.0), np.full(n, 30.0), np.arange(n))


def _back_and_forth(bias_ft, n_pass=10, width=30.0, n=300, step_m=2.0):
    """Passes `width` apart in alternate directions (east, west, ...), every point `bias_ft` to the right of travel:
    x, y (m), heading, width."""
    ft = sms_swath.FT
    xs, ys, hs = [], [], []
    for p in range(n_pass):
        east = p % 2 == 0
        x = np.arange(n) * step_m
        right_y = -1.0 if east else 1.0                   # the right of travel: south going east, north going west
        xs.append(x if east else x[::-1])
        ys.append(np.full(n, p * width * ft + right_y * bias_ft * ft))
        hs.append(np.full(n, 90.0 if east else 270.0))
    x, y, h = np.concatenate(xs), np.concatenate(ys), np.concatenate(hs)
    return x, y, h, np.full(len(x), width)


@pytest.mark.parametrize("bias", [-1.7, 0.0, 1.5])
def test_lateral_bias_is_measured_from_the_combines_own_passes(bias):
    x, y, h, w = _back_and_forth(bias)
    lb = sms.lateral_bias(x, y, h, w)
    assert lb is not None and abs(lb["bias_ft"] - bias) < 0.05
    assert abs(lb["left_ft"] - (30.0 + 2 * bias)) < 0.1 and abs(lb["right_ft"] - (30.0 - 2 * bias)) < 0.1
    assert sms.lateral_bias(x[:150], y[:150], h[:150], w[:150]) is None   # one pass: no opposite neighbours


def _shifted(field, tmp_path, bias_ft):
    """The synthetic field with every point moved bias_ft to the right of its travel."""
    df = pyogrio.read_dataframe(field["shp"])
    east = (df["Track_deg_"].astype(float) == 90.0).to_numpy()
    dlat = bias_ft * sms_swath.FT / 111_320.0
    df.loc[east, "geometry"] = df.loc[east, "geometry"].translate(yoff=-dlat)
    df.loc[~east, "geometry"] = df.loc[~east, "geometry"].translate(yoff=dlat)
    shp = str(tmp_path / f"shifted_{abs(bias_ft):g}.shp")
    df.to_file(shp, engine="pyogrio")
    return shp


def test_swath_bias_setting(field, tmp_path):
    """Points 1.8 ft to the left of the strip they cut: by default the cleaning measures it and warns (the swath
    step narrows every second pass); 'auto' moves them back first and the narrowing goes; the field as cut has no
    bias and no warning."""
    R0, _ = _clean(field["shp"])
    s0 = R0["sms3sigma"]["swath"]
    assert abs(s0["lateral_bias_ft"]["COMBINE-A"]) < 0.2 and not s0["lateral_bias_moved_ft"]
    assert not any("strip its header cut" in w for w in R0["warnings"])
    shp = _shifted(field, tmp_path, -1.8)
    R1, _ = _clean(shp)
    R2, _ = _clean(shp, {"swath_bias": "auto"})
    s1, s2 = R1["sms3sigma"]["swath"], R2["sms3sigma"]["swath"]
    assert abs(s1["lateral_bias_ft"]["COMBINE-A"] + 1.8) < 0.1 and not s1["lateral_bias_moved_ft"]
    assert any("sit 1.8" in w and "to the left" in w for w in R1["warnings"])
    assert abs(s2["lateral_bias_moved_ft"]["COMBINE-A"] + 1.8) < 0.1
    assert s1["n_narrowed"] > 1000 and s2["n_narrowed"] < s0["n_narrowed"] + 50
    R3, _ = _clean(shp, {"swath_bias": "off"})
    assert R3["sms3sigma"]["swath"]["lateral_bias_ft"] == {}
    assert R3["sms3sigma"]["swath"]["n_narrowed"] == s1["n_narrowed"]
    with pytest.raises(ValueError, match="swath_bias"):
        _clean(shp, {"swath_bias": "always"})
