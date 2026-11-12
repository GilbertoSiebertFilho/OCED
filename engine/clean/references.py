# -*- coding: utf-8 -*-
"""Literature behind every step of the cleaning: which verified work supports which rule, and how to cite it.

    from engine.clean import references as refs
    refs.cite("F3")                 # 'Sudduth & Drummond 2007 (SMV: drop a point whose speed differs ...); Griffin ...'
    refs.cite("F3", notes=False)    # 'Sudduth & Drummond 2007; Griffin et al. 2008; Luck et al. 2015; SMV ratio ...'
    refs.full_citation("Sudduth 2007")
    refs.references_markdown()      # the text of docs/REFERENCES.md (python -m engine.clean.references --write)

Method. REFERENCES holds every work of docs/literature/references_verified.csv (121 records with a verified
bibliographic record: key, authors, year, title, venue, volume, issue, pages, DOI), read at import; when the CSV is not
beside the package (a copied engine/ folder) the embedded copy of the rows used by SOURCES is taken instead, with a
warning. SOURCES maps each step of the cascade (F0-F11, F5b), the flow-delay scan ("lag"), the scale-ticket level
("level"), the harmonisation of several combines ("machines"), the harvest sessions ("sessions"), the field of
interest ("aoi") and the order of operations ("order") to the works that support it, each with what it supports
("concept", "method", "threshold" or "range") and a note saying what the paper actually gives. House conventions,
numbers that no verified paper gives, are kept apart in HOUSE_RULES and are always labelled "house rule" / "house
method" in the citation string, so a threshold is never attributed to a paper that does not state it.

Evidence. The mapping follows docs/literature/Yield_map_cleaning_literature_review.md, sections 4.1-4.16 (one per
step), 5 (order), 7.1 and 7.2 (the v1 -> v2 table), and only cites works present in references_verified.csv. Since
29 Oct 2026 each step keeps at most three works, the ones that give the method the step implements, the parameter it
uses (or the published range its value was chosen in) or the key evidence of the error it removes; every note was
checked against docs/literature/evidence_by_paper.json (review wf_25c3ea8f-ef1: 156 entries / 71 works -> 56 / 27):
tests/test_references.py checks every key against the CSV, that every step has a non-empty citation, and that
docs/REFERENCES.md is the output of references_markdown() (so the document cannot drift from the code). The v1
attributions that the review found unsupported are NOT repeated here: Simbahan et al. 2004 for F1 (they use mean
+/- 3 SD, no fixed window) and F8 (they do not screen overlap), Blackmore & Moore 1999 for F4 and F10 (no such rules
in the material held), Vega et al. 2019 for F5/F5b/F6 (no run-length or heading rule), Menegatti & Molin 2004 for
the F9 window, Sudduth & Drummond 2007 for the F7 "4 / 2 points" (START/END are tuned per field, no values given).

v2.4 (29 Oct 2026): the house conventions of "order", "lag", "F7" and "F8" describe the v2.4 model - the F8 footprint
is the strip swept between consecutive header lines (placed Y_Offset to the right of travel), the dose-response is
read on the pass interiors against local no-overlap controls of the same combine at the same distance from the
harvested edge, the automatic threshold never goes below 5 %, and the residual flow delay is still measured after the
cascade and applied to the output geometry only, its scan comparing the passes of the axis the field was harvested in
(measuring it after F6 and applying it before F7 and F8 is an option that failed its pre-registered test). The
evidence is the house's own pre-registered overlap tests, their reviews and the pre-registered v2.4
evaluation (docs/METHOD.md sections 3.1, 4 and 13; docs/overlap_v24/), not a paper, so no work was added or removed
and the changes are labelled house rules / house method. HOUSE_RULES_V23 keeps the v2.3 texts that a run with the
v2.3 model cites.
"""
from __future__ import annotations

import csv
import os
import re
import warnings

CSV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs",
                                         "literature", "references_verified.csv"))
MD_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs",
                                        "REFERENCES.md"))
SUPPORTS = ("concept", "method", "threshold", "range")

# what each step id means (order of STEP_ORDER = order of the document)
STEP_NAMES = {
    "order": "Order of operations and how much to remove",
    "aoi": "Field of interest (plan / boundary) - pre-step",
    "F0": "F0 Record integrity",
    "F1": "F1 Grain moisture range",
    "F2": "F2 Ground-speed range",
    "F3": "F3 Speed change",
    "F4": "F4 Positional consistency (GNSS step vs logged distance)",
    "F5": "F5 Short passes",
    "F6": "F6 Heading change / pass segmentation",
    "lag": "Residual flow-delay scan (after the cascade, output positions)",
    "F7": "F7 Pass ends",
    "F8": "F8 Overlap and the dose-response threshold",
    "F9": "F9 Wet-mass plausibility range",
    "F10": "F10 Global outliers (mean +/- k SD)",
    "F11": "F11 Local outliers (in-pass median)",
    "F5b": "F5b Short surviving runs",
    "sessions": "Harvest sessions (several days) and the moisture basis",
    "machines": "Several combines - harmonisation",
    "level": "Absolute level - scale ticket and the factor L",
}
STEP_ORDER = list(STEP_NAMES)

