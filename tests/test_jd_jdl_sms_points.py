# -*- coding: utf-8 -*-
"""The points the John Deere Gen4 decoder makes as Ag Leader SMS does (engine/formats/jd_jdl.py, points="sms"), on
synthetic log data built in memory: a combine driving north at 1.5 m/s with a 13.716 m header of four sections,
header end points and GNSS at 5 Hz, mass flow and moisture at 1 Hz.

    python -m pytest -q tests/test_jd_jdl_sms_points.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import jd_jdl as J  # noqa: E402

LAT0, LON0 = 52.0, -114.0
T0 = 1_788_000_000_000            # ms UTC
SPEED = 1.5                       # m/s, north
FLOW_MGS = 9_000_000.0            # 9 kg/s
MOIST_PPM = 145_000.0             # 14.5 %
HALF = 13.716 / 2
LB_PER_KG = 2.20462262185


def _sections():
    w = 13.716 / 4
    return pd.DataFrame({"id": [1, 2, 3, 4], "width_m": [w] * 4, "y_m": [-1.5 * w, -0.5 * w, 0.5 * w, 1.5 * w],
                         "cws_id": [7] * 4, "cws_idx": [0, 1, 2, 3], "grp": [0] * 4})


def _file(n=26, t_first=T0, carried=False, t0=None, on_from=None, sections=True, guid="g-1", size=1000,
          flow_until=None, width_12001=None):
    """One synthetic log file: n header samples at 5 Hz from t_first. carried: the header / GNSS records carry the
    previous file's last value in (block start t0). on_from: the sections switch on at that time (off before);
    None = on all the time. sections=False: no section-control states at all."""
    t = t_first + 200 * np.arange(n, dtype=np.int64)
    y = SPEED * (t - T0) / 1000.0
    lat, lon_c = J._local_ll(np.zeros(n), y, LAT0, LON0)
    _, lon1 = J._local_ll(np.full(n, -HALF), y, LAT0, LON0)
    _, lon2 = J._local_ll(np.full(n, HALF), y, LAT0, LON0)
    ends = pd.DataFrame({"t_ms": t, "lat1": lat, "lon1": lon1, "lat2": lat, "lon2": lon2})
    gnss = pd.DataFrame({"t_ms": t, "lat": lat, "lon": lon_c, "alt_m": np.full(n, 1000.0)})
    ft = np.arange(t_first, (flow_until or int(t[-1])) + 1, 1000, dtype=np.int64)
    samples = {(J.DDI_FLOW, "mg1sec-1"): [ft, np.full(len(ft), FLOW_MGS)],
               (J.DDI_MOIST, "ppm"): [ft, np.full(len(ft), MOIST_PPM)]}
    if width_12001 is not None:
        samples[(J.DDI_WIDTH, "m")] = [ft, np.full(len(ft), width_12001)]
    cws = {}
    if sections:
        if on_from is None:
            cws = {0: (np.array([t_first - 5000], np.int64), np.ones((1, 4), np.uint8))}
        else:
            cws = {0: (np.array([t_first - 5000, on_from], np.int64), np.array([[0] * 4, [1] * 4], np.uint8))}
    meta = J.FileMeta(path=f"{guid}.jdl", guid=guid, ref_ms=int(t_first), vin="SYNTH000000000001",
                      sections=_sections(), size=size)
    fd = J.FileData(meta=meta, samples=samples, gnss=gnss, ends=ends, cws=cws,
                    t0_ms=int(t0 if t0 is not None else t_first))
    if carried:
        y0 = SPEED * (int(t0) - T0) / 1000.0
        la, lo = J._local_ll(np.array([0.0]), np.array([y0]), LAT0, LON0)
        fd.ends_carry = (float(la[0]), float(lo[0]), float(la[0]), float(lo[0]))
        fd.gnss_carry = (float(la[0]), float(lo[0]), int(t0))
    return fd


def test_groups_five_samples_per_point_and_the_first_sample_lasts_one_second():
    t = T0 + 200 * np.arange(26, dtype=np.int64)
    first, last, dur = J._sms_groups(t, T0, carried=False)
    assert first.tolist() == [0, 5, 10, 15, 20, 25]
    assert last.tolist() == [4, 9, 14, 19, 24, 25]
    # the first point: its first sample lasts SMS_CARRY_S (1 s) + 4 intervals; then one second per point
    assert dur.tolist() == pytest.approx([1.8, 1.0, 1.0, 1.0, 1.0, 0.2])


def test_groups_carried_file_starts_at_the_block_start_and_a_gap_closes_the_point():
    # a file that carries the previous one in: its block starts 250 ms before its first sample
    t = T0 + 200 * np.arange(10, dtype=np.int64)
    first, last, dur = J._sms_groups(t, T0 - 250, carried=True)
    assert first[0] == 0 and last[0] == 3                  # 0.25 + 3 x 0.2 = 0.85 s fits, the 5th sample does not
    assert dur[0] == pytest.approx(1.0 + 0.25 + 0.6)       # from one second before the block start
    # a gap of 3 s after sample 4 closes the point before it: the next point's Duration covers the gap
    t2 = np.r_[t[:5], t[5:] + 3000]
    f2, l2, d2 = J._sms_groups(t2, T0, carried=False)
    assert l2[0] == 4 and f2[1] == 5
    assert d2[1] == pytest.approx((int(t2[9]) - int(t2[4])) / 1000.0)


def test_file_points_area_mass_and_moisture():
    fd = _file()
    p, info = J._sms_file_points(fd, LAT0, LON0)
    assert not info["no_section_states"]
    assert len(p) == 6 and (p.reason == "").all()
    assert p.width_m.tolist() == pytest.approx([13.716] * 6)
    # distance: the antenna's own 5 Hz steps (0.3 m); the first sample of a file without a GNSS carry adds nothing
    assert p.dist_m.tolist() == pytest.approx([1.2, 1.5, 1.5, 1.5, 1.5, 0.3], abs=1e-6)
    assert p.flow_mgs.tolist() == pytest.approx([FLOW_MGS] * 6)
    assert p.moist.tolist() == pytest.approx([14.5] * 6)
    # wet mass = flow x Duration: 6 points cover 1.8 + 4 x 1.0 + 0.2 = 6.0 s
    wet_lb = float((p.flow_mgs / 1e6 * LB_PER_KG * p.dur_s).sum())
    assert wet_lb == pytest.approx(FLOW_MGS / 1e6 * LB_PER_KG * 6.0)
    # the point sits at its last sample, in the middle of the header
    assert p.lat.iloc[1] == pytest.approx(fd.ends.lat1.iloc[9], abs=1e-9)
    assert p.lon.iloc[1] == pytest.approx(LON0, abs=1e-9)


def test_file_points_header_not_working_counts_as_zero_flow():
    # the sections switch on at 2.35 s: samples 10 and 11 (2.0 and 2.2 s) are off, 12-14 on (on 100 ms after)
    fd = _file(on_from=T0 + 2350)
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert p.reason.tolist()[:2] == ["header_up", "header_up"]
    third = p.iloc[2]                                      # samples 10-14: two off, three on, 0.3 m each
    assert third.reason == "" and third.width_m == pytest.approx(13.716)
    assert third.flow_mgs == pytest.approx(0.6 * FLOW_MGS)
    assert third.moist == pytest.approx(0.6 * 14.5)


def test_file_points_carried_file_first_point():
    fd = _file(n=10, carried=True, t0=T0 - 250)
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert p.dur_s.iloc[0] == pytest.approx(1.85)
    # the GNSS carry gives the first sample its step: 0.25 s x 1.5 m/s
    assert p.dist_m.iloc[0] == pytest.approx(0.375 + 3 * 0.3, abs=1e-6)


def test_last_point_runs_on_to_the_next_flow_sample():
    # the flow channel has a sample 1 s after the last header sample (5.0 s) and no GNSS fix comes before it
    fd = _file(flow_until=T0 + 6000)
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert p.dur_s.iloc[-1] == pytest.approx(0.2 + 1.0)
    p0, _ = J._sms_file_points(_file(), LAT0, LON0)        # no flow sample after it: the point keeps its 0.2 s
    assert p0.dur_s.iloc[-1] == pytest.approx(0.2)


def test_file_without_section_states_uses_the_logged_width():
    # a file of a header with sections defined but no section-control states logged (a short log can hold none):
    # the width is DDI 12001, and the point position is the middle of the header bar
    fd = _file(n=6, sections=False, width_12001=13.716)
    p, info = J._sms_file_points(fd, LAT0, LON0)
    assert info["no_section_states"]
    assert p.width_m.tolist() == pytest.approx([13.716, 13.716])
    assert p.lon.iloc[0] == pytest.approx(LON0, abs=1e-9)
    fd0 = _file(n=3, sections=False)                      # no width channel either: header up
    p0, _ = J._sms_file_points(fd0, LAT0, LON0)
    assert (p0.reason == "header_up").all()


def test_whole_header_element_is_not_a_section():
    secs = pd.DataFrame({"id": range(61), "width_m": [0.15] * 60 + [9.0], "y_m": [0.0] * 61,
                         "cws_id": [1] * 61, "cws_idx": list(range(61)), "grp": [0] * 61})
    meta = J.FileMeta(path="x.jdl", sections=secs)
    assert len(J._sms_sections(meta)) == 60
    meta4 = J.FileMeta(path="y.jdl", sections=_sections())
    assert len(J._sms_sections(meta4)) == 4


def test_unit_points_reads_one_copy_of_a_log_and_files_in_time_order():
    a = _file(n=26, guid="same", size=1000)
    a_short = _file(n=11, guid="same", size=400)           # an earlier, shorter copy of the same log
    b = _file(n=26, t_first=T0 + 60_000, guid="other", size=1000)
    d, info = J._sms_points([a_short, b, a], a.meta)
    assert any("shorter cop" in w for w in info["warnings"])
    assert len(d) == 12                                    # 6 points of each log, the short copy left out
    assert np.all(np.diff(d.t_ms.values) > 0)


def test_points_option_is_checked(tmp_path):
    with pytest.raises(J.JdlError):
        J.decode_detailed(str(tmp_path), points="every_flow_sample", log=lambda m: None)
