#!/usr/bin/env python3
"""Audit a built site folder. Reads files only: no server, no browser, no network.

Usage: check_output.py preview|production DIST [ROOT]

preview:    every page is noindex, robots.txt blocks all, no sitemap, every record has a page.
production: nothing unreviewed is present anywhere in the output, canonical links, sitemap, robots.txt.
Both:       internal links resolve, no external scripts or styles, JSON-LD parses, feed and search index exist.
"""
import gzip
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from html import unescape as html_unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

SITE = "https://stephenchin.com"
NOINDEX_ALL = '<meta name="robots" content="noindex,nofollow">'


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs, self.srcs, self.robots, self.canonical = [], [], [], []
        self.jsonld, self.h1, self.errors = [], 0, []
        self._ld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "link":
            if a.get("rel") == "canonical":
                self.canonical.append(a.get("href"))
            elif a.get("href") and a.get("rel") in ("stylesheet", "modulepreload", "preload"):
                self.srcs.append(a["href"])
        if tag == "meta" and a.get("name") == "robots":
            self.robots.append(a.get("content"))
        if tag == "script":
            if a.get("src"):
                self.srcs.append(a["src"])
            if a.get("type") == "application/ld+json":
                self._ld, self._buf = True, []
        if tag in ("img", "iframe", "embed", "object", "source", "video", "audio"):
            if a.get("src"):
                self.srcs.append(a["src"])
            if tag in ("iframe", "embed", "object"):
                self.errors.append(f"<{tag}> is not allowed")
        if tag == "h1":
            self.h1 += 1
        if tag == "form" and a.get("action"):
            self.errors.append("form with an action")

    def handle_endtag(self, tag):
        if tag == "script" and self._ld:
            self.jsonld.append("".join(self._buf))
            self._ld = False

    def handle_data(self, data):
        if self._ld:
            self._buf.append(data)


def pages(dist):
    return [p for p in sorted(dist.rglob("*.html")) if "pagefind" not in p.relative_to(dist).parts]


