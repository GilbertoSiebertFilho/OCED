# -*- coding: utf-8 -*-
"""Cleaning report (PDF) of one run of engine/clean/yield_clean.py.

    from engine.report.clean_report import make_report
    make_report(result, "out/field_cleaning_report.pdf")

`result` is the dict returned by yield_clean.run (also saved as <tag>_cleaning.json; figure paths are absolute).
Content, 4-8 US-letter pages: (1) summary - input file and its source (an export as given, or the raw monitor dataset
it was decoded from, with the decoder, units, crop, test weight, standard moisture, shrink and calibration), points
in / kept / removed, the field of interest, the moisture basis, how the F8 overlap threshold was chosen, the flow-delay
decision, machines and harmonisation, the level factor when a scale ticket was given, the column to map as yield,
every warning (the decoder's included) and the checks worth making (R['advice']); (2) the cascade table
(pre-steps such as the field-of-interest clip, then every filter: rule with the thresholds used, the works that
support it, removed, remaining; switched-off filters greyed); (3) "Field of interest" (R['aoi']: plan file,
polygons / plots, area, points outside the buffer, output clip); (4) "Harvest sessions" (R['sessions']: one row per
machine x day, the field mean against the cleaned-map mean, the discontinuity check between consecutive sessions, the
recommendation and fig_clean_sessions.png); (5) "Combines" (R['machines']: per-machine means, the harvest layout of
every pair of combines (R['machines']['layout']), the four methods with their traffic light and the one used
(R['machines']['methods']), the factors of the method used with their bootstrap CI and decision, per-machine totals and
their validation); (6) "Level: the grower's weight" (R['level']: the ticket in its
unit, its conversion to bushels, L, the closure with the monitor total, the combines' ticket closure test and the
yield column to map); (7) the settings and the column mapping; (8) the figures; (9) "References": the full
citation (authors, year, title, venue, DOI) of every work cited by the steps that ran, from engine/clean/references.py.
Sections (3)-(6) are written only when their key is in `result`, so a JSON of an older run still renders. Every
number is read from `result`; nothing is recomputed here.

v2.4: the F8 line names the footprint (R['f8']['footprint']: the swept strip or the v2.3 chord rectangle, with
R['f8']['y_offset']), the reference of the dose-response (R['f8']['reference_mode']: the local edge-matched controls of
R['f8']['local'] - combine_key, radius_m against radius_setting_m, edge tolerance, placebo, matched_n of dose_n, the
population (the pass interiors) - or the v2.3 no-overlap band, also when the local reference fell back to it), the
5 % floor (R['f8']['floor_applied']) and what stopped the scan (R['f8']['stop_kind']: too few records with controls,
or a measured yield drop); the flow-delay line names the axis of the scan (R['lag']['axis']: the dominant pass axis,
or the v2.3 E-W-first rule) and where the delay was measured and applied (R['lag']['stage']: 'output', the default,
moves the output geometry only; only 'before_f7', the option, says that F7 and F8 used the shifted positions and how
many records went with F7, R['lag']['n_orphans']); the map caption says the strips are the swept strips. Every one of
these keys is read with .get(), so a JSON written before v2.4 renders with the v2.3 wording.
"""
from __future__ import annotations

import datetime
import json
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from engine.clean import references as refs
from engine.clean import yield_clean

# Olds College palette (assets/brand/BRAND.md, app/brand.py): navy headings and table headers, light-blue zebra rows and
# rules; the warnings keep their amber (5.9:1 on white)
NAVY = colors.HexColor("#00358E")
GREY = colors.HexColor("#5f5f5f")
LIGHT = colors.HexColor("#EEF4FB")
OFF = GREY                       # switched-off rows: 6.4:1 on white (AA); #a3a3a3 was 2.5:1, unreadable on paper
AMBER = colors.HexColor("#8a5a00")
RULE = colors.HexColor("#C9D8EC")
BRAND = "OCED — Olds College Extract Data"
ORG = "Olds College Smart Farm"
# the horizontal Olds College logo (500 x 125 px) for the masthead of the first page, LOGO_H high
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "brand",
                    "oc_logo_horizontal.png")
LOGO_H = 11 * mm
PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch
TEXT_W = PAGE_W - 2 * MARGIN

H1 = ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, spaceAfter=4)
H2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=10,
                    spaceAfter=5)
BRANDP = ParagraphStyle("BRANDP", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=NAVY,
                        alignment=TA_RIGHT)
BRANDS = ParagraphStyle("BRANDS", fontName="Helvetica", fontSize=8, leading=10, textColor=GREY, alignment=TA_RIGHT)
BODY = ParagraphStyle("BODY", fontName="Helvetica", fontSize=10, leading=13.5, alignment=TA_LEFT, spaceAfter=5)
SUB = ParagraphStyle("SUB", parent=BODY, textColor=GREY, fontSize=9.5)
BUL = ParagraphStyle("BUL", parent=BODY, leftIndent=14, bulletIndent=4, spaceAfter=3)
WARN = ParagraphStyle("WARN", parent=BUL, textColor=AMBER)
CAP = ParagraphStyle("CAP", fontName="Helvetica", fontSize=8.5, leading=11, textColor=GREY, spaceAfter=8)
CELL = ParagraphStyle("CELL", fontName="Helvetica", fontSize=8.5, leading=10.5)
CELLS = ParagraphStyle("CELLS", parent=CELL, fontSize=7.5, leading=9)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
CELLOFF = ParagraphStyle("CELLOFF", parent=CELL, textColor=OFF, fontName="Helvetica-Oblique")
CELLH = ParagraphStyle("CELLH", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)


