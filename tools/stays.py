# -*- coding: utf-8 -*-
"""Beds by overnight town: OpenStreetMap and Overture merged, with road distance.

    python3 tools/stays.py --fetch     # pull each town's streets from Overpass (cached)
    python3 tools/stays.py             # merge, measure, write data/harvest/stays.json

Inputs: data/harvest/osm-places.json (kind "stay"), data/harvest/overture-stays.json
(tools/harvest_stays.py), and each town's drivable streets cached to
data/harvest/_raw/streets-<town>.json. Road distance is the shortest drivable path
over those streets from the town record's centre point to the stay, snapped to the
nearest street node at each end; where a stay sits off the fetched streets the row
carries the straight-line figure and says so.

A row appears once: an Overture row within 300 m of an OSM row with the same name
(case, spaces and punctuation ignored, or one name inside the other) is folded into
it, and lends its phone and website where OSM has none.
"""
import heapq
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
H = ROOT / "data" / "harvest"
RAW = H / "_raw"
OUT = H / "stays.json"

# the overnight stops, in clockwise riding order; radius in km
TOWNS = [("chiang-mai", "town", 2.0), ("pai", "town", 6.0), ("soppong", "town", 6.0), ("mae-hong-son", "town", 6.0),
         ("khun-yuam", "town", 6.0), ("mae-sariang", "town", 6.0), ("mae-chaem", "town", 6.0),
         ("doi-inthanon", "stop", 8.0)]
# Distances run from OpenStreetMap's own point for the town (place=town). Soppong's
# place point is a different hamlet 3 km off, so its post office stands in; Doi
# Inthanon's is the summit, from its stop record.
CENTRE = {"chiang-mai": ("node/178056220", None, None, "Chiang Mai", "เชียงใหม่"),
          "pai": ("node/262585787", 19.3592, 98.4407, "Pai", "ปาย"),
          "soppong": ("node/1595640782", 19.5155583, 98.2549603, "Soppong Post Office", "ไปรษณีย์สบป่อง"),
          "mae-hong-son": ("node/301515447", None, None, "Mae Hong Son", "แม่ฮ่องสอน"),
          "khun-yuam": ("node/301516444", None, None, "Khun Yuam", "ขุนยวม"),
          "mae-sariang": ("node/301560655", None, None, "Mae Sariang", "แม่สะเรียง"),
          "mae-chaem": ("node/1287231656", None, None, "Mae Chaem", "แม่แจ่ม")}
MIN_CONF = 0.5          # Overture rows under this are left out
ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter",
             "https://overpass.private.coffee/api/interpreter"]
UA = "mae-hong-son-loop/1.0 (https://motdang.net/loop)"
DRIVE = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street|track|road|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"


