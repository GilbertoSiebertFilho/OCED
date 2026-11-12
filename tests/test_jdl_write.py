# -*- coding: utf-8 -*-
"""The .jdl writer (engine/formats/jd_jdl_write.py) on a synthetic John Deere card (tests/synthetic_jdl.py), for both
ways jd_jdl makes readings (points="sms", its default, and points="ops_center"): the encoder gives the original bytes
back, a clean subset is decoded again as exactly the kept readings (with a narrowed width and a combine factor), the
written logs carry new GUIDs everywhere the card cites them, keep-all writes the card byte for byte, and an empty or
foreign clean file is refused."""
import os

import numpy as np
import pyogrio
import pytest

from engine import run as er
from engine.formats import jd_jdl as J
from engine.formats import jd_jdl_write as W
from tests import synthetic_jdl as S

MODES = ("sms", "ops_center")
T0 = S.REF_MS + 500


def _decode(tmp_path, mode="sms", **card_kw):
    card = S.make_card(str(tmp_path / "card"), **card_kw)
    work = str(tmp_path / "work")
    cands = er.open_input([card["root"]], work, log=lambda m: None)
    cand = [c for c in cands if c["kind"] == "raw"][0]
    assert cand["decoder"] == J.FORMAT_ID
    kw = {} if mode == "sms" else {"points": mode}
    dec = er.decode(cand, None, None, work, log=lambda m: None, tag="syn", **kw)
    assert dec["report"]["points"] == mode
    return card, dec


@pytest.fixture()
def decoded(tmp_path):
    return _decode(tmp_path)


def _write_subset(dec, path, keep, narrow_obj=None, r=0.6):
    g = pyogrio.read_dataframe(dec["shp"])
    c = g[keep(g)].copy()
    if narrow_obj is not None:
        i = c.index[c.Obj__Id == narrow_obj][0]
        c.loc[i, "Swth_Wdth_"] = c.loc[i, "Swth_Wdth_"] * r
        for col in ("Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr"):
            c.loc[i, col] = c.loc[i, col] / r
    pyogrio.write_dataframe(c, path)
    return g, c


def _subset(g):
    return (g.Obj__Id.values % 7 != 0) & (g.Obj__Id.values > 3)


def _redecode(res, dec, mode):
    return J.decode_detailed(res["path"], dec["report"]["units"], None, log=lambda m: None, points=mode)[0]


def _kept_original(dec, c, mode):
    df0 = J.decode_detailed(dec["report"]["input_root"], dec["report"]["units"], None, log=lambda m: None,
                            points=mode)[0]
    k = df0.set_index(["Dataset", "Obj__Id"])
    return k.loc[list(zip(c.Dataset, c.Obj__Id))].reset_index()


