// Response shapes of the Flask JSON API (src/snow_flights/api.py).

export type PassType = "ikon" | "epic";

export interface DestinationAirport {
  iata: string;
  name: string;
  city: string;
  /** Straight-line distance from the resort. */
  dist_mi: number;
}

export interface Resort {
  slug: string;
  name: string;
  pass: PassType;
  country: string;
  region: string;
  lat: number;
  lon: number;
  /** Arrival airports, most useful first. */
  airports: string[];
  destinations: DestinationAirport[];
  hemisphere: "north" | "south";
}

export interface CurrentWeather {
  time: string;
  weather_code: number | null;
  conditions: string | null;
  is_day: boolean;
  temperature: number | null;
  snowfall: number | null;
  precipitation: number | null;
  wind_speed: number | null;
  wind_gusts: number | null;
  snow_depth: number | null;
}

export interface DailyWeather {
  date: string;
  weather_code: number | null;
  conditions: string | null;
  snowfall: number | null;
  precipitation: number | null;
  temp_max: number | null;
  temp_min: number | null;
}

export interface SeasonSnowfall {
  label: string;
  start: string;
  through: string | null;
  snowfall: number;
  in_season: boolean;
}

export interface Weather {
  resort: { slug: string; name: string };
  timezone: string | null;
  current: CurrentWeather;
  daily: DailyWeather[];
  season: SeasonSnowfall | null;
}

export interface NearbyAirport {
  iata: string;
  name: string;
  city: string;
  size: "large" | "medium" | "small";
  dist_mi: number;
}

export interface NearbyAirports {
  zip: string;
  place: string;
  lat: number;
  lon: number;
  radius: number;
  expanded: boolean;
  airports: NearbyAirport[];
}

export interface FlightLink {
  label: string;
  url: string;
  fallback_url: string;
}

export interface FlightDestination {
  iata: string;
  primary: boolean;
  all_origins: FlightLink;
  by_origin: (FlightLink & { origin: string })[];
}

export interface FlightLinks {
  depart: string;
  return: string | null;
  trip: "round_trip" | "one_way";
  adults: number;
  origins: string[];
  destinations: FlightDestination[];
}

export interface PowderRow {
  slug: string;
  name: string;
  pass: PassType;
  region: string;
  country: string;
  total_in: number;
  peak: { date: string; snowfall: number } | null;
  daily: { date: string; snowfall: number }[];
}

export interface PowderBoard {
  days: number;
  resorts: PowderRow[];
}