def km(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


PLACE_PT = {}


def centre(tid, kind):
    n = json.loads((ROOT / "data" / "nodes" / kind / f"{tid}.json").read_text())
    c = CENTRE.get(tid)
    if not c:
        return n, (n["geo"]["lat"], n["geo"]["lon"]), None
    if c[1] is None:
        if not PLACE_PT:
            for r in json.loads((H / "osm-places.json").read_text())["rows"]:
                PLACE_PT[r["osm"]] = (r["lat"], r["lon"])
        lat, lon = PLACE_PT[c[0]]
    else:
        lat, lon = c[1], c[2]
    return n, (lat, lon), {"osm": c[0], "name": c[3], "th": c[4]}


def bbox(c, r):
    dlat = (r + 1.5) / 111.32
    dlon = (r + 1.5) / (111.32 * math.cos(math.radians(c[0])))
    return (c[0] - dlat, c[1] - dlon, c[0] + dlat, c[1] + dlon)


def fetch():
    RAW.mkdir(parents=True, exist_ok=True)
    for tid, kind, r in TOWNS:
        f = RAW / f"streets-{tid}.json"
        if f.exists():
            print(f"{tid}: cached")
            continue
        _, c, _ = centre(tid, kind)
        s, w, n, e = bbox(c, r)
        q = f'[out:json][timeout:90];way["highway"~"^({DRIVE})$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});out geom;'
        for i in range(6):
            ep = ENDPOINTS[i % len(ENDPOINTS)]
            try:
                req = urllib.request.Request(ep, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": UA})
                d = json.loads(urllib.request.urlopen(req, timeout=120).read())
                f.write_text(json.dumps({"fetched": date.today().isoformat(), "endpoint": ep,
                                         "elements": d.get("elements", [])}))
                print(f"{tid}: {len(d.get('elements', []))} ways from {ep}")
                break
            except Exception as ex:                       # pragma: no cover
                print(f"{tid}: {ep} {ex}", file=sys.stderr)
                time.sleep(8 * (i + 1))


class Streets:
    def __init__(self, elements):
        self.adj, self.pt = {}, {}
        for w in elements:
            g = w.get("geometry") or []
            nodes = w.get("nodes") or list(range(len(g)))
            for i, p in enumerate(g):
                self.pt[nodes[i]] = (p["lat"], p["lon"])
            for i in range(len(g) - 1):
                a, b = nodes[i], nodes[i + 1]
                d = km(self.pt[a], self.pt[b])
                self.adj.setdefault(a, []).append((b, d))
                self.adj.setdefault(b, []).append((a, d))
        # only the largest connected piece is snapped to: a service road fenced off
        # inside a compound is not a way to the front door
        seen, best = set(), set()
        for start in self.adj:
            if start in seen:
                continue
            comp, stack = {start}, [start]
            while stack:
                u = stack.pop()
                for v, _ in self.adj.get(u, ()):
                    if v not in comp:
                        comp.add(v)
                        stack.append(v)
            seen |= comp
            if len(comp) > len(best):
                best = comp
        # a coarse grid for snapping
        self.grid = {}
        for nid in best:
            la, lo = self.pt[nid]
            self.grid.setdefault((int(la * 200), int(lo * 200)), []).append(nid)

    def snap(self, p):
        best, bd = None, 9e9
        gy, gx = int(p[0] * 200), int(p[1] * 200)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for nid in self.grid.get((gy + dy, gx + dx), ()):
                    d = km(p, self.pt[nid])
                    if d < bd:
                        best, bd = nid, d
        return best, bd

    def dists(self, src):
        dist = {src: 0.0}
        q = [(0.0, src)]
        while q:
            d, u = heapq.heappop(q)
            if d > dist.get(u, 9e9):
                continue
            for v, w in self.adj.get(u, ()):
                nd = d + w
                if nd < dist.get(v, 9e9):
                    dist[v] = nd
                    heapq.heappush(q, (nd, v))
        return dist


def norm(s):
    return re.sub(r"[\W_]+", "", (s or "").lower())


def same(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    return na == nb or (min(len(na), len(nb)) >= 5 and (na in nb or nb in na))


GENERIC = {"guest", "house", "guesthouse", "resort", "hotel", "hostel", "home", "homestay",
           "lodge", "camp", "bungalow", "bungalows", "room", "rooms", "village", "valley", "river",
           "garden", "hill", "view", "boutique", "place", "baan", "ban", "huen", "pang", "inn",
           "mapha", "pangmapha", "soppong", "maehongson", "mae", "hong", "sariang", "chaem",
           "khun", "yuam", "inthanon", "doi", "thailand", "the", "and"}


def tokens(s):
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower()) if w not in GENERIC}


def is_twin(g, r):
    """Is Overture row r the same place as held row g?"""
    d = km((g["lat"], g["lon"]), (r["lat"], r["lon"]))
    if d > 0.3:
        return False
    names = [g["name"], g["name_th"]]
    if any(same(x, r["name"]) for x in names):
        return True
    ga, rb = tokens(" ".join(filter(None, names))), tokens(r["name"])
    if d <= 0.08 and (ga & rb or any(t in norm(r["name"]) for t in ga)
                      or any(t in norm(" ".join(filter(None, names))) for t in rb)):
        return True
    ph = re.sub(r"\D", "", r.get("phone") or "")[-8:]
    return d <= 0.15 and len(ph) == 8 and ph == re.sub(r"\D", "", g.get("phone") or "")[-8:]


def has_thai(s):
    return bool(s) and any("฀" <= ch <= "๿" for ch in s)


def web(u):
    if not u:
        return None
    u = u.strip()
    return u if u.startswith("http") else "https://" + u


def route(tid, c, got):
    """Road distance over the town's own streets, written into each row."""
    f = RAW / f"streets-{tid}.json"
    if not f.exists():
        return 0
    st = Streets(json.loads(f.read_text())["elements"])
    src, sd = st.snap(c)
    dist = st.dists(src) if src is not None else {}
    n = 0
    for g in got:
        nid, gd = st.snap((g["lat"], g["lon"]))
        if nid is not None and nid in dist and gd <= 0.4 and sd <= 0.4:
            g["road_km"] = round(dist[nid] + gd + sd, 1)
            n += 1
    return n


MOTDANG = Path.home() / "Developer" / "claude code projects" / "mot-dang"
CM_SHOW = 24         # beds listed for the Chiang Mai nights
RENT_M = 0.3         # rental shops counted within this many km of a bed


def _compact(i):
    """The tail of motdang's page filename for a record id (build.py _slug_stem)."""
    return re.sub(r"\D", "", i) or re.sub(r"[^a-z0-9]", "", i.lower())


def chiang_mai(c):
    """Beds for the night before and after, from motdang's Chiang Mai catalogue.

    Kept: a hotel, guesthouse or hostel record with an exact pin within 1.5 km of the
    old city's OSM point and a phone or website of its own. Ranked by how many
    scooter and car rental shops motdang holds within 300 m, then by distance."""
    cat = MOTDANG / "data" / "canonical" / "cm.json"
    pdir = MOTDANG / "docs" / "cm" / "p"
    if not cat.exists():
        return None
    recs = json.loads(cat.read_text())
    pages = {}
    if pdir.exists():
        for fn in (x.name for x in pdir.iterdir()):
            if fn.endswith(".html"):
                pages[fn[:-5].rsplit("-", 1)[-1]] = fn
    rent = re.compile(r"rent|เช่า", re.I)
    shops = [(r["lat"], r["lng"]) for r in recs if r.get("lat") and "transport" in (r.get("cat") or [])
             and ("rental" in (r.get("sub") or []) or rent.search(" ".join(filter(None, [
                 r.get("name"), r.get("nameEn"), (r.get("attrs") or {}).get("kind")]))))]
    out = []
    for r in recs:
        if "hotel" not in (r.get("cat") or []) or not r.get("lat") or r.get("geoPrecision") != "exact":
            continue
        if not (r.get("phone") or r.get("website")):
            continue
        p = (r["lat"], r["lng"])
        d = km(c, p)
        if d > 1.5:
            continue
        a = r.get("attrs") or {}
        page = pages.get(_compact(r["id"]))
        out.append({"id": "md:" + r["id"],
                    "name": r.get("nameEn") or (r["name"] if not has_thai(r["name"]) else None),
                    "name_th": r.get("nameTh") or (r["name"] if has_thai(r["name"]) else None),
                    "lat": r["lat"], "lon": r["lng"], "crow_km": round(d, 2),
                    "kind": (r.get("sub") or [None])[0],
                    "phone": r.get("phone"), "website": web(r.get("website")), "rooms": None,
                    "facebook": a.get("facebook"), "src": ["motdang"],
                    "motdang": f"https://motdang.net/cm/p/{page}" if page else None,
                    "rentals_300m": sum(1 for q in shops if km(p, q) <= RENT_M)})
    out.sort(key=lambda g: (-g["rentals_300m"], g["crow_km"]))
    return out[:CM_SHOW]


def build():
    osm = json.loads((H / "osm-places.json").read_text())
    ov = json.loads((H / "overture-stays.json").read_text())
    osm_rows = [r for r in osm["rows"] if r["kind"] == "stay" and r.get("name")]
    ov_rows = [r for r in ov["rows"] if (r.get("confidence") or 0) >= MIN_CONF
               and r.get("status") not in ("permanently_closed", "closed")]
    towns = []
    for tid, kind, rad in TOWNS:
        n, c, cref = centre(tid, kind)
        if tid == "chiang-mai":
            got = chiang_mai(c)
            if got is None:            # mot-dang not on this machine: keep the last build
                old = json.loads(OUT.read_text()) if OUT.exists() else {"towns": []}
                towns += [t for t in old["towns"] if t["id"] == tid]
                continue
            route(tid, c, got)
            towns.append({"id": tid, "type": kind, "name": n["names"]["name"], "th": n["names"].get("th"),
                          "lat": c[0], "lon": c[1], "centre": cref, "radius_km": rad,
                          "routed": sum(1 for g in got if "road_km" in g), "streets": True,
                          "source": "motdang", "stays": got})
            print(f"{tid}: {len(got)} stays from motdang")
            continue
        got = []
        for r in osm_rows:
            d = km(c, (r["lat"], r["lon"]))
            if d <= rad:
                t = r.get("tags") or {}
                nm_en = t.get("name:en") or (r["name"] if not has_thai(r["name"]) else None)
                nm_th = r.get("name_th") or t.get("name:th") or (r["name"] if has_thai(r["name"]) else None)
                got.append({"id": "osm:" + r["osm"], "name": nm_en, "name_th": nm_th,
                            "lat": r["lat"], "lon": r["lon"], "crow_km": round(d, 2),
                            "kind": t.get("tourism"),
                            "phone": t.get("phone") or t.get("contact:phone"),
                            "website": web(t.get("website") or t.get("contact:website")),
                            "rooms": t.get("rooms"),
                            "src": ["osm"], "osm": r["osm"], "facebook": None})
        for r in ov_rows:
            d = km(c, (r["lat"], r["lon"]))
            if d > rad:
                continue
            twin = next((g for g in got if is_twin(g, r)), None)
            fb = next((s for s in r.get("socials") or [] if "facebook.com" in s), None)
            if twin:
                if "overture" not in twin["src"]:
                    twin["src"].append("overture")
                twin["phone"] = twin["phone"] or r.get("phone")
                twin["website"] = twin["website"] or web(r.get("website"))
                twin["facebook"] = twin["facebook"] or fb
                twin.setdefault("ov", r["id"])
                if has_thai(r["name"]):
                    twin["name_th"] = twin["name_th"] or r["name"]
                else:
                    twin["name"] = twin["name"] or r["name"]
                continue
            got.append({"id": "ov:" + r["id"], "ov": r["id"],
                        "name": r.get("name_en") or (r["name"] if not has_thai(r["name"]) else None),
                        "name_th": r.get("name_th") or (r["name"] if has_thai(r["name"]) else None),
                        "lat": r["lat"], "lon": r["lon"], "crow_km": round(d, 2), "kind": r["cat"],
                        "phone": r.get("phone"), "website": web(r.get("website")), "rooms": None,
                        "src": ["overture"], "facebook": fb})
        f = RAW / f"streets-{tid}.json"
        routed = route(tid, c, got)
        got.sort(key=lambda g: (g.get("road_km", g["crow_km"]), g["name"] or g["name_th"] or ""))
        towns.append({"id": tid, "type": kind, "name": n["names"]["name"], "th": n["names"].get("th"),
                      "lat": c[0], "lon": c[1], "centre": cref, "radius_km": rad, "routed": routed,
                      "streets": f.exists(), "stays": got})
        print(f"{tid}: {len(got)} stays, {routed} routed by road, "
              f"{sum(1 for g in got if g['phone'])} phone, {sum(1 for g in got if g['website'])} site")
    OUT.write_text(json.dumps({
        "built": date.today().isoformat(),
        "sources": {"motdang": {"file": "mot-dang data/canonical/cm.json", "read": date.today().isoformat(),
                                "url": "https://motdang.net/"},
                    "osm": {"fetched": osm["fetched"], "licence": osm["licence"], "attribution": osm["attribution"]},
                    "overture": {"release": ov["release"], "fetched": ov["fetched"], "licence": ov["licence"],
                                 "attribution": ov["attribution"], "min_confidence": MIN_CONF}},
        "note": "Places to sleep near each overnight stop. A row is what OpenStreetMap or Overture "
                "Places holds; road_km is the shortest drivable path from the town centre over "
                "OpenStreetMap streets, crow_km the straight line.",
        "towns": towns}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    build()
