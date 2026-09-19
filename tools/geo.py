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
        # integers, and no repeated point. A tenth of a pixel is not visible at any
        # width this draws at, and the road polylines were most of the map's bytes.
        d, last = [], None
        for i, (lat, lon) in enumerate(pts):
            x, y = self.xy(lat, lon)
            xy = (round(x), round(y))
            if xy == last:
                continue
            d.append(f"{'M' if not d else 'L'}{xy[0]} {xy[1]}")
            last = xy
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


_SWARM_N = 0


def swarm(p: Proj, rows: list, cls="dot", r=2.4) -> str:
    """Hundreds of harvested places as one reusable shape.

    A <circle> with a <title> and a class costs about 130 bytes, and the coffee index
    put twelve hundred of them on the page: 158 KB of the 216 KB it weighed, against
    19 KB for the list of places anyone could actually read. A <use> at integer
    coordinates is a quarter of that, and a two-pixel dot was never a hover target."""
    out, seen = [], set()
    for row in rows:
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None:
            continue
        x, y = p.xy(lat, lon)
        k = (round(x), round(y))
        if k in seen:                 # two shops at one pixel are one pixel
            continue
        seen.add(k)
        out.append((k[0], k[1]))
    if not out:
        return ""
    # a one-character id: two swarms on a page must not collide, and the reference is
    # repeated once per dot, so the name's length is paid a thousand times over
    global _SWARM_N
    _SWARM_N += 1
    sid = f"s{_SWARM_N}"
    body = "".join(f'<use href="#{sid}" x="{x}" y="{y}"/>' for x, y in out)
    return (f'<defs><circle id="{sid}" cx="0" cy="0" r="{r}"/></defs>'
            f'<g class="{cls}">{body}</g>")'.replace('</g>")', "</g>"))


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


# ---------------------------------------------------------------- the basemap
# A route drawn on an empty rectangle reads as a squiggle. These layers give it a place
# to be: ground coloured by height, then water, then the provincial line, then the road.

RELIEF = [(0, "#e9e2d2"), (300, "#ddd6c2"), (600, "#d0c8b0"), (900, "#c2b99c"),
          (1200, "#b3a988"), (1500, "#a39873"), (1800, "#93875f"), (2200, "#847849")]
RELIEF_DARK = [(0, "#1b1812"), (300, "#211d16"), (600, "#28231a"), (900, "#2f291e"),
               (1200, "#372f22"), (1500, "#3f3626"), (1800, "#473d2b"), (2200, "#504530")]


def _regular(grid: list, step: float):
    """Put the fetched points back on a regular lattice, and fill the holes.

    The elevation API throttles, so a long fetch comes back with gaps — whole batches
    missing, which on a map are stripes. Missing cells are filled from their neighbours
    by inverse-distance over a widening ring. That is interpolation, not measurement, and
    it is fine for shading a hillside; it is not a source for how high anything is.
    """
    if not grid:
        return [], [], {}
    lats = sorted({round(g["lat"], 4) for g in grid})
    lons = sorted({round(g["lon"], 4) for g in grid})
    # rebuild a complete lattice from the observed extent and the known step
    lat0, lat1 = lats[0], lats[-1]
    lon0, lon1 = lons[0], lons[-1]
    nr = int(round((lat1 - lat0) / step)) + 1
    nc = int(round((lon1 - lon0) / step)) + 1
    Z = [[None] * nc for _ in range(nr)]
    for g in grid:
        r = int(round((g["lat"] - lat0) / step))
        c = int(round((g["lon"] - lon0) / step))
        if 0 <= r < nr and 0 <= c < nc:
            Z[r][c] = float(g["m"])
    holes = [(r, c) for r in range(nr) for c in range(nc) if Z[r][c] is None]
    for r, c in holes:
        acc = wsum = 0.0
        for rad in (1, 2, 3, 4):
            for dr in range(-rad, rad + 1):
                for dc in range(-rad, rad + 1):
                    if max(abs(dr), abs(dc)) != rad:
                        continue
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < nr and 0 <= cc < nc and Z[rr][cc] is not None:
                        wt = 1.0 / (dr * dr + dc * dc)
                        acc += Z[rr][cc] * wt
                        wsum += wt
            if wsum:
                break
        Z[r][c] = acc / wsum if wsum else 0.0
    return (lat0, lon0, step, nr, nc), Z, len(holes)


