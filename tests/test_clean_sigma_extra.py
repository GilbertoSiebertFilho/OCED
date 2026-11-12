# -*- coding: utf-8 -*-
"""The SMS 3-sigma sequence, second set (synthetic data only): the filter order of a plain settings dict, S0 with no
minimum still removes negative yields, S0 takes the minimum of the file's own import record, the lateral-bias
measurement has bounded memory, far-apart readings without a boundary are reported, the SD drop has two decimals.

    python -m pytest -q tests/test_clean_sigma_extra.py
"""
from __future__ import annotations

import os
import re
import sys
import tracemalloc

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import sms3sigma as sms  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import make_field  # noqa: E402
from tests.synthetic_combines import make_two_combines  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("one_extra")))


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    return make_two_combines(str(tmp_path_factory.mktemp("two_extra")))


def _clean(shp, sset=None, source=None, **extra):
    S = yc.merge_settings({"method": "sms3sigma", "machines": {"harmonise": False}, "sms3sigma": dict(sset or {}),
                           **extra})
    C, _ = yc.resolve_columns(list(pyogrio.read_info(shp)["fields"]), S)
    _g0, g, _gx, _gy, R, _diag = yc.clean(shp, S, C, log=lambda m: None, source=source)
    return R, g


def test_filter_order_of_a_settings_dict_is_the_engine_default():
    """A cleaning RECORD without the key ran speed first (the method before the setting existed); a plain SETTINGS
    dict without it runs this engine's default, as merge_settings fills it in."""
    assert sms.filter_order_of({"group_by": "auto"}) == sms.DEFAULTS["filter_order"] == "moisture_speed"
    assert sms.filter_order_of({}) == "moisture_speed" and sms.filter_order_of(None) == "moisture_speed"
    assert sms.filter_order_of({"settings": {"group_by": "auto"}}) == "speed_moisture"
    assert sms.filter_order_of({"steps": [], "grouping": {}}) == "speed_moisture"
    assert sms.filter_order_of({"filter_order": "speed_moisture"}) == "speed_moisture"
    assert sms.filter_order_of({"settings": {"filter_order": "moisture_speed"}}) == "moisture_speed"
    assert yc.merge_settings({})["sms3sigma"]["filter_order"] == sms.filter_order_of({"group_by": "auto"})


def test_s0_with_no_minimum_still_removes_negative_yields(field, tmp_path):
    """min_yield 0 or None means no minimum, never that a negative dry yield is kept."""
    df = pyogrio.read_dataframe(field["shp"])
    neg = np.arange(10, 40)
    df.loc[neg, "Yld_Vol_Dr"] = -3.0
    shp = str(tmp_path / "negative.shp")
    df.to_file(shp, engine="pyogrio")
    for my in (0, None):
        R, g = _clean(shp, {"min_yield": my})
        s0 = R["cascade"][0]
        assert s0["removed"] == len(neg) and "negative dry yield" in s0["criterion"]
        assert (g.loc[g["Rem_By"] == "S0", "Yld_Vol_Dr"] < 0).all()
    R5, _ = _clean(shp)
    low = int((df["Yld_Vol_Dr"] < 5).sum())
    assert R5["cascade"][0]["removed"] == low                  # the default minimum takes them with the low ones


def test_s0_takes_the_minimum_of_the_files_import(field):
    """settings['sms_import'] (the record of the file's Import as SMS) makes S0 use the import's minimum: the
    import already left out what was below it, so S0 may not apply another one (the step-3 box of 5 bu/ac)."""
    low = int((field["df"]["Yld_Vol_Dr"] < 5).sum())
    assert low > 0
    R0, _ = _clean(field["shp"], {"min_yield": 5.0}, sms_import={"resolved": {"min_yield": 0.0, "max_yield": 300.0}})
    assert R0["cascade"][0]["removed"] == 0
    assert R0["sms3sigma"]["min_yield"] == {"value": None, "source": "the file's Import as SMS"}
    assert any("minimum yield is the one of the file's Import as SMS" in n for n in R0["notes"])
    assert R0["sms_import"]["resolved"]["min_yield"] == 0.0
    R10, _ = _clean(field["shp"], sms_import={"resolved": {"min_yield": 10.0}})
    assert R10["cascade"][0]["removed"] == int((field["df"]["Yld_Vol_Dr"] < 10).sum())
    assert "below 10 bu/ac" in R10["cascade"][0]["criterion"] and "Import as SMS" in R10["cascade"][0]["criterion"]
    # without a record: the caller's minimum, as before
    R5, _ = _clean(field["shp"])
    assert R5["cascade"][0]["removed"] == low and R5["sms3sigma"]["min_yield"]["source"] == "sms3sigma.min_yield"
    with pytest.raises(ValueError, match="sms_import"):
        _clean(field["shp"], sms_import="5 bu/ac")


