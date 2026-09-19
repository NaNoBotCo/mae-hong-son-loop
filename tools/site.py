#!/usr/bin/env python3
"""site.py — build/api → build/site. A static, bilingual, offline-capable site.

Every reader-facing page exists twice: English at its path, Thai at /th/<same path>. The
two are the same build function called with a different language, so a page cannot exist
in one language and silently not the other; where a record has no Thai text the Thai page
says so rather than showing machine translation.

    python3 tools/site.py
    SITE_URL=https://example.org python3 tools/site.py
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet  # noqa: E402
import geo  # noqa: E402
from common import BUILD, TIER_LABEL, TYPES, jload  # noqa: E402
from css import CSS  # noqa: E402

API = BUILD / "api"
SITE = BUILD / "site"
SITE_URL = os.environ.get("SITE_URL", "https://nanobotco.github.io/mae-hong-son-loop").rstrip("/")
# The same site is published twice: the GitHub Pages copy, which is what the repo builds
# by default, and https://motdang.net/loop. Two live copies of one site is duplicate
# content, so both declare the same canonical and the other copy carries rel="alternate".
# CANONICAL_URL overrides where that points; set it to SITE_URL to make a copy primary.
CANONICAL_URL = os.environ.get("CANONICAL_URL", "https://motdang.net/loop").rstrip("/")
# Internal links are root-relative, and this is why. The site is published under a
# path (/loop, /mae-hong-son-loop), and a host that serves /loop with a 200 instead of
# redirecting to /loop/ makes the browser resolve "./images/x.jpg" against the site root.
# GitHub Pages redirects and so hides the problem; R2 behind motdang.net does not, and
# every picture on the front page 404ed. A relative path is only safe when the trailing
# slash is guaranteed, and it is not. BASE_PATH is taken from SITE_URL, and can be
# overridden for a local preview served at the root.
BASE_PATH = os.environ.get("BASE_PATH")
if BASE_PATH is None:
    _p = urllib.parse.urlparse(SITE_URL).path.strip("/")
    BASE_PATH = f"/{_p}/" if _p else "/"
if not BASE_PATH.endswith("/"):
    BASE_PATH += "/"
NAME = {"en": "The Mae Hong Son Loop", "th": "วงรอบแม่ฮ่องสอน"}
TAG = {"en": "1,864 curves between Chiang Mai and Mae Hong Son, and everything worth stopping for",
       "th": "1,864 โค้ง ระหว่างเชียงใหม่กับแม่ฮ่องสอน และทุกจุดที่ควรแวะ"}
DATA_LICENSE = "https://creativecommons.org/licenses/by/4.0/"
AUTHOR = {"@type": "Person", "name": "NaN", "url": "https://wichaa.net"}
LANGS = ("en", "th")


def E(x) -> str:
    return html.escape("" if x is None else str(x))


def T(d: dict, key: str, lang: str, fallback=True):
    """A field in the requested language. `names.th` / `text_th` hold the Thai."""
    if lang == "th":
        if key.startswith("text."):
            v = (d.get("text_th") or {}).get(key[5:])
        elif key.startswith("names."):
            v = (d.get("names") or {}).get(key[6:] + "_th") or (
                (d.get("names") or {}).get("th") if key == "names.name" else None)
        else:
            v = d.get(key + "_th")
        if v:
            return v
        if not fallback:
            return None
    if key.startswith("text."):
        return (d.get("text") or {}).get(key[5:])
    if key.startswith("names."):
        return (d.get("names") or {}).get(key[6:])
    return d.get(key)


# ---------------------------------------------------------------- vocab / labels
V = jload(API / "vocab.json")
TYPE_INFO = {e["key"]: e for e in V["types"]["entries"]}
FACETS = V["facets"]["facets"]
REGIONS = {e["key"]: e for e in V["regions"]["entries"]}
PATH_OF = {t: TYPE_INFO[t]["path"] for t in TYPE_INFO}
DIR_OF = {"leg": "legs", "road": "roads", "town": "towns", "stop": "stops", "wat": "wats",
          "dish": "food",
          "coffee": "coffee", "spring": "springs", "stay": "beds", "hazard": "hazards",
          "bike": "bikes", "kit": "kit", "person": "people", "org": "outfits", "event": "calendar",
          "term": "words", "story": "stories", "art": "objects"}

UI = {
 "en": {"home": "The loop", "legs": "Legs", "which": "Which way", "numbers": "Numbers",
        "good": "The good part", "year": "The year", "air": "Air", "danger": "Danger", "baggage": "Baggage",
        "quiz": "Which ride",
        "roadbook": "Roadbook",
        "all": "Everything", "about": "How this was made",
        "cw": "Clockwise", "ccw": "Counter-clockwise",
        "km": "km", "curves": "curves", "hairpins": "hairpins", "days": "days",
        "hours": "hours", "runs": "Runs", "kin": "Runs with", "said_here": "Named here by",
        "sources": "Sources", "prov": "Where each claim comes from", "back": "Back",
        "what": "What it is", "story": "The long version", "how": "How", "today": "Now",
        "share": "Share", "copy": "Copy link", "print": "Print", "measured": "Measured off the map",
        "no_th": "This section has not been written in Thai yet. The English is below.",
        "unverified": "Parts of this record are marked as needing verification.",
        "riding": "What it asks of you", "season": "By season", "route": "The route"},
 "th": {"home": "วงรอบ", "legs": "ช่วงทาง", "which": "ไปทางไหน", "numbers": "ตัวเลข",
        "good": "ส่วนที่ดี", "year": "ทั้งปี", "air": "อากาศ", "danger": "อันตราย", "baggage": "สัมภาระ",
        "quiz": "ขี่แบบไหน",
        "roadbook": "สมุดเส้นทาง",
        "all": "ทั้งหมด", "about": "ทำขึ้นอย่างไร",
        "cw": "ตามเข็มนาฬิกา", "ccw": "ทวนเข็มนาฬิกา",
        "km": "กม.", "curves": "โค้ง", "hairpins": "โค้งหักศอก", "days": "วัน",
        "hours": "ชั่วโมง", "runs": "เส้นทาง", "kin": "เกี่ยวข้องกับ", "said_here": "ถูกอ้างถึงโดย",
        "sources": "แหล่งอ้างอิง", "prov": "แต่ละข้อความมาจากไหน", "back": "ย้อนกลับ",
        "what": "คืออะไร", "story": "ฉบับยาว", "how": "วิธี", "today": "ตอนนี้",
        "share": "แบ่งปัน", "copy": "คัดลอกลิงก์", "print": "พิมพ์",
        "measured": "วัดจากแผนที่",
        "no_th": "ส่วนนี้ยังไม่ได้เขียนเป็นภาษาไทย ด้านล่างเป็นภาษาอังกฤษ",
        "unverified": "บางส่วนของบันทึกนี้ยังต้องการการตรวจสอบ",
        "riding": "ต้องการอะไรจากคุณ", "season": "ตามฤดูกาล", "route": "เส้นทาง"},
}

NAV = [("", "home"), ("legs/", "legs"), ("which-way/", "which"), ("numbers/", "numbers"),
       ("good/", "good"), ("year/", "year"), ("air/", "air"), ("danger/", "danger"), ("baggage/", "baggage"),
       ("quiz/", "quiz"), ("roadbook/", "roadbook")]


def rel(depth: int = 0) -> str:
    """The site root, as a root-relative path. `depth` is ignored and kept so the call
    sites read the same; see BASE_PATH above for why this is not "../" * depth."""
    return BASE_PATH


def url_of(r: dict, lang="en") -> str:
    """A record's path below its language root."""
    return f"{PATH_OF[r['type']]}/{r['id']}/"


def lroot(lang: str) -> str:
    """The current language's root, as a root-relative path. Body links hang off this;
    images, the API and the machine files hang off rel(), the site root."""
    return f"{BASE_PATH}th/" if lang == "th" else BASE_PATH


def page(title, body, depth, lang, desc="", jsonld=None, canonical="", head="", cur="",
         path="", card=""):
    """`depth` is the page's depth below its LANGUAGE root, which is what the body's own
    links are built against. A Thai page sits one level deeper than that below the site
    root, so assets and the language switch need `r`, while the nav — which stays inside
    the language — needs `rin`.  `path` is the page's own path below the language root,
    and is what lets the switch land on the same page rather than the other home page."""
    rin = BASE_PATH + ("th/" if lang == "th" else "")    # the language root
    r = BASE_PATH                                        # the site root
    ui = UI[lang]
    en_url = f"{BASE_PATH}{path}"
    th_url = f"{BASE_PATH}th/{path}"
    bilingual = path != "api/"
    # Share titles are short: every platform truncates around eighty characters and cuts
    # mid-sentence. The <title> keeps the long form for the browser tab; og:title takes
    # the page's own name. og:url matches the canonical so both published copies share
    # as the same link rather than as two competing ones.
    og_title = title.split(" — ")[0] if " — " in title else title
    if og_title.strip() == NAME[lang]:
        og_title = NAME[lang]
    og_desc = desc or TAG[lang]
    if og_desc.strip() == og_title.strip():
        og_desc = TAG[lang]
    og_url = f"{CANONICAL_URL}/{'th/' if lang == 'th' else ''}{path}"
    # a link with no picture shares as a grey box, so every page names a card
    card_url = f"{CANONICAL_URL}/cards/{card or 'index'}.jpg"
    card_meta = (f'<meta property="og:image" content="{E(card_url)}">'
                 f'<meta property="og:image:secure_url" content="{E(card_url)}">'
                 f'<meta property="og:image:type" content="image/jpeg">'
                 f'<meta property="og:image:width" content="1200">'
                 f'<meta property="og:image:height" content="630">'
                 f'<meta property="og:image:alt" content="{E(og_title)}">'
                 f'<meta name="twitter:image" content="{E(card_url)}">'
                 f'<meta name="twitter:image:alt" content="{E(og_title)}">')
    cur_attr = ' aria-current="page"'
    nav = "".join(f'<a href="{rin}{p}"{cur_attr if k == cur else ""}>{E(ui[k])}</a>'
                  for p, k in NAV)
    ld = json.dumps(jsonld or [], ensure_ascii=False)
    return f"""<!doctype html>
<html lang="{lang}"{' class="th"' if lang == 'th' else ''}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(CANONICAL_URL)}/{"th/" if lang == "th" else ""}{E(path)}">
<link rel="alternate" href="{E(canonical or SITE_URL)}">
<link rel="alternate" hreflang="en" href="{SITE_URL}/{E(path)}">
<link rel="alternate" hreflang="th" href="{SITE_URL}/th/{E(path)}">
<link rel="alternate" hreflang="x-default" href="{SITE_URL}/{E(path)}">
<meta property="og:title" content="{E(og_title)}">
<meta property="og:description" content="{E(og_desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{E(og_url)}">
<meta property="og:site_name" content="{E(NAME[lang])}">
<meta property="og:locale" content="{'th_TH' if lang == 'th' else 'en_GB'}">
<meta name="twitter:card" content="summary_large_image">
{card_meta}
<link rel="icon" href="{r}icon.svg" type="image/svg+xml">
<link rel="manifest" href="{r}manifest.webmanifest">
<link rel="alternate" type="application/atom+xml" href="{r}feed.xml">
<style>{CSS}</style>{head}
<script type="application/ld+json">{ld}</script>
<script defer src="{r}copy.js"></script>
</head>
<body>
<a class="sr" href="#main">Skip to content</a>
<header class="top"><div class="in">
<a class="brand" href="{rin}">Mae Hong Son <b>Loop</b></a>
<nav>{nav}</nav>
<span class="langsw">
<a href="{en_url}"{' aria-current="true"' if lang == 'en' else ''} hreflang="en">EN</a>
{f'<a href="{th_url}"{chr(32)}{"aria-current=" + chr(34) + "true" + chr(34) if lang == "th" else ""} hreflang="th">ไทย</a>' if bilingual else ''}
</span>
</div></header>
<main id="main">
{body}
</main>
<footer class="bot"><div class="in">
<p><b>{E(NAME[lang])}</b> — {E(TAG[lang])}</p>
<p>{'Records CC BY 4.0. Road geometry and places © OpenStreetMap contributors, ODbL 1.0. Air data from Open-Meteo (CAMS), CC BY 4.0, and the Thai Pollution Control Department. Corpus text from Wikipedia, CC BY-SA 4.0.' if lang == 'en' else 'บันทึกเผยแพร่ภายใต้ CC BY 4.0 เส้นทางและสถานที่ © ผู้ร่วมสร้าง OpenStreetMap ภายใต้ ODbL 1.0 ข้อมูลอากาศจาก Open-Meteo (CAMS) ภายใต้ CC BY 4.0 และกรมควบคุมมลพิษ เนื้อหาอ้างอิงจากวิกิพีเดีย ภายใต้ CC BY-SA 4.0'}</p>
<p><a href="{rin}about/">{E(ui['about'])}</a> · <a href="{r}api/">API</a> · <a href="{rin}all/">{E(ui['all'])}</a> · <a href="{r}llms.txt">llms.txt</a></p>
{fleet.row_html(SELF, label=("More from the same publisher" if lang == "en" else "เว็บอื่นของผู้จัดทำ"), roster=ROSTER)}
{fleet.support_html(roster=ROSTER)}
</div></footer>
</body></html>
"""


def marks(text: str) -> str:
    """*Inference —* and *Tradition holds —* become visible markers, **bold** becomes bold."""
    t = E(text)
    t = re.sub(r"\*(Inference|Tradition holds|อนุมาน|ตามธรรมเนียม)\s*—\*",
               lambda m: f'<mark class="inf">{m.group(1)} —</mark>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
    return t


def prose(text: str) -> str:
    if not text:
        return ""
    return "".join(f"<p>{marks(p)}</p>" for p in text.split("\n\n") if p.strip())


# Brand marks, drawn rather than fetched — the CDN a social icon font would come from is
# one more thing that can fail, and these are four paths.
ICONS = {
 "facebook": "M17 2h-3a5 5 0 0 0-5 5v3H6v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z",
 "line": "M12 3C6.5 3 2 6.6 2 11c0 3.9 3.5 7.2 8.2 7.9.3.07.8.2.9.5.1.3.07.7.03 1l-.14.9c-.04.3-.2 1 .9.55 1.1-.45 6-3.5 8.2-6C21.4 14.2 22 12.7 22 11c0-4.4-4.5-8-10-8z",
 "whatsapp": "M20 12a8 8 0 0 1-11.9 7L4 20l1-4.1A8 8 0 1 1 20 12z",
 "x": "M3 3l7.5 9.5L3.5 21h2l6-6.8L17 21h4l-7.9-10L20.5 3h-2l-5.6 6.4L8 3z",
 "reddit": "M22 12a2 2 0 0 0-3.4-1.4A11 11 0 0 0 13 9l.9-3.4 2.6.6a1.6 1.6 0 1 0 .2-1.4l-3.4-.8-1.3 4.9A11 11 0 0 0 5.4 10.6 2 2 0 1 0 3.6 14 4 4 0 0 0 3.5 15c0 3 3.8 5.5 8.5 5.5s8.5-2.5 8.5-5.5a4 4 0 0 0-.1-1A2 2 0 0 0 22 12z",
 "mail": "M3 6h18v12H3zM3 6l9 7 9-7",
 "link": "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1",
 "print": "M7 8V3h10v5M7 18H5a2 2 0 0 1-2-2v-4a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-2M7 14h10v7H7z",
}


def _icon(name: str) -> str:
    d = ICONS.get(name, "")
    fill = "none" if name in ("mail", "link", "print", "whatsapp") else "currentColor"
    return (f'<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true" '
            f'fill="{fill}" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{d}"/></svg>')


def share_row(url: str, title: str, lang: str, blurb: str = "") -> str:
    """The share bar. A row of small grey words was getting the clicks it deserved, so
    this is a block: it says what sharing does, it shows the card that will appear, and
    the buttons are buttons."""
    ui = UI[lang]
    en = lang == "en"
    q = urllib.parse.quote
    share_text = f"{title} — {blurb}" if blurb else title
    links = [
        ("facebook", "Facebook", f"https://www.facebook.com/sharer/sharer.php?u={q(url)}"),
        ("line", "LINE", f"https://social-plugins.line.me/lineit/share?url={q(url)}"),
        ("whatsapp", "WhatsApp", f"https://api.whatsapp.com/send?text={q(share_text + ' ' + url)}"),
        ("x", "X", f"https://twitter.com/intent/tweet?text={q(share_text)}&url={q(url)}"),
        ("reddit", "Reddit", f"https://reddit.com/submit?url={q(url)}&title={q(title)}"),
        ("mail", "Email", f"mailto:?subject={q(title)}&body={q(share_text + chr(10) + chr(10) + url)}"),
    ]
    btns = "".join(
        f'<a class="sh sh-{k}" href="{E(href)}" rel="noopener" target="_blank" '
        f'data-share="{E(k)}">{_icon(k)}<span>{E(label)}</span></a>'
        for k, label, href in links)
    head = ("Send this to whoever is coming with you" if en
            else "ส่งให้คนที่จะไปด้วยกัน")
    sub = ("It opens the same in Thai." if en else "เปิดเป็นภาษาอังกฤษได้เหมือนกัน")
    return (f'<aside class="sharebar"><div class="shhead"><b>{E(head)}</b>'
            f'<span class="mute small">{E(sub)}</span></div>'
            f'<div class="shrow">{btns}'
            f'<button type="button" class="sh sh-link" data-copy="{E(url)}">'
            f'{_icon("link")}<span>{E(ui["copy"])}</span></button>'
            f'<button type="button" class="sh sh-print" onclick="window.print()">'
            f'{_icon("print")}<span>{E(ui["print"])}</span></button>'
            f'<button type="button" class="sh sh-native" hidden data-native="{E(url)}" '
            f'data-title="{E(title)}">{_icon("link")}<span>'
            f'{E("Share…" if en else "แชร์…")}</span></button></div></aside>'
            '<script>document.addEventListener("DOMContentLoaded",function(){'
            'var n=document.querySelector(".sh-native");'
            'if(n&&navigator.share){n.hidden=false;n.addEventListener("click",function(){'
            'navigator.share({title:n.dataset.title,url:n.dataset.native}).catch(function(){})})}});'
            "</script>")


# ---------------------------------------------------------------- data, loaded once
NODES = jload(API / "nodes.json")["nodes"]
BY_ID = {r["id"]: r for r in NODES}
ITIN = jload(API / "itinerary.json")
ROADS = jload(API / "roads.json")
CURVES = jload(API / "curves.json")
AIR = jload(API / "air.json")
AIR_NOW = jload(API / "air-now.json")
PLACES = jload(API / "places.json")
PACKLIST = jload(Path(__file__).resolve().parent.parent / "data" / "vocab" / "packlist.json")
BASE = jload(API / "base.json") if (API / "base.json").exists() else {}
ELEV = jload(API / "elevation.json") if (API / "elevation.json").exists() else {}
SOURCES = {s["id"]: s for s in jload(API / "sources.json")["sources"]}
COV = jload(API / "coverage.json")
ROSTER = fleet.load(Path(__file__).resolve().parent.parent / "data" / "fleet.json")



SELF = "mae-hong-son-loop"

MONTHS = [("01", "Jan", "ม.ค."), ("02", "Feb", "ก.พ."), ("03", "Mar", "มี.ค."), ("04", "Apr", "เม.ย."),
          ("05", "May", "พ.ค."), ("06", "Jun", "มิ.ย."), ("07", "Jul", "ก.ค."), ("08", "Aug", "ส.ค."),
          ("09", "Sep", "ก.ย."), ("10", "Oct", "ต.ค."), ("11", "Nov", "พ.ย."), ("12", "Dec", "ธ.ค.")]


def aqi_class(pm: float) -> str:
    if pm is None:
        return ""
    for lim, c in ((9.0, "aq1"), (35.4, "aq2"), (55.4, "aq3"), (125.4, "aq4"), (225.4, "aq5")):
        if pm <= lim:
            return c
    return "aq6"


_RING = ITIN.get("ring") or {}
MAP_CREDIT = (
    f'The circuit is drawn from OpenStreetMap ways tagged Route 107, 1095 and 108: '
    f'{_RING.get("km", "—")} km, of which {_RING.get("bridged_pct", 0)}% is bridged in a '
    f'straight line where the route number is not tagged. '
    f'© OpenStreetMap contributors · relief Open-Meteo / Copernicus DEM'
) if _RING else "© OpenStreetMap contributors · relief Open-Meteo / Copernicus DEM"

ALL_LINES = [[tuple(c) for c in ln]
             for r in ROADS.values() for ln in (r.get("lines") or ([r["line"]] if r.get("line") else []))]
BOX = geo.fit(ALL_LINES)


def basemap_svg() -> str:
    """The land, drawn once at the shared projection. Every map <image>s this.

    Shaded relief is a per-pixel job, so the terrain arrives as a PNG built by
    tools/terrain.py and is referenced here; water and the provincial line stay vector,
    because a river at one pixel wide wants to be crisp."""
    p = geo.Proj(box=BOX, width=900)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {p.width:.0f} {p.height:.0f}" '
           f'width="{p.width:.0f}" height="{p.height:.0f}">',
           f"<style>{geo.BASEMAP_CSS}</style>"]
    if BASE:
        out.append(geo.water_layer(p, BASE))
        out.append(geo.boundary_layer(p, BASE))
    out.append("</svg>")
    return "".join(out)


