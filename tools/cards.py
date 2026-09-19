#!/usr/bin/env python3
"""cards.py — the picture that shows when a page is shared.

One 1200x630 card per record and per standing page, drawn with Pillow. Masters are
committed to `cards/` and copied into the site by site.py, which points og:image at a
card ONLY when its file exists — an og:image that 404s unfurls worse than none at all.

Each card says what kind of thing the page is, names it, and then shows the one fact
that makes it worth a click:

    place   the town, the tags it has earned, and a dot on a map of the country
    style   the doughs this style runs, drawn in section
    donut   its dough, and the sugar and fat in one piece
    dish    the course, and the count of free recipes on the page
    person  the role and the place they are known for
    term    the root of the word
    art     the picture itself, bled to the edge
    story   the lede

A record with a photograph gets that photograph as a bleed on the right, which is the
strongest card this site can make, and the drawn panel otherwise.

    python3 tools/cards.py              # every card that is missing or out of date
    python3 tools/cards.py --all        # redraw everything
    python3 tools/cards.py place/randys-donuts index near
"""
from __future__ import annotations

import json
import math
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, DATA, GEO, IMAGES, ROOT, jload  # noqa: E402
import usmap  # noqa: E402

CARDS = ROOT / "cards"
W, H = 1200, 630
PAD = 64

# The site's own dark palette: a card is read at thumbnail size in a feed, so it is built
# on the deep plum ground where the box's pink burns hottest.
INK = (25, 14, 21)
INK_2 = (37, 22, 34)
CREAM = (255, 238, 247)
MUTE = (203, 166, 187)
DONUT = (234, 61, 133)
SAUCE_HI = (255, 111, 170)
GOLD = (199, 155, 255)
LINE = (67, 40, 58)
CHIP_BG = (51, 32, 44)

SERIF = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
SERIF_FALLBACK = "/System/Library/Fonts/Supplemental/Futura.ttc"
SANS = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
SANS_R = "/System/Library/Fonts/Supplemental/Arial.ttf"

TYPE_LABEL = {"style": "A STYLE", "donut": "A DONUT", "dish": "ALSO IN THE CASE", "kitchen": "OUT BACK", "place": "A SHOP",
              "person": "A PERSON", "org": "AN OUTFIT", "event": "A DAY", "term": "A WORD",
              "art": "A SIGN", "story": "A STORY"}
SITE_MARK = "PINK BOX"


def font(path: str, size: int, index: int = 0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.truetype(SERIF_FALLBACK, size)


def F_TITLE(sz):
    return font(SERIF, sz, index=1)      # Iowan Old Style Bold


def F_BODY(sz):
    return font(SERIF, sz, index=0)


def F_SANS(sz):
    return font(SANS, sz)


def F_SANS_R(sz):
    return font(SANS_R, sz)


# ------------------------------------------------------------------ helpers

def fit_text(d: ImageDraw.ImageDraw, text: str, fnt_for, max_w: int, max_lines: int, start: int, floor: int):
    """Largest size at which `text` wraps into max_lines of max_w. Returns (font, lines)."""
    size = start
    while size >= floor:
        f = fnt_for(size)
        avg = d.textlength("n", font=f) or 1
        cols = max(8, int(max_w / avg * 1.05))
        lines = textwrap.wrap(text, width=cols) or [text]
        if len(lines) <= max_lines and all(d.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 3
    # nothing fits: take what does and end it plainly
    f = fnt_for(floor)
    avg = d.textlength("n", font=f) or 1
    cols = max(8, int(max_w / avg * 1.05))
    lines = textwrap.wrap(text, width=cols) or [text]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and d.textlength(last + "\u2026", font=f) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,;:\u2014-") + "\u2026"
    return f, lines


def draw_lines(d, x, y, lines, fnt, fill, leading=1.16):
    lh = int(fnt.size * leading)
    for i, line in enumerate(lines):
        d.text((x, y + i * lh), line, font=fnt, fill=fill)
    return y + len(lines) * lh


def chip(d, x, y, text, fnt, fg=CREAM, bg=CHIP_BG, border=LINE):
    tw = d.textlength(text, font=fnt)
    h = int(fnt.size * 1.95)
    d.rounded_rectangle([x, y, x + tw + 30, y + h], radius=h // 2, fill=bg, outline=border, width=2)
    d.text((x + 15, y + (h - fnt.size) / 2 - fnt.size * 0.08), text, font=fnt, fill=fg)
    return x + tw + 30 + 10


def base_card(photo: Image.Image | None = None):
    """The ground: ink, a warm glow behind the text column, an ember rule down the left,
    and the photograph bled into the right third under a gradient so type stays legible."""
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    glow = Image.new("RGB", (W, H), INK)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-260, 240, 520, 1040], fill=(46, 32, 25))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(120)), 0.9)
    d = ImageDraw.Draw(img)
    if photo is not None:
        pw = 520
        ph = photo.copy()
        ratio = max(pw / ph.width, H / ph.height)
        ph = ph.resize((max(1, int(ph.width * ratio)), max(1, int(ph.height * ratio))), Image.LANCZOS)
        left = max(0, (ph.width - pw) // 2)
        top = max(0, (ph.height - H) // 2)
        ph = ph.crop((left, top, left + pw, top + H))
        img.paste(ph, (W - pw, 0))
        # a horizontal fade so the photograph dissolves into the ground rather than butting it
        fade = Image.new("L", (240, 1), 0)
        for x in range(240):
            fade.putpixel((x, 0), int(255 * (1 - x / 240) ** 1.2))
        mask = fade.resize((240, H))
        img.paste(Image.new("RGB", (240, H), INK), (W - pw, 0), mask)
        d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 10, H], fill=DONUT)
    return img, d


