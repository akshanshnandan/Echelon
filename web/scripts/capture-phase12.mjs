// Visual QA against the locally running FastAPI site. Run from web/.
import { chromium } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';

const base = process.env.ECHELON_BASE_URL ?? 'http://127.0.0.1:8000';
const browser = await chromium.launch({headless:true});
const capture = async (viewport, name, actions) => {
  const page = await browser.newPage({viewport,deviceScaleFactor:1});
  await page.goto(base);
  await actions(page);
  await page.screenshot({path:`../docs/phase12_${name}.png`,fullPage:true});
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  if (overflow) throw new Error(`${name} has horizontal overflow`);
  await page.close();
};
await capture({width:1440,height:900},'home_desktop', async (page) => {await page.waitForTimeout(900);});
await capture({width:1440,height:900},'command_desktop', async (page) => {
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await page.getByRole('button',{name:/Command Real-time battlefield/}).click();
  await page.getByLabel('Battlefield map').selectOption('ridge_forest');
  await page.getByRole('button',{name:/Begin battle/}).click();
  await page.locator("svg[aria-label='Command battlefield'] g[data-unit-id]").first().click();
  await page.locator("svg[aria-label='Command battlefield']").click({position:{x:480,y:345}});
  await page.waitForTimeout(1100);
  const metrics = await page.evaluate(() => window.__echelonMetrics);
  const path='../docs/phase12_performance.json';
  const existing=await readFile(path,'utf8').then(JSON.parse).catch(()=>({}));
  await writeFile(path,JSON.stringify({viewport:'1440x900',browser:'Playwright Chromium headless',metrics,completeBattleSamples:existing.completeBattleSamples ?? []},null,2));
});
await capture({width:1440,height:900},'builder_desktop', async (page) => {
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await page.getByRole('button',{name:/Expanded Draft your own army/}).click();
  await page.waitForTimeout(500);
});
await capture({width:1440,height:900},'replay_desktop', async (page) => {
  await page.getByRole('button',{name:'Replays'}).click();
  await page.getByRole('button',{name:'Open Command sample'}).click();
  await page.getByLabel('Command replay timeline').fill('120');
});
await capture({width:900,height:1100},'tablet', async (page) => {
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await page.getByRole('button',{name:/Command Real-time battlefield/}).click();
  await page.getByRole('button',{name:/Begin battle/}).click();
  await page.waitForTimeout(500);
});
await capture({width:390,height:844},'mobile', async (page) => {
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await page.getByRole('button',{name:/Command Real-time battlefield/}).click();
  await page.getByRole('button',{name:/Begin battle/}).click();
  await page.waitForTimeout(500);
});
await browser.close();
