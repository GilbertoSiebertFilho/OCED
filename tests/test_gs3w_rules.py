# -*- coding: utf-8 -*-
"""engine/formats/jd_gs3_rcd_write.py: the rules of the written card, on synthetic GreenStar 3 cards built here (every
number made up, no grower data). Grain carried by the decoder (sms_align) never moves into a kept reading when a whole
session or a clip-like run of readings is removed; only the sessions of the decoded units are written; another field's
block in a written session is neutralised; empty clean files, outputs inside / around the input and duplicate clean
rows are handled; a written card probes with its date span; the fixed-shift alignment round trip; a header value not
held as a dense value is refused; no kept reading starts or ends a harvesting run the raw card did not have (the
removed readings next to a kept one stay harvest readings of 0 kg, below the import's minimum yield), and the result
says which minimum the card must be read with.

    python -m pytest -q tests
"""
from __future__ import annotations

import os
import struct
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.formats import common as C  # noqa: E402
from engine.formats import jd_gs3_rcd as G  # noqa: E402
from engine.formats import jd_gs3_rcd_write as W  # noqa: E402

LAT0, LON0 = 51.8, -114.1
HOLD = "hold"                                   # a value held as 'unchanged' (no dense delta) in the record
ON_OFF = {"Header": ["dtiHeaderStatusOn", "dtiHeaderStatusOff"], "Rec": ["dtiRecordingStatusOn",
                                                                        "dtiRecordingStatusOff"]}
COLS = [("Moist", 3, None, 0.01, 2.5, 14.0), ("Mass", 3, None, 0.001, 32.0, 0.0), ("Header", 1, "Header", 0, 0, 0),
        ("Sec1", 1, "Rec", 0, 0, 0), ("Sec2", 1, "Rec", 0, 0, 0), ("Sec3", 1, "Rec", 0, 0, 0),
        ("Lat", 4, None, 1e-9, 0.00045, LAT0), ("Lon", 4, None, 1e-9, 0.00045, LON0), ("Head", 3, None, 0.01, 5.0, 0.0),
        ("DD", 3, None, 1.0, 5000.0, 0.0), ("Elev", 3, None, 0.001, 1.0, 1000.0), ("Time", 4, None, 1.0, 65500.0, 0.0)]
OPTS = C.DecodeOptions(shrink="one_sided")
SMS = hasattr(G, "sms_align")
quiet = lambda m: None  # noqa: E731


def _column(name, typ, enum, res, limit, init):
    b = struct.pack("<HHH", typ, 0, len(name)) + name.encode("latin1") + b"\x00"
    if typ == 1:
        names = b"".join(struct.pack("<H", len(e)) + e.encode("latin1") for e in ON_OFF[enum])
        return b + struct.pack("<HH", len(ON_OFF[enum]), len(names)) + names
    return b + struct.pack("<H", 24) + struct.pack("<ddd", res, limit, init)


def records(n=150, lat=LAT0, up=range(60, 65), early_kg=1.0, up_kg=5.0, still=(), hold=()):
    """Absolute values per record, heading east at 2 m/s. Grain 5 kg from record 14 on; ``early_kg`` in records 0-13
    (passed over by every position: grain the decoder carries) and ``up_kg`` in the records the header-up positions
    ``up`` take 14 s later (carried too); no grain / moisture value in record 120; distance 0 in ``still``; the header
    value of ``hold`` held as 'unchanged'."""
    dlon = 2.0 / (111_320.0 * np.cos(np.radians(LAT0)))
    up = set(up)
    taken_by_up = {i + 14 for i in up}
    out = []
    for i in range(n):
        u = i in up
        mass = early_kg if i < 14 else (up_kg if i in taken_by_up else 5.0 + (i % 7) / 1000.0)
        out.append({"Moist": None if i == 120 else 14.0 + i / 100.0, "Mass": None if i == 120 else mass,
                    "Header": HOLD if i in hold else (1 if u else 0), "Sec1": 1 if u else 0, "Sec2": 1 if u else 0,
                    "Sec3": 1 if u or 90 <= i <= 94 else 0, "Lat": lat, "Lon": LON0 + i * dlon, "Head": 90.0,
                    "DD": 0.0 if i in still else 200.0, "Elev": 1000.0, "Time": i * 1000.0 + (i * 37) % 50})
    return out


