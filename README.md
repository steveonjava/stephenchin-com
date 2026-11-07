# stephenchin-com

Source for stephenchin.com, built in Astro and published to GitHub Pages by GitHub Actions.

## What is where

- `src/`: the Astro site. Static output, no runtime database, no third-party requests.
- `src/content/works/`: reviewed records. Only `review_status: published` records appear in production.
- `src/content/candidates/`: unreviewed seed records from the research brief. They appear only in the preview build, never in production.
- `src/data/topics.json`, `src/data/sources.json`: topic labels and aliases, and the source ledger.
- `src/data/profile.json`, `src/assets/headshot.jpg`: the owner's biography, word for word, and his portrait with its metadata stripped. `check_catalog.py` fails if the portrait carries EXIF, XMP or IPTC, because Git history is public and permanent.
- `scripts/`: `check_catalog.py` (catalog rules), `check_output.py` (audit of a built folder), `check_lighthouse.mjs` (score budget).
- `scripts/make_backup.py`, `verify_backup.py`, `ruleset_body.py`: make a backup of the three repositories, prove it restores, and rebuild a ruleset from it. `docs/BACKUP-AND-RESTORE.md` is the runbook.
- `ops/`: read-only checks for the domains and the retired steveonjava.com subdomain redirects, the redirect rules and the 22 old URLs they must cover.
- `tests/`: self-tests for the checkers, unit tests for the date and sort helpers, and Playwright tests.

## Two builds

- **Preview** (`SITE_MODE` unset): every page is `noindex,nofollow`, `robots.txt` blocks everything, there is no sitemap and no canonical link. Candidate records are shown with a review panel.
- **Production** (`SITE_MODE=production`): published records only, canonical links, `sitemap-index.xml`, `robots.txt` that allows crawling. `check_output.py` fails the build if any unreviewed record's title or URL appears anywhere in the output, including the search index and the feed.

## Building

Sites are built in GitHub Actions only (`.github/workflows/site.yml`): catalog checks, preview build and audit, production build and audit, then a browser job (Playwright with axe at 390 px and 1280 px, keyboard and no-JavaScript checks, search, Lighthouse). The browser job serves the artifact from the build job and never rebuilds. The `preview` job is the single result to require.

Dependencies are exact versions in `package-lock.json`, installed with `npm ci --ignore-scripts`. Node comes from `.nvmrc`.

## Publishing

`.github/workflows/pages.yml` builds the production site, runs `check_catalog.py` and the production audit, and deploys `dist-production/` on every push to `main`, so a merge is a publish. It also runs on pull requests, where it builds and audits the same artifact and stops before deploying. A manual run from the Actions tab redeploys `main`.

To roll back, revert the offending commit through a pull request; the revert deploys when it merges. The placeholder page that preceded the launch is in the history at the commit before the launch commit. Reverting the launch commit itself brings back the old workflow, which runs only by hand, so start it from the Actions tab afterwards.

## Adding a record

Copy a file in `src/content/candidates/`, keep the schema in `src/content.config.ts`, and run `python3 -I scripts/check_catalog.py`. To publish one, move it to `src/content/works/`, add an approved `summary`, a rights decision and a reviewed role, set `review_status: published`, and open a pull request. See `AGENTS.md` for the rules.

The two historical archives live in [steveonjava-com-archive](https://github.com/steveonjava/steveonjava-com-archive) and [nighthacking-tv-archive](https://github.com/steveonjava/nighthacking-tv-archive).
