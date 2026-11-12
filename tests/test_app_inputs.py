# -*- coding: utf-8 -*-
"""The app (app/oced.py) on synthetic data through Streamlit's AppTest: step 1 (open, upload, the datasets found),
the import as SMS of each file (where its values come from, an unknown product, a file of two crops), the files of a
work (two exports with the same file name), the state of a work (a new work, Save, a saved work opened again, a moved
workspace) and the robustness of opening and cleaning (a failed open, a file held open by another program, long
paths). Every number here is made up (tests/synthetic.py).

    python -m pytest -q tests/test_app_inputs.py
"""
from __future__ import annotations

import ast
import glob
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

from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("data")))


def _by_key(items, prefix):
    return next(x for x in items if str(x.key or "").startswith(prefix))


def _app(tmp_path, monkeypatch, ws="ws"):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / ws) if not os.path.isabs(str(ws)) else str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


def _open(at, path):
    at.text_input(key="path_in").input(str(path))
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception


def _metric(at, label):
    return next((m for m in at.metric if m.label == label), None)


def _variant(src, dst, fn=None):
    """A copy of the synthetic export, changed by fn (a GeoDataFrame -> GeoDataFrame)."""
    import geopandas as gpd
    g = gpd.read_file(src)
    if fn is not None:
        g = fn(g)
    os.makedirs(os.path.dirname(str(dst)), exist_ok=True)
    g.to_file(str(dst), engine="pyogrio")
    return str(dst)


def _imported_count(shp, lo=5.0, hi=300.0):
    y = pd.to_numeric(pyogrio.read_dataframe(shp, read_geometry=False)["Yld_Vol_Dr"], errors="coerce").to_numpy(float)
    return int((np.isfinite(y) & (y >= lo) & (y <= hi)).sum())


