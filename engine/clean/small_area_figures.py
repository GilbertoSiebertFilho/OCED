# -*- coding: utf-8 -*-
"""The figures of the small area for the cleaning report (0.4.0), written by small_area.run next to its CSV and zips
and shown in the report's small area section (small_area.report_section):

    <tag>_small_area_fig_map.png     the clean map (the kept readings as the strips they swept, coloured by their dry
                                     yield) with the plot outlines and names
    <tag>_small_area_fig_inside.png  the readings inside the plots: the part of each strip inside its plot, as grain /
                                     ground counts it (the app's small area map), coloured by the dry yield
    <tag>_small_area_fig_bars_<k>.png the yield of every plot (grain / ground, bu/ac) with the spread inside it as an
                                     error bar, in the table's order, BARS_PER_ROW plots a row and BAR_ROWS rows a
                                     figure (more plots: more figures)

The maps use the report's yield colour scale (engine/clean/yield_clean.figure_final: RdYlGn from the 2nd to the 98th
percentile, centred on the mean of the clean map), the plots' outlines and the bars the Olds College navy, the error
bars its light blue. A name that would overlap another one already drawn, or not fit its plot at the map's scale, is
left out of a map (with many plots the table and the bars name every plot). Nothing here changes what the small area
measures: the figures are drawn from measure_all's result after the CSV and the zips are written.
"""
from __future__ import annotations

import glob
import math
import os

import numpy as np

FIG_PREFIX = "_small_area_fig_"
BARS_PER_ROW = 20                    # plots in one row of the bar chart
BAR_ROWS = 3                         # rows in one figure of the bar chart; more plots continue in another figure
NAME_FONT = 8.0                      # pt, the plot names on the maps (NAME_FONT_MANY with more than NAME_MANY plots)
NAME_FONT_MANY, NAME_MANY = 6.5, 12
NAME_FIT = 1.15                      # a name's box at most this many times its plot's box on the map
NAME_MAX_CHARS = 28                  # a longer name is cut with an ellipsis under its bar (the table has it whole)
CHAR_IN = 0.06                       # in, the width of one character of the 7 pt names under the bars (an estimate)
REMOVED_EDGE = {"removed": "#F5A623", "hand": "#AB47BC", "left_out": "#009CDE"}   # as the app's map


def figure_paths(out_dir: str, tag: str) -> list:
    """The figure files of the small area of tag in out_dir (to remove before new ones are written)."""
    return sorted(glob.glob(os.path.join(glob.escape(out_dir), glob.escape(tag) + FIG_PREFIX + "*.png")))


def remove_figures(out_dir: str, tag: str):
    for p in figure_paths(out_dir, tag):
        try:
            os.remove(p)
        except OSError:
            pass


def _norm(v):
    """The report's yield scale (yield_clean.figure_final): 2nd to 98th percentile, centred on the mean."""
    from matplotlib.colors import TwoSlopeNorm
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return TwoSlopeNorm(vcenter=0.5, vmin=0.0, vmax=1.0), None
    mean = float(v.mean())
    lo, hi = (float(t) for t in np.percentile(v, [2, 98]))
    span = max(abs(mean), 1e-9) * 1e-3
    lo, hi = min(lo, mean - span), max(hi, mean + span)
    return TwoSlopeNorm(vcenter=mean, vmin=lo, vmax=hi), mean