def footer(d, right_note: str = ""):
    f = F_SANS(21)
    d.text((PAD, H - 62), SITE_MARK, font=f, fill=GOLD)
    if right_note:
        fr = F_SANS_R(21)
        tw = d.textlength(right_note, font=fr)
        d.text((W - PAD - tw, H - 62), right_note, font=fr, fill=MUTE)


def eyebrow(d, text: str, y=PAD):
    f = F_SANS(23)
    t = " ".join(text.upper())
    d.text((PAD, y), t, font=f, fill=SAUCE_HI)
    return y + 44


def _open(im: dict):
    p = IMAGES / im["file"]
    if not p.exists():
        return None
    try:
        return Image.open(p).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def vivid(ph: Image.Image) -> Image.Image:
    """Warm the picture toward the site's ember and lift it, so a card glows in a feed
    instead of sitting grey next to it. Never so far that a red donut reads orange."""
    from PIL import ImageEnhance
    ph = ImageEnhance.Color(ph).enhance(1.22)
    ph = ImageEnhance.Contrast(ph).enhance(1.10)
    ph = ImageEnhance.Brightness(ph).enhance(1.04)
    warm = Image.new("RGB", ph.size, (214, 92, 40))
    return Image.blend(ph, warm, 0.06)


def load_photo(rec: dict, ctx: dict | None = None):
    """The record's own picture if it has one; otherwise the best picture among the pages
    it points at, then its style's, then its type's. Returns (image, credit, borrowed_from)."""
    own = rec.get("primary_image") or (rec.get("images") or [None])[0]
    if own:
        ph = _open(own)
        if ph:
            return ph, f'{own.get("author", "")} · {own.get("license", "")}'.strip(" ·"), None
    if not ctx:
        return None, "", None
    by_id = ctx.get("by_id") or {}
    order = [k["to"] for k in (rec.get("kin_out") or [])] + [k["from"] for k in (rec.get("kin_in") or [])]
    # a style or a place makes a better stand-in than a word does
    rank = {"art": 0, "place": 1, "style": 2, "kitchen": 3, "dish": 4, "event": 5, "donut": 6, "person": 7}
    cands = [by_id[i] for i in order if i in by_id and by_id[i].get("images")]
    cands.sort(key=lambda r: rank.get(r["type"], 9))
    seed = sum(ord(ch) for ch in rec["id"])
    for c in cands:
        imgs = c.get("images") or []
        if not imgs:
            continue
        im = imgs[seed % len(imgs)]
        ph = _open(im)
        if ph:
            return ph, f'{im.get("author", "")} · {im.get("license", "")}'.strip(" ·"), c["names"]["name"]
    for sid in ((rec.get("facets") or {}).get("styles") or []):
        st = by_id.get(sid)
        if st and st.get("images"):
            im = st["images"][seed % len(st["images"])]
            ph = _open(im)
            if ph:
                return ph, f'{im.get("author", "")} · {im.get("license", "")}'.strip(" ·"), st["names"]["name"]
    fb = ctx.get("fallback_by_type", {}).get(rec["type"]) or ctx.get("fallback")
    if fb:
        ph = _open(fb[0])
        if ph:
            return ph, f'{fb[0].get("author", "")} · {fb[0].get("license", "")}'.strip(" ·"), fb[1]
    return None, "", None


