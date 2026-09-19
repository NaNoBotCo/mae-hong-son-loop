#!/usr/bin/env python3
"""pages.py — the pages that answer a question rather than describe a record.

  /near/    which shops are near me, what else they sell, and what is worth the drive
  /donut/   the nine donuts USDA has weighed, split by dough: sugar, fat, piece weight
  /dough/   cake against raised, drawn in cross-section
  /counter/ egg rolls, breakfast burritos, bacon egg and cheese, kolaches — who sells what
  /make/    a glaze, a dough, a filling
  /numbers/ distance to the nearest counter, founding years, days open
  /quiz/    which shop are you

Imported by site.py. Everything renders at build time; the only client-side work is
the reader's own geolocation and the sorting that follows it.

Chart colours are validated with the dataviz skill's checker (scripts/validate_palette.js)
against this site's own chart surfaces — #ffffff light, #251622 dark. The categorical
slots are the doughs, in DOUGH_COLOR: raised #d6136a, cake #1f78d1, choux #b35c00,
potato #0d8f63 (light) / #ea3d85 #2f8bd8 #c37a1c #12a97e (dark). Both modes pass the
lightness band, the chroma floor, adjacent-pair CVD separation, the normal-vision floor
and contrast. Identity never rests on colour alone: every row is labelled, every chart
has a table twin, and a dot carries its name in a title.
"""
from __future__ import annotations

import html
import json
import math
import re
import statistics

import usmap
import viz

def E(x) -> str:
    """html.escape, but a null field is a blank rather than a crash — a JSON field is
    null here when nobody published the thing, which is a state the site prints."""
    return html.escape("" if x is None else str(x))

# dough key -> (label, one-line gloss). Order runs raised, cake, choux, then the rest,
# which is the order the argument is usually had in.
DOUGHS = [
    ("yeast", "Raised", "lifted by baker's yeast, proofed twice, longest in the fat."),
    ("cake", "Cake", "lifted by baking powder or soda, dropped as batter, shortest in the fat."),
    ("choux", "Choux", "no yeast, no powder: steam does it. The French cruller."),
    ("potato", "Potato", "potato flour or riced potato in the dough — spudnuts, fasnachts."),
    ("other", "Other", "rice flour, tapioca, and whatever comes next."),
]
DOUGH_LABEL = {k: v for k, v, _ in DOUGHS}

# The categorical palette for the two doughs, validated with the dataviz skill's
# scripts/validate_palette.js against this site's own chart surfaces — #ffffff light,
# #251622 dark. Both modes pass the lightness band, the chroma floor, adjacent-pair CVD
# separation, the normal-vision floor and contrast. Re-run the validator before changing
# a colour or an order.
DOUGH_COLOR = {
    "yeast":  ("#d6136a", "#ea3d85"),
    "cake":   ("#1f78d1", "#2f8bd8"),
    "choux":  ("#b35c00", "#c37a1c"),
    "potato": ("#0d8f63", "#12a97e"),
    "other":  ("#6a6257", "#b2a998"),
}

CHART_CSS = """
.viz{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem;margin:1rem 0}
.viz h3{margin:.1rem 0 .2rem;font-size:1.06rem}.viz .note{font-size:.86rem;color:var(--mute);margin:.1rem 0 .7rem}
.viz svg{width:100%;height:auto;display:block;overflow:visible}
.viz .axis{font:500 11.5px -apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--mute)}
.viz .rowlab{font:600 13px -apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--ink)}
.viz .vallab{font:600 11.5px -apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--mute)}
.viz .grid{stroke:var(--line);stroke-width:1}
.viz .dot{fill:var(--c,var(--donut));stroke:var(--panel);stroke-width:2}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .viz .dot,:root:not([data-theme="light"]) .viz .mark{fill:var(--cd,var(--donut))}}
:root[data-theme="dark"] .viz .dot,:root[data-theme="dark"] .viz .mark{fill:var(--cd,var(--donut))}
.viz .mark{fill:var(--c,var(--donut))}.viz .span{fill:var(--c,var(--donut))}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]) .viz .span{fill:var(--cd,var(--donut))}}
:root[data-theme="dark"] .viz .span{fill:var(--cd,var(--donut))}
.viz .med{stroke:var(--ink);stroke-width:2;stroke-linecap:round}
.viz .seg{stroke:var(--panel);stroke-width:2}
.viz figcaption{font-size:.8rem;color:var(--mute);margin-top:.5rem}
.legend-row{display:flex;flex-wrap:wrap;gap:.45rem .9rem;margin:.5rem 0 .2rem;font-size:.84rem;font-family:-apple-system,"Segoe UI",Roboto,sans-serif}
.legend-row span{display:inline-flex;align-items:center;gap:.35rem;color:var(--ink)}
.legend-row i{width:.78rem;height:.78rem;border-radius:3px;display:inline-block}
details.tbl{margin:.6rem 0 0}details.tbl summary{cursor:pointer;font-size:.86rem;color:var(--mute);font-family:-apple-system,"Segoe UI",Roboto,sans-serif}
details.tbl table{font-size:.86rem;margin-top:.5rem}
.smallmult{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:.9rem;margin-top:.7rem}
.smallmult figure{margin:0;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:.5rem .55rem}
.smallmult figcaption{font-size:.84rem;color:var(--ink);font-weight:600;margin:0 0 .25rem;font-family:-apple-system,"Segoe UI",Roboto,sans-serif}
.smallmult figcaption small{display:block;font-weight:400;color:var(--mute);font-size:.76rem}
"""

NEAR_CSS = """
.finder{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem;margin:.8rem 0 1.2rem}
.finder .row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center}
.finder input[type=search]{flex:1;min-width:12rem;font:inherit;font-size:1.05rem;padding:.55rem .75rem;border:2px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:.4rem;margin:.7rem 0 0}
.chips button{font:inherit;font-size:.85rem;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;padding:.3rem .7rem;border-radius:999px;border:1.5px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.chips button[aria-pressed=true]{background:var(--donut);border-color:var(--donut);color:#fff}
.hit{display:grid;grid-template-columns:auto 1fr auto;gap:.2rem .8rem;align-items:baseline;padding:.55rem 0;border-bottom:1px solid var(--line)}
.hit .mi{font-variant-numeric:tabular-nums;font-weight:700;color:var(--donut);white-space:nowrap;font-family:-apple-system,"Segoe UI",Roboto,sans-serif}
.hit .nm{font-weight:600}.hit .wh{grid-column:2;font-size:.86rem;color:var(--mute)}
.hit .wk{grid-column:2;display:flex;align-items:center;gap:.55rem;margin-top:.3rem;font-size:.8rem;color:var(--mute)}
.hit .wk em{font-style:normal;color:var(--donut);font-weight:600}
.nohours{font-size:.8rem;color:var(--line)}
.daystrip{height:26px;width:176px;display:block;flex:0 0 auto}
.hit .tg{grid-column:2;font-size:.8rem;display:flex;flex-wrap:wrap;gap:.3rem;margin-top:.15rem}
.hit .go{font-size:.82rem;white-space:nowrap}
.drive{display:grid;grid-template-columns:repeat(auto-fill,minmax(16rem,1fr));gap:.9rem}
.drive .card b{display:block;font-size:1.05rem}
.drive .card .why{font-size:.84rem;color:var(--mute);margin-top:.25rem}
.stars{color:var(--gold);letter-spacing:.06em}
"""


def esc_js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


# ---------------------------------------------------------------- near me

