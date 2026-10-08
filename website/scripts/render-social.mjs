import { readFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.setContent('<style>html,body{margin:0;width:1200px;height:630px;overflow:hidden}svg{display:block}</style>' + await readFile(new URL('../public/social-card.svg', import.meta.url), 'utf8'));
  await page.evaluate(() => document.fonts.ready);
  await page.locator('svg').screenshot({ path: new URL('../public/social-card.png', import.meta.url).pathname });
} finally { await browser.close(); }
