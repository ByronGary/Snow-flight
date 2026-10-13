import type { NearbyAirports } from "../api/types";
import type { FetchState } from "../hooks/useApi";
import { RADII } from "../hooks/useUrlState";

interface Props {
  zip: string;
  radius: number;
  zipError: string | null;
  nearby: FetchState<NearbyAirports>;
  excluded: string[];
  onZipChange: (zip: string) => void;
  onRadiusChange: (radius: number) => void;
  onToggleAirport: (iata: string) => void;
}

function lookupMessage(nearby: FetchState<NearbyAirports>): string | null {
  if (!nearby.error) return null;
  if (nearby.error.code === "zip_not_found") return "We couldn't find that ZIP code.";
  return nearby.error.message;
}

export function OriginSearch(props: Props) {
  const { zip, radius, zipError, nearby, excluded, onZipChange, onRadiusChange, onToggleAirport } = props;
  const data = nearby.data;
  const error = zipError ?? lookupMessage(nearby);

  return (
    <div className="origin-search">
      <div className="field-row">
        <div className="field">
          <label className="field-label" htmlFor="zip">
            Home ZIP
          </label>
          <input
            id="zip"
            className="text-input zip-input"
            type="text"
            inputMode="numeric"
            autoComplete="postal-code"
            placeholder="e.g. 10001"
            maxLength={10}
            value={zip}
            aria-invalid={error ? true : undefined}
            aria-describedby="zip-status"
            onChange={(e) => onZipChange(e.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="radius">
            Airports within
          </label>
          <select
            id="radius"
            className="select-input"
            value={radius}
            onChange={(e) => onRadiusChange(Number(e.target.value))}
          >
            {RADII.map((r) => (
              <option key={r} value={r}>
                {r} miles
              </option>
            ))}
          </select>
        </div>
      </div>

      <div id="zip-status" className="field-status" aria-live="polite">
        {error && <p className="error">{error}</p>}
        {!error && nearby.loading && <p className="muted">Finding airports…</p>}
        {!error && data && data.expanded && data.airports.length > 0 && (
          <p className="notice">
            No airports within {data.radius} miles of {data.place}. Showing the nearest instead.
          </p>
        )}
        {!error && data && data.airports.length === 0 && (
          <p className="error">No commercial airports found near {data.place || data.zip}.</p>
        )}
      </div>

      {data && data.airports.length > 0 && (
        <fieldset className="airport-chips">
          <legend className="field-label">
            Fly from <span className="muted">({data.place})</span>
          </legend>
          {data.airports.map((a) => (
            <label key={a.iata} className="chip" title={a.name}>
              <input
                type="checkbox"
                checked={!excluded.includes(a.iata)}
                onChange={() => onToggleAirport(a.iata)}
              />
              <span>
                <strong>{a.iata}</strong> <span className="muted">{a.dist_mi} mi</span>
              </span>
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