def encode_block(recs) -> bytes:
    blk = struct.pack("<HH", 1, 8) + b"synthetc" + struct.pack("<HHH", 1, 2, len(COLS))
    blk += b"".join(_column(*c) for c in COLS)
    nb = (len(COLS) + 7) // 8
    prev = {c[0]: c[5] for c in COLS}
    for r in recs:
        none_bits = hold_bits = 0
        fmt, vals = "<", []
        for k, (name, typ, enum, res, _, _) in enumerate(COLS):
            v = r[name]
            if v is None:
                none_bits |= 1 << k
                prev[name] = 0.0
                continue
            if v == HOLD:
                hold_bits |= 1 << k
                continue
            if typ == 1:
                fmt += "h"
                vals.append(int(v))
            else:
                fmt += "i" if typ == 4 else "h"
                vals.append(int(round((v - prev[name]) / res)))
                prev[name] = prev[name] + vals[-1] * res
        blk += (struct.pack("<HB", 2, 0) + none_bits.to_bytes(nb, "little") + hold_bits.to_bytes(nb, "little")
                + bytes(nb) + struct.pack(fmt, *vals))
    return blk + struct.pack("<H", 4)


SECTION = ('<Section id="{i}"><vrLateralOffset value="{lat}" sourceUOM="mm"/><RecordingStateElement>'
           '<DefinedTypeColumn columnID="Sec{k}"/></RecordingStateElement>'
           '<vrSectionWidth value="2000" sourceUOM="mm"/></Section>')


def _block_xml(field, erid, start, load, fdd_name, pos):
    return f"""<RCDLogBlock><ConfigBlock>
<Setup>
 <Participant><Client name="Synthetic client"/></Participant><Farm name="Synthetic farm"/>
 <Field name="{field}" erid="{{{erid}}}"/>
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
 {SECTION.format(i=10, lat=-2000, k=1)}{SECTION.format(i=11, lat=0, k=2)}{SECTION.format(i=12, lat=2000, k=3)}
 <NavigationReference><vrInlineOffset value="0" sourceUOM="in"/><vrLateralOffset value="0" sourceUOM="in"/>
  <vrLatitude columnID="Lat"/><vrLongitude columnID="Lon"/><vrHeading columnID="Head"/>
  <vrDeltaDistance columnID="DD" sourceUOM="cm"/><vrElevation columnID="Elev"/>
  <dtNavigationType value="dtiComputedImplement"/></NavigationReference>
</EquipmentConfiguration>
<LogTaskRegion timeStamp="{start}" timeColumnID="Time" logInterval="1000" cropYear="2026">
 <Operation><dtOperationClass value="dtiHarvest"/><ProductRef eridRef="{{00000000-0000-0000-0000-0000000000aa}}"/>
  <MeterRef idRef="1"/><MeterRef idRef="2"/><MeterRef idRef="3"/>
  <LoadIdentityRef idRef="{{{load}}}"/></Operation>
</LogTaskRegion></ConfigBlock>
<LogDataBlock><EvenByteDelta filePathName="Documentation\\01\\{fdd_name}.fdd" filePosition="{pos}"/></LogDataBlock>
</RCDLogBlock>"""


FIELD1 = ("Synthetic field one", "00000000-0000-0000-0000-00000000f1e1")
FIELD2 = ("Synthetic field two", "00000000-0000-0000-0000-00000000f2e2")


