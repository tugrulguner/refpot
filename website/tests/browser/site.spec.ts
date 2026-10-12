import { gunzipSync } from 'node:zlib';
import { test, expect } from '@playwright/test';
import { sanitizeAnalyticsProperties } from '../../src/analytics-privacy.mjs';
const routes = ['/', '/package/', '/package-contract/', '/build/crud/', '/build/transactions/', '/build/persistence/', '/build/errors/', '/reference/api/', '/internals/recovery/', '/status/', '/design/', '/performance-method/', '/project/roadmap/', '/does-not-exist/'];
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
      await expect(page.locator('main h1')).toHaveText('A custom embedded database for Python.');
      await expect(page.locator('.research-notice')).toBeVisible();
      await expect(page.locator('.framework-actions a')).toHaveText(['Quick start','Examples','GitHub']);
      await expect(page.locator('.framework-actions a').nth(0)).toHaveAttribute('href','/package/');
      await expect(page.locator('.framework-actions a').nth(1)).toHaveAttribute('href','https://github.com/tugrulguner/refpot/tree/main/examples');
      await expect(page.locator('.framework-actions a').nth(2)).toHaveAttribute('href','https://github.com/tugrulguner/refpot');
      await expect(page.locator('.framework-copy .creator-attribution')).toBeVisible();
      await expect(page.locator('.installation-strip code')).toHaveText('python -m pip install refpot==0.1.1');
      const python = page.locator('pre').filter({ hasText: 'from refpot import Database, Row' }).first();
      await expect(python).toHaveCount(1);
      await expect(python).toContainText('db.insert(1, 42, "answer")');
      await expect(python.locator('xpath=ancestor::figure').getByRole('button', { name: /copy to clipboard/i })).toHaveCount(1);
      await expect(page.locator('main h2')).toContainText(['A first database','Historical package architecture','Run the shipped CRUD and transaction examples']);
      await expect(page.getByRole('link',{name:'Full-size editable SVG'})).toHaveAttribute('href','/refpot-package.svg');
      await expect(page.locator('.pagination-links a[rel="next"]')).toHaveCount(1);
      await expect(page.locator('.pagination-links a[rel="next"]')).toHaveAttribute('href','/package/');
      await expect(page.locator('.pagination-links a[rel="next"]')).toContainText('Quick start');
      await expect(page.locator('iframe')).toHaveCount(0);
      const measured = await page.evaluate(() => {
        const copy=document.querySelector('.framework-copy')!.getBoundingClientRect();
        const art=document.querySelector('.framework-art')!.getBoundingClientRect();
        const actions=document.querySelector('.framework-actions')!.getBoundingClientRect();
        const creator=document.querySelector('.creator-attribution')!.getBoundingClientRect();
        return { overflow:document.documentElement.scrollWidth>innerWidth, copy:{left:copy.left,right:copy.right,top:copy.top,bottom:copy.bottom}, art:{left:art.left,top:art.top}, creatorTop:creator.top, creatorBottom:creator.bottom, actionsBottom:actions.bottom };
      });
      const isDark = theme === 'dark';
      await expect(page.locator('header .refpot-mark')).toHaveCSS('filter', isDark ? 'none' : 'brightness(0.31)');
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
        for(const label of ['GitHub','Community','About Tugrul','Research status','Package preview','Package contract','Roadmap']) await expect(menu.getByRole('link',{name:label,exact:true})).toBeVisible();
        await page.keyboard.press('Escape'); await expect(menu).toBeHidden(); await expect(toggle).toBeFocused();
      }
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    }
  }
});

