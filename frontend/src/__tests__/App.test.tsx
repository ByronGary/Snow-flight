import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { installFakeApi, RESORTS } from "../test/fakeApi";

const IKON = RESORTS.filter((r) => r.pass === "ikon").length;
const EPIC = RESORTS.filter((r) => r.pass === "epic").length;

let calls: string[];

beforeEach(() => {
  // Wed Dec 9 2026, local time. Only Date is faked so promises and timers run normally.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 11, 9, 20, 30));
  calls = installFakeApi();
});

afterEach(() => {
  vi.useRealTimers();
});

async function openResortMenu(user: ReturnType<typeof userEvent.setup>) {
  const input = await screen.findByRole("combobox", { name: "Resort" });
  await waitFor(() => expect(input).toHaveAttribute("placeholder", expect.stringMatching(/Search \d+/)));
  await user.click(input);
  return within(screen.getByRole("listbox")).getAllByRole("option");
}

async function chooseResort(user: ReturnType<typeof userEvent.setup>, query: string, name: RegExp) {
  const input = await screen.findByRole("combobox", { name: "Resort" });
  await user.click(input);
  await user.type(input, query);
  await user.click(within(screen.getByRole("listbox")).getByRole("option", { name }));
}

describe("pass toggle and resort picker", () => {
  it("lists only the current pass's resorts", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(await openResortMenu(user)).toHaveLength(IKON);
    expect(IKON).toBe(57);

    await user.click(screen.getByRole("radio", { name: "Epic Pass" }));
    expect(await openResortMenu(user)).toHaveLength(EPIC);
    expect(EPIC).toBe(42);
  });

  it("clears the selected resort when switching to the other pass", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("radio", { name: "Epic Pass" }));
    await chooseResort(user, "vail", /^Vail/);
    expect(await screen.findByRole("heading", { name: /Vail/ })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Ikon Pass" }));
    expect(screen.getByRole("combobox", { name: "Resort" })).toHaveValue("");
    expect(screen.queryByRole("heading", { name: /Vail/ })).not.toBeInTheDocument();
    expect(window.location.search).not.toContain("resort=");
  });

  it("matches resort names without accents", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("radio", { name: "Epic Pass" }));
    await chooseResort(user, "isere", /Val d'Isère/);
    await screen.findByRole("heading", { name: /Val d'Isère/ });
    expect(calls).toContain("/api/resorts/val-d-isere/weather");
  });

  it("shows a message when nothing matches", async () => {
    const user = userEvent.setup();
    render(<App />);
    const input = await screen.findByRole("combobox", { name: "Resort" });
    await user.click(input);
    await user.type(input, "zzzz");
    expect(within(screen.getByRole("listbox")).queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByText(/No Ikon resorts match/)).toBeInTheDocument();
  });

  it("selects the pass from a shared ?resort= link", async () => {
    window.history.replaceState(null, "", "/?resort=vail");
    render(<App />);
    await screen.findByRole("heading", { name: /Vail/ });
    expect(screen.getByRole("radio", { name: "Epic Pass" })).toBeChecked();
    expect(screen.getByRole("combobox", { name: "Resort" })).toHaveValue("Vail");
  });

  it("loads the weather and a 7-day forecast for the chosen resort", async () => {
    const user = userEvent.setup();
    render(<App />);
    await chooseResort(user, "alta", /Alta Ski Area/);
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(8); // header + 7 days
    expect(calls).toContain("/api/resorts/alta-ski-area/weather");
    expect(screen.getByText("Season 2026-27")).toBeInTheDocument();
    // The 9.5" day is highlighted as a powder day.
    expect(within(table).getByText('9.5"').closest("tr")).toHaveClass("powder");
  });
});

describe("home ZIP and airports", () => {
  it("looks up ZIP+4 by its first five digits", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Home ZIP"), { target: { value: "10001-1234" } });
    expect(await screen.findByRole("checkbox", { name: /JFK/ })).toBeChecked();
    expect(calls).toContain("/api/airports/nearby?zip=10001&radius=50");
  });

  it("rejects malformed ZIPs without calling the API", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Home ZIP"), { target: { value: "abc" } });
    expect(screen.getByText("Enter a 5-digit US ZIP code.")).toBeInTheDocument();
    expect(calls.some((c) => c.startsWith("/api/airports"))).toBe(false);
  });

  it("explains an unknown ZIP", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Home ZIP"), { target: { value: "00000" } });
    expect(await screen.findByText("We couldn't find that ZIP code.")).toBeInTheDocument();
  });

  it("explains when it had to look further than the radius", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Home ZIP"), { target: { value: "69201" } });
    expect(await screen.findByText(/Showing the nearest instead/)).toBeInTheDocument();
  });

  it("refetches airports when the radius changes", async () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Home ZIP"), { target: { value: "10001" } });
    await screen.findByRole("checkbox", { name: /JFK/ });
    fireEvent.change(screen.getByLabelText("Airports within"), { target: { value: "100" } });
    await waitFor(() => expect(calls).toContain("/api/airports/nearby?zip=10001&radius=100"));
  });
});

