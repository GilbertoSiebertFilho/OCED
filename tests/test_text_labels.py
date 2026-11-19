# -*- coding: utf-8 -*-
"""Labels that say what a number is (synthetic data only; no number of the clean file changes): the command line's
final-map line gives the SMS Summary's area-weighted average next to the plain point mean; the swath step's counts
are named as the swath step's; the final map's SD is the population SD, as SMS's Edit Legend; the no-machine-id
warning counts the dataset names and the logs (record-id restarts) apart and says what 'task' filters.

    python -m pytest -q tests/test_text_labels.py
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import sys

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import sms3sigma as sms  # noqa: E402
from engine.report import clean_report as cr  # noqa: E402
from tests.synthetic import make_field  # noqa: E402


def test_the_command_line_labels_the_average_the_swath_counts_and_the_sd(tmp_path):
    F = make_field(str(tmp_path / "f"))
    work = str(tmp_path / "w")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert er.main([F["shp"], "--out", work, "--aoi", F["boundary"], "--tag", "lab"]) == 0
    txt = out.getvalue()
    R = json.load(open(glob.glob(os.path.join(work, "output*", "lab*_cleaning.json"))[0], encoding="utf-8"))
    fm = R["final_map"]
    line = next(ln for ln in txt.splitlines() if ln.strip().startswith("final map"))
    assert (f"average {fm['average_area_weighted']:,.2f} bu/ac (total / area, as the SMS Summary's Avg. Yield), plain "
            f"point mean {fm['mean']:,.2f} bu/ac over {fm['n_points']:,} points") in line
    meth = next(ln for ln in txt.splitlines() if ln.strip().startswith("method"))
    assert "swath step (before the 3-sigma filters)" in meth
    # the SD of the final map: the population SD of the clean file's column, as SMS's Edit Legend
    v = pyogrio.read_dataframe(R["files"]["difm_ready_shp"], columns=[fm["column"]], read_geometry=False)
    v = pd.to_numeric(v[fm["column"]], errors="coerce").to_numpy(float)
    assert fm["sd"] == pytest.approx(float(np.nanstd(v, ddof=0)), rel=1e-12) and "ddof 0" in fm["sd_rule"]
    assert "the swath step's count" in " ".join(R["notes"])
    # every note is plain text (no code fragment left by a missing f prefix); the clean-file note names the width
    assert not any("{" in n or "}" in n for n in R["notes"])
    assert any(f"carry the new width in {R['columns']['width_ft']} and sit" in n for n in R["notes"])
    assert cr._sms_swath_text(R).startswith("in the swath step, before the 3-sigma filters: ")


def test_the_no_machine_warning_counts_names_and_logs():
    one = pd.Series(["TaskName 1/2/2000 (GreenStar 4 Monitor)"] * 10)
    w = sms.no_machine_warning(one, 4, True)
    assert "its 1 dataset name, 4 logs (the record id restarts) carry no differing source" in w
    assert "'task' filters each log on its own, which may be one combine on one day" in w
    w = sms.no_machine_warning(pd.Series(["a", "b", "a"]), 2, False)
    assert "its 2 dataset names carry" in w and "'task' filters each dataset on its own" in w
    assert "no machine column and no dataset column" in sms.no_machine_warning(None, 1, False)
    # one dataset name and one log: nothing for 'task' to split, so no word about it
    w = sms.no_machine_warning(one, 1, False)
    assert "its 1 dataset name carries no differing source" in w and "'task'" not in w and w.endswith("machine column")


def test_the_app_map_panel_gives_the_population_sd():
    """The map panel of the app (app/oced.py stats_of) gives the same SD as final_map.sd: the population SD, as SMS's
    Edit Legend, and its row says so."""
    import ast
    app = os.path.join(ROOT, "app", "oced.py")
    src = open(app, encoding="utf-8").read()
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "stats_of")
    ns = {"np": np}
    exec(compile(ast.Module([fn], []), app, "exec"), ns)
    v = np.array([61.0, 55.0, 70.0, 64.0, np.nan])
    S = ns["stats_of"](v)
    assert S["sd"] == pytest.approx(float(np.std(v[:4], ddof=0)), rel=1e-12)
    assert 'SD_LABEL = "SD (population, as SMS)"' in src and "(SD_LABEL, fmt_value(S[\"sd\"], unit))" in src
