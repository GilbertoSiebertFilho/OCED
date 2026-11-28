# -*- coding: utf-8 -*-
"""0.4.0, the plots (small area) on synthetic data only:

E. the small area's map of step 5 has the look of the general map of steps 2 and 4: its readings are the general
   map's strip layer (strips_layer: 'polygon', 'rgb', 'v') on the general map's colour scale of the dry yield
   (rgba_of), its hover the general map's template (map_tooltip: '<b>Dry yield</b>: v', 'Plot <name>' on a plot's line)
   with the small area's lines after it in the same 'label: value' pattern; the general map's own hover is unchanged.
F. the report's small area section holds three images (the clean map with the plots, the readings inside the plots,
   the yield of every plot with its spread), drawn by small_area.run after the CSV and the zips, which they do not
   change; with many plots the names that would overlap or not fit are left out and the bars continue in more rows
   and figures; a report without plots has none of it; 'Remove the small area' removes the figures too.

    python -m pytest -q tests/test_v040_plots_figures.py
"""
from __future__ import annotations

import ast
import hashlib
import html as H
import os
import sys
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from engine import run as er  # noqa: E402
from engine.clean import small_area as sa  # noqa: E402
from engine.clean import small_area_figures as saf  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from engine.report.clean_report import make_report  # noqa: E402
from tests.synthetic import _rect, make_field  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")
TITLES = ("The plots on the clean map", "The readings inside the plots", "Yield of the plots")


def _app_defs(ns, *names):
    """Functions and module-level constants of app/oced.py by name, run into `ns`, without running the page."""
    tree = ast.parse(open(APP, encoding="utf-8").read())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in names)]
    exec(compile(ast.Module(nodes, []), APP, "exec"), ns)
    return ns


def _fn(name):
    tree = ast.parse(open(APP, encoding="utf-8").read())
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _calls(fn, callee):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == callee]


def _write_plots(path, names, geoms):
    gpd.GeoDataFrame({"name": names}, geometry=geoms, crs=4326).to_file(path, driver="GeoJSON")
    return path


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("p40"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:4000].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    out = os.path.join(d, "out")
    R = yc.run(shp, out, S, log=lambda m: None)
    four = _write_plots(os.path.join(d, "four.geojson"), ["North A", "Rate 120", "Check", "B&B <high>"],
                        [_rect(20, 110, 5, 40), _rect(150, 260, 5, 40), _rect(20, 110, 60, 110),
                         _rect(300, 420, 50, 120)])
    return {"R": R, "out": out, "four": four, "dir": d, "tag": os.path.basename(R["files"]["flagged_zip"])[
        :-len("_flagged.zip")]}


# ================================================================================================================ E
def test_the_small_area_map_draws_the_general_maps_strips_and_hover():
    """In the source: explorer (the general map) and small_area_map draw their readings with strips_layer and give
    their hover by map_tooltip; the small area's strips and parts are that layer (ids sa-strips / sa-parts)."""
    ex, sm = _fn("explorer"), _fn("small_area_map")
    assert _calls(ex, "strips_layer") and _calls(ex, "map_tooltip")
    ids = [c.args[1].value for c in _calls(sm, "strips_layer") if len(c.args) > 1]
    assert ids == ["sa-strips", "sa-parts"]
    mt = _calls(sm, "map_tooltip")
    assert len(mt) == 1 and {k.arg for k in mt[0].keywords} == {"plots", "more", "cls"}
    assert _calls(sm, "legend")                       # the general map's colour bar under it
    assert not [c for c in ast.walk(sm) if isinstance(c, ast.Constant) and c.value == "#0B1F44"]


