#!/usr/bin/env python3
"""Self-tests for scripts/check_catalog.py and scripts/check_output.py.

Each test builds a small fixture tree in a temporary folder, runs a checker on it, and asserts that a
deliberately broken input is reported and a good one is not. Reads and writes files only: no Astro,
no browser, no network.
"""
import gzip
import html
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


catalog = load("check_catalog")
output = load("check_output")

BASE = {
    "title": "A talk", "kind": "talk", "topics": ["java"], "source_ids": ["S01"],
    "url": "https://example.org/a", "year": 2025, "stephen_role": "speaker",
    "review_status": "candidate", "verification_status": "source_page_read",
    "rights_status": "link_only_until_review", "event": None,
    "date": {"value": "2025-07-21", "type": "upload"},
}


def record(**changes):
    r = json.loads(json.dumps(BASE))
    r.update(changes)
    return r


PROFILE = {
    "bio": "Jane Doe is Head of Things at Acme and writes books.",
    "headshot_alt": "Portrait of Jane Doe outdoors",
    "job_title": "Head of Things",
    "employer": "Acme",
}
CLEAN_JPEG = b"\xff\xd8\xff\xd9"


def jpeg_with(marker, payload):
    return b"\xff\xd8" + marker + (len(payload) + 2).to_bytes(2, "big") + payload + b"\xff\xd9"


