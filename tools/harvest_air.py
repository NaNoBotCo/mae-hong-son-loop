#!/usr/bin/env python3
"""harvest_air.py — what the air on the loop has actually done, and what it is doing now.

TWO SOURCES, AND THEY DO NOT AGREE. Both are fetched, both are printed, and where they
disagree the site says so rather than picking.

  --model    Open-Meteo Air Quality: CAMS reanalysis and forecast, hourly PM2.5 and PM10
             at each of the loop's points, 2022-08-01 to today, no key required. A model
             output on a ~40 km grid: it knows the season, it does not know the valley.
             -> data/harvest/air-model.json

  --ground   air4thai, the Thai Pollution Control Department's own monitoring network:
             the current hour at every station, nationwide. ONE station covers the whole
             of Mae Hong Son province (58t, in Mae Hong Son town). Pai, Soppong, Khun Yuam
             and Mae Sariang have none. The PCD's historical endpoint returns 404 as of
             the fetch date, so the ground record here is a single hour, refetched at
             build time.  -> data/harvest/air-ground.json

    python3 tools/harvest_air.py --all
    python3 tools/harvest_air.py --model --from 2022-08-01
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump  # noqa: E402

UA = "mhs-loop-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR4THAI = "https://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
START = "2022-08-01"      # CAMS in Open-Meteo begins here; earlier dates return nulls

# Ten points, spaced around the circuit, each one a place a rider actually sleeps or stops.
POINTS = [
    {"id": "chiang-mai",   "name": "Chiang Mai",    "th": "เชียงใหม่",    "lat": 18.7883, "lon": 98.9853, "ele": 310},
    {"id": "mae-malai",    "name": "Mae Malai",     "th": "แม่มาลัย",     "lat": 19.1206, "lon": 98.9450, "ele": 350},
    {"id": "pai",          "name": "Pai",           "th": "ปาย",         "lat": 19.3592, "lon": 98.4407, "ele": 480},
    {"id": "soppong",      "name": "Soppong",       "th": "สบป่อง",       "lat": 19.4906, "lon": 98.2694, "ele": 640},
    {"id": "mae-hong-son", "name": "Mae Hong Son",  "th": "แม่ฮ่องสอน",   "lat": 19.3020, "lon": 97.9654, "ele": 270},
    {"id": "khun-yuam",    "name": "Khun Yuam",     "th": "ขุนยวม",       "lat": 18.8228, "lon": 97.9336, "ele": 620},
    {"id": "mae-la-noi",   "name": "Mae La Noi",    "th": "แม่ลาน้อย",    "lat": 18.4497, "lon": 97.9678, "ele": 350},
    {"id": "mae-sariang",  "name": "Mae Sariang",   "th": "แม่สะเรียง",   "lat": 18.1614, "lon": 97.9308, "ele": 220},
    {"id": "mae-chaem",    "name": "Mae Chaem",     "th": "แม่แจ่ม",      "lat": 18.4967, "lon": 98.3714, "ele": 470},
    {"id": "hot",          "name": "Hot",           "th": "ฮอด",         "lat": 18.1447, "lon": 98.5847, "ele": 290},
]

# US EPA PM2.5 breakpoints, 24-hour average, µg/m³ -> AQI. The 2024 revision lowered the
# Good/Moderate break from 12.0 to 9.0; that revision is what is used here.
BREAKS = [(0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
          (55.5, 125.4, 151, 200), (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500)]
BANDS = [(0, 50, "good", "Good", "ดี"),
         (51, 100, "moderate", "Moderate", "ปานกลาง"),
         (101, 150, "sensitive", "Unhealthy for sensitive groups", "เริ่มมีผลต่อสุขภาพ"),
         (151, 200, "unhealthy", "Unhealthy", "มีผลต่อสุขภาพ"),
         (201, 300, "very", "Very unhealthy", "มีผลต่อสุขภาพมาก"),
         (301, 999, "hazardous", "Hazardous", "อันตราย")]


def aqi_from_pm25(c: float) -> int:
    c = round(c, 1)
    for lo, hi, alo, ahi in BREAKS:
        if lo <= c <= hi:
            return round((ahi - alo) / (hi - lo) * (c - lo) + alo)
    return 500


def band(aqi: int) -> dict:
    for lo, hi, key, en, th in BANDS:
        if lo <= aqi <= hi:
            return {"key": key, "en": en, "th": th}
    return {"key": "hazardous", "en": "Hazardous", "th": "อันตราย"}


def get(url: str, params: dict | None = None, tries: int = 4):
    u = url + ("?" + urllib.parse.urlencode(params) if params else "")
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 + 4 * i)
    raise RuntimeError(f"{url}: {err}")


def model(start: str, dry=False) -> dict:
    today = dt.date.today()
    end = (today - dt.timedelta(days=1)).isoformat()
    out = {"source": "Open-Meteo Air Quality API (CAMS)", "url": AQ,
           "licence": "CC BY 4.0", "licence_url": "https://creativecommons.org/licenses/by/4.0/",
           "attribution": "Open-Meteo.com, from Copernicus Atmosphere Monitoring Service",
           "fetched": today.isoformat(), "start": start, "end": end,
           "aqi_scale": "US EPA PM2.5, 2024 revision (Good/Moderate break at 9.0 µg/m³)",
           "note": ("Hourly PM2.5 from a continental model on a coarse grid, reduced here to a daily "
                    "mean per point and then to a per-month record across every year fetched. A model "
                    "cell is tens of kilometres wide and a Mae Hong Son valley is not; treat these as "
                    "the shape of the season, not as a reading taken where you are standing."),
           "points": []}
    for p in POINTS:
        print(f"air model: {p['name']} …", flush=True)
        d = get(AQ, {"latitude": p["lat"], "longitude": p["lon"], "hourly": "pm2_5,pm10",
                     "start_date": start, "end_date": end, "timezone": "Asia/Bangkok"})
        h = d["hourly"]
        daily: dict[str, list] = {}
        for t, v in zip(h["time"], h["pm2_5"]):
            if v is not None:
                daily.setdefault(t[:10], []).append(v)
        days = {k: round(sum(v) / len(v), 1) for k, v in daily.items() if len(v) >= 18}
        months: dict[str, list] = {}
        for k, v in days.items():
            months.setdefault(k[5:7], []).append(v)
        by_month = {}
        for m, vals in sorted(months.items()):
            vals = sorted(vals)
            n = len(vals)
            by_month[m] = {
                "days": n,
                "mean": round(sum(vals) / n, 1),
                "median": round(vals[n // 2], 1),
                "p90": round(vals[int(n * 0.9)], 1),
                "max": round(vals[-1], 1),
                "aqi_mean": aqi_from_pm25(sum(vals) / n),
                "aqi_p90": aqi_from_pm25(vals[int(n * 0.9)]),
                "aqi_max": aqi_from_pm25(vals[-1]),
                "over_35": sum(1 for v in vals if v > 35.4),       # above the US 24-h standard
                "over_55": sum(1 for v in vals if v > 55.4),       # Unhealthy for everyone
                "over_125": sum(1 for v in vals if v > 125.4),     # Very unhealthy
            }
        years: dict[str, dict] = {}
        for k, v in days.items():
            y = k[:4]
            years.setdefault(y, {"days": 0, "over_35": 0, "over_55": 0, "over_125": 0, "max": 0})
            years[y]["days"] += 1
            years[y]["max"] = max(years[y]["max"], v)
            for lim, key in ((35.4, "over_35"), (55.4, "over_55"), (125.4, "over_125")):
                if v > lim:
                    years[y][key] += 1
        out["points"].append(dict(p, days=len(days), by_month=by_month, by_year=years,
                                  worst_day=max(days.items(), key=lambda kv: kv[1]) if days else None,
                                  daily=days))
        worst = max(by_month.items(), key=lambda kv: kv[1]["mean"]) if by_month else ("--", {})
        print(f"  {p['name']}: {len(days)} days, worst month {worst[0]} "
              f"mean {worst[1].get('mean')} µg/m³ (AQI {worst[1].get('aqi_mean')})")
        time.sleep(1.5)
    if not dry:
        jdump(out, HARVEST / "air-model.json", indent=0)
        print(f"wrote {HARVEST / 'air-model.json'}")
    return out


def haversine_km(a, b):
    import math
    R = 6371.0088
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def ground(dry=False) -> dict:
    print("air ground: air4thai …", flush=True)
    d = get(AIR4THAI)
    rows = []
    for s in d.get("stations", []):
        try:
            lat, lon = float(s["lat"]), float(s["long"])
        except (TypeError, ValueError):
            continue
        if not (17.4 <= lat <= 20.3 and 97.3 <= lon <= 100.6):
            continue
        last = s.get("AQILast") or {}
        pm25 = (last.get("PM25") or {}).get("value")
        aqi = (last.get("AQI") or {}).get("aqi")
        near = min(POINTS, key=lambda p: haversine_km((lat, lon), (p["lat"], p["lon"])))
        rows.append({"station": s.get("stationID"), "name_en": s.get("nameEN"), "name_th": s.get("nameTH"),
                     "area_en": s.get("areaEN"), "area_th": s.get("areaTH"), "lat": lat, "lon": lon,
                     "pm25": None if pm25 in (None, "-", "") else float(pm25),
                     "aqi": None if aqi in (None, "-", "") else int(aqi),
                     "time": f"{last.get('date', '')} {last.get('time', '')}".strip(),
                     "nearest_point": near["id"],
                     "km_from_point": round(haversine_km((lat, lon), (near["lat"], near["lon"])), 1)})
    on_loop = [r for r in rows if r["km_from_point"] <= 25]
    out = {"source": "Pollution Control Department, Thailand (air4thai)", "url": AIR4THAI,
           "attribution": "กรมควบคุมมลพิษ / Pollution Control Department",
           "fetched": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "note": ("Every PCD station in upper northern Thailand, with the hour it last reported. "
                    "The PCD's historical endpoint returned 404 on the fetch date, so this file is "
                    "one hour deep and is refetched at build time. Mae Hong Son province — 12,765 km² — "
                    "has one station, 58t, in Mae Hong Son town."),
           "stations_north": len(rows), "stations_near_loop": len(on_loop),
           "mhs_province_stations": [r["station"] for r in rows if "Mae Hong Son" in (r["area_en"] or "")],
           "rows": rows}
    for r in sorted(rows, key=lambda r: r["km_from_point"])[:6]:
        print(f"  {r['station']} {r['name_en'][:40]:40} PM2.5 {r['pm25']} AQI {r['aqi']} "
              f"({r['km_from_point']} km from {r['nearest_point']})")
    print(f"  Mae Hong Son province stations: {out['mhs_province_stations']}")
    if not dry:
        jdump(out, HARVEST / "air-ground.json", indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="store_true")
    ap.add_argument("--ground", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--from", dest="start", default=START)
    a = ap.parse_args()
    if a.all or a.ground:
        ground(a.dry)
    if a.all or a.model:
        model(a.start, a.dry)
    if not (a.all or a.model or a.ground):
        ap.print_help()
