# -*- coding: utf-8 -*-
"""0.4.0: the six steps as tabs across the top (app/oced.py), through Streamlit's AppTest, synthetic data only, the
app as it runs (marker lazy_tabs: only the open tab is drawn, OCED_ALL_STEPS unset). The six tabs in order; only the
open tab's widgets drawn; Next step and Back move; each step that cannot be used yet says what is missing in one line;
the whole path files -> raw map -> cleaning -> clean map -> plots with a plot boundary given in step 1 -> final files;
the
values typed or chosen in a step survive a tab change; and the cleaning and the small area cut write the same bytes
as the engine called directly with the same inputs.

AppTest's tabs are not widgets: they report no open tab back to the app as a browser does, so the driver below puts
the open tab into the session before every run (as the browser's widget state would), and Next / Back change it
through the app's own callback.

    python -m pytest -q tests/test_app_tabs.py
"""
from __future__ import annotations

import glob
import hashlib
import os
import sys
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
NAMES = ["Files", "Raw map", "Cleaning", "Clean map", "Plots", "Final files"]
pytestmark = pytest.mark.lazy_tabs


class Drive:
    """The app with its open tab carried from run to run (a browser reports it; AppTest does not)."""

    def __init__(self, ws, monkeypatch):
        from streamlit.testing.v1 import AppTest
        monkeypatch.setenv("OCED_WORKSPACE", str(ws))
        monkeypatch.delenv("OCED_ALL_STEPS", raising=False)
        self.at = AppTest.from_file(APP, default_timeout=900)
        self.tab = None
        self.run()
        self.labels = [t.label for t in self.at.tabs][:6]

    def run(self):
        if self.tab:
            self.at.session_state["step_tab"] = self.tab
        self.at.run()
        assert not self.at.exception, [str(e.value)[:800] for e in self.at.exception]
        self.tab = self.at.session_state["step_tab"] if "step_tab" in self.at.session_state else None
        return self

    def open(self, n: int):
        self.tab = self.labels[n - 1]
        return self.run()

    def click(self, key: str):
        self.at.button(key=key).click()
        return self.run()

    def keys(self, kind: str = "button") -> list:
        return [str(w.key) for w in getattr(self.at, kind)]

    def key(self, prefix: str, kind: str = "button") -> str:
        return next(k for k in self.keys(kind) if k.startswith(prefix))

    def open_step(self) -> int:
        return self.labels.index(self.tab) + 1 if self.tab in self.labels else 1

    def progress(self) -> str:
        return next(h.proto.body for h in self.at.get("html") if 'class="oced-progress' in h.proto.body)


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


def _poly(shp: str, path) -> str:
    """Two plots inside the synthetic field (a plot boundary of two polygons)."""
    g = gpd.read_file(shp)
    x0, x1, y0, y1 = g.geometry.x.min(), g.geometry.x.max(), g.geometry.y.min(), g.geometry.y.max()
    gpd.GeoDataFrame({"name": ["mid", "low"]},
                     geometry=[box(x0 + (x1 - x0) * 0.3, y0 + (y1 - y0) * 0.3, x0 + (x1 - x0) * 0.6,
                                   y0 + (y1 - y0) * 0.6),
                               box(x0, y0, x0 + (x1 - x0) * 0.2, y0 + (y1 - y0) * 0.2)],
                     crs=4326).to_file(path, driver="GeoJSON")
    return str(path)


def _open(d: Drive, shp: str):
    d.open(1)
    d.at.text_input(key="path_in").input(shp)
    d.click("open_btn")
    assert d.at.session_state["datasets"], "nothing opened"


