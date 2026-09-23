"""The roster of NaNoBotCo sites, rendered for people, for machines and for robots.txt.

One copy of this file and of data/fleet.json lives in every repository that shows the
roster, so a clone of any single repository carries the whole list with it.

Canonical roster: https://nanobotco.github.io/index/fleet.json
Regenerate the copies with  tools/fleet_sync.py  in the index repository.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROSTER = Path(__file__).resolve().parent.parent / "data" / "fleet.json"


def load(path: Path | str | None = None) -> dict:
    return json.loads(Path(path or ROSTER).read_text(encoding="utf-8"))


def sites(self_id: str = "", lanes: tuple[str, ...] = ("directory", "meta"),
          roster: dict | None = None, ids: tuple[str, ...] | None = None) -> list[dict]:
    """The roster minus self: by lane, or by an explicit list of ids when a page
    wants only the siblings its own readers would use."""
    r = roster or load()
    if ids is not None:
        by = {s["id"]: s for s in r["sites"]}
        return [by[i] for i in ids if i in by and i != self_id]
    return [s for s in r["sites"] if s["id"] != self_id and s.get("lane") in lanes]


def row_html(self_id: str = "", label: str = "More from NaNoBotCo", cls: str = "fleet",
             roster: dict | None = None, ids: tuple[str, ...] | None = None) -> str:
    """A single footer line of sibling links."""
    out = []
    for s in sites(self_id, roster=roster, ids=ids):
        name = html.escape(s["name"])
        out.append(f'<a href="{html.escape(s["url"])}" title="{html.escape(s["note"])}">{name}</a>')
    return f'<div class="{cls}">{html.escape(label)}: ' + " · ".join(out) + "</div>"


def support_html(cls: str = "support", roster: dict | None = None, contact: bool = True,
                 self_id: str = "") -> str:
    """The contact and sponsor line Nan asked for on 2026-09-18 — same shape as
    the one that went on every README — and, from 2026-09-23, the source link:
    the site's own repository when the roster names one, else the account."""
    r = roster or load()
    links = " · ".join(
        f'<a href="{html.escape(s["url"])}" rel="noopener" target="_blank">{html.escape(s["name"])}</a>'
        for s in r["sites"] if s.get("lane") == "support")
    repo = next((s.get("repo") for s in r["sites"] if s["id"] == self_id and s.get("repo")), None) \
        or r.get("source") or "https://github.com/NaNoBotCo"
    src = f' · Source: <a href="{html.escape(repo)}" rel="noopener">GitHub</a>'
    if not contact:
        # defiant.to and offrampt.net obfuscate every address on purpose and
        # gate the build on it — a plaintext mailto here would undo that.
        return f'<div class="{cls}">Sponsor: {links}{src}</div>'
    return (f'<div class="{cls}">Contact: Nan · '
            f'<a href="mailto:{html.escape(r["contact"])}">{html.escape(r["contact"])}</a>'
            f' · Sponsor: {links}{src}</div>')


def maker(roster: dict | None = None) -> dict:
    """Who builds these. Carried on the roster so one edit reaches every site that
    installs it, rather than a line typed into eight footers."""
    r = roster or load()
    return r.get("maker") or {"name": "Hongdam", "url": "https://hongdam.net/",
                              "city": "Chiang Rai", "country": "TH"}


def maker_html(cls: str = "support maker", roster: dict | None = None, lang: str = "en") -> str:
    """The studio byline for a footer. Takes the `support` class so it inherits the
    footer's own type without a stylesheet change in every repo."""
    m = maker(roster)
    url, name, city = html.escape(m["url"]), html.escape(m["name"]), html.escape(m["city"])
    if lang == "th":
        th_name = html.escape(m.get("th") or m["name"])
        th_city = html.escape(m.get("city_th") or m["city"])
        return (f'<div class="{cls}">จัดทำโดย '
                f'<a href="{url}" rel="noopener">{th_name}</a> {th_city}</div>')
    return (f'<div class="{cls}">Made by '
            f'<a href="{url}" rel="noopener">{name}</a>, {city}.</div>')


def maker_line(roster: dict | None = None) -> str:
    m = maker(roster)
    return f"Made by {m['name']} ({m['url']}), a bilingual web studio in {m['city']}."


