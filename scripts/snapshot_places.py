"""Build site/places.json so Near Me runs entirely on the visitor's device.

Sources (all free and open):
  - All the Places weekly run (CC0): chain store locations scraped from official store
    locators, plus VA facilities (spider department_veterans_affairs, from api.va.gov).
  - OpenStreetMap via Overpass (ODbL): commissaries and exchanges, when a server answers.
  - Wikidata (CC0): U.S. military installations, used only if Overpass is unavailable.
A failed source keeps the previous snapshot's section instead of emptying it.

Usage: python scripts/snapshot_places.py [--quick]   (--quick skips Overpass)
"""
from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "places.json"
UA = {"User-Agent": "FreeMilitaryBenefitsBot/0.3 (+https://github.com/JBrady0850/free-military-benefits)"}
ATP_LATEST = "https://data.alltheplaces.xyz/runs/latest.json"
ATP_OUTPUT = "https://alltheplaces-data.openaddresses.io/runs/{run}/output/{spider}.geojson"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
BASES_Q = ('[out:json][timeout:240];area["ISO3166-1"="US"][admin_level=2]->.us;'
           '(nwr["shop"~"^(supermarket|department_store|general|convenience|mall|wholesale)$"]'
           '["name"~"(commissary|exchange)",i](area.us););out center tags;')
WIKIDATA_Q = """SELECT ?item ?itemLabel ?coord WHERE {
  VALUES ?type { wd:Q245016 wd:Q1324633 wd:Q695850 wd:Q18691599 }
  ?item wdt:P31 ?type; wdt:P17 wd:Q30; wdt:P625 ?coord.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } }"""
FOREIGN = re.compile(r"_(?!us$)[a-z]{2}$")


ALIASES = {"7eleven": "seveneleven"}  # brand spelled as digits where the spider spells it out


def norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()  # Chão == Chao
    s = s.lower().replace(chr(0x2019), "'").replace("&", " ").replace("+", " plus ")
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\band\b|^the\s+", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def low_name(s: str) -> str:
    return " ".join(s.lower().replace(chr(0x2019), "'").split())


def wanted_brands() -> dict[str, str]:
    """lowName -> display brand, from every dataset entry that names a store brand."""
    out: dict[str, str] = {}
    in_store = {"retail", "apparel", "outdoor", "health", "home-improvement", "attractions", "food"}
    for fname in ("veterans-day-2026.yaml", "crawled-veterans-day.yaml", "discounts.yaml", "crawled.yaml",
                  "free.yaml", "travel.yaml"):
        path = ROOT / "data" / fname
        if not path.exists():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cat_default = (doc.get("defaults") or {}).get("category")
        for e in doc.get("entries") or []:
            for b in e.get("osm_brand") or []:
                out[low_name(b)] = b
            if fname == "crawled.yaml" and (e.get("category") or cat_default) in in_store:
                name = re.sub(r"\(.*?\)", "", e["name"]).strip()
                out[low_name(name)] = name
    return out


def match_spiders(spiders: list[str], brands: dict[str, str]) -> dict[str, list[str]]:
    """brand lowName -> candidate U.S. spider names (exact or prefix match on normalized names)."""
    # U.S.-capable: names a _us part anywhere (seven_eleven_ca_us, smoothie_king_ky_us_tt) or carries no country code
    us = [s for s in spiders if re.search(r"_us(_|$)", s) or not FOREIGN.search(s)]
    base = {s: norm(re.sub(r"(_[a-z]{2})+$", "", s).replace("_", " ")) for s in us}  # drop trailing country/state codes
    out: dict[str, list[str]] = {}
    for low, display in brands.items():
        key = norm(display)
        key = ALIASES.get(key, key)
        if len(key) < 3:
            continue
        exact = [s for s, b in base.items() if b == key]
        loose = [s for s, b in base.items() if len(b) >= 5 and len(key) >= 5 and (b.startswith(key) or key.startswith(b))]
        if exact or loose:
            out[low] = (exact or loose)[:3]
    return out


def fetch_spider(runs: list[str], spider: str) -> list[dict]:
    """Latest run first; a spider that came back empty falls back to earlier weekly runs."""
    for run in runs:
        try:
            r = requests.get(ATP_OUTPUT.format(run=run, spider=spider), headers=UA, timeout=120)
            feats = r.json().get("features", []) if r.status_code == 200 else []
        except (requests.RequestException, ValueError):
            feats = []
        if feats:
            return feats
    return []


