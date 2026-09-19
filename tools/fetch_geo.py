"""fetch_geo.py — the US state outlines the maps are drawn from.

Natural Earth, Admin 1 states/provinces, 1:50m, public domain. Fetched once and
kept in data/geo/states.json: every US state and DC, rings simplified to about a
kilometre, coordinates to 3 decimal places. Run it again only to refresh.

    python3 tools/fetch_geo.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEO, jdump  # noqa: E402

URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
       "geojson/ne_50m_admin_1_states_provinces.geojson")
CREDIT = "Natural Earth, Admin 1 – States, Provinces, 1:50m (public domain)"
SITE = "https://www.naturalearthdata.com/downloads/50m-cultural-vectors/"
TOL = 0.01          # degrees, Douglas-Peucker; ~1 km
MIN_RING = 0.02     # drop rings whose bounding box is smaller than this (sandbars)


def _perp(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return ((x - (x1 + t * dx)) ** 2 + (y - (y1 + t * dy)) ** 2) ** 0.5


def simplify(pts: list, tol: float) -> list:
    """Douglas-Peucker, iterative so a long coastline does not blow the stack."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        far, d = -1, tol
        for k in range(i + 1, j):
            dk = _perp(pts[k], pts[i], pts[j])
            if dk > d:
                far, d = k, dk
        if far > 0:
            keep[far] = True
            stack.append((i, far))
            stack.append((far, j))
    return [p for p, k in zip(pts, keep) if k]


def rings_of(geom: dict) -> list:
    if geom["type"] == "Polygon":
        return [geom["coordinates"][0]]
    if geom["type"] == "MultiPolygon":
        return [poly[0] for poly in geom["coordinates"]]
    return []


def main() -> int:
    print(f"fetching {URL}")
    with urllib.request.urlopen(URL, timeout=180) as r:
        gj = json.loads(r.read().decode("utf-8"))
    out = []
    for f in gj["features"]:
        p = f["properties"]
        if p.get("iso_a2") != "US":
            continue
        iso = p.get("iso_3166_2") or ""
        if not iso.startswith("US-"):
            continue
        rings = []
        for ring in rings_of(f["geometry"]):
            xs = [c[0] for c in ring]
            ys = [c[1] for c in ring]
            if max(xs) - min(xs) < MIN_RING and max(ys) - min(ys) < MIN_RING:
                continue
            s = simplify([(round(c[0], 3), round(c[1], 3)) for c in ring], TOL)
            if len(s) > 3:
                rings.append([[x, y] for x, y in s])
        if not rings:
            continue
        out.append({"iso": iso, "name": p.get("name") or iso, "rings": rings})
    out.sort(key=lambda s: s["iso"])
    jdump({"source": CREDIT, "url": SITE, "fetched_from": URL,
           "coords": "[lon, lat], 3 dp (~100 m), Douglas-Peucker at 0.01°",
           "states": out}, GEO / "states.json", indent=None)
    kb = (GEO / "states.json").stat().st_size / 1024
    print(f"wrote {len(out)} states, {sum(len(r) for s in out for r in s['rings'])} points, {kb:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
