# Snow Flights

Snow forecasts and Google Flights searches for Ikon and Epic pass resorts (99 resorts in 14 countries), plus a daily Discord **powder alert** when a resort you watch is about to get dumped on.

- **Web app** (React): opens on a **powder board** ranking your pass's resorts by forecast snow over the next 5 days. Pick a resort and enter your home ZIP to get its forecast, season snowfall, and one-click Google Flights searches from every airport near you, into each of the resort's arrival airports (e.g. Vail: Eagle, then Denver).
- **Powder alerts**: a daily job checks the forecast for your watched resorts and posts to a Discord channel when one crosses your threshold. Each post includes flight links for the night before the big day.

## Quick start

Requires Python 3.12+ and Node 24+.

```bash
python -m venv .venv
make install            # pip install -r requirements-dev.txt && npm ci
make build              # build the React app into frontend/dist
make dev-api            # Flask on http://localhost:8000 (serves the built app + /api)
```

For frontend work, run `make dev-api` and `make dev-web` side by side. `dev-web` starts Vite with hot reload on http://localhost:5173 and proxies `/api` to Flask. If port 8000 is taken, pass the same port to both, e.g. `make dev-api API_PORT=8010` and `make dev-web API_PORT=8010`.

## Tests

```bash
make test               # pytest + Vitest
make lint               # ruff + TypeScript type check
make test-e2e           # Playwright: real Flask API + built app in Chromium (desktop + mobile)
make test-network       # live check that Google Flights still renders our links
```

The first time you run `make test-e2e`, install a browser with `cd frontend && npx playwright install chromium`.

- **pytest** covers:
  - the Google Flights link encoder: each link is decoded and checked, and one URL is pinned to a value verified against Google;
  - airport lookup for 44 major-city ZIP codes;
  - weather parsing, using recorded Open-Meteo responses;
  - every API endpoint;
  - the alerts logic, Discord payloads, and CLI.
- **Vitest + Testing Library** covers the pass toggle and resort search, ZIP and airport selection, trip dates, flight links, and the powder board.
- **Playwright** runs the same flows in a real browser against the real API, with only the weather stubbed. It decodes each Google Flights link to check the airports and dates, and checks that the page never scrolls sideways on a phone.
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs all of the above plus a Docker build and smoke test. A weekly workflow runs the live Google Flights check.
- Network tests are skipped by default. Google sometimes serves throttled pages to scripts, so if a network test fails, open the printed URL in a browser before concluding the link format changed.

## How the flight links work

Google retired the old `google.com/flights#flt=DEN.SLC.2026-12-10` links; they now land on a blank search. The app builds the current format, `https://www.google.com/travel/flights/search?tfs=…`, in [src/snow_flights/flights.py](src/snow_flights/flights.py).

The `tfs` value is a small base64 protobuf that the module hand-encodes; there's no extra dependency. It holds the airports, dates, trip type and passengers.

- Several origins can go in one search, so "LGA/EWR/JFK → EGE" is a single link.
- Each link also has a text-search fallback (`?q=Flights to EGE from LGA on …`) in case Google changes the format again.

## Arrival airports

Each resort lists 1-3 arrival airports, best first. They were picked by hand rather than by distance, because the nearest airport is often the wrong answer:
- Mammoth's own airport (MMH) lost airline service in 2018, so it uses Bishop (BIH), then Reno.
- Turin is the closest airport to Val d'Isère, but the pass road is closed in winter, so it uses Geneva, Lyon and Chambéry.
- Big hubs are added as cheaper alternates, e.g. Denver for Vail and Aspen.

The flights panel gives each arrival airport its own search.

## Origin airports

Airports come from [OurAirports](https://ourairports.com/data/) (`src/snow_flights/data/airports.csv`). Home airports must be US large or medium airports with scheduled service. A denylist removes general-aviation and business-jet fields that OurAirports marks as scheduled (Teterboro, Rocky Mountain Metro, Boeing Field, and others).

Lookup rules:
- The default radius is 50 miles; the UI also offers 25 and 100.
- Large airports are ranked before medium ones, and the closest 5 are shown.
- If none are in range, the nearest 3 within 250 miles are shown instead.
- ZIP+4 codes are accepted.

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness and readiness check. |
| `GET /api/resorts?pass=ikon\|epic` | Resorts with slug, name, pass, region, coordinates and arrival airports (`destinations`: name and distance from the resort). |
| `GET /api/powder?pass=ikon&days=5` | Every resort ranked by forecast snowfall, with daily amounts. One upstream weather call for the whole pass. |
| `GET /api/resorts/<slug>/weather?days=7` | Current conditions, a daily forecast in the resort's local time, and season-to-date snowfall. |
| `GET /api/airports/nearby?zip=10001&radius=50&limit=5` | Home airports near a ZIP code. |
| `GET /api/flights?origins=JFK,LGA&dest=EGE&depart=2026-12-10&return=2026-12-14` | Google Flights links: one combined search, one per origin, and a fallback. |

Errors are always returned as `{"error": {"code": "...", "message": "..."}}`.

Seasons run from Oct 1 to Jun 30 in the northern hemisphere and from Apr 1 to Nov 30 in the southern. Off-season, the app shows last season's total.

## Powder alerts (Discord)

1. In Discord, open **Server Settings → Integrations → Webhooks → New Webhook**, choose the channel, and copy the URL. Anyone who has this URL can post to the channel, so keep it secret.
2. Copy [config/alerts.example.yaml](config/alerts.example.yaml). Set your home airports or ZIP, the thresholds (inches in a single day and/or over the window), and the resort slugs to watch. Slugs are listed by `GET /api/resorts`.
3. Try it out:
   ```bash
   PYTHONPATH=src python -m snow_flights alerts --config my-alerts.yaml --dry-run    # print, don't send
   DISCORD_WEBHOOK_URL=... PYTHONPATH=src python -m snow_flights alerts --config my-alerts.yaml --test-notify
   ```

Alert behaviour:
- Each run sends at most one digest.
- Nothing is sent when no resort crosses its threshold, unless `send_when_empty: true`.
- Exit codes: `0` OK, `2` config error, `3` weather unavailable, `4` Discord failed.

The notifier interface (`Notifier` in [src/snow_flights/alerts/notifiers.py](src/snow_flights/alerts/notifiers.py)) is ready for an SMS backend later.

## Deploy

```bash
docker build -t your-registry/snow-flights:$(git rev-parse --short HEAD) .
kubectl create secret generic snow-flights-discord \
  --from-literal=DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
# set the image tag in k8s/kustomization.yaml, and your watch list in k8s/alerts.yaml
kubectl apply -k k8s/
kubectl create job --from=cronjob/snow-flights-powder-alerts powder-test   # try the alert job now
```

The image is a two-stage build: Node builds the React app, then a Python 3.12 runtime runs gunicorn. The ZIP-code data is baked in, so the container runs as a non-root user with a read-only root filesystem.

The k8s manifests define:
- a 2-replica Deployment with health probes;
- a daily CronJob at 6:00 America/Denver;
- a ConfigMap generated from `k8s/alerts.yaml`.

## Layout

```
src/snow_flights/   Flask app + API, flights/airports/weather modules, alerts package, data files
frontend/           Vite + React + TypeScript UI
tests/              pytest suite (fixtures are recorded Open-Meteo responses)
config/             example alert config
k8s/                Deployment, Service, CronJob, kustomization
```

Weather data: [Open-Meteo](https://open-meteo.com/) (free for non-commercial use). ZIP codes: GeoNames via pgeocode.

## License

MIT