def make_card(folder, sessions):
    """sessions: [(guid, [(field, start ISO, load guid, records), ...]), ...] -> one card under folder/Combine A."""
    eic = os.path.join(folder, "Combine A", "GS3_2630", "Profile", "RCD", "EIC")
    doc = os.path.join(eic, "Documentation", "01")
    os.makedirs(doc, exist_ok=True)
    with open(os.path.join(eic, "global.ver"), "wb") as fh:
        fh.write(b"\x07\x00\x00\x00" + b"\xff" * 1020)
    for guid, blocks in sessions:
        data, xml = b"", []
        for (field, erid), start, load, recs in blocks:
            xml.append(_block_xml(field, erid, start, load, guid, len(data)))
            data += encode_block(recs)
            with open(os.path.join(doc, load + ".fdr"), "w", encoding="latin1") as fh:
                fh.write(f'<?xml version="1.0"?><RCDLoadFile><LoadIdentity loadNumber="7" erid="{{{load}}}"/>'
                         "</RCDLoadFile>")
        with open(os.path.join(doc, guid + ".fdd"), "wb") as fh:
            fh.write(data)
        with open(os.path.join(doc, guid + ".fdl"), "w", encoding="latin1") as fh:
            fh.write('<?xml version="1.0"?>\n<RCDLogFile>' + "\n".join(xml) + "</RCDLogFile>\n")
    return folder


def unit_of(root, field):
    return [u.id for u in G.list_units(root) if u.field == field[0]]


def decode(root, units=None, **kw):
    df, rep = G.decode(root, units, OPTS, log=quiet, **kw)
    return df, rep


def wet_kg(df):
    return (df.Yld_Mass_W * df.Distance_f * df.Swth_Wdth_ / C.SQFT_PER_AC / C.LB_PER_KG).to_numpy()


def clean_file(df, path):
    return C.write_standard(df, path)


def kept_and_left(back, ref, R):
    """(the readings decoded back that the clean file holds, the others): the others are only harvest records the
    writer left as harvest readings (removed_as_harvest), every one without grain and below the import's minimum
    yield, so that a reader with that minimum reads exactly the clean readings."""
    key = set(zip(ref.Machine.astype(str), ref.Time.astype(str)))
    ink = np.fromiter(((m, t) in key for m, t in zip(back.Machine.astype(str), back.Time.astype(str))), bool,
                      len(back))
    left = back[~ink]
    y = left.Yld_Vol_Dr.to_numpy(float)
    assert len(left) <= R["n_removed_harvest"] + R["n_not_offered_harvest"]
    assert not (np.nan_to_num(wet_kg(left)) > 0).any() and not (np.isfinite(y) & (y >= G.MONITOR_MIN_YIELD)).any()
    return back[ink].reset_index(drop=True), left.reset_index(drop=True)


def source(root, units=None, **kw):
    return {"format": "jd_gs3_rcd", "kind": "decoded", "input_root": root, "unit_ids": units, "tz_offset_h": None,
            "decoder_kwargs": kw, "options": {"shrink": "one_sided"}}


S_A, S_B = "6a570000-0000-1000-aaaa-000000000001", "6a570e10-0000-1000-aaaa-000000000003"
L_A, L_B = "6a570010-0000-1000-aaaa-000000000002", "6a570e20-0000-1000-aaaa-000000000004"


@pytest.fixture(scope="module")
def two_sessions(tmp_path_factory):
    """One field, one combine, two sessions an hour apart; both with grain the decoder carries."""
    root = make_card(str(tmp_path_factory.mktemp("gs3two")), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, records())]),
        (S_B, [(FIELD1, "2026-07-15T19:00:00.400Z", L_B, records(lat=LAT0 + 0.0001))])])
    df, rep = decode(root)
    return {"root": root, "df": df, "rep": rep}


