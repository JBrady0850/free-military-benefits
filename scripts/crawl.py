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
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data" / "crawl_sources.yaml"
OUT = ROOT / "data" / "crawled.yaml"
VD_OUT = ROOT / "data" / "crawled-veterans-day.yaml"
WATCH_OUT = ROOT / "data" / "watch.json"
MEMORY_OUT = ROOT / "data" / "source_memory.json"  # each source's last good read, parsed
MAX_CARRY_DAYS = 7  # a source that refuses (HTTP 403 to GitHub's servers, say) is replayed from a read this recent
CURATED = ["discounts.yaml", "hidden.yaml", "travel.yaml", "free.yaml", "veterans-day-2026.yaml"]
UA = "FreeMilitaryBenefitsBot/0.5 (+https://github.com/JBrady0850/free-military-benefits)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}

DASHES = chr(0x2013) + chr(0x2014)
QUOTES = {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
PCT = re.compile(r"(?P<up>up to\s+)?(?P<pct>\d{1,2})\s?(?:%|percent\b)|(?P<half>\bhalf[ -](?:off|price))", re.I)
SEP = re.compile(r"^\s*(?P<brand>[A-Z0-9][^:|" + DASHES + r"]{1,48}?)\s*(?::|\s[-" + DASHES + r"]\s)\s*(?P<rest>.{2,200})$")
OFFERS = re.compile(r"^\s*(?P<brand>[A-Z0-9][\w&'.+!\- ]{1,48}?)\s+(?:offers|gives|provides|extends|takes)\s+"
                    r"(?:an?\s+)?(?:exclusive\s+|generous\s+|flat\s+)?(?:discount\s+of\s+)?(?P<up>up to\s+)?(?P<pct>\d{1,2})\s?(?:%|percent\b)")
# Speculative wording: last year's terms restated as a guess. Never a source for this year.
SPECULATIVE = re.compile(r"\b(will likely|likely|we anticipate|anticipated?|expect(?:ed|s)? to|predicted|pending|"
                         r"not (?:yet )?(?:announced|confirmed)|2025 (?:offer|terms|deal)|last year'?s|in years past|has not announced)\b", re.I)


def pct_of(m) -> tuple[int, bool]:
    """(percent, up-to flag) from a PCT match; 'half off' counts as 50."""
    if m.group("half"):
        return 50, False
    return int(m.group("pct")), bool(m.group("up"))
STOP_START = ("get ", "save ", "enjoy ", "score ", "up to", "free ", "military", "veteran", "active",
              "discount", "offer", "top ", "best ", "all ", "the best", "how ", "what ", "why ", "who ",
              "is ", "are ", "do ", "does ", "can ", "this ", "these ", "our ", "your ", "you ", "if ",
              "when ", "note", "tip", "step", "bonus", "update", "related", "source", "average", "typical")
TRAILING = re.compile(r"\s+(military|veteran|veterans|discount|discounts|program|deal|deals|offer|offers|"
                      r"promo|code|coupon|sale)\b.*$", re.I)
STOP_EXACT = {"value", "price", "prices", "savings", "total", "amount", "discount", "discounts", "military"}
CATEGORY_WORDS = [
    ("services", ("car wash", "haircut", "oil change", "salon", "barber", "tire", "auto parts", "autonation", "safelite",
                  "pep boys", "insurance", "moving", "storage", "cleaning")),
    ("attractions", ("zoo", "museum", "botanical", "gardens", "theatre", "theater", "theme park", "trampoline", "aquarium",
                     "six flags", "ticket", "racing experience", "tough mudder", "cinema", "movie")),
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
    ("apparel", ("cloth", "apparel", "shoe", "boot", "fashion", "jacket", "khaki", "sneaker", "jewel", "diamond",
                 "sunglass", "eyewear", "watch", "denim", "jeans", "underwear")),
]
HEADER_NAMES = {"store", "brand", "company", "retailer", "restaurant", "discount", "deal", "offer", "who", "eligibility",
                "verification", "how to verify", "category", "item name", "website", "notes", "status", "2026 status",
                "quick answer", "summary table", "summary", "coffee and treats", "grocery and retail", "retail and grocery",
                "free meals", "year-round", "all year", "miscellaneous", "entertainment", "travel", "home", "beauty",
                "retail", "grocery", "shopping", "dining", "food", "services", "attractions", "restaurants", "clothing",
                "apparel", "technology", "electronics", "automotive", "car care", "health", "fitness", "outdoors"}
WATCH_IGNORE = {"veteransday", "discounts", "nationalparksservice", "nationalparkservice"}


SYMBOLS = re.compile("[\u2600-\u27BF\U0001F000-\U0001FAFF\uFE0F\u200B-\u200D\uFEFF]")  # emoji and pictographs some lists put in headings


def clean(text: str) -> str:
    for bad, good in QUOTES.items():
        text = text.replace(bad, good)
    text = SYMBOLS.sub(" ", text)  # "☕ Scooter's Coffee" -> "Scooter's Coffee"
    return " ".join(text.split())


def norm(name: str) -> str:
    import unicodedata
    name = unicodedata.normalize("NFKD", clean(name)).encode("ascii", "ignore").decode().lower()  # Chao == Chão
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
    if low.startswith(STOP_START) or low in STOP_EXACT or low in HEADER_NAMES or "%" in brand or brand.isdigit():
        return None
    if re.search(r"\b(deals?|freebies|discounts?|savings|checklist|faq|table|guide)$", low):
        return None  # a section title, not a business
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


def blocks(soup: BeautifulSoup, with_el: bool = False):
    """Yield (text, heading context[, element]) for list items, paragraphs, headings and table rows."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    heading = ""
    for el in soup.find_all(["h1", "h2", "h3", "h4", "li", "p", "tr"]):
        if el.name in ("h1", "h2", "h3", "h4"):
            heading = clean(el.get_text(" "))
            text = heading
        elif el.name == "tr":
            text = " | ".join(clean(c.get_text(" ")) for c in el.find_all(["td", "th"]))
        else:
            text = clean(el.get_text(" "))
        yield (text, heading, el) if with_el else (text, heading)


def extract(text: str) -> tuple[str, int, bool] | None:
    if SPECULATIVE.search(text):
        return None
    if "|" in text:
        cells = [c.strip() for c in text.split("|")]
        for i, cell in enumerate(cells):
            m = PCT.search(cell)
            if m:
                pct, up = pct_of(m)
                for prev in reversed(cells[:i]):
                    brand = valid_brand(prev)
                    if brand:
                        return brand, pct, up
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
            pct, up = pct_of(p)
            return brand, pct, up
    return None


LEAD_OFFER = re.compile(r"^(?:save\b|savings\b|up to\b|get\b|receive\b|enjoy\b|\d{1,2}\s?(?:%|percent))", re.I)


def extract_linked(el, text: str) -> tuple[str, int, bool] | None:
    """A paragraph or list item that opens with a link naming the brand, then the offer:
    '<a href=brand page>DOG iD</a> Save 50% off engraved ID products.' (the VA News year-round list).
    Plain text cannot show where the brand ends; the link can."""
    if el is None or el.name not in ("p", "li") or SPECULATIVE.search(text):
        return None
    a = el.find("a", href=True)
    if a is None:
        return None
    name = clean(a.get_text(" "))
    if not name or not text.startswith(name):
        return None
    rest = text[len(name):].lstrip(" :-\u2013\u2014")
    if not LEAD_OFFER.match(rest):
        return None
    p = PCT.search(rest[:90])
    brand = valid_brand(name)
    if not (p and brand):
        return None
    pct, up = pct_of(p)
    return brand, pct, up


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


PAGE_CACHE: dict[str, BeautifulSoup | None] = {}
FAILED: list[dict] = []
LAST_HIT: dict[str, float] = {}


from datetime import datetime as _dtm, timedelta as _tdm, timezone as _tzm  # noqa: E402

RUN_UTC = _dtm.now(_tzm.utc).strftime("%Y-%m-%dT%H:%MZ")
MEM: dict = {}      # url -> {"read_utc": ..., "pairs": [...]} or {"read_utc": ..., "rows": [...]}
CARRIED: dict = {}  # url -> read_utc of the replayed read, for sources that refused this run


def remember(url: str, payload: dict) -> None:
    MEM[url] = {"read_utc": RUN_UTC, **payload}


def carried(url: str) -> dict | None:
    """The source's last good read when it is at most MAX_CARRY_DAYS old, else None."""
    m = MEM.get(url)
    try:
        age = _dtm.now(_tzm.utc) - _dtm.strptime(m["read_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=_tzm.utc)
    except (TypeError, KeyError, ValueError):
        return None
    return m if age <= _tdm(days=MAX_CARRY_DAYS) else None


def fetch(url: str, robots: dict, report: list) -> BeautifulSoup | None:
    """Fetch once per URL, politely per host (one request a second), with one retry on a 5xx or timeout."""
    if url in PAGE_CACHE:
        return PAGE_CACHE[url]
    if not allowed(url, robots):
        report.append(f"SKIP robots.txt disallows: {url}")
        FAILED.append({"url": url, "reason": "robots.txt disallows"})
        PAGE_CACHE[url] = None
        return None
    host = urlparse(url).netloc
    gap = 1.0 - (time.monotonic() - LAST_HIT.get(host, 0))
    if gap > 0:
        time.sleep(gap)
    r, err = None, ""
    for attempt in (1, 2):
        try:
            LAST_HIT[host] = time.monotonic()
            r = requests.get(url, headers=HEADERS, timeout=30)
            err = "" if r.status_code == 200 else f"HTTP {r.status_code}"
            if r.status_code < 500:
                break
        except requests.RequestException as exc:
            err = type(exc).__name__
        if attempt == 1:
            time.sleep(3)
    if err:
        report.append(f"FAIL {err}: {url}")
        FAILED.append({"url": url, "reason": err})
        PAGE_CACHE[url] = None
        return None
    try:
        html = r.content.decode("utf-8")
    except UnicodeDecodeError:  # some list pages declare UTF-8 but serve Windows-1252
        html = r.content.decode("cp1252", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    PAGE_CACHE[url] = soup
    return soup


def page_is_for(soup: BeautifulSoup, year: str) -> bool:
    """A Veterans Day list counts only when its title names this year (or no year at all)."""
    title = clean((soup.title.get_text(" ") if soup.title else "") + " " + " ".join(h.get_text(" ") for h in soup.find_all("h1")[:2]))
    years = set(re.findall(r"\b20\d{2}\b", title))
    return not years or year in years


AFFILIATE = re.compile(r"(skimresources|skimlinks|redirect|/go/|/out/|amzn\.|amazon\.|linksynergy|awin1|shareasale|"
                       r"impact\.com|sjv\.io|prf\.hn|anrdoezrs|dpbolvw|jdoqocy|kqzyfj|tkqlhce|pjtra|ojrq|rstyle|"
                       r"howl\.me|narrativ|bam-x|clickserve|pntra|avantlink|go\.|click\.|track)", re.I)
VD_STOP = {"veterans day", "free meals", "restaurants", "restaurant", "retail", "retail grocery", "personal care",
           "attractions", "car care", "food dining", "food drink", "faq", "faqs", "summary", "related", "more", "share",
           "national parks", "national parks service", "national park service", "confirmed", "reported", "pending",
           "key takeaway", "key takeaways", "federal holiday", "oil changes", "car washes", "haircuts", "zoos", "museums",
           "banks", "hotels", "theme parks", "dd214", "dd 214", "dependents", "spouses", "national guard", "reserves",
           "gold star families", "active duty", "retirees", "id.me", "sheerid", "govx", "military id", "proof of service",
           "dine-in only", "dine in only", "in-store only", "nov", "november 11", "wednesday", "tuesday", "thank you",
           "question", "questions", "answer", "last verified", "next update", "updated", "breakfast", "lunch", "dinner",
           "coffee", "dessert", "desserts", "snacks", "drinks", "date", "dates", "who qualifies", "proof of service required",
           "methodology", "sources", "source", "details", "how to claim", "what to bring"}
US_STATES = {"alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida",
             "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
             "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska",
             "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
             "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee", "texas",
             "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming", "puerto rico"}
END_OF_ARTICLE = re.compile(r"^(leave a )?(comment|reply)|^\d+ (comments|responses)|^more stories|^link disclaimer|"
                            r"^statement of endorsement|^you may also like|^related (posts|articles|stories)", re.I)
OLD_SECTION = re.compile(r"2024|2025|previous|last year|recurring|not yet|unconfirmed|verify|waiting|predict|expect|"
                         r"anticipat|pending|year[- ]round|all year|never expire|faq", re.I)
EXECUTOR_WORKERS = 8
SLOT_WORDS = (("coffee", ("coffee", "cafe", "donut", "doughnut", "bagel", "dunkin", "starbucks", "krispy", "biggby", "scooter")),
              ("breakfast", ("breakfast", "pancake", "waffle", "ihop", "bob evans", "cracker barrel", "denny", "shoney", "eggs")))


# ---------- offer facts from list text (facts only, written in our own words) ----------
STOP_AFTER = {"for", "to", "with", "on", "at", "when", "from", "through", "in", "during", "by", "if", "until", "while",
              "per", "valid", "dine-in", "dine", "available", "nov", "nov.", "november", "veterans", "veteran", "military",
              "active", "active-duty", "service", "members", "is", "are", "will", "plus", "who", "that", "you", "their",
              "all", "any", "every", "this", "as", "they", "we", "it", "be", "can", "get", "receive", "today"}
TRAIL_DROP = {"and", "or", "a", "an", "the", "&", "+", "of", "with", "your", "their"}
PCT_OFF = re.compile(r"(up to\s+)?(\d{1,2})\s?(?:%|percent)\s*(?:off|discount)", re.I)
DOLLAR = re.compile(r"\$(\d{1,3}(?:\.\d\d)?)\s+(off|tickets?|admission|entrees?|meals?|burgers?|pizzas?|haircuts?|oil changes?)", re.I)
BOGO = re.compile(r"\bbuy one,?\s+(?:entr[ée]e,?\s+)?get one\b|\bbogo\b", re.I)
EAT_FREE = re.compile(r"\b(eat|eats|dine|dines)\s+(for\s+)?free\b|\bfree (meal|entr[ée]e|lunch|dinner|breakfast)\b", re.I)
QUALIFIERS = [
    (re.compile(r"dine[- ]in only|dine[- ]in guests", re.I), "Dine-in only"),
    (re.compile(r"in[- ]store only|in[- ]store purchases? only", re.I), "In-store only"),
    (re.compile(r"participating (locations|restaurants|stores|shops|franchises)", re.I), "At participating locations"),
    (re.compile(r"while supplies last", re.I), "While supplies last"),
    (re.compile(r"voucher|redeem(able)? (later|on a future|for a future|through|by|until)|future visit|bounce[- ]?back", re.I), "Includes something to use later"),
    (re.compile(r"proof of service|military id|valid id|veteran id|dd[- ]?214|id required|with id\b|show (your )?id", re.I), "Bring proof of service"),
]
WHO_WORDS = [("veteran", r"\bveteran"), ("active-duty", r"active[- ]duty|active military|service ?members|active service"),
             ("retiree", r"\bretir"), ("guard-reserve", r"reserv|national guard"), ("spouse", r"spouse|military famil|dependents")]
PROOF_WORDS = [("id.me", r"id\.me"), ("sheerid", r"sheerid"), ("govx", r"govx"), ("promo-code", r"\b(promo )?code\b"),
               ("store-program", r"rewards (member|account|app)|loyalty|sign up|app\b"), ("military-id", r"military id|valid id|veteran id"),
               ("proof-of-service", r"proof of service|dd[- ]?214|id required")]
MONTHS = {"oct": 10, "nov": 11, "dec": 12, "jan": 1}
RANGE = re.compile(r"\b(oct|nov|dec)(?:ember|ober|\.)?\s+(\d{1,2})\s*(?:-|" + chr(0x2013) + r"|through|thru|to|and)\s*(?:(oct|nov|dec)(?:ember|ober|\.)?\s+)?(\d{1,2})\b", re.I)
REDEEM = re.compile(r"(?:redeem(?:able)?|valid|use(?:d)?|good|expires?|through)\s+(?:it\s+|them\s+)?(?:through|by|until|before|thru)?\s*"
                    r"(nov|dec|jan)(?:ember|uary|\.)?\s+(\d{1,2})", re.I)


def free_phrase(text: str) -> str | None:
    """'Free one-topping pizza', '10 free boneless wings and fries'. Stops at prepositions and punctuation."""
    for m in re.finditer(r"\bfree\b", text, re.I):
        before = text[max(0, m.start() - 6):m.start()].strip().split(" ")[-1]
        words = re.findall(r"[\w$'&+/.\-]+|[,;:()!?]", text[m.end():m.end() + 140])  # \w keeps accented letters (entrée)
        out = []
        for w in words:
            lw = w.lower().rstrip(".")
            if w in ",;:()!?" or lw in STOP_AFTER or (w.endswith(".") and lw not in {"oz", "lb", "pc"}):
                if w.endswith(".") and lw and lw not in STOP_AFTER and w not in ",;:()!?":
                    out.append(w.rstrip("."))
                break
            out.append(w)
            if len(out) >= 8:
                break
        out = [w for w in out if w.strip(".-")]
        while out and out[-1].lower() in TRAIL_DROP:
            out.pop()
        if not out or out[0].lower() in {"of", "charge", "shipping", "and", "or"}:
            continue
        lead = (before + " ") if before.isdigit() else ""
        phrase = (lead + "free " + " ".join(out)) if lead else "Free " + " ".join(out)
        return phrase[0].upper() + phrase[1:]
    return None


def offer_facts(text: str) -> dict:
    t = clean(text)
    facts: dict = {"primary": None, "quals": [], "range": None, "redeem": None, "who": set(), "proof": set(), "family": False}
    fp = free_phrase(t)
    m = PCT_OFF.search(t)
    d = DOLLAR.search(t)
    if BOGO.search(t):
        facts["primary"] = "Buy one, get one free" + (" (" + fp[5:] + ")" if fp and len(fp) > 5 and "get one" not in fp.lower() else "")
    elif fp:
        facts["primary"] = fp
    elif m:
        facts["primary"] = ("Up to " if m.group(1) else "") + m.group(2) + "% off"
    elif d:
        facts["primary"] = "$" + d.group(1) + " " + d.group(2).lower()
    elif EAT_FREE.search(t):
        facts["primary"] = "Free meal"
    if facts["primary"] and m and not facts["primary"].endswith("% off") and "%" not in facts["primary"]:
        facts["quals"].append("also mentions " + ("up to " if m.group(1) else "") + m.group(2) + "% off; see a source for what it covers")
    for rx, label in QUALIFIERS:
        if rx.search(t):
            facts["quals"].append(label)
    r = RANGE.search(t)
    if r:
        m1 = MONTHS[r.group(1).lower()[:3]]
        m2 = MONTHS[(r.group(3) or r.group(1)).lower()[:3]]
        a, b = int(r.group(2)), int(r.group(4))
        if 1 <= a <= 31 and 1 <= b <= 31 and (m2, b) > (m1, a):
            facts["range"] = (f"2026-{m1:02d}-{a:02d}", f"2026-{m2:02d}-{b:02d}")
    rd = REDEEM.search(t)
    if rd:
        mo = MONTHS[rd.group(1).lower()[:3]]
        day = int(rd.group(2))
        if 1 <= day <= 31 and (mo, day) > (11, 11) or mo == 1:
            facts["redeem"] = f"{2027 if mo == 1 else 2026}-{mo:02d}-{day:02d}"
    low = t.lower()
    for key, rx in WHO_WORDS:
        if re.search(rx, low):
            facts["who"].add(key)
    for key, rx in PROOF_WORDS:
        if re.search(rx, low):
            facts["proof"].add(key)
    facts["family"] = bool(re.search(r"\b(families|family members|spouses? and|kids eat|children|guests?)\b", low))
    return facts


def summarize_offer(texts: list[str]) -> dict:
    """Combine what several lists say about one offer. The primary offer most lists agree on wins;
    dates count only when two lists agree; qualifiers are kept when any list states them."""
    facts = [offer_facts(t) for t in texts if t]
    votes: dict[str, list[str]] = {}
    for f in facts:
        if f["primary"]:
            key = re.sub(r"[^a-z0-9%$]+", "", f["primary"].lower())
            votes.setdefault(key, []).append(f["primary"])
    primary = None
    if votes:
        best = max(votes.values(), key=lambda v: (len(v), -min(len(x) for x in v)))
        primary = min(best, key=len)
    quals: list[str] = []
    for f in facts:
        for q in f["quals"]:
            if q not in quals and not (primary and q.startswith("also mentions") and "%" in primary):
                quals.append(q)
    ranges = [f["range"] for f in facts if f["range"]]
    rng = max(set(ranges), key=ranges.count) if ranges and ranges.count(max(set(ranges), key=ranges.count)) >= 2 else None
    redeems = sorted(f["redeem"] for f in facts if f["redeem"])
    who = sorted(set().union(*[f["who"] for f in facts])) if facts else []
    proof = sorted(set().union(*[f["proof"] for f in facts])) if facts else []
    family = sum(1 for f in facts if f["family"]) >= 2
    return {"primary": primary, "quals": quals, "range": rng, "redeem": redeems[-1] if redeems else None,
            "who": who, "proof": proof, "family": family, "agree": len(best) if votes else 0}


def guess_slot(name: str) -> str:
    low = name.lower()
    for slot, words in SLOT_WORDS:
        if any(w in low for w in words):
            return slot
    return "anytime"


def frag(url: str, text: str) -> str:
    """Link that opens the page scrolled to, and highlighting, the brand's line (URL text fragment)."""
    if "#" in url or not text:
        return url
    t = re.sub(r"\(.*?\)", "", text).strip()
    variants = [t] + ([t.replace("'", chr(0x2019))] if "'" in t else [])
    return url + "#:~:" + "&".join("text=" + quote(v, safe="") for v in variants)


def domain(url: str) -> str:
    """Registrable domain, so 365.military.com and military.com are one source."""
    host = urlparse(url).netloc.lower()
    host = host.split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def brand_links(el, page_url: str, brand: str = "") -> list[str]:
    """External links inside the block that look like the brand's own military-discount page."""
    out = []
    key = norm(brand)
    for a in el.find_all("a", href=True):
        href = urljoin(page_url, a["href"])
        if not href.startswith("https://") or domain(href) == domain(page_url) or AFFILIATE.search(href):
            continue
        label = norm(a.get_text(" "))
        score = 0 if re.search(r"military|veteran|hero|service", href, re.I) else 2
        if key and (key in norm(href) or label == key):
            score -= 1  # the link names the brand itself
        out.append((score, href))
    out.sort()
    return [h for _, h in out][:2]


def check_brand_page(url: str, pct: int, robots: dict) -> dict | None:
    if not allowed(url, robots):
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    text = BeautifulSoup(r.text, "html.parser").get_text(" ").lower()
    if not re.search(r"military|veteran|service member", text):
        return None
    return {"url": r.url, "pct_ok": re.search(r"(?<!\d)%d\s?(%%|percent)" % pct, text) is not None}


SOURCE_STATS: dict[str, int] = {}
PREV_NAMES: dict[str, str] = {}  # norm(name) -> the display name a generated entry already has, so its id never changes
DESCRIPTORS = {"sleep", "bed", "beds", "mattress", "coffee", "co", "co.", "company", "inc", "inc.", "brand", "brands", "shop", "store",
               "usa", "apparel", "outdoors", "outdoor", "gear", "supply", "cosmetics", "beauty", "knives", "running", "bikes", "foods",
               "wear", "clothing", "official"}


def same_brand(short: str, long: str) -> bool:
    """'Helix' and 'Helix Sleep' are one brand; 'Delta' and 'Delta Faucet' are not (only descriptor words may follow)."""
    s, l = clean(short).lower().split(), clean(long).lower().split()
    return len(norm(short)) >= 5 and len(l) > len(s) and l[:len(s)] == s and all(w in DESCRIPTORS for w in l[len(s):])


KINDS: dict[str, str] = {}  # brand -> business type from the store snapshot (site/places.json "kinds")
FOOD_WORDS = re.compile(
    r"\b(?:meals?|entr[e\u00e9]es?|breakfast|lunch|dinner|brunch|coffee|latte|tea|donuts?|doughnuts?|burgers?|pancakes?|waffles?|subs?|"
    r"sandwich(?:es)?|pizzas?|pizzeria|wings?|tacos?|burritos?|nachos|chips|fries|desserts?|appetizers?|combos?|soups?|salads?|smoothies?|"
    r"shakes?|sundaes?|ice cream|cookies?|pies?|buffet|steaks?|steakhouse|shrimp|seafood|lobster|crab|fish|chicken|tenders|nuggets|bbq|"
    r"barbecue|smokehouse|ribs|brisket|pasta|spaghetti|noodles|sushi|cheesesteaks?|sliders|quesadillas?|drinks?|beverages?|dine-in|dine in|"
    r"menu|plates?|bowls?|biscuits?|bagels?|muffins?|pretzels?|hot dogs?|onion|grill|grille|kitchen|cafe|caf\u00e9|bistro|diner|eatery|"
    r"restaurants?|bakery|cantina|tavern|roadhouse|brewing|taproom|creamery)\b", re.I)


def low_key(s: str) -> str:
    return " ".join(str(s).lower().replace(chr(0x2019), "'").split())


ATTRACTION_WORDS = re.compile(r"\b(?:zoo|aquarium|museum|theme park|amusement|gardens|wildlife|hall of fame|admission|tickets?|disney|seaworld|"
                              r"legoland|six flags|knott|silver dollar city|medieval times|monticello|mount vernon|karting|trolley)\b", re.I)
TRAVEL_WORDS = re.compile(r"\b(?:hotels?|inns?|suites|motel|resorts?|cruises?|ferry|waterway|airlines?|b&bs?|stays?|lodging)\b", re.I)
SERVICE_WORDS = re.compile(r"\b(?:car wash|wash|auto|oil change|tires?|haircuts?|salon|barber|bank|credit union|navyfed|navy federal|usaa|aarp|"
                           r"insurance|membership|lube|monkey)\b", re.I)
FREE_FOOD = re.compile(r"\bfree\b.{0,40}\b(?:meal|entr[e\u00e9]e|coffee|drink|donut|doughnut|burger|pancake|sub|sandwich|pizza|wings?|taco|fries|"
                       r"dessert|appetizer|combo|smoothie|shake|ice|gelato|custard|cookie|breakfast|lunch|dinner|plate|bowl|biscuit|bagel|tea|latte|"
                       r"beer|soda|chips|food|slice|cone|treat)", re.I)


def vd_category(name: str, primary: str | None, texts: list[str]) -> str:
    """A free food or drink is food at any store (7-Eleven's free coffee). Then the store snapshot's business type; then
    attraction, travel or service words in the name or offer; then food words; else retail (a percent off at a store)."""
    offer = primary or ""
    if FREE_FOOD.search(offer):
        return "food"
    k = KINDS.get(low_key(name))
    if k and k != "retail":
        return k
    head = name + " " + offer
    for words, cat in ((ATTRACTION_WORDS, "attractions"), (TRAVEL_WORDS, "travel"), (SERVICE_WORDS, "services")):
        if words.search(head):
            return cat
    g = guess_category(name)
    if g not in ("retail", "food"):
        return g
    if k == "retail":
        return "retail"
    return "food" if FOOD_WORDS.search(" ".join([name, offer] + list(texts or []))) else "retail"


def load_prev_names(*paths) -> None:
    for path in paths:
        try:
            for e in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("entries") or []:
                PREV_NAMES.setdefault(norm(e["name"]), e["name"])
        except (OSError, ValueError, yaml.YAMLError):
            pass


def harvest_directories(cfg: dict, robots: dict, all_names: set, threshold: int, today: str, report: list):
    found: dict[str, dict] = {}
    for url in cfg.get("directories") or []:
        soup = fetch(url, robots, report)
        mem = None
        if soup is None:
            mem = carried(url)
            if mem is None:
                continue
            rows = [tuple(r) for r in mem.get("rows") or []]
        else:
            rows = []
            for text, heading, el in blocks(soup, with_el=True):
                got = extract(text) or extract_linked(el, text)
                if not got or got[1] < threshold or got[1] > 90:
                    continue
                brand, pct, up = got
                cat = guess_category(text)
                if cat == "retail":
                    cat = guess_category(heading)
                rows.append((brand, pct, up, cat, list(brand_links(el, url, brand))))
            remember(url, {"rows": [list(r) for r in rows]})
        hits = 0
        for brand, pct, up, cat, links in rows:
            key = norm(brand)
            if not key or known(key, all_names):
                continue
            hits += 1
            row = found.setdefault(key, {"name": PREV_NAMES.get(key, brand), "category": cat, "hits": {}, "links": []})
            d = domain(url)
            if d not in row["hits"] or pct > row["hits"][d]["pct"]:
                row["hits"][d] = {"pct": pct, "up": up, "url": url, "text": brand}
            for link in links:
                if link not in row["links"]:
                    row["links"].append(link)
        if mem is not None:
            CARRIED[url] = mem["read_utc"]
            report.append(f"KEPT {hits} qualifying rows from the last good read ({mem['read_utc']}): {url}")
            continue
        report.append(f"OK {hits} qualifying rows: {url}")
        SOURCE_STATS[url] = hits
    # One brand under two spellings ("Helix" and "Helix Sleep"): merge, keeping the stronger listing per directory.
    for key in sorted(found, key=len):
        if key not in found:
            continue
        for other in [k for k in found if k != key and k.startswith(key) and same_brand(found[key]["name"], found[k]["name"])]:
            for d, h in found[other]["hits"].items():
                if d not in found[key]["hits"] or h["pct"] > found[key]["hits"][d]["pct"]:
                    found[key]["hits"][d] = h
            found[key]["links"] += [l for l in found[other]["links"] if l not in found[key]["links"]]
            if other in PREV_NAMES and key not in PREV_NAMES:
                found[key]["name"] = PREV_NAMES[other]
            elif key not in PREV_NAMES:
                found[key]["name"] = found[other]["name"]  # the fuller spelling reads better
            del found[other]
    # Verify candidate brand pages in parallel (robots.txt checked per host first).
    jobs = [(key, link, max(h["pct"] for h in row["hits"].values())) for key, row in found.items() for link in row["links"][:2]]
    for _, link, _ in jobs:
        allowed(link, robots)
    with ThreadPoolExecutor(max_workers=EXECUTOR_WORKERS) as pool:
        checks = list(pool.map(lambda j: (j[0], check_brand_page(j[1], j[2], robots)), jobs))
    brand_page: dict[str, dict] = {}
    for key, res in checks:
        if res and (key not in brand_page or (res["pct_ok"] and not brand_page[key]["pct_ok"])):
            brand_page[key] = res
    entries, held = [], []
    for key, row in found.items():
        hits = sorted(row["hits"].values(), key=lambda h: -h["pct"])
        bp = brand_page.get(key)
        if bp and bp["pct_ok"]:
            pct, up, verified, conf = hits[0]["pct"], hits[0]["up"], "brand page", "official"
        elif len(hits) >= 2 and hits[1]["pct"] >= threshold:
            pct, up, verified, conf = hits[1]["pct"], hits[0]["up"] and hits[1]["up"], "two directories", "community"
        else:
            held.append(row["name"])
            continue
        dir_links = [frag(h["url"], h["text"]) for h in hits]
        sources = ([bp["url"]] if bp else []) + dir_links
        amount = ("Up to " if up else "") + f"{pct}% off"
        names = ", ".join(domain(h["url"]) for h in hits)
        offer = (f"{amount} with the military discount. Confirmed on the brand's own page; also listed by {names}."
                 if verified == "brand page" else
                 f"{amount} with the military discount, as reported by {len(hits)} independent directories ({names}).")
        entries.append({"id": "auto-" + slug(row["name"]), "name": row["name"], "category": row["category"],
                        "offer": offer + " Confirm current terms and who qualifies before buying.",
                        "percent": pct, "percent_up": bool(up), "verified_by": verified, "confidence": conf,
                        "source_url": sources[0], "sources": sources[:12]})
    entries.sort(key=lambda e: (-e["percent"], e["name"].lower()))
    report.append(f"DIRECTORIES: {len(entries)} listed, {len(held)} held back with one source, "
                  f"{sum(1 for v in brand_page.values() if v['pct_ok'])} confirmed on brand pages")
    return entries, sorted(held)


def offer_text_after(el, text: str, lead: str) -> str:
    """The words that describe the offer: the rest of the block, plus the next paragraph when the name is a heading."""
    rest = text[len(lead):] if lead and text.startswith(lead[:15]) else text
    if el.name in ("h3", "h4") or len(rest.split()) < 4:
        sib = el.find_next_sibling(["p", "ul", "div"])
        if sib is not None:
            rest += " " + clean(sib.get_text(" "))
    return rest.strip(" :-" + DASHES)[:400]


def vd_names_on(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(business name, offer text) for each list item, paragraph, table row or short heading on a 2026 list page."""
    names = []
    body = soup  # use the article or main element only when it actually holds the list
    for cand_body in (soup.find("article"), soup.find("main")):
        if cand_body is not None and len(cand_body.find_all(["li", "p", "tr"])) >= 25:
            body = cand_body
            break
    for text, heading, el in blocks(body, with_el=True):
        if el.name in ("h2", "h3") and END_OF_ARTICLE.search(text):
            break  # comments, footers and "more stories" are not offers
        if OLD_SECTION.search(heading) and el.name not in ("h1", "h2"):
            continue
        if SPECULATIVE.search(text):
            continue  # "will likely", "2025 terms", "pending": a guess, not an offer
        cand = ""
        if el.name == "tr":
            cand = text.split("|")[0].strip()
        elif el.name in ("h3", "h4"):
            cand = text if len(text.split()) <= 6 else ""
        else:
            lead = el.find(["strong", "b", "a"])
            lead_text = clean(lead.get_text(" ")) if lead else ""
            if lead_text and text.startswith(lead_text[:15]):
                cand = lead_text
        cand = re.split(r"\s[:" + DASHES + r"-]\s|:\s|\s\(", cand)[0].strip(" *:" + DASHES)
        brand = valid_brand(cand) if cand else None
        if brand and re.search(r"\b(with|and|or|for|the|of|to|a|an|at|by|from|in|on)$", brand, re.I):
            continue  # a sentence fragment, not a business name
        if not brand or chr(0xFFFD) in brand:
            continue  # garbled encoding; a clean copy on another list will carry it
        low = brand.lower()
        if low in VD_STOP or low in US_STATES or OLD_SECTION.search(brand) or len(brand.split()) > 6:
            continue
        if re.fullmatch(r"[a-z]+s", low) and low not in {"hooters", "wendys", "dennys", "arbys", "chilis", "culvers"}:
            continue  # a bare plural noun ("Zoos", "Banks") is a heading, not a business
        names.append((brand, offer_text_after(el, text, cand)))
    return names


def harvest_vd_lists(cfg: dict, robots: dict, vd_names: set, today: str, report: list, skip_names: set = frozenset()):
    seen: dict[str, dict] = {}
    year = (cfg.get("veterans_day_year") or today[:4])
    for url in cfg.get("veterans_day_lists") or []:
        soup = fetch(url, robots, report)
        mem = None
        if soup is None:
            mem = carried(url)
            if mem is None:
                continue
            pairs = [tuple(p) for p in mem.get("pairs") or []]
        else:
            if not page_is_for(soup, str(year)):
                report.append(f"SKIP not a {year} list by its title: {url}")
                FAILED.append({"url": url, "reason": f"title is not a {year} list"})
                continue
            pairs = vd_names_on(soup)
            remember(url, {"pairs": [list(p) for p in pairs]})
        for name, said in pairs:
            key = norm(name)
            row = seen.setdefault(key, {"name": PREV_NAMES.get(key, name), "lists": {}, "texts": {}})
            if chr(0xFFFD) in row["name"] and chr(0xFFFD) not in name:
                row["name"] = name  # prefer a clean spelling over a garbled one
            d = domain(url)
            row["lists"].setdefault(d, frag(url, name))
            if said and len(said) > len(row["texts"].get(d, "")):
                row["texts"][d] = said
        names = {p[0] for p in pairs}
        if mem is not None:
            CARRIED[url] = mem["read_utc"]
            report.append(f"KEPT {len(names)} names from the last good read ({mem['read_utc']}): {url}")
            continue
        report.append(f"VD LIST {len(names)} names: {url}")
        SOURCE_STATS[url] = len(names)
    # Merge the same business listed under a longer name ("Cracker Barrel Old Country Store").
    for key in sorted(seen, key=len):
        for other in [k for k in seen if k != key and k.startswith(key) and len(key) >= 6]:
            for d, link in seen[other]["lists"].items():
                seen[key]["lists"].setdefault(d, link)
            for d, said in seen[other]["texts"].items():
                seen[key]["texts"].setdefault(d, said)
            if other in PREV_NAMES and key not in PREV_NAMES:
                seen[key]["name"] = PREV_NAMES[other]  # keep the published name, so the id and My list picks survive
            seen[other]["lists"] = {}
    entries, single = [], []
    for key, row in seen.items():
        if not row["lists"] or known(key, vd_names) or key in skip_names or len(key) < 3:
            continue  # curated by hand, or already in the year-round directory
        links = list(row["lists"].values())
        if len(links) >= 2:
            cat = guess_category(row["name"])
            facts = summarize_offer(list(row["texts"].values()))
            if facts["primary"]:
                lead = facts["primary"].rstrip(".") + "."
                agree = f" Named on {len(links)} independent lists" + (f", {facts['agree']} of them with this offer" if 1 < facts["agree"] < len(links) else "") + "."
            else:
                lead = "Veterans Day offer; the lists word the terms differently."
                agree = f" Named on {len(links)} independent lists."
            quals = "".join(" " + q[0].upper() + q[1:] + "." for q in facts["quals"][:4])
            entry = {"id": "auto-vd-" + slug(row["name"]), "name": row["name"],
                     "category": vd_category(row["name"], facts["primary"], list(row["texts"].values())), "slot": guess_slot(row["name"] + " " + (facts["primary"] or "")),
                     "scope": "locations" if cat == "attractions" else "nationwide",
                     "offer": (lead + quals + agree + " Confirm with your location.")[:500],
                     "osm_brand": [row["name"]], "source_url": links[0], "sources": links[:12]}
            if facts["who"]:
                entry["eligibility"] = facts["who"]
            if facts["proof"]:
                entry["verification"] = facts["proof"]
            vd_day = f"{year}-11-11"
            if facts["range"] and facts["range"][0] <= vd_day <= facts["range"][1]:
                entry["event_start"], entry["event_end"] = facts["range"]  # a window that includes Veterans Day
            elif facts["range"] and facts["range"][0] > vd_day:
                facts["redeem"] = max(facts["redeem"] or "", facts["range"][1])  # a later window is when you redeem
            if facts["redeem"] and facts["redeem"] > entry.get("event_end", vd_day):
                entry["redeem_by"] = facts["redeem"]
            if facts["family"]:
                entry["family"] = True
            entries.append(entry)
        elif "news.va.gov" in row["lists"]:
            single.append(row["name"])
    entries.sort(key=lambda e: e["name"].lower())
    report.append(f"VETERANS DAY LISTS: {len(entries)} offers on two or more lists added; {len(single)} on VA News only")
    return entries, sorted(single)


def write_yaml(path: Path, defaults: dict, entries: list, note: str) -> None:
    header = f"# GENERATED by scripts/crawl.py on {date.today().isoformat()}. Do not edit by hand; curated entries win.\n# {note}\n"
    path.write_text(header + yaml.safe_dump({"defaults": defaults, "entries": entries}, sort_keys=False,
                                            allow_unicode=False, width=200), encoding="utf-8")


def main() -> int:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    try:
        MEM.update(json.loads(MEMORY_OUT.read_text(encoding="utf-8")).get("sources") or {})
    except (OSError, ValueError):
        pass
    threshold = int(cfg.get("threshold", 21))
    today = date.today().isoformat()
    all_names, vd_names = curated_names()
    load_prev_names(OUT, VD_OUT)
    try:
        KINDS.update(json.loads((ROOT / "site" / "places.json").read_text(encoding="utf-8")).get("kinds") or {})
    except (OSError, ValueError):
        pass
    robots: dict = {}
    report: list[str] = []
    dir_entries, held = harvest_directories(cfg, robots, all_names, threshold, today, report)
    write_yaml(OUT, {"eligibility": ["military"], "verification": ["see-source"], "scope": "online",
                     "last_verified": today, "auto": True}, dir_entries,
               f"Brands at {threshold}+ percent with two independent sources or a confirming brand page.")
    year_round = all_names | {norm(e["name"]) for e in dir_entries}
    vd_entries, va_only = harvest_vd_lists(cfg, robots, vd_names, today, report, year_round)
    write_yaml(VD_OUT, {"eligibility": ["military"], "verification": ["see-source"], "scope": "nationwide",
                        "last_verified": today, "confidence": "community", "auto": True,
                        "event_start": "2026-11-11", "event_end": "2026-11-11", "slot": "anytime"}, vd_entries,
               "Veterans Day 2026 offers named on two or more independent lists and not yet curated by hand.")
    url = (cfg.get("watch") or {}).get("veterans_day", "")
    # When each source was last tried and last read; a failed source keeps its last good read from earlier runs
    run_utc = RUN_UTC
    try:
        prev = {s["url"]: s for s in json.loads(WATCH_OUT.read_text(encoding="utf-8")).get("sources") or []}
    except (OSError, ValueError):
        prev = {}

    def status(u: str, kind: str) -> dict:
        rows = SOURCE_STATS.get(u)
        last_ok = run_utc if rows is not None else (prev.get(u) or {}).get("last_ok")
        return {"url": u, "kind": kind, "rows": rows, "last_try": run_utc, "last_ok": last_ok, "carried_from": CARRIED.get(u)}
    sources = [status(u, "directory") for u in cfg.get("directories") or []] + \
              [status(u, "veterans-day") for u in cfg.get("veterans_day_lists") or []]
    WATCH_OUT.write_text(json.dumps({"checked": today, "run_utc": run_utc, "source": url, "new_names": va_only[:40],
                                     "held_single_source": held, "sources": sources, "failed": FAILED,
                                     "counts": {"directory_listed": len(dir_entries), "veterans_day_listed": len(vd_entries),
                                                "held": len(held), "sources_read": sum(1 for s in sources if s["rows"] is not None),
                                                "sources_carried": len(CARRIED), "sources_total": len(sources)}}, indent=1) + "\n", encoding="utf-8")
    configured = [s["url"] for s in sources]
    MEMORY_OUT.write_text(json.dumps({"note": f"Last good read of each source, parsed; replayed up to {MAX_CARRY_DAYS} days when a source refuses.",
                                      "sources": {u: MEM[u] for u in configured if u in MEM}}, indent=0, ensure_ascii=True) + "\n", encoding="utf-8")
    print("\n".join(report))
    print(f"SOURCES: {sum(1 for s in sources if s['rows'] is not None)} of {len(sources)} read; {len(FAILED)} failed; {len(CARRIED)} kept from an earlier read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
