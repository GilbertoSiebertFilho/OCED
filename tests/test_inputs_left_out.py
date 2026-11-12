# -*- coding: utf-8 -*-
"""An input left out when the data was opened (a damaged zip among the zips of a zip or of a folder) is named, with
the reason, wherever the work is recorded: the candidates, the decode report (its warnings and 'inputs_left_out'),
the source of the cleaning, the cleaning record (JSON) and report (PDF), and the saved work, which says it again when
it is opened in a new session. Synthetic data only (tests/synthetic.py, tests/synthetic_isoxml.py,
tests/synthetic_jdl.py): every name and number is made up.

    python -m pytest -q tests/test_inputs_left_out.py
"""
from __future__ import annotations

import glob
import io
import json
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine import works as ew  # noqa: E402
from engine.clean import applied3s as a3  # noqa: E402
from tests import synthetic_isoxml as SI  # noqa: E402
from tests.synthetic import make_applied, make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
Q = lambda m: None  # noqa: E731
BROKEN = "Synthetic broken set.zip"                    # the damaged zip among those of the input
NOT_A_ZIP = b"PK this is not a zip any more"


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("data")))


def _pdf_text(path):
    try:
        import fitz                                      # pymupdf, when installed
    except ImportError:
        return None
    with fitz.open(path) as d:
        return " ".join(" ".join(p.get_text().split()) for p in d)


def _iso_zip(tmp_path) -> str:
    """A zip of zipped ISOXML sets (two halves of one made-up harvest) with a third member that is no zip."""
    R = SI.harvest(n_pass=6, n=60)
    cut = len(R["t"]) // 2 + 20
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), SI.take(R, 0, cut))["folder"]
    b = SI.write_set(str(tmp_path / "in" / "s2" / "TASKDATA"), SI.take(R, cut - 1, len(R["t"])))["folder"]
    z = SI.zip_sets([a, b], str(tmp_path / "Synthetic task data.zip"))
    with zipfile.ZipFile(z, "a") as zf:
        zf.writestr(BROKEN, NOT_A_ZIP)
    return z


def _export_zip(shp: str, zpath: str) -> str:
    """A zip holding the zipped shapefile of a point export and a second member that is no zip."""
    stem = os.path.splitext(shp)[0]
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as zi:
        for p in sorted(glob.glob(stem + ".*")):
            zi.write(p, os.path.basename(p))
    os.makedirs(os.path.dirname(zpath), exist_ok=True)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Synthetic export.zip", inner.getvalue())
        z.writestr(BROKEN, NOT_A_ZIP)
    return zpath


def _names_it(lines) -> list:
    """The lines that name the damaged zip, say it was left out and why."""
    return [w for w in lines if BROKEN in w and "left out" in w and "not a readable zip" in w
            and "NOT in the data" in w]


# ================================================================================================ engine
def test_isoxml_the_zip_left_out_is_in_the_decode_report_and_the_cleaning_record(tmp_path):
    cands = er.open_input([_iso_zip(tmp_path)], str(tmp_path / "w"), log=Q)
    assert [c.get("decoder") for c in cands] == ["isoxml"] and len(_names_it(cands.left_out)) == 1
    assert cands[0]["inputs_left_out"] == cands.left_out            # every candidate of the input carries it
    dec = er.decode(cands[0], None, None, str(tmp_path / "w"), log=Q)
    rep = dec["report"]
    assert rep["inputs_left_out"] == cands.left_out and len(_names_it(rep["warnings"])) == 1
    on_disk = json.load(open(dec["report_json"], encoding="utf-8"))
    assert on_disk["inputs_left_out"] == cands.left_out and len(_names_it(on_disk["warnings"])) == 1
    assert dec["source"]["inputs_left_out"] == cands.left_out and len(_names_it(dec["source"]["warnings"])) == 1
    R = er.clean(dec["shp"], str(tmp_path / "out"), {"method": "sms3sigma"}, log=Q, source=dec["source"])
    assert R["inputs_left_out"] == cands.left_out
    assert len(_names_it(R["warnings"])) == 1                       # said once, not once more as a decoder warning
    assert _names_it(R["warnings"])[0].startswith("input: ")
    saved = json.load(open(R["files"]["json"], encoding="utf-8"))
    assert saved["inputs_left_out"] == cands.left_out and len(_names_it(saved["warnings"])) == 1
    text = _pdf_text(R["files"]["report_pdf"])
    if text is not None:
        assert BROKEN in text and "left out" in text