def near_page(page, places: dict, recs: list, tagvocab: dict, site_url: str) -> str:
    rows = []
    for p in places["places"]:
        if p.get("lat") is None:
            continue
        rows.append({
            "n": p["name"], "u": p.get("url"), "la": round(p["lat"], 4), "lo": round(p["lon"], 4),
            "c": p.get("city") or "", "co": p.get("county") or "", "s": p.get("state") or "",
            "t": p.get("tags") or [], "a": p.get("recognitions") or 0, "rb": p.get("recognized_by") or [],
            "d": "".join((p.get("days") or {}).get(k, "unknown")[0] for k in ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")),
            "so": bool(p.get("sold_out")), "ht": p.get("hours_text") or "",
            "b": (p.get("blurb") or "")[:150], "w": p.get("website") or "", "h": p.get("hours") or "",
            "st": p.get("styles") or [], "sc": p.get("status") or "", "ch": bool(p.get("chain")),
        })
    towns: dict = {}
    for r in rows:
        if r["c"]:
            towns.setdefault(f"{r['c']}, {r['s']}", []).append((r["la"], r["lo"]))
    townpts = {k: [round(sum(x[0] for x in v) / len(v), 4), round(sum(x[1] for x in v) / len(v), 4)] for k, v in towns.items()}
    tags = [e for e in tagvocab.get("entries", []) if e["key"] in {t for r in rows for t in r["t"]}]
    drive = sorted([r for r in rows if r["a"] >= 1 and r["u"]], key=lambda r: (-r["a"], r["n"]))[:18]

    chips = ('<button type="button" data-tag="__sun" aria-pressed="false" title="A source says this one opens on Sunday">&#9788; Open Sunday</button>'
             '<button type="button" data-tag="__today" aria-pressed="false" title="Uses your own clock">&#128337; Open today</button>'
             '<button type="button" data-tag="__indie" aria-pressed="true" title="On by default. Drops every row carrying a company brand — two thirds of the harvest is one company.">&#127881; Independents only</button>'
             '<button type="button" data-tag="__counter" aria-pressed="false" title="Sells something besides donuts: egg rolls, burritos, sandwiches, kolaches, boba">&#129386; More than donuts</button>'
             + "".join(f'<button type="button" data-tag="{E(t["key"])}" aria-pressed="false">{E(t["icon"])} {E(t["label"])}</button>' for t in tags))
    drive_cards = "".join(
        f'<div class="card"><b><a href="../{E(r["u"])}index.html">{E(r["n"])}</a></b>'
        f'<span class="stars" aria-hidden="true">{"●" * min(r["a"], 5)}</span> '
        f'<span class="mute" style="font-size:.82rem">{r["a"]} {"recognition" if r["a"] == 1 else "recognitions"}</span>'
        f'<div class="why">{E(", ".join(r["rb"][:4]))}</div>'
        f'<div class="why">{E(r["c"])}{", " if r["c"] else ""}{E(r["s"])} — {E(r["b"][:110])}…</div></div>' for r in drive)

    counted = {e["key"]: sum(1 for r in rows if e["key"] in r["t"]) for e in tagvocab.get("entries", [])}
    empty = [e for e in tagvocab.get("entries", []) if counted.get(e["key"], 0) == 0]
    thin = [e for e in tagvocab.get("entries", []) if 0 < counted.get(e["key"], 0) <= 3]
    gaps = ""
    if empty:
        gaps += ("No place here carries " + ", ".join(f'<b>{E(e["label"].lower())}</b>' for e in empty)
                 + ". That says nothing about America&#8217;s donut counters — it says where the reading stopped. "
                 + "What would earn it: " + "; ".join(f'{E(e["label"].lower())} — {E(e["evidence"])}' for e in empty) + ". ")
    if thin:
        gaps += "Thin so far: " + ", ".join(f'{E(e["label"].lower())} ({counted[e["key"]]})' for e in thin) + ". "
    gaps += ('Every source read for this is listed on <a href="../story/free-to-use/index.html">where all of this came from</a>. '
             'A shop that wants a tag it has earned can say so on its own site or in a public directory, and it gets read there.')
    body = f"""
<h1><span class="kind">Pink Box</span>Donuts near me</h1>
<p class="lede">Who&#8217;s frying near you, what else is in their case, and who&#8217;s worth the drive. Chains are off unless you switch them on.</p>

<div class="finder">
  <div class="row">
    <button class="btn" id="locate" type="button">📍 Where I'm at</button>
    <input id="town" type="search" list="towns" placeholder="or type a town — Long Beach, Houston, Providence…" aria-label="Town">
    <datalist id="towns">{"".join(f'<option value="{E(t)}">' for t in sorted(townpts))}</datalist>
    <button class="btn ghost" id="go" type="button">Go</button>
  </div>
  <div class="chips" id="chips" role="group" aria-label="Filters">{chips}
    <button type="button" data-tag="__page" aria-pressed="false">📄 Written up here</button></div>
  <p class="mute" style="font-size:.84rem;margin:.6rem 0 0" id="status">Your browser works out where you are. The sorting happens in the page.</p>
</div>

<div id="out"></div>

<h2>Worth the drive</h2>
<p class="mute">Shops somebody already wrote up in print. The dots count how many did; they&#8217;re all named on the shop&#8217;s own page.</p>
<div class="drive">{drive_cards}</div>

<h2 id="gaps">Thin spots</h2>
<p class="mute">{gaps}</p>
<h2>Reading the tags</h2>
<table>{"".join(f'<tr><th>{E(t["icon"])} {E(t["label"])}</th><td>{E(t["evidence"])}</td></tr>' for t in tagvocab.get("entries", []))}</table>
<p class="mute">Each tag names where it came from. No tag means we haven't read that one yet.</p>

<script>
(function(){{
var ROWS={esc_js(rows)}, TOWNS={esc_js(townpts)};
var COUNTER=["egg-rolls","breakfast-burritos","bodega-sandwiches","kolaches","croissant-sandwiches","fried-rice","tamales","biscuits-and-gravy","boba","ice-cream"];
var TAGL={esc_js({e["key"]: (e["icon"] + " " + e["label"]) for e in tagvocab.get("entries", [])})};
var here=null, on={{__indie:true}};   /* the chains are off until a reader asks for them */
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
function miles(a,b,c,d){{var R=3958.8,p=Math.PI/180,x=(c-a)*p,y=(d-b)*p,
  h=Math.sin(x/2)*Math.sin(x/2)+Math.cos(a*p)*Math.cos(c*p)*Math.sin(y/2)*Math.sin(y/2);
  return 2*R*Math.asin(Math.sqrt(h))}}
var TODAY=(new Date().getDay()+6)%7;   /* JS counts Sunday 0; this week starts Monday */
function keep(r){{
  for(var k in on){{ if(!on[k]) continue;
    if(k==="__page"){{ if(!r.u) return false; }}
    else if(k==="__indie"){{ if(r.ch) return false; }}
    else if(k==="__counter"){{ if(!r.t.some(function(x){{return COUNTER.indexOf(x)>=0}})) return false; }}
    /* 'o' open, 'c' closed, 'u' nobody told us. A chip asks for OPEN, so 'u' drops out —
       a counter we have not read is not evidence of anything either way. */
    else if(k==="__sun"){{ if(r.d.charAt(6)!=="o") return false; }}
    else if(k==="__today"){{ if(r.d.charAt(TODAY)!=="o") return false; }}
    else if(r.t.indexOf(k)<0) return false; }}
  return true}}
var DAYL=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],DAY1=["M","T","W","T","F","S","S"];
function strip(d){{
  if(!d||d==="uuuuuuu")return '<span class="nohours">hours not published</span>';
  var w=176,c=(w-10)/7,o='<svg class="daystrip" viewBox="0 0 '+w+' 26" role="img" aria-label="'+
    d.split("").map(function(x,i){{return DAYL[i]+" "+({{o:"open",c:"closed",u:"not published"}}[x])}}).join(", ")+'">';
  for(var i=0;i<7;i++){{var x=i*c+(i===6?10:0),st=d.charAt(i);
    var fill=st==="o"?"var(--donut)":"none",stroke=st==="o"?"var(--donut)":st==="c"?"var(--mute)":"var(--line)";
    var dash=st==="u"?' stroke-dasharray="2.5 2.5"':'',col=st==="o"?"#fff":st==="c"?"var(--mute)":"var(--line)";
    o+='<rect x="'+(x+1.5).toFixed(1)+'" y="3" width="'+(c-3).toFixed(1)+'" height="18" rx="4" fill="'+fill+'" stroke="'+stroke+'" stroke-width="1.6"'+dash+'/>'+
       '<text x="'+(x+c/2).toFixed(1)+'" y="17" text-anchor="middle" fill="'+col+'" style="font:700 11px -apple-system,sans-serif">'+DAY1[i]+'</text>';}}
  return o+'</svg>';
}}
function render(){{
  var out=document.getElementById("out");
  if(!here){{out.innerHTML="";return}}
  var hits=ROWS.filter(keep).map(function(r){{var d=miles(here[0],here[1],r.la,r.lo);return {{r:r,d:d}}}})
    .sort(function(a,b){{return a.d-b.d}}).slice(0,25);
  if(!hits.length){{out.innerHTML='<p class="mute">Nothing doing. Drop a filter, or try the next town over.</p>';return}}
  out.innerHTML='<h2>Nearest first</h2>'+hits.map(function(h){{
    var r=h.r, tg=r.t.map(function(k){{return '<span class="chip">'+esc(TAGL[k]||k)+'</span>'}}).join("");
    var nm=r.u?('<a href="../'+esc(r.u)+'index.html">'+esc(r.n)+'</a>'):esc(r.n);
    var acc=r.a?(' <span class="stars" aria-hidden="true">'+"●".repeat(Math.min(r.a,5))+'</span>'):"";
    var where=[r.c,r.co?r.co+" County":"",r.s].filter(Boolean).join(" · ");
    var go=r.u?'<a class="go" href="../'+esc(r.u)+'index.html">page →</a>':(r.w?'<a class="go" href="'+esc(r.w)+'" rel="noopener">site →</a>':'<span class="go mute">not written up</span>');
    return '<div class="hit"><span class="mi">'+h.d.toFixed(1)+' mi</span><span class="nm">'+nm+acc+'</span>'+go+
      '<span class="wh">'+esc(where)+(r.b?' — '+esc(r.b.slice(0,110))+'…':'')+'</span>'+
      '<span class="wk">'+strip(r.d)+(r.so?' <em>till it runs out</em>':'')+(r.ht?' <em>'+esc(r.ht)+'</em>':(r.h?' <span class="mute">'+esc(r.h)+'</span>':''))+'</span>'+
      (tg?'<span class="tg">'+tg+'</span>':'')+'</div>';
  }}).join("");
}}
document.getElementById("chips").addEventListener("click",function(e){{
  var b=e.target.closest("button[data-tag]"); if(!b)return;
  var k=b.getAttribute("data-tag"); on[k]=!on[k]; b.setAttribute("aria-pressed",on[k]?"true":"false"); render();
}});
document.getElementById("locate").addEventListener("click",function(){{
  var s=document.getElementById("status");
  if(!navigator.geolocation){{s.textContent="This browser won't hand over a location. Type a town instead.";return}}
  s.textContent="Asking…";
  navigator.geolocation.getCurrentPosition(function(p){{
    here=[p.coords.latitude,p.coords.longitude];
    s.textContent="Sorted from where you are.";render();
  }},function(){{s.textContent="Browser said no. Type a town instead — works the same.";}},{{timeout:10000}});
}});
function bytown(){{
  var v=document.getElementById("town").value.trim(), s=document.getElementById("status");
  if(!v)return; var hit=TOWNS[v];
  if(!hit){{ var k=Object.keys(TOWNS).filter(function(t){{return t.toLowerCase().indexOf(v.toLowerCase())===0}});
    if(k.length){{hit=TOWNS[k[0]];v=k[0]}} }}
  if(!hit){{s.textContent="Nothing in this list is in a town by that name. Try the nearest big one.";return}}
  here=hit; s.textContent="Sorted from "+v+"."; render();
}}
document.getElementById("go").addEventListener("click",bytown);
document.getElementById("town").addEventListener("keydown",function(e){{if(e.key==="Enter"&&!e.isComposing){{e.preventDefault();bytown()}}}});
}})();
</script>
"""
    return page("Donuts near me — Pink Box", body, 1,
                "Donut shops near you, anywhere in the United States: cake or raised, open today, independents only, and the ones that also sell egg rolls, breakfast burritos, bacon egg and cheese or kolaches — every tag with its evidence.",
                [{"@context": "https://schema.org", "@type": "WebPage", "name": "Donuts near me", "url": f"{site_url}/near/"}],
                f"{site_url}/near/", extra_head=f"<style>{NEAR_CSS}</style>", card="near",
                og_alt="Every donut shop in America, sorted from where you are")


# ---------------------------------------------------------------- donut charts


def _ticks(hi: float, want=7) -> list:
    """Round numbers that fit the range: 1, 2, 2.5 or 5 times a power of ten. The old
    hard-coded list was right for grams of sugar and wrong by a factor of a hundred for
    milligrams of sodium."""
    if hi <= 0:
        return [0]
    raw = hi / want
    mag = 10 ** math.floor(math.log10(raw))
    step = next((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), 10 * mag)
    out, t = [], 0.0
    while t <= hi + 1e-9:
        out.append(round(t, 6))
        t += step
    return out


def _tick_label(t: float) -> str:
    return f"{t:,.0f}" if t >= 10 or t == int(t) else f"{t:g}"


def strip_plot(groups: list, unit: str, width=700, rowh=46) -> str:
    """One row per dough, one dot per measured donut, a median tick. Position carries the magnitude;
    one hue, because the rows are already labelled."""
    vals = [v for _, pts in groups for v, _ in pts]
    if not vals:
        return ""
    lo, hi = 0, max(vals) * 1.08
    left, right = 168, 24
    w = width
    h = len(groups) * rowh + 56
    px = lambda v: left + (v - lo) / (hi - lo) * (w - left - right)
    ticks = _ticks(hi)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="One dot per measured donut, grouped by dough">']
    for t in ticks:
        out.append(f'<line class="grid" x1="{px(t):.1f}" y1="14" x2="{px(t):.1f}" y2="{h - 40}"/>'
                   f'<text class="axis" x="{px(t):.1f}" y="{h - 24}" text-anchor="middle">{_tick_label(t)}</text>')
    out.append(f'<text class="axis" x="{left}" y="{h - 6}">{E(unit)}</text>')
    for i, (label, pts) in enumerate(groups):
        y = 32 + i * rowh
        out.append(f'<text class="rowlab" x="0" y="{y + 4}">{E(label)}</text>')
        if pts:
            med = statistics.median([v for v, _ in pts])
            out.append(f'<line class="med" x1="{px(med):.1f}" y1="{y - 13}" x2="{px(med):.1f}" y2="{y + 13}"><title>median {med:.1f}</title></line>')
            out.append(f'<text class="vallab" x="{px(med):.1f}" y="{y - 17}" text-anchor="middle">{med:,.4g}</text>')
        seen: dict = {}
        for v, name in sorted(pts):
            k = round(px(v) / 7)
            off = seen.get(k, 0)
            seen[k] = off + 1
            dy = (off % 3 - 1) * 7
            out.append(f'<circle class="dot" cx="{px(v):.1f}" cy="{y + dy}" r="5"><title>{E(name)} — {v:,.4g} {E(unit.split(",")[0])}</title></circle>')
    out.append("</svg>")
    return "".join(out)




def dot_strip(groups: list, unit: str, width=700, rowh=52) -> str:
    """One row per dough, one dot per measured donut, a median tick. Position carries the
    magnitude and the row label carries identity, so each row takes its dough's own colour
    and nothing depends on colour alone."""
    vals = [v for _, _, pts in groups for v, _ in pts]
    if not vals:
        return ""
    lo, hi = 0, max(vals) * 1.1
    left, right = 150, 26
    w = width
    h = len(groups) * rowh + 56
    px = lambda v: left + (v - lo) / (hi - lo) * (w - left - right)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{E(unit)}, one dot per measured donut, grouped by dough">']
    for t in _ticks(hi):
        out.append(f'<line class="grid" x1="{px(t):.1f}" y1="14" x2="{px(t):.1f}" y2="{h - 40}"/>'
                   f'<text class="axis" x="{px(t):.1f}" y="{h - 24}" text-anchor="middle">{_tick_label(t)}</text>')
    out.append(f'<text class="axis" x="{left}" y="{h - 6}">{E(unit)}</text>')
    for i, (key, label, pts) in enumerate(groups):
        y = 34 + i * rowh
        cl, cd = DOUGH_COLOR.get(key, DOUGH_COLOR["other"])
        out.append(f'<text class="rowlab" x="0" y="{y + 4}">{E(label)}</text>')
        if pts:
            med = statistics.median([v for v, _ in pts])
            out.append(f'<line class="med" x1="{px(med):.1f}" y1="{y - 14}" x2="{px(med):.1f}" y2="{y + 14}"><title>median {med:.4g}</title></line>')
            out.append(f'<text class="vallab" x="{px(med):.1f}" y="{y - 18}" text-anchor="middle">{med:,.4g}</text>')
        seen: dict = {}
        for v, name in sorted(pts):
            k = round(px(v) / 8)
            off = seen.get(k, 0)
            seen[k] = off + 1
            dy = (off % 3 - 1) * 8
            out.append(f'<circle class="dot dough-{E(key)}" cx="{px(v):.1f}" cy="{y + dy}" r="6" '
                       f'style="--c:{cl};--cd:{cd}"><title>{E(name)} — {v:,.4g}</title></circle>')
    out.append("</svg>")
    return "".join(out)


def piece_range(foods: list, width=700, rowh=34) -> str:
    """How much a piece weighs, as USDA's own portion table has it: the span from the
    smallest listed piece to the largest, per food. A range bar, not a dot, because the
    span is the finding."""
    rows = [f for f in foods if f.get("portions")]
    if not rows:
        return ""
    hi = max(p["g"] for f in rows for p in f["portions"]) * 1.06
    left, right = 250, 44
    w, h = width, len(rows) * rowh + 46
    px = lambda v: left + v / hi * (w - left - right)
    out = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Grams per piece, smallest to largest portion USDA lists for each doughnut food">']
    for t in _ticks(hi):
        out.append(f'<line class="grid" x1="{px(t):.1f}" y1="10" x2="{px(t):.1f}" y2="{h - 34}"/>'
                   f'<text class="axis" x="{px(t):.1f}" y="{h - 18}" text-anchor="middle">{_tick_label(t)}</text>')
    out.append(f'<text class="axis" x="{left}" y="{h - 2}">grams per piece</text>')
    for i, f in enumerate(rows):
        y = 26 + i * rowh
        cl, cd = DOUGH_COLOR.get(f["dough"], DOUGH_COLOR["other"])
        lo = min(p["g"] for p in f["portions"])
        hi_g = max(p["g"] for p in f["portions"])
        short = f["description"].replace("Doughnuts, ", "").replace(" (includes honey buns)", "")
        out.append(f'<text class="rowlab" x="0" y="{y + 4}" style="font-size:11.5px">{E(short[:40])}</text>')
        out.append(f'<rect class="span" x="{px(lo):.1f}" y="{y - 7}" width="{max(px(hi_g) - px(lo), 3):.1f}" height="14" rx="4" '
                   f'style="--c:{cl};--cd:{cd}" opacity=".28"/>')
        for p_ in f["portions"]:
            out.append(f'<circle class="mark" cx="{px(p_["g"]):.1f}" cy="{y}" r="5" stroke="var(--panel)" stroke-width="2" '
                       f'style="--c:{cl};--cd:{cd}"><title>{E(p_["desc"])} — {p_["g"]:g} g</title></circle>')
        lab = f"{lo:g}" if lo == hi_g else f"{lo:g}–{hi_g:g} g"
        out.append(f'<text class="vallab" x="{px(hi_g) + 8:.1f}" y="{y + 4}">{lab}</text>')
    out.append("</svg>")
    return "".join(out)


def donut_page(page, donuts: dict, recs: list, states_geo: dict, site_url: str, usda: dict | None = None) -> str:
    rows = list((donuts or {}).get("donuts", []))
    donut_recs = [r for r in recs if r["type"] == "donut"]
    body = ['<h1><span class="kind">Pink Box</span>Cake or raised, by the numbers</h1>',
            '<p class="lede">Nine donuts the United States government has weighed, split by what lifts them.</p>']
    if not rows:
        body.append('<p class="mute">Nothing measured yet. The donut pages are up though: '
                    + " · ".join(f'<a href="../donut/{E(r["id"])}/index.html">{E(r["names"]["name"])}</a>' for r in donut_recs) + "</p>")
        return page("Cake or raised — Pink Box", "".join(body), 1, "American donuts measured.", None, f"{site_url}/donut/",
                    extra_head=f"<style>{CHART_CSS}</style>", card="donut")

    withsugar = [x for x in rows if x.get("sugar_g") is not None]
    withfat = [x for x in rows if x.get("fat_g") is not None]
    nosugar = [x for x in rows if x.get("sugar_g") is None]
    body.append('<div class="facts">'
                + "".join(f'<div class="fact"><div class="n">{n}</div><div class="l">{E(l)}</div></div>' for n, l in
                          [(len(rows), "donuts measured"),
                           (sum(1 for x in rows if x.get("dough") == "yeast"), "raised"),
                           (sum(1 for x in rows if x.get("dough") == "cake"), "cake"),
                           (len(nosugar), "with no sugar figure published")])
                + "</div>")

    def grouped(src, field):
        g = []
        for key, label, _ in DOUGHS:
            pts = [(x[field], f'{x["name"]} — {x["serving_g"]:g} g') for x in src if x.get("dough") == key]
            if pts:
                g.append((key, label, pts))
        return g

    g_sug = grouped(withsugar, "sugar_g")
    if g_sug:
        allv = [v for _, _, pts in g_sug for v, _ in pts]
        top = max(withsugar, key=lambda x: x["sugar_g"])
        body.append('<div class="viz"><h3>Sugar in one donut</h3>'
                    f'<p class="note">One dot per food, {len(allv)} in all, each scaled from USDA\'s per-100-gram figures to the piece '
                    f'weight USDA itself lists. The upright tick is the row\'s median. {E(top["name"])} tops it at {top["sugar_g"]:g} g in a '
                    f'{top["serving_g"]:g}-gram piece — a tablespoon of table sugar is about 12.6 g. Hover a dot for the food and its weight.</p>'
                    + dot_strip(g_sug, "grams of sugar in one piece")
                    + '<details class="tbl"><summary>The same numbers as a table</summary><table><tr><th>Donut</th><th>Dough</th><th>Piece</th><th>Sugar</th></tr>'
                    + "".join(f'<tr><td>{E(x["name"])}</td><td>{E(DOUGH_LABEL.get(x.get("dough", ""), ""))}</td><td>{x["serving_g"]:g} g</td><td>{x["sugar_g"]:g} g</td></tr>'
                              for x in sorted(withsugar, key=lambda x: -x["sugar_g"]))
                    + "</table></details></div>")

    g_fat = grouped(withfat, "fat_g")
    if g_fat:
        body.append('<div class="viz"><h3>Fat in one donut</h3>'
                    '<p class="note">The same foods on the other axis. A raised ring sits in the fat about 150 seconds and a cake ring about 90, '
                    'and the raised one comes out carrying more of it — though the cake batter had shortening mixed in before it ever went near the kettle.</p>'
                    + dot_strip(g_fat, "grams of fat in one piece")
                    + '<details class="tbl"><summary>The same numbers as a table</summary><table><tr><th>Donut</th><th>Dough</th><th>Piece</th><th>Fat</th><th>Saturated</th><th>Calories</th></tr>'
                    + "".join(f'<tr><td>{E(x["name"])}</td><td>{E(DOUGH_LABEL.get(x.get("dough", ""), ""))}</td><td>{x["serving_g"]:g} g</td>'
                              f'<td>{x["fat_g"]:g} g</td><td>{x.get("sat_fat_g") or ""}</td><td>{x.get("kcal") or ""}</td></tr>'
                              for x in sorted(withfat, key=lambda x: -x["fat_g"]))
                    + "</table></details></div>")

    foods = (usda or {}).get("foods") or []
    if foods:
        biggest = max((p["g"] for f in foods for p in f["portions"]), default=0)
        smallest = min((p["g"] for f in foods for p in f["portions"]), default=0)
        body.append('<div class="viz"><h3>A piece is not a weight</h3>'
                    f'<p class="note">Every number above depends on what counts as one donut, and USDA\'s own portion table runs from '
                    f'{smallest:g} g to {biggest:g} g — a hole against a jumbo, the same food either way. Each dot is a portion USDA lists; '
                    'the bar spans them. This is the reason a donut\'s calorie count is an argument about size.</p>'
                    + piece_range(foods)
                    + '<figcaption>USDA FoodData Central, SR Legacy. Public domain.</figcaption></div>')

    body.append('<h2>What happens in the kettle</h2>'
                '<p class="mute">The published accounts do not agree on how much fat each dough takes up, so both are here.</p>'
                '<div style="overflow-x:auto"><table>'
                '<tr><th>&nbsp;</th><th>Raised</th><th>Cake</th></tr>'
                '<tr><th>What lifts it</th><td>baker\'s yeast, proofed twice</td><td>baking powder or soda</td></tr>'
                '<tr><th>Flour</th><td>stronger dough</td><td>cake flour, about 7–8% protein</td></tr>'
                '<tr><th>Time in the fat</th><td>about 150 seconds</td><td>about 90 seconds, turning once — '
                'or 30 to 45 seconds commercially, by another account</td></tr>'
                '<tr><th>Fat temperature</th><td>182–190 °C (360–374 °F)</td><td>190–198 °C (374–388 °F); 191 °C by the other account</td></tr>'
                '<tr><th>Oil it carries</th><td>about 25% by weight — or 25 to 35%, depending on the account</td>'
                '<td>about 20% — or 20 to 25% — plus shortening mixed into the batter beforehand</td></tr>'
                '<tr><th>Weight of a ring</th><td>averages 38 g</td><td>24 to 28 g</td></tr>'
                '</table></div>'
                '<p class="mute">Neither account names a laboratory. They agree on the direction and differ on the size of the gap. '
                'Both are cited on <a href="../story/cake-against-raised/index.html">cake against raised</a>.</p>')

    body.append('<h2>Every donut measured</h2><p class="mute">Grams per piece, at the portion weight in the third column. '
                'A blank means USDA publishes no figure for it.</p>'
                '<div style="overflow-x:auto"><table><tr><th>Donut</th><th>Dough</th><th>Piece</th><th>Calories</th><th>Sugar</th>'
                '<th>Fat</th><th>Saturated</th><th>Carbs</th><th>Sodium</th><th>Source</th></tr>'
                + "".join("<tr><td>" + E(x["name"]) + "</td><td>" + E(DOUGH_LABEL.get(x.get("dough", ""), "")) + "</td>"
                          + f'<td>{x["serving_g"]:g} g</td>'
                          + "".join("<td>" + ("" if x.get(k) is None else f"{x[k]:g}{u}") + "</td>"
                                    for k, u in (("kcal", ""), ("sugar_g", " g"), ("fat_g", " g"), ("sat_fat_g", " g"), ("carb_g", " g"), ("sodium_mg", " mg")))
                          + "<td>" + (f'<a href="{E(x["source_url"])}" rel="noopener">USDA</a>' if x.get("source_url") else "") + "</td></tr>"
                          for x in sorted(rows, key=lambda x: (x.get("dough") or "", x["name"])))
                + "</table></div>")

    body.append('<h2>The donuts</h2><div class="cards">' + "".join(
        f'<div class="card"><a class="t" href="../donut/{E(r["id"])}/index.html">{E(r["names"]["name"])}</a>'
        f'<p>{E(r["blurb"][:160])}</p></div>' for r in donut_recs) + "</div>")
    body.append('<p class="legend">Numbers come from USDA FoodData Central\'s SR Legacy set, which publishes nine generic doughnut foods '
                'per 100 grams with its own portion weights; they are public domain and each row links to the food it came from. '
                'These are not any particular shop\'s donuts — almost no independent shop publishes a weight, let alone a panel. '
                'The data is at <a href="../api/donuts.json">api/donuts.json</a>.</p>')
    return page("Cake or raised, by the numbers — Pink Box", "".join(body), 1,
                "American donuts measured: sugar and fat in one piece, split by cake and raised dough, with USDA's own portion weights and the frying numbers behind them.",
                [{"@context": "https://schema.org", "@type": "Dataset", "name": "American donuts, measured", "url": f"{site_url}/donut/",
                  "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": f"{site_url}/api/donuts.json"}]}],
                f"{site_url}/donut/", extra_head=f"<style>{CHART_CSS}</style>", card="donut",
                og_alt="Sugar and fat in an American donut, cake against raised")


