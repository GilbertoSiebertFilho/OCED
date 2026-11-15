"""Synthetic data of the swath-order tests: two blocks of readings over the same ground (made-up numbers only)."""
import os

import numpy as np
import pandas as pd

from tests.synthetic import TEST_WEIGHT, WIDTH_FT, _lonlat

N_PASS_S, PASS_LEN_S, GAP_S = 4, 300.0, 9.0     # four east-west passes of 300 m, 9 m apart, a 30 ft header


def make_strips(folder: str, first: str, second: str, times=None, pass_num: bool = False, machine: bool = True,
                name: str = "Synthetic_strips", seed: int = 3) -> dict:
    """Two blocks of readings logged over the same ground, one reading per second at about 4.5 mph: the block of the
    dataset named `first` is first in the file, the block of `second` after it, at the same positions. Optimize Swath
    Widths keeps whichever block it takes first and removes the other as fully overlapped, so the readings S2 removes
    tell the order it took. times: None = no time per reading (a 'Time' column holding the date only, as an SMS
    export has it), else (start of the first block, start of the second) as 'YYYY-MM-DD HH:MM:SS'. pass_num: a
    Pass_Num column (1-4 in each block, as an SMS export of GreenStar 4 data has it). machine: a Machine column
    (COMBINE-1 for the first block, COMBINE-2 for the second). Every number is made up.
    Returns {"shp", "n", "df", "block"}: block = 0 for the readings of the first block, 1 for the second, file order."""
    import geopandas as gpd
    rng = np.random.default_rng(seed)
    os.makedirs(folder, exist_ok=True)
    rows = []
    step_m = 4.5 * 0.44704
    for b, ds in enumerate((first, second)):
        t = 0.0
        for p in range(N_PASS_S):
            n = int(PASS_LEN_S / step_m)
            xs = np.arange(n) * step_m
            east = p % 2 == 0
            if not east:
                xs = xs[::-1]
            for x in xs:
                rows.append({"x": x, "y": p * GAP_S, "Dataset": ds, "Track_deg_": 90.0 if east else 270.0,
                             "Pass_Num": p + 1, "block": b, "t": t})
                t += 1.0
            t += 20.0
    df = pd.DataFrame(rows)
    n = len(df)
    df["Obj__Id"] = df.groupby("Dataset").cumcount() + 1
    df["Speed_mph_"] = 4.5 + rng.normal(0, 0.1, n)
    df["Distance_f"] = df["Speed_mph_"] * 1.46667
    df["Duration_s"] = 1.0
    df["Swth_Wdth_"] = WIDTH_FT
    df["Moisture__"] = 14.0 + rng.normal(0, 0.3, n)
    df["Yld_Vol_Dr"] = 65.0 + rng.normal(0, 4.0, n)
    shrink = (100 - df["Moisture__"]) / (100 - 14.5)
    df["Yld_Vol_We"] = df["Yld_Vol_Dr"] / shrink
    df["Yld_Mass_W"] = df["Yld_Vol_We"] * TEST_WEIGHT
    df["Yld_Mass_D"] = df["Yld_Vol_Dr"] * TEST_WEIGHT
    df["Field"] = "Synthetic 1"
    df["Product"] = "Wheat"
    if times is None:
        df["Time"] = "2026-09-14"
    else:
        t0 = np.where(df["block"] == 0, pd.Timestamp(times[0]).value, pd.Timestamp(times[1]).value)
        df["Time"] = pd.to_datetime(t0 + (df["t"].to_numpy() * 1e9).astype("int64")).strftime("%Y-%m-%d %H:%M:%S")
    cols = ["Field", "Dataset", "Product", "Obj__Id", "Time", "Duration_s", "Speed_mph_", "Distance_f", "Track_deg_",
            "Swth_Wdth_", "Moisture__", "Yld_Mass_W", "Yld_Mass_D", "Yld_Vol_We", "Yld_Vol_Dr"]
    if pass_num:
        cols.append("Pass_Num")
    if machine:
        df["Machine"] = np.where(df["block"] == 0, "COMBINE-1", "COMBINE-2")
        cols.append("Machine")
    lon, lat = _lonlat(df["x"].to_numpy(), df["y"].to_numpy())
    g = gpd.GeoDataFrame(df[cols].copy(), geometry=gpd.points_from_xy(lon, lat), crs="EPSG:4326")
    shp = os.path.join(folder, name + ".shp")
    g.to_file(shp, engine="pyogrio")
    return {"shp": shp, "n": n, "df": df, "block": df["block"].to_numpy()}
