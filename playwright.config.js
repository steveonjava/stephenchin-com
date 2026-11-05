import { defineConfig } from '@playwright/test';

// Serves an already built folder. The browser job never rebuilds the site.
const dir = process.env.SITE_DIR || 'dist-preview';
const port = Number(process.env.PORT || 4173);

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  retries: 0,
  reporter: [['list']],
  outputDir: 'test-results',
  use: { baseURL: `http://127.0.0.1:${port}` },
  webServer: {
    command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory ${dir}`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: false,
    timeout: 30000,
  },
  projects: [
    { name: 'mobile-390', use: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 } },
    { name: 'desktop-1280', use: { viewport: { width: 1280, height: 900 } } },
  ],
});
