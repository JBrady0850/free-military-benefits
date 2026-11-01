"""Config checks for data/crawl_sources.yaml (no network). Run: python tests/test_sources.py"""
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
cfg = yaml.safe_load((ROOT / "data" / "crawl_sources.yaml").read_text(encoding="utf-8"))
failures = []
dirs = cfg.get("directories") or []
vd = cfg.get("veterans_day_lists") or []
for group, urls in (("directories", dirs), ("veterans_day_lists", vd)):
    for u in urls:
        if not u.startswith("https://"):
            failures.append(f"{group}: not https: {u}")
        if u != u.strip() or " " in u:
            failures.append(f"{group}: whitespace in url: {u}")
        if not urlparse(u).netloc:
            failures.append(f"{group}: no host: {u}")
    if len(set(urls)) != len(urls):
        failures.append(f"{group}: duplicate urls")
if set(dirs) & set(vd):
    failures.append("a url is in both lists")
if not isinstance(cfg.get("threshold"), int) or not 1 <= cfg["threshold"] <= 90:
    failures.append("threshold must be an integer from 1 to 90")
if str(cfg.get("veterans_day_year", "")).isdigit() is False:
    failures.append("veterans_day_year must be a year")
if (cfg.get("watch") or {}).get("veterans_day") not in vd:
    failures.append("the watched Veterans Day list must also be in veterans_day_lists")
if failures:
    print("SOURCE CONFIG FAILED")
    print("\n".join(failures))
    sys.exit(1)
print(f"SOURCE CONFIG OK ({len(dirs)} directories, {len(vd)} Veterans Day lists)")
