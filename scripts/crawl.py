"""Harvest military discounts of THRESHOLD percent or more from public directory pages.

Writes data/crawled.yaml (auto-listed brands) and data/watch.json (Veterans Day
names announced on VA News that the curated list does not have yet).

Rules this crawler keeps:
  - robots.txt is checked for every host before any page is read.
  - Only facts are stored: brand, percentage, and the page that reported it.
  - Brands already curated by hand in data/*.yaml are skipped.
  - Every auto entry is labeled community-reported with its crawl date.

Usage: python scripts/crawl.py
Requires: requests, beautifulsoup4, pyyaml.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "crawl_sources.yaml"
OUT = ROOT / "data" / "crawled.yaml"
WATCH_OUT = ROOT / "data" / "watch.json"
CURATED = ["discounts.yaml", "hidden.yaml", "travel.yaml", "free.yaml", "veterans-day-2026.yaml"]
UA = "EarnedBenefitsBot/0.2 (+https://github.com/JBrady0850/earned-benefits)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

DASHES = chr(0x2013) + chr(0x2014)
QUOTES = {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
PCT = re.compile(r"(?P<up>up to\s+)?(?P<pct>\d{1,2})\s?%", re.I)
SEP = re.compile(r"^\s*(?P<brand>[A-Z0-9][^:|" + DASHES + r"]{1,48}?)\s*(?::|\s[-" + DASHES + r"]\s)\s*(?P<rest>.{2,200})$")
OFFERS = re.compile(r"^\s*(?P<brand>[A-Z0-9][\w&'.+!\- ]{1,48}?)\s+(?:offers|gives|provides|extends)\s+"
                    r"(?:an?\s+)?(?:exclusive\s+)?(?:discount\s+of\s+)?(?P<up>up to\s+)?(?P<pct>\d{1,2})\s?%")
STOP_START = ("get ", "save ", "enjoy ", "score ", "up to", "free ", "military", "veteran", "active",
              "discount", "offer", "top ", "best ", "all ", "the best", "how ", "what ", "why ", "who ",
              "is ", "are ", "do ", "does ", "can ", "this ", "these ", "our ", "your ", "you ", "if ",
              "when ", "note", "tip", "step", "bonus", "update", "related", "source", "average", "typical")
TRAILING = re.compile(r"\s+(military|veteran|veterans|discount|discounts|program|deal|deals|offer|offers|"
                      r"promo|code|coupon|sale)\b.*$", re.I)
STOP_EXACT = {"value", "price", "prices", "savings", "total", "amount", "discount", "discounts", "military"}
CATEGORY_WORDS = [
    ("attractions", ("zoo", "museum", "garden", "theatre", "theater", "theme park", "trampoline", "aquarium",
                     "six flags", "ticket", "racing experience", "tough mudder")),
    ("education", ("universit", "college", "school", "course", "codecademy", "berklee", "language", "pimsleur")),
    ("health", ("lasik", "vision", "eye", "optical", "dental", "oral care", "pharmacy", "cvs", "medical",
                "wellness", "cbd", "lenscrafters")),
    ("travel", ("travel", "hotel", "resort", "lodge", "airline", "car rental", "truck rental", "vacation", "cruise",
                "avis", "budget", "hertz", "sixt")),
    ("technology", ("tech", "electronic", "software", "phone", "wireless", "computer", "laptop", "streaming",
                    "audio", "siriusxm", "hulu", "paramount", "tidal", "samsung", "t-mobile", "at&t")),
    ("food", ("food", "restaurant", "dining", "meal kit", "meal", "hellofresh", "home chef", "harry & david")),
    ("home-improvement", ("furniture", "mattress", "sleep", "appliance", "home goods", "kitchen", "mat")),
    ("outdoor", ("outdoor", "gear", "fitness", "gym", "yoga", "golf", "hunt", "fish", "camp", "snowboard")),
    ("apparel", ("cloth", "apparel", "shoe", "boot", "fashion", "jacket", "khaki", "sneaker")),
]
WATCH_IGNORE = {"veteransday", "discounts", "nationalparksservice", "nationalparkservice"}


def clean(text: str) -> str:
    for bad, good in QUOTES.items():
        text = text.replace(bad, good)
    return " ".join(text.split())


def norm(name: str) -> str:
    name = clean(name).lower()
    name = re.sub(r"\(.*?\)", " ", name)
    name = name.replace("+", " plus ").replace("&", " ")
    name = re.sub(r"\band\b", " ", name)
    name = re.sub(r"^\s*the\s+", "", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", clean(name).lower()).strip("-")[:50]


def valid_brand(brand: str) -> str | None:
    brand = clean(brand).strip(" .,-*")
    brand = TRAILING.sub("", brand).strip(" .,-*")
    low = brand.lower()
    if not 2 <= len(brand) <= 40 or len(brand.split()) > 5:
        return None
    if low.startswith(STOP_START) or low in STOP_EXACT or "%" in brand or brand.isdigit():
        return None
    if re.match(r"^[A-Za-z] [a-z]", brand):
        return None  # broken spacing in the source page, for example "T he"
    if not re.search(r"[A-Za-z]{2}", brand):
        return None
    return brand


def guess_category(context: str) -> str:
    low = context.lower()
    for cat, words in CATEGORY_WORDS:
        if any(w in low for w in words):
            return cat
    return "retail"


def allowed(url: str, cache: dict) -> bool:
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers=HEADERS, timeout=20)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
        cache[host] = rp
    return cache[host].can_fetch(UA, url)


def blocks(soup: BeautifulSoup):
    """Yield (text, heading context) for list items, paragraphs, headings and table rows."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    heading = ""
    for el in soup.find_all(["h1", "h2", "h3", "h4", "li", "p", "tr"]):
        if el.name in ("h1", "h2", "h3", "h4"):
            heading = clean(el.get_text(" "))
            yield heading, heading
        elif el.name == "tr":
            cells = [clean(c.get_text(" ")) for c in el.find_all(["td", "th"])]
            yield " | ".join(cells), heading
        else:
            yield clean(el.get_text(" ")), heading


