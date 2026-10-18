from __future__ import annotations

import json

import httpx
import pytest

from aoe_linear_plugin.client import API_URL, LinearClient
from aoe_linear_plugin.errors import LinearAuthError, LinearGraphQLError, LinearRateLimitError


def test_graphql_query_sends_token_and_variables(recorded_linear_responses) -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        recorded = recorded_linear_responses["identifier_match"]
        return httpx.Response(recorded["http_status"], json=recorded["body"])

    with LinearClient("secret-token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_by_identifier("LIVE-1")

    assert seen["url"] == API_URL
    assert seen["authorization"] == "secret-token"
    assert seen["body"]["variables"] == {"id": "LIVE-1"}
    assert issue["identifier"] == "LIVE-1"
    assert issue["attachments"]["nodes"][0]["subtitle"] is None


def test_branch_lookup_uses_linear_vcs_branch_search(recorded_linear_responses) -> None:
    seen = {}

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.update(body)
        recorded = recorded_linear_responses["branch_match"]
        return httpx.Response(recorded["http_status"], json=recorded["body"])

    with LinearClient("token", transport=httpx.MockTransport(respond)) as client:
        issue = client.issue_for_branch("recorded/live-1-branch")

    assert seen["variables"] == {"branchName": "recorded/live-1-branch"}
    assert issue["identifier"] == "LIVE-1"
    assert issue["state"]["type"] == "started"


def test_http_auth_rate_limit_and_graphql_errors_are_typed() -> None:
    auth_transport = httpx.MockTransport(lambda _: httpx.Response(401))
    with LinearClient("secret-token", transport=auth_transport) as client, pytest.raises(LinearAuthError) as auth:
        client.execute("query { viewer { id } }")
    assert "secret-token" not in str(auth.value)

    limited_transport = httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "17"}))
    with LinearClient("token", transport=limited_transport) as client, pytest.raises(LinearRateLimitError) as limited:
        client.execute("query { viewer { id } }")
    assert limited.value.retry_after == 17

    errors_transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"errors": [{"message": "bad query"}]}))
    with (
        LinearClient("token", transport=errors_transport) as client,
        pytest.raises(LinearGraphQLError, match="bad query"),
    ):
        client.execute("query { viewer { id } }")


def test_retry_after_is_bounded_and_malformed_header_is_ignored() -> None:
    def response(value: str) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": value})

    for value, expected in (("5000", 3600.0), ("-4", 0.0), ("later", None)):
        transport = httpx.MockTransport(lambda _, value=value: response(value))
        with LinearClient("token", transport=transport) as client, pytest.raises(LinearRateLimitError) as error:
            client.execute("query { viewer { id } }")
        assert error.value.retry_after == expected
