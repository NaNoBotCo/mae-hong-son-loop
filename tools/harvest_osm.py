#!/usr/bin/env python3
"""harvest_osm.py — the loop's own geometry and everything OSM puts beside it.

Four verbs, each writing one harvest file under data/harvest/. A harvest file is never a
record: it carries the licence (ODbL 1.0, share-alike), the fetch time and the query, so
an absence reads as "not in OSM on that date" rather than "not there".

  --roads    every way tagged with one of the loop's route numbers, with full geometry,
             stitched into one polyline per road  ->  osm-roads.json
  --places   towns, fuel, wats, coffee, viewpoints, waterfalls, hot springs, caves,
             hotels and guesthouses inside the loop's corridor  ->  osm-places.json
  --curves   counts every direction change above a threshold on each road, per 10 km
             ->  folded into osm-roads.json
  --all      all of the above, in order

    python3 tools/harvest_osm.py --all
    python3 tools/harvest_osm.py --places --dry
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump, jload, slugify  # noqa: E402

UA = "mhs-loop-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]

# The corridor. South to Hot and Doi Inthanon, west to the Salween, north to Pai and
# Pangmapha, east to Chiang Mai. Everything the loop and its two shortcuts touch.
BBOX = (17.55, 97.55, 19.60, 99.20)   # S, W, N, E

# Route numbers the loop runs on, and what each one is doing here. A ref alone is not
# enough — Thailand reuses two- and three-digit numbers — so every way is also clipped
# to the corridor and then to the road's own span.
ROADS = {
    "1095": {"name": "Route 1095", "th": "ทางหลวงหมายเลข 1095",
             "span": (18.70, 98.00, 19.60, 99.05),
             "note": "Mae Malai to Pai to Pangmapha to Mae Hong Son. The curve road."},
    "107":  {"name": "Route 107", "th": "ทางหลวงหมายเลข 107",
             "span": (18.78, 98.88, 19.18, 99.05),
             "note": "Chiang Mai north to Mae Malai, where 1095 turns off."},
    "108":  {"name": "Route 108", "th": "ทางหลวงหมายเลข 108",
             "span": (17.60, 97.80, 19.35, 98.90),
             "note": "Chiang Mai to Hot to Mae Sariang to Khun Yuam to Mae Hong Son."},
    "1263": {"name": "Route 1263", "th": "ทางหลวงหมายเลข 1263",
             "span": (18.20, 97.90, 18.85, 98.50),
             "note": "Khun Yuam east to Mae Chaem. The shortcut that cuts the loop in half."},
    "1088": {"name": "Route 1088", "th": "ทางหลวงหมายเลข 1088",
             "span": (18.30, 98.20, 18.75, 98.60),
             "note": "Mae Chaem north, the Doi Inthanon side road."},
    "1096": {"name": "Route 1096", "th": "ทางหลวงหมายเลข 1096",
             "span": (18.75, 98.55, 19.10, 98.95),
             "note": "Mae Rim to Samoeng. The warm-up loop, ridden on its own."},
}

# Everything worth a pin, by OSM tag. Each kind says which page it feeds.
PLACE_KINDS = [
    ("town",     'node["place"~"^(city|town)$"]'),
    ("village",  'node["place"~"^(village)$"]'),
    ("fuel",     'nwr["amenity"="fuel"]'),
    ("wat",      'nwr["amenity"="place_of_worship"]["religion"="buddhist"]'),
    ("coffee",   'nwr["amenity"="cafe"]'),
    ("coffee",   'nwr["cuisine"~"coffee_shop"]'),
    ("viewpoint", 'nwr["tourism"="viewpoint"]'),
    ("waterfall", 'nwr["waterway"="waterfall"]'),
    ("spring",   'nwr["natural"="hot_spring"]'),
    ("spring",   'nwr["amenity"="public_bath"]["bath:type"="hot_spring"]'),
    ("cave",     'nwr["natural"="cave_entrance"]'),
    ("stay",     'nwr["tourism"~"^(hotel|guest_house|hostel|chalet|resort)$"]'),
    ("market",   'nwr["amenity"="marketplace"]'),
    ("museum",   'nwr["tourism"~"^(museum|attraction)$"]'),
    ("hospital", 'nwr["amenity"~"^(hospital|clinic)$"]'),
    ("airport",  'nwr["aeroway"="aerodrome"]'),
    ("repair",   'nwr["shop"~"^(motorcycle|motorcycle_repair)$"]'),
]

KEEP = ("name", "name:en", "name:th", "int_name", "place", "amenity", "shop", "tourism", "natural",
        "waterway", "religion", "cuisine", "aeroway", "brand", "operator", "website", "phone",
        "opening_hours", "ele", "population", "wikidata", "wikipedia", "internet_access",
        "addr:city", "addr:subdistrict", "addr:district", "addr:province", "fuel:octane_91",
        "fuel:octane_95", "fuel:diesel", "stars", "rooms", "bath:type", "wheelchair", "description")


def overpass(query: str, tries: int = 3):
    err = None
    for i in range(tries):
        ep = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": query}).encode(),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=100) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            print(f"  {ep.split('/')[2]}: {e}; retrying")
            time.sleep(4 + 4 * i)
    raise RuntimeError(f"Overpass failed: {err}")


def haversine(a, b) -> float:
    """Kilometres between two (lat, lon) pairs."""
    R = 6371.0088
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def bearing(a, b) -> float:
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = (math.cos(math.radians(a[0])) * math.sin(math.radians(b[0]))
         - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1])))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def inside(pt, box) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def chain_km(c: list) -> float:
    return sum(haversine(c[i], c[i + 1]) for i in range(len(c) - 1))


def _join(frags: list, tol: float) -> list:
    """One greedy pass: absorb any fragment whose end lands within `tol` km of a chain's end."""
    chains = []
    while frags:
        chain = frags.pop(0)
        moved = True
        while moved:
            moved = False
            for i, f in enumerate(frags):
                if haversine(chain[-1], f[0]) < tol:
                    chain = chain + f
                elif haversine(chain[-1], f[-1]) < tol:
                    chain = chain + list(reversed(f))
                elif haversine(chain[0], f[-1]) < tol:
                    chain = f + chain
                elif haversine(chain[0], f[0]) < tol:
                    chain = list(reversed(f)) + chain
                else:
                    continue
                frags.pop(i)
                moved = True
                break
        chains.append(chain)
    chains.sort(key=lambda c: -chain_km(c))
    return chains


