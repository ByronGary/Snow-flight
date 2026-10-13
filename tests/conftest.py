import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from snow_flights.app import create_app
from snow_flights.weather import WeatherUnavailable

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeWeatherClient:
    """Stands in for WeatherClient in API tests; no network."""

    def __init__(self, fail_forecast=False, fail_season=False):
        self.fail_forecast = fail_forecast
        self.fail_season = fail_season
        self.calls = []

    def forecast(self, resort, days=7):
        self.calls.append(("forecast", resort.slug, days))
        if self.fail_forecast:
            raise WeatherUnavailable("boom")
        return {
            "timezone": "America/Denver",
            "units": {"temp": "F", "snow": "in", "precip": "in", "wind": "mph", "depth": "in"},
            "current": {"time": "2026-12-07T09:00", "weather_code": 71, "conditions": "Light Snow",
                        "is_day": True, "temperature": 21.3, "snowfall": 0.1, "precipitation": 0.01,
                        "wind_speed": 12.0, "wind_gusts": 25.3, "snow_depth": 38.2},
            "daily": [{"date": f"2026-12-{7 + i:02d}", "weather_code": 73, "conditions": "Moderate Snow",
                       "snowfall": 4.2, "precipitation": 0.5, "temp_max": 25.0, "temp_min": 12.1}
                      for i in range(days)],
        }

    def daily_snowfall(self, resorts, days):
        self.calls.append(("daily", len(resorts), days))
        if self.fail_forecast:
            raise WeatherUnavailable("boom")
        start = date(2026, 12, 7)
        # Deterministic: snowier the further north, plus a big day at Alta.
        return {r.slug: [(start + timedelta(days=i), 10.0 if r.slug == "alta-ski-area" and i == 2
                          else round(max(r.lat, 0) / 20, 1)) for i in range(days)]
                for r in resorts}

    def season_snowfall(self, resort, today):
        self.calls.append(("season", resort.slug))
        if self.fail_season:
            raise WeatherUnavailable("boom")
        return {"label": "2026-27", "start": "2026-10-01", "through": "2026-12-04",
                "snowfall": 42.1, "in_season": True}


@pytest.fixture
def fake_weather():
    return FakeWeatherClient()


@pytest.fixture
def static_dir(tmp_path):
    d = tmp_path / "static"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text('<!doctype html><div id="root"></div><script type="module" '
                                  'src="/assets/index.js"></script>')
    (d / "assets" / "index.js").write_text("console.log('hi')")
    (d / "favicon.svg").write_text("<svg/>")
    (d / "manifest.webmanifest").write_text('{"name": "Snow Flights", "display": "standalone"}')
    return d


@pytest.fixture
def client(fake_weather, static_dir):
    app = create_app(weather=fake_weather, static_dir=static_dir)
    app.testing = True
    return app.test_client()


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SNOW_FLIGHTS_CACHE_DIR", str(tmp_path / "cache"))


@pytest.fixture
def frozen_today(monkeypatch):
    """Pin date.today() inside the API module."""
    import snow_flights.api as api_module

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 12, 1)

    monkeypatch.setattr(api_module, "date", FrozenDate)
    return FrozenDate.today()
