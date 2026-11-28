# -*- coding: utf-8 -*-
"""0.4.0: the harvest replay shows every yield with two decimals, the real value of the sum (engine/replay.py,
engine/replay_player.html), synthetic data only. The replay file stores each reading's yield (and the filtered yield
of a cleaning) at 0.01 bu/ac (Y_Q, said in the file as y_q); a file of an older version (no y_q) is read at 0.1; the
player writes the running bu/ac, the reading under the cursor, each combine's yield, the zones and the ramp's ends
with two decimals, and moisture, speed and percent keep theirs.

    python -m pytest -q tests/test_replay_two_decimals.py
"""
from __future__ import annotations

import os
import sys

import geopandas as gpd
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import replay as rp  # noqa: E402
from tests.synthetic import make_field  # noqa: E402


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    """The synthetic field with every yield at two decimals exactly (so the file's values are known)."""
    F = make_field(str(tmp_path_factory.mktemp("field")))
    g = gpd.read_file(F["shp"])
    g["Yld_Vol_Dr"] = np.round(g["Yld_Vol_Dr"].to_numpy(float), 2)
    out = os.path.join(os.path.dirname(F["shp"]), "two_decimals.shp")
    g.to_file(out, engine="pyogrio")
    return {"shp": out, "y": g["Yld_Vol_Dr"].to_numpy(float), "n": len(g)}


def _decoded(P) -> np.ndarray:
    return np.concatenate([rp.payload_columns(P, C)["y"] for C in P["combines"]])


def test_the_yield_is_stored_at_a_hundredth_and_reads_back_exactly(field):
    P = rp.replay_payload(field["shp"], kind="import")
    assert rp.Y_Q == 0.01 and P["y_q"] == 0.01 and P["thin"] == 1
    y = _decoded(P)
    assert len(y) == field["n"]
    # every reading's yield as in the file, to the hundredth (the file's values have two decimals)
    assert np.allclose(np.sort(y[np.isfinite(y)]), np.sort(field["y"]), atol=1e-9)
    # each value read back is the file's to the hundredth (a quantum of 0.1 moved them by up to 0.05): the running
    # bu/ac, grain over area with the replay's strips, ends on the field's figure to two decimals
    assert np.nanmax(np.abs(y * 100 - np.round(y * 100))) < 1e-6


def test_a_file_without_its_quantum_is_read_at_a_tenth(field):
    """A replay written before 0.4.0 has no y_q: its integers are tenths."""
    P = rp.replay_payload(field["shp"], kind="import")
    y = _decoded(P)
    P_old = dict(P)
    P_old.pop("y_q")
    assert np.allclose(_decoded(P_old), y * 10.0, equal_nan=True)


def test_a_cleaning_stores_its_yields_at_a_hundredth(field, tmp_path):
    """A cleaning's replay: each reading's yield is the flagged file's to the hundredth, and the filtered yield of the
    card (S5: the yield x Swath_Scl, carried where it differs) is stored on the same quantum."""
    import inspect
    import engine.run as er
    R = er.clean(field["shp"], str(tmp_path / "out"), None, log=lambda m: None)
    P = rp.replay_payload(R["files"]["flagged_shp"], kind="clean", rows=True)
    assert P["y_q"] == 0.01
    F = gpd.read_file(R["files"]["flagged_shp"])
    for C in P["combines"]:
        y = rp.payload_columns(P, C)["y"]
        want = np.maximum(F["Yld_Vol_Dr"].to_numpy(float)[np.asarray(C["rows"])], 0)
        ok = np.isfinite(want)
        assert np.nanmax(np.abs(y[ok] - want[ok])) <= 0.005 + 1e-9
    assert 'card["yf"] = (yld * np.nan_to_num(_num(g, "Swath_Scl"), nan=1.0), Y_Q)' in inspect.getsource(rp)


def test_the_player_writes_every_yield_with_two_decimals():
    """The player's text: the yield's quantum read from the file, and every yield written with two decimals."""
    with open(rp.PLAYER, encoding="utf-8") as fh:
        h = fh.read()
    assert "const YQ = P.y_q || 0.1;" in h
    assert "y[i] = y[i] < 0 ? NaN : y[i] * YQ;" in h and 'c.yf = dq("yf", YQ);' in h
    for s in ('$("y" + c.num).textContent = ok ? fmt(c.y[j], 2) : "—";',               # each combine's dry yield now
              '<b>${A > 0 ? fmt(B / A, 2) : "—"}</b><span>bu/ac so far<br>(area-weighted)</span>',  # the running bu/ac
              '<b>${fmt(A, 2)}</b><span>acres harvested</span>',                  # the area so far
              '<b>${fmt(B, 2)}</b><span>bushels (dry)</span>',                    # the bushels so far
              "const t = `all zones ${fmt(fieldY, 2)}`;",
              '$("zy" + k).textContent = zfmt(r.yield, 2);',
              "`· ${fmt(fieldY, 2)} bu/ac in the zones`",
              "<td><b>${zfmt(r.yield, 2)}</b></td><td>${zfmt(r.sd, 2)}</td>",         # the zone sheet
              "`<td>${by[z.label] ? fmt(by[z.label].yield, 2) : ",                    # per combine and zone
              "<b>${fmt(yv, 2)}</b> bu/ac${c.yf && Math.abs(c.yf[i] - c.y[i]) > 0.005 ? ` <i>(as filtered; "
              "logged ${fmt(c.y[i], 2)})</i>`",                                         # the reading's card
              '<span>${fmt(sc.lo, m === "yield" ? 2 : 1)}</span>',                    # the ramp's ends
              "if (fmt(R[k].yield, 2) !== fmt(f.yield, 2)) shown++;"):
        assert h.count(s) == 1, s
    # the running bu/ac is the area-weighted one (bushels over acres): its label says so (a tooltip does not show on a
    # phone) and its tooltip says why it can differ from the report's plain mean (0.4.0)
    assert h.count('<div class="val" title="Area-weighted: the bushels harvested so far over the acres harvested so '
                   'far') == 1
    assert "in the second decimal" not in h and "fmt(A, 1)" not in h and "fmt(B, 0)" not in h
    # no yield left with one decimal; moisture, speed and percent keep theirs
    for s in ("fmt(c.y[j], 1)", "fmt(B / A, 1)", "fmt(fieldY, 1)", "zfmt(r.yield, 1)", "zfmt(r.sd, 1)",
              "fmt(by[z.label].yield, 1)", "fmt(yv, 1)", "fmt(c.y[i], 1)", "fmt(R[k].yield, 1)"):
        assert s not in h, s
    assert 'fmt(c.m[j], 1)' in h and 'fmt(c.s[j], 1)' in h and 'fmt(pct, 1) + " %"' in h


def test_a_replay_file_still_opens(field, tmp_path):
    """The replay file written for download: one HTML page with the player and the payload, y_q inside."""
    P = rp.replay_payload(field["shp"], kind="import")
    h = rp.replay_html(P)
    assert h.lstrip().lower().startswith("<!doctype html") and '"y_q":0.01' in h.replace(" ", "")
    assert "const YQ = P.y_q || 0.1;" in h