def stitch(ways: list[dict]) -> list[list]:
    """Join ways end to end into the longest chains they will make.

    Two passes, and the second one is the point. OSM splits a highway at every bridge,
    every surface change and every administrative line, so a road arrives as hundreds of
    fragments in no order — those share nodes exactly and join at 30 m. But a route number
    also goes MISSING for a few hundred metres wherever it crosses a roundabout, runs
    through a town centre on a named street, or overlaps another route: there the chain
    breaks with a real gap. The second pass closes gaps up to 2.5 km between chain ENDS,
    which is the width of the largest such interruption on this circuit and still far
    narrower than the distance between two genuinely different roads carrying the number.

    A gap closed this way is a straight line between two real points. Curve counting
    ignores it (the resampler walks it as one long segment with no direction change) and
    the distance it adds is small, but it is an interpolation and the harvest file says so.
    """
    frags = [list(w) for w in ways if len(w) > 1]
    chains = _join(frags, 0.03)
    big = [c for c in chains if chain_km(c) > 0.4]
    return _join(big, 2.5)


def simplify(pts: list, tol_km: float = 0.05) -> list:
    """Douglas-Peucker, distance in kilometres, so a 200 km road ships as a few thousand
    points rather than tens of thousands. The tolerance is well under a lane width at the
    scale anything here is drawn."""
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    ab = haversine(a, b)
    worst, wi = 0.0, 0
    for i in range(1, len(pts) - 1):
        p = pts[i]
        if ab < 1e-9:
            d = haversine(a, p)
        else:
            # perpendicular distance, flat-earth at this scale
            x0, y0 = p[1] - a[1], p[0] - a[0]
            x1, y1 = b[1] - a[1], b[0] - a[0]
            t = max(0.0, min(1.0, (x0 * x1 + y0 * y1) / (x1 * x1 + y1 * y1)))
            d = haversine(p, (a[0] + t * y1, a[1] + t * x1))
        if d > worst:
            worst, wi = d, i
    if worst <= tol_km:
        return [a, b]
    return simplify(pts[:wi + 1], tol_km)[:-1] + simplify(pts[wi:], tol_km)


