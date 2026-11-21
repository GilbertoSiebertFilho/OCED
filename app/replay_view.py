# -*- coding: utf-8 -*-
"""OCED: the harvest replay in the app ('Play the harvest'), beside the maps of step 2 (the readings as imported) and
of step 3 (the cleaning result, kept and removed). The player is engine/replay.py's HTML, embedded with st.iframe
(Streamlit 1.61: an HTML string becomes a same-origin srcdoc frame that runs its script, with the frame policy that
allows full screen; st.components.v1.html is deprecated, st.html runs no script in a frame of its own), and the same
replay is offered as a file to open in a browser tab.

    import replay_view
    replay_view.section(shp, key, kind="import", outline=rings, raw_root=folder, field=tag)       # step 2
    replay_view.section(flagged_shp, key, kind="clean", outline=rings, steps=names, field=tag)    # step 3

It reads the files only: nothing of the import or of the cleaning changes. The payload is built when the section is
opened (never on a rerun with it closed) and kept in Streamlit's cache (file, its modification time, the boundary,
the steps, the makes and the management zone map).

Management zone map (optional, engine/zones.py): a polygon file the user made elsewhere (OCED never builds zones),
given once per file of the work (field): uploaded, or a file on this computer read in place. Like the boundary, an
upload is kept in the work folder (zones/<tag>/), and the choice (file and class column) in zones/<tag>/zone_map.json
there, so both replays of the file use it and it is still there after a rerun or when the work is opened again. With
it, the player shows the zones and the yield inside each one, and zone_yield.csv can be downloaded.

Edits by hand (step 3, the replay of a cleaning, when the caller gives on_edits): the player is mounted through a
two-way component (st.components.v2, inline JavaScript, no build step: it holds the same self-contained player in an
iframe of its own and passes on the marks the player posts with 'Reprocess with these edits'). The marks (combine
number, reading index of the payload) become the engine's reading keys here (engine.replay.edit_keys, which refuses a
reading cut by the import range, the clip or the swath step and marks made on another version of the cleaning), and
on_edits(keys) writes the edits file and cleans again (app/oced.py). The replay file to download stays read-only:
it shows the readings removed and kept by hand. The replay of the imported readings has no edit mode."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile

import streamlit as st

from engine import replay as rp
from engine import zones as zn

HEIGHT = 660                       # the player's height on the page (px); its taller / shorter switch resizes it
MAKE_CHOICES = [k for k in rp.MAKES]
ZONE_TYPES = ["zip", "geojson", "json", "kml", "kmz", "gpkg", "shp", "shx", "dbf", "prj", "cpg"]
ZONE_EXTS = (".shp", ".zip", ".geojson", ".json", ".gpkg", ".kml", ".kmz")
ZONE_STATE = "replay_zone_maps"    # session state: {work folder|tag: {path, name, column, fingerprint, stamp}}


def _mtime(p: str) -> float:
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


@st.cache_data(max_entries=8, show_spinner=False)
def _hints(root: str, stamp: float) -> dict:
    """The make of each combine as the raw data tells it (engine.replay.make_hints), once per input folder."""
    try:
        return rp.make_hints(root)
    except Exception:                                    # noqa: BLE001 - a raw folder that cannot be read: no hint
        return {}


def _record(record) -> dict | None:
    """The cleaning record (its JSON) of a flagged file: record = (path, stamp) or None."""
    if not record or not record[0] or not os.path.isfile(record[0]):
        return None
    try:
        with open(record[0], encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


@st.cache_data(max_entries=6, show_spinner="Preparing the replay ...")
def payload_of(path: str, stamp: float, kind: str, outline, steps, makes, hints, title, zone=None, record=None,
               edit: bool = False) -> dict:
    """The player's data (engine.replay.replay_payload, NaN made JSON-safe), cached by its inputs. zone: (zone map
    path, its fingerprint, class column) or None; record: (the cleaning record's path, its stamp) for the limits of
    the card and the edits by hand; edit: the replay of a cleaning that can be edited (every reading up to
    EDIT_MAX_BYTES, the file rows of each combine kept for edit_keys; they never reach the page)."""
    return rp._clean_floats(rp.replay_payload(path, kind=kind, outline=outline, title=title, makes=makes, hints=hints,
                                              steps=steps, zones=zone[0] if zone else None,
                                              zone_column=zone[2] if zone else None, record=_record(record),
                                              edit=edit, max_bytes=rp.EDIT_MAX_BYTES if edit else rp.MAX_BYTES))


@st.cache_data(max_entries=6, show_spinner=False)
def html_of(path: str, stamp: float, kind: str, outline, steps, makes, hints, title, embedded: bool,
            zone=None, record=None, edit: bool = False, two_way: bool = False) -> str:
    """The player as one HTML document; two_way: the app's player with 'Edit points' (edit payloads only)."""
    P = payload_of(path, stamp, kind, outline, steps, makes, hints, title, zone, record, edit)
    return rp.replay_html(P, height=HEIGHT if embedded else None, embedded=embedded, edit=bool(edit and two_way))


# ------------------------------------------------------------------------------------------------ the two-way player
PLAYER_JS = """
export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let fr = parentElement.querySelector("iframe");
  if (!fr) {
    fr = document.createElement("iframe");
    fr.setAttribute("allow", "fullscreen"); fr.setAttribute("allowfullscreen", ""); fr.title = "Harvest replay";
    fr.style.cssText = "width:100%;border:0;display:block;border-radius:12px;";
    parentElement.appendChild(fr);
  }
  if (fr.dataset.v !== data.v) { fr.dataset.v = data.v; fr.style.height = data.h + "px"; fr.height = String(data.h); fr.srcdoc = data.html; }
  const onMsg = (ev) => {
    if (ev.source !== fr.contentWindow) return;
    const m = ev.data;
    if (!m || m.type !== "oced-replay-marks") return;
    setTriggerValue("marks", { token: m.token, remove: m.remove, keep: m.keep, changed: m.changed });
  };
  window.addEventListener("message", onMsg);
  return () => window.removeEventListener("message", onMsg);
}
"""
_PLAYER = {}


def _player():
    """The two-way player component: registered once per Streamlit runtime (again when a new runtime no longer knows
    it, as a test's new AppTest)."""
    from streamlit.components.v2.get_bidi_component_manager import get_bidi_component_manager
    if "c" not in _PLAYER or get_bidi_component_manager().get("oced_replay_player") is None:
        _PLAYER["c"] = st.components.v2.component("oced_replay_player", js=PLAYER_JS)
    return _PLAYER["c"]


def marks_key(key: str) -> str:
    """Session state: marks the player sent, for this run (the component's trigger value is copied here, and a test
    can put a value here as the component would send it)."""
    return f"replay_marks_{key}"


def _sent_marks(res, key: str):
    """The marks the player sent in this run, or None."""
    v = None
    try:
        v = res.get("marks") if res is not None and hasattr(res, "get") else None
    except Exception:                                    # noqa: BLE001 - no trigger value
        v = None
    held = st.session_state.pop(marks_key(key), None)
    return v if v else held


def tries_key(key: str) -> str:
    """Session state: how many times the player of key sent its marks. It is part of the player's version, so the
    frame is loaded again after every reprocess, also one that stopped and left the same files (the player would
    otherwise stay on 'Reprocessing in the app ...')."""
    return f"replay_tries_{key}"


def msg_key(key: str) -> str:
    """Session state: why the last marks of the player of key were not applied, shown above the replay in the next
    run (the run that refused them is cut short to load the player again)."""
    return f"replay_marks_msg_{key}"


def mount_two_way(html: str, key: str):
    """The player in the two-way component; returns the marks it sent in this run (or None)."""
    import hashlib as _h
    v = _h.sha1(html.encode()).hexdigest() + f":{int(st.session_state.get(tries_key(key)) or 0)}"
    res = _player()(key=f"replay_cc_{key}", data={"html": html, "h": HEIGHT, "v": v}, on_marks_change=lambda: None)
    return _sent_marks(res, key)


# ------------------------------------------------------------------------------------------------ the zone map
def _parts(path: str) -> list:
    base, ext = os.path.splitext(path)
    return [base + e for e in (".shp", ".shx", ".dbf")] if ext.lower() == ".shp" else [path]


def zone_fingerprint(path: str) -> str:
    """A short hash of what a zone map file holds (a shapefile: its .shp, .shx and .dbf), as the boundary's."""
    h = hashlib.sha1()
    for p in _parts(path):
        try:
            with open(p, "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(b"-")
    return h.hexdigest()[:16]


def _stamp(path: str) -> list:
    """[modification time, size] of each part of a zone map file: when it changes, the file is read again."""
    out = []
    for p in _parts(path):
        try:
            s_ = os.stat(p)
            out += [round(s_.st_mtime, 3), s_.st_size]
        except OSError:
            out += [0, -1]
    return out


@st.cache_data(max_entries=8, show_spinner="Reading the zone map ...")
def zone_info(path: str, fingerprint: str, column: str | None) -> dict:
    """{column, labels, columns (the ranked candidates), notes, n_features} of a zone map, or {error}: never raises
    (a file that cannot be read or used is said in the control, and its Remove button stays there)."""
    try:
        zm = zn.prepare(path, column)
    except Exception as e:                               # noqa: BLE001 - zones.prepare says why in its own words
        return {"error": str(e).strip() or f"the management zone map {os.path.basename(path)} cannot be read "
                                           f"({type(e).__name__})"}
    return {"column": zm.column, "labels": list(zm.labels), "columns": list(zm.columns), "notes": list(zm.notes),
            "n_features": zm.n_features}


def _workdir() -> str:
    return st.session_state.get("workdir") or os.path.join(tempfile.gettempdir(), "oced_replay")


def _zone_dir(field: str) -> str:
    return os.path.join(_workdir(), "zones", str(field))


def _zkey(field: str) -> str:
    """The session's key of a file's management zone map: the work folder and the file's tag (two works can hold
    files of the same tag; each keeps its own zone map)."""
    return os.path.normcase(os.path.abspath(_workdir())) + "|" + str(field)


def _resolve(Z: dict, field: str) -> dict:
    """The record with its path made absolute: an upload is kept relative to the work's zones/<tag>/ folder (the
    work folder can be moved or copied), a file read in place by its absolute path."""
    p = Z.get("path") or ""
    if p and not os.path.isabs(p):
        p = os.path.join(_zone_dir(field), p)
    return dict(Z, path=os.path.normpath(p) if p else p)


def zone_map_of(field: str | None) -> dict | None:
    """The management zone map chosen for a file of the work: from the session, else from the work folder. A file
    changed since it was chosen is fingerprinted again (so the replay reads it again)."""
    if not field:
        return None
    maps = st.session_state.setdefault(ZONE_STATE, {})
    zk = _zkey(field)
    Z = maps.get(zk)
    if Z is None:
        rec = os.path.join(_zone_dir(field), "zone_map.json")
        if os.path.exists(rec):
            try:
                with open(rec, encoding="utf-8") as fh:
                    Z = json.load(fh)
            except (OSError, ValueError):
                Z = None
        maps[zk] = Z if isinstance(Z, dict) else {}
    Z = maps.get(zk) or None
    if not Z:
        return None
    Z = _resolve(Z, field)
    if not os.path.exists(Z.get("path") or ""):
        return dict(Z, missing=True)
    stamp = _stamp(Z["path"])
    if stamp != Z.get("stamp"):                          # changed on disk (or recorded before the stamp existed)
        Z = dict(Z, fingerprint=zone_fingerprint(Z["path"]), stamp=stamp)
        _set_zone_map(field, Z)
    return Z


def _set_zone_map(field: str, Z: dict | None):
    """Records (or, None, forgets) a file's management zone map in the session and in zones/<tag>/zone_map.json.
    Forgetting also deletes the upload kept in zones/<tag>/file/."""
    maps = st.session_state.setdefault(ZONE_STATE, {})
    d = os.path.abspath(_zone_dir(field))
    rec = os.path.join(d, "zone_map.json")
    if Z:
        Z = {k: Z.get(k) for k in ("path", "name", "column", "fingerprint", "stamp")}
        p = os.path.normpath(os.path.abspath(Z["path"]))
        kept = os.path.normcase(p).startswith(os.path.normcase(os.path.join(d, "file")) + os.sep)
        Z["path"] = os.path.relpath(p, d) if kept else p
        if Z.get("stamp") is None:
            Z["stamp"] = _stamp(p)
        maps[_zkey(field)] = Z
        os.makedirs(d, exist_ok=True)
        with open(rec, "w", encoding="utf-8") as fh:
            json.dump(Z, fh, indent=1)
    else:
        maps[_zkey(field)] = {}
        if os.path.exists(rec):
            os.remove(rec)
        shutil.rmtree(os.path.join(d, "file"), ignore_errors=True)


def _use_zone_file(field: str, source) -> str | None:
    """Keeps an uploaded zone map in the work folder (or takes a file on this computer in place), checks it and makes
    it the field's zone map. Returns an error text, or None (a refused upload is not kept)."""
    kind, val = source
    d = os.path.join(_zone_dir(field), "file")
    if kind == "upload":
        low = [os.path.basename(f.name).lower() for f in val]
        dup = sorted({n for n in low if low.count(n) > 1})
        if dup:
            return f"two files are named {dup[0]}: give one zone map (one shapefile set, or a zip)"
        names = [os.path.basename(f.name) for f in val]
        main = ([n for n in names if n.lower().endswith(".shp")] or
                [n for n in names if os.path.splitext(n)[1].lower() in ZONE_EXTS])
        if not main:
            return ("no zone map among the files given: a management zone map is a .zip (a shapefile), the .shp + .shx "
                    "+ .dbf + .prj of a shapefile, a .geojson, a .gpkg, a .kml or a .kmz")
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
        for f in val:
            with open(os.path.join(d, os.path.basename(f.name)), "wb") as fh:
                fh.write(f.getbuffer())
        path = os.path.join(d, main[0])
    else:
        path = str(val).strip().strip('"')
        if not path or not os.path.exists(path):
            return f"not found on this computer: {path or '(empty)'}"
    path = os.path.abspath(path)
    fp = zone_fingerprint(path)
    info = zone_info(path, fp, None)
    if info.get("error"):
        if kind == "upload":                              # a refused upload is not kept in the work folder
            shutil.rmtree(d, ignore_errors=True)
        return info["error"]
    _set_zone_map(field, {"path": path, "name": os.path.basename(path), "column": info["column"], "fingerprint": fp})
    return None


def zone_control(field: str | None, key: str) -> dict | None:
    """The optional 'Management zone map' of the replay: upload or path, then the class column (the ranked
    candidates, the first preselected), and a remove button. Returns the zone map in use, or None."""
    if not field:
        return None
    Z = zone_map_of(field)
    with st.container(border=True, key=f"zm_box_{key}"):
        st.markdown("**Management zone map** · optional",
                    help="A zone map made elsewhere (a prescription or management zone file of polygons, one column "
                         "that names the zones). OCED does not build zones: it plays the harvest over yours and shows "
                         "the yield inside each zone, and at the end whether the zones agree with the yield.")
        if Z and Z.get("missing"):
            st.warning(f"The zone map {Z.get('name')} is no longer at {Z.get('path')}.", icon=":material/warning:")
            if st.button("Remove the zone map", key=f"zm_rm_{key}", icon=":material/delete:"):
                _set_zone_map(field, None)
                st.rerun()
            return None
        if Z:
            info = zone_info(Z["path"], Z["fingerprint"], Z.get("column"))
            if info.get("error"):
                st.error(info["error"], icon=":material/error:")
                if st.button("Remove the zone map", key=f"zm_rm_{key}", icon=":material/delete:"):
                    _set_zone_map(field, None)
                    st.rerun()
                return None
            cols = [c["column"] for c in info["columns"]]
            lab = {c["column"]: f"{c['column']} · {c['n_classes']} zone{'s' if c['n_classes'] != 1 else ''} "
                                f"({', '.join(c['values'][:5])}{', ...' if c['n_classes'] > 5 else ''})"
                   for c in info["columns"]}
            c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
            with c1:
                st.success(f"{Z['name']} · {len(info['labels'])} management zone"
                           f"{'s' if len(info['labels']) != 1 else ''}: {', '.join(info['labels'][:8])}"
                           + (", ..." if len(info["labels"]) > 8 else ""), icon=":material/layers:")
            with c2:
                cur = info["column"]
                pick = st.selectbox("Column that names the zones", cols, index=cols.index(cur) if cur in cols else 0,
                                    format_func=lambda c: lab.get(c, c), key=f"zm_col_{key}_{cur}",
                                    help="The columns with 1 to 12 different values; the likely one first.")
                if pick != cur:
                    _set_zone_map(field, dict(Z, column=pick))
                    st.rerun()
            for n in info["notes"]:
                st.caption(n)
            if st.button("Remove the zone map", key=f"zm_rm_{key}", icon=":material/delete:"):
                _set_zone_map(field, None)
                st.rerun()
            return dict(Z, column=info["column"])
        nonce = int(st.session_state.get(f"zm_nonce_{_zkey(field)}") or 0)
        up = st.file_uploader("Zone map file", accept_multiple_files=True, type=ZONE_TYPES,
                              key=f"zm_up_{key}_{nonce}",
                              help="A .zip (a shapefile), the .shp + .shx + .dbf + .prj of a shapefile, a .geojson, "
                                   ".gpkg, .kml or .kmz. Polygons with a column that names the zones (at most 12).")
        with st.container(horizontal=True, vertical_alignment="bottom"):
            zpath = st.text_input("or a file on this computer", key=f"zm_path_{key}",
                                  placeholder=r"C:\...\zones.shp")
            go = st.button("Use", type="primary", icon=":material/layers:", key=f"zm_use_{key}")
        if go:
            if not up and not (zpath or "").strip():
                st.toast("Upload a zone map or type its path first", icon=":material/info:")
            else:
                err = _use_zone_file(field, ("upload", up) if up else ("path", zpath))
                if err:
                    st.error(err, icon=":material/error:")
                else:
                    st.session_state[f"zm_nonce_{_zkey(field)}"] = nonce + 1
                    st.rerun()
    return None


# ------------------------------------------------------------------------------------------------ the section
def section(path: str | None, key: str, kind: str = "import", outline=None, raw_root=None,
            steps: dict | None = None, title: str | None = None, label: str = "Play the harvest",
            field: str | None = None, record: str | None = None, on_edits=None):
    """The folded section 'Play the harvest': opened, the player of the file (an import, or the flagged file of a
    cleaning: kind 'clean'), a make per combine to correct, and the replay as an HTML file to download. raw_root:
    the raw data's input folder (or a function that gives it, called only when the section is open) for the make
    of each combine. field: the file of the work (its tag), whose management zone map the section offers.
    record: the cleaning record (JSON) of a flagged file (the card's limits, the edits by hand); on_edits: a cleaning
    whose readings can be marked by hand: on_edits(keys) gets engine.replay.edit_keys's result when the player sends
    its marks (it writes the edits file and cleans again)."""
    if not path or not os.path.exists(path):
        return
    refused = st.session_state.pop(msg_key(key), None)
    if refused:                                          # outside the folded section: seen even when it is closed
        st.error(refused, icon=":material/error:")
    box = st.expander(label, expanded=False, key=f"replay_box_{key}", icon=":material/play_circle:",
                      on_change="rerun")
    with box:
        if not box.open:
            return
        stamp = _mtime(path)
        try:
            root = raw_root() if callable(raw_root) else raw_root
        except Exception:                                # noqa: BLE001 - no input folder recorded: no hint
            root = None
        hints = _hints(root, _mtime(root)) if root and os.path.exists(root) else {}
        makes = dict(st.session_state.get(f"replay_makes_{key}") or {})
        Z = zone_control(field, key)
        zone = (Z["path"], Z["fingerprint"], Z["column"]) if Z else None
        args = (path, stamp, kind, outline or None, dict(steps or {}), makes, hints, title)
        rec = (record, _mtime(record)) if (kind == "clean" and record) else None
        edit = bool(kind == "clean" and callable(on_edits))
        try:
            P = payload_of(*args, zone, rec, edit)
        except Exception as e:                           # shown, never a crash of the page
            st.error(f"The replay cannot be built from this file: {e}", icon=":material/error:")
            return
        if not P.get("combines"):
            st.caption("No reading with a position and a time: nothing to play.")
            return
        st.caption(
            ("The readings as they were logged, combine by combine" if kind == "import" else
             "The cleaning: the kept readings in colour, the removed ones in grey (colour by 'Kept / removed' for the "
             "step that removed each)")
            + f": {P['n']:,} readings of {len(P['combines'])} combine{'s' if len(P['combines']) != 1 else ''}. "
            + P["basis"]["note"] + " Space plays and pauses; drag the map, scroll or pinch to zoom; the button at the "
            "top right goes full screen."
            + (" With the management zone map: switch 'Yield map | Zone map'; 'Do the zones agree?' shows the yield of "
               "each zone" + (" (raw readings, not cleaned)." if kind != "clean" else " (the readings the cleaning "
                                                                                       "kept).")
               if P.get("zones") else "")
            + (" Pause, or point at a reading, for its data." if not edit else
               " 'Edit points' (top right of the player): click a kept reading to remove it, or one the moisture, "
               "speed or yield filter removed to keep it, then 'Reprocess with these edits'; the card of the "
               "reading under the cursor shows its data and its combine's limits."))
        if (P.get("zones") or {}).get("coverage_note"):
            st.warning("Management zone map: " + P["zones"]["coverage_note"] + ".", icon=":material/warning:")
        if edit and not (P.get("edit") or {}).get("ok"):
            st.info("Edit points is off for this replay: " + str((P.get("edit") or {}).get("why")) + ".",
                    icon=":material/edit_off:")
        if (P.get("manual") or {}).get("summary"):
            st.caption("This cleaning includes edits by hand: in the player a cross marks a reading removed by hand, "
                       "a ring one kept by hand, a diamond one whose fate moved with the limits.")
        if edit:
            sent = mount_two_way(html_of(*args, True, zone, rec, edit, True), key)
            if sent:
                # every reprocess loads the player again (its version counts the tries): after a cleaning that stopped
                # the files are the same, and the frame would keep showing 'Reprocessing in the app ...'
                st.session_state[tries_key(key)] = int(st.session_state.get(tries_key(key)) or 0) + 1
                try:
                    K = rp.edit_keys(P, sent, path)
                except ValueError as e:
                    st.session_state[msg_key(key)] = f"The marks were not applied: {e}"
                    st.rerun()
                else:
                    on_edits(K)
        else:
            st.iframe(html_of(*args, True, zone), height=HEIGHT)
        c1, c2 = st.columns([1, 2], vertical_alignment="center")
        with c1:
            name = os.path.splitext(os.path.basename(path))[0] + "_replay.html"
            st.download_button("Replay as a file (.html)", data=lambda: html_of(*args, False, zone, rec, edit),
                               file_name=name,
                               mime="text/html", key=f"replay_dl_{key}", icon=":material/download:",
                               help="The same player in one file: open it in a browser tab (full screen, a large "
                                    "monitor), keep it or send it. It needs no internet except for the satellite "
                                    "image." + (" The management zones are in it." if P.get("zones") else ""))
            if P.get("zones"):
                Zp = P["zones"]
                st.download_button("Zone table (zone_yield.csv)",
                                   data=lambda: zn.csv_text(Zp["stats"], raw=Zp["raw"]),
                                   file_name=os.path.splitext(os.path.basename(path))[0] + "_zone_yield.csv",
                                   mime="text/csv", key=f"replay_zcsv_{key}", icon=":material/table:",
                                   help="Per management zone, and per zone and combine: readings, acres, bushels, "
                                        "yield, mean and SD, the share of the zone harvested; with the border readings "
                                        "left out ('interior') and counted ('all')."
                                        + (" Raw readings, not cleaned." if Zp["raw"] else ""))
        with c2:
            with st.popover("Make of each combine", icon=":material/agriculture:"):
                st.caption("The colours of the machine follow its make. What the data told:")
                new = {}
                for C in P["combines"]:
                    own = rp.make_of(None, P.get("src_fmt"), C["id"], rp._hint_for(C["id"], hints))[0]
                    pick = st.selectbox(
                        f"{C['num']} · {C['name']}", MAKE_CHOICES, index=MAKE_CHOICES.index(C["make"]),
                        format_func=lambda k: rp.MAKES[k]["label"], key=f"replay_mk_{key}_{C['num']}",
                        help=f"{C['id']}: {C['make_why']}")
                    if pick != own:
                        new[C["id"]] = pick
                if new != makes and st.button("Apply", key=f"replay_mk_go_{key}", type="primary"):
                    st.session_state[f"replay_makes_{key}"] = new
                    st.rerun()
