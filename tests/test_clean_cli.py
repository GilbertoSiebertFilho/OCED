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
    # the record names the edge tolerance S1 used and the pre-step's cut (the PDF and the app print them)
    C = R["sms3sigma"]["clip"]
    assert C["edge_tolerance_m"] == pytest.approx(sms.DEFAULTS["clip_tolerance_m"])
    assert C["pre_step_buffer_m"] == pytest.approx(R["aoi"]["buffer_m"])
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


def test_cli_clips_a_reading_5_mm_outside_the_boundary(field, tmp_path):
    """The whole command-line cleaning (import as SMS, field-of-interest pre-step, S1) with two readings 5 mm either
    side of the boundary's east edge: at the default edge tolerance (0, as SMS) the one outside is clipped and the one
    inside kept; with sms3sigma.clip_tolerance_m = 0.01 in the settings file both are inside."""
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import pyogrio
    import shapely
    g = pyogrio.read_dataframe(field["shp"])
    bnd = gpd.read_file(field["boundary"])
    utm = bnd.estimate_utm_crs()
    U = bnd.to_crs(utm).geometry.union_all()
    c = U.centroid
    edge = shapely.LineString([(c.x, c.y), (c.x + 1e4, c.y)]).intersection(U.exterior)   # the east edge
    pts = gpd.GeoSeries([shapely.Point(edge.x - 0.005, edge.y), shapely.Point(edge.x + 0.005, edge.y)],
                        crs=utm).to_crs(g.crs)
    back = pts.to_crs(utm)
    d = shapely.distance(shapely.points(back.x.to_numpy(), back.y.to_numpy()), U.exterior)
    assert np.all((d > 0.004) & (d < 0.006))                                     # 5 mm either side
    two = g.iloc[[len(g) // 2, len(g) // 2 + 1]].copy().set_geometry(list(pts), crs=g.crs)
    e = gpd.GeoDataFrame(pd.concat([g, two], ignore_index=True), crs=g.crs)
    if "Obj__Id" in e.columns:
        e["Obj__Id"] = np.arange(1, len(e) + 1)
    shp = str(tmp_path / "edge" / "edge.shp")
    os.makedirs(os.path.dirname(shp))
    e.to_file(shp, engine="pyogrio")
    wide = str(tmp_path / "wide.json")
    with open(wide, "w", encoding="utf-8") as f:
        json.dump({"sms3sigma": {"clip_tolerance_m": 0.01}}, f)
    n_out = field["n"] - field["n_inside"]
    clips = {}
    for tag, extra in (("t0", []), ("t1", ["--settings", wide])):
        work = str(tmp_path / tag)
        assert er.main([shp, "--out", work, "--aoi", field["boundary"], "--tag", tag] + extra) == 0
        R = _record(work, tag)
        assert R["n_read"] == field["n"] + 2
        clips[tag] = R["sms3sigma"]["clip"]
    assert clips["t0"]["edge_tolerance_m"] == 0.0 and clips["t1"]["edge_tolerance_m"] == 0.01
    assert clips["t0"]["sms_clip_equivalent"] == n_out + 1                       # 5 mm outside: clipped
    assert clips["t1"]["sms_clip_equivalent"] == n_out                           # within 1 cm: inside


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
    assert S["aoi"]["buffer_m"] == pytest.approx(sms.DEFAULTS["clip_tolerance_m"]) and S["aoi"]["clip_output"] is True
    # the pre-step cuts at the S1 tolerance the settings give (else S1 could not keep what the pre-step set aside)
    T = er.sms_clean_defaults({"aoi": {"file": "b.geojson"}, "sms3sigma": {"clip_tolerance_m": 0.05}}, None)
    assert T["aoi"]["buffer_m"] == pytest.approx(0.05)
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


def _members(work):
    """The bytes of the clean and flagged .shp / .dbf of a command-line run."""
    out = {}
    for kind in ("clean", "flagged"):
        for ext in (".shp", ".dbf"):
            hits = glob.glob(os.path.join(work, "output*", f"*_sms3s_{kind}{ext}"))
            assert len(hits) == 1, hits
            with open(hits[0], "rb") as f:
                out[kind + ext] = f.read()
    return out


def test_cli_flags_for_the_manual_values_equal_the_import_keys(field, tmp_path, monkeypatch):
    """--manual-swath, --manual-moisture, --start-delay, --stop-delay and --flow-shift set the same import keys as the
    app's step 1: the flag route writes the same clean and flagged files, byte for byte, as a run whose import gets
    those keys directly (the wrapper the command line needed before)."""
    keys = {"use_manual_swath": True, "manual_swath_ft": 25.0, "use_manual_moisture": True,
            "manual_moisture_pct": 14.5, "start_delay_s": 2.0, "stop_delay_s": 1.0, "flow_shift_s": 1.0}
    base = [field["shp"], "--aoi", field["boundary"], "--tag", "man"]
    w1 = str(tmp_path / "flags")
    assert er.main(base + ["--out", w1, "--manual-swath", "25", "--manual-moisture", "14.5", "--start-delay", "2",
                           "--stop-delay", "1", "--flow-shift", "1"]) == 0
    orig = er.import_as_sms

    def wrapped(shp_, tag, folder, import_settings=None, **kw):
        return orig(shp_, tag, folder, dict(import_settings or {}, **keys), **kw)
    monkeypatch.setattr(er, "import_as_sms", wrapped)
    w2 = str(tmp_path / "wrapper")
    assert er.main(base + ["--out", w2]) == 0
    monkeypatch.setattr(er, "import_as_sms", orig)
    a, b = _members(w1), _members(w2)
    assert a == b
    R = _record(w1, "man")
    RS = R["sms_import"]["resolved"]
    assert {k: RS[k] for k in keys} == keys
    ap_ = R["sms_import"]["applied"]
    assert ap_["manual_swath"] and ap_["manual_moisture"] and ap_["flow_shift"] and ap_["start_stop_delay"]
    assert "manual swath 25.00 ft" in R["sms_import"]["settings"] and "NOT applied" not in R["sms_import"]["settings"]


def test_cli_manual_moisture_is_used_with_two_decimals_and_needs_the_import(field, tmp_path, capsys):
    w = str(tmp_path / "mm")
    assert er.main([field["shp"], "--out", w, "--aoi", field["boundary"], "--tag", "mm",
                    "--manual-moisture", "14.163"]) == 0
    assert "--manual-moisture 14.163 % is used as 14.16 %" in capsys.readouterr().out
    R = _record(w, "mm")
    assert R["sms_import"]["resolved"]["manual_moisture_pct"] == 14.16
    s3 = [s for s in R["sms3sigma"]["steps"] if s["step"] == "S3"]
    assert s3 and all(s["removed"] == 0 for s in s3)
    assert er.main([field["shp"], "--out", str(tmp_path / "no"), "--no-sms-import", "--manual-swath", "20"]) == 2


def test_sms_min_yield_overridden_by_the_import_is_a_warning(field, tmp_path):
    """--sms-min-yield with the import on: S0 keeps the import's minimum (nothing moves) and one warning names the
    value asked for and the one in force; the same value as the import's says nothing."""
    w = str(tmp_path / "my")
    assert er.main([field["shp"], "--out", w, "--aoi", field["boundary"], "--tag", "my", "--sms-min-yield",
                    "20"]) == 0
    R = _record(w, "my")
    w_ = [x for x in R["warnings"] if x.startswith("SMS 3-sigma S0: the minimum yield asked for")]
    assert len(w_) == 1 and "20 bu/ac) is not used" in w_[0] and "The minimum in force is none" in w_[0]
    w0 = str(tmp_path / "my0")
    assert er.main([field["shp"], "--out", w0, "--aoi", field["boundary"], "--tag", "my"]) == 0
    R0 = _record(w0, "my")
    assert R0["n_kept"] == R["n_kept"] and not any("minimum yield asked for" in x for x in R0["warnings"])
    w1 = str(tmp_path / "my1")
    assert er.main([field["shp"], "--out", w1, "--aoi", field["boundary"], "--tag", "my", "--sms-min-yield",
                    "0"]) == 0
    assert not any("minimum yield asked for" in x for x in _record(w1, "my")["warnings"])


def test_wdth_raw_is_named_for_what_it_holds(field, tmp_path):
    """After a manual swath Wdth_Raw holds the width the file was imported with (the manual one), not the width the
    monitor logged: the cleaning's note and the command line's sentence say so; without one, 'the original width'."""
    w = str(tmp_path / "ms")
    assert er.main([field["shp"], "--out", w, "--aoi", field["boundary"], "--tag", "ms", "--manual-swath", "25"]) == 0
    R = _record(w, "ms")
    ch = R["sms3sigma"]["difm_ready_changes"]
    assert ch["wdth_raw"].startswith("the width the file was imported with (the manual swath 25 ft")
    txt = " ".join(R["notes"])
    assert "the manual swath 25 ft, not the width the monitor logged) is in Wdth_Raw" in txt
    assert "the original width is in Wdth_Raw" not in txt
    assert "the manual swath 25 ft" in er.difm_note(R)
    w0 = str(tmp_path / "ms0")
    assert er.main([field["shp"], "--out", w0, "--aoi", field["boundary"], "--tag", "ms0"]) == 0
    R0 = _record(w0, "ms0")
    assert R0["sms3sigma"]["difm_ready_changes"]["wdth_raw"] == "the original width"
    assert "the original width is in Wdth_Raw" in " ".join(R0["notes"])


def test_cli_says_the_grain_the_import_left_out(field, tmp_path, capsys):
    w = str(tmp_path / "lo")
    assert er.main([field["shp"], "--out", w, "--aoi", field["boundary"], "--tag", "lo", "--min-yield", "5",
                    "--scale-ticket", "100000"]) == 0
    out = capsys.readouterr().out
    R = _record(w, "lo")
    lo = R["level"]["import_left_out"]
    line = next(x for x in out.splitlines() if x.strip().startswith("import left out"))
    assert f"{lo['steps']['below the min. yield volume']['n']:,} below the min. yield volume" in line
    assert "in the monitor total L is built on" in line and lo["included_in_L"]
