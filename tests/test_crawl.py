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
s = crawl.summarize_offer(["Free Original Grand Slam from opening until noon, dine-in only.",
                           "Veterans get a free Original Grand Slam on Nov. 11 with proof of service."])
check("offer: free item agreed", s["primary"], "Free Original Grand Slam")
check("offer: dine-in kept", "Dine-in only" in s["quals"], True)
check("offer: proof kept", "Bring proof of service" in s["quals"], True)
check("offer: number before free", crawl.free_phrase("10 free boneless wings and fries with valid ID"), "10 free boneless wings and fries")
check("offer: stops at preposition", crawl.free_phrase("Free 12 oz. hot or iced brewed coffee for veterans"), "Free 12 oz. hot or iced brewed coffee")
check("offer: percent", crawl.summarize_offer(["20% off your entire purchase, in-store only"])["primary"], "20% off")
check("offer: bogo", crawl.summarize_offer(["Buy one entree, get one free with code VETS26"])["primary"].startswith("Buy one, get one free"), True)
r = crawl.summarize_offer(["Nov. 10-11: free Bloomin' Onion and drink", "November 10 through 11, a free Bloomin' Onion and a beverage"])
check("offer: date range when two lists agree", r["range"], ("2026-11-10", "2026-11-11"))
check("offer: one list's range not enough", crawl.summarize_offer(["Nov 8-11 20% off", "20% off on Veterans Day"])["range"], None)
check("offer: redeem by", crawl.summarize_offer(["Free combo card redeemable through Nov. 25"])["redeem"], "2026-11-25")
check("offer: eat free", crawl.summarize_offer(["Veterans eat free all day at participating locations"])["primary"], "Free meal")
check("offer: who", crawl.summarize_offer(["Veterans and active duty get a free donut"])["who"], ["active-duty", "veteran"])
check("offer: accented word kept", crawl.free_phrase("Free entrée from the Veterans Day menu"), "Free entrée")
check("offer: no empty phrase", crawl.free_phrase("Get it free. Details in store"), None)
from bs4 import BeautifulSoup  # noqa: E402
check("2025 list skipped", crawl.page_is_for(BeautifulSoup("<title>Veterans Day 2025 deals</title>", "html.parser"), "2026"), False)
check("2026 list kept", crawl.page_is_for(BeautifulSoup("<title>Veterans Day 2026 deals</title><h1>2026</h1>", "html.parser"), "2026"), True)
check("undated list kept", crawl.page_is_for(BeautifulSoup("<title>Veterans Day free meals</title>", "html.parser"), "2026"), True)

if failures:
    print("CRAWL TESTS FAILED")
    print("\n".join(failures))
    sys.exit(1)
