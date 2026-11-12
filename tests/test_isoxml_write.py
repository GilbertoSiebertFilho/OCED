# -*- coding: utf-8 -*-
"""engine/formats/isoxml_write.py: the clean harvest as an ISOXML TASKDATA set. Synthetic data only (made-up field,
made-up combines): every number here is invented."""
from __future__ import annotations

import os
import struct
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pandas as pd
import pytest

from engine.formats import common
from engine.formats import isoxml_write as iw

LAT0, LON0 = 51.90, -114.20                     # a made-up position
M_PER_DEG = 111_320.0


def _clean_file(folder: str, seed: int = 3, date_only: bool = False, jitter: bool = True, narrow: bool = True,
                name: str = "synthetic_sms3s_clean.shp") -> str:
    """Two made-up combines, three datasets, 1-s readings with GPS jitter, a pause, some narrowed readings (as after
    Optimize Swath Widths: Wdth_Raw / Swath_Scl), in the standard schema plus the clean file's appended columns.
    jitter=False / narrow=False: positions one Distance apart and full widths, as a monitor logs them."""
    import geopandas as gpd
    rng = np.random.default_rng(seed)
    rows = []
    for m, (mach, w_ft) in enumerate((("SYNTH-COMBINE-A", 40.0), ("SYNTH-COMBINE-B", 35.0))):
        t0 = pd.Timestamp("2026-08-20 13:00:00") + pd.Timedelta(minutes=7 * m)
        t = 0.0
        oid = 0
        for p in range(4):
            ds = f"Synthetic {mach[-1]} {'26/08/20-13:00:00' if p < 2 else '26/08/20-15:00:00'}"
            if p == 2:
                t += 3600.0                                    # a pause between the datasets
                oid = 0
            n = 60
            east = p % 2 == 0
            x0 = 0.0 if east else 60 * 1.9
            for i in range(n):
                dur = float(rng.choice([0.995, 1.0, 1.005]))
                spd_mph = 4.2 + rng.normal(0, 0.1)
                dist = spd_mph * 1.466667 * dur
                if jitter:
                    x = x0 + (i if east else -i) * 1.9 + rng.normal(0, 0.15)   # jitter: steps are not Distance
                    y = (m * 4 + p) * w_ft * 0.3048 + rng.normal(0, 0.05)
                else:
                    x0 += (dist if east else -dist) * 0.3048 if i else 0.0    # one Distance after the previous
                    x = x0
                    y = (m * 4 + p) * w_ft * 0.3048
                wr = w_ft
                wc = w_ft - (3.0 if (i % 9 == 4 and narrow) else 0.0)         # narrowed readings
                scl = (wr * dist) / (wc * dist)
                wet = (3800.0 + rng.normal(0, 300)) * scl
                moist = 13.0 + rng.normal(0, 0.6)
                dry = wet * min(1.0, (100 - moist) / (100 - 13.5))
                t += dur
                oid += 1
                tt = t0 + pd.Timedelta(seconds=t)
                rows.append({"Field": "Synthetic field", "Dataset": ds, "Product": "Synthetic wheat",
                             "Obj__Id": oid, "Time": tt.strftime("%Y-%m-%d") if date_only else
                             tt.strftime("%Y-%m-%d %H:%M:%S.%f")[:21], "Duration_s": dur, "Elevation_": 3000.0 + y / 10,
                             "Speed_mph_": spd_mph, "Distance_f": dist, "Track_deg_": 90.0 if east else 270.0,
                             "Swth_Wdth_": wc, "Moisture__": round(moist, 1), "Yld_Mass_W": wet, "Yld_Mass_D": dry,
                             "Yld_Vol_We": wet / 60.0, "Yld_Vol_Dr": dry / 60.0, "Machine": mach,
                             "Src_Fmt": "synthetic", "Crop": "wheat", "Wdth_Raw": round(wr, 4),
                             "Swath_Scl": round(scl, 6), "x": x, "y": y})
    df = pd.DataFrame(rows)
    lon = LON0 + df.x / (M_PER_DEG * np.cos(np.radians(LAT0)))
    lat = LAT0 + df.y / M_PER_DEG
    g = gpd.GeoDataFrame(df.drop(columns=["x", "y"]), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    path = os.path.join(folder, name)
    g.to_file(path, driver="ESRI Shapefile", encoding="UTF-8")
    return path


def _subset(path: str, out: str, seed: int = 5) -> str:
    import geopandas as gpd
    g = gpd.read_file(path)
    rng = np.random.default_rng(seed)
    keep = rng.random(len(g)) >= 0.05
    for _, d in g.groupby("Dataset"):
        idx = d.sort_values("Obj__Id").index.to_numpy()
        keep[idx[:10]] = False
        keep[idx[-10:]] = False
    g[keep].to_file(out, driver="ESRI Shapefile", encoding="UTF-8")
    return out


def _clean_totals(path: str, widths: bool = True, factors=None):
    import geopandas as gpd
    g = pd.DataFrame(gpd.read_file(path).drop(columns="geometry"))
    f = g.Machine.map(factors or {}).fillna(1.0).to_numpy()
    area = g.Distance_f * g.Swth_Wdth_ / 43560.0
    wet = g.Yld_Mass_W * area * f
    if not widths:
        area = area * g.Swath_Scl
    return g, float(wet.sum()), float(area.sum())


def test_isoxml_round_trip(tmp_path):
    shp = _clean_file(str(tmp_path))
    W = iw.write_clean(None, shp, str(tmp_path / "out"), new_ids=False, log=lambda m: None)
    g, wet, area = _clean_totals(shp)
    V = W["verify"]
    assert W["n_kept"] == len(g) == V["n_points"] == V["n_matched"]
    assert V["max_position_cm"] < 1.0
    assert V["max_duration_s"] <= 1e-9                         # every reading keeps its own duration
    assert V["n_late"] == 0 and V["max_late_s"] <= iw.CHAIN_TOL_MS / 1000      # and its own time
    assert V["max_moisture_pct"] == 0.0
    assert V["max_wet_lb"] < 1e-4
    assert V["max_area_rel"] < 0.01 and V["n_area_off_1pct"] == 0
    assert abs(V["totals_read"]["wet_lb"] / wet - 1) < 1e-7
    assert abs(V["totals_read"]["area_ac"] / area - 1) < 1e-4
    half = max(m["section_mm"] for m in W["machines"]) / 2 / 304.8
    assert V["max_width_ft"] <= half + 1e-9
    assert not W["warnings"]
    P = iw.read_points(os.path.join(W["path"], "TASKDATA"))
    assert len(P) == len(g) and P.groupby("Machine").size().to_dict() == g.groupby("Machine").size().to_dict()


def _own_points(taskdata_dir: str):
    """The points of a written set by the rules in the writer's docstring, with nothing of OCED's reader: every time
    log of TASKDATA.XML parsed with struct (a value holds until it is logged again); a record is a point when a
    section is on and the flow is above 0; its duration and distance are measured from the record before it (111,120
    m per degree, the longitude scaled by the cosine of that record's latitude); its width = the sections on x the
    header's width / its sections. Returns (one row per point, the shortest time between two records of a log)."""
    import math
    root = ET.parse(os.path.join(taskdata_dir, "TASKDATA.XML")).getroot()
    n_sec = {e.get("A"): sum(1 for s in d.findall("DET") if s.get("C") == "4")
             for d in root.findall("DVC") for e in d.findall("DET") if e.get("C") == "2"}
    rows, closest = [], float("inf")
    for task in root.findall("TSK"):
        for g in task.findall("TLG"):
            name = g.get("A")
            dlv = [(int(v.get("A"), 16), v.get("C"))
                   for v in ET.parse(os.path.join(taskdata_dir, name + ".XML")).getroot().findall("DLV")]
            hdr = next(el for ddi, el in dlv if ddi == 0x0057)
            at = {ddi: j for j, (ddi, el) in enumerate(dlv) if el == hdr}
            N = n_sec[hdr]
            with open(os.path.join(taskdata_dir, name + ".BIN"), "rb") as f:
                b = f.read()
            pos, val, prev = 0, {}, None
            while pos < len(b):
                ms, day, lat, lon, _, k = struct.unpack_from("<IHiiiB", b, pos)
                pos += 19
                for _ in range(k):
                    j, v = struct.unpack_from("<Bi", b, pos)
                    pos += 5
                    val[j] = v
                t = day * 86_400_000 + ms
                on = 0
                for grp in range((N + 15) // 16):
                    c = val.get(at[0x00A1 + grp], 0) & 0xFFFFFFFF
                    on += sum(1 for s in range(16) if 16 * grp + s < N and (c >> (2 * s)) & 3 == 1)
                flow = val.get(at[0x0057], 0)
                if prev is not None:
                    closest = min(closest, t - prev[0])
                    if on and flow > 0:
                        dur = (t - prev[0]) / 1000.0
                        dx = (lon - prev[2]) / 1e7 * 111_120.0 * math.cos(math.radians(prev[1] / 1e7))
                        dy = (lat - prev[1]) / 1e7 * 111_120.0
                        rows.append({"TLG": name, "t_ms": t, "dur_s": dur, "dist_m": math.hypot(dx, dy),
                                     "width_m": on * val[at[0x0046]] / N / 1000.0, "wet_kg": flow / 1e6 * dur,
                                     "moist": val.get(at[0x0063], 0) / 1e4, "lat": lat / 1e7, "lon": lon / 1e7})
                prev = (t, lat, lon)
    return pd.DataFrame(rows), closest


def test_isoxml_every_reading_at_its_own_time_checked_with_a_parser_of_its_own(tmp_path):
    """The written set parsed by this test's own few lines (not by OCED's reader): every reading of a clean file whose
    position steps are not its distances (GPS jitter, narrowed readings) is a point at its own Time, with its own
    duration, grain and area; no two records of a time log are closer than the 0.9 s under which SMS puts records
    together; the reader's read-back agrees with it point by point."""
    import geopandas as gpd
    shp = _clean_file(str(tmp_path))
    g, wet, area = _clean_totals(shp)
    xy = gpd.read_file(shp).geometry
    g = g.assign(lon=xy.x.to_numpy(), lat=xy.y.to_numpy())
    for lead_in in ("gaps", "always"):
        W = iw.write_clean(None, shp, str(tmp_path / lead_in), new_ids=False, lead_in=lead_in, log=lambda m: None)
        O, closest = _own_points(os.path.join(W["path"], "TASKDATA"))
        assert len(O) == len(g) and closest >= iw.MIN_GAP_MS
        I = pd.read_csv(W["index_csv"])
        # written at its Time: a reading behind a lead-in exactly, a monitor record within the 150 ms it may drift
        late = (I.t_written_ms - I.t_clean_ms).to_numpy()
        assert np.abs(late).max() <= iw.CHAIN_TOL_MS and W["verify"]["n_late"] == 0
        assert (late == 0).mean() > 0.9 and not any("after their Time" in w for w in W["warnings"])
        J = I.merge(O, left_on=["TLG", "t_written_ms"], right_on=["TLG", "t_ms"], how="left")
        assert J.dur_s.notna().all()
        c = g.iloc[J.src_row.to_numpy()].reset_index(drop=True)
        t_clean = ((pd.to_datetime(c.Time) - iw.EPOCH) / pd.Timedelta(milliseconds=1)).round().to_numpy()
        assert np.abs(J.t_clean_ms.to_numpy() - t_clean).max() == 0
        assert np.abs(J.dur_s - c.Duration_s).max() < 1e-9 and np.abs(J.moist - c.Moisture__).max() < 1e-4
        a_clean = (c.Distance_f * c.Swth_Wdth_ / 43560.0).to_numpy()
        a_own = (J.dist_m * J.width_m / 4046.8564224).to_numpy()
        assert np.abs(a_own / a_clean - 1).max() <= 0.0101 and abs(a_own.sum() / area - 1) < 1e-4
        w_clean = (c.Yld_Mass_W * a_clean).to_numpy()
        assert np.abs(J.wet_kg * common.LB_PER_KG / w_clean - 1).max() < 1e-6
        assert abs(O.wet_kg.sum() * common.LB_PER_KG / wet - 1) < 1e-7
        pos_m = np.hypot((J.lon - c.lon) * 111_120.0 * np.cos(np.radians(c.lat)), (J.lat - c.lat) * 111_120.0)
        assert pos_m.max() < 0.01
        # the reader's read-back (iw.read_points, what verify uses) gives the same points
        R = iw.read_points(os.path.join(W["path"], "TASKDATA")).merge(O, on=["TLG", "t_ms"], suffixes=("", "_own"))
        assert len(R) == len(O)
        assert np.abs(R.dur_s - R.dur_s_own).max() < 1e-9 and np.abs(R.dist_ft * 0.3048 - R.dist_m).max() < 1e-6
        assert np.abs(R.width_ft * 0.3048 - R.width_m).max() < 1e-9
        assert np.abs(R.wet_lb / common.LB_PER_KG - R.wet_kg).max() < 1e-9


def test_isoxml_a_time_log_without_a_full_width_reading_keeps_its_points_in_place(tmp_path):
    """SMS refers the points of a time log to the centre of the widest state the log holds. A further time log of
    a combine can hold narrowed readings only, an odd number of sections short of the header: its section offsets
    are measured from the centre of that state, so its points stay where the clean file has them."""
    one_section_ft = 254 / 304.8                                 # both made-up headers are whole sections of 254 mm
    shp = _edit(_clean_file(str(tmp_path), jitter=False, narrow=False), str(tmp_path / "alt.shp"),
                Swth_Wdth_=lambda g: np.where(g.Obj__Id % 2 == 0, g.Swth_Wdth_ - one_section_ft, g.Swth_Wdth_))
    W = iw.write_clean(None, shp, str(tmp_path / "o"), new_ids=False, lead_in="always", log=lambda m: None)
    V = W["verify"]
    assert V["time_logs"] == 4 and V["n_points"] == W["n_kept"] and {m["section_mm"] for m in W["machines"]} == {254}
    P = iw.read_points(os.path.join(W["path"], "TASKDATA"))
    widest = P.groupby("TLG").width_ft.max().round(3)
    assert sorted(set(widest - widest.round(0))) != [0.0]         # two of the four logs hold no full-width reading
    assert V["max_position_cm"] < 1.0 and V["max_width_ft"] < 1e-6


def test_isoxml_readings_closer_than_sms_keeps_apart_are_said(tmp_path):
    """Readings 0.3 s apart: SMS puts records closer than 0.9 s together, so only so many fit at their own Time in
    the time logs of a combine; the others are written later, counted in a warning, with their grain."""
    shp = _edit(_clean_file(str(tmp_path), jitter=False, narrow=False), str(tmp_path / "dense.shp"),
                Duration_s=0.3,
                Time=lambda g: (pd.Timestamp("2026-08-20 13:00:00")
                                + pd.to_timedelta(0.3 * g.groupby("Machine").cumcount(), unit="s")
                                ).dt.strftime("%Y-%m-%d %H:%M:%S.%f").str[:23])
    g, wet, area = _clean_totals(shp)
    W = iw.write_clean(None, shp, str(tmp_path / "o"), new_ids=False, log=lambda m: None)
    V = W["verify"]
    assert V["n_points"] == len(g) and abs(V["total_wet_rel"]) < 1e-7
    assert V["time_logs"] == 2 * iw.TIME_LOGS_MAX and V["n_late"] > 0 and V["max_late_s"] > 1.0
    w = [x for x in W["warnings"] if "after their Time" in x]
    assert len(w) == 2 and all("closer than 0.9 s" in x for x in w)
    O, closest = _own_points(os.path.join(W["path"], "TASKDATA"))
    assert len(O) == len(g) and closest >= iw.MIN_GAP_MS


def test_isoxml_any_subset_and_gaps(tmp_path):
    shp = _subset(_clean_file(str(tmp_path)), str(tmp_path / "subset.shp"))
    W = iw.write_clean(None, shp, str(tmp_path / "out"), new_ids=False, log=lambda m: None)
    g, wet, area = _clean_totals(shp)
    V = W["verify"]
    assert V["n_points"] == len(g) == W["n_kept"]
    assert abs(V["totals_read"]["wet_lb"] / wet - 1) < 1e-7
    assert abs(V["totals_read"]["area_ac"] / area - 1) < 1e-4
    # a reading after removed ones keeps its own duration exactly (its lead-in sits at its own duration)
    P = iw.read_points(os.path.join(W["path"], "TASKDATA"))
    I = pd.read_csv(W["index_csv"]).merge(P, on=["TLG", "record"])
    dur = g.Duration_s.to_numpy()[I.src_row.to_numpy()]
    gap = np.r_[True, np.diff(I.t_ms.to_numpy()) > 1500]
    assert gap.sum() >= 10
    assert np.abs(I.dur_s.to_numpy()[gap] - dur[gap]).max() < 1e-9


def test_isoxml_factors_and_raw_widths(tmp_path):
    shp = _clean_file(str(tmp_path))
    fac = {"SYNTH-COMBINE-A": 1.1}
    W = iw.write_clean(None, shp, str(tmp_path / "f"), factors=fac, new_ids=False, log=lambda m: None)
    g, wet, area = _clean_totals(shp, factors=fac)
    assert abs(W["verify"]["totals_read"]["wet_lb"] / wet - 1) < 1e-7
    assert any("1.1000 applied" in n for n in W["notes"])
    W2 = iw.write_clean(None, shp, str(tmp_path / "raw"), widths=False, new_ids=False, log=lambda m: None)
    g, wet, area = _clean_totals(shp, widths=False)
    assert abs(W2["verify"]["totals_read"]["area_ac"] / area - 1) < 1e-4
    P = iw.read_points(os.path.join(W2["path"], "TASKDATA"))
    I = pd.read_csv(W2["index_csv"]).merge(P, on=["TLG", "record"])
    half = max(m["section_mm"] for m in W2["machines"]) / 2 / 304.8
    assert np.abs(I.width_ft.to_numpy() - g.Wdth_Raw.to_numpy()[I.src_row.to_numpy()]).max() <= half + 1e-3
    bad = iw.write_clean(None, shp, str(tmp_path / "bad"), factors={"NO-SUCH": 1.2}, new_ids=False,
                         log=lambda m: None)
    assert any("NO-SUCH" in w for w in bad["warnings"])


def test_isoxml_structure_and_ids(tmp_path):
    shp = _clean_file(str(tmp_path))
    W = iw.write_clean(None, shp, str(tmp_path / "a"), new_ids=False, log=lambda m: None)
    T = os.path.join(W["path"], "TASKDATA")
    root = ET.parse(os.path.join(T, "TASKDATA.XML")).getroot()
    assert root.tag == "ISO11783_TaskData" and root.get("VersionMajor") == "4"
    tsks = root.findall("TSK")
    # one device per combine; its readings in two time logs (their position steps are not their distances), one
    # task per time log, the second one of a combine named '... (2)'
    assert len(root.findall("DVC")) == 2 and len(tsks) == 4 == W["verify"]["time_logs"]
    assert [len(t.findall("TLG")) for t in tsks] == [1, 1, 1, 1]
    assert [t.find("DAN").get("C") for t in tsks] == ["DVC-1", "DVC-1", "DVC-2", "DVC-2"]
    assert [t.get("B").endswith(" (2)") for t in tsks] == [False, True, False, True]
    assert [m["time_logs"] for m in W["machines"]] == [2, 2] and [len(m["tlgs"]) for m in W["machines"]] == [2, 2]
    for d in root.findall("DVC"):
        types = [e.get("C") for e in d.findall("DET")]
        assert types.count("1") == 1 and types.count("2") == 1 and types.count("7") == 1
        assert 16 <= types.count("4") <= 64
    for t in tsks:
        name = t.find("TLG").get("A")
        h = ET.parse(os.path.join(T, name + ".XML")).getroot()
        ddis = {v.get("A") for v in h.findall("DLV")}
        assert {"008D", "0057", "0063", "0042", "0046", "00A1", "008F", "00B8", "0079", "DFFE"} <= ddis
        assert h.find("PTN").attrib == {"A": "", "B": "", "C": "", "D": "1"}
        b = open(os.path.join(T, name + ".BIN"), "rb").read()
        ms, day = struct.unpack_from("<IH", b, 0)
        assert day > 16000                                    # days since 1980-01-01 (2026)
        lat_idx = [i for i, v in enumerate(h.findall("DLV")) if v.get("A") == "008F"][0]
        assert lat_idx >= 0
        tot = {v.get("A"): int(v.get("B")) for v in t.find("TIM").findall("DLV")}
        assert tot["005A"] > 0 and tot["0074"] > 0
    with zipfile.ZipFile(W["zip"]) as z:
        names = z.namelist()
    assert "TASKDATA/TASKDATA.XML" in names and "TASKDATA/LINKLIST.XML" in names
    stem = os.path.basename(W["path"])                      # the set, its zip and its index carry one name
    assert os.path.basename(W["zip"]) == stem + ".zip" and os.path.basename(W["index_csv"]) == stem + "_index.csv"
    assert all(n.startswith("TASKDATA/") for n in names) and sorted(names) == sorted(W["files_changed"])
    # deterministic without new ids, new TLG numbers and task UUIDs with them
    W2 = iw.write_clean(None, shp, str(tmp_path / "b"), new_ids=False, log=lambda m: None)
    a = open(os.path.join(T, "TLG00001.BIN"), "rb").read()
    assert a == open(os.path.join(W2["path"], "TASKDATA", "TLG00001.BIN"), "rb").read()
    W3 = iw.write_clean(None, shp, str(tmp_path / "c"), new_ids=True, log=lambda m: None)
    assert {m["tlg"] for m in W3["machines"]} != {m["tlg"] for m in W["machines"]}
    l1 = open(os.path.join(T, "LINKLIST.XML"), encoding="utf-8").read()
    l3 = open(os.path.join(W3["path"], "TASKDATA", "LINKLIST.XML"), encoding="utf-8").read()
    dev = [x.get("B") for x in ET.fromstring(l1).iter("LNK") if x.get("A").startswith("DVC")]
    dev3 = [x.get("B") for x in ET.fromstring(l3).iter("LNK") if x.get("A").startswith("DVC")]
    tsk = [x.get("B") for x in ET.fromstring(l1).iter("LNK") if x.get("A").startswith("TSK")]
    tsk3 = [x.get("B") for x in ET.fromstring(l3).iter("LNK") if x.get("A").startswith("TSK")]
    assert dev == dev3 and not set(tsk) & set(tsk3)        # the combine keeps its identity, the task is new


def test_isoxml_date_only_time(tmp_path):
    shp = _clean_file(str(tmp_path), date_only=True)
    W = iw.write_clean(None, shp, str(tmp_path / "o"), new_ids=False, log=lambda m: None)
    assert any("no time of day" in w for w in W["warnings"])
    P = iw.read_points(os.path.join(W["path"], "TASKDATA"))
    assert len(P) == W["n_kept"]
    for _, d in P.groupby("TLG"):
        assert (np.diff(d.t_ms.to_numpy()) > 0).all()


def test_isoxml_sections():
    N, ws = iw._sections(12192, 64)
    assert N * ws == 12192 and N == 48                       # a 40 ft header: 48 sections of 254 mm
    N, ws = iw._sections(11893, 64)                          # a made-up width that no section count divides exactly
    assert abs(N * ws - 11893) <= 3 and 16 <= N <= 64
    c = iw._condensed(np.array([48, 0, 1]), 48)
    assert c.shape == (3, 3) and c[0, 0] == 0x55555555 and c[1, 0] == 0
    assert bin(int(c[2, 1])).count("1") == 1                 # one section on, in the middle group


def _edit(path: str, out: str, drop=(), **set_cols) -> str:
    """A copy of a clean file without the columns `drop` and with the columns `set_cols` replaced."""
    import geopandas as gpd
    g = gpd.read_file(path)
    g = g.drop(columns=[c for c in drop if c in g.columns])
    for c, v in set_cols.items():
        g[c] = v(g) if callable(v) else v
    g.to_file(out, driver="ESRI Shapefile", encoding="UTF-8")
    return out


def test_isoxml_monitor_records_where_contiguous(tmp_path):
    """lead_in="gaps" (default): readings that follow the previous one directly, one Distance apart, are written as
    one record each at their own time; lead-ins only at the starts and after the pause; the wet mass then hardly
    depends on whether a reader times a point from the previous or to the next record. lead_in="always" puts a
    lead-in before every reading (every Duration then rests on the previous-record rule)."""
    shp = _clean_file(str(tmp_path), jitter=False, narrow=False)
    W = iw.write_clean(None, shp, str(tmp_path / "g"), new_ids=False, log=lambda m: None)
    g, wet, area = _clean_totals(shp)
    V = W["verify"]
    assert V["n_points"] == len(g)
    assert V["readings_without_lead_in"] >= 0.95 * len(g)
    assert abs(V["totals_read"]["wet_lb"] / wet - 1) < 1e-7
    assert abs(V["totals_read"]["area_ac"] / area - 1) < 2e-3 and V["max_area_rel"] <= iw.AREA_TOL + 1e-6
    assert abs(V["if_duration_to_next_record_wet_rel"]) < 0.01
    assert sum(m["trail_outs"] for m in W["machines"]) >= 4            # before the pause and after the last reading
    # a second time log of a combine holds only the first reading of each pass (it follows the last of the pass
    # before in time, not in place)
    assert V["n_late"] == 0 and sum(m["readings_in_further_logs"] for m in W["machines"]) <= 0.05 * len(g)
    A = iw.write_clean(None, shp, str(tmp_path / "a"), new_ids=False, lead_in="always", log=lambda m: None)
    assert A["verify"]["readings_without_lead_in"] == 0
    assert abs(A["verify"]["totals_read"]["wet_lb"] / wet - 1) < 1e-7
    # a lead-in before every reading: the readings of a run lie in turn in two time logs, none after its Time
    assert A["verify"]["time_logs"] == 4 and A["verify"]["n_late"] == 0 and A["verify"]["max_duration_s"] <= 1e-9
    with pytest.raises(ValueError, match="lead_in"):
        iw.write_clean(None, shp, str(tmp_path / "x"), lead_in="never", log=lambda m: None)


def test_isoxml_readings_with_no_grain_are_not_blamed_on_the_distance_rule(tmp_path):
    """E2E-1: readings written with no grain are not points when the set is read, nor is their area. The area warning
    compares the points read back with the clean file's readings with grain: it does not blame the distance between
    positions (nor offer lead-in records as the cure) for the area of the readings with no grain, the no-grain
    warning gives their area, and the result counts them (n_no_grain, area_no_grain_ac)."""
    shp = _edit(_clean_file(str(tmp_path), jitter=False, narrow=False), str(tmp_path / "nog.shp"),
                Yld_Mass_W=lambda g: g.Yld_Mass_W.where(g.Obj__Id % 4 != 0, 0.0),
                Yld_Mass_D=lambda g: g.Yld_Mass_D.where(g.Obj__Id % 4 != 0, 0.0),
                Yld_Vol_We=lambda g: g.Yld_Vol_We.where(g.Obj__Id % 4 != 0, 0.0),
                Yld_Vol_Dr=lambda g: g.Yld_Vol_Dr.where(g.Obj__Id % 4 != 0, 0.0))
    g, _, area = _clean_totals(shp)
    zero = (g.Yld_Mass_W <= 0).to_numpy()
    a0 = float((g.Distance_f * g.Swth_Wdth_ / 43560.0)[zero].sum())
    for lead_in in ("always", "gaps"):
        W = iw.write_clean(None, shp, str(tmp_path / lead_in), new_ids=False, lead_in=lead_in, log=lambda m: None)
        V = W["verify"]
        if lead_in == "always":                         # the total is exact: nothing left to blame on distances
            assert not any("step between positions" in w or "lead_in='always' keeps" in w for w in W["warnings"]), \
                W["warnings"]
        area_w = [w for w in W["warnings"] if w.startswith("the total area")]
        assert all(f"by {100 * V['total_area_rel_points']:+.2f} %" in w for w in area_w), area_w
        assert any(w.startswith(f"{int(zero.sum()):,} readings with no grain ({a0:,.2f} ac)") for w in W["warnings"])
        assert V["n_points"] == len(g) - zero.sum() == W["n_kept"] - V["n_no_grain"]
        assert V["area_no_grain_ac"] == pytest.approx(a0, rel=1e-9)
        assert abs(V["total_area_rel"]) > 0.1                              # the written set minus the no-grain area
        assert abs(V["total_area_rel_points"]) < 2e-3


def test_isoxml_date_only_datasets_of_one_combine_do_not_overlap(tmp_path):
    shp = _clean_file(str(tmp_path), date_only=True)
    W = iw.write_clean(None, shp, str(tmp_path / "o"), new_ids=False, log=lambda m: None)
    I = pd.read_csv(W["index_csv"])
    for _, d in I.groupby("Machine"):
        spans = sorted((x.t_written_ms.min(), x.t_written_ms.max()) for _, x in d.groupby("Dataset"))
        assert len(spans) == 2
        assert all(b0 > a1 for (_, a1), (b0, _) in zip(spans, spans[1:]))     # one dataset after the other


def test_isoxml_root_order_and_task_controller(tmp_path):
    shp = _clean_file(str(tmp_path))
    W = iw.write_clean(None, shp, str(tmp_path / "o"), new_ids=False, log=lambda m: None)
    root = ET.parse(os.path.join(W["path"], "TASKDATA", "TASKDATA.XML")).getroot()
    tags = [c.tag for c in root]
    order = [tags.index(t) for t in ("AFE", "CPC", "CTP", "CTR", "DVC", "FRM", "PDT", "PFD", "TSK")]
    assert order == sorted(order), tags
    assert root.get("TaskControllerManufacturer") == "OCED" and root.get("TaskControllerVersion") is not None
    assert any("not yet tested in SMS" in n for n in W["notes"]) and W["sms_tested"] is False


def test_isoxml_columns_missing(tmp_path):
    shp = _clean_file(str(tmp_path))
    g, wet, area = _clean_totals(shp)
    q = lambda m: None  # noqa: E731
    # no Distance_f: Distance = Speed x Duration
    a = iw.write_clean(None, _edit(shp, str(tmp_path / "nodist.shp"), drop=("Distance_f",)), str(tmp_path / "a"),
                       new_ids=False, log=q)
    assert any("Speed x Duration" in n for n in a["notes"]) and a["verify"]["n_points"] == len(g)
    # no Yld_Mass_W: wet = Yld_Vol_We x the test weight (here from the crop table)
    b = iw.write_clean(None, _edit(shp, str(tmp_path / "nowet.shp"), drop=("Yld_Mass_W",)), str(tmp_path / "b"),
                       new_ids=False, log=q)
    assert any("Yld_Vol_We x test weight" in n for n in b["notes"])
    assert b["test_weight_lb_bu"] == 60.0 and any("crop table (wheat)" in n for n in b["notes"])
    assert abs(b["verify"]["totals_read"]["wet_lb"] / wet - 1) < 1e-6
    # no wet column at all: rebuilt from the dry yield (warned); barley from the crop table
    c = iw.write_clean(None, _edit(shp, str(tmp_path / "nowet2.shp"), drop=("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D"),
                                   Crop="barley"), str(tmp_path / "c"), new_ids=False, log=q)
    assert any("rebuilt from the DRY yield" in w for w in c["warnings"])
    assert (c["test_weight_lb_bu"], c["std_moisture_pct"]) == tuple(common.CROPS["barley"][:2])
    # nothing to say what the crop is: the fallback constants, warned
    d = iw.write_clean(None, _edit(shp, str(tmp_path / "nocrop.shp"),
                                   drop=("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D", "Crop")), str(tmp_path / "d"),
                       new_ids=False, log=q)
    assert d["test_weight_lb_bu"] == 60.0 and d["std_moisture_pct"] == 13.5
    assert any("60 lb/bu written" in w for w in d["warnings"]) and any("13.5 % written" in w for w in d["warnings"])
    # the decoder's options come before the crop table
    e = iw.write_clean({"options": {"test_weight_lb_bu": 57.0, "std_moisture_pct": 12.5}},
                       _edit(shp, str(tmp_path / "opt.shp"), drop=("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D", "Crop")),
                       str(tmp_path / "e"), new_ids=False, log=q)
    assert e["test_weight_lb_bu"] == 57.0 and e["std_moisture_pct"] == 12.5


def test_isoxml_time_zone_and_no_time(tmp_path):
    shp = _clean_file(str(tmp_path))
    q = lambda m: None  # noqa: E731
    tz = _edit(shp, str(tmp_path / "tz.shp"),
               Time=lambda g: (pd.to_datetime(g["Time"]).dt.strftime("%Y-%m-%dT%H:%M:%S.%f").str[:23] + "-06:00"))
    W = iw.write_clean(None, tz, str(tmp_path / "a"), new_ids=False, log=q)
    I = pd.read_csv(W["index_csv"]).sort_values("t_written_ms")
    first = iw.EPOCH + pd.Timedelta(milliseconds=int(I.t_written_ms.iat[0]))
    assert first.hour == 19                                     # 13:00 at UTC-6 written as 19:00 UTC
    nt = iw.write_clean(None, _edit(shp, str(tmp_path / "nt.shp"), drop=("Time",)), str(tmp_path / "b"),
                        new_ids=False, log=q)
    assert any("no Time column" in w for w in nt["warnings"]) and nt["verify"]["n_points"] == nt["n_kept"]
    I = pd.read_csv(nt["index_csv"])
    t0 = iw.EPOCH + pd.Timedelta(milliseconds=int(I.t_written_ms.min()))
    assert t0.year == 2000 and t0.hour == 12


def test_isoxml_refusals_and_elevation(tmp_path):
    shp = _clean_file(str(tmp_path))
    q = lambda m: None  # noqa: E731
    assert iw.can_write(None) == (True, "")
    import geopandas as gpd
    empty = str(tmp_path / "e.shp")
    gpd.read_file(shp).iloc[:0].to_file(empty, driver="ESRI Shapefile")
    with pytest.raises(iw.IsoxmlWriteError, match="no readings"):
        iw.write_clean(None, empty, str(tmp_path / "o"), log=q)
    inp = tmp_path / "input"
    inp.mkdir()
    with pytest.raises(ValueError, match="inside the raw input"):
        iw.write_clean({"input_root": str(inp)}, shp, str(inp / "out"), log=q)
    ne = _edit(shp, str(tmp_path / "ne.shp"),
               Elevation_=lambda g: np.where(np.arange(len(g)) % 10 == 3, np.nan, g["Elevation_"]))
    W = iw.write_clean(None, ne, str(tmp_path / "el"), new_ids=False, log=q)
    w = [x for x in W["warnings"] if "without an elevation" in x]
    assert w and "nearest elevation" in w[0]
    P = iw.read_points(os.path.join(W["path"], "TASKDATA"))
    assert P.elev_ft.min() > 2900                               # no 0 written


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
