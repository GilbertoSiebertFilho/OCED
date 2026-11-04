# -*- coding: utf-8 -*-
"""OCED — Olds College Extract Data: the brand of the app in one place (name, version, palette, logos, page icon,
the small CSS of the page).

    import brand                      # from app/oced.py (Streamlit puts app/ on sys.path)

    st.set_page_config(page_title=brand.NAME, page_icon=brand.page_icon(), layout="wide")
    brand.inject()                    # once per run, right after set_page_config
    st.logo(brand.LOGO_H, icon_image=brand.LOGO_SHIELD, size="large")
    brand.step_header(1, "Raw data", "Upload the monitor files")   # the numbered heading of a step card
    brand.brand_block()               # name, version and tagline of the title bar

Palette (assets/brand/BRAND.md, the Olds College site stylesheet): navy is the primary colour (buttons, headings,
active states), light blue the accent (icons, outlines, selected states), green = kept / success, orange = removed /
warnings. Contrast on white (WCAG): navy 11.1:1, text 14.7:1, LIGHT_BLUE_TEXT 4.9:1 (AA), GREEN_TEXT 5.5:1,
ORANGE_TEXT 5.4:1. LIGHT_BLUE (3.1:1), GREEN (2.7:1) and ORANGE (2.0:1) fail AA as body text on white: use them for
fills, icons, outlines and large labels only, and the *_TEXT shades when a word must carry the colour.

The theme itself is .streamlit/config.toml (read when the app is started from the project folder: run_oced.bat);
inject() adds what a theme cannot set, as light-dark() pairs that follow the rendered theme: a navy title bar (the
app_header container: white logo, name, version pill, Start over), the four steps as white cards on a light canvas
with a navy top edge and a numbered badge (step_header(); the oced_step_1..4 containers), the controls that decide a
run in tinted, edged panels (method_panel), the tabs as pills with the selected one navy, primary buttons navy with a
lift on hover, the main action (run_go) larger and the clean-shapefile download green, metrics as small cards, the
captions at full opacity (MUTED, 7.6:1). Only stable hooks are used (data-testid, role / aria attributes, the
st-key-* classes of keyed elements). No external font or CDN: the app runs offline on a field laptop (the satellite
image under the maps needs the internet; the maps draw without it).
"""
from __future__ import annotations

import functools
import os
import time as _time

LOADED_AT = _time.time()     # when this module was read
# the file it was read from, (mtime_ns, size)
SOURCE_STAMP = (lambda s: (s.st_mtime_ns, s.st_size))(os.stat(__file__))

NAME = "OCED"
LONG_NAME = "OCED — Olds College Extract Data"
TAGLINE = "Olds College Extract Data · raw yield data to clean shapefiles with the SMS 3-sigma sequence"
ORG = "Olds College Smart Farm (OFPE)"
VERSION = "0.2.0"

# ---- palette (hex strings; BRAND.md)
NAVY = "#00358E"            # primary: buttons, headings, tree group titles, active states, lines and fits in figures
LIGHT_BLUE = "#009CDE"      # accent: icons, outlines (AOI on maps), selected / active switch; not body text on white
GREEN = "#00B373"           # kept points / success fills
DARK_GREEN = "#006747"      # secondary accent (sparingly)
ORANGE = "#F5A623"          # removed points / warning highlight fills
TEXT = "#1F2937"            # body text
MUTED = "#4B5563"           # captions (7.6:1 on white)
BG2 = "#F3F7FC"             # secondary background (widgets, expanders, sidebar)
RULE = "#D7E3F2"            # borders and rules
WHITE = "#FFFFFF"
# AA-safe shades for words that must carry the colour (4.5:1 or better on white and on BG2)
LIGHT_BLUE_TEXT = "#0077B6"
GREEN_TEXT = "#00784D"
ORANGE_TEXT = "#9A5B00"

# ---- logos (absolute paths built from this file: the app can be started from any folder)
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "brand")
LOGO_H = os.path.join(ASSETS, "oc_logo_horizontal.png")               # 500 x 125, white background: header, sidebar
LOGO_H_REV = os.path.join(ASSETS, "oc_logo_horizontal_reversed.png")  # white wordmark for dark backgrounds
LOGO_SHIELD = os.path.join(ASSETS, "oc_logo_shield.png")              # shield + wordmark: favicon, collapsed sidebar