def url_of(dist, path):
    rel = path.relative_to(dist).as_posix()
    if rel.endswith("index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def resolves(dist, href, current):
    u = urlparse(href)
    if u.scheme or u.netloc:
        return True
    path = unquote(u.path) or current
    if not path.startswith("/"):
        return True  # relative links are not produced by the templates; fail loudly elsewhere if they appear
    target = dist / path.lstrip("/")
    return target.is_file() or (target.is_dir() and (target / "index.html").is_file())


def load_records(root, include_works_state):
    out = []
    for group in ("candidates", "works"):
        folder = root / "src/content" / group
        for f in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            r = json.loads(f.read_text(encoding="utf8"))
            out.append((f.stem, group, r))
    return out


def sibling(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError(name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def index_texts(dist):
    """Text of every Pagefind fragment. A fragment is gzip, then a 12-byte signature, then JSON holding the
    page's title, url and full text. Returns (list of texts, number of fragment files)."""
    texts, count = [], 0
    for f in sorted((dist / "pagefind").rglob("*.pf_fragment")):
        count += 1
        raw = f.read_bytes()
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
        if raw.startswith(b"pagefind_dcd"):
            raw = raw[len(b"pagefind_dcd"):]
        text = raw.decode("utf8", errors="ignore")
        try:
            parts, stack = [], [json.loads(text)]
            while stack:
                o = stack.pop()
                if isinstance(o, dict):
                    stack.extend(o.values())
                elif isinstance(o, list):
                    stack.extend(o)
                elif isinstance(o, str):
                    parts.append(o)
            text = "\n".join(parts)
        except ValueError:
            pass
        texts.append(text.replace("\u200b", ""))
    return texts, count


def read_bio(root):
    path = Path(root) / "src/data/profile.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf8")).get("bio")


def image_problems(dist, meta):
    errors = []
    for f in sorted(dist.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".webp"):
            found = meta.image_metadata(f.read_bytes())
            if found:
                errors.append(f"{f.relative_to(dist).as_posix()}: image carries {', '.join(found)}")
    return errors


def audit(mode, dist, root):
    dist, root = Path(dist), Path(root)
    errors = []
    if not dist.is_dir():
        return [f"{dist} does not exist"]
    records = load_records(root, mode)
    if mode == "preview":
        shown = [(i, g, r) for i, g, r in records if r["review_status"] != "rejected"]
    else:
        shown = [(i, g, r) for i, g, r in records if g == "works" and r["review_status"] == "published"]
    hidden = [(i, g, r) for i, g, r in records if (i, g, r) not in shown]

    html = pages(dist)
    if not html:
        errors.append("no html pages")
    robots = dist / "robots.txt"
    if not robots.is_file():
        errors.append("robots.txt missing")
        robots_text = ""
    else:
        robots_text = robots.read_text(encoding="utf8")

    if mode == "preview":
        if "Disallow: /" not in robots_text or "Allow:" in robots_text:
            errors.append("preview robots.txt must disallow everything")
        if list(dist.glob("sitemap*.xml")):
            errors.append("preview build must not write a sitemap")
    else:
        if "Disallow:" in robots_text or f"Sitemap: {SITE}/sitemap-index.xml" not in robots_text:
            errors.append("production robots.txt must allow crawling and name sitemap-index.xml")
        if not (dist / "sitemap-index.xml").is_file():
            errors.append("sitemap-index.xml missing")
        for sm in dist.glob("sitemap-*.xml"):
            if sm.name == "sitemap-index.xml":
                continue
            locs = [e.text for e in ET.parse(sm).getroot().iter() if e.tag.endswith("loc")]
            for loc in locs:
                if not loc.startswith(SITE + "/"):
                    errors.append(f"{sm.name}: {loc} is not on {SITE}")
                if loc.endswith("/404/") or loc.endswith("/search/"):
                    errors.append(f"{sm.name}: {loc} should not be listed")

    all_text = ""
    for p in html:
        u = url_of(dist, p)
        text = p.read_text(encoding="utf8")
        all_text += text
        page = Page()
        page.feed(text)
        for e in page.errors:
            errors.append(f"{u}: {e}")
        if page.h1 != 1 and u != "/404.html":
            errors.append(f"{u}: {page.h1} h1 elements")
        if mode == "preview":
            if NOINDEX_ALL not in text:
                errors.append(f"{u}: missing noindex,nofollow")
            if page.canonical:
                errors.append(f"{u}: preview pages must not carry a canonical link")
        else:
            if u == "/404.html":
                if page.robots != ["noindex"]:
                    errors.append(f"{u}: expected robots noindex, got {page.robots}")
            else:
                if page.robots:
                    errors.append(f"{u}: robots meta {page.robots} on a production page")
                want = SITE + u
                if page.canonical != [want]:
                    errors.append(f"{u}: canonical {page.canonical}, expected {[want]}")
        for src in page.srcs:
            if urlparse(src).scheme or src.startswith("//"):
                errors.append(f"{u}: external resource {src}")
            elif not resolves(dist, src, u):
                errors.append(f"{u}: missing resource {src}")
        for href in page.hrefs:
            if href.startswith("#") or href.startswith(("mailto:", "tel:")):
                continue
            if not resolves(dist, href.split("#")[0] or u, u):
                errors.append(f"{u}: broken link {href}")
        for blob in page.jsonld:
            try:
                data = json.loads(blob)
            except ValueError:
                errors.append(f"{u}: JSON-LD does not parse")
                continue
            if data.get("@context") != "https://schema.org":
                errors.append(f"{u}: JSON-LD context")
            if data.get("@type") in ("Article", "Book", "SoftwareSourceCode") and "datePublished" in data:
                if not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", data["datePublished"]):
                    errors.append(f"{u}: datePublished {data['datePublished']!r}")

    work_dirs = sorted(d.name for d in (dist / "work").iterdir() if d.is_dir()) if (dist / "work").is_dir() else []
    want_dirs = sorted(i for i, _, _ in shown)
    if work_dirs != want_dirs:
        errors.append(f"record pages differ: extra {sorted(set(work_dirs) - set(want_dirs))}, missing {sorted(set(want_dirs) - set(work_dirs))}")

    # Nothing hidden may appear anywhere in the output, not even in the search index or the feed.
    fragments, fragment_count = index_texts(dist)
    if fragment_count == 0:
        errors.append("no search fragments found, so the search index cannot be audited")
    scan = html_unescape(all_text)
    if (dist / "rss.xml").is_file():
        scan += html_unescape((dist / "rss.xml").read_text(encoding="utf8"))
    scan += "\n".join(fragments)
    bio = read_bio(root)
    if bio:
        # The owner's own biography may name a work that has no published record yet. Remove exactly that
        # text and nothing else, so the same title anywhere else in the output still fails.
        scan = scan.replace(bio, "")
    errors += image_problems(dist, sibling("check_catalog"))
    for i, g, r in hidden:
        for needle in (r["title"], r["url"]):
            if needle and needle in scan:
                errors.append(f"hidden record {g}/{i} leaks into the output: {needle!r}")
        if i in work_dirs:
            errors.append(f"hidden record {g}/{i} has a page")

    rss = dist / "rss.xml"
    if not rss.is_file():
        errors.append("rss.xml missing")
    else:
        try:
            items = ET.parse(rss).getroot().findall("./channel/item")
        except ET.ParseError:
            items = []
            errors.append("rss.xml does not parse")
        if len(items) != min(30, len(shown)):
            errors.append(f"rss.xml has {len(items)} items, expected {min(30, len(shown))}")
        for it in items:
            if it.find("pubDate") is not None and not re.fullmatch(r"[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} 00:00:00 GMT", it.find("pubDate").text or ""):
                errors.append(f"rss item {it.findtext('link')}: pubDate {it.findtext('pubDate')!r}")
    for need in ("pagefind/pagefind.js", "pagefind/pagefind-entry.json"):
        if not (dist / need).is_file():
            errors.append(f"{need} missing")
    entry = dist / "pagefind/pagefind-entry.json"
    if entry.is_file():
        languages = json.loads(entry.read_text(encoding="utf8")).get("languages", {})
        pages_indexed = sum(v.get("page_count", 0) for v in languages.values())
        if pages_indexed < len(shown):
            errors.append(f"search index has {pages_indexed} pages, fewer than {len(shown)} records")
    return errors


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("preview", "production"):
        print(__doc__)
        return 2
    root = sys.argv[3] if len(sys.argv) > 3 else Path(__file__).resolve().parents[1]
    errors = audit(sys.argv[1], sys.argv[2], root)
    for e in errors:
        print("FAIL", e)
    print(f"{sys.argv[1]} output: {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