# step -> [{"key", "supports", "note"}]: at most three works per step, the ones that give the method, the
# parameter OCCD uses or the key evidence (review wf_25c3ea8f-ef1, each note checked against
# docs/literature/evidence_by_paper.json); the first entries carry the rule (the PDF table shows the first two)
SOURCES = {
    "order": [
        {"key": "Simbahan 2004", "supports": "method",
         "note": "Sequence: header-up, pass ends, sensor outliers, yield limits, local, short segments last; 13-20 % removed"},
        {"key": "Menegatti 2004", "supports": "method",
         "note": "Fixed-order cascade; a point with several errors counts for the first step that catches it; 4.6-27.3 % removed"},
        {"key": "Sudduth 2007", "supports": "range",
         "note": "Literature 10-50 % removed; their own 12.6-26.9 % on 5 fields; filter detections overlap (sum 20.3 % vs 12.6 %)"},
    ],
    "aoi": [
        {"key": "Menegatti 2004", "supports": "method",
         "note": "Points outside the field boundary deleted as step 1, before any other filter: 0.1-7.8 % in 5 of 6 monitors"},
        {"key": "Owen 2024", "supports": "method",
         "note": "Out-of-boundary blocks must go before automated cleaning: they bias every computed filter value"},
        {"key": "Edge 2024", "supports": "concept",
         "note": "DIFM drops the design's headland polygon; units are 12-20 m of pass within one rate: what Plot_Id feeds"},
    ],
    "F0": [
        {"key": "Menegatti 2004", "supports": "method",
         "note": "Deletes null yield (step 2) and zero step between consecutive positions (step 5): 2.3 % and 9.4 % on GreenStar"},
        {"key": "Menegatti 2003", "supports": "concept",
         "note": "Zero distance = error (ground is cut once): 11.48 % of GreenStar points; 4.6 % null yields put Tukey fence < 0"},
        {"key": "Alves 2026", "supports": "concept",
         "note": "Duplicate, null and negative records 20.0 % of Field A, the largest removal class (global outliers 0.17 %)"},
    ],
    "F1": [
        {"key": "Luck 2014", "supports": "range",
         "note": "moisture sensors read adequately only at 10-33 %; drop < 10 or > 33 %; OCCD corn window = 10-33 %"},
        {"key": "Menegatti 2003", "supports": "method",
         "note": "missing moisture logged as null or system minimum (no signal): 1.06-9.50 % of records on 5 monitors"},
    ],
    "F2": [
        {"key": "Sudduth 2007", "supports": "method",
         "note": "MINV/MAXV per field (no values): slow = yield spikes, fast = partial swaths; MINV flagged 3.1 %, MAXV 0.2 %"},
        {"key": "Luck 2015", "supports": "range",
         "note": "fixed window 0.7-8.2 mph (1-12 ft per 1-s record); OCCD 1.5-6.5 mph lies inside it"},
        {"key": "Griffin 2008", "supports": "range",
         "note": "per-field bounds used: min 0.7-1.8 m/s (1.6-4.0 mph), max 1.6-3.1 m/s (3.6-6.9 mph); MINV largest remover"},
    ],
    "F3": [
        {"key": "Sudduth 2007", "supports": "threshold",
         "note": "SMV: drop a point whose speed differs from the previous by > ratio; example 0.20 = OCCD 20 %; 3.2 % flagged"},
        {"key": "Griffin 2008", "supports": "range",
         "note": "SMV applied in all 6 fields at 0.10-0.20 (W2 printed as 20); 408-1,398 records removed per field"},
        {"key": "Luck 2015", "supports": "concept",
         "note": "abrupt stop logs a short distance at full flow: a 1,666 bu/ac point; gradual acceleration reads low"},
    ],
    "F4": [
        {"key": "Lyle 2014", "supports": "concept",
         "note": "3-point search flags bad GPS fixes on successive points by a maximum-distance threshold (value not shown)"},
        {"key": "Damiano 2022", "supports": "method",
         "note": "Reference = logged distance, else speed x interval (OCCD fallback); Euclidean GNSS step least preferred"},
        {"key": "Menegatti 2003", "supports": "concept",
         "note": "Zero UTM step between consecutive points in 11.48 % of GreenStar records (fix inside GNSS error circle)"},
    ],
    "F5": [
        {"key": "Ping 2005", "supports": "range",
         "note": "Deletes stop-and-go segments < 12 points (2-3 s logging = 24-36 s); top of the 3-12 range OCCD's 10 sits in"},
        {"key": "Clarke 2024", "supports": "range",
         "note": "Removes swaths < 3 points (grain flow not yet steady); bottom of the 3-12 range OCCD's 10 sits in"},
        {"key": "Arslan 2002a", "supports": "concept",
         "note": "Monitor-minus-scale yield differs 5-14 % over 15 m vs 2-11 % over 300 m: short segments read worst"},
    ],
    "F6": [
        {"key": "Clarke 2024", "supports": "threshold",
         "note": "Splits passes where direction changes > 0.6 rad (34.4 deg) and deletes the turn point; OCCD uses 30 deg/s"},
        {"key": "Drummond 1999", "supports": "method",
         "note": "New pass at a rapid, significant heading change, a time break or header up (no number): the 60 deg break"},
        {"key": "Marchant 2019", "supports": "concept",
         "note": "Wrong-direction filter removed 445 of 4,524 points (9.8 %), mostly at row ends and obstacles"},
    ],
    "lag": [
        {"key": "Marchant 2019", "supports": "method",
         "note": "Keeps the time shift maximising correlation of nearby points on opposite-direction adjacent rows, -30..+30 s"},
        {"key": "Lee 2012", "supports": "range",
         "note": "Delay scanned -8..+18 s in 1 s steps around the export delay; residuals on 50 fields -3..+5 s, mostly -2..+1"},
        {"key": "Chung 2002", "supports": "method",
         "note": "Pass-end lows made the nugget method pick 13 s, not 14 s; objective delays mostly within 1 s of visual ones"},
    ],
    "F7": [
        {"key": "Sudduth 2007", "supports": "method",
         "note": "START/END drop a fixed count of records at each pass start/end, set per field; removed 3.2-10.6 % / 1.4-7.3 %"},
        {"key": "Griffin 2008", "supports": "range",
         "note": "Yield Editor start/end trims set per field: 3-6 s / 2-4 s (0 in some fields); OCCD's 4 / 2 lie inside"},
        {"key": "Simbahan 2004", "supports": "threshold",
         "note": "Deleted the first 8 s and last 4 s of every pass (elevator fill / empty); OCCD's 4 / 2 records are half"},
    ],
    "F8": [
        {"key": "Drummond 1999", "supports": "method",
         "note": "Footprint minus earlier cut, time order (Eq. 1); 89 % newly cut (11 % error); 10 cm raster <2 %, 30 cm ~5 %"},
        {"key": "Han 1997", "supports": "method",
         "note": "Bitmap of cut ground updated each fix; newly cut cells = effective width; wheat passes 1.18-2.24 vs 1.52 m"},
        {"key": "Alves 2026", "supports": "range",
         "note": "Yield Editor/AYCE overlap filter: 0.3 m bitmap, record deleted when > 50 % of it already cut (Table 2)"},
    ],
    "F9": [
        {"key": "Arizo-García 2026", "supports": "threshold",
         "note": "Wheat/barley: 0-10,000 kg/ha window, then 500 kg/ha floor from binned robust CV (barley 53.7 vs 16.3 %)"},
        {"key": "Ping 2005", "supports": "method",
         "note": "Floor = lowest yield the combine measures accurately, cap = site yield potential (0.01-22 Mg/ha maize)"},
        {"key": "Menegatti 2003", "supports": "concept",
         "note": "Impossible raw maxima: GreenStar 2,162.6, AFS 485.2, Ceres 2 9,999.9 t/ha (header-up, zero-area records)"},
    ],
    "F10": [
        {"key": "dos Santos 2025", "supports": "threshold",
         "note": "OFPE simple method: field mean +/- 3 SD of dry yield, one global pass, yield >= 0 (pacu clean.sd = 3)"},
        {"key": "Sudduth 2007", "supports": "range",
         "note": "Yield Editor STDY = field mean +/- k SD: 3 SD on several fields, 4 where 3 cut valid data; 0.2-7.7 % flagged"},
        {"key": "Ping 2005", "supports": "method",
         "note": "Mean +/- 3 SD on grain flow, moisture and distance per log (= speed): SMS S3-S4 form; 1,007 pts (3.3 %) cut"},
    ],
    "F11": [
        {"key": "Maldaner 2020", "supports": "method",
         "note": "In-row test: drop a point > 20 % off the median of its neighbours within 21 m along the pass; OCCD uses 30 %"},
        {"key": "da Silva 2024", "supports": "threshold",
         "note": "Row sliding-window filter with a max variation factor f (4 values tested); f = 0.30 recommended = OCCD 30 %"},
        {"key": "Lyle 2014", "supports": "threshold",
         "note": "Within-pass band: mean of 2 records before and 2 after +/- 30 % (Fig. 3); second source of the OCCD 30 %"},
    ],
    "F5b": [
        {"key": "Ping 2005", "supports": "range",
         "note": "Short segments < 12 points removed last (step 6), after the outlier tests; top of F5b's 3-12 range"},
        {"key": "Clarke 2024", "supports": "range",
         "note": "Removes swaths < 3 points (grain flow not yet steady); bottom of the 3-12 range of F5b's 10"},
        {"key": "Marchant 2019", "supports": "concept",
         "note": "Drops points within N s of GPS time gaps, incl. gaps left by earlier filters (123 of 4,524, 2.7 %)"},
    ],
    "sessions": [
        {"key": "Luck 2014", "supports": "method",
         "note": "dry yield = wet x (100 - M)/(100 - Ms); Ms corn 15.5 %, soy 13 %; corn calibrated apart above 20 % moisture"},
        {"key": "dos Santos 2025", "supports": "method",
         "note": "pacu converts to dry basis and re-expresses yield at Ms: x (100 - M) / (100 - Ms), 15.5 % maize = Yld_Dry_Sy"},
        {"key": "Lee 2012", "supports": "concept",
         "note": "field cut on >= 2 dates at very different moisture: delay estimates disagreed (dataset 4, 48 ha)"},
    ],
    "machines": [
        {"key": "Maldaner 2016", "supports": "method",
         "note": "largest-area combine = reference; one ratio from all points or closest paths; nearest combine corrected first"},
        {"key": "Carneiro 2022", "supports": "method",
         "note": "yield / its combine's mean x the field's sold mean: the machine ratio; right only on the same ground mix"},
        {"key": "Chiocco 2019", "supports": "range",
         "note": "multi-harvester gain searched within +/- 10 % on nearest points of adjacent paths: OCCD's 10 % cap"},
        {"key": "Gauci 2023", "supports": "range",
         "note": "calibrated monitors <= 1.7 % off wagon, platforms alike (p >= 0.54): a step under OCCD's 1 % is noise"},
    ],
    "level": [
        {"key": "Clarke 2024", "supports": "method",
         "note": "each cleaned map rescaled so its mean = weighed yield; cleaned wheat maps still 8.1 % off, 17 % by > 15 %"},
        {"key": "Luck 2014", "supports": "threshold",
         "note": "calibrated monitor total within 1-3 % of field scale weight; recalibrate at >= 3 %: OCCD's 1 % and 3 % bands"},
        {"key": "Gauci 2023", "supports": "threshold",
         "note": "<= 1.7 % off weigh wagon in calibrated flow range (3 % limit); outside it +15.8-17.2 %, linear (R2 > 0.99)"},
    ],
}

