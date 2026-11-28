# -*- coding: utf-8 -*-
"""0.4.0: the plots in a step of their own (app/oced.py), through Streamlit's AppTest, synthetic data only, the app as
it runs (marker lazy_tabs: only the open tab is drawn). Six steps: 1 Files, 2 Raw map, 3 Cleaning, 4 Clean map (the
clean map with the field boundary, the replay with Edit points and Reprocess), 5 Plots (the clean map with the plot
boundary and its names, the small area cut: Measure, its tables, map and files, and a replay of the cleaning that
shows the plots), 6 Final files.

Step 5 without a plot boundary says so in one line and is not needed: its badge says so and the title bar counts the
other five (the action tree agrees); with a plot boundary given in step 1 the whole path (Measure in step 5, its
table, map data, downloads and the replay with the plots; then marks by hand and Reprocess in step 4, and the plots
measured again); step 5's own widgets keep their values over a change of tab; a planter file's steps 4 and 5 are one
line each and not needed ('n of 4');
and no text of the app names a wrong step (the strings read from the source, with the parts of a text built over
several lines joined).

    python -m pytest -q tests/test_app_plots_step.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic import make_applied, make_field  # noqa: E402
from tests.test_app_tabs import NAMES, Drive, _deck_paths, _deck_specs, _names_layer, _open, _poly, _rings  # noqa: E402

pytestmark = pytest.mark.lazy_tabs
APP_DIR = os.path.join(ROOT, "app")
NO_PLOTS = "No plot boundary given: give the polygon file in step 1, Plot boundary, to measure plots here."


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field_plots")))


def _badge(d: Drive, num: int) -> str:
    """The heading of step card num (its badge and tag), as HTML."""
    return next(h.proto.body for h in d.at.get("html") if f'id="oced-step-{num}"' in h.proto.body)


def _tree(d: Drive) -> str:
    return " ".join(str(c.value) for c in d.at.sidebar.caption)


def _iframe_payloads(d: Drive) -> list:
    out = []
    for e in list(d.at.get("iframe")) + list(d.at.get("i_frame")):
        src = getattr(e.proto, "srcdoc", "") or ""
        m = re.search(r'type="application/json">(.*?)</script>', src, re.S)
        if m:
            out.append(json.loads(m.group(1)))
    return out


def test_six_steps_and_only_the_open_one_drawn(field, tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    assert [lab.split(" · ", 1)[-1] for lab in d.labels] == NAMES == ["Files", "Raw map", "Cleaning", "Clean map",
                                                                       "Plots", "Final files"]
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.open(3)
    d.click("clean_one")
    seen = {}
    for n in range(1, 7):
        d.open(n)
        seen[n] = set(d.keys())
        assert f'id="oced-step-{n}"' in " ".join(h.proto.body for h in d.at.get("html"))
        assert not [h for h in d.at.get("html") if 'class="oced-step"' in h.proto.body
                    and f'id="oced-step-{n}"' not in h.proto.body]                      # one step card drawn
    assert any(k.startswith("sa_go_") for k in seen[5])
    assert not any(k.startswith("sa_go_") for n in (1, 2, 3, 4, 6) for k in seen[n])
    assert "clean_one" in seen[3] and "clean_one" not in seen[5]
    assert any(k.startswith("nw_go_") for k in seen[6]) and not any(k.startswith("nw_go_") for k in seen[5])
    assert "edits_remove" not in seen[5]


def test_step_5_without_a_plot_boundary_is_one_line_and_not_needed(field, tmp_path, monkeypatch):
    """No plot boundary: step 5 shows one line plus Back / Next, before and after the cleaning, never an error; its
    badge says 'not needed', the title bar counts the other five (its hover says why) and the action tree says not
    needed; step 4 names no plots."""
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, field["shp"])
    for cleaned in (False, True):
        if cleaned:
            d.open(3)
            d.click("clean_one")
        d.open(5)
        assert [i.value for i in d.at.info] == [NO_PLOTS]
        assert not d.at.error and not d.at.warning and not d.at.get("deck_gl_json_chart")
        assert "step_back_5" in d.keys() and "step_next_5" in d.keys()
        assert not [k for k in d.keys() if k.startswith(("sa_go_", "sa_rm_", "sa_chg_", "sa_dl_"))]
        b = _badge(d, 5)
        assert "oced-step-num skip" in b and "not needed" in b and "&#10003;" not in b
        p = d.progress()
        assert re.search(r">\d of 5 steps done<", p), p
        assert 'title="Step 5 (Plots) is not needed for this file: no plot boundary given in step 1."' in p
        assert "not needed: no plot boundary" in _tree(d)
    assert "5 of 5 steps done" in d.progress()                      # steps 1, 2, 3, 4 and 6
    d.open(4)
    assert not any("The plots of the plot boundary" in str(c.value) for c in d.at.caption)
    assert not any(k.startswith("sa_go_") for k in d.keys())
    # Next / Back from step 5 lead to steps 6 and 4
    d.open(5)
    d.click("step_next_5")
    assert d.open_step() == 6
    d.click("step_back_6")
    d.click("step_back_5")
    assert d.open_step() == 4


PLANTER_STEP_4 = ("A planter or sprayer file: its clean map is in step 3 (Cleaning); the edits by hand (here) and the "
                  "plots (step 5) are for harvest files.")


def test_a_planter_files_steps_4_and_5_are_one_line_and_not_needed(tmp_path, monkeypatch):
    """A planter file: steps 4 (Clean map) and 5 (Plots) are for harvest files. Each is one line, before and after
    the cleaning, its badge says 'not needed' (never ticked done), the title bar counts the other four ('n of 4', its
    hover names both steps) and the action tree says not needed."""
    A = make_applied(str(tmp_path / "planter"))
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, A["shp"])
    for cleaned in (False, True):
        if cleaned:
            d.open(3)
            d.click("clean_one")
            assert d.at.session_state["cleaned"][d.at.session_state["active"]]["kind"] == "a3"
        d.open(5)
        assert [i.value for i in d.at.info] == ["A planter or sprayer file: the plots are measured on harvest files; "
                                                "its clean map is in step 3 (Cleaning)."]
        assert not d.at.error and "step_back_5" in d.keys() and "step_next_5" in d.keys()
        b = _badge(d, 5)
        assert "oced-step-num skip" in b and "not needed" in b and "&#10003;" not in b, cleaned
        d.open(4)
        assert [i.value for i in d.at.info] == [PLANTER_STEP_4], cleaned           # the same line before the cleaning
        assert not d.at.error and "step_back_4" in d.keys() and "step_next_4" in d.keys()
        b = _badge(d, 4)
        assert "oced-step-num skip" in b and "not needed" in b and "&#10003;" not in b, cleaned
        p = d.progress()
        assert re.search(r">\d of 4 steps done<", p), p
        assert 'title="Steps 4 (Clean map) and 5 (Plots) are not needed for this file: a planter or sprayer file."' in p
        assert "not needed: no harvest file" in _tree(d)
    assert "4 of 4 steps done" in d.progress()                      # steps 1, 2, 3 and 6


def test_the_whole_path_with_the_plots_in_step_5_then_marks_in_step_4(tmp_path, monkeypatch):
    """A plot boundary given in step 1, the file cleaned: step 4 draws the clean map with no plots and says that they
    are in step 5; step 5 draws them, Measure there gives the table (with units), the small area's map and its
    downloads, the badge and the count say done (6 of 6), and its replay shows the plots (the polygons and grain /
    ground of the table that leads). Then marks by hand in step 4's replay and Reprocess: the plots are measured again
    on the new cleaning (with the figures before the edits), and step 5 shows the table before and after."""
    sys.path.insert(0, APP_DIR)
    import pyogrio
    import replay_view
    from engine import replay as rp
    from tests.synthetic_replay import make_two_at_once
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    poly = _poly(two["shp"], tmp_path / "plots.geojson")
    d = Drive(tmp_path / "ws", monkeypatch)
    _open(d, two["shp"])
    tag = d.at.session_state["active"]
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.open(3)
    d.click("clean_one")
    # step 4: the clean map without the plots, one line naming step 5
    d.open(4)
    assert _names_layer(_deck_specs(d)[0]) is None and _deck_paths(d)[0] == []      # no field boundary, no plots
    assert any("The plots of the plot boundary are in step 5 (Plots): their map, Measure, figures, files and replay."
               in str(c.value) for c in d.at.caption)
    # step 5: the plots drawn before Measure, the replay waits for Measure
    d.click("step_next_4")
    assert d.open_step() == 5 and "oced-step-num done" not in _badge(d, 5)
    assert _deck_paths(d)[0] == _rings(poly)
    assert any(str(c.value) == "Measure first: the replay of the cleaning with the plots follows here."
               for c in d.at.caption)
    assert not [k for k in d.at.session_state.filtered_state if str(k).startswith("replay_box_plots_")]
    d.click(d.key("sa_go_"))
    C = d.at.session_state["cleaned"][tag]
    S = C["R"]["small_area"]
    assert [p["name"] for p in S["polygons"]] == ["mid", "low"]
    k = d.key("sa_go_")[len("sa_go_"):]
    tab = next(e for e in d.at.dataframe if "grain / ground" in e.value.columns)
    cfg = json.loads(tab.proto.columns or "{}")
    assert cfg["grain / ground"]["label"] == "Yield, grain / ground (bu/ac)"
    assert any(e.value is not None and "total dry bu" in e.value.columns for e in d.at.dataframe)
    assert any(any(L.get("id") == "sa-strips" for L in s.get("layers") or []) for s in _deck_specs(d))
    dls = [str(b.key) for b in d.at.get("download_button")]
    assert f"sa_dl_{k}_0" in dls and f"sa_dl_{k}_1" in dls                     # the table (.csv) and the points
    assert f"sa_chg_{k}" in d.keys()                                            # Change in step 1
    assert "oced-step-num done" in _badge(d, 5) and "6 of 6 steps done" in d.progress()
    assert "small area measured: plots.geojson" in _tree(d)
    # the replay of step 5: a player of its own (no Edit points) with the plots of the table that leads
    box = next(x for x in d.at.session_state.filtered_state if str(x).startswith("replay_box_plots_"))
    d.at.session_state[box] = True
    d.run()
    P5 = [P for P in _iframe_payloads(d) if P.get("kind") == "clean"]
    assert len(P5) == 1 and not (P5[0].get("edit") or {}).get("ok")
    SP = P5[0]["small_area"]
    assert [x["name"] for x in SP["polygons"]] == ["mid", "low"]
    for x, p in zip(SP["polygons"], S["polygons"]):
        assert x["dry_yield_bu_ac"] == pytest.approx(p["ground"]["dry_yield_bu_ac"], rel=1e-12)
    assert not d.at.get("bidi_component")                                     # step 4's two-way player not drawn
    # step 4: marks by hand (as the player sends them) and Reprocess
    d.open(4)
    ck = next(x for x in d.at.session_state.filtered_state if str(x).startswith("replay_box_clean_"))
    d.at.session_state[ck] = True
    d.run()
    Pm = rp.replay_payload(C["flagged_shp"], kind="clean", record=C["R"], edit=True, max_bytes=rp.EDIT_MAX_BYTES)
    F = pyogrio.read_dataframe(C["flagged_shp"], read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    rm = []
    for Cb in Pm["combines"]:
        rm += [[Cb["num"], i] for i, r in enumerate(Cb["rows"]) if F.iloc[r]["Rem_By"] == ""][:3]
    d.at.session_state[ck] = True
    d.at.session_state[replay_view.marks_key(ck[len("replay_box_"):])] = {
        "token": Pm["edit"]["token"], "remove": rm[:3], "keep": [], "changed": 3}
    d.run()
    C1 = d.at.session_state["cleaned"][tag]
    assert C1["R"]["manual_edits"]["remove"]["readings_applied"] == 3
    S1 = C1["R"]["small_area"]
    assert S1["auto"] and S1["measured_after"] == C1["at"] and S1["before"]["polygons"]
    assert S1["before"]["edits"] != S1["edits"]
    # step 5: the plots measured again, the table before and after the edits
    d.open(5)
    assert any(e.value is not None and "bu/ac before" in e.value.columns for e in d.at.dataframe)
    assert "oced-step-num done" in _badge(d, 5) and "6 of 6 steps done" in d.progress()
    assert any("they are made in step 4's replay (Edit points)" in str(c.value) for c in d.at.caption)


def test_step_5s_own_widgets_keep_their_values_over_a_change_of_tab(field, tmp_path, monkeypatch):
    d = Drive(tmp_path / "ws", monkeypatch)
    poly = _poly(field["shp"], tmp_path / "plots.geojson")
    _open(d, field["shp"])
    d.at.text_input(key=d.key("sa_path_", "text_input")).input(poly)
    d.run()
    d.open(3)
    d.click("clean_one")
    d.open(5)
    kd = d.key("draw_plots_", "button_group")
    ka = d.key("attr_plots_", "button_group")
    d.at.session_state[kd] = "points"
    d.at.session_state[ka] = "Moisture__"
    d.run()
    d.click(d.key("sa_go_"))
    for n in (6, 4, 1):
        d.open(n)
        d.open(5)
        assert [w.value for w in d.at.button_group if w.key == kd] == ["points"]
        assert [w.value for w in d.at.button_group if w.key == ka] == ["Moisture__"]
    # step 4's map keeps its own choice
    d.open(4)
    k4 = d.key("draw_plot_", "button_group")
    assert [w.value for w in d.at.button_group if w.key == k4] == ["strips"]


# ------------------------------------------------------------------------------------------------ the step texts
def _texts(path: str) -> list:
    """(line, text) of every string of a source file, a text built with + or as an f-string joined into one (a
    string cut over two lines between 'step ' and its number is one text here), each branch of a conditional
    expression kept apart."""
    tree = ast.parse(open(path, encoding="utf-8").read())

    def flat(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return [n.value]
        if isinstance(n, ast.JoinedStr):
            parts = [[x.value] if isinstance(x, ast.Constant) else (flat(x.value) or ["{}"]) for x in n.values]
            out = [""]
            for p in parts:
                out = [a + b for a in out for b in p][:64]
            return out
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            a, b = flat(n.left), flat(n.right)
            if a or b:
                return [x + y for x in (a or ["{}"]) for y in (b or ["{}"])][:64]
        if isinstance(n, ast.IfExp):
            return (flat(n.body) or []) + (flat(n.orelse) or [])
        return None
    out, seen = [], set()
    for n in ast.walk(tree):
        if id(n) in seen or not isinstance(n, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.IfExp)):
            continue
        t = flat(n)
        if not t:
            continue
        for m in ast.walk(n):
            seen.add(id(m))
        out += [(n.lineno, x) for x in t]
    return out


STEP = r"\bsteps?\s+(?:\d\s*(?:,|and|to|or)\s*)*{n}\b"
FINAL_WORDS = ("DIFM", "Final files", "report", "raw format", "monitor's format", "clean shapefile", "hands out",
               "native", "Write it again", "ISOXML set")
PLOT_WORDS = ("small area", "Measure", "plot boundary", "polygon", "plots")


def test_no_text_of_the_app_names_a_wrong_step():
    """Every text of the app (app/oced.py, app/replay_view.py, app/brand.py: captions, helps, toasts, the action
    tree, docstrings) names the steps of the six-step layout: no 'steps 1 to 5' or 'five steps'; a sentence naming
    step 5 says nothing of the final files (DIFM, the report, the raw formats ...); one naming step 6 says nothing of
    the plots; one naming step 4 with Measure or the small area also speaks of the edits (their Reprocess measures
    the plots again)."""
    bad = []
    for f in ("oced.py", "replay_view.py", "brand.py"):
        for ln, t in _texts(os.path.join(APP_DIR, f)):
            flat = " ".join(t.split())
            for wrong in ("steps 1 to 5", "five steps", "the five steps", "of 5 steps done"):
                if wrong in flat.replace("'n of 5'", "") and "0.3." not in flat:
                    bad.append((f, ln, wrong, flat[:160]))
            for sent in re.split(r"(?<=[.;])\s+", flat):
                if "0.3." in sent or "0.4.0's check" in sent:              # an earlier layout named as such
                    continue
                low = sent.lower()
                if re.search(STEP.format(n=5), sent, re.I) and any(w.lower() in low for w in FINAL_WORDS):
                    bad.append((f, ln, "step 5 + final files", sent[:200]))
                if re.search(STEP.format(n=6), sent, re.I) and any(w.lower() in low for w in PLOT_WORDS):
                    bad.append((f, ln, "step 6 + plots", sent[:200]))
                if (re.search(STEP.format(n=4), sent, re.I) and any(w.lower() in low for w in ("measure", "small area"))
                        and not any(w in low for w in ("edit", "reprocess"))):
                    bad.append((f, ln, "step 4 + small area", sent[:200]))
    assert not bad, "\n".join(map(str, bad))
    # the STEPS list drives the tabs: six, the plots fifth, the final files sixth
    tree = ast.parse(open(os.path.join(APP_DIR, "oced.py"), encoding="utf-8").read())
    steps = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                 and getattr(n.targets[0], "id", None) == "STEPS")
    assert [(s[0], s[1], s[2]) for s in steps] == [("files", 1, "Files"), ("raw", 2, "Raw map"),
                                                   ("clean", 3, "Cleaning"), ("cleanmap", 4, "Clean map"),
                                                   ("plots", 5, "Plots"), ("final", 6, "Final files")]