def maker_ld(roster: dict | None = None) -> dict:
    m = maker(roster)
    return {"@type": "Organization", "name": m["name"], "url": m["url"],
            "address": {"@type": "PostalAddress", "addressLocality": m["city"],
                        "addressCountry": m.get("country", "TH")}}


def llms_section(self_id: str = "", heading: str = "## Elsewhere from the same publisher", roster: dict | None = None) -> str:
    r = roster or load()
    lines = [heading, "", maker_line(r), ""]
    for s in sites(self_id, lanes=("directory", "meta", "product", "company"), roster=r):
        lines.append(f"- [{s['name']}]({s['url']}): {s['note']}")
    lines += ["", f"- [The roster as JSON]({r['canonical']})"]
    return "\n".join(lines)


def ai_txt_lines(self_id: str = "", roster: dict | None = None) -> str:
    r = roster or load()
    out = [f"Publisher: {r['publisher']} · {r['contact']}",
           f"Everything this publisher holds, counted: {r['index']}",
           f"Sibling corpora (roster as JSON): {r['canonical']}"]
    for s in sites(self_id, roster=r):
        out.append(f"  {s['name']}: {s['url']}")
    return "\n".join(out) + "\n"


def robots_lines(self_id: str = "", roster: dict | None = None) -> str:
    """Sibling sitemaps, declared so a crawler that reads one site finds the rest."""
    out = []
    for s in sites(self_id, lanes=("directory", "meta"), roster=roster):
        if s.get("sitemap"):
            out.append(f"Sitemap: {s['sitemap']}")
    return "\n".join(out) + "\n"


def same_as(self_id: str = "", roster: dict | None = None) -> list[str]:
    """URLs for a JSON-LD sameAs / isPartOf block."""
    return [s["url"] for s in sites(self_id, lanes=("directory", "meta", "product", "company"), roster=roster)]


def readme_lines(self_id: str = "", roster: dict | None = None) -> str:
    r = roster or load()
    rows = [f"[{s['name']}]({s['url']}) — {s['note']}" for s in sites(self_id, roster=r)]
    return ("## Elsewhere from the same publisher\n\n"
            + "\n".join(f"- {x}" for x in rows)
            + f"\n\nAll of it, counted: {r['index']} · roster as JSON: {r['canonical']}\n")


def txt_row(self_id: str = "", roster: dict | None = None) -> str:
    return " · ".join(f"{s['name']} {s['url']}" for s in sites(self_id, roster=roster))


if __name__ == "__main__":
    import sys
    me = sys.argv[1] if len(sys.argv) > 1 else ""
    print(row_html(me), "\n")
    print(llms_section(me), "\n")
    print(robots_lines(me))


# ------------------------------------------------------------------ schema.org

def publisher_ld(roster: dict | None = None) -> dict:
    r = roster or load()
    return {"@type": "Organization", "name": r["publisher"], "url": r["index"],
            "email": r["contact"], "sameAs": same_as(roster=r)}


def catalog_ld(roster: dict | None = None) -> dict:
    r = roster or load()
    return {"@type": "DataCatalog", "name": "The index", "url": r["index"],
            "description": "Every corpus, site and repository from this publisher, counted."}


# ------------------------------------------------------------------ built site

MARK = "# — roster of sibling sites, generated from data/fleet.json —"


def decorate(site_dir, self_id: str, roster: dict | None = None) -> list[str]:
    """Add the roster to a built site's machine files. Safe to run twice."""
    site = Path(site_dir)
    r = roster or load()
    touched = []

    (site / "fleet.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    touched.append("fleet.json")

    def append(name: str, text: str):
        p = site / name
        if not p.exists():
            return
        cur = p.read_text(encoding="utf-8")
        if MARK in cur:
            cur = cur.split(MARK)[0].rstrip() + "\n"
        p.write_text(cur.rstrip() + "\n\n" + MARK + "\n" + text.rstrip() + "\n", encoding="utf-8")
        touched.append(name)

    append("llms.txt", llms_section(self_id, roster=r))
    append("ai.txt", ai_txt_lines(self_id, roster=r))
    append("robots.txt", robots_lines(self_id, roster=r))
    append("humans.txt", f"/* STUDIO */\n{maker_line(r)}\n\n"
                         f"/* ELSEWHERE */\nEverything this publisher holds, counted: {r['index']}\n"
                         f"The roster, as JSON: {r['canonical']}\n"
                         + "\n".join(f"{s['name']} — {s['url']}" for s in sites(self_id, roster=r)))
    return touched