@pytest.mark.skipif(not SMS, reason="the decoder has no sms_align (no carried grain)")
@pytest.mark.parametrize("mask", ["whole_session", "clip_run"])
def test_removed_grain_never_moves_into_kept_readings(two_sessions, tmp_path, mask):
    df, root = two_sessions["df"], two_sessions["root"]
    al = two_sessions["rep"]["alignment"]
    assert al["kg_too_early"] > 10 and al["kg_not_harvesting"] > 10        # the original card carries grain
    first = (df.Time < "2026-07-15 18:59").to_numpy()                       # the readings of the first session
    if mask == "whole_session":
        keep = ~first
    else:
        i = np.arange(len(df))
        keep = ~(first & (i >= 30) & (i <= 100))                            # a run of readings, as a clip removes
    shp = clean_file(df[keep], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root), shp, str(tmp_path / "out"), widths=False, id_tag=0x101, log=quiet)
    back, rep2 = decode(R["path"])
    ref = df[keep].reset_index(drop=True)
    back, left = kept_and_left(back, ref, R)
    assert len(back) == len(ref) == R["n_kept"] and R["n_removed"] == int((~keep).sum())
    assert len(left) == R["n_removed_harvest"] == {"whole_session": 0, "clip_run": 2}[mask]
    cols = [c for c in ref.columns if c not in ("Obj__Id", "Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr")]
    pd.testing.assert_frame_equal(back[cols].reset_index(drop=True), ref[cols], check_exact=True)
    d = wet_kg(back) - wet_kg(ref)
    lost_max = R["grain"]["kg"]["max_kept_without_own_record"]
    # no grain moves INTO a kept reading; a kept reading loses at most its carried grain when it has no record
    assert d.max() <= 0.0005 + 1e-9 and d.min() >= -(lost_max + 0.0005 + 1e-9)
    big = np.abs(d) > 0.0005 + 1e-9
    assert int(big.sum()) <= R["grain"]["n_kept_without_own_record"]
    if big.any():
        assert any("took no grain record of their own" in w for w in R["warnings"])
    # nothing is left on the written card for a reader to carry
    a2 = rep2["alignment"]
    assert a2["kg_not_harvesting"] == 0 and a2["kg_too_early"] == 0 and a2["kg_carried"] == 0
    assert abs(R["grain"]["kg"]["written"] - (R["grain"]["kg"]["kept"] - R["grain"]["kg"]["kept_without_own_record"])) < 0.0005 * len(ref) + 1e-6
    ck = R["check"]
    assert (ck["matched"], ck["missing"], ck["extra"], ck["extra_below_min"]) == (len(ref), 0, 0, len(left))
    assert ck["n_grain_differs"] == int(big.sum())


@pytest.mark.skipif(not SMS, reason="the decoder has no sms_align")
def test_keep_all_decodes_back_and_only_the_carry_is_folded(two_sessions, tmp_path):
    df, root = two_sessions["df"], two_sessions["root"]
    shp = clean_file(df, str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root), shp, str(tmp_path / "out"), widths=False, id_tag=0x102, log=quiet)
    back, _ = decode(R["path"])
    assert len(back) == len(df) and R["n_removed"] == 0 and R["n_not_offered"] == 0
    d = wet_kg(back) - wet_kg(df)
    assert d.max() <= 0.0005 + 1e-9 and d.min() >= -(R["grain"]["kg"]["max_kept_without_own_record"] + 0.0005 + 1e-9)


def test_only_the_sessions_of_the_decoded_units_are_written(tmp_path):
    root = make_card(str(tmp_path / "card"), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, records())]),
        (S_B, [(FIELD2, "2026-07-15T19:00:00.400Z", L_B, records(lat=LAT0 + 0.001))])])
    u1 = unit_of(root, FIELD1)
    df, _ = decode(root, u1)
    shp = clean_file(df.iloc[::2], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root, u1), shp, str(tmp_path / "out"), id_tag=0x103, log=quiet)
    files = sorted(os.path.basename(os.path.join(d, f)) for d, _, fs in os.walk(R["path"]) for f in fs)
    new = {k: R["id_map"][k] for k in (S_A, L_A)}
    assert files == sorted([new[S_A] + ".fdd", new[S_A] + ".fdl", new[L_A] + ".fdr", "global.ver"])
    assert [u.field for u in G.list_units(R["path"])] == [FIELD1[0]]
    assert R["left_out"]["sessions"] == 1 and R["left_out"]["load files"] == 1
    assert any("not written" in n and "1 sessions" in n for n in R["notes"])
    assert S_B not in R["id_map"]                              # the other field's files are neither copied nor renamed


def test_another_fields_block_in_a_written_session_is_neutralised(tmp_path):
    root = make_card(str(tmp_path / "card"), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, records()),
               (FIELD2, "2026-07-15T18:30:00.400Z", L_B, records(lat=LAT0 + 0.001))])])
    u1, u2 = unit_of(root, FIELD1), unit_of(root, FIELD2)
    df, _ = decode(root, u1)
    shp = clean_file(df, str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root, u1), shp, str(tmp_path / "out"), widths=False, id_tag=0x104, log=quiet)
    assert any("share a session" in w for w in R["warnings"])
    back, _ = decode(R["path"], u1)
    assert len(back) == len(df)
    _, R2, _ = W._records(R["path"], u2, None)                 # the other field: still readable, nothing in it
    assert not R2.harvest.any() and np.nansum(R2.wet_kg) == 0 and len(R2) == 150
    with pytest.raises(ValueError):
        decode(R["path"], u2)


