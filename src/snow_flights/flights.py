"""Google Flights deep links.

Google retired the old ``/flights#flt=ORIG.DEST.DATE`` URLs: they now redirect to
the Google Flights homepage and the fragment is ignored. The current search page
takes a ``tfs`` query parameter holding a base64-encoded protobuf, which we
hand-encode here (no protobuf dependency). Layout, as used by Google:

    Info       { repeated FlightData data = 3; repeated Passenger passengers = 8;
                 Seat seat = 9; Trip trip = 19; }
    FlightData { string date = 2; repeated Airport from = 13; repeated Airport to = 14; }
    Airport    { int32 type = 1;  /* 1 = airport */  string code = 2; }

Several origins (or destinations) in one leg search all of them at once.
A ``?q=`` text-search URL is produced alongside as a fallback in case Google
changes the ``tfs`` format again.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlencode

SEARCH_URL = "https://www.google.com/travel/flights/search"
TEXT_SEARCH_URL = "https://www.google.com/travel/flights"

ROUND_TRIP = 1
ONE_WAY = 2
ECONOMY = 1
ADULT = 1
AIRPORT = 1

MAX_ORIGINS = 7
MAX_DESTINATIONS = 3
MAX_ADULTS = 9

_IATA_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Leg:
    date: date
    origins: tuple[str, ...]
    destinations: tuple[str, ...]


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _varint_field(num: int, value: int) -> bytes:
    return _varint(num << 3) + _varint(value)


def _bytes_field(num: int, value: bytes | str) -> bytes:
    if isinstance(value, str):
        value = value.encode()
    return _varint((num << 3) | 2) + _varint(len(value)) + value


def _airport(code: str) -> bytes:
    return _varint_field(1, AIRPORT) + _bytes_field(2, code)


def _flight_data(leg: Leg) -> bytes:
    return (
        _bytes_field(2, leg.date.isoformat())
        + b"".join(_bytes_field(13, _airport(c)) for c in leg.origins)
        + b"".join(_bytes_field(14, _airport(c)) for c in leg.destinations)
    )


def build_tfs(legs: Sequence[Leg], adults: int = 1, seat: int = ECONOMY, trip: int = ROUND_TRIP) -> str:
    """Encode a search as the ``tfs`` parameter (URL-safe base64, no padding)."""
    message = (
        b"".join(_bytes_field(3, _flight_data(leg)) for leg in legs)
        + b"".join(_varint_field(8, ADULT) for _ in range(adults))
        + _varint_field(9, seat)
        + _varint_field(19, trip)
    )
    return base64.urlsafe_b64encode(message).decode().rstrip("=")


def normalize_codes(codes: Iterable[str] | str, limit: int) -> tuple[str, ...]:
    """Uppercase, validate and de-duplicate IATA codes, keeping their order."""
    if isinstance(codes, str):
        codes = codes.split(",")
    out: list[str] = []
    for raw in codes:
        code = raw.strip().upper()
        if not code:
            continue
        if not _IATA_RE.match(code):
            raise ValueError(f"Invalid airport code: {raw.strip()!r}")
        if code not in out:
            out.append(code)
    if not out:
        raise ValueError("At least one airport code is required.")
    if len(out) > limit:
        raise ValueError(f"At most {limit} airports are allowed.")
    return tuple(out)


def _legs(origins: tuple[str, ...], dests: tuple[str, ...], depart: date, ret: date | None) -> list[Leg]:
    legs = [Leg(depart, origins, dests)]
    if ret is not None:
        legs.append(Leg(ret, dests, origins))
    return legs


def _check_dates(depart: date, ret: date | None) -> None:
    if ret is not None and ret < depart:
        raise ValueError("Return date must be on or after the departure date.")


def google_flights_url(
    origins: Iterable[str] | str,
    dests: Iterable[str] | str,
    depart: date,
    ret: date | None = None,
    adults: int = 1,
) -> str:
    origins = normalize_codes(origins, MAX_ORIGINS)
    dests = normalize_codes(dests, MAX_DESTINATIONS)
    _check_dates(depart, ret)
    if not 1 <= adults <= MAX_ADULTS:
        raise ValueError(f"Adults must be between 1 and {MAX_ADULTS}.")
    tfs = build_tfs(
        _legs(origins, dests, depart, ret),
        adults=adults,
        trip=ROUND_TRIP if ret else ONE_WAY,
    )
    return f"{SEARCH_URL}?{urlencode({'tfs': tfs, 'hl': 'en', 'curr': 'USD'})}"


def google_flights_text_url(origin: str, dest: str, depart: date, ret: date | None = None) -> str:
    """Natural-language fallback, e.g. ``Flights to SLC from DEN on 2026-12-10 through 2026-12-14``.

    Google's text search only understands a single origin and destination.
    """
    (origin,) = normalize_codes([origin], 1)
    (dest,) = normalize_codes([dest], 1)
    _check_dates(depart, ret)
    q = f"Flights to {dest} from {origin} on {depart.isoformat()}"
    q += f" through {ret.isoformat()}" if ret else " oneway"
    return f"{TEXT_SEARCH_URL}?{urlencode({'q': q, 'hl': 'en', 'curr': 'USD'})}"


def _link(origins: tuple[str, ...], dest: str, depart: date, ret: date | None, adults: int) -> dict:
    return {
        "label": f"{'/'.join(origins)} → {dest}",
        "url": google_flights_url(origins, [dest], depart, ret, adults),
        "fallback_url": google_flights_text_url(origins[0], dest, depart, ret),
    }


def flight_links(
    origins: Iterable[str] | str,
    dests: Iterable[str] | str,
    depart: date,
    ret: date | None = None,
    adults: int = 1,
) -> dict:
    """Links for each destination: one search across all origins plus one per origin."""
    origins = normalize_codes(origins, MAX_ORIGINS)
    dests = normalize_codes(dests, MAX_DESTINATIONS)
    _check_dates(depart, ret)
    return {
        "depart": depart.isoformat(),
        "return": ret.isoformat() if ret else None,
        "trip": "round_trip" if ret else "one_way",
        "adults": adults,
        "origins": list(origins),
        "destinations": [
            {
                "iata": dest,
                "primary": i == 0,
                "all_origins": _link(origins, dest, depart, ret, adults),
                "by_origin": [
                    {"origin": o, **_link((o,), dest, depart, ret, adults)} for o in origins
                ],
            }
            for i, dest in enumerate(dests)
        ],
    }


def default_trip_dates(today: date) -> tuple[date, date]:
    """Next Friday after today, returning the following Monday."""
    days_ahead = (4 - today.weekday()) % 7 or 7
    depart = today + timedelta(days=days_ahead)
    return depart, depart + timedelta(days=3)
