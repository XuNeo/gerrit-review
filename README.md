gerrit-review.py
=================

gerrit-review is a small command-line helper to post review labels to Gerrit changes.

This repository contains a single script, `gerrit-review.py`, which can be used to set a label (for example, a Jira-Review label) on one or more Gerrit change IDs. It also supports fetching and operating on related changes.

Requirements
------------

- Python 3.8+ (or your system Python)
- Network access to your Gerrit server and appropriate authentication (SSH/HTTP) configured for the script's requests.

Installation
------------

No installation is required. Make the script executable and run it directly:

```bash
chmod +x ./gerrit-review.py
```

Usage
-----

Basic usage:

```bash
./gerrit-review.py --label <Label-Name> --value <value> <changes> [<change-id> ...] [--related]
```

- `--label`  : The numeric or string label name to post (e.g. `Jira-Review`).
- `--value`  : The value to post for the label (e.g. `1`, `-1`, `2`).
- `<changes>` : One or more Gerrit change numeric IDs to operate on.
- `--related`: Optional flag. If provided, the script will fetch related changes and post the same label/value to them as well.

Example
-------

Here's an example run that demonstrates fetching related changes and posting a label to each found change:

```text
./gerrit-review.py --label Jira-Review --value 1 6197799 --related



🔍 Fetching related changes for 6197799 ...
Found 2 change(s):
	- 6197799
	- 6197798

✅ Posted Jira-Review=1 to 6197799
✅ Posted Jira-Review=1 to 6197798
```

Contributing
------------

Contributions, fixes, and documentation improvements are welcome. Open an issue or submit a pull request with changes.

License
-------
This project is licensed under the MIT License — see the `LICENSE` file for details.
