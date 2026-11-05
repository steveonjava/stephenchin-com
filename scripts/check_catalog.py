#!/usr/bin/env python3
"""Validate the catalog files without Astro, a browser or the network.

Usage: check_catalog.py [ROOT]   (ROOT defaults to the repository root)

Checks the reviewed collection (src/content/works) and the unreviewed one (src/content/candidates):
shape, ids, references, dates, and the promotion rules. Exits 1 and lists every problem it finds.
"""
import datetime
import json
import re
import sys
from pathlib import Path

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE = re.compile(r"^\d{4}(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$")
STATUSES = {"candidate", "verified", "approved", "published", "rejected"}
KINDS = {"article", "book", "code", "community", "interview", "project", "talk", "video"}
REL_TYPES = {"isRecordingOf", "presentedAt", "companionCode", "partOf", "relatedTo", "alternateVersion"}
REQUIRED = {"title", "kind", "topics", "source_ids", "url", "year", "stephen_role", "review_status",
            "verification_status", "rights_status", "event"}
OPTIONAL = {"note", "date", "dates", "platform_video_id", "page_title_observed", "license_observed",
            "relations", "audit", "summary", "featured_rank"}
# Date types that describe something other than the work itself.
NOT_THE_WORK = {"repository_created", "repository_last_push", "planned_publication"}
HTML = re.compile(r"<[A-Za-z/!]")
EXTERNAL_REF = re.compile(r"^(soj|nh):\d+$")


def real_date(value):
    if not DATE.match(value):
        return False
    parts = [int(x) for x in value.split("-")]
    try:
        if len(parts) == 3:
            datetime.date(*parts)
    except ValueError:
        return False
    return True


def load(folder):
    out = {}
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            out[path.stem] = json.loads(path.read_text(encoding="utf8"))
    return out


def check(root):
    root = Path(root)
    errors = []
    works = load(root / "src/content/works")
    cands = load(root / "src/content/candidates")
    topics = {t["id"] for t in json.loads((root / "src/data/topics.json").read_text(encoding="utf8"))}
    sources = {s["id"] for s in json.loads((root / "src/data/sources.json").read_text(encoding="utf8"))}
    both = {**cands, **works}

    for name in set(works) & set(cands):
        errors.append(f"{name}: id exists in both works and candidates")

    for where, group in (("works", works), ("candidates", cands)):
        urls, vids, ranks = {}, {}, {}
        for rid, r in group.items():
            at = f"{where}/{rid}"
            if not SLUG.match(rid):
                errors.append(f"{at}: id is not a lowercase slug")
            missing = REQUIRED - set(r)
            unknown = set(r) - REQUIRED - OPTIONAL
            if missing:
                errors.append(f"{at}: missing {sorted(missing)}")
            if unknown:
                errors.append(f"{at}: unknown fields {sorted(unknown)}")
            if missing:
                continue
            if r["kind"] not in KINDS:
                errors.append(f"{at}: kind {r['kind']!r}")
            if r["review_status"] not in STATUSES:
                errors.append(f"{at}: review_status {r['review_status']!r}")
            if not r["url"].startswith("https://"):
                errors.append(f"{at}: url must be https")
            key = re.sub(r"^https?://(www\.)?", "", r["url"].lower().split("#")[0]).rstrip("/")
            if key in urls:
                errors.append(f"{at}: same url as {urls[key]}")
            urls[key] = rid
            if r.get("platform_video_id"):
                if not re.fullmatch(r"[A-Za-z0-9_-]{6,20}|\d+", r["platform_video_id"]):
                    errors.append(f"{at}: platform_video_id format")
                if r["platform_video_id"] in vids:
                    errors.append(f"{at}: same platform_video_id as {vids[r['platform_video_id']]}")
                vids[r["platform_video_id"]] = rid
            for t in r["topics"]:
                if t not in topics:
                    errors.append(f"{at}: topic {t!r} is not in src/data/topics.json")
            for s in r["source_ids"]:
                if s not in sources:
                    errors.append(f"{at}: source {s!r} is not in src/data/sources.json")
            for field in ("title", "note", "event", "page_title_observed", "summary"):
                if isinstance(r.get(field), str) and HTML.search(r[field]):
                    errors.append(f"{at}: {field} contains markup")
            dated = [r["date"]] if r.get("date") else []
            dated += r.get("dates", [])
            for d in dated:
                if not real_date(d.get("value", "")):
                    errors.append(f"{at}: bad date {d.get('value')!r}")
            work_years = {int(d["value"][:4]) for d in dated if d.get("type") not in NOT_THE_WORK and real_date(d["value"])}
            if r["year"] is not None and work_years and r["year"] not in work_years:
                errors.append(f"{at}: year {r['year']} disagrees with its dates {sorted(work_years)}")
            if r["year"] is None and work_years:
                errors.append(f"{at}: year is null but the record has a date for the work")
            for rel in r.get("relations", []):
                if rel.get("type") not in REL_TYPES:
                    errors.append(f"{at}: relation type {rel.get('type')!r}")
                targets = rel["target"] if isinstance(rel["target"], list) else [rel["target"]]
                for t in targets:
                    if not (t in both or EXTERNAL_REF.match(t) or t.startswith("https://")):
                        errors.append(f"{at}: relation target {t!r} does not exist")
            if "featured_rank" in r:
                ranks.setdefault(r["featured_rank"], []).append(rid)

        for rank, ids in ranks.items():
            if len(ids) > 1:
                errors.append(f"{where}: featured_rank {rank} used by {ids}")

    # Promotion rules: nothing unreviewed may be live, and a live record needs everything the brief lists.
    for rid, r in cands.items():
        if r.get("review_status") in {"approved", "published"}:
            errors.append(f"candidates/{rid}: a candidate cannot be {r['review_status']}; move it to works after review")
        if "featured_rank" in r or "summary" in r:
            errors.append(f"candidates/{rid}: summary and featured_rank belong to reviewed records only")
    featured = 0
    for rid, r in works.items():
        if r.get("review_status") != "published":
            continue
        at = f"works/{rid}"
        if not r.get("summary", "").strip():
            errors.append(f"{at}: published without an approved summary")
        if r.get("rights_status") in (None, "", "link_only_until_review"):
            errors.append(f"{at}: published without a rights decision")
        if not r.get("source_ids"):
            errors.append(f"{at}: published without a source")
        if not r.get("stephen_role"):
            errors.append(f"{at}: published without a reviewed role")
        if r.get("verification_status") not in {"verified", "source_page_read"}:
            errors.append(f"{at}: published with verification_status {r.get('verification_status')!r}")
        if "featured_rank" in r:
            featured += 1
    if featured > 3:
        errors.append(f"works: {featured} featured records; the homepage shows three")
    check_profile(root, errors)
    return errors, len(works), len(cands)


