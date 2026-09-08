#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from collections import deque
from dataclasses import dataclass
import json
import os
import re
import shlex
import subprocess
import sys

DEFAULT_HOST = "ocean-idc.byted.org"
DEFAULT_PORT = 29418
DEFAULT_USER = "xuxingliang"
SSH_TIMEOUT = 30
CHANGE_ID_RE = re.compile(r"^I[0-9a-fA-F]{40}$")
CHANGE_NUMBER_RE = re.compile(r"^[1-9][0-9]*$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
USER_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class GerritError(Exception):
    pass


@dataclass(frozen=True)
class GerritSSH:
    host: str
    port: int
    user: str

    @property
    def destination(self):
        return f"{self.user}@{self.host}"


def ssh_host(value):
    if not HOST_RE.fullmatch(value) or value.startswith("-"):
        raise argparse.ArgumentTypeError(f"invalid SSH host: {value}")
    return value


def ssh_user(value):
    if not USER_RE.fullmatch(value) or value.startswith("-"):
        raise argparse.ArgumentTypeError(f"invalid SSH user: {value}")
    return value


def ssh_port(value):
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "SSH port must be an integer"
        ) from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "SSH port must be between 1 and 65535"
        )
    return port


def change_identifier(value):
    if CHANGE_NUMBER_RE.fullmatch(value) or CHANGE_ID_RE.fullmatch(value):
        return value
    raise argparse.ArgumentTypeError(
        "change must be a positive number or a full Gerrit Change-Id"
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Add a review label to Gerrit changes over SSH, optionally "
            "including related changes"
        )
    )
    parser.add_argument(
        "changes",
        nargs="*",
        type=change_identifier,
        help=(
            "One or more full Change-Ids (I...) or numeric change numbers. "
            "Not required if --topic is used."
        ),
    )
    parser.add_argument(
        "--host",
        type=ssh_host,
        default=os.environ.get("GERRIT_HOST", DEFAULT_HOST),
        help=(
            f"Gerrit SSH host (default: {DEFAULT_HOST}; " "or set GERRIT_HOST)"
        ),
    )
    parser.add_argument(
        "--port",
        type=ssh_port,
        default=os.environ.get("GERRIT_PORT", str(DEFAULT_PORT)),
        help=(
            f"Gerrit SSH port (default: {DEFAULT_PORT}; " "or set GERRIT_PORT)"
        ),
    )
    parser.add_argument(
        "--user",
        "-u",
        type=ssh_user,
        default=os.environ.get("GERRIT_USER", DEFAULT_USER),
        help=(
            f"Gerrit SSH username (default: {DEFAULT_USER}; "
            "or set GERRIT_USER)"
        ),
    )
    parser.add_argument(
        "--label",
        default="Code-Review",
        help="Label name (default: Code-Review)",
    )
    parser.add_argument(
        "--value",
        type=int,
        default=1,
        help="Label value (default: 1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve changes but do not post reviews",
    )
    parser.add_argument(
        "--topic",
        "-t",
        help="Fetch all changes with the specified topic name",
    )
    parser.add_argument(
        "--related",
        action="store_true",
        help="Include the dependency ancestors and descendants",
    )
    parser.add_argument("--message", default="", help="Review message")
    args = parser.parse_args(argv)
    if not args.changes and not args.topic:
        parser.error("must provide either change IDs or --topic")
    return args


