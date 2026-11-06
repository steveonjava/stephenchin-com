#!/usr/bin/env python3
"""Verify a backup made by make_backup.py, and prove it can be restored. Standard library and git only.

Usage: verify_backup.py BACKUP_DIR WORK_DIR [--live]

WORK_DIR must be new or empty. The script clones every bundle into it, then rebuilds each repository the way
a restore would, by pushing branches and tags (never pull request refs) into a fresh bare repository, and
compares the result with the manifest.

Checks, in order:
  1. SHA256SUMS lists every file, every checksum matches, and no listed path leaves the backup folder.
  2. MANIFEST.json parses and has the expected format.
  3. Each bundle passes `git bundle verify`, clones, and its tip equals the tip the manifest recorded.
  4. The restored repository passes `git fsck` and contains the files a rebuild needs.
  5. The branch and tag refs survive a push into an empty bare repository.
  6. The DNS snapshot parses and records no failed lookups. The API snapshot is listed, never judged.
  --live  also compares each saved tip with the tip on GitHub now (information only, never a failure).

Nothing inside the backup is executed. Git hooks are disabled for every command. Exit status 0 only if every
check passes.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

results = []
REQUIRED_FILES = {
    "stephenchin-com": ["README.md", "AGENTS.md", "package.json", ".github/workflows/pages.yml"],
    "steveonjava-com-archive": ["README.md", "CNAME", ".github/workflows/pages.yml"],
    "nighthacking-tv-archive": ["README.md", "CNAME", ".github/workflows/pages.yml"],
}
GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=always"]


def check(ok, name, detail=""):
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name + (f": {detail}" if detail else ""))
    return bool(ok)


def git(*args, cwd=None):
    done = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sums(root):
    sums = root / "SHA256SUMS"
    if not check(sums.is_file(), "SHA256SUMS present"):
        return
    listed = {}
    bad_format = 0
    for line in sums.read_text(encoding="utf8").splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        if len(digest) != 64 or not rel:
            bad_format += 1
            continue
        listed[rel] = digest
    check(bad_format == 0, "SHA256SUMS lines well formed", f"{bad_format} malformed")
    escaping = [r for r in listed if r.startswith("/") or ".." in Path(r).parts]
    check(not escaping, "no checksum path leaves the backup folder", ", ".join(escaping))
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
    check(on_disk == set(listed), "every file is listed and every listed file exists",
          f"unlisted={sorted(on_disk - set(listed))} missing={sorted(set(listed) - on_disk)}")
    mismatched = [r for r, d in listed.items() if r in on_disk and r not in escaping and sha256(root / r) != d]
    check(not mismatched, f"{len(listed)} checksums match", f"changed: {mismatched}")


def restore_check(name, info, root, work):
    bundle = root / info["bundle"]
    code, _, err = git("bundle", "verify", str(bundle))
    if not check(code == 0, f"[{name}] bundle verifies", "" if code == 0 else (err.splitlines() or ["failed"])[-1]):
        return
    clone = work / "clones" / name
    code, _, err = git("clone", "--quiet", "--mirror", str(bundle), str(clone))
    if not check(code == 0, f"[{name}] bundle clones", "" if code == 0 else err[:160]):
        return
    code, head, _ = git("rev-parse", f"refs/heads/{info['default_branch']}", cwd=clone)
    check(code == 0 and head == info["head"], f"[{name}] default branch tip equals the manifest",
          f"{head[:7]} vs {info['head'][:7]}")
    code, _, err = git("fsck", "--no-dangling", cwd=clone)
    check(code == 0, f"[{name}] git fsck is clean", "" if code == 0 else (err.splitlines() or ["failed"])[-1])
    for rel in REQUIRED_FILES.get(name, []):
        code, _, _ = git("cat-file", "-e", f"{info['head']}:{rel}", cwd=clone)
        check(code == 0, f"[{name}] tip contains {rel}")
    rebuilt = work / "rebuilt" / f"{name}.git"
    rebuilt.parent.mkdir(parents=True, exist_ok=True)
    git("init", "--quiet", "--bare", str(rebuilt))
    code, _, err = git("push", "--quiet", str(rebuilt), "refs/heads/*:refs/heads/*", "refs/tags/*:refs/tags/*", cwd=clone)
    check(code == 0, f"[{name}] branches and tags push into an empty repository", "" if code == 0 else err[:160])

    def refs(repo, prefixes):
        _, out, _ = git("for-each-ref", "--format=%(refname) %(objectname)", cwd=repo)
        return sorted(line for line in out.splitlines() if line.split()[0].startswith(prefixes))

    wanted = refs(clone, ("refs/heads/", "refs/tags/"))
    check(wanted == refs(rebuilt, ("refs/heads/", "refs/tags/")) and len(wanted) > 0,
          f"[{name}] rebuilt refs equal the saved refs", f"{len(wanted)} refs")


def live_compare(name, info, base_url):
    code, out, err = git("ls-remote", f"{base_url}/{name}.git", f"refs/heads/{info['default_branch']}")
    if code != 0 or not out:
        print(f"INFO  [{name}] live tip unreadable: {err[:100]}")
        return
    live = out.split()[0]
    state = "same as the backup" if live == info["head"] else f"differs: live {live[:7]}, backup {info['head'][:7]}"
    print(f"INFO  [{name}] live tip {state}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    live = "--live" in sys.argv
    if len(args) != 2:
        print(__doc__)
        return 2
    root, work = Path(args[0]), Path(args[1])
    if not root.is_dir():
        print(f"{root} is not a folder")
        return 2
    if work.exists() and any(work.iterdir()):
        print(f"{work} must be new or empty")
        return 2
    work.mkdir(parents=True, exist_ok=True)

    check_sums(root)
    manifest_path = root / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        check(False, "MANIFEST.json parses")
        manifest = None
    if manifest is not None:
        check(manifest.get("format") == 1 and manifest.get("repos"), "manifest format and repositories", f"created {manifest.get('created_utc')}")
        for name, info in sorted((manifest.get("repos") or {}).items()):
            try:
                restore_check(name, info, root, work)
            except (KeyError, OSError) as error:
                check(False, f"[{name}] restore", f"{type(error).__name__}: {error}")
            if live:
                live_compare(name, info, manifest.get("base_url", ""))
        if manifest.get("dns"):
            snap = root / "dns" / "snapshot.json"
            try:
                records = json.loads(snap.read_text(encoding="utf8"))
                check(isinstance(records, list) and records, "DNS snapshot parses", f"{len(records)} lookups")
                check(manifest["dns"]["failed_lookups"] == 0 and all(r.get("rcode") is not None for r in records),
                      "DNS snapshot has no failed lookups")
            except (OSError, ValueError):
                check(False, "DNS snapshot parses")
        else:
            print("INFO  no DNS snapshot in this backup")
        api = manifest.get("api")
        if isinstance(api, dict):
            for name, info in sorted(api.items()):
                print(f"INFO  [{name}] API snapshot: {len(info['files'])} files, unreadable: {sorted(info['errors']) or 'none'}")
        else:
            print("INFO  no API snapshot in this backup")
    failed = results.count(False)
    print(f"{len(results) - failed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
