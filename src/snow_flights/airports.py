"""Commercial airports (OurAirports data) and US ZIP code lookup (GeoNames centroids)."""

from __future__ import annotations

import csv
import functools
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .data import DATA_DIR, Resort

AIRPORTS_PATH = DATA_DIR / "airports.csv"
# Built by scripts/build_zip_centroids.py from GeoNames (CC BY 4.0).
ZIP_CENTROIDS_PATH = DATA_DIR / "us_zip_centroids.csv"

# OurAirports flags these as having scheduled service, but they are general-aviation
# or business-jet fields with no meaningful airline service for a ski trip.
ORIGIN_DENYLIST = frozenset({
    "TEB", "BJC", "BFI", "HHR", "BED", "PDK", "OPF", "LUK", "MRI", "GYY",
    "MGC", "SQL", "CCR", "FTW", "TIW", "MWL", "BLD", "UST", "EWB",
})

DEFAULT_RADIUS_MI = 50
MAX_RADIUS_MI = 150
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
FALLBACK_COUNT = 3
FALLBACK_MAX_MI = 250

_ZIP_RE = re.compile(r"^(\d{5})(?:-\d{4})?$")


class InvalidZip(ValueError):
    pass


class ZipNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    size: str  # "large" | "medium" | "small"
    lat: float
    lon: float
    scheduled: bool


@dataclass(frozen=True)
class ZipLocation:
    zip: str
    place: str
    lat: float
    lon: float


@dataclass(frozen=True)
class NearbyAirport:
    airport: Airport
    dist_mi: float

    def to_dict(self) -> dict:
        a = self.airport
        return {"iata": a.iata, "name": a.name, "city": a.city, "size": a.size, "dist_mi": self.dist_mi}


@dataclass(frozen=True)
class NearbyResult:
    location: ZipLocation
    radius_mi: int
    expanded: bool
    airports: list[NearbyAirport]

    def to_dict(self) -> dict:
        return {
            "zip": self.location.zip,
            "place": self.location.place,
            "lat": self.location.lat,
            "lon": self.location.lon,
            "radius": self.radius_mi,
            "expanded": self.expanded,
            "airports": [a.to_dict() for a in self.airports],
        }


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def load_airports(path: Path = AIRPORTS_PATH) -> dict[str, Airport]:
    """Every airport with an IATA code, keyed by code."""
    airports: dict[str, Airport] = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iata = row["iata_code"].strip()
            if not iata or not row["type"].endswith("_airport"):
                continue
            try:
                airport = Airport(
                    iata=iata,
                    name=row["name"],
                    city=row["municipality"],
                    country=row["iso_country"],
                    size=row["type"].removesuffix("_airport"),
                    lat=float(row["latitude_deg"]),
                    lon=float(row["longitude_deg"]),
                    scheduled=row["scheduled_service"] == "yes",
                )
            except ValueError:
                continue
            # A few codes appear more than once; keep the one with scheduled service.
            if iata not in airports or airport.scheduled:
                airports[iata] = airport
    return airports


AIRPORTS = load_airports()
ORIGIN_AIRPORTS = [
    a for a in AIRPORTS.values()
    if a.scheduled and a.size in ("large", "medium") and a.country == "US"
    and a.iata not in ORIGIN_DENYLIST
]


def normalize_zip(raw: str) -> str:
    """Accept ``12345`` or ``12345-6789`` and return the 5-digit ZIP."""
    m = _ZIP_RE.match((raw or "").strip())
    if not m:
        raise InvalidZip("Enter a 5-digit US ZIP code.")
    return m.group(1)


@functools.lru_cache(maxsize=1)
def _zip_centroids() -> dict[str, tuple[str, float, float]]:
    """ZIP -> (place, lat, lon), loaded on first lookup (~41k rows)."""
    with open(ZIP_CENTROIDS_PATH, encoding="utf-8", newline="") as f:
        return {
            row["zip"]: (", ".join(p for p in (row["place"], row["state"]) if p), float(row["lat"]), float(row["lon"]))
            for row in csv.DictReader(f)
        }


def lookup_zip(zip5: str) -> ZipLocation:
    try:
        place, lat, lon = _zip_centroids()[zip5]
    except KeyError:
        raise ZipNotFound(f"ZIP code {zip5} was not found.") from None
    return ZipLocation(zip=zip5, place=place, lat=lat, lon=lon)


def airports_near(lat: float, lon: float, radius_mi: int = DEFAULT_RADIUS_MI,
                  limit: int = DEFAULT_LIMIT) -> tuple[list[NearbyAirport], bool]:
    """Origin airports within the radius, large airports first, then sorted by distance.

    If none are within the radius, returns the nearest few within FALLBACK_MAX_MI
    and ``expanded=True``.
    """
    by_dist = sorted(
        (NearbyAirport(a, round(haversine(lat, lon, a.lat, a.lon), 1)) for a in ORIGIN_AIRPORTS),
        key=lambda n: n.dist_mi,
    )
    within = [n for n in by_dist if n.dist_mi <= radius_mi]
    if within:
        picked = sorted(within, key=lambda n: (n.airport.size != "large", n.dist_mi))[:limit]
        return sorted(picked, key=lambda n: n.dist_mi), False
    return [n for n in by_dist[:FALLBACK_COUNT] if n.dist_mi <= FALLBACK_MAX_MI], True


def nearby_airports(raw_zip: str, radius_mi: int = DEFAULT_RADIUS_MI,
                    limit: int = DEFAULT_LIMIT) -> NearbyResult:
    location = lookup_zip(normalize_zip(raw_zip))
    airports, expanded = airports_near(location.lat, location.lon, radius_mi, limit)
    return NearbyResult(location, radius_mi, expanded, airports)


def destination_airports(resort: Resort) -> list[dict]:
    """The resort's arrival airports with names and straight-line distance from the resort."""
    out = []
    for code in resort.airports:
        a = AIRPORTS.get(code)
        if a is None:
            continue
        out.append({"iata": code, "name": a.name, "city": a.city,
                    "dist_mi": round(haversine(resort.lat, resort.lon, a.lat, a.lon))})
    return out