def test_six_tabs_in_order_only_the_open_one_drawn_and_not_ready_lines(tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    assert [lab.split(" · ", 1)[-1] for lab in d.labels] == NAMES
    assert [lab.split(" · ", 1)[0].split()[-1] for lab in d.labels] == ["1", "2", "3", "4", "5", "6"]
    # step 1 is open first: its open row, no widget of another step, Next and no Back
    assert "path_in" in d.keys("text_input") and "open_btn" in d.keys()
    assert "step_next_1" in d.keys() and "step_back_1" not in d.keys() and "clean_one" not in d.keys()
    assert "0 of 6 steps done" in d.progress()
    want = {2: "No data yet: open the raw data of a field in step 1 (Files).",
            3: "No data yet: open the raw data of a field in step 1 (Files).",
            4: "No data yet: open the raw data of a field in step 1 (Files).",
            5: "No data yet: open the raw data of a field in step 1 (Files).",
            6: "Clean a file in step 3: its clean shapefile appears here."}
    for n in (2, 3, 4, 5, 6):
        d.open(n)
        assert d.open_step() == n
        assert "path_in" not in d.keys("text_input") and "open_btn" not in d.keys()     # step 1 is not drawn
        assert [i.value for i in d.at.info if i.value.startswith(want[n])], (n, [i.value for i in d.at.info])
        assert f"step_back_{n}" in d.keys() and (n == 6) == (f"step_next_{n}" not in d.keys())
        assert not d.at.error


def test_next_step_and_back_move(tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    for n in (1, 2, 3, 4, 5):
        d.click(f"step_next_{n}")
        assert d.open_step() == n + 1 and f"step_back_{n + 1}" in d.keys()
    for n in (6, 5, 4, 3, 2):
        d.click(f"step_back_{n}")
        assert d.open_step() == n - 1
    assert "path_in" in d.keys("text_input")


def test_whole_path_with_a_plot_boundary_given_in_step_1(field, tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    # no plot boundary yet: step 5 (Plots) is not needed, the count is of the other five
    assert "1 of 5 steps done" in d.progress() or "2 of 5 steps done" in d.progress()
    # step 1: the plot boundary of the file (its polygon file and its rule), not measured before the cleaning
    kp = d.key("sa_path_", "text_input")
    d.at.text_input(key=kp).input(poly)
    d.at.selectbox(key="sa_rule_" + kp[len("sa_path_"):]).set_value("clip")
    d.run()
    assert d.at.session_state["plot_area"][tag]["source"][0] == "path"
    assert not (d.at.session_state.filtered_state.get("small_area") or {}).get(tag)
    assert "2 of 6 steps done" in d.progress()                     # a plot boundary given: step 5 is counted
    # step 2: the raw map, its boxes follow the attribute chosen
    d.click("step_next_1")
    assert d.open_step() == 2 and "clean_one" not in d.keys()
    ka = d.key("attr_raw_", "button_group") if any(k.startswith("attr_raw_") for k in d.keys("button_group")) else \
        next(k for k in d.at.session_state.filtered_state if str(k).startswith("attr_raw_"))
    d.at.session_state[ka] = "Moisture__"
    d.run()
    assert [m for m in d.at.metric if m.label == "Mean moisture"]
    # step 3: the cleaning
    d.click("step_next_2")
    assert d.open_step() == 3 and "path_in" not in d.keys("text_input")
    d.click("clean_one")
    C = d.at.session_state["cleaned"][tag]
    assert os.path.exists(C["shp"]) and [m for m in d.at.metric if m.label == "Readings kept"]
    # back to steps 1 and 2: what was typed and chosen there is still there
    d.open(2)
    assert d.at.session_state[ka] == "Moisture__"
    # the raw map is drawn open after the cleaning too (only the open tab is drawn: no reason to fold it), with the
    # attribute chosen before
    assert [w.value for w in d.at.button_group if w.key == ka] == ["Moisture__"]
    d.open(1)
    assert d.at.text_input(key=kp).value == poly and d.at.text_input(key="path_in").value == field["shp"]
    assert d.at.selectbox(key="sa_rule_" + kp[len("sa_path_"):]).value == "clip"
    # step 4: the clean map and the replay, a line says that the plots are in step 5; no Measure here
    d.open(4)
    assert any("The plots of the plot boundary are in step 5 (Plots)" in c.value for c in d.at.caption)
    assert not any(k.startswith("sa_go_") for k in d.keys())
    assert "5 of 6 steps done" in d.progress()                     # all but step 5 (the clean zip is written)
    # step 5: the clean map with the plot boundary drawn, then Measure (after the whole-field cleaning)
    d.click("step_next_4")
    assert d.open_step() == 5
    assert any("2 polygon(s) of the plot boundary (plots.geojson)" in c.value for c in d.at.caption)
    d.click(d.key("sa_go_"))
    S = d.at.session_state["cleaned"][tag]["R"]["small_area"]
    assert S["rule"] == "clip" and [p["name"] for p in S["polygons"]] == ["mid", "low"]
    assert "source" not in d.at.session_state["plot_area"][tag]                 # now the one kept with the file
    assert d.at.session_state["small_area"][tag]["rule"] == "clip"
    # step 6: the final files
    d.click("step_next_5")
    assert d.open_step() == 6
    dl = [str(b.key) for b in d.at.get("download_button")]
    assert f"dl_clean_{tag}" in dl and f"dl_difm_{tag}" in dl
    assert "6 of 6 steps done" in d.progress()


def test_import_values_not_applied_survive_and_step_3_says_so(field, tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    sw = d.key("fi_def_", "toggle")
    d.at.toggle(key=sw).set_value(False)
    d.run()
    kmax = d.key("fi_max_", "number_input")
    d.at.number_input(key=kmax).set_value(150.0)
    d.run()
    d.open(3)
    assert any(str(c.value).startswith(":orange[Step 1 has values not applied") for c in d.at.caption), \
        [c.value for c in d.at.caption]
    d.open(1)
    assert d.at.number_input(key=kmax).value == 150.0 and d.at.toggle(key=sw).value is False
    assert "Apply" in d.at.button(key=d.key("fi_go_")).label and not d.at.button(key=d.key("fi_go_")).disabled


def test_cleaning_and_small_area_bytes_equal_the_engine_called_directly(field, tmp_path, monkeypatch):
    import engine.run as er
    from engine.clean import small_area as sa
    calls = {}
    real_clean, real_sa = er.clean, er.small_area_after_clean

    def rec_clean(shp, out_dir, settings=None, **kw):
        calls["clean"] = (shp, settings, kw)
        return real_clean(shp, out_dir, settings, **kw)

    def rec_sa(R, polygons_path, rule="clip", log=print, extra=None, **kw):
        calls["sa"] = (polygons_path, rule, kw)
        return real_sa(R, polygons_path, rule, log=log, extra=extra, **kw)
    monkeypatch.setattr(er, "clean", rec_clean)
    monkeypatch.setattr(er, "small_area_after_clean", rec_sa)
    d = Drive(tmp_path / "ws", monkeypatch)
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.open(3)
    d.click("clean_one")
    d.open(5)
    d.click(d.key("sa_go_"))
    R = d.at.session_state["cleaned"][tag]["R"]
    # the engine called directly with the inputs the app gave it, into another folder
    shp, settings, kw = calls["clean"]
    kw = {k: v for k, v in kw.items() if k != "log"}
    R2 = real_clean(shp, str(tmp_path / "direct"), settings, log=lambda m: None, **kw)
    ppath, rule, skw = calls["sa"]
    fz2 = R2["files"]["flagged_zip"]
    stem2 = os.path.basename(fz2)[:-len("_flagged.zip")]          # the name the engine gives the small area's files
    rec2 = sa.run(fz2, ppath, str(tmp_path / "direct_sa"), stem2, rule, log=lambda m: None,
                  method=skw.get("method"), cv_pct=skw.get("cv_pct"), interior_m=skw.get("interior_m") or 0.0,
                  decoded=skw.get("decoded"), R=R2)

    def digest(path):
        if path.lower().endswith(".zip"):                # the members' bytes (a zip also stores its write time)
            with zipfile.ZipFile(path) as z:
                return {n: hashlib.sha256(z.read(n)).hexdigest() for n in sorted(z.namelist())}
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def shp_set(stem):
        return {os.path.splitext(p)[1]: digest(p) for p in glob.glob(stem + ".*")
                if os.path.splitext(p)[1].lower() in (".shp", ".shx", ".dbf", ".prj", ".cpg")}
    compared = 0
    for k in ("difm_ready_shp", "flagged_shp"):
        a, b = (R["files"] or {}).get(k), (R2["files"] or {}).get(k)
        if a and b:
            assert shp_set(os.path.splitext(a)[0]) == shp_set(os.path.splitext(b)[0]), k
            compared += 1
    for k in ("flagged_zip", "difm_ready_zip"):
        a, b = (R["files"] or {}).get(k), (R2["files"] or {}).get(k)
        if a and b and os.path.exists(a) and os.path.exists(b):
            assert digest(a) == digest(b), k
            compared += 1
    assert compared >= 3, R["files"].keys()
    F1, F2 = R["small_area"]["files"], rec2["files"]
    for k in ("csv", "zip", "parts_zip", "ground_zip"):
        if F1.get(k) or F2.get(k):
            assert digest(F1[k]) == digest(F2[k]), k
            compared += 1
    assert compared >= 6
    assert R["small_area"]["polygons"] == rec2["polygons"]


# ------------------------------------------------------------------------------------------------ the re-seating
def _keep_lists():
    """KEEP_KEYS and KEEP_SKIP of app/oced.py, read from its source (the app runs as a Streamlit script)."""
    import ast
    from engine.formats import native_write as nw
    tree = ast.parse(open(APP, encoding="utf-8").read())
    got = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", None) in (
                "KEEP_KEYS", "KEEP_SKIP"):
            got[node.targets[0].id] = eval(compile(ast.Expression(node.value), APP, "eval"), {"nw": nw})
    pre = tuple(p for ps in got["KEEP_KEYS"].values() for p in ps)
    return tree, pre, tuple(got["KEEP_SKIP"])


def test_no_button_of_the_app_is_re_seated():
    """keep_step_values re-seats every key under KEEP_KEYS but those of KEEP_SKIP: a button, a download button, an
    uploader or a selection whose key it re-seated would raise StreamlitValueAssignmentNotAllowedError when drawn.
    Every such widget of app/oced.py, its key with each format id for {fid} (the download of a raw format written in
    step 6), is outside KEEP_KEYS or inside KEEP_SKIP; the Gen4 checkbox nw_dl_<file> is still re-seated."""
    import ast
    import itertools
    from engine.formats import native_write as nw
    tree, pre, skip = _keep_lists()
    no_set = {"button", "download_button", "file_uploader", "form_submit_button", "data_editor", "chat_input",
              "camera_input", "audio_input", "download"}

    def samples(v):
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            return [v.value]
        if isinstance(v, ast.JoinedStr):
            parts = []
            for x in v.values:
                if isinstance(x, ast.Constant):
                    parts.append([str(x.value)])
                elif isinstance(getattr(x, "value", None), ast.Name) and x.value.id == "fid":
                    parts.append(list(nw.RAW_FORMATS))
                else:
                    parts.append(["k1"])
            return ["".join(c) for c in itertools.product(*parts)]
        return []
    seen, bad = 0, []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
        kw = {k.arg: k.value for k in n.keywords if k.arg}
        if "key" not in kw or not (fn in no_set or "on_select" in kw):
            continue
        for k in samples(kw["key"]):
            seen += 1
            if k.startswith(pre) and not k.startswith(skip):
                bad.append((n.lineno, fn, k))
    # held_uploader draws its uploader and its Clear button (key + "_clear") from the key it is given, a Name inside
    # it: the keys are checked at its call sites, a Name there read from its assignment in the source
    assigned = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            assigned.setdefault(n.targets[0].id, []).append(n.value)
    held = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "held_uploader":
            kv = n.args[1] if len(n.args) > 1 else next(k.value for k in n.keywords if k.arg == "key")
            for v in (assigned.get(kv.id, []) if isinstance(kv, ast.Name) else [kv]):
                for k in samples(v):
                    held.append((n.lineno, k))
                    held.append((n.lineno, k + "_clear"))
    for p in ("ff_up_", "bnd_up_"):                     # step 1's field files and step 3's own boundary
        assert any(k.startswith(p) for _, k in held) and any(k.startswith(p) and k.endswith("_clear")
                                                             for _, k in held), (p, held)
    for ln, k in held:
        seen += 1
        if k.startswith(pre) and not k.startswith(skip):
            bad.append((ln, "held_uploader", k))
    assert seen > 40 and not bad, bad
    assert "nw_dl_k1".startswith(pre) and not "nw_dl_k1".startswith(skip)          # the Gen4 checkbox is kept
    assert all(f"nw_dl_{f}_k1".startswith(skip) for f in nw.RAW_FORMATS)
    assert all(f"draw_{m}_k1".startswith(pre) for m in ("raw", "imp", "clean", "plot", "plots"))
    assert all(f"attr_{m}_k1".startswith(pre) for m in ("raw", "imp", "clean", "plot", "plots"))


def test_the_main_action_of_each_step_then_more_runs_and_tab_changes(field, tmp_path, monkeypatch):
    """The app as it runs: Apply (step 1), Clean (step 3), Measure (step 5) and a raw format written (step 6), each
    followed by more runs of its tab and a change of tab and back, never an exception (a download button re-seated
    raised one on the second run of the final files' step). 'Draw the readings as' survives a change of tab."""
    d = Drive(tmp_path / "ws", monkeypatch)
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    # step 1: own import values, Apply, the plot boundary
    d.at.toggle(key=d.key("fi_def_", "toggle")).set_value(False)
    d.run()
    d.at.number_input(key=d.key("fi_max_", "number_input")).set_value(150.0)
    d.run()
    d.click(d.key("fi_go_"))
    assert d.at.session_state["datasets"][tag]["import_mode"] == "custom"
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run().run().run()
    d.open(2)
    d.open(1)
    assert d.at.session_state["datasets"][tag]["import_mode"] == "custom"
    # step 2: 'Draw the readings as' points, kept across a change of tab
    d.open(2)
    kd = next(k for k in d.keys("button_group") if k.startswith("draw_raw_"))
    d.at.session_state[kd] = "points"
    d.run()
    d.open(4)
    d.open(2)
    assert [w.value for w in d.at.button_group if w.key == kd] == ["points"]
    # step 3: Clean, two more runs
    d.open(3)
    d.click("clean_one")
    d.run().run()
    assert os.path.exists(d.at.session_state["cleaned"][tag]["shp"])
    # step 5: Measure, two more runs, a change of tab and back
    d.open(5)
    d.click(d.key("sa_go_"))
    d.run().run()
    d.open(6)
    d.open(5)
    assert d.at.session_state["cleaned"][tag]["R"]["small_area"]["polygons"]
    # step 6: a raw format written, then two more runs, a change of tab and back
    d.open(6)
    d.click(d.key("nw_go_isoxml_"))
    assert [k for k in d.keys("download_button") if k.startswith("nw_dl_isoxml_")]
    d.run().run()
    d.open(3)
    d.open(6)
    d.run()
    assert [k for k in d.keys("download_button") if k.startswith("nw_dl_isoxml_")]
    assert "6 of 6 steps done" in d.progress()


def test_marks_reprocess_and_remove_all_edits_then_more_runs(tmp_path, monkeypatch):
    """The app as it runs, step 4: the replay's marks (as the player sends them) clean the file again, then more
    runs and a change of tab; 'Remove all edits' cleans it again without them, then more runs. The line beside the
    player says that marks not yet sent are lost on a change of step."""
    sys.path.insert(0, os.path.join(ROOT, "app"))
    import pyogrio
    import replay_view
    from engine import replay as rp
    from tests.synthetic_replay import make_two_at_once
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, two["shp"])
    tag = d.at.session_state["active"]
    d.open(3)
    d.click("clean_one")
    C0 = d.at.session_state["cleaned"][tag]
    d.open(4)
    box = next(k for k in d.at.session_state.filtered_state if str(k).startswith("replay_box_clean_"))
    d.at.session_state[box] = True
    d.run()
    assert any(replay_view.marks_kept_line("clean") in str(c.value) for c in d.at.caption)
    P = rp.replay_payload(C0["flagged_shp"], kind="clean", record=C0["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C0["flagged_shp"], read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    rm = []
    for Cb in P["combines"]:
        rm += [[Cb["num"], i] for i, r in enumerate(Cb["rows"]) if F.iloc[r]["Rem_By"] == ""][:3]
    d.at.session_state[box] = True
    d.at.session_state[replay_view.marks_key(box[len("replay_box_"):])] = {
        "token": P["edit"]["token"], "remove": rm[:3], "keep": [], "changed": 3}
    d.run()
    C1 = d.at.session_state["cleaned"][tag]
    assert C1["R"]["manual_edits"]["remove"]["readings_applied"] == 3
    d.run().run()
    d.open(6)
    d.open(4)
    d.click("edits_remove")
    d.run().run()
    assert "manual_edits" not in d.at.session_state["cleaned"][tag]["R"]
    assert "edits_remove" not in d.keys()


def test_a_plot_boundary_given_and_not_measured_is_kept_with_the_work(field, tmp_path, monkeypatch):
    """Step 1's plot boundary given and not yet measured is saved with the work and comes back when the work is
    opened again: a path (typed again into step 1, with its choices) and an upload (written into the work folder
    until it is measured, read back as bytes). After Measure the save removes the upload's folder. A work with no
    plot boundary given writes no 'plot_area' in its record."""
    import json

    class Up:                                            # an uploaded file as the uploader gives it
        def __init__(self, name, data):
            self.name, self._b = name, data

        def getbuffer(self):
            return memoryview(self._b)

    def record(d):
        with open(os.path.join(d.at.session_state["workdir"], "oced_work.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def reopen(ws):
        d2 = Drive(ws, monkeypatch)
        d2.at.button(key="work_open").click()
        d2.run()
        return d2
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    ws = tmp_path / "ws"
    d = Drive(ws, monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.click("work_save")
    assert "plot_area" not in record(d)
    # a path, with the edge rule and the interior cut changed
    kp = d.key("sa_path_", "text_input")
    TK = kp[len("sa_path_"):]
    d.at.text_input(key=kp).input(poly)
    d.at.selectbox(key=f"sa_rule_{TK}").set_value("full")
    d.at.number_input(key=f"sa_int_{TK}").set_value(5.0)
    d.run()
    d.click("work_save")
    PA = record(d)["plot_area"][tag]
    assert PA["source"] == "path" and PA["path"] == poly and PA["rule"] == "full" and PA["interior"] == 5.0
    d2 = reopen(ws)
    P2 = d2.at.session_state["plot_area"][tag]
    assert P2["source"] == ("path", poly) and P2["rule"] == "full" and P2["interior"] == 5.0
    kp2 = d2.key("sa_path_", "text_input")
    assert d2.at.text_input(key=kp2).value == poly
    assert d2.at.selectbox(key="sa_rule_" + kp2[len("sa_path_"):]).value == "full"
    # an upload: written into the work folder at the save, read back as bytes
    data = open(poly, "rb").read()
    d2.at.text_input(key=kp2).input("")
    d2.run()
    d2.at.session_state["plot_area"][tag]["source"] = ("upload", [Up("plots.geojson", data)])
    d2.at.session_state["plot_area"][tag]["name"] = "plots.geojson"
    d2.run()
    d2.click("work_save")
    PA = record(d2)["plot_area"][tag]
    assert PA["source"] == "upload" and PA["files"] == ["plots.geojson"] and PA["rule"] == "full"
    held = os.path.join(d2.at.session_state["workdir"], PA["path"], "plots.geojson")
    assert open(held, "rb").read() == data
    d3 = reopen(ws)
    src = d3.at.session_state["plot_area"][tag]["source"]
    assert src[0] == "upload" and bytes(src[1][0].getbuffer()) == data
    # measured: the small area is kept with the file, the upload's folder goes at the save
    d3.open(3)
    d3.click("clean_one")
    d3.open(5)
    d3.click(d3.key("sa_go_"))
    S = d3.at.session_state["cleaned"][tag]["R"]["small_area"]
    assert S["rule"] == "full" and [p["name"] for p in S["polygons"]] == ["mid", "low"]
    R = record(d3)
    assert tag in R["small_area"] and "plot_area" not in R
    assert not os.path.exists(os.path.dirname(held))


def test_the_import_widgets_of_an_import_since_replaced_do_not_come_back(field, tmp_path, monkeypatch):
    """The app as it runs: the import settings' widgets are keyed by the import they show. Own values applied, then
    the switch back on: the file is on SMS's default again and its widgets start from it (the switch on, no value
    'not applied'), not from the values typed under that import before the Apply (the re-seating keeps the values of
    the steps not drawn only; a step drawn drops those of its widgets it did not draw)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    sw0 = d.key("fi_def_", "toggle")
    d.at.toggle(key=sw0).set_value(False)
    d.run()
    d.at.number_input(key=d.key("fi_max_", "number_input")).set_value(150.0)
    d.run()
    d.click(d.key("fi_go_"))
    assert d.at.session_state["datasets"][tag]["import_mode"] == "custom"
    assert sw0 not in d.at.session_state.filtered_state          # the widgets of the import replaced: dropped
    d.open(3)
    d.open(1)
    sw = d.key("fi_def_", "toggle")
    d.at.toggle(key=sw).set_value(True)
    d.run()
    assert d.at.session_state["datasets"][tag]["import_mode"] == "default"
    sw2 = d.key("fi_def_", "toggle")
    assert d.at.toggle(key=sw2).value is True
    assert not any("Not applied" in str(c.value) for c in d.at.caption), [c.value for c in d.at.caption]
    d.open(3)
    assert not any(str(c.value).startswith(":orange[Step 1 has values not applied") for c in d.at.caption)


def _uploader(d: Drive, prefix: str):
    return next(u for u in d.at.get("file_uploader") if str(u.key or "").startswith(prefix))


def _waiting(d: Drive, name: str) -> bool:
    return any("Chosen before and waiting" in str(c.value) and name in str(c.value) for c in d.at.caption)


def test_field_files_uploaded_before_open_wait_over_a_change_of_step(field, tmp_path, monkeypatch):
    """Step 1's field boundary and zone map chosen in their uploaders and not yet used: a change of step empties the
    uploaders (Streamlit), the files are held and named on one line, and Open uses them (the same bytes as given).
    The raw data's uploader says that its files wait for Open only while step 1 is open. Clear forgets held files."""
    d = Drive(tmp_path / "ws", monkeypatch)
    raw = os.path.splitext(field["shp"])[0]
    _uploader(d, "uploads_").set_value([(os.path.basename(raw) + e, open(raw + e, "rb").read(),
                                         "application/octet-stream") for e in (".shp", ".shx", ".dbf", ".prj")])
    d.run()
    assert any(str(c.value).startswith("These files wait for Open") for c in d.at.caption)
    _uploader(d, "uploads_").set_value(None)
    d.run()
    bname = os.path.basename(field["boundary"])
    bdata = open(field["boundary"], "rb").read()
    zdata = open(_poly(field["shp"], tmp_path / "zones.geojson"), "rb").read()
    _uploader(d, "ff_up_b_").set_value((bname, bdata, "application/geo+json"))
    d.run()
    _uploader(d, "ff_up_z_").set_value(("zones.geojson", zdata, "application/geo+json"))
    d.run()
    assert not _waiting(d, bname)                                    # in the uploader itself: no line
    d.open(2)
    d.open(4)
    d.open(1)
    assert not _uploader(d, "ff_up_b_").value and not _uploader(d, "ff_up_z_").value   # emptied by the change of step
    assert _waiting(d, bname) and _waiting(d, "zones.geojson")
    _open(d, field["shp"])
    F = d.at.session_state["field_files"]
    assert F["boundary"] and F["boundary"]["name"] == bname and F["zones"]["name"] == "zones.geojson"
    with open(F["boundary"]["path"], "rb") as fh:
        assert fh.read() == bdata
    assert not (d.at.session_state["_held_up"] or {})                # used: nothing is held any more
    assert not _waiting(d, bname)
    # Clear: a file held, then forgotten
    d.click("ff_chg_b")
    _uploader(d, "ff_up_b_").set_value((bname, bdata, "application/geo+json"))
    d.run()
    d.open(3)
    d.open(1)
    assert _waiting(d, bname)
    d.click(next(k for k in d.keys() if k.startswith("ff_up_b_") and k.endswith("_clear")))
    assert not _waiting(d, bname) and not (d.at.session_state["_held_up"] or {})
    # the files taken out of the uploader by the user: not held either
    _uploader(d, "ff_up_b_").set_value((bname, bdata, "application/geo+json"))
    d.run()
    _uploader(d, "ff_up_b_").set_value(None)
    d.run()
    d.open(2)
    d.open(1)
    assert not _waiting(d, bname) and not (d.at.session_state["_held_up"] or {})


def test_a_files_own_boundary_uploaded_in_step_3_waits_over_a_change_of_step(field, tmp_path, monkeypatch):
    """Step 3's own boundary of a file chosen in its uploader, then another step opened and step 3 again: Use takes
    the held file."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.open(3)
    bname = os.path.basename(field["boundary"])
    bdata = open(field["boundary"], "rb").read()
    _uploader(d, "bnd_up_").set_value((bname, bdata, "application/geo+json"))
    d.run()
    d.open(2)
    d.open(3)
    assert not _uploader(d, "bnd_up_").value and _waiting(d, bname)
    d.click(d.key("bnd_use_"))
    B = d.at.session_state["boundary"][tag]
    assert B and B["name"] == bname
    assert not (d.at.session_state["_held_up"] or {})


def test_an_emptied_growers_weight_stays_empty(field, tmp_path, monkeypatch):
    """The grower's weight typed, another value changed, the box emptied: it stays empty (it took the value back up
    to 0.4.0's check), also over a change of step; a weight typed comes back after a change of step."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.open(3)
    wk = d.key("gw_w_", "number_input")
    d.at.number_input(key=wk).set_value(100_000.0)
    d.run()
    assert d.at.session_state["grower"][tag]["weight"] == 100_000.0
    d.at.number_input(key="k_sd").set_value(2.5)
    d.run()
    d.at.number_input(key=wk).set_value(None)
    d.run()
    assert d.at.number_input(key=wk).value is None and not d.at.session_state["grower"][tag]["weight"]
    d.at.number_input(key="k_sd").set_value(3.0)
    d.run()
    assert d.at.number_input(key=wk).value is None
    d.open(2)
    d.open(3)
    assert d.at.number_input(key=wk).value is None and not d.at.session_state["grower"][tag]["weight"]
    d.at.number_input(key=wk).set_value(98_765.0)
    bk = d.key("gw_b_", "button_group")
    assert d.at.button_group(key=bk).value == "dry"                 # 0.4.0: weighed at the standard moisture first
    d.at.button_group(key=bk).set_value("wet")                      # the grain moisture is for a wet weight
    d.run()
    d.at.number_input(key=d.key("gw_m_", "number_input")).set_value(17.5)
    d.run()
    d.open(1)
    d.open(3)
    assert d.at.number_input(key=wk).value == 98_765.0
    assert d.at.button_group(key=bk).value == "wet"
    assert d.at.number_input(key=d.key("gw_m_", "number_input")).value == 17.5
    assert d.at.session_state["grower"][tag]["weight"] == 98_765.0


def test_the_replay_texts_name_the_steps_of_0_4_0():
    """The replay of the imported readings (step 2) shares its edits by hand with the replay of the cleaning, now
    step 4: its caption (a string cut over two lines in the source) and the module's docstring say so."""
    import ast
    src = open(os.path.join(ROOT, "app", "replay_view.py"), encoding="utf-8").read()
    texts = [n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    edits = [t for t in texts if "one list of edits by hand with step" in t]
    assert edits and all("with step 4's" in t for t in edits), edits
    doc = ast.get_docstring(ast.parse(src))
    assert "the same edits file as step\n4's" in doc and "edits file as step\n3's" not in doc
    app_doc = ast.get_docstring(ast.parse(open(APP, encoding="utf-8").read()))
    assert "The maps of step 2 fold once the file is cleaned" not in app_doc


# ------------------------------------------------------------------------------------------------ 0.4.0's last points
def _toast(d: Drive, text: str) -> bool:
    return any(text in str(t.value) for t in d.at.toast)


def _geo(path) -> tuple:
    return os.path.basename(str(path)), open(path, "rb").read(), "application/geo+json"


def test_a_waiting_field_file_and_a_typed_path_take_neither(field, tmp_path, monkeypatch):
    """Step 1's field files: a file chosen earlier and only held (the 'Chosen before and waiting' line) and the path
    of another file typed beside it: Open opens nothing and Use uses nothing, and one line says to Clear the waiting
    file or empty the path (as Open does for the raw data given both ways); Clear, and the path is taken. A file in
    the uploader itself with a path typed is taken as in 0.3.8 (the upload)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    bfile, other = field["boundary"], field["two_fields"]
    zfile = _poly(field["shp"], tmp_path / "zones.geojson")
    zother = _poly(field["shp"], tmp_path / "zones_other.geojson")
    _uploader(d, "ff_up_b_").set_value(_geo(bfile))
    d.run()
    _uploader(d, "ff_up_z_").set_value(_geo(zfile))
    d.run()
    d.open(2)
    d.open(1)
    assert _waiting(d, os.path.basename(bfile)) and _waiting(d, "zones.geojson")
    helps = [str(c.proto.help) for c in d.at.caption if "Chosen before and waiting" in str(c.value)]
    assert helps and all("takes neither" in h and "path box beside is empty" in h for h in helps), helps
    d.at.text_input(key="ff_path_b").input(other)
    d.at.text_input(key="ff_path_z").input(zother)
    d.at.text_input(key="path_in").input(field["shp"])
    d.click("open_btn")
    assert not d.at.session_state["datasets"]                        # nothing opened, nothing guessed
    assert _toast(d, "Both a file waiting and a path are given for the field boundary and the zone map: Clear the "
                     "waiting file or empty the path, then Open"), [t.value for t in d.at.toast]
    assert _waiting(d, os.path.basename(bfile)) and d.at.text_input(key="ff_path_b").value == other
    # Clear the waiting boundary, empty the zone map's path: Open takes the boundary's path and the zone map held
    d.click(next(k for k in d.keys() if k.startswith("ff_up_b_") and k.endswith("_clear")))
    d.at.text_input(key="ff_path_z").input("")
    d.click("open_btn")
    F = d.at.session_state["field_files"]
    assert d.at.session_state["datasets"] and F["boundary"]["name"] == os.path.basename(other)
    assert F["zones"]["name"] == "zones.geojson"
    # with the data open: Use with a held file and a path typed uses neither
    d.click("ff_chg_b")
    _uploader(d, "ff_up_b_").set_value(_geo(bfile))
    d.run()
    d.open(3)
    d.open(1)
    assert _waiting(d, os.path.basename(bfile))
    d.at.text_input(key="ff_path_b").input(other)
    d.click("ff_use_b")
    assert _toast(d, "Both a file waiting and a path are given for the field boundary: Clear the waiting file or "
                     "empty the path, then Use")
    assert d.at.session_state["field_files"]["boundary"]["name"] == os.path.basename(other)   # unchanged
    assert _waiting(d, os.path.basename(bfile))
    # a file in the uploader itself and a path typed: the upload, as 0.3.8
    _uploader(d, "ff_up_b_").set_value(_geo(bfile))
    d.at.text_input(key="ff_path_b").input(other)
    d.click("ff_use_b")
    assert d.at.session_state["field_files"]["boundary"]["name"] == os.path.basename(bfile)
    assert not _toast(d, "Both a file waiting")


def test_a_files_own_waiting_boundary_and_a_typed_path_take_neither(field, tmp_path, monkeypatch):
    """Step 3's own boundary of a file: a held file and a path typed, Use takes neither and says so; a file in the
    uploader itself with a path typed is taken (the upload, as 0.3.8)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    bfile, other = field["boundary"], field["two_fields"]
    d.open(3)
    _uploader(d, "bnd_up_").set_value(_geo(bfile))
    d.run()
    d.open(2)
    d.open(3)
    assert _waiting(d, os.path.basename(bfile))
    d.at.text_input(key=d.key("bnd_path_", "text_input")).input(other)
    d.click(d.key("bnd_use_"))
    assert _toast(d, "Both a file waiting and a path are given for this file's own boundary: Clear the waiting file "
                     "or empty the path, then Use")
    assert not (d.at.session_state["boundary"] or {}).get(tag) and _waiting(d, os.path.basename(bfile))
    _uploader(d, "bnd_up_").set_value(_geo(bfile))
    d.at.text_input(key=d.key("bnd_path_", "text_input")).input(other)
    d.click(d.key("bnd_use_"))
    assert d.at.session_state["boundary"][tag]["name"] == os.path.basename(bfile)


def _plot_box(d: Drive):
    """Step 1's 'Plot boundary' expander (AppTest lists an expander drawn with an icon under status)."""
    return next(e for e in list(d.at.expander) + list(d.at.status) if str(e.label).startswith("Plot boundary"))


def test_the_plot_boundary_section_stays_open_once_touched_and_names_its_file(field, tmp_path, monkeypatch):
    """Step 1's 'Plot boundary' section: folded and 'optional' until the user changes something in it; then it stays
    open over every later run (drawn folded after a run drawn open, the browser folded it: the path typed, emptied,
    then the CV changed) and over a change of step, and its label names the polygon file given."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    box_ = _plot_box(d)
    assert box_.label == "Plot boundary · optional" and not box_.proto.expanded
    pk = d.key("sa_path_", "text_input")
    d.at.text_input(key=pk).input(poly)
    d.run()
    assert _plot_box(d).label == "Plot boundary · plots.geojson given" and _plot_box(d).proto.expanded
    d.at.text_input(key=pk).input("")
    d.run()
    assert _plot_box(d).label == "Plot boundary · optional" and _plot_box(d).proto.expanded
    d.at.number_input(key=d.key("sa_cv_", "number_input")).set_value(3.0)
    d.run()
    assert _plot_box(d).proto.expanded
    d.at.text_input(key=pk).input(poly)
    d.run()
    d.open(2)
    d.open(1)
    assert _plot_box(d).label == "Plot boundary · plots.geojson given" and _plot_box(d).proto.expanded
    assert d.at.session_state["plot_area"][d.at.session_state["active"]]["name"] == "plots.geojson"


def test_a_files_own_boundary_held_goes_with_its_work(field, tmp_path, monkeypatch):
    """Step 3's own boundary of a file chosen and held, then other data opened by path: the held file belonged to the
    old work and is dropped (it came back as 'waiting' under the new work's file of the same name); the field
    boundary held in step 1 for that Open is not dropped: the new work uses it."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    bfile, other = field["boundary"], field["two_fields"]
    d.open(3)
    _uploader(d, "bnd_up_").set_value(_geo(bfile))
    d.run()
    d.open(1)
    assert any(str(k).startswith("bnd_up_") for k in d.at.session_state["_held_up"])
    _uploader(d, "ff_up_b_").set_value(_geo(other))
    d.run()
    d.open(2)
    d.open(1)
    assert _waiting(d, os.path.basename(other))
    d.at.text_input(key="path_in").input(field["shp"])
    d.click("open_btn")
    assert not any(str(k).startswith("bnd_up_") for k in (d.at.session_state["_held_up"] or {}))
    assert d.at.session_state["field_files"]["boundary"]["name"] == os.path.basename(other)
    d.open(3)
    assert not _waiting(d, os.path.basename(bfile))


def _deck_paths(d: Drive) -> list:
    """The lines drawn over each map on screen (its PathLayers' paths, rounded), one sorted list per map."""
    import json
    out = []
    for e in d.at.get("deck_gl_json_chart"):
        spec = json.loads(e.proto.json)
        out.append(sorted(tuple((round(x, 7), round(y, 7)) for x, y in r["path"])
                          for L in spec.get("layers") or [] if L.get("@@type") == "PathLayer"
                          for r in L.get("data") or []))
    return out


def _rings(path) -> list:
    g = gpd.read_file(path).to_crs(4326)
    return sorted(tuple((round(x, 7), round(y, 7)) for x, y in p.exterior.coords) for p in g.geometry)


def _plot_line(d: Drive, name: str):
    return next((s.value for s in d.at.success if str(s.value).startswith(name + " · ")), None)


def _files_in(root) -> set:
    return {os.path.relpath(os.path.join(r, f), root) for r, _, fs in os.walk(root) for f in fs}


def _tmp_reads() -> set:
    import tempfile
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "oced_plot_*")))


def test_the_plot_boundary_is_read_when_given_and_drawn_on_the_maps_before_measure(field, tmp_path, monkeypatch):
    """Step 1's plot boundary is read as soon as it is given, a path or an upload: one line names its file, its
    polygons and acres, nothing is written into the work for it (Measure writes it there, as before) and its
    temporary copy is gone; the raw map of step 2 and the clean map of step 5 (Plots) draw its polygons before
    Measure, with a line under the map saying what the lines are (step 4's clean map draws the field boundary only);
    and a file uploaded after one was measured is the one drawn."""
    tmp0 = _tmp_reads()
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    wd = d.at.session_state["workdir"]
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    g = gpd.read_file(poly)
    ac = g.to_crs(g.estimate_utm_crs()).area.sum() / 4046.8564224
    before = _files_in(wd)
    # a path
    pk = d.key("sa_path_", "text_input")
    d.at.text_input(key=pk).input(poly)
    d.run()
    assert _plot_line(d, "plots.geojson") == f"plots.geojson · 2 polygon(s) · {ac:,.2f} ac"
    assert d.at.session_state["plot_area"][tag]["source"] == ("path", poly) and not d.at.error
    assert _files_in(wd) == before
    d.open(2)
    assert _deck_paths(d)[0] == _rings(poly)                       # no field boundary: the plots' lines only
    assert any(c.value == "The lines: the 2 polygon(s) of the plot boundary (plots.geojson, step 1)."
               for c in d.at.caption)
    # an upload in its place
    d.open(1)
    d.at.text_input(key=pk).input("")
    d.run()
    assert "source" not in d.at.session_state["plot_area"][tag]
    _uploader(d, "sa_up_").set_value([_geo(poly)])
    d.run()
    assert _plot_line(d, "plots.geojson") == f"plots.geojson · 2 polygon(s) · {ac:,.2f} ac"
    assert d.at.session_state["plot_area"][tag]["source"][0] == "upload"
    assert _files_in(wd) == before and _tmp_reads() == tmp0      # read in a temporary folder, deleted
    d.open(2)
    assert _deck_paths(d)[0] == _rings(poly)
    d.open(3)
    d.click("clean_one")
    d.open(4)
    assert _deck_paths(d)[0] == []                                 # step 4: no field boundary here, no plots
    d.open(5)
    assert _deck_paths(d)[0] == _rings(poly)                       # before Measure
    assert any("2 polygon(s) of the plot boundary (plots.geojson)" in c.value for c in d.at.caption)
    d.click(d.key("sa_go_"))
    assert d.at.session_state["small_area"][tag]["name"] == "plots.geojson"
    assert [p["name"] for p in d.at.session_state["cleaned"][tag]["R"]["small_area"]["polygons"]] == ["mid", "low"]
    # the caption under the table of the cleaned map average in detail: 0.3.8's, word for word (OCED's names)
    rt = d.at.session_state["cleaned"][tag]["R"]["small_area"]["rule_text"]
    assert any(c.value == f"Edge rule {rt}. Dry yield = total dry bu / area (area-weighted, as the SMS summary); mean "
               "= the plain mean of the readings. Cleaned: the readings the whole-field cleaning kept (Yld_Vol_Dr x "
               "Swath_Scl over Dist_Opt x Wdth_Opt, as the clean file); as imported: every reading of the field, no "
               "cleaning." for c in d.at.caption)
    # a new file uploaded over the one measured: the new one is drawn (steps 2 and 5) before it is measured
    one = tmp_path / "one.geojson"
    gpd.GeoDataFrame({"name": ["east"]}, geometry=[g.geometry.iloc[0].buffer(0.0001)], crs=4326).to_file(
        one, driver="GeoJSON")
    d.open(1)
    d.click(d.key("sa_chg_"))
    _uploader(d, "sa_up_").set_value([_geo(one)])
    d.run()
    assert _plot_line(d, "one.geojson").startswith("one.geojson · 1 polygon(s) · ")
    d.open(5)
    assert _deck_paths(d)[0] == _rings(one)
    assert any("1 polygon(s) of the plot boundary (one.geojson)" in c.value for c in d.at.caption)
    d.open(2)
    assert _deck_paths(d)[0] == _rings(one)
    assert d.at.session_state["small_area"][tag]["name"] == "plots.geojson"      # not measured: nothing changed
    assert _tmp_reads() == tmp0


def test_a_plot_boundary_that_cannot_be_read_is_said_and_not_kept(field, tmp_path, monkeypatch):
    """A plot boundary that is not a polygon file (an upload of bad bytes, a file of points, a path not there): one
    error line in step 1, the section's label says it is not read, and it is not kept as given (no outline, nothing
    for Measure)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    _uploader(d, "sa_up_").set_value([("bad.geojson", b"not a polygon file", "application/geo+json")])
    d.run()
    assert [e.value for e in d.at.error] == [NOT_POLYGONS.format("bad.geojson")]     # plain: no temporary path
    assert _plot_box(d).label == "Plot boundary · bad.geojson not read"
    assert "source" not in d.at.session_state["plot_area"][tag] and not _plot_line(d, "bad.geojson")
    _uploader(d, "sa_up_").set_value(None)
    d.run()
    pts = tmp_path / "points.geojson"
    gpd.read_file(field["shp"]).head(5)[["geometry"]].to_file(pts, driver="GeoJSON")
    pk = d.key("sa_path_", "text_input")
    for p, why in ((str(pts), "points.geojson holds no polygon"),
                   (str(tmp_path / "gone.geojson"), "not found on this computer: ")):
        d.at.text_input(key=pk).input(p)
        d.run()
        name = os.path.basename(p)
        assert [e.value for e in d.at.error if str(e.value).startswith(f"{name} cannot be read as polygons ({why}")], \
            [e.value for e in d.at.error]
        assert _plot_box(d).label == f"Plot boundary · {name} not read"
        assert "source" not in d.at.session_state["plot_area"][tag]
    d.open(2)
    assert not any(_deck_paths(d)) and not any("of the plot boundary" in str(c.value) for c in d.at.caption)


def test_the_plot_boundary_is_drawn_on_both_maps_of_step_2(field, tmp_path, monkeypatch):
    """With an import of your settings in use, step 2 draws two maps (SMS's default import and the import in use):
    both draw the field boundary and the plot boundary given in step 1, and one line says what the lines are."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    d.at.text_input(key="ff_path_b").input(field["boundary"])
    d.click("ff_use_b")
    assert d.at.session_state["field_files"]["boundary"]
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.at.toggle(key=d.key("fi_def_", "toggle")).set_value(False)
    d.run()
    d.at.number_input(key=d.key("fi_max_", "number_input")).set_value(150.0)
    d.run()
    d.click(d.key("fi_go_"))
    assert d.at.session_state["datasets"][d.at.session_state["active"]].get("import_mode") not in (None, "default")
    d.open(2)
    maps = _deck_paths(d)
    assert len(maps) >= 2, len(maps)
    want = _rings(poly)
    for m in maps[:2]:
        assert all(r in m for r in want) and len(m) > len(want)        # the plots and the field boundary
    assert any(c.value == "The lines: the field boundary and the 2 polygon(s) of the plot boundary (plots.geojson, "
                          "step 1)." for c in d.at.caption)


NOT_POLYGONS = ("{} cannot be read as polygons: it is not a polygon file OCED can read (a .zip of a shapefile, .shp "
                "+ .shx + .dbf + .prj, .geojson, .gpkg, .kml, .kmz). Give another file.")


def _tk(d: Drive) -> str:
    return d.key("sa_cv_", "number_input")[len("sa_cv_"):]


def test_a_plot_of_two_parts_is_one_polygon_on_every_map_and_the_caption_of_oced_names(field, tmp_path,
                                                                                       monkeypatch):
    """A plot boundary of two plots, one of them a polygon of two parts: step 1, the raw map of step 2 and the clean
    map of step 5 all say 2 polygons (the maps draw 3 rings); measured, the caption under the table of the cleaned
    map average in detail is that of 0.3.8 word for word for a file with OCED's names."""
    from shapely.geometry import MultiPolygon
    poly = _poly(field["shp"], tmp_path / "two.geojson")
    g = gpd.read_file(poly)
    a, b = g.geometry.iloc[0], g.geometry.iloc[1]
    multi = tmp_path / "multi.geojson"
    gpd.GeoDataFrame({"name": ["parts", "one"]},
                     geometry=[MultiPolygon([a, b.buffer(-0.00005)]), b.buffer(-0.0001).buffer(0)], crs=4326).to_file(
        multi, driver="GeoJSON")
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(str(multi))
    d.run()
    assert str(_plot_line(d, "multi.geojson")).startswith("multi.geojson · 2 polygon(s) · ")
    d.open(2)
    assert len(_deck_paths(d)[0]) == 3                              # the rings drawn: two parts + one
    assert any(c.value == "The lines: the 2 polygon(s) of the plot boundary (multi.geojson, step 1)."
               for c in d.at.caption), [c.value for c in d.at.caption]
    d.open(3)
    d.click("clean_one")
    d.open(5)
    assert any("the 2 polygon(s) of the plot boundary (multi.geojson)." in c.value for c in d.at.caption)
    d.click(d.key("sa_go_"))
    SA = d.at.session_state["cleaned"][tag]["R"]["small_area"]
    assert "columns" not in SA and [p["name"] for p in SA["polygons"]] == ["parts", "one"]
    want = (f"Edge rule {SA['rule_text']}. Dry yield = total dry bu / area (area-weighted, as the SMS summary); "
            "mean = the plain mean of the readings. Cleaned: the readings the whole-field cleaning kept "
            "(Yld_Vol_Dr x Swath_Scl over Dist_Opt x Wdth_Opt, as the clean file); as imported: every reading "
            "of the field, no cleaning.")
    assert want in [c.value for c in d.at.caption]


def test_clear_keeps_the_plot_boundary_section_open(field, tmp_path, monkeypatch):
    """A plot boundary uploaded and held over a change of step, in a section not touched in this session (a work
    reopened): Clear forgets it and the section stays open after the rerun (it is not folded under the user)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _uploader(d, "sa_up_").set_value([_geo(poly)])
    d.run()
    d.open(2)
    d.open(1)
    TK = _tk(d)
    d.at.session_state[f"sa_touched_{TK}"] = False                # as a work reopened: the section not touched
    d.run()
    assert _plot_box(d).proto.expanded and _plot_box(d).label == "Plot boundary · plots.geojson given"
    d.click(f"sa_clear_{TK}")
    assert "source" not in d.at.session_state["plot_area"][tag]
    assert _plot_box(d).label == "Plot boundary · optional" and _plot_box(d).proto.expanded


def test_keep_the_one_given_drops_what_was_chosen_after_change(field, tmp_path, monkeypatch):
    """Step 1's field files: a file given, then Change, another file chosen (held over a change of step) or another
    path typed, then 'Keep the one given': the file given stays and what was chosen is given up, so the next Open of
    other data does not take it (before, the declined file was taken by that Open without a word)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    zones = _poly(field["shp"], tmp_path / "zones.geojson")
    other_z = _poly(field["shp"], tmp_path / "zones_other.geojson")
    d.at.text_input(key="ff_path_b").input(field["boundary"])
    d.click("ff_use_b")
    d.at.text_input(key="ff_path_z").input(zones)
    d.click("ff_use_z")
    F = d.at.session_state["field_files"]
    assert F["boundary"]["name"] == os.path.basename(field["boundary"]) and F["zones"]["name"] == "zones.geojson"
    # the boundary: another file chosen after Change, held over a change of step, then declined
    d.click("ff_chg_b")
    _uploader(d, "ff_up_b_").set_value(_geo(field["two_fields"]))
    d.run()
    d.open(2)
    d.open(1)
    assert _waiting(d, os.path.basename(field["two_fields"]))
    d.click("ff_keep_b")
    assert not any(str(k).startswith("ff_up_b_") for k in (d.at.session_state["_held_up"] or {}))
    # the zone map: another path typed after Change, then declined
    d.click("ff_chg_z")
    d.at.text_input(key="ff_path_z").input(other_z)
    d.click("ff_keep_z")
    assert not str(d.at.session_state["ff_path_z"] if "ff_path_z" in d.at.session_state else "")
    assert d.at.session_state["field_files"]["boundary"]["name"] == os.path.basename(field["boundary"])
    assert d.at.session_state["field_files"]["zones"]["name"] == "zones.geojson"
    # other data opened (a new work): nothing was waiting, so it starts without field files (before, the files
    # declined were taken by this Open)
    d.at.text_input(key="path_in").input(field["shp"])
    d.click("open_btn")
    F = d.at.session_state["field_files"]
    assert not F.get("boundary") and not F.get("zones"), (F.get("boundary"), F.get("zones"))


def test_a_shapefile_uploaded_as_its_files_is_named_by_its_shp(field, tmp_path, monkeypatch):
    """A plot boundary uploaded as the separate files of a shapefile, the .cpg first: the line, the section's label
    and, for files that cannot be read, the error line name the .shp (the file read), not the first file given."""
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    shp = tmp_path / "plots.shp"
    gpd.read_file(poly).to_file(shp)
    base = str(shp)[:-4]
    with open(base + ".cpg", "w", encoding="ascii") as fh:
        fh.write("UTF-8")
    files = [("plots" + e, open(base + e, "rb").read(), "application/octet-stream")
             for e in (".cpg", ".dbf", ".prj", ".shp", ".shx")]
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    _uploader(d, "sa_up_").set_value(files)
    d.run()
    assert str(_plot_line(d, "plots.shp")).startswith("plots.shp · 2 polygon(s) · "), [s.value for s in d.at.success]
    assert _plot_box(d).label == "Plot boundary · plots.shp given"
    assert d.at.session_state["plot_area"][tag]["name"] == "plots.shp"
    _uploader(d, "sa_up_").set_value([("bad.cpg", b"UTF-8", "application/octet-stream"),
                                      ("bad.shp", b"not a shapefile", "application/octet-stream")])
    d.run()
    assert [e.value for e in d.at.error] == [NOT_POLYGONS.format("bad.shp")]
    assert _plot_box(d).label == "Plot boundary · bad.shp not read"


# ------------------------------------------------------------------------------------------------ 0.4.0: plot names
def _deck_specs(d: Drive) -> list:
    """Each map's deck.gl spec, with its tooltip (sent beside the spec) as 'tooltip'."""
    import json
    out = []
    for e in d.at.get("deck_gl_json_chart"):
        spec = json.loads(e.proto.json)
        spec["tooltip"] = json.loads(e.proto.tooltip) if e.proto.tooltip else None
        out.append(spec)
    return out


def _names_layer(spec: dict) -> dict | None:
    return next((L for L in spec.get("layers") or [] if L.get("@@type") == "TextLayer"), None)


def _plot_ring_names(spec: dict) -> set:
    """The names on the plot rings (the pickable PathLayer whose rows carry 'plot')."""
    return {r["plot"] for L in spec.get("layers") or [] if L.get("@@type") == "PathLayer"
            for r in L.get("data") or [] if "plot" in r}


def _named_plots(shp: str, path) -> list:
    """Three plots: two of one name and one without a name (numbered), as the small area table names them."""
    g = gpd.read_file(shp)
    x0, x1, y0, y1 = g.geometry.x.min(), g.geometry.x.max(), g.geometry.y.min(), g.geometry.y.max()
    dx, dy = x1 - x0, y1 - y0
    gpd.GeoDataFrame({"name": ["test", "test", None]},
                     geometry=[box(x0 + dx * 0.1, y0 + dy * 0.1, x0 + dx * 0.4, y0 + dy * 0.3),
                               box(x0 + dx * 0.5, y0 + dy * 0.1, x0 + dx * 0.8, y0 + dy * 0.3),
                               box(x0 + dx * 0.1, y0 + dy * 0.5, x0 + dx * 0.15, y0 + dy * 0.9)],
                     crs=4326).to_file(path, driver="GeoJSON")
    return ["test", "test (2)", "3"]


def _check_names(spec: dict, want: list):
    L = _names_layer(spec)
    assert L is not None, [x.get("@@type") for x in spec.get("layers") or []]
    assert [r["name"] for r in L["data"]] == want                 # one label per polygon, the table's names
    assert L["sizeUnits"] == "meters" and L["sizeMaxPixels"] > 0 and L["contentCutoffPixels"][1] > 0
    assert L["getContentBox"] == "@@=box" and L["billboard"] is False and L["pickable"] is False


def test_the_plot_names_are_on_every_map_that_draws_the_plots(field, tmp_path, monkeypatch):
    """0.4.0: each plot's name is written inside it on the maps that draw the plot boundary, the same names as the
    small area table (its name column, else its number; 'name (2)' for a second polygon of one name): step 2's raw map
    for a path and for an upload, the clean map of step 5 and the small area's own map (step 4's clean map draws no
    plots); the line of each plot names it
    on the hover (a pickable line of its own, the field boundary's line left as it was)."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    poly = tmp_path / "named.geojson"
    want = _named_plots(field["shp"], poly)
    d.at.text_input(key="ff_path_b").input(field["boundary"])
    d.click("ff_use_b")
    pk = d.key("sa_path_", "text_input")
    d.at.text_input(key=pk).input(str(poly))
    d.run()
    d.open(2)
    spec = _deck_specs(d)[0]
    _check_names(spec, want)
    assert _plot_ring_names(spec) == set(want)
    assert all(r in _deck_paths(d)[0] for r in _rings(poly)) and len(_deck_paths(d)[0]) > len(want)
    assert "{plot}" in spec["tooltip"]["html"] and "{v}" in spec["tooltip"]["html"]
    # an upload in its place
    d.open(1)
    d.at.text_input(key=pk).input("")
    d.run()
    _uploader(d, "sa_up_").set_value([_geo(poly)])
    d.run()
    d.open(2)
    _check_names(_deck_specs(d)[0], want)
    # the clean map of step 5, then the small area's own map after Measure (the table's names)
    d.open(3)
    d.click("clean_one")
    d.open(4)
    assert _names_layer(_deck_specs(d)[0]) is None and not _plot_ring_names(_deck_specs(d)[0])
    d.open(5)
    _check_names(_deck_specs(d)[0], want)
    d.click(d.key("sa_go_"))
    S = d.at.session_state["cleaned"][tag]["R"]["small_area"]
    assert [p["name"] for p in S["polygons"]] == want
    specs = _deck_specs(d)
    sa_map = next(s for s in specs if any(L.get("id") == "sa-strips" for L in s.get("layers") or []))
    _check_names(sa_map, want)
    assert _names_layer(sa_map)["id"] == "sa-names"
    assert sum(1 for s in specs if _names_layer(s)) >= 2            # the clean map keeps its names too


def test_no_plot_boundary_draws_no_names_and_keeps_the_tooltip(field, tmp_path, monkeypatch):
    """Without a plot boundary the maps carry no name layer and the hover of a reading is 0.3.8's."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    d.open(2)
    spec = _deck_specs(d)[0]
    assert _names_layer(spec) is None and not _plot_ring_names(spec)
    assert spec["tooltip"]["html"].startswith("<b>") and spec["tooltip"]["html"].endswith(": {v}")


def test_hundreds_of_small_plots_get_labels_that_fit_and_hide_when_small(tmp_path):
    """A few hundred small plots: one label per plot (the numbered names), each sized in metres to fit inside its own
    plot along its long side (and its short side), capped in pixels and hidden below a size by the content box
    cut-off: they never flood the map. A long, narrow plot turned 30 degrees gets its label along its long side."""
    import ast
    import math
    from shapely import affinity
    from engine.clean import small_area as sa
    src = open(APP, encoding="utf-8").read()
    tree = ast.parse(src)
    keep = {"plot_marks", "PLOT_NAME_MAX_PX", "PLOT_NAME_EM", "PLOT_NAME_FILL", "PLOT_NAME_HIGH"}
    code = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name in keep:
            code.append(ast.get_source_segment(src, n))
        elif isinstance(n, ast.Assign):
            names = {getattr(t, "id", None) for t in getattr(n.targets[0], "elts", [n.targets[0]])}
            if names & keep:
                code.append(ast.get_source_segment(src, n))
    ns = {}
    exec("\n".join(code), ns)
    lat0, lon0, m = 51.8, -114.1, 111_320.0
    kx = m * math.cos(math.radians(lat0))

    def rect(x0, y0, w, h):
        return box(lon0 + x0 / kx, lat0 + y0 / m, lon0 + (x0 + w) / kx, lat0 + (y0 + h) / m)
    geoms = [rect(12 * i, 13 * j, 10, 11) for i in range(30) for j in range(10)]
    geoms.append(affinity.rotate(rect(400, 0, 60, 6), 30))
    path = tmp_path / "grid.geojson"
    gpd.GeoDataFrame({"Plot_Id": [None] * len(geoms)}, geometry=geoms, crs=4326).to_file(path, driver="GeoJSON")
    polys, _ = sa.read_polygons(str(path))
    M = ns["plot_marks"](polys)
    assert [x["name"] for x in M["labels"]] == [str(i) for i in range(1, 302)] == list(polys["name"])
    assert len(M["rings"]) == 301
    for x in M["labels"][:300]:                                   # about square (10 m east, 11 m north): level
        assert x["size"] * ns["PLOT_NAME_EM"] * len(x["name"]) <= ns["PLOT_NAME_FILL"] * 10.0 + 1e-6
        assert 0 < x["size"] <= ns["PLOT_NAME_HIGH"] * 11.0 + 1e-6
        assert abs(x["angle"]) < 1e-6
        b = x["box"]
        assert b[2] == b[3] == -2 * b[0] and b[2] > x["size"]
    last = M["labels"][300]
    assert 25 < last["angle"] < 50                                  # along the long side of the turned strip
    assert last["size"] <= ns["PLOT_NAME_HIGH"] * 6.0 + 1e-6
    # the cut-off: a name is hidden when its content box is under 2 k MIN px on screen (one k for the layer)
    k = M["labels"][0]["box"][2] / M["labels"][0]["size"] / 2
    assert all(abs(x["box"][2] / x["size"] / 2 - k) < 1e-9 for x in M["labels"])
    assert M["cutoff"] == pytest.approx(2 * k * 9)


# ------------------------------------------------------------------------------------- 0.4.0: the small area's units
def _df_config(d: Drive, column: str) -> tuple:
    """(the dataframe holding column, its column config) of the page."""
    import json
    for e in d.at.dataframe:
        if column in e.value.columns:
            return e, json.loads(e.proto.columns or "{}")
    raise AssertionError(column)


def test_the_small_area_tables_say_what_each_column_is_and_its_unit(field, tmp_path, monkeypatch):
    """0.4.0: every column of the small area table, of the table in detail and of the differences between the
    polygons has a header with its unit and a help on how it is computed; the numbers keep their decimals (yields two)
    and the table's own columns stay as they were; the CSV keeps the engine's header."""
    d = Drive(tmp_path / "ws", monkeypatch)
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    tag = d.at.session_state["active"]
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.at.number_input(key=d.key("sa_cv_", "number_input")).set_value(3.0)
    d.run()
    d.open(3)
    d.click("clean_one")
    d.open(5)
    d.click(d.key("sa_go_"))
    e, cfg = _df_config(d, "grain / ground")
    assert list(e.value.columns) == ["polygon", "grain / ground", "grain (bu)", "ground (ac)", "ground %",
                                     "cleaned map", "SMS query", "spread ± %", "calibration"]
    want = {"polygon": "Polygon", "grain / ground": "Yield, grain / ground (bu/ac)", "grain (bu)": "Grain (bu)",
            "ground (ac)": "Ground (ac)", "ground %": "Ground counted (%)",
            "cleaned map": "Yield, cleaned map average (bu/ac)", "SMS query": "Yield, as SMS's query (bu/ac)",
            "spread ± %": "Spread inside the polygon (± %)", "calibration": "Calibration range, 95 % (bu/ac)"}
    for c, lab in want.items():
        assert cfg[c]["label"] == lab and len(cfg[c].get("help") or "") > 20, (c, cfg[c])
    fmts = {c: (cfg[c].get("type_config") or {}).get("format") for c in cfg}
    assert fmts["grain / ground"] == fmts["cleaned map"] == fmts["SMS query"] == fmts["grain (bu)"] == "%.2f"
    assert fmts["ground (ac)"] == "%.3f" and fmts["ground %"] == "%.2f" and fmts["spread ± %"] == "%.2f"
    e2, cfg2 = _df_config(d, "total dry bu")
    assert all(cfg2[c].get("label") and cfg2[c].get("help") for c in e2.value.columns), cfg2
    assert cfg2["dry yield (bu/ac)"]["label"] == "Yield, dry, area-weighted (bu/ac)"
    assert all((cfg2[c].get("type_config") or {}).get("format") == "%.2f"
               for c in ("dry yield (bu/ac)", "mean (bu/ac)", "min", "max", "SD", "total dry bu", "moisture (%)"))
    assert cfg2["area (ac)"]["type_config"]["format"] == "%.3f"
    e3, cfg3 = _df_config(d, "difference (bu/ac)")
    assert all(cfg3[c].get("label") and cfg3[c].get("help") for c in e3.value.columns), cfg3
    # the CSV is the engine's (its bytes against the engine called directly: test_cleaning_and_small_area_bytes_...)
    from engine.clean import small_area as sa
    S = d.at.session_state["cleaned"][tag]["R"]["small_area"]
    with open(S["files"]["csv"], encoding="utf-8") as fh:
        assert fh.readline().strip().split(",") == sa.CSV_COLUMNS


def test_the_before_and_after_headers_say_their_units():
    """The headers of 'Before and after the edits by hand' (grain / ground and the cleaned map average), read from
    the app's source: each column with its unit and a help."""
    import ast
    src = open(APP, encoding="utf-8").read()
    tree = ast.parse(src)
    code = [ast.get_source_segment(src, n) for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "before_after_labels"]

    class _S:
        METHOD_HELP = {"cleaned": "the readings the cleaning kept"}
    ns = {"sarea": _S, "SA_POLYGON_HELP": "The polygon's name."}
    exec(code[0], ns)
    cols_g = ["polygon", "readings before", "readings after", "ground ac before", "ground ac after", "grain bu before",
              "grain bu after", "bu/ac before", "bu/ac after", "kept before", "kept after", "removed by hand before",
              "removed by hand after", "cleaned map average bu/ac before", "cleaned map average bu/ac after"]
    L = ns["before_after_labels"](cols_g, True)
    assert set(L) == set(cols_g)
    assert L["bu/ac before"][0] == "Yield, grain / ground, before (bu/ac)"
    assert L["ground ac after"][0] == "Ground, after (ac)" and L["grain bu before"][0] == "Grain, before (bu)"
    assert L["cleaned map average bu/ac after"][0] == "Yield, cleaned map average, after (bu/ac)"
    assert L["removed by hand before"][0] == "Removed by hand, before (readings)"
    cols_c = ["polygon", "readings before", "readings after", "ac before", "ac after", "bu before", "bu after",
              "bu/ac before", "bu/ac after"]
    L = ns["before_after_labels"](cols_c, False)
    assert set(L) == set(cols_c) and L["bu/ac after"][0] == "Yield, cleaned map average, after (bu/ac)"
    assert L["ac before"][0] == "Area, before (ac)" and all(len(h) > 10 for _, h in L.values())
