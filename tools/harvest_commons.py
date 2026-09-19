#!/usr/bin/env python3
"""harvest_commons.py — free-to-use pictures from Wikimedia Commons, licence attached.

Three verbs:
  --walk "Category:Doughnuts"        list a category's files with licence, author and size into
                             data/images/_triage/<category>.json (nothing downloaded)
  --search "skylight inn"    same, from a Commons full-text search of the File namespace
  --harvest <id> [<id>...]   download the files named in each record's x_commons_files
                             (or images[].title) at 1200px into data/images/<id>/ with a
                             .json sidecar each, and write the images[] entries back into
                             the record. Add --apply to write; without it, a dry run.

Only CC0, public domain, CC BY, CC BY-SA and FAL are accepted; anything else is listed
and skipped. Share-alike is complied with, not avoided: the licence and author ride with
the file and are printed beside it on every page.

    python3 tools/harvest_commons.py --walk "Category:Mae Hong Son Province"
    python3 tools/harvest_commons.py --search "Pai Thailand"
    python3 tools/harvest_commons.py --harvest pai --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, NODES, TYPES, jdump, jload, load_nodes  # noqa: E402

UA = "mhs-loop-build/0.1 (https://wichaa.net; nan@motdang.net) python-urllib"
API = "https://commons.wikimedia.org/w/api.php"
TRIAGE = IMAGES / "_triage"
FREE = re.compile(r"^(cc0|pd|public-domain|cc-by(-sa)?(-[1-4]\.[0-9])?|fal)", re.I)


def is_free(lic: str) -> bool:
    return bool(FREE.match((lic or "").strip().lower().replace(" ", "-")))
LICENSE_URL = {
    "cc0": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/", "cc-by-3.0": "https://creativecommons.org/licenses/by/3.0/",
    "cc-by-2.0": "https://creativecommons.org/licenses/by/2.0/", "cc-by-2.5": "https://creativecommons.org/licenses/by/2.5/",
    "cc-by-sa-4.0": "https://creativecommons.org/licenses/by-sa/4.0/", "cc-by-sa-3.0": "https://creativecommons.org/licenses/by-sa/3.0/",
    "cc-by-sa-2.0": "https://creativecommons.org/licenses/by-sa/2.0/", "cc-by-sa-2.5": "https://creativecommons.org/licenses/by-sa/2.5/",
    "pd": "https://en.wikipedia.org/wiki/Public_domain", "fal": "https://artlibre.org/licence/lal/en/",
}


def api(params: dict) -> dict:
    params = dict(params, format="json")
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API, data=data, headers={"User-Agent": UA})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            time.sleep(2 + 2 * i)
            err = e
    raise RuntimeError(f"Commons API failed: {err}")


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def imageinfo(titles: list[str]) -> list[dict]:
    """Licence, author, size and a 1200px rendition URL for each File: title (batches of 20)."""
    out = []
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        d = api({"action": "query", "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime|sha1", "iiurlwidth": 1200,
                 "titles": "|".join(batch)})
        for p in d.get("query", {}).get("pages", {}).values():
            ii = (p.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata") or {}
            lic = strip_html(em.get("LicenseShortName", {}).get("value", ""))
            out.append({
                "title": p.get("title"), "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(p.get('title', '').replace(' ', '_'))}",
                "url": ii.get("thumburl") or ii.get("url"), "original": ii.get("url"), "mime": ii.get("mime"),
                "width": ii.get("width"), "height": ii.get("height"), "sha1": ii.get("sha1"),
                "license": lic, "license_url": strip_html(em.get("LicenseUrl", {}).get("value", "")),
                "author": strip_html(em.get("Artist", {}).get("value", ""))[:200],
                "credit": strip_html(em.get("Credit", {}).get("value", ""))[:200],
                "date": strip_html(em.get("DateTimeOriginal", {}).get("value", ""))[:40],
                "description": strip_html(em.get("ImageDescription", {}).get("value", ""))[:400],
                "free": is_free(lic),
            })
        time.sleep(0.5)
    return out


def walk(category: str) -> list[dict]:
    files, cont = [], {}
    while True:
        d = api({"action": "query", "list": "categorymembers", "cmtitle": category, "cmnamespace": 6, "cmlimit": 500, **cont})
        files += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        cont = d.get("continue") or {}
        if not cont:
            break
        time.sleep(0.5)
    return imageinfo(files)


def search(text: str, limit=50) -> list[dict]:
    d = api({"action": "query", "list": "search", "srsearch": text, "srnamespace": 6, "srlimit": limit})
    return imageinfo([r["title"] for r in d.get("query", {}).get("search", [])])


def write_triage(name: str, rows: list[dict]):
    TRIAGE.mkdir(parents=True, exist_ok=True)
    p = TRIAGE / (re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") + ".json")
    jdump({"query": name, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(rows), "files": rows}, p)
    free = sum(1 for r in rows if r["free"])
    print(f"{name}: {len(rows)} files, {free} free → {p}")
    for r in rows:
        print(f"  {'✓' if r['free'] else '✗'} {r['license'] or '?':14} {r['width']}x{r['height']}  {r['title']}  — {r['description'][:70]}")


def norm_license(lic: str) -> tuple[str, str]:
    l = (lic or "").strip()
    key = l.lower().replace(" ", "-")
    if key in ("cc0", "cc0-1.0"):
        return "CC0 1.0", LICENSE_URL["cc0"]
    if key.startswith("public-domain") or key.startswith("pd"):
        return "Public domain", LICENSE_URL["pd"]
    m = re.match(r"cc-by(-sa)?-?([1-4]\.[0-9])?", key)
    if m:
        sa = m.group(1) or ""
        ver = m.group(2) or "4.0"
        label = f"CC BY{'-SA' if sa else ''} {ver}"
        return label, LICENSE_URL.get(f"cc-by{sa}-{ver}", "")
    if key.startswith("fal"):
        return "FAL 1.3", LICENSE_URL["fal"]
    return l, ""


def harvest(ids: list[str], apply: bool):
    recs = {r["id"]: r for r in load_nodes()}
    for rid in ids:
        r = recs.get(rid)
        if not r:
            print(f"{rid}: no such record")
            continue
        titles = list(r.get("x_commons_files") or [])
        titles += [im["title"] for im in r.get("images", []) if im.get("source") == "commons" and im.get("title") and not (IMAGES / im["file"]).exists()]
        titles = [t if t.startswith("File:") else "File:" + t for t in dict.fromkeys(titles)]
        if not titles:
            print(f"{rid}: nothing to harvest (add x_commons_files to the record)")
            continue
        info = imageinfo(titles)
        existing = {im.get("title") for im in r.get("images", [])}
        for fi in info:
            if not fi.get("url"):
                print(f"  {rid}: {fi['title']} — not found on Commons")
                continue
            if not fi["free"]:
                print(f"  {rid}: SKIP {fi['title']} — licence {fi['license']!r} not free-to-use")
                continue
            label, lurl = norm_license(fi["license"])
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(fi.get("mime"))
            # Commons renders TIFF originals as JPEG thumbnails, and the 1200px rendition
            # in fi["url"] is that JPEG — what we actually download. The Library of Congress
            # sets (Margolies, Highsmith, FSA/OWI) are uploaded as TIFF, so judging the file
            # by the original's mime would reject the whole roadside archive.
            if not ext and fi.get("mime") == "image/tiff" and (fi.get("url") or "").split("?")[0].lower().endswith((".jpg", ".jpeg")):
                ext = ".jpg"
            if not ext:
                print(f"  {rid}: SKIP {fi['title']} — {fi.get('mime')} is not a raster picture")
                continue
            base = re.sub(r"[^a-z0-9]+", "-", fi["title"][5:].rsplit(".", 1)[0].lower()).strip("-")
            if len(base) > 60:
                # Truncating at 60 collides: two Library of Congress files can differ only in
                # the last digits of their LCCN, and the second download would overwrite the
                # first while both records still claimed it. Keep a readable head, make the
                # tail unique and deterministic.
                base = base[:52].rstrip("-") + "-" + hashlib.sha1(fi["title"].encode()).hexdigest()[:7]
            fname = f"{rid}/{rid}-{base}{ext}"
            dest = IMAGES / fname
            print(f"  {rid}: {'get' if apply else 'would get'} {fi['title']} [{label}] → {fname}")
            if not apply:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(fi["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            dest.write_bytes(data)
            sha = hashlib.sha256(data).hexdigest()
            side = {k: fi.get(k) for k in ("title", "page_url", "original", "author", "credit", "date", "description", "width", "height")}
            side.update({"license": label, "license_url": lurl or fi.get("license_url", ""), "sha256": sha, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "Wikimedia Commons"})
            jdump(side, dest.with_suffix(dest.suffix + ".json"))
            if fi["title"] in existing:
                for im in r["images"]:
                    if im.get("title") == fi["title"]:
                        im.update({"file": fname, "license": label, "license_url": lurl or fi.get("license_url", ""), "author": fi["author"], "page_url": fi["page_url"], "url": fi["original"], "sha256": sha})
            else:
                r.setdefault("images", []).append({
                    "file": fname, "source": "commons", "title": fi["title"], "url": fi["original"], "page_url": fi["page_url"],
                    "license": label, "license_url": lurl or fi.get("license_url", ""), "author": fi["author"], "credit": fi["credit"],
                    "alt": (fi["description"] or fi["title"][5:])[:200], "date": fi["date"], "primary": not r.get("images"), "sha256": sha,
                })
            time.sleep(0.4)
        if apply:
            path = Path(r["_path"])
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            clean.pop("x_commons_files", None)
            jdump(clean, path)
            print(f"  {rid}: record updated, {len(clean.get('images', []))} images")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk")
    ap.add_argument("--search")
    ap.add_argument("--harvest", nargs="*")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.walk:
        write_triage(a.walk, walk(a.walk))
    elif a.search:
        write_triage("search " + a.search, search(a.search))
    elif a.harvest is not None:
        ids = a.harvest or [r["id"] for r in load_nodes() if r.get("x_commons_files")]
        harvest(ids, a.apply)
    else:
        ap.print_help()
