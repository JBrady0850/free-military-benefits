"""Validate the Free Military Benefits dataset and build site/data.json.

Usage:
    python scripts/build_data.py            # validate and write site/data.json
    python scripts/build_data.py --check    # same; exit 1 on any error
    python scripts/build_data.py --selftest # prove the validator rejects tests/fixtures/bad.yaml

Each data file holds `entries:` and an optional `defaults:` block that is
merged under every entry, so repeated fields (dates, source, confidence) are
written once. data/crawled.yaml is produced by scripts/crawl.py.
No em dashes in any generated output (house convention).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "data" / "schema" / "entry.schema.json"
SOURCES = [
    ("hidden", ROOT / "data" / "hidden.yaml"),
    ("veterans-day", ROOT / "data" / "veterans-day-2026.yaml"),
    ("veterans-day", ROOT / "data" / "crawled-veterans-day.yaml"),
    ("travel", ROOT / "data" / "travel.yaml"),
    ("free", ROOT / "data" / "free.yaml"),
    ("discount", ROOT / "data" / "discounts.yaml"),
    ("crawled", ROOT / "data" / "crawled.yaml"),
]
GENERATED = {"crawled.yaml", "crawled-veterans-day.yaml"}
# John, 2026-11-01: every discount or offer needs at least two independent, verifiable sources.
TWO_SOURCE_KINDS = {"discount", "crawled", "veterans-day", "travel"}
# Multi-offer list pages: links get a text fragment so they open at, and highlight, the entry.
LIST_HOSTS = {"news.va.gov", "military.com", "calegion.org", "veteran.com", "usveteransmagazine.com",
              "themilitarywallet.com", "veteransdaydeals.us", "combatfitness.co", "freshcalendars.com",
              "cruisecritic.com", "travelmarketreport.com", "mymilitarybenefits.com", "militarycruisedeals.com",
              "legion-aux.org", "vetrafi.com", "dinova.com", "operationmilitarykids.org", "dealhack.com",
              "hip2save.com", "dealnews.com", "usmilitary.com", "wearethemighty.com", "sheerid.com",
              "militaryfamilies.com", "honestmos.com", "barbend.com", "fedsmith.com"}


def site(url: str) -> str:
    """Registrable domain, so 365.military.com and military.com count as one source."""
    host = re.sub(r"^www\.", "", url.split("/")[2].lower()) if "//" in url else url
    return ".".join(host.split(".")[-2:])


TRACKING = re.compile(r"([?&])(srsltid|utm_[a-z]+|gclid|fbclid|mc_[a-z]+)=[^&#]*", re.I)


def clean_url(url: str) -> str:
    """Drop tracking parameters and AMP markers so links are clean and stable."""
    out = TRACKING.sub(r"\1", url)
    out = re.sub(r"[?&]amp(=1)?(?=[&#]|$)", "", out)
    out = re.sub(r"[?&]+(#|$)", r"\1", re.sub(r"([?&])&+", r"\1", out))
    return out.replace("?&", "?")


STALE_DAYS = 90


def mark_stale(entry: dict, today: date) -> None:
    """Flag entries nobody has re-checked in STALE_DAYS so the page can say so."""
    try:
        seen = date.fromisoformat(str(entry.get("last_verified", "")))
    except ValueError:
        return
    if (today - seen).days > STALE_DAYS and not entry.get("auto"):
        entry["stale"] = True


def with_fragment(url: str, anchor: str) -> str:
    host = re.sub(r"^www\.", "", url.split("/")[2].lower()) if "//" in url else ""
    if "#" in url or not anchor or (host not in LIST_HOSTS and site(url) not in LIST_HOSTS):
        return url
    from urllib.parse import quote
    variants = [anchor] + ([anchor.replace("'", chr(0x2019))] if "'" in anchor else [])
    return url + "#:~:" + "&".join("text=" + quote(v, safe="") for v in variants)


def finalize_sources(entry: dict) -> None:
    """source_url first, then sources; add text fragments; drop duplicates of the same page."""
    anchor = entry.get("anchor") or re.sub(r"\(.*?\)", "", str(entry.get("name", ""))).strip()
    out, pages = [], set()
    for url in [entry.get("source_url", "")] + list(entry.get("sources") or []):
        url = clean_url(url)
        page = url.split("#")[0]
        if url and page not in pages:
            pages.add(page)
            out.append(with_fragment(url, anchor))
    if out:
        entry["source_url"], entry["sources"] = out[0], out[:12]
WATCH = ROOT / "data" / "watch.json"
OUT = ROOT / "site" / "data.json"
EM_DASH = chr(0x2014)
PCT_RANGE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:to|-)\s*(\d{1,2})\s*(?:percent|%)\s+(?:off|discount)", re.I)
PCT_ONE = re.compile(r"(up to\s+)?(?<!\d)(\d{1,2})\s*(?:percent|%)\s+(?:off|discount)", re.I)
HALF = re.compile(r"\bhalf[- ]price", re.I)


def derive_percent(entry: dict) -> None:
    """Fill `percent` (and `percent_up` for "up to" offers) from the offer text.

    Skipped for free items and for offers that lead with "Free", so a free
    admission with a family discount is not badged as a percentage deal.
    """
    offer = str(entry.get("offer", ""))
    if entry.get("percent"):
        if "percent_up" not in entry and re.search(r"up to\s+%d\s*(?:percent|%%)" % entry["percent"], offer, re.I):
            entry["percent_up"] = True
        return
    if entry.get("kind") == "free" or re.match(r"\s*free\b", offer, re.I):
        return
    m = PCT_RANGE.search(offer)
    if m:
        entry["percent"] = max(int(m.group(1)), int(m.group(2)))
        entry["percent_up"] = True
        return
    m = PCT_ONE.search(offer)
    if m:
        entry["percent"] = int(m.group(2))
        if m.group(1):
            entry["percent_up"] = True
        return
    if HALF.search(offer):
        entry["percent"] = 50


def load_entries(sources: list[tuple[str, Path]]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    entries: list[dict] = []
    seen: set[str] = set()
    for kind, path in sources:
        if not path.exists():
            if path.name not in GENERATED:
                errors.append(f"missing data file: {path.name}")
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        defaults = doc.get("defaults") or {}
        for raw in doc.get("entries") or []:
            entry = {**defaults, **raw, "kind": kind}
            derive_percent(entry)
            finalize_sources(entry)
            mark_stale(entry, date.today())
            eid = str(entry.get("id", "<missing id>"))
            if eid in seen:
                errors.append(f"duplicate id: {eid}")
            seen.add(eid)
            entries.append(entry)
    return entries, errors


def validate(entries: list[dict]) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        print("WARNING: jsonschema not installed; schema validation skipped.")
        jsonschema = None
    if jsonschema:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for entry in entries:
            body = {k: v for k, v in entry.items() if k != "kind"}
            for err in validator.iter_errors(body):
                errors.append(f"{entry.get('id', '?')}: {err.message}")
    for entry in entries:
        eid = entry.get("id", "?")
        start, end = entry.get("event_start"), entry.get("event_end")
        if start and end and str(end) < str(start):
            errors.append(f"{eid}: event_end is before event_start")
        if EM_DASH in json.dumps(entry, ensure_ascii=False):
            errors.append(f"{eid}: em dash found (house convention forbids it)")
        if entry.get("kind") in TWO_SOURCE_KINDS:
            n = len({site(u) for u in entry.get("sources") or []})
            if n < 2:
                errors.append(f"{eid}: needs two independent sources ({n} found)")
    return errors


def selftest() -> int:
    """R-007: the validator must reject a known-bad fixture, or it proves nothing."""
    bad = ROOT / "tests" / "fixtures" / "bad.yaml"
    entries, errors = load_entries([("discount", bad)])
    errors += validate(entries)
    expected = ["duplicate id", "is not one of", "does not match", "event_end is before", "em dash",
                "needs two independent sources"]
    missing = [e for e in expected if not any(e in msg for msg in errors)]
    print(f"selftest: {len(errors)} errors raised by the bad fixture")
    for message in errors:
        print(f"  {message}")
    if missing:
        print(f"SELFTEST FAILED: validator did not catch: {missing}")
        return 1
    print("SELFTEST PASSED: every planted defect was caught.")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    check = "--check" in sys.argv
    entries, errors = load_entries(SOURCES)
    errors += validate(entries)
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    watch = json.loads(WATCH.read_text(encoding="utf-8")) if WATCH.exists() else {}
    order = {k: i for i, (k, _) in enumerate(SOURCES)}
    entries.sort(key=lambda e: (order.get(e["kind"], 99), e["id"]))  # stable order keeps diffs small
    distinct_sites = {site(u) for e in entries for u in e.get("sources") or []}
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_version": date.today().isoformat(),
        "counts": counts,
        "total": len(entries),
        "stats": {"brand_confirmed": sum(1 for e in entries if e.get("verified_by") == "brand page"),
                  "over_20": sum(1 for e in entries if (e.get("percent") or 0) >= 21),
                  "stale": sum(1 for e in entries if e.get("stale")),
                  "distinct_sites": len(distinct_sites),
                  "source_pages": (watch.get("counts") or {}).get("sources_total", 0),
                  "source_pages_read": (watch.get("counts") or {}).get("sources_read", 0)},
        "watch": watch,
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    summary = ", ".join(f"{k} {v}" for k, v in counts.items())
    print(f"Wrote {OUT} with {len(entries)} entries ({summary}).")
    for message in errors:
        print(f"ERROR: {message}")
    if errors and check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
