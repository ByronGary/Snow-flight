import { useRef, useState } from "react";
import type { PassType, PowderBoard as Board, PowderRow } from "../api/types";
import type { FetchState } from "../hooks/useApi";
import { formatDay } from "../lib/dates";

const TOP_N = 8;

interface Props {
  pass: PassType;
  board: FetchState<Board>;
  onSelect: (slug: string) => void;
}

function inches(v: number): string {
  return `${v}"`;
}

/** Ranked bars: forecast snowfall per resort over the next few days (one series, one hue). */
export function PowderBoard({ pass, board, onSelect }: Props) {
  // Refetching (e.g. switching pass) keeps the previous render, dimmed, instead of flashing empty.
  const last = useRef<Board | null>(null);
  if (board.data) last.current = board.data;
  const data = board.data ?? (board.loading ? last.current : null);
  const [active, setActive] = useState<string | null>(null);

  const passLabel = pass === "ikon" ? "Ikon" : "Epic";
  // The API already filters by pass and sorts by total; while refetching we keep the old rows.
  const rows = (data?.resorts ?? []).slice(0, TOP_N);
  const max = Math.max(0, ...rows.map((r) => r.total_in));

  return (
    <section className="card" aria-labelledby="powder-heading" aria-busy={board.loading || undefined}>
      <h3 id="powder-heading">
        Most snow in the next {data?.days ?? 5} days <span className="muted">· {passLabel} resorts</span>
      </h3>
      {board.error && <p className="error">{board.error.message}</p>}
      {!data && board.loading && <p className="muted">Checking forecasts…</p>}
      {data && max === 0 && (
        <p className="muted">
          No snow in the forecast for any {passLabel} resort over the next {data.days} days.
        </p>
      )}
      {data && max > 0 && (
        <>
          <ol className={`powder-list${board.loading ? " refreshing" : ""}`}>
            {rows.map((r) => (
              <li key={r.slug} className="powder-item">
                <button
                  type="button"
                  className="powder-row"
                  onClick={() => onSelect(r.slug)}
                  onPointerEnter={() => setActive(r.slug)}
                  onPointerLeave={() => setActive((a) => (a === r.slug ? null : a))}
                  onFocus={() => setActive(r.slug)}
                  onBlur={() => setActive((a) => (a === r.slug ? null : a))}
                  aria-label={`${r.name}: ${inches(r.total_in)} forecast over ${data.days} days`}
                >
                  <span className="powder-name">
                    {r.name} <span className="muted">{r.region}</span>
                  </span>
                  <span className="powder-plot" aria-hidden="true">
                    <span className="powder-bar" style={{ width: `${(r.total_in / max) * 100}%` }} />
                    <span className="powder-value">{inches(r.total_in)}</span>
                  </span>
                </button>
                {active === r.slug && <Tooltip row={r} />}
              </li>
            ))}
          </ol>
          <details className="powder-table">
            <summary>Daily breakdown</summary>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Resort</th>
                    {rows[0]?.daily.map((d) => (
                      <th key={d.date} scope="col">
                        {formatDay(d.date)}
                      </th>
                    ))}
                    <th scope="col">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.slug}>
                      <th scope="row">{r.name}</th>
                      {r.daily.map((d) => (
                        <td key={d.date}>{inches(d.snowfall)}</td>
                      ))}
                      <td>
                        <strong>{inches(r.total_in)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function Tooltip({ row }: { row: PowderRow }) {
  return (
    <div className="powder-tooltip" role="tooltip">
      <div className="tooltip-total">
        <strong>{inches(row.total_in)}</strong> <span className="muted">{row.name}</span>
      </div>
      <ul>
        {row.daily.map((d) => (
          <li key={d.date}>
            <strong>{inches(d.snowfall)}</strong> <span className="muted">{formatDay(d.date)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
