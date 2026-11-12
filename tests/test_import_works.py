# -*- coding: utf-8 -*-
"""Saved works (engine/works.py) on synthetic folders: the input folder and the decode report of a decoded file
survive a save, a reopen and a moved workspace; an older folder is rebuilt with the grower's own bushel weight and
use; a cleaning made by an older engine is marked 'clean again'.

    python -m pytest -q tests/test_import_works.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import works as ew  # noqa: E402


def _decoded_work(ws, name="20000101-120000_Synthetic"):
    """A work folder with an unpacked card under input/ and its decoded file, as the app leaves them."""
    wd = os.path.join(ws, name)
    card = os.path.join(wd, "input", "card", "RCD")
    os.makedirs(card)
    open(os.path.join(card, "Data.fdd"), "wb").write(b"\x00" * 16)
    dec = os.path.join(wd, "decoded")
    os.makedirs(dec)
    shp = os.path.join(dec, "T_decoded.shp")
    for e in (".shp", ".shx", ".dbf"):
        open(shp[:-4] + e, "wb").write(b"")
    rj = os.path.join(dec, "T_decode_report.json")
    rep = {"format": "jd_gs3_rcd", "input_root": os.path.join(wd, "input", "card"), "units": [{"id": "u1"}]}
    json.dump(rep, open(rj, "w", encoding="utf-8"))
    D = {"tag": "T", "shp": shp, "zip": None, "n": 0, "kind": "raw", "op": "harvest", "yield": True, "label": "T",
         "report": rep, "source": {"kind": "decoded", "format": "jd_gs3_rcd", "decode_report": rj,
                                   "decoded_shp": shp},
         "sms_import": {"all_readings": shp, "resolved": {"min_yield": 5.0}}}
    return wd, D


def test_input_folder_kept_and_found_after_a_move(tmp_path):
    wd, D = _decoded_work(str(tmp_path / "ws"))
    rec = ew.make_record(wd, "Synthetic", datasets={"T": D})
    d = rec["datasets"]["T"]
    assert d["report"]["input_root"] == "input/card" and d["source"]["input_root"] == "input/card"
    assert d["source"]["decode_report"] == "decoded/T_decode_report.json" and d["shp"] == "decoded/T_decoded.shp"
    assert d["sms_import"]["all_readings"] == "decoded/T_decoded.shp"
    ew.save_work(wd, rec)
    # the workspace moved to another place: every path comes back under the new work folder
    moved = str(tmp_path / "other" / os.path.basename(wd))
    shutil.copytree(wd, moved)
    shutil.rmtree(wd)
    back = ew.load_work(moved)["datasets"]["T"]
    root = os.path.join(moved, "input", "card")
    assert os.path.normcase(back["source"]["input_root"]) == os.path.normcase(root)
    assert os.path.normcase(back["report"]["input_root"]) == os.path.normcase(root)
    assert os.path.normcase(ew.input_root(back, moved)) == os.path.normcase(root)
    assert os.path.exists(back["source"]["decode_report"]) and os.path.exists(back["shp"])


def test_absolute_paths_of_an_older_record_found_again(tmp_path):
    """A record that kept the paths absolute (an older version), after the workspace moved."""
    wd, D = _decoded_work(str(tmp_path / "ws"))
    rec = ew.make_record(wd, "Synthetic", datasets={"T": D})
    rec["datasets"]["T"]["report"]["input_root"] = os.path.join(wd, "input", "card")      # as an older save did
    rec["datasets"]["T"]["source"].pop("input_root")
    ew.save_work(wd, rec)
    moved = str(tmp_path / "elsewhere" / os.path.basename(wd))
    shutil.move(wd, moved)
    back = ew.load_work(moved)["datasets"]["T"]
    assert os.path.normcase(back["report"]["input_root"]) == os.path.normcase(os.path.join(moved, "input", "card"))
    assert os.path.normcase(ew.input_root(back, moved)) == os.path.normcase(os.path.join(moved, "input", "card"))
    # a card read in place outside the work folder stays where it was (and is None-safe)
    outside = str(tmp_path / "card_in_place")
    assert ew.resolve_moved(outside, moved) == outside and ew.resolve_moved(None, moved) is None


def test_legacy_record_grower_ticket_and_clean_again(tmp_path):
    """An older folder: the grower's own bushel weight and 'validate' come from scale_ticket, and a cleaning whose
    level lacks the combine-factor totals is marked to be cleaned again."""
    wd = str(tmp_path / "ws" / "20261101-090000_Old")
    os.makedirs(os.path.join(wd, "clean", "T"))
    src = os.path.join(wd, "imported", "T_imported.shp")
    os.makedirs(os.path.dirname(src))
    for e in (".shp", ".shx", ".dbf"):
        open(src[:-4] + e, "wb").write(b"")
    R = {"input": src, "n_in_file": 10, "files": {"input": src},
         "settings": {"test_weight_lb_bu": 60.0, "crop": "wheat",
                      "scale_ticket": {"value": 1000.0, "unit": "bu", "basis": "wet", "use": "validate",
                                       "test_weight_lb_bu": 62.5}},
         "level": {"factor": 1.01, "export_total_bu": 990.0}}
    json.dump(R, open(os.path.join(wd, "clean", "T", "T_sms3s_cleaning.json"), "w", encoding="utf-8"))
    rec = ew.load_work(wd)
    G = rec["grower"]["T"]
    assert G["use"] == "validate" and G["test_weight"] == 62.5
    assert "clean it again" in rec["cleaned"]["T"]["clean_again"]
    # the record of the current engine: nothing to say
    R["level"]["monitor_total_final_bu"] = 990.0
    assert ew.clean_again_reason(R) is None and ew.clean_again_reason({"n_in": 3}) is None
    # a ticket without its own bushel weight: the import's, as before
    R["settings"]["scale_ticket"].pop("test_weight_lb_bu")
    R["settings"]["scale_ticket"].pop("use")
    json.dump(R, open(os.path.join(wd, "clean", "T", "T_sms3s_cleaning.json"), "w", encoding="utf-8"))
    G = ew.load_work(wd)["grower"]["T"]
    assert G["test_weight"] == 60.0 and G["use"] == "adjust"
    assert "clean_again" not in ew.load_work(wd)["cleaned"]["T"]


def test_a_copied_work_reads_its_own_files(tmp_path):
    """VA-10: a work whose record kept absolute paths (an older version), COPIED to another workspace while the
    original is still there: every path of the copy points into the copy, not into the folder it came from; a card
    read in place elsewhere stays where it was."""
    wd, D = _decoded_work(str(tmp_path / "ws"))
    rec = ew.make_record(wd, "Synthetic", datasets={"T": D})
    d = rec["datasets"]["T"]
    for part, k in (("report", "input_root"), ("source", "decode_report"), ("source", "decoded_shp"),
                    ("sms_import", "all_readings")):
        d[part][k] = ew.abspath(d[part][k], wd)                  # as an older save kept them
    d["source"].pop("input_root", None)
    ew.save_work(wd, rec)
    copy = str(tmp_path / "ws_copy" / os.path.basename(wd))
    shutil.copytree(wd, copy)
    back = ew.load_work(copy)["datasets"]["T"]
    for p in (back["report"]["input_root"], back["source"]["decode_report"], back["source"]["decoded_shp"],
              back["sms_import"]["all_readings"], ew.input_root(back, copy)):
        assert os.path.normcase(p).startswith(os.path.normcase(copy) + os.sep), p
    outside = str(tmp_path / "card_in_place")
    os.makedirs(outside)
    assert ew.resolve_moved(outside, copy) == outside


def test_the_cleaning_config_is_saved_with_the_work(tmp_path):
    """R3: the config a cleaning ran with (the app's file_config) is saved with the work, its boundary path relative
    when it lies in the work folder, and comes back equal (lists and plain values), so that a change made after the
    cleaning and saved with the work still compares as changed."""
    wd, D = _decoded_work(str(tmp_path / "ws"))
    bnd = os.path.join(wd, "boundary", "T", "Field.geojson")
    os.makedirs(os.path.dirname(bnd))
    open(bnd, "w").write("{}")
    cfg = {"sms3sigma": {"k_sd": 3.0, "min_yield": 5.0, "filter_order": "moisture_speed"},
           "boundary": [os.path.abspath(bnd), [1, 2], "0123456789abcdef"],
           "grower": {"weight": 110000.0, "unit": "lb", "std_moisture": 13.5}, "combines": None}
    C = {"json": os.path.join(wd, "clean", "T", "T_cleaning.json"), "shp": os.path.join(wd, "clean_shapefiles",
                                                                                         "T_sms3s_clean.shp"),
         "settings": {"k_sd": 3.0}, "config": cfg, "kind": "sms", "at": "12:00:00"}
    rec = ew.make_record(wd, "Synthetic", datasets={"T": D}, cleaned={"T": C})
    assert rec["cleaned"]["T"]["config"]["boundary"][0] == "boundary/T/Field.geojson"
    ew.save_work(wd, rec)
    moved = str(tmp_path / "other" / os.path.basename(wd))
    shutil.copytree(wd, moved)
    shutil.rmtree(wd)
    back = ew.load_work(moved)["cleaned"]["T"]["config"]
    assert back == {**cfg, "boundary": [os.path.abspath(os.path.join(moved, "boundary", "T", "Field.geojson")),
                                        [1, 2], "0123456789abcdef"]}
    assert ew.make_record(wd, "x", cleaned={"T": {**C, "config": None}})["cleaned"]["T"]["config"] is None
