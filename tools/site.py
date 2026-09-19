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
NAME = {"en": "The Mae Hong Son Loop", "th": "วงรอบแม่ฮ่องสอน"}
TAG = {"en": "600 kilometres, 1,864 curves on the sign, and a different answer from the map",
       "th": "หกร้อยกิโลเมตร ป้ายบอก 1,864 โค้ง และแผนที่ให้คำตอบอีกแบบ"}
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
          "coffee": "coffee", "spring": "springs", "stay": "beds", "hazard": "hazards",
          "bike": "bikes", "kit": "kit", "person": "people", "org": "outfits", "event": "calendar",
          "term": "words", "story": "stories", "art": "objects"}

UI = {
 "en": {"home": "The loop", "legs": "Legs", "which": "Which way", "numbers": "Numbers",
        "air": "Air", "danger": "Danger", "quiz": "Which ride", "roadbook": "Roadbook",
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
        "air": "อากาศ", "danger": "อันตราย", "quiz": "ขี่แบบไหน", "roadbook": "สมุดเส้นทาง",
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
       ("air/", "air"), ("danger/", "danger"), ("quiz/", "quiz"), ("roadbook/", "roadbook")]


def rel(depth: int) -> str:
    return "../" * depth if depth else "./"


def url_of(r: dict, lang="en") -> str:
    return f"{PATH_OF[r['type']]}/{r['id']}/"


def page(title, body, depth, lang, desc="", jsonld=None, canonical="", head="", cur=""):
    r = rel(depth)
    ui = UI[lang]
    other = "th" if lang == "en" else "en"
    # the same page in the other language: /th/ prefix added or removed
    o_root = r + ("th/" if lang == "en" else "../")
    cur_attr = ' aria-current="page"'
    nav = "".join(f'<a href="{r}{p}"{cur_attr if k == cur else ""}>{E(ui[k])}</a>'
                  for p, k in NAV)
    ld = json.dumps(jsonld or [], ensure_ascii=False)
    return f"""<!doctype html>
<html lang="{lang}"{' class="th"' if lang == 'th' else ''}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical or SITE_URL)}">
<link rel="alternate" hreflang="en" href="{SITE_URL}/{E(canonical.replace(SITE_URL + '/', '').replace('th/', '') if canonical else '')}">
<link rel="alternate" hreflang="th" href="{SITE_URL}/th/{E(canonical.replace(SITE_URL + '/', '').replace('th/', '') if canonical else '')}">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{E(canonical or SITE_URL)}">
<meta property="og:site_name" content="{E(NAME[lang])}">
<meta property="og:locale" content="{'th_TH' if lang == 'th' else 'en_GB'}">
<meta name="twitter:card" content="summary_large_image">
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
<a class="brand" href="{r}">Mae Hong Son <b>Loop</b></a>
<nav>{nav}</nav>
<span class="langsw">
<a href="{r}"{' aria-current="true"' if lang == 'en' else ''} hreflang="en">EN</a>
<a href="{r}th/" {'aria-current="true"' if lang == 'th' else ''} hreflang="th">ไทย</a>
</span>
</div></header>
<main id="main">
{body}
</main>
<footer class="bot"><div class="in">
<p><b>{E(NAME[lang])}</b> — {E(TAG[lang])}</p>
<p>{'Records CC BY 4.0. Road geometry and places © OpenStreetMap contributors, ODbL 1.0. Air data from Open-Meteo (CAMS), CC BY 4.0, and the Thai Pollution Control Department. Corpus text from Wikipedia, CC BY-SA 4.0.' if lang == 'en' else 'บันทึกเผยแพร่ภายใต้ CC BY 4.0 เส้นทางและสถานที่ © ผู้ร่วมสร้าง OpenStreetMap ภายใต้ ODbL 1.0 ข้อมูลอากาศจาก Open-Meteo (CAMS) ภายใต้ CC BY 4.0 และกรมควบคุมมลพิษ เนื้อหาอ้างอิงจากวิกิพีเดีย ภายใต้ CC BY-SA 4.0'}</p>
<p><a href="{r}about/">{E(ui['about'])}</a> · <a href="{r}api/">API</a> · <a href="{r}all/">{E(ui['all'])}</a> · <a href="{r}llms.txt">llms.txt</a></p>
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


def share_row(url: str, title: str, lang: str) -> str:
    ui = UI[lang]
    q = urllib.parse.quote
    return (f'<div class="share">'
            f'<a href="https://www.facebook.com/sharer/sharer.php?u={q(url)}" rel="noopener">Facebook</a>'
            f'<a href="https://line.me/R/msg/text/?{q(title + " " + url)}" rel="noopener">LINE</a>'
            f'<a href="https://api.whatsapp.com/send?text={q(title + " " + url)}" rel="noopener">WhatsApp</a>'
            f'<a href="https://reddit.com/submit?url={q(url)}&title={q(title)}" rel="noopener">Reddit</a>'
            f'<a href="mailto:?subject={q(title)}&body={q(url)}">Email</a>'
            f'<button type="button" data-copy="{E(url)}">{E(ui["copy"])}</button>'
            f'<button type="button" onclick="window.print()">{E(ui["print"])}</button>'
            f'</div>')


# ---------------------------------------------------------------- data, loaded once
NODES = jload(API / "nodes.json")["nodes"]
BY_ID = {r["id"]: r for r in NODES}
ITIN = jload(API / "itinerary.json")
ROADS = jload(API / "roads.json")
CURVES = jload(API / "curves.json")
AIR = jload(API / "air.json")
AIR_NOW = jload(API / "air-now.json")
PLACES = jload(API / "places.json")
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


ALL_LINES = [[tuple(c) for c in ln]
             for r in ROADS.values() for ln in (r.get("lines") or ([r["line"]] if r.get("line") else []))]
BOX = geo.fit(ALL_LINES)


def base_map(width=820, demand=False, highlight=None, pins=None, labels=True):
    """The one map. Every page draws the same geography and adds its own layer.

    Every stitched chain is drawn, not just the longest: a route number goes missing for a
    few hundred metres at roundabouts and through town centres, and drawing only the longest
    run would leave the circuit visibly open where it is not."""
    p = geo.Proj(box=BOX, width=width)
    out = [f'<svg viewBox="0 0 {p.width:.0f} {p.height:.0f}" role="img" '
           f'aria-label="Map of the Mae Hong Son loop">']
    # base: every chain of every road
    for ref, r in ROADS.items():
        for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
            out.append(f'<path class="road" d="{p.path([tuple(c) for c in ln])}"/>')
    if demand:
        for ref, r in CURVES.get("roads", {}).items():
            if r.get("density"):
                out.append(geo.demand_path_layer(p, r["density"]))
    else:
        for ref, r in ROADS.items():
            for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
                out.append(f'<path class="road-on" d="{p.path([tuple(c) for c in ln])}">'
                           f'<title>Route {ref}</title></path>')
    if highlight:
        for ref in highlight:
            r = ROADS.get(ref) or {}
            for ln in (r.get("lines") or ([r["line"]] if r.get("line") else [])):
                out.append(f'<path class="hilite" d="{p.path([tuple(c) for c in ln])}"/>')
    rows = pins if pins is not None else [
        {"lat": n["geo"]["lat"], "lon": n["geo"]["lon"], "name": n["names"]["name"], "cls": "town"}
        for n in NODES if n["type"] == "town" and n.get("geo")]
    out.append(geo.dots(p, rows, r=4.2, label=labels))
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
    r = rel(depth)
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
        thumb = (f'<figure class="thumb"><img src="{E(img_url(im, depth, thumb=True))}" '
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
    r = rel(depth)
    ti = TYPE_INFO[n["type"]]
    name = T(n, "names.name", lang)
    kind = ti["th"] if lang == "th" else ti["name"]
    said = T(n, "names.said", lang)
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}{url_of(n)}"
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
        b.append(hero_shot(n, depth))

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
            b.append('<figure class="map">' + base_map(820, highlight=rt["roads"]) +
                     f'<figcaption>{E("Highlighted: " + ", ".join("Route " + x for x in rt["roads"]) if lang == "en" else "เน้น: " + ", ".join("ทางหลวง " + x for x in rt["roads"]))} · '
                     f'© OpenStreetMap contributors</figcaption></figure>')

    if n.get("geo"):
        g = n["geo"]
        b.append('<figure class="map">' + base_map(
            820, pins=[{"lat": g["lat"], "lon": g["lon"], "name": name, "cls": "town"}], labels=True) +
            f'<figcaption>{g["lat"]:.4f}, {g["lon"]:.4f}'
            f'{" · " + str(g["elevation_m"]) + " m" if g.get("elevation_m") else ""} · '
            f'© OpenStreetMap contributors</figcaption></figure>')

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
        b.append(shot_strip(rest, depth))

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
    return page(f"{name} — {NAME[lang]}", "".join(b), depth, lang,
                clip(T(n, "text.what", lang) or "", 180), ld, url)


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
})();
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
    r = rel(depth)
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
    r = "./"
    cur = CURVES.get("roads", {}).get("1095", {}).get("whole", {})
    n_stop = sum(1 for n in NODES if n["type"] in ("stop", "wat", "spring"))
    b = [f'<h1><span class="kind">{E("Northern Thailand · 600 km" if lang == "en" else "ภาคเหนือ · 600 กม.")}</span>'
         f'{E(NAME[lang])}</h1>',
         f'<p class="lede">{E(TAG[lang])}</p>']
    b.append('<div class="slab">'
             f'<div><b>~600</b><span>{E(ui["km"])}</span></div>'
             f'<div><b>{cur.get("curves", "—")}</b><span>{E("curves on 1095, counted" if lang == "en" else "โค้งบน 1095 นับแล้ว")}</span></div>'
             f'<div><b>{cur.get("hairpins", "—")}</b><span>{E(ui["hairpins"])}</span></div>'
             f'<div><b>4–5</b><span>{E(ui["days"])}</span></div>'
             f'<div><b>{PLACES.get("count", 0):,}</b><span>{E("places mapped" if lang == "en" else "สถานที่บนแผนที่")}</span></div>'
             '</div>')
    b.append(f'<div class="btns"><a class="btn" href="{r}quiz/">{E("Which ride is yours?" if lang == "en" else "คุณควรขี่แบบไหน")}</a>'
             f'<a class="btn alt" href="{r}which-way/">{E("Clockwise or not?" if lang == "en" else "ตามเข็มหรือทวนเข็ม")}</a>'
             f'<a class="btn alt" href="{r}air/">{E("When not to go" if lang == "en" else "ช่วงที่ไม่ควรไป")}</a></div>')
    pool = gallery_pool()
    if pool:
        b.append(shot_strip([im for _, im in pool[:8]], 0))
    b.append('<figure class="map">' + base_map(880, demand=True) +
             f'<figcaption>{E("Coloured by how much steering each 2 km asks for — not a crash map." if lang == "en" else "สีบอกว่าทุก 2 กม. ต้องบังคับรถมากแค่ไหน ไม่ใช่แผนที่อุบัติเหตุ")} '
             f'© OpenStreetMap contributors</figcaption></figure>')
    b.append('<div class="legend">' + "".join(
        f'<span><i style="background:var(--{k})"></i>{E(v if lang == "en" else v)}</span>'
        for k, v in (("g", "under 2 curves/km"), ("b", "2–4"), ("h", "4–6"), ("r", "over 6"))) + "</div>")
    b.append(f'<h2>{E(ui["legs"])}</h2>')
    b.append(dirsw(lang))
    b.append(leg_list(lang, 0))
    b.append(f'<p><a class="btn alt" href="{r}legs/">{E("Every leg, in full" if lang == "en" else "ทุกช่วง แบบเต็ม")}</a></p>')

    # the three numbers
    claims = CURVES.get("claims", [])
    if claims and claims[0].get("measured_over_same_span"):
        c = claims[0]
        b.append(f'<h2>{E("1,864?" if lang == "en" else "1,864 จริงไหม")}</h2>'
                 f'<div class="prose"><p>' +
                 (f'The sign says <strong>1,864</strong>. Thai Wikipedia says <strong>more than 2,000</strong>. '
                  f'Counting the map over the same {c["span_km"]} km gives <strong>{c["measured_over_same_span"]}</strong>. '
                  f'For 1,864 to be right there would be a curve every <strong>{c["implies_metres_per_curve"]} metres</strong>.'
                  if lang == "en" else
                  f'ป้ายบอก <strong>1,864</strong> วิกิพีเดียไทยบอก <strong>กว่า 2,000</strong> '
                  f'การนับจากแผนที่บนระยะ {c["span_km"]} กม. เดียวกันได้ <strong>{c["measured_over_same_span"]}</strong> '
                  f'ถ้า 1,864 ถูก จะต้องมีโค้งทุก <strong>{c["implies_metres_per_curve"]} เมตร</strong>') +
                 f'</p></div><p><a class="btn alt" href="{r}numbers/">{E("The method" if lang == "en" else "วิธีนับ")}</a></p>')

    # air strip
    pai = next((p for p in AIR.get("points", []) if p["id"] == "pai"), None)
    if pai:
        b.append(f'<h2>{E("The air, by month" if lang == "en" else "อากาศ รายเดือน")}</h2>')
        b.append(month_strip(pai, lang))
        b.append(f'<p class="small mute">{E("Pai, mean PM2.5 µg/m³, four burning seasons. July 3.0 · April 29.8." if lang == "en" else "ปาย ค่าเฉลี่ย PM2.5 ไมโครกรัม/ลบ.ม. สี่ฤดูเผา กรกฎาคม 3.0 เมษายน 29.8")}</p>')
        b.append(f'<p><a class="btn alt" href="{r}air/">{E("Every town, every month" if lang == "en" else "ทุกเมือง ทุกเดือน")}</a></p>')

    # the doors
    b.append(f'<h2>{E("Everything else" if lang == "en" else "อย่างอื่นทั้งหมด")}</h2><div class="grid">')
    for t in ("bike", "hazard", "kit", "stop", "wat", "town", "event", "term", "story"):
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
                SITE_URL + ("/th/" if lang == "th" else "/"), head=DIRJS, cur="home")


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
    b.append(dirsw(lang))
    b.append('<figure class="map">' + base_map(880) +
             f'<figcaption>{E("Same road, either direction." if lang == "en" else "ถนนเดียวกัน ไปได้ทั้งสองทาง")} © OpenStreetMap contributors</figcaption></figure>')
    b.append(leg_list(lang, 1))
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
                     f'<p><a class="btn alt" href="../{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}which-way/"
    b.append(share_row(url, "Which way round the Mae Hong Son loop?", lang))
    return page(f'{"Which way round?" if lang == "en" else "ไปทางไหนดี"} — {NAME[lang]}',
                "".join(b), 1, lang,
                "Clockwise or counter-clockwise, argued by season.", None, url, head=DIRJS, cur="which")


# ---------------------------------------------------------------- numbers
def numbers(lang: str) -> str:
    b = [f'<h1><span class="kind">{E("Measured" if lang == "en" else "วัดแล้ว")}</span>'
         f'{E("The numbers" if lang == "en" else "ตัวเลข")}</h1>',
         f'<p class="lede">{E("Three figures are in circulation for this road. Here is a fourth, with its method, so you can argue with it." if lang == "en" else "มีตัวเลขสามตัวที่พูดกันถึงถนนสายนี้ นี่คือตัวที่สี่ พร้อมวิธีนับ เพื่อให้เถียงกับมันได้")}</p>']
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
             f'<th class="num">{E("Curves" if lang == "en" else "โค้ง")}</th>'
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

    b.append(f'<h2>{E("The method" if lang == "en" else "วิธีนับ")}</h2>'
             f'<div class="prose"><p>{E(CURVES.get("method", ""))}</p>'
             f'<p>{E(CURVES.get("not_a_crash_map", ""))}</p></div>')
    n = BY_ID.get("how-many-curves")
    if n:
        b.append(f'<div class="prose">{prose(T(n, "text.story", lang))}</div>'
                 f'<p><a class="btn alt" href="../{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}numbers/"
    b.append(share_row(url, "How many curves does the Mae Hong Son loop actually have?", lang))
    return page(f'{"The numbers" if lang == "en" else "ตัวเลข"} — {NAME[lang]}', "".join(b), 1, lang,
                "1,864 or 2,000 or something else — the curves, counted, with the method.",
                None, url, cur="numbers")


# ---------------------------------------------------------------- air
def air_page(lang: str) -> str:
    pts = AIR.get("points", [])
    b = [f'<h1><span class="kind">{E("Measured · " + str(AIR.get("point_days", 0)) + " point-days" if lang == "en" else "วัดแล้ว · " + str(AIR.get("point_days", 0)) + " จุด-วัน")}</span>'
         f'{E("When not to go" if lang == "en" else "ช่วงที่ไม่ควรไป")}</h1>',
         f'<p class="lede">{E("Ten points on the circuit, four burning seasons, daily PM2.5. The shape is not subtle." if lang == "en" else "สิบจุดบนเส้นทาง สี่ฤดูเผา ค่า PM2.5 รายวัน รูปร่างของมันชัดมาก")}</p>']
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
    b.append(f'<h2>{E("Every town, every month" if lang == "en" else "ทุกเมือง ทุกเดือน")}</h2>')
    b.append(f'<p class="small mute">{E("Mean PM2.5 in µg/m³. Green is under the WHO-adjacent 9.0; the US 24-hour standard is 35.4." if lang == "en" else "ค่าเฉลี่ย PM2.5 ไมโครกรัม/ลบ.ม. สีเขียวคือต่ำกว่า 9.0 ส่วนมาตรฐาน 24 ชั่วโมงของสหรัฐฯ คือ 35.4")}</p>')
    for p in pts:
        b.append(f'<h3>{E(p["th"] if lang == "th" else p["name"])}'
                 f'<span class="mute small"> · {E("worst" if lang == "en" else "แย่สุด")} '
                 f'{E(dict((k, en) for k, en, th in MONTHS).get(p["worst_month"], p["worst_month"]))} '
                 f'{p["worst_mean"]} · ×{p["ratio"]} {E("swing" if lang == "en" else "เท่า")}</span></h3>')
        b.append(month_strip(p, lang))
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
                 f'<p><a class="btn alt" href="../{url_of(n)}">{E("Full page" if lang == "en" else "หน้าเต็ม")}</a></p>')
    b.append(f'<p class="small mute">{E(AIR.get("attribution", ""))} · {E(AIR.get("start"))} → {E(AIR.get("end"))}</p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}air/"
    b.append(share_row(url, "When not to ride the Mae Hong Son loop", lang))
    return page(f'{"When not to go" if lang == "en" else "ช่วงที่ไม่ควรไป"} — {NAME[lang]}', "".join(b), 1, lang,
                "Four burning seasons of daily PM2.5 at ten points on the loop.", None, url, cur="air")


# ---------------------------------------------------------------- danger
def danger(lang: str) -> str:
    hz = [n for n in NODES if n["type"] == "hazard"]
    b = [f'<h1><span class="kind">{E("Demand, not crashes" if lang == "en" else "ความยาก ไม่ใช่อุบัติเหตุ")}</span>'
         f'{E("Where it asks the most" if lang == "en" else "ช่วงที่หนักที่สุด")}</h1>',
         f'<p class="lede">{E("Nobody publishes a crash map for these roads and this project will not invent one. This is a map of how much steering each two kilometres asks for, measured the same way everywhere." if lang == "en" else "ไม่มีใครเผยแพร่แผนที่อุบัติเหตุของถนนเหล่านี้ และโครงการนี้จะไม่แต่งขึ้นมา นี่คือแผนที่ว่าทุกสองกิโลเมตรต้องบังคับรถมากแค่ไหน วัดด้วยวิธีเดียวกันทุกที่")}</p>']
    b.append('<figure class="map">' + base_map(880, demand=True) +
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
    b.append(f'<h2>{E("What actually goes wrong" if lang == "en" else "สิ่งที่มักผิดพลาดจริง")}</h2><div class="grid">')
    for n in sorted(hz, key=lambda n: n["names"]["name"]):
        b.append(node_card(n, lang, 1))
    b.append("</div>")
    b.append(f'<div class="warn">{E(CURVES.get("not_a_crash_map", ""))}</div>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}danger/"
    b.append(share_row(url, "The hardest kilometres on the Mae Hong Son loop", lang))
    return page(f'{"Where it asks the most" if lang == "en" else "ช่วงที่หนักที่สุด"} — {NAME[lang]}',
                "".join(b), 1, lang, "A demand map computed from the road's own geometry.",
                None, url, cur="danger")


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
             f'<a href="../api/quiz.json">quiz.json</a></div>')

    # everything the JS needs, resolved to names and urls at build time
    res = {}
    for k, v in QUIZ["results"].items():
        res[k] = {"name": v["name"][lang], "say": v["say"][lang], "how": v["how"][lang],
                  "dir": v.get("dir", "cw"), "layer": v.get("layer", "plan"),
                  "legs": [{"u": url_of(BY_ID[x]), "n": T(BY_ID[x], "names.name", lang)}
                           for x in v.get("legs", []) if x in BY_ID],
                  "see": [{"u": url_of(BY_ID[x]), "n": T(BY_ID[x], "names.name", lang)}
                          for x in v.get("see", []) if x in BY_ID]}
    res["_base"] = "../"
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
                QUIZ["lede"][lang], None, url, head=head, cur="quiz")


# ---------------------------------------------------------------- roadbook
def roadbook(lang: str) -> str:
    ui = UI[lang]
    b = [f'<h1><span class="kind">{E("Print it, fold it, tank-bag it" if lang == "en" else "พิมพ์ พับ ใส่กระเป๋าถังน้ำมัน")}</span>'
         f'{E("The roadbook" if lang == "en" else "สมุดเส้นทาง")}</h1>',
         f'<p class="lede">{E("Every leg, every number, the fuel gaps and the hazards, on paper — because there are stretches of this road with no phone signal." if lang == "en" else "ทุกช่วง ทุกตัวเลข ระยะไม่มีปั๊ม และจุดอันตราย บนกระดาษ เพราะมีช่วงที่ถนนสายนี้ไม่มีสัญญาณโทรศัพท์")}</p>',
         f'<div class="btns"><button class="btn" onclick="window.print()">{E(ui["print"])}</button></div>']
    b.append('<div class="scroll"><table><thead><tr>'
             f'<th>#</th><th>{E("Leg" if lang == "en" else "ช่วง")}</th><th class="num">km</th>'
             f'<th class="num">{E("Curves" if lang == "en" else "โค้ง")}</th>'
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
    b.append('<figure class="map">' + base_map(820) + "</figure>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}roadbook/"
    b.append(share_row(url, "Mae Hong Son loop roadbook", lang))
    return page(f'{"The roadbook" if lang == "en" else "สมุดเส้นทาง"} — {NAME[lang]}', "".join(b), 1, lang,
                "Every leg, number, fuel gap and hazard on one printable page.", None, url, cur="roadbook")


# ---------------------------------------------------------------- type index
KIND_TO_TYPE = {"wat": "wat", "coffee": "coffee", "spring": "spring", "stay": "stay",
                "viewpoint": "stop", "waterfall": "stop", "cave": "stop", "market": "stop",
                "museum": "stop", "fuel": "org", "repair": "org", "hospital": "org",
                "town": "town", "village": "town", "airport": "org"}


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
            b.append('<figure class="map">' + base_map(860, pins=hp, labels=False) +
                     f'<figcaption>{E(str(len(recs)) + " written up, " + format(len(harv), ",") + " harvested from OpenStreetMap" if lang == "en" else str(len(recs)) + " รายการที่เขียนไว้ " + format(len(harv), ",") + " รายการจาก OpenStreetMap")} · '
                     f'© OpenStreetMap contributors</figcaption></figure>')
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
                     f'<a href="../api/places.json">places.json</a>.</p>')
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}{DIR_OF[t]}/"
    b.append(share_row(url, title, lang))
    return page(f"{title} — {NAME[lang]}", "".join(b), 1, lang,
                ti["th_blurb"] if lang == "th" else ti["blurb"], None, url,
                head=DIRJS if t == "leg" else "", cur="legs" if t == "leg" else "")


def all_page(lang: str) -> str:
    b = [f'<h1><span class="kind">{E(str(len(NODES)) + " records" if lang == "en" else str(len(NODES)) + " บันทึก")}</span>'
         f'{E(UI[lang]["all"])}</h1>']
    for t in TYPES:
        recs = sorted([n for n in NODES if n["type"] == t], key=lambda n: n["names"]["name"])
        if not recs:
            continue
        ti = TYPE_INFO[t]
        b.append(f'<h2><a href="../{DIR_OF[t]}/">{E(ti["th"] if lang == "th" else ti["name"])}</a> ({len(recs)})</h2>')
        b.append('<div class="cols">')
        for n in recs:
            b.append(f'<a href="../{url_of(n)}">{E(T(n, "names.name", lang))}</a>')
        b.append("</div>")
    url = f"{SITE_URL}/{'th/' if lang == 'th' else ''}all/"
    return page(f'{UI[lang]["all"]} — {NAME[lang]}', "".join(b), 1, lang, "", None, url, cur="")


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
                "Sources, tiers, and what this site does not claim.", None, url)


# ---------------------------------------------------------------- machine files
def icon_svg() -> str:
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
            '<rect width="64" height="64" fill="#12100d"/>'
            '<path d="M10 54 C10 40 26 44 26 32 C26 20 40 24 40 12 C40 6 46 6 54 10" '
            'fill="none" stroke="#e0322b" stroke-width="7" stroke-linecap="round"/></svg>')


def manifest() -> str:
    return json.dumps({"name": NAME["en"], "short_name": "MHS Loop", "start_url": "./",
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
    static = ["", "legs/", "which-way/", "numbers/", "air/", "danger/", "quiz/", "roadbook/",
              "all/", "about/"] + [f"{DIR_OF[t]}/" for t in TYPES
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
        b.append(f'<li><a href="{E(f)}">{E(f)}</a></li>')
    b.append("</ul><p>Per-record: <code>/api/&lt;type&gt;/&lt;id&gt;.json</code></p>")
    return page("API — " + NAME["en"], "".join(b), 1, "en",
                "Every record and measurement as open JSON.", None, f"{SITE_URL}/api/")


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
        write(base / "roadbook" / "index.html", roadbook(lang))
        write(base / "all" / "index.html", all_page(lang))
        write(base / "about" / "index.html", about(lang))
        n_pages += 9
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

    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"site: {n_pages} pages ({n_pages // 2} per language), "
          f"{len(list(SITE.rglob('*.html')))} html files, {size / 1e6:.1f} MB")
    print(f"      {SITE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