def test_the_hover_template_is_the_general_maps():
    ns = _app_defs({"html": H}, "MAP_TIP_STYLE", "map_tooltip", "plot_tooltip", "SA_TIP_MORE", "SA_TIP_CLASS")
    # the general map's hover, as before 0.4.0 (without plots, and with them)
    assert ns["map_tooltip"]("Dry yield") == {"html": "<b>Dry yield</b>: {v}", "style": {
        "backgroundColor": "#00358E", "color": "white", "fontSize": "12px"}}
    gen = ns["plot_tooltip"]("Dry yield")
    assert gen["html"] == ('<span style="display:{hd}"><b>Dry yield</b>: {v}</span>'
                           '<span style="display:none;display:{pd}"><b>Plot</b> {plot}</span>')
    # the small area's: the general one (same box, same first line), its own lines after it, in its class
    sa_t = ns["map_tooltip"]("Dry yield", plots=True, more=ns["SA_TIP_MORE"], cls=ns["SA_TIP_CLASS"])
    assert sa_t["style"] == gen["style"]
    assert sa_t["html"] == f'<div class="oced-sa-tip">{gen["html"]}{ns["SA_TIP_MORE"]}</div>'
    for f in ("{st}", "{shl}", "{sh}", "{gg}", "{nr}", "{ck}"):
        assert f in ns["SA_TIP_MORE"]
    assert "<b>Reading</b>: {st}" in ns["SA_TIP_MORE"] and "<b>Grain / ground</b>: {gg}" in ns["SA_TIP_MORE"]


def test_strips_layer_is_one_layer_for_both_maps():
    import pydeck as pdk
    ns = _app_defs({"pdk": pdk, "pd": pd}, "strips_layer")
    df = pd.DataFrame({"polygon": [[[0, 0], [0, 1], [1, 1], [0, 0]]], "rgb": [[1, 2, 3, 220]], "v": ["1.00 bu/ac"]})
    gen = ns["strips_layer"](df)
    assert gen.type == "PolygonLayer" and gen.get_fill_color == "@@=rgb" and gen.stroked is False and gen.pickable
    sml = ns["strips_layer"](df.assign(line=[[0, 0, 0, 0]]), "sa-strips", line=True, auto_highlight=True)
    assert sml.id == "sa-strips" and sml.get_fill_color == "@@=rgb" and sml.get_line_color == "@@=line" and sml.stroked


def test_the_small_area_rows_are_on_the_general_maps_colour_scale(field):
    """Every reading drawn: its strip in rgba_of's colour of its dry yield (faint when kept; orange / purple / blue as
    before for one removed or left out), the part inside the line in that colour (strong), 'v' its yield as the
    general map's hover writes it (fmt_value: two decimals and bu/ac); the plot lines carry 'plot' and their sums."""
    import streamlit as st
    ns = _app_defs({"st": st, "sarea": sa, "np": np, "pd": pd, "html": H}, "small_area_map_data", "SA_MAP_MARGIN_M",
                   "SA_MAP_MAX", "SA_FILL", "SA_LINE", "SA_YIELD", "SA_STRIP_ALPHA", "ATTR_INFO",
                   "rgba_of", "fmt_value")
    fz = field["R"]["files"]["flagged_zip"]
    MD = ns["small_area_map_data"](fz, 0.0, field["four"], 0.0, "clip", "ground")
    M = sa.detail_of(fz, field["four"], "clip", margin_m=ns["SA_MAP_MARGIN_M"], method="ground")
    rows = sorted((0 if D["touch"][j] else 1, k, j) for k, p in enumerate(M["polygons"])
                  for D in [M["ground_rows"][p["name"]]] for j in range(len(D["idx"])))[:ns["SA_MAP_MAX"]]
    ys = np.array([float(M["ground_rows"][M["polygons"][k]["name"]]["yield"][j]) for _c, k, j in rows])
    st_ = [str(M["ground_rows"][M["polygons"][k]["name"]]["status"][j]) for _c, k, j in rows]
    rgb = ns["rgba_of"](ys, "num", "RdYlGn", MD["lo"], MD["hi"], None)
    assert ns["ATTR_INFO"]["Yld_Vol_Dr"] == ("Dry yield", "bu/ac", "RdYlGn")
    seen_kept = seen_removed = 0
    for s in MD["strips"]:
        i = s["c"]
        assert s["v"] == ns["fmt_value"](ys[i], "bu/ac") and s["v"].endswith(" bu/ac")
        if st_[i] == "kept":
            assert s["rgb"] == [int(x) for x in rgb[i][:3]] + [ns["SA_STRIP_ALPHA"]] and s["line"] == [0, 0, 0, 0]
            seen_kept += 1
        elif st_[i] == "removed":
            assert s["rgb"] == ns["SA_FILL"]["removed"] and s["line"] == ns["SA_LINE"]["removed"]
            seen_removed += 1
    assert seen_kept and seen_removed
    for q in MD["parts"]:
        assert q["rgb"] == [int(x) for x in rgb[q["c"]]] and "line" not in q      # no outline: the general map's
    assert {x["plot"] for x in MD["lines"]} == {"North A", "Rate 120", "Check", "B&B <high>"}
    for x in MD["lines"]:
        assert x["hd"] == "none" and x["pd"] == "inline" and x["gg"].endswith(" bu/ac") and x["ck"]


