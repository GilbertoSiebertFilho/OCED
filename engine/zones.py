# -*- coding: utf-8 -*-
"""Management zones in the harvest replay: a zone map the user imports, the readings inside each zone, and whether the
zones agree with the yield. OCED never builds a zone map (no NDVI, no clustering): the map exists already or is made
in another tool, and comes in as a polygon file.

    from engine import zones
    zm = zones.prepare("zones_rx.shp")                    # the column of the classes chosen (or column="zone")
    zi, border, info = zm.assign(lon, lat, width_m)       # the management zone of each reading, and on a border or not
    S = zones.zone_stats(zi, border, area_ac, yld, use, comb, zm.labels, info["map_ac"], combine_names)
    A = zones.agreement(S, zi, border, area_ac, yld, use, comb, zm.labels, combine_names)
    zones.write_csv(S, "zone_yield.csv")

Reading the file (read_zone_file): polygons from a zipped shapefile, a .shp with its side files, GeoJSON, KML / KMZ or
GeoPackage, through the reader of the field boundary (engine.clean.aoi._read_vector). Polygons and multipolygons
only: other geometries are dropped and counted in a note; an invalid geometry is repaired (its polygonal part kept).
The coordinate system is the file's; a file without one is taken as WGS 84 when its coordinates look like degrees,
and refused (with the file's name and coordinate range) when they do not.

The class column (zone_columns, pick_column): one attribute column defines the management zones. The columns that can
(1 to MAX_CLASSES distinct non-null values) are listed and ranked, names such as zone, zona, mz, class, label,
management, rx, rate, gridcode, DN first. A column with more distinct values is refused: no binning here. The classes
are ordered (numbers ascending, text in natural order) and labelled by their value as text.

Geometry (ZoneMap.assign). The polygons are dissolved by class in the metric coordinate system of the data (the UTM
zone of the readings). Where two different classes overlap the area is measured and noted, and that ground belongs to
the first class in order. A reading's management zone is the zone its logged point falls in (a point on an edge
counts as inside); readings in no zone get the class OUTSIDE and are reported apart. A reading is 'on a border' when
its point is closer than half its own swath width (BORDER_DEFAULT_M when the width is missing) to a border between two
different classes or to the outer edge of the zone map. Vectorised: shapely's point tests and an STRtree of the
border segments, no Python loop per reading.

Statistics (zone_stats), per zone and per zone and combine, on the readings in use (the cleaning's kept readings, or
every reading of an import): readings, acres harvested (the sum of distance x width, the replay's own footprint),
dry bushels (yield x acres over the readings with a yield), yield = bushels / acres (the replay's 'bu/ac so far'),
the plain mean and population SD of the reading yields, and the share of the zone's map area that was harvested. Two
versions: 'interior' (the border readings left out, the one shown by default) and 'all'.

Agreement (agreement): eta squared, the between-zone share of the area-weighted variance of the interior reading
yields; the zones in order of yield beside their own order; the same per combine when two or more combines each have
at least MIN_COMBINE_READINGS interior readings in at least two zones. No p-value and no word of significance:
readings next to each other are not independent.
"""
from __future__ import annotations

import csv
import math
import os
import re

import numpy as np
import pandas as pd

MAX_CLASSES = 12
OUTSIDE = "outside the zones"
BORDER_DEFAULT_M = 3.0          # half the swath width of a reading without a width (m)
MIN_COMBINE_READINGS = 200      # interior readings per zone that make a combine's own order of the zones
COVERAGE_NOTE_SHARE = 0.25      # readings outside the management zones from which a note says so
SIMPLIFY_M = 0.5                # the outlines sent to the player: simplified by at most this (m), shared edges kept
AC_PER_M2 = 1 / 4046.8564224
COLUMN_HINTS = ["zone", "zona", "mz", "class", "label", "management", "rx", "rate", "gridcode", "dn"]
# ordered numeric classes: a sequential ramp of blue to purple (not the yield's red-yellow-green, not a combine colour)
RAMP_STOPS = ["#BFCBF2", "#94A6EA", "#7D80DB", "#6E54C4", "#5A2FA3", "#3F1675"]
# text classes: muted colours away from red, yellow and green
CATEGORICAL = ["#7F7FBF", "#5FA2B7", "#B57FB3", "#8C9DB5", "#C2A385", "#6C8EBF", "#A68CC7", "#5E7C99", "#B88A9E",
               "#9C8FB8", "#7FA0C9", "#C79BC2"]


