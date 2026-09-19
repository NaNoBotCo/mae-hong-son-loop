#!/usr/bin/env python3
"""geocode_towns.py — put the donut makers on the map.

A donut record's `profile` names the town and state printed on the label. This turns
those into coordinates through Nominatim, which reads the same OpenStreetMap data the
place map runs on, one request a second as its usage policy asks, cached by
"town, state" so a re-run fetches only what is new.

Output: data/harvest/donut-towns.json — a harvest file, never a record. build.py joins
it onto the donut table, so a town nobody geocoded simply does not appear on the map.

    python3 tools/geocode_towns.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump, jload, load_nodes  # noqa: E402

UA = "buffalo-wings-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OUT = HARVEST / "donut-towns.json"


def main(sleep=1.1) -> int:
    cache = jload(OUT) if OUT.exists() else {
        "source": "Nominatim forward geocoding of OpenStreetMap data",
        "license": "ODbL 1.0", "attribution": "© OpenStreetMap contributors",
        "note": "town centres for the towns printed on donut labels; a point is the town, never the maker's door",
        "rows": {}}
    rows = cache["rows"]
    want = set()
    for r in load_nodes():
        pf = r.get("profile") or {}
        if pf.get("town") and pf.get("state"):
            want.add(f'{pf["town"].strip()}, {pf["state"].strip()}')
    todo = sorted(w for w in want if w not in rows)
    print(f"{len(want)} towns on labels · {len(rows)} cached · {len(todo)} to fetch")
    for w in todo:
        q = urllib.parse.urlencode({"q": w + ", United States", "format": "jsonv2", "limit": 1, "countrycodes": "us"})
        req = urllib.request.Request(f"{NOMINATIM}?{q}", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"  {w}: {e}")
            time.sleep(sleep)
            continue
        if not d:
            print(f"  {w}: no match — left off the map")
            rows[w] = None
        else:
            rows[w] = {"lat": round(float(d[0]["lat"]), 4), "lon": round(float(d[0]["lon"]), 4),
                       "display": d[0].get("display_name", ""), "fetched_at": time.strftime("%Y-%m-%d")}
            print(f"  {w}: {rows[w]['lat']}, {rows[w]['lon']}")
        time.sleep(sleep)
    jdump(cache, OUT)
    got = sum(1 for v in rows.values() if v)
    print(f"wrote {OUT} — {got} of {len(rows)} towns placed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
