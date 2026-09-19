"""usmap.py — one projection, shared by every map on the site.

An equirectangular box works for two states side by side. It does not work for a
country 4,500 km wide: Maine and Washington slide apart and Texas swells. So every
map here is drawn in Albers equal-area conic — the projection the Census Bureau and
the USGS use for the United States — with Alaska and Hawaii projected separately and
set into the lower-left corner at a stated scale, the way a paper atlas does it.

    fit = fit_states(load(), width=760)
    x, y = project(lon, lat, fit)

Alaska and Hawaii are drawn smaller than they are. fit["ak"]["rel"] says by how much,
every map that shows them prints the number, and that is why Alaska looks the size of
Texas here when it is more than twice that.
"""
from __future__ import annotations

import math
from pathlib import Path

from common import GEO, jload

LOWER48 = dict(lon0=-96.0, lat0=37.5, lat1=29.5, lat2=45.5)
ALASKA = dict(lon0=-154.0, lat0=50.0, lat1=55.0, lat2=65.0)
HAWAII = dict(lon0=-157.0, lat0=20.0, lat1=8.0, lat2=18.0)
PR = dict(lon0=-66.0, lat0=18.0, lat1=17.5, lat2=18.5)


def _albers(lon: float, lat: float, c: dict) -> tuple[float, float]:
    r = math.radians
    n = (math.sin(r(c["lat1"])) + math.sin(r(c["lat2"]))) / 2
    if abs(n) < 1e-9:
        n = 1e-9
    C = math.cos(r(c["lat1"])) ** 2 + 2 * n * math.sin(r(c["lat1"]))
    def rho(phi):
        v = C - 2 * n * math.sin(r(phi))
        return math.sqrt(max(v, 0.0)) / n
    theta = n * r(lon - c["lon0"])
    p, p0 = rho(lat), rho(c["lat0"])
    # y is negated: Albers counts north as positive, SVG counts down.
    return p * math.sin(theta), -(p0 - p * math.cos(theta))


def zone(lon: float, lat: float) -> str:
    """Which inset a point belongs to. Geographic tests, not projected ones."""
    if lat >= 50 and (lon <= -128 or lon >= 165):
        return "ak"
    if lat < 26 and -162 <= lon <= -152:
        return "hi"
    if lon > -70 and lat < 20:
        return "pr"
    return "l48"


def load() -> dict:
    return jload(GEO / "states.json")


def _bbox(geo: dict, want: str, conic: dict) -> tuple:
    xs, ys = [], []
    for st in geo["states"]:
        if zone_of_state(st["iso"]) != want:
            continue
        for ring in st["rings"]:
            for lon, lat in ring:
                # the Aleutians cross the antimeridian and come back as +178°
                if want == "ak" and lon > 0:
                    lon -= 360
                x, y = _albers(lon, lat, conic)
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def fit_states(geo: dict, width: float = 760.0, pad: float = 8.0) -> dict:
    """Scale and offsets for one map, measured from the outlines themselves so the
    drawing fills its box whatever Natural Earth hands us. Alaska, Hawaii and Puerto
    Rico are fitted into rectangles in the lower-left; each inset reports how big it
    is against the lower forty-eight, and the maps print that number."""
    x0, y0, x1, y1 = _bbox(geo, "l48", LOWER48)
    k = (width - 2 * pad) / (x1 - x0)
    h = (y1 - y0) * k + 2 * pad
    fit = {"k": k, "x0": x0, "y0": y0, "pad": pad, "w": width, "h": h}
    fit["ak"] = _inset(geo, "ak", ALASKA, k, (pad, h - 0.30 * h, 0.21 * width, 0.27 * h))
    fit["hi"] = _inset(geo, "hi", HAWAII, k, (pad + 0.225 * width, h - 0.13 * h, 0.11 * width, 0.10 * h))
    fit["pr"] = _inset(geo, "pr", PR, k, (pad + 0.875 * width, h - 0.12 * h, 0.07 * width, 0.07 * h))
    return fit


def _inset(geo: dict, want: str, conic: dict, k48: float, rect: tuple) -> dict:
    """rect is (left, top, width, height) in the map's own pixels."""
    bb = _bbox(geo, want, conic)
    if bb is None:            # Natural Earth's US admin-1 file carries no Puerto Rico
        return None
    bx0, by0, bx1, by1 = bb
    rx, ry, rw, rh = rect
    k = min(rw / (bx1 - bx0), rh / (by1 - by0))
    return {"conic": conic, "k": k, "ax": rx - bx0 * k, "ay": ry - by0 * k,
            "rel": k / k48, "rect": rect}


_STATE_ZONE = {"US-AK": "ak", "US-HI": "hi", "US-PR": "pr"}


def zone_of_state(iso: str) -> str:
    return _STATE_ZONE.get(iso, "l48")


def project(lon: float, lat: float, fit: dict, z: str | None = None) -> tuple[float, float]:
    z = z or zone(lon, lat)
    if z == "l48":
        x, y = _albers(lon, lat, LOWER48)
        return fit["pad"] + (x - fit["x0"]) * fit["k"], fit["pad"] + (y - fit["y0"]) * fit["k"]
    ins = fit.get(z)
    if ins is None:
        z = "l48"
        x, y = _albers(lon, lat, LOWER48)
        return fit["pad"] + (x - fit["x0"]) * fit["k"], fit["pad"] + (y - fit["y0"]) * fit["k"]
    if z == "ak" and lon > 0:
        lon -= 360
    x, y = _albers(lon, lat, ins["conic"])
    return ins["ax"] + x * ins["k"], ins["ay"] + y * ins["k"]


def ring_path(ring: list, fit: dict, z: str) -> str:
    pts = [project(lon, lat, fit, z) for lon, lat in ring]
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def state_paths(geo: dict, fit: dict):
    """Yield (iso, name, svg path data) for every state, insets included."""
    for st in geo["states"]:
        z = zone_of_state(st["iso"])
        if fit.get(z) is None and z != "l48":
            continue
        d = " ".join(ring_path(r, fit, z) for r in st["rings"])
        yield st["iso"], st["name"], d
