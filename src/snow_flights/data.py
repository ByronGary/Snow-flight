"""Ikon and Epic resort data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
PASS_TYPES = ("ikon", "epic")


@dataclass(frozen=True)
class Resort:
    slug: str
    name: str
    pass_type: str
    country: str
    region: str
    lat: float
    lon: float
    airports: tuple[str, ...]

    @property
    def hemisphere(self) -> str:
        return "south" if self.lat < 0 else "north"

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "name": self.name,
            "pass": self.pass_type,
            "country": self.country,
            "region": self.region,
            "lat": self.lat,
            "lon": self.lon,
            "airports": list(self.airports),
            "hemisphere": self.hemisphere,
        }


def _parse(raw: dict) -> Resort:
    return Resort(
        slug=raw["slug"],
        name=raw["name"],
        pass_type=raw["pass"],
        country=raw["country"],
        region=raw.get("state") or raw.get("province") or "",
        lat=float(raw["latitude"]),
        lon=float(raw["longitude"]),
        airports=tuple(raw["airports"]),  # curated, closest/most useful first
    )


def load_resorts(data_dir: Path = DATA_DIR) -> list[Resort]:
    resorts: list[Resort] = []
    for pass_type in PASS_TYPES:
        with open(data_dir / f"{pass_type}_resorts.json", encoding="utf-8") as f:
            resorts.extend(_parse(r) for r in json.load(f))
    return resorts


RESORTS = load_resorts()
RESORTS_BY_SLUG = {r.slug: r for r in RESORTS}


def get_resort(slug: str) -> Resort | None:
    return RESORTS_BY_SLUG.get(slug)
