PY ?= .venv/bin/python
API_PORT ?= 8000
export PYTHONPATH := src

.PHONY: install dev-api dev-web build test test-py test-web test-e2e test-network lint alerts-dry-run docker

install:
	$(PY) -m pip install -r requirements-dev.txt
	cd frontend && npm ci

dev-api:  ## Flask API on :$(API_PORT) (serves frontend/dist if built)
	FLASK_DEBUG=true $(PY) -m flask --app "snow_flights.app:create_app()" run --port $(API_PORT)

dev-web:  ## Vite dev server on :5173, proxying /api to :$(API_PORT)
	cd frontend && API_PORT=$(API_PORT) npm run dev

build:
	cd frontend && npm run build

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
	$(PY) -m ruff check src tests
	cd frontend && npm run typecheck

alerts-dry-run:
	$(PY) -m snow_flights alerts --config config/alerts.example.yaml --dry-run

docker:
	docker build -t snow-flights .