def test_empty_clean_file_is_refused(two_sessions, tmp_path):
    import geopandas as gpd
    g = gpd.GeoDataFrame({"Machine": pd.Series([], dtype=str), "Time": pd.Series([], dtype=str)},
                         geometry=gpd.points_from_xy([], []), crs="EPSG:4326")
    p = str(tmp_path / "empty.shp")
    g.to_file(p, driver="ESRI Shapefile")
    with pytest.raises(W.EmptyCleanError):
        W.write_clean(source(two_sessions["root"]), p, str(tmp_path / "out"), log=quiet)
    assert not os.path.exists(tmp_path / "out")
    with pytest.raises(W.EmptyCleanError):
        W.write_clean(source(two_sessions["root"]), str(tmp_path / "missing.shp"), str(tmp_path / "out"), log=quiet)


def test_output_never_in_around_or_over_the_input(two_sessions, tmp_path):
    root = two_sessions["root"]
    shp = clean_file(two_sessions["df"].iloc[:50], str(tmp_path / "clean.shp"))
    src = source(root)
    for out_dir, name in ((root, None), (os.path.join(root, "Combine A", "x"), None),
                          (os.path.dirname(root), os.path.basename(root)), (str(tmp_path), "a/b"),
                          (str(tmp_path), "..")):
        with pytest.raises(W.OutputError):
            W.write_clean(src, shp, out_dir, folder_name=name, log=quiet)
    # a folder with other files is not replaced; a card written before is
    other = tmp_path / "o1" / "card_clean"
    other.mkdir(parents=True)
    (other / "notes.txt").write_text("keep me")
    with pytest.raises(W.OutputError):
        W.write_clean(src, shp, str(tmp_path / "o1"), folder_name="card_clean", log=quiet)
    assert (other / "notes.txt").read_text() == "keep me"
    R1 = W.write_clean(src, shp, str(tmp_path / "o2"), folder_name="card_clean", id_tag=0x105, log=quiet)
    R2 = W.write_clean(src, shp, str(tmp_path / "o2"), folder_name="card_clean", id_tag=0x106, log=quiet)
    assert R1["path"] == R2["path"] and set(R2["id_map"].values()) <= {
        os.path.splitext(f)[0] for _, _, fs in os.walk(R2["path"]) for f in fs}
    assert not any("-1105-" in f for _, _, fs in os.walk(R2["path"]) for f in fs)   # the earlier card is gone
    assert G.find_sessions(root) and len(G.find_sessions(root)) == 2                 # the input is untouched


def test_duplicate_clean_rows_count_once(two_sessions, tmp_path):
    df = two_sessions["df"].iloc[:40]
    shp = clean_file(pd.concat([df, df.iloc[:5]], ignore_index=True), str(tmp_path / "clean.shp"))
    R = W.write_clean(source(two_sessions["root"]), shp, str(tmp_path / "out"), id_tag=0x107, log=quiet)
    assert R["n_kept"] == 40 and R["n_duplicate_rows"] == 5 and R["n_clean_rows"] == 45
    assert any("repeat the machine and time" in w for w in R["warnings"])


def test_can_write(two_sessions, tmp_path):
    assert W.can_write(source(two_sessions["root"])) == (True, "")
    for bad in (None, {"format": "cnh_cn1"}, {**source(two_sessions["root"]), "input_root": str(tmp_path / "gone")},
                {**source(two_sessions["root"]), "kind": "export"}):
        ok, why = W.can_write(bad)
        assert ok is False and why
    with pytest.raises(W.InputGoneError):
        W.write_clean({**source(two_sessions["root"]), "input_root": str(tmp_path / "gone")}, "x.shp",
                      str(tmp_path / "out"), log=quiet)
    assert W.FORMAT_ID == "jd_gs3_rcd" and W.LABEL and issubclass(W.OutputError, ValueError)