def run_ssh(config, remote_args, input_text=None):
    command = [
        "ssh",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-p",
        str(config.port),
        config.destination,
        shlex.join(remote_args),
    ]
    try:
        result = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=SSH_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GerritError("OpenSSH client 'ssh' was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise GerritError(
            f"SSH command timed out for {config.destination}:{config.port}"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if not detail:
            detail = "no error output"
        raise GerritError(
            f"SSH command failed for {config.destination}:{config.port} "
            f"(exit {result.returncode}): {detail}"
        )
    return result.stdout


def parse_query_output(output):
    stats = None
    try:
        rows = [
            json.loads(line) for line in output.splitlines() if line.strip()
        ]
    except json.JSONDecodeError as exc:
        raise GerritError(f"invalid JSON from Gerrit query: {exc}") from exc

    if rows and isinstance(rows[-1], dict) and rows[-1].get("type") == "stats":
        stats = rows.pop()
    if stats is None:
        raise GerritError("Gerrit query response is missing its stats record")
    if stats.get("rowCount") != len(rows):
        raise GerritError(
            "Gerrit query row count does not match its stats record"
        )

    for row in rows:
        try:
            number = int(row["number"])
            patchset = int(row["currentPatchSet"]["number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GerritError(
                "Gerrit query returned a change without a current patch set"
            ) from exc
        if number <= 0 or patchset <= 0:
            raise GerritError("Gerrit query returned an invalid change number")
        row["number"] = number
        row["currentPatchSet"]["number"] = patchset
    return rows


def query_changes(config, query, dependencies=False):
    remote_args = [
        "gerrit",
        "query",
        "--format=JSON",
        "--current-patch-set",
        "--no-limit",
    ]
    if dependencies:
        remote_args.append("--dependencies")
    remote_args.extend(["--", query])
    return parse_query_output(run_ssh(config, remote_args))


def resolve_change(config, identifier, dependencies=False):
    records = query_changes(
        config, f"change:{identifier}", dependencies=dependencies
    )
    if not records:
        raise GerritError(f"change not found: {identifier}")
    if len(records) != 1:
        raise GerritError(
            f"change is ambiguous: {identifier}; use its numeric change number"
        )
    return records[0]


def topic_query(topic):
    escaped = topic.replace("\\", "\\\\").replace('"', '\\"')
    return f'topic:"{escaped}"'


def fetch_changes_by_topic(config, topic, dependencies=False):
    records = query_changes(
        config, topic_query(topic), dependencies=dependencies
    )
    if not records:
        raise GerritError(f"no changes found with topic: {topic}")
    return records


def dependency_identity(dependency):
    number = dependency.get("number")
    if number is not None and CHANGE_NUMBER_RE.fullmatch(str(number)):
        return str(number), int(number)
    change_id = dependency.get("id")
    if change_id is not None and CHANGE_ID_RE.fullmatch(str(change_id)):
        return str(change_id), None
    raise GerritError("Gerrit returned a dependency without a valid change ID")


def is_open(change):
    return change.get("open", change.get("status") == "NEW")


def expand_related(config, seeds):
    cache = {record["number"]: record for record in seeds}
    seed_numbers = list(cache)

    def traverse(field):
        seen = set(seed_numbers)
        pending = deque(seed_numbers)
        while pending:
            record = cache[pending.popleft()]
            for dependency in record.get(field) or []:
                identifier, cache_key = dependency_identity(dependency)
                related = cache.get(cache_key)
                if related is None:
                    related = resolve_change(
                        config, identifier, dependencies=True
                    )
                    cache[related["number"]] = related
                if not is_open(related):
                    continue
                if related["number"] not in seen:
                    seen.add(related["number"])
                    pending.append(related["number"])
        return seen

    numbers = traverse("dependsOn") | traverse("neededBy")
    return [cache[number] for number in sorted(numbers)]


def add_review_to_change(
    config, change, label, value, message="", dry_run=False
):
    number = change["number"]
    patchset = change["currentPatchSet"]["number"]
    target = f"{number},{patchset}"
    payload = {"labels": {label: value}, "message": message}
    payload_text = json.dumps(payload, ensure_ascii=False)

    if dry_run:
        print(
            f"🟡 [Dry-run] Would review {target} on {config.host}: "
            f"{payload_text}"
        )
        return

    run_ssh(
        config,
        ["gerrit", "review", "--json", "--", target],
        input_text=payload_text + "\n",
    )
    print(f"✅ Posted {label}={value} to {target} on {config.host}")


def main(argv=None):
    args = parse_args(argv)
    config = GerritSSH(args.host, args.port, args.user)

    try:
        if args.topic:
            print(f"🔍 Fetching changes with topic '{args.topic}' ...")
            changes = fetch_changes_by_topic(
                config, args.topic, dependencies=args.related
            )
        else:
            identifiers = dict.fromkeys(args.changes)
            changes = [
                resolve_change(config, change, dependencies=args.related)
                for change in identifiers
            ]

        changes = list(
            {change["number"]: change for change in changes}.values()
        )
        if args.related:
            print("🔍 Fetching related changes ...")
            changes = expand_related(config, changes)
        else:
            changes.sort(key=lambda change: change["number"])
    except GerritError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(
        f"Found {len(changes)} change(s) on "
        f"{config.destination}:{config.port}:"
    )
    for change in changes:
        print(
            f"  - {change['number']}," f"{change['currentPatchSet']['number']}"
        )
    print()

    failures = 0
    for change in changes:
        try:
            add_review_to_change(
                config,
                change,
                args.label,
                args.value,
                message=args.message,
                dry_run=args.dry_run,
            )
        except GerritError as exc:
            failures += 1
            print(f"❌ {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
