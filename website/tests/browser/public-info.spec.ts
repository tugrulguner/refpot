import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
for (const width of [1280, 390]) {
  test(`public identity and database discovery are truthful at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/');
    await expect(page).toHaveTitle('Embedded Database for Python | RefPot');
    await expect(page.locator('.framework-art img')).toHaveAttribute('src', '/refpot-lockup.png?v=public-info-1');
    await expect(page.locator('.framework-art img')).toHaveAttribute('alt', /experimental alpha.*CRUD.*transactions/);
    await expect(page.locator('.framework-copy')).toContainText('qualification remains limited');
    const graph = await page.locator('script[type="application/ld+json"]').evaluateAll(nodes => nodes.map(node => JSON.parse(node.textContent || '{}')));
    expect(JSON.stringify(graph)).toContain('C++');
    expect(JSON.stringify(graph)).toContain('Python');
    const image = page.locator('.framework-art img');
    await image.scrollIntoViewIfNeeded();
    await expect.poll(() => image.evaluate(im => (im as HTMLImageElement).complete && (im as HTMLImageElement).naturalWidth > 0)).toBe(true);
    await image.screenshot({ path: test.info().outputPath(`lockup-${width}.png`) });
    await page.screenshot({ path: test.info().outputPath(`home-${width}.png`), fullPage: true });
  });
}
for (const [name, file] of [['lockup', '../../../docs/assets/refpot-lockup.svg'], ['social', '../../public/social-card.svg']]) {
  test(`${name} text fits its preserved canonical canvas`, async ({ page }) => {
    const svg = await readFile(new URL(file, import.meta.url), 'utf8');
    await page.setContent(svg);
    await page.evaluate(() => document.fonts.ready);
    const overflow = await page.locator('svg text').evaluateAll(nodes => nodes.filter(node => {
      const box = (node as SVGGraphicsElement).getBBox();
      const root = (node as SVGElement).ownerSVGElement!;
      return box.x < 0 || box.x + box.width > root.viewBox.baseVal.width || box.y < 0 || box.y + box.height > root.viewBox.baseVal.height;
    }).map(node => node.textContent));
    expect(overflow).toEqual([]);
    await expect(page.locator('svg')).not.toContainText('A simple Python ORM');
  });
}
