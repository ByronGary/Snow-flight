import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { installFakeApi } from "../test/fakeApi";

beforeEach(() => {
  installFakeApi();
});

describe("footer attribution", () => {
  it("credits the CC BY data sources and links the licenses", () => {
    render(<App />);
    const footer = within(screen.getByRole("contentinfo"));
    expect(footer.getByRole("link", { name: "Open-Meteo.com" })).toHaveAttribute("href", "https://open-meteo.com/");
    expect(footer.getByRole("link", { name: "GeoNames" })).toHaveAttribute("href", "https://www.geonames.org/");
    expect(footer.getByRole("link", { name: "CC BY 4.0" })).toHaveAttribute(
      "href",
      "https://creativecommons.org/licenses/by/4.0/",
    );
    expect(footer.getByRole("link", { name: "OurAirports" })).toBeInTheDocument();
    expect(footer.getByRole("link", { name: "Open-source licenses" })).toHaveAttribute("href", "/third-party-licenses.txt");
  });
});
