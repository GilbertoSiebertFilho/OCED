# -*- coding: utf-8 -*-
"""The John Deere Gen4 decoder (engine/formats/jd_jdl.py) end to end on a synthetic .jdl card (tests/synthetic_jdl.py):
what the second log file carries in, the SMS points of the whole card, the section layout of each reading's own file
in both points modes, the whole-header element, and the product SMS imports the logs with.

    python -m pytest -q tests/test_dec_jdl.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import common as C  # noqa: E402
from engine.formats import jd_jdl as J  # noqa: E402
from tests import synthetic_jdl as S  # noqa: E402

QUIET = lambda m: None  # noqa: E731
# another header profile for the first log file: six 1.5 m sections whose middle is 1.5 m left of the bar midpoint
OTHER = [(31 + k, 1.5, -5250.0 + 1500.0 * k) for k in range(6)]


def _card(folder, monkeypatch=None, first_layout=None):
    if first_layout is not None:
        orig = S.definitions

        def defs(guid, ref_ms, prev=None, nxt=None):
            if prev is not None:
                return orig(guid, ref_ms, prev=prev, nxt=nxt)
            keep = S.SECTIONS
            S.SECTIONS = first_layout
            try:
                return orig(guid, ref_ms, prev=prev, nxt=nxt)
            finally:
                S.SECTIONS = keep
        monkeypatch.setattr(S, "definitions", defs)
    return S.make_card(str(folder))


def test_the_second_file_carries_the_last_values_of_the_first(tmp_path):
    """decode_file: the first block of the second file starts at its file's block start (t0_ms), and the header, GNSS
    and channel records bring the first file's last values in (ends_carry, gnss_carry, carry); the first file has
    none (its records are absolute)."""
    card = _card(tmp_path)
    m1, m2 = sorted((J.read_meta(p) for p in card["files"]), key=lambda m: m.ref_ms)
    f1, f2 = J.decode_file(m1.path, m1), J.decode_file(m2.path, m2)
    assert f1.ends_carry is None and f1.gnss_carry is None and not f1.carry
    assert f1.t0_ms == S.REF_MS and f2.t0_ms == m2.ref_ms
    e = f1.ends.iloc[-1]
    assert f2.ends_carry == pytest.approx((e.lat1, e.lon1, e.lat2, e.lon2), abs=1e-9)
    g = f1.gnss.iloc[-1]
    assert f2.gnss_carry[:2] == pytest.approx((g.lat, g.lon), abs=1e-9)
    assert f2.gnss_carry[2] == f2.t0_ms                         # a carry without a time of its own: the block start
    flow = (J.DDI_FLOW, "mg1sec-1")
    assert f2.carry[flow] == pytest.approx(float(f1.samples[flow][1][-1]))
    assert f2.carry[(J.DDI_TW, "lb1bu-1")] == pytest.approx(60.0)
    assert f1.n_absolute > 0 and f2.n_absolute == 0


def test_decode_detailed_as_sms_on_a_synthetic_card(tmp_path):
    """points='sms' end to end: one point per ~1 s of 5 Hz header samples, read file by file; the points cover the two
    passes and not the header-up turn; the grain of the card is on the points (wet mass = flow x Duration)."""
    card = _card(tmp_path)
    df, rep = J.decode_detailed(card["root"], None, None, log=QUIET, points="sms")
    assert rep["points"] == "sms" and len(df) > 100
    assert not C.check_standard(df)
    assert df.Duration_s.between(0.15, 1.85).all() and abs(float(df.Duration_s.median()) - 1.0) < 1e-6
    assert np.allclose(df.Swth_Wdth_, 9.0 * C.FT_PER_M) and np.allclose(df.Y_Offset_f, 0.0)
    assert (rep["pre_step"]["header_up"] > 10) and set(df.Machine) == {S.VIN}
    d = rep["details"][0]
    assert d["n_sms_points"] >= len(df) and "n_flow_samples" not in d and d["files"] == 2
    area = df.Distance_f * df.Swth_Wdth_ / C.SQFT_PER_AC
    wet = float((df.Yld_Mass_W * area).sum())
    assert wet == pytest.approx(float((df.Yld_Mass_W * area).sum()))
    assert 0.9 < wet / (8.0 * 120 * C.LB_PER_KG) < 1.1        # 8 kg/s over the 120 s of harvest
    o, ro = J.decode_detailed(card["root"], None, None, log=QUIET, points="ops_center")
    assert ro["points"] == "ops_center" and "n_flow_samples" in ro["details"][0]


def _lateral(df):
    """Signed distance (m) of each reading from the synthetic track's centre line (east 0 m going north, 9 m south)."""
    east = (df.lon.values - S.LON0) * S.M_PER_DEG_LON
    north = np.cos(np.radians(df.Track_deg_.values)) > 0
    return np.where(north, east - 0.0, 9.0 - east)


