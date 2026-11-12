# -*- coding: utf-8 -*-
"""The wires between the engine modules, each checked on the synthetic cards of tests/ (no real data):
engine.run.decode_source gives the writers and the import what they read (input_root, unit_ids, the card Summary,
the crop definition of the file); engine.formats.native_write offers each raw format's own writer first and ISOXML
last, forwards every writer's own options and lets the Gen4 writer's JdlReferenceError through to the caller; the
Case IH writer reads the catalogue's per-task files and the Summary's decoded_readings; a saved and moved work keeps
what a writer needs; the AOI positions cache is keyed by the decoder's format, points mode, options and a version;
engine.run.import_as_sms resolves with the source's crop definition as engine/sms_import.py does; the GDAL branch
of yield_clean.write_points patches a column on pandas 3; a GreenStar 3 / Operations Center helper or two.

    python -m pytest -q tests/test_integration_wires.py
"""
from __future__ import annotations

import importlib
import inspect
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine import sms_import as si  # noqa: E402
from engine import works as ew  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from engine.formats import cnh_cn1_write as CW  # noqa: E402
from engine.formats import detect  # noqa: E402
from engine.formats import jd_jdl_write as JW  # noqa: E402
from engine.formats import native_write as NW  # noqa: E402
from tests import synthetic_jdl as SJ  # noqa: E402
from tests.synthetic import make_applied, make_field  # noqa: E402
from tests.synthetic_cn1 import make_card as cn1_card  # noqa: E402
from tests.test_jd_gs3_rcd_write import make_card as gs3_card  # noqa: E402

Q = lambda m: None  # noqa: E731
FORMATS = ("jd_jdl", "jd_gs3_rcd", "cnh_cn1")


def _decode_card(folder, fmt, wd=None, **kw):
    """Make the synthetic card of fmt under folder, open it with engine.run and decode its default units."""
    if fmt == "cnh_cn1":
        root = cn1_card(os.path.join(folder, "input"), **kw)["card"]
    elif fmt == "jd_jdl":
        root = SJ.make_card(folder, **kw)["root"]
    else:
        root = gs3_card(folder)["root"]
    wd = wd or os.path.join(folder, "work")
    cand = [c for c in er.open_input([root], wd, log=Q) if c["kind"] == "raw"][0]
    assert cand["decoder"] == fmt
    return {"cand": cand, "dec": er.decode(cand, None, None, wd, log=Q), "wd": wd, "root": root}


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    return {f: _decode_card(str(tmp_path_factory.mktemp(f)), f) for f in FORMATS}


def _clean_subset(dec, out, every=5):
    """A 'clean' file: the decoded readings without every every-th one."""
    g = pyogrio.read_dataframe(dec["shp"])
    keep = np.ones(len(g), bool)
    keep[::every] = False
    g[keep].to_file(out, engine="pyogrio")
    return int(keep.sum())


# ------------------------------------------------------------------------------------------- run.decode_source
def test_decode_source_carries_what_the_writers_and_the_import_need(sources):
    for fmt, S in sources.items():
        rep, src = S["dec"]["report"], S["dec"]["source"]
        assert src["format"] == fmt and src["kind"] == "decoded"
        assert src["input_root"] == rep["input_root"] and os.path.isdir(src["input_root"])
        assert src["unit_ids"] and src["unit_ids"] == er._unit_ids_of(rep)
        assert src["decode_report"] == S["dec"]["report_json"] and os.path.isfile(src["decode_report"])
        assert src["monitor_product"] == rep.get("monitor_product") and src["crop_name"] == rep.get("crop_name")
        if fmt == "cnh_cn1":
            assert src["sms_summary"] == rep["sms_summary"]["total"] and src["sms_summary"]["wet_lb"] > 0
            assert src["monitor_product"] is None
        else:
            assert src["sms_summary"] is None and src["monitor_product"]["max_yield"] == si.SMS_JD_MAX_YIELD


# ------------------------------------------------------------------------------------------- native_write
def test_native_options_put_the_source_format_first_and_isoxml_last(sources):
    for fmt, S in sources.items():
        o = NW.options(S["dec"]["source"])
        mod = importlib.import_module(f"engine.formats.{fmt}_write")
        assert [x["id"] for x in o] == [fmt, NW.ISOXML]
        assert o[0]["label"] == mod.LABEL and o[0]["native"] and o[0]["available"] and o[0]["reason"] == ""
        assert not o[-1]["native"] and not o[-1]["available"]
        # the writer's own check decides (the input gone: not available, with its reason)
        gone = dict(S["dec"]["source"], input_root=os.path.join(S["wd"], "gone"))
        o2 = NW.options(gone)
        assert o2[0]["id"] == fmt and not o2[0]["available"] and o2[0]["reason"]


