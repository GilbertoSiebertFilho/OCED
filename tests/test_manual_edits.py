# -*- coding: utf-8 -*-
"""Readings removed or kept by hand, then the SMS 3-sigma cleaning run again (engine/clean/manual_edits.py), on
synthetic data only (tests/synthetic.py): the edits file, the key of a reading, the step SM after the swath step, the
readings kept by hand inside the statistics of S3-S5, the keys that cannot be applied, the record with the automatic
result beside the edited one, the flagged and clean files, the report, the command line, and the cleaning without
edits byte for byte.

    python -m pytest -q tests/test_manual_edits.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
import pyogrio
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import run as er  # noqa: E402
from engine.clean import manual_edits as me  # noqa: E402
from engine.clean import sms3sigma as sms  # noqa: E402
from engine.clean import yield_clean as yc  # noqa: E402
from tests.synthetic import BOUNDARY_X_M, N_PASS, PASS_GAP_M, _lonlat, _rect, make_field  # noqa: E402

N_SMALL = 2000                   # the first passes of the synthetic field: fast enough for many cleanings


def _settings(F, **kw):
    S = {"method": "sms3sigma", "machines": {"harmonise": False}, "tag": "syn",
         "aoi": {"file": F["boundary"], "buffer_m": 0.01, "clip_output": True}}
    S.update(kw)
    return S


def _md5(path):
    with open(path, "rb") as f:
        b = bytearray(f.read())
    if path.lower().endswith(".dbf"):
        b[1:4] = b"\0\0\0"                                  # the date of the last update (UTC day of the run)
    return hashlib.md5(bytes(b)).hexdigest()


def _members(R):
    out = {}
    for kind, shp in (("clean", R["files"]["difm_ready_shp"]), ("flagged", R["files"]["flagged_shp"])):
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            p = os.path.splitext(shp)[0] + ext
            if os.path.exists(p):
                out[kind + ext] = _md5(p)
    return out


def _flagged(R):
    F = pyogrio.read_dataframe(R["files"]["flagged_shp"], read_geometry=False)
    F["Rem_By"] = F["Rem_By"].fillna("").astype(str)
    return F


@pytest.fixture(scope="module")
def field(tmp_path_factory):
    """The synthetic field (tests/synthetic.py) cut to its first N_SMALL readings (eight passes), same boundary."""
    import geopandas as gpd
    d = str(tmp_path_factory.mktemp("field"))
    F = make_field(d)
    g = gpd.read_file(F["shp"]).iloc[:N_SMALL].copy()
    shp = os.path.join(d, "Synthetic_small.shp")
    g.to_file(shp, engine="pyogrio")
    return dict(F, shp=shp, df=F["df"].iloc[:N_SMALL].copy(), n=N_SMALL)


@pytest.fixture(scope="module")
def auto(field, tmp_path_factory):
    """The automatic cleaning: its result, its flagged table and the key of every reading of the flagged file."""
    R = yc.run(field["shp"], str(tmp_path_factory.mktemp("auto")), _settings(field), log=lambda m: None)
    F = _flagged(R)
    keys, info = me.flagged_keys(R["files"]["flagged_shp"])
    F["key"] = keys
    return {"R": R, "F": F, "info": info}


def _pick(F, rem_by, n, start=0):
    """n keys of readings removed by `rem_by` ('' = kept; 'S5' = any yield pass)."""
    rb = F["Rem_By"]
    m = rb.str.startswith("S5") if rem_by == "S5" else (rb == rem_by)
    return F.loc[m, "key"].tolist()[start:start + n]


@pytest.fixture(scope="module")
def edits(auto, tmp_path_factory):
    F = auto["F"]
    d = tmp_path_factory.mktemp("edits")
    remove = _pick(F, "", 40, start=100)
    keep = _pick(F, "S5", 6) + _pick(F, "S3", 4) + _pick(F, "S4", 4)
    stale = [f"NO-SUCH|ds|{k}|t|" for k in range(12)]
    s0 = _pick(F, "S0", 3)
    path = os.path.join(str(d), "edits.json")
    E = me.write_edits(path, remove=remove + s0[:1], keep=keep + stale + s0[1:], note="synthetic test")
    return {"path": path, "E": E, "remove": remove, "keep": keep, "stale": stale, "s0": s0}


@pytest.fixture(scope="module")
def edited(field, edits, tmp_path_factory):
    R = yc.run(field["shp"], str(tmp_path_factory.mktemp("edited")), _settings(field, manual_edits=edits["path"]),
               log=lambda m: None)
    F = _flagged(R)
    F["key"] = me.flagged_keys(R["files"]["flagged_shp"])[0]
    return {"R": R, "F": F}


# ------------------------------------------------------------------------------------------------ the edits file
def test_the_edits_file_is_validated_and_written_the_same_way_every_time(tmp_path):
    a = me.write_edits(tmp_path / "a.json", remove=["k2", "k1", "k2"], keep=["k9"], note="n")
    b = me.write_edits(tmp_path / "b.json", remove=["k1", "k2"], keep=["k9"], note="n")
    assert open(tmp_path / "a.json", "rb").read() == open(tmp_path / "b.json", "rb").read()
    assert a["remove"] == ["k1", "k2"] and a["sha256"] == b["sha256"] and a["file_sha256"] == b["file_sha256"]
    assert me.read_edits(a)["sha256"] == a["sha256"]           # an object read back is accepted as it is
    assert me.read_edits(str(tmp_path / "a.json"))["n_duplicates"] == 0
    with pytest.raises(ValueError, match="in both lists"):
        me.read_edits({"version": 1, "remove": ["x", "y"], "keep": ["y"]})
    with pytest.raises(ValueError, match="version"):
        me.read_edits({"version": 2, "remove": [], "keep": []})
    with pytest.raises(ValueError, match="unknown key"):
        me.read_edits({"version": 1, "remove": [], "keep": [], "removed": []})
    with pytest.raises(ValueError, match="not reading keys"):
        me.read_edits({"version": 1, "remove": [12], "keep": []})
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON"):
        me.read_edits(str(tmp_path / "bad.json"))


def test_a_key_in_both_lists_stops_the_cleaning_before_anything_runs(field, tmp_path):
    p = tmp_path / "both.json"
    p.write_text(json.dumps({"version": 1, "remove": ["a", "b"], "keep": ["b"]}), encoding="utf-8")
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="in both lists"):
        yc.run(field["shp"], str(out), _settings(field, manual_edits=str(p)), log=lambda m: None)
    assert not out.exists()


def test_manual_edits_need_the_sms_method(field, tmp_path):
    with pytest.raises(ValueError, match="sms3sigma"):
        yc.merge_settings({"method": "occd", "manual_edits": {"version": 1, "remove": ["a"], "keep": []}})


# ------------------------------------------------------------------------------------------------ rule 1
def test_no_edits_or_two_empty_lists_give_the_automatic_cleaning_byte_for_byte(field, auto, tmp_path):
    p = me.write_edits(tmp_path / "empty.json")["file"]
    R = yc.run(field["shp"], str(tmp_path / "empty"), _settings(field, manual_edits=p), log=lambda m: None)
    assert _members(R) == _members(auto["R"])
    assert "manual_edits" not in R and "manual_edits" not in R["settings"]
    assert [c["filter"] for c in R["cascade"]] == [c["filter"] for c in auto["R"]["cascade"]]
    assert "Man_Edit" not in auto["F"].columns
    plain = yc.merge_settings(_settings(field))
    for v in (None, p, {"version": 1, "remove": [], "keep": []}):     # the setting is dropped: nothing else differs
        assert yc.merge_settings(_settings(field, manual_edits=v)) == plain


# ------------------------------------------------------------------------------------------------ rule 5: the key
def test_the_key_is_unique_and_the_same_in_the_file_and_its_flagged_file(field, auto):
    info = auto["info"]
    assert info["n_shared"] == 0 and info["n_unique"] == info["n"] == len(auto["F"])
    assert info["columns"] == {"machine": "Machine", "dataset": "Dataset", "order": "Obj__Id", "time": "Time"}
    df = field["df"]
    i = 17
    want = me.KEY_SEP.join([df["Machine"][i], df["Dataset"][i], str(df["Obj__Id"][i]), df["Time"][i], ""])
    assert want in set(auto["F"]["key"]) or df["x"][i] > BOUNDARY_X_M


def test_the_key_does_not_depend_on_the_order_of_the_rows_nor_on_float_text(field, tmp_path):
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    k1 = dict(zip(g["Obj__Id"], me.reading_keys(g.drop(columns="geometry"))[0]))
    sh = g.sample(frac=1.0, random_state=3).reset_index(drop=True)
    sh["Obj__Id"] = sh["Obj__Id"].astype(float)              # the same ids written as floats
    p = str(tmp_path / "shuffled.shp")
    sh.to_file(p, engine="pyogrio")
    g2 = gpd.read_file(p)
    k2 = dict(zip(g2["Obj__Id"].astype(int), me.reading_keys(g2.drop(columns="geometry"))[0]))
    assert k1 == k2


def test_readings_that_share_a_key_are_counted_and_edited_together():
    df = pd.DataFrame({"Machine": ["A", "A", "A"], "Dataset": ["d", "d", "d"], "Obj__Id": [1, 1, 2],
                       "Time": ["t1", "t1", "t2"]})
    keys, info = me.reading_keys(df)
    assert info["n_shared"] == 2 and info["n_unique"] == 2 and info["shared_first"] == ["A|d|1|t1|"]
    E = me.read_edits({"version": 1, "remove": ["A|d|1|t1|"], "keep": []})
    M = me.Edits(E, keys, info)
    assert M.remove.tolist() == [True, True, False]


def test_without_a_record_id_and_a_time_the_key_is_the_logged_position(field, tmp_path):
    import geopandas as gpd
    g = gpd.read_file(field["shp"]).drop(columns=["Obj__Id", "Time"])
    p = str(tmp_path / "noid.shp")
    g.to_file(p, engine="pyogrio")
    R = yc.run(p, str(tmp_path / "out"), _settings(field, sms3sigma={"swath_order": "file"}), log=lambda m: None)
    keys, info = me.flagged_keys(R["files"]["flagged_shp"])
    assert info["position"] and keys[0].count(",") == 1 and keys[0].split("|")[4].startswith("-114.")
    g0 = gpd.read_file(p)
    lon, lat = g0.geometry.x.to_numpy(), g0.geometry.y.to_numpy()
    k0 = me.reading_keys(g0.drop(columns="geometry"), lonlat=(lon, lat))[0]
    assert set(keys) <= set(k0)


# ------------------------------------------------------------------------------------------------ rule 2: SM
def test_removed_by_hand_leaves_after_the_swath_step_and_before_the_filters(auto, edited, edits):
    Ra, Re = auto["R"], edited["R"]
    ids = [c["filter"] for c in Re["cascade"]]
    assert ids[:4] == ["S0", "S1", "S2", "SM"] and ids[4:6] == ["S3", "S4"]
    sm = Re["cascade"][3]
    assert sm["name"] == me.STEP_NAME and sm["removed"] == len(edits["remove"]) and sm["group"] == me.STEP_GROUP
    for a, b in zip(Ra["cascade"][:3], Re["cascade"][:3]):                 # S0-S2 as before
        assert (a["filter"], a["removed"], a["remaining"]) == (b["filter"], b["removed"], b["remaining"])
    Fa, Fe = auto["F"], edited["F"]
    assert (Fe["Rem_By"] == "SM").sum() == len(edits["remove"])
    assert set(Fe.loc[Fe["Rem_By"] == "SM", "key"]) == set(edits["remove"])
    for c in ("Wdth_Opt", "Swath_Scl", "Dist_Opt", "Overlap_f"):          # the swath step did not change
        assert np.array_equal(Fa[c].to_numpy(float), Fe[c].to_numpy(float), equal_nan=True), c
    # S3's mean is that of the readings alive after SM: the readings removed by hand are not in it
    s3e = next(s for s in Re["sms3sigma"]["steps"] if s["step"] == "S3")
    s3a = next(s for s in Ra["sms3sigma"]["steps"] if s["step"] == "S3")
    assert s3e["n_before"] == s3a["n_before"] - len(edits["remove"])
    alive = ~Fe["Rem_By"].isin(["S0", "S1", "S2", "SM"]).to_numpy()
    v = Fe["Moisture__"].to_numpy(float)[alive]
    assert s3e["mean"] == pytest.approx(v.mean(), rel=1e-12) and s3e["sd"] == pytest.approx(v.std(), rel=1e-12)


# ------------------------------------------------------------------------------------------------ rule 3: kept
def test_kept_by_hand_is_never_cut_and_takes_part_in_the_statistics(edited, edits):
    Re, Fe = edited["R"], edited["F"]
    k = Fe["key"].isin(edits["keep"]).to_numpy()
    assert k.sum() == len(edits["keep"])
    assert (Fe.loc[k, "Keep"] == 1).all() and (Fe.loc[k, "Rem_By"] == "").all()
    assert (Fe.loc[k, "Man_Edit"] == me.MARK_KEPT).all()
    assert set(Fe.loc[k, "Rem_Auto"]) <= {"S3", "S4", "S5a", "S5b"}
    clean = pyogrio.read_dataframe(Re["files"]["difm_ready_shp"], read_geometry=False)
    kid = set(zip(Fe.loc[k, "Dataset"], Fe.loc[k, "Obj__Id"]))
    assert kid <= set(zip(clean["Dataset"], clean["Obj__Id"]))
    steps = {s["step"]: s for s in Re["sms3sigma"]["steps"]}
    # the values each step filters, from the flagged file (the yield scaled by the swath step, the speed of the
    # shortened readings Distance / Duration: Swath_Scl and Dist_Opt are written rounded, hence rel 1e-6 below)
    ym = Fe["Yld_Vol_Dr"].to_numpy(float) * Fe["Swath_Scl"].to_numpy(float)
    sp = Fe["Speed_mph_"].to_numpy(float) * Fe["Dist_Opt"].to_numpy(float) / Fe["Distance_f"].to_numpy(float)
    rb = Fe["Rem_By"]
    for fid, vals in (("S3", Fe["Moisture__"].to_numpy(float)), ("S4", sp), ("S5a", ym)):
        s = steps[fid]
        order = [c["filter"] for c in Re["cascade"]]
        before = set(order[:order.index(fid)])
        alive = ~rb.isin(before).to_numpy()                     # alive at the step: the kept-by-hand ones included
        assert alive[k].all()
        assert s["n_before"] == int(alive.sum())
        assert s["mean"] == pytest.approx(vals[alive].mean(), rel=1e-6)
        out = alive & ~((vals >= s["lo"]) & (vals <= s["hi"]))
        assert (out & k).any()                                  # kept readings lie outside the limits ...
        assert s["removed"] == int((out & ~k).sum())            # ... and are not cut
        after = alive & ~(out & ~k)                             # the SD after the cut counts them
        assert s["sd_after"] == pytest.approx(vals[after].std(), rel=1e-4)
        assert abs(vals[after & ~k].std() / s["sd_after"] - 1) > 1e-3      # without them it would differ
    X = Re["manual_edits"]
    row = {r["key"]: r for r in X["kept_by_hand"]}
    assert set(row) == set(edits["keep"])
    assert {r["automatic_step"] for r in row.values()} <= {"S3", "S4", "S5a", "S5b"}
    assert any(r["outside_limits_of"] is not None for r in row.values())


@pytest.fixture(scope="module")
def keep_s5a(field, auto):
    """Every reading the first yield pass of the automatic cleaning cut, kept by hand (the cleaning proper, its log)."""
    keep = _pick(auto["F"], "S5a", 10 ** 6)
    logs = []
    R, g = _clean(field, {"version": 1, "remove": [], "keep": keep}, log=logs.append)
    return {"R": R, "g": g, "keep": keep, "log": logs}


def test_the_yield_pass_decision_uses_the_sd_with_the_readings_kept_by_hand(auto, keep_s5a):
    """The automatic cleaning runs a second yield pass (the first cut the SD by more than 25 %). With every reading
    the first pass cut kept by hand, they stay in the SD after the cut: it falls by less than 25 % and no second pass
    runs."""
    Ra = auto["R"]
    s5a = next(s for s in Ra["sms3sigma"]["steps"] if s["step"] == "S5a")
    assert Ra["sms3sigma"]["yield_passes"]["field"] == 2 and s5a["sd_drop_pct"] > 25 and s5a["removed"] > 0
    assert len(keep_s5a["keep"]) == s5a["removed"]
    R = keep_s5a["R"]
    e5a = next(s for s in R["sms3sigma"]["steps"] if s["step"] == "S5a")
    assert e5a["removed"] == 0 and e5a["sd_after"] == e5a["sd"] and not e5a["next_pass"]
    assert R["sms3sigma"]["yield_passes"]["field"] == 1
    assert R["manual_edits"]["edited"]["groups"]["field"]["yield_passes"] == 1
    assert R["manual_edits"]["automatic"]["groups"]["field"]["yield_passes"] == 2


def test_the_readings_in_neither_list_whose_fate_moved_are_counted():
    """other_readings: the readings in neither list whose fate differs from the automatic cleaning, by kind, per
    combine and per change; the readings of the lists themselves are not counted."""
    keys = np.array(list("abcdefgh"), dtype=object)
    E = me.read_edits({"version": 1, "remove": ["a"], "keep": ["b"]})
    M = me.Edits(E, keys, {"n_shared": 0})
    auto_ = np.array(["", "S5a", "S5b", "", "S4", "S3", "", "S0"], dtype=object)
    edit_ = np.array(["SM", "", "", "S5b", "S5a", "S3", "", "S0"], dtype=object)
    mach = np.array(["A", "A", "A", "B", "B", "B", "A", "A"], dtype=object)
    o = me.other_readings(M, auto_, edit_, mach)
    assert (o["came_back"], o["newly_cut"], o["cut_by_another_step"], o["total"]) == (1, 1, 1, 3)
    assert o["by_combine"] == {"A": {"came_back": 1, "newly_cut": 0, "cut_by_another_step": 0},
                               "B": {"came_back": 0, "newly_cut": 1, "cut_by_another_step": 1}}
    assert o["by_change"] == {"S4 -> S5a": 1, "S5b -> kept": 1, "kept -> S5b": 1}


def test_the_readings_whose_fate_moved_are_in_the_record_and_the_headline(field, auto, tmp_path):
    """Ten kept readings of the field set to 95 bu/ac: the automatic first yield pass keeps them (the 190 bu/ac
    readings are in its SD), the second pass cuts them. Every reading the first pass cut, kept by hand, cancels the
    second pass: the ten come back although nobody picked them. The record's count equals the automatic second
    pass's cuts and what the flagged file shows (Man_Edit '' and Rem_Auto != Rem_By), and the headline says it."""
    import geopandas as gpd
    F = auto["F"]
    pick = F.index[(F["Rem_By"] == "") & (F["Swath_Scl"].astype(float) == 1.0)][200:210]
    keys10 = set(F.loc[pick, "key"])
    A = gpd.read_file(field["shp"])
    kA = me.reading_keys(A.drop(columns="geometry"))[0]
    A.loc[np.isin(kA, list(keys10)), "Yld_Vol_Dr"] = 95.0
    assert int(np.isin(kA, list(keys10)).sum()) == 10
    shp = str(tmp_path / "Synthetic_95.shp")
    A.to_file(shp, engine="pyogrio")
    f95 = dict(field, shp=shp)
    Ra = yc.run(shp, str(tmp_path / "auto95"), _settings(f95), log=lambda m: None)
    Fa = _flagged(Ra)
    Fa["key"] = me.flagged_keys(Ra["files"]["flagged_shp"])[0]
    s5b = next(s for s in Ra["sms3sigma"]["steps"] if s["step"] == "S5b")
    assert s5b["removed"] >= 10 and keys10 <= set(Fa.loc[Fa["Rem_By"] == "S5b", "key"])
    keep = Fa.loc[Fa["Rem_By"] == "S5a", "key"].tolist()
    R = yc.run(shp, str(tmp_path / "edit95"), _settings(f95, manual_edits={"version": 1, "remove": [], "keep": keep}),
               log=lambda m: None)
    o = R["manual_edits"]["other_readings"]
    assert R["sms3sigma"]["yield_passes"]["field"] == 1
    assert o["came_back"] == o["total"] == s5b["removed"] and o["newly_cut"] == o["cut_by_another_step"] == 0
    assert o["by_change"] == {"S5b -> kept": s5b["removed"]}
    Fe = _flagged(R)
    for c in ("Man_Edit", "Rem_Auto"):
        Fe[c] = Fe[c].fillna("").astype(str)
    moved = Fe[(Fe["Man_Edit"] == "") & (Fe["Rem_Auto"] != Fe["Rem_By"])]
    assert len(moved) == o["total"] and (moved["Rem_Auto"] == "S5b").all() and (moved["Rem_By"] == "").all()
    t = me.summary_text(R)
    assert t.startswith("THIS CLEANING INCLUDES MANUAL EDITS") and me.title_label(R) == "WITH MANUAL EDITS"
    assert (f"{o['total']:,} other reading(s), in neither list, changed fate because the limits moved "
            f"({o['came_back']:,} came back, 0 newly cut, 0 cut by another step)") in t
    assert R["manual_edits"]["changes_result"] is True
    assert t in R["warnings"] and t in er.difm_note(R)