# house conventions per step: numbers no verified paper gives (appended to every citation string); the word
# 'house' comes before the first ' (' because the PDF table keeps only that part
HOUSE_RULES = {
    "order": "lag scan after the cascade and the removal guardrails: house rules (published chains correct the delay first; advice above 60 % removed or when a filter removes > 50 % of its input; fewer than 30 kept points = no output; measuring the delay after F6 and applying it before F7 and F8 is an option, lag_stage before_f7, that failed its pre-registered test on 29 Oct 2026)",
    "aoi": "house cut before the cleaning (the app: at the boundary, 0 m; the engine / CLI: a 50 m buffer), plan detection from >= 4 similar polygons and the headland as the polygon > 5 x the median area: house rules",
    "F0": "position checks: house rule (no fix, (0,0), outside the lon/lat ranges, > 50 km from the median position)",
    "F1": "crop windows other than corn 10-33 %: house rule (barley, wheat, durum, oats, rye and no crop 8-20 %; canola, flax 4-16 %; peas 8-24 %; lentils 8-22 %; soybeans 8-25 %: floors below the published 10 %, ceilings below 33 %)",
    "F2": "1.5-6.5 mph window: house rule (one fixed window for every field, inside the published 0.7-8.2 mph)",
    "F3": "SMV ratio per second and over the current speed: house form (20 % is the published example)",
    "F4": "GNSS step vs logged distance test and its 50 % tolerance: house method (no verified paper compares the two; not in Blackmore & Moore 1999)",
    "F5": "10 points per pass: house value within the published 3-12 points (Clarke et al. 2024; Ping & Dobermann 2005)",
    "F6": "30 deg/s removal and the 60 deg and 15 m pass breaks: house values (nearest published: 0.6 rad = 34.4 deg, Clarke et al. 2024)",
    "lag": "+/-8-record window, 5-point median, the first 14 and last 16 surviving points of a pass left out, >= 100 points per direction, pairs within 1.2 widths on the pass axis the field was harvested in, gates 2 <= |lag| < 8 and r gain > 0.01: house rule (scan on the kept records after the cascade, the shift moves the output geometry only; v2.3 scanned the E-W passes whenever both directions held >= 200 points, which on N-S fields were the headlands; the option of tying every yield to its source position before F7 and F8 failed its pre-registered test)",
    "F7": "first 4 / last 2 surviving records, one setting for all fields: house values, inside the 3-8 s / 2-4 s of the cited works (~4 s / 2 s at 1 Hz; the house's overlap tests found longer ramps at the pass ends, but a per-field count is not adopted until it is measured after the v2.4 F8)",
    "F8": "dose-response threshold: house method - no paper derives an overlap threshold from yield (footprint = the strip swept between the header line at the previous reading of the pass and the one at this reading, centred Y_Offset to the right of travel, the rectangle back along the travel when there is no usable predecessor; 0.25 m raster burnt in time order; bands 0, 0-2, 2-5, 5-10, 10-15, 15-25, 25-35, > 35 %; every record of the pass interiors (>= 15 records alive after F7 on both sides) against its local no-overlap controls: same combine (machine column, else SMS serial or Ops Center log), another pass, within max(15 m, 1.5 header widths), edge distance within 4 m, >= 5 controls; T = upper edge of the last consecutive band with >= 30 matched records whose median ratio over the placebo is within -3 %, never below 5 %, the resolution of the overlap measure; in-plot records when a plan leaves >= 200; with < 30 no-overlap records that have controls, each combine's no-overlap band, which needs >= 30 points and >= 500 points or >= 10 % of the combine's records, pooled by band size; 10 % fallback when the 0-2 % band fails; the house's overlap tests: the v2.3 chord rectangle counted a wedge of the predecessor as already cut; Simbahan et al. 2004 do not screen overlap)",
    "F9": "500-10,000 lb/ac wet for every crop: house window (560-11,209 kg/ha), about 12 % above Arizo-García et al. 2026 (0-10,000 kg/ha with a 500 kg/ha floor, wheat/barley, recorded yield), not a reproduction",
    "F10": "all combines pooled in one mean and SD: house rule (no per-machine screen); SMS 3-sigma: another yield pass while the SD falls > 25 %, at most 5 passes: house procedure",
    "F11": "+/- 10 records window and a minimum of 6 surviving records in it: house values (the record included; with fewer the record is kept untested)",
    "F5b": "10-record minimum re-applied to runs broken by any removal: house extension (Ping & Dobermann 2005 drop < 12-point harvest segments last; Marchant et al. 2019 trim N s at filter gaps)",
    "sessions": "sessions, the Ms inference, the shrink test and the discontinuity check: house method, diagnostic only (session = machine x local calendar day, decoder offset else round(longitude / 15) h; Ms inferred from >= 200 records with dry/wet < 0.999; one-sided shrink when dry == wet on >= 95 % of the records below Ms; 30 m cells, >= 5 kept points of each session, <= 2 % overlap first, >= 10 cells, >= 3 pass pairs; triggers > 2 moisture points or > 20 % below Ms; crop-table Ms other than corn 15.5 / soybean 13 %)",
    "machines": "harvest layout, methods, pairing, bootstrap and gates: house method (combines = the machine column, else the sources in parentheses at the end of the dataset names, or the dataset names that are VINs, when two or more differ; the factor follows the OCCD cascade or the SMS 3-sigma sequence; harvest layout of every pair of combines from the adjacency of their passes, >= 10 kept points within 1.5 header widths of the other combine: >= 50 % interleaved, 10-50 % mixed, < 10 % blocks; method auto = paired cells on interleaved or mixed passes, no factor in blocks or without contact (pseudo-combine evidence: machines.py item 11); machine x machine, track x track and point x point on request, each with a traffic light by layout; every pair of combines with >= 30 cells and >= 5 pass pairs (cells) or >= 5 pass pairs (track, point) solved together by weighted least squares on the log ratios; one factor must fit both halves of the field (within 5 % or not significant); reference = the combine with most kept points, Maldaner et al. 2016 use the largest area; pairs on records <= 2 % overlapped in 30 / 50 m cells with >= 5 points of each machine; 1,000-rep pass-pair bootstrap with the 95 % CIs excluding 1; 30 / 50 m factors within 2 %; 1 % floor; above 10 % nothing applied unless the grower's weight confirms it; ticket closure 1 %, 3 x; 5 % ticket-vs-paired warning)",
    "level": "L over every processed record, the 10 % 'check the ticket coverage' edge, the 5 % set-aside and 1 % ticket-tolerance warnings and the crop-table test weights: house rules (Clarke et al. 2024 rescale the cleaned-map mean; the 1 % and 3 % bands follow Luck & Fulton 2014)",
}
# the v2.3 texts of the steps v2.4 changed: a run with the v2.3 overlap model (yield_clean.LEGACY_V23) cites these
HOUSE_RULES_V23 = {
    "order": "lag scan after the cascade and the removal guardrails: house rules (published chains correct the delay first; advice above 60 % removed or when a filter removes > 50 % of its input; fewer than 30 kept points = no output)",
    "lag": "+/-8-record window, 5-point median, the first 14 and last 16 surviving points of a pass left out, >= 100 points per direction, pairs within 1.2 widths, gates 2 <= |lag| < 8 and r gain > 0.01: house rule",
    "F7": "first 4 / last 2 surviving records, one setting for all fields: house values, inside the 3-8 s / 2-4 s of the cited works (~4 s / 2 s at 1 Hz)",
    "F8": "dose-response threshold: house method - no paper derives an overlap threshold from yield (bands 0, 0-2, 2-5, 5-10, 10-15, 15-25, 25-35, > 35 %; T = upper edge of the last consecutive band with >= 30 points whose mean is within -3 % of the same combine's no-overlap band, a reference needing >= 30 points and >= 500 points or >= 10 % of the combine's records, pooled by band size; in-plot records when a plan leaves >= 200; 0.25 m raster; 10 % fallback when the 0-2 % band fails; Simbahan et al. 2004 do not screen overlap)",
}

