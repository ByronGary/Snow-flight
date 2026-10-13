import pytest

from snow_flights.airports import (
    AIRPORTS,
    ORIGIN_AIRPORTS,
    ORIGIN_DENYLIST,
    InvalidZip,
    ZipNotFound,
    nearby_airports,
    normalize_zip,
)

# (downtown ZIP, airports that must be offered, airports that must not be) at the default 50 mi.
MAJOR_CITIES = [
    ("10001", {"JFK", "LGA", "EWR"}, {"TEB"}),            # New York
    ("11201", {"JFK", "LGA", "EWR"}, set()),              # Brooklyn
    ("90012", {"LAX", "BUR", "LGB"}, {"HHR"}),            # Los Angeles
    ("60601", {"ORD", "MDW"}, {"GYY", "MGC"}),            # Chicago
    ("77002", {"IAH", "HOU"}, set()),                     # Houston
    ("85004", {"PHX"}, set()),                            # Phoenix
    ("19103", {"PHL"}, set()),                            # Philadelphia
    ("78205", {"SAT"}, set()),                            # San Antonio
    ("92101", {"SAN"}, {"TIJ"}),                          # San Diego (no Tijuana)
    ("75201", {"DFW", "DAL"}, {"FTW"}),                   # Dallas
    ("95113", {"SJC", "SFO", "OAK"}, {"SQL"}),            # San Jose
    ("78701", {"AUS"}, set()),                            # Austin
    ("94102", {"SFO", "OAK", "SJC"}, set()),              # San Francisco
    ("98101", {"SEA"}, {"BFI", "TIW"}),                   # Seattle
    ("80202", {"DEN"}, {"BJC"}),                          # Denver
    ("80302", {"DEN"}, {"BJC"}),                          # Boulder: DEN is ~34 mi out
    ("20001", {"DCA", "IAD", "BWI"}, set()),              # Washington DC
    ("02108", {"BOS", "PVD", "MHT"}, {"BED"}),            # Boston
    ("30303", {"ATL"}, {"PDK"}),                          # Atlanta
    ("33131", {"MIA", "FLL"}, {"OPF"}),                   # Miami
    ("55401", {"MSP"}, set()),                            # Minneapolis
    ("84101", {"SLC"}, set()),                            # Salt Lake City
    ("48226", {"DTW"}, {"YQG"}),                          # Detroit (no Windsor, Canada)
    ("32801", {"MCO"}, set()),                            # Orlando
    ("89101", {"LAS"}, {"BLD"}),                          # Las Vegas
    ("97201", {"PDX"}, set()),                            # Portland
    ("28202", {"CLT"}, set()),                            # Charlotte
    ("37203", {"BNA"}, set()),                            # Nashville
    ("64105", {"MCI"}, set()),                            # Kansas City
    ("63101", {"STL"}, set()),                            # St. Louis
    ("15222", {"PIT"}, set()),                            # Pittsburgh
    ("21202", {"BWI", "DCA"}, set()),                     # Baltimore
    ("33602", {"TPA"}, set()),                            # Tampa
    ("27601", {"RDU"}, set()),                            # Raleigh
    ("43215", {"CMH"}, set()),                            # Columbus
    ("46204", {"IND"}, set()),                            # Indianapolis
    ("44113", {"CLE"}, set()),                            # Cleveland
    ("70112", {"MSY"}, set()),                            # New Orleans
    ("95814", {"SMF"}, set()),                            # Sacramento
    ("45202", {"CVG"}, {"LUK"}),                          # Cincinnati
    ("96813", {"HNL"}, set()),                            # Honolulu
    ("99501", {"ANC"}, {"MRI"}),                          # Anchorage
    ("11747", {"ISP", "JFK", "LGA"}, set()),              # Long Island
    ("06901", {"HPN", "LGA"}, set()),                     # Stamford
]


@pytest.mark.parametrize("zip_code,must_include,must_exclude", MAJOR_CITIES, ids=[c[0] for c in MAJOR_CITIES])
def test_major_city_airports(zip_code, must_include, must_exclude):
    result = nearby_airports(zip_code)
    codes = {a.airport.iata for a in result.airports}
    assert not result.expanded
    assert must_include <= codes, f"missing {must_include - codes}; got {codes}"
    assert not codes & must_exclude
    assert len(result.airports) <= 5
    for a in result.airports:
        assert a.airport.country == "US"
        assert a.airport.iata not in ORIGIN_DENYLIST
        assert a.dist_mi <= 50
    dists = [a.dist_mi for a in result.airports]
    assert dists == sorted(dists)


@pytest.mark.parametrize("zip_code", ["10001", "80302", "20001", "60601"])
def test_smaller_radius_is_a_subset(zip_code):
    small = {a.airport.iata for a in nearby_airports(zip_code, radius_mi=25, limit=10).airports}
    large = {a.airport.iata for a in nearby_airports(zip_code, radius_mi=100, limit=10).airports}
    assert small <= large


def test_large_airports_rank_ahead_of_medium_when_limited():
    codes = [a.airport.iata for a in nearby_airports("10001", radius_mi=100, limit=3).airports]
    assert set(codes) == {"JFK", "LGA", "EWR"}


def test_zip_plus_four_is_accepted():
    plain, plus4 = nearby_airports("10001"), nearby_airports(" 10001-1234 ")
    assert plus4.location.zip == "10001"
    assert [a.airport.iata for a in plus4.airports] == [a.airport.iata for a in plain.airports]
    assert plain.location.place == "New York, NY"


@pytest.mark.parametrize("raw", ["", "abc", "1234", "123456", "10001-12", "1000l"])
def test_invalid_zip_format(raw):
    with pytest.raises(InvalidZip):
        normalize_zip(raw)


@pytest.mark.parametrize("zip_code", ["00000", "99999", "00601"])
def test_unknown_zip(zip_code):
    with pytest.raises(ZipNotFound):
        nearby_airports(zip_code)


def test_rural_zip_falls_back_to_nearest_airports():
    result = nearby_airports("69201", radius_mi=25)  # Valentine, NE
    assert result.expanded
    assert len(result.airports) == 3
    assert all(a.dist_mi > 25 for a in result.airports)


def test_origin_airports_are_us_commercial_only():
    assert len(ORIGIN_AIRPORTS) > 400
    assert all(a.country == "US" and a.size in ("large", "medium") and a.scheduled for a in ORIGIN_AIRPORTS)
    assert not {a.iata for a in ORIGIN_AIRPORTS} & ORIGIN_DENYLIST


def test_small_destination_airports_still_known():
    assert AIRPORTS["MMH"].size == "small"  # Mammoth: valid destination, not a home airport