def base_map(width=820, demand=False, highlight=None, pins=None, labels=True, depth=1):
    """The one map. Every page draws the same geography and adds its own layer.

    Every stitched chain is drawn, not just the longest: a route number goes missing for a
    few hundred metres at roundabouts and through town centres, and drawing only the longest
    run would leave the circuit visibly open where it is not."""
    p = geo.Proj(box=BOX, width=width)
    out = [f'<svg viewBox="0 0 {p.width:.0f} {p.height:.0f}" role="img" '
           f'aria-label="Map of the Mae Hong Son loop">']
    # the land: the shaded-relief picture, then the vector water and boundary on top.
    # Both are referenced directly — an <image> pointing at an SVG is isolated and will
    # not fetch anything further, so the terrain cannot live inside basemap.svg.
    r_ = rel(depth)
    out.append(f'<image class="terrain-light" href="{r_}terrain.png" x="0" y="0" '
               f'width="{p.width:.0f}" height="{p.height:.0f}" preserveAspectRatio="none"/>')
    out.append(f'<image class="terrain-dark" href="{r_}terrain-dark.png" x="0" y="0" '
               f'width="{p.width:.0f}" height="{p.height:.0f}" preserveAspectRatio="none"/>')
    if BASE:
        out.append(f'<image href="{r_}basemap.svg" x="0" y="0" '
                   f'width="{p.width:.0f}" height="{p.height:.0f}"/>')
    # every traced road, faint, as context
    for ref, r in ROADS.items():
        for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
            out.append(f'<path class="road" d="{p.path([tuple(c) for c in ln])}"/>')
    # then the circuit itself, as one closed line
    ring = (ITIN.get("ring") or {}).get("line") or []
    if ring and not demand:
        d_ring = p.path([tuple(c) for c in ring])
        out.append(f'<path class="loop-case" d="{d_ring}"/>')
        out.append(f'<path class="loop" d="{d_ring}"><title>The circuit</title></path>')
    if demand:
        for ref, r in CURVES.get("roads", {}).items():
            if r.get("density"):
                out.append(geo.demand_path_layer(p, r["density"]))
    elif not ring:
        for ref, r in ROADS.items():
            for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
                out.append(f'<path class="road-on" d="{p.path([tuple(c) for c in ln])}">'
                           f'<title>Route {ref}</title></path>')
    if highlight:
        for ref in highlight:
            r = ROADS.get(ref) or {}
            for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
                out.append(f'<path class="hilite" d="{p.path([tuple(c) for c in ln])}"/>')
    if pins is None:
        # written-up stops are stars, towns are dots; a waypoint and a destination should
        # not look the same on the page
        starred = [{"lat": n["geo"]["lat"], "lon": n["geo"]["lon"], "name": n["names"]["name"],
                    "cls": ""} for n in NODES
                   if n["type"] in ("stop", "wat", "spring") and n.get("geo")]
        rows = [{"lat": n["geo"]["lat"], "lon": n["geo"]["lon"], "name": n["names"]["name"],
                 "cls": "town"} for n in NODES if n["type"] == "town" and n.get("geo")]
        # everything OpenStreetMap calls a viewpoint or a waterfall, small, underneath —
        # a preview of what there is to stop for, at a density no written-up list reaches
        poi = [{"lat": x["lat"], "lon": x["lon"], "cls": x["kind"],
                "title": x.get("name") or x["kind"]}
               for x in PLACES.get("rows", []) if x["kind"] in ("viewpoint", "waterfall")]
        out.append(geo.dots(p, poi, cls="poi", r=2.1))
        out.append(geo.stars(p, starred, r=5.4))
        out.append(geo.dots(p, rows, r=4.2, label=labels))
    else:
        out.append(geo.dots(p, pins, r=4.2, label=labels))
    out.append(geo.scalebar(p))
    out.append("</svg>")
    return "".join(out)


def tier_chip(p: dict, lang="en") -> str:
    t = (p or {}).get("tier", "")
    return f'<span class="tier {E(t)}">{E(t)}</span>' if t else ""


def prov_block(r: dict, lang: str) -> str:
    ui = UI[lang]
    pv = r.get("provenance") or {}
    rows = [("<em>default</em>", pv.get("default") or {})]
    rows += [(E(k), v) for k, v in (pv.get("fields") or {}).items()]
    body = "".join(
        f"<tr><td>{k}</td><td>{tier_chip(v, lang)}</td>"
        f"<td>{src_link(v.get('source'), lang) if v.get('source') else ''}</td>"
        f"<td class='small mute'>{E(v.get('note') or '')}</td></tr>" for k, v in rows)
    srcs = "".join(f"<li>{src_link(s, lang)}</li>" for s in r.get("sources", []))
    return (f'<details><summary>{E(ui["prov"])}</summary>'
            f'<div class="scroll"><table><thead><tr><th>Field</th><th>Tier</th><th>Source</th><th>Note</th>'
            f'</tr></thead><tbody>{body}</tbody></table></div>'
            f'<h3>{E(ui["sources"])}</h3><ul class="small">{srcs}</ul>'
            f'<p class="small mute">' +
            " · ".join(f"<b>{E(k)}</b> {E(v)}" for k, v in TIER_LABEL.items()) +
            '</p></details>')


def src_link(sid: str, lang="en") -> str:
    s = SOURCES.get(sid)
    if not s:
        return E(sid)
    t = E(s.get("title") or sid)
    pub = E(s.get("publisher") or "")
    if s.get("url"):
        return f'<a href="{E(s["url"])}" rel="noopener">{t}</a>{" — " + pub if pub else ""}'
    return f"{t} — {pub}"


def node_card(n: dict, lang: str, depth: int, n_label=None) -> str:
    r = lroot(lang)
    name = T(n, "names.name", lang)
    th = n["names"].get("th")
    what = T(n, "text.what", lang) or ""
    rt = n.get("route") or {}
    meta = []
    if rt.get("km"):
        meta.append(f'<span class="tag">{rt["km"]} {E(UI[lang]["km"])}</span>')
    if rt.get("curves"):
        meta.append(f'<span class="tag hot">{rt["curves"]} {E(UI[lang]["curves"])}</span>')
    grip = (n.get("riding") or {}).get("grip")
    if grip:
        meta.append(f'<span class="tag">{E(FACETS["grip"]["values"].get(grip, grip))}</span>')
    ims = pictures(n)
    thumb = ""
    if ims:
        im = next((i for i in ims if i.get("primary")), ims[0])
        thumb = (f'<figure class="thumb"><img src="{E(img_url(im, root_depth(depth, lang), thumb=True))}" '
                 f'alt="{E(im.get("alt") or "")}" loading="lazy" decoding="async"></figure>')
    num = f'<span class="n">{n_label}</span>' if n_label else ""
    thai = f'<p class="th">{E(th)}</p>' if th and lang == "en" else ""
    return (f'<article class="card">{num}{thumb}'
            f'<h3><a href="{r}{url_of(n)}">{E(name)}</a></h3>{thai}'
            f'<p>{E(clip(what, 150))}</p>'
            f'<div class="tags">{"".join(meta)}</div></article>')


def clip(t: str, n: int) -> str:
    t = (t or "").strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def credit(im: dict, short=False) -> str:
    """Licence, author and a link to the Commons page — beside the picture, every time.
    Share-alike is complied with rather than avoided, so the terms travel with the file."""
    who = E(im.get("author") or "unknown")
    lic = E(im.get("license") or "")
    page = im.get("page_url") or ""
    lic_html = f'<a href="{E(im["license_url"])}" rel="license noopener">{lic}</a>' if im.get("license_url") else lic
    src = f'<a href="{E(page)}" rel="noopener">Commons</a>' if page else "Commons"
    if short:
        return f"{who} · {lic_html}"
    return f"{who} · {lic_html} · {src}"


def root_depth(depth: int, lang: str) -> int:
    """Depth below the SITE root. Body links count from the language root; anything that
    lives once at the top — images, the API, the machine files — needs this instead."""
    return depth + (1 if lang == "th" else 0)


def img_url(im: dict, depth: int, thumb=False) -> str:
    f = im["file"]
    if thumb:
        f = f.rsplit(".", 1)[0] + ".thumb.jpg"
    return f"{rel(depth)}images/{f}"


def pictures(n: dict) -> list:
    return [i for i in (n.get("images") or []) if i.get("file")]


def hero_shot(n: dict, depth: int) -> str:
    ims = pictures(n)
    if not ims:
        return ""
    im = next((i for i in ims if i.get("primary")), ims[0])
    return (f'<div class="hero-shot"><img src="{E(img_url(im, depth))}" alt="{E(im.get("alt") or "")}" '
            f'loading="lazy" decoding="async">'
            f'<span class="cap">{credit(im, short=True)}</span></div>')


def shot_strip(ims: list, depth: int) -> str:
    if not ims:
        return ""
    out = ['<div class="strip">']
    for im in ims:
        out.append(f'<figure><img src="{E(img_url(im, depth, thumb=True))}" '
                   f'alt="{E(im.get("alt") or "")}" loading="lazy" decoding="async">'
                   f'<figcaption>{credit(im, short=True)}</figcaption></figure>')
    out.append("</div>")
    return "".join(out)


# The front page's band is an invitation, so it is chosen by subject rather than by
# whatever sorts first: places and scenery ahead of roads, and a named shortlist ahead of
# everything. A picture of an airport apron is a true picture of Mae Hong Son and a poor
# argument for going there.
GALLERY_FIRST = ["pang-ung", "ban-rak-thai", "bua-tong-bloom", "doi-kong-mu", "pai",
                 "tham-lot", "mae-surin-waterfall", "doi-inthanon", "op-luang",
                 "chong-kham-chong-klang", "poy-sang-long", "pai-canyon", "cool-season",
                 "mae-hong-son", "the-rains", "mae-sariang"]
GALLERY_TYPES = ("stop", "wat", "town", "event", "leg")


def gallery_pool(limit=8) -> list:
    """One picture per record, best subjects first, capped at `limit`."""
    out, seen = [], set()
    for rid in GALLERY_FIRST:
        n = BY_ID.get(rid)
        ims = pictures(n) if n else []
        if ims:
            out.append((n, next((i for i in ims if i.get("primary")), ims[0])))
            seen.add(rid)
    for n in NODES:
        if len(out) >= limit:
            break
        if n["id"] in seen or n["type"] not in GALLERY_TYPES:
            continue
        ims = pictures(n)
        if ims:
            out.append((n, next((i for i in ims if i.get("primary")), ims[0])))
    return out[:limit]


# ---------------------------------------------------------------- node page
def node_page(n: dict, lang: str) -> str:
    ui = UI[lang]
    depth = 2
    r = lroot(lang)
    ti = TYPE_INFO[n["type"]]
    name = T(n, "names.name", lang)
    kind = ti["th"] if lang == "th" else ti["name"]
    said = T(n, "names.said", lang)
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}{url_of(n)}"
    rdepth = root_depth(depth, lang)
    b = [f'<h1><span class="kind">{E(kind)}</span>{E(name)}</h1>']
    if lang == "en" and n["names"].get("th"):
        b.append(f'<p class="said th">{E(n["names"]["th"])}'
                 f'{" · " + E(n["names"]["rtgs"]) if n["names"].get("rtgs") else ""}</p>')
    if said:
        b.append(f'<p class="said">{E(said)}</p>')
    if n.get("needs_verification"):
        b.append(f'<div class="warn">{E(ui["unverified"])}</div>')
    ims = pictures(n)
    if ims:
        b.append(hero_shot(n, rdepth))

    # the route slab, for legs and roads
    rt = n.get("route") or {}
    if rt:
        cells = []
        if rt.get("km"):
            cells.append((f'{rt["km"]}', ui["km"]))
        if rt.get("curves"):
            cells.append((f'{rt["curves"]}', ui["curves"]))
        if rt.get("hairpins"):
            cells.append((f'{rt["hairpins"]}', ui["hairpins"]))
        if rt.get("hours"):
            cells.append((rt["hours"], ui["hours"]))
        if rt.get("fuel_gap_km"):
            cells.append((f'{rt["fuel_gap_km"]:g}', "km fuel gap" if lang == "en" else "กม. ไม่มีปั๊ม"))
        if cells:
            b.append('<div class="slab">' + "".join(
                f"<div><b>{E(v)}</b><span>{E(l)}</span></div>" for v, l in cells) + "</div>")
        if rt.get("cw") or rt.get("ccw"):
            cw = T(rt, "cw", lang) if lang == "th" else rt.get("cw")
            ccw = T(rt, "ccw", lang) if lang == "th" else rt.get("ccw")
            cw = (rt.get("cw_th") if lang == "th" else None) or rt.get("cw")
            ccw = (rt.get("ccw_th") if lang == "th" else None) or rt.get("ccw")
            b.append(f'<h2>{E(ui["route"])}</h2>'
                     f'<div class="grid">'
                     f'<article class="card"><h3>↻ {E(ui["cw"])}</h3><p>{E(cw or "")}</p></article>'
                     f'<article class="card"><h3>↺ {E(ui["ccw"])}</h3><p>{E(ccw or "")}</p></article>'
                     f'</div>')
        if rt.get("roads"):
            b.append('<figure class="map">' + base_map(820, highlight=rt["roads"], depth=rdepth) +
                     f'<figcaption>{E("Highlighted: " + ", ".join("Route " + x for x in rt["roads"]) if lang == "en" else "เน้น: " + ", ".join("ทางหลวง " + x for x in rt["roads"]))} · '
                     f'{MAP_CREDIT}</figcaption></figure>')

    if n.get("geo"):
        g = n["geo"]
        b.append('<figure class="map">' + base_map(
            820, pins=[{"lat": g["lat"], "lon": g["lon"], "name": name, "cls": "town"}],
            labels=True, depth=rdepth) +
            f'<figcaption>{g["lat"]:.4f}, {g["lon"]:.4f}'
            f'{" · " + str(g["elevation_m"]) + " m" if g.get("elevation_m") else ""} · '
            f'{MAP_CREDIT}</figcaption></figure>')

    # prose
    for key, label in (("what", ui["what"]), ("story", ui["story"]), ("how", ui["how"]), ("today", ui["today"])):
        txt = T(n, f"text.{key}", lang, fallback=False)
        miss = False
        if txt is None:
            txt = (n.get("text") or {}).get(key)
            miss = lang == "th" and bool(txt)
        if not txt:
            continue
        b.append(f'<h2>{E(label)}</h2>')
        if miss:
            b.append(f'<div class="warn">{E(ui["no_th"])}</div>')
        b.append(f'<div class="prose">{prose(txt)}</div>')

    rest = [i for i in ims if not i.get("primary")][:3] if ims else []
    if not rest and len(ims) > 1:
        rest = ims[1:4]
    if rest:
        b.append(shot_strip(rest, rdepth))

    rd = n.get("riding") or {}
    if rd:
        rows = []
        if rd.get("min_class"):
            rows.append((FACETS["class"]["values"].get(rd["min_class"], rd["min_class"]),
                         "Smallest sensible bike" if lang == "en" else "รถเล็กที่สุดที่สมเหตุสมผล"))
        if rd.get("grip"):
            rows.append((FACETS["grip"]["values"].get(rd["grip"], rd["grip"]),
                         "Difficulty" if lang == "en" else "ความยาก"))
        if rd.get("pillion"):
            rows.append(({"fine": "Fine", "think": "Think about it", "no": "No"}.get(rd["pillion"], rd["pillion"])
                         if lang == "en" else
                         {"fine": "ได้", "think": "คิดก่อน", "no": "ไม่ควร"}.get(rd["pillion"], rd["pillion"]),
                         "Pillion" if lang == "en" else "คนซ้อน"))
        note = (rd.get("note_th") if lang == "th" else None) or rd.get("note")
        b.append(f'<h2>{E(ui["riding"])}</h2><div class="scroll"><table><tbody>' +
                 "".join(f"<tr><th>{E(l)}</th><td>{E(v)}</td></tr>" for v, l in rows) +
                 "</tbody></table></div>")
        if note:
            b.append(f"<p>{marks(note)}</p>")
        if rd.get("loaded"):
            b.append(f'<p class="mute">{marks(rd["loaded"])}</p>')

    seas = n.get("seasons") or {}
    if seas:
        b.append(f'<h2>{E(ui["season"])}</h2><div class="grid">')
        for k, v in seas.items():
            lab = FACETS["month"]["values"].get(k, k)
            note = (v.get("note_th") if lang == "th" else None) or v.get("note")
            why = (v.get("why_th") if lang == "th" else None) or v.get("why")
            whyhtml = f'<p class="mute small">{E(why)}</p>' if why else ""
            d = v.get("direction")
            dirhtml = (f'<div class="tags"><span class="tag hot">{E(ui.get(d, d))}</span></div>'
                       if d and d != "either" else "")
            b.append(f'<article class="card"><h3>{E(lab)}</h3><p>{E(note or "")}</p>'
                     f'{whyhtml}{dirhtml}</article>')
        b.append("</div>")

    # kin, both directions
    if n.get("kin"):
        b.append(f'<h2>{E(ui["kin"])}</h2><ul class="kin">')
        for k in n["kin"]:
            t = BY_ID.get(k["to"])
            if not t:
                continue
            b.append(f'<li><span class="rel">{E(k["rel"])}</span>'
                     f'<a href="{r}{url_of(t)}">{E(T(t, "names.name", lang))}</a> — {E(k["as"])}</li>')
        b.append("</ul>")
    if n.get("kin_in"):
        b.append(f'<h2>{E(ui["said_here"])}</h2><ul class="kin">')
        for k in n["kin_in"]:
            t = BY_ID.get(k["from"])
            if not t:
                continue
            b.append(f'<li><span class="rel">{E(k["type"])}</span>'
                     f'<a href="{r}{url_of(t)}">{E(T(t, "names.name", lang))}</a> — {E(k["as"])}</li>')
        b.append("</ul>")

    b.append(share_row(url, name, lang))
    b.append(prov_block(n, lang))

    ld = [{"@context": "https://schema.org", "@type": "Article",
           "headline": name, "inLanguage": lang, "url": url,
           "description": clip(T(n, "text.what", lang) or "", 200),
           "author": AUTHOR, "license": DATA_LICENSE, "dateModified": n.get("updated"),
           "isPartOf": {"@type": "WebSite", "name": NAME[lang], "url": SITE_URL}}]
    if n.get("geo"):
        ld.append({"@context": "https://schema.org", "@type": "Place", "name": name,
                   "geo": {"@type": "GeoCoordinates", "latitude": n["geo"]["lat"],
                           "longitude": n["geo"]["lon"]}})
    card_name = f'{n["type"]}-{n["id"]}' if pictures(n) else "index"
    return page(f"{name} — {NAME[lang]}", "".join(b), depth, lang,
                clip(T(n, "text.what", lang) or "", 180), ld, url, path=url_of(n),
                card=card_name)


