import argparse
import json
from datetime import date, timedelta

import pytest
import requests
import responses
import yaml

from snow_flights.alerts.config import ConfigError, load_config, parse_config
from snow_flights.alerts.notifiers import (
    MAX_EMBEDS_PER_MESSAGE,
    MAX_FIELD_CHARS,
    MAX_MESSAGE_CHARS,
    DiscordNotifier,
    NotifyError,
    app_link,
)
from snow_flights.alerts.powder import evaluate, render_text
from snow_flights.alerts.run import EXIT_CONFIG, EXIT_NOTIFY, EXIT_OK, EXIT_WEATHER, run
from snow_flights.data import RESORTS
from snow_flights.weather import WeatherUnavailable

TODAY = date(2026, 12, 7)
WEBHOOK = "https://discord.com/api/webhooks/123/secret-token"


def base_config(**overrides) -> dict:
    cfg = {
        "home": {"airports": ["JFK", "LGA", "EWR"]},
        "powder": {"window_days": 5, "min_daily_in": 6, "min_total_in": None},
        "trip": {"depart_days_before": 1, "nights": 3},
        "resorts": ["alta-ski-area", "snowbird", {"slug": "jackson-hole", "min_daily_in": 10}],
        "notify": {"discord": {"enabled": True}},
        "app_url": "https://snow.example.com/",
    }
    cfg.update(overrides)
    return cfg


def days(*snow, start=TODAY):
    return [(start + timedelta(days=i), float(s)) for i, s in enumerate(snow)]


# ---- config ----

def test_parse_config_defaults_and_overrides():
    cfg = parse_config(base_config())
    assert cfg.home_airports == ("JFK", "LGA", "EWR")
    assert cfg.window_days == 5 and cfg.nights == 3
    assert [w.slug for w in cfg.resorts] == ["alta-ski-area", "snowbird", "jackson-hole"]
    assert cfg.resorts[0].thresholds.min_daily_in == 6
    assert cfg.resorts[2].thresholds.min_daily_in == 10
    assert cfg.app_url == "https://snow.example.com"
    assert cfg.discord_webhook_env == "DISCORD_WEBHOOK_URL"


def test_unknown_slug_suggests_close_matches():
    with pytest.raises(ConfigError, match="Did you mean: alta-ski-area"):
        parse_config(base_config(resorts=["alta-ski"]))


@pytest.mark.parametrize("override,match", [
    ({"home": {}}, "home.airports or home.zip"),
    ({"home": {"zip": "abcde"}}, "home.zip"),
    ({"home": {"airports": ["DENVER"]}}, "home.airports"),
    ({"powder": {"min_daily_in": None, "min_total_in": None}}, "min_daily_in and/or min_total_in"),
    ({"powder": {"window_days": 30, "min_daily_in": 6}}, "window_days"),
    ({"powder": {"min_daily_in": "lots"}}, "min_daily_in"),
    ({"trip": {"nights": 0}}, "nights"),
    ({"resorts": []}, "non-empty list"),
    ({"resorts": [{"name": "Alta"}]}, "Invalid resort entry"),
    ({"app_url": "snow.example.com"}, "app_url"),
])
def test_config_validation(override, match):
    with pytest.raises(ConfigError, match=match):
        parse_config(base_config(**override))