# ---------------------------------------------------------------- the quiz

def quiz_page(page, quiz: dict, by_id: dict, site_url: str) -> str:
    qs = quiz["questions"]
    res = quiz["results"]
    forms = []
    for i, q in enumerate(qs):
        opts = "".join(
            f'<label class="opt"><input type="radio" name="q{i}" value="{i}-{j}"> {E(a["t"])}</label>' for j, a in enumerate(q["a"]))
        forms.append(f'<fieldset class="qz"><legend>{i + 1}. {E(q["q"])}</legend>{opts}</fieldset>')
    scoring = [[a["s"] for a in q["a"]] for q in qs]
    results = {k: {"title": v["title"], "say": v["say"], "url": f"../style/{k}/index.html"} for k, v in res.items() if k in by_id}
    body = f"""
<h1><span class="kind">Pink Box</span>{E(quiz["title"])}</h1>
<p class="lede">{E(quiz["lede"])}</p>
<form id="qz">{"".join(forms)}
<div class="cta"><button class="btn" id="tally" type="button">Tally it up</button><button class="btn ghost" id="again" type="button">Start over</button></div></form>
<div id="verdict" aria-live="polite"></div>
<p class="legend">The scoring runs in your browser. Each result links to a style page, where the sources sit.</p>
<style>
.qz{{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:.8rem 1rem;margin:.9rem 0}}
.qz legend{{font-weight:600;padding:0 .4rem}}
.opt{{display:block;padding:.35rem .2rem;cursor:pointer}}
.opt input{{margin-right:.55rem}}
.verdict{{background:var(--panel);border:2px solid var(--donut);border-radius:14px;padding:1rem 1.2rem;margin:1rem 0}}
.verdict h2{{margin:.1rem 0 .3rem;border:0}}
.bars{{margin-top:.7rem}}
.bars div{{display:grid;grid-template-columns:11rem 1fr auto;gap:.6rem;align-items:center;margin:.25rem 0;font-size:.9rem}}
.bars i{{display:block;height:.7rem;border-radius:4px;background:var(--donut)}}
</style>
<script>
(function(){{
var S={esc_js(scoring)}, R={esc_js(results)};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
document.getElementById("tally").addEventListener("click",function(){{
  var sc={{}}, answered=0;
  S.forEach(function(q,i){{
    var el=document.querySelector('input[name="q'+i+'"]:checked'); if(!el)return; answered++;
    var j=parseInt(el.value.split("-")[1],10), s=q[j];
    for(var k in s) sc[k]=(sc[k]||0)+s[k];
  }});
  var v=document.getElementById("verdict");
  if(!answered){{v.innerHTML='<p class="mute">Answer at least one.</p>';return}}
  var rank=Object.keys(sc).sort(function(a,b){{return sc[b]-sc[a]}});
  var top=rank[0], max=sc[top], r=R[top]||{{title:top,say:"",url:"#"}};
  var bars=rank.map(function(k){{var w=Math.round(sc[k]/max*100);
    return '<div><span>'+esc((R[k]||{{}}).title||k)+'</span><i style="width:'+w+'%"></i><span>'+sc[k]+'</span></div>'}}).join("");
  v.innerHTML='<div class="verdict"><h2>'+esc(r.title)+'</h2><p>'+esc(r.say)+'</p>'+
    '<p><a class="btn" href="'+esc(r.url)+'">Read the style →</a></p><div class="bars">'+bars+'</div></div>';
  v.scrollIntoView({{behavior:"smooth",block:"nearest"}});
}});
document.getElementById("again").addEventListener("click",function(){{
  document.getElementById("qz").reset(); document.getElementById("verdict").innerHTML="";
}});
}})();
</script>
"""
    return page(f'{quiz["title"]} — Pink Box', body, 1, quiz["lede"], None, f"{site_url}/quiz/", card="quiz",
                og_alt="Which donut shop are you? Six questions and a counter at the end")