# short forms that the generic rule (surnames before the comma of each ';'-separated author) gets wrong
SHORT_OVERRIDES = {
    "Blank 2022": "Blank 2022",
    "Chiocco 2019": "Chiocco & Wuestefeld 2019",
    "Hawkins 2024": "Hawkins et al. 2024",
    "Kharel 2018": "Kharel et al. 2018",
}


# ===================================================================================================== loading
def _short(key: str, authors: str) -> str:
    if key in SHORT_OVERRIDES:
        return SHORT_OVERRIDES[key]
    year = key.split()[-1]
    # one author per ';' as 'Surname, Initials'; parts without a comma are assignees / editorial remarks
    names = [a.split(",")[0].strip() for a in authors.split(";") if "," in a]
    if len(names) == 1:
        return f"{names[0]} {year}"
    if len(names) == 2:
        return f"{names[0]} & {names[1]} {year}"
    return f"{names[0]} et al. {year}"


def _row_to_ref(key, r) -> dict:
    doi = (r.get("doi") or "").strip()
    url = doi if doi.startswith("http") else (f"https://doi.org/{doi}" if doi else "")
    return {"short": _short(key, r["authors"]), "authors": r["authors"].strip(), "year": str(r["year"]).strip(),
            "title": r["title"].strip(), "venue": r["venue"].strip(), "volume": (r.get("volume") or "").strip(),
            "issue": (r.get("issue") or "").strip(), "pages": (r.get("pages") or "").strip(),
            "doi": doi.replace("https://doi.org/", ""), "url": url}


