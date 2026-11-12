# -*- coding: utf-8 -*-
"""The Case IH / New Holland card decoder (engine/formats/cnh_cn1.py) on synthetic cards: tasks without their log are
not units, the copy of a task that is kept, the pre-selected season, the summary of a single-point curve, of the
latest calibration and of a short .tsh, the crop number's SMS product, and a card written in capitals.

    python -m pytest -q tests/test_dec_cnh.py
"""
from __future__ import annotations

import os
import struct
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import cnh_cn1 as cn  # noqa: E402
from tests.test_cnh_cn1 import (APP, LINEAR, OPTS, STAMP, _card, _crop_table, _record, _tlh, _tlo,  # noqa: E402
                                _tsh)

QUIET = dict(log=lambda m: None)


def _tso(name, n_log, area_m2, when=STAMP, crop=48, op=b"Grain Harv", vehicle="SYN00001"):
    p = bytearray(199)
    p[0:len(name)] = name.encode()
    p[19:25] = bytes(when)
    p[33:33 + len(op)] = op
    p[52] = crop
    p[53:53 + len(vehicle)] = vehicle.encode()
    struct.pack_into("<hh", p, 159, 52, -113)
    struct.pack_into("<I", p, 163, n_log)
    struct.pack_into("<I", p, cn.TSO_AREA, int(round(area_m2 * 100)))
    return _record(bytes(p))


def _logged(n=4, when=STAMP, crop=48, name=None):
    name = name or "{:02d}/{:02d}/{:02d}-{:02d}:{:02d}:{:02d}".format(when[0] - 30, *when[1:])
    return {"tso": _tso(name, n, 10_000.0, when=when, crop=crop),
            "tsh": _tsh(LINEAR, seconds=[0, 0, n], counts=[0, 0, 2500 * n], kg=100, moisture_sum=1400),
            "tlo": b"".join(_tlo(i + 1, i, 10, 1000) for i in range(n)),
            "tlh": b"".join(_tlh(i + 1, 2500) for i in range(n))}


def _totals_only(n=300, when=STAMP, **kw):
    return {"tso": _tso("26/07/02-09:30:00", n, 20_000.0, when=when, **kw),
            "tsh": _tsh(LINEAR, seconds=[0, 0, n], counts=[0, 0, 2500 * n], kg=1500, moisture_sum=18_000)}


def test_tasks_without_their_log_are_not_units_and_never_selected(tmp_path):
    """V-cnh-1: a task whose log is not on the card is not listed, so neither the field path of select_units nor
    'all' can take it; totals_only_tasks lists it for the field and season of the units; the latest harvest year is
    pre-selected, an older one is not."""
    old = (55, 7, 1, 12, 0, 0)                                # 2025
    root = _card(tmp_path, {"TASK0001": _logged(), "TASK0002": _totals_only(), "TASK0003": _logged(when=old),
                            "TASK0004": _totals_only(when=old)})
    units = cn.list_units(root)
    assert sorted(u.id.split("/")[-1] for u in units) == ["TASK0001", "TASK0003"]
    assert {u.id.split("/")[-1]: (u.year, u.default) for u in units} == {"TASK0001": (2026, True),
                                                                        "TASK0003": (2025, False)}
    sel, _ = er.select_units(units, "Synthetic field", None, None, False)
    assert [u.id.split("/")[-1] for u in sel] == ["TASK0001"]          # the field's latest season
    sel, _ = er.select_units(units, "Synthetic field", None, None, True)
    assert sorted(u.id.split("/")[-1] for u in sel) == ["TASK0001", "TASK0003"]      # 'all': still no totals-only
    only = cn.totals_only_tasks(root)
    assert sorted((t["task"], t["year"]) for t in only) == [("TASK0002", 2026), ("TASK0004", 2025)]
    u26 = next(u for u in units if u.year == 2026)
    assert [t["task"] for t in cn.totals_only_tasks(root, [u26.id])] == ["TASK0002"]
    _, rep = cn.decode(root, [u26.id], OPTS, **QUIET)
    assert [d["task"] for d in rep["sms_summary"]["datasets"]] == ["TASK0001"] and rep["totals_only_tasks"] == []
    _, rep = cn.decode(root, [u26.id], OPTS, totals_only="field", **QUIET)
    assert [d["task"] for d in rep["sms_summary"]["datasets"]] == ["TASK0001", "TASK0002"]
    t4 = next(t["id"] for t in only if t["task"] == "TASK0004")
    _, rep = cn.decode(root, [u26.id], OPTS, totals_only=[t4], **QUIET)
    assert [d["task"] for d in rep["sms_summary"]["datasets"]] == ["TASK0001", "TASK0004"]
    with pytest.raises(ValueError, match="not a task with totals only"):
        cn.decode(root, [u26.id], OPTS, totals_only=[u26.id], **QUIET)
    with pytest.raises(ValueError, match="totals_only must be"):
        cn.decode(root, [u26.id], OPTS, totals_only="all", **QUIET)


