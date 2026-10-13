"""`python -m snow_flights alerts`: check watched resorts and send a powder digest."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date

from ..airports import InvalidZip, ZipNotFound, nearby_airports
from ..data import get_resort
from ..weather import WeatherClient, WeatherUnavailable
from .config import AlertConfig, ConfigError, load_config
from .notifiers import DiscordNotifier, NotifyError
from .powder import evaluate, render_text

log = logging.getLogger("snow_flights.alerts")

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_WEATHER = 3
EXIT_NOTIFY = 4


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="Path to alerts YAML")
    parser.add_argument("--dry-run", action="store_true", help="Print the digest and Discord JSON; send nothing")
    parser.add_argument("--today", type=date.fromisoformat, help="Override today's date (YYYY-MM-DD)")
    parser.add_argument("--test-notify", action="store_true", help="Send a single test message and exit")
    parser.add_argument("-v", "--verbose", action="store_true")


def resolve_origins(cfg: AlertConfig) -> tuple[tuple[str, ...], list[str]]:
    if cfg.home_airports:
        return cfg.home_airports, []
    try:
        result = nearby_airports(cfg.home_zip, cfg.radius_mi)
    except (InvalidZip, ZipNotFound) as e:
        return (), [f"Home ZIP lookup failed ({e}); flight links omitted."]
    return tuple(a.airport.iata for a in result.airports), []


def run(args: argparse.Namespace, weather: WeatherClient | None = None, session=None) -> int:
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        log.error("config error: %s", e)
        return EXIT_CONFIG

    webhook = os.environ.get(cfg.discord_webhook_env, "").strip()
    discord = DiscordNotifier(webhook, cfg, session=session) if cfg.discord_enabled else None
    if discord and not webhook and not args.dry_run:
        log.error("environment variable %s is not set", cfg.discord_webhook_env)
        return EXIT_CONFIG

    if args.test_notify:
        if not discord:
            log.error("discord is disabled in the config")
            return EXIT_CONFIG
        if args.dry_run:
            log.info("dry run: would send a test message")
            return EXIT_OK
        try:
            discord.send_test()
        except NotifyError as e:
            log.error("%s", e)
            return EXIT_NOTIFY
        log.info("test message sent")
        return EXIT_OK

    today = args.today or date.today()
    origins, errors = resolve_origins(cfg)
    resorts = [get_resort(w.slug) for w in cfg.resorts]
    try:
        forecasts = (weather or WeatherClient()).daily_snowfall(resorts, cfg.window_days)
    except WeatherUnavailable as e:
        log.error("%s", e)
        return EXIT_WEATHER

    digest = evaluate(forecasts, cfg, today, origins, errors)
    log.info("%d of %d watched resorts hit the threshold", len(digest.hits), len(resorts))

    if args.dry_run:
        print(render_text(digest, cfg))
        if discord:
            print("\n--- Discord payloads (webhook not called) ---")
            print(json.dumps(discord.payloads(digest), indent=2, ensure_ascii=False))
        return EXIT_OK

    if not digest.hits and not cfg.send_when_empty:
        log.info("nothing to send")
        return EXIT_OK
    if discord:
        try:
            discord.send(digest)
        except NotifyError as e:
            log.error("%s", e)
            return EXIT_NOTIFY
        log.info("sent to discord")
    return EXIT_OK
