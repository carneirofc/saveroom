import { expect, test } from "../baserowTest";
import { LoginPage } from "../../pages/loginPage";
import { baserowConfig } from "../../playwright.config";

// The e2e stack runs without a branding directory, so these cover the runtime
// branding routes serving the built-in defaults. Overrides themselves are
// covered by the web-frontend unit tests (test/unit/core/branding).
const frontend = (path: string) =>
  `${baserowConfig.PUBLIC_WEB_FRONTEND_URL}${path}`;

test("Branding config is served with defaults @fast", async ({ request }) => {
  const response = await request.get(frontend("/_branding/config.json"));
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body).toMatchObject({
    hasTheme: false,
    siteUrl: "https://github.com/carneirofc/baserow",
    docsUrl: "https://github.com/carneirofc/baserow",
    siteTitle: "Saveroom",
    showAttribution: true,
  });
  expect(body.version).toEqual(expect.any(String));
});

test("Default logo and icons are served safely @fast", async ({ request }) => {
  const logo = await request.get(frontend("/_branding/assets/img/logo.svg"));
  expect(logo.status()).toBe(200);
  expect(logo.headers()["content-type"]).toContain("image/svg+xml");
  expect(logo.headers()["x-content-type-options"]).toBe("nosniff");
  expect(logo.headers()["content-security-policy"]).toContain("sandbox");

  const icon = await request.get(
    frontend("/_branding/assets/icons/formula.svg")
  );
  expect(icon.status()).toBe(200);
});

test("Branding assets reject unsafe paths @fast", async ({ request }) => {
  for (const path of [
    "/_branding/assets/img/..%2f..%2fnuxt.config.ts",
    "/_branding/assets/img/does-not-exist.svg",
    "/_branding/assets/img/logo.html",
    "/_branding/assets/branding.json",
  ]) {
    const response = await request.get(frontend(path));
    expect(response.status(), path).toBe(404);
  }
});

test("Login page uses the branding logo and title @fast", async ({
  page,
  goto,
}) => {
  const loginPage = new LoginPage({ page, goto });
  await loginPage.goto();

  const logo = page.locator(".logo img").first();
  await expect(logo).toHaveAttribute("src", "/_branding/assets/img/logo.svg");
  await expect
    .poll(() => logo.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);
  await expect(page).toHaveTitle(/Saveroom$/);
});
