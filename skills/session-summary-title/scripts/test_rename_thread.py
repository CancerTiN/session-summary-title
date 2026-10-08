"""Regression checks for target isolation and observable rename outcomes."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest.mock import Mock, patch

import rename_thread


CHILD = "00000000-0000-4000-8000-000000000001"
PARENT = "00000000-0000-4000-8000-000000000002"
OTHER = "00000000-0000-4000-8000-000000000003"
TITLE = "审查变异注释项目质量缺陷"


class RenameThreadTest(unittest.TestCase):
    def run_helper(
        self, environment, extra_args=(), unreadable=None, already_named=False,
        fail_at=None, persist=True, title=TITLE, executable="codex",
    ):
        names = {CHILD: TITLE if already_named else "Child", PARENT: "Parent", OTHER: "Other"}
        requests = []
        connections = []

        class Server:
            def request(self, method, params):
                requests.append((method, params.copy()))
                target = params["threadId"]
                if target == unreadable:
                    raise rename_thread.RenameError("Thread is unreadable.")
                if method == "thread/read":
                    if len(connections) == 2 and fail_at == "verify_title":
                        raise rename_thread.RenameError("Verification read failed.")
                    return {"thread": {"id": target, "name": names[target]}}
                if method == "thread/name/set":
                    if persist:
                        names[target] = params["name"]
                    if fail_at == "set_title":
                        raise rename_thread.RenameError("Rename response timed out.")
                    return {}
                raise AssertionError(method)

        @contextmanager
        def connect(*args):
            server = Server()
            connections.append(server)
            if len(connections) == 2 and fail_at == "connect_verifier":
                raise rename_thread.RenameError("Verifier could not connect.")
            yield server

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(rename_thread.os.environ, environment, clear=True),
            patch.object(rename_thread.sys, "argv", ["rename_thread.py", title, *extra_args]),
            patch.object(rename_thread.shutil, "which", return_value=executable),
            patch.object(rename_thread, "connect", side_effect=connect),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            status = rename_thread.main()
        result = json.loads(stdout.getvalue() if status == 0 else stderr.getvalue())
        return status, result, names, requests, connections

    def test_subagent_is_renamed_and_verified_without_touching_parent(self):
        status, result, names, requests, connections = self.run_helper(
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT})
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["thread_id"], CHILD)
        self.assertEqual(names, {CHILD: TITLE, PARENT: "Parent", OTHER: "Other"})
        self.assertTrue(all(params["threadId"] == CHILD for _, params in requests))
        self.assertEqual(len(connections), 2)
        self.assertIsNot(connections[0], connections[1])

    def test_normal_and_legacy_sessions_remain_supported(self):
        for environment in (
            {"CODEX_THREAD_ID": CHILD},
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": CHILD},
            {"CODEX_SESSION_ID": CHILD},
            {"CODEX_THREAD_ID": "", "CODEX_SESSION_ID": CHILD},
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": "invalid-parent"},
        ):
            with self.subTest(environment=environment):
                status, result, *_ = self.run_helper(environment)
                self.assertEqual(status, 0)
                self.assertEqual(result["thread_id"], CHILD)

    def test_invalid_or_missing_current_id_never_falls_back_to_parent(self):
        for environment in ({}, {"CODEX_THREAD_ID": "invalid", "CODEX_SESSION_ID": PARENT}):
            with self.subTest(environment=environment):
                status, result, names, requests, connections = self.run_helper(environment)
                self.assertEqual(status, 1)
                self.assertFalse(result["write_attempted"])
                self.assertEqual(names[PARENT], "Parent")
                self.assertEqual(requests, [])
                self.assertEqual(connections, [])

    def test_unreadable_current_thread_never_falls_back_to_parent(self):
        status, result, names, requests, _ = self.run_helper(
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT}, unreadable=CHILD)
        self.assertEqual(status, 1)
        self.assertFalse(result["write_attempted"])
        self.assertEqual(names[PARENT], "Parent")
        self.assertEqual(requests, [("thread/read", {"threadId": CHILD, "includeTurns": False})])

    def test_explicit_target_overrides_environment(self):
        status, result, names, _, _ = self.run_helper(
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT}, ["--thread-id", OTHER])
        self.assertEqual(status, 0)
        self.assertEqual(result["thread_id"], OTHER)
        self.assertEqual(names, {CHILD: "Child", PARENT: "Parent", OTHER: TITLE})

    def test_invalid_explicit_target_does_not_fall_back_to_environment(self):
        for target in ("", "invalid"):
            with self.subTest(target=target):
                status, result, _, requests, _ = self.run_helper(
                    {"CODEX_THREAD_ID": CHILD}, ["--thread-id", target])
                self.assertEqual(status, 1)
                self.assertFalse(result["write_attempted"])
                self.assertEqual(requests, [])

    def test_existing_title_is_verified_without_writing(self):
        status, result, names, requests, connections = self.run_helper(
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT}, already_named=True)
        self.assertEqual(status, 0)
        self.assertFalse(result["changed"])
        self.assertEqual(names[PARENT], "Parent")
        self.assertEqual([method for method, _ in requests], ["thread/read", "thread/read"])
        self.assertEqual(len(connections), 2)

    def test_lost_rename_response_is_unconfirmed_even_if_name_was_saved(self):
        status, result, names, _, connections = self.run_helper(
            {"CODEX_THREAD_ID": CHILD}, fail_at="set_title",
        )
        self.assertEqual(status, 1)
        self.assertEqual(names[CHILD], TITLE)
        self.assertTrue(result["write_attempted"])
        self.assertFalse(result["request_accepted"])
        self.assertEqual(result["stage"], "set_title")
        self.assertEqual(result["thread_id"], CHILD)
        self.assertEqual(len(connections), 1)

    def test_accepted_write_is_unconfirmed_when_verification_fails(self):
        for fail_at in ("verify_title", "connect_verifier"):
            with self.subTest(fail_at=fail_at):
                status, result, _, requests, _ = self.run_helper(
                    {"CODEX_THREAD_ID": CHILD}, fail_at=fail_at,
                )
                self.assertEqual(status, 1)
                self.assertTrue(result["request_accepted"])
                self.assertEqual(result["stage"], fail_at)
                self.assertEqual(
                    sum(method == "thread/name/set" for method, _ in requests), 1,
                )

    def test_accepted_but_unpersisted_name_is_not_reported_as_success(self):
        status, result, names, _, _ = self.run_helper(
            {"CODEX_THREAD_ID": CHILD}, persist=False,
        )
        self.assertEqual(status, 1)
        self.assertTrue(result["request_accepted"])
        self.assertEqual(result["stage"], "verify_title")
        self.assertEqual(names[CHILD], "Child")

    def test_verify_only_matches_without_writing(self):
        status, result, _, requests, connections = self.run_helper(
            {"CODEX_THREAD_ID": CHILD}, ["--verify-only"], already_named=True,
        )
        self.assertEqual(status, 0)
        self.assertEqual(result["operation"], "verify")
        self.assertFalse(result["write_attempted"])
        self.assertFalse(result["changed"])
        self.assertEqual([method for method, _ in requests], ["thread/read"])
        self.assertEqual(len(connections), 1)

    def test_verify_only_never_changes_a_mismatched_title(self):
        status, result, names, requests, _ = self.run_helper(
            {"CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT},
            ["--verify-only"],
        )
        self.assertEqual(status, 1)
        self.assertFalse(result["write_attempted"])
        self.assertEqual(result["stage"], "verify_title")
        self.assertEqual(names, {CHILD: "Child", PARENT: "Parent", OTHER: "Other"})
        self.assertEqual(requests, [("thread/read", {"threadId": CHILD, "includeTurns": False})])

    def test_invalid_inputs_never_connect(self):
        for title, extra in (
            ("过短标题", []), (TITLE, ["--timeout", "0"]),
            (TITLE, ["--timeout", "61"]), (TITLE, ["--timeout", "nan"]),
        ):
            with self.subTest(title=title, extra=extra):
                status, result, _, requests, connections = self.run_helper(
                    {"CODEX_THREAD_ID": CHILD}, extra, title=title,
                )
                self.assertEqual(status, 1)
                self.assertEqual(result["stage"], "validate_input")
                self.assertFalse(result["write_attempted"])
                self.assertEqual(requests, [])
                self.assertEqual(connections, [])

    def test_missing_cli_reports_stage_without_connecting(self):
        status, result, _, requests, connections = self.run_helper(
            {"CODEX_THREAD_ID": CHILD}, executable=None,
        )
        self.assertEqual(status, 1)
        self.assertEqual(result["stage"], "locate_cli")
        self.assertFalse(result["write_attempted"])
        self.assertEqual(requests, [])
        self.assertEqual(connections, [])

    def test_invalid_thread_metadata_is_rejected_before_writing(self):
        for thread in (
            [], {"id": PARENT, "name": TITLE}, {"id": CHILD},
            {"id": CHILD, "name": []},
        ):
            with self.subTest(thread=thread):
                server = Mock()
                server.request.return_value = {"thread": thread}
                with self.assertRaises(rename_thread.RenameError):
                    rename_thread.read_thread(server, CHILD)
                server.request.assert_called_once_with(
                    "thread/read", {"threadId": CHILD, "includeTurns": False},
                )

    def test_unnamed_thread_metadata_is_valid(self):
        server = Mock()
        server.request.return_value = {"thread": {"id": CHILD, "name": None}}
        self.assertIsNone(rename_thread.read_thread(server, CHILD)["name"])


if __name__ == "__main__":
    unittest.main()
