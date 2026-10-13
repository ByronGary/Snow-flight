import json

import pytest

from _pb import decode_tfs
from conftest import FakeWeatherClient
from snow_flights.app import create_app
from snow_flights.data import RESORTS


def strict_json(resp):
    def reject(constant):
        raise ValueError(f"non-standard JSON constant {constant}")

    return json.loads(resp.get_data(as_text=True), parse_constant=reject)


def error_code(resp):
    return strict_json(resp)["error"]["code"]


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = strict_json(resp)
    assert body["status"] == "ok" and body["resorts"] == 99


def test_resorts_list_and_filter(client):
    all_resorts = strict_json(client.get("/api/resorts"))["resorts"]
    assert len(all_resorts) == 99
    ikon = strict_json(client.get("/api/resorts?pass=ikon"))["resorts"]
    epic = strict_json(client.get("/api/resorts?pass=epic"))["resorts"]
    assert (len(ikon), len(epic)) == (57, 42)
    assert {r["pass"] for r in ikon} == {"ikon"}
    vail = next(r for r in epic if r["slug"] == "vail")
    destinations = vail.pop("destinations")
    assert vail == {"slug": "vail", "name": "Vail", "pass": "epic", "country": "US", "region": "CO",
                    "lat": 39.6433, "lon": -106.3781, "airports": ["EGE", "DEN"], "hemisphere": "north"}
    assert [(d["iata"], d["dist_mi"]) for d in destinations] == [("EGE", 29), ("DEN", 92)]
    assert destinations[1]["name"] == "Denver International Airport"


def test_resorts_bad_pass(client):
    resp = client.get("/api/resorts?pass=mountain-collective")
    assert resp.status_code == 400 and error_code(resp) == "invalid_pass"


@pytest.mark.parametrize("slug", [r.slug for r in RESORTS])
def test_weather_for_every_resort(client, slug):
    resp = client.get(f"/api/resorts/{slug}/weather")
    assert resp.status_code == 200
    body = strict_json(resp)
    assert body["resort"]["slug"] == slug
    assert len(body["daily"]) == 7 and body["season"]["label"]


def test_weather_days_param(client, fake_weather):
    assert len(strict_json(client.get("/api/resorts/vail/weather?days=3"))["daily"]) == 3
    assert client.get("/api/resorts/vail/weather?days=0").status_code == 400
    assert client.get("/api/resorts/vail/weather?days=abc").status_code == 400


def test_weather_unknown_resort(client):
    resp = client.get("/api/resorts/nope/weather")
    assert resp.status_code == 404 and error_code(resp) == "resort_not_found"


def test_weather_upstream_failure_is_502(static_dir):
    app = create_app(weather=FakeWeatherClient(fail_forecast=True), static_dir=static_dir)
    resp = app.test_client().get("/api/resorts/vail/weather")
    assert resp.status_code == 502 and error_code(resp) == "weather_unavailable"


def test_season_failure_still_returns_forecast(static_dir):
    app = create_app(weather=FakeWeatherClient(fail_season=True), static_dir=static_dir)
    resp = app.test_client().get("/api/resorts/vail/weather")
    assert resp.status_code == 200 and strict_json(resp)["season"] is None


def test_powder_board(client, fake_weather):
    body = strict_json(client.get("/api/powder?pass=ikon&days=5"))
    assert body["days"] == 5
    assert len(body["resorts"]) == 57 and {r["pass"] for r in body["resorts"]} == {"ikon"}
    assert fake_weather.calls == [("daily", 57, 5)]  # one upstream call for the whole pass
    top = body["resorts"][0]
    assert top["slug"] == "alta-ski-area"
    assert top["peak"] == {"date": "2026-12-09", "snowfall": 10.0}
    assert len(top["daily"]) == 5
    totals = [r["total_in"] for r in body["resorts"]]
    assert totals == sorted(totals, reverse=True)


def test_powder_board_all_passes_and_errors(client, static_dir):
    assert len(strict_json(client.get("/api/powder"))["resorts"]) == 99
    assert error_code(client.get("/api/powder?pass=nope")) == "invalid_pass"
    assert error_code(client.get("/api/powder?days=40")) == "invalid_days"
    app = create_app(weather=FakeWeatherClient(fail_forecast=True), static_dir=static_dir)
    resp = app.test_client().get("/api/powder?pass=epic")
    assert resp.status_code == 502 and error_code(resp) == "weather_unavailable"


def test_nearby_airports(client):
    body = strict_json(client.get("/api/airports/nearby?zip=10001-1234&radius=50"))
    assert body["zip"] == "10001" and body["place"] == "New York, NY"
    assert {"JFK", "LGA", "EWR"} <= {a["iata"] for a in body["airports"]}
    assert body["expanded"] is False