test('task guides render their API examples and mobile code-copy controls work', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  for (const route of ['/build/crud/', '/build/transactions/', '/build/persistence/', '/build/errors/', '/reference/api/', '/internals/recovery/']) {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(route);
    await expect(page.locator('main h1')).toHaveCount(1);
    await expect(page.locator('main')).toContainText(/Database|transaction|snapshot|recovery/i);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.goto('/package/');
  const code = page.locator('pre').first();
  await expect(code).toBeVisible();
  const figure = code.locator('xpath=ancestor::figure');
  const copy = figure.getByRole('button', { name: /copy to clipboard/i });
  await expect(copy).toBeVisible();
  await copy.click();
  await expect(copy).toHaveAttribute('data-copied', 'Copied!');
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('python -m pip install refpot==0.1.1');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
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


test('PostHog preserves sanitized existing acquisition state and emits real pageviews', async ({ browser }) => {
  const token = 'phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V';
  const distinctId = 'persisted-sdk-regression';
  const context = await browser.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
  await context.addInitScript(({ token, distinctId }) => {
    Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => false });
    Object.defineProperty(Navigator.prototype, 'userAgentData', { get: () => ({ brands: [{ brand: 'Chromium', version: '131' }, { brand: 'Google Chrome', version: '131' }, { brand: 'Not:A-Brand', version: '99' }], mobile: false, platform: 'macOS', getHighEntropyValues: async () => ({}), toJSON: () => ({}) }) });
    localStorage.setItem(`ph_${token}_posthog`, JSON.stringify({ distinct_id: distinctId, '$device_id': distinctId, '$initial_utm_source': 'PERSISTED_SOURCE_SENTINEL', '$initial_referrer': 'https://persisted.example/path?private=PERSISTED_REFERRER_SENTINEL', '$session_entry_utm_source': 'PERSISTED_SESSION_SOURCE_SENTINEL', '$session_entry_gclid': 'PERSISTED_SESSION_CLICK_SENTINEL' }));
  }, { token, distinctId });
  const page = await context.newPage();
  const requests: { url: string; body: Buffer }[] = [];
  await page.route('**/*', async route => {
    const request = route.request();
    const body = request.postDataBuffer();
    if (request.method() === 'POST' && new URL(request.url()).hostname.endsWith('posthog.com')) requests.push({ url: request.url(), body: body ?? Buffer.alloc(0) });
    if ((new URL(request.url()).pathname.includes('/e/') || new URL(request.url()).pathname.includes('/i/v0/e/'))) await route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' });
    else await route.continue();
  });
  await page.goto('/?utm_source=PRIVATE_CAMPAIGN&gclid=PRIVATE_AD_CLICK&safe=PRIVATE_QUERY#PRIVATE_FRAGMENT', { referer: 'https://ref.example/path?private=PRIVATE_REFERRER' });
  await page.waitForFunction(() => (window as any).posthog?.__loaded === true);
  const runtime = await page.evaluate(() => { const ph = (window as any).posthog; return { capturing: ph.is_capturing(), distinctId: ph.get_distinct_id(), initialSource: ph.get_property('$initial_utm_source'), sessionSource: ph.get_property('$session_entry_utm_source'), initialReferrer: ph.get_property('$initial_referrer'), sessionClick: ph.get_property('$session_entry_gclid') }; });
  expect(runtime.capturing).toBe(true);
  expect(runtime.distinctId).toBe(distinctId);
  expect(runtime.initialSource).toBe('PERSISTED_SOURCE_SENTINEL');
  expect(runtime.sessionSource).toBe('PERSISTED_SESSION_SOURCE_SENTINEL');
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  await page.goto('/package/');
  await expect.poll(() => requests.length).toBeGreaterThan(1);
  const decoded = requests.map(({ body }) => { const text = body[0] === 0x1f && body[1] === 0x8b ? gunzipSync(body).toString('utf8') : body.toString('utf8'); return JSON.parse(text); });
  const events = decoded.flatMap(payload => Array.isArray(payload.batch) ? payload.batch : Array.isArray(payload) ? payload : [payload]);
  const pageviews = events.filter(event => event.event === '$pageview');
  expect(pageviews.length).toBeGreaterThanOrEqual(2);
  expect(pageviews.some(event => event.properties?.$pathname === '/')).toBe(true);
  expect(pageviews.some(event => event.properties?.$pathname === '/package/')).toBe(true);
  const envelope = decoded.map(payload => JSON.stringify(payload)).join(' ');
  for (const sentinel of ['PERSISTED_SOURCE_SENTINEL','PERSISTED_REFERRER_SENTINEL','PERSISTED_SESSION_SOURCE_SENTINEL','PERSISTED_SESSION_CLICK_SENTINEL','PRIVATE_CAMPAIGN','PRIVATE_AD_CLICK','PRIVATE_QUERY','PRIVATE_FRAGMENT','PRIVATE_REFERRER']) expect(envelope).not.toContain(sentinel);
  await context.close();
});

test('PostHog opt-out is honored from either persisted cookie or local storage', async ({ browser }) => {
  const token = 'phc_qXkp5FBQfrqHQwkqf3ys8iSoGoMYw2tpTHXGugXJhP8V';
  for (const storage of ['cookie', 'localStorage'] as const) {
    const context = await browser.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
    await context.addInitScript(({ token, storage }) => {
      Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });
      if (storage === 'localStorage') localStorage.setItem(`__ph_opt_in_out_${token}`, '0');
      else document.cookie = `__ph_opt_in_out_${token}=0; path=/; SameSite=Lax`;
    }, { token, storage });
    const page = await context.newPage();
    const ingestion: string[] = [];
    await page.route('**/*', async route => {
      const request = route.request();
      if (request.method() === 'POST' && (new URL(request.url()).pathname.includes('/e/') || new URL(request.url()).pathname.includes('/i/v0/e/'))) {
        ingestion.push(request.url());
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' });
      } else await route.continue();
    });
    await page.goto('/');
    await page.waitForFunction(() => (window as any).posthog?.__loaded === true);
    const runtime = await page.evaluate(() => { const ph = (window as any).posthog; return { capturing: ph.is_capturing(), optedOut: ph.has_opted_out_capturing() }; });
    expect(runtime).toEqual({ capturing: false, optedOut: true });
    expect(ingestion).toEqual([]);
    await context.close();
  }
});

