#!/usr/bin/env python3
"""Self-tests for scripts/make_backup.py, scripts/verify_backup.py and scripts/ruleset_body.py.

Builds three small local repositories, backs them up through file:// URLs, and proves the verifier accepts a
good backup and names each deliberately broken one. No network, no gh login, no Astro.
"""
import contextlib
import datetime
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


make_backup = load("make_backup")
verify_backup = load("verify_backup")
ruleset_body = load("ruleset_body")

FILES = {
    "stephenchin-com": {"README.md": "x", "AGENTS.md": "x", "index.html": "x", ".github/workflows/pages.yml": "x"},
    "steveonjava-com-archive": {"README.md": "x", "CNAME": "steveonjava.com", ".github/workflows/pages.yml": "x"},
    "nighthacking-tv-archive": {"README.md": "x", "CNAME": "nighthacking.tv", ".github/workflows/pages.yml": "x"},
}


def git(*args, cwd=None):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "init.defaultBranch=main", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


def make_remotes(root, extra_file=None):
    base = Path(root) / "remote"
    for name, files in FILES.items():
        work = Path(root) / "src" / name
        work.mkdir(parents=True)
        git("init", "--quiet", cwd=work)
        for rel, body in files.items():
            (work / rel).parent.mkdir(parents=True, exist_ok=True)
            (work / rel).write_text(body)
        if extra_file and name == "stephenchin-com":
            (work / extra_file[0]).write_text(extra_file[1])
        git("add", "-A", cwd=work)
        git("commit", "--quiet", "-m", "one", cwd=work)
        git("tag", "v1", cwd=work)
        (work / "later.txt").write_text("later")
        git("add", "-A", cwd=work)
        git("commit", "--quiet", "-m", "two", cwd=work)
        git("checkout", "--quiet", "-b", "feature", cwd=work)
        (work / "feature.txt").write_text("f")
        git("add", "-A", cwd=work)
        git("commit", "--quiet", "-m", "three", cwd=work)
        git("checkout", "--quiet", "main", cwd=work)
        base.mkdir(exist_ok=True)
        git("clone", "--quiet", "--bare", str(work), str(base / f"{name}.git"))
    return f"file://{base}"


def backup(root, base_url):
    out_dir = Path(root) / "backups"
    out_dir.mkdir()
    with contextlib.redirect_stdout(io.StringIO()):
        return make_backup.make(out_dir, list(FILES), base_url, "nobody", use_api=False, use_dns=False)


def verify(folder, work):
    verify_backup.results.clear()
    buf = io.StringIO()
    argv = sys.argv
    sys.argv = ["verify_backup.py", str(folder), str(work)]
    try:
        with contextlib.redirect_stdout(buf):
            code = verify_backup.main()
    finally:
        sys.argv = argv
    return code, buf.getvalue()


