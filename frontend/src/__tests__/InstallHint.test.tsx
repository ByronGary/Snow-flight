import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { InstallHint, shouldShowInstallHint } from "../components/InstallHint";

const IPHONE =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

function nav(ua: string, extra: Partial<Navigator & { standalone: boolean }> = {}) {
  return { userAgent: ua, platform: "iPhone", maxTouchPoints: 5, ...extra } as Navigator;
}

const browserWindow = { matchMedia: () => ({ matches: false }) } as unknown as Window;
const standaloneWindow = { matchMedia: () => ({ matches: true }) } as unknown as Window;

describe("install hint", () => {
  it("shows in iPhone Safari, but not once installed or on desktop", () => {
    expect(shouldShowInstallHint(nav(IPHONE), browserWindow)).toBe(true);
    expect(shouldShowInstallHint(nav(IPHONE, { standalone: true }), browserWindow)).toBe(false);
    expect(shouldShowInstallHint(nav(IPHONE), standaloneWindow)).toBe(false);
    expect(shouldShowInstallHint(nav("Mozilla/5.0 (X11; Linux x86_64) Chrome/130", { platform: "Linux", maxTouchPoints: 0 }),
      browserWindow)).toBe(false);
    // iPadOS reports itself as a Mac with touch.
    expect(shouldShowInstallHint(nav("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
      { platform: "MacIntel", maxTouchPoints: 5 }), browserWindow)).toBe(true);
  });

  it("stays dismissed", async () => {
    vi.spyOn(navigator, "userAgent", "get").mockReturnValue(IPHONE);
    const user = userEvent.setup();
    const { unmount } = render(<InstallHint />);
    expect(screen.getByRole("complementary", { name: "Install on your iPhone" })).toHaveTextContent("Add to Home Screen");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    unmount();
    render(<InstallHint />);
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
