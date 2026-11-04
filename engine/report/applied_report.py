# -*- coding: utf-8 -*-
"""The cleaning report (PDF) of engine/clean/applied3s.py: what the file is, the readings in / kept / removed, the
steps with their criteria, the limits of every 3-sigma step, the statistics of each attribute before and after, the
warnings, and the figures (the map of the main attribute before and after, the points each step removed, the
histogram with the limits). The look of engine/report/clean_report.py (Olds College palette, masthead, footer).

    python -m engine.report.applied_report <tag>_3s_cleaning.json <out.pdf>
"""
from __future__ import annotations

import datetime
import json
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from engine.report.clean_report import (BODY, BRAND, BUL, CAP, GREY, H1, H2, MARGIN, ORG, PAGE_W, RULE, SUB, TEXT_W,
                                        WARN, _e, _image, _masthead, _n, _table)


def _f(v, d=2) -> str:
    return "-" if v is None else _n(v, d)


def make_report(R: dict, path: str) -> str:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    story = [_masthead(), Spacer(1, 10),
             Paragraph("Point data cleaning report &middot; 3-sigma", H1),
             Paragraph(f"{_e(os.path.basename(R.get('input', '')))} &nbsp;&middot;&nbsp; {_e(R.get('operation_label'))}"
                       f" &nbsp;&middot;&nbsp; {datetime.date.today().isoformat()}", SUB)]
    C = R.get("columns") or {}
    B = R.get("boundary")
    n_read, n_in, n_kept = R.get("n_read"), R.get("n_in"), R.get("n_kept")
    rows = [["", ""],
            ["Operation", _e(R.get("operation_label"))],
            ["Readings in the file", _n(n_read)],
            ["Clipped to the field boundary (S1)",
             (f"{_n(B['n_outside'])} outside {_e(os.path.basename(B['file']))} ({_n(B['area_ac'], 1)} ac)" if B
              else "no boundary given")],
            ["Kept", f"{_n(n_kept)} of {_n(n_in)} ({100 * n_kept / max(n_in or 1, 1):.1f} %); removed "
                     f"{R.get('removed_pct', 0):.1f} %"],
            ["Attributes filtered", ", ".join(_e(a) for a in R.get("attributes") or [])
             + f" (the main one: <b>{_e(R.get('main'))}</b>, {R.get('passes', 1)} pass(es))"],
            ["Mean and SD", _e((R.get("grouping") or {}).get("rule", ""))],
            ["Product", (", ".join(_e(v) for v in R.get("products") or []) or "-")
             + (f" ({_e(C['product'])})" if C.get("product") else "")],
            ["Coordinate system", _e(R.get("crs") or "-")],
            ["Clean file", _e(os.path.basename((R.get("files") or {}).get("clean_zip", "")))]]
    story.append(Paragraph("1. Summary", H2))
    story.append(_table(rows[1:], [0.32 * TEXT_W, 0.68 * TEXT_W], header=False, bold_first=True))
    story.append(Paragraph("Rule: " + _e(R.get("rule", "")) + ".", CAP))
    if R.get("warnings"):
        story.append(Paragraph("Warnings", H2))
        for w in R["warnings"]:
            story.append(Paragraph(_e(w), WARN, bulletText="•"))

    story.append(Paragraph("2. The steps", H2))
    t = [["Step", "Name", "Criterion", "Removed", "Remaining"]]
    off = []
    for i, r in enumerate(R.get("cascade") or []):
        t.append([_e(r["filter"]), _e(r["name"]), _e(r["criterion"]), _n(r["removed"]), _n(r["remaining"])])
        if not r.get("on"):
            off.append(i)
    story.append(_table(t, [0.08 * TEXT_W, 0.22 * TEXT_W, 0.46 * TEXT_W, 0.12 * TEXT_W, 0.12 * TEXT_W], off_rows=off))

    st = [r for r in R.get("steps") or []]
    if st:
        story.append(Paragraph("3. The limits of each 3-sigma step", H2))
        t = [["Step", "Group", "Attribute", "Before", "Mean", "SD", "Low", "High", "Removed", "SD drop"]]
        for r in st:
            t.append([_e(r["step"]), _e(r["group"]), _e(r["attribute"]) + (f" ({_e(r['unit'])})" if r.get("unit") else ""),
                      _n(r["n_before"]), _f(r["mean"], 3), _f(r["sd"], 3), _f(r["lo"]), _f(r["hi"]), _n(r["removed"]),
                      ("-" if r.get("sd_drop_pct") is None else f"{r['sd_drop_pct']:.1f} %")])
        w = TEXT_W / 100
        story.append(_table(t, [7 * w, 12 * w, 17 * w, 9 * w, 10 * w, 9 * w, 9 * w, 9 * w, 9 * w, 9 * w], small=True))
        story.append(Paragraph("Mean and SD of the points still alive before each step; the limits as typed in SMS "
                               "Filter Data (mean &plusmn; k SD, rounded to 2 decimals, inclusive).", CAP))

    S = R.get("stats") or {}
    if S:
        story.append(Paragraph("4. The attributes before and after", H2))
        t = [["Attribute", "", "Points", "Mean", "SD", "CV", "Min", "Median", "Max"]]
        for a, d in S.items():
            for when in ("before", "after"):
                s = d.get(when) or {}
                t.append([_e(a) if when == "before" else "", when, _n(s.get("n")), _f(s.get("mean")), _f(s.get("sd")),
                          ("-" if s.get("cv_pct") is None else f"{s['cv_pct']:.1f} %"), _f(s.get("min")),
                          _f(s.get("median")), _f(s.get("max"))])
        w = TEXT_W / 100
        story.append(_table(t, [18 * w, 9 * w, 10 * w, 10 * w, 10 * w, 9 * w, 11 * w, 11 * w, 12 * w], small=True))

    figs = (R.get("files") or {}).get("figures") or {}
    caps = {"map": f"{_e(R.get('main'))} of every reading before (left) and of the kept readings after the cleaning "
                   "(right); the colours span the 2nd to 98th percentile of the kept values; the blue line is the "
                   "field boundary. Nothing is interpolated or smoothed.",
            "removed": "The kept readings (green, faint) and the readings each step removed, in the colour of the "
                       "step.",
            "hist": "The values of the main attribute before the cleaning (light) and kept (navy), with the lower and "
                    "upper limit of each 3-sigma pass (red)."}
    head = [Paragraph("5. Figures", H2)]
    for key in ("map", "removed", "hist"):
        p = figs.get(key)
        if p and os.path.exists(p):
            story.append(KeepTogether(head + [_image(p, TEXT_W, 3.3 * inch), Paragraph(caps[key], CAP)]))
            head = []

    def _foot(canvas, doc):
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
                            bottomMargin=0.8 * inch, title=f"OCED cleaning report - {R.get('tag', '')}", author=BRAND)
    doc.build(story, onFirstPage=_foot, onLaterPages=_foot)
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        sys.exit("usage: python -m engine.report.applied_report <cleaning.json> <out.pdf>")
    with open(sys.argv[1], encoding="utf-8") as f:
        print(make_report(json.load(f), sys.argv[2]))
