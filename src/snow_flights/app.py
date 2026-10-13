"""Flask app: the JSON API plus the built React frontend."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from flask import Flask, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException, NotFound

from .api import api, error_response
from .weather import WeatherClient

REPO_ROOT = Path(__file__).resolve().parents[2]

# Not in Python's default table; iOS/Android read the manifest to install the app.
mimetypes.add_type("application/manifest+json", ".webmanifest")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)


def default_static_dir() -> Path:
    return Path(os.environ.get("SNOW_FLIGHTS_STATIC_DIR") or REPO_ROOT / "frontend" / "dist")


def create_app(weather: WeatherClient | None = None, static_dir: Path | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    app.extensions["weather"] = weather or WeatherClient()
    # Absolute, because Flask resolves relative paths against the package, not the working dir.
    static_dir = Path(static_dir or default_static_dir()).resolve()
    app.register_blueprint(api)

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        return response

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        if request.path.startswith("/api/"):
            return error_response(e.code or 500, e.name.lower().replace(" ", "_"), e.description)
        return e

    @app.errorhandler(Exception)
    def unhandled_error(e: Exception):
        app.logger.exception("unhandled error")
        if request.path.startswith("/api/"):
            return error_response(500, "internal_error", "Something went wrong.")
        return "Internal Server Error", 500

    @app.get("/submit")
    @app.post("/submit")
    def old_form():
        return redirect("/", code=303)

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        response = send_from_directory(static_dir / "assets", filename, max_age=31536000)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str):
        if path.startswith("api/"):
            raise NotFound()
        if path and (static_dir / path).is_file():
            return send_from_directory(static_dir, path, max_age=3600)
        if not (static_dir / "index.html").is_file():
            return ("Frontend not built. Run `npm run build` in frontend/ "
                    "(or `make dev-web` for the Vite dev server).", 503)
        response = send_from_directory(static_dir, "index.html", max_age=0)
        response.headers["Cache-Control"] = "no-cache"
        return response

    return app


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    create_app().run(host="0.0.0.0", port=8000, debug=debug)
