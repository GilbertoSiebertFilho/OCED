# OCED — Olds College Extract Data

OCED opens the files that come from the machines (combines, planters and sprayers), imports them as Ag Leader SMS
Advanced does, shows the map of every attribute, cleans the data with the 3-sigma method of SMS, and writes the clean
data (a shapefile, or the clean harvest in the monitor's own raw format) and the reports. It is a Streamlit app that
runs on the user's own computer (Windows); the files never leave it.

**Version 0.4.0** (shown in the app's title bar and sidebar). It reads Case IH / New Holland cards, John Deere
GreenStar 3 cards and Gen4 logs, ISOXML harvest task data and point exports; besides the clean shapefile it writes
the shapefile for DIFM (with the choice of the yield it carries) and the clean harvest in the monitor's own format.

*Changes in 0.4.0:* the steps are tabs across the top, as in OCVR: six steps, one card per tab, *Back* and
*Next step* at the foot of each card and *n of 6 steps done* in the title bar (*n of 5* while step 5, Plots, is not
needed: no plot boundary for the file on screen; *n of 4* for a planter or sprayer file, whose steps 4 and 5 are not
needed; the badge then says *not needed*). **1 Files** holds everything the
later steps use: the raw data, the field boundary, the plot boundary (the small area's polygon file and its rule,
given here and kept with the work) and the management zone map, with the import settings folded under each file
(a user who never opens them keeps SMS's default). **2 Raw map**: the map of the imported readings with the field
boundary, the boxes that follow the attribute chosen, the import details and *Play the harvest* of the readings in
use. **3 Cleaning**: the settings, *Clean*, the result strip, the clean map and the tables. **4 Clean map**: the clean
map with the field boundary and *Play the harvest* of the cleaning with *Edit points* and *Reprocess*. **5 Plots**:
everything of the plots: the clean map with the plot boundary and each plot's name, the small area cut (*Measure*,
after the whole-field cleaning, as before: its figures, tables, map and files, *Change in step 1*) and a replay of the
cleaning that shows the plots (a player of its own; the edits by hand are made in step 4, whose *Reprocess* measures
the plots again); without a plot boundary one line says so. **6 Final files**: the clean shapefile, the file for DIFM,
the reports and the raw formats. Only the open tab is drawn, so the page is lighter; the values typed
in a step are still there when you come back to it (the marks of *Edit points* until they are sent: the line beside
the player says so; files uploaded for the raw data wait for *Open* only while step 1 is open, a path typed is kept;
the field boundary, the zone map and a file's own boundary chosen in an uploader wait for *Use* or *Open* over a change
of step; with a path typed beside such a waiting file, *Use* and *Open* take neither and say so: *Clear* the waiting
file or empty the path), and the plot boundary given in step 1 is saved with the work before it is measured (its
section stays open once something in it is changed, and its title names the polygon file given or measured; a
shapefile uploaded as its separate files is named by its .shp).
The plot boundary is read as soon as it is given (one line: its file, polygons and acres; a file that cannot be read as polygons is said there and not kept) and drawn on the raw map of step 2 and the clean map of step 5 before *Measure*.
An emptied box of the
grower's weight (its weight, moisture, bushel weight, acres or standard moisture) now stays empty; before, the value
came back (typing 0 removed it). The grower's weight is shown and written with two decimals in every unit (four in
the box for t, as the engine writes a tonne weight; the box has its own row, the *Unit* under it, and no +/- buttons), never rounded to a whole number (4,451.50 lb, not 4,452), and *Weighed* starts at *At the standard
moisture* (dry) in a new work (a saved work keeps its own); the command line and the engine take a weight given
without its basis as dry too (wet when its grain moisture is given; the legacy `--scale-ticket-bu` keeps wet). *Measure* (step 5) now works on a file that keeps its own column names
(an Operations Center point export: VRYIELDVOL, DISTANCE, SWATHWIDTH ...): the small area reads the columns the
cleaning read and its texts name them; a file with OCED's names gives the same figures as before. Grain / ground
no longer takes two readings of one combine in the same second (a point export whose times are whole seconds) for
one reading logged twice: a reading is counted once only when its machine, its time and its logged position repeat,
and a reading the import left out in the second of a kept one is counted. The bar of the step tabs stays at the
top of the screen while the page scrolls (one row, which scrolls sideways where the main area is too narrow for the
six pills: a phone, or a laptop with the sidebar open). The maps that draw the plot
boundary (step 2, the clean map of step 5, the small area's map) write each plot's name inside it, the name the
small area table gives it (its name column, else its number; *name (2)* for a second plot of one name), sized to
fit the plot and shown as the map is zoomed in when the plots are small; the mouse on a plot's line names it too.
Every column of the small area's tables says what it is and its unit (*Yield, grain / ground (bu/ac)*, *Grain
(bu)*, *Ground (ac)* ...), with a help on how it is computed; the CSV is unchanged. The harvest replay shows every
yield with two decimals (the running bu/ac, the reading under the cursor, each combine, the zones), the real value
of the sum: its file now keeps each yield to 0.01 bu/ac (a replay saved by an earlier version still opens). A step that
cannot be used yet says in one line what is missing and which step gives it.
When mean - 3 SD of the dry yield is negative, nothing is cut below it and the low limit shown is the import minimum in force, with the reason (*5.00 bu/ac (import minimum; 3-sigma gave -22.16, so no cut below)*, or *0.00 bu/ac (... import minimum 0)* without one), in the replay's card (*3-sigma limits of this combine*), step 3's Limits and Steps tabs and the cleaning report; the filter, its record and the files do not change.
Nothing in the cleaning changes: the
same inputs and choices give the same files, byte for byte (the version written into an ISOXML set is 0.4.0). The
step numbers in the notes of the earlier versions below are those of their own layout.

*Changes in 0.3.8:* a John Deere Gen4 .jdl log is read as SMS reads it. Each flow and moisture sample goes to
the nearest position sample (several samples give their plain mean, zeros included) and the section states are
read halfway between position samples. The raw map then equals SMS's raw map reading for reading (the yields up to
the 4th decimal: SMS counts per US survey acre, OCED per international acre). Every .jdl cleaning changes a
little; every other format gives the same files, byte for byte. Step 1 tells when a file is an Ops Center
export by section (those cannot equal SMS's read of the .jdl: upload the raw .jdl), and the map's heading says
where a recomputed yield comes from (for example, computed from WetMass).
The small area (step 3): the hover of its map is short (what happened to the reading, the share of its strip
inside, the yield used, the bushels) and stays inside the map; a click (a tap) on a reading or a polygon's line shows
the whole calculation in a card under the map. The harvest replay's small area (each reading's share, the polygon's
figure) and the table *Before and after the edits by hand* show grain / ground, the figures of the table that leads,
with the cleaned map average beside them, labelled; that table also counts, before and after, the readings the
cleaning kept and those removed by hand. The cleaning files do not change.