def test_jdl_writer_encoder_gives_the_bytes_back(decoded):
    card, _ = decoded
    metas = sorted((J.read_meta(p) for p in card["files"]), key=lambda m: m.ref_ms)
    n = 0
    for i, m in enumerate(metas):
        lg = W._Log(m, i)
        assert lg.serialize() == lg.data
        for r in lg.records():
            assert not r.bad
            assert W._enc_body(r, lg, r.samples, r.anchor, r.at) == r.raw
            n += 1
    assert n >= 15


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_round_trip_subset_width_and_ids(tmp_path, mode):
    card, dec = _decode(tmp_path, mode)
    clean_shp = str(tmp_path / "syn_clean.shp")
    g, c = _write_subset(dec, clean_shp, _subset, narrow_obj=30)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    assert res["n_kept"] == len(c) and res["n_removed"] == len(g) - len(c)
    assert res["points"] == mode
    rt = res["round_trip"]
    assert rt["ok"], rt
    assert rt["n_missing"] == 0 and rt["n_extra"] == 0
    assert rt["non_kept"]["n_with_width"] == 0 and rt["non_kept"]["n_with_sections_on"] == 0
    # the written card decoded on its own: the kept readings, same values; the narrowed one at the written width
    df1 = _redecode(res, dec, mode)
    assert len(df1) == len(c)
    a = c.set_index("Time").sort_index()
    b = df1.set_index("Time").sort_index()
    assert list(a.index) == list(b.index)
    for col in ("Duration_s", "Distance_f", "Speed_mph_", "Moisture__"):
        np.testing.assert_allclose(b[col].values, a[col].values, rtol=1e-12)
    i = a.index[a.Obj__Id == 30][0]
    w_clean = a.loc[i, "Swth_Wdth_"]
    if mode == "sms":
        # SMS takes the width from the sections: 0.6 x 9 m = 5.4 m is written as the nearest run, 4 sections (6 m)
        assert abs(b.loc[i, "Swth_Wdth_"] - 6.0 / 0.3048) < 1e-9
        assert b.loc[i, "n_act"] == 4
        np.testing.assert_allclose(b.loc[i, "Yld_Vol_Dr"] / a.loc[i, "Yld_Vol_Dr"], w_clean / b.loc[i, "Swth_Wdth_"],
                                   rtol=1e-9)
        np.testing.assert_allclose([b.loc[i, "lon"], b.loc[i, "lat"]],
                                   [_kept_original(dec, c, mode).set_index("Time").loc[i, x] for x in ("lon", "lat")],
                                   rtol=1e-12)
    else:
        assert abs(b.loc[i, "Swth_Wdth_"] - w_clean) < 0.002            # 1 mm steps of DDI 12001
        assert abs(b.loc[i, "Yld_Vol_Dr"] / a.loc[i, "Yld_Vol_Dr"] - 1) < 1e-3
    others = a.index != i
    np.testing.assert_allclose(b.Yld_Vol_Dr.values[others], a.Yld_Vol_Dr.values[others], rtol=1e-9)
    # new identifiers: file names, definitions, block headers, links and version.txt
    written = [os.path.join(dp, f) for dp, _, fs in os.walk(res["path"]) for f in fs]
    jdl = [p for p in written if p.endswith(".jdl")]
    assert len(jdl) == 2
    for p in jdl:
        data = open(p, "rb").read()
        for old in card["guids"]:
            assert old.encode() not in data
        assert os.path.basename(p)[:-4].encode() in data
    ver = open([p for p in written if p.endswith("version.txt")][0], "rb").read().decode()
    assert sorted(x.split(",")[0] for x in ver.split("\n")) == sorted(os.path.basename(p)[:-4] for p in jdl)
    assert os.path.exists(res["zip"])
    assert any("not yet tested in Ag Leader SMS" in x for x in res["notes"])
    for k in ("path", "zip", "n_kept", "n_removed", "files_changed", "notes", "warnings", "expected_summary"):
        assert k in res


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_combine_factor(tmp_path, mode):
    _, dec = _decode(tmp_path, mode)
    clean_shp = str(tmp_path / "syn_clean.shp")
    _, c = _write_subset(dec, clean_shp, _subset)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), factors={S.VIN: 1.1}, log=lambda m: None)
    assert res["round_trip"]["ok"], res["round_trip"]
    df1 = _redecode(res, dec, mode)
    a = c.set_index("Time").sort_index()
    b = df1.set_index("Time").sort_index()
    ok = a.Yld_Vol_Dr.values > 1
    np.testing.assert_allclose(b.Yld_Vol_Dr.values[ok], 1.1 * a.Yld_Vol_Dr.values[ok], rtol=1e-6)
    np.testing.assert_allclose(b.Swth_Wdth_.values, a.Swth_Wdth_.values, rtol=1e-12)


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_second_width_channel(tmp_path, mode):
    """A second DDI 12001 channel with a full-width sample inside a removed span: no removed reading comes back."""
    _, dec = _decode(tmp_path, mode, width2=True)
    clean_shp = str(tmp_path / "syn_clean.shp")
    g, c = _write_subset(dec, clean_shp, lambda g: ~((g.Obj__Id.values > 8) & (g.Obj__Id.values < 50)))
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    rt = res["round_trip"]
    assert rt["ok"] and rt["n_extra"] == 0 and rt["n_missing"] == 0, rt
    assert len(_redecode(res, dec, mode)) == len(c)