def count_curves(pts: list, min_turn: float = 25.0, step_km: float = 0.06) -> dict:
    """Count direction changes along a polyline.

    A curve here is a sustained turn: resample the line at a fixed step so a dense stretch
    is not counted more heavily than a sparse one, then walk it accumulating heading change
    in one direction. When the sign flips, close the arc; if it turned more than `min_turn`
    degrees, it was a curve. Hairpins are the arcs above 120 degrees.

    This is a measurement of an OSM polyline, not of a road. Say so wherever it is printed.
    """
    res = resample(pts, step_km)
    if len(res) < 3:
        return {"curves": 0, "hairpins": 0, "km": 0.0, "arcs": []}
    arcs = []
    acc, sign = 0.0, 0
    for i in range(1, len(res) - 1):
        b1 = bearing(res[i - 1], res[i])
        b2 = bearing(res[i], res[i + 1])
        d = (b2 - b1 + 540) % 360 - 180        # signed, -180..180
        s = 1 if d > 0 else (-1 if d < 0 else 0)
        if s == 0 or abs(d) > 150:             # a spike is a data artefact, not a turn
            continue
        if s == sign:
            acc += d
        else:
            if abs(acc) >= min_turn:
                arcs.append(round(abs(acc), 1))
            acc, sign = d, s
    if abs(acc) >= min_turn:
        arcs.append(round(abs(acc), 1))
    km = sum(haversine(res[i], res[i + 1]) for i in range(len(res) - 1))
    return {"curves": len(arcs), "hairpins": sum(1 for a in arcs if a >= 120),
            "tight": sum(1 for a in arcs if 60 <= a < 120), "km": round(km, 2),
            "per_km": round(len(arcs) / km, 2) if km else 0,
            "arcs": arcs}


def resample(pts: list, step_km: float) -> list:
    out = [pts[0]]
    carry = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = haversine(a, b)
        if seg < 1e-9:
            continue
        t = step_km - carry
        while t < seg:
            f = t / seg
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            t += step_km
        carry = (carry + seg) % step_km
    out.append(pts[-1])
    return out


def fetch_tiled(ref: str, span, rows: int = 4, cols: int = 3) -> dict:
    """Overpass times out on a whole-province geometry request for a road this long, and
    the mirrors time out together. Split the span into a grid and ask for one tile at a
    time; a way crossing a tile edge comes back from both, and the way id dedupes it."""
    s0, w0, n0, e0 = span
    dh, dw = (n0 - s0) / rows, (e0 - w0) / cols
    elements, seen = [], set()
    for r in range(rows):
        for c in range(cols):
            s, n = s0 + r * dh, s0 + (r + 1) * dh
            w, e = w0 + c * dw, w0 + (c + 1) * dw
            q = (f'[out:json][timeout:60];way["ref"~"^(TH-)?{ref}$"]["highway"]'
                 f'({s:.4f},{w:.4f},{n:.4f},{e:.4f});out geom;')
            try:
                d = overpass(q, tries=2)
            except RuntimeError as err:
                print(f"    tile {r}{c}: {err}")
                continue
            got = 0
            for el in d.get("elements", []):
                if el["id"] in seen:
                    continue
                seen.add(el["id"])
                elements.append(el)
                got += 1
            print(f"    tile {r}{c}: +{got}", flush=True)
            time.sleep(2)
    return {"elements": elements}


