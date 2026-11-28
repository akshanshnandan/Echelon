import { test, expect } from "@playwright/test";

test("Command setup, orders, clock, and pause", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Play Echelon" }).click();
  await page.getByRole("button", { name: /Command Real-time battlefield/ }).click();
  await page.getByLabel("Battlefield map").selectOption("ridge_forest");
  await page.getByRole("button", { name: /Begin battle/ }).click();
  await expect(page.getByText("COMMAND MODE", { exact: false })).toBeVisible();
  await expect(page.locator("svg[aria-label='Command battlefield']")).toBeVisible();
  await page.locator("svg[aria-label='Command battlefield'] [data-unit-id]").first().click();
  await expect(page.getByText("B1 · infantry")).toBeVisible();
  await page.getByRole("button", { name: "HOLD", exact: true }).click();
  await expect(page.getByText(/HOLD · HP/)).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.getByLabel("Simulation speed").selectOption("2");
  await page.locator("svg[aria-label='Command battlefield'] [data-unit-id]").nth(1).click();
  await page.locator("svg[aria-label='Command battlefield']").click({ position: { x: 500, y: 350 } });
  await page.getByRole("button", { name: "Resume" }).click();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: "../docs/phase11_command_battle.png", fullPage: true });
});

test("Command tap controls fit a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Play Echelon" }).click();
  await page.getByRole("button", { name: /Command Real-time battlefield/ }).click();
  await page.getByRole("button", { name: /Begin battle/ }).click();
  const field = page.locator("svg[aria-label='Command battlefield']");
  await field.locator("[data-unit-id]").first().click();
  await expect(page.getByText("B1 · infantry")).toBeVisible();
  await field.click({ position: { x: 180, y: 140 } });
  await expect(page.getByText(/MOVE · HP/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
