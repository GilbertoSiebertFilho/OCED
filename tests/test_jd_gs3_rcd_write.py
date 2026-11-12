# -*- coding: utf-8 -*-
"""engine/formats/jd_gs3_rcd_write.py on a synthetic GreenStar 3 card written here (every number made up, no grower
data): the clean readings written back into the card read again by the decoder - the kept readings unchanged, the
removed ones gone or (next to a kept reading) left as harvest readings of 0 kg below the import's minimum yield, their
grain set to 0, nothing deleted; the swath width in whole sections (level 2); a combine factor (level 3); new file
ids; the record-level helpers.

    python -m pytest -q tests
"""
from __future__ import annotations

import os
import struct
import sys
import zipfile

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import common as C  # noqa: E402
from engine.formats import jd_gs3_rcd as G  # noqa: E402
from engine.formats import jd_gs3_rcd_write as W  # noqa: E402

LAT0, LON0 = 51.8, -114.1
N = 150
SEC_M = 2.0                                     # three 2 m sections: a 6 m header
NAME = "6a570000-0000-1000-aaaa-000000000001"
LOAD = "6a570010-0000-1000-aaaa-000000000002"
ON_OFF = {"Header": ["dtiHeaderStatusOn", "dtiHeaderStatusOff"], "Rec": ["dtiRecordingStatusOn",
                                                                        "dtiRecordingStatusOff"]}
# name, type, enum, res, limit, init
COLS = [("Moist", 3, None, 0.01, 2.5, 14.0), ("Mass", 3, None, 0.001, 32.0, 0.0), ("Header", 1, "Header", 0, 0, 0),
        ("Sec1", 1, "Rec", 0, 0, 0), ("Sec2", 1, "Rec", 0, 0, 0), ("Sec3", 1, "Rec", 0, 0, 0),
        ("Lat", 4, None, 1e-9, 0.00045, LAT0), ("Lon", 4, None, 1e-9, 0.00045, LON0), ("Head", 3, None, 0.01, 5.0, 0.0),
        ("DD", 3, None, 1.0, 5000.0, 0.0), ("Elev", 3, None, 0.001, 1.0, 1000.0), ("Time", 4, None, 1.0, 65500.0, 0.0)]


def _column(name, typ, enum, res, limit, init):
    b = struct.pack("<HHH", typ, 0, len(name)) + name.encode("latin1") + b"\x00"
    if typ == 1:
        names = b"".join(struct.pack("<H", len(e)) + e.encode("latin1") for e in ON_OFF[enum])
        return b + struct.pack("<HH", len(ON_OFF[enum]), len(names)) + names
    return b + struct.pack("<H", 24) + struct.pack("<ddd", res, limit, init)


def _records():
    """Absolute values per record (None = no value). East at 2 m/s; 5 kg of grain from record 14 on, none in the
    records the header-up positions 60-64 take (74-78), so that the original card has no grain no reading takes;
    no grain / moisture value in record 120 (the decoder restarts those chains from 0 after it)."""
    dlon = 2.0 / (111_320.0 * np.cos(np.radians(LAT0)))
    out = []
    for i in range(N):
        up = 60 <= i <= 64
        none = i == 120
        out.append({"Moist": None if none else 14.0 + i / 100.0,
                    "Mass": None if none else (0.0 if i < 14 or 74 <= i <= 78 else 5.0 + (i % 7) / 1000.0),
                    "Header": 1 if up else 0, "Sec1": 1 if up else 0, "Sec2": 1 if up else 0,
                    "Sec3": 1 if up or 90 <= i <= 94 else 0,
                    "Lat": LAT0, "Lon": LON0 + i * dlon, "Head": 90.0, "DD": 200.0, "Elev": 1000.0,
                    "Time": i * 1000.0 + (i * 37) % 50})       # a few ms of jitter, as on real cards
    return out


