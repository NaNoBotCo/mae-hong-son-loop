#!/usr/bin/env python3
"""build.py — records + harvests → build/api.

Everything the site renders is computed here and written as JSON, so the API a reader or
a bot can fetch is the same data the pages are made from. Nothing is computed twice.

    python3 tools/build.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BUILD, HARVEST, TYPES, jdump, jload, load_harvest, load_nodes,
                    load_sources, load_vocab)  # noqa: E402

API = BUILD / "api"

# Clockwise order of the circuit. The counter-clockwise itinerary is this, reversed, with
# each leg's `ccw` prose swapped in — the site never stores the route twice.
CW = ["cnx-to-pai", "pai-to-soppong", "soppong-to-mhs", "mhs-to-khun-yuam",
      "khun-yuam-to-mae-sariang", "mae-sariang-to-hot", "hot-to-cnx"]
OPTIONAL = ["the-1263-cut", "samoeng-warmup"]


def merge_new_sources() -> dict:
    """sources.json plus any data/sources/new-*.json an author left beside it."""
    return load_sources()


def attach_geometry(recs, roads):
    """Give every leg and road its drawn line, from the harvest, at build time. A record
    never stores geometry it did not author."""
    for r in recs:
        rt = r.get("route")
        if not rt:
            continue
        line = []
        for ref in rt.get("roads", []):
            road = roads.get(ref) or {}
            if road.get("line"):
                line += road["line"]
        if line:
            rt["line"] = line
            rt["line_points"] = len(line)


def air_summary(air):
    """Per-point monthly means and the one figure the site leads with."""
    if not air:
        return {}
    pts = []
    for p in air["points"]:
        months = {m: v["mean"] for m, v in p["by_month"].items()}
        worst = max(p["by_month"].items(), key=lambda kv: kv[1]["mean"]) if p["by_month"] else ("--", {})
        best = min(p["by_month"].items(), key=lambda kv: kv[1]["mean"]) if p["by_month"] else ("--", {})
        pts.append({"id": p["id"], "name": p["name"], "th": p["th"], "lat": p["lat"], "lon": p["lon"],
                    "days": p["days"], "months": months, "by_month": p["by_month"],
                    "worst_month": worst[0], "worst_mean": worst[1].get("mean"),
                    "best_month": best[0], "best_mean": best[1].get("mean"),
                    "worst_day": p["worst_day"],
                    "ratio": round(worst[1].get("mean", 0) / best[1].get("mean", 1), 1) if best[1].get("mean") else None})
    ceiling = max((max(p["daily"].values()) for p in air["points"] if p["daily"]), default=0)
    return {"start": air["start"], "end": air["end"], "fetched": air["fetched"],
            "source": air["source"], "attribution": air["attribution"], "note": air["note"],
            "point_days": sum(p["days"] for p in air["points"]),
            "model_ceiling": round(ceiling, 1),
            "days_over_125": sum(1 for p in air["points"] for v in p["daily"].values() if v > 125.4),
            "points": pts}


def main() -> int:
    recs = load_nodes()
    sources = merge_new_sources()
    vocab = {n: load_vocab(n) for n in ("types", "regions", "facets", "tags", "recognizers")}
    roads_h = load_harvest("osm-roads") or {"roads": {}}
    curves = load_harvest("curve-analysis") or {}
    air_m = load_harvest("air-model")
    air_g = load_harvest("air-ground")
    places = load_harvest("osm-places") or {"rows": [], "count": 0}

    # geometry comes from the curve analysis where it exists (better stitching), else the harvest
    roads = {}
    for ref, r in roads_h.get("roads", {}).items():
        roads[ref] = {"line": r.get("line", []), "km": r.get("km"), "name": r.get("name"),
                      "th": r.get("th"), "note": r.get("note")}
    for ref, r in curves.get("roads", {}).items():
        line = [d["from"] for d in r.get("density", [])] + ([r["density"][-1]["to"]] if r.get("density") else [])
        if len(line) > 2:
            roads.setdefault(ref, {})
            roads[ref].update({"line": line, "lines": r.get("lines", [line]),
                               "km": r["whole"]["km"], "name": r["name"], "th": r["th"],
                               "curves": r["whole"]["curves"], "hairpins": r["whole"]["hairpins"],
                               "per_km": r["whole"]["per_km"], "density": r["density"],
                               "spans": r["spans"], "hardest": r.get("hardest", [])})

    attach_geometry(recs, roads)

    by_id = {r["id"]: r for r in recs}
    for r in recs:
        r.pop("_path", None)
        r.pop("_dir_type", None)

    # ---- kin, answered from both ends
    back = {}
    for r in recs:
        for k in r.get("kin", []):
            back.setdefault(k["to"], []).append({"from": r["id"], "type": r["type"],
                                                 "name": r["names"]["name"], "as": k["as"]})
    for r in recs:
        r["kin_in"] = back.get(r["id"], [])

    # ---- the itinerary, both ways
    legs = [by_id[i] for i in CW if i in by_id]
    total_km = sum((l.get("route") or {}).get("km") or 0 for l in legs)
    total_curves = sum((l.get("route") or {}).get("curves") or 0 for l in legs)
    itinerary = {
        "cw": {"order": CW, "label": "Clockwise", "th": "ตามเข็มนาฬิกา",
               "note": "North first: up 107 and 1095 to Pai, on to Mae Hong Son, home down 108."},
        "ccw": {"order": list(reversed(CW)), "label": "Counter-clockwise", "th": "ทวนเข็มนาฬิกา",
                "note": "South first: down 108 to Hot and Mae Sariang, up to Mae Hong Son, back over 1095."},
        "optional": OPTIONAL, "km": round(total_km), "curves": total_curves,
        "legs": [{"id": l["id"], "name": l["names"]["name"], "th": l["names"].get("th"),
                  "km": (l.get("route") or {}).get("km"),
                  "curves": (l.get("route") or {}).get("curves"),
                  "hairpins": (l.get("route") or {}).get("hairpins"),
                  "hours": (l.get("route") or {}).get("hours"),
                  "from": (l.get("route") or {}).get("from"), "to": (l.get("route") or {}).get("to"),
                  "cw": (l.get("route") or {}).get("cw"), "ccw": (l.get("route") or {}).get("ccw"),
                  "cw_th": (l.get("route") or {}).get("cw_th"), "ccw_th": (l.get("route") or {}).get("ccw_th")}
                 for l in legs]}

    # ---- harvested places, bucketed by kind and tied to the nearest town
    kinds = {}
    for row in places.get("rows", []):
        kinds.setdefault(row["kind"], []).append(row)
    place_summary = {"count": places.get("count", 0), "fetched": places.get("fetched"),
                     "attribution": places.get("attribution"), "note": places.get("note"),
                     "by_kind": {k: len(v) for k, v in sorted(kinds.items())},
                     "named": {k: sum(1 for r in v if r.get("name")) for k, v in sorted(kinds.items())}}

    cov = {"built": time.strftime("%Y-%m-%d %H:%M"),
           "records": len(recs),
           "by_type": {t: sum(1 for r in recs if r["type"] == t) for t in TYPES},
           "kin_edges": sum(len(r.get("kin", [])) for r in recs),
           "sources": len(sources),
           "needs_verification": sum(1 for r in recs if r.get("needs_verification")),
           "bilingual": sum(1 for r in recs if r.get("text_th")),
           "th_fields": sum(len(r.get("text_th") or {}) for r in recs),
           "roads_measured": sorted(curves.get("roads", {}).keys()),
           "osm_places": place_summary,
           "air": {"point_days": sum(p["days"] for p in (air_m or {}).get("points", [])),
                   "stations_near_loop": (air_g or {}).get("stations_near_loop"),
                   "mhs_province_stations": (air_g or {}).get("mhs_province_stations", [])},
           "tiers": {}}
    for r in recs:
        t = (r.get("provenance", {}).get("default") or {}).get("tier", "?")
        cov["tiers"][t] = cov["tiers"].get(t, 0) + 1

    API.mkdir(parents=True, exist_ok=True)
    jdump({"count": len(recs), "nodes": recs}, API / "nodes.json")
    jdump(itinerary, API / "itinerary.json")
    jdump(roads, API / "roads.json", indent=0)
    jdump(curves, API / "curves.json", indent=0)
    jdump(air_summary(air_m), API / "air.json", indent=0)
    jdump(air_g or {}, API / "air-now.json")
    jdump(places, API / "places.json", indent=0)
    jdump({"sources": list(sources.values())}, API / "sources.json")
    jdump(vocab, API / "vocab.json")
    jdump(cov, API / "coverage.json")
    for t in TYPES:
        rows = [r for r in recs if r["type"] == t]
        jdump({"type": t, "count": len(rows), "nodes": rows}, API / f"{t}.json")
        for r in rows:
            jdump(r, API / t / f"{r['id']}.json")

    print(f"build: {len(recs)} records, {cov['kin_edges']} kin, {len(sources)} sources, "
          f"{cov['th_fields']} Thai fields")
    print(f"       roads measured: {', '.join(cov['roads_measured']) or 'none'}")
    print(f"       air: {cov['air']['point_days']} point-days · "
          f"osm places: {place_summary['count']}")
    print(f"       tiers: {cov['tiers']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
