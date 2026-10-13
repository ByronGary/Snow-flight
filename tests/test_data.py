import re

from snow_flights.airports import AIRPORTS
from snow_flights.data import RESORTS, RESORTS_BY_SLUG

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def test_resort_counts():
    assert len(RESORTS) == 99
    assert sum(r.pass_type == "ikon" for r in RESORTS) == 57
    assert sum(r.pass_type == "epic" for r in RESORTS) == 42


def test_slugs_unique_and_well_formed():
    assert len(RESORTS_BY_SLUG) == len(RESORTS)
    bad = [r.slug for r in RESORTS if not SLUG_RE.match(r.slug)]
    assert not bad
    assert RESORTS_BY_SLUG["val-d-isere"].name == "Val d'Isère"
    assert RESORTS_BY_SLUG["morzine-avoriaz"].name == "Morzine–Avoriaz"


def test_destination_airports_exist():
    missing = {(r.slug, code) for r in RESORTS for code in r.airports if code not in AIRPORTS}
    assert not missing


def test_destination_airports_are_curated_lists():
    for r in RESORTS:
        assert 1 <= len(r.airports) <= 3, r.slug
        assert len(set(r.airports)) == len(r.airports), r.slug
        assert all(AIRPORTS[c].scheduled for c in r.airports), r.slug
    # Spots where the nearest airport is the wrong answer.
    assert RESORTS_BY_SLUG["mammoth-mountain"].airports[0] == "BIH"  # MMH lost airline service in 2018
    assert "TRN" not in RESORTS_BY_SLUG["val-d-isere"].airports  # pass road closed in winter
    assert RESORTS_BY_SLUG["vail"].airports == ("EGE", "DEN")


def test_coordinates_in_range():
    for r in RESORTS:
        assert -90 <= r.lat <= 90 and -180 <= r.lon <= 180, r.slug
        assert r.region, r.slug


def test_hemisphere():
    assert RESORTS_BY_SLUG["thredbo"].hemisphere == "south"
    assert RESORTS_BY_SLUG["vail"].hemisphere == "north"
