"""Build site/zip.json (ZIP code -> [lat, lon, state]) from Census Bureau files (public domain).

Bundling it lets the page turn a ZIP code into coordinates and a state on the device, so the
ZIP is never sent anywhere.

Usage:
    python scripts/build_zip.py GAZETTEER_ZIP RELATIONSHIP_TXT
Downloads:
    https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip
    https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "site" / "zip.json"
FIPS = {"01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
        "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
        "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
        "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
        "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
        "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "72": "PR"}


def zip_states(rel_path: str) -> dict[str, str]:
    """Each ZCTA gets the state of the county holding the largest share of its land area."""
    best: dict[str, tuple[int, str]] = {}
    with open(rel_path, encoding="utf-8-sig") as fh:
        header = fh.readline().rstrip("\n").split("|")
        iz, ic, ia = header.index("GEOID_ZCTA5_20"), header.index("GEOID_COUNTY_20"), header.index("AREALAND_PART")
        for line in fh:
            cols = line.rstrip("\n").split("|")
            z, county = cols[iz], cols[ic]
            if not z or not county:
                continue
            area = int(cols[ia] or 0)
            st = FIPS.get(county[:2])
            if st and area >= best.get(z, (-1, ""))[0]:
                best[z] = (area, st)
    return {z: st for z, (_, st) in best.items()}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    states = zip_states(sys.argv[2])
    with zipfile.ZipFile(sys.argv[1]) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8").read()
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    i_zip, i_lat, i_lon = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
    table: dict[str, list] = {}
    for line in lines[1:]:
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) <= max(i_zip, i_lat, i_lon):
            continue
        z = cols[i_zip]
        table[z] = [round(float(cols[i_lat]), 3), round(float(cols[i_lon]), 3), states.get(z, "")]
    OUT.write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    missing = sum(1 for v in table.values() if not v[2])
    print(f"Wrote {OUT} with {len(table)} ZIP codes, {missing} without a state ({OUT.stat().st_size} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
