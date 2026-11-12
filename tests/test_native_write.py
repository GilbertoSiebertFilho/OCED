# -*- coding: utf-8 -*-
"""engine/formats/native_write.py, the dispatcher the app shows: the monitor's own format first, ISOXML always last
and only for exports (or as an explicit fallback); writers imported only when they exist, a broken one reported, not
fatal; the interface keys of every result. Synthetic data only (tests/synthetic_cn1.py, a made-up export).

    python -m pytest -q tests/test_native_write.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import native_write as NW  # noqa: E402
from tests.synthetic_cn1 import make_card  # noqa: E402
from tests.test_isoxml_write import _clean_file  # noqa: E402

QUIET = lambda m: None  # noqa: E731


@pytest.fixture(scope="module")
def decoded(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("nw_card"))
    card = make_card(os.path.join(folder, "input"))
    wd = str(tmp_path_factory.mktemp("nw_work"))
    cand = er.open_input([card["card"]], wd, log=QUIET)[0]
    dec = er.decode(cand, None, None, wd, log=QUIET)
    return {"card": card, "dec": dec}


def test_options_for_a_raw_card(decoded):
    o = NW.options(decoded["dec"]["source"])
    assert [x["id"] for x in o] == ["cnh_cn1", "isoxml"]
    assert o[0]["native"] and o[0]["available"] and o[0]["reason"] == ""
    assert not o[1]["native"] and not o[1]["available"] and "exports" in o[1]["reason"]
    assert "not the source's format" in o[1]["label"]


def test_isoxml_stays_off_for_a_raw_card_with_the_fallback_the_app_passes(decoded):
    """R5T-7: the app asks for the options with isoxml_fallback=True whenever the file has a source; for a decoded
    card whose own writer can write, ISOXML still stays unavailable (it is the fallback, not a second choice)."""
    o = NW.options(decoded["dec"]["source"], isoxml_fallback=True)
    assert [x["id"] for x in o] == ["cnh_cn1", "isoxml"]
    assert o[0]["native"] and o[0]["available"] and o[0]["reason"] == ""
    assert not o[-1]["native"] and not o[-1]["available"] and "exports" in o[-1]["reason"]


def test_options_for_an_export():
    o = NW.options(None)
    assert [x["id"] for x in o] == ["isoxml"] and o[0]["available"]
    o = NW.options({"kind": "export", "format": "sms_export"})
    assert [x["id"] for x in o] == ["isoxml"] and o[0]["available"]


def test_card_gone_and_fallback(decoded, tmp_path):
    src = dict(decoded["dec"]["source"], input_root=str(tmp_path / "gone"))
    o = NW.options(src)
    assert not o[0]["available"] and "not on this computer" in o[0]["reason"] and not o[1]["available"]
    o = NW.options(src, isoxml_fallback=True)
    assert not o[0]["available"] and o[-1]["id"] == "isoxml" and o[-1]["available"]
    with pytest.raises(ValueError, match="not on this computer"):
        NW.write("cnh_cn1", src, decoded["dec"]["shp"], str(tmp_path / "o"), log=QUIET)


def test_a_decode_of_an_older_version_is_not_written_in_its_format(decoded, tmp_path):
    """AF-1: a source decoded by an older version of OCED (its report lacks what every decode of its format now
    carries, here the Case IH card's sms_summary) is not offered in the monitor's format: the writer would decode the
    card again with the current model and write readings the clean file does not hold. ISOXML (written from the clean
    file itself) stays the fallback."""
    src = decoded["dec"]["source"]
    assert NW.decode_outdated(src) == ""
    rep = json.load(open(src["decode_report"], encoding="utf-8"))
    rep.pop("sms_summary")
    old = dict(src, report=rep)
    assert NW.decode_outdated(old) == NW.OLD_DECODE
    o = NW.options(old, isoxml_fallback=True)
    assert not o[0]["available"] and o[0]["reason"] == NW.OLD_DECODE
    assert o[-1]["id"] == "isoxml" and o[-1]["available"]
    with pytest.raises(ValueError, match="older version of OCED"):
        NW.write("cnh_cn1", old, decoded["dec"]["shp"], str(tmp_path / "o"), log=QUIET)
    # the same report read from the decode report file
    p = str(tmp_path / "old_decode_report.json")
    json.dump(rep, open(p, "w", encoding="utf-8"))
    assert NW.decode_outdated(dict(src, decode_report=p)) == NW.OLD_DECODE
    assert NW.decode_outdated(None) == "" and NW.decode_outdated({"kind": "export"}) == ""


def test_missing_or_broken_writer(monkeypatch, decoded):
    monkeypatch.setattr(NW, "_raw_formats", lambda: NW.RAW_FORMATS + ("synfmt",))
    o = NW.options({"kind": "decoded", "format": "synfmt", "label": "Synthetic monitor"})
    assert [x["id"] for x in o] == ["synfmt", "isoxml"]
    assert not o[0]["available"] and "no writer" in o[0]["reason"] and o[0]["label"].startswith("Synthetic monitor")
    real = NW.importlib.import_module

    def broken(name, *a, **k):
        if name == "engine.formats.cnh_cn1_write":
            raise ImportError("synthetic import failure")
        return real(name, *a, **k)
    monkeypatch.setattr(NW.importlib, "import_module", broken)
    o = NW.options(decoded["dec"]["source"])
    assert not o[0]["available"] and "could not be loaded" in o[0]["reason"]


def test_write_native_and_isoxml(decoded, tmp_path):
    src = decoded["dec"]["source"]
    res = NW.write("cnh_cn1", src, decoded["dec"]["shp"], str(tmp_path / "card"), log=QUIET, totals="scaled",
                   lead_in="gaps")
    for k in NW.REQUIRED_KEYS + ("format_id", "label", "native", "sms_tested"):
        assert k in res, k
    assert res["native"] and res["format_id"] == "cnh_cn1" and res["sms_tested"] is False
    assert os.path.isfile(res["zip"]) and res["n_removed"] == 0
    assert any("lead_in" in w for w in res["warnings"])            # an option of another writer: named, not used
    with pytest.raises(ValueError, match="not available|exports"):
        NW.write("isoxml", src, decoded["dec"]["shp"], str(tmp_path / "iso"), log=QUIET)
    shp = _clean_file(str(tmp_path))
    r2 = NW.write("isoxml", None, shp, str(tmp_path / "iso"), log=QUIET, lead_in="always")
    assert not r2["native"] and r2["n_kept"] == len(pyogrio.read_dataframe(shp, read_geometry=False))
    assert r2["lead_in"] == "always" and any("not yet tested in SMS" in n for n in r2["notes"])


def test_refusals(decoded, tmp_path):
    src = decoded["dec"]["source"]
    with pytest.raises(ValueError, match="not offered"):
        NW.write("jd_jdl", src, decoded["dec"]["shp"], str(tmp_path / "o"), log=QUIET)
    with pytest.raises(ValueError, match="inside the raw input"):
        NW.write("cnh_cn1", src, decoded["dec"]["shp"], os.path.join(decoded["dec"]["report"]["input_root"], "x"),
                 log=QUIET)
    empty = str(tmp_path / "empty.shp")
    pyogrio.read_dataframe(decoded["dec"]["shp"]).iloc[:0].to_file(empty, engine="pyogrio")
    with pytest.raises(ValueError, match="no readings"):
        NW.write("cnh_cn1", src, empty, str(tmp_path / "o2"), log=QUIET)
    with pytest.raises(ValueError, match="no readings"):
        NW.write("isoxml", None, empty, str(tmp_path / "o3"), log=QUIET)
    shutil.rmtree(str(tmp_path / "o2"), ignore_errors=True)


def test_an_old_greenstar_source_without_its_report_is_not_written(tmp_path):
    """R4E-1: a GreenStar 3 source saved by the first published version (no 'unit_ids') whose decode report JSON is
    gone: nothing says which units or which grain alignment the decode used, and the GreenStar 3 writer would fall
    back to the decoder's defaults. It is not offered in the card format (as with its report: OLD_DECODE); a source
    of this version without its report JSON (it carries 'unit_ids') still is."""
    from tests.test_jd_gs3_rcd import make_card as gs3_card
    root = gs3_card(str(tmp_path / "card"))["root"]
    wd = str(tmp_path / "work")
    cand = [c for c in er.open_input([root], wd, log=QUIET) if c.get("kind") == "raw"][0]
    dec = er.decode(cand, None, None, wd, log=QUIET)
    src = dec["source"]
    assert src["format"] == "jd_gs3_rcd" and src["unit_ids"]
    gone = str(tmp_path / "gone_decode_report.json")
    o = NW.options(dict(src, decode_report=gone))
    assert o[0]["id"] == "jd_gs3_rcd" and o[0]["available"], o
    old = {k: v for k, v in src.items() if k != "unit_ids"}
    old["decode_report"] = gone
    o = NW.options(old, isoxml_fallback=True)
    assert not o[0]["available"] and o[0]["reason"] == NW.OLD_DECODE, o[0]
    assert NW.decode_outdated(old) == NW.OLD_DECODE
    assert o[-1]["id"] == "isoxml" and o[-1]["available"]
    with pytest.raises(ValueError, match="older version of OCED"):
        NW.write("jd_gs3_rcd", old, dec["shp"], str(tmp_path / "o"), log=QUIET)
    # its report given with the source (as the app passes the report the work keeps): the marker decides
    assert NW.decode_outdated(dict(old, report=dec["report"])) == ""
