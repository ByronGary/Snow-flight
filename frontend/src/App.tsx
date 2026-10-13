import { useEffect, useState } from "react";
import { query } from "./api/client";
import type { FlightLinks, NearbyAirports, PassType, PowderBoard as Board, Resort, Weather } from "./api/types";
import { FlightsPanel } from "./components/FlightsPanel";
import { ForecastTable } from "./components/ForecastTable";
import { OriginSearch } from "./components/OriginSearch";
import { PassToggle } from "./components/PassToggle";
import { PowderBoard } from "./components/PowderBoard";
import { ResortPicker } from "./components/ResortPicker";
import { TripDates } from "./components/TripDates";
import { WeatherCard } from "./components/WeatherCard";
import { useApi } from "./hooks/useApi";
import { useUrlState } from "./hooks/useUrlState";
import { addDays, maxDate, today } from "./lib/dates";

const MAX_DESTINATIONS = 3;

/** "10001", "10001-", "10001-12" and "10001-1234" all look up 10001; null until 5 digits are typed. */
function lookupZip(raw: string): string | null {
  const m = /^(\d{5})(-\d{0,4})?$/.exec(raw.trim());
  return m ? m[1] : null;
}

function zipFormatError(raw: string): string | null {
  const s = raw.trim();
  return s && !/^\d{0,5}(-\d{0,4})?$/.test(s) ? "Enter a 5-digit US ZIP code." : null;
}

export function App() {
  const [state, update] = useUrlState();

  const resortsReq = useApi<{ resorts: Resort[] }>("/api/resorts");
  const resorts = resortsReq.data?.resorts ?? [];
  const resort = resorts.find((r) => r.slug === state.resort) ?? null;
  // A resort from a shared link decides the pass, so the toggle and list always agree.
  const pass: PassType = resort?.pass ?? state.pass;

  const zip = lookupZip(state.zip);
  const zipError = zipFormatError(state.zip);
  const nearbyUrl = zip ? `/api/airports/nearby${query({ zip, radius: state.radius })}` : null;
  const nearby = useApi<NearbyAirports>(nearbyUrl);
  const [excluded, setExcluded] = useState<string[]>([]);
  useEffect(() => setExcluded([]), [nearbyUrl]);
  const origins = (nearby.data?.airports ?? []).map((a) => a.iata).filter((i) => !excluded.includes(i));

  const weather = useApi<Weather>(resort ? `/api/resorts/${resort.slug}/weather` : null);
  // The powder board is the landing view, shown until a resort is picked.
  const board = useApi<Board>(resort || !resortsReq.data ? null : `/api/powder${query({ pass, days: 5 })}`);

  const datesOk = state.depart >= today() && state.ret >= state.depart;
  const flightsUrl =
    resort && origins.length > 0 && datesOk
      ? `/api/flights${query({
          origins: origins.join(","),
          dest: resort.airports.slice(0, MAX_DESTINATIONS).join(","),
          depart: state.depart,
          return: state.ret,
        })}`
      : null;
  const flights = useApi<FlightLinks>(flightsUrl);

  let flightsPrompt: string | null = null;
  if (!zip) flightsPrompt = "Enter your home ZIP code to see flights.";
  else if (nearby.error) flightsPrompt = "Fix the ZIP code above to see flights.";
  else if (nearby.data && origins.length === 0) flightsPrompt = "Select at least one airport to fly from.";
  else if (!datesOk) flightsPrompt = "Choose travel dates from today onward.";

  const flyIn = (date: string) => {
    const depart = maxDate(today(), addDays(date, -1));
    update({ depart, ret: addDays(depart, 3) });
    document.getElementById("flights-heading")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <header className="site-header">
        <h1>Snow Flights</h1>
        <p className="tagline">Forecasts and flights for Ikon and Epic resorts</p>
      </header>
      <main>
        <section className="card search" aria-label="Search">
          <div className="search-top">
            <PassToggle
              value={pass}
              onChange={(p) => update({ pass: p, resort: resort?.pass === p ? resort.slug : null })}
            />
            <ResortPicker
              resorts={resorts}
              pass={pass}
              selected={resort}
              onSelect={(r) => update({ resort: r?.slug ?? null, pass: r?.pass ?? pass })}
            />
          </div>
          <div className="search-bottom">
            <OriginSearch
              zip={state.zip}
              radius={state.radius}
              zipError={zipError}
              nearby={nearby}
              excluded={excluded}
              onZipChange={(z) => update({ zip: z })}
              onRadiusChange={(radius) => update({ radius })}
              onToggleAirport={(iata) =>
                setExcluded((ex) => (ex.includes(iata) ? ex.filter((i) => i !== iata) : [...ex, iata]))
              }
            />
            <TripDates depart={state.depart} ret={state.ret} onChange={({ depart, ret }) => update({ depart, ret })} />
          </div>
        </section>

        {resortsReq.error && <p className="error">Couldn't load resorts: {resortsReq.error.message}</p>}
        {!resort && !resortsReq.loading && !resortsReq.error && (
          <>
            <PowderBoard
              pass={pass}
              board={board}
              onSelect={(slug) => update({ resort: slug, pass: resorts.find((r) => r.slug === slug)?.pass ?? pass })}
            />
            <p className="empty muted">Pick a resort above, or one from the list, to see its forecast and flights.</p>
          </>
        )}

        {resort && (
          <>
            {weather.loading && <section className="card muted">Loading weather…</section>}
            {weather.error && (
              <section className="card">
                <p className="error">{weather.error.message}</p>
              </section>
            )}
            {weather.data && (
              <>
                <WeatherCard resort={resort} weather={weather.data} />
                <ForecastTable daily={weather.data.daily} onFlyIn={flyIn} />
              </>
            )}
            <FlightsPanel resort={resort} links={flights} prompt={flightsPrompt} />
          </>
        )}
      </main>
      <footer className="site-footer muted">
        Weather from Open-Meteo. Flight searches open in Google Flights.
      </footer>
    </>
  );
}
