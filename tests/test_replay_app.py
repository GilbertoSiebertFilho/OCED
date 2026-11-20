# -*- coding: utf-8 -*-
"""The app's 'Play the harvest' sections (app/replay_view.py) through Streamlit's AppTest, on synthetic data only:
folded, nothing is built; opened, the player of the readings (step 2) and of the cleaning (step 3) in a frame, the
replay as a file; the clean and flagged files are the same bytes with and without opening them.

    python -m pytest -q tests/test_replay_app.py
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.synthetic_replay import make_two_at_once  # noqa: E402

APP = os.path.join(ROOT, "app", "oced.py")


def _md5s(folder):
    out = {}
    for p in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True)):
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".shp", ".dbf", ".shx", ".prj"):
            out[os.path.relpath(p, folder)] = hashlib.md5(open(p, "rb").read()).hexdigest()
    return out


def _app(ws, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("OCED_WORKSPACE", str(ws))
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    assert not at.exception, at.exception
    return at


class _Frame:
    """A player mounted in the two-way component (the replay of a cleaning): its HTML as an iframe's srcdoc."""
    def __init__(self, html):
        self.proto = type("proto", (), {"srcdoc": html})()


def _iframes(at):
    """Every player on the page: the replay of the readings in an iframe, the replay of a cleaning in the two-way
    component (st.components.v2, app/replay_view.py), whose data carries the same HTML document."""
    out = [e for e in at.get("iframe")] + [e for e in at.get("i_frame")]
    for e in at.get("bidi_component"):
        if "oced_replay_player" in str(getattr(e.proto, "component_name", "")):
            out.append(_Frame(json.loads(e.proto.json)["html"]))
    return out


def test_app_play_the_harvest_sections_leave_the_files_as_they_are(tmp_path, monkeypatch):
    """Step 2 has 'Play the harvest' (folded: nothing built); opened, the player of the readings in an iframe and the
    replay as a file. After a cleaning, the same beside the clean map with kept / removed. The clean and flagged
    members are the same bytes with and without opening the replays."""
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    assert not at.exception, at.exception
    # the folded section (a keyed expander: AppTest knows it by its state, not by its label); nothing built yet
    assert [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_imp_")] and not _iframes(at)
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    C = at.session_state["cleaned"][at.session_state["active"]]
    out = at.session_state["workdir"]                   # the clean and the flagged files are in sub-folders of it
    assert os.path.exists(C["shp"]) and os.path.exists(C["flagged_shp"])
    before = _md5s(out)
    assert any(k.endswith("_flagged.shp") for k in before) and any(k.endswith("_clean.dbf") for k in before)
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]
    assert len(keys) == 2
    for k in keys:
        at.session_state[k] = True
    at.run()
    assert not at.exception, at.exception
    fr = _iframes(at)
    assert len(fr) == 2
    srcs = [getattr(f.proto, "srcdoc", "") or "" for f in fr]
    assert all("rp-data" in s and "server.arcgisonline.com" in s for s in srcs)
    kinds = sorted(json.loads(re.search(r'type="application/json">(.*?)</script>', s, re.S).group(1))["kind"]
                   for s in srcs)
    assert kinds == ["clean", "import"]
    assert any((d.label or "").startswith("Replay as a file") for d in at.get("download_button"))
    after = _md5s(out)
    assert after == before


def _payload(srcdoc):
    return json.loads(re.search(r'type="application/json">(.*?)</script>', srcdoc, re.S).group(1))


def test_app_management_zone_map_in_both_replays(tmp_path, monkeypatch):
    """'Management zone map' in the replay section: a zone map made elsewhere, given by its path, is used by both
    replays of the file (step 2 and the clean map), kept with the work (zones/<tag>/zone_map.json) and still there
    after a rerun; its class column can be chosen; the zone table can be downloaded; removed, the replays are as
    before. The clean and flagged files are the same bytes with and without it."""
    import geopandas as gpd
    from tests.synthetic import _rect
    two = make_two_at_once(str(tmp_path / "data"), n_pass=6)
    ymax = float(two["df"]["y"].max()) + 30
    zp = str(tmp_path / "zones" / "my_zones.geojson")
    os.makedirs(os.path.dirname(zp))
    gpd.GeoDataFrame({"zone": [1, 2], "Rx_seed": [120.0, 140.0]},
                     geometry=[_rect(-10, 150, -20, ymax), _rect(150, 320, -20, ymax)], crs="EPSG:4326").to_file(zp)
    at = _app(tmp_path / "ws", monkeypatch)
    at.text_input(key="path_in").input(two["shp"])
    at.button(key="open_btn").click().run()
    at.button(key="clean_one").click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    out = at.session_state["workdir"]
    before = _md5s(out)
    keys = [k for k in at.session_state.filtered_state if str(k).startswith("replay_box_")]

    def run(el=None):
        # the sections stay open: AppTest keeps no expander state, and the st.rerun() of an action (Use, a column,
        # Remove) runs the page once more without it, so the page is run again with them open, as a browser does
        for k in keys:
            at.session_state[k] = True
        (el or at).run()
        assert not at.exception, at.exception
        if el is not None:
            for k in keys:
                at.session_state[k] = True
            at.run()
            assert not at.exception, at.exception
    run()
    assert len(_iframes(at)) == 2 and all("zones" not in _payload(f.proto.srcdoc) for f in _iframes(at))
    imp = next(k for k in keys if k.startswith("replay_box_imp_"))[len("replay_box_"):]
    at.text_input(key=f"zm_path_{imp}").input(zp)
    run(at.button(key=f"zm_use_{imp}").click())
    assert not at.error, [e.value for e in at.error]
    fr = _iframes(at)
    assert len(fr) == 2
    for f in fr:                                         # both replays of the file carry the zones
        P = _payload(f.proto.srcdoc)
        assert [c["label"] for c in P["zones"]["classes"]] == ["1", "2"] and P["zones"]["column"] == "zone"
        assert P["zones"]["raw"] == (P["kind"] == "import")
        assert 'id="zpanel"' in f.proto.srcdoc
    labels = [d.label for d in at.get("download_button")]
    assert labels.count("Zone table (zone_yield.csv)") == 2
    tag = at.session_state["active"]
    rec = os.path.join(out, "zones", tag, "zone_map.json")
    assert os.path.exists(rec) and json.load(open(rec, encoding="utf-8"))["column"] == "zone"
    sel = [s for s in at.selectbox if str(s.key or "").startswith(f"zm_col_{imp}_")]
    assert sel and sel[0].value == "zone" and any(o.startswith("Rx_seed · 2 zones") for o in sel[0].options)
    run(sel[0].select("Rx_seed"))                        # another column: the replays follow
    assert all(_payload(f.proto.srcdoc)["zones"]["column"] == "Rx_seed" for f in _iframes(at))
    del at.session_state["replay_zone_maps"]             # a new session of the same work: read back from the folder
    run()
    assert all(_payload(f.proto.srcdoc)["zones"]["column"] == "Rx_seed" for f in _iframes(at))
    run(at.button(key=f"zm_rm_{imp}").click())
    assert all("zones" not in _payload(f.proto.srcdoc) for f in _iframes(at))
    assert not os.path.exists(rec)
    assert _md5s(out) == before