*Changes in 0.3.7:* the field files at the start, openers that stand out, Play the harvest and Edit points after
the raw data, the small area read reading by reading and kept with the file, and the small area's yield as grain /
ground. The whole-field cleaning is not changed (the same files, byte for byte).
- **The small area's yield is grain / ground** (step 3, the default; command line `--small-area-method
  ground|cleaned|sms`). Every reading inside the polygon counts, whatever the cleaning did with it (kept, removed by a
  step, removed by hand) and also the readings the import left out below its minimum yield (read from the work's
  decoded file of that harvest file, with the import's own weight to volume and dry moisture). Each reading's strip
  is taken as logged (its width x its distance, ending at its logged point, its heading turned from true north to
  the map's grid north) and clipped by the polygon's line. Grain = dry yield x logged area x the share inside;
  ground = the area the clipped strips cover, overlaps counted once; the yield = grain / ground. *Why:* checked
  against the weigh wagon in 2026 (a canola and a wheat trial), the average of the cleaned map read the plots high
  and flattened the differences between them (it leaves out the low readings of a no-grain patch but keeps their
  ground out of the area too), while grain / ground came within the scale's own load-to-load scatter in both crops.
  Beside it the table always
  shows the **cleaned map average** (the 0.3.6 figure, under the edge rule) and **as SMS's query** (the kept readings
  whose whole strip is inside, their grain over their own area: the figure SMS gives for a polygon). A small area of
  0.3.6 opens as *cleaned map average (0.3.6)*. When the decoded file is not there (a flagged file given alone),
  grain / ground is computed from the flagged file only and the box and the record say so.
- **The ranges of the small area**: the *spread inside the polygon* (a moving-block bootstrap along each pass,
  blocks of about 30 m, 4,000 draws, a fixed seed: the 95 % bootstrap range of the polygon's figure under the
  yield's variation along the passes; the monitor's calibration error is not in it) and, when you give the combine's calibration CV (`--small-area-cv PCT`), the
  *calibration range* (+- 1.96 x CV x the yield) and a table of the differences between every pair of polygons with
  +- 1.96 x sqrt((CV y1)^2 + (CV y2)^2). The calibration range covers comparisons between polygons of the same
  combine and day; the absolute level also needs a scale level (the grower's weight). The CV is measured on the combine
  itself (monitor against the scale, load by load). *Interior* (`--small-area-interior M`) takes M metres off each end of
  every polygon along its long axis (the ends of a pass read low while the elevator fills and empties, so the
  interior reads higher than the whole pass); a warning says when more than 15 % of a polygon's ground is the first
  or last 10 m of a pass.
- **The hover of the small area's map** now shows each reading as grain / ground counts it: the grain counted
  (yield x logged area x share inside), its clipped area, its part of the ground (after the overlaps with earlier
  readings), whether SMS's query counts it (its whole strip inside) and what the cleaned map average counted. A new
  download, `<tag>_small_area_ground.zip`, holds every clipped strip (`SA_Grain` sums to the grain, `SA_GrndAc` to
  the ground).
- **Step 3's boundary**: *No boundary for this file* now offers the upload / path / *Use* of the file's own boundary,
  and removing the field boundary of step 1 clears the per-file choices made about it.
- **Copied or moved works** read and write their own cleaning folder: the paths of a cleaning record written in
  another folder are put under the work's own, so Measure and *Remove the small area* never touch the folder a work
  was copied from. A small area of 0.3.6 given by its path (not copied into the work) is found again next to the input
  when the file there holds the same polygons.
- **Field files** (step 1, always visible, optional): one field boundary and one management zone map for every
  harvest file of the work, given before or after the data is opened (files given before Open are used when it
  opens). A file uses the field boundary when at least 20 % of its readings lie inside it (+ 50 m), the CLI's
  field-of-interest rule; of a boundary file of several fields, each file takes the polygon holding most of its
  readings (changeable in step 3). Step 3's box says *From the field files*, with *Use another for this file* (its
  own boundary wins) and *No boundary for this file*; a file the boundary does not cover gets none, and the box says
  so. Polygon files carried with the data (a boundary shapefile in the zip, say) are listed as *Found in the input*
  and used only by a click. The zone map shows in both replays of every file; a file can have its own. Saved with the
  work (`field_files` in oced_work.json; uploads kept in `field_files/`).
- **Openers that hold an input** (Open other data, Extract, Decoding options, Edit the settings, Settings, More
  settings, Grower's weight, Play the harvest, Small area, Make of each combine) share one look: a navy edge (light
  blue on a dark page), a tinted head, a bold label and an icon; read-only details keep the plain look. After a
  cleaning only the method folds into *Settings*: the boundary, the grower's weight and the combine factor stay open.
- **Play the harvest · zone map · edit points after the raw data** (step 2, for data that needs no cleaning, an
  export of a map already cleaned, say): *Edit points* removes a reading by hand (click, or Shift + drag / Box) and
  puts back one removed by hand; *Apply these edits* cleans nothing. Under it, **Without cleaning**: the edits line,
  *Remove all edits*, the strip and the map of the edited data, and the downloads: the shapefile (the import in use
  without the readings removed by hand, its records byte for byte), the shapefile for DIFM of the same readings, and
  the edits file. These files are written only when asked for (*Prepare the files without cleaning*) or after an edit
  in step 2, into `without_cleaning/`: opening a work, an older one too, adds nothing to it. One edits file per harvest file for both replays (`edits/<tag>/<tag>_manual_edits.json`): a
  reading removed in step 2 is removed by every cleaning of the file (step SM, after Optimize Swath Widths, so S1, S2
  and the monitor total are those of the automatic cleaning), shows as removed by hand in step 3's replay and can be
  put back there; each replay keeps the edits of the readings it does not show. A cleaned file is not cleaned again
  by step 2: it says *clean again*. The keys use the record id and the time: edits do not carry to another export of
  the same field.
- **The small area, reading by reading** (step 3): under its table a map of every reading near the polygons, its
  strip faint, the part counted coloured by the yield used, a reading the cleaning removed in orange, one removed by
  hand (Edit points) in purple; the mouse on a reading shows its combine, time and record, the yield used (or
  *Removed by hand (Edit points)*), its strip, what the edge rule did (e.g. *33 % inside: 0.00158 of 0.00481 ac
  counted; 67 % cut off: 0.00323 ac*) and the calculation (*61.99 bu/ac x 0.00158 ac = 0.0976 bu, counted in Plot A*).
  The figures come from engine/clean/small_area.py `measure()`'s own rows (the table is their sum). New downloads:
  the point shapefile carries `SA_Share` and `SA_Bu`, and `<tag>_small_area_parts.zip` is a polygon shapefile of the
  counted parts (`SA_Share`, `SA_Area_ac`, `SA_Bu`, `SA_Rule`, `SA_Why`; `SA_Bu` sums to the table's total).
- **The small area kept with the file**: its polygon file (copied into `small_area/<tag>/`) and rule are saved with
  the work and measured again after every cleaning of the file, the reprocess after Edit points included (*measured
  again after the cleaning of hh:mm*), with a table of the figures before and after the edits by hand; the replay of
  the cleaning draws the polygons in yellow (a button zooms to them) and the card of a reading says its polygon and
  the share of its strip counted. *Remove the small area* takes it away. A small area measured by 0.3.6 is kept with
  the file when its polygon file is still in the cleaning's folder (it is copied into `small_area/<tag>/` before the
  next cleaning); otherwise the box asks for the polygon file again.

*Changes in 0.3.6:* a small area cut after the cleaning, the total in bushels, and boxes that follow the attribute
on the map. Step 3 has *Small area (cut after the cleaning)* under the clean map (command line: `--small-area FILE
[--edge-rule clip|full|point]`; engine/clean/small_area.py): a polygon file (zip / shp / geojson / gpkg / kml / kmz,
one or several polygons, each named by its name column or numbered) and an edge rule, *footprint clipped by the
polygon's line (area-weighted)* (default: every reading whose strip, its width x its distance ending at the logged
point, overlaps the polygon counts with the area of the overlap only), *whole footprint inside (as SMS's query)*, or
*the reading's point inside*. A kept reading is placed where the clean file has it (Optimize Swath Widths moves a
strip it narrows to the middle of what it kept); the figures without the cleaning use the readings as logged. The 3-sigma
limits stay those of the whole field: per polygon, the readings the cleaning kept (the clean file's yield and area)
give the readings, acres, total dry bu, area-weighted dry yield, plain mean, min, max, SD and moisture, beside the
same figures without the cleaning and the readings of the polygon each step removed; a table, a CSV, a point
shapefile of the kept readings that count, a line in the cleaning record and a section in the report. The clean,
flagged and DIFM files are not changed. (The field of interest of step 1 still cuts before the cleaning.) The boxes
above the maps of steps 1, 2 and 3 now show the total dry bushels (yield x area of the readings shown), and when
another attribute is chosen on the map (moisture, speed ...) they show that attribute's mean and area-weighted
average with its unit (the total only for a yield).

*Changes in 0.3.5:* read tasks of more than one crop as one crop. When the tasks or logs chosen for a field and season
were logged with more than one crop label (a calibration load logged under another crop, a short log labelled with
the wrong crop), step 1 lists which task has which crop label and offers *Read the selected tasks as one crop*, off
by default, with the crop to use (preselected: the crop of most of the records). On, the tasks become one harvest
file, decoded and imported as the command line's `--allow-mixed --product` does; the import record, the cleaning
record and report and the notes of the shapefile for DIFM say which tasks were read under another crop than they
were logged with, and the choice is kept with the work. When the tasks share one crop nothing changes.

*Changes in 0.3.4:* the harvest replay, management zones and readings removed or kept by hand. *Play the harvest*
plays the harvest on the satellite map, every combine on the readings' own clock, drawn in the colours of its make,
with zoom, follow and full screen, in step 2 (the readings in use) and step 3 (the cleaning, kept and removed), and as
a file to keep or send. A management zone map made elsewhere can be added to it: the yield of each zone while the
combines harvest, and at the end whether the zones agree with the yield (zone_yield.csv). In the replay of a
cleaning, *Edit points* lets the user click a kept reading to remove it, or a reading the moisture, speed or yield
filter removed to keep it (one by one, or a box), with a card of the reading's data and its combine's limits under the
cursor; *Reprocess with these edits* cleans the file again with them (an edits file in the work folder:
`engine/clean/manual_edits.py`, `--manual-edits` on the command line). The readings removed by hand leave after the
swath step and before the moisture, speed and yield filters; the readings kept by hand are never cut by those filters
and stay in their statistics; the import range, the clip and the swath step cannot be undone by hand. The result, the
report, the shapefile for DIFM's note and the record say when a cleaning includes edits by hand, with the automatic
result beside it; *Remove all edits* gives the automatic cleaning again, the same files as before any edit. Without
an edits file the clean, flagged and DIFM shapefiles are the same as with 0.3.3.

*Changes in 0.3.3:* closer to SMS, and every value typed by hand used as it is shown. The clip (S1) keeps a reading
only inside the boundary (edge tolerance 0, as SMS; it was 1 cm), in the field-of-interest pre-step and the
as-applied cleaning too, and the report, the app and the cleaning record name the tolerance used. John Deere Gen4
logs: the speed and the distance of a reading are the receiver's logged ones, as SMS reads them (the decode report
names fixes without them). A manual moisture is used with the 2 decimals it is shown with, and a 3-sigma limit never
leaves out the group's own mean (limits whose rounding would remove more than half of a group are not applied, with a
warning). The import's settings line says what was applied, with the decimals a typed value is used with; the command
line has flags for every manual import value. The grower's weight: the grain of the readings the import left out
(below its minimum) is reported and counted in the monitor total behind the level L; both areas of a bu/ac weight and
both sums of the leveled column are given; grain set aside by the field of interest is named from 1 %. New warnings,
which change no number: a file's units (bushel, moisture as a fraction, width), several combines that may be cleaned
as one group, units left out of the field of interest with readings inside it, a boundary without a .prj, the Gen4
calibration check at the monitor's test weight; the final-map line gives SMS's average and a population SD.

*Changes in 0.3.2:* the files made at the end carry the cleaning's crop and moisture. A product chosen in step 2 for
a point export (a shapefile, a `.kml` / `.kmz`, an Operations Center or SMS export) is now named in its imported
file, its clean file, its shapefile for DIFM and the ISOXML written from it (the readings that named another crop);
after any product change the Product column reads the SMS product name of the crop used (e.g. "Barley - Fall") and
the Crop column its crop key, in the app and on the command line (`--product`) alike, and the shapefile for DIFM of a
clean file without a Product column names the crop the import used. An export whose Crop column holds a crop code (a
number, as Operations Center exports write it) keeps its codes: the crop used goes into an added text column
Crop_Name (and Product, when the file has none), and the ISOXML written from it names that crop as its crop type, not
the code (imported with SMS's default, the crop OCED knows for the file, else the code). A file written in the monitor's own format (Case
IH card, GreenStar 3 card, Gen4 logs) keeps the crop, calibration and moisture the monitor logged; when the
cleaning's import differs from that (another product, weight to volume, dry moisture, Use Manual Moisture), step 4
says beside the writer, and first in its notes, with which SMS settings the file gives the clean file's yields (and,
after a flow shift or a start / stop delay, that the file keeps the grain timing the monitor logged, so no read of it
gives the clean file's yields exactly; then the 'How to read it into SMS' text says that line tells why the totals
differ). A GreenStar 3 card written from a cleaning that kept readings the card cannot give back (a reading that took
no grain record of its own reads 0 kg on the card, below the import's minimum yield) says how many in its notes. The
Case IH writer now writes a cleaning made with Use Manual Moisture, and every monitor writer says that it keeps the
logged moisture. Gen4 logs are written below the folder that holds JD-Data (not below the folders of the zips they
came in), so they fit in the default workspace. Smaller: the report gives the test weight with 2 decimals in its Source
paragraph as in its Import as SMS row (and the import's weight beside it when that is another), names the day of every
harvest session (or counts those without one) and gives its start and end as a time of day, and names the SMS
3-sigma settings of its appendix as the app does (Swath order: automatic); step 2 checks, for each file on its own,
that a raw data folder still holds the raw data of the file's units before offering 'None'; a converted `.kml` /
`.kmz` is the same file byte for byte on any day; texts no longer name settings of the command line; a long
date, a statistic's name and the steps table are no longer cut at a 1440-px window; the ISOXML line beside a card
says why it cannot be written.

*Changes in 0.3.1:* a point export (a shapefile, a `.kml` / `.kmz`, an Operations Center or SMS export) is imported
as SMS's generic import of a point file holds it: every reading is kept (min. yield volume 0, no maximum, where 0.3.0
left out the readings below 5 bu/ac and above a maximum: the product's, or 10,000 bu/ac for an Operations Center
export), with the weight to volume and dry moisture of SMS's product table (an Operations Center barley export: 14.5 %,
no longer the 15.0 % SMS gives the machine's own logs). An Operations Center export of a harvest therefore holds more
readings than the import of the same machines' own card or logs, which leaves out the readings below 5 bu/ac (SMS
imports each of them the same way). The cleaning's S0 takes the import's minimum, so the readings at 0 of a point
export reach the 3-sigma filters, as in SMS; S2 (Optimize Swath Widths) now removes a reading logged with a swath
width of 0 (a rectangle of no area), which such files bring; a cleaning saved by 0.3.0 whose S2 met such readings
says "clean it again" when its work is opened (its flagged file tells). S2 takes the readings of a point file that
has no time per reading (a yield `.kml` exported from SMS, for one) in the file's own row order, as one block, as SMS
holds such a file (one dataset, in the order of its import); 0.3.0 sorted them by the dates in the dataset names,
names without a date last. A point file with a time per reading (an Operations Center export) stays in time order,
and raw monitor data and SMS's exports of GreenStar 4 data keep the order they had. The setting swath_order "file"
now means the file's own row order for any file. The cleaning record and report say the order S2 took and why; a
cleaning saved earlier whose S2 order this changes says "clean it again" when its work is opened (its flagged file
tells). Raw monitor data keeps its import defaults.
The cleaning report's "Import as SMS" row now says, for every file, the settings, where each value came from and the
readings in the data and imported. A point export whose product names durum (e.g. "Wheat - Durum") takes SMS's Wheat -
Durum values (60 lb/bu, 13.0 %) on the command line too, as in the app. A point export whose crop OCED cannot name
keeps the file's own yields: when it carries its own dry yield (bu/ac) and dry mass, as SMS's exports do (one of John
Deere data names the variety as its product), the import note, step 2 and the command line say so plainly and that
choosing the product converts them; any other gets a warning (SMS needs a product: choose it). A work saved by 0.3.0
opens as it was saved and says how this version would import its point exports, and how to import them again.
Every harvest file now opens with SMS's default import, with no setting in step 1: the panel of import defaults for
the files opened next is gone, and that default import is kept as the file's own, beside the import in use. The import
settings of a file (step 2) apply other values to it, or to every harvest file of the work (each on its own SMS
default; the product, weight to volume and dry moisture only to files of the same product), go back to SMS's default,
or use the file with no import as SMS (an export as it is written; raw data decoded again as the monitor logged it).
Values equal to SMS's default go back to the default import. The new import is written beside the old one and takes
its place only once it is complete, so a failed import leaves the file as it was; the file's cleaning is set aside
(`superseded/`), as before. A file extracted again from the same input gets its own import settings again. A Case IH /
New Holland unit whose crop has no weight on the card is decoded with SMS's values for data without a product
(56 lb/bu, 13.0 %, said in a warning) and its product can be chosen in step 2; a file whose import as SMS fails opens
with its readings as they are, and step 2 can import it again. A work saved by 0.3.0 opens with its imports as saved:
a file imported there with its own values keeps them (SMS's default import is made again from its readings), and an
import made under an older rule is marked as such. Steps 1 and 2 are laid out again, to be read step by step: step 1
(*Raw data*) shows only the raw data with SMS's default import — a line naming the import (a badge: *SMS default*,
*Older rule*, *Import failed* ...; a decoding option that is not SMS's is named on it), the strip of cards and the
map, the details folded in small expanders — and step 2 (*Import settings*) starts with the switch *Use SMS's
default settings*: on, the data is step 1's; off, the settings of the file can be changed and applied, and step 2
then shows the changed data in its own strip of cards (with the difference to step 1) and its own map, on step 1's
colour scale. Switching back to the default asks first when the file has a cleaning (it is set aside; the switch
stays off until the answer). A field of step 2 emptied stays empty (no maximum, the weight or moisture the file
gives). A product chosen in step 2 for raw data also names the readings (their Product and Crop), as 0.3.0's decoder
did for a product chosen before extracting. *Apply to all* names, before the click, what it changes in each file,
and a file it could not import is a warning of its own. The longer
explanations moved into the "?" of the control or card they explain. Step 3 (*Cleaning*) is laid out the same way: a
line with the import it starts from (its badge, its readings and S0's minimum) and a line with the sequence; the
settings, drawn open until the file is cleaned and then folded into one line that names them (the grower's weight
folded while it is empty, the less used settings under *More settings*, one line instead of the combine-factor box
with one combine); then the strip of the result (readings kept, area, mean and average dry yield against the import
the cleaning started from, the final yield when a correction was applied, the monitor against the grower's weight
when it is only compared), the clean map right under it with its legend, its statistics and histogram at its side,
and the details in tabs (yield path, steps, limits, removed points, grower's data, combines), where the yield path and
the steps name the import the cleaning started from by its step (*SMS default (step 1)*, *your settings (step 2)*
...). Every map shows six
attributes on small pills and the others under *More*; a corrected yield is one pill away on the clean map, its
statistics compared with the clean yield, instead of a second map. The maps of steps 1 and 2 fold once the file is
cleaned, so that working in step 3 stays as quick as before (a click opens them again). Step 4 is now *Clean files
and reports*: its table names the import each cleaning started from (*SMS default*, *your settings* and what they
change, *as it is*, *as logged*, *older rule*), the cleaning report's import line says *Your settings* for a file
imported with them, and each file shows one line on its file for DIFM (the yield column, with the swath width and the
moisture to map) and the *Not yet tested in SMS* line of the monitor's format, the longer texts folded (*What each file
is*, *About the file for DIFM*, *How to read it into SMS*). The sidebar's action tree is named after the steps (the
files and their readings under *1 · Raw data*, each file's import under *2 · Import settings*), and the page's style
block is in `app/brand.py`, its colours light / dark pairs (the badges, the accent edges of the boxes, a chosen pill
or tab, the legend chips and the verdict boxes keep fixed colours that read on both). A work copied or unzipped without its files' times keeps its imports (an import is
known by its content, not by its time on disk), and SMS's default import made again is written beside the one in use
too. In step 2 an import made under an older rule says what *Apply* changes in it (steps 1 and 2 then show the new
import), *None* gives the S0 minimum step 3 holds, own settings that leave no reading open their fields, and a file
held open by another program is a warning of its own; step 1 says what to do next while nothing is extracted, and its
line of the dataset opened is short (the rest is in the *Unpacking log*). Step 3's yield path names only what moved the
yield, and a kept cleaning whose own import is gone is named, there and in step 4, by the settings it was made with;
the cleaning's status says how many readings were inside the boundary. A product chosen in step 2 for raw data puts
the cleaning record's totals and the decoder's note on that product. *Apply to all* merges the fields typed on the
file into the own settings of every other file, field by field: each keeps its other settings, the weight to volume
and dry moisture go only to files whose import in use is of the same product, a field set back to SMS's default is
taken back from each, and a file the change brings nothing (or whose import it already has) keeps its import, its own
settings and its cleaning. A product chosen goes to the files that had the file's product (the same choice of it, or
each on its data's; *not known* counts as one product), each with that product's own weight to volume, dry moisture
and limits (a limit of a file's own stays where the product does not change it on that file); a file of another
product, or one whose product was chosen on it for other data, keeps its own (a product *Apply to all* or 0.3.0's
step 1 gave counts as the choice of the file it came from), and *unknown* takes the product back. The
orange line before the click and the line after it name what changes in each file (*Max. yield volume none → 150.00*) and the files left as they are; an older rule's import is reached
only by a field that applies to it (it is then imported with today's rule plus the change), a file on *None* keeps
it, and with nothing typed only *Apply* to the file is offered. *Clean all* first brings each file's SMS default up
to date, so that no file is cleaned on an older decode and then set aside. A point export 0.3.0 opened with a
product chosen in step 1 gets its SMS default from its data's crop, as a fresh open does. A raw file a work of
0.3.0 decoded with a product chosen before extracting gets its SMS default decoded again from its raw data, as a fresh
open (*Older rule* while the raw data is not at hand: step 2 then says to put the raw data back, and *Apply* with SMS's
values imports nothing again); when the raw data is back and the file was cleaned on that older import, the cleaning
is set aside (step 1 and the work message say so); own settings that give the same import from the new decode,
reading for reading, keep the import and its cleaning (an import is compared by its content, not by the day its file
was written). The import a file had before *Apply* or *Back to SMS's default* (0.3.0's own, the readings 0.3.0
decoded with a product, with their zip and decode report) is removed once nothing references it, the report and step
1 name an older version's decode by the weight and moisture its yields carry, and *None* on an export whose import
failed keeps its cleaning. Each map names its
data (*SMS default (step 1)*, *your settings (step 2)*, *clean (step 3)*), step 1 leads to step 2 when its import leaves
no reading, values typed in step 2 stay through *None* and back, and a default import that cannot be made is said once
(the reason without a path, kept on step 1's import line) and not tried on every click.

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

## The six steps

The steps are tabs across the top of the page; each card ends with *Back* and *Next step*, and the title bar counts
the steps done for the file on screen (1 its data opened, 2 readings with a position in the import in use, 3 it is
cleaned, 4 its clean map is there, 5 its plot boundary is measured on that cleaning, 6 its clean shapefile is
written). Step 5 is not needed for a file without a plot boundary, steps 4 and 5 for a planter or sprayer file: the badge says
*not needed*, the action tree says so, and the title bar counts the others (*n of 5* or *n of 4 steps done*, its hover
says why). Only the open tab is
drawn; what you type or choose in a step stays when you open another and come back. One exception: files uploaded
for the raw data wait for *Open* only while step 1 is open (opening another step first empties that field; a path
typed is kept), so Open them first. The small files chosen in an uploader (the field boundary, the zone map, the plot
boundary, a file's own boundary in step 3) are held and wait for *Use* or *Open*. A step that cannot be used yet
says in one line what is missing and which step gives it. With several files, the file picker sits above the tabs
and every step follows the file picked.

1. **Files.** Everything the later steps use: the raw data, the field boundary, the plot boundary and the management
   zone map. Upload the files, or type a file or folder on this computer. A folder is read in place; a
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
     - **John Deere** files (GreenStar 3 cards, Gen4 `.jdl` logs): the weight to volume and the dry moisture of the
       file's crop — a GreenStar 3 card's own crop definition; for Gen4 logs the values SMS gives that crop (wheat
       60 lb/bu, 13.5 %; barley 48 lb/bu, 15.0 %), not the file's own, shown as "SMS's value for this John Deere
       crop" — min. yield volume 5 bu/ac and max. 10,000 bu/ac (SMS's values for these files; type the max when SMS
       holds another one for the product); SMS's product table below
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
     - **Case IH / New Holland** cards: SMS's product table — Wheat - Spring 60 lb/bu,
       13.5 %, 5–300 bu/ac; Wheat - Durum 60, 13.0 %, 5–300; Barley (Fall or Spring) 48, 14.5 %, 5–200; Canola 50,
       8.5 %, 10–400; Field Peas and Chick Peas 60, 13.0 %, 5–200; Lentils 60, 14.0 %, 5–200; Oats - Spring 32,
       14.0 %, 5–200; Flax 60, 10.0 %, 10–400; Rye - Annual 56, 14.0 %, 0–500. The crop names cards and exports
       carry (`DURUM`, `Durum Wheat`, `CANOLA`, `HRS wheat`, `Barley - Fall` ...) are mapped to these products; a
       crop outside the table takes its weight and moisture from the crop table and 5–300 bu/ac.
     - **Point exports** (a point shapefile, a `.kml` / `.kmz`, an **Operations Center** export, an SMS export): as
       SMS's generic import of a point file holds them, which keeps every reading of the file — min. yield volume 0
       and no maximum (only a reading with no dry yield, or a negative one, is left out; readings at 0 and far above
       the product's maximum stay, as in SMS), shown as "SMS's generic import of a point file" — and the weight to
       volume and dry moisture of SMS's product table above by the crop name (the crop table for a crop outside it),
       also for an Operations Center export (barley 48 lb/bu, 14.5 %), not the values SMS gives the machine's own
       logs. Type a minimum or a maximum to leave readings out. An Operations Center export of a harvest therefore
       holds more readings than the import of the same machines' own card or logs (which leaves out the readings
       below 5 bu/ac). A product naming durum is SMS's Wheat - Durum (60 lb/bu, 13.0 %). A crop OCED cannot name
       keeps the file's own yields: an export that carries its own dry yield and dry mass (SMS's exports; one of
       John Deere data names the variety as its product) says so in its import note and in step 1's import settings, without a
       warning; any other gets a warning, as SMS's generic import needs a product. Choosing the product in step 1
       (the import settings of the file) converts the yields.
     - Everywhere: expand dry moisture off (one-sided: grain drier than the dry moisture is not raised to it),
       manual swath and moisture off, start / stop delay and flow shift 0 s. The flow shift and the delays work
       within each run of continuous logging (a hole in the log — header up, a stop, the night — starts a new run).
     Every file opens with these values; each one stays editable per file in step 1 (empty = the source's value),
     and each value the user types wins; the import records where each value came from (the file, SMS's product
     table, SMS's values for John Deere files, SMS's generic import of a point file, or you). The dry yield of every
     file is computed again from its wet mass
     with these values (SMS ignores the dry yield a point file carries); a file without a moisture column keeps the
     dry / wet ratio of each of its readings.
   - *Field files* (always visible, optional): one field boundary and one management zone map for every harvest file
     of the work, given before or after the data is opened; step 3 clips to the boundary (S1) and both replays use
     the zone map. A file can still have its own boundary (step 3) and its own zone map (its replay).
   - *Plot boundary · optional* (per harvest file): the polygons of the plots or strips to measure inside the field
     (a polygon file: a .zip, a shapefile, a .geojson, .gpkg, .kml or .kmz), the figure the small area leads with
     (grain / ground by default), the calibration CV, the interior cut and the edge rule. They do not change the
     cleaning: step 5 measures them after the whole-field cleaning (*Measure*), and every later cleaning of the file
     measures them again. A polygon file given and not yet measured is saved with the work too (an upload is kept
     in `plot_boundary_given/<file>/` of the work folder until it is measured) and comes back when the work is
     opened. The section stays open once something in it is changed or while a polygon file is given; folded, its
     title says *· optional*, *· <file> given* or *· <file> measured*.
   - *Import settings · advanced* (folded under the file; the 0.3.x step 2). The switch *Use SMS's default
       settings* is on: the data is SMS's default import. Switched off, the
     import settings of the file open, every one editable and saying where its value came from (product, weight to
     volume, dry moisture, expand dry moisture; manual swath and moisture; min. and max. yield volume; start / stop
     delay and flow shift), and *Apply to* the file imports it again from all its readings with them (*Apply to all
     harvest files*: the fields changed, merged into each file's own settings; the weight to volume and dry moisture go
     only to files of the same product, a product chosen only to the files that had this file's product, with its own
     values for each, and a file the change brings nothing is left as it is). *Import: None* uses the file with no
     import as SMS (an export as it is written; raw data decoded again as the monitor logged it). Values equal to SMS's default go back to the
     default import. Once applied, step 2 shows the changed data beside SMS's default; step 3 cleans it, and the file's earlier cleaning is set aside
     (`superseded/`). Switched back on, the file goes back to SMS's default; when it has a cleaning, a dialog asks
     first. A work saved by 0.3.0 whose import was made under an older rule keeps it, and the import settings say that one Apply
     imports it with today's rule. Planter and sprayer files have no import settings.
2. **Raw map.** The data as SMS's default import gives it: a line naming
   the import (a badge — *SMS default*; *Older rule* for an import a work saved by 0.3.0 made under an older
   rule; *Import failed*; *As it is* for a planter or sprayer file — and its product, weight to volume, dry
   moisture and yield volume limits; a decoding option that is not SMS's is named on it), a strip of cards
   (operation, readings, area, mean and average dry yield, date, machines) and the map: one button per attribute
   colours it over the satellite image (the strips the header swept, or the points), with the legend, the
   statistics and the histogram beside it; the field boundary, once given, is drawn on it. The details are folded
   in small expanders: the **header width as logged** per combine (an initial audit: the most common width should
   be the header's), the import record (the readings in the data and left out, what was recomputed, where each
   value came from), the decoder's report, the table of every attribute, the first records and the extracted
   points. When the file has its own import settings (step 1), the changed data follows: its import line (*Your
   settings* and what changed), four cards (readings, area, mean and average dry yield) with the difference to SMS's
   default and its map on the default's colour scale (the same colour is the same value). Then *Play the harvest* of
   the readings in use (zones, *Edit points*) and *Without cleaning* (the data used as it is, with its edits by hand).
3. **Cleaning: 3-sigma.** Each file keeps its own field boundary and settings; one file or all of them at once.
   - *Harvest:* the SMS 3-sigma sequence as SMS Advanced runs it. With a boundary the readings outside it are set
     aside first (**S1 Clip To Field Boundary**, shown first in the steps), then S0 import check (no position, no
     yield, dry yield below the import's minimum: after an import as SMS it normally finds nothing), S2 Optimize Swath
     Widths (overlapping strips removed or narrowed, per-area values scaled; a reading logged with a swath width of
     0 removed; the readings in time order, or in the file's own row order for a point file without a time per
     reading), **S3 moisture, S4 speed** and S5 dry
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
     factor was applied. The Yield path tab shows how each step moved the mean and the SMS Average.
     **The grower's data** of the field (total weight with its unit — lb, kg, bu or t — or the yield per acre in
     bu/ac with the acres it is over; the basis, the grain moisture on the ticket, the bushel weight) **validate**
     the yields: the monitor's total against the grower's on the same basis, `L = grower / monitor` and a verdict
     (≤ 1 %, 1–3 %, 3–10 %, > 10 %). The two totals are compared as masses in the file's own bushel: a bushel weight
     never changes a weight given in lb, kg or t. A weight *at the standard moisture* is compared with the file's dry
     yield as imported (one-sided), and `Yld_Level` over every processed reading then sums to that weight (the clean
     file, without the readings the cleaning removed, sums less: the report gives both); a wet weight with its grain moisture is
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
     name). A reading whose logged point lies outside the boundary is clipped, even by a few millimetres, as in SMS
     (edge tolerance 0, measured on SMS harvest cleanings, and the same for as-applied files, which SMS clips with
     the same command; `sms3sigma.clip_tolerance_m`, or `clip_tolerance_m` of an as-applied cleaning, widens it).
     A point exactly on the edge is clipped, and so is a reading in a gap between two polygons of the field (a field
     drawn in parts): the field is the union of its polygons; a tolerance above 0 closes gaps up to twice its width.
   - On screen: a line with the import the cleaning starts from (SMS's default or your settings of step 1, its
     readings and S0's minimum: the import's, or *S0 minimum* in the settings for a file not imported as SMS), then
     the settings, folded into one line once the file is cleaned. The result: a strip of cards (readings kept, area,
     mean and average dry yield, the final yield of a correction, the monitor against the grower's weight), the clean
     map under it (the corrected yield one pill away) and the tabs: the yield path, the steps (what each removed),
     the limits of each 3-sigma step, the map of the removed points by step, and for a harvest with the grower's data
     the validation, with several combines the combine factor.
4. **Clean map.** The clean map with the field boundary, *Play the harvest* of the cleaning (kept and removed;
   *Edit points*: readings removed or kept by hand, then *Reprocess with these edits*, which also measures the plots
   of step 5 again; *Remove all edits* above the map; the marks live in the player until they are sent, so a change
   of step or a fold of the section loses those not yet sent, as the line beside the player says). One line says
   that the plots are in step 5 when a plot boundary is given. A planter or sprayer file has its clean map in step 3
   only.
5. **Plots.** Everything of the plots of a harvest file: the clean map with the field boundary, the plot boundary of
   step 1 and each plot's name; the small area cut after the cleaning: *Measure* counts the readings the
   whole-field cleaning kept in each polygon of the plot boundary (grain / ground, the cleaned map average and as
   SMS's query), with its tables (each column with its unit), its map (a hover and, on a click, the card of each
   reading), its files (the table as CSV, the points, the counted parts and the grain / ground strips as zipped
   shapefiles) and *Change in step 1*; then *Play the harvest · the plots*, a replay of the cleaning of its own that
   shows the plots in yellow, each reading's share inside a plot and the plot's grain / ground (no *Edit points*
   there: the edits by hand are made in step 4, whose *Reprocess* measures the plots again). Without a plot boundary
   the step says so in one line (give the polygon file in step 1, *Plot boundary*).
6. **Final files.** On screen: *What each file is* (folded), the table of the cleaned files with the
   import each cleaning started from, then per file its downloads, one line on its file for DIFM (*About the file for
   DIFM* folded under it) and the box of the monitor's format. For each file: the clean shapefile (the kept readings with every attribute of the
   file, in one zip), the flagged points (the readings with `Keep` and `Rem_By`, the step that removed it: for a
   harvest file every reading inside the boundary, the readings clipped by S1 counted in step 3, not listed; for a
   planter or sprayer file every reading, the clipped ones with `Rem_By` S1; a cleaning run again with a **manual edits
   file**, readings removed or kept by hand, `engine/clean/manual_edits.py`, `--manual-edits` on the command line, has
   `Rem_By` SM for the readings removed by hand, after the swath step and before S3, and two more columns: `Man_Edit`
   R removed by hand, K kept by hand, N asked but not applied, and `Rem_Auto` the step of the automatic cleaning), the
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

   **Shapefile for DIFM.** Next to the clean shapefile of each file, step 6 offers the zip to upload to DIFM
   (difm.farm), which reads the layout of Ag Leader SMS shapefile exports (`engine/difm.py`, also in
   `clean_shapefiles/`). A harvest's, `<file>_sms3s_clean_DIFM.zip`, holds the same clean readings at the same
   positions with exactly the fields Field, Dataset, Product, Obj__Id, Distance_f, Track_deg_, Duration_s, Elevation_,
   Time, Swth_Wdth_, Y_Offset_f, Moisture__, Yld_Mass_W, Yld_Vol_We, Yld_Mass_D, Yld_Vol_Dr, Speed_mph_ and Date, in
   the dBASE widths of the file DIFM was seen to read, with the values of the clean file: text as it is, numbers
   with 6 decimals (N 24.6: more than any monitor resolves, an SMS export itself has 4; a number the clean file holds
   with more is rounded, half to even, and a zero is written 0.000000, never -0.000000). With 15 decimals the zip of
   a large field passed 10 MB; a zip that still ends over 10 MB is a warning of step 6. Y_Offset_f is 0 when the
   source has no lateral offset; WGS 84 with the `.prj` SMS writes.
   A field the clean file does not hold (an Operations Center export has no Field, Dataset, Product, Duration_s,
   Yld_Vol_We or Yld_Mass_D) is filled only with what follows exactly from the clean file's own values and from the
   file's import as SMS, never with an invented value: mass = volume x the import's weight to volume and volume =
   mass / it, on the wet and on the dry side (when that import computed the file's yields with it); Duration_s = the
   time step of the readings (the step between consecutive readings of a combine that 90 % of them share: 1 s for a
   log of one reading per second); Field = the field the export's Operations Center metadata names, Product = the
   crop the import read from the file, Dataset = the combine of each reading. What does not follow stays empty (the
   writer's notes say why), and readings without Yld_Mass_D or Yld_Vol_Dr, the fields DIFM maps as the yield, are a
   warning of step 6.
   Time and Date are dBASE dates, the date of each reading: an SMS export's own date as it is; for a time of day its
   calendar day, by one rule for every time in UTC (John Deere logs and cards, and any time that says its zone, as
   the IsoTime of an Operations Center export): this computer's clock time at that instant, as SMS shows it (the
   cleaning's `Harv_Day` uses the solar day for a John Deere log and the day of the time as it is for an export, so
   it can differ by a day there); a time that says no zone, of any other source, is taken as it is (ISOXML task
   data: the time is the display's own clock, which SMS shows as it is, so each reading keeps its own day); else
   `Harv_Day`
   or the date in the dataset name. A zip written by an earlier version (15 decimals) is written again when step 6
   shows it. A planter or
   sprayer file's, `<file>_3s_clean_DIFM.zip`, keeps its own columns with its dates as dBASE dates (the rate's unit is
   chosen in DIFM's Define Features); it has not been tried on DIFM yet. The clean shapefile keeps all its columns.

   *Which yield DIFM gets.* When the cleaning adjusted the yield (a combine factor applied and / or the grower's
   weight used to adjust), step 6 asks which yield the harvest's file carries; with no adjustment there is no
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
   - **3-sigma only (the monitor's yield)**, `<file>_sms3s_clean_DIFM.zip`: the monitor's dry yield as cleaned; step 6
     then says that the adjusted yield is not in that file.

   Each choice has its own file name, so both can be in `clean_shapefiles/`; step 6 offers the one chosen, its
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
(a point export, e.g. an Operations Center export whose crop was not read then, or one that 0.3.0 cut at the
product's yield volume limits: open the export again for the current import as SMS, or import it again in step 1,
whose import settings then hold this version's values); a new cleaning does not change either. *What OCED reads*:
the formats, SMS's default import of each source and the SMS 3-sigma sequence in full. *Action tree*: the six steps
by their names, file by file: *1 · Files* the input, the field files and each file with its readings (a file name
shows that file in steps 1 to 6), *2 · Raw map* the import of each file (SMS default, your settings and what they
change, as it is, as logged, older rule, import failed), *3 · Cleaning* the boundary, the grower's data and the
cleaning (kept, removed %, L), *4 · Clean map* the edits by hand, *5 · Plots* the plot boundary of each harvest file
(measured, given and not measured yet, or not needed), *6 · Final files* the outputs.

## Files

| Path | What it is |
|---|---|
| `app/oced.py` | the app (the six steps) |
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
| `engine/replay.py`, `engine/replay_player.html`, `app/replay_view.py` | the harvest replay: the readings played back on the satellite map combine by combine (each machine drawn in the colours of its make), one self-contained HTML player; in the app *Play the harvest* under step 2, under the clean map of step 4 and in step 5 (the plots); `python -m engine.replay <shp or zip> --out replay.html` |
| `engine/zones.py` | management zones in the harvest replay: a zone map made elsewhere (zip, shp, geojson, kml, kmz, gpkg) read with the boundary reader, the zone of each reading and whether it is on a border, the yield of each zone and whether the zones agree with it; `zone_yield.csv` |
| `engine/run.py` | the API from the files to the clean shapefile (`open_input`, `list_units`, `decode`, `import_as_sms`, `clean`) and a command line (`python -m engine.run --help`, below) |
| `tests/` | end-to-end tests on synthetic fields (`python -m pytest -q tests`, run on the code of the same version: a clone or the GitHub zip); no real data in the repository |
| `workspace/` | the work folders (not in the repository) |

**Command line.** `python -m engine.run <file|folder|zip> --out <folder>` takes the same route as the app: a raw
dataset is decoded, a harvest file is **imported as SMS by default** with the values SMS gives its source (a
GreenStar 3 card's crop definition, SMS's values for the crop of Gen4 logs, a Case IH card's product, each with its
yield volume limits; a point export, an Operations Center export included, as SMS's generic import of a point file:
SMS's product table for the weight to volume and dry moisture, min. yield volume 0 and no maximum, every reading
kept); `--no-sms-import` cleans the file as it is; `--product`,
`--weight-to-volume`, `--dry-moisture`, `--min-yield`, `--max-yield`, `--expand-dry-moisture` set the import's
values, and S0 then takes the import's minimum), then cleaned with the SMS 3-sigma method (the default `--method
sms3sigma`; `--sms-order`, `--sms-group`). `--aoi FILE` is the field boundary: for the SMS method the S1 clip (edge
tolerance 0, as SMS), as in the app. A planter, sprayer or other point export (no yield column) is cleaned as an as-applied
file by `engine/clean/applied3s.py` (`--attributes A,B` chooses the attributes), never by the yield cleaning.

**Harvest replay.** *Play the harvest* (step 2: the readings in use; step 4: the cleaning, kept and removed; step 5: the cleaning
with the plots) plays the harvest on the map: every combine on the readings' own clock (two combines working at the same time move at the
same time; a file without a time of day plays in the file order and says so), the ground each reading covered painted
as the combine passes (the app's strips), coloured by yield, moisture, speed, combine or kept / removed, idle time
skipped, zoom to single passes, follow a combine, full screen, and the same player as a file to keep or send. Each
combine is drawn in the colours of its make (John Deere logs, the model text of a Case IH / New Holland card, ISOXML
and point exports by their machine text; the make can be set by hand) with its own number and colour. It reads the
files only. `python -m engine.replay FILE --boundary B --raw RAW --make COMBINE=MAKE --out replay.html` writes the
player of any point file; the page takes `#t=0.4&speed=60&play=1&z=18&c=yield&f=2` (time on the timeline 0-1 or `at=`
seconds, speed, playing, zoom, colour, follow) and `#gallery=1` shows the colours of every make.

