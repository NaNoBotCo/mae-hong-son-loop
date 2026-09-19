#!/usr/bin/env python3
"""fetch_usda.py — the nine generic donut records USDA publishes, into a harvest file.

FoodData Central's SR Legacy set carries nine doughnut foods, split by dough: four
yeast-leavened, four cake-type, one french cruller. Values are per 100 grams, with a
portion table giving the gram weight of a piece — and the piece weights range from a
13-gram hole to a 157-gram jumbo, which is the point the /donut/ page is built on.

SR Legacy is a public-domain U.S. government dataset. This pulls the published CSV
bundle rather than the API, which needs a key.

    python3 tools/fetch_usda.py            # download, extract, write the harvest file
    python3 tools/fetch_usda.py --keep DIR # keep the unpacked CSVs in DIR
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, jdump  # noqa: E402

URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
UA = "pink-box-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
OUT = HARVEST / "usda-donuts.json"

# fdc_id -> the dough this project files it under. The dough call is USDA's own wording:
# "yeast-leavened", "cake-type", "french crullers" (choux).
FOODS = {
    "172758": "yeast", "175062": "yeast", "172757": "yeast", "172759": "yeast",
    "174990": "cake", "174991": "cake", "174992": "cake", "174993": "cake",
    "172756": "choux",
}
NUTRIENTS = {"1008": "kcal", "1004": "fat_g", "1258": "sat_fat_g", "1005": "carb_g",
             "2000": "sugar_g", "1093": "sodium_mg", "1003": "protein_g", "1079": "fiber_g"}


def main(keep: str | None = None) -> int:
    print(f"fetching {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        blob = r.read()
    z = zipfile.ZipFile(io.BytesIO(blob))
    root = z.namelist()[0].split("/")[0]
    if keep:
        z.extractall(keep)

    def rows(name):
        with z.open(f"{root}/{name}") as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))

    foods = {i: {"fdc_id": i, "dough": d, "per_100g": {}, "portions": []} for i, d in FOODS.items()}
    for r in rows("food.csv"):
        if r["fdc_id"] in foods:
            foods[r["fdc_id"]]["description"] = r["description"]
    for r in rows("food_nutrient.csv"):
        if r["fdc_id"] in foods and r["nutrient_id"] in NUTRIENTS:
            foods[r["fdc_id"]]["per_100g"][NUTRIENTS[r["nutrient_id"]]] = float(r["amount"])
    for r in rows("food_portion.csv"):
        if r["fdc_id"] in foods:
            desc = (r.get("portion_description") or r.get("modifier") or "").strip()
            if desc == "oz":
                continue                      # an ounce is not a piece
            foods[r["fdc_id"]]["portions"].append({"desc": desc, "g": float(r["gram_weight"])})
    for f in foods.values():
        f["portions"].sort(key=lambda p: p["g"])
    jdump({"source": "USDA FoodData Central, SR Legacy",
           "url": "https://fdc.nal.usda.gov/",
           "license": "Public domain (U.S. government work)",
           "release": "SR Legacy CSV bundle 2018-04; rows last updated 2019-04-01",
           "fetched_at": time.strftime("%Y-%m-%d"),
           "note": ("Nutrients are per 100 grams as published. A piece is not a fixed weight: the "
                    "portion table is USDA's own, and runs from a 13-gram hole to a 157-gram jumbo."),
           "foods": list(foods.values())}, OUT)
    print(f"wrote {OUT} — {len(foods)} foods")
    return 0


if __name__ == "__main__":
    keep = None
    if "--keep" in sys.argv:
        keep = sys.argv[sys.argv.index("--keep") + 1]
    raise SystemExit(main(keep))
