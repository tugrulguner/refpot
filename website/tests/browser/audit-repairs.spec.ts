import { test, expect } from '@playwright/test';
test('native skip link reaches the homepage content rather than a missing target',async({page})=>{
 await page.goto('/');
 await page.keyboard.press('Tab');
 await expect(page.locator('a[href="#_top"]').first()).toBeFocused();
 await page.keyboard.press('Enter');
 await expect(page.locator('#_top')).toBeFocused();
 await expect(page.locator('#_top')).toHaveAttribute('aria-labelledby','refpot-title');
 await expect(page.locator('#refpot-title')).toBeVisible();
});
test('all seven reproduced broken document destinations are published correctly',async({page,request})=>{
 for(const path of ['/internals/recovery/','/reference/api/']){
  await page.goto(path);
  const results=page.locator('main a[href="/project/package-performance/"]');
  await expect(results.first()).toBeVisible();
  expect((await request.get('/project/package-performance/')).status()).toBe(200);
  const guide=await page.locator('main').evaluate(el=>Array.from(el.querySelectorAll('a[href]'),a=>a.getAttribute('href')));
  expect(guide).not.toContain('../benchmarks/package-performance/RESULTS.md');
  expect(guide).not.toContain('../benchmarks/package-performance/README.md');
 }
 await page.goto('/project/roadmap/');
 const hrefs=await page.locator('main').evaluate(el=>Array.from(el.querySelectorAll('a[href]'),a=>a.getAttribute('href')));
 expect(hrefs).toContain('/package-contract/');
 expect(hrefs).toContain('/project/package-performance/');
 expect(hrefs.some(href=>/^https:\/\/github\.com\/tugrulguner\/refpot\/blob\/[a-f0-9]{40}\/docs\/releasing\.md$/.test(href??''))).toBeTruthy();
 for(const href of hrefs.filter((value):value is string=>Boolean(value?.startsWith('/')&&!value.startsWith('//')))) expect((await request.get(href)).status(),href).toBe(200);
});
for(const width of [1280,390,320]) for(const theme of ['light','dark'] as const){
 test(`unchanged homepage artwork and repaired keyboard target at ${width}px ${theme}`,async({page},info)=>{
  await page.setViewportSize({width,height:850});
  await page.emulateMedia({colorScheme:theme});
  await page.addInitScript(value=>localStorage.setItem('starlight-theme',value),theme);
  await page.goto('/');
  await expect(page.locator('.framework-hero')).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:info.outputPath(`refpot-${width}-${theme}.png`)});
 });
}

test('deep homepage diagrams defer requests and decode after scrolling',async({page})=>{
 await page.setViewportSize({width:320,height:850}); await page.goto('/');
 const deep=['/refpot-package.png','/refpot-benchmark.png','/refpot-execution.png'];
 for(const path of deep){const img=page.locator(`main img[src^="${path}"]`); await expect(img).toHaveAttribute('loading','lazy'); await expect(img).toHaveAttribute('width',/\d+/); await expect(img).toHaveAttribute('height',/\d+/);}
 const imageStates=await page.locator('main img').evaluateAll(images=>images.map(element=>{const image=element as HTMLImageElement;return {src:image.currentSrc,loading:image.loading,complete:image.complete}}));
 expect(imageStates.filter(image=>deep.some(path=>image.src.endsWith(path) || image.src.includes(path+'?'))).every(image=>image.loading==='lazy')).toBe(true);
 expect(imageStates.filter(image=>image.src.includes('/refpot-execution.png')).every(image=>!image.complete)).toBe(true);
 for(const path of deep){const img=page.locator(`main img[src^="${path}"]`); await img.scrollIntoViewIfNeeded(); await expect.poll(()=>img.evaluate(el=>{const image=el as HTMLImageElement; return image.complete&&image.naturalWidth>0})).toBe(true);}
});
