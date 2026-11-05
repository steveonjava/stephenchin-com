#!/usr/bin/env python3
"""Read-only check of the retired steveonjava.com category-subdomain redirects.

Usage: python3 -I verify_subdomain_redirects.py [subdomain-links.tsv]

Resolves names over public DoH (the lab host resolver appends a wildcard suffix,
so it is never used), connects to the resolved address with SNI and a Host header,
and never follows a redirect, so each hop is judged on its own. Prints no secrets.
Exit status 0 only when every check passes.
"""
import http.client
import json
import socket
import ssl
import sys
import urllib.request
from pathlib import Path

APEX = "steveonjava.com"
CATS = {"javafx.steveonjava.com": "javafx", "flash.steveonjava.com": "flash", "agile.steveonjava.com": "agile"}
GH_PAGES = {"185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"}
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (" :: " + detail if detail else ""))


def doh(kind, name, typ="A"):
    if kind == "cf":
        url = "https://cloudflare-dns.com/dns-query?name=%s&type=%s" % (name, typ)
        hdr = {"accept": "application/dns-json"}
    else:
        url = "https://dns.google/resolve?name=%s&type=%s" % (name, typ)
        hdr = {}
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=20))
    except Exception as exc:  # network failure is a failed check, not a crash
        return None, [], type(exc).__name__
    return d.get("Status"), sorted(a["data"] for a in d.get("Answer", []) if a["type"] == 1), ""


def fetch(host, ip, path, tls):
    """One request, no redirect following. Returns (status, location) or (None, error)."""
    try:
        if tls:
            ctx = ssl.create_default_context()
            conn = http.client.HTTPSConnection(host, 443, timeout=20, context=ctx)
            conn.sock = ctx.wrap_socket(socket.create_connection((ip, 443), timeout=20), server_hostname=host)
        else:
            conn = http.client.HTTPConnection(host, 80, timeout=20)
            conn.sock = socket.create_connection((ip, 80), timeout=20)
        conn.request("GET", path, headers={"Host": host, "User-Agent": "redirect-verifier/1", "Accept-Encoding": "identity"})
        r = conn.getresponse()
        r.read(2048)
        out = (r.status, r.getheader("Location"))
        conn.close()
        return out
    except Exception as exc:
        return None, type(exc).__name__ + ": " + str(exc)[:80]


def expect_redirect(label, host, ip, path, tls, want):
    status, loc = fetch(host, ip, path, tls)
    check(label, status == 301 and loc == want, "got %s %s, want 301 %s" % (status, loc, want))


def expect_redirect_any(label, host, ip, path, tls, wants):
    status, loc = fetch(host, ip, path, tls)
    check(label, status == 301 and loc in wants, "got %s %s, want 301 and one of %s" % (status, loc, wants))


def main():
    tsv = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("subdomain-links.tsv")
    pairs = [tuple(line.split("\t")) for line in tsv.read_text(encoding="utf8").splitlines() if line.strip()]
    # Roots are covered by the dedicated category checks (a root goes to its category page, not the apex root),
    # so only deep paths belong in the pass-through loop and in the query-string and port-80 deep-path tests.
    pairs = [p for p in pairs if p[1] != "/"]

    # Controls first: they prove the harness itself, using records that already work.
    www = doh("cf", "www." + APEX)[1]
    apex = doh("cf", APEX)[1]
    check("control: apex resolves to GitHub Pages", bool(apex) and set(apex) <= GH_PAGES, str(apex))
    if apex:
        status, _ = fetch(APEX, apex[0], "/category/javafx/", True)
        check("control: apex category page is 200", status == 200, str(status))
        status, loc = fetch("www." + APEX, apex[0], "/category/javafx/?a=1", True)
        check("control: www 301 to apex keeps path and query", status == 301 and loc == "https://%s/category/javafx/?a=1" % APEX, "%s %s" % (status, loc))
        # Exercise expect_redirect itself on a redirect that already exists, so a PASS below means the harness works.
        before = len(results)
        expect_redirect("control: expect_redirect on the existing www 301", "www." + APEX, apex[0], "/x/", True, "https://%s/x/" % APEX)
        if results[before:] != [True]:
            print("harness control failed: results below cannot be trusted")

    # DNS: both resolvers agree, hosts exist, nothing points at GitHub Pages or the placeholder origin.
    ips = {}
    for host in CATS:
        cf, g = doh("cf", host), doh("g", host)
        ok = cf[0] == 0 and g[0] == 0 and cf[1] and g[1]
        check("dns %s resolves on Cloudflare and Google DoH" % host, ok, "cf rcode=%s %s | google rcode=%s %s" % (cf[0], cf[1][:2], g[0], g[1][:2]))
        if cf[1]:
            ips[host] = cf[1][0]
            check("dns %s is proxied (not a Pages address, not the 192.0.2.1 placeholder)" % host, not (set(cf[1]) & (GH_PAGES | {"192.0.2.1"})), str(cf[1][:2]))
    status, ips_rand, _ = doh("cf", "zz-probe-%d.%s" % (abs(hash(tsv.name)) % 100000, APEX))
    check("no wildcard: a never-created name is NXDOMAIN", status == 3, "rcode=%s" % status)

    targets = set()
    for host, cat in CATS.items():
        ip = ips.get(host)
        if not ip:
            check("redirect checks for %s (needs an address)" % host, False, "no A record yet")
            continue
        want_root = "https://%s/category/%s/" % (APEX, cat)
        targets.add(want_root)
        expect_redirect("https %s / -> category" % host, host, ip, "/", True, want_root)
        # Port 80 may legitimately take one same-host https hop first (Always Use HTTPS); report which happened.
        expect_redirect_any("http %s / -> category (direct or via https)" % host, host, ip, "/", False, [want_root, "https://%s/" % host])
        # The archive has no feeds. Feed URLs ride the pass-through and land on an honest 404 at the apex.
        expect_redirect("https %s /feed/ passes through to the apex" % host, host, ip, "/feed/", True, "https://%s/feed/" % APEX)
        for h, path in pairs:
            if h == host:
                want = "https://%s%s" % (APEX, path)
                targets.add(want)
                expect_redirect("https %s%s" % (h, path), h, ip, path, True, want)
    if "javafx.steveonjava.com" in ips and pairs:
        h, path = next(p for p in pairs if p[0] == "javafx.steveonjava.com")
        expect_redirect("query string kept on %s%s?utm=x" % (h, path), h, ips[h], path + "?utm=x", True, "https://%s%s?utm=x" % (APEX, path))
        expect_redirect_any("http (port 80) deep path (direct or via https)", h, ips[h], path, False, ["https://%s%s" % (APEX, path), "https://%s%s" % (h, path)])

    # One hop only: every target must answer 200 directly on the apex.
    if apex:
        for t in sorted(targets):
            status, loc = fetch(APEX, apex[0], t[len("https://" + APEX):], True)
            check("target is a final 200 (no chain) %s" % t[len("https://"):], status == 200, "%s %s" % (status, loc or ""))

    passed, failed = sum(results), len(results) - sum(results)
    print("\n%d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
