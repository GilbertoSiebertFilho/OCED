# OCED — Olds College Extract Data

OCED opens the files that come from the machines (combines, planters and sprayers), imports them as Ag Leader SMS
Advanced does, shows the map of every attribute, cleans the data with the 3-sigma method of SMS, and writes the clean
data (a shapefile, or the clean harvest in the monitor's own raw format) and the reports. It is a Streamlit app that
runs on the user's own computer (Windows); the files never leave it.

**Version 0.3.0** (shown in the app's title bar and sidebar). It reads Case IH / New Holland cards, John Deere
GreenStar 3 cards and Gen4 logs, ISOXML harvest task data and point exports; besides the clean shapefile it writes
the shapefile for DIFM (with the choice of the yield it carries) and the clean harvest in the monitor's own format.

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

The work folders go to `workspace/` in this folder. The environment variable `OCED_WORKSPACE`, read when the app
starts, puts them elsewhere: `setx OCED_WORKSPACE C:\OCED_work` in a Command Prompt, then close the app's window and
start it again with a double click on `run_oced.bat` or from a new Command Prompt (setx does not change the Command
Prompt it is typed in). The saved works and `cn1_card_names.json` (the Case IH card names already given) are read
from the workspace folder: to keep them, move them into the new one while the app is closed. Windows opens a path of
at most 259 characters (OCED assumes so also where long paths are turned on, so that its outputs open in any
program): a cleaning needs a workspace folder of at most 162 characters, and the app says what to do when it is
deeper.

## The four steps

1. **Machine data.** Upload the files, or type a file or folder on this computer. A folder is read in place; a
   `.zip` (and every zip inside a folder) is unpacked into the work folder (`input/`), all of it, also the datasets
   you do not pick, and each Open makes a new work folder with its own copy.
   - *Combines, raw:* a Case IH / New Holland AFS Pro 700 card (`.cn1` folder, zipped or not), John Deere Gen4 / G5 /
     X9 logs (the JD-Data folder with `log/*.jdl`), a John Deere GreenStar 3 card (`.fdd` + `.fdl`), ISOXML
     harvest task data (ISO 11783: `TASKDATA.XML` with its `TLG*.XML` / `TLG*.BIN` time logs, any number of
     TASKDATA sets, also a zip of zipped sets as a telematics portal hands them out). The units
     (tasks, machines, loads) are listed; the chosen ones are extracted as **one point shapefile per field, season and
     crop**, so a card of many fields gives many files at once.
   - *Point exports:* yield points from SMS or Operations Center (shapefile, or `.kml` / `.kmz`), the **as-applied
     points of planters and sprayers** (shapefile), or any other point shapefile of a machine. What a file is
     (harvest, seeding, application, other points) is read from its columns. An Operations Center export gets its
     product from the `-Deere-Metadata.json` beside it, and its dry yield is computed again from the wet mass like
     any other file (its own `VRYIELDVOL` is the Operations Center's dry yield, at its own standard moisture).
   - *Import as SMS:* the data comes in as SMS Advanced imports a harvest (its Processing Settings,
     `engine/sms_import.py`), with the values SMS gives each source:
     - **John Deere** files (GreenStar 3 cards, Gen4 `.jdl` logs) and **Operations Center** exports: the weight to
       volume and the dry moisture of the file's crop — a GreenStar 3 card's own crop definition; for Gen4 logs and
       Operations Center exports the values SMS gives that crop (wheat 60 lb/bu, 13.5 %; barley 48 lb/bu, 15.0 %),
       not the file's own, shown as "SMS's value for this John Deere crop" — min. yield volume 5 bu/ac and max.
       10,000 bu/ac (SMS's values for these files; type the max when SMS holds another one for the product);
       SMS's product table below
       only when the file carries no crop definition.
     - **ISOXML** task data (`engine/formats/isoxml.py`): read as SMS reads it, every time log on its own (a
       reading = a record with header sections on and grain flow; its grain is the flow logged one latency later,
       so the last seconds of each log file are no readings; "Time logs: joined" in the decoding options keeps
       them). The weight to volume and the dry moisture are what SMS gives the task's crop (wheat 60 lb/bu, 13.5 %;
       canola 50 lb/bu, 10.0 %), not the density and reference moisture the log carries; min. 5 and max. 10,000
       bu/ac; another crop OCED knows takes SMS's product table below; a crop code it does not know takes the
       log's own density and reference moisture (labelled "from the file", with what they read like and a warning
       to check the product); a task with no crop and no density takes 56 lb/bu and 13.0 %, SMS's values for a
       dataset without a product. The point sits where SMS puts it: the logged position moved by the header's
       offsets, sideways to the centre of the sections the display logs. Section positions that do not lie side
       by side (a display that logged them while laying its header out) are passed over, with a warning: the
       sections are then taken side by side, centred on the header.
     - **Case IH / New Holland** cards and the other point exports: SMS's product table — Wheat - Spring 60 lb/bu,
       13.5 %, 5–300 bu/ac; Wheat - Durum 60, 13.0 %, 5–300; Barley (Fall or Spring) 48, 14.5 %, 5–200; Canola 50,
       8.5 %, 10–400; Field Peas and Chick Peas 60, 13.0 %, 5–200; Lentils 60, 14.0 %, 5–200; Oats - Spring 32,
       14.0 %, 5–200; Flax 60, 10.0 %, 10–400; Rye - Annual 56, 14.0 %, 0–500. The crop names cards and exports
       carry (`DURUM`, `Durum Wheat`, `CANOLA`, `HRS wheat`, `Barley - Fall` ...) are mapped to these products; a
       crop outside the table takes its weight and moisture from the crop table and 5–300 bu/ac.
     - Everywhere: expand dry moisture off (one-sided: grain drier than the dry moisture is not raised to it),
       manual swath and moisture off, start / stop delay and flow shift 0 s. The flow shift and the delays work
       within each run of continuous logging (a hole in the log — header up, a stop, the night — starts a new run).
     Every value stays editable: step 1 holds the defaults for the files opened next (empty = the source's value),
     and each value the user types wins; the import records where each value came from (the file, SMS's product
     table, SMS's values for John Deere files, or you). The dry yield of every file is computed again from its wet mass
     with these values (SMS ignores the dry yield a point file carries); a file without a moisture column keeps the
     dry / wet ratio of each of its readings.
2. **Map and attributes.** One button per attribute colours the map over the satellite image (the strips the header
   swept, or the points), with the legend, the statistics, the histogram, the table of every attribute and the first
   records. The field boundary, once given, is drawn on the map. For each open harvest file: the **header width as
   logged** per combine (an initial audit: the most common width should be the header's), and the **import settings
   of this file** — the values it was imported with, every one editable, with *Import this file again* (the map,
   the statistics and the cleaning then start from the new import; its earlier cleaning is dropped).
3. **Cleaning: 3-sigma.** Each file keeps its own field boundary and settings; one file or all of them at once.
   - *Harvest:* the SMS 3-sigma sequence as SMS Advanced runs it. With a boundary the readings outside it are set
     aside first (**S1 Clip To Field Boundary**, shown first in the steps), then S0 import check (no position, no
     yield, dry yield below the import's minimum: after an import as SMS it normally finds nothing), S2 Optimize Swath
     Widths (overlapping strips removed or narrowed, per-area values scaled), **S3 moisture, S4 speed** and S5 dry
     yield within mean ± 3 SD of the points still alive, another yield pass while the SD falls by more than 25 %.
     The mean and SD (the setting *Mean and SD per*) are taken **per combine** over all its tasks and days, one
     group for the field when one combine cut it; "task" and "field" are explicit choices, and the earlier order
     speed-then-moisture is a setting (filter_order). *Optimize Swath Widths passes* (swath_passes, 1 to 3, default
     1) is beside them: 2 or 3 repeat an SMS cleaning in whose chain Clip + Optimize Swath Widths was added that many
     times (each further pass clips again and narrows what the pass before left); the cleaning record and the
     report's Optimize Swath Widths line say the passes, and a change after a cleaning says to clean again.
     A combine whose
     logged points sit 1 ft or more beside the strip it cut is reported before the swath step (swath_bias "warn").
     Not established against SMS, so off by default: moving such a combine's points back (swath_bias "auto") and
     Optimize Swath Widths per combine (swath_scope "machine") are not yet established against SMS; the rule that
     an empty moisture or speed cell is not removed by that filter is likewise not yet confirmed on an SMS
     cleaning. **Several combines:** the combine factor of OCCD
     (paired cells, track × track, point × point or machine × machine, chosen from how the combines shared the
     field) is off until the user switches it on; beside the switch, the median difference between neighbouring
     passes of different combines and of the same combine (from the last cleaning), to decide. The factor is
     estimated on the yield of the map, after Optimize Swath Widths, and `Yld_Harm` is in the clean file only when a
     factor was applied. The cards above the clean map and the Steps tab show how each step moved the mean and the
     SMS Average.
     **The grower's data** of the field (total weight with its unit — lb, kg, bu or t — or the yield per acre in
     bu/ac with the acres it is over; the basis, the grain moisture on the ticket, the bushel weight) **validate**
     the yields: the monitor's total against the grower's on the same basis, `L = grower / monitor` and a verdict
     (≤ 1 %, 1–3 %, 3–10 %, > 10 %). The two totals are compared as masses in the file's own bushel: a bushel weight
     never changes a weight given in lb, kg or t. A weight *at the standard moisture* is compared with the file's dry
     yield as imported (one-sided), and `Yld_Level` then sums to that weight; a wet weight with its grain moisture is
     a dry-matter comparison. A yield per acre without acres is over the boundary when the clip is on, else over the
     area harvested (every strip once, after S2). *Validate* changes no yield and lets the weight confirm no combine
     factor; *validate and adjust* also writes `Yld_Level` (the dry yield × L) into the clean file. The monitor's
     columns always stay as logged.
   - *Planters, sprayers and other points:* the same 3-sigma rule on the attributes chosen (by default the applied
     rate and the speed): S0 import check (no position; the main attribute missing or at or below the minimum: 0 =
     no product applied for a rate, no minimum for other point data), S1 Clip To Field Boundary, one 3-sigma step
     per attribute (the speed first), the main attribute repeated, per machine, while that machine's SD falls by
     more than 25 %. Limits rounded to 2 decimals as typed in SMS; the lower limit is floored at 0 only for an
     attribute with no negative value. A reading with no value of an attribute is not removed by that attribute's
     step (counted and warned about, as the harvest steps do; not yet confirmed on an SMS cleaning). The counts
     "inside the boundary" and "removed %" are those of the boundary (a reading outside it that S0 removed first is
     still counted outside). A drill that logs seed by mass is recognised as seeding when its product names a crop,
     in step 1 already (from a sample of its records).
   - The boundary is a `.zip` (a shapefile or an SMS *Boundaries* export), a `.shp` with its `.shx`, `.dbf` and
     `.prj`, a `.geojson`, `.gpkg`, `.kml` or `.kmz`; a file of several fields asks which one is this field
     (polygons that all carry one field name, none overlapping another and each within 100 m of another, are taken
     together as that field without asking; a drawing tool's default name such as "Untitled Polygon" is no field
     name). A point on the edge is inside (1 cm tolerance, as SMS).
   - The result: the steps (what each removed), the limits of each 3-sigma step, the clean map, the map of the removed
     points by step, and for a harvest with the grower's data the validation.
4. **Clean data and reports.** For each file: the clean shapefile (the kept readings with every attribute of the
   file, in one zip), the flagged points (the readings with `Keep` and `Rem_By`, the step that removed it: for a
   harvest file every reading inside the boundary, the readings clipped by S1 counted in step 3, not listed; for a
   planter or sprayer file every reading, the clipped ones with `Rem_By` S1), the
   cleaning report (PDF: the steps, the limits, the statistics and the maps) and the cleaning record (JSON); all the
   clean shapefiles in one zip. Next to the clean shapefile, the clean harvest can be written in the **monitor's own
   raw format**, so that SMS reads it as monitor data (`engine/formats/*_write.py`, one dispatcher
   `native_write.py`): a Case IH / New Holland `.cn1` card, a John Deere GreenStar 3 card or Gen4 `.jdl` logs,
   written from the input the file was decoded from (it must still be on the computer, and decoded by this version:
   a file of a saved work extracted by an older version of OCED is said to be so when the work is opened, and is
   offered as ISOXML only until its raw data is opened again); **ISOXML TASKDATA** is the
   format offered where no native writer applies (point exports, KML conversions), and the own format of ISOXML
   task data (a new TASKDATA set of the clean readings, not a copy of the display's set; every reading at its own
   time: where the readings of a combine cannot follow each other in one time log, because SMS puts records closer
   than 0.9 s together, they are written in further time logs of the same combine, as many as are needed (up to
   four per combine), and SMS shows one dataset per time log). *SMS acceptance not yet tested:*
   SMS has not yet read these files back; import them into a test project first. They are written in
   `native/<file>/<cn1|gs3|jdl|isoxml>...` of the work folder (a Gen4 or ISOXML set may carry a time stamp in its
   name), one set per format: writing a format again replaces its earlier set once the new one is written (a write
   that is refused or fails leaves the earlier set, its zip and its record as they were); a write whose deepest
   path would pass 250 characters is refused with the number of characters over (open the data again, or, when
   the workspace folder itself is too deep, use a shorter one: `OCED_WORKSPACE`, above). A Case IH card
   written also adds its new folder name to `cn1_card_names.json` in the workspace (outside the work folders), so
   that no card name is given twice.

   **Shapefile for DIFM.** Next to the clean shapefile of each file, step 4 offers the zip to upload to DIFM
   (difm.farm), which reads the layout of Ag Leader SMS shapefile exports (`engine/difm.py`, also in
   `clean_shapefiles/`). A harvest's, `<file>_sms3s_clean_DIFM.zip`, holds the same clean readings at the same
   positions with exactly the fields Field, Dataset, Product, Obj__Id, Distance_f, Track_deg_, Duration_s, Elevation_,
   Time, Swth_Wdth_, Y_Offset_f, Moisture__, Yld_Mass_W, Yld_Vol_We, Yld_Mass_D, Yld_Vol_Dr, Speed_mph_ and Date, in
   the dBASE widths of the file DIFM was seen to read, with the values of the clean file: text as it is, numbers
   with 6 decimals (N 24.6: more than any monitor resolves, an SMS export itself has 4; a number the clean file holds
   with more is rounded, half to even, and a zero is written 0.000000, never -0.000000). With 15 decimals the zip of
   a large field passed 10 MB; a zip that still ends over 10 MB is a warning of step 4. Y_Offset_f is 0 when the
   source has no lateral offset; WGS 84 with the `.prj` SMS writes.
   A field the clean file does not hold (an Operations Center export has no Field, Dataset, Product, Duration_s,
   Yld_Vol_We or Yld_Mass_D) is filled only with what follows exactly from the clean file's own values and from the
   file's import as SMS, never with an invented value: mass = volume x the import's weight to volume and volume =
   mass / it, on the wet and on the dry side (when that import computed the file's yields with it); Duration_s = the
   time step of the readings (the step between consecutive readings of a combine that 90 % of them share: 1 s for a
   log of one reading per second); Field = the field the export's Operations Center metadata names, Product = the
   crop the import read from the file, Dataset = the combine of each reading. What does not follow stays empty (the
   writer's notes say why), and readings without Yld_Mass_D or Yld_Vol_Dr, the fields DIFM maps as the yield, are a
   warning of step 4.
   Time and Date are dBASE dates, the date of each reading: an SMS export's own date as it is; for a time of day its
   calendar day, by one rule for every time in UTC (John Deere logs and cards, and any time that says its zone, as
   the IsoTime of an Operations Center export): this computer's clock time at that instant, as SMS shows it (the
   cleaning's `Harv_Day` uses the solar day for a John Deere log and the day of the time as it is for an export, so
   it can differ by a day there); a time that says no zone, of any other source, is taken as it is (ISOXML task
   data: the time is the display's own clock, which SMS shows as it is, so each reading keeps its own day); else
   `Harv_Day`
   or the date in the dataset name. A zip written by an earlier version (15 decimals) is written again when step 4
   shows it. A planter or
   sprayer file's, `<file>_3s_clean_DIFM.zip`, keeps its own columns with its dates as dBASE dates (the rate's unit is
   chosen in DIFM's Define Features); it has not been tried on DIFM yet. The clean shapefile keeps all its columns.

   *Which yield DIFM gets.* When the cleaning adjusted the yield (a combine factor applied and / or the grower's
   weight used to adjust), step 4 asks which yield the harvest's file carries; with no adjustment there is no
   question and the plain file is written.
   - **3-sigma + combine correction and grower's weight (adjusted yield)**, the default,
     `<file>_sms3s_clean_adjusted_DIFM.zip`: `Yld_Vol_Dr` is the yield the cleaning adjusted, the column it names as
     the one to map (`Yld_Harm` = the clean dry yield x the combine factor; `Yld_Level` = the clean dry yield x the
     combine factor x L when the grower's weight adjusts), and `Yld_Mass_D`, `Yld_Mass_W` and `Yld_Vol_We` are the
     monitor's values (the clean file's, or those filled from the import's weight to volume) x the same factor per
     reading (adjusted / monitor dry yield), so DIFM reads the same yield by
     Mass or by Volume and the bushel weight and the moisture stay the monitor's; a reading whose monitor yield is 0
     stays 0. Every other field, the layout and the points are those of the other file. The choice names only what
     was applied (combine correction, grower's weight, or both).
   - **3-sigma only (the monitor's yield)**, `<file>_sms3s_clean_DIFM.zip`: the monitor's dry yield as cleaned; step 4
     then says that the adjusted yield is not in that file.

   Each choice has its own file name, so both can be in `clean_shapefiles/`; step 4 offers the one chosen, its
   caption says which yield it carries with the combine factors and L, and the cleaning record (JSON,
   `shapefile_for_difm`) says which was generated, so a work opened again keeps the choice. A new cleaning starts from
   the default. A grower's weight used to validate only is not an adjustment; the symmetric dry yield (`Yld_Dry_Sy`)
   is not one either and has no field in this layout. A cleaning that must be cleaned again gets no DIFM file; a
   write that failed (the zip held open by another program) is tried again with **Write it again**.

**Sidebar.** *Saved works*: the name of this work with **Save**, and the saved works with **Open** (the files, their
boundaries, the grower's data, the settings and the cleanings come back without running again; a work is also saved
automatically after each extraction and cleaning, in `oced_work.json` inside its work folder; older work folders are
listed too, rebuilt from their files). Opening a work saved by an older version of OCED says which files that version
extracted (raw data: open it again for the current decode) or imported with other settings than this version would
(a point export, e.g. an Operations Center export whose crop was not read then: open the export again for the
current import as SMS, or import it again in step 2, whose import settings then hold this version's values); a new
cleaning does not change either. *Action tree*: the four steps and, file by file, the boundary, the grower's data, the
cleaning (kept, removed %, L) and the outputs; a file name shows that file in steps 2 to 4.

## Files

| Path | What it is |
|---|---|
| `app/oced.py` | the app (the four steps) |
| `app/brand.py` | name, version, Olds College palette, logos and the page's CSS |
| `engine/formats/` | the decoders of the raw monitor formats (`cnh_cn1`, `jd_jdl`, `jd_gs3_rcd`, `isoxml`), their writers of the clean harvest (`*_write.py`, ISOXML `isoxml_write.py`), KML points, Operations Center section exports, and `detect.py` (what an input holds) |
| `engine/clean/yield_clean.py`, `sms3sigma.py`, `sms_swath.py` | the cleaning of harvest files: the SMS 3-sigma sequence and Optimize Swath Widths |
| `engine/clean/aoi.py` | the field boundary: read any polygon file, choose the field, inside / outside |
| `engine/clean/sessions.py`, `machines.py`, `references.py` | moisture basis and harvest sessions, machines, the literature cited by the report |
| `engine/clean/applied3s.py` | the 3-sigma cleaning of planter, sprayer and other point files |
| `engine/difm.py` | the clean file as a shapefile for DIFM: a harvest in the layout of an SMS shapefile export, a planter / sprayer file with its own columns and dBASE dates |
| `engine/sms_import.py` | import as SMS: the Processing Settings of SMS's Grain Harvest import, per source and product, and where each value came from |
| `engine/works.py` | saved works: `oced_work.json` per work folder (save, open, list; older folders rebuilt from their files; the input folder of a decoded card kept, found again when the work folder moved) |
| `engine/report/` | the PDF reports (`clean_report.py` for harvest files, `applied_report.py` for the others) |
| `engine/run.py` | the API from the files to the clean shapefile (`open_input`, `list_units`, `decode`, `import_as_sms`, `clean`) and a command line (`python -m engine.run --help`, below) |
| `tests/` | end-to-end tests on synthetic fields (`python -m pytest -q tests`, run on the code of the same version: a clone or the GitHub zip); no real data in the repository |
| `workspace/` | the work folders (not in the repository) |

**Command line.** `python -m engine.run <file|folder|zip> --out <folder>` takes the same route as the app: a raw
dataset is decoded, a harvest file is **imported as SMS by default** with the values SMS gives its source (a
GreenStar 3 card's crop definition, SMS's values for the crop of Gen4 logs or an Operations Center export, a Case IH
card's product; `--no-sms-import` cleans the file as it is; `--product`,
`--weight-to-volume`, `--dry-moisture`, `--min-yield`, `--max-yield`, `--expand-dry-moisture` set the import's
values, and S0 then takes the import's minimum), then cleaned with the SMS 3-sigma method (the default `--method
sms3sigma`; `--sms-order`, `--sms-group`). `--aoi FILE` is the field boundary: for the SMS method the S1 clip (1 cm edge
tolerance), as in the app. A planter, sprayer or other point export (no yield column) is cleaned as an as-applied
file by `engine/clean/applied3s.py` (`--attributes A,B` chooses the attributes), never by the yield cleaning.

Grower data (monitor cards, exports, boundaries, results) never goes into this repository: `.gitignore` lets only the
code and the documents in.

## Limitations

- Planters and sprayers are read from their **point exports** (SMS, Operations Center, the display's export). The
  raw planter and sprayer records of the monitor cards (`.cn1`, JD-Data, GreenStar 3) are not decoded yet: a raw
  card is read for its harvest data only. Send a sample card to add them.
- ISOXML task data is read for its **harvest** logs (a time log with a yield value). The rules were measured
  against SMS on the task data of one combine display; a log with two working headers, a header without
  sections, a log without a mass flow, section positions that do not lie side by side, a crop code OCED does not
  know and other makers' harvest task data are read by the same rules but were not compared with SMS. Task data
  of planters and sprayers is named, not read (as the planter and sprayer records of the cards): open its point
  export.
- A damaged zip among the zips of an input (a zip inside a zip, a zip in a folder given; any format) is left out
  and the others are read: what was in it is not in the data. It is named, with the reason, in a warning of step 1,
  in the decode report, in the cleaning record and report, and in the saved work, which says it again when it is
  opened. A zip given by itself that is damaged is refused.
- The clean harvest in the monitor's raw format and in ISOXML has not yet been read back by SMS (step 4).
- An Operations Center export in metric units is flagged, not converted: export it again in imperial units.
- The as-applied cleaning has no overlap step: Optimize Swath Widths is a harvest step of SMS.
- The grower's data (validation and adjustment) apply to harvest files.
- The satellite image under the maps needs the internet; the points and strips are drawn without it.
