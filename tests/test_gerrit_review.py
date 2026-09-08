import argparse
import json
import subprocess
import unittest
from unittest.mock import patch

import gerrit_review


class GerritReviewTest(unittest.TestCase):
    def setUp(self):
        self.config = gerrit_review.GerritSSH(
            "ocean-idc.byted.org", 29418, "xuxingliang"
        )

    def change(
        self,
        number,
        patchset=1,
        depends_on=None,
        needed_by=None,
        open=True,
    ):
        return {
            "number": number,
            "currentPatchSet": {"number": patchset},
            "dependsOn": depends_on or [],
            "neededBy": needed_by or [],
            "open": open,
        }

    @patch.dict("os.environ", {}, clear=True)
    def test_parse_args_uses_ocean_idc_defaults(self):
        args = gerrit_review.parse_args(["123"])
        self.assertEqual(args.host, "ocean-idc.byted.org")
        self.assertEqual(args.port, 29418)
        self.assertEqual(args.user, "xuxingliang")

    @patch.dict(
        "os.environ",
        {
            "GERRIT_HOST": "ocean-review.byted.org",
            "GERRIT_PORT": "29419",
            "GERRIT_USER": "reviewer",
        },
        clear=True,
    )
    def test_parse_args_uses_environment_and_cli_overrides(self):
        args = gerrit_review.parse_args(["123"])
        self.assertEqual(args.host, "ocean-review.byted.org")
        self.assertEqual(args.port, 29419)
        self.assertEqual(args.user, "reviewer")

        args = gerrit_review.parse_args(
            [
                "--host",
                "ocean-idc.byted.org",
                "--port",
                "29418",
                "--user",
                "xuxingliang",
                "123",
            ]
        )
        self.assertEqual(args.host, "ocean-idc.byted.org")
        self.assertEqual(args.port, 29418)
        self.assertEqual(args.user, "xuxingliang")

    def test_rejects_invalid_change_and_ssh_options(self):
        for value in ("0", "I123", "status:open", "123;touch /tmp/x"):
            with self.assertRaises(argparse.ArgumentTypeError):
                gerrit_review.change_identifier(value)
        for value in ("-oProxyCommand=x", "bad host", "host;cmd"):
            with self.assertRaises(argparse.ArgumentTypeError):
                gerrit_review.ssh_host(value)
        for value in ("0", "65536", "not-a-port"):
            with self.assertRaises(argparse.ArgumentTypeError):
                gerrit_review.ssh_port(value)

    def test_topic_query_escapes_special_characters(self):
        query = gerrit_review.topic_query('a "quoted" \\ topic; $(id)')
        self.assertEqual(query, 'topic:"a \\"quoted\\" \\\\ topic; $(id)"')

    @patch("gerrit_review.subprocess.run")
    def test_run_ssh_quotes_remote_args_and_passes_stdin(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
        output = gerrit_review.run_ssh(
            self.config,
            [
                "gerrit",
                "query",
                "--",
                'topic:a; printf "unsafe"; $(id)',
            ],
            input_text='{"message": "hello; $(id)"}\n',
        )
        self.assertEqual(output, "ok")
        command = run.call_args.args[0]
        self.assertEqual(
            command[:-1],
            [
                "ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "-p",
                "29418",
                "xuxingliang@ocean-idc.byted.org",
            ],
        )
        self.assertEqual(
            command[-1],
            "gerrit query -- 'topic:a; printf \"unsafe\"; $(id)'",
        )
        self.assertEqual(
            run.call_args.kwargs["input"], '{"message": "hello; $(id)"}\n'
        )
        self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_parse_query_output_filters_stats(self):
        output = "\n".join(
            [
                json.dumps(
                    {"number": "123", "currentPatchSet": {"number": "4"}}
                ),
                json.dumps({"type": "stats", "rowCount": 1}),
            ]
        )
        records = gerrit_review.parse_query_output(output)
        self.assertEqual(records[0]["number"], 123)
        self.assertEqual(records[0]["currentPatchSet"]["number"], 4)

    def test_parse_query_output_rejects_invalid_protocol(self):
        invalid_outputs = (
            "",
            '{"number": 1}\n',
            "{not-json}\n",
            '{"type": "stats", "rowCount": 1}\n',
            '{"number": 1}\n{"type": "stats", "rowCount": 1}\n',
        )
        for output in invalid_outputs:
            with self.subTest(output=output):
                with self.assertRaises(gerrit_review.GerritError):
                    gerrit_review.parse_query_output(output)

    @patch("gerrit_review.query_changes")
    def test_resolve_change_requires_unique_result(self, query):
        query.return_value = []
        with self.assertRaisesRegex(gerrit_review.GerritError, "not found"):
            gerrit_review.resolve_change(self.config, "123")

        query.return_value = [self.change(123), self.change(456)]
        with self.assertRaisesRegex(gerrit_review.GerritError, "ambiguous"):
            gerrit_review.resolve_change(self.config, "123")

        expected = self.change(123, 4)
        query.return_value = [expected]
        self.assertIs(
            gerrit_review.resolve_change(self.config, "123"), expected
        )

    @patch("gerrit_review.resolve_change")
    def test_expand_related_keeps_directional_ancestor_descendant_chains(
        self, resolve
    ):
        seed = self.change(
            2,
            depends_on=[{"number": 1}],
            needed_by=[{"number": 3}],
        )
        changes = {
            "1": self.change(1),
            "3": self.change(3, needed_by=[{"number": 4}]),
            "4": self.change(4),
        }
        resolve.side_effect = lambda config, value, dependencies: changes[
            value
        ]

        related = gerrit_review.expand_related(self.config, [seed])
        self.assertEqual(
            [change["number"] for change in related], [1, 2, 3, 4]
        )
        self.assertEqual(
            {call.args[1] for call in resolve.call_args_list}, {"1", "3", "4"}
        )
        self.assertEqual(resolve.call_count, 3)

    @patch("gerrit_review.resolve_change")
    def test_expand_related_stops_at_closed_changes(self, resolve):
        seed = self.change(
            2,
            depends_on=[{"number": 1}],
            needed_by=[{"number": 3}],
        )
        changes = {
            "1": self.change(1, depends_on=[{"number": 9}], open=False),
            "3": self.change(3, needed_by=[{"number": 4}]),
            "4": self.change(4),
        }
        resolve.side_effect = lambda config, value, dependencies: changes[
            value
        ]

        related = gerrit_review.expand_related(self.config, [seed])
        self.assertEqual([change["number"] for change in related], [2, 3, 4])
        self.assertEqual(
            {call.args[1] for call in resolve.call_args_list}, {"1", "3", "4"}
        )
        self.assertEqual(resolve.call_count, 3)

    @patch("gerrit_review.run_ssh")
    def test_add_review_uses_current_patchset_and_message(self, run_ssh):
        change = self.change(123, 4)
        gerrit_review.add_review_to_change(
            self.config,
            change,
            "Code-Review",
            1,
            message="looks good; $(id)",
        )
        remote_args = run_ssh.call_args.args[1]
        payload = json.loads(run_ssh.call_args.kwargs["input_text"])
        self.assertEqual(
            remote_args,
            ["gerrit", "review", "--json", "--", "123,4"],
        )
        self.assertEqual(
            payload,
            {
                "labels": {"Code-Review": 1},
                "message": "looks good; $(id)",
            },
        )

    @patch("gerrit_review.run_ssh")
    def test_dry_run_does_not_post_review(self, run_ssh):
        gerrit_review.add_review_to_change(
            self.config, self.change(123, 4), "Code-Review", 1, dry_run=True
        )
        run_ssh.assert_not_called()

    @patch("gerrit_review.subprocess.run")
    def test_run_ssh_reports_exit_failure(self, run):
        run.return_value = subprocess.CompletedProcess([], 255, "", "denied")
        with self.assertRaisesRegex(gerrit_review.GerritError, "denied"):
            gerrit_review.run_ssh(self.config, ["gerrit", "version"])

    @patch("gerrit_review.subprocess.run")
    def test_run_ssh_reports_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired("ssh", 30)
        with self.assertRaisesRegex(gerrit_review.GerritError, "timed out"):
            gerrit_review.run_ssh(self.config, ["gerrit", "version"])

    @patch("gerrit_review.subprocess.run")
    def test_run_ssh_reports_missing_client(self, run):
        run.side_effect = FileNotFoundError
        with self.assertRaisesRegex(
            gerrit_review.GerritError, "was not found"
        ):
            gerrit_review.run_ssh(self.config, ["gerrit", "version"])

    @patch("gerrit_review.add_review_to_change")
    @patch("gerrit_review.resolve_change")
    def test_main_passes_message_and_selected_instance(self, resolve, add):
        resolve.return_value = self.change(123, 4)
        result = gerrit_review.main(
            [
                "--host",
                "ocean-review.byted.org",
                "--message",
                "done",
                "123",
            ]
        )
        self.assertEqual(result, 0)
        config = add.call_args.args[0]
        self.assertEqual(config.host, "ocean-review.byted.org")
        self.assertEqual(add.call_args.kwargs["message"], "done")

    @patch("gerrit_review.run_ssh")
    def test_query_changes_requests_dependencies_and_no_limit(self, run_ssh):
        run_ssh.return_value = '{"type":"stats","rowCount":0}\n'
        gerrit_review.query_changes(
            self.config, 'topic:"feature"', dependencies=True
        )
        self.assertEqual(
            run_ssh.call_args.args[1],
            [
                "gerrit",
                "query",
                "--format=JSON",
                "--current-patch-set",
                "--no-limit",
                "--dependencies",
                "--",
                'topic:"feature"',
            ],
        )

    @patch("gerrit_review.add_review_to_change")
    @patch("gerrit_review.resolve_change")
    def test_main_aborts_before_review_when_discovery_fails(
        self, resolve, add
    ):
        resolve.side_effect = gerrit_review.GerritError("not found")
        self.assertEqual(gerrit_review.main(["123"]), 1)
        add.assert_not_called()

    @patch("gerrit_review.add_review_to_change")
    @patch("gerrit_review.resolve_change")
    def test_main_continues_after_one_review_failure(self, resolve, add):
        resolve.side_effect = [self.change(123), self.change(456)]
        add.side_effect = [gerrit_review.GerritError("denied"), None]
        self.assertEqual(gerrit_review.main(["123", "456"]), 1)
        self.assertEqual(add.call_count, 2)


if __name__ == "__main__":
    unittest.main()
