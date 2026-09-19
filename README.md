# The Mae Hong Son Loop · วงรอบแม่ฮ่องสอน

**109 records · 115 sources · English and ไทย on every page ·
9,319 places from OpenStreetMap · 15,050 point-days of air data**

A directory and route guide for motorcycling the 600 km loop out of Chiang Mai through
Pai, Mae Hong Son and Mae Sariang. Static HTML, no framework, no web font, no third-party
request. Every claim carries a provenance tier and, where it is cited, the id of a named
source.

→ **https://motdang.net/loop/** · also at **https://nanobotco.github.io/mae-hong-son-loop/**

The same build is published twice. motdang.net/loop carries the canonical; the GitHub
Pages copy declares it as `rel="alternate"`, so the two are not competing duplicates.
`CANONICAL_URL=$SITE_URL ./publish.sh` makes whichever copy you are building the
primary one instead.

## Three things this site found by measuring rather than repeating

**1. The 1,864 on the sign holds up.**
Thai Wikipedia gives Chiang Mai to Mae Hong Son by Route 1095 as about **245 km**, which
puts 1,864 curves at **one every 131 metres**. Counting every change of turning direction
on the OpenStreetMap trace — one lean, one curve — gets to **1,310**
across the same distance, and **1,056 on Route 1095 alone**. That count is a
**floor**: the trace carries a point roughly every 31 metres, so a bend shorter than about
sixty metres leaves no mark in the data, and volunteer traces cut corners. An independent,
deliberately conservative method arrives within a third of the sign, from below. Nobody
publishes the survey behind 1,864 and this repo cannot confirm it to the digit — what it
can say is that the number is the right size.

*(An earlier version of this README claimed 395 over a 97 km span and read as a debunking.
It was wrong twice: the method collapsed a whole snaking sequence into a single arc, and
1,864 is carried for the full 245 km run, not that span. Both are fixed; `tools/curves.py`
carries the note.)*

**2. The famous road is not the densest.**
Route 1095 measures **5.71 curves per kilometre** over 184.9 km. Route 1263,
the Khun Yuam–Mae Chaem shortcut, measures **6.03**. Route
1096, the Samoeng day loop an hour from a Chiang Mai hotel, measures **6.34** —
the densest in the network, and nobody sells a shirt for it.

**3. Chiang Mai has worse air than the loop, and the rains are the cleanest time to ride.**
Four burning seasons of daily PM2.5 at ten points: Chiang Mai's March mean is 37.8 µg/m³
against Pai's 26.1. Pai swings from **3.0 in July to 29.8 in April**. Mae Hong Son
province, 12,765 km², has **one** government air monitor; Pai, Soppong, Khun Yuam and Mae
Sariang have none.

## What it will not tell you

- The curve counts measure an OpenStreetMap polyline — a volunteer trace of a road, not a
  survey of one — and they are reported as a floor, never a total.
- `/danger/` is a **demand map**, not a crash map: it says where a road asks the most of a
  rider. Nobody publishes crash locations for these roads and none are invented here.
- The air model never exceeded 99.4 µg/m³ daily mean in
  15,050 point-days. Ground stations have recorded far higher. Read the
  season from it, not the ceiling.
- Prices, opening hours and business details are absent unless a named source was checked.
  Where they were not, the page says "not on this disk" rather than guessing.

## Both directions, and the season picks

The loop runs clockwise or counter-clockwise and the site refuses to pick one for you.
Every leg carries prose for both, a toggle reverses the whole itinerary, and `?dir=ccw`
is in the URL so a direction is shareable. `/which-way/` argues it out season by season —
the low afternoon sun on the westward run into Mae Hong Son is the strongest single
argument and almost nobody raises it.

## Build it yourself

```
python3 tools/fetch_wiki.py        # the bilingual Wikipedia corpus
python3 tools/harvest_osm.py --all # road geometry and 9,000 places
python3 tools/harvest_air.py --all # CAMS via Open-Meteo, plus air4thai now
python3 tools/curves.py            # curve counts, thresholds, the demand map
python3 tools/validate.py          # schema, kin, sources, banned words
python3 tools/build.py             # records + harvests -> build/api
python3 tools/site.py              # build/api -> build/site
python3 tools/serve.py 8812
```

`./publish.sh` runs the lot and writes `docs/`, which is what GitHub Pages serves.

## Data

Everything the pages are built from is open JSON at `/api/`, fetchable directly:
`nodes.json`, `curves.json` (counts, thresholds, per-2 km demand windows), `air.json`,
`places.json`, `itinerary.json`, `coverage.json`. Also `nodes.csv` and `nodes.jsonl`.

## Provenance

Every record declares a tier, per field where the fields differ:

| tier | records | what it means |
|---|---|---|
| `cited` | 38 | a named source in sources.json backs this |
| `inference` | 21 | this project reasoning from the above, and saying so |
| `harvested` | 11 | a tool fetched it from an open dataset, with its licence |
| `tradition` | 4 | general knowledge of the practice, hedged in the prose |

17 records carry `needs_verification` and say so on the page.

## Licences

- Records, prose and measurements: **CC BY 4.0**
- Road geometry and harvested places: © OpenStreetMap contributors, **ODbL 1.0**
- Air: Open-Meteo / Copernicus CAMS **CC BY 4.0**; Thai Pollution Control Department (air4thai)
- Corpus: Wikipedia, **CC BY-SA 4.0**
- Code: **MIT**

## Elsewhere from the same publisher

- [Mot Dang](https://motdang.net/) — city directory for Chiang Mai and Chiang Rai
- [wichaa](https://wichaa.net/) — Lanna manuscripts, the amulet market, and the traditions around them
- [Amulet Atlas](https://nanobotco.github.io/amulet-atlas/) — amulets, charms and talismans worldwide
- [Carolina Barbecue](https://nanobotco.github.io/carolina-barbecue/) — barbecue in North and South Carolina
- [Wing Country](https://nanobotco.github.io/buffalo-wings/) — the American chicken wing
- [Pink Box](https://nanobotco.github.io/pink-box/) — the American mom-and-pop donut shop
- [Basque Tables](https://nanobotco.github.io/basque-tables/) — Basque dining rooms of California, Nevada and Idaho
- [Pinot Country](https://nanobotco.github.io/pinot-noir/) — pinot noir: the vine, the regions, the cellars
- [Care Abroad](https://nanobotco.github.io/care-abroad/) — treatment across borders, with published prices and their dates
- [Thai Roots](https://nanobotco.github.io/thairoots/) — a root dictionary of Thai, with a word decomposer
- [The index](https://nanobotco.github.io/index/) — every corpus, site and repository, counted
- [Uptake](https://nanobotco.github.io/uptake/) — a field manual on publishing for machines that copy
- [NaNoBotCo](https://nanobotco.github.io/) — the portal
- [ฮักฝรั่ง](https://hakfarang.net/) — เรื่องเงิน วีซ่า และชีวิตกับแฟนฝรั่ง
- [Offrampt](https://offrampt.net/) — turning crypto into spendable local money, Thailand first

All of it, counted: https://nanobotco.github.io/index/ · roster as JSON: https://nanobotco.github.io/index/fleet.json

