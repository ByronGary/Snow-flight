from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from _pb import decode_tfs
from snow_flights import flights


def tfs_of(url: str) -> dict:
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.google.com"
    assert parsed.path == "/travel/flights/search"
    qs = parse_qs(parsed.query)
    assert qs["hl"] == ["en"] and qs["curr"] == ["USD"]
    tfs = qs["tfs"][0]
    assert not set(tfs) & set("=+/"), "tfs must be URL-safe base64 without padding"
    return decode_tfs(tfs)


def test_round_trip_encodes_both_legs():
    url = flights.google_flights_url(["DEN"], ["SLC"], date(2026, 12, 10), date(2026, 12, 14))
    info = tfs_of(url)
    assert info["legs"] == [
        {"date": "2026-12-10", "from": ["DEN"], "to": ["SLC"]},
        {"date": "2026-12-14", "from": ["SLC"], "to": ["DEN"]},
    ]
    assert info["passengers"] == [1]
    assert info["seat"] == flights.ECONOMY
    assert info["trip"] == flights.ROUND_TRIP


def test_one_way_has_single_leg():
    info = tfs_of(flights.google_flights_url("JFK", "GVA", date(2026, 12, 10)))
    assert info["legs"] == [{"date": "2026-12-10", "from": ["JFK"], "to": ["GVA"]}]
    assert info["trip"] == flights.ONE_WAY


def test_multiple_origins_share_one_leg_in_order():
    url = flights.google_flights_url(["jfk", " LGA", "EWR", "JFK"], ["EGE"], date(2026, 12, 10),
                                     date(2026, 12, 14), adults=3)
    info = tfs_of(url)
    assert info["legs"][0]["from"] == ["JFK", "LGA", "EWR"]
    assert info["legs"][1]["to"] == ["JFK", "LGA", "EWR"]
    assert info["passengers"] == [1, 1, 1]


def test_golden_url_matches_the_one_verified_against_google():
    # Checked by hand: this URL opens Google Flights with DEN -> SLC, Dec 10-14, and prices.
    url = flights.google_flights_url(["DEN"], ["SLC"], date(2026, 12, 10), date(2026, 12, 14))
    assert url == (
        "https://www.google.com/travel/flights/search?"
        "tfs=Gh4SCjIwMjYtMTItMTBqBwgBEgNERU5yBwgBEgNTTEMaHhIKMjAyNi0xMi0xNGoHCAESA1NMQ3IHCAESA0RFTkABSAGYAQE"
        "&hl=en&curr=USD"
    )


def test_old_fragment_format_is_gone():
    url = flights.google_flights_url(["DEN"], ["SLC"], date(2026, 12, 10))
    assert "#flt=" not in url and "/flights?" not in url


@pytest.mark.parametrize("codes", ["DE", "DENV", "D3N", "", ",", "DEN;SLC"])
def test_invalid_codes_rejected(codes):
    with pytest.raises(ValueError):
        flights.google_flights_url(codes, ["SLC"], date(2026, 12, 10))


def test_too_many_origins_rejected():
    with pytest.raises(ValueError, match="At most"):
        flights.normalize_codes(["JFK", "LGA", "EWR", "HPN", "ISP", "SWF", "TTN", "PHL"], flights.MAX_ORIGINS)


def test_return_before_depart_rejected():
    with pytest.raises(ValueError, match="Return date"):
        flights.google_flights_url(["DEN"], ["SLC"], date(2026, 12, 10), date(2026, 12, 9))


def test_text_fallback_is_url_encoded():
    url = flights.google_flights_text_url("DEN", "SLC", date(2026, 12, 10), date(2026, 12, 14))
    parsed = urlparse(url)
    assert parsed.path == "/travel/flights"
    assert parse_qs(parsed.query)["q"] == ["Flights to SLC from DEN on 2026-12-10 through 2026-12-14"]
    one_way = flights.google_flights_text_url("den", "SLC", date(2026, 12, 10))
    assert parse_qs(urlparse(one_way).query)["q"] == ["Flights to SLC from DEN on 2026-12-10 oneway"]


def test_flight_links_shape():
    links = flights.flight_links(["JFK", "LGA"], ["EGE", "DEN"], date(2026, 12, 10), date(2026, 12, 14))
    assert links["trip"] == "round_trip"
    assert links["origins"] == ["JFK", "LGA"]
    assert [d["iata"] for d in links["destinations"]] == ["EGE", "DEN"]
    assert [d["primary"] for d in links["destinations"]] == [True, False]
    ege = links["destinations"][0]
    assert ege["all_origins"]["label"] == "JFK/LGA → EGE"
    assert tfs_of(ege["all_origins"]["url"])["legs"][0]["from"] == ["JFK", "LGA"]
    assert [o["origin"] for o in ege["by_origin"]] == ["JFK", "LGA"]
    assert tfs_of(ege["by_origin"][1]["url"])["legs"][0] == {"date": "2026-12-10", "from": ["LGA"],
                                                              "to": ["EGE"]}
    assert all(o["fallback_url"].startswith(flights.TEXT_SEARCH_URL) for o in ege["by_origin"])
    # Text search can't take several origins, so the combined fallback uses the first one.
    assert "from+JFK+on" in ege["all_origins"]["fallback_url"]


@pytest.mark.parametrize("offset", range(7))
def test_default_trip_dates_are_next_friday_to_monday(offset):
    today = date(2026, 12, 7) + timedelta(days=offset)  # Mon Dec 7 .. Sun Dec 13
    depart, ret = flights.default_trip_dates(today)
    assert depart.weekday() == 4 and ret.weekday() == 0
    assert 1 <= (depart - today).days <= 7
    assert ret - depart == timedelta(days=3)


@pytest.mark.network
@pytest.mark.parametrize("origins,dest", [(["DEN"], "SLC"), (["JFK", "LGA", "EWR"], "EGE")])
def test_google_renders_results(origins, dest):
    """Canary for the tfs format. Google sometimes throttles scripted requests, so if this fails,
    open the URL in a browser before concluding the format changed (then switch to fallback_url)."""
    depart = date.today() + timedelta(days=45)
    url = flights.google_flights_url(origins, [dest], depart, depart + timedelta(days=4))
    resp = requests.get(url, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/130.0 Safari/537.36",
        "Accept-Language": "en-US",
    })
    assert resp.status_code == 200
    assert "US dollars" in resp.text, f"no prices rendered; check in a browser: {url}"
