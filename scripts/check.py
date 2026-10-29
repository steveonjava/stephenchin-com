#!/usr/bin/env python3
"""Validate the placeholder pages. Reads files only: no server, no browser, no network."""
from html.parser import HTMLParser
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("index.html", "404.html")
REQUIRED = PAGES + ("style.css",)
CSP = "default-src 'none'; img-src 'self'; style-src 'self'; base-uri 'none'; form-action 'none'"
FORBIDDEN = {"script", "iframe", "object", "embed", "form", "base", "style"}
# Outbound links are allowed only to these hosts, and only as plain anchors.
OUTBOUND = {"https://steveonjava.com/", "https://nighthacking.tv/"}


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.robots = self.csp = self.title = False
        self.stylesheets, self.anchors, self.errors = [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in FORBIDDEN:
            self.errors.append(f"forbidden element <{tag}>")
        for key in attrs:
            if key.startswith("on") or key in {"style", "srcdoc", "srcset"}:
                self.errors.append(f"active attribute {key} on <{tag}>")
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots = attrs.get("content") == "noindex,nofollow"
        if tag == "meta" and (attrs.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp = attrs.get("content") == CSP
        if tag == "link":
            if attrs.get("rel") == "stylesheet":
                self.stylesheets.append(attrs.get("href"))
            else:
                self.errors.append("unexpected <link>")
        if tag == "a":
            self.anchors.append(attrs.get("href"))
        if tag in {"img", "source", "video", "audio", "track"}:
            self.errors.append(f"unexpected media element <{tag}>")
        if tag == "title":
            self.title = True


def main():
    errors = []
    for name in REQUIRED:
        path = ROOT / name
        if not path.is_file() or path.is_symlink():
            errors.append(f"{name}: missing or not a regular file")
    for name in PAGES:
        path = ROOT / name
        if not path.is_file():
            continue
        page = Page()
        page.feed(path.read_text(encoding="utf-8"))
        errors += [f"{name}: {message}" for message in page.errors]
        if not page.robots:
            errors.append(f"{name}: robots meta must be noindex,nofollow")
        if not page.csp:
            errors.append(f"{name}: missing or unexpected Content-Security-Policy")
        if not page.title:
            errors.append(f"{name}: missing <title>")
        if page.stylesheets not in (["style.css"], ["/style.css"]):
            errors.append(f"{name}: stylesheet must be the local style.css, found {page.stylesheets}")
        for href in page.anchors:
            if href is None or not (href in OUTBOUND or href == "/" or href == "./"):
                errors.append(f"{name}: anchor {href!r} is not on the allow list")
    css = ROOT / "style.css"
    if css.is_file() and re.search(r"url\s*\(|@import|expression\s*\(", css.read_text(encoding="utf-8"), re.I):
        errors.append("style.css: external resource or active expression")
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_symlink():
            errors.append(f"{path.relative_to(ROOT)}: symlink")
    if errors:
        print("\n".join(errors))
        return 1
    print(f"ok: {len(PAGES)} pages checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