def test_the_automatic_run_beside_takes_the_swath_step_of_the_edited_run(keep_s5a):
    """S0-S2 do not depend on the edits: the automatic run takes every Optimize Swath Widths result of the edited run
    (identical inputs), computes none again, and the memo is off after the cleaning."""
    line = next(m for m in keep_s5a["log"] if "Optimize Swath Widths taken from the edited run" in m)
    assert "computed again 0 time(s)" in line and "edited run 0 time(s)" not in line
    assert getattr(me._MEMO, "state", None) is None


def test_matching_keys_to_readings_is_linear():
    """10,000 keys against 40,000 readings in well under a second, the same masks as numpy's isin."""
    import time
    keys = np.array([f"VIN{i % 4}|ds{i % 7}|{i}|t{i}|" for i in range(40000)], dtype=object)
    rem = [f"VIN{i % 4}|ds{i % 7}|{i}|t{i}|" for i in range(0, 30000, 3)]
    kee = [f"VIN{i % 4}|ds{i % 7}|{i}|t{i}|" for i in range(1, 30000, 3)][:9000] + [f"x{i}" for i in range(1000)]
    E = me.read_edits({"version": 1, "remove": rem, "keep": kee})
    t0 = time.perf_counter()
    M = me.Edits(E, keys, {"n_shared": 0})
    dt = time.perf_counter() - t0
    assert dt < 1.0
    assert M.remove.dtype == bool and M.remove.tolist() == np.isin(keys, E["remove"]).tolist()
    assert M.keep.tolist() == np.isin(keys, E["keep"]).tolist()
    assert int(M.remove.sum()) == 10000 and int(M.keep.sum()) == 9000