class BackupRoundTrip(unittest.TestCase):
    def test_good_backup_verifies_and_restores(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_remotes(tmp)
            out, manifest = backup(tmp, base)
            self.assertEqual(set(manifest["repos"]), set(FILES))
            for info in manifest["repos"].values():
                self.assertEqual(info["default_branch"], "main")
                self.assertGreaterEqual(info["ref_count"], 3)  # main, feature, tag
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 0, text)
            self.assertIn("rebuilt refs equal the saved refs", text)
            self.assertNotIn("FAIL", text)

    def test_every_file_has_a_checksum_and_the_folder_is_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
            self.assertEqual(names, {"MANIFEST.json", "SHA256SUMS", *(f"bundles/{n}.bundle" for n in FILES)})

    def test_a_changed_bundle_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            target = out / "bundles/stephenchin-com.bundle"
            data = bytearray(target.read_bytes())
            data[-20] ^= 0xFF
            target.write_bytes(bytes(data))
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 1)
            self.assertRegex(text, r"FAIL  \d+ checksums match")

    def test_an_added_and_a_deleted_file_are_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            (out / "extra.txt").write_text("x")
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 1)
            self.assertIn("unlisted=['extra.txt']", text)
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            (out / "bundles/nighthacking-tv-archive.bundle").unlink()
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 1)
            self.assertIn("missing=['bundles/nighthacking-tv-archive.bundle']", text)

    def test_a_manifest_tip_that_disagrees_with_the_bundle_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, manifest = backup(tmp, make_remotes(tmp))
            manifest["repos"]["stephenchin-com"]["head"] = "0" * 40
            (out / "MANIFEST.json").write_text(json.dumps(manifest))
            # keep the checksums honest so only the tip comparison can fail
            make_backup.write_sums(out)
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 1)
            self.assertIn("FAIL  [stephenchin-com] default branch tip equals the manifest", text)

    def test_a_missing_required_file_in_the_tip_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_remotes(tmp)
            out, manifest = backup(tmp, base)
            saved = dict(verify_backup.REQUIRED_FILES)
            verify_backup.REQUIRED_FILES["stephenchin-com"] = saved["stephenchin-com"] + ["package-lock.json"]
            try:
                code, text = verify(out, Path(tmp) / "work")
            finally:
                verify_backup.REQUIRED_FILES.update(saved)
            self.assertEqual(code, 1)
            self.assertIn("FAIL  [stephenchin-com] tip contains package-lock.json", text)

    def test_a_path_that_escapes_the_folder_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            with open(out / "SHA256SUMS", "a") as f:
                f.write("0" * 64 + "  ../outside.txt\n")
            code, text = verify(out, Path(tmp) / "work")
            self.assertEqual(code, 1)
            self.assertIn("no checksum path leaves the backup folder", text)
            self.assertRegex(text, r"FAIL  no checksum path leaves")

    def test_the_verifier_refuses_a_used_work_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = backup(tmp, make_remotes(tmp))
            work = Path(tmp) / "work"
            work.mkdir()
            (work / "old").write_text("x")
            code, text = verify(out, work)
            self.assertEqual(code, 2)
            self.assertIn("must be new or empty", text)

    def test_a_backup_is_never_overwritten_and_a_failed_run_leaves_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = make_remotes(tmp)
            out_dir = Path(tmp) / "backups"
            out_dir.mkdir()
            when = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
            with contextlib.redirect_stdout(io.StringIO()):
                make_backup.make(out_dir, list(FILES), base, "nobody", False, False, now=when)
                with self.assertRaises(SystemExit):
                    make_backup.make(out_dir, list(FILES), base, "nobody", False, False, now=when)
                later = datetime.datetime(2026, 1, 2, 3, 4, 6, tzinfo=datetime.timezone.utc)
                with self.assertRaises(subprocess.CalledProcessError):
                    make_backup.make(out_dir, ["no-such-repo"], base, "nobody", False, False, now=later)
            self.assertEqual([p.name for p in out_dir.iterdir()], ["stephenchin-backup-20260102T030405Z"])

    def test_a_token_in_a_snapshot_stops_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "api").mkdir()
            (folder / "api/x.json").write_text('{"note": "ghp_' + "a" * 36 + '"}')
            self.assertEqual(make_backup.scan_for_secrets(folder), ["api/x.json"])
            (folder / "api/x.json").write_text('{"note": "nothing here"}')
            self.assertEqual(make_backup.scan_for_secrets(folder), [])

    def test_a_failed_dns_lookup_is_recorded_not_hidden(self):
        failing = {"name": "x", "type": "A", "rcode": None, "error": "URLError", "answers": []}
        with mock.patch.object(make_backup, "doh", side_effect=lambda name, rtype: dict(failing, name=name, type=rtype)):
            records = make_backup.snapshot_dns(["example.com"])
        self.assertTrue(records and all(r["rcode"] is None for r in records))


class RulesetBody(unittest.TestCase):
    SAVED = [{"id": 1, "name": "protect-main", "target": "branch", "enforcement": "active", "source": "x/y", "source_type": "Repository",
              "created_at": "t", "updated_at": "t", "node_id": "n", "_links": {}, "current_user_can_bypass": "never",
              "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}}, "bypass_actors": [],
              "rules": [{"type": "deletion"}]}]

    def test_keeps_only_writable_fields(self):
        body = ruleset_body.body_for(self.SAVED, "protect-main")
        self.assertEqual(set(body), set(ruleset_body.WRITABLE))
        self.assertNotIn("id", body)

    def test_a_list_call_entry_is_refused(self):
        with self.assertRaises(SystemExit):
            ruleset_body.body_for([{"id": 1, "name": "protect-main", "target": "branch"}], "protect-main")

    def test_unknown_or_duplicate_names_are_refused(self):
        with self.assertRaises(SystemExit):
            ruleset_body.body_for(self.SAVED, "other")
        with self.assertRaises(SystemExit):
            ruleset_body.body_for(self.SAVED + self.SAVED, "protect-main")


if __name__ == "__main__":
    unittest.main(verbosity=1)