def _unicode_font() -> str:
    """Name of a registered TrueType font with the Latin Extended glyphs (Ř, ů, ã ...) that the base-14 Helvetica
    lacks; the references are set in it. DejaVu Sans ships with matplotlib; Arial is the Windows fallback; Helvetica
    when neither is found (accented names then print as squares)."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = []
    try:
        import matplotlib
        candidates.append(("DejaVuSans", os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")))
    except Exception:                                   # matplotlib absent: try the system font only
        pass
    candidates.append(("ArialUnicode", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", "arial.ttf")))
    for name, path in candidates:
        if os.path.exists(path):
            try:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, path))
                return name
            except Exception:
                continue
    return "Helvetica"


REF_FONT = _unicode_font()
REF = ParagraphStyle("REF", fontName=REF_FONT, fontSize=6.9 if REF_FONT != "Helvetica" else 7.2, leading=8.2,
                     leftIndent=10, firstLineIndent=-10, spaceAfter=0.8)


def _e(v) -> str:
    return escape(str(v))


def _n(v, d=0) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):,.{d}f}"
    except (TypeError, ValueError):
        return _e(v)


def _pct(v, d=2) -> str:
    """A fraction (0.12) as '12.00 %'; None -> '-'."""
    if v is None:
        return "-"
    try:
        return f"{100 * float(v):.{d}f} %"
    except (TypeError, ValueError):
        return _e(v)


def _g(d, *keys, default=None):
    """Nested .get: _g(R, 'sessions', 'field', 'note')."""
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def _table(rows, widths, header=True, off_rows=(), bold_first=False, small=False):
    """rows: list of lists of str (already escaped/markup); off_rows: row indices (data rows, 0-based) to grey."""
    data = []
    base = CELLS if small else CELL
    for i, r in enumerate(rows):
        if header and i == 0:
            data.append([Paragraph(c, CELLH) for c in r])
            continue
        k = i - (1 if header else 0)
        st = CELLOFF if k in off_rows else base
        data.append([Paragraph(c, CELLB if (bold_first and j == 0 and k not in off_rows) else st)
                     for j, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    for k in range(len(rows) - (1 if header else 0)):
        if k % 2 == 1:
            style.append(("BACKGROUND", (0, k + (1 if header else 0)), (-1, k + (1 if header else 0)), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def _image(path, max_w, max_h):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(path).getSize()
    s = min(max_w / iw, max_h / ih)
    return Image(path, width=iw * s, height=ih * s)


def _masthead():
    """The masthead of the first page: the Olds College logo at the left (LOGO_H high) and the app's name at the
    right, over a thin rule. Text only when the logo file is not next to the engine (a copied engine folder)."""
    right = [Paragraph(_e(BRAND), BRANDP),
             Paragraph(_e(ORG) + " &middot; machine data extraction and cleaning", BRANDS)]
    left = _image(LOGO, 0.45 * TEXT_W, LOGO_H) if os.path.exists(LOGO) else Paragraph("", BODY)
    t = Table([[left, right]], colWidths=[0.45 * TEXT_W, 0.55 * TEXT_W])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE)]))
    return t


def _f8_footprint_text(f8) -> str:
    """' Footprint: ...' of a v2.4 result (R['f8']['footprint'], R['f8']['y_offset']); '' for an older JSON."""
    fp = f8.get("footprint")
    if not fp:
        return ""
    t = (" Footprint: the strip the header swept since the previous reading of the pass (from the header line there "
         "to the header line here)" if fp == "swept" else
         " Footprint: the v2.3 rectangle along the chord from the previous reading of the pass")
    yo = f8.get("y_offset") or {}
    if yo.get("applied"):
        t += f", centred {_e(yo.get('column') or 'Y_Offset')} to the right of travel"
    return t + "."


def _frac_pct(v, fmt: str = ".3g") -> str:
    """100 x a fraction as text ('5'), '-' when it is missing."""
    try:
        return format(100 * float(v), fmt)
    except (TypeError, ValueError):
        return "-"


def _f8_controls_text(f8, lead: str = "controls: ") -> str:
    """'(controls: ...; placebo ...)' of the v2.4 local reference (R['f8']['local']): the combine key, the radius
    (max(local_radius_m, 1.5 header widths)), the edge tolerance, the minimum number of controls, the placebo and how
    many records found controls. Every key is read with .get(), so an older v2.4 JSON renders too."""
    loc = f8.get("local") or {}
    pl = loc.get("placebo_ratio")
    key = loc.get("combine_key")
    rad, rset = loc.get("radius_m"), loc.get("radius_setting_m")
    try:
        widened = rset is not None and rad is not None and float(rad) > float(rset) + 1e-6
    except (TypeError, ValueError):
        widened = False
    if key and str(key).startswith("one combine"):
        who = "all records taken as one combine, since the file names none;"
    else:
        who = f"same combine as identified by the {_e(key)}" if key else "same combine"
    txt = (f"({lead}{who}" + ("" if who.endswith(";") else ",") + f" another pass, within {_n(rad, 2)} m"
           + (f" = 1.5 header widths, above the {_n(rset)} m minimum" if widened else "")
           + f", the same distance from the harvested edge within {_n(loc.get('edge_tol_m'))} m, "
           f"&ge; {_n(loc.get('min_controls'))} of them")
    if pl is not None:
        txt += (f"; placebo {float(pl):.3f} = the median ratio of the no-overlap records to their own controls, "
                f"{_n(loc.get('placebo_n'))} records")
    if loc.get("matched_n") is not None and loc.get("dose_n"):
        txt += f"; {_n(loc.get('matched_n'))} of the {_n(loc.get('dose_n'))} records found controls"
    return txt + ")"


def _f8_reference_text(f8) -> str:
    """What each overlap band was compared with: the local edge-matched controls (v2.4) or the no-overlap band."""
    if f8.get("reference_mode") == "local":
        return "the local no-overlap controls " + _f8_controls_text(f8, lead="")
    return "the no-overlap band (measured within each combine, pooled by band size)"


def _f8_stop_text(f8) -> str:
    """' The 2-5 % band that set it reads ...; the 5-10 % band stops the scan (...).' plus what stopped it
    (R['f8']['stop_kind'] of the local reference: too few matched records, or a yield drop); '' without the keys."""
    loc_mode = f8.get("reference_mode") == "local"
    tol = f8.get("tolerance_pct", 3.0)
    parts = []
    if f8.get("margin_pct") is not None and f8.get("last_pass_band"):
        parts.append(f"The {_e(f8['last_pass_band'])} % band that set it reads {f8['margin_pct'] - tol:+.2f} % "
                     f"({f8['margin_pct']:.2f} points above the tolerance, {_n(f8.get('last_pass_band_size'))} "
                     + ("records with controls)" if loc_mode else "points)"))
    if f8.get("stop_band"):
        parts.append(f"{'the' if parts else 'The'} {_e(f8['stop_band'])} % band stops the scan "
                     f"({_e(f8.get('stop_reason') or '')})")
    txt = (" " + "; ".join(parts) + ".") if parts else ""
    kind = f8.get("stop_kind")
    if kind == "too_few":
        txt += (" The scan stopped because the next band has fewer than 30 records with local controls, not because "
                "the yield fell: the automatic threshold reflects how many records found controls, not a measured drop.")
    elif kind == "tolerance":
        txt += f" The scan stopped on a measured yield drop (more than {tol:g} % below the controls)."
    return txt


def _f8_text(R) -> str:
    f8 = R.get("f8") or {}
    mode = f8.get("mode", "auto")
    tol = f8.get("tolerance_pct", 3.0)
    auto = _frac_pct(f8.get("threshold_auto"))
    thr = _frac_pct(f8.get("threshold"))
    loc = f8.get("local") or {}
    loc_mode = f8.get("reference_mode") == "local"
    pop = str(f8.get("dose_population") or "")
    if loc_mode and loc.get("population"):
        pop_txt = (f" The dose-response used the {_e(loc['population']).replace('&gt;=', '&ge;')}; the threshold "
                   "applies to every record.")
    elif pop.startswith("in-plot"):
        pop_txt = " The dose-response was measured on the in-plot records only (the field interior)."
    else:
        pop_txt = ""
    fp_txt = _f8_footprint_text(f8)
    ref_fb = (f" The local controls could not be used: only {_n(loc.get('placebo_n'))} no-overlap records have them "
              "(30 needed), so each band was compared with the no-overlap band of its combine (the v2.3 reference)."
              if loc and f8.get("reference_mode") == "field" else "")
    floor = f8.get("min_threshold")
    stop = _f8_stop_text(f8)
    if mode == "auto" and f8.get("fallback"):
        return (f"<b>{thr} %</b>, the <b>fallback</b> threshold: the lowest overlap band (0-2 %) "
                f"already fails the -{tol:g} % tolerance against {_f8_reference_text(f8)}, so this "
                f"field's dose-response cannot set the threshold (the automatic rule would stop at {auto} %). Check "
                f"the F8 figure.{pop_txt}{ref_fb}{fp_txt}")
    if mode == "auto" and f8.get("floor_applied"):
        return (f"<b>{thr} %</b>, the <b>floor</b>: this field's dose-response against "
                f"{_f8_reference_text(f8)} stops at {auto} %, below the resolution of the overlap measure, so F8 "
                f"removes the records above {_frac_pct(floor or f8.get('threshold'))} %.{stop}{pop_txt}{ref_fb}{fp_txt}")
    if mode == "auto":
        excl = f8.get("excluded_machines") or []
        excl_txt = ((f" Combine(s) {_e(', '.join(map(str, excl)))} found no local controls and are not in the "
                     "dose-response." if loc_mode else
                     f" Combine(s) {_e(', '.join(map(str, excl)))} have too small a no-overlap band to be their own "
                     "reference and were left out of the pooled curve.") if excl else "")
        if loc_mode:
            how = (f"(from 0 up, &ge; 30 records with controls) whose median yield ratio to its local no-overlap "
                   f"controls is within -{tol:g} % of the placebo {_f8_controls_text(f8)}")
        else:
            how = (f"(from 0 up, &ge; 30 points) whose mean yield is within -{tol:g} % of "
                   f"{_f8_reference_text(f8)}")
        return (f"<b>{auto} %</b>, chosen automatically from this field's dose-response: the upper edge of the last "
                f"overlap band {how}" + (f", never below {_frac_pct(floor)} %" if floor else "")
                + f".{stop}{pop_txt}{ref_fb}{excl_txt}{fp_txt}")
    if mode == "fixed":
        return (f"<b>{thr} %</b>, fixed in the settings (the dose-response would choose "
                f"{auto} %).{pop_txt}{fp_txt}")
    return f"<b>F8 switched off</b> (the dose-response would choose {auto} %); no point removed for overlap."


def _lag_text(R) -> str:
    """The flow-delay line: the scan (axis R['lag']['axis'], stage R['lag']['stage']) and the decision. Only a
    'before_f7' run says that F7 and F8 used the shifted positions; the default 'output' stage moves the output
    geometry only."""
    lag = R.get("lag") or {}
    best = lag.get("best_records")
    rbest = max((s["r"] for s in lag.get("scan") or []), default=None)
    stage = lag.get("stage")
    axis = lag.get("axis")
    applied = int(lag.get("applied_records") or 0)
    rule = _e(lag.get("rule") or "")
    on = (" on the passes of the axis the field was harvested in" if axis == "dominant" else
          " on the E-W passes whenever both directions hold &ge; 200 records (the v2.3 axis)" if axis == "ew_first"
          else "")
    where = (", measured on the records alive after F6 (pass interiors) before F7 and F8" if stage == "before_f7" else
             ", measured on the kept records after the cascade" if stage == "output" else "")
    try:
        r0 = f"{float(lag.get('r_at_0')):.3f}"
    except (TypeError, ValueError):
        r0 = "-"
    scan = (f"the scan between opposite-direction neighbours{on} peaks at {int(best):+d} records "
            f"(r = {rbest:.3f}; r at 0 = {r0}){where}" if rbest is not None and best is not None else
            f"the scan was not possible (too few opposite-direction neighbours{on}{where})")
    if applied and stage == "before_f7":
        f7 = next((c for c in R.get("cascade") or [] if c.get("filter") == "F7"), {})
        n_orph = lag.get("n_orphans") or 0
        orph = ((f"; the {_n(n_orph)} records whose source lies beyond their pass were removed with F7"
                 if f7.get("on", True) else
                 f"; F7 is off, so the {_n(n_orph)} records whose source lies beyond their pass keep the overlap of the "
                 "nearest pass end") if n_orph else "")
        return (f"{scan}; <b>every yield tied to the position {applied:+d} records away</b> along its "
                f"pass, the correction for a flow delay of {-applied:+d} records ({rule}): F7 "
                f"and F8 used those positions (the lag_stage before_f7 option) and the output geometry follows "
                f"them{orph}.")
    if applied:
        return (f"{scan}; <b>geometry shifted by {applied:+d} records</b> along each pass, the "
                f"correction for a flow delay of {-applied:+d} records ({rule})"
                + ("; the shift moves the output geometry only: F7 and F8 judged every yield at its logged position."
                   if stage == "output" else "."))
    return f"{scan}; <b>no shift applied</b> ({rule})."


LAYOUT_TEXT = {"interleaved": "interleaved passes", "mixed": "mixed", "blocks": "blocks", "no_contact": "no contact"}
METHOD_TEXT = {"auto": "auto", "cells": "paired cells", "machine": "machine x machine", "track": "track x track",
               "point": "point x point"}
GATE_TEXT = {"applied": "passes the gates", "ci_includes_1": "CI includes 1", "too_few_pairs": "too few pairs",
             "no_link": "no link", "above_max_factor": "above the max", "above_max_factor_unconfirmed":
             "above the max, not proven", "below_min_factor": "below 1 %", "sizes_disagree": "30 m / 50 m disagree",
             "spatially_inconsistent": "differs over the field", "layout": "not used (layout)"}
LIGHT_BG = {"green": colors.HexColor("#D1FAE5"), "yellow": colors.HexColor("#FEF3C7"),
            "red": colors.HexColor("#FEE2E2")}


def _machines_text(R) -> str:
    M = R.get("machines")
    if not M:
        col = R.get("columns", {}).get("machine")
        return ("one machine" + (f" (column {_e(col)} has a single value)" if col else
                                 " (no machine column mapped)") + "; no harmonisation.")
    parts = []
    for m, n in (M.get("n_points") or {}).items():
        fac = (M.get("factor_applied") or {}).get(m, 1.0)
        dec = (M.get("decision") or {}).get(m, "")
        parts.append(f"{_e(m)}: {_n(n)} points, {_n((M.get('n_kept') or {}).get(m))} kept, factor {fac:.4f}"
                     + (f" ({_e(dec)})" if dec else ""))
    req = M.get("method_requested")
    head = (f"{len(M.get('n_points') or {})} machines by the {_e(M.get('basis') or ('column ' + str(M.get('column'))))}"
            + (f", reference {_e(M['reference'])}" if M.get("reference") else "")
            + (f", method {_e(METHOD_TEXT.get(req, req))}" if req else "")
            + (" (all neighbouring pairs solved together)" if M.get("estimate") == "network" else ""))
    s = head + ". " + "; ".join(parts) + "."
    if M.get("per_machine_totals"):
        s += " Per-machine totals were given: see the Combines section."
    return s


def _ticket_label(L) -> str:
    """The grower's weight in its unit ('1,500,000 lb'; the legacy '9,000 bu' when the engine knows bushels only)."""
    v, u = L.get("ticket_value"), L.get("ticket_unit")
    if v is None:
        v, u = L.get("ticket_bu", L.get("scale_ticket_bu")), "bu"
    if v is None:
        return "-"
    return yield_clean.ticket_value_text(float(v), u)


def _ticket_bu(L):
    """The bushels the monitor total was compared with: the ticket at the standard moisture when the ticket's moisture
    was applied (ticket_compared_bu), else the ticket in bu (the same figure L and the closure use)."""
    if L.get("ticket_bu_at_standard") is not None:
        return L.get("ticket_compared_bu", L["ticket_bu_at_standard"])
    return L.get("ticket_bu", L.get("scale_ticket_bu"))


def _harmonised_differs(L) -> bool:
    """True when a combine factor changed the monitor total (the 'after the harmonisation' figures are then worth
    printing; a single combine or nothing applied prints only the one total)."""
    th = L.get("export_total_harmonised_bu")
    mon = _monitor_bu(L)
    if th is None or mon is None:
        return False
    return abs(float(th) - float(mon)) > 1e-9 * max(1.0, abs(float(mon)))


def _spct(x) -> str:
    """A signed percentage ('+5.00 %', '-0.10 %') for the closure rows; '-' when missing."""
    try:
        return f"{float(x):+.2f} %"
    except (TypeError, ValueError):
        return "-"


def _tw_source(L) -> str:
    """'test weight from the file (median ...)' whatever the engine's wording of test_weight_source."""
    s = str(L.get("test_weight_source") or "").strip()
    if not s:
        return ""
    return s if s.lower().startswith("test weight") else "test weight from " + s


def _monitor_bu(L):
    return L.get("export_total_bu", L.get("export_integral_bu"))


def _difm_column(R) -> tuple[str, str]:
    """(yield column to map, why): the cleaning engine's own decision (R['yield_column_for_difm'], the column the
    cleaning record, the final-map figure and the app name), never a second opinion. With a level the leveled column
    the engine chose: Yld_Level in an SMS 3-sigma run (the leveled SMS yield, whatever the sessions diagnostic would
    recommend), Yld_Lvl_Sy only where the engine itself named it (an OCCD run whose sessions recommend the symmetric
    basis). A record that names Yld_Harm although no combine factor was applied (the column is then a copy of the
    yield) maps the yield."""
    added = R.get("difm_ready_added_columns")
    L = R.get("level") or {}
    col = R.get("yield_column_for_difm") or (R.get("columns") or {}).get("yield") or "Yld_Vol_Dr"
    lvl = R.get("level_column_for_difm")
    sym = R.get("level_sym_column_for_difm") or R.get("level_symmetric_column_for_difm")
    if L and L.get("use") != "validate" and col in (lvl, sym) and (added is None or col in added):
        f = L.get("factor_final")
        if f is None and not L.get("per_machine"):
            f = L.get("factor_harmonised", L.get("factor"))
        why = (f"leveled to the grower's weight {_ticket_label(L)}"
               + (f" (L = {float(f):.4f})" if f is not None else (" (per-machine L)" if L.get("per_machine") else "")))
        # the sentence follows the measured integral of the column named, never an assumption
        if col == sym:
            what, gap = ("symmetric dry-matter yield x factor x L, as the harvest sessions recommend",
                         L.get("yld_lvl_sy_vs_ticket_pct"))
        else:
            what, gap = "the mapped dry yield x factor x L", L.get("yld_level_vs_ticket_pct")
        if gap is not None and abs(float(gap)) <= 0.05:
            return col, why + f": the bu/ac now sum to the scale; {what}"
        if gap is None:
            return col, why + f"; {what} (its total against the weight was not measured)"
        return col, (why + f"; {what}: it sums to {float(gap):+.2f} % of the weight compared, the gap between this "
                     f"column and the comparison column ({L.get('integral_column')})")
    fa = ((R.get("machines") or {}).get("factor_applied") or {}).values()
    if str(col).startswith("Yld_Harm") and not any(f is not None and abs(float(f) - 1) > 1e-12 for f in fa):
        col = (R.get("columns") or {}).get("yield") or "Yld_Vol_Dr"
    return col, ""


