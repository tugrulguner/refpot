import { test, expect } from '@playwright/test';
const routes = ['/', '/status/', '/design/', '/performance-method/', '/project/roadmap/', '/does-not-exist/'];
const resources = ['ModePot', 'GitHub', 'Community', 'About Tugrul'];
for (const width of [1280, 768, 390, 320]) {
  for (const theme of ['light', 'dark', 'auto']) {
    test(`homepage ${width}px theme=${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme === 'light' ? 'dark' : 'light' });
      await page.route('**/*posthog.com/**', route => route.abort());
      await page.goto('/');
      await page.locator('header starlight-theme-select select').selectOption(theme);
      await expect(page.locator('html')).toHaveAttribute('data-theme', theme === 'auto' ? 'light' : theme);
      await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(img => img.decode())); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); });
      await expect(page.locator('main h1')).toHaveCount(1);
      await expect(page.locator('main h1')).toHaveText('A custom relational engine. A simple Python ORM.');
      await expect(page.locator('.research-notice')).toBeVisible();
      await expect(page.locator('.framework-actions a')).toHaveText(['Research status','Design direction','GitHub']);
      await expect(page.locator('.framework-copy .creator-attribution')).toBeVisible();
      await expect(page.locator('.pagination-links a[rel="next"]')).toHaveCount(1);
      await expect(page.locator('.pagination-links a[rel="next"]')).toHaveAttribute('href','/status/');
      await expect(page.locator('.pagination-links a[rel="next"]')).toContainText('Research status');
      await expect(page.locator('iframe')).toHaveCount(0);
      const measured = await page.evaluate(() => {
        const copy=document.querySelector('.framework-copy')!.getBoundingClientRect();
        const art=document.querySelector('.framework-art')!.getBoundingClientRect();
        const actions=document.querySelector('.framework-actions')!.getBoundingClientRect();
        const creator=document.querySelector('.creator-attribution')!.getBoundingClientRect();
        return { overflow:document.documentElement.scrollWidth>innerWidth, copy:{left:copy.left,right:copy.right,top:copy.top,bottom:copy.bottom}, art:{left:art.left,top:art.top}, creatorTop:creator.top, creatorBottom:creator.bottom, actionsBottom:actions.bottom };
      });
      const isDark = theme === 'dark';
      await expect(page.locator('.framework-action.primary')).toHaveCSS('color', isDark ? 'rgb(24, 26, 29)' : 'rgb(255, 255, 255)');
      await expect(page.locator('.framework-action.primary')).toHaveCSS('background-color', isDark ? 'rgb(244, 242, 234)' : 'rgb(73, 81, 94)');
      await expect(page.locator('.sl-markdown-content p a[href="/design/"]')).toHaveCSS('color', isDark ? 'rgb(244, 242, 234)' : 'rgb(73, 81, 94)');
      expect(measured.overflow).toBe(false);
      expect(measured.creatorTop).toBeGreaterThanOrEqual(measured.actionsBottom);
      expect(measured.creatorBottom).toBeLessThan(900);
      if (width >= 768) expect(measured.art.left).toBeGreaterThanOrEqual(measured.copy.right);
      else expect(measured.art.top).toBeGreaterThanOrEqual(measured.copy.bottom);
      await page.screenshot({path:testInfo.outputPath('homepage.png'),fullPage:true});
    });
  }
}

test('every layout preserves desktop and compact family navigation with keyboard access', async ({ page }) => {
  for (const width of [1280,320]) {
    await page.setViewportSize({width,height:900});
    for (const route of routes) {
      const response=await page.goto(route);
      expect(response!.status()).toBe(route.includes('does-not') ? 404 : 200);
      await expect(page.locator('main h1')).toHaveCount(1);
      if(width===1280) {
        await expect(page.locator('.family-resources a')).toHaveText(resources);
        for(const link of await page.locator('.family-resources a').all()) await expect(link).toBeVisible();
      } else {
        await expect(page.getByRole('link',{name:'ModePot',exact:true})).toBeVisible();
        const toggle=page.getByRole('button',{name:'Menu',exact:true});
        await toggle.focus(); await page.keyboard.press('Enter');
        const menu=page.getByRole('region',{name:'Menu',exact:true});
        for(const label of ['GitHub','Community','About Tugrul','Research status','Roadmap']) await expect(menu.getByRole('link',{name:label,exact:true})).toBeVisible();
        await page.keyboard.press('Escape'); await expect(menu).toBeHidden(); await expect(toggle).toBeFocused();
      }
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }
  }
});

test('Auto follows live OS changes, metadata and the social raster are real',async({page})=>{
  await page.emulateMedia({colorScheme:'light'}); await page.goto('/');
  await page.locator('header starlight-theme-select select').selectOption('auto');
  await page.emulateMedia({colorScheme:'dark'}); await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.emulateMedia({colorScheme:'light'}); await expect(page.locator('html')).toHaveAttribute('data-theme','light');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href','https://refpot.modepot.io/');
  const data=JSON.parse(await page.locator('script[type="application/ld+json"]').innerText());
  expect(data['@graph'].map((item:{'@type':string})=>item['@type'])).toEqual(['SoftwareSourceCode','WebSite']);
  const image=await page.request.get('/social-card.png?v=offwhite-1'); expect(image.status()).toBe(200);
  const bytes=await image.body(); expect([bytes.readUInt32BE(16),bytes.readUInt32BE(20)]).toEqual([1200,630]);
});