def test_written_card_probes_with_its_date_span(two_sessions, tmp_path):
    shp = clean_file(two_sessions["df"].iloc[:60], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(two_sessions["root"]), shp, str(tmp_path / "out"), id_tag=0xabc, log=quiet)
    p0, p1 = G.probe(two_sessions["root"]), G.probe(R["path"])
    span = p0.summary.split(" log sessions (.fdl + .fdd)")[1].split("; crops")[0]
    assert " - " in span and "2026" in span and span in p1.summary         # the span read from the file names
    for old, new in R["id_map"].items():
        assert "-1abc-" in new or "-1abd-" in new
        assert G.guid_time(new) == G.guid_time(old) is not None


def test_fixed_shift_alignment_round_trip_and_records_never_offered(tmp_path):
    root = make_card(str(tmp_path / "card"), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, records(early_kg=0.0, up_kg=0.0, still=(30, 31)))])])
    df, rep = decode(root, alignment="shift")
    assert rep["pre_step"]["stationary"] == 2
    keep = np.ones(len(df), bool)
    keep[40:55] = False
    shp = clean_file(df[keep], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root, alignment="shift"), shp, str(tmp_path / "out"), widths=False, id_tag=0x108,
                      log=quiet)
    back, _ = decode(R["path"], alignment="shift")
    ref = df[keep].reset_index(drop=True)
    back, left = kept_and_left(back, ref, R)
    assert len(left) == R["n_removed_harvest"] == 2                 # the first and last removed reading
    pd.testing.assert_frame_equal(back.drop(columns="Obj__Id"), ref.drop(columns="Obj__Id"), check_exact=True)
    assert R["n_removed"] == 15 and R["n_not_offered"] == rep["n_records_read"] - len(df) - sum(
        rep["pre_step"][k] for k in ("header_up", "sections_off", "no_gnss"))
    assert any("fixed-shift alignment" in w for w in R["warnings"])
    assert any("never offered" in n for n in R["notes"])


def test_a_header_value_not_held_dense_is_refused(tmp_path):
    root = make_card(str(tmp_path / "card"), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, records(hold=(45,)))])])
    df, _ = decode(root)
    keep = np.ones(len(df), bool)
    keep[44:47] = False                                        # record 45 has to be flagged: its header is held
    shp = clean_file(df[keep], str(tmp_path / "clean.shp"))
    with pytest.raises(W.WriteError, match="does not rewrite in place"):
        W.write_clean(source(root), shp, str(tmp_path / "out"), log=quiet)
    assert not os.path.exists(tmp_path / "out" / "card_clean")


# ------------------------------------------------------------------------------------------------- run edges
# a card with a pause of the log (6 s between records 99 and 100); the clean file removes a run of readings (30-40),
# single readings inside a run (70, 75), the reading after the header-up records 60-64 (65) and the readings just after
# the pause (100-104)
REMOVE = (*range(30, 41), 65, 70, 75, *range(100, 105))
LEFT_BUFFER = {30, 40, 65, 70, 75, 104}          # next to a kept reading in the same run: stay harvest readings
NEW_EDGES_NONE = {29, 41, 66, 69, 71, 74, 76, 105}   # kept readings next to a removed one: run edges if switched off


