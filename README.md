gerrit-review
=============

A command-line tool to post review labels to Gerrit changes over SSH.

The tool can set labels such as `Jira-Review` or `Code-Review` on one or more changes. It can also select all changes in a topic and expand dependency ancestors and descendants.

Requirements
------------

- Python 3.8+
- OpenSSH client (`ssh`)
- A Gerrit SSH public key registered for your account
- Network access to the selected Gerrit SSH instance

No Gerrit HTTP password is required.

Installation
------------

### From PyPI

```bash
pip install gerrit-review
```

### From source

```bash
git clone https://github.com/XuNeo/gerrit-review.git
cd gerrit-review
pip install -e .
```

Usage
-----

```bash
gerrit-review [options] [change-id ...]
```

### SSH instances

The default connection is:

```text
xuxingliang@ocean-idc.byted.org:29418
```

Select the second independent Gerrit instance with:

```bash
gerrit-review --host ocean-review.byted.org 294498
```

The tool does not automatically search the other instance when a change is not found.

### Options

- `--host <host>`: Gerrit SSH host. Default: `ocean-idc.byted.org`
- `--port <port>`: Gerrit SSH port. Default: `29418`
- `--user <username>`, `-u`: Gerrit SSH username. Default: `xuxingliang`
- `--label <name>`: Label name. Default: `Code-Review`
- `--value <num>`: Label value. Default: `1`
- `--topic <name>`, `-t`: Select all changes with the topic
- `--related`: Include dependency ancestors and descendants
- `--dry-run`: Resolve and print targets without posting reviews
- `--message <text>`: Review message

The connection defaults can also be set with `GERRIT_HOST`, `GERRIT_PORT`, and `GERRIT_USER`. Command-line options take precedence.

### Arguments

`change-id ...` accepts positive numeric change numbers or full Gerrit Change-Ids such as `I0123456789abcdef0123456789abcdef01234567`. At least one change or `--topic` is required.

Authentication
--------------

The tool invokes the system OpenSSH client, so private keys, `ssh-agent`, host keys, proxies, and other SSH behavior remain controlled by your normal SSH configuration.

Verify both configured instances with:

```bash
ssh -p 29418 xuxingliang@ocean-idc.byted.org gerrit version
ssh -p 29418 xuxingliang@ocean-review.byted.org gerrit version
```

Examples
--------

### Review specific changes on the default instance

```bash
gerrit-review --label Jira-Review --value 1 18032 18747
```

### Review a change and its dependency chain

```bash
gerrit-review --related --label Jira-Review --value 1 18032
```

`--related` follows open changes through both `dependsOn` and `neededBy` transitively. Merged or abandoned changes form a boundary and are not reviewed. Each final target is reviewed at its current patch set.

### Review every change in a topic

```bash
gerrit-review --topic "my-feature" --label Jira-Review --value 1
```

### Use the ocean-review instance

```bash
gerrit-review \
  --host ocean-review.byted.org \
  --label Code-Review \
  --value 1 \
  294498
```

### Include a message

```bash
gerrit-review --message "Reviewed dependency chain" --related 18032
```

### Dry run

```bash
gerrit-review --topic "my-feature" --related --dry-run
```

Dry-run still performs read-only SSH queries so that Change-Ids, current patch sets, and dependencies can be resolved, but it never invokes `gerrit review`.

Notes
-----

- Topic queries use `--no-limit`, so Gerrit's default query limit does not silently omit changes.
- Discovery must complete before any review is posted. A discovery failure stops the operation.
- If one review post fails, the tool continues with the remaining targets and exits nonzero afterward.
- This tool posts change-level messages and labels. It does not manage inline comments or comment threads.

Contributing
------------

Contributions, fixes, and documentation improvements are welcome. Open an issue or submit a pull request with changes.

License
-------

This project is licensed under the MIT License — see the `LICENSE` file for details.