def _parts(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [q for x in getattr(g, "geoms", []) for q in _parts(x)]


def _rings_xy(g, x0, y0):
    """The outer rings of a polygon geometry as (x, y) arrays moved by (-x0, -y0)."""
    out = []
    for q in _parts(g):
        c = np.asarray(q.exterior.coords, float)
        out.append((c[:, 0] - x0, c[:, 1] - y0))
    return out


def _name_spot(g, x0, y0):
    """(x, y, angle) of a plot's name: the point farthest inside its largest part, along its long side, never upside
    down (as the app's plot names)."""
    from shapely.ops import polylabel
    pm = [q for q in _parts(g) if q.area > 0]
    if not pm:
        return None
    big = max(pm, key=lambda q: q.area)
    rect = list(big.minimum_rotated_rectangle.exterior.coords)
    ang = 0.0
    if len(rect) >= 4:
        e1 = (rect[1][0] - rect[0][0], rect[1][1] - rect[0][1])
        e2 = (rect[2][0] - rect[1][0], rect[2][1] - rect[1][1])
        l1, l2 = math.hypot(*e1), math.hypot(*e2)
        if min(l1, l2) > 0 and max(l1, l2) >= 1.15 * min(l1, l2):
            e = e1 if l1 >= l2 else e2
            ang = (math.degrees(math.atan2(e[1], e[0])) + 90.0) % 180.0 - 90.0
    try:
        c = polylabel(big, tolerance=max(math.sqrt(big.area) / 100.0, 0.01))
    except Exception:                                    # noqa: BLE001 - an odd ring: its representative point
        c = big.representative_point()
    return float(c.x) - x0, float(c.y) - y0, float(ang)


def _draw_plots(ax, fig, names, geoms, x0, y0) -> int:
    """The plot outlines (navy over a thin white line) and their names (navy on a white halo); a name whose box would
    overlap a name already drawn, run out of the map or be larger than its plot (NAME_FIT) is left out. Returns the
    names drawn."""
    from matplotlib import patheffects as pe
    from engine.clean.yield_clean import NAVY
    for g in geoms:
        for rx, ry in _rings_xy(g, x0, y0):
            ax.plot(rx, ry, color="white", lw=2.4, alpha=0.9, zorder=6, solid_joinstyle="round")
            ax.plot(rx, ry, color=NAVY, lw=1.1, zorder=7, solid_joinstyle="round")
    fig.canvas.draw()                                    # the axes at their final size: the names' boxes
    rend = fig.canvas.get_renderer()
    abox = ax.get_window_extent(rend)
    fs = NAME_FONT if len(names) <= NAME_MANY else NAME_FONT_MANY
    placed, shown = [], 0
    for name, g in zip(names, geoms):
        spot = _name_spot(g, x0, y0)
        if spot is None:
            continue
        t = ax.text(spot[0], spot[1], str(name), rotation=spot[2], rotation_mode="anchor", ha="center",
                    va="center", fontsize=fs, fontweight="bold", color=NAVY, zorder=8, clip_on=True,
                    path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])
        bb = t.get_window_extent(rend)
        inside = (bb.x0 >= abox.x0 and bb.x1 <= abox.x1 and bb.y0 >= abox.y0 and bb.y1 <= abox.y1)
        # the name over its own plot: its box no wider and no taller than the plot's on the map (a name larger than
        # its plot would cover the plots around it and could be read as theirs)
        b = g.bounds
        (px0, py0), (px1, py1) = ax.transData.transform([(b[0] - x0, b[1] - y0), (b[2] - x0, b[3] - y0)])
        fits = bb.width <= NAME_FIT * abs(px1 - px0) and bb.height <= NAME_FIT * abs(py1 - py0)
        if not inside or not fits or any(bb.overlaps(o) for o in placed):
            t.remove()
            continue
        placed.append(bb.expanded(1.08, 1.15))
        shown += 1
    return shown


def _map_fig(ex, ey, w_in=7.6, max_h=6.2):
    import matplotlib.pyplot as plt
    xr = float(np.nanmax(ex) - np.nanmin(ex)) + 20.0
    yr = float(np.nanmax(ey) - np.nanmin(ey)) + 20.0
    h = float(np.clip(0.86 * w_in * (yr / xr if xr > 0 else 1.0), 2.6, max_h))
    fig = plt.figure(figsize=(w_in, h + 0.9))
    ax = fig.add_axes([0.08, 0.16, 0.8, 0.8])
    cax = fig.add_axes([0.9, 0.16, 0.022, 0.8])
    return fig, ax, cax


def _finish_map(ax, cax, mp, ex, ey, pad):
    from engine.clean import yield_clean as yc
    yc._extent(ax, ex, ey, pad=pad)
    ax.set_aspect("equal")
    ax.grid(False)
    ax.set_xlabel("Easting from field corner (m)")
    ax.set_ylabel("Northing from field corner (m)")
    ax.apply_aspect()
    p, c = ax.get_position(), cax.get_position()
    cax.set_position([p.x1 + 0.015, p.y0, c.width, p.height])
    cb = ax.figure.colorbar(mp, cax=cax)
    cb.set_label("Dry yield (bu/ac)")
    cb.ax.yaxis.set_major_formatter(_fmt2())


def _fmt2():
    from matplotlib.ticker import FuncFormatter
    return FuncFormatter(lambda v, _p: f"{v:,.2f}")


