# -*- coding: utf-8 -*-
"""The management zone map of the app's replay (app/replay_view.py) called directly, on synthetic files only: it
belongs to its work (two works with a file of the same tag each keep their own), a file that cannot be read is a
message and never a traceback, an upload is kept relative to the work folder (a moved work still finds it), a refused
upload is not kept, Remove deletes the upload, and a file changed on disk is read again.

    python -m pytest -q tests/test_replay_zone_state.py
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import warnings

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "app"))

from tests.synthetic import _rect  # noqa: E402


@pytest.fixture()
def rv():
    warnings.filterwarnings("ignore")
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import streamlit as st
    import replay_view
    st.session_state.pop(replay_view.ZONE_STATE, None)
    yield replay_view
    st.session_state.pop(replay_view.ZONE_STATE, None)
    st.session_state.pop("workdir", None)


def _zone_file(path, column="zone", values=(1, 2)):
    import geopandas as gpd
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gpd.GeoDataFrame({column: list(values)}, geometry=[_rect(0, 50, 0, 50), _rect(50, 100, 0, 50)],
                     crs="EPSG:4326").to_file(path, engine="pyogrio")
    return path


class _Up:
    """A stand-in of st.file_uploader's file: its name and its bytes."""

    def __init__(self, path, name=None):
        self.name = name or os.path.basename(path)
        self._b = open(path, "rb").read()

    def getbuffer(self):
        return memoryview(self._b)


def _workdir(rv, d):
    import streamlit as st
    os.makedirs(d, exist_ok=True)
    st.session_state["workdir"] = str(d)


def test_the_zone_map_belongs_to_its_work(rv, tmp_path):
    """Work A holds a zone map for tag X; work B with a file of tag X has none and gets none written; B's own map
    stays B's; back on A (a new session), A's zones/X/zone_map.json is read again."""
    import streamlit as st
    za = _zone_file(str(tmp_path / "maps" / "a.geojson"))
    zb = _zone_file(str(tmp_path / "maps" / "b.geojson"), column="mz")
    _workdir(rv, tmp_path / "A")
    assert rv._use_zone_file("Home_2026", ("path", za)) is None
    assert rv.zone_map_of("Home_2026")["path"] == os.path.abspath(za)
    _workdir(rv, tmp_path / "B")
    assert rv.zone_map_of("Home_2026") is None
    assert not os.path.exists(tmp_path / "B" / "zones")
    assert rv._use_zone_file("Home_2026", ("path", zb)) is None
    assert rv.zone_map_of("Home_2026")["column"] == "mz"
    st.session_state.pop(rv.ZONE_STATE)                 # a new session: A opened again
    _workdir(rv, tmp_path / "A")
    Z = rv.zone_map_of("Home_2026")
    assert Z["path"] == os.path.abspath(za) and Z["column"] == "zone"
    _workdir(rv, tmp_path / "B")
    assert rv.zone_map_of("Home_2026")["path"] == os.path.abspath(zb)


def test_a_file_that_cannot_be_read_is_a_message(rv, tmp_path):
    _workdir(rv, tmp_path / "W")
    bad = tmp_path / "zones.zip"
    bad.write_bytes(b"not a zip at all" * 64)
    err = rv._use_zone_file("F", ("path", str(bad)))
    assert err and "not a zip archive" in err
    info = rv.zone_info(str(bad), rv.zone_fingerprint(str(bad)), None)
    assert "not a zip archive" in info["error"]
    # the same as an upload: refused, and nothing of it kept in the work folder
    err = rv._use_zone_file("F", ("upload", [_Up(str(bad))]))
    assert err and "not a zip archive" in err
    assert not os.path.exists(tmp_path / "W" / "zones" / "F" / "file")
    assert rv.zone_map_of("F") is None


def test_a_stored_zone_map_that_fails_later_is_a_message(rv, tmp_path):
    """A zone map chosen, then damaged on disk: the control gets an error (its Remove button is reached), no raise."""
    _workdir(rv, tmp_path / "W")
    zp = _zone_file(str(tmp_path / "maps" / "z.geojson"))
    assert rv._use_zone_file("F", ("path", zp)) is None
    open(zp, "w").write("{broken")
    Z = rv.zone_map_of("F")                               # changed on disk: fingerprinted again
    info = rv.zone_info(Z["path"], Z["fingerprint"], Z.get("column"))
    assert info.get("error") and "z.geojson" in info["error"]


def test_an_upload_is_kept_with_the_work_and_removed_with_it(rv, tmp_path):
    zp = _zone_file(str(tmp_path / "maps" / "zones_rx.shp"))
    ups = [_Up(zp[:-4] + e) for e in (".shp", ".shx", ".dbf", ".prj")]
    _workdir(rv, tmp_path / "W")
    assert rv._use_zone_file("F", ("upload", ups)) is None
    kept = tmp_path / "W" / "zones" / "F" / "file" / "zones_rx.shp"
    assert kept.exists()
    rec = json.load(open(tmp_path / "W" / "zones" / "F" / "zone_map.json", encoding="utf-8"))
    assert not os.path.isabs(rec["path"]) and rec["path"].replace("\\", "/") == "file/zones_rx.shp"
    # the work folder moved (or copied) elsewhere: its zone map is still found, inside it
    shutil.copytree(tmp_path / "W", tmp_path / "W2")
    import streamlit as st
    st.session_state.pop(rv.ZONE_STATE)
    _workdir(rv, tmp_path / "W2")
    Z = rv.zone_map_of("F")
    assert not Z.get("missing") and os.path.normcase(Z["path"]) == os.path.normcase(
        str(tmp_path / "W2" / "zones" / "F" / "file" / "zones_rx.shp"))
    rv._set_zone_map("F", None)                            # Remove: the record and the kept upload go
    assert not os.path.exists(tmp_path / "W2" / "zones" / "F" / "file")
    assert not os.path.exists(tmp_path / "W2" / "zones" / "F" / "zone_map.json")
    assert rv.zone_map_of("F") is None


def test_a_file_changed_on_disk_is_read_again(rv, tmp_path):
    _workdir(rv, tmp_path / "W")
    zp = _zone_file(str(tmp_path / "maps" / "z.geojson"))
    assert rv._use_zone_file("F", ("path", zp)) is None
    fp0 = rv.zone_map_of("F")["fingerprint"]
    assert rv.zone_map_of("F")["fingerprint"] == fp0       # unchanged: the same
    _zone_file(zp, values=(3, 4))
    os.utime(zp, (os.path.getatime(zp), os.path.getmtime(zp) + 5))
    Z = rv.zone_map_of("F")
    assert Z["fingerprint"] != fp0
    assert rv.zone_info(Z["path"], Z["fingerprint"], Z["column"])["labels"] == ["3", "4"]
