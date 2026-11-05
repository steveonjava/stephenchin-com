#!/usr/bin/env python3
"""Turn a saved ruleset (from a backup's api/NAME/rulesets.json) into a body GitHub accepts when creating one.

Usage: ruleset_body.py RULESETS_JSON [RULESET_NAME]   (name defaults to protect-main)

Prints the JSON body to stdout. The saved file holds read-only fields (ids, links, timestamps, the current
user's permissions) that the create call rejects, so this keeps only the writable ones. Reads one file and
writes nothing.
"""
import json
import sys

WRITABLE = ("name", "target", "enforcement", "conditions", "bypass_actors", "rules")


def body_for(rulesets, name):
    found = [r for r in rulesets if r.get("name") == name]
    if len(found) != 1:
        raise SystemExit(f"expected exactly one ruleset named {name!r}, found {len(found)}")
    missing = [k for k in WRITABLE if k not in found[0]]
    if missing:
        raise SystemExit(f"saved ruleset lacks {missing}; it was saved from the list call, not the single-ruleset call")
    return {k: found[0][k] for k in WRITABLE}


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf8") as f:
        rulesets = json.load(f)
    json.dump(body_for(rulesets, sys.argv[2] if len(sys.argv) == 3 else "protect-main"), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