def test_an_edits_file_that_changes_nothing_says_so_and_gives_the_automatic_files(field, auto, tmp_path):
    """Stale keys only, plus keep keys of readings the automatic cleaning kept anyway: no reading changes fate, the
    clean file is the automatic one byte for byte, and the texts say that an edits file was given and the result is
    the automatic one (not that the cleaning includes manual edits)."""
    stale = [f"NO-SUCH|ds|{k}|t|" for k in range(5)]
    kept = _pick(auto["F"], "", 3, start=10)
    R = yc.run(field["shp"], str(tmp_path / "nochange"),
               _settings(field, manual_edits={"version": 1, "remove": stale[:2], "keep": stale[2:] + kept}),
               log=lambda m: None)
    X = R["manual_edits"]
    assert X["changes_result"] is False and X["other_readings"]["total"] == 0
    assert X["remove"]["readings_applied"] == 0 and X["keep"]["readings_applied"] == 3
    assert X["remove"]["not_found"] == 2 and X["keep"]["not_found"] == 3
    m_a, m_e = _members(auto["R"]), _members(R)
    clean_a = {k: v for k, v in m_a.items() if k.startswith("clean")}
    assert clean_a and {k: v for k, v in m_e.items() if k.startswith("clean")} == clean_a
    t = me.summary_text(R)
    assert t.startswith("AN EDITS FILE WAS GIVEN BUT IT CHANGES NOTHING") and "INCLUDES MANUAL EDITS" not in t
    assert "the result is the automatic cleaning" in t
    assert me.title_label(R) != "WITH MANUAL EDITS" and "no change" in me.title_label(R)
    assert t in R["warnings"]
    assert not any("INCLUDES MANUAL EDITS" in w for w in R["warnings"])
    assert "INCLUDES MANUAL EDITS" not in er.difm_note(R)