def test_one_copy_per_task_prefers_the_log_then_the_most_records():
    """_one_per_task: a copy with the task's log beats one with its totals only, then the copy with more logging
    records, then a complete card; the task id is compared without case."""
    def row(card, n_log, has_log=True, complete=True, task="TASK0001"):
        return dict(id=f"{card}::{task}", vehicle="SYN00001", task=task, has_log=has_log, n_log=n_log,
                    card_complete=complete)
    out = cn._one_per_task([row("A", 300, has_log=False), row("B", 200)])
    assert [(r["id"], r["copies"]) for r in out] == [("B::TASK0001", 2)]
    out = cn._one_per_task([row("A", 100), row("B", 150, task="task0001"), row("C", 150, complete=False)])
    assert [(r["id"], r["copies"]) for r in out] == [("B::task0001", 3)]
    out = cn._one_per_task([row("A", 150, complete=False), row("B", 150)])
    assert out[0]["id"] == "B::TASK0001"


def test_catalogue_keeps_only_harvest_tasks_with_totals_when_the_log_is_missing(tmp_path):
    """The catalogue: a task without logging records is left out; without its log, only a grain-harvest task with an
    area and a .tsh stays (as totals only); a task with its log is a unit."""
    no_rec = _logged()
    no_rec["tso"] = _tso("26/07/01-12:00:00", 0, 10_000.0)
    other_op = _totals_only(op=b"Tillage   ")
    no_area = {"tso": _tso("26/07/02-10:00:00", 50, 0.0), "tsh": _tsh(LINEAR)}
    no_tsh = {"tso": _tso("26/07/02-11:00:00", 50, 5000.0)}
    root = _card(tmp_path, {"TASK0001": _logged(), "TASK0002": no_rec, "TASK0003": other_op, "TASK0004": no_area,
                            "TASK0005": no_tsh, "TASK0006": _totals_only()})
    rows, cards = cn.catalogue(root)
    assert len(cards) == 1
    assert sorted((r["task"], r["has_log"]) for r in rows) == [("TASK0001", True), ("TASK0006", False)]
    assert [u.id.split("/")[-1] for u in cn.list_units(root)] == ["TASK0001"]
    assert [t["task"] for t in cn.totals_only_tasks(root)] == ["TASK0006"]
    r = next(r for r in rows if r["task"] == "TASK0001")
    assert set(r["files"]) == set(cn.TASK_EXTS) and r["files"][".tst"] is None and r["files"][".tlo"]


def test_summary_of_a_single_point_curve():
    """bins_wet_lb on a single-point calibration [1000, 2600, 1000, ...]: the flow is the line of segment 0-1 extended
    (not folded back to zero above point 1), as flow_lb_s reads it."""
    curve = np.array([1000, 2600] + [1000] * 9, float)
    assert cn.curve_last_point(curve) == 1
    u = 2.5 * (1 + 0.0075 * (14.0 - 12.0))                     # mean count 2,500, moisture 12 %
    flow = (1000 + u * (2600 - 1000) - 1000) / 100
    assert cn.bins_wet_lb([0, 0, 40], [0, 0, 100_000], 12.0, curve, 75) == pytest.approx(40 * flow)
    assert cn.flow_lb_s([2500.0], [12.0], curve, 75)[0][0] == pytest.approx(flow)
    assert cn.bins_wet_lb([5], [5000], None, np.full(11, 1000.0), 75) == 0.0        # no defined point: no mass


def test_summary_uses_the_curve_of_the_calibration_option(tmp_path):
    """calibration='latest': the Summary weight is the bins on the crop's current curve (.ycc), not the task's."""
    root = _card(tmp_path, {"TASK0001": _logged(n=10)})
    _crop_table(root)
    newer = [1000 + 1200 * k for k in range(11)]               # 12 lb/s per 1000 counts instead of 10
    p = bytearray(cn.YCC_LEN)
    struct.pack_into("<11H", p, 0, *newer)
    p[46] = 75
    with open(os.path.join(root, "SYNTH001.cn1", "COMBINES", "SYN00", "SYN00.ycc"), "wb") as f:
        f.write(_record(bytes(p), struct.pack("<I", 48)))
    u = cn.list_units(root)
    _, rt = cn.decode(root, [u[0].id], OPTS, **QUIET)
    _, rl = cn.decode(root, [u[0].id], OPTS, calibration="latest", **QUIET)
    k = 1 + 0.0075 * (14.0 - 14.0)                             # average moisture 1,400 / 100 = 14 %
    assert rt["sms_summary"]["datasets"][0]["wet_lb"] == pytest.approx(10 * 25.0 * k)
    assert rl["sms_summary"]["datasets"][0]["wet_lb"] == pytest.approx(10 * 30.0 * k)
    assert any("current calibration" in w and "not applied" in w for w in rt["warnings"])