# ================================================================================================================ F
def _members(z):
    with zipfile.ZipFile(z) as f:
        return {n: hashlib.sha256(f.read(n)).hexdigest() for n in sorted(f.namelist())}


def test_the_figures_are_written_and_change_nothing_the_measure_writes(field, tmp_path, monkeypatch):
    fz = field["R"]["files"]["flagged_zip"]
    a, b = str(tmp_path / "with"), str(tmp_path / "without")
    rec = sa.run(fz, field["four"], a, "syn", "clip", log=lambda m: None, R=field["R"])
    F = {k: v for k, v in rec["files"].items() if k.startswith("fig_")}
    assert set(F) == {"fig_map", "fig_inside", "fig_bars_1"} and all(os.path.isfile(p) for p in F.values())
    assert all(isinstance(v, str) for v in rec["files"].values() if v)      # every value a path
    I = rec["figures"]
    assert I["n_plots"] == 4 and I["names_map"] == 4 and I["names_inside"] == 4 and I["bars"] == 1
    assert I["lo"] < I["mean"] < I["hi"] and I["n_kept"] > 0 and I["n_parts"] > 0
    # the same measure without the figures (a failure in them): the CSV and the zips are the same bytes
    log = []

    def boom(*_a, **_k):
        raise RuntimeError("no figures")
    monkeypatch.setattr(saf, "write_figures", boom)
    rec2 = sa.run(fz, field["four"], b, "syn", "clip", log=log.append, R=field["R"])
    assert "figures" not in rec2 and not [k for k in rec2["files"] if k.startswith("fig_")]
    assert any("figures could not be drawn" in m for m in log)
    with open(rec["files"]["csv"], "rb") as f1, open(rec2["files"]["csv"], "rb") as f2:
        assert f1.read() == f2.read()
    for k in ("zip", "parts_zip", "ground_zip"):
        assert _members(rec["files"][k]) == _members(rec2["files"][k]), k
    assert rec["polygons"] == rec2["polygons"]


def _pdf(path):
    import pymupdf
    doc = pymupdf.open(path)
    pages = [(p.get_text(), len(p.get_images())) for p in doc]
    doc.close()
    return pages


