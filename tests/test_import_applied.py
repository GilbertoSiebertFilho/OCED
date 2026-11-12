# -*- coding: utf-8 -*-
"""The planter / sprayer / point-data cleaning (engine/clean/applied3s.py) and its report, on synthetic data only:
the counts of the boundary, the repeat pass per group, attributes with negative values, missing values, and the
operation of a drill that logs seed by mass.

    python -m pytest -q tests/test_import_applied.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.clean import applied3s as a3  # noqa: E402
from tests.synthetic import make_applied, make_field  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    return make_field(str(tmp_path_factory.mktemp("field")))


def _quiet(m):
    return None


def _rewrite(shp, out, fn):
    """A copy of a point shapefile with fn(GeoDataFrame) applied."""
    import geopandas as gpd
    g = gpd.read_file(shp)
    g = fn(g)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    g.to_file(out, engine="pyogrio")
    return out


def _pdf_text(path):
    try:
        import fitz                                      # pymupdf, when installed
    except ImportError:
        return None
    with fitz.open(path) as d:
        return " ".join(" ".join(p.get_text().split()) for p in d)


def test_boundary_counts_are_those_of_the_boundary(field, tmp_path):
    """Readings outside the boundary that S0 removed first still count as outside: n_inside is every reading inside,
    removed_pct is of those, and the S1 row says how many outside readings S0 had already taken."""
    A = make_applied(str(tmp_path / "data"), "seeding")
    R = a3.run(A["shp"], str(tmp_path / "out"), {}, boundary=field["boundary"], tag="syn", log=_quiet)
    rows = {r["filter"]: r for r in R["cascade"]}
    n_out = A["n"] - A["n_inside"]
    assert R["boundary"]["n_outside"] == R["n_outside"] == n_out
    assert R["n_inside"] == A["n_inside"]
    assert rows["S0"]["removed"] == A["n_zero"]
    before = R["boundary"]["n_outside_s0"]
    assert before > 0 and rows["S1"]["removed"] == n_out - before
    assert f"{before:,} more outside were already removed by S0" in rows["S1"]["criterion"]
    assert R["removed_pct"] == pytest.approx(100 * (1 - R["n_kept"] / A["n_inside"]))
    assert R["n_in"] == A["n"] - rows["S1"]["removed"]          # the older key, unchanged
    text = _pdf_text(R["files"]["report_pdf"])
    if text is not None:
        assert f"{R['n_kept']:,} of {A['n_inside']:,} inside the boundary" in text
        assert f"{before:,} of them already removed by S0" in text
    # the clip switched off with a boundary given: said so in the steps and in the report
    R2 = a3.run(A["shp"], str(tmp_path / "out2"), {"clip": False}, boundary=field["boundary"], tag="syn2", log=_quiet)
    s1 = next(r for r in R2["cascade"] if r["filter"] == "S1")
    assert s1["criterion"] == "switched off" and R2["n_inside"] == A["n"]
    text = _pdf_text(R2["files"]["report_pdf"])
    if text is not None:
        assert "switched off" in text and "no boundary given" not in text


def test_repeat_pass_per_group(tmp_path):
    """Two planters, the second without rate spikes: its main attribute is filtered again only when its own SD fell
    by more than 25 %, so it keeps what it keeps when cleaned alone."""
    A = make_applied(str(tmp_path / "data"), "seeding", seed=5)
    df = A["df"]
    second = (np.arange(len(df)) % 2) == 1
    rate = df["Rt_Apd_Ct_"].to_numpy(float)
    spikes = rate > 50_000

    def two(g):
        g = g.copy()
        g["Machine"] = np.where(second, "PLANTER-2", "PLANTER-1")
        r = np.array(g["Rt_Apd_Ct_"], dtype=float)
        r[second & spikes] = 32_000.0                          # planter 2: no spikes
        g["Rt_Apd_Ct_"] = r
        return g
    both = _rewrite(A["shp"], str(tmp_path / "two" / "two.shp"), two)
    R = a3.run(both, str(tmp_path / "o_both"), {}, tag="both", log=_quiet)
    assert R["grouping"]["mode"] == "machine"
    pbg = R["passes_by_group"]
    assert pbg["PLANTER-1"] >= 2 and pbg["PLANTER-2"] == 1 and R["passes"] == max(pbg.values())
    alone = _rewrite(both, str(tmp_path / "p2" / "p2.shp"), lambda g: g[g["Machine"] == "PLANTER-2"].copy())
    R2 = a3.run(alone, str(tmp_path / "o_p2"), {}, tag="p2", log=_quiet)
    kept = pyogrio.read_dataframe(R["files"]["clean_shp"], read_geometry=False)
    assert int((kept["Machine"] == "PLANTER-2").sum()) == R2["n_kept"]
    later = [r for r in R["steps"] if r["attribute"] == "Rt_Apd_Ct_" and r["step"][-1] != "a"]
    assert later and all(r["group"] == "PLANTER-1" for r in later)


def test_negative_attribute_and_missing_values(tmp_path):
    """An attribute with negative values is not floored at 0 (about 99.7 % of N(0, 1) kept), point data has no S0
    minimum by default and no 'no product applied', and a missing value is not removed by its step (as the harvest's
    sms3sigma.sigma_step), counted apart and warned about."""
    A = make_applied(str(tmp_path / "data"), "seeding", seed=9)
    rng = np.random.default_rng(4)

    def extra(g):
        g = g.copy()
        g["Offset_m"] = rng.normal(0.0, 1.0, len(g))
        s = np.array(g["Speed_mph_"], dtype=float)
        s[:40] = np.nan
        g["Speed_mph_"] = s
        return g
    shp = _rewrite(A["shp"], str(tmp_path / "neg" / "neg.shp"), extra)
    R = a3.run(shp, str(tmp_path / "o1"), {"attributes": ["Offset_m"], "repeat": "Offset_m", "max_passes": 1},
               tag="neg", log=_quiet)
    s2 = next(r for r in R["steps"] if r["attribute"] == "Offset_m")
    assert s2["lo"] < -2.5 and R["n_kept"] / R["n_read"] > 0.99
    assert "floored at 0" not in R["rule"]
    s0 = next(r for r in R["cascade"] if r["filter"] == "S0")
    assert "no product applied" not in s0["criterion"] and "<=" not in s0["criterion"]
    assert s0["removed"] == 0 and R["settings"]["min_value_used"] is None
    # the default attributes (rate + speed): the 40 readings with no speed are kept by the speed step, said so
    R2 = a3.run(shp, str(tmp_path / "o2"), {}, tag="spd", log=_quiet)
    sp = next(r for r in R2["cascade"] if r["filter"] == "S2")
    s0 = next(r for r in R2["cascade"] if r["filter"] == "S0")
    assert "no product applied" in s0["criterion"]
    miss = sum(r["n_missing"] for r in R2["steps"] if r["step"] == "S2")
    assert 0 < miss <= 40 and f"({miss:,} with no value, not filtered on Speed_mph_)" in sp["criterion"]
    assert sum(f"S2: {miss:,} reading(s) have no Speed_mph_ value" in w for w in R2["warnings"]) == 1
    fl = pyogrio.read_dataframe(R2["files"]["flagged_shp"], read_geometry=False)
    no_speed = ~np.isfinite(fl["Speed_mph_"].to_numpy(float))
    assert no_speed.sum() == 40 and not (fl.loc[no_speed, "Rem_By"] == "S2").any()
    assert "floored at 0 for Speed_mph_, Rt_Apd_Ct_" in R2["rule"]


def test_seeding_by_mass_is_seeding(tmp_path):
    """A drill logging seed by mass (Rt_Apd_Ms_) with a crop as product is seeding; with a fertilizer it stays an
    application; with no product values the label says it can be either."""
    A = make_applied(str(tmp_path / "data"), "seeding", seed=3)

    def by_mass(product):
        def fn(g):
            g = g.rename(columns={"Rt_Apd_Ct_": "Rt_Apd_Ms_", "Rt_Tgt_Ct_": "Rt_Tgt_Ms_"}).copy()
            g["Rt_Apd_Ms_"] = g["Rt_Apd_Ms_"].astype(float) / 250.0
            g["Product"] = product
            return g
        return fn
    cols = ["Product", "Rt_Apd_Ms_", "Rt_Tgt_Ms_", "Speed_mph_"]
    assert a3.detect_operation(cols)["label"] == a3.LABEL_BY_MASS
    for product, op in (("Wheat - Synthetic variety", "seeding"), ("Synthetic 46-0-0", "application")):
        shp = _rewrite(A["shp"], str(tmp_path / op / "m.shp"), by_mass(product))
        R = a3.run(shp, str(tmp_path / ("o_" + op)), {}, tag=op, log=_quiet)
        assert R["operation"] == op and R["main"] == "Rt_Apd_Ms_"
        assert R["operation_label"] == a3.OPERATION_LABEL[op]
