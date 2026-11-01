"""Offline checks for scripts/crawl.py (no network). Run: python tests/test_crawl.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import crawl  # noqa: E402

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


_, vd = crawl.curated_names()
check("watcher knows a curated name", crawl.known(crawl.norm("Chili's"), vd), True)
check("watcher matches & versus and", crawl.known(crawl.norm("McCormick and Schmick's"), vd), True)
check("watcher flags a new name", crawl.known(crawl.norm("Totally New Grill"), vd), False)
check("colon row", crawl.extract("Helly Hansen: 35% off for military"), ("Helly Hansen", 35, False))
check("dash row", crawl.extract("Backcountry " + chr(0x2013) + " 20% Off"), ("Backcountry", 20, False))
check("offers row", crawl.extract("Dickies offers a 20% military discount online"), ("Dickies", 20, False))
check("table row", crawl.extract("24 | Helly Hansen | 35% off | Apparel"), ("Helly Hansen", 35, False))
check("up to flag", crawl.extract("Samsung: Up to 30% off via the program"), ("Samsung", 30, True))
check("junk word rejected", crawl.extract("Value: 50% of the price"), None)
check("broken spacing rejected", crawl.extract("T he Sculpt Society: 30% off"), None)
check("plus normalized", crawl.norm("Paramount+") == crawl.norm("Paramount Plus"), True)
check("parenthetical stripped", crawl.norm("HP (Hewlett Packard)") == crawl.norm("HP"), True)

if failures:
    print("CRAWL TESTS FAILED")
    print("\n".join(failures))
    sys.exit(1)
print("CRAWL TESTS PASSED (12 checks)")
