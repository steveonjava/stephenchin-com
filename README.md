# stephenchin-com

Source for stephenchin.com. Today the published site is a single placeholder page. The full site is built here in Astro and is not deployed yet.

## What is where

- `index.html`, `404.html`, `style.css`: the published placeholder. `pages.yml` deploys only these three files, by hand.
- `src/`: the Astro site. Static output, no runtime database, no third-party requests.
- `src/content/works/`: reviewed records. Only `review_status: published` records appear in production.
- `src/content/candidates/`: unreviewed seed records from the research brief. They appear only in the preview build, never in production.
- `src/data/topics.json`, `src/data/sources.json`: topic labels and aliases, and the source ledger.
- `scripts/`: `check_catalog.py` (catalog rules), `check_output.py` (audit of a built folder), `check_lighthouse.mjs` (score budget), `check.py` (placeholder pages).
- `tests/`: self-tests for the checkers, unit tests for the date and sort helpers, and Playwright tests.

## Two builds

- **Preview** (`SITE_MODE` unset): every page is `noindex,nofollow`, `robots.txt` blocks everything, there is no sitemap and no canonical link. Candidate records are shown with a review panel.
- **Production** (`SITE_MODE=production`): published records only, canonical links, `sitemap-index.xml`, `robots.txt` that allows crawling. `check_output.py` fails the build if any unreviewed record's title or URL appears anywhere in the output, including the search index and the feed.

## Building

Sites are built in GitHub Actions only (`.github/workflows/site.yml`): catalog checks, preview build and audit, production build and audit, then a browser job (Playwright with axe at 390 px and 1280 px, keyboard and no-JavaScript checks, search, Lighthouse). The browser job serves the artifact from the build job and never rebuilds. The `preview` job is the single result to require.

Dependencies are exact versions in `package-lock.json`, installed with `npm ci --ignore-scripts`. Node comes from `.nvmrc`.

## Publishing

Not wired yet. `pages.yml` still deploys the placeholder and runs only when started by hand. To launch the full site, a reviewed pull request will change that workflow to build `dist-production` and deploy on push to `main`, and will remove the placeholder files. Until then the preview artifact is the only way to see the site.

To roll back after launch, revert the launch commit on `main` and the placeholder returns on the next deploy.

## Adding a record

Copy a file in `src/content/candidates/`, keep the schema in `src/content.config.ts`, and run `python3 -I scripts/check_catalog.py`. To publish one, move it to `src/content/works/`, add an approved `summary`, a rights decision and a reviewed role, set `review_status: published`, and open a pull request. See `AGENTS.md` for the rules.

The two historical archives live in [steveonjava-com-archive](https://github.com/steveonjava/steveonjava-com-archive) and [nighthacking-tv-archive](https://github.com/steveonjava/nighthacking-tv-archive).
