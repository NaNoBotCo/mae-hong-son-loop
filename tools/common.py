"""common.py — paths, loaders and the small JSON-Schema checker shared by every tool.

Stdlib only, Python 3.9+. External locations are overridable by environment
variable so the project keeps working when a sibling repo moves.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
NODES = DATA / "nodes"
IMAGES = DATA / "images"
VOCAB = DATA / "vocab"
HARVEST = DATA / "harvest"
GEO = DATA / "geo"
SOURCES = DATA / "sources" / "sources.json"
SCHEMA = ROOT / "schema" / "node.schema.json"
BUILD = ROOT / "build"
VENDOR = ROOT / "vendor"

PROJECTS = Path(os.environ.get("NAN_PROJECTS") or (Path.home() / "Developer" / "claude code projects"))
SEARCH_CORE = Path(os.environ.get("SEARCH_CORE") or (PROJECTS / "search-core"))

TYPES = ("leg", "road", "town", "stop", "wat", "dish", "coffee", "spring", "stay",
         "hazard", "bike", "kit", "person", "org", "event", "term", "story", "art")
TIERS = ("cited", "harvested", "tradition", "inference", "field")
TIER_LABEL = {
    "cited": "Cited — a named source, linked",
    "harvested": "Harvested — fetched from an open dataset, with its licence",
    "tradition": "Tradition — general knowledge of the tradition, hedged",
    "inference": "Inference — this project's own reasoning from the above",
    "field": "Field — someone stood there",
}


def jload(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jdump(obj, path: Path, indent=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, sort_keys=False)
        f.write("\n")
    os.replace(tmp, path)


def load_nodes() -> list[dict]:
    """Every record under data/nodes/<type>/, sorted by type then id."""
    out = []
    for t in TYPES:
        for p in sorted((NODES / t).glob("*.json")):
            d = jload(p)
            if isinstance(d, dict):
                d["_path"] = str(p)
                d["_dir_type"] = t
                out.append(d)
    return out


def load_sources() -> dict:
    """sources.json plus every data/sources/new-*.json (an author's additions not yet merged
    by build.py), so validation sees what the build will see."""
    if not SOURCES.exists():
        return {}
    out = {s["id"]: s for s in jload(SOURCES)["sources"]}
    for p in sorted(SOURCES.parent.glob("new-*.json")):
        try:
            for s in jload(p).get("sources", []):
                out.setdefault(s["id"], s)
        except (ValueError, KeyError, AttributeError):
            print(f"warn  {p.name}: not a sources file")
    return out


def load_vocab(name: str) -> dict:
    p = VOCAB / f"{name}.json"
    return jload(p) if p.exists() else {}


def load_harvest(name: str):
    p = HARVEST / f"{name}.json"
    return jload(p) if p.exists() else None


def search_core():
    """Import the fleet search core: the live copy in search-core/ first, vendor/ as fallback."""
    for d in (SEARCH_CORE, VENDOR):
        if (d / "searchcore.py").exists():
            if str(d) not in sys.path:
                sys.path.insert(0, str(d))
            import searchcore  # noqa: E402
            return searchcore, d
    raise RuntimeError("searchcore.py not found in search-core/ or vendor/")


_STATE_RINGS = None


def state_by_geo(lat: float, lon: float):
    """A two-letter state code, or None, by point-in-polygon against data/geo/states.json
    (ray casting). A postcode or an addr:state tag is a better tell; this is the fallback
    for harvested rows that carry neither. Bounding boxes are checked first so a point in
    Ohio does not walk the Alaskan coastline."""
    global _STATE_RINGS
    if _STATE_RINGS is None:
        g = jload(GEO / "states.json") if (GEO / "states.json").exists() else {"states": []}
        _STATE_RINGS = []
        for st in g["states"]:
            if not st["iso"].startswith("US-"):
                continue
            for ring in st["rings"]:
                xs = [c[0] for c in ring]
                ys = [c[1] for c in ring]
                _STATE_RINGS.append((st["iso"][3:], (min(xs), min(ys), max(xs), max(ys)), ring))
    for code, (x0, y0, x1, y1), ring in _STATE_RINGS:
        if not (x0 <= lon <= x1 and y0 <= lat <= y1):
            continue
        inside = False
        n = len(ring)
        for i in range(n):
            px1, py1 = ring[i]
            px2, py2 = ring[(i + 1) % n]
            if (py1 > lat) != (py2 > lat):
                x = px1 + (lat - py1) * (px2 - px1) / (py2 - py1)
                if x > lon:
                    inside = not inside
        if inside:
            return code
    return None


def slugify(s: str) -> str:
    s = s.lower().replace("&", " and ").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s)


# ------------------------------------------------------------ mini JSON Schema
# Enough of draft 2020-12 to enforce node.schema.json: type, const, enum,
# required, properties, additionalProperties, patternProperties, items,
# minItems/maxItems, minLength, pattern, $ref (local only).

_TYPES = {
    "object": dict, "array": list, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "null": type(None),
}


def _resolve(ref: str, root: dict):
    assert ref.startswith("#/"), ref
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def check(value, schema: dict, root: dict, path="$") -> list[str]:
    errs: list[str] = []
    if "$ref" in schema:
        return check(value, _resolve(schema["$ref"], root), root, path)
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            py = _TYPES[tt]
            if tt in ("integer", "number") and isinstance(value, bool):
                continue
            if isinstance(value, py):
                ok = True
                break
        if not ok:
            return [f"{path}: expected {t}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errs.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(value):
                errs += check(v, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in value:
                errs.append(f"{path}: missing required '{r}'")
        pats = schema.get("patternProperties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                errs += check(v, props[k], root, f"{path}.{k}")
                continue
            matched = False
            for pat, sub in pats.items():
                if re.search(pat, k):
                    matched = True
                    if sub:
                        errs += check(v, sub, root, f"{path}.{k}")
            if matched:
                continue
            if addl is False:
                errs.append(f"{path}: unexpected key '{k}'")
            elif isinstance(addl, dict):
                errs += check(v, addl, root, f"{path}.{k}")
    return errs


def validate_record(rec: dict, schema: dict | None = None) -> list[str]:
    schema = schema or jload(SCHEMA)
    clean = {k: v for k, v in rec.items() if not k.startswith("_")}
    return check(clean, schema, schema)
