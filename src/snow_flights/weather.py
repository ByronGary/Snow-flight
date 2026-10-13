"""Open-Meteo forecast and season-to-date snowfall."""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .data import Resort

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TIMEOUT = (3.05, 10)
MAX_FORECAST_DAYS = 16

WMO_CONDITIONS = {
    0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy Fog",
    51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Heavy Drizzle",
    61: "Light Rain", 63: "Moderate Rain", 65: "Heavy Rain",
    71: "Light Snow", 73: "Moderate Snow", 75: "Heavy Snow", 77: "Snow Grains",
    80: "Light Rain Showers", 81: "Moderate Rain Showers", 82: "Heavy Rain Showers",
    85: "Light Snow Showers", 86: "Heavy Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ Hail", 99: "Thunderstorm w/ Heavy Hail",
}

UNITS = {"temp": "F", "snow": "in", "precip": "in", "wind": "mph", "depth": "in"}
_UNIT_PARAMS = {
    "temperature_unit": "fahrenheit",
    "wind_speed_unit": "mph",
    "precipitation_unit": "inch",
}
# Open-Meteo reports snow depth in feet when precipitation_unit=inch, metres otherwise.
_TO_INCHES = {"inch": 1.0, "in": 1.0, "ft": 12.0, "m": 39.3701, "cm": 1 / 2.54, "mm": 1 / 25.4}


class WeatherUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Season:
    start: date
    end: date
    label: str
    in_season: bool


def season_window(lat: float, today: date) -> Season:
    """The current ski season for a hemisphere, or the last finished one when off-season.

    Northern seasons run Oct 1 - Jun 30, southern seasons Apr 1 - Nov 30.
    """
    y = today.year
    if lat >= 0:
        if today.month >= 10:
            return Season(date(y, 10, 1), date(y + 1, 6, 30), f"{y}-{str(y + 1)[2:]}", True)
        if today.month <= 6:
            return Season(date(y - 1, 10, 1), date(y, 6, 30), f"{y - 1}-{str(y)[2:]}", True)
        return Season(date(y - 1, 10, 1), date(y, 6, 30), f"{y - 1}-{str(y)[2:]}", False)
    if 4 <= today.month <= 11:
        return Season(date(y, 4, 1), date(y, 11, 30), str(y), True)
    last = y if today.month == 12 else y - 1
    return Season(date(last, 4, 1), date(last, 11, 30), str(last), False)


def _round(value, ndigits=1):
    return None if value is None else round(float(value), ndigits)


def _inches(value, unit: str, ndigits=1):
    if value is None:
        return None
    return round(float(value) * _TO_INCHES.get(unit, 1.0), ndigits)


def _conditions(code) -> str | None:
    if code is None:
        return None
    code = int(code)
    return WMO_CONDITIONS.get(code, f"Code {code}")


def default_cache_dir() -> Path:
    return Path(os.environ.get("SNOW_FLIGHTS_CACHE_DIR") or Path(tempfile.gettempdir()) / "snow-flights")


