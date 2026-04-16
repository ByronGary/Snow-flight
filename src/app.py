import csv
import json
import math
import os
import re
from datetime import date, timedelta

import openmeteo_requests
import pandas as pd
import pgeocode
import requests
import requests_cache
from flask import Flask, render_template, request
from retry_requests import retry

app = Flask(__name__)


@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'unsafe-inline' 'self'; script-src 'unsafe-inline' 'self'"
    )
    return response


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
AIRPORTS_PATH = os.path.join(DATA_DIR, "airports.csv")

with open(os.path.join(DATA_DIR, "ikon_resorts.json")) as f:
    _ikon = json.load(f)
with open(os.path.join(DATA_DIR, "epic_resorts.json")) as f:
    _epic = json.load(f)
RESORTS = _ikon + _epic

# Load commercial airports with scheduled service from OurAirports
AIRPORTS = []
with open(AIRPORTS_PATH) as f:
    for row in csv.DictReader(f):
        try:
            iata = row["iata_code"].strip()
            if (row["type"] in ("large_airport", "medium_airport")
                    and row["scheduled_service"] == "yes"
                    and iata):
                AIRPORTS.append({
                    "iata": iata,
                    "name": row["name"],
                    "lat": float(row["latitude_deg"]),
                    "lon": float(row["longitude_deg"]),
                })
        except (ValueError, KeyError):
            pass

cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

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

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_CONDITIONS_HOST = "ski-resort-conditions.p.rapidapi.com"

_nomi = pgeocode.Nominatim("us")


def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def zip_to_airports(zip_code, radius_miles=20):
    """Return all commercial airports within radius_miles of the given ZIP code."""
    result = _nomi.query_postal_code(zip_code.strip())
    if result is None or result["latitude"] != result["latitude"]:
        return None, []
    lat, lon = float(result["latitude"]), float(result["longitude"])
    nearby = []
    for a in AIRPORTS:
        dist = haversine(lat, lon, a["lat"], a["lon"])
        if dist <= radius_miles:
            nearby.append({**a, "dist": round(dist, 1)})
    nearby.sort(key=lambda a: a["dist"])
    return (lat, lon), nearby


def google_flights_links(origin, destination):
    today = date.today()
    links = []
    for i in range(14):
        d = today + timedelta(days=i)
        label = d.strftime("%a, %b %-d")
        url = f"https://www.google.com/flights?hl=en#flt={origin}.{destination}.{d.isoformat()};c:USD;e:1;sd:1;t:f"
        links.append({"date": label, "url": url})
    return links


def fetch_conditions(conditions_id):
    """Fetch lift and trail status from the ski resort conditions API."""
    if not conditions_id:
        return None
    try:
        resp = requests.get(
            "https://ski-resort-conditions.p.rapidapi.com/get_snow_report",
            params={"id": conditions_id},
            headers={
                "x-rapidapi-host": RAPIDAPI_CONDITIONS_HOST,
                "x-rapidapi-key": RAPIDAPI_KEY,
            },
            timeout=5,
        )
        data = resp.json()
        if "error" in data or "message" in data:
            return None
        return {
            "open_lifts": data.get("open_lifts"),
            "open_trails": data.get("open_trails"),
            "base_depth": data.get("base_depth"),
            "snowfall_24h": data.get("snowfall24h"),
        }
    except Exception:
        return None


def season_start():
    today = date.today()
    return date(today.year if today.month >= 11 else today.year - 1, 11, 1)


def fetch_seasonal_snowfall(resort):
    start = season_start()
    yesterday = date.today() - timedelta(days=1)
    if start > yesterday:
        return 0.0
    params = {
        "latitude": resort["latitude"],
        "longitude": resort["longitude"],
        "daily": "snowfall_sum",
        "start_date": start.isoformat(),
        "end_date": yesterday.isoformat(),
        "precipitation_unit": "inch",
    }
    responses = openmeteo.weather_api(
        "https://archive-api.open-meteo.com/v1/archive", params=params
    )
    daily = responses[0].Daily()
    return round(float(daily.Variables(0).ValuesAsNumpy().sum()), 1)


