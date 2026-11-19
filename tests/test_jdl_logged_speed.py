# -*- coding: utf-8 -*-
"""The speed and distance of a John Deere Gen4 point as SMS holds them (engine/formats/jd_jdl.py, points="sms"): the
GNSS records (type 1) log, besides the position, the receiver's own distance travelled per fix (mm; anchor 8 /
deltas 15) and its ground speed (mm/s; anchor 5 / deltas 21). SMS's Distance of a point is the sum of that distance
over the point's fixes - the fixes logged while the header record has a gap (a stop) included, the fixes after the
last header sample of their data block left out - and its flow and moisture are weighted by it. Its Speed: every
fix's speed goes to the header sample nearest in time, a sample reads the plain mean of what it gets, and a point the
mean of its samples weighted by their logged distance. Synthetic data only.

    python -m pytest -q tests/test_jdl_logged_speed.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import jd_jdl as J  # noqa: E402
from engine.formats.jd_jdl_write import _packed_zz  # noqa: E402
from tests.test_jd_jdl_sms_points import LAT0, LON0, SPEED, _file  # noqa: E402

MPH = 2.2369362920544


def _logged(fd, dist_mm, speed_mms, hdr_last=None):
    """Give the GNSS fixes of a synthetic file the logged distance and speed (and the last header sample of their
    data block: by default the file's last header sample, i.e. one block)."""
    g = fd.gnss
    g["dist_mm"] = np.asarray(dist_mm, float)
    g["speed_mms"] = np.asarray(speed_mms, float)
    g["blk_hdr_last"] = np.full(len(g), int(fd.ends.t_ms.max()) if hdr_last is None else 0, np.int64)
    if hdr_last is not None:
        g["blk_hdr_last"] = np.asarray(hdr_last, np.int64)
    return fd


def test_speed_is_the_logged_speed_weighted_by_the_logged_distance():
    fd = _file()                                        # 26 header samples and fixes at 5 Hz, 1.5 m/s north
    n = len(fd.gnss)
    rng = np.random.default_rng(7)
    dist = np.round(300 + rng.normal(0, 40, n))         # mm per fix (not the antenna's 0.3 m steps exactly)
    spd = np.round(1500 + rng.normal(0, 200, n))        # mm/s, varying inside a point
    p, _ = J._sms_file_points(_logged(fd, dist, spd), LAT0, LON0)
    first, last, _ = J._sms_groups(fd.ends.t_ms.values, fd.t0_ms, carried=False)
    want = [np.sum(dist[a:b + 1] * spd[a:b + 1]) / np.sum(dist[a:b + 1]) * 3.6 / 1000 for a, b in zip(first, last)]
    assert p.speed_kmh.tolist() == pytest.approx(want, rel=1e-12)
    # not the antenna's distance over the GNSS time (the rule before), not the plain mean
    old = [SPEED * 3.6] * len(want)
    assert max(abs(a - b) for a, b in zip(p.speed_kmh, old)) > 0.1
    plain = [np.mean(spd[a:b + 1]) * 3.6 / 1000 for a, b in zip(first, last)]
    assert max(abs(a - b) for a, b in zip(p.speed_kmh, plain)) > 1e-4
    # the distance is the logged distance of the point's fixes, not the antenna's steps
    want_d = [np.sum(dist[a:b + 1]) / 1000 for a, b in zip(first, last)]
    assert p.dist_m.tolist() == pytest.approx(want_d, abs=1e-9)
    assert p.dist_m.tolist() != pytest.approx([1.2, 1.5, 1.5, 1.5, 1.5, 0.3], abs=1e-3)


def test_flow_and_moisture_are_weighted_by_the_logged_distance():
    fd = _file()
    ft, fv = fd.samples[(J.DDI_FLOW, "mg1sec-1")]
    # flow samples half a second off the points, so that the flow changes inside every point
    fd.samples[(J.DDI_FLOW, "mg1sec-1")] = [ft - 500, 8_000_000.0 + 1_000_000.0 * np.arange(len(ft))]
    mt, mv = fd.samples[(J.DDI_MOIST, "ppm")]
    fd.samples[(J.DDI_MOIST, "ppm")] = [mt, 140_000.0 + 2_000.0 * np.arange(len(mt))]
    n = len(fd.gnss)
    dist = np.where(np.arange(n) % 5 == 4, 900.0, 100.0)    # the sample that reads the next flow sample weighs most
    p, _ = J._sms_file_points(_logged(fd, dist, np.full(n, 1500.0)), LAT0, LON0)
    t = fd.ends.t_ms.values
    first, last, _ = J._sms_groups(t, fd.t0_ms, carried=False)
    fl = J._held(fd, (J.DDI_FLOW, "mg1sec-1"), t)
    mo = J._held(fd, (J.DDI_MOIST, "ppm"), t) / 1e4
    want_f = [np.sum(fl[a:b + 1] * dist[a:b + 1]) / np.sum(dist[a:b + 1]) for a, b in zip(first, last)]
    want_m = [np.sum(mo[a:b + 1] * dist[a:b + 1]) / np.sum(dist[a:b + 1]) for a, b in zip(first, last)]
    assert p.flow_mgs.tolist() == pytest.approx(want_f, rel=1e-12)
    assert p.moist.tolist() == pytest.approx(want_m, rel=1e-12)
    plain = [np.mean(fl[a:b + 1]) for a, b in zip(first, last)]
    assert max(abs(x - y) for x, y in zip(p.flow_mgs, plain)) > 1000


def test_without_logged_fields_the_speed_is_as_before():
    fd = _file()
    p0, _ = J._sms_file_points(fd, LAT0, LON0)
    fd2 = _logged(_file(), np.full(26, np.nan), np.full(26, np.nan))
    p1, _ = J._sms_file_points(fd2, LAT0, LON0)
    assert p1.speed_kmh.tolist() == p0.speed_kmh.tolist()
    assert p1.dist_m.tolist() == p0.dist_m.tolist() == pytest.approx([1.2, 1.5, 1.5, 1.5, 1.5, 0.3], abs=1e-6)
    assert p0.speed_kmh.iloc[1] == pytest.approx(SPEED * 3.6)


def test_fixes_in_a_header_gap_count_and_fixes_after_the_blocks_last_header_sample_do_not():
    fd = _file(n=26)
    t = fd.ends.t_ms.values.copy()
    # the header record stops after sample 9 and resumes at sample 17 (a stop; the GNSS keeps logging), and the file's
    # last header sample is sample 24: fix 25 comes after it
    keep = np.r_[np.arange(10), np.arange(17, 25)]
    fd.ends = fd.ends.iloc[keep].reset_index(drop=True)
    n = len(fd.gnss)
    dist = np.full(n, 300.0)
    dist[10:17] = [20, 5, 0, 0, 7, 40, 90]
    dist[25] = 5000.0
    spd = np.full(n, 1500.0) + 10.0 * np.arange(n)
    spd[10:17] = [300, 60, 40, 40, 90, 400, 800]
    spd[25] = 9000.0
    # the data blocks: fixes 0-12 in a block whose last header sample is sample 9; fixes 13-25 in the next one
    hl = np.where(np.arange(n) <= 12, t[9], t[24])
    p, _ = J._sms_file_points(_logged(fd, dist, spd, hdr_last=hl), LAT0, LON0)
    assert p.t_ms.tolist() == [t[4], t[9], t[21], t[24]]           # samples 0-4, 5-9 | gap | 17-21, 22-24

    # speed: fixes 10-12 are nearer to sample 9, fix 13 lies exactly halfway (-> the earlier sample), fixes 14-16
    # are nearer to sample 17; fix 25 (after the file's last header sample) goes to none; no block rule
    speed_of = {9: np.arange(9, 14), 17: np.arange(14, 18)}
    # distance: sample 17 takes the gap's fixes 13-16 and its own; 10-12 come after sample 9 in their block
    dist_of = {17: np.arange(13, 18)}

    def point(samples):
        """km/h: per header sample the plain mean of its fixes' speed, weighted by the sample's logged distance"""
        sp = np.array([np.mean(spd[speed_of.get(k, [k])]) for k in samples])
        st = np.array([np.sum(dist[dist_of.get(k, [k])]) for k in samples])
        return np.sum(sp * st) / np.sum(st) * 3.6 / 1000

    before, after, end = np.arange(5, 10), np.arange(17, 22), np.arange(22, 25)
    assert p.speed_kmh.iloc[1] == pytest.approx(point(before), rel=1e-12)
    assert p.speed_kmh.iloc[2] == pytest.approx(point(after), rel=1e-12)
    assert p.speed_kmh.iloc[3] == pytest.approx(point(end), rel=1e-12)
    # not the rule that gives every gap fix to the sample after the gap
    old_before = np.sum(dist[before] * spd[before]) / np.sum(dist[before]) * 3.6 / 1000
    old_after = np.sum(dist[13:22] * spd[13:22]) / np.sum(dist[13:22]) * 3.6 / 1000
    assert abs(p.speed_kmh.iloc[1] - old_before) > 0.1 and abs(p.speed_kmh.iloc[2] - old_after) > 0.1
    # distance: the gap's fixes count with the sample after the gap, except 10-12 (after sample 9 in their block);
    # fix 25 (after its block's last header sample) counts nowhere
    assert p.dist_m.tolist() == pytest.approx([np.sum(dist[0:5]) / 1000, np.sum(dist[before]) / 1000,
                                               np.sum(dist[13:22]) / 1000, np.sum(dist[end]) / 1000], abs=1e-12)
    assert p.dur_s.iloc[2] == pytest.approx((t[21] - t[9]) / 1000.0)


def test_gnss_record_fields_are_read_as_anchored_delta_streams():
    def rec(anchored):
        out = [(10, 2, _packed_zz(np.array([200, 200, 200])))]
        if anchored:
            out += [(8, 1, 250.5), (5, 1, 1300.25)]
        out += [(15, 2, _packed_zz(np.array([10, -5, 3]))), (21, 2, _packed_zz(np.array([100, 0, -50])))]
        return out
    d, v = J._gnss_logged(rec(True), 3, absolute=False)
    assert d.tolist() == [260.5, 255.5, 258.5] and v.tolist() == [1400.25, 1400.25, 1350.25]
    d, v = J._gnss_logged(rec(False), 3, absolute=True)                 # a log session's first record: anchor 0
    assert d.tolist() == [10, 5, 8] and v.tolist() == [100, 100, 50]
    d, v = J._gnss_logged(rec(False), 3, absolute=False)                # deltas without their anchor: unknown
    assert np.isnan(d).all() and np.isnan(v).all()
    d, v = J._gnss_logged([(10, 2, _packed_zz(np.array([200])))], 1, absolute=False)   # a record without them
    assert np.isnan(d).all() and np.isnan(v).all()


def test_synthetic_card_without_logged_fields_decodes_as_before(tmp_path):
    from tests.synthetic_jdl import make_card
    card = make_card(str(tmp_path))
    fd = J.decode_file(card["files"][0])
    assert {"dist_mm", "speed_mms", "blk_hdr_last"} <= set(fd.gnss.columns)
    assert fd.gnss.dist_mm.isna().all() and fd.gnss.speed_mms.isna().all()
    # every fix knows the last header sample of its data block
    assert (fd.gnss.blk_hdr_last.values >= fd.gnss.t_ms.values - 30_000).all()
    df, rep = J.decode(card["root"], points="sms", log=lambda m: None)
    assert len(df) and np.isfinite(df.Speed_mph_.values).all()


def _warns(rep):
    return [w for w in rep["warnings"] if "logged distance or speed" in w]


def test_a_log_with_the_streams_in_part_of_its_fixes_is_named_in_the_warnings(tmp_path, monkeypatch):
    from tests.synthetic_jdl import make_card
    card = make_card(str(tmp_path), logged=True)
    df0, rep = J.decode(card["root"], points="sms", log=lambda m: None)
    assert not _warns(rep)                                   # every fix logs both: nothing to say
    # one GNSS record of the first file without the streams (the rest of the file has them)
    real, seen = J._gnss_logged, []

    def part(rec_fields, n, absolute):
        d, v = real(rec_fields, n, absolute)
        seen.append(n)
        return (np.full(n, np.nan), v) if len(seen) == 2 else (d, v)
    monkeypatch.setattr(J, "_gnss_logged", part)
    df1, rep = J.decode(card["root"], points="sms", log=lambda m: None)
    w = _warns(rep)
    assert len(w) == 1 and f"{seen[1]:,} GNSS fix(es) in 1 log file(s)" in w[0]
    _, rep = J.decode(card["root"], points="ops_center", log=lambda m: None)
    assert not _warns(rep)                                   # the Ops Center readings do not use them
    # what the warning names: the record's fixes add no distance
    assert df1.Distance_f.sum() < df0.Distance_f.sum()


def test_an_absolute_gnss_record_with_a_logged_anchor_is_named_in_the_warnings(tmp_path, monkeypatch):
    from tests.synthetic_jdl import make_card
    card = make_card(str(tmp_path), logged=True)
    real, k = J._stream, []

    def absolute(rec_fields, anchors, deltas, t_delta, bs):
        r = real(rec_fields, anchors, deltas, t_delta, bs)
        if anchors == (1, 2, 4) and isinstance(r, tuple) and not r[2] and any(a == 8 for a, _, _ in rec_fields):
            k.append(1)
            if len(k) == 1:                                  # one anchored record read as an absolute one
                return r[0], r[1], True
        return r
    monkeypatch.setattr(J, "_stream", absolute)
    _, rep = J.decode(card["root"], points="sms", log=lambda m: None)
    w = _warns(rep)
    assert len(w) == 1 and "1 GNSS record(s) with absolute positions" in w[0]
