import { expect, test } from "@playwright/test";
test.use({userAgent:"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/159.0.0.0 Safari/537.36"});

test("analytics waits for consent and sends only after opt-in", async ({page}) => {
  await page.route("**/api/config", async (route) => {
    const response=await route.fetch();
    await route.fulfill({response,json:{...await response.json(),analytics:{token:"public-test-token",host:"https://us.i.posthog.com"}}});
  });
  const outbound:string[]=[];
  await page.route("https://us.i.posthog.com/**", async (route) => {
    outbound.push(route.request().url());
    await route.fulfill({status:200,contentType:"application/json",headers:{"Access-Control-Allow-Origin":"*"},body:"{}"});
  });
  await page.goto("/");
  await expect(page.getByRole("button",{name:"Enable analytics"})).toBeVisible();
  await page.getByRole("button",{name:"Play Echelon"}).click();
  await page.waitForTimeout(400);
  expect(outbound).toHaveLength(0);
  await page.getByRole("button",{name:"Enable analytics"}).click();
  await page.getByRole("button",{name:"Home",exact:true}).click();
  await expect.poll(() => outbound.length).toBeGreaterThan(0);
  expect(outbound.some((url) => /\/(e|batch)\//.test(url))).toBe(true);
  await page.getByRole("button",{name:"Privacy and analytics"}).click();
  await expect(page.getByRole("status").filter({hasText:"Analytics: on"})).toBeVisible();
  await page.getByRole("button",{name:"Turn analytics off"}).click();
  await expect(page.getByRole("status").filter({hasText:"Analytics: off"})).toBeVisible();
  const count=outbound.length;
  await page.getByRole("button",{name:"Play",exact:true}).click();
  await page.waitForTimeout(400);
  expect(outbound.length).toBe(count);
  await page.getByRole("button",{name:"Enable analytics"}).click();
  await page.getByRole("button",{name:"Home",exact:true}).click();
  await expect.poll(() => outbound.length).toBeGreaterThan(count);
});

test("feedback needs no account and Classic session loss has recovery", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Privacy and analytics"}).click();
  await expect(page.getByRole("region",{name:"Privacy notice"})).toContainText("off by default");
  await page.getByRole("button",{name:"Close"}).click();
  await page.getByRole("button",{name:"Give feedback"}).click();
  await page.getByLabel("Feedback rating").selectOption("5");
  await page.getByLabel("Feedback topic").selectOption("controls");
  const feedback=page.waitForResponse((r) => r.url().endsWith("/api/feedback"));
  await page.getByRole("button",{name:"Send feedback"}).click();
  expect((await feedback).status()).toBe(202);
  await expect(page.getByText("Thanks. Your rating was received.")).toBeVisible();
  await page.getByRole("button",{name:"Close"}).click();
  await page.getByRole("button",{name:"Play Echelon"}).click();
  await page.getByRole("button",{name:/Classic Original three formations/}).click();
  const created=page.waitForResponse((r) => r.url().endsWith("/api/games") && r.request().method()==="POST");
  await page.getByRole("button",{name:/Begin battle/}).click();
  const game=await (await created).json();
  const hold=game.legal_orders.find((order:{kind:string}) => order.kind==="HOLD");
  const unit=game.state.units[hold.unit_id];
  await page.route(`**/api/games/${game.id}/orders`, (route) => route.fulfill({status:404,contentType:"application/json",body:JSON.stringify({detail:"Game session not found or expired"})}));
  await page.getByTestId(`cell-${unit.position[0]}-${unit.position[1]}`).click();
  await page.getByTestId("order-hold").click();
  await expect(page.getByRole("alert")).toContainText("Game session expired. Start a new battle.");
  await page.getByRole("button",{name:"New battle"}).click();
  await expect(page.getByRole("button",{name:/Begin battle/})).toBeVisible();
});
