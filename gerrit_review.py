#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
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
        nargs="*",
        help=(
            "One or more Change-Ids (I...) or numeric change\n"
            "numbers (e.g. 12345 6197799). Not required if --topic is used."
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
        help="Gerrit username (or set GERRIT_USER env var)",
    )
    p.add_argument(
        "--password",
        "-p",
        help=(
            "Gerrit http password (or set GERRIT_PASSWORD env var), "
            "see gerrit settings/#HTTPCredentials page"
        ),
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
        "--topic",
        "-t",
        help="Fetch all changes with the specified topic name",
    )
    p.add_argument(
        "--related",
        action="store_true",
        help="Fetch related changes (dependency chain) for each change",
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


def fetch_changes_by_topic(session, base_url, topic):
    """
    Fetch all changes with the specified topic name.
    Returns a list of change numbers (as strings).
    """
    topic_changes = []

    try:
        path = "/a/changes/"
        params = {"q": f"topic:{topic}"}
        topic_results = gerrit_get(session, base_url, path, params=params)
        for c in topic_results:
            topic_changes.append(str(c.get("_number")))
    except requests.HTTPError as e:
        msg = f"⚠️  Failed to fetch changes with topic '{topic}': {e}"
        print(msg, file=sys.stderr)

    return topic_changes


def fetch_related_changes(session, base_url, change_id):
    """
    Fetch related changes (dependency chain) for a given change ID.
    Returns a list of change numbers (as strings).
    """
    all_related = set()

    # Fetch revision-related changes
    try:
        path = f"/a/changes/{change_id}/revisions/current/related"
        data = gerrit_get(session, base_url, path)
        changes = data.get("changes", [])
        for c in changes:
            all_related.add(str(c.get("_change_number")))
    except requests.HTTPError as e:
        msg = f"⚠️  Failed to fetch related changes for {change_id}: {e}"
        print(msg, file=sys.stderr)

    # Ensure at least the original change is present
    if not all_related:
        all_related.add(str(change_id))

    return list(all_related)


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


def main():
    args = parse_args()

    # Get username and password from args or environment variables
    user = args.user or os.environ.get("GERRIT_USER")
    password = args.password or os.environ.get("GERRIT_PASSWORD")

    session = requests.Session()
    session.auth = HTTPBasicAuth(user, password)

    # Validate that either changes or topic is provided
    if not args.changes and not args.topic:
        print(
            "❌ Error: Must provide either change IDs or --topic",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 1: Determine initial set of changes
    if args.topic:
        # Fetch all changes with the specified topic
        print(f"🔍 Fetching changes with topic '{args.topic}' ...")
        changes = fetch_changes_by_topic(session, args.url, args.topic)
    else:
        # Use the provided change IDs
        changes = args.changes

    # Step 2: Optionally expand to include related changes
    if args.related:
        changs_set = set()
        for change in changes:
            print(f"🔍 Fetching related changes for {change} ...")
            related = fetch_related_changes(session, args.url, change)
            changs_set.update(related)
        all_changes = sorted(changs_set)
    else:
        all_changes = changes

    print(f"Found {len(all_changes)} change(s):")
    for c in all_changes:
        print("  -", c)
    print()

    for c in all_changes:
        add_review_to_change(
            session, args.url, c, args.label, args.value, dry_run=args.dry_run
        )


if __name__ == "__main__":
    main()
