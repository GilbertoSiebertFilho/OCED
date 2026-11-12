# -*- coding: utf-8 -*-
"""engine/formats/isoxml.py: ISOXML harvest task data (TASKDATA.XML + TLG time logs) read as Ag Leader SMS reads it,
and its way through the engine (detect, units, decode, import as SMS, the SMS 3-sigma cleaning, the clean file saved
as ISOXML again). Synthetic task data only (tests/synthetic_isoxml.py: a made-up combine, header and field): every
number here is invented.

    python -m pytest -q tests/test_isoxml.py
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import struct
import sys
import zipfile

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine import sms_import as si  # noqa: E402
from engine.formats import common, detect, isoxml  # noqa: E402
from engine.formats import native_write as NW  # noqa: E402
from tests import synthetic_isoxml as SI  # noqa: E402

Q = lambda m: None  # noqa: E731
FT = 1 / 0.3048


def _set(tmp, name, R, **kw):
    return SI.write_set(os.path.join(str(tmp), name, "TASKDATA"), R, **kw)


def _reference(R, latency_s=SI.LATENCY_S):
    """The points of one log by the rules, written out plainly (no record closer than 0.9 s to the next here):
    a record with a section on whose grain (the flow latency_s later) is above 0."""
    n = len(R["t"])
    rows = []
    for i in range(n):
        k = int(R["on"][i].sum())
        j = i + latency_s
        if not k or j >= n or R["flow"][j] <= 0:
            continue
        p = max(i - 1, 0)
        a, b = (p, i) if i else (0, 1)                       # the first record takes the step of the second
        dx = (R["lon"][b] - R["lon"][a]) * SI.M_PER_DEG * np.cos(np.radians(R["lat"][a]))
        dy = (R["lat"][b] - R["lat"][a]) * SI.M_PER_DEG
        dur = (R["t"][i] - R["t"][p]) / 1000.0 if i else 1.0
        ys = (np.arange(R["on"].shape[1]) + 0.5 - R["on"].shape[1] / 2) * SI.SECTION_M
        rows.append({"rec": i, "dur": dur, "dist_m": float(np.hypot(dx, dy)), "width_m": k * SI.SECTION_M,
                     "wet_kg": R["flow"][j] / 1e6 * dur, "moist": R["moist"][j] / 1e4,
                     "y_off_m": float(ys[R["on"][i]].mean()), "t": int(R["t"][i])})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ the rules
def test_points_follow_the_rules_sms_reads_a_time_log_by(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    _set(tmp_path, "a", R)
    df, rep = isoxml.decode(str(tmp_path), None, log=Q)
    E = _reference(R)
    assert len(df) == len(E) > 40 and list(df.columns) == common.STANDARD_NAMES + ["lon", "lat", "Y_Offset_f"]
    assert np.allclose(df.Duration_s, E.dur) and np.allclose(df.Distance_f, E.dist_m * FT)
    assert np.allclose(df.Swth_Wdth_, E.width_m * FT) and np.allclose(df.Moisture__, E.moist)
    area_ac = E.dist_m * E.width_m / 4046.8564224
    assert np.allclose(df.Yld_Mass_W, E.wet_kg * common.LB_PER_KG / area_ac)
    assert np.allclose(df.Yld_Vol_We, df.Yld_Mass_W / 60.0)
    # dry: one-sided at SMS's 13.5 % for this crop
    assert np.allclose(df.Yld_Mass_D, df.Yld_Mass_W * np.minimum(1.0, (100 - E.moist) / (100 - 13.5)))
    assert np.allclose(df.Y_Offset_f, E.y_off_m * FT)        # half the header on: its centre lies left of the middle
    assert (df.Y_Offset_f < -1).sum() == 4 and (df.Y_Offset_f == 0).sum() == len(df) - 4
    # the point sits the connector's X offset ahead of the logged position, along the track
    i = int(E.rec[10])
    east = SI.M_PER_DEG * np.cos(np.radians(R["lat"][i]))
    assert df.Track_deg_.iloc[10] == pytest.approx(90.0, abs=1e-6)
    assert (df.lon.iloc[10] - R["lon"][i]) * east == pytest.approx(SI.X_CONNECTOR_M, abs=1e-6)
    assert df.lat.iloc[10] == pytest.approx(R["lat"][i], abs=1e-9)
    assert df.Time.iloc[0] == "2026-09-10 14:00:00.000" and df.Elevation_.isna().all()
    assert set(df.Machine) == {SI.SERIAL} and set(df.Src_Fmt) == {"isoxml"} and set(df.Field) == {"Synthetic field"}
    assert rep["format"] == "isoxml" and rep["time_logs"] == "sms" and rep["n_readings"] == len(df)
    assert rep["pre_step"]["log_end"] == 0 and rep["pre_step"]["sections_off"] > 0
    assert rep["n_records_read"] == len(R["t"])
    assert rep["calibration"]["display"]["0057"] == "Synthetic wet flow, shown in t/h"
    # a log that ends inside a pass: its last seconds have no grain to take, so they are no points
    shutil.rmtree(tmp_path / "a")
    _set(tmp_path, "b", SI.take(R, 0, 20))
    d2, r2 = isoxml.decode(str(tmp_path), None, log=Q)
    assert r2["pre_step"]["log_end"] == SI.LATENCY_S and len(d2) == 20 - SI.LATENCY_S


def test_a_record_closer_than_0_9_s_to_the_next_is_put_together_with_it(tmp_path):
    R = SI.harvest(n_pass=1, n=30, turn=0)
    R["t"] = R["t"].copy()
    R["t"][12:] -= 500                                           # record 12 comes 0.5 s after record 11
    _set(tmp_path, "a", R, latency_s=0)
    df, rep = isoxml.decode(str(tmp_path), None, log=Q)
    # 30 records: no grain yet in the first LATENCY_S (the flow is read without a latency here), one put together
    assert rep["pre_step"]["put_together"] == 1 and rep["pre_step"]["no_flow"] == SI.LATENCY_S and len(df) == 26
    row = df[df.Time == "2026-09-10 14:00:11.500"].iloc[0]       # record 12, measured from record 10
    step = (R["lon"][12] - R["lon"][10]) * SI.M_PER_DEG * np.cos(np.radians(R["lat"][10]))
    assert row.Duration_s == pytest.approx(1.5) and row.Distance_f == pytest.approx(step * FT, rel=1e-9)
    assert step == pytest.approx(2 * SI.SPEED_MS, abs=0.02)
    flow = (R["flow"][11] * 1.0 + R["flow"][12] * 0.5) / 1.5     # the time-weighted mean of the two
    wet_lb = row.Yld_Mass_W * row.Distance_f * row.Swth_Wdth_ / 43560.0
    assert wet_lb == pytest.approx(flow / 1e6 * common.LB_PER_KG * 1.5, rel=1e-9)
    assert "2026-09-10 14:00:11.000" not in set(df.Time)


# ------------------------------------------------------------------------------------------------ sets and units
@pytest.fixture()
def several(tmp_path):
    """A task handed out in two slices (the second starts with the last record of the first), another field with
    another crop, an older season and a seeding task."""
    R = SI.harvest(n_pass=4, n=40)
    _set(tmp_path, "slice1", SI.take(R, 0, 100), seeding=True)
    _set(tmp_path, "slice2", SI.take(R, 99, len(R["t"])))
    _set(tmp_path, "other", SI.harvest(n_pass=2, n=20, start="2026-09-12 09:00:00", seed=9),
         field="Other synthetic field", crop_attr=("P094_Crop_Type", 10))
    _set(tmp_path, "old", SI.harvest(n_pass=2, n=20, start="2025-09-01 09:00:00", seed=3))
    idle = SI.harvest(n_pass=1, n=20, start="2026-09-13 09:00:00")
    idle["flow"][:] = 0                                          # the combine driven with the header down, no grain
    _set(tmp_path, "idle", idle, field="Idle synthetic field")
    return str(tmp_path), R


def test_units_are_machine_field_crop_and_season(several):
    root, R = several
    p = isoxml.probe(root)
    assert p.format_id == "isoxml" and p.root == root and p.n_files == 5
    assert "5 harvest time log(s) in 5 TASKDATA set(s)" in p.summary and "Synthetic grower" in p.summary
    assert any("without a yield value" in w for w in p.warnings)            # the seeding log is not read
    U = {u.id: u for u in isoxml.list_units(root)}
    assert set(U) == {f"{SI.SERIAL}|Synthetic field|wheat|2026", f"{SI.SERIAL}|Other synthetic field|canola|2026",
                      f"{SI.SERIAL}|Synthetic field|wheat|2025", f"{SI.SERIAL}|Idle synthetic field|wheat|2026"}
    idle = U[f"{SI.SERIAL}|Idle synthetic field|wheat|2026"]             # no grain in its log: listed, not pre-selected
    assert not idle.default and idle.label.endswith("no grain flow in the log(s)")
    with pytest.raises(isoxml.IsoxmlError, match="hold no harvest reading.*holds grain"):
        isoxml.decode(root, [idle.id], log=Q)
    main = U[f"{SI.SERIAL}|Synthetic field|wheat|2026"]
    assert main.default and not U[f"{SI.SERIAL}|Synthetic field|wheat|2025"].default
    assert main.n_records == len(R["t"]) + 1 and main.machine == SI.SERIAL and main.crop == "wheat"
    assert "2 time log(s)" in main.label and "product Synthetic product" in main.label
    with pytest.raises(isoxml.IsoxmlError, match="unknown unit"):
        isoxml.decode(root, ["no such unit"], log=Q)


def test_each_log_on_its_own_as_sms_or_joined(several, tmp_path_factory):
    root, R = several
    uid = [f"{SI.SERIAL}|Synthetic field|wheat|2026"]
    sms, rs = isoxml.decode(root, uid, log=Q)
    joined, rj = isoxml.decode(root, uid, log=Q, time_logs="joined")
    whole = str(tmp_path_factory.mktemp("whole"))
    _set(whole, "one", R)
    one, _ = isoxml.decode(whole, None, log=Q)
    # joined = the task as one log; each slice on its own loses the last seconds of the first slice (the record the
    # second slice repeats is a point there: its first record)
    assert len(joined) == len(one) and len(sms) == len(one) - (SI.LATENCY_S - 1)
    assert rs["pre_step"]["log_end"] == SI.LATENCY_S and rj["pre_step"]["log_end"] == 0
    assert rs["time_logs"] == "sms" and rj["time_logs"] == "joined"
    wet = lambda d: float((d.Yld_Mass_W * d.Distance_f * d.Swth_Wdth_ / 43560.0).sum())  # noqa: E731
    assert wet(joined) == pytest.approx(wet(one), rel=1e-12) and wet(sms) < wet(one)
    assert sms.Dataset.nunique() == 2 and joined.Dataset.nunique() == 1       # one dataset per log read
    with pytest.raises(isoxml.IsoxmlError, match="time_logs"):
        isoxml.decode(root, uid, log=Q, time_logs="other")
    # the same set given twice is read once
    shutil.copytree(os.path.join(root, "slice1"), os.path.join(root, "slice1_copy"))
    again, ra = isoxml.decode(root, uid, log=Q)
    assert len(again) == len(sms) and any("twice" in w for w in ra["warnings"])


def test_two_header_devices_and_a_log_split_over_two_files(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    _set(tmp_path / "plain", "a", R)
    S = _set(tmp_path / "split", "a", R, split=True, idle_header=True)
    assert len(S["parts"]) == 2
    a, _ = isoxml.decode(str(tmp_path / "plain"), None, log=Q)
    b, rep = isoxml.decode(str(tmp_path / "split"), None, log=Q)
    # the grain of the second file belongs to the records of the first; the header that never works gives no point
    pd.testing.assert_frame_equal(a, b)
    assert rep["n_records_read"] == len(R["t"])                # the two files are one log, counted once
    assert {d["time_log"] for d in rep["details"]} == {"TLG00001/TLG00002"}
    assert sorted(d["n_points"] for d in rep["details"]) == [0, len(b)]


def test_no_moisture_and_a_header_without_sections(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    _set(tmp_path / "ref", "a", R)
    ref, _ = isoxml.decode(str(tmp_path / "ref"), None, log=Q)
    _set(tmp_path / "nom", "a", R, moisture=False)
    d, rep = isoxml.decode(str(tmp_path / "nom"), None, log=Q)
    assert len(d) == len(ref) and d.Moisture__.isna().all() and np.allclose(d.Yld_Mass_D, d.Yld_Mass_W)
    assert any("no moisture" in w for w in rep["warnings"])
    # no section states: the actual working width while the device works; nothing to offset the point by
    _set(tmp_path / "nos", "a", R, sections=False)
    d, rep = isoxml.decode(str(tmp_path / "nos"), None, log=Q)
    assert len(d) == len(ref) and np.allclose(d.Swth_Wdth_, ref.Swth_Wdth_) and (d.Y_Offset_f == 0).all()
    assert np.allclose(d.Yld_Mass_W, ref.Yld_Mass_W)
    assert any("0043" in n and "not compared with SMS" in n for n in rep["notes"])


def test_external_files_and_no_connection(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    _set(tmp_path / "ref", "a", R)
    ref, _ = isoxml.decode(str(tmp_path / "ref"), None, log=Q)
    _set(tmp_path / "xfr", "a", R, xfr=True)                    # devices and task in DVC00000.XML / TSK00000.XML
    pd.testing.assert_frame_equal(isoxml.decode(str(tmp_path / "xfr"), None, log=Q)[0], ref)
    _set(tmp_path / "nocnn", "a", R, connection=False)          # no CNN: the connector of the other device
    pd.testing.assert_frame_equal(isoxml.decode(str(tmp_path / "nocnn"), None, log=Q)[0], ref)


# ------------------------------------------------------------------------------------------------ time
def test_time_is_the_log_clock_and_the_offset_to_utc_is_measured(tmp_path):
    R = SI.harvest(n_pass=1, n=20)
    _set(tmp_path / "loc", "a", R)                              # GNSS UTC 6 h ahead of the display's clock
    d, rep = isoxml.decode(str(tmp_path / "loc"), None, log=Q)
    assert rep["time_basis"] == "local" and "-6.00 h" in rep["calibration"]["time_note"]
    o = dataclasses.replace(isoxml.default_options(), tz_offset_h=-7.0)
    d7, r7 = isoxml.decode(str(tmp_path / "loc"), None, o, log=Q)
    assert d7.Time.iloc[0] == "2026-09-10 13:00:00.000" and r7["time_basis"] == "local"
    _set(tmp_path / "utc", "a", R, gps_offset_h=0.0)            # a log on UTC
    du, ru = isoxml.decode(str(tmp_path / "utc"), None, log=Q)
    assert ru["time_basis"] == "UTC" and du.Time.iloc[0] == d.Time.iloc[0]
    _set(tmp_path / "none", "a", R, gps_offset_h=None)          # no GNSS time in the log
    dn, rn = isoxml.decode(str(tmp_path / "none"), None, o, log=Q)
    assert rn["time_basis"] == "unknown" and dn.Time.iloc[0] == d.Time.iloc[0]
    assert any("tz_offset_h ignored" in w for w in rn["warnings"])


# ------------------------------------------------------------------------------------------------ crop and import
def test_crop_and_what_sms_gives_it(tmp_path):
    R = SI.harvest(n_pass=1, n=20)
    _set(tmp_path / "w", "a", R)
    _, rep = isoxml.decode(str(tmp_path / "w"), None, log=Q)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"]) == ("wheat", 60.0, 13.5)
    assert mp["basis"] == "sms_crop"
    assert (mp["min_yield"], mp["max_yield"]) == (5.0, 10_000.0) and rep["crop_name"] == "wheat"
    assert mp["file"]["test_weight_lb_bu"] == pytest.approx(60.0, abs=0.01) and mp["file"]["std_moisture_pct"] == 13.5
    assert si.format_family("isoxml") == "isoxml" and "isoxml" in si.FILE_CROP_FAMILIES
    Rv = si.resolve(si.settings(), rep["crop_name"], mp, "isoxml")
    assert (Rv["test_weight_lb_bu"], Rv["dry_moisture_pct"], Rv["min_yield"], Rv["max_yield"]) == (60.0, 13.5, 5.0, 1e4)
    assert Rv["sources"] == {"test_weight_lb_bu": si.SRC_ISO_CROP, "dry_moisture_pct": si.SRC_ISO_CROP,
                             "min_yield": si.SRC_ISO, "max_yield": si.SRC_ISO}
    assert si.resolve(si.settings({"max_yield": 300}), "wheat", mp, "isoxml")["sources"]["max_yield"] == si.SRC_YOU
    # canola: SMS's 10 %, where the log says another reference moisture and SMS's card table says 8.5 %
    _set(tmp_path / "c", "a", R, crop_attr=("P094_Crop_Type", 10))
    d, rep = isoxml.decode(str(tmp_path / "c"), None, log=Q)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"]) == ("canola", 50.0, 10.0)
    assert si.resolve(si.settings(), "canola", mp, "isoxml")["dry_moisture_pct"] == 10.0
    assert np.allclose(d.Yld_Vol_We, d.Yld_Mass_W / 50.0)
    assert any("differs from the reference moisture" in w for w in rep["warnings"])
    # a maker's code OCED does not know: the log's own density and reference moisture, named as what they are, with
    # what they read like as a guess and a warning to check the product
    _set(tmp_path / "u", "a", R, crop_attr=("P094_Crop_Type", 99))
    U = isoxml.list_units(str(tmp_path / "u"))
    assert [u.crop for u in U] == ["crop type 99"] and "crop type 99 (wheat?)" in U[0].label and U[0].default
    d, rep = isoxml.decode(str(tmp_path / "u"), None, log=Q)
    mp = rep["monitor_product"]
    assert mp["crop"] is None and mp["basis"] is None and mp["dry_moisture_pct"] == 13.5
    assert mp["test_weight_lb_bu"] == pytest.approx(60.0, abs=0.01) and mp["guess"] == "wheat"
    assert "read like wheat" in mp["source"] and "not known" in mp["source"]
    w = [x for x in rep["warnings"] if "is not one OCED knows" in x]
    assert len(w) == 1 and "P094_Crop_Type 99" in w[0] and "13.5 %" in w[0] and "read like wheat" in w[0]
    Rv = si.resolve(si.settings(), rep["crop_name"], mp, "isoxml")
    assert Rv["sources"]["dry_moisture_pct"] == si.SRC_FILE and Rv["sources"]["max_yield"] == si.SRC_ISO
    # decoded together with a unit read at SMS's 60 lb/bu, the log's own 60.00 is no difference worth a warning;
    # a canola unit is
    _set(tmp_path / "u", "w", SI.harvest(n_pass=1, n=20, start="2026-09-11 08:00:00"), field="Second field")
    _, rep2 = isoxml.decode(str(tmp_path / "u"), None, log=Q)
    assert len(rep2["calibration"]["units"]) == 2 and not any("differ between the units" in x for x in rep2["warnings"])
    _set(tmp_path / "u", "c", SI.harvest(n_pass=1, n=20, start="2026-09-12 08:00:00"), field="Third field",
         crop_attr=("P094_Crop_Type", 10))
    _, rep3 = isoxml.decode(str(tmp_path / "u"), None, log=Q)
    assert any("differ between the units" in x and "50.00 / 10.00" in x for x in rep3["warnings"])
    # the crop numbers of the maker's cards: a crop OCED knows, with no SMS value for ISOXML: the product table
    _set(tmp_path / "d", "a", R, crop_attr=("P094_Crop_Type", 47))
    _, rep = isoxml.decode(str(tmp_path / "d"), None, log=Q)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["basis"]) == ("durum", None, None)
    assert si.resolve(si.settings(), rep["crop_name"], mp, "isoxml")["dry_moisture_pct"] == 13.0
    # a crop named by the field's crop type, with no SMS value established: SMS's product table
    _set(tmp_path / "b", "a", R, crop_attr=None, crop_type="Synthetic barley")
    _, rep = isoxml.decode(str(tmp_path / "b"), None, log=Q)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"]) == ("barley", None, None)
    Rv = si.resolve(si.settings(), rep["crop_name"], mp, "isoxml")
    assert (Rv["test_weight_lb_bu"], Rv["dry_moisture_pct"], Rv["max_yield"]) == (48.0, 14.5, 1e4)
    assert Rv["sources"]["test_weight_lb_bu"] == si.SRC_TABLE
    # nothing names the crop and the log carries no density: what SMS gives a dataset without a product, said in a
    # warning; a product chosen by the user works
    _set(tmp_path / "n", "a", R, crop_attr=None, density=False)
    d, rep = isoxml.decode(str(tmp_path / "n"), None, log=Q)
    mp = rep["monitor_product"]
    assert (mp["crop"], mp["test_weight_lb_bu"], mp["dry_moisture_pct"], mp["basis"]) == (None, 56.0, 13.0,
                                                                                         "sms_no_product")
    assert np.allclose(d.Yld_Vol_We, d.Yld_Mass_W / 56.0)
    assert any("without a product" in x and "choose the product" in x for x in rep["warnings"])
    Rv = si.resolve(si.settings(), rep["crop_name"], mp, "isoxml")
    assert (Rv["test_weight_lb_bu"], Rv["dry_moisture_pct"]) == (56.0, 13.0)
    assert Rv["sources"]["test_weight_lb_bu"] == si.SRC_ISO_NONE == "SMS for ISOXML task data without a product"
    o = dataclasses.replace(isoxml.default_options(), crop="oats")
    d, _ = isoxml.decode(str(tmp_path / "n"), None, o, log=Q)
    assert np.allclose(d.Yld_Vol_We, d.Yld_Mass_W / common.CROPS["oats"][0])


# ------------------------------------------------------------------------------------------------ damaged inputs
def test_damaged_and_partial_sets_are_said_plainly(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    good = _set(tmp_path / "in", "good", R)["folder"]
    n_good = len(isoxml.decode(str(tmp_path / "in"), None, log=Q)[0])
    # a set whose .BIN is missing: the other set is read, the missing file is named
    _set(tmp_path / "in", "nobin", SI.harvest(n_pass=1, n=20, start="2026-09-11 08:00:00"), write_bin=False)
    p = isoxml.probe(str(tmp_path / "in"))
    assert p is not None and p.n_files == 1 and any("TLG00001.BIN is missing" in w for w in p.warnings)
    d, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    assert len(d) == n_good and any("TLG00001.BIN is missing" in w for w in rep["warnings"])
    cands = detect.detect([str(tmp_path / "in")])
    assert [c["decoder"] for c in cands] == ["isoxml"] and any("TLG00001.BIN is missing" in n for n in cands.notes)
    # a log cut inside a record: the complete records are read
    b = os.path.join(good, "TLG00001.BIN")
    raw = open(b, "rb").read()
    open(b, "wb").write(raw[:-7])
    d, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    assert any("ends inside a record" in w for w in rep["warnings"]) and rep["n_records_read"] == len(R["t"]) - 1
    # a record naming a value the header does not list: read up to there
    open(b, "wb").write(raw + struct.pack("<IHiiiIHBBi", 1, 17_000, 0, 0, 0, 1, 17_000, 1, 200, 5))
    d, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    assert any("names a value its header does not list" in w for w in rep["warnings"]) and len(d) == n_good
    # TASKDATA.XML that is not XML
    bad = tmp_path / "bad" / "TASKDATA"
    bad.mkdir(parents=True)
    (bad / "TASKDATA.XML").write_text("<ISO11783_TaskData><TSK", encoding="utf-8")
    assert isoxml.probe(str(tmp_path / "bad")) is None and "cannot be read" in isoxml.explain(str(tmp_path / "bad"))
    with pytest.raises(isoxml.IsoxmlError, match="no harvest time log"):
        isoxml.decode(str(tmp_path / "bad"), None, log=Q)
    # task data with no time log at all (a setup or prescription set)
    setup = tmp_path / "setup" / "TASKDATA"
    setup.mkdir(parents=True)
    (setup / "TASKDATA.XML").write_text('<ISO11783_TaskData><CTR A="CTR-1" B="Synthetic grower"/></ISO11783_TaskData>',
                                        encoding="utf-8")
    assert isoxml.probe(str(tmp_path / "setup")) is None and "no time log" in isoxml.explain(str(tmp_path / "setup"))
    assert isoxml.explain(str(tmp_path / "in")) == "" and isoxml.explain(str(tmp_path / "nothing")) == ""


def test_task_data_of_another_operation_is_not_a_harvest(tmp_path):
    """A log without a yield value (here a seeding rate) is not listed; detect says what was found and why no
    harvest is read from it, instead of 'nothing recognised'."""
    R = SI.harvest(n_pass=1, n=20)
    d = _set(tmp_path, "s", R, seeding=True)["folder"]
    for f in os.listdir(d):
        if f.startswith("TLG00001"):
            os.remove(os.path.join(d, f))
    assert isoxml.probe(str(tmp_path)) is None
    cands = detect.detect([str(tmp_path)])
    assert len(cands) == 0 and cands.message.startswith("ISOXML task data was found (1 TASKDATA.XML with 1 TLG log")
    assert "holds a yield value" in cands.message and "Supported inputs" in cands.message
    assert "ISOXML harvest task data" in detect.SUPPORTED_TEXT


# ------------------------------------------------------------------------------------------------ through the engine
@pytest.fixture(scope="module")
def route(tmp_path_factory):
    """A zip of zipped task data sets opened with the engine, decoded, imported as SMS and cleaned (SMS 3-sigma,
    with a boundary)."""
    base = str(tmp_path_factory.mktemp("iso_route"))
    R = SI.harvest(n_pass=6, n=60)
    half = len(R["t"]) // 2 + 20                              # the first slice ends inside a pass
    _set(base, "s1", SI.take(R, 0, half))
    _set(base, "s2", SI.take(R, half - 1, len(R["t"])))
    z = SI.zip_sets([os.path.join(base, "s1", "TASKDATA"), os.path.join(base, "s2", "TASKDATA")],
                    os.path.join(base, "Synthetic task data.zip"))
    wd = os.path.join(base, "work")
    cands = er.open_input([z], wd, log=Q)
    cand = cands[0]
    units = er.list_units(cand)
    dec = er.decode(cand, [u.id for u in units], None, wd, log=Q)
    rep = dec["report"]
    fmt = er.import_format(dec["source"])
    shp_i, n_i, rec = er.import_as_sms(dec["shp"], dec["tag"], os.path.join(wd, "decoded"), crop=rep["crop_name"],
                                       monitor=rep["monitor_product"], fmt=fmt, log=Q)
    S = er.sms_clean_defaults({"method": "sms3sigma", "tag": dec["tag"], "machines": {"harmonise": False},
                               "aoi": {"file": SI.boundary(os.path.join(base, "bnd"), n_pass=6, n=60)}}, rec)
    Rc = er.clean(shp_i, os.path.join(wd, "clean"), S, log=Q, source=dec["source"])
    return {"R": R, "cands": cands, "cand": cand, "units": units, "dec": dec, "fmt": fmt, "import": (shp_i, n_i, rec),
            "clean": Rc, "wd": wd, "base": base}


def test_a_zip_of_zipped_sets_is_one_raw_dataset(route):
    cands, cand = route["cands"], route["cand"]
    assert len(cands) == 1 and cand["kind"] == "raw" and cand["decoder"] == "isoxml" and not cands.message
    assert cand["probe"].n_files == 2 and "2 harvest time log(s) in 2 TASKDATA set(s)" in cand["label"]
    assert not any("ISOXML task data was found" in n for n in cands.notes)
    assert len(route["units"]) == 1 and route["units"][0].default
    assert er.candidate_tag(cand, route["units"]) == "Synthetic_field_2026"
    assert "isoxml" in detect.DECODERS and detect.default_options("isoxml").shrink == "one_sided"


def test_sets_partly_loose_partly_zipped_are_one_dataset(tmp_path):
    R = SI.harvest(n_pass=4, n=40)
    a = _set(tmp_path / "given", "loose", SI.take(R, 0, 100))["folder"]
    b = _set(tmp_path / "tmp", "zipped", SI.take(R, 99, len(R["t"])))["folder"]
    SI.zip_sets([b], str(tmp_path / "given" / "more sets.zip"))
    cands = er.open_input([str(tmp_path / "given")], str(tmp_path / "work"), log=Q)
    assert [c.get("decoder") for c in cands] == ["isoxml"] and cands[0]["probe"].n_files == 2
    assert os.path.isdir(a) and len(er.list_units(cands[0])) == 1


def test_a_damaged_zip_among_the_zipped_sets_does_not_stop_the_others(tmp_path):
    """A portal hands a task out as many zipped sets in one zip: one of them damaged is left out and named (the
    candidates' left_out, also a note), the others are read; nothing of a zip that breaks half way is read."""
    R = SI.harvest(n_pass=4, n=40)
    a = _set(tmp_path / "t", "s1", SI.take(R, 0, 100))["folder"]
    b = _set(tmp_path / "t", "s2", SI.take(R, 99, len(R["t"])))["folder"]
    z = SI.zip_sets([a, b], str(tmp_path / "sets.zip"))
    whole = er.open_input([z], str(tmp_path / "w0"), log=Q)
    assert whole.left_out == [] and whole[0]["probe"].n_files == 2
    # a third zipped set that is no zip, and a fourth whose content is damaged after its first file
    c = _set(tmp_path / "t", "s3", SI.harvest(n_pass=1, n=20, start="2026-09-12 09:00:00"),
             field="Other synthetic field")["folder"]
    inner = SI.zip_sets([c], str(tmp_path / "one.zip"))
    with zipfile.ZipFile(inner) as zi:
        raw = bytearray(zi.read(zi.namelist()[0]))
    raw[len(raw) // 2:len(raw) // 2 + 64] = bytes(64)            # the compressed bytes of its members overwritten
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("TASKDATA-0000000000-20260910149998.zip", b"PK this is not a zip any more")
        zf.writestr("TASKDATA-0000000000-20260910149999.zip", bytes(raw))
    cands = er.open_input([z], str(tmp_path / "w1"), log=Q)
    assert [x.get("decoder") for x in cands] == ["isoxml"] and cands[0]["probe"].n_files == 2
    assert len(er.list_units(cands[0])) == 1                    # nothing of the damaged set (another field) is read
    assert len(cands.left_out) == 2 and all("left out" in w and "NOT in the data" in w for w in cands.left_out)
    assert "20260910149998.zip" in cands.left_out[0] and "20260910149999.zip" in cands.left_out[1]
    assert all(w in cands.notes for w in cands.left_out)
    # the same among the zips of a folder given
    os.makedirs(tmp_path / "folder")
    shutil.copy(z, tmp_path / "folder" / "sets.zip")
    (tmp_path / "folder" / "broken.zip").write_bytes(b"PK nothing")
    cf = er.open_input([str(tmp_path / "folder")], str(tmp_path / "w2"), log=Q)
    assert [x.get("decoder") for x in cf] == ["isoxml"] and len(cf.left_out) == 3
    # a zip GIVEN that is damaged is still refused, and a guard still stops everything
    with pytest.raises(ValueError, match="not a readable zip"):
        er.open_input([str(tmp_path / "folder" / "broken.zip")], str(tmp_path / "w3"), log=Q)
    assert issubclass(detect.DamagedZip, ValueError)


def test_decode_import_and_clean_run_unchanged(route):
    dec, (shp_i, n_i, rec) = route["dec"], route["import"]
    src = dec["source"]
    assert src["format"] == "isoxml" and route["fmt"] == "isoxml" and src["unit_ids"] == [route["units"][0].id]
    assert src["monitor_product"]["crop"] == "wheat" and src["crop_name"] == "wheat"
    assert src["time_basis"] == "local" and os.path.isdir(src["input_root"])
    g = pyogrio.read_dataframe(dec["shp"], read_geometry=False)
    assert "Y_Offset_f" in g.columns and set(g["Crop"]) == {"wheat"} and len(g) == dec["n"]
    assert rec["family"] == "isoxml" and rec["resolved"]["max_yield"] == 1e4 and rec["resolved"]["min_yield"] == 5.0
    assert rec["sources"]["test_weight_lb_bu"] == si.SRC_ISO_CROP and n_i == rec["n_in"] <= dec["n"]
    Rc = route["clean"]
    steps = {r["filter"]: r for r in Rc["cascade"]}
    assert Rc["n_kept"] > 0.5 * n_i and "S2" in steps and Rc["sms3sigma"]["swath"]["scope"]
    # the boundary stops before the east end of the passes: the clip sets readings aside
    assert sum(p["removed"] for p in Rc["pre_steps"]) + steps["S1"]["removed"] > 0
    assert os.path.exists(Rc["files"]["difm_ready_shp"])
    # the field-of-interest check decodes one unit at a time
    lon, lat, area = er._unit_readings(route["cand"], route["units"][0].id, detect.default_options("isoxml"),
                                       route["wd"])
    assert len(lon) == dec["n"] and np.isfinite(area).all()
    # the decoder's own option reaches it through the engine and is recorded
    dj = er.decode(route["cand"], None, None, os.path.join(route["base"], "work_j"), log=Q, time_logs="joined")
    assert dj["report"]["time_logs"] == "joined" and dj["n"] == dec["n"] + SI.LATENCY_S - 1
    assert dj["source"]["decoder_kwargs"] == {"time_logs": "joined"}
    o, R_pre = er.decoder_options_for_import(detect.default_options("isoxml"), {}, "wheat", "isoxml")
    assert o.test_weight_lb_bu is None and o.std_moisture_pct is None and o.shrink == "one_sided"


def test_the_clean_file_is_saved_as_isoxml_and_reads_back(route):
    """ISOXML is the monitor's own format of ISOXML task data: one entry, native, written with the ISOXML writer;
    the written set, read with the reader, holds the clean readings."""
    src = route["dec"]["source"]
    o = NW.options(src)
    assert [(x["id"], x["native"], x["available"]) for x in o] == [("isoxml", True, True)]
    assert o[0]["label"] == NW.ISOXML_NATIVE_LABEL and o[0]["reason"] == NW.ISOXML_NATIVE_NOTE
    old = dict(src, report={k: v for k, v in route["dec"]["report"].items() if k != "time_logs"})
    assert not NW.options(old)[0]["available"] and NW.options(old)[0]["reason"] == NW.OLD_DECODE
    clean = route["clean"]["files"]["difm_ready_shp"]
    W = NW.write("isoxml", src, clean, os.path.join(route["base"], "native"), new_ids=False, log=Q)
    assert W["native"] is True and W["label"] == NW.ISOXML_NATIVE_LABEL and NW.ISOXML_NATIVE_NOTE in W["notes"]
    g = pyogrio.read_dataframe(clean, read_geometry=False)
    back, rep = isoxml.decode(W["path"], None, log=Q)
    assert len(back) == len(g) == W["n_kept"] == W["verify"]["n_points"]
    area = lambda d: float((d.Distance_f * d.Swth_Wdth_).sum() / 43560.0)  # noqa: E731
    wet = lambda d: float((d.Yld_Mass_W * d.Distance_f * d.Swth_Wdth_ / 43560.0).sum())  # noqa: E731
    assert wet(back) == pytest.approx(wet(g), rel=1e-6) and area(back) == pytest.approx(area(g), rel=5e-3)
    assert rep["pre_step"]["put_together"] == 0 or len(back) == len(g)     # no reading lost to a record too close
    with pytest.raises(ValueError, match="inside the raw input"):
        NW.write("isoxml", src, clean, os.path.join(src["input_root"], "out"), log=Q)


def test_a_written_set_of_any_clean_file_reads_back_reading_by_reading(tmp_path):
    """The round trip with the ISOXML writer on the writer's own synthetic clean file (two made-up combines, GPS
    jitter, narrowed readings, a pause): every reading comes back, with its duration, width, moisture and grain."""
    from engine.formats import isoxml_write as iw
    from tests.test_isoxml_write import _clean_file
    shp = _clean_file(str(tmp_path))
    W = iw.write_clean(None, shp, str(tmp_path / "out"), new_ids=False, log=Q)
    g = pyogrio.read_dataframe(shp, read_geometry=False)
    cands = er.open_input([W["zip"]], str(tmp_path / "work"), log=Q)
    assert [c.get("decoder") for c in cands] == ["isoxml"]
    units = er.list_units(cands[0])
    assert sorted(u.machine for u in units) == ["SYNTH-COMBINE-A", "SYNTH-COMBINE-B"]
    assert {u.crop for u in units} == {"wheat"} and {u.field for u in units} == {"Synthetic field"}
    back, rep = isoxml.decode(cands[0]["probe"].root, None, log=Q)
    assert len(back) == len(g) and rep["pre_step"]["put_together"] == 0
    I = pd.read_csv(W["index_csv"])
    back = back.assign(t_ms=((pd.to_datetime(back.Time) - isoxml.EPOCH) / pd.Timedelta(milliseconds=1)).round()
                       .astype("int64"))
    J = I.merge(back, left_on=["Machine", "t_written_ms"], right_on=["Machine", "t_ms"], how="left")
    c = g.iloc[J.src_row.to_numpy()].reset_index(drop=True)
    assert J.Duration_s.notna().all()
    assert np.abs(J.Duration_s - c.Duration_s).max() < 1e-9 and np.abs(J.Moisture__ - c.Moisture__).max() < 1e-4
    wet = lambda d: (d.Yld_Mass_W * d.Distance_f * d.Swth_Wdth_ / 43560.0).to_numpy()  # noqa: E731
    assert np.abs(wet(J) / wet(c) - 1).max() < 1e-6
    assert np.abs((J.Distance_f * J.Swth_Wdth_) / (c.Distance_f * c.Swth_Wdth_) - 1).max() <= 0.0101
    # a reading shorter than 0.9 s keeps its grain: written with 0.9 s and a lower flow
    import geopandas as gpd
    q = gpd.read_file(shp)
    q.loc[q.index % 7 == 3, "Duration_s"] = 0.5
    q.to_file(str(tmp_path / "short.shp"), driver="ESRI Shapefile", encoding="UTF-8")
    W2 = iw.write_clean(None, str(tmp_path / "short.shp"), str(tmp_path / "out2"), new_ids=False, log=Q)
    assert W2["verify"]["n_points"] == len(q) and any("shorter than 0.9 s" in n for n in W2["notes"])
    assert abs(W2["verify"]["total_wet_rel"]) < 1e-7


# ------------------------------------------------------------------------------------------------ across the header
def _recs(df, R):
    """The record of R every reading of df was made of (one record per second from R's first)."""
    t = ((pd.to_datetime(df.Time) - isoxml.EPOCH) / pd.Timedelta(milliseconds=1)).round().astype("int64").to_numpy()
    return ((t - int(R["t"][0])) // 1000).astype(int)


def test_the_point_is_moved_sideways_to_the_centre_of_the_sections_on(tmp_path):
    """Rule 5 pinned in size and direction: with the two outermost sections on the left drawn in, the centre of the
    whole header lies right of the middle, and the point is moved there: to the RIGHT of the track (south on a pass
    driven east, north on the way back), the connector's X offset along the track."""
    R = SI.harvest(n_pass=2, n=30)
    ys = [-2400, -2200, -1500, -500, 500, 1500, 2500, 3500]          # mm; every section is 1 m wide
    _set(tmp_path / "in", "a", R, section_y_mm=ys)
    df, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    y_ref = sum(ys) / len(ys) / 1000.0
    assert y_ref == pytest.approx(0.175) and {d["y_ref_m"] for d in rep["details"]} == {0.175}
    assert {d["sections"] for d in rep["details"]} == {"logged"}
    assert not any("side by side" in w for w in rep["warnings"])
    rec = _recs(df, R)
    assert list(rec) == list(_reference(R).rec)
    north = (df.lat.to_numpy() - R["lat"][rec]) * SI.M_PER_DEG
    east = (df.lon.to_numpy() - R["lon"][rec]) * SI.M_PER_DEG * np.cos(np.radians(R["lat"][rec]))
    go_e = np.isclose(df.Track_deg_, 90.0, atol=1e-6)
    go_w = np.isclose(df.Track_deg_, 270.0, atol=1e-6)
    assert go_e.sum() > 20 and go_w.sum() > 20
    assert np.allclose(north[go_e], -y_ref, atol=1e-6) and np.allclose(north[go_w], y_ref, atol=1e-6)
    assert np.allclose(east[go_e], SI.X_CONNECTOR_M, atol=1e-6)
    assert np.allclose(east[go_w], -SI.X_CONNECTOR_M, atol=1e-6)
    # a part of the header on: Y_Offset_f = the centre of the sections on, measured from that reference
    part = (df.Swth_Wdth_ < 0.6 * SI.N_SECTIONS * SI.SECTION_M * FT).to_numpy()
    assert part.sum() == 4 and np.allclose(df.Y_Offset_f[part], (np.mean(ys[:4]) / 1000.0 - y_ref) * FT)
    assert (df.Y_Offset_f[~part] == 0).all()
    # the widest state of a log decides: a log whose first section is never on is referred to the other seven
    R7 = SI.harvest(n_pass=2, n=30)
    R7["on"] = R7["on"].copy()
    R7["on"][:, 0] = False
    _set(tmp_path / "seven", "a", R7, section_y_mm=ys)
    d7, r7 = isoxml.decode(str(tmp_path / "seven"), None, log=Q)
    assert {d["y_ref_m"] for d in r7["details"]} == {round(sum(ys[1:]) / 7 / 1000.0, 4)}
    assert d7.Swth_Wdth_.max() == pytest.approx(7 * SI.SECTION_M * FT)
    # what a reading measures does not depend on where its point is put
    _set(tmp_path / "sym", "a", R)
    sym, _ = isoxml.decode(str(tmp_path / "sym"), None, log=Q)
    for c in ("Duration_s", "Distance_f", "Swth_Wdth_", "Yld_Mass_W", "Moisture__"):
        assert np.allclose(df[c], sym[c])
    assert np.abs(df.lat - sym.lat).max() * SI.M_PER_DEG == pytest.approx(0.175, abs=1e-6)


def test_section_positions_that_do_not_lie_side_by_side_are_not_used(tmp_path):
    """A display can log the Y offsets of its sections while it is still laying the header out. Offsets that are not
    one section apart cannot be the centres of the sections: used as such they would put every point of the log
    metres beside the header. They are passed over (the sections taken side by side, centred on the header), the
    logs are counted in a warning, and every log of a field keeps its own reference."""
    R = SI.harvest(n_pass=4, n=40)
    half = len(R["t"]) // 2
    crowded = [-3500, -3450, -3400, -3300, -3000, -2500, -1500, -500]      # mm: crowded to the left, 3 m of 8
    drawn_in = [-2400, -2200, -1500, -500, 500, 1500, 2500, 3500]          # side by side but for the left end
    _set(tmp_path / "in", "s1", SI.take(R, 0, half), section_y_mm=crowded)
    _set(tmp_path / "in", "s2", SI.take(R, half, len(R["t"])), section_y_mm=drawn_in)
    df, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    by_set = {d["set"]: d for d in rep["details"]}
    assert (by_set["s1"]["sections"], by_set["s1"]["y_ref_m"]) == ("side by side", 0.0)
    assert (by_set["s2"]["sections"], by_set["s2"]["y_ref_m"]) == ("logged", 0.175)
    w = [x for x in rep["warnings"] if "do not lie side by side" in x]
    assert len(w) == 1 and "1 of 2 time log(s)" in w[0] and "centred on the header" in w[0]
    # that log reads exactly as one whose display logged the centres of the sections
    _set(tmp_path / "ref", "s1", SI.take(R, 0, half))
    ref, r0 = isoxml.decode(str(tmp_path / "ref"), None, log=Q)
    first = df[df.Dataset == df.Dataset.iloc[0]].reset_index(drop=True)
    pd.testing.assert_frame_equal(first, ref)
    assert not any("side by side" in x for x in r0["warnings"])
    assert {d["sections"] for d in r0["details"]} == {"logged"}
    # the other log keeps the reference its own offsets give (0.175 m right of the track)
    other = df[df.Dataset != df.Dataset.iloc[0]]
    rec = _recs(other, R)
    north = (other.lat.to_numpy() - R["lat"][rec]) * SI.M_PER_DEG
    go_e = np.isclose(other.Track_deg_, 90.0, atol=1e-6)
    assert go_e.sum() > 20 and np.allclose(north[go_e], -0.175, atol=1e-6)
    # an odd offset in the middle of the header, or offsets out of order, are passed over too
    for k, ys in enumerate(([-3500, -2500, -1500, -900, 500, 1500, 2500, 3500],
                            [-3500, -2500, 500, -500, -1500, 1500, 2500, 3500])):
        _set(tmp_path / f"odd{k}", "s1", SI.take(R, 0, half), section_y_mm=ys)
        d, r = isoxml.decode(str(tmp_path / f"odd{k}"), None, log=Q)
        assert {x["sections"] for x in r["details"]} == {"side by side"}
        pd.testing.assert_frame_equal(d, ref)


def test_sections_numbered_from_the_right_keep_their_side(tmp_path):
    """A header whose sections are numbered from the right: the Y offsets fall from one section to the next (+ =
    right of travel), so the first sections are the right ones. Offsets one section apart are used as logged: with
    the first half of the header on, the reading is centred RIGHT of the header's middle. Offsets that do not lie
    side by side are passed over and the sections taken side by side in the order they are numbered in (the first
    on the right), centred on the header: the half header still reads on the right, not mirrored to the left."""
    R = SI.harvest(n_pass=2, n=30)
    half_m = SI.N_SECTIONS * SI.SECTION_M / 4.0                  # the centre of half the header, from its middle
    falling = [3500, 2500, 1500, 500, -500, -1500, -2500, -3500]            # mm; section 0 is the rightmost
    _set(tmp_path / "logged", "a", R, section_y_mm=falling)
    df, rep = isoxml.decode(str(tmp_path / "logged"), None, log=Q)
    assert {d["sections"] for d in rep["details"]} == {"logged"} and {d["y_ref_m"] for d in rep["details"]} == {0.0}
    assert not any("side by side" in w for w in rep["warnings"])
    part = (df.Swth_Wdth_ < 0.6 * SI.N_SECTIONS * SI.SECTION_M * FT).to_numpy()
    assert part.sum() == 4 and np.allclose(df.Y_Offset_f[part], +half_m * FT) and (df.Y_Offset_f[~part] == 0).all()
    # the same header numbered from the left reads its first half on the other side
    _set(tmp_path / "rising", "a", R, section_y_mm=falling[::-1])
    dr, _ = isoxml.decode(str(tmp_path / "rising"), None, log=Q)
    assert np.allclose(dr.Y_Offset_f[part], -half_m * FT)
    # offsets logged while the header was laid out, crowded to the right: still numbered from the right
    crowded = [3500, 3450, 3400, 3300, 3000, 2500, 1500, 500]
    _set(tmp_path / "crowded", "a", R, section_y_mm=crowded)
    dc, rc = isoxml.decode(str(tmp_path / "crowded"), None, log=Q)
    assert {d["sections"] for d in rc["details"]} == {"side by side"}
    assert {d["y_ref_m"] for d in rc["details"]} == {0.0}
    assert len([w for w in rc["warnings"] if "do not lie side by side" in w]) == 1
    assert np.allclose(dc.Y_Offset_f[part], +half_m * FT) and (dc.Y_Offset_f[~part] == 0).all()
    pd.testing.assert_frame_equal(dc, df)                 # exactly the log whose display logged the centres
    # ... and crowded to the left, numbered from the left: the mirror image
    _set(tmp_path / "crowded_left", "a", R, section_y_mm=[-v for v in crowded])
    dl, rl = isoxml.decode(str(tmp_path / "crowded_left"), None, log=Q)
    assert {d["sections"] for d in rl["details"]} == {"side by side"}
    assert np.allclose(dl.Y_Offset_f[part], -half_m * FT)
    pd.testing.assert_frame_equal(dl, dr)


# ------------------------------------------------------------------------------------------------ what is left out
def test_what_is_left_out_is_said(tmp_path):
    """Records that give no reading for a reason the user should know (no position, a clock that steps back) are
    counted in a warning, and a unit that gives no reading at all says why."""
    R = SI.harvest(n_pass=2, n=30)
    Rn = {k: v.copy() for k, v in R.items()}
    Rn["lat"][10:15] = 0.0                                       # five records without a position
    Rn["lon"][10:15] = 0.0
    _set(tmp_path / "nopos", "a", Rn)
    d, rep = isoxml.decode(str(tmp_path / "nopos"), None, log=Q)
    n = rep["pre_step"]["no_position"]
    assert n == 6                                                # the five, and the one measured from the last of them
    assert any(f"{n} record(s)" in w and "no position" in w for w in rep["warnings"])
    Rb = {k: v.copy() for k, v in R.items()}
    Rb["t"][20:23] -= 60_000                                     # the clock steps a minute back for three records
    _set(tmp_path / "back", "a", Rb)
    d, rep = isoxml.decode(str(tmp_path / "back"), None, log=Q)
    assert rep["pre_step"]["time_step"] == 3
    assert any("3 record(s)" in w and "steps back" in w for w in rep["warnings"])
    # nothing of the kind in an ordinary log
    _set(tmp_path / "ok", "a", R)
    assert not any("no position" in w or "steps back" in w
                   for w in isoxml.decode(str(tmp_path / "ok"), None, log=Q)[1]["warnings"])
    # a unit whose header measured no grain: the reason is in the message
    idle = SI.harvest(n_pass=1, n=20)
    idle["flow"][:] = 0
    _set(tmp_path / "idle", "a", idle)
    with pytest.raises(isoxml.IsoxmlError) as e:
        isoxml.decode(str(tmp_path / "idle"), None, log=Q)
    msg = str(e.value)
    assert "hold no harvest reading" in msg and not msg.rstrip().endswith(":")
    assert "no grain" in msg and "1 time log(s)" in msg
    # a set whose TASKDATA.XML lost its device descriptions: said, not taken for a combine that cut nothing
    import re
    lost = _set(tmp_path / "nodvc", "a", R)["folder"]
    x = os.path.join(lost, "TASKDATA.XML")
    with open(x, encoding="utf-8") as f:
        txt = f.read()
    with open(x, "w", encoding="utf-8") as f:
        f.write(re.sub(r"<DVC .*?</DVC>", "", txt, flags=re.S))
    with pytest.raises(isoxml.IsoxmlError, match="hold no harvest reading.*device description"):
        isoxml.decode(str(tmp_path / "nodvc"), None, log=Q)
    # sections on and grain, but the log ends before the grain of its records arrives: the counts say so
    _set(tmp_path / "short", "a", SI.take(SI.harvest(n_pass=1, n=20), 2, 5))
    with pytest.raises(isoxml.IsoxmlError, match="hold no harvest reading.*3 record"):
        isoxml.decode(str(tmp_path / "short"), None, log=Q)


def test_a_damaged_log_file_is_named_not_listed(tmp_path):
    R = SI.harvest(n_pass=2, n=30)
    good = _set(tmp_path / "in", "good", R)["folder"]
    n_good = len(isoxml.decode(str(tmp_path / "in"), None, log=Q)[0])
    # a .BIN that is not a time log (bytes of no meaning): its times are not in order
    bad = _set(tmp_path / "in", "noise", SI.harvest(n_pass=1, n=20, start="2026-09-11 08:00:00"))["folder"]
    rng = np.random.default_rng(7)
    with open(os.path.join(bad, "TLG00001.BIN"), "wb") as f:
        f.write(rng.integers(0, 256, 20_000, dtype=np.uint8).tobytes())
    p = isoxml.probe(str(tmp_path / "in"))
    assert p.n_files == 1 and any("TLG00001.BIN" in w and "damaged" in w for w in p.warnings)
    U = isoxml.list_units(str(tmp_path / "in"))
    assert len(U) == 1 and U[0].year == 2026 and U[0].start < U[0].end
    d, rep = isoxml.decode(str(tmp_path / "in"), None, log=Q)
    assert len(d) == n_good and any("damaged" in w for w in rep["warnings"])
    shutil.rmtree(os.path.dirname(bad))
    # a header that lists fewer values than the records use: the unit counts the records that can be read
    x = os.path.join(good, "TLG00001.XML")
    with open(x, encoding="utf-8") as f:
        head = f.read().splitlines()
    dlv = [i for i, s in enumerate(head) if s.startswith("<DLV")]
    with open(x, "w", encoding="utf-8") as f:
        f.write("\n".join(s for i, s in enumerate(head) if i not in dlv[-1:]) + "\n")
    S = isoxml.scan(str(tmp_path / "in"))
    assert S["logs"] == [] and isoxml.probe(str(tmp_path / "in")) is None
    assert any("names a value its header does not list" in w and "not read" in w for w in S["warnings"])
    assert "names a value its header does not list" in isoxml.explain(str(tmp_path / "in"))


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
