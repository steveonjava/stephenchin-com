# Backup and restore runbook

This covers the three public projects: `stephenchin-com`, `steveonjava-com-archive` and `nighthacking-tv-archive`, and the three domains in front of them. Everything here was run on 2026-11-05 unless a section says it was not.

## What is protected, and what is not

A backup made by `scripts/make_backup.py` holds:

- **Every repository ref**, as a Git bundle: branches, tags, and the heads of merged pull requests. This is the source of all three sites.
- **Repository settings read through the GitHub API**: repository, Pages, rulesets (in the form they can be re-created from), Actions permissions, the Pages environment's branch policy, secret and variable *names*, and every pull request and issue with its comments.
- **What public DNS answers** for the three domains, with TTLs.

It does **not** hold:

- **The built websites.** Pages artifacts expire after 3 days. A restore rebuilds the site from source in GitHub Actions. If Actions is unavailable, someone has to run the pinned recipe by hand (see "GitHub is unavailable"). That path has not been exercised.
- **Cloudflare itself.** DNS records are captured as the public sees them, and the redirect rules are kept in `ops/cloudflare-subdomain-redirects.json`. Account settings, API tokens and the zone export are not captured. The homelab agent holds that credential.
- **The registrar account** (Namecheap) and the GitHub account itself.
- **Anything private.** There is none in these repositories, by rule.

**Where copies live today.** One verified backup exists on the researcher host, in `workspace/chronicler-bootstrap/backups/`. The brief asks for a second copy outside the homelab, and that does not exist yet. Until it does, the host is a single point of failure for everything except GitHub itself.

## Make a backup

Needs `git` and `python3`. `gh` is optional: without a login the API snapshot is skipped and the bundles and DNS snapshot are still made.

```
python3 -I scripts/make_backup.py /path/to/backups
```

This creates a new folder `stephenchin-backup-<UTC timestamp>/` and refuses to overwrite one. It writes `bundles/`, `api/`, `dns/`, `MANIFEST.json` and `SHA256SUMS`. A final scan deletes the whole backup if any file looks like it holds a token or a private key. The 2026-11-05 backup is 79 MB, of which 78 MB are the two archives' bundles.

Do not commit a backup. It is large and it is a copy, not a source.

## Verify a backup

```
python3 -I scripts/verify_backup.py /path/to/stephenchin-backup-... /path/to/new-empty-folder --live
```

It checks the checksums (including that no file was added, removed or changed), then restores each repository the way a real restore would: verify the bundle, clone it, compare the tip with the manifest, run `git fsck`, check that the files a rebuild needs are in the tip, and push branches and tags into an empty repository and compare refs. `--live` also compares each saved tip with GitHub now, for information only. The 2026-11-05 backup passes 36 of 36 checks, and the saved tips match the live ones.

`tests/test_backup.py` proves the verifier fails when a bundle byte changes, a file is added or deleted, the manifest disagrees with the bundle, a required file is missing, or a checksum path escapes the folder.

## Restore a deleted or damaged repository

If the repository was deleted less than 90 days ago, GitHub can restore it from Settings, Repositories, Deleted repositories. Try that first. Otherwise:

1. **Create an empty public repository** with the same name under `steveonjava`.
2. **Push the source.** Never use `git push --mirror`: the bundle contains `refs/pull/*`, which GitHub rejects.
   ```
   git clone --mirror BACKUP/bundles/NAME.bundle /tmp/NAME.git
   cd /tmp/NAME.git
   git push https://github.com/steveonjava/NAME.git 'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'
   ```
   Do this **before** step 3, because the ruleset requires pull requests and would refuse the push.
3. **Re-create the ruleset** from the saved one:
   ```
   python3 -I scripts/ruleset_body.py BACKUP/api/NAME/rulesets.json protect-main > body.json
   gh api -X POST repos/steveonjava/NAME/rulesets --input body.json
   ```
   The helper keeps only the writable fields. I checked that its output equals the live ruleset for all three repositories. I have not run the POST against a fresh repository.
4. **Re-create the settings** from `api/NAME/repo.json` and `pages.json`: squash merge only for the two archives (all methods for `stephenchin-com`), Pages source set to GitHub Actions, the `github-pages` environment limited to `main`, and `delete_branch_on_merge` as saved. The owner sets Pages and the custom domain.
5. **Set the custom domain** in the Pages settings (`CNAME` files are ignored for workflow deployments), then enforce HTTPS once the certificate is issued. The `_github-pages-challenge-steveonjava` TXT records belong to the account, not the repository, and must be kept, so verification survives a rebuild.
6. **Deploy.** The archives deploy when `main` changes, or by hand. `stephenchin-com` deploys only by hand (`pages.yml` is `workflow_dispatch`).
7. **Verify** with the commands under "Verify the live sites".