@pytest.mark.parametrize("qs,status,code", [
    ("zip=abc", 400, "invalid_zip"),
    ("", 400, "invalid_zip"),
    ("zip=00000", 404, "zip_not_found"),
    ("zip=10001&radius=1000", 400, "invalid_radius"),
    ("zip=10001&limit=0", 400, "invalid_limit"),
])
def test_nearby_airports_errors(client, qs, status, code):
    resp = client.get(f"/api/airports/nearby?{qs}")
    assert resp.status_code == status and error_code(resp) == code


def test_flights(client, frozen_today):
    resp = client.get("/api/flights?origins=jfk,LGA&dest=EGE,DEN&depart=2026-12-10&return=2026-12-14")
    assert resp.status_code == 200
    body = strict_json(resp)
    assert body["trip"] == "round_trip" and body["origins"] == ["JFK", "LGA"]
    combined = body["destinations"][0]["all_origins"]["url"]
    tfs = combined.split("tfs=")[1].split("&")[0]
    assert decode_tfs(tfs)["legs"][0] == {"date": "2026-12-10", "from": ["JFK", "LGA"], "to": ["EGE"]}


def test_flights_one_way(client, frozen_today):
    body = strict_json(client.get("/api/flights?origins=DEN&dest=SLC&depart=2026-12-10"))
    assert body["trip"] == "one_way" and body["return"] is None


@pytest.mark.parametrize("qs,code", [
    ("origins=DEN&dest=SLC", "invalid_dates"),
    ("origins=DEN&dest=SLC&depart=2026-11-30", "invalid_dates"),          # in the past
    ("origins=DEN&dest=SLC&depart=2026-12-10&return=2026-12-09", "invalid_dates"),
    ("origins=DEN&dest=SLC&depart=2028-01-01", "invalid_dates"),          # too far ahead
    ("origins=DEN&dest=SLC&depart=12/10/2026", "invalid_dates"),
    ("origins=DENVER&dest=SLC&depart=2026-12-10", "invalid_iata"),
    ("origins=&dest=SLC&depart=2026-12-10", "invalid_iata"),
    ("origins=ZZZ&dest=SLC&depart=2026-12-10", "invalid_iata"),           # well-formed but unknown
    ("origins=DEN&dest=SLC&depart=2026-12-10&adults=12", "invalid_adults"),
])
def test_flights_errors(client, frozen_today, qs, code):
    resp = client.get(f"/api/flights?{qs}")
    assert resp.status_code == 400 and error_code(resp) == code


def test_unknown_api_path_is_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404 and resp.is_json and error_code(resp) == "not_found"


def test_api_wrong_method_is_json_405(client):
    resp = client.post("/api/resorts")
    assert resp.status_code == 405 and resp.is_json


def test_spa_routes_serve_index(client):
    for path in ("/", "/some/client/route"):
        resp = client.get(path)
        assert resp.status_code == 200 and b'id="root"' in resp.data
        assert resp.headers["Cache-Control"] == "no-cache"


def test_static_assets(client):
    resp = client.get("/assets/index.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["Cache-Control"]
    assert client.get("/favicon.svg").status_code == 200
    assert client.get("/assets/missing.js").status_code == 404


def test_web_app_manifest(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"
    assert resp.get_json(force=True)["display"] == "standalone"


def test_real_manifest_icons_exist():
    from pathlib import Path

    public = Path(__file__).parents[1] / "frontend" / "public"
    manifest = json.loads((public / "manifest.webmanifest").read_text())
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    for icon in manifest["icons"]:
        assert (public / icon["src"].lstrip("/")).is_file(), icon["src"]
    assert (public / "apple-touch-icon.png").is_file()


def test_old_form_redirects_home(client):
    resp = client.post("/submit", data={"resort": "Vail"})
    assert resp.status_code == 303 and resp.headers["Location"] == "/"


def test_relative_static_dir_from_env(static_dir, monkeypatch):
    monkeypatch.chdir(static_dir.parent)
    monkeypatch.setenv("SNOW_FLIGHTS_STATIC_DIR", static_dir.name)
    client = create_app(weather=FakeWeatherClient()).test_client()
    assert client.get("/").status_code == 200
    assert client.get("/assets/index.js").status_code == 200


def test_missing_frontend_build(tmp_path):
    app = create_app(weather=FakeWeatherClient(), static_dir=tmp_path / "missing")
    resp = app.test_client().get("/")
    assert resp.status_code == 503 and b"npm run build" in resp.data


def test_security_headers(client):
    resp = client.get("/api/health")
    csp = resp.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in csp and "script-src 'self'" in csp
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