**Management zones in the replay.** A management zone map made elsewhere (a prescription or zone file: polygons and one
column that names the zones, at most 12) can be added to *Play the harvest*; OCED never builds zones. The player then
switches between the yield map and the zone map (the zones under the trail, their borders over it), colours the trail by
zone, shows the yield of each zone as the combines harvest (the readings closer to a zone border than half their swath
left out by default), and ends with *Do the zones agree?*: the yield, SD, acres and bushels of each zone, the share of
the yield variation between readings the zones account for (eta squared), the zones in order of yield beside their own
order, the same inside each combine, and the cautions. The cleaning replay counts the readings the cleaning kept; the
replay of the imported readings says 'raw, not cleaned'. `python -m engine.replay FILE --zones ZONES [--zone-column NAME]
[--zone-csv zone_yield.csv] --out replay.html`; the page takes `#view=yield|zones&zb=1&card=1` (and `ptab=combines` for
the tab shown first on a medium screen, where the zones and the combines share the right panel). A zone map that misses
a quarter or more of the readings is said (a map of another field, or one that covers part of it). In the app the zone
map belongs to its work: it is kept in the work folder (`zones/<tag>/`), and a file that cannot be read is a message.

**Readings removed or kept by hand, from the replay.** In *Play the harvest* of a cleaning (step 4), *Edit points*
(in the title card of the player) pauses and shows the whole field. A click on a kept reading marks it to be removed
(a cross), a click on a reading the moisture, speed or yield filter removed marks it to be kept (a ring), a click on a
mark clears it; Shift + drag (or *Box*, then a drag, on a touch screen) marks every reading whose strip centre is in
the box: remove the kept ones, keep the removed ones, or clear their marks. Readings cut by the import range, the clip
or the swath step cannot be marked (their card says why). Whenever the playback is paused, and while editing, the card
of the reading under the cursor (on a touch screen: the one tapped) gives its time, combine, dry yield, moisture and
speed (the values the filters compared) beside its combine's limits, its width and distance, its state and its zone.
The panel counts the marks per combine, with *Undo*, *Clear marks* and *Reprocess with these edits*: the app turns the
marks into reading keys, writes `edits/<tag>/<tag>_manual_edits.json` in the work folder and cleans the file again;
while that file is there every cleaning of the file applies it, and step 4 says so beside *Remove all edits*. The
replay then shows the readings removed and kept by hand and the readings whose fate moved with the limits (a
diamond), and the totals of the edited cleaning beside the automatic ones. The player in the app talks to the page
through a two-way component (`st.components.v2`, inline JavaScript, no build step); the replay file to download shows
the edits, read-only. A replay thinned for a very large field (more than about 16 MB of readings) cannot be edited,
and says so; the replay of the imported readings has no edit mode.

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
- The clean harvest in the monitor's raw format and in ISOXML has not yet been read back by SMS (step 6).
- An Operations Center export in metric units is flagged, not converted: export it again in imperial units.
- The as-applied cleaning has no overlap step: Optimize Swath Widths is a harvest step of SMS.
- The grower's data (validation and adjustment) apply to harvest files.
- The satellite image under the maps needs the internet; the points and strips are drawn without it.
