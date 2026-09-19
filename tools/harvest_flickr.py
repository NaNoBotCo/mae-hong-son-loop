#!/usr/bin/env python3
"""harvest_flickr.py — free-to-use pictures from Flickr, licence read off each photo page.

Flickr's API needs a key this machine does not have, so this works from the public
pages. A photo page carries its own rights three times over — a numeric licence id in
the page's photo model, the words in the title attribute of the <a rel="license">, and
a licence URL in the JSON-LD ImageObject — and the picture bytes sit at a
live.staticflickr.com URL the same page prints, with every rendition's width beside it.
All three rights readings must agree before a byte is downloaded.

Four verbs:
  --search "wilbur's barbecue"   Flickr search, optionally --user <path alias or nsid>,
                                 into data/images/_triage/<query>.json (nothing downloaded)
  --walk <album|tag|photostream> the same, from an album URL or id, an account's
                                 /tags/<tag>/ page, or an account path alias
  --check <photo url or id>      read one photo page and print its rights, verbatim
  --harvest <record-id> ...      download the photos data/harvest/flickr-plan.json lists
                                 for each record into data/images/<id>/ with a .json
                                 sidecar each, and write images[] back into the record.
                                 Add --apply to write; without it, a dry run.

⚠ ON FLICKR THE RIGHTS ARE PER PHOTOGRAPH, NEVER PER ACCOUNT. The State Archives of
North Carolina stream holds "No known copyright restrictions" photographs and "All
rights reserved" photographs side by side, and the same negative appears both ways:
the 2008 upload of N.53.17 314 is all rights reserved, the 2017 re-upload of the same
image is Commons. Nothing here reads a licence from a collection, a neighbour or a
previous run; every download re-reads the photograph's own page first.

Accepted: No known copyright restrictions (Flickr Commons), Public Domain Mark, CC0,
United States Government Work, CC BY, CC BY-SA. Refused and named: all rights reserved,
and every NC or ND licence.

    python3 tools/harvest_flickr.py --search "barbecue" --user north-carolina-state-archives
    python3 tools/harvest_flickr.py --check 22130466182 --user north-carolina-state-archives
    python3 tools/harvest_flickr.py --harvest wilbers-barbecue --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
TRIAGE = IMAGES / "_triage"
PLAN = HARVEST / "flickr-plan.json"
DELAY = 1.5  # seconds between page fetches

# Flickr's licence ids, with the two things a photo page prints beside each: the words
# in the licence link's title attribute, and the URL that link points at. A page is
# believed only when its number, its words and its URL all say the same licence.
#
# `words` is a set because Flickr has printed several wordings for the same id over the
# years and still serves a mixture: id 4 appears as "CC BY 2.0" and as "Attribution
# License", id 10 as "Public Domain Work" and as "Public Domain Mark". A wording not on
# this list is refused, not guessed at — that refusal is how this list grew, and the URL
# leg is what makes widening it safe: a wording can drift, a deed URL names the licence.
LICENSES = {
    0:  ("All rights reserved", "", {"all rights reserved"}, "", False),
    1:  ("CC BY-NC-SA 2.0", "https://creativecommons.org/licenses/by-nc-sa/2.0/",
         {"cc by-nc-sa 2.0", "attribution-noncommercial-sharealike", "attribution-noncommercial-sharealike license"}, "licenses/by-nc-sa/2.0", False),
    2:  ("CC BY-NC 2.0", "https://creativecommons.org/licenses/by-nc/2.0/",
         {"cc by-nc 2.0", "attribution-noncommercial", "attribution-noncommercial license"}, "licenses/by-nc/2.0", False),
    3:  ("CC BY-NC-ND 2.0", "https://creativecommons.org/licenses/by-nc-nd/2.0/",
         {"cc by-nc-nd 2.0", "attribution-noncommercial-noderivs", "attribution-noncommercial-noderivs license"}, "licenses/by-nc-nd/2.0", False),
    4:  ("CC BY 2.0", "https://creativecommons.org/licenses/by/2.0/",
         {"cc by 2.0", "attribution", "attribution license"}, "licenses/by/2.0", True),
    5:  ("CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0/",
         {"cc by-sa 2.0", "attribution-sharealike", "attribution-sharealike license"}, "licenses/by-sa/2.0", True),
    6:  ("CC BY-ND 2.0", "https://creativecommons.org/licenses/by-nd/2.0/",
         {"cc by-nd 2.0", "attribution-noderivs", "attribution-noderivs license"}, "licenses/by-nd/2.0", False),
    7:  ("No known copyright restrictions", "https://www.flickr.com/commons/usage/",
         {"no known copyright restrictions"}, "flickr.com/commons/usage", True),
    8:  ("United States Government Work", "http://www.usa.gov/copyright.shtml",
         {"united states government work", "u.s. government work"}, "usa.gov/copyright", True),
    9:  ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/",
         {"cc0 1.0", "cc0", "public domain dedication", "no copyright"}, "publicdomain/zero/1.0", True),
    10: ("Public domain", "https://creativecommons.org/publicdomain/mark/1.0/",
         {"public domain mark", "public domain work", "public domain"}, "publicdomain/mark/1.0", True),
}
SIZE_ORDER = ["k", "h", "l", "b", "c", "z", "m", "n", "w", "s", "q", "sq", "t", "o"]


# ------------------------------------------------------------------ fetching
def get(url: str, referer: str = "https://www.flickr.com/", binary=False, tries=4):
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Referer": referer}
    if not binary:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            return data if binary else data.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise
            err = e
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(2 + 3 * i)
    raise RuntimeError(f"Flickr fetch failed: {url}: {err}")


# ------------------------------------------------------------------ parsing
def obj_at(h: str, i: int):
    """The brace-balanced JSON object whose opening '{' is at or before index i."""
    start = h.rfind("{", 0, i + 1)
    if start < 0:
        return None
    depth, in_s, esc = 0, False, False
    for j in range(start, len(h)):
        c = h[j]
        if in_s:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_s = False
            continue
        if c == '"':
            in_s = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return h[start:j + 1]
    return None


def models(html: str, registry: str):
    """Every JSON model of one _flickrModelRegistry kind, parsed."""
    out = []
    for m in re.finditer(r'"_flickrModelRegistry":"%s"' % re.escape(registry), html):
        s = obj_at(html, m.start())
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except ValueError:
            continue
    return out


def sizes_of(model: dict) -> dict:
    out = {}
    s = model.get("sizes") or {}
    # a photo page wraps the renditions one level deeper than a listing page does
    if isinstance(s.get("data"), dict):
        s = s["data"]
    for k, v in s.items():
        if isinstance(v, dict) and v.get("width"):
            url = v.get("url") or v.get("src") or v.get("displayUrl") or ""
            out[k] = {"width": v["width"], "height": v.get("height"), "url": ("https:" + url) if url.startswith("//") else url}
        elif isinstance(v, dict) and isinstance(v.get("data"), dict) and v["data"].get("width"):
            d = v["data"]
            url = d.get("url") or d.get("src") or d.get("displayUrl") or ""
            out[k] = {"width": d["width"], "height": d.get("height"), "url": ("https:" + url) if url.startswith("//") else url}
    return out


def biggest(sizes: dict, cap=2600):
    best = None
    for k in SIZE_ORDER:
        s = sizes.get(k)
        if not s or not s.get("url"):
            continue
        if s["width"] > cap:
            continue
        if best is None or s["width"] > best[1]["width"]:
            best = (k, s)
    return best


def rights_from_page(html: str) -> dict:
    """Read the photograph's rights three ways and make them agree.

    1. the numeric licence id in the page's photo model
    2. the words in the title attribute of the <a rel="license"> the page renders
    3. the licence URL — on that same anchor, and again in the JSON-LD ImageObject

    Returns {num, words, href, ld, label, license_url, free, agreed, why}. `agreed` is
    False when the three disagree, and a disagreement is a refusal, never a tie-break.
    """
    nums = sorted({int(m.group(1)) for m in re.finditer(r'"license":(\d+)[,}]', html)})
    anchors = re.findall(r'<a\s[^>]*rel="license[^"]*"[^>]*>', html)
    words, href = "", ""
    for a in anchors:
        t = re.search(r'title="([^"]*)"', a)
        u = re.search(r'href="([^"]*)"', a)
        if t:
            words = t.group(1).strip()
        if u:
            href = u.group(1).strip()
        if words:
            break
    ld = ""
    for m in re.finditer(r'"@type":\s*"ImageObject"', html):
        s = obj_at(html, m.start())
        if not s:
            continue
        try:
            ld = (json.loads(s).get("license") or "").strip()
        except ValueError:
            pass
        if ld:
            break
    num = nums[0] if len(nums) == 1 else (nums[-1] if nums else None)
    base = {"num": num, "words": words, "href": href, "ld": ld}
    if num is None or num not in LICENSES:
        return {**base, "label": "", "license_url": "", "free": False, "agreed": False,
                "why": f"no licence id on the page (found {nums})"}
    label, lurl, ok_words, frag, free = LICENSES[num]
    w = re.sub(r"\s+", " ", words).strip().lower()
    if w not in ok_words:
        return {**base, "label": label, "license_url": lurl, "free": False, "agreed": False,
                "why": f"licence id {num} is {label}, but the page prints {words!r}, which is not a "
                       f"wording this tool knows for it — look at the page before widening the list"}
    seen = (href + " " + ld).lower()
    if frag and frag not in seen:
        return {**base, "label": label, "license_url": lurl, "free": False, "agreed": False,
                "why": f"licence id {num} is {label}, but the page's licence link points at {href or ld!r}, "
                       f"which does not contain {frag!r}"}
    return {**base, "href": href or lurl, "label": label, "license_url": lurl,
            "free": free, "agreed": True, "why": ""}


PHOTOGRAPHER = re.compile(
    r"(?:photo(?:graph)?(?:ed)?\s+by|photographer[:\s]+|image by)\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})")


def parse_photo(html: str, page_url: str) -> dict:
    main = None
    for m in models(html, "photo-models"):
        if "sizes" in m and "title" in m:
            main = m
            break
    if main is None:
        raise RuntimeError(f"no photo model on {page_url}")
    owner = (main.get("owner") or {})
    owner = owner.get("data", owner) if isinstance(owner, dict) else {}
    holder = owner.get("realname") or owner.get("username") or ""
    desc = (main.get("description") or "").strip()
    dt = re.search(r'"dateTaken":"([^"]*)","datePosted":"(\d+)","isDateTakenUnknown":(true|false)', html)
    taken, posted, taken_unknown = ("", "", True)
    if dt:
        taken, posted, taken_unknown = dt.group(1), dt.group(2), dt.group(3) == "true"
    kw = re.search(r'<meta name="keywords" content="([^"]*)"', html)
    r = rights_from_page(html)
    sizes = sizes_of(main)
    pick = biggest(sizes)
    shot = PHOTOGRAPHER.search(desc)
    return {
        "id": str(main.get("id") or ""),
        "title": main.get("title") or "",
        "description": desc,
        "page_url": page_url,
        "holder": holder, "holder_short": owner.get("username") or "",
        "owner_nsid": owner.get("nsid") or "",
        "owner_path": owner.get("pathAlias") or "",
        "photographer": shot.group(1).strip(" .") if shot else "",
        "date_taken": "" if taken_unknown else taken,
        "date_taken_raw": taken,
        "date_taken_unknown": taken_unknown,
        "date_posted": time.strftime("%Y-%m-%d", time.gmtime(int(posted))) if posted else "",
        "keywords": kw.group(1) if kw else "",
        "license_num": r["num"], "license": r["label"], "license_url": r["license_url"],
        "rights_statement": r["words"], "rights_url": r["href"], "rights_ld": r["ld"],
        "free": r["free"] and r["agreed"], "agreed": r["agreed"], "why": r["why"],
        "url": (pick[1]["url"] if pick else ""), "size_key": (pick[0] if pick else ""),
        "width": (pick[1]["width"] if pick else 0), "height": (pick[1]["height"] if pick else 0),
        "sizes": {k: v["width"] for k, v in sizes.items()},
    }


def photo_url(ref: str, user: str = "") -> str:
    ref = ref.strip()
    if ref.startswith("http"):
        return ref.rstrip("/") + "/"
    if not user:
        raise SystemExit(f"--check/{ref}: a bare photo id needs --user <path alias or nsid>")
    return f"https://www.flickr.com/photos/{user}/{ref}/"


def read_photo(ref: str, user: str = "") -> dict:
    url = photo_url(ref, user)
    return parse_photo(get(url), url)


# ------------------------------------------------------------------ listing
def lite_rows(html: str) -> list[dict]:
    """Every result a listing page server-rendered, with id, title, description, licence
    and renditions. Search pages use photo-lite-models and album, tag and photostream
    pages use photo-models, so both are read. Good enough to triage from, never good
    enough to download from — --harvest re-reads each photograph's own page."""
    rows = []
    for m in models(html, "photo-lite-models") + [x for x in models(html, "photo-models") if "title" in x]:
        pid = str(m.get("id") or "")
        if not pid:
            continue
        num = m.get("license")
        label, lurl, _w, _u, free = LICENSES.get(num, ("?", "", set(), "", False))
        sizes = sizes_of(m)
        pick = biggest(sizes)
        owner = m.get("owner")
        owner = owner if isinstance(owner, dict) else {}
        owner = owner.get("data", owner) if isinstance(owner.get("data"), dict) else owner
        path = m.get("pathAlias") or owner.get("pathAlias") or ""
        rows.append({
            "id": pid, "title": m.get("title") or "", "description": (m.get("description") or "")[:400],
            "page_url": f"https://www.flickr.com/photos/{path}/{pid}/" if path else "",
            "holder": m.get("realname") or m.get("username") or owner.get("username") or owner.get("realname") or "",
            "license_num": num, "license": label, "license_url": lurl, "free": free,
            "width": (pick[1]["width"] if pick else 0), "height": (pick[1]["height"] if pick else 0),
        })
    return list({r["id"]: r for r in rows}.values())


