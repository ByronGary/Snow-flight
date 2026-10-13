"""Decide which watched resorts have enough forecast snow to alert on."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from ..data import Resort, get_resort
from ..flights import MAX_DESTINATIONS, flight_links
from .config import AlertConfig

DailySnow = tuple[date, float]


@dataclass(frozen=True)
class PowderHit:
    resort: Resort
    days: tuple[DailySnow, ...]
    trigger_days: tuple[date, ...]
    peak: DailySnow
    total_in: float
    depart: date
    ret: date
    links: dict | None


@dataclass(frozen=True)
class Digest:
    today: date
    window_days: int
    origins: tuple[str, ...]
    hits: tuple[PowderHit, ...]
    errors: tuple[str, ...] = ()
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def evaluate(
    forecasts: Mapping[str, Sequence[DailySnow]],
    cfg: AlertConfig,
    today: date,
    origins: Sequence[str] = (),
    errors: Sequence[str] = (),
) -> Digest:
    """Pure: forecasts (slug -> daily snowfall) + config -> digest of hits, biggest first."""
    hits: list[PowderHit] = []
    for watch in cfg.resorts:
        days = tuple(forecasts.get(watch.slug, ()))[: cfg.window_days]
        if not days:
            continue
        total = round(sum(snow for _, snow in days), 1)
        daily_min, total_min = watch.thresholds.min_daily_in, watch.thresholds.min_total_in
        big_days = tuple(d for d, snow in days if daily_min is not None and snow >= daily_min)
        total_hit = total_min is not None and total >= total_min
        if not big_days and not total_hit:
            continue
        snowy_days = big_days or tuple(d for d, snow in days if snow > 0) or (days[0][0],)
        depart = max(today, snowy_days[0] - timedelta(days=cfg.depart_days_before))
        ret = depart + timedelta(days=cfg.nights)
        resort = get_resort(watch.slug)
        links = (flight_links(origins, resort.airports[:MAX_DESTINATIONS], depart, ret)
                 if origins else None)
        hits.append(PowderHit(
            resort=resort,
            days=days,
            trigger_days=big_days,
            peak=max(days, key=lambda d: d[1]),
            total_in=total,
            depart=depart,
            ret=ret,
            links=links,
        ))
    hits.sort(key=lambda h: (-h.total_in, h.resort.name))
    return Digest(today=today, window_days=cfg.window_days, origins=tuple(origins),
                  hits=tuple(hits), errors=tuple(errors))


def _day(d: date) -> str:
    return f"{d:%a} {d.month}/{d.day}"


def headline(digest: Digest, cfg: AlertConfig) -> str:
    if not digest.hits:
        return f"No powder alerts for the next {digest.window_days} days."
    n = len(digest.hits)
    t = cfg.thresholds
    rule = f'≥ {t.min_daily_in:g}" in a day' if t.min_daily_in else f'≥ {t.min_total_in:g}" total'
    return f"Powder alert: {n} resort{'s' if n != 1 else ''} with {rule} in the next {digest.window_days} days"


def render_text(digest: Digest, cfg: AlertConfig) -> str:
    """Plain-text digest, used for dry runs and any text-only notifier."""
    lines = [headline(digest, cfg)]
    for hit in digest.hits:
        r = hit.resort
        lines.append("")
        lines.append(f'{r.name} ({r.region}, {r.country}): {hit.total_in:g}" over {len(hit.days)} days, '
                     f'biggest {_day(hit.peak[0])} {hit.peak[1]:g}"')
        lines.append("  " + "  ".join(f'{_day(d)} {snow:.1f}"' for d, snow in hit.days))
        if hit.links:
            lines.append(f"  Flights {_day(hit.depart)} → {_day(hit.ret)}:")
            for dest in hit.links["destinations"]:
                lines.append(f"    {dest['all_origins']['label']}: {dest['all_origins']['url']}")
    for err in digest.errors:
        lines.append(f"\nWarning: {err}")
    return "\n".join(lines)