def _rec_time(i):
    t = pd.Timestamp("2026-07-15T18:00:00.400Z") + pd.Timedelta(seconds=i + (5 if i >= 100 else 0))
    return t.strftime("%Y-%m-%d %H:%M:%S.") + str(t.microsecond // 100000)


@pytest.fixture(scope="module")
def paused(tmp_path_factory):
    recs = records()
    for r in recs[100:]:
        r["Time"] += 5000.0                       # the log pauses: record 100 comes 6 s after record 99
    root = make_card(str(tmp_path_factory.mktemp("gs3pause")), [
        (S_A, [(FIELD1, "2026-07-15T18:00:00.400Z", L_A, recs)])])
    df, _ = decode(root)
    return {"root": root, "df": df, "removed": df.Time.isin([_rec_time(i) for i in REMOVE]).to_numpy()}


def runs(path):
    """The records of a card in time order (one log block here: the row is the record number), harvesting or not,
    and per record whether the record before / after it is in the same log block with no pause (<= 2.5 s)."""
    _, R, _ = W._records(path, None, None)
    R = R.sort_values(["Machine", "t_ms"], kind="stable").reset_index(drop=True)
    d = np.diff(R.t_ms.to_numpy())
    same = (R.bi.to_numpy()[1:] == R.bi.to_numpy()[:-1]) & (d <= 2500)
    return R, np.r_[False, same], np.r_[same, False]


@pytest.mark.parametrize("mode", [None, "buffer", "full", "none"])
def test_no_kept_reading_gets_a_run_edge_the_raw_card_did_not_have(paused, tmp_path, mode):
    df, root = paused["df"], paused["root"]
    keep = ~paused["removed"]
    shp = clean_file(df[keep], str(tmp_path / "clean.shp"))
    kw = {} if mode is None else {"removed_as_harvest": mode}
    R = W.write_clean(source(root), shp, str(tmp_path / "out"), widths=False, id_tag=0x109, log=quiet, **kw)
    A, prev, nxt = runs(root)
    B, _, _ = runs(R["path"])
    assert (A.t_ms.to_numpy() == B.t_ms.to_numpy()).all()
    hr, hw = A.harvest.to_numpy(), B.harvest.to_numpy()
    kept = A.Time.isin(df.Time[keep]).to_numpy() & hr
    assert not (hw & ~hr).any()                                    # no record becomes a harvest record
    gone = hr & ~hw                                                # switched off by the writer
    edge = kept & ((np.r_[False, gone[:-1]] & prev) | (np.r_[gone[1:], False] & nxt))
    left = set(np.flatnonzero(hr & hw & ~kept).tolist())
    if mode in (None, "buffer"):                                    # the default
        assert not edge.any() and left == LEFT_BUFFER
        assert set(np.flatnonzero(gone).tolist()) == set(REMOVE) - LEFT_BUFFER   # 100-103: after the pause, off
        assert R["removed_as_harvest"] == "buffer" and R["n_removed_harvest"] == len(LEFT_BUFFER)
    elif mode == "full":                                            # the harvest state as logged
        assert not edge.any() and not gone.any() and left == set(REMOVE) and R["n_removed_harvest"] == len(REMOVE)
    else:                                                           # every removed reading switched off
        assert set(np.flatnonzero(edge).tolist()) == NEW_EDGES_NONE and not left and R["n_removed_harvest"] == 0
        assert any(w.startswith(f"run edges: {len(NEW_EDGES_NONE)} kept readings") for w in R["warnings"])
    assert R["n_new_run_edges"] == int(edge.sum()) and R["n_removed"] == len(REMOVE)


def test_removed_readings_left_read_0_kg_and_the_import_minimum_leaves_them_out(paused, tmp_path):
    df, root = paused["df"], paused["root"]
    y = df.Yld_Vol_Dr.to_numpy(float)
    at_min = np.isfinite(y) & (y >= G.MONITOR_MIN_YIELD)            # the clean file: the import's minimum applied
    assert (~at_min).sum() >= 10                                    # readings without grain (the pause, the end)
    # (the readings that take no grain record of their own hold only carried grain, which the card cannot hold: a
    # warning of its own; left out of this clean file)
    A, prev, nxt = runs(root)
    take, _ = W.taken_records(A)
    own = df.Time.isin(A.Time[take >= 0]).to_numpy()
    assert (at_min & ~own).sum() >= 3
    keep = at_min & own & ~paused["removed"]
    shp = clean_file(df[keep], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root), shp, str(tmp_path / "out"), widths=False, id_tag=0x10a, log=quiet)
    ref = df[keep].reset_index(drop=True)
    back, _ = decode(R["path"])
    yb = back.Yld_Vol_Dr.to_numpy(float)
    read = back[np.isfinite(yb) & (yb >= G.MONITOR_MIN_YIELD)].reset_index(drop=True)
    # read with the import's minimum: exactly the clean readings, every attribute, the grain within half a gram
    cols = [c for c in ref.columns if c not in ("Obj__Id", "Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr")]
    pd.testing.assert_frame_equal(read[cols], ref[cols], check_exact=True)
    assert np.all(np.abs(wet_kg(read) - wet_kg(ref)) <= 0.0005 + 1e-9)
    # without it: also the removed readings next to a kept one, each with 0 kg (0 bu/ac)
    kept = A.Time.isin(ref.Time).to_numpy() & A.harvest.to_numpy()
    rem = A.harvest.to_numpy() & ~kept
    nb = rem & ((np.r_[False, kept[:-1]] & prev) | (np.r_[kept[1:], False] & nxt))
    other = back[~back.Time.isin(ref.Time)]
    assert set(other.Time) == set(A.Time[nb]) and len(other) == R["n_removed_harvest"] >= len(LEFT_BUFFER) + 2
    assert np.all(wet_kg(other) == 0.0) and np.all(other.Yld_Vol_Dr.to_numpy(float) == 0.0)
    # on the card: every grain record a removed reading takes holds 0 kg; the kept readings' records their grain
    B, _, _ = runs(R["path"])
    t = take[rem & (take >= 0)]
    assert len(t) >= 15 and np.all(np.nan_to_num(B.wet_kg.to_numpy()[t]) == 0.0)
    # the writer's own check reads it the same way
    ck = R["check"]
    assert (ck["matched"], ck["missing"], ck["extra"], ck["n_grain_differs"]) == (len(ref), 0, 0, 0)
    assert ck["extra_below_min"] == len(other) and ck["decoded_at_min"] == len(ref) == len(read)
    es = R["expected_summary"]
    assert es["gps_count"] == len(ref) and es["n_left_below_min"] == len(other) and es["min_yield"] == 5.0
    assert any("read with the import's minimum it holds exactly the clean readings" in n for n in R["notes"])


