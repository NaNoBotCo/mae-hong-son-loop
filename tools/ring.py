#!/usr/bin/env python3
"""ring.py — the circuit as one closed line.

Drawn from the route tags alone the loop does not close. OpenStreetMap stops carrying a
highway's `ref` where it runs through a town on named streets, so Route 107 arrives as
five fragments through the northern suburbs of Chiang Mai, Route 1095 stops five
kilometres short of Mae Malai, and Route 108 never reaches the city at all. The result is
a map with holes in it and no explanation for them.

This walks the circuit through its waypoints in order, takes the best-fitting stretch of
traced road for each span, and bridges what is left with a straight line. Every bridge is
counted and returned, so the page can say how much of the drawn ring is interpolated
rather than leaving the reader to wonder.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_osm import chain_km, haversine  # noqa: E402

# Clockwise, starting and ending in Chiang Mai.
WAYPOINTS = [
    ("chiang-mai", 18.7883, 98.9853), ("mae-malai", 19.1206, 98.9450),
    ("pai", 19.3592, 98.4407), ("soppong", 19.4906, 98.2694),
    ("mae-hong-son", 19.3020, 97.9654), ("khun-yuam", 18.8228, 97.9336),
    ("mae-la-noi", 18.4497, 97.9678), ("mae-sariang", 18.1614, 97.9308),
    ("hot", 18.1447, 98.5847), ("chiang-mai", 18.7883, 98.9853),
]
USE = ("107", "1095", "108")


def _nearest_index(line, pt):
    best, bi = None, 0
    for i, p in enumerate(line):
        d = haversine(tuple(p), pt)
        if best is None or d < best:
            best, bi = d, i
    return bi, best


def build(roads: dict, min_km=0.8, near_km=16.0):
    """Return (ring, bridges, stats).

    Each waypoint is projected onto every traced chain. A span between two consecutive
    waypoints is drawn from real road when both ends land on the SAME chain — which lets
    one 300 km run of Route 108 serve four spans in a row instead of being spent on the
    first. Everything else is bridged, and every bridge is reported.
    """
    chains = []
    for ref in USE:
        for ln in (roads.get(ref, {}).get("lines") or []):
            pts = [tuple(c) for c in ln]
            if len(pts) > 1 and chain_km(pts) >= min_km:
                chains.append({"ref": ref, "pts": pts, "km": chain_km(pts)})
    chains.sort(key=lambda c: -c["km"])

    # where does each waypoint sit on each chain?
    proj = []
    for (_, la, lo) in WAYPOINTS:
        row = []
        for ci, ch in enumerate(chains):
            idx, dist = _nearest_index(ch["pts"], (la, lo))
            row.append((dist, ci, idx))
        row.sort()
        proj.append(row)

    ring, bridges = [], []
    cur = (WAYPOINTS[0][1], WAYPOINTS[0][2])

    def _take(seg, a_name, b_name):
        """Append a stretch of real road, bridging whatever gap precedes it."""
        nonlocal cur
        if haversine(cur, seg[0]) > 0.15:
            bridges.append({"from": [round(cur[0], 5), round(cur[1], 5)],
                            "to": [round(seg[0][0], 5), round(seg[0][1], 5)],
                            "km": round(haversine(cur, seg[0]), 2),
                            "between": f"{a_name}\u2013{b_name}"})
            ring.append([round(cur[0], 5), round(cur[1], 5)])
        ring.extend([round(x, 5), round(y, 5)] for x, y in seg)
        cur = seg[-1]

    for k in range(len(WAYPOINTS) - 1):
        a_name, ala, alo = WAYPOINTS[k]
        b_name, bla, blo = WAYPOINTS[k + 1]
        target = (bla, blo)
        used_here = set()
        # a span can need several chains in a row — Chiang Mai to Hot is three — so keep
        # taking whichever untried chain closes the most distance, until none does
        for _ in range(6):
            gap = haversine(cur, target)
            if gap < 1.0:
                break
            best = None
            for ci, ch in enumerate(chains):
                if ci in used_here:
                    continue
                pts = ch["pts"]
                si, sd = _nearest_index(pts, cur)
                if sd > near_km:
                    continue
                for direction in (1, -1):
                    seg = pts[si:] if direction == 1 else list(reversed(pts[:si + 1]))
                    if len(seg) < 2:
                        continue
                    bi, bd = _nearest_index(seg, target)
                    if bi < 1 or bd >= gap - 0.8:
                        continue
                    cand = seg[:bi + 1]
                    score = (gap - bd) - sd * 1.1
                    if best is None or score > best[0]:
                        best = (score, ci, cand, bd)
            if best is None:
                break
            _, ci, seg, _bd = best
            used_here.add(ci)
            _take(seg, a_name, b_name)
        d = haversine(cur, target)
        if d > 8.0:
            bridges.append({"from": [round(cur[0], 5), round(cur[1], 5)],
                            "to": [round(target[0], 5), round(target[1], 5)],
                            "km": round(d, 2), "between": f"{a_name}\u2013{b_name}"})
            ring.append([round(target[0], 5), round(target[1], 5)])
            cur = target
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    total = chain_km([tuple(p) for p in ring]) if len(ring) > 1 else 0
    bkm = sum(b["km"] for b in bridges)
    stats = {"km": round(total, 1), "points": len(ring), "bridges": len(bridges),
             "bridged_km": round(bkm, 2),
             "bridged_pct": round(100 * bkm / total, 1) if total else 0,
             "note": ("The drawn circuit is stitched from OpenStreetMap ways carrying "
                      "Route 107, 1095 and 108. Where the route number is not tagged \u2014 "
                      "through town centres, mostly \u2014 the gap is bridged with a straight "
                      "line so the loop closes. The bridged length is given so it can be "
                      "discounted.")}
    return ring, bridges, stats


if __name__ == "__main__":
    from common import BUILD, jload
    roads = jload(BUILD / "api" / "roads.json")
    ring, bridges, stats = build(roads)
    print(stats)
    for b in bridges:
        print(f"  bridge {b['km']:6.2f} km  {b['from']} -> {b['to']}")
