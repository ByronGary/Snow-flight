# syntax=docker/dockerfile:1

# ---- Build the React frontend ----
FROM node:24-alpine AS web
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The type check covers the test helpers, which import the real resort data.
COPY src/snow_flights/data/ikon_resorts.json src/snow_flights/data/epic_resorts.json /repo/src/snow_flights/data/
RUN npm run build

# ---- Python runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    SNOW_FLIGHTS_STATIC_DIR=/app/static \
    SNOW_FLIGHTS_CACHE_DIR=/tmp/cache
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/
COPY --from=web /repo/frontend/dist ./static

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "30", \
     "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "snow_flights.app:create_app()"]