def _import_text(imp: dict) -> str:
    """The file's Import as SMS record (engine.run.import_as_sms): the settings line and the readings left out."""
    s = _e(imp.get("text") or imp.get("describe") or "")
    if not s:
        r = imp.get("resolved") or imp
        s = ", ".join(f"{_e(k)} {_e(v)}" for k, v in r.items() if not isinstance(v, (dict, list)) and v is not None)
    lo = imp.get("left_out")
    if isinstance(lo, dict) and lo:
        s += "; left out at import: " + ", ".join(f"{_n(v)} {_e(k)}" for k, v in lo.items())
    if imp.get("n_in") is not None and imp.get("n_out") is not None:
        s += f" ({_n(imp['n_in'])} readings in, {_n(imp['n_out'])} imported)"
    return s + "."


def _level_text(R) -> str | None:
    L = R.get("level")
    if not L:
        return None
    tick, mon = _ticket_bu(L), _monitor_bu(L)
    s = f"grower's weight <b>{_ticket_label(L)}</b> ({_e(L.get('ticket_basis', L.get('basis', 'wet')))} basis"
    if L.get("ticket_moisture_pct") is not None:
        s += f", {float(L['ticket_moisture_pct']):g} % moisture"
    s += ")"
    tick_as_given = L.get("ticket_bu", L.get("scale_ticket_bu"))
    own = bool(L.get("grower_bushels_applied") and L.get("ticket_bu_grower") and L.get("test_weight_grower"))
    if L.get("ticket_unit") == "bu/ac" and tick_as_given is not None and L.get("ticket_area_ac"):
        s += (f" &times; {float(L['ticket_area_ac']):,.2f} ac ({_e(L.get('ticket_area_source') or 'area')}) = "
              + (f"{float(L['ticket_bu_grower']):,.2f} bu of {float(L['test_weight_grower']):.2f} lb = "
                 f"{float(tick_as_given):,.2f} of the file's bushels" if own else f"{float(tick_as_given):,.2f} bu"))
    elif own:
        s += (f" of {float(L['test_weight_grower']):.2f} lb = {float(tick_as_given):,.2f} of the file's bushels")
    elif L.get("ticket_unit") and L.get("ticket_unit") != "bu" and tick_as_given is not None:
        s += f" = {float(tick_as_given):,.2f} bu" + (f" at {float(L['test_weight_used']):.2f} lb/bu ({_e(_tw_source(L))})"
                                                    if L.get("test_weight_used") else "")
    if L.get("ticket_bu_at_standard") is not None and tick is not None:
        s += (f" = {float(tick):,.2f} bu at the standard moisture (the ticket shrunk by the rule of the column it is "
              f"compared with, {_e(L.get('integral_column'))}: {_e(L.get('comparison_basis') or '')})")
    s += (f" / monitor total {_n(mon, 2)} bu over {_n(L.get('export_integral_area_ac', L.get('export_area_ac')), 2)} ac "
          f"(column {_e(L.get('integral_column'))}, all processed points"
          + (f"; {_n(L.get('export_total_lb'))} lb" if L.get("export_total_lb") else ""))
    if _harmonised_differs(L) and "factor_harmonised" in L:
        # the L in the file (and of the band and the verdict) is the one after the combine factor: that one in bold
        s += (f") = L = {float(L['factor']):.4f} before the combine factor; with it the monitor total is "
              f"{_n(L.get('export_total_harmonised_bu'), 2)} bu and <b>L = {L['factor_harmonised']:.4f}</b>")
    else:
        s += f") = <b>L = {float(L['factor']):.4f}</b>"
    c = L.get("closure") or {}
    if c.get("verdict"):
        s += f". {_e(c['verdict'])}"
    if "inside_boundary_integral_bu" in L:
        s += (f". Inside the boundary: {L['inside_boundary_integral_bu']:,.2f} bu over "
              f"{L['inside_boundary_area_ac']:,.2f} ac ({L['n_points_outside_boundary']:,} points outside; diagnostic only)")
    for kb, ka in (("inside_aoi_integral_bu", "inside_aoi_area_ac"), ("aoi_integral_bu", "aoi_area_ac")):
        if kb in L:
            s += f". Inside the field of interest (0 m): {L[kb]:,.2f} bu" + (f" over {L[ka]:,.2f} ac" if ka in L else "")
            break
    return s + "."


def _source_text(R) -> str:
    src = R.get("source")
    if not src:
        return "point export as given (no decoding)."
    s = f"decoded from a raw monitor dataset by the app: <b>{_e(src.get('label', src.get('format', '?')))}</b>"
    if src.get("units"):
        u = [str(x) for x in src["units"]]
        s += f"; {len(u)} unit(s): " + "; ".join(_e(x) for x in u[:6]) + (" ..." if len(u) > 6 else "")
    cal = src.get("calibration_summary")
    if cal:
        s += "; " + _e(cal)
    if src.get("decode_report"):
        s += f". Decode report: {_e(os.path.basename(src['decode_report']))}"
    return s + "."


def _aoi_text(R) -> str | None:
    A = R.get("aoi")
    if not A:
        return None
    s = f"<b>{_e(os.path.basename(str(A.get('file', ''))))}</b>: {_n(A.get('n_polygons'))} polygon(s)"
    if A.get("n_plots"):
        s += f", {_n(A['n_plots'])} plots" + (f" and {_n(A['headland_polygons'])} headland/border polygon(s)"
                                             if A.get("headland_polygons") else "")
    if A.get("area_ac") is not None:
        s += f", {_n(A['area_ac'], 2)} ac"
    s += (f". {_n(A.get('n_outside_buffer'))} points outside the field + {_n(A.get('buffer_m'))} m buffer were "
          f"dropped before the cascade; {_n(A.get('n_in'))} processed")
    if A.get("n_output_outside_aoi") is not None:
        s += (f"; {_n(A['n_output_outside_aoi'])} kept points outside the field itself were left out of the clean "
              "file (column In_AOI in the flagged file)" if A.get("clip_output", True) else
              f"; {_n(A['n_output_outside_aoi'])} kept points lie outside the field itself (not clipped; In_AOI)")
    return s + "."


def _moisture_text(R) -> str | None:
    Mo = R.get("moisture")
    if not Mo:
        return None
    ms = Mo.get("standard_pct")
    s = (f"standard moisture <b>{ms:g} %</b>" if isinstance(ms, (int, float)) else "standard moisture unknown")
    if Mo.get("source"):
        s += f" ({_e(Mo['source'])})"
    sh = Mo.get("shrink")
    if sh:
        s += {"one_sided": "; the mapped dry yield is <b>one-sided</b> (readings below the standard are not raised)",
              "symmetric": "; the mapped dry yield is <b>symmetric</b> (dry-matter basis both ways)"}.get(
            sh, f"; shrink {_e(sh)}")
    if Mo.get("shrink_source"):
        s += f" ({_e(Mo['shrink_source'])})"
    if Mo.get("share_below_standard") is not None:
        s += (f"; {_pct(Mo['share_below_standard'])} of the readings ({_n(Mo.get('n_below_standard'))}) are below "
              "the standard")
    if R.get("dry_symmetric_column") or Mo.get("column"):
        s += f". Column <b>{_e(R.get('dry_symmetric_column') or Mo.get('column'))}</b> holds the symmetric dry yield"
    return s + "."


def _sms_sessions_note(R, rec: str) -> str:
    """SMS 3-sigma: the file maps the export's dry yield as SMS does, so the sessions recommendation ('map Yld_Dry_Sy
    ...') is an OCCD diagnostic there; print the engine's note so the sessions rows agree with the clean file row."""
    for n in R.get("notes") or []:
        if str(n).startswith("sessions (diagnostic): "):
            return str(n)
    if "Yld_Dry_Sy" in str(rec):
        return ("sessions (diagnostic): " + str(rec) + "; the SMS 3-sigma file maps the export's dry yield as SMS "
                "does" + (" - Yld_Dry_Sy (scaled the same way) is also in the file"
                          if "Yld_Dry_Sy" in (R.get("difm_ready_added_columns") or []) else ""))
    return str(rec)


def _sessions_said(R, rec: str) -> str:
    """The sessions recommendation as a diagnostic when the clean file does not map the symmetric column: 'the sessions
    diagnostic would recommend Yld_Dry_Sy ...' instead of the imperative 'map Yld_Dry_Sy as the yield ...', so the
    row never contradicts the yield column to map a few lines below."""
    col = str(R.get("yield_column_for_difm") or "")
    sym_cols = {R.get("dry_symmetric_column_for_difm"), R.get("level_sym_column_for_difm"),
                R.get("level_symmetric_column_for_difm"), "Yld_Dry_Sy", "Yld_Lvl_Sy"} - {None}
    lead = "map Yld_Dry_Sy as the yield and keep Harv_Day as a block: "
    if lead in str(rec) and col not in sym_cols:
        return str(rec).replace(lead, "the sessions diagnostic would recommend Yld_Dry_Sy (with Harv_Day as a block); "
                                      "the clean file maps " + col + ": ")
    return str(rec)


def _sessions_brief(R) -> str | None:
    Se = R.get("sessions")
    if not Se or not Se.get("table"):
        return None
    T = Se["table"]
    days = sorted({str(r.get("day")) for r in T})
    machines = sorted({str(r.get("machine")) for r in T})
    s = (f"<b>{len(T)} session(s)</b> (machine x day): {len(machines)} machine(s) over {len(days)} day(s) "
         f"({', '.join(_e(d) for d in days[:6])}{' ...' if len(days) > 6 else ''})")
    rec = Se.get("recommendation")
    if isinstance(rec, dict):
        rec = rec.get("text")
    if rec and _is_sms(R):
        rec = _sms_sessions_note(R, rec)
    if rec:
        s += f". {_e(_sessions_said(R, rec))}"
    return s + "."


def _settings_rows(S):
    """(filter rows, rows switched off, general rows). The general rows are those of the run's method: an SMS 3-sigma
    run leaves out the OCCD-only settings (flow delay, the pass break, the v1 aliases), and any run leaves out a v1
    alias whose v2 key is set (scale_ticket_bu / scale_ticket_basis next to scale_ticket, boundary next to aoi.file,
    harmonise_machines next to machines.harmonise)."""
    from engine.clean.yield_clean import FILTER_INFO, FILTER_ORDER
    rows = [["Filter", "On", "Parameters"]]
    off = []
    for k, fid in enumerate(FILTER_ORDER):
        p = S["filters"][fid]
        params = ", ".join(f"{a} = {v}" for a, v in p.items() if a != "on") or "-"
        rows.append([f"{fid} {_e(FILTER_INFO[fid]['name'])}", "yes" if p["on"] else "no", _e(params)])
        if not p["on"]:
            off.append(k)
    sms = str(S.get("method") or "") == "sms3sigma"
    tk = S.get("scale_ticket") if isinstance(S.get("scale_ticket"), dict) else {}
    aoi = S.get("aoi") if isinstance(S.get("aoi"), dict) else {}
    skip = set()
    if sms:
        skip |= {"lag_correction", "lag_stage", "lag_axis", "harmonise_machines", "scale_ticket_bu",
                 "scale_ticket_basis", "boundary", "pass_break"}
    if tk.get("value") is not None:
        skip |= {"scale_ticket_bu", "scale_ticket_basis"}
    if aoi.get("file"):
        skip.add("boundary")
    if isinstance(S.get("machines"), dict):
        skip.add("harmonise_machines")
    gen = [["Setting", "Value"]]
    for k in ("tag", "method", "crop", "harvester_width_ft", "test_weight_lb_bu", "lag_correction", "lag_stage",
              "lag_axis", "harmonise_machines", "scale_ticket_bu", "scale_ticket_basis", "boundary"):
        if k in S and k not in skip:
            v = S.get(k)
            gen.append([k, _e("-" if v is None else v)])
    for k in ("scale_ticket", "pass_break", "aoi", "moisture", "machines"):
        v = S.get(k)
        if isinstance(v, dict) and k not in skip and not (k == "scale_ticket" and v.get("value") is None):
            gen.append([k, _e(", ".join(f"{a} = {b}" for a, b in v.items()))])
    imp = S.get("sms_import")
    if isinstance(imp, dict):
        gen.append(["sms_import", _e(", ".join(f"{a} = {b}" for a, b in (imp.get("resolved") or imp).items()
                                               if not isinstance(b, (dict, list))))])
    return rows, off, gen