def test_a_key_the_import_left_out_is_not_applied_with_its_reason(field):
    """A reading the import as SMS left out (outside its yield range) is not in the file the cleaning reads, but it is
    in the import's all_readings file: with that file on disk its key is 'not applied' with the IMPORT_LEFT_OUT reason;
    without it, the key is 'not found' and warned."""
    import geopandas as gpd
    A = gpd.read_file(field["shp"])
    g0 = A.drop(index=[5, 6, 7]).reset_index(drop=True)          # the import left three readings out
    gone = me.reading_keys(A.iloc[[5, 6, 7]].drop(columns="geometry"))[0].tolist()
    g = pd.DataFrame({"_row": np.arange(len(g0))})
    E = me.read_edits({"version": 1, "remove": [gone[0]], "keep": gone[1:]})
    for rec, on_disk in (({"all_readings": field["shp"]}, True), ({"all_readings": "missing.shp"}, False),
                         (None, False)):
        M = me.prepare(E, g, g0, None, rec)
        M.apply(np.ones(len(g0), bool), np.array([""] * len(g0), dtype=object), [], log=lambda m: None)
        X = {"remove": M._list_counts("remove"), "keep": M._list_counts("keep")}
        if on_disk:
            assert X["keep"]["not_applied_reasons"] == {me.IMPORT_LEFT_OUT: 2} and X["keep"]["not_found"] == 0
            assert X["remove"]["not_applied_reasons"] == {me.IMPORT_LEFT_OUT: 1} and X["remove"]["not_found"] == 0
            assert {d["step"] for d in X["keep"]["not_applied_keys"]} == {"import"}
        else:
            assert X["keep"]["not_found"] == 2 and X["remove"]["not_found"] == 1
            assert X["keep"]["not_applied"] == X["remove"]["not_applied"] == 0
            W = me.warnings_of(dict(X, key={"n_shared": 0}))
            assert any("'keep' list" in w and "match no reading" in w and gone[1] in w for w in W)
        assert X["keep"]["applied"] == X["remove"]["applied"] == 0


