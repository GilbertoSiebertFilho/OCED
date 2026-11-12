# -*- coding: utf-8 -*-
"""The Case IH / New Holland card decoder (engine/formats/cnh_cn1.py) on a synthetic card written record by record:
what a reading's time and distance are, the flow on the curve segment of the raw count, the stream join across a
counter restart, the Summary read from the card's task totals, and the app on such a card (open, extract, the Summary).

    python -m pytest -q tests/test_cnh_cn1.py
"""
from __future__ import annotations

import os
import struct
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import cnh_cn1 as cn  # noqa: E402
from engine.formats.common import DecodeOptions, FT_PER_M, LB_PER_KG, SQFT_PER_AC  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
OPTS = DecodeOptions(crop="wheat", test_weight_lb_bu=60.0, std_moisture_pct=13.5, shrink="one_sided")
LINEAR = [1000 * (k + 1) for k in range(11)]             # flow = 10 lb/s per 1000 raw counts
BENT = [900, 1400, 1900, 2450, 3000, 3600, 4250, 4900, 5550, 6150, 6700]   # made up: a curve that is not a line
STAMP = (56, 7, 1, 12, 0, 0)                             # 2026-07-01 12:00:00 on the display clock


def _record(payload: bytes, rid: bytes = b"", parent: bytes = b"", when=STAMP, rtype: int = 2) -> bytes:
    """One CNH1 record: 33-byte header (magic, payload length, type, id, parent id, time) + payload."""
    return (cn.MAGIC + struct.pack("<I", len(payload)) + b"\0\0" + bytes([rtype]) + rid.ljust(8, b"\0")[:8]
            + parent.ljust(8, b"\0")[:8] + bytes(when) + payload)


def _tso(name: str, n_log: int, area_m2: float, vehicle: str = "SYN00001") -> bytes:
    p = bytearray(199)
    p[0:len(name)] = name.encode()
    p[19:25] = bytes(STAMP)
    p[33:43] = b"Grain Harv"
    p[52] = 48
    p[53:53 + len(vehicle)] = vehicle.encode()
    struct.pack_into("<hh", p, 159, 52, -113)
    struct.pack_into("<I", p, 163, n_log)
    struct.pack_into("<I", p, cn.TSO_AREA, int(round(area_m2 * 100)))
    return _record(bytes(p))


def _tsh(curve, seconds=(), counts=(), kg: int = 0, moisture_sum: int = 0, offset_byte: int = 100, comp: int = 75,
         scale_kg: float = 0.0) -> bytes:
    p = bytearray(209)
    struct.pack_into("<11H", p, 5, *curve)
    struct.pack_into("<H", p, 27, comp)
    struct.pack_into(f"<{cn.BINS}H", p, 29, *(list(seconds) + [0] * cn.BINS)[:cn.BINS])
    struct.pack_into(f"<{cn.BINS}I", p, 49, *(list(counts) + [0] * cn.BINS)[:cn.BINS])
    struct.pack_into("<I", p, 89, int(round(scale_kg * 10)))
    p[95] = offset_byte
    struct.pack_into("<II", p, 96, kg, moisture_sum)
    return _record(bytes(p))