# ------------------------------------------------------------------ the little map

_GEO = None


def states():
    global _GEO
    if _GEO is None:
        _GEO = jload(GEO / "states.json")
    return _GEO


def mini_map(size=(430, 300), dot=None, dots=None, dot_r=9):
    """The country, with one place lit or many. Albers equal-area, the same projection
    every map on the site uses, drawn at 3x and downsampled because a 1px state border at
    card size otherwise looks like a scan artefact. Alaska and Hawaii are left off a card
    this small — there is no room to say what scale they are at, and an unlabelled inset
    lies."""
    S = 3
    w, h = size[0] * S, size[1] * S
    g = states()
    fit = usmap.fit_states(g, w, pad=10 * S)
    img = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(img)
    dy = (h - fit["h"]) / 2                      # centre the drawing in the card panel

    def proj(lon, lat):
        x, y = usmap.project(lon, lat, fit, "l48")
        return x, y + dy

    for st in g["states"]:
        if usmap.zone_of_state(st["iso"]) != "l48":
            continue
        for ring in st["rings"]:
            pts = [proj(x, y) for x, y in ring]
            d.polygon(pts, fill=(42, 37, 29))
            d.line(pts + [pts[0]], fill=(112, 100, 80), width=S)
    for p in (dots or []):
        if usmap.zone(p[1], p[0]) != "l48":
            continue
        x, y = proj(p[1], p[0])
        d.ellipse([x - 2.2 * S, y - 2.2 * S, x + 2.2 * S, y + 2.2 * S], fill=(176, 84, 48))
    if dot and usmap.zone(dot[1], dot[0]) == "l48":
        x, y = proj(dot[1], dot[0])
        r = dot_r * S
        d.ellipse([x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4], fill=(70, 38, 26))
        d.ellipse([x - r, y - r, x + r, y + r], fill=SAUCE_HI, outline=CREAM, width=2 * S)
    return img.resize(size, Image.LANCZOS)


# ----------------------------------------------------------------- the doughs

DOUGH_INK = {"yeast": (234, 61, 133), "cake": (47, 139, 216), "choux": (195, 122, 28),
             "potato": (18, 169, 126), "other": (120, 100, 112)}


def mini_dough(lit: set, size=(430, 250)):
    """The same two donuts the /dough/ page draws, at card scale: cut through the ring and
    sitting in the fat. Whichever doughs are in `lit` are painted; the rest recede."""
    S = 3
    w, h = size[0] * S, size[1] * S
    img = Image.new("RGB", (w, h), INK)
    d = ImageDraw.Draw(img)
    sx, sy = w / 430, h / 250
    FAT = 150

    def lobe(cx, cy, rx, ry, fill):
        d.ellipse([(cx - rx) * sx, (cy - ry) * sy, (cx + rx) * sx, (cy + ry) * sy], fill=fill, outline=CREAM, width=2 * S)

    # the fat
    d.rectangle([0, FAT * sy, w, h], fill=(40, 30, 20))
    d.line([(0, FAT * sy), (w, FAT * sy)], fill=GOLD, width=2 * S)
    for cx, key, rx, ry, bub, br in ((112, "yeast", 24, 32, 5, 7), (318, "cake", 26, 20, 8, 3)):
        fill = DOUGH_INK.get(key, DOUGH_INK["other"]) if key in lit else (58, 40, 52)
        for sign in (-1, 1):
            x = cx + sign * (rx + 12)
            lobe(x, FAT, rx, ry, fill)
            for i in range(bub):                    # crumb, in the half above the fat
                ang = (i / max(bub - 1, 1)) * 3.1416
                bx = x + math.cos(ang) * rx * 0.5
                by = FAT - 6 - abs(math.sin(ang)) * ry * 0.45
                r = br * min(sx, sy)
                d.ellipse([bx * sx - r, by * sy - r, bx * sx + r, by * sy + r], fill=(255, 238, 247))
        d.line([((cx - 2 * rx - 22) * sx, FAT * sy), ((cx + 2 * rx + 22) * sx, FAT * sy)], fill=CREAM, width=2 * S)
    return img.resize(size, Image.LANCZOS)