def _app_function(name, **ns):
    """One function of app/oced.py with the globals it needs, without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module([fn], []), APP, "exec"), ns)
    return ns[name]


# ------------------------------------------------------------------------------------------------ the files of a work
def test_app_same_name_exports_are_separate_files(field, tmp_path, monkeypatch):
    """Three exports with the same file name in three folders (one per combine, one in lower case): the list names
    their folders, each choice opens its own file under its own tag, and choosing one again shows it."""
    root = tmp_path / "in"
    a = _variant(field["shp"], root / "Combine_1" / "Harvest.shp")
    b = _variant(field["shp"], root / "Combine_2" / "Harvest.shp", lambda g: g.iloc[::3].assign(Machine="COMBINE-B"))
    c = _variant(field["shp"], root / "Combine_3" / "harvest.shp", lambda g: g.iloc[::2].assign(Machine="COMBINE-C"))
    at = _app(tmp_path, monkeypatch)
    _open(at, root)
    sb = at.selectbox(key="cand_idx")
    labels = list(sb.options)
    assert len(labels) == 3 and all(any(f"Combine_{i}" in x for x in labels) for i in (1, 2, 3))
    want = {}
    for i, lab in enumerate(labels):
        src = a if "Combine_1" in lab else b if "Combine_2" in lab else c
        want[i] = _imported_count(src)
    for i in (0, 1, 2):
        at.selectbox(key="cand_idx").select_index(i).run()
        assert not at.exception, at.exception
        assert _metric(at, "Readings").value == f"{want[i]:,}"
    tags = list(at.session_state["datasets"])
    assert len(tags) == 3 and len({t.casefold() for t in tags}) == 3
    assert len({at.session_state["datasets"][t]["shp"].casefold() for t in tags}) == 3   # three imported files
    at.selectbox(key="cand_idx").select_index(0).run()                # an opened one chosen again: it is shown
    assert _metric(at, "Readings").value == f"{want[0]:,}"
    assert at.selectbox(key="active_pick").value == at.session_state["active"]


def test_app_two_uploads_with_one_name_are_refused(field, tmp_path, monkeypatch):
    """Two uploaded shapefile sets with the same names would overwrite each other: refused with a plain message, and
    nothing is left in the workspace."""
    at = _app(tmp_path, monkeypatch)
    base = os.path.splitext(field["shp"])[0]
    files = [(os.path.basename(base) + e, open(base + e, "rb").read(), "application/octet-stream")
             for e in (".shp", ".shx", ".dbf", ".prj")]
    _by_key(at.get("file_uploader"), "uploads_").set_value(files + files).run()
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert any("two uploaded files are named" in e.value for e in at.error)
    assert not os.path.isdir(tmp_path / "ws") or not os.listdir(tmp_path / "ws")


# ------------------------------------------------------------------------------------------------ import as SMS
def test_app_import_panel_unknown_and_known_product(field, tmp_path, monkeypatch):
    """A file whose product is not a crop (a variety, no Crop column): the panel leaves the weight to volume and the
    dry moisture empty instead of wheat's, claims no difference, and importing it again untouched changes nothing.
    A recognised product: no 'differ' caption right after opening, and each value says where it came from."""
    v = _variant(field["shp"], tmp_path / "in" / "Variety.shp", lambda g: g.assign(Product="Variety X"))
    at = _app(tmp_path, monkeypatch)
    _open(at, v)
    assert _by_key(at.number_input, "fi_tw_").value is None and _by_key(at.number_input, "fi_dm_").value is None
    assert any("Product not recognised" in c.value for c in at.caption)
    assert not any("These values differ" in c.value for c in at.caption)
    n0, y0 = _metric(at, "Readings").value, _metric(at, "Mean dry yield").value
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert any("imported again" in s.value for s in at.success)
    assert _metric(at, "Readings").value == n0 and _metric(at, "Mean dry yield").value == y0
    # a recognised product (Wheat): its values from SMS's product table, nothing flagged
    _open(at, field["shp"])
    assert float(_by_key(at.number_input, "fi_tw_").value) == pytest.approx(60.0)
    assert float(_by_key(at.number_input, "fi_dm_").value) == pytest.approx(13.5)
    assert not any("These values differ" in c.value for c in at.caption)
    assert any("Where the values came from" in c.value and "SMS product table" in c.value for c in at.caption)
    assert "SMS product table" in _metric(at, "Readings").help


def test_app_import_panel_follows_a_new_import(field, tmp_path, monkeypatch):
    """The same export opened again after another maximum in step 1: the panel shows the values of the new import,
    not the previous one's (its widgets are keyed by the import)."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    assert float(_by_key(at.number_input, "fi_max_").value) == pytest.approx(300.0)
    at.number_input(key="si_max").set_value(150.0).run()
    _open(at, field["shp"])
    assert float(_by_key(at.number_input, "fi_max_").value) == pytest.approx(150.0)
    assert "150.00 bu/ac" in _metric(at, "Readings").help and "(you)" in _metric(at, "Readings").help


def test_app_two_crops_in_one_export(field, tmp_path, monkeypatch):
    """An export whose Product column names two crops: nothing is converted with one crop's settings, and the page
    says why (the whole column is read, not its first records)."""
    def two(g):
        g = g.copy()
        g.loc[g.index[:300], "Product"] = "Barley"
        return g
    v = _variant(field["shp"], tmp_path / "in" / "Two_crops.shp", two)
    at = _app(tmp_path, monkeypatch)
    _open(at, v)
    assert any("more than one crop" in w.value and "barley (300 readings)" in w.value for w in at.warning)
    assert "recomputed" not in _metric(at, "Readings").help
    assert _by_key(at.number_input, "fi_tw_").value is None