# ------------------------------------------------------------ the other menu

# The counter tags, in the order the page reads them: the three the brief named first,
# then the rest of what turns up in a case.
COUNTER_ORDER = [
    ("egg-rolls", "Egg rolls"), ("breakfast-burritos", "Breakfast burritos"),
    ("bodega-sandwiches", "Deli or bodega sandwiches"), ("kolaches", "Kolaches and klobasniky"),
    ("croissant-sandwiches", "Croissant sandwiches"), ("fried-rice", "Fried rice or chow mein"),
    ("boba", "Boba"), ("tamales", "Tamales"), ("biscuits-and-gravy", "Biscuits and gravy"),
    ("ice-cream", "Ice cream"),
]


def counter_multiples(states_geo: dict, by_tag: dict, width=250) -> str:
    """One little United States per counter item, a dot per shop that carries it. One
    series per panel, so the panel title carries identity."""
    fit = usmap.fit_states(states_geo, width)
    h = fit["h"]
    paths = "".join(f'<path class="st" d="{d}"/>' for iso, name, d in usmap.state_paths(states_geo, fit)
                    if usmap.zone_of_state(iso) == "l48")
    out = ['<div class="smallmult">']
    for key, label in COUNTER_ORDER:
        rows = by_tag.get(key) or []
        if not rows:
            continue
        dots = []
        for r in rows:
            if r.get("lat") is None:
                continue
            x, y = usmap.project(r["lon"], r["lat"], fit)
            if 0 <= x <= width and 0 <= y <= h:
                where = ", ".join(z for z in (r.get("city"), r.get("state")) if z)
                dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="var(--donut)" stroke="var(--panel)" '
                            f'stroke-width="1.2"><title>{E(r["name"])} — {E(where)}</title></circle>')
        out.append(f'<figure><figcaption>{E(label)} <small>{len(rows)} shop{"s" if len(rows) != 1 else ""}</small></figcaption>'
                   f'<svg viewBox="0 0 {width} {h:.0f}" role="img" aria-label="Shops recorded as selling {E(label.lower())}, across the United States">'
                   f'<style>.st{{fill:var(--chip);stroke:var(--mute);stroke-width:.6}}</style>{paths}{"".join(dots)}</svg></figure>')
    out.append("</div>")
    return "".join(out)


def counter_page(page, places: dict, recs: list, tagvocab: dict, states_geo: dict, site_url: str) -> str:
    rows = [r for r in places["places"] if not r.get("chain")]   # the chains are a different subject
    tags = {e["key"]: e for e in tagvocab.get("entries", [])}
    by_tag: dict = {}
    for r in rows:
        for t in r.get("tags", []):
            if t in dict(COUNTER_ORDER):
                by_tag.setdefault(t, []).append(r)
    total = len({r["id"] for v in by_tag.values() for r in v})
    body = ['<h1><span class="kind">Pink Box</span>The other menu</h1>',
            '<p class="lede">What else is in the case, and why it is there.</p>',
            '<div class="facts">'
            + "".join(f'<div class="fact"><div class="n">{len(by_tag.get(k, []))}</div><div class="l">{E(l)}</div></div>'
                      for k, l in COUNTER_ORDER[:4])
            + f'<div class="fact"><div class="n">{total}</div><div class="l">shops in all</div></div></div>',
            '<p>A donut shop\'s own trade is over by mid-morning and the rent is not. Jolly Chan, who opened China Express and '
            'Donut by the 24th Street BART station in San Francisco in 1993, told KQED in 2021 that the two menus sit together '
            'because the combination &#8220;came out of necessity&#8221; — &#8220;We have to sell more stuff to make up the rent and the expense.&#8221; '
            'That is the mechanism, in the words of somebody running it. '
            '<a href="../story/why-the-egg-rolls/index.html">The long version is here</a>.</p>',
            '<div class="viz"><h3>Where each one turns up</h3>'
            '<p class="note">One panel per item, a dot per shop. Hover a dot for the shop and its town. Lower forty-eight only.</p>'
            + counter_multiples(states_geo, by_tag)
            + '<figcaption>State outlines: Natural Earth, public domain. Shop points: OpenStreetMap contributors, ODbL, plus the '
              'shops written up here.</figcaption></div>',
            '<h2>How a shop gets on this page</h2>'
            '<p class="mute">Two kinds of evidence, and every row says which. A shop written up here carries the tag because a menu, '
            'a photograph of the board or a press piece names the item, and the record links to it. A row from OpenStreetMap carries '
            'the tag because the map itself records it — in the shop&#8217;s own name, or in its cuisine tags. A shop called '
            '&#8220;Donut &amp; Burrito&#8221; is advertising the second menu on its sign.</p>'
            '<p class="mute">That is a floor, not a count. Most shops selling egg rolls do not say so in their name, and most have '
            'never been read here. An empty panel says where the reading stopped.</p>'
            '<p class="mute">Chain locations are left out of this page entirely. A company decides what is on its own board '
            'nationally, which is the opposite of the thing being counted here.</p>']
    for key, label in COUNTER_ORDER:
        rows_k = sorted(by_tag.get(key) or [], key=lambda r: (not r.get("curated"), r.get("state") or "", r["name"]))
        if not rows_k:
            continue
        ev = tags.get(key, {}).get("evidence", "")
        items = []
        for r in rows_k[:60]:
            where = ", ".join(z for z in (r.get("city"), r.get("state")) if z)
            nm = (f'<a href="../{E(r["url"])}index.html">{E(r["name"])}</a>' if r.get("url") else E(r["name"]))
            mark = ' <span class="chip">written up</span>' if r.get("curated") else ""
            items.append(f'<li>{nm}{mark} <span class="mute">{E(where)}</span></li>')
        more = f'<p class="mute">…and {len(rows_k) - 60} more.</p>' if len(rows_k) > 60 else ""
        body.append(f'<h2>{E(label)} <span class="count">({len(rows_k)})</span></h2>'
                    f'<p class="mute">What earns the tag: {E(ev)}</p>'
                    f'<div class="pl-list"><ul>{"".join(items)}</ul></div>{more}')
    body.append('<p class="legend">Counter tags for OpenStreetMap rows are derived by <code>tools/build.py</code> from the name and '
                'cuisine tags in the map data, and marked harvested. A shop&#8217;s own record carries its own evidence. '
                'The whole table is at <a href="../api/places.json">api/places.json</a>.</p>')
    return page("The other menu — Pink Box", "".join(body), 1,
                "Donut shops that also sell egg rolls, breakfast burritos, bacon egg and cheese, kolaches, croissant sandwiches, fried rice or boba — mapped, counted, and with the evidence for each.",
                [{"@context": "https://schema.org", "@type": "WebPage", "name": "The other menu", "url": f"{site_url}/counter/"}],
                f"{site_url}/counter/", extra_head=f"<style>{CHART_CSS}</style>", card="counter",
                og_alt="Donut shops that also sell egg rolls, burritos and bacon egg and cheese")


