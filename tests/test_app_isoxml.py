# -*- coding: utf-8 -*-
"""ISOXML harvest task data in the app (app/oced.py) through Streamlit's AppTest: a zip of zipped TASKDATA sets is
opened as one raw dataset, its unit extracted and imported as SMS imports ISOXML task data, cleaned, and the clean
file saved as ISOXML again (the monitor's own format). Synthetic task data only (tests/synthetic_isoxml.py).

    python -m pytest -q tests/test_app_isoxml.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
import zipfile

import pyogrio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests import synthetic_isoxml as SI  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def test_app_says_what_it_made_of_an_unknown_crop_code_and_of_a_damaged_zip(tmp_path, monkeypatch):
    """Task data with grain whose crop code OCED does not know: the unit is listed with what the log's density and
    reference moisture read like, pre-selected, extracted with those values labelled 'from the file', and the
    warning to check the product is on screen. A damaged zip among the zipped sets is a warning, not a refusal."""
    R = SI.harvest(n_pass=4, n=40)
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), R, crop_attr=("P094_Crop_Type", 99))["folder"]
    z = SI.zip_sets([a], str(tmp_path / "Synthetic task data.zip"))
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr("TASKDATA-0000000000-20260910149999.zip", b"PK this is not a zip any more")
    at = _app(tmp_path / "ws", monkeypatch)
    assert any("a crop code OCED does not know" in c.value for c in at.caption)     # the defaults, said in step 1
    at.text_input(key="path_in").input(z)
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    cands = at.session_state["cands"]
    assert [c.get("decoder") for c in cands] == ["isoxml"]
    assert any("20260910149999.zip" in w.value and "left out" in w.value for w in at.warning)
    units = at.session_state["units"][cands[0]["probe"].root]
    assert [u.crop for u in units] == ["crop type 99"] and "crop type 99 (wheat?)" in units[0].label
    assert units[0].default
    next(x for x in at.button if str(x.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    tag = at.session_state["active"]
    D = at.session_state["datasets"][tag]
    rec = D["sms_import"]
    assert D["n"] == rec["n_in"] > 100 and rec["family"] == "isoxml"
    assert abs(rec["resolved"]["test_weight_lb_bu"] - 60.0) < 0.01 and rec["resolved"]["dry_moisture_pct"] == 13.5
    assert rec["sources"]["dry_moisture_pct"] == "file" and rec["sources"]["max_yield"] == "SMS for ISOXML task data"
    assert D["report"]["monitor_product"]["guess"] == "wheat"
    assert any("is not one OCED knows" in w and "P094_Crop_Type 99" in w for w in D["report"]["warnings"])
    shown = [w.value for w in at.warning] + [c.value for c in at.caption] + [m.value for m in at.markdown]
    assert any("is not one OCED knows" in s for s in shown)


def test_app_reads_isoxml_task_data_and_saves_the_clean_file_as_isoxml(tmp_path, monkeypatch):
    R = SI.harvest(n_pass=6, n=60)
    cut = len(R["t"]) // 2 + 20
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), SI.take(R, 0, cut))["folder"]
    b = SI.write_set(str(tmp_path / "in" / "s2" / "TASKDATA"), SI.take(R, cut - 1, len(R["t"])))["folder"]
    z = SI.zip_sets([a, b], str(tmp_path / "Synthetic task data.zip"))
    at = _app(tmp_path / "ws", monkeypatch)
    assert any("ISOXML harvest task data" in c.value for c in at.caption)          # what OCED reads
    at.text_input(key="path_in").input(z)
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    cands = at.session_state["cands"]
    assert [c.get("decoder") for c in cands] == ["isoxml"] and "2 harvest time log(s)" in cands[0]["label"]
    # the decoding option of the format: each time log on its own, as SMS
    opt = next(x for x in at.get("button_group") if str(x.key or "").startswith("isl_"))
    assert opt.value == "sms"
    next(x for x in at.button if str(x.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    tag = at.session_state["active"]
    D = at.session_state["datasets"][tag]
    assert D["kind"] == "raw" and D["source"]["format"] == "isoxml" and D["report"]["time_logs"] == "sms"
    rec = D["sms_import"]
    assert rec["family"] == "isoxml" and rec["resolved"]["test_weight_lb_bu"] == 60.0
    assert rec["resolved"]["dry_moisture_pct"] == 13.5 and rec["resolved"]["max_yield"] == 10_000.0
    assert rec["sources"]["dry_moisture_pct"] == "SMS for this crop in ISOXML task data"
    assert D["n"] == rec["n_in"] > 300
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    C = at.session_state["cleaned"][tag]
    n_clean = int(pyogrio.read_info(C["shp"])["features"])
    assert 0.5 * D["n"] < n_clean <= D["n"]
    # step 4: ISOXML is this file's own raw format: one button, enabled, with what a new set does not carry
    bs = [x for x in at.button if str(x.key or "").startswith("nw_go_")]
    assert len(bs) == 1 and bs[0].key.startswith("nw_go_isoxml_") and not bs[0].disabled
    assert bs[0].label == "Write the ISOXML TASKDATA (a new task data set of the clean readings)"
    assert any("the display's own set is not copied" in c.value for c in at.caption)
    bs[0].click().run()
    assert not at.exception, at.exception
    wd = at.session_state["workdir"]
    p = glob.glob(os.path.join(wd, "native", "*", "isoxml.json"))
    assert len(p) == 1
    W = json.load(open(p[0], encoding="utf-8"))
    assert W["n_kept"] == n_clean and W["check"]["ok"] is True and W["native"] is True and W["sms_tested"] is False
    # the written set is read back by the reader as the clean readings
    from engine.formats import isoxml
    back, _ = isoxml.decode(os.path.join(wd, W["path"]), None, log=lambda m: None)
    assert len(back) == n_clean