WRITER_OPTIONS = {"jd_jdl": {"allow_reference_shift": True, "drop_logs": True, "verify": False},
                  "jd_gs3_rcd": {"id_tag": 7, "folder_name": "card_clean", "check": False},
                  "cnh_cn1": {"mode": "drop", "totals": "scaled", "verify": False, "card_names": {"A": "B"},
                              "registry": "names.json"}}


@pytest.mark.parametrize("fmt", FORMATS)
def test_native_write_forwards_the_writer_options(sources, tmp_path, monkeypatch, fmt):
    mod = importlib.import_module(f"engine.formats.{fmt}_write")
    real = mod.write_clean
    sig = inspect.signature(real)
    kw = WRITER_OPTIONS[fmt]
    assert set(kw) <= set(sig.parameters), f"{fmt}: the writer does not take {set(kw) - set(sig.parameters)}"
    seen = {}

    def recorder(source, clean_shp, out_dir, **k):
        seen.update(k, source=source, clean_shp=clean_shp, out_dir=out_dir)
        return {"path": out_dir, "zip": None, "n_kept": 1, "n_removed": 0, "files_changed": [], "notes": [],
                "warnings": []}
    recorder.__signature__ = sig                           # what native_write reads to pick the writer's options
    monkeypatch.setattr(mod, "write_clean", recorder)
    src = sources[fmt]["dec"]["source"]
    res = NW.write(fmt, src, "clean.shp", str(tmp_path / "out"), widths=False, factors={"M": 1.1}, new_ids=False,
                   log=Q, bogus=1, **kw)
    assert seen["source"] is src and seen["out_dir"] == str(tmp_path / "out")
    assert {k: seen[k] for k in kw} == kw and "bogus" not in seen
    assert seen["widths"] is False and seen["factors"] == {"M": 1.1} and seen["new_ids"] is False
    assert any("bogus" in w for w in res["warnings"])
    assert res["format_id"] == fmt and res["native"] and res["sms_tested"] is False
    assert any("not yet tested in SMS" in n for n in res["notes"])


def test_the_gen4_reference_error_reaches_the_caller_and_the_shift_option_writes(tmp_path):
    """The real Gen4 writer through the dispatcher: removing a log's first widest point raises JdlReferenceError
    with its .logs (the app's 'write anyway' button needs them); allow_reference_shift=True then writes a card whose
    round trip is exact (the case of tests/test_jdl_write.py::test_jdl_writer_reference_across_the_header)."""
    S = _decode_card(str(tmp_path / "jdl"), "jd_jdl", state_times=(0.12, 60.1, 80.1, 83.1),
                     states=([1] * 6, [0] * 6, [1] * 6, [1, 1, 1, 1, 1, 0]))
    dec = S["dec"]
    g = pyogrio.read_dataframe(dec["shp"])
    t0 = SJ.REF_MS + 500
    from engine.formats import jd_jdl as J
    df0 = J.decode_detailed(dec["report"]["input_root"], dec["report"]["units"], None, log=Q)[0]
    drop = set(df0.Time[(df0.t_ms.values > t0 + 79_000) & (df0.t_ms.values < t0 + 84_000)])
    clean = str(tmp_path / "syn_clean.shp")
    g[~g.Time.isin(drop).values].to_file(clean, engine="pyogrio")
    with pytest.raises(JW.JdlReferenceError) as e:
        NW.write("jd_jdl", dec["source"], clean, str(tmp_path / "out"), log=Q)
    assert isinstance(e.value, ValueError) and e.value.logs and "move_m" in e.value.logs[0]
    assert "Write it anyway with allow_reference_shift=True" in str(e.value)    # the phrase the app replaces
    res = NW.write("jd_jdl", dec["source"], clean, str(tmp_path / "out"), log=Q, allow_reference_shift=True)
    assert res["round_trip"]["ok"] and res["n_kept"] == int((~g.Time.isin(drop)).sum())
    assert not any("not options of" in w for w in res["warnings"])


