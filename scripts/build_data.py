"""Validate the Earned Benefits dataset and build site/data.json.

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
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "data" / "schema" / "entry.schema.json"
SOURCES = {
    "hidden": ROOT / "data" / "hidden.yaml",
    "veterans-day": ROOT / "data" / "veterans-day-2026.yaml",
    "travel": ROOT / "data" / "travel.yaml",
    "free": ROOT / "data" / "free.yaml",
    "discount": ROOT / "data" / "discounts.yaml",
    "crawled": ROOT / "data" / "crawled.yaml",
}
WATCH = ROOT / "data" / "watch.json"
OUT = ROOT / "site" / "data.json"
EM_DASH = chr(0x2014)


def load_entries(sources: dict[str, Path]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    entries: list[dict] = []
    seen: set[str] = set()
    for kind, path in sources.items():
        if not path.exists():
            if kind != "crawled":
                errors.append(f"missing data file: {path.name}")
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        defaults = doc.get("defaults") or {}
        for raw in doc.get("entries") or []:
            entry = {**defaults, **raw, "kind": kind}
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
    return errors


def selftest() -> int:
    """R-007: the validator must reject a known-bad fixture, or it proves nothing."""
    bad = ROOT / "tests" / "fixtures" / "bad.yaml"
    entries, errors = load_entries({"fixture": bad})
    errors += validate(entries)
    expected = ["duplicate id", "is not one of", "does not match", "event_end is before", "em dash"]
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
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_version": date.today().isoformat(),
        "counts": counts,
        "total": len(entries),
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
