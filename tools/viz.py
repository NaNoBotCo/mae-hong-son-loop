#!/usr/bin/env python3
"""viz.py — the maps, the infographics and the arithmetic.

Everything here is computed from the corpus at build time. Nothing is decorative: each
picture is the shortest way to say a thing the words would take a paragraph to say.

  distance_png     how near the nearest wing counter is, anywhere in the country
  locator_svg      a place and its neighbours, at street scale
  where_svg        every place matching a style, a donut, a person or a dish
  timeline_svg     when the places that are still open opened
  bars_svg         a plain ranked bar chart with a table twin
  open_days        which days a counter is open, parsed from OpenStreetMap
  kin_matrix_svg   which kinds of page point at which

Colour: one hue with position or lightness carrying the magnitude. The sequential donut
ramp below keeps monotone lightness on a single hue (about 18 degrees); its light end
recedes toward the surface, which is correct for a continuous heatmap and is why every
ramp here ships a numbered legend and a table twin.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import usmap

RAMP = ["#f7e5d6", "#efc1a0", "#e49a6d", "#d67343", "#cf4a1e", "#a63715", "#71230c"]
DONUT = "#cf4a1e"
def E(x) -> str:
    """html.escape, but a null field is a blank rather than a crash — a JSON field is
    null here when nobody published the thing, which is a state the site prints."""
    return __import__("html").escape("" if x is None else str(x))


def hexrgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def project(lon, lat, w, h, box=None):
    """Equirectangular, and ONLY for a small box — a locator at street scale. Every
    national map goes through usmap.project instead, in Albers equal-area."""
    return ((lon - box[0]) / (box[2] - box[0]) * w, (box[3] - lat) / (box[3] - box[1]) * h)


def us_fit(geo, w=760):
    return usmap.fit_states(geo, w)


def _rings(geo, insets=False):
    """Every state ring. insets=False walks the lower forty-eight only, which is what the
    small maps draw; insets=True adds Alaska and Hawaii."""
    for st in geo["states"]:
        z = usmap.zone_of_state(st["iso"])
        if z != "l48" and not insets:
            continue
        for ring in st["rings"]:
            yield st, ring, z


def inside(rings, lon, lat) -> bool:
    for ring in rings:
        n, ins = len(ring), False
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            if (y1 > lat) != (y2 > lat):
                if x1 + (lat - y1) * (x2 - x1) / (y2 - y1) > lon:
                    ins = not ins
        if ins:
            return True
    return False


# ------------------------------------------------------------------ the density map

BUCKET = 1.0   # degrees; the grid the nearest-place search walks outward from


def _buckets(pts):
    g: dict = {}
    for lat, lon in pts:
        g.setdefault((int(math.floor(lat / BUCKET)), int(math.floor(lon / BUCKET))), []).append((lat, lon))
    return g


def _nearest_mi(g, lat, lon, coslat):
    """Miles to the closest point, searching the bucket the query sits in and then rings
    of buckets outward, stopping once no unsearched ring can beat what we have. Ten
    thousand places against sixty thousand grid cells is 600 million comparisons done
    straight; this makes it a few million."""
    bi, bj = int(math.floor(lat / BUCKET)), int(math.floor(lon / BUCKET))
    best = 1e18
    for r in range(0, 40):
        if best < 1e17:
            # a ring r buckets out cannot be nearer than (r-1) whole buckets
            floor_mi = (r - 1) * BUCKET * 69.0 * min(1.0, coslat if coslat > 0.2 else 0.2)
            if floor_mi * floor_mi > best:
                break
        hit = False
        for i in range(bi - r, bi + r + 1):
            for j in range(bj - r, bj + r + 1):
                if r and max(abs(i - bi), abs(j - bj)) != r:
                    continue
                for plat, plon in g.get((i, j), ()):
                    hit = True
                    dy = (plat - lat) * 69.0
                    dx = (plon - lon) * 69.0 * coslat
                    dd = dx * dx + dy * dy
                    if dd < best:
                        best = dd
        if hit and r > 2 and best < 1e17:
            pass
    return math.sqrt(best) if best < 1e17 else None


def distance_png(geo: dict, places: list, out: Path, w=1200, step=0.18):
    """Every point in the lower forty-eight, shaded by how far it is from the nearest
    wing counter. Drawn as pixels rather than sixty thousand SVG rectangles, so the page
    stays light. Alaska and Hawaii are left off: the grid would run over open ocean and
    the insets would lie about distance."""
    fit = usmap.fit_states(geo, w)
    h = int(fit["h"])
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))   # transparent, so it sits on either theme
    d = ImageDraw.Draw(img)
    rings = [r for _, r, z in _rings(geo) ]
    pts = [(p["lat"], p["lon"]) for p in places if p.get("lat") is not None]
    if not pts:
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "PNG", optimize=True)
        return {"cuts": [], "ramp": [], "worst": [], "cells": 0, "median": 0}
    g = _buckets(pts)
    cuts = [3, 6, 10, 18, 30, 60]          # miles; the legend prints these
    colours = [hexrgb(c) for c in RAMP][::-1]   # near = dark
    # one cell is `step` degrees; on screen it is that much of the projected width
    x0, y0 = usmap.project(-100.0, 40.0, fit)
    x1, y1 = usmap.project(-100.0 + step, 40.0 + step, fit)
    cell_w, cell_h = abs(x1 - x0) + 1.2, abs(y1 - y0) + 1.2
    far = []
    lat = 24.0
    while lat <= 49.5:
        lon = -125.2
        coslat = math.cos(math.radians(lat))
        while lon <= -66.5:
            if inside(rings, lon, lat):
                mi = _nearest_mi(g, lat, lon, coslat)
                if mi is not None:
                    far.append((mi, lat, lon))
                    band = next((i for i, c in enumerate(cuts) if mi <= c), len(cuts))
                    x, y = usmap.project(lon, lat, fit, "l48")
                    d.rectangle([x, y - cell_h, x + cell_w, y], fill=colours[band])
            lon += step
        lat += step
    # state edges over the top, and the places as small dark marks
    for st, ring, z in _rings(geo):
        pl = [usmap.project(x, y, fit, "l48") for x, y in ring]
        d.line(pl + [pl[0]], fill=(150, 140, 122, 210), width=2)
    for plat, plon in pts:
        if usmap.zone(plon, plat) != "l48":
            continue
        x, y = usmap.project(plon, plat, fit, "l48")
        d.ellipse([x - 1.4, y - 1.4, x + 1.4, y + 1.4], fill=(24, 18, 14, 215))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    far.sort(reverse=True)
    return {"cuts": cuts, "ramp": RAMP[::-1], "worst": far[:6], "cells": len(far),
            "median": sorted(x[0] for x in far)[len(far) // 2] if far else 0}


# ------------------------------------------------------------------ small maps

def locator_svg(lat, lon, others: list, w=430, span=1.4, label=""):
    """One place at the centre, its neighbours around it, the two states inset."""
    box = (lon - span, lat - span * 0.62, lon + span, lat + span * 0.62)
    h = int(w * 0.62)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Map of the country around {E(label or "this place")}">',
           f'<rect width="{w}" height="{h}" fill="var(--chip)" rx="10"/>']
    for o in others:
        if o.get("lat") is None:
            continue
        if not (box[0] <= o["lon"] <= box[2] and box[1] <= o["lat"] <= box[3]):
            continue
        x, y = project(o["lon"], o["lat"], w, h, box)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="var(--mute)" opacity=".75"><title>{E(o["name"])}</title></circle>')
    x, y = project(lon, lat, w, h, box)
    out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="var(--donut)" opacity=".22"/>'
               f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="var(--donut)" stroke="var(--panel)" stroke-width="2.5"/>')
    out.append(f'<text x="10" y="{h - 10}" style="font:600 11px -apple-system,sans-serif" fill="var(--mute)">'
               f'about {span * 69:.0f} miles across</text>')
    out.append("</svg>")
    return "".join(out)


def where_svg(geo: dict, pts: list, w=430, title=""):
    """The country with a set of places lit — the answer to "where is this style"."""
    fit = usmap.fit_states(geo, w)
    h = fit["h"]
    out = [f'<svg viewBox="0 0 {w} {h:.0f}" role="img" aria-label="Where {E(title)} is found">']
    for st, ring, z in _rings(geo, insets=True):
        pp = " ".join(f"{x:.1f},{y:.1f}" for x, y in (usmap.project(a, b, fit, z) for a, b in ring))
        out.append(f'<polygon points="{pp}" fill="var(--chip)" stroke="var(--mute)" stroke-width=".8"/>')
    for p in pts:
        if p.get("lat") is None:
            continue
        x, y = usmap.project(p["lon"], p["lat"], fit)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="var(--donut)" stroke="var(--panel)" stroke-width="1.5">'
                   f'<title>{E(p.get("name", ""))}</title></circle>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ charts

def timeline_svg(rows: list, w=760):
    """One stem per pit, by the year it opened. Rows stack where years collide."""
    if not rows:
        return ""
    years = [y for y, _ in rows]
    lo, hi = min(years) // 10 * 10, (max(years) // 10 + 1) * 10
    h, base = 300, 232
    px = lambda y: 52 + (y - lo) / (hi - lo) * (w - 96)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="When the pits opened, {lo} to {hi}">']
    for t in range(lo, hi + 1, 10):
        out.append(f'<line x1="{px(t):.1f}" y1="34" x2="{px(t):.1f}" y2="{base}" stroke="var(--line)" stroke-width="1"/>'
                   f'<text x="{px(t):.1f}" y="{base + 22}" text-anchor="middle" fill="var(--mute)" '
                   f'style="font:600 12px -apple-system,sans-serif">{t}</text>')
    seen: dict = {}
    for y, name in sorted(rows):
        k = round(px(y) / 9)
        lvl = seen.get(k, 0)
        seen[k] = lvl + 1
        yy = base - 14 - lvl * 15
        out.append(f'<line x1="{px(y):.1f}" y1="{base}" x2="{px(y):.1f}" y2="{yy:.1f}" stroke="var(--donut)" stroke-width="2" opacity=".55"/>'
                   f'<circle cx="{px(y):.1f}" cy="{yy:.1f}" r="5" fill="var(--donut)"><title>{E(name)} — {y}</title></circle>')
    out.append(f'<line x1="40" y1="{base}" x2="{w - 30}" y2="{base}" stroke="var(--ink)" stroke-width="2"/>')
    out.append("</svg>")
    return "".join(out)


def bars_svg(rows: list, w=760, unit="", rowh=30, left=190):
    """Horizontal bars, one hue, value at the end of each. The plainest honest form."""
    if not rows:
        return ""
    top = max(v for _, v in rows)
    if not top:          # nothing counted yet — draw the labels, not a divide-by-zero
        top = 1
    h = len(rows) * rowh + 16
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{E(unit or "counts")}">']
    for i, (label, v) in enumerate(rows):
        y = 8 + i * rowh
        bw = (w - left - 74) * v / top
        out.append(f'<text x="{left - 12}" y="{y + rowh * 0.62:.0f}" text-anchor="end" fill="var(--ink)" '
                   f'style="font:600 14px -apple-system,sans-serif">{E(label)}</text>'
                   f'<rect x="{left}" y="{y + 4}" width="{max(bw, 2):.1f}" height="{rowh - 12}" rx="4" fill="var(--donut)"/>'
                   f'<text x="{left + bw + 10:.1f}" y="{y + rowh * 0.62:.0f}" fill="var(--mute)" '
                   f'style="font:600 13px -apple-system,sans-serif">{v}</text>')
    out.append("</svg>")
    return "".join(out)


DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
DAY_NAME = {"Mo": "Monday", "Tu": "Tuesday", "We": "Wednesday", "Th": "Thursday", "Fr": "Friday", "Sa": "Saturday", "Su": "Sunday"}


def open_days(hours_strings: list) -> dict:
    """Expand OpenStreetMap opening_hours into a count per weekday. Ranges like Mo-Sa are
    expanded; a day named with 'off' is removed again."""
    count = {d: 0 for d in DAYS}
    for s in hours_strings:
        days = set()
        for part in s.split(";"):
            part = part.strip()
            spec = re.findall(r"\b(Mo|Tu|We|Th|Fr|Sa|Su)\b(?:\s*-\s*(Mo|Tu|We|Th|Fr|Sa|Su))?", part)
            got = set()
            for a, b in spec:
                if b:
                    i, j = DAYS.index(a), DAYS.index(b)
                    got |= set(DAYS[i:j + 1] if i <= j else DAYS[i:] + DAYS[:j + 1])
                else:
                    got.add(a)
            if "off" in part.lower() or "closed" in part.lower():
                days -= got
            elif got:
                days |= got
            elif re.search(r"24/7", part):
                days |= set(DAYS)
        for d in days:
            count[d] += 1
    return count


def kin_matrix_svg(edges: list, types: list, labels: dict, w=700):
    """Which kind of page points at which. A square of cells, one hue, darker where more
    links run — the shape of the site's own argument."""
    n = len(types)
    cell = (w - 150) / n
    h = int(cell * n + 150)
    m: dict = {}
    for e in edges:
        m[(e["from_type"], e["to_type"])] = m.get((e["from_type"], e["to_type"]), 0) + 1
    top = max(m.values()) if m else 1
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="A matrix of which kinds of page link to which">']
    for i, a in enumerate(types):
        y = 96 + i * cell
        out.append(f'<text x="{140 - 10}" y="{y + cell * 0.62:.0f}" text-anchor="end" fill="var(--ink)" '
                   f'style="font:600 13px -apple-system,sans-serif">{E(labels.get(a, a))}</text>')
        for j, b in enumerate(types):
            x = 140 + j * cell
            v = m.get((a, b), 0)
            t = (v / top) ** 0.55
            col = RAMP[min(len(RAMP) - 1, int(t * (len(RAMP) - 1) + 0.0001))] if v else "var(--chip)"
            out.append(f'<rect x="{x + 1.5:.1f}" y="{y + 1.5:.1f}" width="{cell - 3:.1f}" height="{cell - 3:.1f}" rx="3" '
                       f'fill="{col}"><title>{E(labels.get(a, a))} → {E(labels.get(b, b))}: {v}</title></rect>')
            if v and t > 0.45:
                out.append(f'<text x="{x + cell / 2:.1f}" y="{y + cell * 0.62:.0f}" text-anchor="middle" fill="#fff" '
                           f'style="font:600 12px -apple-system,sans-serif">{v}</text>')
    for j, b in enumerate(types):
        x = 140 + j * cell + cell / 2
        out.append(f'<text transform="translate({x:.1f},88) rotate(-52)" fill="var(--ink)" '
                   f'style="font:600 13px -apple-system,sans-serif">{E(labels.get(b, b))}</text>')
    out.append(f'<text x="140" y="{h - 16}" fill="var(--mute)" style="font:400 12.5px -apple-system,sans-serif">'
               f'row points at column · darkest cell = {top} links</text>')
    out.append("</svg>")
    return "".join(out)


