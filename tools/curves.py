#!/usr/bin/env python3
"""curves.py — count the bends, and say what the count cannot see.

A CURVE IS A LEAN. The road snakes: left, right, left, and a rider counts each one. An
earlier version of this tool accumulated turn until the direction reversed and called
that one arc, which collapses a whole snaking kilometre into a handful of "curves" and
produced a figure five times too low. It counted 395 between Mae Malai and Pai and was
then compared against 1,864 — a number that is for the whole Chiang Mai to Mae Hong Son
run, not that 97 km span. Two errors stacked.

What is counted here is every change of turning direction along the road, which is every
time a rider changes which way they are leaning.

THE COUNT IS A FLOOR, and this is the important part. OpenStreetMap traces this road with
a point roughly every 40 metres, so a bend that occupies less than about 80 metres of
road cannot appear in the data at all. Volunteers also cut corners. The number below is
therefore the least it can be, never the most.

    python3 tools/curves.py            # write data/harvest/curve-analysis.json
    python3 tools/curves.py --print    # table to stdout, write nothing

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

THRESHOLDS = (4, 6, 10, 20)
DEFAULT = 4

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
    {"figure": 1864, "of": "Chiang Mai to Mae Hong Son",
     "carried_by": "the roadside sign, and the shirts sold in Pai",
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


def bends(line, step_km=0.03, min_deg=DEFAULT):
    """Every change of turning direction — one lean, one count. `min_deg` is how much a
    bend has to add up to before it counts, so a camber correction does not."""
    from harvest_osm import bearing, resample
    res = resample(line, step_km)
    runs, acc, sign = [], 0.0, 0
    for j in range(1, len(res) - 1):
        b1 = bearing(res[j - 1], res[j])
        b2 = bearing(res[j], res[j + 1])
        dd = (b2 - b1 + 540) % 360 - 180
        if abs(dd) > 150:        # a spike is a data artefact, not a turn
            dd = 0.0
        s = 1 if dd > 0.35 else (-1 if dd < -0.35 else 0)
        if s == 0:
            continue
        if s == sign:
            acc += dd
        else:
            if abs(acc) >= min_deg:
                runs.append(abs(acc))
            acc, sign = dd, s
    if abs(acc) >= min_deg:
        runs.append(abs(acc))
    return runs


def measure(seg: list) -> dict:
    km = chain_km(seg)
    at = {}
    for t in THRESHOLDS:
        n = len(bends(seg, min_deg=t))
        at[str(t)] = {"curves": n, "per_km": round(n / km, 2) if km else 0}
    runs = bends(seg, min_deg=DEFAULT)
    n = len(runs)
    # a hairpin is still a sustained 120-degree arc; that definition was never the problem
    cv = count_curves(seg, min_turn=25)
    return {"km": round(km, 1), "at_threshold": at, "threshold_used": DEFAULT,
            "curves": n, "hairpins": cv["hairpins"], "tight": cv["tight"],
            "per_km": round(n / km, 2) if km else 0,
            "metres_per_curve": round(km * 1000 / n, 1) if n else None,
            "is_floor": True}


# The yardstick, and why the count moves with it -------------------------------------
# A road is not a shape with a number of curves in it. Measure it with a coarse rule and
# the small bends vanish into the straight between two big ones; measure it finer and
# each of those straights turns out to have bends in it too. Richardson found the same
# thing measuring coastlines in the 1950s and Mandelbrot named it: the length of a
# coastline depends on the length of your ruler, and it does not converge.
#
# So this counts the same road at eight rulers and publishes all of them. The site's
# figure is the 30 m / 4-degree cell, which is reproducible because the cell is named --
# not because it is the true number. There is no true number.
YARD_STEPS = [0.01, 0.02, 0.03, 0.06, 0.12, 0.25, 0.5, 1.0]
YARD_DEGS = [2, 4, 8, 15, 25, 45]


def yardstick(line: list) -> dict:
    """The same road counted at every ruler, so the reader can see the count move."""
    from harvest_osm import haversine
    km = sum(haversine(line[i], line[i + 1]) for i in range(len(line) - 1))
    grid = {}
    for st in YARD_STEPS:
        runs = bends(line, step_km=st, min_deg=1)
        grid[str(int(st * 1000))] = {str(d): sum(1 for a in runs if abs(a) >= d)
                                     for d in YARD_DEGS}
    return {"km": round(km, 1), "points": len(line),
            # how finely the survey itself sees the road: no ruler shorter than this
            # reveals anything, it only interpolates between two points that exist
            "metres_per_point": round(km * 1000 / len(line)) if line else None,
            "step_m": [int(x * 1000) for x in YARD_STEPS],
            "degrees": list(YARD_DEGS), "grid": grid}


def density(line: list, window_km: float = 2.0) -> list:
    """Curve density along the road, in fixed windows, so the map can colour it.

    This is not a crash map. Nobody publishes one for these roads, and none is invented
    here. It is a map of how much steering a stretch asks for per kilometre, computed the
    same way everywhere, which is a different claim and a checkable one.
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
                    "per_km": round(per, 2), "band": band,
                    # dropped again below for all but the hardest few: a polyline per
                    # window would multiply curves.json by the length of the road
                    "_line": [[round(a, 5), round(b, 5)] for a, b in seg],
                    "_apex": cv.get("apex", [])})
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
    out = {"method": ("Ways carrying the route number are stitched end to end, resampled every "
                      "30 m, and walked counting every change of turning direction — one lean, one "
                      "curve. A bend counts once it adds up to 4 degrees, so a camber correction "
                      "does not. A hairpin is a sustained arc of 120 degrees or more."),
           # Not a floor under a true number: there is no true number. A road has a curve
           # count the way a coastline has a length -- only once you say how long the
           # ruler is. See `yardstick`, which counts the same road at eight of them.
           "floor": ("Every count here is a count at a stated ruler: the road sampled every "
                     "30 m, a bend counted once it adds up to 4 degrees. It is reproducible, "
                     "not true. Halve the ruler and the number climbs; the same road measured "
                     "at 1 km gives a twelfth of what it gives at 10 m. What bounds the fine "
                     "end is the survey, not the asphalt. See `yardstick` in this file."),
           "step_m": 30, "thresholds": list(THRESHOLDS), "threshold_used": DEFAULT,
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
        # Two stitches, on purpose. MEASUREMENT uses the strict one (30 m joins, then a
        # 2.5 km second pass) so a curve count is never inflated by an invented straight.
        # DRAWING uses a looser one: a route number goes untagged for several kilometres
        # through a town centre, and a map with holes in it is worse than a map with a
        # few straight kilometres in it. The strict chain is what `whole` and `spans`
        # are computed from; these are only ever drawn.
        from harvest_osm import simplify, _join
        draw = _join([list(c) for c in load_chains(ref)], 6.0)
        r["lines"] = [[[round(x, 5), round(y, 5)] for x, y in simplify(c, 0.06)]
                      for c in draw if chain_km(c) > 1.5]
        r["chains"] = len(r["lines"])
        r["density"] = density(line)
        r["bands"] = BANDS
        # twenty rather than three: a leg asks for the hardest window *on that leg*, and
        # the worst few on a road can all sit inside one of the four legs that use it.
        # Pai to Soppong had none of the top eight anywhere near it.
        worst = sorted(r["density"], key=lambda d: -d["per_km"])[:20]
        # the hardest windows keep their geometry; everything else sheds it
        r["hardest"] = [dict(w, line=w["_line"], apex=w["_apex"]) for w in worst]
        for w in r["density"]:
            w.pop("_line", None)
            w.pop("_apex", None)
        for w in r["hardest"]:
            w.pop("_line", None)
            w.pop("_apex", None)
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
    # 1,864 is carried for the whole Chiang Mai to Mae Hong Son run, which Thai Wikipedia
    # gives as about 245 km — not for any single span. Compare it against that.
    FULL_KM = 245.0
    whole95 = p95.get("whole") or {}
    r107 = out["roads"].get("107", {}).get("whole") or {}
    traced_km = (whole95.get("km") or 0) + (r107.get("km") or 0)
    traced_bends = (whole95.get("curves") or 0) + (r107.get("curves") or 0)
    scaled = round(traced_bends * FULL_KM / traced_km) if traced_km else 0
    # the same run, counted at eight rulers
    full_line = load_line("1095") + load_line("107")
    out["yardstick"] = yardstick(full_line)
    out["yardstick"]["published_cell"] = {"step_m": 30, "degrees": DEFAULT}
    out["full_route"] = {"km_published": FULL_KM, "km_traced": round(traced_km, 1),
                         "bends_traced": traced_bends, "bends_scaled_to_published": scaled,
                         "metres_per_bend": round(FULL_KM * 1000 / scaled, 0) if scaled else None,
                         "source_km": "s:thwp-1095"}
    out["claims"][0]["implies_metres_per_curve"] = round(FULL_KM * 1000 / 1864, 0)
    out["claims"][0]["measured_over_same_span"] = scaled
    out["claims"][0]["span_km"] = FULL_KM
    if p95.get("whole"):
        out["claims"][1]["implies_metres_per_curve"] = round(FULL_KM * 1000 / 2000, 0)
        out["claims"][1]["measured_over_same_span"] = scaled
        out["claims"][1]["span_km"] = FULL_KM
    if not a.show:
        jdump(out, HARVEST / "curve-analysis.json", indent=1)
        print(f"wrote {HARVEST / 'curve-analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