def extract(text: str) -> tuple[str, int, bool] | None:
    if "|" in text:
        cells = [c.strip() for c in text.split("|")]
        for i, cell in enumerate(cells):
            m = PCT.search(cell)
            if m:
                for prev in reversed(cells[:i]):
                    brand = valid_brand(prev)
                    if brand:
                        return brand, int(m.group("pct")), bool(m.group("up"))
                return None
        return None
    m = OFFERS.match(text)
    if m:
        brand = valid_brand(m.group("brand"))
        return (brand, int(m.group("pct")), bool(m.group("up"))) if brand else None
    m = SEP.match(text)
    if m:
        p = PCT.search(m.group("rest")[:90])
        brand = valid_brand(m.group("brand"))
        if p and brand:
            return brand, int(p.group("pct")), bool(p.group("up"))
    return None


def curated_names() -> tuple[set[str], set[str]]:
    all_names, vd_names = set(), set()
    for fname in CURATED:
        path = ROOT / "data" / fname
        if not path.exists():
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for e in doc.get("entries") or []:
            for n in [e.get("name", "")] + list(e.get("osm_brand") or []):
                key = norm(n)
                if key:
                    all_names.add(key)
                    if fname.startswith("veterans-day"):
                        vd_names.add(key)
    return all_names, vd_names


def known(key: str, names: set[str]) -> bool:
    return any(key == n or (len(key) > 3 and (n.startswith(key) or key.startswith(n))) for n in names)