SOURCES_IN_TABLE = 2        # short names per cascade row; the rest are in the References section and references.py


def _sources_cell(c) -> str:
    """The works behind one cascade row: the first short names from references.py when the step is known (the house
    convention always named, cut at its parenthesis), else the JSON's text."""
    fid = c.get("filter")
    if fid in refs.SOURCES:
        return _e(refs.cite(fid, notes=False, max_items=SOURCES_IN_TABLE, house="short"))
    return _e(c.get("source", ""))


def _is_sms(R) -> bool:
    return R.get("method") == "sms3sigma"


def _sms_filter_names(R) -> tuple:
    """(first, second) of the two filters between the swath step and the yield passes, in the order the cleaning ran
    them (a record made before the order became a setting ran speed, then moisture)."""
    from engine.clean import sms3sigma
    at = sms3sigma.step_attributes(sms3sigma.filter_order_of(R.get("sms3sigma") or {}))
    return at["S3"], at["S4"]


def _sms_steps_on(R) -> list:
    """The SMS steps that ran, in their order, as (id, attribute or None): read from the cascade rows (the order of
    the run, whatever the settings default), the clip counted when the field-of-interest pre-step did it."""
    out = []
    pre_clip = any(str(p.get("step", "")).upper() == "AOI" and p.get("removed") for p in (R.get("pre_steps") or []))
    for c in R.get("cascade") or []:
        fid = str(c.get("filter", ""))
        if not c.get("on", True) and not (fid == "S1" and pre_clip):
            continue
        if fid.startswith("S5") and len(fid) > 2 and fid[2] != "a":
            continue                                   # the later yield passes are counted with the first
        out.append((fid, c.get("attribute")))
    return out


def _sms_method_text(R) -> str:
    M = R.get("sms3sigma") or {}
    G = M.get("grouping") or {}
    P = M.get("settings") or {}
    passes = M.get("yield_passes") or {}
    pv = sorted(set(passes.values()))
    ptxt = (f"{pv[0]} dry-yield pass(es)" if len(pv) == 1 else
            f"{min(pv)}-{max(pv)} dry-yield passes depending on the group") if pv else "no dry-yield pass"
    words = {"S1": "clip to the field", "S2": "Optimize Swath Widths"}
    seq, filt = [], []
    for fid, attr in _sms_steps_on(R):
        if fid in words:
            seq.append(words[fid])
        elif fid in ("S3", "S4") or fid.startswith("S5"):
            filt.append(attr or ("dry yield" if fid.startswith("S5") else fid))
    if filt:
        seq.append((", ".join(filt[:-1]) + " and " + filt[-1] if len(filt) > 1 else filt[0])
                   + f" each kept within mean &plusmn; {P.get('k_sd', 3):g} SD recomputed on the points still alive")
    head = ", then ".join(seq[:2]) if len(seq) <= 2 else ", ".join(seq[:2]) + ", then " + ", then ".join(seq[2:])
    return (f"<b>SMS 3-sigma</b> (the Ag Leader SMS Advanced sequence of the house procedure): "
            + (head or "every step switched off") + f"; {ptxt}"
            + (f" (another pass only while the SD fell by more than {P.get('sd_drop_pct', 25):g} %)" if pv else "")
            + f". Mean and SD per <b>{_e(G.get('mode', '?'))}</b> "
            f"({G.get('n_groups', '?')} group(s): {_e(G.get('rule', ''))}).")


def _sms_swath_text(R) -> str:
    sw = (R.get("sms3sigma") or {}).get("swath") or {}
    if not sw:
        return "switched off"
    t = (f"{_n(sw.get('n_removed'))} fully overlapped readings removed, {_n(sw.get('n_narrowed'))} narrowed to the "
         "uncovered strip and moved to its centre")
    if sw.get("min_width_ft") is not None:
        t += f" (narrowest {sw['min_width_ft']:.2f} ft, largest scale x {sw.get('max_scale', float('nan')):.2f})"
    if sw.get("n_shortened"):
        t += f"; {_n(sw['n_shortened'])} shortened at the back (Distance trimmed, Speed recomputed)"
    if int(sw.get("swath_passes") or 1) > 1:
        t += (f"; {int(sw['swath_passes'])} passes of Clip + Optimize Swath Widths (an SMS chain where the two were "
              "added that many times)")
    if sw.get("order"):
        t += f"; order: {_e(sw['order'])}"
    return t + (f"; model: {_e(sw.get('model'))}" if sw.get("model") else "") + "."


def _section_sms_limits(story, R, num):
    M = R.get("sms3sigma") or {}
    steps = M.get("steps") or []
    P = M.get("settings") or ((R.get("settings") or {}).get("sms3sigma") or {})
    dec, floor = P.get("round_decimals", 2), P.get("yield_floor", 0.0)
    rnd = f"rounded half up to {int(dec)} decimal(s)" if dec is not None else "at full precision"
    flr = f"the dry-yield floor {float(floor):g}" if floor is not None else "no dry-yield floor"
    story.append(Paragraph(f"{num}. SMS 3-sigma limits per group", H2))
    story.append(Paragraph(
        "The mean and SD of each attribute on the points still alive before the step (the plain point statistics of "
        f"SMS Edit Legend), the limits typed into Filter Data (mean &plusmn; {float(P.get('k_sd', 3)):g} SD, {rnd}; "
        f"{flr}) and what each removed. The dry yield is the yield scaled by Optimize Swath Widths. "
        + _e((M.get("clip") or {}).get("note", "")) + ".", SUB))
    rows = [["Group", "Step", "n before", "Mean", "SD", "Low", "High", "Removed", "SD after", "SD drop"]]
    for s_ in steps:
        if s_.get("lo") is None:
            rows.append([_e(str(s_["group"])[:30]), _e(s_["step"]), _n(s_["n_before"]), "-", "-", "-", "-", "0", "-",
                         _e(s_.get("note") or "")])
            continue
        rows.append([_e(str(s_["group"])[:30]), _e(f"{s_['step']} {s_['attribute']}"), _n(s_["n_before"]),
                     f"{s_['mean']:.3f}", f"{s_['sd']:.3f}", f"{s_['lo']:.2f}", f"{s_['hi']:.2f}", _n(s_["removed"]),
                     (f"{s_['sd_after']:.3f}" if s_.get("sd_after") is not None else "-"),
                     (f"{s_['sd_drop_pct']:.2f} %" + (" &rarr; again" if s_.get("next_pass") else "")
                      if s_.get("sd_drop_pct") is not None else "-")])
    t = _table(rows, [1.33 * inch, 1.05 * inch, 0.6 * inch, 0.55 * inch, 0.5 * inch, 0.5 * inch, 0.55 * inch,
                      0.67 * inch, 0.55 * inch, 0.65 * inch], small=True)
    t.setStyle(TableStyle([("ALIGN", (2, 0), (-1, -1), "RIGHT")]))
    story.append(t)
    imx = _import_max_text(M.get("import_max"))
    if imx:
        story.append(Paragraph(imx, SUB))


def _import_max_text(X) -> str:
    """The import's maximum next to S5a (yield_clean.import_max_check): the maximum, where it came from, the readings
    it left out (per combine) and, per S5a group, whether the maximum is below the group's upper limit or the dry
    yield ran one pass after readings were left out."""
    if not isinstance(X, dict) or not X:
        return ""
    mx = X.get("max_yield")
    s = ("Import maximum: " + ("none" if mx is None else f"{float(mx):,.2f} bu/ac")
         + (f" ({_e(X['max_yield_source'])})" if X.get("max_yield_source") else "")
         + f"; readings it left out before the cleaning: {_n(X.get('left_out') or 0)}")
    by = X.get("left_out_by_group") or {}
    if by:
        s += " (" + ", ".join(f"{_e(k)} {_n(v)}" for k, v in sorted(by.items())) + ")"
    flags = []
    for g in X.get("groups") or []:
        f = []
        if g.get("max_below_s5a_hi"):
            f.append(f"the maximum is below its S5a upper limit {float(g['s5a_hi']):,.2f}")
        if g.get("one_pass_after_left_out"):
            f.append("one dry-yield pass after readings were left out at import")
        if f:
            flags.append(f"{_e(str(g.get('group'))[:30])}: " + " and ".join(f))
    if flags:
        s += (". " + "; ".join(flags) + " (the high readings were decided by the import's maximum, as SMS's import "
              "does with the same value, not by the 3-sigma step)")
    return s + "."


def _sms_settings_rows(S):
    P = S.get("sms3sigma") or {}
    rows = [["SMS 3-sigma setting", "Value"]]
    for k, v in P.items():
        rows.append([_e(k), _e("-" if v is None else v)])
    return rows


# ------------------------------------------------------------------------------------------------- sections
def _section_aoi(story, A, num, sms=False, clip=None):
    story.append(Paragraph(f"{num}. Field of interest", H2))
    if sms:
        tol = (clip or {}).get("tolerance_m")
        story.append(Paragraph(
            "The boundary file is the field SMS clips to (Clip To Field Boundary, S1): the readings whose logged point "
            "lies outside it are set aside before the import check"
            + (f" (a point within {100 * float(tol):g} cm of the edge counts as inside)" if tol is not None else "")
            + " and are not in the flagged file; the swath step, the 3-sigma statistics, the area and the averages use "
            "the readings inside only. When the file holds plots, Plot_Id (and Tgt_Rate) are added to the outputs. "
            f"{_e(refs.cite('aoi', notes=False))}.", BODY))
    else:
        story.append(Paragraph(
            "The plan or boundary file defines the field of interest. Records outside it plus the processing buffer "
            "are dropped before the cascade (the headland context is kept for the pass structure, the overlap raster, "
            "the lag scan and F7); when the output is clipped, the clean file keeps only kept points inside the field "
            "itself. When the file holds plots, Plot_Id (and Tgt_Rate) are added to both outputs and the F8 "
            f"dose-response uses the in-plot records only. {_e(refs.cite('aoi', notes=False))}.", BODY))
    rates = A.get("rates") or []
    rows = [["Item", "Value"],
            ["File", _e(A.get("file", "-"))],
            ["CRS of the file", _e(A.get("crs", "-"))],
            ["Polygons", f"{_n(A.get('n_polygons'))} ({_n(A.get('n_plots'))} plots, "
                         f"{_n(A.get('headland_polygons'))} headland / border)"],
            ["Area (0 m)", f"{_n(A.get('area_ac'), 2)} ac"]]
    if sms:
        rows += [["Clip tolerance", f"{100 * float(A.get('buffer_m') or 0):g} cm"],
                 ["Records inside the boundary (processed)", _n(A.get("n_in"))],
                 ["Records outside (clipped, S1)", _n(A.get("n_outside_buffer"))]]
    else:
        rows += [["Processing buffer", f"{_n(A.get('buffer_m'))} m"],
                 ["Records inside field + buffer (processed)", _n(A.get("n_in"))],
                 ["Records outside the buffer (dropped before the cascade)", _n(A.get("n_outside_buffer"))]]
    rows += [
            ["Kept points outside the field itself", f"{_n(A.get('n_output_outside_aoi'))}"
             + (" (left out of the clean file)" if A.get("clip_output", True) else " (kept; In_AOI = 0)")],
            ["Plot id column", _e(A.get("id_col") or "-")],
            ["Rate column", _e(A.get("rate_col") or "-")],
            ["Target rates", ", ".join(_n(r, 2) if isinstance(r, float) else _e(r) for r in rates) or "-"]]
    story.append(_table(rows, [2.9 * inch, TEXT_W - 2.9 * inch], header=True, bold_first=True))


def _session_label(r) -> str:
    return _e(r.get("session") or f"{r.get('machine', '')} {r.get('day', '')}".strip())


