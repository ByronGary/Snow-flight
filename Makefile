# Everything here runs locally: no Docker or Kubernetes needed.
PY ?= .venv/bin/python
API_PORT ?= 8010
ALERTS_CONFIG ?= config/alerts.example.yaml
export PYTHONPATH := src

.PHONY: install dev dev-api dev-web build serve test test-py test-web test-e2e test-network lint \
	alerts alerts-dry-run docker

install:  ## Python + frontend dependencies (create .venv first: python3 -m venv .venv)
	$(PY) -m pip install -r requirements-dev.txt
	cd frontend && npm ci

dev:  ## React UI with hot reload on :5173 + API on :$(API_PORT). Ctrl+C stops both.
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory dev-api & \
	$(MAKE) --no-print-directory dev-web

dev-api:  ## Flask API on :$(API_PORT) (also serves frontend/dist if built)
	FLASK_DEBUG=true $(PY) -m flask --app "snow_flights.app:create_app()" run --port $(API_PORT)

dev-web:  ## Vite dev server on :5173, proxying /api to :$(API_PORT)
	cd frontend && API_PORT=$(API_PORT) npm run dev

build:
	cd frontend && npm run build

serve: build  ## Build the UI and serve it from Flask alone on :$(API_PORT)
	$(PY) -m flask --app "snow_flights.app:create_app()" run --port $(API_PORT)

test: test-py test-web

test-py:
	$(PY) -m pytest

test-web:
	cd frontend && npm test

test-e2e:  ## Playwright against the real API (weather stubbed)
	cd frontend && PYTHON=$(abspath $(PY)) npx playwright test

test-network:  ## live check that Google Flights still renders our links
	$(PY) -m pytest -m network

lint:
	$(PY) -m ruff check src tests scripts
	cd frontend && npm run typecheck

alerts-dry-run:  ## Print today's powder digest; sends nothing
	$(PY) -m snow_flights alerts --config $(ALERTS_CONFIG) --dry-run

alerts:  ## Check forecasts and post to Discord (needs DISCORD_WEBHOOK_URL)
	$(PY) -m snow_flights alerts --config $(ALERTS_CONFIG)

docker:  ## Optional: container image for hosting
	docker build -t snow-flights .
