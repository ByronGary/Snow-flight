import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { fakeOptions, installFakeApi } from "../test/fakeApi";

let calls: string[];

beforeEach(() => {
  fakeOptions.snow = true;
  calls = installFakeApi();
});

afterEach(() => {
  fakeOptions.snow = true;
});

async function board() {
  const section = await screen.findByRole("region", { name: /Most snow in the next 5 days/ });
  await within(section).findAllByRole("button", { name: /forecast over 5 days/ });
  return section;
}

describe("powder board", () => {
  it("ranks the current pass's resorts by forecast snow", async () => {
    render(<App />);
    const section = await board();
    expect(calls).toContain("/api/powder?pass=ikon&days=5");
    const rows = within(section).getAllByRole("button", { name: /forecast over 5 days/ });
    expect(rows).toHaveLength(8);
    expect(rows[0]).toHaveAccessibleName('Snowbird: 22" forecast over 5 days');
    // Bars are scaled to the snowiest resort.
    expect(rows[0].querySelector<HTMLElement>(".powder-bar")!.style.width).toBe("100%");
  });

  it("follows the pass toggle", async () => {
    const user = userEvent.setup();
    render(<App />);
    await board();
    await user.click(screen.getByRole("radio", { name: "Epic Pass" }));
    await waitFor(() => expect(calls).toContain("/api/powder?pass=epic&days=5"));
    const section = screen.getByRole("region", { name: /Epic resorts/ });
    await waitFor(() =>
      expect(within(section).getAllByRole("button", { name: /forecast/ })[0]).toHaveAccessibleName(/^Vail:/),
    );
  });

  it("opens a resort when its bar is clicked", async () => {
    const user = userEvent.setup();
    render(<App />);
    const section = await board();
    await user.click(within(section).getByRole("button", { name: /^Snowbird:/ }));
    expect(await screen.findByRole("heading", { name: /Snowbird/, level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Resort" })).toHaveValue("Snowbird");
    expect(screen.queryByRole("region", { name: /Most snow/ })).not.toBeInTheDocument();
  });

  it("shows the daily numbers on hover and focus, and in a table", async () => {
    const user = userEvent.setup();
    render(<App />);
    const section = await board();
    await user.hover(within(section).getByRole("button", { name: /^Snowbird:/ }));
    const tip = screen.getByRole("tooltip");
    expect(within(tip).getByText('14"')).toBeInTheDocument();
    await user.unhover(within(section).getByRole("button", { name: /^Snowbird:/ }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    await user.tab({ shift: false });
    await user.click(within(section).getByText("Daily breakdown"));
    const table = within(section).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(9); // header + 8 resorts
  });

  it("says so when nothing is forecast", async () => {
    fakeOptions.snow = false;
    render(<App />);
    expect(await screen.findByText(/No snow in the forecast for any Ikon resort/)).toBeInTheDocument();
  });
});
