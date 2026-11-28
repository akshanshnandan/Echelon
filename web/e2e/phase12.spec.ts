import { expect, test } from "@playwright/test";

test("Command drag selection, pan, zoom, and right-click orders", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Play Echelon"}).click();
  await page.getByRole("button",{name:/Command Real-time battlefield/}).click();
  const created = page.waitForResponse((r) => r.url().endsWith("/api/command") && r.request().method()==="POST");
  await page.getByRole("button",{name:/Begin battle/}).click();
  const id = (await (await created).json()).id as string;
  await page.getByRole("button",{name:"Pause",exact:true}).click();
  const svg=page.locator("svg[aria-label='Command battlefield']");
  const box=await svg.boundingBox();
  expect(box).not.toBeNull();
  const coord=(x:number,y:number) => svg.evaluate((element,[px,py]) => {const svgElement=element as SVGSVGElement;const point=svgElement.createSVGPoint();point.x=px;point.y=py;const screen=point.matrixTransform(svgElement.getScreenCTM()!);return {x:screen.x,y:screen.y};},[x,y] as [number,number]);
  const start=await coord(75,80), end=await coord(245,395);
  await page.mouse.move(start.x,start.y); await page.mouse.down(); await page.mouse.move(end.x,end.y,{steps:12}); await page.mouse.up();
  await expect(page.locator(".war-inspector-unit")).toHaveCount(2);
  await page.getByRole("button",{name:"Zoom in"}).click();
  const before=await svg.getAttribute("viewBox");
  await page.getByRole("button",{name:"Pan",exact:true}).click();
  await page.mouse.move(box!.x+box!.width*.5,box!.y+box!.height*.5); await page.mouse.down();
  await page.mouse.move(box!.x+box!.width*.65,box!.y+box!.height*.5,{steps:10}); await page.mouse.up();
  expect(await svg.getAttribute("viewBox")).not.toBe(before);
  const stateBefore=await (await page.request.get(`/api/command/${id}`)).json();
  expect(stateBefore.battle.units.B1.order).toBe("HOLD");
  await page.getByRole("button",{name:"Pan",exact:true}).click();
  await svg.click({position:{x:box!.width*.55,y:box!.height*.55},button:"right"});
  await expect.poll(async () => (await (await page.request.get(`/api/command/${id}`)).json()).battle.units.B1.order).toBe("MOVE");
});

test("Command replay sample, scrubbing, and malformed upload", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Replays"}).click();
  await page.getByRole("button",{name:"Open Command sample"}).click();
  await expect(page.getByLabel("Command replay timeline")).toBeVisible();
  await page.getByRole("button",{name:"Play Command replay"}).click();
  await expect(page.getByRole("button",{name:"Pause Command replay"})).toBeVisible();
  await page.getByRole("button",{name:"Restart Command replay"}).click();
  const slider=page.getByLabel("Command replay timeline");
  await slider.fill(await slider.getAttribute("max") ?? "0");
  await expect(page.getByText(/Blue victory/)).toBeVisible();
  const sample=await (await page.request.get("/api/replays/sample/command")).json();
  await page.locator("input[type=file]").setInputFiles({name:"truncated.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify({...sample,checkpoints:[]}))});
  await expect(page.getByRole("alert")).toContainText("checkpoint");
  await page.locator("input[type=file]").setInputFiles({name:"valid.json",mimeType:"application/json",buffer:Buffer.from(JSON.stringify(sample))});
  await expect(page.getByLabel("Command replay timeline")).toBeVisible();
});

test("Command battle finishes and opens its recorded replay", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Play Echelon"}).click();
  await page.getByRole("button",{name:/Command Real-time battlefield/}).click();
  const created=page.waitForResponse((r) => r.url().endsWith("/api/command") && r.request().method()==="POST");
  await page.getByRole("button",{name:/Begin battle/}).click();
  const id=(await (await created).json()).id as string;
  for (const [unit,target] of [["B1","R1"],["B2","R2"],["B3","R4"]]) {
    const response=await page.request.post(`/api/command/${id}/orders`,{data:{ids:[unit],kind:"ATTACK",target}});
    expect(response.status()).toBe(200);
  }
  await page.getByLabel("Simulation speed").selectOption("4");
  await expect(page.locator(".war-victory")).toBeVisible({timeout:60_000});
  let pollsAfterFinish=0;
  page.on("request", (request) => {if (request.url().endsWith(`/api/command/${id}`) && request.method()==="GET") pollsAfterFinish++;});
  await page.waitForTimeout(650);
  expect(pollsAfterFinish).toBe(0);
  await expect(page.getByRole("button",{name:"Pause",exact:true})).toBeDisabled();
  const metrics=await page.evaluate(() => (window as Window & {__echelonMetrics?: {fps:number;p95FrameMs:number;sampleCount:number}}).__echelonMetrics);
  expect(metrics?.sampleCount).toBeGreaterThan(30);
  console.log("Command browser frame metrics",metrics);
  const downloaded=page.waitForEvent("download");
  await page.getByRole("button",{name:"Download replay"}).click();
  expect((await downloaded).suggestedFilename()).toContain("echelon-command-");
  await page.getByRole("button",{name:"Study replay"}).click();
  await expect(page.getByLabel("Command replay timeline")).toBeVisible();
});

test("Command pauses polling and recovers clearly from expired sessions", async ({page}) => {
  await page.goto("/");
  await page.getByRole("button",{name:"Play Echelon"}).click();
  await page.getByRole("button",{name:/Command Real-time battlefield/}).click();
  const created=page.waitForResponse((r) => r.url().endsWith("/api/command") && r.request().method()==="POST");
  await page.getByRole("button",{name:/Begin battle/}).click();
  const id=(await (await created).json()).id as string;
  await page.getByRole("button",{name:"Pause",exact:true}).click();
  let polls=0;
  page.on("request", (request) => {if (request.url().endsWith(`/api/command/${id}`) && request.method()==="GET") polls++;});
  await page.waitForTimeout(650);
  expect(polls).toBe(0);
  await page.route(`**/api/command/${id}/control`, (route) => route.fulfill({status:503,body:JSON.stringify({detail:"Temporary network error"}),contentType:"application/json"}), {times:1});
  await page.getByRole("button",{name:"Resume",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Temporary network error");
  await expect(page.getByRole("button",{name:"Resume",exact:true})).toBeEnabled();
  await page.route(`**/api/command/${id}`, (route) => route.request().method()==="GET" ? route.fulfill({status:404,body:JSON.stringify({detail:"Command session not found"}),contentType:"application/json"}) : route.continue());
  await page.getByRole("button",{name:"Resume",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Command session expired. Start a new battle.");
  const count=polls;
  await page.waitForTimeout(650);
  expect(polls).toBe(count);
  await page.getByRole("button",{name:"New battle"}).click();
  await expect(page.getByRole("button",{name:/Begin battle/})).toBeVisible();
});
