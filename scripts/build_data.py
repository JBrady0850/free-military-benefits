"""Validate the Earned Benefits dataset and build site/data.json.

Usage:
    python scripts/build_data.py          # validate and write site/data.json
    python scripts/build_data.py --check  # validate and write; exit 1 on any error

Requires: pyyaml. Optional: jsonschema (schema validation is skipped with a
warning if it is not installed, but CI always installs it).
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
SOURCES = {"discount": ROOT / "data" / "discounts.yaml",
           "free": ROOT / "data" / "free.yaml"}
OUT = ROOT / "site" / "data.json"


def load_entries() -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    entries: list[dict] = []
    seen: set[str] = set()
    for kind, path in SOURCES.items():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for entry in doc.get("entries", []):
            entry = dict(entry)
            entry["kind"] = kind
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
        return errors
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    for entry in entries:
        body = {k: v for k, v in entry.items() if k != "kind"}
        for err in validator.iter_errors(body):
            errors.append(f"{entry.get('id', '?')}: {err.message}")
    return errors


def main() -> int:
    check = "--check" in sys.argv
    entries, errors = load_entries()
    errors += validate(entries)
    for entry in entries:
        if "—" in json.dumps(entry):
            errors.append(f"{entry.get('id', '?')}: em dash found (house convention forbids it)")
    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "data_version": date.today().isoformat(),
        "counts": {"discount": sum(1 for e in entries if e["kind"] == "discount"),
                   "free": sum(1 for e in entries if e["kind"] == "free")},
        "entries": entries,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} with {len(entries)} entries "
          f"({payload['counts']['discount']} discounts, {payload['counts']['free']} free).")
    for message in errors:
        print(f"ERROR: {message}")
    if errors and check:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
