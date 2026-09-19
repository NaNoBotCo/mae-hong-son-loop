"""tests — run with:  python3 -m unittest discover -s tests -v

Covers: every record validates · build produces the API and the kin edges resolve ·
search answers golden queries within the top 3 (Python core, same tables the page
uses) · the site carries its bot-legibility files and no host paths.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

# (query, expected id in top 3) — plainly spelled and misspelled.
GOLDEN = [
    ("randys donuts", "randys-donuts"),
    ("ted ngoy", "ted-ngoy"),
    ("pink box", "pink-box"),
    ("old fashioned", "old-fashioned"),
    ("maple bar", "maple-bar"),
    ("kolache", "kolache"),
    ("egg roll", "egg-roll"),
    ("malasada", "malasada"),
    ("paczki", "paczki"),
    ("cider donut", "cider-donut"),
    ("doughnut plant", "doughnut-plant"),
    ("cafe du monde", "cafe-du-monde"),
    ("long john", "long-john"),
    ("beignet", "beignet"),
]


class Records(unittest.TestCase):
    def test_validate(self):
        r = subprocess.run([sys.executable, str(TOOLS / "validate.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_every_record_has_what_and_provenance(self):
        for p in (ROOT / "data" / "nodes").rglob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            self.assertTrue(d["text"].get("what"), f"{p.name}: no what")
            self.assertTrue(d["provenance"]["default"]["tier"], p.name)


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, str(TOOLS / "build.py")], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_api_files(self):
        api = ROOT / "build" / "api"
        for f in ("nodes.json", "index.json", "places.json", "kin.json", "coverage.json", "sources.json"):
            self.assertTrue((api / f).exists(), f)

    def test_kin_edges_resolve(self):
        api = ROOT / "build" / "api"
        ids = {n["id"] for n in json.loads((api / "index.json").read_text())["nodes"]}
        for e in json.loads((api / "kin.json").read_text())["edges"]:
            self.assertIn(e["to"], ids)
            self.assertIn(e["from"], ids)

    def test_places_table_is_consistent(self):
        t = json.loads((ROOT / "build" / "api" / "places.json").read_text())
        self.assertEqual(t["count"], len(t["places"]))
        self.assertEqual(t["curated"] + t["harvested"], t["count"])

    def test_hours_never_guess_a_closure(self):
        """A day nobody published must read 'unknown', never 'closed'. This is the rule the
        whole finder rests on, so it is a test and not a comment."""
        t = json.loads((ROOT / "build" / "api" / "places.json").read_text())
        for p in t["places"]:
            for day, state in (p.get("days") or {}).items():
                self.assertIn(state, ("open", "closed", "unknown"), f'{p["name"]} {day}')

    def test_every_tag_names_a_source(self):
        for p in (ROOT / "data" / "nodes" / "place").glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            for t in d.get("tags", []):
                self.assertTrue(t.get("source", "").startswith("s:"), f'{p.name}: {t["tag"]} has no source')
                self.assertNotIn(t.get("tier"), ("tradition", "inference"), f'{p.name}: {t["tag"]}')


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from common import search_core
        cls.sc, _ = search_core()
        docs = json.loads((ROOT / "build" / "searchdocs.json").read_text())["docs"]
        groups = json.loads((ROOT / "data" / "search" / "donuts.thesaurus.json").read_text())["groups"]
        cls.core = cls.sc.SearchCore(groups, [])
        cls.index = cls.sc.Index(cls.core)
        cls.prep = {}
        for d in docs:
            f = {"name": (d["names"], 3), "terms": (d["terms"], 2), "text": (d["text"], 1)}
            cls.index.add(d, f)
            cls.prep[d["id"]] = cls.core.prepare_doc(f)
        cls.index.finalize()

    def top(self, q, n=3):
        an = self.core.analyze(q, self.index)
        rows = []
        for i, p in self.prep.items():
            r = self.core.score_doc(an, p)
            if r:
                rows.append((i, r))
        whole = [x for x in rows if x[1]["coverage"] >= 1]
        rows = whole or rows
        rows.sort(key=lambda x: -x[1]["score"])
        return [i for i, _ in rows[:n]]

    def test_golden(self):
        for q, want in GOLDEN:
            self.assertIn(want, self.top(q), f"{q!r} → {self.top(q)}")


class Site(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = subprocess.run([sys.executable, str(TOOLS / "site.py")], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_bot_files(self):
        site = ROOT / "build" / "site"
        for f in ("index.html", "llms.txt", "llms-full.txt", "sitemap.xml", "robots.txt", "feed.xml", "opensearch.xml", "nodes.csv", "nodes.jsonl", "search/index.html", "search/tables.json", "places/index.html", "coverage/index.html"):
            self.assertTrue((site / f).exists(), f)
        self.assertIn("Content-Signal", (site / "robots.txt").read_text())

    def test_no_host_paths(self):
        site = ROOT / "build" / "site"
        for p in site.rglob("*"):
            if p.is_file() and p.suffix in (".html", ".json", ".txt", ".xml", ".csv", ".jsonl"):
                self.assertNotIn("/Users/", p.read_text(encoding="utf-8", errors="ignore"), str(p))

    def test_every_record_has_a_page(self):
        site = ROOT / "build" / "site"
        idx = json.loads((site / "api" / "index.json").read_text())
        for n in idx["nodes"]:
            self.assertTrue((site / n["url"] / "index.html").exists(), n["url"])


if __name__ == "__main__":
    unittest.main()