def _encode_block(recs) -> bytes:
    blk = struct.pack("<HH", 1, 8) + b"synthetc" + struct.pack("<HHH", 1, 2, len(COLS))
    blk += b"".join(_column(*c) for c in COLS)
    nb = (len(COLS) + 7) // 8
    prev = {c[0]: c[5] for c in COLS}
    for r in recs:
        none_bits = 0
        fmt, vals = "<", []
        for k, (name, typ, enum, res, _, _) in enumerate(COLS):
            v = r[name]
            if v is None:
                none_bits |= 1 << k
                prev[name] = 0.0
                continue
            if typ == 1:
                fmt += "h"
                vals.append(int(v))
            else:
                fmt += "i" if typ == 4 else "h"
                vals.append(int(round((v - prev[name]) / res)))
                prev[name] = prev[name] + vals[-1] * res
        blk += struct.pack("<HB", 2, 0) + none_bits.to_bytes(nb, "little") + bytes(2 * nb) + struct.pack(fmt, *vals)
    return blk + struct.pack("<H", 4)


def make_card(folder: str) -> dict:
    card = os.path.join(folder, "Combine A")
    eic = os.path.join(card, "GS3_2630", "Profile", "RCD", "EIC")
    doc = os.path.join(eic, "Documentation", "01")
    os.makedirs(doc, exist_ok=True)
    with open(os.path.join(eic, "global.ver"), "wb") as fh:
        fh.write(b"\x07\x00\x00\x00" + b"\xff" * 1020)
    with open(os.path.join(doc, NAME + ".fdd"), "wb") as fh:
        fh.write(_encode_block(_records()))
    section = ('<Section id="{i}"><vrLateralOffset value="{lat}" sourceUOM="mm"/><RecordingStateElement>'
               '<DefinedTypeColumn columnID="Sec{k}"/></RecordingStateElement>'
               '<vrSectionWidth value="2000" sourceUOM="mm"/></Section>')
    fdl = f"""<?xml version="1.0"?>
<RCDLogFile><RCDLogBlock><ConfigBlock>
<Setup>
 <Participant><Client name="Synthetic client"/></Participant><Farm name="Synthetic farm"/>
 <Field name="Synthetic field" erid="{{00000000-0000-0000-0000-00000000f1e1}}"/>
 <Products><Crop name="Wheat" id="1"><CropWeight value="27.22" sourceUOM="kg1bu-1"/>
  <StandardPayableMoisture value="13.0" sourceUOM="prcnt"/>
  <CropVariety erid="{{00000000-0000-0000-0000-0000000000aa}}" name="Synthetic variety"/></Crop></Products>
 <Equipment><Machine name="Synthetic combine" serialNumber="SYNTH0001"/><Implement serialNumber=""/></Equipment>
</Setup>
<EquipmentConfiguration>
 <Meter id="1"><MeasuredElement calibration="500"><VariableNumberColumn columnID="Moist" sourceUOM="prcnt"
   variableRepresentation="vrHarvestMoisture"/></MeasuredElement></Meter>
 <Meter id="2"><MeasuredElement calibration="500"><VariableNumberColumn columnID="Mass" sourceUOM="kg"
   variableRepresentation="vrYieldWetMass"/></MeasuredElement></Meter>
 <Meter id="3"><MeasuredElement><DefinedTypeColumn columnID="Header" definedTypeRepresentation="dtHeaderStatus"/>
  </MeasuredElement></Meter>
 {section.format(i=10, lat=-2000, k=1)}{section.format(i=11, lat=0, k=2)}{section.format(i=12, lat=2000, k=3)}
 <NavigationReference><vrInlineOffset value="0" sourceUOM="in"/><vrLateralOffset value="0" sourceUOM="in"/>
  <vrLatitude columnID="Lat"/><vrLongitude columnID="Lon"/><vrHeading columnID="Head"/>
  <vrDeltaDistance columnID="DD" sourceUOM="cm"/><vrElevation columnID="Elev"/>
  <dtNavigationType value="dtiComputedImplement"/></NavigationReference>
</EquipmentConfiguration>
<LogTaskRegion timeStamp="2026-07-15T18:00:00.400Z" timeColumnID="Time" logInterval="1000" cropYear="2026">
 <Operation><dtOperationClass value="dtiHarvest"/><ProductRef eridRef="{{00000000-0000-0000-0000-0000000000aa}}"/>
  <MeterRef idRef="1"/><MeterRef idRef="2"/><MeterRef idRef="3"/>
  <LoadIdentityRef idRef="{{{LOAD}}}"/></Operation>
</LogTaskRegion></ConfigBlock>
<LogDataBlock><EvenByteDelta filePathName="Documentation\\01\\{NAME}.fdd" filePosition="0"/></LogDataBlock>
</RCDLogBlock></RCDLogFile>
"""
    with open(os.path.join(doc, NAME + ".fdl"), "w", encoding="latin1") as fh:
        fh.write(fdl)
    with open(os.path.join(doc, LOAD + ".fdr"), "w", encoding="latin1") as fh:
        fh.write(f'<?xml version="1.0"?><RCDLoadFile><LoadIdentity loadNumber="7" erid="{{{LOAD}}}"/></RCDLoadFile>')
    with zipfile.ZipFile(os.path.join(card, "original.zip"), "w") as z:      # an archive inside the card folder
        z.writestr("x.txt", "original")
    return {"root": folder, "fdd": os.path.join(doc, NAME + ".fdd")}