def _section_sessions(story, R, num):
    Se = R["sessions"]
    T = Se.get("table") or []
    Mo = R.get("moisture") or {}
    ms = Mo.get("standard_pct")
    story.append(Paragraph(f"{num}. Harvest sessions", H2))
    story.append(Paragraph(
        "A session is one machine on one calendar day (columns Session and Harv_Day in both outputs)"
        + (f"; here: {_e(Se['basis'])}" if Se.get("basis") else "")
        + ". Grain moisture and the sensor's response change between days, so the sessions are compared, never "
        "corrected: the table gives each session's readings, kept points, area, wet bushels, moisture and the mean "
        "yield on the three bases (wet; dry as mapped by the monitor; dry on the symmetric dry-matter basis, column "
        "Yld_Dry_Sy)" + (f", with the standard moisture at {ms:g} %" if isinstance(ms, (int, float)) else "")
        + f". {_e(refs.cite('sessions', notes=False))}.", BODY))
    if T:
        rows = [["Session", "Dataset(s)", "Start - end", "Readings", "Kept", "Area ac", "Wet bu", "Moist. % (sd)",
                 "Below std", "Wet", "Dry map", "Dry sym"]]
        rows[0] = [h.replace("Below std", "Below<br/>std") for h in rows[0]]
        for r in T:
            ds = r.get("datasets") or r.get("dataset") or "-"
            if isinstance(ds, (list, tuple)):                       # a GreenStar session may hold 20+ loads
                ds = (", ".join(str(x) for x in ds[:2]) + (f" + {len(ds) - 2} more" if len(ds) > 2 else "")) or "-"
            ds = str(ds)[:60]
            se = (f"{_e(str(r['start'])[-8:])} - {_e(str(r['end'])[-8:])}" if r.get("start") and r.get("end")
                  else "-")
            rows.append([_session_label(r), _e(ds), se, _n(r.get("n_readings")), _n(r.get("n_kept")),
                         _n(r.get("area_ac"), 2), _n(r.get("wet_bu")),
                         f"{_n(r.get('mean_moisture'), 2)} ({_n(r.get('sd_moisture'), 2)})",
                         _pct(r.get("share_below_standard_kept", r.get("share_below_standard")), 0),
                         _n(r.get("mean_wet_yield"), 2),
                         _n(r.get("mean_dry_yield"), 2), _n(r.get("mean_dry_sym"), 2)])
        w = [1.1, 0.85, 0.72, 0.7, 0.55, 0.45, 0.5, 0.68, 0.52, 0.42, 0.45, 0.45]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (3, 0), (-1, -1), "RIGHT")]))
        story.append(t)
        story.append(Paragraph("Yields in bu/ac: wet = as logged; dry map = the monitor's dry yield as exported; "
                               "dry sym = wet x (100 - M) / (100 - standard), both ways; below std = share of the "
                               "KEPT readings of the session below the standard moisture (the moisture line above "
                               "gives the share over every processed reading).", CAP))
    Fd = Se.get("field") or {}
    if Fd:
        s = []
        if Fd.get("mean_mass_per_area_all") is not None:
            s.append(f"field mean over all processed readings (mass / area"
                     + (f", {_e(Fd['mean_mass_per_area_basis'])}" if Fd.get("mean_mass_per_area_basis") else "")
                     + (f", {_n(Fd['area_ac'], 2)} ac" if Fd.get("area_ac") is not None else "")
                     + f") <b>{_n(Fd['mean_mass_per_area_all'], 2)}</b>")
        if Fd.get("cleaned_map_mean") is not None:
            s.append(f"mean of the cleaned map <b>{_n(Fd['cleaned_map_mean'], 2)}</b>"
                     + (f" ({_n(Fd['cleaned_map_mean_dry_sym'], 2)} on the symmetric dry basis)"
                        if Fd.get("cleaned_map_mean_dry_sym") is not None else ""))
        if s:
            story.append(Paragraph("Field level: " + "; ".join(s) + (f". {_e(Fd['note'])}" if Fd.get("note") else "")
                                   + ".", BODY))
    Off = Se.get("offsets") or []
    if Off:
        story.append(Paragraph("Discontinuity between consecutive sessions of the same machine (paired 30 m cells "
                               "between adjacent passes of the two sessions, same plot / rate when a plan exists; "
                               "yield ratio = second / first, geometric mean with a block-bootstrap CI over pass "
                               "pairs; diagnostic, never corrected):", BODY))
        rows = [["Machine", "Session 1", "Session 2", "Cells", "Pass pairs", "Yield ratio 2/1", "95 % CI",
                 "Moist. 2 - 1 (pts)", "Status"]]
        for o in Off:
            ci = (f"{_n(o.get('ci_lo'), 3)} - {_n(o.get('ci_hi'), 3)}" if o.get("ci_lo") is not None else "-")
            ratio = o.get("yield_ratio_2_over_1", o.get("yield_ratio"))
            mdiff = o.get("moisture_diff_2_minus_1", o.get("moisture_diff"))
            rows.append([_e(o.get("machine", "-")), _e(o.get("session_1", o.get("session_a", "-"))),
                         _e(o.get("session_2", o.get("session_b", "-"))), _n(o.get("n_cells")),
                         _n(o.get("n_pass_pairs")), _n(ratio, 3), ci, _n(mdiff, 2), _e(o.get("status", ""))])
        w = [0.72, 1.12, 1.12, 0.45, 0.6, 0.75, 0.95, 0.8, 1.2]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (3, 0), (7, -1), "RIGHT")]))
        story.append(t)
    rec = Se.get("recommendation")
    if isinstance(rec, dict):
        rec = rec.get("text") or "; ".join(str(x) for x in (rec.get("reasons") or []))
    if rec and _is_sms(R):
        rec = _sms_sessions_note(R, rec)
    if rec:
        story.append(Paragraph(f"<b>Recommendation.</b> {_e(rec)}", BODY))
    fig = _g(R, "files", "figures", "sessions") or os.path.join(_g(R, "files", "dir", default=""),
                                                                 "fig_clean_sessions.png")
    if fig and os.path.exists(fig):
        story.append(KeepTogether([_image(fig, TEXT_W, 2.3 * inch),
                                   Paragraph("Moisture and dry yield against time, coloured by session; the line is "
                                             "the standard moisture.", CAP)]))


def _section_machines(story, R, num):
    M = R["machines"]
    story.append(Paragraph(f"{num}. Combines", H2))
    story.append(Paragraph(
        f"{len(M.get('n_points') or {})} machines by the {_e(M.get('basis') or ('column ' + str(M.get('column'))))}"
        + (f"; reference <b>{_e(M['reference'])}</b>" if M.get("reference") else "")
        + f". {_e(M.get('method') or M.get('rule') or '')} {_e(refs.cite('machines', notes=False))}.", BODY))
    means = M.get("means") or {}
    rows = [["Machine", "Points", "Kept", "Area ac", "Wet bu", "Field mean", "Moist. %", "Map mean", "Factor",
             "Decision"]]
    for m in sorted(M.get("n_points") or {}):
        mm = means.get(m) or {}
        rows.append([_e(m), _n(_g(M, "n_points", m)), _n(_g(M, "n_kept", m)), _n(mm.get("area_ac"), 2),
                     _n(mm.get("wet_bu")), _n(mm.get("mass_per_area_mean"), 2), _n(mm.get("moisture_mean"), 2),
                     _n(mm.get("cleaned_map_mean"), 2), _n(_g(M, "factor_applied", m, default=1.0), 4),
                     _e(_g(M, "decision", m, default=""))])
    w = [0.85, 0.55, 0.55, 0.55, 0.6, 0.7, 0.6, 0.7, 0.55, 1.6]
    scale = TEXT_W / (sum(w) * inch)
    t = _table(rows, [x * inch * scale for x in w], small=True)
    t.setStyle(TableStyle([("ALIGN", (1, 0), (8, -1), "RIGHT")]))
    story.append(t)
    story.append(Paragraph("Field mean = mass per area over all processed readings of the machine; map mean = mean "
                           "of its kept points (bu/ac).", CAP))
    lay = M.get("layout") or []
    if lay:
        story.append(Paragraph("<b>How the combines shared the field</b> (adjacency = the share of each combine's passes "
                               "with &ge; 10 kept points within 1.5 header widths of the other combine, mean of the "
                               "two; &ge; 50 % interleaved passes, 10-50 % mixed, &lt; 10 % blocks; mixing = the share "
                               "of the 100 m squares both cut):", BODY))
        rows = [["Machine a", "Machine b", "Adjacency %", "Mixing %", "Harvest layout"]]
        for r in lay:
            rows.append([_e(r.get("a")), _e(r.get("b")), _n(100 * float(r.get("adjacency") or 0), 0),
                         _n(100 * float(r.get("mixing") or 0), 0), _e(LAYOUT_TEXT.get(r.get("layout"), r.get("layout")))])
        w = [1.5, 1.5, 0.8, 0.7, 1.3]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (2, 0), (3, -1), "RIGHT")]))
        story.append(t)
        story.append(Spacer(1, 6))
    meths = M.get("methods") or []
    if meths:
        req = M.get("method_requested") or "auto"
        story.append(Paragraph(f"<b>The four methods</b> (chosen: {_e(METHOD_TEXT.get(req, req))}; after "
                               f"{_e(M.get('after') or 'the cleaning')}). Light = how far the method can be trusted "
                               "for the harvest layout (pseudo-combine tests: green reliable, yellow with care, red not "
                               "reliable); result = what the gates say for that method; used = the method of the "
                               "factor applied:", BODY))
        rows = [["Machine", "Method", "Light", "Factor", "95 % CI", "Based on", "Result", "Used"]]
        bg = []
        # the grower's weight's verdict on a factor above the max (machines.ticket_closure writes it into the tests)
        tk_out = {str(t.get("machine")): (t.get("ticket"), t.get("method", "cells")) for t in (M.get("tests") or [])
                  if t.get("ticket")}
        tk_words = {"confirmed": "; the grower's weight confirmed it: applied",
                    "would_confirm": "; the grower's weight would confirm it (validate only: not applied)",
                    "not_confirmed": "; the grower's weight did not confirm it"}
        for k, r in enumerate(meths):
            ci = (f"{_n(r.get('ci_lo'), 4)} - {_n(r.get('ci_hi'), 4)}" if r.get("ci_lo") is not None else "-")
            based = (f"{_n(r.get('n_units'))} {_e(r.get('unit') or '')}" if r.get("n_units") is not None else "-")
            res = GATE_TEXT.get(r.get("gate"), r.get("gate") or "-")
            o_ = tk_out.get(str(r.get("machine")))
            if o_ and r.get("gate") == "above_max_factor" and (r.get("used") or r.get("method") == o_[1]):
                res += tk_words.get(o_[0], "")
            rows.append([_e(r.get("machine")), _e(METHOD_TEXT.get(r.get("method"), r.get("label"))),
                         _e(r.get("light") or "-"), _n(r.get("factor"), 4), ci, based,
                         _e(res), "yes" if r.get("used") else ""])
            if r.get("light") in LIGHT_BG:
                bg.append(("BACKGROUND", (2, k + 1), (2, k + 1), LIGHT_BG[r["light"]]))
        w = [1.05, 1.05, 0.5, 0.55, 1.0, 1.05, 1.1, 0.4]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (3, 0), (3, -1), "RIGHT")] + bg))
        story.append(t)
        adv = M.get("advice") or {}
        if adv:
            story.append(Paragraph("Why a factor estimated was not applied: " + "; ".join(
                f"<b>{_e(m)}</b>: {_e(a)}" for m, a in sorted(adv.items())) + ".", CAP))
        story.append(Spacer(1, 6))
    pairs = [p for p in (M.get("pairs") or []) if p.get("cell_m") == 30]
    if len(pairs) > 1:
        story.append(Paragraph("Pairs of machines that harvested side by side (30 m cells with &ge; 5 kept points of "
                               "both; ratio a / b = exp(mean log(a / b)); a pair is used when it has enough cells and "
                               "pass pairs at 30 m and 50 m):", BODY))
        rows = [["Machine a", "Machine b", "Cells", "Pass pairs", "a / b", "95 % CI", "Used"]]
        for p_ in pairs:
            ci = (f"{_n(p_.get('ci_lo'), 4)} - {_n(p_.get('ci_hi'), 4)}" if p_.get("ci_lo") is not None else "-")
            rows.append([_e(p_.get("a")), _e(p_.get("b")), _n(p_.get("n_cells")), _n(p_.get("n_pass_pairs")),
                         _n(p_.get("factor_a_over_b"), 4), ci, "yes" if p_.get("linked") else "no"])
        w = [1.2, 1.2, 0.5, 0.65, 0.6, 1.2, 0.45]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (2, 0), (-2, -1), "RIGHT")]))
        story.append(t)
    tests = M.get("tests") or []
    if tests:
        story.append(Paragraph(("Factor of each machine against the reference, all used pairs solved together "
                                "(weighted least squares on the log ratios, reference = 1)" if M.get("estimate") ==
                                "network" else "Paired cells against the reference") +
                               " (factor = what multiplies the machine to read like the reference; CI by block "
                               "bootstrap over pass pairs; half 1 / half 2 = the factor in each half of the machine's "
                               "contact cells, which must agree; whole field = map mean ratio, a diagnostic never "
                               "applied):", BODY))
        wf = M.get("whole_field_ratio") or {}
        rows = [["Machine", "Method", "Units", "Pass pairs", "Factor", "95 % CI", "Half 1", "Half 2", "Whole field"]]
        for t_ in tests:
            ci = (f"{_n(t_.get('ci_lo'), 4)} - {_n(t_.get('ci_hi'), 4)}" if t_.get("ci_lo") is not None else "-")
            sp = t_.get("spatial") or {}
            mt = t_.get("method", "cells")
            rows.append([_e(t_.get("machine")),
                         (f"cells {_n(t_.get('cell_m'))} m" if mt == "cells" else _e(METHOD_TEXT.get(mt, mt))),
                         _n(t_.get("n_cells") if mt == "cells" else t_.get("n_units")),
                         _n(t_.get("n_pass_pairs")), _n(t_.get("factor"), 4), ci, _n(sp.get("factor_half_1"), 4),
                         _n(sp.get("factor_half_2"), 4),
                         _n(wf.get(t_.get("machine")), 4) if t_.get("primary", t_.get("cell_m") == 30) else ""])
        w = [1.0, 0.45, 0.5, 0.6, 0.6, 1.15, 0.6, 0.6, 0.7]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
        story.append(t)
    P = M.get("per_machine_totals")
    if P:
        story.append(Paragraph("Per-machine totals (cart or scale weights per combine): L_m = ticket_m / integral_m on "
                               "the wet basis; Yld_Level = yield x L_m and Yld_Harm = yield x L_m / L_reference.", BODY))
        rows = [["Machine", "Ticket bu", "Integral bu", "L_m", "L_m / L_ref"]]
        for m in sorted(P):
            pm = P[m] if isinstance(P[m], dict) else {"ticket_bu": P[m]}
            rows.append([_e(m), _n(pm.get("ticket_bu"), 2), _n(pm.get("integral_bu"), 2), _n(pm.get("L"), 4),
                         _n(pm.get("relative_to_ref", pm.get("relative")), 4)])
        t = _table(rows, [1.4 * inch, 1.2 * inch, 1.2 * inch, 1.0 * inch, 1.0 * inch])
        t.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
        story.append(t)
    V = M.get("validation")
    if V:
        if isinstance(V, dict) and "agreement" not in V:
            lines = [f"{_e(m)}: " + ", ".join(f"{_e(a)} = {_n(b, 4) if isinstance(b, (int, float)) else ('-' if b is None else _e(b))}"
                                               for a, b in v.items() if a != "paired_factor_ungated")
                     for m, v in V.items() if isinstance(v, dict)]
        else:
            lines = [", ".join(f"{_e(a)} = {_n(b, 4) if isinstance(b, (int, float)) else _e(b)}" for a, b in V.items())]
        story.append(Paragraph("Validation of the paired-cell estimate against the per-machine totals "
                               "(agreement = (L_m / L_ref) / f_paired - 1): " + "; ".join(lines) + ".", BODY))
    _section_seams(story, R)