def us_point(f: dict) -> tuple[int, int] | None:
    g = f.get("geometry") or {}
    if g.get("type") != "Point":
        return None
    lon, lat = g["coordinates"][:2]
    country = (f.get("properties") or {}).get("addr:country", "US")
    if country not in ("US", "PR", "GU", "VI") or not (-180 < lon < -60 or lon > 140) or not (13 < lat < 72):
        return None
    return round(lat * 1000), round(lon * 1000)


def brand_ok(f: dict, display: str) -> bool:
    props = f.get("properties") or {}
    b = norm(props.get("brand") or props.get("name") or "")
    k = norm(display)
    b, k = ALIASES.get(b, b), ALIASES.get(k, k)
    b = ALIASES.get(b, b) if b != "seveneleven" else b
    return bool(b) and (b == k or b.startswith(k) or k.startswith(b))


def overpass_bases() -> list[list] | None:
    for url in OVERPASS:
        for attempt in range(2):
            try:
                r = requests.post(url, data={"data": BASES_Q}, headers=UA, timeout=300)
                if r.status_code == 200:
                    rows = []
                    for el in r.json().get("elements", []):
                        la = el.get("lat", (el.get("center") or {}).get("lat"))
                        lo = el.get("lon", (el.get("center") or {}).get("lon"))
                        name = (el.get("tags") or {}).get("name", "")
                        if la is not None and name:
                            rows.append([round(la * 1000), round(lo * 1000), name])
                    return rows
            except (requests.RequestException, ValueError):
                pass
            time.sleep(20 * (attempt + 1))
    return None


def wikidata_installations() -> list[list] | None:
    try:
        r = requests.get("https://query.wikidata.org/sparql", params={"query": WIKIDATA_Q, "format": "json"},
                         headers=UA, timeout=120)
        rows, seen = [], set()
        for b in r.json()["results"]["bindings"]:
            m = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", b["coord"]["value"])
            name = b["itemLabel"]["value"]
            if m and not re.match(r"^Q\d+$", name) and name not in seen:
                seen.add(name)
                rows.append([round(float(m.group(2)) * 1000), round(float(m.group(1)) * 1000), name])
        return rows
    except (requests.RequestException, ValueError, KeyError):
        return None


def main() -> int:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    latest = requests.get(ATP_LATEST, headers=UA, timeout=60).json()
    run = latest["run_id"]
    stats = requests.get(latest["stats_url"], headers=UA, timeout=120).json()
    spiders = [r["spider"] for r in stats["results"]]
    history = requests.get("https://data.alltheplaces.xyz/runs/history.json", headers=UA, timeout=60).json()
    runs = [run] + [h["run_id"] for h in history if h["run_id"] < run][-12:][::-1]  # a broken spider falls back up to 12 weeks
    brands = wanted_brands()
    matches = match_spiders(spiders, brands)
    print(f"ATP run {run} (fallbacks {runs[1:]}): {len(spiders)} spiders; {len(brands)} wanted brands; {len(matches)} matched")
    jobs = sorted({s for ss in matches.values() for s in ss} | {"department_veterans_affairs"})
    with ThreadPoolExecutor(max_workers=6) as pool:
        feats = dict(zip(jobs, pool.map(lambda s: fetch_spider(runs, s), jobs)))
    out_brands: dict[str, list] = {}
    for low, ss in matches.items():
        pts = {us_point(f) for s in ss for f in feats.get(s, []) if brand_ok(f, brands[low])}
        pts.discard(None)
        if pts:
            out_brands[low] = sorted(pts)
    unmatched = sorted(set(brands) - set(out_brands))
    va = []
    for f in feats.get("department_veterans_affairs", []):
        p = us_point(f)
        if p:
            va.append([p[0], p[1], (f.get("properties") or {}).get("name", "VA facility")])
    bases = None if "--quick" in sys.argv else overpass_bases()
    bases_kind = "stores"
    if bases is None:
        bases, bases_kind = wikidata_installations(), "installations"
    if bases is None:
        bases, bases_kind = old.get("bases", []), old.get("bases_kind", "none")
        print("WARNING: commissary/exchange sources unavailable; kept previous snapshot section")
    doc = {
        "generated": date.today().isoformat(),
        "atp_run": run,
        "bases_kind": bases_kind,
        "brands": out_brands,
        "va": va or old.get("va", []),
        "bases": bases,
        "credits": "Chains and VA facilities: All the Places (CC0). Bases: OpenStreetMap (ODbL) or Wikidata (CC0).",
    }
    OUT.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    points = sum(len(v) for v in out_brands.values())
    print(f"Wrote {OUT.name}: {len(out_brands)} brands, {points} store points, {len(va)} VA facilities, "
          f"{len(bases)} bases ({bases_kind}), {OUT.stat().st_size} bytes")
    print("Brands with no location data:", ", ".join(unmatched[:60]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
