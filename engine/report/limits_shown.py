# -*- coding: utf-8 -*-
"""The dry-yield lower limit of the SMS 3-sigma cleaning as it is SHOWN (display only: nothing here changes a limit,
a reading, a file or the cleaning record).

When mean - k SD of a dry-yield pass (S5a, S5b ...) is negative, the filter types the lower limit as 0 (the record
keeps lo = 0.0, engine/clean/sms3sigma.py) and cuts nothing below. The lower limit in force is then the minimum yield
the import check (S0) applied: no reading below it reached the 3-sigma steps. So wherever a limit is shown (the
replay's card, step 3's Limits and Steps tabs, the cleaning report and its limits figure) that minimum is shown, with
the reason:

    5.00 bu/ac (import minimum; 3-sigma gave -22.16, so no cut below)
    0.00 bu/ac (3-sigma gave -22.16: no cut below; import minimum 0)      (no minimum: a point export, SMS's generic
                                                                           import)

A positive mean - k SD, a lower limit a floor above 0 set, and the moisture and speed steps are shown as before.
The value mean - k SD is computed again from the step's mean and SD and the cleaning's k (rounded half up to the
cleaning's decimals, as the limits are typed).
"""
from __future__ import annotations

import math

from engine.clean.sms3sigma import round_half_up


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def settings_of(R) -> dict:
    """The SMS 3-sigma settings of a cleaning record (k_sd, round_decimals ...)."""
    M = (R or {}).get("sms3sigma") or {}
    return M.get("settings") or (((R or {}).get("settings") or {}).get("sms3sigma") or {})


def import_minimum(R) -> float | None:
    """The minimum dry yield S0 applied in this cleaning (bu/ac): the file's own import's when it went through Import
    as SMS, else the cleaning's own (sms3sigma.min_yield). None = no minimum (None or 0)."""
    M = (R or {}).get("sms3sigma") or {}
    my = M.get("min_yield")
    if isinstance(my, dict):
        v = my.get("value")
    elif "min_yield" in M:
        v = my
    else:
        imp = ((R or {}).get("sms_import") or {})
        RS = imp.get("resolved") if isinstance(imp, dict) else None
        v = RS.get("min_yield") if isinstance(RS, dict) and "min_yield" in RS else settings_of(R).get("min_yield")
    v = _num(v)
    return v if (v is not None and v > 0) else None


def is_yield_step(step) -> bool:
    return isinstance(step, dict) and (str(step.get("attribute") or "") == "dry yield"
                                       or (not step.get("attribute") and str(step.get("step") or "").startswith("S5")))


def low_shown(step, R) -> dict | None:
    """{value, raw, minimum, reason, text} of a dry-yield step whose mean - k SD was negative (its lower limit shown
    as the import minimum); None for any other step (a positive mean - k SD, a floor above 0, moisture, speed, a
    group without limits)."""
    if not is_yield_step(step):
        return None
    lo, mu, sd = _num(step.get("lo")), _num(step.get("mean")), _num(step.get("sd"))
    if lo is None or mu is None or sd is None or lo > 0:
        return None
    P = settings_of(R)
    k = _num(P.get("k_sd"))
    k = 3.0 if k is None else k
    dec = P.get("round_decimals", 2)
    raw = mu - k * sd
    if not raw < 0:
        return None
    d = 2 if dec is None else int(dec)
    raw_r = round_half_up(raw, dec)
    raw_txt = f"{raw_r:.{d}f}" if raw_r < 0 else f"{raw:.{d}f}"     # a raw value rounding to 0 keeps its sign
    mn = import_minimum(R)
    if mn is not None:
        reason = f"import minimum; 3-sigma gave {raw_txt}, so no cut below"
        value = mn
    else:
        reason = f"3-sigma gave {raw_txt}: no cut below; import minimum 0"
        value = 0.0
    return {"value": value, "raw": raw_r, "minimum": mn, "reason": reason,
            "text": f"{value:.{max(d, 2)}f} bu/ac ({reason})"}


def low_text(step, R, dec: int = 2) -> str:
    """The lower limit of a step as shown: the number with `dec` decimals, or the import minimum with its reason."""
    L = low_shown(step, R)
    if L is not None:
        return L["text"]
    lo = _num(step.get("lo"))
    return "-" if lo is None else f"{lo:.{dec}f}"


def range_text(step, R) -> str:
    """'lo-hi' of a step with 2 decimals ('-' without limits); a negative dry-yield lower limit as
    '5.00 bu/ac (import minimum; 3-sigma gave -22.16, so no cut below) to 105.53'."""
    if not isinstance(step, dict) or _num(step.get("lo")) is None:
        return "-"
    L = low_shown(step, R)
    if L is not None:
        return f"{L['text']} to {float(step['hi']):.2f}"
    return f"{float(step['lo']):.2f}-{float(step['hi']):.2f}"


def criterion_shown(R, row) -> str:
    """A cascade row's criterion as shown: a dry-yield pass whose lower limit was negative names the import minimum
    in force instead of the 0.00 typed (the record's own text is unchanged); any other row as it is."""
    crit = str((row or {}).get("criterion") or "")
    fid = str((row or {}).get("filter") or "")
    if not fid.startswith("S5") or not (row or {}).get("on", True):
        return crit
    steps = [s for s in (((R or {}).get("sms3sigma") or {}).get("steps") or [])
             if str(s.get("step")) == fid and s.get("lo") is not None]
    shown = [(s, low_shown(s, R)) for s in steps]
    neg = [(s, L) for s, L in shown if L is not None]
    if not neg:
        return crit
    dec = settings_of(R).get("round_decimals", 2)
    d = dec or 2
    if len(steps) == 1:
        s, L = neg[0]
        old = f": {s['lo']:.{d}f}-{s['hi']:.{d}f} bu/ac"
        if old in crit:
            return crit.replace(old, f": lower {L['text']}, upper {s['hi']:.{d}f} bu/ac", 1)
        return crit
    mn = neg[0][1]["minimum"]
    note = (f"where 3-sigma gave a negative lower limit ({len(neg)} of {len(steps)} groups), the lower limit in force "
            + (f"is the import minimum {mn:.2f} bu/ac (no cut below)" if mn is not None
               else "is 0.00 bu/ac (no cut below; import minimum 0)"))
    old = "lower limit floored at 0"
    return crit.replace(old, note, 1) if old in crit else crit + f"; {note}"