def _fig_block(story, R, key, title, caption, max_h):
    """A figure of the run with its bold title and caption, kept together on one page; nothing when not written."""
    p = _g(R, "files", "figures", key)
    if not p or not os.path.exists(p):
        return
    story.append(KeepTogether([Paragraph(title, BODY), _image(p, TEXT_W, max_h), Paragraph(caption, CAP)]))


def _final_map(story, R):
    """The final map (fig_clean_final.png): the yield column to map over the points of the clean file."""
    fm = R.get("final_map") or {}
    applied = "; ".join(_e(a) for a in (fm.get("applied") or []))
    _fig_block(story, R, "final", f"<b>Final map</b>: {_e(fm.get('column', ''))}, the yield to map",
               f"The {_n(fm.get('n_points'))} points of the clean file with their own values ({_e(fm.get('values_from') or '')}); "
               f"mean {_n(fm.get('mean'), 2)}, median {_n(fm.get('median'), 2)}, SD {_n(fm.get('sd'), 2)} bu/ac, CV "
               f"{_n(fm.get('cv_pct'), 2)} %. {applied}. Colours centred on the field mean (yellow): red below, green "
               "above; nothing is interpolated or smoothed.", 4.9 * inch)


def _section_seams(story, R):
    """The seams between neighbouring passes (R['machines']['seams']) and the combine and seam maps."""
    M = R.get("machines") or {}
    S = M.get("seams")
    _fig_block(story, R, "combines", "<b>The combines and their factor</b>",
               "Left: the combine that cut each kept strip. Then the yield as mapped and, when a factor other than 1 "
               "was applied, Yld_Harm = the reading x the factor of its combine, on one colour scale.", 4.6 * inch)
    if not S:
        return
    story.append(Paragraph("<b>Seams between neighbouring passes</b>: " + _e(S.get("rule") or "") + ".", BODY))
    sc, db, da = S["same_combine"], S["different_combines"]["before"], S["different_combines"]["after"]
    moved = S["different_combines"].get("factor_moved_them")
    rows = [["Neighbouring passes", "Stretches", "Pass pairs", "Median difference %", "Stretches > 10 %"]]
    for lab, st in (("same combine", sc), ("different combines" + (", before the factor" if moved else ""), db)) + (
            (("different combines, after the factor", da),) if moved else ()):
        rows.append([_e(lab), _n(st.get("stretches")), _n(st.get("pass_pairs")), _n(st.get("median_pct"), 2),
                     (_n(st.get("share_above_10_pct"), 0) + " %") if st.get("share_above_10_pct") is not None
                     else "-"])
    w = [2.3, 0.9, 0.9, 1.4, 1.3]
    scale = TEXT_W / (sum(w) * inch)
    t = _table(rows, [x * inch * scale for x in w], small=True)
    t.setStyle(TableStyle([("ALIGN", (1, 0), (-1, -1), "RIGHT")]))
    story.append(t)
    pr = S.get("pairs") or []
    if pr:
        story.append(Paragraph("Per pair of combines (a over b = the median signed difference at their seams: the part "
                               "a calibration difference would make the same on every seam):", BODY))
        rows = [["Combine a", "Combine b", "Stretches", "Pass pairs", "Median diff. %", "a over b %"]]
        for p_ in pr:
            md = _n(p_.get("median_pct_before"), 2) + ((" &rarr; " + _n(p_.get("median_pct_after"), 2)) if moved else "")
            ab = (f"{p_.get('a_over_b_pct_before'):+.2f}" + (f" &rarr; {p_.get('a_over_b_pct_after'):+.2f}" if moved else ""))
            rows.append([_e(p_.get("a")), _e(p_.get("b")), _n(p_.get("stretches")), _n(p_.get("pass_pairs")), md, ab])
        w = [1.45, 1.45, 0.75, 0.75, 1.2, 1.2]
        scale = TEXT_W / (sum(w) * inch)
        t = _table(rows, [x * inch * scale for x in w], small=True)
        t.setStyle(TableStyle([("ALIGN", (2, 0), (-1, -1), "RIGHT")]))
        story.append(t)
        if moved:
            story.append(Paragraph("before &rarr; after the combine factor.", CAP))
    story.append(Paragraph(_e(S.get("text") or ""), BODY))
    _fig_block(story, R, "seams", "<b>Seam map</b>",
               "Each line is 50 m of the seam between two neighbouring passes, coloured by how much the two passes "
               "differ there (the mean of the kept readings on each side). Bars: the share of the stretches in each "
               "class.", 5.0 * inch)