# ------------------------------------------------------------------------------------------------ rule 4
def test_keys_cut_by_the_import_check_or_the_clip_are_not_applied_and_said(edited, edits, field):
    X = edited["R"]["manual_edits"]
    kp, rm = X["keep"], X["remove"]
    assert kp["asked"] == len(edits["keep"]) + len(edits["stale"]) + 2 and rm["asked"] == len(edits["remove"]) + 1
    assert kp["applied"] == kp["readings_applied"] == len(edits["keep"])
    assert kp["not_applied_reasons"] == {me.CUT_BEFORE["S0"]: 2}
    assert rm["not_applied_reasons"] == {me.CUT_BEFORE["S0"]: 1} and rm["applied"] == len(edits["remove"])
    Fe = edited["F"]
    assert (Fe.loc[Fe["key"].isin(edits["s0"]), "Man_Edit"] == me.MARK_NOT_APPLIED).all()
    assert (Fe.loc[Fe["key"].isin(edits["s0"]), "Rem_By"] == "S0").all()
    W = edited["R"]["warnings"]
    assert any("'keep' list" in w and "not applied" in w and "S0" in w for w in W)


def test_a_key_of_a_reading_cut_by_the_swath_step_or_set_aside_is_not_applied():
    keys = np.array(["a", "b", "c", "d"], dtype=object)
    E = me.read_edits({"version": 1, "remove": ["b"], "keep": ["a", "c", "far"]})
    M = me.Edits(E, keys, {"n_shared": 0}, aside_keys=["far"])
    why = np.array(["S2", "S1b", "", ""], dtype=object)
    alive = why == ""
    rows = []
    alive2, kp = M.apply(alive, why, rows, log=lambda m: None)
    assert kp.tolist() == [False, False, True, False] and alive2.tolist() == alive.tolist()
    c = M._list_counts("keep")
    assert c["applied"] == 1 and c["not_found"] == 0
    assert c["not_applied_reasons"] == {me.CUT_BEFORE["S2"]: 1, me.ASIDE: 1}
    r = M._list_counts("remove")
    assert r["applied"] == 0 and r["not_applied_reasons"] == {me.CUT_BEFORE["S1b"]: 1}
    assert rows[0]["filter"] == "SM" and rows[0]["removed"] == 0