def image_metadata(data):
    """Names of the metadata blocks a photograph carries. A portrait committed to a public repository keeps
    its EXIF, XMP and IPTC in Git history forever, so none of them may be present."""
    found = []
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 4 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if marker in (0xDA, 0xD9):
                break
            if 0xD0 <= marker <= 0xD7 or marker == 0x01:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            if length < 2:
                break
            segment = data[i + 4:i + 2 + length]
            if marker == 0xE1 and segment.startswith(b"Exif\0\0"):
                found.append("EXIF")
            elif marker == 0xE1 and b"ns.adobe.com/xap" in segment[:40]:
                found.append("XMP")
            elif marker == 0xED and segment.startswith(b"Photoshop 3.0"):
                found.append("IPTC")
            elif marker == 0xFE:
                found.append("comment")
            i += 2 + length
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        i = 12
        while i + 8 <= len(data):
            fourcc = data[i:i + 4]
            size = int.from_bytes(data[i + 4:i + 8], "little")
            if fourcc == b"EXIF":
                found.append("EXIF")
            elif fourcc == b"XMP ":
                found.append("XMP")
            i += 8 + size + (size & 1)
    return found


PROFILE_FIELDS = {"bio", "headshot_alt", "job_title", "employer"}


def check_profile(root, errors):
    root = Path(root)
    path = root / "src/data/profile.json"
    if not path.is_file():
        errors.append("src/data/profile.json is missing")
        return
    try:
        profile = json.loads(path.read_text(encoding="utf8"))
    except ValueError:
        errors.append("src/data/profile.json does not parse")
        return
    if set(profile) != PROFILE_FIELDS:
        errors.append(f"profile.json fields differ: missing {sorted(PROFILE_FIELDS - set(profile))}, unknown {sorted(set(profile) - PROFILE_FIELDS)}")
    for key in sorted(PROFILE_FIELDS & set(profile)):
        value = profile[key]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"profile.{key}: must be a non-empty string")
        elif HTML.search(value):
            errors.append(f"profile.{key}: markup in text")
        elif value != value.strip() or "\n" in value or "  " in value:
            errors.append(f"profile.{key}: stray whitespace or a line break")
    bio = profile.get("bio") if isinstance(profile.get("bio"), str) else ""
    for key in ("job_title", "employer"):
        value = profile.get(key)
        if isinstance(value, str) and value and value not in bio:
            errors.append(f"profile.{key} {value!r} does not appear in the bio, so the structured data would say something the bio does not")
    alt = profile.get("headshot_alt")
    if isinstance(alt, str) and len(alt) > 150:
        errors.append("profile.headshot_alt is longer than 150 characters")
    image = root / "src/assets/headshot.jpg"
    if not image.is_file():
        errors.append("src/assets/headshot.jpg is missing")
    else:
        found = image_metadata(image.read_bytes())
        if found:
            errors.append(f"src/assets/headshot.jpg carries {', '.join(found)}; strip it before committing, because Git history is public and permanent")


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    errors, nw, nc = check(root)
    for e in errors:
        print("FAIL", e)
    print(f"{nw} reviewed, {nc} candidate records; {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
