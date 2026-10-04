# -*- coding: utf-8 -*-
"""Places to sleep near the loop's overnight towns, from Overture Maps Places.

OpenStreetMap holds 7 named beds at Soppong and 14 at Khun Yuam. Overture Places
(CDLA-Permissive 2.0, read from a public S3 bucket) is mostly Facebook business
pages, each with the page's own phone and website, so it is a second witness that
carries contact details OSM lacks. duckdb reads the remote parquet in place.

    python3 tools/harvest_stays.py                  # newest release
    python3 tools/harvest_stays.py --release 2026-08-19.0

Writes data/harvest/overture-stays.json. Needs duckdb; the site build does not.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "harvest" / "overture-stays.json"
BUCKET = "s3://overturemaps-us-west-2/release"

# the overnight towns and Doi Inthanon, with room around each
BBOX = (97.80, 18.05, 98.62, 19.62)
CATS = ("hotel", "accommodation", "bed_and_breakfast", "resort", "hostel", "lodge",
        "campground", "holiday_rental_home", "inn", "cabin", "service_apartments",
        "cottage", "guest_house", "motel", "homestay", "mountain_hut")


def latest_release(con):
    rows = con.execute(f"SELECT file FROM glob('{BUCKET}/*/theme=places/type=place/*.parquet')").fetchall()
    rel = sorted({f[0].split("/release/")[1].split("/")[0] for f in rows})
    return rel[-1] if rel else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release")
    a = ap.parse_args()
    try:
        import duckdb
    except ImportError:
        sys.exit("needs duckdb: python3 -m pip install duckdb")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; SET s3_region='us-west-2';")
    rel = a.release or latest_release(con)
    if not rel:
        sys.exit("no Overture release found; pass --release")
    x0, y0, x1, y1 = BBOX
    cats = ",".join(f"'{c}'" for c in CATS)
    rows = con.execute(f"""
        SELECT id, names.primary, names.common, taxonomy.primary, confidence,
               operating_status, phones[1], websites[1], socials, addresses[1].freeform,
               addresses[1].postcode, (bbox.xmin + bbox.xmax) / 2, (bbox.ymin + bbox.ymax) / 2
        FROM read_parquet('{BUCKET}/{rel}/theme=places/type=place/*', hive_partitioning=1)
        WHERE bbox.xmin BETWEEN {x0} AND {x1} AND bbox.ymin BETWEEN {y0} AND {y1}
          AND (taxonomy.primary IN ({cats}) OR list_contains(taxonomy.hierarchy, 'accommodation'))
    """).fetchall()
    out = []
    for (oid, name, common, cat, conf, status, phone, web, socials, addr, pc, lon, lat) in rows:
        if not name:
            continue
        common = dict(common or {})
        out.append({"id": oid, "name": name, "name_th": common.get("th"), "name_en": common.get("en"),
                    "cat": cat, "confidence": round(conf or 0, 3), "status": status,
                    "phone": phone, "website": web, "socials": list(socials or []),
                    "address": addr, "postcode": pc, "lat": round(lat, 6), "lon": round(lon, 6)})
    out.sort(key=lambda r: r["id"])
    OUT.write_text(json.dumps({
        "licence": "CDLA-Permissive-2.0",
        "licence_url": "https://cdla.dev/permissive-2-0/",
        "attribution": "© Overture Maps Foundation",
        "release": rel, "fetched": date.today().isoformat(),
        "source": f"{BUCKET}/{rel}/theme=places/type=place/",
        "bbox": list(BBOX), "categories": list(CATS), "count": len(out),
        "note": "Overture Places rows in lodging categories. Mostly Facebook business pages: "
                "the page's own name, phone and website, as of the release date.",
        "rows": out}, ensure_ascii=False, indent=1))
    print(f"overture {rel}: {len(out)} stays -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