def test_nothing_left_out_is_an_empty_list_everywhere(tmp_path):
    R0 = SI.harvest(n_pass=4, n=40)
    a = SI.write_set(str(tmp_path / "in" / "s1" / "TASKDATA"), R0)["folder"]
    cands = er.open_input([SI.zip_sets([a], str(tmp_path / "Synthetic task data.zip"))], str(tmp_path / "w"), log=Q)
    assert cands.left_out == [] and "inputs_left_out" not in cands[0]
    dec = er.decode(cands[0], None, None, str(tmp_path / "w"), log=Q)
    assert dec["report"]["inputs_left_out"] == [] and dec["source"]["inputs_left_out"] == []
    assert not any("left out" in w for w in dec["report"]["warnings"])
    R = er.clean(dec["shp"], str(tmp_path / "out"), {"method": "sms3sigma"}, log=Q, source=dec["source"])
    assert R["inputs_left_out"] == [] and not any(w.startswith("input: ") for w in R["warnings"])


def test_a_point_export_the_zip_left_out_is_in_the_cleaning_record(field, tmp_path):
    """A point export has no decode report: the candidate carries what was left out and the cleaning takes it."""
    cands = er.open_input([_export_zip(field["shp"], str(tmp_path / "in" / "Synthetic exports.zip"))],
                          str(tmp_path / "w"), log=Q)
    assert [c["kind"] for c in cands] == ["export"] and len(_names_it(cands.left_out)) == 1
    assert cands[0]["inputs_left_out"] == cands.left_out
    R = er.clean(cands[0]["path"], str(tmp_path / "out"), {"method": "sms3sigma"}, log=Q,
                 inputs_left_out=cands[0]["inputs_left_out"])
    assert R["inputs_left_out"] == cands.left_out and len(_names_it(R["warnings"])) == 1
    saved = json.load(open(R["files"]["json"], encoding="utf-8"))
    assert saved["inputs_left_out"] == cands.left_out and len(_names_it(saved["warnings"])) == 1
    text = _pdf_text(R["files"]["report_pdf"])
    if text is not None:
        assert BROKEN in text and "left out" in text


def test_a_planter_file_the_zip_left_out_is_in_its_cleaning_record(tmp_path):
    A = make_applied(str(tmp_path / "data"), "seeding")
    cands = er.open_input([_export_zip(A["shp"], str(tmp_path / "in" / "Synthetic seeding.zip"))],
                          str(tmp_path / "w"), log=Q)
    assert len(cands) == 1 and cands[0].get("yield") is False
    R = a3.run(cands[0]["path"], str(tmp_path / "out"), {}, tag="syn", log=Q,
               inputs_left_out=cands[0]["inputs_left_out"])
    assert R["inputs_left_out"] == cands.left_out and len(_names_it(R["warnings"])) == 1
    saved = json.load(open(R["files"]["json"], encoding="utf-8"))
    assert saved["inputs_left_out"] == cands.left_out
    text = _pdf_text(R["files"]["report_pdf"])
    if text is not None:
        assert BROKEN in text and "left out" in text
    assert a3.run(A["shp"], str(tmp_path / "out2"), {}, tag="syn", log=Q)["inputs_left_out"] == []


