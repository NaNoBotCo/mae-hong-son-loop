#!/usr/bin/env python3
"""serve.py — serve build/site locally.  python3 tools/serve.py [port]   (default 8812)"""
from __future__ import annotations

import functools
import http.server
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BUILD  # noqa: E402

SITE = BUILD / "site"

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8812
    if not (SITE / "index.html").exists():
        print("no build/site yet — run tools/build.py then tools/site.py")
        sys.exit(1)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    print(f"serving {SITE} at http://127.0.0.1:{port}/  (Ctrl-C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
