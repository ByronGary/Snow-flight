import { describe, expect, it } from "vitest";
import { addDays, defaultTripDates, isISODate, parseISODate, toISODate } from "../lib/dates";

describe("dates", () => {
  it.each([
    ["2026-12-07", "2026-12-11"], // Mon
    ["2026-12-08", "2026-12-11"],
    ["2026-12-09", "2026-12-11"],
    ["2026-12-10", "2026-12-11"],
    ["2026-12-11", "2026-12-18"], // Fri -> next Fri, never today
    ["2026-12-12", "2026-12-18"],
    ["2026-12-13", "2026-12-18"], // Sun
  ])("defaultTripDates(%s) departs %s and returns Monday", (from, depart) => {
    expect(defaultTripDates(from)).toEqual({ depart, ret: addDays(depart, 3) });
    expect(parseISODate(addDays(depart, 3)).getDay()).toBe(1);
  });

  it("formats local dates without shifting to UTC", () => {
    expect(toISODate(new Date(2026, 11, 9, 23, 59))).toBe("2026-12-09");
    expect(toISODate(new Date(2026, 0, 1, 0, 0))).toBe("2026-01-01");
  });

  it("adds days across month and year boundaries", () => {
    expect(addDays("2026-12-30", 3)).toBe("2027-01-02");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it.each([
    ["2026-12-09", true],
    ["2026-02-30", false],
    ["2026-1-9", false],
    ["", false],
    [null, false],
  ])("isISODate(%s) is %s", (value, expected) => {
    expect(isISODate(value)).toBe(expected);
  });
});