class ZoneMapError(ValueError):
    """A management zone map that cannot be used (the message says why, with the file's name)."""


# ===================================================================================================== reading
def read_zone_file(path: str):
    """(GeoDataFrame of the polygons with their columns, in WGS 84; notes) of a management zone map file."""
    import geopandas as gpd
    import shapely
    from engine.clean import aoi
    path = os.path.abspath(str(path))
    name = os.path.basename(path)
    if not os.path.exists(path):
        raise ZoneMapError(f"management zone map not found: {path}")
    try:
        gdf, notes = aoi._read_vector(path)
    except Exception as e:                                  # noqa: BLE001 - any failure of the reader: said, no trace
        raise ZoneMapError(f"the management zone map {name} cannot be read: {_reader_reason(e)}") from e
    notes = list(notes)
    if "geometry" not in gdf or len(gdf) == 0:
        raise ZoneMapError(f"the management zone map {name} holds no feature")
    geom = gdf.geometry
    empty = geom.isna() | geom.is_empty
    poly = ~empty & geom.geom_type.isin(["Polygon", "MultiPolygon"])
    if (~poly).any():
        kinds = sorted({str(t) for t in geom[~poly & ~empty].geom_type})
        notes.append(f"{int((~poly).sum())} feature(s) of {name} are not polygons "
                     f"({', '.join(kinds) if kinds else 'empty'}): left out of the management zones")
    gdf = gdf[poly.to_numpy()].reset_index(drop=True)
    if len(gdf) == 0:
        raise ZoneMapError(f"the management zone map {name} holds no polygon")
    if gdf.crs is None:
        x0, y0, x1, y1 = (float(v) for v in gdf.total_bounds)
        if -180 <= x0 <= x1 <= 180 and -90 <= y0 <= y1 <= 90:
            gdf = gdf.set_crs("EPSG:4326")
            notes.append(f"{name} has no coordinate system: its coordinates look like degrees, taken as WGS 84")
        else:
            raise ZoneMapError(f"the management zone map {name} has no coordinate system and its coordinates are not "
                               f"degrees (x {x0:,.1f} to {x1:,.1f}, y {y0:,.1f} to {y1:,.1f}): save it with its "
                               "coordinate system (the .prj of a shapefile) in the tool that made it")
    bad = ~gdf.geometry.is_valid
    if bad.any():
        fixed = []
        for g in gdf.geometry[bad]:
            v = shapely.make_valid(g)
            parts = [p for p in getattr(v, "geoms", [v]) if p.geom_type in ("Polygon", "MultiPolygon")]
            fixed.append(shapely.union_all(parts) if parts else None)
        gdf.loc[bad, "geometry"] = fixed
        notes.append(f"{int(bad.sum())} invalid polygon(s) of {name} repaired")
        keep = gdf.geometry.notna() & ~gdf.geometry.is_empty
        gdf = gdf[keep.to_numpy()].reset_index(drop=True)
        if len(gdf) == 0:
            raise ZoneMapError(f"the management zone map {name} holds no usable polygon")
    if not gdf.crs.equals("EPSG:4326"):
        gdf = gdf.to_crs("EPSG:4326")
    return gdf, notes


def _reader_reason(e: Exception) -> str:
    """Why the reader failed, in the words of a zone map (the boundary reader speaks of 'the field / plan file')."""
    import zipfile
    if isinstance(e, zipfile.BadZipFile):
        return "it is not a zip archive (damaged, or a file of another kind renamed .zip)"
    msg = re.sub(r"^cannot read the field / plan file [^:]*:\s*", "", str(e)).strip()
    return msg or type(e).__name__


def _norm(c) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")