def test_load_config_errors(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read"):
        load_config(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("home: [unclosed")
    with pytest.raises(ConfigError, match="Invalid YAML"):
        load_config(bad)


def test_example_config_is_valid():
    from pathlib import Path

    cfg = load_config(Path(__file__).parents[1] / "config" / "alerts.example.yaml")
    assert cfg.resorts and cfg.discord_enabled


def test_k8s_config_is_valid():
    from pathlib import Path

    assert load_config(Path(__file__).parents[1] / "k8s" / "alerts.yaml").resorts


# ---- evaluate ----

def test_threshold_is_inclusive():
    cfg = parse_config(base_config())
    digest = evaluate({"alta-ski-area": days(0, 6, 0, 0, 0), "snowbird": days(0, 5.9, 0, 0, 0)}, cfg, TODAY,
                      ["JFK"])
    assert [h.resort.slug for h in digest.hits] == ["alta-ski-area"]
    hit = digest.hits[0]
    assert hit.trigger_days == (TODAY + timedelta(days=1),)
    assert hit.depart == TODAY and hit.ret == TODAY + timedelta(days=3)


def test_window_excludes_later_days():
    cfg = parse_config(base_config())
    digest = evaluate({"alta-ski-area": days(0, 0, 0, 0, 0, 20)}, cfg, TODAY)
    assert digest.hits == ()


def test_per_resort_override():
    cfg = parse_config(base_config())
    digest = evaluate({"jackson-hole": days(8, 9, 0, 0, 0), "alta-ski-area": days(8, 0, 0, 0, 0)}, cfg, TODAY)
    assert [h.resort.slug for h in digest.hits] == ["alta-ski-area"]


def test_total_threshold_and_sorting():
    cfg = parse_config(base_config(powder={"window_days": 5, "min_daily_in": None, "min_total_in": 10}))
    digest = evaluate({
        "alta-ski-area": days(0, 0, 3, 4, 4),
        "snowbird": days(5, 5, 5, 0, 0),
        "jackson-hole": days(2, 2, 2, 2, 1),
    }, cfg, TODAY, ["JFK"])
    assert [(h.resort.slug, h.total_in) for h in digest.hits] == [("snowbird", 15.0), ("alta-ski-area", 11.0)]
    alta = digest.hits[1]
    # Total-only trigger: fly in the day before the first snowy day.
    assert alta.depart == TODAY + timedelta(days=1)


def test_depart_is_day_before_big_day():
    cfg = parse_config(base_config(trip={"depart_days_before": 1, "nights": 4}))
    hit = evaluate({"alta-ski-area": days(0, 0, 0, 12, 0)}, cfg, TODAY, ["JFK"]).hits[0]
    assert hit.depart == TODAY + timedelta(days=2)
    assert hit.ret == TODAY + timedelta(days=6)
    assert hit.peak == (TODAY + timedelta(days=3), 12.0)
    leg = hit.links["destinations"][0]
    assert leg["iata"] == "SLC" and leg["all_origins"]["label"] == "JFK → SLC"


def test_no_origins_means_no_links():
    cfg = parse_config(base_config())
    hit = evaluate({"alta-ski-area": days(10, 0, 0, 0, 0)}, cfg, TODAY, []).hits[0]
    assert hit.links is None
    assert "Flights" not in render_text(evaluate({"alta-ski-area": days(10, 0, 0, 0, 0)}, cfg, TODAY), cfg)


# ---- discord ----

def make_digest(n_hits: int, cfg=None):
    cfg = cfg or parse_config(base_config(resorts=[r.slug for r in RESORTS[:n_hits]]))
    forecasts = {r.slug: days(12, 3, 0, 0, 0) for r in RESORTS[:n_hits]}
    return cfg, evaluate(forecasts, cfg, TODAY, ["JFK", "LGA", "EWR"])


def test_discord_payload_shape():
    cfg, digest = make_digest(1)
    (payload,) = DiscordNotifier(WEBHOOK, cfg).payloads(digest)
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["content"].startswith("Powder alert: 1 resort")
    embed = payload["embeds"][0]
    assert embed["title"] == f'{RESORTS[0].name} ({RESORTS[0].region}): 15" in 5 days'
    assert embed["url"].startswith("https://snow.example.com/?resort=")
    flights_field = embed["fields"][1]
    assert "/travel/flights/search?tfs=" in flights_field["value"]
    assert all(len(f["value"]) <= MAX_FIELD_CHARS for f in embed["fields"])
    assert "Open-Meteo.com" in embed["footer"]["text"]  # CC BY 4.0 attribution


def test_discord_batches_embeds():
    cfg, digest = make_digest(23)
    payloads = DiscordNotifier(WEBHOOK, cfg).payloads(digest)
    assert sum(len(p["embeds"]) for p in payloads) == 23
    assert all(len(p["embeds"]) <= MAX_EMBEDS_PER_MESSAGE for p in payloads)
    assert all(len(json.dumps(p)) < MAX_MESSAGE_CHARS * 2 for p in payloads)
    assert "content" in payloads[0] and all("content" not in p for p in payloads[1:])


def test_app_link_includes_zip_when_configured():
    cfg = parse_config(base_config(home={"zip": "10001", "radius_mi": 50}))
    _, digest = make_digest(1, parse_config(base_config(home={"zip": "10001"}, resorts=[RESORTS[0].slug])))
    assert "zip=10001" in app_link(cfg, digest.hits[0])
    assert app_link(parse_config(base_config(app_url=None)), digest.hits[0]) is None


@responses.activate
def test_discord_send_ok():
    responses.post(WEBHOOK, json={"id": "1"})
    cfg, digest = make_digest(12)
    DiscordNotifier(WEBHOOK, cfg).send(digest)
    assert len(responses.calls) == 2
    assert responses.calls[0].request.url == WEBHOOK + "?wait=true"


@responses.activate
def test_discord_retries_once_on_429():
    responses.post(WEBHOOK, status=429, json={"retry_after": 0.5})
    responses.post(WEBHOOK, json={"id": "1"})
    slept = []
    cfg, digest = make_digest(1)
    DiscordNotifier(WEBHOOK, cfg, sleep=slept.append).send(digest)
    assert slept == [0.5] and len(responses.calls) == 2


@responses.activate
def test_discord_error_does_not_leak_webhook():
    responses.post(WEBHOOK, status=400, json={"message": "bad"})
    cfg, digest = make_digest(1)
    with pytest.raises(NotifyError) as e:
        DiscordNotifier(WEBHOOK, cfg).send(digest)
    assert "secret-token" not in str(e.value)


@responses.activate
def test_discord_connection_error_does_not_leak_webhook():
    responses.post(WEBHOOK, body=requests.ConnectionError(f"failed to reach {WEBHOOK}"))
    cfg, digest = make_digest(1)
    with pytest.raises(NotifyError) as e:
        DiscordNotifier(WEBHOOK, cfg).send(digest)
    assert "secret-token" not in str(e.value)


# ---- CLI ----

class FakeWeather:
    def __init__(self, forecasts=None, fail=False):
        self.forecasts, self.fail = forecasts or {}, fail

    def daily_snowfall(self, resorts, n):
        if self.fail:
            raise WeatherUnavailable("down")
        return {r.slug: self.forecasts.get(r.slug, days(0, 0, 0, 0, 0)) for r in resorts}


def cli_args(path, **kw):
    return argparse.Namespace(config=str(path), dry_run=kw.get("dry_run", False), today=TODAY,
                              test_notify=kw.get("test_notify", False), verbose=False)


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "alerts.yaml"
    path.write_text(yaml.safe_dump(base_config()))
    return path


@responses.activate
def test_cli_sends_digest(config_file, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    responses.post(WEBHOOK, json={"id": "1"})
    weather = FakeWeather({"alta-ski-area": days(0, 14, 2, 0, 0)})
    assert run(cli_args(config_file), weather=weather) == EXIT_OK
    assert len(responses.calls) == 1
    body = json.loads(responses.calls[0].request.body)
    assert "Alta Ski Area" in body["embeds"][0]["title"]


@responses.activate
def test_cli_quiet_day_sends_nothing(config_file, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    assert run(cli_args(config_file), weather=FakeWeather()) == EXIT_OK
    assert len(responses.calls) == 0


@responses.activate
def test_cli_dry_run_never_posts(config_file, capsys, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    weather = FakeWeather({"alta-ski-area": days(0, 14, 2, 0, 0)})
    assert run(cli_args(config_file, dry_run=True), weather=weather) == EXIT_OK
    out = capsys.readouterr().out
    assert "Alta Ski Area" in out and "Discord payloads" in out
    assert len(responses.calls) == 0


def test_cli_missing_webhook_is_config_error(config_file, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    assert run(cli_args(config_file), weather=FakeWeather()) == EXIT_CONFIG


def test_cli_bad_config(tmp_path):
    path = tmp_path / "alerts.yaml"
    path.write_text(yaml.safe_dump(base_config(resorts=["nope"])))
    assert run(cli_args(path), weather=FakeWeather()) == EXIT_CONFIG


def test_cli_weather_down(config_file, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    assert run(cli_args(config_file), weather=FakeWeather(fail=True)) == EXIT_WEATHER


@responses.activate
def test_cli_notify_failure(config_file, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    responses.post(WEBHOOK, status=500)
    weather = FakeWeather({"alta-ski-area": days(0, 14, 2, 0, 0)})
    assert run(cli_args(config_file), weather=weather) == EXIT_NOTIFY


@responses.activate
def test_cli_test_notify(config_file, monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)
    responses.post(WEBHOOK, json={"id": "1"})
    assert run(cli_args(config_file, test_notify=True), weather=FakeWeather()) == EXIT_OK
    assert "webhook OK" in json.loads(responses.calls[0].request.body)["content"]


def test_cli_resolves_origins_from_zip(tmp_path, capsys):
    path = tmp_path / "alerts.yaml"
    path.write_text(yaml.safe_dump(base_config(home={"zip": "80302", "radius_mi": 50})))
    weather = FakeWeather({"alta-ski-area": days(0, 14, 2, 0, 0)})
    assert run(cli_args(path, dry_run=True), weather=weather) == EXIT_OK
    assert "DEN → SLC" in capsys.readouterr().out
