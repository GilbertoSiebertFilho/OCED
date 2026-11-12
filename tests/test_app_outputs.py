# -*- coding: utf-8 -*-
"""Step 4 of the app (app/oced.py) through Streamlit's AppTest: the clean harvest saved in the same raw format it was
imported from (engine/formats/native_write.py options / write) or as ISOXML TASKDATA, on synthetic data only (a
synthetic Case IH card, GreenStar 3 card, Gen4 logs and a made-up point export). Every option of the monitor comes
first, ISOXML last; an option that cannot be written is disabled with its reason; every output says it is not yet
tested in SMS; a write runs into native/<tag>/ of the work folder, keeps a small record there and decodes back as
the clean file; a work opened again from a moved workspace still writes the card.

    python -m pytest -q tests/test_app_outputs.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import zipfile

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
CAVEAT = "Not yet tested in SMS: read it into a scratch SMS project, not into the project that holds the original data"


def _by_key(items, prefix):
    return next(x for x in items if str(x.key or "").startswith(prefix))


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


def _extract_and_clean(at, filters_off=False):
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    if filters_off:                       # the synthetic logs drive at one speed: no SD to filter on
        at.toggle(key="t_speed").set_value(False).run()
        at.toggle(key="t_moist").set_value(False).run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


def _write_buttons(at):
    return [b for b in at.button if str(b.key or "").startswith("nw_go_")]


def _record(at, fid):
    wd = at.session_state["workdir"]
    p = glob.glob(os.path.join(wd, "native", "*", f"{fid}.json"))
    assert len(p) == 1, p
    return json.load(open(p[0], encoding="utf-8")), wd


def _decode_back(path, source, wd, tag):
    """The written output decoded with the engine and the source's decoding options: the readings."""
    import dataclasses
    from engine import run as er
    from engine.formats import common
    cands = [c for c in er.open_input([path], wd, log=lambda m: None) if c.get("kind") == "raw"]
    assert cands, f"nothing raw recognised in {path}"
    o = dict(source.get("options") or {})
    opts = common.DecodeOptions(**{k: v for k, v in o.items() if k in {f.name for f in dataclasses.fields(
        common.DecodeOptions)}})
    units = [u.id for u in er.list_units(cands[0])]
    dec = er.decode(cands[0], units, opts, wd, log=lambda m: None, tag=tag, **dict(source.get("decoder_kwargs") or {}))
    return pyogrio.read_dataframe(dec["shp"], read_geometry=False)


@pytest.fixture(scope="module")
def cnh_card(tmp_path_factory):
    from tests.synthetic_cn1 import make_card
    return make_card(str(tmp_path_factory.mktemp("cnh_in")))["card"]


