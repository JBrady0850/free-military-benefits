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
check("percent word", crawl.extract("Brooks Running: 25 percent off eligible full-price items"), ("Brooks Running", 25, False))
check("half off", crawl.extract("Fogo de Chao: half off the full churrasco"), ("Fogo de Chao", 50, False))
check("speculative row rejected", crawl.extract("Dave & Buster's: will likely offer 50% off on Veterans Day"), None)
check("last year's terms rejected", crawl.extract("Red Lobster: 30% off (2025 terms)"), None)
check("table header rejected", crawl.extract("Store | Discount | Eligibility"), None)
check("section title rejected", crawl.valid_brand("Retail Deals"), None)
check("registrable domain", crawl.domain("https://365.military.com/discounts/x"), crawl.domain("https://www.military.com/y"))
check("coffee slot", crawl.guess_slot("Dunkin'"), "coffee")
check("breakfast slot", crawl.guess_slot("Cracker Barrel Old Country Store"), "breakfast")
check("default slot", crawl.guess_slot("Texas Roadhouse"), "anytime")
check("car wash is a service", crawl.guess_category("Grace for Vets car wash"), "services")
check("Olive Garden is food, not an attraction", crawl.guess_category("Olive Garden"), "retail")
check("Butchart Gardens is an attraction", crawl.guess_category("Butchart Gardens"), "attractions")
from bs4 import BeautifulSoup  # noqa: E402
check("2025 list skipped", crawl.page_is_for(BeautifulSoup("<title>Veterans Day 2025 deals</title>", "html.parser"), "2026"), False)
check("2026 list kept", crawl.page_is_for(BeautifulSoup("<title>Veterans Day 2026 deals</title><h1>2026</h1>", "html.parser"), "2026"), True)
check("undated list kept", crawl.page_is_for(BeautifulSoup("<title>Veterans Day free meals</title>", "html.parser"), "2026"), True)

if failures:
    print("CRAWL TESTS FAILED")
    print("\n".join(failures))
    sys.exit(1)
print("CRAWL TESTS PASSED (29 checks)")
