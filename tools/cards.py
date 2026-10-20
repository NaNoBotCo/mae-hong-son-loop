#!/usr/bin/env python3
"""cards.py — a share card per page, 1200×630.

A link with no picture shares as a grey box with a line of text under it, and
`twitter:card: summary_large_image` with no image attached is worse than declaring
nothing. This draws one card for every page that has something to show: the page's own
photograph, a scrim heavy enough to read type over, the headline, and one number where
there is a number worth leading with.

Cards are only redrawn when missing, so a rebuild is cheap. Pass --force to redo them.

    python3 tools/cards.py
    python3 tools/cards.py --force --only numbers
"""
from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD, IMAGES, jload  # noqa: E402

W, H = 1200, 630
FONTS = Path("/System/Library/Fonts/Supplemental")
DISPLAY = FONTS / "Arial Black.ttf"
BODY = FONTS / "Arial Bold.ttf"
THAI = FONTS / "Ayuthaya.ttf"
HOT = (255, 59, 47)
CREAM = (250, 245, 236)


def _font(path: Path, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(path), size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _is_thai(s: str) -> bool:
    return any("฀" <= c <= "๿" for c in s or "")


def _fit(draw, text, font_path, size, max_w, max_lines=3):
    """Shrink until the headline fits in `max_lines`, then wrap it."""
    from PIL import ImageFont
    while size > 26:
        f = _font(font_path, size)
        avg = max(1, draw.textlength("MMMMMMMMMM", font=f) / 10)
        per = max(8, int(max_w / avg))
        lines = textwrap.wrap(text, per, break_long_words=False) or [text]
        if len(lines) <= max_lines and all(draw.textlength(l, font=f) <= max_w for l in lines):
            return f, lines
        size -= 4
    f = _font(font_path, size)
    return f, textwrap.wrap(text, 24)[:max_lines] or [text]


def draw_card(out: Path, headline: str, kicker: str = "", big: str = "", big_label: str = "",
              photo: Path | None = None, credit: str = "", address: str = ""):
    from PIL import Image, ImageDraw, ImageFilter
    base = Image.new("RGB", (W, H), (18, 16, 13))
    if photo and photo.exists():
        try:
            im = Image.open(photo).convert("RGB")
            # cover
            r = max(W / im.width, H / im.height)
            im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)
            base.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        except Exception:  # noqa: BLE001
            pass
    # scrim: dark at the left and the bottom, where the type goes
    scrim = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(scrim)
    for x in range(W):
        sd.line([(x, 0), (x, H)], fill=int(232 - 170 * min(1.0, x / (W * 0.85))))
    bottom = Image.new("L", (W, H), 0)
    bd = ImageDraw.Draw(bottom)
    for y in range(H):
        bd.line([(0, y), (W, y)], fill=int(20 + 190 * max(0.0, (y - H * 0.45) / (H * 0.55))))
    scrim = Image.blend(scrim, bottom, 0.55).filter(ImageFilter.GaussianBlur(2))
    base = Image.composite(Image.new("RGB", (W, H), (10, 8, 5)), base, scrim)

    d = ImageDraw.Draw(base)
    pad = 62
    y = pad
    if kicker:
        kf = _font(THAI if _is_thai(kicker) else BODY, 26)
        d.text((pad, y), kicker.upper() if not _is_thai(kicker) else kicker, font=kf, fill=HOT)
        y += 46
    if big:
        bf = _font(DISPLAY, 148)
        # measure rather than assume: Arial Black's box is taller than its size and the
        # label was landing inside the digits' descender
        bbox = d.textbbox((pad, y), big, font=bf)
        d.text((pad, y), big, font=bf, fill=(255, 255, 255))
        y = bbox[3] + 10
        if big_label:
            lf = _font(THAI if _is_thai(big_label) else BODY, 27)
            d.text((pad, y), big_label, font=lf, fill=HOT)
            y += 46
    y += 12
    hf, lines = _fit(d, headline, THAI if _is_thai(headline) else DISPLAY,
                     74 if not big else 50, W - pad * 2, 3 if not big else 2)
    for line in lines:
        d.text((pad, y), line, font=hf, fill=(255, 255, 255))
        y += int(hf.size * 1.12)
    if address:
        af = _font(BODY, 22)
        d.text((W - pad - d.textlength(address, font=af), pad), address, font=af, fill=CREAM)
    # the mark
    mf = _font(DISPLAY, 28)
    label = "MAE HONG SON "
    d.text((pad, H - pad - 26), label, font=mf, fill=CREAM)
    d.text((pad + d.textlength(label, font=mf), H - pad - 26), "LOOP", font=mf, fill=HOT)
    if credit:
        cf = _font(THAI if _is_thai(credit) else BODY, 17)
        t = credit[:74]
        d.text((W - pad - d.textlength(t, font=cf), H - pad - 20), t, font=cf, fill=(190, 178, 162))
    d.rectangle([0, 0, W - 1, H - 1], outline=(255, 255, 255), width=6)
    out.parent.mkdir(parents=True, exist_ok=True)
    # JPEG, not PNG: these are photographs with type over them, and as PNG the same 78
    # cards came to 79 MB against about 9 as JPEG. Every platform that reads og:image
    # takes JPEG.
    base.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out


