#!/usr/bin/env python3
"""harvest_base.py — the land under the road: rivers, lakes, the border and the ridges.

A route drawn on nothing reads as a squiggle. These layers give it somewhere to be: the
Salween making the western border, the Pai and the Yuam that the road follows, the
reservoirs, the provincial line, and a coarse elevation grid for the hills.

    python3 tools/harvest_base.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_osm import BBOX, overpass, simplify  # noqa: E402
from common import HARVEST, jdump, jload  # noqa: E402

UA = "mhs-loop-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
ELEV = "https://api.open-meteo.com/v1/elevation"


def waters():
    s, w, n, e = BBOX
    out = {"licence": "ODbL 1.0", "attribution": "© OpenStreetMap contributors",
           "fetched": time.strftime("%Y-%m-%d"), "rivers": [], "lakes": [], "boundary": []}
    # named rivers, as ways with geometry; the big ones only, or the map turns to hair
    q = (f'[out:json][timeout:180];'
         f'way["waterway"="river"]["name"]({s},{w},{n},{e});out geom;')
    print("waters: rivers …", flush=True)
    d = overpass(q, tries=3)
    by_name = {}
    for el in d.get("elements", []):
        g = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
        if len(g) > 1:
            by_name.setdefault(el["tags"].get("name", "?"), []).append(g)
    for name, segs in by_name.items():
        total = sum(len(x) for x in segs)
        if total < 40:            # a named ditch is still a ditch
            continue
        out["rivers"].append({"name": name,
                              "name_en": segs and None,
                              "lines": [[[round(a, 5), round(b, 5)] for a, b in simplify(x, 0.12)]
                                        for x in segs if len(x) > 4]})
    print(f"  {len(out['rivers'])} named rivers")
    time.sleep(3)

    q = (f'[out:json][timeout:180];'
         f'(way["natural"="water"]({s},{w},{n},{e});rel["natural"="water"]({s},{w},{n},{e}););'
         f'out geom;')
    print("waters: lakes …", flush=True)
    try:
        d = overpass(q, tries=3)
        for el in d.get("elements", []):
            g = [(p["lat"], p["lon"]) for p in el.get("geometry", [])]
            if len(g) > 12:
                out["lakes"].append([[round(a, 5), round(b, 5)] for a, b in simplify(g, 0.15)])
    except RuntimeError as err:
        print("  lakes:", err)
    print(f"  {len(out['lakes'])} water bodies")
    time.sleep(3)

    # the provincial line — the thing that makes the map a place rather than a region
    q = ('[out:json][timeout:180];'
         'rel["boundary"="administrative"]["admin_level"="4"]["name:en"~"Mae Hong Son",i];'
         'out geom;')
    print("waters: province boundary …", flush=True)
    try:
        d = overpass(q, tries=3)
        for el in d.get("elements", []):
            for m in el.get("members", []):
                g = [(p["lat"], p["lon"]) for p in m.get("geometry", []) or []]
                if len(g) > 8:
                    out["boundary"].append([[round(a, 5), round(b, 5)]
                                            for a, b in simplify(g, 0.2)])
    except RuntimeError as err:
        print("  boundary:", err)
    print(f"  {len(out['boundary'])} boundary segments")
    jdump(out, HARVEST / "osm-base.json", indent=0)
    print(f"wrote {HARVEST / 'osm-base.json'}")


def elevation(step=0.02):
    """A coarse elevation grid from Open-Meteo, free and keyless, for the hillshade.
    The API takes up to 100 points per call."""
    s, w, n, e = BBOX
    lats, lons = [], []
    y = s
    while y <= n:
        x = w
        while x <= e:
            lats.append(round(y, 4)); lons.append(round(x, 4))
            x += step
        y += step
    print(f"elevation: {len(lats)} points …", flush=True)
    vals = []
    for i in range(0, len(lats), 100):
        la = lats[i:i + 100]; lo = lons[i:i + 100]
        q = {"latitude": ",".join(map(str, la)), "longitude": ",".join(map(str, lo))}
        url = ELEV + "?" + urllib.parse.urlencode(q)
        for attempt in range(4):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    vals += json.load(r)["elevation"]
                break
            except Exception as err:  # noqa: BLE001
                if attempt == 3:
                    print("  !", err); vals += [None] * len(la)
                time.sleep(2 + 3 * attempt)
        if i % 1000 == 0:
            print(f"  {i}/{len(lats)}", flush=True)
        time.sleep(0.25)
    # a dropped batch leaves a stripe of holes across the map, so anything missing is
    # asked for again before the file is written
    missing = [i for i, v in enumerate(vals) if v is None]
    for attempt in range(3):
        if not missing:
            break
        print(f"  refetching {len(missing)} gaps (pass {attempt + 1})", flush=True)
        for j in range(0, len(missing), 100):
            idx = missing[j:j + 100]
            q = {"latitude": ",".join(str(lats[i]) for i in idx),
                 "longitude": ",".join(str(lons[i]) for i in idx)}
            try:
                req = urllib.request.Request(ELEV + "?" + urllib.parse.urlencode(q),
                                             headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    got = json.load(r)["elevation"]
                for i, v in zip(idx, got):
                    vals[i] = v
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.4)
        missing = [i for i, v in enumerate(vals) if v is None]
    if missing:
        print(f"  {len(missing)} points still missing after three passes")
    grid = [{"lat": a, "lon": b, "m": v} for a, b, v in zip(lats, lons, vals) if v is not None]
    ok = [g["m"] for g in grid]
    jdump({"source": "Open-Meteo Elevation API (Copernicus DEM GLO-90)",
           "url": ELEV, "licence": "CC BY 4.0", "attribution": "Open-Meteo.com",
           "fetched": time.strftime("%Y-%m-%d"), "step_deg": step, "bbox": list(BBOX),
           "count": len(grid), "min_m": min(ok) if ok else None, "max_m": max(ok) if ok else None,
           "grid": grid}, HARVEST / "elevation.json", indent=0)
    print(f"wrote {len(grid)} points, {min(ok):.0f}–{max(ok):.0f} m")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--waters", action="store_true")
    ap.add_argument("--elevation", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    if a.all or a.waters:
        waters()
    if a.all or a.elevation:
        elevation()
    if not (a.all or a.waters or a.elevation):
        ap.print_help()