def test_app_area_card_is_the_file_on_screen(field, tmp_path, monkeypatch):
    """'Area harvested' is distance x width of the readings imported (a point export shows it too), and it follows
    'Import this file again'."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])

    def area_now():
        shp = at.session_state["datasets"][at.session_state["active"]]["shp"]
        d = pyogrio.read_dataframe(shp, read_geometry=False)
        return float((d["Distance_f"].astype(float) * d["Swth_Wdth_"].astype(float)).sum() / 43560.0)
    a1 = area_now()
    assert _metric(at, "Area harvested").value == f"{a1:,.2f} ac"
    _by_key(at.number_input, "fi_min_").set_value(60.0).run()
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    a2 = area_now()
    assert a2 < a1 and _metric(at, "Area harvested").value == f"{a2:,.2f} ac"


# ------------------------------------------------------------------------------------------------ opening
def test_app_failed_open_keeps_the_work(field, tmp_path, monkeypatch):
    """A path that does not exist, or an input with nothing usable in it, leaves the work on screen as it is and no
    new folder; 'nothing usable' says why. An input left before anything was made of it is removed when another one
    is opened."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    ws = tmp_path / "ws"
    n_dirs = len(os.listdir(ws))
    readings = _metric(at, "Readings").value
    _open(at, tmp_path / "does_not_exist")
    assert any("not found on this computer" in e.value for e in at.error)
    assert _metric(at, "Readings").value == readings and len(os.listdir(ws)) == n_dirs
    empty = tmp_path / "empty"
    empty.mkdir()
    _open(at, empty)
    assert any("Nothing usable" in e.value and "Why:" in e.value for e in at.error)
    assert _metric(at, "Readings").value == readings and len(os.listdir(ws)) == n_dirs
    arch = tmp_path / "data.7z"
    arch.write_bytes(b"7z" + b"\0" * 64)
    _open(at, arch)
    assert any("this archive type is not unpacked" in e.value for e in at.error)
    # an input that asks for a choice, left without one, then another input: its folder goes
    root = tmp_path / "two"
    _variant(field["shp"], root / "A" / "One.shp")
    _variant(field["shp"], root / "B" / "Two.shp", lambda g: g.iloc[::2])
    _open(at, root)
    assert at.selectbox(key="cand_idx").value is None
    left = at.session_state["workdir"]
    _open(at, field["shp"])
    assert not os.path.exists(left)


def test_app_upload_then_path_opens_the_path(field, tmp_path, monkeypatch):
    """After an upload is opened its field is emptied, so a path typed next is opened (not the upload again); both
    filled at once are refused instead of one being chosen silently."""
    at = _app(tmp_path, monkeypatch)
    base = os.path.splitext(field["shp"])[0]
    files = [(os.path.basename(base) + e, open(base + e, "rb").read(), "application/octet-stream")
             for e in (".shp", ".shx", ".dbf", ".prj")]
    up = _by_key(at.get("file_uploader"), "uploads_")
    up.set_value(files).run()
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert _metric(at, "Readings") is not None
    up2 = _by_key(at.get("file_uploader"), "uploads_")
    assert up2.key != up.key and not up2.value
    other = _variant(field["shp"], tmp_path / "in" / "Other.shp", lambda g: g.iloc[::2])
    _open(at, other)
    assert at.session_state["input_label"] == other
    # both an upload and a new path: refused
    _by_key(at.get("file_uploader"), "uploads_").set_value(files).run()
    at.text_input(key="path_in").input(field["shp"])
    at.button(key="open_btn").click().run()
    assert at.session_state["input_label"] == other


def test_app_new_work_does_not_inherit_the_widgets(field, tmp_path, monkeypatch):
    """Open, then Open another field whose export has the same file name, without Start over: the grower's weight
    typed for the first one is not the second one's."""
    a = _variant(field["shp"], tmp_path / "A" / "Harvest.shp")
    b = _variant(field["shp"], tmp_path / "B" / "Harvest.shp", lambda g: g.iloc[::2])
    at = _app(tmp_path, monkeypatch)
    _open(at, a)
    _by_key(at.number_input, "gw_w_").set_value(123_456.0).run()
    assert at.session_state["grower"][at.session_state["active"]]["weight"] == 123_456.0
    _open(at, b)
    assert _by_key(at.number_input, "gw_w_").value is None
    assert not (at.session_state["grower"].get(at.session_state["active"]) or {}).get("weight")


