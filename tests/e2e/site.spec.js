import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readdirSync, readFileSync, mkdirSync } from 'node:fs';

const CAND = 'src/content/candidates';
const candidates = readdirSync(CAND).filter((f) => f.endsWith('.json')).map((f) => ({ id: f.slice(0, -5), ...JSON.parse(readFileSync(`${CAND}/${f}`, 'utf8')) }));
const KEY_PAGES = ['/', '/work/', '/talks/', '/topics/', '/topics/javafx/', '/work/talk-crabrag/', '/search/', '/404.html'];

mkdirSync('screenshots', { recursive: true });
const slug = (p) => (p === '/' ? 'home' : p.replace(/^\/|\/$/g, '').replace(/[/.]/g, '-'));

test.describe('every key template', () => {
  for (const path of KEY_PAGES) {
    test(`${path}: axe, overflow, one h1, own origin only`, async ({ page }, info) => {
      const foreign = [];
      page.on('request', (r) => { if (!r.url().startsWith('http://127.0.0.1') && !r.url().startsWith('data:')) foreign.push(r.url()); });
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
      expect(results.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`), 'axe violations').toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(0);
      await expect(page.locator('h1')).toHaveCount(1);
      expect(foreign, 'requests to other origins').toEqual([]);
      await page.screenshot({ path: `screenshots/${info.project.name}-${slug(path)}.png`, fullPage: true });
    });
  }
});

test.describe('without JavaScript', () => {
  test.use({ javaScriptEnabled: false });
  test('the full list is reachable and nothing depends on a script', async ({ page }) => {
    await page.goto('/work/');
    await expect(page.locator('#records .record')).toHaveCount(candidates.length);
    await expect(page.locator('#filters')).toBeHidden();
    await page.goto('/talks/');
    const talks = candidates.filter((c) => ['talk', 'video', 'interview'].includes(c.kind)).length;
    await expect(page.locator('#records .record')).toHaveCount(talks);
    await page.goto('/search/');
    await expect(page.getByRole('link', { name: 'Browse the full list' })).toBeVisible();
  });
});

test.describe('keyboard', () => {
  test('the skip link is first, shows focus, and moves focus to the content', async ({ page }) => {
    await page.goto('/');
    await page.keyboard.press('Tab');
    const skip = page.locator('.skip');
    await expect(skip).toBeFocused();
    expect(await skip.evaluate((el) => parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThan(0);
    await page.keyboard.press('Enter');
    await expect(page.locator('main')).toBeFocused();
  });
});

test.describe('filters on /work/', () => {
  test('filters compose, update the status, and an empty result says so', async ({ page }) => {
    await page.goto('/work/');
    const rows = page.locator('#records .record:not([hidden])');
    await expect(rows).toHaveCount(candidates.length);
    await page.selectOption('select[name=kind]', 'talk');
    const talks = candidates.filter((c) => c.kind === 'talk');
    await expect(rows).toHaveCount(talks.length);
    await page.selectOption('select[name=topic]', 'graphrag');
    const both = talks.filter((c) => c.topics.includes('graphrag'));
    await expect(rows).toHaveCount(both.length);
    expect(both.length).toBeLessThan(talks.length);
    await expect(page.locator('#list-status')).toContainText(`Showing ${both.length} of ${candidates.length}`);
    await page.selectOption('select[name=kind]', 'book');
    await page.selectOption('select[name=topic]', 'agents');
    const none = candidates.filter((c) => c.kind === 'book' && c.topics.includes('agents')).length;
    expect(none).toBe(0);
    await expect(rows).toHaveCount(0);
    await expect(page.locator('#list-empty')).toBeVisible();
    expect(new URL(page.url()).search).toContain('kind=book');
  });
});

test.describe('search', () => {
  async function search(page, term) {
    await page.goto('/search/');
    await expect(page.locator('#search-form')).toBeVisible();
    await page.fill('#q', term);
    await page.press('#q', 'Enter');
    await expect(page.locator('#search-status')).not.toHaveText('');
  }
  for (const term of ['steveonjava', 'JavaFX', 'Raspberry Pi', 'DevOps', 'GraphRAG', 'Java FX']) {
    test(`finds "${term}"`, async ({ page }) => {
      await search(page, term);
      await expect(page.locator('#results .result').first()).toBeVisible();
      await expect(page.locator('#search-status')).toContainText(/\d+ results?/);
    });
  }
  test('an unknown word says there are no results', async ({ page }) => {
    await search(page, 'zzzqxv');
    await expect(page.locator('#search-status')).toContainText('No results');
    await expect(page.locator('#results .result')).toHaveCount(0);
  });
  test('a format filter narrows a search', async ({ page }) => {
    await search(page, 'GraphRAG');
    await expect(page.locator('#results .result').first()).toBeVisible();
    const all = await page.locator('#results .result').count();
    // The status line still shows the previous count while the filtered search runs, so wait on the
    // result list itself: it is emptied first, then refilled with the narrowed set.
    await page.selectOption('select[name=kind]', 'Talk');
    await expect.poll(() => page.locator('#results .result').count(), { message: 'Talk results after filtering' }).toBeGreaterThan(0);
    const talks = await page.locator('#results .result').count();
    expect(talks).toBeLessThan(all);
    expect(new URL(page.url()).search).toContain('kind=Talk');
  });
});
});