def test_the_command_line_records_it_for_a_raw_dataset_and_for_an_export(field, tmp_path, capsys):
    assert er.main([_iso_zip(tmp_path), "--out", str(tmp_path / "cli_raw"), "--method", "sms3sigma"]) == 0
    recs = glob.glob(str(tmp_path / "cli_raw" / "output" / "*_cleaning.json"))
    assert len(recs) == 1 and len(_names_it(json.load(open(recs[0], encoding="utf-8"))["inputs_left_out"])) == 1
    z = _export_zip(field["shp"], str(tmp_path / "in2" / "Synthetic exports.zip"))
    assert er.main([z, "--out", str(tmp_path / "cli_exp"), "--method", "sms3sigma"]) == 0
    recs = glob.glob(str(tmp_path / "cli_exp" / "output" / "*_cleaning.json"))
    assert len(recs) == 1 and len(_names_it(json.load(open(recs[0], encoding="utf-8"))["inputs_left_out"])) == 1
    assert BROKEN in capsys.readouterr().out


def test_a_john_deere_log_zip_per_combine_one_of_them_damaged(tmp_path):
    """Another raw format: a zip holding one zip per combine (JD-Data logs), one of them damaged."""
    from tests import synthetic_jdl as SJ
    card = SJ.make_card(str(tmp_path / "card"))
    root = card["root"] if isinstance(card, dict) else str(card)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as zi:
        for dp, _, fn in os.walk(root):
            for f in fn:
                p = os.path.join(dp, f)
                zi.write(p, os.path.relpath(p, os.path.dirname(root)))
    z = str(tmp_path / "Synthetic logs.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Synthetic combine 1.zip", inner.getvalue())
        zf.writestr(BROKEN, NOT_A_ZIP)
    cands = er.open_input([z], str(tmp_path / "w"), log=Q)
    assert [c.get("decoder") for c in cands] == ["jd_jdl"] and len(_names_it(cands.left_out)) == 1
    dec = er.decode(cands[0], None, None, str(tmp_path / "w"), log=Q)
    assert dec["report"]["inputs_left_out"] == cands.left_out and len(_names_it(dec["report"]["warnings"])) == 1
    assert dec["source"]["inputs_left_out"] == cands.left_out


def test_the_saved_work_keeps_what_was_left_out(tmp_path):
    wd = str(tmp_path / "ws" / "20260101-000000_syn")
    os.makedirs(wd)
    msg = [f"{BROKEN}: a damaged zip among those of the input, left out (made up)"]
    rec = ew.make_record(wd, "Synthetic work", datasets={}, inputs_left_out=msg)
    assert rec["inputs_left_out"] == msg
    ew.save_work(wd, rec)
    assert ew.load_work(wd)["inputs_left_out"] == msg
    assert ew.make_record(wd, "Synthetic work", datasets={})["inputs_left_out"] == []
    # a record without the list (a folder rebuilt from its files): what its files carry, each once
    files = {"datasets": {"a": {"report": {"inputs_left_out": msg}}, "b": {"inputs_left_out": msg + ["another"]},
                          "c": {"report": None}}}
    assert ew.inputs_left_out(files) == msg + ["another"]
    assert ew.inputs_left_out({"inputs_left_out": [], **files}) == [] and ew.inputs_left_out(None) == []


# ================================================================================================ the app
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


def _reopen(ws, monkeypatch):
    """A new session on the same workspace with its one saved work opened."""
    at = _app(ws, monkeypatch)
    assert not at.session_state["datasets"] and not _names_it(w.value for w in at.warning)
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert at.session_state["datasets"] and at.session_state["cands"] is None
    return at