def _section_level(story, R, num):
    """The grower's weight as the real level: the ticket in its unit, the conversion, L, the closure, the combines'
    ticket test and the yield column to map. Every number is read from R['level'] / R['machines']['ticket_test']."""
    L = R["level"]
    tick, mon = _ticket_bu(L), _monitor_bu(L)
    added = R.get("difm_ready_added_columns")
    leveled_in = [c for c in ("Yld_Level", "Yld_Lvl_Sy") if added is None or c in added]
    validate = L.get("use") == "validate" or not leveled_in
    story.append(Paragraph(f"{num}. " + ("Grower's data: validation" if validate else "Level: the grower's weight"),
                           H2))
    story.append(Paragraph(
        ("The weight the grower got for the field is compared with the monitor's total over every processed record "
         "(the scale weighs every load, headland included); L is the factor that would level the map to it, and the "
         "file keeps the monitor's yields. " if validate else
         "The weight the grower got for the field is the real total; the monitor's bu/ac are leveled to it with one "
         "factor L = weight / monitor total over every processed record (the scale weighs every load, headland "
         "included). ")
        + "The two are compared as masses, in the bushel of the file's own volume columns, and on one moisture "
        "basis: a weight at the standard moisture against the file's own dry yield (one-sided, as SMS reports the dry "
        "total), a wet weight with its grain moisture brought to the standard by the same rule, a wet weight without "
        "it against the wet yield. "
        + ("Here the weight was used to validate only: L and the verdict are reported, the clean file keeps the "
           "monitor's yields and no leveled column is added. " if validate else
           "The file keeps the monitor's columns and adds the leveled yield"
           + ("s " if len(leveled_in) > 1 else " ")
           + " and ".join({"Yld_Level": "Yld_Level (mapped dry yield x combine factor x L)",
                           "Yld_Lvl_Sy": "Yld_Lvl_Sy (the symmetric dry-matter yield x factor x L)"}[c]
                          for c in leveled_in) + ". ")
        + "L does not change the "
        "pattern or the ranking of the treatments, only the level the economics sit at. Do not trust L when the "
        "weight covers several fields, includes dockage, or is on another moisture basis than the comparison. "
        f"{_e(refs.cite('level', notes=False))}.", BODY))
    rows = [["Item", "Value"]]
    basis = L.get("ticket_basis", L.get("basis", "wet"))
    rows.append(["Grower's yield per acre" if L.get("ticket_unit") == "bu/ac" else "Grower's weight (scale ticket)",
                 f"<b>{_ticket_label(L)}</b>, {_e(basis)} basis"
                 + (f", {float(L['ticket_moisture_pct']):g} % moisture on the ticket" if L.get("ticket_moisture_pct") is not None
                    else "") + (f". {_e(L['ticket_note'])}" if L.get("ticket_note") else "")])
    if L.get("ticket_unit") == "bu/ac":
        own = bool(L.get("grower_bushels_applied") and L.get("ticket_bu_grower") and L.get("test_weight_grower"))
        rows.append(["Made a total", f"{_ticket_label(L)} &times; {_n(L.get('ticket_area_ac'), 2)} ac "
                     f"({_e(L.get('ticket_area_source') or 'area')}) = "
                     + (f"{_n(L.get('ticket_bu_grower'), 2)} bu of {float(L['test_weight_grower']):.2f} lb = "
                        f"{_n(L.get('ticket_lb'))} lb = {_n(L.get('ticket_bu'), 2)} bu at "
                        f"{float(L['test_weight_used']):.2f} lb/bu (the file's bushel)" if own else
                        f"{_n(L.get('ticket_bu'), 2)} bu"
                        + (f"; {_n(L.get('ticket_lb'))} lb at {float(L['test_weight_used']):.2f} lb/bu"
                           if L.get("ticket_lb") and L.get("test_weight_used") else ""))])
    elif L.get("ticket_unit") and L.get("ticket_unit") != "bu":
        conv = (f"{_n(tick, 2)} bu" + (f" at {float(L['test_weight_used']):.2f} lb/bu" if L.get("test_weight_used") else "")
                + (f" ({_e(_tw_source(L))})" if L.get("test_weight_source") else "")
                + (f"; {_n(L.get('ticket_lb'))} lb" if L.get("ticket_lb") and L.get("ticket_unit") != "lb" else ""))
        rows.append(["Converted to bushels", conv])
    if L.get("test_weight_grower") and L.get("ticket_caption"):
        # two bushel weights: the comparison is one of mass, in the bushel of the monitor's total
        rows.append(["Bushels", _e(L["ticket_caption"]) + ". Every bushel of this section is the file's ("
                     + (f"{float(L['test_weight_used']):.2f} lb" if L.get("test_weight_used") else "its own weight")
                     + "), so the grower's weight and the monitor's total are compared as masses."])
    at_std = L.get("ticket_bu_at_standard", L.get("ticket_bu_dry"))
    if at_std is not None:
        rows.append(["At the standard moisture", f"{_n(at_std, 2)} bu (the ticket shrunk by the rule of the column it "
                     "is compared with" + (f"; compared on the {_e(L['comparison_basis'])} basis"
                                           if L.get("comparison_basis") else "") + ")"])
    harm_differs = _harmonised_differs(L)
    tots = [(k, L.get(k)) for k in ("monitor_total_wet_bu", "monitor_total_dry_bu", "monitor_total_dry_sym_bu")]
    if any(v is not None for _k, v in tots):
        names = {"monitor_total_wet_bu": "wet", "monitor_total_dry_bu": "dry as the file (one-sided)",
                 "monitor_total_dry_sym_bu": "dry, symmetric"}
        rows.append(["Monitor totals", "; ".join(f"{names[k]} {_n(v, 2)} bu" for k, v in tots if v is not None)
                     + (f"; over {_n(L.get('monitor_area_ac'), 2)} ac ({_e(L.get('monitor_area_source') or '')}) for "
                        "the bu/ac" if L.get("monitor_area_ac") else "")])
    rows.append(["Monitor total (processed set)",
                 f"{_n(mon, 2)} bu over {_n(L.get('export_integral_area_ac', L.get('export_area_ac')), 2)} ac, column "
                 f"{_e(L.get('integral_column'))}" + (f"; {_n(L.get('export_total_lb'))} lb" if L.get("export_total_lb") else "")
                 + (f"; after the combine harmonisation {_n(L.get('export_total_harmonised_bu'), 2)} bu"
                    if harm_differs else "")])
    # the factor applied to the columns first (factor_final = after the harmonisation when a combine factor was
    # applied); the pre-harmonisation factor only when a factor changed it. The scale figure is the one L divides by:
    # the ticket at the standard moisture when the ticket's moisture was applied
    ff = L.get("factor_final")
    if ff is None:
        ff = L.get("factor_harmonised", L.get("factor"))
    lv = f"<b>{float(ff):.4f}</b>" if ff is not None else "-"
    mon_f = L.get("export_total_harmonised_bu") if (harm_differs and not L.get("per_machine")) else None
    if mon_f and tick:
        # the L in the file goes with the monitor total after the combine factor, not with the one before it
        lv += (f" (monitor {_n(mon_f)} bu with the combine factor vs scale {_n(tick)} bu, "
               f"{100 * (float(tick) / float(mon_f) - 1):+.2f} %")
        if L.get("ticket_bu_at_standard") is not None and L.get("ticket_bu") is not None:
            lv += (f"; the ticket's {_n(L['ticket_bu'])} bu at {float(L['ticket_moisture_pct']):g} % = {_n(tick)} bu at "
                   "the standard moisture")
        lv += ")"
    elif mon and tick:
        lv += f" (monitor {_n(mon)} bu vs scale {_n(tick)} bu, {100 * (float(tick) / float(mon) - 1):+.2f} %"
        if L.get("ticket_bu_at_standard") is not None and L.get("ticket_bu") is not None:
            lv += (f"; the ticket's {_n(L['ticket_bu'])} bu at {float(L['ticket_moisture_pct']):g} % = {_n(tick)} bu at "
                   "the standard moisture")
        lv += ")"
    if harm_differs and L.get("factor") is not None and ff is not None and abs(float(ff) - float(L["factor"])) > 1e-9:
        lv += f"; before the combine harmonisation {float(L['factor']):.4f}"
    if L.get("per_machine"):
        lv += "; field-level only: each combine is leveled with its own L (Combines section)"
    rows.append(["Level factor L", lv])
    c = L.get("closure") or {}
    if c:
        cl = (f"monitor {_n(c.get('monitor_total_bu'), 2)} bu vs scale {_n(c.get('ticket_bu'), 2)} bu: "
              f"the monitor is {_spct(c.get('diff_pct'))} from the scale")
        after = c.get("after_harmonisation_bu")
        if (after is not None and c.get("monitor_total_bu") is not None
                and abs(float(after) - float(c["monitor_total_bu"])) > 1e-9 * max(1.0, abs(float(c["monitor_total_bu"])))):
            cl += (("; the leveled map integrates to " if L.get("per_machine") else "; after the combine harmonisation ")
                   + f"{_n(after, 2)} bu ({_spct(c.get('diff_after_pct'))})")
        if c.get("verdict"):
            v = str(c["verdict"])
            cl += f". {_e(v[:1].upper() + v[1:])}"
        rows.append(["Closure", cl])
    tt = _g(R, "machines", "ticket_test") or {}
    if tt and (tt.get("candidates") or tt.get("rejected")):
        # only a factor above the max is tested against the weight: without such a candidate the row would read
        # 'factor not applied' for a cleaning whose ordinary factor was applied
        wo, wi = tt.get("without") or {}, tt.get("with") or {}
        rows.append(["Factor above the max (ticket closure test)",
                     f"without the factor above the max {_n(wo.get('total_bu'), 2)} bu ({_spct(wo.get('diff_pct'))} "
                     f"from the scale); with it {_n(wi.get('total_bu'), 2)} bu ({_spct(wi.get('diff_pct'))}): "
                     + ("<b>applied</b>" if tt.get("applied") else "<b>not applied</b>")
                     + (" (the weight would confirm it, but it is used to validate only)" if tt.get("would_apply")
                        else "")
                     + (f" ({_e(', '.join(map(str, tt.get('machines') or [])))})" if tt.get("machines") else "")
                     + (f". {_e(tt.get('verdict') or tt.get('text'))}" if (tt.get("verdict") or tt.get("text"))
                        else "")])
    col, why = _difm_column(R)
    if not why and L.get("use") == "validate":
        why = ("the grower's weight was used to validate the monitor only: no leveled yield is in the clean file and "
               "the weight applied no combine factor")
    rows.append(["Yield column to map", f"<b>{_e(col)}</b>" + (f": {_e(why)}" if why else "")])
    if L.get("set_aside_integral_bu"):
        rows.append(["Records set aside by the field of interest",
                     f"{_n(L['set_aside_integral_bu'])} bu over {_n(L.get('set_aside_area_ac'), 2)} ac not in the "
                     f"denominator; whole file {_n(L.get('file_integral_bu'))} bu, L would be {_n(L.get('factor_whole_file'), 4)}"])
    story.append(_table(rows, [2.0 * inch, TEXT_W - 2.0 * inch], header=True, bold_first=True))


def _steps_that_ran(R) -> list:
    steps = ["order"]
    if R.get("aoi"):
        steps.append("aoi")
    steps += [c["filter"] for c in R.get("cascade", []) if c.get("on", True) and c.get("filter") in refs.SOURCES]
    if _is_sms(R) and "F10" in refs.SOURCES:
        steps.append("F10")                 # the mean +/- k SD rule of the 3-sigma steps
    if R.get("lag") and not _is_sms(R):
        steps.append("lag")
    if R.get("sessions"):
        steps.append("sessions")
    if R.get("machines"):
        steps.append("machines")
    if R.get("level"):
        steps.append("level")
    return steps


def _section_references(story, R, num):
    steps = _steps_that_ran(R)
    keys = refs.used_keys(steps)
    # the SMS report borrows the mean +/- k SD literature registered under F10: name it by the steps it supports
    label = {"F10": "S3-S5 (mean +/- k SD)"} if _is_sms(R) else {}
    story.append(Paragraph(f"{num}. References", H2))
    story.append(Paragraph(
        f"The {len(keys)} works cited by the steps that ran ({', '.join(_e(label.get(s, s)) for s in steps)}), from "
        "docs/literature/references_verified.csv; in brackets, the steps each work supports (what it gives for each "
        "step: engine/clean/references.py).", SUB))
    for k in keys:
        where = [label.get(s, s) for s in steps if any(e["key"] == k for e in refs.SOURCES[s])]
        story.append(Paragraph(f"{_e(refs.full_citation(k, compact=True))} "
                               f"<font color='#5f5f5f'>[{_e(', '.join(where))}]</font>", REF))


