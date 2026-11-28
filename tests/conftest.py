# -*- coding: utf-8 -*-
"""The app's test mode for the AppTests (0.4.0): the steps are tabs and only the open one is drawn in a run, so the
AppTests of the blocks (written for the long page of 0.3.x, every step drawn in one run) run the app with
OCED_ALL_STEPS=1, which draws every tab in one run, in the order of the steps. A test marked lazy_tabs runs the app as
it is (only the open tab drawn): tests/test_app_tabs.py."""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "lazy_tabs: the app as it runs (only the open step's tab is drawn)")


@pytest.fixture(autouse=True)
def _all_steps(request, monkeypatch):
    if request.node.get_closest_marker("lazy_tabs"):
        monkeypatch.delenv("OCED_ALL_STEPS", raising=False)
    else:
        monkeypatch.setenv("OCED_ALL_STEPS", "1")
