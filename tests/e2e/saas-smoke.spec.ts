import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const apiUrl = (process.env.E2E_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const skipAll = process.env.E2E_SKIP === "1";

test.describe("SaaS browser smoke", () => {
  test.beforeEach(async ({}, testInfo) => {
    if (skipAll) {
      testInfo.skip(true, "E2E_SKIP=1 (stack not running)");
    }
    try {
      const res = await fetch(`${apiUrl}/api/v1/health/live`);
      if (!res.ok) {
        testInfo.skip(true, `API not reachable at ${apiUrl}`);
      }
    } catch {
      testInfo.skip(true, `API not reachable at ${apiUrl}`);
    }
  });

  test("register → documents → optional billing", async ({ page }) => {
    const user = `e2e_${Date.now().toString(36)}`;
    const password = "E2eTestPass123!";

    await page.goto("/login");
    await page.locator("aside button.landing-auth-link", { hasText: "Register" }).click();
    await page.locator("#user").fill(user);
    await page.locator("#pass").fill(password);
    await page.locator("#confirm").fill(password);
    await page.getByRole("checkbox").check();
    await page.locator("form button[type='submit']").click();

    await page.waitForURL(/\/(onboarding)?/, { timeout: 60_000 });

    await page.goto("/documents");
    await expect(page.getByRole("heading", { name: /document management/i })).toBeVisible({
      timeout: 30_000,
    });

    const dataDir = path.join(__dirname, "..", "..", "Data");
    const fixture =
      fs.readdirSync(dataDir).find((f) => f.endsWith(".pdf")) &&
      path.join(dataDir, fs.readdirSync(dataDir).find((f) => f.endsWith(".pdf"))!);
    if (fixture && fs.existsSync(fixture)) {
      const fileInput = page.locator('input[type="file"]').first();
      await fileInput.setInputFiles(fixture);
      await expect(page.getByText(/upload|index/i).first()).toBeVisible({ timeout: 90_000 });
    }

    if (process.env.E2E_STRIPE === "1") {
      await page.goto("/settings");
      const upgrade = page.getByRole("link", { name: /upgrade|billing|plan/i }).first();
      if (await upgrade.isVisible().catch(() => false)) {
        await upgrade.click();
        await expect(page).toHaveURL(/billing|settings/, { timeout: 15_000 });
      }
    }
  });

  test("litigation desk tabs visible", async ({ page }) => {
    const user = `e2e_lit_${Date.now().toString(36)}`;
    const password = "E2eTestPass123!";

    await page.goto("/login");
    await page.locator("aside button.landing-auth-link", { hasText: "Register" }).click();
    await page.locator("#user").fill(user);
    await page.locator("#pass").fill(password);
    await page.locator("#confirm").fill(password);
    await page.getByRole("checkbox").check();
    await page.locator("form button[type='submit']").click();
    await page.waitForURL(/\/(onboarding)?/, { timeout: 60_000 });

    await page.goto("/litigation");
    await expect(page.getByRole("button", { name: "Court Day" })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByRole("button", { name: "Evidence" })).toBeVisible();
    await expect(page.getByText(/contradictions|cause list|Import cause list/i).first()).toBeVisible();
  });
});