# ---------------------------------------------------------------- parallax bands
# Hand-picked backgrounds. A Commons search returns a lot that is true and useless — the
# `shan` query came back with a Laotian waterfall and a museum knife — so the pictures
# that get to be a full-width band are named here rather than taken from whatever sorts
# first. Each entry is (record id, filename fragment); the fragment must match one file.
BANDS = {
    "pano-chaem":  ("the-1263-cut", "2013-pano-mae-chaem-district-1"),
    "pano-chaem2": ("the-1263-cut", "2013-pano-mae-chaem-district-2"),
    "road-1263":   ("the-1263-cut", "chiang-mai-province-road-1263"),
    "pai-canyon":  ("pai", "pai-canyon"),
    "cnx-pano":    ("chiang-mai", "panoramic-view-of-chiang-mai-city"),
    "ban-rak-thai": ("ban-rak-thai", "125159307"),
    "ban-rak-thai2": ("ban-rak-thai", "125159295"),
    "op-luang":    ("op-luang", "aoblaung01"),
    "pang-ung":    ("pang-ung", ""),
    "bua-tong":    ("bua-tong-bloom", ""),
    "doi-kong-mu": ("doi-kong-mu", ""),
    "smoke":       ("the-smoke", "burning-mountains"),
    "rains":       ("the-rains", ""),
    "tham-lot":    ("tham-lot", ""),
    "inthanon":    ("doi-inthanon", ""),
    "mhs":         ("mae-hong-son", ""),
    "mae-surin":   ("mae-surin-waterfall", ""),
    "poy":         ("poy-sang-long", ""),
}


def band_image(key: str):
    rid, frag = BANDS.get(key, (None, None))
    n = BY_ID.get(rid or "")
    ims = pictures(n) if n else []
    if not ims:
        return None
    if frag:
        for im in ims:
            if frag in im["file"]:
                return im
    return next((i for i in ims if i.get("primary")), ims[0])


def band(key: str, kicker: str, head: str, line: str = "", depth: int = 0, lang: str = "en",
         big: str = "", big_label: str = "", href: str = "", cta: str = "",
         cls: str = "") -> str:
    """One full-bleed parallax band. Returns "" when the picture is missing, so a band
    never ships as an empty black strip."""
    im = band_image(key)
    if not im:
        return ""
    url = img_url(im, depth)
    inner = [f'<span class="kicker">{E(kicker)}</span>']
    if big:
        inner.append(f'<p class="big">{E(big)}'
                     f'{f"<small>{E(big_label)}</small>" if big_label else ""}</p>')
    if head:
        inner.append(f"<h2>{E(head)}</h2>")
    if line:
        inner.append(f"<p>{E(line)}</p>")
    if href and cta:
        inner.append(f'<a class="btn" href="{E(href)}">{E(cta)}</a>')
    return (f'<section class="band {cls}" style="background-image:url({E(url)})">'
            f'<div class="in">{"".join(inner)}</div>'
            f'<span class="cred">{credit(im, short=True)}</span></section>')


# ---------------------------------------------------------------- the direction switch
DIRJS = """
<script>
document.addEventListener('DOMContentLoaded',function(){
 function q(s,r){return Array.prototype.slice.call((r||document).querySelectorAll(s))}
 var KEY='mhs-dir';
 function set(d,push){
  q('.dirsw button').forEach(function(b){b.setAttribute('aria-pressed',b.dataset.dir===d)});
  q('[data-dir]').forEach(function(el){
    if(el.tagName==='BUTTON')return;
    el.hidden = el.dataset.dir!==d;});
  var list=document.getElementById('legs');
  if(list){var li=q('li',list);li.sort(function(a,b){
    var x=+a.dataset.order,y=+b.dataset.order;return d==='ccw'?y-x:x-y});
    li.forEach(function(n,i){list.appendChild(n);
      var num=n.querySelector('.num'); if(num)num.textContent=(i+1)+'.'});}
  try{localStorage.setItem(KEY,d)}catch(e){}
  if(push){var u=new URL(location);u.searchParams.set('dir',d);history.replaceState({},'',u)}
 }
 var init=new URLSearchParams(location.search).get('dir');
 if(!init){try{init=localStorage.getItem(KEY)}catch(e){}}
 set(init==='ccw'?'ccw':'cw',false);
 q('.dirsw button').forEach(function(b){b.addEventListener('click',function(){set(b.dataset.dir,true)})});
 q('[data-copy]').forEach(function(b){b.addEventListener('click',function(){
   navigator.clipboard&&navigator.clipboard.writeText(b.dataset.copy);
   var t=b.textContent;b.textContent='✓';setTimeout(function(){b.textContent=t},1200)})});
});
</script>
"""


def dirsw(lang: str) -> str:
    ui = UI[lang]
    return (f'<div class="dirsw" role="group" aria-label="Direction">'
            f'<button type="button" data-dir="cw" aria-pressed="true">↻ {E(ui["cw"])}</button>'
            f'<button type="button" data-dir="ccw" aria-pressed="false">↺ {E(ui["ccw"])}</button>'
            f'</div>'
            f'<p class="dirnote" data-dir="cw">{E(ITIN["cw"]["note"] if lang == "en" else "ขึ้นเหนือก่อน ไปตามทางหลวง 107 และ 1095 สู่ปาย ต่อไปแม่ฮ่องสอน แล้วลงใต้ตามทางหลวง 108 กลับบ้าน")}</p>'
            f'<p class="dirnote" data-dir="ccw" hidden>{E(ITIN["ccw"]["note"] if lang == "en" else "ลงใต้ก่อน ไปตามทางหลวง 108 สู่ฮอดและแม่สะเรียง ขึ้นไปแม่ฮ่องสอน แล้วกลับทางถนนโค้ง 1095")}</p>')


def leg_list(lang: str, depth: int) -> str:
    r = lroot(lang)
    ui = UI[lang]
    out = ['<ol class="legs" id="legs">']
    for i, l in enumerate(ITIN["legs"], 1):
        n = BY_ID[l["id"]]
        meta = " · ".join(filter(None, [
            f'{l["km"]} {ui["km"]}' if l.get("km") else "",
            f'{l["curves"]} {ui["curves"]}' if l.get("curves") else "",
            f'{l["hairpins"]} {ui["hairpins"]}' if l.get("hairpins") else "",
            f'{l["hours"]} {ui["hours"]}' if l.get("hours") else ""]))
        cw = l.get("cw_th") if lang == "th" else l.get("cw")
        ccw = l.get("ccw_th") if lang == "th" else l.get("ccw")
        out.append(
            f'<li data-order="{i}"><div class="hd"><span class="num">{i}.</span>'
            f'<a href="{r}{url_of(n)}">{E(T(n, "names.name", lang))}</a>'
            f'<span class="meta">{E(meta)}</span></div>'
            f'<p data-dir="cw">{E(cw or "")}</p>'
            f'<p data-dir="ccw" hidden>{E(ccw or "")}</p></li>')
    out.append("</ol>")
    return "".join(out)


# ---------------------------------------------------------------- front page
def front(lang: str) -> str:
    ui = UI[lang]
    r = lroot(lang)
    d0 = root_depth(0, lang)
    cur = CURVES.get("roads", {}).get("1095", {}).get("whole", {})
    n_stop = sum(1 for n in NODES if n["type"] in ("stop", "wat", "spring"))
    b = [f'<h1><span class="kind">{E("Northern Thailand · 600 km" if lang == "en" else "ภาคเหนือ · 600 กม.")}</span>'
         f'{E(NAME[lang])}</h1>',
         f'<p class="lede">{E(TAG[lang])}</p>']
    b.append('<div class="slab">'
             f'<div><b>~600</b><span>{E(ui["km"])}</span></div>'
             f'<div><b>1,864</b><span>{E("curves, Chiang Mai to Mae Hong Son" if lang == "en" else "โค้ง เชียงใหม่ถึงแม่ฮ่องสอน")}</span></div>'
             f'<div><b>{cur.get("hairpins", "—")}</b><span>{E(ui["hairpins"])}</span></div>'
             f'<div><b>4–5</b><span>{E(ui["days"])}</span></div>'
             f'<div><b>{PLACES.get("count", 0):,}</b><span>{E("places mapped" if lang == "en" else "สถานที่บนแผนที่")}</span></div>'
             '</div>')
    b.append(f'<div class="btns"><a class="btn" href="{r}quiz/">{E("Which ride is yours?" if lang == "en" else "คุณควรขี่แบบไหน")}</a>'
             f'<a class="btn alt" href="{r}which-way/">{E("Clockwise or not?" if lang == "en" else "ตามเข็มหรือทวนเข็ม")}</a>'
             f'<a class="btn alt" href="{r}good/">{E("The good part" if lang == "en" else "ส่วนที่ดี")}</a>'
             f'<a class="btn alt" href="{r}air/">{E("When to go" if lang == "en" else "ควรไปเมื่อไหร่")}</a></div>')
    pool = gallery_pool()
    if pool:
        b.append(shot_strip([im for _, im in pool[:8]], root_depth(0, lang)))
    b.append('<figure class="map">' + base_map(880, demand=True, depth=d0) +
             f'<figcaption>{E("Coloured by how much steering each 2 km asks for — not a crash map." if lang == "en" else "สีบอกว่าทุก 2 กม. ต้องบังคับรถมากแค่ไหน ไม่ใช่แผนที่อุบัติเหตุ")} '
             f'{MAP_CREDIT}</figcaption></figure>')
    b.append('<div class="legend">' + "".join(
        f'<span><i style="background:var(--{k})"></i>{E(v if lang == "en" else v)}</span>'
        for k, v in (("g", "under 2 curves/km"), ("b", "2–4"), ("h", "4–6"), ("r", "over 6"))) +
        f'<span><svg width="14" height="14" viewBox="0 0 14 14" style="vertical-align:-.15em">'
        f'<polygon class="star" points="{geo.star(7, 7, 6)}"/></svg> '
        f'{E("a stop" if lang == "en" else "จุดแวะ")}</span>' +
        f'<span><svg width="12" height="12" viewBox="0 0 12 12" style="vertical-align:-.1em">'
        f'<circle class="dot town" cx="6" cy="6" r="4"/></svg> '
        f'{E("a town" if lang == "en" else "เมือง")}</span>' + "</div>")
    b.append(band("pano-chaem", "Mae Chaem" if lang == "en" else "แม่แจ่ม",
                  "Six hundred kilometres of this" if lang == "en" else "หกร้อยกิโลเมตรแบบนี้",
                  "Chiang Mai out, Pai, Mae Hong Son, Mae Sariang, home. Four days if you hurry."
                  if lang == "en" else "ออกจากเชียงใหม่ ปาย แม่ฮ่องสอน แม่สะเรียง กลับบ้าน สี่วันถ้ารีบ",
                  d0, lang, href=f"{r}legs/", cta="Every leg" if lang == "en" else "ทุกช่วง"))
    b.append(f'<h2>{E(ui["legs"])}</h2>')
    b.append(dirsw(lang))
    b.append(leg_list(lang, 0))
    b.append(f'<p><a class="btn alt" href="{r}legs/">{E("Every leg, in full" if lang == "en" else "ทุกช่วง แบบเต็ม")}</a></p>')

    b.append(band("road-1263", "Route 1263" if lang == "en" else "ทางหลวง 1263",
                  "4.25 curves a kilometre" if lang == "en" else "4.25 โค้งต่อกิโลเมตร",
                  "Denser than the road with the T-shirt. No town in between, and no fuel."
                  if lang == "en" else "หนาแน่นกว่าถนนที่มีเสื้อขาย ไม่มีเมืองคั่นกลาง และไม่มีปั๊ม",
                  d0, lang, href=f"{r}leg/the-1263-cut/",
                  cta="The cut" if lang == "en" else "ทางลัด", cls="right"))

    # the three numbers
    claims = CURVES.get("claims", [])
    full = CURVES.get("full_route") or {}
    if full:
        b.append(f'<h2>{E("1,864 curves" if lang == "en" else "1,864 โค้ง")}</h2>'
                 f'<div class="prose"><p>' +
                 (f'Over the <strong>245 km</strong> from Chiang Mai to Mae Hong Son that is one every '
                  f'<strong>131 metres</strong>. Counting every change of turning direction on the map '
                  f'gets to <strong>{full["bends_scaled_to_published"]:,}</strong> from below — and the map '
                  f'has a point only every 31 metres, so it cannot see a bend shorter than sixty. '
                  f'The number is the right size.'
                  if lang == "en" else
                  f'บนระยะ <strong>245 กม.</strong> จากเชียงใหม่ถึงแม่ฮ่องสอน คิดเป็นหนึ่งโค้งทุก '
                  f'<strong>131 เมตร</strong> การนับทุกครั้งที่ทิศการเลี้ยวเปลี่ยนบนแผนที่ได้ '
                  f'<strong>{full["bends_scaled_to_published"]:,}</strong> โดยเข้าจากด้านล่าง และแผนที่มีจุดทุก 31 เมตร '
                  f'จึงมองไม่เห็นโค้งที่สั้นกว่าหกสิบเมตร ตัวเลขนี้อยู่ในขนาดที่ถูกต้อง') +
                 f'</p></div><p><a class="btn alt" href="{r}numbers/">{E("Every road, counted" if lang == "en" else "ทุกสาย นับแล้ว")}</a></p>')

    b.append(band("smoke", "March and April" if lang == "en" else "มีนาคมและเมษายน",
                  "Two months this has a reason not to happen"
                  if lang == "en" else "สองเดือนที่ทริปนี้มีเหตุผลที่จะไม่เกิด",
                  "Pai measures 3.0 µg/m³ in July and 29.8 in April. Four seasons of daily figures."
                  if lang == "en" else "ปายวัดได้ 3.0 ในเดือนกรกฎาคม และ 29.8 ในเดือนเมษายน ข้อมูลรายวันสี่ฤดู",
                  d0, lang, big="×9.9", big_label=("Pai, July to April" if lang == "en" else "ปาย ก.ค. ถึง เม.ย."),
                  href=f"{r}air/", cta="The air" if lang == "en" else "เรื่องอากาศ"))

    # air strip
    pai = next((p for p in AIR.get("points", []) if p["id"] == "pai"), None)
    if pai:
        b.append(f'<h2>{E("The air, by month" if lang == "en" else "อากาศ รายเดือน")}</h2>')
        b.append(month_strip(pai, lang))
        b.append(f'<p class="small mute">{E("Pai, mean PM2.5 µg/m³, four burning seasons. July 3.0 · April 29.8." if lang == "en" else "ปาย ค่าเฉลี่ย PM2.5 ไมโครกรัม/ลบ.ม. สี่ฤดูเผา กรกฎาคม 3.0 เมษายน 29.8")}</p>')
        b.append(f'<p><a class="btn alt" href="{r}air/">{E("Every town, every month" if lang == "en" else "ทุกเมือง ทุกเดือน")}</a></p>')

    b.append(band("pang-ung", "Pang Ung, before six" if lang == "en" else "ปางอุ๋ง ก่อนหกโมง",
                  "Which ride is yours?" if lang == "en" else "คุณควรขี่แบบไหน",
                  "Seven questions. Seventeen answers. Nobody gets the same loop."
                  if lang == "en" else "เจ็ดคำถาม สิบเจ็ดคำตอบ ไม่มีใครได้วงรอบเหมือนกัน",
                  d0, lang, href=f"{r}quiz/", cta="Take it" if lang == "en" else "เริ่มเลย",
                  cls="right tall"))

    # the doors
    b.append(f'<h2>{E("Everything else" if lang == "en" else "อย่างอื่นทั้งหมด")}</h2><div class="grid">')
    for t in ("stop", "wat", "dish", "coffee", "spring", "stay", "town", "bike", "kit",
              "event", "hazard", "term", "story"):
        ti = TYPE_INFO[t]
        n = sum(1 for x in NODES if x["type"] == t)
        if not n:
            continue
        b.append(f'<article class="card"><h3><a href="{r}{DIR_OF[t]}/">'
                 f'{E(ti["th"] if lang == "th" else ti["name"])} ({n})</a></h3>'
                 f'<p>{E(clip(ti["th_blurb"] if lang == "th" else ti["blurb"], 130))}</p></article>')
    b.append("</div>")
    b.append(share_row(SITE_URL + ("/th/" if lang == "th" else "/"), NAME[lang], lang))

    ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": NAME[lang],
           "url": SITE_URL, "inLanguage": lang, "description": TAG[lang], "author": AUTHOR,
           "license": DATA_LICENSE,
           "publisher": fleet.publisher_ld(roster=ROSTER),
           "sameAs": fleet.same_as(SELF, roster=ROSTER)},
          fleet.catalog_ld(roster=ROSTER)]
    return page(f"{NAME[lang]} — {TAG[lang]}", "".join(b), 0, lang, TAG[lang], ld,
                SITE_URL + ("/th/" if lang == "th" else "/"), head=DIRJS, cur="home", path="", card="index")