# ------------------------------------------------------------------------------------------------ the options
def test_app_export_offers_isoxml_only(tmp_path, monkeypatch):
    """A point export has no raw source: step 4 offers ISOXML TASKDATA only (marked experimental), with the SMS
    caveat; the write reads back as the clean file; a new cleaning makes the write stale."""
    F = make_field(str(tmp_path / "data"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, F["shp"])
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    bs = _write_buttons(at)
    assert [b.key.split("_")[2] for b in bs] == ["isoxml"] and not bs[0].disabled
    assert "experimental" in bs[0].label
    assert any(w.value.startswith(CAVEAT) for w in at.warning)
    bs[0].click().run()
    assert not at.exception, at.exception
    rec, wd = _record(at, "isoxml")
    C = at.session_state["cleaned"][at.session_state["active"]]
    n_clean = int(pyogrio.read_info(C["shp"])["features"])
    assert rec["n_kept"] == n_clean and rec["check"]["ok"] is True and rec["sms_tested"] is False
    assert os.path.exists(os.path.join(wd, rec["zip"])) and not os.path.isabs(rec["zip"])
    assert any(d.label.startswith("Download the ISOXML") for d in at.get("download_button"))
    assert any(f"{n_clean:,} readings kept" in c.value for c in at.caption)
    # the same file cleaned again: the write is from an earlier cleaning
    at.number_input(key="k_sd").set_value(2.5).run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert any("Written from an earlier cleaning" in w.value for w in at.warning)


def test_app_isoxml_readings_with_no_grain_are_not_a_failed_check(tmp_path, monkeypatch):
    """E2E-1: readings with no grain kept by a min. yield volume of 0 are written but are not points when the set is
    read: the writer's check line says how many were written and why fewer are read back, and is not a failure."""
    import geopandas as gpd
    import numpy as np
    F = make_field(str(tmp_path / "data"))
    g = gpd.read_file(F["shp"])
    zero = np.arange(len(g)) % 25 == 3
    for c in ("Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr"):
        if c in g.columns:
            g.loc[zero, c] = 0.0
    os.makedirs(tmp_path / "nog")
    shp = str(tmp_path / "nog" / "Synthetic_no_grain.shp")
    g.to_file(shp, driver="ESRI Shapefile", encoding="UTF-8")
    at = _app(tmp_path / "ws", monkeypatch)
    at.number_input(key="si_min").set_value(0.0).run()
    _open(at, shp)
    for k in ("t_speed", "t_moist", "t_yield"):
        at.toggle(key=k).set_value(False).run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    C = at.session_state["cleaned"][at.session_state["active"]]
    n_clean = int(pyogrio.read_info(C["shp"])["features"])
    n0 = int((pyogrio.read_dataframe(C["shp"], read_geometry=False)["Yld_Mass_W"].astype(float) <= 0).sum())
    assert n0 > 0
    _write_buttons(at)[0].click().run()
    assert not at.exception, at.exception
    rec, _ = _record(at, "isoxml")
    assert rec["check"]["ok"] is True, rec["check"]
    assert rec["check"]["line"].startswith(f"{n_clean:,} readings written, read back as {n_clean - n0:,} points "
                                           f"({n0:,} readings with no grain are not points)")
    assert not any("The writer's own check" in e.value for e in at.error)
    assert not any("step between positions" in w for w in rec["warnings"]), rec["warnings"]


def test_app_write_again_keeps_one_set_per_format(tmp_path, monkeypatch):
    """E2E-6: writing Gen4 logs or ISOXML again replaces the earlier set (folder, zip, ISOXML index) instead of adding
    a time-stamped copy next to it: one set per format under native/<tag>/, the one the record and the download
    point to."""
    from tests import synthetic_jdl as SJ
    F = make_field(str(tmp_path / "data"))
    for fid, path, off in (("isoxml", F["shp"], False), ("jd_jdl", SJ.make_card(str(tmp_path / "jdl"))["root"], True)):
        at = _app(tmp_path / f"ws_{fid}", monkeypatch)
        _open(at, path)
        _extract_and_clean(at, filters_off=off) if fid == "jd_jdl" else at.button(key="clean_one").click().run()
        assert not at.exception, at.exception
        for _ in range(2):
            next(b for b in _write_buttons(at) if b.key.startswith(f"nw_go_{fid}_")).click().run()
            assert not at.exception, at.exception
        rec, wd = _record(at, fid)
        [nd] = glob.glob(os.path.join(wd, "native", "*"))
        base = {"isoxml": "isoxml", "jd_jdl": "jdl"}[fid]
        sets = sorted(n for n in os.listdir(nd) if n.startswith(base) and not n.endswith(".json"))
        folders = [n for n in sets if os.path.isdir(os.path.join(nd, n))]
        assert len(folders) == 1, sets
        assert os.path.basename(rec["zip"]) in sets and os.path.basename(rec["path"]) == folders[0]
        assert len([n for n in sets if n.endswith(".zip")]) == 1, sets


def test_app_cnh_card_written_as_a_card(cnh_card, tmp_path, monkeypatch):
    """A Case IH card: its own format first and enabled, ISOXML last and disabled with the reason (the clean data
    came from raw monitor data); the card is written into native/<tag>/ (never inside the input), its record holds
    the writer's check and the totals, and the card decoded back with the engine holds exactly the clean readings."""
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, cnh_card)
    _extract_and_clean(at)
    bs = _write_buttons(at)
    ids = [b.key[len("nw_go_"):].rsplit("_", 1)[0] for b in bs]
    assert ids == ["cnh_cn1", "isoxml"]
    assert not bs[0].disabled and bs[1].disabled and bs[0].label.startswith("Write the Case IH")
    assert any("ISOXML TASKDATA (not the source's format): not available" in c.value for c in at.caption)
    bs[0].click().run()
    assert not at.exception, at.exception
    rec, wd = _record(at, "cnh_cn1")
    tag = at.session_state["active"]
    C = at.session_state["cleaned"][tag]
    clean = pyogrio.read_dataframe(C["shp"], read_geometry=False)
    assert rec["check"]["ok"] is True and rec["n_kept"] == len(clean) and rec["card_names"]
    assert rec["options"] == {"widths": True, "factors": None, "new_ids": True, "advanced": {}}
    assert {r[""] for r in rec["totals"]} >= {"the clean file", "what the SMS Summary should show"}
    out = os.path.join(wd, rec["path"])
    assert os.path.commonpath([out, os.path.join(wd, "native", tag)]) == os.path.join(wd, "native", tag)
    D = at.session_state["datasets"][tag]
    card_out = glob.glob(os.path.join(out, "*.cn1"))[0]
    back = _decode_back(card_out, D["source"], str(tmp_path / "chk"), "back")
    assert len(back) == len(clean)
    key = lambda df: sorted(zip(df["Time"].astype(str), df["Moisture__"].round(3)))  # noqa: E731
    assert key(back) == key(clean)
    assert abs(float((back.Distance_f * back.Swth_Wdth_).sum()) / float((clean.Distance_f * clean.Swth_Wdth_).sum())
               - 1) < 1e-6
    with zipfile.ZipFile(os.path.join(wd, rec["zip"])) as z:
        assert any(n.lower().endswith("index.vy1") for n in z.namelist())
    # the sidebar's action tree lists the write
    assert any("Case IH / New Holland AFS Pro 700 card (.cn1)" in c.value for c in at.caption
               if "report (PDF)" in c.value)


