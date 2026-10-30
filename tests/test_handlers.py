from __future__ import annotations

import subprocess
from pathlib import Path

import httpx

from aoe_linear_plugin.auth import resolve_token
from aoe_linear_plugin.handlers import linear_open, linear_status


def test_token_resolution_prefers_named_linear_key_only() -> None:
    assert resolve_token({"LINEAR_API_KEY": " first ", "LINEAR_TOKEN": "second"}) == "first"
    assert resolve_token({"LINEAR_TOKEN": " second "}) == "second"
    assert resolve_token({"GITHUB_TOKEN": "not-linear"}) is None
    assert resolve_token({"LINEAR_API_KEY": "  "}) is None


def test_status_auth_error_is_actionable_without_requesting_network(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "eng-3-fix", str(tmp_path)], check=True, capture_output=True)
    status = linear_status(str(tmp_path), env={})
    assert status["branch"] == "eng-3-fix"
    assert status["issues"] == []
    assert status["error"]["kind"] == "auth"
    assert "LINEAR_API_KEY" in status["error"]["hint"]


def test_status_on_a_checkout_that_does_not_use_linear_reports_no_error(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    status = linear_status(str(tmp_path), env={})
    assert status["linked"] is False
    assert status["error"] is None
    assert status["summary"] == "Linear: no issue linked to main"


def test_unlinked_checkout_ignores_api_failures(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "dependabot/pip/httpx-0.27.0", str(tmp_path)], check=True, capture_output=True)
    status = linear_status(
        str(tmp_path),
        env={"LINEAR_API_KEY": "token"},
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    assert status["linked"] is False
    assert status["error"] is None
    assert status["summary"].startswith("Linear: no issue linked")


def test_open_without_a_linked_issue_is_not_an_error(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    assert linear_open(str(tmp_path), env={}) == {"url": "", "kind": "none", "identifier": ""}


def test_status_uses_branch_issue_identifier_and_summarizes_state(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "feature/ENG-7-do-work", str(tmp_path)], check=True, capture_output=True)

    def response(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        issue = {"id": "i7", "identifier": "ENG-7", "title": "Do work", "state": {"name": "In Progress"}}
        if "issueVcsBranchSearch" in body:
            return httpx.Response(200, json={"data": {"issueVcsBranchSearch": issue}})
        return httpx.Response(200, json={"data": {"issue": issue}})

    status = linear_status(
        str(tmp_path),
        env={"LINEAR_API_KEY": "token"},
        transport=httpx.MockTransport(response),
    )
    assert status["summary"] == "ENG-7: Do work (In Progress)"
    assert status["selected"] == "ENG-7"