def month_strip(pt: dict, lang: str) -> str:
    out = ['<div class="months">']
    for k, en, th in MONTHS:
        v = pt["months"].get(k)
        out.append(f'<div class="{aqi_class(v)}"><span class="m">{E(th if lang == "th" else en)}</span>'
                   f'{v if v is not None else "—"}</div>')
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------- which way round
SEASON_GRID = [
  # key, EN label, TH label, cw case, ccw case, verdict
  ("cool", "Cool and dry · Nov–Feb", "หนาวและแห้ง · พ.ย.–ก.พ.",
   "Dry tarmac on every descent, and the hardest riding done on day one while fresh.",
   "The westward run into Mae Hong Son happens in the morning with the sun behind you, instead of head-on into a low afternoon sun.",
   "ccw", "The low sun is a real, physical argument and this is the season it bites. Counter-clockwise, narrowly."),
  ("smoke", "Burning season · Mar–Apr", "ช่วงเผา · มี.ค.–เม.ย.",
   "Pai — the mildest measured air on the circuit in March — is reached on the afternoon of day one and left behind.",
   "The high sections come later in the trip, and mornings are always clearer than afternoons.",
   "either", "Direction barely matters. The clock does: ride early, stop by two. Or move the trip to May."),
  ("rains", "The rains · Jun–Oct", "หน้าฝน · มิ.ย.–ต.ค.",
   "The technical descent into Pai is ridden on day one, before four days of wet roads have worn you down.",
   "A long, forgiving first day on Route 108 lets you learn how a rented bike behaves in the wet before the hairpins.",
   "ccw", "Wet roads reward knowing the bike. Take the easy road first. And drop the 1263 either way."),
  ("hot", "Hot · Mar–May", "ร้อน · มี.ค.–พ.ค.",
   "The low, shadeless Chiang Mai–Hot section is ridden last, at the end of the trip.",
   "That same hot low section is ridden first — which is worse in the afternoon and fine before eleven.",
   "cw", "Clockwise keeps you high and cool for the first three days. Do the low ground early or late, never at two."),
]