def write_tree(root, works=None, candidates=None, profile=PROFILE, headshot=CLEAN_JPEG):
    root = Path(root)
    for folder in ("src/content/works", "src/content/candidates", "src/data", "src/assets"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if profile is not None:
        (root / "src/data/profile.json").write_text(json.dumps(profile))
    if headshot is not None:
        (root / "src/assets/headshot.jpg").write_bytes(headshot)
    (root / "src/data/topics.json").write_text(json.dumps([{"id": "java", "label": "Java"}]))
    (root / "src/data/sources.json").write_text(json.dumps([{"id": "S01"}]))
    for rid, r in (works or {}).items():
        (root / "src/content/works" / f"{rid}.json").write_text(json.dumps(r))
    for rid, r in (candidates or {}).items():
        (root / "src/content/candidates" / f"{rid}.json").write_text(json.dumps(r))


def problems(works=None, candidates=None, **tree):
    with tempfile.TemporaryDirectory() as tmp:
        write_tree(tmp, works, candidates, **tree)
        return catalog.check(tmp)[0]


class CatalogChecks(unittest.TestCase):
    def test_good_candidate_passes(self):
        self.assertEqual(problems(candidates={"a-talk": record()}), [])

    def test_good_published_record_passes(self):
        good = record(review_status="published", rights_status="link_only", summary="What it is and why it matters.")
        self.assertEqual(problems(works={"a-talk": good}), [])

    def test_calendar_dates_are_checked(self):
        for bad in ("2025-02-30", "2025-13", "2025-7-1", "July 2025"):
            errs = problems(candidates={"a-talk": record(date={"value": bad, "type": "upload"})})
            self.assertTrue(any("bad date" in e for e in errs), bad)

    def test_a_missing_day_is_never_filled_in(self):
        errs = problems(candidates={"a-talk": record(date={"value": "2025-07", "type": "upload"})})
        self.assertEqual(errs, [])

    def test_year_must_agree_with_the_work_date(self):
        errs = problems(candidates={"a-talk": record(year=2019)})
        self.assertTrue(any("disagrees" in e for e in errs))

    def test_repository_dates_do_not_set_the_year(self):
        r = record(year=None, date=None, dates=[{"value": "2015-03-22", "type": "repository_created"}])
        del r["date"]
        self.assertEqual(problems(candidates={"a-repo": r}), [])
        r2 = record(year=2015, date=None, dates=[{"value": "2020-01-01", "type": "repository_created"}])
        del r2["date"]
        self.assertEqual(problems(candidates={"a-repo": r2}), [])

    def test_null_year_with_a_work_date_is_reported(self):
        errs = problems(candidates={"a-talk": record(year=None)})
        self.assertTrue(any("year is null" in e for e in errs))

    def test_duplicate_urls_and_video_ids(self):
        errs = problems(candidates={"one": record(platform_video_id="abcdefghijk"), "two": record(platform_video_id="abcdefghijk")})
        self.assertTrue(any("same url" in e for e in errs))
        self.assertTrue(any("same platform_video_id" in e for e in errs))

    def test_unknown_topic_source_and_field(self):
        errs = problems(candidates={"a-talk": record(topics=["nope"], source_ids=["S99"], surprise=1)})
        self.assertTrue(any("topic" in e for e in errs))
        self.assertTrue(any("source" in e for e in errs))
        self.assertTrue(any("unknown fields" in e for e in errs))

    def test_markup_in_text_is_reported(self):
        errs = problems(candidates={"a-talk": record(title="Hello <script>x</script>")})
        self.assertTrue(any("markup" in e for e in errs))

    def test_broken_relation_target(self):
        r = record(relations=[{"type": "relatedTo", "target": "ghost", "note": "x"}])
        self.assertTrue(any("does not exist" in e for e in problems(candidates={"a-talk": r})))
        ok = record(relations=[{"type": "relatedTo", "target": ["soj:2371", "https://example.org/x"], "note": "x"}])
        self.assertEqual(problems(candidates={"a-talk": ok}), [])

    def test_a_candidate_cannot_be_live(self):
        for status in ("approved", "published"):
            errs = problems(candidates={"a-talk": record(review_status=status)})
            self.assertTrue(any("cannot be" in e for e in errs), status)
        errs = problems(candidates={"a-talk": record(summary="written")})
        self.assertTrue(any("belong to reviewed records" in e for e in errs))

    def test_published_needs_summary_rights_role_and_verification(self):
        bare = record(review_status="published")
        errs = problems(works={"a-talk": bare})
        self.assertTrue(any("approved summary" in e for e in errs))
        self.assertTrue(any("rights decision" in e for e in errs))
        no_role = record(review_status="published", summary="s", rights_status="link_only", stephen_role=None)
        self.assertTrue(any("reviewed role" in e for e in problems(works={"a-talk": no_role})))
        unverified = record(review_status="published", summary="s", rights_status="link_only", verification_status="search_only")
        self.assertTrue(any("verification_status" in e for e in problems(works={"a-talk": unverified})))

    def test_a_complete_published_featured_record_passes(self):
        good = record(review_status="published", rights_status="link_only", summary="A reviewed summary.", featured_rank=1)
        self.assertEqual(problems(works={"a-talk": good}), [])

    def test_at_most_three_featured_and_ranks_are_unique(self):
        works = {}
        for i in range(4):
            works[f"talk-{i}"] = record(review_status="published", rights_status="link_only", summary="s",
                                        url=f"https://example.org/{i}", featured_rank=i + 1)
        self.assertTrue(any("four" in e or "4 featured" in e for e in problems(works=works)))
        dup = {k: dict(v, featured_rank=1) for k, v in list(works.items())[:2]}
        self.assertTrue(any("featured_rank 1" in e for e in problems(works=dup)))

    def test_same_id_in_both_collections(self):
        errs = problems(works={"x": record()}, candidates={"x": record(url="https://example.org/other")})
        self.assertTrue(any("both works and candidates" in e for e in errs))


class ProfileChecks(unittest.TestCase):
    def test_good_profile_passes(self):
        self.assertEqual(problems(), [])

    def test_missing_profile_and_headshot_are_reported(self):
        self.assertTrue(any("profile.json is missing" in e for e in problems(profile=None)))
        self.assertTrue(any("headshot.jpg is missing" in e for e in problems(headshot=None)))

    def test_bad_fields_are_reported(self):
        self.assertTrue(any("unknown" in e for e in problems(profile=dict(PROFILE, nickname="x"))))
        self.assertTrue(any("markup" in e for e in problems(profile=dict(PROFILE, bio="Jane Doe is Head of Things at Acme <b>now</b>"))))
        self.assertTrue(any("line break" in e for e in problems(profile=dict(PROFILE, bio=PROFILE["bio"] + "\n"))))
        self.assertTrue(any("longer than 150" in e for e in problems(profile=dict(PROFILE, headshot_alt="x" * 151))))
        self.assertTrue(any("non-empty" in e for e in problems(profile=dict(PROFILE, headshot_alt=""))))

    def test_job_title_and_employer_must_come_from_the_bio(self):
        self.assertTrue(any("job_title" in e for e in problems(profile=dict(PROFILE, job_title="Chief Wizard"))))
        self.assertTrue(any("employer" in e for e in problems(profile=dict(PROFILE, employer="Globex"))))

    def test_headshot_metadata_is_reported(self):
        for name, jpeg in (("EXIF", jpeg_with(b"\xff\xe1", b"Exif\x00\x00II*\x00")),
                           ("XMP", jpeg_with(b"\xff\xe1", b"http://ns.adobe.com/xap/1.0/\x00<x/>")),
                           ("IPTC", jpeg_with(b"\xff\xed", b"Photoshop 3.0\x00")),
                           ("comment", jpeg_with(b"\xff\xfe", b"made with a camera"))):
            errs = problems(headshot=jpeg)
            self.assertTrue(any(f"carries {name}" in e for e in errs), name)

    def test_a_colour_profile_alone_is_allowed(self):
        self.assertEqual(problems(headshot=jpeg_with(b"\xff\xe2", b"ICC_PROFILE\x00\x01\x01")), [])


# ---- output audit ---------------------------------------------------------------------------------

PREVIEW_HEAD = '<meta name="robots" content="noindex,nofollow">'


def page(title, body="", head="", canonical=None):
    can = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    return f"<!doctype html><html lang=en><head><title>{title}</title>{head}{can}</head><body><main><h1>{title}</h1>{body}</main></body></html>"


def write_fragment(dist, text):
    folder = dist / "pagefind/fragment"
    folder.mkdir(parents=True, exist_ok=True)
    payload = b"pagefind_dcd" + json.dumps({"url": "/", "content": text, "meta": {"title": "Home"}}).encode("utf8")
    (folder / "en_abc123.pf_fragment").write_bytes(gzip.compress(payload))


def make_dist(root, mode, leak=False, drop_noindex=False, drop_canonical=False, drop_record_page=False,
              leak_in_index=False, no_fragments=False, bio=None, image=None):
    dist = Path(root) / "dist"
    (dist / "pagefind").mkdir(parents=True)
    (dist / "pagefind/pagefind.js").write_text("// index")
    (dist / "pagefind/pagefind-entry.json").write_text(json.dumps({"languages": {"en": {"page_count": 5}}}))
    if not no_fragments:
        write_fragment(dist, (bio or "Stephen Chin") + (" A talk" if leak_in_index else ""))
    if image:
        (dist / "_astro").mkdir()
        (dist / "_astro" / image[0]).write_bytes(image[1])
    rss = '<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>{items}</channel></rss>'
    if mode == "preview":
        head = "" if drop_noindex else PREVIEW_HEAD
        (dist / "index.html").write_text(page("Stephen Chin", '<a href="/work/">w</a>', head))
        (dist / "work").mkdir()
        (dist / "work/index.html").write_text(page("Work", "", head))
        if not drop_record_page:
            (dist / "work/a-talk").mkdir()
            (dist / "work/a-talk/index.html").write_text(page("A talk", "", head))
        (dist / "404.html").write_text(page("Not found", "", head))
        (dist / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
        (dist / "rss.xml").write_text(rss.format(items='<item><title>A talk</title><link>https://stephenchin.com/work/a-talk/</link></item>'))
    else:
        def can(path):
            return None if drop_canonical else f"https://stephenchin.com{path}"
        extra = "<p>A talk https://example.org/a</p>" if leak else ""
        bio_html = f"<p>{html.escape(bio)}</p>" if bio else ""
        (dist / "index.html").write_text(page("Stephen Chin", '<a href="/work/">w</a>' + bio_html + extra, "", can("/")))
        (dist / "work").mkdir()
        (dist / "work/index.html").write_text(page("Work", "", "", can("/work/")))
        (dist / "404.html").write_text(page("Not found", "", '<meta name="robots" content="noindex">'))
        (dist / "robots.txt").write_text("User-agent: *\nAllow: /\n\nSitemap: https://stephenchin.com/sitemap-index.xml\n")
        (dist / "sitemap-index.xml").write_text("<sitemapindex/>")
        (dist / "sitemap-0.xml").write_text('<urlset><url><loc>https://stephenchin.com/</loc></url></urlset>')
        (dist / "rss.xml").write_text(rss.format(items=""))
    return dist


def audit_output(mode, profile=PROFILE, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        # The unreviewed record exists in the source, so in production it must not be in the output.
        write_tree(tmp, {}, {"a-talk": record()}, profile=profile)
        dist = make_dist(tmp, mode, **kw)
        return output.audit(mode, dist, tmp)


class OutputChecks(unittest.TestCase):
    def test_good_preview_passes(self):
        self.assertEqual(audit_output("preview"), [])

    def test_preview_page_without_noindex_is_reported(self):
        self.assertTrue(any("noindex" in e for e in audit_output("preview", drop_noindex=True)))

    def test_preview_missing_a_record_page_is_reported(self):
        self.assertTrue(any("record pages differ" in e for e in audit_output("preview", drop_record_page=True)))

    def test_good_production_passes(self):
        self.assertEqual(audit_output("production"), [])

    def test_production_leak_of_an_unreviewed_record_is_reported(self):
        errs = audit_output("production", leak=True)
        self.assertTrue(any("leaks" in e for e in errs), errs)

    def test_production_page_without_canonical_is_reported(self):
        self.assertTrue(any("canonical" in e for e in audit_output("production", drop_canonical=True)))

    def test_a_hidden_title_in_the_search_index_is_reported(self):
        errs = audit_output("production", leak_in_index=True)
        self.assertTrue(any("leaks" in e for e in errs), errs)

    def test_missing_search_fragments_are_reported(self):
        self.assertTrue(any("no search fragments" in e for e in audit_output("production", no_fragments=True)))

    def test_the_owner_bio_may_name_an_unpublished_work_but_nowhere_else(self):
        named = dict(PROFILE, bio="Jane Doe is Head of Things at Acme and is writing A talk for fun.")
        self.assertEqual(audit_output("production", profile=named, bio=named["bio"]), [])
        errs = audit_output("production", profile=named, bio=named["bio"], leak=True)
        self.assertTrue(any("leaks" in e for e in errs), errs)
        errs = audit_output("production", profile=named, bio=named["bio"], leak_in_index=True)
        self.assertTrue(any("leaks" in e for e in errs), errs)

    def test_photo_metadata_in_the_output_is_reported(self):
        exif_jpeg = jpeg_with(b"\xff\xe1", b"Exif\x00\x00II*\x00")
        errs = audit_output("preview", image=("a.jpg", exif_jpeg))
        self.assertTrue(any("a.jpg" in e and "EXIF" in e for e in errs), errs)
        webp_exif = b"RIFF\x00\x00\x00\x00WEBPVP8 \x04\x00\x00\x00\x00\x00\x00\x00EXIF\x02\x00\x00\x00ab"
        errs = audit_output("preview", image=("a.webp", webp_exif))
        self.assertTrue(any("a.webp" in e and "EXIF" in e for e in errs), errs)

    def test_clean_images_pass(self):
        webp = b"RIFF\x00\x00\x00\x00WEBPVP8 \x04\x00\x00\x00\x00\x00\x00\x00"
        self.assertEqual(audit_output("preview", image=("a.webp", webp)), [])
        self.assertEqual(audit_output("preview", image=("a.jpg", CLEAN_JPEG)), [])

    def test_broken_internal_link_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_tree(tmp, {}, {"a-talk": record()})
            dist = make_dist(tmp, "preview")
            (dist / "index.html").write_text(page("Stephen Chin", '<a href="/nowhere/">x</a>', PREVIEW_HEAD))
            errs = output.audit("preview", dist, tmp)
            self.assertTrue(any("broken link" in e for e in errs))

    def test_external_script_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_tree(tmp, {}, {"a-talk": record()})
            dist = make_dist(tmp, "preview")
            (dist / "index.html").write_text(page("Stephen Chin", '<script src="https://cdn.example/x.js"></script>', PREVIEW_HEAD))
            errs = output.audit("preview", dist, tmp)
            self.assertTrue(any("external resource" in e for e in errs))

    def test_stretched_rss_date_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_tree(tmp, {}, {"a-talk": record()})
            dist = make_dist(tmp, "preview")
            (dist / "rss.xml").write_text('<rss><channel><item><title>A talk</title><link>x</link><pubDate>Wed, 01 Jan 2025 12:30:00 GMT</pubDate></item></channel></rss>')
            self.assertTrue(any("pubDate" in e for e in output.audit("preview", dist, tmp)))


if __name__ == "__main__":
    unittest.main(verbosity=1)