def write_figures(fl, M: dict, out_dir: str, tag: str, cols: dict | None = None) -> tuple:
    """The three figures of the small area (the module's docstring) from the flagged file fl and measure_all's M.
    Returns ({name: path}, info) with info: n_plots, names_map / names_inside (the names drawn on each map), n_kept
    (the readings of the clean map), n_parts (the parts inside the plots), n_removed / n_hand / n_left_out (parts of
    readings removed by the cleaning, by hand, left out by the import), mean / lo / hi of the colour scale (bu/ac),
    bars (the bar chart's figures), per_row, n_no_figure (plots without a grain / ground figure)."""
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shapely
    from matplotlib.collections import PolyCollection
    from engine.clean import small_area as sa
    from engine.clean import yield_clean as yc

    remove_figures(out_dir, tag)
    yc._style(plt)
    cmap = matplotlib.colormaps[yc.YIELD_CMAP]
    crs = M["crs"]
    P = sa.prepare(fl if fl.crs is not None else fl.set_crs(4326), cols)
    K = P["kept"]
    pm = gpd.GeoSeries(shapely.points(K["x"], K["y"]), crs=K["crs"]).to_crs(crs)
    kx, ky = pm.x.to_numpy(float), pm.y.to_numpy(float)
    keep = P["keep"] & np.isfinite(kx) & np.isfinite(ky)
    kx, ky = kx[keep], ky[keep]
    kv = np.asarray(K["yield"], float)[keep]
    q = yc.swath_quads(kx, ky, np.asarray(P["heading"], float)[keep], np.asarray(K["len_ft"], float)[keep] * sa.FT_M,
                       np.asarray(K["wid_ft"], float)[keep] * sa.FT_M)
    names = [str(p["name"]) for p in M["polygons"]]
    geoms = list(M["geoms"])
    gb = [g.bounds for g in geoms if g is not None and not g.is_empty]
    if not len(kx) and not gb:
        return {}, {}
    x0 = float(np.nanmin(np.r_[kx, [b[0] for b in gb]]))
    y0 = float(np.nanmin(np.r_[ky, [b[1] for b in gb]]))
    norm, mean = _norm(kv)
    files, info = {}, {"n_plots": len(names), "n_kept": int(len(kv)), "mean": mean,
                       "lo": float(norm.vmin), "hi": float(norm.vmax)}
    base = os.path.join(out_dir, tag + FIG_PREFIX)

    # ---- 1. the clean map with the plots
    ex = np.r_[kx - x0, [b[0] - x0 for b in gb], [b[2] - x0 for b in gb]]
    ey = np.r_[ky - y0, [b[1] - y0 for b in gb], [b[3] - y0 for b in gb]]
    fig, ax, cax = _map_fig(ex, ey)
    mp = yc._strips(ax, q - np.array([x0, y0]), kx - x0, ky - y0, kv, cmap, norm=norm)
    if mp is None:
        mp = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    _finish_map(ax, cax, mp, ex, ey, pad=12.0)
    ax.set_title(f"The clean map ({len(kv):,} readings) and the {len(names):,} plots", loc="left")
    info["names_map"] = _draw_plots(ax, fig, names, geoms, x0, y0)
    files["map"] = base + "map.png"
    fig.savefig(files["map"], dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---- 2. the readings inside the plots (grain / ground's parts)
    polys, vals, edges = [], [], []
    cnt = {"removed": 0, "hand": 0, "left_out": 0}
    for name in names:
        D = (M.get("ground_rows") or {}).get(name)
        if not D:
            continue
        for j in range(len(D["idx"])):
            part = D["part"][j]
            if not D["touch"][j] or part is None:
                continue
            stt = str(D["status"][j])
            for qq in _parts(part):
                c = np.asarray(qq.exterior.coords, float) - np.array([x0, y0])
                polys.append(c)
                vals.append(float(D["yield"][j]))
                edges.append(REMOVED_EDGE.get(stt, "none"))
            if stt in cnt:
                cnt[stt] += 1
    info.update(n_parts=len(polys), n_removed=cnt["removed"], n_hand=cnt["hand"], n_left_out=cnt["left_out"])
    gx = np.r_[[b[0] - x0 for b in gb], [b[2] - x0 for b in gb]]
    gy = np.r_[[b[1] - y0 for b in gb], [b[3] - y0 for b in gb]]
    if len(gx):
        fig, ax, cax = _map_fig(gx, gy)
        mp = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
        if polys:
            v = np.asarray(vals, float)
            ok = np.isfinite(v)
            pc = PolyCollection([p for p, o in zip(polys, ok) if o], linewidths=0, rasterized=True, zorder=2)
            pc.set_array(v[ok])
            pc.set_cmap(cmap)
            pc.set_norm(norm)
            ax.add_collection(pc, autolim=False)
            mp = pc
            ed = [p for p, e in zip(polys, edges) if e != "none"]
            if ed:
                ax.add_collection(PolyCollection(ed, facecolors="none", linewidths=0.7, zorder=3,
                                                 edgecolors=[e for e in edges if e != "none"]), autolim=False)
        span = max(float(np.nanmax(gx) - np.nanmin(gx)), float(np.nanmax(gy) - np.nanmin(gy)), 1.0)
        _finish_map(ax, cax, mp, gx, gy, pad=max(2.0, 0.03 * span))
        ax.set_title("The readings inside the plots: each strip's part inside its plot", loc="left")
        info["names_inside"] = _draw_plots(ax, fig, names, geoms, x0, y0)
        files["inside"] = base + "inside.png"
        fig.savefig(files["inside"], dpi=150, bbox_inches="tight")
        plt.close(fig)

    # ---- 3. the yield of every plot with the spread inside it
    Y, LO, HI = [], [], []
    for p in M["polygons"]:
        G = p.get("ground") or {}
        sp = G.get("spread") or {}
        y = G.get("dry_yield_bu_ac")
        Y.append(float(y) if y is not None else np.nan)
        LO.append(float(sp["lo"]) if sp.get("lo") is not None else np.nan)
        HI.append(float(sp["hi"]) if sp.get("hi") is not None else np.nan)
    Y, LO, HI = (np.asarray(a, float) for a in (Y, LO, HI))
    info["n_no_figure"] = int((~np.isfinite(Y)).sum())
    top = float(np.nanmax(np.r_[Y, HI, [1.0]]))
    ymax = top * 1.22
    rows = [list(range(i, min(i + BARS_PER_ROW, len(names)))) for i in range(0, len(names), BARS_PER_ROW)]
    figs = [rows[i:i + BAR_ROWS] for i in range(0, len(rows), BAR_ROWS)]
    ticks = [n if len(n) <= NAME_MAX_CHARS else n[:NAME_MAX_CHARS - 1] + "…" for n in names]
    long_names = max((len(n) for n in ticks), default=1)
    for k, frows in enumerate(figs, start=1):
        # the names under the bars: across when the longest fits its slot, else at 45 degrees, else upright
        slot = 6.4 / (BARS_PER_ROW if len(rows) > 1 else max(len(frows[0]), 1))
        need = long_names * CHAR_IN
        rot = 0 if need <= 0.9 * slot else 45 if need * 0.7 <= 1.0 else 90
        lab_h = 0.3 if rot == 0 else (0.7 if rot == 45 else 1.0) * need + 0.15
        row_h = 2.0 + lab_h
        fig, axs = plt.subplots(len(frows), 1, figsize=(7.6, row_h * len(frows) + 0.2), squeeze=False)
        for ax, idx in zip(axs[:, 0], frows):
            x = np.arange(BARS_PER_ROW if len(rows) > 1 else len(idx), dtype=float)[:len(idx)]
            yy, lo, hi = Y[idx], LO[idx], HI[idx]
            ax.bar(x, np.nan_to_num(yy), width=0.68, color=yc.NAVY, zorder=3)
            have = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(yy)
            if have.any():
                # the spread from its low to its high end, capped (the bootstrap's range need not hold the figure:
                # drawn as it is, not as +- around the bar)
                ax.vlines(x[have], lo[have], hi[have], colors=yc.LIGHT_BLUE, linewidths=1.6, zorder=4)
                for e in (lo, hi):
                    ax.hlines(e[have], x[have] - 0.16, x[have] + 0.16, colors=yc.LIGHT_BLUE, linewidths=1.4,
                              zorder=4)
            vert = len(idx) > 8
            for xi, yi, hi_i in zip(x, yy, hi):
                if not np.isfinite(yi):
                    ax.text(xi, top * 0.04, "no reading", rotation=90, ha="center", va="bottom", fontsize=6.5,
                            color=yc.INK2, zorder=5)
                    continue
                yt = (hi_i if np.isfinite(hi_i) else yi) + top * 0.02
                ax.text(xi, yt, f"{yi:,.2f}", rotation=90 if vert else 0, ha="center", va="bottom",
                        fontsize=6.5 if vert else 7.5, color=yc.INK, zorder=5)
            ax.set_xticks(x)
            ax.set_xticklabels([ticks[i] for i in idx], rotation=rot, ha="right" if rot == 45 else "center",
                               rotation_mode="anchor" if rot == 45 else "default", fontsize=7)
            ax.set_xlim(-0.6, (BARS_PER_ROW if len(rows) > 1 else len(idx)) - 0.4)
            ax.set_ylim(0, ymax)
            ax.set_ylabel("bu/ac")
            ax.yaxis.set_major_formatter(_fmt2())
            ax.grid(axis="x", visible=False)
            ax.tick_params(axis="y", labelsize=7.5)
        first = frows[0][0] + 1
        last = frows[-1][-1] + 1
        axs[0, 0].set_title(f"Yield of the plots, grain / ground (bu/ac): plots {first} to {last} of {len(names)}"
                            if len(figs) > 1 or len(rows) > 1 else "Yield of the plots, grain / ground (bu/ac)",
                            loc="left")
        fig.tight_layout(h_pad=1.0)
        files[f"bars_{k}"] = base + f"bars_{k}.png"
        fig.savefig(files[f"bars_{k}"], dpi=150, bbox_inches="tight")
        plt.close(fig)
    info["bars"] = len(figs)
    info["per_row"] = BARS_PER_ROW
    return files, info
