gerrit-review
=============

A command-line tool to post review labels to Gerrit changes.

This tool can be used to set labels (for example, Jira-Review or Code-Review) on one or more Gerrit change IDs. It also supports fetching and operating on related changes and changes within a topic.

Requirements
------------

- Python 3.8+
- Network access to your Gerrit server with HTTP authentication configured

Installation
------------

### From PyPI (recommended)

```bash
pip install gerrit-review
```

### From source

```bash
git clone https://github.com/XuNeo/gerrit-review.git
cd gerrit-review
pip install -e .
```

### Standalone script (legacy)

You can also download and run the standalone script directly:

```bash
chmod +x gerrit-review
gerrit-review --help
```

Usage
-----

Basic usage:

```bash
gerrit-review [options] [change-id ...]
```

### Options

- `--label <name>` : The label name to post (e.g. `Jira-Review`, `Code-Review`). Default: `Code-Review`
- `--value <num>` : The value to post for the label (e.g. `1`, `-1`, `2`). Default: `1`
- `--url <url>` : Gerrit base URL. Default: `https://gerrit.pt.mioffice.cn/`
- `--user <username>`, `-u` : Gerrit username (or set `GERRIT_USER` environment variable)
- `--password <password>`, `-p` : Gerrit HTTP password (or set `GERRIT_PASSWORD` environment variable)
- `--topic <name>`, `-t` : Fetch all changes with the specified topic name
- `--related` : Fetch related changes (dependency chain) for each change
- `--dry-run` : Do not post changes, only print what would be done
- `--message <text>` : Review message to include

### Arguments

- `change-id ...` : One or more Gerrit change numeric IDs. Not required if `--topic` is used.

### Authentication

Credentials can be provided via command-line arguments or environment variables:

```bash
# Using command-line arguments
gerrit-review --user myuser --password mypass --label Jira-Review --value 1 6197799

# Using environment variables
export GERRIT_USER=myuser
export GERRIT_PASSWORD=mypass
gerrit-review --label Jira-Review --value 1 6197799
```

Command-line arguments take precedence over environment variables.

Examples
--------

### Example 1: Review specific changes

Post a label to one or more changes:

```bash
gerrit-review --label Jira-Review --value 1 6197799 6197798
```

### Example 2: Review changes with their dependencies

Fetch related changes (dependency chain) and post the label to all:

```bash
gerrit-review --label Jira-Review --value 1 6197799 --related
```

Output:
```text
🔍 Fetching related changes for 6197799 ...
Found 2 change(s):
  - 6197798
  - 6197799

✅ Posted Jira-Review=1 to 6197798
✅ Posted Jira-Review=1 to 6197799
```

### Example 3: Review all changes in a topic

Fetch all changes with a specific topic and post the label:

```bash
gerrit-review --topic "my-feature" --label Jira-Review --value 1
```

### Example 4: Review topic changes with their dependencies

Fetch all changes in a topic, then fetch their related changes (dependency chains), and post the label to all:

```bash
gerrit-review --topic "my-feature" --related --label Jira-Review --value 1
```

Output:
```text
🔍 Fetching changes with topic 'my-feature' ...
🔍 Fetching related changes for 6181520 ...
🔍 Fetching related changes for 6181521 ...
Found 5 change(s):
  - 6181519
  - 6181520
  - 6181521
  - 6181522
  - 6181523

✅ Posted Jira-Review=1 to 6181519
✅ Posted Jira-Review=1 to 6181520
...
```

### Example 5: Dry run

Preview what would be done without actually posting:

```bash
gerrit-review --topic "my-feature" --related --label Jira-Review --value 1 --dry-run
```

Notes
-----

- This script uses Gerrit's REST API and requires HTTP authentication
- The `--related` flag fetches changes in the dependency chain (parent/child commits)
- The `--topic` flag queries all changes tagged with the specified topic
- When both topic and related are used, the script first fetches all changes in the topic, then expands to include their dependency chains
- Results are automatically deduplicated when multiple changes reference the same dependencies

Contributing
------------

Contributions, fixes, and documentation improvements are welcome. Open an issue or submit a pull request with changes.

License
-------
This project is licensed under the MIT License — see the `LICENSE` file for details.
