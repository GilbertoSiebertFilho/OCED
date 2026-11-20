# -*- coding: utf-8 -*-
"""Synthetic harvests for the replay tests (every number is made up; a made-up position near Olds, Alberta).

    from tests.synthetic_replay import make_two_at_once
    F = make_two_at_once(folder)                 # {"shp", "boundary", "df", "lunch", "t0"}

Two combines cut the same field AT THE SAME TIME: COMBINE-A the south half, COMBINE-B the north half, east-west passes
of `pass_len_m`, a 30 ft header, one reading a second at about 4.5 mph, a 25 s turn between passes. Both stop for
lunch at the same time (`lunch_s`), so no combine works then (an idle gap of the field); COMBINE-A also pauses alone
for `pause_s` (unloading). The file holds A's readings first, then B's (file order is not time order across
combines). time: "clock" (Time with a time of day), "date" (Time holds the date only, as an SMS point export),
"none" (no Time column); dataset_stamps: the Dataset name carries its start time 'YY/MM/DD-HH:MM:SS' (SMS / CNH);
track: the file has a heading column (Track_deg_)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

from tests.synthetic import TEST_WEIGHT, WIDTH_FT, _lonlat, _rect


def make_two_at_once(folder: str, time: str = "clock", dataset_stamps: bool = False, track: bool = True,
                     n_pass: int = 8, pass_len_m: float = 300.0, lunch_s: float = 1800.0, pause_s: float = 400.0,
                     seed: int = 3, name: str = "Synthetic_replay") -> dict:
    import geopandas as gpd
    rng = np.random.default_rng(seed)
    os.makedirs(folder, exist_ok=True)
    gap_m = WIDTH_FT * 0.3048
    t0 = pd.Timestamp("2026-09-14 13:00:00")
    rows = []
    for mi, (machine, y0) in enumerate((("COMBINE-A", 0.0), ("COMBINE-B", n_pass * gap_m + 30.0))):
        t, k = 0.0, 0
        for p in range(n_pass):
            if p == n_pass // 2:
                t += lunch_s                                   # both stop for lunch at the same time
            if machine == "COMBINE-A" and p == 2:
                t += pause_s                                   # A alone stops to unload
            spd = 4.5 + rng.normal(0, 0.08, int(pass_len_m / (4.5 * 0.44704)))
            dist = spd * 0.44704
            xs = np.cumsum(dist)
            east = p % 2 == 0
            xpos = xs if east else float(xs[-1]) - xs + dist
            for i in range(len(xs)):
                k += 1
                rows.append({"x": xpos[i], "y": y0 + p * gap_m, "Machine": machine, "t": t, "Speed_mph_": spd[i],
                             "Distance_f": dist[i] / 0.3048, "Track_deg_": 90.0 if east else 270.0,
                             "Moisture__": 13.0 + rng.normal(0, 0.3), "Yld_Vol_Dr": 60 + 10 * np.sin(xpos[i] / 60)
                             + rng.normal(0, 3), "Obj__Id": k, "pass": p})
                t += 1.0
            t += 25.0
    df = pd.DataFrame(rows)
    df["Duration_s"] = 1.0
    df["Swth_Wdth_"] = WIDTH_FT
    df["Yld_Vol_We"] = df["Yld_Vol_Dr"]
    df["Yld_Mass_D"] = df["Yld_Vol_Dr"] * TEST_WEIGHT
    df["Yld_Mass_W"] = df["Yld_Mass_D"]
    df["Field"] = "Synthetic replay"
    df["Product"] = "Wheat"
    stamp = {"COMBINE-A": "26/09/14-13:00:00", "COMBINE-B": "26/09/14-13:00:00"}
    df["Dataset"] = [(f"Task {m[-1]} {stamp[m]}" if dataset_stamps else f"Task {m[-1]}") for m in df["Machine"]]
    when = [t0 + pd.Timedelta(seconds=float(s)) for s in df["t"]]
    if time == "clock":
        df["Time"] = [w.strftime("%Y-%m-%d %H:%M:%S") for w in when]
    elif time == "date":
        df["Time"] = [w.strftime("%Y-%m-%d") for w in when]
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    cols = ["Field", "Dataset", "Product", "Obj__Id"] + (["Time"] if time != "none" else []) + [
        "Duration_s", "Speed_mph_", "Distance_f"] + (["Track_deg_"] if track else []) + [
        "Swth_Wdth_", "Moisture__", "Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr", "Machine"]
    g = gpd.GeoDataFrame(df[cols].copy(), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    shp = os.path.join(folder, name + ".shp")
    g.to_file(shp, engine="pyogrio")
    x1 = float(df["x"].max()) + 5
    field = _rect(-5.0, x1, -gap_m, float(df["y"].max()) + gap_m)
    bnd = os.path.join(folder, name + "_boundary.geojson")
    gpd.GeoDataFrame({"Name": ["Synthetic replay"]}, geometry=[field], crs="EPSG:4326").to_file(bnd, driver="GeoJSON")
    return {"shp": shp, "boundary": bnd, "df": df, "lunch_s": lunch_s, "pause_s": pause_s, "t0": t0}