def test_a_short_tsh_gives_a_summary_without_weight(tmp_path):
    """A .tsh payload shorter than 104 bytes (older software, cut file): the task decodes, its Summary has the area
    and no weight, moisture or volume."""
    t = _logged()
    full = _tsh(LINEAR, seconds=[0, 0, 4], counts=[0, 0, 10_000], kg=100, moisture_sum=1400)
    t["tsh"] = _record(full[cn.HDR:cn.HDR + 100])              # the display's kg, not the bins nor the moisture
    root = _card(tmp_path, {"TASK0001": t})
    u = cn.list_units(root)
    df, rep = cn.decode(root, [u[0].id], OPTS, **QUIET)
    d = rep["sms_summary"]["datasets"][0]
    assert len(df) == 4 and d["area_ac"] == pytest.approx(10_000.0 / 4046.8564224)
    assert d["wet_lb"] is None and d["dry_bu"] is None and d["moisture_pct"] is None
    assert d["display_wet_lb"] == pytest.approx(100 * 2.20462262185)
    assert rep["sms_summary"]["total"]["decoded_readings"] == 4


def test_crop_number_gives_the_sms_product(tmp_path):
    """The card holds the crop as a number: 47 is SMS's 'Wheat - Durum' (crop key durum) even where the card's crop
    table says 65 lb/bu; the report names the product, and a card has no monitor product of its own."""
    root = _card(tmp_path, {"TASK0001": _logged(crop=47)})
    _crop_table(root, test_weight=65.0, std_moisture=14.5)
    u = cn.list_units(root)
    assert u[0].crop == "durum" and "Wheat - Durum" in u[0].label
    df, rep = cn.decode(root, [u[0].id], None, **QUIET)
    assert rep["crop_name"] == "Wheat - Durum" and rep["crop_names"] == ["Wheat - Durum"]
    assert rep["monitor_product"] is None and set(df.Product) == {"Wheat - Durum"}
    assert cn.CROP_NAMES[48] == ("Wheat - Spring", "wheat") and cn.CROP_NAMES[17][1] == "barley"


def test_a_card_written_in_capitals_is_read(tmp_path):
    """INDEX.VY1, SHARED/<FARM>.FMD/<FIELD>.FLD/<TASK>.TSO / .TLO / .TLH / .TSH and COMBINES/<V>/<V>.YCS: found and
    decoded as the same card in small letters."""
    small = _card(tmp_path / "a", {"TASK0001": _logged(n=6)})
    _crop_table(small)
    big = tmp_path / "b"
    for d, _, files in os.walk(small):
        rel = os.path.relpath(d, small)
        out = big if rel == "." else big / rel.upper()
        os.makedirs(out, exist_ok=True)
        for f in files:
            stem, ext = os.path.splitext(f)
            with open(os.path.join(d, f), "rb") as src, open(out / (stem + ext.upper()), "wb") as dst:
                dst.write(src.read())
    assert [c for c in cn.find_cards(str(big))][0][1] is True
    assert os.path.isfile(big / "SYNTH001.CN1" / "INDEX.VY1")
    ua, ub = cn.list_units(small), cn.list_units(str(big))
    assert len(ub) == 1 and ub[0].n_records == ua[0].n_records == 6
    da, _ = cn.decode(small, [ua[0].id], OPTS, **QUIET)
    db, rb = cn.decode(str(big), [ub[0].id], OPTS, **QUIET)
    assert len(db) == len(da) == 6 and np.allclose(db.Yld_Vol_Dr, da.Yld_Vol_Dr)
    assert rb["sms_summary"]["datasets"][0]["wet_lb"] == pytest.approx(150.0)
    assert cn.probe(str(big)) is not None and "1 task logs" in cn.probe(str(big)).summary


def test_app_shows_the_summary_of_each_dataset(tmp_path, monkeypatch):
    """The app's decode report on a card: the table of the SMS Summary of each dataset (one row per task, the
    readings before the import's limits named decoded_readings)."""
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(tmp_path / "ws"))
    root = _card(tmp_path / "card", {"TASK0001": _logged(n=40)})
    _crop_table(root)
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.text_input(key="path_in").input(root)
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    next(b for b in at.button if str(b.key or "").startswith("extract_")).click().run()
    assert not at.exception, at.exception
    tables = [d.value for d in at.dataframe if "decoded_readings" in getattr(d.value, "columns", [])]
    assert len(tables) == 1 and len(tables[0]) == 1 and int(tables[0]["decoded_readings"].iloc[0]) == 40
