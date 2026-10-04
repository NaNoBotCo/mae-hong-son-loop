# -*- coding: utf-8 -*-
"""Routes into Chiang Mai (CNX), copied from motdang's flight board.

    python3 tools/cnx_flights.py      # reads mot-dang/data/flights.json

Writes data/harvest/cnx-flights.json: every route at CNX with its airlines, monthly
count, weekly counts, notes and the sources motdang names for them, plus the
Travelpayouts affiliate settings. The timetable rows stay on motdang's board.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path.home() / "Developer" / "claude code projects" / "mot-dang" / "data" / "flights.json"
OUT = ROOT / "data" / "harvest" / "cnx-flights.json"
KEEP = ("iata", "en", "th", "country_en", "country_th", "dom", "per_month", "per_week",
        "airlines", "src", "notes", "season", "start", "end", "status", "block_min")


def main():
    d = json.loads(SRC.read_text())
    routes = [{k: r[k] for k in KEEP if k in r} for r in d["routes"] if r["airport"] == "CNX"]
    used = {c for r in routes for c in r["airlines"]}
    ids = set()
    for r in d["routes"]:
        if r["airport"] != "CNX":
            continue
        for v in (r.get("src") or {}).values():
            for part in str(v).replace(";", ",").split(","):
                ids.add(part.strip().split(" ")[0])
    OUT.write_text(json.dumps({
        "from": "https://motdang.net/flights.html",
        "file": "mot-dang data/flights.json",
        "as_of": d["as_of"],
        "affiliate": d["affiliate"],
        "airport": d["airports"]["CNX"],
        "airlines": {k: v for k, v in d["airlines"].items() if k in used},
        "sources": [s for s in d["sources"] if s["id"] in ids],
        "routes": routes}, ensure_ascii=False, indent=1))
    print(f"{len(routes)} routes at CNX, as of {d['as_of']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