class WeatherClient:
    """Thin JSON client for Open-Meteo with timeouts, retries and an HTTP cache.

    The cached session is created lazily so each gunicorn worker opens its own
    SQLite connection after forking.
    """

    def __init__(self, session: requests.Session | None = None, cache_dir: Path | None = None,
                 timeout=TIMEOUT):
        self._session = session
        self._cache_dir = cache_dir
        self._timeout = timeout
        self._lock = threading.Lock()

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            with self._lock:
                if self._session is None:
                    self._session = self._make_session()
        return self._session

    def _make_session(self) -> requests.Session:
        import requests_cache

        cache_dir = self._cache_dir or default_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        session = requests_cache.CachedSession(
            str(cache_dir / "open-meteo"),
            backend="sqlite",
            expire_after=1800,
            urls_expire_after={"archive-api.open-meteo.com": 43200, "api.open-meteo.com": 1800},
        )
        retry = Retry(total=2, backoff_factor=0.3, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def _get(self, url: str, params: dict):
        try:
            resp = self.session.get(url, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            raise WeatherUnavailable(f"Open-Meteo request failed: {e}") from e
        if isinstance(data, dict) and data.get("error"):
            raise WeatherUnavailable(f"Open-Meteo error: {data.get('reason')}")
        return data

    def forecast(self, resort: Resort, days: int = 7) -> dict:
        data = self._get(FORECAST_URL, {
            "latitude": resort.lat,
            "longitude": resort.lon,
            "current": "temperature_2m,is_day,snowfall,precipitation,wind_speed_10m,"
                       "wind_gusts_10m,weather_code,snow_depth",
            "daily": "weather_code,snowfall_sum,precipitation_sum,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": days,
            **_UNIT_PARAMS,
        })
        try:
            cur, cu = data["current"], data["current_units"]
            daily, du = data["daily"], data["daily_units"]
            current = {
                "time": cur["time"],
                "weather_code": cur.get("weather_code"),
                "conditions": _conditions(cur.get("weather_code")),
                "is_day": bool(cur.get("is_day")),
                "temperature": _round(cur.get("temperature_2m")),
                "snowfall": _inches(cur.get("snowfall"), cu.get("snowfall", "inch")),
                "precipitation": _round(cur.get("precipitation"), 2),
                "wind_speed": _round(cur.get("wind_speed_10m")),
                "wind_gusts": _round(cur.get("wind_gusts_10m")),
                "snow_depth": _inches(cur.get("snow_depth"), cu.get("snow_depth", "m")),
            }
            snow_unit = du.get("snowfall_sum", "inch")
            rows = []
            for i, day in enumerate(daily["time"]):
                code = daily["weather_code"][i]
                rows.append({
                    "date": day,
                    "weather_code": code,
                    "conditions": _conditions(code),
                    "snowfall": _inches(daily["snowfall_sum"][i], snow_unit),
                    "precipitation": _round(daily["precipitation_sum"][i], 2),
                    "temp_max": _round(daily["temperature_2m_max"][i]),
                    "temp_min": _round(daily["temperature_2m_min"][i]),
                })
        except (KeyError, IndexError, TypeError) as e:
            raise WeatherUnavailable(f"Unexpected Open-Meteo response: {e}") from e
        return {"timezone": data.get("timezone"), "units": UNITS, "current": current, "daily": rows}

    def season_snowfall(self, resort: Resort, today: date) -> dict:
        """Snowfall so far this season (or last season's total when off-season)."""
        season = season_window(resort.lat, today)
        end = min(season.end, today - timedelta(days=1))
        result = {
            "label": season.label,
            "start": season.start.isoformat(),
            "through": None,
            "snowfall": 0.0,
            "in_season": season.in_season,
        }
        if end < season.start:
            return result
        data = self._get(ARCHIVE_URL, {
            "latitude": resort.lat,
            "longitude": resort.lon,
            "daily": "snowfall_sum",
            "start_date": season.start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "auto",
            "precipitation_unit": "inch",
        })
        try:
            unit = data["daily_units"].get("snowfall_sum", "inch")
            days = [(d, v) for d, v in zip(data["daily"]["time"], data["daily"]["snowfall_sum"], strict=True)
                    if v is not None]
        except (KeyError, TypeError, ValueError) as e:
            raise WeatherUnavailable(f"Unexpected Open-Meteo response: {e}") from e
        # The archive lags a few days behind; report the last day that has data.
        result["through"] = days[-1][0] if days else None
        result["snowfall"] = _inches(sum(v for _, v in days), unit)
        return result

    def daily_snowfall(self, resorts: Sequence[Resort], days: int) -> dict[str, list[tuple[date, float]]]:
        """Daily forecast snowfall (inches) for many resorts in one request, in each resort's local time."""
        if not resorts:
            return {}
        data = self._get(FORECAST_URL, {
            "latitude": ",".join(str(r.lat) for r in resorts),
            "longitude": ",".join(str(r.lon) for r in resorts),
            # Requesting any `current` variable changes the model data Open-Meteo sums into
            # daily totals; include one so alerts match the numbers shown by forecast().
            "current": "weather_code",
            "daily": "snowfall_sum",
            "timezone": "auto",
            "forecast_days": days,
            "precipitation_unit": "inch",
        })
        locations = data if isinstance(data, list) else [data]
        if len(locations) != len(resorts):
            raise WeatherUnavailable("Open-Meteo returned the wrong number of locations.")
        out: dict[str, list[tuple[date, float]]] = {}
        for resort, loc in zip(resorts, locations, strict=True):
            try:
                unit = loc["daily_units"].get("snowfall_sum", "inch")
                out[resort.slug] = [
                    (date.fromisoformat(d), _inches(v, unit) or 0.0)
                    for d, v in zip(loc["daily"]["time"], loc["daily"]["snowfall_sum"], strict=True)
                ]
            except (KeyError, TypeError, ValueError) as e:
                raise WeatherUnavailable(f"Unexpected Open-Meteo response: {e}") from e
        return out