OPTS = C.DecodeOptions(shrink="one_sided")
SOURCE = {"format": "jd_gs3_rcd", "unit_ids": None, "tz_offset_h": None, "decoder_kwargs": {}}


def _decode(root):
    df, _ = G.decode(root, None, OPTS, log=lambda m: None)
    return df


# a decoder that carries the grain no reading took (jd_gs3_rcd.sms_align): the writer puts each kept reading's grain
# on its own grain record, rounded to the channel's 1 g; the fixed-shift decoder has no carry: exact
TOL_KG = 0.0005 + 1e-9 if hasattr(G, "sms_align") else 0.0
YIELDS = ["Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr"]


def _wet_kg(df):
    return (df.Yld_Mass_W * df.Distance_f * df.Swth_Wdth_ / C.SQFT_PER_AC / C.LB_PER_KG).to_numpy()


def _assert_same_readings(back, ref):
    """The same readings with every attribute equal; the grain within TOL_KG (and the yields with it)."""
    back, ref = back.reset_index(drop=True), ref.reset_index(drop=True)
    cols = [c for c in ref.columns if c not in ["Obj__Id"] + YIELDS]
    pd.testing.assert_frame_equal(back[cols], ref[cols], check_exact=True)
    assert np.all(np.abs(_wet_kg(back) - _wet_kg(ref)) <= TOL_KG)
    if TOL_KG == 0:
        pd.testing.assert_frame_equal(back[YIELDS], ref[YIELDS], check_exact=True)


def _kept_and_left(back, ref, R):
    """The readings decoded back that the clean file holds and the others: only the harvest records the writer left
    (removed_as_harvest), every one without grain and below the import's minimum yield (a reader with that minimum
    reads exactly the clean readings)."""
    key = set(zip(ref.Machine.astype(str), ref.Time.astype(str)))
    ink = np.fromiter(((m, t) in key for m, t in zip(back.Machine.astype(str), back.Time.astype(str))), bool,
                      len(back))
    left = back[~ink]
    y = left.Yld_Vol_Dr.to_numpy(float)
    assert len(left) == R["n_removed_harvest"] + R["n_not_offered_harvest"]
    assert not (np.nan_to_num(_wet_kg(left)) > 0).any() and not (np.isfinite(y) & (y >= G.MONITOR_MIN_YIELD)).any()
    return back[ink].reset_index(drop=True), left


def _written_files(path):
    return sorted(os.path.relpath(os.path.join(d, f), path).replace(os.sep, "/") for d, _, fs in os.walk(path)
                  for f in fs)


