import { addDays, maxDate, today } from "../lib/dates";

interface Props {
  depart: string;
  ret: string;
  onChange: (dates: { depart: string; ret: string }) => void;
}

export function TripDates({ depart, ret, onChange }: Props) {
  const min = today();
  return (
    <div className="field-row">
      <div className="field">
        <label className="field-label" htmlFor="depart">
          Depart
        </label>
        <input
          id="depart"
          className="text-input"
          type="date"
          min={min}
          value={depart}
          onChange={(e) => {
            const value = e.target.value;
            if (!value) return;
            // Keep the trip length when the departure moves past the return date.
            onChange({ depart: value, ret: ret < value ? addDays(value, 3) : ret });
          }}
        />
      </div>
      <div className="field">
        <label className="field-label" htmlFor="return">
          Return
        </label>
        <input
          id="return"
          className="text-input"
          type="date"
          min={maxDate(depart, min)}
          value={ret}
          onChange={(e) => {
            const value = e.target.value;
            if (!value) return;
            onChange({ depart, ret: maxDate(value, depart) });
          }}
        />
      </div>
    </div>
  );
}
