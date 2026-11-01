"""Build site/zip.json (ZIP code -> [lat, lon]) from the Census ZCTA Gazetteer.

The Census Bureau Gazetteer ZCTA file is public domain. Bundling it lets the
page turn a ZIP code into coordinates without sending the ZIP anywhere.

Usage:
    python scripts/build_zip.py PATH_TO_2024_Gaz_zcta_national.zip
Download:
    https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "site" / "zip.json"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with zipfile.ZipFile(sys.argv[1]) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".txt"))
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8").read()
    lines = text.splitlines()
    header = [h.strip() for h in lines[0].split("\t")]
    i_zip, i_lat, i_lon = header.index("GEOID"), header.index("INTPTLAT"), header.index("INTPTLONG")
    table: dict[str, list[float]] = {}
    for line in lines[1:]:
        cols = [c.strip() for c in line.split("\t")]
        if len(cols) <= max(i_zip, i_lat, i_lon):
            continue
        table[cols[i_zip]] = [round(float(cols[i_lat]), 3), round(float(cols[i_lon]), 3)]
    OUT.write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} with {len(table)} ZIP codes ({OUT.stat().st_size} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