def test_jdl_writer_width_channels_out_of_time_order(tmp_path):
    """sms mode, a file without section states (width = DDI 12001) whose second width channel's sample is logged in
    a block after a later sample of the first channel: jd_jdl reads that file's width by a binary search over the
    samples in record order. The written file holds the DDI in one channel in time order and the kept points read
    the width they had; keep-all stays byte for byte."""
    card, dec = _decode(tmp_path, width2=True, width2_s=75.0, states2=False)
    df0 = J.decode_detailed(dec["report"]["input_root"], dec["report"]["units"], None, log=lambda m: None)[0]
    late = df0.t_ms.values > T0 + 80_000
    assert late.sum() > 20
    clean_shp = str(tmp_path / "syn_clean.shp")
    _, c = _write_subset(dec, clean_shp, lambda g: ~(g.Time.isin(set(df0.Time[late][::3]))).values)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    rt = res["round_trip"]
    assert rt["ok"] and rt["n_extra"] == 0 and rt["n_missing"] == 0, rt
    assert next(iter(res["details"].values()))["width_channels_merged_files"] == 1
    res = W.write_clean(dec["source"], dec["shp"], str(tmp_path / "out2"), new_ids=False, log=lambda m: None)
    assert res["files_changed"] == []


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_state_held_by_a_carry(tmp_path, mode):
    """A section change 100 ms before the first kept reading, with every sample before it removed (the state the kept
    readings see then comes from the change and the carries): the kept readings keep their sections."""
    _, dec = _decode(tmp_path, mode, state_times=(0.12, 60.1, 80.2))
    df0 = J.decode_detailed(dec["report"]["input_root"], dec["report"]["units"], None, log=lambda m: None,
                            points=mode)[0]
    t_keep = set(df0.Time[df0.t_ms.values >= T0 + 80_300])
    clean_shp = str(tmp_path / "syn_clean.shp")
    _, c = _write_subset(dec, clean_shp, lambda g: g.Time.isin(t_keep).values)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    assert res["round_trip"]["ok"], res["round_trip"]
    df1 = _redecode(res, dec, mode).set_index("t_ms").sort_index()
    k0 = df0[df0.t_ms.values >= T0 + 80_300].set_index("t_ms").sort_index()
    assert list(df1.index) == list(k0.index)
    assert (df1.n_act.values == k0.n_act.values).all()


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_two_header_layouts(tmp_path, mode):
    """The second log defines another section layout (3 sections of 3 m, another work-state element): its readings
    are marked and narrowed with their own layout."""
    _, dec = _decode(tmp_path, mode, layout2=True)
    g = pyogrio.read_dataframe(dec["shp"])
    late = g.Obj__Id[g.Time > g.Time.sort_values().iloc[len(g) * 3 // 4]].iloc[0]
    clean_shp = str(tmp_path / "syn_clean.shp")
    _, c = _write_subset(dec, clean_shp, lambda g: g.Obj__Id.values % 5 != 0, narrow_obj=int(late), r=0.5)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    assert res["round_trip"]["ok"], res["round_trip"]
    b = _redecode(res, dec, mode).set_index("Time")
    i = c.Time[c.Obj__Id == late].iloc[0]
    if mode == "sms":
        assert b.loc[i, "n_act"] == 2                              # 4.5 m in 3 m sections: 2 of them (6 m)
        assert abs(b.loc[i, "Swth_Wdth_"] - 6.0 / 0.3048) < 1e-9
    else:
        assert abs(b.loc[i, "Swth_Wdth_"] - c.Swth_Wdth_[c.Obj__Id == late].iloc[0]) < 0.002


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_keep_all(tmp_path, mode):
    """Every reading kept, new_ids off: in sms mode the card byte for byte; in ops_center mode only the flow samples
    the vendor leaves out (header up, stationary) get their sections switched off, and the result says how many."""
    card, dec = _decode(tmp_path, mode)
    res = W.write_clean(dec["source"], dec["shp"], str(tmp_path / "out"), new_ids=False, log=lambda m: None)
    rt = res["round_trip"]
    assert rt["ok"] and rt["n_extra"] == 0 and rt["n_missing"] == 0
    root = dec["report"]["input_root"]
    same = [open(p, "rb").read() == open(os.path.join(res["path"], os.path.relpath(p, root)), "rb").read()
            for p in card["files"]]
    u = next(iter(res["details"].values()))
    if mode == "sms":
        assert all(same)
        assert res["files_changed"] == []
    else:
        assert u["marked_off"] == u["flow_samples"] - u["kept"] > 0
        assert res["bytes"]["records_changed"] > 0
    # the note says which model the logs decode back with: SMS's only for points="sms" (AF-1)
    assert (W.SMS_CAVEAT in res["notes"]) == (mode == "sms")
    assert (W.SMS_CAVEAT_OPS in res["notes"]) == (mode == "ops_center")


@pytest.mark.parametrize("mode", MODES)
def test_jdl_writer_without_the_round_trip_claims_no_exact_decode(tmp_path, mode):
    """R4E-2: verify=False (the writer's option, also through the dispatcher): the notes say the round trip was not
    run and claim nothing about decoding back exactly."""
    from engine.formats import native_write as NW
    _, dec = _decode(tmp_path, mode)
    clean_shp = str(tmp_path / "syn_clean.shp")
    _write_subset(dec, clean_shp, _subset)
    for i, fn in enumerate((W.write_clean, lambda *a, **k: NW.write("jd_jdl", *a, **k))):
        res = fn(dec["source"], clean_shp, str(tmp_path / f"out{i}"), verify=False, log=lambda m: None)
        assert res.get("round_trip") is None and "round trip not run (verify=False)" in res["notes"]
        assert not any("back exactly" in str(n) for n in res["notes"]), res["notes"]
        assert W.SMS_CAVEAT_UNVERIFIED in res["notes"]


def test_jdl_writer_reference_across_the_header(tmp_path):
    """sms mode: the first widest point of the second log (6 sections) is removed and the rest of that log runs on 5:
    SMS's reference across the header of that log moves half a section. Refused by default; written on request,
    with the kept points moved and their lateral offset moved back."""
    _, dec = _decode(tmp_path, state_times=(0.12, 60.1, 80.1, 83.1),
                     states=([1] * 6, [0] * 6, [1] * 6, [1, 1, 1, 1, 1, 0]))
    df0 = J.decode_detailed(dec["report"]["input_root"], dec["report"]["units"], None, log=lambda m: None)[0]
    drop = set(df0.Time[(df0.t_ms.values > T0 + 79_000) & (df0.t_ms.values < T0 + 84_000)])
    clean_shp = str(tmp_path / "syn_clean.shp")
    _, c = _write_subset(dec, clean_shp, lambda g: ~g.Time.isin(drop).values)
    with pytest.raises(W.JdlReferenceError) as e:
        W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    assert e.value.logs and abs(abs(e.value.logs[0]["move_m"]) - 0.75) < 1e-9
    assert not os.path.exists(str(tmp_path / "out" / "syn_clean_jdl"))
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), allow_reference_shift=True,
                        log=lambda m: None)
    assert res["round_trip"]["ok"], res["round_trip"]
    assert res["warnings"] and "sideways" in res["warnings"][0]
    b = _redecode(res, dec, "sms").set_index("t_ms")
    a = df0.set_index("t_ms").loc[b.index]
    late = b.index.values > T0 + 84_000
    np.testing.assert_allclose(b.Swth_Wdth_.values, a.Swth_Wdth_.values, rtol=1e-12)
    np.testing.assert_allclose(b.Yld_Vol_Dr.values, a.Yld_Vol_Dr.values, rtol=1e-12)
    dx, dy = J._local_xy(b.lat.values, b.lon.values, a.lat.values, a.lon.values)
    mv = np.hypot(dx, dy)
    assert np.allclose(mv[late], 0.75, atol=1e-3) and np.allclose(mv[~late], 0.0, atol=1e-6)
    np.testing.assert_allclose((b.Y_Offset_f.values - a.Y_Offset_f.values)[late], 0.75 / 0.3048, atol=1e-6)