# pydeck colours of the app's maps ([r, g, b]; add the alpha in the layer)
map_colors = {"kept": [0, 179, 115], "removed": [245, 166, 35], "aoi": [0, 156, 222]}


@functools.lru_cache(maxsize=1)
def page_icon():
    """The page icon for st.set_page_config: the shield mark of oc_logo_shield.png as a square PIL image (the
    wordmark under the shield is unreadable at favicon size, so the rows above the first transparent gap are kept and
    padded to a square). The file's path when PIL cannot open it (st.set_page_config accepts both)."""
    try:
        from PIL import Image
        im = Image.open(LOGO_SHIELD).convert("RGBA")
        w, h = im.size
        alpha = im.getchannel("A")
        cut = h
        for y in range(h):                                    # first fully transparent row = the gap under the shield
            if alpha.crop((0, y, w, y + 1)).getbbox() is None:
                cut = y
                break
        mark = im.crop((0, 0, w, cut))
        box = mark.getbbox()
        if box:
            mark = mark.crop(box)
        side = max(mark.size) + 8
        icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        icon.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2), mark)
        return icon
    except Exception:                                         # pragma: no cover - a missing/odd file: the path works too
        return LOGO_SHIELD


def _css() -> str:
    """The style block: stable hooks only (data-testid attributes, the .stApp root, the st-key-* classes of the keyed
    containers and widgets, our own .oced-* classes); no emotion class names. Every colour is a CSS light-dark() pair
    resolved by the browser against the color-scheme that Streamlit sets on .stApp for the rendered theme, so the
    block is right on the very first run too (dark mode is not a target, but stays legible). Python-side detection
    through st.context.theme.type is not used: on the first run after a connection it reports the OS preference, not
    the configured theme.

    The look (v2.6): a navy title bar (app_header), the four steps as white cards on a light canvas with a navy top
    edge and a numbered badge (step_header; keys oced_step_1..4), the controls that decide the run in tinted panels
    (method_panel: crop and cleaning method; factor_method_box; the column mapping expander colmap), the tabs as
    pills (the selected one navy), primary buttons navy with a lift on hover, the main action (run_go) larger and the
    clean-shapefile download green, metrics as small cards. The captions keep full opacity (WCAG AA: 7.6:1 on white)."""
    navy, blue, txt = NAVY, LIGHT_BLUE, TEXT
    heading = f"light-dark({NAVY}, {LIGHT_BLUE})"
    rule = f"light-dark({RULE}, rgba(255,255,255,0.14))"
    muted = f"light-dark({MUTED}, rgba(255,255,255,0.68))"
    link = f"light-dark({LIGHT_BLUE_TEXT}, {LIGHT_BLUE})"
    canvas = "light-dark(#F3F6FA, #0E1117)"
    card = "light-dark(#FFFFFF, #161B22)"
    tint = "light-dark(#EAF2FC, rgba(0,156,222,0.12))"
    tint2 = "light-dark(#F5F9FE, rgba(255,255,255,0.03))"
    edge = "light-dark(#C9DCF3, rgba(0,156,222,0.35))"
    pill_txt = f"light-dark({NAVY}, #CFE3FA)"
    shadow = "0 1px 2px rgba(16,24,40,0.05), 0 6px 22px rgba(0,53,142,0.07)"
    return f"""<style>
/* ---- OCED brand (app/brand.py) ---- */
.stApp [data-testid="stMain"], .stApp [data-testid="stHeader"] {{ background: {canvas}; }}
.stApp h1, .stApp h2, .stApp h3 {{ color: {heading}; }}
.stApp [data-testid="stMainBlockContainer"] {{ padding-top: 4.4rem; }}
/* captions: full opacity, muted text (7.6:1 on white, 7.0:1 on the sidebar), AA links */
div[data-testid="stCaptionContainer"] {{ opacity: 1; }}
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] p,
div[data-testid="stCaptionContainer"] li {{ color: {muted}; }}
div[data-testid="stCaptionContainer"] a {{ color: {link}; }}

/* ---- title bar */
.stApp .st-key-app_header {{
  background: linear-gradient(115deg, #00266B 0%, {navy} 42%, #0060C0 82%, {blue} 125%);
  border-radius: 16px; padding: 1.0rem 1.5rem !important; box-shadow: 0 10px 28px rgba(0,53,142,0.28);
  margin-bottom: 0.4rem;
}}
.oced-brand {{ display: flex; flex-direction: column; gap: 0.15rem; }}
.oced-brand-name {{ font-size: 2.05rem; font-weight: 800; letter-spacing: 0.03em; color: #FFFFFF; line-height: 1.1;
  display: flex; align-items: center; gap: 0.6rem; }}
.oced-brand-tag {{ font-size: 0.98rem; color: rgba(255,255,255,0.88); }}
.oced-pill {{ font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; padding: 0.18rem 0.55rem;
  border-radius: 999px; background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.45); color: #FFFFFF; }}
.stApp .st-key-app_header [data-testid="stCaptionContainer"],
.stApp .st-key-app_header [data-testid="stCaptionContainer"] p {{ color: rgba(255,255,255,0.88) !important; }}
.stApp .st-key-app_header [data-testid="stBaseButton-secondary"] {{
  background: rgba(255,255,255,0.10); color: #FFFFFF; border: 1px solid rgba(255,255,255,0.55); }}
.stApp .st-key-app_header [data-testid="stBaseButton-secondary"]:hover {{
  background: rgba(255,255,255,0.22); border-color: #FFFFFF; color: #FFFFFF; }}
.stApp .st-key-app_header [data-testid="stBaseButton-secondary"] p,
.stApp .st-key-app_header [data-testid="stBaseButton-secondary"] [data-testid="stIconMaterial"] {{ color: #FFFFFF; }}

/* ---- the steps: cards with a navy top edge and a numbered badge */
.stApp [class*="st-key-oced_step_"] {{
  background: {card}; border: 1px solid {rule} !important; border-top: 4px solid {navy} !important;
  border-radius: 14px !important; box-shadow: {shadow}; padding: 1.15rem 1.45rem 1.4rem !important;
}}
.oced-step {{ display: flex; align-items: center; gap: 0.85rem; margin: 0.05rem 0 0.25rem; }}
.oced-step-num {{ flex: none; width: 2.35rem; height: 2.35rem; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-weight: 800; font-size: 1.15rem; color: #FFFFFF;
  background: linear-gradient(135deg, {navy} 0%, #0060C0 100%); box-shadow: 0 3px 8px rgba(0,53,142,0.30); }}
.oced-step-title {{ font-size: 1.45rem; font-weight: 800; color: {heading}; line-height: 1.15; }}
.oced-step-sub {{ font-size: 0.92rem; color: {muted}; margin-top: 0.1rem; }}

/* ---- the controls that decide the run: tinted panels */
.stApp .st-key-method_panel, .stApp .st-key-factor_method_box {{
  background: {tint}; border: 1px solid {edge}; border-left: 5px solid {blue}; border-radius: 12px;
  padding: 0.85rem 1.1rem 0.95rem !important;
}}
.stApp .st-key-clean_method [data-testid="stWidgetLabel"] p,
.stApp .st-key-factor_method [data-testid="stWidgetLabel"] p {{ font-weight: 700; font-size: 1.02rem; color: {heading}; }}
/* the options of the two segmented controls (buttons with role radio, aria-checked on the chosen one) */
.stApp .st-key-clean_method button[role="radio"], .stApp .st-key-factor_method button[role="radio"] {{
  min-height: 2.6rem; padding: 0.5rem 1.15rem; font-weight: 600; font-size: 0.98rem; background: {card};
  color: {pill_txt}; }}
.stApp .st-key-clean_method button[role="radio"] p, .stApp .st-key-factor_method button[role="radio"] p {{
  font-weight: 600; color: {pill_txt}; }}
.stApp .st-key-clean_method button[role="radio"]:hover, .stApp .st-key-factor_method button[role="radio"]:hover {{
  background: {tint}; border-color: {blue}; }}
.stApp .st-key-clean_method button[role="radio"][aria-checked="true"],
.stApp .st-key-factor_method button[role="radio"][aria-checked="true"] {{
  background: {navy}; border-color: {navy}; box-shadow: 0 2px 8px rgba(0,53,142,0.28); }}
.stApp .st-key-clean_method button[role="radio"][aria-checked="true"] p,
.stApp .st-key-factor_method button[role="radio"][aria-checked="true"] p {{ color: #FFFFFF; }}
/* the column mapping: a tinted, edged expander */
.stApp .st-key-colmap [data-testid="stExpander"] details {{
  border: 1px solid {edge}; border-left: 5px solid {navy}; border-radius: 12px; background: {card}; overflow: hidden; }}
.stApp .st-key-colmap [data-testid="stExpander"] summary {{ background: {tint}; padding-top: 0.8rem; padding-bottom: 0.8rem; }}
.stApp .st-key-colmap [data-testid="stExpander"] summary p {{ font-weight: 700; font-size: 1.02rem; color: {heading}; }}
.stApp .st-key-colmap [data-testid="stExpander"] summary [data-testid="stIconMaterial"] {{ color: {heading}; }}
/* other expanders of the main area: a soft hover */
.stApp [data-testid="stMain"] [data-testid="stExpander"] details {{ border-radius: 12px; }}
.stApp [data-testid="stMain"] [data-testid="stExpander"] summary:hover {{ background: {tint2}; }}
.stApp [data-testid="stMain"] [data-testid="stExpander"] summary p {{ font-weight: 600; }}

/* ---- tabs as pills: the selected one navy */
.stApp [data-testid="stMain"] [data-testid="stTabs"] [role="tablist"] {{
  gap: 0.4rem; flex-wrap: wrap; padding: 0.45rem; background: {tint2}; border: 1px solid {rule}; border-radius: 12px;
  box-shadow: none; }}
.stApp [data-testid="stMain"] [data-testid="stTab"] {{
  height: auto; margin: 0; padding: 0.42rem 0.95rem; border-radius: 999px; background: {card}; border: 1px solid {edge};
  transition: background 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease; }}
.stApp [data-testid="stMain"] [data-testid="stTab"] p {{ font-weight: 600; font-size: 0.95rem; color: {pill_txt}; }}
.stApp [data-testid="stMain"] [data-testid="stTab"]:hover {{ background: {tint}; border-color: {blue}; }}
.stApp [data-testid="stMain"] [data-testid="stTab"][aria-selected="true"] {{
  background: {navy}; border-color: {navy}; box-shadow: 0 2px 8px rgba(0,53,142,0.28); }}
.stApp [data-testid="stMain"] [data-testid="stTab"][aria-selected="true"] p {{ color: #FFFFFF; }}
.stApp [data-testid="stMain"] [data-testid="stTabs"] .react-aria-SelectionIndicator {{ display: none; }}
.stApp [data-testid="stMain"] [data-testid="stTabPanel"] {{ padding-top: 0.6rem; }}
.stApp [data-testid="stMain"] [data-testid="stTabPanel"] h3 {{ font-size: 1.35rem; }}

/* ---- blocks nested in a step (field of interest, one filter): white cards, a smaller heading */
.stApp .st-key-aoi_block, .stApp [class*="st-key-filter_box_"] {{
  background: {card}; border-radius: 12px !important; border: 1px solid {rule} !important;
  border-left: 4px solid {blue} !important; }}
.stApp .st-key-aoi_block h3, .stApp [class*="st-key-filter_box_"] h3 {{ font-size: 1.2rem; padding: 0.2rem 0 0.45rem; }}

/* ---- buttons: primary navy with a lift, secondary outlined, the main action larger, the main download green */
.stApp [data-testid="stBaseButton-primary"] {{
  background: linear-gradient(180deg, #0A4FB8 0%, {navy} 100%); border: 1px solid #00307F; color: #FFFFFF;
  font-weight: 600; box-shadow: 0 1px 2px rgba(16,24,40,0.10), 0 4px 12px rgba(0,53,142,0.22);
  transition: transform 0.08s ease, box-shadow 0.15s ease, filter 0.15s ease; }}
.stApp [data-testid="stBaseButton-primary"]:hover {{
  filter: brightness(1.08); color: #FFFFFF; border-color: #00307F; transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0,53,142,0.32); }}
.stApp [data-testid="stBaseButton-primary"]:disabled {{ filter: grayscale(0.6) opacity(0.55); box-shadow: none;
  transform: none; }}
.stApp [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {{ border-color: {edge}; color: {pill_txt};
  font-weight: 500; }}
.stApp [data-testid="stMain"] [data-testid="stBaseButton-secondary"]:hover {{ background: {tint}; border-color: {navy};
  color: {pill_txt}; }}
.stApp .st-key-run_go [data-testid="stBaseButton-primary"] {{
  min-height: 3.3rem; padding: 0.75rem 2.3rem; border-radius: 12px; font-size: 1.12rem; font-weight: 700;
  background: linear-gradient(135deg, {navy} 0%, #0060C0 70%, {blue} 130%); letter-spacing: 0.01em; }}
.stApp .st-key-run_go [data-testid="stBaseButton-primary"] p {{ font-size: 1.12rem; font-weight: 700; }}
.stApp [data-testid="stDownloadButton"] [data-testid="stBaseButton-primary"] {{
  background: linear-gradient(180deg, #00A86B 0%, #00875A 100%); border-color: #007A50;
  box-shadow: 0 1px 2px rgba(16,24,40,0.10), 0 4px 12px rgba(0,135,90,0.25); }}
.stApp [data-testid="stDownloadButton"] [data-testid="stBaseButton-primary"]:hover {{
  border-color: #007A50; box-shadow: 0 6px 18px rgba(0,135,90,0.32); }}

/* ---- metrics as small cards */
.stApp [data-testid="stMain"] [data-testid="stMetric"] {{ background: {card}; border-radius: 12px; }}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {{ font-weight: 600; }}
.stApp [data-testid="stMain"] [data-testid="stMetricLabel"] p {{ text-transform: uppercase; letter-spacing: 0.05em;
  font-size: 0.78rem; color: {muted}; }}
[data-testid="stMetricValue"] {{ color: {heading}; font-weight: 700; }}

/* ---- alerts, tables */
.stApp [data-testid="stAlert"] > div {{ border-radius: 10px; }}
.stApp [data-testid="stDataFrame"] {{ border-radius: 10px; overflow: hidden; }}

/* ---- sidebar: section labels, white cards for the tree steps */
[data-testid="stSidebar"] h3 {{ font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.09em;
  color: {heading}; }}
[data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] {{ color: {heading}; font-weight: 700; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background: {card}; border-radius: 10px;
  border-color: {rule}; }}
[data-testid="stSidebar"] [data-testid="stExpander"] summary p {{ font-weight: 600; }}
.oced-rule {{ height: 1px; background: {rule}; border: 0; margin: 0.6rem 0 1.0rem; }}
</style>"""