test('PostHog drops query, fragment, and uncontrolled campaign data from every envelope field', async ({ browser }) => {
  const context = await browser.newContext({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
  await context.addInitScript(() => {
    Object.defineProperty(Navigator.prototype, 'webdriver', { get: () => undefined });
    Object.defineProperty(Navigator.prototype, 'userAgentData', { get: () => ({ brands: [{ brand: 'Chromium', version: '131' }, { brand: 'Google Chrome', version: '131' }], mobile: false, platform: 'macOS' }) });
  });
  const page = await context.newPage();
  const requests: { url: string; body: Buffer }[] = [];
  const sdkTrace: string[] = [];
  page.on('requestfailed', request => sdkTrace.push(`failed ${request.url()} ${request.failure()?.errorText}`));
  page.on('console', message => sdkTrace.push(`console ${message.type()} ${message.text()}`));
  page.on('pageerror', error => sdkTrace.push(`pageerror ${error.message}`));
  page.on('response', response => { if (response.url().includes('posthog')) sdkTrace.push(`response ${response.status()} ${response.url()}`); });
  await page.route('**/*', async route => {
    const request = route.request();
    if (new URL(request.url()).hostname.endsWith('posthog.com')) sdkTrace.push(`request ${request.method()} ${request.url()}`);
    const body = request.postDataBuffer();
    if (request.method() === 'POST') requests.push({ url: request.url(), body: body ?? Buffer.alloc(0) });
    if (/\/(?:i\/v0\/)?e\//.test(new URL(request.url()).pathname)) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{"status":"ok"}' });
    } else await route.continue();
  });
  await page.goto('/?utm_source=PRIVATE_CAMPAIGN&gclid=PRIVATE_AD_CLICK&safe=PRIVATE_QUERY#PRIVATE_FRAGMENT');
  await expect.poll(() => requests.length).toBeGreaterThan(0);
  await page.locator('a[href="/package/"]:visible').first().click();
  await expect(page).toHaveURL(/\/package\/$/);
  await expect.poll(() => requests.length).toBeGreaterThan(1);
  const decodedRequests = requests.map(({ body }) => {
    const decoded = body[0] === 0x1f && body[1] === 0x8b ? gunzipSync(body).toString('utf8') : body.toString('utf8');
    return JSON.parse(decoded);
  });
  const events = decodedRequests.flatMap(payload => Array.isArray(payload.batch) ? payload.batch : Array.isArray(payload) ? payload : [payload]);
  expect(events.filter(event => event.event === '$pageview').length).toBeGreaterThanOrEqual(2);
  expect(events.some(event => event.event === '$pageview' && event.properties?.$pathname === '/')).toBe(true);
  expect(events.some(event => event.event === '$pageview' && event.properties?.$pathname === '/package/')).toBe(true);
  const sample = sanitizeAnalyticsProperties({ $current_url: 'https://refpot.modepot.io/package/?secret=PRIVATE_QUERY#PRIVATE_FRAGMENT', $set: { $initial_utm_source: 'PRIVATE_CAMPAIGN', $session_entry_gclid: 'PRIVATE_AD_CLICK', $initial_referrer: 'https://secret.example/?private=PRIVATE_QUERY' }, $set_once: { $session_exit_gad_source: 'PRIVATE_AD_CLICK', $initial_qclid: 'PRIVATE_AD_CLICK' }, timestamp: new Date('2026-01-02T00:00:00Z') });
  expect(JSON.stringify(sample)).not.toMatch(/PRIVATE_(?:QUERY|FRAGMENT|CAMPAIGN|AD_CLICK)/);
  expect(sample.$current_url).toBe('https://refpot.modepot.io/package/');
  expect(sample.timestamp).toEqual(new Date('2026-01-02T00:00:00Z'));
  const envelope = requests.map(({ body }) => {
    const decoded = body[0] === 0x1f && body[1] === 0x8b ? gunzipSync(body).toString('utf8') : body.toString('utf8');
    return decoded;
  }).join(' ');
  for (const sentinel of ['PRIVATE_CAMPAIGN', 'PRIVATE_AD_CLICK', 'PRIVATE_QUERY', 'PRIVATE_FRAGMENT']) expect(envelope).not.toContain(sentinel);
});
