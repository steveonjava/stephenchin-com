# Rules for anyone changing this repository

## Authority

- Open a pull request for every change. `main` is protected. Do not push to it.
- Do not touch DNS, Pages settings, the custom domain, or approval settings. The owner and the homelab agent hold those.
- Do not build the site on a workstation. CI builds it.
- Do not add a runtime service, a database, an analytics script, a font or image from another origin, or an embedded player that loads before a click.

## Content

- Every record needs a source URL, a role, a date with explicit precision (year, month or day) or no date, and a rights decision before it is published.
- Never write a missing month or day as `01`. A repository's creation date is not the date of the work.
- Seeds are candidates. A page that was fetched does not prove a video plays, a rights holder agreed, or that Stephen wrote what he is credited with.
- Write summaries in the owner's voice only from his own words. Do not invent a quote, a date, a provider id, or a first-person claim.
- Public professional sources only. No private messages, family details, internal planning, or unpublished book text.
- Do not place photographs of private individuals.

## Promotion

A record moves from `src/content/candidates/` to `src/content/works/` only with the owner's approval in the pull request. `check_catalog.py` fails a candidate that claims to be approved or published, and a published record without a summary, rights decision, role, or verification.

## Accessibility

Target WCAG 2.2 AA. Keep ordinary browsing usable without JavaScript. Reserve scripts for filters and search. Respect `prefers-reduced-motion`.

## Commit and PR text

Caveats, open questions and evidence go in the commit message and pull request body. Reader-facing pages carry only what is true and approved.