def test_app_gs3_and_gen4_written_in_their_format(tmp_path, monkeypatch):
    """A GreenStar 3 card and Gen4 logs: each offers its own writer first; the write decodes back with the kept
    readings (no reading missing, none extra) and says it is not tested in SMS."""
    from tests import synthetic_jdl as SJ
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    for fid, card in (("jd_gs3_rcd", gs3_card(str(tmp_path / "gs3"))["root"]),
                      ("jd_jdl", SJ.make_card(str(tmp_path / "jdl"))["root"])):
        at = _app(tmp_path / f"ws_{fid}", monkeypatch)
        _open(at, card)
        _extract_and_clean(at, filters_off=True)
        bs = _write_buttons(at)
        assert bs[0].key.startswith(f"nw_go_{fid}_") and not bs[0].disabled and bs[-1].disabled
        bs[0].click().run()
        assert not at.exception, at.exception
        rec, wd = _record(at, fid)
        n_clean = int(pyogrio.read_info(at.session_state["cleaned"][at.session_state["active"]]["shp"])["features"])
        assert rec["n_kept"] == n_clean and rec["check"]["ok"] is True, rec["check"]
        assert any(w.value.startswith(CAVEAT) for w in at.warning)


def _tree(folder):
    """Every file under `folder`: {relative path: bytes}."""
    return {os.path.relpath(os.path.join(d, f), folder): open(os.path.join(d, f), "rb").read()
            for d, _, fs in os.walk(folder) for f in fs}


