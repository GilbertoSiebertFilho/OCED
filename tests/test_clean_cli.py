# -*- coding: utf-8 -*-
"""The command line cleans as the app does (synthetic data only): the import as SMS by default, the S1 clip of the
field of interest (not the 50 m buffer of the OCCD cascade), the same readings in and kept and the same L as the app's
route (engine.run.import_as_sms + the settings the app builds), the crop of a point export decided as the app does
(durum), and a planter file cleaned as an as-applied file.
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
                                       log=lambda m: None, fmt=er.import_format(None, {"kind": "export"}))
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
    # a point export: SMS's generic import keeps every reading, and S0 takes its minimum (none above 0)
    assert R["sms_import"]["fmt"] == "point_export" and n_i == field["n"]
    S0 = next(r for r in R["cascade"] if r["filter"] == "S0")
    assert R["sms_import"]["resolved"]["min_yield"] == 0.0 and S0["removed"] == 0
    # without the import: the file as it is (the readings the import left out come back)
    work2 = str(tmp_path / "cli_raw")
    assert er.main([field["shp"], "--out", work2, "--aoi", field["boundary"], "--tag", "raw", "--no-sms-import"]) == 0
    R2 = _record(work2, "raw")
    assert "sms_import" not in R2 and R2["n_read"] == field["n"]
    # the import's minimum is S0's: --min-yield 5 leaves the low readings out at import, S0 finds none
    work3 = str(tmp_path / "cli_min5")
    assert er.main([field["shp"], "--out", work3, "--tag", "min5", "--min-yield", "5"]) == 0
    R3 = _record(work3, "min5")
    assert R3["sms3sigma"]["min_yield"]["source"] == "the file's Import as SMS"
    assert R3["cascade"][0]["removed"] == 0 and R3["sms_import"]["resolved"]["min_yield"] == 5
    assert R3["sms_import"]["left_out"]["below the min. yield volume"] > 0
    assert R3["sms_import"]["sources"]["min_yield"] == "you"


def test_cli_takes_the_crop_of_a_durum_export_as_the_app(field, tmp_path):
    """The command line decides the crop of a point export as the app does (the import's crop key): a product naming
    durum is SMS's Wheat - Durum (60 lb/bu, 13.0 %), not Wheat - Spring; so is an Operations Center export whose
    metadata names durum while its Product column holds a variety."""
    import pyogrio
    g = pyogrio.read_dataframe(field["shp"])
    p1 = str(tmp_path / "d" / "Synthetic_durum.shp")
    p2 = str(tmp_path / "o" / "Synthetic_ops.shp")
    for p, prod in ((p1, "Wheat - Durum"), (p2, "Variety 7")):
        os.makedirs(os.path.dirname(p))
        g.assign(Product=prod).to_file(p, engine="pyogrio")
    with open(os.path.splitext(p2)[0] + "-Deere-Metadata.json", "w", encoding="utf-8") as fh:
        json.dump({"CropName": "Wheat (Durum)", "CropId": 24}, fh)
    for p, tag, fmt in ((p1, "durum", "point_export"), (p2, "ops", "jd_ops_center")):
        work = str(tmp_path / f"cli_{tag}")
        assert er.main([p, "--out", work, "--tag", tag]) == 0
        IM = _record(work, tag)["sms_import"]
        assert IM["fmt"] == fmt and IM["sms_product"] == "Wheat - Durum", (IM["fmt"], IM["sms_product"])
        assert (IM["resolved"]["test_weight_lb_bu"], IM["resolved"]["dry_moisture_pct"]) == (60.0, 13.0)


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


def test_cli_names_a_product_chosen_for_a_point_export_as_the_app(field, tmp_path):
    """0.3.2 (O3): --product on a point export of another crop names the crop used in the imported and the clean file
    as the app does (Product: the SMS product name, Crop: the crop key); the export's own crop changes nothing."""
    import glob
    import pyogrio
    work = str(tmp_path / "cli_b")
    assert er.main([field["shp"], "--out", work, "--tag", "barley", "--product", "barley"]) == 0
    for pat in ("**/barley_imported.shp", "**/*barley*clean*.shp"):
        shp = [p for p in glob.glob(os.path.join(work, pat), recursive=True) if "flag" not in os.path.basename(p)]
        assert shp, pat
        g = pyogrio.read_dataframe(shp[0], read_geometry=False)
        assert set(g["Product"]) == {"Barley - Fall"} and set(g["Crop"]) == {"barley"}, pat
    work = str(tmp_path / "cli_w")
    assert er.main([field["shp"], "--out", work, "--tag", "wheat", "--product", "wheat"]) == 0
    shp = glob.glob(os.path.join(work, "**", "wheat_imported.shp"), recursive=True)
    g = pyogrio.read_dataframe(shp[0] if shp else field["shp"], read_geometry=False)
    assert set(g["Product"]) == {"Wheat"} and "Crop" not in g.columns


def test_isoxml_of_a_crop_code_export_names_the_crop_its_import_used(field, tmp_path):
    """0.3.2 (R1): a point export whose Crop column holds a crop code (a number), with no Product column and no
    metadata naming its crop, imported with --product barley and cleaned: the imported and the clean file name barley
    (Product and Crop_Name, the code left as it is), and the ISOXML written from the clean file names barley as its
    crop type (CTP) and product (PDT), which OCED's own decoder reads back as barley. Imported with the default, the
    crop is not known: the set keeps the code as its crop type, and names the crop the import used when the source
    gives one."""
    import re
    import numpy as np
    import pyogrio
    from engine.formats import native_write as nw
    g = pyogrio.read_dataframe(field["shp"]).drop(columns=["Product"])
    g["Crop"] = np.int64(7)
    os.makedirs(tmp_path / "in")
    shp = str(tmp_path / "in" / "export.shp")
    pyogrio.write_dataframe(g, shp)

    def run(name, *extra):
        work = str(tmp_path / name)
        assert er.main([shp, "--out", work, "--tag", name] + list(extra)) == 0
        imp = glob.glob(os.path.join(work, "**", f"{name}_imported.shp"), recursive=True)
        cl = [p for p in glob.glob(os.path.join(work, "**", f"{name}*clean*.shp"), recursive=True)
              if "flag" not in os.path.basename(p)]
        return imp[0] if imp else None, cl[0]

    def iso(clean, out, source):
        nw.write(nw.ISOXML, source, clean, out, log=lambda m: None)
        x = open(glob.glob(os.path.join(out, "**", "TASKDATA.XML"), recursive=True)[0], encoding="utf-8").read()
        return re.findall(r'<CTP A="CTP-1" B="([^"]*)"', x), re.findall(r'<PDT A="PDT-\d+" B="([^"]*)"', x)

    imp, cl = run("barley", "--product", "barley")
    for p in (imp, cl):
        e = pyogrio.read_dataframe(p, read_geometry=False)
        assert set(e["Crop"]) == {7} and set(e["Product"]) == {"Barley - Fall"} and set(e["Crop_Name"]) == {"barley"}
    out = str(tmp_path / "iso_b")
    assert iso(cl, out, {"kind": "export"}) == (["barley"], ["Barley - Fall"])
    cand = [c for c in er.open_input([out], str(tmp_path / "rb"), log=lambda m: None) if c.get("kind") == "raw"][0]
    assert {u.crop for u in er.list_units(cand)} == {"barley"}
    dec = er.decode(cand, None, None, str(tmp_path / "rb"), log=lambda m: None, tag="RB")
    assert dec["report"]["crop_name"] == "barley"
    _, cl0 = run("plain")
    assert iso(cl0, str(tmp_path / "iso_0"), {"kind": "export"}) == (["7"], ["Harvest"])
    assert iso(cl0, str(tmp_path / "iso_w"), {"kind": "export", "options": {"crop": "wheat"}})[0] == ["wheat"]