describe("flights", () => {
  it("links one Google Flights search across every selected airport", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/?resort=vail&zip=10001");
    render(<App />);
    // Vail flies into Eagle first, with Denver as the alternate.
    const [ege, den] = await screen.findAllByRole("link", { name: /Search all 3 airports/ });
    expect(ege.getAttribute("href")).toContain("/travel/flights/search?tfs=");
    expect(ege.getAttribute("href")).toContain("LGA-EWR-JFK-EGE");
    expect(den.getAttribute("href")).toContain("LGA-EWR-JFK-DEN");
    expect(screen.getByRole("heading", { name: /Into DEN · Denver International Airport/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "JFK → EGE" })).toBeInTheDocument();
    expect(calls).toContain("/api/flights?origins=LGA%2CEWR%2CJFK&dest=EGE%2CDEN&depart=2026-12-11&return=2026-12-14");

    await user.click(screen.getByRole("checkbox", { name: /EWR/ }));
    const [updated] = await screen.findAllByRole("link", { name: /Search all 2 airports/ });
    expect(updated.getAttribute("href")).toContain("LGA-JFK-EGE");
  });

  it("asks for a ZIP before showing flights", async () => {
    window.history.replaceState(null, "", "/?resort=vail");
    render(<App />);
    expect(await screen.findByText("Enter your home ZIP code to see flights.")).toBeInTheDocument();
    expect(calls.some((c) => c.startsWith("/api/flights"))).toBe(false);
  });

  it("shows a single destination without the 'Into' heading", async () => {
    window.history.replaceState(null, "", "/?resort=alta-ski-area&zip=10001");
    render(<App />);
    expect(await screen.findByRole("link", { name: /Search all 3 airports: LGA\/EWR\/JFK → SLC/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Into / })).not.toBeInTheDocument();
  });

  it("asks for an airport when all are unticked", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/?resort=vail&zip=10001");
    render(<App />);
    for (const code of ["LGA", "EWR", "JFK"]) {
      await user.click(await screen.findByRole("checkbox", { name: new RegExp(code) }));
    }
    expect(screen.getByText("Select at least one airport to fly from.")).toBeInTheDocument();
  });
});

describe("trip dates", () => {
  it("defaults to next Friday through Monday in local time", () => {
    render(<App />);
    expect(screen.getByLabelText("Depart")).toHaveValue("2026-12-11");
    expect(screen.getByLabelText("Return")).toHaveValue("2026-12-14");
  });

  it("keeps the return date on or after departure", () => {
    render(<App />);
    fireEvent.change(screen.getByLabelText("Return"), { target: { value: "2026-12-10" } });
    expect(screen.getByLabelText("Return")).toHaveValue("2026-12-11");
    fireEvent.change(screen.getByLabelText("Depart"), { target: { value: "2026-12-20" } });
    expect(screen.getByLabelText("Return")).toHaveValue("2026-12-23");
  });

  it("ignores past dates from a shared link", () => {
    window.history.replaceState(null, "", "/?depart=2026-11-01&return=2026-11-05");
    render(<App />);
    expect(screen.getByLabelText("Depart")).toHaveValue("2026-12-11");
  });

  it("'Fly in for this' books the night before a powder day", async () => {
    const user = userEvent.setup();
    window.history.replaceState(null, "", "/?resort=alta-ski-area&zip=10001");
    render(<App />);
    const table = await screen.findByRole("table");
    const powderRow = within(table).getByText('9.5"').closest("tr")!;
    await user.click(within(powderRow).getByRole("button", { name: "Fly in for this" }));
    expect(screen.getByLabelText("Depart")).toHaveValue("2026-12-10");
    expect(screen.getByLabelText("Return")).toHaveValue("2026-12-13");
    await waitFor(() => expect(calls.some((c) => c.includes("depart=2026-12-10&return=2026-12-13"))).toBe(true));
  });
});
