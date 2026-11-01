"""Checks for build_data.derive_percent, the source of the over-20-percent badge.
Run: python tests/test_percent.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_data import derive_percent  # noqa: E402

CASES = [
    ("plain", "30 percent off in-store for military.", 30, None),
    ("range keeps max as up to", "20 to 25 percent off on request with ID.", 25, True),
    ("up to", "Up to 10 percent off cruise fares.", 10, True),
    ("half price", "Half-price entree on Sunday.", 50, None),
    ("rating is not a discount", "Edelweiss is limited to 100 percent disabled veterans.", None, None),
    ("free lead is skipped", "Free admission; up to four family members get 50 percent off.", None, None),
    ("no off or discount word", "Flash deals up to 60 percent.", None, None),
    ("percent sign", "Save 35% off full-price gear.", 35, None),
]
failures = []
for label, offer, want_pct, want_up in CASES:
    e = {"kind": "discount", "offer": offer}
    derive_percent(e)
    if e.get("percent") != want_pct or e.get("percent_up") != want_up:
        failures.append(f"{label}: got percent={e.get('percent')} up={e.get('percent_up')}, want {want_pct} {want_up}")
preset = {"kind": "crawled", "offer": "Reported up to 40 percent military discount.", "percent": 40}
derive_percent(preset)
if preset.get("percent_up") is not True:
    failures.append("preset percent with 'up to' text should set percent_up")
if failures:
    print("PERCENT TESTS FAILED")
    print("\n".join(failures))
    sys.exit(1)
print(f"PERCENT TESTS PASSED ({len(CASES) + 1} checks)")
