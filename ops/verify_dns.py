#!/usr/bin/env python3
"""Read-only check of a GitHub Pages custom domain: DNS records, TLS and HTTP behaviour. Standard library only.

usage: python3 -I verify_stephenchin_dns.py [--dns-only] [--domain stephenchin.com]
           [--expect-title "Stephen Chin"] [--expect-robots none] [--asset /robots.txt]

--expect-robots none means the home page must carry no robots meta tag at all (an indexable page). Any other
value must match the tag's content exactly, for example noindex,nofollow for the old placeholder.

Exit status 0 only if every check passes. Each line is PASS or FAIL with the observed value.

Why it talks to public resolvers and raw sockets instead of curl:
the host resolver may append a search suffix with a wildcard, so a name that does not exist can resolve to an
unrelated address and produce a misleading HTTP answer. This script resolves with DNS-over-HTTPS (Cloudflare and
Google) and connects to the resulting address with the real name for SNI and certificate checks. Certificate
verification is always on. TXT values are never printed.
"""
import argparse
import datetime
import json
import re
import secrets
import socket
import ssl
import sys
import urllib.request

PAGES_A = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
PAGES_AAAA = ["2606:50c0:8000::153", "2606:50c0:8001::153", "2606:50c0:8002::153", "2606:50c0:8003::153"]
WWW_TARGET = "steveonjava.github.io."
CLOUDFLARE_NS = ["magdalena.ns.cloudflare.com.", "wilson.ns.cloudflare.com."]
GITHUB_OWNER = "steveonjava"
RESOLVERS = {"cloudflare": "https://cloudflare-dns.com/dns-query", "google": "https://dns.google/resolve"}
TYPES = {"A": 1, "NS": 2, "CNAME": 5, "MX": 15, "TXT": 16, "AAAA": 28}

results = []


def record(ok, name, detail):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")


def doh(resolver, name, rtype):
    request = urllib.request.Request(f"{RESOLVERS[resolver]}?name={name}&type={rtype}", headers={"accept": "application/dns-json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = json.load(response)
    answers = [a["data"] for a in body.get("Answer", []) if a["type"] == TYPES[rtype]]
    return body.get("Status"), answers


def dns_checks(domain):
    for resolver in RESOLVERS:
        try:
            status, ns = doh(resolver, domain, "NS")
            record(sorted(x.lower() for x in ns) == CLOUDFLARE_NS, f"[{resolver}] NS", f"rcode={status} {sorted(ns)}")
            status, a = doh(resolver, domain, "A")
            record(sorted(a) == PAGES_A, f"[{resolver}] apex A", f"rcode={status} {sorted(a)}")
            status, aaaa = doh(resolver, domain, "AAAA")
            record(sorted(aaaa) == PAGES_AAAA, f"[{resolver}] apex AAAA", f"rcode={status} {sorted(aaaa)}")
            status, cname = doh(resolver, "www." + domain, "CNAME")
            record([x.lower() for x in cname] == [WWW_TARGET], f"[{resolver}] www CNAME", f"rcode={status} {cname}")
            status, txt = doh(resolver, f"_github-pages-challenge-{GITHUB_OWNER}.{domain}", "TXT")
            record(len(txt) >= 1, f"[{resolver}] GitHub verification TXT present", f"rcode={status} records={len(txt)} (values not printed)")
            probe = "wildcard-probe-" + secrets.token_hex(4) + "." + domain
            status, stray = doh(resolver, probe, "A")
            record(status == 3 and not stray, f"[{resolver}] no wildcard record", f"random name {probe.split('.')[0]} -> rcode={status} answers={stray}")
        except Exception as error:  # a transport failure is not an empty zone
            record(False, f"[{resolver}] lookup", f"{type(error).__name__}: {error}")
    status, mx = doh("cloudflare", domain, "MX")
    print(f"INFO  apex MX (not judged): rcode={status} {mx}")
    status, txt = doh("cloudflare", domain, "TXT")
    print(f"INFO  apex TXT records (not judged): {len(txt)}")


def address(name, rtype="A"):
    status, found = doh("cloudflare", name, rtype)
    return found[0] if found else None


def request(host, ip, port, tls, path):
    """One GET over a raw socket to a chosen address. Returns (status, headers, body, certificate or None)."""
    raw = socket.create_connection((ip, port), timeout=15)
    cert = None
    if tls:
        raw = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        cert = raw.getpeercert()
    raw.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: dns-verify\r\nAccept: */*\r\nConnection: close\r\n\r\n".encode())
    data = b""
    while len(data) < 200000:
        chunk = raw.recv(65536)
        if not chunk:
            break
        data += chunk
    raw.close()
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(":")
        headers[key.strip().lower()] = value.strip()
    return int(lines[0].split()[1]), headers, body.decode("utf-8", "replace"), cert


def robots_meta_matches(body, expected):
    """expected == 'none': no robots meta tag at all. Otherwise the tag must carry exactly that content."""
    if expected == "none":
        return re.search(r"<meta[^>]+name=[\"']?robots", body, re.I) is None
    return f'<meta name="robots" content="{expected}">' in body


def http_checks(domain, title, robots, asset):
    ip = address(domain)
    if not ip:
        record(False, "HTTPS", f"{domain} has no A record yet, so there is nothing to connect to")
        return
    try:
        status, headers, body, cert = request(domain, ip, 443, True, "/")
        record(status == 200, f"https://{domain}/ status", f"{status} via {ip}, certificate verified")
        lowered = body.lower()
        record(f"<title>{title.lower()}" in lowered or title.lower() in lowered.split("</title>")[0], "page title", f"expects {title!r}")
        record(robots_meta_matches(body, robots), "robots meta", f"expects {robots}")
        sans = sorted(v for k, v in cert["subjectAltName"] if k == "DNS")
        record(domain in sans and "www." + domain in sans, "certificate covers apex and www", f"SAN={sans}")
        expires = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=datetime.timezone.utc)
        days = (expires - datetime.datetime.now(datetime.timezone.utc)).days
        record(days > 14, "certificate expiry", f"{expires.date()} ({days} days left)")
        status, headers, _, _ = request(domain, ip, 443, True, asset)
        record(status == 200, f"asset {asset}", f"{status} {headers.get('content-type', '')}")
        status, _, body, _ = request(domain, ip, 443, True, "/no-such-page-" + secrets.token_hex(3) + "/")
        record(status == 404, "unknown path returns 404", str(status))
    except Exception as error:
        record(False, f"https://{domain}/", f"{type(error).__name__}: {error}")
    for label, host, port, tls in (("www over HTTPS", "www." + domain, 443, True), ("apex over HTTP (after Enforce HTTPS)", domain, 80, False)):
        try:
            target_ip = address(host) if host.startswith("www.") else ip
            status, headers, _, _ = request(host, target_ip, port, tls, "/")
            record(status in (301, 308) and headers.get("location") == f"https://{domain}/", label, f"{status} -> {headers.get('location')}")
        except Exception as error:
            record(False, label, f"{type(error).__name__}: {error}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domain", default="stephenchin.com")
    parser.add_argument("--dns-only", action="store_true")
    parser.add_argument("--expect-title", default="Stephen Chin")
    parser.add_argument("--expect-robots", default="none")
    parser.add_argument("--asset", default="/robots.txt")
    return parser


def main():
    args = build_parser().parse_args()
    print(f"checked {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M:%SZ} domain={args.domain}")
    dns_checks(args.domain)
    if not args.dns_only:
        http_checks(args.domain, args.expect_title, args.expect_robots, args.asset)
    failed = results.count(False)
    print(f"{len(results) - failed} passed, {failed} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
