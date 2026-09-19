#!/usr/bin/env python3
"""curves.py — count the curves, and show the method's own sensitivity.

Three numbers are in circulation for the Chiang Mai–Pai road: 1,864 (the sign and the
merchandise), "more than 2,000" (Thai Wikipedia on Route 1095), and whatever you get by
counting. This tool produces the third one, at four thresholds rather than one, so the
figure arrives with its own error bars rather than as a rival slogan.

Method: stitch the road, resample at a fixed 60 m step so a densely-traced stretch does
not outvote a sparsely-traced one, walk the line accumulating signed heading change, and
close an arc when the turn reverses. An arc above the threshold is a curve; above 120
degrees it is a hairpin. It measures an OpenStreetMap polyline, not a road.

    python3 tools/curves.py            # write data/harvest/curve-analysis.json
    python3 tools/curves.py --print    # table to stdout, write nothing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump, jload  # noqa: E402
from harvest_osm import ROADS, chain_km, count_curves, haversine, stitch  # noqa: E402

THRESHOLDS = (15, 25, 35, 45)
DEFAULT = 25

# Named points that cut a road into the spans people actually argue about.
SPLITS = {
    "1095": [("mae-malai", "Mae Malai", "แม่มาลัย", 19.1206, 98.9450),
             ("pai", "Pai", "ปาย", 19.3592, 98.4407),
             ("soppong", "Soppong", "สบป่อง", 19.4906, 98.2694),
             ("mae-hong-son", "Mae Hong Son", "แม่ฮ่องสอน", 19.3020, 97.9654)],
    "108": [("chiang-mai", "Chiang Mai", "เชียงใหม่", 18.7883, 98.9853),
            ("hot", "Hot", "ฮอด", 18.1447, 98.5847),
            ("mae-sariang", "Mae Sariang", "แม่สะเรียง", 18.1614, 97.9308),
            ("mae-la-noi", "Mae La Noi", "แม่ลาน้อย", 18.4497, 97.9678),
            ("khun-yuam", "Khun Yuam", "ขุนยวม", 18.8228, 97.9336),
            ("mae-hong-son", "Mae Hong Son", "แม่ฮ่องสอน", 19.3020, 97.9654)],
    "1263": [("khun-yuam", "Khun Yuam", "ขุนยวม", 18.8228, 97.9336),
             ("mae-chaem", "Mae Chaem", "แม่แจ่ม", 18.4967, 98.3714)],
}

# The figures already in circulation, each with who is carrying it. Printed beside the
# measurement so a reader can see three methods rather than one answer.
CLAIMS = [
    {"figure": 1864, "of": "Chiang Mai to Pai", "carried_by": "the roadside sign, and the shirts sold in Pai",
     "method": "not published by anyone", "source": None},
    {"figure": 2000, "of": "Route 1095", "qualifier": "more than", "carried_by": "Thai Wikipedia, ทางหลวงแผ่นดินหมายเลข 1095",
     "method": "not published", "source": "s:thwp-1095", "quote": "กว่า 2,000 โค้ง"},
]


def load_chains(ref: str) -> list:
    """Every stitched chain for a route number, longest first, from the raw cache."""
    raw = HARVEST / "_raw" / f"ways-{ref}.json"
    if not raw.exists():
        return []
    d = jload(raw)
    ways = [[(p["lat"], p["lon"]) for p in el.get("geometry", [])] for el in d.get("elements", [])]
    ways = [w for w in ways if len(w) > 1]
    return stitch(ways) if ways else []


def load_line(ref: str) -> list:
    """The longest chain — the one every measurement on this site is taken from."""
    ch = load_chains(ref)
    return ch[0] if ch else []


def cut(line: list, pts: list) -> list:
    """Cut a line at each named point, in the order the points are given."""
    idx = []
    for key, name, th, lat, lon in pts:
        i = min(range(len(line)), key=lambda i: haversine(line[i], (lat, lon)))
        idx.append((i, key, name, th, round(haversine(line[i], (lat, lon)), 2)))
    idx.sort()
    spans = []
    for a, b in zip(idx, idx[1:]):
        seg = line[a[0]:b[0] + 1]
        if len(seg) > 2:
            spans.append({"from": a[1], "from_name": a[2], "from_th": a[3], "from_off_km": a[4],
                          "to": b[1], "to_name": b[2], "to_th": b[3], "to_off_km": b[4],
                          "points": seg})
    return spans


def measure(seg: list) -> dict:
    km = chain_km(seg)
    at = {}
    for t in THRESHOLDS:
        cv = count_curves(seg, min_turn=t)
        at[str(t)] = {"curves": cv["curves"], "per_km": round(cv["curves"] / km, 2) if km else 0}
    cv = count_curves(seg, min_turn=DEFAULT)
    return {"km": round(km, 1), "at_threshold": at, "threshold_used": DEFAULT,
            "curves": cv["curves"], "hairpins": cv["hairpins"], "tight": cv["tight"],
            "per_km": cv["per_km"],
            "metres_per_curve": round(km * 1000 / cv["curves"], 1) if cv["curves"] else None}


def density(line: list, window_km: float = 2.0) -> list:
    """Curve density along the road, in fixed windows, so the map can colour it.

    This is not a crash map — nobody publishes one for these roads, and this project will
    not invent one. It is a map of how much steering a stretch asks for per kilometre,
    computed the same way everywhere, which is a different claim and a checkable one.
    Each window carries its own curve count, hairpin count and a demand band.
    """
    from harvest_osm import bearing, resample
    res = resample(line, 0.06)
    out, i = [], 0
    while i < len(res) - 2:
        seg, run = [res[i]], 0.0
        j = i
        while j < len(res) - 1 and run < window_km:
            run += haversine(res[j], res[j + 1])
            j += 1
            seg.append(res[j])
        if run < window_km * 0.4:
            break
        cv = count_curves(seg, min_turn=DEFAULT)
        per = cv["curves"] / run if run else 0
        band = ("gentle" if per < 2 else "busy" if per < 4 else "hard" if per < 6 else "relentless")
        out.append({"from": [round(seg[0][0], 5), round(seg[0][1], 5)],
                    "to": [round(seg[-1][0], 5), round(seg[-1][1], 5)],
                    "mid": [round(seg[len(seg) // 2][0], 5), round(seg[len(seg) // 2][1], 5)],
                    "km": round(run, 2), "curves": cv["curves"], "hairpins": cv["hairpins"],
                    "per_km": round(per, 2), "band": band})
        i = j
    return out


BANDS = {"gentle": "Under 2 curves a kilometre — you can look at the view",
         "busy": "2 to 4 — steady work, both hands",
         "hard": "4 to 6 — a steering input every few seconds",
         "relentless": "Over 6 — this is where a tired rider makes the mistake"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="show", action="store_true")
    a = ap.parse_args()
    out = {"method": ("Ways carrying the route number are stitched end to end, resampled every 60 m, "
                      "and walked accumulating signed heading change; an arc is closed when the turn "
                      "reverses and counted when it exceeds the threshold. 120 degrees or more is a "
                      "hairpin. This measures an OpenStreetMap polyline, which is a volunteer trace "
                      "of a road rather than a survey of one."),
           "step_m": 60, "thresholds": list(THRESHOLDS), "threshold_used": DEFAULT,
           "hairpin_degrees": 120, "source": "s:mhs-measured", "claims": CLAIMS,
           "density_window_km": 2.0, "bands": BANDS,
           "not_a_crash_map": ("Demand is measured the same way everywhere on this network: curves per "
                               "kilometre in fixed 2 km windows. It says where a road asks the most of a "
                               "rider. It is NOT a record of where anyone has crashed — no such record is "
                               "published for these roads, and none is invented here."),
           "roads": {}}
    for ref in ROADS:
        line = load_line(ref)
        if not line:
            print(f"  {ref}: no cached ways — run tools/harvest_osm.py --roads")
            continue
        r = {"name": ROADS[ref]["name"], "th": ROADS[ref]["th"], "whole": measure(line), "spans": []}
        for sp in cut(line, SPLITS.get(ref, [])):
            m = measure(sp.pop("points"))
            r["spans"].append(dict(sp, **m))
        # every chain over 2 km, simplified, so the map draws a complete road even where
        # the ref tag breaks; measurements still come from the longest chain only.
        from harvest_osm import simplify
        r["lines"] = [[[round(x, 5), round(y, 5)] for x, y in simplify(c, 0.06)]
                      for c in load_chains(ref) if chain_km(c) > 1.5]
        r["chains"] = len(r["lines"])
        r["density"] = density(line)
        r["bands"] = BANDS
        worst = sorted(r["density"], key=lambda d: -d["per_km"])[:3]
        r["hardest"] = worst
        out["roads"][ref] = r
        w = r["whole"]
        print(f"  {ref}: {w['km']} km, {w['curves']} curves at {DEFAULT}°, {w['hairpins']} hairpin, "
              f"{w['per_km']}/km, one every {w['metres_per_curve']} m")
        for d in worst:
            print(f"       hardest 2 km: {d['per_km']}/km, {d['hairpins']} hairpin, at {d['mid']}")
        for sp in r["spans"]:
            print(f"       {sp['from_name']} → {sp['to_name']}: {sp['km']} km, {sp['curves']} curves, "
                  f"{sp['per_km']}/km " +
                  " ".join(f"[{t}°:{sp['at_threshold'][t]['curves']}]" for t in map(str, THRESHOLDS)))
    # what the circulating figures would imply, in metres between curves
    p95 = out["roads"].get("1095", {})
    # The 1,864 figure is carried for Chiang Mai to Pai, so it has to be compared against
    # the Mae Malai–Pai span specifically. Matching on `to == "pai"` alone silently picks
    # whichever neighbouring span happens to end there once the line is re-stitched.
    want = {"mae-malai", "pai"}
    to_pai = next((s for s in p95.get("spans", []) if {s["from"], s["to"]} == want), None)
    if to_pai:
        out["claims"][0]["implies_metres_per_curve"] = round(to_pai["km"] * 1000 / 1864, 1)
        out["claims"][0]["measured_over_same_span"] = to_pai["curves"]
        out["claims"][0]["span_km"] = to_pai["km"]
    if p95.get("whole"):
        out["claims"][1]["implies_metres_per_curve"] = round(p95["whole"]["km"] * 1000 / 2000, 1)
        out["claims"][1]["measured_over_same_span"] = p95["whole"]["curves"]
        out["claims"][1]["span_km"] = p95["whole"]["km"]
    if not a.show:
        jdump(out, HARVEST / "curve-analysis.json", indent=1)
        print(f"wrote {HARVEST / 'curve-analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