def test_the_result_says_which_minimum_yield_the_card_needs(paused, tmp_path):
    df, root = paused["df"], paused["root"]
    shp = clean_file(df[~paused["removed"]], str(tmp_path / "clean.shp"))
    R = W.write_clean(source(root), shp, str(tmp_path / "out"), widths=False, id_tag=0x10b, log=quiet)
    n = len(LEFT_BUFFER)
    assert R["min_yield_needed"] == G.MONITOR_MIN_YIELD == 5.0 and R["n_removed_harvest"] == n
    cav = [x for x in R["notes"] if x.startswith("READ THIS CARD WITH A MINIMUM YIELD ABOVE 0")]
    assert len(cav) == 1
    for part in ("the import's minimum, 5 bu/ac dry", f"{n:,} harvest records the clean file does not hold",
                 f"({n:,} readings the import's minimum / maximum or the cleaning removed", "0 kg of grain",
                 "each next to a kept reading", f"Read with a minimum of 0 they would be up to {n:,} points of 0 yield"):
        assert part in cav[0], part
    assert any(f"{len(REMOVE) - n:,} set to not harvesting, {n:,} left as harvest readings with 0 kg" in x
               for x in R["notes"])
    assert any(x.startswith("run edges: 0 kept readings") for x in R["notes"])
    assert any("in a scratch project first (start / stop delay 0, minimum yield 5 bu/ac, not 0)" in x
               for x in R["notes"])
    # every removed reading switched off: no reading of 0 kg, no minimum needed, the new run edges a warning
    R0 = W.write_clean(source(root), shp, str(tmp_path / "out0"), widths=False, id_tag=0x10c, log=quiet,
                       removed_as_harvest="none")
    assert R0["min_yield_needed"] is None and R0["n_removed_harvest"] == 0
    assert not any("MINIMUM YIELD ABOVE 0" in x or "bu/ac, not 0" in x for x in R0["notes"] + R0["warnings"])
    assert any("run edges" in w and "removed_as_harvest 'buffer' or 'full'" in w for w in R0["warnings"])
    with pytest.raises(W.WriteError, match="removed_as_harvest"):
        W.write_clean(source(root), shp, str(tmp_path / "out1"), log=quiet, removed_as_harvest="some")
    assert not os.path.exists(tmp_path / "out1")
