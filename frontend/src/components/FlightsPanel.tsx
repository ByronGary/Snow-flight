import type { FlightLinks, Resort } from "../api/types";
import type { FetchState } from "../hooks/useApi";
import { formatDay } from "../lib/dates";

interface Props {
  resort: Resort;
  links: FetchState<FlightLinks>;
  prompt: string | null;
}

export function FlightsPanel({ resort, links, prompt }: Props) {
  const data = links.data;
  const info = (iata: string) => resort.destinations.find((d) => d.iata === iata);
  return (
    <section className="card" aria-labelledby="flights-heading">
      <h3 id="flights-heading">
        Flights
        {data && (
          <span className="muted">
            {" "}
            · {formatDay(data.depart)}
            {data.return && ` – ${formatDay(data.return)}`}
          </span>
        )}
      </h3>
      {prompt && <p className="muted">{prompt}</p>}
      {!prompt && links.loading && <p className="muted">Building searches…</p>}
      {!prompt && links.error && <p className="error">{links.error.message}</p>}
      {!prompt &&
        data?.destinations.map((dest) => (
          <div key={dest.iata} className="destination">
            {data.destinations.length > 1 && (
              <h4 className="destination-name">
                Into {dest.iata}
                {info(dest.iata) && (
                  <span className="muted">
                    {" "}
                    · {info(dest.iata)!.name} · {info(dest.iata)!.dist_mi} mi from {resort.name}
                  </span>
                )}
              </h4>
            )}
            <a className="flight-button" href={dest.all_origins.url} target="_blank" rel="noopener noreferrer">
              {data.origins.length > 1 ? `Search all ${data.origins.length} airports` : "Search flights"}:{" "}
              {dest.all_origins.label} ↗
            </a>
            {dest.by_origin.length > 1 && (
              <ul className="origin-links">
                {dest.by_origin.map((o) => (
                  <li key={o.origin}>
                    <a href={o.url} target="_blank" rel="noopener noreferrer">
                      {o.label}
                    </a>
                  </li>
                ))}
              </ul>
            )}
            <p className="fallback">
              Results not loading?{" "}
              <a href={dest.all_origins.fallback_url} target="_blank" rel="noopener noreferrer">
                Try Google's text search
              </a>
            </p>
          </div>
        ))}
    </section>
  );
}
