# -*- coding: utf-8 -*-
"""How the John Deere Gen4 decoder (engine/formats/jd_jdl.py, points="sms") gives the mass flow (DDI 510) and the
moisture (DDI 6) to the header samples (type 2), and when it reads the section work states, on synthetic data only:

    every channel sample goes to the header sample NEAREST in time (a sample exactly halfway: the earlier one; a
    sample after the file's last header sample: none); a header sample reads the plain mean of what it gets (zeros
    included), holds the last sample given before it when it gets none, else the file's carry;
    the section states of a header sample are read at the middle to the next one (a change exactly halfway: the
    earlier sample's), SMS_SNAP_MS after the file's last header sample.

    python -m pytest -q tests/test_jdl_nearest_sample.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import jd_jdl as J  # noqa: E402
from tests.test_jd_jdl_sms_points import LAT0, LON0, T0, _file  # noqa: E402

KEY = (J.DDI_FLOW, "mg1sec-1")
KEY_M = (J.DDI_MOIST, "ppm")


def _fd(ts, vs, carry=None, key=KEY):
    meta = J.FileMeta(path="x.jdl", guid="x", ref_ms=0, vin="SYNTH000000000009")
    fd = J.FileData(meta=meta, samples={key: [np.asarray(ts, np.int64), np.asarray(vs, float)]} if len(ts) else {},
                    gnss=None, ends=None, cws={})
    if carry is not None:
        fd.carry[key] = float(carry)
    return fd


T = np.array([1000, 1200, 1400, 1600], np.int64)       # header samples at 5 Hz


def test_bounds_are_the_middles_and_the_last_sample_itself():
    assert J._sms_bounds(T).tolist() == [1100, 1300, 1500, 1600]
    assert J._sms_bounds(np.array([1000, 1201], np.int64)).tolist() == [1100, 1201]   # odd gap: floor
    assert J._sms_state_times(T).tolist() == [1100, 1300, 1500, 1600 + J.SMS_SNAP_MS]


def test_a_sample_exactly_halfway_goes_to_the_earlier_header_sample():
    v = J._held_nearest(_fd([1100], [5.0]), KEY, T)
    assert v[0] == 5.0                                   # 1100 is halfway between 1000 and 1200
    v = J._held_nearest(_fd([1101], [5.0]), KEY, T)
    assert np.isnan(v[0]) and v[1] == 5.0                # one ms later: the later sample's


def test_a_header_sample_reads_the_plain_mean_of_its_samples_zeros_included():
    # 1150 and 1250 both nearest to 1200; the 0 (a stop) counts
    v = J._held_nearest(_fd([1150, 1250, 1290], [6.0, 0.0, 3.0]), KEY, T)
    assert v[1] == 3.0                                   # (6 + 0 + 3) / 3
    v = J._held_nearest(_fd([990, 1010], [0.0, 4.0]), KEY, T)
    assert v[0] == 2.0                                   # before the first header sample: nearest is the first


def test_a_header_sample_without_samples_holds_the_last_one_given_before_it():
    v = J._held_nearest(_fd([1000, 1050, 1390], [2.0, 8.0, 7.0]), KEY, T)
    # 1000, 1050 -> header 0 (mean 5); nothing for 1200 -> holds 8 (the last sample header 0 got, not its mean);
    # 1390 -> header 2; nothing for 1600 -> holds 7
    assert v.tolist() == [5.0, 8.0, 7.0, 7.0]


def test_before_any_sample_the_carry_else_nan():
    v = J._held_nearest(_fd([1390], [7.0], carry=4.0), KEY, T)
    assert v.tolist() == [4.0, 4.0, 7.0, 7.0]
    v = J._held_nearest(_fd([1390], [7.0]), KEY, T)
    assert np.isnan(v[:2]).all() and v[2:].tolist() == [7.0, 7.0]
    v = J._held_nearest(_fd([], [], carry=3.0), KEY, T)
    assert v.tolist() == [3.0] * 4
    assert np.isnan(J._held_nearest(_fd([], []), KEY, T)).all()


def test_the_last_header_sample_takes_nothing_after_it():
    v = J._held_nearest(_fd([1500, 1600, 1601, 1700], [1.0, 3.0, 50.0, 60.0]), KEY, T)
    assert v[2] == 1.0                                   # 1500 is halfway 1400-1600: the earlier
    assert v[3] == 3.0                                   # 1601 and 1700 lie after the file's last header sample


def test_samples_out_of_order_are_read_in_time_order():
    v = J._held_nearest(_fd([1390, 1000, 1050], [7.0, 2.0, 8.0]), KEY, T)
    assert v.tolist() == [5.0, 8.0, 7.0, 7.0]


def test_moisture_follows_the_same_rule_in_the_file_points():
    fd = _file(n=26)
    t = fd.ends.t_ms.values.astype(np.int64)
    ft = np.array([t[0], t[0] + 1000, t[0] + 2000, t[0] + 3000, t[0] + 4000], np.int64)
    fd.samples[KEY_M] = [ft, np.array([100_000.0, 200_000.0, 100_000.0, 200_000.0, 100_000.0])]
    held = J._held_nearest(fd, KEY_M, t)
    # a header sample at a moisture sample's own time reads it; the ones between hold it
    assert held[0] == 100_000.0 and held[4] == 100_000.0 and held[5] == 200_000.0
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert np.isfinite(p.moist.values).all() and (p.moist.values > 0).all()


def test_flow_of_a_point_is_the_distance_weighted_mean_of_its_samples_nearest_rule():
    fd = _file(n=26)
    t = fd.ends.t_ms.values.astype(np.int64)
    # one flow sample 100 ms after every header sample: halfway -> it belongs to that header sample
    vals = np.arange(len(t), dtype=float) * 1000.0 + 1_000_000.0
    fd.samples[KEY] = [t + 100, vals]
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    first, last, _ = J._sms_groups(t, fd.t0_ms, carried=False)
    held = J._held_nearest(fd, KEY, t)
    assert np.allclose(held[:-1], vals[:-1]) and held[-1] == vals[-2]   # the last sample's flow lies after the file
    for k, (a, b) in enumerate(zip(first, last)):
        if k == 0:
            continue                                     # the first point weighs its first sample by its own step
        assert abs(p.flow_mgs.values[k] / held[a:b + 1].mean() - 1) < 1e-9   # equal steps: the plain mean


def _file_states(change_ms):
    """A file whose four sections switch on at change_ms (off before)."""
    return _file(n=26, on_from=change_ms)


def test_section_state_is_read_at_the_middle_to_the_next_header_sample():
    t0 = T0
    # a change 100 ms after header sample 10 (exactly halfway to sample 11): sample 10's
    fd = _file_states(t0 + 10 * 200 + 100)
    S = J._sms_state_times(fd.ends.t_ms.values.astype(np.int64))
    assert S[10] == t0 + 10 * 200 + 100
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    tt = fd.ends.t_ms.values.astype(np.int64)
    first, last, _ = J._sms_groups(tt, fd.t0_ms, carried=False)
    # the width of a point is that of its last sample's states
    expect = J._sms_state_times(tt)[last] >= t0 + 10 * 200 + 100
    assert ((p.width_m.values > 0) == expect).all()
    assert expect.any() and not expect.all()


def test_section_change_just_after_the_middle_belongs_to_the_next_sample():
    t0 = T0
    fd = _file_states(t0 + 10 * 200 + 101)
    tt = fd.ends.t_ms.values.astype(np.int64)
    first, last, _ = J._sms_groups(tt, fd.t0_ms, carried=False)
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    expect = J._sms_state_times(tt)[last] >= t0 + 10 * 200 + 101
    assert ((p.width_m.values > 0) == expect).all()
    # the earlier rule (t + 100 ms) would have put this change in sample 11 too, but one 50 ms after the middle of a
    # 1 s gap not: the middle decides
    gap = pd.concat([fd.ends.iloc[:13], fd.ends.iloc[13:].assign(t_ms=fd.ends.t_ms.values[13:] + 800)])
    fd.ends = gap.reset_index(drop=True)
    tt = fd.ends.t_ms.values.astype(np.int64)
    mid = int(tt[12] + (tt[13] - tt[12]) // 2)
    fd.cws = {0: (np.array([tt[0] - 5000, mid + 50], np.int64), np.array([[0] * 4, [1] * 4], np.uint8))}
    st = J._sms_state_times(tt)
    assert st[12] == mid and st[12] > tt[12] + J.SMS_SNAP_MS
    first, last, _ = J._sms_groups(tt, fd.t0_ms, carried=False)
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert ((p.width_m.values > 0) == (st[last] >= mid + 50)).all()


def test_last_header_sample_reads_the_states_snap_ms_after_it():
    fd = _file(n=26)
    tt = fd.ends.t_ms.values.astype(np.int64)
    fd.cws = {0: (np.array([tt[0] - 5000, tt[-1] + J.SMS_SNAP_MS], np.int64),
                  np.array([[1] * 4, [0] * 4], np.uint8))}
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert p.width_m.values[-1] == 0.0                   # switched off exactly SMS_SNAP_MS after the last sample
    fd.cws = {0: (np.array([tt[0] - 5000, tt[-1] + J.SMS_SNAP_MS + 1], np.int64),
                  np.array([[1] * 4, [0] * 4], np.uint8))}
    p, _ = J._sms_file_points(fd, LAT0, LON0)
    assert p.width_m.values[-1] > 0