def test_every_reading_takes_the_section_layout_of_its_own_file(tmp_path, monkeypatch):
    """A-0 / UPDATE 3: the first log file defines another header profile, whose sections centre 1.5 m left of the bar
    midpoint; the second file the real header. In both modes the readings of the second file sit on the bar
    midpoint (with the first file's layout for every reading they sat 1.5 m to one side), and the readings of the
    first file take the first file's layout; the report names the two layouts."""
    card = _card(tmp_path, monkeypatch, first_layout=OTHER)
    split = S.REF_MS + 70_000
    df, rep = J.decode_detailed(card["root"], None, None, log=QUIET, points="ops_center")
    assert any("2 section layouts" in w and "its own log file" in w for w in rep["warnings"])
    second, first = df[df.t_ms.values > split + 1000], df[df.t_ms.values < split - 1000]
    assert len(second) > 20 and len(first) > 20
    assert np.allclose(second.Y_Offset_f, 0.0) and np.allclose(_lateral(second), 0.0, atol=0.02)
    assert np.allclose(first.Y_Offset_f, -1.5 * C.FT_PER_M)                        # its own file's sections
    lay = rep["details"][0]["layouts"]
    assert sorted(x["files"] for x in lay) == [1, 1] and all(x["layout"].startswith("6 sections / 9.000 m") for x in lay)
    sm, rs = J.decode_detailed(card["root"], None, None, log=QUIET, points="sms")
    s2 = sm[sm.t_ms.values > split + 1000]
    assert len(s2) > 20 and np.allclose(_lateral(s2), 0.0, atol=0.02) and np.allclose(s2.Y_Offset_f, 0.0)


def test_a_layout_that_does_not_fit_the_bar_is_reported(tmp_path, monkeypatch):
    """The self-check: a layout of 12 m on a 9 m cutter bar (the end points logged with its readings) gets a warning."""
    wide = [(31 + k, 2.0, -5000.0 + 2000.0 * k) for k in range(6)]
    card = _card(tmp_path, monkeypatch, first_layout=wide)
    _, rep = J.decode_detailed(card["root"], None, None, log=QUIET, points="ops_center")
    assert any("does not match the cutter-bar length" in w and "12.000 m" in w for w in rep["warnings"])


def _secs(widths):
    w = np.asarray(widths, float)
    y = np.cumsum(w) - w / 2 - w.sum() / 2
    return pd.DataFrame({"id": range(len(w)), "width_m": w, "y_m": y, "cws_id": 1, "cws_idx": range(len(w)), "grp": 0})


def test_whole_header_element_only_when_it_is_the_sum_of_the_others():
    """V-gs4-0: a combine that lists its sections and also the whole header (their sum): the header element is left
    out; a header of two unequal sections keeps both; three sections where none is the sum of the others too."""
    whole = _secs([0.15] * 60 + [9.0])
    assert len(J._sms_sections(J.FileMeta(path="x", sections=whole))) == 60
    two = _secs([5.0, 4.0])
    assert len(J._sms_sections(J.FileMeta(path="x", sections=two))) == 2
    three = _secs([4.0, 3.0, 2.5])
    assert len(J._sms_sections(J.FileMeta(path="x", sections=three))) == 3
    near = _secs([6.0, 6.03, 12.0])                         # 12.0 vs 12.03: within 0.5 % -> the whole header
    assert len(J._sms_sections(J.FileMeta(path="x", sections=near))) == 2


def test_monitor_product_follows_what_sms_gives_the_crop(tmp_path):
    """UPDATE 4: SMS imports a .jdl with ITS values for the file's crop (wheat 60 lb/bu 13.5 %, barley 48 lb/bu 15.0 %),
    not the file's own; a crop without established values gives None (the product table applies); min 5, max
    10,000 bu/ac; the file's own numbers are kept under 'file'."""
    card = _card(tmp_path)
    _, rep = J.decode_detailed(card["root"], None, None, log=QUIET)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"]) == ("wheat", None, None)
    assert (mp["min_yield"], mp["max_yield"]) == (5.0, 10_000.0) and "21.1" in mp["source"]
    assert mp["file"]["crop_name"] == "Wheat (Test)" and mp["file"]["std_moisture_pct"] == 13.5
    assert rep["crop_name"] == "Wheat (Test)"
    hrs = C.jd_monitor_product("Wheat (Hard Red Spring)", "x")
    assert (hrs["crop"], hrs["test_weight_lb_bu"], hrs["dry_moisture_pct"]) == ("wheat", 60.0, 13.5)
    assert C.jd_monitor_product("Barley", "x")["dry_moisture_pct"] == 15.0
    assert C.jd_monitor_product(None, "x", crop_id=24)["test_weight_lb_bu"] == 60.0
    assert C.jd_monitor_product("Canola", "x")["crop"] == "canola"
    assert hrs["basis"] == "sms_crop" and C.jd_monitor_product("Canola", "x")["basis"] is None