def test_app_isoxml_the_zip_left_out_is_recorded_saved_and_said_again(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    at = _app(ws, monkeypatch)
    _open(at, _iso_zip(tmp_path))
    assert len(_names_it(w.value for w in at.warning)) == 1                 # on screen when the input is opened
    left = list(at.session_state["cands"].left_out)
    next(x for x in at.button if str(x.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    tag = at.session_state["active"]
    D = at.session_state["datasets"][tag]
    assert D["inputs_left_out"] == left and D["report"]["inputs_left_out"] == left
    assert len(_names_it(D["report"]["warnings"])) == 1
    rj = glob.glob(os.path.join(at.session_state["workdir"], "decoded", "*_decode_report.json"))
    assert len(rj) == 1 and json.load(open(rj[0], encoding="utf-8"))["inputs_left_out"] == left
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    C = at.session_state["cleaned"][tag]
    assert C["R"]["inputs_left_out"] == left and len(_names_it(C["R"]["warnings"])) == 1
    assert json.load(open(C["json"], encoding="utf-8"))["inputs_left_out"] == left
    wd = at.session_state["workdir"]
    assert json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))["inputs_left_out"] == left
    # a new session: the work opened again says what was left out when its data was read
    at2 = _reopen(ws, monkeypatch)
    shown = [w.value for w in at2.warning]
    assert left[0] in shown                                    # step 1, as when the input was opened
    assert "input: " + left[0] in shown                        # with the cleaning's result
    assert any("1 damaged zip(s) of the input were left out" in s for s in shown)     # the 'Opened ...' message
    assert at2.session_state["cleaned"][tag]["R"]["inputs_left_out"] == left
    assert at2.session_state["datasets"][tag]["inputs_left_out"] == left
    # saved again from the new session (a cleaning saves the work): still there
    at2.button(key="clean_one").click().run()
    assert not at2.exception, at2.exception
    assert json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))["inputs_left_out"] == left
    assert at2.session_state["cleaned"][tag]["R"]["inputs_left_out"] == left


def test_app_point_export_the_zip_left_out_is_recorded_saved_and_said_again(field, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    at = _app(ws, monkeypatch)
    _open(at, _export_zip(field["shp"], str(tmp_path / "in" / "Synthetic exports.zip")))
    assert len(_names_it(w.value for w in at.warning)) == 1
    left = list(at.session_state["cands"].left_out)
    tag = at.session_state["active"]
    assert at.session_state["datasets"][tag]["inputs_left_out"] == left
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    C = at.session_state["cleaned"][tag]
    assert C["R"]["inputs_left_out"] == left and len(_names_it(C["R"]["warnings"])) == 1
    assert json.load(open(C["json"], encoding="utf-8"))["inputs_left_out"] == left
    wd = at.session_state["workdir"]
    assert json.load(open(os.path.join(wd, "oced_work.json"), encoding="utf-8"))["inputs_left_out"] == left
    at2 = _reopen(ws, monkeypatch)
    shown = [w.value for w in at2.warning]
    assert left[0] in shown and "input: " + left[0] in shown
    assert any("1 damaged zip(s) of the input were left out" in s for s in shown)
    assert at2.session_state["datasets"][tag]["inputs_left_out"] == left
    # the work folder without its saved-work file (rebuilt from its files): the cleaning record still says it
    os.remove(os.path.join(wd, "oced_work.json"))
    legacy = ew.load_work(wd)
    assert legacy["legacy"] and "inputs_left_out" not in legacy and ew.inputs_left_out(legacy) == left
    at4 = _reopen(ws, monkeypatch)
    assert left[0] in [w.value for w in at4.warning] and at4.session_state["left_out"] == left
    # a work with nothing left out says nothing of the kind
    ws0 = tmp_path / "ws0"
    at0 = _app(ws0, monkeypatch)
    _open(at0, field["shp"])
    assert not any("left out (" in w.value for w in at0.warning)
    assert json.load(open(glob.glob(str(ws0 / "*" / "oced_work.json"))[0], encoding="utf-8"))["inputs_left_out"] == []
    at3 = _reopen(ws0, monkeypatch)
    assert not any("left out (" in w.value for w in at3.warning)
