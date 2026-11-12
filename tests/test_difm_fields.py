# -*- coding: utf-8 -*-
"""The shapefile for DIFM (engine/difm.py): what a clean file does not hold, and how its numbers and dates are written.
A point export under other column names (an Operations Center export: no Field, Dataset, Product, Duration_s,
Yld_Vol_We, Yld_Mass_D) gets those fields only where they follow exactly from its own values and from its import as
SMS (mass = volume x the import's lb/bu on the wet and the dry side, the time step of the readings, the field and the
combines of the export's metadata, the crop the import read); what does not follow stays empty, the notes say so, and
readings without Yld_Mass_D or Yld_Vol_Dr are a warning, also in step 4 of the app and when the zip is read back. The
adjusted file keeps one factor on the four yield fields. Numbers have 6 decimals (rounded half to even on their
decimal text; the adjusted yield still equals the cleaning's column), a zero is never written -0.000000, a zip over
10 MB is warned, and a zip written with 15 decimals by an earlier version is written again. Dates: one rule for every
time in UTC (the decoders that write UTC, and a time that says its zone), this computer's clock day. Synthetic data
only (tests/synthetic.py and small files made here).

    python -m pytest -q tests/test_difm_fields.py
"""
from __future__ import annotations

import json
import os
import struct
import sys
import zipfile
from decimal import Decimal

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from tests.synthetic import _lonlat, make_field, make_two_combines  # noqa: E402
from tests.test_difm import (TESTED, _app, _by_key, _cells, _clean_like, _dbf, _dec, _dec6,  # noqa: E402
                             _difm_functions, _level_record, _open, _parts, _point_set, _small)

SIX = ("Field", "Dataset", "Product", "Duration_s", "Yld_Vol_We", "Yld_Mass_D")
SERIALS = {"1": "SYNTHETIC-COMBINE-0001", "2": "SYNTHETIC-COMBINE-0002"}
CROP, FIELD = "Wheat (Hard Red Spring)", "Synthetic 2 (north)"
CLOCK = "UTC in this computer's clock time: UTC -6 h"


def _difm():
    from engine import difm
    return difm