def _tlo(counter: int, k: int, dt_tenths: int, dist_mm: int, logging: int = 1, width_mm: int = 10000) -> bytes:
    """A .tlo record at the k-th position of a pass heading north (1 m apart), header ends 5 m either side."""
    lat = 1_000_000 + 900 * k                                  # x1e-8 degrees above the task origin
    p = bytearray(cn.TLO_LEN)
    p[0], p[1] = logging, dt_tenths
    struct.pack_into("<HH", p, 2, dist_mm, width_mm)
    struct.pack_into("<ii", p, 6, lat, 2_000_000)
    struct.pack_into("<i", p, 14, 900_000)
    p[18] = 1
    struct.pack_into("<i", p, 19, 43_200_000 + 1000 * k)
    struct.pack_into("<iiii", p, 25, lat, 2_000_000 - 7300, lat, 2_000_000 + 7300)
    sec = STAMP[5] + k
    return _record(bytes(p), struct.pack("<I", counter), when=STAMP[:4] + (sec // 60, sec % 60))


def _tlh(counter: int, raw_count: int, moisture_tenths: int = 140) -> bytes:
    p = bytearray(cn.TLH_LEN)
    struct.pack_into("<H", p, 1, raw_count)
    p[5] = moisture_tenths
    return _record(bytes(p), struct.pack("<I", counter))


def _card(root, tasks: dict) -> str:
    """A card folder with one field; tasks = {task id: {"tso", "tsh", "tlo" (optional), "tlh" (optional)}}."""
    card = os.path.join(str(root), "SYNTH001.cn1")
    fld = os.path.join(card, "shared", "FARM0001.fmd", "FIELD001.fld")
    os.makedirs(fld)
    with open(os.path.join(card, "index.vy1"), "wb") as f:
        f.write(_record(b"synthetic display"))
    with open(os.path.join(card, "shared", "FARM0001.fmd", "FIELD001.fls"), "wb") as f:
        f.write(_record(b"Synthetic field\0", b"FIELD001", b"FARM0001"))
    for task, parts in tasks.items():
        for ext, data in parts.items():
            with open(os.path.join(fld, f"{task}.{ext}"), "wb") as f:
                f.write(data)
    return str(root)


def _crop_table(root, vehicle_folder: str = "SYN00", test_weight: float = 60.0, std_moisture: float = 13.5):
    """COMBINES/<folder>/<folder>.ycs: 147 crops, each with this test weight and standard moisture."""
    d = os.path.join(root, "SYNTH001.cn1", "COMBINES", vehicle_folder)
    os.makedirs(d)
    p = bytearray(cn.YCS_LEN)
    struct.pack_into("<H", p, 2, int(round(test_weight * 10)))
    p[4] = p[6] = int(round(std_moisture * 10))
    with open(os.path.join(d, vehicle_folder + ".ycs"), "wb") as f:
        f.write(b"".join(_record(bytes(p), struct.pack("<I", k)) for k in range(147)))


def _one_task(root, tlo_records, tlh_records, curve=LINEAR, **tsh):
    return _card(root, {"TASK0001": {"tso": _tso("26/07/01-12:00:00", len(tlo_records), 10_000.0),
                                     "tsh": _tsh(curve, **tsh), "tlo": b"".join(tlo_records),
                                     "tlh": b"".join(tlh_records)}})


def _decode(root, **kw):
    units = cn.list_units(root)
    return cn.decode(root, [u.id for u in units], OPTS, log=lambda m: None, **kw)


def test_reading_time_and_distance_are_the_records_own(tmp_path):
    """SMS: Duration_s = the interval byte, Distance_f = the logged distance, mass = flow x Duration_s; a record
    without time has no mass and is not a reading. 'period' = one logging period (1 s) per record."""
    dt = [10, 20, 10, 0, 5, 10]                               # tenths of a second
    dist = [1000, 2000, 1000, 800, 500, 1000]                 # mm: 1 m/s wherever there is time
    root = _one_task(tmp_path, [_tlo(i + 1, i, dt[i], dist[i]) for i in range(6)], [_tlh(i + 1, 2500) for i in range(6)])
    df, rep = _decode(root)
    assert len(df) == 5 and rep["pre_step"] == {"interval byte 0 (no time: no mass, no speed)": 1}
    assert df.Duration_s.tolist() == pytest.approx([1.0, 2.0, 1.0, 0.5, 1.0])
    assert df.Distance_f.tolist() == pytest.approx([d / 1000 * FT_PER_M for d in (1000, 2000, 1000, 500, 1000)])
    assert df.Speed_mph_.tolist() == pytest.approx([2.2369362920544] * 5)
    area = df.Distance_f * df.Swth_Wdth_ / SQFT_PER_AC
    assert (df.Yld_Mass_W * area).tolist() == pytest.approx([25.0, 50.0, 25.0, 12.5, 25.0])     # 25 lb/s x Duration_s
    assert rep["calibration"]["record_time"] == "sms"
    dp, rp = _decode(root, time_basis="period")
    assert dp.Duration_s.tolist() == pytest.approx([1.0] * 5)
    assert dp.Distance_f.tolist() == pytest.approx([FT_PER_M] * 5)
    ap = dp.Distance_f * dp.Swth_Wdth_ / SQFT_PER_AC
    assert (dp.Yld_Mass_W * ap).tolist() == pytest.approx([25.0] * 5)
    assert dp.Yld_Vol_Dr.tolist() == pytest.approx(df.Yld_Vol_Dr.tolist())                       # the same yields
    with pytest.raises(ValueError):
        _decode(root, time_basis="byte")


def test_readings_longer_than_their_records_are_reported(tmp_path):
    """Interval bytes that add up to more time than one logging period per reading: a warning names the excess."""
    root = _one_task(tmp_path, [_tlo(i + 1, i, 20 if i % 2 else 10, 1000) for i in range(10)],
                     [_tlh(i + 1, 2500) for i in range(10)])
    df, rep = _decode(root)
    assert df.Duration_s.sum() == pytest.approx(15.0)
    assert any("50.0 % more time" in w and "5 readings" in w for w in rep["warnings"])
    assert not any("more time" in w for w in _decode(root, time_basis="period")[1]["warnings"])


def test_flow_on_the_curve_segment_of_the_raw_count():
    """A raw count just above a curve point whose moisture-compensated count falls below it is read on the UPPER
    segment's line (SMS), not on the segment of the compensated count."""
    curve = np.array(BENT, float)
    u = 2.010 * (1 + 0.0075 * (14.0 - 16.0))                  # 1.97985: below point 2, raw count above it
    flow, neg = cn.flow_lb_s([2010.0], [16.0], curve, 75)
    assert neg == 0
    assert flow[0] == pytest.approx((1900 + (u - 2) * (2450 - 1900) - 1000) / 100)
    assert flow[0] != pytest.approx((1400 + (u - 1) * (1900 - 1400) - 1000) / 100, abs=1e-4)
    flow, _ = cn.flow_lb_s([1500.0, 150.0], [14.0, 14.0], curve, 75)
    assert flow.tolist() == pytest.approx([(1400 + 0.5 * 500 - 1000) / 100, 0.0])               # below the zero -> 0


def test_records_after_a_counter_restart_are_read(tmp_path):
    """The display restarted twice and went back to counter 3: every run is read, each .tlo record with the .tlh
    record of the same run (the .tlh lost its last record before the first restart)."""
    tlo_ctr = [1, 2, 3, 4, 5, 3, 4, 3, 4, 5, 6]
    tlh_ctr = [1, 2, 3, 4, 3, 4, 3, 4, 5, 6]
    raw = [1100, 1200, 1300, 1400, 2300, 2400, 3300, 3400, 3500, 3600]
    root = _one_task(tmp_path, [_tlo(c, i, 10, 1000) for i, c in enumerate(tlo_ctr)],
                     [_tlh(c, raw[i]) for i, c in enumerate(tlh_ctr)])
    assert cn.stream_runs(tlo_ctr).tolist() == [0, 0, 0, 0, 0, 1, 1, 2, 2, 2, 2]
    df, rep = _decode(root)
    assert len(df) == 10 and rep["pre_step"] == {"no .tlh record for the .tlo counter": 1}
    area = df.Distance_f * df.Swth_Wdth_ / SQFT_PER_AC
    assert (df.Yld_Mass_W * area).tolist() == pytest.approx([v / 100 for v in raw])              # flow = count / 100
    assert any("goes back 2 time(s)" in w and "6 records" in w for w in rep["warnings"])


def test_streams_that_restart_differently_fall_back_to_the_first_record(tmp_path):
    root = _one_task(tmp_path, [_tlo(c, i, 10, 1000) for i, c in enumerate([1, 2, 3, 2, 3, 4])],
                     [_tlh(c, 2000 + 100 * c) for c in (1, 2, 3, 4)])
    df, rep = _decode(root)
    assert len(df) == 4
    assert any("cannot be paired" in w for w in rep["warnings"])


def test_summary_from_the_card_totals(tmp_path):
    """The Summary of a task = its totals on the card: the area counter, the average moisture (sensor offset added)
    and the weight of the calibration bins on the curve; a task without its log is listed and summed, without
    readings."""
    bins = dict(seconds=[0, 100, 200], counts=[0, 150_000, 500_000], kg=5000, moisture_sum=70_000, offset_byte=110)
    root = _card(tmp_path, {
        "TASK0001": {"tso": _tso("26/07/01-12:00:00", 4, 10_000.0), "tsh": _tsh(LINEAR, **bins),
                     "tlo": b"".join(_tlo(i + 1, i, 10, 1000) for i in range(4)),
                     "tlh": b"".join(_tlh(i + 1, 2500) for i in range(4))},
        "TASK0002": {"tso": _tso("#26/07/02-09:30:00", 300, 20_000.0),
                     "tsh": _tsh(BENT, seconds=[0, 0, 300], counts=[0, 0, 750_000], kg=1500, moisture_sum=18_000,
                                 scale_kg=1600.0)}})
    units = cn.list_units(root)
    assert [u.n_records for u in units] == [4]                  # a task without its log is not a unit
    only = cn.totals_only_tasks(root)
    assert [t["logged_records"] for t in only] == [300] and "totals only" in only[0]["label"]
    assert cn.totals_only_tasks(root, [units[0].id]) == only     # same field and harvest year
    df, rep = cn.decode(root, [u.id for u in units], OPTS, log=lambda m: None, totals_only="field")
    assert len(df) == 4 and set(df.Dataset) == {"TASK0001 26/07/01-12:00:00"}
    one, two = rep["sms_summary"]["datasets"]
    k = 1 + 0.0075 * (14.0 - 15.0)                             # average moisture 70,000 / 5,000 + 1.0 = 15.0 %
    assert one["area_ac"] == pytest.approx(10_000.0 / 4046.8564224)
    assert one["moisture_pct"] == pytest.approx(15.0)
    assert one["wet_lb"] == pytest.approx(100 * 15.0 * k + 200 * 25.0 * k)                       # 10 lb/s per 1000 counts
    assert one["dry_bu"] == pytest.approx(one["wet_lb"] / 60.0 * (100 - 15.0) / (100 - 13.5))
    assert one["bu_ac"] == pytest.approx(one["dry_bu"] / one["area_ac"])
    assert one["display_wet_lb"] == pytest.approx(5000 * LB_PER_KG)
    assert (one["has_log"], one["decoded_readings"], one["logged_records"]) == (True, 4, 4)
    u2 = 2.5 * (1 + 0.0075 * (14.0 - 12.0))                    # moisture 18,000 / 1,500 = 12.0 %, no offset
    assert two["wet_lb"] == pytest.approx(300 * (1900 + (u2 - 2) * 550 - 1000) / 100)
    assert two["dry_bu"] == pytest.approx(two["wet_lb"] / 60.0)                                  # drier than the standard
    assert two["scale_wet_lb"] == pytest.approx(1600 * LB_PER_KG)
    assert (two["has_log"], two["decoded_readings"], two["logged_records"]) == (False, 0, 300)
    tot = rep["sms_summary"]["total"]
    assert tot["area_ac"] == pytest.approx(30_000.0 / 4046.8564224)
    assert tot["wet_lb"] == pytest.approx(one["wet_lb"] + two["wet_lb"])
    assert tot["bu_ac"] == pytest.approx((one["dry_bu"] + two["dry_bu"]) / tot["area_ac"])
    assert tot["moisture_pct"] == pytest.approx((15.0 * 1 + 12.0 * 2) / 3)                       # weighted by the area
    assert any("TASK0002" in w and "not its log" in w for w in rep["warnings"])
    assert rep["totals_only_tasks"] == [only[0]["id"]]
    assert len(cn.decode(root, [units[0].id], OPTS, log=lambda m: None)[1]["sms_summary"]["datasets"]) == 1
    with pytest.raises(ValueError, match="hold only the display's totals"):     # no reading to decode
        cn.decode(root, [only[0]["id"]], OPTS, log=lambda m: None)


def test_app_extracts_a_card_and_shows_its_summary(tmp_path, monkeypatch):
    """The app on a card: the time-basis option is offered with SMS's as the default, the extraction runs and the
    Summary of the card's totals is shown next to the numbers of the readings."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    n = 60
    root = _card(tmp_path / "card", {"TASK0001": {
        "tso": _tso("26/07/01-12:00:00", n, 6000.0),
        "tsh": _tsh(LINEAR, seconds=[0, 0, n], counts=[0, 0, 2500 * n], kg=700, moisture_sum=9800),
        "tlo": b"".join(_tlo(i + 1, i, 10, 1000) for i in range(n)),
        "tlh": b"".join(_tlh(i + 1, 2500) for i in range(n))}})
    _crop_table(root)
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.text_input(key="path_in").input(root)
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert next(g for g in at.button_group if str(g.key or "").startswith("tb_")).value == "sms"
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    assert next(m for m in at.metric if m.label == "Readings").value == f"{n:,}"
    line = next(c.value for c in at.caption if c.value.startswith("SMS Summary of these datasets"))
    assert "1.48 ac" in line and "1,500 lb wet" in line and "moisture 14.00 %" in line     # 6,000 m2; 60 s x 25 lb/s
