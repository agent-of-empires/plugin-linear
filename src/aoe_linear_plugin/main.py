"""JSON-RPC worker entry point for Agent of Empires."""

from __future__ import annotations

import json
import sys
from typing import Any

from aoe_linear_plugin.handlers import linear_open, linear_status


def _dispatch(method: str, params: dict[str, Any]) -> Any:
    if set(params) - {"path", "selected"}:
        raise ValueError("Unknown parameter")
    path = params.get("path", ".")
    selected = params.get("selected")
    if not isinstance(path, str) or (selected is not None and not isinstance(selected, str)):
        raise ValueError("path and selected must be strings")
    if method == "plugin.community.linear.status":
        return linear_status(path, selected=selected)
    if method == "plugin.community.linear.open":
        return linear_open(path, selected=selected, open_browser=True)
    raise LookupError(f"Unknown method: {method}")


def _error(code: int, message: str, request_id: Any = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _response(request: Any) -> dict[str, Any] | None:
    if isinstance(request, dict) and "id" not in request:
        return None
    response: dict[str, Any] | None = None
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        response = _error(-32600, "Invalid Request")
    else:
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")
        if not isinstance(method, str) or not isinstance(params, dict):
            response = _error(-32600, "Invalid Request")
        elif "id" not in request:
            return None
        elif request_id is not None and (isinstance(request_id, bool) or not isinstance(request_id, (str, int, float))):
            response = _error(-32600, "Invalid Request")
        else:
            try:
                response = {"jsonrpc": "2.0", "id": request_id, "result": _dispatch(method, params)}
            except LookupError as exc:
                response = _error(-32601, str(exc), request_id)
            except ValueError as exc:
                response = _error(-32602, str(exc), request_id)
    return response


def main() -> None:
    """Read newline-delimited JSON-RPC requests until stdin closes."""
    for line in sys.stdin:
        response: dict[str, Any] | None
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = _error(-32700, "Parse error")
        else:
            response = _response(request)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
