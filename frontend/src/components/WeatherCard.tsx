import type { Resort, Weather } from "../api/types";
import { resortLocation } from "./ResortPicker";

function fmt(value: number | null | undefined, suffix = ""): string {
  return value === null || value === undefined ? "—" : `${value}${suffix}`;
}

function Stat({ label, value, unit, highlight }: { label: string; value: string; unit?: string; highlight?: boolean }) {
  return (
    <div className={`stat${highlight ? " highlight" : ""}`}>
      <div className="value">
        {value}
        {unit && value !== "—" && <span className="unit">{unit}</span>}
      </div>
      <div className="label">{label}</div>
    </div>
  );
}

export function WeatherCard({ resort, weather }: { resort: Resort; weather: Weather }) {
  const { current, season, daily } = weather;
  const today = daily[0];
  const seasonLabel = season ? (season.in_season ? `Season ${season.label}` : `Last season (${season.label})`) : "Season";
  return (
    <section className="card" aria-labelledby="weather-heading">
      <h2 id="weather-heading">
        {resort.name}
        {current.conditions && <span className="conditions"> — {current.conditions}</span>}
      </h2>
      <p className="muted subtitle">
        {resortLocation(resort)} · Flies into {resort.airports.join(" / ")}
      </p>
      <div className="stats">
        <Stat label="Temperature" value={fmt(current.temperature)} unit="°F" />
        <Stat label="Snow depth" value={fmt(current.snow_depth)} unit={'"'} />
        <Stat label="Snow today" value={fmt(today?.snowfall)} unit={'"'} highlight={(today?.snowfall ?? 0) >= 6} />
        <Stat label={seasonLabel} value={fmt(season?.snowfall)} unit={'"'} />
        <Stat label="Wind" value={fmt(current.wind_speed)} unit=" mph" />
        <Stat label="Gusts" value={fmt(current.wind_gusts)} unit=" mph" />
      </div>
      {season?.through && <p className="muted footnote">Season snowfall through {season.through}.</p>}
    </section>
  );
}
