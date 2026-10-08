"""Exercise the JSONL transport and fresh-process verification without live data."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch

import rename_thread


CHILD = "00000000-0000-4000-8000-000000000001"
PARENT = "00000000-0000-4000-8000-000000000002"
TITLE = "审查变异注释项目质量缺陷"

FAKE_SERVER = r'''
import json
import os
from pathlib import Path
import sys

store = Path(__file__).with_suffix(".json")
log = Path(__file__).with_suffix(".jsonl")
initialized = False
for line in sys.stdin:
    message = json.loads(line)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"pid": os.getpid(), **message}) + "\n")
    method = message.get("method")
    if method == "initialize":
        result = {"userAgent": "isolated-test-server"}
    elif method == "initialized":
        initialized = True
        continue
    else:
        assert initialized, "Request before initialization"
        state = json.loads(store.read_text(encoding="utf-8"))
        params = message["params"]
        target = params["threadId"]
        if method == "thread/read":
            result = {"thread": {"id": target, "name": state[target]}}
        elif method == "thread/name/set":
            state[target] = params["name"]
            store.write_text(json.dumps(state), encoding="utf-8")
            result = {}
            print(json.dumps({"method": "thread/name/updated", "params": params}), flush=True)
        else:
            raise AssertionError(method)
    print(json.dumps({"id": message["id"], "result": result}), flush=True)
'''


class AppServerProtocolTest(unittest.TestCase):
    def client_with_messages(self, *messages):
        client = rename_thread.AppServer.__new__(rename_thread.AppServer)
        client.timeout = 0.01
        client.sequence = 0
        client.messages = queue.Queue()
        for message in messages:
            client.messages.put(message)
        sent = []
        client.send = sent.append
        return client, sent

    def test_notifications_requests_and_unrelated_ids_do_not_replace_response(self):
        client, sent = self.client_with_messages(
            '{"method":"thread/name/updated","params":{}}',
            '{"id":90,"method":"item/commandExecution/requestApproval","params":{}}',
            '{"id":99,"result":{"ignored":true}}',
            '{"id":1,"result":{"expected":true}}',
        )
        self.assertEqual(client.request("thread/read", {}), {"expected": True})
        self.assertEqual(sent[1]["id"], 90)
        self.assertEqual(sent[1]["error"]["code"], -32601)

    def test_malformed_responses_raise_controlled_errors(self):
        for response in (
            "[]", "null", "false", "invalid-json",
            '{"id":1,"error":"private-server-content"}',
            '{"id":1,"error":null}', '{"id":1,"error":{"code":"bad"}}',
            '{"id":1,"result":[]}', '{"id":1}',
        ):
            with self.subTest(response=response):
                client, _ = self.client_with_messages(response)
                with self.assertRaises(rename_thread.RenameError) as caught:
                    client.request("thread/read", {})
                self.assertNotIn("private-server-content", str(caught.exception))

    def test_server_rejection_does_not_echo_private_error_message(self):
        client, _ = self.client_with_messages(
            '{"id":1,"error":{"code":-32000,"message":"private-server-content"}}',
        )
        with self.assertRaises(rename_thread.RenameError) as caught:
            client.request("thread/name/set", {})
        self.assertIn("-32000", str(caught.exception))
        self.assertNotIn("private-server-content", str(caught.exception))

    def test_eof_timeout_and_reader_failure_are_controlled(self):
        for messages in ((), (None,), (rename_thread.RenameError("Read failed"),)):
            with self.subTest(messages=messages):
                client, _ = self.client_with_messages(*messages)
                with self.assertRaises(rename_thread.RenameError):
                    client.request("thread/read", {})


class AppServerProcessTest(unittest.TestCase):
    def test_persistence_is_verified_by_distinct_initialized_process(self):
        with tempfile.TemporaryDirectory(prefix="session-title-protocol-test-") as temp:
            executable = Path(temp) / "fake_codex.py"
            executable.write_text(
                f"#!{sys.executable}\n" + FAKE_SERVER, encoding="utf-8",
            )
            executable.chmod(0o700)
            store = executable.with_suffix(".json")
            store.write_text(json.dumps({CHILD: "Child", PARENT: "Parent"}))
            stdout, stderr = io.StringIO(), io.StringIO()
            with (
                patch.dict(rename_thread.os.environ, {
                    "CODEX_THREAD_ID": CHILD, "CODEX_SESSION_ID": PARENT,
                }, clear=True),
                patch.object(rename_thread.shutil, "which", return_value=str(executable)),
                patch.object(rename_thread.sys, "argv", ["rename_thread.py", TITLE]),
                redirect_stdout(stdout), redirect_stderr(stderr),
            ):
                status = rename_thread.main()
            self.assertEqual(status, 0, stderr.getvalue())
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["status"], "verified")
            self.assertTrue(result["request_accepted"])
            self.assertEqual(json.loads(store.read_text()), {CHILD: TITLE, PARENT: "Parent"})
            messages = [
                json.loads(line)
                for line in executable.with_suffix(".jsonl").read_text().splitlines()
            ]
            reads = [message for message in messages if message["method"] == "thread/read"]
            self.assertEqual(len(reads), 2)
            self.assertNotEqual(reads[0]["pid"], reads[1]["pid"])
            self.assertEqual({message["method"] for message in messages}, {
                "initialize", "initialized", "thread/read", "thread/name/set",
            })
            for pid in {message["pid"] for message in messages}:
                methods = [message["method"] for message in messages if message["pid"] == pid]
                self.assertEqual(methods[:2], ["initialize", "initialized"])


if __name__ == "__main__":
    unittest.main()