def fetch_weather(resort):
    params = {
        "latitude": resort["latitude"],
        "longitude": resort["longitude"],
        "daily": ["weather_code", "snowfall_sum", "precipitation_sum", "temperature_2m_max", "temperature_2m_min"],
        "hourly": ["snow_depth"],
        "current": [
            "temperature_2m",
            "is_day",
            "snowfall",
            "wind_speed_10m",
            "wind_gusts_10m",
            "precipitation",
            "weather_code",
        ],
        "timezone": "America/Denver",
        "past_days": 0,
        "forecast_days": 7,
        "wind_speed_unit": "mph",
        "temperature_unit": "fahrenheit",
        "precipitation_unit": "inch",
    }
    responses = openmeteo.weather_api("https://api.open-meteo.com/v1/forecast", params=params)
    response = responses[0]

    current = response.Current()
    weather_code = int(current.Variables(6).Value())
    current_data = {
        "temperature": round(current.Variables(0).Value(), 1),
        "is_day": bool(current.Variables(1).Value()),
        "snowfall": round(current.Variables(2).Value(), 2),
        "wind_speed": round(current.Variables(3).Value(), 1),
        "wind_gusts": round(current.Variables(4).Value(), 1),
        "precipitation": round(current.Variables(5).Value(), 2),
        "conditions": WMO_CONDITIONS.get(weather_code, f"Code {weather_code}"),
    }

    hourly = response.Hourly()
    snow_depth_m = hourly.Variables(0).ValuesAsNumpy()
    valid_depths = [v for v in snow_depth_m if v is not None and v >= 0]
    current_data["snow_depth"] = round(valid_depths[0] * 39.3701, 1) if valid_depths else 0.0

    daily = response.Daily()
    daily_data = {
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        )
    }
    daily_data["snowfall_sum"] = [round(float(v), 2) for v in daily.Variables(1).ValuesAsNumpy()]
    daily_data["precipitation_sum"] = [round(float(v), 2) for v in daily.Variables(2).ValuesAsNumpy()]
    daily_data["temp_max"] = [round(float(v), 1) for v in daily.Variables(3).ValuesAsNumpy()]
    daily_data["temp_min"] = [round(float(v), 1) for v in daily.Variables(4).ValuesAsNumpy()]
    daily_df = pd.DataFrame(daily_data)
    daily_df["date"] = daily_df["date"].dt.strftime("%a %b %-d")

    return current_data, daily_df.to_dict(orient="records")


@app.route("/", methods=["GET"])
def index():
    return render_template("form.html", resorts=RESORTS, pass_type="ikon")


@app.route("/submit", methods=["POST"])
def submit():
    resort_name = request.form.get("resort")
    zip_code = request.form.get("zip_code", "").strip()
    pass_type = request.form.get("pass_type", "ikon")
    resort = next((r for r in RESORTS if r["name"] == resort_name), None)
    if not resort:
        return render_template("form.html", resorts=RESORTS, pass_type=pass_type, error="Resort not found.")

    current, daily = fetch_weather(resort)
    seasonal_snowfall = fetch_seasonal_snowfall(resort)
    conditions = fetch_conditions(resort.get("conditions_id"))

    nearby_airports = []
    zip_error = None

    if zip_code:
        if not re.fullmatch(r"[0-9]{5}(?:-[0-9]{4})?", zip_code):
            zip_error = "Please enter a valid 5-digit US ZIP code."
        else:
            _, nearby_airports = zip_to_airports(zip_code)
            if not nearby_airports:
                zip_error = f"No commercial airports within 20 miles of {zip_code}."

    # Build per-airport flight links for each nearby airport
    flights_by_airport = [
        {
            "iata": ap["iata"],
            "name": ap["name"],
            "dist": ap["dist"],
            "links": google_flights_links(ap["iata"], resort["airport"]),
        }
        for ap in nearby_airports
    ]

    return render_template(
        "form.html",
        resorts=RESORTS,
        selected=resort_name,
        current=current,
        daily=daily,
        resort=resort,
        seasonal_snowfall=seasonal_snowfall,
        flights_by_airport=flights_by_airport,
        zip_code=zip_code,
        zip_error=zip_error,
        conditions=conditions,
        pass_type=pass_type,
    )


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8000, debug=debug)
