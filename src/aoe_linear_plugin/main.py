"""JSON-RPC worker entry point for Agent of Empires."""

from __future__ import annotations

import json
import sys
from typing import Any

from aoe_linear_plugin.handlers import linear_open, linear_status


def _dispatch(method: str, params: dict[str, Any]) -> Any:
    command = method.rsplit(".", 1)[-1]
    path = params.get("path", ".")
    selected = params.get("selected")
    if not isinstance(path, str) or (selected is not None and not isinstance(selected, str)):
        raise ValueError("path and selected must be strings")
    if command == "status":
        return linear_status(path, selected=selected)
    if command == "open":
        return linear_open(path, selected=selected, open_browser=True)
    raise LookupError(f"Unknown method: {method}")


def _response(request: Any) -> dict[str, Any] | None:
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return None
    if "id" not in request:
        return None
    request_id = request["id"]
    method = request.get("method")
    params = request.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Invalid params"}}
    try:
        return {"jsonrpc": "2.0", "id": request_id, "result": _dispatch(method, params)}
    except LookupError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": str(exc)}}
    except ValueError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}


def main() -> None:
    """Read newline-delimited JSON-RPC requests until stdin closes."""
    for line in sys.stdin:
        try:
            response = _response(json.loads(line))
        except json.JSONDecodeError:
            continue
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