def test_jdl_writer_definition_counts_follow_a_longer_block(tmp_path):
    """Definitions field 7 (sum of the block durations) follows a block duration the writer extends; 8 and 9 stay."""
    card = S.make_card(str(tmp_path / "card"), counts=True)
    m = J.read_meta(card["files"][0])
    lg = W._Log(m, 0)
    assert lg.defs_counts[7] == sum(b.dur for b in lg.blocks) and lg.defs_counts[8] == len(lg.blocks)
    lg.new_dur[len(lg.blocks) - 1] = lg.blocks[-1].dur + 250
    p = str(tmp_path / "x.jdl")
    open(p, "wb").write(lg.serialize())
    lg2 = W._Log(J.read_meta(p), 0)
    assert lg2.defs_counts[7] == lg.defs_counts[7] + 250
    assert lg2.defs_counts[8] == lg.defs_counts[8] and lg2.defs_counts[9] == lg.defs_counts[9]
    assert lg2.blocks[-1].dur == lg.blocks[-1].dur + 250


def test_jdl_writer_drop_logs(tmp_path):
    _, dec = _decode(tmp_path)
    clean_shp = str(tmp_path / "syn_clean.shp")
    g = pyogrio.read_dataframe(dec["shp"])
    first = sorted(g.Time)[: len(g) // 3]
    _, c = _write_subset(dec, clean_shp, lambda g: g.Time.isin(first).values)
    res = W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), drop_logs=True, log=lambda m: None)
    assert res["logs_written"] == 1 and res["logs_in_units"] == 2
    assert res["round_trip"]["ok"], res["round_trip"]


