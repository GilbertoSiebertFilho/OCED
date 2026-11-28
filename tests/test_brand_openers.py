# -*- coding: utf-8 -*-
"""0.3.7, the openers that hold an input share one look (app/brand.py OPENER_KEYS ...): a static check that the list
stays honest. Every keyed st.expander and st.popover of app/oced.py and app/replay_view.py is in an opener tuple or
in READ_ONLY_KEYS; every opener toggle prefix names a keyed st.toggle of the app; the page's CSS holds a rule for every
prefix (the direct-child selector of a keyed expander, its popover button, its toggle label).

    python -m pytest -q tests/test_brand_openers.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

import brand  # noqa: E402

SOURCES = [os.path.join(ROOT, "app", "oced.py"), os.path.join(ROOT, "app", "replay_view.py")]


def _calls(name: str) -> list:
    """(file, the literal start of the key) of every st.<name>( call that gives key=, the key's f-string cut at its
    first '{'."""
    out = []
    for p in SOURCES:
        src = open(p, encoding="utf-8").read()
        for m in re.finditer(r"st\.%s\(" % name, src):
            depth, i = 0, m.end() - 1
            while i < len(src):                      # the call's text, to its closing bracket
                ch = src[i]
                depth += ch == "("
                depth -= ch == ")"
                if depth == 0:
                    break
                i += 1
            call = src[m.start():i + 1]
            k = re.search(r"""key\s*=\s*f?["']([^"'{]*)""", call)
            if k:
                out.append((os.path.basename(p), k.group(1)))
                continue
            v = re.search(r"key\s*=\s*([A-Za-z_]\w*)", call)       # a key held in a name: its assignment
            if v:
                a = re.search(r"(?<![\w.])%s\s*=\s*f?[\"']([^\"'{]*)" % re.escape(v.group(1)), src)
                assert a, f"{os.path.basename(p)}: key={v.group(1)} of st.{name}: its value is not found"
                out.append((os.path.basename(p), a.group(1)))
    return out


def _known(prefix: str, tuples) -> bool:
    return any(prefix.startswith(p) or p.startswith(prefix) for t in tuples for p in t)


def test_every_keyed_expander_and_popover_is_listed():
    tuples = (brand.OPENER_KEYS, brand.OPENER_KEYS_INNER, brand.READ_ONLY_KEYS)
    exp = _calls("expander")
    assert exp, "no keyed expander found: the check reads nothing"
    missing = [(f, k) for f, k in exp if not _known(k, tuples)]
    assert not missing, f"keyed expanders in no opener tuple and not in READ_ONLY_KEYS: {missing}"
    pop = _calls("popover")
    missing = [(f, k) for f, k in pop if not _known(k, (brand.OPENER_POPOVERS, brand.READ_ONLY_KEYS))]
    assert not missing, f"keyed popovers in no tuple: {missing}"
    # the openers named in 0.3.7 carry their keys
    keys = {k for _, k in exp + pop}
    for k in ("open_box", "src_box_", "dec_box_", "fi_edit_", "set_box_", "more_sms", "gw_box_", "gw_more_",
              "sa_box_", "replay_box_", "mk_pop_"):
        assert any(x.startswith(k) for x in keys), k


def test_the_opener_toggles_exist():
    tg = {k for _, k in _calls("toggle")}
    for p in brand.OPENER_TOGGLES:
        assert any(k.startswith(p) for k in tg), p


def test_the_css_has_a_rule_for_every_prefix():
    css = brand._css()
    for p in brand.OPENER_KEYS + brand.OPENER_KEYS_INNER:
        assert f'[class*="st-key-{p}"] > [data-testid="stExpander"] > details' in css, p
    for p in brand.OPENER_POPOVERS:
        assert f'[class*="st-key-{p}"] [data-testid="stPopoverButton"]' in css, p
    for p in brand.OPENER_TOGGLES:
        assert f'[class*="st-key-{p}"] > [data-testid="stCheckbox"]' in css, p
    assert "st-key-gw_more_" in css and "border-left: 3px solid" in css       # the inner openers: a thinner edge
    assert "light-dark(" in css.split("openers of inputs")[1]                  # the dark-mode pairs
    assert css.count("<style>") == 1 and css.strip().endswith("</style>")


def test_the_step_bar_is_one_row_at_every_width_and_follows_the_open_step():
    """0.4.0: the step bar is one row that scrolls sideways at every width (with the sidebar open the main area is
    too narrow for the six pills up to about 1,330 px of viewport, which a rule on the viewport's width missed: the
    sixth pill went to a second row); up to 900 px its pills are smaller. Its script brings the open step's pill into
    view by the bar's own scrollLeft only (the page never moves up or down)."""
    css = brand._css()
    bar = css.split('.st-key-step_tab > div > [role="tablist"] {', 1)[1].split("}", 1)[0]
    assert "flex-wrap: nowrap" in bar and "overflow-x: auto" in bar and "@media" not in bar
    small = css.split("@media (max-width: 900px)", 1)[1].split("\n}", 1)[0]
    assert "flex-wrap" not in small and "font-size: 0.95rem" in small
    assert "@media (max-width: 640px)" not in css
    # the grower's weight box: no +/- buttons
    assert '[class*="st-key-gw_w_"] [data-testid="stNumberInputStepUp"]' in css
    js = brand.STEP_BAR_JS
    assert js.startswith("<script>") and "scrollIntoView" not in js and "scrollTo({left: left" in js
    assert '[role="tab"][aria-selected="true"]' in js and ".st-key-step_tab" in js
    src = open(os.path.join(ROOT, "app", "brand.py"), encoding="utf-8").read()
    assert "st.html(STEP_BAR_JS, unsafe_allow_javascript=True)" in src
