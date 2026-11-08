import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readdirSync, readFileSync, mkdirSync } from 'node:fs';

const readFolder = (dir) => readdirSync(dir).filter((f) => f.endsWith('.json')).map((f) => ({ id: f.slice(0, -5), ...JSON.parse(readFileSync(`${dir}/${f}`, 'utf8')) }));
// The preview build shows the reviewed records and the unreviewed candidates together, so the expected counts come from both.
const works = readFolder('src/content/works');
const candidates = [...works, ...readFolder('src/content/candidates')].filter((c) => c.review_status !== 'rejected');
const featuredIds = works.filter((w) => typeof w.featured_rank === 'number').sort((a, b) => a.featured_rank - b.featured_rank).map((w) => w.id);
const profile = JSON.parse(readFileSync('src/data/profile.json', 'utf8'));
const KEY_PAGES = ['/', '/work/', '/talks/', '/topics/', '/topics/javafx/', '/work/talk-crabrag/', '/work/talk-graphrag-definitive-guide/', '/search/', '/404.html'];

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

test.describe('page title and favicon', () => {
  test('home has the approved title without changing another page title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle('Stephen Chin | Author, Speaker and VP of Developer Relations');
    await page.goto('/work/');
    await expect(page).toHaveTitle('Work | Stephen Chin');
  });

  for (const path of ['/', '/work/', '/404.html']) {
    test(`${path}: favicon is same-origin, served and decodable`, async ({ page, request }) => {
      await page.goto(path);
      const icon = page.locator('link[rel="icon"]');
      await expect(icon).toHaveCount(1);
      await expect(icon).toHaveAttribute('href', '/favicon.png');
      await expect(icon).toHaveAttribute('type', 'image/png');
      await expect(icon).toHaveAttribute('sizes', '64x64');
      const response = await request.get('/favicon.png');
      expect(response.status()).toBe(200);
      expect(response.headers()['content-type']).toContain('image/png');
      expect(await response.body()).toEqual(readFileSync('public/favicon.png'));
      const dimensions = await page.evaluate(async () => {
        const image = new Image();
        image.src = document.querySelector('link[rel="icon"]').href;
        await image.decode();
        return [image.naturalWidth, image.naturalHeight];
      });
      expect(dimensions).toEqual([64, 64]);
    });
  }
});

test.describe('home profile', () => {
  test('shows the supplied bio word for word and a portrait that loads', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('.bio')).toHaveText(profile.bio);
    const img = page.locator('img.portrait');
    await expect(img).toBeVisible();
    await expect(img).toHaveAttribute('alt', profile.headshot_alt);
    expect(await img.evaluate((el) => el.naturalWidth), 'portrait decoded').toBeGreaterThan(0);
  });
});

test.describe('social metadata', () => {
  for (const path of ['/', '/work/', '/topics/javafx/', '/work/talk-agentic-graphrag/', '/404.html']) {
    test(`${path}: escaped title and description match the social tags`, async ({ page }) => {
      await page.goto(path);
      const title = await page.title();
      const descriptions = page.locator('meta[name="description"]');
      const description = await descriptions.count() ? await descriptions.getAttribute('content') : title;
      await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', title);
      await expect(page.locator('meta[name="twitter:title"]')).toHaveAttribute('content', title);
      await expect(page.locator('meta[property="og:description"]')).toHaveAttribute('content', description);
      await expect(page.locator('meta[name="twitter:description"]')).toHaveAttribute('content', description);
      await expect(page.locator('meta[property="og:url"]')).toHaveCount(0);
      await expect(page.locator('meta[property="og:image"]')).toHaveAttribute('content', '/social-card.jpg');
      if (path === '/work/talk-agentic-graphrag/') expect(title).toContain("AI's");
      if (path === '/') expect(description).toBe("Explore Stephen Chin's talks, books, writing and projects on AI, graph technology, Java, open source and developer communities.");
    });
  }
  test('the preview card is served locally and decodes at its declared dimensions', async ({ page, request }) => {
    await page.goto('/');
    const response = await request.get('/social-card.jpg');
    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('image/jpeg');
    expect(await response.body()).toEqual(readFileSync('public/social-card.jpg'));
    const dimensions = await page.evaluate(async () => {
      const image = new Image();
      image.src = document.querySelector('meta[property="og:image"]').content;
      await image.decode();
      return [image.naturalWidth, image.naturalHeight];
    });
    expect(dimensions).toEqual([1200, 630]);
    await expect(page.locator('meta[property="og:image:alt"]')).toHaveAttribute('content', /Portrait of Stephen Chin/);
  });
});

test.describe('selected work on the home page', () => {
  test('shows the featured records in rank order, each linking to its own page', async ({ page }) => {
    expect(featuredIds.length, 'the owner chose three').toBe(3);
    await page.goto('/');
    const rows = page.locator('section[aria-labelledby="selected"] .record');
    await expect(rows).toHaveCount(featuredIds.length);
    const hrefs = await rows.locator('h3 a').evaluateAll((links) => links.map((a) => a.getAttribute('href')));
    expect(hrefs).toEqual(featuredIds.map((id) => `/work/${id}/`));
    await expect(page.locator('.review')).toHaveCount(0);
  });
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
