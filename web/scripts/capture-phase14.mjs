import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const base = process.env.ECHELON_BASE_URL ?? 'http://127.0.0.1:8000';
const frames = '../docs/.phase14_frames';
await mkdir(frames, {recursive:true});
const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1440,height:900},deviceScaleFactor:1});
await page.goto(base);
await page.getByRole('button',{name:'Play Echelon'}).click();
await page.getByLabel('Battle size').selectOption('grand');
const created = page.waitForResponse(r => r.url().endsWith('/api/command') && r.request().method()==='POST');
await page.getByRole('button',{name:/Begin battle/}).click();
const id = (await (await created).json()).id;
await page.getByRole('button',{name:'Got it'}).click().catch(()=>{});
await page.getByRole('navigation',{name:'Friendly formations'}).getByRole('button',{name:'Select all'}).click();
await page.screenshot({path:'../docs/phase14_grand_deployment.png'});
for (const [unit,target] of [['B1','R1'],['B2','R2'],['B3','R4']])
  await page.request.post(`${base}/api/command/${id}/orders`,{data:{ids:[unit],kind:'ATTACK',target}});
await page.getByLabel('Simulation speed').selectOption('4');
let routed = false;
for (let i=0;i<45;i++) {
  await page.waitForTimeout(800);
  const state = await (await page.request.get(`${base}/api/command/${id}`)).json();
  const hasRouting = Object.values(state.battle.units).some(u => u.morale_state === 'routing');
  if (hasRouting && !routed) {await page.screenshot({path:'../docs/phase14_routing.png'});routed=true;}
  await page.locator('.war-field-wrap').screenshot({path:`${frames}/${String(i).padStart(3,'0')}.png`});
  if (state.battle.finished) break;
}
if (!routed) throw new Error('No routing appeared in captured battle');
await page.locator('.war-victory').waitFor();
await page.screenshot({path:'../docs/phase14_result.png'});
console.log(JSON.stringify({id,frames:routed}));
await browser.close();
