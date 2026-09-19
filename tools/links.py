#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""links.py — resolve every internal reference in build/site and report the misses.

Written after motdang.net served /loop with a 200 instead of redirecting to /loop/,
which made the browser resolve "./images/x.jpg" against the site root. Every picture
on the front page 404ed and the build looked clean, because a relative path is only
wrong once you know where the page is mounted. So the check mounts the site the way
the host does, and follows the references from there — including from the page without
its trailing slash, which is the case that broke.

    python3 tools/links.py            # both mountings
    python3 tools/links.py --quiet    # exit code only
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD  # noqa: E402

SITE = BUILD / "site"
REF = re.compile(r'(?:href|src|data-src)\s*=\s*"([^"]+)"|url\(([^)]+)\)')
SKIP = ("http://", "https://", "//", "mailto:", "tel:", "data:", "javascript:", "#")
# script bodies build their hrefs by concatenation, so an attribute scanner reads
# half an expression and calls it a path. Those links are checked by their base,
# which is emitted into the page as a path like any other.
SCRIPT = re.compile(r"<script\b[^>]*>.*?</script>", re.S | re.I)


def served(path: str) -> bool:
    """Does the host have something to send for this absolute path?"""
    p = path.lstrip("/")
    f = SITE / p
    if f.is_file():
        return True
    if path.endswith("/") or f.is_dir():
        return (SITE / p / "index.html").is_file()
    return False


def check(base: str, slashless: bool) -> list:
    """Follow every reference in every page, as mounted at `base`.

    slashless asks the harder question: if the host serves the directory URL without
    its trailing slash — no redirect, straight 200 — does the page still find its
    own pictures? Only root-relative references survive that.
    """
    misses = []
    for f in sorted(SITE.rglob("*.html")):
        rel_dir = f.parent.relative_to(SITE).as_posix()
        url = base + ("" if rel_dir == "." else rel_dir + "/")
        if slashless and url.endswith("/") and len(url) > 1:
            url = url[:-1]      # the front page included: that is the URL people type
        text = SCRIPT.sub("", f.read_text(encoding="utf-8", errors="replace"))
        for m in REF.finditer(text):
            raw = (m.group(1) or m.group(2) or "").strip().strip("'\"")
            if not raw or raw.startswith(SKIP):
                continue
            target = urllib.parse.urljoin(url, raw).split("#")[0].split("?")[0]
            if not target.startswith(base):
                misses.append((f.relative_to(SITE).as_posix(), raw, target, "outside the mount"))
            elif not served("/" + target[len(base):]):
                misses.append((f.relative_to(SITE).as_posix(), raw, target, "404"))
    return misses


def main() -> int:
    quiet = "--quiet" in sys.argv
    stamp = SITE / ".basepath"
    if not stamp.is_file():
        print("no build/site/.basepath — run tools/site.py first")
        return 1
    base = stamp.read_text(encoding="utf-8").strip()
    bad = 0
    for slashless in (False, True):
        misses = check(base, slashless)
        label = f"{base} without trailing slashes" if slashless else base
        seen = {(a, b) for a, b, _, _ in misses}
        print(f"links: {len(misses):>5} misses, {len(seen):>4} distinct  — {label}")
        bad += len(misses)
        if misses and not quiet:
            for page, raw, target, why in misses[:12]:
                print(f"       {page} -> {raw}  ({why}: {target})")
            if len(misses) > 12:
                print(f"       ... and {len(misses) - 12} more")
    return 3 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