# ------------------------------------------------------------------ the sugar scale

def sugar_scale(img: Image.Image, x: int, y: int, value, others: list, w=470):
    """Where this bottle sits between nothing and a spoonful of sugar. Drawn straight onto
    the card through an alpha layer, so the photograph stays visible behind it."""
    S = 3
    h = 92
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, x1, cy = 8 * S, (w - 8) * S, 34 * S
    d.rounded_rectangle([x0, cy - 5 * S, x1, cy + 5 * S], radius=5 * S, fill=(255, 255, 255, 46))
    for o in others:
        ox = x0 + (x1 - x0) * min(o / 12.6, 1)
        d.ellipse([ox - 4 * S, cy - 4 * S, ox + 4 * S, cy + 4 * S], fill=(255, 255, 255, 120))
    if value is not None:
        vx = x0 + (x1 - x0) * min(value / 12.6, 1)
        d.ellipse([vx - 14 * S, cy - 14 * S, vx + 14 * S, cy + 14 * S], fill=DONUT + (110,))
        d.ellipse([vx - 9 * S, cy - 9 * S, vx + 9 * S, cy + 9 * S], fill=SAUCE_HI + (255,), outline=CREAM + (255,), width=2 * S)
    f = font(SANS, 17 * S)
    d.text((x0, cy + 18 * S), "0 g", font=f, fill=MUTE + (255,))
    t = "12.6 g \u2014 a spoonful of sugar"
    d.text((x1 - d.textlength(t, font=f), cy + 18 * S), t, font=f, fill=MUTE + (255,))
    img.paste(layer.resize((w, h), Image.LANCZOS), (x, y), layer.resize((w, h), Image.LANCZOS))


# ------------------------------------------------------------------ record cards

def photo_ground(ph: Image.Image, strength=1.0):
    """The picture, warmed and bled edge to edge, with a scrim that is opaque under the
    text column and clear on the right. This is the card; the type sits on top of it."""
    img = Image.new("RGB", (W, H), INK)
    ph = vivid(ph)
    ratio = max(W / ph.width, H / ph.height)
    ph = ph.resize((max(1, int(ph.width * ratio)), max(1, int(ph.height * ratio))), Image.LANCZOS)
    img.paste(ph, ((W - ph.width) // 2, (H - ph.height) // 2))
    # horizontal scrim: solid ink at the left edge, gone by 70% across
    grad = Image.new("L", (W, 1), 0)
    for x in range(W):
        t = x / W
        v = 252 if t < 0.26 else int(252 * max(0.0, (0.76 - t) / 0.5) ** 0.85)
        grad.putpixel((x, 0), int(v * strength))
    img.paste(Image.new("RGB", (W, H), INK), (0, 0), grad.resize((W, H)))
    # a bottom band so the footer line always has ground under it
    bot = Image.new("L", (1, H), 0)
    for y in range(H):
        bot.putpixel((0, y), int(210 * max(0.0, (y - H * 0.80) / (H * 0.20)) ** 1.1))
    img.paste(Image.new("RGB", (W, H), INK), (0, 0), bot.resize((W, H)))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 10, H], fill=DONUT)
    return img, d


FOOT_Y = H - 62          # the footer baseline
FACT_Y = H - 168         # chips, dots and panels hang from here, never from the flow