def which_way(lang: str) -> str:
    ui = UI[lang]
    b = [f'<h1><span class="kind">{E("The argument" if lang == "en" else "ข้อถกเถียง")}</span>'
         f'{E("Which way round?" if lang == "en" else "ไปทางไหนดี")}</h1>',
         f'<p class="lede">{E("Both. The question is which one, in which month — and the season changes the answer." if lang == "en" else "ได้ทั้งสองทาง คำถามคือทางไหนในเดือนไหน และฤดูกาลเปลี่ยนคำตอบ")}</p>']
    d1 = root_depth(1, lang)
    b.append(band("cnx-pano", "Chiang Mai" if lang == "en" else "เชียงใหม่",
                  "Same road. Two rides." if lang == "en" else "ถนนเดียวกัน แต่เป็นสองการเดินทาง",
                  "North first up the curves, or south first down the long one."
                  if lang == "en" else "ขึ้นเหนือเจอโค้งก่อน หรือลงใต้เจอทางยาวก่อน", d1, lang))
    b.append(dirsw(lang))
    b.append('<figure class="map">' + base_map(880, depth=root_depth(1, lang)) +
             f'<figcaption>{E("Same road, either direction." if lang == "en" else "ถนนเดียวกัน ไปได้ทั้งสองทาง")} {MAP_CREDIT}</figcaption></figure>')
    b.append(leg_list(lang, 1))
    b.append(band("bua-tong", "Doi Mae U-Kho, November" if lang == "en" else "ดอยแม่อูคอ พฤศจิกายน",
                  "The season picks the direction" if lang == "en" else "ฤดูกาลเป็นคนเลือกทิศ",
                  "Light, smoke, water and what is flowering. Each one argues for a different way round."
                  if lang == "en" else "แสง ควัน น้ำ และดอกไม้ แต่ละอย่างเถียงเข้าข้างคนละทิศ",
                  d1, lang, cls="right"))
    b.append(f'<h2>{E("Season by direction" if lang == "en" else "ฤดูกาลกับทิศทาง")}</h2>')
    b.append('<div class="scroll"><table><thead><tr>'
             f'<th>{E("Season" if lang == "en" else "ฤดู")}</th>'
             f'<th>↻ {E(ui["cw"])}</th><th>↺ {E(ui["ccw"])}</th>'
             f'<th>{E("Leans" if lang == "en" else "เอนไปทาง")}</th></tr></thead><tbody>')
    for key, en, th, cw, ccw, lean, why in SEASON_GRID:
        lab = {"cw": ui["cw"], "ccw": ui["ccw"], "either": "Either" if lang == "en" else "ได้ทั้งสอง"}[lean]
        b.append(f'<tr><th>{E(th if lang == "th" else en)}</th>'
                 f'<td>{E(cw)}</td><td>{E(ccw)}</td>'
                 f'<td><span class="tag {"hot" if lean != "either" else ""}">{E(lab)}</span>'
                 f'<div class="small mute">{E(why)}</div></td></tr>')
    b.append("</tbody></table></div>")
    warn_en = ("These are arguments, not findings. The road facts underneath them are sourced "
               "on each leg page; the reasoning on top of them is this project's own.")
    warn_th = ("นี่คือข้อโต้แย้ง ไม่ใช่ข้อค้นพบ ข้อเท็จจริงเรื่องถนนที่อยู่ข้างใต้มีแหล่งอ้างอิงในหน้าของแต่ละช่วง "
               "ส่วนการให้เหตุผลข้างบนเป็นของโครงการนี้")
    b.append(f'<div class="warn">{E(warn_en if lang == "en" else warn_th)}</div>')
    for sid in ("which-way-round", "season-and-direction"):
        n = BY_ID.get(sid)
        if n:
            b.append(f'<h2>{E(T(n, "names.name", lang))}</h2>'
                     f'<div class="prose">{prose(T(n, "text.story", lang))}</div>'
                     f'<p><a class="btn alt" href="{lroot(lang)}{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}which-way/"
    b.append(share_row(url, "Which way round the Mae Hong Son loop?", lang))
    return page(f'{"Which way round?" if lang == "en" else "ไปทางไหนดี"} — {NAME[lang]}',
                "".join(b), 1, lang,
                "Clockwise or counter-clockwise, argued by season.", None, url, head=DIRJS,
                cur="which", path="which-way/", card="which-way")


# ---------------------------------------------------------------- numbers
def numbers(lang: str) -> str:
    b = [f'<h1><span class="kind">{E("Measured" if lang == "en" else "วัดแล้ว")}</span>'
         f'{E("The numbers" if lang == "en" else "ตัวเลข")}</h1>',
         f'<p class="lede">{E("What you actually did, per road and per leg, so you can say it with a figure attached." if lang == "en" else "สิ่งที่คุณทำมาจริงๆ แยกตามสายและตามช่วง พร้อมตัวเลขให้อ้างอิง")}</p>']
    d1 = root_depth(1, lang)
    b.append(band("pai-canyon", "Pai" if lang == "en" else "ปาย",
                  "", "", d1, lang, big="1,864",
                  big_label=("curves, Chiang Mai to Mae Hong Son"
                             if lang == "en" else "โค้ง เชียงใหม่ถึงแม่ฮ่องสอน")))
    claims = CURVES.get("claims", [])
    b.append('<div class="grid">')
    for c in claims:
        b.append(f'<article class="card"><h3>{"more than " if c.get("qualifier") else ""}{c["figure"]:,}</h3>'
                 f'<p>{E(c["of"])} — {E(c["carried_by"])}</p>'
                 f'<p class="small mute">{E("Method: " + c["method"] if lang == "en" else "วิธี: " + c["method"])}</p>'
                 + (f'<p class="small">{E("Implies a curve every " + str(c["implies_metres_per_curve"]) + " m" if lang == "en" else "หมายถึงโค้งทุก " + str(c["implies_metres_per_curve"]) + " เมตร")}</p>'
                    if c.get("implies_metres_per_curve") else "") + '</article>')
    r95 = CURVES.get("roads", {}).get("1095", {})
    if r95:
        w = r95["whole"]
        b.append(f'<article class="card"><h3>{w["curves"]:,}</h3>'
                 f'<p>{E("Route 1095, whole road — counted off the OpenStreetMap trace" if lang == "en" else "ทางหลวง 1095 ทั้งสาย นับจากเส้นทางใน OpenStreetMap")}</p>'
                 f'<p class="small mute">{E("Method: printed below" if lang == "en" else "วิธี: อยู่ด้านล่าง")}</p>'
                 f'<p class="small">{E("A curve every " + str(w["metres_per_curve"]) + " m" if lang == "en" else "โค้งทุก " + str(w["metres_per_curve"]) + " เมตร")}</p></article>')
    b.append("</div>")

    b.append(f'<h2>{E("Every road, measured" if lang == "en" else "ทุกสาย วัดแล้ว")}</h2>')
    b.append('<div class="scroll"><table><thead><tr>'
             f'<th>{E("Road" if lang == "en" else "สาย")}</th><th class="num">km</th>'
             f'<th class="num">{E("Curves, at least" if lang == "en" else "โค้ง อย่างน้อย")}</th>'
             f'<th class="num">{E("Hairpins" if lang == "en" else "หักศอก")}</th>'
             f'<th class="num">{E("Per km" if lang == "en" else "ต่อ กม.")}</th>'
             f'<th class="num">{E("One every" if lang == "en" else "ทุก")}</th></tr></thead><tbody>')
    for ref, rr in sorted(CURVES.get("roads", {}).items(),
                          key=lambda kv: -kv[1]["whole"]["per_km"]):
        w = rr["whole"]
        b.append(f'<tr><th>{E(rr["th"] if lang == "th" else rr["name"])}</th>'
                 f'<td class="num">{w["km"]}</td><td class="num">{w["curves"]}</td>'
                 f'<td class="num">{w["hairpins"]}</td><td class="num">{w["per_km"]}</td>'
                 f'<td class="num">{w["metres_per_curve"]} m</td></tr>')
    b.append("</tbody></table></div>")

    if r95.get("spans"):
        b.append(f'<h2>{E("Threshold sensitivity" if lang == "en" else "ผลของเกณฑ์องศา")}</h2>'
                 f'<p>{E("A curve is an arc of at least N degrees. Change N and the count changes. This is the whole argument, made visible." if lang == "en" else "โค้งคือส่วนโค้งที่มีมุมอย่างน้อย N องศา เปลี่ยน N ผลนับก็เปลี่ยน นี่คือข้อถกเถียงทั้งหมด ทำให้เห็นได้")}</p>')
        ths = CURVES.get("thresholds", [15, 25, 35, 45])
        b.append('<div class="scroll"><table><thead><tr><th>Span</th><th class="num">km</th>' +
                 "".join(f'<th class="num">{t}°</th>' for t in ths) + "</tr></thead><tbody>")
        for sp in reversed(r95["spans"]):
            b.append(f'<tr><th>{E(sp["from_name"])} → {E(sp["to_name"])}</th>'
                     f'<td class="num">{sp["km"]}</td>' +
                     "".join(f'<td class="num">{sp["at_threshold"][str(t)]["curves"]}</td>' for t in ths) +
                     "</tr>")
        b.append("</tbody></table></div>")
        b.append(f'<p class="small mute">{E("25° is used everywhere else on this site." if lang == "en" else "ทั้งเว็บนี้ใช้ 25 องศา")}</p>')

    b.append(band("pano-chaem2", "Mae Chaem" if lang == "en" else "แม่แจ่ม",
                  "Change the threshold, change the answer"
                  if lang == "en" else "เปลี่ยนเกณฑ์ ก็เปลี่ยนคำตอบ",
                  "At 15° it is 450. At 45° it is 280. The method is printed so it can be argued with."
                  if lang == "en" else "ที่ 15 องศาได้ 450 ที่ 45 องศาได้ 280 วิธีนับพิมพ์ไว้ให้เถียงได้",
                  d1, lang, cls="right"))
    b.append(f'<h2>{E("The method, and what it cannot see" if lang == "en" else "วิธีนับ และสิ่งที่มันมองไม่เห็น")}</h2>'
             f'<div class="prose"><p>{E(CURVES.get("method", ""))}</p>'
             f'<p><strong>{E(CURVES.get("floor", ""))}</strong></p></div>')
    n = BY_ID.get("how-many-curves")
    if n:
        b.append(f'<div class="prose">{prose(T(n, "text.story", lang))}</div>'
                 f'<p><a class="btn alt" href="{lroot(lang)}{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}numbers/"
    b.append(share_row(url, "How many curves does the Mae Hong Son loop actually have?", lang))
    return page(f'{"The numbers" if lang == "en" else "ตัวเลข"} — {NAME[lang]}', "".join(b), 1, lang,
"1,864 curves between Chiang Mai and Mae Hong Son, counted independently and per road.",
                None, url, cur="numbers", path="numbers/", card="numbers")


# ---------------------------------------------------------------- air
def air_page(lang: str) -> str:
    pts = AIR.get("points", [])
    b = [f'<h1><span class="kind">{E("Measured · " + str(AIR.get("point_days", 0)) + " point-days" if lang == "en" else "วัดแล้ว · " + str(AIR.get("point_days", 0)) + " จุด-วัน")}</span>'
         f'{E("When to go" if lang == "en" else "ควรไปเมื่อไหร่")}</h1>',
         f'<p class="lede">{E("Ten points on the circuit, four years of daily PM2.5. Ten months of the year the answer is yes." if lang == "en" else "สิบจุดบนเส้นทาง ข้อมูล PM2.5 รายวันสี่ปี สิบเดือนในหนึ่งปีคำตอบคือไปได้")}</p>']
    pai = next((p for p in pts if p["id"] == "pai"), None)
    cnx = next((p for p in pts if p["id"] == "chiang-mai"), None)
    if pai and cnx:
        b.append('<div class="slab">'
                 f'<div><b>{pai["months"].get("07")}</b><span>{E("Pai, July µg/m³" if lang == "en" else "ปาย ก.ค.")}</span></div>'
                 f'<div><b>{pai["months"].get("04")}</b><span>{E("Pai, April" if lang == "en" else "ปาย เม.ย.")}</span></div>'
                 f'<div><b>{cnx["months"].get("03")}</b><span>{E("Chiang Mai, March" if lang == "en" else "เชียงใหม่ มี.ค.")}</span></div>'
                 f'<div><b>{len(AIR_NOW.get("mhs_province_stations", []))}</b>'
                 f'<span>{E("official monitor in MHS province" if lang == "en" else "สถานีวัดของรัฐในแม่ฮ่องสอน")}</span></div>'
                 '</div>')
    d1 = root_depth(1, lang)
    b.append(band("rains", "May to October" if lang == "en" else "พฤษภาคมถึงตุลาคม",
                  "Ten months of the year this is some of the cleanest air in Thailand"
                  if lang == "en" else "สิบเดือนในหนึ่งปี อากาศที่นี่สะอาดที่สุดแห่งหนึ่งในประเทศไทย",
                  "Pai measures 3.0 µg/m³ in July. The green months are the clean ones."
                  if lang == "en" else "ปายวัดได้ 3.0 ในเดือนกรกฎาคม เดือนที่เขียวคือเดือนที่สะอาด",
                  d1, lang, big="3.0", big_label="µg/m³ · Pai, July"))
    b.append(f'<h2>{E("Every town, every month" if lang == "en" else "ทุกเมือง ทุกเดือน")}</h2>')
    b.append(f'<p class="small mute">{E("Mean PM2.5 in µg/m³. Green is under the WHO-adjacent 9.0; the US 24-hour standard is 35.4." if lang == "en" else "ค่าเฉลี่ย PM2.5 ไมโครกรัม/ลบ.ม. สีเขียวคือต่ำกว่า 9.0 ส่วนมาตรฐาน 24 ชั่วโมงของสหรัฐฯ คือ 35.4")}</p>')
    for p in pts:
        b.append(f'<h3>{E(p["th"] if lang == "th" else p["name"])}'
                 f'<span class="mute small"> · {E("worst" if lang == "en" else "แย่สุด")} '
                 f'{E(dict((k, en) for k, en, th in MONTHS).get(p["worst_month"], p["worst_month"]))} '
                 f'{p["worst_mean"]} · ×{p["ratio"]} {E("swing" if lang == "en" else "เท่า")}</span></h3>')
        b.append(month_strip(p, lang))
    b.append(band("smoke", "March and April" if lang == "en" else "มีนาคมและเมษายน",
                  "And the two months that are not" if lang == "en" else "และสองเดือนที่ไม่ใช่",
                  "Late February to late April the hills burn, and it ends with the first rains."
                  if lang == "en" else "ปลายกุมภาพันธ์ถึงปลายเมษายนภูเขาถูกเผา และจบเมื่อฝนแรกมา",
                  d1, lang, cls="right"))
    b.append(f'<h2>{E("Right now" if lang == "en" else "ตอนนี้")}</h2>')
    rows = sorted([r for r in AIR_NOW.get("rows", []) if r.get("pm25") is not None],
                  key=lambda r: r["km_from_point"])[:8]
    if rows:
        b.append('<div class="scroll"><table><thead><tr>'
                 f'<th>{E("Station" if lang == "en" else "สถานี")}</th>'
                 f'<th class="num">PM2.5</th><th class="num">AQI</th>'
                 f'<th>{E("Reported" if lang == "en" else "เวลา")}</th></tr></thead><tbody>')
        for r_ in rows:
            b.append(f'<tr><th>{E(r_["name_th"] if lang == "th" else r_["name_en"])}'
                     f'<div class="small mute">{E(r_["area_th"] if lang == "th" else r_["area_en"])}</div></th>'
                     f'<td class="num"><span class="tag {aqi_class(r_["pm25"])}">{r_["pm25"]}</span></td>'
                     f'<td class="num">{r_["aqi"] if r_["aqi"] is not None else "—"}</td>'
                     f'<td class="small">{E(r_["time"])}</td></tr>')
        b.append("</tbody></table></div>")
        b.append(f'<p class="small mute">{E("Fetched " + str(AIR_NOW.get("fetched")) + " when this page was built — it does not update by itself." if lang == "en" else "ดึงข้อมูลเมื่อ " + str(AIR_NOW.get("fetched")) + " ตอนสร้างหน้านี้ และไม่อัปเดตเอง")} '
                 f'<a href="https://air4thai.pcd.go.th/" rel="noopener">air4thai</a></p>')
    b.append(f'<div class="warn"><strong>{E("Two caveats, both load-bearing." if lang == "en" else "ข้อควรระวังสองข้อ สำคัญทั้งคู่")}</strong> '
             f'{E("In " + format(AIR.get("point_days", 0), ",") + " point-days the model never produced a daily mean above " + str(AIR.get("model_ceiling")) + " µg/m³. Ground stations in northern Thailand have recorded far higher: read the seasonal shape from this data, not the ceiling. And Mae Hong Son province — 12,765 km² — has one official monitor, in Mae Hong Son town. Pai, Soppong, Khun Yuam and Mae Sariang have none." if lang == "en" else "ใน " + format(AIR.get("point_days", 0), ",") + " จุด-วัน แบบจำลองไม่เคยให้ค่าเฉลี่ยรายวันเกิน " + str(AIR.get("model_ceiling")) + " เลย สถานีภาคพื้นดินในภาคเหนือเคยวัดได้สูงกว่านั้นมาก ให้อ่านรูปร่างของฤดูกาลจากข้อมูลนี้ ไม่ใช่เพดานสูงสุด และจังหวัดแม่ฮ่องสอน พื้นที่ 12,765 ตร.กม. มีสถานีวัดของรัฐแห่งเดียว อยู่ในตัวเมือง ปาย สบป่อง ขุนยวม แม่สะเรียง ไม่มีเลย")}</div>')
    n = BY_ID.get("the-smoke")
    if n:
        b.append(f'<h2>{E(T(n, "names.name", lang))}</h2><div class="prose">{prose(T(n, "text.story", lang))}</div>'
                 f'<p><a class="btn alt" href="{lroot(lang)}{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    b.append(f'<p class="small mute">{E(AIR.get("attribution", ""))} · {E(AIR.get("start"))} → {E(AIR.get("end"))}</p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}air/"
    b.append(share_row(url, "When not to ride the Mae Hong Son loop", lang))
    return page(f'{"When to go" if lang == "en" else "ควรไปเมื่อไหร่"} — {NAME[lang]}', "".join(b), 1, lang,
                "Four burning seasons of daily PM2.5 at ten points on the loop.", None, url,
                cur="air", path="air/", card="air")


# ---------------------------------------------------------------- danger
def danger(lang: str) -> str:
    hz = [n for n in NODES if n["type"] == "hazard"]
    b = [f'<h1><span class="kind">{E("Demand, not crashes" if lang == "en" else "ความยาก ไม่ใช่อุบัติเหตุ")}</span>'
         f'{E("Where it asks the most" if lang == "en" else "ช่วงที่หนักที่สุด")}</h1>',
         f'<p class="lede">{E("Nobody publishes a crash map for these roads and this project will not invent one. This is a map of how much steering each two kilometres asks for, measured the same way everywhere." if lang == "en" else "ไม่มีใครเผยแพร่แผนที่อุบัติเหตุของถนนเหล่านี้ และโครงการนี้จะไม่แต่งขึ้นมา นี่คือแผนที่ว่าทุกสองกิโลเมตรต้องบังคับรถมากแค่ไหน วัดด้วยวิธีเดียวกันทุกที่")}</p>']
    d1 = root_depth(1, lang)
    b.append(band("road-1263", "Route 1263" if lang == "en" else "ทางหลวง 1263",
                  "Where it asks the most" if lang == "en" else "ช่วงที่หนักที่สุด",
                  "Curves per kilometre in fixed two-kilometre windows, measured the same way everywhere."
                  if lang == "en" else "จำนวนโค้งต่อกิโลเมตรในหน้าต่างสองกิโลเมตร วัดด้วยวิธีเดียวกันทุกที่",
                  d1, lang, big="7.45", big_label=("hardest 2 km on Route 1095"
                                                   if lang == "en" else "2 กม. ที่หนักที่สุดบน 1095")))
    b.append('<figure class="map">' + base_map(880, demand=True, depth=d1) +
             f'<figcaption>© OpenStreetMap contributors · {E("2 km windows, 25° threshold" if lang == "en" else "หน้าต่าง 2 กม. เกณฑ์ 25 องศา")}</figcaption></figure>')
    bands = CURVES.get("bands", {})
    b.append('<div class="legend">' + "".join(
        f'<span><i style="background:var(--{geo.band_class(k)})"></i>{E(v)}</span>'
        for k, v in bands.items()) + "</div>")
    hardest = []
    for ref, rr in CURVES.get("roads", {}).items():
        for d in rr.get("hardest", [])[:2]:
            hardest.append((ref, d))
    hardest.sort(key=lambda x: -x[1]["per_km"])
    if hardest:
        b.append(f'<h2>{E("The hardest two kilometres on each road" if lang == "en" else "สองกิโลเมตรที่หนักที่สุดของแต่ละสาย")}</h2>')
        b.append('<div class="scroll"><table><thead><tr><th>Road</th>'
                 f'<th class="num">{E("Curves/km" if lang == "en" else "โค้ง/กม.")}</th>'
                 f'<th class="num">{E("Hairpins" if lang == "en" else "หักศอก")}</th>'
                 f'<th>{E("Where" if lang == "en" else "ที่ไหน")}</th></tr></thead><tbody>')
        for ref, d in hardest[:10]:
            b.append(f'<tr><th>Route {E(ref)}</th><td class="num">'
                     f'<span class="tag {geo.band_class(d["band"])}">{d["per_km"]}</span></td>'
                     f'<td class="num">{d["hairpins"]}</td>'
                     f'<td class="small mono">{d["mid"][0]:.4f}, {d["mid"][1]:.4f}</td></tr>')
        b.append("</tbody></table></div>")
    b.append(band("op-luang", "Op Luang" if lang == "en" else "ออบหลวง",
                  "It is not a crash map" if lang == "en" else "นี่ไม่ใช่แผนที่อุบัติเหตุ",
                  "Nobody publishes one for these roads. None is invented here."
                  if lang == "en" else "ไม่มีใครเผยแพร่แผนที่แบบนั้นสำหรับถนนเหล่านี้ และที่นี่ไม่ได้แต่งขึ้น",
                  d1, lang, cls="right short"))
    b.append(f'<h2>{E("What actually goes wrong" if lang == "en" else "สิ่งที่มักผิดพลาดจริง")}</h2><div class="grid">')
    for n in sorted(hz, key=lambda n: n["names"]["name"]):
        b.append(node_card(n, lang, 1))
    b.append("</div>")
    b.append(f'<div class="warn">{E(CURVES.get("not_a_crash_map", ""))}</div>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}danger/"
    b.append(share_row(url, "The hardest kilometres on the Mae Hong Son loop", lang))
    return page(f'{"Where it asks the most" if lang == "en" else "ช่วงที่หนักที่สุด"} — {NAME[lang]}',
                "".join(b), 1, lang, "A demand map computed from the road's own geometry.",
                None, url, cur="danger", path="danger/", card="danger")


# ---------------------------------------------------------------- quiz
QUIZ = jload(Path(__file__).resolve().parent.parent / "data" / "vocab" / "quiz.json")

QUIZJS = """
<script>
document.addEventListener('DOMContentLoaded',function(){
 var R=%RESULTS%;
 var form=document.getElementById('quiz'),out=document.getElementById('out');
 function block(r,over){
  var h='<div class="result"><h2>'+(over?'&#9656; ':'')+r.name+'</h2><p class="lede">'+r.say+'</p><p>'+r.how+'</p>';
  if(r.legs&&r.legs.length){h+='<h3>'+R._ui.legs+'</h3><ol class="legs">'+
    r.legs.map(function(l,i){return '<li><div class="hd"><span class="num">'+(i+1)+
      '.</span><a href="'+R._base+l.u+'">'+l.n+'</a></div></li>'}).join('')+'</ol>'}
  if(r.see&&r.see.length){h+='<h3>'+R._ui.see+'</h3><div class="tags">'+
    r.see.map(function(x){return '<a class="tag" href="'+R._base+x.u+'">'+x.n+'</a>'}).join('')+'</div>'}
  if(!over){h+='<p class="small mute">'+R._ui.dir+': <b>'+(r.dir==='ccw'?R._ui.ccw:R._ui.cw)+'</b></p>'}
  return h+'</div>';
 }
 function score(){
  var s={},answered=form.querySelectorAll('input:checked').length;
  Array.prototype.forEach.call(form.querySelectorAll('input:checked'),function(i){
    var w=JSON.parse(i.dataset.s);
    for(var k in w){s[k]=(s[k]||0)+w[k]}});
  if(!answered){out.innerHTML='';return}
  var plans=[],overs=[];
  for(var k in s){ if(!R[k])continue;
    (R[k].layer==='overlay'?overs:plans).push([k,s[k]]) }
  plans.sort(function(a,b){return b[1]-a[1]});
  overs.sort(function(a,b){return b[1]-a[1]});
  var h='';
  if(plans.length){h+=block(R[plans[0][0]],false)}
  overs.filter(function(o){return o[1]>=R._th}).slice(0,3).forEach(function(o){
    h+=block(R[o[0]],true)});
  var alt=plans.slice(1,3).filter(function(p){return plans[0]&&p[1]>=plans[0][1]*0.6});
  if(alt.length){h+='<p class="small mute">'+R._ui.also+' '+alt.map(function(p){
    return '<b>'+R[p[0]].name+'</b>'}).join(', ')+'</p>'}
  h+='<div class="share"><button type="button" data-copy="'+R._url+'?r='+(plans[0]||[''])[0]+
     '">'+R._ui.copy+'</button><button type="button" onclick="window.print()">'+R._ui.print+'</button></div>';
  if(answered<R._n){h+='<p class="small mute">'+R._ui.more.replace('%n',R._n-answered)+'</p>'}
  out.innerHTML=h;
  Array.prototype.forEach.call(out.querySelectorAll('[data-copy]'),function(b){
    b.addEventListener('click',function(){navigator.clipboard&&navigator.clipboard.writeText(b.dataset.copy);
      var t=b.textContent;b.textContent='\u2713';setTimeout(function(){b.textContent=t},1200)})});
 }
 form.addEventListener('change',score);
 var pre=new URLSearchParams(location.search).get('r');
 if(pre&&R[pre]){out.innerHTML=block(R[pre],false)}
});
</script>
"""


def quiz_page(lang: str) -> str:
    ui = UI[lang]
    b = [f'<h1><span class="kind">{E(str(len(QUIZ["results"])) + " possible answers" if lang == "en" else str(len(QUIZ["results"])) + " คำตอบที่เป็นไปได้")}</span>'
         f'{E(QUIZ["title"][lang])}</h1>',
         f'<p class="lede">{E(QUIZ["lede"][lang])}</p>',
         band("ban-rak-thai", "Ban Rak Thai" if lang == "en" else "บ้านรักไทย",
              "", "", root_depth(1, lang), lang,
              big=str(len(QUIZ["results"])),
              big_label=("possible answers" if lang == "en" else "คำตอบที่เป็นไปได้")),
         '<form id="quiz">']
    for i, q in enumerate(QUIZ["questions"]):
        b.append(f'<fieldset><legend>{i + 1}. {E(q["q"][lang])}</legend><div class="opts">')
        for j, a in enumerate(q["a"]):
            s = html.escape(json.dumps(a["s"]), quote=True)
            b.append(f'<label><input type="radio" name="q{i}" value="{j}" data-s="{s}">'
                     f'<span>{E(a["t"][lang])}</span></label>')
        b.append("</div></fieldset>")
    b.append("</form><div id='out'></div>")
    qw_en = ("The weights are this project's own opinion and they are printed in the JSON so you "
             "can disagree with them. Nothing you tick leaves this page.")
    qw_th = ("น้ำหนักคะแนนเป็นความเห็นของโครงการนี้เอง และพิมพ์ไว้ในไฟล์ JSON เพื่อให้เถียงได้ "
             "สิ่งที่คุณเลือกไม่ถูกส่งออกจากหน้านี้")
    b.append(f'<div class="warn">{E(qw_en if lang == "en" else qw_th)} '
             f'<a href="{rel(root_depth(1, lang))}api/quiz.json">quiz.json</a></div>')

    # everything the JS needs, resolved to names and urls at build time
    res = {}
    for k, v in QUIZ["results"].items():
        res[k] = {"name": v["name"][lang], "say": v["say"][lang], "how": v["how"][lang],
                  "dir": v.get("dir", "cw"), "layer": v.get("layer", "plan"),
                  "legs": [{"u": url_of(BY_ID[x]), "n": T(BY_ID[x], "names.name", lang)}
                           for x in v.get("legs", []) if x in BY_ID],
                  "see": [{"u": url_of(BY_ID[x]), "n": T(BY_ID[x], "names.name", lang)}
                          for x in v.get("see", []) if x in BY_ID]}
    res["_base"] = lroot(lang)
    res["_url"] = f"{SITE_URL}/{'th/' if lang == 'th' else ''}quiz/"
    res["_th"] = QUIZ.get("scoring", {}).get("overlay_threshold", 5)
    res["_n"] = len(QUIZ["questions"])
    res["_ui"] = {"legs": "Your legs" if lang == "en" else "ช่วงทางของคุณ",
                  "see": "Read these" if lang == "en" else "อ่านเพิ่ม",
                  "dir": "Direction" if lang == "en" else "ทิศทาง",
                  "cw": ui["cw"], "ccw": ui["ccw"], "copy": ui["copy"], "print": ui["print"],
                  "also": "Also close:" if lang == "en" else "ใกล้เคียง:",
                  "more": ("%n question(s) left — the answer sharpens as you go."
                           if lang == "en" else "เหลืออีก %n ข้อ คำตอบจะชัดขึ้นเรื่อยๆ")}
    head = QUIZJS.replace("%RESULTS%", json.dumps(res, ensure_ascii=False))
    url = res["_url"]
    b.append(share_row(url, QUIZ["title"][lang], lang))
    return page(f'{QUIZ["title"][lang]} — {NAME[lang]}', "".join(b), 1, lang,
                QUIZ["lede"][lang], None, url, head=head, cur="quiz", path="quiz/", card="quiz")


# ---------------------------------------------------------------- the year
# What is on, month by month. Each row: months, EN label, TH label, EN line, TH line,
# record id to link, and how good a month it is to be here (1 fine, 2 good, 3 special).
YEAR = [
 (["01","02"], "Cool, dry, clear", "หนาว แห้ง ฟ้าใส",
  "Sea of mist at dawn, cold mornings on the ridges, dry tarmac on every descent.",
  "ทะเลหมอกยามรุ่ง เช้าหนาวบนสันเขา ถนนแห้งทุกทางลง", "cool-season", 3),
 (["02","03","04"], "The hills burn", "ภูเขาถูกเผา",
  "Late February to late April. The viewpoints go white and the air is at its worst.",
  "ปลายกุมภาพันธ์ถึงปลายเมษายน จุดชมวิวกลายเป็นสีขาว และอากาศแย่ที่สุด", "burning-season", 1),
 (["03","04"], "Poy Sang Long", "ปอยส่างลอง",
  "The Shan ordination festival. Boys in gold, carried, feet never touching the ground.",
  "งานบวชลูกแก้วของชาวไทใหญ่ เด็กชายแต่งทอง ถูกแบก เท้าไม่แตะพื้น", "poy-sang-long", 3),
 (["04"], "Songkran", "สงกรานต์",
  "13 to 15 April. You will be soaked, repeatedly, by strangers with buckets.",
  "13 ถึง 15 เมษายน คุณจะเปียกซ้ำๆ จากคนแปลกหน้าถือถัง", "songkran", 2),
 (["05"], "It clears", "อากาศเปิด",
  "The smoke goes, the first rain comes, and Pai drops from 29.8 to 10.0 µg/m³.",
  "ควันหายไป ฝนแรกมา และปายลงจาก 29.8 เหลือ 10.0", "the-rains", 2),
 (["06","07","08","09","10"], "The green season", "หน้าเขียว",
  "The cleanest air of the year, waterfalls running, rooms cheap, roads empty.",
  "อากาศสะอาดที่สุดของปี น้ำตกมีน้ำ ห้องพักถูก ถนนว่าง", "the-rains", 3),
 (["07","08","09","10"], "Khao Phansa", "เข้าพรรษา",
  "The rains retreat. Candles at the temples, and the province at its quietest.",
  "ช่วงจำพรรษา เทียนพรรษาที่วัด และจังหวัดที่เงียบที่สุด", "phansa", 2),
 (["07","08","09"], "Terraces green", "นาเขียว",
  "Pa Bong Piang and the Karen terraces at their greenest, above Mae Chaem.",
  "ป่าบงเปียงและนาขั้นบันไดกะเหรี่ยงเขียวที่สุด เหนือแม่แจ่ม", "pa-bong-piang", 3),
 (["08"], "Akha Swing Festival", "เทศกาลโล้ชิงช้าอาข่า",
  "Late August — but east of here. Worth a trip; not this trip.",
  "ปลายสิงหาคม แต่อยู่ทางตะวันออก ควรไป แต่คนละทริป", "akha-swing", 1),
 (["10","11"], "Terraces gold", "นาเหลืองทอง",
  "The rice turns before the harvest.",
  "ข้าวเปลี่ยนสีก่อนเกี่ยว", "pa-bong-piang", 2),
 (["11"], "Bua Tong", "ทุ่งบัวตอง",
  "Doi Mae U-Kho above Khun Yuam turns yellow for a few weeks and then does not.",
  "ดอยแม่อูคอเหนือขุนยวมเหลืองอยู่ไม่กี่สัปดาห์ แล้วก็ไม่", "bua-tong-bloom", 3),
 (["11"], "Loi Krathong and Yi Peng", "ลอยกระทง และยี่เป็ง",
  "Floats on every river, lanterns in the north, on the twelfth full moon.",
  "กระทงลอยทุกสายน้ำ โคมลอยทางเหนือ ในคืนเพ็ญเดือนสิบสอง", "loi-krathong", 3),
 (["11","12"], "Mist season opens", "เริ่มฤดูทะเลหมอก",
  "Pang Ung and Huai Nam Dang start working at six in the morning.",
  "ปางอุ๋งและห้วยน้ำดังเริ่มทำงานตอนหกโมงเช้า", "pang-ung", 3),
]


def year_page(lang: str) -> str:
    en = lang == "en"
    d1 = root_depth(1, lang)
    b = [f'<h1><span class="kind">{E("Month by month" if en else "เดือนต่อเดือน")}</span>'
         f'{E("The year" if en else "ทั้งปี")}</h1>',
         f'<p class="lede">{E("What is flowering, what is flooded, what is burning and what is being carried through the streets." if en else "อะไรกำลังบาน อะไรกำลังท่วม อะไรกำลังไหม้ และอะไรกำลังถูกแห่ไปตามถนน")}</p>']
    b.append(band("bua-tong", "Doi Mae U-Kho, November" if en else "ดอยแม่อูคอ พฤศจิกายน",
                  "Time it right and you get four things at once"
                  if en else "จับจังหวะให้ดี แล้วจะได้สี่อย่างพร้อมกัน",
                  "Clean air, the sunflowers out, the waterfalls still running and the lanterns going up."
                  if en else "อากาศสะอาด ทุ่งบัวตองบาน น้ำตกยังมีน้ำ และโคมกำลังลอยขึ้น", d1, lang))
    # the grid
    b.append('<div class="scroll"><table class="year"><thead><tr><th></th>' +
             "".join(f'<th class="num">{E(th if lang == "th" else en_)}</th>'
                     for _, en_, th in MONTHS) + "</tr></thead><tbody>")
    for months, l_en, l_th, line_en, line_th, rid, rank in YEAR:
        rec = BY_ID.get(rid)
        label = E(l_th if lang == "th" else l_en)
        if rec:
            label = f'<a href="{lroot(lang)}{url_of(rec)}">{label}</a>'
        cells = "".join(
            f'<td class="yr y{rank}" data-m="{E(th if lang == "th" else en_)}"></td>'
            if m in months else f'<td class="yr" data-m="{E(th if lang == "th" else en_)}"></td>'
            for m, en_, th in MONTHS)
        b.append(f'<tr><th>{label}<div class="small mute">'
                 f'{E(line_th if lang == "th" else line_en)}</div></th>{cells}</tr>')
    b.append("</tbody></table></div>")
    b.append('<div class="legend">'
             f'<span><i class="sw y3"></i>{E("the reason to pick that month" if en else "เหตุผลที่ควรเลือกเดือนนั้น")}</span>'
             f'<span><i class="sw y2"></i>{E("good, and on" if en else "ดี และมีอยู่")}</span>'
             f'<span><i class="sw y1"></i>{E("happening, plan around it" if en else "เกิดขึ้น ควรวางแผนเผื่อ")}</span></div>')
    pai = next((p for p in AIR.get("points", []) if p["id"] == "pai"), None)
    if pai:
        b.append(f'<h2>{E("And the air, the same twelve months" if en else "และอากาศ ในสิบสองเดือนเดียวกัน")}</h2>')
        b.append(month_strip(pai, lang))
        b.append(f'<p class="small mute">{E("Pai, mean PM2.5 µg/m³, four years measured." if en else "ปาย ค่าเฉลี่ย PM2.5 วัดสี่ปี")}</p>')
    b.append(f'<h2>{E("Everything with a date" if en else "ทุกอย่างที่มีวันกำหนด")}</h2><div class="grid">')
    for n_ in sorted([x for x in NODES if x["type"] == "event"], key=lambda x: x["names"]["name"]):
        b.append(node_card(n_, lang, 1))
    b.append("</div>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}year/"
    b.append(share_row(url, "The Mae Hong Son loop, month by month", lang))
    return page(f'{"The year" if en else "ทั้งปี"} — {NAME[lang]}', "".join(b), 1, lang,
                "Festivals, blooms, mist, rain and smoke, month by month.",
                None, url, cur="year", path="year/", card="year")


# ---------------------------------------------------------------- the good part
def good(lang: str) -> str:
    en = lang == "en"
    d1 = root_depth(1, lang)
    cur = CURVES.get("roads", {}).get("1095", {}).get("whole", {})
    b = [f'<h1><span class="kind">{E("Why you would" if en else "ทำไมถึงไป")}</span>'
         f'{E("The good part" if en else "ส่วนที่ดี")}</h1>',
         f'<p class="lede">{E("Six hundred kilometres of mountain road with something worth stopping for every twenty minutes of it." if en else "ถนนภูเขาหกร้อยกิโลเมตร ที่มีอะไรให้หยุดดูทุกยี่สิบนาที")}</p>']
    b.append(band("pang-ung", "Pang Ung, six in the morning" if en else "ปางอุ๋ง หกโมงเช้า",
                  "Four curves a kilometre, for four days"
                  if en else "สี่โค้งต่อกิโลเมตร ต่อเนื่องสี่วัน",
                  "A steering input every few seconds, for four days. That is the whole attraction."
                  if en else "สั่งรถเลี้ยวทุกไม่กี่วินาที ต่อเนื่องสี่วัน นั่นคือเสน่ห์ทั้งหมด",
                  d1, lang, big=str(cur.get("per_km", "4.03")),
                  big_label=("curves per kilometre on Route 1095"
                             if en else "โค้งต่อกิโลเมตรบนทางหลวง 1095")))
    joy_en = ("""**{c} curves over {k} kilometres. {h} of them hairpins.** On a road this tight engine size stops mattering and line choice starts, which is why a 110cc step-through is as absorbing here as anything with four times the power. You are never not doing something.

The riding is the obvious pleasure and it is not the biggest one. What the circuit actually gives you is a rhythm: you are somewhere different every evening, the days are short enough to stop constantly, and there is something worth stopping for roughly every twenty minutes. Nobody rides this loop fast twice.

**The province is quiet in a way that is hard to find.** Mae Hong Son has the lowest population density of any province in Thailand — twenty-two people per square kilometre across nearly thirteen thousand of them. On the long southern leg you can ride for half an hour and meet four vehicles.

And the thing nobody puts in the itinerary: **the ten minutes after you stop.** You get off, the engine ticks as it cools, your hearing comes back, and whatever you climbed for is just sitting there. That happens six or seven times a day on this road. It is the whole thing.""").format(
        c=cur.get("curves", 729), k=cur.get("km", 185), h=cur.get("hairpins", 110))
    joy_th = ("""**{c} โค้งในระยะ {k} กิโลเมตร เป็นโค้งหักศอก {h} โค้ง** บนถนนที่แคบขนาดนี้ ขนาดเครื่องยนต์เลิกมีความหมาย แล้วการเลือกไลน์เริ่มมีแทน นั่นคือเหตุผลที่รถออโต้ 110 ซีซี สนุกที่นี่ได้เท่ารถที่แรงกว่าสี่เท่า คุณไม่มีวินาทีไหนที่ไม่ได้ทำอะไร

การขี่คือความสุขที่เห็นชัด และไม่ใช่ความสุขที่ใหญ่ที่สุด สิ่งที่เส้นทางนี้ให้จริงๆ คือจังหวะ คุณอยู่คนละที่ทุกเย็น วันสั้นพอที่จะหยุดได้ตลอด และมีอะไรให้หยุดดูราวทุกยี่สิบนาที ไม่มีใครขี่วงรอบนี้เร็วเป็นครั้งที่สอง

**จังหวัดนี้เงียบในแบบที่หายาก** แม่ฮ่องสอนมีความหนาแน่นประชากรต่ำที่สุดในบรรดาทุกจังหวัดของไทย ยี่สิบสองคนต่อตารางกิโลเมตร บนพื้นที่เกือบหนึ่งหมื่นสามพันตารางกิโลเมตร บนช่วงใต้ที่ยาว คุณขี่ครึ่งชั่วโมงแล้วอาจสวนกับรถแค่สี่คัน

และสิ่งที่ไม่มีใครใส่ไว้ในแผนการเดินทาง **สิบนาทีหลังจากคุณหยุด** คุณลงจากรถ เครื่องยนต์ดังติ๊กๆ ขณะเย็นตัว การได้ยินกลับมา และสิ่งที่คุณไต่ขึ้นมาดูก็นั่งอยู่ตรงนั้น เรื่องนี้เกิดขึ้นหกหรือเจ็ดครั้งต่อวันบนถนนสายนี้ นั่นแหละคือทั้งหมด""").format(
        c=cur.get("curves", 729), k=cur.get("km", 185), h=cur.get("hairpins", 110))
    b.append(f'<div class="prose">{prose(joy_en if en else joy_th)}</div>')

    b.append(band("bua-tong", "Doi Mae U-Kho" if en else "ดอยแม่อูคอ",
                  "A day built round the stops" if en else "วันที่สร้างขึ้นรอบจุดแวะ",
                  "", d1, lang, cls="right"))
    day_en = """**06:00** The morning market. Curry in a bag, sticky rice, coffee. It is packing up by nine.
**08:00** Ride. The first two hours are the clearest air and the emptiest road of the day.
**10:00** The stall at the top of the climb. Twenty minutes, a bench, a valley.
**12:00** Noodles, wherever you are. Khao soi if it has not gone; nam ngiao if it has.
**14:00** Stop riding. The afternoon is for the town you landed in.
**16:00** Hot water on the forearms, or a temple with nobody in it, or a hammock.
**18:00** Whatever the town does in the evening. In Mae Hong Son that is two lit temples reflected in a pond.
"""
    day_th = """**06:00** ตลาดเช้า แกงใส่ถุง ข้าวเหนียว กาแฟ เก็บร้านตอนเก้าโมง
**08:00** ออกเดินทาง สองชั่วโมงแรกคืออากาศที่ใสที่สุดและถนนที่ว่างที่สุดของวัน
**10:00** เพิงกาแฟบนยอดดอย ยี่สิบนาที ม้านั่งหนึ่งตัว หุบเขาหนึ่งหุบ
**12:00** ก๋วยเตี๋ยว ที่ไหนก็ได้ที่อยู่ ข้าวซอยถ้ายังไม่หมด ขนมจีนน้ำเงี้ยวถ้าหมดแล้ว
**14:00** เลิกขี่ บ่ายเป็นของเมืองที่คุณไปถึง
**16:00** น้ำร้อนบนท้องแขน หรือวัดที่ไม่มีคน หรือเปลญวน
**18:00** อะไรก็ตามที่เมืองนั้นทำตอนเย็น ที่แม่ฮ่องสอนคือวัดสองหลังเปิดไฟสะท้อนหนองน้ำ
"""
    b.append(f'<div class="prose">{prose(day_en if en else day_th)}</div>')

    for t, head_en, head_th in (("dish", "What you eat", "ของกิน"),
                                ("coffee", "Coffee", "กาแฟ"),
                                ("spring", "Hot water", "น้ำพุร้อน"),
                                ("wat", "Wats", "วัด"),
                                ("stop", "Stops", "จุดแวะ"),
                                ("stay", "Beds", "ที่พัก")):
        recs = sorted([n for n in NODES if n["type"] == t], key=lambda n: n["names"]["name"])
        if not recs:
            continue
        b.append(f'<h2><a href="{lroot(lang)}{DIR_OF[t]}/">{E(head_en if en else head_th)}</a></h2>'
                 '<div class="grid">')
        b += [node_card(n_, lang, 1) for n_ in recs[:6]]
        b.append("</div>")

    b.append(band("ban-rak-thai2", "Ban Rak Thai" if en else "บ้านรักไทย",
                  "Nobody rides it fast twice" if en else "ไม่มีใครขี่เร็วเป็นครั้งที่สอง",
                  "", d1, lang, cls="short"))
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}good/"
    b.append(share_row(url, "The good part of the Mae Hong Son loop", lang))
    return page(f'{"The good part" if en else "ส่วนที่ดี"} — {NAME[lang]}', "".join(b), 1, lang,
                "Food, coffee, hot water, temples and the ten minutes after you stop.",
                None, url, cur="good", path="good/", card="good")


# ---------------------------------------------------------------- baggage
# The towns a rider actually sleeps in, in clockwise order, against what is mapped there.
BAG_TOWNS = [("chiang-mai", 18.7883, 98.9853), ("mae-malai", 19.1206, 98.9450),
             ("pai", 19.3592, 98.4407), ("soppong", 19.4906, 98.2694),
             ("mae-hong-son", 19.3020, 97.9654), ("khun-yuam", 18.8228, 97.9336),
             ("mae-la-noi", 18.4497, 97.9678), ("mae-sariang", 18.1614, 97.9308),
             ("mae-chaem", 18.4967, 98.3714), ("hot", 18.1447, 98.5847)]
BAG_NAMES = {"mae-malai": ("Mae Malai", "แม่มาลัย"), "mae-la-noi": ("Mae La Noi", "แม่ลาน้อย")}


# OSM tags a Thailand Post counter and a private courier agent with the same
# `amenity=post_office`, and they are not the same thing to a rider: the state office keeps
# government hours and closes at weekends, while an agent counter in a shop can be open
# until ten at night. Split them by name.
STATE_POST = re.compile(r"post\s*office|ไปรษณีย์", re.I)


def _is_state_post(row) -> bool:
    name = " ".join(filter(None, [row.get("name"), row.get("name_th"),
                                  (row.get("tags") or {}).get("name:en")]))
    return bool(STATE_POST.search(name))


def _near(lat, lon, kind, r_km=8.0):
    import math
    out = []
    for row in PLACES.get("rows", []):
        if row["kind"] != kind:
            continue
        R = 6371.0088
        p1, p2 = math.radians(lat), math.radians(row["lat"])
        h = (math.sin((p2 - p1) / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(math.radians(row["lon"] - lon) / 2) ** 2)
        d = 2 * R * math.asin(math.sqrt(h))
        if d <= r_km:
            out.append((round(d, 1), row))
    out.sort(key=lambda x: x[0])
    return out


def baggage(lang: str) -> str:
    ui = UI[lang]
    d1 = root_depth(1, lang)
    en = lang == "en"
    b = [f'<h1><span class="kind">{E("Logistics" if en else "การเดินทาง")}</span>'
         f'{E("Send the bag ahead" if en else "ส่งกระเป๋าไปก่อน")}</h1>',
         f'<p class="lede">'
         f'{E("You need four nights of clothes, a toothbrush and your chargers. It does not have to be on your back — it can be at the guesthouse before you are." if en else "คุณต้องมีเสื้อผ้าสี่คืน แปรงสีฟัน และที่ชาร์จ ของพวกนี้ไม่ต้องอยู่บนหลังคุณ มันไปรอที่ที่พักก่อนคุณได้")}</p>']
    b.append(band("road-1263", "Route 1263" if en else "ทางหลวง 1263",
                  "Two bags, not one" if en else "สองใบ ไม่ใช่ใบเดียว",
                  "A small one that stays with you. A larger one that leapfrogs ahead."
                  if en else "ใบเล็กอยู่กับตัว ใบใหญ่กระโดดข้ามไปรอ", d1, lang, cls="short"))

    n = BY_ID.get("sending-the-bag-ahead")
    if n:
        b.append(f'<div class="prose">{prose(T(n, "text.story", lang))}</div>')

    b.append(f'<h2>{E("Where it can land" if en else "ส่งไปลงที่ไหนได้")}</h2>')
    note_en = ("Counted from OpenStreetMap on " + str(PLACES.get("fetched")) + ". Distance is to "
               "the town centre. OSM tags a state post office and a private courier counter "
               "identically, so they are split here by name — the difference matters, because the "
               "state office keeps government hours and an agent in a shop may be open until ten "
               "at night. An absence is an absence from OpenStreetMap, not proof there is nowhere.")
    note_th = ("นับจาก OpenStreetMap เมื่อ " + str(PLACES.get("fetched")) + " ระยะวัดถึงกลางเมือง "
               "OSM ติดป้ายที่ทำการไปรษณีย์ของรัฐกับเคาน์เตอร์ขนส่งเอกชนเหมือนกัน ที่นี่จึงแยกด้วยชื่อ "
               "ความต่างนี้สำคัญ เพราะที่ทำการของรัฐเปิดตามเวลาราชการ ส่วนตัวแทนในร้านอาจเปิดถึงสี่ทุ่ม "
               "การไม่มีในนี้คือไม่มีใน OpenStreetMap ไม่ใช่ข้อพิสูจน์ว่าไม่มีจริง")
    b.append(f"<p>{E(note_en if en else note_th)}</p>")
    b.append('<div class="scroll"><table><thead><tr>'
             f'<th>{E("Town" if en else "เมือง")}</th>'
             f'<th>{E("Thailand Post" if en else "ไปรษณีย์ไทย")}</th>'
             f'<th>{E("Courier agent" if en else "ตัวแทนขนส่งเอกชน")}</th>'
             f'<th class="num">{E("Bus station" if en else "สถานีขนส่ง")}</th>'
             f'<th class="num">{E("Beds mapped" if en else "ที่พักในแผนที่")}</th>'
             f'<th>{E("Verdict" if en else "สรุป")}</th></tr></thead><tbody>')
    for tid, lat, lon in BAG_TOWNS:
        rec = BY_ID.get(tid)
        if rec:
            nm = T(rec, "names.name", lang)
            href = f'<a href="{lroot(lang)}{url_of(rec)}">{E(nm)}</a>'
        else:
            nm = BAG_NAMES.get(tid, (tid, tid))[0 if en else 1]
            href = E(nm)
        allpost = _near(lat, lon, "post")
        state = [(d_, r_) for d_, r_ in allpost if _is_state_post(r_)]
        agents = [(d_, r_) for d_, r_ in allpost if not _is_state_post(r_)]
        bus = _near(lat, lon, "bus")
        stay = _near(lat, lon, "stay")
        if state:
            dkm, row = state[0]
            pname = (row.get("name_th") if lang == "th" and row.get("name_th") else row.get("name")) or "—"
            pcell = (f'<a href="https://www.openstreetmap.org/{E(row["osm"])}" rel="noopener nofollow">'
                     f'{E(pname)}</a> <span class="mute small">{dkm} km</span>')
        else:
            pcell = f'<span class="tag r">{E("none mapped" if en else "ไม่มีในแผนที่")}</span>'
        if agents:
            names = []
            for dkm, row in agents[:3]:
                nm2 = row.get("name") or (row.get("tags") or {}).get("name:en")
                if not nm2:          # an unnamed counter helps nobody find it
                    continue
                hrs = (row.get("tags") or {}).get("opening_hours")
                names.append(E(nm2) + (f' <span class="mute small">{E(hrs)}</span>' if hrs else ""))
            acell = "<br>".join(names)
        else:
            acell = '<span class="mute">—</span>'
        ok = bool(state) or bool(agents) or bool(bus)
        verdict = ("Send it here" if ok else "Carry it that night") if en else ("ส่งได้" if ok else "คืนนั้นพกไปเอง")
        b.append(f'<tr><th>{href}</th><td>{pcell}</td><td>{acell}</td>'
                 f'<td class="num">{len(bus) or "—"}</td><td class="num">{len(stay) or "—"}</td>'
                 f'<td><span class="tag {"g" if ok else "r"}">{E(verdict)}</span></td></tr>')
    b.append("</tbody></table></div>")

    pins = []
    for kind, cls in (("post", "wat"), ("bus", "town")):
        for row in PLACES.get("rows", []):
            if row["kind"] == kind:
                pins.append({"lat": row["lat"], "lon": row["lon"], "cls": cls, "name": "",
                             "title": (row.get("name") or kind)})
    b.append('<figure class="map">' + base_map(860, pins=pins, labels=False, depth=root_depth(1, lang)) +
             f'<figcaption>{E(str(sum(1 for r in PLACES["rows"] if r["kind"] == "post")) + " post offices and " + str(sum(1 for r in PLACES["rows"] if r["kind"] == "bus")) + " bus stations in the corridor" if en else str(sum(1 for r in PLACES["rows"] if r["kind"] == "post")) + " ที่ทำการไปรษณีย์ และ " + str(sum(1 for r in PLACES["rows"] if r["kind"] == "bus")) + " สถานีขนส่ง ในเขตเส้นทาง")} · '
             f'{MAP_CREDIT}</figcaption></figure>')

    # the bus method, step by step: the part that usually gets a sentence rather than a procedure
    bp = BY_ID.get("bus-parcel")
    if bp:
        b.append(band("pano-chaem", "Prempracha" if en else "เปรมประชา",
                      T(bp, "names.name", lang), T(bp, "names.said", lang), d1, lang))
        b.append(f'<div class="prose">{prose(T(bp, "text.story", lang))}</div>'
                 f'<h3>{E("Step by step" if en else "ทีละขั้น")}</h3>'
                 f'<div class="prose">{prose(T(bp, "text.how", lang))}</div>')
        stations = [r_ for r_ in PLACES.get("rows", []) if r_["kind"] == "bus"]
        named = [r_ for r_ in stations if (r_.get("name") or "").lower().find("songthaew") < 0
                 and (r_.get("name") or r_.get("name_th"))]
        if named:
            b.append('<div class="scroll"><table><thead><tr>'
                     f'<th>{E("Bus station" if en else "สถานีขนส่ง")}</th>'
                     f'<th>{E("Thai" if en else "ภาษาไทย")}</th>'
                     f'<th>{E("Operator, where OSM names one" if en else "ผู้เดินรถ ตามที่ OSM ระบุ")}</th>'
                     "</tr></thead><tbody>")
            for r_ in sorted(named, key=lambda x: -x["lat"])[:14]:
                op = (r_.get("tags") or {}).get("operator") or "—"
                b.append(f'<tr><th><a href="https://www.openstreetmap.org/{E(r_["osm"])}" '
                         f'rel="noopener nofollow">{E(r_.get("name") or r_.get("name_th"))}</a></th>'
                         f'<td class="th">{E(r_.get("name_th") or "—")}</td><td>{E(op)}</td></tr>')
            b.append("</tbody></table></div>")

    if n:
        b.append(f'<h2>{E("Carry, do not ship" if en else "พกไปเอง อย่าส่ง")}</h2>'
                 f'<div class="prose">{prose(T(n, "text.how", lang))}</div>')

    # the checklist — the thing people actually want when they open a baggage page
    b.append(band("pai-canyon", "Four nights" if en else "สี่คืน",
                  "What to pack" if en else "เอาอะไรไปบ้าง",
                  "Which bag each thing goes in, and why the split is the point."
                  if en else "ของแต่ละอย่างอยู่กระเป๋าใบไหน และทำไมการแยกใบถึงสำคัญ",
                  d1, lang, cls="right short"))
    b.append(f'<p class="small mute">{E(PACKLIST["note"])}</p>' if en else "")
    b.append('<div class="grid packs">')
    for g in PACKLIST["groups"]:
        head = g["en"] if en else g["th"]
        why = g["why_en"] if en else g["why_th"]
        items = "".join(
            f'<li><label><input type="checkbox"> <span>{E(i["en"] if en else i["th"])}</span></label></li>'
            for i in g["items"])
        b.append(f'<article class="card pack"><h3>{E(head)}</h3>'
                 f'<p class="mute small">{E(why)}</p><ul class="check">{items}</ul></article>')
    b.append("</div>")
    b.append(f'<div class="btns">'
             f'<button type="button" class="btn alt" id="copypack">'
             f'{E("Copy the list" if en else "คัดลอกรายการ")}</button>'
             f'<button type="button" class="btn alt" onclick="window.print()">'
             f'{E("Print it" if en else "พิมพ์")}</button></div>')
    plain = []
    for g in PACKLIST["groups"]:
        plain.append((g["en"] if en else g["th"]).upper())
        plain += ["  [ ] " + (i["en"] if en else i["th"]) for i in g["items"]]
        plain.append("")
    txt = json.dumps("\n".join(plain) + f"\n{SITE_URL}/{'th/' if lang == 'th' else ''}baggage/")
    b.append("<script>document.addEventListener('DOMContentLoaded',function(){"
             "var b=document.getElementById('copypack');if(!b)return;"
             "b.addEventListener('click',function(){navigator.clipboard&&"
             f"navigator.clipboard.writeText({txt});"
             "var t=b.textContent;b.textContent='\u2713';"
             "setTimeout(function(){b.textContent=t},1400)})});</script>")
    ns = BY_ID.get("no-storage")
    if ns:
        b.append(band("pai-canyon", "Pai" if en else "ปาย",
                      T(ns, "names.name", lang), T(ns, "names.said", lang), d1, lang, cls="right short"))
        b.append(f'<div class="prose">{prose(T(ns, "text.story", lang))}</div>')
    b.append(f'<div class="grid">')
    for rid in ("sending-the-bag-ahead", "bus-parcel", "no-storage", "packing-light",
                "one-way-rental", "renting-a-bike", "loaded-bike"):
        r_ = BY_ID.get(rid)
        if r_:
            b.append(node_card(r_, lang, 1))
    b.append("</div>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}baggage/"
    b.append(share_row(url, "Can you send your bag ahead on the Mae Hong Son loop?", lang))
    return page(f'{"Send the bag ahead" if en else "ส่งกระเป๋าไปก่อน"} — {NAME[lang]}',
                "".join(b), 1, lang,
                "Yes — every overnight town on the loop can receive a parcel except two.",
                None, url, cur="baggage", path="baggage/", card="baggage")


# ---------------------------------------------------------------- roadbook
def roadbook(lang: str) -> str:
    ui = UI[lang]
    b = [f'<h1><span class="kind">{E("Print it, fold it, tank-bag it" if lang == "en" else "พิมพ์ พับ ใส่กระเป๋าถังน้ำมัน")}</span>'
         f'{E("The roadbook" if lang == "en" else "สมุดเส้นทาง")}</h1>',
         f'<p class="lede">{E("Every leg, every number, the fuel gaps and the hazards, on paper — because there are stretches of this road with no phone signal." if lang == "en" else "ทุกช่วง ทุกตัวเลข ระยะไม่มีปั๊ม และจุดอันตราย บนกระดาษ เพราะมีช่วงที่ถนนสายนี้ไม่มีสัญญาณโทรศัพท์")}</p>',
         f'<div class="btns"><button class="btn" onclick="window.print()">{E(ui["print"])}</button></div>']
    b.append(band("doi-kong-mu", "Doi Kong Mu" if lang == "en" else "ดอยกองมู",
                  "On paper, in a tank bag" if lang == "en" else "บนกระดาษ ในกระเป๋าถังน้ำมัน",
                  "There are stretches of this road with no phone signal."
                  if lang == "en" else "ถนนสายนี้มีช่วงที่ไม่มีสัญญาณโทรศัพท์",
                  root_depth(1, lang), lang, cls="short"))
    b.append('<div class="scroll"><table><thead><tr>'
             f'<th>#</th><th>{E("Leg" if lang == "en" else "ช่วง")}</th><th class="num">km</th>'
             f'<th class="num">{E("Curves, at least" if lang == "en" else "โค้ง อย่างน้อย")}</th>'
             f'<th class="num">{E("Hairpins" if lang == "en" else "หักศอก")}</th>'
             f'<th class="num">{E("Hours" if lang == "en" else "ชม.")}</th>'
             f'<th>{E("Roads" if lang == "en" else "ทางหลวง")}</th></tr></thead><tbody>')
    tot_km = tot_c = 0
    for i, l in enumerate(ITIN["legs"], 1):
        n = BY_ID[l["id"]]
        rt = n.get("route") or {}
        tot_km += l.get("km") or 0
        tot_c += l.get("curves") or 0
        b.append(f'<tr><td class="num">{i}</td><th>{E(T(n, "names.name", lang))}</th>'
                 f'<td class="num">{l.get("km") or "—"}</td><td class="num">{l.get("curves") or "—"}</td>'
                 f'<td class="num">{l.get("hairpins") or "—"}</td><td class="num">{E(l.get("hours") or "—")}</td>'
                 f'<td>{E(", ".join(rt.get("roads", [])))}</td></tr>')
    b.append(f'<tr><td></td><th>{E("Total" if lang == "en" else "รวม")}</th>'
             f'<td class="num"><b>{tot_km}</b></td><td class="num"><b>{tot_c}</b></td>'
             f'<td colspan="3"></td></tr>')
    b.append("</tbody></table></div>")
    b.append(f'<h2>{E("Fuel" if lang == "en" else "น้ำมัน")}</h2><ul>')
    for l in ITIN["legs"] + [{"id": x} for x in ITIN["optional"]]:
        n = BY_ID.get(l["id"])
        gap = ((n or {}).get("route") or {}).get("fuel_gap_km")
        if gap:
            b.append(f'<li><b>{E(T(n, "names.name", lang))}</b> — '
                     f'{E("longest stretch with no pump: " if lang == "en" else "ช่วงยาวที่สุดที่ไม่มีปั๊ม: ")}{gap:g} km</li>')
    b.append(f'<li>{E("Fill at every town whether or not the tank needs it." if lang == "en" else "เติมน้ำมันทุกเมือง ไม่ว่าถังจะพร่องหรือไม่")}</li></ul>')
    b.append(f'<h2>{E("Hazards, in one list" if lang == "en" else "จุดอันตราย รวมรายการเดียว")}</h2><ul>')
    for n in sorted([x for x in NODES if x["type"] == "hazard"], key=lambda n: n["names"]["name"]):
        b.append(f'<li><b>{E(T(n, "names.name", lang))}</b> — {E(T(n, "names.said", lang) or "")}</li>')
    b.append("</ul>")
    b.append(f'<h2>{E("Words at a pump, a clinic, a checkpoint" if lang == "en" else "คำที่ใช้ที่ปั๊ม คลินิก ด่าน")}</h2><ul>')
    for n in sorted([x for x in NODES if x["type"] == "term"], key=lambda n: n["names"]["name"]):
        b.append(f'<li><b>{E(n["names"]["name"])}</b> · <span class="th">{E(n["names"].get("th") or "")}</span>'
                 f'{" · " + E(n["names"]["rtgs"]) if n["names"].get("rtgs") else ""} — '
                 f'{E(clip(T(n, "text.what", lang) or "", 110))}</li>')
    b.append("</ul>")
    b.append('<figure class="map">' + base_map(820, depth=root_depth(1, lang)) + "</figure>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}roadbook/"
    b.append(share_row(url, "Mae Hong Son loop roadbook", lang))
    return page(f'{"The roadbook" if lang == "en" else "สมุดเส้นทาง"} — {NAME[lang]}', "".join(b), 1, lang,
                "Every leg, number, fuel gap and hazard on one printable page.", None, url,
                cur="roadbook", path="roadbook/", card="roadbook")


# A band per type index, so every door into the site opens on a photograph. Keyed by
# type: (band key, EN kicker, TH kicker, EN line, TH line, extra classes).
TYPE_BANDS = {
 "leg":    ("mhs", "Mae Hong Son", "แม่ฮ่องสอน",
            "Every leg reads differently depending on which way you came at it.",
            "แต่ละช่วงอ่านต่างกันไปตามทิศที่คุณมา", "short"),
 "road":   ("road-1263", "Route 1263", "ทางหลวง 1263",
            "Six numbers on a blue sign, and one of them is 4.46 curves a kilometre.",
            "หกหมายเลขบนป้ายสีน้ำเงิน และหนึ่งในนั้นคือ 4.46 โค้งต่อกิโลเมตร", ""),
 "town":   ("cnx-pano", "Chiang Mai", "เชียงใหม่",
            "Nine places to sleep, eat, fill up and find a mechanic.",
            "เก้าที่สำหรับนอน กิน เติมน้ำมัน และหาช่าง", ""),
 "stop":   ("mae-surin", "Mae Surin", "น้ำตกแม่สุรินทร์",
            "The reason the ride takes four days and not two.",
            "เหตุผลที่ทริปนี้ใช้สี่วัน ไม่ใช่สองวัน", "right"),
 "wat":    ("doi-kong-mu", "Doi Kong Mu", "ดอยกองมู",
            "Shan spires and Burmese tin, in a Thai province. The border explains it.",
            "เจดีย์ไทใหญ่และสังกะสีพม่า ในจังหวัดไทย ชายแดนคือคำอธิบาย", ""),
 "coffee": ("ban-rak-thai2", "Ban Rak Thai", "บ้านรักไทย",
            "Grown on the ridge you just rode over, and poured at the bottom of it.",
            "ปลูกบนดอยที่เพิ่งข้ามมา และชงให้ที่เชิงดอย", "short"),
 "spring": ("tham-pla" if "tham-pla" in BANDS else "op-luang", "Hot water", "น้ำพุร้อน",
            "Geothermal water, a hillside, and an hour with nothing required of you.",
            "น้ำพุร้อน ไหล่เขา และหนึ่งชั่วโมงที่ไม่มีอะไรเรียกร้องจากคุณ", "short"),
 "stay":   ("ban-rak-thai", "Ban Rak Thai", "บ้านรักไทย",
            "Bamboo, a mattress, and the valley where the fourth wall should be.",
            "ไม้ไผ่ ที่นอน และหุบเขาตรงที่ควรเป็นผนังที่สี่", "short"),
 "hazard": ("road-1263", "Route 1263", "ทางหลวง 1263",
            "Gravel on the apex, diesel at the junction, and the drop with nothing beside it.",
            "กรวดกลางโค้ง คราบน้ำมันตรงแยก และเหวที่ไม่มีอะไรกั้น", "right"),
 "bike":   ("pai-canyon", "Pai", "ปาย",
            "A 110 scooter and a 1200 adventure bike ride the same road.",
            "สกู๊ตเตอร์ 110 กับแอดเวนเจอร์ 1200 ขี่ถนนเส้นเดียวกัน", ""),
 "kit":    ("pano-chaem2", "Mae Chaem", "แม่แจ่ม",
            "What rides with you, what goes ahead in a parcel, what stays in Chiang Mai.",
            "อะไรไปกับรถ อะไรส่งล่วงหน้า อะไรฝากไว้เชียงใหม่", "right"),
 "person": ("poy", "Poy Sang Long", "ปอยส่างลอง",
            "Shan, Karen, Lisu, Lahu, Hmong, Lua, Pa-O and Chinese Yunnanese.",
            "ไทใหญ่ กะเหรี่ยง ลีซู ลาหู่ ม้ง ลัวะ ปะโอ และจีนยูนนาน", ""),
 "org":    ("cnx-pano", "Chiang Mai", "เชียงใหม่",
            "Rental counters, parcel offices, hospitals and national parks.",
            "เคาน์เตอร์เช่ารถ ที่ทำการพัสดุ โรงพยาบาล และอุทยานแห่งชาติ", "short"),
 "event":  ("bua-tong", "Doi Mae U-Kho", "ดอยแม่อูคอ",
            "When you go decides what you get.", "ไปเมื่อไหร่เป็นตัวกำหนดว่าจะได้อะไร", ""),
 "term":   ("tham-lot", "Tham Lot", "ถ้ำลอด",
            "Words for a pump, a checkpoint, a clinic and a noodle stall.",
            "คำที่ใช้ที่ปั๊ม ด่าน คลินิก และร้านก๋วยเตี๋ยว", "right"),
 "story":  ("pano-chaem", "Mae Chaem", "แม่แจ่ม",
            "The arguments this road starts, and who is making them.",
            "ข้อถกเถียงที่ถนนสายนี้ก่อ และใครเป็นคนเถียง", ""),
 "art":    ("pai-canyon", "Pai", "ปาย",
            "The sign with the number on it, and the stone that always tells the truth.",
            "ป้ายที่มีตัวเลข และหลักที่พูดความจริงเสมอ", "short"),
}


# ---------------------------------------------------------------- type index
KIND_TO_TYPE = {"wat": "wat", "coffee": "coffee", "spring": "spring", "stay": "stay",
                "viewpoint": "stop", "waterfall": "stop", "cave": "stop", "market": "stop",
                "museum": "stop", "fuel": "org", "repair": "org", "hospital": "org",
                "town": "town", "village": "town", "airport": "org",
                "post": "org", "parcel": "org", "bus": "org"}


def harvested_for(t: str) -> list:
    kinds = [k for k, v in KIND_TO_TYPE.items() if v == t]
    return [r for r in PLACES.get("rows", []) if r["kind"] in kinds]


def type_index(t: str, lang: str) -> str:
    ui = UI[lang]
    ti = TYPE_INFO[t]
    recs = sorted([n for n in NODES if n["type"] == t], key=lambda n: n["names"]["name"])
    harv = harvested_for(t)
    named = [h for h in harv if h.get("name")]
    title = ti["th"] if lang == "th" else ti["name"]
    b = [f'<h1><span class="kind">{E(str(len(recs)) + " written up" if lang == "en" else str(len(recs)) + " รายการที่เขียนไว้")}</span>{E(title)}</h1>',
         f'<p class="lede">{E(ti["th_blurb"] if lang == "th" else ti["blurb"])}</p>']
    tb = TYPE_BANDS.get(t)
    if tb:
        key, k_en, k_th, l_en, l_th, cls = tb
        # the headline is the band's own line — repeating the page title under the page
        # title is the thing that makes these read as filler
        b.append(band(key, k_en if lang == "en" else k_th,
                      (l_en if lang == "en" else l_th) or title, "",
                      root_depth(1, lang), lang, cls=cls))
    if t == "leg":
        b.append(dirsw(lang))
        b.append(leg_list(lang, 1))
        opt = [BY_ID[x] for x in ITIN["optional"] if x in BY_ID]
        if opt:
            b.append(f'<h2>{E("Optional" if lang == "en" else "ทางเลือก")}</h2><div class="grid">')
            b += [node_card(n, lang, 1) for n in opt]
            b.append("</div>")
    else:
        pins = [{"lat": n["geo"]["lat"], "lon": n["geo"]["lon"], "name": n["names"]["name"], "cls": "town"}
                for n in recs if n.get("geo")]
        if pins or named:
            hp = pins + [{"lat": h["lat"], "lon": h["lon"], "name": "", "cls": t,
                          "title": h.get("name") or ""} for h in named[:1200]]
            b.append('<figure class="map">' + base_map(860, pins=hp, labels=False, depth=root_depth(1, lang)) +
                     f'<figcaption>{E(str(len(recs)) + " written up, " + format(len(harv), ",") + " harvested from OpenStreetMap" if lang == "en" else str(len(recs)) + " รายการที่เขียนไว้ " + format(len(harv), ",") + " รายการจาก OpenStreetMap")} · '
                     f'{MAP_CREDIT}</figcaption></figure>')
        if recs:
            b.append('<div class="grid">')
            b += [node_card(n, lang, 1) for n in recs]
            b.append("</div>")
    if harv:
        b.append(f'<h2>{E("What OpenStreetMap has" if lang == "en" else "สิ่งที่ OpenStreetMap มี")}</h2>')
        fetched = PLACES.get("fetched")
        if lang == "en":
            msg = (f"{len(harv):,} rows inside the corridor, {len(named):,} of them with a name. "
                   f"These are not written up, not checked, and not endorsed — they are what "
                   f"volunteers mapped, on {fetched}. An absence here is an absence from "
                   f"OpenStreetMap, not from the road.")
        else:
            msg = (f"{len(harv):,} รายการในเขตเส้นทาง มีชื่อ {len(named):,} รายการ "
                   f"ยังไม่ได้เขียนถึง ไม่ได้ตรวจสอบ และไม่ได้รับรอง "
                   f"เป็นสิ่งที่อาสาสมัครทำแผนที่ไว้เมื่อ {fetched} "
                   f"การไม่มีในนี้คือไม่มีใน OpenStreetMap ไม่ใช่ไม่มีบนถนน")
        b.append(f"<p>{E(msg)}</p>")
        b.append('<div class="cols">')
        for h in sorted(named, key=lambda h: h["name"])[:400]:
            nm = h.get("name_th") if lang == "th" and h.get("name_th") else h["name"]
            b.append(f'<a href="https://www.openstreetmap.org/{E(h["osm"])}" rel="noopener nofollow">'
                     f'{E(nm)}</a>')
        b.append("</div>")
        if len(named) > 400:
            b.append(f'<p class="small mute">{E(f"First 400 of {len(named):,}. The rest are in " if lang == "en" else f"400 แรกจาก {len(named):,} ที่เหลืออยู่ใน ")}'
                     f'<a href="{rel(root_depth(1, lang))}api/places.json">places.json</a>.</p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}{DIR_OF[t]}/"
    b.append(share_row(url, title, lang))
    return page(f"{title} — {NAME[lang]}", "".join(b), 1, lang,
                ti["th_blurb"] if lang == "th" else ti["blurb"], None, url,
                head=DIRJS if t == "leg" else "", cur="legs" if t == "leg" else "",
                path=f"{DIR_OF[t]}/", card="legs" if t == "leg" else "index")


def all_page(lang: str) -> str:
    b = [f'<h1><span class="kind">{E(str(len(NODES)) + " records" if lang == "en" else str(len(NODES)) + " บันทึก")}</span>'
         f'{E(UI[lang]["all"])}</h1>']
    for t in TYPES:
        recs = sorted([n for n in NODES if n["type"] == t], key=lambda n: n["names"]["name"])
        if not recs:
            continue
        ti = TYPE_INFO[t]
        b.append(f'<h2><a href="{lroot(lang)}{DIR_OF[t]}/">{E(ti["th"] if lang == "th" else ti["name"])}</a> ({len(recs)})</h2>')
        b.append('<div class="cols">')
        for n in recs:
            b.append(f'<a href="{lroot(lang)}{url_of(n)}">{E(T(n, "names.name", lang))}</a>')
        b.append("</div>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}all/"
    return page(f'{UI[lang]["all"]} — {NAME[lang]}', "".join(b), 1, lang, "", None, url,
                cur="", path="all/")


def about(lang: str) -> str:
    c = COV
    b = [f'<h1><span class="kind">{E("Method" if lang == "en" else "วิธีทำ")}</span>'
         f'{E(UI[lang]["about"])}</h1>']
    b.append('<div class="slab">'
             f'<div><b>{c["records"]}</b><span>{E("records" if lang == "en" else "บันทึก")}</span></div>'
             f'<div><b>{c["kin_edges"]}</b><span>{E("links between them" if lang == "en" else "ลิงก์ระหว่างกัน")}</span></div>'
             f'<div><b>{c["sources"]}</b><span>{E("sources" if lang == "en" else "แหล่งอ้างอิง")}</span></div>'
             f'<div><b>{c["th_fields"]}</b><span>{E("Thai fields" if lang == "en" else "ฟิลด์ภาษาไทย")}</span></div>'
             f'<div><b>{c["osm_places"]["count"]:,}</b><span>{E("OSM places" if lang == "en" else "สถานที่จาก OSM")}</span></div>'
             f'<div><b>{c["air"]["point_days"]:,}</b><span>{E("air point-days" if lang == "en" else "จุด-วัน อากาศ")}</span></div>'
             "</div>")
    b.append(f'<h2>{E("Where each claim comes from" if lang == "en" else "แต่ละข้อความมาจากไหน")}</h2>')
    b.append('<div class="scroll"><table><thead><tr><th>Tier</th><th class="num">Records</th><th>What it means</th></tr></thead><tbody>')
    for k, v in sorted(c["tiers"].items(), key=lambda kv: -kv[1]):
        b.append(f'<tr><td><span class="tier {E(k)}">{E(k)}</span></td><td class="num">{v}</td>'
                 f'<td>{E(TIER_LABEL.get(k, ""))}</td></tr>')
    b.append("</tbody></table></div>")
    b.append(f'<p>{E(str(c["needs_verification"]) + " records carry needs_verification: parts of them are marked as unconfirmed on the page itself." if lang == "en" else str(c["needs_verification"]) + " บันทึกมีเครื่องหมายว่าต้องตรวจสอบ ส่วนที่ยังไม่ยืนยันถูกระบุไว้ในหน้านั้นๆ")}</p>')
    b.append(f'<h2>{E("What this site does not claim" if lang == "en" else "สิ่งที่เว็บนี้ไม่ได้อ้าง")}</h2><ul>'
             f'<li>{E("The curve counts measure an OpenStreetMap polyline, which is a volunteer trace of a road rather than a survey of one." if lang == "en" else "จำนวนโค้งวัดจากเส้นทางใน OpenStreetMap ซึ่งเป็นการลากเส้นโดยอาสาสมัคร ไม่ใช่การสำรวจถนน")}</li>'
             f'<li>{E("The demand map says where a road asks the most of a rider. It is not a record of where anyone has crashed; no such record is published for these roads." if lang == "en" else "แผนที่ความยากบอกว่าถนนช่วงไหนเรียกร้องจากคนขี่มากที่สุด ไม่ใช่บันทึกว่าใครเคยชนที่ไหน ไม่มีการเผยแพร่บันทึกแบบนั้นสำหรับถนนเหล่านี้")}</li>'
             f'<li>{E("The air model never produced a daily mean above " + str(AIR.get("model_ceiling")) + " µg/m³ in " + format(AIR.get("point_days", 0), ",") + " point-days. Ground stations have recorded far higher. Read the season from it, not the ceiling." if lang == "en" else "แบบจำลองอากาศไม่เคยให้ค่าเฉลี่ยรายวันเกิน " + str(AIR.get("model_ceiling")) + " ใน " + format(AIR.get("point_days", 0), ",") + " จุด-วัน สถานีภาคพื้นดินเคยวัดได้สูงกว่ามาก อ่านฤดูกาลจากมัน ไม่ใช่เพดาน")}</li>'
             f'<li>{E("Harvested places are what volunteers mapped on a date. An absence is an absence from the dataset." if lang == "en" else "สถานที่ที่เก็บมาคือสิ่งที่อาสาสมัครทำแผนที่ไว้ ณ วันหนึ่ง การไม่มีคือไม่มีในชุดข้อมูล")}</li>'
             f'<li>{E("Prices, opening hours and business details are not published here unless a named source was checked. Where they were not, the page says so." if lang == "en" else "ราคา เวลาเปิดปิด และรายละเอียดร้านค้าไม่ได้เผยแพร่ที่นี่ เว้นแต่ตรวจสอบจากแหล่งที่ระบุชื่อแล้ว ถ้าไม่ได้ตรวจ หน้านั้นจะบอกไว้")}</li></ul>')
    b.append(f'<h2>{E("Rebuild it" if lang == "en" else "สร้างใหม่")}</h2>'
             '<pre class="small"><code>python3 tools/fetch_wiki.py\n'
             'python3 tools/harvest_osm.py --all\npython3 tools/harvest_air.py --all\n'
             'python3 tools/curves.py\npython3 tools/validate.py\n'
             'python3 tools/build.py\npython3 tools/site.py</code></pre>')
    b.append(f'<p class="small mute">{E("Built " + c["built"])}</p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}about/"
    return page(f'{UI[lang]["about"]} — {NAME[lang]}', "".join(b), 1, lang,
                "Sources, tiers, and what this site does not claim.", None, url, path="about/")


# ---------------------------------------------------------------- machine files
def icon_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" fill="#12100d"/>'
            '<path d="M10 54 C10 40 26 44 26 32 C26 20 40 24 40 12 C40 6 46 6 54 10" '
            'fill="none" stroke="#e0322b" stroke-width="7" stroke-linecap="round"/></svg>')


def manifest() -> str:
    return json.dumps({"name": NAME["en"], "short_name": "MHS Loop", "start_url": BASE_PATH,
                       "display": "standalone", "background_color": "#fdfbf4",
                       "theme_color": "#e0322b", "lang": "en",
                       "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"}]},
                      ensure_ascii=False, indent=1)


def robots() -> str:
    return (f"User-agent: *\nAllow: /\n\n"
            f"# Every page and the whole /api/ tree is open. Records CC BY 4.0.\n"
            f"Content-Signal: search=yes, ai-train=yes\n\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n\n"
            f"# The rest of this publisher's sites\n"
            + fleet.robots_lines(SELF, roster=ROSTER))


def sitemap() -> str:
    urls = []
    today = time.strftime("%Y-%m-%d")
    static = ["", "legs/", "which-way/", "numbers/", "good/", "year/", "air/", "danger/",
              "baggage/", "quiz/", "roadbook/", "all/", "about/"] + [f"{DIR_OF[t]}/" for t in TYPES
                                   if any(n["type"] == t for n in NODES)]
    for lang in LANGS:
        pre = "th/" if lang == "th" else ""
        for s in static:
            urls.append((f"{SITE_URL}/{pre}{s}", today, "0.8" if s else "1.0"))
        for n in NODES:
            urls.append((f"{SITE_URL}/{pre}{url_of(n)}", n.get("updated", today), "0.6"))
    body = "".join(
        f"<url><loc>{E(u)}</loc><lastmod>{E(m)}</lastmod><priority>{p}</priority>"
        f'<xhtml:link rel="alternate" hreflang="{"th" if "/th/" in u else "en"}" href="{E(u)}"/>'
        f"</url>" for u, m, p in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + body + "</urlset>\n")


def feed() -> str:
    items = sorted(NODES, key=lambda n: n.get("updated", ""), reverse=True)[:40]
    body = "".join(
        f"<entry><title>{E(n['names']['name'])}</title>"
        f'<link href="{SITE_URL}/{url_of(n)}"/><id>{SITE_URL}/{url_of(n)}</id>'
        f"<updated>{E(n.get('updated', ''))}T00:00:00Z</updated>"
        f"<summary>{E(clip((n.get('text') or {}).get('what') or '', 300))}</summary></entry>"
        for n in items)
    return ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
            f'<title>{E(NAME["en"])}</title><link href="{SITE_URL}/"/>'
            f"<id>{SITE_URL}/</id><updated>{time.strftime('%Y-%m-%d')}T00:00:00Z</updated>"
            f"<author><name>NaN</name></author>{body}</feed>\n")


def llms_txt() -> str:
    c = COV
    r95 = CURVES.get("roads", {}).get("1095", {}).get("whole", {})
    lines = [f"# {NAME['en']}", "", f"> {TAG['en']}", "",
             f"A bilingual (English and Thai) directory and route guide for the Mae Hong Son loop in "
             f"northern Thailand, built from {c['sources']} named sources. Every claim carries a "
             f"provenance tier. Records are CC BY 4.0.", "",
             "## What is measured here, and how", "",
             f"- Curve counts are computed from OpenStreetMap way geometry: ways carrying each route "
             f"number are stitched, resampled every 60 m, and walked accumulating heading change; an "
             f"arc over 25 degrees is a curve, over 120 a hairpin. Route 1095 measures "
             f"{r95.get('km')} km and {r95.get('curves')} curves, {r95.get('hairpins')} of them hairpins. "
             f"This measures a volunteer trace, not a road survey.",
             f"- The roadside sign and merchandise carry 1,864 for the Chiang Mai–Pai road; Thai "
             f"Wikipedia's Route 1095 article says 'more than 2,000'. Over the Mae Malai–Pai span this "
             f"project counts 395 at a 25-degree threshold. All three figures are printed with their methods.",
             f"- Route 1096 (Samoeng) measures the densest curves on this network at 4.46/km, ahead of "
             f"Route 1095 at 4.03.",
             f"- Air: {c['air']['point_days']:,} point-days of modelled daily PM2.5 at ten points, "
             f"Aug 2022 onward, from Copernicus CAMS via Open-Meteo. The model never exceeded "
             f"{AIR.get('model_ceiling')} µg/m³ daily mean; ground stations have recorded far higher.",
             f"- Mae Hong Son province (12,765 km²) has {len(AIR_NOW.get('mhs_province_stations', []))} "
             f"official PM2.5 monitor. Pai, Soppong, Khun Yuam and Mae Sariang have none.",
             f"- {c['osm_places']['count']:,} places harvested from OpenStreetMap inside the corridor.", "",
             "## Pages", ""]
    for p, k in NAV:
        lines.append(f"- [{UI['en'][k]}]({SITE_URL}/{p})")
    lines += ["", "## Records by type", ""]
    for t in TYPES:
        n = sum(1 for x in NODES if x["type"] == t)
        if n:
            lines.append(f"- [{TYPE_INFO[t]['name']}]({SITE_URL}/{DIR_OF[t]}/) — {n}")
    lines += ["", "## Data", "",
              f"- [nodes.json]({SITE_URL}/api/nodes.json) — every record",
              f"- [curves.json]({SITE_URL}/api/curves.json) — curve counts, thresholds, demand windows",
              f"- [air.json]({SITE_URL}/api/air.json) — monthly PM2.5 per point",
              f"- [places.json]({SITE_URL}/api/places.json) — the OpenStreetMap harvest",
              f"- [itinerary.json]({SITE_URL}/api/itinerary.json) — the loop, both directions",
              f"- [coverage.json]({SITE_URL}/api/coverage.json) — counts and provenance tiers", "",
              "## Licences", "",
              "- Records and measurements: CC BY 4.0",
              "- Road geometry and places: © OpenStreetMap contributors, ODbL 1.0",
              "- Air: Open-Meteo / Copernicus CAMS, CC BY 4.0; Thai PCD (air4thai)",
              "- Corpus text: Wikipedia, CC BY-SA 4.0", "",
              "## Thai", "", f"Every page exists at {SITE_URL}/th/<same path>.", "",
              fleet.llms_section(SELF, roster=ROSTER)]
    return "\n".join(lines) + "\n"


def llms_full() -> str:
    out = [llms_txt(), "\n\n# Full records\n"]
    for n in NODES:
        out.append(f"\n## {n['names']['name']} ({n['type']}/{n['id']})\n")
        if n["names"].get("th"):
            out.append(f"Thai: {n['names']['th']}\n")
        for k, v in (n.get("text") or {}).items():
            out.append(f"\n### {k}\n{v}\n")
        pv = (n.get("provenance") or {}).get("default") or {}
        out.append(f"\nProvenance: {pv.get('tier')}"
                   f"{' · ' + pv['source'] if pv.get('source') else ''}\n")
        if n.get("sources"):
            out.append("Sources: " + ", ".join(n["sources"]) + "\n")
        if n.get("needs_verification"):
            out.append("NEEDS VERIFICATION\n")
    return "".join(out)


def humans_txt() -> str:
    return (f"/* TEAM */\nBuilt by: NaN\nSite: https://wichaa.net\n\n"
            f"/* SITE */\nRecords: {COV['records']}\nSources: {COV['sources']}\n"
            f"Languages: English, ไทย\nStandards: HTML5, SVG, JSON-LD\n"
            f"Components: hand-written HTML, one inline stylesheet, inline SVG.\n"
            f"Built: {COV['built']}\n\n"
            + fleet.txt_row(SELF, roster=ROSTER) + "\n")


def ai_txt() -> str:
    return ("# ai.txt\n# Training and retrieval are both allowed.\n"
            "# Records and measurements are CC BY 4.0 — attribute "
            f"'{NAME['en']}, {SITE_URL}'.\n"
            "# OpenStreetMap-derived data is ODbL 1.0 and its share-alike terms apply to it.\n"
            "User-agent: *\nAllow: /\n\n"
            + fleet.ai_txt_lines(SELF, roster=ROSTER))


def api_index() -> str:
    files = ["nodes.json", "itinerary.json", "roads.json", "curves.json", "air.json",
             "air-now.json", "places.json", "sources.json", "vocab.json", "coverage.json",
             "quiz.json"] + [f"{t}.json" for t in TYPES if any(n["type"] == t for n in NODES)]
    b = ["<h1><span class=\"kind\">Open</span>API</h1>",
         "<p class=\"lede\">Every record and measurement the pages are built from, as JSON, "
         "fetchable directly. Records CC BY 4.0; OpenStreetMap-derived data ODbL 1.0.</p>", "<ul>"]
    for f in files:
        b.append(f'<li><a href="{rel()}api/{E(f)}">{E(f)}</a></li>')
    b.append("</ul><p>Per-record: <code>/api/&lt;type&gt;/&lt;id&gt;.json</code></p>")
    b.append('<p class="small mute">One tree, in one place. The Thai pages read the same '
             'files.</p>')
    return page("API — " + NAME["en"], "".join(b), 1, "en",
                "Every record and measurement as open JSON.", None, f"{SITE_URL}/api/", path="api/")


# ---------------------------------------------------------------- main
def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)
    n_pages = 0

    for lang in LANGS:
        base = SITE / ("th" if lang == "th" else "")
        write(base / "index.html", front(lang))
        write(base / "which-way" / "index.html", which_way(lang))
        write(base / "numbers" / "index.html", numbers(lang))
        write(base / "air" / "index.html", air_page(lang))
        write(base / "danger" / "index.html", danger(lang))
        write(base / "quiz" / "index.html", quiz_page(lang))
        write(base / "good" / "index.html", good(lang))
        write(base / "year" / "index.html", year_page(lang))
        write(base / "baggage" / "index.html", baggage(lang))
        write(base / "roadbook" / "index.html", roadbook(lang))
        write(base / "all" / "index.html", all_page(lang))
        write(base / "about" / "index.html", about(lang))
        n_pages += 12
        for t in TYPES:
            if any(n["type"] == t for n in NODES):
                write(base / DIR_OF[t] / "index.html", type_index(t, lang))
                n_pages += 1
        for n in NODES:
            write(base / PATH_OF[n["type"]] / n["id"] / "index.html", node_page(n, lang))
            n_pages += 1

    # pictures, with their sidecars left behind
    src_img = Path(__file__).resolve().parent.parent / "data" / "images"
    if src_img.exists():
        shutil.copytree(src_img, SITE / "images",
                        ignore=shutil.ignore_patterns("*.json", "_triage"), dirs_exist_ok=True)

    # the API tree, copied whole
    shutil.copytree(API, SITE / "api", dirs_exist_ok=True)
    shutil.copy(Path(__file__).resolve().parent.parent / "data" / "vocab" / "quiz.json",
                SITE / "api" / "quiz.json")
    write(SITE / "api" / "index.html", api_index())

    write(SITE / "basemap.svg", basemap_svg())
    write(SITE / "icon.svg", icon_svg())
    write(SITE / "manifest.webmanifest", manifest())
    write(SITE / "robots.txt", robots())
    write(SITE / "sitemap.xml", sitemap())
    write(SITE / "feed.xml", feed())
    write(SITE / "llms.txt", llms_txt())
    write(SITE / "llms-full.txt", llms_full())
    write(SITE / "humans.txt", humans_txt())
    write(SITE / "ai.txt", ai_txt())

    # CSV and JSONL dumps, for anyone who would rather not parse the tree
    import csv
    with open(SITE / "nodes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "type", "name", "name_th", "lat", "lon", "km", "curves", "hairpins",
                    "tier", "confidence", "needs_verification", "url"])
        for n in NODES:
            g = n.get("geo") or {}
            rt = n.get("route") or {}
            w.writerow([n["id"], n["type"], n["names"]["name"], n["names"].get("th", ""),
                        g.get("lat", ""), g.get("lon", ""), rt.get("km", ""), rt.get("curves", ""),
                        rt.get("hairpins", ""),
                        ((n.get("provenance") or {}).get("default") or {}).get("tier", ""),
                        n.get("confidence", ""), n.get("needs_verification", False),
                        f"{SITE_URL}/{url_of(n)}"])
    with open(SITE / "nodes.jsonl", "w", encoding="utf-8") as f:
        for n in NODES:
            f.write(json.dumps({k: v for k, v in n.items() if k != "kin_in"},
                               ensure_ascii=False) + "\n")

    # a small no-JS fallback note and the copy-button handler for pages without DIRJS
    write(SITE / "copy.js",
          "document.querySelectorAll('[data-copy]').forEach(function(b){"
          "b.addEventListener('click',function(){navigator.clipboard&&"
          "navigator.clipboard.writeText(b.dataset.copy);var t=b.textContent;"
          "b.textContent='\\u2713';setTimeout(function(){b.textContent=t},1200)})});")

    # the mount point, so serve.py and links.py can reproduce production exactly
    write(SITE / ".basepath", BASE_PATH)

    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"site: {n_pages} pages ({n_pages // 2} per language), "
          f"{len(list(SITE.rglob('*.html')))} html files, {size / 1e6:.1f} MB")
    print(f"      {SITE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
