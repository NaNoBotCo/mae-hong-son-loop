#!/usr/bin/env python3
"""geo.py — the projection and the drawing primitives every map on this site shares.

One projection: a transverse-Mercator-ish local conic is overkill for a 200 km box, so
this uses an equirectangular projection with the x axis scaled by cos(mean latitude).
At 18–20 degrees north over a 1.7-degree box the distortion that remains is under a
percent, which is far below the width of a drawn road.

Everything returns SVG strings. No external library, no web font, no network request.
"""
from __future__ import annotations

import math

# The corridor every map is drawn in. South, West, North, East. Fitted to the drawn
# geometry with a small margin rather than guessed, so no map ships with empty bands.
BOX = (18.09, 97.86, 19.61, 99.04)


def fit(lines, pad_deg=0.045, pad_e=0.055):
    """A box around every drawn line, so a map is never mostly empty."""
    pts = [p for line in lines for p in line]
    if not pts:
        return BOX
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    return (min(lats) - pad_deg, min(lons) - pad_deg, max(lats) + pad_deg, max(lons) + pad_e)


class Proj:
    def __init__(self, box=BOX, width=900, pad=14):
        self.s, self.w, self.n, self.e = box
        self.kx = math.cos(math.radians((self.s + self.n) / 2))
        self.pad = pad
        span_x = (self.e - self.w) * self.kx
        span_y = self.n - self.s
        self.width = width
        self.scale = (width - 2 * pad) / span_x
        self.height = span_y * self.scale + 2 * pad

    def xy(self, lat, lon):
        x = self.pad + (lon - self.w) * self.kx * self.scale
        y = self.pad + (self.n - lat) * self.scale
        return x, y

    def path(self, line, every=1):
        if not line:
            return ""
        pts = line[::every] if every > 1 else line
        if pts[-1] is not line[-1]:
            pts = list(pts) + [line[-1]]
        d = []
        for i, (lat, lon) in enumerate(pts):
            x, y = self.xy(lat, lon)
            d.append(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}")
        return "".join(d)


def band_class(band: str) -> str:
    return {"gentle": "g", "busy": "b", "hard": "h", "relentless": "r"}.get(band, "b")


def road_layer(p: Proj, lines: dict, cls="road") -> str:
    """Every road drawn plain, as the base under anything coloured."""
    out = []
    for ref, line in lines.items():
        if line:
            out.append(f'<path class="{cls}" d="{p.path(line)}"><title>Route {ref}</title></path>')
    return "".join(out)


def demand_layer(p: Proj, density: list) -> str:
    """The road coloured by how much steering it asks for. Each window is its own path so
    the colour changes where the road does."""
    out = []
    for d in density:
        x1, y1 = p.xy(*d["from"])
        x2, y2 = p.xy(*d["to"])
        out.append(f'<line class="dm dm-{band_class(d["band"])}" x1="{x1:.1f}" y1="{y1:.1f}" '
                   f'x2="{x2:.1f}" y2="{y2:.1f}"><title>{d["per_km"]} curves/km · '
                   f'{d["hairpins"]} hairpin</title></line>')
    return "".join(out)


def demand_path_layer(p: Proj, density: list, pts_by_window: list | None = None) -> str:
    out = []
    for d in density:
        seg = [d["from"], d["mid"], d["to"]]
        out.append(f'<path class="dm dm-{band_class(d["band"])}" d="{p.path(seg)}">'
                   f'<title>{d["per_km"]} curves/km · {d["hairpins"]} hairpin · {d["km"]} km</title></path>')
    return "".join(out)


def dots(p: Proj, rows: list, cls="dot", r=3.2, label=False) -> str:
    """Pins, and optionally their names. A label near the right edge is anchored to the
    end and drawn to the LEFT of its pin, because a label that runs off the canvas is
    worse than one on the other side of the dot."""
    out = []
    for row in rows:
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None:
            continue
        x, y = p.xy(lat, lon)
        name = (row.get("name") or "").replace("&", "&amp;").replace("<", "&lt;")
        extra = row.get("title") or name
        out.append(f'<circle class="{cls} {row.get("cls","")}" cx="{x:.1f}" cy="{y:.1f}" r="{r}">'
                   f'<title>{extra}</title></circle>')
        if label and name:
            # roughly 6.4 px per character at the label's size and weight
            flip = (x + 8 + len(name) * 6.4) > p.width
            lx = x - 7 if flip else x + 7
            anchor = ' text-anchor="end"' if flip else ""
            out.append(f'<text class="lbl"{anchor} x="{lx:.1f}" y="{y + 3.5:.1f}">{name}</text>')
    return "".join(out)


def scalebar(p: Proj, km=50) -> str:
    """A bar whose length is computed through the projection rather than assumed."""
    lat = p.s + (p.n - p.s) * 0.06
    dlon = km / (111.32 * p.kx)
    x1, y1 = p.xy(lat, p.w + (p.e - p.w) * 0.06)
    x2, _ = p.xy(lat, p.w + (p.e - p.w) * 0.06 + dlon)
    return (f'<g class="scale"><line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y1:.1f}"/>'
            f'<line x1="{x1:.1f}" y1="{y1 - 4:.1f}" x2="{x1:.1f}" y2="{y1 + 4:.1f}"/>'
            f'<line x1="{x2:.1f}" y1="{y1 - 4:.1f}" x2="{x2:.1f}" y2="{y1 + 4:.1f}"/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{y1 - 7:.1f}">{km} km</text></g>')


def sparkline(values: list, width=120, height=26, cls="spark") -> str:
    """Twelve monthly values, drawn small. Used for a town's air through the year."""
    vals = [v for v in values if v is not None]
    if not vals:
        return ""
    lo, hi = 0, max(vals) or 1
    n = len(values)
    step = width / max(n - 1, 1)
    pts = []
    for i, v in enumerate(values):
        if v is None:
            continue
        x = i * step
        y = height - (v - lo) / (hi - lo) * (height - 2) - 1
        pts.append(f"{'M' if not pts else 'L'}{x:.1f} {y:.1f}")
    return (f'<svg class="{cls}" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-hidden="true"><path d="{"".join(pts)}"/></svg>')