def test_the_cnh_writer_reads_the_catalogue_files_and_decoded_readings(tmp_path):
    """A card written in capitals (every name inside the card folder upper case): the writer finds every task file
    through the catalogue's r['files'] and its check reads the Summary rows by 'decoded_readings'."""
    S = _decode_card(str(tmp_path / "cn1"), "cnh_cn1", upper=True)
    clean = str(tmp_path / "clean.shp")
    n = _clean_subset(S["dec"], clean)
    res = NW.write("cnh_cn1", S["dec"]["source"], clean, str(tmp_path / "out"), log=Q)
    assert res["n_kept"] == n and res["check"]["ok"], res["check"].get("problems")
    rows = res["check"]["summary_datasets"]
    assert rows and all("decoded_readings" in r and "readings" not in r for r in rows)
    assert sum(r["decoded_readings"] for r in rows) == n
    code = inspect.getsource(CW)
    assert 'r["files"]' in code and 'r["base"]' not in code and "r['base']" not in code


# ------------------------------------------------------------------------------------------- works
def test_a_saved_and_moved_work_keeps_what_the_writer_needs(tmp_path):
    """A card unpacked under the work folder's input/, decoded, saved; the workspace moved: the reopened source
    finds its card, decode report and decoded file again, and the native writer is still available."""
    wd = er.new_workdir(str(tmp_path / "ws"), "syn")
    S = _decode_card(wd, "cnh_cn1", wd=wd)
    d = S["dec"]
    D = {"tag": d["tag"], "shp": d["shp"], "zip": d["zip"], "n": d["n"], "kind": "raw", "op": "harvest",
         "yield": True, "label": d["tag"], "report": d["report"], "source": d["source"]}
    ew.save_work(wd, ew.make_record(wd, "Synthetic", datasets={d["tag"]: D}))
    moved = str(tmp_path / "other" / os.path.basename(wd))
    shutil.move(wd, moved)
    back = ew.load_work(moved)["datasets"][d["tag"]]["source"]
    assert os.path.normcase(back["input_root"]).startswith(os.path.normcase(moved)) and os.path.isdir(back["input_root"])
    assert os.path.isfile(back["decode_report"]) and os.path.isfile(back["decoded_shp"])
    assert back["unit_ids"] == d["source"]["unit_ids"] and back["sms_summary"] == d["source"]["sms_summary"]
    o = NW.options(back)
    assert o[0]["id"] == "cnh_cn1" and o[0]["available"], o[0]["reason"]


def test_an_older_sms_cleaning_is_marked_clean_again():
    R = {"sms3sigma": {"settings": {"k_sd": 3}, "steps": []}}
    assert "clean it again" in ew.clean_again_reason(R)
    R["sms3sigma"]["method_revision"] = 2
    assert ew.clean_again_reason(R) is None


# ------------------------------------------------------------------------------------------- AOI cache
def test_the_aoi_cache_key_follows_format_points_options_and_version(sources, monkeypatch):
    S = sources["jd_jdl"]
    cand, uid = S["cand"], S["dec"]["source"]["unit_ids"][0]
    opts = detect.default_options("jd_jdl")
    k = er.aoi_cache_key(cand, uid, opts)
    assert k == er.aoi_cache_key(cand, uid, opts, {"points": "sms"})          # the default named or not: one key
    assert k != er.aoi_cache_key(cand, uid, opts, {"points": "ops_center"})
    assert er.decoder_call_kwargs("jd_jdl")["points"] == "sms"
    assert er.decoder_call_kwargs("cnh_cn1", {"time_basis": "period"})["time_basis"] == "period"
    monkeypatch.setattr(er, "AOI_CACHE_VERSION", er.AOI_CACHE_VERSION + 1)
    assert k != er.aoi_cache_key(cand, uid, opts)
    monkeypatch.undo()
    other = dict(cand, decoder="cnh_cn1")
    assert k != er.aoi_cache_key(other, uid, opts)


def test_the_aoi_positions_are_decoded_with_the_decoder_options(sources, tmp_path):
    """points 'sms' and 'ops_center' give the Gen4 unit other readings: each gets its own cache file, and a second
    call reads the cache (the decoder is not called again)."""
    S = sources["jd_jdl"]
    cand, uid = S["cand"], S["dec"]["source"]["unit_ids"][0]
    wd = str(tmp_path / "aoi")
    a = er._unit_readings(cand, uid, None, wd)
    b = er._unit_readings(cand, uid, None, wd, decoder_kwargs={"points": "ops_center"})
    assert len(a[0]) == S["dec"]["n"] and len(b[0]) != len(a[0])
    assert len(os.listdir(os.path.join(wd, "decoded", "aoi_cache"))) == 2
    mod = detect.decoder("jd_jdl")
    calls = []
    real = mod.decode

    def counting(*x, **k):
        calls.append(k)
        return real(*x, **k)
    counting.__signature__ = inspect.signature(real)       # the key reads the decoder's keyword defaults
    try:
        mod.decode = counting
        a2 = er._unit_readings(cand, uid, None, wd)
    finally:
        mod.decode = real
    assert not calls and np.array_equal(a2[0], a[0])


