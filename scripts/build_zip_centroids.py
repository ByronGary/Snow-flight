"""Build src/snow_flights/data/us_zip_centroids.csv from the GeoNames US postal code dump.

    python scripts/build_zip_centroids.py              # download from GeoNames
    python scripts/build_zip_centroids.py --source US.zip

GeoNames postal data is licensed CC BY 4.0 (https://www.geonames.org/). This is the
same dataset pgeocode used; bundling it means no download at startup and no pandas.
"""

from __future__ import annotations

import argparse
import csv
import io
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

SOURCE_URL = "https://download.geonames.org/export/zip/US.zip"
OUT = Path(__file__).resolve().parents[1] / "src" / "snow_flights" / "data" / "us_zip_centroids.csv"


def read_geonames(source: Path) -> list[list[str]]:
    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as zf, zf.open("US.txt") as f:
            text = io.TextIOWrapper(f, encoding="utf-8").read()
    else:
        text = source.read_text(encoding="utf-8")
    return [line.split("\t") for line in text.splitlines() if line]


def build(rows: list[list[str]]) -> list[tuple[str, str, str, float, float]]:
    # Columns: country, postal code, place, admin1 name, admin1 code (state), ..., lat (9), lon (10)
    grouped: dict[str, list[list[str]]] = defaultdict(list)
    for r in rows:
        if r[0] == "US" and r[1].isdigit() and len(r[1]) == 5 and r[9] and r[10]:
            grouped[r[1]].append(r)
    out = []
    for zip5, group in sorted(grouped.items()):
        # A handful of ZIPs repeat; average their coordinates and keep the first place name.
        lat = sum(float(r[9]) for r in group) / len(group)
        lon = sum(float(r[10]) for r in group) / len(group)
        out.append((zip5, group[0][2], group[0][4], round(lat, 4), round(lon, 4)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, help="Local US.zip or US.txt instead of downloading")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    source = args.source
    if source is None:
        tmp = Path(tempfile.mkdtemp()) / "US.zip"
        print(f"Downloading {SOURCE_URL} ...")
        urllib.request.urlretrieve(SOURCE_URL, tmp)
        source = tmp

    rows = build(read_geonames(source))
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["zip", "place", "state", "lat", "lon"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} ZIP codes to {args.out}")


if __name__ == "__main__":
    main()
