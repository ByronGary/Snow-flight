"""JSON API consumed by the React frontend."""

from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, current_app, jsonify, request

from . import flights
from .airports import (
    AIRPORTS,
    DEFAULT_LIMIT,
    DEFAULT_RADIUS_MI,
    MAX_LIMIT,
    MAX_RADIUS_MI,
    ORIGIN_AIRPORTS,
    InvalidZip,
    ZipNotFound,
    destination_airports,
    nearby_airports,
)
from .data import PASS_TYPES, RESORTS, get_resort
from .weather import MAX_FORECAST_DAYS, WeatherUnavailable

api = Blueprint("api", __name__, url_prefix="/api")

MAX_DAYS_AHEAD = 330


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def error_response(status: int, code: str, message: str):
    return jsonify({"error": {"code": code, "message": message}}), status


@api.errorhandler(ApiError)
def _api_error(e: ApiError):
    return error_response(e.status, e.code, e.message)


def _int_arg(name: str, default: int, lo: int, hi: int, code: str) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(400, code, f"{name} must be a whole number.") from None
    if not lo <= value <= hi:
        raise ApiError(400, code, f"{name} must be between {lo} and {hi}.")
    return value


def _date_arg(name: str, required: bool) -> date | None:
    raw = request.args.get(name, "").strip()
    if not raw:
        if required:
            raise ApiError(400, "invalid_dates", f"{name} is required (YYYY-MM-DD).")
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ApiError(400, "invalid_dates", f"{name} must be a date (YYYY-MM-DD).") from None


def _cached(response, seconds: int):
    response.headers["Cache-Control"] = f"public, max-age={seconds}"
    return response


@api.get("/health")
def health():
    return jsonify({"status": "ok", "resorts": len(RESORTS), "airports": len(ORIGIN_AIRPORTS)})


def _pass_arg() -> str | None:
    pass_type = request.args.get("pass")
    if pass_type and pass_type not in PASS_TYPES:
        raise ApiError(400, "invalid_pass", f"pass must be one of: {', '.join(PASS_TYPES)}.")
    return pass_type or None


@api.get("/resorts")
def list_resorts():
    pass_type = _pass_arg()
    resorts = [{**r.to_dict(), "destinations": destination_airports(r)}
               for r in RESORTS if not pass_type or r.pass_type == pass_type]
    return _cached(jsonify({"resorts": resorts}), 3600)


@api.get("/resorts/<slug>/weather")
def resort_weather(slug: str):
    resort = get_resort(slug)
    if resort is None:
        raise ApiError(404, "resort_not_found", f"No resort called {slug!r}.")
    days = _int_arg("days", 7, 1, MAX_FORECAST_DAYS, "invalid_days")
    weather = current_app.extensions["weather"]
    try:
        forecast = weather.forecast(resort, days)
    except WeatherUnavailable:
        current_app.logger.exception("forecast failed for %s", slug)
        raise ApiError(502, "weather_unavailable", "Weather data is unavailable right now.") from None
    try:
        season = weather.season_snowfall(resort, date.today())
    except WeatherUnavailable:
        current_app.logger.warning("season snowfall failed for %s", slug, exc_info=True)
        season = None
    body = {"resort": {"slug": resort.slug, "name": resort.name}, **forecast, "season": season}
    return _cached(jsonify(body), 600)


@api.get("/airports/nearby")
def airports_nearby():
    radius = _int_arg("radius", DEFAULT_RADIUS_MI, 5, MAX_RADIUS_MI, "invalid_radius")
    limit = _int_arg("limit", DEFAULT_LIMIT, 1, MAX_LIMIT, "invalid_limit")
    try:
        result = nearby_airports(request.args.get("zip", ""), radius, limit)
    except InvalidZip as e:
        raise ApiError(400, "invalid_zip", str(e)) from None
    except ZipNotFound as e:
        raise ApiError(404, "zip_not_found", str(e)) from None
    return jsonify(result.to_dict())


@api.get("/flights")
def flight_search_links():
    depart = _date_arg("depart", required=True)
    ret = _date_arg("return", required=False)
    adults = _int_arg("adults", 1, 1, flights.MAX_ADULTS, "invalid_adults")
    today = date.today()
    if depart < today:
        raise ApiError(400, "invalid_dates", "Departure date is in the past.")
    if depart > today + timedelta(days=MAX_DAYS_AHEAD):
        raise ApiError(400, "invalid_dates", f"Departure must be within {MAX_DAYS_AHEAD} days.")
    if ret is not None and ret < depart:
        raise ApiError(400, "invalid_dates", "Return date must be on or after the departure date.")
    try:
        origins = flights.normalize_codes(request.args.get("origins", ""), flights.MAX_ORIGINS)
        dests = flights.normalize_codes(request.args.get("dest", ""), flights.MAX_DESTINATIONS)
    except ValueError as e:
        raise ApiError(400, "invalid_iata", str(e)) from None
    unknown = [c for c in origins + dests if c not in AIRPORTS]
    if unknown:
        raise ApiError(400, "invalid_iata", f"Unknown airport code: {', '.join(unknown)}.")
    return jsonify(flights.flight_links(origins, dests, depart, ret, adults))


@api.get("/powder")
def powder_board():
    """Every resort (optionally one pass) ranked by forecast snowfall over the next `days`."""
    pass_type = _pass_arg()
    days = _int_arg("days", 5, 1, MAX_FORECAST_DAYS, "invalid_days")
    resorts = [r for r in RESORTS if not pass_type or r.pass_type == pass_type]
    try:
        forecasts = current_app.extensions["weather"].daily_snowfall(resorts, days)
    except WeatherUnavailable:
        current_app.logger.exception("powder board forecast failed")
        raise ApiError(502, "weather_unavailable", "Weather data is unavailable right now.") from None
    rows = []
    for r in resorts:
        daily = forecasts.get(r.slug, [])
        peak = max(daily, key=lambda d: d[1]) if daily else None
        rows.append({
            "slug": r.slug,
            "name": r.name,
            "pass": r.pass_type,
            "region": r.region,
            "country": r.country,
            "total_in": round(sum(snow for _, snow in daily), 1),
            "peak": {"date": peak[0].isoformat(), "snowfall": peak[1]} if peak else None,
            "daily": [{"date": d.isoformat(), "snowfall": snow} for d, snow in daily],
        })
    rows.sort(key=lambda row: (-row["total_in"], row["name"]))
    return _cached(jsonify({"days": days, "resorts": rows}), 900)