def step_header(num: int, title: str, subtitle: str = "") -> None:
    """The heading of a step card: a numbered navy badge, the title and a one-line subtitle (the .oced-step classes
    of inject())."""
    import html
    import streamlit as st
    st.html(f'<div class="oced-step"><div class="oced-step-num">{int(num)}</div><div><div class="oced-step-title">'
            f'{html.escape(title)}</div>' + (f'<div class="oced-step-sub">{html.escape(subtitle)}</div>' if subtitle
                                             else "") + "</div></div>")


def brand_block(name: str | None = None, version: str | None = None, tagline: str | None = None) -> None:
    """The name, version and tagline of the title bar (white on navy)."""
    import html
    import streamlit as st
    st.html(f'<div class="oced-brand"><div class="oced-brand-name">{html.escape(name or NAME)}<span class="oced-pill">'
            f'v{html.escape(version or VERSION)}</span></div><div class="oced-brand-tag">'
            f'{html.escape(tagline or TAGLINE)}</div></div>')


def inject():
    """Write the style block into the page (st.html; once per run, after st.set_page_config)."""
    import streamlit as st
    st.html(_css())


def rule():
    """A thin light rule between the steps (the .oced-rule class of inject())."""
    import streamlit as st
    st.html('<div class="oced-rule"></div>')


def footer_caption() -> str:
    """The sidebar footer: 'OCED 0.2.0 · Olds College Smart Farm (OFPE)'."""
    return f"{NAME} {VERSION} · {ORG}"