Pull requests and issues are not restored by this. They remain in `api/NAME/pull-requests.json` and `issues.json` as a record.

## A deploy went wrong

Revert through a pull request, then run the Pages workflow again. A revert is a normal reviewed change, so the ruleset still requires a pull request. The `preview` workflow still runs on every pull request, but the ruleset no longer makes it a required check. Do not force-push `main`; the ruleset blocks it.

## DNS is wrong or lost

Compare the live records with `dns/snapshot.json`, then with the expectations below. The homelab agent holds the Cloudflare credential; the researcher has none and must not be given one for this.

- **Nameservers:** `magdalena.ns.cloudflare.com` and `wilson.ns.cloudflare.com` for all three domains (2026-11-05).
- **Apex A:** `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`. **Apex AAAA:** `2606:50c0:8000::153` to `2606:50c0:8003::153`. TTL 300.
- **`www`:** CNAME to `steveonjava.github.io`. TTL 300.
- **Verification:** a TXT at `_github-pages-challenge-steveonjava.<domain>`. Keep it.
- **No wildcard record.** A wildcard hides mistakes, because nonexistent names then resolve.
- **MX, apex TXT, CAA:** none on any of the three domains today. `nighthacking.com` is a different domain and is untouched.
- **Retired subdomains:** `javafx`, `flash` and `agile` under steveonjava.com stay proxied, so Cloudflare can answer them with a redirect.

## The subdomain redirects are lost

`ops/cloudflare-subdomain-redirects.json` holds the Single Redirects rules, and `ops/subdomain-links.tsv` holds the 22 old URLs (a subdomain and a path each) that must redirect. The homelab agent applies the rules. Then run `python3 -I ops/verify_subdomain_redirects.py`; it runs 63 checks over those 22 URLs and must report 63 passed, 0 failed.

## Verify the live sites

All read-only. They resolve over public DNS-over-HTTPS because the lab resolver appends a wildcard suffix.

```
python3 -I ops/verify_dns.py                       # stephenchin.com, the placeholder
python3 -I ops/verify_dns.py --domain steveonjava.com --expect-title "Latest Posts | SteveOnJava" --expect-robots index,follow --asset /assets/archive.css
python3 -I ops/verify_dns.py --domain nighthacking.tv --expect-title "Latest Videos | NightHacking" --expect-robots index,follow --asset /assets/archive.css
python3 -I ops/verify_subdomain_redirects.py
```

All four pass today (21 checks each for the three sites, 63 for the redirects). The expected title changes whenever a home page title changes. `--dns-only` skips the HTTP and certificate checks.

## GitHub is unavailable, or the account is lost

The domains are independent of the host, which is the point of keeping them at the registrar and Cloudflare. A replacement host needs a built folder, the custom domain and a certificate.

1. **Build.** `stephenchin-com`: Node from `.nvmrc`, `npm ci --ignore-scripts`, `npm run build:production`, output in `dist-production/`. The archives: Python 3.13, `pip install -r requirements.txt`, `python scripts/build.py --base-path ""`, output in `_site/`. These are the commands in the workflows. **They have not been run outside GitHub Actions**, and this project builds only there by rule, so treat the first manual run as a test.
2. **Publish the folder** to any static host that serves a directory and issues certificates for a custom domain.
3. **Change DNS** at Cloudflare to the new host. The homelab agent does this. Expect up to the record TTL before it takes effect (300 seconds for A and AAAA).
4. **Do not run two indexable copies.** Point the domain at one host only, and keep a standby `noindex`.

A backup alone is not failover. Nothing in this runbook makes the sites survive an outage without a person acting.

## Registrar and renewals

Read from the public registry (RDAP) on 2026-11-05: `steveonjava.com` expires **2027-01-09**, `stephenchin.com` **2027-02-23**, `nighthacking.tv` **2027-10-08**. All three carry `client transfer prohibited`. Renewals are handled by homelab management. `steveonjava.com` is the nearest, 65 days from the date of writing.

## Restore drill

Before the production launch, and every quarter after (next by 2027-02-05):

1. Make a backup and verify it with `--live`. All checks must pass.
2. Restore the placeholder: clone its bundle into an empty folder, check out the saved tip, run `python3 -I scripts/check.py`.
3. Run `scripts/ruleset_body.py` for each repository and confirm it produces a body.
4. Run the four live-site verifiers above.
5. Compare `dns/snapshot.json` with a fresh snapshot. Investigate any difference.
6. Read the three registry expiry dates and confirm recovery access to the registrar and to Cloudflare.
7. Write the result in `status.md` with the date, and list anything that failed.

What the drill does **not** yet cover is building a site from a restored copy, creating a repository from scratch, and moving a site to a second host. Each needs a scratch repository or a scratch host and the owner's say-so.
