# -*- coding: utf-8 -*-
"""The SMS 3-sigma sequence, second set (synthetic data only): the filter order of a plain settings dict, S0 with no
minimum still removes negative yields, S0 takes the minimum of the file's own import record, S2 removes the readings
logged with no swath width, the order S2 takes (a point file without a time per reading in its own row order; time
order; raw data and GreenStar 4 exports as before; swath_order 'file'), the lateral-bias
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


def test_s2_removes_the_readings_logged_with_no_swath_width(field, tmp_path):
    """A point file imported with no minimum brings readings logged with a swath width of 0 (no cut: header up,
    sections off) and no yield. S0 keeps them (no minimum); S2 removes them (a rectangle of no area), whatever their
    yield, and removes the same other readings as without them; with S2 off they stay."""
    df = pyogrio.read_dataframe(field["shp"])
    zero = np.arange(200, 260)
    df.loc[zero, "Swth_Wdth_"] = 0.0
    df.loc[zero[:50], ["Yld_Vol_Dr", "Yld_Vol_We", "Yld_Mass_W", "Yld_Mass_D"]] = 0.0
    shp = str(tmp_path / "no_width.shp")
    df.to_file(shp, engine="pyogrio")
    point_import = {"resolved": {"min_yield": 0.0, "max_yield": None}}
    R0, _ = _clean(field["shp"], sms_import=point_import)
    R, g = _clean(shp, sms_import=point_import)
    s0 = next(r for r in R["cascade"] if r["filter"] == "S0")
    s2 = next(r for r in R["cascade"] if r["filter"] == "S2")
    s2_0 = next(r for r in R0["cascade"] if r["filter"] == "S2")
    assert s0["removed"] == 0
    assert (g.loc[g["Swth_Wdth_"] == 0, "Rem_By"] == "S2").all() and int((g["Swth_Wdth_"] == 0).sum()) == len(zero)
    assert s2["removed"] == s2_0["removed"] + len(zero) and "no swath width (0) - removed" in s2["criterion"]
    sw = R["sms3sigma"]["swath"]
    assert sw["n_no_width"] == len(zero) and sw["removed_by_reason"][sms.NO_WIDTH_REASON] == len(zero)
    assert "no swath width" not in s2_0["criterion"] and "n_no_width" not in R0["sms3sigma"]["swath"]
    Roff, goff = _clean(shp, {"swath": False}, sms_import=point_import)
    assert next(r for r in Roff["cascade"] if r["filter"] == "S2")["removed"] == 0
    assert not (goff.loc[goff["Swth_Wdth_"] == 0, "Rem_By"] == "S2").any()


POINT_IMPORT = {"family": "point", "fmt": "point_export", "resolved": {"min_yield": 0.0, "max_yield": None}}
RAW_IMPORT = {"family": "cnh", "fmt": "cnh_cn1", "resolved": {"min_yield": 0.0, "max_yield": None}}


@pytest.fixture(scope="module")
def strips(tmp_path_factory):
    """Two blocks over the same ground: an undated dataset first in the file, a dated one after it; the same with a
    time per reading (the first block an hour later than the second); an SMS export of GreenStar 4 data (two dated
    datasets, the later date first in the file, Pass_Num, no time per reading)."""
    from tests.synthetic_strips import make_strips
    d = tmp_path_factory.mktemp("strips")
    return {"untimed": make_strips(str(d / "u"), "Strip U", "Strip D 9/14/2026"),
            "timed": make_strips(str(d / "t"), "Strip U", "Strip D 9/14/2026",
                                 times=("2026-09-14 14:00:00", "2026-09-14 13:00:00")),
            "gs4": make_strips(str(d / "g"), "TaskName 9/15/2026 (GreenStar 4 Monitor)",
                               "TaskName 9/14/2026 (GreenStar 4 Monitor)", pass_num=True, machine=False)}


def _s2_by_block(g, F):
    """Readings S2 removed in the first and the second block of the file (the block S2 took first keeps its own)."""
    b = F["block"][g["_row"].to_numpy()]
    s2 = g["Rem_By"].to_numpy() == "S2"
    return int((s2 & (b == 0)).sum()), int((s2 & (b == 1)).sum())


def test_point_import_is_the_family_or_the_format_of_the_import_record():
    assert sms.point_import(POINT_IMPORT) and sms.point_import({"fmt": "point_export"})
    assert sms.point_import({"family": "john_deere", "fmt": "jd_ops_center"})       # an Ops Center export
    assert not sms.point_import(RAW_IMPORT) and not sms.point_import({"fmt": "jd_jdl"})
    assert not sms.point_import(None) and not sms.point_import({"resolved": {"min_yield": 0.0}})


def test_s2_takes_an_untimed_point_file_in_its_row_order(strips):
    """A point file without a time per reading (its import record says family 'point'): S2 takes the readings in the
    file's own row order, as one block, so the undated dataset first in the file is cut first and the dated one after
    it is removed as fully overlapped. The table keeps the dataset order (the dated dataset first), only S2 changes;
    the record says the order and why, and the warning about several combines names the file's row order."""
    F = strips["untimed"]
    n_b = F["n"] // 2
    R, g = _clean(F["shp"], sms_import=POINT_IMPORT)
    assert _s2_by_block(g, F) == (0, n_b)
    sw = R["sms3sigma"]["swath"]
    assert sw["order_basis"] == sms.ORDER_FILE and sw["order_setting"] == "auto"
    assert "point file without a time per reading" in sw["order_reason"] and "swath_order" not in sw["order_reason"]
    assert sw["order"].startswith("the file's own row order, as one block")
    assert R["order"]["basis"] == "dataset+order" and g["Dataset"].iloc[0] == "Strip D 9/14/2026"
    assert yc.SEVERAL_FILE_ORDER in R["warnings"] and yc.SEVERAL_NO_TIME not in R["warnings"]
    assert R["sms3sigma"]["method_revision"] == sms.METHOD_REVISION >= sms.FILE_ORDER_REVISION == 4
    # the same file without a point import record: the datasets in the order of the dates in their names (unchanged)
    R0, g0 = _clean(F["shp"])
    assert _s2_by_block(g0, F) == (n_b, 0) and R0["sms3sigma"]["swath"]["order_basis"] == sms.ORDER_EXPORT
    assert yc.SEVERAL_NO_TIME in R0["warnings"] and yc.SEVERAL_FILE_ORDER not in R0["warnings"]