def record_card(rec: dict, ctx: dict) -> Image.Image:
    t = rec["type"]
    photo, credit, borrowed = load_photo(rec, ctx)
    art = t == "art" and photo is not None and not borrowed

    if art:
        img = Image.new("RGB", (W, H), INK)
        ph = vivid(photo)
        ratio = max(W / ph.width, H / ph.height)
        ph = ph.resize((int(ph.width * ratio), int(ph.height * ratio)), Image.LANCZOS)
        img.paste(ph, ((W - ph.width) // 2, (H - ph.height) // 2))
        scrim = Image.new("L", (1, H), 0)
        for yy in range(H):
            scrim.putpixel((0, yy), int(248 * max(0.0, (yy - H * 0.32) / (H * 0.68)) ** 1.05))
        img.paste(Image.new("RGB", (W, H), INK), (0, 0), scrim.resize((W, H)))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 10, H], fill=DONUT)
        col_w, y, title_lines = W - PAD * 2, eyebrow(d, TYPE_LABEL.get(t, t), y=int(H * 0.50)), 2
    elif photo is not None:
        img, d = photo_ground(photo)
        col_w, y, title_lines = int(W * 0.55), eyebrow(d, TYPE_LABEL.get(t, t)), 2
    else:
        img, d = base_card(None)
        col_w, y, title_lines = W - PAD * 2 - 470, eyebrow(d, TYPE_LABEL.get(t, t)), 3

    f, lines = fit_text(d, rec["names"]["name"], F_TITLE, col_w, title_lines, 78, 32)
    y = draw_lines(d, PAD, y + 4, lines, f, CREAM, 1.07) + 10

    a = rec.get("address") or {}
    fc = rec.get("facets") or {}
    sub = ""
    if t == "place":
        sub = ", ".join(x for x in (a.get("city"), a.get("state")) if x)
    elif t == "person":
        sub = ", ".join((fc.get("role") or [])[:2]).replace("-", " ")
    elif t in ("style", "donut"):
        sub = (rec.get("region_terms") or [{}])[0].get("name", "")
    elif t == "term":
        sub = "a word, with its root"
    elif t == "dish":
        sub = {"main": "on the plate", "side": "a side", "bread": "bread", "sweet": "a sweet",
               "drink": "a drink", "condiment": "a condiment"}.get(fc.get("course", ""), "")
    elif t == "event":
        sub = str(fc.get("when", "") or "")
    if sub:
        d.text((PAD, y), sub[:60], font=F_SANS(25), fill=GOLD)
        y += 44

    # the blurb takes whatever room is left above the fact line, and no more
    room = FACT_Y - 16 - y
    if room > 40:
        maxl = max(1, min(3, room // 39))
        fb, bl = fit_text(d, rec.get("blurb") or rec["text"]["what"], F_BODY, col_w, maxl, 29, 20)
        draw_lines(d, PAD, y, bl, fb, (208, 199, 185), 1.3)

    # the one fact, anchored
    fy = FACT_Y
    if t == "place":
        x = PAD
        fchip = F_SANS(20)
        for tg in (rec.get("tag_facts") or [])[:4]:
            lab = tg.get("label", "")
            if x + d.textlength(lab, font=fchip) + 42 > PAD + col_w:
                break
            x = chip(d, x, fy, lab, fchip, fg=CREAM, border=GOLD if tg.get("group") == "ownership" else LINE)
        n = rec.get("acclaim") or 0
        if n:
            d.text((PAD, fy + 54), "\u25cf" * min(n, 5) + f"  written down by {n} others", font=F_SANS(20), fill=GOLD)
        if rec.get("geo") and photo is None:
            img.paste(mini_map(dot=(rec["geo"]["lat"], rec["geo"]["lon"]), dots=ctx.get("dots")), (W - PAD - 430, 210))
    elif t == "style":
        cuts = ctx.get("style_cuts", {}).get(rec["id"], set())
        if photo is None:
            img.paste(mini_dough(cuts), (W - PAD - 430, 290))
        elif cuts:
            chip(d, PAD, fy + 18, {2: "both doughs, one kettle"}.get(len(cuts), ", ".join(sorted(cuts)) + " dough"), F_SANS(21), fg=CREAM, border=GOLD)
    elif t == "donut":
        pf = rec.get("profile") or {}
        v, g = pf.get("sugar_g"), pf.get("serving_g")
        if v is not None and g:
            d.text((PAD, fy - 6), f"{v:g} g of sugar in a {g:g} g piece", font=F_SANS(23), fill=CREAM)
            sugar_scale(img, PAD, fy + 26, v, ctx.get("sugars", []), min(470, col_w))
        elif pf.get("dough"):
            chip(d, PAD, fy + 18, pf["dough"] + " dough", F_SANS(21), fg=CREAM, border=GOLD)
        elif pf.get("ingredients"):
            chip(d, PAD, fy + 18, "first on the label: " + pf["ingredients"][0][:32], F_SANS(21), fg=CREAM, border=GOLD)
    elif t == "dish" and rec.get("recipes"):
        n = len(rec["recipes"])
        free = sum(1 for r in rec["recipes"] if "ingredients-only" not in (r.get("license") or "").lower())
        chip(d, PAD, fy + 18, f"{n} recipe{'s' if n != 1 else ''}, {free} you may copy in full", F_SANS(21), fg=CREAM, border=GOLD)
    elif t == "term":
        root = (rec.get("etymology") or {}).get("root", "")
        if root:
            fr, rl = fit_text(d, root, F_BODY, col_w, 2, 25, 18)
            draw_lines(d, PAD, fy, rl, fr, CREAM, 1.24)
    elif t == "person":
        pl = [k["name"] for k in (rec.get("kin_out") or []) if k.get("type") == "place"][:2]
        if pl:
            chip(d, PAD, fy + 18, " \u00b7 ".join(pl)[:46], F_SANS(21), fg=CREAM, border=LINE)

    note = credit if (photo is not None and not borrowed) else (f"picture: {borrowed}" if borrowed else ctx.get("host", ""))
    footer(d, note[:74])
    return img


# ------------------------------------------------------------------ page cards

def page_card(title: str, lede: str, eyebrow_text: str, ctx: dict, panel=None, stats=None, photo_id=None) -> Image.Image:
    ph = None
    if photo_id:
        rec = (ctx.get("by_id") or {}).get(photo_id)
        if rec and rec.get("images"):
            ph = _open(rec["images"][0])
    if ph is not None:
        img, d = photo_ground(ph)
        panel = None
    else:
        img, d = base_card()
    y = eyebrow(d, eyebrow_text)
    f, lines = fit_text(d, title, F_TITLE, W - PAD * 2 - (470 if panel is not None else 0), 2, 86, 40)
    y = draw_lines(d, PAD, y + 4, lines, f, CREAM, 1.06) + 16
    fb, bl = fit_text(d, lede, F_BODY, W - PAD * 2 - (470 if panel is not None else 0), 3, 31, 22)
    y = draw_lines(d, PAD, y, bl, fb, MUTE, 1.3) + 18
    if stats:
        x, y = PAD, max(y, FACT_Y - 30)
        for n, lab in stats:
            fn, fl = F_TITLE(44), F_SANS(19)
            d.text((x, y), str(n), font=fn, fill=SAUCE_HI)
            d.text((x, y + 52), lab.upper(), font=fl, fill=MUTE)
            x += max(d.textlength(str(n), font=fn), d.textlength(lab.upper(), font=fl)) + 52
    if panel is not None:
        img.paste(panel, (W - PAD - panel.width, (H - panel.height) // 2))
    footer(d, ctx.get("host", ""))
    return img


# ------------------------------------------------------------------ main

def main(argv: list[str]) -> int:
    api = BUILD / "api"
    if not (api / "nodes.json").exists():
        print("run tools/build.py first")
        return 1
    recs = jload(api / "nodes.json")["nodes"]
    places = jload(api / "places.json")
    cov = jload(api / "coverage.json")
    donuts = jload(api / "donuts.json") if (api / "donuts.json").exists() else {"donuts": []}
    CARDS.mkdir(exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pages as sitepages
    style_cuts = {k: v for k, _, v, _ in sitepages.DOUGH_STYLES}
    ctx = {"by_id": {r["id"]: r for r in recs},
           "dots": [(p["lat"], p["lon"]) for p in places["places"] if p.get("lat") is not None],
           "style_cuts": style_cuts,
           "sugars": [s["sugar_g"] for s in donuts.get("donuts", []) if s.get("sugar_g") is not None],
           "host": "nanobotco.github.io/pink-box"}

    want = set(argv)
    redraw_all = "--all" in want
    want.discard("--all")
    made = 0

    def save(img: Image.Image, name: str):
        """JPEG, because these are photographs: the same cards as PNG came to 164 MB.
        Every unfurler takes JPEG, and 1200x630 at q86 is about 120 KB."""
        nonlocal made
        p = CARDS / (name + ".jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p, "JPEG", quality=86, optimize=True, progressive=True, subsampling=1)
        made += 1

    # standing pages
    allmap = mini_map(size=(470, 330), dots=ctx["dots"])
    pages = {
        "index": ("Pink Box", "Cake or raised, egg rolls in the case, and who's been up since two. A directory of the American mom-and-pop donut shop.", "two doughs, fifty states", allmap,
                  [(cov["records"]["place"] + places["harvested"], "shops"), (sum(cov["records"].values()), "records"), (cov["recipes"], "recipes"), (cov["images"]["count"], "pictures")], "socal-pink-box"),
        "near": ("Donuts near me", "Every shop in America sorted from where you're standing, filtered to independents, to the ones open today, and to the ones selling more than donuts.", "nearest first", allmap, None, None),
        "donut": ("Cake or raised, by the numbers", "Nine donuts the United States government has weighed. Sugar and fat in one piece, and what USDA counts as a piece.", "measured", None,
                  [(len(donuts.get("donuts", [])), "donuts measured"), (sum(1 for x in donuts.get("donuts", []) if x.get("dough") == "yeast"), "raised"), (sum(1 for x in donuts.get("donuts", []) if x.get("dough") == "cake"), "cake")], "glazed-raised"),
        "dough": ("Cake or raised", "Yeast against baking powder. 150 seconds against 90. Thirty-eight grams against twenty-six. The whole shop is arranged around which.", "the two doughs", mini_dough({"yeast", "cake"}, (470, 280)), None, None),
        "counter": ("The other menu", "Egg rolls, breakfast burritos, deli sandwiches, kolaches, boba. Not a quirk — rent, in the words of the people paying it.", "what else is in the case", allmap, None, None),
        "make": ("Make some", "A glaze, a dough or a filling. Where a free-to-use recipe exists it is named and used in its own ratios.", "build one", None,
                 [("5", "glazes"), ("4", "doughs"), ("4", "fillings")], "glazed-raised"),
        "quiz": ("Which donut shop are you?", "Six questions about the hour you turn up, what else is on the board, and which dough you defend.", "a quiz", None, None, "socal-pink-box"),
        "art": ("Signs", "Neon, hand-lettered boards, the pink box, and the giant donut on the roof. Free to use, licence under each one.", "signs", None, None, "neon-donut"),
        "places": ("Every shop", "Every donut place in the country this project knows of, on one map, chains marked as chains.", "the map", allmap, None, None),
        "words": ("Words", "Donut against doughnut, olykoek, the hole, fry cake, bar, Long John, bismarck, jimmies, day-old.", "vocabulary", None, None, "pink-box"),
        "numbers": ("Numbers", "How far you are from the nearest donut anywhere in the country, when the shops opened, what the recipes call for.", "the arithmetic", allmap, None, None),
        "coverage": ("Coverage", "Where every row comes from, how many shops carry each tag, and what nobody has read yet.", "the holes", None, None, None),
        "search": ("Search", "Spell it however you spell it: doughnut, donut, paczki, punchki, kolache. Near spellings turn up, and say they are near.", "search", None, None, None),
        "sources": ("Sources", "Every article, dataset and page the records cite, by id.", "sources", None, None, None),
        "stories": ("The stories", "Cake against raised, the Donut King, why the egg rolls, and what counts as a mom-and-pop.", "long reads", None, None, "the-donut-king"),
    }
    for name, (title, lede, eb, panel, stats, photo_id) in pages.items():
        if want and name not in want:
            continue
        p = CARDS / (name + ".jpg")
        if not redraw_all and not want and p.exists():
            continue
        save(page_card(title, lede, eb, ctx, panel, stats, photo_id), name)

    # records
    for r in recs:
        key = f'{r["type"]}__{r["id"]}'
        sel = f'{r["type"]}/{r["id"]}'
        if want and sel not in want and key not in want:
            continue
        p = CARDS / (key + ".jpg")
        if not redraw_all and not want and p.exists():
            continue
        try:
            save(record_card(r, ctx), key)
        except Exception as e:  # noqa: BLE001
            print(f"  {key}: {e}")
    total = len(list(CARDS.glob("*.jpg")))
    size = sum(f.stat().st_size for f in CARDS.glob("*.jpg"))
    print(f"cards: {made} drawn, {total} on file, {size/1e6:.1f} MB in {CARDS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