def test_app_failed_write_leaves_the_card_written_before(cnh_card, tmp_path, monkeypatch):
    """R5T-13: a Case IH or GreenStar 3 card written again whose writer fails half-way (made to fail here after it
    has started the new card folder) leaves the card written before, its zip and its record as they were, with no
    set left aside; the next write that succeeds replaces it (one card folder, one zip). A card folder that holds a
    file the writer does not write is not moved aside: the writer refuses it as it refuses any such folder, and the
    card, the file, the zip and the record stay."""
    from engine.formats import cnh_cn1_write as CW
    from engine.formats import jd_gs3_rcd_write as GW
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    for fid, card, mod, fn in (("cnh_cn1", cnh_card, CW, "_write_task"),
                               ("jd_gs3_rcd", gs3_card(str(tmp_path / "gs3"))["root"], GW, "new_id_map")):
        at = _app(tmp_path / f"ws_{fid}", monkeypatch)
        _open(at, card)
        _extract_and_clean(at, filters_off=fid == "jd_gs3_rcd")
        go = lambda: next(b for b in _write_buttons(at) if b.key.startswith(f"nw_go_{fid}_"))  # noqa: E731
        go().click().run()
        assert not at.exception, at.exception
        rec, wd = _record(at, fid)
        folder, zp = os.path.join(wd, rec["path"]), os.path.join(wd, rec["zip"])
        nd = os.path.dirname(folder)
        snap = (_tree(folder), open(zp, "rb").read(), sorted(os.listdir(nd)))
        assert snap[0]

        def boom(*a, **k):
            raise OSError("synthetic failure in the middle of the write")
        with monkeypatch.context() as m:
            m.setattr(mod, fn, boom)
            go().click().run()
        assert any("synthetic failure" in str(e.value) for e in at.exception), (fid, at.exception)
        assert (_tree(folder), open(zp, "rb").read(), sorted(os.listdir(nd))) == snap, fid
        assert _record(at, fid)[0] == rec
        go().click().run()
        assert not at.exception, at.exception
        assert sorted(os.listdir(nd)) == snap[2] and not any(n.endswith(("~", "~.zip")) for n in os.listdir(nd))
        assert _tree(folder) != snap[0]                          # new card names / file ids
        rec = _record(at, fid)[0]
        snap = (_tree(folder), open(zp, "rb").read(), sorted(os.listdir(nd)))
        with open(os.path.join(folder, "notes.txt"), "w") as fh:
            fh.write("not the writer's")
        go().click().run()
        assert not at.exception, at.exception
        refused = "exists and holds other files" if fid == "cnh_cn1" else "holds files that are not a written card"
        assert any(refused in e.value for e in at.error), (fid, [e.value for e in at.error])
        tree = _tree(folder)
        assert tree.pop("notes.txt") == b"not the writer's" and tree == snap[0], fid
        assert (open(zp, "rb").read(), sorted(os.listdir(nd))) == snap[1:] and _record(at, fid)[0] == rec


def test_app_card_gone_falls_back_to_isoxml(cnh_card, tmp_path, monkeypatch):
    """The raw input is no longer on this computer: the card's own format is disabled with the writer's reason and
    ISOXML becomes the fallback."""
    src = tmp_path / "card_copy" / os.path.basename(cnh_card)
    shutil.copytree(cnh_card, src)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, src)
    _extract_and_clean(at)
    shutil.rmtree(src.parent)
    at.run()
    assert not at.exception, at.exception
    bs = {b.key[len("nw_go_"):].rsplit("_", 1)[0]: b for b in _write_buttons(at)}
    assert bs["cnh_cn1"].disabled and not bs["isoxml"].disabled
    assert any("not on this computer any more" in c.value and "not available" in c.value for c in at.caption)
    bs["isoxml"].click().run()
    assert not at.exception, at.exception
    assert _record(at, "isoxml")[0]["check"]["ok"] is True


def test_app_moved_work_writes_the_card(cnh_card, tmp_path, monkeypatch):
    """A card opened from a zip is unpacked into the work folder; the workspace moved elsewhere and the work opened
    again: the writer finds the card under the moved work folder (the input folder resolved relative to it) and
    writes it."""
    z = tmp_path / "card.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for dp, _, fn in os.walk(cnh_card):
            for f in fn:
                p = os.path.join(dp, f)
                zf.write(p, os.path.relpath(p, os.path.dirname(cnh_card)))
    at = _app(tmp_path / "ws1", monkeypatch)
    _open(at, z)
    _extract_and_clean(at)
    at.button(key="work_save").click().run()
    assert not at.exception, at.exception
    shutil.move(str(tmp_path / "ws1"), str(tmp_path / "ws2"))
    at2 = _app(tmp_path / "ws2", monkeypatch)
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    tag = at2.session_state["active"]
    assert tag in at2.session_state["cleaned"]
    assert str(tmp_path / "ws2") in at2.session_state["workdir"]
    b = next(b for b in _write_buttons(at2) if b.key.startswith("nw_go_cnh_cn1_"))
    assert not b.disabled
    b.click().run()
    assert not at2.exception, at2.exception
    rec, _ = _record(at2, "cnh_cn1")
    assert rec["check"]["ok"] is True