@pytest.fixture(scope="module")
def card(tmp_path_factory):
    c = make_card(str(tmp_path_factory.mktemp("gs3card")))
    c["df"] = _decode(c["root"])
    return c


def _clean(card, tmp, keep, **change):
    df = card["df"][keep].copy()
    for k, v in change.items():
        df[k] = v
    return C.write_standard(df, os.path.join(tmp, "clean.shp"))


def test_layout_reads_every_record(card):
    blk = open(card["fdd"], "rb").read()
    L = W.Layout(blk)
    _, info = G.decode_block(blk)
    assert L.n == info["n_records"] == N and L.end == len(blk)
    assert (L.states[120, L.index["Mass"]], L.states[121, L.index["Mass"]]) == (G.ST_NONE, G.ST_DELTA)


def test_level1_round_trip(card, tmp_path):
    df = card["df"]
    rng = np.random.default_rng(3)
    keep = (rng.random(len(df)) > 0.2) & ~df.index.isin(range(10, 16))
    shp = _clean(card, str(tmp_path), keep)
    R = W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out"), widths=False, id_tag=0x123,
                      log=lambda m: None)
    assert R["n_kept"] == int(keep.sum()) and R["n_unmatched"] == 0
    # every record is still there, every log block keeps its size
    new_fdd = [f for f in _written_files(R["path"]) if f.endswith(".fdd")]
    assert new_fdd == [f"Combine A/GS3_2630/Profile/RCD/EIC/Documentation/01/{NAME.replace('-1000-', '-1123-')}.fdd"]
    a, b = open(card["fdd"], "rb").read(), open(os.path.join(R["path"], new_fdd[0]), "rb").read()
    assert len(a) == len(b) and W.Layout(b).n == N
    # the decoder reads the kept readings, every attribute as from the original card, and the removed readings left
    # as harvest readings with 0 kg (below the import's minimum yield: read with it, exactly the kept readings)
    ref = df[keep].reset_index(drop=True)
    back, left = _kept_and_left(_decode(R["path"]), ref, R)
    assert len(back) == len(ref) and len(left) == R["n_removed_harvest"] > 0
    _assert_same_readings(back, ref)
    # removed readings: header and sections Off, or (next to a kept reading) as logged; the grain they took set to 0
    # (no grain left for a reader to carry)
    v, _ = G.decode_block(b)
    times = set(ref.Time)
    t_all = pd.Timestamp("2026-07-15T18:00:00.400Z") + pd.to_timedelta(np.arange(N), unit="s")
    t_txt = t_all.strftime("%Y-%m-%d %H:%M:%S.") + (t_all.microsecond // 100000).astype(str)
    removed = [i for i in range(N) if not 60 <= i <= 64 and t_txt[i] not in times]
    flagged = [i for i in removed if v["Header"][i] == 1]
    stayed = [i for i in removed if v["Header"][i] == 0]
    assert all(v["Sec1"][i] == 1 for i in flagged) and len(removed) == R["n_removed"]
    assert len(stayed) == R["n_removed_harvest"] and set(t_txt[stayed]) == set(left.Time)
    kept_rec = {i for i in range(N) if t_txt[i] in times}
    assert all(i - 1 in kept_rec or i + 1 in kept_rec for i in stayed)                    # each next to a kept one
    assert not any(i - 1 in kept_rec or i + 1 in kept_rec for i in flagged)                # no new run edge
    _, Rr, _ = W._records(card["root"], None, None)
    take, _ = W.taken_records(Rr)                  # the grain record of each position, by the decoder's alignment
    taken = [int(take[i]) for i in removed if take[i] >= 0 and np.isfinite(Rr.wet_kg[take[i]])]
    assert len(taken) >= 20 and np.all(v["Mass"][taken] == 0.0)
    others = [i for i in range(N) if i not in set(taken) and i != 120]
    changed = np.flatnonzero(v["Mass"][others] != G.decode_block(a)[0]["Mass"][others])
    assert len(changed) == 0 or hasattr(G, "sms_align")       # else only the folded carried grain changes grain
    # ids: renamed files, cited ids replaced, the zip inside the card not copied
    files = _written_files(R["path"])
    assert not any(f.endswith(".zip") for f in files) and any(f.endswith("global.ver") for f in files)
    fdl = open(os.path.join(R["path"], [f for f in files if f.endswith(".fdl")][0]), encoding="latin1").read()
    assert NAME.replace("-1000-", "-1123-") + ".fdd" in fdl and LOAD.replace("-1000-", "-1123-") in fdl
    assert NAME not in fdl and LOAD not in fdl
    assert any(f.endswith(LOAD.replace("-1000-", "-1123-") + ".fdr") for f in files)
    with zipfile.ZipFile(R["zip"]) as z:                       # the files and an entry for every folder
        names = z.namelist()
        assert sorted(n for n in names if not n.endswith("/")) == files
        dirs = {n for n in names if n.endswith("/")}
        assert {"/".join(f.split("/")[:k]) + "/" for f in files for k in range(1, f.count("/") + 1)} == dirs
    # the check decodes the written card again: every kept reading, nothing else above the minimum yield, grain within
    # half a gram
    ck = R["check"]
    assert (ck["matched"], ck["missing"], ck["extra"], ck["n_grain_differs"]) == (int(keep.sum()), 0, 0, 0)
    assert ck["extra_below_min"] == len(left) and ck["decoded"] == len(back) + len(left)


def test_any_subset_and_no_new_ids(card, tmp_path):
    df = card["df"]
    keep = np.zeros(len(df), bool)
    keep[::3] = True
    shp = _clean(card, str(tmp_path), keep)
    R = W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out"), widths=False, new_ids=False,
                      log=lambda m: None)
    back, _ = _kept_and_left(_decode(R["path"]), df[keep], R)
    _assert_same_readings(back, df[keep])
    assert any(f.endswith(NAME + ".fdd") for f in _written_files(R["path"])) and not R["id_map"]


