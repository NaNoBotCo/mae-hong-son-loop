#!/usr/bin/env python3
"""fetch_wiki.py — the drafting corpus: Wikipedia articles as plain text, one per file.

Pulls the English article and, where it exists, the Thai one, so a bilingual record can
cite both. Each file carries its URL, its revision id and the fetch date at the top.
Wikipedia is CC BY-SA 4.0; the corpus is a working input, never published as-is.

    python3 tools/fetch_wiki.py                 # into data/corpus/
    python3 tools/fetch_wiki.py --out /tmp/x    # somewhere else
    python3 tools/fetch_wiki.py --list          # print the article list and stop
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, jdump, slugify  # noqa: E402

UA = "mhs-loop-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"

EN = """
Mae Hong Son province
Mae Hong Son
Pai, Mae Hong Son
Pai District
Pang Mapha District
Khun Yuam District
Mae Sariang District
Mae La Noi District
Sop Moei District
Mueang Mae Hong Son District
Mae Chaem District
Hot District
Chom Thong District
Mae Taeng District
Samoeng District
Mae Rim District
Chiang Mai
Chiang Mai province
Thai highway network
Doi Inthanon
Doi Pui
Salween River
Pai River
Ping River
Shan people
Shan State
Karen people
Kayan people (Myanmar)
Karenni people
Lahu people
Lisu people
Hmong people
Padaung
Tai peoples
Poy Sang Long
Loi Krathong
Wat Phra That Doi Kong Mu
Wat Chong Kham
Tham Lot
Mae Hong Son Airport
Pai Airport
Ban Rak Thai
Mae Surin Waterfall
Namtok Mae Surin National Park
Salawin National Park
Tham Pla–Namtok Pha Suea National Park
Op Luang National Park
Mexican sunflower
Tithonia diversifolia
Southeast Asian haze
Hairpin turn
Motorcycle safety
Motorcycle helmet
Honda Wave
Honda Click
Honda Super Cub
Kawasaki KLX
Honda CB500X
Royal Enfield Himalayan
Underbone
Scooter (motorcycle)
Dual-sport motorcycle
International Driving Permit
Driving licence in Thailand
Road signs in Thailand
Traffic collisions in Thailand
Thai baht
Thailand Post
Monsoon
Climate of Thailand
Teak
Thai highway 108
Mae Hong Son Loop
Burma Road
Thailand in World War II
Japanese occupation of Burma
""".strip().splitlines()

TH = """
จังหวัดแม่ฮ่องสอน
อำเภอปาย
อำเภอปางมะผ้า
อำเภอขุนยวม
อำเภอแม่สะเรียง
อำเภอแม่ลาน้อย
อำเภอสบเมย
อำเภอเมืองแม่ฮ่องสอน
อำเภอแม่แจ่ม
อำเภอฮอด
ทางหลวงแผ่นดินหมายเลข 108
ทางหลวงแผ่นดินหมายเลข 1095
ดอยอินทนนท์
แม่น้ำสาละวิน
ไทใหญ่
กะเหรี่ยง
ปอยส่างลอง
พระธาตุดอยกองมู
ถ้ำลอด
บ้านรักไทย
น้ำตกแม่สุรินทร์
""".strip().splitlines()


def fetch(title: str, lang: str) -> dict | None:
    api = f"https://{lang}.wikipedia.org/w/api.php"
    q = {"action": "query", "format": "json", "prop": "extracts|info", "explaintext": 1,
         "redirects": 1, "inprop": "url", "titles": title}
    req = urllib.request.Request(api + "?" + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
    except Exception as e:  # noqa: BLE001
        print(f"  ! {title}: {e}")
        return None
    for p in d.get("query", {}).get("pages", {}).values():
        if "missing" in p or not p.get("extract"):
            return None
        return {"title": p["title"], "url": p.get("fullurl", ""), "rev": p.get("lastrevid"),
                "lang": lang, "text": p["extract"]}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "corpus"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        print("\n".join(EN + TH))
        return 0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    index, missing = [], []
    for lang, titles in (("en", EN), ("th", TH)):
        for t in titles:
            t = t.strip()
            if not t:
                continue
            d = fetch(t, lang)
            if not d:
                missing.append(f"{lang}:{t}")
                print(f"  MISSING {lang}:{t}")
                continue
            slug = slugify(d["title"]) or re.sub(r"\W+", "-", d["title"])[:60]
            name = f"{'wp' if lang == 'en' else 'th'}-{slug}.txt"
            (out / name).write_text(
                f"# {d['title']}\n# {d['url']}\n# revision {d['rev']}\n# fetched {today}\n"
                f"# Wikipedia, CC BY-SA 4.0\n\n{d['text']}\n", encoding="utf-8")
            index.append({"id": f"s:{'wp' if lang == 'en' else 'thwp'}-{slug}", "kind": "web",
                          "title": d["title"], "publisher": f"Wikipedia ({lang})", "url": d["url"],
                          "accessed": today, "file": name, "words": len(d["text"].split())})
            print(f"  {name}  {len(d['text'].split())} words")
            time.sleep(0.4)
    jdump({"fetched": today, "licence": "CC BY-SA 4.0", "articles": index, "missing": missing},
          out / "_index.json")
    print(f"\n{len(index)} articles into {out}; {len(missing)} missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