# ------------------------------------------------------------------------------------------- import as SMS
def test_import_as_sms_resolves_with_the_source_crop_definition(tmp_path):
    """engine.run.import_as_sms with a John Deere monitor_product: max 10,000 and the file's weight and moisture,
    recorded with where each came from; the same file as a Case IH card's product: SMS's product table."""
    F = make_field(str(tmp_path / "field"))
    mon = {"crop": "wheat", "test_weight_lb_bu": 60.0098, "dry_moisture_pct": 13.0, "min_yield": 5.0,
           "max_yield": 10_000.0, "source": "synthetic file"}
    _, n_jd, rec = er.import_as_sms(F["shp"], "jd", str(tmp_path / "d1"), {}, crop="wheat", log=Q, monitor=mon,
                                    fmt="jd_gs3_rcd")
    assert rec["resolved"]["max_yield"] == si.SMS_JD_MAX_YIELD and rec["resolved"]["test_weight_lb_bu"] == 60.0098
    assert rec["sources"]["max_yield"] == si.SRC_JD and rec["sources"]["dry_moisture_pct"] == si.SRC_FILE
    assert rec["family"] == "john_deere" and rec["fmt"] == "jd_gs3_rcd" and rec["monitor"] == mon
    assert "left_out_by_group" in rec and "applied" in rec and "SMS for John Deere files" in rec["sources_text"]
    _, n_cnh, rec2 = er.import_as_sms(F["shp"], "cnh", str(tmp_path / "d2"), {}, crop="Wheat - Spring", log=Q,
                                      fmt="cnh_cn1")
    assert rec2["resolved"]["max_yield"] == 300.0 and rec2["sms_product"] == "Wheat - Spring"
    assert rec2["sources"]["max_yield"] == si.SRC_TABLE and n_cnh <= n_jd
    # the decoder of a John Deere file keeps the file's crop definition (nothing typed: no weight forced on it)
    o, _ = er.decoder_options_for_import(detect.default_options("jd_jdl"), {}, "wheat", fmt="jd_jdl")
    assert o.test_weight_lb_bu is None and o.std_moisture_pct is None and o.shrink == "one_sided"
    o, _ = er.decoder_options_for_import(detect.default_options("cnh_cn1"), {}, "wheat", fmt="cnh_cn1")
    assert o.test_weight_lb_bu == 60.0 and o.std_moisture_pct == 13.5
    assert er.import_format(None, {"kind": "export", "monitor_product": mon}) == "jd_ops_center"
    assert er.import_format(None, {"kind": "export"}) is None and er.import_format({"format": "jd_jdl"}) == "jd_jdl"


def test_import_max_is_reported_next_to_s5a():
    imp = {"resolved": {"max_yield": 200.0}, "sources": {"max_yield": "you"},
           "left_out": {yc.IMPORT_MAX_STEP: 7}, "left_out_by_group": {yc.IMPORT_MAX_STEP: {"A": 5, "B": 2}}}
    steps = [{"group": "A", "step": "S5a", "hi": 215.4}, {"group": "B", "step": "S5a", "hi": 180.0},
             {"group": "A", "step": "S4", "hi": 6.0}]
    X, w = yc.import_max_check(imp, steps, {"A": 2, "B": 1}, "machine")
    assert [(g["group"], g["left_out"], g["max_below_s5a_hi"], g["one_pass_after_left_out"]) for g in X["groups"]] == [
        ("A", 5, True, False), ("B", 2, False, True)]
    assert len(w) == 2 and "below the S5a upper limit 215.40" in w[0] and "ran one pass" in w[1]
    imp["sources"]["max_yield"] = si.SRC_TABLE                        # SMS's own value: reported, not warned
    X, w = yc.import_max_check(imp, steps, {"A": 2, "B": 1}, "machine")
    assert not w and X["groups"][0]["max_below_s5a_hi"]
    from engine.report.clean_report import _import_max_text
    t = _import_max_text(X)
    assert "Import maximum: 200.00 bu/ac" in t and "A 5" in t and "below its S5a upper limit 215.40" in t
    assert yc.import_max_check(None, steps, {}, "machine") == (None, [])


