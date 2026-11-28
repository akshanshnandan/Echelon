import {expect,test} from '@playwright/test';

test('grand battle drafts, selects and orders fifteen formations', async ({page}) => {
  await page.goto('/');
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await expect(page.getByRole('button',{name:/Command Real-time battlefield/})).toHaveClass(/active/);
  await page.getByLabel('Battle size').selectOption('grand');
  await expect(page.getByText(/15\/15/)).toBeVisible();
  const created=page.waitForResponse(r=>r.url().endsWith('/api/command')&&r.request().method()==='POST');
  await page.getByRole('button',{name:/Begin battle/}).click();
  const initial=await (await created).json();
  expect(initial.battle.ruleset_version).toBe(4);
  expect(Object.keys(initial.battle.units)).toHaveLength(30);
  await page.getByRole('button',{name:'Pause',exact:true}).click();
  await page.getByRole('navigation',{name:'Friendly formations'}).getByRole('button',{name:'Select all'}).click();
  await expect(page.locator('.war-inspector-unit')).toHaveCount(15);
  const field=page.locator('svg[aria-label="Command battlefield"]');
  await field.click({position:{x:450,y:270}});
  const state=await (await page.request.get(`/api/command/${initial.id}`)).json();
  expect(Object.values(state.battle.units).filter((u:any)=>u.army==='Blue'&&u.order==='MOVE')).toHaveLength(15);
  await page.getByRole('button',{name:'Zoom in'}).click();
  await expect(field).toHaveAttribute('viewBox',/ /);
});

test('grand battle controls remain within mobile viewport',async ({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await page.getByRole('button',{name:'Play Echelon'}).click();
  await page.getByLabel('Battle size').selectOption('grand');
  await page.getByRole('button',{name:/Begin battle/}).click();
  await expect(page.locator('svg[aria-label="Command battlefield"]')).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Friendly formations'}).getByRole('button')).toHaveCount(16);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