# ------------------------------------------------------------- cake or raised

# A donut in section: two lobes with the hole between them, sitting above the fat. The
# raised one is tall and full of gas; the cake one is short, dense and split on top.
# Emphasis, not categories — one dough at a time is painted and the other recedes — plus
# the two dough colours where both are shown together, which the legend names.

def dough_svg(lit: set, width=460, label=True, ident="") -> str:
    """Two donuts cut through the ring and set in the fat, so the hole is the gap in the
    middle and the pale belt is the line where each one floated. `lit` holds the doughs to
    paint; anything not in it recedes to the panel's own chip colour."""
    uid = re.sub(r"[^a-z0-9]+", "", (ident or "d").lower())[:12] or "d"
    def col(key):
        return DOUGH_COLOR[key][0] if key in lit else "var(--chip)"
    FAT = 150          # the surface of the fat, and the belt line
    o = [f'<svg viewBox="0 0 460 236" role="img" aria-label="A raised donut and a cake donut cut through the ring '
         f'and floating in the fat: the raised one tall and full of gas, the cake one shorter, denser and split on top">']
    # the fat: a wave across the whole width with a body below it
    wave = "M0 %d " % FAT + " ".join("q11 -7 22 0 t22 0" for _ in range(11))
    o.append(f'<path d="{wave} L460 236 L0 236 Z" fill="var(--lemon)" opacity=".16"/>')
    o.append(f'<path d="{wave}" fill="none" stroke="var(--lemon)" stroke-width="2.6" opacity=".85"/>')

    def donut(cx, key, rx, ry, bubbles, br, crack):
        c = col(key)
        g = [f'<defs><clipPath id="c{uid}{key}"><rect x="{cx - 120}" y="{FAT - ry - 8}" width="240" height="{ry + 8}"/></clipPath></defs>']
        for sign in (-1, 1):
            x = cx + sign * (rx + 13)
            g.append(f'<ellipse cx="{x}" cy="{FAT}" rx="{rx}" ry="{ry}" fill="{c}" stroke="var(--ink)" stroke-width="2.6"/>')
            # the glaze: a cap over the top third, not an outline
            # the glaze, the crumb and the belt are painted in white at low opacity rather
            # than in the panel colour: they must read pale on the dough in both themes.
            g.append(f'<ellipse cx="{x}" cy="{FAT}" rx="{rx - 2}" ry="{ry - 2}" fill="#fff" opacity=".30" '
                     f'clip-path="url(#c{uid}{key})"/>')
            for bx, by, m in bubbles:
                g.append(f'<circle cx="{x + bx}" cy="{FAT + by}" r="{br * m:.1f}" fill="#fff" opacity=".62"/>')
            if crack:
                g.append(f'<path d="M{x - rx * 0.62:.0f} {FAT - ry * 0.55:.0f} l6 7 l7 -8 l7 8 l6 -7" fill="none" '
                         f'stroke="#2a1420" stroke-width="2.4" stroke-linejoin="round" opacity=".55"/>')
        # the belt, drawn last so it sits on top of both lobes at the fat line
        g.append(f'<line x1="{cx - rx * 2 - 26}" y1="{FAT}" x2="{cx + rx * 2 + 26}" y2="{FAT}" '
                 f'stroke="#fff" stroke-width="3" opacity=".75"/>')
        return "".join(g)

    RAISED_B = [(-11, -13, 1.0), (9, -17, .85), (0, -6, .7), (13, -6, .8), (-13, -2, .75)]
    CAKE_B = [(x, y, .34) for x, y in ((-14, -9), (-6, -14), (3, -7), (11, -12), (15, -3), (-3, -2), (8, -2), (-16, -3))]
    o.append(donut(118, "yeast", 25, 33, RAISED_B, 6.5, False))
    o.append(donut(330, "cake", 27, 21, CAKE_B, 6.5, True))

    if label:
        for x, t in ((118, "raised"), (330, "cake")):
            o.append(f'<text x="{x}" y="34" text-anchor="middle" fill="var(--ink)" '
                     f'style="font:700 20px \'Arial Rounded MT Bold\',Avenir,sans-serif">{E(t)}</text>')
        o.append(f'<text x="118" y="60" text-anchor="middle" fill="var(--mute)" style="font:600 12px -apple-system,sans-serif">'
                 f'yeast · 150 s · 38 g</text>')
        o.append(f'<text x="330" y="60" text-anchor="middle" fill="var(--mute)" style="font:600 12px -apple-system,sans-serif">'
                 f'baking powder · 90 s · 24–28 g</text>')
        for x in (118, 330):
            o.append(f'<line x1="{x}" y1="{FAT + 40}" x2="{x}" y2="{FAT - 10}" stroke="var(--mute)" stroke-width="1.4" stroke-dasharray="4 3"/>')
            o.append(f'<text x="{x}" y="{FAT + 58}" text-anchor="middle" fill="var(--ink)" '
                     f'style="font:700 14px \'Arial Rounded MT Bold\',Avenir,sans-serif">the hole</text>')
        o.append(f'<text x="8" y="{FAT - 8}" fill="var(--mute)" style="font:600 12px -apple-system,sans-serif">the fat</text>')
        o.append(f'<text x="452" y="{FAT - 8}" text-anchor="end" fill="var(--mute)" style="font:600 12px -apple-system,sans-serif">the belt</text>')
    o.append("</svg>")
    return "".join(o)


# (style id, label, doughs it runs, the sentence under the drawing)
DOUGH_STYLES = [
    ("socal-pink-box", "The pink box shop", {"yeast", "cake"},
     "Both doughs, one kettle: raised goes up overnight and is fried first, cake batter drops after."),
    ("southern-hot-now", "The hot light", {"yeast"},
     "One raised ring, glazed hot in a window, and a sign that says the fryer is running."),
    ("new-england-cider", "The orchard window", {"cake"},
     "One cake batter with cider in it, one machine, and six weeks of the year."),
    ("hawaii-malasada", "The malasada counter", {"yeast"},
     "Raised, hand-pulled, no hole, and into the sugar straight out of the fat."),
    ("louisiana-beignet", "The beignet stand", {"choux"},
     "Neither yeast nor powder in the New Orleans version: steam lifts it and it comes out hollow."),
    ("pennsylvania-fastnacht", "Fastnacht Day", {"potato"},
     "Potato dough, risen overnight, cut square, and only on the Tuesday."),
    ("texas-kolache-counter", "The kolache counter", {"yeast", "cake"},
     "Both doughs plus an oven, because the klobasniky are baked and the donuts are not."),
]


def dough_page(page, by_id: dict, site_url: str) -> str:
    bench = [i for i in ("yeast-raise", "cake-batter", "proof-box", "the-fryer", "frying-fat", "glaze-table", "hand-cut") if i in by_id]
    body = ['<h1><span class="kind">Pink Box</span>Cake or raised</h1>',
            '<p class="lede">Every donut in the case is one or the other, and the whole shop is arranged around which.</p>',
            '<div class="drawwrap">' + dough_svg({"yeast", "cake"}) + '</div>',
            '<div class="legend-row"><span><i style="background:' + DOUGH_COLOR["yeast"][0] + '"></i>Raised — yeast</span>'
            '<span><i style="background:' + DOUGH_COLOR["cake"][0] + '"></i>Cake — baking powder or soda</span></div>',
            '<p class="mute">Both drawings are cut through the ring, so the hole is the gap in the middle. The pale band across '
            'each one is the belt: the line where the donut floated before it was turned. On the cake ring the top splits as it '
            'fries, which is what an old-fashioned is sold for.</p>',
            '<div class="two-up">'
            '<div class="pitch"><h2 style="border:0;margin-top:0">Raised</h2>'
            '<p>Yeast, proofed twice, about 150 seconds at 182–190 °C. Averages 38 grams. Comes out light, goes stale fastest, '
            'and takes a thin glaze while it is still hot enough to melt it.</p>'
            '<p class="mute">Glazed rings, bars, fritters, bear claws, filled rounds, malasadas, pączki.</p></div>'
            '<div class="pitch"><h2 style="border:0;margin-top:0">Cake</h2>'
            '<p>Baking powder or soda, dropped as batter, about 90 seconds at 190–198 °C. Runs 24 to 28 grams. Denser, holds a '
            'flavour, keeps longer, and takes sugar or a heavy icing rather than a thin glaze.</p>'
            '<p class="mute">Old-fashioned, buttermilk bars, sour cream, blueberry, chocolate, cider donuts.</p></div></div>']
    body.append('<h2>Who runs which</h2><div class="cards">')
    for sid, label, doughs, line in DOUGH_STYLES:
        if sid not in by_id:
            continue
        body.append(f'<div class="card">{dough_svg(doughs, label=False, ident=sid)}'
                    f'<a class="t" href="../style/{E(sid)}/index.html">{E(label)}</a><p>{E(line)}</p></div>')
    body.append("</div>")
    if bench:
        body.append('<h2>Out back</h2><p class="mute">The steps the two doughs argue over.</p><div class="cards">'
                    + "".join(f'<div class="card"><a class="t" href="../kitchen/{E(c)}/index.html">{E(by_id[c]["names"]["name"])}</a>'
                              f'<p>{E(by_id[c]["blurb"][:150])}</p></div>' for c in bench) + "</div>")
    body.append('<p class="legend">Frying times, temperatures, weights and oil figures come from the cited accounts on '
                '<a href="../story/cake-against-raised/index.html">cake against raised</a>, which disagree about the oil and agree '
                'about the direction. The drawings are this project\'s, not a photograph of any shop\'s donut.</p>')
    return page("Cake or raised — Pink Box", "".join(body), 1,
                "What separates a raised donut from a cake donut: yeast against baking powder, 150 seconds against 90, 38 grams against 26, and which shops run which.",
                [{"@context": "https://schema.org", "@type": "WebPage", "name": "Cake or raised", "url": f"{site_url}/dough/"}],
                f"{site_url}/dough/", extra_head=f"<style>{CHART_CSS}.drawwrap{{background:var(--panel);border:2px solid var(--line);border-radius:16px;padding:.8rem}}.drawwrap svg{{width:100%;max-width:34rem;height:auto;display:block;margin:0 auto}}.cards svg{{width:100%;height:auto;margin-bottom:.4rem}}</style>",
                card="dough", og_alt="A raised donut and a cake donut in cross-section")