def test_app_gen4_reference_shift_asks_before_writing(tmp_path, monkeypatch):
    """A Gen4 card whose cleaning removed a log's reference point: the writer refuses (JdlReferenceError with the
    logs it would move); the page says so and offers 'Write anyway', which writes with allow_reference_shift."""
    from engine.formats import jd_jdl_write as JW
    from engine.formats import native_write as NW
    from tests import synthetic_jdl as SJ
    card = SJ.make_card(str(tmp_path / "jdl"))["root"]
    real = NW.write
    calls = []

    def fake(fmt_id, *a, **k):
        calls.append(dict(k))
        if fmt_id == "jd_jdl" and not k.get("allow_reference_shift"):
            raise JW.JdlReferenceError("synthetic: the first widest point of a log was removed. Write it anyway with "
                                       "allow_reference_shift=True (the move is then predicted and checked per "
                                       "reading).",
                                       logs=[{"log": "a.jdl", "machine": "M", "kept_readings": 12, "move_m": 0.1}])
        return real(fmt_id, *a, **k)
    monkeypatch.setattr(NW, "write", fake)
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    _extract_and_clean(at, filters_off=True)
    _write_buttons(at)[0].click().run()
    assert not at.exception, at.exception
    shift = _by_key(at.button, "nw_shift_")
    assert "Write anyway: 12 kept readings of 1 log(s) are placed 0.100 m sideways" in shift.label
    assert any("first widest point" in w.value for w in at.warning)
    # E2E-7: the page names its own button, not the writer's option
    assert any("Use the 'Write anyway' button below to write them" in w.value for w in at.warning)
    assert not any("allow_reference_shift" in w.value for w in at.warning)
    shift.click().run()
    assert not at.exception, at.exception
    assert calls[-1].get("allow_reference_shift") is True
    assert _record(at, "jd_jdl")[0]["options"]["advanced"].get("allow_reference_shift") is True


def test_native_factors_follow_step_3():
    """The factors the writers get: none when nothing was applied; the combine factor of each combine; with the
    yields adjusted, times the L in the file (after the combine factor)."""
    import ast
    tree = ast.parse(open(APP, encoding="utf-8").read())
    ns = {"np": __import__("numpy"), "GATE_TEXT": {}}
    for name in ("factor_outcome", "native_factors"):
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        exec(compile(ast.Module([fn], []), APP, "exec"), ns)
    ns["clean_machines"] = lambda shp: ["A", "B"]
    nf = ns["native_factors"]
    base = {"shp": "x.shp", "adjusted": False}
    assert nf({**base, "R": {}}) == (None, "")
    R = {"machines": {"factor_applied": {"A": 1.0, "B": 0.95}, "tests": []},
         "settings": {"machines": {"harmonise": True, "max_factor": 0.1}}}
    f, txt = nf({**base, "R": R})
    assert f == {"A": 1.0, "B": 0.95} and "B x 0.9500" in txt
    R2 = {**R, "level": {"factor": 1.1, "factor_final": 1.05}}
    f, txt = nf({**base, "adjusted": True, "R": R2})
    assert f == pytest.approx({"A": 1.05, "B": 0.95 * 1.05}) and "L 1.0500" in txt
    R3 = {"level": {"factor": 1.2, "factor_final": None}}
    f, _ = nf({**base, "adjusted": True, "R": R3})
    assert f == pytest.approx({"A": 1.2, "B": 1.2})