def ramp_legend(cuts: list, ramp: list, unit: str) -> str:
    """A numbered key. The ramp's pale end recedes into the page, so the numbers do the work."""
    n = len(ramp)
    cells = []
    for i, c in enumerate(ramp):
        lab = ("under " + str(cuts[0])) if i == 0 else (f"{cuts[i-1]}–{cuts[i]}" if i < len(cuts) else f"over {cuts[-1]}")
        cells.append(f'<span style="display:inline-flex;flex-direction:column;align-items:center;gap:.2rem">'
                     f'<i style="width:3.1rem;height:.85rem;background:{c};border-radius:2px;display:block"></i>'
                     f'<small style="font-size:.72rem;color:var(--mute)">{E(lab)}</small></span>')
    return (f'<div style="display:flex;gap:.35rem;flex-wrap:wrap;align-items:flex-end;margin:.6rem 0 .2rem">'
            + "".join(cells) + f'<span style="font-size:.8rem;color:var(--mute);margin-left:.5rem">{E(unit)}</span></div>')


# ------------------------------------------------------------------ the week

DAY_ORDER = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
DAY_ONE = {"Mo": "M", "Tu": "T", "We": "W", "Th": "T", "Fr": "F", "Sa": "S", "Su": "S"}


def day_strip(days: dict, w=176, h=26, title=True) -> str:
    """Seven boxes, Monday to Sunday. Filled means open, hollow means closed, and a dashed
    outline means nobody has told us — which is not the same thing and never drawn as if
    it were. Sunday is drawn apart because Sunday is the question people ask."""
    if not days:
        return ""
    cell = (w - 10) / 7
    out = [f'<svg class="daystrip" viewBox="0 0 {w} {h}" role="img" aria-label="'
           + E(", ".join(f"{DAY_NAME[d]} {days.get(d, 'unknown')}" for d in DAY_ORDER)) + '">']
    for i, d in enumerate(DAY_ORDER):
        st = days.get(d, "unknown")
        x = i * cell + (10 if d == "Su" else 0)
        fill = {"open": "var(--donut)", "closed": "none", "unknown": "none"}[st]
        stroke = {"open": "var(--donut)", "closed": "var(--mute)", "unknown": "var(--line)"}[st]
        dash = ' stroke-dasharray="2.5 2.5"' if st == "unknown" else ""
        col = {"open": "#fff", "closed": "var(--mute)", "unknown": "var(--line)"}[st]
        out.append(f'<rect x="{x + 1.5:.1f}" y="3" width="{cell - 3:.1f}" height="{h - 8}" rx="4" fill="{fill}" '
                   f'stroke="{stroke}" stroke-width="1.6"{dash}/>'
                   f'<text x="{x + cell / 2:.1f}" y="{h / 2 + 4.5:.0f}" text-anchor="middle" fill="{col}" '
                   f'style="font:700 11px -apple-system,sans-serif">{DAY_ONE[d]}</text>')
        if title:
            out.append(f'<title>{E(DAY_NAME[d])}: {E(st)}</title>')
    out.append("</svg>")
    return "".join(out)


def day_key() -> str:
    return ('<span class="daykey"><i class="on"></i> open <i class="off"></i> closed '
            '<i class="unk"></i> not published</span>')


DAY_CSS = """
.daystrip{height:26px;width:176px;display:block}
.daykey{font-size:.76rem;color:var(--mute);display:inline-flex;align-items:center;gap:.3rem;font-family:var(--ui,sans-serif)}
.daykey i{width:.7rem;height:.9rem;border-radius:3px;display:inline-block;margin-left:.5rem}
.daykey i.on{background:var(--donut);border:1.6px solid var(--donut)}
.daykey i.off{border:1.6px solid var(--mute)}
.daykey i.unk{border:1.6px dashed var(--line)}
.sunday-yes{color:var(--donut);font-weight:700}
.sunday-no{color:var(--mute)}
"""
