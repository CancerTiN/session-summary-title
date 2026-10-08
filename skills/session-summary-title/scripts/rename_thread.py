#!/usr/bin/env python3
"""Persist a validated title through the local Codex app-server protocol."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid

from validate_title import validate_title


class RenameError(Exception):
    pass


def resolve_thread_id(explicit: str | None) -> str:
    if explicit is not None:
        return str(uuid.UUID(explicit))
    # Subagents may inherit the parent's session ID; the thread ID takes priority.
    current = os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
    if not current:
        raise RenameError("Current thread ID is unavailable; do not guess a target.")
    return str(uuid.UUID(current))


class AppServer:
    def __init__(self, executable: str, timeout: float):
        self.timeout = timeout
        self.sequence = 0
        self.messages: queue.Queue = queue.Queue()
        self.process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.reader = threading.Thread(target=self._collect, daemon=True)
        self.reader.start()

    def _collect(self) -> None:
        try:
            with self.process.stdout:
                for line in self.process.stdout:
                    self.messages.put(line)
        except (OSError, UnicodeError):
            self.messages.put(RenameError("Could not read app-server output."))
        finally:
            self.messages.put(None)

    def send(self, message: dict) -> None:
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def request(self, method: str, params: dict) -> dict:
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RenameError(f"{method} timed out.")
            try:
                line = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise RenameError(f"{method} timed out.") from None
            if line is None:
                raise RenameError(f"app-server exited during {method}.")
            if isinstance(line, RenameError):
                raise line
            try:
                message = json.loads(line)
            except (ValueError, TypeError):
                raise RenameError(f"Invalid JSON during {method}.") from None
            if not isinstance(message, dict):
                raise RenameError(f"Invalid {method} response: expected an object.")
            if "method" in message:
                if "id" in message:
                    self.send({
                        "id": message["id"],
                        "error": {"code": -32601, "message": "Metadata-only client"},
                    })
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                if not isinstance(error, dict) or type(error.get("code")) is not int:
                    raise RenameError(f"Invalid {method} error response.")
                code = error["code"]
                raise RenameError(f"{method} rejected by app-server (code {code}).")
            result = message.get("result")
            if not isinstance(result, dict):
                raise RenameError(f"Invalid {method} response.")
            return result

    def close(self) -> None:
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        finally:
            self.reader.join(timeout=3)


@contextmanager
def connect(executable: str, timeout: float):
    server = AppServer(executable, timeout)
    try:
        server.request("initialize", {
            "clientInfo": {"name": "session_summary_title", "version": "1.0"},
        })
        server.send({"method": "initialized", "params": {}})
        yield server
    finally:
        server.close()


def read_thread(server: AppServer, thread_id: str) -> dict:
    result = server.request("thread/read", {
        "threadId": thread_id, "includeTurns": False,
    })
    thread = result.get("thread")
    if not isinstance(thread, dict) or thread.get("id") != thread_id:
        raise RenameError("thread/read returned a different or missing thread ID.")
    if "name" not in thread:
        raise RenameError("thread/read did not provide a name to verify.")
    if thread["name"] is not None and not isinstance(thread["name"], str):
        raise RenameError("thread/read returned an invalid name.")
    return thread


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Exactly twelve Han characters")
    parser.add_argument("--thread-id", help="Only for a target explicitly named by the user")
    parser.add_argument("--timeout", type=float, default=15, help="Seconds per RPC (default: 15)")
    parser.add_argument(
        "--verify-only", action="store_true",
        help="Check the saved title without sending a rename request",
    )
    args = parser.parse_args()
    stage = "validate_input"
    thread_id = None
    changed = False
    write_attempted = False
    request_accepted = False
    try:
        validate_title(args.title)
        if not 0 < args.timeout <= 60:
            raise RenameError("Timeout must be greater than zero and at most 60 seconds.")
        stage = "resolve_target"
        thread_id = resolve_thread_id(args.thread_id)
        stage = "locate_cli"
        executable = shutil.which("codex")
        if not executable:
            raise RenameError("codex executable is unavailable.")
        if not args.verify_only:
            stage = "connect_writer"
            with connect(executable, args.timeout) as server:
                stage = "read_target"
                before = read_thread(server, thread_id)
                changed = before["name"] != args.title
                if changed:
                    stage = "set_title"
                    write_attempted = True
                    server.request("thread/name/set", {
                        "threadId": thread_id, "name": args.title,
                    })
                    request_accepted = True
        # A new process verifies persistence instead of the first client's memory.
        stage = "connect_verifier"
        with connect(executable, args.timeout) as verifier:
            stage = "verify_title"
            after = read_thread(verifier, thread_id)
            if after["name"] != args.title:
                raise RenameError("Persisted title does not match the requested title.")
        print(json.dumps({
            "status": "verified", "thread_id": thread_id,
            "title": args.title, "changed": changed,
            "operation": "verify" if args.verify_only else "rename",
            "write_attempted": write_attempted, "request_accepted": request_accepted,
            "verification": "thread/read from a new app-server process",
            "display": "not_checked",
        }, ensure_ascii=False))
        return 0
    except (RenameError, ValueError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({
            "status": "unconfirmed", "stage": stage, "thread_id": thread_id,
            "write_attempted": write_attempted,
            "request_accepted": request_accepted, "error": str(error),
        }, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