def test_level2_width_in_whole_sections_on_the_side_the_point_moved(card, tmp_path):
    df = card["df"]
    keep = np.ones(len(df), bool)
    w = df.Swth_Wdth_.to_numpy().copy()
    lat = df.lat.to_numpy().copy()
    narrow = (np.arange(len(df)) % 5 == 0) & np.isclose(w, 3 * SEC_M * C.FT_PER_M)
    w[narrow] = 3.1 * C.FT_PER_M                               # 3.1 m -> two sections (4 m)
    lat[narrow] -= 1.0 / 111_320.0                             # heading east: 1 m to the right is south
    shp = _clean(card, str(tmp_path), keep, Swth_Wdth_=w, lat=lat)
    R = W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out"), id_tag=0x124,
                      log=lambda m: None)
    assert R["n_width_changed"] == int(narrow.sum()) > 0
    back = _decode(R["path"])
    assert np.allclose(back.Swth_Wdth_[narrow], 2 * SEC_M * C.FT_PER_M) and np.allclose(back.Swth_Wdth_[~narrow],
                                                                                          df.Swth_Wdth_[~narrow])
    # the yield follows the written width; grain, distance, moisture unchanged
    area_b = back.Distance_f * back.Swth_Wdth_
    area_o = df.Distance_f * df.Swth_Wdth_
    assert np.all(np.abs(back.Yld_Mass_W * area_b - df.Yld_Mass_W * area_o) / C.SQFT_PER_AC / C.LB_PER_KG
                  <= TOL_KG + 1e-9)
    # the right-hand two sections stay on (the point moved right), the left one is off
    fdd = [f for f in _written_files(R["path"]) if f.endswith(".fdd")][0]
    v, _ = G.decode_block(open(os.path.join(R["path"], fdd), "rb").read())
    t = pd.Timestamp("2026-07-15T18:00:00.400Z") + pd.to_timedelta(np.arange(N), unit="s")
    txt = list(t.strftime("%Y-%m-%d %H:%M:%S.") + (t.microsecond // 100000).astype(str))
    rec = [txt.index(x) for x in df.Time[narrow]]
    assert np.all(v["Sec1"][rec] == 1) and np.all(v["Sec2"][rec] == 0) and np.all(v["Sec3"][rec] == 0)


def test_level3_factor(card, tmp_path):
    df = card["df"]
    keep = np.ones(len(df), bool)
    keep[40:50] = False
    shp = _clean(card, str(tmp_path), keep)
    R = W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out"), factors={"SYNTH0001": 1.1},
                      id_tag=0x125, log=lambda m: None)
    ref = df[keep]
    back, _ = _kept_and_left(_decode(R["path"]), ref, R)
    kg_b = back.Yld_Mass_W.to_numpy() * (back.Distance_f * back.Swth_Wdth_).to_numpy() / C.SQFT_PER_AC / C.LB_PER_KG
    kg_o = ref.Yld_Mass_W.to_numpy() * (ref.Distance_f * ref.Swth_Wdth_).to_numpy() / C.SQFT_PER_AC / C.LB_PER_KG
    assert len(back) == len(ref) and np.all(np.abs(kg_b - 1.1 * kg_o) <= 0.0005 + 1.1 * TOL_KG + 1e-9)
    assert np.allclose(back.Moisture__, ref.Moisture__, rtol=0, atol=0)
    with pytest.raises(W.WriteError):
        W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out2"), factors={"SYNTH0001": 9.0},
                      log=lambda m: None)                       # 45 kg in a record: above the channel's limit