def _clean(field, edits, design=None, log=None):
    """(R, g) of the cleaning proper with an edits file or object, no files written."""
    S = _settings(field, manual_edits=edits)
    if design:
        S["aoi"] = {"file": design, "buffer_m": 0.01, "clip_output": True}
    S0 = yc.merge_settings(S)
    C, _ = yc.resolve_columns(list(pyogrio.read_info(field["shp"])["fields"]), S0)
    _g0, g, _gx, _gy, R, _d = yc.clean(field["shp"], S0, C, log=log or (lambda m: None))
    return R, g


def test_a_key_set_aside_by_the_clip_is_reported_with_its_reason(field, auto, tmp_path):
    import geopandas as gpd
    g = gpd.read_file(field["shp"])
    out_ = g[g.geometry.x > _lonlat(BOUNDARY_X_M + 5.0, 0.0)[0]]         # readings east of the boundary
    k = me.reading_keys(out_.drop(columns="geometry"))[0].tolist()[:2]
    assert len(k) == 2
    R, g = _clean(field, {"version": 1, "remove": [k[0]], "keep": [k[1]]})
    X = R["manual_edits"]
    assert X["keep"]["not_applied_reasons"] == {me.ASIDE: 1} and X["remove"]["not_applied_reasons"] == {me.ASIDE: 1}
    assert X["keep"]["not_found"] == X["remove"]["not_found"] == 0
    assert R["n_kept"] == auto["R"]["n_kept"]                            # nothing applied: the automatic result