def test_lateral_bias_memory_is_bounded():
    """6,000 readings on one spot (a frozen GNSS fix) asked every pair (n^2: gigabytes); now k nearest per reading."""
    rng = np.random.default_rng(3)
    n = 6000
    x, y = rng.normal(0, 0.01, n), rng.normal(0, 0.01, n)
    h, w = rng.uniform(0, 360, n), np.full(n, 30.0)
    tracemalloc.start()
    r = sms.lateral_bias(x, y, h, w)
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert r is None and peak < 150e6


@pytest.mark.parametrize("bias", [-1.7, 0.8])
def test_lateral_bias_unchanged_on_back_and_forth_passes(bias):
    """The k-nearest search finds the same abeam neighbours as every pair did: the bias of passes in alternate
    directions, exactly, and no reading truncated."""
    ft = 0.3048
    xs, ys, hs = [], [], []
    for p in range(12):
        east = p % 2 == 0
        x = np.arange(250) * 1.8
        xs.append(x if east else x[::-1])
        ys.append(np.full(250, p * 30.0 * ft + (-1.0 if east else 1.0) * bias * ft))
        hs.append(np.full(250, 90.0 if east else 270.0))
    lb = sms.lateral_bias(np.concatenate(xs), np.concatenate(ys), np.concatenate(hs), np.full(3000, 30.0))
    assert lb is not None and abs(lb["bias_ft"] - bias) < 0.01 and lb["n_truncated"] == 0


def test_far_apart_readings_without_a_boundary_are_reported(field, tmp_path):
    """A second block of readings 2 km away and no boundary to clip them: a warning says they all enter the
    statistics; with the boundary (S1) there is nothing to say."""
    df = pyogrio.read_dataframe(field["shp"])
    far = df.iloc[:400].copy()
    far["geometry"] = far.geometry.translate(xoff=2000.0 / 69_000.0)
    import pandas as pd
    two = pd.concat([df, far], ignore_index=True)
    two["Obj__Id"] = np.arange(1, len(two) + 1)
    shp = str(tmp_path / "two_places.shp")
    two.to_file(shp, engine="pyogrio")
    R, _ = _clean(shp, {"swath": False, "min_yield": 0})
    w = [x for x in R["warnings"] if "groups more than 500 m apart" in x]
    assert len(w) == 1 and "400 readings" in w[0]
    Rb, _ = _clean(field["shp"], {"swath": False},
                   aoi={"file": field["boundary"], "buffer_m": 0.01, "clip_output": True})
    assert not any("groups more than 500 m apart" in x for x in Rb["warnings"])


def test_sd_drop_has_two_decimals(field):
    R, _ = _clean(field["shp"])
    crit = next(r["criterion"] for r in R["cascade"] if r["filter"] == "S5a")
    assert re.search(r"\d+\.\d\d % drop", crit)


def test_harvest_sessions_do_not_depend_on_the_decode_report(two):
    """A decoded John Deere file (Src_Fmt jd_jdl, times in UTC) opened again without its decode report: the same
    Harv_Day / Session and session table as with it (every evening crosses the UTC midnight: in UTC days each
    evening would be two sessions)."""
    R1, g1 = _clean(two["shp"], source=two["source"])
    R2, g2 = _clean(two["shp"], source=None)
    assert (g1["Session"].astype(str).to_numpy() == g2["Session"].astype(str).to_numpy()).all()
    assert (g1["Harv_Day"].astype(str).to_numpy() == g2["Harv_Day"].astype(str).to_numpy()).all()
    assert R1["sessions"]["n_sessions"] == R2["sessions"]["n_sessions"] == 4