def _hint_rank(col) -> tuple:
    """(0 exact name of a hint, 1 a word of the name is a hint, 2 none; the hint's place) for the ranking."""
    n = _norm(col)
    if n in COLUMN_HINTS:
        return (0, COLUMN_HINTS.index(n))
    words = [w for w in re.split(r"[_\d]+", n) if w]
    for i, h in enumerate(COLUMN_HINTS):
        if any(w == h or (len(h) >= 4 and w.startswith(h)) for w in words):
            return (1, i)
    return (2, 0)


def _values(s: pd.Series) -> list:
    v = s[s.notna()]
    v = v[~v.astype(str).str.strip().isin(["", "nan", "None", "NaN", "<NA>"])]
    return list(pd.unique(v))


def zone_columns(gdf) -> list:
    """The columns that can define the management zones (1 to MAX_CLASSES distinct non-null values), ranked:
    [{"column", "n_classes", "values" (the first few, as text)}]."""
    out = []
    for i, c in enumerate(c for c in gdf.columns if c != "geometry"):
        vals = _values(gdf[c])
        if not 1 <= len(vals) <= MAX_CLASSES:
            continue
        out.append((_hint_rank(c), i, {"column": str(c), "n_classes": len(vals),
                                       "values": [label_of(v) for v in order_classes(vals)[:6]]}))
    out.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in out]


def _as_number(v):
    if isinstance(v, (bool, np.bool_)):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v) if math.isfinite(float(v)) else None
    try:
        f = float(str(v).strip())
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def _natural(s: str):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", str(s)) if t != ""]


def order_classes(values) -> list:
    """The classes in order: numbers ascending when every value is a number, else text in natural order."""
    vals = list(values)
    nums = [_as_number(v) for v in vals]
    if vals and all(n is not None for n in nums):
        return [v for _, v in sorted(zip(nums, vals), key=lambda t: t[0])]
    return sorted(vals, key=lambda v: _natural(str(v)))


def label_of(v) -> str:
    """A class's value as text (a whole number without its '.0')."""
    n = _as_number(v)
    if n is not None and not isinstance(v, str):
        return str(int(n)) if float(n).is_integer() else f"{n:g}"
    return str(v).strip()


def colours_of(n: int, numeric: bool) -> list:
    """n colours of the management zones: a sequential ramp (ordered numbers) or a muted categorical set (text)."""
    if not numeric:
        return [CATEGORICAL[i % len(CATEGORICAL)] for i in range(n)]
    rgb = [tuple(int(h[k:k + 2], 16) for k in (1, 3, 5)) for h in RAMP_STOPS]
    out = []
    for i in range(n):
        x = (i / (n - 1) if n > 1 else 0.5) * (len(rgb) - 1)
        k = min(int(x), len(rgb) - 2)
        f = x - k
        out.append("#" + "".join(f"{round(rgb[k][q] + (rgb[k + 1][q] - rgb[k][q]) * f):02X}" for q in range(3)))
    return out


def pick_column(gdf, column: str | None, name: str = "the zone map") -> str:
    """The class column: the one asked for (checked), else the first ranked candidate."""
    cols = [c for c in gdf.columns if c != "geometry"]
    if column:
        if column not in cols:
            raise ZoneMapError(f"{name} has no column {column!r}; its columns are {', '.join(map(str, cols)) or 'none'}")
        n = len(_values(gdf[column]))
        if n > MAX_CLASSES:
            raise ZoneMapError(f"the column {column!r} of {name} holds {n} different values: a management zone map has "
                               f"at most {MAX_CLASSES} classes. Group the values into classes in the tool that made the "
                               "map (OCED does not bin a continuous column)")
        if n == 0:
            raise ZoneMapError(f"the column {column!r} of {name} is empty")
        return column
    cand = zone_columns(gdf)
    if not cand:
        raise ZoneMapError(f"no column of {name} can define the management zones (1 to {MAX_CLASSES} different "
                           f"values); its columns are {', '.join(map(str, cols)) or 'none'}")
    return cand[0]["column"]


