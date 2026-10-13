import { useCallback, useState } from "react";
import type { PassType } from "../api/types";
import { defaultTripDates, isISODate, today } from "../lib/dates";

export const RADII = [25, 50, 100] as const;
export const DEFAULT_RADIUS = 50;
const ZIP_STORAGE_KEY = "snowflights.zip";

export interface AppState {
  pass: PassType;
  resort: string | null;
  zip: string;
  radius: number;
  depart: string;
  ret: string;
}

function storedZip(): string {
  try {
    return window.localStorage.getItem(ZIP_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function storeZip(zip: string) {
  try {
    window.localStorage.setItem(ZIP_STORAGE_KEY, zip);
  } catch {
    // Storage may be unavailable (private mode); the ZIP just won't be remembered.
  }
}

export function readState(search: string): AppState {
  const p = new URLSearchParams(search);
  const radius = Number(p.get("radius"));
  const defaults = defaultTripDates();
  let depart = p.get("depart");
  let ret = p.get("return");
  if (!isISODate(depart) || depart < today()) {
    depart = defaults.depart;
    ret = null;
  }
  if (!isISODate(ret) || ret < depart) {
    ret = depart === defaults.depart ? defaults.ret : depart;
  }
  return {
    pass: p.get("pass") === "epic" ? "epic" : "ikon",
    resort: p.get("resort") || null,
    zip: p.get("zip") ?? storedZip(),
    radius: (RADII as readonly number[]).includes(radius) ? radius : DEFAULT_RADIUS,
    depart,
    ret,
  };
}

function writeUrl(s: AppState) {
  const p = new URLSearchParams();
  p.set("pass", s.pass);
  if (s.resort) p.set("resort", s.resort);
  if (s.zip) p.set("zip", s.zip);
  if (s.radius !== DEFAULT_RADIUS) p.set("radius", String(s.radius));
  p.set("depart", s.depart);
  p.set("return", s.ret);
  window.history.replaceState(null, "", `${window.location.pathname}?${p}`);
}

/** App state mirrored into the query string, so searches can be shared and deep-linked from alerts. */
export function useUrlState(): [AppState, (patch: Partial<AppState>) => void] {
  const [state, setState] = useState<AppState>(() => readState(window.location.search));
  const update = useCallback((patch: Partial<AppState>) => {
    setState((prev) => {
      const next = { ...prev, ...patch };
      writeUrl(next);
      if (patch.zip !== undefined) storeZip(next.zip);
      return next;
    });
  }, []);
  return [state, update];
}