def _closer_second_pass(monkeypatch, east_m=5.0):
    """The synthetic track with its second pass `east_m` east of the first instead of 9 m (the 9 m header overlaps)."""
    orig = S.track

    def near(*a, **k):
        tr = orig(*a, **k)
        s = (tr["et"] - (S.REF_MS + 500)) / 1000.0
        d = (east_m - 9.0) * np.where(s >= 80, 1.0, np.where(s >= 60, (s - 60) / 20.0, 0.0)) / S.M_PER_DEG_LON
        for k_ in ("lon1", "lon2", "glon"):
            tr[k_] = tr[k_] + d
        return tr
    monkeypatch.setattr(S, "track", near)


def test_decode_keeps_the_offset_of_the_sections_on_through_import_and_s2(tmp_path, monkeypatch):
    """VC-1: decode() returns Y_Offset_f with the SMS points (the point at the header reference, the centre of the
    sections on Y_Offset_f to the right of it, as SMS's own export of the logs), the decoded shapefile and the import
    as SMS keep it, and the SMS 3-sigma swath step moves the readings by it. The second pass runs 5 m beside the first
    with the 9 m header, full width for 20 s, then its outer (left, east) half only: its half-width readings cut
    ground nobody cut and keep their width; without the column they sat at the header midpoint, over the first pass,
    and S2 narrowed or removed them. ops_center points sit at the centre of the sections on already: no column."""
    import pyogrio
    from engine import run as er
    from engine.formats import detect
    _closer_second_pass(monkeypatch)
    card = S.make_card(str(tmp_path / "in"), state_times=(0.12, 60.1, 80.1, 100.1),
                       states=[[1] * 6, [0] * 6, [1] * 6, [1, 1, 1, 0, 0, 0]])
    df, _ = J.decode(card["root"], None, None, log=QUIET)
    assert list(df.columns) == C.STANDARD_NAMES + ["lon", "lat", "Y_Offset_f"]
    half = df.Swth_Wdth_.values < 9.0 * C.FT_PER_M - 0.1
    assert half.sum() > 20 and (~half).sum() > 20
    np.testing.assert_allclose(df.Y_Offset_f.values[half], -2.25 * C.FT_PER_M, atol=1e-6)    # left half: - 2.25 m
    np.testing.assert_allclose(df.Y_Offset_f.values[~half], 0.0, atol=1e-9)
    o, _ = J.decode(card["root"], None, None, log=QUIET, points="ops_center")
    assert "Y_Offset_f" not in o.columns
    # decoded file -> import as SMS -> SMS 3-sigma (S2 only): the column reaches S2
    wd = er.new_workdir(str(tmp_path / "ws"), "syn")
    cand = [c for c in er.open_input([card["root"]], wd, log=QUIET) if c.get("kind") == "raw"][0]
    dec = er.decode(cand, None, detect.default_options("jd_jdl"), wd, log=QUIET, tag="syn")
    d = pyogrio.read_dataframe(dec["shp"], read_geometry=False)
    assert list(d.columns[:len(C.STANDARD_NAMES) + 1]) == C.STANDARD_NAMES + ["Y_Offset_f"]
    np.testing.assert_allclose(d.Y_Offset_f.values, df.Y_Offset_f.values, atol=1e-9)
    imp, n, _ = er.import_as_sms(dec["shp"], "syn", os.path.join(wd, "imported"), {}, log=QUIET,
                                 monitor=dec["report"]["monitor_product"], fmt="jd_jdl")
    assert "Y_Offset_f" in pyogrio.read_info(imp)["fields"] and n == len(df)
    no = pyogrio.read_dataframe(imp)
    no["Y_Offset_f"] = 0.0                                       # the same file as the decoder gave it before
    imp0 = os.path.join(wd, "imported", "syn_no_offset.shp")
    no.to_file(imp0, engine="pyogrio")
    S3 = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
          "sms3sigma": {"speed": False, "moisture": False, "yield": False}}
    out = {}
    for k, p in (("offset", imp), ("none", imp0)):
        R = er.clean(p, os.path.join(wd, "clean", k), dict(S3, tag=k), log=QUIET, source=dec["source"])
        c = pyogrio.read_dataframe(R["files"]["difm_ready_shp"], read_geometry=False)
        hw = 4.5 * C.FT_PER_M
        out[k] = (R["sms3sigma"]["swath"], int((np.abs(pd.to_numeric(c.Swth_Wdth_) - hw) < 1e-6).sum()), c)
    sw, n_half_kept, c = out["offset"]
    assert sw["y_offset_column"] == "Y_Offset_f" and sw["n_offset_moved"] == int(half.sum())
    assert n_half_kept == int(half.sum())                        # every half-width reading kept at its width
    assert np.allclose(pd.to_numeric(c.Y_Offset_f), 0.0)         # SMS writes 0 once it moved the readings
    assert out["none"][1] < n_half_kept - 10                     # at the midpoint: narrowed / removed over pass 1