def _upsample(Z, nr, nc, f=3):
    """Bilinear, so a 2 km lattice stops looking like 2 km squares."""
    out = [[0.0] * ((nc - 1) * f + 1) for _ in range((nr - 1) * f + 1)]
    for r in range((nr - 1) * f + 1):
        fr = r / f
        r0 = min(int(fr), nr - 2)
        tr = fr - r0
        for c in range((nc - 1) * f + 1):
            fc = c / f
            c0 = min(int(fc), nc - 2)
            tc = fc - c0
            a = Z[r0][c0] * (1 - tc) + Z[r0][c0 + 1] * tc
            b = Z[r0 + 1][c0] * (1 - tc) + Z[r0 + 1][c0 + 1] * tc
            out[r][c] = a * (1 - tr) + b * tr
    return out


# Green in the valleys, brown on the flanks, pale on the tops. The ramp does the reading;
# the hillshade does the drama.
RAMP = [(0, (108, 132, 88)), (250, (126, 142, 92)), (500, (150, 152, 98)),
        (750, (166, 150, 104)), (1000, (176, 146, 110)), (1250, (184, 150, 122)),
        (1500, (196, 166, 146)), (1750, (214, 196, 182)), (2100, (236, 228, 220))]
RAMP_DARK = [(0, (26, 34, 26)), (250, (32, 40, 28)), (500, (40, 44, 30)),
             (750, (48, 46, 32)), (1000, (56, 48, 36)), (1250, (64, 52, 42)),
             (1500, (74, 60, 52)), (1750, (88, 74, 66)), (2100, (104, 94, 88))]