def load_csv(path: str = CSV_PATH) -> dict:
    """{key: reference} from references_verified.csv (utf-8 with BOM)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        k = r["key"].strip()
        if k in out:
            raise ValueError(f"duplicate key in {path}: {k}")
        out[k] = _row_to_ref(k, r)
    return out


def _load() -> dict:
    if os.path.exists(CSV_PATH):
        return load_csv(CSV_PATH)
    warnings.warn(f"references_verified.csv not found at {CSV_PATH}: using the embedded copy of the rows cited",
                  RuntimeWarning, stacklevel=2)
    return {k: _row_to_ref(k, r) for k, r in _EMBEDDED_ROWS.items()}


# ===================================================================================================== citing
def used_keys(step_ids=None) -> list:
    """Sorted keys cited by the given steps (default: every step), in the order of the short citation."""
    steps = STEP_ORDER if step_ids is None else [s for s in step_ids if s in SOURCES]
    keys = {e["key"] for s in steps for e in SOURCES[s]}
    return sorted(keys, key=lambda k: (REFERENCES[k]["short"].lower() if k in REFERENCES else k.lower(), k))


def short_citation(key: str) -> str:
    """'Sudduth & Drummond 2007' (the key itself when the work is unknown, so a report never crashes on it)."""
    r = REFERENCES.get(key)
    return r["short"] if r else key


def cite(step_id: str, notes: bool = True, max_items: int | None = None, house: str = "full",
         legacy: bool = False) -> str:
    """One-line citation of a step: 'Sudduth & Drummond 2007 (SMV example ratio 0.20); Griffin et al. 2008
    (0.10-0.20 applied); ...; <house rule>'. notes=False gives the short names only; max_items keeps the first N works
    and says how many more there are; house="short" cuts the house convention at its first parenthesis (for table
    cells), house="none" leaves it out; legacy=True cites the v2.3 house text of the steps v2.4 changed
    (HOUSE_RULES_V23)."""
    if step_id not in SOURCES:
        raise KeyError(f"unknown step {step_id!r}; steps are {STEP_ORDER}")
    entries = SOURCES[step_id]
    shown = entries if max_items is None else entries[:max_items]
    parts = [f"{short_citation(e['key'])} ({e['note']})" if notes else short_citation(e["key"]) for e in shown]
    if len(shown) < len(entries):
        parts.append(f"+ {len(entries) - len(shown)} more")
    rule = (HOUSE_RULES_V23.get(step_id) if legacy else None) or HOUSE_RULES.get(step_id, "")
    if rule and house != "none":
        parts.append(rule.split(" (")[0].strip() if house == "short" else rule)
    return "; ".join(parts)


def _compact(s: str, keep: int = 70) -> str:
    """Drop the editorial remark of a CSV field: everything from the first ' (' or ';' remark once the field is longer
    than `keep` characters ('article 2411950 (no page range in Crossref)' -> 'article 2411950')."""
    if len(s) <= keep:
        return re.split(r"\s\((?=[a-z])", s, maxsplit=1)[0].strip()
    return re.split(r"\s\(|;\s(?=assignee|et al\.|originally)", s, maxsplit=1)[0].strip()


def full_citation(key: str, compact: bool = False) -> str:
    """'Authors (year). Title. Venue, vol(issue), pages. https://doi.org/...' ('No DOI.' when the record has none).
    compact=True (the PDF) drops the CSV's editorial remarks on authors, venue and pages (assignees, 'article number',
    companion documents); the Markdown keeps the fields verbatim."""
    r = REFERENCES.get(key)
    if r is None:
        return key
    authors, venue, pages = r["authors"], r["venue"], r["pages"]
    if compact:
        authors, venue, pages = _compact(authors, 40), _compact(venue), _compact(pages, 0)
    s = f"{authors} ({r['year']}). {r['title']}. {venue}"
    if r["volume"]:
        s += f", {r['volume']}" + (f"({r['issue']})" if r["issue"] else "")
    if pages:
        s += f", {pages}"
    s = s.rstrip(".") + "."
    return s + (f" {r['url']}" if r["url"] else " No DOI.")


def filter_sources(filter_info: dict) -> dict:
    """Update FILTER_INFO in place: 'source' = cite(fid) (the key name kept for backward compatibility) and 'sources' =
    the list of SOURCES entries, for every filter id present in SOURCES. Returns the dict."""
    for fid, info in filter_info.items():
        if fid in SOURCES:
            info["source"] = cite(fid)
            info["sources"] = [dict(e) for e in SOURCES[fid]]
    return filter_info


def check_sources(refs: dict | None = None) -> list:
    """Problems in SOURCES / HOUSE_RULES against the reference table: unknown keys, bad 'supports', empty notes,
    duplicated keys within a step, steps without entries. Empty list = consistent."""
    refs = REFERENCES if refs is None else refs
    bad = []
    for s in STEP_ORDER:
        if s not in SOURCES:
            bad.append(f"{s}: no SOURCES entry")
            continue
        if not SOURCES[s]:
            bad.append(f"{s}: empty")
        seen = set()
        for e in SOURCES[s]:
            if e["key"] not in refs:
                bad.append(f"{s}: key {e['key']!r} is not in references_verified.csv")
            if e["supports"] not in SUPPORTS:
                bad.append(f"{s}: {e['key']} supports {e['supports']!r} (not in {SUPPORTS})")
            if not (e.get("note") or "").strip():
                bad.append(f"{s}: {e['key']} has no note")
            if e["key"] in seen:
                bad.append(f"{s}: {e['key']} listed twice")
            seen.add(e["key"])
        if s not in HOUSE_RULES:
            bad.append(f"{s}: no HOUSE_RULES entry (use '' when there is none)")
    for s in list(SOURCES) + list(HOUSE_RULES):
        if s not in STEP_NAMES:
            bad.append(f"{s}: not in STEP_NAMES")
    return bad


# ===================================================================================================== documents
def references_markdown() -> str:
    """The text of docs/REFERENCES.md: per step, the works with what they support, the note and the DOI, then the house
    conventions and the full list of works cited."""
    L = ["# References behind the cleaning steps", "",
         "Generated by `python -m engine.clean.references --write` from `engine/clean/references.py` (SOURCES, "
         "HOUSE_RULES) and `docs/literature/references_verified.csv`; do not edit by hand. The mapping follows "
         "`docs/literature/Yield_map_cleaning_literature_review.md`, sections 4.1-4.16, 5, 7.1 and 7.2. Every work "
         "below has a verified bibliographic record; a number that no verified paper gives is a **house rule** and "
         "is listed as such. \"Supports\" says what the work gives for the step: the *concept* (the error it "
         "documents or the idea of the filter), the *method*, a *threshold* it uses, or a *range* of values.", "",
         f"{len(used_keys())} works cited over {len(STEP_ORDER)} steps.", ""]
    for s in STEP_ORDER:
        L += [f"## {STEP_NAMES[s]}", "", f"Citation string (`cite(\"{s}\")`): {cite(s)}", "",
              "| Work | Supports | What the work gives | DOI |", "|---|---|---|---|"]
        for e in SOURCES[s]:
            r = REFERENCES.get(e["key"], {})
            url = r.get("url", "")
            L.append(f"| {short_citation(e['key'])} | {e['supports']} | {e['note']} | "
                     f"{('[' + r.get('doi', '') + '](' + url + ')') if url else 'no DOI'} |")
        house = HOUSE_RULES.get(s, "")
        L += ["", f"House convention: {house}" if house else "House convention: none (the threshold is the published example).", ""]
    L += ["## Works cited", ""]
    for k in used_keys():
        L.append(f"- **{short_citation(k)}** - {full_citation(k)}")
    L.append("")
    return "\n".join(L)


def write_markdown(path: str = MD_PATH) -> str:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(references_markdown())
    return path


def embedded_rows_source(keys=None) -> str:
    """Python source of _EMBEDDED_ROWS for the keys used (tools/build_references.py pastes it into this file)."""
    rows = load_csv(CSV_PATH)
    keys = used_keys() if keys is None else keys
    L = ["_EMBEDDED_ROWS = {"]
    for k in keys:
        r = rows[k]
        L.append(f"    {k!r}: {{\"authors\": {r['authors']!r}, \"year\": {r['year']!r}, \"title\": {r['title']!r},")
        L.append(f"        \"venue\": {r['venue']!r}, \"volume\": {r['volume']!r}, \"issue\": {r['issue']!r}, "
                 f"\"pages\": {r['pages']!r}, \"doi\": {r['url']!r}}},")
    L.append("}")
    return "\n".join(L)


# ===================================================================================================== embedded copy
# BEGIN EMBEDDED (generated by tools/build_references.py; the rows of references_verified.csv cited by SOURCES)
_EMBEDDED_ROWS = {
    'Alves 2026': {"authors": 'Alves, F.L.; de Souza, E.G.; Sobjak, R.; Bazzi, C.L.; Uribe-Opazo, M.A.; Hachisuca, A.M.M.; Mercante, E.', "year": '2026', "title": 'AgDataBox-Map-Clean: A Web-Based Module for Screening Yield Monitor Data and Improving Yield Maps',
        "venue": 'Agronomy (MDPI)', "volume": '16', "issue": '16', "pages": '1566 (article number)', "doi": 'https://doi.org/10.3390/agronomy16161566'},
    'Arizo-García 2026': {"authors": 'Arizo-García, P.; Castiñeira-Ibáñez, S.; Cruzado-Campos, E.; Ricarte, B.; Rubio, C.; San Bautista, A.', "year": '2026', "title": 'A Standardized Framework for Cleaning Non-Normal Yield Data from Wheat and Barley Crops, and Validation Using Machine Learning Models for Satellite Imagery',
        "venue": 'Agronomy (MDPI), ISSN 2073-4395', "volume": '16', "issue": '3', "pages": '386 (article number)', "doi": 'https://doi.org/10.3390/agronomy16030386'},
    'Arslan 2002a': {"authors": 'Arslan, S.; Colvin, T.S.', "year": '2002', "title": 'An Evaluation of the Response of Yield Monitors and Combines to Varying Yields',
        "venue": 'Precision Agriculture', "volume": '3', "issue": '2', "pages": '107-122', "doi": 'https://doi.org/10.1023/A:1013887801918'},
    'Carneiro 2022': {"authors": 'Carneiro, F. M.; Shiratsuchi, L.', "year": '2022', "title": 'How to Correct a Yield Map When Using Multiple Harvest Machines',
        "venue": 'Louisiana Crops Newsletter, LSU AgCenter (extension article, not refereed)', "volume": '12', "issue": '1', "pages": '', "doi": 'https://lsuagcenter.com/articles/page1645406281020'},
    'Chiocco 2019': {"authors": 'Chiocco, G. D.; Wuestefeld, E. A. (inventors); assignee: Trimble Inc. (current assignee per Google Patents: PTX Trimble LLC)', "year": '2019', "title": 'Crop yield data adjustments',
        "venue": 'United States Patent US 10,373,353 B2 (application US 14/068,644; filed 31 Oct 2013, priority 31 Oct 2013, granted 6 Aug 2019; pre-grant publication US 2015/0116330 A1, 30 Apr 2015)', "volume": '', "issue": '', "pages": '', "doi": ''},
    'Chung 2002': {"authors": 'Chung, S. O.; Sudduth, K. A.; Drummond, S. T.', "year": '2002', "title": 'Determining Yield Monitoring System Delay Time with Geostatistical and Data Segmentation Approaches',
        "venue": 'Transactions of the ASAE', "volume": '45', "issue": '4', "pages": '915-926', "doi": 'https://doi.org/10.13031/2013.9938'},
    'Clarke 2024': {"authors": 'Clarke, D.E.; Stockdale, E.A.; Hannam, J.A.; Marchant, B.P.; Hallett, S.H.', "year": '2024', "title": 'Whole-farm yield map datasets – Data validation for exploring spatiotemporal yield and economic stability',
        "venue": 'Agricultural Systems', "volume": '218', "issue": '', "pages": '103972 (article number)', "doi": 'https://doi.org/10.1016/j.agsy.2024.103972'},
    'da Silva 2024': {"authors": 'da Silva, E. R. O.; Molin, J. P.; Wei, M. C. F.; Canal Filho, R.', "year": '2024', "title": 'Automatic Filtering of Sugarcane Yield Data',
        "venue": 'AgriEngineering', "volume": '6', "issue": '4', "pages": '4812-4830', "doi": 'https://doi.org/10.3390/agriengineering6040275'},
    'Damiano 2022': {"authors": 'Damiano, L.; Niemi, J.', "year": '2022', "title": 'The RITAS algorithm: a constructive yield monitor data processing algorithm',
        "venue": 'arXiv preprint arXiv:2209.11313 [stat.ME] (submitted 22 Sep 2022, v1; 33 pages, 4 figures)', "volume": '', "issue": '', "pages": '33 pages (preprint)', "doi": 'https://doi.org/10.48550/arXiv.2209.11313'},
    'dos Santos 2025': {"authors": 'dos Santos, C. L.; Miguez, F. E.', "year": '2025', "title": 'A comparative study of yield monitor data processing methods for on-farm agronomic trials',
        "venue": 'Agronomy Journal', "volume": '117', "issue": '5', "pages": 'e70168', "doi": 'https://doi.org/10.1002/agj2.70168'},
    'Drummond 1999': {"authors": 'Drummond, S. T.; Fraisse, C. W.; Sudduth, K. A.', "year": '1999', "title": 'Combine Harvest Area Determination by Vector Processing of GPS Position Data',
        "venue": 'Transactions of the ASAE', "volume": '42', "issue": '5', "pages": '1221-1228', "doi": 'https://doi.org/10.13031/2013.13287'},
    'Edge 2024': {"authors": 'Edge, B.; Mieno, T.; Bullock, D. S.', "year": '2024', "title": 'Processing of On-Farm Precision Experiment Data in the DIFM Project',
        "venue": 'OSF Preprints (Open Science Framework, Center for Open Science), preprint n9rgu, posted 2024-02-21', "volume": '', "issue": '', "pages": '', "doi": 'https://doi.org/10.31219/osf.io/n9rgu'},
    'Gauci 2023': {"authors": 'Gauci, A. A.; Fulton, J. P.; Lindsey, A.; Shearer, S. A.; Barker, D.; Hawkins, E. M.', "year": '2023', "title": 'Precision of grain yield monitors for use in on-farm research strip trials',
        "venue": 'Precision Agriculture', "volume": '25', "issue": '2', "pages": '771-784', "doi": 'https://doi.org/10.1007/s11119-023-10092-y'},
    'Griffin 2008': {"authors": 'Griffin, T.W.; Dobbins, C.L.; Vyn, T.J.; Florax, R.J.G.M.; Lowenberg-DeBoer, J.M.', "year": '2008', "title": 'Spatial analysis of yield monitor data: case studies of on-farm trials and farm management decision making',
        "venue": 'Precision Agriculture', "volume": '9', "issue": '5', "pages": '269-283', "doi": 'https://doi.org/10.1007/s11119-008-9072-2'},
    'Han 1997': {"authors": 'Han, S.; Schneider, S. M.; Rawlins, S. L.; Evans, R. G.', "year": '1997', "title": 'A Bitmap Method for Determining Effective Combine Cut Width in Yield Mapping',
        "venue": 'Transactions of the ASAE', "volume": '40', "issue": '2', "pages": '485-490', "doi": 'https://doi.org/10.13031/2013.21267'},
    'Lee 2012': {"authors": 'Lee, D. H.; Sudduth, K. A.; Drummond, S. T.; Chung, S. O.; Myers, D. B.', "year": '2012', "title": 'Automated Yield Map Delay Identification Using Phase Correlation Methodology',
        "venue": 'Transactions of the ASABE', "volume": '55', "issue": '3', "pages": '743-752', "doi": 'https://doi.org/10.13031/2013.41506'},
    'Luck 2014': {"authors": 'Luck, J. D.; Fulton, J. P.', "year": '2014', "title": 'Precision Agriculture: Best Management Practices for Collecting Accurate Yield Data and Avoiding Errors During Harvest (EC2004)',
        "venue": 'University of Nebraska-Lincoln Extension, Extension Circular EC2004 (published 8 Sep 2014; 6 pp.). Companion: EC2005 "Improving Yield Map Quality by Reducing Errors through Yield Data File Post-Processing", Luck, J.; Mueller, N.; Fulton, J. P., 2015 (published 4 Sep 2015)', "volume": '', "issue": '', "pages": '6 pp. (EC2004)', "doi": ''},
    'Luck 2015': {"authors": 'Luck, J. D.; Mueller, N.; Fulton, J. P.', "year": '2015', "title": 'Improving Yield Map Quality by Reducing Errors through Yield Data File Post-Processing',
        "venue": 'Nebraska Extension Circular EC2005, University of Nebraska-Lincoln Extension (Institute of Agriculture and Natural Resources)', "volume": '', "issue": '', "pages": '9 pp.', "doi": ''},
    'Lyle 2014': {"authors": 'Lyle, G.; Bryan, B. A.; Ostendorf, B.', "year": '2014', "title": 'Post-processing methods to eliminate erroneous grain yield measurements: review and directions for future development',
        "venue": 'Precision Agriculture', "volume": '15', "issue": '4', "pages": '377-402', "doi": 'https://doi.org/10.1007/s11119-013-9336-3'},
    'Maldaner 2020': {"authors": 'Maldaner, L. F.; Molin, J. P.', "year": '2020', "title": 'Data processing within rows for sugarcane yield mapping',
        "venue": 'Scientia Agricola', "volume": '77', "issue": '5', "pages": 'e20180391 (article number)', "doi": 'https://doi.org/10.1590/1678-992x-2018-0391'},
    'Maldaner 2016': {"authors": 'Maldaner, L. F.; Molin, J. P.; Canata, T. F.', "year": '2016', "title": 'Processing yield data from two or more combines',
        "venue": 'Proceedings of the 13th International Conference on Precision Agriculture, July 31 - August 4, 2016, St. Louis, Missouri, USA (International Society of Precision Agriculture, Monticello, IL)', "volume": '', "issue": '', "pages": '9 pp. (unpaginated conference paper; no page range in the source)', "doi": ''},
    'Marchant 2019': {"authors": 'Marchant, B.; Rudolph, S.; Roques, S.; Kindred, D.; Gillingham, V.; Welham, S.; Coleman, C.; Sylvester-Bradley, R.', "year": '2019', "title": "Establishing the precision and robustness of farmers' crop experiments",
        "venue": 'Field Crops Research', "volume": '230', "issue": '', "pages": '31-45', "doi": 'https://doi.org/10.1016/j.fcr.2018.10.006'},
    'Menegatti 2003': {"authors": 'Menegatti, L. A. A.; Molin, J. P.', "year": '2003', "title": 'Metodologia para identificação e caracterização de erros em mapas de produtividade',
        "venue": 'Revista Brasileira de Engenharia Agrícola e Ambiental', "volume": '7', "issue": '2', "pages": '367-374', "doi": 'https://doi.org/10.1590/S1415-43662003000200031'},
    'Menegatti 2004': {"authors": 'Menegatti, L. A. A.; Molin, J. P.', "year": '2004', "title": 'Remoção de erros em mapas de produtividade via filtragem de dados brutos',
        "venue": 'Revista Brasileira de Engenharia Agrícola e Ambiental', "volume": '8', "issue": '1', "pages": '126-134', "doi": 'https://doi.org/10.1590/S1415-43662004000100019'},
    'Owen 2024': {"authors": 'Owen, O. K.; Sudduth, K. A.; Abendroth, L. J.', "year": '2024', "title": 'USDA LTAR Common Experiment measurement: Post-processing of spatial grain yield data v1',
        "venue": 'protocols.io (USDA Long-Term Agroecosystem Research network, Common Experiment measurement protocol); Crossref publisher of record: Springer Science and Business Media LLC (protocols.io is a Springer Nature platform)', "volume": '', "issue": '', "pages": '', "doi": 'https://doi.org/10.17504/protocols.io.4r3l2qmy3l1y/v1'},
    'Ping 2005': {"authors": 'Ping, J. L.; Dobermann, A.', "year": '2005', "title": 'Processing of Yield Map Data',
        "venue": 'Precision Agriculture', "volume": '6', "issue": '2', "pages": '193-212', "doi": 'https://doi.org/10.1007/s11119-005-1035-2'},
    'Simbahan 2004': {"authors": 'Simbahan, G. C.; Dobermann, A.; Ping, J. L.', "year": '2004', "title": 'Screening Yield Monitor Data Improves Grain Yield Maps',
        "venue": 'Agronomy Journal', "volume": '96', "issue": '4', "pages": '1091-1102', "doi": 'https://doi.org/10.2134/agronj2004.1091'},
    'Sudduth 2007': {"authors": 'Sudduth, K.A.; Drummond, S.T.', "year": '2007', "title": 'Yield Editor: Software for Removing Errors from Crop Yield Maps',
        "venue": 'Agronomy Journal', "volume": '99', "issue": '6', "pages": '1471-1482', "doi": 'https://doi.org/10.2134/agronj2006.0326'},
}
# END EMBEDDED

REFERENCES = _load()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="literature behind the cleaning steps")
    ap.add_argument("--write", nargs="?", const=MD_PATH, metavar="REFERENCES.md",
                    help="write docs/REFERENCES.md (or the given path)")
    ap.add_argument("--check", action="store_true", help="check SOURCES against the CSV and exit 1 on a problem")
    ap.add_argument("step", nargs="?", help="print cite(step)")
    a = ap.parse_args(argv)
    if a.check:
        bad = check_sources()
        print("\n".join(bad) if bad else "SOURCES consistent with references_verified.csv")
        return 1 if bad else 0
    if a.write:
        print(write_markdown(a.write))
    if a.step:
        print(cite(a.step))
    if not a.write and not a.step:
        for s in STEP_ORDER:
            print(f"{s}: {cite(s)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
