# -*- coding: utf-8 -*-
"""What a release must agree on with itself: one version (the app's title bar and sidebar, the engine, the ISOXML
sets OCED writes, README.md and INSTALAR.txt) and documents that describe what the writers do. Synthetic data only.

    python -m pytest -q tests/test_release.py
"""
from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402

Q = lambda m: None  # noqa: E731


def _text(*parts) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _app_version() -> str:
    m = re.search(r'^VERSION = "(\d+\.\d+\.\d+)"', _text("app", "brand.py"), re.M)
    assert m, "app/brand.py names no VERSION"
    return m.group(1)


def test_one_version_in_the_app_the_engine_and_the_documents():
    v = _app_version()
    assert er.__version__ == v                                   # no second version beside the app's
    assert f"**Version {v}**" in _text("README.md")
    assert f"Versão {v}" in _text("INSTALAR.txt")
    # the app takes its version from brand.py and shows it (title bar, sidebar) and keeps it with a saved work
    app = _text("app", "oced.py")
    assert "NAME, VERSION, TAGLINE = brand.NAME, brand.VERSION, brand.TAGLINE" in app and "app_version=VERSION" in app
    assert not re.search(r'^(?:__version__|VERSION)\s*=\s*"', app, re.M)


def test_an_isoxml_set_written_by_oced_carries_that_version(tmp_path):
    from engine.formats import isoxml_write as iw
    from tests.test_isoxml_write import _clean_file
    v = _app_version()
    W = iw.write_clean(None, _clean_file(str(tmp_path)), str(tmp_path / "out"), new_ids=False, log=Q)
    root = ET.parse(os.path.join(W["path"], "TASKDATA", "TASKDATA.XML")).getroot()
    assert root.get("ManagementSoftwareManufacturer") == "OCED" and root.get("ManagementSoftwareVersion") == v
    assert root.get("TaskControllerVersion") == v
    assert {d.get("C") for d in root.iter("DVC")} == {f"OCED {v}"}


def test_the_documents_say_how_many_time_logs_an_isoxml_set_takes():
    """The ISOXML writer puts the readings of a combine in as many time logs as they need (up to TIME_LOGS_MAX):
    the documents do not promise two."""
    from engine.formats import isoxml_write as iw
    readme = " ".join(_text("README.md").split())
    assert "second time log" not in readme and "second dataset" not in readme
    assert "as many as are needed" in readme and "SMS shows one dataset per time log" in readme
    assert {4: "up to four per combine"}[iw.TIME_LOGS_MAX] in readme
    doc = " ".join((iw.__doc__ or "").split())
    assert "in turn in two of them" not in doc and "in turn in two logs" not in doc