def test_app_save_keeps_the_value_typed_just_before(field, tmp_path, monkeypatch):
    """Save clicked in the same run as a value typed: the saved work holds the value."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    _by_key(at.number_input, "gw_w_").set_value(98_765.0)
    at.number_input(key="k_sd").set_value(2.5)
    at.button(key="work_save").click().run()
    assert not at.exception, at.exception
    rec = json.load(open(glob.glob(str(tmp_path / "ws" / "*" / "oced_work.json"))[0], encoding="utf-8"))
    assert next(iter(rec["grower"].values()))["weight"] == 98_765.0 and rec["smsset"]["k_sd"] == 2.5


def test_app_moved_workspace_imports_again(field, tmp_path, monkeypatch):
    """An uploaded export, saved; the workspace moved; the work opened again: 'Import this file again' finds the
    readings in the moved folder."""
    at = _app(tmp_path, monkeypatch, ws="ws1")
    base = os.path.splitext(field["shp"])[0]
    files = [(os.path.basename(base) + e, open(base + e, "rb").read(), "application/octet-stream")
             for e in (".shp", ".shx", ".dbf", ".prj")]
    _by_key(at.get("file_uploader"), "uploads_").set_value(files).run()
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    assert glob.glob(str(tmp_path / "ws1" / "*" / "oced_work.json"))      # saved when it was opened
    shutil.move(str(tmp_path / "ws1"), str(tmp_path / "ws2"))
    at2 = _app(tmp_path, monkeypatch, ws="ws2")
    at2.button(key="work_open").click().run()
    assert not at2.exception, at2.exception
    _by_key(at2.number_input, "fi_min_").set_value(20.0).run()
    _by_key(at2.button, "fi_go_").click().run()
    assert not at2.exception, at2.exception
    assert any("imported again" in s.value for s in at2.success)
    assert at2.session_state["datasets"][at2.session_state["active"]]["shp"].startswith(str(tmp_path / "ws2"))


# ------------------------------------------------------------------------------------------------ cleaning a work
def test_app_import_minimum_long_paths_saved_work_and_superseded_files(field, tmp_path, monkeypatch):
    """One file through the whole work, uploaded as a zip with a 64-character name into a workspace 130 characters
    deep: imported with min 0 (S0 then keeps those readings), cleaned (the record carries the import, every path within
    the Windows limit), another k saved and the work opened again (flagged 'clean again'), then imported again (the
    previous clean files move to superseded/)."""
    import zipfile
    pad = 130 - len(str(tmp_path)) - len(os.sep + "OCED_workspace") - 1
    if pad < 4:
        pytest.skip("the temporary folder is already too deep for this test")
    deep = tmp_path / ("d" * pad) / "OCED_workspace"
    long_name = "Synthetic_export_with_a_long_name_for_the_path_limit_1234567890"
    assert len(long_name) == 63
    shp = _variant(field["shp"], tmp_path / "in" / f"{long_name}.shp")
    zp = tmp_path / f"{long_name}.zip"
    with zipfile.ZipFile(zp, "w") as z:
        for e in (".shp", ".shx", ".dbf", ".prj"):
            z.write(shp[:-4] + e, long_name + e)
    at = _app(tmp_path, monkeypatch, ws=str(deep))
    _by_key(at.get("file_uploader"), "uploads_").set_value([(zp.name, zp.read_bytes(), "application/zip")]).run()
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    tag = at.session_state["active"]
    assert tag and len(tag) <= 60
    assert not glob.glob(str(deep / "*" / "uploads" / "*.zip"))          # unpacked: the uploaded copy is gone
    _by_key(at.number_input, "fi_min_").set_value(0.0).run()
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    assert any("S0 minimum: none" in c.value for c in at.caption) and at.number_input(key="min_yield").disabled
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    js = glob.glob(str(deep / "*" / "clean" / "*" / "*_cleaning.json"))
    R = json.load(open(js[0], encoding="utf-8"))
    assert R["sms_import"]["n_all"] == field["n"] and R["sms_import"]["all_readings"] == os.path.basename(shp)
    assert R["sms_import"]["resolved"]["min_yield"] == 0.0
    s0 = next(r for r in R["cascade"] if str(r["filter"]).startswith("S0"))
    assert int(s0["removed"]) == 0
    longest = max(len(os.path.join(dp, f)) for dp, _, fn in os.walk(str(deep)) for f in fn)
    assert longest <= 250
    # another k, saved; Start over; the saved work opened again: flagged
    at.number_input(key="k_sd").set_value(2.5)
    at.button(key="work_save").click().run()
    at.button(key="start_over").click().run()
    at.button(key="work_open").click().run()
    assert not at.exception, at.exception
    assert any("changed since this file was cleaned" in w.value for w in at.warning)
    # imported again: the cleaning is dropped and its files leave clean_shapefiles/
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    wd = at.session_state["workdir"]
    assert not glob.glob(os.path.join(wd, "clean_shapefiles", f"{tag}_sms3s_clean.*"))
    assert glob.glob(os.path.join(wd, "superseded", "*", "p", f"{tag}_sms3s_clean.shp"))
    assert glob.glob(os.path.join(wd, "superseded", "*", f"{tag}_sms3s_cleaning.json"))
    assert not os.path.isdir(os.path.join(wd, "clean", tag)) or not glob.glob(os.path.join(wd, "clean", tag, "*.json"))
    longest = max(len(os.path.join(dp, f)) for dp, _, fn in os.walk(str(deep)) for f in fn)
    assert longest <= 259


@pytest.mark.skipif(os.name != "nt", reason="file locks are a Windows behaviour")
def test_app_clean_again_with_the_clean_file_open(field, tmp_path, monkeypatch):
    """The published clean .dbf held open by another program: cleaning again says which file to close, raises
    nothing, and leaves the previous clean file as it was."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    shp = glob.glob(str(tmp_path / "ws" / "*" / "clean_shapefiles" / "*_sms3s_clean.shp"))[0]
    before = os.path.getmtime(shp)
    with open(shp[:-4] + ".dbf", "rb"):
        at.number_input(key="k_sd").set_value(2.5).run()
        at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert any("is open in another program" in e.value for e in at.error)
    assert os.path.getmtime(shp) == before
    assert not glob.glob(str(tmp_path / "ws" / "*" / "clean" / "*" / ".oced_cleaning.lock"))