def test_correct_numeric_keeps_the_values_after_the_change(card):
    blk = bytearray(open(card["fdd"], "rb").read())
    L = W.Layout(bytes(blk))
    before, _ = G.decode_block(bytes(blk))
    e = np.zeros(N, np.int64)
    e[[30, 31, 119, 121]] = [-5000, 100, -5006, 7]               # 0 kg, +0.1 kg, 0 kg before the empty record, +7 g
    assert not len(W.correct_numeric(blk, L, "Mass", e))
    after, _ = G.decode_block(bytes(blk))
    exp = before["Mass"].copy()
    exp[[30, 31, 119, 121]] += np.array([-5000, 100, -5006, 7]) * 0.001
    assert np.allclose(after["Mass"], exp, equal_nan=True, rtol=0, atol=1e-9) and np.isnan(after["Mass"][120])
    big = np.zeros(N, np.int64)
    big[50] = 40_000                                              # 40 kg more: above the limit of 32 kg
    assert list(W.correct_numeric(bytearray(blk), L, "Mass", big)) == [50, 51]


def test_clean_file_from_another_card_is_refused(card, tmp_path):
    df = card["df"].copy()
    df["Time"] = "2020-01-01 00:00:00.0"
    shp = C.write_standard(df, os.path.join(str(tmp_path), "other.shp"))
    with pytest.raises(W.WriteError):
        W.write_clean({**SOURCE, "input_root": card["root"]}, shp, str(tmp_path / "out"), log=lambda m: None)
    with pytest.raises(W.WriteError):
        W.write_clean({**SOURCE, "format": "cnh_cn1", "input_root": card["root"]}, shp, str(tmp_path / "o2"),
                      log=lambda m: None)


def test_new_id_map_keeps_the_length_and_avoids_used_values():
    m = W.new_id_map(["a/6a570000-0000-1000-aaaa-000000000001.fdd", "a/6a570000-0000-1001-aaaa-000000000001.fdl",
                      "a/notanid.fdd", "a/6a570000-0000-1000-aaaa-000000000003.txt"], tag=1)
    assert m == {"6a570000-0000-1000-aaaa-000000000001": "6a570000-0000-1002-aaaa-000000000001",
                 "6a570000-0000-1001-aaaa-000000000001": "6a570000-0000-1003-aaaa-000000000001"}
