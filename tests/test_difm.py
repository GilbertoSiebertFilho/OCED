# -*- coding: utf-8 -*-
"""The clean data as a shapefile for DIFM (engine/difm.py). A harvest: the layout of an SMS shapefile export (field
names, order, dBASE types and widths of the layout DIFM was seen to read, numbers with 6 decimals, real dBASE dates),
the values of the clean file (numbers to 6 decimals), Y_Offset_f carried or 0, the date of each reading (an export's
own dBASE date copied, a time of
day taken to its day: UTC times in this computer's clock time), the zip and its members, WGS 84 with the ESRI .prj. A
planter / sprayer file: its own columns with its dates as dBASE dates. The app writing it next to the clean shapefile
and offering it in step 4, its warnings after the work is opened again, none for a cleaning to clean again, a failed
write tried again on request, the clean shapefile left as it was, and the path checks. The yield of a harvest's
file: 3-sigma only (the monitor's) or, when the cleaning adjusted it (a combine factor applied, the grower's weight
used to adjust), the adjusted one under its own name (<clean>_adjusted_DIFM.zip: Yld_Vol_Dr = the column the
cleaning names, the other yield fields by the same factor per reading), the default of the question step 4 asks; no
question without an adjustment; the choice kept by the cleaning record. Synthetic data only (tests/synthetic.py and
small files made here).

    python -m pytest -q tests/test_difm.py
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import shutil
import struct
import sys
import types
import zipfile
from decimal import Decimal

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import applied3s as a3  # noqa: E402
from tests.synthetic import make_applied, make_field, make_two_combines  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
LAYOUT = [("Field", "C"), ("Dataset", "C"), ("Product", "C"), ("Obj__Id", "N"), ("Distance_f", "N"),
          ("Track_deg_", "N"), ("Duration_s", "N"), ("Elevation_", "N"), ("Time", "D"), ("Swth_Wdth_", "N"),
          ("Y_Offset_f", "N"), ("Moisture__", "N"), ("Yld_Mass_W", "N"), ("Yld_Vol_We", "N"), ("Yld_Mass_D", "N"),
          ("Yld_Vol_Dr", "N"), ("Speed_mph_", "N"), ("Date", "D")]
# the dBASE descriptors (name, type, width, decimals): the names, types and widths of the layout DIFM was seen to read
# and map, the numbers with 6 decimals
TESTED = [("Field", "C", 80, 0), ("Dataset", "C", 80, 0), ("Product", "C", 80, 0), ("Obj__Id", "N", 18, 0),
          ("Distance_f", "N", 24, 6), ("Track_deg_", "N", 24, 6), ("Duration_s", "N", 24, 6),
          ("Elevation_", "N", 24, 6), ("Time", "D", 8, 0), ("Swth_Wdth_", "N", 24, 6), ("Y_Offset_f", "N", 24, 6),
          ("Moisture__", "N", 24, 6), ("Yld_Mass_W", "N", 24, 6), ("Yld_Vol_We", "N", 24, 6),
          ("Yld_Mass_D", "N", 24, 6), ("Yld_Vol_Dr", "N", 24, 6), ("Speed_mph_", "N", 24, 6), ("Date", "D", 8, 0)]
HALF = 5.01e-7                            # half a unit of the 6th decimal (and the float noise of the comparison)
ESRI_PRJ = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
            'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
# the clean file's column of each DIFM field when the clean file has SMS names
SAME_NAME = [f for f, t in LAYOUT if t != "D" and f != "Y_Offset_f"]
NUM_FIELDS = [f for f, t in LAYOUT if t == "N" and f != "Y_Offset_f"]


def _difm():
    from engine import difm                     # here, so that each test fails on its own where the module is missing
    return difm


def _dbf(b: bytes):
    """(n, [(name, type, width, decimals)], records n x rlen) of .dbf bytes."""
    n, hlen, rlen = struct.unpack("<IHH", b[4:12])
    fields, i = [], 32
    while b[i] != 0x0D:
        d = b[i:i + 32]
        fields.append((d[:11].split(b"\0")[0].decode("ascii"), chr(d[11]), d[16], d[17]))
        i += 32
    assert hlen == i + 1 and b[-1:] == b"\x1A" and len(b) == hlen + n * rlen + 1
    return n, fields, np.frombuffer(b, np.uint8, count=n * rlen, offset=hlen).reshape(n, rlen)


def _cells(fields, recs, name) -> list:
    off = 1
    for f, _, w, _ in fields:
        if f == name:
            return [bytes(r) for r in recs[:, off:off + w]]
        off += w
    raise KeyError(name)


def _parts(zp):
    with zipfile.ZipFile(zp) as z:
        names = [i.filename for i in z.infolist()]
        return names, {os.path.splitext(n)[1]: z.read(n) for n in names}


def _clean_bytes(shp):
    base = os.path.splitext(shp)[0]
    return {e: open(base + e, "rb").read() for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")
            if os.path.exists(base + e)}


def _dec(cell: bytes):
    """The decimal value of a dBASE N cell (None when blank)."""
    s = cell.strip()
    return Decimal(s.decode("ascii")) if s else None


def _dec6(cell: bytes):
    """The decimal value of a dBASE N cell rounded to 6 decimals, half to even (None when blank)."""
    v = _dec(cell)
    return None if v is None else v.quantize(Decimal("0.000001"), rounding="ROUND_HALF_EVEN")


def _write_dbf(path, desc, cols: dict, n: int):
    """A .dbf with the descriptors `desc` [(name, type, width, decimals)]; cols {name: values} (numbers for N, text
    for C, 'YYYYMMDD' or '' for D); a value of None is a blank cell."""
    hlen, rlen = 32 + 32 * len(desc) + 1, 1 + sum(w for _, _, w, _ in desc)
    head = bytearray(32)
    head[0], head[1:4] = 0x03, bytes([126, 9, 30])
    struct.pack_into("<IHH", head, 4, n, hlen, rlen)
    out = [bytes(head)]
    for name, t, w, d in desc:
        out.append(name.encode("ascii").ljust(11, b"\0") + t.encode("ascii") + b"\0" * 4 + bytes([w, d]) + b"\0" * 14)
    out.append(b"\x0D")
    for i in range(n):
        rec = [b" "]
        for name, t, w, d in desc:
            v = cols[name][i]
            if v is None or (isinstance(v, float) and not np.isfinite(v)):
                s = ""
            elif t == "N":
                s = f"{float(v):.{d}f}" if d else str(int(round(float(v))))
            else:
                s = str(v)
            assert len(s) <= w, (name, s)
            rec.append((s.rjust(w) if t == "N" else s.ljust(w)).encode("ascii"))
        out.append(b"".join(rec))
    out.append(b"\x1A")
    with open(path, "wb") as fh:
        fh.write(b"".join(out))


def _point_set(path, lon, lat, desc, cols: dict):
    """A point shapefile in WGS 84 whose .dbf has exactly the descriptors `desc` (an SMS export's dBASE dates and
    widths, which GDAL does not write)."""
    import geopandas as gpd
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gpd.GeoDataFrame({"k": np.arange(len(lon))}, geometry=gpd.points_from_xy(lon, lat),
                     crs="EPSG:4326").to_file(path, engine="pyogrio")
    _write_dbf(os.path.splitext(path)[0] + ".dbf", desc, cols, len(lon))
    return path


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("difm_field")))


@pytest.fixture(scope="module")
def cleaned(field, tmp_path_factory):
    """The synthetic export cleaned with the SMS 3-sigma method and the boundary (a run that writes Harv_Day)."""
    wd = er.new_workdir(str(tmp_path_factory.mktemp("difm_ws")), "syn")
    cand = er.open_input([field["shp"]], wd)[0]
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": field["boundary"], "buffer_m": 0.01, "clip_output": True, "feature": None}}
    R = er.clean(cand["path"], str(tmp_path_factory.mktemp("difm_out")), S, log=lambda m: None)
    return R


def _days(s) -> list:
    return [("" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d")) for v in s]


def _clean_like(path, df: pd.DataFrame, lon, lat, crs="EPSG:4326"):
    """A small point shapefile laid out as a clean file (SMS names and OCED's columns)."""
    import geopandas as gpd
    g = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    if crs != "EPSG:4326":
        g = g.to_crs(crs)
    g.to_file(path, engine="pyogrio")
    return path


def _small(n=6, **over):
    base = {"Field": ["Synthetic 1"] * n, "Dataset": ["26/09/14-20:00:00"] * n, "Product": ["Wheat"] * n,
            "Obj__Id": np.arange(1, n + 1), "Time": ["2026-09-15 01:59:58"] * n, "Duration_s": [1.0] * n,
            "Elevation_": [3400.25] * n, "Speed_mph_": [4.5] * n, "Distance_f": [6.6] * n, "Track_deg_": [90.0] * n,
            "Swth_Wdth_": [30.0] * n, "Moisture__": [14.2] * n, "Yld_Mass_W": [3900.5] * n,
            "Yld_Mass_D": [3890.25] * n, "Yld_Vol_We": [65.0083] * n, "Yld_Vol_Dr": [64.8375] * n,
            "Machine": ["COMBINE-A"] * n}
    base.update(over)
    return pd.DataFrame(base)


def _sms_export_like(folder, field, own_days, desc_c=254, desc_n=(15, 4), name="Synthetic_sms_export.shp"):
    """The synthetic field as an SMS point export writes it: Time and Date dBASE dates (the reading's own date,
    `own_days`), C(254) / N(15,4) fields (or the widths given), the dataset named by the day the harvest started."""
    df = field["df"]
    n = len(df)
    from tests.synthetic import _lonlat
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    w, d = desc_n
    desc = [("Field", "C", desc_c, 0), ("Dataset", "C", desc_c, 0), ("Product", "C", desc_c, 0),
            ("Obj__Id", "N", w, d), ("Distance_f", "N", w, d), ("Track_deg_", "N", w, d), ("Duration_s", "N", w, d),
            ("Elevation_", "N", w, d), ("Time", "D", 8, 0), ("Swth_Wdth_", "N", w, d), ("Y_Offset_f", "N", w, d),
            ("Moisture__", "N", w, d), ("Yld_Mass_W", "N", w, d), ("Yld_Vol_We", "N", w, d),
            ("Yld_Mass_D", "N", w, d), ("Yld_Vol_Dr", "N", w, d), ("Speed_mph_", "N", w, d), ("Date", "D", 8, 0)]
    cols = {c: df[c].to_numpy() for c in ("Field", "Dataset", "Product", "Obj__Id", "Distance_f", "Track_deg_",
                                          "Duration_s", "Elevation_", "Swth_Wdth_", "Moisture__", "Yld_Mass_W",
                                          "Yld_Vol_We", "Yld_Mass_D", "Yld_Vol_Dr", "Speed_mph_")}
    cols["Y_Offset_f"] = np.zeros(n)
    cols["Time"] = cols["Date"] = list(own_days)
    return _point_set(os.path.join(folder, name), lon, lat, desc, cols)


# ------------------------------------------------------------------------------------------------ the engine
def test_layout_names_order_and_dbase_types(cleaned, tmp_path):
    difm = _difm()
    assert difm.ZIP_SUFFIX == "_DIFM.zip" and [f for f, _ in difm.FIELDS] == [f for f, _ in LAYOUT]
    clean = cleaned["files"]["difm_ready_shp"]
    W = difm.write_zip(clean, str(tmp_path / "syn_sms3s_clean_DIFM.zip"), columns=cleaned["columns"])
    names, P = _parts(W["zip"])
    assert names == [f"syn_sms3s_clean_DIFM{e}" for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    n, fields, _ = _dbf(P[".dbf"])
    assert [(f, t) for f, t, _, _ in fields] == LAYOUT                       # names, order, dBASE types
    assert fields == TESTED                                                  # and the widths DIFM read
    assert n == cleaned["n_kept"] == W["n"]
    assert P[".prj"].decode("ascii") == ESRI_PRJ and P[".cpg"] == b"UTF-8"
    vs = f"/vsizip/{W['zip']}/syn_sms3s_clean_DIFM.shp"
    info = pyogrio.read_info(vs)
    assert list(info["fields"]) == [f for f, _ in LAYOUT]
    dt_ = dict(zip(info["fields"], info["dtypes"]))
    assert str(dt_["Time"]).startswith("datetime64") and str(dt_["Date"]).startswith("datetime64")
    assert info["crs"] == "EPSG:4326" and info["geometry_type"] == "Point" and info["features"] == n


def test_values_are_the_clean_file_s(cleaned, tmp_path):
    difm = _difm()
    clean = cleaned["files"]["difm_ready_shp"]
    W = difm.write_zip(clean, str(tmp_path / "a_DIFM.zip"), columns=cleaned["columns"])
    _, P = _parts(W["zip"])
    C = _clean_bytes(clean)
    nc, fc, rc = _dbf(C[".dbf"])
    nd, fd, rd = _dbf(P[".dbf"])
    assert nc == nd and fd == TESTED
    wide = 0
    for f in SAME_NAME:
        t = [x for x in fc if x[0] == f][0]
        if t[1] == "C":                                     # text: as it is
            assert [c.strip() for c in _cells(fd, rd, f)] == [c.strip() for c in _cells(fc, rc, f)], f
            continue
        if f == "Obj__Id":                                  # the record's id: the same number
            assert [_dec(c) for c in _cells(fd, rd, f)] == [_dec(c) for c in _cells(fc, rc, f)], f
            continue
        wide += t[3] > 6                                    # a number: the clean file's, to 6 decimals (half to even)
        got = _cells(fd, rd, f)
        assert [_dec(c) for c in got] == [_dec6(c) for c in _cells(fc, rc, f)], f
        assert all(len(c.strip().split(b".")[1]) == 6 for c in got if c.strip()), f
    assert wide > 5                                         # the clean file holds these numbers with more decimals
    assert P[".shp"] == C[".shp"] and P[".shx"] == C[".shx"]   # the same points at the same positions
    a = pyogrio.read_dataframe(clean)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/a_DIFM.shp")
    for f in SAME_NAME:
        if not pd.api.types.is_numeric_dtype(a[f]):
            assert a[f].equals(b[f]), f
        else:
            assert np.abs(a[f].to_numpy(float) - b[f].to_numpy(float)).max() <= HALF, f
    assert np.array_equal(a.geometry.x, b.geometry.x) and np.array_equal(a.geometry.y, b.geometry.y)
    assert (b["Y_Offset_f"] == 0).all()                    # the synthetic export has no lateral offset
    assert "Y_Offset_f = 0: the clean file has no lateral offset" in W["notes"]
    # the clean file itself is not touched
    assert _clean_bytes(clean) == C


def test_dates_are_the_day_of_each_reading(cleaned, tmp_path):
    """Local times (no time basis said): the calendar day of each reading's own time, which is Harv_Day too."""
    difm = _difm()
    clean = cleaned["files"]["difm_ready_shp"]
    W = difm.write_zip(clean, str(tmp_path / "d_DIFM.zip"), columns=cleaned["columns"])
    a = pyogrio.read_dataframe(clean, read_geometry=False)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/d_DIFM.shp", read_geometry=False)
    assert W["days"] == {"the day of the reading's time (Time)": len(a)} and W["n_no_day"] == 0
    day = pd.to_datetime(a["Time"]).dt.date
    assert (pd.to_datetime(b["Time"]).dt.date == day).all() and (pd.to_datetime(b["Date"]).dt.date == day).all()
    assert (day == pd.to_datetime(a["Harv_Day"]).dt.date).all()


def test_an_export_s_own_dates_are_copied_not_its_dataset_date(field, tmp_path):
    """An SMS point export (Time and Date are dBASE dates, the reading's own date; no time of day) whose harvest went
    past midnight: the cleaning's Harv_Day is the date in the dataset name for every reading, but DIFM's Time and
    Date are each reading's own date, copied byte for byte from the clean file. Its C(254) / N(15,4) fields come in
    the widths of the layout DIFM read, with the same decimal values."""
    difm = _difm()
    n = field["n"]
    own = ["20260914"] * (n // 2) + ["20260915"] * (n - n // 2)
    shp = _sms_export_like(str(tmp_path / "data"), field, own)
    wd = er.new_workdir(str(tmp_path / "ws"), "exp")
    cand = er.open_input([shp], wd)[0]
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "exp",
         "moisture": {"standard_pct": 14.5}}                       # a standard moisture given, as the app does
    R = er.clean(cand["path"], str(tmp_path / "out"), S, log=lambda m: None)
    clean = R["files"]["difm_ready_shp"]
    a = pyogrio.read_dataframe(clean, read_geometry=False)
    assert set(a["Harv_Day"]) == {"2026-09-14"}                     # the dataset name's date: the trap
    W = difm.write_zip(clean, str(tmp_path / "exp_DIFM.zip"), columns=R["columns"])
    _, P = _parts(W["zip"])
    nc, fc, rc = _dbf(open(clean[:-4] + ".dbf", "rb").read())
    nd, fd, rd = _dbf(P[".dbf"])
    assert ("Time", "D", 8, 0) in fc and nc == nd
    assert _cells(fd, rd, "Time") == _cells(fc, rc, "Time") == _cells(fd, rd, "Date")
    assert sum(c == b"20260915" for c in _cells(fd, rd, "Time")) > 0
    assert W["days"] == {"the reading's own date (Time, a dBASE date of the clean file)": nd}
    # the widths of the layout DIFM read, every value the same decimal number (blank stays blank)
    assert fd == TESTED
    for f in NUM_FIELDS:
        assert [_dec(c) for c in _cells(fd, rd, f)] == [_dec(c) for c in _cells(fc, rc, f)], f
    for f in ("Field", "Dataset", "Product"):
        assert [c.rstrip() for c in _cells(fd, rd, f)] == [c.rstrip() for c in _cells(fc, rc, f)], f
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/exp_DIFM.shp", read_geometry=False)
    for f in NUM_FIELDS:
        assert np.array_equal(b[f].to_numpy(float), a[f].to_numpy(float), equal_nan=True), f


def test_a_blank_own_date_falls_back_to_harv_day_then_the_dataset_name(tmp_path):
    difm = _difm()
    n = 4
    desc = [("Dataset", "C", 40, 0), ("Time", "D", 8, 0), ("Yld_Vol_Dr", "N", 15, 4), ("Harv_Day", "C", 10, 0)]
    cols = {"Dataset": ["26/09/14-20:00:00"] * n, "Time": ["20260915", "", "", "20260916"],
            "Yld_Vol_Dr": [60.0] * n, "Harv_Day": ["2026-09-14", "2026-09-14", "", "2026-09-14"]}
    shp = _point_set(str(tmp_path / "b_sms3s_clean.shp"), np.full(n, -114.1), np.full(n, 51.8), desc, cols)
    W = difm.write_zip(shp)
    _, P = _parts(W["zip"])
    _, fd, rd = _dbf(P[".dbf"])
    assert _cells(fd, rd, "Time") == [b"20260915", b"20260914", b"20260914", b"20260916"]
    assert W["days"] == {"the reading's own date (Time, a dBASE date of the clean file)": 2, "Harv_Day": 1,
                         "the date in the dataset name (Dataset)": 1}


def test_utc_readings_after_local_midnight_take_this_computer_s_clock_day(tmp_path, monkeypatch):
    """John Deere readings (Src_Fmt jd_jdl: UTC times) at 06:30 UTC: the cleaning's Harv_Day (solar time at the
    longitude, UTC-8 here) puts them on the evening before; SMS shows them in the computer's clock time (UTC-6 in a
    Mountain summer): the DIFM file takes that clock's day, per reading (a clock that changes its offset in between
    gives each reading its own), unless the decoder gave a time-zone offset."""
    difm = _difm()
    n = 4
    times = ["2026-09-15 06:30:00", "2026-09-15 06:31:00", "2026-11-02 06:30:00", "2026-11-02 06:31:00"]
    df = _small(n, Time=times, Src_Fmt=["jd_jdl"] * n, Harv_Day=["2026-09-14"] * 2 + ["2026-11-01"] * 2)
    shp = _clean_like(str(tmp_path / "u_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    cut = pd.Timestamp("2026-11-01 08:00:00").value / 1e9           # the end of daylight time, in UTC seconds
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0 if s < cut else -7.0)
    W = difm.write_zip(shp)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/u_sms3s_clean_DIFM.shp", read_geometry=False)
    assert _days(b["Time"]) == _days(b["Date"]) == ["2026-09-15", "2026-09-15", "2026-11-01", "2026-11-01"]
    assert W["days"] == {"the day of the reading's time (Time, UTC in this computer's clock time: UTC -6 h, -7 h)": n}
    # the decoder's own time-zone offset wins over the clock
    W2 = difm.write_zip(shp, str(tmp_path / "tz_DIFM.zip"), source={"time_basis": "UTC", "tz_offset_h": -7})
    b2 = pyogrio.read_dataframe(f"/vsizip/{W2['zip']}/tz_DIFM.shp", read_geometry=False)
    assert _days(b2["Time"]) == ["2026-09-14", "2026-09-14", "2026-11-01", "2026-11-01"]
    # local times keep their own day
    W3 = difm.write_zip(shp, str(tmp_path / "loc_DIFM.zip"), source={"time_basis": "local"})
    b3 = pyogrio.read_dataframe(f"/vsizip/{W3['zip']}/loc_DIFM.shp", read_geometry=False)
    assert _days(b3["Time"]) == ["2026-09-15", "2026-09-15", "2026-11-02", "2026-11-02"]


def test_utc_times_with_blank_cells_still_take_the_clock_day(tmp_path, monkeypatch):
    """More than 1 % of the time cells blank (the cleaning's parser then calls the column 'not times'): the cells that
    do parse are times of day in UTC, so they still take this computer's clock day; the blank ones fall back to
    Harv_Day."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    n = 50
    times = ["2026-09-15 05:30:%02d" % i for i in range(n)]
    times[7] = times[31] = ""
    df = _small(n, Time=times, Src_Fmt=["jd_jdl"] * n, Harv_Day=["2026-09-14"] * n)
    shp = _clean_like(str(tmp_path / "b_sms3s_clean.shp"), df, np.full(n, -114.1) + 1e-5 * np.arange(n), np.full(n, 51.8))
    W = difm.write_zip(shp)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/b_sms3s_clean_DIFM.shp", read_geometry=False)
    assert _days(b["Time"]) == _days(b["Date"]) == ["2026-09-14"] * n
    assert W["days"] == {"the day of the reading's time (Time, UTC in this computer's clock time: UTC -6 h)": n - 2,
                         "Harv_Day": 2}


def test_the_clock_is_this_computer_s():
    """clock_utc_offset_h: the offset of this computer's local time at that instant (what SMS shows UTC logs in)."""
    difm = _difm()
    for s in (pd.Timestamp("2026-07-01 12:00:00").value / 1e9, pd.Timestamp("2026-12-01 12:00:00").value / 1e9):
        local = dt.datetime.fromtimestamp(s)
        utc = dt.datetime.fromtimestamp(s, dt.timezone.utc).replace(tzinfo=None)
        assert difm.clock_utc_offset_h(s) == (local - utc).total_seconds() / 3600


def test_y_offset_carried(tmp_path, monkeypatch):
    """A clean file of John Deere Gen4 readings (Src_Fmt jd_jdl: UTC times) with no Harv_Day: Y_Offset_f carried
    byte for byte; 01:59:58 UTC is the evening before in a UTC-6 clock."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    n = 6
    df = _small(n, Y_Offset_f=[0.0, 1.25, -2.5, 3.125, 0.0, 7.0], Src_Fmt=["jd_jdl"] * n)
    lon, lat = np.full(n, -114.1) + 1e-4 * np.arange(n), np.full(n, 51.8)
    shp = _clean_like(str(tmp_path / "gen4_sms3s_clean.shp"), df, lon, lat)
    W = difm.write_zip(shp)
    assert W["zip"] == str(tmp_path / "gen4_sms3s_clean_DIFM.zip") == difm.zip_path_for(shp)
    _, P = _parts(W["zip"])
    nc, fc, rc = _dbf(open(shp[:-4] + ".dbf", "rb").read())
    _, fd, rd = _dbf(P[".dbf"])
    assert [_dec(c) for c in _cells(fd, rd, "Y_Offset_f")] == [_dec(c) for c in _cells(fc, rc, "Y_Offset_f")]
    assert W["columns"]["Y_Offset_f"] == "Y_Offset_f"
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/gen4_sms3s_clean_DIFM.shp", read_geometry=False)
    assert list(b["Y_Offset_f"]) == [0.0, 1.25, -2.5, 3.125, 0.0, 7.0]
    assert _days(b["Time"]) == _days(b["Date"]) == ["2026-09-14"] * n


def test_harv_day_then_the_dataset_date_when_there_is_no_time(tmp_path):
    difm = _difm()
    n = 4
    df = _small(n, Harv_Day=["2026-09-11", "2026-09-11", "", ""], Time=["", "", "", ""])
    shp = _clean_like(str(tmp_path / "h_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    W = difm.write_zip(shp)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/h_sms3s_clean_DIFM.shp", read_geometry=False)
    assert _days(b["Date"]) == ["2026-09-11", "2026-09-11", "2026-09-14", "2026-09-14"]
    assert W["days"] == {"Harv_Day": 2, "the date in the dataset name (Dataset)": 2}
    # no day anywhere: empty dates, said in the warnings
    df = _small(2, Time=["", ""], Dataset=["load", "load"])
    shp = _clean_like(str(tmp_path / "x_sms3s_clean.shp"), df, np.full(2, -114.1), np.full(2, 51.8))
    W = difm.write_zip(shp)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/x_sms3s_clean_DIFM.shp", read_geometry=False)
    assert b["Time"].isna().all() and W["n_no_day"] == 2 and "have no harvest day" in W["warnings"][0]


def test_narrow_widths_take_the_tested_widths_with_the_same_values(tmp_path):
    """A clean file with narrow fields (C(3), N(5,0), N(10,6) ...): the DIFM file has the descriptors of the layout
    DIFM read and every value is the same decimal number; a value that does not fit them exactly keeps its field's
    own width (said in the notes)."""
    difm = _difm()
    n = 3
    narrow = [("Field", "C", 3, 0), ("Dataset", "C", 33, 0), ("Product", "C", 14, 0), ("Obj__Id", "N", 5, 0),
              ("Swth_Wdth_", "N", 9, 6), ("Moisture__", "N", 9, 6), ("Yld_Mass_D", "N", 12, 6),
              ("Yld_Vol_We", "N", 10, 6), ("Y_Offset_f", "N", 11, 6), ("Distance_f", "N", 10, 6),
              ("Duration_s", "N", 9, 6), ("Track_deg_", "N", 10, 6), ("Time", "D", 8, 0), ("Elevation_", "N", 11, 6),
              ("Yld_Mass_W", "N", 12, 6), ("Yld_Vol_Dr", "N", 10, 6), ("Speed_mph_", "N", 9, 6), ("Date", "D", 8, 0)]
    cols = {"Field": ["F1", "F1", "F1"], "Dataset": ["26/09/14-13:00:00 (1)"] * n, "Product": ["Wheat"] * n,
            "Obj__Id": [1, 2, 3], "Swth_Wdth_": [30.0, 29.5, None], "Moisture__": [14.25, 13.0, 12.5],
            "Yld_Mass_D": [3600.123456, 3700.0, 3800.5], "Yld_Vol_We": [61.5, 62.0, -0.25],
            "Y_Offset_f": [0.0, -1.5, 2.25], "Distance_f": [6.6, 6.7, 6.8], "Duration_s": [1.0, 1.0, 1.0],
            "Track_deg_": [90.0, 270.0, 90.5], "Time": ["20260914", "20260914", "20260915"],
            "Elevation_": [3400.5, 3401.0, 3401.25], "Yld_Mass_W": [3700.0, 3800.0, 3900.0],
            "Yld_Vol_Dr": [60.002058, 61.666667, 63.341667], "Speed_mph_": [4.5, 4.6, 4.7],
            "Date": ["20260914", "20260914", "20260915"]}
    shp = _point_set(str(tmp_path / "k_sms3s_clean.shp"), np.full(n, -114.1), np.full(n, 51.8), narrow, cols)
    W = difm.write_zip(shp)
    _, P = _parts(W["zip"])
    _, fc, rc = _dbf(open(shp[:-4] + ".dbf", "rb").read())
    _, fd, rd = _dbf(P[".dbf"])
    assert fd == TESTED
    for f in NUM_FIELDS + ["Y_Offset_f"]:
        assert [_dec(c) for c in _cells(fd, rd, f)] == [_dec(c) for c in _cells(fc, rc, f)], f
    assert _cells(fd, rd, "Obj__Id") == [b"1".rjust(18), b"2".rjust(18), b"3".rjust(18)]
    assert _cells(fd, rd, "Yld_Mass_D")[0] == b"3600.123456".rjust(24)
    assert _cells(fd, rd, "Swth_Wdth_")[2] == b" " * 24
    assert _cells(fd, rd, "Time") == _cells(fc, rc, "Time")
    # a text longer than 80 characters keeps its field's own width; a number with 9 digits before the point fits
    wide = [("Dataset", "C", 120, 0), ("Yld_Vol_Dr", "N", 15, 4), ("Speed_mph_", "N", 15, 4)]
    cols = {"Dataset": ["x" * 100, "y", "z"], "Yld_Vol_Dr": [123456789.5, 1.0, 2.0], "Speed_mph_": [4.5, 4.5, 4.5]}
    shp = _point_set(str(tmp_path / "w_sms3s_clean.shp"), np.full(n, -114.1), np.full(n, 51.8), wide, cols)
    W = difm.write_zip(shp)
    _, P = _parts(W["zip"])
    _, fd, rd = _dbf(P[".dbf"])
    d = {f[0]: f for f in fd}
    assert d["Dataset"] == ("Dataset", "C", 120, 0) and d["Yld_Vol_Dr"] == ("Yld_Vol_Dr", "N", 24, 6)
    assert d["Speed_mph_"] == ("Speed_mph_", "N", 24, 6)
    assert _cells(fd, rd, "Dataset")[0] == b"x" * 100 + b" " * 20
    assert _cells(fd, rd, "Yld_Vol_Dr")[0] == b"123456789.500000".rjust(24)
    assert any("Dataset" in x and "own width" in x for x in W["notes"])
    assert not any("Yld_Vol_Dr" in x and "own width" in x for x in W["notes"])


def test_missing_fields_projected_file_and_the_column_to_map(tmp_path):
    """A clean file without Elevation_ / Yld_Mass_D / Obj__Id, in UTM: those fields empty (Obj__Id = the record
    number), the positions projected to WGS 84 with the ESRI .prj; a column to map that has no field here is said."""
    difm = _difm()
    from pyproj import Transformer
    n = 5
    df = _small(n).drop(columns=["Elevation_", "Yld_Mass_D", "Obj__Id"])
    df["Yld_Level"] = 70.0
    lon, lat = np.linspace(-114.1, -114.09, n), np.full(n, 51.8)
    shp = _clean_like(str(tmp_path / "u_sms3s_clean.shp"), df, lon, lat, crs="EPSG:32611")
    W = difm.write_zip(shp, map_column="Yld_Level")
    names, P = _parts(W["zip"])
    n2, fields, _ = _dbf(P[".dbf"])
    assert [(f, t) for f, t, _, _ in fields] == LAYOUT and n2 == n
    assert P[".prj"].decode("ascii") == ESRI_PRJ
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/u_sms3s_clean_DIFM.shp")
    assert b["Elevation_"].isna().all() and b["Yld_Mass_D"].isna().all() and list(b["Obj__Id"]) == [1, 2, 3, 4, 5]
    src = pyogrio.read_dataframe(shp)
    x, y = Transformer.from_crs("EPSG:32611", "EPSG:4326", always_xy=True).transform(src.geometry.x, src.geometry.y)
    assert np.allclose(b.geometry.x, x, atol=1e-10, rtol=0) and np.allclose(b.geometry.y, y, atol=1e-10, rtol=0)
    assert any("Yld_Level" in w and "has no field in this layout" in w for w in W["warnings"])
    assert "Yld_Level" not in b.columns


def test_zip_replaces_the_previous_one_and_leaves_no_temporary_file(tmp_path):
    difm = _difm()
    shp = _clean_like(str(tmp_path / "r_sms3s_clean.shp"), _small(3), np.full(3, -114.1), np.full(3, 51.8))
    zp = difm.zip_path_for(shp)
    with open(zp, "wb") as fh:
        fh.write(b"previous")
    W = difm.write_zip(shp)
    assert W["zip"] == zp and zipfile.is_zipfile(zp)
    assert sorted(os.listdir(tmp_path)) == sorted(os.path.basename(shp)[:-4] + e
                                                  for e in (".shp", ".shx", ".dbf", ".prj", ".cpg", "_DIFM.zip"))
    # a clean file whose .shp and .dbf disagree is refused, the zip left as it was
    shx = open(shp[:-4] + ".shx", "rb").read()
    open(shp[:-4] + ".shx", "wb").write(shx[:-8])
    before = open(zp, "rb").read()
    with pytest.raises(ValueError, match="2 points and 3 attribute rows"):
        difm.write_zip(shp)
    assert open(zp, "rb").read() == before


def test_the_zip_container_is_the_one_difm_read(tmp_path):
    """The zip as the one DIFM read: deflated members .shp .shx .dbf .prj .cpg in that order, made on Windows (DOS
    attributes), each a regular file read-write for all (external attributes 0o100666 << 16), no comment; the same
    clean file gives the same zip, byte for byte."""
    difm = _difm()
    shp = _clean_like(str(tmp_path / "z_sms3s_clean.shp"), _small(3), np.full(3, -114.1), np.full(3, 51.8))
    W = difm.write_zip(shp)
    with zipfile.ZipFile(W["zip"]) as z:
        infos = z.infolist()
        assert [os.path.splitext(i.filename)[1] for i in infos] == [".shp", ".shx", ".dbf", ".prj", ".cpg"]
        assert z.comment == b""
        for i in infos:
            assert i.compress_type == zipfile.ZIP_DEFLATED and i.create_system == 0
            assert i.external_attr == 0o100666 << 16 and i.flag_bits & 0x800 == 0 and i.extra == b""
    first = open(W["zip"], "rb").read()
    difm.write_zip(shp)
    assert open(W["zip"], "rb").read() == first


def test_read_back_gives_the_warnings_of_the_zip(tmp_path):
    """read_zip: a zip written earlier (a work opened again) gives back its readings, fields, readings without a day
    and the warnings (the column to map that has no field, the days missing) without writing anything."""
    difm = _difm()
    n = 4
    df = _small(n, Time=["", "", "", ""], Dataset=["load"] * n)
    df["Yld_Level"] = 70.0
    shp = _clean_like(str(tmp_path / "q_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    W = difm.write_zip(shp, map_column="Yld_Level")
    before = open(W["zip"], "rb").read()
    B = difm.read_zip(W["zip"], map_column="Yld_Level")
    assert open(W["zip"], "rb").read() == before
    assert B["zip"] == W["zip"] and B["n"] == n and B["fields"] == W["fields"] and B["n_no_day"] == 4
    assert B["warnings"] == W["warnings"] and len(B["warnings"]) == 2
    with pytest.raises(ValueError):
        difm.read_zip(str(tmp_path / "missing_DIFM.zip"))


# ------------------------------------------------------------------------------------------------ the adjusted yield
YIELD4 = ("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D", "Yld_Vol_Dr")
LABEL_3S = "3-sigma only (the monitor's yield)"
LABEL_BOTH = "3-sigma + combine correction and grower's weight (adjusted yield)"


@pytest.fixture(scope="module")
def two(tmp_path_factory):
    """Two combines side by side, COMBINE-B reading 5 % high: a combine factor its passes prove (below the 10 % max)."""
    return make_two_combines(str(tmp_path_factory.mktemp("difm_two")), bias_b=1.05)


def _clean_two(two, folder, factor: bool, use: str | None) -> dict:
    """The two combines cleaned as the app does (SMS 3-sigma): the combine factor on or off, the true weight used to
    'adjust', to 'validate', or not given (None)."""
    wd = er.new_workdir(os.path.join(folder, "ws"), "two")
    cand = er.open_input([two["shp"]], wd)[0]
    S = {"method": "sms3sigma", "tag": "two", "sms3sigma": {},
         "machines": ({"harmonise": True, "method": "auto", "reference": "auto", "max_factor": 0.10,
                       "ticket_confirms": True} if factor else {"harmonise": False})}
    if use:
        S["scale_ticket"] = {"value": float(two["truth"]["wet_lb"]), "unit": "lb", "basis": "wet",
                             "moisture_pct": None, "note": None, "area_ac": None, "use": use,
                             "test_weight_lb_bu": None, "bushel_from": "file"}
    return er.clean(cand["path"], os.path.join(folder, "out"), er.sms_clean_defaults(S, None), log=lambda m: None)


@pytest.fixture(scope="module")
def cleaned_two(two, tmp_path_factory):
    """{case: cleaning record}: 'factor' (a combine factor applied, no weight), 'adjust' (the weight used to adjust,
    the factor off), 'both', 'validate' (the weight used to validate only, the factor off)."""
    base = str(tmp_path_factory.mktemp("difm_cases"))
    return {case: _clean_two(two, os.path.join(base, case), factor, use)
            for case, factor, use in (("factor", True, None), ("adjust", False, "adjust"), ("both", True, "adjust"),
                                      ("validate", False, "validate"))}


def _level_record(L=0.96, harm=None):
    """A cleaning record whose column to map is the yield leveled to the grower's weight (hand made)."""
    R = {"method": "sms3sigma", "level": {"use": "adjust", "factor": L, "factor_final": L},
         "yield_column_for_difm": "Yld_Level", "level_column_for_difm": "Yld_Level",
         "difm_ready_added_columns": ["Yld_Level"], "columns": {"yield": "Yld_Vol_Dr", "time": "Time"}}
    if harm:
        R["machines"] = {"factor_applied": dict(harm)}
        R["difm_ready_added_columns"] = ["Yld_Harm", "Yld_Level"]
    return R


def test_the_adjusted_yield_is_the_column_the_cleaning_names(cleaned_two):
    """Which column is 'the adjusted yield', on the dry-volume basis: a combine factor only, Yld_Harm = the clean dry
    yield x the combine's factor; the grower's weight used to adjust, Yld_Level = the clean dry yield x L; both,
    Yld_Level = the clean dry yield x the combine's factor x L (the L after the combine factor); the weight used to
    validate only, none (no adjusted column is in the clean file). It is the column the app's final map shows
    (corrected_column)."""
    difm = _difm()
    from tests.test_app_fixes import _app_function
    corrected_column, = _app_function("corrected_column", er=er)
    want = {"factor": ("Yld_Harm", ["combine"]), "adjust": ("Yld_Level", ["weight"]),
            "both": ("Yld_Level", ["combine", "weight"]), "validate": None}
    for case, R in cleaned_two.items():
        shp = R["files"]["difm_ready_shp"]
        names = difm.field_names(shp)
        assert names == list(pyogrio.read_info(shp)["fields"])
        J = difm.adjustment_of(R, names)
        shown = corrected_column({"R": R, "adjusted": case in ("adjust", "both")}, names, "Yld_Vol_Dr")
        if want[case] is None:
            assert J is None and shown is None and er.recommended_yield_column(R)[0] == "Yld_Vol_Dr"
            assert not {"Yld_Harm", "Yld_Level", "Yld_Lvl_Sy"} & set(names)
            assert difm.yield_label("monitor", J) == LABEL_3S
            continue
        col, parts = want[case]
        assert (J["column"], J["parts"], J["monitor_column"]) == (col, parts, "Yld_Vol_Dr"), case
        assert er.recommended_yield_column(R)[0] == col == shown[0]
        a = pyogrio.read_dataframe(shp, read_geometry=False)
        k = a[col].to_numpy(float) / a["Yld_Vol_Dr"].to_numpy(float)
        b = (a["Machine"] == "COMBINE-B").to_numpy()
        fB = float(R["machines"]["factor_applied"]["COMBINE-B"]) if "combine" in parts else 1.0
        L = float(R["level"]["factor_final"]) if "weight" in parts else 1.0
        if "combine" in parts:
            assert abs(fB - 1) > 0.02 and J["combine"] == pytest.approx({"COMBINE-A": 1.0, "COMBINE-B": fB})
            assert f"x the combine factor (COMBINE-B x {fB:.4f}; the others x 1)" in J["what"]
        else:
            assert J["combine"] == {} and "combine factor" not in J["what"]
        if "weight" in parts:
            assert abs(L - 1) > 1e-4 and J["level"] == pytest.approx(L)
            assert f"x L {L:.4f} (leveled to the grower's weight)" in J["what"]
        else:
            assert J["level"] is None and "x L" not in J["what"]
        # the column is the clean dry yield x those factors, per reading (it is held with 4 decimals)
        assert np.allclose(k[b], fB * L, rtol=0, atol=2e-5) and np.allclose(k[~b], L, rtol=0, atol=2e-5), case
        assert difm.yield_label("adjusted", J) == {
            "factor": "3-sigma + combine correction (adjusted yield)",
            "adjust": "3-sigma + grower's weight (adjusted yield)", "both": LABEL_BOTH}[case]
        assert difm.adjustment_of(R, [c for c in names if c != col]) is None      # not in the file: no adjustment
    # a symmetric dry yield named the column to map is a moisture basis, not an adjustment
    R = {"sessions": {"recommendation": {"map_column": "Yld_Dry_Sy", "text": "map Yld_Dry_Sy"}},
         "difm_ready_added_columns": ["Yld_Dry_Sy"], "columns": {"yield": "Yld_Vol_Dr"}}
    assert er.recommended_yield_column(R)[0] == "Yld_Dry_Sy" and difm.adjustment_of(R) is None
    assert difm.adjustment_of(None) is None and difm.adjustment_of({}) is None


def test_the_adjusted_file_has_the_same_layout_and_one_factor_per_reading(cleaned_two, tmp_path):
    """The adjusted file of each case: named ..._adjusted_DIFM.zip; the layout of the 3-sigma only file (the same
    descriptors, members, points, .prj) and every other field byte for byte; Yld_Vol_Dr is the cleaning's adjusted
    column (the same decimal numbers) and Yld_Mass_D, Yld_Mass_W and Yld_Vol_We are the monitor's x that reading's
    adjusted / dry yield, so lb/bu and the moisture stay what they were. The 3-sigma only file is the one written
    without any adjustment named; the clean shapefile is not touched."""
    difm = _difm()
    assert difm.ADJUSTED_ZIP_SUFFIX == "_adjusted_DIFM.zip" and difm.YIELDS == ("monitor", "adjusted")
    for case in ("factor", "adjust", "both"):
        R = cleaned_two[case]
        clean = R["files"]["difm_ready_shp"]
        before = _clean_bytes(clean)
        J = difm.adjustment_of(R, difm.field_names(clean))
        col = J["column"]
        M = difm.write_zip(clean, str(tmp_path / f"{case}_sms3s_clean_DIFM.zip"), columns=R["columns"],
                           map_column=col, adjustment=J)
        X = difm.write_zip(clean, str(tmp_path / f"{case}_sms3s_clean_adjusted_DIFM.zip"), columns=R["columns"],
                           map_column=col, adjustment=J, adjusted=True)
        assert (M["yield"], X["yield"], X["adjusted_column"], M["adjusted_column"]) == ("monitor", "adjusted", col,
                                                                                         None)
        assert X["columns"]["Yld_Vol_Dr"] == col and M["columns"]["Yld_Vol_Dr"] == "Yld_Vol_Dr"
        nm, Pm = _parts(M["zip"])
        nx, Px = _parts(X["zip"])
        assert nx == [f"{case}_sms3s_clean_adjusted_DIFM{e}" for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
        n1, fm, rm = _dbf(Pm[".dbf"])
        n2, fx, rx = _dbf(Px[".dbf"])
        assert fx == fm == TESTED == [tuple(f) for f in X["fields"]] and n1 == n2 == R["n_kept"]
        for e in (".shp", ".shx", ".prj", ".cpg"):
            assert Px[e] == Pm[e], e
        for f, _, _, _ in TESTED:
            assert (_cells(fx, rx, f) == _cells(fm, rm, f)) == (f not in YIELD4), f
        a = pyogrio.read_dataframe(clean, read_geometry=False)
        m = pyogrio.read_dataframe(f"/vsizip/{M['zip']}/{nm[0]}", read_geometry=False)
        x = pyogrio.read_dataframe(f"/vsizip/{X['zip']}/{nx[0]}", read_geometry=False)
        adj, dry = a[col].to_numpy(float), a["Yld_Vol_Dr"].to_numpy(float)
        assert np.abs(m["Yld_Vol_Dr"].to_numpy(float) - dry).max() <= HALF      # the monitor's, to 6 decimals
        assert np.array_equal(x["Yld_Vol_Dr"].to_numpy(float), adj)             # the cleaning's adjusted column
        _, fc, rc = _dbf(before[".dbf"])
        assert [_dec(c) for c in _cells(fx, rx, "Yld_Vol_Dr")] == [_dec(c) for c in _cells(fc, rc, col)]
        k = adj / dry
        assert X["n_adjusted"] == len(a) and X["factor"]["min"] == pytest.approx(k.min(), abs=1e-12)
        assert X["factor"]["max"] == pytest.approx(k.max(), abs=1e-12)
        for f in ("Yld_Mass_D", "Yld_Mass_W", "Yld_Vol_We"):
            assert np.abs(m[f].to_numpy(float) - a[f].to_numpy(float)).max() <= HALF, f
            assert np.abs(x[f].to_numpy(float) - a[f].to_numpy(float) * k).max() <= HALF, f     # x the factor
            assert np.abs(x[f] - m[f]).max() > 1.0, f                           # and it did change
        for num, den in (("Yld_Mass_D", "Yld_Vol_Dr"), ("Yld_Mass_W", "Yld_Vol_We"), ("Yld_Vol_We", "Yld_Vol_Dr")):
            assert np.allclose(x[num] / x[den], m[num] / m[den], rtol=1e-6, atol=0), (num, den)    # lb/bu, moisture
        assert x["Moisture__"].equals(m["Moisture__"])
        assert X["warnings"] == [] and len(M["warnings"]) == 1
        assert X["label"] == difm.yield_label("adjusted", J) and X["line"].startswith(X["label"] + ": Yld_Vol_Dr = ")
        assert J["what"] in X["line"] and M["label"] == LABEL_3S and "is NOT in this file" in M["line"]
        assert _clean_bytes(clean) == before
        plain = difm.write_zip(clean, str(tmp_path / "plain" / f"{case}_sms3s_clean_DIFM.zip"), columns=R["columns"])
        assert open(plain["zip"], "rb").read() == open(M["zip"], "rb").read()
        assert plain["yield"] == "monitor" and "the cleaning adjusted no yield" in plain["line"]
    R = cleaned_two["validate"]                              # validate only: no adjusted file to write
    assert difm.adjustment_of(R, difm.field_names(R["files"]["difm_ready_shp"])) is None
    with pytest.raises(ValueError, match="the cleaning adjusted no yield"):
        difm.write_zip(R["files"]["difm_ready_shp"], str(tmp_path / "v_adjusted_DIFM.zip"), columns=R["columns"],
                       adjusted=True)
    assert not os.path.exists(tmp_path / "v_adjusted_DIFM.zip")


def test_adjusted_zero_stays_zero_and_a_reading_without_an_adjusted_yield_keeps_the_monitor_s(tmp_path):
    """A reading whose monitor yield is 0 stays 0 in the four yield fields; one with a monitor yield and a blank
    adjusted one keeps the monitor's (warned); a blank monitor yield stays blank. A clean file in an SMS point
    export's widths (N 15.4) comes in the widths of the layout DIFM read. The default name is next to the clean file;
    an adjustment that names a column the file does not hold is refused."""
    difm = _difm()
    n = 5
    desc = [("Dataset", "C", 40, 0), ("Time", "D", 8, 0), ("Moisture__", "N", 15, 4), ("Yld_Mass_W", "N", 15, 4),
            ("Yld_Vol_We", "N", 15, 4), ("Yld_Mass_D", "N", 15, 4), ("Yld_Vol_Dr", "N", 15, 4),
            ("Yld_Level", "N", 15, 4)]
    cols = {"Dataset": ["26/09/14-20:00:00"] * n, "Time": ["20260914"] * n,
            "Moisture__": [14.0, 13.5, 15.0, 14.5, 12.0],
            "Yld_Mass_W": [3660.0, 0.0, 3060.0, 2460.0, None], "Yld_Vol_We": [61.0, 0.0, 51.0, 41.0, None],
            "Yld_Mass_D": [3600.0, 0.0, 3000.0, 2400.0, None], "Yld_Vol_Dr": [60.0, 0.0, 50.0, 40.0, None],
            "Yld_Level": [66.0, 0.0, 47.5, None, None]}
    shp = _point_set(str(tmp_path / "z_sms3s_clean.shp"), np.full(n, -114.1), np.full(n, 51.8), desc, cols)
    R = _level_record(L=1.1)
    J = difm.adjustment_of(R, difm.field_names(shp))
    assert J["column"] == "Yld_Level" and J["parts"] == ["weight"] and J["level"] == 1.1
    X = difm.write_zip(shp, columns=R["columns"], map_column="Yld_Level", adjustment=J, adjusted=True)
    assert X["zip"] == difm.zip_path_for(shp, True) == str(tmp_path / "z_sms3s_clean_adjusted_DIFM.zip")
    assert difm.zip_path_for(shp) == str(tmp_path / "z_sms3s_clean_DIFM.zip")
    assert not os.path.exists(difm.zip_path_for(shp))
    _, P = _parts(X["zip"])
    _, fd, rd = _dbf(P[".dbf"])
    assert fd == TESTED
    got = {f: [_dec(c) for c in _cells(fd, rd, f)] for f in YIELD4}
    assert got["Yld_Vol_Dr"] == [Decimal("66"), Decimal("0"), Decimal("47.5"), Decimal("40"), None]
    for f, want in (("Yld_Mass_D", [3960, 0, 2850, 2400, None]), ("Yld_Vol_We", [67.1, 0, 48.45, 41, None]),
                    ("Yld_Mass_W", [4026, 0, 2907, 2460, None])):
        assert [None if v is None else float(v) for v in got[f]] == [
            None if v is None else pytest.approx(v, abs=1e-9) for v in want], f
        assert got[f][1] == Decimal("0") and got[f][3] == Decimal(str(want[3]))      # 0 stays 0; the monitor's own
    assert [_dec(c) for c in _cells(fd, rd, "Moisture__")] == [Decimal(str(v)) for v in cols["Moisture__"]]
    assert X["n_adjusted"] == 2 and X["factor"] == {"min": pytest.approx(0.95), "max": pytest.approx(1.1),
                                                    "mean": pytest.approx(1.025)}
    assert [w for w in X["warnings"] if "1 of 5 readings have a monitor yield and no adjusted one" in w]
    assert any("2 readings whose monitor yield is 0 or blank keep their values" in x for x in X["notes"])
    with pytest.raises(ValueError, match="has no column Yld_Harm"):
        difm.write_zip(shp, adjustment={"column": "Yld_Harm", "what": "Yld_Harm"}, adjusted=True)
    with pytest.raises(ValueError, match="the cleaning adjusted no yield"):
        difm.write_zip(shp, adjusted=True)
    assert sorted(f for f in os.listdir(tmp_path) if f.endswith(".zip")) == ["z_sms3s_clean_adjusted_DIFM.zip"]


def test_read_back_says_which_yield_and_only_the_3_sigma_file_warns(tmp_path):
    """The adjusted file carries the column the cleaning names: no warning, when written and when read back. The
    3-sigma only file of the same cleaning says that the adjusted yield is in the other file (no longer that it has
    no field in the layout)."""
    difm = _difm()
    n = 4
    df = _small(n)
    df["Yld_Harm"] = 64.8375 * 0.95
    df["Yld_Level"] = 64.8375 * 0.95 * 1.02
    shp = _clean_like(str(tmp_path / "q_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    R = _level_record(L=1.02, harm={"COMBINE-A": 1.0, "COMBINE-B": 0.95})
    J = difm.adjustment_of(R, difm.field_names(shp))
    assert J["parts"] == ["combine", "weight"]
    assert J["what"] == ("Yld_Level = the monitor's dry yield as cleaned x the combine factor (COMBINE-B x 0.9500; "
                         "the others x 1) x L 1.0200 (leveled to the grower's weight)")
    X = difm.write_zip(shp, columns=R["columns"], map_column="Yld_Level", adjustment=J, adjusted=True)
    M = difm.write_zip(shp, columns=R["columns"], map_column="Yld_Level", adjustment=J)
    assert X["warnings"] == [] and X["label"] == LABEL_BOTH
    assert len(M["warnings"]) == 1 and "has no field in this layout" not in M["warnings"][0]
    assert M["warnings"][0].startswith("3-sigma only: DIFM's Mass and Volume are the monitor's dry yield as cleaned")
    assert J["what"] in M["warnings"][0] and "_adjusted_DIFM.zip" in M["warnings"][0]
    before = {p: open(p, "rb").read() for p in (X["zip"], M["zip"])}
    BX = difm.read_zip(X["zip"], map_column="Yld_Level", columns=R["columns"], adjustment=J, adjusted=True)
    BM = difm.read_zip(M["zip"], map_column="Yld_Level", columns=R["columns"], adjustment=J)
    assert {p: open(p, "rb").read() for p in before} == before
    for B, W, which in ((BX, X, "adjusted"), (BM, M, "monitor")):
        assert (B["yield"], B["label"], B["line"], B["warnings"]) == (which, W["label"], W["line"], W["warnings"])
        assert B["fields"] == W["fields"] and B["n"] == n and B["adjustment"] == J
    assert BX["adjusted_column"] == "Yld_Level" and BM["adjusted_column"] is None


# ------------------------------------------------------------------------------------------------ as-applied
def test_as_applied_file_its_own_columns_with_dbase_dates(tmp_path):
    """A planter file cleaned by engine/clean/applied3s.py: the DIFM file holds the clean file's own fields in their
    order, every cell byte for byte, except its dates: Time (text with a time of day) becomes a dBASE date, the day
    of each reading; the same points; WGS 84 with the ESRI .prj."""
    difm = _difm()
    A = make_applied(str(tmp_path / "data"), "seeding")
    R = a3.run(A["shp"], str(tmp_path / "out"), {"attributes": [A["rate"], "Speed_mph_"]}, log=lambda m: None)
    clean = R["files"]["clean_shp"]
    W = difm.write_applied_zip(clean)
    assert W["zip"] == difm.zip_path_for(clean) and W["zip"].endswith("_3s_clean_DIFM.zip")
    names, P = _parts(W["zip"])
    assert names == [os.path.basename(clean)[:-4] + "_DIFM" + e for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    nc, fc, rc = _dbf(open(clean[:-4] + ".dbf", "rb").read())
    nd, fd, rd = _dbf(P[".dbf"])
    assert nc == nd == R["n_kept"]
    assert [f[0] for f in fd] == [f[0] for f in fc]
    for f, t, w, d in fd:
        if f == "Time":
            assert (t, w, d) == ("D", 8, 0)
            assert set(_cells(fd, rd, f)) == {b"20260512"}
        else:
            assert (f, t, w, d) in fc and _cells(fd, rd, f) == _cells(fc, rc, f), f
    assert W["dates"] == {"Time": "the day of the reading's time (Time)"} and W["n_no_day"] == 0
    assert P[".prj"].decode("ascii") == ESRI_PRJ and P[".shp"] == open(clean[:-4] + ".shp", "rb").read()


def test_as_applied_sms_export_keeps_its_own_dates(tmp_path):
    """An SMS as-applied export (Time and Date dBASE dates): the clean file of the 3-sigma cleaning holds them as text
    (GDAL writes no dBASE date); the DIFM file has them back as dBASE dates, each reading's own date."""
    difm = _difm()
    A = make_applied(str(tmp_path / "data"), "application")
    df = A["df"]
    n = len(df)
    from tests.synthetic import _lonlat
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    own = ["20260512"] * (n // 2) + ["20260513"] * (n - n // 2)
    desc = [("Field", "C", 254, 0), ("Dataset", "C", 254, 0), ("Product", "C", 254, 0), ("Obj__Id", "N", 15, 4),
            ("Time", "D", 8, 0), ("Swth_Wdth_", "N", 15, 4), ("Speed_mph_", "N", 15, 4), ("Track_deg_", "N", 15, 4),
            ("Rt_Apd_Vol", "N", 15, 4), ("Rt_Tgt_Vol", "N", 15, 4), ("Date", "D", 8, 0)]
    cols = {"Field": ["Synthetic 1"] * n, "Dataset": df["Dataset"].tolist(), "Product": df["Product"].tolist(),
            "Obj__Id": df["Obj__Id"].to_numpy(), "Time": own, "Swth_Wdth_": df["Swth_Wdth_"].to_numpy(),
            "Speed_mph_": df["Speed_mph_"].to_numpy(), "Track_deg_": df["Track_deg_"].to_numpy(),
            "Rt_Apd_Vol": df["Rt_Apd_Vol"].to_numpy(), "Rt_Tgt_Vol": df["Rt_Tgt_Vol"].to_numpy(), "Date": own}
    shp = _point_set(str(tmp_path / "data" / "Synthetic_sms_applied.shp"), lon, lat, desc, cols)
    R = a3.run(shp, str(tmp_path / "out"), {"attributes": ["Rt_Apd_Vol", "Speed_mph_"]}, log=lambda m: None)
    clean = R["files"]["clean_shp"]
    _, fc, rc = _dbf(open(clean[:-4] + ".dbf", "rb").read())
    assert dict((f[0], f[1]) for f in fc)["Time"] == "C"                 # the clean file: text
    W = difm.write_applied_zip(clean)
    _, P = _parts(W["zip"])
    nd, fd, rd = _dbf(P[".dbf"])
    d = {f[0]: f for f in fd}
    assert d["Time"] == ("Time", "D", 8, 0) and d["Date"] == ("Date", "D", 8, 0)
    keep = pyogrio.read_dataframe(clean, read_geometry=False)["Obj__Id"].astype(int).to_numpy() - 1
    want = [own[i].encode("ascii") for i in keep]
    assert _cells(fd, rd, "Time") == want and _cells(fd, rd, "Date") == want
    assert W["dates"] == {"Time": "the date of the reading (Time)", "Date": "the date of the reading (Date)"}
    for f in ("Rt_Apd_Vol", "Speed_mph_", "Dataset"):
        assert _cells(fd, rd, f) == _cells(fc, rc, f), f


# ------------------------------------------------------------------------------------------------ the app
def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception


def _by_key(items, prefix):
    return next(x for x in items if str(x.key or "").startswith(prefix))


def _difm_functions():
    """The functions of app/oced.py that write and choose the shapefile for DIFM, with the globals they need (a
    session with no dataset)."""
    from engine import works as ew
    from engine.clean import yield_clean as yc
    from tests.test_app_fixes import _app_defs
    difm = _difm()
    ss = types.SimpleNamespace(datasets={}, cleaned={}, workdir=None)
    ns = {"os": os, "json": json, "ed": difm, "er": er, "ew": ew, "yc": yc, "ss": ss}
    return _app_defs(ns, "DIFM_RECORD", "mtime", "difm_map_column", "difm_adjustment", "difm_yield_of",
                     "difm_note_record", "difm_basis", "write_difm", "difm_new_cleaning", "difm_of")


def test_app_writes_and_offers_the_shapefile_for_difm(field, tmp_path, monkeypatch):
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, field["shp"])
    _by_key(at.text_input, "bnd_path_").input(field["boundary"])
    _by_key(at.button, "bnd_use_").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    tag = at.session_state["active"]
    C = at.session_state["cleaned"][tag]
    wd = at.session_state["workdir"]
    zp = os.path.join(wd, "clean_shapefiles", f"{tag}_sms3s_clean_DIFM.zip")
    assert os.path.exists(zp) and C["difm"]["zip"] == zp and C["difm"]["error"] is None
    assert any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    assert any("the layout of an SMS shapefile export, the layout DIFM reads" in c.value for c in at.caption)
    # this cleaning adjusted nothing: no question, the plain 3-sigma file only, and the caption says which it is
    assert not [r for r in at.radio if str(r.key or "").startswith("difm_y_")]
    assert sorted(f for f in os.listdir(os.path.dirname(zp)) if f.endswith("_DIFM.zip")) == [os.path.basename(zp)]
    assert any(f"({tag}_sms3s_clean_DIFM.zip): {LABEL_3S}" in c.value and "the cleaning adjusted no yield" in c.value
               for c in at.caption)
    assert C["difm"]["yield"] == "monitor" and "shapefile_for_difm" not in C["R"]
    names, P = _parts(zp)
    assert names == [f"{tag}_sms3s_clean_DIFM{e}" for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    n, fields, _ = _dbf(P[".dbf"])
    assert fields == TESTED and n == int(pyogrio.read_info(C["shp"])["features"])
    # the clean shapefile handed out is the engine's, unchanged, with its own columns
    eng = os.path.join(wd, "clean", tag, os.path.basename(C["shp"]))
    assert _clean_bytes(C["shp"]) == _clean_bytes(eng)
    assert {"Machine", "Harv_Day", "Wdth_Raw", "Swath_Scl"} <= set(pyogrio.read_info(C["shp"])["fields"])
    longest = max(len(os.path.join(dp, f)) for dp, _, fn in os.walk(wd) for f in fn)
    assert longest <= 250
    # a work cleaned before (no DIFM zip): written when step 4 shows it
    os.remove(zp)
    at.session_state["cleaned"][tag].pop("difm", None)
    at.run()
    assert not at.exception, at.exception
    assert os.path.exists(zp) and any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    # a write that fails (here a folder in the zip's place) is said, with a button that tries again
    os.remove(zp)
    at.session_state["cleaned"][tag].pop("difm", None)
    os.makedirs(zp)
    at.run()
    assert not at.exception, at.exception
    assert any("The shapefile for DIFM could not be written" in w.value for w in at.warning)
    assert not any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    at.run()                                                    # not tried again by itself
    assert os.path.isdir(zp)
    os.rmdir(zp)
    at.button(key=f"difm_retry_{tag}").click().run()
    assert not at.exception, at.exception
    assert zipfile.is_zipfile(zp) and any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    # a cleaning to clean again (an older version's, files replaced): no DIFM file offered, said why
    again = "made by an older version of the SMS 3-sigma method: clean it again"
    at.session_state["cleaned"][tag]["clean_again"] = again
    at.session_state["cleaned"][tag].pop("difm", None)
    at.run()
    assert not at.exception, at.exception
    assert not any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    assert any("Shapefile for DIFM: not offered" in x.value for x in list(at.info) + list(at.warning))
    at.session_state["cleaned"][tag].pop("clean_again", None)
    at.session_state["cleaned"][tag].pop("difm", None)
    at.run()
    # imported again: the cleaning is dropped and its DIFM zip leaves clean_shapefiles/ with the clean set
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert not os.path.exists(zp)
    assert glob.glob(os.path.join(wd, "superseded", "*", "p", f"{tag}_sms3s_clean_DIFM.zip"))
    assert not any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))


def test_the_symmetric_column_warning_comes_back_when_the_work_is_opened_again(tmp_path):
    """The DIFM file of a cleaning whose column to map is no adjustment and has no field in the layout (the symmetric
    dry yield of a cleaning by the cascade): no question (one file, the monitor's yield); its warning is given when
    the zip is written and again when the work is opened again (the session then holds no result of the writer, and
    the zip is not written again)."""
    F = _difm_functions()
    n = 4
    df = _small(n)
    df["Yld_Dry_Sy"] = 66.0
    shp = _clean_like(str(tmp_path / "v_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    R = {"sessions": {"recommendation": {"map_column": "Yld_Dry_Sy", "text": "map Yld_Dry_Sy"}},
         "difm_ready_added_columns": ["Yld_Dry_Sy"], "columns": {"yield": "Yld_Vol_Dr", "time": "Time"}}
    assert er.recommended_yield_column(R)[0] == "Yld_Dry_Sy" == F["difm_map_column"](R)
    C = {"shp": shp, "R": R, "kind": "sms"}
    assert F["difm_adjustment"](shp, R) is None
    W1 = F["difm_of"]("v", C)
    assert W1["zip"] == shp[:-4] + "_DIFM.zip" and W1["yield"] == "monitor"
    assert any("Yld_Dry_Sy" in w and "has no field in this layout" in w for w in W1["warnings"])
    zb, zt = open(W1["zip"], "rb").read(), os.path.getmtime(W1["zip"])
    C2 = {"shp": shp, "R": R, "kind": "sms"}                         # the work opened again
    W2 = F["difm_of"]("v", C2)
    assert W2["zip"] == W1["zip"] and W2["warnings"] == W1["warnings"] and W2["error"] is None
    assert open(W2["zip"], "rb").read() == zb and os.path.getmtime(W2["zip"]) == zt
    assert "shapefile_for_difm" not in R and not os.path.exists(shp[:-4] + "_adjusted_DIFM.zip")


def test_no_adjustment_no_choice_and_one_file(tmp_path):
    """A cleaning that adjusted nothing (no combine factor applied; no grower's weight, or one used to validate only):
    no choice, whatever the session holds; the plain 3-sigma file is the only one written and its result says so; the
    cleaning record gets no entry."""
    F = _difm_functions()
    shp = _clean_like(str(tmp_path / "n_sms3s_clean.shp"), _small(4), np.full(4, -114.1), np.full(4, 51.8))
    for R in ({"method": "sms3sigma", "yield_column_for_difm": "Yld_Vol_Dr", "columns": {"yield": "Yld_Vol_Dr"},
               "machines": {"factor_applied": {"COMBINE-A": 1.0, "COMBINE-B": 1.0}}},
              {"method": "sms3sigma", "yield_column_for_difm": "Yld_Vol_Dr", "columns": {"yield": "Yld_Vol_Dr"},
               "level": {"use": "validate", "factor": 0.97, "factor_final": 0.97},
               "difm_ready_added_columns": ["Wdth_Raw"]}):
        js = str(tmp_path / "n_cleaning.json")
        json.dump(R, open(js, "w", encoding="utf-8"), indent=1)
        was = open(js, "rb").read()
        C = {"shp": shp, "R": R, "kind": "sms", "json": js, "difm_yield": "adjusted"}
        assert F["difm_adjustment"](shp, R) is None and F["difm_yield_of"](C, None) == "monitor"
        W = F["difm_of"]("n", C)
        assert W["zip"] == shp[:-4] + "_DIFM.zip" and W["yield"] == "monitor" and W["warnings"] == []
        assert W["label"] == LABEL_3S and "the cleaning adjusted no yield" in W["line"]
        assert sorted(f for f in os.listdir(tmp_path) if f.endswith(".zip")) == ["n_sms3s_clean_DIFM.zip"]
        assert "shapefile_for_difm" not in R and open(js, "rb").read() == was
        os.remove(W["zip"])


def test_each_choice_has_its_file_and_the_record_says_which(tmp_path):
    """A cleaning that adjusted the yield: the default is the adjusted file (<clean>_adjusted_DIFM.zip, no warning);
    the other choice writes <clean>_DIFM.zip and keeps the first; the cleaning record (JSON) says which one was
    generated and what the adjustment was, changing nothing else of it; a work opened again (the record read back)
    keeps the choice and writes nothing; a new cleaning starts from the default and removes the zip of the other name
    that the earlier cleaning left."""
    F = _difm_functions()
    n = 4
    df = _small(n)
    df["Yld_Level"] = 64.8375 * 0.96
    shp = _clean_like(str(tmp_path / "v_sms3s_clean.shp"), df, np.full(n, -114.1), np.full(n, 51.8))
    za, zm = shp[:-4] + "_adjusted_DIFM.zip", shp[:-4] + "_DIFM.zip"
    R = _level_record(L=0.96)
    R["n_kept"], R["notes"] = n, ["a note", float("nan")]
    js = str(tmp_path / "v_cleaning.json")
    json.dump(R, open(js, "w", encoding="utf-8"), indent=1)
    C = {"shp": shp, "R": R, "kind": "sms", "json": js}
    adj = F["difm_adjustment"](shp, R)
    assert adj["column"] == "Yld_Level" and F["difm_yield_of"](C, adj) == "adjusted"
    W1 = F["difm_of"]("v", C)
    assert W1["zip"] == za and W1["yield"] == "adjusted" and W1["warnings"] == [] and W1["error"] is None
    assert os.path.exists(za) and not os.path.exists(zm)
    x = pyogrio.read_dataframe(f"/vsizip/{za}/v_sms3s_clean_adjusted_DIFM.shp", read_geometry=False)
    assert np.allclose(x["Yld_Vol_Dr"], 64.8375 * 0.96, atol=1e-9) and np.allclose(x["Yld_Mass_D"], 3890.25 * 0.96,
                                                                                    atol=1e-6)
    J1 = json.load(open(js, encoding="utf-8"))
    rec = J1.pop("shapefile_for_difm")
    assert rec == R["shapefile_for_difm"] and rec["file"] == "v_sms3s_clean_adjusted_DIFM.zip"
    assert (rec["yield"], rec["column"], rec["other_file"]) == ("adjusted", "Yld_Level", "v_sms3s_clean_DIFM.zip")
    assert rec["label"] == "3-sigma + grower's weight (adjusted yield)" and rec["adjustment"]["level"] == 0.96
    assert "Yld_Vol_Dr = Yld_Level = the monitor's dry yield as cleaned x L 0.9600" in rec["line"]
    J0 = {k: v for k, v in R.items() if k != "shapefile_for_difm"}
    assert json.dumps(J1, sort_keys=True) == json.dumps(J0, sort_keys=True)      # nothing else of the record changed
    ta = os.path.getmtime(za)
    # the other choice
    C["difm_yield"] = "monitor"
    W2 = F["difm_of"]("v", C)
    assert W2["zip"] == zm and W2["yield"] == "monitor" and os.path.exists(za) and os.path.getmtime(za) == ta
    assert len(W2["warnings"]) == 1 and W2["warnings"][0].startswith("3-sigma only")
    assert "is NOT in this file" in W2["line"]
    m = pyogrio.read_dataframe(f"/vsizip/{zm}/v_sms3s_clean_DIFM.shp", read_geometry=False)
    assert np.allclose(m["Yld_Vol_Dr"], 64.8375, atol=1e-9)
    rec = json.load(open(js, encoding="utf-8"))["shapefile_for_difm"]
    assert (rec["file"], rec["yield"], rec["column"], rec["other_file"]) == (
        "v_sms3s_clean_DIFM.zip", "monitor", "Yld_Vol_Dr", "v_sms3s_clean_adjusted_DIFM.zip")
    assert rec["adjustment"]["column"] == "Yld_Level" and rec["label"] == LABEL_3S
    tm = os.path.getmtime(zm)
    # the work opened again: the record read back, no choice in the session
    C2 = {"shp": shp, "R": json.load(open(js, encoding="utf-8")), "kind": "sms", "json": js}
    assert F["difm_yield_of"](C2, adj) == "monitor"
    W3 = F["difm_of"]("v", C2)
    assert W3["zip"] == zm and W3["warnings"] == W2["warnings"] and W3["line"] == W2["line"]
    C2["difm_yield"] = "adjusted"                                    # back to the adjusted one: it is there, read back
    W4 = F["difm_of"]("v", C2)
    assert W4["zip"] == za and W4["yield"] == "adjusted" and W4["warnings"] == []
    assert (os.path.getmtime(za), os.path.getmtime(zm)) == (ta, tm)
    assert json.load(open(js, encoding="utf-8"))["shapefile_for_difm"]["yield"] == "adjusted"
    # a failed write of one choice does not stand for the other
    C2["difm"] = {"zip": None, "error": "held", "yield": "monitor", "for": max(
        os.path.getmtime(shp[:-4] + e) for e in (".shp", ".shx", ".dbf")), "notes": [], "warnings": []}
    assert F["difm_of"]("v", C2)["zip"] == za
    # a new cleaning of the file: the default again, and the other name's zip (of the earlier cleaning) goes
    res = {"shp": shp, "R": _level_record(L=0.96), "kind": "sms", "json": js}
    F["difm_new_cleaning"]("v", res)
    assert res["difm"]["zip"] == za and res["difm"]["yield"] == "adjusted" and not os.path.exists(zm)
    assert res["R"]["shapefile_for_difm"]["yield"] == "adjusted"
    res = {"shp": shp, "R": {"method": "sms3sigma", "yield_column_for_difm": "Yld_Vol_Dr",
                             "columns": {"yield": "Yld_Vol_Dr", "time": "Time"}}, "kind": "sms"}
    F["difm_new_cleaning"]("v", res)                                 # ... one that adjusted nothing: one file
    assert res["difm"]["zip"] == zm and res["difm"]["yield"] == "monitor" and not os.path.exists(za)
    assert "shapefile_for_difm" not in res["R"]


def test_app_asks_which_yield_when_the_cleaning_adjusted_it(two, tmp_path, monkeypatch):
    """Two combines with a combine factor applied and the grower's weight used to adjust: step 4 asks which yield the
    shapefile for DIFM carries, the adjusted one by default (<tag>_sms3s_clean_adjusted_DIFM.zip: Yld_Vol_Dr is the
    clean file's Yld_Level and the other yield fields follow by the same factor per reading; no warning); the caption
    and the cleaning record say which was generated, with the combine factor and L. The other choice writes
    <tag>_sms3s_clean_DIFM.zip (the monitor's yield) and keeps the first. Saved and opened again, the work keeps the
    choice and writes nothing. Cleaned again with nothing adjusted: no question and one file."""
    from tests.test_app_fixes import _long_path_ns
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, two["shp"])
    _by_key(at.toggle, "cf_on_").set_value(True).run()
    _by_key(at.number_input, "gw_w_").set_value(float(two["truth"]["wet_lb"])).run()
    _by_key(at.button_group, "gw_use_").set_value("adjust").run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    C = at.session_state["cleaned"][tag]
    R = C["R"]
    fB, L = float(R["machines"]["factor_applied"]["COMBINE-B"]), float(R["level"]["factor_final"])
    assert abs(fB - 1) > 0.02 and abs(L - 1) > 1e-4 and C["adjusted"]
    cdir = os.path.join(wd, "clean_shapefiles")
    za = os.path.join(cdir, f"{tag}_sms3s_clean_adjusted_DIFM.zip")
    zm = os.path.join(cdir, f"{tag}_sms3s_clean_DIFM.zip")
    q = _by_key(at.radio, "difm_y_")
    assert q.value == "adjusted" and list(q.options) == [LABEL_3S, LABEL_BOTH]
    assert os.path.exists(za) and not os.path.exists(zm)
    assert C["difm"]["zip"] == za and C["difm"]["yield"] == "adjusted" and C["difm"]["error"] is None
    assert any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    cap = next(c.value for c in at.caption if c.value.startswith("Shapefile for DIFM ("))
    assert cap.startswith(f"Shapefile for DIFM ({tag}_sms3s_clean_adjusted_DIFM.zip): {LABEL_BOTH}: Yld_Vol_Dr = "
                          "Yld_Level = the monitor's dry yield as cleaned x the combine factor (COMBINE-B x "
                          f"{fB:.4f}; the others x 1) x L {L:.4f} (leveled to the grower's weight)")
    assert "the layout of an SMS shapefile export, the layout DIFM reads" in cap and "other choice" not in cap
    assert not any(w.value.startswith("Shapefile for DIFM:") for w in at.warning)
    rec = json.load(open(C["json"], encoding="utf-8"))["shapefile_for_difm"]
    assert (rec["file"], rec["yield"], rec["column"]) == (os.path.basename(za), "adjusted", "Yld_Level")
    assert rec["adjustment"]["level"] == pytest.approx(L)
    assert rec["adjustment"]["combine"]["COMBINE-B"] == pytest.approx(fB)
    assert rec["label"] == LABEL_BOTH and rec == at.session_state["cleaned"][tag]["R"]["shapefile_for_difm"]
    # the adjusted file: the same layout, Yld_Vol_Dr = the clean file's Yld_Level, one factor per reading
    a = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    names, P = _parts(za)
    assert names == [f"{tag}_sms3s_clean_adjusted_DIFM{e}" for e in (".shp", ".shx", ".dbf", ".prj", ".cpg")]
    n, fields, _ = _dbf(P[".dbf"])
    assert fields == TESTED and n == len(a)
    x = pyogrio.read_dataframe(f"/vsizip/{za}/{names[0]}", read_geometry=False)
    k = a["Yld_Level"].to_numpy(float) / a["Yld_Vol_Dr"].to_numpy(float)
    b = (a["Machine"] == "COMBINE-B").to_numpy()
    assert np.allclose(k[b], fB * L, rtol=0, atol=2e-5) and np.allclose(k[~b], L, rtol=0, atol=2e-5)
    assert np.array_equal(x["Yld_Vol_Dr"].to_numpy(float), a["Yld_Level"].to_numpy(float))
    for f in ("Yld_Mass_D", "Yld_Mass_W", "Yld_Vol_We"):
        assert np.abs(x[f].to_numpy(float) - a[f].to_numpy(float) * k).max() <= HALF, f
    assert np.allclose(x["Yld_Mass_D"] / x["Yld_Vol_Dr"], a["Yld_Mass_D"] / a["Yld_Vol_Dr"], rtol=1e-6, atol=0)
    assert np.abs(x["Moisture__"].to_numpy(float) - a["Moisture__"].to_numpy(float)).max() <= HALF
    # both names are within the path budget of the work folder
    depth = _long_path_ns()["clean_depth"](len(wd), len(tag), True)
    assert len(zm) < len(za) <= depth <= 259
    # the other choice: the monitor's yield under the other name; the adjusted file stays
    ta = os.path.getmtime(za)
    q.set_value("monitor").run()
    assert not at.exception, at.exception
    C = at.session_state["cleaned"][tag]
    assert C["difm"]["zip"] == zm and C["difm"]["yield"] == "monitor" and os.path.exists(zm)
    assert os.path.exists(za) and os.path.getmtime(za) == ta
    cap = next(c.value for c in at.caption if c.value.startswith("Shapefile for DIFM ("))
    assert cap.startswith(f"Shapefile for DIFM ({tag}_sms3s_clean_DIFM.zip): {LABEL_3S}: Yld_Mass_D and Yld_Vol_Dr are "
                          "the monitor's dry yield as cleaned; the adjusted yield of the cleaning (Yld_Level = ")
    assert "is NOT in this file" in cap
    assert f"The file of the other choice, {tag}_sms3s_clean_adjusted_DIFM.zip, was written too" in cap
    warn = [w.value for w in at.warning if w.value.startswith("Shapefile for DIFM:")]
    assert len(warn) == 1 and "3-sigma only" in warn[0] and "_adjusted_DIFM.zip" in warn[0]
    names_m, Pm = _parts(zm)
    assert _dbf(Pm[".dbf"])[1] == TESTED and Pm[".shp"] == P[".shp"]
    m = pyogrio.read_dataframe(f"/vsizip/{zm}/{names_m[0]}", read_geometry=False)
    assert np.abs(m["Yld_Vol_Dr"].to_numpy(float) - a["Yld_Vol_Dr"].to_numpy(float)).max() <= HALF
    assert json.load(open(C["json"], encoding="utf-8"))["shapefile_for_difm"]["yield"] == "monitor"
    tm = os.path.getmtime(zm)
    # saved and opened again: the choice is kept and nothing is written again
    at.button(key="work_save").click().run()
    assert not at.exception, at.exception
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    assert at2.session_state["workdir"] == wd and tag in at2.session_state["cleaned"]
    q2 = _by_key(at2.radio, "difm_y_")
    assert q2.value == "monitor"                                     # from the cleaning record, not the session
    assert at2.session_state["cleaned"][tag]["difm"]["zip"] == zm
    assert any(w.value.startswith("Shapefile for DIFM: 3-sigma only") for w in at2.warning)
    q2.set_value("adjusted").run()
    assert not at2.exception, at2.exception
    assert at2.session_state["cleaned"][tag]["difm"]["zip"] == za
    assert (os.path.getmtime(za), os.path.getmtime(zm)) == (ta, tm)
    assert not any(w.value.startswith("Shapefile for DIFM:") for w in at2.warning)
    cap = next(c.value for c in at2.caption if c.value.startswith("Shapefile for DIFM ("))
    assert LABEL_BOTH in cap and f"The file of the other choice, {tag}_sms3s_clean_DIFM.zip, was written too" in cap
    # cleaned again with nothing adjusted (the factor off, the weight to validate only): no question, one file
    _by_key(at2.toggle, "cf_on_").set_value(False).run()
    _by_key(at2.button_group, "gw_use_").set_value("validate").run()
    at2.button(key="clean_one").click().run()
    assert not at2.exception, at2.exception
    C = at2.session_state["cleaned"][tag]
    assert not [r for r in at2.radio if str(r.key or "").startswith("difm_y_")]
    assert C["difm"]["zip"] == zm and C["difm"]["yield"] == "monitor" and os.path.exists(zm) and not os.path.exists(za)
    cap = next(c.value for c in at2.caption if c.value.startswith("Shapefile for DIFM ("))
    assert f"({tag}_sms3s_clean_DIFM.zip): {LABEL_3S}" in cap and "the cleaning adjusted no yield" in cap
    assert not any(w.value.startswith("Shapefile for DIFM:") for w in at2.warning)
    assert "shapefile_for_difm" not in json.load(open(C["json"], encoding="utf-8"))
    m2 = pyogrio.read_dataframe(f"/vsizip/{zm}/{names_m[0]}", read_geometry=False)
    a2 = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    assert "Yld_Level" not in a2.columns
    assert np.abs(m2["Yld_Vol_Dr"].to_numpy(float) - a2["Yld_Vol_Dr"].to_numpy(float)).max() <= HALF


def test_a_dropped_cleaning_takes_both_difm_zips_with_it(tmp_path):
    """A cleaning that no longer applies (its file imported or extracted again): both shapefiles for DIFM of the file,
    the 3-sigma only one and the adjusted one, leave clean_shapefiles/ with the clean set (to superseded/); the files
    of another file whose name starts with this one stay."""
    from engine.formats import detect
    from tests.test_app_fixes import _app_defs

    class _Session(dict):
        __getattr__ = dict.__getitem__

    wd = str(tmp_path / "w")
    cdir = os.path.join(wd, "clean_shapefiles")
    os.makedirs(cdir)
    mine = ["T_sms3s_clean.shp", "T_sms3s_clean.dbf", "T_sms3s_clean.zip", "T_sms3s_clean_DIFM.zip",
            "T_sms3s_clean_adjusted_DIFM.zip"]
    other = ["T2_sms3s_clean.shp", "T2_sms3s_clean_DIFM.zip", "T2_sms3s_clean_adjusted_DIFM.zip"]
    for f in mine + other:
        with open(os.path.join(cdir, f), "wb") as fh:
            fh.write(f.encode("ascii"))
    ss = _Session(workdir=wd, cleaned={"T": {"shp": os.path.join(cdir, "T_sms3s_clean.shp"),
                                             "zip": os.path.join(cdir, "T_sms3s_clean.zip")},
                                       "T2": {"shp": os.path.join(cdir, "T2_sms3s_clean.shp")}})
    ns = _app_defs({"os": os, "shutil": shutil, "dt": dt, "detect": detect, "er": er, "ed": _difm(), "ss": ss,
                    "NATIVE_DIR": "native", "LOCK_NAME": ".oced_cleaning.lock", "all_clean_zip": lambda: None},
                   "superseded_dir", "_move_free", "drop_cleaning")
    assert ns["drop_cleaning"]("T") == []
    assert sorted(os.listdir(cdir)) == sorted(other) and list(ss.cleaned) == ["T2"]
    moved = glob.glob(os.path.join(wd, "superseded", "*", "p", "*"))
    assert sorted(os.path.basename(p) for p in moved) == sorted(mine)


def test_a_cleaning_to_clean_again_gets_no_difm_file(tmp_path):
    F = _difm_functions()
    shp = _clean_like(str(tmp_path / "o_sms3s_clean.shp"), _small(3), np.full(3, -114.1), np.full(3, 51.8))
    C = {"shp": shp, "R": {}, "kind": "sms", "clean_again": "made by an older version: clean it again"}
    W = F["difm_of"]("o", C)
    assert W["zip"] is None and W["blocked"] == C["clean_again"] and not W.get("error")
    assert not os.path.exists(shp[:-4] + "_DIFM.zip")


def test_app_planter_file_gets_its_shapefile_for_difm(tmp_path, monkeypatch):
    A = make_applied(str(tmp_path / "data"), "seeding")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, A["shp"])
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    wd = at.session_state["workdir"]
    tag = at.session_state["active"]
    C = at.session_state["cleaned"][tag]
    zp = os.path.join(wd, "clean_shapefiles", f"{tag}_3s_clean_DIFM.zip")
    assert C["kind"] == "a3" and C["difm"]["zip"] == zp and os.path.exists(zp)
    assert any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    assert any("its own columns" in c.value and "dBASE dates" in c.value for c in at.caption)
    _, P = _parts(zp)
    _, fd, _ = _dbf(P[".dbf"])
    assert ("Time", "D", 8, 0) in fd and A["rate"] in [f[0] for f in fd]


def test_path_checks_count_the_shapefile_for_difm(tmp_path):
    """clean_depth counts the longer name of a harvest file's shapefile for DIFM, clean_shapefiles/
    <tag>_sms3s_clean_adjusted_DIFM.zip (whether a cleaning adjusts the yield is only known once it ran), and
    <tag>_3s_clean_DIFM.zip (an as-applied file); the cleaning guard refuses a cleaning whose DIFM zip would pass the
    259 characters Windows opens, before anything is written."""
    from tests.test_app_fixes import _long_path_ns, _path_of_length
    difm = _difm()
    ns = _long_path_ns()
    sep = len(os.sep)
    assert "_sms3s_clean" + difm.ADJUSTED_ZIP_SUFFIX == "_sms3s_clean_adjusted_DIFM.zip"
    assert "_3s_clean" + difm.ZIP_SUFFIX == "_3s_clean_DIFM.zip"
    for wd_len in (100, 220):
        for k in (1, 4):
            assert ns["clean_depth"](wd_len, k, True) == wd_len + max(
                2 * sep + len("clean") + sep + 2 * k + len("_sms3s_cleaning_report.pdf"),
                2 * sep + len("clean_shapefiles") + k + len("_sms3s_clean.shp.bak"),
                2 * sep + len("clean_shapefiles") + k + len("_sms3s_clean_adjusted_DIFM.zip"))
            assert ns["clean_depth"](wd_len, k, False) == wd_len + max(
                2 * sep + len("clean") + sep + 2 * k + len(ns["a3"].REPORT_SUFFIX),
                2 * sep + len("clean_shapefiles") + k + len("_3s_clean.shp.bak"),
                2 * sep + len("clean_shapefiles") + k + len("_3s_clean_DIFM.zip"))
    assert ns["clean_depth"](211, 1, True) == 260 and ns["clean_depth"](210, 1, True) == 259
    assert ns["clean_depth"](220, 1, False) == 220 + 2 * sep + len("clean_shapefiles") + 1 + len("_3s_clean_DIFM.zip")
    # a tag at the floor of tag_budget (12 characters): the adjusted name is the longest path of its cleaning
    assert ns["clean_depth"](0, 12, True) == (2 * sep + len("clean_shapefiles") + 12
                                              + len("_sms3s_clean_adjusted_DIFM.zip"))
    assert ns["workspace_room"]() == 259 - (1 + 16 + 20) - ns["clean_depth"](0, 12, True) == 162
    ws = _path_of_length(tmp_path / "ws", 211 - 1 - 16 - 2, "w")
    wd = os.path.join(ws, "20250101-120000_A1")
    assert len(wd) == 211
    out = os.path.join(wd, "clean", "A")
    cdir = os.path.join(wd, "clean_shapefiles")
    zm, za = os.path.join(cdir, "A_sms3s_clean_DIFM.zip"), os.path.join(cdir, "A_sms3s_clean_adjusted_DIFM.zip")
    assert (len(zm), len(za)) == (251, 260)
    with ns["cleaning_guard"]("A", out, [os.path.join(cdir, "A_sms3s_clean")], files=[zm]):
        pass                                                # the 3-sigma only name alone would fit
    shutil.rmtree(out)
    with pytest.raises(ns["PathTooLong"], match="A_sms3s_clean_adjusted_DIFM.zip would be 260 characters long"):
        with ns["cleaning_guard"]("A", out, [os.path.join(cdir, "A_sms3s_clean")], files=[zm, za]):
            pass
    assert not os.path.exists(out)                          # refused before the lock or any folder


def test_app_cleaning_guards_both_names_of_the_shapefile_for_difm(field, tmp_path, monkeypatch):
    """Through the app: a harvest file of 12 characters in a work folder of 200. Its report (258), its clean set and
    its 3-sigma only shapefile for DIFM (251) fit, the adjusted name (260) does not: step 1 says the file is too long
    for this folder and the cleaning is refused before anything is written, naming that file."""
    from tests.test_app_fixes import _path_of_length
    name = os.path.splitext(os.path.basename(field["shp"]))[0][:20]
    at = _app(_path_of_length(tmp_path / "ws", 200 - 1 - 16 - len(name), "w"), monkeypatch)
    _open(at, field["shp"])
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    assert len(wd) == 200 and len(tag) == 12
    cdir = os.path.join(wd, "clean_shapefiles")
    assert len(os.path.join(wd, "clean", tag, tag + "_sms3s_cleaning_report.pdf")) == 258
    assert len(os.path.join(cdir, tag + "_sms3s_clean_DIFM.zip")) == 251
    assert len(os.path.join(cdir, tag + "_sms3s_clean_adjusted_DIFM.zip")) == 260
    warn = [w.value for w in at.warning if "Windows opens" in w.value]
    assert len(warn) == 1 and f"The file {tag} of this work is longer." in warn[0]
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    err = [e.value for e in at.error if "nothing was changed" in e.value]
    assert err and f"{tag}_sms3s_clean_adjusted_DIFM.zip would be 260 characters long" in err[0]
    assert not at.session_state["cleaned"] and not os.path.exists(os.path.join(wd, "clean", tag))
    assert not glob.glob(os.path.join(cdir, "*"))


@pytest.mark.skipif(os.name != "nt", reason="file locks are a Windows behaviour")
def test_a_difm_zip_held_open_stops_the_cleaning_before_it_runs(tmp_path):
    from tests.test_app_fixes import _long_path_ns
    ns = _long_path_ns()
    wd = os.path.join(str(tmp_path), "w")
    cdir = os.path.join(wd, "clean_shapefiles")
    os.makedirs(cdir)
    zp = os.path.join(cdir, "T_sms3s_clean_DIFM.zip")
    with open(zp, "wb") as fh:
        fh.write(b"old")
    with open(zp, "rb"):
        with pytest.raises(ns["FileInUse"], match="T_sms3s_clean_DIFM.zip is open in another program"):
            with ns["cleaning_guard"]("T", os.path.join(wd, "clean", "T"), [os.path.join(cdir, "T_sms3s_clean")],
                                      files=[zp]):
                pass
    assert open(zp, "rb").read() == b"old"
    with ns["cleaning_guard"]("T", os.path.join(wd, "clean", "T"), [os.path.join(cdir, "T_sms3s_clean")], files=[zp]):
        pass
    assert hashlib.md5(open(zp, "rb").read()).hexdigest() == hashlib.md5(b"old").hexdigest()
    shutil.rmtree(wd)
