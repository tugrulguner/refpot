import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const [source, target, height] of [
    ['../../docs/assets/refpot-lockup.svg', '../../docs/assets/refpot-lockup.png', 900],
    ['../public/social-card.svg', '../public/social-card.png', 630],
  ]) {
    await page.setViewportSize({ width: 1200, height });
    await page.setContent('<style>html,body{margin:0;padding:0}svg{display:block}</style>' + await readFile(new URL(source, import.meta.url), 'utf8'));
    await page.evaluate(() => document.fonts.ready);
    await page.locator('svg').screenshot({ path: new URL(target, import.meta.url).pathname });
  }
  await writeFile(new URL('../public/refpot-lockup.png', import.meta.url), await readFile(new URL('../../docs/assets/refpot-lockup.png', import.meta.url)));
} finally { await browser.close(); }
