#!/usr/bin/env python3
"""harvest_archives.py — pictures from library and archive repositories, rights read per item.

The companion to harvest_commons.py and harvest_flickr.py, for the holders that are
neither: DigitalNC (Tind) and CONTENTdm sites such as the Greenville County Library
System's. DPLA itself is only an index and is not used here — it points at the holder,
and the holder's own item page is the only thing this tool will read a rights statement
from. The survey in data/harvest/picture-sources.json records why: DPLA's search payload
strips edmRights, so a rights value read from DPLA is not a rights value.

Two verbs:
  --check <plan key>         read one item's page and print its rights statement, verbatim
  --harvest <record-id> ...  download the items data/harvest/archives-plan.json lists for
                             each record into data/images/<id>/ with a .json sidecar each,
                             and write images[] back into the record. --apply to write.

Accepted: NoC-US, No Copyright - United States, No known copyright restrictions, Public
domain, Public Domain Mark, CC0, CC BY, CC BY-SA, United States Government Work. Anything
else is printed with the words the page actually used and skipped. A statement this tool
does not recognise is a refusal, never a guess.

⚠ lib.digitalnc.org SITS BEHIND AWS WAF. Plain requests get HTTP 202 with an empty body,
whatever the user agent. The way through is an aws-waf-token cookie from a browser that
has solved the challenge: open the record in a browser, read document.cookie, and pass
the token as --waf-token or in DIGITALNC_WAF_TOKEN. The token is short-lived, so a rerun
usually needs a fresh one; without it the tool says so and stops rather than half-working.
CONTENTdm needs nothing.

    DIGITALNC_WAF_TOKEN=... python3 tools/harvest_archives.py --check nc-barbecue-1898
    DIGITALNC_WAF_TOKEN=... python3 tools/harvest_archives.py --harvest --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import HARVEST, IMAGES, jdump, jload, load_nodes  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
PLAN = HARVEST / "archives-plan.json"
DELAY = 1.5

# A rights statement is accepted only when the words on the item's own page match one of
# these. The label on the right is what goes into images[].license, and every label here
# is on validate.py's free-to-use allowlist.
RIGHTS = [
    (re.compile(r"rightsstatements\.org/(?:vocab|page)/NoC-US/1\.0", re.I), "NoC-US",
     "http://rightsstatements.org/vocab/NoC-US/1.0/"),
    (re.compile(r"^\s*no copyright\s*[-–]\s*united states\s*$", re.I), "NoC-US",
     "http://rightsstatements.org/vocab/NoC-US/1.0/"),
    (re.compile(r"^\s*no known copyright restrictions\s*$", re.I), "No known copyright restrictions",
     "https://rightsstatements.org/page/NKC/1.0/"),
    (re.compile(r"^\s*public domain(\s*mark(\s*1\.0)?)?\.?\s*$", re.I), "Public domain",
     "https://creativecommons.org/publicdomain/mark/1.0/"),
    (re.compile(r"creativecommons\.org/publicdomain/mark/1\.0", re.I), "Public domain",
     "https://creativecommons.org/publicdomain/mark/1.0/"),
    (re.compile(r"creativecommons\.org/publicdomain/zero/1\.0", re.I), "CC0 1.0",
     "https://creativecommons.org/publicdomain/zero/1.0/"),
    (re.compile(r"creativecommons\.org/licenses/by/(\d\.\d)", re.I), "CC BY {}",
     "https://creativecommons.org/licenses/by/{}/"),
    (re.compile(r"creativecommons\.org/licenses/by-sa/(\d\.\d)", re.I), "CC BY-SA {}",
     "https://creativecommons.org/licenses/by-sa/{}/"),
    (re.compile(r"^\s*united states government work\s*$", re.I), "United States Government Work",
     "http://www.usa.gov/copyright.shtml"),
]


def read_rights(statement: str):
    """(label, url) for a free statement, or (None, None). The statement must be the words
    the holder printed, passed in whole — never a fragment this tool went looking for."""
    s = (statement or "").strip()
    for pat, label, url in RIGHTS:
        m = pat.search(s)
        if m:
            ver = m.group(1) if m.groups() else ""
            return label.format(ver), url.format(ver)
    return None, None


def get(url: str, waf: str = "", referer: str = "", binary=False, tries=3):
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    if waf and "digitalnc.org" in url:
        headers["Cookie"] = "aws-waf-token=" + waf
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                code, data = r.getcode(), r.read()
            if code == 202 or (not binary and len(data) < 4000 and b"awswaf" in data.lower()):
                raise RuntimeError("AWS WAF returned an empty 202 — pass a fresh --waf-token "
                                   "from a browser that has loaded the page")
            return data if binary else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(2 + 3 * i)
    raise RuntimeError(f"fetch failed: {url}: {err}")


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


# ------------------------------------------------------------------ the two holders
def digitalnc(item: dict, waf: str) -> dict:
    """A Tind record page. The rights sit in a labelled field, 'Standard Rights Statement'."""
    page = f"https://lib.digitalnc.org/record/{item['record_id']}"
    html = get(page, waf=waf)
    def field(label):
        """Tind renders each field as <div class="title">Label</div><div class="value">…</div>,
        and a value can hold nested divs, so the closing tag has to be counted, not guessed."""
        m = re.search(r'<div class="title">\s*' + re.escape(label) + r'\s*</div>\s*<div class="value">', html, re.I)
        if not m:
            return ""
        i, depth = m.end(), 1
        for t in re.finditer(r"<(/?)div\b[^>]*>", html[i:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                return strip_html(html[i:i + t.start()])
        return ""
    rights = field("Standard Rights Statement") or field("Rights")
    if not rights:
        m = re.search(r"(https?://rightsstatements\.org/vocab/[A-Za-z-]+/1\.0/)", html)
        rights = m.group(1) if m else ""
    fname = item.get("file") or ""
    if not fname:
        m = re.search(r"/record/%s/files/([^\"'?]+)" % item["record_id"], html)
        fname = m.group(1) if m else ""
    return {
        "page_url": page, "rights_statement": rights,
        "title": field("Title") or strip_html(re.search(r"<title>(.*?)</title>", html, re.S).group(1) if re.search(r"<title>(.*?)</title>", html, re.S) else ""),
        "description": field("Description"), "creator": field("Creator"),
        "date": field("Date (Text)") or field("Date"), "holder": field("Contributing Institution"),
        "collection": field("Digital Collection"), "credit_contact": field("Contact Information"),
        "image_url": (f"https://lib.digitalnc.org/nanna/api/multimedia/image/v2/"
                      f"recid:{item['record_id']}-{fname}/full/{item.get('width', 1600)},/0/default.jpg"),
    }


def contentdm(item: dict, waf: str = "") -> dict:
    """A CONTENTdm item. The public JSON API carries every metadata field, keyless."""
    base, alias, cid = item["base"].rstrip("/"), item["alias"], item["item_id"]
    d = json.loads(get(f"{base}/digital/api/collections/{alias}/items/{cid}/false"))
    f = {x.get("label", ""): (x.get("value") or "") for x in d.get("fields", [])}
    iiif = item.get("iiif") or f"{base}/iiif/2"
    return {
        "page_url": f"{base}/digital/collection/{alias}/id/{cid}",
        "rights_statement": f.get("Rights", ""), "title": f.get("Title") or d.get("title", ""),
        "description": f.get("Description", ""), "creator": f.get("Creator", "") or f.get("Photographer", ""),
        "date": f.get("Approximate Date") or f.get("Date", ""),
        "holder": f.get("Contributing Institution", ""), "collection": f.get("Digital Collection", ""),
        "credit_contact": f.get("Source", ""),
        "image_url": f"{iiif}/{alias}:{cid}/full/{item.get('width', 1600)},/0/default.jpg",
    }


READERS = {"digitalnc": digitalnc, "contentdm": contentdm}


def read_item(item: dict, waf: str) -> dict:
    info = READERS[item["holder_kind"]](item, waf)
    label, lurl = read_rights(info["rights_statement"])
    info.update({"license": label or "", "license_url": lurl or "", "free": bool(label)})
    return info


# ------------------------------------------------------------------ harvest
def harvest(ids: list[str], apply: bool, waf: str):
    if not PLAN.exists():
        raise SystemExit(f"no plan: write {PLAN} first")
    plan = jload(PLAN).get("items", [])
    recs = {r["id"]: r for r in load_nodes()}
    want = [it for it in plan if not ids or it["record"] in ids]
    touched: dict[str, dict] = {}
    for it in want:
        rid = it["record"]
        r = recs.get(rid)
        if not r:
            print(f"{rid}: no such record")
            continue
        try:
            info = read_item(it, waf)
        except Exception as e:  # noqa: BLE001
            print(f"  {rid}: CANNOT READ {it.get('key', it.get('record_id', it.get('item_id')))} — {e}")
            continue
        time.sleep(DELAY)
        if not info["free"]:
            print(f"  {rid}: REFUSED {info['page_url']} — the holder's rights field says "
                  f"{info['rights_statement']!r}, which is not a free-to-use statement. Nothing downloaded.")
            continue
        fname = f"{rid}/{rid}-{it['slug']}.jpg"
        dest = IMAGES / fname
        print(f"  {rid}: {'get' if apply else 'would get'} {info['title']!r} [{info['license']}] → {fname}")
        if not apply:
            continue
        data = get(info["image_url"], waf=waf, referer=info["page_url"], binary=True)
        if not data.startswith(b"\xff\xd8"):
            print(f"  {rid}: SKIP — the bytes at {info['image_url']} are not a JPEG")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        author = it.get("author") or info.get("creator") or info.get("holder") or ""
        credit = it.get("credit") or "; ".join(x for x in (info.get("collection"), info.get("holder")) if x)
        side = {
            "title": info["title"], "page_url": info["page_url"], "original": info["image_url"],
            "author": author, "credit": credit, "date": it.get("date") or info.get("date", ""),
            "description": info.get("description", ""),
            "license": info["license"], "license_url": info["license_url"],
            "rights_statement_on_page": info["rights_statement"],
            "holder": info.get("holder", ""), "collection": info.get("collection", ""),
            "contact": info.get("credit_contact", ""),
            "sha256": sha, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": it.get("source") or info.get("holder", ""),
        }
        jdump(side, dest.with_suffix(dest.suffix + ".json"))
        entry = {
            "file": fname, "source": "other", "title": info["title"], "url": info["image_url"],
            "page_url": info["page_url"], "license": info["license"], "license_url": info["license_url"],
            "author": author, "credit": credit, "alt": it["alt"],
            "date": it.get("date") or info.get("date", ""), "primary": bool(it.get("primary")), "sha256": sha,
        }
        imgs = r.setdefault("images", [])
        for i, im in enumerate(imgs):
            if im.get("file") == fname:
                imgs[i] = entry
                break
        else:
            if not imgs:
                entry["primary"] = True
            imgs.append(entry)
        touched[rid] = r
        time.sleep(DELAY)
    if apply:
        for rid, r in touched.items():
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            jdump(clean, Path(r["_path"]))
            print(f"  {rid}: record updated, {len(clean.get('images', []))} images")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check")
    ap.add_argument("--harvest", nargs="*")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--waf-token", default=os.environ.get("DIGITALNC_WAF_TOKEN", ""),
                    help="aws-waf-token cookie from a browser, for lib.digitalnc.org")
    a = ap.parse_args()
    if a.check:
        it = next((x for x in jload(PLAN)["items"] if x.get("key") == a.check), None)
        if not it:
            raise SystemExit(f"no plan item with key {a.check!r}")
        i = read_item(it, a.waf_token)
        print(f"{i['page_url']}\n  title       {i['title']}\n  creator     {i.get('creator') or '—'}"
              f"\n  holder      {i.get('holder')}\n  collection  {i.get('collection')}"
              f"\n  date        {i.get('date')}\n  rights      {i['rights_statement']!r}"
              f"\n  reads as    {i['license'] or '(not a statement this tool accepts)'}"
              f"\n  FREE TO USE {i['free']}\n  picture     {i['image_url']}"
              f"\n  description {i.get('description', '')[:400]}")
    elif a.harvest is not None:
        harvest(a.harvest, a.apply, a.waf_token)
    else:
        ap.print_help()