# ------------------------------------------------------------------------------------------------ helpers of the page
def test_width_audit_takes_the_header_not_the_overlap_trim():
    """A monitor that trims the width by the overlap logs most readings 0.5 ft narrower than the header: the header
    is the widest width a material share logged, and the shares add up to 100 %."""
    from engine.clean import sms3sigma as sms
    from engine.clean import yield_clean as yc
    wa = _app_function("width_audit", pd=pd, np=np, yc=yc, sms=sms, HEADER_SHARE=0.05)
    w = np.r_[np.full(600, 44.5), np.full(250, 45.0), np.full(100, 30.0), np.full(40, 44.0), np.full(10, 45.5)]
    df = pd.DataFrame({"Swth_Wdth_": w, "Machine": "COMBINE-A", "Yld_Vol_Dr": 60.0})
    r = wa(df)[0]
    assert r["logged width (ft)"] == 45.0
    assert r["readings at it (%)"] == pytest.approx(25.0) and r["wider (%)"] == pytest.approx(1.0)
    assert r["within 1 ft below (%)"] == pytest.approx(64.0) and r["narrower (%)"] == pytest.approx(10.0)


def test_sms_summary_follows_the_import_settings():
    """The SMS Summary of a card: its dry volume and yield from the file's import settings (wet weight / weight to
    volume x the one-sided shrink at the dataset's moisture); without an import only area, wet weight, moisture."""
    from engine import sms_import as si
    from engine.formats import common
    view = _app_function("sms_summary_view", pd=pd, common=common, si=si)
    rep = {"sms_summary": {"total": {"area_ac": 10.0, "wet_lb": 6000.0, "moisture_pct": 15.0, "dry_bu": 1.0},
                           "datasets": [{"unit": "u1", "area_ac": 10.0, "wet_lb": 6000.0, "moisture_pct": 15.0,
                                         "dry_bu": 1.0, "bu_ac": 0.1, "decoded_readings": 40}]}}
    imp = {"resolved": {"test_weight_lb_bu": 60.0, "dry_moisture_pct": 13.5, "expand_dry_moisture": False}}
    T, D, how = view(rep, imp)
    assert T["dry_bu"] == pytest.approx(6000 / 60 * (85 / 86.5)) and "13.50 %" in how
    imp["resolved"]["dry_moisture_pct"] = 16.0                 # drier than the standard: one-sided, no credit
    T2, _, _ = view(rep, imp)
    assert T2["dry_bu"] == pytest.approx(100.0) and T2["bu_ac"] == pytest.approx(10.0)
    T3, D3, how3 = view(rep, None)
    assert "dry_bu" not in T3 and "dry_bu" not in D3.columns and "not imported" in how3


