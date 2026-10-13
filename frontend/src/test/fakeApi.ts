import { vi } from "vitest";
import epic from "../../../src/snow_flights/data/epic_resorts.json";
import ikon from "../../../src/snow_flights/data/ikon_resorts.json";
import type { FlightLinks, NearbyAirports, PowderBoard, Resort, Weather } from "../api/types";

interface RawResort {
  slug: string;
  name: string;
  pass: string;
  country: string;
  state?: string;
  province?: string;
  latitude: number;
  longitude: number;
  airports: string[];
}

const AIRPORT_NAMES: Record<string, string> = {
  EGE: "Eagle County Regional Airport",
  DEN: "Denver International Airport",
  SLC: "Salt Lake City International Airport",
};

// The real resort data, mapped the same way the API does, so counts can't drift.
export const RESORTS: Resort[] = ([...ikon, ...epic] as RawResort[]).map((r) => ({
  slug: r.slug,
  name: r.name,
  pass: r.pass as Resort["pass"],
  country: r.country,
  region: r.state ?? r.province ?? "",
  lat: r.latitude,
  lon: r.longitude,
  airports: r.airports,
  destinations: r.airports.map((iata, i) => ({
    iata, name: AIRPORT_NAMES[iata] ?? `${iata} Airport`, city: "", dist_mi: 25 + i * 60,
  })),
  hemisphere: r.latitude < 0 ? "south" : "north",
}));

export function weatherFor(slug: string): Weather {
  const resort = RESORTS.find((r) => r.slug === slug)!;
  return {
    resort: { slug, name: resort.name },
    timezone: "America/Denver",
    current: {
      time: "2026-12-09T09:00", weather_code: 73, conditions: "Moderate Snow", is_day: true,
      temperature: 21.3, snowfall: 0.2, precipitation: 0.02, wind_speed: 12, wind_gusts: 25.3, snow_depth: 38.2,
    },
    daily: Array.from({ length: 7 }, (_, i) => ({
      date: `2026-12-${String(9 + i).padStart(2, "0")}`,
      weather_code: 73,
      conditions: "Moderate Snow",
      snowfall: i === 2 ? 9.5 : 1.0,
      precipitation: 0.3,
      temp_max: 25,
      temp_min: 12,
    })),
    season: { label: "2026-27", start: "2026-10-01", through: "2026-12-06", snowfall: 42.1, in_season: true },
  };
}

const NYC: NearbyAirports = {
  zip: "10001", place: "New York, NY", lat: 40.75, lon: -73.99, radius: 50, expanded: false,
  airports: [
    { iata: "LGA", name: "LaGuardia Airport", city: "New York", size: "large", dist_mi: 6.8 },
    { iata: "EWR", name: "Newark Liberty International Airport", city: "Newark", size: "large", dist_mi: 10 },
    { iata: "JFK", name: "John F Kennedy International Airport", city: "New York", size: "large", dist_mi: 13.7 },
  ],
};

const VALENTINE: NearbyAirports = {
  zip: "69201", place: "Valentine, NE", lat: 42.8, lon: -100.5, radius: 50, expanded: true,
  airports: [{ iata: "PIR", name: "Pierre Regional Airport", city: "Pierre", size: "medium", dist_mi: 110.2 }],
};

function flightsFor(url: URL): FlightLinks {
  const origins = url.searchParams.get("origins")!.split(",");
  const dests = url.searchParams.get("dest")!.split(",");
  const depart = url.searchParams.get("depart")!;
  const ret = url.searchParams.get("return");
  const link = (o: string[], d: string) => ({
    label: `${o.join("/")} → ${d}`,
    url: `https://www.google.com/travel/flights/search?tfs=FAKE-${o.join("-")}-${d}-${depart}`,
    fallback_url: `https://www.google.com/travel/flights?q=Flights+to+${d}+from+${o[0]}`,
  });
  return {
    depart, return: ret, trip: ret ? "round_trip" : "one_way", adults: 1, origins,
    destinations: dests.map((d, i) => ({
      iata: d,
      primary: i === 0,
      all_origins: link(origins, d),
      by_origin: origins.map((o) => ({ origin: o, ...link([o], d) })),
    })),
  };
}

/** Snowiest first: Snowbird (Ikon) and Vail (Epic) lead; everything else gets a little. */
export function powderFor(pass: string | null, days: number, snow = true): PowderBoard {
  const resorts = RESORTS.filter((r) => !pass || r.pass === pass).map((r, i) => {
    const lead = r.slug === "snowbird" || r.slug === "vail";
    const daily = Array.from({ length: days }, (_, d) => ({
      date: `2026-12-${String(9 + d).padStart(2, "0")}`,
      snowfall: !snow ? 0 : lead ? (d === 1 ? 14 : 2) : Math.max(0, 3 - i * 0.05),
    }));
    const total = Math.round(daily.reduce((a, d) => a + d.snowfall, 0) * 10) / 10;
    const peak = daily.reduce((a, d) => (d.snowfall > a.snowfall ? d : a), daily[0]);
    return { slug: r.slug, name: r.name, pass: r.pass, region: r.region, country: r.country, total_in: total, peak, daily };
  });
  resorts.sort((a, b) => b.total_in - a.total_in || a.name.localeCompare(b.name));
  return { days, resorts };
}

export const fakeOptions = { snow: true };

function route(url: URL): { status: number; body: unknown } {
  const path = url.pathname;
  if (path === "/api/resorts") return { status: 200, body: { resorts: RESORTS } };
  const weather = /^\/api\/resorts\/([^/]+)\/weather$/.exec(path);
  if (weather) return { status: 200, body: weatherFor(weather[1]) };
  if (path === "/api/airports/nearby") {
    const zip = url.searchParams.get("zip");
    if (zip === "00000") {
      return { status: 404, body: { error: { code: "zip_not_found", message: "ZIP code 00000 was not found." } } };
    }
    return { status: 200, body: zip === "69201" ? VALENTINE : { ...NYC, zip: zip! } };
  }
  if (path === "/api/flights") return { status: 200, body: flightsFor(url) };
  if (path === "/api/powder") {
    const days = Number(url.searchParams.get("days") ?? 5);
    return { status: 200, body: powderFor(url.searchParams.get("pass"), days, fakeOptions.snow) };
  }
  return { status: 404, body: { error: { code: "not_found", message: "Not found" } } };
}

/** Replace global fetch with the fake API; returns the list of requested paths. */
export function installFakeApi() {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      calls.push(url.pathname + url.search);
      const { status, body } = route(url);
      return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}
