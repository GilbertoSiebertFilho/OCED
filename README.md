# OCED — Olds College Extract Data

OCED opens the files that come from the machines (combines, planters and sprayers), shows the map of every
attribute, cleans the data with the 3-sigma method of Ag Leader SMS, and writes the clean shapefiles and the reports.
It is a Streamlit app that runs on the user's own computer (Windows); the files never leave it.

Installation in Portuguese, step by step: [INSTALAR.txt](INSTALAR.txt).

## Start the app

Double-click `run_oced.bat`, or from this folder:

```
python -m streamlit run app\oced.py --server.port 8502
```

The app opens in the browser at http://localhost:8502. Install the packages once with `install_oced.bat` (a private
environment `.venv` in this folder, the tested versions of `constraints.txt`), or by hand with
`python -m pip install -r requirements.txt` (Python 3.12 or newer). `atualizar_oced.bat` updates an installed folder
to the newest version of this repository (branch `main`), keeping a backup and rolling back on any failure.

## The four steps

1. **Machine data.** Upload the files, or type a file or folder on this computer (nothing is copied).
   - *Combines, raw:* a Case IH / New Holland AFS Pro 700 card (`.cn1` folder, zipped or not), John Deere Gen4 / G5 /
     X9 logs (the JD-Data folder with `log/*.jdl`), a John Deere GreenStar 3 card (`.fdd` + `.fdl`). The units
     (tasks, machines, loads) are listed; the chosen ones are extracted as **one point shapefile per field, season and
     crop**, so a card of many fields gives many files at once.
   - *Point exports:* yield points from SMS or Operations Center (shapefile, or `.kml` / `.kmz`), the **as-applied
     points of planters and sprayers** (shapefile), or any other point shapefile of a machine. What a file is
     (harvest, seeding, application, other points) is read from its columns.
2. **Map and attributes.** One button per attribute colours the map over the satellite image (the strips the header
   swept, or the points), with the legend, the statistics, the histogram, the table of every attribute and the first
   records. The field boundary, once given, is drawn on the map.
3. **Cleaning: 3-sigma.** Each file keeps its own field boundary and settings; one file or all of them at once.
   - *Harvest:* the SMS 3-sigma sequence as SMS Advanced runs it: S0 import check (no position, no yield, dry yield
     below 5 bu/ac), **S1 Clip To Field Boundary**, S2 Optimize Swath Widths (overlapping strips removed or narrowed,
     per-area values scaled), S3 speed, S4 moisture and S5 dry yield within mean ± 3 SD of the points still alive,
     another yield pass while the SD falls by more than 25 %. No combine factor between harvesters.
     **The grower's data** of the field (total weight with its unit — lb, kg, bu or t — and basis, the grain moisture
     on the ticket, the bushel weight) **validate** the yields: the monitor's total against the grower's on the same
     basis (at the standard moisture when the grain moisture is given), `L = grower / monitor` and a verdict
     (≤ 1 %, 1–3 %, 3–10 %, > 10 %). *Validate and adjust* also writes `Yld_Level` (the dry yield × L) into the
     clean file; the monitor's columns always stay as logged.
   - *Planters, sprayers and other points:* the same 3-sigma rule on the attributes chosen (by default the applied
     rate and the speed): S0 import check (no position; the main attribute missing or at or below the minimum, 0 =
     no product applied), S1 Clip To Field Boundary, one 3-sigma step per attribute (the speed first), the main
     attribute repeated while its SD falls by more than 25 %. Limits rounded to 2 decimals as typed in SMS.
   - The boundary is a `.zip` (a shapefile or an SMS *Boundaries* export), a `.shp` with its `.shx`, `.dbf` and
     `.prj`, a `.geojson`, `.gpkg`, `.kml` or `.kmz`; a file of several fields asks which one is this field. A point
     on the edge is inside (1 cm tolerance, as SMS).
   - The result: the steps (what each removed), the limits of each 3-sigma step, the clean map, the map of the removed
     points by step, and for a harvest with the grower's data the validation.
4. **Clean shapefiles and reports.** For each file: the clean shapefile (the kept readings with every attribute of the
   file, in one zip), the flagged points (every reading with `Keep` and `Rem_By`, the step that removed it), the
   cleaning report (PDF: the steps, the limits, the statistics and the maps) and the cleaning record (JSON); all the
   clean shapefiles in one zip.

## Files

| Path | What it is |
|---|---|
| `app/oced.py` | the app (the four steps) |
| `app/brand.py` | name, version, Olds College palette, logos and the page's CSS |
| `engine/formats/` | the decoders of the raw monitor formats (`cnh_cn1`, `jd_jdl`, `jd_gs3_rcd`), KML points, Operations Center section exports, and `detect.py` (what an input holds) |
| `engine/clean/yield_clean.py`, `sms3sigma.py`, `sms_swath.py` | the cleaning of harvest files: the SMS 3-sigma sequence and Optimize Swath Widths |
| `engine/clean/aoi.py` | the field boundary: read any polygon file, choose the field, inside / outside |
| `engine/clean/sessions.py`, `machines.py`, `references.py` | moisture basis and harvest sessions, machines, the literature cited by the report |
| `engine/clean/applied3s.py` | the 3-sigma cleaning of planter, sprayer and other point files |
| `engine/report/` | the PDF reports (`clean_report.py` for harvest files, `applied_report.py` for the others) |
| `engine/run.py` | the API from the files to the clean shapefile (`open_input`, `list_units`, `decode`, `clean`) and a command line (`python -m engine.run --help`) |
| `tests/` | end-to-end tests on synthetic fields (`python -m pytest -q tests`); no real data in the repository |
| `workspace/` | the work folders (not in the repository) |

Grower data (monitor cards, exports, boundaries, results) never goes into this repository: `.gitignore` lets only the
code and the documents in.

## Limitations

- Planters and sprayers are read from their **point exports** (SMS, Operations Center, the display's export). The
  raw planter and sprayer records of the monitor cards (`.cn1`, JD-Data, GreenStar 3) are not decoded yet: a raw
  card is read for its harvest data only. Send a sample card to add them.
- The as-applied cleaning has no overlap step: Optimize Swath Widths is a harvest step of SMS.
- The grower's data (validation and adjustment) apply to harvest files.
- The satellite image under the maps needs the internet; the points and strips are drawn without it.