def photo_for(node: dict):
    for im in (node.get("images") or []):
        if im.get("primary"):
            return IMAGES / im["file"], f'{im.get("author", "")} · {im.get("license", "")}'
    for im in (node.get("images") or []):
        return IMAGES / im["file"], f'{im.get("author", "")} · {im.get("license", "")}'
    return None, ""




def _thai_lib() -> bool:
    """The card library (CARDS_LIB, or ~/Developer/claude code projects/cards), node and sips (macOS) are there."""
    import shutil
    lib = Path(os.environ.get("CARDS_LIB") or Path.home() / "Developer/claude code projects/cards")
    return (lib / "src" / "node.mjs").is_file() and shutil.which("node") is not None and shutil.which("sips") is not None


def _pick(t: str, credits: dict):
    """The first photograph in a page's HTML that is in data/images, and its credit."""
    import re
    for src in re.findall(r'<img[^>]*?\ssrc="([^"]+)"', t):
        if "/images/" not in src:
            continue
        rel = src.split("/images/", 1)[1].replace(".thumb.jpg", ".jpg")
        if (IMAGES / rel).is_file():
            return IMAGES / rel, credits.get(rel, "")
    return None, ""


def fill_missing(site: Path, nodes: list, host: str, kicker: dict, fallback_id: str, force: bool = False,
                 only: str = "") -> int:
    """Draw a card for every built page whose og:image names a card that is not there yet.

    The page's title and description are the card's words, its first photograph from data/images
    (or none) the picture, and the address of the page this copy serves the foot."""
    import html as _html
    import re
    credits = {}
    for nd in nodes:
        for im in (nd.get("images") or []):
            credits[im["file"]] = f'{im.get("author", "")} · {im.get("license", "")}'
    fb = next((nd for nd in nodes if nd["id"] == fallback_id), None)
    drawn = 0
    thai = []
    for f in sorted(site.rglob("index.html")):
        t = f.read_text(encoding="utf-8")
        m = re.search(r'<meta property="og:image" content="[^"]*/cards/([^"/]+)\.jpg"', t)
        if not m:
            continue
        out = site / "cards" / f"{m.group(1)}.jpg"
        if (out.exists() and not force) or (only and only != m.group(1)):
            continue
        tm = re.search(r'<meta property="og:title" content="([^"]*)"', t)
        title = _html.unescape(tm.group(1)) if tm else m.group(1)
        lang = (re.search(r'<html lang="(\w+)"', t) or [0, "en"])[1]
        photo, credit = _pick(t, credits)
        if photo is None:
            # a page with no picture of its own borrows the first picture of a page it links to
            bp = site / ".basepath"
            base = bp.read_text(encoding="utf-8").strip() if bp.is_file() else "/"
            seen = 0
            for href in re.findall(r'<a[^>]*?\shref="([^"#?]+)"', t):
                rel = href[len(base):].strip("/") if href.startswith(base) else ""
                if rel.count("/") < 1:
                    continue
                p = site / rel / "index.html"
                if p.is_file() and p != f:
                    photo, credit = _pick(p.read_text(encoding="utf-8"), credits)
                    if photo:
                        break
                seen += 1
                if seen > 60:
                    break
        if photo is None and fb:
            photo, credit = photo_for(fb)
        dm = re.search(r'<meta property="og:description" content="([^"]*)"', t)
        k = kicker.get(lang, kicker["en"])
        if dm and title.strip().lower() == k.strip().lower():
            title = _html.unescape(dm.group(1)).split(". ")[0][:90]
        where = f.parent.relative_to(site).as_posix()
        address = f"{host}/{where}/".replace("/./", "/").rstrip("/") if where != "." else host
        if lang == "th" and _thai_lib():
            # Thai cards come from the card library, which shapes the tone marks; PIL does not
            sub = _html.unescape(dm.group(1)).split(". ")[0][:110] if dm else ""
            if not sub or title == sub[:90] or (title in sub and len(sub) < len(title) + 15):
                sub = ""          # a line that only repeats the title says nothing more
            thai.append({"out": str(out), "title": title, "sub": sub, "kicker": k, "url": address,
                         "image": str(photo) if photo else "", "credit": credit, "accent": "#ff3b2f"})
        else:
            draw_card(out, title, k, "", "", photo, credit, address=address)
        drawn += 1
    if thai:
        import json
        import subprocess
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as jf:
            json.dump(thai, jf, ensure_ascii=False)
        subprocess.run(["node", str(Path(__file__).resolve().parent / "thai_cards.mjs"), jf.name], check=True)
        os.unlink(jf.name)
    return drawn


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    a_force = a.force
    site = BUILD / "site"
    host = os.environ.get("SITE_URL", "https://nanobotco.github.io/mae-hong-son-loop").rstrip("/").split("://", 1)[1]
    nodes = jload(BUILD / "api" / "nodes.json")["nodes"]
    by_id = {n["id"]: n for n in nodes}
    curves = jload(BUILD / "api" / "curves.json")
    air = jload(BUILD / "api" / "air.json")
    itin = jload(BUILD / "api" / "itinerary.json")
    r95 = curves.get("roads", {}).get("1095", {}).get("whole", {})
    ring = itin.get("ring", {})

    # A share card is a brag, not a footnote. Lead with the number people came for.
    PAGES = [
        ("index", "Chiang Mai to Mae Hong Son and back", "Northern Thailand",
         "1,864", "curves · 600 km · 4 days", "pang-ung"),
        ("numbers", "Every road, counted", "The numbers",
         "1,056", "curves on Route 1095 alone", "pai-canyon"),
        ("air", "Ten months of the year the answer is yes", "When to go",
         "3.0", "µg/m³ · Pai, July", "the-rains"),
        ("good", "Something worth stopping for every twenty minutes", "The good part",
         "", "", "pang-ung"),
        ("when", "Smoke, rain and crowds, every date of the year", "Pick a date",
         "", "", "bua-tong-bloom"),
        ("year", "Time it right and you get four things at once", "Month by month",
         "", "", "bua-tong-bloom"),
        ("baggage", "Send the bag ahead. The bus is going your way.", "Logistics",
         "", "", "road-1263" if "road-1263" in by_id else "the-1263-cut"),
        ("danger", "Where the road asks the most", "Demand, not crashes",
         "8.93", "curves per km, hardest 2 km", "op-luang"),
        ("quiz", "Nine plans, eight overlays, 761 ways it comes out.", "Which ride is yours",
         "", "", "ban-rak-thai"),
        ("which-way", "Clockwise or not? The season decides.", "The argument",
         "", "", "cnx-pano" if "cnx-pano" in by_id else "chiang-mai"),
        ("legs", "Nine legs, both directions", "The loop",
         "580", "curves, Chiang Mai to Pai", "mae-hong-son"),
        ("roadbook", "On paper, in a tank bag", "Roadbook", "", "", "doi-kong-mu"),
    ]
    n = 0
    for slug, head, kicker, big, big_label, photo_id in PAGES:
        if a.only and a.only != slug:
            continue
        out = site / "cards" / f"{slug}.jpg"
        if out.exists() and not a.force:
            continue
        node = by_id.get(photo_id)
        p, credit = photo_for(node) if node else (None, "")
        draw_card(out, head, kicker, big, big_label, p, credit,
                  address=host if slug == "index" else f"{host}/{slug}")
        n += 1
        print(f"  cards/{slug}.jpg")
    # one per record that has a photograph
    for node in nodes:
        out = site / "cards" / f"{node['type']}-{node['id']}.jpg"
        if out.exists() and not a.force:
            continue
        if a.only and a.only != node["id"]:
            continue
        p, credit = photo_for(node)
        if not p:
            continue
        rt = node.get("route") or {}
        n_curves = rt.get("curves")
        big = f"{n_curves:,}" if n_curves else ""
        draw_card(out, node["names"]["name"], node["names"].get("th") or node["type"],
                  big, "curves" if big else "", p, credit, address=host)
        n += 1
    # every other page the site names a card for: its title, its first photograph, its address
    n += fill_missing(site, nodes, host, {"en": "Mae Hong Son Loop", "th": "วงรอบแม่ฮ่องสอน"}, "pang-ung", force=a_force, only=a.only or "")
    print(f"cards: {n} drawn")