def numbers_page(page, recs: list, places: dict, geo: dict, site_url: str, site_dir) -> str:
    import collections
    import re as _re

    pl = places["places"]
    by_id = {r["id"]: r for r in recs}

    # 1 — how near the nearest donut counter is, anywhere in the country
    out_png = site_dir / "viz" / "near-the-nearest-donut.png"
    stats = viz.distance_png(geo, pl, out_png)

    # 2 — when the pits opened
    years = []
    for r in recs:
        y = (r.get("facets") or {}).get("founded")
        if r["type"] == "place" and y and _re.fullmatch(r"\d{4}", str(y)):
            years.append((int(y), r["names"]["name"]))

    # 3 — what the recipes call for
    stop = {"teaspoon", "teaspoons", "tablespoon", "tablespoons", "tbsp", "tsp", "cups", "cup", "quart", "pound",
            "pounds", "ounce", "ounces", "optional", "ground", "minced", "chopped", "finely", "taste", "large",
            "small", "fresh", "about", "into", "with", "plus", "each", "more", "than", "very", "well", "your",
            "prepared", "granulated", "packed", "pieces", "piece", "inch", "size", "good", "half", "them", "from"}
    words = collections.Counter()
    nrec = 0
    for r in recs:
        for rc in r.get("recipes", []):
            nrec += 1
            seen = set()
            for i in rc.get("ingredients", []):
                for wd in _re.findall(r"[a-z]{4,}", i.lower()):
                    if wd not in stop:
                        seen.add(wd)
            words.update(seen)
    ing_rows = [(w, c) for w, c in words.most_common(16)]

    # 4 — which days a donut counter is open
    known = [p for p in pl if any(v != "unknown" for v in (p.get("days") or {}).values())]
    nh = len(known)
    days = {d: sum(1 for p in known if (p.get("days") or {}).get(d) == "open") for d in viz.DAYS}
    closed_su = sum(1 for p in known if (p.get("days") or {}).get("Su") == "closed")
    unk_su = len(pl) - nh
    day_rows = [(viz.DAY_NAME[d], days[d]) for d in viz.DAYS]

    # 5 — which kinds of page point at which
    edges = []
    for r in recs:
        for k in r.get("kin_out", []):
            t = by_id.get(k["to"])
            if t:
                edges.append({"from_type": r["type"], "to_type": t["type"]})
    order = ["style", "donut", "dish", "kitchen", "place", "person", "org", "event", "term", "art", "story"]
    present = [t for t in order if any(e["from_type"] == t or e["to_type"] == t for e in edges)]
    labels = {"style": "styles", "donut": "donuts", "dish": "dishes", "kitchen": "the kitchen", "place": "places",
              "person": "people", "org": "orgs", "event": "events", "term": "words", "art": "art", "story": "stories"}

    # a few numbers worth stating plainly
    lat_lon = [(p["lat"], p["lon"]) for p in pl if p.get("lat") is not None]
    import math as _m
    nearest = []
    for i, (a, b) in enumerate(lat_lon):
        best = min(((a - c) * 69) ** 2 + ((b - d) * 69 * _m.cos(_m.radians(a))) ** 2
                   for j, (c, d) in enumerate(lat_lon) if i != j)
        nearest.append(_m.sqrt(best))
    nearest.sort()
    med_gap = nearest[len(nearest) // 2] if nearest else 0

    body = ['<h1><span class="kind">Pink Box</span>Numbers</h1>',
            '<p class="lede">Adding it up.</p>',
            '<div class="facts">'
            + "".join(f'<div class="fact"><div class="n">{n}</div><div class="l">{E(l)}</div></div>' for n, l in [
                (f"{stats['median']:.0f} mi", "median distance to a donut counter, lower forty-eight"),
                (f"{med_gap:.1f} mi", "median distance from one counter to the next"),
                (len(pl), "places"), (nrec, "recipes"), (len(edges), "links between pages")])
            + "</div>"]

    body.append('<div class="viz"><h3>Distance to a donut</h3>'
                f'<p class="note">Every point in the lower forty-eight, shaded by the distance to the closest of the {len(lat_lon)} places on the map. '
                f'Black dots are the places themselves. Half the country sits within {stats["median"]:.0f} miles of one.</p>'
                f'<img src="../viz/near-the-nearest-donut.png" alt="A map of the United States shaded by distance to the nearest donut counter; the eastern seaboard and the Great Lakes run dark, the Great Basin and the high plains pale." style="width:100%;border-radius:10px;display:block">'
                + viz.ramp_legend(stats["cuts"], stats["ramp"], "miles to the nearest donut counter")
                + '<details class="tbl"><summary>The far corners</summary><table><tr><th>Miles to a donut</th><th>Where</th></tr>'
                + "".join(f'<tr><td>{mi:.0f}</td><td>{lat:.2f}, {lon:.2f}</td></tr>' for mi, lat, lon in stats["worst"])
                + '</table></details></div>')

    if years:
        body.append('<div class="viz"><h3>Founding years</h3>'
                    f'<p class="note">The {len(years)} places here whose founding year is on a page. Stems stack where a year is crowded. '
                    'Hover one for the name.</p>' + viz.timeline_svg(years)
                    + '<details class="tbl"><summary>By decade</summary><table><tr><th>Decade</th><th>Pits</th></tr>'
                    + "".join(f"<tr><td>{d}s</td><td>{c}</td></tr>" for d, c in sorted(collections.Counter((y // 10) * 10 for y, _ in years).items()))
                    + "</table></details></div>")

    body.append('<div class="viz"><h3>Ingredients, by how many recipes call for them</h3>'
                f'<p class="note">Across {nrec} recipes, counting each ingredient once per recipe. Measures and cutting words are dropped.</p>'
                + viz.bars_svg(ing_rows, unit="recipes calling for it")
                + '<details class="tbl"><summary>As a table</summary><table><tr><th>Ingredient word</th><th>Recipes</th></tr>'
                + "".join(f"<tr><td>{E(w)}</td><td>{c}</td></tr>" for w, c in ing_rows) + "</table></details></div>")

    body.append('<div class="viz"><h3>Days open</h3>'
                f'<p class="note">From the {nh} places whose days we could read. A donut counter keeps the weekend and most of the week. '
                f'{closed_su} of the {nh} shut on Sunday; another {unk_su} have no published days at all, and those draw as blanks. '
                'A blank means unread, and the filters leave it out.</p>'
                + viz.bars_svg(day_rows, unit="places open", left=140)
                + '<details class="tbl"><summary>As a table</summary><table><tr><th>Day</th><th>Open</th></tr>'
                + "".join(f"<tr><td>{E(d)}</td><td>{c}</td></tr>" for d, c in day_rows) + "</table></details></div>")

    body.append('<div class="viz"><h3>Kin, by kind of page</h3>'
                f'<p class="note">Every one of the {len(edges)} links between pages, by the kind of page at each end. '
                'The row points at the column.</p>'
                + viz.kin_matrix_svg(edges, present, labels) + "</div>")

    body.append('<p class="legend">The distance map is computed on a grid clipped to the states\' own outlines '
                '(Natural Earth, public domain) and measured against every place on the map, most of which come from OpenStreetMap under the ODbL. '
                'Everything else is counted straight out of <a href="../api/nodes.json">the records</a>.</p>')
    return page("Numbers — Pink Box", "".join(body), 1,
                "American donut shops counted: how near the nearest counter sits anywhere in the country, when the shops opened, what the recipes call for, which days they open.",
                None, f"{site_url}/numbers/", extra_head=f"<style>{CHART_CSS}</style>", card="numbers",
                og_alt="A map of the United States shaded by distance to the nearest donut counter")


# ---------------------------------------------------------------- make a donut

MAKE_CSS = """
.dials{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:1rem;background:var(--panel);
  border:1px solid var(--line);border-radius:14px;padding:1rem 1.1rem;margin:.6rem 0 1.2rem}
.dial b{display:block;font-size:.78rem;text-transform:uppercase;letter-spacing:.14em;color:var(--gold);
  font-family:var(--sign,sans-serif);margin-bottom:.4rem}
.dial .opts{display:flex;flex-wrap:wrap;gap:.35rem}
.dial button{font:inherit;font-size:.86rem;font-family:var(--ui,sans-serif);padding:.32rem .72rem;border-radius:999px;
  border:1.5px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.dial button[aria-pressed=true]{background:var(--donut);border-color:var(--donut);color:#fff}
.recipe{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:1.2rem 1.3rem}
.recipe h3{margin:.1rem 0 .1rem;font-size:1.3rem}
.recipe .says{color:var(--mute);font-style:italic;margin:0 0 .9rem}
.recipe ul{list-style:none;margin:.2rem 0 1rem;padding:0}
.recipe li{display:flex;gap:.7rem;padding:.3rem 0;border-bottom:1px dotted var(--line);font-size:1rem}
.recipe li .q{flex:0 0 9.5rem;text-align:right;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}
@media(max-width:520px){.recipe li{flex-direction:column;gap:0}.recipe li .q{text-align:left;flex:none}}
.recipe li.zero{display:none}
.recipe ol{margin:.2rem 0 1rem;padding-left:1.2rem}.recipe ol li{display:list-item;border:0;padding:.15rem 0}
.recipe .prov{font-size:.85rem;color:var(--mute);border-top:1px solid var(--line);padding-top:.7rem;margin-top:.4rem}
.sugarline{display:flex;align-items:baseline;gap:.6rem;flex-wrap:wrap;margin:.2rem 0 .3rem}
.sugarline b{font-size:1.5rem;font-family:var(--display,serif)}
.nearby{font-size:.88rem;color:var(--mute);margin:.5rem 0 0}
.mk-actions{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem}
"""


MAKE_TABS_CSS = """
.tabs{display:flex;gap:.4rem;margin:.2rem 0 1rem}
.tabs button{font:inherit;font-family:var(--sign,sans-serif);font-size:.95rem;letter-spacing:.04em;padding:.5rem 1.1rem;
  border-radius:999px;border:2px solid var(--line);background:var(--bg);color:var(--ink);cursor:pointer}
.tabs button[aria-selected=true]{background:var(--donut);border-color:var(--donut);color:#fff}
.panel[hidden]{display:none}
.carolina-note{background:var(--panel);border-left:5px solid var(--gold);border-radius:0 12px 12px 0;padding:.8rem 1rem;margin:.2rem 0 1rem;font-size:.95rem}
.per{font-size:.86rem;color:var(--mute);margin:.1rem 0 .8rem}
"""


def make_page(page, builder: dict, donuts: dict, recs: list, site_url: str, rub: dict | None = None, dip: dict | None = None) -> str:
    by_id = {r["id"]: r for r in recs}
    # every bottle we measured, so the result can be put beside them
    measured = [{"n": s["name"], "d": s.get("dough"), "g": s.get("sugar_g"), "w": s.get("serving_g")}
                for s in donuts.get("donuts", []) if s.get("sugar_g") is not None]
    for b in builder["bases"]:
        rec = by_id.get(b["donut"])
        b["href"] = f"../donut/{b['donut']}/index.html" if rec else ""
        st = by_id.get(b["style"])
        b["style_href"] = f"../style/{b['style']}/index.html" if st else ""
        b["style_name"] = st["names"]["name"] if st else ""

    # The page opens on the recipe as its source has it — heat and sweetness at 1.0 — so the
    # first thing a reader sees is the cited proportions, and the dials move away from them.
    DEFAULTS = {"base": builder["bases"][0]["key"], "heat": "medium", "sweet": "sweet", "batch": "cup"}

    def dial(name, key, opts):
        return (f'<div class="dial"><b>{E(name)}</b><div class="opts" data-dial="{key}">'
                + "".join(f'<button type="button" data-v="{E(o["key"])}" '
                          f'aria-pressed="{"true" if o["key"] == DEFAULTS[key] else "false"}">{E(o["label"])}</button>'
                          for o in opts) + "</div></div>")

    RDEF = {"level": rub["levels"][1]["key"], "meat": "twenty", "heat": "medium"}
    SDEF = {"kind": dip["kinds"][0]["key"], "size": "cup", "sweet": "some", "heat": "some"}

    def sdial(name, key, opts):
        return (f'<div class="dial"><b>{E(name)}</b><div class="opts" data-dial="{key}">'
                + "".join(f'<button type="button" data-v="{E(o["key"])}" '
                          f'aria-pressed="{"true" if o["key"] == SDEF[key] else "false"}">{E(o["label"])}</button>'
                          for o in opts) + "</div></div>")

    def rdial(name, key, opts):
        return (f'<div class="dial"><b>{E(name)}</b><div class="opts" data-dial="{key}">'
                + "".join(f'<button type="button" data-v="{E(o["key"])}" '
                          f'aria-pressed="{"true" if o["key"] == RDEF[key] else "false"}">{E(o["label"])}</button>'
                          for o in opts) + "</div></div>")

    body = f"""
<h1><span class="kind">Pink Box</span>Make some</h1>
<p class="lede">A glaze, a dough, or something to put inside it. Where a free-to-use recipe exists it is named and used in its
own ratios. Where none does, the page says the proportions are this project&#8217;s.</p>

<div class="tabs" role="tablist">
  <button type="button" role="tab" data-panel="donut" aria-selected="true">Glaze</button>
  <button type="button" role="tab" data-panel="rub" aria-selected="false">Dough</button>
  <button type="button" role="tab" data-panel="dip" aria-selected="false">Filling</button>
</div>

<section class="panel" id="panel-donut">
<div class="dials">
  {dial("Which glaze", "base", [{"key": b["key"], "label": b["name"]} for b in builder["bases"]])}
  {dial("How thin", "heat", builder["heats"])}
  {dial("How sweet", "sweet", builder["sweets"])}
  {dial("How much", "batch", builder["batches"])}
</div>

<div class="recipe" id="out"></div>

</section>

<section class="panel" id="panel-rub" hidden>
<p class="carolina-note">{E(rub["house_note"])}</p>
<div class="dials">
  {rdial("Which dough", "level", [{"key": l["key"], "label": l["name"]} for l in rub["levels"]])}
  {rdial("How much flour", "meat", [{"key": m["key"], "label": m["label"]} for m in rub["meats"]])}
  {rdial("Spice", "heat", rub["heats"])}
</div>
<div class="recipe" id="rubout"></div>
<p class="legend">A pound of flour is taken as about a dozen donuts, which is this project's rule of thumb rather than a
measurement. The proportions inside each dough are the cited part.</p>
</section>

<section class="panel" id="panel-dip" hidden>
<p class="carolina-note">{E(dip["house_note"])}</p>
<div class="dials">
  {sdial("Which filling", "kind", [{"key": k["key"], "label": k["name"]} for k in dip["kinds"]])}
  {sdial("How much", "size", [{"key": z["key"], "label": z["label"]} for z in dip["sizes"]])}
  {sdial("How sweet", "sweet", dip["sweets"])}
  {sdial("Flavouring", "heat", dip["heats"])}
</div>
<div class="recipe" id="slawout"></div>
<p class="legend">Quantities scale off the finished cup. A cup fills about eight donuts, which is a rule of thumb. Each
filling says whose proportions it is using.</p>
</section>

<p class="legend">Sugar is worked out from the quantities on screen: {builder["sugar_g_per_tbsp"]["powdered sugar"]} g of sugar in a tablespoon of powdered sugar, {builder["sugar_g_per_tbsp"]["sugar"]} g in granulated, {builder["sugar_g_per_tbsp"]["maple syrup"]} g in maple syrup, {builder["sugar_g_per_tbsp"]["honey"]} g in honey. It is then divided across a dozen donuts to the cup of glaze, which is a rule of thumb rather than a measurement. The donuts it is drawn against were weighed by USDA and are on <a href="../donut/index.html">the donut page</a> — those figures are the whole donut, dough included, and this one is the glaze alone.</p>

<script>
(function(){{
var B={esc_js(builder)}, MEASURED={esc_js(measured)};
var pick={{base:B.bases[0].key, heat:"medium", sweet:"sweet", batch:"cup"}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
var FRAC=[[1,"1"],[0.75,"¾"],[0.6667,"⅔"],[0.5,"½"],[0.3333,"⅓"],[0.25,"¼"],[0.125,"⅛"]];
function nice(tbsp){{
  /* the kitchen unit a cook would actually reach for */
  if(tbsp<=0) return null;
  var p=function(v,w){{return frac(v)+" "+w+(v>1.02?"s":"")}};
  if(tbsp>=16) return p(tbsp/16,"cup");
  if(tbsp>=1) return p(tbsp,"tablespoon");
  return p(tbsp*3,"teaspoon");
}}
function frac(v){{
  var whole=Math.floor(v+1e-9), rem=v-whole, best="", bd=9;
  for(var i=0;i<FRAC.length;i++){{var d=Math.abs(rem-FRAC[i][0]); if(d<bd){{bd=d;best=FRAC[i][1];}}}}
  if(rem<0.06) return String(whole||"0");
  /* a kitchen has no 0.58 of a spoon: snap to the nearest named fraction unless it is
     genuinely far from all of them */
  if(bd>0.1&&whole===0) return (Math.round(v*100)/100).toString();
  if(best==="1"){{whole+=1;best="";}}
  return (whole?whole+(best?" ":""):"")+best;
}}
function base(){{return B.bases.filter(function(b){{return b.key===pick.base}})[0]}}
function mult(list,key){{var m=list.filter(function(x){{return x.key===key}})[0]; return m?m.mult:1}}
function compute(){{
  var b=base(), tbsp=B.batches.filter(function(x){{return x.key===pick.batch}})[0].tbsp;
  var hm=mult(B.heats,pick.heat), sm=mult(B.sweets,pick.sweet);
  var rows=[], vol=0, sugar=0;
  b.ingredients.forEach(function(ing){{
    var f=ing.per_tbsp;
    if(ing.dial==="heat") f*=hm;
    if(ing.dial==="sweet") f*=sm;
    var q=f*tbsp;
    vol+=q;
    if(ing.sugar) sugar+=q*B.sugar_g_per_tbsp[ing.sugar];
    rows.push({{name:ing.name, q:q, hint:ing.unit_hint||""}});
  }});
  return {{b:b, rows:rows, vol:vol, sugar:vol>0?sugar/vol:0, tbsp:tbsp}};
}}
function perDonut(sugarPerTbsp){{
  /* a dozen is taken as the cup batch, so the glaze on one donut is the batch's sugar
     divided by twelve — this project's rule of thumb, said as one on the page */
  var tbsp=B.batches.filter(function(x){{return x.key===pick.batch}})[0].tbsp;
  var per=B.batches.filter(function(x){{return x.key===pick.batch}})[0].label.indexOf("dozen")>=0?12:12;
  var dozens=tbsp/16;
  return sugarPerTbsp*tbsp/(12*dozens);
}}
function scale(g){{
  /* grams of sugar in ONE donut, so the glaze and the USDA rows share an axis */
  var top=Math.max(20, g*1.15);
  MEASURED.forEach(function(m){{ if(m.g>top) top=m.g*1.08 }});
  var w=440, x0=10, x1=w-10, pos=function(v){{return x0+(x1-x0)*Math.min(v/top,1)}};
  var o='<svg viewBox="0 0 '+w+' 66" role="img" aria-label="Sugar in one glazed donut, against the donuts USDA has weighed">';
  o+='<rect x="'+x0+'" y="26" width="'+(x1-x0)+'" height="8" rx="4" fill="var(--chip)"/>';
  MEASURED.forEach(function(m){{ o+='<circle cx="'+pos(m.g).toFixed(1)+'" cy="30" r="3.6" fill="var(--mute)" opacity=".7"><title>'+esc(m.n)+' — '+m.g+' g in a '+m.w+' g piece</title></circle>'; }});
  o+='<circle cx="'+pos(g).toFixed(1)+'" cy="30" r="11" fill="var(--donut)" opacity=".25"/>';
  o+='<circle cx="'+pos(g).toFixed(1)+'" cy="30" r="7" fill="var(--donut)" stroke="var(--panel)" stroke-width="2"/>';
  o+='<text x="'+x0+'" y="58" fill="var(--mute)" style="font:600 11px var(--ui,sans-serif)">0 g</text>';
  o+='<text x="'+x1+'" y="58" text-anchor="end" fill="var(--mute)" style="font:600 11px var(--ui,sans-serif)">'+top.toFixed(0)+' g of sugar in one piece</text>';
  return o+'</svg>';
}}
function gap(g,key){{
  var all=MEASURED.map(function(m){{return m.g}}).sort(function(a,c){{return a-c}});
  if(all.length<2) return "";
  var med=all[Math.floor(all.length/2)];
  var d=med-g;
  if(Math.abs(d)<1.2) return '<p class="nearby">Roughly where the donuts USDA weighed sit — a median of '+med.toFixed(1)+' g of sugar in a piece, the whole donut included.</p>';
  if(d>0) return '<p class="nearby">The donuts USDA has weighed run around <b>'+med.toFixed(1)+' g</b> of sugar a piece, dough and all, so this glaze is the lighter half of that.</p>';
  return '<p class="nearby">That is more sugar than the median donut USDA weighed carries in total — <b>'+med.toFixed(1)+' g</b> — and this is the glaze alone.</p>';
}}function render(){{
  var r=compute(), b=r.b, a=b.anchor;
  var heat=B.heats.filter(function(x){{return x.key===pick.heat}})[0].label.toLowerCase();
  var sweet=B.sweets.filter(function(x){{return x.key===pick.sweet}})[0].label.toLowerCase();
  var batch=B.batches.filter(function(x){{return x.key===pick.batch}})[0].label;
  var ing=r.rows.map(function(x){{
    var q=nice(x.q);
    return '<li class="'+(q?'':'zero')+'"><span class="q">'+esc(q||'')+'</span><span>'+esc(x.name)+
      (x.hint?' <span class="mute">('+esc(x.hint)+')</span>':'')+'</span></li>';
  }}).join("");
  var perOne=perDonut(r.sugar);
  var near=MEASURED.sort(function(p,q){{return Math.abs(p.g-perOne)-Math.abs(q.g-perOne)}}).slice(0,3);
  var prov;
  if(a.kind==="recipe") prov='Built on <b>'+esc(a.title)+'</b>'+(a.year?', '+a.year:'')+', '+esc(a.publisher)+
      ' — '+esc(a.license)+(a.url?' · <a href="'+esc(a.url)+'" rel="noopener">the recipe</a>':'')+'. '+esc(a.note||'');
  else if(a.kind==="ancestor") prov='Descends from <b>'+esc(a.title)+'</b>, '+esc(a.publisher)+' '+(a.year||'')+
      ' ('+esc(a.license)+'). '+esc(a.note||'');
  else prov='<b>These proportions are this project\\'s own.</b> '+esc(a.note||'');
  document.getElementById("out").innerHTML=
    '<h3>'+esc(b.name)+', '+esc(heat)+', '+esc(sweet)+' — '+esc(batch)+'</h3>'+
    '<p class="says">'+esc(b.says)+' · '+esc(b.region)+'</p>'+
    '<ul>'+ing+'</ul>'+
    '<h4>How</h4><ol>'+b.method.map(function(m){{return '<li>'+esc(m)+'</li>'}}).join("")+'</ol>'+
    '<div class="sugarline"><b>'+perOne.toFixed(1)+' g</b><span class="mute">of sugar this glaze puts on one donut, at a dozen to the cup</span></div>'+
    scale(perOne)+
    gap(perOne,b.key)+
    (near.length?'<p class="nearby">Nearest measured donuts: '+near.map(function(x){{return esc(x.n)+' ('+x.g+' g in a '+x.w+' g piece)'}}).join(' · ')+'</p>':'')+
    '<div class="mk-actions"><button type="button" class="btn" id="copy">Copy the recipe</button>'+
    (b.href?'<a class="btn ghost" href="'+b.href+'">About this donut</a>':'')+
    (b.style_href?'<a class="btn ghost" href="'+b.style_href+'">'+esc(b.style_name)+'</a>':'')+'</div>'+
    '<p class="prov">'+prov+' Method '+(b.method_tier==="cited"?'as published':b.method_tier==="tradition"?'as the tradition has it':'is ours')+'.</p>';
  document.getElementById("copy").addEventListener("click",function(){{
    var txt=b.name+' — '+heat+', '+sweet+', '+batch+'\\n\\n'+
      r.rows.filter(function(x){{return nice(x.q)}}).map(function(x){{return nice(x.q)+'  '+x.name}}).join('\\n')+
      '\\n\\n'+b.method.join('\\n')+'\\n\\n'+perDonut(r.sugar).toFixed(1)+' g of sugar on each donut.\\n'+
      'From Pink Box — {site_url}/make/';
    (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(function(){{
      document.getElementById("copy").textContent="Copied";
      setTimeout(function(){{document.getElementById("copy").textContent="Copy the recipe"}},1600);}},function(){{}});
  }});
}}
document.querySelector("#panel-donut .dials").addEventListener("click",function(e){{
  var btn=e.target.closest("button[data-v]"); if(!btn)return;
  var group=btn.closest("[data-dial]"), k=group.dataset.dial;
  pick[k]=btn.dataset.v;
  [].forEach.call(group.querySelectorAll("button"),function(x){{x.setAttribute("aria-pressed",x===btn?"true":"false")}});
  render();
}});
render();
}})();

/* ------------------------------------------------------------------ the rub */
(function(){{
var R={esc_js(rub)}, pick={{level:R.levels[1].key, meat:"twenty", heat:"medium"}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
var FR=[[1,"1"],[0.75,"¾"],[0.6667,"⅔"],[0.5,"½"],[0.3333,"⅓"],[0.25,"¼"],[0.125,"⅛"]];
function frac(v){{var w=Math.floor(v+1e-9),r=v-w,b="",bd=9;
  for(var i=0;i<FR.length;i++){{var d=Math.abs(r-FR[i][0]); if(d<bd){{bd=d;b=FR[i][1];}}}}
  if(r<0.06)return String(w||"0");
  if(bd>0.08&&w===0)return (Math.round(v*100)/100).toString();
  if(b==="1"){{w+=1;b="";}}
  return (w?w+(b?" ":""):"")+b;}}
function nice(tbsp){{if(tbsp<=0)return null;
  var p=function(v,wd){{return frac(v)+" "+wd+(v>1.02?"s":"")}};
  if(tbsp>=16)return p(tbsp/16,"cup");
  if(tbsp>=1)return p(tbsp,"tablespoon");
  return p(tbsp*3,"teaspoon");}}
function rate(tbspPerLb){{
  /* under a tablespoon reads better as teaspoons, which is where every level but the last sits */
  if(tbspPerLb>=1) return frac(tbspPerLb)+' tablespoon'+(tbspPerLb>1.02?'s':'');
  var t=tbspPerLb*3; return frac(t)+' teaspoon'+(t>1.02?'s':'');
}}
function lvl(){{return R.levels.filter(function(x){{return x.key===pick.level}})[0]}}
function render(){{
  var L=lvl(), M=R.meats.filter(function(x){{return x.key===pick.meat}})[0];
  var hm=R.heats.filter(function(x){{return x.key===pick.heat}})[0];
  var total=L.tbsp_per_lb*M.lb, rows=[], sum=0;
  for(var k in L.parts){{
    var f=L.parts[k];
    if(R.heat_ingredients.indexOf(k)>=0) f*=hm.mult;
    rows.push({{name:k, q:f*total}}); sum+=f*total;
  }}
  var a=L.anchor, prov;
  if(a.kind==="recipe") prov='<b>'+esc(a.title)+'</b>, '+esc(a.publisher)+' — '+esc(a.license)+
     (a.url?' · <a href="'+esc(a.url)+'" rel="noopener">the recipe</a>':'')+'. '+esc(a.note);
  else if(a.kind==="named") prov='<b>'+esc(a.title)+'</b>, from '+esc(a.publisher)+
     (a.url?' · <a href="'+esc(a.url)+'" rel="noopener">the article</a>':'')+'. '+esc(a.note);
  else prov=esc(a.note);
  document.getElementById("rubout").innerHTML=
    '<h3>'+esc(L.name)+' — for '+esc(M.label.toLowerCase())+'</h3>'+
    '<p class="says">'+esc(L.says)+'</p>'+
    '<p class="per">'+esc(M.label)+' is taken as <b>'+M.lb+' lb</b> ('+esc(M.note)+'), at '+
      rate(L.tbsp_per_lb)+' of rub to the pound.</p>'+
    '<ul>'+rows.map(function(x){{var q=nice(x.q);
      return '<li class="'+(q?'':'zero')+'"><span class="q">'+esc(q||'')+'</span><span>'+esc(x.name)+'</span></li>';}}).join("")+'</ul>'+
    '<p class="per">About '+esc(nice(sum)||"nothing")+' of rub in all.</p>'+
    (L.when?'<h4>When</h4><ol>'+L.when.map(function(m){{return '<li>'+esc(m)+'</li>'}}).join("")+'</ol>':'')+
    '<div class="mk-actions"><button type="button" class="btn" id="rubcopy">Copy the rub</button>'+
    '<a class="btn ghost" href="../dough/index.html">Cake or raised</a>'+
    '<a class="btn ghost" href="../kitchen/glaze-table/index.html">The glaze table</a></div>'+
    '<p class="prov">'+prov+'</p>';
  document.getElementById("rubcopy").addEventListener("click",function(){{
    var txt=L.name+' — for '+M.label.toLowerCase()+' ('+M.lb+' lb)\\n\\n'+
      rows.filter(function(x){{return nice(x.q)}}).map(function(x){{return nice(x.q)+'  '+x.name}}).join('\\n')+
      '\\n\\nFrom Pink Box — {site_url}/make/';
    (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(function(){{
      var b=document.getElementById("rubcopy"); b.textContent="Copied";
      setTimeout(function(){{b.textContent="Copy the rub"}},1600);}},function(){{}});
  }});
}}
document.querySelector("#panel-rub .dials").addEventListener("click",function(e){{
  var btn=e.target.closest("button[data-v]"); if(!btn)return;
  var g=btn.closest("[data-dial]"); pick[g.dataset.dial]=btn.dataset.v;
  [].forEach.call(g.querySelectorAll("button"),function(x){{x.setAttribute("aria-pressed",x===btn?"true":"false")}});
  render();
}});
render();
}})();

/* ------------------------------------------------------------------ the dip */
(function(){{
var S={esc_js(dip)}, pick={{kind:S.kinds[0].key, size:"cup", sweet:"some", heat:"some"}};
function esc(s){{return String(s==null?"":s).replace(/[&<>"]/g,function(c){{return {{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[c]}})}}
var FS=[[1,"1"],[0.75,"¾"],[0.6667,"⅔"],[0.5,"½"],[0.3333,"⅓"],[0.25,"¼"],[0.125,"⅛"]];
function frac(v){{var w=Math.floor(v+1e-9),r=v-w,b="",bd=9;
  for(var i=0;i<FS.length;i++){{var d=Math.abs(r-FS[i][0]); if(d<bd){{bd=d;b=FS[i][1];}}}}
  if(r<0.06)return String(w||"0");
  if(bd>0.08&&w===0)return (Math.round(v*100)/100).toString();
  if(b==="1"){{w+=1;b="";}}
  return (w?w+(b?" ":""):"")+b;}}
function amount(q,unit){{
  /* cups fall back to tablespoons and spoons to each other, so nothing reads as 0.06 cup */
  if(q<=0)return null;
  var plural=function(v,w){{return frac(v)+" "+w+(v>1.02?"s":"")}};
  if(unit==="cup"){{ if(q<0.25) return plural(q*16,"tablespoon"); return plural(q,"cup"); }}
  if(unit==="tbsp"){{ if(q<1) return plural(q*3,"teaspoon"); return plural(q,"tablespoon"); }}
  if(unit==="tsp"){{ if(q>=3) return plural(q/3,"tablespoon"); return plural(q,"teaspoon"); }}
  if(unit==="egg"){{ return frac(q); }}
  return plural(q,unit);
}}
function kind(){{return S.kinds.filter(function(x){{return x.key===pick.kind}})[0]}}
function render(){{
  var K=kind(), Z=S.sizes.filter(function(x){{return x.key===pick.size}})[0];
  var sw=S.sweets.filter(function(x){{return x.key===pick.sweet}})[0].mult;
  var ht=S.heats.filter(function(x){{return x.key===pick.heat}})[0].mult;
  var rows=K.per_cup.map(function(ing){{
    var q=ing.q*Z.cups;
    if(ing.dial==="sweet") q*=sw;
    if(ing.dial==="heat") q*=ht;
    return {{name:ing.name, txt:amount(q,ing.unit), opt:!!ing.optional}};
  }});
  var a=K.anchor, prov;
  if(a.kind==="recipe") prov='<b>'+esc(a.title)+'</b>, '+esc(a.publisher)+' '+(a.year||'')+' ('+esc(a.license)+'). '+esc(a.note);
  else prov='<b>These proportions are ours.</b> '+esc(a.note);
  document.getElementById("slawout").innerHTML=
    '<h3>'+esc(K.name)+' — '+esc(Z.label.toLowerCase())+'</h3>'+
    '<p class="says">'+esc(K.says)+' · '+esc(K.region)+'</p>'+
    '<p class="per">Makes about <b>'+Z.cups+' cup'+(Z.cups>1?'s':'')+'</b>.</p>'+
    '<ul>'+
    rows.map(function(x){{
      return '<li class="'+(x.txt?'':'zero')+'"><span class="q">'+esc(x.txt||'')+'</span><span>'+esc(x.name)+
        (x.opt?' <span class="mute">(optional)</span>':'')+'</span></li>';}}).join("")+'</ul>'+
    '<h4>How</h4><ol>'+K.steps.map(function(m){{return '<li>'+esc(m)+'</li>'}}).join("")+'</ol>'+
    (K.swap?'<p class="per"><b>Or:</b> '+esc(K.swap)+'</p>':'')+
    '<div class="mk-actions"><button type="button" class="btn" id="slawcopy">Copy the dip</button>'+
    '<a class="btn ghost" href="../donut/'+esc(K.dish)+'/index.html">About this dip</a></div>'+
    '<p class="prov">'+prov+(K.verbatim?' Steps quoted from the receipt.':' Steps are ours.')+'</p>';
  document.getElementById("slawcopy").addEventListener("click",function(){{
    var txt=K.name+' — '+Z.label.toLowerCase()+'\\n\\n'+
      rows.filter(function(x){{return x.txt}}).map(function(x){{return x.txt+'  '+x.name}}).join('\\n')+
      '\\n\\n'+K.steps.join('\\n')+'\\n\\nFrom Pink Box — {site_url}/make/';
    (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(function(){{
      var b=document.getElementById("slawcopy"); b.textContent="Copied";
      setTimeout(function(){{b.textContent="Copy the dip"}},1600);}},function(){{}});
  }});
}}
document.querySelector("#panel-dip .dials").addEventListener("click",function(e){{
  var btn=e.target.closest("button[data-v]"); if(!btn)return;
  var g=btn.closest("[data-dial]"); pick[g.dataset.dial]=btn.dataset.v;
  [].forEach.call(g.querySelectorAll("button"),function(x){{x.setAttribute("aria-pressed",x===btn?"true":"false")}});
  render();
}});
render();
}})();

/* ------------------------------------------------------------------ the tabs */
(function(){{
var tabs=document.querySelector(".tabs");
tabs.addEventListener("click",function(e){{
  var b=e.target.closest("button[data-panel]"); if(!b)return;
  [].forEach.call(tabs.querySelectorAll("button"),function(x){{
    var on=x===b; x.setAttribute("aria-selected",on?"true":"false");
    document.getElementById("panel-"+x.dataset.panel).hidden=!on;
  }});
}});
}})();
</script>
"""
    return page("Make some — Pink Box", body, 1,
                "Build a glaze, a dough or a filling. Every proportion says whether it came from a free-to-use published recipe or from this project, and the sugar is worked out on screen.",
                None, f"{site_url}/make/", extra_head=f"<style>{MAKE_CSS}{MAKE_TABS_CSS}{CHART_CSS}</style>", card="make",
                og_alt="Make a donut glaze, a dough or a filling")