def _ramp(m: float, ramp) -> tuple:
    if m <= ramp[0][0]:
        return ramp[0][1]
    for (a, ca), (b, cb) in zip(ramp, ramp[1:]):
        if m <= b:
            t = (m - a) / (b - a) if b > a else 0
            return tuple(round(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
    return ramp[-1][1]


def terrain_layer(p: Proj, grid: list, step_deg: float, dark=False, upscale=3,
                  az=315.0, alt=42.0, zf=7.0) -> str:
    """Hypsometric tint and hillshade, baked to one colour per cell so the whole thing is
    a single flat list of rects rather than two stacked layers."""
    import math
    meta, Z, holes = _regular(grid, step_deg)
    if not Z:
        return ""
    lat0, lon0, step, nr, nc = meta
    U = _upsample(Z, nr, nc, upscale)
    ur, uc = len(U), len(U[0])
    ustep = step / upscale
    mid = math.radians(lat0 + (nr - 1) * step / 2)
    dy = ustep * 111320.0
    dx = ustep * 111320.0 * math.cos(mid)
    az_r, alt_r = math.radians(360 - az + 90), math.radians(alt)
    ramp = RAMP_DARK if dark else RAMP
    half = ustep / 2
    out = ['<g class="terrain">']
    for r in range(ur):
        for c in range(uc):
            m = U[r][c]
            w = U[r][max(c - 1, 0)]; e = U[r][min(c + 1, uc - 1)]
            s_ = U[max(r - 1, 0)][c]; n = U[min(r + 1, ur - 1)][c]
            dzdx = (e - w) / (2 * dx) * zf
            dzdy = (n - s_) / (2 * dy) * zf
            slope = math.atan(math.hypot(dzdx, dzdy))
            aspect = math.atan2(dzdy, -dzdx)
            sh = (math.sin(alt_r) * math.cos(slope)
                  + math.cos(alt_r) * math.sin(slope) * math.cos(az_r - aspect))
            sh = max(0.0, min(1.0, sh))
            col = _ramp(m, ramp)
            k = 0.55 + 0.9 * sh          # multiply the tint by the light
            col = tuple(max(0, min(255, round(v * k))) for v in col)
            lat = lat0 + r * ustep
            lon = lon0 + c * ustep
            x1, y1 = p.xy(lat + half, lon - half)
            x2, y2 = p.xy(lat - half, lon + half)
            wpx, hpx = abs(x2 - x1), abs(y2 - y1)
            if wpx < 0.2 or hpx < 0.2:
                continue
            out.append(f'<rect x="{min(x1,x2):.2f}" y="{min(y1,y2):.2f}" '
                       f'width="{wpx + 0.45:.2f}" height="{hpx + 0.45:.2f}" '
                       f'fill="#{col[0]:02x}{col[1]:02x}{col[2]:02x}"/>')
    out.append("</g>")
    return "".join(out)


def water_layer(p: Proj, base: dict, min_lake_pts: int = 24) -> str:
    """Lakes as filled shapes, rivers as lines. The lake list is mostly farm ponds, so
    only the ones with enough traced outline to be worth a shape are drawn."""
    out = ['<g class="water">']
    for ring in base.get("lakes", []):
        if len(ring) < min_lake_pts:
            continue
        d = p.path([tuple(c) for c in ring])
        if d:
            out.append(f'<path class="lake" d="{d}Z"/>')
    for r in base.get("rivers", []):
        total = sum(len(l) for l in r["lines"])
        cls = "river big" if total > 200 else "river"
        for line in r["lines"]:
            d = p.path([tuple(c) for c in line])
            if d:
                out.append(f'<path class="{cls}" d="{d}"><title>{r["name"]}</title></path>')
    out.append("</g>")
    return "".join(out)


def boundary_layer(p: Proj, base: dict) -> str:
    out = ['<g class="bound">']
    for seg in base.get("boundary", []):
        d = p.path([tuple(c) for c in seg])
        if d:
            out.append(f'<path d="{d}"/>')
    out.append("</g>")
    return "".join(out)


def star(x: float, y: float, r: float = 6.0) -> str:
    """A five-pointed star, points up, centred on (x, y)."""
    import math
    pts = []
    for i in range(10):
        a = math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(f"{x + rad * math.cos(a):.1f},{y - rad * math.sin(a):.1f}")
    return " ".join(pts)


def stars(p: Proj, rows: list, cls="star", r=6.0, label=False) -> str:
    """Stops, as stars. Anything that is a destination rather than a waypoint."""
    out = []
    for row in rows:
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None:
            continue
        x, y = p.xy(lat, lon)
        name = (row.get("name") or "").replace("&", "&amp;").replace("<", "&lt;")
        poly = (f'<polygon class="{cls} {row.get("cls","")}" points="{star(x, y, r)}">'
                f'<title>{row.get("title") or name}</title></polygon>')
        # a star marks a place that is written up, so it goes to the write-up
        href = row.get("href")
        out.append(f'<a href="{href}" class="starlink">{poly}</a>' if href else poly)
        if label and name:
            flip = (x + 9 + len(name) * 6.4) > p.width
            lx = x - 8 if flip else x + 8
            anchor = ' text-anchor="end"' if flip else ""
            out.append(f'<text class="lbl"{anchor} x="{lx:.1f}" y="{y + 3.5:.1f}">{name}</text>')
    return "".join(out)

def metre_bar(p: Proj, m: int = 500) -> str:
    """A scale bar in metres, for a map zoomed in far enough that kilometres are silly."""
    lat = p.s + (p.n - p.s) * 0.08
    dlon = (m / 1000.0) / (111.32 * p.kx)
    x1, y1 = p.xy(lat, p.w + (p.e - p.w) * 0.07)
    x2, _ = p.xy(lat, p.w + (p.e - p.w) * 0.07 + dlon)
    return (f'<g class="scale"><line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y1:.1f}"/>'
            f'<line x1="{x1:.1f}" y1="{y1 - 4:.1f}" x2="{x1:.1f}" y2="{y1 + 4:.1f}"/>'
            f'<line x1="{x2:.1f}" y1="{y1 - 4:.1f}" x2="{x2:.1f}" y2="{y1 + 4:.1f}"/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{y1 - 7:.1f}">{m} m</text></g>')


# The svg fills its container's width, so the viewBox aspect is what decides how tall
# the figure lands on the page. Cap height against width; a genuinely north-south
# stretch is letterboxed rather than allowed to run a thousand pixels down the page.
TALLEST = 0.8
SHORTEST = 0.42


def closeup(window: dict, width: int = 520, label_every: int = 1) -> str:
    """One curve-density window, drawn on its own at the scale of its own bends.

    The whole-loop map is six hundred kilometres across, at which width a two-kilometre
    stretch is four millimetres of line and every bend in it is a rounding error. Drawn
    to its own bounding box it is a shape, which is what somebody arguing about a road
    actually wants to see. Each mark is a direction reversal the counter scored: the
    big ones are the hairpins."""
    line = [tuple(c) for c in (window.get("line") or [])]
    if len(line) < 3:
        return ""
    lats = [c[0] for c in line]
    lons = [c[1] for c in line]
    # pad each axis by its own span. Padding both by the longer one leaves the short
    # axis swimming in margin, which is most of a frame spent on nothing.
    dy, dx = max(lats) - min(lats), max(lons) - min(lons)
    cy, cx = (max(lats) + min(lats)) / 2, (max(lons) + min(lons)) / 2
    kx = math.cos(math.radians(cy))
    # A near-vertical stretch has almost no longitude span, and the projection scales to
    # width: the canvas came out 1,220 px tall for two kilometres of road.
    wx, wy = dx * kx, dy
    if wy > wx * TALLEST:
        dx = (wy / TALLEST) / kx
    elif wy < wx * SHORTEST:
        # and the other way: an east-west stretch letterboxed to 79 px on a phone is a
        # sliver nobody can read the bends in
        dy = wx * SHORTEST
    py = (dy * 0.09) or 0.0015
    px = (dx * 0.09) or 0.0015
    box = (cy - dy / 2 - py, cx - dx / 2 - px, cy + dy / 2 + py, cx + dx / 2 + px)
    p = Proj(box=box, width=width, pad=10)
    out = [f'<svg viewBox="0 0 {p.width:.0f} {p.height:.0f}" class="closeup" role="img" '
           f'aria-label="The {window.get("km", 2)} km that asks the most, drawn close up">']
    d = p.path(line)
    out.append(f'<path class="cu-case" d="{d}"/>')
    out.append(f'<path class="cu-road {band_class(window.get("band", ""))}" d="{d}"/>')
    for a in (window.get("apex") or []):
        lat, lon, deg = a[0], a[1], (a[2] if len(a) > 2 else 0)
        x, y = p.xy(lat, lon)
        hard = deg >= 120
        r = 5.4 if hard else 3.4
        out.append(f'<circle class="cu-bend{" pin" if hard else ""}" cx="{x:.1f}" cy="{y:.1f}" '
                   f'r="{r}"><title>{deg:g}°{" — hairpin" if hard else ""}</title></circle>')
    # the ends, so the direction of travel is legible
    for c, cls in ((line[0], "start"), (line[-1], "end")):
        x, y = p.xy(c[0], c[1])
        out.append(f'<circle class="cu-cap {cls}" cx="{x:.1f}" cy="{y:.1f}" r="3"/>')
    ref = window.get("ref")
    if ref:
        # one plate at the start of the run, so the close-up names its own road
        x, y = p.xy(line[0][0], line[0][1])
        w = 9 + 7.6 * len(str(ref))
        out.append(f'<g class="shield"><rect x="{x - w / 2:.0f}" y="{y - 22:.0f}" '
                   f'width="{w:.0f}" height="17" rx="3"/>'
                   f'<text x="{x:.0f}" y="{y - 9:.0f}">{ref}</text></g>')
    out.append(metre_bar(p, 500))
    out.append("</svg>")
    return "".join(out)

def _chain_km(line) -> float:
    from harvest_osm import haversine
    return sum(haversine(line[i], line[i + 1]) for i in range(len(line) - 1))


def shields(p: Proj, roads: dict, per_km: float = 70.0, cap: int = 4,
            r: float = 0) -> str:
    """Route numbers on the map, the way they are on the road.

    Somebody reading this has a sign in front of them that says 1095, and a map with no
    number on it makes them do the translation themselves. Shields are spaced along each
    road rather than dropped at its midpoint, because Route 108 is three hundred
    kilometres and one label on it names only the middle.

    Placement skips anything outside the frame and anything that would sit on a shield
    already placed, so a junction where three roads meet does not stack three plates."""
    placed, out = [], []
    # the longest roads first: they have the most claim on the few legible positions
    order = sorted(roads.items(), key=lambda kv: -_road_km(kv[1]))
    for ref, rd in order:
        lines = rd.get("lines") or ([rd["line"]] if rd.get("line") else [])
        lines = sorted(lines, key=len, reverse=True)
        if not lines:
            continue
        km = _road_km(rd)
        want = max(1, min(cap, int(km / per_km + 0.5)))
        spots = []
        for i in range(want):
            frac = (i + 0.5) / want
            spots.append(_at_fraction(lines, frac))
        w = 9 + 7.6 * len(str(ref))
        h = 17
        for pt in spots:
            if not pt:
                continue
            x, y = p.xy(pt[0], pt[1])
            if not (4 <= x <= p.width - 4 and 4 <= y <= p.height - 4):
                continue
            box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if any(not (box[2] < q[0] - 5 or box[0] > q[2] + 5 or
                        box[3] < q[1] - 5 or box[1] > q[3] + 5) for q in placed):
                continue
            placed.append(box)
            out.append(
                f'<g class="shield"><rect x="{box[0]:.0f}" y="{box[1]:.0f}" '
                f'width="{w:.0f}" height="{h}" rx="3"/>'
                f'<text x="{x:.0f}" y="{y + 4.6:.0f}">{ref}</text></g>')
    return "".join(out)


def _road_km(rd: dict) -> float:
    if rd.get("km"):
        return float(rd["km"])
    lines = rd.get("lines") or ([rd["line"]] if rd.get("line") else [])
    return sum(_chain_km([tuple(c) for c in l]) for l in lines)


def _at_fraction(lines: list, frac: float):
    """A point `frac` of the way along the road, walking its chains end to end."""
    segs = [[tuple(c) for c in l] for l in lines if len(l) > 1]
    if not segs:
        return None
    lens = [_chain_km(sg) for sg in segs]
    total = sum(lens)
    if total <= 0:
        return segs[0][0]
    target = total * frac
    for sg, ln in zip(segs, lens):
        if target > ln:
            target -= ln
            continue
        from harvest_osm import haversine
        run = 0.0
        for i in range(len(sg) - 1):
            d = haversine(sg[i], sg[i + 1])
            if run + d >= target:
                return sg[i + 1]
            run += d
        return sg[-1]
    return segs[-1][-1]

def richardson(y: dict, deg: str = "4", width: int = 560, height: int = 240) -> str:
    """Count against ruler length, both axes logarithmic.

    A straight line here is the signature Richardson found in coastlines: halve the
    ruler, get a fixed multiple more of whatever you are counting, with no plateau to
    converge on. The flattening at the fine end is not the road running out of bends,
    it is OpenStreetMap running out of points."""
    steps = [s_ for s_ in y["step_m"]]
    vals = [y["grid"][str(s_)][deg] for s_ in steps]
    if not vals:
        return ""
    pad_l, pad_b, pad_t, pad_r = 44, 30, 12, 10
    x0, y0 = pad_l, height - pad_b
    w = width - pad_l - pad_r
    h = height - pad_b - pad_t
    lx = [math.log10(s_) for s_ in steps]
    ly = [math.log10(v) for v in vals]
    xmin, xmax = min(lx), max(lx)
    ymin, ymax = min(ly), max(ly)
    def px(v): return x0 + (v - xmin) / (xmax - xmin) * w
    def py(v): return y0 - (v - ymin) / (ymax - ymin) * h
    out = [f'<svg viewBox="0 0 {width} {height}" class="rich" role="img" '
           f'aria-label="Curves counted against ruler length, both axes logarithmic">']
    # axes
    out.append(f'<line class="ax" x1="{x0}" y1="{pad_t}" x2="{x0}" y2="{y0}"/>')
    out.append(f'<line class="ax" x1="{x0}" y1="{y0}" x2="{width - pad_r}" y2="{y0}"/>')
    for s_ in steps:
        x = px(math.log10(s_))
        out.append(f'<line class="grid" x1="{x:.0f}" y1="{pad_t}" x2="{x:.0f}" y2="{y0}"/>')
        lab = f"{s_} m" if s_ < 1000 else "1 km"
        out.append(f'<text class="tick" x="{x:.0f}" y="{y0 + 14:.0f}">{lab}</text>')
    for v in (min(vals), max(vals)):
        yy = py(math.log10(v))
        out.append(f'<text class="tick l" x="{x0 - 6}" y="{yy + 3.5:.0f}">{v:,}</text>')
    d = "".join(f"{'M' if i == 0 else 'L'}{px(lx[i]):.1f} {py(ly[i]):.1f}"
                for i in range(len(steps)))
    out.append(f'<path class="rline" d="{d}"/>')
    for i, s_ in enumerate(steps):
        x, yy = px(lx[i]), py(ly[i])
        cls = "rdot pub" if s_ == 30 else "rdot"
        out.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{yy:.1f}" r="{4.6 if s_ == 30 else 3.2}">'
                   f'<title>{vals[i]:,} at a {s_} m ruler</title></circle>')
        if s_ == 30:
            out.append(f'<text class="pubtag" x="{x:.0f}" y="{yy - 11:.0f}">published</text>')
    out.append("</svg>")
    return "".join(out)



# The basemap ships as its own file, so it carries its own styles. It is referenced by
# <image>, which is an isolated document: the page's stylesheet does not reach inside it.
BASEMAP_CSS = """
.relief rect{stroke:none}
.r0{fill:#e9e2d2}.r1{fill:#ddd6c2}.r2{fill:#d0c8b0}.r3{fill:#c2b99c}
.r4{fill:#b3a988}.r5{fill:#a39873}.r6{fill:#93875f}.r7{fill:#847849}
.lake{fill:#9fc9e0;stroke:#6aa9cd;stroke-width:.4;opacity:.95}
.river{fill:none;stroke:#6fb0d4;stroke-width:1.1;stroke-linecap:round;opacity:.9}
.river.big{stroke-width:2.6;stroke:#4f9ac4}
.bound path{fill:none;stroke:#6b5b3e;stroke-width:1.6;stroke-dasharray:8 6;opacity:.6}
@media (prefers-color-scheme:dark){
 .lake{fill:#1f4560;stroke:#2f6285}
 .river{stroke:#2f6285}.river.big{stroke:#3f7ea6}
 .bound path{stroke:#6f6248;opacity:.7}}
"""