def test_app_card_summary_and_totals_only_option(tmp_path, monkeypatch):
    """A synthetic Case IH card with a task whose log is not on it: the option to add its totals to the SMS Summary
    is offered, and the Summary's dry volume follows 'Import this file again' with another dry moisture."""
    from tests.test_dec_cnh import _card, _crop_table, _logged, _totals_only
    root = _card(tmp_path / "card", {"TASK0001": _logged(n=40), "TASK0002": _totals_only()})
    _crop_table(root)
    at = _app(tmp_path, monkeypatch)
    _open(at, root)
    assert any("whose log is not on the card" in c.label for c in at.checkbox)
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception

    def summary():
        return next(c.value for c in at.caption if c.value.startswith("SMS Summary of these datasets"))
    s1 = summary()
    assert "bu dry" in s1 and "the import settings of this file" in s1
    dm = _by_key(at.number_input, "fi_dm_")
    dm.set_value(float(dm.value) + 3.0).run()
    _by_key(at.button, "fi_go_").click().run()
    assert not at.exception, at.exception
    s2 = summary()
    assert s2 != s1 and "bu dry" in s2


def test_app_gen4_points_option_reaches_the_decoder(tmp_path, monkeypatch):
    """A synthetic Gen4 card: the decoding option 'Points' (as SMS Advanced / as Operations Center) reaches the
    decoder and the decode report says which points the file holds; the import takes SMS's values for John Deere
    files (min 5, max 10,000)."""
    from tests import synthetic_jdl as S
    card = S.make_card(str(tmp_path / "card"))["root"]
    at = _app(tmp_path, monkeypatch)
    _open(at, card)
    _by_key(at.button_group, "pts_").set_value("ops_center").run()
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    D = at.session_state["datasets"][at.session_state["active"]]
    assert D["report"]["points"] == "ops_center" and D["report"]["decoder_kwargs"]["points"] == "ops_center"
    assert any(c.value.startswith("Points: one per flow sample") for c in at.caption)
    R = D["sms_import"]["resolved"]
    assert R["min_yield"] == 5.0 and R["max_yield"] == 10_000.0
    assert D["sms_import"]["sources"]["max_yield"] == "SMS for John Deere files"


def test_app_boundary_replaced_by_another_file_with_the_same_name(field, tmp_path, monkeypatch):
    """A cleaning with an uploaded boundary; the boundary removed and another file with the same name uploaded (it
    lands at the same path): the cleaning is flagged 'clean again' (the boundary is known by what it holds)."""
    import geopandas as gpd
    b2 = tmp_path / "b2" / "Field.geojson"
    os.makedirs(b2.parent)
    g = gpd.read_file(field["boundary"])
    g.set_geometry(g.geometry.scale(0.9, 0.9)).to_file(str(b2), driver="GeoJSON")      # a smaller field
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    _by_key(at.get("file_uploader"), "bnd_up_").set_value(
        [("Field.geojson", open(field["boundary"], "rb").read(), "application/geo+json")]).run()
    _by_key(at.button, "bnd_use_").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception, at.exception
    assert not any("changed since this file was cleaned" in w.value for w in at.warning)
    _by_key(at.button, "bnd_rm_").click().run()
    _by_key(at.get("file_uploader"), "bnd_up_").set_value([("Field.geojson", b2.read_bytes(),
                                                            "application/geo+json")]).run()
    _by_key(at.button, "bnd_use_").click().run()
    assert not at.exception, at.exception
    assert any("changed since this file was cleaned" in w.value for w in at.warning)