# ------------------------------------------------------------------------------------------------- report
def make_report(result: dict, path: str) -> str:
    """Write the cleaning report of `result` to `path` (PDF) and return the absolute path."""
    R = result
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    files = R.get("files", {})
    story = []
    inp = R.get("input") or files.get("input", "")
    story.append(_masthead())
    story.append(Spacer(1, 10))
    story.append(Paragraph("Yield map cleaning report" + (" &middot; SMS 3-sigma method" if _is_sms(R) else ""), H1))
    story.append(Paragraph(f"{_e(os.path.basename(inp))} &nbsp;&middot;&nbsp; tag {_e(R.get('tag', ''))} "
                           f"&nbsp;&middot;&nbsp; {datetime.date.today().isoformat()}", SUB))
    story.append(Spacer(1, 6))

    # ---- 1. summary
    story.append(Paragraph("1. Summary", H2))
    ycol = R.get("yield_column_for_difm") or R.get("columns", {}).get("yield")
    rem = R["n_in"] - R["n_kept"]
    rows = [
        ["Input file", _e(inp)],
        ["Source", _source_text(R)],
    ]
    aoi_txt = _aoi_text(R)
    if aoi_txt:
        rows.append(["Field of interest", aoi_txt])
    rows += [
        ["Points", f"{R['n_in']:,} in &rarr; <b>{R['n_kept']:,} kept</b>; {rem:,} removed ({R['removed_pct']:.2f} %)"],
        ["Harvest order", _e(f"{R['order']['basis']}: {R['order']['rule']}")
         + (f" ({R['order']['n_logs']} logs)" if R["order"].get("n_logs") else "")],
    ]
    mo = _moisture_text(R)
    if mo:
        rows.append(["Moisture basis", mo])
    se = _sessions_brief(R)
    if se:
        rows.append(["Harvest sessions", se])
    if _is_sms(R):
        rows += [
            ["Method", _sms_method_text(R)],
            ["Optimize Swath Widths", _sms_swath_text(R)],
            ["Machines", _machines_text(R)],
        ]
    else:
        rows += [
            ["F8 overlap threshold", _f8_text(R)],
            ["Flow delay", _lag_text(R)],
            ["Machines", _machines_text(R)],
        ]
    imp = R.get("sms_import")
    if isinstance(imp, dict):
        rows.append(["Import as SMS", _import_text(imp)])
    lv = _level_text(R)
    if lv:
        added_l = R.get("difm_ready_added_columns")
        val_l = (R.get("level") or {}).get("use") == "validate" or (
            added_l is not None and not any(c in added_l for c in ("Yld_Level", "Yld_Lvl_Sy")))
        rows.append(["Grower's data: validation" if val_l else "Level to scale ticket", lv])
    lcol, lwhy = _difm_column(R)
    if R.get("level") and lwhy:
        ycol = lcol
        difm = f"map <b>{_e(ycol)}</b> as the yield column (bu/ac): {_e(lwhy)}"
    else:
        difm = f"map <b>{_e(ycol)}</b> as the yield column (bu/ac)"
        lvl_col = R.get("level_column_for_difm", "Yld_Level")
        added0 = R.get("difm_ready_added_columns")
        if R.get("level") and (added0 is None or lvl_col in added0):
            difm += (f"; <b>{_e(lvl_col)}</b> is the same yield leveled to the scale "
                     "ticket (use it when the maps should show scale-level yields)")
        elif R.get("level"):
            difm += ("; the grower's weight validated the monitor's total (Grower's data above) and the "
                     "leveled yields are not in the file")
    what = "decoded readings" if R.get("source") else "original export records"
    crs = (" Coordinates are in WGS 84 (EPSG:4326); the input was reprojected." if R.get("output_crs") == "EPSG:4326"
           and any("written in WGS 84" in n for n in (R.get("notes") or [])) else "")
    added = R.get("difm_ready_added_columns")
    n_dr = R.get("n_difm_ready")
    s2_on = any(c.get("filter") == "S2" and c.get("on", True) for c in R.get("cascade") or [])
    if _is_sms(R) and s2_on:
        held = (f"The file is the export as SMS writes it after Optimize Swath Widths (the narrowed points carry the "
                f"new width, the shortened ones the new Distance and Speed; both have their per-area values multiplied "
                f"by old / new area (Swath_Scl); Y_Offset is written as 0 and every point sits where SMS moved it; "
                f"every other cell is the {what}' value), removed points dropped, plus the added columns")
    elif _is_sms(R):
        held = (f"The file holds the {what}' values (Optimize Swath Widths was switched off), removed points dropped, "
                "plus the added columns")
    else:
        held = f"The file holds the {what} verbatim (removed points dropped) plus the added columns"
    rows.append(["Clean file", f"{_e(os.path.basename(files.get('difm_ready_zip', '')))}: {difm}. {held}"
                 + (f" {_e(', '.join(str(a) for a in added))}" if added else "")
                 + (f"; {n_dr:,} points" if isinstance(n_dr, int) and n_dr != R["n_kept"] else "") + f".{crs}"])
    fm = R.get("final_map") or {}
    if fm.get("area_ac") is not None:
        rows.append(["Kept area and average",
                     f"{_n(fm['area_ac'], 2)} ac of kept readings (distance x width of the clean file); average "
                     f"{_e(fm.get('column', ''))} {_n(fm.get('average_area_weighted'), 2)} bu/ac (total / area, as the "
                     f"SMS Summary computes it); plain point mean {_n(fm.get('mean'), 2)} bu/ac"])
    story.append(_table(rows, [1.45 * inch, TEXT_W - 1.45 * inch], header=False, bold_first=True))
    warns = R.get("warnings") or []
    story.append(Paragraph("Warnings", H2))
    if warns:
        for w in warns:
            story.append(Paragraph(_e(w), WARN, bulletText="•"))
    else:
        story.append(Paragraph("None.", BODY))
    adv = R.get("advice") or []
    if adv:
        story.append(Paragraph("Worth checking before the upload", H2))
        for w in adv:
            story.append(Paragraph(_e(w), WARN, bulletText="•"))
    notes = R.get("notes") or []
    if notes:
        story.append(Paragraph("Notes", H2))
        for w in notes:
            story.append(Paragraph(_e(w), BUL, bulletText="•"))
    _final_map(story, R)

    # ---- 2. cascade
    story.append(Spacer(1, 4))
    if _is_sms(R):
        story.append(Paragraph("2. Cleaning steps (SMS 3-sigma)", H2))
        short = {"S0": "import check", "S1": "clip", "S1b": "second clip", "S2": "swath widths"}
        codes = []
        for c in R.get("cascade") or []:
            fid = str(c.get("filter", ""))
            if fid.startswith("S5"):
                if "S5" not in codes:
                    codes.append("S5")
                continue
            codes.append(fid)
        names = [("S5a/S5b... the dry-yield passes" if f == "S5" else
                  f"{f} {short.get(f) or next((c.get('attribute') for c in R['cascade'] if c.get('filter') == f), '')}")
                 for f in codes]
        pre_clip = any(str(p.get("step", "")).upper() == "AOI" for p in (R.get("pre_steps") or []))
        story.append(Paragraph("The SMS steps run in this order on the points still alive; each point is removed by the "
                               "first step it fails (column Rem_By of the flagged file: " + ", ".join(names) + ")."
                               + (" The clip ran first, before the import check: the readings outside the boundary "
                                  "are not in the flagged file." if pre_clip else "")
                               + " Greyed rows were switched off. The limits of every group are in the limits "
                               "section.", BODY))
    else:
        story.append(Paragraph("2. Cleaning cascade", H2))
        story.append(Paragraph("Filters run in this order on the points still alive; each point is removed by the first "
                               "filter it fails (column Rem_By of the flagged file). Greyed rows were switched off. "
                               "\"Sources\" names the first works that support each rule and the house convention when a "
                               "number is one; every work cited is in the References section, and what each gives in "
                               "engine/clean/references.py.", BODY))
    rows = [["Step", "Rule (thresholds used)", "Sources", "Removed", "Remaining"]]
    off = []
    pre = R.get("pre_steps") or []
    n_file = R.get("n_in_file", R.get("n_read"))
    if n_file == R["n_in"] and not pre:
        n_file = None
    sms_pre = _is_sms(R) and any(str(p.get("step", "")).upper() == "AOI" for p in pre)
    for p in pre:
        remaining = _n(n_file - p.get("removed", 0)) if isinstance(n_file, (int, float)) else "-"
        is_aoi = str(p.get("step", "")).upper() == "AOI"
        label = ("S1 Clip To Field Boundary (set aside before S0)" if (sms_pre and is_aoi) else
                 f"{_e(p.get('step', 'pre-step'))} (pre-step)")
        rows.append([label, _e(p.get("criterion", "")),
                     _e(refs.cite("aoi", notes=False, max_items=SOURCES_IN_TABLE, house="short"))
                     if is_aoi else _e(p.get("source", "")),
                     _n(p.get("removed")), remaining])
    for c in R["cascade"]:
        if sms_pre and c.get("filter") == "S1" and not c.get("removed"):
            continue                               # the clip is the pre-step row above (the app shows it so)
        rows.append([f"{_e(c['filter'])} {_e(c.get('name', ''))}", _e(c["criterion"]), _sources_cell(c),
                     _n(c["removed"]), _n(c["remaining"])])
        if not c.get("on", True):
            off.append(len(rows) - 2)
    rows.append(["<b>Total</b>", "", "", f"<b>{rem:,}</b>", f"<b>{R['n_kept']:,}</b>"])
    t = _table(rows, [1.0 * inch, 2.45 * inch, 1.95 * inch, 0.75 * inch, 0.85 * inch], off_rows=off)
    t.setStyle(TableStyle([("ALIGN", (3, 0), (4, -1), "RIGHT")]))
    story.append(t)
    cov = R.get("coverage_ac")
    story.append(Paragraph(f"{R['n_in']:,} points in"
                           + (f" the cascade ({n_file:,} in the file)" if isinstance(n_file, int) else "")
                           + (f". Swept coverage of the overlap raster: {cov:,.2f} ac." if cov is not None else "."),
                           CAP))

    num = 3
    if _is_sms(R) and (R.get("sms3sigma") or {}).get("steps"):
        _section_sms_limits(story, R, num)
        num += 1
    if R.get("aoi"):
        _section_aoi(story, R["aoi"], num, sms=_is_sms(R),
                     clip={"tolerance_m": ((R.get("sms3sigma") or {}).get("settings") or {}).get("clip_tolerance_m")})
        num += 1
    if R.get("sessions"):
        _section_sessions(story, R, num)
        num += 1
    if R.get("machines"):
        _section_machines(story, R, num)
        num += 1
    if R.get("level"):
        _section_level(story, R, num)
        num += 1

    # ---- settings and columns (filter parameters and column mapping side by side, general settings below)
    S = R.get("settings")
    C = R.get("columns")
    col_table = None
    if C:
        from engine.clean.yield_clean import COLUMN_UNITS
        src = R.get("columns_source", {})
        det = R.get("columns_detected", {})
        rows = [["Key", "Column used", "Unit", "From"]]
        for k, v in C.items():
            how = src.get(k, "")
            if how == "detected" and v is None and det.get(k):
                how = f"detected ({_e(det[k])}) but not used"
            elif v is None:
                how = "not found"
            rows.append([_e(k), _e(v if v else "-"), _e(COLUMN_UNITS.get(k, "")), how])
        col_table = _table(rows, [0.95 * inch, 1.05 * inch, 0.5 * inch, 0.85 * inch], small=True)
    if S or col_table:
        story.append(Paragraph(f"{num}. Settings and column mapping", H2))
        num += 1
        story.append(Paragraph("Left: the filter parameters (the rule each one applies, with these values, is in the "
                               "cascade table). Right: the column of the input used for each key. Below: the general "
                               "settings of the run.", SUB))
        side = []
        if S:
            frows, foff, gen = _settings_rows(S)
            if _is_sms(R):
                side.append(_table(_sms_settings_rows(S), [1.4 * inch, 2.15 * inch], small=True))
            else:
                side.append(_table(frows, [1.05 * inch, 0.35 * inch, 2.15 * inch], off_rows=foff, small=True))
        if col_table is not None:
            side.append(col_table)
        if len(side) == 2:
            ts = Table([side], colWidths=[3.6 * inch, TEXT_W - 3.6 * inch])
            ts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                    ("RIGHTPADDING", (0, 0), (0, 0), 6), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
            story.append(ts)
        else:
            story.append(side[0])
        if S:
            story.append(Spacer(1, 6))
            story.append(_table(gen, [1.5 * inch, TEXT_W - 1.5 * inch], small=True))

    # ---- figures
    figs = files.get("figures", {})
    f8r = R.get("f8") or {}
    v24 = "footprint" in f8r or "lag_stage" in (S or {})      # a v2.4 run: the maps draw the swept strips
    caps = {"map": ("Yield (mapped column) before and after cleaning, each reading drawn as the strip its header swept "
                    "since the previous reading (before: at the logged position; after: the strip of the position its "
                    "grain came from, after the flow-delay shift); bottom row: points removed by each filter group. "
                    "The strips are for display: no total is computed over them." if v24 else
                    "Yield (mapped column) before and after cleaning; bottom row: points removed by each filter group."),
            "f8": ("F8 dose-response (median ratio of each overlap band to its local no-overlap controls, over the "
                   "placebo; under each bar the records with controls / all records) and the sensitivity of the points "
                   "removed and the mean yield kept to the threshold." if f8r.get("reference_mode") == "local" else
                   "F8 dose-response (mean yield of each overlap band vs the no-overlap band) and the sensitivity of "
                   "the points removed and the mean yield kept to the threshold."),
            "cascade": "Points removed by each filter.",
            "lag": "Residual flow-delay scan: correlation of opposite-direction neighbours against a shift of the "
                   "yield along the pass"
                   + {"dominant": ", on the passes of the axis the field was harvested in",
                      "ew_first": ", on the E-W passes when both directions hold &ge; 200 records (v2.3)"}.get(
                       (R.get("lag") or {}).get("axis"), "")
                   + (" (records alive after F6, the before_f7 option)." if (R.get("lag") or {}).get("stage")
                      == "before_f7" else
                      " (kept records after the cascade)." if (R.get("lag") or {}).get("stage") == "output" else ".")}
    if _is_sms(R):
        caps.update({"map": ("Dry yield before and after the SMS 3-sigma cleaning (before: each reading as the strip its "
                             "header swept since the previous reading; after: SMS's own rectangles with the width and "
                             "distance of Optimize Swath Widths and the yield it scaled); bottom row: points removed by "
                             "each step group." if v24 else
                             "Dry yield before and after the SMS 3-sigma cleaning (after: the yield scaled by Optimize "
                             "Swath Widths); bottom row: points removed by each step group."),
                     "limits": "The values entering each 3-sigma step and the limits applied (one pair of lines per "
                               "group).",
                     "cascade": "Points removed by each SMS step."})
    head = [Paragraph(f"{num}. Figures", H2)]          # kept with the first figure, so the heading is never orphaned
    num += 1
    for key in (("map", "limits") if _is_sms(R) else ("map", "f8")):
        p = figs.get(key)
        if not p or not os.path.exists(p):
            head.append(Paragraph(f"Figure {key} missing.", WARN))
            continue
        max_h = 3.5 * inch if key == "map" else 2.3 * inch
        story.append(KeepTogether(head + [_image(p, TEXT_W, max_h), Paragraph(caps[key], CAP)]))
        head = []
    story.extend(head)
    # the two small figures side by side
    pair = []
    for key in (("cascade",) if _is_sms(R) else ("cascade", "lag")):
        p = figs.get(key)
        if p and os.path.exists(p):
            pair.append([_image(p, TEXT_W / 2 - 6, 2.2 * inch), Paragraph(caps[key], CAP)])
        else:
            pair.append([Paragraph(f"Figure {key} missing.", WARN)])
    tp = Table([pair], colWidths=[TEXT_W / 2] * len(pair))
    tp.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(tp)

    # ---- references
    _section_references(story, R, num)

    def _foot(canvas, doc):
        """Every page: a thin rule, the brand at the left, the tag and the page number at the right."""
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 0.66 * inch, PAGE_W - MARGIN, 0.66 * inch)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN, 0.5 * inch, f"{BRAND} · {ORG}")
        canvas.drawRightString(PAGE_W - MARGIN, 0.5 * inch, f"{R.get('tag', '')} · page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=letter, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN,
                            bottomMargin=0.8 * inch, title=f"OCED cleaning report - {R.get('tag', '')}",
                            author=BRAND)
    doc.build(story, onFirstPage=_foot, onLaterPages=_foot)
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        sys.exit("usage: python -m engine.report.clean_report <cleaning.json> <out.pdf>")
    with open(sys.argv[1], encoding="utf-8") as f:
        print(make_report(json.load(f), sys.argv[2]))
