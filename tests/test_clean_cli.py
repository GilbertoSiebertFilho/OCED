# -*- coding: utf-8 -*-
"""The command line cleans as the app does (synthetic data only): the import as SMS by default, the S1 clip of the
field of interest (not the 50 m buffer of the OCCD cascade), the same readings in and kept and the same L as the app's
route (engine.run.import_as_sms + the settings the app builds), and a planter file cleaned as an as-applied file.
Also the two run.py details the native writers and the AOI cache rely on.

    python -m pytest -q tests/test_clean_cli.py
"""
from __future__ import annotations

import dataclasses
import glob
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import sms3sigma as sms  # noqa: E402
from engine.formats import common  # noqa: E402
from tests.synthetic import make_applied, make_field  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("cli_field")))


def _record(work, tag):
    hits = glob.glob(os.path.join(work, "output*", f"{tag}*_cleaning.json"))
    assert len(hits) == 1, hits
    with open(hits[0], encoding="utf-8") as f:
        return json.load(f)


def test_cli_imports_as_sms_and_clips_like_the_app(field, tmp_path):
    tk = ["--scale-ticket", "110000", "--ticket-unit", "lb"]
    work = str(tmp_path / "cli")
    assert er.main([field["shp"], "--out", work, "--aoi", field["boundary"], "--tag", "cli"] + tk) == 0
    R = _record(work, "cli")
    # the app's route: Import as SMS of the file, then the settings app/oced.py settings_of builds
    shp_i, n_i, rec = er.import_as_sms(field["shp"], "app", str(tmp_path / "app_dec"), {}, crop="wheat",
                                       log=lambda m: None)
    RS = rec["resolved"]
    S_app = {"method": "sms3sigma", "tag": "app", "sms3sigma": {}, "machines": {"harmonise": False},
             "aoi": {"file": field["boundary"], "buffer_m": float(sms.DEFAULTS["clip_tolerance_m"]),
                     "clip_output": True, "feature": None},
             "scale_ticket": {"value": 110000.0, "unit": "lb", "basis": "wet", "moisture_pct": None, "note": None,
                              "area_ac": None},
             "test_weight_lb_bu": float(RS["test_weight_lb_bu"]), "moisture": {"standard_pct": RS["dry_moisture_pct"]}}
    A = er.clean(shp_i, str(tmp_path / "app_out"), S_app, log=lambda m: None)
    assert R["sms_import"]["n_in"] == n_i and R["sms_import"]["resolved"]["test_weight_lb_bu"] == RS["test_weight_lb_bu"]
    assert R["n_in"] == A["n_in"] and R["n_kept"] == A["n_kept"]
    assert R["level"]["factor"] == pytest.approx(A["level"]["factor"], rel=1e-12)
    assert R["aoi"]["buffer_m"] == pytest.approx(sms.DEFAULTS["clip_tolerance_m"])      # the clip, not 50 m
    assert R["n_read"] == n_i                                                         # the imported file is cleaned
    # without the import: the file as it is (the readings the import left out come back)
    work2 = str(tmp_path / "cli_raw")
    assert er.main([field["shp"], "--out", work2, "--aoi", field["boundary"], "--tag", "raw", "--no-sms-import"]) == 0
    R2 = _record(work2, "raw")
    assert "sms_import" not in R2 and R2["n_read"] == field["n"]
    # the import's minimum is S0's: --min-yield 0 keeps the low readings through S0 (only negatives would go)
    work3 = str(tmp_path / "cli_min0")
    assert er.main([field["shp"], "--out", work3, "--tag", "min0", "--min-yield", "0"]) == 0
    R3 = _record(work3, "min0")
    assert R3["sms3sigma"]["min_yield"]["source"] == "the file's Import as SMS"
    assert R3["cascade"][0]["removed"] == 0 and R3["sms_import"]["resolved"]["min_yield"] == 0


def test_cli_cleans_a_planter_file_as_applied(tmp_path):
    P = make_applied(str(tmp_path / "planter"), "seeding")
    work = str(tmp_path / "cli_planter")
    assert er.main([P["shp"], "--out", work, "--tag", "seed"]) == 0
    hits = glob.glob(os.path.join(work, "output*", "*.json"))
    assert hits, "no as-applied result written"


def test_sms_clean_defaults_set_only_what_is_missing():
    rec = {"resolved": {"test_weight_lb_bu": 48.0, "dry_moisture_pct": 14.5, "min_yield": 5.0}}
    S = er.sms_clean_defaults({"aoi": {"file": "b.geojson"}, "test_weight_lb_bu": 50.0}, rec)
    assert S["test_weight_lb_bu"] == 50.0 and S["moisture"]["standard_pct"] == 14.5 and S["sms_import"] is rec
    assert S["aoi"]["buffer_m"] == pytest.approx(0.01) and S["aoi"]["clip_output"] is True
    O = er.sms_clean_defaults({"method": "occd", "aoi": {"file": "b.geojson"}}, None)
    assert "buffer_m" not in O["aoi"] and "sms_import" not in O


def test_decode_source_and_aoi_cache_key():
    """decode_source carries the input root and the unit ids (the native writers read them); the AOI cache key
    changes with the decoder, its code revision and the options, so an older decode is never read back."""
    rep = {"format": "cnh_cn1", "label": "x", "units": ["u1", "u2"], "input_root": "C:/data/card",
           "options": {"shrink": "one_sided", "tz_offset_h": None}, "calibration": {}}
    src = er.decode_source({"report": rep, "n": 3})
    assert src["input_root"] == "C:/data/card" and src["unit_ids"] == ["u1", "u2"]
    rep_cnh = dict(rep, units=[{"id": "c1", "label": "task 1"}, {"id": "c2", "label": "task 2"}])
    assert er.decode_source({"report": rep_cnh, "n": 3})["unit_ids"] == ["c1", "c2"]      # the Case IH report
    o = common.DecodeOptions(shrink="one_sided")
    k1 = er.aoi_cache_key({"decoder": "cnh_cn1"}, "u1", o)
    assert k1 == er.aoi_cache_key({"decoder": "cnh_cn1"}, "u1", common.DecodeOptions(shrink="one_sided"))
    assert k1 != er.aoi_cache_key({"decoder": "jd_jdl"}, "u1", o)
    assert k1 != er.aoi_cache_key({"decoder": "cnh_cn1"}, "u2", o)
    assert k1 != er.aoi_cache_key({"decoder": "cnh_cn1"}, "u1", dataclasses.replace(o, shrink="symmetric"))
