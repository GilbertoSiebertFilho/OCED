# -*- coding: utf-8 -*-
"""ISOXML harvest task data together with the outputs of steps 3 and 4: cleaned through the app, its shapefile for
DIFM (the 18 fields of the layout, the swath width and the moisture on every record, mass / volume = the import's
weight to volume, the date of each reading = its own day on the display's clock, numbers with 6 decimals, the
adjusted yield when the grower's weight or a combine factor is applied), the 'Optimize Swath Widths passes' control
of step 3, the clean harvest written as ISOXML again after such a cleaning, and the warnings of step 4, which stay
silent on a normal harvest and speak for a header that logs no moisture. Synthetic task data only
(tests/synthetic_isoxml.py: a made-up combine, header and field); every name and number is invented.

    python -m pytest -q tests/test_isoxml_difm.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import isoxml  # noqa: E402
from tests import synthetic_isoxml as SI  # noqa: E402
from tests.test_app_fixes import STALE, _app, _by_key, _clean, _open  # noqa: E402
from tests.test_difm import HALF, LABEL_3S, TESTED, _cells, _dbf, _difm, _parts  # noqa: E402

Q = lambda m: None  # noqa: E731
FT = 1 / 0.3048
FULL_FT = SI.N_SECTIONS * SI.SECTION_M * FT            # the whole made-up header
CANOLA = ("P094_Crop_Type", 10)                        # the made-up logs carry 60 lb/bu and 13.5 % for every crop ...
LB_BU, DRY_PCT = 50.0, 10.0                            # ... the import takes what SMS gives canola in ISOXML task data
SIX = re.compile(rb"^ *-?\d+\.\d{6}$")                 # a number with 6 decimals in its dBASE cell
YIELD_FIELDS = ("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D", "Yld_Vol_Dr")
DAY_OF_TIME = "the day of the reading's time (Time)"


def _harvest(n_pass: int, n: int, start: str, squeeze: float = 1.0) -> dict:
    """A made-up harvest whose grain flow follows the sections on (half the header at the start of every pass: those
    readings are half as wide with the same yield) and whose records carry an altitude. squeeze < 1 lays the passes
    closer to each other than the header is wide, so that every pass overlaps the one before."""
    R = SI.harvest(n_pass=n_pass, n=n, start=start)
    share = R["on"].sum(1) / R["on"].shape[1]
    R["flow"] = np.rint(R["flow"] * np.r_[np.ones(SI.LATENCY_S), share[:-SI.LATENCY_S]])   # cut LATENCY_S earlier
    R["up"] = np.rint(1_000_000 + 2_000 * np.sin(np.arange(len(R["t"])) / 40.0)).astype(np.int64)      # mm
    if squeeze != 1.0:
        R["lat"] = np.rint((SI.LAT0 + (R["lat"] - SI.LAT0) * squeeze) * 1e7) / 1e7
    return R


def _wet_lb(d) -> float:
    return float((d.Yld_Mass_W * d.Distance_f * d.Swth_Wdth_ / 43560.0).sum())


def _check_difm(zp: str, a: pd.DataFrame, lb_bu: float) -> pd.DataFrame:
    """What every shapefile for DIFM of an ISOXML harvest holds, against its clean file `a`: the members of the zip,
    the 18 fields of the layout with no empty cell, numbers with 6 decimals, the swath width and the moisture of
    every reading as the clean file has them, mass / volume = lb_bu on the wet and on the dry side, Time and Date =
    the day of the reading's own time, no lateral offset left after Optimize Swath Widths. Returns its attributes."""
    names, P = _parts(zp)
    stem = os.path.basename(zp)[:-len(".zip")]
    assert names == [stem + e for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    n, fields, recs = _dbf(P[".dbf"])
    assert fields == TESTED and len(fields) == 18 and n == len(a)
    cells = {f: _cells(fields, recs, f) for f, _, _, _ in fields}
    for f, typ, _, _ in fields:
        assert not sum(not c.strip() for c in cells[f]), f"{f}: empty cells"
        if typ == "N" and f != "Obj__Id":
            assert all(SIX.match(c) for c in cells[f]), f"{f}: not 6 decimals"
    x = pyogrio.read_dataframe(f"/vsizip/{zp}/{names[0]}", read_geometry=False)
    for f in ("Swth_Wdth_", "Moisture__", "Distance_f", "Track_deg_", "Duration_s", "Elevation_", "Speed_mph_"):
        assert np.abs(x[f].to_numpy(float) - a[f].to_numpy(float)).max() <= HALF, f
    assert (x["Swth_Wdth_"] > 0).all() and x["Moisture__"].between(5, 25).all()
    assert x["Elevation_"].between(3200, 3400).all()                  # the made-up altitude, about 1000 m, in feet
    for m, v in (("Yld_Mass_W", "Yld_Vol_We"), ("Yld_Mass_D", "Yld_Vol_Dr")):
        assert np.allclose(x[m] / x[v], lb_bu, rtol=1e-6, atol=0), (m, v)
    own = [str(t)[:10].replace("-", "") for t in a["Time"]]
    assert [c.decode() for c in cells["Time"]] == own and [c.decode() for c in cells["Date"]] == own
    assert (x["Y_Offset_f"] == 0).all()
    return x


def _no_difm_warning(at) -> bool:
    return not [w.value for w in at.warning if w.value.startswith("Shapefile for DIFM:")]


def _written_back(at, n_clean: int):
    """Step 4's one button for ISOXML task data pressed: (the record of the write, the written set read back)."""
    bs = [x for x in at.button if str(x.key or "").startswith("nw_go_")]
    assert len(bs) == 1 and bs[0].key.startswith("nw_go_isoxml_") and not bs[0].disabled
    bs[0].click().run()
    assert not at.exception, at.exception
    wd = at.session_state["workdir"]
    p = glob.glob(os.path.join(wd, "native", "*", "isoxml.json"))
    assert len(p) == 1
    W = json.load(open(p[0], encoding="utf-8"))
    assert W["n_kept"] == n_clean and W["check"]["ok"] is True and W["native"] is True
    back, _ = isoxml.decode(os.path.join(wd, W["path"]), None, log=Q)
    return W, back


# ================================================================================================ one combine
def test_app_isoxml_harvest_shapefile_for_difm_swath_passes_and_isoxml_again(tmp_path, monkeypatch):
    """One made-up combine that harvests across midnight on its display's clock, passes overlapping. Cleaned as it
    is: the shapefile for DIFM holds the monitor's yield and step 4 warns about nothing. With two passes of Optimize
    Swath Widths and the grower's weight used to adjust: the control reaches the cleaning, the default file is the
    adjusted one (Yld_Vol_Dr = Yld_Level, the other yield fields by the same factor), the other choice the monitor's,
    and the clean harvest written as ISOXML again reads back reading by reading, at its own time, with the weight's
    factor on its grain."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)     # a time taken as UTC would lose 6 hours
    R = _harvest(8, 60, "2026-09-10 23:56:00", squeeze=0.9)
    cut = len(R["t"]) // 2 + 20
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), SI.take(R, 0, cut), crop_attr=CANOLA)["folder"]
    b = SI.write_set(str(tmp_path / "in" / "s2" / "TASKDATA"), SI.take(R, cut - 1, len(R["t"])),
                     crop_attr=CANOLA)["folder"]
    z = SI.zip_sets([a, b], str(tmp_path / "Synthetic task data.zip"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, z)
    next(x for x in at.button if str(x.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    D = at.session_state["datasets"][tag]
    rec = D["sms_import"]
    assert rec["family"] == "isoxml" and D["source"]["time_basis"] == "local"
    assert (rec["resolved"]["test_weight_lb_bu"], rec["resolved"]["dry_moisture_pct"]) == (LB_BU, DRY_PCT)
    _by_key(at.text_input, "bnd_path_").input(SI.boundary(str(tmp_path / "bnd"), n_pass=8, n=60))
    _by_key(at.button, "bnd_use_").click().run()
    cdir = os.path.join(wd, "clean_shapefiles")
    zm = os.path.join(cdir, f"{tag}_sms3s_clean_DIFM.zip")
    za = os.path.join(cdir, f"{tag}_sms3s_clean_adjusted_DIFM.zip")

    # ---- cleaned as it is: one pass of Optimize Swath Widths (the control's default), nothing adjusted
    box = at.number_input(key="swath_passes")
    assert (box.value, box.min, box.max, box.label) == (1, 1, 3, "Optimize Swath Widths passes")
    C1 = _clean(at)
    R1 = C1["R"]
    assert R1["sms3sigma"]["swath"]["swath_passes"] == 1 and R1["sms3sigma"]["swath"]["n_narrowed"] > 100
    W1 = C1["difm"]
    assert (W1["zip"], W1["yield"], W1["error"], W1["warnings"]) == (zm, "monitor", None, [])
    assert _no_difm_warning(at) and not os.path.exists(za)
    assert not [r for r in at.radio if str(r.key or "").startswith("difm_y_")]
    a1 = pyogrio.read_dataframe(C1["shp"], read_geometry=False)
    x1 = _check_difm(zm, a1, LB_BU)
    for f in YIELD_FIELDS:
        assert np.abs(x1[f].to_numpy(float) - a1[f].to_numpy(float)).max() <= HALF, f
    assert (x1["Yld_Vol_Dr"] < x1["Yld_Vol_We"]).mean() > 0.9           # grain wetter than the 10 % of the import
    # the display's clock ran over midnight: both days are in the file, each reading on its own
    days = pd.Series(pd.to_datetime(x1["Time"]).dt.strftime("%Y-%m-%d")).value_counts().to_dict()
    assert set(days) == {"2026-09-10", "2026-09-11"} and min(days.values()) > 100
    assert W1["days"] == {DAY_OF_TIME: len(a1)} and set(a1["Harv_Day"]) == set(days)
    # the widths the sections gave: the readings of half the header are there, at half its width; a narrowed
    # reading carries its narrowed width (the logged one stays in Wdth_Raw of the clean shapefile)
    part = (a1["Wdth_Raw"] < 0.6 * FULL_FT).to_numpy()
    assert part.sum() >= 3 and np.allclose(a1["Wdth_Raw"][part], FULL_FT / 2)
    assert np.allclose(a1["Wdth_Raw"][~part], FULL_FT)
    narrowed = (a1["Swth_Wdth_"] < a1["Wdth_Raw"] - 1e-6).to_numpy()
    assert narrowed.sum() > 100 and np.array_equal(x1["Swth_Wdth_"].to_numpy(float) < FULL_FT - 1e-3, narrowed | part)

    # ---- two passes of Optimize Swath Widths, the grower's weight used to adjust
    at.number_input(key="swath_passes").set_value(2).run()
    assert not at.exception, at.exception
    assert at.session_state["smsset"]["swath_passes"] == 2 and any(STALE in w.value for w in at.warning)
    _by_key(at.number_input, "gw_w_").set_value(round(_wet_lb(a1) * 1.05)).run()
    _by_key(at.button_group, "gw_use_").set_value("adjust").run()
    C2 = _clean(at)
    R2 = C2["R"]
    assert C2["settings"]["swath_passes"] == 2 and R2["settings"]["sms3sigma"]["swath_passes"] == 2
    assert R2["sms3sigma"]["swath"]["swath_passes"] == 2
    assert "(2 passes)" in next(r for r in R2["cascade"] if r["filter"] == "S2")["criterion"]
    assert not any(STALE in w.value for w in at.warning)
    L = float(R2["level"]["factor_final"])
    assert C2["adjusted"] and abs(L - 1) > 0.02
    q = _by_key(at.radio, "difm_y_")
    assert q.value == "adjusted" and q.options[0] == LABEL_3S and "grower's weight (adjusted yield)" in q.options[1]
    W2 = C2["difm"]
    assert (W2["zip"], W2["yield"], W2["error"], W2["warnings"]) == (za, "adjusted", None, [])
    assert _no_difm_warning(at) and not os.path.exists(zm)
    a2 = pyogrio.read_dataframe(C2["shp"], read_geometry=False)
    x2 = _check_difm(za, a2, LB_BU)
    k = a2["Yld_Level"].to_numpy(float) / a2["Yld_Vol_Dr"].to_numpy(float)
    assert np.allclose(k, L, rtol=0, atol=2e-5)
    assert np.abs(x2["Yld_Vol_Dr"].to_numpy(float) - a2["Yld_Level"].to_numpy(float)).max() <= HALF
    for f in ("Yld_Mass_D", "Yld_Mass_W", "Yld_Vol_We"):
        assert np.abs(x2[f].to_numpy(float) / (a2[f].to_numpy(float) * k) - 1).max() < 1e-6, f
    assert W2["days"] == {DAY_OF_TIME: len(a2)}
    said = json.load(open(C2["json"], encoding="utf-8"))["shapefile_for_difm"]
    assert (said["file"], said["yield"], said["column"]) == (os.path.basename(za), "adjusted", "Yld_Level")
    # the other choice: the monitor's yield of the same cleaning, in the same layout
    q.set_value("monitor").run()
    assert not at.exception, at.exception
    assert at.session_state["cleaned"][tag]["difm"]["zip"] == zm and os.path.exists(za)
    x3 = _check_difm(zm, a2, LB_BU)
    for f in YIELD_FIELDS:
        assert np.abs(x3[f].to_numpy(float) - a2[f].to_numpy(float)).max() <= HALF, f
    _by_key(at.radio, "difm_y_").set_value("adjusted").run()
    assert _no_difm_warning(at)

    # ---- the clean harvest of that cleaning as ISOXML again: every reading, at its own time
    W, back = _written_back(at, len(a2))
    assert len(back) == len(a2) and sorted(back["Time"].astype(str)) == sorted(a2["Time"].astype(str))
    o_b, o_a = np.argsort(back["Time"].astype(str).to_numpy(), kind="stable"), np.argsort(
        a2["Time"].astype(str).to_numpy(), kind="stable")
    bb, aa = back.iloc[o_b].reset_index(drop=True), a2.iloc[o_a].reset_index(drop=True)
    assert np.abs(bb["Moisture__"].to_numpy(float) - aa["Moisture__"].to_numpy(float)).max() < 1e-3
    assert np.abs(bb["Duration_s"].to_numpy(float) - aa["Duration_s"].to_numpy(float)).max() < 1e-6
    area = lambda d: (d.Distance_f * d.Swth_Wdth_).to_numpy(float)  # noqa: E731
    assert np.abs(area(bb) / area(aa) - 1).max() <= 0.0101           # widths in whole sections, the area kept
    assert abs(area(bb).sum() / area(aa).sum() - 1) < 5e-3
    assert (bb["Swth_Wdth_"] < 0.6 * FULL_FT).sum() == (aa["Swth_Wdth_"] < 0.6 * FULL_FT).sum() >= 3
    assert _wet_lb(back) == pytest.approx(_wet_lb(a2) * L, rel=1e-4)  # the factor of step 3 on the grain
    assert any("applied to the grain" in n for n in W["notes"])
    assert _no_difm_warning(at)


# ================================================================================================ two combines
def _two_combines(folder: str, monkeypatch, n_pass: int = 32, n: int = 200, bias: float = 1.06) -> str:
    """Two made-up combines on alternate passes of one field (a zip of their two zipped sets): the second reads its
    grain `bias` times too high and starts 90 s after the first; both harvest across midnight on their clocks."""
    R = _harvest(n_pass, n, "2026-09-10 23:40:00")
    blk = len(R["t"]) // n_pass
    sets = []
    for k, (serial, b) in enumerate((("SYN-ISO-0001", 1.0), ("SYN-ISO-0002", bias))):
        idx = np.concatenate([np.arange(p * blk, (p + 1) * blk) for p in range(k, n_pass, 2)])
        Rk = {key: v[idx] for key, v in R.items()}
        Rk["t"] = R["t"][0] + 90_000 * k + 1000 * np.arange(len(idx), dtype=np.int64)
        Rk["flow"] = np.rint(Rk["flow"] * b)
        monkeypatch.setattr(SI, "SERIAL", serial)
        sets.append(SI.write_set(os.path.join(folder, f"c{k + 1}", "TASKDATA"), Rk, crop_attr=CANOLA)["folder"])
    return SI.zip_sets(sets, os.path.join(folder, "Synthetic task data.zip"))


def test_app_two_isoxml_combines_the_combine_factor_goes_into_the_adjusted_file(tmp_path, monkeypatch):
    """Two made-up combines side by side, one reading 6 % high, the combine factor switched on: the factor is applied,
    step 4 asks which yield and the default file carries the corrected one (Yld_Vol_Dr = Yld_Harm, the other yield
    fields by the factor of each reading's combine) in the same layout, with the swath width, the moisture and the own
    day of every reading; the clean harvest written as ISOXML again carries the factor on each combine's grain."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    z = _two_combines(str(tmp_path / "in"), monkeypatch)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, z)
    next(x for x in at.button if str(x.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["datasets"]) == 1                       # one field, season and crop: one file
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    _by_key(at.toggle, "cf_on_").set_value(True).run()
    C = _clean(at)
    R = C["R"]
    fa = {m: float(v) for m, v in R["machines"]["factor_applied"].items()}
    assert sorted(fa) == ["SYN-ISO-0001", "SYN-ISO-0002"]
    assert fa["SYN-ISO-0001"] / fa["SYN-ISO-0002"] == pytest.approx(1.06, abs=0.01) and "level" not in R
    za = os.path.join(wd, "clean_shapefiles", f"{tag}_sms3s_clean_adjusted_DIFM.zip")
    q = _by_key(at.radio, "difm_y_")
    assert q.value == "adjusted" and q.options[0] == LABEL_3S and "combine correction (adjusted yield)" in q.options[1]
    Wd = C["difm"]
    assert (Wd["zip"], Wd["yield"], Wd["error"], Wd["warnings"]) == (za, "adjusted", None, [])
    assert _no_difm_warning(at)
    a = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    x = _check_difm(za, a, LB_BU)
    k = a["Machine"].map(fa).to_numpy(float)
    assert set(np.round(k, 6)) == {round(v, 6) for v in fa.values()} and len(set(a["Machine"])) == 2
    assert np.abs(x["Yld_Vol_Dr"].to_numpy(float) - a["Yld_Harm"].to_numpy(float)).max() <= HALF
    assert np.allclose(a["Yld_Harm"].to_numpy(float) / a["Yld_Vol_Dr"].to_numpy(float), k, rtol=0, atol=2e-5)
    for f in ("Yld_Mass_D", "Yld_Mass_W", "Yld_Vol_We"):
        assert np.allclose(x[f].to_numpy(float) / a[f].to_numpy(float), k, rtol=0, atol=2e-5), f
    days = set(pd.to_datetime(x["Time"]).dt.strftime("%Y-%m-%d"))
    assert days == {"2026-09-10", "2026-09-11"} and Wd["days"] == {DAY_OF_TIME: len(a)}
    assert set(x["Dataset"]) == set(a["Dataset"]) and len(set(x["Dataset"])) == 2      # one dataset per combine
    # ISOXML again: each combine's readings with its factor on the grain
    W, back = _written_back(at, len(a))
    assert len(back) == len(a) and sorted(set(back["Machine"])) == sorted(fa)
    for m, f in fa.items():
        assert _wet_lb(back[back["Machine"] == m]) == pytest.approx(_wet_lb(a[a["Machine"] == m]) * f, rel=1e-4), m
    assert _no_difm_warning(at)


# ================================================================================================ the engine
def _cleaned(folder: str, **set_kw) -> dict:
    """One made-up harvest decoded, imported as SMS and cleaned with the engine: {dec, rec, R, clean (attributes)}."""
    R0 = _harvest(6, 60, "2026-09-10 23:57:00")
    SI.write_set(os.path.join(folder, "in", "s1", "TASKDATA"), R0, crop_attr=CANOLA, **set_kw)
    wd = os.path.join(folder, "work")
    cand = er.open_input([os.path.join(folder, "in")], wd, log=Q)[0]
    dec = er.decode(cand, None, None, wd, log=Q)
    rep = dec["report"]
    shp_i, _, rec = er.import_as_sms(dec["shp"], dec["tag"], os.path.join(wd, "decoded"), crop=rep["crop_name"],
                                     monitor=rep["monitor_product"], fmt=er.import_format(dec["source"]), log=Q)
    S = er.sms_clean_defaults({"method": "sms3sigma", "tag": dec["tag"], "machines": {"harmonise": False}}, rec)
    R = er.clean(shp_i, os.path.join(wd, "clean"), S, log=Q, source=dec["source"])
    return {"dec": dec, "rec": rec, "R": R, "shp": R["files"]["difm_ready_shp"],
            "clean": pyogrio.read_dataframe(R["files"]["difm_ready_shp"], read_geometry=False)}


def _write(K: dict, zp: str, **kw) -> dict:
    difm = _difm()
    return difm.write_zip(K["shp"], zp, source=kw.pop("source", K["dec"]["source"]), columns=K["R"]["columns"],
                          basis=difm.import_basis(K["R"]), **kw)


def test_the_day_of_an_isoxml_reading_is_the_day_on_the_display_s_clock(tmp_path, monkeypatch):
    """The Time of ISOXML task data is the log's own clock, which SMS shows as it is. A display on local time (the
    GNSS time of the log is hours ahead), one whose log carries no GNSS time, and one whose clock is the GNSS UTC
    time itself: every reading is dated by its own time, whatever this computer's clock, with the decode record and
    without it (a clean file opened on its own says its source in Src_Fmt). The rule of the UTC times stays that of
    the sources that write UTC instants: the same clean file said to be a John Deere log is dated by this computer's
    clock."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    for name, kw, basis in (("local", {}, "local"), ("no_gnss", {"gps_offset_h": None}, "unknown"),
                            ("utc", {"gps_offset_h": 0.0}, "UTC")):
        K = _cleaned(str(tmp_path / name), **kw)
        assert K["dec"]["source"]["time_basis"] == basis
        W = _write(K, str(tmp_path / f"{name}_DIFM.zip"))
        names, P = _parts(W["zip"])
        n, fields, recs = _dbf(P[".dbf"])
        own = [str(t)[:10].replace("-", "") for t in K["clean"]["Time"]]
        assert len(set(own)) == 2 and n == len(own)                     # the harvest ran over midnight on its clock
        got = [c.decode() for c in _cells(fields, recs, "Time")]
        assert got == [c.decode() for c in _cells(fields, recs, "Date")]
        assert got == own and W["days"] == {DAY_OF_TIME: n}, name
        # the same without the decode record (a clean file opened on its own): Src_Fmt says ISOXML
        W0 = _write(K, str(tmp_path / f"{name}_alone_DIFM.zip"), source=None)
        n0, f0, r0 = _dbf(_parts(W0["zip"])[1][".dbf"])
        assert [c.decode() for c in _cells(f0, r0, "Time")] == own and W0["days"] == {DAY_OF_TIME: n}, name
        # a decoder's time-zone offset in the record is not applied again (the ISOXML decoder moved the times)
        W1 = _write(K, str(tmp_path / f"{name}_tz_DIFM.zip"), source=dict(K["dec"]["source"], tz_offset_h=-7.0))
        n1, f1, r1 = _dbf(_parts(W1["zip"])[1][".dbf"])
        assert [c.decode() for c in _cells(f1, r1, "Time")] == own, name
    # the UTC rule itself is untouched: the same times as a source that writes UTC instants
    Wj = _write(K, str(tmp_path / "as_jd_DIFM.zip"), source={"format": "jd_jdl", "time_basis": "UTC"})
    nj, fj, rj = _dbf(_parts(Wj["zip"])[1][".dbf"])
    assert set(c.decode() for c in _cells(fj, rj, "Time")) == {"20260910"}
    assert list(Wj["days"]) == ["the day of the reading's time (Time, UTC in this computer's clock time: UTC -6 h)"]


def test_task_data_without_an_elevation_leaves_the_field_empty_and_says_so(tmp_path):
    """A display that logs no elevation: Elevation_ is empty on every record of the shapefile for DIFM (never an
    invented value), the notes say why, nothing is warned about, and every other number is the clean file's own."""
    R0 = _harvest(4, 40, "2026-09-10 14:00:00")
    R0.pop("up")
    SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), R0, crop_attr=CANOLA)
    wd = str(tmp_path / "work")
    dec = er.decode(er.open_input([str(tmp_path / "in")], wd, log=Q)[0], None, None, wd, log=Q)
    S = er.sms_clean_defaults({"method": "sms3sigma", "tag": dec["tag"], "machines": {"harmonise": False}}, None)
    R = er.clean(dec["shp"], os.path.join(wd, "clean"), S, log=Q, source=dec["source"])
    shp = R["files"]["difm_ready_shp"]
    a = pyogrio.read_dataframe(shp, read_geometry=False)
    assert a["Elevation_"].isna().all() and len(a) > 100
    W = _difm().write_zip(shp, str(tmp_path / "flat_DIFM.zip"), source=dec["source"], columns=R["columns"])
    n, fields, recs = _dbf(_parts(W["zip"])[1][".dbf"])
    assert fields == TESTED and n == len(a) and W["warnings"] == []
    assert all(not c.strip() for c in _cells(fields, recs, "Elevation_"))
    assert (f"Elevation_: {n:,} of {n:,} readings hold no number in the clean file's Elevation_ (a value the source "
            "did not log): left empty") in W["notes"]
    assert not any("written from their numeric value" in x for x in W["notes"])
    for f, typ, _, _ in fields:
        if typ == "N" and f not in ("Obj__Id", "Elevation_"):
            cells = _cells(fields, recs, f)
            assert all(SIX.match(c) for c in cells), f
            if f != "Y_Offset_f":
                assert np.abs(np.array([float(c) for c in cells]) - a[f].to_numpy(float)).max() <= HALF, f


def test_an_isoxml_header_that_logs_no_moisture_is_warned_about_and_one_without_sections_has_its_width(tmp_path):
    """The swath width and the moisture of the readings are to be in the file DIFM gets. A normal harvest: both on
    every record, no warning. A header that logs no moisture: the field is empty and the warning of step 4 says so.
    A header without sections: its swath width is the working width it logs, on every record."""
    difm = _difm()
    K = _cleaned(str(tmp_path / "normal"))
    W = _write(K, str(tmp_path / "normal_DIFM.zip"))
    assert W["warnings"] == []
    _check_difm(W["zip"], K["clean"], LB_BU)
    dry = _cleaned(str(tmp_path / "dry"), moisture=False)           # two days: the sessions diagnostic pairs them
    assert any("logs no moisture" in w for w in dry["dec"]["report"]["warnings"])
    assert dry["R"]["sessions"]["n_sessions"] == 2 and dry["R"]["n_kept"] > 300

    def no_constant(name):
        raise AssertionError(f"{name} in the cleaning record")
    json.loads(open(dry["R"]["files"]["json"], encoding="utf-8").read(), parse_constant=no_constant)
    assert dry["R"]["sessions"]["field"]["cleaned_map_mean_dry_sym"] is None
    Wn = _write(dry, str(tmp_path / "dry_DIFM.zip"))
    n = len(dry["clean"])
    assert Wn["warnings"] == [difm.blank_mapped_warning({"Moisture__": n}, n)]
    assert f"{n:,} of {n:,} readings have no Moisture__ (the moisture)" in Wn["warnings"][0]
    nn, fields, recs = _dbf(_parts(Wn["zip"])[1][".dbf"])
    assert all(not c.strip() for c in _cells(fields, recs, "Moisture__"))
    assert not sum(not c.strip() for c in _cells(fields, recs, "Swth_Wdth_"))
    # a header that logs no moisture leaves no number in the clean file: said plainly, the other numbers exact
    assert (f"Moisture__: {n:,} of {n:,} readings hold no number in the clean file's Moisture__ (a value the source "
            "did not log): left empty") in Wn["notes"]
    assert not any("written from their numeric value" in x for x in Wn["notes"])
    flat = _cleaned(str(tmp_path / "flat"), sections=False)
    Wf = _write(flat, str(tmp_path / "flat_DIFM.zip"))
    assert Wf["warnings"] == []
    xf = _check_difm(Wf["zip"], flat["clean"], LB_BU)
    assert set(np.round(xf["Swth_Wdth_"], 3)) == {round(FULL_FT, 3), round(FULL_FT / 2, 3)}
