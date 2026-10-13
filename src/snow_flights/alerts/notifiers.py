"""Where alerts go. v1 ships Discord; add an SMS notifier by implementing ``Notifier``."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urlencode

import requests

from .config import AlertConfig
from .powder import Digest, PowderHit, headline, render_text

EMBED_COLOR = 0x3B82F6
MAX_EMBEDS_PER_MESSAGE = 10
MAX_MESSAGE_CHARS = 6000
MAX_FIELD_CHARS = 1024
MAX_TITLE_CHARS = 256
MAX_RETRY_AFTER_S = 30


class NotifyError(RuntimeError):
    pass


class Notifier(Protocol):
    name: str

    def send(self, digest: Digest) -> None: ...


class ConsoleNotifier:
    name = "console"

    def __init__(self, cfg: AlertConfig, out: Callable[[str], None] = print):
        self.cfg, self.out = cfg, out

    def send(self, digest: Digest) -> None:
        self.out(render_text(digest, self.cfg))


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def app_link(cfg: AlertConfig, hit: PowderHit) -> str | None:
    """Deep link into the React UI with the resort, home ZIP and trip dates filled in."""
    if not cfg.app_url:
        return None
    params = {"resort": hit.resort.slug, "depart": hit.depart.isoformat(), "return": hit.ret.isoformat()}
    if cfg.home_zip:
        params["zip"] = cfg.home_zip
        params["radius"] = cfg.radius_mi
    return f"{cfg.app_url}/?{urlencode(params)}"


def _embed_chars(embed: dict) -> int:
    return (len(embed.get("title", "")) + len(embed.get("description", ""))
            + len(embed.get("footer", {}).get("text", ""))
            + sum(len(f["name"]) + len(f["value"]) for f in embed.get("fields", [])))


def build_embed(cfg: AlertConfig, hit: PowderHit, generated_at: str) -> dict:
    r = hit.resort
    peak_day, peak_snow = hit.peak
    forecast = "\n".join(f'{d:%a %m/%d}  {snow:>4.1f}"' for d, snow in hit.days)
    embed = {
        "title": _truncate(f'{r.name} ({r.region}): {hit.total_in:g}" in {len(hit.days)} days', MAX_TITLE_CHARS),
        "color": EMBED_COLOR,
        "description": f'Biggest day: {peak_day:%a %b} {peak_day.day}, {peak_snow:g}"',
        "fields": [{"name": "Forecast", "value": _truncate(f"```\n{forecast}\n```", MAX_FIELD_CHARS)}],
        "footer": {"text": "Weather data by Open-Meteo.com (CC BY 4.0)"},
        "timestamp": generated_at,
    }
    url = app_link(cfg, hit)
    if url:
        embed["url"] = url
    if hit.links:
        lines = []
        for dest in hit.links["destinations"]:
            line = f"[{dest['all_origins']['label']}]({dest['all_origins']['url']})"
            if sum(len(x) + 1 for x in lines) + len(line) > MAX_FIELD_CHARS:
                break
            lines.append(line)
        embed["fields"].append({
            "name": f"Flights {hit.depart:%b} {hit.depart.day} – {hit.ret:%b} {hit.ret.day}",
            "value": "\n".join(lines),
        })
    return embed


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str, cfg: AlertConfig, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self._url = webhook_url
        self.cfg = cfg
        self._session = session or requests.Session()
        self._sleep = sleep

    def payloads(self, digest: Digest) -> list[dict]:
        """Split the digest into messages that respect Discord's embed and size limits."""
        stamp = digest.generated_at.isoformat()
        embeds = [build_embed(self.cfg, hit, stamp) for hit in digest.hits]
        if digest.errors:
            embeds.append({"title": "Warnings", "color": 0xF59E0B,
                           "description": _truncate("\n".join(digest.errors), 4096)})
        content = headline(digest, self.cfg)
        messages: list[list[dict]] = [[]]
        chars = len(content)
        for embed in embeds:
            size = _embed_chars(embed)
            if len(messages[-1]) >= MAX_EMBEDS_PER_MESSAGE or chars + size > MAX_MESSAGE_CHARS:
                messages.append([])
                chars = 0
            messages[-1].append(embed)
            chars += size
        return [
            {
                "username": self.cfg.discord_username,
                "allowed_mentions": {"parse": []},
                **({"content": content} if i == 0 else {}),
                "embeds": batch,
            }
            for i, batch in enumerate(messages)
        ]

    def _post(self, payload: dict) -> None:
        for attempt in range(2):
            try:
                resp = self._session.post(self._url, params={"wait": "true"}, json=payload, timeout=10)
            except requests.RequestException as e:
                # The exception text can include the webhook URL, which is a secret.
                raise NotifyError(f"Discord request failed ({type(e).__name__})") from None
            if resp.status_code == 429 and attempt == 0:
                try:
                    retry_after = float(resp.json().get("retry_after", 1))
                except ValueError:
                    retry_after = 1.0
                self._sleep(min(retry_after, MAX_RETRY_AFTER_S))
                continue
            if resp.status_code >= 400:
                raise NotifyError(f"Discord returned HTTP {resp.status_code}")
            return

    def send(self, digest: Digest) -> None:
        for payload in self.payloads(digest):
            self._post(payload)

    def send_test(self) -> None:
        self._post({
            "username": self.cfg.discord_username,
            "allowed_mentions": {"parse": []},
            "content": "Snow Flights webhook OK: powder alerts will be posted here.",
        })
