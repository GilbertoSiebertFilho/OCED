# -*- coding: utf-8 -*-
"""The GreenStar 3 card decoder (engine/formats/jd_gs3_rcd.py) on a synthetic card: a session that is in the input
twice is read once (two zips of the same card, a folder next to its own zip, a copy that grew), and a card whose
files got new ids from a writer keeps its date span.

    python -m pytest -q tests/test_dec_gs3.py
"""
from __future__ import annotations

import os
import shutil
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.formats import jd_gs3_rcd as G  # noqa: E402
from tests.test_jd_gs3_rcd import make_card  # noqa: E402

NAME = "6a570000-0000-1000-aaaa-000000000001"
QUIET = lambda m: None  # noqa: E731


def _zip_folder(folder, zpath, prefix=""):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, files in os.walk(folder):
            for f in files:
                p = os.path.join(d, f)
                z.write(p, os.path.join(prefix, os.path.relpath(p, folder)).replace("\\", "/"))
    return zpath


def _decode_open(paths, work):
    cands = er.open_input(paths, work, log=QUIET)
    raw = [c for c in cands if c["kind"] == "raw"]
    assert len(raw) == 1, [c["label"] for c in cands]
    df, rep = G.decode(raw[0]["probe"].root, None, log=QUIET)
    return raw[0], df, rep


def test_a_session_uploaded_twice_is_read_once(tmp_path):
    """A-1: the same zip uploaded under two names (a browser re-download) holds every session twice under one scan
    root: one copy is read, and the probe and the decode report say that a copy was left out."""
    card = make_card(str(tmp_path / "card"))
    _, df1, rep1 = _decode_open([card["root"]], str(tmp_path / "w1"))
    up = tmp_path / "uploads"
    up.mkdir()
    _zip_folder(card["root"], str(up / "T.zip"))
    shutil.copyfile(up / "T.zip", up / "T (1).zip")
    cand, df2, rep2 = _decode_open([str(up)], str(tmp_path / "w2"))
    assert len(df2) == len(df1) == card["n"] - 5
    assert float(df2.Distance_f.sum()) == pytest.approx(float(df1.Distance_f.sum()))
    assert "1 GreenStar 3 log sessions" in cand["probe"].summary
    assert any("1 duplicate GreenStar 3 session" in w for w in cand["probe"].warnings)
    assert any("1 duplicate GreenStar 3 session" in w for w in rep2["warnings"]) and rep2["sessions_left_out"] == 1
    assert rep1["sessions_left_out"] == 0 and not any("duplicate" in w for w in rep1["warnings"])


def test_a_folder_next_to_its_own_zip_inside_one_zip_is_read_once(tmp_path):
    """A-1: one zip holding the card as a folder AND as a zip of that folder (a cloud drive download)."""
    card = make_card(str(tmp_path / "card"))
    inner = _zip_folder(card["root"], str(tmp_path / "Card.zip"))
    outer = tmp_path / "upload.zip"
    _zip_folder(card["root"], str(outer), prefix="Card")
    with zipfile.ZipFile(outer, "a") as z:
        z.write(inner, "Card.zip")
    cand, df, rep = _decode_open([str(outer)], str(tmp_path / "w"))
    assert len(df) == card["n"] - 5                    # once: the nested zip is not unpacked beside its folder ...
    keep, left = G.session_files(cand["probe"].root)
    assert len(keep) == 1 and rep["sessions_left_out"] == len(left)      # ... or its copy is left out


def test_the_largest_copy_of_a_session_is_kept(tmp_path):
    """Two copies of one session, the later export of the card longer: the longer one is read."""
    short = make_card(str(tmp_path / "a"), n=110)
    long_ = make_card(str(tmp_path / "b"), n=140)
    keep, left = G.session_files(str(tmp_path))
    assert [os.path.basename(p) for p in keep] == [NAME + ".fdl"] and len(left) == 1
    assert keep[0].startswith(long_["root"]) and left[0].startswith(short["root"])
    df, rep = G.decode(str(tmp_path), None, log=QUIET)
    assert len(df) == 140 - 5 and rep["sessions_left_out"] == 1
    assert G.find_sessions(str(tmp_path)) == keep


def test_a_card_with_new_file_ids_keeps_its_date_span(tmp_path):
    """A writer gives the files new ids by changing the third group (1000 -> 1xxx, SMS refuses archived files): the
    start time in the name is still read, so the probe gives the date span and the two cards are two sessions."""
    card = make_card(str(tmp_path / "card"))
    new = NAME.replace("-1000-", "-1a3f-")
    assert G.guid_time(new + ".fdd") == G.guid_time(NAME + ".fdd") is not None
    assert G.guid_time("6a570000-0000-2000-aaaa-000000000001.fdd") is None
    doc = os.path.join(card["root"], "RCD", "EIC", "Documentation", "AA")
    w = tmp_path / "written" / "RCD" / "EIC" / "Documentation" / "AA"
    w.mkdir(parents=True)
    for ext in (".fdd", ".fdl"):
        shutil.copyfile(os.path.join(doc, NAME + ext), w / (new + ext))
    pr = G.probe(str(tmp_path / "written"))
    assert pr is not None and "(UTC, from the file names)" in pr.summary
    keep, left = G.session_files(str(tmp_path))
    assert len(keep) == 2 and not left
