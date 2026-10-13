import { expect, test, type Page } from "@playwright/test";

function weather(slug: string) {
  return {
    resort: { slug, name: slug },
    timezone: "America/Denver",
    current: {
      time: "2026-12-09T09:00", weather_code: 73, conditions: "Moderate Snow", is_day: true, temperature: 21,
      snowfall: 0.2, precipitation: 0.02, wind_speed: 12, wind_gusts: 25, snow_depth: 38,
    },
    daily: Array.from({ length: 7 }, (_, i) => ({
      date: isoDay(i), weather_code: 73, conditions: "Moderate Snow",
      snowfall: i === 2 ? 9.5 : 1, precipitation: 0.3, temp_max: 25, temp_min: 12,
    })),
    season: { label: "2026-27", start: "2026-10-01", through: "2026-12-06", snowfall: 42.1, in_season: true },
  };
}

function isoDay(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Decode the protobuf in a Google Flights tfs link into its printable strings (airports, dates). */
function tfsStrings(href: string): string[] {
  const tfs = new URL(href).searchParams.get("tfs")!;
  const bytes = Buffer.from(tfs.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("latin1");
  return bytes.match(/[A-Z]{3}|\d{4}-\d{2}-\d{2}/g) ?? [];
}

const problems: string[] = [];

test.beforeEach(async ({ page }) => {
  problems.length = 0;
  page.on("console", (m) => {
    // A 404 for an unknown ZIP is expected API behaviour; anything else (e.g. CSP violations) is not.
    if (m.type() === "error" && !m.text().includes("404")) problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
  await page.route("**/api/resorts/*/weather", (route) => {
    const slug = route.request().url().split("/api/resorts/")[1].split("/")[0];
    return route.fulfill({ json: weather(slug) });
  });
  await page.route("**/api/powder?*", (route) => {
    const pass = new URL(route.request().url()).searchParams.get("pass");
    const resorts = pass === "epic"
      ? [["vail", "Vail", "CO", 14.2], ["beaver-creek", "Beaver Creek", "CO", 12.0], ["whistler-blackcomb", "Whistler Blackcomb", "BC", 3.1]]
      : [["snowbird", "Snowbird", "UT", 21.5], ["alta-ski-area", "Alta Ski Area", "UT", 19.0], ["jackson-hole", "Jackson Hole", "WY", 6.4]];
    return route.fulfill({
      json: {
        days: 5,
        resorts: resorts.map(([slug, name, region, total]) => ({
          slug, name, region, pass, country: "US", total_in: total, peak: { date: isoDay(1), snowfall: total },
          daily: Array.from({ length: 5 }, (_, i) => ({ date: isoDay(i), snowfall: i === 1 ? total : 0 })),
        })),
      },
    });
  });
  // Never leave the app during tests.
  await page.route("https://www.google.com/**", (route) => route.abort());
});

test.afterEach(() => {
  expect(problems, "console errors").toEqual([]);
});

async function pickResort(page: Page, query: string, name: RegExp) {
  const input = page.getByRole("combobox", { name: "Resort" });
  await input.fill(query);
  await page.getByRole("listbox").getByRole("option", { name }).click();
}

test("pass toggle switches between 57 Ikon and 42 Epic resorts", async ({ page }) => {
  await page.goto("/");
  const input = page.getByRole("combobox", { name: "Resort" });
  await expect(input).toHaveAttribute("placeholder", "Search 57 Ikon resorts…");
  await input.click();
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(57);
  await page.keyboard.press("Escape");
  await page.getByText("Epic Pass").click();
  await expect(input).toHaveAttribute("placeholder", "Search 42 Epic resorts…");
  await input.click();
  await expect(page.getByRole("listbox").getByRole("option")).toHaveCount(42);
});

test("NYC to Vail builds one Google Flights search per arrival airport", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Epic Pass").click();
  await pickResort(page, "vail", /^Vail/);
  await page.getByLabel("Home ZIP").fill("10001-1234");

  const chips = page.locator(".chip strong");
  await expect(chips).toHaveText(["LGA", "EWR", "JFK", "HPN", "ISP"]);

  const searches = page.getByRole("link", { name: /Search all 5 airports/ });
  await expect(searches).toHaveCount(2); // EGE, then DEN as the alternate
  const [ege, den] = await searches.all();
  const depart = await page.getByLabel("Depart").inputValue();
  const ret = await page.getByLabel("Return").inputValue();
  const egeHref = (await ege.getAttribute("href"))!;
  expect(egeHref).toMatch(/^https:\/\/www\.google\.com\/travel\/flights\/search\?tfs=[\w-]+&hl=en&curr=USD$/);
  // Outbound leg: date, five origins, EGE. Return leg: date, EGE, five origins.
  expect(tfsStrings(egeHref)).toEqual([
    depart, "LGA", "EWR", "JFK", "HPN", "ISP", "EGE", ret, "EGE", "LGA", "EWR", "JFK", "HPN", "ISP",
  ]);
  expect(tfsStrings((await den.getAttribute("href"))!)).toContain("DEN");
  await expect(page.getByRole("heading", { name: /Into DEN · Denver International Airport/ })).toBeVisible();

  await page.getByRole("checkbox", { name: /EWR/ }).uncheck();
  const fewer = page.getByRole("link", { name: /Search all 4 airports/ });
  await expect(fewer).toHaveCount(2);
  const [ege4] = await fewer.all();
  expect(tfsStrings((await ege4.getAttribute("href"))!)).not.toContain("EWR");
  await expect(page).toHaveURL(/resort=vail/);
});

test("the powder board ranks resorts and opens one on click", async ({ page }) => {
  await page.goto("/");
  const board = page.getByRole("region", { name: /Most snow in the next 5 days/ });
  const bars = board.getByRole("button", { name: /forecast over 5 days/ });
  await expect(bars).toHaveCount(3);
  await expect(bars.first()).toHaveAccessibleName('Snowbird: 21.5" forecast over 5 days');
  await bars.first().hover();
  await expect(page.getByRole("tooltip")).toContainText('21.5"');
  await page.getByText("Epic Pass").click();
  await expect(bars.first()).toHaveAccessibleName(/^Vail:/);
  await bars.first().click();
  await expect(page.getByRole("heading", { name: /Vail/, level: 2 })).toBeVisible();
  await expect(board).toHaveCount(0);
});

test("a shared link restores the resort, pass and airports", async ({ page }) => {
  await page.goto("/?resort=alta-ski-area&zip=80302");
  await expect(page.getByRole("radio", { name: "Ikon Pass" })).toBeChecked();
  await expect(page.getByRole("combobox", { name: "Resort" })).toHaveValue("Alta Ski Area");
  await expect(page.locator(".chip strong")).toHaveText(["DEN"]); // Boulder: no GA fields like BJC
  await expect(page.getByRole("link", { name: /Search flights: DEN → SLC/ })).toBeVisible();
});

test("'Fly in for this' moves the trip to the night before a powder day", async ({ page }) => {
  await page.goto("/?resort=alta-ski-area&zip=10001");
  const powderRow = page.locator("tr.powder");
  await expect(powderRow).toHaveCount(1);
  await powderRow.getByRole("button", { name: "Fly in for this" }).click();
  await expect(page.getByLabel("Depart")).toHaveValue(isoDay(1));
});

test("unknown and malformed ZIPs explain themselves", async ({ page }) => {
  await page.goto("/?resort=vail");
  await page.getByLabel("Home ZIP").fill("00000");
  await expect(page.getByText("We couldn't find that ZIP code.")).toBeVisible();
  await page.getByLabel("Home ZIP").fill("abc");
  await expect(page.getByText("Enter a 5-digit US ZIP code.")).toBeVisible();
  await expect(page.getByText("Fix the ZIP code above to see flights.").or(page.getByText("Enter your home ZIP code"))).toBeVisible();
});

test("the page never scrolls sideways", async ({ page }) => {
  await page.goto("/?resort=alta-ski-area&zip=10001");
  await expect(page.locator("tbody tr")).toHaveCount(7);
  await expect(page.getByRole("link", { name: /Search all/ }).first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBe(0);
});

test.describe("iPhone home screen install", () => {
  test.use({
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  });

  test("the app is installable and explains how", async ({ page, request }) => {
    await page.goto("/");
    await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
    await expect(page.locator('link[rel="apple-touch-icon"]')).toHaveAttribute("href", "/apple-touch-icon.png");

    const manifest = await request.get("/manifest.webmanifest");
    expect(manifest.headers()["content-type"]).toContain("application/manifest+json");
    const body = await manifest.json();
    expect(body.display).toBe("standalone");
    for (const src of [...body.icons.map((i: { src: string }) => i.src), "/apple-touch-icon.png"]) {
      const icon = await request.get(src);
      expect(icon.status(), src).toBe(200);
      expect(icon.headers()["content-type"]).toBe("image/png");
    }

    const hint = page.getByRole("complementary", { name: "Install on your iPhone" });
    await expect(hint).toContainText("Add to Home Screen");
    await hint.getByRole("button", { name: "Dismiss" }).click();
    await expect(hint).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("combobox", { name: "Resort" })).toBeVisible();
    await expect(hint).toHaveCount(0);
  });
});
