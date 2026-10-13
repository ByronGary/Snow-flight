# Snow Flights

Snow forecasts and Google Flights searches for Ikon and Epic pass resorts (99 resorts in 14 countries), plus a daily Discord **powder alert** when a resort you watch is about to get dumped on.

- **Web app** (React): opens on a **powder board** ranking your pass's resorts by forecast snow over the next 5 days. Pick a resort and enter your home ZIP to get its forecast, season snowfall, and one-click Google Flights searches from every airport near you, into each of the resort's arrival airports (e.g. Vail: Eagle, then Denver).
- **Powder alerts**: a daily job (cron on your machine, or a Kubernetes CronJob) checks the forecast for your watched resorts and posts to a Discord channel when one crosses your threshold. Each post includes flight links for the night before the big day.

## Run it locally

Everything runs on your own machine with Python 3.12+ and Node 24+. Docker and Kubernetes are optional, for hosting it somewhere (see [Hosting](#hosting-optional-docker-or-kubernetes)).

```bash
python3 -m venv .venv
make install            # Python and frontend dependencies
make dev                # React UI with hot reload: http://localhost:5173
```

`make dev` starts the Flask API on port 8010 and the Vite dev server on port 5173, which forwards `/api` requests to Flask. Ctrl+C stops both.

| Command | What runs | Open |
|---|---|---|
| `make dev` | React dev server (hot reload) + Flask API | http://localhost:5173 |
| `make serve` | Builds the app, then Flask serves it alone (no Node process) | http://localhost:8010 |

To use a different API port, pass `API_PORT`, e.g. `make dev API_PORT=8020`.

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
- ZIP+4 codes are accepted. ZIPs are looked up in a bundled file of US ZIP centroids (see [Data sources](#data-sources)), so nothing is downloaded at runtime.

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
   make alerts-dry-run ALERTS_CONFIG=my-alerts.yaml       # print the digest, send nothing
   DISCORD_WEBHOOK_URL=... PYTHONPATH=src .venv/bin/python -m snow_flights alerts --config my-alerts.yaml --test-notify
   DISCORD_WEBHOOK_URL=... make alerts ALERTS_CONFIG=my-alerts.yaml   # real run
   ```

Alert behaviour:
- Each run sends at most one digest.
- Nothing is sent when no resort crosses its threshold, unless `send_when_empty: true`.
- Exit codes: `0` OK, `2` config error, `3` weather unavailable, `4` Discord failed.

The notifier interface (`Notifier` in [src/snow_flights/alerts/notifiers.py](src/snow_flights/alerts/notifiers.py)) is ready for an SMS backend; see the [roadmap](#roadmap).

### Running alerts daily without Kubernetes

1. Put the webhook in a `.env` file, which is gitignored:
   ```bash
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
2. Add a cron entry with `crontab -e`:
   ```cron
   0 6 * * * cd /path/to/snow-flights && set -a && . ./.env && set +a && make alerts ALERTS_CONFIG=my-alerts.yaml >> alerts.log 2>&1
   ```

Cron only runs while the machine is on. On WSL, start it first with `sudo service cron start`.

## Hosting (optional): Docker or Kubernetes

You don't need either to use the app; they're for running it on a server.

**Docker only:**

```bash
docker build -t snow-flights .
docker run -p 8000:8000 snow-flights      # http://localhost:8000
```

**Kubernetes** (the web app plus the daily alert job):

```bash
docker build -t your-registry/snow-flights:$(git rev-parse --short HEAD) .
kubectl create secret generic snow-flights-discord \
  --from-literal=DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/...'
# set the image tag in k8s/kustomization.yaml, and your watch list in k8s/alerts.yaml
kubectl apply -k k8s/
kubectl create job --from=cronjob/snow-flights-powder-alerts powder-test   # try the alert job now
```

The image is a two-stage build: Node builds the React app, then a Python 3.12 runtime runs gunicorn. It's about 150 MB and uses about 115 MiB with two workers. All data files ship in the image, so the container runs as a non-root user with a read-only root filesystem.

The k8s manifests define:
- a 2-replica Deployment with health probes;
- a daily CronJob at 6:00 America/Denver;
- a ConfigMap generated from `k8s/alerts.yaml`.

## Layout

```
src/snow_flights/   Flask app + API, flights/airports/weather modules, alerts package, data files
frontend/           Vite + React + TypeScript UI (Vitest unit tests, Playwright e2e in frontend/e2e)
tests/              pytest suite (fixtures are recorded Open-Meteo responses)
scripts/            data builders (ZIP centroids)
config/             example alert config
k8s/                Deployment, Service, CronJob, kustomization
.github/workflows/  CI and the weekly Google Flights canary
```

## Data sources

| Data | Source | License | File |
|---|---|---|---|
| Weather | [Open-Meteo](https://open-meteo.com/) forecast and archive APIs | CC BY 4.0, free for non-commercial use | fetched at runtime and cached |
| Airports | [OurAirports](https://ourairports.com/data/) | Public domain | `src/snow_flights/data/airports.csv` |
| US ZIP centroids | [GeoNames](https://www.geonames.org/) postal codes | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | `src/snow_flights/data/us_zip_centroids.csv` |
| Resorts | curated for this project | MIT | `src/snow_flights/data/{ikon,epic}_resorts.json` |

The ZIP file covers 41,488 US ZIP codes: the 50 states, DC, military APO/FPO codes and a few Marshall Islands codes. Puerto Rico and other territories aren't included. To refresh it from GeoNames:

```bash
python scripts/build_zip_centroids.py
```

## Roadmap

**SMS alerts**
- Add a Twilio notifier next to `DiscordNotifier` that sends `render_text()`.
- Link to the web app (`app_url`) rather than raw Google Flights links: each `tfs` URL is 150+ characters, which uses up SMS segments.
- US numbers need A2P 10DLC or toll-free verification before Twilio will deliver. Approval can take days, so start that early.

**iOS app on the Apple App Store**
- Package the existing React app with Capacitor, or rewrite it in React Native if it needs more native features.
- Add native value so it doesn't get rejected as a plain website wrapper (App Review guideline 4.2):
  - push notifications for powder alerts, replacing or adding to Discord/SMS;
  - a home-screen widget showing the powder board;
  - home airports from the device's location instead of a ZIP code.
- Host the API publicly over HTTPS. The app needs a configurable API base URL (the web app uses relative `/api` paths), plus CORS and CSP `connect-src` entries for the app's origin.
- Needs an Apple Developer Program membership ($99/year), App Store privacy labels (location, if used), and APNs keys for push.

## License

MIT