def fetch(url: str, robots: dict, report: list) -> BeautifulSoup | None:
    if not allowed(url, robots):
        report.append(f"SKIP robots.txt disallows: {url}")
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        report.append(f"FAIL {type(exc).__name__}: {url}")
        return None
    if r.status_code != 200:
        report.append(f"FAIL HTTP {r.status_code}: {url}")
        return None
    return BeautifulSoup(r.text, "html.parser")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    threshold = int(cfg.get("threshold", 20))
    today = date.today().isoformat()
    all_names, vd_names = curated_names()
    robots: dict = {}
    report: list[str] = []
    found: dict[str, dict] = {}
    for url in cfg.get("directories") or []:
        soup = fetch(url, robots, report)
        if soup is None:
            continue
        hits = 0
        for text, heading in blocks(soup):
            got = extract(text)
            if not got:
                continue
            brand, pct, up = got
            if pct < threshold or pct > 90:
                continue
            key = norm(brand)
            if not key or known(key, all_names):
                continue
            hits += 1
            cat = guess_category(text)
            if cat == "retail":
                cat = guess_category(heading)
            row = found.setdefault(key, {"name": brand, "percent": pct, "up": up, "sources": [],
                                         "category": cat})
            if pct > row["percent"]:
                row.update(percent=pct, up=up)
            if url not in row["sources"]:
                row["sources"].append(url)
        report.append(f"OK {hits} qualifying rows: {url}")
        time.sleep(2)
    entries = []
    for key, row in sorted(found.items(), key=lambda kv: (-kv[1]["percent"], kv[1]["name"].lower())):
        domains = ", ".join(sorted({urlparse(u).netloc.replace("www.", "") for u in row["sources"]}))
        amount = ("up to " if row["up"] else "") + f"{row['percent']} percent"
        entries.append({
            "id": "auto-" + slug(row["name"]),
            "name": row["name"],
            "category": row["category"],
            "offer": f"Reported {amount} military discount (listed by {domains}). Confirm current terms and who qualifies at the brand before buying.",
            "percent": row["percent"],
            "source_url": row["sources"][0],
            "sources": row["sources"][:12],
        })
    seen, unique = set(), []
    for e in entries:
        if e["id"] not in seen:
            seen.add(e["id"])
            unique.append(e)
    doc = {
        "defaults": {"eligibility": ["military"], "verification": ["see-source"], "scope": "online",
                     "last_verified": today, "confidence": "community", "auto": True},
        "entries": unique,
    }
    header = (f"# GENERATED by scripts/crawl.py on {today}. Do not edit by hand; curated entries win.\n"
              f"# Brands reported at {threshold} percent or more by the directories in crawl_sources.yaml.\n")
    OUT.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=False, width=200), encoding="utf-8")
    report.append(f"WROTE {len(unique)} auto-listed brands at {threshold}+ percent to {OUT.name}")
    watch_vd(cfg, robots, vd_names, today, report)
    print("\n".join(report))
    return 0


def watch_vd(cfg: dict, robots: dict, vd_names: set[str], today: str, report: list) -> None:
    url = (cfg.get("watch") or {}).get("veterans_day")
    if not url:
        return
    soup = fetch(url, robots, report)
    if soup is None:
        return
    body = soup.find("article") or soup
    new = []
    for p in body.find_all("p"):
        first = p.find(["a", "strong"])
        if not first or not clean(p.get_text(" ")).startswith(clean(first.get_text(" "))[:20]):
            continue
        name = clean(first.get_text(" ")).strip(" :")
        key = norm(re.sub(r"\(.*?\)", "", name))
        if key in WATCH_IGNORE:
            continue
        if 2 < len(name) < 60 and key and not known(key, vd_names) and name not in new:
            new.append(name)
    WATCH_OUT.write_text(json.dumps({"checked": today, "source": url, "new_names": new[:40]}, indent=1) + "\n",
                         encoding="utf-8")
    report.append(f"WATCH {len(new)} Veterans Day names on VA News not yet curated")


if __name__ == "__main__":
    sys.exit(main())
