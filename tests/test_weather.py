import copy
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from conftest import load_fixture
from snow_flights.data import get_resort
from snow_flights.weather import (
    ARCHIVE_URL,
    FORECAST_URL,
    WeatherClient,
    WeatherUnavailable,
    season_window,
)


@pytest.fixture
def client():
    # A plain session: no HTTP cache between tests.
    return WeatherClient(session=requests.Session())


def query(call) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


@responses.activate
def test_forecast_uses_resort_local_timezone(client):
    responses.get(FORECAST_URL, json=load_fixture("forecast_niseko-united"))
    result = client.forecast(get_resort("niseko-united"))
    q = query(responses.calls[0])
    assert q["timezone"] == "auto"
    assert q["precipitation_unit"] == "inch" and q["temperature_unit"] == "fahrenheit"
    assert result["timezone"] == "Asia/Tokyo"
    assert len(result["daily"]) == 7
    assert result["daily"][0]["date"] == "2026-10-13"


@responses.activate
def test_snow_depth_in_feet_is_converted_to_inches(client):
    data = load_fixture("forecast_alta-ski-area")
    assert data["current_units"]["snow_depth"] == "ft"
    data["current"]["snow_depth"] = 3.0
    responses.get(FORECAST_URL, json=data)
    assert client.forecast(get_resort("alta-ski-area"))["current"]["snow_depth"] == 36.0


@responses.activate
def test_snow_depth_in_metres_is_converted_to_inches(client):
    data = load_fixture("forecast_alta-ski-area")
    data["current_units"]["snow_depth"] = "m"
    data["current"]["snow_depth"] = 1.0
    responses.get(FORECAST_URL, json=data)
    assert client.forecast(get_resort("alta-ski-area"))["current"]["snow_depth"] == 39.4


@responses.activate
def test_forecast_maps_conditions_and_nulls(client):
    data = copy.deepcopy(load_fixture("forecast_alta-ski-area"))
    data["daily"]["snowfall_sum"][1] = None
    data["current"]["weather_code"] = 73
    responses.get(FORECAST_URL, json=data)
    result = client.forecast(get_resort("alta-ski-area"))
    assert result["current"]["conditions"] == "Moderate Snow"
    assert result["daily"][1]["snowfall"] is None
    assert result["daily"][0]["conditions"]


@responses.activate
def test_forecast_failures_raise_weather_unavailable(client):
    responses.get(FORECAST_URL, status=500)
    with pytest.raises(WeatherUnavailable):
        client.forecast(get_resort("vail"))


@responses.activate
def test_forecast_timeout_raises_weather_unavailable(client):
    responses.get(FORECAST_URL, body=requests.Timeout("slow"))
    with pytest.raises(WeatherUnavailable):
        client.forecast(get_resort("vail"))


@responses.activate
def test_forecast_unexpected_shape_raises(client):
    responses.get(FORECAST_URL, json={"current": {}})
    with pytest.raises(WeatherUnavailable):
        client.forecast(get_resort("vail"))


@responses.activate
def test_season_snowfall_skips_missing_archive_days(client):
    data = load_fixture("archive_alta-ski-area")
    data["daily"]["snowfall_sum"][-2:] = [None, None]  # archive lags a few days
    responses.get(ARCHIVE_URL, json=data)
    result = client.season_snowfall(get_resort("alta-ski-area"), date(2026, 10, 12))
    q = query(responses.calls[0])
    assert (q["start_date"], q["end_date"]) == ("2026-10-01", "2026-10-11")
    assert result["label"] == "2026-27" and result["in_season"]
    assert result["through"] == data["daily"]["time"][-3]
    expected = round(sum(v for v in data["daily"]["snowfall_sum"] if v is not None), 1)
    assert result["snowfall"] == expected


def test_season_snowfall_on_opening_day_makes_no_call(client):
    result = client.season_snowfall(get_resort("vail"), date(2026, 10, 1))
    assert result == {"label": "2026-27", "start": "2026-10-01", "through": None, "snowfall": 0.0,
                      "in_season": True}


@pytest.mark.parametrize("lat,today,expected", [
    (40, date(2026, 10, 12), (date(2026, 10, 1), date(2027, 6, 30), "2026-27", True)),
    (40, date(2027, 2, 1), (date(2026, 10, 1), date(2027, 6, 30), "2026-27", True)),
    (40, date(2026, 8, 1), (date(2025, 10, 1), date(2026, 6, 30), "2025-26", False)),
    (-36, date(2026, 8, 1), (date(2026, 4, 1), date(2026, 11, 30), "2026", True)),
    (-36, date(2026, 12, 15), (date(2026, 4, 1), date(2026, 11, 30), "2026", False)),
    (-36, date(2027, 2, 1), (date(2026, 4, 1), date(2026, 11, 30), "2026", False)),
])
def test_season_window(lat, today, expected):
    s = season_window(lat, today)
    assert (s.start, s.end, s.label, s.in_season) == expected


@responses.activate
def test_daily_snowfall_for_many_resorts_in_one_call(client):
    responses.get(FORECAST_URL, json=load_fixture("daily_multi"))
    resorts = [get_resort(s) for s in ("alta-ski-area", "vail", "niseko-united")]
    result = client.daily_snowfall(resorts, 5)
    assert len(responses.calls) == 1
    q = query(responses.calls[0])
    assert q["latitude"].count(",") == 2 and q["timezone"] == "auto"
    assert set(result) == {"alta-ski-area", "vail", "niseko-united"}
    assert all(len(days) == 5 for days in result.values())
    assert result["niseko-united"][0][0] == date(2026, 10, 13)  # Japan is already tomorrow


@responses.activate
def test_daily_snowfall_location_count_mismatch(client):
    responses.get(FORECAST_URL, json=load_fixture("daily_multi")[:2])
    with pytest.raises(WeatherUnavailable):
        client.daily_snowfall([get_resort(s) for s in ("alta-ski-area", "vail", "niseko-united")], 5)


def test_default_client_creates_cache_lazily(tmp_path):
    client = WeatherClient(cache_dir=tmp_path / "c")
    assert not (tmp_path / "c").exists()
    _ = client.session
    assert (tmp_path / "c").is_dir()