def test_app_workspace_disk_use_and_clean_up(field, tmp_path, monkeypatch):
    """The sidebar measures the workspace on request, removes the folders nothing lists (after a confirmation), and
    deletes a saved work other than the one on screen (after a confirmation)."""
    ws = tmp_path / "ws"
    left = ws / "20260101-000000_left"
    os.makedirs(left / "input")
    (left / "input" / "some.bin").write_bytes(b"x" * 1000)
    old = 1_700_000_000
    os.utime(left, (old, old))
    a = _variant(field["shp"], tmp_path / "A" / "First.shp")
    b = _variant(field["shp"], tmp_path / "B" / "Second.shp", lambda g: g.iloc[::2])
    at = _app(tmp_path, monkeypatch)
    _open(at, a)
    first = at.session_state["workdir"]
    _open(at, b)
    at.button(key="ws_measure").click().run()
    assert any("1 without a saved work" in c.value for c in at.caption)
    at.checkbox(key="ws_rm_ok").check().run()
    at.button(key="ws_rm").click().run()
    assert not at.exception, at.exception
    assert not os.path.exists(left) and os.path.exists(first)
    at.selectbox(key="work_pick").set_value(first).run()
    _by_key(at.checkbox, "ws_del_ok_").check().run()
    at.button(key="ws_del").click().run()
    assert not at.exception, at.exception
    assert not os.path.exists(first) and os.path.exists(at.session_state["workdir"])


def test_app_gs3_card_takes_the_card_product_and_the_alignment_option(tmp_path, monkeypatch):
    """A synthetic GreenStar 3 card: the import takes the card's own crop definition (60.01 lb/bu, 13.0 %) and SMS's
    5 to 10,000 bu/ac for John Deere files, says so per value, and the decoding option 'Grain and moisture of a
    reading' reaches the decoder (extracting again with the other choice replaces the file)."""
    from tests.test_jd_gs3_rcd import make_card
    card = make_card(str(tmp_path / "card"))["root"]
    at = _app(tmp_path, monkeypatch)
    _open(at, card)
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    D = at.session_state["datasets"][at.session_state["active"]]
    R, S = D["sms_import"]["resolved"], D["sms_import"]["sources"]
    assert R["test_weight_lb_bu"] == pytest.approx(60.0098, abs=1e-4) and R["dry_moisture_pct"] == 13.0
    assert (R["min_yield"], R["max_yield"]) == (5.0, 10_000.0)
    assert S["test_weight_lb_bu"] == "file" and S["max_yield"] == "SMS for John Deere files"
    assert "60.01 lb/bu (from the file)" in _metric(at, "Readings").help
    assert D["report"]["alignment"]["method"] == "sms"
    _by_key(at.button_group, "al_").set_value("shift").run()
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    assert len(at.session_state["datasets"]) == 1
    D = at.session_state["datasets"][at.session_state["active"]]
    assert D["report"]["alignment"]["method"] == "shift" and D["report"]["decoder_kwargs"]["alignment"] == "shift"


def test_work_folder_names_say_what_was_opened(tmp_path):
    """The name part of a new work folder: the first zip / shapefile / KML of an upload, never a log called by its
    GUID; a raw log file given by path gives a neutral name; at most 20 characters."""
    import re
    from types import SimpleNamespace as F
    fn = _app_function("_work_folder_name", os=os, _GUID=re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
                                                                     r"[0-9a-f]{12}$", re.I),
                       RAW_FILE_EXTS=(".jdl", ".fdd", ".fdl"), WORK_FOLDER_CHARS=20)
    guid = "0a1b2c3d-0000-4000-8000-000000000001"
    assert fn("upload", [F(name=f"{guid}.jdl"), F(name="version.txt")]) == "upload"
    assert fn("upload", [F(name=f"{guid}.jdl"), F(name="Synthetic_combine_data.zip")]) == "Synthetic_combine_da"
    log = tmp_path / f"{guid}.jdl"
    log.write_bytes(b"x")
    assert fn("path", str(log)) == "data"
    assert fn("path", str(tmp_path / "Synthetic harvest")) == "Synthetic harvest"


def test_app_file_gone_from_disk(field, tmp_path, monkeypatch):
    """The points of the file on screen removed from disk: a plain message and a button to take the file out of the
    work, not a traceback."""
    at = _app(tmp_path, monkeypatch)
    _open(at, field["shp"])
    shp = at.session_state["datasets"][at.session_state["active"]]["shp"]
    for e in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        if os.path.exists(shp[:-4] + e):
            os.remove(shp[:-4] + e)
    at.run()
    assert not at.exception, at.exception
    assert any("are no longer at" in e.value for e in at.error)
    _by_key(at.button, "rm_file_").click().run()
    assert not at.exception, at.exception
    assert not at.session_state["datasets"]