# ===================================================================================================== the zone map
class ZoneMap:
    """A management zone map ready for the replay: the classes in order (labels, colours) and their polygons
    dissolved by class (WGS 84). Built by prepare()."""

    def __init__(self, path, column, classes, labels, colours, numeric, geoms, notes, columns, n_features):
        self.path = path
        self.file = os.path.basename(path)
        self.column = column
        self.classes = classes          # the values, in order
        self.labels = labels            # their text
        self.colours = colours
        self.numeric = numeric
        self.geoms = geoms              # one shapely geometry per class (WGS 84), in order
        self.notes = list(notes)
        self.columns = columns          # zone_columns() of the file
        self.n_features = n_features

    @property
    def n(self) -> int:
        return len(self.labels)

    def metric(self, lon, lat):
        """(pyproj CRS of the UTM zone of the points, x, y in metres)."""
        import geopandas as gpd
        from pyproj import Transformer
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        ok = np.isfinite(lon) & np.isfinite(lat)
        if ok.any():
            crs = gpd.GeoSeries(gpd.points_from_xy(lon[ok][:: max(1, ok.sum() // 5000)],
                                                   lat[ok][:: max(1, ok.sum() // 5000)]), crs="EPSG:4326"
                                ).estimate_utm_crs()
        else:
            crs = gpd.GeoSeries(self.geoms, crs="EPSG:4326").estimate_utm_crs()
        tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        x, y = tr.transform(lon, lat)
        return crs, np.asarray(x, float), np.asarray(y, float)

    def metric_geoms(self, crs) -> tuple[list, float, list]:
        """(the class polygons in crs made exclusive: ground where classes overlap goes to the first in order;
        the overlap area in acres; the overlap notes)."""
        import geopandas as gpd
        import shapely
        g = list(gpd.GeoSeries(self.geoms, crs="EPSG:4326").to_crs(crs))
        out, taken, overlap, pairs = [], None, 0.0, []
        for i, gi in enumerate(g):
            if taken is not None and gi.intersects(taken):
                inter = gi.intersection(taken)
                a = float(inter.area)
                if a > 0.01:
                    overlap += a
                    for j in range(i):
                        aj = float(gi.intersection(g[j]).area)
                        if aj > 0.01:
                            pairs.append((self.labels[j], self.labels[i], aj * AC_PER_M2))
                gi = gi.difference(taken)
            out.append(gi)
            taken = gi if taken is None else shapely.union(taken, gi)
        notes = [f"management zones {a} and {b} overlap on {ac:,.3f} ac: that ground (and its readings) is given to "
                 f"zone {a}, the first in order" for a, b, ac in pairs]
        return out, overlap * AC_PER_M2, notes

    def assign(self, lon, lat, width_m=None) -> tuple[np.ndarray, np.ndarray, dict]:
        """(zone index of each reading, 0..n-1 in class order and n = OUTSIDE; on a border (bool); info). info:
        crs, map_ac (each zone's map area, exclusive), overlap_ac, notes, geoms (the exclusive polygons in crs)."""
        import shapely
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        m = len(lon)
        crs, x, y = self.metric(lon, lat)
        geoms, overlap_ac, notes = self.metric_geoms(crs)
        ok = np.isfinite(x) & np.isfinite(y)
        zi = np.full(m, self.n, np.int64)
        free = ok.copy()
        for k, g in enumerate(geoms):
            if g.is_empty or not free.any():
                continue
            shapely.prepare(g)
            hit = np.zeros(m, bool)
            hit[free] = shapely.intersects_xy(g, x[free], y[free])
            zi[hit] = k
            free &= ~hit
        # the borders: the edges of the exclusive zones (between two classes, or the outer edge of the map)
        segs = []
        for g in geoms:
            if g.is_empty:
                continue
            b = shapely.boundary(g)
            for line in getattr(b, "geoms", [b]):
                c = shapely.get_coordinates(line)
                if len(c) >= 2:
                    segs.append(np.stack([c[:-1], c[1:]], axis=1))
        border = np.zeros(m, bool)
        if segs and ok.any():
            w = np.full(m, np.nan) if width_m is None else np.asarray(width_m, float)
            half = np.where(np.isfinite(w) & (w > 0), w / 2.0, BORDER_DEFAULT_M)
            lines = shapely.linestrings(np.concatenate(segs))
            tree = shapely.STRtree(lines)
            iok = np.flatnonzero(ok)
            pts = shapely.points(x[iok], y[iok])
            # the segments within half a swath of each point (a tree query), then strictly closer than that
            pi, si = tree.query(pts, predicate="dwithin", distance=half[iok])
            if len(pi):
                d = shapely.distance(pts[pi], lines[si])
                near = pi[d < half[iok][pi]]
                border[iok[np.unique(near)]] = True
        map_ac = [float(g.area) * AC_PER_M2 for g in geoms]
        return zi, border, {"crs": crs, "map_ac": map_ac, "overlap_ac": overlap_ac, "notes": notes, "geoms": geoms}

    def summary(self) -> dict:
        return {"file": self.file, "column": self.column, "labels": list(self.labels), "colours": list(self.colours),
                "numeric": bool(self.numeric), "notes": list(self.notes), "n_features": int(self.n_features)}


def prepare(path: str, column: str | None = None) -> ZoneMap:
    """Read a management zone map and choose its class column (column, or the first ranked candidate): the classes
    in order and their polygons dissolved by class. Raises ZoneMapError with a clear message, whatever fails."""
    try:
        return _prepare(path, column)
    except ZoneMapError:
        raise
    except Exception as e:                                  # noqa: BLE001 - a file the steps below cannot handle
        raise ZoneMapError(f"the management zone map {os.path.basename(str(path))} cannot be used: "
                           f"{str(e).strip() or type(e).__name__}") from e


def coverage_note(zi, use, n_zones: int, name: str = "the zone map") -> str | None:
    """A note when many of the readings counted fall outside the management zones (a zone map of another field,
    or one that covers part of it): all of them, or at least COVERAGE_NOTE_SHARE. None otherwise."""
    zi = np.asarray(zi, np.int64)
    use = np.asarray(use, bool)
    n = int(use.sum())
    if n == 0:
        return None
    out = int((use & (zi >= n_zones)).sum())
    if out == n:
        return (f"none of the {n:,} readings falls inside the management zones of {name}: is it the zone map of this "
                "field? (check the file and its coordinate system)")
    if out / n >= COVERAGE_NOTE_SHARE:
        return (f"{100 * out / n:.0f} % of the readings ({out:,} of {n:,}) fall outside the management zones of "
                f"{name}: the zone map covers only part of the harvest")
    return None


def _prepare(path: str, column: str | None) -> ZoneMap:
    import shapely
    gdf, notes = read_zone_file(path)
    name = os.path.basename(str(path))
    col = pick_column(gdf, column, name)
    vals = _values(gdf[col])
    classes = order_classes(vals)
    labels = [label_of(v) for v in classes]
    if len(set(labels)) != len(labels):           # two values that read the same (1 and '1'): keep them apart
        labels = [f"{lab} ({i + 1})" if labels.count(lab) > 1 else lab for i, lab in enumerate(labels)]
    numeric = all(_as_number(v) is not None for v in classes)
    col_vals = gdf[col]
    blank = ~col_vals.isin(vals)
    if blank.any():
        notes.append(f"{int(blank.sum())} polygon(s) of {name} have no value in {col}: left out of the management zones")
    geoms = []
    for v in classes:
        parts = list(gdf.geometry[(col_vals == v).to_numpy() & ~blank.to_numpy()])
        geoms.append(shapely.union_all(parts))
    return ZoneMap(os.path.abspath(str(path)), col, classes, labels, colours_of(len(classes), numeric), numeric, geoms,
                   notes, zone_columns(gdf), len(gdf))


# ===================================================================================================== statistics
def _rec(sel, area_ac, yld) -> dict:
    a = area_ac[sel]
    y = yld[sel]
    fy = np.isfinite(y)
    acres = float(a.sum())
    bu = float((y[fy] * a[fy]).sum())
    yy = y[fy]
    return {"n": int(sel.sum()), "acres": acres, "bu": bu, "yield": (bu / acres) if acres > 0 else None,
            "n_y": int(fy.sum()), "mean": float(yy.mean()) if len(yy) else None,
            "sd": float(yy.std()) if len(yy) else None}


def zone_stats(zi, border, area_ac, yld, use, comb, labels, map_ac, combines=None) -> dict:
    """The statistics of the management zones (see the module text). zi: zone index per reading (len(labels) =
    outside); border: bool; area_ac: each reading's footprint (distance x width, acres; 0 when not known); yld: dry
    yield (NaN when none); use: the readings counted (the cleaning's kept, or all); comb: combine index per reading;
    map_ac: each zone's map area (acres); combines: their names."""
    zi = np.asarray(zi, np.int64)
    border = np.asarray(border, bool)
    area_ac = np.asarray(area_ac, float)
    yld = np.asarray(yld, float)
    use = np.asarray(use, bool)
    comb = np.asarray(comb, np.int64)
    K = len(labels)
    names = list(combines) if combines is not None else [str(i + 1) for i in range(int(comb.max()) + 1 if len(comb)
                                                                                     else 0)]
    out = {"labels": list(labels), "outside": OUTSIDE, "map_ac": [float(v) for v in map_ac]}
    for ver, sel0 in (("interior", use & ~border), ("all", use)):
        zs = []
        for k in range(K + 1):
            r = _rec(sel0 & (zi == k), area_ac, yld)
            r.update({"zone": k, "label": labels[k] if k < K else OUTSIDE,
                      "map_ac": float(map_ac[k]) if k < K else None,
                      "n_border": int((use & border & (zi == k)).sum())})
            r["share"] = (r["acres"] / r["map_ac"]) if (k < K and r["map_ac"]) else None
            zs.append(r)
        byc = []
        for ci, nm in enumerate(names):
            rows = []
            for k in range(K + 1):
                r = _rec(sel0 & (zi == k) & (comb == ci), area_ac, yld)
                r.update({"zone": k, "label": labels[k] if k < K else OUTSIDE})
                rows.append(r)
            byc.append({"num": ci + 1, "name": str(nm), "zones": rows})
        field = _rec(sel0 & (zi < K), area_ac, yld)
        out[ver] = {"zones": zs, "by_combine": byc, "in_zones": field}
    # the sums of each combine, zone and border flag (the player's running numbers end exactly on these)
    cells = []
    fy = np.isfinite(yld)
    y0 = np.where(fy, yld, 0.0)
    for ci in range(len(names)):
        for k in range(K + 1):
            for b in (0, 1):
                s = use & (comb == ci) & (zi == k) & (border == bool(b))
                if not s.any():
                    continue
                a = area_ac[s]
                cells.append([ci, k, b, int(s.sum()), float(a.sum()), float((y0[s] * a).sum()),
                              int((s & fy).sum()), float(y0[s].sum()), float((y0[s] ** 2).sum())])
    out["cells"] = cells
    return out


def agreement(S: dict, zi, border, area_ac, yld, use, comb, labels, combines=None) -> dict:
    """Do the management zones agree with the yield? eta squared of the interior readings (area-weighted), the
    zones in order of yield beside their own order, and each combine's own order (see the module text)."""
    zi = np.asarray(zi, np.int64)
    K = len(labels)
    a = np.asarray(area_ac, float)
    y = np.asarray(yld, float)
    sel = np.asarray(use, bool) & ~np.asarray(border, bool) & (zi < K) & np.isfinite(y) & (a > 0)
    eta2 = None
    if sel.sum() >= 2:
        w, yy, zz = a[sel], y[sel], zi[sel]
        ybar = float((w * yy).sum() / w.sum())
        ss_t = float((w * (yy - ybar) ** 2).sum())
        sw = np.bincount(zz, weights=w, minlength=K)
        swy = np.bincount(zz, weights=w * yy, minlength=K)
        m = sw > 0
        yz = np.where(m, swy / np.where(m, sw, 1), 0.0)
        ss_b = float((sw[m] * (yz[m] - ybar) ** 2).sum())
        eta2 = (ss_b / ss_t) if ss_t > 0 else None
    zs = S["interior"]["zones"][:K]
    have = [r for r in zs if r["yield"] is not None and r["n"] > 0]
    by_yield = [r["label"] for r in sorted(have, key=lambda r: r["yield"])]
    own = [r["label"] for r in have]
    rho = None
    if len(have) >= 3:
        rank_y = pd.Series([r["yield"] for r in have]).rank().to_numpy()
        rank_o = np.arange(1, len(have) + 1, dtype=float)
        rho = float(np.corrcoef(rank_o, rank_y)[0, 1]) if np.std(rank_y) > 0 else None
    # each combine's own order of the zones it harvested well enough
    comb = np.asarray(comb, np.int64)
    names = list(combines) if combines is not None else []
    field_rank = {lab: i for i, lab in enumerate(by_yield)}
    per = []
    for C in S["interior"]["by_combine"]:
        rows = [r for r in C["zones"][:K] if r["n"] >= MIN_COMBINE_READINGS and r["yield"] is not None]
        if len(rows) >= 2:
            order = [r["label"] for r in sorted(rows, key=lambda r: r["yield"])]
            field_order = sorted(order, key=lambda lab: field_rank.get(lab, 1e9))
            # how close the combine's order is to the field's, over the zones it has: a rank correlation (3 or
            # more zones), and whether its lowest and its highest zone are the field's lowest and highest of them
            rho_f = None
            if len(rows) >= 3:
                ry = pd.Series([r["yield"] for r in rows]).rank().to_numpy()
                rf = pd.Series([field_rank.get(r["label"], 1e9) for r in rows]).rank().to_numpy()
                rho_f = float(np.corrcoef(ry, rf)[0, 1]) if np.std(ry) > 0 and np.std(rf) > 0 else None
            per.append({"num": C["num"], "name": C["name"], "order_by_yield": order,
                        "same_as_field": order == field_order, "field_order": field_order, "rho_field": rho_f,
                        "same_lowest": order[0] == field_order[0], "same_highest": order[-1] == field_order[-1],
                        "zones": [{"label": r["label"], "yield": r["yield"], "n": r["n"]} for r in rows]})
    per_combine = per if len(per) >= 2 else []
    return {"eta2": eta2, "n": int(sel.sum()), "order_own": own, "order_by_yield": by_yield, "rank_rho": rho,
            "ordered_classes": True, "per_combine": per_combine, "min_combine_readings": MIN_COMBINE_READINGS,
            "n_combines": len(names) if names else len(S["interior"]["by_combine"])}


CSV_FIELDS = ["version", "combine", "zone", "label", "readings", "border_readings_left_out", "acres", "bushels",
              "yield_bu_ac", "mean_bu_ac", "sd_bu_ac", "readings_with_yield", "zone_map_acres", "share_harvested"]


def csv_rows(S: dict, raw: bool = False) -> list:
    """The rows of zone_yield.csv: per zone, and per zone and combine, both versions (interior first)."""
    rows = []
    tag = " (raw, not cleaned)" if raw else ""
    for ver in ("interior", "all"):
        V = S[ver]
        for r in V["zones"]:
            rows.append(_csv_row(ver + tag, "all combines", r))
        for C in V["by_combine"]:
            for r in C["zones"]:
                if r["n"]:
                    rows.append(_csv_row(ver + tag, f"{C['num']} {C['name']}", r))
    return rows


def _csv_row(ver, comb, r) -> dict:
    def f(v, d):
        return "" if v is None else f"{v:.{d}f}"
    return {"version": ver, "combine": comb, "zone": r["zone"] + 1 if r["label"] != OUTSIDE else "",
            "label": r["label"], "readings": r["n"], "border_readings_left_out": r.get("n_border", "")
            if ver.startswith("interior") else "", "acres": f(r["acres"], 4), "bushels": f(r["bu"], 2),
            "yield_bu_ac": f(r["yield"], 3), "mean_bu_ac": f(r["mean"], 3), "sd_bu_ac": f(r["sd"], 3),
            "readings_with_yield": r["n_y"], "zone_map_acres": f(r.get("map_ac"), 4),
            "share_harvested": f(r.get("share"), 4)}


def csv_text(S: dict, raw: bool = False) -> str:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS, lineterminator="\n")
    w.writeheader()
    for r in csv_rows(S, raw):
        w.writerow(r)
    return buf.getvalue()


def write_csv(S: dict, path: str, raw: bool = False) -> str:
    """zone_yield.csv: per zone, and per zone and combine (both versions: interior = border readings left out)."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(csv_text(S, raw))
    return path