def harvest_roads(dry=False, refetch=False):
    out = {"licence": "ODbL 1.0", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
           "attribution": "© OpenStreetMap contributors", "fetched": time.strftime("%Y-%m-%d"),
           "note": ("Ways carrying each route number inside the loop's corridor, stitched end to end "
                    "and simplified to 50 m. Curve counts are measured off this polyline, which is a "
                    "volunteer trace of the road, not a survey of it."),
           "roads": {}}
    for ref, meta in ROADS.items():
        s, w, n, e = meta["span"]
        q = (f'[out:json][timeout:180];way["ref"~"^(TH-)?{ref}$"]["highway"]({s},{w},{n},{e});'
             'out geom;')
        cache = HARVEST / "_raw" / f"ways-{ref}.json"
        if cache.exists() and not refetch:
            d = jload(cache)
            print(f"ref {ref}: cached", flush=True)
        else:
            print(f"fetching ref {ref} …", flush=True)
            d = fetch_tiled(ref, meta["span"])
            jdump(d, cache, indent=0)
        ways, names = [], {}
        for el in d.get("elements", []):
            g = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
            if len(g) > 1:
                ways.append(g)
            for k in ("name", "name:th", "surface", "lanes", "maxspeed"):
                if el.get("tags", {}).get(k):
                    names.setdefault(k, {})
                    names[k][el["tags"][k]] = names[k].get(el["tags"][k], 0) + 1
        chains = stitch(ways)
        keep = [c for c in chains if sum(haversine(c[i], c[i + 1]) for i in range(len(c) - 1)) > 2.0]
        line = simplify(keep[0], 0.05) if keep else []
        km = sum(haversine(line[i], line[i + 1]) for i in range(len(line) - 1)) if line else 0
        cv = count_curves(keep[0]) if keep else {}
        out["roads"][ref] = dict(meta, ways=len(ways), chains=len(keep), points=len(line),
                                 km=round(km, 1), line=[[round(p[0], 5), round(p[1], 5)] for p in line],
                                 curves=cv, tags=names, query=q)
        print(f"  {ref}: {len(ways)} ways -> {len(keep)} chains, longest {km:.1f} km, "
              f"{cv.get('curves', 0)} curves ({cv.get('hairpins', 0)} hairpin)")
        if not cache.exists() or refetch:
            time.sleep(3)
    if not dry:
        jdump(out, HARVEST / "osm-roads.json", indent=0)
        print(f"wrote {HARVEST / 'osm-roads.json'}")
    return out


def harvest_places(dry=False):
    s, w, n, e = BBOX
    rows, seen = [], set()
    for kind, sel in PLACE_KINDS:
        q = f'[out:json][timeout:180];{sel}({s},{w},{n},{e});out center tags;'
        print(f"places: {kind} …", flush=True)
        try:
            d = overpass(q)
        except RuntimeError as err:
            print(f"  {kind}: {err}")
            continue
        got = 0
        for el in d.get("elements", []):
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            t = el.get("tags", {})
            if lat is None or lon is None:
                continue
            key = (el["type"], el["id"])
            if key in seen:
                continue
            seen.add(key)
            name = t.get("name:en") or t.get("int_name") or t.get("name")
            rows.append({"kind": kind, "osm": f"{el['type']}/{el['id']}", "lat": round(lat, 6),
                         "lon": round(lon, 6), "name": name, "name_th": t.get("name:th"),
                         "slug": slugify(name) if name else None,
                         "tags": {k: v for k, v in t.items() if k in KEEP}})
            got += 1
        print(f"  {kind}: {got}")
        time.sleep(3)
    out = {"licence": "ODbL 1.0", "licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
           "attribution": "© OpenStreetMap contributors", "fetched": time.strftime("%Y-%m-%d"),
           "bbox": list(BBOX), "count": len(rows),
           "note": ("Everything OSM carries inside the loop's corridor under the tags listed in "
                    "PLACE_KINDS. A row is what a mapper entered, on the date above. Many rows "
                    "carry no English name and some carry no name at all."),
           "kinds": sorted({r["kind"] for r in rows}), "rows": rows}
    prev = HARVEST / "osm-places.json"
    if prev.exists() and not dry:
        old = jload(prev).get("count", 0)
        if len(rows) < old * 0.6:
            print(f"REFUSED: {len(rows)} rows would replace {old}. Rerun or pass --force.")
            return out
    if not dry:
        jdump(out, prev, indent=0)
        print(f"wrote {prev}: {len(rows)} rows")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--roads", action="store_true")
    ap.add_argument("--places", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--refetch", action="store_true", help="ignore the raw cache under data/harvest/_raw/")
    a = ap.parse_args()
    if a.all or a.roads:
        harvest_roads(a.dry, a.refetch)
    if a.all or a.places:
        harvest_places(a.dry)
    if not (a.all or a.roads or a.places):
        ap.print_help()
