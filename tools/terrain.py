#!/usr/bin/env python3
"""terrain.py — the land, rendered once to a PNG.

Shaded relief is a per-pixel job and SVG is the wrong container for it: drawn as
rectangles the same image came to 75,000 elements and five megabytes. This writes it as
an image instead, at the shared projection, so every map on the site can lay its roads
over the same picture.

The elevation lattice is coarse (about 2 km) and has holes, because the free API
throttles. Both are handled and both are stated: holes are filled from neighbours by
inverse distance, and the whole grid is bilinearly resampled to pixel resolution. What
comes out is a good impression of where the mountains are. It is not a survey.

    python3 tools/terrain.py            # build/site/terrain.png
    python3 tools/terrain.py --dark
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
from common import BUILD, jload, load_harvest  # noqa: E402


def render(out_path: Path, box, width=1600, dark=False, az=315.0, alt=40.0, zf=6.0):
    from PIL import Image
    elev = load_harvest("elevation")
    if not elev or not elev.get("grid"):
        print("no elevation harvest — run tools/harvest_base.py --elevation")
        return None
    step = elev["step_deg"]
    meta, Z, holes = geo._regular(elev["grid"], step)
    lat0, lon0, step, nr, nc = meta
    p = geo.Proj(box=box, width=width)
    W, H = int(p.width), int(p.height)
    ramp = geo.RAMP_DARK if dark else geo.RAMP

    # metres per lattice cell, for the slope
    mid = math.radians(lat0 + (nr - 1) * step / 2)
    dy = step * 111320.0
    dx = step * 111320.0 * math.cos(mid)
    az_r, alt_r = math.radians(360 - az + 90), math.radians(alt)

    # precompute shade and colour per lattice cell, then bilinear per pixel
    shade = [[0.0] * nc for _ in range(nr)]
    for r in range(nr):
        for c in range(nc):
            w = Z[r][max(c - 1, 0)]; e = Z[r][min(c + 1, nc - 1)]
            s_ = Z[max(r - 1, 0)][c]; n = Z[min(r + 1, nr - 1)][c]
            dzdx = (e - w) / (2 * dx) * zf
            dzdy = (n - s_) / (2 * dy) * zf
            slope = math.atan(math.hypot(dzdx, dzdy))
            aspect = math.atan2(dzdy, -dzdx)
            v = (math.sin(alt_r) * math.cos(slope)
                 + math.cos(alt_r) * math.sin(slope) * math.cos(az_r - aspect))
            shade[r][c] = max(0.0, min(1.0, v))

    def bilin(G, fr, fc):
        r0 = max(0, min(int(fr), nr - 2)); c0 = max(0, min(int(fc), nc - 2))
        tr = min(max(fr - r0, 0), 1); tc = min(max(fc - c0, 0), 1)
        a = G[r0][c0] * (1 - tc) + G[r0][c0 + 1] * tc
        b = G[r0 + 1][c0] * (1 - tc) + G[r0 + 1][c0 + 1] * tc
        return a * (1 - tr) + b * tr

    img = Image.new("RGB", (W, H), (240, 236, 226) if not dark else (18, 16, 13))
    px = img.load()
    s_lat, w_lon, n_lat, e_lon = p.s, p.w, p.n, p.e
    for y in range(H):
        lat = n_lat - (y - p.pad) / p.scale
        fr = (lat - lat0) / step
        for x in range(W):
            lon = w_lon + (x - p.pad) / (p.scale * p.kx)
            fc = (lon - lon0) / step
            if not (-0.5 <= fr <= nr - 0.5 and -0.5 <= fc <= nc - 0.5):
                continue
            m = bilin(Z, fr, fc)
            sh = bilin(shade, fr, fc)
            col = geo._ramp(m, ramp)
            k = 0.52 + 0.95 * sh
            px[x, y] = tuple(max(0, min(255, int(v * k))) for v in col)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    kb = out_path.stat().st_size / 1024
    print(f"{out_path.name}: {W}x{H}, {kb:.0f} KB · lattice {nr}x{nc}, {holes} cells filled")
    return {"w": W, "h": H, "holes": holes, "lattice": [nr, nc]}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--out", default=str(BUILD / "site" / "terrain.png"))
    a = ap.parse_args()
    roads = jload(BUILD / "api" / "roads.json") if (BUILD / "api" / "roads.json").exists() else {}
    lines = [[tuple(c) for c in ln] for r in roads.values()
             for ln in (r.get("lines") or ([r["line"]] if r.get("line") else []))]
    render(Path(a.out), geo.fit(lines) if lines else geo.BOX, a.width, a.dark)