def search(text: str, user: str = "", sort: str = "", license_ids: str = "") -> list[dict]:
    q = {"text": text}
    if user:
        q["user_id"] = user
    if sort:
        q["sort"] = sort
    if license_ids:
        q["license"] = license_ids
    url = "https://www.flickr.com/search/?" + urllib.parse.urlencode(q)
    return lite_rows(get(url))


def walk(target: str) -> list[dict]:
    """An album URL or bare album id, an account's /tags/<tag>/ page, or an account path
    alias (its photostream's first page)."""
    t = target.strip()
    if t.startswith("http"):
        url = t.rstrip("/") + "/"
    elif re.fullmatch(r"7\d{16,17}", t):
        raise SystemExit("a bare album id needs its account: pass the full album URL")
    else:
        url = f"https://www.flickr.com/photos/{t}/"
    rows = lite_rows(get(url))
    # album and photostream models carry no pathAlias, so a row from one has no page_url
    # until the account the walk was pointed at is put back in
    m = re.search(r"/photos/([^/]+)", url)
    for r in rows:
        if not r["page_url"] and m:
            r["page_url"] = f"https://www.flickr.com/photos/{m.group(1)}/{r['id']}/"
    return rows


def write_triage(name: str, rows: list[dict]):
    TRIAGE.mkdir(parents=True, exist_ok=True)
    p = TRIAGE / ("flickr-" + re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")[:70] + ".json")
    jdump({"query": name, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "count": len(rows), "note": "licences here are the listing page's claim; --harvest re-reads each photo page",
           "files": rows}, p)
    free = sum(1 for r in rows if r["free"])
    print(f"{name}: {len(rows)} photos, {free} free → {p}")
    for r in rows:
        print(f"  {'OK  ' if r['free'] else 'SKIP'} {r['license']:32.32} {r['width']}x{r['height']}  "
              f"{r['title'][:44]:44.44} {r['page_url']}")
        if r["description"]:
            print(f"       {r['description'][:150]}")


# ------------------------------------------------------------------ harvest
def holder_name(p: dict) -> str:
    """The institution as it should be credited. An account's realname often has the town
    appended — 'State Archives of North Carolina Raleigh, NC' — while its username does
    not, so the username is preferred and the realname is only the fallback."""
    for h in (p.get("holder_short"), p.get("holder")):
        h = (h or "").strip()
        if h:
            return h
    return ""


def author_line(p: dict, override: str = "") -> str:
    if override:
        return override
    bits = [b for b in (p.get("photographer"), holder_name(p)) if b]
    return "; ".join(dict.fromkeys(bits))


def harvest(ids: list[str], apply: bool):
    if not PLAN.exists():
        raise SystemExit(f"no plan: write {PLAN} first — {{'items':[{{'record':…,'photo':…,'alt':…}}]}}")
    plan = jload(PLAN).get("items", [])
    recs = {r["id"]: r for r in load_nodes()}
    want = [it for it in plan if not ids or it["record"] in ids]
    if not want:
        print("nothing in the plan for those records")
        return
    touched: dict[str, dict] = {}
    for it in want:
        rid = it["record"]
        r = recs.get(rid)
        if not r:
            print(f"{rid}: no such record")
            continue
        try:
            p = read_photo(it["photo"], it.get("user", ""))
        except Exception as e:  # noqa: BLE001
            print(f"  {rid}: CANNOT READ {it['photo']} — {e}")
            continue
        time.sleep(DELAY)
        if not p["agreed"]:
            print(f"  {rid}: REFUSED {p['page_url']} — rights unreadable: {p['why']}")
            continue
        if not p["free"]:
            print(f"  {rid}: REFUSED {p['page_url']} — the page says {p['rights_statement']!r} "
                  f"(Flickr licence {p['license_num']}). Not free to use; nothing downloaded.")
            continue
        base = re.sub(r"[^a-z0-9]+", "-", (it.get("slug") or p["title"]).lower()).strip("-")
        if len(base) > 52 or not base:
            base = (base[:44].rstrip("-") + "-" if base else "") + hashlib.sha1(p["id"].encode()).hexdigest()[:7]
        fname = f"{rid}/{rid}-{base}.jpg"
        dest = IMAGES / fname
        print(f"  {rid}: {'get' if apply else 'would get'} {p['title']!r} [{p['license']}] "
              f"{p['width']}x{p['height']} → {fname}")
        if not apply:
            continue
        data = get(p["url"], referer=p["page_url"], binary=True)
        if not data.startswith(b"\xff\xd8"):
            print(f"  {rid}: SKIP {p['page_url']} — the bytes at {p['url']} are not a JPEG")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        date = it.get("date") or p["date_taken"] or ""
        side = {
            "title": p["title"], "photo_id": p["id"], "page_url": p["page_url"], "original": p["url"],
            "author": author_line(p, it.get("author", "")), "credit": it.get("credit") or holder_name(p),
            "date": date, "date_posted_to_flickr": p["date_posted"],
            "description": p["description"], "width": p["width"], "height": p["height"],
            "license": p["license"], "license_url": p["license_url"],
            "rights_statement_on_page": p["rights_statement"], "flickr_license_id": p["license_num"],
            "sha256": sha, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": it.get("source") or (f"{holder_name(p)} via Flickr Commons" if p["license_num"] == 7
                                          else f"{holder_name(p)} via Flickr"),
        }
        jdump(side, dest.with_suffix(dest.suffix + ".json"))
        entry = {
            "file": fname, "source": "flickr", "title": p["title"], "url": p["url"], "page_url": p["page_url"],
            "license": p["license"], "license_url": p["license_url"], "author": author_line(p, it.get("author", "")),
            "credit": it.get("credit") or holder_name(p), "alt": it.get("alt") or p["description"][:300],
            "date": date, "primary": bool(it.get("primary")), "sha256": sha,
            "width": p["width"], "height": p["height"],
        }
        imgs = r.setdefault("images", [])
        for i, im in enumerate(imgs):
            if im.get("file") == fname or (im.get("page_url") and im["page_url"] == p["page_url"]):
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
    ap.add_argument("--search")
    ap.add_argument("--walk")
    ap.add_argument("--check")
    ap.add_argument("--user", default="", help="path alias or nsid, to scope a search or resolve a bare photo id")
    ap.add_argument("--sort", default="", help="relevance (default), date-posted-desc, date-taken-asc, interestingness-desc")
    ap.add_argument("--license", default="", help="Flickr licence ids to filter a search, e.g. 7 or 4,5,7,9,10")
    ap.add_argument("--harvest", nargs="*")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if a.search:
        write_triage(("user:" + a.user + " " if a.user else "") + a.search + (" sort:" + a.sort if a.sort else ""),
                     search(a.search, a.user, a.sort, a.license))
    elif a.walk:
        write_triage("walk " + a.walk, walk(a.walk))
    elif a.check:
        p = read_photo(a.check, a.user)
        print(f"{p['page_url']}\n  title       {p['title']}\n  holder      {p['holder']}"
              f"\n  photographer{' ' + p['photographer'] if p['photographer'] else ' —'}"
              f"\n  rights      {p['rights_statement']!r}  (Flickr licence id {p['license_num']})"
              f"\n  rights url  {p['rights_url']}\n  JSON-LD     {p['rights_ld']}"
              f"\n  agree       {p['agreed']}  {p['why']}\n  FREE TO USE {p['free']}"
              f"\n  date taken  {p['date_taken'] or '(the page marks the EXIF date unknown: ' + p['date_taken_raw'] + ')'}"
              f"\n  posted      {p['date_posted']}\n  picture     {p['width']}x{p['height']}  {p['url']}"
              f"\n  sizes       {p['sizes']}\n  description {p['description'][:500]}")
    elif a.harvest is not None:
        harvest(a.harvest, a.apply)
    else:
        ap.print_help()
