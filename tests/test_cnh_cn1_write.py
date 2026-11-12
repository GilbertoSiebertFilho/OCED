# -*- coding: utf-8 -*-
"""The clean harvest written back as a Case IH / New Holland card (engine/formats/cnh_cn1_write.py), on the synthetic
card of tests/synthetic_cn1.py: the decoder reads the written card and gets exactly the kept readings (level 1), the
clean widths, distances and positions (level 2) and the corrected mass (level 3); every record keeps a valid checksum;
nothing removed = the original files byte for byte; the Summary of the written card is the kept readings' (totals
"points"); upper-case cards keep their names; partial cards, empty files and outputs inside the input are refused;
card names are never given twice.

    python -m pytest -q tests/test_cnh_cn1_write.py
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import cnh_cn1 as C  # noqa: E402
from engine.formats import cnh_cn1_write as W  # noqa: E402
from tests.synthetic_cn1 import make_card  # noqa: E402

QUIET = lambda m: None  # noqa: E731


def _decode_input(folder, wd, upper=False):
    card = make_card(os.path.join(folder, "input"), upper=upper)
    cand = er.open_input([card["card"]], wd, log=QUIET)[0]
    assert cand["kind"] == "raw" and cand["decoder"] == "cnh_cn1"
    dec = er.decode(cand, None, None, wd, log=QUIET)
    return {"card": card, "dec": dec, "wd": wd}


@pytest.fixture(scope="module")
def decoded(tmp_path_factory):
    return _decode_input(str(tmp_path_factory.mktemp("card")), str(tmp_path_factory.mktemp("work")))


@pytest.fixture(scope="module")
def decoded_upper(tmp_path_factory):
    return _decode_input(str(tmp_path_factory.mktemp("card_up")), str(tmp_path_factory.mktemp("work_up")), upper=True)


def _decode(path):
    units = [u.id for u in C.list_units(path)]
    return C.decode(path, units, None, log=QUIET)


def _subset(dec, out, drop_every=7, narrow=(), shorten=()):
    """A 'clean' file: the decoded readings without every drop_every-th one; the rows in `narrow` at half width and
    moved 1 m north, the rows in `shorten` at 60 % of their distance (as Optimize Swath Widths does)."""
    g = pyogrio.read_dataframe(dec["shp"])
    keep = np.ones(len(g), bool)
    keep[::drop_every] = False
    keep[:3] = True
    g = g[keep].copy()
    for i in narrow:
        g.iloc[i, g.columns.get_loc("Swth_Wdth_")] = g["Swth_Wdth_"].iloc[i] / 2
    if narrow:
        geo = g.geometry.copy()
        from shapely.geometry import Point
        idx = g.index[list(narrow)]
        geo.loc[idx] = [Point(p.x, p.y + 1.0 / 111320.0) for p in geo.loc[idx]]
        g = g.set_geometry(geo)
    for i in shorten:
        g.iloc[i, g.columns.get_loc("Distance_f")] = g["Distance_f"].iloc[i] * 0.6
    g.to_file(out, engine="pyogrio")
    return g


def _fld(res, upper=False):
    return os.path.join(res["cards"][0], *(("SHARED", "SYNFARM1.FMD", "SYNFLD01.FLD") if upper else
                                           ("shared", "SYNFARM1.fmd", "SYNFLD01.fld")))


def test_checksum_rule(decoded):
    tlo = os.path.join(decoded["card"]["field_dir"], "SYNTSK01.tlo")
    n, bad, stray = W.check_file(tlo)
    assert (n, bad, stray) == (300, 0, 0)
    b = bytearray(open(tlo, "rb").read())
    b[74 + 40] ^= 0x01                                           # one byte of the second record changed
    assert W.checksum(b[74:148]) != b[74 + 8]
    W.set_checksum(b, 74, 74)
    assert W.checksum(b[74:148]) == b[74 + 8]


def test_identity_is_byte_for_byte(decoded, tmp_path):
    res = W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / "s"), totals="scaled", log=QUIET)
    assert res["n_removed"] == 0 and res["files_changed"] == []
    assert res["check"]["ok"], res["check"]["problems"]
    assert res["records_bad_checksum"] == 0
    name = os.path.basename(res["cards"][0])
    assert name.endswith(".cn1") and name != "SYN0001A.cn1"       # new card folder name, ids inside kept
    src, dst = decoded["card"]["field_dir"], _fld(res)
    for t in ("SYNTSK01", "SYNTSK02"):
        for ext in W.TASK_EXTS:
            assert open(os.path.join(src, t + ext), "rb").read() == open(os.path.join(dst, t + ext), "rb").read()
    assert not os.path.exists(os.path.join(dst, "SYNGUIDE.ags"))  # guidance lines left out
    assert os.path.isfile(res["zip"])
    assert any("not yet tested in SMS" in n for n in res["notes"])
    # the default totals ("points") rewrite only the task totals: the logs stay byte for byte
    res2 = W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / "p"), log=QUIET)
    assert res2["totals"] == "points" and res2["check"]["ok"], res2["check"]["problems"]
    assert {os.path.splitext(f)[1] for f in res2["files_changed"]} <= {".tso", ".tsh"}


@pytest.mark.parametrize("mode", W.MODES)
def test_level1_kept_readings_only(decoded, tmp_path, mode):
    clean = str(tmp_path / "clean.shp")
    g = _subset(decoded["dec"], clean, drop_every=5)
    res = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "out"), widths=False, mode=mode, log=QUIET)
    assert res["n_kept"] == len(g)
    chk = res["check"]
    assert chk["ok"], chk["problems"]
    assert chk["exact"]["all_level1"] == len(g)                   # every attribute of every kept reading identical
    df, rep = _decode(res["path"])
    assert len(df) == len(g)
    assert list(df["Time"]) == list(g.sort_values(["Dataset", "Obj__Id"])["Time"])
    # the record counts of the task follow the records left
    for t in rep["sms_summary"]["datasets"]:
        assert t["logged_records"] < 300
    # the display restart of task 2 is still paired run by run
    _, notes = C.read_task(os.path.join(_fld(res), "SYNTSK02"))
    assert notes["counter runs"] == {".tlo": 2, ".tlh": 2}


def test_display_restart_edges_stay(decoded, tmp_path):
    """Taking out (mode "drop") every reading around a display restart must not join the two counter runs: the
    records at the restart stay with the logging bit cleared, the decoder still pairs the streams run by run."""
    g = pyogrio.read_dataframe(decoded["dec"]["shp"])
    t2 = g["Dataset"].str.startswith("SYNTSK02")
    o = g["Obj__Id"]
    clean = str(tmp_path / "clean.shp")
    g[~(t2 & (o >= 100) & (o <= 140))].to_file(clean, engine="pyogrio")
    res = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "out"), mode="drop", log=QUIET)
    assert res["check"]["ok"], res["check"]["problems"]
    t = next(x for x in res["tasks"] if x["task"] == "SYNTSK02")
    assert t["records_flagged_at_restarts"] == 2 and t["records_dropped"][".tlo"] == 39
    _, notes = C.read_task(os.path.join(_fld(res), "SYNTSK02"))
    assert notes["counter runs"] == {".tlo": 2, ".tlh": 2}


def test_level2_widths_distance_position(decoded, tmp_path):
    clean = str(tmp_path / "clean.shp")
    g = _subset(decoded["dec"], clean, drop_every=6, narrow=(10, 11, 200), shorten=(40,))
    res = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "out"), log=QUIET)
    chk = res["check"]
    assert chk["ok"], chk["problems"]
    assert chk["deviations"]["width_ft"] < 0.002 and chk["deviations"]["position_m"] < 0.002
    assert chk["deviations"]["distance_ft"] < 0.002 and chk["deviations"]["wet_yield_rel"] < 1e-3
    assert sum(t["width_changed"] for t in res["tasks"] if t.get("written")) == 3
    assert sum(t["distance_changed"] for t in res["tasks"] if t.get("written")) == 1
    assert sum(t["moved"] for t in res["tasks"] if t.get("written")) == 3
    df, _ = _decode(res["path"])
    gs = g.sort_values(["Dataset", "Obj__Id"]).reset_index(drop=True)
    assert np.allclose(df["Swth_Wdth_"], gs["Swth_Wdth_"], atol=0.002)
    assert np.allclose(df["lat"], gs.geometry.y, atol=2e-8) and np.allclose(df["lon"], gs.geometry.x, atol=2e-8)
    # the logged antenna point moved with the header centre (its offset from the centre is kept)
    assert sum(t["antenna_moved"] for t in res["tasks"] if t.get("written")) == 3
    rows = []
    for t in ("SYNTSK01", "SYNTSK02"):
        a, _ = C.read_task(os.path.join(decoded["card"]["field_dir"], t))
        b, _ = C.read_task(os.path.join(_fld(res), t))
        off_a = a["lat0"] - (a["latL"] + a["latR"]) / 2
        off_b = b["lat0"] - (b["latL"] + b["latR"]) / 2
        assert float(np.abs(off_a - off_b).max()) < 2e-8
        rows.append(int((np.abs(a["lat0"] - b["lat0"]) > 1e-7).sum()))
    assert sum(rows) == 3
    # widths=False on the same file: the card keeps the logged widths and says so
    res2 = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "out2"), widths=False, log=QUIET)
    assert res2["check"]["ok"], res2["check"]["problems"]
    w = [x for x in res2["warnings"] if x.startswith("widths=False")]
    assert w and "4 readings" in w[0]


def test_level3_factor_and_header_up(decoded, tmp_path):
    res = W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / "f"),
                        factors={decoded["card"]["vehicle"]: 1.10}, log=QUIET)
    assert res["check"]["ok"], res["check"]["problems"]
    d0, _ = _decode(decoded["card"]["card"])
    d1, _ = _decode(res["path"])
    r = (d1.Yld_Mass_W / d0.Yld_Mass_W)[d0.Yld_Mass_W > 0]
    assert abs(r.median() - 1.10) < 1e-3 and (r - 1.10).abs().max() < 0.01
    assert abs(res["summary_vs_clean"]["wet"]) < 2e-3          # the Summary follows the factor too
    clean = str(tmp_path / "clean.shp")
    g = _subset(decoded["dec"], clean, drop_every=4)
    res2 = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "h"), log=QUIET)     # default header_up
    assert res2["check"]["ok"], res2["check"]["problems"]
    base = os.path.join(_fld(res2), "SYNTSK01")
    assert os.path.getsize(base + ".tlo") == 300 * 74                 # records kept, logging bit cleared
    so = open(base + ".tso", "rb").read()
    n_log, n_off = struct.unpack_from("<II", so, 196)
    co, _, O, _, _ = C.read_stream(base + ".tlo", C.TLO_LEN)
    assert n_log == int((O[:, 0] & 1).sum()) and n_off == int((~O[:, 0] & 1).sum())
    assert len(_decode(res2["path"])[0]) == len(g)
    # the distance of the readings set header-up moves from the logged [183] to the header-up [187] distance
    s0 = open(os.path.join(decoded["card"]["field_dir"], "SYNTSK01.tso"), "rb").read()
    d183_0, d187_0 = struct.unpack_from("<I", s0, 33 + 183)[0], struct.unpack_from("<I", s0, 33 + 187)[0]
    d183_1, d187_1 = struct.unpack_from("<I", so, 33 + 183)[0], struct.unpack_from("<I", so, 33 + 187)[0]
    assert d183_1 < d183_0 and d187_1 > d187_0 and abs((d183_1 + d187_1) - (d183_0 + d187_0)) <= 2


def test_summary_is_the_kept_readings(decoded, tmp_path):
    """totals="points": the Summary SMS should show for the written card (the decoder's sms_summary of it) is the
    clean file's area and wet weight; "scaled" keeps the display's ratio and is reported against the clean totals."""
    clean = str(tmp_path / "clean.shp")
    _subset(decoded["dec"], clean, drop_every=3, narrow=(5, 6), shorten=(30,))
    res = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "p"), log=QUIET)
    assert res["check"]["ok"], res["check"]["problems"]
    assert abs(res["summary_vs_clean"]["area"]) < 1e-4, res["summary_vs_clean"]
    cmp = res["summary_vs_points"]                       # the made-up 'clean' file does not keep the narrowed mass
    assert abs(cmp["area"]) < 1e-4 and abs(cmp["wet"]) < 2e-3, cmp
    assert res["expected_summary"]["area_ac"] == pytest.approx(res["clean_totals"]["area_ac"], rel=1e-4)
    res2 = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "s"), totals="scaled", log=QUIET)
    assert res2["summary_vs_clean"] is not None and res2["clean_totals"] == res["clean_totals"]
    # the bins of the written card weigh the kept readings' mass
    p = os.path.join(_fld(res), "SYNTSK01.tsh")
    sh = C._task_sh(p)
    df, _ = C.read_task(os.path.join(_fld(res), "SYNTSK01"))
    keep, _ = C.select_readings(df)
    g = df[keep]
    fl, _ = C.flow_lb_s(g.hA.values, g.hB.values / 10.0, sh["curve"], sh["comp"])
    wet = float((fl * g.dt_byte.values).sum())
    assert C.bins_wet_lb(sh["seconds"], sh["counts"], sh["moisture_pct"], sh["curve"], sh["comp"]) == \
        pytest.approx(wet, rel=2e-3)


def test_whole_task_dropped(decoded, tmp_path):
    g = pyogrio.read_dataframe(decoded["dec"]["shp"])
    clean = str(tmp_path / "clean.shp")
    g[g["Dataset"].str.startswith("SYNTSK02")].to_file(clean, engine="pyogrio")
    res = W.write_clean(decoded["dec"]["source"], clean, str(tmp_path / "out"), log=QUIET)
    assert res["check"]["ok"], res["check"]["problems"]
    assert res["check"]["datasets_without_kept_reading"] == 1
    assert res["expected_summary"] is not None and res["expected_summary"]["tasks"] == 1
    assert not os.path.exists(os.path.join(_fld(res), "SYNTSK01.tlo"))
    assert [t["written"] for t in res["tasks"]] == [False, True]


def test_upper_case_card_keeps_its_names(decoded_upper, tmp_path):
    D = decoded_upper
    ok, why = W.can_write(D["dec"]["source"])
    assert ok, why
    clean = str(tmp_path / "clean.shp")
    g = _subset(D["dec"], clean, drop_every=5, narrow=(7,))
    res = W.write_clean(D["dec"]["source"], clean, str(tmp_path / "out"), log=QUIET)
    assert res["check"]["ok"], res["check"]["problems"]
    card = res["cards"][0]
    top = sorted(os.listdir(card))
    assert top == ["COMBINES", "INDEX.VY1", "SHARED"], top
    assert sorted(os.listdir(os.path.join(card, "SHARED"))) == ["GROWERS.GWS", "SYNFARM1.FMD", "SYNFARM1.FMS"]
    fld = _fld(res, upper=True)
    assert sorted(os.listdir(fld)) == sorted(t + e.upper() for t in ("SYNTSK01", "SYNTSK02") for e in W.TASK_EXTS)
    assert len(_decode(res["path"])[0]) == len(g)
    with open(os.path.join(card, "INDEX.VY1"), "rb") as a, open(os.path.join(D["card"]["card"], "INDEX.VY1"), "rb") as b:
        assert a.read() == b.read()


def test_refusals(decoded, tmp_path):
    src = decoded["dec"]["source"]
    clean = str(tmp_path / "empty.shp")
    g = pyogrio.read_dataframe(decoded["dec"]["shp"])
    g.iloc[:0].to_file(clean, engine="pyogrio")
    with pytest.raises(ValueError, match="no readings"):
        W.write_clean(src, clean, str(tmp_path / "out"), log=QUIET)
    with pytest.raises(W.CardWriteError, match="inside the input"):
        W.write_clean(src, decoded["dec"]["shp"], os.path.join(decoded["card"]["card"], "out"), log=QUIET)
    assert W.can_write(None)[0] is False
    assert W.can_write(dict(src, format="jd_jdl"))[0] is False
    foreign = str(tmp_path / "foreign.shp")
    f = g.iloc[:20].copy()
    f["Time"] = "2020-01-01 00:00:00.0"
    f.to_file(foreign, engine="pyogrio")
    with pytest.raises(ValueError, match="do not match"):
        W.write_clean(src, foreign, str(tmp_path / "out"), log=QUIET)


def test_partial_card_is_refused(tmp_path):
    card = make_card(str(tmp_path / "in"))
    loose = str(tmp_path / "loose")
    shutil.copytree(os.path.join(card["card"], "shared", "SYNFARM1.fmd"), os.path.join(loose, "SYNFARM1.fmd"))
    cand = er.open_input([loose], str(tmp_path / "w"), log=QUIET)[0]
    dec = er.decode(cand, None, None, str(tmp_path / "w"), log=QUIET)
    ok, why = W.can_write(dec["source"])
    assert not ok and "partial" in why
    with pytest.raises(W.CardWriteError, match="partial"):
        W.write_clean(dec["source"], dec["shp"], str(tmp_path / "out"), log=QUIET)


def test_card_names_are_never_given_twice(decoded, tmp_path):
    reg = str(tmp_path / "names.json")
    names = set()
    for k in range(3):
        res = W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / f"o{k}"), registry=reg,
                            verify=False, log=QUIET)
        names.add(os.path.basename(res["cards"][0]).lower())
    assert len(names) == 3
    assert len(json.load(open(reg, encoding="utf-8"))["cards"]) == 3
    res = W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / "o9"), registry=reg,
                        verify=False, card_names={"SYN0001A": "MYCARD01"}, log=QUIET)
    assert os.path.basename(res["cards"][0]) == "MYCARD01.cn1"
    with pytest.raises(W.CardWriteError, match="already used"):
        W.write_clean(decoded["dec"]["source"], decoded["dec"]["shp"], str(tmp_path / "o10"), registry=reg,
                      verify=False, card_names={"SYN0001A.cn1": "mycard01"}, log=QUIET)


def _tree(folder):
    """Every file under `folder`: {relative path: bytes}."""
    return {os.path.relpath(os.path.join(d, f), folder): open(os.path.join(d, f), "rb").read()
            for d, _, fs in os.walk(folder) for f in fs}


def test_a_refused_write_leaves_the_card_written_before(decoded, tmp_path):
    """R5T-13: writing into the same folder again replaces the card written before only once every refusal is past:
    a clean file that is not from this decode, or a card name already given, leaves the earlier card as it was; a
    write that succeeds replaces it (one card, its new name)."""
    src, shp = decoded["dec"]["source"], decoded["dec"]["shp"]
    out, reg = str(tmp_path / "out"), str(tmp_path / "names.json")
    kw = {"registry": reg, "verify": False, "out_name": "cn1", "log": QUIET}
    first = W.write_clean(src, shp, out, **kw)
    snap = _tree(first["path"])
    assert snap and os.listdir(first["path"]) == [os.path.basename(first["cards"][0])]
    foreign = str(tmp_path / "foreign.shp")
    f = pyogrio.read_dataframe(shp).iloc[:20].copy()
    f["Time"] = "2020-01-01 00:00:00.0"
    f.to_file(foreign, engine="pyogrio")
    with pytest.raises(W.CardWriteError, match="do not match"):
        W.write_clean(src, foreign, out, **kw)
    assert _tree(first["path"]) == snap
    taken = os.path.basename(first["cards"][0])[:-4]
    with pytest.raises(W.CardWriteError, match="already used"):
        W.write_clean(src, shp, out, card_names={"SYN0001A": taken}, **kw)
    assert _tree(first["path"]) == snap
    second = W.write_clean(src, shp, out, **kw)
    assert second["path"] == first["path"] and os.listdir(second["path"]) == [os.path.basename(second["cards"][0])]
    assert second["cards"][0] != first["cards"][0]
