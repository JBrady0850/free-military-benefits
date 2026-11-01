"""Confirm literal backslash escapes survived file writes (house rule). Exit 1 on any miss."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BS = chr(92)
EXPECT = {
    "site/index.html": [BS + "r" + BS + "n", BS + "n" + BS + "n", "/" + BS + "s+/", "(/" + BS + BS + "/g",
                        BS + "$1", "/" + BS + "r?" + BS + "n/g", "^px" + BS + "b"],
    "scripts/crawl.py": ["up to" + BS + "s+", BS + "d{1,2}", BS + "(.*?" + BS + ")", BS + "s+(military"],
    "scripts/build_data.py": ['"' + BS + 'n"'],
}
bad = 0
for rel, needles in EXPECT.items():
    text = (ROOT / rel).read_bytes().decode("utf-8")
    if chr(0x2014) in text and rel != "tests/fixtures/bad.yaml":
        print(f"EM DASH in {rel}")
        bad += 1
    for n in needles:
        count = text.count(n)
        print(f"{'OK  ' if count else 'MISS'} {rel}: {n!r} x{count}")
        bad += 0 if count else 1
sys.exit(1 if bad else 0)
