import { chromium } from '@playwright/test';

const base = process.env.ECHELON_BASE_URL ?? 'http://127.0.0.1:8000';
const headless = process.env.HEADFUL !== '1';
const viewport = process.env.MOBILE === '1' ? {width:390,height:844} : {width:1440,height:900};
const browser = await chromium.launch({headless});
const page = await browser.newPage({viewport,deviceScaleFactor:1});
const cdp = await page.context().newCDPSession(page);
await page.goto(base);
await page.getByRole('button',{name:'Play Echelon'}).click();
await page.getByRole('button',{name:/Command Real-time battlefield/}).click();
await page.getByLabel('Battlefield map').selectOption('ridge_forest');
const created = page.waitForResponse(r => r.url().endsWith('/api/command') && r.request().method()==='POST');
await page.getByRole('button',{name:/Begin battle/}).click();
const id = (await (await created).json()).id;
await page.evaluate(() => {
  window.__profile = { frames:[], longs:[], polls:[], started:performance.now() };
  let last = performance.now();
  function frame(now) { window.__profile.frames.push([now,now-last]); last=now; requestAnimationFrame(frame); }
  requestAnimationFrame(frame);
  new PerformanceObserver(list => { for(const e of list.getEntries()) window.__profile.longs.push([e.startTime,e.duration]); }).observe({entryTypes:['longtask']});
});
page.on('response', async r => {if (r.url().includes(`/api/command/${id}`) && r.request().method()==='GET') {
  await page.evaluate(v => window.__profile?.polls.push(v), {status:r.status()}).catch(()=>{});
}});
if (process.env.INTERACTIVE === '1') await page.getByRole('button',{name:'Pause',exact:true}).click();
for (const [unit,target] of [['B1','R1'],['B2','R2'],['B3','R4']]) await page.request.post(`${base}/api/command/${id}/orders`,{data:{ids:[unit],kind:'ATTACK',target}});
if (process.env.INTERACTIVE === '1') {
  await page.locator('[data-unit-id="B1"]').click();
  await page.locator('[data-unit-id="B2"]').click({modifiers:['Shift']});
  await page.getByRole('button',{name:'Zoom in'}).click();
  const beforePan = await page.locator('svg[aria-label="Command battlefield"]').getAttribute('viewBox');
  await page.getByRole('button',{name:'Pan',exact:true}).click();
  const box = await page.locator('svg[aria-label="Command battlefield"]').boundingBox();
  await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);
  await page.mouse.down();
  await page.mouse.move(box.x+box.width*.65,box.y+box.height*.5,{steps:12});
  await page.mouse.up();
  if (await page.locator('.war-inspector-unit').count() !== 2) throw new Error('Multiple selection failed');
  if (await page.locator('svg[aria-label="Command battlefield"]').getAttribute('viewBox') === beforePan) throw new Error('Camera did not move');
  await page.getByRole('button',{name:'Resume',exact:true}).click();
}
await page.getByLabel('Simulation speed').selectOption('4');
const trace = [];
cdp.on('Tracing.dataCollected', ({value}) => trace.push(...value));
await cdp.send('Tracing.start',{categories:'devtools.timeline,blink.user_timing,toplevel,disabled-by-default-devtools.timeline',transferMode:'ReportEvents'});
await page.locator('.war-victory').waitFor({timeout:60000});
await cdp.send('Tracing.end');
await new Promise(resolve => cdp.once('Tracing.tracingComplete',resolve));
const raw = await page.evaluate(() => window.__profile);
const finalState = await (await page.request.get(`${base}/api/command/${id}`)).json();
const hitCount = finalState.battle.events.filter(e=>e.type==='hit').length;
if (hitCount === 0) throw new Error('Battle produced no hit effects');
const percentile = (v,p) => v.sort((a,b)=>a-b)[Math.min(v.length-1,Math.floor(v.length*p))];
const frames=raw.frames.map(v=>v[1]).filter(v=>v>0);
const byWindow = [];
for(let i=0;i<frames.length;i+=300) { const f=frames.slice(i,i+300); byWindow.push({fps:1000/(f.reduce((a,b)=>a+b,0)/f.length),p95:percentile([...f],.95),count:f.length}); }
const types={};
for (const e of trace) if(e.ph==='X' && e.dur && ['FunctionCall','EvaluateScript','Layout','Paint','UpdateLayerTree','RecalculateStyles','RunTask','Animation','FireAnimationFrame','ParseHTML','XHRReadyStateChange'].includes(e.name)) {const t=types[e.name]??={count:0,ms:0,max:0}; t.count++;t.ms+=e.dur/1000;t.max=Math.max(t.max,e.dur/1000);}
const result={headless,viewport,interactive:process.env.INTERACTIVE==='1',ua:await page.evaluate(()=>navigator.userAgent),durationMs:frames.reduce((a,b)=>a+b,0),fps:1000/(frames.reduce((a,b)=>a+b,0)/frames.length),p95FrameMs:percentile([...frames],.95),frameCount:frames.length,byWindow,hitCount,longTaskCount:raw.longs.length,pollCount:raw.polls.length,traceTypes:types};
console.log(JSON.stringify(result,null,2));
await browser.close();
