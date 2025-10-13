#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import requests
import json
from requests.auth import HTTPBasicAuth
import sys


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Add a review label (for example, Code-Review +1) to a Gerrit "
            "change and its related changes"
        )
    )
    p.add_argument(
        "changes",
        nargs="+",
        help=(
            "One or more Change-Ids (I...) or numeric change\n"
            "numbers (e.g. 12345 6197799)"
        ),
    )
    p.add_argument(
        "--url",
        default="https://gerrit.pt.mioffice.cn/",
        help="Gerrit base URL, e.g. https://gerrit.example.com",
    )
    p.add_argument(
        "--user",
        "-u",
        help="Gerrit username",
    )
    p.add_argument(
        "--password",
        "-p",
        help="Gerrit http password, see gerrit settings/#HTTPCredentials page",
    )
    p.add_argument(
        "--label",
        default="Code-Review",
        help="Label name (default: Code-Review)",
    )
    p.add_argument(
        "--value",
        type=int,
        default=1,
        help="Label value (default: 1)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not post changes, only print what would be done",
    )
    p.add_argument(
        "--related",
        action="store_true",
        help="Fetch related changes",
    )
    p.add_argument("--message", default="", help="Review message")
    return p.parse_args()


def gerrit_get(session, base_url, path, params=None):
    url = base_url.rstrip("/") + path
    r = session.get(url, params=params, timeout=30)
    r.raise_for_status()
    # Gerrit prepends )]}' to JSON responses; strip it before parsing
    text = r.text
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    # return parsed JSON using our cleaned text (do not rely on r.json() which
    # would see the original response body)
    if not text:
        return {}
    return json.loads(text)


def gerrit_post(session, base_url, path, payload):
    url = base_url.rstrip("/") + path
    r = session.post(url, json=payload, timeout=30)
    r.raise_for_status()
    text = r.text
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1]
    if not text:
        return {}
    return json.loads(text)


def fetch_related_changes(session, base_url, change_id):
    try:
        path = f"/a/changes/{change_id}/revisions/current/related"
        data = gerrit_get(session, base_url, path)
    except requests.HTTPError as e:
        msg = f"⚠️  Failed to fetch related changes for {change_id}: {e}"
        print(msg, file=sys.stderr)
        return []

    changes = data.get("changes", [])
    res = [str(c.get("_change_number")) for c in changes]

    # Ensure at least the original change is present
    if not res:
        res = [change_id]
    return res


def add_review_to_change(
    session, base_url, change_id, label, value, message="", dry_run=False
):
    path = f"/a/changes/{change_id}/revisions/current/review"
    payload = {"labels": {label: value}, "message": message}
    if dry_run:
        msg = (
            f"🟡 [Dry-run] Would POST {label}={value} to {change_id} -> "
            f"POST {path} with payload: {payload}"
        )
        print(msg)
        return
    try:
        resp = gerrit_post(session, base_url, path, payload)
        print(f"✅ Posted {label}={value} to {change_id}")
        return resp
    except requests.HTTPError as e:
        print(f"❌ Failed to post review to {change_id}: {e}", file=sys.stderr)


if __name__ == "__main__":
    args = parse_args()
    session = requests.Session()
    session.auth = HTTPBasicAuth(args.user, args.password)

    if args.related:
        all_changes_set = set()
        for change in args.changes:
            print(f"🔍 Fetching related changes for {change} ...")
            related = fetch_related_changes(session, args.url, change)
            all_changes_set.update(related)
        all_changes = sorted(all_changes_set)
    else:
        all_changes = args.changes

    print(f"Found {len(all_changes)} change(s):")
    for c in all_changes:
        print("  -", c)
    print()

    for c in all_changes:
        add_review_to_change(
            session, args.url, c, args.label, args.value, dry_run=args.dry_run
        )
