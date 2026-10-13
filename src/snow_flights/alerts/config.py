"""Alert configuration (YAML)."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .. import flights
from ..airports import DEFAULT_RADIUS_MI, MAX_RADIUS_MI, InvalidZip, normalize_zip
from ..data import RESORTS_BY_SLUG
from ..weather import MAX_FORECAST_DAYS


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Thresholds:
    min_daily_in: float | None
    min_total_in: float | None


@dataclass(frozen=True)
class WatchedResort:
    slug: str
    thresholds: Thresholds


@dataclass(frozen=True)
class AlertConfig:
    home_airports: tuple[str, ...]
    home_zip: str | None
    radius_mi: int
    window_days: int
    thresholds: Thresholds
    depart_days_before: int
    nights: int
    resorts: tuple[WatchedResort, ...]
    send_when_empty: bool
    discord_enabled: bool
    discord_webhook_env: str
    discord_username: str
    app_url: str | None


def _section(raw: dict, key: str) -> dict:
    value = raw.get(key) or {}
    if not isinstance(value, dict):
        raise ConfigError(f"'{key}' must be a mapping.")
    return value


def _number(section: dict, key: str, where: str, default=None, *, lo=None, hi=None, integer=False):
    value = section.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (integer and not isinstance(value, int)):
        raise ConfigError(f"{where}.{key} must be a {'whole ' if integer else ''}number.")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ConfigError(f"{where}.{key} must be between {lo} and {hi}.")
    return value


def _thresholds(section: dict, where: str, fallback: Thresholds | None = None) -> Thresholds:
    daily = _number(section, "min_daily_in", where, lo=0.1, hi=100)
    total = _number(section, "min_total_in", where, lo=0.1, hi=300)
    if fallback is not None:
        daily = daily if "min_daily_in" in section else fallback.min_daily_in
        total = total if "min_total_in" in section else fallback.min_total_in
    if daily is None and total is None:
        raise ConfigError(f"{where} needs min_daily_in and/or min_total_in.")
    return Thresholds(daily, total)


def _resorts(raw, defaults: Thresholds) -> tuple[WatchedResort, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'resorts' must be a non-empty list of resort slugs.")
    out: list[WatchedResort] = []
    for item in raw:
        entry = {"slug": item} if isinstance(item, str) else item
        if not isinstance(entry, dict) or not isinstance(entry.get("slug"), str):
            raise ConfigError(f"Invalid resort entry: {item!r}")
        slug = entry["slug"]
        if slug not in RESORTS_BY_SLUG:
            close = difflib.get_close_matches(slug, RESORTS_BY_SLUG, n=3)
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            raise ConfigError(f"Unknown resort slug {slug!r}.{hint}")
        out.append(WatchedResort(slug, _thresholds(entry, f"resorts[{slug}]", defaults)))
    return tuple(out)


def parse_config(raw) -> AlertConfig:
    if not isinstance(raw, dict):
        raise ConfigError("Config must be a YAML mapping.")
    home, powder, trip, notify = (_section(raw, k) for k in ("home", "powder", "trip", "notify"))
    discord = _section(notify, "discord")

    try:
        airports = flights.normalize_codes(home["airports"], flights.MAX_ORIGINS) if home.get("airports") else ()
    except ValueError as e:
        raise ConfigError(f"home.airports: {e}") from None
    home_zip = home.get("zip")
    if home_zip is not None:
        try:
            home_zip = normalize_zip(str(home_zip))
        except InvalidZip as e:
            raise ConfigError(f"home.zip: {e}") from None
    if not airports and not home_zip:
        raise ConfigError("Set home.airports or home.zip.")

    defaults = _thresholds(powder, "powder")
    app_url = raw.get("app_url")
    if app_url is not None and not (isinstance(app_url, str) and app_url.startswith(("http://", "https://"))):
        raise ConfigError("app_url must be an http(s) URL or null.")

    return AlertConfig(
        home_airports=airports,
        home_zip=home_zip,
        radius_mi=_number(home, "radius_mi", "home", DEFAULT_RADIUS_MI, lo=5, hi=MAX_RADIUS_MI, integer=True),
        window_days=_number(powder, "window_days", "powder", 5, lo=1, hi=MAX_FORECAST_DAYS, integer=True),
        thresholds=defaults,
        depart_days_before=_number(trip, "depart_days_before", "trip", 1, lo=0, hi=7, integer=True),
        nights=_number(trip, "nights", "trip", 3, lo=1, hi=30, integer=True),
        resorts=_resorts(raw.get("resorts"), defaults),
        send_when_empty=bool(notify.get("send_when_empty", False)),
        discord_enabled=bool(discord.get("enabled", True)),
        discord_webhook_env=str(discord.get("webhook_env", "DISCORD_WEBHOOK_URL")),
        discord_username=str(discord.get("username", "Snow Flights")),
        app_url=app_url.rstrip("/") if app_url else None,
    )


def load_config(path: str | Path) -> AlertConfig:
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError as e:
        raise ConfigError(f"Cannot read {path}: {e.strerror}") from None
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from None
    return parse_config(raw)
