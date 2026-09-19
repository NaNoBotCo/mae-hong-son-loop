#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serve.py — serve build/site locally, mounted where the host mounts it.

    python3 tools/serve.py [port]        # default 8812

The site is published under a path (/loop, /mae-hong-son-loop), so serving it at the
root made the local preview a different site from the live one — and hid the bug where
a host answers /loop with a 200 instead of a redirect and every relative path resolves
one directory too high. This mounts at build/site/.basepath and answers the slashless
URL directly, the unforgiving way, so the preview can only be kinder than production
if the pages are actually correct.
"""
from __future__ import annotations

import functools
import http.server
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD  # noqa: E402

SITE = BUILD / "site"


class Mounted(http.server.SimpleHTTPRequestHandler):
    base = "/"

    def translate_path(self, path):
        if self.base != "/" and path.startswith(self.base.rstrip("/")):
            path = "/" + path[len(self.base.rstrip("/")):].lstrip("/")
        return super().translate_path(path)

    def do_GET(self):
        if self.base != "/" and not self.path.startswith(self.base.rstrip("/")):
            self.send_response(302)
            self.send_header("Location", self.base)
            self.end_headers()
            return
        super().do_GET()

    def log_message(self, fmt, *a):
        code = a[1] if len(a) > 1 else ""
        if str(code).startswith(("4", "5")):
            sys.stderr.write(f"  {code}  {a[0]}\n")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8812
    if not (SITE / "index.html").exists():
        print("no build/site yet — run tools/build.py then tools/site.py")
        sys.exit(1)
    stamp = SITE / ".basepath"
    Mounted.base = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else "/"
    handler = functools.partial(Mounted, directory=str(SITE))
    print(f"serving {SITE} at http://127.0.0.1:{port}{Mounted.base}  (Ctrl-C to stop)")
    print("  only 4xx/5xx are logged")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