def test_s2_keeps_time_order_for_a_timed_point_file(strips):
    """A point file with a time per reading (an Operations Center export): S2 stays in time order, whatever the order
    of the rows: the block logged an hour earlier is cut first although it is second in the file."""
    F = strips["timed"]
    R, g = _clean(F["shp"], sms_import=POINT_IMPORT)
    assert _s2_by_block(g, F) == (F["n"] // 2, 0)
    sw = R["sms3sigma"]["swath"]
    assert sw["order_basis"] == sms.ORDER_TIME and sw["order"] == "time order across combines"
    assert sw["order_reason"] == "the file has a time per reading"
    assert not any("replaces the per-record time order" in w for w in R["warnings"])


def test_s2_order_of_raw_data_and_greenstar_4_exports_is_unchanged(strips):
    """Raw data (an import record of a card) and a file without an import record keep the order of 0.3.1: the
    datasets by the dates in their names; an SMS export of GreenStar 4 data imported as a point file keeps its logged
    files re-chained and in the order of their dates, exactly as without the point record."""
    F = strips["untimed"]
    R0, g0 = _clean(F["shp"])
    Rr, gr = _clean(F["shp"], sms_import=RAW_IMPORT)
    assert _s2_by_block(gr, F) == (F["n"] // 2, 0) and Rr["sms3sigma"]["swath"]["order_basis"] == sms.ORDER_EXPORT
    assert "not a point file" in Rr["sms3sigma"]["swath"]["order_reason"]
    for c in ("Keep", "Rem_By", "Wdth_Opt", "Swath_Scl", "Dist_Opt"):
        assert (gr[c].to_numpy() == g0[c].to_numpy()).all(), c
    G = strips["gs4"]
    Rp, gp = _clean(G["shp"], sms_import=POINT_IMPORT)
    Rn, gn = _clean(G["shp"])
    assert _s2_by_block(gp, G) == (G["n"] // 2, 0)               # 9/14 (second in the file) cut first
    sw = Rp["sms3sigma"]["swath"]
    assert sw["order_basis"] == sms.ORDER_CHAIN and "GreenStar 4" in sw["order_reason"]
    assert sw["order"] == Rn["sms3sigma"]["swath"]["order"]
    for c in ("Keep", "Rem_By", "Wdth_Opt", "Swath_Scl", "Dist_Opt"):
        assert (gp[c].to_numpy() == gn[c].to_numpy()).all(), c


def test_swath_order_file_is_the_files_row_order(strips):
    """swath_order 'file' set by the user wins: S2 takes the file's own row order for any file, over the dataset dates
    of a file without an import record, over a time per reading (with a warning) and over the re-chaining of a
    GreenStar 4 export."""
    F, T, G = strips["untimed"], strips["timed"], strips["gs4"]
    for D, kw in ((F, {}), (F, {"sms_import": RAW_IMPORT}), (T, {"sms_import": POINT_IMPORT}),
                  (G, {"sms_import": POINT_IMPORT}), (G, {})):
        R, g = _clean(D["shp"], {"swath_order": "file"}, **kw)
        assert _s2_by_block(g, D) == (0, D["n"] // 2)
        sw = R["sms3sigma"]["swath"]
        assert sw["order_basis"] == sms.ORDER_FILE and sw["order_reason"] == "set by swath_order 'file'"
        assert sw["order_setting"] == "file"
        replaced = [w for w in R["warnings"] if "swath_order 'file' replaces the per-record time order" in w]
        assert len(replaced) == (1 if D is T else 0)
    # 'chain' stays what it was: the file blocks re-chained, then the datasets in the order of their dates
    Rc, gc = _clean(G["shp"], {"swath_order": "chain"}, sms_import=POINT_IMPORT)
    assert _s2_by_block(gc, G) == (G["n"] // 2, 0) and Rc["sms3sigma"]["swath"]["order_basis"] == sms.ORDER_CHAIN


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
