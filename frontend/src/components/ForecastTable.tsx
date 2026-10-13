import type { DailyWeather } from "../api/types";
import { formatDay } from "../lib/dates";

export const POWDER_DAY_IN = 6;

interface Props {
  daily: DailyWeather[];
  onFlyIn: (date: string) => void;
}

export function ForecastTable({ daily, onFlyIn }: Props) {
  return (
    <section className="card" aria-labelledby="forecast-heading">
      <h3 id="forecast-heading">{daily.length}-Day Forecast</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Conditions</th>
              <th scope="col">High / Low</th>
              <th scope="col">Snow</th>
              <th scope="col">
                <span className="visually-hidden">Trip</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {daily.map((day) => {
              const powder = (day.snowfall ?? 0) >= POWDER_DAY_IN;
              return (
                <tr key={day.date} className={powder ? "powder" : undefined}>
                  <td>{formatDay(day.date)}</td>
                  <td>{day.conditions ?? "—"}</td>
                  <td>
                    {day.temp_max ?? "—"}° / {day.temp_min ?? "—"}°F
                  </td>
                  <td>{day.snowfall === null ? "—" : `${day.snowfall}"`}</td>
                  <td>
                    <button type="button" className="link-button" onClick={() => onFlyIn(day.date)}>
                      Fly in for this
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