# ------------------------------------------------------------------------------------------- the rest
def test_write_points_patches_a_column_through_gdal(tmp_path):
    """The GDAL branch of yield_clean.write_points (used when a byte copy is not possible) rewrites patched cells:
    on pandas 3 the column's array is read-only, so it must be copied first."""
    import geopandas as gpd
    g0 = gpd.GeoDataFrame({"Yld_Vol_Dr": [10.0, 20.0, 30.0, 40.0], "Name": list("abcd")},
                          geometry=gpd.points_from_xy([-114.0, -114.0001, -114.0002, -114.0003], [51.0] * 4),
                          crs="EPSG:4326")
    src = str(tmp_path / "src.shp")
    g0.to_file(src, engine="pyogrio")
    out = str(tmp_path / "out.shp")
    mask = np.array([False, True, False, True])
    how = yc.write_points(out, src, g0, np.array([0, 1, 2, 3]), [], byte_copy=None,
                          patch={"Yld_Vol_Dr": (np.array([0.0, 21.5, 0.0, 41.5]), mask)})
    back = pyogrio.read_dataframe(out, read_geometry=False)
    assert how == "geopandas" and back["Yld_Vol_Dr"].tolist() == [10.0, 21.5, 30.0, 41.5]
    assert back["Name"].tolist() == list("abcd")


def test_a_case_ih_cards_readings_and_summary_are_compared():
    src = {"format": "cnh_cn1", "totals": {"wet_lb": 1050.0, "area_ac": 3.1}, "decoder_kwargs": {},
           "sms_summary": {"wet_lb": 1000.0, "area_ac": 3.0}}
    cs = yc.card_summary_gap(src)
    assert cs["ratio"] == pytest.approx(1.05) and cs["time_basis"] == "sms"
    assert yc.card_summary_gap(dict(src, format="jd_jdl")) is None
    assert yc.card_summary_gap(dict(src, sms_summary=None)) is None


def test_operations_center_machine_serials(tmp_path):
    meta = {"MachineUsage": {"1": {"MachineSerial": "SYNTHVIN000000001"}, "2": {"MachineSerial": ""},
                             "3": {"MachineSerial": "SYNTHVIN000000003"}}}
    assert detect.machine_serials(meta) == {"1": "SYNTHVIN000000001", "3": "SYNTHVIN000000003"}
    assert detect.machine_serials({"MachineUsage": [{"MachineSerial": "SYNTHVIN000000009"}]}) == {
        "1": "SYNTHVIN000000009"}
    assert detect.machine_serials({}) == {} and detect.machine_serials(None) == {}
    # an export with its metadata: the candidate carries the serials and the crop definition
    F = make_field(str(tmp_path / "f"))
    stem = os.path.splitext(F["shp"])[0]
    json.dump({"CropName": "Wheat (Hard Red Spring)", "CropId": 25, **meta},
              open(stem + "-Deere-Metadata.json", "w", encoding="utf-8"))
    cand = er.open_input([F["shp"]], str(tmp_path / "w"), log=Q)[0]
    assert cand["machine_serials"] == {"1": "SYNTHVIN000000001", "3": "SYNTHVIN000000003"}
    assert cand["monitor_product"] and er.import_format(None, cand) == "jd_ops_center"


def test_new_workdir_keeps_a_short_tag(tmp_path):
    wd = er.new_workdir(str(tmp_path), "A very long upload name that would eat the path limit.zip")
    tag = os.path.basename(wd).split("_", 1)[1]
    assert len(tag) <= er.WORKDIR_TAG_CHARS and os.path.isdir(os.path.join(wd, "input"))


def test_step_one_reads_seeding_by_mass_from_the_records(tmp_path):
    """detect.py labels a drill that logs seed by mass from a sample of its records, as applied3s.run does from the
    whole file: a crop as product is seeding, a fertilizer an application."""
    from tests.test_import_applied import _rewrite
    A = make_applied(str(tmp_path / "data"), "seeding", seed=3)

    def by_mass(product):
        def fn(g):
            g = g.rename(columns={"Rt_Apd_Ct_": "Rt_Apd_Ms_", "Rt_Tgt_Ct_": "Rt_Tgt_Ms_"}).copy()
            g["Rt_Apd_Ms_"] = g["Rt_Apd_Ms_"].astype(float) / 250.0
            g["Product"] = product
            return g
        return fn
    for product, op in (("Wheat - Synthetic variety", "seeding"), ("Synthetic 46-0-0", "application")):
        shp = _rewrite(A["shp"], str(tmp_path / op / "m.shp"), by_mass(product))
        cand = er.open_input([shp], str(tmp_path / ("w_" + op)), log=Q)[0]
        assert cand["kind"] == "export" and not cand["yield"] and cand["operation"] == op, (product, cand["label"])
