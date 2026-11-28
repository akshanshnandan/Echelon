import { expect, test, type Page } from "@playwright/test";
import type { Game, Order } from "../src/types";

async function completeBattle(
  page: Page,
  ruleset: "Classic" | "Expanded",
  army: "Blue" | "Red",
) {
  await page.goto("/");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByText("Choose your command.")).toBeVisible();
  if (ruleset === "Expanded") {
    await page
      .getByRole("button", { name: /Expanded Draft your own army/ })
      .click();
    await page.getByLabel("Recruit cavalry").click();
    await expect(page.getByText("YOUR FORMATIONS · 4/4")).toBeVisible();
  }
  if (ruleset === "Classic") await page.getByRole("button", {name:/Classic Original three formations/}).click();
  await page.getByLabel("Your army").selectOption(army);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/games") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Begin battle/ }).click();
  const game = (await (await created).json()) as Game;
  await expect(
    page.getByRole("grid", { name: "Eight by eight battlefield" }),
  ).toBeVisible();
  await expect(page.locator(".game-view")).toHaveCSS("opacity", "1");
  await page.screenshot({
    path: `../docs/phase10_${ruleset.toLowerCase()}_battle.png`,
    fullPage: true,
  });

  let turns = 0;
  while (turns < 31) {
    const response = await page.request.get(`/api/games/${game.id}`);
    const current = (await response.json()) as Game;
    if (current.state.finished) break;
    const legal = current.legal_orders;
    const chosen: Order =
      legal.find((order) => order.kind === "ATTACK") ??
      legal.find((order) => order.kind === "ADVANCE") ??
      legal[0];
    const unit = current.state.units[chosen.unit_id];
    await page
      .getByTestId(`cell-${unit.position[0]}-${unit.position[1]}`)
      .click();
    await page.getByTestId(`order-${chosen.kind.toLowerCase()}`).click();
    if (chosen.kind !== "HOLD") {
      const target = Array.isArray(chosen.target)
        ? chosen.target
        : current.state.units[chosen.target as string].position;
      await expect(
        page.getByTestId(`cell-${target[0]}-${target[1]}`),
      ).toHaveClass(/legal/);
      await page.getByTestId(`cell-${target[0]}-${target[1]}`).click();
    }
    turns++;
  }
  await expect(page.getByTestId("battle-result")).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: /Download replay/ }).click();
  expect((await downloaded).suggestedFilename()).toContain("echelon-");
  const replay = await page.request.get(`/api/games/${game.id}/replay`);
  expect(replay.status()).toBe(200);
  const recording = await replay.json();
  expect(recording.final.finished).toBe(true);
  await page.screenshot({
    path: `../docs/phase10_${ruleset.toLowerCase()}_result.png`,
    fullPage: true,
  });
  return recording;
}

test("a Blue human completes a Classic browser battle", async ({ page }) => {
  await page.goto("/");
  await page.screenshot({
    path: "../docs/phase10_landing.png",
    fullPage: true,
  });
  const recording = await completeBattle(page, "Classic", "Blue");
  await page.getByRole("button", { name: "Restart" }).click();
  await expect(page.getByTestId("battle-result")).toHaveCount(0);
  await page.getByRole("button", { name: "Replays" }).click();
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "completed.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(recording)),
    });
  await expect(page.getByRole("button", { name: "Next action" })).toBeVisible();
  await page.getByRole("button", { name: "Next action" }).click();
  await expect(page.getByText(/1 \/ .* ORDERS/)).toBeVisible();
});

test("a Red human drafts and completes an Expanded browser battle", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page
    .getByRole("button", { name: /Expanded Draft your own army/ })
    .click();
  await expect(page.locator(".setup-layout")).toHaveCSS("opacity", "1");
  await page.screenshot({ path: "../docs/phase10_draft.png", fullPage: true });
  await completeBattle(page, "Expanded", "Red");
});

test("replay viewer steps through bundled snapshots", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Replays" }).click();
  await page.getByRole("button", { name: "Open Classic sample" }).click();
  await expect(page.getByText(/0 \/ .* ORDERS/)).toBeVisible();
  await page.getByRole("button", { name: "Next action" }).click();
  await expect(page.getByText(/1 \/ .* ORDERS/)).toBeVisible();
  await page.getByRole("button", { name: "Previous action" }).click();
  await expect(page.getByText(/0 \/ .* ORDERS/)).toBeVisible();
  await page.getByRole("button", { name: "Play replay" }).click();
  await expect(
    page.getByRole("button", { name: "Pause replay" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Open Expanded sample" }).click();
  await expect(page.getByText(/0 \/ .* ORDERS/)).toBeVisible();
});

test("mobile setup and battlefield fit the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByText("Choose your command.")).toBeVisible();
  await page.locator(".setup-layout").evaluate(async (element) => {
    await Promise.all(
      element.getAnimations().map((animation) => animation.finished),
    );
  });
  await page.screenshot({ path: "../docs/phase10_mobile.png", fullPage: true });
  await page.getByRole("button", {name:/Classic Original three formations/}).click();
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/games") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: /Begin battle/ }).click();
  await created;
  await expect(page.getByRole("grid")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});