def test_stale_keys_are_warned_with_their_count_and_the_first_ten(edited, edits):
    X = edited["R"]["manual_edits"]
    assert X["keep"]["not_found"] == len(edits["stale"]) == 12
    assert X["keep"]["not_found_first"] == sorted(edits["stale"])[:10]
    w = [w for w in edited["R"]["warnings"] if "match no reading" in w]
    assert len(w) == 1 and "12 key(s)" in w[0] and sorted(edits["stale"])[9] in w[0]


# ------------------------------------------------------------------------------------------------ rules 6-8
def test_the_record_holds_the_automatic_result_beside_the_edited_one(auto, edited, edits):
    Ra, Re = auto["R"], edited["R"]
    X = Re["manual_edits"]
    assert X["sha256"] == edits["E"]["sha256"] and X["file_sha256"] == edits["E"]["file_sha256"]
    assert X["note"] == "synthetic test" and X["step"]["id"] == "SM"
    A, Ed = X["automatic"]["combines"]["ALL"], X["edited"]["combines"]["ALL"]
    assert A["points"] == Ra["n_difm_ready"] and Ed["points"] == Re["n_difm_ready"]
    assert A["acres"] == pytest.approx(Ra["final_map"]["area_ac"], rel=1e-6)
    assert A["yield_bu_ac"] == pytest.approx(Ra["final_map"]["average_area_weighted"], rel=1e-6)
    assert Ed["yield_bu_ac"] == pytest.approx(Re["final_map"]["average_area_weighted"], rel=1e-6)
    lim_a = {(s["group"], s["step"]): (s["lo"], s["hi"]) for s in Ra["sms3sigma"]["steps"]}
    got = {(g, s["step"]): (s["lo"], s["hi"]) for g, G in X["automatic"]["groups"].items() for s in G["steps"]}
    assert got == lim_a
    assert X["automatic"]["groups"]["field"]["yield_passes"] == Ra["sms3sigma"]["yield_passes"]["field"]
    assert X["by_combine"] == {"COMBINE-A": {"removed_by_hand": len(edits["remove"]),
                                             "kept_by_hand": len(edits["keep"])}}
    assert X["by_rate"] is None and "rate" in X["by_rate_note"]
    assert X["keep_rule"] == me.KEEP_RULE
    head = Re["warnings"][[i for i, w in enumerate(Re["warnings"]) if "MANUAL EDITS" in w][0]]
    assert f"{A['points']:,} points" in head and f"{Ed['points']:,} points" in head


