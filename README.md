# stephenchin-com

Placeholder for stephenchin.com. The full site is to follow.

The repository holds one static page (`index.html`, `404.html`, `style.css`) with no build step, no scripts and no external requests. Both pages carry `noindex,nofollow` until the full site launches.

`scripts/check.py` is the only code. It parses the pages and fails on scripts, inline styles, event handlers, external resources, missing files or a missing robots tag. The `Check` workflow runs it on every pull request and push to `main`.

## Publishing

`.github/workflows/pages.yml` deploys the page with GitHub Actions, but only when started by hand, so a repository whose Pages setting is still off shows no failing runs. The custom domain, DNS and the Pages source belong to the owner and are not set here. Once Pages is set to deploy from GitHub Actions, run the workflow from the Actions tab.

When the full site replaces this page, change the workflow trigger to `push` on `main`.

The two historical archives live in [steveonjava-com-archive](https://github.com/steveonjava/steveonjava-com-archive) and [nighthacking-tv-archive](https://github.com/steveonjava/nighthacking-tv-archive).