def _ops_export(folder: str) -> dict:
    """The two synthetic combines as an Operations Center point export: its column names (no Field, Dataset, Product,
    Duration_s, wet volume or dry mass), the combines as the export's machine index, Time and IsoTime in UTC between
    01:00 and 05:00 (the evening before in a clock at UTC-6), and the export's metadata beside it (the crop, the
    field, the serial number of each machine)."""
    import geopandas as gpd
    two = make_two_combines(os.path.join(folder, "src"))
    df = two["df"]
    t = pd.to_datetime(df["Time"]) + pd.Timedelta(hours=12)
    out = pd.DataFrame({
        "DISTANCE": df["Distance_f"], "SWATHWIDTH": df["Swth_Wdth_"], "VRYIELDVOL": df["Yld_Vol_Dr"], "Crop": 25,
        "WetMass": df["Yld_Mass_W"], "Moisture": df["Moisture__"], "Time": t.dt.strftime("%m/%d/%Y %I:%M:%S %p"),
        "Heading": df["Track_deg_"], "Elevation": df["Elevation_"],
        "IsoTime": t.dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "Machine": np.where(df["Machine"] == "COMBINE-A", 1, 2), "VEHICLSPEE": df["Speed_mph_"]})
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    shp = os.path.join(folder, "ops", "Synthetic_Harvest_2026-09-15_00.shp")
    os.makedirs(os.path.dirname(shp), exist_ok=True)
    gpd.GeoDataFrame(out, geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326").to_file(shp, engine="pyogrio")
    with open(shp[:-4] + "-Deere-Metadata.json", "w", encoding="utf-8") as fh:
        json.dump({"Version": "1.0", "Operation": "Harvest", "FieldName": FIELD, "CropId": 25, "CropName": CROP,
                   "MachineUsage": {k: {"MachineSerial": v} for k, v in SERIALS.items()}}, fh)
    assert t.min() >= pd.Timestamp("2026-09-15 01:00:00") and t.max() < pd.Timestamp("2026-09-15 05:00:00")
    return {"shp": shp, "n": len(df)}


@pytest.fixture(scope="module")
def ops(tmp_path_factory):
    """The synthetic Operations Center export imported as SMS and cleaned with the SMS 3-sigma method, as the app
    does: {shp (the export), imported (the file the import read), R (the cleaning record), clean (its shapefile)}."""
    base = str(tmp_path_factory.mktemp("difm_ops"))
    X = _ops_export(base)
    wd = er.new_workdir(os.path.join(base, "ws"), "ops")
    cand = er.open_input([X["shp"]], wd)[0]
    assert cand["crop"] == CROP
    shp_i, n_i, rec = er.import_as_sms(cand["path"], "ops", os.path.join(wd, "imported"), crop=cand.get("crop"),
                                       monitor=cand.get("monitor_product"), fmt=er.import_format(None, cand),
                                       log=lambda m: None)
    assert rec["fmt"] == "jd_ops_center" and rec["applied"]["weight_and_moisture"] and rec["changed"] == ["VRYIELDVOL"]
    S = er.sms_clean_defaults({"method": "sms3sigma", "tag": "ops", "machines": {"harmonise": False}}, rec)
    R = er.clean(shp_i, os.path.join(base, "out"), S, log=lambda m: None)
    return {"shp": X["shp"], "imported": rec["all_readings"], "R": R, "clean": R["files"]["difm_ready_shp"],
            "lb_bu": float(rec["resolved"]["test_weight_lb_bu"])}


def _read(W):
    """(fields, records, {field: cells}) of a written zip."""
    _, P = _parts(W["zip"])
    n, fd, rd = _dbf(P[".dbf"])
    return fd, rd, {f[0]: _cells(fd, rd, f[0]) for f in fd}


def _blank(cells) -> int:
    return sum(1 for c in cells if not c.strip())


# ------------------------------------------------------------------------------------------------ what follows
def test_an_export_s_missing_fields_follow_from_its_own_values_and_its_import(ops, tmp_path, monkeypatch):
    """A: the clean file of an Operations Center export holds none of Field, Dataset, Product, Duration_s, Yld_Vol_We
    and Yld_Mass_D. With what its import knows (import_basis of the cleaning record) every one is filled on every
    reading: mass = volume x the import's lb/bu on the dry and on the wet side, the duration is the time step of the
    readings, the field and the combines are those of the export's metadata, the product is the crop the import
    read. Nothing is warned, the result and its notes say how each was filled, and the clean file is not touched."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    R, clean, tw = ops["R"], ops["clean"], ops["lb_bu"]
    names = difm.field_names(clean)
    assert not set(SIX) & set(names) and {"VRYIELDVOL", "WetMass", "IsoTime", "Machine"} <= set(names)
    before = {e: open(clean[:-4] + e, "rb").read() for e in (".shp", ".shx", ".dbf")}
    B = difm.import_basis(R, imported=ops["imported"])
    assert (B["lb_bu"], B["product"], B["field"], B["format"]) == (tw, CROP, FIELD, "jd_ops_center")
    assert B["machines"] == SERIALS and tw in (60.0,)
    W = difm.write_zip(clean, str(tmp_path / "ops_sms3s_clean_DIFM.zip"), columns=R["columns"], basis=B)
    fd, rd, D = _read(W)
    n = W["n"]
    assert fd == TESTED and n == R["n_kept"] > 1000
    assert {f: _blank(D[f]) for f in SIX} == {f: 0 for f in SIX}
    assert W["warnings"] == [] and W["n_blank_yield"] == {"Yld_Mass_D": 0, "Yld_Vol_Dr": 0}
    assert set(W["derived"]) == set(SIX) and all(W["columns"][f] is None for f in SIX)
    a = pyogrio.read_dataframe(clean, read_geometry=False)
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/ops_sms3s_clean_DIFM.shp", read_geometry=False)
    _, fc, rc = _dbf(open(clean[:-4] + ".dbf", "rb").read())
    dry = np.array([float(c) for c in _cells(fc, rc, "VRYIELDVOL")])
    wet = np.array([float(c) for c in _cells(fc, rc, "WetMass")])
    # the filled cells are the clean file's value x or / the import's lb/bu, to 6 decimals
    assert [_dec(c) for c in D["Yld_Mass_D"]] == [Decimal(f"{v * tw:.6f}") for v in dry]
    assert [_dec(c) for c in D["Yld_Vol_We"]] == [Decimal(f"{v / tw:.6f}") for v in wet]
    # mass / volume is the import's lb/bu on every reading, wet and dry (as far as 6 decimals can say)
    for mass, vol in (("Yld_Mass_D", "Yld_Vol_Dr"), ("Yld_Mass_W", "Yld_Vol_We")):
        m, v = b[mass].to_numpy(float), b[vol].to_numpy(float)
        assert (v > 1.0).all() and (np.abs(m / v - tw) <= 5.01e-7 * (1 + tw) / v).all(), mass
    # the dry side against the wet side: the import's one-sided shrink, as in the clean file
    assert np.allclose(b["Yld_Mass_D"] / b["Yld_Mass_W"], dry * tw / wet, rtol=1e-6, atol=0)
    assert set(_dec(c) for c in D["Duration_s"]) == {Decimal("1.000000")}
    assert set(c.rstrip() for c in D["Field"]) == {FIELD.encode("ascii")}
    assert set(c.rstrip() for c in D["Product"]) == {CROP.encode("ascii")}
    assert [c.rstrip().decode("ascii") for c in D["Dataset"]] == [SERIALS[str(int(m))] for m in a["Machine"]]
    note = next(x for x in W["notes"] if x.startswith("not in the clean file, filled with what follows exactly"))
    for part in (f"Yld_Mass_D = Yld_Vol_Dr (VRYIELDVOL) x {tw:g} lb/bu", f"Yld_Vol_We = Yld_Mass_W (WetMass) / {tw:g} "
                 "lb/bu", "Duration_s = 1 s, the time step of the readings", f"Field = {FIELD}", f"Product = {CROP}",
                 "Dataset = the combine of each reading (Machine)"):
        assert part in note, part
    assert not any("left empty" in x and "Yld_Mass_D" in x for x in W["notes"])
    assert {e: open(clean[:-4] + e, "rb").read() for e in before} == before
    # read back (a work opened again): the same fields, no warning
    back = difm.read_zip(W["zip"])
    assert back["warnings"] == [] and back["n_blank_yield"] == W["n_blank_yield"] and back["fields"] == W["fields"]


def test_what_does_not_follow_stays_empty_is_noted_and_warned(ops, tmp_path):
    """A: without what the import knows the six fields stay empty (never an invented value): the notes name them with
    the reason, and the readings without Yld_Mass_D are a warning, when the zip is written and when it is read back.
    An import that did not compute the file's yields with its weight to volume gives no lb/bu: mass and volume are
    not derived from it. A file that holds neither side of a pair says so."""
    difm = _difm()
    R, clean = ops["R"], ops["clean"]
    W = difm.write_zip(clean, str(tmp_path / "none_DIFM.zip"), columns=R["columns"])
    fd, rd, D = _read(W)
    n = W["n"]
    assert {f: _blank(D[f]) for f in SIX if f != "Duration_s"} == {f: n for f in SIX if f != "Duration_s"}
    assert _blank(D["Duration_s"]) == 0 and "Duration_s" in W["derived"]       # the time step is the file's own
    assert W["n_blank_yield"] == {"Yld_Mass_D": n, "Yld_Vol_Dr": 0}
    warn = [w for w in W["warnings"] if "have no Yld_Mass_D" in w]
    assert len(warn) == 1 and warn[0].startswith(f"{n:,} of {n:,} readings have no Yld_Mass_D (the field DIFM maps "
                                                  "as the yield mass)") and "Yld_Vol_Dr" not in warn[0].split(":")[0]
    left = next(x for x in W["notes"] if x.startswith("not in the clean file, left empty: "))
    for part in ("Field (the file's import names none)", "Dataset (the clean file names no dataset)",
                 "Product (the file's import names none)",
                 "Yld_Vol_We (no weight to volume of an import that computed the file's yields)",
                 "Yld_Mass_D (no weight to volume of an import that computed the file's yields)"):
        assert part in left, part
    assert difm.read_zip(W["zip"])["warnings"] == W["warnings"]
    # the import record says the weight to volume was not applied (or holds none): no lb/bu follows
    S = R["settings"]
    for change in ({"applied": {**S["sms_import"]["applied"], "weight_and_moisture": False}},
                   {"resolved": {**S["sms_import"]["resolved"], "test_weight_lb_bu": None}}, {"applied": None}):
        R2 = {**R, "settings": {**S, "sms_import": {**S["sms_import"], **change}}}
        B = difm.import_basis(R2, imported=ops["imported"])
        assert B["lb_bu"] is None and B["field"] == FIELD and B["product"] == CROP
    assert difm.import_basis(None)["lb_bu"] is None and difm.import_basis({"settings": {}})["product"] is None
    assert difm.import_basis(R)["field"] is None and difm.import_basis(R)["lb_bu"] == ops["lb_bu"]
    W2 = difm.write_zip(clean, str(tmp_path / "text_DIFM.zip"), columns=R["columns"],
                        basis=difm.import_basis(R2, imported=ops["imported"]))
    _, _, D2 = _read(W2)
    assert _blank(D2["Yld_Mass_D"]) == n and _blank(D2["Field"]) == 0 and _blank(D2["Dataset"]) == 0
    assert any("have no Yld_Mass_D" in w for w in W2["warnings"])
    # neither the dry mass nor the dry volume: both stay empty, both are warned
    df = _small(4).drop(columns=["Yld_Mass_D", "Yld_Vol_Dr", "Yld_Vol_We"])
    shp = _clean_like(str(tmp_path / "w_sms3s_clean.shp"), df, np.full(4, -114.1), np.full(4, 51.8))
    W3 = difm.write_zip(shp, basis={"lb_bu": 60.0})
    _, _, D3 = _read(W3)
    assert _blank(D3["Yld_Mass_D"]) == _blank(D3["Yld_Vol_Dr"]) == 4
    assert [_dec(c) for c in D3["Yld_Vol_We"]] == [Decimal(f"{3900.5 / 60.0:.6f}")] * 4       # the wet side follows
    w3 = next(w for w in W3["warnings"] if "have no Yld_Mass_D" in w)
    assert "4 of 4 readings have no Yld_Vol_Dr (the field DIFM maps as the yield volume)" in w3
    assert any("Yld_Mass_D (the clean file holds neither it nor Yld_Vol_Dr)" in x for x in W3["notes"])


def test_a_file_without_moisture_or_swath_width_is_warned(tmp_path):
    """DIFM's Define Features is to have the moisture and the swath width mapped: a clean file that holds neither
    leaves them empty and says so, when the zip is written and when it is read back; a file that holds both is not
    warned about them."""
    difm = _difm()
    n = 5
    lon, lat = np.full(n, -114.1), np.full(n, 51.8)
    W0 = difm.write_zip(_clean_like(str(tmp_path / "a_sms3s_clean.shp"), _small(n), lon, lat))
    assert not any("Moisture__" in w or "Swth_Wdth_" in w for w in W0["warnings"])
    df = _small(n).drop(columns=["Moisture__", "Swth_Wdth_"])
    W = difm.write_zip(_clean_like(str(tmp_path / "b_sms3s_clean.shp"), df, lon, lat))
    _, _, D = _read(W)
    assert _blank(D["Moisture__"]) == _blank(D["Swth_Wdth_"]) == n
    warn = [w for w in W["warnings"] if "have no Moisture__" in w]
    assert len(warn) == 1 and f"{n:,} of {n:,} readings have no Swth_Wdth_ (the swath width)" in warn[0]
    assert "Define Features" in warn[0]
    assert difm.read_zip(W["zip"])["warnings"] == W["warnings"]
    only = difm.write_zip(_clean_like(str(tmp_path / "c_sms3s_clean.shp"), _small(n).drop(columns=["Moisture__"]),
                                      lon, lat))
    w1 = next(w for w in only["warnings"] if "have no Moisture__" in w)
    assert "Swth_Wdth_ (" not in w1


def test_the_adjusted_file_of_an_export_keeps_one_factor_on_the_four_yield_fields(tmp_path):
    """A: the adjusted file of a clean file that holds only the wet mass and the dry volume (the export's names): the
    two filled fields take the reading's factor too (the adjusted yield / the monitor's dry yield), so mass / volume
    stays the import's lb/bu and the four yield fields move by one factor; a zero stays 0."""
    difm = _difm()
    n = 4
    desc = [("Machine", "C", 20, 0), ("Time", "C", 30, 0), ("Moisture", "N", 15, 4), ("WetMass", "N", 24, 15),
            ("VRYIELDVOL", "N", 24, 15), ("Yld_Level", "N", 15, 4)]
    dry = [61.123456789012345, 0.0, 48.000000499999999, 70.5]
    wet = [3700.111111111111111, 0.0, 2900.25, 4300.123456789]
    cols = {"Machine": ["COMBINE-A"] * n, "Time": ["2026-09-14 13:00:0%d" % i for i in range(n)],
            "Moisture": [14.0, 13.0, 15.5, 12.25], "WetMass": wet, "VRYIELDVOL": dry,
            "Yld_Level": [round(dry[0] * 1.1, 4), 0.0, round(dry[2] * 1.1, 4), round(dry[3] * 1.1, 4)]}
    shp = _point_set(str(tmp_path / "x_sms3s_clean.shp"), np.full(n, -114.1), np.full(n, 51.8), desc, cols)
    R = _level_record(L=1.1)
    R["columns"] = {"yield": "VRYIELDVOL", "wet_mass_lbac": "WetMass", "moisture": "Moisture", "time": "Time",
                    "machine": "Machine"}
    J = difm.adjustment_of(R, difm.field_names(shp))
    assert J["column"] == "Yld_Level" and J["monitor_column"] == "VRYIELDVOL"
    basis = {"lb_bu": 60.0, "format": "jd_ops_center", "product": CROP, "field": FIELD}
    M = difm.write_zip(shp, columns=R["columns"], adjustment=J, basis=basis)
    X = difm.write_zip(shp, columns=R["columns"], adjustment=J, adjusted=True, basis=basis)
    fm, _, Dm = _read(M)
    fx, _, Dx = _read(X)
    assert fm == fx == TESTED                              # (the hand-made file holds no swath width: warned)
    assert [w for w in X["warnings"] if "Define Features" not in w] == []
    mon = {f: [_dec(c) for c in Dm[f]] for f in ("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D", "Yld_Vol_Dr")}
    adj = {f: [_dec(c) for c in Dx[f]] for f in mon}
    lev = [Decimal(str(v)) for v in cols["Yld_Level"]]
    assert adj["Yld_Vol_Dr"] == lev                         # the cleaning's adjusted column, the same decimal number
    assert all(len(c.strip().split(b".")[1]) == 6 for f in mon for c in Dx[f])
    for i in (0, 2, 3):
        k = float(lev[i]) / dry[i]
        assert k == pytest.approx(1.1, abs=2e-6)
        for f in ("Yld_Mass_W", "Yld_Vol_We", "Yld_Mass_D"):          # one factor on the four fields
            assert float(adj[f][i]) == pytest.approx(float(mon[f][i]) * k, abs=2e-6), (f, i)
        assert float(adj["Yld_Mass_D"][i]) / float(adj["Yld_Vol_Dr"][i]) == pytest.approx(60.0, abs=1e-5)
        assert float(adj["Yld_Mass_W"][i]) / float(adj["Yld_Vol_We"][i]) == pytest.approx(60.0, abs=1e-5)
    for f in mon:                                           # a zero stays 0, and is written without a sign
        assert adj[f][1] == mon[f][1] == Decimal("0") and Dx[f][1].strip() == b"0.000000", f
    assert any("Yld_Mass_W, Yld_Vol_We, Yld_Mass_D = their monitor value x Yld_Level / VRYIELDVOL" in x
               for x in X["notes"])


def test_the_time_step_of_the_readings():
    """A: Duration_s of a file without a duration column is the step between consecutive readings of a combine that
    90 % of them share, whatever readings are missing in between; none for readings at irregular intervals, for
    dates without a time of day, and for a single step."""
    difm = _difm()
    t0 = pd.Timestamp("2026-09-14 13:00:00")
    sec = np.r_[np.arange(0, 300), np.arange(330, 630), np.arange(700, 1000)]         # 1 s, two gaps
    times = [(t0 + pd.Timedelta(seconds=int(s))).strftime("%Y-%m-%d %H:%M:%S") for s in sec]
    step, share = difm.time_step(times)
    assert step == 1.0 and share == pytest.approx(897 / 899)
    # two combines whose rows alternate: the step is taken within each combine
    both = [x for pair in zip(times, times) for x in pair]
    who = ["A", "B"] * len(times)
    assert difm.time_step(both, [who])[0] == 1.0
    assert difm.time_step(both)[0] is None                              # told apart by nothing: half the steps are 0
    # a log every 5 s; milliseconds that wander around the second; a zone designator
    five = [(t0 + pd.Timedelta(seconds=5 * i)).strftime("%Y-%m-%d %H:%M:%S") for i in range(50)]
    assert difm.time_step(five)[0] == 5.0
    ms = [(t0 + pd.Timedelta(milliseconds=1000 * i + (3 if i % 2 else -4))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
          for i in range(200)]
    assert difm.time_step(ms)[0] == 1.0
    # irregular intervals, dates only, one step: no duration follows
    rng = np.random.default_rng(5)
    irr = np.cumsum(rng.uniform(0.5, 6.0, 300))
    odd = [(t0 + pd.Timedelta(seconds=float(s))).strftime("%Y-%m-%d %H:%M:%S.%f") for s in irr]
    assert difm.time_step(odd)[0] is None
    assert difm.time_step(["2026-09-14"] * 40) == (None, 0.0)
    assert difm.time_step(times[:2]) == (None, 0.0)


# ------------------------------------------------------------------------------------------------ numbers
def _raw_set(path, desc, cells: dict, n: int, lon=-114.1, lat=51.8):
    """A point shapefile whose .dbf holds exactly the text of `cells` {field: [text per record]} (right-aligned for
    N), with the descriptors `desc`: the decimal text of each number is the one given, not a float's."""
    import geopandas as gpd
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gpd.GeoDataFrame({"k": np.arange(n)}, geometry=gpd.points_from_xy(np.full(n, lon) + 1e-5 * np.arange(n),
                                                                     np.full(n, lat)),
                     crs="EPSG:4326").to_file(path, engine="pyogrio")
    hlen, rlen = 32 + 32 * len(desc) + 1, 1 + sum(w for _, _, w, _ in desc)
    head = bytearray(32)
    head[0], head[1:4] = 0x03, bytes([126, 9, 30])
    struct.pack_into("<IHH", head, 4, n, hlen, rlen)
    out = [bytes(head)]
    for name, t, w, d in desc:
        out.append(name.encode("ascii").ljust(11, b"\0") + t.encode("ascii") + b"\0" * 4 + bytes([w, d]) + b"\0" * 14)
    out.append(b"\x0D")
    for i in range(n):
        out.append(b" " + b"".join((cells[name][i].rjust(w) if t == "N" else cells[name][i].ljust(w)).encode("ascii")
                                   for name, t, w, d in desc))
    out.append(b"\x1A")
    with open(os.path.splitext(path)[0] + ".dbf", "wb") as fh:
        fh.write(b"".join(out))
    return path


def test_numbers_have_six_decimals_rounded_half_to_even_and_no_negative_zero(tmp_path):
    """B, D: a number of the clean file with more than 6 decimals is rounded on its decimal text, half to even; one
    with fewer is padded; a zero, and a value that rounds to zero, is written 0.000000, never -0.000000 (the
    Y_Offset_f of a Gen4 file); text in exponent notation or an overflow mark is written from its numeric value (or
    left blank), said in the notes."""
    difm = _difm()
    yoff = ["-0.000000000000000", "0.000000000000000", "-0.000000400000000", "-0.000000500000000",
            "-0.000000600000000", "1.250000000000000", "-2.500000500000000", "0.000000000000014"]
    want_y = ["0.000000", "0.000000", "0.000000", "0.000000", "-0.000001", "1.250000", "-2.500000", "0.000000"]
    dist = ["1.000000500000000", "1.000001500000000", "2.999999500000001", "6.123456499999999", "6.6", "7",
            "123456789012.123456789", "0.999999999999999"]
    want_d = ["1.000000", "1.000002", "3.000000", "6.123456", "6.600000", "7.000000", "123456789012.123457",
              "1.000000"]
    spd = ["4.5e+00", "************************", "", "4.25", "-0.0", "nan", "1e-9", "3"]
    want_s = ["4.500000", "", "", "4.250000", "0.000000", "", "0.000000", "3.000000"]
    n = len(yoff)
    desc = [("Dataset", "C", 20, 0), ("Time", "C", 24, 0), ("Y_Offset_f", "N", 24, 15), ("Distance_f", "N", 24, 15),
            ("Speed_mph_", "N", 24, 15), ("Yld_Vol_Dr", "N", 15, 4), ("Yld_Mass_D", "N", 15, 4)]
    cells = {"Dataset": ["26/09/14-13:00:00"] * n, "Time": ["2026-09-14 13:00:0%d" % i for i in range(n)],
             "Y_Offset_f": yoff, "Distance_f": dist, "Speed_mph_": spd, "Yld_Vol_Dr": ["60.1234"] * n,
             "Yld_Mass_D": ["3607.4040"] * n}
    shp = _raw_set(str(tmp_path / "r_sms3s_clean.shp"), desc, cells, n)
    W = difm.write_zip(shp)
    fd, rd, D = _read(W)
    assert fd == TESTED
    assert [c.strip().decode("ascii") for c in D["Y_Offset_f"]] == want_y
    assert [c.strip().decode("ascii") for c in D["Distance_f"]] == want_d
    assert [c.strip().decode("ascii") for c in D["Speed_mph_"]] == want_s
    assert [c.strip() for c in D["Yld_Vol_Dr"]] == [b"60.123400"] * n and D["Yld_Vol_Dr"][0] == b"60.123400".rjust(24)
    assert not any(c.strip().startswith(b"-0.000000") and float(c) == 0 for f in D for c in D[f] if c.strip()
                   and f not in ("Field", "Dataset", "Product", "Time", "Date"))
    assert any(x.startswith("Speed_mph_: the clean file's Speed_mph_ holds values that are no plain decimal numbers")
               for x in W["notes"])
    assert [w for w in W["warnings"] if "Define Features" not in w] == []     # no moisture or width here
    # the cells the writer computes itself: no negative zero either
    assert [bytes(r).strip() for r in difm._number_cells([-0.0, -1e-9, -4.9e-7, -5.1e-7, 0.0, 2.5])] == [
        b"0.000000", b"0.000000", b"0.000000", b"-0.000001", b"0.000000", b"2.500000"]
    assert [bytes(r).strip() for r in difm._number_cells([-0.4, 0.4, -0.6], 18, 0)] == [b"0", b"0", b"-1"]


def test_every_number_of_a_cleaned_export_is_the_clean_file_s_to_six_decimals(ops, tmp_path):
    """B: on a cleaned file whose numbers have 15 decimals, every numeric field of the layout is N 24.6 and each cell
    is the clean file's decimal number rounded to 6 decimals; no cell starts with -0. and is zero."""
    difm = _difm()
    R, clean = ops["R"], ops["clean"]
    W = difm.write_zip(clean, str(tmp_path / "six_DIFM.zip"), columns=R["columns"],
                       basis=difm.import_basis(R, imported=ops["imported"]))
    fd, rd, D = _read(W)
    assert [(f, w, d) for f, t, w, d in fd if t == "N" and f != "Obj__Id"] == [
        (f, 24, 6) for f, t, _, _ in TESTED if t == "N" and f != "Obj__Id"]
    _, fc, rc = _dbf(open(clean[:-4] + ".dbf", "rb").read())
    more = 0
    for f, col in W["columns"].items():
        if col is None or dict((x[0], x[1]) for x in fc)[col] != "N":
            continue
        src = _cells(fc, rc, col)
        more += dict((x[0], x[3]) for x in fc)[col] > 6
        assert [_dec(c) for c in D[f]] == [_dec6(c) for c in src], f
    assert more >= 6                                        # the clean file holds these numbers with 15 decimals
    for f, t, _, _ in fd:
        if t == "N":
            assert not any(c.strip().startswith(b"-0.") and float(c) == 0 for c in D[f] if c.strip()), f


def test_a_zip_over_ten_megabytes_is_warned(tmp_path, monkeypatch):
    """B: the limit is 10 MB; a zip over it is warned when it is written and when it is read back, a harvest's and a
    planter's alike; under it nothing is said."""
    difm = _difm()
    assert difm.MAX_ZIP_BYTES == 10_000_000 and difm.size_warning(10_000_000) is None
    assert difm.size_warning(12_340_000) == ("the zip is 12.3 MB, over 10 MB: DIFM may not take a file of this size "
                                             "in one upload")
    shp = _clean_like(str(tmp_path / "s_sms3s_clean.shp"), _small(5), np.full(5, -114.1), np.full(5, 51.8))
    W = difm.write_zip(shp)
    assert W["warnings"] == [] and W["zip_bytes"] == os.path.getsize(W["zip"]) < 10_000
    monkeypatch.setattr(difm, "MAX_ZIP_BYTES", 500)
    W = difm.write_zip(shp)
    assert len(W["warnings"]) == 1 and W["warnings"][0].startswith("the zip is 0.0 MB, over 0.0005 MB")
    assert difm.read_zip(W["zip"])["warnings"] == W["warnings"]
    A = difm.write_applied_zip(shp, str(tmp_path / "a_3s_clean_DIFM.zip"))
    assert [w for w in A["warnings"] if w.startswith("the zip is ")] and A["zip_bytes"] == os.path.getsize(A["zip"])
    assert difm.read_zip(A["zip"], applied=True)["warnings"] == A["warnings"]


def test_a_zip_written_with_15_decimals_is_written_again(tmp_path, monkeypatch):
    """B: the zip an earlier version wrote (N 24.15) is not read back as this layout: the app writes it again when
    step 4 shows it, with 6 decimals."""
    difm = _difm()
    F = _difm_functions()
    shp = _clean_like(str(tmp_path / "o_sms3s_clean.shp"), _small(5, Yld_Vol_Dr=[64.8375123456789] * 5),
                      np.full(5, -114.1), np.full(5, 51.8))
    with monkeypatch.context() as m:                        # the earlier format: 15 decimals
        m.setattr(difm, "N_DEC", 15)
        m.setattr(difm, "WIDTHS", {**difm.WIDTHS, "N": (24, 15)})
        old = difm.write_zip(shp)
    _, P = _parts(old["zip"])
    assert ("Yld_Vol_Dr", "N", 24, 15) in _dbf(P[".dbf"])[1]
    with pytest.raises(ValueError, match="written by an earlier version of OCED"):
        difm.read_zip(old["zip"])
    os.utime(old["zip"])                                    # not older than the clean shapefile
    C = {"shp": shp, "kind": "sms", "R": {"method": "sms3sigma", "yield_column_for_difm": "Yld_Vol_Dr",
                                          "columns": {"yield": "Yld_Vol_Dr", "time": "Time"}}}
    W = F["difm_of"]("o", C)
    assert W["zip"] == old["zip"] and W["error"] is None
    _, P = _parts(W["zip"])
    n, fd, rd = _dbf(P[".dbf"])
    assert fd == TESTED and set(c.strip() for c in _cells(fd, rd, "Yld_Vol_Dr")) == {b"64.837512"}
    assert difm.read_zip(W["zip"])["fields"] == W["fields"]


# ------------------------------------------------------------------------------------------------ dates
def test_one_rule_for_every_time_in_utc(ops, tmp_path, monkeypatch):
    """C: readings between 01:00 and 05:00 UTC, the evening before in a clock at UTC-6. An Operations Center export
    (Time without a zone beside IsoTime, which says 'Z') is dated from the time that says its zone, in this
    computer's clock time; a John Deere decode (Src_Fmt) of the same instants gets the same day by the same rule; so
    does a file whose only time column says its zone. A time that says no zone, of a source that says nothing, is
    taken as it is. The result's days and notes say which."""
    difm = _difm()
    monkeypatch.setattr(difm, "clock_utc_offset_h", lambda s: -6.0)
    R, clean = ops["R"], ops["clean"]
    assert R["columns"]["time"] == "Time"
    a = pyogrio.read_dataframe(clean, read_geometry=False)
    assert set(a["Harv_Day"]) == {"2026-09-15"}             # the cleaning's own day of these times: the UTC day
    W = difm.write_zip(clean, str(tmp_path / "ops_DIFM.zip"), columns=R["columns"])
    _, _, D = _read(W)
    n = W["n"]
    assert set(D["Time"]) == set(D["Date"]) == {b"20260914"} and W["n_no_day"] == 0
    assert W["days"] == {f"the day of the reading's time (IsoTime, {CLOCK})": n}
    assert f"Time and Date: the day of the reading's time (IsoTime, {CLOCK}) ({n:,} readings)" in W["notes"]
    # the same instants as a John Deere decode writes them (UTC, no zone said; Src_Fmt says the decoder)
    k = 6
    iso = ["2026-09-15T01:00:0%d.000Z" % i for i in range(k)]
    plain = ["2026-09-15 01:00:0%d" % i for i in range(k)]
    lon, lat = np.full(k, -114.1) + 1e-5 * np.arange(k), np.full(k, 51.8)
    jd = _clean_like(str(tmp_path / "jd_sms3s_clean.shp"), _small(k, Time=plain, Src_Fmt=["jd_jdl"] * k), lon, lat)
    Wj = difm.write_zip(jd)
    assert set(_read(Wj)[2]["Time"]) == {b"20260914"}
    assert Wj["days"] == {f"the day of the reading's time (Time, {CLOCK})": k}
    # a file whose own time column says its zone ('Z', or an offset): the same rule
    west = ["2026-09-14 19:00:0%d-06:00" % i for i in range(k)]         # the same instants, said in a zone at UTC-6
    for name, times in (("z", iso), ("off", [t.replace(".000Z", "+00:00") for t in iso]), ("west", west)):
        z = _clean_like(str(tmp_path / f"{name}_sms3s_clean.shp"), _small(k, Time=times), lon, lat)
        Wz = difm.write_zip(z)
        assert set(_read(Wz)[2]["Time"]) == {b"20260914"}, name
        assert Wz["days"] == {f"the day of the reading's time (Time, {CLOCK})": k}, name
    # no zone said and no source that writes UTC: the time as it is
    loc = _clean_like(str(tmp_path / "loc_sms3s_clean.shp"), _small(k, Time=plain), lon, lat)
    Wl = difm.write_zip(loc)
    assert set(_read(Wl)[2]["Time"]) == {b"20260915"} and Wl["days"] == {"the day of the reading's time (Time)": k}
    assert difm._zoned(pd.Series(iso)) and not difm._zoned(pd.Series(plain))
    assert not difm._zoned(pd.Series(["2026-09-14", "2026-09-15"])) and not difm._zoned(pd.Series(["", None]))
    assert not difm._zoned(pd.Series(["09/15/2026 01:00:00 AM"]))


# ------------------------------------------------------------------------------------------------ the app
def test_app_fills_an_export_s_fields_and_keeps_them_when_the_work_is_opened_again(tmp_path, monkeypatch):
    """A, through the app: an Operations Center export opened, cleaned and shown in step 4: its shapefile for DIFM
    holds the six fields (the field and the combines from the export's metadata, found from the work), mass / volume
    is the import's lb/bu, its numbers have 6 decimals, and nothing is warned; saved and opened again, the same zip
    is offered without a warning."""
    X = _ops_export(str(tmp_path / "data"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, X["shp"])
    tag, wd = at.session_state["active"], at.session_state["workdir"]
    IM = at.session_state["datasets"][tag]["sms_import"]
    assert IM["fmt"] == "jd_ops_center" and IM["applied"]["weight_and_moisture"]
    tw = float(IM["resolved"]["test_weight_lb_bu"])
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    C = at.session_state["cleaned"][tag]
    W = C["difm"]
    assert W["error"] is None and set(W["derived"]) == set(SIX) and W["warnings"] == []
    assert not any(w.value.startswith("Shapefile for DIFM:") for w in at.warning)
    cap = next(c.value for c in at.caption if c.value.startswith("Shapefile for DIFM ("))
    assert "its numbers with 6 decimals" in cap and "mass = volume x the import's lb/bu" in cap
    fd, rd, D = _read(W)
    assert fd == TESTED and {f: _blank(D[f]) for f in SIX} == {f: 0 for f in SIX}
    assert set(c.rstrip() for c in D["Field"]) == {FIELD.encode("ascii")}
    assert set(c.rstrip().decode("ascii") for c in D["Dataset"]) == set(SERIALS.values())
    b = pyogrio.read_dataframe(f"/vsizip/{W['zip']}/{os.path.basename(W['zip'])[:-4]}.shp", read_geometry=False)
    for mass, vol in (("Yld_Mass_D", "Yld_Vol_Dr"), ("Yld_Mass_W", "Yld_Vol_We")):
        m, v = b[mass].to_numpy(float), b[vol].to_numpy(float)
        assert (np.abs(m / v - tw) <= 5.01e-7 * (1 + tw) / v).all(), mass
    zb = open(W["zip"], "rb").read()
    at.button(key="work_save").click().run()
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    assert at2.session_state["workdir"] == wd and at2.session_state["cleaned"][tag]["difm"]["zip"] == W["zip"]
    assert open(W["zip"], "rb").read() == zb
    assert not any(w.value.startswith("Shapefile for DIFM:") for w in at2.warning)
    assert any(d.label == "Shapefile for DIFM (.zip)" for d in at2.get("download_button"))


def test_app_warns_in_step_4_about_a_file_without_its_yield_mass(tmp_path, monkeypatch):
    """A, B, through the app: a point export that holds a dry yield volume and no mass at all (its import as SMS
    cannot compute the yields with a weight to volume): Yld_Mass_D stays empty and step 4 warns, on the run of the
    cleaning and when the work is opened again; a zip over the size limit (set low here) is warned there too."""
    monkeypatch.setattr(_difm(), "MAX_ZIP_BYTES", 2000)
    F = make_field(str(tmp_path / "src"))
    g = pyogrio.read_dataframe(F["shp"]).drop(columns=["Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We"])
    shp = str(tmp_path / "data" / "Synthetic_volume_only.shp")
    os.makedirs(os.path.dirname(shp))
    g.to_file(shp, engine="pyogrio")
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, shp)
    tag = at.session_state["active"]
    assert not at.session_state["datasets"][tag]["sms_import"]["applied"]["weight_and_moisture"]
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    W = at.session_state["cleaned"][tag]["difm"]
    n = W["n"]
    assert W["error"] is None and W["n_blank_yield"] == {"Yld_Mass_D": n, "Yld_Vol_Dr": 0}
    warn = [w.value for w in at.warning if w.value.startswith("Shapefile for DIFM:")]
    assert len(warn) == 2 and f"{n:,} of {n:,} readings have no Yld_Mass_D" in warn[0]
    assert warn[1].startswith("Shapefile for DIFM: the zip is ") and "MB, over 0.002 MB" in warn[1]
    assert W["zip_bytes"] == os.path.getsize(W["zip"]) > 2000
    assert any(d.label == "Shapefile for DIFM (.zip)" for d in at.get("download_button"))
    with zipfile.ZipFile(W["zip"]) as z:
        _, fd, rd = _dbf(z.read([m for m in z.namelist() if m.endswith(".dbf")][0]))
    assert _blank(_cells(fd, rd, "Yld_Mass_D")) == n and _blank(_cells(fd, rd, "Yld_Vol_Dr")) == 0
    at.button(key="work_save").click().run()
    at2 = _app(tmp_path / "ws", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    warn2 = [w.value for w in at2.warning if w.value.startswith("Shapefile for DIFM:")]
    assert warn2 == warn
