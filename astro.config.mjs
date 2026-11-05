// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// SITE_MODE picks what the build is for. "preview" shows candidate records for review and marks every
// page noindex. "production" builds reviewed records only, with canonical links, a sitemap and robots.txt.
const production = process.env.SITE_MODE === 'production';

export default defineConfig({
  site: 'https://stephenchin.com',
  trailingSlash: 'always',
  compressHTML: true,
  outDir: process.env.OUT_DIR ?? './dist',
  build: { format: 'directory' },
  integrations: production ? [sitemap({ filter: (page) => !page.endsWith('/404/') && !page.endsWith('/search/') })] : [],
});
