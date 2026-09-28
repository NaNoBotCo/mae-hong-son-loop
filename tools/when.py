# -*- coding: utf-8 -*-
"""when.py — a rating for every 4-day trip start in the coming year: smoke, rain, crowds.

    python3 tools/when.py --fetch   # refresh the rain climatology (Open-Meteo archive, ERA5)
    python3 tools/when.py           # rescore into data/harvest/when.json

Rain: daily totals 1996–2025 at five loop towns, reduced to the share of days with
5 mm or more, by calendar date, smoothed ±7 days. Smoke: the CAMS daily PM2.5 already
in air-model.json at the nine loop points (Chiang Mai left out), the 75th percentile
by date (a bad year, not an average one), smoothed ±5 days. Crowds: an estimated
seasonal curve plus weekends and the dated events below — no visitor counts are
published for the loop. The event list is for YEAR_START onward and is rewritten
each year.

Rating = 10 × cube root of (clean × dry × quiet), each 0–1, so one bad factor sinks
a date rather than being averaged away.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump, jload  # noqa: E402

TOWNS = {"pai": (19.36, 98.44), "soppong": (19.47, 98.26), "mae-hong-son": (19.30, 97.97),
         "khun-yuam": (18.83, 97.93), "mae-sariang": (18.17, 97.93)}
RAIN_FROM, RAIN_TO = "1996-01-01", "2025-12-31"
WET_MM = 5.0
TRIP = 4
YEAR_START = dt.date(2026, 10, 1)

# smoke: model PM2.5 (bad-year) at which a date scores 1 and 0
PM_CLEAN, PM_BAD = 8.0, 28.0
# rain: share of wet days at which a date scores 0
WET_BAD = 0.5

# crowds, 0–1, by month — an estimate of the high-season shape (Pai and the viewpoints)
SEASON = {1: .75, 2: .5, 3: .3, 4: .25, 5: .12, 6: .1, 7: .12, 8: .12, 9: .1,
          10: .3, 11: .55, 12: .85}
# (first day, last day, added crowd, English, Thai)
EVENTS = [
    ("2026-10-01", "2026-10-07", .15, "China Golden Week", "โกลเด้นวีกจีน"),
    ("2026-10-10", "2026-10-13", .35, "13 Oct long weekend", "หยุดยาว 13 ต.ค."),
    ("2026-10-14", "2026-10-31", .10, "Thai school break", "ปิดเทอม"),
    ("2026-10-23", "2026-10-25", .35, "Chulalongkorn Day long weekend", "หยุดยาววันปิยมหาราช"),
    ("2026-10-25", "2026-10-27", .35, "Ok Phansa in Mae Hong Son", "ออกพรรษา แม่ฮ่องสอน"),
    ("2026-11-10", "2026-12-05", .10, "Bua Tong bloom, Khun Yuam", "ทุ่งบัวตองบาน ขุนยวม"),
    ("2026-11-23", "2026-11-25", .30, "Loy Krathong", "ลอยกระทง"),
    ("2026-12-05", "2026-12-07", .35, "5 Dec long weekend", "หยุดยาว 5 ธ.ค."),
    ("2026-12-10", "2026-12-13", .30, "Constitution Day", "วันรัฐธรรมนูญ"),
    ("2026-12-19", "2027-01-04", .40, "Christmas and New Year", "คริสต์มาสและปีใหม่"),
    ("2027-02-05", "2027-02-10", .20, "Chinese New Year", "ตรุษจีน"),
    ("2027-03-20", "2027-05-10", .10, "Thai school break", "ปิดเทอม"),
    ("2027-04-10", "2027-04-18", .40, "Songkran", "สงกรานต์"),
    ("2027-05-01", "2027-05-04", .25, "May long weekend", "หยุดยาวต้นพฤษภาคม"),
    ("2027-07-17", "2027-07-20", .25, "Asalha Bucha long weekend", "หยุดยาวอาสาฬหบูชา"),
    ("2027-07-28", "2027-07-28", .20, "King's Birthday", "วันเฉลิมพระชนมพรรษา"),
    ("2027-08-12", "2027-08-15", .25, "Mother's Day long weekend", "หยุดยาววันแม่"),
]

RAIN_FILE = HARVEST / "rain-model.json"
AIR_FILE = HARVEST / "air-model.json"
OUT = HARVEST / "when.json"
KEYS = [(dt.date(2027, 1, 1) + dt.timedelta(i)).strftime("%m-%d") for i in range(365)]


def fetch_rain():
    wet = {}
    for tid, (la, lo) in TOWNS.items():
        u = ("https://archive-api.open-meteo.com/v1/archive"
             f"?latitude={la}&longitude={lo}&start_date={RAIN_FROM}&end_date={RAIN_TO}"
             "&daily=precipitation_sum&timezone=Asia%2FBangkok")
        d = json.load(urllib.request.urlopen(u, timeout=180))["daily"]
        by = defaultdict(lambda: [0, 0])
        for day, p in zip(d["time"], d["precipitation_sum"]):
            if p is None or day[5:] == "02-29":
                continue
            by[day[5:]][0] += p >= WET_MM
            by[day[5:]][1] += 1
        wet[tid] = {k: [by[k][0], by[k][1]] for k in KEYS}
        print(f"rain: {tid} {len(d['time'])} days")
    jdump({"source": "Open-Meteo Historical Weather API (ERA5 reanalysis)",
           "url": "https://open-meteo.com/en/docs/historical-weather-api",
           "licence": "CC BY 4.0", "attribution": "Open-Meteo.com, ERA5 (Copernicus)",
           "fetched": dt.date.today().isoformat(), "start": RAIN_FROM, "end": RAIN_TO,
           "wet_mm": WET_MM,
           "note": "Per calendar date: [days with >= wet_mm, days counted]. A reanalysis "
                   "grid cell, not a rain gauge.",
           "towns": {k: {"lat": v[0], "lon": v[1]} for k, v in TOWNS.items()},
           "wet": wet}, RAIN_FILE, indent=0)


def smooth(raw: dict, w: int) -> dict:
    vals = [raw[k] for k in KEYS]
    n = len(vals)
    return {KEYS[i]: st.mean(vals[(i + j) % n] for j in range(-w, w + 1)) for i in range(n)}


def p75(v: list) -> float:
    v = sorted(v)
    return v[int(.75 * (len(v) - 1))]


def score():
    rain = jload(RAIN_FILE)
    air = jload(AIR_FILE)
    wet = smooth({k: sum(rain["wet"][t][k][0] for t in TOWNS) /
                  sum(rain["wet"][t][k][1] for t in TOWNS) for k in KEYS}, 7)
    pm = defaultdict(list)
    for p in air["points"]:
        if p["id"] == "chiang-mai":
            continue
        for day, v in p["daily"].items():
            if v is not None and day[5:] != "02-29":
                pm[day[5:]].append(v)
    pmd = smooth({k: p75(pm[k]) for k in KEYS}, 5)

    ev = {}
    for a, b, bump, en, th in EVENTS:
        d, e = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        while d <= e:
            if bump >= ev.get(d, (0,))[0]:
                ev[d] = (bump, en, th)
            d += dt.timedelta(1)

    def crowd(d):
        c = SEASON[d.month] + (.15 if d.weekday() == 5 else .1 if d.weekday() in (4, 6) else 0)
        b = ev.get(d)
        return min(1.0, c + (b[0] if b else 0)), b

    rows = []
    for i in range(365):
        s = YEAR_START + dt.timedelta(i)
        days = [s + dt.timedelta(j) for j in range(TRIP)]
        w = st.mean(wet[x.strftime("%m-%d")] for x in days)
        p = st.mean(pmd[x.strftime("%m-%d")] for x in days)
        cs = [crowd(x) for x in days]
        c = st.mean(x[0] for x in cs)
        seen, en, th = set(), [], []
        for _, b in cs:
            if b and b[1] not in seen:
                seen.add(b[1]); en.append(b[1]); th.append(b[2])
        g_s = max(0.0, min(1.0, (PM_BAD - p) / (PM_BAD - PM_CLEAN)))
        g_r = max(0.0, min(1.0, 1 - w / WET_BAD))
        g_c = 1 - c
        r = 10 * (max(g_s, .02) * max(g_r, .02) * max(g_c, .02)) ** (1 / 3)
        rows.append({"d": s.isoformat(), "r": round(r, 2), "wet": round(w * 100),
                     "pm": round(p, 1), "crowd": round(c * 100), "ev": en, "ev_th": th})

    picks = []
    for x in sorted(rows, key=lambda x: -x["r"]):
        if all(abs((dt.date.fromisoformat(x["d"]) - dt.date.fromisoformat(y["d"])).days) >= 21
               for y in picks):
            picks.append(x)
        if len(picks) == 3:
            break
    jdump({"generated": dt.date.today().isoformat(), "trip_days": TRIP,
           "year_start": YEAR_START.isoformat(),
           "method": {"rain": f"share of days >= {WET_MM} mm, {RAIN_FROM[:4]}–{RAIN_TO[:4]}, "
                              f"{len(TOWNS)} towns, ±7 days",
                      "smoke": f"CAMS PM2.5 75th percentile by date, {air['start']} to "
                               f"{air['end']}, 9 loop points, ±5 days; "
                               f"scores 1 at {PM_CLEAN}, 0 at {PM_BAD}",
                      "crowds": "estimated: seasonal curve + weekends + dated events",
                      "rating": "10 × cube root of (clean × dry × quiet)"},
           "sources": [rain["attribution"], air["attribution"]],
           "picks": [p["d"] for p in picks], "days": rows}, OUT, indent=0)
    for p in picks:
        print("pick", p["d"], p["r"], p["wet"], p["pm"], p["crowd"], p["ev"])


if __name__ == "__main__":
    if "--fetch" in sys.argv or not RAIN_FILE.exists():
        fetch_rain()
    score()