def test_jdl_writer_refuses(decoded, tmp_path):
    card, dec = decoded
    g = pyogrio.read_dataframe(dec["shp"])
    # rows of another decode
    bad = g.iloc[:10].copy()
    bad["Obj__Id"] = bad["Obj__Id"] + 100_000
    p = str(tmp_path / "bad.shp")
    pyogrio.write_dataframe(bad, p)
    with pytest.raises(W.JdlWriteError):
        W.write_clean(dec["source"], p, str(tmp_path / "out"), log=lambda m: None)
    # an empty clean file
    p = str(tmp_path / "empty.shp")
    pyogrio.write_dataframe(g.iloc[:0].copy(), p)
    with pytest.raises(W.JdlWriteError, match="no reading"):
        W.write_clean(dec["source"], p, str(tmp_path / "out"), log=lambda m: None)
    # an output folder inside the input
    with pytest.raises(W.JdlWriteError, match="inside the input"):
        W.write_clean(dec["source"], dec["shp"], os.path.join(dec["report"]["input_root"], "out"), log=lambda m: None)
    assert issubclass(W.JdlWriteError, ValueError)


def test_jdl_writer_failed_round_trip_writes_nothing(decoded, tmp_path, monkeypatch):
    _, dec = decoded
    clean_shp = str(tmp_path / "syn_clean.shp")
    _write_subset(dec, clean_shp, _subset)
    monkeypatch.setattr(W, "_plan", lambda *a, **k: (set(), {}, {}))         # a writer that marks nothing
    monkeypatch.setattr(W, "_check", lambda *a, **k: None)
    with pytest.raises(W.JdlRoundTripError, match="extra") as e:
        W.write_clean(dec["source"], clean_shp, str(tmp_path / "out"), log=lambda m: None)
    assert e.value.round_trip["n_extra"] > 0
    assert os.listdir(str(tmp_path / "out")) == []


def test_jdl_writer_can_write(decoded):
    _, dec = decoded
    assert W.can_write(dec["source"]) == (True, "")
    assert W.FORMAT_ID == J.FORMAT_ID and W.LABEL
    ok, why = W.can_write(None)
    assert not ok and why
    ok, why = W.can_write(dict(dec["source"], format="cnh_cn1"))
    assert not ok and "cnh_cn1" in why
    ok, why = W.can_write(dict(dec["source"], decode_report=None, input_root="/no/such/folder"))
    assert not ok and "not on disk" in why
