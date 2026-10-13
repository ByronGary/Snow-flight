// Dates are handled as local calendar days ("YYYY-MM-DD"). Avoid toISOString(),
// which converts to UTC and shifts the day for US users in the evening.

export function toISODate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function parseISODate(s: string): Date {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function isISODate(s: string | null | undefined): s is string {
  if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  return toISODate(parseISODate(s)) === s;
}

export function addDays(iso: string, days: number): string {
  const d = parseISODate(iso);
  d.setDate(d.getDate() + days);
  return toISODate(d);
}

export function today(): string {
  return toISODate(new Date());
}

/** Next Friday after `from`, returning the following Monday (matches flights.default_trip_dates). */
export function defaultTripDates(from: string = today()): { depart: string; ret: string } {
  const weekday = parseISODate(from).getDay(); // 0 = Sunday ... 5 = Friday
  const ahead = (5 - weekday + 7) % 7 || 7;
  const depart = addDays(from, ahead);
  return { depart, ret: addDays(depart, 3) };
}

export function formatDay(iso: string): string {
  return parseISODate(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export function maxDate(a: string, b: string): string {
  return a > b ? a : b;
}
