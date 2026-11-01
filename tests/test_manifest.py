"""Standalone app identity. The site shares jbrady0850.github.io with other apps, so the manifest id must resolve to
this app's own folder (an id of "./" or "/" resolves to the whole site and merges installs), and the service worker
may only delete caches it owns."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

SITE = Path(__file__).resolve().parent.parent / "site"
ORIGIN = "https://jbrady0850.github.io"
APP = ORIGIN + "/free-military-benefits/"
errors = []

m = json.loads((SITE / "manifest.webmanifest").read_text(encoding="utf-8"))
start = urljoin(APP + "manifest.webmanifest", m.get("start_url", "."))
resolved = urljoin(ORIGIN + "/", m["id"]) if "id" in m else start  # spec: id resolves against start_url's origin
if resolved != APP:
    errors.append(f"manifest id resolves to {resolved}, not {APP}")
if not urljoin(APP + "manifest.webmanifest", m.get("scope", ".")).startswith(APP):
    errors.append("manifest scope leaves the app folder")
if not start.startswith(APP):
    errors.append("start_url leaves the app folder")
sw = (SITE / "sw.js").read_text(encoding="utf-8")
if not re.search(r'const PREFIX = "fmb-"', sw) or "k.startsWith(PREFIX)" not in sw:
    errors.append("sw.js must delete only caches named fmb-*")
page = (SITE / "index.html").read_text(encoding="utf-8").lower()
for other in ("road trip planner", "road-trip-planner", "nhl daily", "nhl-daily-analytics", "daily-brief-sitrep", "fers-planning-project", "fers planner"):
    if other in page:
        errors.append(f"index.html mentions another project: {other}")
if errors:
    print("MANIFEST TEST FAILED:\n  " + "\n  ".join(errors))
    sys.exit(1)
print("MANIFEST TEST PASSED (id, scope, start_url, cache prefix, no links to other projects)")