def test_the_flagged_file_marks_the_edits_and_the_clean_file_keeps_its_columns(auto, edited, edits):
    Fe = edited["F"]
    assert list(Fe.columns[-3:-1]) == ["Man_Edit", "Rem_Auto"]
    assert list(auto["F"].columns) == [c for c in Fe.columns if c not in ("Man_Edit", "Rem_Auto")]
    assert (Fe.loc[Fe["Rem_By"] == "SM", "Man_Edit"] == me.MARK_REMOVED).all()
    assert (Fe["Rem_Auto"].fillna("").astype(str).to_numpy() == auto["F"]["Rem_By"].to_numpy()).all()
    ca = pyogrio.read_info(auto["R"]["files"]["difm_ready_shp"])["fields"].tolist()
    ce = pyogrio.read_info(edited["R"]["files"]["difm_ready_shp"])["fields"].tolist()
    assert ca == ce


def test_the_same_edits_twice_give_the_same_files(field, edited, edits, tmp_path):
    R = yc.run(field["shp"], str(tmp_path / "again"), _settings(field, manual_edits=edits["path"]),
               log=lambda m: None)
    assert _members(R) == _members(edited["R"])
    a, b = dict(R["manual_edits"]), dict(edited["R"]["manual_edits"])
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_the_report_and_the_difm_note_say_the_cleaning_includes_manual_edits(edited):
    R = edited["R"]
    assert os.path.getsize(R["files"]["report_pdf"]) > 0
    story = []
    assert me.report_section(story, R, 7) == 8
    text = " ".join(getattr(p, "text", "") for p in story)
    assert "7. Manual edits" in text and "THIS CLEANING INCLUDES MANUAL EDITS" in text
    assert "MANUAL EDITS" in er.difm_note(R)


def test_counts_per_rate_with_a_trial_design(field, auto, edits, tmp_path):
    import geopandas as gpd
    half = PASS_GAP_M / 2
    y0, y1 = -half, (N_PASS - 1) * PASS_GAP_M + half
    xs = np.linspace(-2.0, BOUNDARY_X_M, 5)
    plots = [_rect(xs[i], xs[i + 1], y0, y1) for i in range(4)]
    design = str(tmp_path / "design.geojson")
    gpd.GeoDataFrame({"plot": ["1", "2", "3", "4"], "Rate": [100.0, 150.0, 100.0, 150.0]}, geometry=plots,
                     crs="EPSG:4326").to_file(design, driver="GeoJSON")
    R, g = _clean(field, edits["path"], design)
    X = R["manual_edits"]
    assert set(X["by_rate"]) <= {"100", "150"}
    assert sum(v["removed_by_hand"] for v in X["by_rate"].values()) == X["remove"]["readings_applied"]
    assert sum(v["kept_by_hand"] for v in X["by_rate"].values()) == X["keep"]["readings_applied"]
    r = pd.to_numeric(g["Tgt_Rate"], errors="coerce")
    assert X["by_rate"]["100"]["removed_by_hand"] == int(((g["_man_edit"] == "R") & (r == 100)).sum())


def test_the_command_line_takes_manual_edits(field, edits, tmp_path, capsys):
    rc = er.main([field["shp"], "--out", str(tmp_path / "w"), "--aoi", field["boundary"], "--tag", "syn",
                  "--manual-edits", edits["path"]])
    assert rc == 0
    out = capsys.readouterr().out
    assert "SM   removed" in out and "manual edits     THIS CLEANING INCLUDES MANUAL EDITS" in out
    assert "WARNING: THIS CLEANING INCLUDES MANUAL EDITS" in out
    J = json.load(open(os.path.join(str(tmp_path / "w"), "output", "syn_sms3s_cleaning.json"), encoding="utf-8"))
    assert J["manual_edits"]["sha256"] == edits["E"]["sha256"]
    assert J["settings"]["manual_edits"]["remove"] == edits["E"]["remove"]
    bad = tmp_path / "both.json"
    bad.write_text(json.dumps({"version": 1, "remove": ["a"], "keep": ["a"]}), encoding="utf-8")
    rc = er.main([field["shp"], "--out", str(tmp_path / "w2"), "--manual-edits", str(bad)])
    assert rc == 2 and "in both lists" in capsys.readouterr().err
    assert not (tmp_path / "w2").exists()                                # refused before anything ran
