"""NDJSON JSON-RPC worker entry point."""

from __future__ import annotations

import itertools
import json
import os
import queue
import sys
import threading
import time
from typing import Any

from aoe_linear_plugin import refresh as refresh_data
from aoe_linear_plugin.errors import LinearError
from aoe_linear_plugin.handlers import linear_open, linear_status
from aoe_linear_plugin.uistate import PANE_SLOT, ROW_BADGE_SLOT, ROW_COLUMN_SLOT, SELECT_METHOD, session_payloads

DEFAULT_REFRESH_SECS = 120
RPC_TIMEOUT = 10.0
EOF = object()
_ids = itertools.count(1_000_000)


class UnknownMethodError(Exception):
    """No worker handler is registered for the requested method."""


def _parse_message(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _response(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, kind: str, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": message, "data": {"kind": kind}}}


def _path(params: dict[str, Any]) -> str:
    args = params.get("args") or {}
    return args.get("path") or params.get("cwd") or "."


class Runtime:
    """Single stdin reader, bounded host RPC waits, and serialized refresh loop."""

    def __init__(self, stdin: Any = None, stdout: Any = None) -> None:
        self.stdin = stdin if stdin is not None else sys.stdin
        self.stdout = stdout if stdout is not None else sys.stdout
        self.inbox: queue.Queue[Any] = queue.Queue()
        self.lock = threading.Lock()
        self.stopped = False
        self.snapshot: dict[str, Any] = {"sessions": [], "auth": {"present": False}}
        self.selected: dict[str, str] = {}
        self.pushed: set[str] = set()
        self.interval = DEFAULT_REFRESH_SECS
        self.ignore_submodules = True
        self.show_priority = True
        self.next_refresh = 0.0
        self.refresh_due = False

    def send(self, message: dict[str, Any]) -> None:
        with self.lock:
            self.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.stdout.flush()

    def _read(self) -> None:
        try:
            for raw in self.stdin:
                message = _parse_message(raw)
                if message is not None:
                    self.inbox.put(message)
        finally:
            self.inbox.put(EOF)

    def call_host(self, method: str, params: dict[str, Any], timeout: float = RPC_TIMEOUT) -> Any:
        request_id = next(_ids)
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self.inbox.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                return None
            if message is EOF:
                self.stopped = True
                self.inbox.put(EOF)
                return None
            if message.get("id") == request_id and "method" not in message:
                return message.get("result")
            self.handle(message)
        return None

    def sessions(self) -> list[dict[str, Any]] | None:
        result = self.call_host("sessions.list", {"exclude": ["archived", "snoozed", "trashed"]})
        values = result.get("sessions") if isinstance(result, dict) else None
        if not isinstance(values, list):
            return None
        valid = all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in values)
        if not valid:
            return None
        return [
            item for item in values if not item.get("archived") and not item.get("snoozed") and not item.get("trashed")
        ]

    def refresh(self, sessions: list[dict[str, Any]] | None = None) -> None:
        sessions = self.sessions() if sessions is None else sessions
        if sessions is None or self.stopped:
            return
        self.snapshot = refresh_data.build_snapshot(sessions, ignore_submodules=self.ignore_submodules)
        self._push()
        active = {item.get("session_id") for item in self.snapshot.get("sessions", [])}
        self._remove_vanished(active)
        self.pushed = {sid for sid in active if isinstance(sid, str)}

    def _remove_vanished(self, active: set[Any]) -> None:
        for sid in self.pushed - active:
            for slot, slot_id in (ROW_BADGE_SLOT, ROW_COLUMN_SLOT, PANE_SLOT):
                params = {"slot": slot, "id": slot_id, "session_id": sid}
                self.send({"jsonrpc": "2.0", "id": next(_ids), "method": "ui.state.remove", "params": params})

    def _push(self) -> None:
        for params in session_payloads(self.snapshot, self.selected, show_priority=self.show_priority):
            method = "ui.state.set"
            if params.get("slot") == ROW_COLUMN_SLOT[0] and not params.get("payload", {}).get("text"):
                method = "ui.state.remove"
            self.send({"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params})

    def _command_result(self, method: str, params: dict[str, Any]) -> Any:
        if method in ("plugin.community.linear.status", "plugin.community.linear.open"):
            if not isinstance(params, dict) or set(params) - {"path", "selected"}:
                raise ValueError("Unknown parameter")
            path = params.get("path", ".")
            selected = params.get("selected")
            if not isinstance(path, str) or (selected is not None and not isinstance(selected, str)):
                raise ValueError("path and selected must be strings")
            if method == "plugin.community.linear.status":
                return linear_status(path, selected=selected)
            return linear_open(path, selected=selected, open_browser=True)
        if method == "linear.status":
            return linear_status(_path(params), selected=params.get("issue"))
        if method in ("linear.open", "plugin.community.linear.open"):
            return linear_open(_path(params), selected=params.get("issue"))
        if method in ("linear.refresh", "plugin.community.linear.refresh", SELECT_METHOD):
            return {"accepted": True}
        raise UnknownMethodError(method)

    def _after_command(self, method: str, params: dict[str, Any]) -> None:
        if method in ("linear.refresh", "plugin.community.linear.refresh"):
            self.refresh_due = True
        elif method == SELECT_METHOD:
            sid = params.get("session_id")
            identifier = params.get("issue")
            if isinstance(sid, str) and isinstance(identifier, str):
                self.selected[sid] = identifier
                self._push()

    def handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            return
        params = message.get("params") or {}
        msg_id = message.get("id")
        try:
            result = self._command_result(method, params)
            self._after_command(method, params)
        except UnknownMethodError:
            if isinstance(msg_id, int):
                self.send(_error(msg_id, "method_not_found", f"Unknown method: {method}"))
            return
        except (LinearError, ValueError) as exc:
            if isinstance(msg_id, int):
                self.send(_error(msg_id, getattr(exc, "kind", "invalid_request"), str(exc)))
            return
        except Exception:  # noqa: BLE001  isolate malformed requests and unexpected repaint failures.
            if isinstance(msg_id, int):
                self.send(_error(msg_id, "internal_error", "Linear command failed unexpectedly."))
            return
        if isinstance(msg_id, int):
            self.send(_response(msg_id, result))

    def _configure(self) -> None:
        result = self.call_host("config.get", {"key": "ui_refresh_secs"})
        value = result.get("value") if isinstance(result, dict) else None
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            self.interval = min(value, 86400)
        else:
            raw = os.environ.get("AOE_LINEAR_UI_REFRESH_SECS")
            if raw is not None:
                try:
                    self.interval = min(max(0, int(raw)), 86400)
                except ValueError:
                    self.interval = DEFAULT_REFRESH_SECS
        self._configure_boolean("ignore_submodules")
        self._configure_boolean("show_priority")

    def _configure_boolean(self, key: str) -> None:
        result = self.call_host("config.get", {"key": key})
        value = result.get("value") if isinstance(result, dict) else None
        if isinstance(value, bool):
            setattr(self, key, value)

    def _scheduled_refresh(self) -> None:
        self.refresh_due = False
        try:
            self.refresh()
        except Exception as exc:  # noqa: BLE001  one failed poll must not terminate the worker.
            sys.stderr.write(f"Linear refresh failed unexpectedly ({type(exc).__name__}).\n")
        finally:
            self.next_refresh = time.monotonic() + self.interval if self.interval else float("inf")

    def run(self) -> None:
        threading.Thread(target=self._read, daemon=True).start()
        self._configure()
        while not self.stopped:
            if self.refresh_due or time.monotonic() >= self.next_refresh:
                self._scheduled_refresh()
            if self.stopped:
                break
            timeout = max(0.0, self.next_refresh - time.monotonic()) if self.interval else None
            try:
                item = self.inbox.get(timeout=timeout)
            except queue.Empty:
                continue
            if item is EOF:
                break
            self.handle(item)


def main() -> None:
    Runtime().run()


if __name__ == "__main__":
    main()
