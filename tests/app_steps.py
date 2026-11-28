# -*- coding: utf-8 -*-
"""Helpers of the app tests (Streamlit's AppTest, synthetic data only) for the steps of 0.3.1: step 2's switch 'Use
SMS's default settings' and Apply, the dialog that takes a cleaned file back to SMS's default, the last card of a
label (step 2's, after a change, comes after step 1's), the 'Starts from' line of step 3."""
from __future__ import annotations


def by_key(items, prefix):
    """The first element whose key starts with prefix (None when there is none)."""
    return next((x for x in items if str(x.key or "").startswith(prefix)), None)


def switch(at):
    """Step 2's switch 'Use SMS's default settings' (None for a file without one: a planter, a legacy file)."""
    return by_key(at.toggle, "fi_def_")


def _run(at):
    at.run()
    assert not at.exception, [str(e.value)[:500] for e in at.exception]


def _switch_off(at):
    """The switch off (the import fields are drawn only then)."""
    s = switch(at)
    assert s is not None, "step 2 has no switch"
    if s.value:
        s.set_value(False)
        _run(at)


def _field(at, name):
    p = f"fi_{name}_"
    for group in (at.number_input, at.selectbox, at.checkbox, at.button_group):
        w = by_key(group, p)
        if w is not None:
            return w
    raise AssertionError(f"step 2 has no field {p}")


def _set_import(at, **values):
    """The switch off and the fields set (fi_max_=150 as max=150.0; how='none' for 'None: the file as it is'),
    without Apply."""
    _switch_off(at)
    if "how" in values:                                   # first: 'None' hides the fields
        _field(at, "how").set_value(values.pop("how"))
        _run(at)
    for name, v in values.items():
        _field(at, name).set_value(v)
        _run(at)


def _apply_import(at, **values):
    """Switch fi_def_ off, set the fi_<name>_ widgets, click fi_go_ (Apply to this file), run."""
    _set_import(at, **values)
    go = by_key(at.button, "fi_go_")
    assert go is not None and not go.disabled, "Apply is disabled: nothing differs from what is applied"
    go.click()
    _run(at)


def _apply_to_all(at, **values):
    """As _apply_import, with 'Apply to all N harvest files' (fi_goall_)."""
    _set_import(at, **values)
    go = by_key(at.button, "fi_goall_")
    assert go is not None and not go.disabled
    go.click()
    _run(at)


def _back_to_default(at, confirm=True):
    """The switch back on; with a cleaning, the dialog's 'Back to SMS's default' (confirm) or 'Keep my settings'."""
    s = switch(at)
    assert s is not None and not s.value, "the switch is not off"
    s.set_value(True)
    _run(at)
    b = by_key(at.button, "fi_backgo_" if confirm else "fi_backno_")
    if b is not None:                                     # the dialog: the file had a cleaning
        b.click()
        _run(at)


def _last_metric(at, label):
    """The last card of that label on the page (step 2's after a change; the first one is step 1's)."""
    m = [x for x in at.metric if x.label == label]
    assert m, f"no card {label!r}: {[x.label for x in at.metric]}"
    return m[-1]


def _first_metric(at, label):
    m = [x for x in at.metric if x.label == label]
    assert m, f"no card {label!r}: {[x.label for x in at.metric]}"
    return m[0]


def _starts_from(at):
    """Step 3's 'Starts from' line (its markdown element: .value, .help)."""
    return next(m for m in at.markdown if str(m.value).startswith("Starts from "))


def step_order(at, kind="markdown"):
    """The elements of a kind in the order the long page of 0.3.x showed them: 0.4.0 draws the steps as tabs (the
    test mode, OCED_ALL_STEPS, draws every tab in one run), and the import settings, step 2 of 0.3.x, are now folded
    in step 1, before the default import's map (step 2). So: step 2's elements (the default import, then the import
    in use), step 1's (the import settings), then steps 3 to 6 (the plots, step 5, before the final files, as 0.3.x
    drew the small area before them)."""
    tabs = [t for t in at.tabs if " · " in str(t.label)][:6]
    if len(tabs) < 6:
        return list(getattr(at, kind))
    out = []
    for i in (1, 0, 2, 3, 4, 5):
        out += list(getattr(tabs[i], kind))
    return out


def _badge_lines(at):
    """The lines with an import badge, as text (in the order of step_order)."""
    import re
    return [re.sub(r"<[^>]+>", "", m.value).strip() for m in step_order(at) if "oced-badge" in m.value]


def _extract_again(at, rows=(0,)):
    """'Extract more of this input' with the units of these rows of its table ticked (the table ticks nothing once a
    file of the input is in the work; AppTest keeps a selection set through the session state for one run only, so
    it is set in the run of the click)."""
    u = by_key(at.dataframe, "units_")
    assert u is not None, "no table of units"
    at.session_state[u.key] = {"selection": {"rows": list(rows), "columns": [], "cells": []}}
    b = next(x for x in at.button if str(x.key or "").startswith("extract_"))
    b.click()
    _run(at)
