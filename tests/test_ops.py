#!/usr/bin/env python3
"""Self-tests for ops/verify_dns.py. Pure: no network, no sockets."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("verify_dns", Path(__file__).resolve().parents[1] / "ops" / "verify_dns.py")
verify_dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify_dns)
matches = verify_dns.robots_meta_matches

PLACEHOLDER = '<head><meta name="robots" content="noindex,nofollow"><title>Stephen Chin</title></head>'
PRODUCTION = '<head><meta charset="utf-8"><title>Stephen Chin</title><link rel="canonical" href="https://stephenchin.com/"></head>'
PRODUCTION_404 = '<head><meta name="robots" content="noindex"><title>Page not found</title></head>'


class RobotsMeta(unittest.TestCase):
    def test_none_accepts_a_page_with_no_robots_tag(self):
        self.assertTrue(matches(PRODUCTION, "none"))

    def test_none_rejects_the_placeholder_and_any_other_robots_tag(self):
        self.assertFalse(matches(PLACEHOLDER, "none"))
        self.assertFalse(matches(PRODUCTION_404, "none"))
        self.assertFalse(matches('<meta content="noindex" name=robots>', "none"))
        self.assertFalse(matches('<META NAME="ROBOTS" CONTENT="noindex">', "none"))

    def test_an_exact_value_must_match_exactly(self):
        self.assertTrue(matches(PLACEHOLDER, "noindex,nofollow"))
        self.assertFalse(matches(PRODUCTION, "noindex,nofollow"))
        self.assertFalse(matches(PRODUCTION_404, "noindex,nofollow"))
        self.assertTrue(matches('<meta name="robots" content="index,follow">', "index,follow"))

    def test_the_defaults_describe_the_launched_site(self):
        args = verify_dns.build_parser().parse_args([])
        self.assertEqual((args.domain, args.expect_title, args.expect_robots, args.asset),
                         ("stephenchin.com", "Stephen Chin", "none", "/robots.txt"))

    def test_the_old_placeholder_can_still_be_checked_by_flag(self):
        args = verify_dns.build_parser().parse_args(["--expect-robots", "noindex,nofollow", "--asset", "/style.css"])
        self.assertEqual((args.expect_robots, args.asset), ("noindex,nofollow", "/style.css"))


if __name__ == "__main__":
    unittest.main()
