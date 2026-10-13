# Third-party notices

Snow Flights' own code is MIT licensed (see [LICENSE](LICENSE)). This file lists the data and software it uses, and their licenses.

## Data

| Data | Source | License | What we do with it |
|---|---|---|---|
| Weather forecasts and history | [Open-Meteo](https://open-meteo.com/) API | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | Fetched at runtime and cached briefly. The free API is for **non-commercial use only**; a paid or commercial version needs an [Open-Meteo API plan](https://open-meteo.com/en/pricing). |
| US ZIP code locations | [GeoNames](https://www.geonames.org/) postal code dump | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | **Modified:** reduced to one centroid per ZIP code (duplicates averaged) in `src/snow_flights/data/us_zip_centroids.csv` by `scripts/build_zip_centroids.py`. |
| Airports | [OurAirports](https://ourairports.com/data/) | Public domain | Shipped unmodified as `src/snow_flights/data/airports.csv`; filtered at runtime. |
| Resorts and arrival airports | Compiled for this project | MIT (this repo) | `src/snow_flights/data/{ikon,epic}_resorts.json`. Ikon Pass and Epic Pass are trademarks of their owners; this project isn't affiliated with them. |

The web app's footer credits Open-Meteo, GeoNames and OurAirports and links to the CC BY 4.0 license, as attribution requires. Discord alerts credit Open-Meteo in each message.

Flight searches open on Google Flights. The app only builds links to it; no Google data is copied or stored.

## Software in the web app (sent to browsers)

All of these are bundled into the JavaScript the browser downloads. Their full license texts are generated at build time into `frontend/dist/third-party-licenses.txt`, served at `/third-party-licenses.txt` and linked from the app's footer.

| Package | License |
|---|---|
| react, react-dom, scheduler | MIT |
| downshift, compute-scroll-into-view | MIT |
| @babel/runtime | MIT |
| prop-types, react-is | MIT |

## Software on the server (Python, in the Docker image)

Installed from `requirements.txt`. Each package's own license file ships inside the image under `site-packages/*.dist-info/`.

| Package | License |
|---|---|
| Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, click | BSD-3-Clause |
| blinker | MIT |
| gunicorn | MIT |
| requests | Apache-2.0 |
| urllib3, charset-normalizer | MIT |
| idna | BSD-3-Clause |
| certifi | MPL-2.0 (used unmodified) |
| requests-cache | BSD-2-Clause |
| attrs, cattrs, platformdirs, url-normalize | MIT |
| PyYAML | MIT |
| typing_extensions | PSF-2.0 |

Development-only tools (pytest, ruff, Vite, TypeScript, Vitest, Playwright and so on) aren't shipped in the app or the image.
