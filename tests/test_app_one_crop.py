# -*- coding: utf-8 -*-
"""0.3.5: 'Read the selected tasks as one crop' in step 1 (app/oced.py) through Streamlit's AppTest, synthetic data
only (tests/synthetic_cn1.py, tests/synthetic_isoxml.py). Tasks of one field and season logged with two crop labels:
the option is shown, off by default (one file per crop, as before); on, one file read as the chosen crop, decoded,
imported and cleaned byte for byte as the command line's --allow-mixed --product, with the lines that say which task
was read under another crop in its import record, cleaning record and DIFM notes; the choice survives saving and
reopening the work. Tasks of one crop: no option and the files of the command line.

    python -m pytest -q tests/test_app_one_crop.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from tests import synthetic_cn1 as SC  # noqa: E402
from tests import synthetic_isoxml as SI  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
EXTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _run(at):
    at.run()
    assert not at.exception, [str(e.value)[:500] for e in at.exception]


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click()
    _run(at)


def _option(at):
    chk = [c for c in at.checkbox if str(c.key or "").startswith("onecrop_")]
    sb = [s for s in at.selectbox if str(s.key or "").startswith("onecrop_p_")]
    return (chk[0] if chk else None), (sb[0] if sb else None)


def _extract(at):
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click()
    _run(at)


def _clean(at):
    at.button(key="clean_one").click()
    _run(at)
    assert not at.error, [e.value for e in at.error]
    return at.session_state["cleaned"][at.session_state["active"]]


def _md5s(shp):
    st = os.path.splitext(shp)[0]
    return {e: hashlib.md5(open(st + e, "rb").read()).hexdigest() for e in EXTS if os.path.exists(st + e)}


def _cli(card, out, *extra):
    assert er.main([card, "--field", "Field 1", "--year", "2026", "--method", "sms3sigma", "--out", str(out),
                    *extra]) == 0
    dec = os.path.join(str(out), "decoded")
    tag = next(f[:-len("_decoded.shp")] for f in os.listdir(dec) if f.endswith("_decoded.shp"))
    o = os.path.join(str(out), "output")
    imp = os.path.join(dec, f"{tag}_imported.shp")      # not written when the import changes nothing
    return {"decoded": os.path.join(dec, f"{tag}_decoded.shp"),
            "imported": imp if os.path.exists(imp) else os.path.join(dec, f"{tag}_decoded.shp"),
            "clean": os.path.join(o, f"{tag}_sms3s_clean.shp"), "flagged": os.path.join(o, f"{tag}_sms3s_flagged.shp")}


def _app_files(D, C):
    return {"decoded": D["import_default"]["basis"]["all_readings"], "imported": D["shp"], "clean": C["shp"],
            "flagged": C["flagged_shp"]}


def test_two_crops_option_off_by_default_and_on_gives_the_command_lines_one_file(tmp_path, monkeypatch):
    card = SC.make_card(str(tmp_path / "cnh"), second_crop=18)["card"]
    # off (the default): one file per crop, as 0.3.4
    at = _app(tmp_path / "ws_off", monkeypatch)
    _open(at, card)
    chk, sb = _option(at)
    assert chk is not None and chk.value is False
    assert sb.value == "Wheat - Spring"                  # the crop of most of the records (295 of 490)
    assert any("carry more than one crop label" in m.value for m in at.markdown)
    shown = [d.value for d in at.dataframe if "crop label" in list(getattr(d.value, "columns", []))]
    assert shown and sorted(shown[0]["crop label"]) == ["barley", "wheat"] and sorted(shown[0]["records"]) == [195, 295]   # harvest records
    _extract(at)
    DS = at.session_state["datasets"]
    assert len(DS) == 2 and not any(D.get("one_crop") for D in DS.values())
    # on: one file of both tasks, read as wheat
    at = _app(tmp_path / "ws_on", monkeypatch)
    _open(at, card)
    chk, sb = _option(at)
    chk.check()
    _run(at)
    _extract(at)
    DS = at.session_state["datasets"]
    assert len(DS) == 1
    tag, D = next(iter(DS.items()))
    oc = D["one_crop"]
    assert oc["product"] == "Wheat - Spring" and oc["crop"] == "wheat" and len(oc["units"]) == 2
    assert D["label"].endswith(" · wheat") and D["sms_import"]["resolved"]["product"] == "wheat"
    assert oc["lines"][0].startswith("read as one crop, Wheat - Spring: 1 of 2 selected task(s)")
    assert any("replaced by 'wheat'" in w for w in oc["lines"])
    for where in (D["sms_import"]["notes"], D["source"]["warnings"]):
        assert oc["lines"][0] in where and any("replaced by 'wheat'" in w for w in where)
    C = _clean(at)
    R = json.load(open(C["json"], encoding="utf-8"))
    assert "read as one crop, Wheat - Spring" in json.dumps(R)
    assert C["difm"]["notes"][0] == oc["lines"][0]
    # byte for byte the command line's --allow-mixed --product run with the same engine
    cli = _cli(card, tmp_path / "cli_on", "--allow-mixed", "--product", "Wheat - Spring")
    mine = _app_files(D, C)
    for k in ("decoded", "imported", "clean", "flagged"):
        assert _md5s(mine[k]) == _md5s(cli[k]), k
    # saved with the work and restored when it is reopened
    wd = at.session_state["workdir"]
    rec = json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))
    assert rec["datasets"][tag]["one_crop"]["product"] == "Wheat - Spring"
    at.button(key="start_over").click().run()
    at.selectbox(key="work_pick").set_value(wd).run()
    at.button(key="work_open").click()
    _run(at)
    D2 = at.session_state["datasets"][tag]
    assert D2["one_crop"] == oc and D2["import_default"]["basis"]["product"] == "wheat"
    assert any(c.value.startswith(":orange[read as one crop, Wheat - Spring: 1 of 2") for c in at.caption)
    assert _md5s(D2["import_default"]["basis"]["all_readings"]) == _md5s(cli["decoded"])


def test_one_crop_no_option_and_the_command_lines_files(tmp_path, monkeypatch):
    card = SC.make_card(str(tmp_path / "cnh"))["card"]
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, card)
    assert _option(at) == (None, None)
    assert not any("carry more than one crop label" in m.value for m in at.markdown)
    _extract(at)
    DS = at.session_state["datasets"]
    assert len(DS) == 1
    D = next(iter(DS.values()))
    assert "one_crop" not in D and "product" not in D["import_default"]["basis"]
    C = _clean(at)
    cli = _cli(card, tmp_path / "cli")
    mine = _app_files(D, C)
    for k in ("decoded", "imported", "clean", "flagged"):
        assert _md5s(mine[k]) == _md5s(cli[k]), k


def test_isoxml_logs_of_two_crops_become_one_file_when_asked(tmp_path, monkeypatch):
    R = SI.harvest(n_pass=6, n=60)
    cut = len(R["t"]) // 3
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), SI.take(R, 0, cut),
                     crop_attr=("P094_Crop_Type", 10))["folder"]         # a short log labelled canola
    b = SI.write_set(str(tmp_path / "in" / "s2" / "TASKDATA"), SI.take(R, cut - 1, len(R["t"])))["folder"]
    z = SI.zip_sets([a, b], str(tmp_path / "Synthetic task data.zip"))
    at = _app(tmp_path / "ws", monkeypatch)
    _open(at, z)
    units = at.session_state["units"][at.session_state["cands"][0]["probe"].root]
    assert len({u.crop for u in units}) == 2
    chk, sb = _option(at)
    assert chk is not None and chk.value is False
    chk.check()
    _run(at)
    _option(at)[1].set_value("Wheat - Spring")
    _extract(at)
    DS = at.session_state["datasets"]
    assert len(DS) == 1
    D = next(iter(DS.values()))
    assert D["one_crop"]["crop"] == "wheat" and sorted(D["units"]) == sorted(u.label for u in units)
    assert any("replaced by 'wheat'" in w for w in D["source"]["warnings"])