check("emoji stripped from a heading name", crawl.clean("\u2615 Scooter's Coffee"), "Scooter's Coffee")
check("pictograph stripped", crawl.clean("\U0001F6D2 Kroger \U0001F1FA\U0001F1F8"), "Kroger")
# Carry forward: a list that refuses this run is replayed from its last good read, only when it is at most 7 days old
_real_fetch = crawl.fetch
crawl.fetch = lambda url, robots, report: None
_u1, _u2 = "https://example.org/vd-list/", "https://example.net/vd-list/"
crawl.MEM.clear(); crawl.CARRIED.clear()
crawl.MEM[_u1] = {"read_utc": crawl.RUN_UTC, "pairs": [["Testco Grill", "Free meal for veterans"], ["Othercafe", "Free coffee"]]}
crawl.MEM[_u2] = {"read_utc": crawl.RUN_UTC, "pairs": [["Testco Grill", "Free meal"]]}
_cfg = {"veterans_day_lists": [_u1, _u2], "veterans_day_year": 2026}
check("refused lists replay their last good read", [e["name"] for e in crawl.harvest_vd_lists(_cfg, {}, set(), "2026-11-02", [])[0]], ["Testco Grill"])
check("replayed lists are marked as kept", sorted(crawl.CARRIED), sorted([_u1, _u2]))
crawl.MEM[_u1]["read_utc"] = "2026-10-01T00:00Z"; crawl.CARRIED.clear()
check("a read older than 7 days is not replayed", [e["name"] for e in crawl.harvest_vd_lists(_cfg, {}, set(), "2026-11-02", [])[0]], [])
crawl.fetch = _real_fetch; crawl.MEM.clear(); crawl.CARRIED.clear()
# Linked-brand rows: the leading link names the brand (VA News year-round list)
_p = lambda html: BeautifulSoup(html, "html.parser").find(["p", "li"])
_x = lambda html: crawl.extract_linked(_p(html), crawl.clean(_p(html).get_text(" ")))
check("linked brand, Save N% off", _x('<p><a href="https://dogid.com/pages/military">DOG iD</a> Save 50% off engraved ID products.</p>'), ("DOG iD", 50, False))
check("linked brand, Up to N% off", _x('<p><a href="https://www.pods.com/military">PODS</a> Up to 30% off.</p>'), ("PODS", 30, True))
check("linked brand, N% Off", _x('<p><a href="https://apupabove.com/x">A Pup Above</a> 20% Off.</p>'), ("A Pup Above", 20, False))
check("a link inside a sentence is not a brand row", _x('<p>Read our <a href="https://x.com">guide</a> to save 50% off.</p>'), None)
# Same brand under two spellings, and names that never change (so ids stay put)
check("Helix and Helix Sleep are one brand", crawl.same_brand("Helix", "Helix Sleep"), True)
check("Delta and Delta Faucet are not", crawl.same_brand("Delta", "Delta Faucet"), False)
check("a short name never merges", crawl.same_brand("HP", "HP Inc"), False)
crawl.fetch = lambda url, robots, report: None
_d1, _d2 = "https://example.org/discounts/", "https://example.net/discounts/"
crawl.MEM.clear(); crawl.CARRIED.clear(); crawl.PREV_NAMES.clear()
crawl.MEM[_d1] = {"read_utc": crawl.RUN_UTC, "rows": [["Helix", 30, False, "home", []], ["Sirius XM", 25, False, "entertainment", []]]}
crawl.MEM[_d2] = {"read_utc": crawl.RUN_UTC, "rows": [["Helix Sleep", 30, False, "home", []], ["SiriusXM", 25, False, "entertainment", []]]}
crawl.PREV_NAMES["siriusxm"] = "SiriusXM"
_listed = sorted(e["name"] for e in crawl.harvest_directories({"directories": [_d1, _d2]}, {}, set(), 21, "2026-11-02", [])[0])
check("two spellings on two directories list once, and a listed name keeps its spelling", _listed, ["Helix Sleep", "SiriusXM"])
crawl.fetch = _real_fetch; crawl.MEM.clear(); crawl.CARRIED.clear(); crawl.PREV_NAMES.clear()
# Veterans Day categories: a discount store is never filed under free meals
crawl.KINDS.clear()
check("a store with a percent discount is retail", crawl.vd_category("Five Below", "10% off", []), "retail")
check("a furniture store is retail", crawl.vd_category("Ashley", "5% off", ["5% off furniture"]), "retail")
check("a free dish is food", crawl.vd_category("Fazoli's", "Free Spaghetti", []), "food")
check("a restaurant discount on the meal is food", crawl.vd_category("Culver's", "10% off", ["10% off your meal"]), "food")
crawl.KINDS["red roof"] = "travel"
check("the store snapshot's business type wins", crawl.vd_category("Red Roof", "10% off", ["10% off stays"]), "travel")
crawl.KINDS.clear()
crawl.KINDS["7-eleven"] = "retail"; crawl.KINDS["target"] = "retail"
check("a free coffee at a convenience store is food", crawl.vd_category("7-Eleven", "Free coffee", []), "food")
check("a percent off at a department store is retail", crawl.vd_category("Target", "20% off", []), "retail")
check("a theme park is an attraction", crawl.vd_category("Disney", "Discounted tickets", []), "attractions")
check("a ferry is travel", crawl.vd_category("NY Waterway", "Free rides", []), "travel")
check("a restaurant named Kitchen is food", crawl.vd_category("BRAVO! Italian Kitchen", "Half off an entree", []), "food")
check("a free Italian ice is food", crawl.vd_category("Jeremiah's Italian Ice", "Free Italian ice", []), "food")
crawl.KINDS.clear()
check("zero-width characters are stripped", crawl.clean("\u200b Newk's Eatery"), "Newk's Eatery")
# The published name survives when a new list uses a shorter spelling
crawl.fetch = lambda url, robots, report: None
_v1, _v2 = "https://example.org/vd2/", "https://example.net/vd2/"
crawl.MEM.clear(); crawl.CARRIED.clear(); crawl.PREV_NAMES.clear()
crawl.MEM[_v1] = {"read_utc": crawl.RUN_UTC, "pairs": [["Black Angus Steakhouse", "Free meal"]]}
crawl.MEM[_v2] = {"read_utc": crawl.RUN_UTC, "pairs": [["Black Angus", "Free meal"]]}
crawl.PREV_NAMES[crawl.norm("Black Angus Steakhouse")] = "Black Angus Steakhouse"
_n = [e["name"] for e in crawl.harvest_vd_lists({"veterans_day_lists": [_v1, _v2], "veterans_day_year": 2026}, {}, set(), "2026-11-08", [])[0]]
check("a shorter spelling on a new list keeps the published name", _n, ["Black Angus Steakhouse"])
crawl.fetch = _real_fetch; crawl.MEM.clear(); crawl.CARRIED.clear(); crawl.PREV_NAMES.clear()
print("CRAWL TESTS PASSED (69 checks)")
