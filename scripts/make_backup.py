#!/usr/bin/env python3
"""Make a verifiable backup of the public stephenchin.com projects. Standard library, git, and optionally gh.

Usage: make_backup.py OUT_DIR [--repos NAME ...] [--base-url URL] [--owner NAME] [--no-api] [--no-dns]

Creates OUT_DIR/stephenchin-backup-YYYYmmddTHHMMSSZ/ holding:
  bundles/NAME.bundle   every ref of each repository, including merged pull request heads (git bundle --all)
  api/NAME/*.json       repository settings, Pages, rulesets, pull requests and issues, as read through gh
  dns/snapshot.json     what public DNS answers for the three domains, read over DNS-over-HTTPS
  MANIFEST.json         what was captured, when, and each repository's tip commit
  SHA256SUMS            a checksum for every other file, in `sha256sum -c` format

Only public data is read and no credential is needed for the bundles or the DNS snapshot. The API snapshot
uses whatever gh login exists and is skipped without one. Nothing is written outside the new folder, and the
script refuses to run if that folder already exists. Settings that need a login to read (secrets) are saved
by name only. A final scan fails the run if any file looks like it holds a token or private key.
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://github.com/steveonjava"
DEFAULT_REPOS = ["stephenchin-com", "steveonjava-com-archive", "nighthacking-tv-archive"]
DOMAINS = ["stephenchin.com", "steveonjava.com", "nighthacking.tv"]
CHALLENGE_LABEL = "_github-pages-challenge-steveonjava"
EXTRA_NAMES = [("javafx.steveonjava.com", "A"), ("flash.steveonjava.com", "A"), ("agile.steveonjava.com", "A")]
APEX_TYPES = ["NS", "A", "AAAA", "MX", "TXT", "CAA"]
TYPE_CODES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28, "CAA": 257}
SECRET_PATTERNS = [
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"(?i)bearer\s+[A-Za-z0-9._~+/-]{24,}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
PR_FIELDS = "number,title,body,state,createdAt,mergedAt,mergeCommit,headRefName,baseRefName,author,url,comments,reviews,labels"
ISSUE_FIELDS = "number,title,body,state,createdAt,closedAt,author,url,comments,labels"
VERSION = 1


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bundle_repo(base_url, name, out, work):
    mirror = work / f"{name}.git"
    run(["git", "clone", "--mirror", "--quiet", f"{base_url}/{name}.git", str(mirror)])
    target = out / "bundles" / f"{name}.bundle"
    run(["git", "bundle", "create", "--quiet", str(target), "--all"], cwd=mirror)
    head = run(["git", "rev-parse", "HEAD"], cwd=mirror).strip()
    branch = run(["git", "symbolic-ref", "--short", "HEAD"], cwd=mirror).strip()
    refs = run(["git", "for-each-ref", "--format=%(refname) %(objectname)"], cwd=mirror).splitlines()
    return {"head": head, "default_branch": branch, "ref_count": len(refs),
            "pull_refs": sum(1 for r in refs if r.startswith("refs/pull/")), "bundle": f"bundles/{name}.bundle"}


def gh_json(args):
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{type(error).__name__}"
    if done.returncode != 0:
        return None, (done.stderr.strip().splitlines() or ["failed"])[-1][:160]
    try:
        return json.loads(done.stdout or "null"), None
    except ValueError:
        return None, "not JSON"


def snapshot_api(owner, name, folder):
    """Returns (files written, {endpoint: error}). Secrets and variables are reduced to their names."""
    folder.mkdir(parents=True, exist_ok=True)
    base = f"repos/{owner}/{name}"
    wanted = {
        "repo": [base],
        "pages": [base + "/pages"],
        "rulesets": [base + "/rulesets"],
        "github-pages-branch-policies": [base + "/environments/github-pages/deployment-branch-policies"],
        "actions-permissions": [base + "/actions/permissions"],
        "actions-workflow-permissions": [base + "/actions/permissions/workflow"],
        "secrets": [base + "/actions/secrets"],
        "variables": [base + "/actions/variables"],
    }
    written, errors = [], {}
    for key, (path,) in wanted.items():
        data, err = gh_json(["api", path])
        if data is None:
            errors[key] = err or "empty answer"
            continue
        if key == "rulesets" and isinstance(data, list):
            full = []
            for item in data:
                one, _ = gh_json(["api", f"{path}/{item['id']}"])
                full.append(one if one else item)
            data = full
        if key in ("secrets", "variables"):
            listed = data.get(key, []) if isinstance(data, dict) else []
            data = sorted(x["name"] for x in listed)
            key = key + "-names-only"
        (folder / f"{key}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf8")
        written.append(f"{key}.json")
    for key, cmd in (("pull-requests", ["pr", "list", "--state", "all", "--limit", "1000", "--json", PR_FIELDS]),
                     ("issues", ["issue", "list", "--state", "all", "--limit", "1000", "--json", ISSUE_FIELDS])):
        data, err = gh_json([*cmd, "-R", f"{owner}/{name}"])
        if data is None:
            errors[key] = err or "empty answer"
            continue
        (folder / f"{key}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf8")
        written.append(f"{key}.json")
    return written, errors


def doh(name, rtype):
    url = f"https://cloudflare-dns.com/dns-query?name={name}&type={rtype}"
    request = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.load(response)
    except Exception as error:  # a transport failure is recorded, never mistaken for an empty record set
        return {"name": name, "type": rtype, "rcode": None, "error": type(error).__name__, "answers": []}
    answers = [{"data": a["data"], "ttl": a["TTL"]} for a in body.get("Answer", []) if a.get("type") == TYPE_CODES[rtype]]
    return {"name": name, "type": rtype, "rcode": body.get("Status"), "answers": sorted(answers, key=lambda a: a["data"])}


def snapshot_dns(domains):
    queries = []
    for d in domains:
        queries += [(d, t) for t in APEX_TYPES]
        queries += [("www." + d, "CNAME"), (f"{CHALLENGE_LABEL}.{d}", "TXT")]
    queries += EXTRA_NAMES
    return [doh(n, t) for n, t in queries]


def scan_for_secrets(folder):
    hits = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix != ".bundle":
            data = path.read_bytes()
            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    hits.append(path.relative_to(folder).as_posix())
                    break
    return hits


def write_sums(folder):
    lines = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            lines.append(f"{sha256(path)}  {path.relative_to(folder).as_posix()}")
    (folder / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf8")
    return len(lines)


def make(out_dir, repos, base_url, owner, use_api, use_dns, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out = Path(out_dir) / f"stephenchin-backup-{stamp}"
    if out.exists():
        raise SystemExit(f"{out} already exists; refusing to overwrite a backup")
    (out / "bundles").mkdir(parents=True)
    manifest = {"format": VERSION, "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "base_url": base_url,
                "git": run(["git", "--version"]).strip(), "repos": {}, "api": {}, "dns": None}
    try:
        with tempfile.TemporaryDirectory(dir=str(Path(out_dir))) as work:
            for name in repos:
                manifest["repos"][name] = bundle_repo(base_url, name, out, Path(work))
        if use_api and shutil.which("gh"):
            for name in repos:
                files, errors = snapshot_api(owner, name, out / "api" / name)
                manifest["api"][name] = {"files": files, "errors": errors}
        else:
            manifest["api"] = "skipped"
        if use_dns:
            (out / "dns").mkdir()
            records = snapshot_dns(DOMAINS)
            (out / "dns" / "snapshot.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf8")
            manifest["dns"] = {"domains": DOMAINS, "queries": len(records), "failed_lookups": sum(1 for r in records if r["rcode"] is None)}
        (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf8")
        hits = scan_for_secrets(out)
        if hits:
            raise SystemExit(f"possible secret in {hits}; backup removed")
        write_sums(out)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise
    return out, manifest


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_dir")
    p.add_argument("--repos", nargs="+", default=DEFAULT_REPOS)
    p.add_argument("--base-url", default=DEFAULT_BASE)
    p.add_argument("--owner", default="steveonjava")
    p.add_argument("--no-api", action="store_true")
    p.add_argument("--no-dns", action="store_true")
    args = p.parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    out, manifest = make(args.out_dir, args.repos, args.base_url, args.owner, not args.no_api, not args.no_dns)
    print(f"wrote {out}")
    for name, info in manifest["repos"].items():
        print(f"  {name}: tip {info['head'][:7]} on {info['default_branch']}, {info['ref_count']} refs ({info['pull_refs']} pull request refs)")
    api = manifest["api"]
    print("  api: skipped" if api == "skipped" else "  api: " + ", ".join(f"{n} {len(v['files'])} files, {len(v['errors'])} unreadable" for n, v in api.items()))
    if manifest["dns"]:
        print(f"  dns: {manifest['dns']['queries']} lookups, {manifest['dns']['failed_lookups']} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