def test_the_report_section_holds_the_three_images(field, tmp_path):
    R = dict(field["R"])
    R["files"] = dict(R["files"])
    pdf0 = str(tmp_path / "no_plots.pdf")
    make_report(R, pdf0)
    text0 = " ".join(t for t, _n in _pdf(pdf0))
    assert not any(t in text0 for t in TITLES) and "Small area" not in text0
    R["small_area"] = sa.run(R["files"]["flagged_zip"], field["four"], str(tmp_path / "sa"), "syn", "clip",
                             log=lambda m: None, R=field["R"])
    pdf1 = str(tmp_path / "plots.pdf")
    make_report(R, pdf1)
    pages = _pdf(pdf1)
    text1 = " ".join(t for t, _n in pages)
    for t in TITLES:
        assert t in text1, t
    first = next(i for i, (t, _n) in enumerate(pages) if "Small area (cut after the cleaning)" in t)
    last = next(i for i, (t, _n) in enumerate(pages) if "The cleaned map average in detail" in t)
    assert sum(n for _t, n in pages[first:last + 1]) >= 3
    assert "Each plot's name is written inside it." in text1 and "the same colour is the same yield" in text1
    assert "bu/ac" in text1 and "spread inside the plot" in text1
    # the images come after the table of the figures and before the cleaned map average in detail
    assert text1.index("Yield of the plots") < text1.index("The cleaned map average in detail")
    # a small area measured before 0.4.0 (no figures in its record): the section as before, no image titles
    X = {k: v for k, v in R["small_area"].items() if k != "figures"}
    X["files"] = {k: v for k, v in X["files"].items() if not k.startswith("fig_")}
    pdf2 = str(tmp_path / "old.pdf")
    make_report(dict(R, small_area=X), pdf2)
    text2 = " ".join(t for t, _n in _pdf(pdf2))
    assert "Small area (cut after the cleaning)" in text2 and not any(t in text2 for t in TITLES)


def test_many_plots_wrap_and_names_that_do_not_fit_are_left_out(field, tmp_path):
    fl = sa._read_flagged(field["R"]["files"]["flagged_zip"])
    names, geoms = [], []
    for r in range(5):
        for c in range(13):                                # 65 small plots, 8 m squares, long names
            geoms.append(_rect(20 + c * 30, 20 + c * 30 + 8, 5 + r * 22, 5 + r * 22 + 8))
            names.append(f"Plot number {r * 13 + c + 1:03d}")
    polys, _ = sa.read_polygons(_write_plots(str(tmp_path / "many.geojson"), names, geoms))
    M = sa.measure_all(fl, polys, "clip", "ground")
    files, I = saf.write_figures(fl, M, str(tmp_path), "many")
    assert I["n_plots"] == 65 and I["names_map"] < 65 and I["names_inside"] < 65
    assert I["bars"] == 2 and saf.BARS_PER_ROW * saf.BAR_ROWS == 60
    assert set(files) == {"map", "inside", "bars_1", "bars_2"}
    # written again with fewer plots: the old figures of the tag are gone
    polys4, _ = sa.read_polygons(field["four"])
    files4, _I = saf.write_figures(fl, sa.measure_all(fl, polys4, "clip", "ground"), str(tmp_path), "many")
    assert not os.path.exists(files["bars_2"]) and sorted(saf.figure_paths(str(tmp_path), "many")) == \
        sorted(files4.values())


def test_the_caption_says_when_no_plot_name_fits():
    """The plot names sentence of a figure's caption: every name, some of them, or none ('0 of the 71' is not said)."""
    assert sa.plot_names_said(None, 71) == sa.plot_names_said(71, 71) == "Each plot's name is written inside it."
    assert sa.plot_names_said(12, 71).startswith("The names of 12 of the 71 plots are written inside them;")
    none = sa.plot_names_said(0, 71)
    assert none == "No plot name fits its plot at this scale; the table and the bar chart name every plot."
    assert "0 of" not in none


def test_remove_the_small_area_removes_the_figures(field, tmp_path):
    import shutil
    d = str(tmp_path / "copy")
    shutil.copytree(field["out"], d)
    R = {"files": {"flagged_zip": os.path.join(d, os.path.basename(field["R"]["files"]["flagged_zip"])), "dir": d},
         "tag": "syn"}
    rec = er.small_area_after_clean(R, field["four"], "clip", log=lambda m: None)
    figs = [v for k, v in rec["files"].items() if k.startswith("fig_")]
    assert figs and all(os.path.isfile(p) for p in figs)
    assert er.small_area_remove(R, log=lambda m: None)
    assert not any(os.path.exists(p) for p in figs)
